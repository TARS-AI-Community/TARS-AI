function fmtUptime(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60),ss=s%60;return h+'h '+m+'m '+ss+'s'}
function connect(){
  const dot=document.getElementById('connDot');
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/dashboard');
  ws.onopen=function(){dot.className='live-dot'};
  ws.onmessage=function(e){
    const d=JSON.parse(e.data);
    document.getElementById('uptime').textContent=fmtUptime(d.uptime);
    const ss=document.getElementById('stats-section');let bars='';
    function mkBar(title,pct,label,extra){const c=pct<70?'var(--cyan)':pct<90?'var(--orange)':'var(--red)';const g='linear-gradient(90deg,'+c+',rgba(180,77,255,0.5))';return '<div class="glass" style="margin:0;'+(extra||'')+'"><h2>'+title+'</h2><div class="bar-bg"><div class="bar-fg" style="background:'+g+';width:'+Math.min(pct,100)+'%"></div><span class="bar-label">'+label+'</span></div></div>';}
    if(d.system&&d.system.cpu_percent!==undefined){bars+=mkBar('CPU',d.system.cpu_percent,d.system.cpu_percent+'%');}
    if(d.system&&d.system.ram_percent!==undefined){bars+=mkBar('RAM',d.system.ram_percent,d.system.ram_used_gb.toFixed(1)+' / '+d.system.ram_total_gb.toFixed(1)+' GB ('+d.system.ram_percent+'%)');}
    if(d.gpu&&d.gpu.vram_percent!==undefined){bars+=mkBar('Dedicated GPU',d.gpu.vram_percent,d.gpu.vram_allocated_gb.toFixed(1)+' / '+d.gpu.vram_total_gb.toFixed(1)+' GB ('+d.gpu.vram_percent+'%)');}
    if(d.gpu&&d.gpu.shared_percent!==undefined){bars+=mkBar('Shared GPU',d.gpu.shared_percent,d.gpu.shared_used_gb.toFixed(1)+' / '+d.gpu.shared_total_gb.toFixed(1)+' GB ('+d.gpu.shared_percent+'%)');}
    ss.innerHTML=bars;
    const tb=document.getElementById('svc-table');let rows='';
    const vramTotal=d.gpu&&d.gpu.vram_total_gb?d.gpu.vram_total_gb:12;
    for(const[n,s]of Object.entries(d.services)){
      const lat=d.latency[n]?d.latency[n].avg_latency_ms.toFixed(0)+'ms <span style="color:var(--text-dim)">('+d.latency[n].requests+')</span>':'<span style="color:var(--text-dim)">-</span>';
      const det=s.model||(n==='tts'?'Piper':'ready');
      let status;
      if(s.vram_gb!==undefined&&s.vram_gb>0){
        const pct=Math.min(100,s.vram_gb/vramTotal*100);
        const c=pct<30?'var(--cyan)':pct<60?'var(--orange)':'var(--red)';
        status='<div style="display:flex;align-items:center;gap:8px"><span class="status-ready" style="flex-shrink:0"></span>'
          +'<div style="flex:1;min-width:80px;height:18px;background:rgba(0,229,255,0.06);border:1px solid var(--border);border-radius:4px;position:relative;overflow:hidden">'
          +'<div style="height:100%;width:'+pct.toFixed(0)+'%;background:linear-gradient(90deg,'+c+',rgba(180,77,255,0.4));border-radius:3px"></div>'
          +'<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:var(--font-hud);font-size:9px;letter-spacing:.05em;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,0.7)">'+s.vram_gb.toFixed(1)+' GB</span>'
          +'</div></div>';
      }else{
        status='<span class="status-ready">Online</span>';
      }
      rows+='<tr><td class="svc-name">'+n.toUpperCase()+'</td><td>'+status+'</td><td style="color:var(--text-dim)">'+det+'</td><td>'+lat+'</td></tr>';
    }
    tb.innerHTML=rows||'<tr><td colspan="4" style="color:var(--text-dim)">No services loaded</td></tr>';
    const la=document.getElementById('log-area');
    if(d.recent_logs&&d.recent_logs.length){
      la.innerHTML=d.recent_logs.map(l=>{
        const sc=l.status<400?'s2':l.status<500?'s4':'s5';
        let llm='';
        if(l.llm){const m=l.llm;const ttft=m.ttft_ms>0?(m.ttft_ms<1000?m.ttft_ms+'ms':((m.ttft_ms/1000).toFixed(1))+'s'):'--';llm='<span class="le-llm">'+m.tokens_per_sec+' t/s | '+m.completion_tokens+' tok | '+ttft+' ttft</span>';}
        return '<div class="log-entry"><span class="le-time">'+l.time+'</span><span class="le-method">'+l.method+'</span><span class="le-path">'+l.endpoint+'</span>'+llm+'<span class="le-status '+sc+'">'+l.status+'</span><span class="le-ms">'+l.latency_ms+'ms</span></div>';
      }).join('');
      la.scrollTop=la.scrollHeight;
    }
  };
  ws.onclose=function(){dot.className='live-dot off';setTimeout(connect,3000)};
  ws.onerror=function(){ws.close()};
}
connect();

// Tunnel controls
let tunnelActive=false;
function checkTunnel(){
  fetch('/api/tunnel/status').then(r=>r.json()).then(d=>{
    const st=document.getElementById('tunnel-status');
    const btn=document.getElementById('tunnel-btn');
    const urlDiv=document.getElementById('tunnel-url');
    if(d.state==='active'){
      tunnelActive=true;
      st.innerHTML='<span style="color:var(--green)">Active</span>';
      btn.textContent='Close Tunnel';btn.className='hud-btn-sm danger';
      document.getElementById('tunnel-link').href=d.url;
      document.getElementById('tunnel-link').textContent=d.url;
      const qr=document.getElementById('tunnel-qr');
      qr.src='/api/tunnel/qr?url='+encodeURIComponent(d.url);qr.style.display='block';
      urlDiv.style.display='block';
    }else if(d.state==='starting'){
      st.innerHTML='<span style="color:var(--orange)">Starting...</span>';
      btn.disabled=true;setTimeout(checkTunnel,2000);
    }else if(d.state==='error'){
      tunnelActive=false;
      st.innerHTML='<span style="color:var(--red)">Error: '+d.error+'</span>';
      btn.textContent='Retry';btn.className='hud-btn-sm';btn.disabled=false;
      urlDiv.style.display='none';
    }else{
      tunnelActive=false;
      st.textContent=d.installed?'Inactive':'cloudflared not installed (will auto-install)';
      btn.textContent='Open Tunnel';btn.className='hud-btn-sm';btn.disabled=false;
      urlDiv.style.display='none';
    }
  }).catch(()=>{});
}
function toggleTunnel(){
  const btn=document.getElementById('tunnel-btn');btn.disabled=true;
  if(tunnelActive){
    fetch('/api/tunnel/stop',{method:'POST'}).then(()=>{checkTunnel()});
  }else{
    document.getElementById('tunnel-status').innerHTML='<span style="color:var(--orange)">Starting...</span>';
    fetch('/api/tunnel/start',{method:'POST'}).then(()=>{setTimeout(checkTunnel,3000)});
  }
}
function copyTunnelUrl(){
  const url=document.getElementById('tunnel-link').textContent;
  navigator.clipboard.writeText(url).then(()=>{
    const btn=event.target;btn.textContent='Copied!';setTimeout(()=>{btn.textContent='Copy'},1500);
  });
}
checkTunnel();
