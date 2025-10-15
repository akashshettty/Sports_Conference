from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from .extensions import db


class Match(db.Model):
	__tablename__ = "matches"

	id = db.Column(db.Integer, primary_key=True)
	team_a = db.Column(db.String(120), nullable=False)
	team_b = db.Column(db.String(120), nullable=False)
	num_sets = db.Column(db.Integer, nullable=False, default=3)
	status = db.Column(db.String(32), nullable=False, default="scheduled")
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

	sets = db.relationship("Set", backref="match", cascade="all, delete-orphan")
	events = db.relationship("Event", backref="match", cascade="all, delete-orphan")


class Set(db.Model):
	__tablename__ = "sets"

	id = db.Column("set_id", db.Integer, primary_key=True)
	match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False, index=True)
	team_a_score = db.Column(db.Integer, nullable=False, default=0)
	team_b_score = db.Column(db.Integer, nullable=False, default=0)
	winner = db.Column(db.String(120), nullable=True)
	# Service tracking fields
	team_a_service_hand = db.Column(db.Integer, nullable=False, default=1)
	team_b_service_hand = db.Column(db.Integer, nullable=False, default=1)
	team_a_max_consecutive = db.Column(db.Integer, nullable=False, default=0)
	team_b_max_consecutive = db.Column(db.Integer, nullable=False, default=0)
	current_serving_team = db.Column(db.String(1), nullable=False, default="A")  # "A" or "B"


class Event(db.Model):
	__tablename__ = "events"

	id = db.Column("event_id", db.Integer, primary_key=True)
	match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False, index=True)
	action = db.Column(db.String(120), nullable=False)
	timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
	extra_data = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=True)


class VoiceEmbedding(db.Model):
	__tablename__ = "voice_embeddings"

	umpire_id = db.Column(db.String(64), primary_key=True)
	# Store as JSON array of floats for SQLite; use REAL[] or vector in Postgres if desired
	embedding = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=False)
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


