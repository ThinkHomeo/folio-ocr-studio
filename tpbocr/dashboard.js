const DATA = JSON.parse(document.getElementById('data').textContent);
const HEX = {5:'#c62828',4:'#d87800',3:'#1a7a3c',2:'#1e5ac8',1:'#7a3caa'};
const NAME = {5:'CAPITALS (5)',4:'Antique/bold (4)',3:'Italic (3)',2:'Roman (2)',1:'(parens) (1)'};
const RNAME = {5:'CAPITALS',4:'Antique',3:'Italic',2:'Roman',1:'paren'};
// the OCR "skills" (engines) the user can switch between — only the ones that
// actually differ: final(=MLP-primary), the hand-feature scalar, the independent
// shape engine, and "auto" = the final decision on just the un-flagged tokens.
const ENGINES = [['final','System / MLP (final)'],['scalar','Scalar (hand-features)'],
  ['shape','Shape (independent)'],['auto','Auto — बिना review']];
const COLS = ['book','page','rubric','remedy','rank','rank_name','scalar','mlp','shape',
  'confidence','flag','adjudicated','gold','correct','engine'];
let pi = 0, filter = 'all', engine = 'final';

function el(t, c, h){const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e;}

// rank the SELECTED engine assigns this token; a null engine value (caps/parens,
// which no measured engine scores) falls back to the final decision.
function eff(tk){
  if(engine==='mlp')    return tk.mlp    ?? tk.rank;
  if(engine==='scalar') return tk.scalar ?? tk.rank;
  if(engine==='shape')  return tk.shape  ?? tk.rank;
  return tk.rank;                       // final / auto / vision = final decision
}
function okOf(tk){ return tk.gold==null ? null : (eff(tk)===tk.gold); }
function engLabel(){ return (ENGINES.find(e=>e[0]===engine)||['',''])[1]; }
// the "auto" skill scores/ships only tokens the system did NOT flag for review
function inScope(tk){ return engine!=='auto' || !tk.flag; }


