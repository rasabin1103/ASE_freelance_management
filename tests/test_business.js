const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
let records=[];
const ctx={by:k=>records.filter(r=>r.kind===k),round:Math.round,eur:n=>String(n/100),esc:String,year:2026,month:0,quarter:0,period:r=>r.date.startsWith('2026'),matchesConcept:()=>true,Intl,Date,console};
vm.createContext(ctx);
for(const name of ['dashboard.js','business.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../public',name),'utf8'),ctx);
records=[{kind:'client',id:1,extraIrpf:5},{kind:'invoice',client:'1',paid:true,date:'2026-01-01',paidDate:'2026-01-01',baseCents:100000,vatCents:21000,irpfCents:15000,totalCents:106000,clientSnapshot:{name:'Cliente'},lines:[{unit:'horas',quantity:10,baseCents:100000}]},{kind:'expense',paid:true,date:'2026-01-02',totalCents:12100,vatCents:2100,vatDeductible:100},{kind:'cashsettings',openingBalance:100,withdrawals:50,vatPaid:100,extraIrpfUsed:20}];
let cash=vm.runInContext('cashData()',ctx);
// Opening 10000 + receipts 106000 - costs 12100 - withdrawal 5000 - tax paid 12000 - remaining VAT 8900 - remaining IRPF reserve 3000.
assert.equal(cash.available,75000);assert.equal(cash.vat,8900);assert.equal(cash.reserve,3000);
records.push({kind:'invoice',client:'1',paid:false,date:'2026-01-01',totalCents:999999,vatCents:21000,baseCents:100000,irpfCents:15000});
assert.equal(vm.runInContext('cashData().available',ctx),75000);
const target=vm.runInContext('calculateGoal(2500,500,20,160,.2)',ctx);
assert.equal(target.base,3750);assert.equal(target.day,187.5);assert.equal(vm.runInContext('calculateGoal(2500,500,0,0,1)',ctx),null);
const today=new Date().toLocaleDateString('sv-SE'),future=vm.runInContext('addDays(isoToday(),10)',ctx);
records=[{kind:'invoice',paid:false,due:future,totalCents:10000},{kind:'invoice',paid:false,due:'2000-01-01',totalCents:99999},{kind:'expense',paid:false,date:future,totalCents:1000},{kind:'expense',paid:true,date:future,totalCents:5000}];
const forecast=vm.runInContext('forecastData()',ctx);assert.equal(forecast[0].income,10000);assert.equal(forecast[0].expenses,1000);
console.log('OK: caja y reservas sin duplicar, pendientes excluidos, objetivos y previsión.');
