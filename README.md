# SN▓KE — Telegram Mini App

> Online snake game with 6 food types, live leaderboard, player profiles and game saves.
> Built as a Telegram Mini App. Single-command deploy via Docker Compose.

![Python](https://img.shields.io/badge/Python-3.12-3572A5?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Mini_App-2CA5E0?style=flat-square&logo=telegram&logoColor=white)

---

## Field guide — what's on the board

| Symbol | Name    | Effect |
|--------|---------|--------|
| `◉` Berry  | Standard food   | +score (scales with level) |
| `◆` Gem    | Rare pickup     | ×4 score bonus · glows on field |
| `↯` Charge | Speed boost     | Snake moves ×2 speed for 3 sec |
| `❋` Frost  | Slow motion     | Snake moves ÷2 speed for 4 sec — collect more safely |
| `✕` Poison | Dangerous       | Shrinks snake by 3 segments · game over if length ≤ 3 |
| `◎` Relic  | Rare shrink     | Shrinks by 2 · big point bonus |

Rare items (Gem, Relic) can only appear one at a time. At most 2 foods on field once score passes 200.

---

## Scoring

```
score     += level × multiplier  per food eaten
level      = min(floor(food_eaten / 5) + 1,  6)
multiplier = Berry ×10 · Gem ×40 · Charge ×8 · Frost ×15 · Relic ×25 · Poison ×0
```

Speed per level: 180 → 150 → 120 → 95 → 75 → 60 ms per tick.
Charge halves the tick interval. Frost doubles it.

---

## Features

- **6 food types** with distinct effects — some help, one kills
- **Online leaderboard** — global top-50, your rank shown after each game
- **User profile** — auto-filled from Telegram (name, initials avatar, best score, games)
- **Save & continue** — pause mid-game and resume later
- **Food breakdown** on game over — how many of each type you ate and what it scored
- **Controls** — d-pad buttons, keyboard (WASD / arrows), swipe gestures on canvas
- **Effect timer bar** — visual countdown at the bottom of the field during active effects
- **Mobile-first** — built for Telegram, works in any browser

---

## Stack

| Layer     | Tech |
|-----------|------|
| Frontend  | Vanilla HTML/CSS/JS — no framework, single file |
| Backend   | FastAPI + aiosqlite |
| Database  | SQLite in persistent Docker volume |
| Deploy    | Docker Compose: nginx (frontend) + uvicorn (backend) |

---

## Project structure

```
snake-miniapp/
├── .env.example
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py            FastAPI: users, scores, leaderboard, saves
└── frontend/
    ├── Dockerfile          nginx
    ├── nginx.conf          serves static + proxies /api/ → backend
    └── index.html          game + Mini App UI (all in one file)
```

---

## Quick start

```bash
git clone https://github.com/franklin-lol/snake-miniapp
cd snake-miniapp
cp .env.example .env
docker compose up -d
```

Open `http://localhost` — game runs in browser without Telegram.
In Telegram, user profile fills automatically from `initDataUnsafe.user`.

---

## Telegram setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Use `/newapp` command → set the URL to your deployed frontend
3. Deploy to any VPS:

```bash
# on server
git clone ... && cd snake-miniapp
cp .env.example .env
# edit .env: set WEBAPP_URL, BOT_TOKEN
docker compose up -d
```

Add SSL via certbot + nginx reverse proxy, or use Cloudflare tunnel.

---

## Environment

Copy `.env.example` to `.env` and fill in:

```env
BACKEND_PORT=8000
FRONTEND_PORT=80
DB_PATH=/data/snake.db
BOT_TOKEN=your_bot_token_here
WEBAPP_URL=https://yourdomain.com
```

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/user` | Register / update user |
| `GET` | `/api/user/{id}` | User stats + last 10 games |
| `POST` | `/api/score` | Submit game result → returns rank |
| `GET` | `/api/leaderboard` | Top-50 by best score |
| `POST` | `/api/save` | Save mid-game state (JSON blob) |
| `GET` | `/api/save/{id}` | Load save |
| `DELETE` | `/api/save/{id}` | Delete save |

---

## License

MIT
