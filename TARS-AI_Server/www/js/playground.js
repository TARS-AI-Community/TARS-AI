const base='';
function hdr(){return {'Content-Type':'application/json'}}
function hdrForm(){return {}}

function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const map={chat:0,stt:1,tts:2,vis:3,img:4,mus:5};
  document.querySelectorAll('.tab')[map[name]].classList.add('active');
  document.getElementById('p-'+name).classList.add('active');
  if(name==='tts')loadVoices();
}

async function sendChat(){
  const input=document.getElementById('chat-input');const out=document.getElementById('chat-out');
  const text=input.value.trim();if(!text)return;
  input.value='';
  const userDiv=document.createElement('div');userDiv.className='msg user';userDiv.textContent=text;out.appendChild(userDiv);
  const msgDiv=document.createElement('div');msgDiv.className='msg assistant';out.appendChild(msgDiv);
  try{
    const resp=await fetch(base+'/v1/chat/completions',{method:'POST',headers:hdr(),
      body:JSON.stringify({messages:[{role:'user',content:text}],stream:true,max_tokens:512})});
    if(!resp.ok){msgDiv.className='msg error';msgDiv.textContent='Error: '+resp.status+' '+resp.statusText;out.scrollTop=out.scrollHeight;return;}
    const reader=resp.body.getReader();const dec=new TextDecoder();let buf='';
    while(true){
      const{done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data: ')||line==='data: [DONE]')continue;
        try{
          const c=JSON.parse(line.slice(6));
          const t=c.choices[0].delta.content||'';
          if(t)msgDiv.textContent+=t;
          if(c.choices[0].finish_reason==='stop'&&c.usage){
            const u=c.usage;const ms=u.elapsed_ms||1;
            const tps=(u.completion_tokens/(ms/1000)).toFixed(1);
            const stat=document.createElement('div');
            stat.style.cssText='text-align:right;font-size:11px;color:var(--text-dim);margin-top:4px;font-family:var(--font-hud);letter-spacing:.08em';
            stat.textContent=u.completion_tokens+' tokens \u00B7 '+tps+' t/s';
            out.appendChild(stat);
          }
        }catch(e){}
      }
    }
  }catch(e){msgDiv.className='msg error';msgDiv.textContent='Error: '+e;}
  out.scrollTop=out.scrollHeight;
}

async function transcribeFile(){
  const file=document.getElementById('stt-file').files[0];
  if(!file){document.getElementById('stt-out').textContent='Select a file first.';return}
  const fd=new FormData();fd.append('audio',file);
  document.getElementById('stt-out').textContent='Transcribing...';
  try{
    const resp=await fetch(base+'/save_audio',{method:'POST',headers:hdrForm(),body:fd});
    const d=await resp.json();
    const text=d.transcription?d.transcription.map(s=>s.text).join(' '):'(empty)';
    document.getElementById('stt-out').textContent=text;
  }catch(e){document.getElementById('stt-out').textContent='Error: '+e}
}

let mediaRec=null,audioChunks=[];
function toggleRecord(){
  const btn=document.getElementById('rec-btn');
  if(mediaRec&&mediaRec.state==='recording'){
    mediaRec.stop();btn.textContent='Record';btn.className='hud-btn';return;
  }
  navigator.mediaDevices.getUserMedia({audio:true}).then(stream=>{
    mediaRec=new MediaRecorder(stream);audioChunks=[];
    mediaRec.ondataavailable=e=>audioChunks.push(e.data);
    mediaRec.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop());
      const blob=new Blob(audioChunks,{type:'audio/wav'});
      const fd=new FormData();fd.append('audio',blob,'recording.wav');
      document.getElementById('stt-out').textContent='Transcribing...';
      try{
        const resp=await fetch(base+'/save_audio',{method:'POST',headers:hdrForm(),body:fd});
        const d=await resp.json();
        document.getElementById('stt-out').textContent=d.transcription?d.transcription.map(s=>s.text).join(' '):'(empty)';
      }catch(e){document.getElementById('stt-out').textContent='Error: '+e}
    };
    mediaRec.start();btn.textContent='Stop Recording';btn.className='hud-btn recording';
  });
}

async function loadVoices(){
  try{
    const resp=await fetch(base+'/tts/voices',{headers:hdrForm()});
    const d=await resp.json();const sel=document.getElementById('tts-voice');
    sel.innerHTML='';
    (d.voices||[]).forEach(v=>{const o=document.createElement('option');o.value=v;o.text=v;sel.add(o)});
  }catch(e){}
}

