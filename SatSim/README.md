# SatSim

SatSim is a lightweight, web-based space mission analysis application for
**building satellite constellations and evaluating their viability** against
ground station networks. Inspired by Systems Tool Kit (STK), it is a
self-contained astrodynamics dashboard built entirely on Python's core
scientific and web ecosystem — no external services, no internet access
required at runtime.

## Capabilities

- **Orbital mechanics engine** — classical Keplerian elements
  (a, e, i, Ω, ω, ν) propagated with an adaptive Runge–Kutta 4(5) integrator
  (`scipy.integrate.solve_ivp`) including the Earth's J2 oblateness
  perturbation.
- **Constellation builder** — generate Walker delta/star patterns
  (`i: t/p/f`) in one step, or enter individual satellites element-by-element.
- **Coordinate transformations** — ECI (GCRS) ↔ ECEF (ITRS) rotations and
  WGS-84 geodetic conversions via astropy, configured to run fully offline.
- **Ground station access analysis** — topocentric azimuth/elevation/slant
  range, contact windows with interpolated rise/set times, and pass schedules.
- **Viability metrics** — per-station and network-wide coverage fraction,
  contact time, pass statistics, and revisit/outage gaps (mean and worst
  case).
- **Web dashboard & REST API** — a Flask UI for interactive studies plus a
  JSON API for scripted parameter sweeps; scenarios, runs, and passes persist
  in SQLite through SQLAlchemy.
- **Plots** — ground tracks, per-station elevation profiles, and
  simultaneous-visibility timelines rendered with matplotlib; pass schedules
  export to CSV via pandas.

## Quickstart

The pinned versions in `requirements.txt` mirror the target environment
captured in *Paython Environment Constraints.txt* (Anaconda 2021.11 /
Python 3.9) — if you are in that environment, everything is already
installed. The code also runs on current releases (validated with numpy 2.x,
scipy 1.17, astropy 8, Flask 3.1, SQLAlchemy 2.0); on a modern Python simply
install the same packages without pins.

```bash
# Start the dashboard
python run.py
# then open http://127.0.0.1:5000
```

Typical workflow:

1. **Create a scenario** — name, UTC epoch, analysis window, time step.
2. **Add assets** — generate a Walker constellation (e.g. 24/3/1 at 550 km,
   53°) and add ground stations (lat/lon/alt + minimum elevation mask).
3. **Run the simulation** — propagates every satellite, computes access
   windows for every station, stores the run.
4. **Review viability** — coverage percentage, worst outage, pass schedule,
   ground tracks, and per-station access plots; download passes as CSV.

### Headless / scripted use

The astrodynamics core is importable without the web stack:

```bash
python examples/demo.py        # Walker 24/3/1 vs. two ground sites
```

or drive the REST API:

```bash
curl -X POST http://127.0.0.1:5000/api/scenarios \
  -H "Content-Type: application/json" \
  -d '{"name": "LEO study", "start_time": "2026-01-01T00:00:00",
       "duration_s": 86400, "time_step_s": 60}'
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/scenarios` | GET/POST | List / create scenarios |
| `/api/scenarios/<id>` | GET/DELETE | Scenario detail / delete |
| `/api/scenarios/<id>/satellites` | POST | Add a satellite (elements) |
| `/api/scenarios/<id>/walker` | POST | Generate a Walker constellation |
| `/api/scenarios/<id>/ground-stations` | POST | Add a ground station |
| `/api/scenarios/<id>/run` | POST | Execute the simulation |
| `/api/runs/<id>` | GET | Run metrics + pass list |
| `/api/runs/<id>/passes.csv` | GET | Pass schedule as CSV |

## Troubleshooting

**`ImportError: DLL load failed while importing ft2font`** (Windows/Anaconda)

matplotlib's native extension cannot load — usually an architecture
mismatch or a mixed conda/pip install of matplotlib or its freetype
dependency. SatSim treats plots as optional, so simulations still run and
report full metrics and pass schedules; the results page shows a notice in
place of the figures. To restore plotting:

```bat
conda install --force-reinstall freetype matplotlib
```

If that doesn't clear it, check for a stray pip copy shadowing the conda
one (`pip uninstall matplotlib`, then reinstall via conda) and confirm the
interpreter architecture matches the packages
(`python -c "import struct; print(struct.calcsize('P') * 8)"` should print
`64` for a 64-bit Anaconda). Re-run the scenario afterwards to generate the
figures.

## Architecture

```
satsim/
├── core/          # pure astrodynamics engine (numpy/scipy/astropy only)
│   ├── elements.py        # Keplerian elements <-> state vectors, anomalies
│   ├── propagator.py      # RK45 two-body + J2 propagation
│   ├── frames.py          # ECI<->ECEF, geodetic conversions (astropy)
│   ├── stations.py        # topocentric look angles
│   ├── constellation.py   # Walker pattern generator
│   ├── access.py          # contact window extraction
│   └── analysis.py        # coverage / viability metrics
├── models.py      # SQLAlchemy ORM entities
├── db.py          # engine + scoped session wiring
├── services/      # orchestration between core and persistence
├── api/           # REST/JSON blueprint (/api)
├── web/           # server-rendered dashboard (templates + static)
└── plotting.py    # matplotlib figure generation
```

The layering is strict: `core` never imports Flask or SQLAlchemy, route
handlers never touch the physics directly, and all behaviour shared by the
API and dashboard lives in `services`. See `docs/ARCHITECTURE.md` for design
decisions, accuracy notes, and the roadmap for growing the feature set.

## Testing

```bash
python -m pytest tests/ -q
```

The suite covers the physics (element round-trips, energy conservation,
J2 nodal-regression rates against the analytic secular solution, frame
rotation rates), the geometry (access windows, coverage statistics), and the
full web/API cycle including plot generation.
