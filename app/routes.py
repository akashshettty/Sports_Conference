from flask import Blueprint, request, jsonify, abort, send_file
from .extensions import db, socketio
from .models import Match, Set, Event
from .voice import parse_command
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


api_bp = Blueprint("api", __name__)

# In-memory guard against rapid duplicate voice commands per match
_last_voice = {}  # match_id -> { 'last_text': str, 'last_ts': float }

# Server-side state: thresholds announced per (match_id, set_id)
_court_change_state: dict[tuple[int, int], set[int]] = {}

# Service tracking state: consecutive points per team per set
_service_consecutive_state: dict[tuple[int, int, str], int] = {}  # (match_id, set_id, team) -> consecutive_count

# Gesture mode toggle per match
_gesture_enabled: dict[int, bool] = {}


def _update_service_tracking(match_id: int, set_id: int, scoring_team: str, current_set: Set) -> None:
	"""Update service hand tracking when a point is scored."""
	# Get the current serving team
	serving_team = current_set.current_serving_team
	
	# Update consecutive count for the scoring team
	consecutive_key = (match_id, set_id, scoring_team)
	current_consecutive = _service_consecutive_state.get(consecutive_key, 0)
	current_consecutive += 1
	_service_consecutive_state[consecutive_key] = current_consecutive
	
	# Update max consecutive for the scoring team
	if scoring_team == "A":
		current_set.team_a_max_consecutive = max(current_set.team_a_max_consecutive, current_consecutive)
	else:
		current_set.team_b_max_consecutive = max(current_set.team_b_max_consecutive, current_consecutive)
	
	# If the scoring team is the serving team, they keep serving
	if scoring_team == serving_team:
		# Reset consecutive count for the other team
		other_team = "B" if scoring_team == "A" else "A"
		other_key = (match_id, set_id, other_team)
		_service_consecutive_state[other_key] = 0
	else:
		# Service changes to the scoring team
		current_set.current_serving_team = scoring_team
		
		# When service changes, increment the hand of the team that is losing service
		# (the team that was previously serving), not the team gaining service
		if serving_team == "A":
			current_set.team_a_service_hand += 1
			# Cycle back to 1 after hand 5
			if current_set.team_a_service_hand > 5:
				current_set.team_a_service_hand = 1
		else:
			current_set.team_b_service_hand += 1
			# Cycle back to 1 after hand 5
			if current_set.team_b_service_hand > 5:
				current_set.team_b_service_hand = 1
		
		# Reset consecutive count for the new serving team
		_service_consecutive_state[consecutive_key] = 1


def _recompute_set_service_tracking(match: Match, current_set: Set) -> None:
	"""Recompute service hands, current server, and max consecutive streaks
	from the event history for this set. This ensures undo/redo keeps service
	state consistent with the actual rally sequence.
	"""
	# Reset per-set tracking fields to defaults
	current_set.team_a_service_hand = 1
	current_set.team_b_service_hand = 1
	current_set.team_a_max_consecutive = 0
	current_set.team_b_max_consecutive = 0
	current_set.current_serving_team = "A"
	# Clear in-memory consecutive counters for this set
	_service_consecutive_state.pop((match.id, current_set.id, "A"), None)
	_service_consecutive_state.pop((match.id, current_set.id, "B"), None)
	# Replay point events for this set in order
	points = Event.query.filter_by(match_id=match.id).filter(Event.action.in_(["point_a", "point_b"]))\
		.order_by(Event.id.asc()).all()
	for e in points:
		try:
			if not e.extra_data or not isinstance(e.extra_data, dict):
				continue
			if e.extra_data.get("set_id") != current_set.id:
				continue
		except Exception:
			continue
		scoring_team = "A" if e.action == "point_a" else "B"
		_update_service_tracking(match.id, current_set.id, scoring_team, current_set)


