/* Read-only dashboard. No build step; optional ECharts/marked with offline fallbacks. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const arr = value => Array.isArray(value) ? value : [];
  const obj = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const objectRows = value => arr(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));
  const recordMap = value => Object.fromEntries(Object.entries(obj(value)).filter(([,item]) => item && typeof item === 'object' && !Array.isArray(item)));
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const number = value => numeric(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:4}) : '—';
  const millions = value => numeric(value) ? value / 1e6 : null;
  const pct = value => numeric(value) ? Math.max(0, Math.min(100, value)) : 0;
  const signed = value => numeric(value) ? (value > 0 ? '+' : '') + number(value) : '—';
  const palette = ['#22d3ee','#a78bfa','#2dd4bf','#60a5fa','#fbbf24','#f472b6','#fb923c'];
  const views = {
    overview:['总览','研究进度 / OVERVIEW','研究全貌、关键指标与最新进展。'],
    dataset:['数据集','研究基础 / DATASET','五个赛季的比赛数据、模式分布与划分协议。'],
    ideas:['创新点','研究探索 / IDEAS','记录每个想法的动机、证据与取舍。'],
    results:['实验对比','实验评估 / RESULTS','在相同任务与数据划分下，对比基线与研究方法。'],
    training:['训练曲线','实验过程 / TRAINING','叠加训练记录，追踪每一个指标的变化。'],
    slurm:['SLURM','计算资源 / SLURM','当前作业队列与最近两天的执行记录。'],
    session:['会话日志','运行记录 / SESSION LOGS','最近 30 份日志，每份保留末尾 20 KB。'],
    paper:['论文','研究产出 / PAPER','章节进度、图表准备与引用核验。'],
    progress:['PROGRESS.md','研究记录 / PROGRESS','项目进度文档，与研究现场保持同步。']
  };
  const statusNames = {not_started:'未开始',in_progress:'进行中',running:'进行中',done:'已完成',blocked:'已阻塞',proposed:'已提出',promising:'有潜力',pruned:'已剪枝',selected:'已选定',pending:'等待中',draft:'草稿',review:'审核中',ready:'已就绪',unknown:'待更新',RUNNING:'运行中',PENDING:'排队中',COMPLETED:'已完成',FAILED:'失败',CANCELLED:'已取消',TIMEOUT:'超时',COMPLETING:'结束中',SUSPENDED:'已挂起',NODE_FAIL:'节点故障',OUT_OF_MEMORY:'内存不足'};
  const state = {data:{},errors:{},view:'overview',busy:false,charts:[],ideaFilter:'all',resultGroup:'',resultMetric:'',trainMetric:'',trainAxis:'step',trainSplit:'all',selectedRuns:null,logFile:'',logFilter:'',lastUpdate:null};
  const dateFormatter = new Intl.DateTimeFormat('zh-CN', {timeZone:'Europe/Amsterdam',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  const clockFormatter = new Intl.DateTimeFormat('zh-CN', {timeZone:'Europe/Amsterdam',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  function dateValue(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      const date = new Date(Math.abs(value) < 1e11 ? value * 1000 : value);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    if (typeof value !== 'string' || !value.trim()) return null;
    let text = value.trim();
    // Legacy CET strings are explicit UTC+1; unzoned wall-clock values are ambiguous.
    if (/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)? CET$/.test(text)) text = text.replace(' ', 'T').replace(' CET', '+01:00');
    if (!/[T ]\d\d:\d\d/.test(text) || !/(?:Z|[+-]\d\d:?\d\d)$/.test(text)) return null;
    const date = new Date(text);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  function formatTime(value) {
    const date = dateValue(value);
    if (date) return dateFormatter.format(date).replace(/\//g, '-') + ' CET';
    if (typeof value === 'string' && /^\d{4}-\d\d-\d\d$/.test(value)) return value;
    return value ? '时间待规范（需时区）' : '—';
  }
  function formatLogs(text) {
    return String(text || '').replace(/\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b/g, value => formatTime(value));
  }
  function badge(status) { const key = String(status || 'unknown'); return `<span class="chip ${esc(key.replace(/[^a-zA-Z_]/g,''))}">${esc(statusNames[key] || key)}</span>`; }
  function empty(title, detail, symbol = '∅') { return `<div class="empty"><span class="empty-symbol" aria-hidden="true">${esc(symbol)}</span><h3>${esc(title)}</h3><p>${esc(detail || '')}</p></div>`; }
  function card(title, body, extra = '', span = '') { return `<section class="card ${span}"><div class="card-head"><h2>${esc(title)}</h2>${extra}</div>${body}</section>`; }
  function kpi(label, value, foot, color = '', index = '', text = false) { return `<div class="card kpi ${color}"><div class="kpi-label">${esc(label)}<span class="kpi-index">${esc(index)}</span></div><div class="kpi-value${text ? ' text' : ''}">${value}</div><div class="kpi-foot">${foot}</div></div>`; }
  function progressBar(value) { return `<div class="bar" role="progressbar" aria-label="完成进度" aria-valuenow="${pct(value)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct(value)}%"></i></div>`; }
  function notice(value) { return value ? `<div class="notice">${esc(value)}</div>` : ''; }
  function apiError(name) { return state.errors[name] || obj(state.data[name]).error || ''; }
  function table(headers, rows) { return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`; }
  function safeHref(value) {
    const link = String(value || '').trim();
    if (/^(https?:\/\/|mailto:)/i.test(link) && !/[\u0000-\u0020]/.test(link)) return link;
    if (/^#\//.test(link)) return link;
    return '';
  }
  function link(label, url) { const href = safeHref(url); return href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label); }
  function paperProgress() {
    const sections = objectRows(obj(state.data.paper).sections);
    return sections.length ? sections.reduce((sum, s) => sum + pct(s.progress), 0) / sections.length : null;
  }
  function resultGroups() {
    const groups = new Map();
    Object.entries(obj(state.data.results)).forEach(([file, value]) => {
      const records = Array.isArray(value) ? value : Array.isArray(obj(value).results) ? value.results : [value];
      records.forEach((record, index) => {
        const row = obj(record);
        if (!row.method || !Object.keys(obj(row.metrics)).some(key => numeric(row.metrics[key]))) return;
        const task = String(row.task || '未指定任务'), split = String(row.split || '未指定划分');
        const key = JSON.stringify([task, split]);
        if (!groups.has(key)) groups.set(key, {key,task,split,rows:[],metrics:[],lower:new Set(),conflicts:new Set()});
        groups.get(key).rows.push(Object.assign({}, row, {file,recordId:file + ':' + index}));
      });
    });
    groups.forEach(group => {
      group.metrics = [...new Set(group.rows.flatMap(row => Object.keys(obj(row.metrics)).filter(key => numeric(row.metrics[key]))))].sort();
      group.metrics.forEach(metric => {
        const directions = new Set(group.rows.filter(row => numeric(row.metrics[metric])).map(row => arr(row.lower_is_better).includes(metric)));
        if (directions.has(true)) group.lower.add(metric);
        if (directions.size > 1) group.conflicts.add(metric);
      });
    });
    return [...groups.values()].sort((a,b) => a.key.localeCompare(b.key));
  }
  function metricStats(group, metric) {
    const lower = group.lower.has(metric), values = group.rows.filter(row => numeric(row.metrics[metric]));
    const best = rows => rows.length ? (lower ? Math.min(...rows.map(row => row.metrics[metric])) : Math.max(...rows.map(row => row.metrics[metric]))) : null;
    const baseline = best(values.filter(row => row.is_baseline === true));
    const ours = best(values.filter(row => row.is_baseline === false));
    return {lower,best:best(values),baseline,ours,delta:group.conflicts.has(metric) || baseline == null || ours == null ? null : (ours-baseline)*(lower ? -1 : 1),conflict:group.conflicts.has(metric)};
  }
  function overview() {
    const phasesData = obj(state.data.phases), phases = objectRows(phasesData.phases);
    const active = phases.filter(phase => ['in_progress','running'].includes(phase.status));
    const current = phases.find(phase => phase.id === phasesData.current_phase) || active[active.length-1] ||
      phases.find(phase => phase.status === 'blocked') || phases.find(phase => phase.status === 'not_started') || phases[phases.length-1];
    const ideas = objectRows(obj(state.data.ideas).ideas), alive = ideas.filter(idea => idea && idea.status !== 'pruned').length, pruned = ideas.length-alive;
    const slurm = obj(state.data.slurm), queue = objectRows(slurm.queue), slurmReady = state.data.slurm && !slurm.queue_error && !state.errors.slurm;
    const running = queue.filter(row => ['RUNNING','R','COMPLETING','CG'].includes(row.state)).length;
    const pending = queue.filter(row => ['PENDING','PD'].includes(row.state)).length;
    const paper = paperProgress();
    const group = resultGroups().find(g => g.metrics.some(metric => metricStats(g,metric).delta != null));
    const metric = group && (group.metrics.includes(state.resultMetric) && metricStats(group,state.resultMetric).delta != null ? state.resultMetric : group.metrics.find(m => metricStats(group,m).delta != null));
    const best = group ? metricStats(group,metric) : null;
    const dataset = obj(state.data.dataset), totals = obj(dataset.totals);
    const kpis = kpi('当前研究阶段',current ? esc(current.id) : '—',current ? esc(current.name) : '等待阶段状态','cyan','01') +
      kpi('SLURM 运行 / 等待',slurmReady ? `${running}<span class="unit">/ ${pending}</span>` : '—',slurmReady ? '当前用户的实时作业' : '队列状态暂不可用','','02') +
      kpi('创新点存活 / 剪枝',state.data.ideas && !apiError('ideas') ? `${alive}<span class="unit">/ ${pruned}</span>` : '—','<a href="#/ideas">探索候选算法 ↗</a>','teal','03') +
      kpi('最佳结果 · Δ 基线',best ? `<span class="${best.delta >= 0 ? 'positive':'negative'}">${signed(best.delta)}</span>` : '—',best ? `${esc(group.task)} / ${esc(group.split)} · ${esc(metric)}<br>本方法 ${number(best.ours)} · 基线 ${number(best.baseline)}` : '等待同任务、同划分对比','amber','04') +
      kpi('论文完成度',paper == null ? '—' : `${number(Math.round(paper))}<span class="unit">%</span>`,paper == null ? '等待论文章节状态' : '按章节平均进度' + progressBar(paper),'','05');
    const phaseDefaults = ['环境','进度大屏','文献与创新','实验','达标即停','论文'];
    const timeline = `<div class="timeline">${phaseDefaults.map((name,index) => {
      const phase = phases.find(p => p.id === 'P'+index) || {id:'P'+index,name,status:'unknown'};
      return `<div class="phase ${esc(String(phase.status).replace(/[^a-z_]/g,''))}"><div class="phase-node">${esc(phase.id)}</div><div class="phase-name">${esc(phase.name)}</div>${badge(phase.status)}</div>`;
    }).join('')}</div>`;
    const details = phases.length ? `<div class="phase-details">${phases.filter(p => p.conclusion || active.includes(p)).map(p => `<div><strong>${esc(p.id)} · ${esc(p.name)}</strong><span class="mono muted">　${formatTime(p.started)}${p.finished ? ' → ' + formatTime(p.finished):''}</span><p>${esc(p.conclusion || '暂无阶段结论')}</p></div>`).join('') || '<span class="muted">暂无阶段结论</span>'}</div>` : '<div class="subtle-note">尚未提供阶段状态，P0–P5 等待更新。</div>';
    const dataBody = numeric(totals.games) ? `<div class="stat-inline"><strong>${number(totals.games)}</strong><span>已解析比赛<br>${number(totals.seasons)} 个赛季 · ${number(dataset.fps)} FPS</span></div><div class="metric-pair"><span class="muted">帧总量</span><strong>${number(millions(totals.frames))} M</strong></div><div class="metric-pair"><span class="muted">解析失败 / 已删除</span><strong>${number(totals.failed)} / ${number(totals.deleted)}</strong></div><div class="subtle-note">数据截至 ${esc(dataset.as_of || '—')}</div>` : empty('数据集尚未接入','添加数据集状态后显示规模与分布。');
    const logs = Object.entries(recordMap(state.data.logs)).sort((a,b) => (dateValue(b[1].mtime) || 0)-(dateValue(a[1].mtime) || 0));
    const recent = logs.length ? `<div class="small muted" style="margin-bottom:12px">${esc(logs[0][0])} <span class="mono">· ${formatTime(logs[0][1].mtime)}</span></div><pre class="log-preview">${esc(formatLogs(String(logs[0][1].tail || '').split('\n').filter(Boolean).slice(-12).join('\n')))}</pre>` : empty('还没有会话记录','研究会话开始后，最新日志将显示在这里。','≡');
    const research = best ? `<div class="metric-pair"><span class="muted">任务 / 划分</span><strong>${esc(group.task)} / ${esc(group.split)}</strong></div><div class="metric-pair"><span class="muted">最佳基线 · ${esc(metric)}</span><strong>${number(best.baseline)}</strong></div><div class="metric-pair"><span class="muted">本方法最优 · ${esc(metric)}</span><strong class="amber-text">${number(best.ours)}</strong></div><div class="subtle-note">Δ 已按指标方向归一化；正值表示优于基线。</div>` : empty('等待首组实验结果','完成同一任务与划分的基线和方法评估后，即可查看提升。','↗');
    return `<div class="kpis">${kpis}</div><div class="grid">${card('研究路线 · P0—P5',notice(apiError('phases'))+timeline+details,`<span class="meta">${phases.length ? phases.filter(p=>p.status==='done').length+' / 6 阶段完成':'等待状态'}</span>`,'s8')}${card('数据资产',dataBody,'<a href="#/dataset">查看数据集 ↗</a>','s4')}${card('最近活动',recent,'<a href="#/session">全部日志 ↗</a>','s8')}${card('基线与研究方法',research,'<a href="#/results">实验对比 ↗</a>','s4')}</div>`;
  }
  function datasetView() {
    const data = obj(state.data.dataset), totals = obj(data.totals), seasons = objectRows(data.seasons), modes = obj(totals.modes);
    if (!seasons.length) return card('数据集',notice(apiError('dataset'))+empty('尚无数据集概况','等待数据集汇总与赛季统计。','▤'));
    const modeTotal = ['1v1','2v2','3v3'].reduce((sum,key)=>sum+(numeric(modes[key])?modes[key]:0),0);
    const other = numeric(totals.games) ? Math.max(0, totals.games-modeTotal) : 0;
    const storage = objectRows(data.storage), storageTotal = storage.reduce((sum,item)=>sum+(numeric(item.gb)?item.gb:0),0);
    const kpis = kpi('已解析比赛',number(totals.games),`${number(totals.seasons)} 个赛季已完成解析`,'cyan','01')+kpi('帧总量',`${number(millions(totals.frames))}<span class="unit">M</span>`,`${number(data.fps)} FPS · 原始汇总口径`,'teal','02')+kpi('解析失败 / 已删除',`${number(totals.failed)}<span class="unit">/ ${number(totals.deleted)}</span>`,'失败约 0.3% · 下载前已删除','','03')+kpi('数据占用',`${number(storageTotal)}<span class="unit">GB</span>`,'帧数据与两类原始回放','','04');
    const rows = seasons.map(season => `<tr><td>${esc(season.name)}</td><td class="mono">${number(season.games)}</td><td class="mono">${number(millions(season.frames))} M</td>${['1v1','2v2','3v3'].map(mode=>`<td class="mono">${number(obj(season.modes)[mode])}</td>`).join('')}</tr>`);
    rows.push(`<tr><td><strong>合计</strong></td><td class="mono cyan-text">${number(totals.games)}</td><td class="mono cyan-text">${number(millions(totals.frames))} M</td>${['1v1','2v2','3v3'].map(mode=>`<td class="mono">${number(modes[mode])}</td>`).join('')}</tr>`);
    const modeData = ['1v1','2v2','3v3'].map((name,index)=>({name,value:modes[name],color:palette[index]})).concat([{name:'其他 / 缺员',value:other,color:'#50627e'}]);
    const distribution = `<div id="mode-chart" class="chart short" role="img" aria-label="比赛模式分布"></div><div class="legend">${modeData.map(item=>`<span><i style="background:${item.color}"></i>${esc(item.name)}<span class="count">${number(item.value)}</span></span>`).join('')}</div>`;
    const storageBody = storage.map((item,index)=>`<div class="storage-item"><div class="row"><span>${esc(item.name)}</span><span class="mono">${number(item.gb)} GB</span></div><div class="bar"><i style="width:${storageTotal?item.gb/storageTotal*100:0}%;background:${palette[index]}"></i></div>${item.path ? `<code>${esc(item.path)}</code>`:''}</div>`).join('');
    const protocol = obj(data.split_protocol);
    state.draw = () => {
      barChart('season-games', seasons.map(s=>({name:s.name,value:s.games})), '比赛数');
      barChart('season-frames', seasons.map(s=>({name:s.name,value:millions(s.frames),color:'#2dd4bf'})), '帧数 / M');
      donutChart('mode-chart', modeData);
    };
    return `<div class="kpis four">${kpis}</div><div class="grid">${card('赛季规模 · 比赛数','<div id="season-games" class="chart" role="img" aria-label="各赛季比赛数量柱状图"></div>',`<span class="meta">截至 ${esc(data.as_of)}</span>`,'s6')}${card('赛季规模 · 帧数','<div id="season-frames" class="chart" role="img" aria-label="各赛季帧数柱状图"></div>','<span class="meta">30 FPS · 百万帧</span>','s6')}${card('赛季明细',table(['赛季','已解析比赛','帧数','1v1','2v2','3v3'],rows)+`<p class="table-note">${esc(arr(data.notes).join(' '))}</p>`,'<span class="meta">5 SEASONS</span>','s8')}${card('比赛模式',distribution,'<span class="meta">按比赛计数</span>','s4')}${card('存储占用',storageBody,'<span class="meta">GB</span>','s6')}${card('数据划分协议',`<div class="protocol"><strong>按系列赛 / 赛事 / 赛季划分</strong><p>${esc(protocol.rule || '以 series / event / season 为分组单位，避免同组样本跨集合。')}</p></div><p class="small muted">${esc(protocol.notes || '同一分组的数据只进入一个集合，避免相邻帧与同场比赛泄漏。')}</p>`, '<span class="chip running">分组隔离</span>','s6')}</div>`;
  }
  function ideasView() {
    const all = objectRows(obj(state.data.ideas).ideas);
    const filters = ['all','proposed','running','promising','pruned','selected'];
    const toolbar = `<div class="controls filter-pills">${filters.map(value=>`<button type="button" class="filter-pill ${state.ideaFilter===value?'active':''}" data-idea-filter="${value}" aria-pressed="${state.ideaFilter===value}">${value==='all'?'全部':statusNames[value]} <span class="mono">${value==='all'?all.length:all.filter(i=>i.status===value).length}</span></button>`).join('')}</div>`;
    const filtered = all.filter(idea=>state.ideaFilter==='all'||idea.status===state.ideaFilter);
    const cards = filtered.map(idea=>{
      const refs = arr(idea.inspiration_refs || idea.refs).filter(ref=>typeof ref==='string'||(ref&&typeof ref==='object'&&!Array.isArray(ref))).map(ref=>typeof ref==='string'?link(ref,ref):link(ref.title||ref.label||ref.url,ref.url)).join('<span class="muted">·</span>');
      const best = obj(idea.best_metric);
      return `<article class="card idea-card s6"><div class="idea-top"><h3>${esc(idea.name || idea.algorithm || idea.id || '未命名候选')}</h3>${badge(idea.status)}</div><p>${esc(idea.motivation || '动机待补充')}</p><div class="refs"><span class="muted">灵感来源</span>${refs || '<span class="muted">尚未记录</span>'}</div>${idea.prune_reason?notice('剪枝原因：'+idea.prune_reason):''}<div class="idea-meta"><span class="muted">最佳指标 <strong class="mono cyan-text">${best.name||best.metric ? esc(best.name||best.metric)+' · '+number(best.value):numeric(idea.best_metric)?number(idea.best_metric):'—'}</strong>${best.task ? ' · '+esc(best.task):''}${best.split?' / '+esc(best.split):''}</span><span class="muted">${formatTime(idea.updated)}</span></div></article>`;
    }).join('');
    state.bind = () => document.querySelectorAll('[data-idea-filter]').forEach(button=>button.addEventListener('click',()=>{state.ideaFilter=button.dataset.ideaFilter;render();}));
    return notice(apiError('ideas'))+toolbar+(cards?`<div class="grid">${cards}</div>`:card('候选算法',empty(all.length?'此状态下还没有候选':'让第一个想法开始','记录动机与参考文献，随后跟踪实验表现及剪枝原因。','◇')));
  }
  function resultsView() {
    const groups = resultGroups();
    if (!groups.length) return card('实验对比',notice(apiError('results'))+empty('还没有可对比的实验','基线与研究方法的评估结果将按任务、划分自动归组。','▥'));
    const group = groups.find(g=>g.key===state.resultGroup) || groups[0]; state.resultGroup=group.key;
    const metric = group.metrics.includes(state.resultMetric)?state.resultMetric:group.metrics[0]; state.resultMetric=metric;
    const stats = metricStats(group,metric);
    const toolbar = `<div class="controls"><label>任务 / 划分 <select id="result-group">${groups.map(g=>`<option value="${esc(g.key)}" ${g===group?'selected':''}>${esc(g.task)} / ${esc(g.split)}</option>`).join('')}</select></label><label>图表指标 <select id="result-metric">${group.metrics.map(m=>`<option ${m===metric?'selected':''}>${esc(m)}</option>`).join('')}</select></label><span class="chip ${stats.lower?'pending':'running'}">${stats.lower?'↓ 越低越好':'↑ 越高越好'}</span></div>`;
    const rows = group.rows.slice().sort((a,b)=>{
      const av=a.metrics[metric],bv=b.metrics[metric];
      if (!numeric(av)) return 1; if (!numeric(bv)) return -1;
      return stats.lower?av-bv:bv-av;
    });
    const tableRows = rows.map(row=>`<tr class="${row.is_baseline===false?'ours-row':''}"><td>${esc(row.method)}<div class="small muted">${esc(row.notes||'')}</div></td><td>${row.is_baseline===true?'<span class="chip baseline">基线</span>':row.is_baseline===false?'<span class="chip ours">本方法</span>':'<span class="chip">未分类</span>'}</td>${group.metrics.map(m=>{
      const info=metricStats(group,m),value=row.metrics[m],delta=info.baseline==null||!numeric(value)||info.conflict?null:(value-info.baseline)*(info.lower?-1:1);
      return `<td class="mono ${!info.conflict&&numeric(value)&&value===info.best?'best':''}">${number(value)}${!info.conflict&&numeric(value)&&value===info.best?' ★':''}<div class="small ${delta>=0?'positive':'negative'}">Δ ${signed(delta)}</div></td>`;
    }).join('')}</tr>`);
    state.bind = () => {
      $('result-group').addEventListener('change',event=>{state.resultGroup=event.target.value;render();});
      $('result-metric').addEventListener('change',event=>{state.resultMetric=event.target.value;render();});
    };
    state.draw = () => barChart('result-chart',rows.filter(row=>numeric(row.metrics[metric])).map(row=>({name:row.method,value:row.metrics[metric],color:row.is_baseline===false?'#fbbf24':'#60a5fa'})),metric);
    return toolbar+notice(group.conflicts.size?'部分结果的指标方向配置不一致：'+[...group.conflicts].join('、')+'。这些指标暂停最优标记与 Δ 计算，请统一 lower_is_better。':'')+`<div class="kpis four">${kpi('当前任务',esc(group.task),esc(group.split),'cyan','01',true)}${kpi('最佳基线',number(stats.baseline),esc(metric),'','02')}${kpi('本方法最优',number(stats.ours),esc(metric),'amber','03')}${kpi('相对基线提升',signed(stats.delta),'方向已归一化 · 正值表示改善','teal','04')}</div><div class="grid">${card('指标对比',table(['方法','类型',...group.metrics.map(m=>m+(group.lower.has(m)?' ↓':' ↑'))],tableRows)+'<p class="table-note">★ 为同组最优（含并列）；Δ 相对该指标最佳基线，保留指标原单位。不同任务、划分与指标分别比较。</p>',`<span class="meta">${rows.length} 项结果</span>`,'s12')}${card('方法表现 · '+metric,'<div id="result-chart" class="chart" role="img" aria-label="方法指标柱状图"></div>','<div class="legend"><span><i style="background:#60a5fa"></i>基线</span><span><i style="background:#fbbf24"></i>本方法</span></div>','s12')}</div>`;
  }
  function trainingSeries(runs, metric, axis, split, selected) {
    const series=[];
    Object.entries(recordMap(runs)).forEach(([id,run])=>{
      if (!selected.has(id)) return;
      const bySplit=new Map();
      arr(run.rows).forEach(row=>{
        if (!row || !numeric(row[metric])) return;
        const rowSplit=String(row.split||'未标注');
        if (split!=='all' && rowSplit!==split) return;
        const date=axis==='time'?dateValue(row.time):null;
        const x=axis==='time'?(date?date.getTime():null):row[axis];
        if (!numeric(x)) return;
        if (!bySplit.has(rowSplit)) bySplit.set(rowSplit,[]);
        bySplit.get(rowSplit).push([x,row[metric]]);
      });
      bySplit.forEach((data,rowSplit)=>series.push({name:id+' / '+rowSplit,data:data.sort((a,b)=>a[0]-b[0]),color:palette[series.length%palette.length]}));
    });
    return series;
  }
  function trainingView() {
    const runs=recordMap(state.data.runs), ids=Object.keys(runs);
    if (!ids.length) return card('训练曲线',notice(apiError('runs'))+empty('训练尚未留下曲线','启动实验并持续记录 step、epoch 与数值指标后，即可叠加比较。','⌁'));
    const metrics=[...new Set(ids.flatMap(id=>arr(runs[id].rows).flatMap(row=>Object.keys(obj(row)).filter(key=>!['step','epoch','time','split'].includes(key)&&numeric(row[key])))))].sort();
    const splits=[...new Set(ids.flatMap(id=>arr(runs[id].rows).map(row=>String(obj(row).split||'未标注'))))].sort();
    if (state.selectedRuns===null) state.selectedRuns=new Set(ids);
    const selected=state.selectedRuns;
    if (!metrics.includes(state.trainMetric)) state.trainMetric=metrics[0]||'';
    if (state.trainSplit!=='all'&&!splits.includes(state.trainSplit)) state.trainSplit='all';
    const toolbar=`<div class="controls"><label>指标 <select id="train-metric">${metrics.map(m=>`<option ${m===state.trainMetric?'selected':''}>${esc(m)}</option>`).join('')||'<option>无数值指标</option>'}</select></label><label>横轴 <select id="train-axis">${[['step','步数'],['epoch','轮次'],['time','时间 · CET']].map(([key,label])=>`<option value="${key}" ${key===state.trainAxis?'selected':''}>${label}</option>`).join('')}</select></label><label>数据划分 <select id="train-split"><option value="all">全部（分别绘制）</option>${splits.map(s=>`<option value="${esc(s)}" ${s===state.trainSplit?'selected':''}>${esc(s)}</option>`).join('')}</select></label></div>`;
    const runList=`<div class="controls"><button id="select-runs" class="btn" type="button">全选</button><button id="clear-runs" class="btn" type="button">清空</button></div><div class="run-list">${ids.map(id=>{
      const run=runs[id],meta=obj(run.meta);
      return `<label class="run-choice"><input type="checkbox" data-run="${esc(id)}" ${selected.has(id)?'checked':''}><span>${esc(meta.name||id)}<small>${esc(id)} · ${number(arr(run.rows).length)} 个采样点${run.sampled?' · 已抽样':''}</small><small>${esc(meta.method||'')}${meta.task?' / '+esc(meta.task):''}${meta.status?' · '+esc(statusNames[meta.status]||meta.status):''}</small>${run.skipped_lines?`<small>跳过 ${number(run.skipped_lines)} 行不完整或无效记录</small>`:''}</span></label>`;
    }).join('')}</div>`;
    const series=trainingSeries(runs,state.trainMetric,state.trainAxis,state.trainSplit,selected);
    const chart=series.length?'<div id="training-chart" class="chart tall" role="img" aria-label="多次运行训练指标叠加曲线"></div>':empty(selected.size?'当前指标或横轴没有有效数据':'选择要对比的训练运行',selected.size?'检查记录是否包含所选指标和横轴；时间轴需要带时区的时间。':'在左侧勾选一个或多个运行。','⌁');
    state.bind=()=>{
      [['train-metric','trainMetric'],['train-axis','trainAxis'],['train-split','trainSplit']].forEach(([id,key])=>$(id).addEventListener('change',event=>{state[key]=event.target.value;render();}));
      document.querySelectorAll('[data-run]').forEach(input=>input.addEventListener('change',()=>{input.checked?selected.add(input.dataset.run):selected.delete(input.dataset.run);render();}));
      $('select-runs').addEventListener('click',()=>{state.selectedRuns=new Set(ids);render();});
      $('clear-runs').addEventListener('click',()=>{state.selectedRuns=new Set();render();});
    };
    state.draw=()=>{if(series.length)lineChart('training-chart',series,state.trainAxis,state.trainMetric);};
    return toolbar+`<div class="grid">${card('训练运行',runList,`<span class="meta">${ids.filter(id=>selected.has(id)).length} / ${ids.length} 已选择</span>`,'s4')}${card(state.trainMetric||'训练指标',chart+`<div class="legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div><div class="subtle-note">同一运行的 train / val / test 分别绘制。拖动图表或滚轮缩放（ECharts 可用时）。</div>`,'<span class="meta">多运行叠加</span>','s8')}</div>`;
  }
  function slurmView() {
    const data=obj(state.data.slurm), queue=objectRows(data.queue), history=objectRows(data.history);
    const queueRows=queue.map(job=>`<tr><td class="mono">${esc(job.jobid)}</td><td>${esc(job.partition)}</td><td>${esc(job.name)}</td><td>${badge(job.state)}</td><td class="mono nowrap">${esc(job.time)}</td><td class="mono nowrap">${esc(job.limit)}</td><td class="mono">${esc(job.nodes)}</td><td>${esc(job.reason)}</td></tr>`);
    const historyRows=history.map(job=>`<tr><td class="mono">${esc(job.jobid)}</td><td>${esc(job.name)}</td><td>${badge(job.state)}</td><td class="mono nowrap">${esc(job.elapsed)}</td><td class="mono nowrap">${['Unknown','N/A','None',''].includes(job.end||'')?'—':formatTime(job.end)}</td></tr>`);
    return notice(apiError('slurm'))+card('当前作业队列',notice(data.queue_error)+(queue.length?table(['作业 ID','分区','名称','状态','已用时长','时限','节点数','节点 / 等待原因'],queueRows):empty(data.queue_error?'无法读取作业队列':state.data.slurm?'当前没有排队或运行的作业':'正在读取 SLURM','队列仅显示当前用户的作业；命令不可用时不影响其他页面。','▣')),`<span class="meta">${number(queue.length)} 个作业 · ${formatTime(data.updated)}</span>`)+card('最近两天 · 作业历史',notice(data.history_error)+(history.length?table(['作业 ID','名称','状态','耗时','结束时间 · CET'],historyRows):empty(data.history_error?'历史记录暂不可用':'暂无历史作业','历史数据来自 SLURM 记账服务。','↳')),'<span class="meta">过去 2 天</span>');
  }
  function logsView() {
    const logs=recordMap(state.data.logs),names=Object.keys(logs).sort((a,b)=>(dateValue(logs[b].mtime)||0)-(dateValue(logs[a].mtime)||0));
    if (!names.length) return card('会话日志',notice(apiError('logs'))+empty('还没有日志文件','最新会话与操作记录将在这里按更新时间排列。','≡'));
    if (!names.includes(state.logFile)) state.logFile=names[0];
    const selected=logs[state.logFile];
    const filterLines=()=>{
      const lines=formatLogs(selected.tail).split('\n');
      return state.logFilter?lines.filter(line=>line.toLocaleLowerCase().includes(state.logFilter.toLocaleLowerCase())).join('\n'):lines.join('\n');
    };
    state.bind=()=>{
      document.querySelectorAll('[data-log]').forEach(button=>button.addEventListener('click',()=>{state.logFile=button.dataset.log;render();}));
      $('log-filter').addEventListener('input',event=>{state.logFilter=event.target.value;$('log-output').textContent=filterLines()||'没有匹配的日志行';});
    };
    return card('会话日志',`<div class="controls"><label for="log-filter">筛选日志行</label><input type="search" id="log-filter" value="${esc(state.logFilter)}" placeholder="输入关键词，实时筛选…"></div><div class="log-layout"><div class="log-files">${names.map(name=>`<button type="button" class="log-file ${name===state.logFile?'active':''}" data-log="${esc(name)}" aria-pressed="${name===state.logFile}">${esc(name)}<small>${formatTime(logs[name].mtime)}</small></button>`).join('')}</div><div><div class="small muted" style="margin-bottom:10px">${esc(state.logFile)}${selected.truncated?' · 显示文件末尾 20 KB':''}</div><pre class="log-output" id="log-output">${esc(filterLines()||'没有匹配的日志行')}</pre></div></div><div class="subtle-note">带时区的日志时间转为 CET；未标明时区的原始日志文本保持原样。</div>`,`<span class="meta">${names.length} / 30 份日志</span>`);
  }
  function paperView() {
    const paper=obj(state.data.paper),sections=objectRows(paper.sections),figures=objectRows(paper.figures),citations=obj(paper.citations),progress=paperProgress();
    const names={Introduction:'引言', 'Related Work':'相关工作',Dataset:'数据集',Method:'方法',Experiments:'实验',Conclusion:'结论',Appendix:'附录'};
    const sectionBody=sections.length?sections.map(section=>`<div class="section-row"><span>${esc(names[section.name]||section.name)}<div class="small muted">${esc(section.name)}</div></span><span>${badge(section.status)}</span>${progressBar(section.progress)}<span class="mono section-percent">${number(pct(section.progress))}%</span></div>`).join(''):empty('尚无论文章节','添加章节计划后显示各部分完成进度。','▧');
    const figureRows=figures.map(figure=>`<tr><td>${esc(figure.id||'—')}</td><td>${esc(figure.title||figure.name||'未命名图表')}</td><td>${badge(figure.status)}</td><td>${esc(figure.path||figure.notes||'—')}</td></tr>`);
    return notice(apiError('paper'))+`<div class="kpis four">${kpi('总体完成度',progress==null?'—':`${number(Math.round(progress))}<span class="unit">%</span>`,'按章节等权平均','cyan','01')}${kpi('章节完成',`${sections.filter(s=>s.status==='done').length}<span class="unit">/ ${sections.length}</span>`,'覆盖正文与附录','','02')}${kpi('图表就绪',`${figures.filter(f=>['done','ready'].includes(f.status)).length}<span class="unit">/ ${figures.length}</span>`,'已完成或已就绪的图表','','03')}${kpi('引用已核验',`${number(citations.verified)}<span class="unit">/ ${number(citations.total)}</span>`,'已核验 / 引用总数','teal','04')}</div><div class="grid">${card('章节进度',sectionBody,'<span class="meta">写作与修订</span>','s8')}${card('投稿目标',`<span class="eyebrow">TARGET VENUE</span><div class="target-venue">${esc(paper.target||'待确定')}</div><div class="metric-pair"><span class="muted">最近更新</span><span class="small">${formatTime(paper.updated)}</span></div><p class="small muted">${esc(paper.notes||'研究结论与实验验证完成后，逐步推进论文写作。')}</p>`,'','s4')}${card('图表清单',figures.length?table(['编号','图表','状态','文件 / 备注'],figureRows):empty('图表清单待建立','在这里跟踪方法图、结果图与补充材料的准备情况。','▧'),`<span class="meta">${figures.length} 项</span>`,'s12')}</div>`;
  }
  // Markdown HTML is rebuilt from a small allowlist; images never trigger remote loads.
  function sanitizeMarkdown(html) {
    const parsed=new DOMParser().parseFromString(String(html),'text/html');
    const allowed=new Set(['P','BR','HR','H1','H2','H3','H4','H5','H6','UL','OL','LI','STRONG','EM','DEL','S','PRE','CODE','BLOCKQUOTE','TABLE','THEAD','TBODY','TR','TH','TD','A']);
    const blocked=new Set(['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','SVG','MATH','FORM','INPUT','BUTTON','LINK','META','IMG','VIDEO','AUDIO','SOURCE']);
    function clean(node) {
      if(node.nodeType===3)return esc(node.textContent);
      if(node.nodeType!==1)return '';
      if(blocked.has(node.tagName))return '';
      const content=Array.from(node.childNodes).map(clean).join('');
      if(!allowed.has(node.tagName))return content;
      const tag=node.tagName.toLowerCase();
      if(tag==='a'){const href=safeHref(node.getAttribute('href'));return href?`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${content}</a>`:content;}
      return `<${tag}>${content}${['br','hr'].includes(tag)?'':`</${tag}>`}`;
    }
    return Array.from(parsed.body.childNodes).map(clean).join('');
  }
  function inlineMarkdown(text) {
    const tokens=[];
    let value=String(text).replace(/`([^`]+)`/g,(_,code)=>{tokens.push('<code>'+esc(code)+'</code>');return '\u0000'+(tokens.length-1)+'\u0000';});
    value=value.replace(/!?\[([^\]]+)\]\(([^\s)]+)\)/g,(match,label,url)=>{tokens.push(match.startsWith('!')?esc(label):link(label,url));return '\u0000'+(tokens.length-1)+'\u0000';});
    value=esc(value).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/~~([^~]+)~~/g,'<del>$1</del>');
    return value.replace(/\u0000(\d+)\u0000/g,(_,index)=>tokens[Number(index)]||'');
  }
  function fallbackMarkdown(source) {
    const lines=String(source).replace(/\r/g,'').split('\n');let out='',paragraph=[],code=[],inCode=false,fence='',list='';
    const flush=()=>{if(paragraph.length){out+='<p>'+paragraph.map(inlineMarkdown).join('<br>')+'</p>';paragraph=[];}};
    const closeList=()=>{if(list){out+='</'+list+'>';list='';}};
    const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());
    for(let index=0;index<lines.length;index++){
      const line=lines[index];
      if(/^\s*(```|~~~)/.test(line)){const current=line.trim().slice(0,3);if(!inCode){flush();closeList();inCode=true;fence=current;}else if(current===fence){out+='<pre><code>'+esc(code.join('\n'))+'</code></pre>';code=[];inCode=false;}else code.push(line);continue;}
      if(inCode){code.push(line);continue;}
      if(!line.trim()){flush();closeList();continue;}
      if(line.includes('|')&&index+1<lines.length&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index+1])){
        flush();closeList();out+='<div class="table-wrap"><table><thead><tr>'+cells(line).map(c=>'<th>'+inlineMarkdown(c)+'</th>').join('')+'</tr></thead><tbody>';index++;
        while(index+1<lines.length&&lines[index+1].includes('|'))out+='<tr>'+cells(lines[++index]).map(c=>'<td>'+inlineMarkdown(c)+'</td>').join('')+'</tr>';
        out+='</tbody></table></div>';continue;
      }
      const heading=line.match(/^(#{1,6})\s+(.+)$/),item=line.match(/^\s*(?:([-*+])|\d+\.)\s+(.+)$/);
      if(heading){flush();closeList();const level=heading[1].length;out+=`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`;}
      else if(/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)){flush();closeList();out+='<hr>';}
      else if(item){flush();const type=item[1]?'ul':'ol';if(list!==type){closeList();list=type;out+='<'+type+'>';}out+='<li>'+inlineMarkdown(item[2])+'</li>';}
      else if(/^>\s?/.test(line)){flush();closeList();out+='<blockquote>'+inlineMarkdown(line.replace(/^>\s?/,''))+'</blockquote>';}
      else{closeList();paragraph.push(line);}
    }
    flush();closeList();if(inCode)out+='<pre><code>'+esc(code.join('\n'))+'</code></pre>';return out;
  }
  function progressView() {
    const source=typeof state.data.progress==='string'?state.data.progress:'';
    if(!source.trim())return card('PROGRESS.md',notice(apiError('progress'))+empty('进度文档尚未建立','项目的阶段结论、实验记录与下一步计划将在这里呈现。','↳'));
    let html;
    try{
      if(window.marked){
        // Escape raw HTML and omit image resources before parsing the resulting DOM.
        const renderer=new window.marked.Renderer();
        renderer.html=raw=>esc(raw);
        renderer.image=(href,title,text)=>esc(text||'');
        html=sanitizeMarkdown(window.marked.parse(source,{gfm:true,renderer}));
      }else html=fallbackMarkdown(source);
    }catch(error){html=fallbackMarkdown(source);}
    return card('研究进度文档',`<article class="document">${html}</article>`,'<span class="meta">PROGRESS.md</span>');
  }
  function useEcharts(id,options) {
    const element=$(id);if(!element||!window.echarts)return false;
    try{const chart=window.echarts.init(element,null,{renderer:'canvas'});chart.setOption(Object.assign({backgroundColor:'transparent',color:palette,textStyle:{color:'#8296b3',fontFamily:'sans-serif'},animation:false},options));state.charts.push(chart);return true;}catch(error){element.innerHTML='';return false;}
  }
  const axisStyle={axisLine:{lineStyle:{color:'#24466e'}},axisTick:{show:false},axisLabel:{color:'#8296b3',fontSize:10},splitLine:{lineStyle:{color:'#16263f'}}};
  function barChart(id,items,label) {
    const element=$(id);if(!element)return;
    const data=items.filter(item=>numeric(item.value));
    if(!data.length){element.innerHTML=empty('没有数值数据','等待指标写入。');return;}
    if(useEcharts(id,{tooltip:{trigger:'axis',renderMode:'richText',axisPointer:{type:'shadow'}},grid:{left:56,right:18,top:25,bottom:64},xAxis:Object.assign({},axisStyle,{type:'category',data:data.map(item=>item.name),axisLabel:{color:'#8296b3',fontSize:10,interval:0,rotate:data.length>7?25:0,width:90,overflow:'truncate'}}),yAxis:Object.assign({},axisStyle,{type:'value',name:label,nameTextStyle:{fontSize:10}}),series:[{type:'bar',barMaxWidth:48,data:data.map(item=>({value:item.value,itemStyle:{color:item.color||'#22d3ee',borderRadius:[3,3,0,0]}}))}]}))return;
    const width=720,height=280,left=70,right=20,top=25,bottom=58,plotW=width-left-right,plotH=height-top-bottom;
    let min=Math.min(0,...data.map(item=>item.value)),max=Math.max(0,...data.map(item=>item.value));if(max===min)max=min+1;
    const y=value=>top+(max-value)/(max-min)*plotH,zero=y(0),slot=plotW/data.length;
    let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}柱状图">`;
    for(let index=0;index<=4;index++){const value=min+(max-min)*index/4,yp=y(value);svg+=`<path d="M${left} ${yp}H${width-right}" stroke="#16263f"/><text x="${left-10}" y="${yp+4}" text-anchor="end" fill="#8296b3" font-size="10">${esc(number(value))}</text>`;}
    data.forEach((item,index)=>{const x=left+slot*index+slot*.2,yp=y(item.value),barW=slot*.6;svg+=`<rect x="${x}" y="${Math.min(yp,zero)}" width="${barW}" height="${Math.max(1,Math.abs(zero-yp))}" rx="2" fill="${item.color||'#22d3ee'}"><title>${esc(item.name)}: ${number(item.value)}</title></rect><text x="${x+barW/2}" y="${height-bottom+22}" text-anchor="middle" fill="#8296b3" font-size="10">${esc(String(item.name).length>16?String(item.name).slice(0,15)+'…':item.name)}</text>`;});
    element.innerHTML=svg+'</svg>';
  }
  function donutChart(id,items) {
    const element=$(id);if(!element)return;
    const total=items.reduce((sum,item)=>sum+(numeric(item.value)?item.value:0),0);
    if(useEcharts(id,{tooltip:{trigger:'item',renderMode:'richText'},title:{text:number(total),subtext:'已解析比赛',left:'center',top:'36%',textStyle:{color:'#d7e3f4',fontSize:22,fontFamily:'monospace'},subtextStyle:{color:'#8296b3',fontSize:10}},series:[{type:'pie',radius:['65%','82%'],center:['50%','48%'],label:{show:false},data:items.map(item=>({name:item.name,value:item.value,itemStyle:{color:item.color}}))}]}))return;
    let offset=0;
    element.innerHTML=`<svg viewBox="0 0 300 210" role="img" aria-label="模式分布"><circle cx="150" cy="100" r="73" fill="none" stroke="#16263f" stroke-width="19"/>${items.map(item=>{const size=total?item.value/total*100:0,shape=`<circle cx="150" cy="100" r="73" pathLength="100" fill="none" stroke="${item.color}" stroke-width="19" stroke-dasharray="${size} ${100-size}" stroke-dashoffset="${-offset}" transform="rotate(-90 150 100)"><title>${esc(item.name)}: ${number(item.value)}</title></circle>`;offset+=size;return shape;}).join('')}<text x="150" y="101" text-anchor="middle" fill="#d7e3f4" font-family="monospace" font-size="25">${number(total)}</text><text x="150" y="122" text-anchor="middle" fill="#8296b3" font-size="11">已解析比赛</text></svg>`;
  }
  function lineChart(id,series,axis,metric) {
    const element=$(id);if(!element)return;
    const xFormat=value=>axis==='time'?clockFormatter.format(new Date(value))+' CET':number(value);
    if(useEcharts(id,{tooltip:{trigger:'axis',renderMode:'richText',axisPointer:{label:{formatter:params=>axis==='time'?formatTime(params.value):number(params.value)}},formatter:params=>{
      const rows=Array.isArray(params)?params:[params];const first=rows[0];if(!first)return '';
      return (axis==='time'?formatTime(first.value[0]):axis+' '+number(first.value[0]))+'\n'+rows.map(row=>row.seriesName+': '+number(row.value[1])).join('\n');
    }},grid:{left:65,right:22,top:25,bottom:70},xAxis:Object.assign({},axisStyle,{type:axis==='time'?'time':'value',axisLabel:{color:'#8296b3',fontSize:10,formatter:xFormat}}),yAxis:Object.assign({},axisStyle,{type:'value',scale:true,name:metric}),dataZoom:[{type:'inside'},{type:'slider',height:15,bottom:10,borderColor:'#24466e',textStyle:{color:'#8296b3'},labelFormatter:xFormat}],series:series.map(s=>({name:s.name,type:'line',data:s.data,showSymbol:s.data.length<30,symbolSize:5,lineStyle:{width:2,color:s.color},itemStyle:{color:s.color},connectNulls:false}))}))return;
    const points=series.flatMap(s=>s.data),width=800,height=370,left=72,right=20,top=22,bottom=52;
    const bounds=points.reduce((box,p)=>[Math.min(box[0],p[0]),Math.max(box[1],p[0]),Math.min(box[2],p[1]),Math.max(box[3],p[1])],[Infinity,-Infinity,Infinity,-Infinity]);
    let [minX,maxX,minY,maxY]=bounds;
    if(minX===maxX)maxX=minX+1;if(minY===maxY){minY-=.5;maxY+=.5;}
    const padding=(maxY-minY)*.08;minY-=padding;maxY+=padding;
    const x=value=>left+(value-minX)/(maxX-minX)*(width-left-right),y=value=>top+(maxY-value)/(maxY-minY)*(height-top-bottom);
    let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(metric)}训练曲线">`;
    for(let index=0;index<=4;index++){const value=minY+(maxY-minY)*index/4,yp=y(value),xv=minX+(maxX-minX)*index/4;svg+=`<path d="M${left} ${yp}H${width-right}" stroke="#16263f"/><text x="${left-9}" y="${yp+3}" fill="#8296b3" font-size="10" text-anchor="end">${number(value)}</text><text x="${x(xv)}" y="${height-25}" fill="#8296b3" font-size="10" text-anchor="middle">${esc(xFormat(xv))}</text>`;}
    series.forEach(s=>{svg+=`<polyline points="${s.data.map(p=>x(p[0])+','+y(p[1])).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2"><title>${esc(s.name)}</title></polyline>`;const stride=Math.max(1,Math.ceil(s.data.length/150));s.data.filter((p,index)=>index%stride===0||index===s.data.length-1).forEach(p=>{svg+=`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="2.5" fill="${s.color}"><title>${esc(s.name)} · ${esc(axis==='time'?formatTime(p[0]):number(p[0]))} · ${number(p[1])}</title></circle>`;});});
    element.innerHTML=svg+'</svg>';
  }
  const renderers={overview,dataset:datasetView,ideas:ideasView,results:resultsView,training:trainingView,slurm:slurmView,session:logsView,paper:paperView,progress:progressView};
  function render() {
    const active=document.activeElement,focus=active&&active.id,start=active&&active.selectionStart;
    const logScroll=$('log-output')?$('log-output').scrollTop:null;
    state.charts.forEach(chart=>chart.dispose());state.charts=[];state.bind=null;state.draw=null;
    const page=views[state.view];$('page-title').textContent=page[0];$('breadcrumb').textContent=page[0];$('page-kicker').textContent=page[1];$('page-description').textContent=page[2];
    document.title=page[0]+' · RLCS 战术研究';
    document.querySelectorAll('[data-view]').forEach(anchor=>{const current=anchor.dataset.view===state.view;anchor.classList.toggle('active',current);if(current)anchor.setAttribute('aria-current','page');else anchor.removeAttribute('aria-current');});
    try{$('view').innerHTML=renderers[state.view]();if(state.bind)state.bind();if(state.draw)state.draw();}catch(error){$('view').innerHTML=card('数据暂不可用',empty('无法显示当前数据','请检查文件字段格式；其他页面仍可查看。'));console.error(error);}
    $('chart-mode').textContent=window.echarts?'ECharts 5.5.0':'离线 SVG 图表';
    if(focus&&$(focus)){try{$(focus).focus({preventScroll:true});if(typeof start==='number'&&$(focus).setSelectionRange)$(focus).setSelectionRange(start,start);}catch(error){/* Non-text controls cannot restore a caret. */}}
    if(logScroll!==null&&$('log-output'))$('log-output').scrollTop=logScroll;
  }
  function route() {const name=location.hash.replace(/^#\/?/,'').split(/[?\/]/)[0]||'overview';state.view=Object.prototype.hasOwnProperty.call(views,name)?name:'overview';render();}
  async function fetchData(name) {
    const controller=typeof AbortController==='function'?new AbortController():null;
    const timeout=controller?setTimeout(()=>controller.abort(),35000):null;
    try{
      const response=await fetch('/api/'+name,{cache:'no-store',signal:controller?controller.signal:undefined});
      if(!response.ok)throw new Error('HTTP '+response.status);
      state.data[name]=await response.json();delete state.errors[name];
    }catch(error){state.errors[name]=name+' 数据读取失败，保留上次结果；将在下次刷新重试。';}
    finally{if(timeout)clearTimeout(timeout);}
  }
  function updateHeader() {
    const host=obj(state.data.host);$('host').textContent=host.host||'—';
    $('last-update').textContent=formatTime(state.lastUpdate);
    const failures=Object.keys(state.errors),partial=failures.length>0;
    $('connection-dot').className='dot '+(partial?'warn':'ok');$('connection').textContent=partial?'部分数据中断':'服务已连接';
    $('api-notice').hidden=!partial;$('api-notice').textContent=failures.map(name=>state.errors[name]).join(' ');
  }
  async function refresh() {
    if(state.busy)return;state.busy=true;$('refresh').disabled=true;
    const slurm=fetchData('slurm').then(()=>{if(['overview','slurm'].includes(state.view))render();});
    await Promise.all(['host','phases','dataset','ideas','paper','results','runs','logs','progress'].map(fetchData));
    if(!state.errors.host)state.lastUpdate=obj(state.data.host).time;
    updateHeader();render();await slurm;updateHeader();state.busy=false;$('refresh').disabled=false;
  }
  $('refresh').addEventListener('click',refresh);
  window.addEventListener('hashchange',route);
  window.addEventListener('resize',()=>state.charts.forEach(chart=>chart.resize()));
  document.querySelectorAll('script[src*="cdnjs"]').forEach(script=>script.addEventListener('load',()=>render()));
  const tick=()=>{$('clock').textContent=clockFormatter.format(new Date())+' CET';};
  tick();setInterval(tick,1000);setInterval(refresh,30000);route();refresh();
})();
