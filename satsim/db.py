"""Database wiring: engine, scoped session, and declarative base.

SQLAlchemy is used directly (no Flask extension) so the same session
machinery serves the Flask app, scripts, and tests.  The application
factory calls :func:`init_db` once at startup; request handlers and
services import :data:`db_session`.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

Base = declarative_base()

# Configured (bound to an engine) by init_db().
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False))

_engine = None


def init_db(database_url: str):
    """Create the engine, bind the session registry, and create tables."""
    global _engine
    connect_args = {}
    if database_url.startswith("sqlite"):
        # The Flask dev server may hand sessions across threads.
        connect_args["check_same_thread"] = False
    _engine = create_engine(database_url, connect_args=connect_args)
    db_session.remove()
    db_session.configure(bind=_engine)

    # Import models so their tables are registered on Base.metadata
    # before create_all runs.
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)
    return _engine


def shutdown_session(exception=None):
    """Flask ``teardown_appcontext`` hook: return the session to the pool."""
    db_session.remove()
