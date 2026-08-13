"""Application services.

Services orchestrate the pure :mod:`satsim.core` engine and the
:mod:`satsim.models` persistence layer.  Both the REST API and the web
dashboard call into this package, so behaviour stays identical across
interfaces and route handlers stay thin.
"""

from .scenarios import (
    ValidationError,
    add_ground_station,
    add_satellite,
    add_walker_constellation,
    create_scenario,
    delete_ground_station,
    delete_satellite,
    delete_scenario,
    get_run,
    get_scenario,
    list_scenarios,
)
from .simulation import SimulationOutput, run_scenario, simulate

__all__ = [
    "SimulationOutput",
    "ValidationError",
    "add_ground_station",
    "add_satellite",
    "add_walker_constellation",
    "create_scenario",
    "delete_ground_station",
    "delete_satellite",
    "delete_scenario",
    "get_run",
    "get_scenario",
    "list_scenarios",
    "run_scenario",
    "simulate",
]