async function synthesize(){
  const text=document.getElementById('tts-input').value.trim();if(!text)return;
  const voice=document.getElementById('tts-voice').value||undefined;
  const btn=document.getElementById('tts-btn');
  const status=document.getElementById('tts-status');
  const player=document.getElementById('tts-player');
  btn.textContent='Generating...';btn.style.pointerEvents='none';btn.style.opacity='.5';
  try{
    const t0=performance.now();
    const resp=await fetch(base+'/tts/generate',{method:'POST',headers:hdr(),
      body:JSON.stringify({text,voice})});
    if(!resp.ok){status.textContent='Error: '+resp.status;status.style.color='var(--red)';player.style.display='block';return}
    const blob=await resp.blob();const url=URL.createObjectURL(blob);
    const audio=document.getElementById('tts-audio');audio.src=url;
    player.style.display='flex';
    const ms=Math.round(performance.now()-t0);
    status.style.color='var(--text-dim)';
    status.textContent='Generated in '+ms+'ms \u00B7 '+(blob.size/1024).toFixed(1)+' KB';
    audio.play();
  }catch(e){status.textContent='Error: '+e;status.style.color='var(--red)';player.style.display='flex'}
  finally{btn.textContent='Speak';btn.style.pointerEvents='';btn.style.opacity=''}
}

async function captionImg(){
  const file=document.getElementById('vis-file').files[0];
  if(!file){document.getElementById('vis-out').textContent='Select an image first.';return}
  const prompt=document.getElementById('vis-prompt').value.trim();
  document.getElementById('vis-out').textContent='Captioning...';
  const fd=new FormData();fd.append('image',file);
  if(prompt)fd.append('prompt',prompt);
  try{
    const t0=performance.now();
    const resp=await fetch(base+'/caption',{method:'POST',body:fd});
    if(!resp.ok){document.getElementById('vis-out').textContent='Error: '+resp.status+' '+resp.statusText;return}
    const d=await resp.json();
    const ms=Math.round(performance.now()-t0);
    document.getElementById('vis-out').textContent=d.caption+'\n\n('+ms+'ms)';
  }catch(e){document.getElementById('vis-out').textContent='Error: '+e}
}

function _uid(){try{return crypto.randomUUID()}catch(e){return 'xxxx-xxxx-xxxx-xxxx'.replace(/x/g,function(){return(Math.random()*16|0).toString(16)})}}
async function generateImg(){
  const prompt=document.getElementById('img-prompt').value.trim();if(!prompt)return;
  const neg=document.getElementById('img-neg').value.trim();
  const steps=parseInt(document.getElementById('img-steps').value)||20;
  const width=parseInt(document.getElementById('img-width').value)||1024;
  const height=parseInt(document.getElementById('img-height').value)||1024;
  const cfg=parseFloat(document.getElementById('img-cfg').value)||7.0;
  const seed=parseInt(document.getElementById('img-seed').value);
  const taskId=_uid();
  const btn=document.getElementById('img-gen-btn');
  btn.disabled=true;btn.style.opacity='0.5';
  document.getElementById('img-out').textContent='';
  document.getElementById('img-preview-wrap').style.display='none';
  const wrap=document.getElementById('img-progress-wrap');
  const bar=document.getElementById('img-progress-bar');
  const pctEl=document.getElementById('img-progress-pct');
  const lbl=document.getElementById('img-progress-label');
  wrap.style.display='block';bar.style.width='0%';pctEl.textContent='0%';lbl.textContent='Starting...';
  let done=false;
  const poll=setInterval(function(){
    if(done)return;
    fetch(base+'/imagegen_progress/'+taskId).then(function(r){return r.json()}).then(function(d){
      if(done)return;
      if(d.active&&d.total>0){
        var p=Math.round(d.step/d.total*100);
        bar.style.width=p+'%';pctEl.textContent=p+'%';
        lbl.textContent='Step '+d.step+' / '+d.total;
      }
    }).catch(function(){});
  },500);
  try{
    const resp=await fetch(base+'/generate_image',{method:'POST',headers:hdr(),
      body:JSON.stringify({prompt:prompt,negative_prompt:neg,steps:steps,width:width,height:height,cfg_scale:cfg,seed:isNaN(seed)?-1:seed,task_id:taskId})});
    done=true;clearInterval(poll);
    bar.style.width='100%';pctEl.textContent='100%';lbl.textContent='Complete';
    if(!resp.ok){document.getElementById('img-out').textContent='Error: '+resp.status+' '+resp.statusText;setTimeout(function(){wrap.style.display='none'},2000);return}
    const blob=await resp.blob();const url=URL.createObjectURL(blob);
    const img=document.getElementById('img-preview');img.src=url;document.getElementById('img-preview-wrap').style.display='block';
    document.getElementById('img-out').textContent='Done.';
    setTimeout(function(){wrap.style.display='none'},2000);
    loadGallery();
  }catch(e){done=true;clearInterval(poll);wrap.style.display='none';document.getElementById('img-out').textContent='Error: '+e}
  finally{btn.disabled=false;btn.style.opacity=''}
}