def _emit_score_update(match_id: int, current_set: Set) -> None:
	payload = {
		"match_id": match_id,
		"set_id": current_set.id,
		"team_a_score": current_set.team_a_score,
		"team_b_score": current_set.team_b_score,
		"winner": current_set.winner,
		# Service tracking data
		"team_a_service_hand": current_set.team_a_service_hand,
		"team_b_service_hand": current_set.team_b_service_hand,
		"team_a_max_consecutive": current_set.team_a_max_consecutive,
		"team_b_max_consecutive": current_set.team_b_max_consecutive,
		"current_serving_team": current_set.current_serving_team,
	}
	# Court-change detection once per threshold per set
	thresholds = {9, 18, 27}
	key = (match_id, current_set.id)
	state = _court_change_state.setdefault(key, set())
	if (current_set.team_a_score in thresholds) or (current_set.team_b_score in thresholds):
		thr = current_set.team_a_score if current_set.team_a_score in thresholds else current_set.team_b_score
		if thr not in state:
			state.add(thr)
			payload["court_change"] = True
			payload["threshold"] = thr
	# Broadcast
	socketio.emit("score_update", payload, room=f"match_{match_id}")


def _check_and_announce_set_and_match(match: Match, current_set: Set) -> None:
	# Determine set winner under badminton-like rule: 35 points per set, win by 2 if tied at 34–34
	a = current_set.team_a_score
	b = current_set.team_b_score
	if current_set.winner:
		return
	if (a >= 35 or b >= 35) and abs(a - b) >= 2:
		current_set.winner = match.team_a if a > b else match.team_b
		db.session.commit()
		# Broadcast set win
		socketio.emit("score_update", {
			"match_id": match.id,
			"set_id": current_set.id,
			"team_a_score": a,
			"team_b_score": b,
			"winner": current_set.winner,
			"announcement": f"Set won by {current_set.winner} {a}-{b}"
		}, room=f"match_{match.id}")


def _undo_last_point(match_id: int) -> bool:
	"""Undo the most recent point event for a match. Returns True if something was undone."""
	last_point = Event.query.filter_by(match_id=match_id).filter(Event.action.in_(["point_a", "point_b"]))\
		.order_by(Event.id.desc()).first()
	if not last_point:
		return False
	# Try to locate the set from event.extra_data
	set_id = None
	try:
		if last_point.extra_data and isinstance(last_point.extra_data, dict):
			set_id = last_point.extra_data.get("set_id")
	except Exception:
		set_id = None
	current_set = None
	if set_id:
		current_set = Set.query.filter_by(id=set_id, match_id=match_id).first()
	if not current_set:
		# Fallback to most recent set
		current_set = Set.query.filter_by(match_id=match_id).order_by(Set.id.desc()).first()
	if not current_set:
		return False
	# Decrement score safely
	if last_point.action == "point_a" and current_set.team_a_score > 0:
		current_set.team_a_score -= 1
	elif last_point.action == "point_b" and current_set.team_b_score > 0:
		current_set.team_b_score -= 1
	else:
		return False
	# If a winner was set and conditions no longer apply, clear winner
	if current_set.winner:
		a = current_set.team_a_score
		b = current_set.team_b_score
		if not ((a >= 35 or b >= 35) and abs(a - b) >= 2):
			current_set.winner = None
	# Delete the event
	db.session.delete(last_point)
	# Recompute service tracking based on remaining events
	match = Match.query.get(match_id)
	if match and current_set:
		_recompute_set_service_tracking(match, current_set)
	# Commit state changes
	db.session.commit()
	# Broadcast
	socketio.emit("event", {
		"match_id": match_id,
		"action": "undo",
		"timestamp": last_point.timestamp.isoformat() if last_point.timestamp else None,
	}, room=f"match_{match_id}")
	_emit_score_update(match_id, current_set)
	return True


@api_bp.post("/matches")
def create_match():
	data = request.get_json() or {}
	team_a = data.get("team_a")
	team_b = data.get("team_b")
	num_sets = int(data.get("num_sets", 3))
	if not team_a or not team_b:
		abort(400, description="team_a and team_b are required")
	match = Match(team_a=team_a, team_b=team_b, num_sets=num_sets)
	db.session.add(match)
	db.session.commit()
	return jsonify({"id": match.id, "status": match.status}), 201


@api_bp.get("/matches")
def list_matches():
	matches = Match.query.order_by(Match.id.desc()).all()
	return jsonify([
		{
			"id": m.id,
			"team_a": m.team_a,
			"team_b": m.team_b,
			"num_sets": m.num_sets,
			"status": m.status,
		}
		for m in matches
	]), 200


