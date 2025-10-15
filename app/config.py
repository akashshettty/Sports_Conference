import os


class BaseConfig:
	SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
	SQLALCHEMY_DATABASE_URI = os.environ.get(
		"DATABASE_URL",
		"sqlite:///scoreboard.db",
	)
	SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(BaseConfig):
	DEBUG = True


class ProductionConfig(BaseConfig):
	DEBUG = False


def get_config(name: str | None):
	if name is None:
		name = os.environ.get("FLASK_ENV", "development")
	name = name.lower()
	if name.startswith("prod"):
		return ProductionConfig
	return DevelopmentConfig


