"""Single-sheet, full-color workshop report, generated only on inMateriis server."""
import math, os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from PIL import Image

FONTDIR=Path('/usr/share/fonts/truetype/dejavu')
for face,file in [('IM','DejaVuSans.ttf'),('IM-Bold','DejaVuSans-Bold.ttf')]:
    if face not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(face,str(FONTDIR/file)))
INK='#14392F';MUTED='#536F67';GOLD='#FFCB28';GREEN='#16856C';BLUE='#3A6AE8'
PALETTE={'MA01':'#E5A619','SE02':'#3269E4','SE01':'#8253C6','INTAMSYS':'#12A080','IDEX':'#B73B59','22IDEX V3':'#B73B59'}

def draw_report(root,items,timeline,now,tz,rate,start,end,label,errors,output='latest.pdf'):
    """One US-letter page. No truncation of jobs; layout scales to the day's volume."""
    w,h=letter;temp=root/(output+'.tmp')
    c=canvas.Canvas(str(temp),pagesize=letter)
    c.setTitle('inMateriis | Limpieza del taller | '+label)
    c.setAuthor('inMateriis - Laboratorio de prototipado')
    def fill(color):c.setFillColor(colors.HexColor(color))
    def text(x,y,s,size=9,color=INK,bold=False):
        fill(color);c.setFont('IM-Bold' if bold else 'IM',size);c.drawString(x,y,str(s))
    def right(x,y,s,size=9,color=INK,bold=False):
        fill(color);c.setFont('IM-Bold' if bold else 'IM',size);c.drawRightString(x,y,str(s))
    def box(x,y,ww,hh,color,r=9):fill(color);c.roundRect(x,y,ww,hh,r,fill=1,stroke=0)
    def lines(s,width,size=9,font='IM',limit=None):
        # Wrap filenames too, not only space-separated words.
        out=[];line=''
        for ch in str(s):
            if pdfmetrics.stringWidth(line+ch,font,size)>width:
                out.append(line);line=ch
            else:line+=ch
        if line:out.append(line)
        if limit and len(out)>limit:
            out=out[:limit];out[-1]=out[-1][:-3]+'…'
        return out
    def date(ts):return datetime.fromtimestamp(ts,tz).strftime('%d/%m %H:%M')
    def amount(g):return (Decimal(str(g))*Decimal(str(rate))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    fill('#F1F5F3');c.rect(0,0,w,h,fill=1,stroke=0)
    box(24,h-106,w-48,82,INK,14)
    logo=root/'inmateriis-logo.png'
    if logo.exists():c.drawImage(ImageReader(str(logo)),38,h-93,57,57,preserveAspectRatio=True,anchor='c',mask='auto')
    text(108,h-49,'inMateriis',21,'#FFFFFF',True)
    text(108,h-69,'LABORATORIO DE PROTOTIPADO',8,'#A8D4C0',True)
    text(108,h-87,'Limpieza y retiro de soportes',10,'#FFFFFF')
    right(w-40,h-49,datetime.fromtimestamp(now,tz).strftime('%d / %m / %Y'),12,GOLD,True)
    right(w-40,h-68,'CORTE '+('09:30' if label=='mañana' else 'EN VIVO'),9,'#FFFFFF',True)
    right(w-40,h-85,'Guadalajara · '+datetime.fromtimestamp(now,tz).strftime('%H:%M'),8,'#B7D6CB')
    total_g=sum(j.get('support_g') or 0 for j in items)
    total_cost=sum((amount(j.get('support_g') or 0) for j in items),Decimal('0'))
    unknown=sum(j.get('support_g') is None for j in items)
    stats=[('PARA LIMPIAR',str(len(items))+' trabajos',GOLD),('SOPORTE ESTIMADO',f'{total_g:.2f} g','#D2E9FF'),('IMPORTE ESTIMADO',f'${total_cost:.2f} MXN','#B9EFDC')]
    gap=8;sw=(w-48-gap*2)/3
    for i,(title,value,col) in enumerate(stats):
        x=24+i*(sw+gap);box(x,h-171,sw,53,col)
        text(x+12,h-136,title,7,INK,True);text(x+12,h-156,value,16,INK,True)
    text(26,h-190,'PIEZAS LISTAS PARA ESTA JORNADA',9,INK,True)
    right(w-26,h-190,f'${rate:.2f} MXN / g de soporte',8,MUTED)
    text(26,h-204,f'Terminadas: {date(start)} a {date(end)} · Sólo finales confirmados',7.5,MUTED)
    # Available card region: 350 points. Up to 5 rows use comfortable thumbnails.
    n=len(items);top=h-216;bottom=224;area=top-bottom
    columns=1 if n<=5 else (2 if n<=12 else 3)
    rows=max(1,math.ceil(n/columns));row_h=(area-(rows-1)*7)/rows
    cw=(w-48-(columns-1)*8)/columns
    if n>30:raise ValueError('Más de 30 trabajos en una jornada: se requiere un formato especial para conservar legibilidad en una hoja')
    if not items:
        box(24,bottom,w-48,area,'#FFFFFF')
        text(48,top-60,'Aún no hay piezas terminadas en este corte.',13,INK,True)
        text(48,top-82,'Las nuevas terminaciones aparecerán automáticamente.',9,MUTED)
    for i,j in enumerate(items):
        col=i%columns;row=i//columns;x=24+col*(cw+8);y=top-(row+1)*row_h-row*7
        accent=PALETTE.get(j['printer'],GREEN)
        box(x,y,cw,row_h,'#FFFFFF');box(x,y,5,row_h,accent,2)
        imsize=min(row_h-18,100 if columns==1 else 66)
        ix=x+13;iy=y+(row_h-imsize)/2
        box(ix,iy,imsize,imsize,'#EAF0F2',7)
        if j.get('thumb'):
            try:
                # Crop transparent padding around real slicer thumbnail for a readable preview.
                im=Image.open(root/j['thumb']).convert('RGBA')
                bounds=im.getchannel('A').getbbox()
                if bounds:im=im.crop(bounds)
                scale=min((imsize-8)/im.width,(imsize-8)/im.height)
                iw,ih=im.width*scale,im.height*scale
                c.drawImage(ImageReader(im),ix+(imsize-iw)/2,iy+(imsize-ih)/2,iw,ih,mask='auto')
            except Exception:text(ix+8,iy+imsize/2,'Sin vista',7,MUTED)
        else:text(ix+8,iy+imsize/2,'Sin vista',7,MUTED)
        tx=ix+imsize+12;available=cw-(tx-x)-12
        if columns==1 and row_h>=95:
            title_size=10;body_size=8.4
            text(tx,y+row_h-20,j['printer'],title_size,accent,True)
            right(x+cw-14,y+row_h-20,'Terminó '+date(j['ended']),8,MUTED)
            title=lines(j['filename'].replace('.gcode',''),available-105,body_size,limit=3)
            for k,line in enumerate(title):text(tx,y+row_h-37-k*11,line,body_size,INK,True)
            cost='Por revisar' if j.get('support_g') is None else f"${amount(j['support_g']):.2f}"
            right(x+cw-15,y+row_h-49,cost,22,INK,True)
            right(x+cw-15,y+row_h-63,'MXN / limpieza',7,MUTED)
            grams='Peso sin confirmar' if j.get('support_g') is None else f"{j['support_g']:.2f} g de soporte · estimado"
            text(tx,y+28,grams,8,MUTED)
            for k,word in enumerate(['Limpiar','Revisar']):
                xx=tx+k*83;c.setStrokeColor(colors.HexColor('#83A79B'));c.rect(xx,y+11,8,8,fill=0,stroke=1);text(xx+13,y+12,word,7.5,MUTED)
        else:
            size=max(6,min(8,row_h/12))
            text(tx,y+row_h-15,j['printer']+' · '+datetime.fromtimestamp(j['ended'],tz).strftime('%H:%M'),size+1,accent,True)
            for k,line in enumerate(lines(j['filename'].replace('.gcode',''),available,size,limit=3)):
                text(tx,y+row_h-28-k*(size+2),line,size,INK)
            cost='Revisar peso' if j.get('support_g') is None else f"{j['support_g']:.2f} g · ${amount(j['support_g']):.2f} MXN"
            text(tx,y+13,cost,size,accent,True)
    # Graphical timeline: printer lanes, actual completed periods, live estimates.
    ty=192;text(26,ty,'TIMELINE DEL TALLER',9,INK,True)
    right(w-26,ty,'Verde: terminada   Azul: en curso / estimación',7,MUTED)
    box(24,66,w-48,116,'#FFFFFF')
    chart_x=104;chart_w=w-134;chart_top=160
    start_axis=start
    ends=[now+6*3600]
    for row in timeline.get('rows',[]):
        for j in row.get('jobs',[]):
            if j.get('isCurrent') and j.get('etaKnown'):ends.append(j['endMs']/1000)
    end_axis=min(now+72*3600,max(ends));span=max(3600,end_axis-start_axis)
    def xx(t):return chart_x+max(0,min(1,(t-start_axis)/span))*chart_w
    for tick in range(5):
        ts=start_axis+span*tick/4;x=xx(ts)
        c.setStrokeColor(colors.HexColor('#DDE8E3'));c.setLineWidth(.5);c.line(x,80,x,162)
        s=datetime.fromtimestamp(ts,tz).strftime('%d/%m %Hh')
        text(min(w-78,x-17),169,s,6,MUTED)
    printers=[('SE01','SE01'),('SE02','SE02'),('MA01','MA01'),('IDEX','22IDEX'),('INTAMSYS','INTAMSYS')]
    rows_by_id={r['printer']['id']:r for r in timeline.get('rows',[])}
    for index,(pid,title) in enumerate(printers):
        yy=chart_top-13-index*16;text(34,yy,title,7,INK,True)
        row=rows_by_id.get(pid,{})
        lane_jobs=[j for j in row.get('jobs',[]) if j.get('isCurrent')]
        finished=[j for j in items if j['printer'] in (pid,'22IDEX V3' if pid=='IDEX' else pid)]
        painted=False
        for j in finished:
            a=max(start_axis,j.get('started') or j['ended']-600);b=j['ended']
            if b>=a:
                box(xx(a),yy-2,max(3,xx(b)-xx(a)),8,'#22A882',3);painted=True
        for j in lane_jobs:
            if j.get('etaKnown'):
                a=max(start_axis,j.get('startMs',now*1000)/1000);b=j['endMs']/1000
                box(xx(a),yy-2,max(3,xx(b)-xx(a)),8,BLUE,3)
                right(w-35,yy+9,'Sale '+date(b),6,INK,True);painted=True
            else:text(chart_x+4,yy,'En curso · salida por estimar',6.5,MUTED);painted=True
        if not painted:text(chart_x+4,yy,'Sin trabajo activo' if row.get('state')!='offline' else 'Sin conexión',6.5,MUTED)
    c.setStrokeColor(colors.HexColor('#DF9E00'));c.setDash(2,2);c.line(xx(now),79,xx(now),161);c.setDash()
    text(26,49,'Responsable: ___________________________   Revisión: ____________',8,INK)
    note=f'Importes estimados; sólo soportes, sin modelo ni purga. {unknown} peso(s) por confirmar.'
    text(26,35,note,6.6,MUTED)
    right(w-26,35,'Generado en inMateriis · 1 hoja',6.6,MUTED)
    if errors:text(26,24,'Datos sin actualizar: '+', '.join(errors),6.5,'#B64632')
    c.showPage();c.save();os.replace(temp,root/output)
