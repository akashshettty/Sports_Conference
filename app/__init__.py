from flask import Flask
from .config import get_config
from .extensions import db, migrate, socketio
from .routes import api_bp
from .views import views_bp
from .socket_handlers import register_socketio_handlers


def create_app(config_name: str | None = None) -> Flask:
	app = Flask(__name__, static_folder="static", template_folder="templates")
	app.config.from_object(get_config(config_name))

	# Extensions
	db.init_app(app)
	migrate.init_app(app, db)
	socketio.init_app(app, cors_allowed_origins="*")

	# Blueprints
	app.register_blueprint(api_bp, url_prefix="/api")
	app.register_blueprint(views_bp)

	# Socket.IO handlers
	register_socketio_handlers(socketio)

	# Basic health route
	@app.get("/health")
	def health() -> tuple[dict, int]:
		return {"status": "ok"}, 200

	return app


