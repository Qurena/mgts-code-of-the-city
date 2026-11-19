const WAVES=DATA.waves,NW=WAVES.length,DIMS=DATA.dims,ITEMS=DATA.items,D=DATA.people,C=DATA.comments,SIG=DATA.signals,INFO=DATA.info;
const N=null;
const st={role:'hr',tab:'overview',item:ITEMS[0].id,intern:2,mentor:1,status:{},log:{},showClosed:false};
const KEY='pulse-demo-v2';
try{const s=JSON.parse(localStorage.getItem(KEY)||'{}');if(s.status)st.status=s.status;if(s.log)st.log=s.log}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify({status:st.status,log:st.log}))}catch(e){}};
const $=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const U=id=>D.find(x=>x.id===id),IT=id=>ITEMS.find(x=>x.id===id);
// Одна общая шкала 1–10: шкала 1–5 растягивается линейно, как в загрузчике. Для показа остаётся исходное «4 из 5».
const norm=(v,mx)=>v===N?N:1+(v-1)*9/(mx-1);
const num=v=>String(Math.round(v*10)/10).replace('.',',');
const chip=(v,mx)=>v===N?'<span class="sc no">нет</span>':`<span class="sc ${v/mx>=.7?'hi':v/mx>.5?'mid':'lo'}">${v}<small>/${mx}</small></span>`;
const median=a=>{const b=a.filter(x=>x!==N).sort((x,y)=>x-y);if(!b.length)return N;const h=b.length/2;return b.length%2?b[(b.length-1)/2]:(b[h-1]+b[h])/2};
const sstat=k=>st.status[k]||'Новый',open=()=>SIG.filter(s=>sstat(s.key)!=='Закрыт');
const TYPE={content:['p-content','Комментарий'],change:['p-change','Изменение'],divergence:['p-div','Расхождение'],low:['p-content','Стабильно низко'],data:['p-data','Нет данных']};
const topicName=k=>DIMS[k]?DIMS[k].label:'Другое / непонятно';

