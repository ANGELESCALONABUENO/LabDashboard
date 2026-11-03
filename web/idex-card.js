(() => {
  const grid = document.getElementById('grid');
  if (!grid) return;
  const style = document.createElement('style');
  style.textContent = `
    .idex-card{align-self:start;border:1px solid #752631;border-radius:18px;overflow:hidden;background:#300c13;color:#ffecef;box-shadow:0 12px 30px #28040833}
    .idex-header{background:#4b0e19;color:white;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
    .idex-header h2{margin:0;font-size:20px}.idex-header p{margin:5px 0 0;color:#e4b2bb;font-size:12px}
    .idex-links{display:flex;gap:8px;flex-wrap:wrap}.idex-links a{border:1px solid #ffffff70;border-radius:99px;padding:9px 13px;color:#fff;font-size:12px;font-weight:800;background:#ffffff12}
    .idex-body{padding:12px 14px;display:grid;grid-template-columns:1fr;gap:14px}.idex-status{font-weight:900;color:#ffbac6;font-size:12px;text-transform:uppercase}.idex-job{font-size:13px;margin:10px 0;overflow-wrap:anywhere}.idex-progress{accent-color:#df4a63;width:100%;height:12px}
    .idex-materials{display:grid;grid-template-columns:1fr;gap:10px}.idex-material{border:1px solid #70303c;border-radius:10px;padding:12px;background:#42121d}.idex-material strong{display:block;font-size:12px;color:#ffc9d2;margin-bottom:8px}.idex-material span{display:block;font-size:13px}.idex-material small{display:block;color:#d8a7b1;margin-top:6px}
    .idex-temp{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px;font-size:12px;color:#f5c7cf}.idex-note{font-size:11px;color:#c99ca5;margin-top:12px}.idex-stale{opacity:.65}
    .idex-viewer{width:100%;aspect-ratio:16/9;background:#0b080b;position:relative}.idex-viewer iframe{display:block;border:0;width:100%;height:100%;pointer-events:none}.idex-links a{font-size:10px;padding:7px 9px}.idex-linkline{display:block;padding:10px 14px;border-bottom:1px solid #70303c;color:#e6b2bc;font-size:11px;font-weight:700}
    @media(max-width:760px){.idex-body{grid-template-columns:1fr}.idex-materials{grid-template-columns:1fr 1fr}}
  `;
  document.head.append(style);
  style.textContent += `.idex-section{border-top:1px solid #70303c;padding-top:12px}.idex-section h3{font-size:12px;color:#ffc9d2;margin:0 0 10px}.idex-buttons{display:flex;flex-wrap:wrap;gap:7px}.idex-buttons button{border:1px solid #9b5361;border-radius:18px;background:#5b202c;color:#ffecef;font-size:10px;padding:8px 10px;font-weight:800;cursor:pointer}.idex-buttons button:disabled{opacity:.35;cursor:not-allowed}.idex-buttons .danger{background:#aa1832}.idex-table{width:100%;font-size:11px;border-collapse:collapse}.idex-table td,.idex-table th{padding:8px 3px;border-bottom:1px solid #70303c;text-align:left}.idex-recent{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.idex-recent a{color:#ffecef;font-size:10px;overflow-wrap:anywhere;border:1px solid #70303c;border-radius:9px;overflow:hidden;padding:6px}.idex-recent img{width:100%;height:80px;object-fit:contain;background:#ffffff0c}.idex-spool-art{float:right;width:60px;height:60px;margin:0 0 8px 8px}.idex-message{font-size:11px;margin-top:10px;overflow-wrap:anywhere}`;
  grid.insertAdjacentHTML('beforeend', `<article class="idex-card" id="idex-card">
    <header class="idex-header"><div><h2>22IDEX V3</h2><p>Duet 3 · dos extrusores independientes</p></div><nav class="idex-links" aria-label="Dashboard IDEX">
    <a href="http://192.0.2.10:8811/" target="_blank" rel="noopener">Abrir control ↗</a>
    <a href="http://192.0.2.10:8811/?view=viewer" target="_blank" rel="noopener">Visor 3D ↗</a>
    <a href="http://192.0.2.10:8811/?files-list" target="_blank" rel="noopener">Archivos y cola ↗</a></nav></header>
    <div class="idex-viewer" aria-label="Cámara GoPro IDEX" style="overflow:hidden"><img id="idex-gopro-live" alt="Cámara en vivo de la IDEX" style="display:none;width:100%;height:100%;object-fit:cover;object-position:center"><span id="idex-gopro-status" role="status" style="position:absolute;bottom:6px;left:6px;padding:4px 6px;border-radius:5px;font-size:10px;background:#181a20dc;color:#fff">Conectando GoPro…</span></div>
    <a class="idex-linkline" href="http://192.0.2.10:8811/?view=viewer" target="_blank" rel="noopener">ABRIR VISOR 3D EN EL DASHBOARD ↗</a>
    <div class="idex-body"><section><div class="idex-status" id="idex-status">Conectando…</div><div class="idex-job" id="idex-job">Consultando la Duet</div>
    <progress class="idex-progress" id="idex-progress" max="100" value="0" hidden style="display:none" aria-label="Avance de impresion IDEX"></progress><div id="idex-percent"></div><div class="idex-temp" id="idex-temp"></div><div class="idex-note" id="idex-note">Datos desde el dashboard IDEX</div></section>
    <section class="idex-materials" aria-label="Materiales Spoolman de IDEX">${['left','right'].map((side,i)=>`<div class="idex-material"><strong>E${i} · ${i?'DERECHO':'IZQUIERDO'}</strong><span id="idex-spool-${side}">Consultando Spoolman…</span><small id="idex-weight-${side}"></small></div>`).join('')}</section></div></article>`);
  const card = document.getElementById('idex-card');
  const cameraImage=card.querySelector('#idex-gopro-live'),cameraStatus=card.querySelector('#idex-gopro-status');
  let cameraBusy=false;
  function refreshCamera(){
    if(cameraBusy||document.hidden)return;
    cameraBusy=true;
    cameraImage.onload=()=>{cameraImage.style.display='block';cameraStatus.textContent='GoPro · En vivo'};
    cameraImage.onerror=()=>{cameraImage.style.display='none';cameraStatus.textContent='GoPro sin señal · Reconectando…';cameraBusy=false;setTimeout(refreshCamera,3000)};
    cameraImage.src='http://192.0.2.10:8811/api/camera/stream.mjpg?t='+Date.now();
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshCamera()});
  refreshCamera();
  const picker=document.createElement('dialog');picker.style.cssText='width:min(520px,90vw);border:1px solid #ccc;border-radius:16px;padding:20px;color:#243345';
  picker.innerHTML='<h3 id="idex-picker-title">Cambiar carrete IDEX</h3><p>Asigna el carrete montado. No calienta ni mueve filamento.</p><input id="idex-picker-search" placeholder="Buscar número, fabricante o material" style="width:100%;padding:10px;box-sizing:border-box"><div id="idex-picker-list" style="max-height:45vh;overflow:auto;margin:12px 0"></div><p id="idex-picker-note" role="status"></p><button type="button" id="idex-picker-close">Cerrar</button>';document.body.append(picker);
  let pickingSide=null,availableSpools=[],savingSpool=false;
  const pickerList=picker.querySelector('#idex-picker-list'),pickerNote=picker.querySelector('#idex-picker-note');
  function drawSpools(){const query=picker.querySelector('input').value.toLowerCase();pickerList.replaceChildren();availableSpools.filter(s=>!s.archived).forEach(s=>{const f=s.filament||{},label=`#${s.id} · ${f.vendor?.name||''} ${f.name||''} · ${f.material||'—'} · ${Number.isFinite(s.remaining_weight)?Math.round(s.remaining_weight)+' g restantes':'Peso sin dato'}`;if(!label.toLowerCase().includes(query))return;const button=document.createElement('button');button.type='button';button.textContent=label;button.style.cssText='display:block;width:100%;padding:12px;margin:5px 0;text-align:left;border:1px solid #d5dce5;border-radius:8px;background:#f6f8fb;color:#243345;cursor:pointer';button.disabled=savingSpool;button.onclick=async()=>{if(savingSpool||!confirm(`Asignar ${label} a ${pickingSide==='left'?'E0 izquierdo':'E1 derecho'} de IDEX?`))return;savingSpool=true;drawSpools();pickerNote.textContent='Guardando…';try{const response=await fetch('/proxy/idex/api/mounted-spools',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({side:pickingSide,spool_id:s.id}),signal:AbortSignal.timeout(45000)});const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'No se pudo guardar');spoolCache.clear();await materials();picker.close();}catch(error){pickerNote.textContent=error.message;}finally{savingSpool=false;drawSpools();}};pickerList.append(button);});}
  picker.querySelector('input').addEventListener('input',drawSpools);picker.querySelector('#idex-picker-close').onclick=()=>{if(!savingSpool)picker.close();};picker.addEventListener('cancel',event=>{if(savingSpool)event.preventDefault();});
  async function openSpoolPicker(side){window.openIdexSpoolAction(side);}
  ['left','right'].forEach(side=>{const tile=document.getElementById('idex-spool-'+side).parentElement;tile.tabIndex=0;tile.setAttribute('role','button');tile.setAttribute('aria-label','Cambiar carrete IDEX '+(side==='left'?'E0 izquierdo':'E1 derecho'));tile.style.cursor='pointer';tile.title='Cambiar carrete de este extrusor';tile.addEventListener('click',event=>{event.stopPropagation();openSpoolPicker(side);});tile.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();event.stopPropagation();openSpoolPicker(side);}});});
  card.tabIndex=0;
  card.setAttribute('aria-label','22IDEX V3 · abrir panel de control');
  card.style.cursor='pointer';
  card.addEventListener('click',event=>{
    if(event.target.closest('a,button,input,select,textarea,[role="button"]'))return;
    window.location.href='http://192.0.2.10:8811/';
  });
  card.addEventListener('keydown',event=>{
    if(event.target!==card||!['Enter',' '].includes(event.key))return;
    event.preventDefault();window.location.href='http://192.0.2.10:8811/';
  });
  const actions=[['home','HOME TODOS'],['home_x','X'],['home_y','Y'],['home_z','Z'],['home_u','U'],['auto_calibration','AUTO CALIBRATION'],['cooldown_sleep','ENFRIAR Y REPOSAR'],['save_z_offset','GUARDAR Z-OFFSET'],['pause','PAUSAR'],['resume','CONTINUAR'],['cancel','CANCELAR'],['emergency','PARADA DE EMERGENCIA']];
  card.querySelector('.idex-body').insertAdjacentHTML('beforeend', `<section class="idex-section"><h3>TRABAJOS EN COLA · <span id="idex-queue-count">—</span></h3><div id="idex-queue" class="idex-message">Consultando…</div></section><section class="idex-section"><h3>INICIALIZAR Y MACROS · DUET</h3><div class="idex-buttons">${actions.map(([key,label])=>`<button disabled data-idex-action="${key}" class="${key==='emergency'?'danger':''}">${label}</button>`).join('')}${[0,1].map(tool=>`<button disabled data-idex-material="load" data-tool="${tool}">CARGAR E${tool}</button><button disabled data-idex-material="unload" data-tool="${tool}">EXTRAER E${tool}</button>`).join('')}</div><div id="idex-command-note" class="idex-message" role="status">Sin ejecutar comandos.</div></section><section class="idex-section"><h3>TEMPERATURAS</h3><table class="idex-table"><thead><tr><th>Nombre</th><th>Estado</th><th>Actual</th><th>Objetivo</th></tr></thead><tbody id="idex-heaters"></tbody></table></section><section class="idex-section"><h3>ÚLTIMOS G-CODE CARGADOS</h3><div id="idex-recent" class="idex-recent"></div></section>`);
  let machineState='unknown', busy=false;
  function gate(){card.querySelectorAll('button[data-idex-action],button[data-idex-material]').forEach(button=>{const action=button.dataset.idexAction;const permitted=action==='emergency'?machineState!=='unknown':action==='pause'?['processing','printing'].includes(machineState):action==='resume'?machineState==='paused':action==='cancel'?['processing','printing','paused','pausing','resuming'].includes(machineState):machineState==='idle';button.disabled=busy||!permitted;});}
  card.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||button.disabled)return;
    const action=button.dataset.idexAction, material=button.dataset.idexMaterial;
    if(!action&&!material)return;
    if(!confirm(`IDEX: ${button.textContent}. ${material?'Se calentará según el material asignado y se moverá el filamento.':action==='cancel'?'Se cancelará el trabajo actual.':'Esta acción actúa sobre la impresora.'} ¿Continuar?`))return;
    busy=true;gate();set('idex-command-note','Enviando '+button.textContent+'…');
    try{const response=await fetch('/proxy/idex/api/'+(action?'control':material),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(action?{action}:{tool:Number(button.dataset.tool)}),signal:AbortSignal.timeout(35000)});const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'Comando rechazado');set('idex-command-note','Solicitud aceptada: '+button.textContent+'.');}
    catch(error){set('idex-command-note','No se pudo confirmar: '+error.message+'. Consulta el dashboard antes de reintentar.');}
    finally{busy=false;gate();}
  });
  const set = (id, value) => document.getElementById(id).textContent = value;
  async function get(path) {
    const response = await fetch('/proxy/idex' + path, {cache:'no-store', signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw Error('Sin respuesta del dashboard IDEX');
    return response.json();
  }
  const spoolCache = new Map();
  window.refreshIdexMaterials=async()=>{spoolCache.clear();await materials();};
  async function materials() {
    try {
      const {assignments} = await get('/api/mounted-spools');
      await Promise.all(['left','right'].map(async side => {
        const id = assignments[side];
        if (!id) {set('idex-spool-'+side,'Sin carrete asignado');set('idex-weight-'+side,'');return;}
        let cached=spoolCache.get(id);
        if (!cached || Date.now()-cached.at>60000) {cached={at:Date.now(),data:(await get('/api/spools/'+id)).spool};spoolCache.set(id,cached);}
        const spool=cached.data, f=spool.filament||{};
        const container=document.getElementById('idex-spool-'+side).parentElement;
        let art=container.querySelector('.idex-spool-art');
        if(!art){container.insertAdjacentHTML('afterbegin','<svg class="idex-spool-art" viewBox="0 0 100 100" role="img" aria-label="Carrete gris oscuro con tres ventanas del color del filamento"><circle cx="50" cy="50" r="48" fill="#333333"/>'+[0,120,240].map(angle=>`<g transform="rotate(${angle} 50 50)"><path d="M29 13 Q50 1 71 13 Q72 14 70 17 L59 37 Q50 44 41 37 L30 17 Q28 14 29 13Z" fill="currentColor"/><path d="M39 31 Q50 24 61 31 L56 39 Q50 43 44 39Z" fill="#bfbfbf"/></g>`).join('')+'</svg>');art=container.querySelector('.idex-spool-art');}
        art.style.color=/^[a-f0-9]{6}$/i.test(f.color_hex||'')?'#'+f.color_hex:'#b5b5b5';
        set('idex-spool-'+side,`#${id} · ${f.vendor?.name||''} ${f.name||f.material||'Material'}`.trim());
        set('idex-weight-'+side,`${f.material||'—'} · ${Number.isFinite(spool.remaining_weight)?Math.round(spool.remaining_weight)+' g restantes':'Peso sin dato'}`);
        if (/^[a-f0-9]{6}$/i.test(f.color_hex||'')) document.getElementById('idex-spool-'+side).parentElement.style.borderLeft='5px solid #'+f.color_hex;
      }));
    } catch (_) {['left','right'].forEach(side=>{set('idex-spool-'+side,'Material no disponible');set('idex-weight-'+side,'Reintento automatico');});}
  }
  async function tick() {
    try {
      const data=await get('/api/state'), state=data.state?.status||'unknown', job=data.job||{};
      machineState=state;gate();
      const names={idle:'Descansando',processing:'Imprimiendo',printing:'Imprimiendo',paused:'Pausada',pausing:'Pausando',resuming:'Reanudando',busy:'Ocupada',halted:'Detenida',off:'Apagada',starting:'Iniciando',updating:'Actualizando',simulating:'Simulando'};
      const active=['processing','printing','paused','pausing','resuming','simulating'].includes(state);
      set('idex-status',(names[state]||state)+' · '+(data.tools?.find(t=>t.number===data.state?.currentTool)?.name||'Sin herramienta activa'));
      const filename=data.file?.fileName||job.file?.fileName||job.file?.name;
      set('idex-job',active?(filename?filename.split('/').pop():'Trabajo en curso'):'Sin impresión activa');
      {const holder=document.getElementById('idex-job');holder.className=active?'idex-job live-job':'idex-job live-empty';holder.style.minHeight='';if(active&&filename){holder.replaceChildren();const image=document.createElement('img'),text=document.createElement('div'),label=document.createElement('strong');image.className='live-thumb';image.src='/proxy/idex/api/thumbnail?name='+encodeURIComponent(filename);image.alt='Miniatura del trabajo activo';image.onerror=()=>{image.remove();holder.style.gridTemplateColumns='1fr'};holder.style.gridTemplateColumns='';text.className='live-file';label.textContent='Archivo activo:';text.append(label,document.createElement('br'),document.createTextNode(filename.split('/').pop()));holder.append(image,text);}}
      const size=job.file?.size, pct=active&&size?Math.max(0,Math.min(100,100*(job.filePosition||0)/size)):0;
      const progressBar=document.getElementById('idex-progress');progressBar.value=pct;progressBar.hidden=!active;progressBar.style.display=active?'block':'none';set('idex-percent',active?pct.toFixed(1)+' %':'');
      const heaters=data.heat?.heaters||[];
      const heaterBody=document.getElementById('idex-heaters');heaterBody.replaceChildren();
      ['E0 · Izquierdo','E1 · Derecho','Cama','Cámara'].forEach((name,i)=>{const h=heaters[i],row=heaterBody.insertRow();[name,h?(h.state||((h.active||0)>0?'Activo':'Apagado')):'Sin dato',Number.isFinite(h?.current)?h.current.toFixed(1)+' °C':'—',Number.isFinite(h?.active)?h.active+' °C':'—'].forEach(value=>row.insertCell().textContent=value);});
      set('idex-temp',['E0','E1','Cama','Cámara'].map((name,i)=>`${name}: ${Number.isFinite(heaters[i]?.current)?heaters[i].current.toFixed(1):'—'} °C / ${heaters[i]?.active??'—'} °C`).join(' · '));
      set('idex-note','Actualizado '+new Date().toLocaleTimeString('es-MX')+' · Control y materiales en su dashboard');card.classList.remove('idex-stale');
    } catch (_) {machineState='unknown';gate();const bar=document.getElementById('idex-progress');bar.hidden=true;bar.style.display='none';set('idex-percent','');set('idex-status','Sin conexión con IDEX');set('idex-note','Datos anteriores; reintentando conexión');card.classList.add('idex-stale');}
    finally {setTimeout(tick,10000);}
  }
  async function extras(){
    try{const data=await get('/api/queue'),pending=(data.jobs||[]).filter(job=>['queued','pending','running'].includes(job.status));set('idex-queue-count',pending.length);set('idex-queue',pending.length?pending.map(job=>(job.display_name||job.file_name)+' · '+job.status).join(' · '):'Sin trabajos pendientes en la cola IDEX.');}catch(_){set('idex-queue','Cola no disponible');}
    try{const data=await get('/api/files'),recent=(data.files||[]).sort((a,b)=>String(b.date||'').localeCompare(String(a.date||''))).slice(0,3),holder=document.getElementById('idex-recent');holder.replaceChildren();recent.forEach(file=>{const a=document.createElement('a');a.href='http://192.0.2.10:8811/?files-list';a.target='_blank';a.rel='noopener';const img=document.createElement('img');img.alt='Miniatura de '+file.name;img.loading='lazy';img.src='/proxy/idex/api/thumbnail?name='+encodeURIComponent(file.name);img.onerror=()=>{img.remove();};a.append(img,document.createTextNode(file.name));holder.append(a);});}catch(_){set('idex-recent','Archivos no disponibles');}
  }
  tick();materials();extras();setInterval(materials,20000);setInterval(extras,60000);
})();
