/* ═══════════════════════════════════════════════════
   T.A.R.S. · MAIN JS
   Modules: wifi · emotions · avatar · chat · arms · legs · motion · config · ui
═══════════════════════════════════════════════════ */

'use strict';

// Forward debug logs to Python terminal via SocketIO (for phone testing)
// Batches messages to avoid "Too many packets in payload" SocketIO errors
let _dbgQueue = [];
let _dbgTimer = null;
function _dbg(...args) {
  const msg = args.join(' ');
  console.log(msg);
  _dbgQueue.push(msg);
  if (!_dbgTimer) {
    _dbgTimer = setTimeout(() => {
      _dbgTimer = null;
      const batch = _dbgQueue.splice(0);
      try { if (window.socket) window.socket.emit('client_debug', batch.join('\n')); } catch(e) {}
    }, 250);
  }
}

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
let isMuted = true;
let _audioUnlocked = false;

function start_talking() { if (!isMuted) avatarIsTalking = true; }
function stop_talking()  { avatarIsTalking = false; }

// Unlock the <audio> element on first user gesture.
// Chrome blocks play() on <audio> until a user gesture triggers play() at least once.
function _unlockAudioElement() {
  if (_audioUnlocked) return;
  _audioUnlocked = true;
  // Remove listeners now that we've had a user gesture — no need to keep firing
  document.removeEventListener('click', _unlockAudioElement);
  document.removeEventListener('touchend', _unlockAudioElement);
  document.removeEventListener('keydown', _unlockAudioElement);
  const el = $('audioPlayer');
  if (!el) return;
  const wav = new Uint8Array([
    0x52,0x49,0x46,0x46, 0x26,0x00,0x00,0x00, 0x57,0x41,0x56,0x45,
    0x66,0x6D,0x74,0x20, 0x10,0x00,0x00,0x00, 0x01,0x00,0x01,0x00,
    0x44,0xAC,0x00,0x00, 0x88,0x58,0x01,0x00, 0x02,0x00,0x10,0x00,
    0x64,0x61,0x74,0x61, 0x02,0x00,0x00,0x00, 0x00,0x00
  ]);
  const blob = new Blob([wav], { type: 'audio/wav' });
  const url = URL.createObjectURL(blob);
  el.muted = true;
  el.src = url;
  el.play().then(() => {
    _dbg('[AUDIO] Audio element unlocked');
    URL.revokeObjectURL(url);
    el.muted = isMuted;
    if (!_audioPlaying && _audioQueue.length) _playNextFromQueue();
  }).catch(e => {
    if (e.name !== 'AbortError') _audioUnlocked = false;
    URL.revokeObjectURL(url);
    _dbg('[AUDIO] Unlock:', e.name, e.message);
  });
}
document.addEventListener('click', _unlockAudioElement);
document.addEventListener('touchend', _unlockAudioElement);
document.addEventListener('keydown', _unlockAudioElement);

// Global audioPlayer reference (element exists in DOM before this script loads)
const audioPlayer = $('audioPlayer');
let audioStarted = false;

// ── Audio state ──
const _audioQueue = [];
let _audioPlaying = false;
let _audioDone = false;
// True while bot is generating/playing audio (from bot_stream_start to all audio done)
let _botResponding = false;
// Voice mode state — set by DOMContentLoaded closure, read by audio pipeline
let voiceActive = false;
// Mic control functions — assigned by DOMContentLoaded closure
let _micPause = function() {};
let _micRestart = function() {};

// Called when ALL bot audio finishes — restarts mic in voice mode
function _fireAllAudioDone() {
  _botResponding = false;
  stop_talking();
  _dbg('[AUDIO] All audio done | voiceActive:', voiceActive);
  if (voiceActive) _micRestart();
}

document.addEventListener('DOMContentLoaded', function () {
  const audioPlayer = $('audioPlayer');
  const muteBtn = $('muteButton');

  muteBtn.addEventListener('click', function () {
    const icon = this.querySelector('i');
    isMuted = !isMuted;
    audioPlayer.muted = isMuted;
    if (isMuted) {
      icon.className = 'bi bi-volume-mute-fill';
      stop_talking();
    } else {
      icon.className = 'bi bi-volume-up-fill';
      _unlockAudioElement();
      if (_audioPlaying) start_talking();
      if (!_audioPlaying && _audioQueue.length) _playNextFromQueue();
    }
  });

  audioPlayer.addEventListener('ended', stop_talking);

  // When phone app returns from background, reset stale audio state
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      if (_audioPlaying && audioPlayer.paused) {
        _dbg('[DEBUG] Page resumed with stale _audioPlaying flag — resetting');
        _audioPlaying = false;
        audioStarted = false;
        _playNextFromQueue();
      }
    }
  });
});

// Legacy full-response audio (used for image uploads / non-streaming paths)
function _legacyAudioDone() {
  stop_talking();
  audioStarted = false;
  _fireAllAudioDone();
}

function startAudioStream() {
  if (audioStarted) return;
  if (_audioQueue.length || _audioPlaying) return;
  audioStarted = true;
  fetch('/audio_stream').then(r => r.blob()).then(blob => {
    if (!blob.size) { _legacyAudioDone(); return; }
    const url = URL.createObjectURL(blob);
    audioPlayer.src = url; audioPlayer.load();
    audioPlayer.play().then(() => {
      start_talking();
      audioPlayer.onended = () => { URL.revokeObjectURL(url); setTimeout(playNextAudioChunk, 500); };
    }).catch(e => { console.error(e); _legacyAudioDone(); });
  }).catch(e => { console.error(e); _legacyAudioDone(); });
}

function playNextAudioChunk() {
  fetch('/get_next_audio_chunk').then(r => {
    if (r.status === 204) { _legacyAudioDone(); return null; }
    return r.blob();
  }).then(blob => {
    if (!blob || !blob.size) { _legacyAudioDone(); return; }
    const url = URL.createObjectURL(blob);
    audioPlayer.src = url; audioPlayer.load();
    audioPlayer.play().then(() => {
      start_talking();
      audioPlayer.onended = () => { URL.revokeObjectURL(url); setTimeout(playNextAudioChunk, 500); };
    }).catch(e => { console.error('Legacy chunk play failed:', e); _legacyAudioDone(); });
  }).catch(e => { console.error('Legacy chunk fetch failed:', e); _legacyAudioDone(); });
}

let _audioSafetyTimer = null;

function _playNextFromQueue() {
  if (!_audioUnlocked) {
    _dbg('[DEBUG] _playNextFromQueue → blocked (audioUnlocked=false) | queued:', _audioQueue.length);
    return;
  }
  if (_audioPlaying || !_audioQueue.length) {
    if (!_audioQueue.length && _audioDone) {
      _dbg('[DEBUG] _playNextFromQueue → queue drained + audioDone → firing _fireAllAudioDone');
      _audioDone = false;
      _fireAllAudioDone();
    }
    return;
  }
  _dbg('[DEBUG] _playNextFromQueue → playing chunk | queueLen:', _audioQueue.length);
  _audioPlaying = true;
  if (_audioSafetyTimer) clearTimeout(_audioSafetyTimer);
  const b64 = _audioQueue.shift();
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  audioPlayer.src = url;
  audioPlayer.load();
  audioPlayer.play().then(() => {
    start_talking();
    _audioSafetyTimer = setTimeout(() => {
      if (_audioPlaying && _audioSafetyTimer) {
        _dbg('[DEBUG] Audio safety timeout — forcing queue advance');
        _audioSafetyTimer = null;
        URL.revokeObjectURL(url);
        _audioPlaying = false;
        _playNextFromQueue();
      }
    }, 30000);

    function _advanceQueue() {
      if (!_audioPlaying) return;
      if (_audioSafetyTimer) { clearTimeout(_audioSafetyTimer); _audioSafetyTimer = null; }
      URL.revokeObjectURL(url);
      _audioPlaying = false;
      _dbg('[DEBUG] _advanceQueue → chunk done, queueLen:', _audioQueue.length, '| audioDone:', _audioDone);
      _playNextFromQueue();
    }

    audioPlayer.onended = () => { _dbg('[DEBUG] audioPlayer.onended fired'); _advanceQueue(); };
    audioPlayer.onerror = (e) => { _dbg('[DEBUG] audioPlayer.onerror:', e); _advanceQueue(); };
  }).catch(e => {
    if (_audioSafetyTimer) { clearTimeout(_audioSafetyTimer); _audioSafetyTimer = null; }
    _dbg('[DEBUG] audioPlayer.play() REJECTED:', e.name, e.message);
    _audioPlaying = false;
    _playNextFromQueue();
  });
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
    if (voiceActive) {
      sendMessage();
      return;
    }
    const reader = new FileReader();
    reader.onload = e => {
      $('imagePreview').src = e.target.result;
      $('imagePreviewContainer').style.display = 'block';
    };
    reader.readAsDataURL(f);
    updateMicSendButton();
  });
  $('removeImageButton').addEventListener('click', () => {
    selectedImageFile = null;
    $('imagePreviewContainer').style.display = 'none';
    $('imagePreview').src = '';
    updateMicSendButton();
  });

  // Socket.IO
  const socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
  window.socket = socket;
  let _streamRow = null;
  let _streamText = null;
  let _streamActive = false;

  socket.on('bot_stream_start', () => {
    _dbg('[DEBUG] bot_stream_start received');
    removeTypingMessage();
    if (_streamRow) { _streamRow = null; _streamText = null; }
    _streamActive = true;
    _botResponding = true;
    // Flush audio state from previous message
    _audioQueue.length = 0;
    _audioDone = false;
    _audioPlaying = false;
    audioStarted = false;
    // Pause mic during bot response to prevent restart cycles
    if (voiceActive) _micPause();
  });

  socket.on('bot_token', d => {
    removeTypingMessage();
    if (!_streamActive) return;
    if (!_streamRow) {
      const chatBody = document.querySelector('.chat-messages');
      _streamRow = document.createElement('div');
      _streamRow.className = 'msg-row msg-bot';
      _streamRow.innerHTML = '<div class="msg-bubble msg-bubble-bot"><div class="response-text"></div></div>';
      chatBody.appendChild(_streamRow);
      _streamText = _streamRow.querySelector('.response-text');
    }
    _streamText.textContent += d.text;
    const chatBody = document.querySelector('.chat-messages');
    chatBody.scrollTop = chatBody.scrollHeight;
  });

  socket.on('bot_audio_chunk', d => {
    _dbg('[AUDIO] bot_audio_chunk received | queueLen:', _audioQueue.length + 1, '| playing:', _audioPlaying);
    _audioQueue.push(d.data);
    _playNextFromQueue();
  });

  socket.on('bot_audio_done', () => {
    _dbg('[DEBUG] bot_audio_done | playing:', _audioPlaying, '| queueLen:', _audioQueue.length, '| audioUnlocked:', _audioUnlocked);
    _audioDone = true;
    if (!_audioPlaying && !_audioQueue.length) {
      _dbg('[DEBUG] bot_audio_done → all complete immediately');
      _fireAllAudioDone();
    } else if (!_audioUnlocked && _audioQueue.length) {
      // Audio element never unlocked (mobile autoplay policy) — chunks will never play.
      // Drain the queue and restart mic immediately.
      _dbg('[DEBUG] bot_audio_done → audio locked, flushing queue and firing allAudioDone');
      _audioQueue.length = 0;
      _audioDone = false;
      _fireAllAudioDone();
    } else {
      _dbg('[DEBUG] bot_audio_done → waiting for queue to drain');
      // Safety: if queue hasn't drained in 15s, something is stuck — force recovery
      setTimeout(() => {
        if (_botResponding && voiceActive) {
          _dbg('[DEBUG] bot_audio_done safety timeout — forcing _fireAllAudioDone | playing:', _audioPlaying, '| queueLen:', _audioQueue.length);
          _audioQueue.length = 0;
          _audioPlaying = false;
          _audioDone = false;
          _fireAllAudioDone();
        }
      }, 15000);
    }
  });

  socket.on('bot_message', d => {
    _dbg('[DEBUG] bot_message | audio_streamed:', d.audio_streamed, '| hasStreamRow:', !!_streamRow, '| msgLen:', (d.message||'').length);
    removeTypingMessage();
    _streamActive = false;
    if (_streamRow) {
      if (d.message) {
        _streamText.innerHTML = formatText(d.message);
        if (!d.audio_streamed) {
          _dbg('[DEBUG] bot_message → triggering legacy startAudioStream');
          startAudioStream();
        }
      } else {
        _streamRow.remove();
      }
      _streamRow = null;
      _streamText = null;
    } else {
      if (d.message) displayBotMessage(d.message, false, d.audio_streamed);
    }
  });

  socket.on('user_message',   d => displayUserMessage(d.message, null, d.speaker));
  socket.on('talking_state',  d => { _dbg('[DEBUG] talking_state:', d.talking); avatarIsTalking = d.talking; });
  socket.on('emotion_change', d => preloadAvatarSprites(d));

  // Skill execution status (sandbox, etc.) — shows a status indicator in chat
  socket.on('skill_status', d => {
    _dbg('[DEBUG] skill_status:', d.skill, d.status, d.description);
    const statusId = 'skill-status-' + d.skill;
    let el = document.getElementById(statusId);
    if (!el) {
      el = document.createElement('div');
      el.id = statusId;
      el.className = 'skill-status';
      const chatBox = document.getElementById('chatBox');
      if (chatBox) chatBox.appendChild(el);
    }
    const icons = { running: '\u2699\uFE0F', completed: '\u2705', failed: '\u274C', timeout: '\u23F1\uFE0F' };
    const icon = icons[d.status] || '';
    el.innerHTML = '<span class="skill-status-icon">' + icon + '</span> '
      + '<strong>' + (d.description || d.skill) + '</strong>'
      + ' <span class="skill-status-badge skill-status-' + d.status + '">' + d.status + '</span>'
      + (d.output ? '<pre class="skill-output">' + d.output.substring(0, 300) + '</pre>' : '');
    // Auto-remove completed/failed status after a few seconds
    if (d.status !== 'running') {
      setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 8000);
    }
  });

  // Deferred speaker name correction — update the last user message bubble if
  // speaker ID resolved after the initial display
  socket.on('update_last_user_speaker', d => {
    const rows = document.querySelectorAll('.msg-row-user');
    if (rows.length > 0) {
      const lastRow = rows[rows.length - 1];
      const nameEl = lastRow.querySelector('.msg-name');
      if (nameEl && d.speaker) nameEl.textContent = d.speaker;
    }
  });

  // Connection status
  const connDot = document.getElementById('connDot');
  socket.on('connect', () => {
    if (connDot) connDot.className = 'conn-dot';
  });
  socket.on('disconnect', () => {
    if (connDot) connDot.className = 'conn-dot disconnected';
    _audioQueue.length = 0;
    _audioDone = false;
    _audioPlaying = false;
    _botResponding = false;
    audioStarted = false;
    stop_talking();
    if (window.showToast) showToast('Connection lost — reconnecting...', 'error');
    // Socket.IO auto-reconnects — do NOT manually call socket.connect()
    // as that creates duplicate connections
    if (connDot) connDot.className = 'conn-dot reconnecting';
  });
  socket.on('reconnect_attempt', () => {
    if (connDot) connDot.className = 'conn-dot reconnecting';
  });

  function formatText(text) {
    if (!text) return '';
    return text
      .replace(/\n/g, '<br>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/``(.*?)``/g, '<code>$1</code>')
      .replace(/\\u([\dA-F]{4})/gi, (m, g) => String.fromCharCode(parseInt(g, 16)));
  }

  const prompt = $('prompt');

  function sendMessage() {
    const txt = prompt.value.trim();
    if (!txt && !selectedImageFile) return;
    displayUserMessage(txt, selectedImageFile);
    sendUserMessage(txt, selectedImageFile);
    prompt.value = '';
    selectedImageFile = null;
    $('imagePreviewContainer').style.display = 'none';
    $('imagePreview').src = '';
    updateMicSendButton();
    setTimeout(() => displayBotMessage('', true), 1000);
  }

  if (prompt) prompt.addEventListener('keyup', e => { if (e.key === 'Enter') sendMessage(); });

  function sendUserMessage(message, file) {
    const fd = new FormData();
    fd.append('message', message);
    if (file) fd.append('file', file);
    fetch('/process_llm', { method: 'POST', body: fd }).catch(console.error);
  }

  function displayBotMessage(message, isTyping = false, audioStreamed = false) {
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
    if (!isTyping && !audioStreamed) startAudioStream();
  }

  function removeTypingMessage() {
    document.querySelectorAll('.is-typing').forEach(el => el.remove());
  }

  function displayUserMessage(message, imageFile, speakerName) {
    const chatBody = document.querySelector('.chat-messages');
    const row = document.createElement('div');
    row.className = 'msg-row msg-row-user';
    const name = speakerName || window.APP_CONFIG?.userName || 'User';
    const meta = document.createElement('div');
    meta.className = 'msg-meta msg-meta-user';
    meta.innerHTML = `<span class="msg-name">${name}</span>`;
    row.appendChild(meta);
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

  // Avatar toggle
  const avatarHeader = document.querySelector('.avatar-header');
  if (avatarHeader) {
    if (localStorage.getItem('avatarHidden') === '1') avatarHeader.classList.add('collapsed');
    avatarHeader.addEventListener('click', () => {
      avatarHeader.classList.toggle('collapsed');
      localStorage.setItem('avatarHidden', avatarHeader.classList.contains('collapsed') ? '1' : '0');
    });
  }

  // ── MIC / SEND TOGGLE + VOICE MODE ─────────────────────────────────────────
  const voiceModeBtn = $('voiceModeButton');
  const voiceOverlay = $('voiceOverlay');
  const inputPill    = document.querySelector('.input-pill');
  const voiceCanvas  = $('voiceWaveform');
  const voiceStatus  = $('voiceStatus');

  let voiceAnimFrame = null;
  let voiceAnimLevel = 0;
  let isSendMode = false;

  // MediaRecorder voice mode state
  let _micStream = null;       // MediaStream — stays alive entire voice session
  let _micContext = null;       // AudioContext for VAD
  let _micAnalyser = null;      // AnalyserNode for volume detection
  let _micProcessor = null;     // ScriptProcessorNode for PCM capture
  let _micRecording = false;    // Currently capturing speech audio
  let _micChunks = [];          // Int16 PCM chunks accumulated during speech
  let _vadSpeaking = false;     // VAD: user is currently speaking
  let _vadSilenceStart = 0;     // Timestamp when silence began
  let _waitingForSTT = false;   // Waiting for server transcription result

  // VAD thresholds
  const VAD_SPEECH_THRESH = 0.015;  // RMS level to detect speech start
  const VAD_SILENCE_THRESH = 0.01;  // RMS level to detect speech end
  const VAD_SILENCE_MS = 800;       // ms of silence before sending audio
  const VAD_MIN_SPEECH_MS = 300;    // minimum speech duration to send
  let _vadSpeechStart = 0;
  let _micHealthTimer = null;     // Periodic AudioContext health check

  function updateMicSendButton() {
    if (!voiceModeBtn || !prompt || voiceActive) return;
    const hasText = prompt.value.trim().length > 0 || selectedImageFile;
    if (hasText && !isSendMode) {
      isSendMode = true;
      voiceModeBtn.querySelector('i').className = 'bi bi-send-fill';
      voiceModeBtn.classList.add('send-mode');
      voiceModeBtn.setAttribute('aria-label', 'Send');
    } else if (!hasText && isSendMode) {
      isSendMode = false;
      voiceModeBtn.querySelector('i').className = 'bi bi-mic-fill';
      voiceModeBtn.classList.remove('send-mode');
      voiceModeBtn.setAttribute('aria-label', 'Voice mode');
    }
  }

  if (prompt) prompt.addEventListener('input', updateMicSendButton);

  if (voiceModeBtn) {
    voiceModeBtn.addEventListener('click', () => {
      if (isSendMode) {
        sendMessage();
      } else if (voiceActive) {
        stopVoiceMode();
      } else {
        startVoiceMode();
      }
    });
  }

  // ── MediaRecorder + Server STT voice pipeline ───────────────────────────
  //
  // Strategy: Use Web Audio API for VAD, capture raw PCM, send to server
  // for Whisper transcription. No Chrome SpeechRecognition at all.
  //
  //   1. getUserMedia → MediaStream (stays alive entire session)
  //   2. AudioContext + ScriptProcessorNode captures 16kHz mono Int16 PCM
  //   3. AnalyserNode monitors RMS volume for VAD
  //   4. Speech detected → accumulate PCM chunks
  //   5. Silence detected → base64-encode PCM, emit 'browser_audio' via SocketIO
  //   6. Server transcribes with Whisper, emits 'browser_transcription' back
  //   7. During bot response: just stop accumulating (stream stays alive)
  //

  // Pause mic — stop recording during bot response. Stream stays alive.
  _micPause = function() {
    _dbg('[MIC] paused — stopping recording (stream alive)');
    _micRecording = false;
    _vadSpeaking = false;
    _micChunks = [];
    if (voiceStatus) voiceStatus.textContent = '';
  };

  // Restart mic — resume recording after bot audio finishes.
  _micRestart = function() {
    if (!voiceActive) return;
    _dbg('[MIC] restarting — resuming recording | ctxState:', _micContext ? _micContext.state : 'null');
    _micRecording = true;
    _vadSpeaking = false;
    _micChunks = [];
    // CRITICAL: Chrome suspends AudioContext when another audio source plays.
    // If suspended, onaudioprocess silently stops firing and the mic appears dead.
    if (_micContext && _micContext.state === 'suspended') {
      _micContext.resume().then(() => {
        _dbg('[MIC] AudioContext resumed from suspended state');
      }).catch(e => {
        _dbg('[MIC] AudioContext resume failed:', e.message);
      });
    }
    if (voiceStatus) voiceStatus.textContent = 'Listening...';
  };

  // Handle transcription result from server
  socket.on('browser_transcription', function(d) {
    _waitingForSTT = false;
    const text = (d.text || '').trim();
    if (d.error) _dbg('[MIC] STT error:', d.error);
    if (!text) {
      _dbg('[MIC] STT returned empty');
      if (voiceActive && !_botResponding) {
        voiceStatus.textContent = 'Listening...';
      }
      return;
    }
    // Guard: ignore duplicate transcriptions if already processing
    if (_botResponding) {
      _dbg('[MIC] STT result ignored — bot already responding:', text);
      return;
    }
    _dbg('[MIC] STT result:', text);
    _botResponding = true;  // set immediately to block duplicates
    voiceStatus.textContent = 'Processing...';
    displayUserMessage(text);
    sendUserMessage(text);
    setTimeout(() => displayBotMessage('', true), 500);
  });

  function _sendAudioToServer(chunks) {
    if (!chunks.length || _waitingForSTT) return;
    // Merge Int16 chunks into single buffer
    let totalLen = 0;
    for (let i = 0; i < chunks.length; i++) totalLen += chunks[i].length;
    const merged = new Int16Array(totalLen);
    let offset = 0;
    for (let i = 0; i < chunks.length; i++) {
      merged.set(chunks[i], offset);
      offset += chunks[i].length;
    }
    // Base64 encode — use chunked apply to avoid stack overflow on large buffers
    const bytes = new Uint8Array(merged.buffer);
    const CHUNK = 8192;
    let binary = '';
    for (let i = 0; i < bytes.length; i += CHUNK) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    const b64 = btoa(binary);
    _dbg('[MIC] Sending audio to server |', merged.length, 'samples |', Math.round(merged.length / 16000 * 10) / 10, 's');
    _waitingForSTT = true;
    voiceStatus.textContent = 'Transcribing...';
    socket.emit('browser_audio', { audio: b64, sample_rate: 16000 });
  }

  async function startVoiceMode() {
    _dbg('[MIC] startVoiceMode called (MediaRecorder pipeline)');

    // Request mic permission
    try {
      _micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 }
      });
    } catch(e) {
      _dbg('[MIC] getUserMedia FAILED:', e.name, e.message);
      if (window.showToast) showToast('Microphone access denied', 'error');
      return;
    }

    // Set up AudioContext for VAD + PCM capture
    _micContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    // Ensure AudioContext is running (some browsers start suspended)
    if (_micContext.state === 'suspended') {
      await _micContext.resume();
      _dbg('[MIC] AudioContext was suspended on creation, resumed');
    }
    _dbg('[MIC] AudioContext created | state:', _micContext.state, '| sampleRate:', _micContext.sampleRate);
    const source = _micContext.createMediaStreamSource(_micStream);

    // AnalyserNode for RMS volume detection
    _micAnalyser = _micContext.createAnalyser();
    _micAnalyser.fftSize = 2048;
    source.connect(_micAnalyser);

    // ScriptProcessorNode to capture raw PCM at 16kHz
    // bufferSize=4096 at 16kHz = ~256ms per callback
    _micProcessor = _micContext.createScriptProcessor(4096, 1, 1);
    source.connect(_micProcessor);
    _micProcessor.connect(_micContext.destination); // required for processing to run

    _micProcessor.onaudioprocess = function(e) {
      if (!voiceActive || !_micRecording || _botResponding) return;

      const input = e.inputBuffer.getChannelData(0); // Float32 -1..1
      // Calculate RMS
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);

      // Update waveform animation
      voiceAnimLevel = Math.min(1.0, rms * 10);

      const now = Date.now();

      if (!_vadSpeaking) {
        // Waiting for speech to start
        if (rms > VAD_SPEECH_THRESH) {
          _vadSpeaking = true;
          _vadSpeechStart = now;
          _vadSilenceStart = 0;
          _micChunks = [];
          _dbg('[MIC] VAD: speech started | rms:', rms.toFixed(4));
          voiceStatus.textContent = 'Listening...';
        }
      }

      if (_vadSpeaking) {
        // Convert Float32 to Int16 and accumulate
        const int16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        _micChunks.push(int16);

        if (rms > VAD_SILENCE_THRESH) {
          // Still speaking
          _vadSilenceStart = 0;
        } else {
          // Silence detected
          if (!_vadSilenceStart) _vadSilenceStart = now;
          if (now - _vadSilenceStart >= VAD_SILENCE_MS) {
            // End of utterance
            _vadSpeaking = false;
            _vadSilenceStart = 0;  // Reset to prevent re-triggering
            const speechDuration = now - _vadSpeechStart;
            _dbg('[MIC] VAD: silence detected | speech duration:', speechDuration, 'ms | chunks:', _micChunks.length);
            if (speechDuration >= VAD_MIN_SPEECH_MS && _micChunks.length > 0) {
              _sendAudioToServer(_micChunks);
            } else {
              _dbg('[MIC] VAD: too short, discarding');
              voiceStatus.textContent = 'Listening...';
            }
            _micChunks = [];
          }
        }
      }
    };

    voiceActive = true;
    _micRecording = true;
    _vadSpeaking = false;
    _micChunks = [];

    voiceOverlay.style.display = 'flex';
    inputPill.classList.add('voice-active');
    voiceModeBtn.classList.add('voice-active');
    voiceModeBtn.querySelector('i').className = 'bi bi-stop-circle-fill';
    voiceModeBtn.setAttribute('aria-label', 'Stop voice');
    voiceStatus.textContent = 'Listening...';

    // Periodic health check — auto-resume AudioContext if it gets suspended
    if (_micHealthTimer) clearInterval(_micHealthTimer);
    _micHealthTimer = setInterval(() => {
      if (!voiceActive || !_micContext) { clearInterval(_micHealthTimer); _micHealthTimer = null; return; }
      if (_micContext.state === 'suspended' && _micRecording && !_botResponding) {
        _dbg('[MIC] Health check: AudioContext suspended while should be listening — resuming');
        _micContext.resume().catch(e => _dbg('[MIC] Health check resume failed:', e.message));
      }
    }, 2000);

    drawVoiceWaveform();
    _dbg('[MIC] Voice mode started (MediaRecorder pipeline)');
  }

  function stopVoiceMode() {
    _dbg('[MIC] stopVoiceMode called');
    voiceActive = false;
    _micRecording = false;
    _vadSpeaking = false;
    _micChunks = [];

    // Stop health check timer
    if (_micHealthTimer) { clearInterval(_micHealthTimer); _micHealthTimer = null; }

    // Tear down audio pipeline
    if (_micProcessor) {
      _micProcessor.onaudioprocess = null;
      try { _micProcessor.disconnect(); } catch(e) {}
      _micProcessor = null;
    }
    if (_micAnalyser) {
      try { _micAnalyser.disconnect(); } catch(e) {}
      _micAnalyser = null;
    }
    if (_micContext) {
      try { _micContext.close(); } catch(e) {}
      _micContext = null;
    }
    if (_micStream) {
      _micStream.getTracks().forEach(t => t.stop());
      _micStream = null;
    }

    if (voiceAnimFrame) { cancelAnimationFrame(voiceAnimFrame); voiceAnimFrame = null; }

    voiceModeBtn.classList.remove('voice-active');
    voiceModeBtn.classList.remove('send-mode');
    voiceModeBtn.querySelector('i').className = 'bi bi-mic-fill';
    voiceModeBtn.setAttribute('aria-label', 'Voice mode');
    voiceOverlay.style.display = 'none';
    inputPill.classList.remove('voice-active');
    isSendMode = false;
    updateMicSendButton();
  }

  function drawVoiceWaveform() {
    if (!voiceActive) return;
    voiceCanvas.width = voiceCanvas.clientWidth;
    voiceCanvas.height = voiceCanvas.clientHeight;
    const ctx = voiceCanvas.getContext('2d');
    const w = voiceCanvas.width;
    const h = voiceCanvas.height;
    ctx.clearRect(0, 0, w, h);

    voiceAnimLevel *= 0.92;
    const barCount = 40;
    const barWidth = (w / barCount) * 0.7;
    const gap = (w / barCount) * 0.3;

    ctx.fillStyle = '#00ced1';
    for (let i = 0; i < barCount; i++) {
      const wave = Math.sin(Date.now() / 200 + i * 0.3) * 0.5 + 0.5;
      const level = 0.05 + voiceAnimLevel * wave * 0.95;
      const barH = Math.max(2, level * (h - 4));
      const x = i * (barWidth + gap);
      const y = (h - barH) / 2;
      ctx.fillRect(x, y, barWidth, barH);
    }

    voiceAnimFrame = requestAnimationFrame(drawVoiceWaveform);
  }

});


