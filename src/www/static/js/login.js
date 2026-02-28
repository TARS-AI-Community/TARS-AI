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

// ─── generate points along the panel's rounded-rect outline ─────────────────
function buildPanelOutline(count){
  const panel = document.querySelector('.panel');
  const rect  = panel.getBoundingClientRect();
  const r     = 14; // border-radius from CSS

  const x0 = rect.left, y0 = rect.top;
  const w  = rect.width, h = rect.height;

  // perimeter segments: straights + quarter-circle arcs
  const straightH = w - 2*r;
  const straightV = h - 2*r;
  const cornerArc = Math.PI * r / 2;
  const perimeter = 2*straightH + 2*straightV + 4*cornerArc;

  // define 8 segments around the rounded rect (clockwise from top-left corner)
  const segs = [
    { type:'line', x1:x0+r,   y1:y0,     x2:x0+w-r, y2:y0,     len:straightH },  // top
    { type:'arc',  cx:x0+w-r, cy:y0+r,    sa:-Math.PI/2,         len:cornerArc },  // top-right
    { type:'line', x1:x0+w,   y1:y0+r,    x2:x0+w,   y2:y0+h-r, len:straightV },  // right
    { type:'arc',  cx:x0+w-r, cy:y0+h-r,  sa:0,                  len:cornerArc },  // bottom-right
    { type:'line', x1:x0+w-r, y1:y0+h,    x2:x0+r,   y2:y0+h,   len:straightH },  // bottom
    { type:'arc',  cx:x0+r,   cy:y0+h-r,  sa:Math.PI/2,          len:cornerArc },  // bottom-left
    { type:'line', x1:x0,     y1:y0+h-r,  x2:x0,     y2:y0+r,   len:straightV },  // left
    { type:'arc',  cx:x0+r,   cy:y0+r,    sa:Math.PI,            len:cornerArc },  // top-left
  ];

  const pts = [];
  for(let i=0; i<count; i++){
    const d = (i / count) * perimeter;
    let x = x0, y = y0; // fallback
    let acc = 0;

    for(const s of segs){
      if(d < acc + s.len){
        const local = d - acc;
        if(s.type === 'line'){
          const t = local / s.len;
          x = s.x1 + (s.x2 - s.x1) * t;
          y = s.y1 + (s.y2 - s.y1) * t;
        } else {
          const angle = s.sa + local / r;
          x = s.cx + r * Math.cos(angle);
          y = s.cy + r * Math.sin(angle);
        }
        break;
      }
      acc += s.len;
    }

    // colour: cyan → purple gradient along the perimeter
    const t = i / count;
    const cr = Math.round(0 + t * 180);
    const cg = Math.round(229 - t * 152);
    pts.push({ x, y, r:cr, g:cg, b:255, a:0.85 });
  }

  // shuffle so particles arrive from mixed positions
  for(let i=pts.length-1; i>0; i--){
    const j = Math.floor(Math.random()*(i+1));
    [pts[i],pts[j]] = [pts[j],pts[i]];
  }
  return pts;
}

