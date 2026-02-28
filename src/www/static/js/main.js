/* ═══════════════════════════════════════════════════
   T.A.R.S. · MAIN JS
   Modules: wifi · emotions · avatar · chat · arms · legs · motion · config · ui
═══════════════════════════════════════════════════ */

'use strict';

// ── WIFI ────────────────────────────────────────────────────────────────────
(function () {
  let wfSelected = null;

  function signalIcon(sig) {
    return sig >= 40 ? '/static/imgs/wifi-blue.png' : '/static/imgs/wifi-gray.png';
  }

  async function loadStatus() {
    try {
      const d = await fetch('/api/wifi/status').then(r => r.json());
      const icon  = $('wfStatusIcon'), ssid = $('wfStatusSsid'),
            ip    = $('wfStatusIp'),   badge = $('wfStatusBadge'),
            hbtn  = $('wfHotspotBtn');
      if (d.mode === 'client') {
        icon.src = '/static/imgs/wifi-blue.png'; ssid.textContent = d.ssid || 'Connected';
        ip.textContent = d.ip || ''; badge.textContent = 'CONNECTED'; badge.className = 'wf-badge wf-badge-ok';
        hbtn.textContent = 'Start Hotspot';
      } else if (d.mode === 'hotspot') {
        icon.src = '/static/imgs/wifi-yellow.png'; ssid.textContent = 'TARS-Setup';
        ip.textContent = '10.42.0.1'; badge.textContent = 'HOTSPOT'; badge.className = 'wf-badge wf-badge-hot';
        hbtn.textContent = 'Stop Hotspot';
      } else {
        icon.src = '/static/imgs/wifi-gray.png'; ssid.textContent = 'Not connected';
        ip.textContent = ''; badge.textContent = 'OFFLINE'; badge.className = 'wf-badge wf-badge-off';
        hbtn.textContent = 'Start Hotspot';
      }
    } catch {}
  }

  window.wfScan = async function () {
    const list = $('wfNetList');
    list.innerHTML = '<div class="wf-scanning"><span class="wf-spinner"></span>Scanning…</div>';
    wfSelected = null;
    $('wfSelectedCard').style.display = 'none';
    try {
      const d = await fetch('/api/wifi/networks').then(r => r.json());
      const nets = d.networks || [];
      if (!nets.length) { list.innerHTML = '<div class="wf-scanning">No networks found.</div>'; return; }
      list.innerHTML = nets.map(n => `
        <button class="wf-net-btn${n.in_use ? ' in-use' : ''}" onclick='wfSelect(${JSON.stringify(n)})' data-ssid="${n.ssid}">
          <img class="wf-net-icon" src="${signalIcon(n.signal)}" alt="">
          <span class="wf-net-name">${n.ssid}${n.in_use ? ' <span style="color:var(--green);font-size:.68rem;">✓</span>' : ''}</span>
          <span class="wf-net-sec">${n.security || ''}</span>
        </button>`).join('');
    } catch (e) {
      list.innerHTML = `<div class="wf-scanning" style="color:var(--red);">Scan failed: ${e.message}</div>`;
    }
  };

  window.wfSelect = function (net) {
    wfSelected = net;
    document.querySelectorAll('.wf-net-btn').forEach(b => b.classList.toggle('selected', b.dataset.ssid === net.ssid));
    const isEnt = net.security === 'WPA2-Enterprise', isOpen = net.security === 'open';
    $('wfCardSsid').textContent = net.ssid;
    $('wfCardDesc').textContent = isOpen ? 'Open network' : isEnt ? 'Enterprise (802.1X)' : 'Password required';
    $('wfPersonalFields').style.display   = isEnt ? 'none' : '';
    $('wfEnterpriseFields').style.display = isEnt ? '' : 'none';
    ['wfPassword','wfUsername','wfPasswordEnt'].forEach(id => $(id).value = '');
    $('wfMsg').textContent = ''; $('wfMsg').className = 'wf-msg';
    $('wfSelectedCard').style.display = '';
  };

  window.wfDeselect = function () {
    wfSelected = null;
    document.querySelectorAll('.wf-net-btn').forEach(b => b.classList.remove('selected'));
    $('wfSelectedCard').style.display = 'none';
  };

  window.wfConnect = function () {
    if (!wfSelected) return;
    $('wfConfirmSsid').textContent  = wfSelected.ssid;
    $('wfConfirmSsid2').textContent = wfSelected.ssid;
    $('wfConfirmMsg').textContent   = ''; $('wfConfirmMsg').className = 'wf-msg';
    $('wfConfirmBtn').disabled = false; $('wfConfirmBtn').textContent = 'Connect Now';
    $('wfConfirmOverlay').style.display = 'flex';
  };

  window.wfConfirmCancel = function () { $('wfConfirmOverlay').style.display = 'none'; };

  window.wfConfirmConnect = async function () {
    const btn = $('wfConfirmBtn'), cancel = $('wfCancelBtn'), msg = $('wfConfirmMsg');
    const isEnt = wfSelected.security === 'WPA2-Enterprise';
    const password = isEnt ? $('wfPasswordEnt').value : $('wfPassword').value;
    const username = isEnt ? $('wfUsername').value : '';
    btn.disabled = true; cancel.disabled = true;
    btn.innerHTML = '<span class="wf-spinner"></span>Connecting…'; msg.textContent = '';
    try {
      const r = await fetch('/api/wifi/connect', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ ssid: wfSelected.ssid, password, username })
      });
      const d = await r.json();
      if (!r.ok || !d.success) throw new Error(d.error || 'Connection failed');
      msg.textContent = '✓ Connected! Hotspot shutting down…'; msg.className = 'wf-msg wf-msg-ok';
      if (window.showToast) showToast('WiFi connected to ' + wfSelected.ssid, 'success');
      setTimeout(() => { $('wfConfirmOverlay').style.display = 'none'; wfDeselect(); loadStatus(); }, 2500);
    } catch (e) {
      msg.textContent = '✗ ' + e.message; msg.className = 'wf-msg wf-msg-err';
      btn.disabled = false; cancel.disabled = false; btn.textContent = 'Connect Now';
    }
  };

  window.wfToggleHotspot = function () {
    const btn = $('wfHotspotBtn');
    const isHotspot = btn.textContent.trim() === 'Stop Hotspot';
    const msg = isHotspot
      ? 'Stop the hotspot and go offline?'
      : 'This will disconnect Wi-Fi and start the hotspot. Continue?';
    if (!confirm(msg)) return;
    btn.disabled = true;
    fetch('/api/wifi/hotspot', { method: 'PUT' })
      .then(() => setTimeout(loadStatus, 1500))
      .finally(() => { btn.disabled = false; });
  };

  const wifiTab = $('wifi-tab');
  if (wifiTab) wifiTab.addEventListener('shown.bs.tab', () => { loadStatus(); wfScan(); });
})();


