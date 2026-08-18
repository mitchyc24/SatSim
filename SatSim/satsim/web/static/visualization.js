/**
 * SatSim 3D Visualization Module
 *
 * Uses Three.js to render an Earth globe with satellite orbits and
 * ground station markers.  Data is fetched from the API visualization
 * endpoint for the given scenario.
 */
/* global THREE */
var SatSimViz = (function () {
  "use strict";

  var scene, camera, renderer, earth, controls;
  var satellites = [];
  var groundStations = [];
  var orbitLines = [];
  var linkLines = [];
  var animationTime = 0;
  var speedFactor = 1.0;
  var showOrbits = true;
  var showLinks = true;
  var container;

  function init(containerId, scenarioId) {
    container = document.getElementById(containerId);
    if (!container) return;

    // Scene setup
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    camera.position.set(0, 0, 4);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Lighting
    var ambientLight = new THREE.AmbientLight(0x404040, 1.5);
    scene.add(ambientLight);
    var directionalLight = new THREE.DirectionalLight(0xffffff, 1.0);
    directionalLight.position.set(5, 3, 5);
    scene.add(directionalLight);

    // Earth sphere
    var earthGeometry = new THREE.SphereGeometry(1, 64, 64);
    var earthMaterial = new THREE.MeshPhongMaterial({
      color: 0x2233aa,
      emissive: 0x112244,
      specular: 0x333333,
      shininess: 25,
      wireframe: false,
    });
    earth = new THREE.Mesh(earthGeometry, earthMaterial);
    scene.add(earth);

    // Wireframe overlay for continents feel
    var wireGeometry = new THREE.SphereGeometry(1.002, 32, 32);
    var wireMaterial = new THREE.MeshBasicMaterial({
      color: 0x44cc88,
      wireframe: true,
      transparent: true,
      opacity: 0.15,
    });
    var wireframe = new THREE.Mesh(wireGeometry, wireMaterial);
    scene.add(wireframe);

    // Simple mouse orbit controls (manual implementation)
    addMouseControls();

    // UI controls
    var chkOrbits = document.getElementById("chk-orbits");
    var chkLinks = document.getElementById("chk-links");
    var speedSlider = document.getElementById("speed-slider");

    if (chkOrbits) {
      chkOrbits.addEventListener("change", function () {
        showOrbits = this.checked;
        orbitLines.forEach(function (l) {
          l.visible = showOrbits;
        });
      });
    }
    if (chkLinks) {
      chkLinks.addEventListener("change", function () {
        showLinks = this.checked;
        linkLines.forEach(function (l) {
          l.visible = showLinks;
        });
      });
    }
    if (speedSlider) {
      speedSlider.addEventListener("input", function () {
        speedFactor = this.value / 50.0;
      });
    }

    // Fetch visualization data
    fetch("/api/scenarios/" + scenarioId + "/visualization")
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        buildScene(data);
        var loading = document.getElementById("viz-loading");
        if (loading) loading.style.display = "none";
      })
      .catch(function (err) {
        var loading = document.getElementById("viz-loading");
        if (loading) loading.textContent = "Error loading data.";
        console.error("SatSimViz fetch error:", err);
      });

    // Handle resize
    window.addEventListener("resize", onResize);
    animate();
  }

  function buildScene(data) {
    // Add satellite orbits
    data.satellites.forEach(function (sat) {
      var points = sat.orbit_positions.map(function (p) {
        return new THREE.Vector3(p[0], p[2], -p[1]);
      });
      // Close the loop
      if (points.length > 0) {
        points.push(points[0].clone());
      }

      var orbitGeometry = new THREE.BufferGeometry().setFromPoints(points);
      var orbitMaterial = new THREE.LineBasicMaterial({
        color: 0x00ccff,
        transparent: true,
        opacity: 0.5,
      });
      var orbitLine = new THREE.Line(orbitGeometry, orbitMaterial);
      orbitLine.visible = showOrbits;
      scene.add(orbitLine);
      orbitLines.push(orbitLine);

      // Satellite marker (small sphere at first position)
      var satGeometry = new THREE.SphereGeometry(0.02, 8, 8);
      var satMaterial = new THREE.MeshBasicMaterial({ color: 0x00ccff });
      var satMesh = new THREE.Mesh(satGeometry, satMaterial);
      if (points.length > 0) {
        satMesh.position.copy(points[0]);
      }
      scene.add(satMesh);
      satellites.push({
        mesh: satMesh,
        positions: points.slice(0, -1),
        period_s: sat.period_s,
        name: sat.name,
      });
    });

    // Add ground stations
    data.ground_stations.forEach(function (gs) {
      var pos = latLonToVector3(gs.latitude_deg, gs.longitude_deg, 1.01);
      var gsGeometry = new THREE.SphereGeometry(0.025, 8, 8);
      var gsMaterial = new THREE.MeshBasicMaterial({ color: 0xff4444 });
      var gsMesh = new THREE.Mesh(gsGeometry, gsMaterial);
      gsMesh.position.copy(pos);
      scene.add(gsMesh);
      groundStations.push({ mesh: gsMesh, name: gs.name, position: pos });
    });

    // Create link lines (one per ground station, toggled during animation)
    groundStations.forEach(function () {
      var linkGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 0, 0),
      ]);
      var linkMaterial = new THREE.LineBasicMaterial({
        color: 0xffcc00,
        transparent: true,
        opacity: 0.7,
      });
      var linkLine = new THREE.Line(linkGeometry, linkMaterial);
      linkLine.visible = false;
      scene.add(linkLine);
      linkLines.push(linkLine);
    });
  }

  function latLonToVector3(lat, lon, radius) {
    var phi = ((90 - lat) * Math.PI) / 180;
    var theta = ((lon + 180) * Math.PI) / 180;
    return new THREE.Vector3(
      -(radius * Math.sin(phi) * Math.cos(theta)),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta)
    );
  }

  var lastTimestamp = 0;

  function animate(timestamp) {
    requestAnimationFrame(animate);
    var delta = lastTimestamp ? (timestamp - lastTimestamp) / 1000.0 : 0.016;
    lastTimestamp = timestamp;
    animationTime += delta * speedFactor;

    // Animate satellite positions along orbits
    satellites.forEach(function (sat) {
      if (sat.positions.length === 0) return;
      var t =
        ((animationTime * 10) / (sat.period_s / 100)) % sat.positions.length;
      var idx = Math.floor(t);
      var frac = t - idx;
      var nextIdx = (idx + 1) % sat.positions.length;
      sat.mesh.position.lerpVectors(
        sat.positions[idx],
        sat.positions[nextIdx],
        frac
      );
    });

    // Update link lines (show link to nearest visible satellite)
    groundStations.forEach(function (gs, gsIdx) {
      if (!showLinks || satellites.length === 0) {
        linkLines[gsIdx].visible = false;
        return;
      }
      var closest = null;
      var closestDist = Infinity;
      satellites.forEach(function (sat) {
        var d = sat.mesh.position.distanceTo(gs.position);
        if (d < closestDist) {
          closestDist = d;
          closest = sat;
        }
      });
      // Only show link if satellite is within reasonable range
      if (closest && closestDist < 2.0) {
        var positions = linkLines[gsIdx].geometry.attributes.position;
        positions.setXYZ(0, gs.position.x, gs.position.y, gs.position.z);
        positions.setXYZ(
          1,
          closest.mesh.position.x,
          closest.mesh.position.y,
          closest.mesh.position.z
        );
        positions.needsUpdate = true;
        linkLines[gsIdx].visible = true;
      } else {
        linkLines[gsIdx].visible = false;
      }
    });

    // Slowly rotate Earth
    earth.rotation.y += 0.001 * speedFactor;

    renderer.render(scene, camera);
  }

  function onResize() {
    if (!container) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  }

  function addMouseControls() {
    var isDragging = false;
    var previousMousePosition = { x: 0, y: 0 };
    var spherical = { theta: 0, phi: Math.PI / 2 };
    var radius = 4;

    container.addEventListener("mousedown", function (e) {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    container.addEventListener("mousemove", function (e) {
      if (!isDragging) return;
      var deltaX = e.clientX - previousMousePosition.x;
      var deltaY = e.clientY - previousMousePosition.y;
      spherical.theta -= deltaX * 0.005;
      spherical.phi -= deltaY * 0.005;
      spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi));
      updateCamera();
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    container.addEventListener("mouseup", function () {
      isDragging = false;
    });

    container.addEventListener("mouseleave", function () {
      isDragging = false;
    });

    container.addEventListener("wheel", function (e) {
      e.preventDefault();
      radius += e.deltaY * 0.005;
      radius = Math.max(1.5, Math.min(20, radius));
      updateCamera();
    });

    function updateCamera() {
      camera.position.x =
        radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.position.y = radius * Math.cos(spherical.phi);
      camera.position.z =
        radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.lookAt(0, 0, 0);
    }
  }

  return { init: init };
})();
