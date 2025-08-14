# Hit4Power Player Development Tool

FastAPI + Jinja2 app designed for Render.

## Features
- Player & Instructor logins (embedded on their pages)
- Clients (Roster renamed), "My Clients" favorites (⭐) that update live
- Instructor: create player (with photo), bulk CSV import, add metrics (Exit Velocity only), coach notes, drill library (upload & send), optional SMS via Twilio
- Player: compact red chart, coach notes (only if shared)
- Theme toggle with persisted preference, logo shown

## Environment
- `SESSION_SECRET` (required)
- `INSTRUCTOR_MASTER_CODE` (bootstrap instructor creation; default COACH123)
- Optional for SMS: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