// ── EMOTIONS ────────────────────────────────────────────────────────────────
(function () {
  window.emSetMood = async function (mood) {
    document.querySelectorAll('.em-btn').forEach(b => b.classList.remove('active'));
    event.currentTarget.classList.add('active');
    const status = $('emStatus');
    status.textContent = 'Sending…';
    try {
      const d = await fetch('/api/eyes/mood', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ mood })
      }).then(r => r.json());
      status.textContent = d.success ? '✓ ' + mood.toLowerCase() : '✗ ' + (d.error || 'failed');
    } catch (e) { status.textContent = '✗ ' + e.message; }
  };
})();


// ── AVATAR ──────────────────────────────────────────────────────────────────
let talkingheadBaseUrl = '';
let avatarIsTalking = false, avatarIsBlinking = false;
let avatarNextBlink = Date.now() + 3000 + Math.random() * 1000;
let avatarBlinkEnd = 0, avatarSprites = {}, avatarImages = {};

function preloadAvatarSprites(urls) {
  avatarSprites = urls; avatarImages = {};
  for (const [k, url] of Object.entries(urls)) {
    const img = new window.Image(); img.src = url; avatarImages[k] = img;
  }
}

function updateAvatarFrame() {
  const now = Date.now();
  if (!avatarIsBlinking && now >= avatarNextBlink) { avatarIsBlinking = true; avatarBlinkEnd = now + 400; }
  if (avatarIsBlinking && now >= avatarBlinkEnd) { avatarIsBlinking = false; avatarNextBlink = now + 3000 + Math.random() * 1000; }
  let key;
  if (avatarIsTalking) {
    key = avatarIsBlinking ? 'talking_closed' : (Math.random() < 0.7 ? 'talking_open' : 'nottalking_open');
  } else {
    key = avatarIsBlinking ? 'nottalking_closed' : 'nottalking_open';
  }
  const el = $('backgroundImage');
  if (el && avatarSprites[key]) el.src = avatarSprites[key];
}
setInterval(updateAvatarFrame, 100);

fetch('/get_ip').then(r => r.json()).then(d => { talkingheadBaseUrl = d.talkinghead_base_url; }).catch(() => {});
fetch('/avatar_sprites').then(r => r.json()).then(d => {
  preloadAvatarSprites(d);
  if (d.nottalking_open) $('backgroundImage').src = d.nottalking_open;
}).catch(() => {});


// ── AUDIO ───────────────────────────────────────────────────────────────────
let isMuted = false;

function start_talking() { if (!isMuted) avatarIsTalking = true; }
function stop_talking()  { avatarIsTalking = false; }

document.addEventListener('DOMContentLoaded', function () {
  const audioPlayer = $('audioPlayer');
  const muteBtn = $('muteButton');

  muteBtn.addEventListener('click', function () {
    const icon = this.querySelector('i');
    if (isMuted) {
      audioPlayer.muted = false;
      icon.className = 'bi bi-volume-up-fill';
      if (!audioPlayer.paused) start_talking();
    } else {
      audioPlayer.muted = true;
      icon.className = 'bi bi-volume-mute-fill';
      stop_talking();
    }
    isMuted = !isMuted;
  });
});

const audioPlayer = $('audioPlayer');
if (audioPlayer) audioPlayer.addEventListener('ended', stop_talking);

let audioStarted = false;

function startAudioStream() {
  if (audioStarted) return;
  audioStarted = true;
  fetch('/audio_stream').then(r => r.blob()).then(blob => {
    if (!blob.size) return;
    const url = URL.createObjectURL(blob);
    audioPlayer.src = url; audioPlayer.load();
    audioPlayer.play().then(() => {
      start_talking();
      audioPlayer.onended = () => setTimeout(playNextAudioChunk, 500);
    }).catch(console.error);
  }).catch(console.error);
}

function playNextAudioChunk() {
  fetch('/get_next_audio_chunk').then(r => {
    if (r.status === 204) { stop_talking(); audioStarted = false; return null; }
    return r.blob();
  }).then(blob => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    audioPlayer.src = url; audioPlayer.load();
    audioPlayer.play().then(() => {
      start_talking();
      audioPlayer.onended = () => setTimeout(playNextAudioChunk, 500);
    });
  }).catch(console.error);
}


