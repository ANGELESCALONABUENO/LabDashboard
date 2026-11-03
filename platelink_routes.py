"""Same-origin adapter for physical plate metadata. No printer endpoints."""
import json,re,urllib.request,urllib.error
from urllib.parse import urlsplit
BASE='http://192.0.2.10:8812'
PHOTO=re.compile(r'^/api/platelink/photo/([a-f0-9-]{36})/([AB])$')
def handle(handler,method):
 path=urlsplit(handler.path).path
 if not path.startswith('/api/platelink/'):return False
 try:
  if method=='GET':
   match=PHOTO.fullmatch(path)
   if path=='/api/platelink/plates':up='/api/lab/plates'
   elif match:up='/api/lab/photo/'+match[1]+'/'+match[2]
   else:handler._send(404,b'{"error":"Ruta no permitida"}');return True
   req=urllib.request.Request(BASE+up,method='GET')
  elif method=='POST' and path=='/api/platelink/assign':
   origin=handler.headers.get('Origin')
   if origin and urlsplit(origin).netloc!=handler.headers.get('Host'):
    handler._send(403,b'{"error":"Origen no permitido"}');return True
   if 'application/json' not in handler.headers.get('Content-Type',''):raise ValueError('Se requiere JSON')
   length=int(handler.headers.get('Content-Length','0'))
   if not 0<length<=4096:raise ValueError('Solicitud demasiado grande o vacía')
   value=json.loads(handler.rfile.read(length))
   if not isinstance(value,dict) or set(value)-{'action','revision','printer','plate_id','face','transfer_from'}:raise ValueError('Solicitud inválida')
   req=urllib.request.Request(BASE+'/api/lab/assign',data=json.dumps(value).encode(),headers={'Content-Type':'application/json'},method='POST')
  else:handler._send(404,b'{"error":"Ruta no permitida"}');return True
  with urllib.request.urlopen(req,timeout=10) as response:
   body=response.read(3*1024*1024+1)
   if len(body)>3*1024*1024:raise ValueError('Respuesta demasiado grande')
   handler._send(response.status,body,response.headers.get_content_type())
 except urllib.error.HTTPError as e:handler._send(e.code,e.read(10000),e.headers.get_content_type())
 except (ValueError,TypeError):handler._send(400,json.dumps({'error':'Solicitud de cama inválida. Actualiza e inténtalo de nuevo.'}).encode())
 except Exception:handler._send(502,json.dumps({'error':'PlateLink no está disponible. No se cambió la cama registrada.'}).encode())
 return True
