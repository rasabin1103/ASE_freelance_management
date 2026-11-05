import copy, datetime, json, unittest, urllib.error
import test_business as common
from portfolio_csv import inspect_csv, decimal_value, parse_csv

class PortfolioTests(unittest.TestCase):
    setUp=common.BusinessTests.setUp
    tearDown=common.BusinessTests.tearDown
    request=common.BusinessTests.request
    create=common.BusinessTests.create
    def plan(self):
        return self.create('wealthplan',dict(category='investment',name='Cartera',startMonth='2020-01',initial=0,monthly=0,target=0,annualRate=5,horizon=12))
    def positions(self,plan=None):
        return dict(planId=plan or self.plan(),source='Trade Republic',mode='positions',snapshotDate='2026-01-31',numberFormat='comma',dateFormat='iso',delimiter=';',mapping={'name':'Nombre','isin':'ISIN','quantity':'Cantidad','cost':'Coste','value':'Valor','currency':'Moneda'},csvText='\ufeffNombre;ISIN;Cantidad;Coste;Valor;Moneda\n"Empresa; ejemplo";ES0000000001;2;180,00;220,00;EUR\nETF;IE0000000001;3;250,00;300,00;EUR\n',fileName='cartera.csv')
    def preview(self,payload):return self.request('POST','/api/portfolio/preview',payload)
    def commit(self,payload,preview=None):
        preview=preview or self.preview(payload)
        return self.request('POST','/api/portfolio/import',{**payload,'previewHash':preview['previewHash']})
    def transactions(self,plan=None):
        return dict(planId=plan or self.plan(),source='Trade Republic',mode='transactions',snapshotDate='2026-01-31',numberFormat='comma',dateFormat='dmy',delimiter=';',mapping={'date':'Fecha','type':'Tipo','name':'Activo','quantity':'Títulos','amount':'Importe','fees':'Comisión','reference':'Ref','currency':'Moneda'},csvText='Fecha;Tipo;Activo;Títulos;Importe;Comisión;Ref;Moneda\n01/01/2026;buy;ETF;2;-200,00;1,00;A;EUR\n05/01/2026;dividend;ETF;;5,00;0,00;B;EUR\n')
    def test_positions_preview_commit_duplicate_and_no_ledger(self):
        payload=self.positions();preview=self.preview(payload)
        self.assertTrue(preview['canImport']);self.assertEqual(preview['data'][0]['totalCents'],52000)
        self.assertEqual(len(self.request('GET')),1)
        result=self.commit(payload,preview);self.assertEqual(result['imported'],1)
        records=self.request('GET');self.assertEqual(len(records),3)
        self.assertFalse(any(r['kind']=='wealthentry' for r in records))
        same=self.preview({**payload,'fileName':'otro-nombre.csv'})
        self.assertEqual(same['duplicates'],1);self.assertFalse(same['canImport'])
    def test_replace_snapshot_and_backup_delete(self):
        payload=self.positions();first=self.commit(payload)
        changed={**payload,'csvText':payload['csvText'].replace('220,00','240,00')}
        self.assertTrue(self.preview(changed)['errors'])
        changed['replaceSnapshot']=True;self.commit(changed)
        rows=self.request('GET');self.assertEqual(len([r for r in rows if r['kind']=='portfoliosnapshot']),1)
        self.assertEqual(next(r for r in rows if r['kind']=='portfoliosnapshot')['totalCents'],54000)
        backup=self.request('GET','/api/backup')
        self.request('POST','/api/restore',backup)
        self.request('DELETE','/api/portfolio/imports/'+str(first['id']))
        self.assertEqual(len([r for r in self.request('GET') if r['kind']=='portfoliosnapshot']),1)
    def test_movements_duplicates_overlap_and_conflicts(self):
        payload=self.transactions();self.commit(payload)
        preview=self.preview(payload);self.assertEqual(preview['duplicates'],2)
        payload['csvText']+='06/01/2026;sell;ETF;1;110,00;1,00;C;EUR\n'
        preview=self.preview(payload);self.assertEqual(preview['duplicates'],2);self.assertEqual(len(preview['data']),1)
        self.commit(payload,preview)
        tx=[r for r in self.request('GET') if r['kind']=='portfoliotransaction'];self.assertEqual(len(tx),3)
        self.assertEqual(next(t for t in tx if t['type']=='buy')['amountCents'],-20000)
        altered={**payload,'csvText':payload['csvText'].replace('-200,00','-210,00')}
        self.assertTrue(self.preview(altered)['errors'])
    def test_unknown_types_foreign_currency_and_no_partial_write(self):
        payload=self.transactions();payload['csvText']+='06/01/2026;TRADE;ETF;1;100,00;0,00;C;USD\n'
        preview=self.preview(payload);self.assertFalse(preview['canImport']);self.assertTrue(preview['errors'])
        with self.assertRaises(urllib.error.HTTPError) as caught:self.commit(payload,preview)
        caught.exception.close();self.assertEqual(len(self.request('GET')),1)
        payload['typeMap']={'TRADE':'ignore'};preview=self.preview(payload)
        self.assertTrue(preview['canImport']);self.assertEqual(preview['ignored'],1)
        payload['typeMap']={'TRADE':'buy'};self.assertTrue(self.preview(payload)['errors'])
    def test_identical_rows_without_reference_have_occurrence_keys(self):
        payload=self.transactions();payload['mapping'].pop('reference')
        payload['csvText']='Fecha;Tipo;Activo;Títulos;Importe;Comisión;Ref;Moneda\n01/01/2026;buy;ETF;2;-200,00;1,00;;EUR\n01/01/2026;buy;ETF;2;-200,00;1,00;;EUR\n'
        preview=self.preview(payload);self.assertEqual(len(preview['data']),2)
        self.commit(payload,preview);self.assertEqual(self.preview(payload)['duplicates'],2)
    def test_types_inspection_number_formats_and_lot_aggregation(self):
        info=inspect_csv(self.transactions());self.assertEqual(info['typeValues'],['buy','dividend'])
        self.assertEqual(str(decimal_value('1.234,56','comma')),'1234.56')
        self.assertEqual(str(decimal_value('1,234.56','dot')),'1234.56')
        self.assertRaises(ValueError,decimal_value,'1234.56','comma')
        payload=self.positions();payload['csvText']+='ETF;IE0000000001;1;80,00;100,00;EUR\n'
        preview=self.preview(payload);self.assertEqual(len(preview['positions']),2)
        etf=next(p for p in preview['positions'] if p['name']=='ETF');self.assertEqual(etf['quantity'],'4');self.assertEqual(etf['valueCents'],40000)
    def test_stale_preview_and_plan_deletion(self):
        payload=self.positions();preview=self.preview(payload);self.commit(payload,preview)
        for method,path,body in [('POST','/api/portfolio/import',{**payload,'previewHash':preview['previewHash']}),('DELETE','/api/records/'+str(payload['planId']),None)]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request(method,path,body)
            caught.exception.close()
        self.assertEqual(len(self.request('GET')),3)

if __name__=='__main__':unittest.main()