// ── CHAT ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  let selectedImageFile = null;

  // Image upload
  $('uploadImageButton').addEventListener('click', () => $('imageUpload').click());
  $('imageUpload').addEventListener('change', function () {
    const f = this.files[0];
    if (!f) return;
    selectedImageFile = f;
    const reader = new FileReader();
    reader.onload = e => {
      $('imagePreview').src = e.target.result;
      $('imagePreviewContainer').style.display = 'block';
    };
    reader.readAsDataURL(f);
  });
  $('removeImageButton').addEventListener('click', () => {
    selectedImageFile = null;
    $('imagePreviewContainer').style.display = 'none';
    $('imagePreview').src = '';
  });

  // Socket.IO
  const socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
  socket.on('bot_message',    d => displayBotMessage(d.message));
  socket.on('user_message',   d => displayUserMessage(d.message));
  socket.on('talking_state',  d => { avatarIsTalking = d.talking; });
  socket.on('emotion_change', d => preloadAvatarSprites(d));

  // Connection status indicator
  const connDot = document.getElementById('connDot');
  socket.on('connect', () => {
    if (connDot) { connDot.className = 'conn-dot'; }
  });
  socket.on('disconnect', () => {
    if (connDot) { connDot.className = 'conn-dot disconnected'; }
    if (window.showToast) showToast('Connection lost — reconnecting...', 'error');
    setTimeout(() => {
      if (connDot) connDot.className = 'conn-dot reconnecting';
      socket.connect();
    }, 2000);
  });
  socket.on('reconnect_attempt', () => {
    if (connDot) { connDot.className = 'conn-dot reconnecting'; }
  });

  function formatText(text) {
    if (!text) return '';
    return text
      .replace(/\n/g, '<br>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/``(.*?)``/g, '<code>$1</code>')
      .replace(/\\u([\dA-F]{4})/gi, (m, g) => String.fromCharCode(parseInt(g, 16)));
  }

  const prompt   = $('prompt');
  const sendBtn  = $('button-addon2');

  function sendMessage() {
    const txt = prompt.value.trim();
    if (!txt && !selectedImageFile) return;
    displayUserMessage(txt, selectedImageFile);
    sendUserMessage(txt, selectedImageFile);
    prompt.value = '';
    selectedImageFile = null;
    $('imagePreviewContainer').style.display = 'none';
    $('imagePreview').src = '';
    // show typing indicator after 1s
    setTimeout(() => displayBotMessage('', true), 1000);
  }

  if (sendBtn) sendBtn.addEventListener('click', sendMessage);
  if (prompt)  prompt.addEventListener('keyup', e => { if (e.key === 'Enter') sendMessage(); });

  function sendUserMessage(message, file) {
    const fd = new FormData();
    fd.append('message', message);
    if (file) fd.append('file', file);
    fetch('/process_llm', { method: 'POST', body: fd }).catch(console.error);
  }

  function displayBotMessage(message, isTyping = false) {
    const chatBody = document.querySelector('.chat-messages');
    const row = document.createElement('div');
    row.className = 'msg-row msg-bot';

    if (!isTyping) {
      removeTypingMessage();
      row.innerHTML = `<div class="msg-bubble msg-bubble-bot">
        <div class="response-text">${formatText(message)}</div>
      </div>`;
    } else {
      row.classList.add('is-typing');
      row.innerHTML = `<div class="msg-bubble msg-bubble-bot">
        <div class="typing-indicator"><span></span><span></span><span></span></div>
      </div>`;
    }

    chatBody.appendChild(row);
    chatBody.scrollTop = chatBody.scrollHeight;
    if (!isTyping) startAudioStream();
  }

  function removeTypingMessage() {
    document.querySelectorAll('.is-typing').forEach(el => el.remove());
  }

  function displayUserMessage(message, imageFile) {
    const chatBody = document.querySelector('.chat-messages');
    const row = document.createElement('div');
    row.className = 'msg-row msg-row-user';
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble msg-bubble-user';
    if (message) bubble.innerHTML = `<div class="response-text">${formatText(message)}</div>`;
    row.appendChild(bubble);
    chatBody.appendChild(row);
    chatBody.scrollTop = chatBody.scrollHeight;

    if (imageFile) {
      const reader = new FileReader();
      reader.onload = function (e) {
        const img = document.createElement('img');
        img.src = e.target.result;
        img.style.maxWidth = '200px';
        img.style.borderRadius = 'var(--radius)';
        img.style.marginTop = '6px';
        bubble.insertBefore(img, bubble.firstChild);
        chatBody.scrollTop = chatBody.scrollHeight;
      };
      reader.readAsDataURL(imageFile);
    }
  }

  // set char name from APP_CONFIG
  const nameEl = document.getElementById('bot-name');
  if (nameEl && window.APP_CONFIG?.charName) nameEl.textContent = window.APP_CONFIG.charName;

  // Avatar toggle — click to collapse/expand
  const avatarHeader = document.querySelector('.avatar-header');
  if (avatarHeader) {
    if (localStorage.getItem('avatarHidden') === '1') avatarHeader.classList.add('collapsed');
    avatarHeader.addEventListener('click', () => {
      avatarHeader.classList.toggle('collapsed');
      localStorage.setItem('avatarHidden', avatarHeader.classList.contains('collapsed') ? '1' : '0');
    });
  }
});


// ── ARMS ────────────────────────────────────────────────────────────────────
function updateArmConstraints() {
  const armTab = $('arms');
  const vals   = armTab.querySelectorAll('.servo-val');
  const leftMain = parseInt($('leftMain').value);
  const lfSlider = $('leftForearm'), lhSlider = $('leftHand');
  let maxLF = leftMain <= 50 ? Math.max(1, Math.round(leftMain / 2)) : Math.round(25 + (leftMain - 50) * 1.5);
  if (parseInt(lfSlider.value) > maxLF) { lfSlider.value = maxLF; vals[1].textContent = maxLF; }
  updateSliderGauge(lfSlider, maxLF);
  let maxLH = parseInt(lfSlider.value) <= 50 ? Math.max(1, Math.round(parseInt(lfSlider.value) / 2)) : Math.round(25 + (parseInt(lfSlider.value) - 50) * 1.5);
  if (parseInt(lhSlider.value) > maxLH) { lhSlider.value = maxLH; vals[2].textContent = maxLH; }
  updateSliderGauge(lhSlider, maxLH);
  const rightMain = parseInt($('rightMain').value);
  const rfSlider = $('rightForearm'), rhSlider = $('rightHand');
  let maxRF = rightMain <= 50 ? Math.max(1, Math.round(rightMain / 2)) : Math.round(25 + (rightMain - 50) * 1.5);
  if (parseInt(rfSlider.value) > maxRF) { rfSlider.value = maxRF; vals[4].textContent = maxRF; }
  updateSliderGauge(rfSlider, maxRF);
  let maxRH = parseInt(rfSlider.value) <= 50 ? Math.max(1, Math.round(parseInt(rfSlider.value) / 2)) : Math.round(25 + (parseInt(rfSlider.value) - 50) * 1.5);
  if (parseInt(rhSlider.value) > maxRH) { rhSlider.value = maxRH; vals[5].textContent = maxRH; }
  updateSliderGauge(rhSlider, maxRH);
}

function updateSliderGauge(slider, maxAllowed) {
  const pct = maxAllowed;
  slider.style.background = `linear-gradient(to top,rgba(0,229,255,.3) 0%,rgba(0,229,255,.3) ${pct}%,rgba(220,53,69,.3) ${pct}%,rgba(220,53,69,.3) 100%)`;
}

function updateArmValueDisplay(slider, i) {
  $('arms').querySelectorAll('.servo-val')[i].textContent = slider.value;
}

function resetArmServo(id, i) {
  $(id).value = 1;
  $('arms').querySelectorAll('.servo-val')[i].textContent = '1';
  updateArmConstraints();
}

function applyArmControls() {
  fetch('/move_arms', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      left_main: +$('leftMain').value, left_forearm: +$('leftForearm').value,
      left_hand: +$('leftHand').value, right_main: +$('rightMain').value,
      right_forearm: +$('rightForearm').value, right_hand: +$('rightHand').value,
      speed: +$('armSpeedSlider').value
    })
  }).catch(console.error);
}

function resetAllArms() {
  fetch('/move_arms', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ left_main:1, left_forearm:1, left_hand:1, right_main:1, right_forearm:1, right_hand:1, speed:0.75 })
  }).then(() => {
    ['leftMain','leftForearm','leftHand','rightMain','rightForearm','rightHand'].forEach(id => $(id).value = 1);
    $('arms').querySelectorAll('.servo-val').forEach(d => d.textContent = '1');
    updateArmConstraints();
    return fetch('/disable_servos', { method:'POST', headers:{'Content-Type':'application/json'} });
  }).then(() => fetch('/reset_positions', { method:'POST', headers:{'Content-Type':'application/json'} }))
    .then(() => fetch('/disable_servos', { method:'POST', headers:{'Content-Type':'application/json'} }))
    .catch(console.error);
}


