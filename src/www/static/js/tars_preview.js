// ── TARS 3D Preview for Builder ──────────────────────────────────────────────
//
// Physical model:
//   TARS is 3 flat planks (left leg, body, right leg) side by side.
//   The HEIGHT servos slide legs up/down relative to the body.
//   The SWING servos rotate legs forward/back around the top axle.
//   The body is PASSIVE — sandwiched between the legs, no motors.
//
//   Geometry (front view, neutral):
//
//       ┌─┐ ┌───┐ ┌─┐
//       │L│ │   │ │R│     ← top axle (pivot for fwd/back swing)
//       │ │ │ B │ │ │     ← height servos slide legs up/down
//       │ │ │   │ │ │
//       └─┘ └───┘ └─┘     ← feet on ground
//      ─────────────────   ← ground (y = 0)
//
//   Physics approach (constraint-based):
//     - Legs are DRIVEN (servo values set their position directly)
//     - Body is CONSTRAINED (sandwiched between legs, gravity pulls it vertical)
//     - Body Y: geometric — rises when legs push against ground
//     - Body lean: constrained between leg swing angles, biased toward vertical
//     - Body sway: geometric tilt from leg height difference
//     - All transitions smoothed with lerp (no spring-damper tuning needed)
//
(function () {
  'use strict';

  var scene, camera, renderer;
  var tarsGroup, segments; // segments[0]=left, segments[1]=body, segments[2]=right
  var animationFrameId = null;
  var previewPlaying = false;
  var initialized = false;
  var allowLocomotion = false; // set true only for walk/turn/step movements
  var locomotionDir   = 1;    // 1 = forward (+Z), -1 = backward (-Z)

  var SEG_WIDTH = 1.4;
  var SEG_HEIGHT = 7.0;
  var SEG_DEPTH = 2.1;
  var GAP = 0.15;

  // ── Smooth state ─────────────────────────────────────────────────────
  // All values lerp toward their geometric targets. No velocities needed.
  var smoothBodyY = 0;       // current body height (lerps toward target)
  var smoothLean  = 0;       // current torso forward/back angle
  var smoothSway  = 0;       // current torso side-to-side angle
  var smoothBodyZ = 0;       // accumulated forward position
  var smoothTwist = 0;       // torso Y rotation (twist from leg swing diff)
  var smoothYaw   = 0;       // accumulated tarsGroup Y rotation (turning)

  var prevLeftSwing  = 0;    // for computing forward motion
  var prevRightSwing = 0;

  // Lerp speed: 0.0 = frozen, 1.0 = instant. ~0.12 feels smooth and natural.
  var SMOOTH = 0.12;

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

  function buildTars() {
    tarsGroup = new THREE.Group();
    segments = [];

    var outerMat = new THREE.MeshStandardMaterial({ map: createOuterTexture(), roughness: 0.7, metalness: 0.3 });
    var centerMat = new THREE.MeshStandardMaterial({ map: createCenterTexture(), roughness: 0.4, metalness: 0.6 });
    var screenMat = new THREE.MeshBasicMaterial({ map: createScreenTexture() });

    var legW = SEG_WIDTH;
    var bodyW = SEG_WIDTH * 2 + GAP;

    // segments[0] = left leg  (negative X)
    // segments[1] = body      (center)
    // segments[2] = right leg (positive X)
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
      pivot.position.set(cfg.x, SEG_HEIGHT, 0);
      mesh.position.y = -SEG_HEIGHT / 2;
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

  // ── Render loop (constraint-based) ──────────────────────────────────

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

      // Read current leg state
      var leftSwing  = segments[0].pivot.rotation.x;
      var rightSwing = segments[2].pivot.rotation.x;
      var leftPivotY  = segments[0].pivot.position.y;
      var rightPivotY = segments[2].pivot.position.y;

      // Leg heights relative to body (positive = extended down)
      var leftHeight  = SEG_HEIGHT - leftPivotY;
      var rightHeight = SEG_HEIGHT - rightPivotY;

      // ── 1. Body Y: geometric ground constraint ─────────────────
      // Body rises so no foot clips below ground.
      var targetY = Math.max(leftHeight, rightHeight, 0);
      smoothBodyY += (targetY - smoothBodyY) * SMOOTH;
      tarsGroup.position.y = smoothBodyY;

      segments[1].pivot.rotation.x = 0;

      // ── 3. Torso twist (rotation.y): from leg swing difference ──
      // When legs swing opposite directions (walking), the torso
      // twists — right leg forward → torso twists left, like a human.
      var targetTwist = (leftSwing - rightSwing) * 0.4;
      smoothTwist += (targetTwist - smoothTwist) * SMOOTH;
      segments[1].pivot.rotation.y = smoothTwist;

      segments[1].pivot.rotation.z = 0;

      // ── 4 & 5. Locomotion (only for walk/turn/step movements) ─────
      var leftDelta  = leftSwing  - prevLeftSwing;
      var rightDelta = rightSwing - prevRightSwing;
      if (allowLocomotion) {
        // Grounded leg swinging backward pushes body forward.
        if (leftPivotY <= rightPivotY) {
          if (leftDelta < 0) smoothBodyZ -= leftDelta * 5.0 * locomotionDir;
        } else {
          if (rightDelta < 0) smoothBodyZ -= rightDelta * 5.0 * locomotionDir;
        }
        // Asymmetric swing drives yaw (turning).
        var swingDiffDelta = leftDelta - rightDelta;
        if (Math.abs(swingDiffDelta) > 0.001) smoothYaw += swingDiffDelta * 2.0;
      }

      prevLeftSwing  = leftSwing;
      prevRightSwing = rightSwing;
      tarsGroup.position.z = smoothBodyZ;
      tarsGroup.rotation.set(0, smoothYaw, 0);

      if (renderer && scene && camera) renderer.render(scene, camera);
    }
    loop(performance.now());
  }

  // ── Map builder step values to TARS poses ──────────────────────────────

  function mapStepToPose(step) {
    var lh = ((step.left_height  || 50) - 50) / 50;
    var rh = ((step.right_height || 50) - 50) / 50;
    var ll = ((step.left_leg     || 50) - 50) / 50;
    var rl = ((step.right_leg    || 50) - 50) / 50;

    return {
      leftHeight:  lh * 0.5,
      rightHeight: rh * 0.5,
      leftSwing:  -ll * 0.5,   // negate: servo 1=forward → positive rotation → foot forward
      rightSwing: -rl * 0.5
    };
  }

  // ── Apply a pose to the 3D model ──────────────────────────────────────

  function applyPose(pose) {
    if (!segments || segments.length < 3) return;

    var baseY = SEG_HEIGHT;

    // Legs: directly driven by servo values
    // segments[0] = negative X = screen-left = robot's left
    // segments[2] = positive X = screen-right = robot's right
    // Lower pivot = leg extended further down = foot below ground = body must rise on that side.
    segments[0].pivot.position.y = baseY - pose.leftHeight;
    segments[1].pivot.position.y = baseY;
    segments[2].pivot.position.y = baseY - pose.rightHeight;

    segments[0].pivot.rotation.x = pose.leftSwing;
    segments[2].pivot.rotation.x = pose.rightSwing;

    // Body Y, lean, sway, and forward motion all handled in render loop
  }

  function resetPose() {
    smoothBodyY = 0;
    smoothLean  = 0;
    smoothSway  = 0;
    smoothBodyZ = 0;
    smoothTwist = 0;
    smoothYaw   = 0;
    prevLeftSwing  = 0;
    prevRightSwing = 0;
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

  // Resolve 0 (= "unchanged") servo values by inheriting from the previous step.
  // move_legs(0, 0, ...) means "keep current height" — the preview must do the same.
  function resolveSteps(steps) {
    var prevLH = 50, prevRH = 50, prevLL = 50, prevRL = 50;
    return steps.map(function (s) {
      var lh = (s.left_height  && s.left_height  !== 0) ? s.left_height  : prevLH;
      var rh = (s.right_height && s.right_height !== 0) ? s.right_height : prevRH;
      var ll = (s.left_leg     && s.left_leg     !== 0) ? s.left_leg     : prevLL;
      var rl = (s.right_leg    && s.right_leg    !== 0) ? s.right_leg    : prevRL;
      prevLH = lh; prevRH = rh; prevLL = ll; prevRL = rl;
      return Object.assign({}, s, { left_height: lh, right_height: rh, left_leg: ll, right_leg: rl });
    });
  }

  function playPreview() {
    if (!window._bldGetSteps) return;
    var rawSteps = window._bldGetSteps();
    animSteps = resolveSteps(rawSteps.filter(function (s) { return !s.movement; }));
    if (animSteps.length === 0) return;

    allowLocomotion = !!window._bldLocomotion;
    locomotionDir   = (window._bldLocomotionDir === -1) ? -1 : 1;
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
    allowLocomotion = false;
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
