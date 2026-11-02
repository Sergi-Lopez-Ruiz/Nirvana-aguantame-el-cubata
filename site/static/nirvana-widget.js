(()=>{
  'use strict';
  const NS='http://www.w3.org/2000/svg';
  const widget=document.getElementById('nirvana-widget');
  if (!widget) return;
  const translations={
    es:{node:'Nodo',action:'pulsar o arrastrar',interactions:'interacciones',nodes:'nodos'},
    en:{node:'Node',action:'click or drag',interactions:'interactions',nodes:'nodes'},
    de:{node:'Knoten',action:'anklicken oder ziehen',interactions:'Interaktionen',nodes:'Knoten'}
  };
  const labels=translations[widget.dataset.lang]||translations.es;
  const svg=widget.querySelector('#nirvana-system');
  const layer=widget.querySelector('#nirvana-nodes');
  const edgeLayer=widget.querySelector('#nirvana-edges');
  const status=widget.querySelector('#n-status');
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const init=[
    [188,160,'#4ac800'],[312,160,'#ff7907'],[131,256,'#ffd419'],
    [250,256,'#106af3'],[370,256,'#ff2528'],[188,343,'#fa299c'],[312,343,'#a96213']
  ];
  const additions=[
    {at:45,x:249,y:129,link:0,link2:1,type:'sparkle'},
    {at:65,x:109,y:194,link:2,link2:0,type:'leaf'},
    {at:85,x:389,y:194,link:4,link2:1,type:'star'},
    {at:100,x:251,y:358,link:5,link2:6,type:'sun'}
  ];
  const palette=['#4ac800','#ff7907','#ffd419','#106af3','#ff2528','#fa299c','#a96213','#9160de','#11b5ab'];
  const transformed=['heart','star','sun','flower','moon','diamond','sparkle'];
  const order=[5,0,4,3,1,6,2];
  const pinks=['#ff83bd','#ff77a7','#f7ae4a','#f58ebd','#f47ba9','#d886c7','#ff80b8'];
  const golds=['#ffd35e','#ffe48e','#ffbd40','#f8cd6c','#ffe39b','#ffc84a','#ffd878','#f7d77e','#ffdf88','#efbd50','#ffe8a6'];
  const mk=(tag,attrs={})=>{const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e};
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const star=(points,outer,inner,rotate=-Math.PI/2)=>{
    const out=[];
    for(let k=0;k<points*2;k++){
      const a=rotate+k*Math.PI/points,r=k%2?inner:outer;
      out.push(`${k?'L':'M'}${(Math.cos(a)*r).toFixed(1)} ${(Math.sin(a)*r).toFixed(1)}`);
    }
    return out.join(' ')+' Z';
  };
  const flower=()=>{
    let d='';
    for(let k=0;k<=72;k++){
      const a=k/72*2*Math.PI,r=24+9*Math.cos(6*a);
      d+=`${k?'L':'M'} ${(r*Math.cos(a)).toFixed(1)} ${(r*Math.sin(a)).toFixed(1)} `;
    }
    return d+'Z';
  };
  const paths={
    circle:'M28 0 A28 28 0 1 0 -28 0 A28 28 0 1 0 28 0 Z',
    rounded:'M-17 -28 H17 Q28 -28 28 -17 V17 Q28 28 17 28 H-17 Q-28 28 -28 17 V-17 Q-28 -28 -17 -28 Z',
    hexagon:'M-25 -17 L0 -32 L25 -17 L25 17 L0 32 L-25 17 Z',
    diamond:'M0 -32 L30 0 L0 32 L-30 0 Z',
    heart:'M0 31 C-5 26 -31 9 -31 -10 C-31 -29 -8 -34 0 -17 C8 -34 31 -29 31 -10 C31 9 5 26 0 31 Z',
    star:star(5,33,15),sun:star(12,32,23),sparkle:star(4,33,12),flower:flower(),
    moon:'M12 -29 A31 31 0 1 0 12 29 C-15 23 -15 -23 12 -29 Z',
    leaf:'M0 -33 C33 -26 40 13 0 33 C-33 14 -25 -24 0 -33 Z'
  };
  const initialTypes=['circle','rounded','hexagon','diamond','flower'];
  const base=[[0,1],[0,2],[0,5],[1,4],[1,6],[5,6]];
  let count=0,transformedCount=0,additionCount=0;
  const nodes=[],links=[];
  const target=(n,x,y)=>{n.tx=clamp(x,94,408);n.ty=clamp(y,108,394)};
  function createNode(x,y,color,type,extra=false){
    const i=nodes.length;
    const g=mk('g',{class:'n-node',tabindex:0,role:'button','aria-label':`${labels.node} ${i+1}: ${labels.action}`});
    const glow=mk('circle',{class:'n-glow',r:35});
    const p=mk('path',{class:'n-shape',d:paths[type],fill:color});
    const hit=mk('circle',{r:38,fill:'transparent','pointer-events':'all'});
    g.append(glow,p,hit);layer.append(g);
    const n={i,g,p,glow,x,y,tx:x,ty:y,vx:0,vy:0,type,c:color,angle:0,locked:extra,drag:null};
    nodes.push(n);installHandlers(n);
    if(extra&&!reduced&&g.animate)g.animate([{opacity:0,transform:`translate(${x}px,${y}px) scale(.1)`},{opacity:1}],{duration:450,easing:'ease-out'});
    return n;
  }
  function link(a,b){const e=mk('line',{class:'n-edge'});edgeLayer.append(e);links.push({a,b,e})}
  init.forEach(d=>createNode(...d,'circle'));
  base.forEach(([a,b])=>link(a,b));
  const changeTo=(n,type,color)=>{n.type=type;n.c=color;n.angle=0;n.locked=true;n.p.setAttribute('d',paths[type]);n.p.setAttribute('fill',color);};
  function updatePhases(){
    while(transformedCount<7&&count>=30+10*transformedCount){
      const n=nodes[order[transformedCount]];
      changeTo(n,transformed[transformedCount],pinks[transformedCount]);
      transformedCount++;
    }
    while(additionCount<additions.length&&count>=additions[additionCount].at){
      const d=additions[additionCount];
      const n=createNode(d.x,d.y,palette[(additionCount+3)%palette.length],d.type,true);
      link(n.i,d.link);link(n.i,d.link2);
      additionCount++;
    }
    widget.classList.toggle('n-pink',count>=90&&count<120);
    widget.classList.toggle('n-gold',count>=120);
    if(count>=120){
      nodes.forEach((n,i)=>{n.c=golds[i%golds.length];n.p.setAttribute('fill',n.c);n.p.setAttribute('d',paths[n.type]);});
    }
    status.textContent=`${count} ${labels.interactions}. ${nodes.length} ${labels.nodes}.`;
  }
  function interact(n,dragged=false){
    count++;
    if(!n.locked){
      const opts=initialTypes.filter(s=>s!==n.type);
      n.type=opts[Math.floor(Math.random()*opts.length)];
      const c=palette.filter(c=>c!==n.c);n.c=c[Math.floor(Math.random()*c.length)];
      n.p.setAttribute('d',paths[n.type]);n.p.setAttribute('fill',n.c);n.angle+=(Math.random()-.5)*34;
    }
    if(!dragged)target(n,n.tx+(Math.random()-.5)*20,n.ty+(Math.random()-.5)*20);
    for(const other of nodes)if(other!==n&&!other.drag)target(other,other.tx+(Math.random()-.5)*14,other.ty+(Math.random()-.5)*14);
    if(!reduced&&n.glow.animate)n.glow.animate([{opacity:.55},{opacity:0}],{duration:350,easing:'ease-out'});
    updatePhases();
  }
  function coord(e){const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const m=svg.getScreenCTM();return m?p.matrixTransform(m.inverse()):{x:0,y:0}}
  function installHandlers(n){
    n.g.addEventListener('pointerdown',e=>{
      if(e.pointerType==='mouse'&&e.button!==0)return;
      e.preventDefault();const p=coord(e);
      n.drag={id:e.pointerId,px:p.x,py:p.y,nx:n.x,ny:n.y,moved:false};
      n.g.setPointerCapture(e.pointerId);
    });
    n.g.addEventListener('pointermove',e=>{
      const d=n.drag;if(!d||d.id!==e.pointerId)return;
      const p=coord(e),dx=p.x-d.px,dy=p.y-d.py;
      if(Math.hypot(dx,dy)>5)d.moved=true;
      if(d.moved){
        n.x=clamp(d.nx+dx,95,406);n.y=clamp(d.ny+dy,107,393);
        n.tx=n.x;n.ty=n.y;n.vx=n.vy=0;
        for(const other of nodes)if(other!==n&&!other.drag){
          const distance=Math.hypot(n.x-other.x,n.y-other.y);
          const strength=clamp((200-distance)/200,0,.6)*.08;
          target(other,other.tx+dx*strength*.1,other.ty+dy*strength*.1);
        }
      }
    });
    const end=e=>{
      if(!n.drag||n.drag.id!==e.pointerId)return;
      const moved=n.drag.moved;n.drag=null;
      if(n.g.hasPointerCapture(e.pointerId))n.g.releasePointerCapture(e.pointerId);
      if(e.type==='pointerup')interact(n,moved);
    };
    n.g.addEventListener('pointerup',end);n.g.addEventListener('pointercancel',end);
    n.g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();interact(n)}});
  }
  function reset(){
    count=0;transformedCount=0;additionCount=0;
    while(nodes.length>init.length){const n=nodes.pop();n.g.remove()}
    while(links.length>base.length)links.pop().e.remove();
    nodes.forEach((n,i)=>{
      const [x,y,c]=init[i];n.type='circle';n.c=c;n.angle=0;n.locked=false;n.drag=null;
      n.p.setAttribute('d',paths.circle);n.p.setAttribute('fill',c);target(n,x,y);n.vx=n.vy=0;
    });
    updatePhases();
  }
  widget.querySelector('#n-reset').addEventListener('click',reset);
  function frame(){
    if(!widget.isConnected)return;
    nodes.forEach(n=>{
      if(!n.drag){
        if(reduced){n.x=n.tx;n.y=n.ty}
        else{n.vx=(n.vx+(n.tx-n.x)*.045)*.82;n.vy=(n.vy+(n.ty-n.y)*.045)*.82;n.x+=n.vx;n.y+=n.vy}
      }
      n.g.setAttribute('transform',`translate(${n.x.toFixed(2)} ${n.y.toFixed(2)}) rotate(${n.angle.toFixed(1)})`);
    });
    links.forEach(({a,b,e})=>{
      e.setAttribute('x1',nodes[a].x);e.setAttribute('y1',nodes[a].y);
      e.setAttribute('x2',nodes[b].x);e.setAttribute('y2',nodes[b].y);
    });
    requestAnimationFrame(frame);
  }
  updatePhases();frame();
})();