function tabs(){
  const t = document.getElementById('tabs'); t.innerHTML='';
  DATA.pages.forEach((p,i)=>{
    const b=el('div','tab'+(i===pi?' on':''), 'पेज '+p.book+' <span class="mut">('+p.tag+')</span>');
    b.onclick=()=>{pi=i; render();}; t.appendChild(b);
  });
}
function engineBar(){
  const e=document.getElementById('engine'); e.innerHTML='';
  e.appendChild(el('label',null,'OCR इंजन (skill):'));
  const sel=el('select');
  ENGINES.forEach(([k,l])=>{const o=document.createElement('option');
    o.value=k; o.textContent=l; if(k===engine)o.selected=true; sel.appendChild(o);});
  sel.onchange=()=>{engine=sel.value; render();};
  e.appendChild(sel);
  const p=DATA.pages[pi], g=p.tokens.filter(t=>t.gold!=null && inScope(t));
  const ok=g.filter(t=>okOf(t)).length;
  const acc=g.length?(100*ok/g.length).toFixed(1):'—';
  const extra=engine==='auto'?' · flagged टोकन review के लिए रोके':'';
  e.appendChild(el('span','engbadge','· इस पेज: '+acc+'% ('+ok+'/'+g.length+' gold सही)'+extra));
}
function filters(){
  const defs=[['all','सब'],['flag','review queue ⚑'],['err','सिर्फ़ गलतियाँ'],['ok','सिर्फ़ सही'],
    ['5','CAPS'],['4','Antique'],['3','Italic'],['2','Roman'],['low','कम-confidence']];
  const f=document.getElementById('filters'); f.innerHTML='';
  defs.forEach(([k,l])=>{const b=el('div','btn'+(filter===k?' on':''),l);
    b.onclick=()=>{filter=k; render();}; f.appendChild(b);});
}
function show(tk){
  if(filter==='all')return true;
  if(filter==='flag')return tk.flag===true;
  if(filter==='err')return okOf(tk)===false;
  if(filter==='ok')return okOf(tk)===true;
  if(filter==='low')return tk.conf<0.6;
  return String(eff(tk))===filter;
}
function boxes(){
  const p=DATA.pages[pi];
  document.getElementById('pageimg').src=p.image;
  const st=document.getElementById('stage');
  [...st.querySelectorAll('.box')].forEach(e=>e.remove());
  p.tokens.forEach((tk)=>{
    if(!show(tk))return;
    const r=eff(tk), bad=okOf(tk)===false;
    const [x0,y0,x1,y1]=tk.bbox;
    const b=el('div','box'+(bad?' wrong':''));
    b.style.left=(100*x0/p.w)+'%'; b.style.top=(100*y0/p.h)+'%';
    b.style.width=(100*(x1-x0)/p.w)+'%'; b.style.height=(100*(y1-y0)/p.h)+'%';
    b.style.borderColor=HEX[r];
    const tag=el('div','tag', r + (bad?('→'+tk.gold):'') + (tk.flag?' ⚑':''));
    tag.style.background=HEX[r]; b.appendChild(tag);
    if(tk.flag) b.style.outline='2px dotted #ffd43b';
    if(tk.adj) b.style.outline='2px solid #39d98a';
    if(!inScope(tk)) b.style.opacity='0.3';   // auto skill: flagged tokens withheld
    b.onmouseenter=()=>detail(tk); b.onclick=()=>detail(tk);
    st.appendChild(b);
  });
}
function detail(tk){
  const d=document.getElementById('detail');
  const pill=(r)=>'<span class="pill" style="background:'+HEX[r]+'">'+r+' '+RNAME[r]+'</span>';
  let v='<div class="big">'+tk.text+'</div><div class="mut">rubric: '+(tk.rubric||'—')+'</div>';
  if(engine!=='final')v+='<div class="row"><span>चयनित इंजन ('+engine+')</span>'+pill(eff(tk))+'</div>';
  v+='<div class="row"><span>System (final)</span>'+pill(tk.rank)+'</div>';
  if(tk.mlp)v+='<div class="row"><span>MLP इंजन</span>'+pill(tk.mlp)+'</div>';
  if(tk.scalar)v+='<div class="row"><span>scalar इंजन</span>'+pill(tk.scalar)+'</div>';
  if(tk.shape)v+='<div class="row"><span>shape इंजन</span>'+pill(tk.shape)+'</div>';
  v+='<div class="row"><span>Gold (सही)</span>'+(tk.gold?pill(tk.gold):'<span class="mut">अज्ञात</span>')+'</div>';
  if(tk.flag)v+='<div class="row" style="color:#ffd43b">⚑ review queue में (इंजन असहमत / कम-confidence)</div>';
  if(tk.adj)v+='<div class="row" style="color:#39d98a">✓ vision द्वारा पुष्टि (adjudicated)</div>';
  const ok=okOf(tk);
  if(ok===false)v+='<div class="row" style="color:#ff6b6b">⚠ इस इंजन से गलत वर्गीकरण</div>';
  else if(ok===true)v+='<div class="row" style="color:#39d98a">✓ इस इंजन से सही</div>';
  v+='<div class="row"><span>weight</span><code>'+(tk.weight??'—')+'</code></div>';
  v+='<div class="row"><span>slant</span><code>'+(tk.slant==null?'—':(Math.round(tk.slant*10)/10))+'°</code></div>';
  v+='<div class="row"><span>confidence</span><code>'+tk.conf+'</code></div>';
  d.innerHTML=v; d.classList.remove('mut');
}
function stats(){
  const p=DATA.pages[pi];
  const gAll=p.tokens.filter(t=>t.gold!=null);
  const g=gAll.filter(inScope);           // scored set for the selected skill
  const ok=g.filter(t=>okOf(t)).length;
  const acc=g.length?(100*ok/g.length):0;
  // review queue: flagged tokens; auto skill = unflagged subset
  const flagged=p.tokens.filter(t=>t.flag);
  const gFlag=gAll.filter(t=>t.flag), gAuto=gAll.filter(t=>!t.flag);
  const autoOk=gAuto.filter(t=>okOf(t)).length;
  const errTot=gAll.filter(t=>okOf(t)===false).length;
  const errCaught=gFlag.filter(t=>okOf(t)===false).length;
  const autoAcc=gAuto.length?100*autoOk/gAuto.length:0;
  const kpi=document.getElementById('kpi');
  kpi.innerHTML=
   box(engLabel(),'सक्रिय इंजन (skill)')+
   box(p.tokens.length,'remedy tokens')+
   box(g.length,'gold से मिले')+
   box(acc.toFixed(1)+'%','rank सटीकता')+
   box(g.length-ok,'गलतियाँ')+
   box(flagged.length,'review queue ⚑')+
   box(autoAcc.toFixed(1)+'%','auto (बिना-flag) सटीकता')+
   box((errTot?Math.round(100*errCaught/errTot):0)+'%','flag में पकड़ी गलतियाँ');
  // confusion matrix 5..1 (selected engine)
  const R=[5,4,3,2,1]; const m={};R.forEach(a=>{m[a]={};R.forEach(b=>m[a][b]=0)});
  g.forEach(t=>{const s=eff(t); if(m[t.gold]&&m[t.gold][s]!=null)m[t.gold][s]++});
  let h='<table><tr><th>gold↓ / sys→</th>'+R.map(r=>'<th><span class="sw" style="background:'+HEX[r]+'"></span>'+r+'</th>').join('')+'</tr>';
  R.forEach(a=>{h+='<tr><th><span class="sw" style="background:'+HEX[a]+'"></span>'+a+'</th>'+
    R.map(b=>{const v=m[a][b];const diag=a===b;
      return '<td style="background:'+(v===0?'transparent':(diag?'#12351f':'#3a1414'))+
      ';color:'+(v===0?'#555':'#fff')+'">'+v+'</td>';}).join('')+'</tr>';});
  h+='</table>';
  document.getElementById('cm').innerHTML=h;
  // errors by confusion type + by length (selected engine)
  const errs=g.filter(t=>okOf(t)===false);
  const conf={}; errs.forEach(t=>{const k=t.gold+'→'+eff(t);conf[k]=(conf[k]||0)+1});
  const byLen={}; errs.forEach(t=>{const L=(t.text.split(/\s+/)[0]||'').replace(/[^A-Za-z]/g,'').length;byLen[L]=(byLen[L]||0)+1});
  let e='<div class="mut" style="margin-bottom:6px">कुल '+errs.length+' गलतियाँ</div>';
  e+='<b style="font-size:12px">किस तरह (gold→system)</b>';
  Object.entries(conf).sort((a,b)=>b[1]-a[1]).forEach(([k,n])=>{e+=barRow(k,n,errs.length);});
  e+='<b style="font-size:12px">token लम्बाई (अक्षर)</b>';
  Object.entries(byLen).sort((a,b)=>a[0]-b[0]).forEach(([k,n])=>{e+=barRow(k+'-अक्षर',n,errs.length);});
  document.getElementById('err').innerHTML=e;
  // legend
  document.getElementById('legend').innerHTML=[5,4,3,2,1].map(r=>
    '<div><span class="sw" style="background:'+HEX[r]+'"></span>'+NAME[r]+'</div>').join('')+
    '<div class="mut" style="margin-top:6px">weight threshold इस पेज: <code>'+(p.weight_threshold??'—')+'</code> · लाल डैश बॉक्स = gold से भिन्न</div>';
}
function barRow(label,n,tot){
  const pct=tot?100*n/tot:0;
  return '<div class="row"><span>'+label+'</span><span>'+n+'</span></div>'+
    '<div class="bar"><span style="width:'+pct+'%"></span></div>';
}
function box(n,l){return '<div class="b"><div class="n">'+n+'</div><div class="l">'+l+'</div></div>';}

