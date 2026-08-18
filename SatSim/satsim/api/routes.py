"""REST/JSON endpoints.

All routes return JSON.  Validation problems map to HTTP 400, missing
entities to 404; both carry ``{"error": "..."}`` bodies.  The endpoints
mirror the capabilities of the web dashboard so scripted studies
(parameter sweeps, batch runs) can drive SatSim programmatically.
"""

from __future__ import annotations

import math

from flask import Blueprint, Response, current_app, jsonify, request

from ..db import db_session
from ..services import scenarios as scenario_svc
from ..services.scenarios import NotFoundError, ValidationError
from ..services.simulation import run_scenario
from ..utils import parse_utc_datetime

api_bp = Blueprint("api", __name__)

#: Samples per orbit returned by the visualization endpoint.  Enough for
#: a smooth ring at any zoom the 3D view offers without bloating the
#: payload for a large constellation.
ORBIT_SAMPLES = 72


@api_bp.errorhandler(ValidationError)
def _validation_error(exc):
    return jsonify({"error": str(exc)}), 400


@api_bp.errorhandler(NotFoundError)
def _not_found_error(exc):
    return jsonify({"error": str(exc)}), 404


def _payload() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        raise ValidationError("Request body must be a JSON object")
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    return data


def _require(data: dict, *keys):
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValidationError("Missing required field(s): %s" % ", ".join(missing))


# ----------------------------------------------------------------------
# Scenarios
# ----------------------------------------------------------------------
@api_bp.route("/scenarios", methods=["GET"])
def list_scenarios():
    scenarios = scenario_svc.list_scenarios(db_session)
    return jsonify({"scenarios": [s.to_dict() for s in scenarios]})


@api_bp.route("/scenarios", methods=["POST"])
def create_scenario():
    data = _payload()
    _require(data, "name", "start_time")
    try:
        start_time = parse_utc_datetime(data["start_time"])
    except ValueError as exc:
        raise ValidationError(str(exc))
    scenario = scenario_svc.create_scenario(
        db_session,
        name=data["name"],
        start_time=start_time,
        duration_s=data.get("duration_s", 86400.0),
        time_step_s=data.get("time_step_s", 60.0),
        description=data.get("description", ""),
    )
    return jsonify(scenario.to_dict()), 201


