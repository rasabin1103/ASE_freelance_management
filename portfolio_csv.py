"""Importación local y revisable de posiciones y movimientos de cartera en EUR."""
import csv, datetime, hashlib, io, json, re, unicodedata
from decimal import Decimal, ROUND_HALF_UP

KINDS={'portfoliosnapshot','portfoliotransaction','portfolioimport'}
TYPES={'buy','sell','dividend','interest','fee','deposit','withdrawal'}
ALIASES={
    'date':['fecha','date','datum','datetime','timestamp','bookingdate','executiondate'],
    'name':['nombre','name','asset','assetname','instrument','instrumentname','description','descripcion','wertpapier'],
    'isin':['isin','symbol','ticker','identificador'],
    'quantity':['cantidad','quantity','shares','units','stuck','anzahl','titulos'],
    'value':['valoractual','marketvalue','currentvalue','valuation','valor','value','valoracion'],
    'price':['precioactual','currentprice','marketprice','price','precio','kurs'],
    'cost':['costetotal','totalcost','costbasis','coste','cost','purchasevalue'],
    'averageCost':['costemedio','averagecost','averageprice','buyin','preciomedio'],
    'currency':['moneda','currency','wahrung'],
    'type':['tipo','type','transactiontype','operation','operacion'],
    'amount':['importe','amount','total','cashamount','netamount','netto'],
    'fees':['comision','comisiones','fee','fees','commission'],
    'reference':['referencia','reference','transactionid','id','orderid'],
}
def normalized(value):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower())

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def parse_csv(text,delimiter='auto'):
    if not isinstance(text,str) or not text.strip() or len(text.encode('utf-8'))>5000000:raise ValueError('Selecciona un CSV de texto de hasta 5 MB')
    text=text.lstrip('\ufeff')
    if '\x00' in text:raise ValueError('Codificación no válida; prueba UTF-8 o Windows-1252')
    if delimiter=='auto':
        try:delimiter=csv.Sniffer().sniff(text[:20000],delimiters=',;\t|').delimiter
        except csv.Error:raise ValueError('No se detectó el separador. Selecciónalo manualmente')
    if delimiter not in [',',';','\t','|']:raise ValueError('Separador no válido')
    csv.field_size_limit(1000000)
    try:
        reader=csv.reader(io.StringIO(text,newline=''),delimiter=delimiter,strict=True)
        headers=next(reader)
        headers=[h.strip() for h in headers]
        if not 2<=len(headers)<=80 or any(not h for h in headers) or len(set(headers))!=len(headers):raise ValueError('La primera fila debe tener entre 2 y 80 cabeceras únicas y sin vacíos')
        rows=[]
        for row in reader:
            if not any(v.strip() for v in row):continue
            if len(row)!=len(headers):raise ValueError(f'Fila {reader.line_num}: número de columnas distinto de la cabecera')
            rows.append((reader.line_num,[v.strip() for v in row]))
            if len(rows)>5000:raise ValueError('Máximo 5.000 filas por importación')
    except (csv.Error,StopIteration) as e:raise ValueError('El CSV está vacío o tiene comillas/formato inválido') from e
    if not rows:raise ValueError('El CSV no contiene datos')
    return headers,rows,delimiter

def inspect_csv(payload):
    headers,rows,delimiter=parse_csv(payload.get('csvText'),payload.get('delimiter','auto'))
    suggestions={key:next((h for h in headers if normalized(h) in aliases),'') for key,aliases in ALIASES.items()}
    type_column=payload.get('typeColumn') or suggestions['type']
    type_values=sorted({values[headers.index(type_column)] for _,values in rows}) if type_column in headers else []
    if len(type_values)>100:raise ValueError('La columna de tipo tiene más de 100 valores distintos; revisa su asignación')
    return dict(headers=headers,suggestions=suggestions,delimiter=delimiter,totalRows=len(rows),sample=[dict(line=line,values=values) for line,values in rows[:5]],typeColumn=type_column,typeValues=type_values)

