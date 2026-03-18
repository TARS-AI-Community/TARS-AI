// ── TARS 3D Preview for Builder ──────────────────────────────────────────────
(function () {
  'use strict';

  var scene, camera, renderer, controls;
  var tarsGroup, segments; // segments = [leftLeg, body, rightLeg]
  var animationFrameId = null;
  var previewPlaying = false;
  var initialized = false;

  var SEG_WIDTH = 1.4;
  var SEG_HEIGHT = 7.0;
  var SEG_DEPTH = 2.1;
  var GAP = 0.15;

  // ── Build TARS geometry ────────────────────────────────────────────────────

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

  function buildTars() {
    tarsGroup = new THREE.Group();
    segments = [];

    var outerMat = new THREE.MeshStandardMaterial({ map: createOuterTexture(), roughness: 0.7, metalness: 0.3 });
    var centerMat = new THREE.MeshStandardMaterial({ map: createCenterTexture(), roughness: 0.4, metalness: 0.6 });
    var screenMat = new THREE.MeshBasicMaterial({ map: createScreenTexture() });

    var legW = SEG_WIDTH;
    var bodyW = SEG_WIDTH * 2 + GAP;

    var configs = [
      { width: legW, mat: outerMat, x: -(bodyW / 2 + legW / 2 + GAP) },
      { width: bodyW, mat: centerMat, x: 0 },
      { width: legW, mat: outerMat, x: (bodyW / 2 + legW / 2 + GAP) }
    ];

    configs.forEach(function (cfg, i) {
      var geo = new THREE.BoxGeometry(cfg.width, SEG_HEIGHT, SEG_DEPTH);
      var mesh = new THREE.Mesh(geo, cfg.mat);
      mesh.castShadow = true;

      var pivotY = SEG_HEIGHT - 0.2;
      var pivot = new THREE.Group();
      pivot.position.set(cfg.x, pivotY, 0);
      mesh.position.y = (SEG_HEIGHT / 2) - pivotY;
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
      segments.push({ pivot: pivot, mesh: mesh, baseY: pivotY });
    });

    scene.add(tarsGroup);
  }

  // ── Scene setup ────────────────────────────────────────────────────────────

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

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    var dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight.position.set(5, 10, 5);
    dirLight.castShadow = true;
    scene.add(dirLight);
    var rimLight = new THREE.PointLight(0x00aaff, 0.4, 20);
    rimLight.position.set(-4, 6, -3);
    scene.add(rimLight);

    // Ground plane
    var groundGeo = new THREE.PlaneGeometry(20, 20);
    var groundMat = new THREE.MeshStandardMaterial({ color: 0x111118, roughness: 0.9, metalness: 0.1 });
    var ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // Grid helper for reference
    var grid = new THREE.GridHelper(20, 20, 0x222233, 0x151522);
    grid.position.y = 0.01;
    scene.add(grid);

    buildTars();

    // Orbit controls (manual since we can't use ES module import)
    setupOrbitControls(container);

    initialized = true;
    startRenderLoop();

    // Resize observer
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

  // ── Simple orbit controls (no ES module dependency) ────────────────────────

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
        var panSpeed = 0.02;
        var right = new THREE.Vector3();
        var up = new THREE.Vector3(0, 1, 0);
        camera.getWorldDirection(right);
        right.cross(up).normalize();
        target.addScaledVector(right, -dx * panSpeed);
        target.y += dy * panSpeed;
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

    // Touch support
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

  // ── Render loop ────────────────────────────────────────────────────────────

  function startRenderLoop() {
    function loop() {
      animationFrameId = requestAnimationFrame(loop);
      if (renderer && scene && camera) renderer.render(scene, camera);
    }
    loop();
  }

  // ── Map builder step values to TARS segment poses ──────────────────────────
  // Builder values are 1-100, 50 = neutral.
  // left_height/right_height: vertical offset of legs
  // left_leg/right_leg: forward/back rotation of legs

  function mapStepToPose(step) {
    var lhNorm = ((step.left_height || 50) - 50) / 50;   // -1 to 1
    var rhNorm = ((step.right_height || 50) - 50) / 50;
    var llNorm = ((step.left_leg || 50) - 50) / 50;
    var rlNorm = ((step.right_leg || 50) - 50) / 50;

    var maxHeight = 2.5;  // max vertical offset
    var maxAngle = 0.5;   // max rotation in radians

    return {
      leftY: lhNorm * maxHeight,
      rightY: rhNorm * maxHeight,
      leftRot: llNorm * maxAngle,
      rightRot: rlNorm * maxAngle,
      bodyTilt: (lhNorm - rhNorm) * 0.1 // slight body tilt from uneven heights
    };
  }

  function applyPose(pose) {
    if (!segments || segments.length < 3) return;
    // Left leg
    segments[0].pivot.position.y = segments[0].baseY + pose.leftY;
    segments[0].pivot.rotation.x = pose.leftRot;
    // Body
    segments[1].pivot.rotation.z = pose.bodyTilt;
    // Right leg
    segments[2].pivot.position.y = segments[2].baseY + pose.rightY;
    segments[2].pivot.rotation.x = pose.rightRot;
  }

  function resetPose() {
    applyPose({ leftY: 0, rightY: 0, leftRot: 0, rightRot: 0, bodyTilt: 0 });
  }

  // ── Preview animation ─────────────────────────────────────────────────────

  var animSteps = [];
  var animIndex = 0;
  var animProgress = 0;
  var animTimerId = null;

  function playPreview() {
    if (!window._bldGetSteps) return;
    var rawSteps = window._bldGetSteps();
    // Filter to position steps only (movement steps can't be previewed)
    animSteps = rawSteps.filter(function (s) { return !s.movement; });
    if (animSteps.length === 0) return;

    previewPlaying = true;
    animIndex = 0;
    animProgress = 0;

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
    var transitionMs = (1.1 - speed) * 800 + 100; // faster speed = shorter transition

    // Get current pose from segments
    var startPose = {
      leftY: segments[0].pivot.position.y - segments[0].baseY,
      rightY: segments[2].pivot.position.y - segments[2].baseY,
      leftRot: segments[0].pivot.rotation.x,
      rightRot: segments[2].pivot.rotation.x,
      bodyTilt: segments[1].pivot.rotation.z
    };

    var startTime = performance.now();

    function tweenStep() {
      if (!previewPlaying) return;
      var elapsed = performance.now() - startTime;
      var t = Math.min(elapsed / transitionMs, 1);
      // Smooth ease in-out
      t = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

      applyPose({
        leftY: startPose.leftY + (targetPose.leftY - startPose.leftY) * t,
        rightY: startPose.rightY + (targetPose.rightY - startPose.rightY) * t,
        leftRot: startPose.leftRot + (targetPose.leftRot - startPose.leftRot) * t,
        rightRot: startPose.rightRot + (targetPose.rightRot - startPose.rightRot) * t,
        bodyTilt: startPose.bodyTilt + (targetPose.bodyTilt - startPose.bodyTilt) * t
      });

      if (t < 1) {
        requestAnimationFrame(tweenStep);
      } else {
        // Hold, then next step
        animTimerId = setTimeout(function () {
          animIndex++;
          animatePreviewStep();
        }, holdTime);
      }
    }

    requestAnimationFrame(tweenStep);
  }

  // ── Init on DOM ready ──────────────────────────────────────────────────────

  function bindButtons() {
    var playBtn = document.getElementById('bldPreview');
    var stopBtn = document.getElementById('bldPreviewStop');
    if (playBtn) playBtn.addEventListener('click', function () {
      initScene();
      playPreview();
    });
    if (stopBtn) stopBtn.addEventListener('click', stopPreview);
  }

  // Initialize scene when the builder tab becomes visible
  function watchForVisibility() {
    var viewport = document.getElementById('bldPreviewViewport');
    if (!viewport) return;

    var observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting && !initialized) {
        initScene();
      }
    }, { threshold: 0.1 });
    observer.observe(viewport);
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindButtons();
    watchForVisibility();
  });
})();