// ── LEGS ────────────────────────────────────────────────────────────────────
function updateValueDisplay(slider, i) {
  document.querySelectorAll('.servo-val')[i].textContent = slider.value;
}

function resetServo(id, i) {
  $(id).value = 50;
  document.querySelectorAll('.servo-val')[i].textContent = '50';
}

function applyLegControls() {
  fetch('/move_legs', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      left_height:  +$('leftHeight').value,
      right_height: +$('rightHeight').value,
      left_leg:     +$('leftLeg').value,
      right_leg:    +$('rightLeg').value,
      speed:        +$('speedSlider').value
    })
  }).catch(console.error);
}

function resetAllLegs() {
  fetch('/neutral_legs', { method:'POST', headers:{'Content-Type':'application/json'} })
    .then(() => {
      ['leftHeight','rightHeight','leftLeg','rightLeg'].forEach(id => $(id).value = 50);
      $('legs').querySelectorAll('.servo-val').forEach(d => d.textContent = '50');
      return fetch('/reset_positions', { method:'POST', headers:{'Content-Type':'application/json'} });
    }).catch(console.error);
}


// ── MOTION D-PAD ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const btnUp = $('btnUp'), btnDown = $('btnDown'),
        btnLeft = $('btnLeft'), btnRight = $('btnRight');

  function getSpeed() { const r = document.querySelector('input[name="speed"]:checked'); return r ? r.value : 'fast'; }
  function move(dir) {
    fetch('/robot_move', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ direction: dir })
    }).catch(console.error);
  }

  btnUp.addEventListener('click',    () => move(getSpeed() === 'fast' ? 'forward'  : 'forward_slow'));
  btnDown.addEventListener('click',  () => move(getSpeed() === 'fast' ? 'backward' : 'backward_slow'));
  btnLeft.addEventListener('click',  () => move(getSpeed() === 'fast' ? 'left'     : 'left_slow'));
  btnRight.addEventListener('click', () => move(getSpeed() === 'fast' ? 'right'    : 'right_slow'));
});

function loadMovements() {
  fetch('/get_movements').then(r => r.json()).then(data => {
    if (!data.success) return;
    const sel = $('actionSelect');
    sel.innerHTML = '';
    const reset = document.createElement('option');
    reset.value = 'reset_positions'; reset.textContent = 'Reset Position';
    sel.appendChild(reset);
    ['legs_only','has_arms'].forEach((group, gi) => {
      if (data[group]?.length) {
        const g = document.createElement('optgroup');
        g.label = gi === 0 ? '── Legs Only ──' : '── With Arms ──';
        data[group].forEach(m => {
          const o = document.createElement('option'); o.value = m.id; o.textContent = m.name;
          g.appendChild(o);
        });
        sel.appendChild(g);
      }
    });
  }).catch(console.error);
}
document.addEventListener('DOMContentLoaded', loadMovements);

function executeAction() {
  fetch('/execute_action', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action: $('actionSelect').value })
  }).catch(console.error);
}


