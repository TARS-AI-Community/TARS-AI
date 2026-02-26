/* ════════════════════════════════════════════
   ALL JAVASCRIPT LOGIC
   ════════════════════════════════════════════ */

// --- WiFi Tab Logic ---
(function () {
    let wfSelected = null;
    function wfSignalIcon(signal) {
        return signal >= 40 ? '/static/imgs/wifi-blue.png' : '/static/imgs/wifi-gray.png';
    }
    async function wfLoadStatus() {
        try {
            const r = await fetch('/api/wifi/status');
            const d = await r.json();
            const icon = document.getElementById('wfStatusIcon'), ssid = document.getElementById('wfStatusSsid'),
                ip = document.getElementById('wfStatusIp'), badge = document.getElementById('wfStatusBadge'),
                hbtn = document.getElementById('wfHotspotBtn');
            if (d.mode === 'client') {
                icon.src = '/static/imgs/wifi-blue.png'; ssid.textContent = d.ssid || 'Connected'; ip.textContent = d.ip || '';
                badge.textContent = 'Connected'; badge.className = 'wf-badge wf-badge-ok'; hbtn.textContent = 'Start Hotspot';
            } else if (d.mode === 'hotspot') {
                icon.src = '/static/imgs/wifi-yellow.png'; ssid.textContent = 'TARS-Setup'; ip.textContent = '10.42.0.1';
                badge.textContent = 'Hotspot'; badge.className = 'wf-badge wf-badge-hot'; hbtn.textContent = 'Stop Hotspot';
            } else {
                icon.src = '/static/imgs/wifi-gray.png'; ssid.textContent = 'Not connected'; ip.textContent = '';
                badge.textContent = 'Offline'; badge.className = 'wf-badge wf-badge-off'; hbtn.textContent = 'Start Hotspot';
            }
        } catch (e) { }
    }
    window.wfScan = async function () {
        const list = document.getElementById('wfNetList');
        list.innerHTML = '<div style="text-align:center;color:var(--text-dim);font-size:.85rem;padding:.75rem 0;"><span class="wf-spinner"></span>Scanning…</div>';
        wfSelected = null; document.getElementById('wfSelectedCard').style.display = 'none';
        try {
            const r = await fetch('/api/wifi/networks'); const d = await r.json();
            const nets = d.networks || [];
            if (!nets.length) { list.innerHTML = '<div style="text-align:center;color:var(--text-dim);font-size:.85rem;padding:.75rem 0;">No networks found.</div>'; return; }
            list.innerHTML = nets.map(n => `
      <button class="wf-net-btn${n.in_use ? ' in-use' : ''}" onclick='wfSelect(${JSON.stringify(n)})' data-ssid="${n.ssid}">
        <img class="wf-net-icon" src="${wfSignalIcon(n.signal)}" alt="">
        <span class="wf-net-name">${n.ssid}${n.in_use ? ' <span style="color:var(--green);font-size:.7rem;">✓</span>' : ''}</span>
        <span class="wf-net-sec">${n.security || ''}</span>
      </button>`).join('');
        } catch (e) { list.innerHTML = `<div style="text-align:center;color:var(--red);font-size:.85rem;padding:.75rem 0;">Scan failed: ${e.message}</div>`; }
    };
    window.wfSelect = function (net) {
        wfSelected = net;
        document.querySelectorAll('.wf-net-btn').forEach(b => b.classList.toggle('selected', b.dataset.ssid === net.ssid));
        const isEnt = net.security === 'WPA2-Enterprise', isOpen = net.security === 'open';
        document.getElementById('wfCardSsid').textContent = net.ssid;
        document.getElementById('wfCardDesc').textContent = isOpen ? 'Open network' : isEnt ? 'Enterprise network (802.1X)' : 'Password required';
        document.getElementById('wfPersonalFields').style.display = isEnt ? 'none' : '';
        document.getElementById('wfEnterpriseFields').style.display = isEnt ? '' : 'none';
        document.getElementById('wfPassword').value = ''; document.getElementById('wfUsername').value = '';
        document.getElementById('wfPasswordEnt').value = ''; document.getElementById('wfMsg').textContent = '';
        document.getElementById('wfMsg').className = 'wf-msg'; document.getElementById('wfSelectedCard').style.display = '';
    };
    window.wfDeselect = function () {
        wfSelected = null;
        document.querySelectorAll('.wf-net-btn').forEach(b => b.classList.remove('selected'));
        document.getElementById('wfSelectedCard').style.display = 'none';
    };
    window.wfConnect = function () {
        if (!wfSelected) return;
        document.getElementById('wfConfirmSsid').textContent = wfSelected.ssid;
        document.getElementById('wfConfirmSsid2').textContent = wfSelected.ssid;
        document.getElementById('wfConfirmMsg').textContent = ''; document.getElementById('wfConfirmMsg').className = 'wf-msg';
        document.getElementById('wfConfirmBtn').disabled = false; document.getElementById('wfConfirmBtn').textContent = 'Connect Now';
        document.getElementById('wfConfirmOverlay').style.display = 'flex';
    };
    window.wfConfirmCancel = function () { document.getElementById('wfConfirmOverlay').style.display = 'none'; };
    window.wfConfirmConnect = async function () {
        const btn = document.getElementById('wfConfirmBtn'), cancelBtn = document.getElementById('wfCancelBtn'),
            msg = document.getElementById('wfConfirmMsg');
        const isEnt = wfSelected.security === 'WPA2-Enterprise';
        const password = isEnt ? document.getElementById('wfPasswordEnt').value : document.getElementById('wfPassword').value;
        const username = isEnt ? document.getElementById('wfUsername').value : '';
        btn.disabled = true; cancelBtn.disabled = true;
        btn.innerHTML = '<span class="wf-spinner"></span>Connecting…'; msg.textContent = '';
        try {
            const r = await fetch('/api/wifi/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ssid: wfSelected.ssid, password, username }) });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error(d.error || 'Connection failed');
            msg.textContent = '✓ Connected! Hotspot shutting down…'; msg.className = 'wf-msg wf-msg-ok';
            setTimeout(() => { document.getElementById('wfConfirmOverlay').style.display = 'none'; wfDeselect(); wfLoadStatus(); }, 2500);
        } catch (e) {
            msg.textContent = '✗ ' + e.message; msg.className = 'wf-msg wf-msg-err';
            btn.disabled = false; cancelBtn.disabled = false; btn.textContent = 'Connect Now';
        }
    };
    window.wfToggleHotspot = async function () {
        const btn = document.getElementById('wfHotspotBtn'); btn.disabled = true;
        try { await fetch('/api/wifi/hotspot', { method: 'PUT' }); setTimeout(wfLoadStatus, 1500); } finally { btn.disabled = false; }
    };
    document.getElementById('wifi-tab').addEventListener('shown.bs.tab', function () { wfLoadStatus(); wfScan(); });
})();

// --- Emotion Tab Logic ---
(function () {
    window.emSetMood = async function (mood) {
        document.querySelectorAll('.em-btn').forEach(b => b.classList.remove('active'));
        event.currentTarget.classList.add('active');
        const status = document.getElementById('emStatus'); status.textContent = 'Sending…';
        try {
            const r = await fetch('/api/eyes/mood', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mood }) });
            const d = await r.json();
            status.textContent = d.success ? '✓ Mood set to ' + mood.toLowerCase() : '✗ ' + (d.error || 'failed');
        } catch (e) { status.textContent = '✗ ' + e.message; }
    };
})();

