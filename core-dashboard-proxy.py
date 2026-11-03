#!/usr/bin/env python3
import json
import mimetypes
import os
from pathlib import Path
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from timeline_data import snapshot as timeline_snapshot
from timeline_speed import apply as apply_timeline_speed
import cleanup_reports
import platelink_routes

ROOT = str(Path(__file__).resolve().parent / 'web')
SHARE_API = 'http://127.0.0.1:8790'
PORT = int(os.environ.get('LAB_PORT','8788'))

def read_file(path):
    with open(path, 'rb') as f:
        return f.read()

def content_type(path):
    if path.endswith('.html'):
        return 'text/html; charset=utf-8'
    if path.endswith('.js'):
        return 'application/javascript; charset=utf-8'
    if path.endswith('.css'):
        return 'text/css; charset=utf-8'
    typ, _ = mimetypes.guess_type(path)
    return typ or 'application/octet-stream'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence access logs
        pass

    def _send(self, code, body, typ='application/json', extra=None):
        self.send_response(code)
        self.send_header('Content-Type', typ)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _proxy_json(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            SHARE_API + path,
            data=data,
            method=method,
            headers={'Content-Type': 'application/json'} if data is not None else {},
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read(), r.headers.get_content_type()

    def do_OPTIONS(self):
        if self.path.startswith('/api/'):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            return
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if os.environ.get("LAB_ENABLE_COMMANDS") != "1":
            self._send(403, b'{"error":"Commands disabled: explicitly enable LAB_ENABLE_COMMANDS on a trusted network"}')
            return
        if self.path == '/api/timeline/speed':
            origin=self.headers.get('Origin','')
            if origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):
                return self._send(403,b'{"error":"Se requiere el dashboard del laboratorio"}')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096 or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('Solicitud inválida')
                result=apply_timeline_speed(json.loads(self.rfile.read(length)))
                return self._send(200,json.dumps(result).encode())
            except ValueError as error:
                return self._send(409,json.dumps({'error':str(error)}).encode())
            except Exception:
                return self._send(502,b'{"error":"No se pudo consultar la impresora; actualiza antes de ajustar"}')

        if platelink_routes.handle(self, "POST"):return
        if self.path == '/proxy/intamsys/server/spoolman/spool_id':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 128:
                    return self._send(400, b'{"error":"Invalid spool assignment"}')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {'spool_id'} or type(payload['spool_id']) is not int or payload['spool_id'] <= 0:
                    return self._send(400, b'{"error":"Invalid spool assignment"}')
                with urllib.request.urlopen('http://127.0.0.1:7912/api/v1/spool/' + str(payload['spool_id']), timeout=12) as response:
                    spool = json.load(response)
                if spool.get('archived'):
                    return self._send(400, b'{"error":"Spool unavailable"}')
                req = urllib.request.Request('http://192.0.2.16:7125/server/spoolman/spool_id', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=12) as response:
                    self._send(response.status, response.read(), response.headers.get_content_type())
            except urllib.error.HTTPError as exc:
                self._send(exc.code, exc.read(), exc.headers.get_content_type())
            except (ValueError, TypeError):
                self._send(400, b'{"error":"Invalid spool assignment"}')
            except Exception:
                self._send(502, b'{"error":"Unable to assign INTAMSYS spool"}')
            return
        if self.path == '/proxy/intamsys/server/intamsys/material/sync':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 64:
                    return self._send(400,b'{"error":"Invalid request"}')
                if json.loads(self.rfile.read(length)) != {}:
                    return self._send(400,b'{"error":"Metadata sync accepts no commands"}')
                req=urllib.request.Request('http://192.0.2.16:7125/server/intamsys/material/sync',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(req,timeout=15) as response:
                    self._send(response.status,response.read(),response.headers.get_content_type())
            except Exception:
                self._send(502,b'{"error":"INTAMSYS metadata unavailable"}')
            return
        if cleanup_reports.handle(self, 'POST', urlparse(self.path).path):
            return
        if self.path == '/proxy/idex/api/mounted-spools':
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    return self._send(400, b'{"error":"Invalid payload"}')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict) or set(payload) != {'side', 'spool_id'} or payload['side'] not in ('left', 'right') or type(payload['spool_id']) is not int or payload['spool_id'] <= 0:
                    return self._send(400, b'{"error":"Invalid spool assignment"}')
                with urllib.request.urlopen('http://127.0.0.1:8811/api/spools/' + str(payload['spool_id']), timeout=12) as response:
                    spool = json.load(response).get('spool')
                if not spool or spool.get('archived'):
                    return self._send(400, b'{"error":"Spool unavailable"}')
                with urllib.request.urlopen('http://127.0.0.1:8811/api/mounted-spools', timeout=12) as response:
                    assignments = json.load(response)['assignments']
                assignments[payload['side']] = payload['spool_id']
                req = urllib.request.Request('http://127.0.0.1:8811/api/mounted-spools', data=json.dumps(assignments).encode(), headers={'Content-Type':'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=30) as response:
                    self._send(response.status, response.read(), response.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception:
                self._send(502, b'{"error":"Unable to update spool"}')
            return
        if self.path in ('/proxy/idex/api/control', '/proxy/idex/api/load', '/proxy/idex/api/unload'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024:
                    return self._send(400, b'{"error":"Invalid payload"}')
                payload = json.loads(self.rfile.read(size))
                allowed = {'pause', 'resume', 'cancel', 'emergency', 'home', 'home_x', 'home_y', 'home_z', 'home_u', 'auto_calibration', 'cooldown_sleep', 'save_z_offset'}
                if self.path.endswith('/control'):
                    valid = isinstance(payload, dict) and payload.get('action') in allowed and set(payload) == {'action'}
                else:
                    valid = isinstance(payload, dict) and type(payload.get('tool')) is int and payload['tool'] in (0, 1) and set(payload) == {'tool'}
                if not valid:
                    return self._send(400, b'{"error":"Action not permitted"}')
                if not self.path.endswith('/control') or payload.get('action') not in {'pause', 'resume', 'cancel', 'emergency'}:
                    with urllib.request.urlopen('http://127.0.0.1:8811/api/state', timeout=12) as response:
                        state = json.load(response).get('state', {}).get('status')
                    if state != 'idle':
                        return self._send(409, b'{"error":"IDEX must be idle for this action"}')
                req = urllib.request.Request('http://127.0.0.1:8811' + self.path[len('/proxy/idex'):], data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=30) as response:
                    self._send(response.status, response.read(), response.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception:
                self._send(502, b'{"error":"IDEX dashboard unavailable"}')
            return
        if self.path == '/api/shares':
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                code, body, typ = self._proxy_json('POST', '/api/shares', payload)
                self._send(code, body, typ)
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return
        self._send(404, b'{"error":"not found"}')

    def do_GET(self):
        if platelink_routes.handle(self, "GET"):return
        if cleanup_reports.handle(self, 'GET', urlparse(self.path).path):
            return
        path = urlparse(self.path).path
        if path == '/api/timeline':
            try:
                return self._send(200, json.dumps(timeline_snapshot()).encode())
            except Exception:
                return self._send(502, b'{"error":"Timeline unavailable"}')
        if path == '/api/card-order':
            def read(base, suffix):
                try:
                    with urllib.request.urlopen(base + suffix, timeout=6) as response:
                        return json.load(response)
                except Exception:
                    return None
            def stamp(value):
                try:
                    return float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
                except Exception:
                    return 0
            def latest(item):
                name, base, idex = item
                dates = []
                success = False
                if idex:
                    requests = [('/api/files', 'files'), ('/api/history', 'jobs'), ('/api/queue', 'jobs')]
                else:
                    requests = [('/server/files/list?root=gcodes', 'files'), ('/server/history/list?limit=1&order=desc', 'history'), ('/server/job_queue/status', 'queue')]
                for suffix, kind in requests:
                    data = read(base, suffix)
                    if data is None:
                        continue
                    success = True
                    rows = data.get(kind, []) if idex else (data.get('result', []) if kind == 'files' else data.get('result', {}).get('jobs' if kind == 'history' else 'queued_jobs', []))
                    for row in rows:
                        if kind == 'files' and not str(row.get('name', row.get('path', ''))).lower().endswith(('.gcode', '.gco', '.gc')):
                            continue
                        keys = ('date', 'created_at', 'started_at') if idex else ('modified', 'start_time', 'time_added')
                        dates.extend(stamp(row.get(key)) for key in keys)
                return name, {'timestamp': max(dates, default=0), 'available': success}
            targets = [('SE01', 'http://192.0.2.11', False), ('SE02', 'http://192.0.2.12', False), ('MA01', 'http://192.0.2.13', False), ('IDEX', 'http://127.0.0.1:8811', True), ('INTAMSYS', 'http://192.0.2.16', False)]
            with ThreadPoolExecutor(max_workers=5) as pool:
                result = dict(pool.map(latest, targets))
            return self._send(200, json.dumps(result).encode())
        if path.startswith('/proxy/intamsys/'):
            upstream = self.path[len('/proxy/intamsys'):]
            allowed = {'/printer/info', '/printer/objects/query', '/server/spoolman/status', '/server/job_queue/status', '/server/files/list', '/server/files/metadata', '/server/intamsys/material'}
            thumbnail_path = urlparse(upstream).path
            is_thumbnail = thumbnail_path.startswith('/server/files/gcodes/.thumbs/') and thumbnail_path.endswith('.png') and '..' not in urllib.parse.unquote(thumbnail_path)
            if thumbnail_path not in allowed and not is_thumbnail:
                return self._send(404, b'{"error":"not found"}')
            try:
                with urllib.request.urlopen('http://192.0.2.16' + upstream, timeout=12) as response:
                    self._send(response.status, response.read(), response.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception:
                self._send(502, b'{"error":"INTAMSYS unavailable"}')
            return
        if path.startswith('/proxy/idex/'):
            subpath = path[len('/proxy/idex'):]
            allowed = subpath in ('/api/state', '/api/mounted-spools', '/api/spools', '/api/queue', '/api/files', '/api/thumbnail') or (
                subpath.startswith('/api/spools/') and subpath.rsplit('/', 1)[-1].isdigit())
            if not allowed:
                return self._send(404, b'{"error":"not found"}')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8811' + subpath + ('?' + urlparse(self.path).query if urlparse(self.path).query else ''), timeout=12) as response:
                    self._send(response.status, response.read(), response.headers.get_content_type())
            except Exception:
                self._send(502, b'{"error":"IDEX dashboard unavailable"}')
            return
        if path == '/api/public-url':
            try:
                code, body, typ = self._proxy_json('GET', '/api/public-url')
                self._send(code, body, typ)
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return

        if path.startswith('/api/share/') or path.startswith('/api/camera/'):
            try:
                req = urllib.request.Request(SHARE_API + path, method='GET')
                with urllib.request.urlopen(req, timeout=45) as r:
                    self._send(r.status, r.read(), r.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return

        if path == '/proxy/se02-ups':
            try:
                req = urllib.request.Request('http://192.0.2.12:8791/api/status?ups=ups-se02', method='GET')
                with urllib.request.urlopen(req, timeout=10) as r:
                    self._send(r.status, r.read(), r.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return

        if path == '/proxy/ma01-ups':
            try:
                req = urllib.request.Request('http://192.0.2.13:8791/api/status?ups=ups-ma01', method='GET')
                with urllib.request.urlopen(req, timeout=10) as r:
                    self._send(r.status, r.read(), r.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return

        if path == '/proxy/intamsys-ups':
            try:
                with urllib.request.urlopen('http://192.0.2.16:8791/api/status?ups=ups-intamsys', timeout=8) as r:
                    self._send(r.status, r.read(), r.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode())
            return
        if path == '/proxy/se01-ups':
            try:
                req = urllib.request.Request('http://192.0.2.11:8791/api/status?ups=ups-se01', method='GET')
                with urllib.request.urlopen(req, timeout=10) as r:
                    self._send(r.status, r.read(), r.headers.get_content_type())
            except urllib.error.HTTPError as e:
                self._send(e.code, e.read(), e.headers.get_content_type())
            except Exception as e:
                self._send(502, json.dumps({'error': str(e)}).encode('utf-8'))
            return

        if path == '/apc/se01':
            body = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SE01 APC UPS</title><style>:root{--panel:#fff;--ink:#17212b;--muted:#5b6876;--line:#d9dee5;--ok:#127a65;--bad:#b42318}*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#edf2f8 0%,#f7f9fc 100%);font-family:"Segoe UI",Tahoma,sans-serif;color:var(--ink)}.wrap{max-width:1100px;margin:0 auto;padding:22px}.top,.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:0 16px 40px rgba(23,33,43,.08)}.top{padding:18px 20px;margin-bottom:16px}.top h1{margin:0;font-size:28px}.top p{margin:8px 0 0;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{padding:14px}.k{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6a7988;font-weight:800}.v{margin-top:6px;font-size:20px;font-weight:900}.big{font-size:30px}.chart{margin-top:16px;height:260px;border:1px solid var(--line);border-radius:14px;background:#fff;position:relative;overflow:hidden}.chart canvas{width:100%;height:100%}.footer{margin-top:12px;color:var(--muted);font-size:12px}.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid #cbdcff;background:#e6edfd;color:#2c5bc4;border-radius:999px;padding:10px 14px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;text-decoration:none}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between}.status-ok{color:var(--ok)}.status-bad{color:var(--bad)}@media (max-width:900px){.grid{grid-template-columns:1fr}.v{font-size:18px}.big{font-size:24px}}</style></head><body><div class="wrap"><div class="top"><div class="row"><div><h1>APC-GESTOR · APC UPS</h1><p>Panel en vivo del UPS APC conectado por USB a APC-GESTOR.</p></div><a class="btn" href="http://192.0.2.15:8791/api/status" target="_blank" rel="noopener">Ver JSON</a></div></div><div class="grid"><div class="card"><div class="k">Estado</div><div class="v" id="status">--</div></div><div class="card"><div class="k">Batería</div><div class="v big" id="bcharge">--</div></div><div class="card"><div class="k">Carga</div><div class="v big" id="loadpct">--</div></div><div class="card"><div class="k">Potencia estimada</div><div class="v big" id="watts">--</div></div><div class="card"><div class="k">Tiempo restante</div><div class="v big" id="timeleft">--</div></div><div class="card"><div class="k">Entrada AC</div><div class="v big" id="linev">--</div></div></div><div class="chart card" style="padding:0"><canvas id="c"></canvas></div><div class="footer" id="meta">Cargando...</div></div><script>const ctx=document.getElementById('c').getContext('2d');const data={labels:[],load:[],watts:[]};function draw(){const c=ctx.canvas,w=c.width=c.clientWidth,dpr=window.devicePixelRatio||1,h=c.height=c.clientHeight*dpr;c.width=w*dpr;c.height=h;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#e5ebf2';ctx.lineWidth=1;for(let i=0;i<5;i++){const y=20+i*(h/dpr-40)/4;ctx.beginPath();ctx.moveTo(12,y);ctx.lineTo(w-12,y);ctx.stroke()}function plot(arr,color,max){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();arr.forEach((v,i)=>{const x=12+i*(w-24)/Math.max(1,arr.length-1);const y=(h/dpr-20)-((v/max)*(h/dpr-40));if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()}plot(data.load,'#0b5fff',100);plot(data.watts,'#127a65',600);ctx.fillStyle='#5b6876';ctx.font='12px Segoe UI';ctx.fillText('Load % (azul) / Watts estimados (verde)',12,16)}async function tick(){try{const r=await fetch('/proxy/se01-ups?ts='+Date.now(),{cache:'no-store'});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||'sin datos');document.getElementById('status').textContent=j.status||'--';document.getElementById('bcharge').textContent=j.bcharge||'--';document.getElementById('loadpct').textContent=j.loadpct||'--';document.getElementById('watts').textContent=(j.watts??'--') + (j.watts!=null?' W':'');document.getElementById('timeleft').textContent=j.timeleft||'--';document.getElementById('linev').textContent=j.linev||'--';document.getElementById('meta').textContent=`Modelo ${j.model||'APC'} · ${j.upsname||'se01'} · ${j.driver||''}`;const load=parseFloat(String(j.loadpct||'0').split(' ')[0]);const watts=parseFloat(String(j.watts||'0'));data.labels.push(new Date().toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit',second:'2-digit'}));data.load.push(Number.isFinite(load)?load:0);data.watts.push(Number.isFinite(watts)?watts:0);if(data.labels.length>60){data.labels.shift();data.load.shift();data.watts.shift()}draw()}catch(e){document.getElementById('meta').textContent=e.message}}tick();setInterval(tick,5000);window.addEventListener('resize',draw);draw();</script></body></html>'''
            self._send(200, body, 'text/html; charset=utf-8')
            return

        if path == '/' or path == '/index.html':
            body = read_file(os.path.join(ROOT, 'index.html'))
            self._send(200, body, 'text/html; charset=utf-8')
            return

        if path.startswith('/'):
            local = os.path.normpath(os.path.join(ROOT, path.lstrip('/')))
            if os.path.commonpath([ROOT, local]) != ROOT:
                self._send(403, b'forbidden', 'text/plain; charset=utf-8')
                return
            if os.path.isfile(local):
                self._send(200, read_file(local), content_type(local))
                return

        self._send(404, b'not found', 'text/plain; charset=utf-8')

cleanup_reports.start()
if __name__ == '__main__':
    ThreadingHTTPServer((os.environ.get('LAB_BIND','127.0.0.1'), PORT), Handler).serve_forever()
