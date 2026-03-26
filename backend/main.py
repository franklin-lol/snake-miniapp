import os
import time
import json
import aiosqlite
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

DB_PATH  = os.environ.get("DB_PATH", "snake.db")
COLS, ROWS = 20, 20

# ── Simple in-memory rate limiter ─────────────────────────────────────────────
_score_last: dict[int, float] = defaultdict(float)
SCORE_RATE_SEC = 8          # minimum seconds between submits per user


# ── DB ─────────────────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Performance pragmas
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-8000")   # 8 MB page cache
        await db.execute("PRAGMA temp_store=MEMORY")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                best_score  INTEGER DEFAULT 0,
                games       INTEGER DEFAULT 0,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                score       INTEGER,
                length      INTEGER,
                duration    INTEGER,
                created_at  INTEGER DEFAULT (strftime('%s','now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saves (
                user_id     INTEGER PRIMARY KEY,
                state       TEXT,
                updated_at  INTEGER DEFAULT (strftime('%s','now'))
            )
        """)

        # Indexes for leaderboard + history queries
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scores_user ON scores(user_id, created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_best ON users(best_score DESC)"
        )

        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────────────────

class UserIn(BaseModel):
    user_id:    int
    username:   Optional[str] = None
    first_name: Optional[str] = "Player"


class ScoreIn(BaseModel):
    user_id:    int
    username:   Optional[str] = None
    first_name: Optional[str] = "Player"
    score:      int
    length:     int
    duration:   int   # seconds


class SaveIn(BaseModel):
    user_id: int
    state:   dict


# ── Validation helpers ─────────────────────────────────────────────────────────

MAX_SCORE  = COLS * ROWS * 40 * 6   # theoretical ceiling: all gems, max level
MAX_LENGTH = COLS * ROWS

def validate_score(data: ScoreIn):
    if not (0 <= data.score <= MAX_SCORE):
        raise HTTPException(400, f"Invalid score (0–{MAX_SCORE})")
    if not (3 <= data.length <= MAX_LENGTH):
        raise HTTPException(400, f"Invalid length (3–{MAX_LENGTH})")
    if not (1 <= data.duration <= 3600):
        raise HTTPException(400, "Invalid duration (1–3600 sec)")
    if data.user_id < 1:
        raise HTTPException(400, "Invalid user_id")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/user")
async def upsert_user(user: UserIn):
    if user.user_id < 1:
        raise HTTPException(400, "Invalid user_id")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user.user_id, user.username, user.first_name or "Player"))
        await db.commit()
    return {"ok": True}


@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "User not found")

        async with db.execute("""
            SELECT score, length, duration, created_at
            FROM scores WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 10
        """, (user_id,)) as cur:
            history = [dict(r) for r in await cur.fetchall()]

    return {**dict(row), "history": history}


@app.post("/api/score")
async def submit_score(data: ScoreIn):
    # Rate limit
    now = time.time()
    if now - _score_last[data.user_id] < SCORE_RATE_SEC:
        raise HTTPException(429, "Too many requests — wait a moment")
    _score_last[data.user_id] = now

    # Validate
    validate_score(data)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (data.user_id, data.username, data.first_name or "Player"))

        await db.execute("""
            INSERT INTO scores (user_id, score, length, duration)
            VALUES (?, ?, ?, ?)
        """, (data.user_id, data.score, data.length, data.duration))

        await db.execute("""
            UPDATE users SET
                games      = games + 1,
                best_score = MAX(best_score, ?)
            WHERE user_id = ?
        """, (data.score, data.user_id))

        await db.commit()

        async with db.execute("""
            SELECT COUNT(*) AS cnt FROM users WHERE best_score > ?
        """, (data.score,)) as cur:
            row = await cur.fetchone()
            rank = row[0] + 1

    return {"ok": True, "rank": rank}


@app.get("/api/leaderboard")
async def leaderboard(limit: int = 50):
    limit = min(max(limit, 1), 100)   # clamp 1–100
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT user_id, first_name, username, best_score, games
            FROM users
            WHERE best_score > 0
            ORDER BY best_score DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return {"leaderboard": rows}


@app.post("/api/save")
async def save_game(data: SaveIn):
    if data.user_id < 1:
        raise HTTPException(400, "Invalid user_id")
    state_json = json.dumps(data.state)
    if len(state_json) > 64_000:
        raise HTTPException(400, "Save state too large")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO saves (user_id, state, updated_at)
            VALUES (?, ?, strftime('%s','now'))
            ON CONFLICT(user_id) DO UPDATE SET
                state      = excluded.state,
                updated_at = excluded.updated_at
        """, (data.user_id, state_json))
        await db.commit()
    return {"ok": True}


@app.get("/api/save/{user_id}")
async def load_game(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT state, updated_at FROM saves WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return {"save": None}
    return {"save": json.loads(row["state"]), "updated_at": row["updated_at"]}


@app.delete("/api/save/{user_id}")
async def delete_save(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM saves WHERE user_id = ?", (user_id,))
        await db.commit()
    return {"ok": True}