// ---- download / export (client-side; works even from a file:// dashboard) ----
function rowOf(p,tk){const r=eff(tk), g=tk.gold;
  return {book:p.book,page:p.tag,rubric:tk.rubric||'',remedy:tk.text,rank:r,rank_name:RNAME[r],
    scalar:tk.scalar??'',mlp:tk.mlp??'',shape:tk.shape??'',confidence:tk.conf,
    flag:tk.flag?1:0,adjudicated:tk.adj?1:0,gold:(g==null?'':g),
    correct:(g==null?'':(r===g?1:0)),engine:engine};}
function pageRows(p){return p.tokens.map(t=>rowOf(p,t));}
function allRows(){const o=[];DATA.pages.forEach(p=>p.tokens.forEach(t=>o.push(rowOf(p,t))));return o;}
function csvCell(v){v=String(v);return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
function csvRows(rows){let s=COLS.join(',')+'\n';
  rows.forEach(r=>{s+=COLS.map(c=>csvCell(r[c])).join(',')+'\n';}); return s;}
function proofTxt(p){
  const order=[5,4,3,2,1]; let s='PAGE '+p.tag+' (book '+p.book+')  engine='+engine+'\n';
  s+='rank 5=CAPITALS 4=Antique 3=Italic 2=Roman 1=(paren)\n'+'='.repeat(60)+'\n';
  const seen=[], byRub={};
  p.tokens.forEach(tk=>{const k=tk.rubric||'(no heading)';
    if(!(k in byRub)){byRub[k]=[];seen.push(k);} byRub[k].push(tk);});
  seen.forEach(k=>{s+='\n'+k+'\n';
    order.forEach(r=>{const items=byRub[k].filter(t=>eff(t)===r).map(t=>t.text+(t.conf<0.6?'?':''));
      if(items.length) s+='  ['+r+' '+RNAME[r]+'] '+items.join(', ')+'\n';});});
  return s;}
function dl(name,text,mime){
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([text],{type:mime})); a.download=name;
  document.body.appendChild(a); a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href); a.remove();},0);}
function downloads(){
  const d=document.getElementById('downloads'); d.innerHTML='';
  const p=DATA.pages[pi];
  const mk=(label,fn)=>{const b=el('div','btn',label); b.onclick=fn; d.appendChild(b);};
  mk('CSV — सब पेज · रिपर्टरी (इंजन: '+engine+')',
     ()=>dl('tpb_grades_'+engine+'.csv','﻿'+csvRows(allRows()),'text/csv;charset=utf-8'));
  mk('CSV — यह पेज ('+p.tag+')',
     ()=>dl('tpb_grades_'+p.tag+'_'+engine+'.csv','﻿'+csvRows(pageRows(p)),'text/csv;charset=utf-8'));
  mk('Proof .txt — यह पेज',
     ()=>dl(p.tag+'_proof_'+engine+'.txt',proofTxt(p),'text/plain;charset=utf-8'));
  mk('JSON — यह पेज',
     ()=>dl(p.tag+'_'+engine+'.json',JSON.stringify(pageRows(p),null,1),'application/json'));
  mk('JSON — सब पेज',
     ()=>dl('tpb_grades_'+engine+'.json',JSON.stringify(allRows(),null,1),'application/json'));
  d.appendChild(el('div','hint','चयनित इंजन “'+engine+'” की रैंक निर्यात · CSV में gold+correct कॉलम · UTF-8 BOM (Excel-ready)।'));
}
function render(){tabs();engineBar();filters();downloads();boxes();stats();}
render();
