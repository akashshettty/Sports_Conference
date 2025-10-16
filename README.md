# Voice and Gesture-Activated Scorekeeping and Real-Time Scoreboard Management System for Ball Badminton

## 📖 Project Description

This project introduces an AI-powered voice and gesture-based scorekeeping system designed to modernize traditional Ball Badminton scoring. The system allows umpires to record scores using voice commands or hand gestures, reducing manual errors and improving the speed and accuracy of scoring. It also offers real-time score updates, event logging, and automatic match reports, creating a professional and engaging experience for players, coaches, and fans.

Built using Flask (backend), SQLAlchemy (database), and Socket.IO (real-time communication), the system ensures seamless synchronization between the umpire’s interface, the live scoreboard, and spectator dashboards. The Web Speech API and Vosk handle voice recognition, while MediaPipe and OpenCV enable gesture-based scoring.

## 🎯 Why It Is Used

To eliminate score disputes and human errors during matches.

To provide hands-free scoring for umpires using voice or gesture controls.

To display live scores and analytics for spectators and coaches.

To auto-generate match reports with all scores, events, and statistics.

To make Ball Badminton smarter, fairer, and more interactive through technology.

⚙️ How It Works

Voice & Gesture Recognition:
Umpires can update scores using simple voice commands (via Web Speech API & Vosk) or gestures (via MediaPipe + OpenCV). Commands like “Point Team A” or a ✌️ hand gesture instantly update the live scoreboard.

Real-Time Synchronization:
The backend, built with Flask and Flask-SocketIO, updates all connected clients instantly — including the umpire dashboard and spectator view.

Database & Reports:
Match data such as scores, service hands, and events are stored using SQLAlchemy (PostgreSQL/SQLite) and compiled into auto-generated PDF reports using ReportLab.

Service Tracking:
The system tracks which hand is serving (1–5) and displays consecutive service streaks to reduce confusion and improve accuracy.

Spectator & Coach Features:
Fans can view live match analytics and updates in real time, while coaches access post-match insights for performance analysis.
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
```
## 🧾 Sample Results

Here’s an example of the live scoreboard display:
<p align="center">
<img width="786" height="517" alt="image" src="https://github.com/user-attachments/assets/e384a37d-1945-4610-8dff-a550c409af97" />
  <br>
  <em>Figure 1: Voice-activated scorekeeping interface.</em>
</p>
<p align="center">
<img width="604" height="492" alt="image" src="https://github.com/user-attachments/assets/16b1704e-7a3d-4393-9c04-01dc922f3a69" />
  <br>
  <em>Figure 2: Setup match.</em>
</p>
<p align="center">
<img width="674" height="531" alt="image" src="https://github.com/user-attachments/assets/6240eeee-fbdb-46bf-b36c-2d49cda657b2" />
<br>
  <em>Figure 3: Scoarboard Sample.</em>
</p>
<p align="center">
  <img width="578" height="457" alt="image" src="https://github.com/user-attachments/assets/9dba5fac-ec59-48a1-80ce-5e476adf0d62" />
<br>
  <em>Figure 4: Live Analytics.</em>
</p>
<p align="center">
<img width="580" height="492" alt="image" src="https://github.com/user-attachments/assets/edb1ca7a-6c2d-4ac3-9b0b-4d6112845e31" />
<br>
  <em>Figure 5: Watch Mode Setup.</em>
</p>
<p align="center">
<img width="476" height="507" alt="image" src="https://github.com/user-attachments/assets/fc2f3490-70d5-4cf9-a004-6b77d7e4d620" />
  <br>
  <em>Figure 6: Sample Pdf Report.</em>
</p>






