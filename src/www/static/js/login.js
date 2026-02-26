(function(){
'use strict';

// ─── canvas setup ───────────────────────────────────────────────────────────
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');
let W = 0, H = 0;

function setSize(){
  W = canvas.width  = window.innerWidth;
  H = canvas.height = window.innerHeight;
}
setSize();
window.addEventListener('resize', setSize);

// ─── easing ─────────────────────────────────────────────────────────────────
const easeOut  = t => 1 - Math.pow(1-t, 3);
const easeIn   = t => t * t;
const easeIO   = t => t<.5 ? 2*t*t : -1+(4-2*t)*t;
const rand     = (a,b) => Math.random()*(b-a)+a;
const clamp    = (v,lo,hi) => Math.min(hi,Math.max(lo,v));

// ─── render login UI to offscreen canvas → get pixel targets ────────────────
function buildUICanvas(){
  const off = document.createElement('canvas');
  off.width  = W;
  off.height = H;
  const c = off.getContext('2d');

  // Layout math — mirrors the CSS panel
  const pad    = W < 480 ? 18 : 28;
  const panelW = Math.min(420, W - 32);
  const panelH = W < 480 ? Math.min(H-32, 520) : Math.min(H-32, 500);
  const pX     = Math.floor((W - panelW) / 2);
  const pY     = Math.floor((H - panelH) / 2);
  const iX     = pX + pad;       // inner content left
  const iW     = panelW - pad*2; // inner content width
  const CYAN   = 'rgba(0,229,255,';
  const DIM    = 'rgba(0,229,255,0.28)';

  // helper: stroke rect outline only (1px)
  const strokeBox = (x,y,w,h,col,lw=1)=>{
    c.strokeStyle=col; c.lineWidth=lw;
    c.strokeRect(x+.5,y+.5,w,h);
  };

  // ── panel border ──
  strokeBox(pX, pY, panelW, panelH, DIM);

  // ── corner brackets ──
  const cSz=13, cW=2;
  c.strokeStyle=CYAN+'0.85)'; c.lineWidth=cW;
  const corners=[
    [pX,pY,[0,cSz,0,0,cSz,0]],
    [pX+panelW,pY,[-cSz,0,0,0,0,cSz]],
    [pX,pY+panelH,[cSz,0,0,0,0,-cSz]],
    [pX+panelW,pY+panelH,[-cSz,0,0,0,0,-cSz]],
  ];
  corners.forEach(([cx,cy,[dx1,dy1,dx2,dy2,dx3,dy3]])=>{
    c.beginPath();
    c.moveTo(cx+dx1,cy+dy1); c.lineTo(cx+dx2,cy+dy2); c.lineTo(cx+dx3,cy+dy3);
    c.stroke();
  });

  // current layout cursor
  let cursor = pY + (W<480 ? 22 : 30);

  // ── T.A.R.S. logo inside panel ──
  const logoFS = Math.min(panelW * 0.195, W<480 ? 38 : 58);
  c.fillStyle  = CYAN+'0.92)';
  c.font       = `900 ${logoFS}px "Orbitron", sans-serif`;
  c.textAlign  = 'center';
  c.textBaseline = 'alphabetic';
  const logoY = cursor + logoFS;
  c.fillText('T.A.R.S.', W/2, logoY);
  cursor = logoY + (W<480 ? 6 : 10);

  // ── subtitle ──
  const subFS = Math.max(8, panelW * 0.028);
  c.font       = `${subFS}px "Share Tech Mono", monospace`;
  c.fillStyle  = 'rgba(61,90,110,0.9)';
  c.fillText('Access Control Protocol · v4.1', W/2, cursor + subFS);
  cursor += subFS + (W<480 ? 10 : 14);

  // ── status row ──
  const sFS = Math.max(8, panelW * 0.026);
  c.font = `${sFS}px "Share Tech Mono", monospace`;
  c.fillStyle = CYAN+'0.5)';
  c.textAlign = 'center';
  c.fillText('● INITIALIZING', W/2, cursor + sFS);
  cursor += sFS + (W<480 ? 12 : 18);

  // ── divider ──
  c.strokeStyle = DIM; c.lineWidth = 1;
  c.beginPath();
  c.moveTo(iX+20, cursor); c.lineTo(iX+iW-20, cursor);
  c.stroke();
  c.fillStyle = CYAN+'0.4)';
  c.font = `${Math.max(10,panelW*0.032)}px monospace`;
  c.fillText('◈', W/2, cursor + 5);
  cursor += (W<480 ? 14 : 18);

  // ── label ──
  const lblFS = Math.max(8, panelW * 0.026);
  c.font = `${lblFS}px "Share Tech Mono", monospace`;
  c.fillStyle = CYAN+'0.5)';
  c.textAlign = 'left';
  c.fillText('// AUTHORIZATION KEY', iX, cursor + lblFS);
  cursor += lblFS + 7;

  // ── input box ──
  const inputH = W<480 ? 42 : 46;
  strokeBox(iX, cursor, iW, inputH, DIM);
  // icon + placeholder
  c.fillStyle = CYAN+'0.3)';
  c.font = `${Math.max(10,panelW*0.032)}px monospace`;
  c.textAlign = 'left';
  c.fillText('⬡', iX+11, cursor + inputH/2 + 5);
  c.fillStyle = 'rgba(61,90,110,0.7)';
  c.font = `${Math.max(10,panelW*0.032)}px "Share Tech Mono", monospace`;
  c.fillText('Enter security token', iX+32, cursor + inputH/2 + 5);
  cursor += inputH + (W<480 ? 10 : 14);

  // ── button ──
  const btnH = W<480 ? 44 : 48;
  strokeBox(iX, cursor, iW, btnH, CYAN+'0.9)');
  c.fillStyle = CYAN+'0.07)';
  c.fillRect(iX+1, cursor+1, iW-1, btnH-1);
  const btnFS = Math.max(10, panelW * 0.038);
  c.font = `700 ${btnFS}px "Orbitron", sans-serif`;
  c.fillStyle = CYAN+'0.88)';
  c.textAlign = 'center';
  c.fillText('INITIALIZE LINK  →', W/2, cursor + btnH/2 + btnFS*0.36);
  cursor += btnH + (W<480 ? 14 : 20);

  // ── footer divider ──
  c.strokeStyle = DIM; c.lineWidth=1;
  c.beginPath(); c.moveTo(iX, cursor); c.lineTo(iX+iW, cursor); c.stroke();
  cursor += 10;

  // ── footer text ──
  const ftFS = Math.max(7, panelW*0.024);
  c.font = `${ftFS}px "Share Tech Mono", monospace`;
  c.fillStyle = 'rgba(61,90,110,0.7)';
  c.textAlign = 'left';  c.fillText('TARS-AI', iX, cursor+ftFS);
  c.textAlign = 'right'; c.fillText(new Date().toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}), iX+iW, cursor+ftFS);

  return off;
}