// ─── sample T.A.R.S. text ──────────────────────────────────────────────────
function sampleTARS(step, maxPts){
  const off = document.createElement('canvas');
  off.width=W; off.height=H;
  const c   = off.getContext('2d');

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
  constructor(textTarget, outlineTarget){
    this.tt = textTarget;   // where it forms TARS text
    this.ot = outlineTarget; // its place on the panel outline

    // spawn from edge
    const e=Math.floor(rand(0,4));
    if(e===0){this.x=rand(0,W);        this.y=rand(-150,-5);}
    else if(e===1){this.x=rand(W+5,W+150);this.y=rand(0,H);}
    else if(e===2){this.x=rand(0,W);        this.y=rand(H+5,H+150);}
    else{this.x=rand(-150,-5);        this.y=rand(0,H);}

    this.cx=this.x; this.cy=this.y;
    this.phase='forming'; // forming|holding|morphing|outline|resolve

    // colour from outline target
    this.r = outlineTarget.r; this.g = outlineTarget.g; this.b = outlineTarget.b;
    this.targetA = outlineTarget.a;

    this.size = rand(1.0, 2.0);
    this.alpha = 0;

    // stagger morphing for ripple effect
    this.morphOffset = rand(0, .42);
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
      this.cx = this.fromX + (this.ot.x - this.fromX)*ease;
      this.cy = this.fromY + (this.ot.y - this.fromY)*ease;
      this.alpha = 1;

    }else if(p==='outline'){
      // hold position on the outline with subtle shimmer
      const now=Date.now()*.001;
      this.cx = this.ot.x + Math.sin(now*2+this.ot.x*.05)*.3;
      this.cy = this.ot.y + Math.cos(now*2+this.ot.y*.05)*.3;
      this.alpha = clamp(this.alpha, 0.7, 1);

    }else if(p==='resolve'){
      this.alpha -= rand(.008,.018);
      if(this.alpha<0){ this.alpha=0; this.phase='dead'; }
    }
  }

  draw(){
    if(this.alpha<=0||this.phase==='dead') return;
    const p=this.phase;

    let col;
    if(p==='morphing'||p==='outline'||p==='resolve'){
      col=`rgba(${this.r},${this.g},${this.b},${this.alpha})`;
    } else {
      // cyan→purple blend during forming/holding
      const mix = clamp(this.cx / (W||1), 0, 1);
      const r = Math.round(0 + mix * 180);
      const g = Math.round(229 - mix * 152);
      col=`rgba(${r},${g},255,${this.alpha*.9})`;
    }
    ctx.beginPath();
    ctx.arc(this.cx,this.cy,this.size,0,Math.PI*2);
    ctx.fillStyle=col;
    ctx.fill();

    // soft glow during holding & outline phases
    if(p==='holding'||p==='outline'){
      const mix = clamp(this.cx / (W||1), 0, 1);
      const gr = Math.round(0 + mix * 180);
      const gg = Math.round(229 - mix * 152);
      const g=ctx.createRadialGradient(this.cx,this.cy,0,this.cx,this.cy,this.size*4);
      g.addColorStop(0,`rgba(${gr},${gg},255,${this.alpha*.15})`);
      g.addColorStop(1,'transparent');
      ctx.beginPath();
      ctx.arc(this.cx,this.cy,this.size*4,0,Math.PI*2);
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
    const amix = clamp(this.x / (W||1), 0, 1);
    const ar = Math.round(0 + amix * 140);
    const ag = Math.round(180 - amix * 100);
    ctx.fillStyle=`rgba(${ar},${ag},230,${this.a*this.life})`;
    ctx.fill();
  }
}

// ─── engine state ────────────────────────────────────────────────────────────
let particles=[], ambient=[], phase='boot', phaseStart=0;

function boot(){
  const maxParticles = Math.min(2400, Math.floor(W*H/200));
  const outlinePts   = buildPanelOutline(maxParticles);
  const count        = outlinePts.length;
  const tarsPts      = sampleTARS(4, count);

  // pad tars pts if outline has more points
  while(tarsPts.length < count)
    tarsPts.push({...tarsPts[Math.floor(rand(0,tarsPts.length))]});

  particles = outlinePts.map((op,i) => new Particle(tarsPts[i], op));
  ambient   = Array.from({length:55}, () => new Ambient());

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
function toOutline(now){
  phase='outline'; phaseStart=now;
  particles.forEach(p=>{p.phase='outline';});
}
function toResolve(now){
  phase='resolve'; phaseStart=now;
  showForm(); // HTML fades in while outline still visible
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
    if(elapsed>1250) toOutline(now);

  }else if(phase==='outline'){
    // particles hold the outline shape briefly
    particles.forEach(p=>{p.update(1);p.draw();});
    if(elapsed>600) toResolve(now);

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
  document.fonts.ready.then(()=>{ boot(); requestAnimationFrame(tick); });
}

})();
