/**
 * SatSim 3D scene: an inertial orbit view drawn on a 2-D canvas.
 *
 * Deliberately dependency-free.  SatSim is designed to run fully
 * offline, so pulling a WebGL library off a CDN made the view fail
 * closed -- a blocked script left the page stuck on "Loading 3D
 * scene..." with nothing to explain why.  Everything here is a few
 * hundred lines of vector maths against the browser's own canvas.
 *
 * Frames follow the API payload (see /api/scenarios/<id>/visualization):
 * orbits are inertial (ECI) and fixed, while the globe, its graticule
 * and the ground stations are Earth-fixed (ECEF) and spun into ECI by
 * earth_angle_deg + omega * t.  Distances are Earth radii.
 * Links are drawn from real topocentric elevation against each site's
 * own mask, so a drawn line means an actual contact.
 */
var SatSimViz = (function () {
  "use strict";

  var DEG = Math.PI / 180;
  var WORLD_UP = [0, 0, 1];
  var MAX_ELEVATION = 1.45;     // radians; keeps the camera off the poles
  var MIN_DISTANCE = 1.25;
  var MAX_DISTANCE = 24.0;
  var FOV = 45 * DEG;

  var COLOR = {
    space: "#05070d",
    globe: "#1d3f8f",
    globeLit: "#3f6fd0",
    globeEdge: "#6f9be8",
    graticule: "rgba(140, 190, 255, 0.30)",
    equator: "rgba(180, 220, 255, 0.55)",
    orbit: "#00ccff",
    satellite: "#7fe6ff",
    station: "#ff4444",
    link: "#ffcc00",
    label: "#dbe6f5"
  };

  var container, canvas, ctx, overlay, readout;
  var view = { width: 0, height: 0, dpr: 1 };
  var scene = null;
  var graticule = buildGraticule();
  var camera = { azimuth: -1.1, elevation: 0.5, distance: 4.2 };
  var frameState = { eye: [0, 0, 0], right: [1, 0, 0], up: [0, 1, 0],
                     forward: [0, 0, 1], focal: 1, cx: 0, cy: 0, radius: 0 };
  var options = { orbits: true, links: true, timeScale: 280, paused: false };
  var simTime = 0;          // seconds since the scenario epoch
  var lastTimestamp = 0;
  var lastReadout = 0;
  var animationHandle = null;

  // ------------------------------------------------------------------
  // Set-up
  // ------------------------------------------------------------------
  function init(containerId, dataUrl) {
    container = document.getElementById(containerId);
    if (!container) return;
    overlay = document.getElementById("viz-loading");
    readout = document.getElementById("viz-readout");

    canvas = document.createElement("canvas");
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.touchAction = "none";
    container.insertBefore(canvas, container.firstChild);

    ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) {
      fail("This browser cannot draw on a 2-D canvas, so the 3D view is " +
           "unavailable. The scenario and run pages are unaffected.");
      return;
    }

    bindControls();
    bindPointer();
    window.addEventListener("resize", resize);
    resize();

    load(dataUrl);
  }

  function load(dataUrl) {
    status("Loading scene data…");
    fetch(dataUrl, { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("scene data request failed (HTTP " +
                          response.status + ")");
        }
        return response.json();
      })
      .then(function (data) {
        scene = buildScene(data);
        hideOverlay();
        start();
      })
      .catch(function (error) {
        fail("Could not load the scene: " + error.message);
      });
  }

  function buildScene(data) {
    var satellites = (data.satellites || []).map(function (sat) {
      return {
        name: sat.name,
        positions: sat.orbit_positions || [],
        phase: sat.phase || 0,
        period_s: sat.period_s || 5400,
        position: [0, 0, 0]
      };
    });
    var stations = (data.ground_stations || []).map(function (gs) {
      var ecef = gs.position_ecef || [0, 0, 0];
      // The globe is drawn as a sphere of one equatorial radius, but the
      // Earth is oblate: a real WGS-84 site is up to 21 km inside that
      // sphere and would be buried by it.  Markers therefore ride a
      // separate vector lifted just clear of the surface, while the
      // link geometry keeps using the true site position.
      return {
        name: gs.name,
        ecef: ecef,
        marker: scaleTo(ecef, 1.004),
        up: gs.up_ecef || [0, 0, 1],
        minElevation: gs.min_elevation_deg || 0,
        position: [0, 0, 0],
        markerPosition: [0, 0, 0],
        up_eci: [0, 0, 1],
        contacts: 0
      };
    });
    return {
      name: data.scenario_name || "",
      epoch: data.epoch_utc ? new Date(data.epoch_utc + "Z") : null,
      earthAngle: (data.earth_angle_deg || 0) * DEG,
      spinRate: (data.earth_rotation_deg_s || 0) * DEG,
      satellites: satellites,
      stations: stations
    };
  }

  function start() {
    if (animationHandle === null) {
      lastTimestamp = 0;
      animationHandle = window.requestAnimationFrame(frame);
    }
  }

  // ------------------------------------------------------------------
  // Animation
  // ------------------------------------------------------------------
  function frame(timestamp) {
    animationHandle = window.requestAnimationFrame(frame);
    var delta = lastTimestamp ? (timestamp - lastTimestamp) / 1000.0 : 0;
    lastTimestamp = timestamp;
    // A long stall (background tab) must not teleport the scene.
    if (delta > 0.25) delta = 0.25;
    if (!options.paused) simTime += delta * options.timeScale;

    advance(simTime);
    draw();
    if (timestamp - lastReadout > 200) {
      updateReadout();
      lastReadout = timestamp;
    }
  }

  /** Place every satellite and Earth-fixed asset at ``time`` seconds. */
  function advance(time) {
    var angle = scene.earthAngle + scene.spinRate * time;
    var cos = Math.cos(angle);
    var sin = Math.sin(angle);

    scene.satellites.forEach(function (sat) {
      var count = sat.positions.length;
      if (!count) return;
      // The samples are evenly spaced in time, so a constant step
      // through them traces the orbit at the right speed.
      var exact = (sat.phase + time / sat.period_s) * count;
      var index = ((Math.floor(exact) % count) + count) % count;
      var next = (index + 1) % count;
      var fraction = exact - Math.floor(exact);
      var a = sat.positions[index];
      var b = sat.positions[next];
      sat.position[0] = a[0] + (b[0] - a[0]) * fraction;
      sat.position[1] = a[1] + (b[1] - a[1]) * fraction;
      sat.position[2] = a[2] + (b[2] - a[2]) * fraction;
    });

    scene.stations.forEach(function (station) {
      spin(station.ecef, cos, sin, station.position);
      spin(station.marker, cos, sin, station.markerPosition);
      spin(station.up, cos, sin, station.up_eci);
      // Counted here rather than while drawing, so the readout reports
      // the geometry even when links are toggled off.
      station.contacts = scene.satellites.filter(function (sat) {
        return sat.positions.length &&
               elevationDeg(station, sat.position) >= station.minElevation;
      }).length;
    });
    scene.earthSpin = angle;
  }

  /** Rotate an Earth-fixed vector into ECI about the spin axis. */
  function spin(vector, cos, sin, out) {
    out[0] = vector[0] * cos - vector[1] * sin;
    out[1] = vector[0] * sin + vector[1] * cos;
    out[2] = vector[2];
    return out;
  }

  // ------------------------------------------------------------------
  // Camera and projection (the usual look-at construction)
  // ------------------------------------------------------------------
  function updateCamera() {
    var ce = Math.cos(camera.elevation);
    var se = Math.sin(camera.elevation);
    var ca = Math.cos(camera.azimuth);
    var sa = Math.sin(camera.azimuth);
    var eye = [camera.distance * ce * ca,
               camera.distance * ce * sa,
               camera.distance * se];

    var forward = normalize([-eye[0], -eye[1], -eye[2]]);
    var right = normalize(cross(forward, WORLD_UP));
    var up = cross(right, forward);

    frameState.eye = eye;
    frameState.forward = forward;
    frameState.right = right;
    frameState.up = up;
    frameState.focal = (view.height / 2) / Math.tan(FOV / 2);
    frameState.cx = view.width / 2;
    frameState.cy = view.height / 2;
    // Apparent radius of a unit sphere seen from ``distance``.
    frameState.radius =
      frameState.focal / Math.sqrt(camera.distance * camera.distance - 1);
  }

  /** Project an ECI point; returns null when it is behind the camera. */
  function project(point) {
    var dx = point[0] - frameState.eye[0];
    var dy = point[1] - frameState.eye[1];
    var dz = point[2] - frameState.eye[2];
    var depth = dx * frameState.forward[0] + dy * frameState.forward[1] +
                dz * frameState.forward[2];
    if (depth <= 0.01) return null;
    var scale = frameState.focal / depth;
    return {
      x: frameState.cx + (dx * frameState.right[0] + dy * frameState.right[1] +
                          dz * frameState.right[2]) * scale,
      y: frameState.cy - (dx * frameState.up[0] + dy * frameState.up[1] +
                          dz * frameState.up[2]) * scale,
      depth: depth
    };
  }

  /** True when the Earth sits between the camera and ``point``. */
  function hidden(point) {
    var eye = frameState.eye;
    var dx = point[0] - eye[0];
    var dy = point[1] - eye[1];
    var dz = point[2] - eye[2];
    var a = dx * dx + dy * dy + dz * dz;
    var b = 2 * (eye[0] * dx + eye[1] * dy + eye[2] * dz);
    var c = eye[0] * eye[0] + eye[1] * eye[1] + eye[2] * eye[2] - 1;
    var discriminant = b * b - 4 * a * c;
    if (discriminant <= 0) return false;
    var root = Math.sqrt(discriminant);
    // The tolerance keeps a point resting on the surface from being
    // occluded by the surface it sits on.
    var entry = (-b - root) / (2 * a);
    return entry > 1e-6 && entry < 1 - 1e-4;
  }

  // ------------------------------------------------------------------
  // Drawing
  // ------------------------------------------------------------------
  function draw() {
    updateCamera();
    ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
    ctx.fillStyle = COLOR.space;
    ctx.fillRect(0, 0, view.width, view.height);

    // Far side first, dimmed, then the globe over it, then the near
    // side: a painter's ordering that keeps the far half legible
    // without letting it read as being in front.
    drawOrbits(true);
    drawLinks(true);
    drawGlobe();
    drawGraticule();
    drawOrbits(false);
    drawLinks(false);
    drawStations();
    drawSatellites();
  }

  function drawGlobe() {
    var gradient = ctx.createRadialGradient(
      frameState.cx - frameState.radius * 0.35,
      frameState.cy - frameState.radius * 0.35,
      frameState.radius * 0.1,
      frameState.cx, frameState.cy, frameState.radius
    );
    gradient.addColorStop(0, COLOR.globeLit);
    gradient.addColorStop(1, COLOR.globe);

    ctx.beginPath();
    ctx.arc(frameState.cx, frameState.cy, frameState.radius, 0, Math.PI * 2);
    ctx.fillStyle = gradient;
    ctx.globalAlpha = 0.94;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = COLOR.globeEdge;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  function drawGraticule() {
    var cos = Math.cos(scene.earthSpin);
    var sin = Math.sin(scene.earthSpin);
    var point = [0, 0, 0];
    graticule.forEach(function (line) {
      ctx.beginPath();
      ctx.strokeStyle = line.equator ? COLOR.equator : COLOR.graticule;
      ctx.lineWidth = line.equator ? 1.2 : 0.8;
      var pen = false;
      line.points.forEach(function (vertex) {
        spin(vertex, cos, sin, point);
        var screen = hidden(point) ? null : project(point);
        if (!screen) { pen = false; return; }
        if (pen) ctx.lineTo(screen.x, screen.y);
        else ctx.moveTo(screen.x, screen.y);
        pen = true;
      });
      ctx.stroke();
    });
  }

  function drawOrbits(farSide) {
    if (!options.orbits) return;
    ctx.strokeStyle = COLOR.orbit;
    ctx.lineWidth = farSide ? 0.8 : 1.2;
    ctx.globalAlpha = farSide ? 0.18 : 0.5;
    scene.satellites.forEach(function (sat) {
      if (sat.positions.length < 2) return;
      ctx.beginPath();
      var pen = false;
      for (var i = 0; i <= sat.positions.length; i += 1) {
        var vertex = sat.positions[i % sat.positions.length];
        var screen = (hidden(vertex) === farSide) ? project(vertex) : null;
        if (!screen) { pen = false; continue; }
        if (pen) ctx.lineTo(screen.x, screen.y);
        else ctx.moveTo(screen.x, screen.y);
        pen = true;
      }
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  function drawSatellites() {
    scene.satellites.forEach(function (sat) {
      if (!sat.positions.length) return;
      var behind = hidden(sat.position);
      var screen = project(sat.position);
      if (!screen) return;
      var radius = Math.max(1.8, 3.6 * (camera.distance / screen.depth));
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = COLOR.satellite;
      ctx.globalAlpha = behind ? 0.25 : 1;
      ctx.fill();
      ctx.globalAlpha = 1;
    });
  }

  function drawStations() {
    scene.stations.forEach(function (station) {
      var behind = hidden(station.markerPosition);
      var screen = project(station.markerPosition);
      if (!screen) return;
      ctx.globalAlpha = behind ? 0.2 : 1;
      ctx.beginPath();
      ctx.arc(screen.x, screen.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = COLOR.station;
      ctx.fill();
      if (!behind) {
        ctx.fillStyle = COLOR.label;
        ctx.font = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(station.name, screen.x, screen.y - 9);
      }
      ctx.globalAlpha = 1;
    });
  }

  function drawLinks(farSide) {
    if (!options.links) return;
    ctx.strokeStyle = COLOR.link;
    ctx.lineWidth = farSide ? 0.8 : 1.4;
    ctx.globalAlpha = farSide ? 0.15 : 0.75;
    scene.stations.forEach(function (station) {
      scene.satellites.forEach(function (sat) {
        if (!sat.positions.length) return;
        if (elevationDeg(station, sat.position) < station.minElevation) return;
        var midpoint = [
          (station.markerPosition[0] + sat.position[0]) / 2,
          (station.markerPosition[1] + sat.position[1]) / 2,
          (station.markerPosition[2] + sat.position[2]) / 2
        ];
        if (hidden(midpoint) !== farSide) return;
        var from = project(station.markerPosition);
        var to = project(sat.position);
        if (!from || !to) return;
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.stroke();
      });
    });
    ctx.globalAlpha = 1;
  }

  /** Topocentric elevation of an ECI point above a station, in degrees. */
  function elevationDeg(station, point) {
    var dx = point[0] - station.position[0];
    var dy = point[1] - station.position[1];
    var dz = point[2] - station.position[2];
    var range = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (range === 0) return 90;
    var projected = (dx * station.up_eci[0] + dy * station.up_eci[1] +
                     dz * station.up_eci[2]) / range;
    return Math.asin(Math.max(-1, Math.min(1, projected))) / DEG;
  }

  // ------------------------------------------------------------------
  // Interaction and chrome
  // ------------------------------------------------------------------
  function bindPointer() {
    var dragging = false;
    var last = { x: 0, y: 0 };

    canvas.addEventListener("pointerdown", function (event) {
      dragging = true;
      last = { x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      camera.azimuth -= (event.clientX - last.x) * 0.006;
      camera.elevation += (event.clientY - last.y) * 0.006;
      camera.elevation = clamp(camera.elevation, -MAX_ELEVATION, MAX_ELEVATION);
      last = { x: event.clientX, y: event.clientY };
    });
    function release(event) {
      if (!dragging) return;
      dragging = false;
      if (canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
      }
    }
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);

    canvas.addEventListener("wheel", function (event) {
      event.preventDefault();
      camera.distance = clamp(camera.distance * Math.exp(event.deltaY * 0.001),
                              MIN_DISTANCE, MAX_DISTANCE);
    }, { passive: false });
  }

  function bindControls() {
    on("chk-orbits", "change", function () { options.orbits = this.checked; });
    on("chk-links", "change", function () { options.links = this.checked; });
    on("speed-slider", "input", function () { setTimeScale(this.value); });
    on("btn-pause", "click", function () {
      options.paused = !options.paused;
      this.textContent = options.paused ? "Resume" : "Pause";
    });
    on("btn-reset", "click", function () {
      camera = { azimuth: -1.1, elevation: 0.5, distance: 4.2 };
      simTime = 0;
    });
    var slider = document.getElementById("speed-slider");
    if (slider) setTimeScale(slider.value);
  }

  function on(id, event, handler) {
    var element = document.getElementById(id);
    if (element) element.addEventListener(event, handler);
  }

  /** Slider position (0-100) to a real-time multiplier, log-spaced.
   *
   * The top of the range is bounded at ~3000x deliberately: one orbit
   * sample is roughly 80 s of flight time for a LEO satellite, so a
   * faster clock would step over samples between frames and alias the
   * motion instead of animating it.
   */
  function setTimeScale(value) {
    options.timeScale = Math.round(Math.pow(10, (Number(value) / 100) * 3.5));
    var label = document.getElementById("speed-value");
    if (label) label.textContent = options.timeScale + "× real time";
  }

  function updateReadout() {
    if (!readout) return;
    var contacts = scene.stations.reduce(function (total, station) {
      return total + station.contacts;
    }, 0);
    var clock = scene.epoch
      ? new Date(scene.epoch.getTime() + simTime * 1000)
          .toISOString().replace("T", " ").slice(0, 19) + " UTC"
      : formatElapsed(simTime);
    readout.textContent = clock + "  ·  T+" + formatElapsed(simTime) +
      "  ·  " + scene.satellites.length + " satellites  ·  " +
      contacts + " active link" + (contacts === 1 ? "" : "s");
  }

  function formatElapsed(seconds) {
    var whole = Math.max(0, Math.floor(seconds));
    var days = Math.floor(whole / 86400);
    var hours = Math.floor((whole % 86400) / 3600);
    var minutes = Math.floor((whole % 3600) / 60);
    return (days ? days + "d " : "") + pad(hours) + "h " + pad(minutes) + "m";
  }

  function pad(value) {
    return (value < 10 ? "0" : "") + value;
  }

  function resize() {
    if (!container || !canvas) return;
    view.dpr = window.devicePixelRatio || 1;
    view.width = container.clientWidth;
    view.height = container.clientHeight;
    canvas.width = Math.max(1, Math.round(view.width * view.dpr));
    canvas.height = Math.max(1, Math.round(view.height * view.dpr));
  }

  function status(message) {
    if (overlay) {
      overlay.textContent = message;
      overlay.style.display = "";
    }
  }

  function hideOverlay() {
    if (overlay) overlay.style.display = "none";
  }

  function fail(message) {
    status(message);
    if (overlay) overlay.className = "viz-error";
    if (window.console) window.console.error("SatSimViz: " + message);
  }

  // ------------------------------------------------------------------
  // Geometry helpers
  // ------------------------------------------------------------------
  function buildGraticule() {
    var lines = [];
    var step = 4 * DEG;
    var latitude, longitude, angle, points;

    for (latitude = -60; latitude <= 60; latitude += 30) {
      points = [];
      var lat = latitude * DEG;
      for (angle = 0; angle <= Math.PI * 2 + 1e-9; angle += step) {
        points.push([Math.cos(lat) * Math.cos(angle),
                     Math.cos(lat) * Math.sin(angle),
                     Math.sin(lat)]);
      }
      lines.push({ points: points, equator: latitude === 0 });
    }

    for (longitude = -180; longitude < 180; longitude += 30) {
      points = [];
      var lon = longitude * DEG;
      for (angle = -Math.PI / 2; angle <= Math.PI / 2 + 1e-9; angle += step) {
        points.push([Math.cos(angle) * Math.cos(lon),
                     Math.cos(angle) * Math.sin(lon),
                     Math.sin(angle)]);
      }
      lines.push({ points: points, equator: false });
    }
    return lines;
  }

  function cross(a, b) {
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]];
  }

  /** Rescale a vector to a given length. */
  function scaleTo(v, length) {
    var unit = normalize(v);
    return [unit[0] * length, unit[1] * length, unit[2] * length];
  }

  function normalize(v) {
    var length = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) || 1;
    return [v[0] / length, v[1] / length, v[2] / length];
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  return { init: init };
})();
