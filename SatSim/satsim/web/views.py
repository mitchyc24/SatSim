"""Dashboard routes.

Thin form handlers over :mod:`satsim.services`; validation errors are
flashed back to the referring page rather than raising.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from ..db import db_session
from ..services import scenarios as scenario_svc
from ..services.scenarios import NotFoundError, ValidationError
from ..services.simulation import run_scenario
from ..utils import format_duration, parse_utc_datetime

web_bp = Blueprint(
    "web", __name__, template_folder="templates", static_folder="static",
    static_url_path="/web-static",
)


@web_bp.app_template_filter("duration")
def _duration_filter(seconds):
    return format_duration(seconds or 0)


@web_bp.app_template_filter("pct")
def _pct_filter(fraction):
    return "%.1f%%" % (100.0 * (fraction or 0.0))


@web_bp.errorhandler(NotFoundError)
def _not_found(exc):
    return render_template("error.html", message=str(exc)), 404


def _form_float(name, default=None):
    raw = request.form.get(name, "")
    if raw in ("", None):
        if default is None:
            raise ValidationError("Field '%s' is required" % name)
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValidationError("Field '%s' must be a number" % name)


def _form_int(name, default=None):
    raw = request.form.get(name, "")
    if raw in ("", None):
        if default is None:
            raise ValidationError("Field '%s' is required" % name)
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValidationError("Field '%s' must be an integer" % name)


# ----------------------------------------------------------------------
# Scenario list / create
# ----------------------------------------------------------------------
@web_bp.route("/", methods=["GET"])
def index():
    scenarios = scenario_svc.list_scenarios(db_session)
    return render_template("index.html", scenarios=scenarios)


@web_bp.route("/scenarios", methods=["POST"])
def create_scenario():
    try:
        start_time = parse_utc_datetime(request.form.get("start_time", ""))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.index"))
    try:
        scenario = scenario_svc.create_scenario(
            db_session,
            name=request.form.get("name", ""),
            start_time=start_time,
            duration_s=_form_float("duration_hours", 24.0) * 3600.0,
            time_step_s=_form_float("time_step_s", 60.0),
            description=request.form.get("description", ""),
        )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.index"))
    flash("Scenario '%s' created." % scenario.name, "success")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


@web_bp.route("/scenarios/<int:scenario_id>/delete", methods=["POST"])
def delete_scenario(scenario_id):
    scenario_svc.delete_scenario(db_session, scenario_id)
    flash("Scenario deleted.", "success")
    return redirect(url_for("web.index"))


# ----------------------------------------------------------------------
# Scenario detail and asset management
# ----------------------------------------------------------------------
@web_bp.route("/scenarios/<int:scenario_id>", methods=["GET"])
def scenario_detail(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    return render_template("scenario.html", scenario=scenario)


@web_bp.route("/scenarios/<int:scenario_id>/satellites", methods=["POST"])
def add_satellite(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    try:
        scenario_svc.add_satellite(
            db_session,
            scenario,
            name=request.form.get("name", ""),
            semi_major_axis_km=_form_float("semi_major_axis_km"),
            eccentricity=_form_float("eccentricity", 0.0),
            inclination_deg=_form_float("inclination_deg"),
            raan_deg=_form_float("raan_deg", 0.0),
            arg_perigee_deg=_form_float("arg_perigee_deg", 0.0),
            true_anomaly_deg=_form_float("true_anomaly_deg", 0.0),
        )
        flash("Satellite added.", "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


@web_bp.route(
    "/scenarios/<int:scenario_id>/satellites/<int:satellite_id>/delete",
    methods=["POST"],
)
def delete_satellite(scenario_id, satellite_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    scenario_svc.delete_satellite(db_session, scenario, satellite_id)
    flash("Satellite removed.", "success")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


@web_bp.route("/scenarios/<int:scenario_id>/walker", methods=["POST"])
def add_walker(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    try:
        created = scenario_svc.add_walker_constellation(
            db_session,
            scenario,
            total_satellites=_form_int("total_satellites"),
            planes=_form_int("planes"),
            relative_phasing=_form_int("relative_phasing", 0),
            altitude_km=_form_float("altitude_km"),
            inclination_deg=_form_float("inclination_deg"),
            name_prefix=request.form.get("name_prefix", "SAT"),
            raan_offset_deg=_form_float("raan_offset_deg", 0.0),
            pattern=request.form.get("pattern", "delta"),
        )
        flash("Added %d Walker constellation satellites." % len(created),
              "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


@web_bp.route("/scenarios/<int:scenario_id>/ground-stations", methods=["POST"])
def add_ground_station(scenario_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    try:
        scenario_svc.add_ground_station(
            db_session,
            scenario,
            name=request.form.get("name", ""),
            latitude_deg=_form_float("latitude_deg"),
            longitude_deg=_form_float("longitude_deg"),
            altitude_m=_form_float("altitude_m", 0.0),
            min_elevation_deg=_form_float("min_elevation_deg", 5.0),
        )
        flash("Ground station added.", "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


@web_bp.route(
    "/scenarios/<int:scenario_id>/ground-stations/<int:station_id>/delete",
    methods=["POST"],
)
def delete_ground_station(scenario_id, station_id):
    scenario = scenario_svc.get_scenario(db_session, scenario_id)
    scenario_svc.delete_ground_station(db_session, scenario, station_id)
    flash("Ground station removed.", "success")
    return redirect(url_for("web.scenario_detail", scenario_id=scenario.id))


# ----------------------------------------------------------------------
# Simulation runs
# ----------------------------------------------------------------------
@web_bp.route("/scenarios/<int:scenario_id>/run", methods=["POST"])
def run_simulation(scenario_id):
    try:
        run = run_scenario(
            db_session, scenario_id, plots_dir=current_app.config["PLOTS_DIR"]
        )
    except ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.scenario_detail", scenario_id=scenario_id))
    flash("Simulation completed in %.1f s." % (run.elapsed_s or 0.0), "success")
    plots_error = run.metrics.get("plots_error")
    if plots_error:
        flash(
            "Metrics and pass schedule were saved, but plot rendering failed "
            "(%s). Check the matplotlib install; the analysis results below "
            "are unaffected." % plots_error,
            "warning",
        )
    return redirect(url_for("web.run_detail", run_id=run.id))


@web_bp.route("/runs/<int:run_id>", methods=["GET"])
def run_detail(run_id):
    run = scenario_svc.get_run(db_session, run_id)
    metrics = run.metrics
    return render_template(
        "run.html",
        run=run,
        scenario=run.scenario,
        metrics=metrics,
        network=metrics.get("network") or {},
        stations=metrics.get("stations") or {},
    )


@web_bp.route("/plots/<path:filename>", methods=["GET"])
def plot_file(filename):
    return send_from_directory(current_app.config["PLOTS_DIR"], filename)
