"""Validación de planes personales y movimientos reales, sin asientos automáticos."""
import datetime, json, re
from decimal import Decimal, ROUND_HALF_UP

def amount(value):
    number=Decimal(str(value))
    if not number.is_finite() or not 0 <= number <= 100000000:
        raise ValueError('Introduce un importe entre 0 y 100.000.000 €')
    return int((number*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def annual_rate(data):
    if 'annualRate' in data:
        rate=Decimal(str(data['annualRate']))
    else:
        monthly=Decimal(str(data.get('monthlyRate',0)))
        if not monthly.is_finite() or not -100 <= monthly <=100: raise ValueError('Rentabilidad mensual antigua no válida')
        rate=((1+monthly/100)**12-1)*100
    if not rate.is_finite() or not -100 <= rate <=1000000: raise ValueError('La rentabilidad anual debe estar entre -100 % y 1.000.000 %')
    return str(rate)

def migrate_annual_rates(c):
    count=0
    for row in c.execute("SELECT id,data FROM records WHERE kind IN ('wealthplan','deleted_wealthplan')").fetchall():
        data=json.loads(row['data'])
        if 'annualRate' not in data or 'monthlyRate' in data:
            data['annualRate']=annual_rate(data) if data['category']=='investment' else '0'
            data.pop('monthlyRate',None)
            c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),row['id']))
            count+=1
    return count

def validate_wealth(kind,data):
    if kind=='wealthplan':
        category=data.get('category')
        if category not in ['saving','investment']: raise ValueError('Tipo de plan no válido')
        name=str(data.get('name','')).strip()
        if not name or len(name)>100: raise ValueError('El nombre debe tener entre 1 y 100 caracteres')
        month=str(data.get('startMonth',''))
        if not re.fullmatch(r'\d{4}-\d{2}',month): raise ValueError('Mes inicial no válido')
        date=datetime.date.fromisoformat(month+'-01')
        if not 1900 <= date.year <= 2100: raise ValueError('El año debe estar entre 1900 y 2100')
        horizon=int(data.get('horizon',12))
        if not 1<=horizon<=120: raise ValueError('La proyección admite entre 1 y 120 meses')
        rate=annual_rate(data) if category=='investment' else '0'
        active=data.get('active',True)
        if active not in [True,False,'true','false']: raise ValueError('Estado del plan no válido')
        cents={key+'Cents':amount(data.get(key,0)) for key in ['initial','monthly','target']}
        return dict(category=category,name=name,startMonth=month,horizon=horizon,annualRate=rate,active=active in [True,'true'],**{key:str(Decimal(value)/100) for key,value in [(k,cents[k+'Cents']) for k in ['initial','monthly','target']]},**cents)
    if kind=='wealthentry':
        plan_id=int(data['planId'])
        if plan_id<=0: raise ValueError('Plan no válido')
        action=data.get('action')
        if action not in ['contribution','withdrawal','valuation']: raise ValueError('Movimiento no válido')
        date=datetime.date.fromisoformat(data['date'])
        if date>datetime.date.today(): raise ValueError('Los movimientos reales no pueden tener fecha futura')
        cents=amount(data.get('amount',0))
        if action!='valuation' and cents==0: raise ValueError('El importe debe ser mayor que cero')
        from_business=data.get('fromBusiness',False)
        if from_business not in [True,False,'true','false']: raise ValueError('Origen del dinero no válido')
        note=str(data.get('note','')).strip()
        if len(note)>500: raise ValueError('La nota admite hasta 500 caracteres')
        return dict(planId=plan_id,action=action,date=date.isoformat(),amount=str(Decimal(cents)/100),amountCents=cents,fromBusiness=action!='valuation' and from_business in [True,'true'],note=note)
    raise ValueError('Registro de patrimonio no válido')

def validate_ledger(plan,entries):
    balance=plan['initialCents']
    for entry in sorted(entries,key=lambda e:(e['date'],e.get('id',10**15))):
        if entry['date'][:7]<plan['startMonth']: raise ValueError('El movimiento es anterior al inicio del plan')
        if entry['action']=='valuation':
            if plan['category']!='investment': raise ValueError('Las valoraciones solo se registran en inversiones')
            balance=entry['amountCents']
        elif entry['action']=='contribution': balance+=entry['amountCents']
        else:
            balance-=entry['amountCents']
            if balance<0: raise ValueError('La retirada supera el saldo registrado del plan en esa fecha')

def check_ledger(c,plan_id,proposed=None,exclude_id=None,plan_override=None):
    row=c.execute("SELECT data FROM records WHERE id=? AND kind='wealthplan'",(plan_id,)).fetchone()
    if not row: raise ValueError('Plan no encontrado')
    plan=plan_override or json.loads(row['data'])
    entries=[dict(json.loads(r['data']),id=r['id']) for r in c.execute("SELECT id,data FROM records WHERE kind='wealthentry'") if int(json.loads(r['data'])['planId'])==plan_id and r['id']!=exclude_id]
    if proposed: entries.append(dict(proposed,id=exclude_id or 10**15))
    validate_ledger(plan,entries)
