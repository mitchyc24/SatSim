"""SatSim -- satellite constellation design and viability analysis.

Package layout:

* :mod:`satsim.core`     -- pure astrodynamics engine (no web/DB imports)
* :mod:`satsim.models`   -- SQLAlchemy ORM entities
* :mod:`satsim.services` -- orchestration between core and persistence
* :mod:`satsim.api`      -- REST/JSON blueprint (``/api``)
* :mod:`satsim.web`      -- server-rendered dashboard blueprint
"""

from __future__ import annotations

import os

from flask import Flask

__version__ = "0.1.0"


def create_app(config_overrides: dict = None) -> Flask:
    """Application factory."""
    app = Flask(__name__, instance_relative_config=True)

    from .config import Config

    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.instance_path, exist_ok=True)
    plots_dir = os.path.join(app.instance_path, app.config["PLOTS_SUBDIR"])
    os.makedirs(plots_dir, exist_ok=True)
    app.config["PLOTS_DIR"] = plots_dir

    if not app.config.get("DATABASE_URL"):
        app.config["DATABASE_URL"] = "sqlite:///" + os.path.join(
            app.instance_path, "satsim.db"
        )

    from .db import init_db, shutdown_session

    init_db(app.config["DATABASE_URL"])
    app.teardown_appcontext(shutdown_session)

    from .api import api_bp
    from .web import web_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    return app
