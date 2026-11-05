from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import sqlite3, json, datetime, os, re, base64, calendar
from contextlib import contextmanager
from business import generate_recurring, backup_payload, validate_backup
from wealth import validate_wealth, check_ledger, migrate_annual_rates
from portfolio_csv import KINDS as PORTFOLIO_KINDS, validate_portfolio, inspect_csv, preview_import, commit_import

ROOT = Path(__file__).parent
DB = ROOT / 'data' / 'autonomo.db'
DB.parent.mkdir(exist_ok=True)

@contextmanager
def connection():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

with connection() as c:
    c.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL)')
    migrate_annual_rates(c)

def money(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def next_month_due(invoice_date):
    date=datetime.date.fromisoformat(invoice_date)
    year,month=(date.year+1,1) if date.month==12 else (date.year,date.month+1)
    return datetime.date(year,month,calendar.monthrange(year,month)[1]).isoformat()

def validate(kind, d):
    if kind in PORTFOLIO_KINDS:return validate_portfolio(kind,d)
    if kind in ['wealthplan','wealthentry']:
        return validate_wealth(kind,d)
    if kind == 'cashsettings':
        result={}
        for key in ['openingBalance','withdrawals','vatPaid','extraIrpfUsed']:
            value=Decimal(str(d.get(key,0)))
            if not value.is_finite() or abs(value)>100000000 or (key!='openingBalance' and value<0): raise ValueError('Ajuste de caja no válido')
            result[key]=str(value)
        return result
    if kind == 'recurring':
        date=datetime.date.fromisoformat(d['nextDate'])
        day=int(d.get('day',date.day))
        if not 1 <= day <=31: raise ValueError('Día de repetición no válido')
        template=validate('expense',dict(d['template']))
        return dict(nextDate=date.isoformat(),day=day,template=template,active=bool(d.get('active',True)))
    if kind == 'timesheet':
        month=d.get('month','');datetime.date.fromisoformat(month+'-01')
        result={'month':month}
        for key in ['vacations','holidays']:
            days=d.get(key,[])
            if not isinstance(days,list) or len(days)>31: raise ValueError('Días no válidos')
            for day in days:
                datetime.date.fromisoformat(day)
                if day[:7]!=month: raise ValueError('Los días deben pertenecer al mes seleccionado')
            result[key]=sorted(set(days))
        if set(result['vacations']) & set(result['holidays']): raise ValueError('Un día no puede ser festivo y vacaciones a la vez')
        return result
    if kind not in ['profile', 'client', 'invoice', 'expense']: raise ValueError('Tipo no válido')
    required = {'profile':['name','taxid','address'], 'client':['name','taxid','address'], 'invoice':['client','date','description'], 'expense':['supplier','date','description']}[kind]
    for key in required:
        if not str(d.get(key, '')).strip(): raise ValueError('Completa el campo: ' + key)
    if kind == 'client' and d.get('startDate'):
        datetime.date.fromisoformat(d['startDate'])
    if kind == 'client':
        extra=Decimal(str(d.get('extraIrpf',0)))
        if not extra.is_finite() or not 0 <= extra <= 100: raise ValueError('La reserva extra de IRPF debe estar entre 0 y 100%')
        d['extraIrpf']=str(extra)
        if d.get('paymentRule','nextMonth') not in ['nextMonth','days']: raise ValueError('Regla de cobro no válida')
        days=int(d.get('paymentDays',60))
        if not 0 <= days <= 365: raise ValueError('El plazo debe estar entre 0 y 365 días')
        d['paymentDays']=days
    if kind == 'profile':
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',d.get('invoiceColor','#176b52')): raise ValueError('Color no válido')
        logo=d.get('logo','')
        if logo:
            if not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',logo) or len(logo)>700000: raise ValueError('Usa un logo PNG, JPG o WebP de hasta 500 KB')
            raw=base64.b64decode(logo.split(',',1)[1],validate=True)
            if not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff') or (raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')): raise ValueError('Imagen de logo no válida')
    if kind == 'invoice' and d.get('serviceMonth'):
        datetime.date.fromisoformat(d['serviceMonth']+'-01')
    if kind == 'invoice' and d.get('due'):
        datetime.date.fromisoformat(d['due'])
    if kind in ['invoice','expense']:
        if kind == 'expense':
            paid=d.get('paid',True)
            if paid not in [True,False,'true','false']: raise ValueError('Estado de pago no válido')
            d['paid']=paid in [True,'true']
        datetime.date.fromisoformat(d['date'])
        for key in (['quantity','rate','vat','irpf'] if kind == 'invoice' else ['base','vat','deductible','vatDeductible']):
            v = Decimal(str(d.get(key, 0)))
            if not v.is_finite() or v < 0 or v > 100000000: raise ValueError('Importe no válido')
        for key in (['vat','irpf'] if kind == 'invoice' else ['vat','deductible','vatDeductible']):
            if Decimal(str(d[key])) > 100: raise ValueError('Porcentaje fuera de rango')
        if kind == 'invoice':
            lines=d.get('lines', [{key:d.get(key) for key in ['description','unit','quantity','rate']}])
            if not isinstance(lines,list) or not 1 <= len(lines) <= 100: raise ValueError('Añade entre 1 y 100 líneas')
            clean=[]
            for line in lines:
                if not isinstance(line,dict): raise ValueError('Línea no válida')
                if line.get('unit') not in ['días','horas']: raise ValueError('Unidad no válida')
                quantity=Decimal(str(line.get('quantity',0))); rate=Decimal(str(line.get('rate',0)))
                if not quantity.is_finite() or not rate.is_finite() or not 0 < quantity <= 100000000 or not 0 <= rate <= 100000000: raise ValueError('Cantidad o tarifa no válida')
                clean.append(dict(description=str(line.get('description','')).strip(),unit=line['unit'],quantity=str(quantity),rate=str(rate),baseCents=money(quantity*rate)))
            d['lines']=clean
            base=sum(line['baseCents'] for line in clean)
        else: base = money(d['base'])
        vat = int((Decimal(base) * Decimal(str(d['vat'])) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        irpf = int((Decimal(base) * Decimal(str(d.get('irpf',0))) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        d.update(baseCents=base, vatCents=vat, irpfCents=irpf, totalCents=base+vat-irpf)
    return d

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT/'public'), **kwargs)
    def send_json(self, data, status=200):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        if self.path in ['/api/portfolio/template/positions.csv','/api/portfolio/template/transactions.csv']:
            import csv,io
            stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';')
            if self.path.endswith('/positions.csv'):
                writer.writerow(['Nombre','ISIN','Cantidad','Coste total','Valor actual','Moneda'])
                writer.writerow(['Activo de ejemplo','',10,'950,00','1000,00','EUR'])
            else:
                writer.writerow(['Fecha','Tipo','Nombre','ISIN','Cantidad','Importe','Comisiones','Moneda','Referencia'])
                writer.writerow([datetime.date.today().isoformat(),'buy','Activo de ejemplo','',10,'-950,00','1,00','EUR','ejemplo-001'])
            raw=('\ufeff'+stream.getvalue()).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="plantilla-'+('posiciones' if '/positions.' in self.path else 'movimientos')+'.csv"');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            return
        if self.path == '/api/backup':
            with connection() as c: payload=backup_payload(c)
            raw=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="cuenta-clara-copia-'+datetime.date.today().isoformat()+'.json"');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
            return
        if re.fullmatch(r'/api/timesheets/\d{4}-\d{2}/pdf',self.path):
            month=self.path.split('/')[3]
            try:
                datetime.date.fromisoformat(month+'-01')
                with connection() as c:
                    entries=c.execute("SELECT data FROM records WHERE kind='timesheet'").fetchall()
                    profile=c.execute("SELECT data FROM records WHERE kind='profile' LIMIT 1").fetchone()
                record=next((json.loads(r['data']) for r in entries if json.loads(r['data'])['month']==month),{})
                from invoice_pdf import generate_timesheet
                pdf=generate_timesheet(month,record,json.loads(profile['data']) if profile else {})
                self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition',f'attachment; filename="timesheet-{month}.pdf"');self.send_header('Content-Length',str(len(pdf)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(pdf)
            except ValueError as e:return self.send_json({'error':str(e)},400)
            except ImportError:return self.send_json({'error':'Instala las dependencias PDF con requirements.txt'},503)
            return
        if re.fullmatch(r'/api/invoices/\d+/pdf',self.path):
            ident=int(self.path.split('/')[3])
            with connection() as c:
                row=c.execute("SELECT data FROM records WHERE id=? AND kind='invoice'",(ident,)).fetchone()
                profile=c.execute("SELECT data FROM records WHERE kind='profile' LIMIT 1").fetchone()
            if not row: return self.send_json({'error':'Factura no encontrada'},404)
            try:
                from invoice_pdf import generate_invoice
                invoice=json.loads(row['data'])
                pdf=generate_invoice(invoice,json.loads(profile['data']) if profile else invoice['profileSnapshot'])
                self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment; filename="factura-'+invoice['number']+'.pdf"');self.send_header('Content-Length',str(len(pdf)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(pdf)
            except ImportError: return self.send_json({'error':'Instala las dependencias: python -m pip install --target .dependencies -r requirements.txt'},503)
            return
        if self.path == '/api/health':
            return self.send_json({'app':'cuenta-clara'})
        if self.path == '/api/records':
            with connection() as c:
                c.execute('BEGIN IMMEDIATE')
                generate_recurring(c,validate)
                rows=c.execute("SELECT * FROM records WHERE kind NOT LIKE 'deleted_%' ORDER BY id DESC").fetchall()
            return self.send_json([dict(id=r['id'],kind=r['kind'],**json.loads(r['data'])) for r in rows])
        return super().do_GET()
    def do_POST(self):
        if self.path in ['/api/portfolio/inspect','/api/portfolio/preview','/api/portfolio/import']:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''):return self.send_json({'error':'Origen no permitido'},403)
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=6500000:raise ValueError('El CSV debe ocupar como máximo 5 MB')
                payload=json.loads(self.rfile.read(length))
                if self.path.endswith('/inspect'):return self.send_json(inspect_csv(payload))
                with connection() as c:
                    if self.path.endswith('/import'):
                        c.execute('BEGIN IMMEDIATE');result=commit_import(c,payload)
                    else:result=preview_import(c,payload)
                return self.send_json(result,201 if self.path.endswith('/import') else 200)
            except (ValueError,KeyError,TypeError,ArithmeticError) as e:return self.send_json({'error':str(e)},400)
        if self.path == '/api/restore':
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''): return self.send_json({'error':'Origen no permitido'},403)
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0 < length <=50000000: raise ValueError('Copia demasiado grande (máximo 50 MB)')
                payload=json.loads(self.rfile.read(length));records=validate_backup(payload,validate)
                with connection() as c:
                    c.execute('BEGIN IMMEDIATE')
                    safe=backup_payload(c)
                    folder=DB.parent/'backups';folder.mkdir(exist_ok=True)
                    name='antes-restaurar-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'
                    (folder/name).write_text(json.dumps(safe,ensure_ascii=False),encoding='utf-8')
                    c.execute('DELETE FROM records')
                    c.executemany('INSERT INTO records(id,kind,data) VALUES (?,?,?)',[(r['id'],r['kind'],json.dumps(r['data'])) for r in records])
                return self.send_json({'ok':True,'safetyBackup':name,'count':len(records)})
            except (ValueError,KeyError,TypeError,ArithmeticError) as e:return self.send_json({'error':str(e)},400)
        if self.path != '/api/records': return self.send_json({'error':'No encontrado'},404)
        if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''): return self.send_json({'error':'Origen no permitido'},403)
        try:
            length=int(self.headers.get('Content-Length',0))
            if length > 1000000: raise ValueError('Petición demasiado grande')
            body=json.loads(self.rfile.read(length)); kind=body['kind']; d=validate(kind,body['data'])
            with connection() as c:
                c.execute('BEGIN IMMEDIATE')
                if kind=='wealthentry': check_ledger(c,d['planId'],proposed=d)
                if kind == 'timesheet':
                    existing=c.execute("SELECT id,data FROM records WHERE kind='timesheet'").fetchall()
                    for record in existing:
                        if json.loads(record['data'])['month']==d['month']:
                            c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(d),record['id']))
                            return self.send_json({'id':record['id']})
                if kind == 'invoice':
                    client=c.execute('SELECT data FROM records WHERE id=? AND kind=?',(int(d['client']),'client')).fetchone()
                    profile=c.execute("SELECT data FROM records WHERE kind='profile' LIMIT 1").fetchone()
                    if not client or not profile: raise ValueError('Guarda tus datos fiscales y el cliente antes de crear la factura')
                    if json.loads(client['data']).get('paymentRule','nextMonth') == 'nextMonth':
                        d['due']=next_month_due(d['date'])
                    d['clientSnapshot']=json.loads(client['data']); d['profileSnapshot']=json.loads(profile['data'])
                    year=d['date'][:4]
                    numbers=c.execute("SELECT data FROM records WHERE kind IN ('invoice','deleted_invoice')").fetchall()
                    count=max((int(json.loads(row['data'])['number'].rsplit('-',1)[1]) for row in numbers),default=0)+1
                    d['number']=f'{year}-{count:04d}'; d['paid']=False
                if kind in ['profile','cashsettings']: c.execute('DELETE FROM records WHERE kind=?',(kind,))
                row=c.execute('INSERT INTO records(kind,data) VALUES (?,?)',(kind,json.dumps(d)))
            return self.send_json({'id':row.lastrowid},201)
        except (ValueError,KeyError,TypeError,ArithmeticError) as e: return self.send_json({'error':str(e)},400)
    def do_DELETE(self):
        if re.fullmatch(r'/api/portfolio/imports/\d+',self.path):
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''):return self.send_json({'error':'Origen no permitido'},403)
            ident=int(self.path.rsplit('/',1)[1])
            with connection() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT id FROM records WHERE id=? AND kind='portfolioimport'",(ident,)).fetchone()
                if not row:return self.send_json({'error':'Importación no encontrada'},404)
                for record in c.execute("SELECT id,kind,data FROM records WHERE kind IN ('portfoliosnapshot','portfoliotransaction')").fetchall():
                    if json.loads(record['data'])['importId']==ident:c.execute('UPDATE records SET kind=? WHERE id=?',('deleted_'+record['kind'],record['id']))
                c.execute("UPDATE records SET kind='deleted_portfolioimport' WHERE id=?",(ident,))
            return self.send_json({'ok':True})
        try:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''): return self.send_json({'error':'Origen no permitido'},403)
            if not self.path.startswith('/api/records/'): return self.send_json({'error':'No encontrado'},404)
            ident=int(self.path.removeprefix('/api/records/'))
            with connection() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT kind,data FROM records WHERE id=?',(ident,)).fetchone()
                if not row or row['kind'] not in ['invoice','expense','recurring','wealthplan','wealthentry']: return self.send_json({'error':'Registro no encontrado'},404)
                if row['kind']=='wealthplan':
                    if any(int(json.loads(r['data'])['planId'])==ident for r in c.execute("SELECT data FROM records WHERE kind='wealthentry'")):
                        raise ValueError('Este plan tiene movimientos. Puedes pausarlo o eliminar primero sus movimientos')
                    if any(int(json.loads(r['data'])['planId'])==ident for r in c.execute("SELECT data FROM records WHERE kind IN ('portfolioimport','portfoliosnapshot','portfoliotransaction')")):
                        raise ValueError('El plan tiene importaciones de cartera. Elimínalas primero desde el historial de importaciones')
                if row['kind']=='wealthentry': check_ledger(c,int(json.loads(row['data'])['planId']),exclude_id=ident)
                c.execute('UPDATE records SET kind=? WHERE id=?',('deleted_'+row['kind'],ident))
            self.send_json({'ok':True})
        except ValueError as e: self.send_json({'error':str(e)},400)
    def do_PUT(self):
        try:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''): return self.send_json({'error':'Origen no permitido'},403)
            if not self.path.startswith('/api/records/'): return self.send_json({'error':'No encontrado'},404)
            ident=int(self.path.removeprefix('/api/records/'))
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length <= 100000: raise ValueError('Petición no válida')
            body=json.loads(self.rfile.read(length))
            with connection() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT kind,data FROM records WHERE id=?',(ident,)).fetchone()
                if not row: return self.send_json({'error':'Registro no encontrado'},404)
                kind=row['kind']
                if kind not in ['invoice','client','expense','wealthplan','wealthentry'] or body['kind'] != kind: raise ValueError('Tipo no editable')
                old=json.loads(row['data'])
                fields = ['client','date','due','description','unit','quantity','rate','vat','irpf','lines','serviceMonth'] if kind == 'invoice' else ['name','taxid','address','email','startDate','paymentDays','paymentRule']
                if kind == 'client': fields.append('extraIrpf')
                if kind == 'expense':
                    fields=['supplier','description','reference','date','base','vat','deductible','vatDeductible','paid']
                if kind=='wealthplan': fields=['name','startMonth','horizon','annualRate','initial','monthly','target','active']
                if kind=='wealthentry': fields=['action','date','amount','fromBusiness','note']
                changes={key:body['data'][key] for key in fields if key in body['data']}
                d=validate(kind,{**old,**changes})
                if kind=='wealthplan': check_ledger(c,ident,plan_override=d)
                if kind=='wealthentry': check_ledger(c,d['planId'],proposed=d,exclude_id=ident)
                if kind == 'invoice':
                    terms=c.execute("SELECT data FROM records WHERE id=? AND kind='client'",(int(d['client']),)).fetchone()
                    if terms and json.loads(terms['data']).get('paymentRule','nextMonth') == 'nextMonth':
                        d['due']=next_month_due(d['date'])
                if kind == 'invoice' and str(d['client']) != str(old['client']):
                    client=c.execute("SELECT data FROM records WHERE id=? AND kind='client'",(int(d['client']),)).fetchone()
                    if not client: raise ValueError('Cliente no encontrado')
                    d['clientSnapshot']=json.loads(client['data'])
                c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(d),ident))
            self.send_json({'id':ident})
        except (ValueError,KeyError,TypeError,ArithmeticError) as e: self.send_json({'error':str(e)},400)
    def do_PATCH(self):
        try:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''): raise ValueError('Origen no permitido')
            ident=int(self.path.removeprefix('/api/records/'))
            with connection() as c:
                row=c.execute("SELECT kind,data FROM records WHERE id=? AND kind IN ('invoice','expense')",(ident,)).fetchone()
                if not row: raise ValueError('Registro no encontrado')
                d=json.loads(row['data']); d['paid']=not d.get('paid',row['kind']=='expense')
                d['paidDate']=datetime.date.today().isoformat() if d['paid'] else None
                c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(d),ident))
            self.send_json({'ok':True})
        except ValueError as e: self.send_json({'error':str(e)},400)

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PORT','8000'))),Handler)
    print('Tu aplicación está en http://127.0.0.1:8000',flush=True)
    server.serve_forever()