// --- Global Avatar & UI Logic ---
let talkingheadBaseUrl = '';
const tabButtons = document.querySelectorAll('.custom-tab');
tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        tabButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

let avatarIsTalking = false, avatarIsBlinking = false;
let avatarNextBlink = Date.now() + 3000 + Math.random() * 1000;
let avatarBlinkEnd = 0, avatarSprites = {}, avatarImages = {};

function preloadAvatarSprites(spriteUrls) {
    avatarSprites = spriteUrls; avatarImages = {};
    for (const [key, url] of Object.entries(spriteUrls)) {
        const img = new window.Image(); img.src = url; avatarImages[key] = img;
    }
}
function updateAvatarFrame() {
    const now = Date.now();
    if (!avatarIsBlinking && now >= avatarNextBlink) { avatarIsBlinking = true; avatarBlinkEnd = now + 400; }
    if (avatarIsBlinking && now >= avatarBlinkEnd) { avatarIsBlinking = false; avatarNextBlink = now + 3000 + Math.random() * 1000; }
    let key;
    if (avatarIsTalking) {
        key = avatarIsBlinking ? 'talking_closed' : (Math.random() < 0.7 ? 'talking_open' : 'nottalking_open');
    } else { key = avatarIsBlinking ? 'nottalking_closed' : 'nottalking_open'; }
    const el = document.getElementById('backgroundImage');
    if (el && avatarSprites[key]) el.src = avatarSprites[key];
}
setInterval(updateAvatarFrame, 100);

fetch('/get_ip').then(r => r.json()).then(d => { talkingheadBaseUrl = d.talkinghead_base_url; }).catch(e => console.error(e));
fetch('/avatar_sprites').then(r => r.json()).then(d => {
    preloadAvatarSprites(d);
    if (d.nottalking_open) document.getElementById('backgroundImage').src = d.nottalking_open;
}).catch(e => console.error(e));

let isMuted = false;
function start_talking() { if (!isMuted) avatarIsTalking = true; }
function stop_talking() { avatarIsTalking = false; }

document.addEventListener("DOMContentLoaded", function () {
    const audioPlayer = document.getElementById("audioPlayer");
    const muteButton = document.getElementById("muteButton");
    muteButton.addEventListener("click", function () {
        const icon = this.querySelector('i');
        if (isMuted) {
            audioPlayer.muted = false;
            icon.classList.replace('bi-volume-mute-fill', 'bi-volume-up-fill');
            muteButton.setAttribute('aria-label', 'Mute');
            if (!audioPlayer.paused) start_talking();
        } else {
            audioPlayer.muted = true;
            icon.classList.replace('bi-volume-up-fill', 'bi-volume-mute-fill');
            muteButton.setAttribute('aria-label', 'Unmute');
            stop_talking();
        }
        isMuted = !isMuted;
    });
});

var audioPlayer = document.getElementById('audioPlayer');
audioPlayer.addEventListener('ended', stop_talking);

let audioStarted = false, firstChunkPlayed = false;
function startAudioStream() {
    if (audioStarted) return;
    audioStarted = true; firstChunkPlayed = false;
    fetch('/audio_stream').then(r => r.blob()).then(blob => {
        if (blob.size === 0) return;
        const url = URL.createObjectURL(blob);
        audioPlayer.src = url; audioPlayer.load();
        audioPlayer.play().then(() => {
            firstChunkPlayed = true;
            audioPlayer.onended = () => { setTimeout(() => playNextAudioChunk(), 500); };
        }).catch(e => console.error(e));
    }).catch(e => console.error(e));
}
function playNextAudioChunk() {
    fetch('/get_next_audio_chunk').then(r => {
        if (r.status === 204) { stop_talking(); audioStarted = false; return null; }
        return r.blob();
    }).then(blob => {
        if (blob) {
            const url = URL.createObjectURL(blob);
            audioPlayer.src = url; audioPlayer.load();
            audioPlayer.play().then(() => {
                start_talking();
                audioPlayer.onended = () => { setTimeout(() => playNextAudioChunk(), 500); };
            });
        }
    }).catch(e => console.error(e));
}

