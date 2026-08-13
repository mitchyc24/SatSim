"""End-to-end tests through the REST API and web dashboard.

A small scenario (short window, coarse step, few satellites) keeps the
full simulate-persist-plot cycle fast enough for CI.
"""

import json


def _create_scenario(client, **overrides):
    payload = {
        "name": "API test scenario",
        "start_time": "2026-01-01T00:00:00",
        "duration_s": 7200.0,
        "time_step_s": 120.0,
    }
    payload.update(overrides)
    response = client.post(
        "/api/scenarios",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 201, response.data
    return json.loads(response.data)


def _post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload),
                       content_type="application/json")


def test_scenario_crud(client):
    scenario = _create_scenario(client)
    assert scenario["name"] == "API test scenario"

    listing = json.loads(client.get("/api/scenarios").data)
    assert len(listing["scenarios"]) == 1

    detail = json.loads(
        client.get("/api/scenarios/%d" % scenario["id"]).data
    )
    assert detail["satellites"] == []
    assert detail["ground_stations"] == []

    assert client.delete("/api/scenarios/%d" % scenario["id"]).status_code == 200
    assert client.get("/api/scenarios/%d" % scenario["id"]).status_code == 404


def test_scenario_validation_errors(client):
    response = _post_json(client, "/api/scenarios", {"name": "x"})
    assert response.status_code == 400
    assert "start_time" in json.loads(response.data)["error"]

    response = _post_json(client, "/api/scenarios", {
        "name": "x", "start_time": "2026-01-01T00:00:00",
        "duration_s": -5,
    })
    assert response.status_code == 400

    # Sample-count guard
    response = _post_json(client, "/api/scenarios", {
        "name": "x", "start_time": "2026-01-01T00:00:00",
        "duration_s": 86400.0 * 10, "time_step_s": 1.0,
    })
    assert response.status_code == 400


def test_satellite_and_station_endpoints(client):
    scenario = _create_scenario(client)
    base = "/api/scenarios/%d" % scenario["id"]

    response = _post_json(client, base + "/satellites", {
        "name": "ISS-like", "semi_major_axis_km": 6798.0,
        "inclination_deg": 51.6, "eccentricity": 0.0005,
    })
    assert response.status_code == 201
    sat = json.loads(response.data)

    # Invalid elements are rejected with a helpful message
    response = _post_json(client, base + "/satellites", {
        "name": "bad", "semi_major_axis_km": 6400.0, "inclination_deg": 0.0,
    })
    assert response.status_code == 400
    assert "erigee" in json.loads(response.data)["error"]

    response = _post_json(client, base + "/ground-stations", {
        "name": "Ottawa", "latitude_deg": 45.42, "longitude_deg": -75.70,
    })
    assert response.status_code == 201

    response = _post_json(client, base + "/ground-stations", {
        "name": "bad", "latitude_deg": 95.0, "longitude_deg": 0.0,
    })
    assert response.status_code == 400

    assert client.delete(
        base + "/satellites/%d" % sat["id"]
    ).status_code == 200
    assert client.delete(
        base + "/satellites/%d" % sat["id"]
    ).status_code == 404


def test_walker_endpoint(client):
    scenario = _create_scenario(client)
    response = _post_json(
        client, "/api/scenarios/%d/walker" % scenario["id"], {
            "total_satellites": 6, "planes": 3, "relative_phasing": 1,
            "altitude_km": 550.0, "inclination_deg": 53.0,
            "name_prefix": "W",
        },
    )
    assert response.status_code == 201
    body = json.loads(response.data)
    assert body["created"] == 6
    assert body["satellites"][0]["name"] == "W-101"

    response = _post_json(
        client, "/api/scenarios/%d/walker" % scenario["id"], {
            "total_satellites": 7, "planes": 3, "relative_phasing": 0,
            "altitude_km": 550.0, "inclination_deg": 53.0,
        },
    )
    assert response.status_code == 400


def test_full_simulation_cycle(client):
    scenario = _create_scenario(client)
    base = "/api/scenarios/%d" % scenario["id"]
    _post_json(client, base + "/walker", {
        "total_satellites": 4, "planes": 2, "relative_phasing": 1,
        "altitude_km": 550.0, "inclination_deg": 53.0,
    })
    _post_json(client, base + "/ground-stations", {
        "name": "Ottawa", "latitude_deg": 45.42, "longitude_deg": -75.70,
        "min_elevation_deg": 5.0,
    })

    response = client.post(base + "/run")
    assert response.status_code == 201, response.data
    run = json.loads(response.data)
    assert run["status"] == "completed"

    metrics = run["metrics"]
    assert metrics["num_satellites"] == 4
    assert metrics["num_stations"] == 1
    assert "Ottawa" in metrics["stations"]
    station = metrics["stations"]["Ottawa"]
    assert 0.0 <= station["coverage_fraction"] <= 1.0

    detail = json.loads(client.get("/api/runs/%d" % run["id"]).data)
    assert detail["num_passes"] == len(detail["passes"])
    for record in detail["passes"]:
        assert record["duration_s"] > 0
        assert record["max_elevation_deg"] >= 5.0

    csv_response = client.get("/api/runs/%d/passes.csv" % run["id"])
    assert csv_response.status_code == 200
    assert csv_response.mimetype == "text/csv"

    # Run without stations is a clean 400, not a crash
    empty = _create_scenario(client, name="empty")
    response = client.post("/api/scenarios/%d/run" % empty["id"])
    assert response.status_code == 400


def test_web_pages_render(client, app):
    # Index
    response = client.get("/")
    assert response.status_code == 200
    assert b"SatSim" in response.data

    # Create scenario through the form
    response = client.post("/scenarios", data={
        "name": "Web scenario",
        "start_time": "2026-01-01T00:00",
        "duration_hours": "2",
        "time_step_s": "120",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Web scenario" in response.data

    scenario_id = json.loads(
        client.get("/api/scenarios").data
    )["scenarios"][0]["id"]

    # Add assets via forms
    response = client.post(
        "/scenarios/%d/walker" % scenario_id,
        data={
            "total_satellites": "4", "planes": "2", "relative_phasing": "1",
            "altitude_km": "550", "inclination_deg": "53",
            "name_prefix": "W", "raan_offset_deg": "0", "pattern": "delta",
        },
        follow_redirects=True,
    )
    assert b"W-101" in response.data

    response = client.post(
        "/scenarios/%d/ground-stations" % scenario_id,
        data={
            "name": "Ottawa", "latitude_deg": "45.42",
            "longitude_deg": "-75.70", "altitude_m": "70",
            "min_elevation_deg": "5",
        },
        follow_redirects=True,
    )
    assert b"Ottawa" in response.data

    # Run and view results (also exercises plot generation)
    response = client.post(
        "/scenarios/%d/run" % scenario_id, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Station viability" in response.data
    assert b"ground_track" in response.data

    # Plot files are served
    run = json.loads(client.get("/api/scenarios/%d" % scenario_id).data)
    run_id = run["runs"][0]["id"]
    page = client.get("/runs/%d" % run_id)
    assert page.status_code == 200
    plot_response = client.get(
        "/plots/run%d_ground_track.png" % run_id
    )
    assert plot_response.status_code == 200
    assert plot_response.data[:8] == b"\x89PNG\r\n\x1a\n"

    # Unknown scenario renders the error page
    assert client.get("/scenarios/9999").status_code == 404