// ─── sample bright pixels from canvas ──────────────────────────────────────
function samplePixels(offCanvas, step, maxPts){
  const c   = offCanvas.getContext('2d');
  const img = c.getImageData(0,0,W,H);
  const d   = img.data;
  const pts = [];
  for(let y=0; y<H; y+=step)
    for(let x=0; x<W; x+=step){
      const i=(y*W+x)*4;
      if(d[i+3]>40) // alpha threshold
        pts.push({
          x, y,
          r: d[i],
          g: d[i+1],
          b: d[i+2],
          a: d[i+3]/255,
        });
    }
  // shuffle
  for(let i=pts.length-1;i>0;i--){
    const j=Math.floor(Math.random()*(i+1));
    [pts[i],pts[j]]=[pts[j],pts[i]];
  }
  return pts.slice(0, maxPts);
}

// ─── sample T.A.R.S. text ──────────────────────────────────────────────────
function sampleTARS(step, maxPts){
  const off = document.createElement('canvas');
  off.width=W; off.height=H;
  const c   = off.getContext('2d');

  // fit font so it never clips — max 85% of usable width
  const maxW = W * 0.85;
  let fs = Math.min(W * 0.20, H * 0.22, 160);
  c.font = `900 ${fs}px "Orbitron", sans-serif`;
  let measured = c.measureText('T.A.R.S.').width;
  if(measured > maxW) fs *= (maxW / measured);

  c.fillStyle = '#fff';
  c.font = `900 ${fs}px "Orbitron", sans-serif`;
  c.textAlign    = 'center';
  c.textBaseline = 'middle';
  c.fillText('T.A.R.S.', W/2, H/2);

  const img=c.getImageData(0,0,W,H).data;
  const pts=[];
  for(let y=0;y<H;y+=step)
    for(let x=0;x<W;x+=step)
      if(img[(y*W+x)*4+3]>128)
        pts.push({x:x+rand(-step*.4,step*.4), y:y+rand(-step*.4,step*.4)});

  for(let i=pts.length-1;i>0;i--){
    const j=Math.floor(Math.random()*(i+1));
    [pts[i],pts[j]]=[pts[j],pts[i]];
  }
  return pts.slice(0,maxPts);
}