// ── ARM CONTROLS ──
function updateArmConstraints() {
    const armTab = document.getElementById('arms');
    const displays = armTab.querySelectorAll('.servo-value-display');
    const leftMain = parseInt(document.getElementById('leftMain').value);
    const leftForearmSlider = document.getElementById('leftForearm');
    const leftHandSlider = document.getElementById('leftHand');
    let maxLeftForearm = leftMain <= 50 ? Math.max(1, Math.round(leftMain / 2)) : Math.round(25 + (leftMain - 50) * 1.5);
    let leftForearmValue = parseInt(leftForearmSlider.value);
    if (leftForearmValue > maxLeftForearm) { leftForearmSlider.value = maxLeftForearm; displays[1].textContent = maxLeftForearm; leftForearmValue = maxLeftForearm; }
    updateSliderGauge(leftForearmSlider, maxLeftForearm);
    let maxLeftHand = leftForearmValue <= 50 ? Math.max(1, Math.round(leftForearmValue / 2)) : Math.round(25 + (leftForearmValue - 50) * 1.5);
    let leftHandValue = parseInt(leftHandSlider.value);
    if (leftHandValue > maxLeftHand) { leftHandSlider.value = maxLeftHand; displays[2].textContent = maxLeftHand; }
    updateSliderGauge(leftHandSlider, maxLeftHand);
    const rightMain = parseInt(document.getElementById('rightMain').value);
    const rightForearmSlider = document.getElementById('rightForearm');
    const rightHandSlider = document.getElementById('rightHand');
    let maxRightForearm = rightMain <= 50 ? Math.max(1, Math.round(rightMain / 2)) : Math.round(25 + (rightMain - 50) * 1.5);
    let rightForearmValue = parseInt(rightForearmSlider.value);
    if (rightForearmValue > maxRightForearm) { rightForearmSlider.value = maxRightForearm; displays[4].textContent = maxRightForearm; rightForearmValue = maxRightForearm; }
    updateSliderGauge(rightForearmSlider, maxRightForearm);
    let maxRightHand = rightForearmValue <= 50 ? Math.max(1, Math.round(rightForearmValue / 2)) : Math.round(25 + (rightForearmValue - 50) * 1.5);
    let rightHandValue = parseInt(rightHandSlider.value);
    if (rightHandValue > maxRightHand) { rightHandSlider.value = maxRightHand; displays[5].textContent = maxRightHand; }
    updateSliderGauge(rightHandSlider, maxRightHand);
}
function updateSliderGauge(slider, maxAllowed) {
    const pct = (maxAllowed / 100) * 100;
    slider.style.background = `linear-gradient(to top, rgba(0,229,255,0.3) 0%, rgba(0,229,255,0.3) ${pct}%, rgba(220,53,69,0.3) ${pct}%, rgba(220,53,69,0.3) 100%)`;
}
function updateArmValueDisplay(slider, index) {
    document.getElementById('arms').querySelectorAll('.servo-value-display')[index].textContent = slider.value;
}
function resetArmServo(servoId, index) {
    const input = document.getElementById(servoId); input.value = 1;
    document.getElementById('arms').querySelectorAll('.servo-value-display')[index].textContent = '1';
    updateArmConstraints();
}
function sendArmCommand(lm, lf, lh, rm, rf, rh, speedOverride = null) {
    const speed = speedOverride !== null ? speedOverride : parseFloat(document.getElementById('armSpeedSlider').value);
    return fetch('/move_arms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ left_main: lm, left_forearm: lf, left_hand: lh, right_main: rm, right_forearm: rf, right_hand: rh, speed }) });
}
function applyArmControls() {
    const lm = parseInt(document.getElementById('leftMain').value), lf = parseInt(document.getElementById('leftForearm').value),
        lh = parseInt(document.getElementById('leftHand').value), rm = parseInt(document.getElementById('rightMain').value),
        rf = parseInt(document.getElementById('rightForearm').value), rh = parseInt(document.getElementById('rightHand').value),
        speed = parseFloat(document.getElementById('armSpeedSlider').value);
    fetch('/move_arms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ left_main: lm, left_forearm: lf, left_hand: lh, right_main: rm, right_forearm: rf, right_hand: rh, speed }) })
        .then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e));
}
function resetAllArms() {
    sendArmCommand(1, 1, 1, 1, 1, 1, 0.75).then(() => {
        ['leftMain', 'leftForearm', 'leftHand', 'rightMain', 'rightForearm', 'rightHand'].forEach(id => document.getElementById(id).value = 1);
        document.getElementById('arms').querySelectorAll('.servo-value-display').forEach(d => d.textContent = '1');
        updateArmConstraints();
        return fetch('/disable_servos', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    }).then(r => r && r.json()).then(() => fetch('/reset_positions', { method: 'POST', headers: { 'Content-Type': 'application/json' } }))
        .then(r => r && r.json()).then(() => fetch('/disable_servos', { method: 'POST', headers: { 'Content-Type': 'application/json' } }))
        .then(r => r && r.json()).catch(e => console.error(e));
}

function loadMovements() {
    fetch('/get_movements').then(r => r.json()).then(data => {
        if (data.success) {
            const select = document.getElementById('actionSelect');
            select.innerHTML = '';
            const resetOpt = document.createElement('option'); resetOpt.value = 'reset_positions'; resetOpt.textContent = 'Reset Position'; select.appendChild(resetOpt);
            if (data.legs_only && data.legs_only.length > 0) {
                const g = document.createElement('optgroup'); g.label = '── Legs Only ──';
                data.legs_only.forEach(m => { const o = document.createElement('option'); o.value = m.id; o.textContent = m.name; g.appendChild(o); }); select.appendChild(g);
            }
            if (data.has_arms && data.has_arms.length > 0) {
                const g = document.createElement('optgroup'); g.label = '── With Arms ──';
                data.has_arms.forEach(m => { const o = document.createElement('option'); o.value = m.id; o.textContent = m.name; g.appendChild(o); }); select.appendChild(g);
            }
        }
    }).catch(e => console.error(e));
}
document.addEventListener('DOMContentLoaded', loadMovements);

function executeAction() {
    fetch('/execute_action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: document.getElementById('actionSelect').value }) })
        .then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e));
}