// ── BODY (ARMS + LEGS) ──────────────────────────────────────────────────────
function updateBodyArmVal(slider) {
  slider.closest('.servo-card').querySelector('.servo-val').textContent = slider.value;
}

function updateBodyLegVal(slider) {
  slider.closest('.servo-card').querySelector('.servo-val').textContent = slider.value;
}

function resetBodyServo(id, def) {
  const el = $(id);
  el.value = def;
  el.closest('.servo-card').querySelector('.servo-val').textContent = def;
  updateArmConstraints();
}

function updateArmConstraints() {
  function clampChild(slider, maxVal) {
    if (parseInt(slider.value) > maxVal) {
      slider.value = maxVal;
      slider.closest('.servo-card').querySelector('.servo-val').textContent = maxVal;
    }
    updateSliderGauge(slider, maxVal);
  }
  function calcMax(parentVal) {
    return parentVal <= 50 ? Math.max(1, Math.round(parentVal / 2)) : Math.round(25 + (parentVal - 50) * 1.5);
  }
  // left arm chain
  const lm = parseInt($('leftMain').value);
  clampChild($('leftForearm'), calcMax(lm));
  clampChild($('leftHand'), calcMax(parseInt($('leftForearm').value)));
  // right arm chain
  const rm = parseInt($('rightMain').value);
  clampChild($('rightForearm'), calcMax(rm));
  clampChild($('rightHand'), calcMax(parseInt($('rightForearm').value)));
}

function updateSliderGauge(slider, maxAllowed) {
  const pct = maxAllowed;
  slider.style.background = `linear-gradient(to right,rgba(0,229,255,.3) 0%,rgba(0,229,255,.3) ${pct}%,rgba(180,77,255,.3) ${pct}%,rgba(180,77,255,.3) 100%)`;
}

// speed slider value display + stop touch propagation on all body sliders
(function () {
  var sp = document.getElementById('bodySpeedSlider');
  if (sp) sp.addEventListener('input', function () {
    var v = document.querySelector('.body-speed-val');
    if (v) v.textContent = parseFloat(this.value).toFixed(2);
  });
  // prevent range inputs from triggering swipe navigation
  document.querySelectorAll('.body-range, #bodySpeedSlider').forEach(function (slider) {
    slider.addEventListener('touchstart', function (e) { e.stopPropagation(); }, { passive: true });
    slider.addEventListener('touchmove', function (e) { e.stopPropagation(); }, { passive: true });
  });
})();

function applyBodyControls() {
  const speed = +$('bodySpeedSlider').value;
  fetch('/move_arms', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      left_main: +$('leftMain').value, left_forearm: +$('leftForearm').value,
      left_hand: +$('leftHand').value, right_main: +$('rightMain').value,
      right_forearm: +$('rightForearm').value, right_hand: +$('rightHand').value,
      speed: speed
    })
  }).catch(console.error);
  fetch('/move_legs', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      left_height: +$('leftHeight').value, right_height: +$('rightHeight').value,
      left_leg: +$('leftLeg').value, right_leg: +$('rightLeg').value,
      speed: speed
    })
  }).catch(console.error);
}

function resetBody() {
  const armIds = ['leftMain','leftForearm','leftHand','rightMain','rightForearm','rightHand'];
  const legIds = ['leftHeight','rightHeight','leftLeg','rightLeg'];
  fetch('/move_arms', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ left_main:1, left_forearm:1, left_hand:1, right_main:1, right_forearm:1, right_hand:1, speed:0.75 })
  }).then(() => {
    armIds.forEach(id => { $(id).value = 1; $(id).closest('.servo-card').querySelector('.servo-val').textContent = '1'; });
    updateArmConstraints();
    return fetch('/disable_servos', { method:'POST', headers:{'Content-Type':'application/json'} });
  }).then(() => fetch('/reset_positions', { method:'POST', headers:{'Content-Type':'application/json'} }))
    .then(() => fetch('/disable_servos', { method:'POST', headers:{'Content-Type':'application/json'} }))
    .catch(console.error);
  fetch('/neutral_legs', { method:'POST', headers:{'Content-Type':'application/json'} })
    .then(() => {
      legIds.forEach(id => { $(id).value = 50; $(id).closest('.servo-card').querySelector('.servo-val').textContent = '50'; });
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
    }).then(r => { if (!r.ok) r.json().then(d => console.error('Move failed:', d)); })
     .catch(console.error);
  }

  btnUp.addEventListener('click',    () => move(getSpeed() === 'fast' ? 'forward'  : 'forward_slow'));
  btnDown.addEventListener('click',  () => move(getSpeed() === 'fast' ? 'backward' : 'backward_slow'));
  btnLeft.addEventListener('click',  () => move(getSpeed() === 'fast' ? 'left'     : 'left_slow'));
  btnRight.addEventListener('click', () => move(getSpeed() === 'fast' ? 'right'    : 'right_slow'));
});

