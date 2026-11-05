import unittest, tempfile, pathlib, threading, urllib.request, urllib.error, json
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server, business

class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.original=server.DB
        server.DB=pathlib.Path(self.folder.name)/'test.db'
        with server.connection() as c:c.execute('CREATE TABLE records (id INTEGER PRIMARY KEY,kind TEXT,data TEXT)')
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();server.DB=self.original;self.folder.cleanup()
    def request(self,method,path='/api/records',data=None):
        request=urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}'+path,method=method,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:return json.load(response)
    def create(self,kind,data):return self.request('POST',data=dict(kind=kind,data=data))['id']
    def expense(self):return dict(supplier='TGSS',description='Cuota',reference='',date='2026-01-31',base='100',vat='0',deductible='100',vatDeductible='0',paid=False)
    def test_recurring_is_idempotent_and_preserves_day_31(self):
        import datetime
        original=business.today;business.today=lambda:datetime.date(2026,3,31)
        try:
            self.create('recurring',dict(nextDate='2026-01-31',day=31,template=self.expense()))
            rows=self.request('GET');generated=[r for r in rows if r['kind']=='expense']
            self.assertEqual(sorted(r['date'] for r in generated),['2026-01-31','2026-02-28','2026-03-31'])
            self.assertTrue(all(r['paid'] is False for r in generated))
            self.assertEqual(len(self.request('GET')),4)
            rule=next(r for r in rows if r['kind']=='recurring')
            self.request('DELETE','/api/records/'+str(rule['id']))
            self.assertEqual(len(self.request('GET')),3)
        finally:business.today=original
    def test_backup_restore_validates_and_preserves_deleted(self):
        expense=self.create('expense',self.expense())
        self.create('timesheet',dict(month='2026-10',vacations=['2026-10-05'],holidays=['2026-10-12']))
        self.request('DELETE','/api/records/'+str(expense))
        backup=self.request('GET','/api/backup')
        self.create('cashsettings',dict(openingBalance='500'))
        broken={**backup,'checksum':'bad'}
        with self.assertRaises(urllib.error.HTTPError):self.request('POST','/api/restore',broken)
        self.assertEqual(len(self.request('GET')),2)
        result=self.request('POST','/api/restore',backup)
        self.assertTrue(result['ok']);self.assertEqual(len(self.request('GET')),1)
        self.assertTrue((server.DB.parent/'backups'/result['safetyBackup']).exists())
        recovered=self.request('GET','/api/backup')
        self.assertEqual(recovered['records'],backup['records'])
    def test_expense_payment_state(self):
        ident=self.create('expense',self.expense())
        self.request('PATCH','/api/records/'+str(ident))
        expense=self.request('GET')[0]
        self.assertTrue(expense['paid']);self.assertIsNotNone(expense['paidDate'])

if __name__=='__main__':unittest.main()
