(() => {
  const thumbnailCache=new Map();
  async function attachActiveThumbnail(live,title,filename,state){
    if(!filename||!['printing','paused'].includes(state))return;
    try{
      let url=thumbnailCache.get(filename);
      if(!url){
        const meta=await fetchJson('/proxy/intamsys/server/files/metadata?filename='+encodeURIComponent(filename));
        const best=[...(meta.result?.thumbnails||[])].sort((a,b)=>(b.width*b.height)-(a.width*a.height))[0];
        if(!best)return;
        const directory=filename.includes('/')?filename.slice(0,filename.lastIndexOf('/')+1):'';
        url='/proxy/intamsys/server/files/gcodes/'+(directory+best.relative_path).split('/').map(encodeURIComponent).join('/');
        thumbnailCache.set(filename,url);
      }
      const row=document.createElement('div');row.className='live-job';
      const image=document.createElement('img');image.className='live-thumb';image.alt='Miniatura del trabajo activo de HT09';image.src=url;image.style.objectFit='contain';
      image.onerror=()=>{image.remove();row.style.display='block'};
      title.className='live-file';live.replaceChild(row,title);row.append(image,title);
    }catch(_){}
  }
  const grid=document.getElementById('grid');if(!grid)return;
  const cam={id:'INTAMSYS',ip:'192.0.2.16',maintenance:false};
  grid.insertAdjacentHTML('beforeend',cardTemplate(cam));
  const card=document.getElementById('card-INTAMSYS');card.id='intamsys-card';card.setAttribute('aria-label','Abrir HT09 en Mainsail');card.style.alignSelf='start';
  card.querySelector('.cam-title').textContent='HT09';
  card.querySelector('.controls').insertAdjacentHTML('beforebegin','<section class="ups-card" data-ups-link="http://192.0.2.16:8788/apc/intamsys"><div class="ups-title">Energía / APC UPS <a href="http://192.0.2.16:8788/apc/intamsys" target="_blank" rel="noopener">Abrir panel ↗</a></div><div id="ups-intamsys-status" class="ups-grid">Consultando APC…</div></section>');
  async function upsTick(){try{const j=await fetchJson('/proxy/intamsys-ups');const box=document.getElementById('ups-intamsys-status');box.replaceChildren();if(!j.ok)throw Error(j.error);[['Estado',j.status],['Batería',j.bcharge],['Carga',j.loadpct],['Autonomía estimada',j.timeleft]].forEach(([label,value])=>{const item=document.createElement('div');item.className='ups-item';const k=document.createElement('div'),v=document.createElement('div');k.className='k';v.className='v';k.textContent=label;v.textContent=value||'—';item.append(k,v);box.append(item);});}catch(_){document.getElementById('ups-intamsys-status').textContent='Sin lectura del APC; reintentando.'}setTimeout(upsTick,10000)}upsTick();
  card.querySelector('.share-btn')?.remove();
  const frame=document.getElementById('fr-INTAMSYS');
  frame.innerHTML='<div class="placeholder" style="flex-direction:column;gap:12px;text-align:center;padding:20px"><strong style="font-size:20px">HT09</strong><span>Sin cámara configurada</span><small style="max-width:240px;line-height:1.5">No hay una cámara registrada en Moonraker.</small><a href="http://192.0.2.16/" style="color:#dbe8ff;font-weight:700">ABRIR MAINSAIL ↗</a></div>';
  document.getElementById('src-INTAMSYS').textContent='Klipper · Moonraker';
  const actions=[['home','TODO'],['home_x','X'],['home_y','Y'],['home_z','Z'],['sensors','ESTADO SENSORES Z'],['load_mesh','CARGAR MALLA'],['unload_material','EXTRAER MATERIAL'],['load_material','CARGAR MATERIAL'],['pause','PAUSAR'],['resume','CONTINUAR'],['cancel','CANCELAR'],['emergency','PARADA DE EMERGENCIA']];
  const controls=card.querySelector('.controls');
  controls.innerHTML='<div class="controls-title">Inicializar y macros</div><div class="control-row">'+actions.map(([action,label])=>`<button disabled type="button" class="control-btn ${action==='emergency'?'danger':action==='home'?'primary':action==='pause'?'warn':''}" data-intamsys-action="${action}">${label}</button>`).join('')+'</div><div id="intamsys-command" class="live-empty" role="status">Listo para ejecutar comandos.</div><p style="font-size:11px;color:#60758a;line-height:1.5">Calibración de malla: requiere validar cero Z y alcance XY. <a href="http://192.0.2.16/" target="_blank" rel="noopener">Abrir en Mainsail ↗</a></p>';
  card.style.cursor='pointer';
  card.addEventListener('click',event=>{if(!event.target.closest('a,button,input,select,[role="button"]'))location.href='http://192.0.2.16/';});
  card.addEventListener('keydown',event=>{if(event.target===card&&['Enter',' '].includes(event.key)){event.preventDefault();location.href='http://192.0.2.16/';}});
  bindSpoolSelector(cam);
  let currentState='unknown',materialPhase='unknown',ready=false,busy=false;
  function gate(){controls.querySelectorAll('button').forEach(button=>{const action=button.dataset.intamsysAction;const permitted=action==='emergency'?true:!ready?false:action==='pause'?currentState==='printing':action==='resume'?currentState==='paused':action==='cancel'?['printing','paused'].includes(currentState):!['printing','paused','unknown'].includes(currentState)&&['idle','complete'].includes(materialPhase);button.disabled=action==='emergency'?false:busy||!permitted;});}
  const commands={home:'G28',home_x:'G28 X',home_y:'G28 Y',home_z:'G28 Z',sensors:'ESTADO_SENSORES_Z',load_mesh:'CARGAR_MALLA'};
  controls.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||button.disabled)return;event.stopPropagation();
    const action=button.dataset.intamsysAction,note=document.getElementById('intamsys-command');
    busy=true;gate();
    try{
      let script=commands[action];
      if(['load_material','unload_material'].includes(action)){
        const {result:s}=await fetchJson('/proxy/intamsys/server/intamsys/material');
        if(!s?.valid||!Number.isInteger(s.spool_id)||s.spool_id<1||!Number.isFinite(s.temperature))throw Error('Selecciona una bobina activa con temperatura en Spoolman');
        if(!Number.isFinite(s.max_temperature)||s.temperature>s.max_temperature)throw Error(`La bobina #${s.spool_id} pide ${s.temperature} °C; límite habilitado ${s.max_temperature} °C. No se calentó ni extruyó`);
        const loading=action==='load_material';
        if(!confirm(`HT09 · ${loading?'Cargar':'Extraer'} material\nBobina activa #${s.spool_id} · ${s.material} · ${s.temperature} °C (Spoolman).\nConfirma que esta es la bobina realmente colocada.\n${loading?'Introduce el filamento en el extrusor y deja la boquilla físicamente separada de la cama y cualquier pieza. Cargará 100 mm a 3 mm/s.':'Retraerá hasta 50 mm; la retirada final es manual.'}\nNo moverá XYZ. Calentará la boquilla y la apagará al finalizar. ¿Continuar?`))return;
        script=`${loading?'CARGAR_MATERIAL LIBRE=1':'EXTRAER_MATERIAL'} EXPECTED_ID=${s.spool_id} EXPECTED_TEMP=${s.temperature}`;
      }else if(!confirm(`HT09: ${button.textContent}. ${action.startsWith('home')?'Se moverán los ejes: verifica que estén libres.':'La acción se enviará a la impresora.'} ¿Continuar?`))return;
      note.textContent='Enviando…';
      if(script){await sendPrinterCommand(cam,script);if(['load_material','unload_material'].includes(action))materialPhase='pending';}
      else{const endpoint={pause:'pause',resume:'resume',cancel:'cancel'}[action];await fetchJson('http://192.0.2.16'+(action==='emergency'?'/printer/emergency_stop':'/printer/print/'+endpoint),{method:'POST'},45000);}
      note.textContent='Solicitud enviada: '+button.textContent+'. Consulta el resultado en la consola de Mainsail.';
    }catch(error){note.textContent='No se pudo confirmar: '+error.message+'. Consulta Mainsail antes de reintentar.';}
    finally{busy=false;gate();}
  });
  async function tick(){try{
    const data=await fetchJson('/proxy/intamsys/printer/objects/query?print_stats&virtual_sdcard&extruder&heater_bed&heater_generic%20Camara&gcode_macro%20_HT_STATE'),info=await fetchJson('/proxy/intamsys/printer/info');
    const status=data.result.status,p=status.print_stats||{};currentState=p.state||'unknown';materialPhase=status['gcode_macro _HT_STATE']?.phase||'unknown';ready=info.result.state==='ready';gate();
    const badge=document.getElementById('st-INTAMSYS');badge.className='badge '+(!ready?'offline':currentState==='printing'?'printing':currentState==='paused'||currentState==='error'?'offline':'resting');badge.textContent=ready?({standby:'DESCANSANDO',printing:'IMPRIMIENDO',paused:'PAUSADA',complete:'COMPLETADA',cancelled:'CANCELADA',error:'ERROR'}[currentState]||currentState):info.result.state.toUpperCase();
    const live=document.getElementById('live-INTAMSYS');live.replaceChildren();const title=document.createElement('div');title.textContent=ready?(p.filename||'Sin impresión activa.'):info.result.state_message;live.append(title);await attachActiveThumbnail(live,title,p.filename,currentState);
    if(['printing','paused'].includes(currentState)){const progress=document.createElement('progress');progress.max=100;progress.value=100*(status.virtual_sdcard?.progress||0);progress.style.width='100%';const percentage=document.createElement('span');percentage.textContent=progress.value.toFixed(1)+' %';live.append(progress,percentage);}
    const holder=document.getElementById('temps-INTAMSYS');holder.replaceChildren();[['Extrusor','extruder'],['Cama','heater_bed'],['Cámara','heater_generic Camara']].forEach(([name,key])=>{const h=status[key],row=document.createElement('div');row.className='temp-row';[name,h?(h.target>0?'on':'off'):'—',Number.isFinite(h?.temperature)?h.temperature.toFixed(1)+' °C':'—',Number.isFinite(h?.target)?h.target+' °C':'—'].forEach((text,i)=>{const cell=document.createElement('div');cell.className=['temp-name','temp-state','temp-value','temp-target'][i];cell.textContent=text;row.append(cell);});holder.append(row);});
  }catch(_){currentState='unknown';materialPhase='unknown';ready=false;gate();document.getElementById('st-INTAMSYS').textContent='SIN CONEXIÓN';document.getElementById('live-INTAMSYS').textContent='Sin respuesta; reintentando.';}finally{setTimeout(tick,10000);}}
  async function extras(){await Promise.allSettled([fetchSpoolMaterial(cam),(async()=>{try{const data=await fetchJson('/proxy/intamsys/server/job_queue/status'),q=data.result;document.getElementById('queue-count-INTAMSYS').textContent=q.queued_jobs?.length||0;document.getElementById('queue-INTAMSYS').textContent=(q.queued_jobs?.length||0)+' pendientes · '+({paused:'Pausada',ready:'Lista'}[q.queue_state]||q.queue_state);}catch(_){document.getElementById('queue-INTAMSYS').textContent='Cola no disponible.';}})(),(async()=>{const holder=document.getElementById('gcode-INTAMSYS');try{const data=await fetchJson('/proxy/intamsys/server/files/list?root=gcodes'),files=(data.result||[]).filter(file=>/\.(gcode|gco|gc)$/i.test(file.path||'')).sort((a,b)=>b.modified-a.modified).slice(0,3);holder.replaceChildren();if(!files.length){holder.textContent='Sin archivos G-code cargados.';return;}for(const file of files){const link=document.createElement('a');link.className='gcode-card';link.href='http://192.0.2.16/';link.target='_blank';link.rel='noopener';const name=document.createElement('div');name.className='gcode-info';name.textContent=file.path;link.append(name);holder.append(link);}}catch(_){holder.textContent='Archivos no disponibles.';}})()]);setTimeout(extras,30000);}
  tick();extras();
})();
