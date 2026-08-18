"""Tests for the 3D visualization endpoint and page."""

import json
import math

from satsim.api.routes import ORBIT_SAMPLES
from satsim.core.elements import ClassicalElements


def _create_scenario_with_assets(client):
    """Helper: create a scenario with a satellite and ground station."""
    payload = {
        "name": "Viz test",
        "start_time": "2026-01-01T00:00:00",
        "duration_s": 3600.0,
        "time_step_s": 60.0,
    }
    resp = client.post(
        "/api/scenarios",
        data=json.dumps(payload),
        content_type="application/json",
    )
    scenario = json.loads(resp.data)
    sid = scenario["id"]

    client.post(
        "/api/scenarios/%d/satellites" % sid,
        data=json.dumps({
            "name": "SAT-1",
            "semi_major_axis_km": 7000.0,
            "inclination_deg": 53.0,
        }),
        content_type="application/json",
    )

    client.post(
        "/api/scenarios/%d/ground-stations" % sid,
        data=json.dumps({
            "name": "GS-1",
            "latitude_deg": 40.0,
            "longitude_deg": -75.0,
        }),
        content_type="application/json",
    )
    return sid


def test_visualization_api_endpoint(client):
    """The visualization API returns orbital positions and ground stations."""
    sid = _create_scenario_with_assets(client)
    resp = client.get("/api/scenarios/%d/visualization" % sid)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["scenario_id"] == sid
    assert len(data["satellites"]) == 1
    assert len(data["ground_stations"]) == 1

    sat = data["satellites"][0]
    assert sat["name"] == "SAT-1"
    assert len(sat["orbit_positions"]) == ORBIT_SAMPLES
    assert 0.0 <= sat["phase"] < 1.0
    # A 7000 km circular orbit is a ring of constant radius, expressed
    # in Earth radii for the client.
    expected = 7000.0 / 6378.137
    for point in sat["orbit_positions"]:
        radius = math.sqrt(sum(v * v for v in point))
        assert abs(radius - expected) < 1e-3
    assert abs(sat["period_s"] - 5828.5) < 1.0

    gs = data["ground_stations"][0]
    assert gs["name"] == "GS-1"
    assert gs["min_elevation_deg"] == 5.0
    # The site vector sits on the ellipsoid and its local vertical is a
    # unit vector, which is what the client needs for link geometry.
    assert abs(math.sqrt(sum(v * v for v in gs["position_ecef"])) - 1.0) < 0.01
    assert abs(math.sqrt(sum(v * v for v in gs["up_ecef"])) - 1.0) < 1e-4


def test_visualization_api_frame_metadata(client):
    """The payload carries what the client needs to spin the Earth."""
    sid = _create_scenario_with_assets(client)
    data = json.loads(client.get("/api/scenarios/%d/visualization" % sid).data)
    assert 0.0 <= data["earth_angle_deg"] < 360.0
    # One sidereal day of rotation, in degrees per second.
    assert abs(data["earth_rotation_deg_s"] - 360.0 / 86164.1) < 1e-6
    assert data["epoch_utc"].startswith("2026-01-01")


def test_orbit_samples_are_evenly_spaced_in_time(client):
    """Samples step by equal time, not equal angle.

    The client animates by walking the array at a constant rate, so on an
    eccentric orbit the samples must bunch up near apogee -- where the
    satellite is slow -- and spread out near perigee.
    """
    elements = ClassicalElements(
        semi_major_axis_km=12000.0, eccentricity=0.4, inclination_deg=20.0,
        raan_deg=0.0, arg_perigee_deg=0.0, true_anomaly_deg=0.0,
    )
    points = elements.sample_orbit_km(48)
    radii = [math.sqrt(float(sum(v * v for v in p))) for p in points]
    steps = [
        math.sqrt(float(sum((points[i + 1][k] - points[i][k]) ** 2
                            for k in range(3))))
        for i in range(len(points) - 1)
    ]
    # The step taken while near perigee is the longest one.
    perigee_step = steps[0]
    apogee_index = radii.index(max(radii))
    assert perigee_step > steps[apogee_index] * 2.0


def test_visualization_api_empty_scenario(client):
    """Visualization endpoint works for an empty scenario."""
    payload = {
        "name": "Empty",
        "start_time": "2026-01-01T00:00:00",
    }
    resp = client.post(
        "/api/scenarios",
        data=json.dumps(payload),
        content_type="application/json",
    )
    sid = json.loads(resp.data)["id"]
    resp = client.get("/api/scenarios/%d/visualization" % sid)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["satellites"] == []
    assert data["ground_stations"] == []


def test_visualization_page_renders(client):
    """The web visualization page loads successfully."""
    sid = _create_scenario_with_assets(client)
    resp = client.get("/scenarios/%d/visualization" % sid)
    assert resp.status_code == 200
    assert b"viz-container" in resp.data
    assert b"visualization.js" in resp.data
    # The page must point the renderer at the real API route.
    assert (b"/api/scenarios/%d/visualization" % sid) in resp.data


def test_visualization_page_loads_no_external_scripts(client):
    """The 3D view has to work on a machine with no internet access.

    An earlier version pulled Three.js from a CDN under a subresource
    integrity hash that never matched, so the browser blocked the script
    and the page sat on "Loading 3D scene..." forever.  Nothing on the
    page may reference an external host.
    """
    sid = _create_scenario_with_assets(client)
    page = client.get("/scenarios/%d/visualization" % sid).data.decode()
    for marker in ('src="http', "src='http", 'href="http', "href='http",
                   "integrity=", "//cdn"):
        assert marker not in page, "page references %r" % marker


def test_visualization_404_for_missing_scenario(client):
    """Requesting visualization for non-existent scenario returns 404."""
    resp = client.get("/api/scenarios/9999/visualization")
    assert resp.status_code == 404