@api_bp.route("/scenarios/<int:scenario_id>", methods=["GET"])
def get_scenario(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    return jsonify(scenario.to_dict(include_children=True))


@api_bp.route("/scenarios/<int:scenario_id>", methods=["DELETE"])
def delete_scenario(scenario_id):
    scenario_svc.delete_scenario(db_session, scenario_id)
    return jsonify({"deleted": scenario_id})


# ----------------------------------------------------------------------
# Satellites
# ----------------------------------------------------------------------
@api_bp.route("/scenarios/<int:scenario_id>/satellites", methods=["POST"])
def add_satellite(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    data = _payload()
    _require(data, "name", "semi_major_axis_km", "inclination_deg")
    satellite = scenario_svc.add_satellite(
        db_session,
        scenario,
        name=data["name"],
        semi_major_axis_km=data["semi_major_axis_km"],
        eccentricity=data.get("eccentricity", 0.0),
        inclination_deg=data["inclination_deg"],
        raan_deg=data.get("raan_deg", 0.0),
        arg_perigee_deg=data.get("arg_perigee_deg", 0.0),
        true_anomaly_deg=data.get("true_anomaly_deg", 0.0),
        constellation=data.get("constellation", ""),
    )
    return jsonify(satellite.to_dict()), 201


@api_bp.route(
    "/scenarios/<int:scenario_id>/satellites/<int:satellite_id>",
    methods=["DELETE"],
)
def delete_satellite(scenario_id, satellite_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    scenario_svc.delete_satellite(db_session, scenario, satellite_id)
    return jsonify({"deleted": satellite_id})


@api_bp.route("/scenarios/<int:scenario_id>/walker", methods=["POST"])
def add_walker(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    data = _payload()
    _require(data, "total_satellites", "planes", "relative_phasing",
             "altitude_km", "inclination_deg")
    satellites = scenario_svc.add_walker_constellation(
        db_session,
        scenario,
        total_satellites=data["total_satellites"],
        planes=data["planes"],
        relative_phasing=data["relative_phasing"],
        altitude_km=data["altitude_km"],
        inclination_deg=data["inclination_deg"],
        name_prefix=data.get("name_prefix", "SAT"),
        raan_offset_deg=data.get("raan_offset_deg", 0.0),
        pattern=data.get("pattern", "delta"),
    )
    return jsonify({
        "created": len(satellites),
        "satellites": [s.to_dict() for s in satellites],
    }), 201


# ----------------------------------------------------------------------
# Ground stations
# ----------------------------------------------------------------------
@api_bp.route("/scenarios/<int:scenario_id>/ground-stations", methods=["POST"])
def add_ground_station(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    data = _payload()
    _require(data, "name", "latitude_deg", "longitude_deg")
    station = scenario_svc.add_ground_station(
        db_session,
        scenario,
        name=data["name"],
        latitude_deg=data["latitude_deg"],
        longitude_deg=data["longitude_deg"],
        altitude_m=data.get("altitude_m", 0.0),
        min_elevation_deg=data.get("min_elevation_deg", 5.0),
    )
    return jsonify(station.to_dict()), 201


@api_bp.route(
    "/scenarios/<int:scenario_id>/ground-stations/<int:station_id>",
    methods=["DELETE"],
)
def delete_ground_station(scenario_id, station_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    scenario_svc.delete_ground_station(db_session, scenario, station_id)
    return jsonify({"deleted": station_id})


# ----------------------------------------------------------------------
# Simulation runs
# ----------------------------------------------------------------------
@api_bp.route("/scenarios/<int:scenario_id>/run", methods=["POST"])
def run_simulation(scenario_id):
    run = run_scenario(
        db_session, scenario_id, plots_dir=current_app.config["PLOTS_DIR"]
    )
    return jsonify(run.to_dict()), 201


@api_bp.route("/runs/<int:run_id>", methods=["GET"])
def get_run(run_id):
    run = scenario_svc.get_run(db_session, run_id)
    return jsonify(run.to_dict(include_passes=True))


@api_bp.route("/scenarios/<int:scenario_id>/visualization", methods=["GET"])
def get_visualization_data(scenario_id):
    """Scene description for the 3D view.

    Everything is returned in Earth radii so the client can render
    without knowing any physical constants:

    * ``satellites[].orbit_positions`` -- one revolution of the two-body
      ellipse in ECI, sampled uniformly in time (see
      :meth:`ClassicalElements.sample_orbit_km`), so a client stepping
      through the array at a constant rate animates the orbit correctly.
      ``phase`` is where the satellite sits in that array at the epoch.
    * ``ground_stations[].position_ecef`` / ``up_ecef`` -- the WGS-84
      site vector and its local vertical, enough to compute a true
      elevation angle client-side and draw links only for real contacts.
    * ``earth_angle_deg`` / ``earth_rotation_deg_s`` -- how to spin the
      Earth-fixed frame against the inertial orbits.
    """
    from ..core.constants import (
        EARTH_ROTATION_RATE_RAD_S,
        R_EARTH_EQ_KM,
    )
    from ..core.frames import eci_to_ecef_angle_deg

    scenario = scenario_svc.get_scenario(db_session, scenario_id)

    satellites_data = []
    for sat in scenario.satellites:
        elements = sat.to_elements()
        positions = elements.sample_orbit_km(ORBIT_SAMPLES) / R_EARTH_EQ_KM
        satellites_data.append({
            "id": sat.id,
            "name": sat.name,
            "constellation": sat.constellation or "",
            "perigee_altitude_km": round(elements.perigee_altitude_km, 1),
            "apogee_altitude_km": round(elements.apogee_altitude_km, 1),
            "orbit_positions": [
                [round(float(v), 5) for v in row] for row in positions
            ],
            "phase": round(elements.mean_anomaly_deg / 360.0, 6),
            "period_s": round(elements.period_s(), 1),
        })

    stations_data = []
    for gs in scenario.ground_stations:
        geometry = gs.to_geometry()
        position = geometry.ecef_km / R_EARTH_EQ_KM
        up = geometry.enu_basis[2]
        stations_data.append({
            "id": gs.id,
            "name": gs.name,
            "latitude_deg": gs.latitude_deg,
            "longitude_deg": gs.longitude_deg,
            "altitude_m": gs.altitude_m,
            "min_elevation_deg": gs.min_elevation_deg,
            "position_ecef": [round(float(v), 5) for v in position],
            "up_ecef": [round(float(v), 5) for v in up],
        })

    return jsonify({
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "epoch_utc": scenario.start_time.isoformat(),
        "duration_s": scenario.duration_s,
        "earth_radius_km": R_EARTH_EQ_KM,
        "earth_angle_deg": round(
            eci_to_ecef_angle_deg(scenario.start_time), 4),
        "earth_rotation_deg_s": math.degrees(EARTH_ROTATION_RATE_RAD_S),
        "satellites": satellites_data,
        "ground_stations": stations_data,
    })


@api_bp.route("/runs/<int:run_id>/passes.csv", methods=["GET"])
def run_passes_csv(run_id):
    import pandas as pd

    run = scenario_svc.get_run(db_session, run_id)
    frame = pd.DataFrame([p.to_dict() for p in run.passes])
    csv_text = frame.to_csv(index=False)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=satsim_run%d_passes.csv" % run.id
        },
    )
