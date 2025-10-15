from flask import Blueprint, render_template


views_bp = Blueprint("views", __name__)


@views_bp.get("/")
def landing():
	return render_template("landing.html")


@views_bp.get("/setup")
def setup():
	return render_template("setup.html")


@views_bp.get("/matches")
def matches_list():
	return render_template("matches.html")


@views_bp.get("/scoreboard/<int:match_id>")
def scoreboard(match_id: int):
	return render_template("scoreboard.html", match_id=match_id)


@views_bp.get("/analytics/<int:match_id>")
def analytics(match_id: int):
	return render_template("analytics.html", match_id=match_id)


@views_bp.get("/watch")
def watch_match():
	return render_template("watch.html")


