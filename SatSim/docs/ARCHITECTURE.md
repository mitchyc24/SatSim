# SatSim architecture

This document records the structure and the design decisions behind the
prototype so the codebase can grow without losing its shape.

## Layering

```
        ┌────────────────────────────────────────────┐
        │  web/ (dashboard)        api/ (REST JSON)  │   interface layer
        └───────────────┬────────────┬───────────────┘
                        │            │
        ┌───────────────▼────────────▼───────────────┐
        │              services/                     │   orchestration
        │   scenarios.py (CRUD + validation)         │
        │   simulation.py (simulate / run_scenario)  │
        └───────┬───────────────────────────┬────────┘
                │                           │
   ┌────────────▼─────────────┐   ┌─────────▼──────────┐
   │        core/             │   │  models.py + db.py │   engine / persistence
   │  pure astrodynamics      │   │  SQLAlchemy ORM    │
   │  (numpy/scipy/astropy)   │   │  (SQLite)          │
   └──────────────────────────┘   └────────────────────┘
```

Rules that keep the layering intact:

1. **`core` is pure.** It imports only numpy, scipy, and astropy. No Flask,
   no SQLAlchemy, no file I/O. Everything in it is callable from a script or
   notebook, which is also how the physics tests exercise it.
2. **Interfaces are thin.** Route handlers parse input, call a service, and
   render/serialize the result. Any behaviour worth testing lives below the
   route layer.
3. **Services own transactions.** They accept a session argument (the scoped
   session in production, a test session in tests), commit on success, and
   raise typed errors (`ValidationError` → 400, `NotFoundError` → 404) that
   the interface layers translate uniformly.
4. **ORM rows convert to core types at the boundary** —
   `Satellite.to_elements()`, `GroundStation.to_geometry()` — so the engine
   never sees database objects.

## Data model

- `Scenario` — epoch, duration, time step; owns satellites, stations, runs.
- `Satellite` — classical elements at the scenario epoch (+ optional
  constellation label for grouping).
- `GroundStation` — geodetic site + minimum elevation mask.
- `SimulationRun` — status, wall-clock time, viability metrics (JSON), and
  the list of plot files rendered for it.
- `PassRecord` — one contact window (satellite, station, AOS/LOS, duration,
  max elevation).

Ephemeris samples are deliberately **not** persisted: they are cheap to
recompute (seconds) and would dominate storage. Plots derived from them are
written to the Flask instance directory (`instance/plots/`) and referenced
by file name from the run row. The SQLite database lives at
`instance/satsim.db`; both are recreated on demand.

## Simulation pipeline

`services/simulation.py::simulate(scenario)` is a pure function from a
scenario definition to a `SimulationOutput`:

1. Build the time grid `0 .. duration` at `time_step` resolution.
2. Propagate each satellite's elements (RK45, two-body + J2) → ECI states.
3. Rotate positions to ECEF with astropy (one vectorized transform per
   satellite) and derive geodetic ground tracks.
4. For each station: elevation profiles per satellite → access windows
   (threshold crossings with linear interpolation) → per-station
   `CoverageReport`.
5. Union all windows into a network-level report.

`run_scenario` wraps `simulate` with persistence (run + pass records) and
plot rendering. Keeping `simulate` side-effect-free makes it directly
reusable for future features (parameter sweeps, optimization loops) and
trivially testable.

### Degradation policy

The analysis products (metrics, pass schedule, CSV export) and the
presentation artifacts (figures) fail independently. Plot rendering runs
inside `_render_plots`, which catches everything — an unimportable or
misbuilt matplotlib, an unwritable plots directory, a rendering bug — and
lets the run persist regardless. A completed simulation is never
discarded because a figure could not be drawn.

Figures themselves have two backends, tried in order:

| Backend | Module | Output | Needs |
|---|---|---|---|
| Preferred | `plotting.py` | PNG | matplotlib |
| Fallback | `plotting_svg.py` | SVG | numpy only |

Both read their palette and typography from `plot_style.py`, which
imports nothing, so the two are visually interchangeable and the fallback
stays importable in an environment where matplotlib is broken. That
happens more often than it should: a mixed 32/64-bit Anaconda install on
Windows raises `ImportError: DLL load failed while importing ft2font` the
moment matplotlib is imported. The run records which backend drew the
figures in `plots_renderer`, and keeps the matplotlib failure in
`plots_error` so the cause stays diagnosable rather than silently
papered over. Only when both backends fail does a run land without
figures.

