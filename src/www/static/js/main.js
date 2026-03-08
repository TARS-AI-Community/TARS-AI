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
let isMuted = true;

function start_talking() { if (!isMuted) avatarIsTalking = true; }
function stop_talking()  { avatarIsTalking = false; }

document.addEventListener('DOMContentLoaded', function () {
  const audioPlayer = $('audioPlayer');
  const muteBtn = $('muteButton');

  // Default to muted on load — use volume=0 so audio still plays through
  // in real time (prevents queue buildup when muted)
  audioPlayer.volume = 0;

  muteBtn.addEventListener('click', function () {
    const icon = this.querySelector('i');
    if (isMuted) {
      audioPlayer.volume = 1;
      icon.className = 'bi bi-volume-up-fill';
      if (!audioPlayer.paused) start_talking();
    } else {
      audioPlayer.volume = 0;
      icon.className = 'bi bi-volume-mute-fill';
      stop_talking();
    }
    isMuted = !isMuted;
  });
});

const audioPlayer = $('audioPlayer');
if (audioPlayer) audioPlayer.addEventListener('ended', stop_talking);

let audioStarted = false;

// Legacy full-response audio (used for image uploads / non-streaming paths)
function startAudioStream() {
  if (audioStarted) return;
  audioStarted = true;
  fetch('/audio_stream').then(r => r.blob()).then(blob => {
    if (!blob.size) { audioStarted = false; return; }
    const url = URL.createObjectURL(blob);
    audioPlayer.src = url; audioPlayer.load();
    audioPlayer.play().then(() => {
      start_talking();
      audioPlayer.onended = () => { URL.revokeObjectURL(url); setTimeout(playNextAudioChunk, 500); };
    }).catch(e => { audioStarted = false; console.error(e); });
  }).catch(e => { audioStarted = false; console.error(e); });
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
      audioPlayer.onended = () => { URL.revokeObjectURL(url); setTimeout(playNextAudioChunk, 500); };
    });
  }).catch(console.error);
}

// Sentence-by-sentence SocketIO audio queue (used for streaming text responses)
const _audioQueue = [];
let _audioPlaying = false;
let _audioDone = false;