@api_bp.get("/matches/<int:match_id>")
def get_match(match_id: int):
	match = Match.query.get_or_404(match_id)
	sets = Set.query.filter_by(match_id=match.id).all()
	return jsonify({
		"id": match.id,
		"team_a": match.team_a,
		"team_b": match.team_b,
		"num_sets": match.num_sets,
		"status": match.status,
        "gesture_enabled": _gesture_enabled.get(match.id, False),
		"sets": [
			{
				"set_id": s.id,
				"team_a_score": s.team_a_score,
				"team_b_score": s.team_b_score,
				"winner": s.winner,
				"team_a_service_hand": s.team_a_service_hand,
				"team_b_service_hand": s.team_b_service_hand,
				"team_a_max_consecutive": s.team_a_max_consecutive,
				"team_b_max_consecutive": s.team_b_max_consecutive,
				"current_serving_team": s.current_serving_team,
			}
			for s in sets
		],
	}), 200


@api_bp.post("/matches/<int:match_id>/sets")
def create_set(match_id: int):
	match = Match.query.get_or_404(match_id)
	new_set = Set(match_id=match.id)
	db.session.add(new_set)
	db.session.commit()
	return jsonify({"set_id": new_set.id}), 201


@api_bp.post("/matches/<int:match_id>/events")
def add_event(match_id: int):
	_ = Match.query.get_or_404(match_id)
	data = request.get_json() or {}
	action = data.get("action")
	# Accept either 'extra_data' or legacy 'metadata'
	extra_data = data.get("extra_data") or data.get("metadata")
	if not action:
		abort(400, description="action is required")
	event = Event(match_id=match_id, action=action, extra_data=extra_data)
	db.session.add(event)
	db.session.commit()
	# broadcast event to clients
	socketio.emit("event", {
		"match_id": match_id,
		"action": action,
		"timestamp": event.timestamp.isoformat(),
	}, room=f"match_{match_id}")
	return jsonify({"event_id": event.id, "timestamp": event.timestamp.isoformat()}), 201


@api_bp.post("/matches/<int:match_id>/gesture_mode")
def set_gesture_mode(match_id: int):
    _ = Match.query.get_or_404(match_id)
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", False))
    _gesture_enabled[match_id] = enabled
    socketio.emit("event", {"match_id": match_id, "action": "gesture_mode", "enabled": enabled, "timestamp": None}, room=f"match_{match_id}")
    return jsonify({"ok": True, "gesture_enabled": enabled})


@api_bp.post("/matches/<int:match_id>/gesture_command")
def gesture_command(match_id: int):
    _ = Match.query.get_or_404(match_id)
    if not _gesture_enabled.get(match_id, False):
        return jsonify({"ok": False, "reason": "gesture_disabled"}), 200
    data = request.get_json() or {}
    cmd = (data.get("command") or "").lower().strip()
    # Map commands to existing flows to avoid code duplication
    if cmd == "point_a":
        # Reuse voice transcript flow for consistency with parsing/guards
        return voice_transcript_proxy(match_id, "point to team a")
    if cmd == "point_b":
        return voice_transcript_proxy(match_id, "point to team b")
    if cmd == "undo":
        ok = _undo_last_point(match_id)
        return jsonify({"ok": ok, "action": "undo"})
    if cmd == "next_set":
        new_set = Set(match_id=match_id)
        db.session.add(new_set)
        db.session.commit()
        socketio.emit("event", {"match_id": match_id, "action": "next_set", "timestamp": None}, room=f"match_{match_id}")
        return jsonify({"ok": True, "action": "next_set", "set_id": new_set.id})
    if cmd == "reset_match":
        # Mirror reset flow
        Event.query.filter_by(match_id=match_id).delete()
        Set.query.filter_by(match_id=match_id).delete()
        db.session.commit()
        for k in list(_court_change_state.keys()):
            if k[0] == match_id:
                _court_change_state.pop(k, None)
        for k in list(_service_consecutive_state.keys()):
            if k[0] == match_id:
                _service_consecutive_state.pop(k, None)
        socketio.emit("event", {"match_id": match_id, "action": "reset_match", "timestamp": None}, room=f"match_{match_id}")
        socketio.emit("score_update", {"match_id": match_id, "set_id": None, "team_a_score": 0, "team_b_score": 0}, room=f"match_{match_id}")
        return jsonify({"ok": True, "action": "reset_match"})
    return jsonify({"ok": False, "reason": "unknown_command"}), 200