document.getElementById('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat()}});
loadVoices();
fetch(base+'/api/settings').then(function(r){return r.json()}).then(function(d){
  if(d.imagegen){
    if(d.imagegen.default_steps)document.getElementById('img-steps').value=d.imagegen.default_steps;
    if(d.imagegen.default_cfg)document.getElementById('img-cfg').value=d.imagegen.default_cfg;
  }
  if(d.musicgen){
    if(d.musicgen.default_duration)document.getElementById('mus-duration').value=d.musicgen.default_duration;
    if(d.musicgen.default_steps)document.getElementById('mus-steps').value=d.musicgen.default_steps;
    if(d.musicgen.default_cfg)document.getElementById('mus-cfg').value=d.musicgen.default_cfg;
  }
}).catch(function(){});
(function(){
  var p=document.getElementById('img-prompt'),n=document.getElementById('img-neg');
  var sp=localStorage.getItem('img-prompt'),sn=localStorage.getItem('img-neg');
  if(sp)p.value=sp;if(sn)n.value=sn;
  p.addEventListener('input',function(){localStorage.setItem('img-prompt',p.value)});
  n.addEventListener('input',function(){localStorage.setItem('img-neg',n.value)});
})();

async function loadGallery(){
  var g=document.getElementById('img-gallery');
  try{
    var r=await fetch(base+'/imagegen_gallery');var d=await r.json();
    if(!d.images||!d.images.length){g.innerHTML='';return}
    var html='<label style="margin-top:8px">Gallery</label><div class="img-gallery-grid">';
    d.images.forEach(function(item){
      var m=item.meta||{};
      var tip=(m.prompt||'')+(m.timestamp?'\n'+m.timestamp:'')+(m.steps?'\nSteps: '+m.steps:'')+(m.cfg_scale?'  CFG: '+m.cfg_scale:'')+(m.seed?'  Seed: '+m.seed:'');
      html+='<div class="img-gallery-item" data-file="'+item.filename+'">';
      html+='<img src="'+base+'/imagegen_gallery/file/'+item.filename+'" title="'+tip.replace(/"/g,'&quot;')+'">';
      html+='<button class="img-del" data-del="'+item.filename+'">&times;</button>';
      html+='<div class="img-meta">'+(m.prompt?m.prompt.substring(0,40):'')+'</div>';
      html+='</div>';
    });
    html+='</div>';
    g.innerHTML=html;
  }catch(e){g.innerHTML=''}
}
document.getElementById('img-gallery').addEventListener('click',function(e){
  var del=e.target.closest('[data-del]');
  if(del){
    e.stopPropagation();e.preventDefault();
    fetch(base+'/imagegen_gallery/'+del.getAttribute('data-del'),{method:'DELETE'}).then(function(){loadGallery()});
    return;
  }
  var item=e.target.closest('.img-gallery-item');
  if(item&&e.target.tagName==='IMG'){
    document.getElementById('img-preview').src=e.target.src;
    document.getElementById('img-preview-wrap').style.display='block';
  }
});
loadGallery();

// Custom audio player
function _fmt(s){if(!s||!isFinite(s))return '0:00';var m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+(sec<10?'0':'')+sec}
function createPlayer(container,src,small,title,onDelete){
  container.innerHTML='';
  var audio=new Audio();
  audio.preload='auto';
  audio.crossOrigin='anonymous';
  var wrap=document.createElement('div');wrap.className='tars-player'+(small?' tp-sm':'');
  var btn=document.createElement('button');btn.className='tp-btn';btn.type='button';btn.textContent='\u25B6';
  var track=document.createElement('div');track.className='tp-track';
  var barWrap=document.createElement('div');barWrap.className='tp-bar-wrap';
  var barBg=document.createElement('div');barBg.className='tp-bar-bg';
  var bar=document.createElement('div');bar.className='tp-bar';
  var thumb=document.createElement('div');thumb.className='tp-thumb';
  var timeRow=document.createElement('div');timeRow.className='tp-time';
  var tCur=document.createElement('span');tCur.textContent='0:00';
  var tDur=document.createElement('span');tDur.textContent='0:00';
  barWrap.appendChild(barBg);barWrap.appendChild(bar);barWrap.appendChild(thumb);
  timeRow.appendChild(tCur);
  if(title){var titleEl=document.createElement('div');titleEl.className='tp-title';titleEl.textContent=title;titleEl.title=title;timeRow.appendChild(titleEl)}
  timeRow.appendChild(tDur);
  track.appendChild(barWrap);track.appendChild(timeRow);
  wrap.appendChild(btn);wrap.appendChild(track);
  if(onDelete){
    var delBtn=document.createElement('button');delBtn.className='tp-del';delBtn.type='button';delBtn.textContent='\u00D7';
    delBtn.addEventListener('click',function(e){e.stopPropagation();e.preventDefault();onDelete()});
    wrap.appendChild(delBtn);
  }
  container.appendChild(wrap);

  var dragging=false,ready=false;

  function updateBar(){
    if(!ready||!isFinite(audio.duration))return;
    var p=audio.currentTime/audio.duration*100;
    bar.style.width=p+'%';thumb.style.left=p+'%';
    tCur.textContent=_fmt(audio.currentTime);
  }

  function seek(clientX){
    if(!ready||!isFinite(audio.duration))return;
    var r=barWrap.getBoundingClientRect();
    var p=Math.max(0,Math.min(1,(clientX-r.left)/r.width));
    audio.currentTime=p*audio.duration;
    updateBar();
  }

  btn.addEventListener('click',function(){
    if(!ready)return;
    if(audio.paused){audio.play()}else{audio.pause()}
  });

  audio.addEventListener('loadedmetadata',function(){ready=true;tDur.textContent=_fmt(audio.duration)});
  audio.addEventListener('canplay',function(){ready=true;tDur.textContent=_fmt(audio.duration)});
  audio.addEventListener('play',function(){btn.textContent='\u23F8'});
  audio.addEventListener('pause',function(){btn.textContent='\u25B6'});
  audio.addEventListener('timeupdate',function(){if(!dragging)updateBar()});
  audio.addEventListener('ended',function(){btn.textContent='\u25B6';bar.style.width='0%';thumb.style.left='0%';tCur.textContent='0:00'});

  barWrap.addEventListener('mousedown',function(e){
    e.preventDefault();
    dragging=true;seek(e.clientX);
    function onMove(ev){ev.preventDefault();seek(ev.clientX)}
    function onUp(){dragging=false;document.removeEventListener('mousemove',onMove);document.removeEventListener('mouseup',onUp)}
    document.addEventListener('mousemove',onMove);
    document.addEventListener('mouseup',onUp);
  });

  barWrap.addEventListener('touchstart',function(e){
    dragging=true;seek(e.touches[0].clientX);
    function onMove(ev){seek(ev.touches[0].clientX)}
    function onEnd(){dragging=false;document.removeEventListener('touchmove',onMove);document.removeEventListener('touchend',onEnd)}
    document.addEventListener('touchmove',onMove,{passive:true});
    document.addEventListener('touchend',onEnd);
  },{passive:true});

  audio.src=src;
  return audio;
}

// MusicGen
async function generateMusic(){
  var prompt=document.getElementById('mus-prompt').value.trim();if(!prompt)return;
  var lyrics=document.getElementById('mus-lyrics').value;
  var duration=parseFloat(document.getElementById('mus-duration').value)||60;
  var steps=parseInt(document.getElementById('mus-steps').value)||60;
  var cfg=parseFloat(document.getElementById('mus-cfg').value)||15.0;
  var seed=parseInt(document.getElementById('mus-seed').value);
  var taskId=_uid();
  var btn=document.getElementById('mus-gen-btn');
  btn.disabled=true;btn.style.opacity='0.5';
  document.getElementById('mus-out').textContent='';
  document.getElementById('mus-player').style.display='none';
  var wrap=document.getElementById('mus-progress-wrap');
  var bar=document.getElementById('mus-progress-bar');
  var pctEl=document.getElementById('mus-progress-pct');
  var lbl=document.getElementById('mus-progress-label');
  wrap.style.display='block';bar.style.width='0%';pctEl.textContent='0%';lbl.textContent='Starting...';
  var done=false;
  var poll=setInterval(function(){
    if(done)return;
    fetch(base+'/musicgen_progress/'+taskId).then(function(r){return r.json()}).then(function(d){
      if(done)return;
      if(d.active){
        bar.style.width=d.pct+'%';pctEl.textContent=d.pct+'%';
        lbl.textContent=d.status.charAt(0).toUpperCase()+d.status.slice(1)+'...';
      }
    }).catch(function(){});
  },500);
  try{
    var resp=await fetch(base+'/generate_music',{method:'POST',headers:hdr(),
      body:JSON.stringify({prompt:prompt,lyrics:lyrics,duration:duration,steps:steps,guidance_scale:cfg,seed:isNaN(seed)?-1:seed,task_id:taskId})});
    done=true;clearInterval(poll);
    bar.style.width='100%';pctEl.textContent='100%';lbl.textContent='Complete';
    if(!resp.ok){document.getElementById('mus-out').textContent='Error: '+resp.status+' '+resp.statusText;setTimeout(function(){wrap.style.display='none'},2000);return}
    var blob=await resp.blob();var url=URL.createObjectURL(blob);
    var playerDiv=document.getElementById('mus-player');
    playerDiv.style.display='block';
    var audio=createPlayer(playerDiv,url,false);
    audio.play();
    document.getElementById('mus-out').textContent='Done.';
    setTimeout(function(){wrap.style.display='none'},2000);
    loadMusicGallery();
  }catch(e){done=true;clearInterval(poll);wrap.style.display='none';document.getElementById('mus-out').textContent='Error: '+e}
  finally{btn.disabled=false;btn.style.opacity=''}
}
async function loadMusicGallery(){
  var g=document.getElementById('mus-gallery');
  try{
    var r=await fetch(base+'/musicgen_gallery');var d=await r.json();
    if(!d.tracks||!d.tracks.length){g.innerHTML='';return}
    g.innerHTML='<label style="margin-top:8px">Gallery</label>';
    d.tracks.forEach(function(item){
      var m=item.meta||{};
      var playerWrap=document.createElement('div');playerWrap.style.cssText='margin:6px 0';
      createPlayer(playerWrap,base+'/musicgen_gallery/file/'+item.filename,true,m.prompt||'',function(){
        fetch(base+'/musicgen_gallery/'+item.filename,{method:'DELETE'}).then(function(){loadMusicGallery()});
      });
      g.appendChild(playerWrap);
    });
  }catch(e){g.innerHTML=''}
}
(function(){
  var p=document.getElementById('mus-prompt'),l=document.getElementById('mus-lyrics');
  var sp=localStorage.getItem('mus-prompt'),sl=localStorage.getItem('mus-lyrics');
  if(sp)p.value=sp;if(sl)l.value=sl;
  p.addEventListener('input',function(){localStorage.setItem('mus-prompt',p.value)});
  l.addEventListener('input',function(){localStorage.setItem('mus-lyrics',l.value)});
})();
loadMusicGallery();

// Vision: image preview + drag-and-drop
(function(){
  const inp=document.getElementById('vis-file'),drop=document.getElementById('vis-drop'),prev=document.getElementById('vis-preview');
  function showPreview(file){
    const url=URL.createObjectURL(file);prev.src=url;prev.style.display='block';
    prev.onload=()=>URL.revokeObjectURL(url);
  }
  inp.addEventListener('change',()=>{if(inp.files[0])showPreview(inp.files[0])});
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.style.borderColor='var(--cyan)';drop.style.background='rgba(0,229,255,0.06)'});
  drop.addEventListener('dragleave',()=>{drop.style.borderColor='';drop.style.background=''});
  drop.addEventListener('drop',e=>{
    e.preventDefault();drop.style.borderColor='';drop.style.background='';
    const file=e.dataTransfer.files[0];
    if(file&&file.type.startsWith('image/')){
      const dt=new DataTransfer();dt.items.add(file);inp.files=dt.files;
      showPreview(file);
    }
  });
})();

// Dim tabs for services that aren't loaded, auto-select first available
fetch(base+'/health').then(r=>r.json()).then(d=>{
  const active=Object.keys(d.services||{});
  const tabs=document.querySelectorAll('.tab[data-svc]');
  let firstAvail=null;
  tabs.forEach(tab=>{
    if(!active.includes(tab.dataset.svc)){
      tab.classList.add('disabled');
      tab.classList.remove('active');
    }else if(!firstAvail){firstAvail=tab}
  });
  const cur=document.querySelector('.tab.active');
  if(!cur||cur.classList.contains('disabled')){
    if(firstAvail){
      const map={llm:'chat',stt:'stt',tts:'tts',vision:'vis',imagegen:'img',musicgen:'mus'};
      switchTab(map[firstAvail.dataset.svc]||'chat');
    }
  }
}).catch(()=>{});
