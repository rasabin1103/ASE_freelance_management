import unittest, urllib.error
from test_business import BusinessTests
import server

class WealthTests(unittest.TestCase):
    setUp=BusinessTests.setUp
    tearDown=BusinessTests.tearDown
    request=BusinessTests.request
    create=BusinessTests.create
    def plan(self,category='investment',initial='1000'):
        return dict(category=category,name='Plan de prueba',startMonth='2026-01',initial=initial,monthly='100',target='5000',monthlyRate='2',horizon=12,active=True)
    def entry(self,plan,action='contribution',amount='100',date='2026-01-15',cash=False):
        return dict(planId=plan,action=action,amount=amount,date=date,fromBusiness=cash,note='Prueba')
    def test_create_edit_and_restore_plans_and_entries(self):
        ident=self.create('wealthplan',self.plan())
        eid=self.create('wealthentry',self.entry(ident,cash=True))
        updated={**self.entry(ident,cash=True),'amount':'250'}
        self.request('PUT','/api/records/'+str(eid),dict(kind='wealthentry',data=updated))
        entry=next(r for r in self.request('GET') if r['id']==eid)
        self.assertEqual(entry['amountCents'],25000)
        self.assertTrue(entry['fromBusiness'])
        backup=self.request('GET','/api/backup')
        self.request('DELETE','/api/records/'+str(eid))
        self.request('POST','/api/restore',backup)
        self.assertEqual(self.request('GET','/api/backup')['records'],backup['records'])
    def test_withdrawal_integrity_and_plan_deletion(self):
        ident=self.create('wealthplan',self.plan('saving','0'))
        eid=self.create('wealthentry',self.entry(ident))
        self.create('wealthentry',self.entry(ident,'withdrawal','80','2026-01-16'))
        for action in [lambda:self.request('DELETE','/api/records/'+str(eid)),lambda:self.request('DELETE','/api/records/'+str(ident)),lambda:self.create('wealthentry',self.entry(ident,'withdrawal','50','2026-01-17'))]:
            with self.assertRaises(urllib.error.HTTPError) as caught:action()
            self.assertEqual(caught.exception.code,400);caught.exception.close()
        self.assertEqual(len(self.request('GET')),3)
    def test_investment_valuation_is_not_business_transfer(self):
        ident=self.create('wealthplan',self.plan())
        eid=self.create('wealthentry',self.entry(ident,'valuation','1300',cash=True))
        entry=next(r for r in self.request('GET') if r['id']==eid)
        self.assertFalse(entry['fromBusiness'])
        self.assertEqual(entry['amountCents'],130000)
    def test_invalid_inputs(self):
        ident=self.create('wealthplan',self.plan('saving'))
        cases=[('wealthplan',{**self.plan(),'monthlyRate':'NaN'}),('wealthplan',{**self.plan(),'monthlyRate':'-101'}),('wealthplan',{**self.plan(),'monthly':'-10'}),('wealthplan',{**self.plan(),'horizon':121}),('wealthentry',self.entry(ident,'valuation')),('wealthentry',self.entry(ident,date='2050-01-01')),('wealthentry',self.entry(ident,date='2025-12-01'))]
        for kind,data in cases:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.create(kind,data)
            self.assertEqual(caught.exception.code,400);caught.exception.close()
    def test_annual_rate_and_legacy_backup(self):
        data=self.plan()
        data.pop('monthlyRate')
        data['annualRate']='12'
        ident=self.create('wealthplan',data)
        plan=next(r for r in self.request('GET') if r['id']==ident)
        self.assertEqual(plan['annualRate'],'12')
        self.assertNotIn('monthlyRate',plan)
        self.request('PUT','/api/records/'+str(ident),dict(kind='wealthplan',data={'annualRate':'8'}))
        self.assertEqual(self.request('GET')[0]['annualRate'],'8')
        from wealth import annual_rate
        from decimal import Decimal
        self.assertEqual(Decimal(annual_rate({'monthlyRate':'1'})),Decimal('12.682503013196972066120100'))
        import business,hashlib,json
        backup=self.request('GET','/api/backup')
        backup['records'][0]['data'].pop('annualRate')
        backup['records'][0]['data']['monthlyRate']='1'
        backup['checksum']=hashlib.sha256(json.dumps(backup['records'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        normalized=business.validate_backup(backup,server.validate)
        self.assertIn('annualRate',normalized[0]['data'])
        self.assertNotIn('monthlyRate',normalized[0]['data'])

if __name__=='__main__':unittest.main()