def voice_transcript_proxy(match_id: int, transcript: str):
    # Internal helper to reuse voice handler logic without HTTP round-trip
    class DummyReq:
        def __init__(self, match_id, transcript):
            self.json = {"match_id": match_id, "transcript": transcript}
    # Monkey: temporarily swap request object is heavy; instead, directly call parse + partial logic
    match = Match.query.get_or_404(match_id)
    cmd = parse_command(transcript, team_a_name=match.team_a, team_b_name=match.team_b)
    if not cmd:
        return jsonify({"ok": False, "reason": "unrecognized"}), 200
    # Minimal subset: only points reusing same code path
    current_set = Set.query.filter_by(match_id=match.id).order_by(Set.id.desc()).first()
    if not current_set:
        current_set = Set(match_id=match.id)
        db.session.add(current_set)
        db.session.commit()
    if cmd.type == "point":
        if current_set.winner:
            return jsonify({"ok": False, "reason": "set_over"}), 200
        if cmd.team == "A":
            current_set.team_a_score += 1
            act = "point_a"
        else:
            current_set.team_b_score += 1
            act = "point_b"
        _update_service_tracking(match.id, current_set.id, cmd.team, current_set)
        evt = Event(match_id=match.id, action=act, extra_data={"set_id": current_set.id})
        db.session.add(evt)
        db.session.commit()
        socketio.emit("event", {"match_id": match.id, "action": act, "timestamp": evt.timestamp.isoformat()}, room=f"match_{match.id}")
        _check_and_announce_set_and_match(match, current_set)
        _emit_score_update(match.id, current_set)
        return jsonify({"ok": True, "action": act})
    return jsonify({"ok": False, "reason": "no_action"}), 200


@api_bp.post("/matches/<int:match_id>/undo")
def undo_endpoint(match_id: int):
	_ = Match.query.get_or_404(match_id)
	ok = _undo_last_point(match_id)
	return jsonify({"ok": ok}), 200


@api_bp.post("/matches/<int:match_id>/sets/<int:set_id>/score")
def update_score(match_id: int, set_id: int):
	_ = Match.query.get_or_404(match_id)
	current_set = Set.query.filter_by(id=set_id, match_id=match_id).first()
	if not current_set:
		abort(404, description="set not found")
	# Stop further scoring if set already has a winner
	if current_set.winner:
		return jsonify({
			"match_id": match_id,
			"set_id": set_id,
			"team_a_score": current_set.team_a_score,
			"team_b_score": current_set.team_b_score,
			"winner": current_set.winner,
		}), 200
	data = request.get_json() or {}
	team_a_score = data.get("team_a_score")
	team_b_score = data.get("team_b_score")
	
	# Determine which team scored (if any)
	prev_a = current_set.team_a_score
	prev_b = current_set.team_b_score
	
	if team_a_score is not None:
		current_set.team_a_score = int(team_a_score)
	if team_b_score is not None:
		current_set.team_b_score = int(team_b_score)
	
	# Update service tracking if a point was scored
	if team_a_score is not None and team_a_score > prev_a:
		_update_service_tracking(match_id, set_id, "A", current_set)
	elif team_b_score is not None and team_b_score > prev_b:
		_update_service_tracking(match_id, set_id, "B", current_set)
	
	if data.get("winner"):
		current_set.winner = data["winner"]
	db.session.commit()

	# Check set/match completion per rule: 35 points, win by 2 if ≥ 34–34
	_check_and_announce_set_and_match(Match.query.get(match_id), current_set)

	_emit_score_update(match_id, current_set)
	return jsonify({
		"match_id": match_id,
		"set_id": set_id,
		"team_a_score": current_set.team_a_score,
		"team_b_score": current_set.team_b_score,
		"winner": current_set.winner,
	}), 200