// ── CONFIG ──────────────────────────────────────────────────────────────────
(function () {
  // helpers
  window.detectArrayValue = function (value) {
    if (typeof value !== 'string') return { isArray:false, type:null, items:[] };
    const t = value.trim();
    if (t.startsWith('[') && t.endsWith(']')) {
      try { const p = JSON.parse(t); if (Array.isArray(p)) return { isArray:true, type:'json', items:p }; } catch {}
      const inner = t.slice(1,-1).trim();
      if (inner.includes(',')) {
        const items = parseCsvQuoted(inner);
        if (items.length > 1) return { isArray:true, type:'json', items };
      }
    }
    if (!t.startsWith('[') && !t.startsWith('http') && t.includes(',')) {
      const items = t.split(',').map(i => i.trim()).filter(Boolean);
      if (items.length > 1) return { isArray:true, type:'csv', items };
    }
    return { isArray:false, type:null, items:[] };
  };

  function parseCsvQuoted(str) {
    const items = []; let cur = '', inQ = false, qc = null;
    for (const ch of str) {
      if ((ch==='"'||ch==="'") && !inQ) { inQ=true; qc=ch; }
      else if (ch===qc && inQ) { inQ=false; qc=null; }
      else if (ch===',' && !inQ) { const t=cur.trim().replace(/^['"]/,'').replace(/['"]$/,''); if(t) items.push(t); cur=''; }
      else cur+=ch;
    }
    const t=cur.trim().replace(/^['"]/,'').replace(/['"]$/,''); if(t) items.push(t);
    return items;
  }

  function arrToVal(items, type) { return type==='json' ? JSON.stringify(items) : items.join(','); }
  function esc(t)  { const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }
  function escAttr(s) { return s.replace(/'/g,"&#39;"); }

  function tagInputHtml(fid, sec, key, items, arrType) {
    const tags = items.map((it,i) =>
      `<span class="config-tag" data-index="${i}">
         <span class="config-tag-text">${esc(String(it))}</span>
         <button type="button" class="config-tag-remove" data-index="${i}">×</button>
       </span>`).join('');
    return `<div class="config-tag-input-container" id="${fid}" data-section="${sec}" data-key="${key}" data-array-type="${arrType}">
      <div class="config-tags-wrapper">${tags}<input type="text" class="config-tag-input" placeholder="Type + Enter…"/></div>
      <input type="hidden" class="config-array-value" value='${escAttr(JSON.stringify(items))}'/></div>`;
  }

  function screensaverHtml(fid, sec, key, cur, options) {
    let sel = [];
    if (typeof cur==='string') { const t=cur.trim().toLowerCase(); sel = t==='random'?['random']:(t?cur.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean):[]); }
    const opts = options.map(opt => {
      const isRand=opt.toLowerCase()==='random', isSel=sel.includes(opt.toLowerCase());
      return `<span class="screensaver-option${isSel?' selected':''}${isRand?' random-option':''}" data-value="${opt}">${isRand?'<i class="bi bi-shuffle" style="font-size:10px;margin-right:3px;"></i>':''}${opt}</span>`;
    }).join('');
    return `<div class="screensaver-select-container" id="${fid}" data-section="${sec}" data-key="${key}">
      <div class="screensaver-select-options">${opts}</div>
      <input type="hidden" class="screensaver-select-value" value="${esc(cur)}"/></div>`;
  }

  function initScreensaverSelects() {
    document.querySelectorAll('.screensaver-select-container').forEach(cont => {
      const hidden = cont.querySelector('.screensaver-select-value');
      const wrapper = cont.querySelector('.screensaver-select-options');
      function getSel() { const v=hidden.value.trim().toLowerCase(); return v==='random'?['random']:(v?v.split(',').map(s=>s.trim()).filter(Boolean):[]); }
      function setSel(items) {
        if (!items.length || items.includes('random')) { hidden.value='random'; items=['random']; }
        else hidden.value=items.join(',');
        wrapper.querySelectorAll('.screensaver-option').forEach(o => o.classList.toggle('selected', items.includes(o.dataset.value.toLowerCase())));
      }
      wrapper.querySelectorAll('.screensaver-option').forEach(opt => {
        opt.addEventListener('click', function () {
          const cv=this.dataset.value.toLowerCase(), isRand=cv==='random';
          let sel=getSel();
          if (isRand) { if(!sel.includes('random')) setSel(['random']); }
          else { if(sel.includes(cv)) { sel=sel.filter(s=>s!==cv); setSel(sel.length?sel:['random']); } else { sel=sel.filter(s=>s!=='random'); sel.push(cv); setSel(sel); } }
        });
      });
    });
  }

  function initTagInputs() {
    document.querySelectorAll('.config-tag-input-container').forEach(cont => {
      const input=cont.querySelector('.config-tag-input'), wrapper=cont.querySelector('.config-tags-wrapper'), hidden=cont.querySelector('.config-array-value');
      const isScr = cont.dataset.section==='UI' && cont.dataset.key==='screensaver_list';
      function getItems() { try { return JSON.parse(hidden.value)||[]; } catch { return []; } }
      function setItems(items) { hidden.value=JSON.stringify(items); render(); }
      function render() {
        wrapper.querySelectorAll('.config-tag').forEach(t=>t.remove());
        const html = getItems().map((it,i) =>
          `<span class="config-tag"><span class="config-tag-text">${esc(String(it))}</span>
           <button type="button" class="config-tag-remove" data-index="${i}">×</button></span>`).join('');
        input.insertAdjacentHTML('beforebegin', html);
        wrapper.querySelectorAll('.config-tag-remove').forEach(btn => {
          btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); const it=getItems(); it.splice(+btn.dataset.index,1); setItems(it); });
        });
      }
      function addItem(text) {
        const t=text.trim(); if(!t) return;
        let items=getItems();
        if (isScr) { if(t.toLowerCase()==='random') items=['random']; else { items=items.filter(i=>i.toLowerCase()!=='random'); if(!items.includes(t)) items.push(t); } }
        else { if(!items.includes(t)) items.push(t); }
        setItems(items); input.value='';
      }
      input.addEventListener('keydown', e => {
        if (e.key==='Enter') { e.preventDefault(); addItem(input.value); }
        else if (e.key==='Backspace' && !input.value) { const it=getItems(); if(it.length){it.pop();setItems(it);} }
      });
      input.addEventListener('paste', e => {
        e.preventDefault();
        const pasted=(e.clipboardData||window.clipboardData).getData('text');
        const newItems=pasted.split(/[,\n]/).map(s=>s.trim()).filter(Boolean);
        if (newItems.length) {
          let items=getItems();
          if (isScr) { if(newItems.some(i=>i.toLowerCase()==='random')) items=['random']; else { items=items.filter(i=>i.toLowerCase()!=='random'); newItems.forEach(i=>{if(!items.includes(i))items.push(i);}); } }
          else newItems.forEach(i=>{if(!items.includes(i))items.push(i);});
          setItems(items);
        }
      });
      cont.addEventListener('click', e => { if(e.target===cont||e.target===wrapper) input.focus(); });
      wrapper.querySelectorAll('.config-tag-remove').forEach(btn => {
        btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); const it=getItems(); it.splice(+btn.dataset.index,1); setItems(it); });
      });
    });
  }

  function loadConfiguration() {
    fetch('/get_config').then(r=>r.json()).then(data => {
      const form = $('configForm');
      let html = '<div class="accordion" id="configAccordion">';
      let si = 0;
      for (const [section, fields] of Object.entries(data.config)) {
        const desc = data.field_options[`${section}.__section__`];
        const accId = `collapse${si}`, first = si===0;
        html += `<div class="accordion-item config-accordion-item">
          <h2 class="accordion-header"><button class="accordion-button config-accordion-button${first?'':' collapsed'}" type="button" data-bs-toggle="collapse" data-bs-target="#${accId}" aria-expanded="${first}">
            <i class="bi bi-folder-fill me-2"></i><span class="fw-bold">${section}</span>
            ${desc?`<small class="ms-2 text-muted opacity-75">– ${desc.description||desc}</small>`:''}
          </button></h2>
          <div id="${accId}" class="accordion-collapse collapse${first?' show':''}" data-bs-parent="#configAccordion">
            <div class="accordion-body config-accordion-body"><div class="row g-2">`;

        for (const [key, value] of Object.entries(fields)) {
          const fid = `cfg_${section}_${key}`, fi = data.field_options[`${section}.${key}`], desc2 = fi?.description||'';
          html += `<div class="col-md-6 col-lg-4"><div class="field-wrapper">
            <label for="${fid}" class="form-label d-flex align-items-center gap-1"><span>${key}</span>`;

          if (fi?.type==='screensaver_select') {
            html += `</label>${screensaverHtml(fid,section,key,value,fi.options||[])}`;
          } else if (fi?.options) {
            html += `</label><select class="form-select form-select-sm config-input" id="${fid}" data-section="${section}" data-key="${key}">`;
            fi.options.forEach(opt => { html += `<option value="${opt}"${String(value)===String(opt)?' selected':''}>${opt}</option>`; });
            html += '</select>';
          } else if (typeof value==='boolean'||['True','False','true','false'].includes(value)) {
            const chk = (value===true||value==='True'||value==='true') ? 'checked' : '';
            html += `</label><div class="form-check form-switch mt-1"><input class="form-check-input config-toggle" type="checkbox" id="${fid}" data-section="${section}" data-key="${key}" ${chk}><label class="form-check-label small" for="${fid}">${chk?'Enabled':'Disabled'}</label></div>`;
          } else {
            const arrInfo = detectArrayValue(value);
            if ((fi?.type==='array') || arrInfo.isArray) {
              const items = arrInfo.isArray ? arrInfo.items : (value?[value]:[]);
              html = html.replace(`<span>${key}</span>`,`<span>${key}</span><span class="config-array-badge">${arrInfo.type==='json'?'JSON':'LIST'}</span>`);
              html += `</label>${tagInputHtml(fid,section,key,items,arrInfo.type||'csv')}`;
            } else {
              html += `</label><input type="text" class="form-control form-control-sm config-input" id="${fid}" data-section="${section}" data-key="${key}" value="${esc(String(value))}">`;
            }
          }

          if (desc2) html += `<div class="config-hint mt-1"><i class="bi bi-info-circle"></i><small>${desc2}</small></div>`;
          html += '</div></div>';
        }
        html += '</div></div></div></div>';
        si++;
      }
      html += '</div>';
      form.innerHTML = html;

      document.querySelectorAll('.config-toggle').forEach(t => {
        t.addEventListener('change', function () {
          const lbl = this.parentElement.querySelector('.form-check-label');
          if (lbl) lbl.textContent = this.checked ? 'Enabled' : 'Disabled';
        });
      });
      initTagInputs(); initScreensaverSelects();
    }).catch(err => {
      $('configForm').innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle me-2"></i>Error: ${err.message}</div>`;
    });
  }

  function saveConfiguration() {
    const saveBtn = $('saveConfigBtn');
    if (saveBtn.disabled) return;
    const data = {};
    document.querySelectorAll('#configForm input, #configForm select').forEach(inp => {
      if (['config-array-value','config-tag-input','screensaver-select-value'].some(c => inp.classList.contains(c))) return;
      const sec=inp.getAttribute('data-section'), key=inp.getAttribute('data-key');
      if (!sec||!key) return;
      if (!data[sec]) data[sec]={};
      data[sec][key] = inp.type==='checkbox' ? inp.checked : inp.value;
    });
    document.querySelectorAll('.config-tag-input-container').forEach(c => {
      const sec=c.dataset.section, key=c.dataset.key, type=c.dataset.arrayType;
      if (!data[sec]) data[sec]={};
      try { data[sec][key]=arrToVal(JSON.parse(c.querySelector('.config-array-value').value)||[],type); } catch { data[sec][key]=''; }
    });
    document.querySelectorAll('.screensaver-select-container').forEach(c => {
      const sec=c.dataset.section, key=c.dataset.key;
      if (!data[sec]) data[sec]={};
      data[sec][key] = c.querySelector('.screensaver-select-value').value;
    });

    const origHtml=saveBtn.innerHTML, origClass=saveBtn.className;
    saveBtn.innerHTML='<i class="bi bi-arrow-clockwise spin"></i> Saving…'; saveBtn.disabled=true;

    fetch('/save_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
      .then(r=>r.json()).then(d => {
        if (d.success) {
          saveBtn.innerHTML='<i class="bi bi-check-circle-fill"></i> Saved!';
          saveBtn.classList.add('hud-btn-success');
          if (window.showToast) showToast('Configuration saved', 'success');
          setTimeout(()=>{ saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false; },2000);
        } else { saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false; if (window.showToast) showToast('Error: '+(d.error||'Unknown'), 'error'); }
      }).catch(err=>{ saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false; alert('Error: '+err.message); });
  }

  const configTab = $('config-tab');
  if (configTab) configTab.addEventListener('shown.bs.tab', () => {
    if ($('configForm').innerHTML.includes('Loading')) loadConfiguration();
  });

  const saveBtn = $('saveConfigBtn');
  if (saveBtn) saveBtn.addEventListener('click', e => { e.preventDefault(); saveConfiguration(); });
})();


// ── TAB RESET LOGIC ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const legsTab = $('legs-tab'), armsTab = $('arms-tab');

  if (legsTab) legsTab.addEventListener('hide.bs.tab', () => {
    const lh=+$('leftHeight').value, rh=+$('rightHeight').value,
          ll=+$('leftLeg').value,    rl=+$('rightLeg').value;
    if (lh!==50||rh!==50||ll!==50||rl!==50) resetAllLegs();
  });

  if (armsTab) armsTab.addEventListener('hide.bs.tab', () => {
    const lm=+$('leftMain').value, lf=+$('leftForearm').value, lh=+$('leftHand').value,
          rm=+$('rightMain').value, rf=+$('rightForearm').value, rh=+$('rightHand').value;
    if (lm!==1||lf!==1||lh!==1||rm!==1||rf!==1||rh!==1) resetAllArms();
  });

  document.querySelectorAll('.custom-tab').forEach(tab => {
    tab.addEventListener('shown.bs.tab', e => {
      const id = e.target.getAttribute('data-bs-target')?.replace('#','');
      if (id==='legs'||id==='arms') {
        fetch('/reset_positions',{method:'POST',headers:{'Content-Type':'application/json'}}).catch(()=>{});
      }
    });
  });
});


