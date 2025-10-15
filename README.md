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
<img width="476" height="507" alt="image" src="https://github.com/user-attachments/assets/4b21c9b1-ba15-4c2c-9bd1-03d12c4f3927" />
<img width="674" height="531" alt="image" src="https://github.com/user-attachments/assets/ca9c97ec-3a84-4e7a-9312-22c30e49c3c7" />
<img width="578" height="457" alt="image" src="https://github.com/user-attachments/assets/a9101e88-3fce-4ead-9856-feb90e8f5846" />
<img width="594" height="457" alt="image" src="https://github.com/user-attachments/assets/d749352d-6b41-4704-b936-8879fa053151" />
<img width="580" height="492" alt="image" src="https://github.com/user-attachments/assets/765cc543-7d5d-43d2-832d-0c874896891a" />
<img width="604" height="492" alt="image" src="https://github.com/user-attachments/assets/b0869522-94a5-44cf-ae2e-29af8e76587d" />
<img width="786" height="517" alt="image" src="https://github.com/user-attachments/assets/004c49e0-3487-4b28-b1ad-39b984670374" />

```