@api_bp.post("/voice/transcript")
def voice_transcript():
	import time
	data = request.get_json() or {}
	match_id = data.get("match_id")
	transcript = data.get("transcript", "")
	if not match_id:
		abort(400, description="match_id required")
	match = Match.query.get_or_404(match_id)
	# Broadcast raw transcript for UI visibility
	socketio.emit("transcript", {"match_id": match.id, "text": transcript}, room=f"match_{match.id}")
	# Simple duplicate guard within 1.2s for identical transcripts per match
	now = time.time()
	info = _last_voice.get(match.id)
	if info and info.get('last_text') == transcript and (now - info.get('last_ts', 0)) < 1.2:
		return jsonify({"ok": False, "reason": "duplicate_ignored"}), 200
	_last_voice[match.id] = { 'last_text': transcript, 'last_ts': now }

	cmd = parse_command(transcript, team_a_name=match.team_a, team_b_name=match.team_b)
	if not cmd:
		return jsonify({"ok": False, "reason": "unrecognized"}), 200

	# Ensure set exists only for actions that modify or require a new set
	current_set = Set.query.filter_by(match_id=match.id).order_by(Set.id.desc()).first()
	if not current_set and cmd.type in ("point", "next_set"):
		current_set = Set(match_id=match.id)
		db.session.add(current_set)
		db.session.commit()

	if cmd.type == "point":
		# Stop scoring if set already decided
		if current_set and current_set.winner:
			return jsonify({"ok": False, "reason": "set_over"}), 200
		if cmd.team == "A":
			current_set.team_a_score += 1
			act = "point_a"
		else:
			current_set.team_b_score += 1
			act = "point_b"
		
		# Update service tracking
		_update_service_tracking(match.id, current_set.id, cmd.team, current_set)
		
		evt = Event(match_id=match.id, action=act, extra_data={"set_id": current_set.id})
		db.session.add(evt)
		db.session.commit()
		# Broadcast event
		socketio.emit("event", {
			"match_id": match.id,
			"action": act,
			"timestamp": evt.timestamp.isoformat(),
		}, room=f"match_{match.id}")
		# Check set/match completion
		_check_and_announce_set_and_match(match, current_set)
		_emit_score_update(match.id, current_set)
		return jsonify({
			"ok": True,
			"action": act,
			"match_id": match.id,
			"set_id": current_set.id,
			"team_a_score": current_set.team_a_score,
			"team_b_score": current_set.team_b_score,
		})

	if cmd.type == "undo":
		ok = _undo_last_point(match.id)
		return jsonify({"ok": ok, "action": "undo"})

	if cmd.type == "whats_score":
		# Announce current score without mutating state
		a = current_set.team_a_score if current_set else 0
		b = current_set.team_b_score if current_set else 0
		payload = {
			"match_id": match.id,
			"set_id": current_set.id if current_set else None,
			"team_a_score": a,
			"team_b_score": b,
			"winner": current_set.winner if current_set else None,
			"announcement": f"Current score {a}-{b}.",
		}
		# Emit so clients can speak the score immediately
		socketio.emit("score_update", payload, room=f"match_{match.id}")
		return jsonify({
			"ok": True,
			"team_a_score": a,
			"team_b_score": b,
		})

	if cmd.type == "next_set":
		new_set = Set(match_id=match.id)
		db.session.add(new_set)
		db.session.commit()
		socketio.emit("event", {
			"match_id": match.id,
			"action": "next_set",
			"timestamp": None,
		}, room=f"match_{match.id}")
		return jsonify({"ok": True, "action": "next_set", "set_id": new_set.id})

	if cmd.type == "reset_match":
		# Delete sets and events
		Event.query.filter_by(match_id=match.id).delete()
		Set.query.filter_by(match_id=match.id).delete()
		db.session.commit()
		# Clear court-change memory for this match (all sets)
		for k in list(_court_change_state.keys()):
			if k[0] == match.id:
				_court_change_state.pop(k, None)
		# Clear service tracking memory for this match (all sets)
		for k in list(_service_consecutive_state.keys()):
			if k[0] == match.id:
				_service_consecutive_state.pop(k, None)
		socketio.emit("event", {
			"match_id": match.id,
			"action": "reset_match",
			"timestamp": None,
		}, room=f"match_{match.id}")
		socketio.emit("score_update", {
			"match_id": match.id,
			"set_id": None,
			"team_a_score": 0,
			"team_b_score": 0,
		}, room=f"match_{match.id}")
		return jsonify({"ok": True, "action": "reset_match"})

	return jsonify({"ok": False, "reason": "no_action"})


