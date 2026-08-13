"""Development entry point.

Usage:
    python run.py            # serve on http://127.0.0.1:5000
    SATSIM_PORT=8080 python run.py
"""

import os

from satsim import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("SATSIM_HOST", "127.0.0.1"),
        port=int(os.environ.get("SATSIM_PORT", "5000")),
        debug=os.environ.get("SATSIM_DEBUG", "1") == "1",
    )
