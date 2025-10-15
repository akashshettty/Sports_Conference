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

⚙️ Key Features

🎙️ Voice & Gesture-Based Scoring

🔁 Real-Time Score Updates via WebSockets

📊 Event Logging & Live Analytics

🧠 AI-Driven Command Recognition

📄 Auto-Generated Match Reports (PDF)

👀 Live Viewer Dashboard for Fans

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
  <img width="476" height="507" alt="Live Scoreboard" src="https://github.com/user-attachments/assets/1cbb7c8d-07c3-4362-b246-ba967fb86343" />
  <br>
  <em>Figure 1: Voice-activated scorekeeping interface.</em>
</p>




