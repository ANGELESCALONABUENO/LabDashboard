"""Read-only timeline adapters. No printer commands or persistent state."""
import json
import time
from pathlib import Path
from timeline_speed import ticket, estimate, duet_status
import urllib.request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HOSTS = {'SE01': '192.0.2.11', 'SE02': '192.0.2.12',
         'MA01': '192.0.2.13', 'INTAMSYS': '192.0.2.16'}

def fetch(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=7) as response:
            return json.load(response)
    except Exception:
        return {}

def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000
    except (ValueError, AttributeError):
        return None

def current_job(filename, elapsed, progress, remaining, state, now):
    # Do not invent a one-hour finish when there is no usable estimate.
    elapsed = max(0, elapsed or 0)
    progress = max(0, min(1, progress or 0))
    if not remaining and progress > .01 and elapsed > 0:
        remaining = elapsed * (1 - progress) / progress
    known = bool(remaining and remaining > 0) and state != 'paused'
    return dict(filename=filename or 'Sin archivo', startMs=now-elapsed*1000,
                endMs=now+(remaining*1000 if known else 0), state=state,
                isCurrent=True, progress=progress, etaKnown=known, estimated=True)

def moon_row(name, host, now):
    base = 'http://' + host
    paths = ['/printer/objects/query?print_stats&virtual_sdcard&gcode_move',
             '/server/history/list?limit=100&order=desc', '/server/job_queue/status']
    with ThreadPoolExecutor(max_workers=3) as pool:
        status, history, queue = list(pool.map(lambda p: fetch(base, p), paths))
    ps = status.get('result', {}).get('status', {}).get('print_stats', {})
    vs = status.get('result', {}).get('status', {}).get('virtual_sdcard', {})
    state = ps.get('state', 'offline')
    speed = status.get('result', {}).get('status', {}).get('gcode_move', {}).get('speed_factor', 0)*100
    jobs = []
    current = state in ('printing', 'paused')
    active_record=next((j for j in history.get('result',{}).get('jobs',[]) if j.get('status')=='in_progress'),{})
    ps['_timeline_job_id']=active_record.get('job_id')
    if current:
        progress=vs.get('progress') or 0
        remaining=estimate(name,ps,progress,speed,now) if speed>0 else None
        jobs.append(current_job(ps.get('filename'), ps.get('print_duration'), progress, remaining, state, now))
        if state=='printing' and speed>0 and jobs[0]['etaKnown']:
            jobs[0].update(speedPercent=speed,speedTicket=ticket(name,ps,speed,now))
        jobs[0]['startMs'] = now - (ps.get('total_duration') or ps.get('print_duration') or 0)*1000
    for job in history.get('result', {}).get('jobs', []):
        start, end = job.get('start_time'), job.get('end_time')
        if not start or not end or (current and job.get('status') == 'in_progress'):
            continue
        label = {'completed': 'completed', 'cancelled': 'cancelled', 'error': 'error',
                 'klippy_shutdown': 'error', 'klippy_disconnect': 'error', 'interrupted': 'error'}.get(job.get('status'))
        if label:
            jobs.append(dict(filename=job.get('filename', ''), startMs=start*1000,
                             endMs=end*1000, state=label, isCurrent=False))
    queued = queue.get('result', {}).get('queued_jobs', [])
    queue_paused = queue.get('result', {}).get('queue_state') != 'ready'
    next_start = jobs[0]['endMs'] if current else now
    scheduled = not queue_paused and (not current or jobs[0]['etaKnown'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        estimates = list(pool.map(lambda j: fetch(base, '/server/files/metadata?filename=' + quote(j.get('filename',''), safe='')).get('result', {}), queued[:30]))
    for job, metadata in zip(queued[:30], estimates):
        filename = job.get('filename', '')
        duration = metadata.get('estimated_time') or 0
        if scheduled and duration > 0:
            jobs.append(dict(filename=filename, startMs=next_start, endMs=next_start+duration*1000,
                             state='queued', isCurrent=False, estimated=True, etaKnown=True))
            next_start += duration*1000
        else:
            scheduled = False
    return dict(printer=dict(id=name, name='HT09' if name=='INTAMSYS' else name), state=state, currentFile=ps.get('filename'),
                jobs=jobs, queueCount=len(queued), queuePaused=queue_paused,
                unscheduledQueue=len(queued)-sum(j['state']=='queued' for j in jobs),
                historyAvailable='result' in history)

def idex_row(now):
    base = 'http://127.0.0.1:8811'
    with ThreadPoolExecutor(max_workers=3) as pool:
        data, history, queue = list(pool.map(lambda p: fetch(base, p), ['/api/state', '/api/history', '/api/queue']))
    state = {'processing':'printing','printing':'printing','paused':'paused','pausing':'paused',
             'resuming':'printing','idle':'standby','halted':'error'}.get(data.get('state', {}).get('status'), 'offline')
    job = data.get('job') or {}
    file = job.get('file') or {}
    jobs = []
    if state in ('printing', 'paused'):
        size = file.get('size') or 0
        remaining = (job.get('timesLeft') or {}).get('slicer') or (job.get('timesLeft') or {}).get('file')
        progress=(job.get('filePosition') or 0)/size if size else 0
        try:
            normalized=duet_status(data)['result']['status']
            ps=normalized['print_stats'];speed=normalized['gcode_move']['speed_factor']*100
            remaining=estimate('IDEX',ps,progress,speed,now,remaining)
        except (ValueError,KeyError,TypeError):
            ps=None;speed=None
        jobs.append(current_job(file.get('fileName', '').replace('0:/gcodes/', ''), job.get('duration'),progress,remaining,state,now))
        if ps and ps.get('filename') and state=='printing' and jobs[0]['etaKnown']:
            jobs[0].update(speedPercent=speed,speedTicket=ticket('IDEX',ps,speed,now))
    for row in history.get('jobs', []):
        start, end = stamp(row.get('started_at')), stamp(row.get('finished_at'))
        if not start or not end:
            continue
        jobs.append(dict(filename=row.get('display_name') or row.get('file_name', ''),
                         startMs=start, endMs=end, state='completed' if row.get('status') in ('completed','done') else 'cancelled',
                         isCurrent=False, legacy=bool(row.get('legacy') or row.get('incomplete'))))
    pending = [r for r in queue.get('jobs', []) if r.get('status') in ('queued','pending')]
    next_start = jobs[0]['endMs'] if jobs and jobs[0].get('isCurrent') else now
    # IDEX queue requires manual start; do not promise an automatic start time.
    return dict(printer=dict(id='IDEX', name='22IDEX V3'), state=state, jobs=jobs,
                queueCount=len(pending), unscheduledQueue=len(pending), queuePaused=True,
                historyAvailable='jobs' in history, currentFile=file.get('fileName'))

def snapshot():
    now = time.time()*1000
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(moon_row, name, host, now) for name, host in HOSTS.items()]
        futures.append(pool.submit(idex_row, now))
        rows = [future.result() for future in futures]
    rows.extend(print_host_rows())
    return dict(rows=rows, updated=now)


def print_host_rows():
    data={}
    try:
        token=(Path.home()/'.timeline-printhost-token').read_text().strip()
        req=urllib.request.Request('http://192.0.2.14:8132/devices',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=7) as response: data=json.load(response)
    except Exception: pass
    configs=[('ql','Brother QL-700'),('tape','Brother PT-P950NW'),('paper','Canon G2110')]
    rows=[]
    for key,name in configs:
        device=next((d for d in data.get('printers',[]) if d['key']==key),{})
        jobs=[]
        for job in device.get('jobs',[]):
            created=(job.get('created') or 0)*1000
            if not created: continue
            # A timestamp marker, not an invented print duration or finish ETA.
            jobs.append(dict(filename=job.get('name') or 'Trabajo PrintHost',startMs=created,endMs=created,
                state='queued' if job.get('active') else {'Completado':'completed','Cancelado':'cancelled'}.get(job.get('state'),'error'),
                isCurrent=False,eventOnly=True,etaKnown=False))
        stale=time.time()-data.get('updated',0)>30 or bool(data.get('error'))
        state='offline' if stale or not device.get('online') else ('paused' if device.get('status')=='Pausada' else ('printing' if any(j.get('state')=='Procesando' for j in device.get('jobs',[])) else ('queued' if device.get('waiting') else 'standby')))
        rows.append(dict(printer=dict(id='PrintHost-'+key,name=name,kind='print_host'),state=state,jobs=jobs,
            unscheduledQueue=device.get('waiting',0),note=device.get('title','')))
    return rows