@api_bp.get("/reports/<int:match_id>/pdf")
def report_pdf(match_id: int):
	match = Match.query.get_or_404(match_id)
	sets = Set.query.filter_by(match_id=match.id).order_by(Set.id.asc()).all()
	events = Event.query.filter_by(match_id=match.id).order_by(Event.id.asc()).all()

	buf = io.BytesIO()
	doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
	styles = getSampleStyleSheet()
	story = []

	# Title
	title = Paragraph(f"<b>Ball Badminton Match Report</b>", styles['Title'])
	story.append(title)
	story.append(Spacer(1, 12))
	meta = Paragraph(f"Match ID: <b>{match.id}</b> &nbsp;&nbsp; Teams: <b>{match.team_a}</b> vs <b>{match.team_b}</b>", styles['Normal'])
	story.append(meta)
	story.append(Spacer(1, 6))

	# Sets table
	set_data = [["Set", f"{match.team_a}", f"{match.team_b}", "Winner"]]
	for idx, s in enumerate(sets, start=1):
		set_data.append([idx, s.team_a_score, s.team_b_score, s.winner or "-"])

	table = Table(set_data, hAlign='LEFT')
	table.setStyle(TableStyle([
		('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
		('BOX', (0,0), (-1,-1), 0.5, colors.black),
		('GRID', (0,0), (-1,-1), 0.25, colors.grey),
		('ALIGN', (1,1), (-2,-1), 'CENTER'),
		('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
	]))
	story.append(Spacer(1, 12))
	story.append(Paragraph("<b>Set Summary</b>", styles['Heading2']))
	story.append(table)

	# Service Tracking Summary
	story.append(Spacer(1, 12))
	story.append(Paragraph("<b>Service Tracking Summary</b>", styles['Heading2']))
	
	service_data = [["Set", f"{match.team_a} Service Hands", f"{match.team_b} Service Hands", f"{match.team_a} Max Consecutive", f"{match.team_b} Max Consecutive"]]
	for idx, s in enumerate(sets, start=1):
		service_data.append([
			idx,
			f"Hand {s.team_a_service_hand}",
			f"Hand {s.team_b_service_hand}",
			s.team_a_max_consecutive,
			s.team_b_max_consecutive
		])
	
	service_table = Table(service_data, hAlign='LEFT')
	service_table.setStyle(TableStyle([
		('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
		('BOX', (0,0), (-1,-1), 0.5, colors.black),
		('GRID', (0,0), (-1,-1), 0.25, colors.grey),
		('ALIGN', (1,1), (-1,-1), 'CENTER'),
		('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
	]))
	story.append(service_table)

	# Summary analytics
	story.append(Spacer(1, 12))
	total_rallies = sum((s.team_a_score + s.team_b_score) for s in sets) if sets else 0
	lead_changes = 0  # simple placeholder; computing precisely requires rally timeline
	
	# Calculate service tracking statistics
	max_consecutive_overall = 0
	if sets:
		max_consecutive_overall = max(max(s.team_a_max_consecutive, s.team_b_max_consecutive) for s in sets)
	
	summary = [
		["Metric", "Value"],
		["Total Rallies", total_rallies],
		["Lead Changes (approx)", lead_changes],
		["Max Consecutive Service (Overall)", max_consecutive_overall],
	]
	summary_table = Table(summary, hAlign='LEFT')
	summary_table.setStyle(TableStyle([
		('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
		('BOX', (0,0), (-1,-1), 0.5, colors.black),
		('GRID', (0,0), (-1,-1), 0.25, colors.grey),
		('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
	]))
	story.append(Paragraph("<b>Live Analytics Summary</b>", styles['Heading2']))
	story.append(summary_table)

	# Event log
	story.append(Spacer(1, 12))
	story.append(Paragraph("<b>Event Log</b>", styles['Heading2']))
	event_rows = [["Time", "Event"]]
	for e in events:
		label = e.action
		if e.action == 'point_a':
			label = f"Point to {match.team_a}"
		elif e.action == 'point_b':
			label = f"Point to {match.team_b}"
		event_rows.append([e.timestamp.strftime('%H:%M:%S'), label])
	event_table = Table(event_rows, hAlign='LEFT', colWidths=[80, 400])
	event_table.setStyle(TableStyle([
		('BOX', (0,0), (-1,-1), 0.5, colors.black),
		('GRID', (0,0), (-1,-1), 0.25, colors.grey),
		('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
		('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
	]))
	story.append(event_table)

	doc.build(story)
	buf.seek(0)
	filename = f"match_{match.id}_report.pdf"
	return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/pdf')