// ─── Particle ───────────────────────────────────────────────────────────────
class Particle {
  constructor(textTarget, uiTarget){
    this.tt = textTarget; // where it forms TARS text
    this.ut = uiTarget;   // its exact pixel home in the UI

    // spawn from edge
    const e=Math.floor(rand(0,4));
    if(e===0){this.x=rand(0,W);        this.y=rand(-150,-5);}
    else if(e===1){this.x=rand(W+5,W+150);this.y=rand(0,H);}
    else if(e===2){this.x=rand(0,W);        this.y=rand(H+5,H+150);}
    else{this.x=rand(-150,-5);        this.y=rand(0,H);}

    this.cx=this.x; this.cy=this.y;
    this.phase='forming'; // forming|holding|morphing|resolve

    // pixel colour from UI target
    this.r = uiTarget.r; this.g = uiTarget.g; this.b = uiTarget.b;
    this.targetA = uiTarget.a;

    this.size = rand(.9,2.2);
    this.alpha = 0;

    // stagger morphing so it ripples visually
    this.morphOffset = rand(0,.42);
    this.fromX = this.cx;
    this.fromY = this.cy;
  }

  update(t){
    const p=this.phase;
    if(p==='forming'){
      const spd = 0.05 + easeIO(t)*0.045;
      this.cx += (this.tt.x - this.cx)*spd;
      this.cy += (this.tt.y - this.cy)*spd;
      this.alpha = clamp(this.alpha+.038, 0, .95);

    }else if(p==='holding'){
      const now=Date.now()*.001;
      this.cx = this.tt.x + Math.sin(now+this.tt.x*.012)*.35;
      this.cy = this.tt.y + Math.cos(now+this.tt.y*.012)*.35;
      this.alpha = clamp(this.alpha+.05, 0, 1);

    }else if(p==='morphing'){
      const raw  = clamp((t-this.morphOffset)/(1-this.morphOffset),0,1);
      const ease = easeOut(raw);
      this.cx = this.fromX + (this.ut.x - this.fromX)*ease;
      this.cy = this.fromY + (this.ut.y - this.fromY)*ease;
      this.alpha = 1;
      this.size  = Math.max(.5, this.size - ease*.3);

    }else if(p==='resolve'){
      this.alpha -= rand(.016,.030);
      if(this.alpha<0){ this.alpha=0; this.phase='dead'; }
    }
  }

  draw(){
    if(this.alpha<=0||this.phase==='dead') return;
    const p=this.phase;
    // during morph → resolve use true pixel colour; during forming use cyan
    let col;
    if(p==='morphing'||p==='resolve'){
      col=`rgba(${this.r},${this.g},${this.b},${this.alpha})`;
    } else {
      col=`rgba(0,229,255,${this.alpha*.9})`;
    }
    ctx.beginPath();
    ctx.arc(this.cx,this.cy,this.size,0,Math.PI*2);
    ctx.fillStyle=col;
    ctx.fill();

    // soft glow when formed as TARS text
    if(p==='holding'){
      const g=ctx.createRadialGradient(this.cx,this.cy,0,this.cx,this.cy,this.size*4.5);
      g.addColorStop(0,`rgba(0,229,255,${this.alpha*.18})`);
      g.addColorStop(1,'transparent');
      ctx.beginPath();
      ctx.arc(this.cx,this.cy,this.size*4.5,0,Math.PI*2);
      ctx.fillStyle=g; ctx.fill();
    }
  }
}

