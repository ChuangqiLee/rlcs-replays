/* Offline rendering audit using the real status/results and sacct snapshots.
 * No dependencies, network, SSH, or Slurm. Python is used ONLY for the existing
 * server's read-only PSV parser and local auxiliary-file readers.
 * Raw whitelist: code fields (path, field, id, job); filesystem paths and exact
 * job/partition/node/run IDs. Prose, labels, tooltips and ARIA text are checked.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const codeRoot = path.resolve(__dirname, '..');
const root = path.resolve(process.env.DASH_DATA_ROOT || codeRoot);
const cjk = /[\u3000-\u9fff\uff00-\uffef]/;
const decode = text => String(text).replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (_, x) =>
  x[0] === '#' ? String.fromCodePoint(parseInt(x.slice(x[1].toLowerCase()==='x'?2:1),x[1].toLowerCase()==='x'?16:10)) :
    ({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:' '})[x.toLowerCase()]);
// Minimal HTML tree, not an HTML-stripping-only mock: innerHTML/textContent,
// hidden nodes and actual index.html chrome participate in the audit.
class Element {
  constructor(tag='div', attrs={}) {this.tag=tag;this.attrs=attrs;this.children=[];this.style={};this.hidden=Object.hasOwn(attrs,'hidden');}
  set innerHTML(html) {this.children=parse(String(html));}
  get innerHTML() {return this.children.map(n=>typeof n==='string'?n:n.outerHTML).join('');}
  get outerHTML() {return `<${this.tag}>${this.innerHTML}</${this.tag}>`;}
  set textContent(text) {this.children=[String(text)];}
  get textContent() {return this.children.map(n=>typeof n==='string'?n:n.textContent).join('');}
  setAttribute(k,v) {this.attrs[k]=String(v);}
  get id() {return this.attrs.id;}
  addEventListener() {}
  focus() {}
}
function parse(html) {
  const parent=new Element(), stack=[parent], voids=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  const tokens=html.match(/<!--[\s\S]*?-->|<![^>]*>|<[^>"']*(?:(?:"[^"]*"|'[^']*')[^>"']*)*>|[^<]+/g)||[];
  for(const token of tokens) {
    if(token.startsWith('<!'))continue;
    if(token.startsWith('</')) {const tag=token.slice(2,-1).trim().toLowerCase();for(let i=stack.length-1;i>0;i--)if(stack[i].tag===tag){stack.length=i;break;}continue;}
    if(token[0]!=='<') {stack[stack.length-1].children.push(decode(token));continue;}
    const name=token.match(/^<([\w-]+)/);if(!name)continue;
    const attrs={};
    for(const match of token.slice(name[0].length).matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[match[1]]=decode(match[2]??match[3]??match[4]??'');
    const node=new Element(name[1].toLowerCase(),attrs);stack[stack.length-1].children.push(node);
    if(!voids.has(node.tag)&&!token.endsWith('/>'))stack.push(node);
  }
  return parent.children;
}
function* nodes(parent) {yield parent;for(const child of parent.children)if(typeof child!=='string')yield* nodes(child);}
const tree=new Element('root');tree.innerHTML=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const element=id=>[...nodes(tree)].find(n=>n.id===id)||null;
const warnings=[],errors=[];
const context=vm.createContext({document:{getElementById:element,addEventListener(){},querySelectorAll(){return [];},documentElement:[...nodes(tree)].find(n=>n.tag==='html')},
  localStorage:{getItem(){return 'en';},setItem(){}},window:{addEventListener(){}},Intl,Date,URL,
  console:{warn(...x){warnings.push(x.join(' '));},error(...x){errors.push(x.join(' '));}}});
const source=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
const marker='route();refresh();tick();setInterval(tick,1000);';assert.ok(source.includes(marker));
vm.runInContext(source.replace(marker,'globalThis.audit={state,render,renderers,resultGroups,resultPanel,localized,statusName,terms,setLang(v){lang=v;},tick};'),context);
const api=context.audit;
const translations=JSON.parse(fs.readFileSync(path.join(__dirname,'i18n_map.json'),'utf8'));
for(const [key,pair] of Object.entries(api.terms)) {
  assert.equal(pair.label_zh,translations[key].zh,'Chinese generated term: '+key);
  assert.equal(pair.label_en,translations[key].en,'English generated term: '+key);
}
const data={};
for(const name of ['phases','dataset','ideas','highlights','paper','job_purposes'])data[name]=JSON.parse(fs.readFileSync(path.join(root,'status',name+'.json'),'utf8'));
data.results=Object.fromEntries(fs.readdirSync(path.join(root,'results')).filter(n=>n.endsWith('.json')).map(n=>[n.slice(0,-5),JSON.parse(fs.readFileSync(path.join(root,'results',n),'utf8'))]));
const auxiliary=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-B','-c',`
import json
from dashboard import server
with open('dashx/sacct_dash.psv', encoding='utf-8') as handle:
    rows=server.parse_jobs(handle.read())
print(json.dumps(server.json_safe(dict(jobs=dict(jobs=rows,summary=server.job_summary(rows),source='dashx/sacct_dash.psv',updated='2026-10-31T23:47:00+00:00'),paper=server.paper(),runs=server.runs(),logs=server.logs(),literature=server.literature(),progress=server.progress())),ensure_ascii=False))
`],{cwd:codeRoot,encoding:'utf8',env:{...process.env,DASH_DATA_ROOT:root,DASH_OFFLINE:'1',PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:64*1024*1024}));
Object.assign(data,auxiliary,{host:{host:'snapshot',time:'2026-10-31T23:47:00+00:00'}});
assert.ok(data.jobs.jobs.length,'Real PSV must contain jobs');
api.state.data=data;api.state.last=data.host.time;api.state.next=Infinity;
const rawKinds=new Set(['path','field','id','job']);
function visible(node) {
  if(node.hidden||['script','style','noscript','head'].includes(node.tag))return '';
  if(node.tag==='code'&&rawKinds.has(node.attrs['data-i18n-raw']))return '';
  let out='';
  for(const key of ['aria-label','aria-valuetext','title','alt','placeholder','data-tip'])if(node.attrs[key])out+=' '+node.attrs[key];
  for(const child of node.children)out+=' '+(typeof child==='string'?child:visible(child));
  return out;
}
const rawNames=new Set(data.jobs.jobs.flatMap(j=>[j.name,j.partition,j.nodes,j.jobid,j.gpu_model]).filter(Boolean));
rawNames.add('snapshot');
function checkedText(htmlOrNode) {
  let node=htmlOrNode;
  if(typeof node==='string'){node=new Element();node.innerHTML=htmlOrNode;}
  let text=visible(node);
  // Exact known opaque names only; do not whitelist whole tables/cards/pre blocks.
  for(const name of rawNames) {
    const escaped=name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    text=text.replace(new RegExp('(?<![\\p{L}\\p{N}_])'+escaped+'(?![\\p{L}\\p{N}_])','gu'),'');
  }
  return text.replace(/(?:https?:\/\/|(?:[\w*.-]+\/)+)[\w./*:<>=+-]*/g,'');
}
const report=[];
let originalGroupKeys=null;
function audit(label,node,language) {
  const text=checkedText(node);
  assert.doesNotMatch(text,/\[(?:untranslated|未翻译)\]/,label+' has a missing translation');
  if(language==='en')assert.ok(!cjk.test(text),label+' contains CJK: '+(text.match(/.{0,50}[\u3000-\u9fff\uff00-\uffef].{0,80}/)||[])[0]);
  else {
    const letters=(text.match(/[A-Za-z]/g)||[]).length;
    const chars=text.replace(/\s/g,'').length;
    return {label,letters,chars,ratio:chars?100*letters/chars:0};
  }
}
for(const language of ['en','zh']) {
  api.setLang(language);
  for(const page of Object.keys(api.renderers)) {
    api.state.view=page;api.render();api.tick();
    assert.equal(errors.length,0,'Render errors: '+errors.join('\n'));
    const row=audit(language+'/'+page,tree,language);if(row)report.push(row);
    audit(language+'/document-title',context.document.title,language);
  }
  // The production resultPanel renders every group, including off-screen tables
  // and SVG titles/tips. Avoid rebuilding a many-thousand-option selector for
  // each panel; the full selector was already checked in render() above.
  const groups=api.resultGroups();let chars=0,letters=0;
  if(originalGroupKeys)assert.deepEqual([...groups.keys()],originalGroupKeys,'Language must not alter comparison groups');
  else originalGroupKeys=[...groups.keys()];
  for(const [key,rows] of groups) {
    const row=audit(language+'/results/'+key,api.resultPanel(rows),language);
    if(row){chars+=row.chars;letters+=row.letters;}
  }
  if(language==='zh')report.push({label:'zh/all result groups',letters,chars,ratio:100*letters/chars});
  console.log(`${language}: ${Object.keys(api.renderers).length} views, ${groups.size} result groups, ${data.jobs.jobs.length} real jobs passed.`);
}
assert.equal(warnings.length,0,'Snapshot translation warnings:\n'+warnings.slice(0,30).join('\n'));
// Fail closed for unseen live prose, including mixed-language originals/arrays.
const beforeWarnings=warnings.length;
api.setLang('en');assert.equal(api.localized({name:'新增中文说明'},'name'),'[untranslated]');
assert.equal(api.localized({name:'plain English'},'name'),'plain English');
assert.equal(api.localized({name_zh:'只有中文'},'name'),'[untranslated]');
assert.equal(api.localized({name_en:'污染的 English'},'name'),'[untranslated]');
assert.deepEqual(Array.from(api.localized({notes:['English','中文']},'notes')),['English','[untranslated]']);
api.setLang('zh');assert.equal(api.localized({name:'New English prose'},'name'),'[未翻译]');
assert.equal(api.localized({name:'中文说明'},'name'),'中文说明');
assert.equal(api.localized({name_en:'English only'},'name'),'[未翻译]');
assert.equal(api.localized({name:'RMST'},'name'),'RMST');
assert.equal(api.localized({name:'中文 with English prose'},'name'),'[未翻译]');
for(const language of ['en','zh']){api.setLang(language);assert.equal(api.statusName('未知新状态'),language==='en'?'Unknown':'未知');}
assert.ok(warnings.length>beforeWarnings,'Missing translations must warn');
const warningCount=warnings.length;api.setLang('en');api.localized({name:'新增中文说明'},'name');assert.equal(warnings.length,warningCount,'Duplicate warning is suppressed');
console.log('Chinese Latin-letter ratios (after exact ID/path/job exclusions; technical terms remain):');
for(const row of report)console.log(`  ${row.label}: ${row.ratio.toFixed(2)}% (${row.letters}/${row.chars})`);
console.log('i18n audit passed; unseen-prose fallback and console warnings verified.');
