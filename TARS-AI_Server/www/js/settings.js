// Load settings from API
async function loadSettings(){
  try{
    const r=await fetch('/api/settings');const d=await r.json();
    document.getElementById('s-apikey').value=d.server.api_key||'';
    document.getElementById('s-port').value=d.server.port||'5678';
    document.getElementById('svc-stt').checked=d.services.stt==='true';
    document.getElementById('svc-tts').checked=d.services.tts==='true';
    document.getElementById('svc-llm').checked=d.services.llm==='true';
    document.getElementById('svc-vision').checked=d.services.vision==='true';
    document.getElementById('svc-imagegen').checked=d.services.imagegen==='true';
    document.getElementById('svc-musicgen').checked=d.services.musicgen==='true';
    document.getElementById('svc-embeddings').checked=d.services.embeddings==='true';
    setSelect('dev-stt',d.stt.device||'auto');
    setSelect('dev-llm',d.llm.device||'auto');
    setSelect('dev-vision',d.vision.device||'auto');
    setSelect('dev-imagegen',d.imagegen.device||'auto');
    setSelect('dev-musicgen',d.musicgen.device||'auto');
    setSelect('dev-embeddings',d.embeddings.device||'auto');
    setSelect('s-stt-model',d.stt.whisper_model);
    setSelect('s-stt-compute',d.stt.compute_type);
    document.getElementById('s-stt-vad').checked=d.stt.vad_filter==='true';
    setSelect('s-llm-backend',d.llm.backend||'transformers');
    toggleLlmBackend();
    document.getElementById('s-llm-model').value=d.llm.model;
    setSelect('s-llm-dtype',d.llm.dtype);
    setSelect('s-llm-quantize',d.llm.quantize||'none');
    document.getElementById('s-llm-nctx').value=d.llm.n_ctx||4096;
    document.getElementById('s-llm-ngpu').value=d.llm.n_gpu_layers||-1;
    document.getElementById('s-llm-kvs').value=d.llm.kv_cache_sessions;
    document.getElementById('s-llm-kvt').value=d.llm.kv_cache_ttl;
    window._ttsVoicesDir=d.tts.voices_dir||'';
    document.getElementById('s-tts-cache').value=d.tts.cache_size;
    try{const vr=await fetch('/tts/voices');const vd=await vr.json();const sel=document.getElementById('s-tts-voice');sel.innerHTML='';(vd.voices||[]).forEach(v=>{const o=document.createElement('option');o.value=v;o.text=v;sel.add(o)});if(d.tts.default_voice)setSelect('s-tts-voice',d.tts.default_voice)}catch(e){document.getElementById('s-tts-voice').innerHTML='<option value="">TTS not loaded</option>'}
    document.getElementById('s-vision-model').value=d.vision.model;
    document.getElementById('s-imagegen-model').value=d.imagegen.model;
    document.getElementById('s-imagegen-steps').value=d.imagegen.default_steps;
    document.getElementById('s-imagegen-cfg').value=d.imagegen.default_cfg;
    document.getElementById('s-musicgen-model').value=d.musicgen.model;
    document.getElementById('s-musicgen-duration').value=d.musicgen.default_duration;
    document.getElementById('s-musicgen-steps').value=d.musicgen.default_steps;
    document.getElementById('s-musicgen-cfg').value=d.musicgen.default_cfg;
    document.getElementById('s-embeddings-model').value=d.embeddings.model;
    // Disable cuda options if no GPU
    if(!d._meta.has_cuda){
      document.querySelectorAll('select[id^="dev-"]').forEach(s=>{
        for(const o of s.options){if(o.value==='cuda')o.disabled=true}
      });
    }
  }catch(e){console.error('Failed to load settings',e)}
}
function setSelect(id,val){const s=document.getElementById(id);for(let i=0;i<s.options.length;i++){if(s.options[i].value===val){s.selectedIndex=i;return}}}
function toggleLlmBackend(){
  const isLlamaCpp=document.getElementById('s-llm-backend').value==='llamacpp';
  document.getElementById('llm-transformers-opts').style.display=isLlamaCpp?'none':'';
  document.getElementById('llm-llamacpp-opts').style.display=isLlamaCpp?'':'none';
  document.getElementById('s-llm-model-lbl').textContent=isLlamaCpp?'GGUF Path':'Model';
}

