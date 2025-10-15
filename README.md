# Live Scoreboard (Flask + Socket.IO + Bootstrap)

## Features
- Flask backend with REST API
- Real-time updates via Flask-SocketIO
- SQLite by default, easy switch to PostgreSQL
- Bootstrap frontend, mobile-friendly

## Quick start

```bash
# Windows PowerShell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt

# Initialize database (SQLite file scoreboard.db)
$env:FLASK_APP = "app"
flask db init
flask db migrate -m "init"
flask db upgrade

# Run server
python run.py
```

Open http://localhost:5000

## Switching to PostgreSQL
Set `DATABASE_URL` env var, e.g.

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://user:pass@localhost:5432/scoreboard"
```

## Project layout
```
app/
  __init__.py
  __main__.py
  config.py
  extensions.py
  models.py
  routes.py
  socket_handlers.py
  templates/
    index.html


run.py
requirements.txt

##Sample Results


```