function _playNextFromQueue() {
  if (_audioPlaying || !_audioQueue.length) {
    // If queue empty and server signalled done, finish up
    if (!_audioQueue.length && _audioDone) {
      _audioDone = false;
      stop_talking();
    }
    return;
  }
  _audioPlaying = true;
  const b64 = _audioQueue.shift();
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  audioPlayer.src = url;
  audioPlayer.load();
  audioPlayer.play().then(() => {
    start_talking();
    audioPlayer.onended = () => {
      URL.revokeObjectURL(url);
      _audioPlaying = false;
      _playNextFromQueue();
    };
  }).catch(e => {
    console.error('Audio chunk play failed:', e);
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
      // In voice mode, send image instantly
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
  // Streaming bot response
  let _streamRow = null;
  let _streamText = null;
  let _streamActive = false;

  socket.on('bot_stream_start', () => {
    removeTypingMessage();
    _streamActive = true;
    // Flush audio state from previous message
    _audioQueue.length = 0;
    _audioDone = false;
    _audioPlaying = false;
    audioStarted = false;
    // Bubble created lazily on first bot_token to avoid empty flash
  });

  socket.on('bot_token', d => {
    removeTypingMessage();
    if (!_streamActive) return;
    // Create bubble on first token
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
    _audioQueue.push(d.data);
    _playNextFromQueue();
  });

  socket.on('bot_audio_done', () => {
    _audioDone = true;
    // If nothing playing and queue empty, stop talking now
    if (!_audioPlaying && !_audioQueue.length) stop_talking();
  });

  socket.on('bot_message', d => {
    removeTypingMessage();
    _streamActive = false;
    if (_streamRow) {
      if (d.message) {
        _streamText.innerHTML = formatText(d.message);
        // Only use legacy audio fetch if audio wasn't already streamed via SocketIO
        if (!d.audio_streamed) startAudioStream();
      } else {
        _streamRow.remove();
      }
      _streamRow = null;
      _streamText = null;
    } else {
      if (d.message) displayBotMessage(d.message);
    }
  });

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
    // show typing indicator after 1s
    setTimeout(() => displayBotMessage('', true), 1000);
  }

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

  // ── MIC / SEND TOGGLE + VOICE MODE ─────────────────────────────────────────
  const voiceModeBtn = $('voiceModeButton');
  const voiceOverlay = $('voiceOverlay');
  const inputPill    = document.querySelector('.input-pill');
  const voiceCanvas  = $('voiceWaveform');
  const voiceStatus  = $('voiceStatus');

  let voiceActive = false;
  let recognition = null;
  let voiceAnimFrame = null;
  let voiceAnimLevel = 0;
  let voiceDebounceTimer = null;
  let voicePendingTranscript = '';
  let voiceLastSent = '';
  let isSendMode = false;

  // Check browser support for SpeechRecognition
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  // Toggle mic icon ↔ send icon based on text input
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

  if (prompt) {
    prompt.addEventListener('input', updateMicSendButton);
  }

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

  function startVoiceMode() {
    if (!SpeechRecognition) {
      if (window.showToast) showToast('Speech recognition not supported in this browser. Use Chrome or Edge.', 'error');
      return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = function(event) {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      // Animate waveform when hearing speech
      if (interimTranscript) {
        voiceAnimLevel = 1.0;
      }

      // When we get a final result, debounce before sending.
      // On Android Chrome, each final result is cumulative (contains all words so far),
      // so we replace rather than accumulate to avoid word duplication.
      if (finalTranscript.trim()) {
        voicePendingTranscript = finalTranscript.trim();
        if (voiceDebounceTimer) clearTimeout(voiceDebounceTimer);
        voiceDebounceTimer = setTimeout(() => {
          const text = voicePendingTranscript.trim();
          voicePendingTranscript = '';
          if (text && text !== voiceLastSent) {
            voiceLastSent = text;
            displayUserMessage(text);
            sendUserMessage(text);
            setTimeout(() => displayBotMessage('', true), 500);
            setTimeout(() => { if (voiceActive) voiceStatus.textContent = 'Listening...'; }, 1500);
          }
        }, 600);
      }
    };

    recognition.onerror = function(event) {
      console.error('Speech recognition error:', event.error);
      if (event.error === 'not-allowed') {
        if (window.showToast) showToast('Microphone access denied', 'error');
        stopVoiceMode();
        return;
      }
      // For transient errors (network, no-speech), keep listening
      voiceStatus.textContent = 'Error: ' + event.error;
      setTimeout(() => { if (voiceActive) voiceStatus.textContent = 'Listening...'; }, 2000);
    };

    recognition.onend = function() {
      // Auto-restart if voice mode is still active (browser stops after silence)
      if (voiceActive && recognition) {
        try { recognition.start(); } catch(e) { /* already started */ }
      }
    };

    try {
      recognition.start();
    } catch(e) {
      console.error('Failed to start speech recognition:', e);
      return;
    }

    voiceActive = true;
    voiceOverlay.style.display = 'flex';
    inputPill.classList.add('voice-active');
    voiceModeBtn.classList.add('voice-active');
    voiceModeBtn.querySelector('i').className = 'bi bi-stop-circle-fill';
    voiceModeBtn.setAttribute('aria-label', 'Stop voice');
    voiceStatus.textContent = 'Listening...';

    drawVoiceWaveform();
  }

  function stopVoiceMode() {
    voiceActive = false;
    if (voiceDebounceTimer) { clearTimeout(voiceDebounceTimer); voiceDebounceTimer = null; }
    voicePendingTranscript = '';
    voiceLastSent = '';

    if (recognition) { recognition.onend = null; recognition.onerror = null; recognition.onresult = null; recognition.abort(); recognition = null; }
    if (voiceAnimFrame) { cancelAnimationFrame(voiceAnimFrame); voiceAnimFrame = null; }

    voiceModeBtn.classList.remove('voice-active');
    voiceModeBtn.classList.remove('send-mode');
    voiceModeBtn.querySelector('i').className = 'bi bi-mic-fill';
    voiceModeBtn.setAttribute('aria-label', 'Voice mode');
    voiceOverlay.style.display = 'none';
    inputPill.classList.remove('voice-active');
    isSendMode = false;
    updateMicSendButton();
    voiceStatus.textContent = 'Listening...';
  }

  function drawVoiceWaveform() {
    if (!voiceActive) return;
    voiceCanvas.width = voiceCanvas.clientWidth;
    voiceCanvas.height = voiceCanvas.clientHeight;
    const ctx = voiceCanvas.getContext('2d');
    const w = voiceCanvas.width;
    const h = voiceCanvas.height;
    ctx.clearRect(0, 0, w, h);

    // Animated pulse based on activity
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
    'HOME_ASSISTANT':'bi-house-fill','DISCORD':'bi-discord',
    'STABLE_DIFFUSION':'bi-image-fill',
    'BATTERY':'bi-battery-half',
    'MISC':'bi-wrench-adjustable',
    'CHARACTER_EDITOR':'bi-person-lines-fill'
  };
  const SECTION_LABELS = {
    'CHAR':'System','CONTROLS':'Controls',
    'STT':'Speech','LLM':'AI Model','VISION':'Vision','EMOTION':'Emotion',
    'TTS':'Voice','UI':'Display','RAG':'Memory',
    'ACCESS':'Access',
    'HOME_ASSISTANT':'Home Asst','DISCORD':'Discord',
    'STABLE_DIFFUSION':'Img Gen',
    'BATTERY':'Battery',
    'MISC':'Misc',
    'CHARACTER_EDITOR':'Character'
  };

  const SECTION_ORDER = [
    'CHAR', 'LLM',
    'STT', 'TTS',
    'EMOTION', 'VISION', 'RAG',
    'UI', 'ACCESS',
    'CONTROLS',
    'BATTERY',
    'HOME_ASSISTANT', 'DISCORD',
    'STABLE_DIFFUSION'
  ];

  // Character editor tile is appended after config sections
  const CHARACTER_EDITOR_ID = 'CHARACTER_EDITOR';

  let activeConfigSection = null;

  function loadConfiguration() {
    fetch('/get_config').then(r=>r.json()).then(data => {
      const form = $('configForm');

      // Order sections: SECTION_ORDER first, then any extras from backend
      const allSections = Object.keys(data.config);
      const ordered = SECTION_ORDER.filter(s => allSections.includes(s));
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
          </div>
          <div class="config-panel-body"><div class="row g-2">`;

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
              html += `</label><input type="text" class="form-control form-control-sm config-input" id="${fid}" data-section="${section}" data-key="${key}" value="${esc(String(value))}">`;
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

      // Remote access tunnel controls
      initTunnelControls();
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
  const TAB_IDS = ['chat', 'motion', 'body', 'emotions', 'wifi', 'config', 'nexus'];
  const TAB_BTN_IDS = ['chat-tab', 'motion-tab', 'body-tab', 'emotions-tab', 'wifi-tab', 'config-tab', 'nexus-tab'];
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