async function saveSettings(){
  const st=document.getElementById('save-status');
  const btn=document.querySelector('.save-bar .hud-btn');
  st.textContent='Saving & applying...';st.className='save-status';
  if(btn)btn.disabled=true;
  const body={
    server:{port:document.getElementById('s-port').value,api_key:document.getElementById('s-apikey').value},
    services:{stt:document.getElementById('svc-stt').checked?'true':'false',tts:document.getElementById('svc-tts').checked?'true':'false',llm:document.getElementById('svc-llm').checked?'true':'false',vision:document.getElementById('svc-vision').checked?'true':'false',imagegen:document.getElementById('svc-imagegen').checked?'true':'false',musicgen:document.getElementById('svc-musicgen').checked?'true':'false',embeddings:document.getElementById('svc-embeddings').checked?'true':'false'},
    stt:{whisper_model:document.getElementById('s-stt-model').value,compute_type:document.getElementById('s-stt-compute').value,vad_filter:document.getElementById('s-stt-vad').checked?'true':'false',device:document.getElementById('dev-stt').value},
    llm:{model:document.getElementById('s-llm-model').value,backend:document.getElementById('s-llm-backend').value,dtype:document.getElementById('s-llm-dtype').value,quantize:document.getElementById('s-llm-quantize').value,n_ctx:document.getElementById('s-llm-nctx').value,n_gpu_layers:document.getElementById('s-llm-ngpu').value,kv_cache_sessions:document.getElementById('s-llm-kvs').value,kv_cache_ttl:document.getElementById('s-llm-kvt').value,device:document.getElementById('dev-llm').value},
    tts:{default_voice:document.getElementById('s-tts-voice').value,voices_dir:window._ttsVoicesDir||'',cache_size:document.getElementById('s-tts-cache').value},
    vision:{model:document.getElementById('s-vision-model').value,device:document.getElementById('dev-vision').value},
    imagegen:{model:document.getElementById('s-imagegen-model').value,default_steps:document.getElementById('s-imagegen-steps').value,default_cfg:document.getElementById('s-imagegen-cfg').value,device:document.getElementById('dev-imagegen').value},
    musicgen:{model:document.getElementById('s-musicgen-model').value,default_duration:document.getElementById('s-musicgen-duration').value,default_steps:document.getElementById('s-musicgen-steps').value,default_cfg:document.getElementById('s-musicgen-cfg').value,device:document.getElementById('dev-musicgen').value},
    embeddings:{model:document.getElementById('s-embeddings-model').value,device:document.getElementById('dev-embeddings').value}
  };
  try{
    const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    // Show detailed result with color coding
    const hasErrors=d.errors&&d.errors.length>0;
    const hasUnloaded=d.unloaded&&d.unloaded.length>0;
    const hasLoaded=d.loaded&&d.loaded.length>0;
    let msg=d.message||'Saved!';
    // Show GPU info if services were unloaded
    if(hasUnloaded&&d.gpu&&d.gpu.vram_free_gb!==undefined){
      msg+=` VRAM free: ${d.gpu.vram_free_gb} GB`;
    }
    st.textContent=msg;
    st.className=hasErrors?'save-status err':'save-status ok';
    // Auto-clear after a few seconds
    setTimeout(()=>{st.textContent='';st.className='save-status'},8000);
  }catch(e){
    st.textContent='Error: '+e;st.className='save-status err';
  }finally{
    if(btn)btn.disabled=false;
  }
}

loadSettings();