// ── LEG CONTROLS ──
function resetServo(servoId, index) {
    document.getElementById(servoId).value = 50;
    document.querySelectorAll('.servo-value-display')[index].textContent = '50';
}
function updateValueDisplay(slider, index) {
    document.querySelectorAll('.servo-value-display')[index].textContent = slider.value;
}
function applyLegControls() {
    fetch('/move_legs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
            left_height: parseInt(document.getElementById('leftHeight').value),
            right_height: parseInt(document.getElementById('rightHeight').value),
            left_leg: parseInt(document.getElementById('leftLeg').value),
            right_leg: parseInt(document.getElementById('rightLeg').value),
            speed: parseFloat(document.getElementById('speedSlider').value)
        })
    }).then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e));
}
function sendLegCommand(lh, rh, ll, rl, speedOverride = null) {
    const speed = speedOverride !== null ? speedOverride : parseFloat(document.getElementById('speedSlider').value);
    return fetch('/move_legs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ left_height: lh, right_height: rh, left_leg: ll, right_leg: rl, speed }) });
}
function resetAllLegs() {
    fetch('/neutral_legs', { method: 'POST', headers: { 'Content-Type': 'application/json' } }).then(r => r.json()).then(data => {
        ['leftHeight', 'rightHeight', 'leftLeg', 'rightLeg'].forEach(id => document.getElementById(id).value = 50);
        document.getElementById('legs').querySelectorAll('.servo-value-display').forEach(d => d.textContent = '50');
        return fetch('/reset_positions', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    }).then(r => r && r.json()).catch(e => console.error(e));
}

// ── MOTION TAB D-PAD ──
document.addEventListener('DOMContentLoaded', function () {
    const btnUp = document.getElementById('btnUp'), btnDown = document.getElementById('btnDown'),
        btnLeft = document.getElementById('btnLeft'), btnRight = document.getElementById('btnRight');
    function getSpeedMode() { const r = document.querySelector('input[name="speed"]:checked'); return r ? r.value : 'fast'; }
    function moveRobot(dir) {
        fetch('/robot_move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction: dir }) })
            .then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e));
    }
    btnUp.addEventListener('click', () => { const s = getSpeedMode(); moveRobot(s === 'fast' ? 'forward' : 'forward_slow'); });
    btnDown.addEventListener('click', () => { const s = getSpeedMode(); moveRobot(s === 'fast' ? 'backward' : 'backward_slow'); });
    btnLeft.addEventListener('click', () => { const s = getSpeedMode(); moveRobot(s === 'fast' ? 'left' : 'left_slow'); });
    btnRight.addEventListener('click', () => { const s = getSpeedMode(); moveRobot(s === 'fast' ? 'right' : 'right_slow'); });

    // ── IMAGE UPLOAD ──
    let selectedImageFile = null;
    document.getElementById('uploadImageButton').addEventListener('click', () => document.getElementById('imageUpload').click());
    document.getElementById('imageUpload').addEventListener('change', function () {
        const f = this.files[0];
        if (f) {
            selectedImageFile = f;
            const reader = new FileReader();
            reader.onload = e => { document.getElementById('imagePreview').src = e.target.result; document.getElementById('imagePreviewContainer').style.display = 'block'; };
            reader.readAsDataURL(f);
        }
    });
    document.getElementById('removeImageButton').addEventListener('click', () => {
        selectedImageFile = null;
        document.getElementById('imagePreviewContainer').style.display = 'none';
        document.getElementById('imagePreview').src = '';
    });

    // ── SOCKET.IO ──
    var socket = io.connect('http://' + document.domain + ':' + location.port);
    socket.on('bot_message', d => displayBotMessage(d.message));
    socket.on('user_message', d => displayUserMessage(d.message));
    socket.on('disconnect', () => setTimeout(() => socket.connect(), 5000));
    socket.on('talking_state', d => { avatarIsTalking = d.talking; });
    socket.on('emotion_change', d => preloadAvatarSprites(d));

    function formatText(text) {
        text = text.replace(/\n/g, '<br>');
        text = text.replace(/\*(.*?)\*/g, '<span class="emphasized-text">$1</span>');
        text = text.replace(/``(.*?)``/g, '<span class="code-text">$1</span>');
        text = text.replace(/\\u([\dA-F]{4})/gi, (m, g) => String.fromCharCode(parseInt(g, 16)));
        return text;
    }

    // These variables are injected via Flask Template markers. 
    // They are handled in the HTML call using data-attributes or script constants.
    // See the HTML section for how to pass these values.

    const promptInput = document.getElementById('prompt'), sendButton = document.getElementById('button-addon2');

    function sendMessage() {
        const userInput = promptInput.value.trim();
        if (userInput || selectedImageFile) {
            displayUserMessage(userInput);
            sendUserMessage(userInput, selectedImageFile);
            promptInput.value = '';
            selectedImageFile = null;
            document.getElementById('imagePreviewContainer').style.display = 'none';
            document.getElementById('imagePreview').src = '';
            delayedMessage();
        }
    }
    if (sendButton) sendButton.addEventListener('click', sendMessage);
    if (promptInput) promptInput.addEventListener('keyup', e => { if (e.key === 'Enter') sendMessage(); });

    function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
    async function delayedMessage() { await delay(1000); displayBotMessage("", true); }

    function sendUserMessage(message, imageFile) {
        const formData = new FormData(); formData.append('message', message);
        if (imageFile) { formData.append('file', imageFile); }
        fetch('/process_llm', { method: 'POST', body: formData }).then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e));
    }

    function displayBotMessage(message, isTemporary = false) {
        const chatBody = document.querySelector('.chat-messages');
        const responseContainer = document.createElement('div');
        responseContainer.className = 'd-flex flex-row justify-content-left mb-4 pt-1';
        const avatarEl = document.createElement('img');
        avatarEl.src = '/static/imgs/char.png'; avatarEl.alt = 'avatar 1'; avatarEl.style.width = '45px'; avatarEl.style.height = '100%';
        responseContainer.appendChild(avatarEl);
        const responseContent = document.createElement('div');
        responseContent.className = 'response-content';
        responseContent.style.cssText = 'border:0;box-shadow:0 2px 4px rgba(0,0,0,0.4);background-color:rgba(0,0,0,0.4);border-radius:10px;padding:1%;margin-left:10px;';
        const responseText = document.createElement('div');
        responseText.className = 'response-text'; responseText.innerHTML = formatText(message);
        responseContent.appendChild(responseText); responseContainer.appendChild(responseContent);
        if (isTemporary) {
            responseContainer.classList.add('is-typing');
            const typingEl = document.createElement('div'); typingEl.textContent = 'Is Typing'; typingEl.className = 'typing-dots';
            responseContent.appendChild(typingEl);
        } else { removeTypingMessage(); }
        chatBody.appendChild(responseContainer); chatBody.scrollTop = chatBody.scrollHeight;
        startAudioStream();
    }
    function removeTypingMessage() {
        const chatBody = document.querySelector('.chat-messages');
        const typing = chatBody.getElementsByClassName('is-typing');
        while (typing.length > 0) typing[0].parentNode.removeChild(typing[0]);
    }
    function displayUserMessage(message) {
        const chatBody = document.querySelector('.chat-messages');
        const userInputContainer = document.createElement('div');
        userInputContainer.className = 'd-flex flex-row justify-content-end mb-4 pt-1'; userInputContainer.style.cssText = 'width:100%;';
        const imgContainer = document.createElement('div');
        imgContainer.style.cssText = 'display:flex;justify-content:flex-end;width:100%;margin-bottom:5px;';
        if (selectedImageFile) {
            const reader = new FileReader(); reader.onload = e => { const img = document.createElement('img'); img.src = e.target.result; img.style.cssText = 'max-width:200px;border-radius:10px;display:block;margin-left:auto;'; imgContainer.appendChild(img); };
            reader.readAsDataURL(selectedImageFile);
        }
        const userInputContent = document.createElement('div');
        userInputContent.className = 'd-flex flex-column';
        userInputContent.style.cssText = 'color:rgb(204,204,204);border:0;box-shadow:0 2px 4px rgba(0,0,0,0.4);background-color:rgba(0,0,0,0.4);border-radius:10px;padding:1%;margin-right:10px;max-width:80%;align-self:flex-start;';
        const userInputText = document.createElement('p');
        userInputText.className = 'firstmess'; userInputText.id = 'user'; userInputText.innerHTML = formatText(message);
        userInputText.style.cssText = 'color:rgb(204,204,204);margin:0;padding:0;white-space:nowrap;word-break:normal;overflow-wrap:break-word;';
        userInputContent.appendChild(userInputText);
        userInputContainer.appendChild(imgContainer); userInputContainer.appendChild(userInputContent);
        const userAvatar = document.createElement('img');
        userAvatar.src = '/static/imgs/user.png'; userAvatar.alt = 'avatar 1'; userAvatar.style.width = '45px'; userAvatar.style.height = '100%';
        userInputContainer.appendChild(userAvatar);
        chatBody.appendChild(userInputContainer); chatBody.scrollTop = chatBody.scrollHeight;
    }

    // ── CONFIG HELPERS ──
    window.detectArrayValue = function (value) {
        if (typeof value !== 'string') return { isArray: false, type: null, items: [] };
        const t = value.trim();
        if (t.startsWith('[') && t.endsWith(']')) {
            try { const p = JSON.parse(t); if (Array.isArray(p)) return { isArray: true, type: 'json', items: p }; } catch (e) {
                const inner = t.slice(1, -1).trim();
                if (inner.includes(',')) { const items = parseCommaSeparatedWithQuotes(inner); if (items.length > 1) return { isArray: true, type: 'json', items }; }
            }
        }
        if (!t.startsWith('[') && !t.startsWith('http') && t.includes(',')) {
            const items = t.split(',').map(i => i.trim()).filter(i => i.length > 0);
            if (items.length > 1) return { isArray: true, type: 'csv', items };
        }
        return { isArray: false, type: null, items: [] };
    }
    function parseCommaSeparatedWithQuotes(str) {
        const items = []; let current = '', inQuote = false, quoteChar = null;
        for (const char of str) {
            if ((char === '"' || char === "'") && !inQuote) { inQuote = true; quoteChar = char; }
            else if (char === quoteChar && inQuote) { inQuote = false; quoteChar = null; }
            else if (char === ',' && !inQuote) { const t = current.trim().replace(/^["']|["']$/g, ''); if (t) items.push(t); current = ''; }
            else current += char;
        }
        const t = current.trim().replace(/^["']|["']$/g, ''); if (t) items.push(t); return items;
    }
    function arrayToConfigValue(items, originalType) { return originalType === 'json' ? JSON.stringify(items) : items.join(','); }
    function escapeHtmlForTags(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
    function escapeForAttribute(str) { return str.replace(/'/g, '&#39;'); }

    function generateTagInputHtml(fieldId, section, key, items, arrayType) {
        const tagsHtml = items.map((item, i) => `<span class="config-tag" data-index="${i}"><span class="config-tag-text">${escapeHtmlForTags(String(item))}</span><button type="button" class="config-tag-remove" data-index="${i}" aria-label="Remove">×</button></span>`).join('');
        return `<div class="config-tag-input-container" id="${fieldId}" data-section="${section}" data-key="${key}" data-array-type="${arrayType}"><div class="config-tags-wrapper">${tagsHtml}<input type="text" class="config-tag-input" placeholder="Type and press Enter..." /></div><input type="hidden" class="config-array-value" value='${escapeForAttribute(JSON.stringify(items))}' /></div>`;
    }

    function generateScreensaverSelectHtml(fieldId, section, key, currentValue, options) {
        let selectedItems = [];
        if (typeof currentValue === 'string') { const t = currentValue.trim().toLowerCase(); if (t === 'random') selectedItems = ['random']; else if (t) selectedItems = currentValue.split(',').map(s => s.trim().toLowerCase()).filter(s => s); }
        const optionsHtml = options.map(option => { const isRandom = option.toLowerCase() === 'random', isSelected = selectedItems.includes(option.toLowerCase()); return `<span class="screensaver-option${isSelected ? ' selected' : ''}${isRandom ? ' random-option' : ''}" data-value="${option}">${isRandom ? '<i class="bi bi-shuffle" style="font-size:10px;margin-right:3px;"></i>' : ''}${option}</span>`; }).join('');
        return `<div class="screensaver-select-container" id="${fieldId}" data-section="${section}" data-key="${key}"><div class="screensaver-select-options">${optionsHtml}</div><input type="hidden" class="screensaver-select-value" value="${escapeHtmlForTags(currentValue)}" /></div>`;
    }

    function initializeScreensaverSelects() {
        document.querySelectorAll('.screensaver-select-container').forEach(container => {
            const hiddenInput = container.querySelector('.screensaver-select-value');
            const optionsWrapper = container.querySelector('.screensaver-select-options');
            function getSelectedItems() { const v = hiddenInput.value.trim().toLowerCase(); if (v === 'random') return ['random']; if (!v) return []; return v.split(',').map(s => s.trim()).filter(s => s); }
            function setSelectedItems(items) {
                if (items.length === 0 || items.includes('random')) { hiddenInput.value = 'random'; items = ['random']; }
                else hiddenInput.value = items.join(',');
                optionsWrapper.querySelectorAll('.screensaver-option').forEach(opt => opt.classList.toggle('selected', items.includes(opt.dataset.value.toLowerCase())));
            }
            optionsWrapper.querySelectorAll('.screensaver-option').forEach(option => {
                option.addEventListener('click', function () {
                    const cv = this.dataset.value.toLowerCase(), isRandom = cv === 'random';
                    let sel = getSelectedItems();
                    if (isRandom) { if (sel.includes('random')) return; setSelectedItems(['random']); }
                    else {
                        if (sel.includes(cv)) { sel = sel.filter(s => s !== cv); setSelectedItems(sel.length === 0 ? ['random'] : sel); }
                        else { sel = sel.filter(s => s !== 'random'); sel.push(cv); setSelectedItems(sel); }
                    }
                });
            });
        });
    }

    function initializeTagInputs() {
        document.querySelectorAll('.config-tag-input-container').forEach(container => {
            const input = container.querySelector('.config-tag-input'), wrapper = container.querySelector('.config-tags-wrapper'), hiddenInput = container.querySelector('.config-array-value');
            const isScreensaverList = container.dataset.section === 'UI' && container.dataset.key === 'screensaver_list';
            function getItems() { try { return JSON.parse(hiddenInput.value) || []; } catch { return []; } }
            function setItems(items) { hiddenInput.value = JSON.stringify(items); renderTags(); }
            function renderTags() {
                const items = getItems(); wrapper.querySelectorAll('.config-tag').forEach(t => t.remove());
                const html = items.map((item, i) => `<span class="config-tag" data-index="${i}"><span class="config-tag-text">${escapeHtmlForTags(String(item))}</span><button type="button" class="config-tag-remove" data-index="${i}" aria-label="Remove">×</button></span>`).join('');
                input.insertAdjacentHTML('beforebegin', html);
                wrapper.querySelectorAll('.config-tag-remove').forEach(btn => { btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); const items = getItems(); items.splice(parseInt(btn.dataset.index), 1); setItems(items); }); });
            }
            function addItem(text) {
                const t = text.trim(); if (!t) return;
                let items = getItems();
                if (isScreensaverList) {
                    if (t.toLowerCase() === 'random') items = ['random'];
                    else { items = items.filter(i => i.toLowerCase() !== 'random'); if (!items.includes(t)) items.push(t); }
                    setItems(items);
                } else { if (!items.includes(t)) { items.push(t); setItems(items); } }
                input.value = '';
            }
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); addItem(input.value); }
                else if (e.key === 'Backspace' && input.value === '') { const items = getItems(); if (items.length > 0) { items.pop(); setItems(items); } }
            });
            input.addEventListener('paste', e => {
                e.preventDefault();
                const pasted = (e.clipboardData || window.clipboardData).getData('text');
                const newItems = pasted.split(/[,\n]/).map(s => s.trim()).filter(s => s);
                if (newItems.length > 0) {
                    let items = getItems();
                    if (isScreensaverList) { const hasRandom = newItems.some(i => i.toLowerCase() === 'random'); if (hasRandom) { items = ['random']; } else { items = items.filter(i => i.toLowerCase() !== 'random'); newItems.forEach(i => { if (!items.includes(i)) items.push(i); }); } }
                    else newItems.forEach(i => { if (!items.includes(i)) items.push(i); });
                    setItems(items);
                }
            });
            container.addEventListener('click', e => { if (e.target === container || e.target === wrapper) input.focus(); });
            wrapper.querySelectorAll('.config-tag-remove').forEach(btn => { btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); const items = getItems(); items.splice(parseInt(btn.dataset.index), 1); setItems(items); }); });
        });
    }

    function loadConfiguration() {
        fetch('/get_config').then(r => r.json()).then(data => {
            const configForm = document.getElementById('configForm');
            let formHtml = '<div class="accordion" id="configAccordion">';
            let sectionIndex = 0;
            for (const [section, fields] of Object.entries(data.config)) {
                const sectionDesc = data.field_options[`${section}.__section__`];
                const accordionId = `collapse${sectionIndex}`, isFirst = sectionIndex === 0;
                formHtml += `<div class="accordion-item config-accordion-item"><h2 class="accordion-header"><button class="accordion-button config-accordion-button${isFirst ? '' : ' collapsed'}" type="button" data-bs-toggle="collapse" data-bs-target="#${accordionId}" aria-expanded="${isFirst}" aria-controls="${accordionId}"><i class="bi bi-folder-fill me-2"></i><span class="fw-bold">${section}</span>${sectionDesc ? `<small class="ms-2 text-muted opacity-75">- ${sectionDesc.description || sectionDesc}</small>` : ''}</button></h2><div id="${accordionId}" class="accordion-collapse collapse${isFirst ? ' show' : ''}" data-bs-parent="#configAccordion"><div class="accordion-body config-accordion-body">`;
                formHtml += '<div class="row g-3">';
                for (const [key, value] of Object.entries(fields)) {
                    const fieldId = `config_${section}_${key}`, fieldInfo = data.field_options[`${section}.${key}`], description = fieldInfo?.description || '';
                    formHtml += `<div class="col-md-6 col-lg-4"><div class="field-wrapper"><label for="${fieldId}" class="form-label small d-flex align-items-center"><i class="bi bi-gear-fill me-1" style="font-size:10px;opacity:0.4;"></i><span>${key}</span></label>`;
                    if (fieldInfo && fieldInfo.type === 'screensaver_select') { formHtml += generateScreensaverSelectHtml(fieldId, section, key, value, fieldInfo.options || []); }
                    else if (fieldInfo && fieldInfo.options && fieldInfo.type !== 'screensaver_select') {
                        formHtml += `<select class="form-select form-select-sm config-input" id="${fieldId}" data-section="${section}" data-key="${key}">`;
                        fieldInfo.options.forEach(opt => { formHtml += `<option value="${opt}"${String(value) === String(opt) ? ' selected' : ''}>${opt}</option>`; });
                        formHtml += '</select>';
                    } else if (typeof value === 'boolean' || value === 'True' || value === 'False' || value === 'true' || value === 'false') {
                        const checked = (value === true || value === 'True' || value === 'true') ? 'checked' : '';
                        formHtml += `<div class="form-check form-switch mt-2"><input class="form-check-input config-toggle" type="checkbox" id="${fieldId}" data-section="${section}" data-key="${key}" ${checked}><label class="form-check-label small" for="${fieldId}" id="${fieldId}_label">${checked ? 'Enabled' : 'Disabled'}</label></div>`;
                    } else {
                        const isArrayType = fieldInfo && fieldInfo.type === 'array', arrayInfo = detectArrayValue(value);
                        if (isArrayType || arrayInfo.isArray) {
                            const items = arrayInfo.isArray ? arrayInfo.items : (value ? [value] : []);
                            const arrayType = arrayInfo.isArray ? arrayInfo.type : 'csv';
                            formHtml = formHtml.replace(`<span>${key}</span>`, `<span>${key}</span><span class="config-array-badge">${arrayType === 'json' ? 'JSON' : 'LIST'}</span>`);
                            formHtml += generateTagInputHtml(fieldId, section, key, items, arrayType);
                        } else {
                            formHtml += `<input type="text" class="form-control form-control-sm config-input" id="${fieldId}" data-section="${section}" data-key="${key}" value="${escapeHtmlForTags(String(value))}">`;
                        }
                    }
                    if (description) formHtml += `<div class="config-hint mt-1"><i class="bi bi-info-circle me-1"></i><small>${description}</small></div>`;
                    formHtml += '</div></div>';
                }
                formHtml += '</div></div></div></div>';
                sectionIndex++;
            }
            formHtml += '</div>';
            configForm.innerHTML = formHtml;
            document.querySelectorAll('.config-toggle').forEach(toggle => {
                toggle.addEventListener('change', function () {
                    const label = document.getElementById(this.id + '_label');
                    if (label) label.textContent = this.checked ? 'Enabled' : 'Disabled';
                });
            });
            initializeTagInputs(); initializeScreensaverSelects();
        }).catch(error => {
            document.getElementById('configForm').innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle me-2"></i>Error loading configuration: ${error.message}</div>`;
        });
    }

    function saveConfiguration() {
        const saveBtn = document.getElementById('saveConfigBtn');
        if (saveBtn.disabled) return;
        const configData = {};
        document.querySelectorAll('#configForm input, #configForm select').forEach(input => {
            if (input.classList.contains('config-array-value') || input.classList.contains('config-tag-input') || input.classList.contains('screensaver-select-value')) return;
            const section = input.getAttribute('data-section'), key = input.getAttribute('data-key');
            if (!section || !key) return;
            if (!configData[section]) configData[section] = {};
            configData[section][key] = input.type === 'checkbox' ? input.checked : input.value;
        });
        document.querySelectorAll('.config-tag-input-container').forEach(container => {
            const section = container.dataset.section, key = container.dataset.key, arrayType = container.dataset.arrayType;
            const hiddenInput = container.querySelector('.config-array-value');
            if (!configData[section]) configData[section] = {};
            try { const items = JSON.parse(hiddenInput.value) || []; configData[section][key] = arrayToConfigValue(items, arrayType); } catch { configData[section][key] = ''; }
        });
        document.querySelectorAll('.screensaver-select-container').forEach(container => {
            const section = container.dataset.section, key = container.dataset.key, hiddenInput = container.querySelector('.screensaver-select-value');
            if (!configData[section]) configData[section] = {};
            configData[section][key] = hiddenInput.value;
        });
        const originalHtml = saveBtn.innerHTML, originalClass = saveBtn.className;
        saveBtn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i><span>Saving...</span>'; saveBtn.disabled = true;
        fetch('/save_config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(configData) }).then(r => r.json()).then(data => {
            if (data.success) {
                saveBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i><span>Saved!</span>'; saveBtn.className = 'btn save-config-btn-success';
                setTimeout(() => { saveBtn.innerHTML = originalHtml; saveBtn.className = originalClass; saveBtn.disabled = false; }, 2000);
            } else { saveBtn.innerHTML = originalHtml; saveBtn.className = originalClass; saveBtn.disabled = false; alert('Error: ' + (data.error || 'Unknown error')); }
        }).catch(error => { saveBtn.innerHTML = originalHtml; saveBtn.className = originalClass; saveBtn.disabled = false; alert('Error: ' + error.message); });
    }

    const configTab = document.getElementById('config-tab');
    if (configTab) configTab.addEventListener('click', () => { if (document.getElementById('configForm').innerHTML.includes('Loading')) loadConfiguration(); });
    const saveBtn = document.getElementById('saveConfigBtn');
    if (saveBtn) saveBtn.addEventListener('click', e => { e.preventDefault(); saveConfiguration(); });
});

