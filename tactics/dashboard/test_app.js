/* Dependency-free data/render regression tests. No browser or network access. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {addEventListener(){},setAttribute(){},focus(){},style:{}});
  return elements.get(id);
};
const context = vm.createContext({
  document:{getElementById:element,addEventListener(){},querySelectorAll(){return [];},documentElement:{}},
  localStorage:{getItem(){return 'zh';}},window:{addEventListener(){}},console,Intl,Date,URL,
});
const code = fs.readFileSync(path.join(__dirname,'app.js'),'utf8').replace(
  'route();refresh();tick();setInterval(tick,1000);',
  'globalThis.test = {state, renderers, effectRows, finding, validEffect, localized, interval, time, progress, lineChart, setLang(v){lang=v;}};'
);
vm.runInContext(code,context);
const t = context.test;
for (const status of ['selected','done','pruned','fit','ok','promising','descriptive'])assert.equal(t.finding(status),'uncertain');
assert.equal(t.finding('passed'),'pass');assert.equal(t.finding('not_passed'),'fail');
assert.equal(t.progress({status:'running'}),null);assert.equal(t.progress({status:'done'}),100);
assert.equal(t.progress({progress:125,status:'running'}),null);
assert.equal(t.localized({name_zh:'中文',name_en:'English',name:'fallback'},'name'),'中文');
t.setLang('en');assert.equal(t.localized({name_en:'English',name:'fallback'},'name'),'English');
assert.equal(t.localized({name:'fallback'},'name'),'fallback');
assert.match(t.time('2026-07-15T12:00:00-05:00'),/19:00:00 CEST/);
assert.match(t.time('2026-10-31T08:47:05-05:00'),/14:47:05 CET/);
assert.equal(t.time('Unknown'),'Unknown');
for (const lang of ['zh','en']) {
  t.setLang(lang);
  for(const [page,render] of Object.entries(t.renderers))assert.equal(typeof render(),'string',page);
}
t.state.data.results = Object.fromEntries(['p5_latency','boost_mediation','pushup_heterogeneity'].map(name=>[name,JSON.parse(fs.readFileSync(path.join(root,'dashx',name+'.json'),'utf8'))]));
let rows=t.effectRows();
assert.equal(rows.filter(r=>r.source.includes('p5_latency') && t.validEffect(r)).length,9);
assert.equal(rows.filter(r=>r.source.includes('boost_mediation') && t.validEffect(r)).length,6);
assert.ok(rows.some(r=>r.method==='fixed_bootstrap_ci95'&&t.validEffect(r)));
assert.ok(rows.some(r=>r.source.includes('/comparisons/')&&!t.validEffect(r)));
assert.ok(rows.filter(r=>r.source.includes('p5_latency')).every(r=>r.task==='P5a only'));
assert.ok(rows.filter(r=>r.source.includes('boost_mediation')).every(r=>r.units===null));
assert.match(t.renderers.results(),/zero-line/);
t.state.data.results = {sample:[{estimate:0,ci95:[-1,1],units:'seconds',status:'passed',label:'<script>alert(1)</script>'},{estimate:2,ci95:[3,1],units:'seconds',status:'failed'}]};
assert.match(t.renderers.results(),/&lt;script&gt;/);assert.doesNotMatch(t.renderers.results(),/<script>/);
assert.equal(t.effectRows().filter(t.validEffect).length,1);
assert.equal(t.validEffect({estimate:3,lo:0,hi:2}),true); // A valid bootstrap CI need not contain the point estimate.
t.state.axis='step';
const chart=t.lineChart([{name:'Test',color:'#77dfef',points:[[0,1],[1,null],[2,0]]}],'loss','dimensionless');
assert.match(chart,/Training step \(steps\)/);assert.match(chart,/dimensionless/);assert.match(chart,/data-tip=/);
assert.match(chart,/d="M[^L"]+M/); // Missing metric breaks the line.
t.state.data.runs={test:{meta:{metric_units:{loss:'dimensionless'}},rows:[{step:0,split:'train',loss:0},{step:1,split:'val',loss:1}]}};
assert.match(t.renderers.training(),/Train/);assert.match(t.renderers.training(),/Validation/);
// Text contrast checks: all UI text colors on the lightest panel background.
function luminance(hex){const a=hex.match(/\w\w/g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return a[0]*.2126+a[1]*.7152+a[2]*.0722;}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
const css=fs.readFileSync(path.join(__dirname,'style.css'),'utf8');
const colors=Object.fromEntries([...css.matchAll(/--([\w-]+):\s*#([\da-f]{6})/g)].map(m=>[m[1],m[2]]));
for(const name of ['text','muted','accent','pass','fail','uncertain'])assert.ok(contrast(colors[name],'21354b')>=4.5,name);
assert.ok(contrast(colors.border,colors.panel2)>=3);
assert.ok(contrast('ffe1a4','342b1b')>=4.5);
assert.doesNotMatch(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),/<(?:script|link)[^>]+(?:src|href)="https?:/);
console.log('Frontend checks passed: bilingual/empty states, real effect exports, CI validity, escaping, training gaps and WCAG AA text/control contrast.');