def decimal_value(value,style,empty=False):
    text=str(value).strip().replace('\u00a0','').replace(' ','')
    if empty and not text:return None
    if not text:raise ValueError('Falta un importe o cantidad')
    text=re.sub(r'(?i)EUR','',text).replace('€','')
    negative=text.startswith('(') and text.endswith(')')
    if negative:text='-'+text[1:-1]
    if style=='comma':
        if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?',text):raise ValueError('Número no válido para formato 1.234,56')
        text=text.replace('.','').replace(',','.')
    elif style=='dot':
        if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',text):raise ValueError('Número no válido para formato 1,234.56')
        text=text.replace(',','')
    else:raise ValueError('Formato numérico no válido')
    number=Decimal(text)
    if not number.is_finite() or abs(number)>100000000:raise ValueError('Número fuera del rango admitido')
    return number

def cents(value):return int((value*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def parse_date(value,style):
    text=str(value).strip()
    try:
        if style=='iso':
            if not re.match(r'^\d{4}-\d{2}-\d{2}',text):raise ValueError()
            parsed=datetime.datetime.fromisoformat(text.replace('Z','+00:00')) if len(text)>10 else datetime.datetime.combine(datetime.date.fromisoformat(text),datetime.time())
        else:
            if style not in ['dmy','mdy']:raise ValueError()
            for fmt in (['%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'] if style=='dmy' else ['%m/%d/%Y','%m-%d-%Y']):
                try:parsed=datetime.datetime.strptime(text,fmt);break
                except ValueError:pass
            else:raise ValueError()
    except ValueError:raise ValueError('Fecha no válida para el formato seleccionado')
    if parsed.date()>datetime.date.today():raise ValueError('La fecha no puede ser futura')
    return parsed.date().isoformat(),parsed.isoformat() if len(text)>10 else parsed.date().isoformat()

def validate_portfolio(kind,d):
    plan=int(d['planId']);source=str(d.get('source','')).strip()
    if plan<=0 or not source or len(source)>100:raise ValueError('Plan o plataforma no válidos')
    common=dict(planId=plan,source=source)
    if kind=='portfolioimport':
        if d.get('mode') not in ['positions','transactions']:raise ValueError('Tipo de importación no válido')
        for key in ['imported','duplicates','ignored']:
            if type(d.get(key)) is not int or d[key]<0:raise ValueError('Resumen de importación no válido')
        return {**common,**{k:d[k] for k in ['mode','imported','duplicates','ignored']},'fileName':str(d.get('fileName',''))[:200],'created':str(d.get('created',''))[:60]}
    date=datetime.date.fromisoformat(d['date'])
    if date>datetime.date.today():raise ValueError('Fecha de cartera futura')
    if not re.fullmatch(r'[0-9a-f]{64}',d.get('fingerprint','')):raise ValueError('Identificador de importación no válido')
    common.update(date=date.isoformat(),fingerprint=d['fingerprint'],importId=int(d['importId']))
    if kind=='portfoliosnapshot':
        positions=d.get('positions',[])
        if not isinstance(positions,list) or not 1<=len(positions)<=5000:raise ValueError('Posiciones no válidas')
        for p in positions:
            if p.get('currency')!='EUR' or not p.get('name') or Decimal(str(p['quantity']))<=0:raise ValueError('Posición no válida')
            if not Decimal(str(p['quantity'])).is_finite():raise ValueError('Cantidad no válida')
            if type(p.get('valueCents')) is not int or not 0<=p['valueCents']<=10**12:raise ValueError('Valor de posición no válido')
            if p.get('costCents') is not None and (type(p['costCents']) is not int or not 0<=p['costCents']<=10**12):raise ValueError('Coste de posición no válido')
        return {**common,'positions':positions,'totalCents':sum(p['valueCents'] for p in positions),'costCents':sum(p['costCents'] for p in positions) if all(p.get('costCents') is not None for p in positions) else None}
    if kind=='portfoliotransaction':
        if d.get('type') not in TYPES or d.get('currency')!='EUR':raise ValueError('Movimiento de cartera no válido')
        if any(type(d.get(k)) is not int or abs(d[k])>10**12 for k in ['amountCents','feesCents']):raise ValueError('Importe de movimiento no válido')
        return {**d,**common}
    raise ValueError('Tipo de cartera no válido')

def preview_import(c,payload):
    plan_id=int(payload['planId']);source=str(payload.get('source','')).strip()
    if not source or len(source)>100:raise ValueError('Indica una plataforma o cuenta de hasta 100 caracteres')
    row=c.execute("SELECT data FROM records WHERE id=? AND kind='wealthplan'",(plan_id,)).fetchone()
    if not row or json.loads(row['data'])['category']!='investment':raise ValueError('Selecciona un plan de inversión válido')
    plan=json.loads(row['data']);mode=payload.get('mode')
    if mode not in ['positions','transactions']:raise ValueError('Elige posiciones o movimientos')
    headers,rows,delimiter=parse_csv(payload.get('csvText'),payload.get('delimiter','auto'))
    mapping=payload.get('mapping',{})
    if not isinstance(mapping,dict):raise ValueError('Asignación de columnas no válida')
    for name in mapping.values():
        if name and name not in headers:raise ValueError('La asignación no coincide con las cabeceras')
    indexes={key:headers.index(value) for key,value in mapping.items() if value}
    if mode=='positions' and 'name' not in indexes and 'isin' not in indexes:raise ValueError('Asigna una columna de nombre o identificador del activo')
    if mode=='positions' and ('quantity' not in indexes or ('value' not in indexes and 'price' not in indexes)):raise ValueError('Posiciones: asigna cantidad y valor total o precio actual')
    if mode=='transactions' and ('date' not in indexes or 'amount' not in indexes or ('type' not in indexes and not payload.get('fixedType'))):raise ValueError('Movimientos: asigna fecha, importe y tipo (o selecciona un tipo fijo)')
    style=payload.get('numberFormat','comma');date_style=payload.get('dateFormat','iso')
    snapshot_date,_=parse_date(payload.get('snapshotDate',datetime.date.today().isoformat()),'iso')
    if mode=='positions' and snapshot_date[:7]<plan['startMonth']:raise ValueError('La captura es anterior al inicio del plan; ajusta primero el mes inicial')
    kind='portfoliosnapshot' if mode=='positions' else 'portfoliotransaction'
    existing=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT id,data FROM records WHERE kind=?',(kind,)) if int(json.loads(r['data'])['planId'])==plan_id and json.loads(r['data'])['source'].casefold()==source.casefold()]
    errors=[];warnings=[];ignored=0;positions={};transactions=[];seen={};duplicates=0
    existing_keys={r.get('dedupKey',r['fingerprint']):r for r in existing}
    source_key=source.casefold()
    type_alias={normalized(k):v for k,v in {
        'buy':'buy','compra':'buy','purchase':'buy','kauf':'buy','achat':'buy',
        'sell':'sell','venta':'sell','verkauf':'sell','vente':'sell',
        'dividend':'dividend','dividends':'dividend','dividendo':'dividend','dividende':'dividend',
        'interest':'interest','intereses':'interest','zins':'interest',
        'fee':'fee','fees':'fee','comision':'fee','comisiones':'fee',
        'deposit':'deposit','deposito':'deposit','ingreso':'deposit','cashin':'deposit','transferin':'deposit',
        'withdrawal':'withdrawal','retirada':'withdrawal','cashout':'withdrawal','transferout':'withdrawal',
    }.items()}
    if not isinstance(payload.get('typeMap',{}),dict):raise ValueError('Asignación de tipos no válida')
    refs=0;counts={}
    for line,values in rows:
        def cell(key):return values[indexes[key]] if key in indexes else ''
        try:
            if mode=='transactions':
                raw_type=cell('type')
                custom=payload.get('typeMap',{})
                action=custom.get(raw_type) if raw_type in custom else (type_alias.get(normalized(raw_type)) if 'type' in indexes else payload.get('fixedType'))
                if action=='ignore':ignored+=1;continue
                if action not in TYPES:raise ValueError(f'Tipo «{raw_type}» sin asignar; selecciona su significado o ignóralo expresamente')
            currency=cell('currency').upper() or payload.get('currency','EUR')
            if currency not in ['EUR','€']:raise ValueError('Solo se admiten euros; no se convierten otras monedas automáticamente')
            name=cell('name') or cell('isin');identifier=cell('isin').upper()
            if len(name)>300 or len(identifier)>100:raise ValueError('Nombre o identificador demasiado largo')
            if mode=='positions':
                if not name:raise ValueError('Falta el nombre del activo')
                if 'date' in indexes and cell('date'):
                    rowdate,_=parse_date(cell('date'),date_style)
                    if rowdate!=snapshot_date:raise ValueError('La fecha de la fila no coincide con la fecha de captura seleccionada')
                quantity=decimal_value(cell('quantity'),style)
                if quantity<=0:raise ValueError('La cantidad de la posición debe ser positiva')
                value=decimal_value(cell('value'),style) if 'value' in indexes else decimal_value(cell('price'),style)*quantity
                cost=decimal_value(cell('cost'),style,True) if 'cost' in indexes else (decimal_value(cell('averageCost'),style,True)*quantity if 'averageCost' in indexes and cell('averageCost') else None)
                if value<0 or (cost is not None and cost<0):raise ValueError('El valor y el coste no pueden ser negativos')
                key=identifier or name.casefold()
                part=dict(name=name,identifier=identifier,quantity=str(quantity),valueCents=cents(value),costCents=cents(cost) if cost is not None else None,currency='EUR')
                if key in positions:
                    old=positions[key];old['quantity']=str(Decimal(old['quantity'])+quantity);old['valueCents']+=part['valueCents'];old['costCents']=old['costCents']+part['costCents'] if old['costCents'] is not None and part['costCents'] is not None else None
                else:positions[key]=part
            else:
                date,timestamp=parse_date(cell('date'),date_style)
                if date[:7]<plan['startMonth']:raise ValueError('El movimiento es anterior al inicio del plan')
                quantity=decimal_value(cell('quantity'),style,True) if 'quantity' in indexes else None
                if action in ['buy','sell'] and (not name or quantity is None or quantity<=0):raise ValueError('Compras y ventas necesitan activo y cantidad positiva')
                amount=decimal_value(cell('amount'),style)
                fees=decimal_value(cell('fees'),style,True) if 'fees' in indexes else None
                reference=cell('reference')
                if len(reference)>200:raise ValueError('Referencia demasiado larga')
                sign=-1 if action in ['buy','fee','withdrawal'] else 1
                tx=dict(planId=plan_id,source=source,date=date,timestamp=timestamp,type=action,name=name,identifier=identifier,quantity=str(quantity) if quantity is not None else '',amountCents=sign*abs(cents(amount)),feesCents=abs(cents(fees)) if fees is not None else 0,currency='EUR',reference=reference)
                fp=digest({k:v for k,v in tx.items() if k!='source'}|{'source':source_key})
                if reference:
                    refs+=1;key=digest([plan_id,source_key,'reference',reference])
                else:
                    counts[fp]=counts.get(fp,0)+1;key=digest([fp,counts[fp]])
                tx.update(fingerprint=fp,dedupKey=key,line=line)
                if key in seen:
                    if seen[key]!=fp:raise ValueError('Una referencia identifica dos movimientos distintos en el archivo')
                    duplicates+=1;continue
                seen[key]=fp
                old=existing_keys.get(key)
                if old:
                    if old['fingerprint']!=fp:raise ValueError('Ya existe un movimiento diferente con esa referencia; revisa el archivo antes de importarlo')
                    duplicates+=1;continue
                transactions.append(tx)
        except (ValueError,TypeError,ArithmeticError) as e:errors.append(dict(line=line,message=str(e)))
    replace_ids=[];data=[]
    if mode=='positions' and positions:
        ordered=sorted(positions.values(),key=lambda p:(p['identifier'],p['name'].casefold()))
        fp=digest(dict(planId=plan_id,source=source_key,date=snapshot_date,positions=ordered))
        previous=[r for r in existing if r['date']==snapshot_date]
        if any(r['fingerprint']==fp for r in previous):duplicates=1
        else:
            if previous:
                if payload.get('replaceSnapshot') is True:
                    replace_ids=[r['id'] for r in previous];warnings.append('Se sustituirá la captura anterior de esta plataforma y fecha; se conserva en la copia interna')
                else:errors.append(dict(line=0,message='Ya existe otra captura para esta plataforma y fecha. Activa «Sustituir captura» para reemplazarla completa'))
            snapshot=dict(planId=plan_id,source=source,date=snapshot_date,positions=ordered,totalCents=sum(p['valueCents'] for p in ordered),costCents=sum(p['costCents'] for p in ordered) if all(p['costCents'] is not None for p in ordered) else None,fingerprint=fp)
            try:validate_portfolio('portfoliosnapshot',{**snapshot,'importId':1});data=[snapshot]
            except (ValueError,TypeError,ArithmeticError) as e:errors.append(dict(line=0,message=str(e)))
        if len(positions)<len(rows):warnings.append('Las filas del mismo identificador se agrupan como lotes de un activo; revisa las cantidades y valores totales')
        warnings.append('La captura debe incluir toda la cartera que quieras representar para esta plataforma en esa fecha; no se fusiona con capturas anteriores')
    if mode=='transactions':
        data=transactions
        if refs<len(rows)-ignored:warnings.append('Sin referencia única, los movimientos se comparan por contenido y repetición. Para períodos solapados con operaciones idénticas, usa referencias o importa el historial completo')
        warnings.append('Los importes se guardan con el signo del tipo asignado. Las comisiones se muestran aparte y no se vuelven a restar del importe. Los movimientos no proporcionan cotizaciones actuales ni modifican la caja o las aportaciones del plan')
    if errors:errors=errors[:100]
    state=dict(data=data,duplicates=duplicates,replaceIds=replace_ids,errors=errors,mode=mode,planId=plan_id,source=source,ignored=ignored)
    return dict(**state,previewHash=digest(state),rows=len(rows),delimiter=delimiter,warnings=warnings,positions=list(positions.values()) if mode=='positions' else [],canImport=not errors and bool(data))

def commit_import(c,payload):
    preview=preview_import(c,payload)
    if not preview['canImport']:raise ValueError('No hay datos nuevos válidos para importar. Revisa la vista previa')
    if payload.get('previewHash')!=preview['previewHash']:raise ValueError('La vista previa ha cambiado; vuelve a revisarla antes de confirmar')
    metadata=dict(planId=preview['planId'],source=preview['source'],mode=preview['mode'],fileName=str(payload.get('fileName',''))[:200],created=datetime.datetime.now().isoformat(),imported=len(preview['data']),duplicates=preview['duplicates'],ignored=preview['ignored'])
    metadata=validate_portfolio('portfolioimport',metadata)
    batch=c.execute("INSERT INTO records(kind,data) VALUES ('portfolioimport',?)",(json.dumps(metadata),)).lastrowid
    for ident in preview['replaceIds']:c.execute("UPDATE records SET kind='deleted_portfoliosnapshot' WHERE id=?",(ident,))
    kind='portfoliosnapshot' if preview['mode']=='positions' else 'portfoliotransaction'
    for data in preview['data']:
        data={k:v for k,v in data.items() if k!='line'};data['importId']=batch
        data=validate_portfolio(kind,data)
        c.execute('INSERT INTO records(kind,data) VALUES (?,?)',(kind,json.dumps(data)))
    return dict(id=batch,imported=len(preview['data']),duplicates=preview['duplicates'],ignored=preview['ignored'])
