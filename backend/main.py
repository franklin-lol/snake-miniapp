import os
import time
import json
import aiosqlite
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "snake.db")


# ── DB ─────────────────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
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
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = "Player"


class ScoreIn(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = "Player"
    score: int
    length: int
    duration: int  # seconds


class SaveIn(BaseModel):
    user_id: int
    state: dict  # full game state JSON


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/user")
async def upsert_user(user: UserIn):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user.user_id, user.username, user.first_name))
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
            raise HTTPException(status_code=404, detail="User not found")

        async with db.execute("""
            SELECT score, length, duration, created_at
            FROM scores WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 10
        """, (user_id,)) as cur:
            history = [dict(r) for r in await cur.fetchall()]

    return {**dict(row), "history": history}


@app.post("/api/score")
async def submit_score(data: ScoreIn):
    async with aiosqlite.connect(DB_PATH) as db:
        # upsert user
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (data.user_id, data.username, data.first_name))

        # save score entry
        await db.execute("""
            INSERT INTO scores (user_id, score, length, duration)
            VALUES (?, ?, ?, ?)
        """, (data.user_id, data.score, data.length, data.duration))

        # update best + games count
        await db.execute("""
            UPDATE users SET
                games      = games + 1,
                best_score = MAX(best_score, ?)
            WHERE user_id = ?
        """, (data.score, data.user_id))

        await db.commit()

        # return rank
        async with db.execute("""
            SELECT COUNT(*) as cnt FROM users WHERE best_score > ?
        """, (data.score,)) as cur:
            row = await cur.fetchone()
            rank = row[0] + 1

    return {"ok": True, "rank": rank}


@app.get("/api/leaderboard")
async def leaderboard(limit: int = 20):
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
    state_json = json.dumps(data.state)
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