// ── FULLSCREEN ───────────────────────────────────────────────────────────────
window.toggleFullscreen = function () {
  const icon = $('fullscreen-icon');
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
      .then(()=>icon.className='bi bi-fullscreen-exit')
      .catch(console.log);
  } else {
    document.exitFullscreen()
      .then(()=>icon.className='bi bi-fullscreen');
  }
};

document.addEventListener('fullscreenchange', () => {
  const icon = $('fullscreen-icon');
  if (icon) icon.className = document.fullscreenElement ? 'bi bi-fullscreen-exit' : 'bi bi-fullscreen';
});


// ── TOAST NOTIFICATIONS ──────────────────────────────────────────────────────
window.showToast = function (message, type, duration) {
  type = type || 'info';
  duration = duration || 3000;
  var container = document.getElementById('toastContainer');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast-msg toast-' + type;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(function () {
    toast.classList.add('toast-out');
    toast.addEventListener('animationend', function () { toast.remove(); });
  }, duration);
};


// ── NEXUS DASHBOARD ──────────────────────────────────────────────────────────
(function () {
  var nexusActive = false;
  var moodHistory = [];   // [{emotion, timestamp}] — last 50 entries
  var consoleLines = [];  // rolling buffer of console strings
  var MAX_CONSOLE = 80;
  var pollInterval = null;

  // Emotion → color mapping
  var EMOTION_COLORS = {
    neutral: '#00e5ff', happy: '#39ff14', sad: '#4488ff', angry: '#ff4444',
    excited: '#ffb700', afraid: '#ff00ff', sleepy: '#3d5a6e',
    curious: '#00e5ff', love: '#ff69b4', surprise: '#ffcc00'
  };

  function formatUptime(secs) {
    var d = Math.floor(secs / 86400);
    var h = Math.floor((secs % 86400) / 3600);
    var m = Math.floor((secs % 3600) / 60);
    if (d > 0) return d + 'd ' + h + 'h ' + m + 'm';
    if (h > 0) return h + 'h ' + m + 'm';
    return m + 'm';
  }

  function consolePush(msg) {
    consoleLines.push(msg);
    if (consoleLines.length > MAX_CONSOLE) consoleLines.shift();
    var el = document.getElementById('nxConsole');
    if (!el) return;
    el.innerHTML = consoleLines.map(function (l) {
      return '<div class="nexus-console-line">' + l + '</div>';
    }).join('');
    el.scrollTop = el.scrollHeight;
  }

  function updateMetrics(data) {
    var cpuEl = document.getElementById('nxCpu');
    var ramEl = document.getElementById('nxRam');
    var tempEl = document.getElementById('nxTemp');
    var cpuBar = document.getElementById('nxCpuBar');
    var ramBar = document.getElementById('nxRamBar');
    var tempBar = document.getElementById('nxTempBar');

    if (cpuEl)  cpuEl.textContent = data.cpu_load + '%';
    if (ramEl)  ramEl.textContent = data.ram_usage + '%';
    if (tempEl) tempEl.textContent = data.cpu_temp + '°C';
    if (cpuBar) cpuBar.style.width = Math.min(data.cpu_load, 100) + '%';
    if (ramBar) ramBar.style.width = Math.min(data.ram_usage, 100) + '%';
    if (tempBar) tempBar.style.width = Math.min((data.cpu_temp / 85) * 100, 100) + '%';

    // State badge
    var stateText = document.getElementById('nxStateText');
    if (stateText) stateText.textContent = (data.emotion || 'neutral').toUpperCase();

    // System info
    var charEl = document.getElementById('nxCharName');
    if (charEl) charEl.textContent = data.character || '--';

    var uptimeEl = document.getElementById('nxUptime');
    if (uptimeEl) uptimeEl.textContent = formatUptime(data.uptime_secs || 0);

    // Battery
    var battEl = document.getElementById('nxBattery');
    if (battEl && data.battery) {
      var pct = Math.round(data.battery.percentage || 0);
      var icon = data.battery.charging ? '⚡' : '';
      battEl.textContent = pct + '% ' + icon + (data.battery.voltage ? ' (' + data.battery.voltage.toFixed(1) + 'V)' : '');
    } else if (battEl) {
      battEl.textContent = 'N/A';
    }

    // Console log entry
    consolePush('&gt; [TARS_CORE] CPU: ' + data.cpu_load + '% | RAM: ' + data.ram_usage + '% | ' + data.cpu_temp + '°C | State: ' + (data.emotion || 'neutral'));

    // Track mood history
    var emo = (data.emotion || 'neutral').toLowerCase();
    var last = moodHistory.length ? moodHistory[moodHistory.length - 1].emotion : null;
    if (emo !== last || moodHistory.length === 0) {
      moodHistory.push({ emotion: emo, timestamp: Date.now() });
      if (moodHistory.length > 50) moodHistory.shift();
      updateMoodTags(emo);
    }

    drawMoodChart();
  }

  function updateMoodTags(current) {
    var container = document.getElementById('nxMoodTags');
    if (!container) return;
    // collect unique recent emotions
    var seen = {};
    var tags = [];
    for (var i = moodHistory.length - 1; i >= 0 && tags.length < 5; i--) {
      var e = moodHistory[i].emotion;
      if (!seen[e]) { seen[e] = true; tags.unshift(e); }
    }
    container.innerHTML = tags.map(function (e) {
      return '<span class="nexus-mood-tag' + (e === current ? ' active' : '') + '">' + e.toUpperCase() + '</span>';
    }).join('');
  }

  function drawMoodChart() {
    var canvas = document.getElementById('nxMoodCanvas');
    if (!canvas || moodHistory.length < 2) return;
    var ctx = canvas.getContext('2d');
    var w = canvas.width = canvas.offsetWidth * (window.devicePixelRatio > 1 ? 2 : 1);
    var h = canvas.height = canvas.offsetHeight * (window.devicePixelRatio > 1 ? 2 : 1);
    ctx.clearRect(0, 0, w, h);

    // map emotion to a numeric value for charting
    var EMOTION_VALUES = {
      angry: 0, afraid: 0.15, sad: 0.25, sleepy: 0.35,
      neutral: 0.5, curious: 0.6, happy: 0.75, love: 0.8,
      excited: 0.9, surprise: 0.85
    };

    var points = moodHistory.map(function (m) {
      return EMOTION_VALUES[m.emotion] !== undefined ? EMOTION_VALUES[m.emotion] : 0.5;
    });

    var padding = 10;
    var graphW = w - padding * 2;
    var graphH = h - padding * 2;

    // draw subtle grid lines
    ctx.strokeStyle = 'rgba(0,229,255,0.06)';
    ctx.lineWidth = 1;
    for (var gy = 0; gy <= 4; gy++) {
      var y = padding + (gy / 4) * graphH;
      ctx.beginPath(); ctx.moveTo(padding, y); ctx.lineTo(w - padding, y); ctx.stroke();
    }

    // draw line
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(0,229,255,0.7)';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    for (var i = 0; i < points.length; i++) {
      var x = padding + (i / (points.length - 1)) * graphW;
      var y2 = padding + (1 - points[i]) * graphH;
      if (i === 0) ctx.moveTo(x, y2);
      else ctx.lineTo(x, y2);
    }
    ctx.stroke();

    // glow fill under line
    var grad = ctx.createLinearGradient(0, padding, 0, h - padding);
    grad.addColorStop(0, 'rgba(0,229,255,0.12)');
    grad.addColorStop(1, 'rgba(0,229,255,0)');
    ctx.lineTo(w - padding, h - padding);
    ctx.lineTo(padding, h - padding);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // draw dots on data points
    for (var j = 0; j < points.length; j++) {
      var px = padding + (j / (points.length - 1)) * graphW;
      var py = padding + (1 - points[j]) * graphH;
      var emo2 = moodHistory[j].emotion;
      ctx.beginPath();
      ctx.arc(px, py, 3, 0, Math.PI * 2);
      ctx.fillStyle = EMOTION_COLORS[emo2] || 'var(--cyan)';
      ctx.fill();
    }
  }

  function fetchMetrics() {
    fetch('/api/system/metrics')
      .then(function (r) { return r.json(); })
      .then(updateMetrics)
      .catch(function () {
        consolePush('&gt; [ERROR] Failed to fetch system metrics');
      });
  }

  function fetchMemoryStats() {
    fetch('/api/memory/stats')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var topicsEl = document.getElementById('nxTopics');
        var memEl = document.getElementById('nxMemories');
        if (topicsEl) topicsEl.textContent = data.topics || 0;
        if (memEl) memEl.textContent = data.memories || 0;
      })
      .catch(function () {});
  }

  // Start polling when nexus tab is shown
  document.addEventListener('DOMContentLoaded', function () {
    var nexusTab = document.getElementById('nexus-tab');
    if (!nexusTab) return;

    nexusTab.addEventListener('shown.bs.tab', function () {
      nexusActive = true;
      fetchMetrics();
      fetchMemoryStats();
      if (!pollInterval) {
        pollInterval = setInterval(function () {
          if (nexusActive) fetchMetrics();
        }, 5000); // poll every 5s
      }
    });

    nexusTab.addEventListener('hide.bs.tab', function () {
      nexusActive = false;
    });
  });
})();


