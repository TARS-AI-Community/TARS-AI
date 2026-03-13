/* ═══════════════════════════════════════════════════
   T.A.R.S. · Cosmic Ray Background
   Prismatic light streaks + ambient particles
   RPi-safe: 30fps cap, low element count
   Theme-aware: reads CSS custom properties for colors
═══════════════════════════════════════════════════ */

(function () {
  'use strict';

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var canvas = document.getElementById('particleBg');
  if (!canvas) return;

  var ctx = canvas.getContext('2d');
  var w, h;
  var TARGET_FPS = 30;
  var frameInterval = 1000 / TARGET_FPS;
  var lastFrame = 0;
  var time = 0;

  // ── Theme-aware color reading ──
  var themeParticleRGB = '0, 229, 255';  // fallback cyan
  var themeOrbHues = [190, 280, 320];    // fallback cyan, purple, magenta
  var themeRaysEnabled = true;

  function readThemeColors() {
    var style = getComputedStyle(document.documentElement);

    // Read particle color from --accent-rgb (e.g. "0, 229, 255")
    var accentRaw = style.getPropertyValue('--accent-rgb').trim();
    if (accentRaw) themeParticleRGB = accentRaw;

    // Read orb hues from --particle-orb-hues (e.g. "190, 280, 320")
    var orbRaw = style.getPropertyValue('--particle-orb-hues').trim();
    if (orbRaw) {
      themeOrbHues = orbRaw.split(',').map(function(s) { return parseInt(s.trim(), 10); });
    }

    // Check if rays are disabled by theme
    var raysRaw = style.getPropertyValue('--particle-rays').trim();
    themeRaysEnabled = raysRaw !== 'none';

    // Read custom prism palette if provided (semicolon-separated r,g,b groups)
    var prismRaw = style.getPropertyValue('--particle-prism').trim();
    if (prismRaw && prismRaw !== 'default') {
      try {
        var groups = prismRaw.split(';');
        var newColors = [];
        for (var i = 0; i < groups.length; i++) {
          var parts = groups[i].trim().split(',');
          if (parts.length === 3) {
            newColors.push({ r: parseInt(parts[0],10), g: parseInt(parts[1],10), b: parseInt(parts[2],10) });
          }
        }
        if (newColors.length > 0) PRISM_COLORS = newColors;
      } catch(e) { /* keep defaults */ }
    }
  }

  // ── Prismatic rays (the "cosmic rays" / chromatic aberration streaks) ──
  var rays = [];
  var RAY_COUNT = 6;

  // ── Ambient glow orbs ──
  var orbs = [];
  var ORB_COUNT = 4;

  // ── Small floating particles ──
  var particles = [];
  var PARTICLE_COUNT = 25;
  var CONNECTION_DIST = 120;

  // Rainbow color palette for prismatic effects (overridable by theme)
  var PRISM_COLORS = [
    { r: 255, g: 0,   b: 60  },  // red
    { r: 255, g: 100, b: 0   },  // orange
    { r: 255, g: 220, b: 0   },  // yellow
    { r: 0,   g: 255, b: 80  },  // green
    { r: 0,   g: 180, b: 255 },  // cyan
    { r: 80,  g: 0,   b: 255 },  // blue
    { r: 180, g: 0,   b: 255 }   // violet
  ];

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  // ── Ray creation ──
  function createRay() {
    var side = Math.floor(Math.random() * 4); // 0=top, 1=right, 2=bottom, 3=left
    var x, y, angle;

    // Position rays near edges/corners for that lens flare look
    switch (side) {
      case 0: x = Math.random() * w; y = -20; angle = Math.PI * 0.3 + Math.random() * 0.4; break;
      case 1: x = w + 20; y = Math.random() * h; angle = Math.PI * 0.6 + Math.random() * 0.4; break;
      case 2: x = Math.random() * w; y = h + 20; angle = -Math.PI * 0.3 + Math.random() * 0.4; break;
      default: x = -20; y = Math.random() * h; angle = -Math.PI * 0.1 + Math.random() * 0.4; break;
    }

    var colorIdx = Math.floor(Math.random() * PRISM_COLORS.length);
    return {
      x: x,
      y: y,
      angle: angle + (Math.random() - 0.5) * 0.3,
      length: 150 + Math.random() * 300,
      width: 1 + Math.random() * 3,
      speed: 0.002 + Math.random() * 0.004,
      drift: (Math.random() - 0.5) * 0.15,
      alpha: 0,
      maxAlpha: 0.04 + Math.random() * 0.08,
      phase: Math.random() * Math.PI * 2,
      life: 0,
      maxLife: 300 + Math.random() * 400,
      colorIdx: colorIdx,
      spread: 8 + Math.random() * 16 // chromatic spread distance
    };
  }

  // ── Orb creation (soft ambient glows) ──
  function createOrb() {
    var huePool = themeOrbHues;
    var hue = huePool[Math.floor(Math.random() * huePool.length)];
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      radius: 80 + Math.random() * 200,
      vx: (Math.random() - 0.5) * 0.15,
      vy: (Math.random() - 0.5) * 0.15,
      hue: hue,
      alpha: 0.015 + Math.random() * 0.02,
      phase: Math.random() * Math.PI * 2
    };
  }

  // ── Particle creation ──
  function createParticle() {
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.2 + 0.3,
      alpha: Math.random() * 0.3 + 0.1
    };
  }

  function init() {
    resize();
    readThemeColors();
    rays = [];
    orbs = [];
    particles = [];

    for (var i = 0; i < RAY_COUNT; i++) {
      rays.push(createRay());
    }
    for (var j = 0; j < ORB_COUNT; j++) {
      orbs.push(createOrb());
    }
    for (var k = 0; k < PARTICLE_COUNT; k++) {
      particles.push(createParticle());
    }
  }

  // ── Update ──
  function update() {
    time += 0.016; // ~60fps equivalent time step at 30fps

    // Update rays
    if (themeRaysEnabled) {
      for (var i = 0; i < rays.length; i++) {
        var r = rays[i];
        r.life++;
        r.angle += r.drift * 0.001;

        // Fade in/out lifecycle
        var lifeRatio = r.life / r.maxLife;
        if (lifeRatio < 0.15) {
          r.alpha = r.maxAlpha * (lifeRatio / 0.15);
        } else if (lifeRatio > 0.75) {
          r.alpha = r.maxAlpha * (1 - (lifeRatio - 0.75) / 0.25);
        } else {
          r.alpha = r.maxAlpha;
        }

        // Subtle shimmer
        r.alpha *= 0.8 + 0.2 * Math.sin(time * 2 + r.phase);

        // Respawn dead rays
        if (r.life >= r.maxLife) {
          rays[i] = createRay();
        }
      }
    }

    // Update orbs
    for (var j = 0; j < orbs.length; j++) {
      var o = orbs[j];
      o.x += o.vx;
      o.y += o.vy;

      // Soft bounce at edges
      if (o.x < -o.radius) o.x = w + o.radius;
      if (o.x > w + o.radius) o.x = -o.radius;
      if (o.y < -o.radius) o.y = h + o.radius;
      if (o.y > h + o.radius) o.y = -o.radius;
    }

    // Update particles
    for (var k = 0; k < particles.length; k++) {
      var p = particles[k];
      p.vx *= 0.99;
      p.vy *= 0.99;
      p.x += p.vx;
      p.y += p.vy;

      if (p.x < -10) p.x = w + 10;
      if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10;
      if (p.y > h + 10) p.y = -10;
    }
  }

  // ── Draw ──
  function draw() {
    ctx.clearRect(0, 0, w, h);

    // 1. Draw ambient glow orbs (bottom layer)
    for (var j = 0; j < orbs.length; j++) {
      var o = orbs[j];
      var pulse = 0.8 + 0.2 * Math.sin(time * 0.5 + o.phase);
      var grad = ctx.createRadialGradient(o.x, o.y, 0, o.x, o.y, o.radius);
      grad.addColorStop(0, 'hsla(' + o.hue + ', 80%, 50%, ' + (o.alpha * pulse) + ')');
      grad.addColorStop(0.5, 'hsla(' + o.hue + ', 80%, 40%, ' + (o.alpha * pulse * 0.3) + ')');
      grad.addColorStop(1, 'hsla(' + o.hue + ', 80%, 30%, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(o.x - o.radius, o.y - o.radius, o.radius * 2, o.radius * 2);
    }

    // 2. Draw prismatic rays (chromatic aberration streaks)
    if (themeRaysEnabled) {
      ctx.save();
      ctx.globalCompositeOperation = 'screen';

      for (var i = 0; i < rays.length; i++) {
        var r = rays[i];
        if (r.alpha < 0.001) continue;

        var cos = Math.cos(r.angle);
        var sin = Math.sin(r.angle);
        var perpX = -sin;
        var perpY = cos;

        // Draw multiple color-shifted streaks for chromatic aberration
        for (var c = 0; c < PRISM_COLORS.length; c++) {
          var color = PRISM_COLORS[c];
          var offset = (c - 3) * (r.spread / PRISM_COLORS.length);

          var sx = r.x + perpX * offset;
          var sy = r.y + perpY * offset;
          var ex = sx + cos * r.length;
          var ey = sy + sin * r.length;

          var rayGrad = ctx.createLinearGradient(sx, sy, ex, ey);
          var a = r.alpha * 0.7;
          rayGrad.addColorStop(0, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ', 0)');
          rayGrad.addColorStop(0.2, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',' + a * 0.5 + ')');
          rayGrad.addColorStop(0.5, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',' + a + ')');
          rayGrad.addColorStop(0.8, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',' + a * 0.5 + ')');
          rayGrad.addColorStop(1, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ', 0)');

          ctx.strokeStyle = rayGrad;
          ctx.lineWidth = r.width;
          ctx.beginPath();
          ctx.moveTo(sx, sy);
          ctx.lineTo(ex, ey);
          ctx.stroke();
        }
      }

      ctx.restore();
    }

    // 3. Draw particle connections (very subtle)
    ctx.lineWidth = 0.4;
    for (var m = 0; m < particles.length; m++) {
      for (var n = m + 1; n < particles.length; n++) {
        var dx = particles[m].x - particles[n].x;
        var dy = particles[m].y - particles[n].y;
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECTION_DIST) {
          var alpha = (1 - dist / CONNECTION_DIST) * 0.08;
          ctx.strokeStyle = 'rgba(' + themeParticleRGB + ', ' + alpha + ')';
          ctx.beginPath();
          ctx.moveTo(particles[m].x, particles[m].y);
          ctx.lineTo(particles[n].x, particles[n].y);
          ctx.stroke();
        }
      }
    }

    // 4. Draw particles (small dots)
    for (var k = 0; k < particles.length; k++) {
      var p = particles[k];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + themeParticleRGB + ', ' + (p.alpha * 0.7) + ')';
      ctx.fill();
    }
  }

  function loop(timestamp) {
    requestAnimationFrame(loop);
    var delta = timestamp - lastFrame;
    if (delta < frameInterval) return;
    lastFrame = timestamp - (delta % frameInterval);
    update();
    draw();
  }

  window.addEventListener('resize', function () {
    resize();
    // Reposition orbs that are now off-screen
    for (var j = 0; j < orbs.length; j++) {
      if (orbs[j].x > w + orbs[j].radius) orbs[j].x = w * Math.random();
      if (orbs[j].y > h + orbs[j].radius) orbs[j].y = h * Math.random();
    }
  });

  // Re-read theme colors when the theme stylesheet changes
  var themeLink = document.getElementById('themeCSS');
  if (themeLink) {
    themeLink.addEventListener('load', function () {
      readThemeColors();
      // Reinit orbs with new hues
      orbs = [];
      for (var j = 0; j < ORB_COUNT; j++) { orbs.push(createOrb()); }
    });
  }

  init();
  requestAnimationFrame(loop);
})();
