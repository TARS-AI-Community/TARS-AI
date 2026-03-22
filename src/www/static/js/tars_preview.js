// ── TARS 3D Preview for Builder ──────────────────────────────────────────────
//
// Physical model:
//   TARS is 3 flat planks (right leg, body, left leg) side by side.
//   The HEIGHT servos slide legs up/down relative to the body.
//   The SWING servos rotate legs forward/back around the top axle.
//   The body is PASSIVE — sandwiched between the legs, no motors.
//
//   Geometry (front view, neutral):
//
//       ┌─┐ ┌───┐ ┌─┐
//       │R│ │   │ │L│     ← top axle (pivot for fwd/back swing)
//       │ │ │ B │ │ │     ← height servos slide legs up/down
//       │ │ │   │ │ │
//       └─┘ └───┘ └─┘     ← feet on ground
//      ─────────────────   ← ground (y = 0)
//
//   3D model approach:
//     - Legs slide DOWN relative to body when height increases
//     - Height difference tilts the entire assembly (tarsGroup rotation)
//     - Swing rotates each leg around its top pivot (rotation.x)
//     - Body forward/back swing = damped pendulum physics (gravity + inertia)
//     - Ground constraint prevents any segment from clipping below y=0
//
(function () {
  'use strict';

  var scene, camera, renderer;
  var tarsGroup, segments; // segments = [rightLeg, body, leftLeg]
  var animationFrameId = null;
  var previewPlaying = false;
  var initialized = false;

  var SEG_WIDTH = 1.4;
  var SEG_HEIGHT = 7.0;
  var SEG_DEPTH = 2.1;
  var GAP = 0.15;

  // ── Physics state ──────────────────────────────────────────────────────
  // The body is a damped pendulum hanging from the axle.
  // When legs move, the axle shifts; the body swings to follow with delay.
  var bodySwingAngle = 0;     // current body forward/back angle (radians)
  var bodySwingVel = 0;       // angular velocity (rad/s)
  var PENDULUM_LEN = 3.5;    // CoM distance below axle
  var CONTACT_K = 15.0;      // spring stiffness toward leg angle
  var SWING_DAMPING = 5.0;   // friction
  var lastFrameTime = 0;

  // ── Textures ───────────────────────────────────────────────────────────

  function createOuterTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 512; canvas.height = 1024;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, 512, 1024);
    var step = 64;
    ctx.fillStyle = '#222222';
    ctx.strokeStyle = '#111111';
    ctx.lineWidth = 4;
    for (var y = 0; y < 350; y += step) {
      for (var x = 0; x < 512; x += step) {
        ctx.fillRect(x + 2, y + 2, step - 4, step - 4);
        ctx.strokeRect(x, y, step, step);
      }
    }
    ctx.fillStyle = 'rgba(255,255,255,0.02)';
    for (var i = 0; i < 1000; i++) ctx.fillRect(Math.random() * 512, Math.random() * 1024, 2, 2);
    return new THREE.CanvasTexture(canvas);
  }

  function createCenterTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 1024; canvas.height = 1024;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#bbbbbb';
    ctx.fillRect(0, 0, 1024, 1024);
    ctx.fillStyle = '#111111';
    ctx.fillRect(0, 750, 1024, 120);
    ctx.fillRect(0, 150, 150, 100);
    ctx.fillRect(874, 150, 150, 100);
    ctx.strokeStyle = '#888888';
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(512, 0); ctx.lineTo(512, 1024); ctx.stroke();
    [300, 450, 600, 900].forEach(function (yy) {
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(1024, yy); ctx.stroke();
    });
    ctx.fillStyle = '#cca300';
    ctx.font = 'bold 80px monospace';
    ctx.save();
    ctx.translate(140, 500);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('TARS', 0, 0);
    ctx.restore();
    return new THREE.CanvasTexture(canvas);
  }

  function createScreenTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 512;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#001133';
    ctx.fillRect(0, 0, 256, 512);
    ctx.fillStyle = '#00aaff';
    ctx.fillRect(10, 10, 236, 30);
    for (var i = 60; i < 450; i += 10) {
      var w = Math.random() * 100 + 10;
      ctx.fillStyle = 'rgba(0, 170, 255, ' + Math.random() + ')';
      ctx.fillRect(10, i, w, 4);
    }
    ctx.strokeStyle = '#00aaff';
    ctx.lineWidth = 2;
    ctx.strokeRect(40, 150, 176, 200);
    return new THREE.CanvasTexture(canvas);
  }

  // ── Build TARS geometry ────────────────────────────────────────────────
  // Each segment's pivot is at the TOP of the mesh (the axle point).
  // The mesh hangs downward from the pivot.

  function buildTars() {
    tarsGroup = new THREE.Group();
    segments = [];

    var outerMat = new THREE.MeshStandardMaterial({ map: createOuterTexture(), roughness: 0.7, metalness: 0.3 });
    var centerMat = new THREE.MeshStandardMaterial({ map: createCenterTexture(), roughness: 0.4, metalness: 0.6 });
    var screenMat = new THREE.MeshBasicMaterial({ map: createScreenTexture() });

    var legW = SEG_WIDTH;
    var bodyW = SEG_WIDTH * 2 + GAP;

    // segments[0] = right leg (negative X)
    // segments[1] = body (center)
    // segments[2] = left leg (positive X)
    var configs = [
      { width: legW, mat: outerMat, x: -(bodyW / 2 + legW / 2 + GAP) },
      { width: bodyW, mat: centerMat, x: 0 },
      { width: legW, mat: outerMat, x: (bodyW / 2 + legW / 2 + GAP) }
    ];

    configs.forEach(function (cfg, i) {
      var geo = new THREE.BoxGeometry(cfg.width, SEG_HEIGHT, SEG_DEPTH);
      var mesh = new THREE.Mesh(geo, cfg.mat);
      mesh.castShadow = true;

      // Pivot at the very top of the mesh
      var pivot = new THREE.Group();
      pivot.position.set(cfg.x, SEG_HEIGHT, 0); // pivot at top
      mesh.position.y = -SEG_HEIGHT / 2;         // mesh center hangs below pivot
      pivot.add(mesh);

      // Screen on center body
      if (i === 1) {
        var sw = bodyW * 0.6;
        var sh = SEG_HEIGHT * 0.4;
        var screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(sw, sh), screenMat);
        screenMesh.position.set(0, 0.3, (SEG_DEPTH / 2) + 0.01);
        mesh.add(screenMesh);
        var light = new THREE.PointLight(0x00aaff, 0.3, 1.5);
        light.position.set(0, 0.3, SEG_DEPTH / 2 + 0.2);
        mesh.add(light);
      }

      tarsGroup.add(pivot);
      segments.push({ pivot: pivot, mesh: mesh });
    });

    scene.add(tarsGroup);
  }

  // ── Scene setup ────────────────────────────────────────────────────────

  function initScene() {
    if (initialized) return;
    var container = document.getElementById('bldPreviewViewport');
    if (!container || typeof THREE === 'undefined') return;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a14);

    var w = container.clientWidth;
    var h = container.clientHeight;
    camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
    camera.position.set(6, 6, 10);
    camera.lookAt(0, 3, 0);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    var dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(5, 10, 5);
    dirLight.castShadow = true;
    scene.add(dirLight);
    scene.add(new THREE.PointLight(0x00aaff, 0.4, 20).translateX(-4).translateY(6).translateZ(-3));

    // Ground
    var ground = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      new THREE.MeshStandardMaterial({ color: 0x111118, roughness: 0.9, metalness: 0.1 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    var grid = new THREE.GridHelper(20, 20, 0x222233, 0x151522);
    grid.position.y = 0.01;
    scene.add(grid);

    buildTars();
    setupOrbitControls(container);
    initialized = true;
    startRenderLoop();

    var ro = new ResizeObserver(function () {
      var cw = container.clientWidth;
      var ch = container.clientHeight;
      if (cw > 0 && ch > 0) {
        camera.aspect = cw / ch;
        camera.updateProjectionMatrix();
        renderer.setSize(cw, ch);
      }
    });
    ro.observe(container);
  }

  // ── Orbit controls ────────────────────────────────────────────────────

  function setupOrbitControls(container) {
    var isDragging = false;
    var isPanning = false;
    var prevX = 0, prevY = 0;
    var spherical = { theta: 0.6, phi: 1.0, radius: 13 };
    var target = new THREE.Vector3(0, 3, 0);

    function updateCamera() {
      var r = spherical.radius;
      camera.position.set(
        target.x + r * Math.sin(spherical.phi) * Math.sin(spherical.theta),
        target.y + r * Math.cos(spherical.phi),
        target.z + r * Math.sin(spherical.phi) * Math.cos(spherical.theta)
      );
      camera.lookAt(target);
    }
    updateCamera();

    container.addEventListener('mousedown', function (e) {
      if (e.button === 0) isDragging = true;
      if (e.button === 2) isPanning = true;
      prevX = e.clientX; prevY = e.clientY;
      e.preventDefault();
    });
    container.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    window.addEventListener('mousemove', function (e) {
      var dx = e.clientX - prevX;
      var dy = e.clientY - prevY;
      prevX = e.clientX; prevY = e.clientY;
      if (isDragging) {
        spherical.theta -= dx * 0.005;
        spherical.phi -= dy * 0.005;
        spherical.phi = Math.max(0.2, Math.min(Math.PI - 0.2, spherical.phi));
        updateCamera();
      }
      if (isPanning) {
        var right = new THREE.Vector3();
        camera.getWorldDirection(right);
        right.cross(new THREE.Vector3(0, 1, 0)).normalize();
        target.addScaledVector(right, -dx * 0.02);
        target.y += dy * 0.02;
        updateCamera();
      }
    });
    window.addEventListener('mouseup', function () { isDragging = false; isPanning = false; });
    container.addEventListener('wheel', function (e) {
      spherical.radius += e.deltaY * 0.01;
      spherical.radius = Math.max(5, Math.min(30, spherical.radius));
      updateCamera();
      e.preventDefault();
    }, { passive: false });

    // Touch
    var touchStartDist = 0;
    container.addEventListener('touchstart', function (e) {
      if (e.touches.length === 1) {
        isDragging = true;
        prevX = e.touches[0].clientX;
        prevY = e.touches[0].clientY;
      } else if (e.touches.length === 2) {
        isDragging = false;
        var dx = e.touches[0].clientX - e.touches[1].clientX;
        var dy = e.touches[0].clientY - e.touches[1].clientY;
        touchStartDist = Math.sqrt(dx * dx + dy * dy);
      }
    });
    container.addEventListener('touchmove', function (e) {
      e.preventDefault();
      if (e.touches.length === 1 && isDragging) {
        var dx = e.touches[0].clientX - prevX;
        var dy = e.touches[0].clientY - prevY;
        prevX = e.touches[0].clientX;
        prevY = e.touches[0].clientY;
        spherical.theta -= dx * 0.005;
        spherical.phi -= dy * 0.005;
        spherical.phi = Math.max(0.2, Math.min(Math.PI - 0.2, spherical.phi));
        updateCamera();
      } else if (e.touches.length === 2) {
        var ddx = e.touches[0].clientX - e.touches[1].clientX;
        var ddy = e.touches[0].clientY - e.touches[1].clientY;
        var dist = Math.sqrt(ddx * ddx + ddy * ddy);
        spherical.radius += (touchStartDist - dist) * 0.03;
        spherical.radius = Math.max(5, Math.min(30, spherical.radius));
        touchStartDist = dist;
        updateCamera();
      }
    }, { passive: false });
    container.addEventListener('touchend', function () { isDragging = false; });
  }

  // ── Render loop with physics ───────────────────────────────────────────

  function startRenderLoop() {
    lastFrameTime = performance.now();
    function loop(now) {
      animationFrameId = requestAnimationFrame(loop);
      if (!segments || segments.length < 3) {
        if (renderer && scene && camera) renderer.render(scene, camera);
        return;
      }

      var dt = Math.min((now - lastFrameTime) / 1000, 0.05);
      lastFrameTime = now;

      // ── Body pendulum physics ────────────────────────────────────────
      // The body hangs from the axle.  The "target" angle is where
      // the legs are pushing — the body swings toward it with inertia.
      //
      // Forces:
      //   1. Gravity → pulls body toward vertical (angle = 0)
      //   2. Leg contact → spring toward the average leg swing angle
      //   3. Damping → friction
      var rSwing = segments[0].targetSwing || 0;
      var lSwing = segments[2].targetSwing || 0;
      var legAngle = (rSwing + lSwing) / 2;

      var gravityTorque = -(9.8 / PENDULUM_LEN) * Math.sin(bodySwingAngle);
      var contactTorque = -CONTACT_K * (bodySwingAngle - legAngle);
      var dampingTorque = -SWING_DAMPING * bodySwingVel;

      bodySwingVel += (gravityTorque + contactTorque + dampingTorque) * dt;
      bodySwingAngle += bodySwingVel * dt;

      // Body can overshoot legs slightly but not wildly
      var maxOvershoot = 0.15;
      var lo = Math.min(0, legAngle) - maxOvershoot;
      var hi = Math.max(0, legAngle) + maxOvershoot;
      if (bodySwingAngle < lo) { bodySwingAngle = lo; bodySwingVel *= -0.2; }
      if (bodySwingAngle > hi) { bodySwingAngle = hi; bodySwingVel *= -0.2; }

      // Apply body rotation
      segments[1].pivot.rotation.x = bodySwingAngle;

      // ── Ground constraint ─────────────────────────────────────────
      // applyPose sets tarsGroup position/rotation for height+tilt.
      // Check if swing rotation pushes any foot below ground and
      // add extra lift if needed (don't overwrite, just add).
      var lowestWorld = Infinity;
      for (var si = 0; si < 3; si++) {
        var seg = segments[si].pivot;
        var swAngle = seg.rotation.x;
        // Local bottom Y (before tarsGroup transform)
        var localBottomY = seg.position.y - SEG_HEIGHT * Math.cos(swAngle);
        // Transform to world: rotate by tarsGroup.rotation.z, then translate
        var localX = seg.position.x;
        var worldY = tarsGroup.position.y
          + localX * Math.sin(tarsGroup.rotation.z)
          + localBottomY * Math.cos(tarsGroup.rotation.z);
        if (worldY < lowestWorld) lowestWorld = worldY;
      }
      if (lowestWorld < 0) {
        tarsGroup.position.y -= lowestWorld;
      }

      if (renderer && scene && camera) renderer.render(scene, camera);
    }
    loop(performance.now());
  }

  // ── Map builder step values to TARS poses ──────────────────────────────
  // Builder values: 1-100, 50 = neutral.
  //   height 1 = fully retracted (up), 100 = fully extended (down/push)
  //   leg    1 = fully forward,        100 = fully backward

  function mapStepToPose(step) {
    // Normalize to -1..+1 range
    var lh = ((step.left_height  || 50) - 50) / 50;
    var rh = ((step.right_height || 50) - 50) / 50;
    var ll = ((step.left_leg     || 50) - 50) / 50;
    var rl = ((step.right_leg    || 50) - 50) / 50;

    return {
      leftHeight:  lh * 2.5,   // leg extension offset (units)
      rightHeight: rh * 2.5,
      leftSwing:   ll * 0.5,   // leg rotation (radians)
      rightSwing:  rl * 0.5
    };
  }

  // ── Apply a pose to the 3D model ──────────────────────────────────────
  //
  // Pose has 4 values (from builder sliders, normalized):
  //   leftHeight / rightHeight  — leg extension (units, 0 = neutral)
  //   leftSwing  / rightSwing   — leg fwd/back rotation (radians)
  //
  // What this function does:
  //   1. Slides each leg's pivot DOWN by its height offset (body stays)
  //   2. Applies swing rotation to each leg (rotation.x)
  //   3. Tilts the entire tarsGroup based on height difference
  //   4. Positions tarsGroup so the grounded foot stays at y=0
  //   5. Body rotation.x is set by the physics loop (not here)

  function applyPose(pose) {
    if (!segments || segments.length < 3) return;

    // ── Segment positioning ─────────────────────────────────────
    // Legs slide DOWN relative to body (height extension).
    // tarsGroup handles assembly tilt + lift so segments stay
    // flush and don't clip through each other.

    var baseY = SEG_HEIGHT;

    // Legs SLIDE relative to body when height changes.
    // Extended leg moves DOWN, body stays at base height.
    segments[0].pivot.position.y = baseY - pose.rightHeight;  // right leg slides down
    segments[2].pivot.position.y = baseY - pose.leftHeight;   // left leg slides down
    segments[1].pivot.position.y = baseY;                     // body stays at axle

    // No per-segment side tilt (they're sandwiched)
    segments[1].pivot.rotation.z = 0;

    // Leg swing
    segments[0].pivot.rotation.x = pose.rightSwing;
    segments[0].targetSwing = pose.rightSwing;
    segments[2].pivot.rotation.x = pose.leftSwing;
    segments[2].targetSwing = pose.leftSwing;

    // ── Height → tarsGroup lift + tilt ───────────────────────────
    // Both legs extending equally → pure lift (body rises)
    // One leg extending more → assembly tips toward the shorter side
    var lh = pose.leftHeight;
    var rh = pose.rightHeight;

    // The shorter leg's foot stays on ground.
    // The common extension lifts the whole robot.
    var commonLift = Math.min(lh, rh);
    var heightDiff = rh - lh;  // positive = right (neg-X) extends more

    // Tilt: rotate entire assembly around the grounded foot
    // Right leg at negative-X, left leg at positive-X
    var rightX = segments[0].pivot.position.x;  // negative
    var leftX  = segments[2].pivot.position.x;  // positive
    var span = leftX - rightX;  // total foot span

    // Tilt angle: negative rotation.z → right side (neg-X) goes UP
    var tiltAngle = -Math.atan2(heightDiff, span);
    tarsGroup.rotation.z = tiltAngle;

    // Position tarsGroup so the grounded foot stays at y = 0
    // The grounded foot is on the shorter-leg side
    var groundedX = (heightDiff >= 0) ? leftX : rightX;
    // After rotation, the grounded foot's Y = groundedX * sin(tiltAngle)
    // Compensate so it lands at y = 0, plus add common lift
    tarsGroup.position.y = commonLift - groundedX * Math.sin(tiltAngle);
    tarsGroup.position.x = groundedX * (1 - Math.cos(tiltAngle));

    // rotation.x set by physics in render loop
  }

  function resetPose() {
    bodySwingAngle = 0;
    bodySwingVel = 0;
    applyPose({ leftHeight: 0, rightHeight: 0, leftSwing: 0, rightSwing: 0 });
    if (tarsGroup) {
      tarsGroup.position.set(0, 0, 0);
      tarsGroup.rotation.set(0, 0, 0);
    }
  }

  // ── Preview animation ─────────────────────────────────────────────────

  var animSteps = [];
  var animIndex = 0;
  var animTimerId = null;

  function playPreview() {
    if (!window._bldGetSteps) return;
    var rawSteps = window._bldGetSteps();
    animSteps = rawSteps.filter(function (s) { return !s.movement; });
    if (animSteps.length === 0) return;

    previewPlaying = true;
    animIndex = 0;

    var playBtn = document.getElementById('bldPreview');
    var stopBtn = document.getElementById('bldPreviewStop');
    if (playBtn) playBtn.style.display = 'none';
    if (stopBtn) stopBtn.style.display = '';

    animatePreviewStep();
  }

  function stopPreview() {
    previewPlaying = false;
    if (animTimerId) { clearTimeout(animTimerId); animTimerId = null; }
    resetPose();

    var playBtn = document.getElementById('bldPreview');
    var stopBtn = document.getElementById('bldPreviewStop');
    if (playBtn) playBtn.style.display = '';
    if (stopBtn) stopBtn.style.display = 'none';
  }

  function animatePreviewStep() {
    if (!previewPlaying || animIndex >= animSteps.length) {
      stopPreview();
      return;
    }

    var step = animSteps[animIndex];
    var targetPose = mapStepToPose(step);
    var speed = step.speed || 0.85;
    var holdTime = (step.hold_time || 0) * 1000;
    var transitionMs = (1.1 - speed) * 800 + 100;

    var startPose;
    if (animIndex > 0) {
      startPose = mapStepToPose(animSteps[animIndex - 1]);
    } else {
      startPose = { leftHeight: 0, rightHeight: 0, leftSwing: 0, rightSwing: 0 };
    }

    var startTime = performance.now();

    function tweenStep() {
      if (!previewPlaying) return;
      var elapsed = performance.now() - startTime;
      var t = Math.min(elapsed / transitionMs, 1);
      t = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

      applyPose({
        leftHeight:  startPose.leftHeight  + (targetPose.leftHeight  - startPose.leftHeight)  * t,
        rightHeight: startPose.rightHeight + (targetPose.rightHeight - startPose.rightHeight) * t,
        leftSwing:   startPose.leftSwing   + (targetPose.leftSwing   - startPose.leftSwing)   * t,
        rightSwing:  startPose.rightSwing  + (targetPose.rightSwing  - startPose.rightSwing)  * t
      });

      if (t < 1) {
        requestAnimationFrame(tweenStep);
      } else {
        animTimerId = setTimeout(function () {
          animIndex++;
          animatePreviewStep();
        }, holdTime);
      }
    }

    requestAnimationFrame(tweenStep);
  }

  // ── Init ───────────────────────────────────────────────────────────────

  function bindButtons() {
    var playBtn = document.getElementById('bldPreview');
    var stopBtn = document.getElementById('bldPreviewStop');
    if (playBtn) playBtn.addEventListener('click', function () {
      initScene();
      playPreview();
    });
    if (stopBtn) stopBtn.addEventListener('click', stopPreview);
  }

  function watchForVisibility() {
    var viewport = document.getElementById('bldPreviewViewport');
    if (!viewport) return;
    var observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting && !initialized) initScene();
    }, { threshold: 0.1 });
    observer.observe(viewport);
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindButtons();
    watchForVisibility();
  });
})();