function chart(series,label){
  const W=640,H=250,L=30,R=14,T=12,B=28,x=i=>L+(W-L-R)*i/(NW-1),y=v=>T+(H-T-B)*(10-v)/9;
  let g='';for(const v of [2,4,6,8,10])g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L-6}" y="${y(v)+4}" text-anchor="end">${v}</text>`;
  WAVES.forEach((m,i)=>{g+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle">${m}</text>`});
  series.forEach(s=>{
    s.v.forEach((v,i)=>{if(v===N)g+=`<rect x="${x(i)-14}" y="${T}" width="28" height="${H-T-B}" fill="var(--soft)" opacity=".7"/><text x="${x(i)}" y="${T+14}" text-anchor="middle">нет</text>`});
    let d='',pen=false;s.v.forEach((v,i)=>{if(v===N){pen=false;return}d+=(pen?'L':'M')+x(i)+' '+y(v)+' ';pen=true});
    g+=`<path d="${d}" fill="none" stroke="var(--${s.c})" stroke-width="2.5" ${s.dash?'stroke-dasharray="6 4"':''} stroke-linejoin="round"/>`;
    s.v.forEach((v,i)=>{if(v!==N)g+=`<circle cx="${x(i)}" cy="${y(v)}" r="${i===NW-1?5:3.5}" fill="${i===NW-1?'var(--'+s.c+')':'var(--bg)'}" stroke="var(--${s.c})" stroke-width="2"><title>${s.name}, ${WAVES[i]}: ${num(v)} из 10</title></circle>`});
  });
  return `<div class="chartbox"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${label}">${g}</svg></div>`;
}
const legend=it=>`<div class="legend">${it.i?'<span><i style="background:var(--intern)"></i>Стажёр: '+esc(DIMS[it.i].label)+'</span>':''}${it.m?'<span><i style="background:none;height:0;border-top:3px dashed var(--mentor)"></i>Наставник: '+esc(DIMS[it.m].label)+'</span>':''}</div>`;
const itemSel=()=>`<select id="itemSel" aria-label="Вопрос">${ITEMS.map(k=>`<option value="${k.id}" ${k.id===st.item?'selected':''}>${esc(k.label)}</option>`).join('')}</select>`;
const series=(it,fn)=>{const o=[];if(it.i)o.push({v:fn('i',it.i),c:'intern',name:'Стажёр'});if(it.m)o.push({v:fn('m',it.m),c:'mentor',name:'Наставник',dash:1});return o};
const cellPair=(u,it,w)=>{const a=it.i?chip(u.i[it.i][w],DIMS[it.i].max):'<span class="sc no">—</span>',b=it.m?chip(u.m[it.m][w],DIMS[it.m].max):'<span class="sc no">—</span>';return `${a}<span class="sep">/</span>${b}`};

function overview(){
  const it=IT(st.item),last=NW-1;
  const ni=D.filter(u=>Object.values(u.i).some(a=>a[last]!==N)).length,nm=D.filter(u=>Object.values(u.m).some(a=>a[last]!==N)).length,o=open();
  const ser=series(it,(s,d)=>WAVES.map((_,w)=>median(D.map(u=>norm(u[s][d][w],DIMS[d].max)))));
  const cnt={};C.forEach(c=>{if(c.side==='i'&&c.topic!=='other')cnt[c.topic]=(cnt[c.topic]||0)+1});
  const mx=Math.max(1,...Object.values(cnt));
  return `<div class="grid g3">
   <div class="card kpi"><div class="l">Ответили в волне «${WAVES[last]}»</div><div class="v num">${ni+nm} из ${D.length*2}</div><div class="s">стажёры ${ni}/${D.length} · наставники ${nm}/${D.length}</div></div>
   <div class="card kpi"><div class="l">Требуют внимания</div><div class="v num">${o.length}</div><div class="s">${o.filter(s=>s.type==='content').length} комментариев · ${o.filter(s=>['change','divergence','low'].includes(s.type)).length} по динамике · ${o.filter(s=>s.type==='data').length} по данным</div></div>
   <div class="card kpi"><div class="l">Источник данных</div><div class="v num">2 таблицы</div><div class="s">ответы стажёров и ответы наставников, ${NW} месяцев</div></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
   <div class="card"><div class="head"><h2>Динамика по месяцам</h2><div class="ctrl">${itemSel()}</div></div>${legend(it)}
     ${chart(ser,'Медиана оценок по месяцам')}
     <div class="s" style="color:var(--muted);font-size:12px">Оценки приведены к шкале 1–10. Медиана по ответившим, участников мало, поэтому средний балл не считаем.</div></div>
   <div class="card"><h2>Темы в комментариях стажёров</h2><p style="color:var(--muted);margin:4px 0 12px;font-size:13px">Тему и цитату определяет разборщик, цитату проверяет код.</p>
     ${Object.entries(cnt).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="bar"><span>${esc(topicName(k))}</span><div class="tr"><i style="width:${v/mx*100}%"></i></div><b class="num">${v}</b></div>`).join('')}
     <div class="note" style="margin-top:14px">Единичные случаи не превращаем в «процент недовольных»: на малой группе показываем число комментариев.</div></div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Все стажёры по вопросу «${esc(it.label)}»</h2><div class="scroll"><table><tr><th>Стажёр · наставник</th>${WAVES.map(w=>`<th>${w}</th>`).join('')}</tr>${D.map(u=>`<tr><td><button class="open" data-open="${u.id}">${esc(u.id)}</button> · ${esc(u.mentor)}</td>${WAVES.map((_,w)=>`<td class="num">${cellPair(u,it,w)}</td>`).join('')}</tr>`).join('')}</table></div>
   <div class="m" style="color:var(--muted);font-size:12px;margin-top:8px">В ячейке: стажёр / наставник, в исходных шкалах. Зелёный: от 70 % максимума, жёлтый: больше 50 %, красный: до 50 %.</div></div>`;
}
function queue(){
  const o=st.showClosed?SIG:open();
  return `<div class="card"><div class="head"><h2>Очередь внимания · ${open().length} активных</h2><label class="chk"><input type="checkbox" id="showClosed" ${st.showClosed?'checked':''}>Показать закрытые</label></div><p class="m" style="color:var(--muted);font-size:13px;margin:0 0 8px">Порядок: вес типа сигнала, затем более поздний месяц. Сигнал означает «проверить», а не оценку человека.</p><div class="list">
  ${o.length?'':'<div class="empty">Активных случаев нет.</div>'}${o.map(s=>{const t=TYPE[s.type];return `<div class="row"><div><span class="pill ${t[0]}">${t[1]}</span> <span class="t">${esc(s.u)}</span> <span class="m">· ${WAVES[s.w]}</span><div class="t" style="font-weight:500;margin-top:4px">${esc(s.title)}</div><div class="m">${esc(s.why)}</div></div>
   <div class="ctrl"><select data-st="${s.key}" aria-label="Статус">${['Новый','В работе','Закрыт'].map(x=>`<option ${sstat(s.key)===x?'selected':''}>${x}</option>`).join('')}</select><button class="open" data-open="${s.u}">Карточка</button></div></div>`}).join('')}
  </div></div>`;
}
function card(id,mentorView){
  const u=U(id),sigs=SIG.filter(s=>s.u===id),cm=C.filter(c=>c.u===id),log=st.log[id]||[],it=IT(st.item);
  const hot=(k,w)=>sigs.some(s=>s.w===w&&(s.dim===k.id||s.dim===k.i||s.dim===k.m));
  const tbl=`<div class="scroll"><table><tr><th>Вопрос (стажёр / наставник)</th>${WAVES.map(w=>`<th>${w}</th>`).join('')}</tr>${ITEMS.map(k=>`<tr><td>${esc(k.label)}</td>${WAVES.map((_,w)=>`<td class="${hot(k,w)?'sig':''} num">${cellPair(u,k,w)}</td>`).join('')}</tr>`).join('')}</table></div><div class="scale"><span><span class="sc hi">≥70%</span>высокая</span><span><span class="sc mid">&gt;50%</span>средняя</span><span><span class="sc lo">≤50%</span>низкая</span><span><span class="sc no">нет</span>ответа нет</span><span><span class="sc" style="box-shadow:inset 0 0 0 1px var(--crit)">&nbsp;</span>рамка: по ячейке есть сигнал</span></div>`;
  const comments=mentorView?`<div class="note">Тексты стажёра скрыты политикой доступа. Показывать ли их наставнику, решает HR.</div>`:
    (cm.length?cm.map(c=>{const ok=c.quote&&c.text.includes(c.quote);const t=ok?esc(c.text).replace(esc(c.quote),'<mark>'+esc(c.quote)+'</mark>'):esc(c.text);
      return `<div class="quote"><div class="who ${c.side}">${c.side==='i'?'Стажёр':'Наставник'} · ${WAVES[c.w]}</div><div>${t}</div><div style="margin-top:4px"><span class="pill p-data">Тема: ${esc(topicName(c.topic))}</span> ${ok?'<span class="pill p-ok">цитата найдена в источнике</span>':''}</div></div>`}).join(''):'<div class="empty">Комментариев нет.</div>');
  return `${mentorView?'':'<button class="back" id="back">← Очередь внимания</button>'}
  <div class="grid g2"><div class="card"><div class="head"><div><h2>${esc(u.id)}</h2><span style="color:var(--muted);font-size:13px">Наставник ${esc(u.mentor)} · ${NW} месяцев</span></div><div class="ctrl">${itemSel()}</div></div>${legend(it)}
   ${chart(series(it,(s,d)=>u[s][d].map(v=>norm(v,DIMS[d].max))),'Оценки стажёра и наставника')}
   <h3 style="margin:14px 0 6px">Все ответы по месяцам</h3>${tbl}</div>
   <div class="grid" style="align-content:start">
    <div class="card"><h2>Сигналы</h2>${sigs.length?sigs.map(s=>mentorView&&s.type==='content'?`<div class="row"><div><span class="pill p-data">Комментарий</span><div style="margin-top:4px">Есть вопрос по теме «${esc(topicName(s.dim))}». Текст и цитата доступны только HR.</div></div></div>`:`<div class="row"><div><span class="pill ${TYPE[s.type][0]}">${TYPE[s.type][1]}</span><div style="margin-top:4px">${esc(s.title)}</div><div class="m">${esc(s.why)}</div></div></div>`).join(''):'<div class="empty">Сигналов нет.</div>'}</div>
    <div class="card"><h2>Комментарии</h2>${comments}</div>
    ${mentorView?'':`<div class="card"><h2>Действие HR</h2>${log.map(l=>`<div class="quote"><div class="who">${esc(l.owner)} · до ${esc(l.due)}</div>${esc(l.note)}</div>`).join('')}
     <form class="form" id="actForm"><input id="actOwner" placeholder="Ответственный" required><input id="actDue" type="date" required><textarea id="actNote" placeholder="Что делаем и почему" required></textarea><button class="btn" type="submit">Записать действие</button></form></div>`}
   </div></div>`;
}
function signalsTab(){
  return `<div class="card"><h2>Каталог сигналов</h2><p style="color:var(--muted);font-size:13px;margin:4px 0 12px">Сигналы мы определяем сами: для каждого указано, когда он срабатывает, почему важен HR и что HR делает дальше. Расчёт идёт по простым правилам, без ИИ, поэтому результат можно проверить вручную. Пороги: падение ${DATA.thr.drop}, расхождение ${DATA.thr.divergence}, низкая оценка не выше ${DATA.thr.low} ${DATA.thr.low_months} месяца подряд (шкала 1–10).</p>
  <div class="list">${Object.values(INFO).map(s=>`<div class="row"><div><div class="t">${esc(s.name)}</div><div class="m"><b>Когда:</b> ${esc(s.rule)}</div><div class="m"><b>Почему важно:</b> ${esc(s.why)}</div><div class="m"><b>Что делает HR:</b> ${esc(s.action)}</div></div></div>`).join('')}</div></div>`;
}
function dataTab(){
  const tb=(h,rows)=>`<div class="scroll"><table><tr>${h.map(x=>`<th>${esc(x)}</th>`).join('')}</tr>${rows.map(r=>`<tr>${r.map(x=>`<td>${x===null?'<span class="sc no">пусто</span>':esc(x)}</td>`).join('')}</tr>`).join('')}</table></div>`;
  return `<div class="card"><h2>Какие данные загружаем</h2><p style="color:var(--muted);font-size:13px;margin:4px 0 12px">Формат из вебинара: две таблицы Excel, ответы стажёров и ответы наставников за один период. ${D.length} стажёров, ${D.length} наставников, ${NW} ежемесячных опросов, анонимные ID, один наставник на одного стажёра. Вопросы у сторон разные и не меняются между месяцами. Ниже первые строки двух таблиц.</p>
  <h3 style="margin:12px 0 6px">Таблица 1. Ответы стажёров</h3>${tb(DATA.sample.i.head,DATA.sample.i.rows)}
  <h3 style="margin:16px 0 6px">Таблица 2. Ответы наставников</h3>${tb(DATA.sample.m.head,DATA.sample.m.rows)}
  <div class="note" style="margin-top:14px"><b>Как читаем:</b> пара «стажёр и наставник» определяется по ID. Шкалы приводятся к 1–10. Пустая ячейка остаётся пропуском, ноль мы не подставляем. Повторная загрузка не создаёт дублей. Если в день финала колонки называются иначе, меняется только файл сопоставления колонок.</div></div>`;
}
function render(){
  const hr=st.role==='hr';
  $('#mentorPick').hidden=hr;
  $('#roleHr').setAttribute('aria-pressed',hr);$('#roleMentor').setAttribute('aria-pressed',!hr);
  const tabs=hr?[['overview','Обзор программы'],['queue','Очередь внимания'+`<span class="badge" aria-label="${open().length} активных">${open().length}</span>`],['intern','Карточка стажёра'],['signals','Сигналы'],['data','Данные']]:[['intern','Мой стажёр']];
  if(!hr)st.tab='intern';
  $('#tabs').innerHTML=tabs.map(([k,l])=>`<button role="tab" id="tab-${k}" aria-controls="view" data-tab="${k}" aria-selected="${st.tab===k}" tabindex="${st.tab===k?0:-1}">${l}</button>`).join('');
  const v=$('#view');v.setAttribute('aria-labelledby','tab-'+st.tab);
  const views={overview,queue,signals:signalsTab,data:dataTab};
  if(!hr)v.innerHTML=card(st.mentor,true);
  else v.innerHTML=views[st.tab]?views[st.tab]():card(st.intern,false);
  const ds=$('#itemSel');if(ds)ds.onchange=e=>{st.item=e.target.value;render()};
  const sc2=$('#showClosed');if(sc2)sc2.onchange=e=>{st.showClosed=e.target.checked;render();const c=$('#showClosed');if(c)c.focus()};
  v.querySelectorAll('[data-st]').forEach(s=>s.onchange=e=>{st.status[s.dataset.st]=e.target.value;save();render()});
  v.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{st.intern=b.dataset.open;st.tab='intern';location.hash='intern/'+st.intern});
  const bk=$('#back');if(bk)bk.onclick=()=>{st.tab='queue';location.hash='queue'};
  const f=$('#actForm');if(f)f.onsubmit=e=>{e.preventDefault();const btn=f.querySelector('button');if(btn.disabled)return;btn.disabled=true;(st.log[st.intern]=st.log[st.intern]||[]).push({owner:$('#actOwner').value,due:$('#actDue').value,note:$('#actNote').value});save();render()};
}
$('#tabs').onclick=e=>{const b=e.target.closest('[data-tab]');if(!b)return;st.tab=b.dataset.tab;location.hash=st.tab==='intern'?'intern/'+st.intern:st.tab;render()};
$('#tabs').onkeydown=e=>{
  const bs=[...document.querySelectorAll('#tabs [role=tab]')],i=bs.indexOf(document.activeElement);if(i<0)return;
  const n={ArrowRight:(i+1)%bs.length,ArrowLeft:(i-1+bs.length)%bs.length,Home:0,End:bs.length-1}[e.key];
  if(n===undefined)return;e.preventDefault();bs[n].focus();bs[n].click();setTimeout(()=>{const t=document.querySelector('#tabs [aria-selected=true]');if(t)t.focus()},0);
};
$('#roleHr').onclick=()=>{st.role='hr';st.tab='overview';render()};
$('#roleMentor').onclick=()=>{st.role='mentor';render()};
$('#mentorPick').innerHTML=D.map(u=>`<option value="${u.id}">Наставник ${esc(u.mentor)}</option>`).join('');
$('#mentorPick').onchange=e=>{st.mentor=e.target.value;render()};
function fromHash(){const m=decodeURIComponent(location.hash.slice(1)).split('/'),h=m[0];
  if(['overview','queue','intern','signals','data'].includes(h))st.tab=h;
  if(h==='intern'&&m[1]&&U(m[1])){st.intern=m[1];if(st.role==='mentor')st.mentor=st.intern}
  if(h==='mentor'){st.role='mentor';if(m[1]&&U(m[1]))st.mentor=m[1]}
  if(h==='hr')st.role='hr'}
window.addEventListener('hashchange',()=>{fromHash();render()});
st.intern=D[1].id;st.mentor=D[0].id;fromHash();render();
