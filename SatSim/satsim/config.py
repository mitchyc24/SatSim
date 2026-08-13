"""Application configuration.

Defaults suit a local single-user deployment; every value can be
overridden with a ``SATSIM_``-prefixed environment variable or a mapping
passed to :func:`satsim.create_app`.
"""

from __future__ import annotations

import os


class Config:
    SECRET_KEY = os.environ.get("SATSIM_SECRET_KEY", "satsim-dev-key")

    # Filled in by create_app() from the instance path when unset.
    DATABASE_URL = os.environ.get("SATSIM_DATABASE_URL")

    # Subdirectory of the instance path holding rendered figures.
    PLOTS_SUBDIR = "plots"
