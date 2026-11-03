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
  'globalThis.test = {state, renderers, resultGroups, effectRows, finding, validEffect, localized, sourceText, interval, time, progress, lineChart, setLang(v){lang=v;}};'
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
assert.match(t.time('2026-07-15T12:00:00-05:00'),/18:00:00 CET/);
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
// A full-data RQ4 summary should be visible on first load even when older
// experiments arrive first. A user's existing comparison selection must survive.
t.state.data.results = {
  legacy:{task:'Legacy comparison',task_zh:'既有对比',task_en:'Legacy comparison',label:'Legacy estimate',label_zh:'既有效应量',label_en:'Legacy estimate',units:'dimensionless',estimate:0,ci95:[-1,1]},
  dash_full_summary:{rq4:{task:'RQ4 full summary',task_zh:'RQ4 全量摘要',task_en:'RQ4 full summary',units:'dimensionless',rows:[
    {label:'Extracted habit',label_zh:'摘录习惯',label_en:'Extracted habit',rho:0,ci95:[-1,1]}
  ]}}
};
const summaryGroups=t.resultGroups();
const legacyGroup=[...summaryGroups].find(([,group])=>group.some(row=>row.source.startsWith('results/legacy.json')))[0];
const rq4Group=[...summaryGroups].find(([,group])=>group.some(row=>row.source.startsWith('results/dash_full_summary.json/rq4/')))[0];
assert.equal(summaryGroups.keys().next().value,legacyGroup,'The fixture must put the legacy result first');
t.state.resultGroup=null;
assert.match(t.renderers.results(),/Extracted habit/);
assert.equal(t.state.resultGroup,rq4Group,'Default to the full-data RQ4 group');
t.state.resultGroup=legacyGroup;
t.renderers.results();
assert.equal(t.state.resultGroup,legacyGroup,'Keep a manually selected comparison');
t.setLang('zh');t.renderers.results();
assert.equal(t.state.resultGroup,legacyGroup,'Language switching must retain the selected comparison');
t.setLang('en');
delete t.state.data.results.dash_full_summary;
t.state.resultGroup=rq4Group;
t.renderers.results();
assert.equal(t.state.resultGroup,legacyGroup,'Fall back when a previously selected summary is absent');
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
// Running card must show both resource types, purposes and honest remaining times.
t.state.data.jobs={source:'synthetic-test',excluded_jobs:2,project_root:'/project',jobs:[
  {jobid:'cpu-test',name:'cpu',state_code:'RUNNING',resource_type:'CPU',alloc_cpus:16,elapsed_seconds:60,timelimit:'01:00:00',workdir:'/project'},
  {jobid:'gpu-test',name:'gpu',state_code:'COMPLETING',resource_type:'GPU',gpu_count:2,alloc_cpus:8,elapsed_seconds:30,timelimit:'UNLIMITED',workdir:'/project'}
]};
t.state.data.job_purposes={purposes:{cpu:{zh:'测试用途',en:'Test purpose'}}};
for(const language of ['zh','en']){
  t.setLang(language);
  for(const view of ['overview','jobs']){
    const rendered=t.renderers[view]();
    assert.match(rendered,/cpu-test/);assert.match(rendered,/gpu-test/);
    assert.match(rendered,/0:59:00/);assert.match(rendered,/CPU/);assert.match(rendered,/GPU × 2/);
    assert.match(rendered,language==='en'?/Test purpose/:/测试用途/);
    assert.match(rendered,language==='en'?/Remaining/:/剩余/);
    assert.ok(rendered.indexOf('cpu-test')<rendered.indexOf('Resource usage')||view==='jobs'||language==='zh');
    if(language==='en')assert.doesNotMatch(rendered,/[\u3000-\u9fff]/);
  }
}
t.state.data.paper={sections:[],pdf:{available:true,pages:7,compiled:'2026-10-31T12:00:00Z'}};
t.setLang('en');assert.match(t.renderers.paper(),/<iframe[^>]+src="\/paper.pdf"/);
assert.match(t.renderers.paper(),/13:00:00 CET/);
// The local data snapshot has PDFs and manuscript status even when TeX sources
// are unavailable. Source statistics stay unknown; the supplied status survives.
t.state.data.paper={
  sections:[],figures:[],pdf:{available:false},status:'in_progress',
  snapshot_updated:'2026-11-01T08:10:00+01:00',main_pages:7,supplement_pages:9,
  cluster_commit:'2d041a4',manuscript_commit:'7c3e20c',
  note_zh:'论文继续修订；q 值按置换下限如实报告。',
  note_en:'Manuscript revision continues; q values are reported at the permutation floor.',
  notes_zh:'源码统计暂缺；状态来自论文快照。',
  notes_en:'Source statistics are unavailable; status comes from the manuscript snapshot.',
  snapshot_source_zh:'PROGRESS.md 与论文状态记录',snapshot_source_en:'PROGRESS.md and manuscript status record'
};
for(const language of ['zh','en']){
  t.setLang(language);
  const rendered=t.renderers.paper();
  assert.match(rendered,language==='en'?/Manuscript status snapshot/:/论文状态快照/);
  assert.match(rendered,language==='en'?/No manuscript sources/:/暂无论文源码/);
  assert.ok(rendered.includes(t.state.data.paper['note_'+language]));
  assert.ok(rendered.includes(t.state.data.paper['notes_'+language]));
  assert.match(rendered,language==='en'?/Main pages<\/div><div class="kpi-value">7<\/div>/:/正文页数<\/div><div class="kpi-value">7<\/div>/);
  assert.match(rendered,language==='en'?/Supplement pages<\/div><div class="kpi-value">9<\/div>/:/补充材料页数<\/div><div class="kpi-value">9<\/div>/);
  assert.match(rendered,/2d041a4/);assert.match(rendered,/7c3e20c/);
  assert.match(rendered,/08:10:00 CET/);
  assert.doesNotMatch(rendered,/\[(?:untranslated|未翻译)\]/);
  if(language==='en')assert.doesNotMatch(rendered,/[\u3000-\u9fff\uff00-\uffef]/);
}
t.setLang('en');
t.state.data.progress={text_en:'# Heading\n- One\n<script>bad()</script>\n![image](https://invalid.example/image.png)'};
assert.match(t.renderers.progress(),/<h1>Heading<\/h1>/);
assert.doesNotMatch(t.renderers.progress(),/<script>|<img/);
// GET responses from the real service have no bilingual siblings on legacy
// status fields and contain mixed-language Markdown and raw server logs.
const live=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/live-api-20261101.json'),'utf8')).data;
const untouched=JSON.stringify(live),warnings=[];
context.console={warn(...args){warnings.push(args.join(' '));}};
t.state.data=live;t.state.selected=null;t.state.metric='loss';
for(const language of ['zh','en']){
  t.setLang(language);
  for(const [page,render] of Object.entries(t.renderers)){
    const html=render();
    assert.doesNotMatch(html,/\[(?:untranslated|未翻译)\]|Cannot display current data|无法显示当前数据/,language+'/'+page);
    if(language==='en')assert.doesNotMatch(html,/[\u3000-\u9fff\uff00-\uffef]/,page+' English includes SVG/hidden/attribute text');
  }
  const completed=live.jobs.jobs.find(j=>j.jobid==='41105069');
  assert.equal(completed.state_code,'COMPLETED');assert.match(t.renderers.jobs(),/41105069/);
  assert.match(t.renderers.training(),/<circle[^>]+data-tip=/);
  assert.match(t.renderers.results(),/zero-line/);
  assert.match(t.renderers.paper(),/<iframe[^>]+src="\/paper.pdf"/);
  assert.doesNotMatch(t.renderers.progress(),/English translation unavailable/);
  for(const job of live.jobs.jobs.filter(j=>j.state_code==='RUNNING')){
    const html=t.renderers.overview();
    assert.ok(html.includes(job.jobid));assert.ok(html.includes(job.name));
    assert.ok(html.includes(live.job_purposes.purposes[job.name][language]));
  }
}
assert.deepEqual(warnings,[],'Legacy API rendering must not emit translation warnings');
assert.equal(JSON.stringify(live),untouched,'Rendering must not mutate source evidence');
t.setLang('en');
assert.equal(t.localized({name:'New unmapped 中文'},'name'),'[untranslated]');
assert.equal(t.localized({name:'RLCS 2025',name_en:'Explicit name'},'name'),'Explicit name');
assert.equal(t.sourceText({tail:'new 中文 log'},'tail'),'[Source line 1: English translation unavailable]');
t.setLang('zh');assert.equal(t.sourceText({tail:'new 中文 log'},'tail'),'new 中文 log');
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