// ─── ambient drift particles ─────────────────────────────────────────────────
class Ambient{
  constructor(){this.init();}
  init(){
    this.x=rand(0,W); this.y=rand(0,H);
    this.vx=rand(-.12,.12); this.vy=rand(-.25,-.03);
    this.r=rand(.3,1.1); this.a=rand(.05,.22); this.life=rand(.5,1);
  }
  tick(){
    this.x+=this.vx; this.y+=this.vy; this.life-=.0015;
    if(this.life<=0||this.y<-5) this.init();
    ctx.beginPath();
    ctx.arc(this.x,this.y,this.r,0,Math.PI*2);
    ctx.fillStyle=`rgba(0,180,210,${this.a*this.life})`;
    ctx.fill();
  }
}

// ─── engine state ────────────────────────────────────────────────────────────
let particles=[], ambient=[], phase='boot', phaseStart=0;

function boot(){
  // render the login UI to offscreen canvas
  const uiCanvas = buildUICanvas();
  // sample it — 1 particle per pixel cluster (step=2 → dense but not 1:1 for perf)
  const maxParticles = Math.min(2400, Math.floor(W*H/200));
  const uiPts   = samplePixels(uiCanvas, 2, maxParticles);
  const count   = uiPts.length;
  const tarsPts = sampleTARS(4, count);

  // pad tars pts if UI has more points
  while(tarsPts.length < count)
    tarsPts.push({...tarsPts[Math.floor(rand(0,tarsPts.length))]});

  particles = uiPts.map((up,i)=>new Particle(tarsPts[i], up));
  ambient   = Array.from({length:55},()=>new Ambient());

  phase='forming'; phaseStart=performance.now();
}

// ─── transitions ─────────────────────────────────────────────────────────────
function toHold(now){
  phase='holding'; phaseStart=now;
  particles.forEach(p=>{p.phase='holding';});
}
function toMorph(now){
  phase='morphing'; phaseStart=now;
  particles.forEach(p=>{p.phase='morphing'; p.fromX=p.cx; p.fromY=p.cy;});
}
function toResolve(now){
  phase='resolve'; phaseStart=now;
  showForm(); // HTML fades in NOW — while particles still visible
  particles.forEach(p=>p.phase='resolve');
}

// ─── render loop ─────────────────────────────────────────────────────────────
function tick(now){
  ctx.clearRect(0,0,W,H);
  ambient.forEach(a=>a.tick());

  if(phase==='boot'){requestAnimationFrame(tick);return;}

  const elapsed=now-phaseStart;

  if(phase==='forming'){
    const t=clamp(elapsed/2400,0,1);
    particles.forEach(p=>p.update(t));
    particles.forEach(p=>p.draw());
    if(elapsed>2200) toHold(now);

  }else if(phase==='holding'){
    particles.forEach(p=>{p.update(1);p.draw();});
    if(elapsed>750) toMorph(now);

  }else if(phase==='morphing'){
    const t=clamp(elapsed/1200,0,1);
    particles.forEach(p=>p.update(t));
    particles.forEach(p=>p.draw());
    if(elapsed>1250) toResolve(now);

  }else if(phase==='resolve'){
    particles.forEach(p=>{p.update(1);p.draw();});
    if(particles.every(p=>p.phase==='dead')){
      ctx.clearRect(0,0,W,H);
      canvas.style.display='none';
      return;
    }
  }
  requestAnimationFrame(tick);
}

// ─── show HTML form ──────────────────────────────────────────────────────────
function showForm(){
  const el=document.getElementById('login');
  el.classList.add('show');
  setTimeout(()=>{
    const pw=document.getElementById('pw');
    if(pw) pw.focus();
  },700);
}

// ─── clock ───────────────────────────────────────────────────────────────────
function tickClock(){
  const el=document.getElementById('clk');
  if(el) el.textContent=new Date().toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
setInterval(tickClock,1000); tickClock();

// ─── form submit feedback ─────────────────────────────────────────────────────
const form=document.getElementById('form');
if(form) form.addEventListener('submit',()=>{
  const b=document.getElementById('btntxt');
  const btn=document.getElementById('btn');
  const s=document.getElementById('stxt');
  if(b) b.textContent='AUTHENTICATING…';
  if(btn) btn.disabled=true;
  if(s) s.textContent='VERIFYING…';
});

// ─── boot ─────────────────────────────────────────────────────────────────────
if(window.matchMedia('(prefers-reduced-motion:reduce)').matches){
  showForm();
  canvas.style.display='none';
}else{
  // wait for Orbitron to load before sampling text
  document.fonts.ready.then(()=>{ boot(); requestAnimationFrame(tick); });
}

})();