// ── TAB RESET LOGIC ──
document.addEventListener('DOMContentLoaded', function () {
    const legsTab = document.getElementById('legs-tab'), armsTab = document.getElementById('arms-tab');
    if (legsTab) legsTab.addEventListener('hide.bs.tab', function () {
        const lh = parseInt(document.getElementById('leftHeight').value), rh = parseInt(document.getElementById('rightHeight').value),
            ll = parseInt(document.getElementById('leftLeg').value), rl = parseInt(document.getElementById('rightLeg').value);
        if (lh !== 50 || rh !== 50 || ll !== 50 || rl !== 50) resetAllLegs();
    });
    if (armsTab) armsTab.addEventListener('hide.bs.tab', function () {
        const lm = parseInt(document.getElementById('leftMain').value), lf = parseInt(document.getElementById('leftForearm').value),
            lh = parseInt(document.getElementById('leftHand').value), rm = parseInt(document.getElementById('rightMain').value),
            rf = parseInt(document.getElementById('rightForearm').value), rh = parseInt(document.getElementById('rightHand').value);
        if (lm !== 1 || lf !== 1 || lh !== 1 || rm !== 1 || rf !== 1 || rh !== 1) resetAllArms();
    });
    document.querySelectorAll('.custom-tab').forEach(tab => {
        tab.addEventListener('shown.bs.tab', e => {
            const newTabId = e.target.getAttribute('data-bs-target').replace('#', '');
            if (newTabId === 'legs' || newTabId === 'arms') {
                fetch('/reset_positions', { method: 'POST', headers: { 'Content-Type': 'application/json' } }).then(r => r.json()).catch(e => console.error(e));
            }
        });
    });
});

window.toggleFullscreen = function () {
    const icon = document.getElementById('fullscreen-icon');
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().then(() => { icon.classList.replace('bi-fullscreen', 'bi-fullscreen-exit'); }).catch(e => console.log(e));
    } else {
        if (document.exitFullscreen) document.exitFullscreen().then(() => { icon.classList.replace('bi-fullscreen-exit', 'bi-fullscreen'); });
    }
}
document.addEventListener('fullscreenchange', () => {
    const icon = document.getElementById('fullscreen-icon');
    if (!document.fullscreenElement) icon.classList.replace('bi-fullscreen-exit', 'bi-fullscreen');
});