Apply the same rule to future optional outputs: compute the analysis
first, then attempt presentation, and never let the second invalidate the
first.

## 3D view

`web/static/visualization.js` draws the scene on a plain 2-D canvas with
no third-party library. An earlier version loaded Three.js from a CDN,
which broke the view twice over: SatSim is meant to run with no network
access, and the `integrity` hash on the script tag was the SHA-384 of the
empty string, so browsers refused to execute the file even when it did
download. The page then sat on "Loading 3D scene…" forever, because
nothing surfaced the failure. Keep the view dependency-free; the
`test_visualization_page_loads_no_external_scripts` test enforces it.

The scene works from `/api/scenarios/<id>/visualization`, which returns
everything in Earth radii so the client needs no physical constants:

- Orbits are one revolution of the two-body ellipse, sampled uniformly in
  **mean** anomaly (`ClassicalElements.sample_orbit_km`). Walking the
  array at a constant rate therefore animates the orbit at the right
  speed; sampling in true anomaly would run an eccentric orbit backwards
  in feel, fast at apogee and slow at perigee.
- Ground stations carry their WGS-84 site vector and local vertical, so
  the client computes a true topocentric elevation and draws a link only
  where a real contact exists.
- `earth_angle_deg` is the ECI→ECEF rotation at the epoch, measured from
  `eci_to_ecef_km` itself rather than from a sidereal-time formula — GMST
  is reckoned from the mean equinox of date, which has precessed about a
  third of a degree away from the GCRS x-axis the propagator uses.

The view is two-body: it drifts from the J2 analysis by a few degrees
over several hours. It is a qualitative picture of the geometry, and the
run pages remain the numerical product.

## Accuracy posture

This is a **viability-analysis** tool, not an operational flight-dynamics
system. Chosen approximations, and what it would take to upgrade them:

| Aspect | Current approach | Upgrade path |
|---|---|---|
| Gravity model | Two-body + J2 secular/periodic effects via RK45 | Add higher zonals/drag/SRP terms to `propagator.acceleration_km_s2` |
| Earth orientation | astropy GCRS↔ITRS with bundled IERS tables (offline; sub-arcsecond) | Enable IERS auto-download for operational EOP accuracy |
| Rise/set times | Linear interpolation between grid samples (error ≪ time step) | Root-finding (e.g. `scipy.optimize.brentq`) on the elevation function |
| Max elevation | Highest grid sample in the window | Parabolic refinement around the peak sample |
| Time scales | Naive UTC datetimes; astropy handles UTC→TT internally | Carry leap-second-aware epochs end to end |

Guard rails: element sets are validated (perigee above 100 km, e < 0.95),
scenarios are capped at 200 satellites / 50 000 time samples, and stations
must have sane geodetic coordinates and masks.

## Extension points

The module boundaries were drawn where the next features will land:

- **New constellation patterns** → `core/constellation.py` (streets of
  coverage, flower constellations, multi-shell); the service and UI only
  need a new form/endpoint mapping.
- **New perturbations** → `core/propagator.py` acceleration function.
- **New viability metrics** (N-fold coverage, latency proxies, grid-based
  area coverage) → `core/analysis.py`; metrics flow to the UI through the
  run's JSON blob, so older runs stay readable.
- **New interfaces** (CLI batch runner, notebook helpers) → thin layers over
  `services`, like `api/` and `web/` today.
- **Background execution** — `run_scenario` is synchronous today (seconds
  for typical scenarios); if scenarios grow, it can move behind a task queue
  without changing its signature.

## Environment constraints

The application targets the pinned environment in
`Paython Environment Constraints.txt` (Python 3.9 / Flask 1.1.2 /
SQLAlchemy 1.4.22 / astropy 4.3.1 / scipy 1.7.1 / numpy 1.20.3) and is also
kept compatible with current releases of every dependency. Practical
consequences:

- Flask usage sticks to APIs stable across 1.1 → 3.x (`Blueprint`,
  `route(methods=...)`, `jsonify`; no `app.get/post` shortcuts).
- SQLAlchemy usage sticks to the 1.4/2.0 intersection
  (`sqlalchemy.orm.declarative_base`, `Session.get`, `session.query` for
  simple filters).
- astropy access is confined to `core/frames.py`, with IERS auto-download
  disabled so first use never blocks on the network.
- numpy usage avoids APIs removed in 2.0 (`np.trapz`, `np.float_`, ...).
