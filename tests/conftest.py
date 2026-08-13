import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def app(tmp_path):
    """A SatSim app bound to a throwaway SQLite database."""
    from satsim import create_app

    db_path = os.path.join(str(tmp_path), "test.db")
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite:///" + db_path,
    })
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