// ── MOBILE SWIPE NAV ─────────────────────────────────────────────────────────
(function () {
  const TAB_IDS = ['chat', 'motion', 'legs', 'arms', 'nexus', 'config', 'wifi', 'emotions'];
  const TAB_BTN_IDS = ['chat-tab', 'motion-tab', 'legs-tab', 'arms-tab', 'nexus-tab', 'config-tab', 'wifi-tab', 'emotions-tab'];
  let currentIndex = 0;
  let isMobile = false;

  // mobile detection
  const mobileQuery = window.matchMedia('(max-width: 768px)');
  const landscapeQuery = window.matchMedia('(max-width: 900px) and (orientation: landscape) and (max-height: 500px)');

  function checkMobile() {
    isMobile = mobileQuery.matches || landscapeQuery.matches;
  }
  checkMobile();
  mobileQuery.addEventListener('change', checkMobile);
  landscapeQuery.addEventListener('change', checkMobile);

  // swipe state
  let touchStartX = 0, touchStartY = 0, touchDeltaX = 0;
  let direction = null; // null | 'horizontal' | 'vertical'
  let isSwiping = false;

  const SWIPE_THRESHOLD = 40;
  const DIRECTION_LOCK = 12; // px before locking direction

  document.addEventListener('DOMContentLoaded', function () {
    const track = document.getElementById('swipeTrack');
    const tabContent = document.getElementById('myTabContent');
    const navBtns = document.querySelectorAll('.mobile-nav-btn');

    if (!track || !tabContent) return;

    // ── Touch handlers ──
    tabContent.addEventListener('touchstart', function (e) {
      if (!isMobile) return;
      direction = null;
      isSwiping = false;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchDeltaX = 0;
      track.classList.remove('animating');
    }, { passive: true });

    tabContent.addEventListener('touchmove', function (e) {
      if (!isMobile) return;

      const dx = e.touches[0].clientX - touchStartX;
      const dy = e.touches[0].clientY - touchStartY;

      // lock direction after initial movement
      if (!direction) {
        if (Math.abs(dx) > DIRECTION_LOCK || Math.abs(dy) > DIRECTION_LOCK) {
          direction = Math.abs(dx) > Math.abs(dy) ? 'horizontal' : 'vertical';
        }
      }

      if (direction !== 'horizontal') return;

      // prevent vertical scroll while swiping horizontally
      e.preventDefault();
      isSwiping = true;

      touchDeltaX = dx;
      const baseOffset = -currentIndex * 100;

      // rubber-band at edges
      let pctDelta = (dx / tabContent.offsetWidth) * 100;
      if ((currentIndex === 0 && dx > 0) || (currentIndex === TAB_IDS.length - 1 && dx < 0)) {
        pctDelta *= 0.25; // resistance at bounds
      }

      track.style.transform = 'translateX(' + (baseOffset + pctDelta) + '%)';
    }, { passive: false });

    function onTouchFinish() {
      if (!isMobile || !isSwiping) return;
      isSwiping = false;

      let newIndex = currentIndex;

      if (Math.abs(touchDeltaX) > SWIPE_THRESHOLD) {
        if (touchDeltaX < 0 && currentIndex < TAB_IDS.length - 1) {
          newIndex = currentIndex + 1; // swipe left → next
        } else if (touchDeltaX > 0 && currentIndex > 0) {
          newIndex = currentIndex - 1; // swipe right → prev
        }
      }

      goToTab(newIndex, true);
    }

    tabContent.addEventListener('touchend', onTouchFinish);
    tabContent.addEventListener('touchcancel', onTouchFinish);

    // ── Mobile nav button clicks ──
    navBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        const idx = parseInt(this.getAttribute('data-tab-index'));
        if (!isNaN(idx)) goToTab(idx, true);
      });
    });

    // ── Core tab switching ──
    function goToTab(index, animated) {
      if (index < 0 || index >= TAB_IDS.length) return;

      const oldIndex = currentIndex;
      currentIndex = index;

      if (isMobile) {
        // animate swipe-track
        if (animated) {
          track.classList.add('animating');
          var onEnd = function () {
            track.classList.remove('animating');
            track.removeEventListener('transitionend', onEnd);
          };
          track.addEventListener('transitionend', onEnd);
        }
        track.style.transform = 'translateX(-' + (index * 100) + '%)';
      }

      // always trigger Bootstrap Tab for event compatibility
      var tabBtn = document.getElementById(TAB_BTN_IDS[index]);
      if (tabBtn && typeof bootstrap !== 'undefined') {
        new bootstrap.Tab(tabBtn).show();
      }

      // update mobile nav active state
      updateMobileNav(index);
      void(index);
    }

    function updateMobileNav(index) {
      navBtns.forEach(function (btn, i) {
        btn.classList.toggle('active', i === index);
        if (i === index) {
          btn.classList.remove('glow-pulse');
          // force reflow to restart animation
          void btn.offsetWidth;
          btn.classList.add('glow-pulse');
        }
      });
    }


    // ── Sync desktop tab clicks with swipe state ──
    document.querySelectorAll('.custom-tab[data-bs-toggle="tab"]').forEach(function (tab) {
      tab.addEventListener('shown.bs.tab', function () {
        var target = this.getAttribute('data-bs-target');
        if (!target) return;
        var tabId = target.replace('#', '');
        var idx = TAB_IDS.indexOf(tabId);
        if (idx !== -1 && idx !== currentIndex) {
          currentIndex = idx;
          if (isMobile) {
            track.style.transform = 'translateX(-' + (idx * 100) + '%)';
          }
          updateMobileNav(idx);
          void(idx);
        }
      });
    });

    // expose for other modules
    window.switchTab = goToTab;
    window.getCurrentTabIndex = function () { return currentIndex; };
  });
})();


// ── UTIL: shorthand getElementById ───────────────────────────────────────────
function $(id) { return document.getElementById(id); }
