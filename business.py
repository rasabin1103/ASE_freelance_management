"""Recurrencias y copias portables para la aplicación local."""
import calendar, datetime, hashlib, json

def today(): return datetime.date.today()

def next_occurrence(date, day):
    year,month=(date.year+1,1) if date.month==12 else (date.year,date.month+1)
    return datetime.date(year,month,min(day,calendar.monthrange(year,month)[1]))

def generate_recurring(c, validate):
    count=0
    for row in c.execute("SELECT id,data FROM records WHERE kind='recurring'").fetchall():
        rule=json.loads(row['data'])
        if not rule.get('active',True): continue
        date=datetime.date.fromisoformat(rule['nextDate'])
        while date<=today():
            if count>=1200: raise ValueError('Demasiados gastos a generar; revisa las fechas de recurrencia')
            expense=validate('expense',{**rule['template'],'date':date.isoformat(),'paid':False,'recurringId':row['id']})
            c.execute("INSERT INTO records(kind,data) VALUES ('expense',?)",(json.dumps(expense),))
            date=next_occurrence(date,rule['day']);count+=1
        rule['nextDate']=date.isoformat()
        c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(rule),row['id']))
    return count

def backup_payload(c):
    records=[dict(id=r['id'],kind=r['kind'],data=json.loads(r['data'])) for r in c.execute('SELECT * FROM records ORDER BY id')]
    canonical=json.dumps(records,sort_keys=True,ensure_ascii=False).encode()
    return dict(app='cuenta-clara-backup',version=1,created=datetime.datetime.now().isoformat(),checksum=hashlib.sha256(canonical).hexdigest(),records=records)

def validate_backup(payload, validate):
    if not isinstance(payload,dict) or payload.get('app')!='cuenta-clara-backup' or payload.get('version')!=1: raise ValueError('Usa una copia completa de Cuenta Clara, no la exportación de registros')
    records=payload.get('records')
    if not isinstance(records,list) or len(records)>100000: raise ValueError('Copia no válida')
    canonical=json.dumps(records,sort_keys=True,ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=payload.get('checksum'): raise ValueError('La copia está incompleta o ha sido modificada')
    ids=set();numbers=set();profiles=0;months=set()
    allowed={'profile','client','invoice','expense','timesheet','recurring','deleted_invoice','deleted_expense','deleted_recurring','cashsettings','wealthplan','wealthentry','deleted_wealthplan','deleted_wealthentry'}
    from portfolio_csv import KINDS as PORTFOLIO_KINDS
    allowed.update(PORTFOLIO_KINDS);allowed.update('deleted_'+kind for kind in PORTFOLIO_KINDS)
    for row in records:
        if not isinstance(row,dict) or type(row.get('id')) is not int or row['id']<=0 or row['id'] in ids or row.get('kind') not in allowed or not isinstance(row.get('data'),dict): raise ValueError('Registro de copia no válido')
        ids.add(row['id']);kind=row['kind'].removeprefix('deleted_');d=row['data']
        normalized=validate(kind,dict(d))
        if kind=='wealthplan':
            row['data']=normalized
            d=normalized
        if kind=='invoice':
            import re
            if not re.fullmatch(r'\d{4}-\d{4,}',d.get('number','')) or d['number'] in numbers: raise ValueError('Numeración de facturas no válida')
            numbers.add(d['number']);validate('profile',dict(d['profileSnapshot']));validate('client',dict(d['clientSnapshot']))
        if kind=='profile': profiles+=1
        if kind=='timesheet':
            if d['month'] in months: raise ValueError('Calendarios duplicados')
            months.add(d['month'])
    if profiles>1: raise ValueError('Datos fiscales duplicados')
    clients={r['id'] for r in records if r['kind']=='client'}
    for row in records:
        if row['kind'] in ['invoice','deleted_invoice'] and int(row['data']['client']) not in clients: raise ValueError('Falta un cliente de una factura')
    from wealth import validate_ledger
    plans={r['id']:r['data'] for r in records if r['kind']=='wealthplan'}
    for row in records:
        if row['kind']=='wealthentry' and row['data']['planId'] not in plans: raise ValueError('Falta el plan de un movimiento')
    for ident,plan in plans.items():
        validate_ledger(plan,[dict(r['data'],id=r['id']) for r in records if r['kind']=='wealthentry' and r['data']['planId']==ident])
    batches={r['id']:r['data'] for r in records if r['kind']=='portfolioimport'}
    for row in records:
        if row['kind'] in PORTFOLIO_KINDS:
            d=row['data'];plan=plans.get(d['planId'])
            if not plan or plan['category']!='investment':raise ValueError('Falta el plan de inversión de una importación')
            if row['kind']!='portfolioimport' and (d['importId'] not in batches or batches[d['importId']]['planId']!=d['planId']):raise ValueError('Falta el historial de una importación de cartera')
    return records
