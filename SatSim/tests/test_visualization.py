"""Tests for the 3D visualization endpoint and page."""

import json


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
    assert len(sat["orbit_positions"]) == 36
    assert "period_s" in sat
    gs = data["ground_stations"][0]
    assert gs["name"] == "GS-1"


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
    assert b"3D Visualization" in resp.data
    assert b"viz-container" in resp.data
    assert b"three.min.js" in resp.data


def test_visualization_404_for_missing_scenario(client):
    """Requesting visualization for non-existent scenario returns 404."""
    resp = client.get("/api/scenarios/9999/visualization")
    assert resp.status_code == 404
