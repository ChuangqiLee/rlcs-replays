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
  const cjk = /[\u3000-\u9fff\uff00-\uffef]/;
  const warnedTranslations = new Set();
  // Only identifiers, paths and established technical tokens may remain English
  // without a Chinese sibling. Prose never falls back to the other language.
  const technical = /^(?:[A-Z][A-Z0-9]*(?:[-_.][A-Z0-9]+)*|(?:RQ|P|B|L|K)\d+[a-z]?(?:\.\d+)?|uu|bootstrap|k-means|lbfgs|\d+(?:\.\d+)?(?:s|ms|Hz|GB|MB|uu)?|[\d+−–.,%()[\] /:]+)$/;
  function localized(row, key) {
    row = obj(row);
    const translated = row[key + '_' + lang];
    const original = row[key];
    const explicit = translated !== undefined && translated !== null && translated !== '';
    const source = explicit ? translated : original;
    const other = row[key + (lang === 'en' ? '_zh' : '_en')];
    if ((source == null || source === '') && other != null && other !== '') {
      const id = lang + ':' + key + ':missing';
      if (!warnedTranslations.has(id)) {
        warnedTranslations.add(id);
        console.warn('[i18n] Missing ' + key + '_' + lang + '; other-language field is not a fallback');
      }
      const marker = t('[未翻译]', '[untranslated]');
      return Array.isArray(other) ? other.map(()=>marker) : marker;
    }
    const check = text => {
      if (text === undefined || text === null || text === '') return '';
      if (typeof text !== 'string') return typeof text === 'number' ? text : '';
      const safe = lang === 'en' ? !cjk.test(text) : explicit ||
        !/[A-Za-z]/.test(text.replace(/(?:https?:\/\/|(?:[\w.-]+\/)+)[^\s，。；]+/g, '').replace(/\b(?:RMST|AIPW|OLS|GRU|GPU|CPU|RLCS|CI|ID|uu|bootstrap|boost)\b/g, '')) || technical.test(text);
      if (safe) return text;
      const id = lang + ':' + key + ':' + text;
      if (!warnedTranslations.has(id)) {
        warnedTranslations.add(id);
        console.warn('[i18n] Missing or invalid ' + key + '_' + lang, text);
      }
      return t('[未翻译]', '[untranslated]');
    };
    return Array.isArray(source) ? source.map(x=>typeof x === 'object' ? x : check(x)) : check(source);
  }
  // BEGIN GENERATED I18N TERMS (reviewed in dashboard/i18n_map.json)
  const terms = {
  "adjusted": {
    "label_zh": "调整后",
    "label_en": "Adjusted"
  },
  "difference_for": {
    "label_zh": "进球概率差",
    "label_en": "Scoring probability difference"
  },
  "difference_against": {
    "label_zh": "失球概率差",
    "label_en": "Concession probability difference"
  },
  "difference_net_gd": {
    "label_zh": "净进球差",
    "label_en": "Net goal difference"
  },
  "stay_for": {
    "label_zh": "保持位置时进球概率",
    "label_en": "Scoring probability when staying"
  },
  "stay_against": {
    "label_zh": "保持位置时失球概率",
    "label_en": "Concession probability when staying"
  },
  "stay_net_gd": {
    "label_zh": "保持位置时净进球",
    "label_en": "Net goals when staying"
  },
  "advance_for": {
    "label_zh": "前压时进球概率",
    "label_en": "Scoring probability when advancing"
  },
  "advance_against": {
    "label_zh": "前压时失球概率",
    "label_en": "Concession probability when advancing"
  },
  "advance_net_gd": {
    "label_zh": "前压时净进球",
    "label_en": "Net goals when advancing"
  },
  "deep_for": {
    "label_zh": "深位时进球概率",
    "label_en": "Scoring probability in deep position"
  },
  "deep_against": {
    "label_zh": "深位时失球概率",
    "label_en": "Concession probability in deep position"
  },
  "deep_net_gd": {
    "label_zh": "深位时净进球",
    "label_en": "Net goals in deep position"
  },
  "advanced_for": {
    "label_zh": "前压位置进球概率",
    "label_en": "Scoring probability in advanced position"
  },
  "advanced_against": {
    "label_zh": "前压位置失球概率",
    "label_en": "Concession probability in advanced position"
  },
  "advanced_net_gd": {
    "label_zh": "前压位置净进球",
    "label_en": "Net goals in advanced position"
  },
  "roster_id": {
    "label_zh": "阵容 ID",
    "label_en": "Roster ID"
  },
  "player_id": {
    "label_zh": "球员 ID",
    "label_en": "Player ID"
  },
  "null": {
    "label_zh": "零模型",
    "label_en": "Null model"
  },
  "primary": {
    "label_zh": "主分析",
    "label_en": "Primary"
  },
  "empirical_marginal_diagnostic": {
    "label_zh": "经验边际诊断",
    "label_en": "Empirical marginal diagnostic"
  },
  "eligible_unshifted_diagnostic": {
    "label_zh": "合格未平移样本诊断",
    "label_en": "Eligible unshifted diagnostic"
  },
  "result": {
    "label_zh": "结果",
    "label_en": "Result"
  },
  "inputs": {
    "label_zh": "输入",
    "label_en": "Inputs"
  },
  "full_model": {
    "label_zh": "完整模型",
    "label_en": "Full model"
  },
  "metrics": {
    "label_zh": "指标",
    "label_en": "Metrics"
  },
  "top1": {
    "label_zh": "第1位命中率",
    "label_en": "Top-1 accuracy"
  },
  "top5": {
    "label_zh": "前5位命中率",
    "label_en": "Top-5 accuracy"
  },
  "mrr": {
    "label_zh": "平均倒数排名",
    "label_en": "Mean reciprocal rank"
  },
  "a": {
    "label_zh": "路径 a",
    "label_en": "Path a"
  },
  "b": {
    "label_zh": "路径 b",
    "label_en": "Path b"
  },
  "a*b": {
    "label_zh": "路径 a*b",
    "label_en": "Path a*b"
  },
  "direct": {
    "label_zh": "直接项",
    "label_en": "Direct component"
  },
  "total": {
    "label_zh": "总计",
    "label_en": "Total"
  },
  "proportion": {
    "label_zh": "比例",
    "label_en": "Proportion"
  },
  "sensitivity": {
    "label_zh": "敏感性",
    "label_en": "Sensitivity"
  },
  "earlier_width": {
    "label_zh": "较早宽度",
    "label_en": "Earlier width"
  },
  "details": {
    "label_zh": "明细",
    "label_en": "Details"
  },
  "realized_ball_control": {
    "label_zh": "实际球运动控制",
    "label_en": "Realized-ball control"
  },
  "train": {
    "label_zh": "训练集",
    "label_en": "Train"
  },
  "L1_km_rmst": {
    "label_zh": "L1 Kaplan–Meier RMST",
    "label_en": "L1 Kaplan–Meier RMST"
  },
  "L1_uncensored_ols": {
    "label_zh": "L1 未删失 OLS",
    "label_en": "L1 uncensored OLS"
  },
  "L2_latency_logit": {
    "label_zh": "L2 延迟逻辑回归",
    "label_en": "L2 latency logit"
  },
  "S_opp": {
    "label_zh": "对手指标 S_opp",
    "label_en": "Opponent metric S_opp"
  },
  "S_opp_concede": {
    "label_zh": "对手失球指标 S_opp_concede",
    "label_en": "Opponent concession metric S_opp_concede"
  },
  "paired_urgency": {
    "label_zh": "配对紧迫程度",
    "label_en": "Paired urgency"
  },
  "urgency": {
    "label_zh": "紧迫程度",
    "label_en": "Urgency"
  },
  "contrasts": {
    "label_zh": "对比",
    "label_en": "Contrasts"
  },
  "p6_1_leading_late_minus_early": {
    "label_zh": "P6.1 领先方末段减早段",
    "label_en": "P6.1 leading late minus early"
  },
  "p6_1_trailing_late_minus_early": {
    "label_zh": "P6.1 落后方末段减早段",
    "label_en": "P6.1 trailing late minus early"
  },
  "p6_1_trailing_minus_leading_interaction": {
    "label_zh": "P6.1 落后减领先交互",
    "label_en": "P6.1 trailing minus leading interaction"
  },
  "p6_6_ot_minus_late_tied": {
    "label_zh": "P6.6 加时减常规末段平局",
    "label_en": "P6.6 overtime minus late tied regulation"
  },
  "p6_6_late_trailing_minus_ot": {
    "label_zh": "P6.6 末段落后减加时",
    "label_en": "P6.6 late trailing minus overtime"
  },
  "p6_7_centroid_interaction": {
    "label_zh": "P6.7 质心交互",
    "label_en": "P6.7 centroid interaction"
  },
  "p6_7_mean_depth_interaction": {
    "label_zh": "P6.7 平均深度交互",
    "label_en": "P6.7 mean-depth interaction"
  },
  "Intercept": {
    "label_zh": "截距",
    "label_en": "Intercept"
  },
  "late": {
    "label_zh": "末段",
    "label_en": "Late"
  },
  "late:trailing": {
    "label_zh": "末段×落后",
    "label_en": "Late × trailing"
  },
  "trailing": {
    "label_zh": "落后",
    "label_en": "Trailing"
  },
  "RQ1_p_holm": {
    "label_zh": "RQ1 Holm 校正 p 值",
    "label_en": "RQ1 Holm-adjusted p"
  },
  "RQ3_p_holm": {
    "label_zh": "RQ3 Holm 校正 p 值",
    "label_en": "RQ3 Holm-adjusted p"
  },
  "anchors": {
    "label_zh": "锚点数",
    "label_en": "Anchors"
  },
  "bytes": {
    "label_zh": "字节数",
    "label_en": "Bytes"
  },
  "causal_identification_gate_passed": {
    "label_zh": "因果识别门槛通过",
    "label_en": "Causal identification gate passed"
  },
  "context_rows": {
    "label_zh": "情境行数",
    "label_en": "Context rows"
  },
  "discoveries_q005": {
    "label_zh": "发现数（q005）",
    "label_en": "Discoveries (q005)"
  },
  "elapsed_seconds": {
    "label_zh": "已用秒数",
    "label_en": "Elapsed seconds"
  },
  "excess_gain_bits": {
    "label_zh": "超额增益（比特）",
    "label_en": "Excess gain (bits)"
  },
  "exploratory_dr_difference_against": {
    "label_zh": "探索性双重稳健失球概率差",
    "label_en": "Exploratory DR concession probability difference"
  },
  "exploratory_dr_difference_for": {
    "label_zh": "探索性双重稳健进球概率差",
    "label_en": "Exploratory DR scoring probability difference"
  },
  "exploratory_dr_difference_net_gd": {
    "label_zh": "探索性双重稳健净进球差",
    "label_en": "Exploratory DR net goal difference"
  },
  "failed_games": {
    "label_zh": "失败比赛数",
    "label_en": "Failed games"
  },
  "family_size": {
    "label_zh": "检验族大小",
    "label_en": "Family size"
  },
  "figures": {
    "label_zh": "图表数",
    "label_en": "Figures"
  },
  "files": {
    "label_zh": "文件数",
    "label_en": "Files"
  },
  "fingerprints": {
    "label_zh": "指纹数",
    "label_en": "Fingerprints"
  },
  "frame_derived_timed_goal_coverage": {
    "label_zh": "帧推导带时间进球覆盖率",
    "label_en": "Frame-derived timed goal coverage"
  },
  "frames": {
    "label_zh": "帧数",
    "label_en": "Frames"
  },
  "goal_agreement_rate": {
    "label_zh": "进球一致率",
    "label_en": "Goal agreement rate"
  },
  "ideas": {
    "label_zh": "想法数",
    "label_en": "Ideas"
  },
  "index_games": {
    "label_zh": "索引比赛数",
    "label_en": "Indexed games"
  },
  "interaction": {
    "label_zh": "交互项",
    "label_en": "Interaction"
  },
  "k": {
    "label_zh": "聚类数 k",
    "label_en": "Cluster count k"
  },
  "live_frames": {
    "label_zh": "活球帧数",
    "label_en": "Live-play frames"
  },
  "metadata_timed_goal_coverage": {
    "label_zh": "元数据带时间进球覆盖率",
    "label_en": "Metadata timed goal coverage"
  },
  "n_train_replays": {
    "label_zh": "训练回放数",
    "label_en": "Training replays"
  },
  "n_val_replays": {
    "label_zh": "验证回放数",
    "label_en": "Validation replays"
  },
  "not_computable": {
    "label_zh": "无法计算",
    "label_en": "Not computable"
  },
  "odd_player_games": {
    "label_zh": "奇数球员比赛数",
    "label_en": "Games with odd player counts"
  },
  "ok_games": {
    "label_zh": "成功比赛数",
    "label_en": "Successful games"
  },
  "p_value": {
    "label_zh": "p 值",
    "label_en": "p-value"
  },
  "perspectives": {
    "label_zh": "视角数",
    "label_en": "Perspectives"
  },
  "player_fingerprints": {
    "label_zh": "球员指纹数",
    "label_en": "Player fingerprints"
  },
  "predictive_gain_bits": {
    "label_zh": "预测增益（比特）",
    "label_en": "Predictive gain (bits)"
  },
  "primary_estimates": {
    "label_zh": "主估计数",
    "label_en": "Primary estimates"
  },
  "promising": {
    "label_zh": "有潜力",
    "label_en": "Promising"
  },
  "replays": {
    "label_zh": "回放数",
    "label_en": "Replays"
  },
  "replays_processed": {
    "label_zh": "已处理回放数",
    "label_en": "Processed replays"
  },
  "scanned_frames": {
    "label_zh": "已扫描帧数",
    "label_en": "Scanned frames"
  },
  "season_fingerprints": {
    "label_zh": "赛季指纹数",
    "label_en": "Season fingerprints"
  },
  "selected_replays": {
    "label_zh": "选定回放数",
    "label_en": "Selected replays"
  },
  "series": {
    "label_zh": "系列赛",
    "label_en": "Series"
  },
  "series_coverage": {
    "label_zh": "系列赛覆盖率",
    "label_en": "Series coverage"
  },
  "shards": {
    "label_zh": "分片数",
    "label_en": "Shards"
  },
  "stable_player_id_coverage": {
    "label_zh": "稳定球员 ID 覆盖率",
    "label_en": "Stable player ID coverage"
  },
  "state_decoding_failures": {
    "label_zh": "状态解码失败数",
    "label_en": "State decoding failures"
  },
  "tests": {
    "label_zh": "检验数",
    "label_en": "Tests"
  },
  "timed_goal_coverage": {
    "label_zh": "带时间进球覆盖率",
    "label_en": "Timed goal coverage"
  },
  "validated_replays": {
    "label_zh": "已验证回放数",
    "label_en": "Validated replays"
  },
  "validation_reconstruction": {
    "label_zh": "验证集重构",
    "label_en": "Validation reconstruction"
  },
  "weak": {
    "label_zh": "证据较弱",
    "label_en": "Weak evidence"
  },
  "windows": {
    "label_zh": "窗口数",
    "label_en": "Windows"
  },
  "loss": {
    "label_zh": "损失",
    "label_en": "Loss"
  },
  "dimensionless": {
    "label_zh": "无量纲",
    "label_en": "Dimensionless"
  },
  "seconds": {
    "label_zh": "秒",
    "label_en": "seconds"
  },
  "ms": {
    "label_zh": "毫秒",
    "label_en": "ms"
  },
  "uu": {
    "label_zh": "游戏单位 uu",
    "label_en": "game units (uu)"
  },
  "all": {
    "label_zh": "全部",
    "label_en": "All"
  },
  "val": {
    "label_zh": "验证集",
    "label_en": "Validation"
  },
  "test": {
    "label_zh": "测试集",
    "label_en": "Test"
  },
  "unspecified": {
    "label_zh": "未标注划分",
    "label_en": "Unspecified split"
  },
  "rlcs-2025": {
    "label_zh": "RLCS 2025",
    "label_en": "RLCS 2025"
  },
  "rlcs-2024": {
    "label_zh": "RLCS 2024",
    "label_en": "RLCS 2024"
  },
  "rlcs-21-22": {
    "label_zh": "RLCS 21-22",
    "label_en": "RLCS 21-22"
  },
  "rlcs-22-23": {
    "label_zh": "RLCS 22-23",
    "label_en": "RLCS 22-23"
  }
};
  // END GENERATED I18N TERMS
  const term = key => key == null || key === '' ? unknown() : localized(terms[key] || {label:key}, 'label');
  const raw = (text, kind) => `<code data-i18n-raw="${kind}">${esc(str(text))}</code>`;
  function resultLabel(path) { return path.split('/').slice(-2).map(term).join(' / '); }
  const str = v => v == null || v === '' || ['Unknown','N/A','None','(null)'].includes(v) ? unknown() : String(v);
  const fmt = v => num(v) ? v.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-GB', {maximumFractionDigits:5}) : unknown();
  const value = v => num(v) ? fmt(v) : str(v);
  const state = {data:{}, errors:{}, view:'overview', busy:false, last:null, metric:'', axis:'step', split:'all', selected:null, resultGroup:'', ideaFilter:'all', ideaStatus:'all', legacyGroup:'', log:'', logFilter:'', next:Date.now()+30000};
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
    completed:['已完成','Completed'], planned:['已计划','Planned'], computed:['已计算','Computed'], estimated:['已估计','Estimated'], computed_association_causal_gate_failed:['关联已计算；因果门槛未通过','Association computed; causal gate failed'], not_computable:['无法计算','Not computable'], insufficient_support:['支持不足','Insufficient support'], insufficient_data:['数据不足','Insufficient data'], missing_or_conflicting:['缺失或冲突','Missing or conflicting'], 通过:['通过','Passed'], 未通过:['未通过','Not passed'],
    RUNNING:['运行中','Running'], PENDING:['排队中','Pending'], COMPLETED:['已完成','Completed'], FAILED:['失败','Failed'], CANCELLED:['已取消','Cancelled'], TIMEOUT:['超时','Timed out'], COMPLETING:['结束中','Completing'], SUSPENDED:['挂起','Suspended'], NODE_FAIL:['节点故障','Node failure'], OUT_OF_MEMORY:['内存不足','Out of memory'], BOOT_FAIL:['启动失败','Boot failure'], DEADLINE:['超过期限','Deadline'], PREEMPTED:['被抢占','Preempted'], REVOKED:['撤销','Revoked'], REQUEUED:['重新排队','Requeued'], RESIZING:['调整资源','Resizing']
  };
  function statusName(s) { const pair = statuses[s] || statuses[String(s).toLowerCase()]; return pair ? t(...pair) : unknown(); }
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
    return new Intl.DateTimeFormat(lang === 'zh' ? 'zh-CN' : 'en-GB', {timeZone:'Etc/GMT-1',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(d)+' CET';
  }
  const empty = (zh='暂无数据',en='No data available',detail='') => `<div class="empty"><strong>${esc(t(zh,en))}</strong><p>${esc(detail)}</p></div>`;
  const note = text => text ? `<div class="notice">${esc(text)}</div>` : '';
  const card = (title,body,meta='') => `<section class="card"><div class="card-head"><h2>${esc(title)}</h2><span class="meta">${esc(meta)}</span></div>${body}</section>`;
  const kpi = (label,v,foot='') => `<div class="kpi"><div class="kpi-label">${esc(label)}</div><div class="kpi-value">${esc(value(v))}</div><div class="kpi-foot">${esc(foot)}</div></div>`;
  const table = (headers,rows,cls='') => `<div class="table-wrap"><table class="${cls}"><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(c=>`<tr>${c.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const error = name => state.errors[name] ? t('读取失败，保留上次结果：','Read failed; retaining previous data: ')+'/api/'+name : localized(state.data[name],'error');
  function progress(p) {
    if (num(p.progress) && p.progress >= 0 && p.progress <= 100) return p.progress;
    if (['done','completed'].includes(p.status)) return 100;
    if (p.status === 'not_started') return 0;
    return null;
  }
  function phaseRows(rows) {
    return rows.length ? rows.map(p=>{ const n=progress(p), label=`${p.id || ''} ${localized(p,'name')}`.trim(); return `<div class="phase-row"><div class="phase-title"><h3>${esc(label)}</h3>${badge(p.status)}</div><div class="bar ${n==null?'unknown':''}" role="progressbar" aria-label="${esc(label)}" aria-valuemin="0" aria-valuemax="100" ${n==null?`aria-valuetext="${unknown()}"`:`aria-valuenow="${n}"`}><span style="width:${n ?? 0}%"></span></div><div class="meta">${n==null?t('进度未知','Progress unknown'):fmt(n)+'%'}${p.started?' · '+time(p.started):''}${p.finished?' → '+time(p.finished):''}</div><p>${esc(localized(p,'conclusion'))}</p></div>`; }).join('') : empty();
  }
  function purpose(name) {
    const p=obj(obj(obj(state.data.job_purposes).purposes)[name]);
    return (lang==='en' && cjk.test(p.en||'')) ? unknown() : (p[lang] || unknown());
  }
  function duration(seconds) {
    if(!num(seconds)||seconds<0)return unknown();
    const n=Math.floor(seconds),h=Math.floor(n/3600),m=Math.floor(n%3600/60),sec=n%60;
    return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  }
  function limitSeconds(v) {
    const m=String(v||'').match(/^(?:(\d+)-)?(?:(\d+):)?(\d{2}):(\d{2})$/);
    return m && +m[3]<60 && +m[4]<60 && !(m[1]&&!m[2]) ? (+m[1]||0)*86400+(+m[2]||0)*3600+(+m[3])*60+(+m[4]) : null;
  }
  function projectRule() {
    const j=obj(state.data.jobs);
    return `<p class="muted project-rule">${t('过滤规则：仅保留 WorkDir 位于 ~/workspace/rlcs-replays 本身或其子目录的作业；缺失或未知路径排除。','Filter: only jobs whose WorkDir is ~/workspace/rlcs-replays itself or a descendant are included; missing or unknown paths are excluded.')} ${j.project_root?raw(j.project_root,'path'):''} · ${t('本次排除','Excluded')}: ${fmt(j.excluded_jobs)}</p>`;
  }
  function liveJobsCard() {
    const data=obj(state.data.jobs),rows=records(data.jobs).filter(j=>['RUNNING','COMPLETING'].includes(j.state_code));
    const body=rows.map(j=>{
      const L=limitSeconds(j.timelimit),E=num(j.elapsed_seconds)?j.elapsed_seconds:null;
      const remaining=L!==null&&E!==null?Math.max(0,L-E):null,pc=L>0&&E!==null?Math.min(100,E/L*100):null;
      const res=j.resource_type==='GPU'?`GPU × ${fmt(j.gpu_count)} · ${esc(str(j.gpu_model))}`:j.resource_type==='CPU'?'CPU':unknown();
      return `<article class="runjob"><div class="phase-title"><h3>${t('作业 ID','Job ID')} ${raw(j.jobid,'id')} · ${raw(j.name,'job')}</h3>${badge(j.state_code)}</div><p class="purpose">${t('用途','Purpose')}: ${esc(purpose(j.name))}</p><p>${t('资源','Resources')}: ${res} · CPU ${t('核数','cores')}: ${fmt(j.alloc_cpus)}</p><div class="runbar ${pc===null?'unknown':''}"><span style="width:${pc===null?0:pc}%"></span></div><p class="duration"><span>${t('申请时长','Time limit')}: <b>${duration(L)}</b></span><span>${t('已用','Elapsed')}: <b>${duration(E)}</b></span><span>${t('剩余','Remaining')}: <b>${duration(remaining)}</b></span></p><p class="meta">${t('开始时间','Started')}: ${esc(time(j.start))} · ${t('工作目录','WorkDir')}: ${raw(j.workdir,'path')}</p></article>`;
    }).join('');
    return `<div class="live-jobs">${card(t('运行中作业','Running jobs'),projectRule()+note(error('jobs'))+note(error('job_purposes'))+(body||empty(data.source?'当前记录中无运行中作业':'运行状态未知',data.source?'No running jobs in the current records':'Running status unknown'))+`<p class="meta">${t('来源','Source')}: ${esc(str(data.source))} · ${t('记录时间','Record time')}: ${esc(time(data.source?(data.cache_file_updated||data.updated):null))}</p><p class="muted">${t('时长格式为 时:分:秒。已用与剩余按来源快照计算，不随浏览器时钟推算；缓存不代表当前集群状态。','Durations are hours:minutes:seconds. Elapsed and remaining use the source snapshot; the browser does not extrapolate. Cached records do not establish current cluster state.')}</p>`)}</div>`;
  }
  function overviewContext() {
    const p=obj(state.data.phases),phases=records(p.phases),active=phases.filter(x=>['in_progress','running'].includes(x.status));
    const current=phases.find(x=>x.id===p.current_phase)||active[active.length-1]||phases.find(x=>x.status==='blocked')||phases.find(x=>x.status==='not_started')||phases[phases.length-1];
    const next=phases.find(x=>x.status==='not_started'),paper=obj(state.data.paper),j=obj(state.data.jobs),ideas=records(obj(state.data.ideas).ideas);
    const logs=Object.entries(obj(state.data.logs)).sort((a,b)=>(dateValue(b[1].mtime)||0)-(dateValue(a[1].mtime)||0));
    const recent=logs[0];
    return `<div class="kpis">${kpi(t('当前阶段','Current stage'),current?localized(current,'name'):null)}${kpi(t('下一阶段','Next stage'),next?localized(next,'name'):null)}${kpi(t('排队作业','Pending jobs'),j.source?records(j.jobs).filter(x=>x.state_code==='PENDING').length:null)}${kpi(t('候选存活 / 剪枝','Active / pruned ideas'),state.data.ideas?ideas.filter(x=>x.status!=='pruned').length+' / '+ideas.filter(x=>x.status==='pruned').length:null)}${kpi(t('论文总进度','Paper progress'),num(paper.progress)?fmt(paper.progress)+'%':null)}</div>`+
      card(t('最近活动','Recent activity'),recent?`<p>${raw(recent[0],'path')} · ${esc(time(recent[1].mtime))}</p><pre>${esc(String(localized(recent[1],'tail')||'').split('\n').slice(-12).join('\n'))}</pre><a href="#/session">${t('全部日志','All logs')}</a>`:empty('暂无会话记录','No session logs'));
  }
  function barChart(items,label,unit) {
    const valid=items.filter(x=>num(x.value));if(!valid.length)return empty();
    let low=Math.min(0,...valid.map(x=>x.value)),high=Math.max(0,...valid.map(x=>x.value));if(low===high)high=low+1;
    const w=1000,h=valid.length*48+100,left=260,right=150,x=v=>left+(v-low)/(high-low)*(w-left-right);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label+' ('+unit+')')}">`;
    for(let i=0;i<=4;i++){const v=low+(high-low)*i/4;svg+=`<path class="grid-line" d="M${x(v)} 20V${h-65}"/><text x="${x(v)}" y="${h-40}" text-anchor="middle">${fmt(v)}</text>`;}
    valid.forEach((r,i)=>{const y=28+i*48;svg+=`<text x="${left-12}" y="${y+20}" text-anchor="end">${esc(r.name.length>30?r.name.slice(0,29)+'…':r.name)}<title>${esc(r.name)}</title></text><rect x="${Math.min(x(0),x(r.value))}" y="${y}" width="${Math.max(1,Math.abs(x(r.value)-x(0)))}" height="30" fill="${r.color||palette[i%palette.length]}"/><text x="${x(r.value)+8}" y="${y+20}">${fmt(r.value)}</text>`;});
    return `<div class="chart-scroll">${svg}<text class="axis-title" x="${(left+w-right)/2}" y="${h-8}" text-anchor="middle">${esc(label+' ('+unit+')')}</text></svg></div>`;
  }
  function overview() {
    const j=obj(state.data.jobs), s=obj(j.summary), ideas=records(obj(state.data.ideas).ideas), counts={pass:0,fail:0,uncertain:0};
    ideas.forEach(i=>counts[finding(i.status)]++);
    const totals=obj(obj(state.data.dataset).totals);
    const highlights=records(obj(state.data.highlights).cards);
    const resourceFoot=t('已分配资源 × 实际已用时长；含 GPU 作业的 CPU。','Allocated resources × actual elapsed time; includes CPUs in GPU jobs.');
    return liveJobsCard()+overviewContext()+`<div class="kpis">${kpi(t('运行中作业','Running jobs'),s.running)}${kpi(t('已完成作业','Completed jobs'),s.completed)}${kpi(t('失败 / 取消 / 超时','Failed / cancelled / timed out'),s.failed)}${kpi(t('其他状态作业','Other job states'),s.other)}</div>`+
      card(t('资源用量','Resource usage'),`<div class="kpis">${kpi(t('CPU·小时','CPU·hours'),s.cpu_hours,t('缺少用量字段的作业：','Jobs missing usage fields: ')+fmt(s.cpu_missing_jobs))}${kpi(t('GPU·小时','GPU·hours'),s.gpu_hours,t('缺少用量字段的作业：','Jobs missing usage fields: ')+fmt(s.gpu_missing_jobs))}</div><p class="muted">${esc(resourceFoot)} ${esc(t('缺失项不计入合计，存在缺失时合计仅为已知部分。','Missing values are excluded; totals are partial when fields are missing.'))}</p><p class="meta">${esc(t('来源：','Source: ')+str(j.source))} · ${esc(t('读取时间：','Fetched: ')+time(j.updated))}${j.cache_file_updated?' · '+esc(t('缓存文件时间：','Cache file timestamp: ')+time(j.cache_file_updated)):''}</p>`)+
      `<div class="grid">${card(t('阶段进度','Stage progress'),phaseRows(records(obj(state.data.phases).phases)),t('未知进度不估算','Unknown progress is not estimated'))}${card(t('发现状态','Finding status'),`<div class="kpis">${['pass','fail','uncertain'].map(k=>kpi(t(...({pass:['通过','Passed'],fail:['未通过','Not passed'],uncertain:['不确定','Uncertain']}[k])),(error('ideas')||!state.data.ideas)?null:counts[k])).join('')}</div><p class="muted">${esc(t('仅将明确的通过、未通过判定计入对应类别；已选定、已完成、已剪枝等流程状态均计为不确定。','Only explicit pass/passed/confirmed and fail/failed/not_passed/rejected statuses count as decisions. Workflow states such as selected, done and pruned count as uncertain.'))}</p><a href="#/ideas">${t('查看全部发现 →','View all findings →')}</a>`)}</div>`+
      card(t('关键数字','Highlights'),`<div class="kpis">${kpi(t('已解析比赛','Parsed games'),totals.games,'status/dataset.json · totals.games')}${kpi(t('数据帧','Frames'),totals.frames,'status/dataset.json · totals.frames')}${kpi(t('赛季','Seasons'),totals.seasons,'status/dataset.json · totals.seasons')}${highlights.map(h=>kpi(localized(h,'label')||unknown(),localized(h,'value') || h.value,`${t('区间：','CI: ')}${Array.isArray(h.ci)?h.ci.map(value).join(' – '):value(h.ci)} · ${t('来源：','Source: ')}${localized(h,'source')}`)).join('')}</div>${!highlights.length?`<p class="meta">${t('尚未配置额外卡片。','No additional highlight cards configured.')}</p>`:''}`);
  }
  function jobsView() {
    const data=obj(state.data.jobs), rows=records(data.jobs).slice().sort((a,b)=>(b.state_code==='RUNNING')-(a.state_code==='RUNNING')||String(b.jobid).localeCompare(String(a.jobid),undefined,{numeric:true}));
    const headers=[t('作业 ID / 名称 / 用途','Job ID / name / purpose'),t('工作目录','WorkDir'),t('资源','Resources'),t('状态','State'),t('申请内存 / 峰值 RSS','Requested memory / peak RSS'),t('分区','Partition'),t('节点','Nodes'),t('已用时 / 申请时长','Elapsed / time limit'),t('开始时间','Start'),t('结束时间','End')];
    const body=rows.map(j=>[
      `<span class="mono">${raw(j.jobid,'id')}</span><span class="muted">${raw(j.name,'job')}</span><p>${esc(purpose(j.name))}</p>`,raw(j.workdir,'path'),
      j.resource_type==='GPU'?`GPU × ${fmt(j.gpu_count)}<span class="muted">${t('型号：','Model: ')}${esc(str(j.gpu_model))}${j.gpu_model_source==='partition'?' · '+t('分区映射','partition mapping'):''}</span><span class="muted">CPU × ${fmt(j.alloc_cpus)}</span>`:j.resource_type==='CPU'?`CPU · ${fmt(j.alloc_cpus)} ${t('核','cores')}`:unknown(),
      badge(j.state_code),
      `${esc(str(j.req_mem))} / ${esc(str(j.max_rss))}`,esc(str(j.partition)),esc(str(j.nodes)),`${esc(str(j.elapsed))} / ${esc(str(j.timelimit))}`,esc(time(j.start)),esc(time(j.end))
    ]);
    return liveJobsCard()+card(t('作业列表（新→旧）','Job list (newest first)'),`<p class="meta">${esc(t('来源：','Source: ')+str(data.source))} · ${esc(t('读取：','Fetched: ')+time(data.updated))}${data.cache_file_updated?' · '+esc(t('缓存文件：','Cache file: ')+time(data.cache_file_updated)):''}</p><p class="muted">${t('时间：CET（全年固定 UTC+1）。申请内存保留 Slurm 单位：c = 每 CPU，n = 每节点；峰值 RSS 未返回时显示未知。','Times: CET (fixed UTC+1 throughout the year). Requested memory keeps Slurm units: c = per CPU, n = per node. Missing peak RSS is unknown.')}</p>${rows.length?table(headers,body,'jobs-table'):empty('暂无作业记录','No job records',data.source?t('当前来源未返回作业。','The current source returned no jobs.'):t('sacct 与本地缓存均不可用。','Neither sacct nor the local cache is available.'))}`,t('60 秒结果缓存','60-second result cache'));
  }
  function ideasView() {
    const ideas=records(obj(state.data.ideas).ideas), filtered=ideas.filter(i=>(state.ideaFilter==='all'||finding(i.status)===state.ideaFilter)&&(state.ideaStatus==='all'||i.status===state.ideaStatus));
    return `<div class="controls"><label>${t('证据状态','Evidence status')}<select id="idea-filter">${[['all',t('全部','All')],['pass',t('通过','Passed')],['fail',t('未通过','Not passed')],['uncertain',t('不确定','Uncertain')]].map(([k,l])=>`<option value="${k}" ${state.ideaFilter===k?'selected':''}>${l}</option>`).join('')}</select></label><label>${t('流程状态','Workflow state')}<select id="idea-status">${['all',...new Set(ideas.map(i=>i.status))].map(k=>`<option value="${esc(k)}" ${state.ideaStatus===k?'selected':''}>${k==='all'?t('全部','All'):statusName(k)}</option>`).join('')}</select></label></div>`+(filtered.length?filtered.map(i=>`<section class="card finding ${finding(i.status)}"><div class="card-head"><h2>${esc(localized(i,'name')||i.id||unknown())}</h2>${badge(i.status)}</div><p>${esc(localized(i,'latest')||localized(i,'note'))}</p><p class="meta">${t('发现判定：','Finding decision: ')}${badge(i.status,true)}</p><details><summary>${t('动机、方法与参考','Motivation, method and references')}</summary>${['motivation','method','prune_reason'].map(k=>`<p>${esc(localized(i,k))}</p>`).join('')}${records(i.refs||i.inspiration_refs).map(r=>`<p>${link(localized(r,'title'),r.url)}</p>`).join('')}${i.best_metric?`<p>${esc(localized(i.best_metric,'name'))}: ${fmt(i.best_metric.value)}</p>`:''}</details></section>`).join(''):empty());
  }
  function link(label,url) { return /^https?:\/\//i.test(String(url)) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label||url)}</a>` : esc(label||unknown()); }
  function datasetView() {
    const d=obj(state.data.dataset), totals=obj(d.totals), seasons=records(d.seasons), split=obj(d.split_protocol);
    return `<div class="kpis">${kpi(t('比赛','Games'),totals.games)}${kpi(t('帧数','Frames'),totals.frames)}${kpi(t('采样率（帧/秒）','Sampling rate (frames/s)'),d.fps)}${kpi(t('解析失败','Parse failures'),totals.failed)}${kpi(t('下载前删除','Deleted before download'),totals.deleted)}</div>`+datasetCharts(d)+card(t('赛季分布','Seasons'),seasons.length?table([t('赛季','Season'),t('比赛','Games'),t('帧数','Frames'),'1v1','2v2','3v3'],seasons.map(s=>[esc(localized(s,'name')),fmt(s.games),fmt(s.frames),...['1v1','2v2','3v3'].map(m=>fmt(obj(s.modes)[m]))])):empty())+card(t('存储','Storage'),table([t('名称','Name'),t('路径','Path'),'GB'],records(d.storage).map(s=>[esc(localized(s,'name')),esc(str(s.path)),fmt(s.gb)])))+card(t('划分协议与备注','Split protocol and notes'),`<p>${esc(localized(split,'rule'))}</p><p>${esc(localized(split,'notes'))}</p>${arr(localized(d,'notes')).map(n=>`<p>${esc(typeof n==='object'?localized(n,'text'):n)}</p>`).join('')}`);
  }
  function datasetCharts(d) {
    const seasons=records(d.seasons),totals=obj(d.totals),modes=obj(totals.modes),keys=['1v1','2v2','3v3'];
    const other=num(totals.games)&&keys.every(k=>num(modes[k]))?totals.games-keys.reduce((n,k)=>n+modes[k],0):null;
    const items=keys.map(k=>({name:k,value:modes[k]})).concat([{name:t('其他 / 缺员','Other / incomplete teams'),value:other>=0?other:null}]);
    return card(t('赛季规模：比赛数','Season size: games'),barChart(seasons.map(x=>({name:localized(x,'name'),value:x.games})),t('比赛数','Games'),t('场','games')))+card(t('赛季规模：帧数','Season size: frames'),barChart(seasons.map(x=>({name:localized(x,'name'),value:x.frames})),t('帧数','Frames'),t('帧','frames')))+card(t('比赛模式','Game modes'),barChart(items,t('比赛数','Games'),t('场','games')));
  }
  const unitLabel = u => ({seconds:t('秒','seconds'),s:t('秒','seconds'),ms:t('毫秒','ms'),'log odds per second':t('对数优势/秒','log odds per second'),dimensionless:t('无量纲','dimensionless'),uu:t('游戏单位 uu','game units (uu)')})[u] || (u ? (cjk.test(u) && lang==='zh' ? u : term(u)) : unknown());
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
      const c={...ctx, taskKey:v.task||obj(v.scope).section||ctx.taskKey, splitKey:v.split||obj(v.scope).split||ctx.splitKey, unitsKey:v.units||v.unit||ctx.unitsKey, task:localized(v,'task')||localized(v.scope,'section')||ctx.task, split:localized(v,'split')||localized(v.scope,'split')||ctx.split, units:localized(v,'units')||localized(v,'unit')||ctx.units, status:v.status||ctx.status};
      const estimate=v.effect_size ?? v.effect ?? v.estimate ?? v.rho;
      const ci=interval(v), hasEffect=['effect_size','effect','estimate','rho'].some(k=>Object.hasOwn(v,k));
      if (hasEffect) {
        output.push({...c, estimate, ...ci, label:localized(v,'label')||localized(v,'name')||localized(v,'method')||resultLabel(path), source:path, raw:v});
      }
      // Real heterogeneity exports store coefficients and matching CIs in parallel maps.
      if (v.fixed && v.fixed_bootstrap_ci95) Object.entries(obj(v.fixed)).forEach(([key,est])=>{
        const ci=arr(v.fixed_bootstrap_ci95[key]); output.push({...c,estimate:est,lo:ci[0],hi:ci[1],method:'fixed_bootstrap_ci95',label:term(path.split('/').slice(-1)[0])+' / '+term(key),source:path+'/fixed/'+key,raw:{}});
      });
      Object.entries(v).forEach(([key,x])=>{if (x && typeof x==='object' && !key.endsWith('_zh') && !key.endsWith('_en') && !['fixed','fixed_bootstrap_ci95','slopes','total_slopes','covariance'].includes(key)) walk(x,path+'/'+key,c,depth+1);});
    }
    Object.entries(obj(state.data.results)).forEach(([file,r])=>walk(r,'results/'+file+'.json',{task:null,split:null,units:null,status:null}));
    return output;
  }
  function validEffect(r) { return [r.estimate,r.lo,r.hi].every(num) && r.lo<=r.hi; }
  function legend() { return `<div class="legend">${['pass','fail','uncertain'].map(k=>`<span>${badge(k,true)}</span>`).join('')}</div>`; }
  function forest(rows,unit) {
    if (!rows.length) return empty('没有可绘制的效应量与 95% 置信区间','No plottable effect estimates with 95% CIs',t('缺失、非数值或无效区间保留在表格中。','Missing, non-numeric or invalid intervals remain in the table.'));
    let lo=Math.min(0,...rows.flatMap(r=>[r.lo,r.estimate])), hi=Math.max(0,...rows.flatMap(r=>[r.hi,r.estimate]));
    const pad=(hi-lo||1)*.12;lo-=pad;hi+=pad;
    const w=1000,h=100+rows.length*60,left=300,right=50,bottom=h-65,x=v=>left+(v-lo)/(hi-lo)*(w-left-right);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(t('效应量及 95% 置信区间森林图','Forest plot of effect estimates and 95% confidence intervals'))}">`;
    for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4;svg+=`<path class="grid-line" d="M${x(v)} 15 V${bottom}"/><text x="${x(v)}" y="${bottom+25}" text-anchor="middle">${fmt(v)}</text>`;}
    svg+=`<path class="zero-line" d="M${x(0)} 15 V${bottom}"/><text x="${x(0)}" y="14" text-anchor="middle">0</text>`;
    rows.forEach((r,i)=>{const y=42+i*60,c={pass:'#80e6b1',fail:'#ffacb5',uncertain:'#ffdc85'}[finding(r.status)],tip=`${r.label}\n${t('效应量','Effect')}: ${fmt(r.estimate)} ${unitLabel(unit)}\n${t('95% 置信区间','95% CI')}: [${fmt(r.lo)}, ${fmt(r.hi)}]\n${t('状态','Status')}: ${statusName(r.status)}\n${r.source}`;
      svg+=`<text x="${left-20}" y="${y+5}" text-anchor="end">${esc(r.label.length>28?'…'+r.label.slice(-27):r.label)}<title>${esc(r.label)}</title></text><g tabindex="0" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><path d="M${x(r.lo)} ${y}H${x(r.hi)} M${x(r.lo)} ${y-7}v14 M${x(r.hi)} ${y-7}v14" stroke="${c}" stroke-width="3"/><circle cx="${x(r.estimate)}" cy="${y}" r="6" fill="${c}"/><rect x="${x(r.lo)-8}" y="${y-14}" width="${Math.max(16,x(r.hi)-x(r.lo)+16)}" height="28" fill="transparent"/><title>${esc(tip)}</title></g>`;
    });
    svg+=`<text class="axis-title" x="${(left+w-right)/2}" y="${h-10}" text-anchor="middle">${esc(t('效应量','Effect estimate')+' ('+unitLabel(unit)+') · '+t('95% 置信区间','95% CI'))}</text></svg>`;
    return `<div class="chart-scroll">${svg}</div>`;
  }
  function resultGroups() {
    const rows=effectRows(), groups=new Map();
    rows.forEach(r=>{
      // Group on original metadata, so translation cannot merge experiments or
      // reset the selected experiment. Missing units stay separate by metric.
      const k=JSON.stringify([r.taskKey||r.source.split('.json/')[0],r.splitKey||null,r.unitsKey||null,r.unitsKey?null:r.source]);
      if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);
    });
    return groups;
  }
  function resultPanel(selected) {
    const unit=selected[0].units;
    return card(t('效应量与 95% 置信区间','Effects and 95% confidence intervals'),legend()+forest(selected.filter(validEffect),unit)+`<p class="muted">${t('虚线为 0 参考线。颜色仅依据明确的发现状态；已拟合、计算成功、已完成不代表通过。单位缺失时不合并比较。','Dashed line: zero reference. Colors use explicit finding status only; fit/ok/done do not mean passed. Missing units are not pooled.')}</p>`)+card(t('结果明细','Result details'),table([t('实验 / 来源','Experiment / source'),t('效应量','Effect'),t('95% 置信区间 / 区间字段','95% CI / interval field'),t('单位','Unit'),t('发现状态 / 原始状态','Finding / original status')],selected.map(r=>[`${esc(r.label)}<span class="muted">${esc(r.source)}</span>`,fmt(r.estimate),`[${fmt(r.lo)}, ${fmt(r.hi)}]<span class="muted">${raw(r.method,'field')}${!validEffect(r)?' · '+t('无法绘制','Cannot plot'):''}</span>`,esc(unitLabel(r.units)),badge(r.status,true)+`<span class="muted">${esc(statusName(r.status))}</span>`])));
  }
  function resultsView() {
    const groups=resultGroups();
    if (!groups.size) return card(t('实验对比','Experiments'),empty('尚无效应量与区间数据','No effect estimates or intervals yet',t('读取 results/*.json 中的结构化效应量与 95% 置信区间。现有描述文字不会转换为数值。','Reads structured effects and 95% CIs from results/*.json. Narrative descriptions are not converted into numbers.'))+legacyResults());
    if (!groups.has(state.resultGroup))state.resultGroup=groups.keys().next().value;
    const selected=groups.get(state.resultGroup);
    return `<div class="controls"><label>${t('对比组','Comparison group')}<select id="result-group">${[...groups].map(([k,rs])=>`<option value="${esc(k)}" ${k===state.resultGroup?'selected':''}>${esc([str(rs[0].task),str(rs[0].split),unitLabel(rs[0].units),rs[0].units?'':rs[0].source].filter(Boolean).join(' · '))}</option>`).join('')}</select></label></div>`+resultPanel(selected)+legacyResults();
  }
  function legacyResults() {
    const groups=new Map();
    Object.entries(obj(state.data.results)).forEach(([file,data])=>{
      (Array.isArray(data)?data:Array.isArray(obj(data).results)?data.results:[data]).forEach(row=>{
        const r=obj(row);Object.entries(obj(r.metrics)).forEach(([metric,v])=>{
          if(!num(v))return;
          const unit=obj(r.metric_units)[metric]||r.units||null;
          // Absent units cannot establish comparability between source files.
          const key=JSON.stringify([r.task||file,r.split||null,metric,unit,unit?null:file]);
          if(!groups.has(key))groups.set(key,[]);groups.get(key).push({r,file,metric,value:v,unit});
        });
      });
    });
    if(!groups.size)return '';
    if(!groups.has(state.legacyGroup))state.legacyGroup=groups.keys().next().value;
    const rows=groups.get(state.legacyGroup),first=rows[0],metric=first.metric,unit=unitLabel(first.unit);
    const lower=r=>Array.isArray(r.lower_is_better)?r.lower_is_better.includes(metric):typeof r.lower_is_better==='boolean'?r.lower_is_better:null;
    const directions=rows.map(x=>lower(x.r)),comparable=first.unit&&directions.every(d=>d!==null&&d===directions[0]);
    const best=vals=>vals.length?(directions[0]?Math.min(...vals):Math.max(...vals)):null;
    const baseline=comparable?best(rows.filter(x=>x.r.is_baseline===true).map(x=>x.value)):null;
    const ours=comparable?best(rows.filter(x=>x.r.is_baseline===false).map(x=>x.value)):null;
    const delta=v=>baseline!==null?(v-baseline)*(directions[0]?-1:1):null;
    const label=x=>[localized(x.r,'task')||x.file,localized(x.r,'split')||unknown(),metricLabel({},x.metric),unitLabel(x.unit)].join(' · ');
    const toolbar=`<div class="controls"><label>${t('指标对比组','Metric comparison group')}<select id="legacy-group">${[...groups].map(([key,rs])=>`<option value="${esc(key)}" ${key===state.legacyGroup?'selected':''}>${esc(label(rs[0]))}</option>`).join('')}</select></label></div>`;
    return card(t('基线与方法指标','Baseline and method metrics'),toolbar+`<div class="kpis">${kpi(t('最佳基线','Best baseline'),baseline)}${kpi(t('本方法最优','Best method'),ours)}${kpi(t('方向归一化差值','Direction-normalized difference'),ours!==null?delta(ours):null)}</div>`+barChart(rows.map(x=>({name:localized(x.r,'method')||x.file,value:x.value,color:x.r.is_baseline===true?palette[0]:palette[3]})),metricLabel({},metric),unit)+table([t('方法','Method'),t('类型','Type'),t('指标','Metric'),t('数值','Value'),'Δ'],rows.map(x=>[esc(localized(x.r,'method')||x.file),x.r.is_baseline===true?t('基线','Baseline'):x.r.is_baseline===false?t('本方法','Method'):unknown(),esc(metricLabel({},metric)),fmt(x.value),fmt(delta(x.value))]))+`<p class="muted">${t('只在任务、划分、指标、已声明单位和方向一致时计算最佳基线及差值；正值表示改善。缺失或冲突时显示未知。原始指标柱状图不表示统计显著性。','Best baselines and differences require matching task, split, metric, declared units and direction; positive differences indicate improvement. Missing or conflicting metadata is unknown. Raw metric bars do not imply statistical significance.')}</p>`);
  }
  function splitName(s) { return ({train:t('训练集','Train'),val:t('验证集','Validation'),test:t('测试集','Test'),unspecified:t('未标注划分','Unspecified split')})[s]||term(s); }
  function axisLabel() { return ({step:t('训练步数（步）','Training step (steps)'),epoch:t('训练轮次（轮）','Epoch (epochs)'),time:t('时间（CET · UTC+1）','Time (CET · UTC+1)')})[state.axis]; }
  function metricLabel(meta, metric) { const names={loss:['损失','Loss'],elapsed_seconds:['已用秒数','Elapsed seconds'],replays_done:['已处理回放','Processed replays'],replays_planned:['计划回放','Planned replays'],val_series_available:['可用验证系列','Available validation series']}; return localized(obj(obj(meta).metric_labels)[metric],'label')||(names[metric]?t(...names[metric]):(terms[metric]?term(metric):unknown()+' ('+metric.replace(/[\u3000-\u9fff\uff00-\uffef]/g,'?')+')')); }
  function lineChart(series, label, unit) {
    const points=series.flatMap(s=>s.points).filter(p=>p[1]!==null);
    if (!points.length) return empty('当前选择没有有效采样点','No valid samples for this selection');
    const w=1000,h=440,left=110,right=35,top=50,bottom=100;
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    points.forEach(([x,y])=>{minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);});
    if(minX===maxX){minX-=.5;maxX+=.5;}if(minY===maxY){minY-=.5;maxY+=.5;}
    const padding=(maxY-minY)*.08;minY-=padding;maxY+=padding;
    const x=v=>left+(v-minX)/(maxX-minX)*(w-left-right),y=v=>top+(maxY-v)/(maxY-minY)*(h-top-bottom);
    const xFmt=v=>state.axis==='time'?new Intl.DateTimeFormat(lang==='zh'?'zh-CN':'en-GB',{timeZone:'Etc/GMT-1',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(v)):fmt(v);
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
  function runName(run,id) {const m=obj(run.meta);return m.name===id.split('/').pop()?id:(localized(m,'name')||id);}
  function trainingView() {
    const runs=obj(state.data.runs), ids=Object.keys(runs);
    if (!ids.length) return card(t('训练曲线','Training curves'),empty('暂无训练记录','No training records',t('扫描 runs/*/metrics.jsonl、robust/*/runs/*/metrics.jsonl 和 artifacts/*/runs/*/metrics.jsonl；需有指标及 step、epoch 或带时区的 time。','Scanning runs/*/metrics.jsonl, robust/*/runs/*/metrics.jsonl and artifacts/*/runs/*/metrics.jsonl; metrics require step, epoch or timezone-qualified time.')));
    const metrics=[...new Set(ids.flatMap(id=>records(runs[id].rows).flatMap(r=>Object.keys(r).filter(k=>!['step','epoch','time','split'].includes(k)&&num(r[k])))))].sort();
    const splits=[...new Set(ids.flatMap(id=>records(runs[id].rows).map(r=>r.split||'unspecified')))];
    if(state.selected===null)state.selected=new Set(ids);
    if(!metrics.includes(state.metric))state.metric=metrics.includes('loss')?'loss':metrics[0]||'';
    const controls=`<div class="controls"><label>${t('指标','Metric')}<select id="train-metric">${metrics.map(m=>`<option value="${esc(m)}" ${m===state.metric?'selected':''}>${esc(metricLabel(runs[ids[0]].meta,m))}</option>`).join('')}</select></label><label>${t('横轴','X axis')}<select id="train-axis">${[['step',t('步数','Step')],['epoch',t('轮次','Epoch')],['time',t('时间','Time')]].map(([k,l])=>`<option value="${k}" ${k===state.axis?'selected':''}>${l}</option>`).join('')}</select></label><label>${t('数据划分','Split')}<select id="train-split"><option value="all">${t('全部（分别绘制）','All (separate series)')}</option>${splits.map(s=>`<option value="${esc(s)}" ${s===state.split?'selected':''}>${esc(splitName(s))}</option>`).join('')}</select></label></div>`;
    const choices=card(t('训练运行','Training runs'),`<div class="controls"><button id="runs-all">${t('全选','Select all')}</button><button id="runs-none">${t('清空','Clear')}</button></div><div class="run-list">${ids.map(id=>`<label><input type="checkbox" data-run="${esc(id)}" ${state.selected.has(id)?'checked':''}> ${esc(runName(runs[id],id))}<span class="muted"> · ${fmt(records(runs[id].rows).length)} ${t('采样点','samples')}${runs[id].sampled?' · '+t('已抽样','sampled'):''}${runs[id].skipped_lines?' · '+fmt(runs[id].skipped_lines)+' '+t('无效行已跳过','invalid rows skipped'):''}</span></label>`).join('')}</div>`);
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
      bySplit.forEach((points,split)=>groups.get(key).series.push({name:runName(run,id)+' / '+splitName(split),points:points.sort((a,b)=>a[0]-b[0]),color:palette[color++%palette.length]}));
    });
    return (ids.some(id=>runs[id].reference)?note(t('本地审阅模式：包含明确选定的参考目录原始指标；这些是历史样例，不是实时集群数据。','Local review mode: includes original metrics from the explicitly selected reference directory. These are historical samples, not live cluster data.')):'')+controls+choices+([...groups.values()].filter(g=>g.series.some(s=>s.points.some(p=>p[1]!==null))).map(g=>card(g.label,lineChart(g.series,g.label,g.unit))).join('')||empty('当前选择没有有效采样点','No valid samples for this selection'))+`<p class="muted">${t('单位读取 meta.json 的 metric_units。缺失单位显示未知，并按运行分图；缺失指标不连线；不含所选指标的运行不绘图。悬停或用 Tab 聚焦数据点查看精确读数。','Units come from metric_units in meta.json. Missing units are unknown and plotted separately by run; missing metrics break the line; runs without the selected metric are omitted. Hover or Tab to a point for exact readings.')}</p>`;
  }
  function paperView() {
    const p=obj(state.data.paper),sections=records(p.sections),figures=records(p.figures),cit=obj(p.citations),pdf=obj(p.pdf);
    const partial=p.counts_partial?t('已读文件的小计','Subtotal of readable files'):'';
    const pdfPanel=card(t('论文 PDF','Paper PDF'),`<div class="kpis">${kpi(t('编译时间（PDF 创建元数据）','Compile time (PDF creation metadata)'),time(pdf.compiled))}${kpi(t('页数','Pages'),pdf.pages)}${kpi(t('PDF 文件提交','PDF file commit'),pdf.commit?pdf.commit.slice(0,12):null)}</div><p class="meta">${t('PDF 文件修改时间','PDF file modified')}: ${esc(time(pdf.modified))}</p>`+(pdf.available?`<p><a href="/paper.pdf" target="_blank" rel="noopener">${t('打开 PDF','Open PDF')}</a></p><iframe class="paper-pdf" src="/paper.pdf" title="${t('论文 PDF 预览','Paper PDF preview')}"></iframe>`:empty('尚无论文 PDF','No paper PDF available',t('等待 paper/main.pdf；不运行编译命令。','Waiting for paper/main.pdf; no compilation command is run.')))+`<p class="muted">${t('创建元数据缺失时编译时间未知；文件修改时间不等同于编译时间。PDF 文件提交不等同于编译所用源码提交。','Missing creation metadata leaves compile time unknown; file modification time is not compilation time. The PDF file commit does not establish the source commit used to compile it.')}</p>`);
    return (p.reference?note(t('本地审阅模式：论文源码来自参考目录。','Local review mode: manuscript sources come from the reference directory.')):'')+`<div class="kpis">${kpi(t('总进度','Overall progress'),num(p.progress)?fmt(p.progress)+'%':null,t('明确完成章节 / 全部章节','Explicitly completed / all sections'))}${kpi(t('章节完成','Sections complete'),p.completed_sections,partial)}${kpi(t('字数（近似）','Word count (approximate)'),p.words,partial)}${kpi(t('图数','Figures'),p.figure_count,partial)}${kpi(t('论文最新提交','Latest paper commit'),p.commit?p.commit.slice(0,12):null)}</div>`+pdfPanel+
      card(t('章节进度','Section progress'),`<p class="muted">${t('自动扫描 paper/main.tex 及其 input/include。字数按英文词和汉字计数，图数按 figure 环境计数。含正文为草稿；TODO 保持草稿；仅章节内明确的 % dashboard-status: done 标记计为完成。缺失文件使总进度未知。','Automatically scans paper/main.tex and its input/include files. Counts English tokens and CJK characters; figures count figure environments. Text is a draft; TODOs remain drafts. Only explicit per-section % dashboard-status: done markers count as completed. Missing files make overall progress unknown.')}</p>`+(sections.length?table([t('章节','Section'),t('状态','Status'),t('字数','Words'),t('图数','Figures'),t('最新提交','Latest commit'),t('源文件','Source file')],sections.map(x=>[esc(localized(x,'name')),badge(x.status),fmt(x.words),fmt(x.figure_count),esc(x.commit?x.commit.slice(0,12):unknown()),raw(x.path,'path')])):empty('暂无论文源码','No manuscript sources',t('等待 paper/main.tex。','Waiting for paper/main.tex.'))))+
      card(t('投稿目标与引用','Target venue and citations'),`<p>${esc(localized(p,'target')||unknown())}</p><p>${esc(localized(p,'notes'))}</p><div class="kpis">${kpi(t('引用已核验','Verified citations'),cit.verified)}${kpi(t('引用总数','Total citations'),cit.total)}</div>`)+
      card(t('图表清单','Figures'),figures.length?table([t('编号','ID'),t('标题','Title'),t('状态','Status'),t('路径 / 备注','Path / notes')],figures.map(f=>[esc(str(f.id)),esc(localized(f,'title')||localized(f,'name')),badge(f.status),raw(f.path,'path')])):empty());
  }
  function logsView() {
    const logs=obj(state.data.logs),names=Object.keys(logs);
    if (!names.length)return card(t('会话日志','Session logs'),empty());
    if (!names.includes(state.log))state.log=names[0];
    const record=logs[state.log];
    return card(t('会话日志','Session logs'),`<div class="controls"><label>${t('日志文件','Log file')}<select id="log-file">${names.map(n=>`<option ${n===state.log?'selected':''}>${esc(n)}</option>`).join('')}</select></label><label>${t('筛选日志行','Filter log lines')}<input type="search" id="log-filter" value="${esc(state.logFilter)}"></label></div><p class="meta">${esc(time(record.mtime))}${record.truncated?' · '+t('仅显示末尾 20 KB','Last 20 KB only'):''}</p><pre id="log-output">${esc(logLines())}</pre><p class="meta">${t('带时区的日志时间转为 CET；未标注时区的时间保留原样。缺少当前语言文本时标为未翻译。','Timezone-qualified log timestamps convert to CET; unqualified times remain unchanged. Text unavailable in this language is marked untranslated.')}</p>`);
  }
  function logLines() { return String(localized(obj(obj(state.data.logs)[state.log]),'tail')||'').replace(/\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})/g,match=>time(match)).split('\n').filter(line=>line.toLowerCase().includes(state.logFilter.toLowerCase())).join('\n')||t('没有匹配的日志行','No matching log lines'); }
  function literatureView() {
    const items=records(obj(state.data.literature).items);
    return card(t('参考文献','Literature'),items.length?table([t('标题','Title'),t('期刊 / 会议','Venue'),t('年份','Year')],items.map(r=>[link(localized(r,'title'),String(r.doi_or_url||'').startsWith('10.')?'https://doi.org/'+r.doi_or_url:r.doi_or_url||r.url),esc(localized(r,'venue')),esc(str(r.year))])):empty());
  }
  function inlineMarkdown(text) {
    const tokens=[];
    let value=String(text).replace(/`([^`]+)`/g,(_,code)=>{tokens.push('<code>'+esc(code)+'</code>');return '\u0000'+(tokens.length-1)+'\u0000';});
    value=value.replace(/!?\[([^\]]+)\]\(([^\s)]+)\)/g,(match,label,url)=>{tokens.push(match.startsWith('!')?esc(label):link(label,url));return '\u0000'+(tokens.length-1)+'\u0000';});
    value=esc(value).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/~~([^~]+)~~/g,'<del>$1</del>');
    return value.replace(/\u0000(\d+)\u0000/g,(_,index)=>tokens[Number(index)]||'');
  }
  function markdown(source) {
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
    const text=localized(typeof state.data.progress==='string'?{text:state.data.progress}:state.data.progress,'text');
    // Source HTML and image references remain escaped; no external resources load.
    return card(t('研究进度文档','Research progress document'),text?markdown(text):empty(),'PROGRESS.md');
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
    $('language').textContent=t('切换为英语','Switch to Chinese');$('language').setAttribute('aria-label',t('切换为英语','Switch to Chinese'));
    $('footer').textContent=t('原生 SVG · 无外部依赖 · CET（UTC+1）','Native SVG · No external dependencies · CET (UTC+1)');
    $('sync').textContent=t('主机：','Host: ')+str(obj(state.data.host).host)+' · '+t('最近同步：','Last sync: ')+time(state.last);
    const failures=Object.keys(state.errors);$('connection').textContent=state.busy?t('正在同步…','Syncing…'):failures.length?t('部分数据不可用','Some data unavailable'):t('本地服务已连接','Local service connected');
    const apiNames={overview:['phases','ideas','dataset','highlights'],training:['runs'],session:['logs'],jobs:[],results:['results']};
    const messages=(apiNames[state.view]||[state.view]).map(error).filter(Boolean);
    $('api-notice').hidden=!messages.length;$('api-notice').textContent=messages.join(' · ');
    $('tooltip').hidden=true;
    try{$('view').innerHTML=renderers[state.view]();}catch(e){$('view').innerHTML=empty('无法显示当前数据','Cannot display current data',t('请检查 JSON 字段格式。','Check the JSON field types.'));console.error(e);}
    [['idea-filter','ideaFilter'],['idea-status','ideaStatus'],['legacy-group','legacyGroup'],['result-group','resultGroup'],['train-metric','metric'],['train-axis','axis'],['train-split','split'],['log-file','log']].forEach(([id,key])=>bind(id,key));
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
    await Promise.all(['host','phases','dataset','ideas','highlights','jobs','job_purposes','results','runs','logs','paper','literature','progress'].map(fetchData));
    state.last=obj(state.data.host).time||state.last;state.busy=false;state.next=Date.now()+30000;render();
  }
  $('language').onclick=()=>{lang=lang==='zh'?'en':'zh';try{localStorage.setItem('dash-language',lang);}catch(_){}render();tick();};
  $('refresh').onclick=refresh;window.addEventListener('hashchange',route);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')$('tooltip').hidden=true;});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  function tick(){$('clock').textContent=time(Date.now());if(!document.hidden&&Date.now()>=state.next)refresh();}
  route();refresh();tick();setInterval(tick,1000);
})();
