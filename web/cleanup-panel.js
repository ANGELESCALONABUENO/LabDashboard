(() => {
  const panel = document.createElement('section');
  panel.id = 'cleanup-panel';
  panel.innerHTML = `<style>
    #cleanup-panel{margin:12px 0;padding:10px 14px;border:1px solid #73968b66;border-radius:12px;background:var(--panel,transparent);color:inherit}
    #cleanup-panel h2{font-size:13px;margin:0}#cleanup-panel p{font-size:11px;line-height:1.4;margin:4px 0}
    #cleanup-panel .cleanup-bar{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}#cleanup-panel .actions{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0}#cleanup-panel button,#cleanup-panel a{padding:7px 10px;border-radius:7px;border:1px solid #63918077;color:inherit;background:#729e8c22;font:inherit;font-size:11px;cursor:pointer;text-decoration:none}
    #cleanup-panel li{font-size:12px;margin:10px 0;line-height:1.6}#cleanup-panel li button{margin-left:8px;padding:4px 8px}#cleanup-status{min-height:20px}
  </style><div class="cleanup-bar"><div><h2>Limpieza del taller</h2><p id="cleanup-status">Consultando reportes…</p></div>
  <div class="actions"><a href="/api/cleanup/pdf" target="_blank" rel="noopener">PDF + timeline</a><button id="cleanup-print">Imprimir a color</button></div></div>
  <details><summary style="font-size:11px;cursor:pointer">Detalles de la jornada</summary><p>Corte nocturno desde las 18:00 · resumen 9:30 a. m. · $0.50 MXN/g · Generado en la PC inMateriis</p><div class="actions"><button id="cleanup-refresh">Actualizar</button><a href="/timeline.html">Timeline completo ↗</a></div><p id="cleanup-daily"></p><ul id="cleanup-list"></ul></details>`;
  const host=document.querySelector('#grid');
  if(host)host.before(panel);else document.body.append(panel);
  const status=panel.querySelector('#cleanup-status');
  async function post(action,data={}){
    const r=await fetch('/api/cleanup/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const j=await r.json();if(!r.ok||j.error)throw Error(j.error||'No se pudo completar');return j;
  }
  async function tick(){try{
    const r=await fetch('/api/cleanup',{cache:'no-store'});const s=await r.json();if(!r.ok)throw Error(s.error);
    const total=s.jobs.reduce((a,j)=>a+(j.cost_mxn||0),0),missing=s.jobs.filter(j=>j.support_g==null).length;
    status.textContent=`${s.jobs.length} pendientes · $${total.toFixed(2)} MXN estimados${missing?' · '+missing+' sin peso fiable':''}${s.updating?' · Actualizando…':''}${s.errors.length?' · Sin consulta: '+s.errors.join(', '):''}`;
    panel.querySelector('#cleanup-print').disabled=!s.pdf||s.updating;
    const cuts=panel.querySelector('#cleanup-daily');cuts.replaceChildren();
    if(s.daily.length){const link=document.createElement('a');link.textContent='Ver último corte diario';link.href='/api/cleanup/'+s.daily[s.daily.length-1];link.target='_blank';link.rel='noopener';cuts.append(link)}
    const list=panel.querySelector('#cleanup-list');list.replaceChildren();
    for(const j of s.jobs){const li=document.createElement('li');li.textContent=`${j.printer} · ${j.filename} · ${j.support_g==null?'Peso pendiente':j.support_g.toFixed(2)+' g de soporte estimado'} `;
      const b=document.createElement('button');b.textContent='Marcar limpiada';b.onclick=async()=>{if(!confirm('¿Ya retiraste los soportes y revisaste esta pieza?'))return;try{await post('cleaned',{id:j.id});await tick()}catch(e){status.textContent=e.message}};li.append(b);list.append(li)}
  }catch(e){status.textContent='Reporte no disponible: '+e.message}}
  panel.querySelector('#cleanup-refresh').onclick=async()=>{try{await post('refresh');status.textContent='Actualizando reporte y timeline…'}catch(e){status.textContent=e.message}};
  panel.querySelector('#cleanup-print').onclick=async function(){if(!confirm('¿Enviar el PDF de pendientes y timeline a la Canon de oficina, a color, tamaño carta?'))return;this.disabled=true;try{const j=await post('print',{confirm:true});status.textContent=(j.duplicate?'Ya enviado: ':'Enviado a PrintHost: ')+(j.job||'Canon_G2110')}catch(e){status.textContent='No se pudo imprimir: '+e.message}finally{this.disabled=false}};
  tick();setInterval(tick,30000);
})();
