"""Internal cleanup register. Reads printers only; printing requires an explicit POST."""
import hashlib, io, json, math, os, re, sqlite3, threading, time, urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from timeline_data import HOSTS, snapshot

ROOT = Path('./data/cleanup-reports')
ROOT.mkdir(parents=True,exist_ok=True)
TZ = ZoneInfo('America/Mexico_City')
LOCK = threading.RLock()
BUSY = threading.Lock()
STATUS = {'updating': True, 'errors': [], 'updated': None}
RATE = 0.50
LAST_TIMELINE = {}
INITIAL = time.time() - 48*3600
DB = ROOT/'jobs.sqlite3'
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, cleaned INTEGER DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('since', str(INITIAL)))
    INITIAL = float(db.execute('SELECT value FROM settings WHERE key="since"').fetchone()[0])

def get(url, binary=False, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = r.read()
    return data if binary else json.loads(data)

def localdate(ts):
    return datetime.fromtimestamp(ts, TZ).strftime('%d/%m %H:%M')

def support_weight(data):
    """Estimate deposited support extrusion; exclude retraction recovery and non-support."""
    text = data.decode('utf-8', errors='replace')
    declared=re.findall(r'^;\s*(?:support(?: material| filament)? (?:used|weight)(?: \[g\])?|support_weight)\s*[:=]\s*(\d+(?:\.\d+)?)\s*(?:g)?\s*$',text,re.M|re.I)
    if declared:return round(float(declared[-1]),2),'Peso de soporte declarado explícitamente en el G-code'
    def setting(name):
        matches = re.findall(r'^;\s*'+name+r'\s*[:=]\s*([^\r\n]+)', text, re.M)
        if not matches: return []
        return [float(x) for x in re.findall(r'\d+(?:\.\d+)?', matches[-1])]
    densities, diameters = setting('filament_density'), setting('filament_diameter')
    if not densities or not diameters:
        return None, 'Sin densidad o diámetro en el G-code'
    relative, tool, feature = False, 0, ''
    positions, debts, lengths = {}, {}, {}
    tagged = False
    for line in text.splitlines():
        if line.startswith(';TYPE:') or line.startswith('; FEATURE:'):
            feature = line.split(':',1)[1].strip().lower(); tagged = True
        code = line.split(';',1)[0].strip().upper()
        if not code: continue
        command = code.split()[0]
        if command == 'M200':
            d = re.search(r'\bD([\d.]+)',code)
            if d and float(d[1]) != 0: return None, 'Extrusión volumétrica: revisar peso'
        if command in ('G90','G91'): relative = command == 'G91'
        if command in ('M82','M83'): relative = command == 'M83'
        if re.fullmatch(r'T\d+',command): tool = int(command[1:])
        e = re.search(r'(?:^|\s)E(-?\d*\.?\d+)', code)
        if not e: continue
        value = float(e[1])
        if command == 'G92': positions[tool] = value; continue
        if command not in ('G0','G1','G2','G3'): continue
        delta = value if relative else value - positions.get(tool,0)
        positions[tool] = positions.get(tool,0)+value if relative else value
        if delta < 0: debts[tool] = debts.get(tool,0)-delta; continue
        recovery = min(delta,debts.get(tool,0)); debts[tool] = debts.get(tool,0)-recovery
        # Travel/re-prime without spatial motion is not deposited support.
        if feature.startswith('support') and re.search(r'(?:^|\s)[XYZIJK]-?\d',code):
            lengths[tool] = lengths.get(tool,0)+max(0,delta-recovery)
    if not tagged: return None, 'Sin etiquetas de tipo de trayectoria'
    grams = 0
    for t,length in lengths.items():
        if t >= len(densities) and len(densities) != 1: return None, 'Densidad de herramienta no disponible'
        if t >= len(diameters) and len(diameters) != 1: return None, 'Diámetro de herramienta no disponible'
        grams += length*math.pi*(diameters[min(t,len(diameters)-1)]/2)**2*densities[min(t,len(densities)-1)]/1000
    return round(grams,2), 'Estimado de extrusión Support + Support interface; no incluye torre, brim ni modelo'

def add_moon(name,host):
    base = 'http://'+host
    history = get(base+'/server/history/list?limit=100&order=desc')['result']['jobs']
    for row in history:
        end = row.get('end_time') or 0
        if row.get('status') != 'completed' or end < INITIAL: continue
        uid = name+':'+str(row['job_id'])
        with sqlite3.connect(DB) as db:
            existing=db.execute('SELECT data FROM jobs WHERE id=?',(uid,)).fetchone()
            if existing and json.loads(existing[0]).get('analysis_version')==2:continue
        filename = row['filename']; key = hashlib.sha256(uid.encode()).hexdigest()
        job = dict(id=uid,printer=name,filename=filename,ended=end,started=row.get('start_time'),support_g=None,analysis_version=2,
                   weight_note='Pendiente de lectura',thumb=None)
        validated=False
        try:
            current=get(base+'/server/files/metadata?filename='+quote(filename,safe=''))['result']
            original=row.get('metadata') or {}
            if original.get('size')!=current.get('size') or abs(original.get('modified',0)-current.get('modified',0))>1:
                raise ValueError('El archivo cambió desde esta impresión; no se reutiliza su peso')
            validated=True
            previous=json.loads(existing[0]) if existing else {}
            if previous.get('support_g') is not None:
                job['support_g'],job['weight_note']=previous['support_g'],previous['weight_note']
            else:
                raw = get(base+'/server/files/gcodes/'+quote(filename,safe='/'),True,120)
                job['support_g'],job['weight_note'] = support_weight(raw)
        except Exception as exc: job['weight_note'] = 'No se pudo leer el G-code: '+str(exc)[:100]
        thumbs = ((row.get('metadata') or {}).get('thumbnails') or []) if validated else []
        if thumbs:
            thumb = max(thumbs,key=lambda x:x.get('width',0))
            relative = str(Path(filename).parent/ thumb['relative_path'])
            try:
                image = get(base+'/server/files/gcodes/'+quote(relative,safe='/'),True)
                p = ROOT/(key+'.png'); p.write_bytes(image); job['thumb'] = p.name
            except Exception: pass
        with sqlite3.connect(DB) as db:
            db.execute('INSERT INTO jobs(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(uid,json.dumps(job)))

def add_idex():
    history = get('http://127.0.0.1:8811/api/history')
    rows = history.get('sessions',[]) + [r for r in history.get('jobs',[]) if not r.get('legacy')]
    for r in rows:
        # Session "incomplete" refers to sampled material consumption, not its final outcome.
        if r.get('status') not in ('completed','done') or r.get('legacy'): continue
        try: end = datetime.fromisoformat(r['finished_at'].replace('Z','+00:00')).timestamp()
        except Exception: continue
        if end < INITIAL: continue
        uid = 'IDEX:'+str(r['id'])
        with sqlite3.connect(DB) as db:
            if db.execute('SELECT 1 FROM jobs WHERE id=?',(uid,)).fetchone(): continue
        name = r.get('file_name') or r.get('display_name')
        job = dict(id=uid,printer='22IDEX V3',filename=name,ended=end,support_g=None,
                   weight_note='G-code pendiente de validación',thumb=None)
        # Use the existing local cache; never redownload a large active Duet file.
        cache = Path('./data/idex-cache')
        index = []
        try:
            full='0:/gcodes/'+name.removeprefix('0:/gcodes/')
            info=get('http://192.0.2.17/rr_fileinfo?name='+quote(full,safe=''))
            revision=f"{full}|{info.get('size',0)}|{info.get('lastModified','')}"
            index=[cache/(hashlib.sha256(revision.encode()).hexdigest()+'.gcode')]
        except Exception: pass
        if len(index)==1 and index[0].exists():
            job['support_g'],job['weight_note']=support_weight(index[0].read_bytes())
        try:
            data=get('http://127.0.0.1:8811/api/thumbnail?name='+quote(name,safe=''),True)
            p=ROOT/(hashlib.sha256(uid.encode()).hexdigest()+'.png');p.write_bytes(data);job['thumb']=p.name
        except Exception: pass
        with sqlite3.connect(DB) as db: db.execute('INSERT OR IGNORE INTO jobs(id,data) VALUES (?,?)',(uid,json.dumps(job)))

def report_window(now=None, morning=False):
    current=datetime.fromtimestamp(now or time.time(),TZ)
    start=(current-timedelta(days=1)).replace(hour=18,minute=0,second=0,microsecond=0)
    end=current.replace(hour=9,minute=30,second=0,microsecond=0) if morning else current
    return start.timestamp(),min(current.timestamp(),end.timestamp())

def pending(now=None, morning=False):
    with sqlite3.connect(DB) as db:
        rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM jobs WHERE cleaned=0')]
    start,end=report_window(now,morning)
    return sorted((j for j in rows if start<=j['ended']<=end),key=lambda j:j['ended'])

def state():
    with LOCK:
        jobs=pending()
        for j in jobs:
            j['cost_mxn']=float((Decimal(str(j['support_g']))*Decimal(str(RATE))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)) if j.get('support_g') is not None else None
        return dict(STATUS, jobs=jobs,pdf=('/api/cleanup/pdf' if (ROOT/'latest.pdf').exists() else None),
                    daily=sorted(p.name for p in ROOT.glob('diario-*.pdf'))[-7:],rate=RATE,timezone=str(TZ))

def render(timeline,morning=False,output='latest.pdf'):
    from cleanup_design import draw_report
    now=time.time();start,end=report_window(now,morning)
    draw_report(ROOT,pending(now,morning),timeline,now,TZ,RATE,start,end,
                'mañana' if morning else 'vivo',STATUS['errors'],output)

def refresh():
    global LAST_TIMELINE
    if not BUSY.acquire(False):return
    try:
        STATUS['updating']=True;errors=[]
        def collect(pair):
            try:add_moon(*pair)
            except Exception:errors.append(pair[0])
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(collect,HOSTS.items()))
        try:add_idex()
        except Exception:errors.append('IDEX')
        timeline=snapshot()
        with LOCK:
            LAST_TIMELINE=timeline
            STATUS['errors']=errors;render(timeline);STATUS['updated']=time.time()
    except Exception as exc:STATUS['errors']=['Generación: '+str(exc)]
    finally:STATUS['updating']=False;BUSY.release()

def daily():
    with LOCK:
        if not (ROOT/'latest.pdf').exists():raise ValueError('El primer reporte aún está generándose')
        name='diario-'+datetime.now(TZ).strftime('%Y-%m-%d')+'.pdf'
        dest=ROOT/name
        design=ROOT/(name+'.design')
        if not dest.exists() or not design.exists() or design.read_text()!='color-v2':
            render(LAST_TIMELINE or snapshot(),morning=True,output=name)
            design.write_text('color-v2')
        return {'ok':True,'file':name}

def worker():
    while True:
        refresh()
        # The daily cut is scheduled by the server's native systemd timer.
        time.sleep(60)

def handle(handler,method,path):
    if not path.startswith('/api/cleanup'):return False
    try:
        if method=='GET' and path=='/api/cleanup':result=state()
        elif method=='GET' and (path=='/api/cleanup/pdf' or re.fullmatch(r'/api/cleanup/diario-\d{4}-\d{2}-\d{2}\.pdf',path)):
            target='latest.pdf' if path=='/api/cleanup/pdf' else path.rsplit('/',1)[-1]
            with LOCK:data=(ROOT/target).read_bytes()
            handler._send(200,data,'application/pdf');return True
        elif method=='POST':
            # Do not allow a cross-origin site to print or alter the register.
            origin=handler.headers.get('Origin','')
            if origin and origin not in ('http://192.0.2.10:8788','http://192.0.2.10:8800'):
                raise ValueError('Origen no permitido')
            length=int(handler.headers.get('Content-Length','0'))
            if length>4096:raise ValueError('Solicitud demasiado grande')
            body=json.loads(handler.rfile.read(length) or b'{}')
            if path=='/api/cleanup/refresh':threading.Thread(target=refresh,daemon=True).start();result={'ok':True}
            elif path=='/api/cleanup/daily':result=daily()
            elif path=='/api/cleanup/cleaned':
                with sqlite3.connect(DB) as db:db.execute('UPDATE jobs SET cleaned=1 WHERE id=?',(body.get('id'),))
                threading.Thread(target=refresh,daemon=True).start();result={'ok':True}
            elif path=='/api/cleanup/print':
                if body.get('confirm') is not True:raise ValueError('Confirma la impresión a color')
                with LOCK:data=(ROOT/'latest.pdf').read_bytes()
                token=(ROOT/'print-token').read_text().strip()
                req=urllib.request.Request('http://192.0.2.14:8131/print',data=data,method='POST',headers={'Content-Type':'application/pdf','Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=25) as r:result=json.load(r)
            else:raise ValueError('Acción desconocida')
        else:raise ValueError('Ruta desconocida')
        handler._send(200,json.dumps(result).encode())
    except Exception as exc:handler._send(400,json.dumps({'error':str(exc)}).encode())
    return True

def start():threading.Thread(target=worker,daemon=True,name='cleanup-readonly-collector').start()
