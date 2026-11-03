/* Speed changes require an active job, a fresh signed snapshot and operator confirmation. */
window.timelineSpeedEditing=false;
function timelineSpeedPlan(currentPercent, remainingMs, desiredRemainingMs) {
  const percent=currentPercent*remainingMs/desiredRemainingMs;
  if (![currentPercent,remainingMs,desiredRemainingMs,percent].every(Number.isFinite) || remainingMs<=0 || desiredRemainingMs<=0 || percent<5 || percent>200) return null;
  return Math.round(percent*100)/100;
}
window.attachSpeedHandle=function(block,job,pd){
  if(!job.isCurrent || job.state!=='printing' || !job.speedTicket || !job.etaKnown) return;
  block.classList.add('speed-editable');block.setAttribute('role','group');
  const handle=document.createElement('button');handle.className='speed-handle';handle.type='button';
  handle.textContent='↔';handle.setAttribute('aria-label','Ajustar hora de salida de '+pd.printer.name);
  handle.title='Arrastra para ajustar la salida; pulsa para elegir la hora. 5–200 %';
  block.append(handle);
  window.timelineSpeedOpeners[pd.printer.id]=()=>preview(job,pd,job.endMs);
  handle.addEventListener('click',e=>e.stopPropagation());
  handle.addEventListener('keydown',e=>{
    if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();preview(job,pd,job.endMs);}
  });
  handle.addEventListener('pointerdown',e=>{
    if(e.button!==0 || window.timelineSpeedEditing)return;
    e.preventDefault();e.stopPropagation();window.timelineSpeedEditing=true;
    hideTooltip();const now=Date.now(),remaining=job.endMs-now,start=e.clientX,width=block.style.width;
    if(remaining<=0){window.timelineSpeedEditing=false;return;}
    let target=job.endMs,valid=true,moved=false;
    const tip=document.createElement('div');tip.className='speed-drag-tip';tip.setAttribute('role','status');document.body.append(tip);
    const show=()=>{const percent=timelineSpeedPlan(job.speedPercent,remaining,target-now);
      valid=percent!==null;tip.textContent=valid?'Salida ≈ '+new Date(target).toLocaleString('es-MX')+' · '+percent+' %':'Fuera de rango: solo se permite 5–200 %';
      tip.classList.toggle('invalid',!valid);
      if(valid)block.style.width=Math.max(4,tsToX(target)-Math.max(0,tsToX(job.startMs)))+'px';};
    show();handle.setPointerCapture(e.pointerId);
    const move=event=>{moved=moved||Math.abs(event.clientX-start)>3;target=job.endMs+(event.clientX-start)/pixelsPerHour*3600000;show();};
    const finish=event=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',cancel);
      tip.remove();block.style.width=width;
      if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);
      if(valid)preview(job,pd,moved?target:job.endMs);else{window.timelineSpeedEditing=false;loadAll();}
    };
    const cancel=()=>{valid=false;finish();};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',cancel);
  });
  function preview(job,pd,target){
    window.timelineSpeedEditing=true;
    const now=Date.now(),remaining=job.endMs-now;
    const dialog=document.createElement('dialog');dialog.className='speed-dialog';dialog.setAttribute('aria-labelledby','speed-dialog-title');
    dialog.innerHTML='<form method="dialog"><div class="timeline-eyebrow">CONTROL DE IMPRESIÓN</div><h2 id="speed-dialog-title">Ajustar salida</h2><p class="speed-job"></p><p class="speed-current"></p><label>Nueva salida aproximada<input type="datetime-local" step="1" required></label><label class="percent-label">Velocidad de impresión (%)<input class="speed-percent" type="number" min="5" max="200" step="0.01" required></label><p class="speed-plan" role="status"></p><p>La estimación se corregirá con el avance real. Calentamientos, movimientos y cambios de herramienta pueden afectar la duración. El porcentaje se aplica a esta impresión; no cambia el archivo.</p><div class="speed-actions"><button type="button" class="speed-back">Volver</button><button type="submit" class="speed-apply">Aplicar velocidad</button></div></form>';
    if(pd.printer.id==='IDEX'){const warning=document.createElement('p');warning.className='speed-idex-warning';warning.textContent='IDEX: en multicolor, un cambio de herramienta puede restablecer la velocidad. No se conservará automáticamente; comprueba el porcentaje después del cambio.';dialog.querySelector('form').insertBefore(warning,dialog.querySelector('.speed-actions'));}
    const input=dialog.querySelector('input[type=datetime-local]'),percentInput=dialog.querySelector('.speed-percent'),plan=dialog.querySelector('.speed-plan'),apply=dialog.querySelector('.speed-apply'),back=dialog.querySelector('.speed-back');
    dialog.querySelector('.speed-job').textContent=pd.printer.name+' · '+job.filename;
    dialog.querySelector('.speed-current').textContent='Actual: '+job.speedPercent+' % · Salida ≈ '+new Date(job.endMs).toLocaleString('es-MX');
    function local(ms){const date=new Date(ms);return new Date(ms-date.getTimezoneOffset()*60000).toISOString().slice(0,19);}
    input.value=local(target);input.min=local(now+remaining*job.speedPercent/200);input.max=local(now+remaining*job.speedPercent/5);
    let percent=null,sending=false;
    percentInput.addEventListener('input',()=>{const value=Number(percentInput.value);if(value>=5&&value<=200){input.value=local(now+remaining*job.speedPercent/value);update(false);}else{percent=null;plan.textContent='La velocidad debe estar entre 5 y 200 %.';apply.disabled=true;}});
    function update(syncPercent=true){percent=timelineSpeedPlan(job.speedPercent,remaining,new Date(input.value).getTime()-now);
      if(syncPercent)percentInput.value=percent??'';
      plan.textContent=percent===null?'Elige una hora que corresponda a una velocidad entre 5 y 200 %.':'Velocidad propuesta: '+percent+' %';apply.disabled=percent===null;}
    input.addEventListener('input',update);input.addEventListener('change',update);update();
    back.onclick=()=>dialog.close();dialog.addEventListener('cancel',e=>{if(sending)e.preventDefault();});
    dialog.addEventListener('close',()=>{dialog.remove();window.timelineSpeedEditing=false;loadAll();},{once:true});
    dialog.querySelector('form').addEventListener('submit',async e=>{
      e.preventDefault();update();if(percent===null||sending)return;sending=true;apply.disabled=true;back.disabled=true;input.disabled=true;percentInput.disabled=true;
      plan.textContent='Comprobando el trabajo y aplicando la velocidad…';
      try{
        const response=await fetch('./api/timeline/speed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket:job.speedTicket,percent})});
        const result=await response.json();
        plan.textContent=response.ok?result.message+(result.actual!==undefined?' · Lectura: '+result.actual.toFixed(2)+' %':''):result.error||'No se pudo aplicar';
      }catch(error){plan.textContent='No se pudo confirmar la solicitud. Comprueba la velocidad antes de repetir.';}
      sending=false;back.disabled=false;back.textContent='Cerrar';apply.hidden=true;
    });
    document.body.append(dialog);dialog.showModal();back.focus();
  }
};
