"""Bounded operator-requested speed overrides. Never runs automatically."""
from datetime import datetime
import base64, hashlib, hmac, json, math, secrets, threading, time, urllib.request
HOSTS={'SE01':'192.0.2.11','SE02':'192.0.2.12','MA01':'192.0.2.13','INTAMSYS':'192.0.2.16','IDEX':'idex-bridge'}
KEY=secrets.token_bytes(32)
LOCK=threading.Lock()
USED={}
ESTIMATES={}

def duet_status(data):
    # Read the existing local Wi-Fi bridge, never connect directly to the Duet.
    if not data.get('server_time'): raise ValueError('No hay lectura reciente de la IDEX')
    age=time.time()-datetime.fromisoformat(data['server_time'].replace('Z','+00:00')).timestamp()
    if not -5<=age<=10: raise ValueError('La lectura de la IDEX está desactualizada')
    job=data.get('job') or {};file=job.get('file') or {}
    state={'processing':'printing','printing':'printing','paused':'paused','pausing':'paused','resuming':'printing'}.get(data.get('state',{}).get('status'),'standby')
    speed=(data.get('status') or {}).get('params',{}).get('speedFactor')
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or speed<=0:
        raise ValueError('La IDEX no informa su porcentaje de velocidad')
    return {'result':{'status':{'print_stats':{'state':state,'filename':file.get('fileName','').replace('0:/gcodes/',''),'print_duration':job.get('duration') or 0,'total_duration':job.get('duration') or 0},'gcode_move':{'speed_factor':speed/100}}}}

def read(host, path):
    if host=='idex-bridge':
        with urllib.request.urlopen('http://127.0.0.1:8811/api/state',timeout=10) as r:
            return duet_status(json.load(r))
    with urllib.request.urlopen('http://'+host+':7125'+path,timeout=8) as r:
        return json.load(r)

def ticket(printer, ps, speed, now):
    data=dict(printer=printer,filename=ps.get('filename'),elapsed=ps.get('total_duration') or 0,speed=speed,issued=now/1000,nonce=secrets.token_hex(12),jobId=ps.get('_timeline_job_id'))
    raw=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode()
    return raw+'.'+hmac.new(KEY,raw.encode(),hashlib.sha256).hexdigest()

def decode(token, now):
    raw,sig=token.split('.')
    if not hmac.compare_digest(hmac.new(KEY,raw.encode(),hashlib.sha256).hexdigest(),sig):
        raise ValueError('La consulta expiró; actualiza la línea de tiempo')
    data=json.loads(base64.urlsafe_b64decode(raw))
    if not 0 <= now-data['issued'] <= 120: raise ValueError('La consulta expiró; actualiza la línea de tiempo')
    return data

def estimate(printer, ps, progress, speed, now, base_remaining=None):
    elapsed=ps.get('print_duration') or 0
    remaining=base_remaining or (elapsed*(1-progress)/progress if .01<progress<1 else 0)
    start=now-(ps.get('total_duration') or 0)*1000
    with LOCK:
        old=ESTIMATES.get(printer)
        same=old and old['file']==ps.get('filename') and abs(start-old['start'])<10000 and progress>=old['progress']
        if same:
            if abs(speed-old['speed'])>.05:
                remaining=old['remaining']*(1-progress)/max(.00001,1-old['progress'])*old['speed']/speed
                anchor=(now,progress)
            else:
                anchor=old['anchor']
                dt=(now-anchor[0])/1000; dp=progress-anchor[1]
                if dt>=30 and dp>.00001:
                    remaining=dt*(1-progress)/dp
                else:
                    remaining=old['remaining']*(1-progress)/max(.00001,1-old['progress'])
        else: anchor=(now,progress)
        ESTIMATES[printer]=dict(file=ps.get('filename'),start=start,progress=progress,speed=speed,remaining=remaining,anchor=anchor)
    return remaining

def apply(payload, reader=read, opener=urllib.request.urlopen, clock=time.time):
    if not isinstance(payload,dict) or set(payload)!={'ticket','percent'}: raise ValueError('Solicitud inválida')
    percent=payload['percent']
    if isinstance(percent,bool) or not isinstance(percent,(float,int)) or not math.isfinite(percent) or not 5<=percent<=200:
        raise ValueError('La velocidad debe estar entre 5 y 200 %')
    data=decode(payload['ticket'],clock())
    host=HOSTS.get(data['printer'])
    if not host: raise ValueError('Esta impresora no permite ajustar la velocidad desde la línea de tiempo')
    with LOCK:
        if data['nonce'] in USED: return USED[data['nonce']]
        status=reader(host,'/printer/objects/query?print_stats&gcode_move')['result']['status']
        ps=status['print_stats']; speed=status['gcode_move']['speed_factor']*100
        age=clock()-data['issued']; elapsed=ps.get('total_duration') or 0
        if ps.get('state')!='printing' or ps.get('filename')!=data['filename'] or not data['elapsed']-2<=elapsed<=data['elapsed']+age+15:
            raise ValueError('El trabajo cambió o ya no está imprimiendo; actualiza antes de ajustar')
        if data.get('jobId'):
            jobs=reader(host,'/server/history/list?limit=5&order=desc').get('result',{}).get('jobs',[])
            if not any(j.get('job_id')==data['jobId'] and j.get('status')=='in_progress' for j in jobs):
                raise ValueError('El trabajo cambió; actualiza antes de ajustar')
        if abs(speed-data['speed'])>.05: raise ValueError('La velocidad cambió desde la consulta; actualiza antes de ajustar')
        # Reserve before sending: network ambiguity must never cause an automatic retry.
        result=dict(sent=True,confirmed=False,percent=percent,message='Solicitud enviada; comprueba el porcentaje antes de repetir')
        USED[data['nonce']]=result
        for key in list(USED)[:-200]: USED.pop(key,None)
        url='http://127.0.0.1:8811/api/command' if host=='idex-bridge' else 'http://'+host+':7125/printer/gcode/script'
        body={'command' if host=='idex-bridge' else 'script':f'M220 S{percent:.2f}'}
        req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        try:
            with opener(req,timeout=8) as r: r.read()
            if host=='idex-bridge': time.sleep(1.1)  # Let the bridge's one-second read cache expire.
            actual=reader(host,'/printer/objects/query?gcode_move')['result']['status']['gcode_move']['speed_factor']*100
            result.update(actual=actual,confirmed=abs(actual-percent)<.1,message='Velocidad confirmada' if abs(actual-percent)<.1 else 'Enviada; el porcentaje leído todavía es distinto. No se repetirá automáticamente.')
        except Exception:
            result['message']='No se pudo confirmar el envío. Revisa la velocidad de la impresora antes de volver a intentarlo.'
        return result
