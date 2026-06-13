# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PirateRace is a turn-based multiplayer 2D tile game. Players program their pirate ship's moves in advance using cards, then watch the round resolve simultaneously — with board elements (currents, turrets, vortexes) also acting each round. First to hit all checkpoints wins.

**Tech stack:** Django REST backend + Angular/Ionic frontend + Phaser 3 game renderer + PostgreSQL + Redis + Nginx, all orchestrated via docker-compose.

## Development Setup

All development runs inside Docker containers. The game is available at `http://localhost:1337` (nginx proxies everything).

```bash
# First-time setup
docker-compose pull
docker-compose build
maint/backend_migrate.sh        # run Django migrations
maint/frontend_npm_install.sh   # install npm deps inside container
maint/backend_collectstatic.sh  # collect static files

# Start everything
docker-compose up -d
```

### Useful maintenance scripts (all run commands inside Docker)

```bash
maint/backend_migrate.sh        # makemigrations + migrate
maint/backend_shell.sh          # bash shell in backend container
maint/backend_shell_plus.sh     # Django shell_plus
maint/frontend_shell.sh         # bash shell in frontend container
maint/db_dump.sh / db_restore.sh
```

### Running tests

```bash
# Backend (Django tests) — no tests currently exist, but this is the command
docker-compose run --rm backend python manage.py test pigame

# Frontend (Karma/Jasmine)
docker-compose run --rm frontend npm test
```

### Linting / Formatting

```bash
maint/prettier.sh               # runs both backend (black) and frontend (prettier)
maint/backend_prettier.sh       # black with --line-length 132
maint/frontend_prettier.sh      # prettier with --print-width 132
```

## Architecture

### Backend (`backend/`)

Django project named `piraterace` with three apps:

- **`pigame`** — core game logic: models (`GameConfig`, `BaseGame`/`ClassicGame`), card definitions, and all game simulation in `game_logic.py`
- **`piplayer`** — user/account management; `Account` extends Django `User` with a `game` FK and `time_submitted` timestamp
- **`pichat`** — in-game and global chat stored entirely in Redis cache (no DB persistence)

**Authentication:** JWT via `djoser` + `djangorestframework_simplejwt`. All API endpoints require `IsAuthenticated`. Custom `AuthenticationMiddlewareJWT` middleware at `piraterace/middleware/jwt_middleware.py`.

**API routes** (all under `/api/`):
- `/api/pigame/` — game config CRUD, game state, card submission, map info
- `/api/piplayer/` — user detail, random name generation
- `/api/pichat/` — global/game/gameconfig chat
- `/api/auth/` — djoser JWT auth (login, register, refresh)

**Storage:** PostgreSQL for persistent data; Redis for player decks (per-game, shuffled), play stack cache, map cache, and all chat messages.

### Game state machine

A game's `BaseGame.state` cycles through: `select` → `countdown` → `animate` → `select` (repeat). The `game` view in `pigame/views.py` drives all state transitions on each GET poll from the frontend.

### Card system (`pigame/models.py` + `game_logic.py`)

Cards are integers encoded as `card_id * NRANKINGS + rank` (where `NRANKINGS=100`). The rank determines play order within a slot (higher rank plays first). `CARDS` dict defines movement/rotation/repair effects; `CANNON_DIRECTION_CARDS` use negative IDs. The `play_stack()` function in `game_logic.py` replays the entire game history from `BaseGame.cards_played` to produce an `actionstack` (list of action groups) that drives frontend animations.

### Maps (`backend/static/maps/`)

Tiled JSON format (`.json`) with required layers: `background` (tile data) and `startinglocs` (object layer), optional `checkpoints` (object layer, named with integers 1..N). Each tile must have all properties defined in `TILE_DEFAULTS` (collision, current_x/y, damage, void, vortex, turret_x/y, fast_current). Maps are validated on creation via `verify_map()` and cached in Redis indefinitely.

### Frontend (`frontend/src/app/`)

Ionic/Angular SPA with lazy-loaded modules:
- **`auth/`** — login/register pages
- **`home/`** — landing page and about
- **`lobby/`** — game list, game config creation/joining/settings
- **`game/`** — the actual game view

**`game/game-scene.ts`** — Phaser 3 `Scene` subclass that handles all rendering and animation playback. It's instantiated by `game.component.ts` which passes itself as `component` so the scene can read `gameinfo`.

**`services/`:**
- `auth.service.ts` — JWT token management, stored via `StorageService` (Ionic Storage)
- `http.service.ts` — all API calls
- `token.interceptor.ts` — auto-attaches JWT header and handles 401 refresh

**Environment config:** `src/environments/environment.ts` sets `API_URL` (`http://localhost:1337/api`) and `STATIC_URL` for dev; `environment.prod.ts` for production.

### Infrastructure

- `docker-compose.yml` — dev setup: backend on `runserver_plus :8000`, frontend with `ionic serve --lab :8100/:8200`, nginx on `:1337`
- `docker-compose-prod.yml` — production: backend via uwsgi, frontend pre-built
- `nginx/` — reverse proxy; `/api/` → backend, `/static/` → static files, everything else → frontend
- `deployment/` — Terraform (Hetzner Cloud) + Ansible for cloud provisioning
