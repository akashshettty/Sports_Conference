from flask_socketio import SocketIO, emit, join_room, leave_room


def register_socketio_handlers(socketio: SocketIO) -> None:
	@socketio.on("connect")
	def on_connect():
		emit("connected", {"message": "Connected to scoreboard server"})

	@socketio.on("join_match")
	def on_join_match(data):
		match_id = data.get("match_id")
		if match_id is not None:
			join_room(f"match_{match_id}")
			emit("joined", {"room": f"match_{match_id}"})

	@socketio.on("leave_match")
	def on_leave_match(data):
		match_id = data.get("match_id")
		if match_id is not None:
			leave_room(f"match_{match_id}")
			emit("left", {"room": f"match_{match_id}"})

	# Helper for server-side to broadcast
	def broadcast_score_update(match_id: int, payload: dict) -> None:
		socketio.emit("score_update", payload, room=f"match_{match_id}")

	# Expose helper on module for import
	register_socketio_handlers.broadcast_score_update = broadcast_score_update