// ── MOTION CAMERA TOGGLE ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const toggle = $('motionCameraToggle');
  const bg = $('motionCameraBg');
  const feed = $('motionCameraFeed');
  if (!toggle || !bg || !feed) return;

  toggle.addEventListener('click', function () {
    const active = bg.classList.toggle('active');
    toggle.classList.toggle('active', active);
    feed.src = active ? '/camera_feed' : '';
  });
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
  const action = $('actionSelect').value;
  if (!action) return;
  fetch('/execute_action', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action: action })
  }).then(r => { if (!r.ok) r.json().then(d => console.error('Action failed:', d)); })
   .catch(console.error);
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
  function esc(t)  { const d=document.createElement('div'); d.textContent=t; return d.innerHTML.replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
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

  const SECTION_ICONS = {
    'CHAR':'bi-person-fill',
    'CONTROLS':'bi-controller','STT':'bi-mic-fill','LLM':'bi-robot',
    'VISION':'bi-eye-fill','EMOTION':'bi-emoji-smile-fill','TTS':'bi-volume-up-fill',
    'UI':'bi-display-fill','RAG':'bi-database-fill',
    'ACCESS':'bi-key-fill',
    'BATTERY':'bi-battery-half',
    'SKILLS':'bi-lightning-fill',
    'MISC':'bi-wrench-adjustable',
    'CHARACTER_EDITOR':'bi-person-lines-fill'
  };
  const SECTION_LABELS = {
    'CHAR':'System','CONTROLS':'Controls',
    'STT':'Speech','LLM':'AI Model','VISION':'Vision','EMOTION':'Emotion',
    'TTS':'Voice','UI':'Display','RAG':'Memory',
    'ACCESS':'Access',
    'BATTERY':'Battery',
    'SKILLS':'Skills',
    'MISC':'Misc',
    'CHARACTER_EDITOR':'Character'
  };

  const SECTION_ORDER = [
    'CHAR', 'LLM', 'SKILLS',
    'STT', 'TTS',
    'EMOTION', 'VISION', 'RAG',
    'UI', 'ACCESS',
    'CONTROLS',
    'BATTERY'
  ];

  // Character editor tile is appended after config sections
  const CHARACTER_EDITOR_ID = 'CHARACTER_EDITOR';

  let activeConfigSection = null;

  function _skillFieldHtml(skillName, key, fieldDef, value) {
    const fid = `skill_${skillName}_${key}`;
    const desc = fieldDef.description || '';
    const label = fieldDef.label || key.replace(/_/g, ' ');
    const type = fieldDef.type || 'text';
    let h = `<div class="col-md-6 col-lg-4 skill-cfg-field" data-skill-field="${key}"><div class="field-wrapper">`;
    h += `<label for="${fid}" class="form-label d-flex align-items-center gap-1"><span>${label}</span>`;
    if (desc) h += `<span class="config-tooltip-wrap" data-tip="${esc(desc)}"><i class="bi bi-info-circle config-tooltip-icon"></i></span>`;

    if (type === 'bool') {
      const chk = (value === true || value === 'true' || value === 'True') ? 'checked' : '';
      h += `</label><div class="form-check form-switch mt-1"><input class="form-check-input config-toggle skill-cfg-input" type="checkbox" id="${fid}" data-skill="${skillName}" data-key="${key}" ${chk}><label class="form-check-label small" for="${fid}">${chk?'Enabled':'Disabled'}</label></div>`;
    } else if (type === 'select' && fieldDef.options) {
      h += `</label><select class="form-select form-select-sm config-input skill-cfg-input" id="${fid}" data-skill="${skillName}" data-key="${key}">`;
      fieldDef.options.forEach(opt => { h += `<option value="${opt}"${String(value)===String(opt)?' selected':''}>${opt}</option>`; });
      h += '</select>';
    } else if (type === 'number') {
      h += `</label><input type="number" class="form-control form-control-sm config-input skill-cfg-input" id="${fid}" data-skill="${skillName}" data-key="${key}" value="${esc(String(value??fieldDef.default??''))}"`;
      if (fieldDef.min !== undefined) h += ` min="${fieldDef.min}"`;
      if (fieldDef.max !== undefined) h += ` max="${fieldDef.max}"`;
      h += '>';
    } else if (type === 'password') {
      h += `</label><div class="config-password-wrap"><input type="password" class="form-control form-control-sm config-input skill-cfg-input" id="${fid}" data-skill="${skillName}" data-key="${key}" value="${esc(String(value??''))}"><button type="button" class="config-password-toggle" data-target="${fid}" title="Show/hide"><i class="bi bi-eye"></i></button></div>`;
    } else {
      h += `</label><input type="text" class="form-control form-control-sm config-input skill-cfg-input" id="${fid}" data-skill="${skillName}" data-key="${key}" value="${esc(String(value??''))}">`;
    }
    h += '</div></div>';
    return h;
  }

  function _checkSkillDeps(skillName) {
    // Show/hide skill config fields based on depends_on
    const panel = document.querySelector(`.skill-config-panel[data-skill-panel="${skillName}"]`);
    const card = document.querySelector(`.skill-card[data-skill-name="${skillName}"]`);
    if (!panel) return;
    const schema = card?._skillSchema || {};
    panel.querySelectorAll('.skill-cfg-field').forEach(fieldEl => {
      const key = fieldEl.dataset.skillField;
      const dep = schema[key]?.depends_on;
      if (!dep) return;
      const depInput = panel.querySelector(`.skill-cfg-input[data-key="${dep.field}"]`);
      if (!depInput) return;
      const depVal = depInput.type === 'checkbox' ? (depInput.checked ? 'true' : 'false') : depInput.value;
      const allowed = (dep.values || []).map(String);
      fieldEl.style.display = allowed.includes(depVal) ? '' : 'none';
    });
  }

  function loadSkillsPanel() {
    const grid = document.getElementById('skillsGrid');
    if (!grid) return;
    grid.innerHTML = '<div class="config-loading"><div class="hud-spinner"></div><span>Loading skills…</span></div>';
    fetch('/get_skills').then(r => r.json()).then(data => {
      if (!data.skills || !data.skills.length) {
        grid.innerHTML = '<div class="text-center p-3 text-muted">No skills discovered</div>';
        return;
      }
      // Skill toggle cards in a grid — each skill card followed by its own config panel
      let html = '<div class="row g-2">';
      for (const skill of data.skills) {
        const chk = skill.enabled ? 'checked' : '';
        const label = skill.name.replace(/_/g, ' ');
        const desc = skill.description || '';
        const hasConfig = skill.config_schema && Object.keys(skill.config_schema).length > 0;

        html += `<div class="col-md-6 col-lg-4"><div class="field-wrapper skill-card" data-skill-name="${skill.name}">`;
        html += `<label class="form-label d-flex align-items-center gap-1 mb-0">
          <span style="text-transform:capitalize">${label}</span>
          ${desc ? `<span class="config-tooltip-wrap" data-tip="${esc(desc)}"><i class="bi bi-info-circle config-tooltip-icon"></i></span>` : ''}
        </label>`;
        html += `<div class="d-flex align-items-center justify-content-between mt-1">
          <div class="form-check form-switch mb-0">
            <input class="form-check-input config-toggle skill-toggle" type="checkbox" data-skill="${skill.name}" ${chk}>
            <label class="form-check-label small">${chk?'Enabled':'Disabled'}</label>
          </div>`;
        if (hasConfig) {
          html += `<button class="hud-btn hud-btn-sm hud-btn-ghost skill-expand-btn" data-skill="${skill.name}" title="Settings" style="padding:2px 8px;font-size:12px;"><i class="bi bi-gear"></i></button>`;
        }
        html += `</div></div></div>`;

        // Config panel right after this skill's card — full row width
        if (hasConfig) {
          html += `<div class="col-12 skill-config-panel" data-skill-panel="${skill.name}" style="display:none;">`;
          html += `<div class="field-wrapper" style="padding:16px;">`;
          html += `<div class="d-flex align-items-center justify-content-between mb-3">`;
          html += `<label class="form-label mb-0 d-flex align-items-center gap-1"><i class="bi bi-gear"></i> <span style="text-transform:capitalize">${label} Settings</span></label>`;
          html += `<button class="hud-btn hud-btn-sm hud-btn-ghost skill-collapse-btn" data-skill="${skill.name}" title="Close"><i class="bi bi-x-lg"></i></button>`;
          html += `</div>`;
          html += '<div class="row g-2">';
          for (const [key, fieldDef] of Object.entries(skill.config_schema)) {
            const val = skill.config_values[key] ?? fieldDef.default ?? '';
            html += _skillFieldHtml(skill.name, key, fieldDef, val);
          }
          html += '</div>';
          html += `</div></div>`;
        }
      }
      html += '</div>';
      grid.innerHTML = html;

      // Store schema refs on card elements for depends_on checks
      for (const skill of data.skills) {
        const card = grid.querySelector(`.skill-card[data-skill-name="${skill.name}"]`);
        if (card) card._skillSchema = skill.config_schema || {};
      }

      // Wire up toggle handlers
      grid.querySelectorAll('.skill-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
          const name = this.dataset.skill;
          const enabled = this.checked;
          const lbl = this.nextElementSibling;
          if (lbl) lbl.textContent = enabled ? 'Enabled' : 'Disabled';
          fetch('/toggle_skill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, enabled })
          }).then(r => r.json()).then(res => {
            if (res.success) {
              showToast(`Skill "${name.replace(/_/g,' ')}" ${enabled?'enabled':'disabled'}`, 'success');
            } else {
              showToast(`Failed: ${res.error}`, 'error');
              toggle.checked = !enabled;
              if (lbl) lbl.textContent = !enabled ? 'Enabled' : 'Disabled';
            }
          }).catch(() => { showToast('Failed to toggle skill', 'error'); toggle.checked = !enabled; });
        });
      });

      // Wire up expand/collapse — show full-width panel below grid
      grid.querySelectorAll('.skill-expand-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const name = this.dataset.skill;
          const panel = grid.querySelector(`.skill-config-panel[data-skill-panel="${name}"]`);
          if (panel) {
            // Close any other open panels first
            grid.querySelectorAll('.skill-config-panel').forEach(p => {
              if (p !== panel) p.style.display = 'none';
            });
            grid.querySelectorAll('.skill-expand-btn').forEach(b => {
              if (b !== this) b.querySelector('i').className = 'bi bi-gear';
            });
            const shown = panel.style.display !== 'none';
            panel.style.display = shown ? 'none' : 'block';
            this.querySelector('i').className = shown ? 'bi bi-gear' : 'bi bi-chevron-up';
            if (!shown) {
              _checkSkillDeps(name);
              panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
          }
        });
      });
      // Wire up close buttons inside panels
      grid.querySelectorAll('.skill-collapse-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const name = this.dataset.skill;
          const panel = grid.querySelector(`.skill-config-panel[data-skill-panel="${name}"]`);
          if (panel) panel.style.display = 'none';
          const expandBtn = grid.querySelector(`.skill-expand-btn[data-skill="${name}"]`);
          if (expandBtn) expandBtn.querySelector('i').className = 'bi bi-gear';
        });
      });

      // Wire up bool toggle labels
      grid.querySelectorAll('.skill-cfg-input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', function() {
          const lbl = this.nextElementSibling;
          if (lbl) lbl.textContent = this.checked ? 'Enabled' : 'Disabled';
          _checkSkillDeps(this.dataset.skill);
        });
      });

      // Wire up select/text change for depends_on
      grid.querySelectorAll('.skill-cfg-input:not([type="checkbox"])').forEach(input => {
        input.addEventListener('change', function() { _checkSkillDeps(this.dataset.skill); });
      });

      // Wire up password toggles
      grid.querySelectorAll('.config-password-toggle').forEach(btn => {
        btn.addEventListener('click', function() {
          const input = document.getElementById(this.dataset.target);
          if (input) {
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            this.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
          }
        });
      });

      // Initial depends_on check for all skills
      for (const skill of data.skills) {
        _checkSkillDeps(skill.name);
      }

      // Re-bind tooltips for dynamically rendered skill elements
      initConfigTooltips();
    }).catch(err => {
      grid.innerHTML = `<div class="text-center p-3 text-danger">Failed to load skills: ${err.message}</div>`;
    });
  }

  function loadConfiguration() {
    fetch('/get_config').then(r=>r.json()).then(data => {
      const form = $('configForm');

      // Order sections: SECTION_ORDER first, then any extras from backend
      // SKILLS is always shown (it has its own data source, not config.ini)
      const allSections = Object.keys(data.config);
      const alwaysShow = ['SKILLS'];
      const ordered = SECTION_ORDER.filter(s => allSections.includes(s) || alwaysShow.includes(s));
      allSections.forEach(s => { if (!ordered.includes(s)) ordered.push(s); });

      // Build icon grid
      let html = '<div class="config-icon-grid">';
      for (const section of ordered) {
        const icon = SECTION_ICONS[section] || 'bi-gear';
        const label = SECTION_LABELS[section] || section;
        html += `<div class="config-icon-tile" data-section-target="${section}">
          <div class="config-icon-tile-inner"><i class="bi ${icon}"></i></div>
          <span class="config-icon-label">${label}</span>
        </div>`;
      }
      html += '</div>';

      // Build section panels
      for (const section of ordered) {
        const fields = data.config[section];
        const desc = data.field_options[`${section}.__section__`];
        const label = SECTION_LABELS[section] || section;
        const icon = SECTION_ICONS[section] || 'bi-gear';

        html += `<div class="config-panel" id="configPanel_${section}">
          <div class="config-panel-header">
            <button class="config-panel-back" data-section="${section}"><i class="bi bi-chevron-left"></i></button>
            <div class="config-panel-title">
              <i class="bi ${icon}"></i><span>${label}</span>
              ${desc?`<small>${desc.description||desc}</small>`:''}
            </div>
          </div>`;

        // Skills section: dynamic skill toggles loaded from API
        if (section === 'SKILLS') {
          html += `<div class="config-panel-body">
            <div class="skills-grid" id="skillsGrid">
              <div class="config-loading"><div class="hud-spinner"></div><span>Loading skills…</span></div>
            </div>
          </div></div>`;
          continue;
        }

        html += `<div class="config-panel-body"><div class="row g-2">`;

        for (const [key, value] of Object.entries(fields)) {
          const fid = `cfg_${section}_${key}`, fi = data.field_options[`${section}.${key}`], desc2 = fi?.description||'';
          const depData = fi?.depends_on ? JSON.stringify(Array.isArray(fi.depends_on) ? fi.depends_on : [fi.depends_on]) : null;
          html += depData
            ? `<div class="col-md-6 col-lg-4" data-dep-conds='${depData}' data-dep-section="${section}"><div class="field-wrapper">`
            : `<div class="col-md-6 col-lg-4"><div class="field-wrapper">`;
          html += `<label for="${fid}" class="form-label d-flex align-items-center gap-1"><span>${fi?.label||key}</span>`;
          if (desc2) html += `<span class="config-tooltip-wrap" data-tip="${esc(desc2)}"><i class="bi bi-info-circle config-tooltip-icon"></i></span>`;

          if (fi?.type==='slider') {
            const mn=fi.min??0, mx=fi.max??100, st=fi.step??1, v=Number(value)||mn;
            html += `</label><div class="d-flex align-items-center gap-2"><input type="range" class="config-slider config-input" id="${fid}" data-section="${section}" data-key="${key}" min="${mn}" max="${mx}" step="${st}" value="${v}"><span class="config-slider-val">${v}</span></div>`;
          } else if (fi?.type==='screensaver_select') {
            html += `</label>${screensaverHtml(fid,section,key,value,fi.options||[])}`;
          } else if (fi?.options) {
            html += `</label><div class="d-flex align-items-center gap-1"><select class="form-select form-select-sm config-input" id="${fid}" data-section="${section}" data-key="${key}" style="flex:1">`;
            const optLabels = fi.option_labels || {};
            fi.options.forEach(opt => { html += `<option value="${opt}"${String(value)===String(opt)?' selected':''}>${optLabels[opt]||opt}</option>`; });
            html += '</select>';
            if (key === 'character_card_path') {
              html += `<button class="hud-btn hud-btn-sm hud-btn-primary config-char-edit-btn" type="button" title="Edit character"><i class="bi bi-pencil-square"></i></button>`;
            }
            html += '</div>';
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
              const isPassword = (fi?.type === 'password' || key.toLowerCase().includes('password'));
              const inputType = isPassword ? 'password' : 'text';
              if (isPassword) {
                html += `</label><div class="config-password-wrap"><input type="${inputType}" class="form-control form-control-sm config-input" id="${fid}" data-section="${section}" data-key="${key}" value="${esc(String(value))}"><button type="button" class="config-password-toggle" data-target="${fid}" title="Show/hide password"><i class="bi bi-eye"></i></button></div>`;
              } else {
                html += `</label><input type="${inputType}" class="form-control form-control-sm config-input" id="${fid}" data-section="${section}" data-key="${key}" value="${esc(String(value))}">`;
              }
            }
          }

          html += '</div></div>';
        }

        // Inject Remote Access tunnel controls into the ACCESS grid
        if (section === 'ACCESS') {
          html += `<div class="col-md-6 col-lg-4"><div class="field-wrapper">
<label class="form-label d-flex align-items-center gap-1">
  <span>remote_access</span>
  <span class="config-tooltip-wrap" data-tip="Start a temporary Cloudflare tunnel to access TARS remotely. A unique URL is generated each session and nothing persists after reboot."><i class="bi bi-info-circle config-tooltip-icon"></i></span>
  <span class="badge bg-secondary ms-1" id="tunBadge" style="font-size:.6rem">Inactive</span>
</label>
<div class="text-center mt-3">
  <button class="btn btn-sm btn-outline-primary" id="tunStartBtn"><i class="bi bi-globe me-1"></i>Start Tunnel</button>
  <button class="btn btn-sm btn-outline-danger" id="tunStopBtn" style="display:none"><i class="bi bi-stop-fill me-1"></i>Stop Tunnel</button>
  <div id="tunError" style="display:none" class="mt-2"><p class="small text-danger mb-1" id="tunErrorMsg"></p><button class="btn btn-sm btn-outline-primary" id="tunRetryBtn"><i class="bi bi-arrow-clockwise me-1"></i>Retry</button></div>
</div>
</div></div>
<div class="col-md-6 col-lg-4" id="tunUrlCol" style="display:none"><div class="field-wrapper">
<label class="form-label d-flex align-items-center gap-1"><span>remote_url</span><span class="config-tooltip-wrap" data-tip="Your public URL for accessing TARS from anywhere."><i class="bi bi-info-circle config-tooltip-icon"></i></span></label>
<div class="d-flex gap-1 align-items-stretch"><button class="btn btn-sm tun-btn" type="button" id="tunCopyBtn" title="Copy URL"><i class="bi bi-clipboard"></i></button><input type="text" class="form-control form-control-sm config-input flex-grow-1" id="tunUrl" readonly style="cursor:pointer"><button class="btn btn-sm tun-btn" type="button" id="tunOpenBtn" title="Open URL"><i class="bi bi-box-arrow-up-right"></i></button></div>
</div></div>
<div class="col-md-6 col-lg-4" id="tunQrCol" style="display:none"><div class="field-wrapper">
<label class="form-label d-flex align-items-center gap-1"><span>qr_code</span><span class="config-tooltip-wrap" data-tip="Scan with your phone to open the remote access URL."><i class="bi bi-info-circle config-tooltip-icon"></i></span></label>
<div class="text-center"><img id="tunQrCode" class="rounded" style="max-width:120px; border:1px solid rgba(255,255,255,.25)" alt="QR Code"></div>
</div></div>
</div></div></div>`;
        } else {
          html += '</div></div></div>';
        }
      }

      // Character Editor panel (same pattern as config-panel)
      html += `<div class="config-panel" id="configPanel_${CHARACTER_EDITOR_ID}">
        <div class="config-panel-header">
          <button class="config-panel-back" data-section="${CHARACTER_EDITOR_ID}"><i class="bi bi-chevron-left"></i></button>
          <div class="config-panel-title">
            <i class="bi bi-person-lines-fill"></i><span>Character Editor</span>
            <small>Edit character JSON and personality traits</small>
          </div>
        </div>
        <div class="config-panel-body" style="padding:0">
          <div class="chared-wrap">
            <div class="chared-header">
              <div class="chared-header-right" style="width:100%">
                <select id="charedSelect" class="form-select form-select-sm chared-selector">
                  <option value="">— select character —</option>
                </select>
                <button class="hud-btn hud-btn-primary" id="saveCharBtn">
                  <i class="bi bi-save"></i> SAVE
                </button>
              </div>
            </div>
            <div class="chared-loading" id="charedLoading" style="display:none">
              <div class="hud-spinner"></div><span>Loading…</span>
            </div>
            <div class="chared-empty" id="charedEmpty">
              <i class="bi bi-person-lines-fill"></i>
              <span>Select a character above to begin editing</span>
            </div>
            <div class="chared-body" id="charedBody" style="display:none">
              <div class="chared-tabs">
                <button class="chared-inner-tab active" data-chared-tab="identity">IDENTITY</button>
                <button class="chared-inner-tab" data-chared-tab="persona">PERSONA</button>
                <button class="chared-inner-tab" data-chared-tab="dialogue">DIALOGUE</button>
                <button class="chared-inner-tab" data-chared-tab="traits">TRAITS</button>
              </div>
              <div class="chared-panel active" id="charedPanel_identity">
                <div class="chared-fields">
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_char_name">NAME</label>
                    <input type="text" id="ched_char_name" class="form-control form-control-sm chared-input" placeholder="Character name">
                  </div>
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_description">DESCRIPTION <span class="chared-tip">Physical appearance and basic identity</span></label>
                    <textarea id="ched_description" class="form-control chared-textarea" rows="3" placeholder="Physical description…"></textarea>
                  </div>
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_personality">PERSONALITY <span class="chared-tip">Core personality traits and behavioral tendencies</span></label>
                    <textarea id="ched_personality" class="form-control chared-textarea" rows="3" placeholder="Personality traits…"></textarea>
                  </div>
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_scenario">SCENARIO <span class="chared-tip">Context and setting the character exists in</span></label>
                    <textarea id="ched_scenario" class="form-control chared-textarea" rows="3" placeholder="Setting and context…"></textarea>
                  </div>
                </div>
              </div>
              <div class="chared-panel" id="charedPanel_persona">
                <div class="chared-fields">
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_char_persona">CHARACTER PERSONA <span class="chared-tip">Full persona description fed directly to the AI</span></label>
                    <textarea id="ched_char_persona" class="form-control chared-textarea" rows="6" placeholder="Full persona for the LLM system prompt…"></textarea>
                  </div>
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_world_scenario">WORLD SCENARIO <span class="chared-tip">World or operational context</span></label>
                    <textarea id="ched_world_scenario" class="form-control chared-textarea" rows="4" placeholder="World and operational context…"></textarea>
                  </div>
                </div>
              </div>
              <div class="chared-panel" id="charedPanel_dialogue">
                <div class="chared-fields">
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_first_mes">GREETING MESSAGE <span class="chared-tip">First message shown when a conversation starts</span></label>
                    <textarea id="ched_first_mes" class="form-control chared-textarea" rows="4" placeholder="Opening greeting…"></textarea>
                  </div>
                  <div class="chared-field-row">
                    <label class="chared-label" for="ched_mes_example">EXAMPLE DIALOGUE <span class="chared-tip">Sample conversations that shape the character voice</span></label>
                    <textarea id="ched_mes_example" class="form-control chared-textarea chared-textarea-xl" rows="10" placeholder="User: …&#10;Character: …"></textarea>
                  </div>
                </div>
              </div>
              <div class="chared-panel" id="charedPanel_traits">
                <div class="chared-traits-intro">Personality trait values (0 = minimal · 100 = maximum)</div>
                <div class="chared-traits-grid" id="charedTraitsGrid"></div>
              </div>
            </div>
          </div>
        </div>
      </div>`;

      form.innerHTML = html;
      activeConfigSection = null;

      // Wire up character editor events
      initCharacterEditor();

      // Icon tile click handlers
      document.querySelectorAll('.config-icon-tile').forEach(tile => {
        tile.addEventListener('click', function() {
          const target = this.dataset.sectionTarget;
          const panel = document.getElementById(`configPanel_${target}`);
          const grid = document.querySelector('.config-icon-grid');
          if (activeConfigSection === target) {
            panel.classList.remove('open');
            this.classList.remove('active');
            grid.classList.remove('has-active');
            activeConfigSection = null;
          } else {
            document.querySelectorAll('.config-panel.open').forEach(p => p.classList.remove('open'));
            document.querySelectorAll('.config-icon-tile.active').forEach(t => t.classList.remove('active'));
            panel.classList.add('open');
            this.classList.add('active');
            grid.classList.add('has-active');
            activeConfigSection = target;
            if (target === 'SKILLS') loadSkillsPanel();
            if (target === 'CHARACTER_EDITOR' && window.onCharacterEditorOpen) window.onCharacterEditorOpen();
            setTimeout(() => panel.scrollIntoView({ behavior:'smooth', block:'start' }), 80);
          }
        });
      });

      // Back button handlers
      document.querySelectorAll('.config-panel-back').forEach(btn => {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          const sec = this.dataset.section;
          document.getElementById(`configPanel_${sec}`).classList.remove('open');
          const tile = document.querySelector(`.config-icon-tile[data-section-target="${sec}"]`);
          if (tile) tile.classList.remove('active');

          if (sec === CHARACTER_EDITOR_ID) {
            // Go back to System (CHAR) panel instead of blank grid
            const charPanel = document.getElementById('configPanel_CHAR');
            const charTile = document.querySelector('.config-icon-tile[data-section-target="CHAR"]');
            if (charPanel) { charPanel.classList.add('open'); charPanel.scrollIntoView({ behavior:'smooth', block:'start' }); }
            if (charTile) charTile.classList.add('active');
            activeConfigSection = 'CHAR';
          } else {
            document.querySelector('.config-icon-grid').classList.remove('has-active');
            activeConfigSection = null;
            document.querySelector('.config-icon-grid').scrollIntoView({ behavior:'smooth', block:'start' });
          }
        });
      });

      document.querySelectorAll('.config-toggle').forEach(t => {
        t.addEventListener('change', function () {
          const lbl = this.parentElement.querySelector('.form-check-label');
          if (lbl) lbl.textContent = this.checked ? 'Enabled' : 'Disabled';
        });
      });
      document.querySelectorAll('input[type="range"].config-input').forEach(r => {
        r.addEventListener('input', function () {
          const badge = this.parentElement.querySelector('.config-slider-val');
          if (badge) badge.textContent = this.value;
        });
      });
      initTagInputs(); initScreensaverSelects(); initConfigTooltips();
      applyDependencies(); attachDependencyHandlers(); attachBackendUrlAutoFill();

      // Character edit button → open CHARACTER_EDITOR panel with the selected character
      document.querySelectorAll('.config-char-edit-btn').forEach(btn => {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          // Extract character name from the selected path (e.g. "character/TARS/TARS.json" → "TARS")
          const sel = document.getElementById('cfg_CHAR_character_card_path');
          const selectedPath = sel ? sel.value : '';
          const charName = selectedPath ? selectedPath.split('/')[1] : '';

          // Open the CHARACTER_EDITOR panel
          const editorPanel = document.getElementById(`configPanel_${CHARACTER_EDITOR_ID}`);
          const grid = document.querySelector('.config-icon-grid');
          document.querySelectorAll('.config-panel.open').forEach(p => p.classList.remove('open'));
          document.querySelectorAll('.config-icon-tile.active').forEach(t => t.classList.remove('active'));
          if (editorPanel) editorPanel.classList.add('open');
          if (grid) grid.classList.add('has-active');
          activeConfigSection = CHARACTER_EDITOR_ID;

          if (window.onCharacterEditorOpen) window.onCharacterEditorOpen(charName);
          setTimeout(() => editorPanel && editorPanel.scrollIntoView({ behavior:'smooth', block:'start' }), 80);
        });
      });

      // Live theme preview — swap the theme stylesheet
      var themeSelect = document.getElementById('cfg_ACCESS_webui_theme');
      if (themeSelect) {
        themeSelect.addEventListener('change', function () {
          var theme = this.value || 'midnight';
          var link = document.getElementById('themeCSS');
          if (link) link.href = '/static/css/themes/' + theme + '.css?v=' + Date.now();
        });
      }

      // Remote access tunnel controls
      initTunnelControls();

      // Password show/hide toggle (event delegation)
      var configForm = $('configForm');
      if (configForm) {
        configForm.addEventListener('click', function (e) {
          var btn = e.target.closest('.config-password-toggle');
          if (!btn) return;
          var targetId = btn.getAttribute('data-target');
          var inp = document.getElementById(targetId);
          if (!inp) return;
          var isHidden = inp.type === 'password';
          inp.type = isHidden ? 'text' : 'password';
          var icon = btn.querySelector('i');
          if (icon) {
            icon.className = isHidden ? 'bi bi-eye-slash' : 'bi bi-eye';
          }
        });
      }
    }).catch(err => {
      $('configForm').innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle me-2"></i>Error: ${err.message}</div>`;
    });
  }

  /* ── Remote Access Tunnel (Cloudflare Quick Tunnel) ──────────── */
  function initTunnelControls() {
    const badge    = $('tunBadge');
    const startBtn = $('tunStartBtn');
    const stopBtn  = $('tunStopBtn');
    const urlCol   = $('tunUrlCol');
    const qrCol    = $('tunQrCol');
    const urlInput = $('tunUrl');
    const copyBtn  = $('tunCopyBtn');
    const openBtn  = $('tunOpenBtn');
    const qrImg    = $('tunQrCode');
    const error    = $('tunError');
    const errorMsg = $('tunErrorMsg');
    const retryBtn = $('tunRetryBtn');
    if (!badge || !startBtn) return;

    function showState(state) {
      error.style.display = state === 'error' ? '' : 'none';
      urlCol.style.display = state === 'active' ? '' : 'none';
      qrCol.style.display = state === 'active' ? '' : 'none';
    }

    function setButtons(isActive) {
      startBtn.style.display = isActive ? 'none' : '';
      stopBtn.style.display = isActive ? '' : 'none';
    }

    let pollTimer = null;
    function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

    function pollStatus() {
      fetch('/api/tunnel/status').then(r => r.json()).then(d => {
        if (d.state === 'active' && d.url) {
          stopPolling();
          badge.textContent = 'Active';
          badge.className = 'badge bg-success';
          urlInput.value = d.url;
          qrImg.src = `/api/tunnel/qr?url=${encodeURIComponent(d.url)}`;
          showState('active');
          setButtons(true);
        } else if (d.state === 'error') {
          stopPolling();
          badge.textContent = 'Error';
          badge.className = 'badge bg-danger';
          errorMsg.textContent = d.error || 'Failed to start tunnel';
          showState('error');
          setButtons(false);
        }
      }).catch(() => {});
    }

    function startTunnel() {
      showState(null);
      badge.textContent = 'Starting';
      badge.className = 'badge bg-warning';
      startBtn.style.display = 'none';
      stopBtn.style.display = 'none';
      stopPolling();

      fetch('/api/tunnel/start', { method:'POST' })
        .then(r => r.json()).then(d => {
          if (d.state === 'active' && d.url) {
            badge.textContent = 'Active';
            badge.className = 'badge bg-success';
            urlInput.value = d.url;
            qrImg.src = `/api/tunnel/qr?url=${encodeURIComponent(d.url)}`;
            showState('active');
            setButtons(true);
          } else {
            pollTimer = setInterval(pollStatus, 2000);
          }
        }).catch(() => {
          badge.textContent = 'Error';
          badge.className = 'badge bg-danger';
          errorMsg.textContent = 'Request failed. Check your connection.';
          showState('error');
          setButtons(false);
        });
    }

    function stopTunnel() {
      stopPolling();
      badge.textContent = 'Stopping...';
      badge.className = 'badge bg-warning';
      startBtn.style.display = 'none';
      stopBtn.style.display = 'none';
      fetch('/api/tunnel/stop', { method:'POST' }).then(() => {
        badge.textContent = 'Inactive';
        badge.className = 'badge bg-secondary';
        showState(null);
        setButtons(false);
      }).catch(() => {
        badge.textContent = 'Inactive';
        badge.className = 'badge bg-secondary';
        showState(null);
        setButtons(false);
      });
    }

    // Copy (with fallback for Android/non-HTTPS contexts)
    function copyUrl() {
      const text = urlInput.value;
      if (!text) return;
      function onSuccess() {
        copyBtn.innerHTML = '<i class="bi bi-check"></i>';
        setTimeout(() => { copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 1500);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(() => {
          urlInput.select();
          document.execCommand('copy');
          onSuccess();
        });
      } else {
        urlInput.select();
        document.execCommand('copy');
        onSuccess();
      }
    }
    copyBtn.addEventListener('click', copyUrl);
    urlInput.addEventListener('click', copyUrl);

    // Open URL in new tab
    if (openBtn) {
      openBtn.addEventListener('click', () => {
        const url = urlInput.value;
        if (url) window.open(url, '_blank');
      });
    }

    // QR fullscreen popup
    let qrOverlay = null;
    let qrAutoHide = null;
    function hideQrOverlay() {
      if (qrOverlay) { qrOverlay.remove(); qrOverlay = null; }
      if (qrAutoHide) { clearTimeout(qrAutoHide); qrAutoHide = null; }
    }
    qrImg.style.cursor = 'pointer';
    qrImg.addEventListener('click', () => {
      if (!qrImg.src) return;
      hideQrOverlay();
      qrOverlay = document.createElement('div');
      Object.assign(qrOverlay.style, {
        position:'fixed', top:'0', left:'0', width:'100vw', height:'100vh',
        background:'rgba(0,0,0,0.85)', display:'flex', alignItems:'center',
        justifyContent:'center', zIndex:'99999', cursor:'pointer'
      });
      const img = document.createElement('img');
      img.src = qrImg.src;
      Object.assign(img.style, { maxWidth:'80vmin', maxHeight:'80vmin', borderRadius:'12px', background:'#fff', padding:'16px' });
      qrOverlay.appendChild(img);
      document.body.appendChild(qrOverlay);
      qrOverlay.addEventListener('click', hideQrOverlay);
      qrAutoHide = setTimeout(hideQrOverlay, 8000);
      // Tell the Pi screen to show QR too
      if (window.socket) window.socket.emit('show_qr', { url: urlInput.value });
    });

    // Button handlers
    startBtn.addEventListener('click', startTunnel);
    stopBtn.addEventListener('click', stopTunnel);
    retryBtn.addEventListener('click', startTunnel);

    // Check current state on load
    fetch('/api/tunnel/status').then(r => r.json()).then(d => {
      if (d.state === 'active' && d.url) {
        badge.textContent = 'Active';
        badge.className = 'badge bg-success';
        urlInput.value = d.url;
        qrImg.src = `/api/tunnel/qr?url=${encodeURIComponent(d.url)}`;
        showState('active');
        setButtons(true);
      }
    }).catch(() => {});
  }

  /* ── Fixed-position tooltips (escape overflow:hidden) ──────────── */
  function initConfigTooltips() {
    let activeTip = null;
    function removeTip() { if (activeTip) { activeTip.remove(); activeTip = null; } }

    document.querySelectorAll('.config-tooltip-wrap[data-tip]').forEach(wrap => {
      wrap.addEventListener('mouseenter', function () {
        removeTip();
        const text = this.dataset.tip;
        if (!text) return;
        const tip = document.createElement('div');
        tip.className = 'config-tooltip-popup';
        tip.textContent = text;
        document.body.appendChild(tip);
        activeTip = tip;

        const iconRect = this.getBoundingClientRect();
        const tipW = tip.offsetWidth, tipH = tip.offsetHeight;
        const pad = 10;

        // Horizontal: center on the icon, clamp to viewport
        let left = iconRect.left + iconRect.width / 2 - tipW / 2;
        left = Math.max(pad, Math.min(left, window.innerWidth - tipW - pad));

        // Arrow points at the icon center
        const arrowX = iconRect.left + iconRect.width / 2 - left;
        tip.style.setProperty('--arrow-x', arrowX + 'px');

        // Vertical: prefer above, fall below if no room
        if (iconRect.top - tipH - pad > 0) {
          tip.style.top = (iconRect.top - tipH - pad) + 'px';
          tip.classList.add('arrow-bottom');
        } else {
          tip.style.top = (iconRect.bottom + pad) + 'px';
          tip.classList.add('arrow-top');
        }
        tip.style.left = left + 'px';
      });
      wrap.addEventListener('mouseleave', removeTip);
    });
    // Clean up if user scrolls away
    document.querySelectorAll('.config-panel-body, .tab-content, .config-wrap').forEach(el => {
      el.addEventListener('scroll', removeTip);
    });
  }

  function applyDependencies() {
    document.querySelectorAll('[data-dep-conds]').forEach(wrapper => {
      const conds = JSON.parse(wrapper.dataset.depConds);
      const section = wrapper.dataset.depSection;
      const visible = conds.every(cond => {
        const parentEl = document.getElementById(`cfg_${section}_${cond.field}`);
        if (!parentEl) return true;
        // Skip condition if the parent field's own wrapper is hidden
        const parentWrapper = parentEl.closest('[data-dep-conds]');
        if (parentWrapper && parentWrapper.style.display === 'none') return true;
        const val = parentEl.type === 'checkbox'
          ? (parentEl.checked ? 'true' : 'false')
          : parentEl.value.toLowerCase();
        return cond.values.map(v => v.toLowerCase()).includes(val);
      });
      wrapper.style.display = visible ? '' : 'none';
    });
  }

  function attachDependencyHandlers() {
    const attached = new Set();
    document.querySelectorAll('[data-dep-conds]').forEach(wrapper => {
      const conds = JSON.parse(wrapper.dataset.depConds);
      const section = wrapper.dataset.depSection;
      conds.forEach(cond => {
        const parentId = `cfg_${section}_${cond.field}`;
        if (!attached.has(parentId)) {
          attached.add(parentId);
          const parentEl = document.getElementById(parentId);
          if (parentEl) {
            parentEl.addEventListener('change', applyDependencies);
            if (parentEl.type === 'range') parentEl.addEventListener('input', applyDependencies);
          }
        }
      });
    });
  }

  const BACKEND_URLS = {
    'openai':    'https://api.openai.com/v1',
    'grok':      'https://api.x.ai/v1',
    'deepinfra': 'https://api.deepinfra.com/v1/openai',
  };

  function attachBackendUrlAutoFill() {
    const backendEl = document.getElementById('cfg_LLM_llm_backend');
    const urlEl = document.getElementById('cfg_LLM_base_url');
    if (!backendEl || !urlEl) return;
    // Remember the saved "other" URL so switching away and back restores it
    let savedOtherUrl = backendEl.value === 'other' ? urlEl.value : '';
    backendEl.addEventListener('change', (e) => {
      const prev = e.target._prevValue || backendEl.value;
      if (prev === 'other') savedOtherUrl = urlEl.value;
      const url = BACKEND_URLS[backendEl.value];
      if (url) {
        urlEl.value = url;
      } else if (backendEl.value === 'other') {
        urlEl.value = savedOtherUrl;
      }
      e.target._prevValue = backendEl.value;
    });
    backendEl._prevValue = backendEl.value;
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

    // Also collect skill config values from any skill panels
    const skillSaves = [];
    document.querySelectorAll('.skill-card[data-skill-name]').forEach(card => {
      const name = card.dataset.skillName;
      const schema = card._skillSchema || {};
      if (!Object.keys(schema).length) return;
      const panel = document.querySelector(`.skill-config-panel[data-skill-panel="${name}"]`);
      if (!panel) return;
      const values = {};
      panel.querySelectorAll('.skill-cfg-input').forEach(input => {
        const key = input.dataset.key;
        const fieldType = schema[key]?.type || 'text';
        if (input.type === 'checkbox') values[key] = input.checked;
        else if (fieldType === 'number') values[key] = Number(input.value);
        else values[key] = input.value;
      });
      if (Object.keys(values).length) skillSaves.push({ name, values });
    });

    fetch('/save_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
      .then(r=>r.json()).then(d => {
        if (d.success) {
          // Save skill configs in parallel
          const skillPromises = skillSaves.map(s =>
            fetch('/save_skill_config', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(s) })
          );
          Promise.all(skillPromises).then(() => {
            saveBtn.innerHTML='<i class="bi bi-check-circle-fill"></i> Saved!';
            saveBtn.classList.add('hud-btn-success');
            if (window.showToast) showToast('Configuration saved', 'success');
            setTimeout(()=>{
              saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false;
              showRebootConfirm();
            },1000);
          });
        } else { saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false; if (window.showToast) showToast('Error: '+(d.error||'Unknown'), 'error'); }
      }).catch(err=>{ saveBtn.innerHTML=origHtml; saveBtn.className=origClass; saveBtn.disabled=false; alert('Error: '+err.message); });
  }

  const configTab = $('config-tab');
  if (configTab) configTab.addEventListener('shown.bs.tab', () => {
    if ($('configForm').innerHTML.includes('Loading')) loadConfiguration();
  });

  const saveBtn = $('saveConfigBtn');
  if (saveBtn) saveBtn.addEventListener('click', e => { e.preventDefault(); saveConfiguration(); });

  /* ── Reboot Confirm Modal ─────────────────────── */
  window.showRebootConfirm = function() {
    // Source position: save button center
    const srcBtn = $('saveConfigBtn');
    const srcRect = srcBtn ? srcBtn.getBoundingClientRect() : null;
    const sx = srcRect ? srcRect.left + srcRect.width / 2 : window.innerWidth / 2;
    const sy = srcRect ? srcRect.top + srcRect.height / 2 : window.innerHeight;
    // Target: screen center (where the card will be)
    const tx = window.innerWidth / 2, ty = window.innerHeight / 2;

    // Build DOM
    const overlay = document.createElement('div');
    overlay.className = 'reboot-overlay';
    const canvas = document.createElement('canvas');
    overlay.appendChild(canvas);
    overlay.innerHTML += `
      <div class="reboot-card">
        <div class="reboot-icon"><i class="bi bi-arrow-repeat"></i></div>
        <div class="reboot-title">REBOOT REQUIRED</div>
        <p class="reboot-subtitle">Settings saved successfully.<br>Reboot now to apply changes?</p>
        <div class="reboot-actions">
          <button class="hud-btn hud-btn-ghost" id="rebootNo">Later</button>
          <button class="hud-btn hud-btn-primary" id="rebootYes"><i class="bi bi-power"></i> Reboot Now</button>
        </div>
      </div>`;
    overlay.insertBefore(canvas, overlay.firstChild);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => requestAnimationFrame(() => overlay.classList.add('active')));

    // Particle system
    const ctx = canvas.getContext('2d');
    let particles = [], animId = 0;
    function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
    resize(); window.addEventListener('resize', resize);

    const accentRGB = getComputedStyle(document.documentElement)
      .getPropertyValue('--accent-rgb').trim().split(',').map(Number);
    const N = 50;

    // Spawn all particles at the save button — each gets a random
    // delay so they stream out in a staggered burst, not all at once.
    for (let i = 0; i < N; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 1.5 + Math.random() * 3;
      particles.push({
        x: sx, y: sy,
        // Initial burst velocity toward card center + random spread
        vx: (tx - sx) * 0.008 + Math.cos(angle) * speed,
        vy: (ty - sy) * 0.008 + Math.sin(angle) * speed,
        r: Math.random() * 2.2 + 0.6,
        a: 0,                            // fades in
        maxA: Math.random() * 0.6 + 0.2,
        life: 0,
        delay: i * 0.6,                  // stagger frames
        phase: Math.random() * Math.PI * 2  // orbit offset
      });
    }

    const startTime = performance.now();
    function drawParticles(now) {
      const elapsed = (now - startTime) / 16.67; // frame count approx
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        if (elapsed < p.delay) continue; // still waiting
        p.life++;

        // Phase 1 (life < 60): fly toward card center with damping
        // Phase 2 (life >= 60): gentle orbit around card center
        if (p.life < 60) {
          // Attract toward card center
          const dx = tx - p.x, dy = ty - p.y;
          p.vx += dx * 0.003;
          p.vy += dy * 0.003;
          // Damping
          p.vx *= 0.97;
          p.vy *= 0.97;
          p.x += p.vx;
          p.y += p.vy;
          // Fade in
          p.a = Math.min(p.maxA, p.a + 0.03);
        } else {
          // Orbit: gentle circular drift around card
          const orbitR = 80 + (p.r * 40);
          const t = (p.life - 60) * 0.008 + p.phase;
          const goalX = tx + Math.cos(t) * orbitR;
          const goalY = ty + Math.sin(t) * orbitR * 0.6;
          p.x += (goalX - p.x) * 0.03;
          p.y += (goalY - p.y) * 0.03;
          // Subtle pulse
          p.a = p.maxA * (0.7 + 0.3 * Math.sin(t * 2));
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${accentRGB[0]},${accentRGB[1]},${accentRGB[2]},${p.a})`;
        ctx.fill();
      }
      animId = requestAnimationFrame(drawParticles);
    }
    animId = requestAnimationFrame(drawParticles);

    function close() {
      overlay.classList.remove('active');
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
      setTimeout(() => overlay.remove(), 400);
    }

    overlay.querySelector('#rebootNo').onclick = close;
    overlay.querySelector('#rebootYes').onclick = function() {
      this.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Rebooting…';
      this.disabled = true;
      overlay.querySelector('#rebootNo').disabled = true;
      if (window.showToast) showToast('Rebooting...', 'success');
      fetch('/reboot_program', { method: 'POST' }).catch(() => {});
      setTimeout(close, 2000);
    };
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  };
})();


// ── TAB RESET LOGIC ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const bodyTab = $('body-tab');

  if (bodyTab) bodyTab.addEventListener('hide.bs.tab', () => {
    const lh=+$('leftHeight').value, rh=+$('rightHeight').value,
          ll=+$('leftLeg').value,    rl=+$('rightLeg').value;
    const lm=+$('leftMain').value, lf=+$('leftForearm').value, lha=+$('leftHand').value,
          rm=+$('rightMain').value, rf=+$('rightForearm').value, rha=+$('rightHand').value;
    if (lh!==50||rh!==50||ll!==50||rl!==50||lm!==1||lf!==1||lha!==1||rm!==1||rf!==1||rha!==1) resetBody();
  });

  document.querySelectorAll('.custom-tab').forEach(tab => {
    tab.addEventListener('shown.bs.tab', e => {
      const id = e.target.getAttribute('data-bs-target')?.replace('#','');
      if (id==='body') {
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
  var consoleLines = [];  // rolling buffer of console strings
  var MAX_CONSOLE = 200;
  var pollInterval = null;
  var logHead = 0;  // cursor for incremental log fetching

  function renderConsole() {
    var el = document.getElementById('nxConsole');
    if (!el) return;
    el.innerHTML = consoleLines.map(function (l) {
      var safe = l.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return '<div class="nexus-console-line">' + safe + '</div>';
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
  }

  function fetchMetrics() {
    fetch('/api/system/metrics')
      .then(function (r) { return r.json(); })
      .then(updateMetrics)
      .catch(function () {});
  }

  function fetchLogs() {
    fetch('/api/console/logs?since=' + logHead)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.lines && data.lines.length) {
          for (var i = 0; i < data.lines.length; i++) {
            consoleLines.push(data.lines[i]);
          }
          while (consoleLines.length > MAX_CONSOLE) consoleLines.shift();
          renderConsole();
        }
        logHead = data.head;
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
      fetchLogs();
      if (!pollInterval) {
        pollInterval = setInterval(function () {
          if (nexusActive) {
            fetchMetrics();
            fetchLogs();
          }
        }, 2000);
      }
    });

    nexusTab.addEventListener('hide.bs.tab', function () {
      nexusActive = false;
    });
  });
})();


// ── MOBILE SWIPE NAV ─────────────────────────────────────────────────────────
(function () {
  const TAB_IDS = ['chat', 'motion', 'body', 'emotions', 'wifi', 'config', 'dashboard', 'nexus'];
  const TAB_BTN_IDS = ['chat-tab', 'motion-tab', 'body-tab', 'emotions-tab', 'wifi-tab', 'config-tab', 'dashboard-tab', 'nexus-tab'];
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
  let touchOnSlider = false; // ignore swipe when interacting with range inputs

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
      // skip swipe when touching range sliders or their containers
      var el = e.target;
      touchOnSlider = (el.tagName === 'INPUT' && el.type === 'range') ||
                      !!(el.closest && el.closest('.servo-card, .body-speed'));
      direction = null;
      isSwiping = false;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchDeltaX = 0;
      track.classList.remove('animating');
    }, { passive: true });

    tabContent.addEventListener('touchmove', function (e) {
      if (!isMobile || touchOnSlider) return;

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


// ── CHARACTER EDITOR ─────────────────────────────────────────────────────────
(function () {
  const TRAIT_NAMES = [
    'verbosity','humor','sarcasm','honesty','empathy',
    'curiosity','confidence','formality','adaptability','discipline',
    'imagination','emotional_stability','pragmatism','optimism',
    'resourcefulness','cheerfulness','engagement','respectfulness'
  ];

  const JSON_FIELDS = [
    'char_name', 'description', 'personality', 'scenario',
    'char_persona', 'world_scenario', 'first_mes', 'mes_example'
  ];

  let currentCharName = null;
  let currentCharData = null;
  let currentTraits = null;
  let charListLoaded = false;

  function show(id) { const el = document.getElementById(id); if (el) el.style.display = ''; }
  function hide(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }

  async function loadCharacterList() {
    const sel = document.getElementById('charedSelect');
    if (!sel) return;
    try {
      const d = await fetch('/api/characters').then(r => r.json());
      const names = d.characters || [];
      sel.innerHTML = '<option value="">— select character —</option>' +
        names.map(n => `<option value="${n}">${n}</option>`).join('');
      charListLoaded = true;
      // Pre-select active character
      const active = (window.APP_CONFIG && window.APP_CONFIG.charName) || '';
      if (active && names.includes(active)) {
        sel.value = active;
        loadCharacter(active);
      }
    } catch (e) {
      sel.innerHTML = '<option value="">Error loading characters</option>';
    }
  }

  async function loadCharacter(name) {
    if (!name) { hide('charedBody'); hide('charedLoading'); show('charedEmpty'); return; }

    hide('charedBody'); hide('charedEmpty'); show('charedLoading');

    try {
      const d = await fetch(`/api/character/${encodeURIComponent(name)}`).then(r => r.json());
      if (d.error) throw new Error(d.error);

      currentCharName = name;
      currentCharData = d.character || {};
      currentTraits   = d.traits   || {};

      JSON_FIELDS.forEach(key => {
        const el = document.getElementById('ched_' + key);
        if (el) el.value = currentCharData[key] || '';
      });

      buildTraitsGrid(currentTraits);
      hide('charedLoading'); hide('charedEmpty'); show('charedBody');
    } catch (e) {
      hide('charedLoading'); show('charedEmpty');
      if (window.showToast) showToast('Failed to load character: ' + e.message, 'error');
    }
  }

  function buildTraitsGrid(traits) {
    const grid = document.getElementById('charedTraitsGrid');
    if (!grid) return;
    grid.innerHTML = TRAIT_NAMES.map(name => {
      const val = traits[name] !== undefined ? parseInt(traits[name]) : 50;
      const label = name.replace(/_/g, ' ').toUpperCase();
      return `
        <div class="chared-trait">
          <div class="chared-trait-header">
            <span class="chared-trait-name">${label}</span>
            <span class="chared-trait-val" id="traitVal_${name}">${val}</span>
          </div>
          <input type="range" min="0" max="100" value="${val}"
            id="trait_${name}" class="chared-trait-slider"
            oninput="document.getElementById('traitVal_${name}').textContent=this.value">
        </div>`;
    }).join('');
  }

  async function saveCharacter() {
    if (!currentCharName) return;

    const btn = document.getElementById('saveCharBtn');
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="hud-spinner" style="width:12px;height:12px;border-width:2px;margin-right:6px;"></span>SAVING';

    const charData = Object.assign({}, currentCharData);
    JSON_FIELDS.forEach(key => {
      const el = document.getElementById('ched_' + key);
      if (el) charData[key] = el.value;
    });
    if (charData.char_name) charData.name = charData.char_name;

    const traits = {};
    TRAIT_NAMES.forEach(name => {
      const el = document.getElementById('trait_' + name);
      if (el) traits[name] = parseInt(el.value);
    });

    try {
      const r = await fetch(`/api/character/${encodeURIComponent(currentCharName)}/save`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ character: charData, traits })
      });
      const d = await r.json();
      if (!r.ok || d.error) throw new Error(d.error || 'Save failed');
      if (window.showToast) showToast('Character saved', 'success');
      currentCharData = charData;
      currentTraits   = traits;
    } catch (e) {
      if (window.showToast) showToast('Save failed: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }

  // Called by loadConfiguration() after the config form HTML is injected
  window.initCharacterEditor = function () {
    charListLoaded = false;
    currentCharName = null;

    const sel = document.getElementById('charedSelect');
    if (sel) sel.addEventListener('change', function () { loadCharacter(this.value); });

    const saveBtn = document.getElementById('saveCharBtn');
    if (saveBtn) saveBtn.addEventListener('click', saveCharacter);

    document.querySelectorAll('.chared-inner-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.chared-inner-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.chared-panel').forEach(p => p.classList.remove('active'));
        this.classList.add('active');
        const panel = document.getElementById('charedPanel_' + this.dataset.charedTab);
        if (panel) panel.classList.add('active');
      });
    });
  };

  // Trigger character list load when the editor panel opens
  window.onCharacterEditorOpen = function (preselect) {
    if (!charListLoaded) {
      loadCharacterList().then(() => {
        if (preselect) {
          const sel = document.getElementById('charedSelect');
          if (sel) { sel.value = preselect; loadCharacter(preselect); }
        }
      });
    } else if (preselect) {
      const sel = document.getElementById('charedSelect');
      if (sel) { sel.value = preselect; loadCharacter(preselect); }
    }
  };
})();

/* ═══════════════════════════════════════════════════════════════════
   DASHBOARD — Memory Graph, Mood Analytics, Audit Log, Topics
   ═══════════════════════════════════════════════════════════════════ */
(function () {
  var dashLoaded = false;
  var graphSim = null;

  // Axis group colors — each of the 8 radar axes gets a distinct color
  var axisColors = {
    joy:       '#66bb6a',   // green
    anger:     '#ef5350',   // red
    sadness:   '#5c6bc0',   // blue
    fear:      '#7e57c2',   // purple
    love:      '#ec407a',   // pink
    curiosity: '#29b6f6',   // cyan
    surprise:  '#ffca28',   // amber
    neutral:   '#78909c'    // gray
  };
  // Map every GoEmotions label → its axis for color lookup
  var emotionToAxis = {
    joy:'joy', amusement:'joy', excitement:'joy', optimism:'joy', pride:'joy', relief:'joy',
    anger:'anger', annoyance:'anger', disapproval:'anger', disgust:'anger',
    sadness:'sadness', disappointment:'sadness', grief:'sadness', remorse:'sadness', embarrassment:'sadness',
    fear:'fear', nervousness:'fear',
    love:'love', admiration:'love', caring:'love', desire:'love', gratitude:'love', approval:'love',
    curiosity:'curiosity', confusion:'curiosity', realization:'curiosity',
    surprise:'surprise',
    neutral:'neutral'
  };
  // Ordered list: emotions grouped by axis for timeline y-axis
  var emotionOrder = [
    'joy','amusement','excitement','optimism','pride','relief',
    'love','admiration','caring','desire','gratitude','approval',
    'curiosity','confusion','realization',
    'surprise',
    'neutral',
    'fear','nervousness',
    'sadness','disappointment','grief','remorse','embarrassment',
    'anger','annoyance','disapproval','disgust'
  ];
  function getMoodColor(m) {
    var key = (m||'').toLowerCase();
    var axis = emotionToAxis[key] || key;
    return axisColors[axis] || '#78909c';
  }

  // Track which sub-panels have been rendered
  var _panelRendered = {};
  var _moodData = null;
  var _topicsData = null;

  // Sub-tab switching
  document.querySelectorAll('.dash-subtab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.dash-subtab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.dash-panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      var panelId = btn.getAttribute('data-panel');
      var panel = document.getElementById(panelId);
      if (panel) panel.classList.add('active');
      // Deferred render for panels that need visible containers
      requestAnimationFrame(function () {
        if (panelId === 'dshMood' && _moodData && !_panelRendered.mood) {
          _panelRendered.mood = true;
          renderEmotionalRadar(_moodData.emotional_state);
          renderMoodTimeline(_moodData.timeline);
          renderActivityHeatmap(_moodData.activity_heatmap || {});
        }
        if (panelId === 'dshTopicsPanel' && _topicsData && !_panelRendered.topics) {
          _panelRendered.topics = true;
          renderTopicsGraph(_topicsData);
        }
        if (panelId === 'dshPrompt' && _promptInteractions.length && !_panelRendered.prompt) {
          _panelRendered.prompt = true;
          populatePromptDropdown();
        }
      });
    });
  });

  // Detail drawer
  var drawer = document.getElementById('dshDetailDrawer');
  var drawerClose = document.getElementById('dshDetailClose');
  if (drawerClose) drawerClose.addEventListener('click', function () { drawer.classList.remove('open'); });

  // Currently selected node for operations
  var _selectedNode = null;

  // ── Editable field helpers ──
  var _editableFields = { 'user_input': true, 'bot_response': true, 'speaker': true };
  var _editableTopicFields = { 'topic': true, 'mention_count': true };

  function _makeEditableField(key, value, nodeType, nodeIndex) {
    var isEditable = (nodeType === 'memory' && _editableFields[key]) ||
                     (nodeType === 'topic' && _editableTopicFields[key]);
    var displayKey = key.replace(/_/g, ' ');
    if (!isEditable) {
      return '<div class="detail-row"><span class="detail-label">' + displayKey + '</span><br>' + escapeHtml(String(value)) + '</div>';
    }
    var escapedVal = escapeHtml(String(value));
    return '<div class="detail-row detail-row-editable">' +
      '<span class="detail-label">' + displayKey + ' <i class="bi bi-pencil detail-edit-icon"></i></span>' +
      '<div class="detail-editable" contenteditable="true" spellcheck="false"' +
      ' data-field="' + key + '" data-type="' + nodeType + '" data-index="' + nodeIndex + '"' +
      ' data-original="' + escapedVal + '">' + escapedVal + '</div></div>';
  }

  function _saveEditableField(el) {
    var field = el.getAttribute('data-field');
    var nodeType = el.getAttribute('data-type');
    var index = parseInt(el.getAttribute('data-index'), 10);
    var original = el.getAttribute('data-original');
    var newVal = el.textContent.trim();
    if (newVal === original || !newVal) {
      el.textContent = original;
      return;
    }
    el.classList.add('detail-saving');
    var url;
    if (nodeType === 'memory') {
      url = '/api/dashboard/memory/edit';
    } else if (nodeType === 'topic') {
      url = '/api/dashboard/topic/edit';
    } else { return; }
    var fields = {};
    fields[field] = newVal;
    var body = JSON.stringify({ index: index, fields: fields });

    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        el.classList.remove('detail-saving');
        if (data.success) {
          el.classList.add('detail-saved');
          el.setAttribute('data-original', newVal);
          // Update the node label in the graph if topic name changed
          if (nodeType === 'topic' && field === 'topic' && _selectedNode) {
            _selectedNode.name = newVal;
            d3.selectAll('text').filter(function (d) { return d && d.id === _selectedNode.id; })
              .text(newVal.length > 20 ? newVal.substring(0, 18) + '..' : newVal);
            var titleEl = document.getElementById('dshDetailTitle');
            if (titleEl) titleEl.textContent = newVal;
          }
          // Update node details in memory for graph label
          if (nodeType === 'memory' && _selectedNode && _selectedNode.details) {
            _selectedNode.details[field] = newVal;
            if (field === 'user_input') {
              _selectedNode.name = newVal.substring(0, 50);
              d3.selectAll('text').filter(function (d) { return d && d.id === _selectedNode.id; })
                .text(newVal.length > 20 ? newVal.substring(0, 18) + '..' : newVal);
              var titleEl = document.getElementById('dshDetailTitle');
              if (titleEl) titleEl.textContent = newVal.substring(0, 50);
            }
          }
          setTimeout(function () { el.classList.remove('detail-saved'); }, 1500);
        } else {
          el.classList.add('detail-error');
          setTimeout(function () { el.classList.remove('detail-error'); el.textContent = original; }, 2000);
        }
      }).catch(function () {
        el.classList.remove('detail-saving');
        el.classList.add('detail-error');
        setTimeout(function () { el.classList.remove('detail-error'); el.textContent = original; }, 2000);
      });
  }

  // Global blur handler for editable fields (auto-save on click off)
  document.addEventListener('focusout', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('detail-editable')) {
      _saveEditableField(e.target);
    }
  });
  // Also save on Enter key (but allow Shift+Enter for newlines)
  document.addEventListener('keydown', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('detail-editable') && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.target.blur();
    }
  });

  function _addDeleteButton(actions, nodeType, nodeIndex, node) {
    var isMemory = nodeType === 'memory';
    var label = isMemory ? 'Delete Memory' : 'Delete Topic';
    var url = isMemory ? '/api/dashboard/memory/delete' : '/api/dashboard/topic/delete';

    var btn = document.createElement('button');
    btn.className = 'dash-delete-btn';
    btn.innerHTML = '<i class="bi bi-trash3"></i> ' + label;
    var clickCount = 0;
    btn.addEventListener('click', function () {
      clickCount++;
      if (clickCount === 1) {
        btn.classList.add('confirm');
        btn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Click again to confirm';
        setTimeout(function () { clickCount = 0; btn.classList.remove('confirm'); btn.innerHTML = '<i class="bi bi-trash3"></i> ' + label; }, 3000);
      } else {
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Deleting...';
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: nodeIndex })
        }).then(function (r) { return r.json(); }).then(function (data) {
          if (data.success) {
            btn.innerHTML = '<i class="bi bi-check2"></i> Deleted';
            btn.style.color = '#39ff14';
            btn.style.borderColor = 'rgba(57,255,20,0.3)';
            d3.selectAll('circle').filter(function (d) { return d.id === node.id; }).transition().duration(300).attr('r', 0).remove();
            d3.selectAll('line').filter(function (d) { return d.source.id === node.id || d.target.id === node.id; }).transition().duration(300).attr('opacity', 0).remove();
            if (isMemory) {
              var memEl = document.getElementById('dshMemories');
              if (memEl && data.remaining !== undefined) memEl.textContent = data.remaining;
            } else {
              var topEl = document.getElementById('dshTopics');
              if (topEl && data.remaining !== undefined) topEl.textContent = data.remaining;
            }
            setTimeout(function () { drawer.classList.remove('open'); }, 800);
          } else {
            btn.innerHTML = '<i class="bi bi-x-circle"></i> ' + (data.error || 'Failed');
            btn.style.color = '#ef5350';
            btn.disabled = false;
            clickCount = 0;
          }
        }).catch(function () {
          btn.innerHTML = '<i class="bi bi-x-circle"></i> Error';
          btn.disabled = false;
          clickCount = 0;
        });
      }
    });
    actions.appendChild(btn);
  }

  function showDetail(node) {
    _selectedNode = node;
    var title = document.getElementById('dshDetailTitle');
    var body = document.getElementById('dshDetailBody');
    var actions = document.getElementById('dshDetailActions');
    title.textContent = node.name || node.id;

    var isMemory = node.group === 'memory' && node.id && node.id.startsWith('mem_');
    var isTopic = node.group === 'topic' && node.id && node.id.startsWith('topic_');
    var nodeIndex = -1;
    if (isMemory) nodeIndex = parseInt(node.id.replace('mem_', ''), 10);
    if (isTopic) nodeIndex = parseInt(node.id.replace('topic_', ''), 10);

    var html = '';
    html += '<div class="detail-row"><span class="detail-label">Type</span><br>' + (node.group || '--') + '</div>';
    if (node.details) {
      var nodeType = isMemory ? 'memory' : (isTopic ? 'topic' : '');
      Object.keys(node.details).forEach(function (k) {
        var v = node.details[k];
        if (v !== '' && v !== null && v !== undefined) {
          if (nodeType && nodeIndex >= 0) {
            html += _makeEditableField(k, v, nodeType, nodeIndex);
          } else {
            html += '<div class="detail-row"><span class="detail-label">' + k.replace(/_/g, ' ') + '</span><br>' + escapeHtml(String(v)) + '</div>';
          }
        }
      });
    }
    body.innerHTML = html;

    // Action buttons (delete for memories and topics)
    actions.innerHTML = '';
    if (isMemory && !isNaN(nodeIndex)) {
      _addDeleteButton(actions, 'memory', nodeIndex, node);
    } else if (isTopic && !isNaN(nodeIndex)) {
      _addDeleteButton(actions, 'topic', nodeIndex, node);
    }

    drawer.classList.add('open');
  }

  // ── Refresh stats strip (lightweight, safe to call repeatedly) ──
  var _emotionEnabled = true; // assume true until stats tell us otherwise

  function refreshStats() {
    fetch('/api/dashboard/stats').then(function (r) { return r.json(); }).then(function (d) {
      var el = function (id) { return document.getElementById(id); };
      if (el('dshMemories'))     el('dshMemories').textContent = d.memories || 0;
      if (el('dshTopics'))       el('dshTopics').textContent = d.topics || 0;
      if (el('dshInteractions')) el('dshInteractions').textContent = d.interactions || 0;

      _emotionEnabled = d.emotion_enabled !== false;

      if (el('dshEmotion')) {
        if (_emotionEnabled) {
          var emo = d.current_emotion || 'neutral';
          el('dshEmotion').textContent = emo;
          el('dshEmotion').style.color = getMoodColor(emo);
          el('dshEmotion').parentElement.style.display = '';
        } else {
          el('dshEmotion').parentElement.style.display = 'none';
        }
      }

      // Disable/enable the Mood sub-tab
      var moodBtn = document.querySelector('.dash-subtab[data-panel="dshMood"]');
      if (moodBtn) {
        if (_emotionEnabled) {
          moodBtn.disabled = false;
          moodBtn.style.opacity = '';
          moodBtn.style.pointerEvents = '';
          moodBtn.title = '';
        } else {
          moodBtn.disabled = true;
          moodBtn.style.opacity = '0.3';
          moodBtn.style.pointerEvents = 'none';
          moodBtn.title = 'Enable emotions in config to use this panel';
        }
      }
    }).catch(function () {});
  }

  // ── Load dashboard data (heavy, runs once) ──
  function loadDashboard() {
    dashLoaded = true;
    refreshStats();
    loadGraph();
    loadMoodData();
    loadLog();
    loadTopicsData();
    loadPrompt();
  }

  // ── Live dashboard updates via SocketIO ──
  function refreshActiveDashboardPanel() {
    if (!dashLoaded) return;
    // Always refresh the stats strip
    refreshStats();
    // Invalidate render cache so inactive panels re-render on next visit
    _panelRendered = {};
    // Find which sub-panel is active and refresh it
    var activePanel = document.querySelector('.dash-panel.active');
    if (!activePanel) return;
    var panelId = activePanel.id;
    if (panelId === 'dshMood') {
      fetch('/api/dashboard/mood').then(function (r) { return r.json(); }).then(function (data) {
        _moodData = data;
        renderEmotionalRadar(data.emotional_state);
        renderMoodTimeline(data.timeline);
        renderActivityHeatmap(data.activity_heatmap || {});
      }).catch(function () {});
    } else if (panelId === 'dshLog') {
      loadLog();
    } else if (panelId === 'dshGraph') {
      loadGraph();
    } else if (panelId === 'dshTopicsPanel') {
      loadTopicsData();
    } else if (panelId === 'dshPrompt') {
      loadPrompt();
    }
  }

  var _dashRefreshTimer = null;
  function debouncedDashRefresh() {
    if (_dashRefreshTimer) clearTimeout(_dashRefreshTimer);
    _dashRefreshTimer = setTimeout(function () {
      _dashRefreshTimer = null;
      refreshActiveDashboardPanel();
    }, 1000);
  }

  function _bindDashSocketListeners() {
    if (!window.socket) return;
    window.socket.on('emotion_change', function () {
      debouncedDashRefresh();
    });
    window.socket.on('bot_message', function () {
      debouncedDashRefresh();
    });
  }
  // Socket may not exist yet (created in DOMContentLoaded), so defer binding
  if (window.socket) {
    _bindDashSocketListeners();
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      // Small delay to ensure socket is created first
      setTimeout(_bindDashSocketListeners, 100);
    });
  }

  // ── GRAPH ──
  function loadGraph() {
    var maxNodes = 500, hours = 0;
    var slider = document.getElementById('dshGraphMaxNodes');
    var hoursSelect = document.getElementById('dshGraphHours');
    if (slider) maxNodes = parseInt(slider.value) || 500;
    if (hoursSelect) hours = parseInt(hoursSelect.value) || 0;
    fetch('/api/dashboard/graph?max_memories=' + maxNodes + '&hours=' + hours)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderGraph(data.nodes, data.links);
        var countEl = document.getElementById('dshGraphNodeCount');
        if (countEl) countEl.textContent = data.nodes.length + ' nodes';
      }).catch(function () {});
  }

  // Graph control event listeners
  (function () {
    var slider = document.getElementById('dshGraphMaxNodes');
    var valLabel = document.getElementById('dshGraphMaxNodesVal');
    var hoursSelect = document.getElementById('dshGraphHours');
    var debounceTimer = null;
    if (slider) {
      slider.addEventListener('input', function () {
        if (valLabel) valLabel.textContent = slider.value;
      });
      slider.addEventListener('change', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(loadGraph, 300);
      });
    }
    if (hoursSelect) {
      hoursSelect.addEventListener('change', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(loadGraph, 300);
      });
    }
  })();

  function renderGraph(nodes, links) {
    var container = document.getElementById('dshGraphSvg');
    if (!container || typeof d3 === 'undefined') return;
    container.innerHTML = '';

    var w = container.clientWidth || 600;
    var h = Math.max(container.clientHeight || 450, 450);

    var svg = d3.select(container).append('svg')
      .attr('viewBox', '0 0 ' + w + ' ' + h)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    // Glow filter for hub/core nodes
    var defs = svg.append('defs');
    var filter = defs.append('filter').attr('id', 'glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    filter.append('feMerge').selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic']).enter().append('feMergeNode')
      .attr('in', function (d) { return d; });

    // Zoom + pan
    var g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.2, 5]).on('zoom', function (e) {
      g.attr('transform', e.transform);
    }));

    // ── Build parallel-link index so overlapping links curve apart ──
    var linkCounts = {};  // "nodeA|nodeB" -> count
    var linkIndex = {};   // same key -> next index
    links.forEach(function (l) {
      var sId = typeof l.source === 'object' ? l.source.id : l.source;
      var tId = typeof l.target === 'object' ? l.target.id : l.target;
      var key = sId < tId ? sId + '|' + tId : tId + '|' + sId;
      linkCounts[key] = (linkCounts[key] || 0) + 1;
    });
    links.forEach(function (l) {
      var sId = typeof l.source === 'object' ? l.source.id : l.source;
      var tId = typeof l.target === 'object' ? l.target.id : l.target;
      var key = sId < tId ? sId + '|' + tId : tId + '|' + sId;
      linkIndex[key] = (linkIndex[key] || 0);
      l._total = linkCounts[key];
      l._index = linkIndex[key];
      linkIndex[key]++;
    });

    // Distance based on node relationship
    function linkDist(d) {
      var sg = (d.source.group || d.source), tg = (d.target.group || d.target);
      if (sg === 'core' || tg === 'core') return 160;
      if (sg === 'hub' || tg === 'hub') return 110;
      if (sg === 'cluster' || tg === 'cluster') return 70;
      if (sg === 'category' || tg === 'category') return 70;
      if (sg === 'person' && tg === 'cluster') return 100;
      if (sg === 'overflow' || tg === 'overflow') return 35;
      return 45;
    }

    var simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(function (d) { return d.id; }).distance(linkDist).strength(0.35))
      .force('charge', d3.forceManyBody().strength(function (d) {
        if (d.group === 'core') return -500;
        if (d.group === 'hub') return -300;
        if (d.group === 'cluster' || d.group === 'category' || d.group === 'person') return -180;
        if (d.group === 'overflow') return -15;
        return -50;
      }))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide().radius(function (d) { return (d.size || 6) + 6; }).strength(0.8))
      .force('x', d3.forceX(w / 2).strength(0.025))
      .force('y', d3.forceY(h / 2).strength(0.025))
      .alphaDecay(0.02);  // slower settling for better layout

    // ── Links as curved paths ──
    function linkColor(d) {
      var sg = typeof d.source === 'object' ? d.source.group : '';
      var tg = typeof d.target === 'object' ? d.target.group : '';
      if (sg === 'person' && tg === 'cluster') return 'rgba(236,64,122,0.18)';
      if (sg === 'person' && tg === 'topic') return 'rgba(236,64,122,0.12)';
      return 'rgba(0,229,255,0.12)';
    }

    var link = g.append('g').selectAll('path')
      .data(links).enter().append('path')
      .attr('fill', 'none')
      .attr('stroke', linkColor)
      .attr('stroke-width', function (d) {
        var sg = typeof d.source === 'object' ? d.source.group : '';
        if (sg === 'core') return 2;
        if (sg === 'hub') return 1.5;
        return 0.8;
      })
      .attr('stroke-dasharray', function (d) {
        var sg = typeof d.source === 'object' ? d.source.group : '';
        var tg = typeof d.target === 'object' ? d.target.group : '';
        if (sg === 'person' && (tg === 'cluster' || tg === 'topic')) return '4,3';
        return null;
      });

    // Compute curved path for each link
    function linkPath(d) {
      var sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y;
      // Straight line for single links between a pair
      if (d._total <= 1) {
        return 'M' + sx + ',' + sy + 'L' + tx + ',' + ty;
      }
      // Curve parallel links apart using quadratic bezier
      var dx = tx - sx, dy = ty - sy;
      var dist = Math.sqrt(dx * dx + dy * dy) || 1;
      // Perpendicular offset: alternate sides, spread by index
      var offset = (d._index - (d._total - 1) / 2) * Math.min(25, dist * 0.2);
      var mx = (sx + tx) / 2 + (-dy / dist) * offset;
      var my = (sy + ty) / 2 + (dx / dist) * offset;
      return 'M' + sx + ',' + sy + 'Q' + mx + ',' + my + ' ' + tx + ',' + ty;
    }

    // Nodes
    var node = g.append('g').selectAll('circle')
      .data(nodes).enter().append('circle')
      .attr('r', function (d) { return d.size || 6; })
      .attr('fill', function (d) { return d.color || '#42a5f5'; })
      .attr('stroke', function (d) {
        if (d.group === 'core') return '#b44dff';
        if (d.group === 'hub' || d.group === 'category') return 'rgba(255,255,255,0.15)';
        return 'rgba(0,229,255,0.15)';
      })
      .attr('stroke-width', function (d) {
        if (d.group === 'core') return 3;
        if (d.group === 'hub') return 2;
        return 0.5;
      })
      .attr('opacity', function (d) {
        if (d.group === 'memory' || d.group === 'topic') return 0.7;
        return 0.9;
      })
      .attr('filter', function (d) {
        if (d.group === 'core' || d.group === 'hub') return 'url(#glow)';
        return null;
      })
      .style('cursor', 'pointer')
      .on('click', function (event, d) { showDetail(d); })
      .on('mouseover', function (event, d) {
        // Highlight connected links
        link.attr('stroke-opacity', function (l) {
          return (l.source === d || l.target === d) ? 1 : 0.15;
        }).attr('stroke', function (l) {
          return (l.source === d || l.target === d) ? 'rgba(0,229,255,0.6)' : 'rgba(0,229,255,0.08)';
        });
        // Show tooltip
        tooltip.style('display', 'block')
          .html(d.name + (d.group ? '<br><span style="color:rgba(0,229,255,0.5);font-size:9px">' + d.group + '</span>' : ''));
      })
      .on('mousemove', function (event) {
        tooltip.style('left', (event.offsetX + 12) + 'px').style('top', (event.offsetY - 10) + 'px');
      })
      .on('mouseout', function () {
        link.attr('stroke-opacity', 1).attr('stroke', linkColor);
        tooltip.style('display', 'none');
      })
      .call(d3.drag()
        .on('start', function (event, d) {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', function (event, d) { d.fx = event.x; d.fy = event.y; })
        .on('end', function (event, d) {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    // Tooltip div
    var tooltip = d3.select(container).append('div')
      .style('position', 'absolute').style('display', 'none')
      .style('background', 'rgba(10,18,32,0.9)').style('border', '1px solid rgba(0,229,255,0.3)')
      .style('padding', '6px 10px').style('border-radius', '6px')
      .style('font-family', 'var(--font-mono)').style('font-size', '11px')
      .style('color', '#e2eaf2').style('pointer-events', 'none')
      .style('z-index', '100').style('max-width', '200px');

    // Labels for important nodes
    var labelNodes = nodes.filter(function (d) {
      return d.group === 'core' || d.group === 'hub' || d.group === 'person' || d.group === 'category' || d.group === 'cluster';
    });
    var labels = g.append('g').selectAll('text')
      .data(labelNodes).enter().append('text')
      .attr('class', 'dash-node-label')
      .attr('dy', function (d) { return (d.size || 8) + 12; })
      .attr('font-size', function (d) {
        if (d.group === 'core') return '12px';
        if (d.group === 'hub') return '10px';
        return '8px';
      })
      .attr('fill', function (d) {
        if (d.group === 'core' || d.group === 'hub') return d.color;
        return 'rgba(226,234,242,0.6)';
      })
      .text(function (d) {
        var n = d.name;
        return n.length > 20 ? n.substring(0, 18) + '..' : n;
      });

    simulation.on('tick', function () {
      link.attr('d', linkPath);
      node.attr('cx', function (d) { return d.x; })
          .attr('cy', function (d) { return d.y; });
      labels.attr('x', function (d) { return d.x; })
            .attr('y', function (d) { return d.y; });
    });

    graphSim = simulation;
  }

  // ── MOOD ──
  function loadMoodData() {
    fetch('/api/dashboard/mood').then(function (r) { return r.json(); }).then(function (data) {
      _moodData = data;
      // Only render if mood panel is currently visible
      var moodPanel = document.getElementById('dshMood');
      if (moodPanel && moodPanel.classList.contains('active')) {
        _panelRendered.mood = true;
        renderEmotionalRadar(data.emotional_state);
        renderMoodTimeline(data.timeline);
        renderActivityHeatmap(data.activity_heatmap || {});
      }
    }).catch(function () {});
  }

  function renderEmotionalRadar(state) {
    var el = document.getElementById('dshMoodBar');
    if (!el || typeof d3 === 'undefined') return;
    el.innerHTML = '';
    var entries = Object.entries(state || {});
    if (!entries.length) { el.innerHTML = '<div class="dash-log-empty">No emotional data yet — talk to TARS to build up the emotional profile</div>'; return; }

    // All emotions, keep backend order
    var labels = entries.map(function (e) { return e[0]; });
    var values = entries.map(function (e) { return e[1]; });
    var n = labels.length;

    // Size: fit within card, square aspect
    var labelMargin = 60;
    var containerW = el.clientWidth || 350;
    var size = Math.min(containerW, 380);
    var cx = size / 2, cy = size / 2;
    var maxR = (size / 2) - labelMargin;

    var svg = d3.select(el).append('svg')
      .attr('viewBox', '0 0 ' + size + ' ' + size)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    // Glow filter
    var defs = svg.append('defs');
    var filter = defs.append('filter').attr('id', 'radarGlow');
    filter.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'blur');
    var merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    var g = svg.append('g');

    // Helper: angle for axis i (start from top)
    function angle(i) { return (Math.PI * 2 * i / n) - Math.PI / 2; }
    function ptx(i, r) { return cx + r * Math.cos(angle(i)); }
    function pty(i, r) { return cy + r * Math.sin(angle(i)); }

    // Concentric grid rings (circles for clean look)
    var rings = [25, 50, 75, 100];
    rings.forEach(function (pct) {
      var r = maxR * pct / 100;
      g.append('circle')
        .attr('cx', cx).attr('cy', cy).attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', pct === 50 ? 'rgba(0,229,255,0.15)' : 'rgba(0,229,255,0.06)')
        .attr('stroke-width', pct === 50 ? 1 : 0.5);
      // Ring percentage label
      if (pct < 100) {
        g.append('text')
          .attr('x', cx + 3).attr('y', cy - r + 1)
          .attr('fill', 'rgba(0,229,255,0.2)')
          .attr('font-family', 'var(--font-mono)')
          .attr('font-size', '7px')
          .attr('dominant-baseline', 'auto')
          .text(pct + '%');
      }
    });

    // Axis spokes
    for (var i = 0; i < n; i++) {
      g.append('line')
        .attr('x1', cx).attr('y1', cy)
        .attr('x2', ptx(i, maxR)).attr('y2', pty(i, maxR))
        .attr('stroke', 'rgba(0,229,255,0.1)').attr('stroke-width', 0.5);
    }

    // Data polygon (filled area)
    var pts = [];
    for (var i = 0; i < n; i++) {
      var r = maxR * Math.min(values[i], 100) / 100;
      pts.push(ptx(i, r) + ',' + pty(i, r));
    }
    // Find dominant axis for polygon color
    var maxVal = 0, domIdx = 0;
    for (var i = 0; i < n; i++) { if (values[i] > maxVal) { maxVal = values[i]; domIdx = i; } }
    var domColor = maxVal > 0 ? getMoodColor(labels[domIdx]) : '#00e5ff';
    g.append('polygon').attr('points', pts.join(' '))
      .attr('fill', domColor)
      .attr('fill-opacity', 0.12)
      .attr('stroke', domColor)
      .attr('stroke-width', 2)
      .attr('stroke-linejoin', 'round')
      .attr('filter', 'url(#radarGlow)');

    // Data points on non-zero vertices
    for (var i = 0; i < n; i++) {
      if (values[i] <= 0) continue;
      var r = maxR * Math.min(values[i], 100) / 100;
      var color = getMoodColor(labels[i]);
      g.append('circle')
        .attr('cx', ptx(i, r)).attr('cy', pty(i, r))
        .attr('r', 4)
        .attr('fill', color)
        .attr('stroke', 'rgba(255,255,255,0.3)')
        .attr('stroke-width', 1);
    }

    // Axis labels: name + percentage on separate lines
    for (var i = 0; i < n; i++) {
      var labelR = maxR + 14;
      var a = angle(i);
      var cosA = Math.cos(a), sinA = Math.sin(a);
      var lx = cx + labelR * cosA;
      var ly = cy + labelR * sinA;
      var anchor = 'middle';
      if (cosA > 0.2) anchor = 'start';
      else if (cosA < -0.2) anchor = 'end';
      var val = Math.round(values[i]);
      var color = val > 0 ? getMoodColor(labels[i]) : 'rgba(226,234,242,0.35)';
      g.append('text')
        .attr('x', lx).attr('y', ly - 5)
        .attr('text-anchor', anchor)
        .attr('dominant-baseline', 'central')
        .attr('fill', color)
        .attr('font-family', 'var(--font-mono)')
        .attr('font-size', '9px')
        .attr('font-weight', 'bold')
        .text(labels[i]);
      g.append('text')
        .attr('x', lx).attr('y', ly + 7)
        .attr('text-anchor', anchor)
        .attr('dominant-baseline', 'central')
        .attr('fill', val > 0 ? 'rgba(226,234,242,0.6)' : 'rgba(226,234,242,0.2)')
        .attr('font-family', 'var(--font-mono)')
        .attr('font-size', '8px')
        .text(val + '%');
    }
  }

  function renderMoodTimeline(timeline) {
    var el = document.getElementById('dshMoodTimeline');
    if (!el || typeof d3 === 'undefined') return;
    el.innerHTML = '';
    if (!timeline.length) { el.innerHTML = '<div class="dash-log-empty">No timeline data yet</div>'; return; }

    var parseTime = function (ts) {
      try { return new Date(ts.replace(' ', 'T')); } catch (e) { return new Date(); }
    };
    var data = timeline.map(function (d) {
      return { time: parseTime(d.timestamp), mood: d.mood, axis: d.axis || emotionToAxis[d.mood] || d.mood };
    });

    // Always show all 28 emotions in grouped order
    var moods = emotionOrder.slice();

    // Figure out which axis groups are present and where separators go
    var axisGroups = [];
    var lastAxis = null;
    moods.forEach(function (m, i) {
      var axis = emotionToAxis[m] || m;
      if (axis !== lastAxis) {
        axisGroups.push({ axis: axis, startIdx: i, count: 0 });
        lastAxis = axis;
      }
      axisGroups[axisGroups.length - 1].count++;
    });

    var longestMood = moods.reduce(function (a, b) { return a.length > b.length ? a : b; }, '');
    var leftMargin = Math.max(longestMood.length * 6.5 + 28, 70);
    var rowH = 22;
    var groupGap = 6;
    var margin = { top: 12, right: 12, bottom: 30, left: leftMargin };
    var w = Math.max(el.clientWidth || 400, 280);

    // Total height: rows + gaps between axis groups
    var totalRows = moods.length * rowH + (axisGroups.length - 1) * groupGap;
    var h = totalRows + margin.top + margin.bottom;
    var iw = w - margin.left - margin.right;

    var svg = d3.select(el).append('svg')
      .attr('viewBox', '0 0 ' + w + ' ' + h)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    // Glow filter
    var defs = svg.append('defs');
    var filter = defs.append('filter').attr('id', 'dotGlow');
    filter.append('feGaussianBlur').attr('stdDeviation', '2.5').attr('result', 'blur');
    var fmerge = filter.append('feMerge');
    fmerge.append('feMergeNode').attr('in', 'blur');
    fmerge.append('feMergeNode').attr('in', 'SourceGraphic');

    var g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

    // Build y positions with gaps between axis groups
    var yPos = {};
    var curY = 0;
    axisGroups.forEach(function (grp, gi) {
      if (gi > 0) curY += groupGap;
      // Draw axis group label (small, left-aligned)
      g.append('text')
        .attr('x', -leftMargin + 4)
        .attr('y', curY + (grp.count * rowH) / 2 + 3)
        .text(grp.axis.toUpperCase())
        .attr('fill', axisColors[grp.axis] || '#78909c')
        .attr('font-size', '7px')
        .attr('font-weight', '700')
        .attr('font-family', 'var(--font-mono)')
        .attr('text-anchor', 'start')
        .attr('opacity', 0.6);
      // Draw subtle group background
      g.append('rect')
        .attr('x', 0).attr('y', curY)
        .attr('width', iw).attr('height', grp.count * rowH)
        .attr('fill', axisColors[grp.axis] || '#78909c')
        .attr('opacity', 0.03)
        .attr('rx', 3);
      for (var j = 0; j < grp.count; j++) {
        yPos[moods[grp.startIdx + j]] = curY + j * rowH + rowH / 2;
      }
      curY += grp.count * rowH;
    });

    var x = d3.scaleTime()
      .domain(d3.extent(data, function (d) { return d.time; }))
      .range([0, iw]);

    // Track which emotions have data points
    var seenMoods = {};
    data.forEach(function (d) { seenMoods[d.mood] = true; });

    // Emotion labels on left — dim if no data points
    moods.forEach(function (m) {
      var hasPts = seenMoods[m];
      g.append('text').attr('x', -8).attr('y', yPos[m] + 3)
        .text(m).attr('fill', getMoodColor(m)).attr('font-size', '9px')
        .attr('font-family', 'var(--font-mono)').attr('text-anchor', 'end')
        .attr('opacity', hasPts ? 1 : 0.25);
    });

    // Subtle horizontal guide lines
    moods.forEach(function (m) {
      g.append('line')
        .attr('x1', 0).attr('x2', iw)
        .attr('y1', yPos[m]).attr('y2', yPos[m])
        .attr('stroke', getMoodColor(m)).attr('stroke-opacity', 0.08);
    });

    // X axis
    g.append('g').attr('transform', 'translate(0,' + curY + ')')
      .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat('%H:%M')))
      .selectAll('text').attr('fill', 'rgba(226,234,242,0.5)').attr('font-size', '9px');
    g.selectAll('.domain').attr('stroke', 'rgba(0,229,255,0.1)');
    g.selectAll('.tick line').attr('stroke', 'rgba(0,229,255,0.08)');

    // Dots with glow
    g.selectAll('.tl-dot').data(data).enter().append('circle')
      .attr('class', 'tl-dot')
      .attr('cx', function (d) { return x(d.time); })
      .attr('cy', function (d) { return yPos[d.mood] || 0; })
      .attr('r', 4.5)
      .attr('fill', function (d) { return getMoodColor(d.mood); })
      .attr('opacity', 0.9)
      .attr('filter', 'url(#dotGlow)');
  }

  function renderActivityHeatmap(heatmap) {
    var el = document.getElementById('dshActivityBar');
    if (!el || typeof d3 === 'undefined') return;
    el.innerHTML = '';

    var days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    var hours = [];
    for (var h = 0; h < 24; h++) hours.push(h);

    // Build flat data array
    var data = [];
    var maxVal = 0;
    days.forEach(function (day, di) {
      hours.forEach(function (hr) {
        var val = heatmap[di + '_' + hr] || 0;
        if (val > maxVal) maxVal = val;
        data.push({ day: di, hour: hr, val: val });
      });
    });

    if (maxVal === 0) { el.innerHTML = '<div class="dash-log-empty">No activity data yet</div>'; return; }

    var margin = { top: 6, right: 12, bottom: 24, left: 32 };
    var w = Math.max(el.clientWidth || 400, 280);
    var cellH = 14;
    var ht = days.length * cellH + margin.top + margin.bottom;
    var iw = w - margin.left - margin.right;
    var cellW = iw / 24;

    var svg = d3.select(el).append('svg')
      .attr('viewBox', '0 0 ' + w + ' ' + ht)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    var g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');

    // Color scale: dark → cyan
    var color = d3.scaleSequential(function (t) {
      if (t === 0) return 'rgba(0,229,255,0.04)';
      return 'rgba(0,229,255,' + (0.15 + t * 0.85) + ')';
    }).domain([0, maxVal]);

    // Cells
    g.selectAll('.hm-cell').data(data).enter().append('rect')
      .attr('class', 'hm-cell')
      .attr('x', function (d) { return d.hour * cellW; })
      .attr('y', function (d) { return d.day * cellH; })
      .attr('width', cellW - 1)
      .attr('height', cellH - 1)
      .attr('rx', 2)
      .attr('fill', function (d) { return color(d.val); })
      .append('title').text(function (d) {
        return days[d.day] + ' ' + (d.hour < 10 ? '0' : '') + d.hour + ':00 — ' + d.val + ' interactions';
      });

    // Day labels
    days.forEach(function (day, i) {
      g.append('text')
        .attr('x', -4).attr('y', i * cellH + cellH / 2 + 3)
        .text(day).attr('fill', 'rgba(226,234,242,0.5)')
        .attr('font-size', '8px').attr('font-family', 'var(--font-mono)')
        .attr('text-anchor', 'end');
    });

    // Hour labels (every 3 hours)
    hours.forEach(function (hr) {
      if (hr % 3 !== 0) return;
      g.append('text')
        .attr('x', hr * cellW + cellW / 2)
        .attr('y', days.length * cellH + 12)
        .text((hr < 10 ? '0' : '') + hr)
        .attr('fill', 'rgba(226,234,242,0.5)')
        .attr('font-size', '8px').attr('font-family', 'var(--font-mono)')
        .attr('text-anchor', 'middle');
    });
  }

  // ── AUDIT LOG ──
  function loadLog() {
    fetch('/api/dashboard/interactions?limit=100').then(function (r) { return r.json(); }).then(function (data) {
      var list = document.getElementById('dshLogList');
      if (!list) return;
      if (!data.length) { list.innerHTML = '<div class="dash-log-empty">No interactions recorded yet.</div>'; return; }

      var html = '';
      // Show newest first
      for (var i = data.length - 1; i >= 0; i--) {
        var e = data[i];
        html += '<div class="dash-log-entry">';
        html += '<div class="dash-log-meta">';
        html += '<span class="dash-log-ts">' + (e.ts || '') + '</span>';
        if (e.emotion_raw || e.emotion) {
          var rawLabel = e.emotion_raw || e.emotion;
          var pillColor = getMoodColor(rawLabel);
          html += '<span class="dash-log-emotion" style="border-color:' + pillColor + ';color:' + pillColor + '">' + rawLabel + '</span>';
        }
        if (e.speaker) html += '<span class="dash-log-speaker">' + e.speaker + '</span>';
        html += '</div>';
        if (e.user) html += '<div class="dash-log-user"><strong>User:</strong> ' + escapeHtml(e.user) + '</div>';
        if (e.bot) html += '<div class="dash-log-bot"><strong>Bot:</strong> ' + escapeHtml(e.bot).substring(0, 300) + '</div>';
        html += '</div>';
      }
      list.innerHTML = html;
    }).catch(function () {});
  }

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── TOPICS ──
  function loadTopicsData() {
    fetch('/api/dashboard/topics').then(function (r) { return r.json(); }).then(function (data) {
      var topics = data.topics || [];
      _topicsData = topics;
      renderTopicsTable(topics);
      // Only render graph if topics panel is currently visible
      var topicsPanel = document.getElementById('dshTopicsPanel');
      if (topicsPanel && topicsPanel.classList.contains('active')) {
        _panelRendered.topics = true;
        renderTopicsGraph(topics);
      }
    }).catch(function () {});
  }

  function renderTopicsTable(topics) {
    var tbody = document.querySelector('#dshTopicsTable tbody');
    if (!tbody) return;
    if (!topics.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:rgba(226,234,242,0.3)">No topics yet</td></tr>'; return; }

    // Update header if needed (add Actions column)
    var thead = document.querySelector('#dshTopicsTable thead tr');
    if (thead && thead.children.length === 4) {
      var th = document.createElement('th');
      th.textContent = '';
      th.style.width = '32px';
      thead.appendChild(th);
    }

    var html = '';
    // Sort by mention count desc, preserve original indices for API calls
    var indexed = topics.map(function (t, i) { return { t: t, origIdx: i }; });
    indexed.sort(function (a, b) { return (b.t.mention_count || 1) - (a.t.mention_count || 1); });
    indexed.forEach(function (item) {
      var t = item.t;
      var origIdx = item.origIdx;
      var name = typeof t === 'string' ? t : (t.topic || '');
      var mentions = t.mention_count || 1;
      var first = (t.first_mentioned || '').substring(0, 10);
      var last = (t.last_mentioned || '').substring(0, 10);
      html += '<tr data-topic-idx="' + origIdx + '">'
        + '<td><span class="topic-editable" contenteditable="true" spellcheck="false" data-field="topic" data-index="' + origIdx + '">' + escapeHtml(name) + '</span></td>'
        + '<td>' + mentions + '</td><td>' + first + '</td><td>' + last + '</td>'
        + '<td><button class="topic-delete-btn" data-index="' + origIdx + '" title="Delete topic"><i class="bi bi-x-lg"></i></button></td>'
        + '</tr>';
    });
    tbody.innerHTML = html;

    // Inline edit: save on blur
    tbody.querySelectorAll('.topic-editable').forEach(function (el) {
      var origVal = el.textContent;
      el.addEventListener('focus', function () { origVal = el.textContent; });
      el.addEventListener('blur', function () {
        var newVal = el.textContent.trim();
        if (!newVal || newVal === origVal) { el.textContent = origVal; return; }
        el.style.opacity = '0.5';
        fetch('/api/dashboard/topic/edit', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: parseInt(el.getAttribute('data-index'), 10), fields: { topic: newVal } })
        }).then(function (r) { return r.json(); }).then(function (d) {
          el.style.opacity = '1';
          if (d.success) {
            origVal = newVal;
            el.style.color = '#39ff14';
            setTimeout(function () { el.style.color = ''; }, 1200);
          } else { el.textContent = origVal; }
        }).catch(function () { el.style.opacity = '1'; el.textContent = origVal; });
      });
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); el.blur(); }
        if (e.key === 'Escape') { el.textContent = origVal; el.blur(); }
      });
    });

    // Delete buttons
    tbody.querySelectorAll('.topic-delete-btn').forEach(function (btn) {
      var clicks = 0;
      btn.addEventListener('click', function () {
        clicks++;
        if (clicks === 1) {
          btn.style.color = '#ef5350';
          btn.title = 'Click again to confirm';
          setTimeout(function () { clicks = 0; btn.style.color = ''; btn.title = 'Delete topic'; }, 3000);
        } else {
          btn.disabled = true;
          var idx = parseInt(btn.getAttribute('data-index'), 10);
          fetch('/api/dashboard/topic/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: idx })
          }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.success) {
              var row = btn.closest('tr');
              if (row) { row.style.opacity = '0'; setTimeout(function () { row.remove(); }, 300); }
              var topEl = document.getElementById('dshTopics');
              if (topEl && d.remaining !== undefined) topEl.textContent = d.remaining;
              // Reload topics to refresh indices after delete
              setTimeout(function () { loadTopicsData(); }, 400);
            } else { btn.disabled = false; clicks = 0; }
          }).catch(function () { btn.disabled = false; clicks = 0; });
        }
      });
    });
  }

  function renderTopicsGraph(topics) {
    var container = document.getElementById('dshTopicsGraph');
    if (!container || typeof d3 === 'undefined' || !topics.length) return;
    container.innerHTML = '';

    var w = container.clientWidth || 400;
    var h = Math.max(250, Math.min(topics.length * 12 + 100, 400));

    var nodes = [{ id: 'center', name: 'TOPICS', color: '#39ff14', size: 18, group: 'hub' }];
    var links = [];
    topics.forEach(function (t, i) {
      var name = typeof t === 'string' ? t : (t.topic || '');
      var mentions = (typeof t === 'object' ? t.mention_count : 1) || 1;
      var nid = 'topic_' + i;
      nodes.push({ id: nid, name: name, color: '#66bb6a', size: 4 + Math.min(mentions * 1.5, 12), group: 'topic', mentions: mentions });
      links.push({ source: 'center', target: nid });
    });

    var svg = d3.select(container).append('svg').attr('viewBox', '0 0 ' + w + ' ' + h)
      .style('width', '100%').style('height', '100%');

    // Glow
    var defs = svg.append('defs');
    var filter = defs.append('filter').attr('id', 'topicGlow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    var merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    var g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', function (e) { g.attr('transform', e.transform); }));

    var sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(function (d) { return d.id; }).distance(60))
      .force('charge', d3.forceManyBody().strength(-80))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide().radius(function (d) { return d.size + 4; }));

    var link = g.append('g').selectAll('line').data(links).enter().append('line')
      .attr('stroke', 'rgba(57,255,20,0.12)').attr('stroke-width', 1);

    var node = g.append('g').selectAll('circle').data(nodes).enter().append('circle')
      .attr('r', function (d) { return d.size; })
      .attr('fill', function (d) { return d.color; })
      .attr('opacity', function (d) { return d.group === 'hub' ? 0.95 : 0.7; })
      .attr('filter', function (d) { return d.group === 'hub' ? 'url(#topicGlow)' : null; })
      .call(d3.drag()
        .on('start', function (e, d) { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', function (e, d) { d.fx = e.x; d.fy = e.y; })
        .on('end', function (e, d) { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    var labels = g.append('g').selectAll('text').data(nodes).enter().append('text')
      .attr('class', 'dash-node-label')
      .attr('dy', function (d) { return d.size + 10; })
      .attr('font-size', function (d) { return d.group === 'hub' ? '10px' : '8px'; })
      .attr('fill', function (d) { return d.group === 'hub' ? '#39ff14' : 'rgba(226,234,242,0.6)'; })
      .text(function (d) { return d.name.length > 20 ? d.name.substring(0, 18) + '..' : d.name; });

    sim.on('tick', function () {
      link.attr('x1', function (d) { return d.source.x; }).attr('y1', function (d) { return d.source.y; })
          .attr('x2', function (d) { return d.target.x; }).attr('y2', function (d) { return d.target.y; });
      node.attr('cx', function (d) { return d.x; }).attr('cy', function (d) { return d.y; });
      labels.attr('x', function (d) { return d.x; }).attr('y', function (d) { return d.y; });
    });
  }

  // ── PROMPT DEBUGGER ──
  var _promptInteractions = [];
  var _currentPromptText = null;

  function loadPrompt() {
    fetch('/api/dashboard/prompt').then(function (r) { return r.json(); }).then(function (data) {
      _promptInteractions = data.interactions || [];
      var promptPanel = document.getElementById('dshPrompt');
      if (promptPanel && promptPanel.classList.contains('active')) {
        _panelRendered.prompt = true;
        populatePromptDropdown();
      }
    }).catch(function () {});
  }

  function populatePromptDropdown() {
    var select = document.getElementById('dshPromptSelect');
    if (!select) return;
    // Keep the first placeholder option
    select.innerHTML = '<option value="">Select interaction to debug...</option>';
    _promptInteractions.forEach(function (item) {
      if (!item.has_prompt) return;
      var opt = document.createElement('option');
      opt.value = item.id;
      var ts = (item.ts || '').split(' ')[1] || item.ts || '';
      var label = ts + ' — ' + (item.user || '(no input)');
      if (item.emotion) label += ' [' + item.emotion + ']';
      opt.textContent = label;
      select.appendChild(opt);
    });
  }

  function setPromptToolbarState(enabled) {
    ['dshPromptCopy', 'dshPromptExpandAll', 'dshPromptCollapseAll'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.disabled = !enabled;
    });
  }

  function loadSelectedPrompt(entryId) {
    var sections = document.getElementById('dshPromptSections');
    var info = document.getElementById('dshPromptInfo');
    if (!entryId) {
      sections.innerHTML = '<div class="dash-prompt-empty"><i class="bi bi-bug" style="font-size:2rem;opacity:0.3"></i><div>Select an interaction above to inspect its prompt</div></div>';
      info.innerHTML = '';
      _currentPromptText = null;
      setPromptToolbarState(false);
      return;
    }

    sections.innerHTML = '<div class="dash-prompt-empty"><i class="bi bi-hourglass-split" style="font-size:1.5rem;opacity:0.3"></i><div>Loading prompt...</div></div>';

    // Find the interaction metadata
    var meta = _promptInteractions.find(function (i) { return i.id === entryId; });

    fetch('/api/dashboard/prompt?id=' + encodeURIComponent(entryId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _currentPromptText = data.prompt || '';
        setPromptToolbarState(!!_currentPromptText);

        // Build info chips
        if (meta && info) {
          var chips = '';
          if (meta.ts) chips += '<span class="dash-prompt-info-chip"><strong>Time:</strong> ' + meta.ts + '</span>';
          if (meta.speaker) chips += '<span class="dash-prompt-info-chip"><strong>Speaker:</strong> ' + escapeHtml(meta.speaker) + '</span>';
          if (meta.emotion) chips += '<span class="dash-prompt-info-chip"><strong>Mood:</strong> ' + escapeHtml(meta.emotion) + '</span>';
          var charCount = _currentPromptText.length;
          var approxTokens = Math.round(_currentPromptText.split(/\s+/).length * 1.3);
          chips += '<span class="dash-prompt-info-chip"><strong>' + charCount.toLocaleString() + '</strong> chars · <strong>~' + approxTokens.toLocaleString() + '</strong> tokens</span>';
          info.innerHTML = chips;
        }

        // Parse prompt into sections
        renderPromptSections(_currentPromptText, meta);

        // Render LLM response section below the prompt
        renderLLMResponse(data.llm_raw || '', meta);
      })
      .catch(function () {
        sections.innerHTML = '<div class="dash-prompt-empty"><i class="bi bi-x-circle" style="font-size:1.5rem;color:#ef5350"></i><div>Failed to load prompt</div></div>';
      });
  }

  function renderPromptSections(promptText, meta) {
    var sections = document.getElementById('dshPromptSections');
    if (!sections) return;

    var html = '';

    // Parse the prompt into logical sections
    var parsed = parsePromptSections(promptText);
    parsed.forEach(function (sec, idx) {
      var secId = 'prompt-sec-' + idx;
      var lineCount = sec.content.split('\n').length;
      // All prompt sections start collapsed
      var collapsed = true;
      html += '<div class="dash-prompt-section">';
      html += '<div class="dash-prompt-section-title' + (collapsed ? ' collapsed' : '') + '" data-collapse="' + secId + '">';
      html += '<i class="bi bi-chevron-down"></i> ' + escapeHtml(sec.name);
      html += '<span class="prompt-sec-lines">' + lineCount + ' lines</span>';
      html += '</div>';
      html += '<pre class="dash-prompt-pre' + (collapsed ? ' collapsed' : '') + '" id="' + secId + '">' + highlightPrompt(sec.content) + '</pre>';
      html += '</div>';
    });

    sections.innerHTML = html;
  }

  function parsePromptSections(text) {
    if (!text) return [{ name: 'Full Prompt', content: '(empty)' }];

    var sections = [];
    var lines = text.split('\n');
    var currentName = 'System Instructions';
    var currentLines = [];
    var MIN_SECTION_LINES = 3; // Don't split on headers that create tiny sections

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      // Match section headers: "## Title", "=== Title ===", "Part N: Title"
      var headerMatch = line.match(/^#{1,3}\s+(.+)$/) ||
                        line.match(/^===+\s*(.+?)\s*===+$/) ||
                        line.match(/^(Part\s+\d+[:\s].+)$/i);
      if (headerMatch && currentLines.length >= MIN_SECTION_LINES) {
        var content = currentLines.join('\n').trim();
        if (content) sections.push({ name: currentName, content: content });
        currentName = headerMatch[1].trim();
        currentLines = [];
      } else {
        currentLines.push(line);
      }
    }
    if (currentLines.length > 0) {
      var content = currentLines.join('\n').trim();
      if (content) sections.push({ name: currentName, content: content });
    }

    // Merge any tiny trailing sections into the previous one
    var merged = [];
    for (var j = 0; j < sections.length; j++) {
      var sec = sections[j];
      if (j > 0 && sec.content.split('\n').length < 2) {
        merged[merged.length - 1].content += '\n\n' + sec.name + '\n' + sec.content;
      } else {
        merged.push(sec);
      }
    }

    if (merged.length <= 1) {
      return [{ name: 'Full Prompt', content: text }];
    }
    return merged;
  }

  function highlightPrompt(text) {
    var safe = escapeHtml(text);
    // Highlight headers
    safe = safe.replace(/^(#{1,3}\s+.*)$/gm, '<span style="color:#00e5ff;font-weight:bold">$1</span>');
    // Highlight bracketed labels
    safe = safe.replace(/^(\[.*?\])(.*)$/gm, '<span style="color:#b44dff">$1</span>$2');
    // Highlight XML-like tags
    safe = safe.replace(/(&lt;[^&]+&gt;)/g, '<span style="color:rgba(0,229,255,0.45)">$1</span>');
    // Highlight JSON keys
    safe = safe.replace(/"([^"]+)":/g, '<span style="color:#ffca28">"$1"</span>:');
    return safe;
  }

  function renderLLMResponse(rawText, meta) {
    var sections = document.getElementById('dshPromptSections');
    if (!sections || !rawText) return;

    var html = '<div class="dash-prompt-response-divider"><span>LLM RESPONSE</span></div>';

    // Try to parse as JSON to show individual fields
    var parsed = null;
    try { parsed = JSON.parse(rawText); } catch (e) {}

    if (parsed && typeof parsed === 'object') {
      // Render each key as its own collapsible section
      var keys = Object.keys(parsed);
      keys.forEach(function (key) {
        var val = parsed[key];
        var display = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        var secId = 'llm-field-' + key;
        var collapsed = key !== 'reply' && key !== 'question';
        html += '<div class="dash-prompt-section">';
        html += '<div class="dash-prompt-section-title' + (collapsed ? ' collapsed' : '') + '" data-collapse="' + secId + '">';
        html += '<i class="bi bi-chevron-down"></i> ' + escapeHtml(key);
        if (typeof val === 'string') {
          html += '<span class="prompt-sec-lines">' + val.length + ' chars</span>';
        } else if (Array.isArray(val)) {
          html += '<span class="prompt-sec-lines">' + val.length + ' items</span>';
        }
        html += '</div>';
        html += '<pre class="dash-prompt-pre' + (collapsed ? ' collapsed' : '') + '" id="' + secId + '">' + highlightPrompt(display) + '</pre>';
        html += '</div>';
      });

      // Full raw JSON (collapsed)
      html += '<div class="dash-prompt-section">';
      html += '<div class="dash-prompt-section-title collapsed" data-collapse="llm-field-raw">';
      html += '<i class="bi bi-chevron-down"></i> Raw JSON';
      html += '<span class="prompt-sec-lines">' + rawText.length + ' chars</span>';
      html += '</div>';
      html += '<pre class="dash-prompt-pre collapsed" id="llm-field-raw">' + highlightPrompt(rawText) + '</pre>';
      html += '</div>';
    } else {
      // Not valid JSON — show as plain text
      html += '<div class="dash-prompt-section">';
      html += '<div class="dash-prompt-section-title" data-collapse="llm-field-raw">';
      html += '<i class="bi bi-chevron-down"></i> Raw Response';
      html += '<span class="prompt-sec-lines">' + rawText.length + ' chars</span>';
      html += '</div>';
      html += '<pre class="dash-prompt-pre" id="llm-field-raw">' + escapeHtml(rawText) + '</pre>';
      html += '</div>';
    }

    sections.innerHTML += html;
  }

  // Delegated collapse toggle for all prompt/response sections
  var promptContainer = document.getElementById('dshPromptSections');
  if (promptContainer) {
    promptContainer.addEventListener('click', function (e) {
      var title = e.target.closest('.dash-prompt-section-title[data-collapse]');
      if (!title) return;
      var targetId = title.getAttribute('data-collapse');
      var target = document.getElementById(targetId);
      if (target) {
        target.classList.toggle('collapsed');
        title.classList.toggle('collapsed');
      }
    });
  }

  // Dropdown change handler
  var promptSelect = document.getElementById('dshPromptSelect');
  if (promptSelect) {
    promptSelect.addEventListener('change', function () {
      loadSelectedPrompt(this.value);
    });
  }

  // Copy button
  var copyBtn = document.getElementById('dshPromptCopy');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      if (_currentPromptText) {
        navigator.clipboard.writeText(_currentPromptText).then(function () {
          copyBtn.innerHTML = '<i class="bi bi-check2"></i> Copied';
          setTimeout(function () { copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy'; }, 1500);
        }).catch(function () {});
      }
    });
  }

  // Expand / Collapse all buttons
  var expandBtn = document.getElementById('dshPromptExpandAll');
  if (expandBtn) {
    expandBtn.addEventListener('click', function () {
      var container = document.getElementById('dshPromptSections');
      if (!container) return;
      container.querySelectorAll('.dash-prompt-section-title.collapsed').forEach(function (t) {
        t.classList.remove('collapsed');
      });
      container.querySelectorAll('.dash-prompt-pre.collapsed').forEach(function (p) {
        p.classList.remove('collapsed');
      });
    });
  }
  var collapseBtn = document.getElementById('dshPromptCollapseAll');
  if (collapseBtn) {
    collapseBtn.addEventListener('click', function () {
      var container = document.getElementById('dshPromptSections');
      if (!container) return;
      container.querySelectorAll('.dash-prompt-section-title:not(.collapsed)').forEach(function (t) {
        t.classList.add('collapsed');
      });
      container.querySelectorAll('.dash-prompt-pre:not(.collapsed)').forEach(function (p) {
        p.classList.add('collapsed');
      });
    });
  }

  // ── Tab activation ──
  var dashTab = document.getElementById('dashboard-tab');
  if (dashTab) {
    dashTab.addEventListener('shown.bs.tab', function () {
      if (!dashLoaded) loadDashboard();
      else refreshStats();  // always refresh stats strip on tab visit
    });
  }
})();
