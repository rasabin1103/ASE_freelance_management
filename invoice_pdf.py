"""PDF A4 con datos fiscales, detalle, impuestos y forma de pago."""
from io import BytesIO
from pathlib import Path
import base64, sys
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent / '.dependencies'))
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import A4

def generate_invoice(invoice, branding):
    output=BytesIO()
    accent=colors.HexColor(branding.get('invoiceColor','#176b52'))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('SmallText',fontName='Helvetica',fontSize=9,leading=14,textColor=colors.HexColor('#52625b'),spaceAfter=5))
    styles.add(ParagraphStyle('InvoiceTitle',fontName='Helvetica-Bold',fontSize=27,leading=32,textColor=accent,spaceAfter=10))
    styles.add(ParagraphStyle('LabelText',fontName='Helvetica-Bold',fontSize=9,leading=14,textColor=accent,spaceAfter=8))
    styles.add(ParagraphStyle('RightText',parent=styles['SmallText'],alignment=TA_RIGHT))
    def text(value,style='SmallText'): return Paragraph(escape(str(value or '')).replace('\n','<br/>'),styles[style])
    def money(cents): return f'{cents/100:,.2f}'.replace(',','_').replace('.',',').replace('_','.')+' EUR'
    def date(value): return '-'.join(reversed(value.split('-'))) if value else 'Sin indicar'
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=48,title='Factura '+invoice['number'],author=invoice['profileSnapshot']['name'])
    story=[]
    if branding.get('logo'):
        image=Image(BytesIO(base64.b64decode(branding['logo'].split(',',1)[1])))
        factor=min(150/image.imageWidth,65/image.imageHeight)
        image.drawWidth=image.imageWidth*factor;image.drawHeight=image.imageHeight*factor;image.hAlign='LEFT'
        story.extend([image,Spacer(1,18)])
    story.extend([text('FACTURA','InvoiceTitle'),text('N.º '+invoice['number'],'LabelText'),text('Emisión: '+date(invoice['date'])+'    |    Vencimiento: '+date(invoice.get('due')))])
    if invoice.get('serviceMonth'): story.append(text('Período de trabajo: '+invoice['serviceMonth']))
    story.append(Spacer(1,22))
    issuer=invoice['profileSnapshot'];client=invoice['clientSnapshot']
    def party(label,p):return [text(label,'LabelText'),text(p['name']),text('NIF / CIF: '+p['taxid']),text(p['address']),text(p.get('email',''))]
    parties=Table([[party('EMISOR',issuer),party('CLIENTE',client)]],colWidths=[255,256])
    parties.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),18)]))
    story.extend([parties,Spacer(1,24),text(invoice['description'],'LabelText'),Spacer(1,5)])
    rows=[[text(t,'LabelText') for t in ['CONCEPTO','CANTIDAD','TARIFA','IMPORTE']]]
    for line in invoice.get('lines',[invoice]):
        rows.append([text(line.get('description') or invoice['description']),text(str(line['quantity'])+' '+line['unit']),text(money(round(float(line['rate'])*100)),'RightText'),text(money(line['baseCents']),'RightText')])
    detail=Table(rows,colWidths=[240,85,90,96],repeatRows=1,hAlign='LEFT')
    detail.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f0f5f2')),('LINEBELOW',(0,0),(-1,0),1,accent),('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#dfe7e2')),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story.extend([detail,Spacer(1,22)])
    totalrows=[['Base imponible',money(invoice['baseCents'])],['IVA ('+str(invoice['vat'])+'%)',money(invoice['vatCents'])],['Retención IRPF ('+str(invoice['irpf'])+'%)','- '+money(invoice['irpfCents'])],['TOTAL A COBRAR',money(invoice['totalCents'])]]
    totals=Table([[text(a,'LabelText' if i==3 else 'SmallText'),text(b,'RightText')] for i,(a,b) in enumerate(totalrows)],colWidths=[180,140],hAlign='RIGHT')
    totals.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('BACKGROUND',(0,3),(-1,3),colors.HexColor('#f0f5f2')),('LINEABOVE',(0,3),(-1,3),1,accent)]))
    closing=[totals,Spacer(1,24)]
    if issuer.get('iban'): closing.extend([text('FORMA DE PAGO','LabelText'),text('Transferencia bancaria · IBAN: '+issuer['iban'])])
    story.append(KeepTogether(closing))
    def footer(canvas,document):
        canvas.setStrokeColor(accent);canvas.line(42,37,A4[0]-42,37)
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#68786f'))
        canvas.drawString(42,25,'Factura '+invoice['number']);canvas.drawRightString(A4[0]-42,25,'Página '+str(document.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()

def generate_timesheet(month, record, profile):
    import calendar, datetime
    output=BytesIO();accent=colors.HexColor(profile.get('invoiceColor','#176b52'))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('TSBody',fontSize=9,leading=14,textColor=colors.HexColor('#42584b')))
    styles.add(ParagraphStyle('TSTitle',fontName='Helvetica-Bold',fontSize=25,leading=30,textColor=accent,spaceAfter=14))
    def p(value,style='TSBody'):return Paragraph(escape(str(value or '')).replace('\n','<br/>'),styles[style])
    year,number=map(int,month.split('-'));names=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    vacations=set(record.get('vacations',[]));holidays=set(record.get('holidays',[]));weekdays=vac=hol=0
    story=[]
    if profile.get('logo'):
        logo=Image(BytesIO(base64.b64decode(profile['logo'].split(',',1)[1])))
        scale=min(150/logo.imageWidth,60/logo.imageHeight);logo.drawWidth=logo.imageWidth*scale;logo.drawHeight=logo.imageHeight*scale;logo.hAlign='LEFT';story.extend([logo,Spacer(1,16)])
    story.extend([p('TIMESHEET','TSTitle'),p(names[number-1]+' '+str(year),'Heading2'),p(profile.get('name','')),p('NIF: '+profile.get('taxid','') if profile.get('taxid') else ''),Spacer(1,20)])
    rows=[[p(day) for day in ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']]];marked=[]
    for week in calendar.monthcalendar(year,number):
        cells=[]
        for i,day in enumerate(week):
            if not day:cells.append('');continue
            date=f'{month}-{day:02d}';weekend=i>4;holiday=date in holidays;vacation=date in vacations
            if not weekend:
                weekdays+=1
                if holiday:hol+=1
                elif vacation:vac+=1
            label='' if holiday or vacation or weekend else 'X'
            cells.append(p(str(day)+'\n'+label))
        rows.append(cells)
    table=Table(rows,colWidths=[73]*7,rowHeights=[28]+[65]*(len(rows)-1))
    commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf4ef')),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#d9e3dc')),('TOPPADDING',(0,0),(-1,-1),9)]
    commands += [('BACKGROUND',(col,row),(col,row),color) for row,col,color in marked]
    table.setStyle(TableStyle(commands));story.extend([table,Spacer(1,22)])
    for value in [f'Días laborables de lunes a viernes: {weekdays}',f'Vacaciones en días laborables: {vac}',f'Festivos en días laborables: {hol}',f'DÍAS DE TRABAJO PREVISTOS: {weekdays-vac-hol}']:story.append(p(value))
    story.extend([Spacer(1,18),p('X: día de trabajo previsto. Vacaciones, festivos y fines de semana sin marca.'),p('Calendario previsto según las marcas guardadas. No acredita asistencia ni horas reales trabajadas.')])
    def footer(canvas,document):
        canvas.setStrokeColor(accent);canvas.line(42,37,A4[0]-42,37);canvas.setFont('Helvetica',8)
        canvas.drawString(42,25,'Timesheet '+month);canvas.drawRightString(A4[0]-42,25,'Página '+str(document.page))
    SimpleDocTemplate(output,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=35,bottomMargin=48,title='Timesheet '+month).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
