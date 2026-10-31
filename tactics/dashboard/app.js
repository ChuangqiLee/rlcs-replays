/* Offline, read-only dashboard. Native JS/SVG; all application copy is bilingual. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const obj = v => v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  const arr = v => Array.isArray(v) ? v : [];
  const records = v => arr(v).filter(x => x && typeof x === 'object' && !Array.isArray(x));
  const num = v => typeof v === 'number' && Number.isFinite(v);
  let lang = 'zh';
  try { lang = localStorage.getItem('dash-language') === 'en' ? 'en' : 'zh'; } catch (_) { /* Storage may be disabled. */ }
  const t = (zh, en) => lang === 'zh' ? zh : en;
  const unknown = () => t('未知', 'Unknown');
  const localized = (row, key) => obj(row)[key + '_' + lang] || obj(row)[key] || '';
  const str = v => v == null || v === '' || ['Unknown','N/A','None','(null)'].includes(v) ? unknown() : String(v);
  const fmt = v => num(v) ? v.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-GB', {maximumFractionDigits:5}) : unknown();
  const value = v => num(v) ? fmt(v) : str(v);
  const state = {data:{}, errors:{}, view:'overview', busy:false, last:null, metric:'', axis:'step', split:'all', selected:null, resultGroup:'', ideaFilter:'all', log:'', logFilter:'', next:Date.now()+30000};
  const palette = ['#77dfef','#d4b4ff','#80e6b1','#ffdc85','#ffacb5','#9bc9ff'];
  const pages = {
    overview:['总览','Overview','阶段、计算资源与研究证据。','Stages, compute resources and research evidence.'],
    dataset:['数据集','Dataset','数据规模、赛季与划分协议。','Dataset size, seasons and split protocol.'],
    ideas:['发现与创新','Findings & ideas','保留原始状态，明确区分证据与候选想法。','Original statuses distinguish evidence from candidate ideas.'],
    results:['实验对比','Experiments','效应量与 95% 置信区间；按任务、划分和单位分组。','Effect estimates with 95% confidence intervals, grouped by task, split and unit.'],
    training:['训练曲线','Training','按运行与数据划分展示指标；悬停或聚焦查看读数。','Metrics by run and split. Hover or focus to inspect readings.'],
    jobs:['作业列表','Jobs','最近三天的记账记录与已分配资源。','Accounting records and allocated resources from the last three days.'],
    session:['会话日志','Session logs','最近 30 份日志，每份保留末尾 20 KB。','The latest 30 logs, with the last 20 KB of each.'],
    paper:['论文','Paper','章节进度、图表与引用核验。','Section progress, figures and citation verification.'],
    literature:['参考文献','Literature','研究参考资料。','Research references.'],
    progress:['研究记录','Progress','项目的阶段结论与下一步计划。','Project conclusions and next steps.']
  };
  const statuses = {
    unknown:['未知','Unknown'], not_started:['未开始','Not started'], in_progress:['进行中','In progress'], running:['运行中','Running'], done:['已完成','Done'], blocked:['阻塞','Blocked'], proposed:['已提出','Proposed'], promising:['有潜力','Promising'], pruned:['已剪枝','Pruned'], selected:['已选定','Selected'], weak:['证据较弱','Weak evidence'], descriptive:['描述性','Descriptive'], pending:['等待中','Pending'], draft:['草稿','Draft'], review:['审核中','In review'], ready:['已就绪','Ready'], fit:['已拟合','Fitted'], ok:['计算成功','Computed'], not_estimable:['无法估计','Not estimable'], passed:['通过','Passed'], pass:['通过','Passed'], failed:['未通过','Failed'], fail:['未通过','Failed'], uncertain:['不确定','Uncertain'], inconclusive:['不确定','Inconclusive'], not_passed:['未通过','Not passed'], confirmed:['通过','Confirmed'], rejected:['未通过','Rejected'],
    RUNNING:['运行中','Running'], PENDING:['排队中','Pending'], COMPLETED:['已完成','Completed'], FAILED:['失败','Failed'], CANCELLED:['已取消','Cancelled'], TIMEOUT:['超时','Timed out'], COMPLETING:['结束中','Completing'], SUSPENDED:['挂起','Suspended'], NODE_FAIL:['节点故障','Node failure'], OUT_OF_MEMORY:['内存不足','Out of memory'], BOOT_FAIL:['启动失败','Boot failure'], DEADLINE:['超过期限','Deadline'], PREEMPTED:['被抢占','Preempted'], REVOKED:['撤销','Revoked'], REQUEUED:['重新排队','Requeued'], RESIZING:['调整资源','Resizing']
  };
  function statusName(s) { const pair = statuses[s]; return pair ? t(...pair) : (s ? `${unknown()} (${s})` : unknown()); }
  // Workflow states (selected/done/pruned/promising) are NOT hypothesis decisions.
  function finding(s) {
    if (['passed','pass','confirmed','通过'].includes(s)) return 'pass';
    if (['failed','fail','not_passed','rejected','未通过'].includes(s)) return 'fail';
    return 'uncertain';
  }
  function badge(s, decision=false) { const c = finding(s); return `<span class="chip ${c}">${esc(decision ? t(...({pass:['通过','Passed'],fail:['未通过','Not passed'],uncertain:['不确定','Uncertain']}[c])) : statusName(s))}</span>`; }
  function dateValue(v) {
    if (num(v)) return new Date(Math.abs(v)<1e11 ? v*1000 : v);
    if (typeof v !== 'string') return null;
    let text = v.trim();
    text = text.replace(/ (CET|CEST|CDT|CST)$/, (_, z) => ({CET:'+01:00',CEST:'+02:00',CDT:'-05:00',CST:'-06:00'}[z]));
    if (!/[T ]\d\d:\d\d/.test(text) || !/(Z|[+-]\d\d:?\d\d)$/.test(text)) return null;
    const d = new Date(text.replace(' ','T')); return Number.isFinite(d.getTime()) ? d : null;
  }
  function time(v) {
    const d = dateValue(v);
    if (!d) return typeof v === 'string' && /^\d{4}-\d\d-\d\d$/.test(v) ? v : unknown();
    const zone = new Intl.DateTimeFormat('en-GB', {timeZone:'Europe/Amsterdam',timeZoneName:'short'}).formatToParts(d).find(p=>p.type==='timeZoneName').value;
    return new Intl.DateTimeFormat(lang === 'zh' ? 'zh-CN' : 'en-GB', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(d)+' '+zone;
  }
  const empty = (zh='暂无数据',en='No data available',detail='') => `<div class="empty"><strong>${esc(t(zh,en))}</strong><p>${esc(detail)}</p></div>`;
  const note = text => text ? `<div class="notice">${esc(text)}</div>` : '';
  const card = (title,body,meta='') => `<section class="card"><div class="card-head"><h2>${esc(title)}</h2><span class="meta">${esc(meta)}</span></div>${body}</section>`;
  const kpi = (label,v,foot='') => `<div class="kpi"><div class="kpi-label">${esc(label)}</div><div class="kpi-value">${esc(value(v))}</div><div class="kpi-foot">${esc(foot)}</div></div>`;
  const table = (headers,rows,cls='') => `<div class="table-wrap"><table class="${cls}"><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const error = name => state.errors[name] ? t('读取失败，保留上次结果：','Read failed; retaining previous data: ')+name : localized(state.data[name],'error');
  function progress(p) {
    if (num(p.progress) && p.progress >= 0 && p.progress <= 100) return p.progress;
    if (['done','completed'].includes(p.status)) return 100;
    if (p.status === 'not_started') return 0;
    return null;
  }
  function phaseRows(rows) {
    return rows.length ? rows.map(p=>{ const n=progress(p), label=`${p.id || ''} ${localized(p,'name')}`.trim(); return `<div class="phase-row"><div class="phase-title"><h3>${esc(label)}</h3>${badge(p.status)}</div><div class="bar ${n==null?'unknown':''}" role="progressbar" aria-label="${esc(label)}" aria-valuemin="0" aria-valuemax="100" ${n==null?`aria-valuetext="${unknown()}"`:`aria-valuenow="${n}"`}><span style="width:${n ?? 0}%"></span></div><div class="meta">${n==null?t('进度未知','Progress unknown'):fmt(n)+'%'}${p.started?' · '+time(p.started):''}${p.finished?' → '+time(p.finished):''}</div><p>${esc(localized(p,'conclusion'))}</p></div>`; }).join('') : empty();
  }
  function overview() {
    const j=obj(state.data.jobs), s=obj(j.summary), ideas=records(obj(state.data.ideas).ideas), counts={pass:0,fail:0,uncertain:0};
    ideas.forEach(i=>counts[finding(i.status)]++);
    const totals=obj(obj(state.data.dataset).totals);
    const highlights=records(obj(state.data.highlights).cards);
    const resourceFoot=t('已分配资源 × 实际已用时长；含 GPU 作业的 CPU。','Allocated resources × actual elapsed time; includes CPUs in GPU jobs.');
    return note(error('jobs'))+`<div class="kpis">${kpi(t('运行中作业','Running jobs'),s.running)}${kpi(t('已完成作业','Completed jobs'),s.completed)}${kpi(t('失败 / 取消 / 超时','Failed / cancelled / timed out'),s.failed)}${kpi(t('其他状态作业','Other job states'),s.other)}</div>`+
      card(t('资源用量','Resource usage'),`<div class="kpis">${kpi(t('CPU·小时','CPU·hours'),s.cpu_hours,t('缺少用量字段的作业：','Jobs missing usage fields: ')+fmt(s.cpu_missing_jobs))}${kpi(t('GPU·小时','GPU·hours'),s.gpu_hours,t('缺少用量字段的作业：','Jobs missing usage fields: ')+fmt(s.gpu_missing_jobs))}</div><p class="muted">${esc(resourceFoot)} ${esc(t('缺失项不计入合计，存在缺失时合计仅为已知部分。','Missing values are excluded; totals are partial when fields are missing.'))}</p><p class="meta">${esc(t('来源：','Source: ')+str(j.source))} · ${esc(t('读取时间：','Fetched: ')+time(j.updated))}${j.cache_file_updated?' · '+esc(t('缓存文件时间：','Cache file timestamp: ')+time(j.cache_file_updated)):''}</p>`)+
      `<div class="grid">${card(t('阶段进度','Stage progress'),phaseRows(records(obj(state.data.phases).phases)),t('未知进度不估算','Unknown progress is not estimated'))}${card(t('发现状态','Finding status'),`<div class="kpis">${['pass','fail','uncertain'].map(k=>kpi(t(...({pass:['通过','Passed'],fail:['未通过','Not passed'],uncertain:['不确定','Uncertain']}[k])),(error('ideas')||!state.data.ideas)?null:counts[k])).join('')}</div><p class="muted">${esc(t('仅将明确的 pass/passed/confirmed、fail/failed/not_passed/rejected 状态计为通过或未通过；selected、done、pruned 等流程状态均计为不确定。','Only explicit pass/passed/confirmed and fail/failed/not_passed/rejected statuses count as decisions. Workflow states such as selected, done and pruned count as uncertain.'))}</p><a href="#/ideas">${t('查看全部发现 →','View all findings →')}</a>`)}</div>`+
      card(t('关键数字','Highlights'),`<div class="kpis">${kpi(t('已解析比赛','Parsed games'),totals.games,'status/dataset.json · totals.games')}${kpi(t('数据帧','Frames'),totals.frames,'status/dataset.json · totals.frames')}${kpi(t('赛季','Seasons'),totals.seasons,'status/dataset.json · totals.seasons')}${highlights.map(h=>kpi(localized(h,'label')||unknown(),h.value,`${t('区间：','CI: ')}${Array.isArray(h.ci)?h.ci.map(value).join(' – '):value(h.ci)} · ${t('来源：','Source: ')}${str(h.source)}`)).join('')}</div>${!highlights.length?`<p class="meta">${t('尚未配置额外卡片。','No additional highlight cards configured.')}</p>`:''}`);
  }
  function jobsView() {
    const data=obj(state.data.jobs), rows=records(data.jobs);
    const headers=[t('作业 ID / 名称','Job ID / name'),t('资源','Resources'),t('状态','State'),t('申请内存 / 峰值 RSS','Requested memory / peak RSS'),t('分区','Partition'),t('节点','Nodes'),t('已用时 / 申请时长','Elapsed / time limit'),t('开始时间','Start'),t('结束时间','End')];
    const body=rows.map(j=>[
      `<span class="mono">${esc(str(j.jobid))}</span><span class="muted">${esc(str(j.name))}</span>`,
      j.resource_type==='GPU'?`GPU × ${fmt(j.gpu_count)}<span class="muted">${t('型号：','Model: ')}${esc(str(j.gpu_model))}${j.gpu_model_source==='partition'?' · '+t('分区映射','partition mapping'):''}</span><span class="muted">CPU × ${fmt(j.alloc_cpus)}</span>`:j.resource_type==='CPU'?`CPU · ${fmt(j.alloc_cpus)} ${t('核','cores')}`:unknown(),
      badge(j.state_code)+`<span class="muted mono">${esc(str(j.state))}</span>`,
      `${esc(str(j.req_mem))} / ${esc(str(j.max_rss))}`,esc(str(j.partition)),esc(str(j.nodes)),`${esc(str(j.elapsed))} / ${esc(str(j.timelimit))}`,esc(time(j.start)),esc(time(j.end))
    ]);
    return note(error('jobs'))+card(t('作业列表','Job list'),`<p class="meta">${esc(t('来源：','Source: ')+str(data.source))} · ${esc(t('读取：','Fetched: ')+time(data.updated))}${data.cache_file_updated?' · '+esc(t('缓存文件：','Cache file: ')+time(data.cache_file_updated)):''}</p><p class="muted">${t('时间：Europe/Amsterdam（冬季 CET，夏季 CEST）。申请内存保留 Slurm 单位：c = 每 CPU，n = 每节点；峰值 RSS 未返回时显示未知。','Times: Europe/Amsterdam (CET in winter, CEST in summer). Requested memory keeps Slurm units: c = per CPU, n = per node. Missing peak RSS is unknown.')}</p>${rows.length?table(headers,body,'jobs-table'):empty('暂无作业记录','No job records',data.source?t('当前来源未返回作业。','The current source returned no jobs.'):t('sacct 与本地缓存均不可用。','Neither sacct nor the local cache is available.'))}`,t('60 秒结果缓存','60-second result cache'));
  }
  function ideasView() {
    const ideas=records(obj(state.data.ideas).ideas), filtered=ideas.filter(i=>state.ideaFilter==='all'||finding(i.status)===state.ideaFilter);
    return `<div class="controls"><label>${t('证据状态','Evidence status')}<select id="idea-filter">${[['all',t('全部','All')],['pass',t('通过','Passed')],['fail',t('未通过','Not passed')],['uncertain',t('不确定','Uncertain')]].map(([k,l])=>`<option value="${k}" ${state.ideaFilter===k?'selected':''}>${l}</option>`).join('')}</select></label></div>`+(filtered.length?filtered.map(i=>`<section class="card finding ${finding(i.status)}"><div class="card-head"><h2>${esc(localized(i,'name')||i.id||unknown())}</h2>${badge(i.status)}</div><p>${esc(localized(i,'latest')||localized(i,'note'))}</p><p class="meta">${t('发现判定：','Finding decision: ')}${badge(i.status,true)}</p><details><summary>${t('动机、方法与参考','Motivation, method and references')}</summary>${['motivation','method','prune_reason'].map(k=>`<p>${esc(localized(i,k))}</p>`).join('')}${records(i.refs||i.inspiration_refs).map(r=>`<p>${link(localized(r,'title'),r.url)}</p>`).join('')}${i.best_metric?`<p>${esc(localized(i.best_metric,'name'))}: ${fmt(i.best_metric.value)}</p>`:''}</details></section>`).join(''):empty());
  }
  function link(label,url) { return /^https?:\/\//i.test(String(url)) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label||url)}</a>` : esc(label||unknown()); }
  function datasetView() {
    const d=obj(state.data.dataset), totals=obj(d.totals), seasons=records(d.seasons), split=obj(d.split_protocol);
    return `<div class="kpis">${kpi(t('比赛','Games'),totals.games)}${kpi(t('帧数','Frames'),totals.frames)}${kpi(t('采样率（帧/秒）','Sampling rate (frames/s)'),d.fps)}${kpi(t('解析失败','Parse failures'),totals.failed)}</div>`+card(t('赛季分布','Seasons'),seasons.length?table([t('赛季','Season'),t('比赛','Games'),t('帧数','Frames'),'1v1','2v2','3v3'],seasons.map(s=>[esc(localized(s,'name')),fmt(s.games),fmt(s.frames),...['1v1','2v2','3v3'].map(m=>fmt(obj(s.modes)[m]))])):empty())+card(t('存储','Storage'),table([t('名称','Name'),t('路径','Path'),'GB'],records(d.storage).map(s=>[esc(localized(s,'name')),esc(str(s.path)),fmt(s.gb)])))+card(t('划分协议与备注','Split protocol and notes'),`<p>${esc(localized(split,'rule'))}</p><p>${esc(localized(split,'notes'))}</p>${arr(localized(d,'notes')).map(n=>`<p>${esc(typeof n==='object'?localized(n,'text'):n)}</p>`).join('')}`);
  }
  const unitLabel = u => ({seconds:t('秒','seconds'),s:t('秒','seconds'),ms:t('毫秒','ms'),'log odds per second':t('对数优势/秒','log odds per second'),dimensionless:t('无量纲','dimensionless'),uu:t('游戏单位 uu','game units (uu)')})[u] || str(u);
  function interval(row) {
    const r=obj(row);
    for (const k of ['ci95','bootstrap_ci95','cr1_ci95','ci']) {
      const ci=r[k]; if (Array.isArray(ci)) return {lo:ci[0],hi:ci[1],method:k};
      if (ci && typeof ci==='object') return {lo:ci.low ?? ci.lower,hi:ci.high ?? ci.upper,method:k};
    }
    return {lo:r.ci_low ?? r.ci_lower,hi:r.ci_high ?? r.ci_upper,method:'ci_low / ci_high'};
  }
  function effectRows() {
    const output=[];
    function walk(v,path,ctx,depth=0) {
      if (depth>20 || !v || typeof v!=='object') return;
      if (Array.isArray(v)) { v.forEach((x,i)=>walk(x,path+'/'+i,ctx,depth+1)); return; }
      const c={...ctx, task:v.task||obj(v.scope).section||ctx.task, split:v.split||obj(v.scope).split||ctx.split, units:localized(v,'units')||localized(v,'unit')||ctx.units, status:v.status||ctx.status};
      const estimate=v.effect_size ?? v.effect ?? v.estimate ?? v.rho;
      const ci=interval(v), hasEffect=['effect_size','effect','estimate','rho'].some(k=>Object.hasOwn(v,k));
      if (hasEffect) {
        output.push({...c, estimate, ...ci, label:localized(v,'label')||localized(v,'name')||localized(v,'method')||path.split('/').slice(-2).join(' / '), source:path, raw:v});
      }
      // Real heterogeneity exports store coefficients and matching CIs in parallel maps.
      if (v.fixed && v.fixed_bootstrap_ci95) Object.entries(obj(v.fixed)).forEach(([key,est])=>{
        const ci=arr(v.fixed_bootstrap_ci95[key]); output.push({...c,estimate:est,lo:ci[0],hi:ci[1],method:'fixed_bootstrap_ci95',label:path.split('/').slice(-1)[0]+' / '+key,source:path+'/fixed/'+key,raw:{}});
      });
      Object.entries(v).forEach(([key,x])=>{if (x && typeof x==='object' && !['fixed','fixed_bootstrap_ci95','slopes','total_slopes','covariance'].includes(key)) walk(x,path+'/'+key,c,depth+1);});
    }
    Object.entries(obj(state.data.results)).forEach(([file,r])=>walk(r,'results/'+file+'.json',{task:null,split:null,units:null,status:null}));
    return output;
  }
  function validEffect(r) { return [r.estimate,r.lo,r.hi].every(num) && r.lo<=r.hi; }
  function legend() { return `<div class="legend">${['pass','fail','uncertain'].map(k=>`<span>${badge(k,true)}</span>`).join('')}</div>`; }
  function forest(rows,unit) {
    if (!rows.length) return empty('没有可绘制的效应量与 95% CI','No plottable effect estimates with 95% CIs',t('缺失、非数值或无效区间保留在表格中。','Missing, non-numeric or invalid intervals remain in the table.'));
    let lo=Math.min(0,...rows.flatMap(r=>[r.lo,r.estimate])), hi=Math.max(0,...rows.flatMap(r=>[r.hi,r.estimate]));
    const pad=(hi-lo||1)*.12;lo-=pad;hi+=pad;
    const w=1000,h=100+rows.length*60,left=300,right=50,bottom=h-65,x=v=>left+(v-lo)/(hi-lo)*(w-left-right);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(t('效应量及 95% 置信区间森林图','Forest plot of effect estimates and 95% confidence intervals'))}">`;
    for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4;svg+=`<path class="grid-line" d="M${x(v)} 15 V${bottom}"/><text x="${x(v)}" y="${bottom+25}" text-anchor="middle">${fmt(v)}</text>`;}
    svg+=`<path class="zero-line" d="M${x(0)} 15 V${bottom}"/><text x="${x(0)}" y="14" text-anchor="middle">0</text>`;
    rows.forEach((r,i)=>{const y=42+i*60,c={pass:'#80e6b1',fail:'#ffacb5',uncertain:'#ffdc85'}[finding(r.status)],tip=`${r.label}\n${t('效应量','Effect')}: ${fmt(r.estimate)} ${unitLabel(unit)}\n95% CI: [${fmt(r.lo)}, ${fmt(r.hi)}]\n${t('状态','Status')}: ${statusName(r.status)}\n${r.source}`;
      svg+=`<text x="${left-20}" y="${y+5}" text-anchor="end">${esc(r.label.length>28?'…'+r.label.slice(-27):r.label)}<title>${esc(r.label)}</title></text><g tabindex="0" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><path d="M${x(r.lo)} ${y}H${x(r.hi)} M${x(r.lo)} ${y-7}v14 M${x(r.hi)} ${y-7}v14" stroke="${c}" stroke-width="3"/><circle cx="${x(r.estimate)}" cy="${y}" r="6" fill="${c}"/><rect x="${x(r.lo)-8}" y="${y-14}" width="${Math.max(16,x(r.hi)-x(r.lo)+16)}" height="28" fill="transparent"/><title>${esc(tip)}</title></g>`;
    });
    svg+=`<text class="axis-title" x="${(left+w-right)/2}" y="${h-10}" text-anchor="middle">${esc(t('效应量','Effect estimate')+' ('+unitLabel(unit)+') · 95% CI')}</text></svg>`;
    return `<div class="chart-scroll">${svg}</div>`;
  }
  function resultsView() {
    const rows=effectRows(), groups=new Map();
    rows.forEach(r=>{
      // Missing units stay separate by metric; do not imply comparability.
      const k=JSON.stringify([r.task||r.source.split('.json/')[0],r.split,r.units,r.units?null:r.source]);
      if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);
    });
    if (!groups.size) return card(t('实验对比','Experiments'),empty('尚无效应量与区间数据','No effect estimates or intervals yet',t('读取 results/*.json 中的结构化效应量与 95% CI。现有描述文字不会转换为数值。','Reads structured effects and 95% CIs from results/*.json. Narrative descriptions are not converted into numbers.'))+legacyResults());
    if (!groups.has(state.resultGroup))state.resultGroup=groups.keys().next().value;
    const selected=groups.get(state.resultGroup), unit=selected[0].units;
    return `<div class="controls"><label>${t('对比组','Comparison group')}<select id="result-group">${[...groups].map(([k,rs])=>`<option value="${esc(k)}" ${k===state.resultGroup?'selected':''}>${esc([str(rs[0].task),str(rs[0].split),unitLabel(rs[0].units),rs[0].units?'':rs[0].source].filter(Boolean).join(' · '))}</option>`).join('')}</select></label></div>`+card(t('效应量与 95% 置信区间','Effects and 95% confidence intervals'),legend()+forest(selected.filter(validEffect),unit)+`<p class="muted">${t('虚线为 0 参考线。颜色仅依据明确的发现状态；fit/ok/done 不代表通过。单位缺失时不合并比较。','Dashed line: zero reference. Colors use explicit finding status only; fit/ok/done do not mean passed. Missing units are not pooled.')}</p>`)+card(t('结果明细','Result details'),table([t('实验 / 来源','Experiment / source'),t('效应量','Effect'),t('95% CI / 区间字段','95% CI / interval field'),t('单位','Unit'),t('发现状态 / 原始状态','Finding / original status')],selected.map(r=>[`${esc(r.label)}<span class="muted">${esc(r.source)}</span>`,fmt(r.estimate),`[${fmt(r.lo)}, ${fmt(r.hi)}]<span class="muted">${esc(r.method)}${!validEffect(r)?' · '+t('无法绘制','Cannot plot'):''}</span>`,esc(unitLabel(r.units)),badge(r.status,true)+`<span class="muted">${esc(statusName(r.status))}</span>`])))+legacyResults();
  }
  function legacyResults() {
    const rows=[];
    Object.entries(obj(state.data.results)).forEach(([file,data])=>{
      (Array.isArray(data)?data:Array.isArray(obj(data).results)?data.results:[data]).forEach(r=>Object.entries(obj(obj(r).metrics)).forEach(([metric,v])=>{
        if(num(v))rows.push([esc(localized(r,'method')||file),esc(str(r.task)),esc(str(r.split)),esc(metric),fmt(v)]);
      }));
    });
    return rows.length?card(t('已有指标记录','Existing metric records'),table([t('方法','Method'),t('任务','Task'),t('划分','Split'),t('指标','Metric'),t('数值','Value')],rows)+`<p class="muted">${t('这些指标未声明效应量与 95% CI，因此仅显示表格。','These metrics do not declare effects and 95% CIs, so they are shown only in the table.')}</p>`):'';
  }
  function splitName(s) { return ({train:t('训练集','Train'),val:t('验证集','Validation'),test:t('测试集','Test'),unspecified:t('未标注划分','Unspecified split')})[s]||s; }
  function axisLabel() { return ({step:t('训练步数（步）','Training step (steps)'),epoch:t('训练轮次（轮）','Epoch (epochs)'),time:t('时间（Europe/Amsterdam · CET/CEST）','Time (Europe/Amsterdam · CET/CEST)')})[state.axis]; }
  function metricLabel(meta, metric) { return localized(obj(obj(meta).metric_labels)[metric],'label')||metric; }
  function lineChart(series, label, unit) {
    const points=series.flatMap(s=>s.points).filter(p=>p[1]!==null);
    if (!points.length) return empty('当前选择没有有效采样点','No valid samples for this selection');
    const w=1000,h=440,left=110,right=35,top=50,bottom=100;
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    points.forEach(([x,y])=>{minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);});
    if(minX===maxX){minX-=.5;maxX+=.5;}if(minY===maxY){minY-=.5;maxY+=.5;}
    const padding=(maxY-minY)*.08;minY-=padding;maxY+=padding;
    const x=v=>left+(v-minX)/(maxX-minX)*(w-left-right),y=v=>top+(maxY-v)/(maxY-minY)*(h-top-bottom);
    const xFmt=v=>state.axis==='time'?new Intl.DateTimeFormat(lang==='zh'?'zh-CN':'en-GB',{timeZone:'Europe/Amsterdam',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(v)):fmt(v);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label+' · '+unitLabel(unit))}"><text class="axis-title" x="${left}" y="25">${esc(label+' ('+unitLabel(unit)+')')}</text>`;
    for(let i=0;i<=4;i++){const v=minY+(maxY-minY)*i/4,xv=minX+(maxX-minX)*i/4;svg+=`<path class="grid-line" d="M${left} ${y(v)}H${w-right}"/><text x="${left-12}" y="${y(v)+5}" text-anchor="end">${fmt(v)}</text><text x="${x(xv)}" y="${h-bottom+30}" text-anchor="middle">${esc(xFmt(xv))}</text>`;}
    svg+=`<path d="M${left} ${top}V${h-bottom}H${w-right}" stroke="#b9c8dc" fill="none"/><text class="axis-title" x="${(left+w-right)/2}" y="${h-18}" text-anchor="middle">${esc(axisLabel())}</text>`;
    series.forEach(s=>{
      let path='',pen=false;
      s.points.forEach(p=>{if(p[1]===null){pen=false;return;}path+=`${pen?'L':'M'}${x(p[0])} ${y(p[1])} `;pen=true;});
      svg+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.5"/>`;
      s.points.filter(p=>p[1]!==null).forEach(p=>{
        const tip=`${s.name}\n${axisLabel()}: ${state.axis==='time'?time(p[0]):fmt(p[0])}\n${label}: ${fmt(p[1])} (${unitLabel(unit)})`;
        svg+=`<circle tabindex="0" cx="${x(p[0])}" cy="${y(p[1])}" r="4" fill="${s.color}" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><title>${esc(tip)}</title></circle>`;
      });
    });
    return `<div class="chart-scroll">${svg}</svg></div><div class="legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div>`;
  }
  function trainingView() {
    const runs=obj(state.data.runs), ids=Object.keys(runs);
    if (!ids.length) return card(t('训练曲线','Training curves'),empty('暂无训练记录','No training records',t('等待 runs/<run>/metrics.jsonl 写入指标与 step、epoch 或带时区的 time。','Waiting for metrics in runs/<run>/metrics.jsonl with step, epoch or timezone-qualified time.')));
    const metrics=[...new Set(ids.flatMap(id=>records(runs[id].rows).flatMap(r=>Object.keys(r).filter(k=>!['step','epoch','time','split'].includes(k)&&num(r[k])))))].sort();
    const splits=[...new Set(ids.flatMap(id=>records(runs[id].rows).map(r=>r.split||'unspecified')))];
    if(state.selected===null)state.selected=new Set(ids);
    if(!metrics.includes(state.metric))state.metric=metrics[0]||'';
    const controls=`<div class="controls"><label>${t('指标','Metric')}<select id="train-metric">${metrics.map(m=>`<option ${m===state.metric?'selected':''}>${esc(m)}</option>`).join('')}</select></label><label>${t('横轴','X axis')}<select id="train-axis">${[['step',t('步数','Step')],['epoch',t('轮次','Epoch')],['time',t('时间','Time')]].map(([k,l])=>`<option value="${k}" ${k===state.axis?'selected':''}>${l}</option>`).join('')}</select></label><label>${t('数据划分','Split')}<select id="train-split"><option value="all">${t('全部（分别绘制）','All (separate series)')}</option>${splits.map(s=>`<option value="${esc(s)}" ${s===state.split?'selected':''}>${esc(splitName(s))}</option>`).join('')}</select></label></div>`;
    const choices=card(t('训练运行','Training runs'),`<div class="controls"><button id="runs-all">${t('全选','Select all')}</button><button id="runs-none">${t('清空','Clear')}</button></div><div class="run-list">${ids.map(id=>`<label><input type="checkbox" data-run="${esc(id)}" ${state.selected.has(id)?'checked':''}> ${esc(localized(runs[id].meta,'name')||id)}<span class="muted"> · ${fmt(records(runs[id].rows).length)} ${t('采样点','samples')}${runs[id].sampled?' · '+t('已抽样','sampled'):''}${runs[id].skipped_lines?' · '+fmt(runs[id].skipped_lines)+' '+t('无效行已跳过','invalid rows skipped'):''}</span></label>`).join('')}</div>`);
    const groups=new Map();let color=0;
    ids.filter(id=>state.selected.has(id)).forEach(id=>{
      const run=runs[id],meta=obj(run.meta),unit=obj(meta.metric_units)[state.metric]||null;
      const key=unit||id; // Unknown units do not imply cross-run comparability.
      if(!groups.has(key))groups.set(key,{unit,label:metricLabel(meta,state.metric),series:[]});
      const bySplit=new Map();
      records(run.rows).forEach(row=>{
        const split=row.split||'unspecified';if(state.split!=='all'&&state.split!==split)return;
        const date=state.axis==='time'?dateValue(row.time):null, xv=state.axis==='time'?(date?date.getTime():null):row[state.axis];
        if(!num(xv))return;
        if(!bySplit.has(split))bySplit.set(split,[]);
        bySplit.get(split).push([xv,num(row[state.metric])?row[state.metric]:null]);
      });
      bySplit.forEach((points,split)=>groups.get(key).series.push({name:(localized(meta,'name')||id)+' / '+splitName(split),points:points.sort((a,b)=>a[0]-b[0]),color:palette[color++%palette.length]}));
    });
    return controls+choices+([...groups.values()].map(g=>card(g.label,lineChart(g.series,g.label,g.unit))).join('')||empty('请选择训练运行','Select a training run'))+`<p class="muted">${t('单位读取 meta.json 的 metric_units。缺失单位显示未知，并按运行分图；缺失指标不连线。悬停或用 Tab 聚焦数据点查看精确读数。','Units come from metric_units in meta.json. Missing units are unknown and plotted separately by run; missing metrics break the line. Hover or Tab to a point for exact readings.')}</p>`;
  }
  function paperView() {
    const p=obj(state.data.paper),sections=records(p.sections),figures=records(p.figures),cit=obj(p.citations);
    return `<div class="kpis">${kpi(t('章节完成','Sections complete'),sections.filter(s=>s.status==='done').length)}${kpi(t('引用已核验','Verified citations'),cit.verified)}${kpi(t('引用总数','Total citations'),cit.total)}</div>`+card(t('投稿目标','Target venue'),`<p>${esc(localized(p,'target')||unknown())}</p><p>${esc(localized(p,'notes'))}</p>`)+card(t('章节进度','Section progress'),phaseRows(sections))+card(t('图表清单','Figures'),figures.length?table([t('编号','ID'),t('标题','Title'),t('状态','Status'),t('路径 / 备注','Path / notes')],figures.map(f=>[esc(str(f.id)),esc(localized(f,'title')||localized(f,'name')),badge(f.status),esc(f.path||localized(f,'notes')||unknown())])):empty());
  }
  function logsView() {
    const logs=obj(state.data.logs),names=Object.keys(logs);
    if (!names.length)return card(t('会话日志','Session logs'),empty());
    if (!names.includes(state.log))state.log=names[0];
    const record=logs[state.log];
    return card(t('会话日志','Session logs'),`<div class="controls"><label>${t('日志文件','Log file')}<select id="log-file">${names.map(n=>`<option ${n===state.log?'selected':''}>${esc(n)}</option>`).join('')}</select></label><label>${t('筛选日志行','Filter log lines')}<input type="search" id="log-filter" value="${esc(state.logFilter)}"></label></div><p class="meta">${esc(time(record.mtime))}${record.truncated?' · '+t('仅显示末尾 20 KB','Last 20 KB only'):''}</p><pre id="log-output">${esc(logLines())}</pre><p class="meta">${t('日志保留原始内容和原始时间格式。','Logs preserve their original content and time format.')}</p>`);
  }
  function logLines() { return String(obj(obj(state.data.logs)[state.log]).tail||'').split('\n').filter(line=>line.toLowerCase().includes(state.logFilter.toLowerCase())).join('\n')||t('没有匹配的日志行','No matching log lines'); }
  function literatureView() {
    const items=records(obj(state.data.literature).items);
    return card(t('参考文献','Literature'),items.length?table([t('标题','Title'),t('期刊 / 会议','Venue'),t('年份','Year')],items.map(r=>[link(localized(r,'title'),String(r.doi_or_url||'').startsWith('10.')?'https://doi.org/'+r.doi_or_url:r.doi_or_url||r.url),esc(localized(r,'venue')),esc(str(r.year))])):empty());
  }
  function progressView() {
    const text=typeof state.data.progress==='string'?state.data.progress:localized(state.data.progress,'text');
    // Source text is escaped, so Markdown HTML and image references never load resources.
    return card(t('研究进度文档','Research progress document'),text?`<pre>${esc(text)}</pre>`:empty(),'PROGRESS.md');
  }
  const renderers={overview,dataset:datasetView,ideas:ideasView,results:resultsView,training:trainingView,jobs:jobsView,session:logsView,paper:paperView,literature:literatureView,progress:progressView};
  function bind(id,key) { const el=$(id);if(el)el.addEventListener('change',e=>{state[key]=e.target.value;render();}); }
  function render() {
    const page=pages[state.view], focused=document.activeElement?.id;
    document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.title=t(page[0],page[1])+' · RLCS';
    $('skip').textContent=t('跳转到内容','Skip to content');$('brand-sub').textContent=t('战术研究工作台','Tactical research workspace');
    $('navigation').setAttribute('aria-label',t('研究导航','Research navigation'));
    $('navigation').innerHTML=Object.entries(pages).map(([k,p],i)=>`<a href="#/${k}" ${k===state.view?'class="active" aria-current="page"':''}><span class="nav-index">${String(i+1).padStart(2,'0')}</span>${esc(t(p[0],p[1]))}</a>`).join('');
    $('sidebar-note').textContent=t('只读监控 · 每 30 秒刷新。隐藏页面时暂停。','Read-only monitor · Refreshes every 30 seconds. Pauses when hidden.');
    $('page-title').textContent=t(page[0],page[1]);$('page-description').textContent=t(page[2],page[3]);$('eyebrow').textContent=t('研究工作台 / RLCS','RESEARCH WORKSPACE / RLCS');
    $('refresh').textContent=t('刷新','Refresh');$('refresh').disabled=state.busy;
    $('language').textContent=lang==='zh'?'English':'中文';$('language').setAttribute('aria-label',t('切换为英语','Switch to Chinese'));
    $('footer').textContent=t('原生 SVG · 无外部依赖 · Europe/Amsterdam（CET / CEST）','Native SVG · No external dependencies · Europe/Amsterdam (CET / CEST)');
    $('sync').textContent=t('主机：','Host: ')+str(obj(state.data.host).host)+' · '+t('最近同步：','Last sync: ')+time(state.last);
    const failures=Object.keys(state.errors);$('connection').textContent=state.busy?t('正在同步…','Syncing…'):failures.length?t('部分数据不可用','Some data unavailable'):t('本地服务已连接','Local service connected');
    const apiNames={overview:['phases','ideas','dataset','highlights'],training:['runs'],session:['logs'],jobs:[],results:['results']};
    const messages=(apiNames[state.view]||[state.view]).map(error).filter(Boolean);
    $('api-notice').hidden=!messages.length;$('api-notice').textContent=messages.join(' · ');
    $('tooltip').hidden=true;
    try{$('view').innerHTML=renderers[state.view]();}catch(e){$('view').innerHTML=empty('无法显示当前数据','Cannot display current data',t('请检查 JSON 字段格式。','Check the JSON field types.'));console.error(e);}
    [['idea-filter','ideaFilter'],['result-group','resultGroup'],['train-metric','metric'],['train-axis','axis'],['train-split','split'],['log-file','log']].forEach(([id,key])=>bind(id,key));
    document.querySelectorAll('[data-run]').forEach(el=>el.addEventListener('change',()=>{el.checked?state.selected.add(el.dataset.run):state.selected.delete(el.dataset.run);render();}));
    if($('runs-all'))$('runs-all').onclick=()=>{state.selected=new Set(Object.keys(obj(state.data.runs)));render();};
    if($('runs-none'))$('runs-none').onclick=()=>{state.selected=new Set();render();};
    if($('log-filter'))$('log-filter').oninput=e=>{state.logFilter=e.target.value;$('log-output').textContent=logLines();};
    document.querySelectorAll('[data-tip]').forEach(el=>{
      const show=e=>{const tip=$('tooltip');tip.textContent=el.dataset.tip;tip.hidden=false;const rect=el.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(e.clientX||rect.left,innerWidth-tip.offsetWidth-12))+'px';tip.style.top=Math.max(8,Math.min((e.clientY||rect.top)+18,innerHeight-tip.offsetHeight-12))+'px';};
      el.addEventListener('pointermove',show);el.addEventListener('focus',show);el.addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});el.addEventListener('blur',()=>{$('tooltip').hidden=true;});
    });
    if(focused&&$(focused))$(focused).focus({preventScroll:true});
  }
  function route(){let v=location.hash.replace(/^#\/?/,'').split(/[/?]/)[0];if(v==='slurm')v='jobs';state.view=Object.hasOwn(pages,v)?v:'overview';render();}
  async function fetchData(name){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{const response=await fetch('/api/'+name,{cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error(String(response.status));state.data[name]=await response.json();delete state.errors[name];}catch(e){state.errors[name]=true;}finally{clearTimeout(timer);}
  }
  async function refresh(){
    if(state.busy)return;state.busy=true;$('refresh').disabled=true;
    await Promise.all(['host','phases','dataset','ideas','highlights','jobs','results','runs','logs','paper','literature','progress'].map(fetchData));
    state.last=obj(state.data.host).time||state.last;state.busy=false;state.next=Date.now()+30000;render();
  }
  $('language').onclick=()=>{lang=lang==='zh'?'en':'zh';try{localStorage.setItem('dash-language',lang);}catch(_){}render();tick();};
  $('refresh').onclick=refresh;window.addEventListener('hashchange',route);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')$('tooltip').hidden=true;});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  function tick(){$('clock').textContent=time(Date.now());if(!document.hidden&&Date.now()>=state.next)refresh();}
  route();refresh();tick();setInterval(tick,1000);
})();
