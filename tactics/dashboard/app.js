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
  // Exact-source translations for legacy APIs without bilingual sibling fields.
  // Changed source text never inherits a translation by ID or position.
  const proseTranslations = {
  "Native-schema audit": {
    "zh": "原生数据结构审计",
    "en": "Native-schema audit"
  },
  "audit": {
    "zh": "审计",
    "en": "audit"
  },
  "all": {
    "zh": "全部",
    "en": "All"
  },
  "Source reference counts are not treated as measured fixture/cluster counts.": {
    "zh": "来源中的参考计数不视为实测样例或集群计数。",
    "en": "Source reference counts are not treated as measured fixture/cluster counts."
  },
  "134 parse failures and 26 deleted downloads are separate; never subtract them again from parsed games.": {
    "zh": "134 个解析失败与 26 个已删除下载是两类记录；不得再从已解析比赛数中扣除。",
    "en": "134 parse failures and 26 deleted downloads are separate; never subtract them again from parsed games."
  },
  "per_replay_decoded": {
    "zh": "逐回放解码",
    "en": "per_replay_decoded"
  },
  "main": {
    "zh": "主分析",
    "en": "main"
  },
  "quantile_10": {
    "zh": "分位数_10",
    "en": "quantile_10"
  },
  "quantile_20": {
    "zh": "分位数_20",
    "en": "quantile_20"
  },
  "quantile_30": {
    "zh": "分位数_30",
    "en": "quantile_30"
  },
  "exclude_kickoff_3s": {
    "zh": "排除开球后_3秒",
    "en": "exclude_kickoff_3s"
  },
  "exclude_overtime": {
    "zh": "排除加时",
    "en": "exclude_overtime"
  },
  "reference_rlcs-21-22": {
    "zh": "参考赛季_rlcs-21-22",
    "en": "reference_rlcs-21-22"
  },
  "reference_rlcs-22-23": {
    "zh": "参考赛季_rlcs-22-23",
    "en": "reference_rlcs-22-23"
  },
  "reference_rlcs-2024": {
    "zh": "参考赛季_rlcs-2024",
    "en": "reference_rlcs-2024"
  },
  "leading": {
    "zh": "领先",
    "en": "leading"
  },
  "tied": {
    "zh": "平局",
    "en": "tied"
  },
  "trailing": {
    "zh": "落后",
    "en": "Trailing"
  },
  "own_half": {
    "zh": "己方半场",
    "en": "own_half"
  },
  "opponent_half": {
    "zh": "对方半场",
    "en": "opponent_half"
  },
  "descriptive decomposition, not causal mediation": {
    "zh": "描述性分解，非因果中介分析",
    "en": "descriptive decomposition, not causal mediation"
  },
  "whole series": {
    "zh": "完整系列赛",
    "en": "whole series"
  },
  "val": {
    "zh": "验证集",
    "en": "Validation"
  },
  "Predeclared three-test Holm family": {
    "zh": "预先声明的三项检验 Holm 族",
    "en": "Predeclared three-test Holm family"
  },
  "confirmation": {
    "zh": "确认性分析",
    "en": "confirmation"
  },
  "RQ1 grammar, RQ3 late-by-score coverage, RQ4 persistence. Missing tests retain family slots.": {
    "zh": "RQ1 语法、RQ3 末段与比分交互下的覆盖、RQ4 持续性。缺失检验仍保留其在检验族中的位置。",
    "en": "RQ1 grammar, RQ3 late-by-score coverage, RQ4 persistence. Missing tests retain family slots."
  },
  "test": {
    "zh": "测试集",
    "en": "Test"
  },
  "Pooled exploratory BH": {
    "zh": "合并探索性 BH 校正",
    "en": "Pooled exploratory BH"
  },
  "exploratory_multiplicity": {
    "zh": "探索性多重检验",
    "en": "exploratory_multiplicity"
  },
  "The pooled q_value is the reported exploratory correction; per-vocabulary q-values are diagnostics only. No exploratory finding is confirmatory.": {
    "zh": "合并的 q_value 是报告采用的探索性校正；各词表的 q 值仅作诊断。任何探索性发现均不属于确认性证据。",
    "en": "The pooled q_value is the reported exploratory correction; per-vocabulary q-values are diagnostics only. No exploratory finding is confirmatory."
  },
  "Audited compact extraction": {
    "zh": "经审计的紧凑数据提取",
    "en": "Audited compact extraction"
  },
  "extract": {
    "zh": "提取",
    "en": "extract"
  },
  "NaN context stays unknown; no frame-wise complete-case mode filter.": {
    "zh": "NaN 情境值保持未知；不按逐帧完整案例筛选模式。",
    "en": "NaN context stays unknown; no frame-wise complete-case mode filter."
  },
  "seconds": {
    "zh": "秒",
    "en": "seconds"
  },
  "log odds per second": {
    "zh": "对数优势/秒",
    "en": "log odds per second"
  },
  "whole series, all available games and focal views": {
    "zh": "完整系列赛，包含所有可用比赛与焦点队伍视角",
    "en": "whole series, all available games and focal views"
  },
  "P5a only": {
    "zh": "仅 P5a",
    "en": "P5a only"
  },
  "OLS; series-clustered CR1 t tests; percentile whole-series bootstrap intervals": {
    "zh": "OLS；按系列赛聚类的 CR1 t 检验；完整系列赛 bootstrap 百分位区间",
    "en": "OLS; series-clustered CR1 t tests; percentile whole-series bootstrap intervals"
  },
  "series_id; both teams and every available replay remain together": {
    "zh": "series_id；两队及每个可用回放始终共同保留",
    "en": "series_id; both teams and every available replay remain together"
  },
  "train 2021-22/22-23/2024 · val 2025 · test 2026": {
    "zh": "训练集 2021-22/22-23/2024 · 验证集 2025 · 测试集 2026",
    "en": "train 2021-22/22-23/2024 · val 2025 · test 2026"
  },
  "series": {
    "zh": "系列赛",
    "en": "Series"
  },
  "Series-adjusted geometric cover": {
    "zh": "按系列赛调整的几何覆盖",
    "en": "Series-adjusted geometric cover"
  },
  "pressure": {
    "zh": "压力",
    "en": "pressure"
  },
  "Primary response is uncovered fraction; depth, coverage count and spacing are exploratory. Known-score live regulation only.": {
    "zh": "主响应为无覆盖比例；深度、覆盖人数与间距为探索性指标。仅纳入比分已知的常规时间活球片段。",
    "en": "Primary response is uncovered fraction; depth, coverage count and spacing are exploratory. Known-score live regulation only."
  },
  "OLS with series-clustered CR1 uncertainty": {
    "zh": "OLS，采用按系列赛聚类的 CR1 不确定性估计",
    "en": "OLS with series-clustered CR1 uncertainty"
  },
  "train-frozen HGB / series-cross-fitted AIPW state audit": {
    "zh": "训练集冻结的 HGB / 按系列赛交叉拟合的 AIPW 状态审计",
    "en": "train-frozen HGB / series-cross-fitted AIPW state audit"
  },
  "pushup_dr": {
    "zh": "前压双重稳健分析",
    "en": "pushup_dr"
  },
  "equal-series observed risk; descriptive dose association, no dose intervention": {
    "zh": "系列赛等权的观测风险；描述性剂量关联，非剂量干预",
    "en": "equal-series observed risk; descriptive dose association, no dose intervention"
  },
  "train_oof": {
    "zh": "训练集折外",
    "en": "train_oof"
  },
  "Each arm averages its arm-present series; arm targets may differ from the common retained-series DR target": {
    "zh": "每组对该组出现的系列赛取平均；各组目标总体可能不同于共同保留系列赛的双重稳健目标总体",
    "en": "Each arm averages its arm-present series; arm targets may differ from the common retained-series DR target"
  },
  "Exploratory development model-dependent contrasts; structural positivity fails for depth treatment with full geometry controls.": {
    "zh": "探索性开发阶段的模型依赖对比；完整几何控制下的深度处理存在结构性正性失败。",
    "en": "Exploratory development model-dependent contrasts; structural positivity fails for depth treatment with full geometry controls."
  },
  "train-frozen HGB / series-cross-fitted AIPW initiation audit": {
    "zh": "训练集冻结的 HGB / 按系列赛交叉拟合的 AIPW 启动审计",
    "en": "train-frozen HGB / series-cross-fitted AIPW initiation audit"
  },
  "Observational initiation landmark contrasts; no-unmeasured-confounding and noninformative selection assumptions remain unverified even when overlap gates pass.": {
    "zh": "观测性启动时点对比；即使通过重叠门槛，无未测混杂与非信息性选择假设仍未经验证。",
    "en": "Observational initiation landmark contrasts; no-unmeasured-confounding and noninformative selection assumptions remain unverified even when overlap gates pass."
  },
  "whole series, stratified by season; all models refitted": {
    "zh": "完整系列赛，按赛季分层；重新拟合所有模型",
    "en": "whole series, stratified by season; all models refitted"
  },
  "pushup_possession": {
    "zh": "控球条件下的前压",
    "en": "pushup_possession"
  },
  "possession-conditioned train-frozen HGB / AIPW initiation": {
    "zh": "控球条件下训练集冻结的 HGB / AIPW 启动分析",
    "en": "possession-conditioned train-frozen HGB / AIPW initiation"
  },
  "paired whole series, union of retained series": {
    "zh": "配对完整系列赛，采用保留系列赛的并集",
    "en": "paired whole series, union of retained series"
  },
  "Preregistered development sensitivity; R4 nonestimable strata are not interpreted; causal language requires unchanged original gates and assumptions.": {
    "zh": "预注册开发阶段敏感性分析；R4 无法估计的分层不作解释；使用因果表述须满足未改动的原始门槛与假设。",
    "en": "Preregistered development sensitivity; R4 nonestimable strata are not interpreted; causal language requires unchanged original gates and assumptions."
  },
  "brainstorm_quick_screen": {
    "zh": "创新想法快速筛查",
    "en": "brainstorm_quick_screen"
  },
  "screen": {
    "zh": "筛查",
    "en": "screen"
  },
  "Fixed-penalty regularized multinomial likelihood": {
    "zh": "固定惩罚的正则化多项似然",
    "en": "Fixed-penalty regularized multinomial likelihood"
  },
  "Player-event bins are calibration summaries; all inferential resampling is by series.": {
    "zh": "球员事件分箱仅作校准汇总；所有推断重采样均以系列赛为单位。",
    "en": "Player-event bins are calibration summaries; all inferential resampling is by series."
  },
  "Complete receiver-response blocks swapped within same-roster/opponent cross-series context-matched pairs": {
    "zh": "在同阵容/对手、跨系列赛且情境匹配的配对中交换完整接收方响应块",
    "en": "Complete receiver-response blocks swapped within same-roster/opponent cross-series context-matched pairs"
  },
  "Zero conditional matched contrast": {
    "zh": "条件匹配对比为零",
    "en": "Zero conditional matched contrast"
  },
  "brainstorm_screen_v2": {
    "zh": "创新想法筛查第 v2 版",
    "en": "brainstorm_screen_v2"
  },
  "gain (opposite uu/s per uu/s)": {
    "zh": "增益（反向 uu/秒，每 uu/秒）",
    "en": "gain (opposite uu/s per uu/s)"
  },
  "uu width": {
    "zh": "宽度 uu",
    "en": "uu width"
  },
  "concession probability difference": {
    "zh": "失球概率差",
    "en": "concession probability difference"
  },
  "bits/action": {
    "zh": "比特/动作",
    "en": "bits/action"
  },
  "exactly-one probability difference": {
    "zh": "恰好一人的概率差",
    "en": "exactly-one probability difference"
  },
  "Spearman rho": {
    "zh": "Spearman 相关系数",
    "en": "Spearman rho"
  },
  "slowing probability interaction": {
    "zh": "减速概率交互",
    "en": "slowing probability interaction"
  },
  "observed/independent pair-shortage ratio": {
    "zh": "观测/独立基线的双人资源短缺比",
    "en": "observed/independent pair-shortage ratio"
  },
  "uu excursion (low minus high diversity)": {
    "zh": "回撤距离 uu（低多样性减高多样性）",
    "en": "uu excursion (low minus high diversity)"
  },
  "uu clearance change": {
    "zh": "通道净宽变化 uu",
    "en": "uu clearance change"
  },
  "response probability difference": {
    "zh": "响应概率差",
    "en": "response probability difference"
  },
  "lag-0.2s autocorrelation difference": {
    "zh": "滞后 0.2秒的自相关差",
    "en": "lag-0.2s autocorrelation difference"
  },
  "rear/front response gain": {
    "zh": "后排/前排响应增益",
    "en": "rear/front response gain"
  },
  "peak-to-trough change in linear pulse probability per 0.1 s": {
    "zh": "每 0.1 秒线性脉冲概率的峰谷变化",
    "en": "peak-to-trough change in linear pulse probability per 0.1 s"
  },
  "pulse probability modulation excess per 0.1s": {
    "zh": "每 0.1秒脉冲概率调制超额量",
    "en": "pulse probability modulation excess per 0.1s"
  },
  "seconds capped latency": {
    "zh": "截顶延迟（秒）",
    "en": "seconds capped latency"
  },
  "uu ball progress per doubling rarity": {
    "zh": "稀有度每翻倍的球推进距离 uu",
    "en": "uu ball progress per doubling rarity"
  },
  "distinct-sector probability difference": {
    "zh": "不同扇区占用概率差",
    "en": "distinct-sector probability difference"
  },
  "Node-local shard staging": {
    "zh": "节点本地分片暂存",
    "en": "Node-local shard staging"
  },
  "stage": {
    "zh": "暂存",
    "en": "stage"
  },
  "Context-standardized independent-series fingerprints": {
    "zh": "情境标准化的独立系列赛指纹",
    "en": "Context-standardized independent-series fingerprints"
  },
  "style": {
    "zh": "风格",
    "en": "style"
  },
  "Positive persistence effect means different-roster distance exceeds within-roster distance. Roster permutation matches region, event exposure, series-count band and context support.": {
    "zh": "持续性效应为正表示异阵容距离大于同阵容距离。阵容置换匹配赛区、赛事暴露、系列赛数量区间与情境支持。",
    "en": "Positive persistence effect means different-roster distance exceeds within-roster distance. Roster permutation matches region, event exposure, series-count band and context support."
  },
  "Calendar drift is not a patch effect; token mixture and within-token geometry saved separately. No out-of-support claim without calibrated vocabulary support.": {
    "zh": "日历时间漂移不是版本补丁效应；词元构成与词元内几何分别保存。词表支持未经校准时，不作支持范围外的结论。",
    "en": "Calendar drift is not a patch effect; token mixture and within-token geometry saved separately. No out-of-support claim without calibrated vocabulary support."
  },
  "Masked invariant GRU + k-means": {
    "zh": "掩码不变性 GRU + k-means",
    "en": "Masked invariant GRU + k-means"
  },
  "tokens": {
    "zh": "词元",
    "en": "tokens"
  },
  "Frozen training codebook; 2025 selection; 2026 only opened with --evaluate-test": {
    "zh": "冻结训练词表；2025 用于选择；仅在 --evaluate-test 下开放 2026",
    "en": "Frozen training codebook; 2025 selection; 2026 only opened with --evaluate-test"
  },
  "Train-fit smoothed jump chain + empirical state dwell; distribution-preserving, not exact transition counts; empirical training dwells include boundary-censored runs and final simulated dwell is censored at original length": {
    "zh": "训练集拟合的平滑跳链 + 经验状态停留时间；保持分布而非精确转移次数；经验训练停留时间包含边界删失游程，最终模拟停留在原始长度处删失",
    "en": "Train-fit smoothed jump chain + empirical state dwell; distribution-preserving, not exact transition counts; empirical training dwells include boundary-censored runs and final simulated dwell is censored at original length"
  },
  "Handcrafted geometry + k-means": {
    "zh": "手工几何特征 + k-means",
    "en": "Handcrafted geometry + k-means"
  },
  "Held-out global grammar test; motifs exploratory; nonoverlapping windows and complete-series uncertainty": {
    "zh": "留出集全局语法检验；母题为探索性；窗口不重叠，不确定性以完整系列赛估计",
    "en": "Held-out global grammar test; motifs exploratory; nonoverlapping windows and complete-series uncertainty"
  },
  "P3 descriptive research figures": {
    "zh": "P3 描述性研究图表",
    "en": "P3 descriptive research figures"
  },
  "viz": {
    "zh": "可视化",
    "en": "viz"
  },
  "Descriptive figures. Empty panels explicitly show unavailable or insufficient artifacts.": {
    "zh": "描述性图表。空面板明确标注产物不可用或不足。",
    "en": "Descriptive figures. Empty panels explicitly show unavailable or insufficient artifacts."
  },
  "event": {
    "zh": "赛事",
    "en": "event"
  },
  "season": {
    "zh": "赛季",
    "en": "season"
  },
  "GPU models verified by nvidia-smi output in probe job logs; nodes not listed show model unknown.": {
    "zh": "GPU 型号由探测作业日志中的 nvidia-smi 输出验证；未列出的节点显示型号未知。",
    "en": "GPU models verified by nvidia-smi output in probe job logs; nodes not listed show model unknown."
  },
  "TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2 (IEEE Transactions on Games 2026)": {
    "zh": "TAGNet：用于职业 Counter-Strike 2 防守战术模式识别的时序注意力图网络（IEEE 游戏汇刊 2026）",
    "en": "TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2 (IEEE Transactions on Games 2026)"
  },
  "TS2Vec: Towards Universal Representation of Time Series (AAAI 2022)": {
    "zh": "TS2Vec：迈向通用时间序列表示（AAAI 2022）",
    "en": "TS2Vec: Towards Universal Representation of Time Series (AAAI 2022)"
  },
  "Coordinated Multi-Agent Imitation Learning (ICML 2017)": {
    "zh": "协同多智能体模仿学习（ICML 2017）",
    "en": "Coordinated Multi-Agent Imitation Learning (ICML 2017)"
  },
  "Generating Multi-Agent Trajectories using Programmatic Weak Supervision (ICLR 2019)": {
    "zh": "使用程序化弱监督生成多智能体轨迹（ICLR 2019）",
    "en": "Generating Multi-Agent Trajectories using Programmatic Weak Supervision (ICLR 2019)"
  },
  "Actions Speak Louder than Goals: Valuing Player Actions in Soccer (KDD 2019)": {
    "zh": "行动胜于进球：足球球员动作价值评估（KDD 2019）",
    "en": "Actions Speak Louder than Goals: Valuing Player Actions in Soccer (KDD 2019)"
  },
  "Implicit Coordination Dynamics: A Synchrony-Based Study on Team Positioning and Performance in Competitive Dota 2 (IEEE Transactions on Games 2025)": {
    "zh": "隐式协调动态：基于同步性的竞技 Dota 2 团队站位与表现研究（IEEE 游戏汇刊 2025）",
    "en": "Implicit Coordination Dynamics: A Synchrony-Based Study on Team Positioning and Performance in Competitive Dota 2 (IEEE Transactions on Games 2025)"
  },
  "Deep Sets (NeurIPS 2017)": {
    "zh": "深度集合（NeurIPS 2017）",
    "en": "Deep Sets (NeurIPS 2017)"
  },
  "A Behavioral Pattern Mining Approach to Model Player Skills in Rocket League (IEEE CoG 2020)": {
    "zh": "基于行为模式挖掘的 Rocket League 玩家技能建模（IEEE CoG 2020）",
    "en": "A Behavioral Pattern Mining Approach to Model Player Skills in Rocket League (IEEE CoG 2020)"
  },
  "Node-local data staging": {
    "zh": "节点本地数据暂存",
    "en": "Node-local data staging"
  },
  "Avoid random GPFS reads during computation": {
    "zh": "避免计算期间随机读取 GPFS",
    "en": "Avoid random GPFS reads during computation"
  },
  "Data and parser semantics audit": {
    "zh": "数据与解析器语义审计",
    "en": "Data and parser semantics audit"
  },
  "Audited 3v3 extraction": {
    "zh": "经审计的 3v3 提取",
    "en": "Audited 3v3 extraction"
  },
  "RQ1 rotation grammar": {
    "zh": "RQ1 轮转语法",
    "en": "RQ1 rotation grammar"
  },
  "validation_reconstruction": {
    "zh": "验证集重构",
    "en": "Validation reconstruction"
  },
  "Pressure redistributes cover": {
    "zh": "压力使覆盖职责重新分配",
    "en": "Pressure redistributes cover"
  },
  "interaction": {
    "zh": "交互项",
    "en": "Interaction"
  },
  "Roster style persists across series": {
    "zh": "阵容风格在系列赛间持续存在",
    "en": "Roster style persists across series"
  },
  "need >=2 eligible rosters matched on region/event exposure/series-count band, >=2 series per half, and common context support": {
    "zh": "需要 >=2 个在赛区/赛事暴露/系列赛数量区间上匹配的合格阵容，每半区间 >=2 个系列赛，并具备共同情境支持",
    "en": "need >=2 eligible rosters matched on region/event exposure/series-count band, >=2 series per half, and common context support"
  },
  "Initial interpretability atlas": {
    "zh": "初步可解释性图谱",
    "en": "Initial interpretability atlas"
  },
  "Inspectable geometry and uncertainty-aware summaries": {
    "zh": "可检查的几何与纳入不确定性的汇总",
    "en": "Inspectable geometry and uncertainty-aware summaries"
  },
  "learned vocabulary K=6": {
    "zh": "学习词表 K=6",
    "en": "learned vocabulary K=6"
  },
  "silhouette": {
    "zh": "轮廓系数",
    "en": "silhouette"
  },
  "Unsupervised development selection; no hypothesis p-value used": {
    "zh": "无监督开发阶段选择；不使用假设检验 p 值",
    "en": "Unsupervised development selection; no hypothesis p-value used"
  },
  "learned vocabulary K=8": {
    "zh": "学习词表 K=8",
    "en": "learned vocabulary K=8"
  },
  "Lower validation selection score than chosen K": {
    "zh": "验证集选择得分低于选定的 K",
    "en": "Lower validation selection score than chosen K"
  },
  "learned vocabulary K=12": {
    "zh": "学习词表 K=12",
    "en": "learned vocabulary K=12"
  },
  "learned vocabulary K=16": {
    "zh": "学习词表 K=16",
    "en": "learned vocabulary K=16"
  },
  "handcrafted vocabulary K=6": {
    "zh": "手工词表 K=6",
    "en": "handcrafted vocabulary K=6"
  },
  "handcrafted vocabulary K=8": {
    "zh": "手工词表 K=8",
    "en": "handcrafted vocabulary K=8"
  },
  "handcrafted vocabulary K=12": {
    "zh": "手工词表 K=12",
    "en": "handcrafted vocabulary K=12"
  },
  "handcrafted vocabulary K=16": {
    "zh": "手工词表 K=16",
    "en": "handcrafted vocabulary K=16"
  },
  "L1 +1.37s [1.02,1.70]; measurement gate FAILED -> appendix only": {
    "zh": "L1 +1.37秒 [1.02,1.70]；测量门槛未通过 → 仅放附录",
    "en": "L1 +1.37s [1.02,1.70]; measurement gate FAILED -> appendix only"
  },
  "job 41105069": {
    "zh": "作业 41105069",
    "en": "job 41105069"
  },
  "medium: habit rho 0.36-0.74 all q<0.001; retention not estimable (same-roster n=3)": {
    "zh": "中规模：习惯相关系数 0.36-0.74，所有 q<0.001；留存效应无法估计（同阵容 n=3）",
    "en": "medium: habit rho 0.36-0.74 all q<0.001; retention not estimable (same-roster n=3)"
  },
  "post hoc clip±3: concede20s -0.037 [-0.049,-0.025] 2000/2000; descriptive": {
    "zh": "事后截断±3：20秒失球差 -0.037 [-0.049,-0.025]，2000/2000；描述性",
    "en": "post hoc clip±3: concede20s -0.037 [-0.049,-0.025] 2000/2000; descriptive"
  },
  "post hoc validated-only: L1 +1.37s [1.02,1.69]; gate still failed -> appendix": {
    "zh": "事后仅纳入验证有效项：L1 +1.37秒 [1.02,1.69]；门槛仍未通过 → 附录",
    "en": "post hoc validated-only: L1 +1.37s [1.02,1.69]; gate still failed -> appendix"
  },
  "random-slope SD ~811uu; cross-season stability not estimable; needs full compact": {
    "zh": "随机斜率标准差 ~811uu；跨赛季稳定性无法估计；需要完整紧凑数据",
    "en": "random-slope SD ~811uu; cross-season stability not estimable; needs full compact"
  },
  "boost path a*b +0.00095 [0.00059,0.00132]; does not explain association; descriptive": {
    "zh": "boost 路径 a*b +0.00095 [0.00059,0.00132]；未解释该关联；描述性",
    "en": "boost path a*b +0.00095 [0.00059,0.00132]; does not explain association; descriptive"
  },
  "IEEE Transactions on Games": {
    "zh": "IEEE Transactions on Games",
    "en": "IEEE Transactions on Games"
  },
  "Introduction": {
    "zh": "引言",
    "en": "Introduction"
  },
  "Related Work": {
    "zh": "相关工作",
    "en": "Related Work"
  },
  "Dataset": {
    "zh": "数据集",
    "en": "Dataset"
  },
  "Method": {
    "zh": "方法",
    "en": "Method"
  },
  "Experiments": {
    "zh": "实验",
    "en": "Experiments"
  },
  "Conclusion": {
    "zh": "结论",
    "en": "Conclusion"
  },
  "Appendix": {
    "zh": "附录",
    "en": "Appendix"
  },
  "一阶转移+停留时间零模型": {
    "zh": "一阶转移+停留时间零模型",
    "en": "First-order transition + dwell-time null model"
  },
  "RQ1 轮转语法": {
    "zh": "RQ1 轮转语法",
    "en": "RQ1 rotation grammar"
  },
  "计划中（指标待实验产出，未填任何数值）。保留一阶转移、停留分布与重置边界的零序列。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。保留一阶转移、停留分布与重置边界的零序列。",
    "en": "Planned (metrics await experimental output; no numerical values entered). Null sequences preserve first-order transitions, dwell distributions and reset boundaries."
  },
  "GRU 自编码器": {
    "zh": "GRU 自编码器",
    "en": "GRU autoencoder"
  },
  "计划中（指标待实验产出，未填任何数值）。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。",
    "en": "Planned (metrics await experimental output; no numerical values entered)."
  },
  "手工几何特征+k-means": {
    "zh": "手工几何特征+k-means",
    "en": "Handcrafted geometric features + k-means"
  },
  "时序图编码器+冻结词表+序列挖掘（本文）": {
    "zh": "时序图编码器+冻结词表+序列挖掘（本文）",
    "en": "Temporal graph encoder + frozen vocabulary + sequence mining (ours)"
  },
  "计划中（指标待实验产出，未填任何数值）。与一阶半马尔可夫零模型比较高阶结构超额量。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。与一阶半马尔可夫零模型比较高阶结构超额量。",
    "en": "Planned (metrics await experimental output; no numerical values entered). Compare excess higher-order structure against a first-order semi-Markov null model."
  },
  "手工规则描述符（无聚类）": {
    "zh": "手工规则描述符（无聚类）",
    "en": "Handcrafted rule descriptors (no clustering)"
  },
  "静态图编码器（无历史）": {
    "zh": "静态图编码器（无历史）",
    "en": "Static graph encoder (no history)"
  },
  "TAGNet 式重构+固定随机 GRU": {
    "zh": "TAGNet 式重构+固定随机 GRU",
    "en": "TAGNet-style reconstruction + fixed random GRU"
  },
  "计划中（指标待实验产出，未填任何数值）。RLCS 适配，非 CS2 精确复现。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。RLCS 适配，非 CS2 精确复现。",
    "en": "Planned (metrics await experimental output; no numerical values entered). RLCS adaptation, not an exact CS2 replication."
  },
  "交接缺口描述符+混合效应竞争结局回归（本文）": {
    "zh": "交接缺口描述符+混合效应竞争结局回归（本文）",
    "en": "Handoff-gap descriptors + mixed-effects competing-outcome regression (ours)"
  },
  "RQ2 交接缺口与失球风险": {
    "zh": "RQ2 交接缺口与失球风险",
    "en": "RQ2 handoff gaps and concession risk"
  },
  "GRU 自编码器表示+同一回归": {
    "zh": "GRU 自编码器表示+同一回归",
    "en": "GRU autoencoder representation + the same regression"
  },
  "RQ3 压力下职责再分配": {
    "zh": "RQ3 压力下职责再分配",
    "en": "RQ3 redistribution of responsibilities under pressure"
  },
  "手工覆盖特征+线性回归": {
    "zh": "手工覆盖特征+线性回归",
    "en": "Handcrafted coverage features + linear regression"
  },
  "冻结词表+连续几何的层次回归（本文）": {
    "zh": "冻结词表+连续几何的层次回归（本文）",
    "en": "Hierarchical regression with frozen vocabulary + continuous geometry (ours)"
  },
  "计划中（指标待实验产出，未填任何数值）。主对比 [末段−早段,落后1]−[末段−早段,领先1]。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。主对比 [末段−早段,落后1]−[末段−早段,领先1]。",
    "en": "Planned (metrics await experimental output; no numerical values entered). Primary contrast: [late−early, trailing by 1]−[late−early, leading by 1]."
  },
  "手工统计指纹": {
    "zh": "手工统计指纹",
    "en": "Handcrafted statistical fingerprints"
  },
  "RQ4 风格归属与 meta 演化": {
    "zh": "RQ4 风格归属与 主流打法 演化",
    "en": "RQ4 style attribution and metagame evolution"
  },
  "情境标准化风格指纹（本文）": {
    "zh": "情境标准化风格指纹（本文）",
    "en": "Context-standardized style fingerprints (ours)"
  },
  "计划中（指标待实验产出，未填任何数值）。比较独立系列赛半区间同/异阵容指纹距离。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。比较独立系列赛半区间同/异阵容指纹距离。",
    "en": "Planned (metrics await experimental output; no numerical values entered). Compare same/different-roster fingerprint distances between independent series halves."
  },
  "PCA+k-means 指纹": {
    "zh": "PCA+k-means 指纹",
    "en": "PCA+k-means fingerprints"
  },
  "TS2Vec 表示指纹": {
    "zh": "TS2Vec 表示指纹",
    "en": "TS2Vec representation fingerprints"
  },
  "历史价值模型 m(t)（本文）": {
    "zh": "历史价值模型 m(t)（本文）",
    "en": "History-based value model m(t) (ours)"
  },
  "RQ5 进球前的势": {
    "zh": "RQ5 进球前的势",
    "en": "RQ5 pre-goal momentum"
  },
  "计划中（指标待实验产出，未填任何数值）。对照：Logistic/GBDT 快照价值模型。": {
    "zh": "计划中（指标待实验产出，未填任何数值）。对照：Logistic/GBDT 快照价值模型。",
    "en": "Planned (metrics await experimental output; no numerical values entered). Controls: Logistic/GBDT snapshot value models."
  },
  "事件中心补偿响应模型（本文）": {
    "zh": "事件中心补偿响应模型（本文）",
    "en": "Event-centered compensatory response model (ours)"
  },
  "RQ6 低 boost/击毁补偿": {
    "zh": "RQ6 低 boost/击毁补偿",
    "en": "RQ6 low-boost/demolition compensation"
  },
  "层次滞后组合模型（本文）": {
    "zh": "层次滞后组合模型（本文）",
    "en": "Hierarchical lagged compositional model (ours)"
  },
  "RQ7 系列赛战术对话": {
    "zh": "RQ7 系列赛战术对话",
    "en": "RQ7 tactical dialogue within a series"
  },
  "油箱保险组合": {
    "zh": "油箱保险组合",
    "en": "Fuel-tank insurance portfolio"
  },
  "被对手带进节拍": {
    "zh": "被对手带进节拍",
    "en": "Drawn into the opponent's rhythm"
  },
  "轮转的对位法": {
    "zh": "轮转的对位法",
    "en": "Counterpoint in rotation"
  },
  "战术磁滞": {
    "zh": "战术磁滞",
    "en": "Tactical hysteresis"
  },
  "防线保险丝": {
    "zh": "防线保险丝",
    "en": "Defensive fuse"
  },
  "队友可读，对手难读": {
    "zh": "队友可读，对手难读",
    "en": "Readable to teammates, hard for opponents to read"
  },
  "雪堆博弈：到底谁上": {
    "zh": "雪堆博弈：到底谁上",
    "en": "Snowdrift game: who goes?"
  },
  "团队旋涡：阵容有左撇子吗": {
    "zh": "团队旋涡：阵容有左撇子吗",
    "en": "Team circulation: are rosters left-handed?"
  },
  "薛定谔进攻者": {
    "zh": "薛定谔进攻者",
    "en": "Schrödinger's attacker"
  },
  "响应多样性：不同步的韧性": {
    "zh": "响应多样性：不同步的韧性",
    "en": "Response diversity: resilience through asynchrony"
  },
  "无球引力：把防守带走": {
    "zh": "无球引力：把防守带走",
    "en": "Off-ball gravity: drawing defenders away"
  },
  "进攻句子的静默逗号": {
    "zh": "进攻句子的静默逗号",
    "en": "The silent comma in an attacking sentence"
  },
  "防线渗流：门缝何时贯通": {
    "zh": "防线渗流：门缝何时贯通",
    "en": "Defensive percolation: when does a gap connect through?"
  },
  "临界减速：阵型复原变慢了吗": {
    "zh": "临界减速：阵型复原变慢了吗",
    "en": "Critical slowing: is formation recovery slowing down?"
  },
  "蛇形甩尾：队尾放大了横移吗": {
    "zh": "蛇形甩尾：队尾放大了横移吗",
    "en": "Whiplash: does the rear amplify lateral motion?"
  },
  "重复铺垫，突然变奏": {
    "zh": "重复铺垫，突然变奏",
    "en": "Repeated setup, sudden variation"
  },
  "稀有队形红利": {
    "zh": "稀有队形红利",
    "en": "Rare-formation dividend"
  },
  "生态位装配：不同球员，相似互补": {
    "zh": "生态位装配：不同球员，相似互补",
    "en": "Niche assembly: different players, similar complementarity"
  },
  "帧数据 · 30 fps": {
    "zh": "帧数据 · 30 fps",
    "en": "Frame data · 30 fps"
  },
  "原始回放 · Kaggle（已解压）": {
    "zh": "原始回放 · Kaggle（已解压）",
    "en": "Raw replays · Kaggle (extracted)"
  },
  "原始回放 · ballchasing（tar 分片）": {
    "zh": "原始回放 · ballchasing（tar 分片）",
    "en": "Raw replays · ballchasing (tar shards)"
  },
  "按 series / event / season 分组划分训练、验证与测试集。": {
    "zh": "按系列赛 / 赛事 / 赛季分组划分训练、验证与测试集。",
    "en": "Split training, validation and test sets by series / event / season groups."
  },
  "同一分组不得跨集合；不按帧随机切分。具体集合清单与比例待实验协议确定。": {
    "zh": "同一分组不得跨集合；不按帧随机切分。具体集合清单与比例待实验协议确定。",
    "en": "A group must not span sets; do not randomly split frames. Exact set manifests and proportions await the experimental protocol."
  },
  "五个赛季均已下载并完成解析，无需重新下载。调整帧率或增加特征时，使用 scripts/parse_replays.py 重新解析原始回放。": {
    "zh": "五个赛季均已下载并完成解析，无需重新下载。调整帧率或增加特征时，使用 scripts/parse_replays.py 重新解析原始回放。",
    "en": "All five seasons have been downloaded and parsed; no new download is needed. Use scripts/parse_replays.py to reparse raw replays when changing frame rate or adding features."
  },
  "帧数按原始摘要的百万帧精度保留：总计 591.2 M，分赛季显示值之和为 591.1 M；未用分项之和改写总计。": {
    "zh": "帧数按原始摘要的百万帧精度保留：总计 591.2 M，分赛季显示值之和为 591.1 M；未用分项之和改写总计。",
    "en": "Frame counts retain the original summary's million-frame precision: total 591.2 M; displayed season counts sum to 591.1 M. The total has not been replaced by the sum of its parts."
  },
  "1v1 / 2v2 / 3v3 之外的 94 场为玩家缺失或断线造成的奇数玩家对局。": {
    "zh": "1v1 / 2v2 / 3v3 之外的 94 场为玩家缺失或断线造成的奇数玩家对局。",
    "en": "The 94 games outside 1v1 / 2v2 / 3v3 have odd player counts due to missing or disconnected players."
  },
  "134 个回放解析失败（原摘要标注 0.3%），错误已记录在索引中，主要因中途加入或离开、或头部记录超过六名玩家。": {
    "zh": "134 个回放解析失败（原摘要标注 0.3%），错误已记录在索引中，主要因中途加入或离开、或头部记录超过六名玩家。",
    "en": "134 replays failed parsing (0.3% in the original summary); errors are recorded in the index, mainly due to mid-game joins or departures, or headers listing more than six players."
  },
  "官方分组中 26 个回放在下载前已被 ballchasing 删除。": {
    "zh": "官方分组中 26 个回放在下载前已被 ballchasing 删除。",
    "en": "In the official groups, 26 replays had been deleted by ballchasing before download."
  },
  "RQ1 三人轮转是否存在可复用的“语法”": {
    "zh": "RQ1 三人轮转是否存在可复用的“语法”",
    "en": "RQ1 Is there a reusable grammar of three-player rotation?"
  },
  "追踪最近球员变化与深度/逼近速度，从冻结词表挖掘 2–4 token 序列；时序图表示+聚类+游程编码+序列挖掘，与一阶半马尔可夫零模型对比，按系列赛 bootstrap。": {
    "zh": "追踪最近球员变化与深度/逼近速度，从冻结词表挖掘 2–4 词元 序列；时序图表示+聚类+游程编码+序列挖掘，与一阶半马尔可夫零模型对比，按系列赛 bootstrap。",
    "en": "Track changes in the nearest player and depth/approach speed; mine 2–4 token sequences from a frozen vocabulary. Use temporal graph representations + clustering + run-length encoding + sequence mining, compare against a first-order semi-Markov null model, and bootstrap by series."
  },
  "已剪枝(降为次要)：中规模学习词表 excess 0.0028 bit(CI 0.0022-0.0033, p=0.002)，手工 0.0085(p=0.002)；留出预测增益 学习 +0.0009 / 手工 +0.0035；核对后单位为每窗口机会，校正后学习 -0.0016 bit/跳": {
    "zh": "已剪枝（降为次要）：中规模学习词表超额量 0.0028 比特（置信区间 0.0022-0.0033，p=0.002），手工 0.0085（p=0.002）；留出预测增益：学习 +0.0009 / 手工 +0.0035；核对后单位为每窗口机会，校正后学习 -0.0016 比特/跳",
    "en": "Pruned (demoted to secondary): medium-scale learned vocabulary excess 0.0028 bit (CI 0.0022-0.0033, p=0.002), handcrafted 0.0085 (p=0.002); held-out prediction gain: learned +0.0009 / handcrafted +0.0035. After checking, the unit is per window opportunity; corrected learned value −0.0016 bit/jump."
  },
  "RQ2 危险时刻是否与轮转交接缺口相关": {
    "zh": "RQ2 危险时刻是否与轮转交接缺口相关",
    "en": "RQ2 Are dangerous moments associated with rotation handoff gaps?"
  },
  "以最近球员交接为锚点，度量交接时延、无覆盖比例、双人同时逼近（overlap 代理）与补位深度；混合效应竞争结局回归，调整交接前球态与资源。": {
    "zh": "以最近球员交接为锚点，度量交接时延、无覆盖比例、双人同时逼近（重叠代理）与补位深度；混合效应竞争结局回归，调整交接前球态与资源。",
    "en": "Anchor on handoffs of the nearest player; measure handoff delay, uncovered fraction, simultaneous approach by two players (overlap proxy), and covering depth. Use mixed-effects competing-outcome regression, adjusting for pre-handoff ball state and resources."
  },
  "RQ3 压力下球队是加大冒险还是重新分配职责": {
    "zh": "RQ3 压力下球队是加大冒险还是重新分配职责",
    "en": "RQ3 Under pressure, do teams take more risks or redistribute responsibilities?"
  },
  "主对比：[末段−早段, 落后1球]−[末段−早段, 领先1球]，主响应为无覆盖活球比例；层次回归含非线性时间与比分×时间交互，加时单独分析。": {
    "zh": "主对比：[末段−早段, 落后1球]−[末段−早段, 领先1球]，主响应为无覆盖活球比例；层次回归含非线性时间与比分×时间交互，加时单独分析。",
    "en": "Primary contrast: [late−early, trailing by 1 goal]−[late−early, leading by 1 goal]. The primary response is uncovered live-play fraction; hierarchical regression includes nonlinear time and score×time interactions, with overtime analyzed separately."
  },
  "中规模校正指标：真正最后一人 late×trailing +458uu 更靠前(CI 390-529, p=1.5e-31)；原 third_depth(离球最远者) -801uu。未覆盖比例：OLS p=0.049(Holm 0.099)，混合效应(本次收敛) +0.0145 p=0.012 作敏感性。下一步：启动前压→扳平/失球 AIPW": {
    "zh": "中规模校正指标：真正最后一人“末段×落后” +458uu 更靠前（置信区间 390-529，p=1.5e-31）；原 third_depth（离球最远者）-801uu。未覆盖比例：OLS p=0.049（Holm 0.099），混合效应（本次收敛）+0.0145 p=0.012 作敏感性。下一步：启动前压→扳平/失球 AIPW",
    "en": "Medium-scale corrected metric: the true last defender is +458uu further forward for late×trailing (CI 390-529, p=1.5e-31); original third_depth (player furthest from the ball) −801uu. Uncovered fraction: OLS p=0.049 (Holm 0.099); mixed effects (converged this time) +0.0145, p=0.012 as sensitivity. Next: AIPW for initiating a push-up → equalizing/conceding."
  },
  "RQ4 风格属于选手、阵容还是俱乐部，以及 meta 如何演化": {
    "zh": "RQ4 风格属于选手、阵容还是俱乐部，以及主流打法如何演化",
    "en": "RQ4 Does style belong to players, rosters or clubs, and how does the metagame evolve?"
  },
  "以母题频率、转移、角色占用、覆盖与 boost 分布构建情境标准化指纹，比较独立系列赛间同阵容/异阵容距离；赛季变化分解为母题构成、母题内执行与支持外行为。": {
    "zh": "以母题频率、转移、角色占用、覆盖与 boost 分布构建情境标准化指纹，比较独立系列赛间同阵容/异阵容距离；赛季变化分解为母题构成、母题内执行与支持外行为。",
    "en": "Build context-standardized fingerprints from motif frequencies, transitions, role occupancy, coverage and boost distributions. Compare same/different-roster distances across independent series; decompose seasonal changes into motif composition, within-motif execution and out-of-support behavior."
  },
  "选手层面跨赛季指纹(41104888): top-1 15.4% [13.1,17.7] vs 随机 0.9%，MRR 0.262；排除同队后 top-1 15.0%": {
    "zh": "选手层面跨赛季指纹（41104888）：第1位命中率 15.4% [13.1,17.7]，随机 0.9%，MRR 0.262；排除同队后第1位命中率 15.0%",
    "en": "Player-level cross-season fingerprints (41104888): top-1 15.4% [13.1,17.7] vs random 0.9%, MRR 0.262; top-1 15.0% after excluding teammates."
  },
  "RQ5 进球前的“势”能否在进球前被度量": {
    "zh": "RQ5 进球前的“势”能否在进球前被度量",
    "en": "RQ5 Can pre-goal momentum be measured before the goal?"
  },
  "前瞻采样活球时刻，定义 V10=己方10秒内先进球概率−对方概率；历史模型（前6秒）与同等容量快照模型之差 m(t) 作为历史信息量，系列赛交叉拟合并校准。": {
    "zh": "前瞻采样活球时刻，定义 V10=己方10秒内先进球概率−对方概率；历史模型（前6秒）与同等容量快照模型之差 m(t) 作为历史信息量，系列赛交叉拟合并校准。",
    "en": "Prospectively sample live-play moments; define V10=probability of our team scoring first within 10 seconds−opponent probability. Use the difference m(t) between a history model (preceding 6 seconds) and a snapshot model of equal capacity as the value of history; cross-fit by series and calibrate."
  },
  "RQ6 队友如何补偿低 boost 或被击毁": {
    "zh": "RQ6 队友如何补偿低 boost 或被击毁",
    "en": "RQ6 How do teammates compensate for low boost or demolition?"
  },
  "标记低 boost（<20% 持续≥0.5秒）与击毁起点，度量队友接管时延、覆盖与角色占用；事件中心时序/图表示，与匹配非事件轨迹对比的混合效应事件时间模型。": {
    "zh": "标记低 boost（<20% 持续≥0.5秒）与击毁起点，度量队友接管时延、覆盖与角色占用；事件中心时序/图表示，与匹配非事件轨迹对比的混合效应事件时间模型。",
    "en": "Mark low-boost onsets (<20% for ≥0.5 seconds) and demolitions; measure teammate takeover delay, coverage and role occupancy. Use event-centered temporal/graph representations and a mixed-effects event-time model comparing matched non-event trajectories."
  },
  "RQ7 一个系列赛中是否存在战术“对话”": {
    "zh": "RQ7 一个系列赛中是否存在战术“对话”",
    "en": "RQ7 Is there tactical dialogue within a series?"
  },
  "用第 g 局对手情境标准化行为预测第 g+1 局本队母题，控制自身前局行为、前局结果、局序与阵容连续性；层次滞后组合模型，层内整系列置换检验。": {
    "zh": "用第 g 局对手情境标准化行为预测第 g+1 局本队母题，控制自身前局行为、前局结果、局序与阵容连续性；层次滞后组合模型，层内整系列置换检验。",
    "en": "Predict our team's motifs in game g+1 from the opponent's context-standardized behavior in game g, controlling our prior-game behavior, prior-game outcome, game order and roster continuity. Use a hierarchical lagged compositional model and whole-series permutations within strata."
  },
  "B08 双人低 boost：42/42 单元通过但循环平移零模型失败 → 附录负对照": {
    "zh": "B08 双人低 boost：42/42 单元通过但循环平移零模型失败 → 附录负对照",
    "en": "B08 paired low boost: 42/42 cells passed, but the circular-shift null failed → appendix negative control"
  },
  "P4 前压的收益与风险（双重稳健 AIPW）": {
    "zh": "P4 前压的收益与风险（双重稳健 AIPW）",
    "en": "P4 Benefits and risks of pushing up (doubly robust AIPW)"
  },
  "末段落后时最后一人前压 +458 uu；前压是换来进球还是送掉失球？": {
    "zh": "末段落后时最后一人前压 +458 uu；前压是换来进球还是送掉失球？",
    "en": "The last defender pushes up +458 uu when trailing late; does pushing up buy goals or give away concessions?"
  },
  "DR 41104850 两种设计均未过因果门槛(SMD 0.76/0.23>0.1)；晚段落后时前压关联净进球 +0.066/10s[0.026,0.111]，所有比分状态都类似且失球反而更低→疑似控球混杂；不支持“风险大于收益”，也不能因果证明收益。docs/P4_DR_review.md": {
    "zh": "DR 41104850 两种设计均未过因果门槛(SMD 0.76/0.23>0.1)；晚段落后时前压关联净进球 +0.066/10s[0.026,0.111]，所有比分状态都类似且失球反而更低→疑似控球混杂；不支持“风险大于收益”，也不能因果证明收益。docs/P4_DR_review.md",
    "en": "DR 41104850: neither design passed the causal gates (SMD 0.76/0.23>0.1). When trailing late, pushing up is associated with net goals +0.066/10s [0.026,0.111]; all score states look similar and concessions are lower → suspected possession confounding. This does not support “risk outweighs benefit”, nor establish causal benefit. docs/P4_DR_review.md"
  },
  "控球条件化敏感性：条件化后净进球差仍 +0.086 [0.020,0.177]，控球代理未解释掉关联；R5 不特异于落后": {
    "zh": "控球条件化敏感性：条件化后净进球差仍 +0.086 [0.020,0.177]，控球代理未解释掉关联；R5 不特异于落后",
    "en": "Possession-conditioned sensitivity: net-goal difference remains +0.086 [0.020,0.177] after conditioning; possession proxies did not explain away the association; R5 is not specific to trailing."
  },
  "轮转延迟（主）：41105041 运行中（首次 41105023 因 bash 空数组失败已修）": {
    "zh": "轮转延迟（主）：41105041 运行中（首次 41105023 因 bash 空数组失败已修）",
    "en": "Rotation latency (primary): 41105041 running (initial 41105023 failed due to a bash empty-array issue, now fixed)"
  },
  "评审意见分析：P6.1/6.2/6.6/6.7 已完成；P6.3 异质性 41105024、P6.4 boost 分解 41105038 运行中": {
    "zh": "评审意见分析：P6.1/6.2/6.6/6.7 已完成；P6.3 异质性 41105024、P6.4 boost 分解 41105038 运行中",
    "en": "Reviewer-response analyses: P6.1/6.2/6.6/6.7 complete; P6.3 heterogeneity 41105024 and P6.4 boost decomposition 41105038 running"
  },
  "对称性：领先方末位后撤 -211 [-286,-141] uu，落后方前压 +247 [171,318]；交互 +458 [390,529]，双向都存在（关联）": {
    "zh": "对称性：领先方末位后撤 -211 [-286,-141] uu，落后方前压 +247 [171,318]；交互 +458 [390,529]，双向都存在（关联）",
    "en": "Symmetry: the leading side's last defender retreats −211 [-286,-141] uu; the trailing side pushes up +247 [171,318]; interaction +458 [390,529]. Both directions are present (association)."
  },
  "开球自然实验：球状态重置后，落后方非开球手仍更靠前 +370 [165,570] uu（末段 +1010）；更激进开球 20 秒失球 6.6% vs 10.2%（-3.7pp [-4.9,-2.5]，bootstrap 不完整，团队选择混杂）": {
    "zh": "开球自然实验：球状态重置后，落后方非开球手仍更靠前 +370 [165,570] uu（末段 +1010）；更激进开球 20 秒失球 6.6% 对比 10.2%（-3.7个百分点 [-4.9,-2.5]，bootstrap 不完整，团队选择混杂）",
    "en": "Kickoff natural experiment: after ball-state reset, trailing non-kickoff players remain further forward by +370 [165,570] uu (late +1010); more aggressive kickoffs: 20-second concessions 6.6% vs 10.2% (−3.7pp [-4.9,-2.5], incomplete bootstrap, team-selection confounding)."
  },
  "加时：末位比常规末段平局更深 169 [131,208] uu；无等价界，不称相同": {
    "zh": "加时：末位比常规末段平局更深 169 [131,208] uu；无等价界，不称相同",
    "en": "Overtime: the last defender is 169 [131,208] uu deeper than in late tied regulation; no equivalence margin, so do not call them the same."
  },
  "定义稳健性：队伍质心交互 +434 [371,499] uu，方向一致（平均深度为代数别名）": {
    "zh": "定义稳健性：队伍质心交互 +434 [371,499] uu，方向一致（平均深度为代数别名）",
    "en": "Definition robustness: team-centroid interaction +434 [371,499] uu, consistent direction (mean depth is an algebraic alias)."
  },
  "RQ4 全量提取：估时 ~9h/16 CPU，~40 GB；仅提取脚本编写中（不覆盖现有结果）": {
    "zh": "RQ4 全量提取：估时 ~9h/16 CPU，~40 GB；仅提取脚本编写中（不覆盖现有结果）",
    "en": "RQ4 full extraction: estimated ~9h/16 CPU, ~40 GB; extraction-only script in progress (existing results will not be overwritten)."
  },
  "RQ4 习惯稳定性 / habit stability": {
    "zh": "RQ4 习惯稳定性",
    "en": "RQ4 habit stability"
  },
  "P6.2 K2 事后敏感性": {
    "zh": "P6.2 K2 事后敏感性",
    "en": "P6.2 K2 post hoc sensitivity"
  },
  "P5 事后敏感性": {
    "zh": "P5 事后敏感性",
    "en": "P5 post hoc sensitivity"
  },
  "P6.3 异质性 / heterogeneity": {
    "zh": "P6.3 异质性",
    "en": "P6.3 heterogeneity"
  },
  "P6.4 boost 中介 / mediation": {
    "zh": "P6.4 boost 中介",
    "en": "P6.4 boost mediation"
  },
  "环境": {
    "zh": "环境",
    "en": "Environment"
  },
  "A100 80GB；torch 2.5.1+cu121 + PyG 2.8.1 打包环境 49 秒就绪；已读数据 README": {
    "zh": "A100 80GB；torch 2.5.1+cu121 + PyG 2.8.1 打包环境 49 秒就绪；已读数据 README",
    "en": "A100 80GB; packaged torch 2.5.1+cu121 + PyG 2.8.1 environment ready in 49 seconds; data README read"
  },
  "进度大屏": {
    "zh": "进度大屏",
    "en": "Research dashboard"
  },
  "进度大屏上线：login006 127.0.0.1:18765，10 个页面，tmux 看门狗自动拉起": {
    "zh": "进度大屏上线：login006 127.0.0.1:18765，10 个页面，tmux 看门狗自动拉起",
    "en": "Dashboard online: login006 127.0.0.1:18765, 10 pages, automatically restarted by a tmux watchdog"
  },
  "文献与创新": {
    "zh": "文献与创新",
    "en": "Literature and research design"
  },
  "设计完成：7 个研究问题（轮转语法/压力下补位/风格指纹为主），8 篇白名单文献 + 3 个数据来源已核实": {
    "zh": "设计完成：7 个研究问题（轮转语法/压力下补位/风格指纹为主），8 篇白名单文献 + 3 个数据来源已核实",
    "en": "Design complete: 7 research questions (primarily rotation grammar / covering under pressure / style fingerprints); 8 allowlisted papers + 3 data sources verified"
  },
  "实验": {
    "zh": "实验",
    "en": "Experiments"
  },
  "中规模 41104745(7,500 场,358 个验证系列赛)：RQ1 学习 0.0028 vs 手工 0.0085 bit/跳→降级；RQ3 主检验 +0.015(p=0.049, Holm 0.099)未通过；第三人(离球最远者)深度 -801uu(p=3e-31)；RQ4 合格阵容 0": {
    "zh": "中规模 41104745(7,500 场,358 个验证系列赛)：RQ1 学习 0.0028 对比 手工 0.0085 比特/跳→降级；RQ3 主检验 +0.015(p=0.049, Holm 0.099)未通过；第三人(离球最远者)深度 -801uu(p=3e-31)；RQ4 合格阵容 0",
    "en": "Medium scale 41104745 (7,500 games, 358 validation series): RQ1 learned 0.0028 vs handcrafted 0.0085 bit/jump → demoted; RQ3 primary test +0.015 (p=0.049, Holm 0.099) did not pass; third-player (furthest from ball) depth −801uu (p=3e-31); RQ4 eligible rosters 0"
  },
  "发现收敛": {
    "zh": "发现收敛",
    "en": "Finding consolidation"
  },
  "校正指标确认：末段落后一球时真正最后一人(最靠己方球门者)比领先时靠前 458uu(CI 390-529, p=1.5e-31, 358 系列赛, 作业 41104851)。前压双重稳健分析 41104850 运行中(状态设计因正性失败仅作描述，启动前压设计为主)；快筛并行 41104877/78/79": {
    "zh": "校正指标确认：末段落后一球时真正最后一人(最靠己方球门者)比领先时靠前 458uu(CI 390-529, p=1.5e-31, 358 系列赛, 作业 41104851)。前压双重稳健分析 41104850 运行中(状态设计因正性失败仅作描述，启动前压设计为主)；快筛并行 41104877/78/79",
    "en": "Corrected metric confirmed: when trailing by one goal late, the true last defender (closest to own goal) is 458uu further forward than when leading (CI 390-529, p=1.5e-31, 358 series, job 41104851). Doubly robust push-up analysis 41104850 running (state design descriptive only due to positivity failure; initiation design primary); parallel quick screens 41104877/78/79"
  },
  "论文": {
    "zh": "论文",
    "en": "Manuscript"
  },
  "P6.4": {
    "zh": "P6.4",
    "en": "P6.4"
  },
  "RLCS 2026": {
    "zh": "RLCS 2026",
    "en": "RLCS 2026"
  },
  "PCA+k-means": {
    "zh": "PCA+k-means",
    "en": "PCA+k-means"
  },
  "lbfgs": {
    "zh": "lbfgs",
    "en": "lbfgs"
  },
  "": {
    "zh": "",
    "en": ""
  },
  "RLCS 2021-22": {
    "zh": "RLCS 2021-22",
    "en": "RLCS 2021-22"
  },
  "RLCS 22-23": {
    "zh": "RLCS 22-23",
    "en": "RLCS 22-23"
  },
  "RLCS 2024": {
    "zh": "RLCS 2024",
    "en": "RLCS 2024"
  },
  "RLCS 2025": {
    "zh": "RLCS 2025",
    "en": "RLCS 2025"
  },
  "动机：协调中可能存在超越静态站位、一阶角色转移与停留时间的高阶多步序列（如 接近→撤出→补位→再进入）。 方法：追踪最近球员变化与深度/逼近速度，从冻结词表挖掘 2–4 token 序列；时序图表示+聚类+游程编码+序列挖掘，与一阶半马尔可夫零模型对比，按系列赛 bootstrap。": {
    "zh": "动机：协调中可能存在超越静态站位、一阶角色转移与停留时间的高阶多步序列（如 接近→撤出→补位→再进入）。 方法：追踪最近球员变化与深度/逼近速度，从冻结词表挖掘 2–4 词元 序列；时序图表示+聚类+游程编码+序列挖掘，与一阶半马尔可夫零模型对比，按系列赛 bootstrap。",
    "en": "Motivation: Higher-order multistep sequences (such as approach→withdraw→cover→re-enter) may exist in coordination beyond static positioning, first-order role transitions and dwell times. Method: Track changes in the nearest player and depth/approach speed; mine 2–4 token sequences from a frozen vocabulary. Use temporal graph representations + clustering + run-length encoding + sequence mining, compare against a first-order semi-Markov null model, and bootstrap by series."
  },
  "动机：关键失球可能源于半秒的无人覆盖空档，而非明显糟糕的阵型。 方法：以最近球员交接为锚点，度量交接时延、无覆盖比例、双人同时逼近（overlap 代理）与补位深度；混合效应竞争结局回归，调整交接前球态与资源。": {
    "zh": "动机：关键失球可能源于半秒的无人覆盖空档，而非明显糟糕的阵型。 方法：以最近球员交接为锚点，度量交接时延、无覆盖比例、双人同时逼近（重叠代理）与补位深度；混合效应竞争结局回归，调整交接前球态与资源。",
    "en": "Motivation: Critical concessions may arise from a half-second gap without coverage, rather than an obviously poor formation. Method: Anchor on handoffs of the nearest player; measure handoff delay, uncovered fraction, simultaneous approach by two players (overlap proxy), and covering depth. Use mixed-effects competing-outcome regression, adjusting for pre-handoff ball state and resources."
  },
  "动机：“关键时刻”可能表现为保护第三人安全边际、同时另一人更激进。 方法：主对比：[末段−早段, 落后1球]−[末段−早段, 领先1球]，主响应为无覆盖活球比例；层次回归含非线性时间与比分×时间交互，加时单独分析。": {
    "zh": "动机：“关键时刻”可能表现为保护第三人安全边际、同时另一人更激进。 方法：主对比：[末段−早段, 落后1球]−[末段−早段, 领先1球]，主响应为无覆盖活球比例；层次回归含非线性时间与比分×时间交互，加时单独分析。",
    "en": "Motivation: Clutch moments may involve protecting the third player’s safety margin while another player becomes more aggressive. Method: Primary contrast: [late−early, trailing by 1 goal]−[late−early, leading by 1 goal]. The primary response is uncovered live-play fraction; hierarchical regression includes nonlinear time and score×time interactions, with overtime analyzed separately."
  },
  "动机：选手可能把可识别的习惯带到新阵容，而俱乐部风格会在转会后改变。 方法：以母题频率、转移、角色占用、覆盖与 boost 分布构建情境标准化指纹，比较独立系列赛间同阵容/异阵容距离；赛季变化分解为母题构成、母题内执行与支持外行为。": {
    "zh": "动机：选手可能把可识别的习惯带到新阵容，而俱乐部风格会在转会后改变。 方法：以母题频率、转移、角色占用、覆盖与 boost 分布构建情境标准化指纹，比较独立系列赛间同阵容/异阵容距离；赛季变化分解为母题构成、母题内执行与支持外行为。",
    "en": "Motivation: Players may bring recognizable habits into new rosters, while club style may change after transfers. Method: Build context-standardized fingerprints from motif frequencies, transitions, role occupancy, coverage and boost distributions. Compare same/different-roster distances across independent series; decompose seasonal changes into motif composition, within-motif execution and out-of-support behavior."
  },
  "动机：检验“压力在累积”的直觉，包括最终失败的进攻。 方法：前瞻采样活球时刻，定义 V10=己方10秒内先进球概率−对方概率；历史模型（前6秒）与同等容量快照模型之差 m(t) 作为历史信息量，系列赛交叉拟合并校准。": {
    "zh": "动机：检验“压力在累积”的直觉，包括最终失败的进攻。 方法：前瞻采样活球时刻，定义 V10=己方10秒内先进球概率−对方概率；历史模型（前6秒）与同等容量快照模型之差 m(t) 作为历史信息量，系列赛交叉拟合并校准。",
    "en": "Motivation: Test the intuition that pressure builds up, including attacks that ultimately fail. Method: Prospectively sample live-play moments; define V10=probability of our team scoring first within 10 seconds−opponent probability. Use the difference m(t) between a history model (preceding 6 seconds) and a snapshot model of equal capacity as the value of history; cross-fit by series and calibrate."
  },
  "动机：揭示进球/助攻统计看不到的支援工作。 方法：标记低 boost（<20% 持续≥0.5秒）与击毁起点，度量队友接管时延、覆盖与角色占用；事件中心时序/图表示，与匹配非事件轨迹对比的混合效应事件时间模型。": {
    "zh": "动机：揭示进球/助攻统计看不到的支援工作。 方法：标记低 boost（<20% 持续≥0.5秒）与击毁起点，度量队友接管时延、覆盖与角色占用；事件中心时序/图表示，与匹配非事件轨迹对比的混合效应事件时间模型。",
    "en": "Motivation: Reveal support work invisible to goal/assist statistics. Method: Mark low-boost onsets (<20% for ≥0.5 seconds) and demolitions; measure teammate takeover delay, coverage and role occupancy. Use event-centered temporal/graph representations and a mixed-effects event-time model comparing matched non-event trajectories."
  },
  "动机：BO 系列赛可能包含应对与反应对，而非独立重复的比赛。 方法：用第 g 局对手情境标准化行为预测第 g+1 局本队母题，控制自身前局行为、前局结果、局序与阵容连续性；层次滞后组合模型，层内整系列置换检验。": {
    "zh": "动机：BO 系列赛可能包含应对与反应对，而非独立重复的比赛。 方法：用第 g 局对手情境标准化行为预测第 g+1 局本队母题，控制自身前局行为、前局结果、局序与阵容连续性；层次滞后组合模型，层内整系列置换检验。",
    "en": "Motivation: Best-of series may contain responses and counter-responses, rather than independent repetitions of games. Method: Predict our team's motifs in game g+1 from the opponent's context-standardized behavior in game g, controlling our prior-game behavior, prior-game outcome, game order and roster continuity. Use a hierarchical lagged compositional model and whole-series permutations within strata."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 横向补偿增益为 -89.01 每 1000 uu/秒创新对应的反向速度（uu/秒），q=0.0015；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 横向补偿增益为 -89.01 每 1000 uu/秒创新对应的反向速度（uu/秒），q=0.0015；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Lateral compensation gain is -89.01 opposite velocity (uu/s) per 1000 uu/s innovation, q=0.0015; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 前进历史相对后退历史的阵型宽度差为 8.44 uu，q=0.898；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 前进历史相对后退历史的阵型宽度差为 8.44 uu，q=0.898；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Formation-width difference for forward versus backward history is 8.44 uu, q=0.898; no clear evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 高脆弱性相对低脆弱性的失球概率差为 0.3765 个百分点，q=0.00514；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 高脆弱性相对低脆弱性的失球概率差为 0.3765 个百分点，q=0.00514；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Concession-probability difference for high versus low brittleness is 0.3765 percentage points, q=0.00514; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 对手历史相对队友历史的预测损失差为 0.0001194 比特/动作，q=0.376；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 对手历史相对队友历史的预测损失差为 0.0001194 比特/动作，q=0.376；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Prediction-loss difference for opponent versus teammate history is 0.0001194 bits/action, q=0.376; no clear evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 恰好一人上前的超额概率为 2.372 个百分点，q=0.109；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 恰好一人上前的超额概率为 2.372 个百分点，q=0.109；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess probability of exactly one player approaching is 2.372 percentage points, q=0.109; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 阵容旋转方向的分半相关为 0.2158 相关系数，q=0.0882；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 阵容旋转方向的分半相关为 0.2158 相关系数，q=0.0882；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Split-half correlation of roster circulation direction is 0.2158, q=0.0882; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 宽间距下进攻者模糊性的额外减速概率为 34.97 个百分点，q=0.244；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 宽间距下进攻者模糊性的额外减速概率为 34.97 个百分点，q=0.244；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional slowing probability from attacker ambiguity at wide spacing is 34.97 percentage points, q=0.244; no clear evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 双人低 boost 风险相对独立基线的比值为 0.7841 倍，q=0.0015；值得扩大筛查，尚非确认。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 双人低 boost 风险相对独立基线的比值为 0.7841 倍，q=0.0015；值得扩大筛查，尚非确认。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Paired low-boost risk relative to the independent baseline is 0.7841 times, q=0.0015; worth scaling the screen, not yet confirmed."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 低响应多样性相对高多样性的额外回撤距离为 -28.78 uu，q=0.0015；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 低响应多样性相对高多样性的额外回撤距离为 -28.78 uu，q=0.0015；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional backward excursion for low versus high response diversity is -28.78 uu, q=0.0015; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 追随防守带来的通道净宽变化为 141.6 uu，q=0.0015；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 追随防守带来的通道净宽变化为 141.6 uu，q=0.0015；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Lane-clearance change associated with following defenders is 141.6 uu, q=0.0015; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 停顿后的对手加速响应概率差为 0.1841 个百分点，q=0.565；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 停顿后的对手加速响应概率差为 0.1841 个百分点，q=0.565；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Difference in opponent acceleration-response probability after a pause is 0.1841 percentage points, q=0.565; no clear evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 贯通通道相对封闭通道的失球概率差为 0.8971 个百分点，q=0.109；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 贯通通道相对封闭通道的失球概率差为 0.8971 个百分点，q=0.109；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Concession-probability difference for connected versus closed corridors is 0.8971 percentage points, q=0.109; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 失球前阵型面积残差的额外持续性为 -0.001378 相关系数差，q=0.764；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 失球前阵型面积残差的额外持续性为 -0.001378 相关系数差，q=0.764；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess persistence of formation-area residuals before conceding is -0.001378 in correlation difference, q=0.764; no clear evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 后排横向响应的额外放大增益为 -0.3057 倍增益，q=0.0015；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 后排横向响应的额外放大增益为 -0.3057 倍增益，q=0.0015；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess amplification gain of rear lateral response is -0.3057, q=0.0015; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 超出零模型的节拍调制概率为 0.4035 个百分点/0.1秒，q=0.0882；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 超出零模型的节拍调制概率为 0.4035 个百分点/0.1秒，q=0.0882；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Rhythmic probability modulation beyond the null is 0.4035 percentage points/0.1 seconds, q=0.0882; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 打破重复路线后的额外响应延迟为 -0.08444 秒，q=0.0015；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 打破重复路线后的额外响应延迟为 -0.08444 秒，q=0.0015；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional response latency after breaking a repeated route is -0.08444 seconds, q=0.0015; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 队形稀有度每翻倍的推进距离变化为 57.92 uu/稀有度翻倍，q=0.063；证据较弱。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 队形稀有度每翻倍的推进距离变化为 57.92 uu/稀有度翻倍，q=0.063；证据较弱。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Change in forward progress per doubling of formation rarity is 57.92 uu/doubling rarity, q=0.063; weak evidence."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 超出独立球员习惯基线的空间互补概率为 0.891 个百分点，q=0.36；未见清晰证据。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 超出独立球员习惯基线的空间互补概率为 0.891 个百分点，q=0.36；未见清晰证据。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Spatial-complementarity probability beyond the independent-player-habit baseline is 0.891 percentage points, q=0.36; no clear evidence."
  },
  "Music: counterpoint and compensatory motion": {
    "zh": "音乐：对位法与补偿运动",
    "en": "Music: counterpoint and compensatory motion"
  },
  "After one player's lateral acceleration, the other two have excess opposite lateral acceleration beyond their common reaction to the ball. The object is a signed compensatory response, not generic synchrony.": {
    "zh": "一名球员横向加速后，另外两人出现超出共同球反应的额外反向横向加速。研究对象是带方向的补偿响应，而非一般同步性。",
    "en": "After one player's lateral acceleration, the other two have excess opposite lateral acceleration beyond their common reaction to the ball. The object is a signed compensatory response, not generic synchrony."
  },
  "At anchors ≥6 s apart, freeze i as the unambiguous ball-nearest teammate. Let u=vxi(t+.2)-vxi(t), and v=Σj≠i[vxj(t+.7)-vxj(t+.2)]. Residualize u and v against the preceding 1 s of ball trajectory and all starting player positions/velocities/boost. Primary statistic Δg is observed compensation gain g=−slope(v~u) minus the gain from the matched-block null. A gain of .15 means an extra 150 uu/s of summed opposite movement per 1,000 uu/s innovation. No claim that i causes the response.": {
    "zh": "在间隔 ≥6 秒的锚点，将 i 固定为明确离球最近的队友。令 u=vxi(t+.2)-vxi(t)，v=Σj≠i[vxj(t+.7)-vxj(t+.2)]。对之前 1 秒的球轨迹及所有球员初始位置/速度/boost 回归，取 u 与 v 的残差。主统计量 Δg 为观测补偿增益 g=−slope(v~u) 减去匹配块零模型的增益。.15 的增益表示每 1,000 uu/秒创新对应额外 150 uu/秒的合计反向运动。不声称 i 导致该响应。",
    "en": "At anchors ≥6 s apart, freeze i as the unambiguous ball-nearest teammate. Let u=vxi(t+.2)-vxi(t), and v=Σj≠i[vxj(t+.7)-vxj(t+.2)]. Residualize u and v against the preceding 1 s of ball trajectory and all starting player positions/velocities/boost. Primary statistic Δg is observed compensation gain g=−slope(v~u) minus the gain from the matched-block null. A gain of .15 means an extra 150 uu/s of summed opposite movement per 1,000 uu/s innovation. No claim that i causes the response."
  },
  "No extra compensatory coupling conditional on the shared stimulus. Re-pair complete receiver-pair trajectory blocks with source blocks from other series of the same roster where possible, tightly matching initial geometry, own-half/attack-half, ball history, score/time and strength. Preserve receiver-pair covariance and within-block autocorrelation. No independent frame shuffle; insufficient exchangeable blocks means no permutation claim.": {
    "zh": "给定共同刺激后不存在额外补偿耦合。尽可能将完整的接收方双人轨迹块与同阵容其他系列赛的源块重新配对，严格匹配初始几何、己方半场/进攻半场、球历史、比分/时间及实力。保留接收方双人协方差与块内自相关。不独立打乱帧；可交换块不足时不作置换推断。",
    "en": "No extra compensatory coupling conditional on the shared stimulus. Re-pair complete receiver-pair trajectory blocks with source blocks from other series of the same roster where possible, tightly matching initial geometry, own-half/attack-half, ball history, score/time and strength. Preserve receiver-pair covariance and within-block autocorrelation. No independent frame shuffle; insufficient exchangeable blocks means no permutation claim."
  },
  "Estimate paired observed-minus-null gains with series-bootstrap CI; obtain the primary p from 2,000 matched-block randomizations with whole series as outer resampling units. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "估计配对的观测减零模型增益及系列赛 bootstrap 置信区间；以完整系列赛为外层重采样单位，通过 2,000 次匹配块随机化获得主 p 值。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Estimate paired observed-minus-null gains with series-bootstrap CI; obtain the primary p from 2,000 matched-block randomizations with whole series as outer resampling units. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Sidewalls, centroid/width, regression to zero velocity and common later ball acceleration. Do not adjust for the future receiver motion itself. Matching the realized ball path is a descriptive sensitivity, not a causal adjustment.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 侧墙、质心/宽度、速度向零回归，以及共同的后续球加速度。不调整未来的接收方运动本身。匹配实际发生的球路径属于描述性敏感性分析，而非因果调整。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Sidewalls, centroid/width, regression to zero velocity and common later ball acceleration. Do not adjust for the future receiver motion itself. Matching the realized ball path is a descriptive sensitivity, not a causal adjustment."
  },
  "Δg≥.15 and ≥.10 after realized-ball-path matching; ≥500 qualifying windows. Prespecified 5/10 Hz analyses must agree in sign. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "Δg≥.15，且匹配实际球路径后 ≥.10；≥500 个合格窗口。预先指定的 5/10 Hz 分析必须同号。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Δg≥.15 and ≥.10 after realized-ball-path matching; ≥500 qualifying windows. Prespecified 5/10 Hz analyses must agree in sign. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests counter-motion and its magnitude, rather than re-running P2's role grammar or declaring all synchrony beneficial.": {
    "zh": "检验反向运动及其幅度，而非重复 P2 的角色语法或宣称所有同步性都有益。",
    "en": "Tests counter-motion and its magnitude, rather than re-running P2's role grammar or declaring all synchrony beneficial."
  },
  "Three colored lateral-velocity voices and a summed coverage trace.": {
    "zh": "三条不同颜色的横向速度声部与一条合计覆盖轨迹。",
    "en": "Three colored lateral-velocity voices and a summed coverage trace."
  },
  "Physics: hysteresis and memory": {
    "zh": "物理学：磁滞与记忆",
    "en": "Physics: hysteresis and memory"
  },
  "At similar present ball states, a ball that arrived from the attacking direction leaves a narrower team than one that has just advanced from defense; team shape retains a measurable history.": {
    "zh": "在相似的当前球状态下，相比刚从防守方向推进的球，从进攻方向回来的球对应更窄的队形；队形保留可测量的历史。",
    "en": "At similar present ball states, a ball that arrived from the attacking direction leaves a narrower team than one that has just advanced from defense; team shape retains a measurable history."
  },
  "At ≥6 s anchors require |ball vy|<300 uu/s. Label previous 1.5 s ball-y displacement >600 uu as forward history and <−600 uu as backward history. Response is mean own-team lateral width max(xi)−min(xi) over [t,t+.5]. Primary effect is forward-minus-backward adjusted width in uu. Match present ball xyz/vxyz, team centroid, current mean velocity and boost; current width is the outcome and is deliberately not adjusted away.": {
    "zh": "间隔 ≥6 秒的锚点要求 |ball vy|<300 uu/秒。前 1.5 秒球的 y 位移 >600 uu 标为前进历史，<−600 uu 标为后退历史。响应为 [t,t+.5] 内己方横向宽度 max(xi)−min(xi) 的均值。主效应为调整后的前进减后退宽度，单位 uu。匹配当前球 xyz/vxyz、队伍质心、当前平均速度与 boost；当前宽度是结局，特意不将其调整掉。",
    "en": "At ≥6 s anchors require |ball vy|<300 uu/s. Label previous 1.5 s ball-y displacement >600 uu as forward history and <−600 uu as backward history. Response is mean own-team lateral width max(xi)−min(xi) over [t,t+.5]. Primary effect is forward-minus-backward adjusted width in uu. Match present ball xyz/vxyz, team centroid, current mean velocity and boost; current width is the outcome and is deliberately not adjusted away."
  },
  "Current ball state, translation and resources suffice to explain width: conditional history contrast=0. First use within-series matched turning states; otherwise match same-roster/season/region states with overlap. A separate baseline including width 1.5 s earlier tests whether the contrast is simply carried-over starting width.": {
    "zh": "当前球状态、平移与资源足以解释宽度：条件历史对比=0。优先使用系列赛内匹配的转向状态，否则匹配有重叠的同阵容/赛季/赛区状态。另设包含 1.5 秒前宽度的基线，检验对比是否仅来自起始宽度的延续。",
    "en": "Current ball state, translation and resources suffice to explain width: conditional history contrast=0. First use within-series matched turning states; otherwise match same-roster/season/region states with overlap. A separate baseline including width 1.5 s earlier tests whether the contrast is simply carried-over starting width."
  },
  "Series-bootstrap standardized matched width contrast and null-centered p; report overlap/balance before interpreting the contrast. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "通过系列赛 bootstrap 估计标准化匹配宽度对比及以零假设为中心的 p 值；先报告重叠与平衡，再解释对比。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap standardized matched width contrast and null-centered p; report overlap/balance before interpreting the contrast. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Ball wall distance, turn magnitude, earlier team width, ball-height history and roster composition. This is geometric persistence, not psychological inertia or a causal history intervention. Override C's full current player-coordinate adjustment here: use centroid and earlier width, not the three current x coordinates or current width, which algebraically determine the response.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 球到墙的距离、转向幅度、较早的队形宽度、球高度历史与阵容构成。这是几何持续性，不是心理惯性或因果历史干预。此处替代 C 的完整当前球员坐标调整：使用质心和较早宽度，不使用三个当前 x 坐标或当前宽度，因为它们在代数上决定响应。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Ball wall distance, turn magnitude, earlier team width, ball-height history and roster composition. This is geometric persistence, not psychological inertia or a causal history intervention. Override C's full current player-coordinate adjustment here: use centroid and earlier width, not the three current x coordinates or current width, which algebraically determine the response."
  },
  "Forward-minus-backward width≥150 uu; ≥150 matched windows per history class. Sign must survive 1/2 s history definitions and conditioning on earlier width. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "前进减后退宽度≥150 uu；每类历史 ≥150 个匹配窗口。使用 1/2 秒历史定义及条件化较早宽度后，符号必须保持。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Forward-minus-backward width≥150 uu; ≥150 matched windows per history class. Sign must survive 1/2 s history definitions and conditioning on earlier width. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "A specific state-history loop and physical-unit effect; more concrete than generic momentum or late-game aggression.": {
    "zh": "具体的状态历史回路与有物理单位的效应；比泛称势头或末段激进更明确。",
    "en": "A specific state-history loop and physical-unit effect; more concrete than generic momentum or late-game aggression."
  },
  "Width-versus-ball-y loop with arrows showing the two arrival histories.": {
    "zh": "宽度与球 y 坐标的回路图，用箭头标出两种到达历史。",
    "en": "Width-versus-ball-y loop with arrows showing the two arrival histories."
  },
  "Reliability engineering: single-point dependence": {
    "zh": "可靠性工程：单点依赖",
    "en": "Reliability engineering: single-point dependence"
  },
  "Equal total geometric coverage can hide unequal reliance on one defender; the more brittle formation is associated with more near-term concessions.": {
    "zh": "相同的总几何覆盖可能掩盖对单个防守者不同程度的依赖；更脆弱的阵型与更多近期失球相关。",
    "en": "Equal total geometric coverage can hide unequal reliance on one defender; the more brittle formation is associated with more near-term concessions."
  },
  "On the fixed own-half xy grid, cell ownership means nearest own player is closer than nearest opponent. Let A be the owned fraction, and A−i the fraction after virtually omitting own player i. For A≥.10 define B=max_i(A−A−i)/A. At ≥6 s prospective anchors, primary effect is the adjusted concession-risk difference within 3 s for B's upper versus lower training-defined tertile, controlling A; middle tertile is excluded from this contrast. Also report which player maximizes loss, without calling that player at fault.": {
    "zh": "在固定的己方半场 xy 网格上，最近己方球员比最近对手更近即视为己方占有该格。令 A 为占有比例，A−i 为虚拟移除己方球员 i 后的比例。对 A≥.10 定义 B=max_i(A−A−i)/A。在间隔 ≥6 秒的前瞻锚点，主效应为控制 A 后，按训练集定义的 B 最高与最低三分位组在 3 秒内的调整后失球风险差；中间三分位组不纳入此对比。同时报告移除哪名球员造成最大损失，但不归责于该球员。",
    "en": "On the fixed own-half xy grid, cell ownership means nearest own player is closer than nearest opponent. Let A be the owned fraction, and A−i the fraction after virtually omitting own player i. For A≥.10 define B=max_i(A−A−i)/A. At ≥6 s prospective anchors, primary effect is the adjusted concession-risk difference within 3 s for B's upper versus lower training-defined tertile, controlling A; middle tertile is excluded from this contrast. Also report which player maximizes loss, without calling that player at fault."
  },
  "At matched initial coverage A, ball threat, resources and context, high/low B have equal future concession probability. Match snapshots on A, nearest-defender distance, ball position/heading/speed/height and number goal-side. Virtual deletion is only a diagnostic of geometry, not a simulated demolition treatment.": {
    "zh": "在初始覆盖 A、球威胁、资源与情境匹配后，高/低 B 的未来失球概率相等。按 A、最近防守者距离、球位置/朝向/速度/高度及位于球门侧的人数匹配快照。虚拟删除仅诊断几何，不是模拟击毁处理。",
    "en": "At matched initial coverage A, ball threat, resources and context, high/low B have equal future concession probability. Match snapshots on A, nearest-defender distance, ball position/heading/speed/height and number goal-side. Virtual deletion is only a diagnostic of geometry, not a simulated demolition treatment."
  },
  "Fit a series-cross-fitted binary risk model and standardize the high-minus-low probability difference over shared support; series-bootstrap CI/p. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "拟合按系列赛交叉拟合的二元风险模型，在共同支持上标准化高减低概率差；用系列赛 bootstrap 估计置信区间/p 值。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Fit a series-cross-fitted binary risk model and standardize the high-minus-low probability difference over shared support; series-bootstrap CI/p. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Own player height and stale coordinates, already imminent shots, boost imbalance and ball-carrying coverage outside the meaningful goal area. Goals must come from audited decoded score changes; see outcome contract. Override C's full simultaneous coordinate control: use A, centroid/extent, nearest-defender distance, goal-side count, height and resources, not every own/opponent coordinate, which determines B and removes exposure overlap.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 己方球员高度与陈旧坐标、已经迫近的射门、boost 不平衡，以及有效球门区域之外的带球覆盖。进球须来自经审计解码的比分变化；见结局约定。替代 C 的完整同时坐标控制：使用 A、质心/范围、最近防守者距离、球门侧人数、高度与资源，不使用全部己方/对手坐标，因为这些坐标决定 B 并消除暴露重叠。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Own player height and stale coordinates, already imminent shots, boost imbalance and ball-carrying coverage outside the meaningful goal area. Goals must come from audited decoded score changes; see outcome contract. Override C's full simultaneous coordinate control: use A, centroid/extent, nearest-defender distance, goal-side count, height and resources, not every own/opponent coordinate, which determines B and removes exposure overlap."
  },
  "Absolute concession-risk increase≥2 percentage points; ≥100 concession anchors across ≥50 series, and ≥200 anchors in each tertile. Same sign at 17×11 and 33×21 grids. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "失球风险绝对增加≥2 个百分点；≥50 个系列赛中 ≥100 个失球锚点，且每个三分位组 ≥200 个锚点。17×11 与 33×21 网格下同号。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Absolute concession-risk increase≥2 percentage points; ≥100 concession anchors across ≥50 series, and ≥200 anchors in each tertile. Same sign at 17×11 and 33×21 grids. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Replaces 'how much coverage?' with 'how fragile is the same coverage?', without needing trustworthy demolition labels.": {
    "zh": "将“覆盖多少”转为“同等覆盖有多脆弱”，无需可靠的击毁标签。",
    "en": "Replaces 'how much coverage?' with 'how fragile is the same coverage?', without needing trustworthy demolition labels."
  },
  "Same-coverage formations with a heat map of cells lost when each car is omitted.": {
    "zh": "相同覆盖的阵型，配合逐车移除后丢失网格的热图。",
    "en": "Same-coverage formations with a heat map of cells lost when each car is omitted."
  },
  "Linguistics: audience design; information theory": {
    "zh": "语言学：受众设计；信息论",
    "en": "Linguistics: audience design; information theory"
  },
  "A focal player's next movement is better predicted by teammate history than equally sized opponent history after controlling the complete present state and ball history.": {
    "zh": "控制完整当前状态与球历史后，队友历史比等量对手历史更能预测焦点球员的下一步运动。",
    "en": "A focal player's next movement is better predicted by teammate history than equally sized opponent history after controlling the complete present state and ball history."
  },
  "Target: focal player's next .5 s lateral displacement classified L/S/R by ±150 uu. Baseline has all six players' current xyz/vxyz/boost and target/ball past 1 s. Add either both teammates' past trajectories or two opponents' past trajectories selected by a fixed nearest-to-target rule. Use the same regularized multinomial model, feature dimension, training count and tuning budget. Primary held-out effect is (log-loss_opponent−log-loss_teammate)/ln(2), bits/action, averaged first within series.": {
    "zh": "目标：按 ±150 uu 将焦点球员未来 .5 秒的横向位移分为 L/S/R。基线包含六名球员当前 xyz/vxyz/boost，以及目标球员/球过去 1 秒的信息。加入两名队友的历史轨迹，或按固定的离目标最近规则选出的两名对手历史轨迹。使用相同正则化多项模型、特征维度、训练量与调参预算。留出集主效应为 (log-loss_opponent−log-loss_teammate)/ln(2)，单位比特/动作，先在系列赛内平均。",
    "en": "Target: focal player's next .5 s lateral displacement classified L/S/R by ±150 uu. Baseline has all six players' current xyz/vxyz/boost and target/ball past 1 s. Add either both teammates' past trajectories or two opponents' past trajectories selected by a fixed nearest-to-target rule. Use the same regularized multinomial model, feature dimension, training count and tuning budget. Primary held-out effect is (log-loss_opponent−log-loss_teammate)/ln(2), bits/action, averaged first within series."
  },
  "No teammate-specific predictive increment. Reassign added 1 s trajectory blocks among geometry/context-matched training windows from different series, retaining full blocks. Match distance and speed distributions of teammate and opponent inputs; report no-overlap exclusions. Baseline and both augmented models are trained only on training series.": {
    "zh": "不存在队友特异的预测增量。在不同系列赛、几何/情境匹配的训练窗口之间重新分配新增的 1 秒轨迹块，保留完整块。匹配队友与对手输入的距离及速度分布；报告无重叠排除。基线及两个增强模型仅在训练系列赛上训练。",
    "en": "No teammate-specific predictive increment. Reassign added 1 s trajectory blocks among geometry/context-matched training windows from different series, retaining full blocks. Match distance and speed distributions of teammate and opponent inputs; report no-overlap exclusions. Baseline and both augmented models are trained only on training series."
  },
  "Paired series-bootstrap of out-of-fold loss advantage and centered p; matched history-block shuffles are the falsification control. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "对折外损失优势作配对系列赛 bootstrap，并计算中心化 p 值；匹配历史块打乱作为证伪对照。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Paired series-bootstrap of out-of-fold loss advantage and centered p; matched history-block shuffles are the falsification control. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Proximity, shared ball forcing, recent ball acceleration, roster familiarity, target-class imbalance and different information dimension. This measures statistical information in recorded movement, not what any player perceived or communicated.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 接近程度、共同球驱动、近期球加速度、阵容熟悉度、目标类别不平衡及信息维度差异。度量的是记录运动中的统计信息，不是球员实际感知或交流的内容。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Proximity, shared ball forcing, recent ball acceleration, roster familiarity, target-class imbalance and different information dimension. This measures statistical information in recorded movement, not what any player perceived or communicated."
  },
  "Advantage≥.02 bits/action; ≥1,000 valid windows and ≥3 adequately represented seasons with the same sign. Must remain positive after proximity matching and left/right reflection. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "优势≥.02 比特/动作；≥1,000 个有效窗口，且 ≥3 个样本充分的赛季同号。在接近程度匹配与左右反射后仍须为正。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Advantage≥.02 bits/action; ≥1,000 valid windows and ≥3 adequately represented seasons with the same sign. Must remain positive after proximity matching and left/right reflection. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "An information-asymmetry question with a readable bits/action effect, rather than building another tactical classifier.": {
    "zh": "研究信息不对称，效应可读为比特/动作，而非再建一个战术分类器。",
    "en": "An information-asymmetry question with a readable bits/action effect, rather than building another tactical classifier."
  },
  "Two equal-size prediction panels explaining which past motion reduces uncertainty.": {
    "zh": "两个等规模预测面板，说明哪些过去运动减少了不确定性。",
    "en": "Two equal-size prediction panels explaining which past motion reduces uncertainty."
  },
  "Game theory: volunteer's dilemma and anti-coordination": {
    "zh": "博弈论：志愿者困境与反协调",
    "en": "Game theory: volunteer's dilemma and anti-coordination"
  },
  "When two teammates have similar opportunity to approach, exactly one approaches more often than context-conditioned independent choices predict.": {
    "zh": "当两名队友具备相似的上前机会时，恰好一人上前的频率高于情境条件下独立选择的预测。",
    "en": "When two teammates have similar opportunity to approach, exactly one approaches more often than context-conditioned independent choices predict."
  },
  "At onset choose the two closest teammates with both ball distances≤1,500 uu, distance gap≤200 uu, ball z<400 uu and an opponent within 2,000 uu. Over the next .5 s, approach=ball-distance reduction≥150 uu and positive mean closing. Cross-fit individual probabilities p1,p2 from initial state and ball history. Primary excess is P(exactly one)−mean[p1(1−p2)+p2(1−p1)], in percentage points.": {
    "zh": "在起点选择最近的两名队友，要求两者到球距离≤1,500 uu、距离差≤200 uu、球 z<400 uu，且 2,000 uu 内有对手。未来 .5 秒内，到球距离减少≥150 uu 且平均接近速度为正即为上前。根据初始状态与球历史交叉拟合个体概率 p1,p2。主超额量为 P(恰好一人)−mean[p1(1−p2)+p2(1−p1)]，单位百分点。",
    "en": "At onset choose the two closest teammates with both ball distances≤1,500 uu, distance gap≤200 uu, ball z<400 uu and an opponent within 2,000 uu. Over the next .5 s, approach=ball-distance reduction≥150 uu and positive mean closing. Cross-fit individual probabilities p1,p2 from initial state and ball history. Primary excess is P(exactly one)−mean[p1(1−p2)+p2(1−p1)], in percentage points."
  },
  "Conditional independence of the two approach responses. Construct matched pseudo-pairs using whole .5 s response blocks from different series, preserving each player's marginal rates, initial opportunity and boost. Fit/calibrate p1,p2 only on inner training-series folds and evaluate untouched outer series; a misspecified independent baseline cannot establish coordination.": {
    "zh": "两名球员的上前响应条件独立。使用不同系列赛的完整 .5 秒响应块构造匹配伪配对，保留各球员边际频率、初始机会与 boost。仅在内层训练系列赛折上拟合/校准 p1,p2，在未接触的外层系列赛上评估；设定错误的独立基线不能证明协调。",
    "en": "Conditional independence of the two approach responses. Construct matched pseudo-pairs using whole .5 s response blocks from different series, preserving each player's marginal rates, initial opportunity and boost. Fit/calibrate p1,p2 only on inner training-series folds and evaluate untouched outer series; a misspecified independent baseline cannot establish coordination."
  },
  "Bootstrap complete series and recompute marginal models; primary p from conditional pseudo-pair randomization. Keep 00/11 frequencies descriptive unless added to the BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "对完整系列赛作 bootstrap 并重算边际模型；主 p 值来自条件伪配对随机化。00/11 频率保持描述性，除非纳入 BH 检验族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Bootstrap complete series and recompute marginal models; primary p from conditional pseudo-pair randomization. Keep 00/11 frequencies descriptive unless added to the BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Shared later ball motion, third-player cover, relative boost, wall proximity, height and distance-derived mechanical dependence. Repeat conditioning on realized ball motion and more exact own movement toward the ball.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 共同的后续球运动、第三人覆盖、相对 boost、距墙距离、高度，以及由距离带来的机械依赖。重复分析时条件化实际球运动及更精确的己方朝球运动。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Shared later ball motion, third-player cover, relative boost, wall proximity, height and distance-derived mechanical dependence. Repeat conditioning on realized ball motion and more exact own movement toward the ball."
  },
  "Excess exactly-one probability≥7 percentage points; ≥500 episodes. Positive at 100/200/300 uu opportunity-gap sensitivity and under the realized-ball control. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "恰好一人的超额概率≥7 个百分点；≥500 个事件。在机会差 100/200/300 uu 的敏感性分析及实际球运动控制下为正。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Excess exactly-one probability≥7 percentage points; ≥500 episodes. Positive at 100/200/300 uu opportunity-gap sensitivity and under the realized-ball control. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests symmetry-breaking when opportunities are tied, rather than counting ordinary handoff gaps.": {
    "zh": "检验机会相当时的对称性破缺，而非统计普通交接缺口。",
    "en": "Tests symmetry-breaking when opportunities are tied, rather than counting ordinary handoff gaps."
  },
  "Four-cell 00/01/10/11 table versus the conditionally independent prediction.": {
    "zh": "00/01/10/11 四格表与条件独立预测对照。",
    "en": "Four-cell 00/01/10/11 table versus the conditionally independent prediction."
  },
  "Physics: chirality and circulation": {
    "zh": "物理学：手性与环流",
    "en": "Physics: chirality and circulation"
  },
  "Some exact rosters have a reproducible signed circulation preference beyond ball-induced movement and uneven left/right field use.": {
    "zh": "某些固定阵容具有可复现的有向环流偏好，超出球诱导运动及左右场地使用不均的解释。",
    "en": "Some exact rosters have a reproducible signed circulation preference beyond ball-induced movement and uneven left/right field use."
  },
  "Let ri=own xy position−own centroid and wi=own xy velocity−own mean velocity. L=Σ(rix*wiy−riy*wix)/Σ||ri||², s⁻¹. Exclude RMS radius<300 uu. Residualize L against ball xyz/vxyz, ball circulation around centroid, width/depth and C. Deterministically split whole series into two balanced halves. Primary statistic: Spearman correlation across roster-average residual L in the two halves.": {
    "zh": "令 ri=己方 xy 位置−己方质心，wi=己方 xy 速度−己方平均速度。L=Σ(rix*wiy−riy*wix)/Σ||ri||²，单位秒⁻¹。排除均方根半径<300 uu。对球 xyz/vxyz、球绕质心的环流、宽度/深度及 C 回归，取 L 残差。确定性地将完整系列赛划为两个平衡半区间。主统计量为各阵容平均残差 L 在两个半区间间的 Spearman 相关。",
    "en": "Let ri=own xy position−own centroid and wi=own xy velocity−own mean velocity. L=Σ(rix*wiy−riy*wix)/Σ||ri||², s⁻¹. Exclude RMS radius<300 uu. Residualize L against ball xyz/vxyz, ball circulation around centroid, width/depth and C. Deterministically split whole series into two balanced halves. Primary statistic: Spearman correlation across roster-average residual L in the two halves."
  },
  "No stable roster handedness. Permute whole roster-series summary labels in one half within season/region/strength strata, preserving each roster's series count and keeping paired opponents together during outer series resampling. Audit exchangeability; if roster labels cannot be permuted credibly use only descriptive intervals, not a passing p.": {
    "zh": "不存在稳定的阵容惯用方向。在赛季/赛区/实力分层内置换一个半区间的完整阵容系列赛汇总标签，保留各阵容系列赛数量，并在外层系列赛重采样时将配对对手共同保留。审计可交换性；若无法可信地置换阵容标签，仅报告描述性区间，不报告通过门槛的 p 值。",
    "en": "No stable roster handedness. Permute whole roster-series summary labels in one half within season/region/strength strata, preserving each roster's series count and keeping paired opponents together during outer series resampling. Audit exchangeability; if roster labels cannot be permuted credibly use only descriptive intervals, not a passing p."
  },
  "2,000 restricted whole-series label permutations for correlation; series-bootstrap CI with adequate representation in both halves. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以 2,000 次受限完整系列赛标签置换检验相关；在两个半区间均有充分代表时计算系列赛 bootstrap 置信区间。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "2,000 restricted whole-series label permutations for correlation; series-bootstrap CI with adequate representation in both halves. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Kickoff-side imbalance, ball circulation, tiny triangles, roster turnover, unequal field-side occupancy and identity errors. Reflect x: L must change sign but split-half reproducibility must not. Override C's full simultaneous player-state adjustment: control centroid, extent, side occupancy and ball forcing, not every instantaneous player position/velocity, which would algebraically determine L. Exclude focal roster_id and player_ids from the nuisance residualizer: roster fixed effects would remove the mean handedness signal. Use identities for aggregation, partitioning and permutation, while retaining contextual and opponent-strength adjustment.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 开球侧不平衡、球环流、过小三角形、阵容更替、左右场地占用不均及身份错误。反射 x：L 必须反号，但分半可复现性不应改变。替代 C 的完整同时球员状态调整：控制质心、范围、侧边占用及球驱动，不使用每个瞬时球员位置/速度，因为它们在代数上决定 L。从干扰残差模型中排除焦点 roster_id 与 player_ids：阵容固定效应会移除平均惯用方向信号。身份仅用于汇总、划分与置换，同时保留情境及对手实力调整。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Kickoff-side imbalance, ball circulation, tiny triangles, roster turnover, unequal field-side occupancy and identity errors. Reflect x: L must change sign but split-half reproducibility must not. Override C's full simultaneous player-state adjustment: control centroid, extent, side occupancy and ball forcing, not every instantaneous player position/velocity, which would algebraically determine L. Exclude focal roster_id and player_ids from the nuisance residualizer: roster fixed effects would remove the mean handedness signal. Use identities for aggregation, partitioning and permutation, while retaining contextual and opponent-strength adjustment."
  },
  "Correlation≥.40; ≥10 rosters with ≥8 independent series each, ≥4 in each half. Result must survive equal left/right occupancy reweighting. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and stable positive split-half correlation under a second prespecified balanced split (this replaces the generic within-half sign gate, since the primary statistic already compares halves). These are proposed gates, not results.": {
    "zh": "相关≥.40；≥10 个阵容，每个 ≥8 个独立系列赛，每半区间 ≥4 个。左右占用等权重加权后结果必须保留。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Correlation≥.40; ≥10 rosters with ≥8 independent series each, ≥4 in each half. Result must survive equal left/right occupancy reweighting. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and stable positive split-half correlation under a second prespecified balanced split (this replaces the generic within-half sign gate, since the primary statistic already compares halves). These are proposed gates, not results."
  },
  "Identifies handedness rather than a generic boost/aerial style fingerprint.": {
    "zh": "识别惯用方向，而非一般的 boost/空中风格指纹。",
    "en": "Identifies handedness rather than a generic boost/aerial style fingerprint."
  },
  "Anonymous clockwise/counterclockwise trajectory ribbons and split-half scatter.": {
    "zh": "匿名顺/逆时针轨迹带与分半散点图。",
    "en": "Anonymous clockwise/counterclockwise trajectory ribbons and split-half scatter."
  },
  "Pragmatics and signaling games: geometric ambiguity": {
    "zh": "语用学与信号博弈：几何模糊性",
    "en": "Pragmatics and signaling games: geometric ambiguity"
  },
  "Two separated players with similarly short approach-time proxies are associated with more opponent slowing than a clear primary approacher, beyond ordinary congestion.": {
    "zh": "两名相互分开的球员具有相近且较短的接近时间代理值时，相比明确的主要接近者，对手更常减速，且超出普通拥挤的解释。",
    "en": "Two separated players with similarly short approach-time proxies are associated with more opponent slowing than a clear primary approacher, beyond ordinary congestion."
  },
  "For each player c_i=vi_xy·(ball_xy−pi_xy)/d_i and τ_i=d_i/c_i, with c_i>300 uu/s and d_i∈[500,2500] uu. τ is a straight-line proxy, not interception time. Compare two candidates with |τ1−τ2|≤.15 s versus ≥.5 s, crossed with lateral separation≥1,200 versus≤600 uu. Low ball z<300 and |vz|<300 primary. Response: initially ball-approaching nearest opponent (c≥500, d>800) reduces its c by≥300 uu/s over next .5 s. Primary effect is ambiguity-by-separation interaction in probability: (ambiguous−clear)_wide−(ambiguous−clear)_narrow.": {
    "zh": "对每名球员定义 c_i=vi_xy·(ball_xy−pi_xy)/d_i，τ_i=d_i/c_i，要求 c_i>300 uu/秒、d_i∈[500,2500] uu。τ 是直线代理值，不是拦截时间。比较 |τ1−τ2|≤.15 秒与 ≥.5 秒的两名候选者，并与横向间距≥1,200 或 ≤600 uu 交叉分组。主分析要求低球 z<300 且 |vz|<300。响应为：初始正在接近球的最近对手（c≥500，d>800）在未来 .5 秒内将 c 降低≥300 uu/秒。主效应为概率上的模糊性与间距交互：(模糊−明确)_宽−(模糊−明确)_窄。",
    "en": "For each player c_i=vi_xy·(ball_xy−pi_xy)/d_i and τ_i=d_i/c_i, with c_i>300 uu/s and d_i∈[500,2500] uu. τ is a straight-line proxy, not interception time. Compare two candidates with |τ1−τ2|≤.15 s versus ≥.5 s, crossed with lateral separation≥1,200 versus≤600 uu. Low ball z<300 and |vz|<300 primary. Response: initially ball-approaching nearest opponent (c≥500, d>800) reduces its c by≥300 uu/s over next .5 s. Primary effect is ambiguity-by-separation interaction in probability: (ambiguous−clear)_wide−(ambiguous−clear)_narrow."
  },
  "No ambiguity interaction at comparable urgency. Match minimum τ, broad mean-distance/overall-speed strata, defender geometry/boost and ball history within each separation band. Do not simultaneously match both candidate distances and summed c, or every candidate coordinate/velocity: these can determine the τ gap and eliminate ambiguity overlap. Keep the separation contrast identifiable using within-band opportunity controls.": {
    "zh": "在相近紧迫程度下不存在模糊性交互。在各间距组内匹配最小 τ、粗略平均距离/总体速度分层、防守者几何/boost 与球历史。不同时匹配两名候选者距离与 c 之和，也不匹配每个候选者坐标/速度：这些可能决定 τ 差并消除模糊性重叠。通过组内机会控制保持间距对比可识别。",
    "en": "No ambiguity interaction at comparable urgency. Match minimum τ, broad mean-distance/overall-speed strata, defender geometry/boost and ball history within each separation band. Do not simultaneously match both candidate distances and summed c, or every candidate coordinate/velocity: these can determine the τ gap and eliminate ambiguity overlap. Keep the separation contrast identifiable using within-band opportunity controls."
  },
  "Series-bootstrap standardized probability difference-in-differences and centered p. Four simple cell comparisons are explanatory, or enter the expanded BH family if tested. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计标准化概率双重差分及中心化 p 值。四个简单单元对比用于解释；若作检验则纳入扩展 BH 族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap standardized probability difference-in-differences and centered p. Four simple cell comparisons are explanatory, or enter the expanded BH family if tested. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Ball deceleration, defender already braking, sidewalls, aerial feasibility and shared transition direction. No claim of hesitation as a mental state or deliberate deception. The preceding exception overrides C's full current candidate geometry adjustment; report balance in broad urgency covariates and actual overlap in the four cells.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 球减速、防守者已在刹车、侧墙、空中可行性与共同转换方向。不将犹豫解释为心理状态，也不声称有意欺骗。上述例外替代 C 的完整当前候选者几何调整；报告粗略紧迫程度协变量的平衡及四个单元中的实际重叠。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Ball deceleration, defender already braking, sidewalls, aerial feasibility and shared transition direction. No claim of hesitation as a mental state or deliberate deception. The preceding exception overrides C's full current candidate geometry adjustment; report balance in broad urgency covariates and actual overlap in the four cells."
  },
  "Interaction≥5 percentage points; ≥100 anchors per cell and ≥30 series per cell. Same direction after matching realized ball acceleration; validate common support between ambiguity conditions. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "交互≥5 个百分点；每单元 ≥100 个锚点及 ≥30 个系列赛。匹配实际球加速度后同方向；验证模糊条件间的共同支持。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Interaction≥5 percentage points; ≥100 anchors per cell and ≥30 series per cell. Same direction after matching realized ball acceleration; validate common support between ambiguity conditions. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Measures the price of ambiguous approach geometry, rather than assuming every simultaneous approach is a mistake.": {
    "zh": "测量接近几何模糊性的代价，而非假设每次同时上前都是失误。",
    "en": "Measures the price of ambiguous approach geometry, rather than assuming every simultaneous approach is a mistake."
  },
  "Four matched diagrams and an opponent speed trace.": {
    "zh": "四张匹配示意图与一条对手速度轨迹。",
    "en": "Four matched diagrams and an opponent speed trace."
  },
  "Ecology and finance: resource insurance and joint tail risk": {
    "zh": "生态学与金融：资源保险与联合尾部风险",
    "en": "Ecology and finance: resource insurance and joint tail risk"
  },
  "Pairs of teammates experience fewer simultaneous low-boost states than expected from calibrated individual resource-risk models sharing the same observed starting state.": {
    "zh": "相比共享同一观测初始状态的、经校准的个体资源风险模型预测，队友配对同时处于低 boost 的情况更少。",
    "en": "Pairs of teammates experience fewer simultaneous low-boost states than expected from calibrated individual resource-risk models sharing the same observed starting state."
  },
  "At ≥6 s anchors with known normalized boost u, let Yi=1 if player i has u<.20 at t+1 s. Cross-fit p_i=P(Yi=1|all six initial xyz/vxyz/u, past 1 s ball/boost history,C). All pair sums run only over focal teammates i,j∈{0,1,2}; all six players are in the conditioning set. Primary R_pair=series-weighted mean[Σi<j YiYj]/series-weighted mean[Σi<j p_i*p_j], observed pairwise shortage divided by conditionally independent expected shortage. Test log(R_pair). Also report the absolute difference in pair-shortage probability (divide both sums by 3). The three pairs are not independent samples; future team-total boost is not a control.": {
    "zh": "在间隔 ≥6 秒且归一化 boost u 已知的锚点，若球员 i 在 t+1 秒时 u<.20，则 Yi=1。交叉拟合 p_i=P(Yi=1|六名球员初始 xyz/vxyz/u、过去 1 秒球/boost 历史、C)。所有配对求和仅覆盖焦点队友 i,j∈{0,1,2}；条件集中包含全部六人。主指标 R_pair=系列赛加权 mean[Σi<j YiYj]/系列赛加权 mean[Σi<j p_i*p_j]，即观测双人短缺除以条件独立预期短缺。检验 log(R_pair)。另报告双人短缺概率绝对差（两求和均除以 3）。三个配对不是独立样本；未来全队总 boost 不作控制变量。",
    "en": "At ≥6 s anchors with known normalized boost u, let Yi=1 if player i has u<.20 at t+1 s. Cross-fit p_i=P(Yi=1|all six initial xyz/vxyz/u, past 1 s ball/boost history,C). All pair sums run only over focal teammates i,j∈{0,1,2}; all six players are in the conditioning set. Primary R_pair=series-weighted mean[Σi<j YiYj]/series-weighted mean[Σi<j p_i*p_j], observed pairwise shortage divided by conditionally independent expected shortage. Test log(R_pair). Also report the absolute difference in pair-shortage probability (divide both sums by 3). The three pairs are not independent samples; future team-total boost is not a control."
  },
  "Conditional independence of future shortages given shared starting resources, geometry and past ball forcing. Null expected pair count is Σp_i*p_j evaluated at the real observed starting states. No exact permutation can preserve all continuous states and common future shocks; use the model-based null with audited held-out marginal calibration and series-bootstrap uncertainty. Never condition on realized future total boost, which can manufacture anticorrelation.": {
    "zh": "给定共同起始资源、几何与过去球驱动后，未来短缺条件独立。零模型预期配对数为在真实观测初始状态上评估的 Σp_i*p_j。没有精确置换能保留所有连续状态与共同未来冲击；采用模型零假设，审计留出集边际校准，并以系列赛 bootstrap 估计不确定性。不得条件化实际未来总 boost，这会人为制造负相关。",
    "en": "Conditional independence of future shortages given shared starting resources, geometry and past ball forcing. Null expected pair count is Σp_i*p_j evaluated at the real observed starting states. No exact permutation can preserve all continuous states and common future shocks; use the model-based null with audited held-out marginal calibration and series-bootstrap uncertainty. Never condition on realized future total boost, which can manufacture anticorrelation."
  },
  "Whole-series bootstrap of log R_pair, refitting cross-fitted marginal models, and centered null test log R_pair=0. No simulated Bernoulli draw is treated as an independent observed sample. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "对 log R_pair 作完整系列赛 bootstrap，重新拟合交叉拟合的边际模型，并进行以 log R_pair=0 为中心的零假设检验。不把模拟 Bernoulli 抽样当作独立观测样本。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Whole-series bootstrap of log R_pair, refitting cross-fitted marginal models, and centered null test log R_pair=0. No simulated Bernoulli draw is treated as an independent observed sample. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Pad encounter geometry, simultaneous respawns/resets, shared boost spending, residual common ball forcing and probability-model calibration. No pad ownership, intentional sharing or altruism inferred. Models use only measured boosts, not boost-button states.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 补给垫遭遇几何、同时重生/重置、共同 boost 消耗、残余共同球驱动与概率模型校准。不推断补给垫所有权、有意分享或利他行为。模型仅使用实测 boost，不使用 boost 按钮状态。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Pad encounter geometry, simultaneous respawns/resets, shared boost spending, residual common ball forcing and probability-model calibration. No pad ownership, intentional sharing or altruism inferred. Models use only measured boosts, not boost-button states."
  },
  "R_pair≤.80, absolute pair-shortage reduction≥1 percentage point, ≥200 observed and ≥200 expected pair-shortage events across ≥50 series; held-out marginal calibration absolute error≤.03 in prespecified broad risk bins with adequate support. Triple shortages are descriptive only, not an alternative primary endpoint. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "R_pair≤.80，双人短缺绝对减少≥1 个百分点；≥50 个系列赛中，观测双人短缺事件 ≥200，预期双人短缺事件 ≥200；在预先指定且支持充分的粗风险分箱中，留出集边际校准绝对误差≤.03。三人短缺仅作描述，不作替代主终点。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "R_pair≤.80, absolute pair-shortage reduction≥1 percentage point, ≥200 observed and ≥200 expected pair-shortage events across ≥50 series; held-out marginal calibration absolute error≤.03 in prespecified broad risk bins with adequate support. Triple shortages are descriptive only, not an alternative primary endpoint. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests resource-risk pooling, beyond P2's low-boost role takeover and beyond individual movement style.": {
    "zh": "检验资源风险共担，超出 P2 的低 boost 角色接管及个体运动风格。",
    "en": "Tests resource-risk pooling, beyond P2's low-boost role takeover and beyond individual movement style."
  },
  "Three fuel gauges with observed versus independent joint-empty frequency.": {
    "zh": "三个油量表，配合观测与独立基线的同时耗尽频率。",
    "en": "Three fuel gauges with observed versus independent joint-empty frequency."
  },
  "Ecology: response diversity and resilience": {
    "zh": "生态学：响应多样性与韧性",
    "en": "Ecology: response diversity and resilience"
  },
  "Different immediate longitudinal reactions to the same adverse ball reversal are associated with less subsequent backward ball travel, even at the same mean team response.": {
    "zh": "对同一次不利球反转的不同即时纵向反应，与后续更少的球后退相关，即使全队平均响应相同。",
    "en": "Different immediate longitudinal reactions to the same adverse ball reversal are associated with less subsequent backward ball travel, even at the same mean team response."
  },
  "Detect ball vy changing from >500 to <−500 uu/s, both sustained≥.3 s, with ≥3 s between events. Over [0,.4] s compute SD of the three players' Δvy and residualize it against mean Δvy and initial velocities using other series. Upper/lower training-tertile residual diversity is exposure. Outcome: maximum backward ball excursion over [.5,2.5] s relative to ball y at .5. Primary effect is low-diversity minus high-diversity adjusted excursion, uu; exposure and outcome windows do not overlap.": {
    "zh": "检测球 vy 从 >500 变为 <−500 uu/秒，两侧均持续≥.3 秒，事件间隔 ≥3 秒。在 [0,.4] 秒内计算三名球员 Δvy 的标准差，并使用其他系列赛，对平均 Δvy 与初始速度回归取残差。暴露为按训练集三分位定义的残差多样性最高/最低组。结局为 [.5,2.5] 秒内相对 .5 秒时球 y 坐标的最大后退距离。主效应为低多样性减高多样性的调整后回撤，单位 uu；暴露与结局窗口不重叠。",
    "en": "Detect ball vy changing from >500 to <−500 uu/s, both sustained≥.3 s, with ≥3 s between events. Over [0,.4] s compute SD of the three players' Δvy and residualize it against mean Δvy and initial velocities using other series. Upper/lower training-tertile residual diversity is exposure. Outcome: maximum backward ball excursion over [.5,2.5] s relative to ball y at .5. Primary effect is low-diversity minus high-diversity adjusted excursion, uu; exposure and outcome windows do not overlap."
  },
  "No diversity association beyond common response magnitude and initial state. Match reversal magnitude, all starting geometry, average response and resources. Re-pair diversity/outcome event blocks across matched series only; the primary adjusted comparison is observational.": {
    "zh": "除共同响应幅度与初始状态外，不存在多样性关联。匹配反转幅度、全部初始几何、平均响应与资源。仅在匹配系列赛间重新配对多样性/结局事件块；主调整对比是观测性的。",
    "en": "No diversity association beyond common response magnitude and initial state. Match reversal magnitude, all starting geometry, average response and resources. Re-pair diversity/outcome event blocks across matched series only; the primary adjusted comparison is observational."
  },
  "Series-bootstrap standardized excursion reduction and centered p; matched series-block label permutation as a support check. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计标准化回撤减少量及中心化 p 值；以匹配系列赛块标签置换作支持性检查。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap standardized excursion reduction and centered p; matched series-block label permutation as a support check. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Existing goal-side defender, walls, double reversals, opponent motion and a single defender dominating the SD. Adjust most-defensive-player response in a sensitivity analysis. Apply the shared goal/reset trajectory censoring rule.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 已有球门侧防守者、墙壁、二次反转、对手运动，以及单个防守者主导标准差。敏感性分析调整最靠防守端球员的响应。应用共同的进球/重置轨迹删失规则。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Existing goal-side defender, walls, double reversals, opponent motion and a single defender dominating the SD. Adjust most-defensive-player response in a sensitivity analysis. Apply the shared goal/reset trajectory censoring rule."
  },
  "Excursion reduction≥200 uu; ≥400 reversals across ≥50 series; remains positive after the most-defensive-player control and complete-horizon sensitivity. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "回撤减少≥200 uu；≥50 个系列赛中 ≥400 次反转；加入最靠防守端球员控制及完整时间范围敏感性后仍为正。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Excursion reduction≥200 uu; ≥400 reversals across ≥50 series; remains positive after the most-defensive-player control and complete-horizon sensitivity. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Asks whether heterogeneity helps at fixed average effort, rather than equating coordination with sameness.": {
    "zh": "在平均投入固定时考察异质性是否有益，而非把协调等同于一致。",
    "en": "Asks whether heterogeneity helps at fixed average effort, rather than equating coordination with sameness."
  },
  "Three response arrows after the same reversal, followed by ball excursion envelopes.": {
    "zh": "同一次反转后的三条响应箭头，随后展示球回撤包络。",
    "en": "Three response arrows after the same reversal, followed by ball excursion envelopes."
  },
  "Ecology: pursuit externalities and decoy geometry": {
    "zh": "生态学：追逐外部性与诱饵几何",
    "en": "Ecology: pursuit externalities and decoy geometry"
  },
  "An off-ball player followed away from the ball is associated with a widening geometric lane for a teammate. 'Decoy' is only a descriptive metaphor.": {
    "zh": "无球球员被跟随并远离球，与队友几何通道拓宽相关。“诱饵”仅是描述性比喻。",
    "en": "An off-ball player followed away from the ball is associated with a widening geometric lane for a teammate. 'Decoy' is only a descriptive metaphor."
  },
  "Candidate: own player initially >700 uu from ball, increasing that distance≥300 uu over .5 s. Pursuit=one initially nearby opponent (within1,500 uu) reduces distance to that player≥200 uu while increasing own ball distance≥200 uu. At onset freeze the other teammate nearest the ball. Let corridor clearance be minimum opponent-to-line-segment distance for the segment from that teammate to the current ball, clipped [0,2000] uu. Primary effect: pursuit versus matched no-pursuit difference in clearance change from t to t+1 s.": {
    "zh": "候选者：己方球员起初距球 >700 uu，并在 .5 秒内将距离增加≥300 uu。追随定义为：一名起初较近（1,500 uu 内）的对手，到该球员距离减少≥200 uu，同时自身到球距离增加≥200 uu。在起点固定另外两名队友中离球最近者。通道净宽为该队友至当前球的线段与对手间最小距离，截断至 [0,2000] uu。主效应为追随与匹配无追随事件在 t 至 t+1 秒净宽变化上的差。",
    "en": "Candidate: own player initially >700 uu from ball, increasing that distance≥300 uu over .5 s. Pursuit=one initially nearby opponent (within1,500 uu) reduces distance to that player≥200 uu while increasing own ball distance≥200 uu. At onset freeze the other teammate nearest the ball. Let corridor clearance be minimum opponent-to-line-segment distance for the segment from that teammate to the current ball, clipped [0,2000] uu. Primary effect: pursuit versus matched no-pursuit difference in clearance change from t to t+1 s."
  },
  "No extra lane opening associated with pursuit once initial state and prior opening trend are matched. Match onset corridor clearance and its preceding .5 s change, full ball/player state, walls and C; compare same-roster event blocks. A negative-control preceding interval must not already show the full effect.": {
    "zh": "匹配初始状态及先前开阔趋势后，追随不关联额外通道拓宽。匹配起点通道净宽及此前 .5 秒变化、完整球/球员状态、墙壁与 C；比较同阵容事件块。作为负对照的前置区间不得已经显示完整效应。",
    "en": "No extra lane opening associated with pursuit once initial state and prior opening trend are matched. Match onset corridor clearance and its preceding .5 s change, full ball/player state, walls and C; compare same-roster event blocks. A negative-control preceding interval must not already show the full effect."
  },
  "Series-bootstrap adjusted clearance-change difference and centered p; restricted pursuit-label permutation only when matched series blocks are exchangeable. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计调整后净宽变化差与中心化 p 值；仅当匹配系列赛块可交换时采用受限追随标签置换。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap adjusted clearance-change difference and centered p; restricted pursuit-label permutation only when matched series blocks are exchangeable. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Common transition direction, ball motion, initial corridor trend, other two defenders, airborne cars and reverse causation. Include a diagnostic using a lane frozen at onset so moving endpoints alone cannot explain the result.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 共同转换方向、球运动、初始通道趋势、另外两名防守者、空中车辆与反向因果。加入起点冻结通道的诊断，排除仅由端点移动解释结果。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Common transition direction, ball motion, initial corridor trend, other two defenders, airborne cars and reverse causation. Include a diagnostic using a lane frozen at onset so moving endpoints alone cannot explain the result."
  },
  "Additional widening≥200 uu; ≥300 candidate episodes. Matched pre-period imbalance<100 uu and frozen-lane effect retains the same sign. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "额外拓宽≥200 uu；≥300 个候选事件。匹配前期不平衡<100 uu，且冻结通道效应保持同号。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Additional widening≥200 uu; ≥300 candidate episodes. Matched pre-period imbalance<100 uu and frozen-lane effect retains the same sign. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "A computable externality of off-ball chasing; does not require bump, demolition, possession or intent labels.": {
    "zh": "可计算的无球追逐外部性；无需碰撞、击毁、控球或意图标签。",
    "en": "A computable externality of off-ball chasing; does not require bump, demolition, possession or intent labels."
  },
  "Matched paired clips showing defender movement and lane clearance.": {
    "zh": "匹配成对片段，展示防守者移动及通道净宽。",
    "en": "Matched paired clips showing defender movement and lane clearance."
  },
  "Linguistics: temporal pragmatics and rhetorical pauses": {
    "zh": "语言学：时间语用与修辞停顿",
    "en": "Linguistics: temporal pragmatics and rhetorical pauses"
  },
  "An approacher's brief kinematic pause is followed by more opponent approach acceleration than a matched uninterrupted approach; the reverse-time association is smaller.": {
    "zh": "相比匹配的不中断接近，接近者短暂的运动学停顿之后，对手更常加速接近；反向时间关联更小。",
    "en": "An approacher's brief kinematic pause is followed by more opponent approach acceleration than a matched uninterrupted approach; the reverse-time association is smaller."
  },
  "Freeze ball-nearest own player while d∈[700,1500] uu and its own velocity component toward ball c≥500 uu/s for .3 s. Pause: c falls below100 for .3 s while d remains>400 uu; use the end of this qualifying .3 s as the response anchor. Compare with uninterrupted episodes at matched elapsed time. Response: initially nearest opponent's c increases≥400 uu/s over next .5 s. Primary risk difference=pause−uninterrupted. Require all ball–car distances>300 uu during the pause, and exclude large ball impulses; no touch labels needed.": {
    "zh": "固定离球最近的己方球员，要求 d∈[700,1500] uu，且其自身朝球速度分量 c≥500 uu/秒持续 .3 秒。停顿定义为 c 降至100以下并持续 .3 秒，同时 d>400 uu；以该合格 .3 秒结束时作为响应锚点。与已用时匹配的不中断事件比较。响应为初始最近对手的 c 在未来 .5 秒增加≥400 uu/秒。主风险差=停顿−不中断。停顿期间所有球车距离须 >300 uu，并排除大幅球冲量；无需触球标签。",
    "en": "Freeze ball-nearest own player while d∈[700,1500] uu and its own velocity component toward ball c≥500 uu/s for .3 s. Pause: c falls below100 for .3 s while d remains>400 uu; use the end of this qualifying .3 s as the response anchor. Compare with uninterrupted episodes at matched elapsed time. Response: initially nearest opponent's c increases≥400 uu/s over next .5 s. Primary risk difference=pause−uninterrupted. Require all ball–car distances>300 uu during the pause, and exclude large ball impulses; no touch labels needed."
  },
  "After matching pre-pause ball/player paths and resources, pause status has no additional opponent-response association. Match pre-pause opponent acceleration and the time already spent approaching; use same-roster windows. Reverse-lag outcome over the .5 s before pause onset is a negative control, never evidence of anticipatory communication.": {
    "zh": "匹配停顿前球/球员轨迹及资源后，停顿状态不再关联额外对手响应。匹配停顿前对手加速度及已接近时长；使用同阵容窗口。停顿起点前 .5 秒的反向滞后结局为负对照，不能作为预期性交流的证据。",
    "en": "After matching pre-pause ball/player paths and resources, pause status has no additional opponent-response association. Match pre-pause opponent acceleration and the time already spent approaching; use same-roster windows. Reverse-lag outcome over the .5 s before pause onset is a negative control, never evidence of anticipatory communication."
  },
  "Series-bootstrap standardized probability difference and centered p; if adding reverse-lag significance, include it in the expanded BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计标准化概率差及中心化 p 值；若加入反向滞后显著性检验，将其纳入扩展 BH 族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap standardized probability difference and centered p; if adding reverse-lag significance, include it in the expanded BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Opponent motion provoking the pause, boost shortage, turning at walls, ball deceleration and missed contacts. Match recent opponent trajectory and use no-large-ball-acceleration sensitivity. Distance exclusion reduces touch confusion but does not prove an intentional fake.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 对手运动引发停顿、boost 短缺、墙边转向、球减速及漏记接触。匹配近期对手轨迹，并进行无大幅球加速度敏感性分析。距离排除减少触球混淆，但不能证明有意假动作。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Opponent motion provoking the pause, boost shortage, turning at walls, ball deceleration and missed contacts. Match recent opponent trajectory and use no-large-ball-acceleration sensitivity. Distance exclusion reduces touch confusion but does not prove an intentional fake."
  },
  "Risk difference≥8 percentage points; ≥300 pauses and300 matched uninterrupted episodes; absolute reverse-lag risk difference≤half the primary estimate, with uncertainty reported. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "风险差≥8 个百分点；≥300 次停顿及300 个匹配不中断事件；反向滞后风险差绝对值≤主估计的一半，并报告不确定性。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Risk difference≥8 percentage points; ≥300 pauses and300 matched uninterrupted episodes; absolute reverse-lag risk difference≤half the primary estimate, with uncertainty reported. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests the function of a measurable pause, not just who changes roles or takes a shot.": {
    "zh": "检验可测停顿的功能，而非仅看谁换角色或射门。",
    "en": "Tests the function of a measurable pause, not just who changes roles or takes a shot."
  },
  "Approach-speed punctuation marks with forward and reverse event-time curves.": {
    "zh": "接近速度标点图，配合正向与反向事件时间曲线。",
    "en": "Approach-speed punctuation marks with forward and reverse event-time curves."
  },
  "Physics and graph theory: percolation and widest paths": {
    "zh": "物理学与图论：渗流与最宽路径",
    "en": "Physics and graph theory: percolation and widest paths"
  },
  "A continuous high-clearance route through the defending half carries information about a near-term concession beyond the nearest defender's distance.": {
    "zh": "穿过防守半场的连续高净空通道，提供超出最近防守者距离的近期失球信息。",
    "en": "A continuous high-clearance route through the defending half carries information about a near-term concession beyond the nearest defender's distance."
  },
  "For ball y∈[−4800,−300], z<300 uu, use the fixed own-half 33×21 grid. Cell clearance is nearest own defender xy distance. From ball cell to central cell at (0,−5120), allow eight-neighbor edges only with nonincreasing y (and no repeated cell). Widest-path clearance W=max_paths min_cell clearance. Define open if W>600 uu. Primary effect: adjusted first-goal-conceded probability within3 s, open minus closed. This is a planar corridor to a fixed goal-line target, not a physically achievable shot.": {
    "zh": "对球 y∈[−4800,−300]、z<300 uu，使用固定己方半场 33×21 网格。格点净空为距最近己方防守者的 xy 距离。从球所在格到 (0,−5120) 中央格，仅允许 y 不增加的八邻接边（且不得重复格点）。最宽路径净空 W=max_paths min_cell clearance。W>600 uu 定义为贯通。主效应为 3 秒内率先失球的调整后概率，贯通减封闭。这是通向固定球门线目标的平面通道，不代表物理上可行的射门。",
    "en": "For ball y∈[−4800,−300], z<300 uu, use the fixed own-half 33×21 grid. Cell clearance is nearest own defender xy distance. From ball cell to central cell at (0,−5120), allow eight-neighbor edges only with nonincreasing y (and no repeated cell). Widest-path clearance W=max_paths min_cell clearance. Define open if W>600 uu. Primary effect: adjusted first-goal-conceded probability within3 s, open minus closed. This is a planar corridor to a fixed goal-line target, not a physically achievable shot."
  },
  "No added corridor association at matched ball xyz/vxyz, nearest-defender distance, goal-side count, initial grid coverage and boost. Include ball heading and speed explicitly; retain both open/closed only on common support. The fixed target avoids assuming any unobserved goal-mouth width.": {
    "zh": "匹配球 xyz/vxyz、最近防守者距离、球门侧人数、初始网格覆盖与 boost 后，不存在额外通道关联。明确纳入球朝向与速度；仅在共同支持上保留贯通/封闭两类。固定目标避免假设未观测的球门口宽度。",
    "en": "No added corridor association at matched ball xyz/vxyz, nearest-defender distance, goal-side count, initial grid coverage and boost. Include ball heading and speed explicitly; retain both open/closed only on common support. The fixed target avoids assuming any unobserved goal-mouth width."
  },
  "Series-bootstrap standardized risk difference and centered p, with nuisance models cross-fitted by series. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计标准化风险差及中心化 p 值，干扰模型按系列赛交叉拟合。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap standardized risk difference and centered p, with nuisance models cross-fitted by series. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Grid discretization, wall proximity, defender height, ball heading, current distance to goal and routes that require impossible turns or more than3 s travel. Do not name W 'shot probability' or infer pad/physics accessibility. Override C's full simultaneous coordinate control: use the named coverage/distance/heading/count summaries and centroid/extent, not every defender coordinate, which determines W and removes open/closed overlap.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 网格离散化、距墙距离、防守者高度、球朝向、当前距球门距离，以及需要不可能转向或超过3 秒行程的路径。不将 W 称为“射门概率”，也不推断补给垫/物理可达性。替代 C 的完整同时坐标控制：使用上述覆盖/距离/朝向/人数汇总与质心/范围，不使用每个防守者坐标，因为它们决定 W 并消除贯通/封闭重叠。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Grid discretization, wall proximity, defender height, ball heading, current distance to goal and routes that require impossible turns or more than3 s travel. Do not name W 'shot probability' or infer pad/physics accessibility. Override C's full simultaneous coordinate control: use the named coverage/distance/heading/count summaries and centroid/extent, not every defender coordinate, which determines W and removes open/closed overlap."
  },
  "Risk difference≥2 percentage points; ≥100 concession anchors in≥50 series, ≥200 open and200 closed anchors. Same sign at600 uu under two grid resolutions;400/800 uu are sensitivity only. Effect must survive nearest-defender and heading controls. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "风险差≥2 个百分点；≥50 个系列赛中 ≥100 个失球锚点，≥200 个贯通和200 个封闭锚点。两种网格分辨率在600 uu 下同号；400/800 uu 仅作敏感性。加入最近防守者与朝向控制后效应须保留。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Risk difference≥2 percentage points; ≥100 concession anchors in≥50 series, ≥200 open and200 closed anchors. Same sign at600 uu under two grid resolutions;400/800 uu are sensitivity only. Effect must survive nearest-defender and heading controls. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests connected empty space rather than team compactness or a single distance.": {
    "zh": "检验连通空白空间，而非队伍紧凑性或单一距离。",
    "en": "Tests connected empty space rather than team compactness or a single distance."
  },
  "A clearance map with the maximum-bottleneck path drawn over the defense.": {
    "zh": "净空图上叠加穿过防线的最大瓶颈路径。",
    "en": "A clearance map with the maximum-bottleneck path drawn over the defense."
  },
  "Physics and ecology: persistence and resilience": {
    "zh": "物理学与生态学：持续性与韧性",
    "en": "Physics and ecology: persistence and resilience"
  },
  "Team-shape deviations persist more strongly before a concession, even at comparable present ball threat and residual variance.": {
    "zh": "在当前球威胁与残差方差相近时，失球前的队形偏离仍有更强的持续性。",
    "en": "Team-shape deviations persist more strongly before a concession, even at comparable present ball threat and residual variance."
  },
  "Every .2 s compute xy triangle area A=abs(cross(p2−p1,p3−p1))/2. Cross-fit expected log(A+10,000 uu²) from ball xyz/vxyz, team centroid, resources and C, without using future outcomes. For each prospective ≥9 s anchor use the preceding6 s in one segment to estimate lag-one (.2 s) residual autocorrelation ρ; omit windows with residual SD<.05 log units. Primary effect: mean adjusted ρ in anchors with opponent first goal within3 s minus matched nonconcession anchors.": {
    "zh": "每 .2 秒计算 xy 三角形面积 A=abs(cross(p2−p1,p3−p1))/2。根据球 xyz/vxyz、队伍质心、资源与 C 交叉拟合预期 log(A+10,000 uu²)，不使用未来结局。对每个间隔 ≥9 秒的前瞻锚点，使用同一片段中之前6 秒估计残差的一阶滞后（.2 秒）自相关 ρ；剔除残差标准差<.05 对数单位的窗口。主效应为对手在3 秒内率先进球的锚点与匹配未失球锚点间，调整后平均 ρ 的差。",
    "en": "Every .2 s compute xy triangle area A=abs(cross(p2−p1,p3−p1))/2. Cross-fit expected log(A+10,000 uu²) from ball xyz/vxyz, team centroid, resources and C, without using future outcomes. For each prospective ≥9 s anchor use the preceding6 s in one segment to estimate lag-one (.2 s) residual autocorrelation ρ; omit windows with residual SD<.05 log units. Primary effect: mean adjusted ρ in anchors with opponent first goal within3 s minus matched nonconcession anchors."
  },
  "No excess shape persistence before concessions once present threat, area and residual variance are matched. Controls include current area, ball distance/heading toward goal, defensive occupancy and resources. Use all prospective anchors, not only sampled pre-goal clips.": {
    "zh": "匹配当前威胁、面积及残差方差后，失球前不存在额外队形持续性。控制变量包括当前面积、球距球门距离/朝向、防守占用与资源。使用所有前瞻锚点，而非仅抽取进球前片段。",
    "en": "No excess shape persistence before concessions once present threat, area and residual variance are matched. Controls include current area, ball distance/heading toward goal, defensive occupancy and resources. Use all prospective anchors, not only sampled pre-goal clips."
  },
  "Series-bootstrap matched autocorrelation difference and centered p. The test concerns temporal persistence; it does not identify a physical critical point or prove an increasing trend toward collapse. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以系列赛 bootstrap 估计匹配自相关差及中心化 p 值。检验针对时间持续性，不能识别物理临界点，也不能证明走向崩溃的递增趋势。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series-bootstrap matched autocorrelation difference and centered p. The test concerns temporal persistence; it does not identify a physical critical point or prove an increasing trend toward collapse. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Sustained ball trapping, residual-model misspecification, small-variance bias, arbitrary sample rate, lookback overlap and resets. Fit on training series and freeze lookback before outcomes. In the residual model, C contributes score/time/region/strength and resources, not all instantaneous individual coordinates (which determine triangle area). Current area and residual variance enter the subsequent event-matching model instead.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 持续困球、残差模型设定错误、小方差偏差、任意采样率、回看窗口重叠及重置。在训练系列赛拟合，并在查看结局前冻结回看窗口。残差模型中，C 提供比分/时间/赛区/实力与资源，不提供全部瞬时个体坐标（它们决定三角形面积）。当前面积及残差方差转而纳入后续事件匹配模型。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Sustained ball trapping, residual-model misspecification, small-variance bias, arbitrary sample rate, lookback overlap and resets. Fit on training series and freeze lookback before outcomes. In the residual model, C contributes score/time/region/strength and resources, not all instantaneous individual coordinates (which determine triangle area). Current area and residual variance enter the subsequent event-matching model instead."
  },
  "Difference inρ≥.08; ≥100 concession anchors across≥50 series and≥200 matched controls; sign stable for4/8 s histories and for lag .4 s (secondary). Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "ρ 差≥.08；≥50 个系列赛中 ≥100 个失球锚点及≥200 个匹配对照；4/8 秒历史及 .4 秒滞后（次要分析）下符号稳定。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Difference inρ≥.08; ≥100 concession anchors across≥50 series and≥200 matched controls; sign stable for4/8 s histories and for lag .4 s (secondary). Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests a concrete persistence statistic before failure, rather than a generic score-prediction model.": {
    "zh": "检验失败前的具体持续性统计量，而非一般比分预测模型。",
    "en": "Tests a concrete persistence statistic before failure, rather than a generic score-prediction model."
  },
  "Area residuals showing fast versus slow decay with matched current formations.": {
    "zh": "面积残差展示快速与缓慢衰减，并匹配当前阵型。",
    "en": "Area residuals showing fast versus slow decay with matched current formations."
  },
  "Traffic physics: string instability": {
    "zh": "交通物理学：串行不稳定性",
    "en": "Traffic physics: string instability"
  },
  "After comparable lateral ball reversals, the rear player's lateral correction is larger than the front player's and exceeds the gain explained by shared forcing.": {
    "zh": "相近的球横向反转之后，后排球员的横向修正大于前排，且超出共同驱动所能解释的增益。",
    "en": "After comparable lateral ball reversals, the rear player's lateral correction is larger than the front player's and exceeds the gain explained by shared forcing."
  },
  "Detect isolated ball vx sign reversals with |Δvx|≥800 uu/s in .3 s, opposite signs sustained≥.3 s. Freeze front/middle/rear by decreasing own y at onset; retain events with ordering unchanged through .8 s and no next reversal within1 s. Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0). Residualize front/rear responses against initial geometry/resources, ball impulse and C. Primary ΔG=observed regression slope(rear~front) minus the slope under matched block re-pairing. Separately require raw conditional gain G≥1.20.": {
    "zh": "检测孤立的球 vx 反号，要求 .3 秒内 |Δvx|≥800 uu/秒，两侧相反符号均持续≥.3 秒。按起点己方 y 降序固定前/中/后排；保留至 .8 秒排序不变且1 秒内无再次反转的事件。Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0)。对初始几何/资源、球冲量及 C 回归，取前/后排响应残差。主 ΔG=观测回归斜率 slope(rear~front) 减去匹配块重新配对后的斜率。另要求原始条件增益 G≥1.20。",
    "en": "Detect isolated ball vx sign reversals with |Δvx|≥800 uu/s in .3 s, opposite signs sustained≥.3 s. Freeze front/middle/rear by decreasing own y at onset; retain events with ordering unchanged through .8 s and no next reversal within1 s. Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0). Residualize front/rear responses against initial geometry/resources, ball impulse and C. Primary ΔG=observed regression slope(rear~front) minus the slope under matched block re-pairing. Separately require raw conditional gain G≥1.20."
  },
  "No excess amplification beyond shared ball forcing. Re-pair whole rear-response blocks with front-response blocks from different series matched on reversal trajectory, spacing, own starting vx and C; keep all within-block dynamics. Do not divide by small front responses.": {
    "zh": "共同球驱动之外不存在额外放大。将完整后排响应块与不同系列赛的前排响应块重新配对，匹配反转轨迹、间距、自身初始 vx 与 C；保留块内全部动态。不除以过小的前排响应。",
    "en": "No excess amplification beyond shared ball forcing. Re-pair whole rear-response blocks with front-response blocks from different series matched on reversal trajectory, spacing, own starting vx and C; keep all within-block dynamics. Do not divide by small front responses."
  },
  "Matched-block randomization for ΔG with series-bootstrap intervals; test one primary excess-gain statistic. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "对 ΔG 作匹配块随机化，配合系列赛 bootstrap 区间；仅检验一个主超额增益统计量。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Matched-block randomization for ΔG with series-bootstrap intervals; test one primary excess-gain statistic. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Front/rear are geometric depth ranks, not tactical leaders; common ball stimulus, wall constraints, boost, selection for stable ordering and response measurement error. A same-time slope cannot establish a causal front-to-rear propagation chain.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 前/后排是几何深度排序，不是战术领导者；共同球刺激、墙壁约束、boost、稳定排序选择及响应测量误差。同时斜率不能确立前至后的因果传播链。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Front/rear are geometric depth ranks, not tactical leaders; common ball stimulus, wall constraints, boost, selection for stable ordering and response measurement error. A same-time slope cannot establish a causal front-to-rear propagation chain."
  },
  "ΔG≥.15 and G≥1.20; ≥300 reversals across≥50 series. Result must survive a sensitivity retaining order changes with onset identities frozen; if only selected stable formations work, narrow the claim. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "ΔG≥.15 且 G≥1.20；≥50 个系列赛中 ≥300 次反转。冻结起点身份并保留排序变化的敏感性分析后结果须保留；若仅选定的稳定阵型有效，应收窄结论。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "ΔG≥.15 and G≥1.20; ≥300 reversals across≥50 series. Result must survive a sensitivity retaining order changes with onset identities frozen; if only selected stable formations work, narrow the claim. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Looks for amplification of corrections, unlike B01's opposite compensation; both can be false.": {
    "zh": "寻找修正的放大，与 B01 的反向补偿不同；两者都可能不成立。",
    "en": "Looks for amplification of corrections, unlike B01's opposite compensation; both can be false."
  },
  "Front/middle/rear response traces and a gain diagram.": {
    "zh": "前/中/后排响应轨迹与增益图。",
    "en": "Front/middle/rear response traces and a gain diagram."
  },
  "Music: entrainment and phase response": {
    "zh": "音乐：节律同步与相位响应",
    "en": "Music: entrainment and phase response"
  },
  "Opponent approach phase predicts a team's approach timing beyond its own cadence and shared ball motion.": {
    "zh": "对手接近相位在本队节律与共同球运动之外，仍能预测本队接近时机。",
    "en": "Opponent approach phase predicts a team's approach timing beyond its own cadence and shared ball motion."
  },
  "Approach pulse: minimum team–ball xy distance crosses below800 uu after being>1200 for≥.3 s; debounce .5 s. Using only prior pulses, cycle T=median(last3 interpulse intervals), all between .8 and4 s. Phase φ=2π(elapsed since last pulse mod T)/T. A series-cross-fitted hazard model predicts next-.1 s own pulse from own history/phase, ball state/history and C, then adds sinφ_opponent and cosφ_opponent. Primary effect ΔD=held-out standardized peak-to-trough predicted pulse-probability modulation minus the modulation from the matched-history null.": {
    "zh": "接近脉冲：全队最小球距 xy 在 >1200 持续≥.3 秒后穿越至800 uu 以下；去抖 .5 秒。仅使用过去脉冲，周期 T=median(最近3 个脉冲间隔)，各间隔均介于 .8 与4 秒。相位 φ=2π(距上次脉冲时间 mod T)/T。按系列赛交叉拟合的风险模型先根据本队历史/相位、球状态/历史及 C 预测未来 .1 秒本队脉冲，再加入 sinφ_opponent 与 cosφ_opponent。主效应 ΔD=留出集标准化峰谷预测脉冲概率调制，减去匹配历史零模型的调制。",
    "en": "Approach pulse: minimum team–ball xy distance crosses below800 uu after being>1200 for≥.3 s; debounce .5 s. Using only prior pulses, cycle T=median(last3 interpulse intervals), all between .8 and4 s. Phase φ=2π(elapsed since last pulse mod T)/T. A series-cross-fitted hazard model predicts next-.1 s own pulse from own history/phase, ball state/history and C, then adds sinφ_opponent and cosφ_opponent. Primary effect ΔD=held-out standardized peak-to-trough predicted pulse-probability modulation minus the modulation from the matched-history null."
  },
  "No residual opponent-phase information. Replace complete opponent pulse-history blocks by other-series blocks matched on current geometry, ball history, own cadence and pulse count; never shuffle individual pulses or use future intervals. Evaluate the complete fitted procedure on held-out series so choosing a peak cannot by itself create a positive result.": {
    "zh": "不存在残余对手相位信息。用其他系列赛中匹配当前几何、球历史、本队节律及脉冲数的完整对手脉冲历史块替换原块；不得打乱单个脉冲或使用未来间隔。在留出系列赛上评估完整拟合程序，使选择峰值本身不能制造正结果。",
    "en": "No residual opponent-phase information. Replace complete opponent pulse-history blocks by other-series blocks matched on current geometry, ball history, own cadence and pulse count; never shuffle individual pulses or use future intervals. Evaluate the complete fitted procedure on held-out series so choosing a peak cannot by itself create a positive result."
  },
  "Joint two-coefficient phase test via2,000 matched history-block randomizations; whole-series bootstrap ΔD CI. Peak-to-trough alone is nonnegative, so its uncorrected size is not a valid null test. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "通过2,000 次匹配历史块随机化进行两个相位系数的联合检验；用完整系列赛 bootstrap 估计 ΔD 置信区间。峰谷差本身非负，因此未经校正的大小不是有效的零假设检验。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Joint two-coefficient phase test via2,000 matched history-block randomizations; whole-series bootstrap ΔD CI. Peak-to-trough alone is nonnegative, so its uncorrected size is not a valid null test. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Shared bounces, wall exchanges, kickoff cadence, uneven pulse rates, ball acceleration/height and finite-cycle selection. Restrict comparisons to phase/cadence ranges with actual support; inspect reverse-direction coupling descriptively.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 共同弹跳、墙边交换、开球节律、不均脉冲频率、球加速度/高度及有限周期选择。对比限于实际支持的相位/节律范围；反向耦合仅作描述性检查。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Shared bounces, wall exchanges, kickoff cadence, uneven pulse rates, ball acceleration/height and finite-cycle selection. Restrict comparisons to phase/cadence ranges with actual support; inspect reverse-direction coupling descriptively."
  },
  "Observed modulation≥5 percentage points per .1 s hazard and ΔD≥3 percentage points above null; ≥500 pulse events in≥50 series; direction/phase relationship reproduces in prespecified held-out series half. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "每 .1 秒风险的观测调制≥5 个百分点，且 ΔD 比零模型高≥3 个百分点；≥50 个系列赛中 ≥500 个脉冲事件；方向/相位关系在预先指定的留出系列赛半区间复现。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Observed modulation≥5 percentage points per .1 s hazard and ΔD≥3 percentage points above null; ≥500 pulse events in≥50 series; direction/phase relationship reproduces in prespecified held-out series half. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests opponent phase-locking within live play, rather than generic game-to-game adaptation.": {
    "zh": "检验活球期间的对手相位锁定，而非一般的局间适应。",
    "en": "Tests opponent phase-locking within live play, rather than generic game-to-game adaptation."
  },
  "Two pulse tracks and a circular phase-response curve.": {
    "zh": "两条脉冲轨迹与一条圆形相位响应曲线。",
    "en": "Two pulse tracks and a circular phase-response curve."
  },
  "Linguistics and music: expectation violation": {
    "zh": "语言学与音乐：违背预期",
    "en": "Linguistics and music: expectation violation"
  },
  "The same physical lateral turn is associated with a slower opponent adjustment when it breaks a previously repeated local route ending.": {
    "zh": "同样的物理横向转向，如果打破此前局部路线末尾的重复模式，则与更慢的对手调整相关。",
    "en": "The same physical lateral turn is associated with a slower opponent adjustment when it breaks a previously repeated local route ending."
  },
  "Route symbols every .5 s: L if Δx<−150 uu, S if |Δx|≤150, R if Δx>150. Keep a focal player within2000 uu of ball and with own toward-ball component>300. A three-symbol prefix qualifies only after≥3 earlier nonoverlapping occurrences in the same replay/player, with a common next symbol in≥75%. An observed alternative L/R ending is a variation. Anchor response measurement at the end of that ending interval (exposure then known). Freeze nearest opponent at ending onset. Latency=first onset within next1 s for which opponent vx takes the new-turn sign with magnitude≥200 uu/s for .3 s. Require observation through1.3 s to verify the sustain, including for onsets near1 s; alignment already present at anchor counts0 only if sustained through.3 s. No qualifying onset by1 s gives1. Primary effect: adjusted mean capped latency versus physically matched L/R endings without established repetition.": {
    "zh": "每 .5 秒生成路线符号：Δx<−150 uu 为 L，|Δx|≤150 为 S，Δx>150 为 R。保留距球2000 uu 内且自身朝球分量>300 的焦点球员。三符号前缀仅在同回放/球员中已有≥3 次更早且不重叠的出现、且≥75% 采用共同后续符号时合格。观测到另一种 L/R 结尾即为变奏。以该结尾区间结束时测量响应（此时暴露已知）。在结尾开始时固定最近对手。延迟=未来1 秒内，对手 vx 首次采用新转向符号、幅度≥200 uu/秒且持续 .3 秒的起点。须观测至1.3 秒以核验持续性，包括接近1 秒的起点；锚点已有同向运动，仅在持续至 .3 秒时记0。1 秒内无合格起点记1。主效应为相对物理匹配、但未形成既定重复的 L/R 结尾，调整后的平均截顶延迟差。",
    "en": "Route symbols every .5 s: L if Δx<−150 uu, S if |Δx|≤150, R if Δx>150. Keep a focal player within2000 uu of ball and with own toward-ball component>300. A three-symbol prefix qualifies only after≥3 earlier nonoverlapping occurrences in the same replay/player, with a common next symbol in≥75%. An observed alternative L/R ending is a variation. Anchor response measurement at the end of that ending interval (exposure then known). Freeze nearest opponent at ending onset. Latency=first onset within next1 s for which opponent vx takes the new-turn sign with magnitude≥200 uu/s for .3 s. Require observation through1.3 s to verify the sustain, including for onsets near1 s; alignment already present at anchor counts0 only if sustained through.3 s. No qualifying onset by1 s gives1. Primary effect: adjusted mean capped latency versus physically matched L/R endings without established repetition."
  },
  "No history-specific delay after matching the actual turn, ball motion, current opponent velocity and prior trajectories. Reassign repetition histories only across same-player/roster context-matched occurrences, preserving current route and response blocks; histories must be strictly earlier. Never infer a prefix's expected ending from future occurrences.": {
    "zh": "匹配实际转向、球运动、当前对手速度及先前轨迹后，不存在历史特异延迟。仅在同球员/阵容、情境匹配的事件间重新分配重复历史，保留当前路线与响应块；历史必须严格早于事件。不得用未来出现推断前缀的预期结尾。",
    "en": "No history-specific delay after matching the actual turn, ball motion, current opponent velocity and prior trajectories. Reassign repetition histories only across same-player/roster context-matched occurrences, preserving current route and response blocks; histories must be strictly earlier. Never infer a prefix's expected ending from future occurrences."
  },
  "Whole-series bootstrap of the matched capped-latency difference and centered p. The cap defines a restricted one-second response-time estimand; missing/reset-censored responses follow the outcome contract. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "对匹配截顶延迟差作完整系列赛 bootstrap 并计算中心化 p 值。截顶定义了一秒限制响应时间估计目标；缺失/重置删失响应遵守结局约定。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Whole-series bootstrap of the matched capped-latency difference and centered p. The cap defines a restricted one-second response-time estimand; missing/reset-censored responses follow the outcome contract. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Long games producing more repetition, role/position selection, mechanical turn difficulty, ball tracking instead of player tracking, already moving opponents and hindsight choice of prefix. Report both pre-anchor alignment and post-anchor delay without uncorrected fishing.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 长局产生更多重复、角色/位置选择、转向机械难度、追踪球而非球员、已在移动的对手，以及事后选择前缀。同时报告锚点前同向状态与锚点后延迟，不作未经校正的筛选。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Long games producing more repetition, role/position selection, mechanical turn difficulty, ball tracking instead of player tracking, already moving opponents and hindsight choice of prefix. Report both pre-anchor alignment and post-anchor delay without uncorrected fishing."
  },
  "Latency increase≥.10 s (one compact frame); ≥100 qualifying variations across≥50 series and≥100 matched controls. Require a raw30 Hz timing validation subset before scaling; no new signals beyond existing raw columns. Sparse support remains inconclusive, with no post hoc relaxed prefix rule. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "延迟增加≥.10 秒（一个紧凑帧）；≥50 个系列赛中 ≥100 个合格变奏及≥100 个匹配对照。扩大规模前须有原始30 Hz 时间验证子集；不使用现有原始列之外的新信号。支持稀疏则保持不确定，不事后放宽前缀规则。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Latency increase≥.10 s (one compact frame); ≥100 qualifying variations across≥50 series and≥100 matched controls. Require a raw30 Hz timing validation subset before scaling; no new signals beyond existing raw columns. Sparse support remains inconclusive, with no post hoc relaxed prefix rule. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests repeated local expectation against matched identical turns, rather than merely detecting a recurring grammar.": {
    "zh": "将重复形成的局部预期与匹配的相同转向对照，而非仅检测重复语法。",
    "en": "Tests repeated local expectation against matched identical turns, rather than merely detecting a recurring grammar."
  },
  "A repeated musical-style route score with one altered ending and opponent lag.": {
    "zh": "乐谱式重复路线，含一个改变的结尾与对手滞后。",
    "en": "A repeated musical-style route score with one altered ending and opponent lag."
  },
  "Evolutionary ecology: negative frequency dependence": {
    "zh": "演化生态学：负频率依赖",
    "en": "Evolutionary ecology: negative frequency dependence"
  },
  "The same explicit formation has greater forward-ball payoff against opponents for whom that formation is rarer in other observed series, beyond shape and opponent main effects. This is an exposure–payoff association, not proof of unfamiliarity or learning.": {
    "zh": "同一种明确阵型，对那些在其他已观测系列赛中较少遇到该阵型的对手，具有更大的球前进收益，且超出阵型与对手主效应的解释。这是暴露与收益的关联，不证明不熟悉或学习。",
    "en": "The same explicit formation has greater forward-ball payoff against opponents for whom that formation is rarer in other observed series, beyond shape and opponent main effects. This is an exposure–payoff association, not proof of unfamiliarity or learning."
  },
  "Four shape states use own lateral spread≥2500 versus narrower and longitudinal spread≥2500 versus shallower. For each opponent roster o and state s, estimate E_os=frequency that opponents of o used s in other same-season series, excluding the evaluated series and every series involving the evaluated focal roster. Context-standardize to shared ball-half/height/score/time support and shrink with training-only rules. Rarity R_os=−log2(E_os). Outcome: signed ball-y progress over next2 s. Primary coefficient β is uu progress per doubling rarity, with shape fixed effects, opponent and own-roster effects, continuous spread/depth and C.": {
    "zh": "按己方横向跨度≥2500 或更窄、纵向跨度≥2500 或更浅定义四种阵型状态。对每个对手阵容 o 与状态 s，估计 E_os=在同赛季其他系列赛中，o 的对手使用 s 的频率，排除被评估系列赛及所有涉及被评估焦点阵容的系列赛。在共同球半场/高度/比分/时间支持上进行情境标准化，并按仅用训练集确定的规则收缩。稀有度 R_os=−log2(E_os)。结局为未来2 秒带符号的球 y 推进。主系数 β 为稀有度每翻倍的推进 uu，纳入阵型固定效应、对手与己方阵容效应、连续跨度/深度及 C。",
    "en": "Four shape states use own lateral spread≥2500 versus narrower and longitudinal spread≥2500 versus shallower. For each opponent roster o and state s, estimate E_os=frequency that opponents of o used s in other same-season series, excluding the evaluated series and every series involving the evaluated focal roster. Context-standardize to shared ball-half/height/score/time support and shrink with training-only rules. Rarity R_os=−log2(E_os). Outcome: signed ball-y progress over next2 s. Primary coefficient β is uu progress per doubling rarity, with shape fixed effects, opponent and own-roster effects, continuous spread/depth and C."
  },
  "β=0 after geometry, shape and opponent main effects. Identification comes from the supported opponent×shape interaction; a season×region prevalence alone would be absorbed by saturated controls and is not used. Compare the same shape across opponents and different supported shapes within opponents. Cluster bootstrap recomputes all cross-fitted exposure estimates.": {
    "zh": "控制几何、阵型与对手主效应后 β=0。识别来自有支持的对手×阵型交互；仅有赛季×赛区流行率会被饱和控制吸收，故不使用。比较同一阵型在不同对手间，以及同一对手内不同受支持阵型。聚类 bootstrap 重新计算全部交叉拟合暴露估计。",
    "en": "β=0 after geometry, shape and opponent main effects. Identification comes from the supported opponent×shape interaction; a season×region prevalence alone would be absorbed by saturated controls and is not used. Compare the same shape across opponents and different supported shapes within opponents. Cluster bootstrap recomputes all cross-fitted exposure estimates."
  },
  "Whole-series bootstrap β CI and centered p, including exposure-estimation uncertainty. Do not use a season/region permutation that destroys the structure needed for identification. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "以完整系列赛 bootstrap 估计 β 置信区间与中心化 p 值，纳入暴露估计不确定性。不使用会破坏识别所需结构的赛季/赛区置换。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Whole-series bootstrap β CI and centered p, including exposure-estimation uncertainty. Do not use a season/region permutation that destroys the structure needed for identification. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Opponent schedule composition, regional geometry, latent matchup preferences, sparse exposure cells, within-bin shape differences and absent exact chronology. Do not call other-series exposure prior experience; no temporal selection claim. Require full-rank design and report common-support losses.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 对手赛程构成、赛区几何、潜在对阵偏好、稀疏暴露单元、分箱内阵型差异及缺失精确时间顺序。不将其他系列赛暴露称为既往经验；不作时间选择结论。要求设计满秩，并报告共同支持损失。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Opponent schedule composition, regional geometry, latent matchup preferences, sparse exposure cells, within-bin shape differences and absent exact chronology. Do not call other-series exposure prior experience; no temporal selection claim. Require full-rank design and report common-support losses."
  },
  "β≥150 uu per doubling rarity; ≥12 opponent rosters each with≥5 reference series excluding the focal roster and≥3 supported shape states, ≥50 evaluated series, and≥20 reference windows per retained cell. Same sign leaving out each season. Goal/reset trajectory sensitivity must agree. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "β≥150 uu/稀有度翻倍；≥12 个对手阵容，各有≥5 个排除焦点阵容的参考系列赛与≥3 个受支持阵型状态，≥50 个评估系列赛，每个保留单元≥20 个参考窗口。逐一留出赛季后同号。进球/重置轨迹敏感性须一致。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "β≥150 uu per doubling rarity; ≥12 opponent rosters each with≥5 reference series excluding the focal roster and≥3 supported shape states, ≥50 evaluated series, and≥20 reference windows per retained cell. Same sign leaving out each season. Goal/reset trajectory sensitivity must agree. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "Tests a specific frequency–payoff mechanism instead of announcing that seasonal style changed.": {
    "zh": "检验具体的频率与收益机制，而非宣称赛季风格发生了变化。",
    "en": "Tests a specific frequency–payoff mechanism instead of announcing that seasonal style changed."
  },
  "For one shape, payoff versus opponent-specific rarity with uncertainty and support counts.": {
    "zh": "对某一阵型，展示收益与对手特异稀有度的关系，附不确定性及支持数量。",
    "en": "For one shape, payoff versus opponent-specific rarity with uncertainty and support counts."
  },
  "Ecology and evolution: community assembly and convergent organization": {
    "zh": "生态学与演化：群落装配与趋同组织",
    "en": "Ecology and evolution: community assembly and convergent organization"
  },
  "New combinations of player identities display more simultaneous spatial complementarity than independently combining those players' habits measured in other rosters.": {
    "zh": "新的球员身份组合表现出更强的同时空间互补性，超过将这些球员在其他阵容测得的习惯独立组合所得结果。",
    "en": "New combinations of player identities display more simultaneous spatial complementarity than independently combining those players' habits measured in other rosters."
  },
  "Assign each own player a ball-relative planar sector: left/center/right using x−ball_x thresholds±600 uu, crossed with behind/ahead using y−ball_y<0 versus≥0. Complementarity=probability three players occupy three distinct sectors. For each target roster, estimate each member's sector distribution only from other-roster same-season series, matched on ball state, score/time, velocity and boost. Primary effect=observed distinct-sector probability minus synthetic independent-trio probability, averaged equally over target rosters.": {
    "zh": "为每名己方球员分配相对球的平面扇区：以 x−ball_x 阈值±600 uu 区分左/中/右，再以 y−ball_y<0 或≥0 区分后/前。互补性=三名球员占据三个不同扇区的概率。对每个目标阵容，仅用同赛季其他阵容系列赛估计各成员扇区分布，匹配球状态、比分/时间、速度与 boost。主效应=观测不同扇区概率减合成独立三人组概率，目标阵容间等权平均。",
    "en": "Assign each own player a ball-relative planar sector: left/center/right using x−ball_x thresholds±600 uu, crossed with behind/ahead using y−ball_y<0 versus≥0. Complementarity=probability three players occupy three distinct sectors. For each target roster, estimate each member's sector distribution only from other-roster same-season series, matched on ball state, score/time, velocity and boost. Primary effect=observed distinct-sector probability minus synthetic independent-trio probability, averaged equally over target rosters."
  },
  "Independent assortment of individual habits under matched context. Generate pseudo-trios from actual complete other-roster observation blocks for each player; preserve each member's marginal sector distribution and resource context. A same-roster cross-series pseudo-trio null is a secondary diagnostic for shared-ball constraints, not a replacement primary test.": {
    "zh": "匹配情境下个体习惯独立组合。用各球员真实完整的其他阵容观测块生成伪三人组；保留各成员边际扇区分布及资源情境。同阵容跨系列赛伪三人组零模型是共同球约束的次要诊断，不替代主检验。",
    "en": "Independent assortment of individual habits under matched context. Generate pseudo-trios from actual complete other-roster observation blocks for each player; preserve each member's marginal sector distribution and resource context. A same-roster cross-series pseudo-trio null is a secondary diagnostic for shared-ball constraints, not a replacement primary test."
  },
  "Series bootstrap and conditional pseudo-trio randomization; whenever target/reference rosters share players, require a crossed shared-player/roster and series multiway bootstrap for primary uncertainty. Use the larger of the series-bootstrap and dependency-aware p-values as this idea's single BH input, and the hull of their confidence intervals. The player-disjoint target-roster sensitivity is additional support, never a substitute for valid primary uncertainty. Insufficient independent cluster support makes the result inconclusive. The bootstrap must include both target and reference series and re-estimate marginal habits. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "采用系列赛 bootstrap 与条件伪三人组随机化；目标/参考阵容共享球员时，主不确定性必须采用共享球员/阵容与系列赛交叉的多向 bootstrap。取系列赛 bootstrap 与考虑依赖的 p 值中较大者，作为该想法唯一的 BH 输入；置信区间取两者包络。球员不重叠目标阵容的敏感性仅作附加支持，不替代有效的主不确定性。独立聚类支持不足则结果不确定。bootstrap 必须包含目标与参考系列赛，并重新估计边际习惯。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Series bootstrap and conditional pseudo-trio randomization; whenever target/reference rosters share players, require a crossed shared-player/roster and series multiway bootstrap for primary uncertainty. Use the larger of the series-bootstrap and dependency-aware p-values as this idea's single BH input, and the hull of their confidence intervals. The player-disjoint target-roster sensitivity is additional support, never a substitute for valid primary uncertainty. Insufficient independent cluster support makes the result inconclusive. The bootstrap must include both target and reference series and re-estimate marginal habits. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Selection into rosters, player-ID errors, crossover scarcity, common ball constraints, strength and repeated players across supposed independent assemblies. Without verified chronology do not call this causal adaptation after transfers or demonstrated evolutionary convergence. Do not condition the pseudo-trio null on each player's actual sector or exact ball-relative xy at the evaluated time; those define the outcome. Match ball context, speed/boost and coarse spatial opportunity with support.": {
    "zh": "score_diff、剩余时间（非线性）、加时及加时时长、赛季、仅由明确 group_path 标签恢复的赛区、赛事/阶段、roster_id 与 opponent_roster_id、留系列赛外的对手实力估计；窗口前球的 xyz/vxyz、球员几何/速度/boost，以及距活球片段起点的时间。采用共同支持与系列赛等权。 阵容选择、球员 ID 错误、跨阵容样本稀缺、共同球约束、实力，以及所谓独立装配间重复出现的球员。无经验证时间顺序时，不称为转会后的因果适应或已证实的演化趋同。不对伪三人组零模型条件化各球员评估时的实际扇区或精确相对球 xy，因为它们定义结局。匹配球情境、速度/boost 及有支持的粗空间机会。",
    "en": "score_diff, remaining (nonlinear), overtime and OT duration, season, region recovered only from explicit group_path labels, event/stage, roster_id and opponent_roster_id, leave-series-out opponent-strength estimate; pre-window ball xyz/vxyz, player geometry/speed/boost and time since live-segment start. Use common support and equal-series weighting. Selection into rosters, player-ID errors, crossover scarcity, common ball constraints, strength and repeated players across supposed independent assemblies. Without verified chronology do not call this causal adaptation after transfers or demonstrated evolutionary convergence. Do not condition the pseudo-trio null on each player's actual sector or exact ball-relative xy at the evaluated time; those define the outcome. Match ball context, speed/boost and coarse spatial opportunity with support."
  },
  "Excess complementarity≥10 percentage points; ≥10 target rosters whose three members each have≥3 other-roster reference series and≥100 matched samples, ≥50 total series, positive in≥70% of target rosters, plus ≥5 player-disjoint target rosters with same sign and ≥20 distinct players overall; the effect and CI/p gate must also pass required shared-player/roster-aware inference. If crossover support fails, inconclusive, not rejected. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results.": {
    "zh": "超额互补性≥10 个百分点；≥10 个目标阵容，其三名成员各有≥3 个其他阵容参考系列赛与≥100 个匹配样本，总计 ≥50 个系列赛，≥70% 目标阵容中为正，另有≥5 个球员不重叠目标阵容同号，总体 ≥20 名不同球员；效应与置信区间/p 值门槛还须通过必需的共享球员/阵容依赖推断。跨阵容支持不足则为不确定，而非拒绝。 另须满足共同门槛 G：约 1,500 场 2026 年前、属于完整已知系列赛的比赛，≥50 个合格系列赛，≥2 个赛季，每个对比侧 ≥20 个系列赛，p≤.01，BH q≤.10，95% 系列赛置信区间在假设方向上排除零假设值，且两个预先指定的系列赛半区间方向一致。这些是拟定门槛，不是结果。",
    "en": "Excess complementarity≥10 percentage points; ≥10 target rosters whose three members each have≥3 other-roster reference series and≥100 matched samples, ≥50 total series, positive in≥70% of target rosters, plus ≥5 player-disjoint target rosters with same sign and ≥20 distinct players overall; the effect and CI/p gate must also pass required shared-player/roster-aware inference. If crossover support fails, inconclusive, not rejected. Plus common gate G: approximately 1,500 pre-2026 games in complete known series, ≥50 eligible series, ≥2 seasons, each comparison side ≥20 series, p≤.01, BH q≤.10, 95% series CI excluding the null in the proposed direction, and same direction in both prespecified series halves. These are proposed gates, not results."
  },
  "A compositional assembly test beyond generic stable style or season drift; explicitly high-interest, low-feasibility.": {
    "zh": "组合装配检验，超出一般稳定风格或赛季漂移；明确为高趣味、低可行性。",
    "en": "A compositional assembly test beyond generic stable style or season drift; explicitly high-interest, low-feasibility."
  },
  "Observed sector occupancy beside independently assembled synthetic trios.": {
    "zh": "观测扇区占用与独立装配的合成三人组并列展示。",
    "en": "Observed sector occupancy beside independently assembled synthetic trios."
  },
  "借鉴：Music: counterpoint and compensatory motion。假设：After one player's lateral acceleration, the other two have excess opposite lateral acceleration beyond their common reaction to the ball. The object is a signed compensatory response, not generic synchrony.": {
    "zh": "借鉴：音乐：对位法与补偿运动。假设：一名球员横向加速后，另外两人出现超出共同球反应的额外反向横向加速。研究对象是带方向的补偿响应，而非一般同步性。",
    "en": "Inspiration: Music: counterpoint and compensatory motion. Hypothesis: After one player's lateral acceleration, the other two have excess opposite lateral acceleration beyond their common reaction to the ball. The object is a signed compensatory response, not generic synchrony."
  },
  "指标：At anchors ≥6 s apart, freeze i as the unambiguous ball-nearest teammate. Let u=vxi(t+.2)-vxi(t), and v=Σj≠i[vxj(t+.7)-vxj(t+.2)]. Residualize u and v against the preceding 1 s of ball trajectory and all starting player positions/velocities/boost. Primary statistic Δg is observed compensation gain g=−slope(v~u) minus the gain from the matched-block null. A gain of .15 means an extra 150 uu/s of summed opposite movement per 1,000 uu/s innovation. No claim that i causes the response. 零模型：No extra compensatory coupling conditional on the shared stimulus. Re-pair complete receiver-pair trajectory blocks with source blocks from other series of the same roster where possible, tightly matching initial geometry, own-half/attack-half, ball history, score/time and strength. Preserve receiver-pair covariance and within-block autocorrelation. No independent frame shuffle; insufficient exchangeable blocks means no permutation claim. 检验：Estimate paired observed-minus-null gains with series-bootstrap CI; obtain the primary p from 2,000 matched-block randomizations with whole series as outer resampling units. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：在间隔 ≥6 秒的锚点，将 i 固定为明确离球最近的队友。令 u=vxi(t+.2)-vxi(t)，v=Σj≠i[vxj(t+.7)-vxj(t+.2)]。对之前 1 秒的球轨迹及所有球员初始位置/速度/boost 回归，取 u 与 v 的残差。主统计量 Δg 为观测补偿增益 g=−slope(v~u) 减去匹配块零模型的增益。.15 的增益表示每 1,000 uu/秒创新对应额外 150 uu/秒的合计反向运动。不声称 i 导致该响应。 零模型：给定共同刺激后不存在额外补偿耦合。尽可能将完整的接收方双人轨迹块与同阵容其他系列赛的源块重新配对，严格匹配初始几何、己方半场/进攻半场、球历史、比分/时间及实力。保留接收方双人协方差与块内自相关。不独立打乱帧；可交换块不足时不作置换推断。 检验：估计配对的观测减零模型增益及系列赛 bootstrap 置信区间；以完整系列赛为外层重采样单位，通过 2,000 次匹配块随机化获得主 p 值。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: At anchors ≥6 s apart, freeze i as the unambiguous ball-nearest teammate. Let u=vxi(t+.2)-vxi(t), and v=Σj≠i[vxj(t+.7)-vxj(t+.2)]. Residualize u and v against the preceding 1 s of ball trajectory and all starting player positions/velocities/boost. Primary statistic Δg is observed compensation gain g=−slope(v~u) minus the gain from the matched-block null. A gain of .15 means an extra 150 uu/s of summed opposite movement per 1,000 uu/s innovation. No claim that i causes the response. Null model: No extra compensatory coupling conditional on the shared stimulus. Re-pair complete receiver-pair trajectory blocks with source blocks from other series of the same roster where possible, tightly matching initial geometry, own-half/attack-half, ball history, score/time and strength. Preserve receiver-pair covariance and within-block autocorrelation. No independent frame shuffle; insufficient exchangeable blocks means no permutation claim. Test: Estimate paired observed-minus-null gains with series-bootstrap CI; obtain the primary p from 2,000 matched-block randomizations with whole series as outer resampling units. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Physics: hysteresis and memory。假设：At similar present ball states, a ball that arrived from the attacking direction leaves a narrower team than one that has just advanced from defense; team shape retains a measurable history.": {
    "zh": "借鉴：物理学：磁滞与记忆。假设：在相似的当前球状态下，相比刚从防守方向推进的球，从进攻方向回来的球对应更窄的队形；队形保留可测量的历史。",
    "en": "Inspiration: Physics: hysteresis and memory. Hypothesis: At similar present ball states, a ball that arrived from the attacking direction leaves a narrower team than one that has just advanced from defense; team shape retains a measurable history."
  },
  "指标：At ≥6 s anchors require |ball vy|<300 uu/s. Label previous 1.5 s ball-y displacement >600 uu as forward history and <−600 uu as backward history. Response is mean own-team lateral width max(xi)−min(xi) over [t,t+.5]. Primary effect is forward-minus-backward adjusted width in uu. Match present ball xyz/vxyz, team centroid, current mean velocity and boost; current width is the outcome and is deliberately not adjusted away. 零模型：Current ball state, translation and resources suffice to explain width: conditional history contrast=0. First use within-series matched turning states; otherwise match same-roster/season/region states with overlap. A separate baseline including width 1.5 s earlier tests whether the contrast is simply carried-over starting width. 检验：Series-bootstrap standardized matched width contrast and null-centered p; report overlap/balance before interpreting the contrast. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：间隔 ≥6 秒的锚点要求 |ball vy|<300 uu/秒。前 1.5 秒球的 y 位移 >600 uu 标为前进历史，<−600 uu 标为后退历史。响应为 [t,t+.5] 内己方横向宽度 max(xi)−min(xi) 的均值。主效应为调整后的前进减后退宽度，单位 uu。匹配当前球 xyz/vxyz、队伍质心、当前平均速度与 boost；当前宽度是结局，特意不将其调整掉。 零模型：当前球状态、平移与资源足以解释宽度：条件历史对比=0。优先使用系列赛内匹配的转向状态，否则匹配有重叠的同阵容/赛季/赛区状态。另设包含 1.5 秒前宽度的基线，检验对比是否仅来自起始宽度的延续。 检验：通过系列赛 bootstrap 估计标准化匹配宽度对比及以零假设为中心的 p 值；先报告重叠与平衡，再解释对比。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: At ≥6 s anchors require |ball vy|<300 uu/s. Label previous 1.5 s ball-y displacement >600 uu as forward history and <−600 uu as backward history. Response is mean own-team lateral width max(xi)−min(xi) over [t,t+.5]. Primary effect is forward-minus-backward adjusted width in uu. Match present ball xyz/vxyz, team centroid, current mean velocity and boost; current width is the outcome and is deliberately not adjusted away. Null model: Current ball state, translation and resources suffice to explain width: conditional history contrast=0. First use within-series matched turning states; otherwise match same-roster/season/region states with overlap. A separate baseline including width 1.5 s earlier tests whether the contrast is simply carried-over starting width. Test: Series-bootstrap standardized matched width contrast and null-centered p; report overlap/balance before interpreting the contrast. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Reliability engineering: single-point dependence。假设：Equal total geometric coverage can hide unequal reliance on one defender; the more brittle formation is associated with more near-term concessions.": {
    "zh": "借鉴：可靠性工程：单点依赖。假设：相同的总几何覆盖可能掩盖对单个防守者不同程度的依赖；更脆弱的阵型与更多近期失球相关。",
    "en": "Inspiration: Reliability engineering: single-point dependence. Hypothesis: Equal total geometric coverage can hide unequal reliance on one defender; the more brittle formation is associated with more near-term concessions."
  },
  "指标：On the fixed own-half xy grid, cell ownership means nearest own player is closer than nearest opponent. Let A be the owned fraction, and A−i the fraction after virtually omitting own player i. For A≥.10 define B=max_i(A−A−i)/A. At ≥6 s prospective anchors, primary effect is the adjusted concession-risk difference within 3 s for B's upper versus lower training-defined tertile, controlling A; middle tertile is excluded from this contrast. Also report which player maximizes loss, without calling that player at fault. 零模型：At matched initial coverage A, ball threat, resources and context, high/low B have equal future concession probability. Match snapshots on A, nearest-defender distance, ball position/heading/speed/height and number goal-side. Virtual deletion is only a diagnostic of geometry, not a simulated demolition treatment. 检验：Fit a series-cross-fitted binary risk model and standardize the high-minus-low probability difference over shared support; series-bootstrap CI/p. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：在固定的己方半场 xy 网格上，最近己方球员比最近对手更近即视为己方占有该格。令 A 为占有比例，A−i 为虚拟移除己方球员 i 后的比例。对 A≥.10 定义 B=max_i(A−A−i)/A。在间隔 ≥6 秒的前瞻锚点，主效应为控制 A 后，按训练集定义的 B 最高与最低三分位组在 3 秒内的调整后失球风险差；中间三分位组不纳入此对比。同时报告移除哪名球员造成最大损失，但不归责于该球员。 零模型：在初始覆盖 A、球威胁、资源与情境匹配后，高/低 B 的未来失球概率相等。按 A、最近防守者距离、球位置/朝向/速度/高度及位于球门侧的人数匹配快照。虚拟删除仅诊断几何，不是模拟击毁处理。 检验：拟合按系列赛交叉拟合的二元风险模型，在共同支持上标准化高减低概率差；用系列赛 bootstrap 估计置信区间/p 值。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: On the fixed own-half xy grid, cell ownership means nearest own player is closer than nearest opponent. Let A be the owned fraction, and A−i the fraction after virtually omitting own player i. For A≥.10 define B=max_i(A−A−i)/A. At ≥6 s prospective anchors, primary effect is the adjusted concession-risk difference within 3 s for B's upper versus lower training-defined tertile, controlling A; middle tertile is excluded from this contrast. Also report which player maximizes loss, without calling that player at fault. Null model: At matched initial coverage A, ball threat, resources and context, high/low B have equal future concession probability. Match snapshots on A, nearest-defender distance, ball position/heading/speed/height and number goal-side. Virtual deletion is only a diagnostic of geometry, not a simulated demolition treatment. Test: Fit a series-cross-fitted binary risk model and standardize the high-minus-low probability difference over shared support; series-bootstrap CI/p. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Linguistics: audience design; information theory。假设：A focal player's next movement is better predicted by teammate history than equally sized opponent history after controlling the complete present state and ball history.": {
    "zh": "借鉴：语言学：受众设计；信息论。假设：控制完整当前状态与球历史后，队友历史比等量对手历史更能预测焦点球员的下一步运动。",
    "en": "Inspiration: Linguistics: audience design; information theory. Hypothesis: A focal player's next movement is better predicted by teammate history than equally sized opponent history after controlling the complete present state and ball history."
  },
  "指标：Target: focal player's next .5 s lateral displacement classified L/S/R by ±150 uu. Baseline has all six players' current xyz/vxyz/boost and target/ball past 1 s. Add either both teammates' past trajectories or two opponents' past trajectories selected by a fixed nearest-to-target rule. Use the same regularized multinomial model, feature dimension, training count and tuning budget. Primary held-out effect is (log-loss_opponent−log-loss_teammate)/ln(2), bits/action, averaged first within series. 零模型：No teammate-specific predictive increment. Reassign added 1 s trajectory blocks among geometry/context-matched training windows from different series, retaining full blocks. Match distance and speed distributions of teammate and opponent inputs; report no-overlap exclusions. Baseline and both augmented models are trained only on training series. 检验：Paired series-bootstrap of out-of-fold loss advantage and centered p; matched history-block shuffles are the falsification control. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：目标：按 ±150 uu 将焦点球员未来 .5 秒的横向位移分为 L/S/R。基线包含六名球员当前 xyz/vxyz/boost，以及目标球员/球过去 1 秒的信息。加入两名队友的历史轨迹，或按固定的离目标最近规则选出的两名对手历史轨迹。使用相同正则化多项模型、特征维度、训练量与调参预算。留出集主效应为 (log-loss_opponent−log-loss_teammate)/ln(2)，单位比特/动作，先在系列赛内平均。 零模型：不存在队友特异的预测增量。在不同系列赛、几何/情境匹配的训练窗口之间重新分配新增的 1 秒轨迹块，保留完整块。匹配队友与对手输入的距离及速度分布；报告无重叠排除。基线及两个增强模型仅在训练系列赛上训练。 检验：对折外损失优势作配对系列赛 bootstrap，并计算中心化 p 值；匹配历史块打乱作为证伪对照。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Target: focal player's next .5 s lateral displacement classified L/S/R by ±150 uu. Baseline has all six players' current xyz/vxyz/boost and target/ball past 1 s. Add either both teammates' past trajectories or two opponents' past trajectories selected by a fixed nearest-to-target rule. Use the same regularized multinomial model, feature dimension, training count and tuning budget. Primary held-out effect is (log-loss_opponent−log-loss_teammate)/ln(2), bits/action, averaged first within series. Null model: No teammate-specific predictive increment. Reassign added 1 s trajectory blocks among geometry/context-matched training windows from different series, retaining full blocks. Match distance and speed distributions of teammate and opponent inputs; report no-overlap exclusions. Baseline and both augmented models are trained only on training series. Test: Paired series-bootstrap of out-of-fold loss advantage and centered p; matched history-block shuffles are the falsification control. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Game theory: volunteer's dilemma and anti-coordination。假设：When two teammates have similar opportunity to approach, exactly one approaches more often than context-conditioned independent choices predict.": {
    "zh": "借鉴：博弈论：志愿者困境与反协调。假设：当两名队友具备相似的上前机会时，恰好一人上前的频率高于情境条件下独立选择的预测。",
    "en": "Inspiration: Game theory: volunteer's dilemma and anti-coordination. Hypothesis: When two teammates have similar opportunity to approach, exactly one approaches more often than context-conditioned independent choices predict."
  },
  "指标：At onset choose the two closest teammates with both ball distances≤1,500 uu, distance gap≤200 uu, ball z<400 uu and an opponent within 2,000 uu. Over the next .5 s, approach=ball-distance reduction≥150 uu and positive mean closing. Cross-fit individual probabilities p1,p2 from initial state and ball history. Primary excess is P(exactly one)−mean[p1(1−p2)+p2(1−p1)], in percentage points. 零模型：Conditional independence of the two approach responses. Construct matched pseudo-pairs using whole .5 s response blocks from different series, preserving each player's marginal rates, initial opportunity and boost. Fit/calibrate p1,p2 only on inner training-series folds and evaluate untouched outer series; a misspecified independent baseline cannot establish coordination. 检验：Bootstrap complete series and recompute marginal models; primary p from conditional pseudo-pair randomization. Keep 00/11 frequencies descriptive unless added to the BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：在起点选择最近的两名队友，要求两者到球距离≤1,500 uu、距离差≤200 uu、球 z<400 uu，且 2,000 uu 内有对手。未来 .5 秒内，到球距离减少≥150 uu 且平均接近速度为正即为上前。根据初始状态与球历史交叉拟合个体概率 p1,p2。主超额量为 P(恰好一人)−mean[p1(1−p2)+p2(1−p1)]，单位百分点。 零模型：两名球员的上前响应条件独立。使用不同系列赛的完整 .5 秒响应块构造匹配伪配对，保留各球员边际频率、初始机会与 boost。仅在内层训练系列赛折上拟合/校准 p1,p2，在未接触的外层系列赛上评估；设定错误的独立基线不能证明协调。 检验：对完整系列赛作 bootstrap 并重算边际模型；主 p 值来自条件伪配对随机化。00/11 频率保持描述性，除非纳入 BH 检验族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: At onset choose the two closest teammates with both ball distances≤1,500 uu, distance gap≤200 uu, ball z<400 uu and an opponent within 2,000 uu. Over the next .5 s, approach=ball-distance reduction≥150 uu and positive mean closing. Cross-fit individual probabilities p1,p2 from initial state and ball history. Primary excess is P(exactly one)−mean[p1(1−p2)+p2(1−p1)], in percentage points. Null model: Conditional independence of the two approach responses. Construct matched pseudo-pairs using whole .5 s response blocks from different series, preserving each player's marginal rates, initial opportunity and boost. Fit/calibrate p1,p2 only on inner training-series folds and evaluate untouched outer series; a misspecified independent baseline cannot establish coordination. Test: Bootstrap complete series and recompute marginal models; primary p from conditional pseudo-pair randomization. Keep 00/11 frequencies descriptive unless added to the BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Physics: chirality and circulation。假设：Some exact rosters have a reproducible signed circulation preference beyond ball-induced movement and uneven left/right field use.": {
    "zh": "借鉴：物理学：手性与环流。假设：某些固定阵容具有可复现的有向环流偏好，超出球诱导运动及左右场地使用不均的解释。",
    "en": "Inspiration: Physics: chirality and circulation. Hypothesis: Some exact rosters have a reproducible signed circulation preference beyond ball-induced movement and uneven left/right field use."
  },
  "指标：Let ri=own xy position−own centroid and wi=own xy velocity−own mean velocity. L=Σ(rix*wiy−riy*wix)/Σ||ri||², s⁻¹. Exclude RMS radius<300 uu. Residualize L against ball xyz/vxyz, ball circulation around centroid, width/depth and C. Deterministically split whole series into two balanced halves. Primary statistic: Spearman correlation across roster-average residual L in the two halves. 零模型：No stable roster handedness. Permute whole roster-series summary labels in one half within season/region/strength strata, preserving each roster's series count and keeping paired opponents together during outer series resampling. Audit exchangeability; if roster labels cannot be permuted credibly use only descriptive intervals, not a passing p. 检验：2,000 restricted whole-series label permutations for correlation; series-bootstrap CI with adequate representation in both halves. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：令 ri=己方 xy 位置−己方质心，wi=己方 xy 速度−己方平均速度。L=Σ(rix*wiy−riy*wix)/Σ||ri||²，单位秒⁻¹。排除均方根半径<300 uu。对球 xyz/vxyz、球绕质心的环流、宽度/深度及 C 回归，取 L 残差。确定性地将完整系列赛划为两个平衡半区间。主统计量为各阵容平均残差 L 在两个半区间间的 Spearman 相关。 零模型：不存在稳定的阵容惯用方向。在赛季/赛区/实力分层内置换一个半区间的完整阵容系列赛汇总标签，保留各阵容系列赛数量，并在外层系列赛重采样时将配对对手共同保留。审计可交换性；若无法可信地置换阵容标签，仅报告描述性区间，不报告通过门槛的 p 值。 检验：以 2,000 次受限完整系列赛标签置换检验相关；在两个半区间均有充分代表时计算系列赛 bootstrap 置信区间。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Let ri=own xy position−own centroid and wi=own xy velocity−own mean velocity. L=Σ(rix*wiy−riy*wix)/Σ||ri||², s⁻¹. Exclude RMS radius<300 uu. Residualize L against ball xyz/vxyz, ball circulation around centroid, width/depth and C. Deterministically split whole series into two balanced halves. Primary statistic: Spearman correlation across roster-average residual L in the two halves. Null model: No stable roster handedness. Permute whole roster-series summary labels in one half within season/region/strength strata, preserving each roster's series count and keeping paired opponents together during outer series resampling. Audit exchangeability; if roster labels cannot be permuted credibly use only descriptive intervals, not a passing p. Test: 2,000 restricted whole-series label permutations for correlation; series-bootstrap CI with adequate representation in both halves. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Pragmatics and signaling games: geometric ambiguity。假设：Two separated players with similarly short approach-time proxies are associated with more opponent slowing than a clear primary approacher, beyond ordinary congestion.": {
    "zh": "借鉴：语用学与信号博弈：几何模糊性。假设：两名相互分开的球员具有相近且较短的接近时间代理值时，相比明确的主要接近者，对手更常减速，且超出普通拥挤的解释。",
    "en": "Inspiration: Pragmatics and signaling games: geometric ambiguity. Hypothesis: Two separated players with similarly short approach-time proxies are associated with more opponent slowing than a clear primary approacher, beyond ordinary congestion."
  },
  "指标：For each player c_i=vi_xy·(ball_xy−pi_xy)/d_i and τ_i=d_i/c_i, with c_i>300 uu/s and d_i∈[500,2500] uu. τ is a straight-line proxy, not interception time. Compare two candidates with |τ1−τ2|≤.15 s versus ≥.5 s, crossed with lateral separation≥1,200 versus≤600 uu. Low ball z<300 and |vz|<300 primary. Response: initially ball-approaching nearest opponent (c≥500, d>800) reduces its c by≥300 uu/s over next .5 s. Primary effect is ambiguity-by-separation interaction in probability: (ambiguous−clear)_wide−(ambiguous−clear)_narrow. 零模型：No ambiguity interaction at comparable urgency. Match minimum τ, broad mean-distance/overall-speed strata, defender geometry/boost and ball history within each separation band. Do not simultaneously match both candidate distances and summed c, or every candidate coordinate/velocity: these can determine the τ gap and eliminate ambiguity overlap. Keep the separation contrast identifiable using within-band opportunity controls. 检验：Series-bootstrap standardized probability difference-in-differences and centered p. Four simple cell comparisons are explanatory, or enter the expanded BH family if tested. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：对每名球员定义 c_i=vi_xy·(ball_xy−pi_xy)/d_i，τ_i=d_i/c_i，要求 c_i>300 uu/秒、d_i∈[500,2500] uu。τ 是直线代理值，不是拦截时间。比较 |τ1−τ2|≤.15 秒与 ≥.5 秒的两名候选者，并与横向间距≥1,200 或 ≤600 uu 交叉分组。主分析要求低球 z<300 且 |vz|<300。响应为：初始正在接近球的最近对手（c≥500，d>800）在未来 .5 秒内将 c 降低≥300 uu/秒。主效应为概率上的模糊性与间距交互：(模糊−明确)_宽−(模糊−明确)_窄。 零模型：在相近紧迫程度下不存在模糊性交互。在各间距组内匹配最小 τ、粗略平均距离/总体速度分层、防守者几何/boost 与球历史。不同时匹配两名候选者距离与 c 之和，也不匹配每个候选者坐标/速度：这些可能决定 τ 差并消除模糊性重叠。通过组内机会控制保持间距对比可识别。 检验：以系列赛 bootstrap 估计标准化概率双重差分及中心化 p 值。四个简单单元对比用于解释；若作检验则纳入扩展 BH 族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: For each player c_i=vi_xy·(ball_xy−pi_xy)/d_i and τ_i=d_i/c_i, with c_i>300 uu/s and d_i∈[500,2500] uu. τ is a straight-line proxy, not interception time. Compare two candidates with |τ1−τ2|≤.15 s versus ≥.5 s, crossed with lateral separation≥1,200 versus≤600 uu. Low ball z<300 and |vz|<300 primary. Response: initially ball-approaching nearest opponent (c≥500, d>800) reduces its c by≥300 uu/s over next .5 s. Primary effect is ambiguity-by-separation interaction in probability: (ambiguous−clear)_wide−(ambiguous−clear)_narrow. Null model: No ambiguity interaction at comparable urgency. Match minimum τ, broad mean-distance/overall-speed strata, defender geometry/boost and ball history within each separation band. Do not simultaneously match both candidate distances and summed c, or every candidate coordinate/velocity: these can determine the τ gap and eliminate ambiguity overlap. Keep the separation contrast identifiable using within-band opportunity controls. Test: Series-bootstrap standardized probability difference-in-differences and centered p. Four simple cell comparisons are explanatory, or enter the expanded BH family if tested. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Ecology and finance: resource insurance and joint tail risk。假设：Pairs of teammates experience fewer simultaneous low-boost states than expected from calibrated individual resource-risk models sharing the same observed starting state.": {
    "zh": "借鉴：生态学与金融：资源保险与联合尾部风险。假设：相比共享同一观测初始状态的、经校准的个体资源风险模型预测，队友配对同时处于低 boost 的情况更少。",
    "en": "Inspiration: Ecology and finance: resource insurance and joint tail risk. Hypothesis: Pairs of teammates experience fewer simultaneous low-boost states than expected from calibrated individual resource-risk models sharing the same observed starting state."
  },
  "指标：At ≥6 s anchors with known normalized boost u, let Yi=1 if player i has u<.20 at t+1 s. Cross-fit p_i=P(Yi=1|all six initial xyz/vxyz/u, past 1 s ball/boost history,C). All pair sums run only over focal teammates i,j∈{0,1,2}; all six players are in the conditioning set. Primary R_pair=series-weighted mean[Σi<j YiYj]/series-weighted mean[Σi<j p_i*p_j], observed pairwise shortage divided by conditionally independent expected shortage. Test log(R_pair). Also report the absolute difference in pair-shortage probability (divide both sums by 3). The three pairs are not independent samples; future team-total boost is not a control. 零模型：Conditional independence of future shortages given shared starting resources, geometry and past ball forcing. Null expected pair count is Σp_i*p_j evaluated at the real observed starting states. No exact permutation can preserve all continuous states and common future shocks; use the model-based null with audited held-out marginal calibration and series-bootstrap uncertainty. Never condition on realized future total boost, which can manufacture anticorrelation. 检验：Whole-series bootstrap of log R_pair, refitting cross-fitted marginal models, and centered null test log R_pair=0. No simulated Bernoulli draw is treated as an independent observed sample. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：在间隔 ≥6 秒且归一化 boost u 已知的锚点，若球员 i 在 t+1 秒时 u<.20，则 Yi=1。交叉拟合 p_i=P(Yi=1|六名球员初始 xyz/vxyz/u、过去 1 秒球/boost 历史、C)。所有配对求和仅覆盖焦点队友 i,j∈{0,1,2}；条件集中包含全部六人。主指标 R_pair=系列赛加权 mean[Σi<j YiYj]/系列赛加权 mean[Σi<j p_i*p_j]，即观测双人短缺除以条件独立预期短缺。检验 log(R_pair)。另报告双人短缺概率绝对差（两求和均除以 3）。三个配对不是独立样本；未来全队总 boost 不作控制变量。 零模型：给定共同起始资源、几何与过去球驱动后，未来短缺条件独立。零模型预期配对数为在真实观测初始状态上评估的 Σp_i*p_j。没有精确置换能保留所有连续状态与共同未来冲击；采用模型零假设，审计留出集边际校准，并以系列赛 bootstrap 估计不确定性。不得条件化实际未来总 boost，这会人为制造负相关。 检验：对 log R_pair 作完整系列赛 bootstrap，重新拟合交叉拟合的边际模型，并进行以 log R_pair=0 为中心的零假设检验。不把模拟 Bernoulli 抽样当作独立观测样本。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: At ≥6 s anchors with known normalized boost u, let Yi=1 if player i has u<.20 at t+1 s. Cross-fit p_i=P(Yi=1|all six initial xyz/vxyz/u, past 1 s ball/boost history,C). All pair sums run only over focal teammates i,j∈{0,1,2}; all six players are in the conditioning set. Primary R_pair=series-weighted mean[Σi<j YiYj]/series-weighted mean[Σi<j p_i*p_j], observed pairwise shortage divided by conditionally independent expected shortage. Test log(R_pair). Also report the absolute difference in pair-shortage probability (divide both sums by 3). The three pairs are not independent samples; future team-total boost is not a control. Null model: Conditional independence of future shortages given shared starting resources, geometry and past ball forcing. Null expected pair count is Σp_i*p_j evaluated at the real observed starting states. No exact permutation can preserve all continuous states and common future shocks; use the model-based null with audited held-out marginal calibration and series-bootstrap uncertainty. Never condition on realized future total boost, which can manufacture anticorrelation. Test: Whole-series bootstrap of log R_pair, refitting cross-fitted marginal models, and centered null test log R_pair=0. No simulated Bernoulli draw is treated as an independent observed sample. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Ecology: response diversity and resilience。假设：Different immediate longitudinal reactions to the same adverse ball reversal are associated with less subsequent backward ball travel, even at the same mean team response.": {
    "zh": "借鉴：生态学：响应多样性与韧性。假设：对同一次不利球反转的不同即时纵向反应，与后续更少的球后退相关，即使全队平均响应相同。",
    "en": "Inspiration: Ecology: response diversity and resilience. Hypothesis: Different immediate longitudinal reactions to the same adverse ball reversal are associated with less subsequent backward ball travel, even at the same mean team response."
  },
  "指标：Detect ball vy changing from >500 to <−500 uu/s, both sustained≥.3 s, with ≥3 s between events. Over [0,.4] s compute SD of the three players' Δvy and residualize it against mean Δvy and initial velocities using other series. Upper/lower training-tertile residual diversity is exposure. Outcome: maximum backward ball excursion over [.5,2.5] s relative to ball y at .5. Primary effect is low-diversity minus high-diversity adjusted excursion, uu; exposure and outcome windows do not overlap. 零模型：No diversity association beyond common response magnitude and initial state. Match reversal magnitude, all starting geometry, average response and resources. Re-pair diversity/outcome event blocks across matched series only; the primary adjusted comparison is observational. 检验：Series-bootstrap standardized excursion reduction and centered p; matched series-block label permutation as a support check. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：检测球 vy 从 >500 变为 <−500 uu/秒，两侧均持续≥.3 秒，事件间隔 ≥3 秒。在 [0,.4] 秒内计算三名球员 Δvy 的标准差，并使用其他系列赛，对平均 Δvy 与初始速度回归取残差。暴露为按训练集三分位定义的残差多样性最高/最低组。结局为 [.5,2.5] 秒内相对 .5 秒时球 y 坐标的最大后退距离。主效应为低多样性减高多样性的调整后回撤，单位 uu；暴露与结局窗口不重叠。 零模型：除共同响应幅度与初始状态外，不存在多样性关联。匹配反转幅度、全部初始几何、平均响应与资源。仅在匹配系列赛间重新配对多样性/结局事件块；主调整对比是观测性的。 检验：以系列赛 bootstrap 估计标准化回撤减少量及中心化 p 值；以匹配系列赛块标签置换作支持性检查。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Detect ball vy changing from >500 to <−500 uu/s, both sustained≥.3 s, with ≥3 s between events. Over [0,.4] s compute SD of the three players' Δvy and residualize it against mean Δvy and initial velocities using other series. Upper/lower training-tertile residual diversity is exposure. Outcome: maximum backward ball excursion over [.5,2.5] s relative to ball y at .5. Primary effect is low-diversity minus high-diversity adjusted excursion, uu; exposure and outcome windows do not overlap. Null model: No diversity association beyond common response magnitude and initial state. Match reversal magnitude, all starting geometry, average response and resources. Re-pair diversity/outcome event blocks across matched series only; the primary adjusted comparison is observational. Test: Series-bootstrap standardized excursion reduction and centered p; matched series-block label permutation as a support check. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Ecology: pursuit externalities and decoy geometry。假设：An off-ball player followed away from the ball is associated with a widening geometric lane for a teammate. 'Decoy' is only a descriptive metaphor.": {
    "zh": "借鉴：生态学：追逐外部性与诱饵几何。假设：无球球员被跟随并远离球，与队友几何通道拓宽相关。“诱饵”仅是描述性比喻。",
    "en": "Inspiration: Ecology: pursuit externalities and decoy geometry. Hypothesis: An off-ball player followed away from the ball is associated with a widening geometric lane for a teammate. 'Decoy' is only a descriptive metaphor."
  },
  "指标：Candidate: own player initially >700 uu from ball, increasing that distance≥300 uu over .5 s. Pursuit=one initially nearby opponent (within1,500 uu) reduces distance to that player≥200 uu while increasing own ball distance≥200 uu. At onset freeze the other teammate nearest the ball. Let corridor clearance be minimum opponent-to-line-segment distance for the segment from that teammate to the current ball, clipped [0,2000] uu. Primary effect: pursuit versus matched no-pursuit difference in clearance change from t to t+1 s. 零模型：No extra lane opening associated with pursuit once initial state and prior opening trend are matched. Match onset corridor clearance and its preceding .5 s change, full ball/player state, walls and C; compare same-roster event blocks. A negative-control preceding interval must not already show the full effect. 检验：Series-bootstrap adjusted clearance-change difference and centered p; restricted pursuit-label permutation only when matched series blocks are exchangeable. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：候选者：己方球员起初距球 >700 uu，并在 .5 秒内将距离增加≥300 uu。追随定义为：一名起初较近（1,500 uu 内）的对手，到该球员距离减少≥200 uu，同时自身到球距离增加≥200 uu。在起点固定另外两名队友中离球最近者。通道净宽为该队友至当前球的线段与对手间最小距离，截断至 [0,2000] uu。主效应为追随与匹配无追随事件在 t 至 t+1 秒净宽变化上的差。 零模型：匹配初始状态及先前开阔趋势后，追随不关联额外通道拓宽。匹配起点通道净宽及此前 .5 秒变化、完整球/球员状态、墙壁与 C；比较同阵容事件块。作为负对照的前置区间不得已经显示完整效应。 检验：以系列赛 bootstrap 估计调整后净宽变化差与中心化 p 值；仅当匹配系列赛块可交换时采用受限追随标签置换。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Candidate: own player initially >700 uu from ball, increasing that distance≥300 uu over .5 s. Pursuit=one initially nearby opponent (within1,500 uu) reduces distance to that player≥200 uu while increasing own ball distance≥200 uu. At onset freeze the other teammate nearest the ball. Let corridor clearance be minimum opponent-to-line-segment distance for the segment from that teammate to the current ball, clipped [0,2000] uu. Primary effect: pursuit versus matched no-pursuit difference in clearance change from t to t+1 s. Null model: No extra lane opening associated with pursuit once initial state and prior opening trend are matched. Match onset corridor clearance and its preceding .5 s change, full ball/player state, walls and C; compare same-roster event blocks. A negative-control preceding interval must not already show the full effect. Test: Series-bootstrap adjusted clearance-change difference and centered p; restricted pursuit-label permutation only when matched series blocks are exchangeable. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Linguistics: temporal pragmatics and rhetorical pauses。假设：An approacher's brief kinematic pause is followed by more opponent approach acceleration than a matched uninterrupted approach; the reverse-time association is smaller.": {
    "zh": "借鉴：语言学：时间语用与修辞停顿。假设：相比匹配的不中断接近，接近者短暂的运动学停顿之后，对手更常加速接近；反向时间关联更小。",
    "en": "Inspiration: Linguistics: temporal pragmatics and rhetorical pauses. Hypothesis: An approacher's brief kinematic pause is followed by more opponent approach acceleration than a matched uninterrupted approach; the reverse-time association is smaller."
  },
  "指标：Freeze ball-nearest own player while d∈[700,1500] uu and its own velocity component toward ball c≥500 uu/s for .3 s. Pause: c falls below100 for .3 s while d remains>400 uu; use the end of this qualifying .3 s as the response anchor. Compare with uninterrupted episodes at matched elapsed time. Response: initially nearest opponent's c increases≥400 uu/s over next .5 s. Primary risk difference=pause−uninterrupted. Require all ball–car distances>300 uu during the pause, and exclude large ball impulses; no touch labels needed. 零模型：After matching pre-pause ball/player paths and resources, pause status has no additional opponent-response association. Match pre-pause opponent acceleration and the time already spent approaching; use same-roster windows. Reverse-lag outcome over the .5 s before pause onset is a negative control, never evidence of anticipatory communication. 检验：Series-bootstrap standardized probability difference and centered p; if adding reverse-lag significance, include it in the expanded BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：固定离球最近的己方球员，要求 d∈[700,1500] uu，且其自身朝球速度分量 c≥500 uu/秒持续 .3 秒。停顿定义为 c 降至100以下并持续 .3 秒，同时 d>400 uu；以该合格 .3 秒结束时作为响应锚点。与已用时匹配的不中断事件比较。响应为初始最近对手的 c 在未来 .5 秒增加≥400 uu/秒。主风险差=停顿−不中断。停顿期间所有球车距离须 >300 uu，并排除大幅球冲量；无需触球标签。 零模型：匹配停顿前球/球员轨迹及资源后，停顿状态不再关联额外对手响应。匹配停顿前对手加速度及已接近时长；使用同阵容窗口。停顿起点前 .5 秒的反向滞后结局为负对照，不能作为预期性交流的证据。 检验：以系列赛 bootstrap 估计标准化概率差及中心化 p 值；若加入反向滞后显著性检验，将其纳入扩展 BH 族。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Freeze ball-nearest own player while d∈[700,1500] uu and its own velocity component toward ball c≥500 uu/s for .3 s. Pause: c falls below100 for .3 s while d remains>400 uu; use the end of this qualifying .3 s as the response anchor. Compare with uninterrupted episodes at matched elapsed time. Response: initially nearest opponent's c increases≥400 uu/s over next .5 s. Primary risk difference=pause−uninterrupted. Require all ball–car distances>300 uu during the pause, and exclude large ball impulses; no touch labels needed. Null model: After matching pre-pause ball/player paths and resources, pause status has no additional opponent-response association. Match pre-pause opponent acceleration and the time already spent approaching; use same-roster windows. Reverse-lag outcome over the .5 s before pause onset is a negative control, never evidence of anticipatory communication. Test: Series-bootstrap standardized probability difference and centered p; if adding reverse-lag significance, include it in the expanded BH family. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Physics and graph theory: percolation and widest paths。假设：A continuous high-clearance route through the defending half carries information about a near-term concession beyond the nearest defender's distance.": {
    "zh": "借鉴：物理学与图论：渗流与最宽路径。假设：穿过防守半场的连续高净空通道，提供超出最近防守者距离的近期失球信息。",
    "en": "Inspiration: Physics and graph theory: percolation and widest paths. Hypothesis: A continuous high-clearance route through the defending half carries information about a near-term concession beyond the nearest defender's distance."
  },
  "指标：For ball y∈[−4800,−300], z<300 uu, use the fixed own-half 33×21 grid. Cell clearance is nearest own defender xy distance. From ball cell to central cell at (0,−5120), allow eight-neighbor edges only with nonincreasing y (and no repeated cell). Widest-path clearance W=max_paths min_cell clearance. Define open if W>600 uu. Primary effect: adjusted first-goal-conceded probability within3 s, open minus closed. This is a planar corridor to a fixed goal-line target, not a physically achievable shot. 零模型：No added corridor association at matched ball xyz/vxyz, nearest-defender distance, goal-side count, initial grid coverage and boost. Include ball heading and speed explicitly; retain both open/closed only on common support. The fixed target avoids assuming any unobserved goal-mouth width. 检验：Series-bootstrap standardized risk difference and centered p, with nuisance models cross-fitted by series. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：对球 y∈[−4800,−300]、z<300 uu，使用固定己方半场 33×21 网格。格点净空为距最近己方防守者的 xy 距离。从球所在格到 (0,−5120) 中央格，仅允许 y 不增加的八邻接边（且不得重复格点）。最宽路径净空 W=max_paths min_cell clearance。W>600 uu 定义为贯通。主效应为 3 秒内率先失球的调整后概率，贯通减封闭。这是通向固定球门线目标的平面通道，不代表物理上可行的射门。 零模型：匹配球 xyz/vxyz、最近防守者距离、球门侧人数、初始网格覆盖与 boost 后，不存在额外通道关联。明确纳入球朝向与速度；仅在共同支持上保留贯通/封闭两类。固定目标避免假设未观测的球门口宽度。 检验：以系列赛 bootstrap 估计标准化风险差及中心化 p 值，干扰模型按系列赛交叉拟合。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: For ball y∈[−4800,−300], z<300 uu, use the fixed own-half 33×21 grid. Cell clearance is nearest own defender xy distance. From ball cell to central cell at (0,−5120), allow eight-neighbor edges only with nonincreasing y (and no repeated cell). Widest-path clearance W=max_paths min_cell clearance. Define open if W>600 uu. Primary effect: adjusted first-goal-conceded probability within3 s, open minus closed. This is a planar corridor to a fixed goal-line target, not a physically achievable shot. Null model: No added corridor association at matched ball xyz/vxyz, nearest-defender distance, goal-side count, initial grid coverage and boost. Include ball heading and speed explicitly; retain both open/closed only on common support. The fixed target avoids assuming any unobserved goal-mouth width. Test: Series-bootstrap standardized risk difference and centered p, with nuisance models cross-fitted by series. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Physics and ecology: persistence and resilience。假设：Team-shape deviations persist more strongly before a concession, even at comparable present ball threat and residual variance.": {
    "zh": "借鉴：物理学与生态学：持续性与韧性。假设：在当前球威胁与残差方差相近时，失球前的队形偏离仍有更强的持续性。",
    "en": "Inspiration: Physics and ecology: persistence and resilience. Hypothesis: Team-shape deviations persist more strongly before a concession, even at comparable present ball threat and residual variance."
  },
  "指标：Every .2 s compute xy triangle area A=abs(cross(p2−p1,p3−p1))/2. Cross-fit expected log(A+10,000 uu²) from ball xyz/vxyz, team centroid, resources and C, without using future outcomes. For each prospective ≥9 s anchor use the preceding6 s in one segment to estimate lag-one (.2 s) residual autocorrelation ρ; omit windows with residual SD<.05 log units. Primary effect: mean adjusted ρ in anchors with opponent first goal within3 s minus matched nonconcession anchors. 零模型：No excess shape persistence before concessions once present threat, area and residual variance are matched. Controls include current area, ball distance/heading toward goal, defensive occupancy and resources. Use all prospective anchors, not only sampled pre-goal clips. 检验：Series-bootstrap matched autocorrelation difference and centered p. The test concerns temporal persistence; it does not identify a physical critical point or prove an increasing trend toward collapse. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：每 .2 秒计算 xy 三角形面积 A=abs(cross(p2−p1,p3−p1))/2。根据球 xyz/vxyz、队伍质心、资源与 C 交叉拟合预期 log(A+10,000 uu²)，不使用未来结局。对每个间隔 ≥9 秒的前瞻锚点，使用同一片段中之前6 秒估计残差的一阶滞后（.2 秒）自相关 ρ；剔除残差标准差<.05 对数单位的窗口。主效应为对手在3 秒内率先进球的锚点与匹配未失球锚点间，调整后平均 ρ 的差。 零模型：匹配当前威胁、面积及残差方差后，失球前不存在额外队形持续性。控制变量包括当前面积、球距球门距离/朝向、防守占用与资源。使用所有前瞻锚点，而非仅抽取进球前片段。 检验：以系列赛 bootstrap 估计匹配自相关差及中心化 p 值。检验针对时间持续性，不能识别物理临界点，也不能证明走向崩溃的递增趋势。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Every .2 s compute xy triangle area A=abs(cross(p2−p1,p3−p1))/2. Cross-fit expected log(A+10,000 uu²) from ball xyz/vxyz, team centroid, resources and C, without using future outcomes. For each prospective ≥9 s anchor use the preceding6 s in one segment to estimate lag-one (.2 s) residual autocorrelation ρ; omit windows with residual SD<.05 log units. Primary effect: mean adjusted ρ in anchors with opponent first goal within3 s minus matched nonconcession anchors. Null model: No excess shape persistence before concessions once present threat, area and residual variance are matched. Controls include current area, ball distance/heading toward goal, defensive occupancy and resources. Use all prospective anchors, not only sampled pre-goal clips. Test: Series-bootstrap matched autocorrelation difference and centered p. The test concerns temporal persistence; it does not identify a physical critical point or prove an increasing trend toward collapse. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Traffic physics: string instability。假设：After comparable lateral ball reversals, the rear player's lateral correction is larger than the front player's and exceeds the gain explained by shared forcing.": {
    "zh": "借鉴：交通物理学：串行不稳定性。假设：相近的球横向反转之后，后排球员的横向修正大于前排，且超出共同驱动所能解释的增益。",
    "en": "Inspiration: Traffic physics: string instability. Hypothesis: After comparable lateral ball reversals, the rear player's lateral correction is larger than the front player's and exceeds the gain explained by shared forcing."
  },
  "指标：Detect isolated ball vx sign reversals with |Δvx|≥800 uu/s in .3 s, opposite signs sustained≥.3 s. Freeze front/middle/rear by decreasing own y at onset; retain events with ordering unchanged through .8 s and no next reversal within1 s. Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0). Residualize front/rear responses against initial geometry/resources, ball impulse and C. Primary ΔG=observed regression slope(rear~front) minus the slope under matched block re-pairing. Separately require raw conditional gain G≥1.20. 零模型：No excess amplification beyond shared ball forcing. Re-pair whole rear-response blocks with front-response blocks from different series matched on reversal trajectory, spacing, own starting vx and C; keep all within-block dynamics. Do not divide by small front responses. 检验：Matched-block randomization for ΔG with series-bootstrap intervals; test one primary excess-gain statistic. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：检测孤立的球 vx 反号，要求 .3 秒内 |Δvx|≥800 uu/秒，两侧相反符号均持续≥.3 秒。按起点己方 y 降序固定前/中/后排；保留至 .8 秒排序不变且1 秒内无再次反转的事件。Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0)。对初始几何/资源、球冲量及 C 回归，取前/后排响应残差。主 ΔG=观测回归斜率 slope(rear~front) 减去匹配块重新配对后的斜率。另要求原始条件增益 G≥1.20。 零模型：共同球驱动之外不存在额外放大。将完整后排响应块与不同系列赛的前排响应块重新配对，匹配反转轨迹、间距、自身初始 vx 与 C；保留块内全部动态。不除以过小的前排响应。 检验：对 ΔG 作匹配块随机化，配合系列赛 bootstrap 区间；仅检验一个主超额增益统计量。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Detect isolated ball vx sign reversals with |Δvx|≥800 uu/s in .3 s, opposite signs sustained≥.3 s. Freeze front/middle/rear by decreasing own y at onset; retain events with ordering unchanged through .8 s and no next reversal within1 s. Response_i=mean(vxi,.3:.8)−mean(vxi,−.5:0). Residualize front/rear responses against initial geometry/resources, ball impulse and C. Primary ΔG=observed regression slope(rear~front) minus the slope under matched block re-pairing. Separately require raw conditional gain G≥1.20. Null model: No excess amplification beyond shared ball forcing. Re-pair whole rear-response blocks with front-response blocks from different series matched on reversal trajectory, spacing, own starting vx and C; keep all within-block dynamics. Do not divide by small front responses. Test: Matched-block randomization for ΔG with series-bootstrap intervals; test one primary excess-gain statistic. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Music: entrainment and phase response。假设：Opponent approach phase predicts a team's approach timing beyond its own cadence and shared ball motion.": {
    "zh": "借鉴：音乐：节律同步与相位响应。假设：对手接近相位在本队节律与共同球运动之外，仍能预测本队接近时机。",
    "en": "Inspiration: Music: entrainment and phase response. Hypothesis: Opponent approach phase predicts a team's approach timing beyond its own cadence and shared ball motion."
  },
  "指标：Approach pulse: minimum team–ball xy distance crosses below800 uu after being>1200 for≥.3 s; debounce .5 s. Using only prior pulses, cycle T=median(last3 interpulse intervals), all between .8 and4 s. Phase φ=2π(elapsed since last pulse mod T)/T. A series-cross-fitted hazard model predicts next-.1 s own pulse from own history/phase, ball state/history and C, then adds sinφ_opponent and cosφ_opponent. Primary effect ΔD=held-out standardized peak-to-trough predicted pulse-probability modulation minus the modulation from the matched-history null. 零模型：No residual opponent-phase information. Replace complete opponent pulse-history blocks by other-series blocks matched on current geometry, ball history, own cadence and pulse count; never shuffle individual pulses or use future intervals. Evaluate the complete fitted procedure on held-out series so choosing a peak cannot by itself create a positive result. 检验：Joint two-coefficient phase test via2,000 matched history-block randomizations; whole-series bootstrap ΔD CI. Peak-to-trough alone is nonnegative, so its uncorrected size is not a valid null test. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：接近脉冲：全队最小球距 xy 在 >1200 持续≥.3 秒后穿越至800 uu 以下；去抖 .5 秒。仅使用过去脉冲，周期 T=median(最近3 个脉冲间隔)，各间隔均介于 .8 与4 秒。相位 φ=2π(距上次脉冲时间 mod T)/T。按系列赛交叉拟合的风险模型先根据本队历史/相位、球状态/历史及 C 预测未来 .1 秒本队脉冲，再加入 sinφ_opponent 与 cosφ_opponent。主效应 ΔD=留出集标准化峰谷预测脉冲概率调制，减去匹配历史零模型的调制。 零模型：不存在残余对手相位信息。用其他系列赛中匹配当前几何、球历史、本队节律及脉冲数的完整对手脉冲历史块替换原块；不得打乱单个脉冲或使用未来间隔。在留出系列赛上评估完整拟合程序，使选择峰值本身不能制造正结果。 检验：通过2,000 次匹配历史块随机化进行两个相位系数的联合检验；用完整系列赛 bootstrap 估计 ΔD 置信区间。峰谷差本身非负，因此未经校正的大小不是有效的零假设检验。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Approach pulse: minimum team–ball xy distance crosses below800 uu after being>1200 for≥.3 s; debounce .5 s. Using only prior pulses, cycle T=median(last3 interpulse intervals), all between .8 and4 s. Phase φ=2π(elapsed since last pulse mod T)/T. A series-cross-fitted hazard model predicts next-.1 s own pulse from own history/phase, ball state/history and C, then adds sinφ_opponent and cosφ_opponent. Primary effect ΔD=held-out standardized peak-to-trough predicted pulse-probability modulation minus the modulation from the matched-history null. Null model: No residual opponent-phase information. Replace complete opponent pulse-history blocks by other-series blocks matched on current geometry, ball history, own cadence and pulse count; never shuffle individual pulses or use future intervals. Evaluate the complete fitted procedure on held-out series so choosing a peak cannot by itself create a positive result. Test: Joint two-coefficient phase test via2,000 matched history-block randomizations; whole-series bootstrap ΔD CI. Peak-to-trough alone is nonnegative, so its uncorrected size is not a valid null test. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Linguistics and music: expectation violation。假设：The same physical lateral turn is associated with a slower opponent adjustment when it breaks a previously repeated local route ending.": {
    "zh": "借鉴：语言学与音乐：违背预期。假设：同样的物理横向转向，如果打破此前局部路线末尾的重复模式，则与更慢的对手调整相关。",
    "en": "Inspiration: Linguistics and music: expectation violation. Hypothesis: The same physical lateral turn is associated with a slower opponent adjustment when it breaks a previously repeated local route ending."
  },
  "指标：Route symbols every .5 s: L if Δx<−150 uu, S if |Δx|≤150, R if Δx>150. Keep a focal player within2000 uu of ball and with own toward-ball component>300. A three-symbol prefix qualifies only after≥3 earlier nonoverlapping occurrences in the same replay/player, with a common next symbol in≥75%. An observed alternative L/R ending is a variation. Anchor response measurement at the end of that ending interval (exposure then known). Freeze nearest opponent at ending onset. Latency=first onset within next1 s for which opponent vx takes the new-turn sign with magnitude≥200 uu/s for .3 s. Require observation through1.3 s to verify the sustain, including for onsets near1 s; alignment already present at anchor counts0 only if sustained through.3 s. No qualifying onset by1 s gives1. Primary effect: adjusted mean capped latency versus physically matched L/R endings without established repetition. 零模型：No history-specific delay after matching the actual turn, ball motion, current opponent velocity and prior trajectories. Reassign repetition histories only across same-player/roster context-matched occurrences, preserving current route and response blocks; histories must be strictly earlier. Never infer a prefix's expected ending from future occurrences. 检验：Whole-series bootstrap of the matched capped-latency difference and centered p. The cap defines a restricted one-second response-time estimand; missing/reset-censored responses follow the outcome contract. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：每 .5 秒生成路线符号：Δx<−150 uu 为 L，|Δx|≤150 为 S，Δx>150 为 R。保留距球2000 uu 内且自身朝球分量>300 的焦点球员。三符号前缀仅在同回放/球员中已有≥3 次更早且不重叠的出现、且≥75% 采用共同后续符号时合格。观测到另一种 L/R 结尾即为变奏。以该结尾区间结束时测量响应（此时暴露已知）。在结尾开始时固定最近对手。延迟=未来1 秒内，对手 vx 首次采用新转向符号、幅度≥200 uu/秒且持续 .3 秒的起点。须观测至1.3 秒以核验持续性，包括接近1 秒的起点；锚点已有同向运动，仅在持续至 .3 秒时记0。1 秒内无合格起点记1。主效应为相对物理匹配、但未形成既定重复的 L/R 结尾，调整后的平均截顶延迟差。 零模型：匹配实际转向、球运动、当前对手速度及先前轨迹后，不存在历史特异延迟。仅在同球员/阵容、情境匹配的事件间重新分配重复历史，保留当前路线与响应块；历史必须严格早于事件。不得用未来出现推断前缀的预期结尾。 检验：对匹配截顶延迟差作完整系列赛 bootstrap 并计算中心化 p 值。截顶定义了一秒限制响应时间估计目标；缺失/重置删失响应遵守结局约定。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Route symbols every .5 s: L if Δx<−150 uu, S if |Δx|≤150, R if Δx>150. Keep a focal player within2000 uu of ball and with own toward-ball component>300. A three-symbol prefix qualifies only after≥3 earlier nonoverlapping occurrences in the same replay/player, with a common next symbol in≥75%. An observed alternative L/R ending is a variation. Anchor response measurement at the end of that ending interval (exposure then known). Freeze nearest opponent at ending onset. Latency=first onset within next1 s for which opponent vx takes the new-turn sign with magnitude≥200 uu/s for .3 s. Require observation through1.3 s to verify the sustain, including for onsets near1 s; alignment already present at anchor counts0 only if sustained through.3 s. No qualifying onset by1 s gives1. Primary effect: adjusted mean capped latency versus physically matched L/R endings without established repetition. Null model: No history-specific delay after matching the actual turn, ball motion, current opponent velocity and prior trajectories. Reassign repetition histories only across same-player/roster context-matched occurrences, preserving current route and response blocks; histories must be strictly earlier. Never infer a prefix's expected ending from future occurrences. Test: Whole-series bootstrap of the matched capped-latency difference and centered p. The cap defines a restricted one-second response-time estimand; missing/reset-censored responses follow the outcome contract. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Evolutionary ecology: negative frequency dependence。假设：The same explicit formation has greater forward-ball payoff against opponents for whom that formation is rarer in other observed series, beyond shape and opponent main effects. This is an exposure–payoff association, not proof of unfamiliarity or learning.": {
    "zh": "借鉴：演化生态学：负频率依赖。假设：同一种明确阵型，对那些在其他已观测系列赛中较少遇到该阵型的对手，具有更大的球前进收益，且超出阵型与对手主效应的解释。这是暴露与收益的关联，不证明不熟悉或学习。",
    "en": "Inspiration: Evolutionary ecology: negative frequency dependence. Hypothesis: The same explicit formation has greater forward-ball payoff against opponents for whom that formation is rarer in other observed series, beyond shape and opponent main effects. This is an exposure–payoff association, not proof of unfamiliarity or learning."
  },
  "指标：Four shape states use own lateral spread≥2500 versus narrower and longitudinal spread≥2500 versus shallower. For each opponent roster o and state s, estimate E_os=frequency that opponents of o used s in other same-season series, excluding the evaluated series and every series involving the evaluated focal roster. Context-standardize to shared ball-half/height/score/time support and shrink with training-only rules. Rarity R_os=−log2(E_os). Outcome: signed ball-y progress over next2 s. Primary coefficient β is uu progress per doubling rarity, with shape fixed effects, opponent and own-roster effects, continuous spread/depth and C. 零模型：β=0 after geometry, shape and opponent main effects. Identification comes from the supported opponent×shape interaction; a season×region prevalence alone would be absorbed by saturated controls and is not used. Compare the same shape across opponents and different supported shapes within opponents. Cluster bootstrap recomputes all cross-fitted exposure estimates. 检验：Whole-series bootstrap β CI and centered p, including exposure-estimation uncertainty. Do not use a season/region permutation that destroys the structure needed for identification. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：按己方横向跨度≥2500 或更窄、纵向跨度≥2500 或更浅定义四种阵型状态。对每个对手阵容 o 与状态 s，估计 E_os=在同赛季其他系列赛中，o 的对手使用 s 的频率，排除被评估系列赛及所有涉及被评估焦点阵容的系列赛。在共同球半场/高度/比分/时间支持上进行情境标准化，并按仅用训练集确定的规则收缩。稀有度 R_os=−log2(E_os)。结局为未来2 秒带符号的球 y 推进。主系数 β 为稀有度每翻倍的推进 uu，纳入阵型固定效应、对手与己方阵容效应、连续跨度/深度及 C。 零模型：控制几何、阵型与对手主效应后 β=0。识别来自有支持的对手×阵型交互；仅有赛季×赛区流行率会被饱和控制吸收，故不使用。比较同一阵型在不同对手间，以及同一对手内不同受支持阵型。聚类 bootstrap 重新计算全部交叉拟合暴露估计。 检验：以完整系列赛 bootstrap 估计 β 置信区间与中心化 p 值，纳入暴露估计不确定性。不使用会破坏识别所需结构的赛季/赛区置换。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Four shape states use own lateral spread≥2500 versus narrower and longitudinal spread≥2500 versus shallower. For each opponent roster o and state s, estimate E_os=frequency that opponents of o used s in other same-season series, excluding the evaluated series and every series involving the evaluated focal roster. Context-standardize to shared ball-half/height/score/time support and shrink with training-only rules. Rarity R_os=−log2(E_os). Outcome: signed ball-y progress over next2 s. Primary coefficient β is uu progress per doubling rarity, with shape fixed effects, opponent and own-roster effects, continuous spread/depth and C. Null model: β=0 after geometry, shape and opponent main effects. Identification comes from the supported opponent×shape interaction; a season×region prevalence alone would be absorbed by saturated controls and is not used. Compare the same shape across opponents and different supported shapes within opponents. Cluster bootstrap recomputes all cross-fitted exposure estimates. Test: Whole-series bootstrap β CI and centered p, including exposure-estimation uncertainty. Do not use a season/region permutation that destroys the structure needed for identification. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "借鉴：Ecology and evolution: community assembly and convergent organization。假设：New combinations of player identities display more simultaneous spatial complementarity than independently combining those players' habits measured in other rosters.": {
    "zh": "借鉴：生态学与演化：群落装配与趋同组织。假设：新的球员身份组合表现出更强的同时空间互补性，超过将这些球员在其他阵容测得的习惯独立组合所得结果。",
    "en": "Inspiration: Ecology and evolution: community assembly and convergent organization. Hypothesis: New combinations of player identities display more simultaneous spatial complementarity than independently combining those players' habits measured in other rosters."
  },
  "指标：Assign each own player a ball-relative planar sector: left/center/right using x−ball_x thresholds±600 uu, crossed with behind/ahead using y−ball_y<0 versus≥0. Complementarity=probability three players occupy three distinct sectors. For each target roster, estimate each member's sector distribution only from other-roster same-season series, matched on ball state, score/time, velocity and boost. Primary effect=observed distinct-sector probability minus synthetic independent-trio probability, averaged equally over target rosters. 零模型：Independent assortment of individual habits under matched context. Generate pseudo-trios from actual complete other-roster observation blocks for each player; preserve each member's marginal sector distribution and resource context. A same-roster cross-series pseudo-trio null is a secondary diagnostic for shared-ball constraints, not a replacement primary test. 检验：Series bootstrap and conditional pseudo-trio randomization; whenever target/reference rosters share players, require a crossed shared-player/roster and series multiway bootstrap for primary uncertainty. Use the larger of the series-bootstrap and dependency-aware p-values as this idea's single BH input, and the hull of their confidence intervals. The player-disjoint target-roster sensitivity is additional support, never a substitute for valid primary uncertainty. Insufficient independent cluster support makes the result inconclusive. The bootstrap must include both target and reference series and re-estimate marginal habits. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data.": {
    "zh": "指标：为每名己方球员分配相对球的平面扇区：以 x−ball_x 阈值±600 uu 区分左/中/右，再以 y−ball_y<0 或≥0 区分后/前。互补性=三名球员占据三个不同扇区的概率。对每个目标阵容，仅用同赛季其他阵容系列赛估计各成员扇区分布，匹配球状态、比分/时间、速度与 boost。主效应=观测不同扇区概率减合成独立三人组概率，目标阵容间等权平均。 零模型：匹配情境下个体习惯独立组合。用各球员真实完整的其他阵容观测块生成伪三人组；保留各成员边际扇区分布及资源情境。同阵容跨系列赛伪三人组零模型是共同球约束的次要诊断，不替代主检验。 检验：采用系列赛 bootstrap 与条件伪三人组随机化；目标/参考阵容共享球员时，主不确定性必须采用共享球员/阵容与系列赛交叉的多向 bootstrap。取系列赛 bootstrap 与考虑依赖的 p 值中较大者，作为该想法唯一的 BH 输入；置信区间取两者包络。球员不重叠目标阵容的敏感性仅作附加支持，不替代有效的主不确定性。独立聚类支持不足则结果不确定。bootstrap 必须包含目标与参考系列赛，并重新估计边际习惯。 使用 2,000 次完整系列赛 bootstrap 重复（保留两队及所有比赛）；除非指定受限置换，否则采用以零假设为中心的双侧聚类 bootstrap 检验，并对全部 18 项主筛查作 BH 校正；冻结至多三个扩大规模的假设，在未接触的确认数据上采用 Holm α=.05。",
    "en": "Metric: Assign each own player a ball-relative planar sector: left/center/right using x−ball_x thresholds±600 uu, crossed with behind/ahead using y−ball_y<0 versus≥0. Complementarity=probability three players occupy three distinct sectors. For each target roster, estimate each member's sector distribution only from other-roster same-season series, matched on ball state, score/time, velocity and boost. Primary effect=observed distinct-sector probability minus synthetic independent-trio probability, averaged equally over target rosters. Null model: Independent assortment of individual habits under matched context. Generate pseudo-trios from actual complete other-roster observation blocks for each player; preserve each member's marginal sector distribution and resource context. A same-roster cross-series pseudo-trio null is a secondary diagnostic for shared-ball constraints, not a replacement primary test. Test: Series bootstrap and conditional pseudo-trio randomization; whenever target/reference rosters share players, require a crossed shared-player/roster and series multiway bootstrap for primary uncertainty. Use the larger of the series-bootstrap and dependency-aware p-values as this idea's single BH input, and the hull of their confidence intervals. The player-disjoint target-roster sensitivity is additional support, never a substitute for valid primary uncertainty. Insufficient independent cluster support makes the result inconclusive. The bootstrap must include both target and reference series and re-estimate marginal habits. Use 2,000 whole-series bootstrap replicates (both teams/all games retained), a two-sided null-centered cluster-bootstrap test unless a restricted permutation is specified, and BH across all 18 primary screens; freeze at most three scaled hypotheses for Holm α=.05 on unexposed confirmation data."
  },
  "adjusted": {
    "zh": "调整后",
    "en": "Adjusted"
  },
  "difference_for": {
    "zh": "进球概率差",
    "en": "Scoring probability difference"
  },
  "difference_against": {
    "zh": "失球概率差",
    "en": "Concession probability difference"
  },
  "difference_net_gd": {
    "zh": "净进球差",
    "en": "Net goal difference"
  },
  "stay_for": {
    "zh": "保持位置时进球概率",
    "en": "Scoring probability when staying"
  },
  "stay_against": {
    "zh": "保持位置时失球概率",
    "en": "Concession probability when staying"
  },
  "stay_net_gd": {
    "zh": "保持位置时净进球",
    "en": "Net goals when staying"
  },
  "advance_for": {
    "zh": "前压时进球概率",
    "en": "Scoring probability when advancing"
  },
  "advance_against": {
    "zh": "前压时失球概率",
    "en": "Concession probability when advancing"
  },
  "advance_net_gd": {
    "zh": "前压时净进球",
    "en": "Net goals when advancing"
  },
  "deep_for": {
    "zh": "深位时进球概率",
    "en": "Scoring probability in deep position"
  },
  "deep_against": {
    "zh": "深位时失球概率",
    "en": "Concession probability in deep position"
  },
  "deep_net_gd": {
    "zh": "深位时净进球",
    "en": "Net goals in deep position"
  },
  "advanced_for": {
    "zh": "前压位置进球概率",
    "en": "Scoring probability in advanced position"
  },
  "advanced_against": {
    "zh": "前压位置失球概率",
    "en": "Concession probability in advanced position"
  },
  "advanced_net_gd": {
    "zh": "前压位置净进球",
    "en": "Net goals in advanced position"
  },
  "roster_id": {
    "zh": "阵容 ID",
    "en": "Roster ID"
  },
  "player_id": {
    "zh": "球员 ID",
    "en": "Player ID"
  },
  "null": {
    "zh": "零模型",
    "en": "Null model"
  },
  "primary": {
    "zh": "主分析",
    "en": "Primary"
  },
  "empirical_marginal_diagnostic": {
    "zh": "经验边际诊断",
    "en": "Empirical marginal diagnostic"
  },
  "eligible_unshifted_diagnostic": {
    "zh": "合格未平移样本诊断",
    "en": "Eligible unshifted diagnostic"
  },
  "result": {
    "zh": "结果",
    "en": "Result"
  },
  "inputs": {
    "zh": "输入",
    "en": "Inputs"
  },
  "full_model": {
    "zh": "完整模型",
    "en": "Full model"
  },
  "metrics": {
    "zh": "指标",
    "en": "Metrics"
  },
  "top1": {
    "zh": "第1位命中率",
    "en": "Top-1 accuracy"
  },
  "top5": {
    "zh": "前5位命中率",
    "en": "Top-5 accuracy"
  },
  "mrr": {
    "zh": "平均倒数排名",
    "en": "Mean reciprocal rank"
  },
  "a": {
    "zh": "路径 a",
    "en": "Path a"
  },
  "b": {
    "zh": "路径 b",
    "en": "Path b"
  },
  "a*b": {
    "zh": "路径 a*b",
    "en": "Path a*b"
  },
  "direct": {
    "zh": "直接项",
    "en": "Direct component"
  },
  "total": {
    "zh": "总计",
    "en": "Total"
  },
  "proportion": {
    "zh": "比例",
    "en": "Proportion"
  },
  "sensitivity": {
    "zh": "敏感性",
    "en": "Sensitivity"
  },
  "earlier_width": {
    "zh": "较早宽度",
    "en": "Earlier width"
  },
  "details": {
    "zh": "明细",
    "en": "Details"
  },
  "realized_ball_control": {
    "zh": "实际球运动控制",
    "en": "Realized-ball control"
  },
  "train": {
    "zh": "训练集",
    "en": "Train"
  },
  "L1_km_rmst": {
    "zh": "L1 Kaplan–Meier RMST",
    "en": "L1 Kaplan–Meier RMST"
  },
  "L1_uncensored_ols": {
    "zh": "L1 未删失 OLS",
    "en": "L1 uncensored OLS"
  },
  "L2_latency_logit": {
    "zh": "L2 延迟逻辑回归",
    "en": "L2 latency logit"
  },
  "S_opp": {
    "zh": "对手指标 S_opp",
    "en": "Opponent metric S_opp"
  },
  "S_opp_concede": {
    "zh": "对手失球指标 S_opp_concede",
    "en": "Opponent concession metric S_opp_concede"
  },
  "paired_urgency": {
    "zh": "配对紧迫程度",
    "en": "Paired urgency"
  },
  "urgency": {
    "zh": "紧迫程度",
    "en": "Urgency"
  },
  "contrasts": {
    "zh": "对比",
    "en": "Contrasts"
  },
  "p6_1_leading_late_minus_early": {
    "zh": "P6.1 领先方末段减早段",
    "en": "P6.1 leading late minus early"
  },
  "p6_1_trailing_late_minus_early": {
    "zh": "P6.1 落后方末段减早段",
    "en": "P6.1 trailing late minus early"
  },
  "p6_1_trailing_minus_leading_interaction": {
    "zh": "P6.1 落后减领先交互",
    "en": "P6.1 trailing minus leading interaction"
  },
  "p6_6_ot_minus_late_tied": {
    "zh": "P6.6 加时减常规末段平局",
    "en": "P6.6 overtime minus late tied regulation"
  },
  "p6_6_late_trailing_minus_ot": {
    "zh": "P6.6 末段落后减加时",
    "en": "P6.6 late trailing minus overtime"
  },
  "p6_7_centroid_interaction": {
    "zh": "P6.7 质心交互",
    "en": "P6.7 centroid interaction"
  },
  "p6_7_mean_depth_interaction": {
    "zh": "P6.7 平均深度交互",
    "en": "P6.7 mean-depth interaction"
  },
  "Intercept": {
    "zh": "截距",
    "en": "Intercept"
  },
  "late": {
    "zh": "末段",
    "en": "Late"
  },
  "late:trailing": {
    "zh": "末段×落后",
    "en": "Late × trailing"
  },
  "RQ1_p_holm": {
    "zh": "RQ1 Holm 校正 p 值",
    "en": "RQ1 Holm-adjusted p"
  },
  "RQ3_p_holm": {
    "zh": "RQ3 Holm 校正 p 值",
    "en": "RQ3 Holm-adjusted p"
  },
  "anchors": {
    "zh": "锚点数",
    "en": "Anchors"
  },
  "bytes": {
    "zh": "字节数",
    "en": "Bytes"
  },
  "causal_identification_gate_passed": {
    "zh": "因果识别门槛通过",
    "en": "Causal identification gate passed"
  },
  "context_rows": {
    "zh": "情境行数",
    "en": "Context rows"
  },
  "discoveries_q005": {
    "zh": "发现数（q005）",
    "en": "Discoveries (q005)"
  },
  "elapsed_seconds": {
    "zh": "已用秒数",
    "en": "Elapsed seconds"
  },
  "excess_gain_bits": {
    "zh": "超额增益（比特）",
    "en": "Excess gain (bits)"
  },
  "exploratory_dr_difference_against": {
    "zh": "探索性双重稳健失球概率差",
    "en": "Exploratory DR concession probability difference"
  },
  "exploratory_dr_difference_for": {
    "zh": "探索性双重稳健进球概率差",
    "en": "Exploratory DR scoring probability difference"
  },
  "exploratory_dr_difference_net_gd": {
    "zh": "探索性双重稳健净进球差",
    "en": "Exploratory DR net goal difference"
  },
  "failed_games": {
    "zh": "失败比赛数",
    "en": "Failed games"
  },
  "family_size": {
    "zh": "检验族大小",
    "en": "Family size"
  },
  "figures": {
    "zh": "图表数",
    "en": "Figures"
  },
  "files": {
    "zh": "文件数",
    "en": "Files"
  },
  "fingerprints": {
    "zh": "指纹数",
    "en": "Fingerprints"
  },
  "frame_derived_timed_goal_coverage": {
    "zh": "帧推导带时间进球覆盖率",
    "en": "Frame-derived timed goal coverage"
  },
  "frames": {
    "zh": "帧数",
    "en": "Frames"
  },
  "goal_agreement_rate": {
    "zh": "进球一致率",
    "en": "Goal agreement rate"
  },
  "ideas": {
    "zh": "想法数",
    "en": "Ideas"
  },
  "index_games": {
    "zh": "索引比赛数",
    "en": "Indexed games"
  },
  "k": {
    "zh": "聚类数 k",
    "en": "Cluster count k"
  },
  "live_frames": {
    "zh": "活球帧数",
    "en": "Live-play frames"
  },
  "metadata_timed_goal_coverage": {
    "zh": "元数据带时间进球覆盖率",
    "en": "Metadata timed goal coverage"
  },
  "n_train_replays": {
    "zh": "训练回放数",
    "en": "Training replays"
  },
  "n_val_replays": {
    "zh": "验证回放数",
    "en": "Validation replays"
  },
  "not_computable": {
    "zh": "无法计算",
    "en": "Not computable"
  },
  "odd_player_games": {
    "zh": "奇数球员比赛数",
    "en": "Games with odd player counts"
  },
  "ok_games": {
    "zh": "成功比赛数",
    "en": "Successful games"
  },
  "p_value": {
    "zh": "p 值",
    "en": "p-value"
  },
  "perspectives": {
    "zh": "视角数",
    "en": "Perspectives"
  },
  "player_fingerprints": {
    "zh": "球员指纹数",
    "en": "Player fingerprints"
  },
  "predictive_gain_bits": {
    "zh": "预测增益（比特）",
    "en": "Predictive gain (bits)"
  },
  "primary_estimates": {
    "zh": "主估计数",
    "en": "Primary estimates"
  },
  "promising": {
    "zh": "有潜力",
    "en": "Promising"
  },
  "replays": {
    "zh": "回放数",
    "en": "Replays"
  },
  "replays_processed": {
    "zh": "已处理回放数",
    "en": "Processed replays"
  },
  "scanned_frames": {
    "zh": "已扫描帧数",
    "en": "Scanned frames"
  },
  "season_fingerprints": {
    "zh": "赛季指纹数",
    "en": "Season fingerprints"
  },
  "selected_replays": {
    "zh": "选定回放数",
    "en": "Selected replays"
  },
  "series_coverage": {
    "zh": "系列赛覆盖率",
    "en": "Series coverage"
  },
  "shards": {
    "zh": "分片数",
    "en": "Shards"
  },
  "stable_player_id_coverage": {
    "zh": "稳定球员 ID 覆盖率",
    "en": "Stable player ID coverage"
  },
  "state_decoding_failures": {
    "zh": "状态解码失败数",
    "en": "State decoding failures"
  },
  "tests": {
    "zh": "检验数",
    "en": "Tests"
  },
  "timed_goal_coverage": {
    "zh": "带时间进球覆盖率",
    "en": "Timed goal coverage"
  },
  "validated_replays": {
    "zh": "已验证回放数",
    "en": "Validated replays"
  },
  "weak": {
    "zh": "证据较弱",
    "en": "Weak evidence"
  },
  "windows": {
    "zh": "窗口数",
    "en": "Windows"
  },
  "loss": {
    "zh": "损失",
    "en": "Loss"
  },
  "dimensionless": {
    "zh": "无量纲",
    "en": "Dimensionless"
  },
  "ms": {
    "zh": "毫秒",
    "en": "ms"
  },
  "uu": {
    "zh": "游戏单位 uu",
    "en": "game units (uu)"
  },
  "unspecified": {
    "zh": "未标注划分",
    "en": "Unspecified split"
  },
  "rlcs-2025": {
    "zh": "RLCS 2025",
    "en": "RLCS 2025"
  },
  "rlcs-2024": {
    "zh": "RLCS 2024",
    "en": "RLCS 2024"
  },
  "rlcs-21-22": {
    "zh": "RLCS 21-22",
    "en": "RLCS 21-22"
  },
  "rlcs-22-23": {
    "zh": "RLCS 22-23",
    "en": "RLCS 22-23"
  },
  "pressure.json": {
    "zh": "pressure.json",
    "en": "pressure.json"
  },
  "tokens_learned_val.json": {
    "zh": "tokens_learned_val.json",
    "en": "tokens_learned_val.json"
  },
  "/home/c.li16@students.uu.nl/workspace/rlcs-replays/data": {
    "zh": "/home/c.li16@students.uu.nl/workspace/rlcs-replays/data",
    "en": "/home/c.li16@students.uu.nl/workspace/rlcs-replays/data"
  },
  "analysis/posthoc-sens-41105078/posthoc_sens.json": {
    "zh": "analysis/posthoc-sens-41105078/posthoc_sens.json",
    "en": "analysis/posthoc-sens-41105078/posthoc_sens.json"
  },
  "analysis/rq4-habits-medium/rq4_habits.json (job 41105075)": {
    "zh": "analysis/rq4-habits-medium/rq4_habits.json （作业 41105075）",
    "en": "analysis/rq4-habits-medium/rq4_habits.json (job 41105075)"
  },
  "tactics/docs/P2_design.md §6–7": {
    "zh": "tactics/docs/P2_design.md §6–7",
    "en": "tactics/docs/P2_design.md §6–7"
  },
  "results/p5_latency.json (job 41105041)": {
    "zh": "results/p5_latency.json （作业 41105041）",
    "en": "results/p5_latency.json (job 41105041)"
  },
  "artifacts/p6-kickoff-medium/results/p6_kickoff.json K1.pooled (job 41105020)": {
    "zh": "artifacts/p6-kickoff-medium/results/p6_kickoff.json K1.pooled （作业 41105020）",
    "en": "artifacts/p6-kickoff-medium/results/p6_kickoff.json K1.pooled (job 41105020)"
  },
  "results/p6_variants.json (job 41105010)": {
    "zh": "results/p6_variants.json （作业 41105010）",
    "en": "results/p6_variants.json (job 41105010)"
  },
  "tokens_handcrafted_val.json": {
    "zh": "tokens_handcrafted_val.json",
    "en": "tokens_handcrafted_val.json"
  },
  "tactics/docs/P2_design.md §6": {
    "zh": "tactics/docs/P2_design.md §6",
    "en": "tactics/docs/P2_design.md §6"
  },
  "nvidia-smi in jobs 41104642/41104643/41104646": {
    "zh": "作业 41104642/41104643/41104646 中的 nvidia-smi",
    "en": "nvidia-smi in jobs 41104642/41104643/41104646"
  },
  "Dashboard highlights / 仪表盘关键数字": {
    "zh": "仪表盘关键数字",
    "en": "Dashboard highlights"
  },
  "Local source path and field / 本地来源路径及字段": {
    "zh": "本地来源路径及字段",
    "en": "Local source path and field"
  },
  "开球 K1：落后−领先 前压深度 (uu)": {
    "zh": "开球 K1：落后−领先 前压深度 (uu)",
    "en": "Kickoff K1: trailing−leading push-up depth (uu)"
  },
  "Kickoff K1: trailing−leading push-up depth (uu)": {
    "zh": "开球 K1：落后−领先 前压深度 (uu)",
    "en": "Kickoff K1: trailing−leading push-up depth (uu)"
  },
  "对称性交互 (uu)": {
    "zh": "对称性交互 (uu)",
    "en": "Symmetry interaction (uu)"
  },
  "Symmetry interaction (uu)": {
    "zh": "对称性交互 (uu)",
    "en": "Symmetry interaction (uu)"
  },
  "落后方 后段−前段 (uu)": {
    "zh": "落后方 后段−前段 (uu)",
    "en": "Trailing late−early (uu)"
  },
  "Trailing late−early (uu)": {
    "zh": "落后方 后段−前段 (uu)",
    "en": "Trailing late−early (uu)"
  },
  "领先方 后段−前段 (uu)": {
    "zh": "领先方 后段−前段 (uu)",
    "en": "Leading late−early (uu)"
  },
  "Leading late−early (uu)": {
    "zh": "领先方 后段−前段 (uu)",
    "en": "Leading late−early (uu)"
  },
  "K2 高−低激进 20s 失球率（事后，±3 截断）": {
    "zh": "K2 高−低激进 20s 失球率（事后，±3 截断）",
    "en": "K2 high−low aggressiveness, concede ≤20 s (post hoc, clip ±3)"
  },
  "K2 high−low aggressiveness, concede ≤20 s (post hoc, clip ±3)": {
    "zh": "K2 高−低激进 20s 失球率（事后，±3 截断）",
    "en": "K2 high−low aggressiveness, concede ≤20 s (post hoc, clip ±3)"
  },
  "P5 轮转延迟 RMST 差 (s，门槛未过)": {
    "zh": "P5 轮转延迟 RMST 差 (s，门槛未过)",
    "en": "P5 rotation latency RMST diff (s, gate failed)"
  },
  "P5 rotation latency RMST diff (s, gate failed)": {
    "zh": "P5 轮转延迟 RMST 差 (s，门槛未过)",
    "en": "P5 rotation latency RMST diff (s, gate failed)"
  },
  "习惯稳定性 Spearman ρ 范围（中样本）": {
    "zh": "习惯稳定性 Spearman ρ 范围（中样本）",
    "en": "Habit stability Spearman ρ range (medium)"
  },
  "Habit stability Spearman ρ range (medium)": {
    "zh": "习惯稳定性 Spearman ρ 范围（中样本）",
    "en": "Habit stability Spearman ρ range (medium)"
  },
  "0.36–0.74": {
    "zh": "0.36–0.74",
    "en": "0.36–0.74"
  },
  "VisuaLeague: Visual Analytics of Multiple Games": {
    "zh": "VisuaLeague：多场比赛的可视分析",
    "en": "VisuaLeague: Visual Analytics of Multiple Games"
  },
  "2021 25th International Conference Information Visualisation (IV)": {
    "zh": "2021 年第 25 届信息可视化国际会议（IV）",
    "en": "2021 25th International Conference Information Visualisation (IV)"
  },
  "ballchasing.com": {
    "zh": "ballchasing.com",
    "en": "ballchasing.com"
  },
  "Rocket League replay hosting, visualization, and statistics service": {
    "zh": "Rocket League 回放托管、可视化与统计服务",
    "en": "Rocket League replay hosting, visualization, and statistics service"
  },
  "Doubly Robust Estimation in Missing Data and Causal Inference Models": {
    "zh": "缺失数据与因果推断模型中的双重稳健估计",
    "en": "Doubly Robust Estimation in Missing Data and Causal Inference Models"
  },
  "Biometrics": {
    "zh": "《生物统计学》",
    "en": "Biometrics"
  },
  "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing": {
    "zh": "控制错误发现率：一种实用且有效的多重检验方法",
    "en": "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing"
  },
  "Journal of the Royal Statistical Society. Series B (Methodological)": {
    "zh": "《皇家统计学会学报 B 辑（方法论）》",
    "en": "Journal of the Royal Statistical Society. Series B (Methodological)"
  },
  "Rocket League Championship Series 2021-2022": {
    "zh": "Rocket League 冠军系列赛 2021–2022",
    "en": "Rocket League Championship Series 2021-2022"
  },
  "Kaggle dataset": {
    "zh": "Kaggle 数据集",
    "en": "Kaggle dataset"
  },
  "Coordinated Multi-Agent Imitation Learning": {
    "zh": "协调式多智能体模仿学习",
    "en": "Coordinated Multi-Agent Imitation Learning"
  },
  "Proceedings of the 34th International Conference on Machine Learning": {
    "zh": "第 34 届国际机器学习会议论文集",
    "en": "Proceedings of the 34th International Conference on Machine Learning"
  },
  "Representing and Discovering Adversarial Team Behaviors Using Player Roles": {
    "zh": "利用球员角色表示与发现对抗性团队行为",
    "en": "Representing and Discovering Adversarial Team Behaviors Using Player Roles"
  },
  "2013 IEEE Conference on Computer Vision and Pattern Recognition": {
    "zh": "2013 年 IEEE 计算机视觉与模式识别会议",
    "en": "2013 IEEE Conference on Computer Vision and Pattern Recognition"
  },
  "A Behavioral Pattern Mining Approach to Model Player Skills in Rocket League": {
    "zh": "通过行为模式挖掘建模 Rocket League 玩家技能",
    "en": "A Behavioral Pattern Mining Approach to Model Player Skills in Rocket League"
  },
  "2020 IEEE Conference on Games (CoG)": {
    "zh": "2020 年 IEEE 游戏会议（CoG）",
    "en": "2020 IEEE Conference on Games (CoG)"
  },
  "A Model for High-Order Markov Chains": {
    "zh": "高阶马尔可夫链模型",
    "en": "A Model for High-Order Markov Chains"
  },
  "Estimation of Regression Coefficients When Some Regressors are not Always Observed": {
    "zh": "部分回归变量并非始终可观测时的回归系数估计",
    "en": "Estimation of Regression Coefficients When Some Regressors are not Always Observed"
  },
  "Journal of the American Statistical Association": {
    "zh": "《美国统计学会杂志》",
    "en": "Journal of the American Statistical Association"
  },
  "Temporal Graph Networks for Deep Learning on Dynamic Graphs": {
    "zh": "用于动态图深度学习的时间图网络",
    "en": "Temporal Graph Networks for Deep Learning on Dynamic Graphs"
  },
  "arXiv preprint arXiv:2006.10637": {
    "zh": "arXiv 预印本 arXiv:2006.10637",
    "en": "arXiv preprint arXiv:2006.10637"
  },
  "subtr-actor": {
    "zh": "subtr-actor",
    "en": "subtr-actor"
  },
  "Software repository": {
    "zh": "软件代码仓库",
    "en": "Software repository"
  },
  "Analyzing the Differences between Professional and Amateur Esports through Win Probability": {
    "zh": "通过获胜概率分析职业与业余电竞的差异",
    "en": "Analyzing the Differences between Professional and Amateur Esports through Win Probability"
  },
  "Proceedings of the ACM Web Conference 2022": {
    "zh": "2022 年 ACM 万维网会议论文集",
    "en": "Proceedings of the ACM Web Conference 2022"
  },
  "Deep Sets": {
    "zh": "深度集合",
    "en": "Deep Sets"
  },
  "Advances in Neural Information Processing Systems": {
    "zh": "《神经信息处理系统进展》",
    "en": "Advances in Neural Information Processing Systems"
  },
  "## P1 进度大屏 — 2026-10-31 14:55 CET（已上线）": {
    "zh": "## P1 进度大屏 — 2026-10-31 14:55 CET（已上线）",
    "en": "## P1 Dashboard — 2026-10-31 14:55 CET (live)"
  },
  "- 服务：login006 127.0.0.1:18765，标准库 http.server（/usr/bin/python3 3.6），tmux 会话 dash + watchdog.sh（30s 健康检查自动拉起）+ crontab */5 与 @reboot 调 ensure.sh。": {
    "zh": "- 服务：login006 127.0.0.1:18765，标准库 http.server（/usr/bin/python3 3.6），tmux 会话 dash + watchdog.sh（30s 健康检查自动拉起）+ crontab */5 与 @reboot 调 ensure.sh。",
    "en": "- Service: login006 127.0.0.1:18765, standard-library http.server (/usr/bin/python3 3.6), tmux session dash + watchdog.sh (health checks and restart every 30s) + crontab */5 and @reboot invoking ensure.sh."
  },
  "- Mac 转发：ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel → http://127.0.0.1:18765/ ，已 curl 验证。": {
    "zh": "- Mac 转发：ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel → http://127.0.0.1:18765/ ，已 curl 验证。",
    "en": "- Mac forwarding: `ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel` to http://127.0.0.1:18765/; verified with curl. (Historical source record.)"
  },
  "- 数据约定见 tactics/dashboard/README.md（status/phases.json、runs/*/metrics.jsonl、logs/*.log、results/*.json）。": {
    "zh": "- 数据约定见 tactics/dashboard/README.md（status/phases.json、runs/*/metrics.jsonl、logs/*.log、results/*.json）。",
    "en": "- Data conventions: tactics/dashboard/README.md (status/phases.json, runs/*/metrics.jsonl, logs/*.log, results/*.json)."
  },
  "- 下一步：各阶段完成时更新 status/phases.json 和本文件。": {
    "zh": "- 下一步：各阶段完成时更新 status/phases.json 和本文件。",
    "en": "- Next: update status/phases.json and this file as each phase completes."
  },
  "## Direction change — 2026-10-31 (创奇)": {
    "zh": "## Direction change — 2026-10-31 (创奇)",
    "en": "## Direction change — 2026-10-31 (Chuangqi)"
  },
  "and 2021→2026 meta evolution; RQ5 measurable pre-goal 势 (history beyond current state) +": {
    "zh": "and 2021→2026 meta evolution; RQ5 measurable pre-goal 势 (history beyond current state) +",
    "en": "and 2021–2026 meta evolution; RQ5 measurable pre-goal potential (history beyond current state) +"
  },
  "## 2026-11-01 01:15 CET 状态": {
    "zh": "## 2026-11-01 01:15 CET 状态",
    "en": "## 2026-11-01 01:15 CET status"
  },
  "- 41105069 全量抽取 COMPLETED（46,793 replay）。41105106(P6.3)/41105107(RQ4) 因 5 个 replay 解码诊断 `live_share_below_50_percent` 触发检查而 FAILED。": {
    "zh": "- 41105069 全量抽取 COMPLETED（46,793 replay）。41105106(P6.3)/41105107(RQ4) 因 5 个 replay 解码诊断 `live_share_below_50_percent` 触发检查而 FAILED。",
    "en": "- 41105069 full extraction COMPLETED (46,793 replays). 41105106 (P6.3) / 41105107 (RQ4) FAILED because five replays triggered the `live_share_below_50_percent` decoding diagnostic."
  },
  "- 不合格：5 / 40,688 开发集 replay（0.012%；rlcs-22-23: 2，rlcs-2024: 3），不集中。上游清单 compact/decode_exclusions.json（副本 results/decode_exclusions_full.json）；screen.metadata_inventory 仅跳过清单内且失败原因精确匹配者，其余检查不放宽（ebf2753, 660cecb）。论文数据节需写明剔除 5 场。": {
    "zh": "- 不合格：5 / 40,688 开发集 replay（0.012%；rlcs-22-23: 2，rlcs-2024: 3），不集中。上游清单 compact/decode_exclusions.json（副本 results/decode_exclusions_full.json）；screen.metadata_inventory 仅跳过清单内且失败原因精确匹配者，其余检查不放宽（ebf2753, 660cecb）。论文数据节需写明剔除 5 场。",
    "en": "- Ineligible: 5 / 40,688 development replays (0.012%; rlcs-22-23: 2, rlcs-2024: 3), not concentrated. Upstream manifest: compact/decode_exclusions.json (copy: results/decode_exclusions_full.json); screen.metadata_inventory skips only listed replays with exactly matching failure reasons; other checks remain unchanged (ebf2753, 660cecb). The paper data section must disclose the five exclusions."
  },
  "- 备注：统计脚本读取了 2026 分片的元数据列（replay_id/解码状态），未读结果或数组数据。": {
    "zh": "- 备注：统计脚本读取了 2026 分片的元数据列（replay_id/解码状态），未读结果或数组数据。",
    "en": "- Note: the statistics script read metadata columns (replay_id / decoding status) from the 2026 shards, not outcomes or array data."
  },
  "- 运行中：41105126 P6.3 全量（32 核，--time 4h，medium 用 20 min）；41105127 RQ4 习惯全量（1 核，--time 2h，medium 用 6 min）。": {
    "zh": "- 运行中：41105126 P6.3 全量（32 核，--time 4h，medium 用 20 min）；41105127 RQ4 习惯全量（1 核，--time 2h，medium 用 6 min）。",
    "en": "- Running: 41105126 P6.3 full data (32 cores, --time 4h; medium took 20 min); 41105127 RQ4 full habits (1 core, --time 2h; medium took 6 min)."
  },
  "- 下一步：结果出来后写入论文“谁压/值不值”；收敛分析，不新增方向；论文结构、图、引用核实、编译 PDF；大屏由独立 Codex 修复，待逐页截图验收。": {
    "zh": "- 下一步：结果出来后写入论文“谁压/值不值”；收敛分析，不新增方向；论文结构、图、引用核实、编译 PDF；大屏由独立 Codex 修复，待逐页截图验收。",
    "en": "- Next: incorporate results into the paper sections on who pushes up and whether it is worthwhile; consolidate analyses without adding directions; complete paper structure, figures, citation checks and PDF compilation. A separate Codex session is fixing the dashboard, pending screenshot acceptance for every page."
  },
  "Spatio-Temporal Analysis of Team Sports": {
    "zh": "团队运动的时空分析",
    "en": "Spatio-Temporal Analysis of Team Sports"
  },
  "ACM Computing Surveys": {
    "zh": "《ACM 计算综述》",
    "en": "ACM Computing Surveys"
  },
  "Discovering Team Structures in Soccer from Spatiotemporal Data": {
    "zh": "从时空数据中发现足球团队结构",
    "en": "Discovering Team Structures in Soccer from Spatiotemporal Data"
  },
  "IEEE Transactions on Knowledge and Data Engineering": {
    "zh": "《IEEE 知识与数据工程汇刊》",
    "en": "IEEE Transactions on Knowledge and Data Engineering"
  },
  "Visual analysis of pressure in football": {
    "zh": "足球比赛中施压行为的可视分析",
    "en": "Visual analysis of pressure in football"
  },
  "Data Mining and Knowledge Discovery": {
    "zh": "《数据挖掘与知识发现》",
    "en": "Data Mining and Knowledge Discovery"
  },
  "Data-driven detection of counterpressing in professional football: A supervised machine learning task based on synchronized positional and event data with expert-based feature extraction": {
    "zh": "职业足球中反抢行为的数据驱动检测：基于同步位置与事件数据及专家特征提取的监督式机器学习任务",
    "en": "Data-driven detection of counterpressing in professional football: A supervised machine learning task based on synchronized positional and event data with expert-based feature extraction"
  },
  "Beyond Expected Goals": {
    "zh": "超越预期进球",
    "en": "Beyond Expected Goals"
  },
  "MIT Sloan Sports Analytics Conference": {
    "zh": "麻省理工学院斯隆体育分析会议",
    "en": "MIT Sloan Sports Analytics Conference"
  },
  "Actions Speak Louder than Goals: Valuing Player Actions in Soccer": {
    "zh": "行动胜于进球：评估足球球员动作的价值",
    "en": "Actions Speak Louder than Goals: Valuing Player Actions in Soccer"
  },
  "Proceedings of the 25th ACM SIGKDD International Conference on Knowledge Discovery & Data Mining": {
    "zh": "第 25 届 ACM SIGKDD 知识发现与数据挖掘国际会议论文集",
    "en": "Proceedings of the 25th ACM SIGKDD International Conference on Knowledge Discovery & Data Mining"
  },
  "Valuing Player Actions in Counter-Strike: Global Offensive": {
    "zh": "评估 Counter-Strike: Global Offensive 中玩家动作的价值",
    "en": "Valuing Player Actions in Counter-Strike: Global Offensive"
  },
  "2020 IEEE International Conference on Big Data (Big Data)": {
    "zh": "2020 年 IEEE 大数据国际会议",
    "en": "2020 IEEE International Conference on Big Data (Big Data)"
  },
  "TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2": {
    "zh": "TAGNet：用于职业 Counter-Strike 2 防守战术模式识别的时间注意力图网络",
    "en": "TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2"
  },
  "Bayesian Clustering of Player Styles for Multiplayer Games": {
    "zh": "多人游戏中玩家风格的贝叶斯聚类",
    "en": "Bayesian Clustering of Player Styles for Multiplayer Games"
  },
  "Proceedings of the AAAI Conference on Artificial Intelligence and Interactive Digital Entertainment": {
    "zh": "AAAI 人工智能与交互数字娱乐会议论文集",
    "en": "Proceedings of the AAAI Conference on Artificial Intelligence and Interactive Digital Entertainment"
  },
  "TS2Vec: Towards Universal Representation of Time Series": {
    "zh": "TS2Vec：迈向通用时间序列表征",
    "en": "TS2Vec: Towards Universal Representation of Time Series"
  },
  "Proceedings of the AAAI Conference on Artificial Intelligence": {
    "zh": "AAAI 人工智能会议论文集",
    "en": "Proceedings of the AAAI Conference on Artificial Intelligence"
  },
  "A Multiresolution Stochastic Process Model for Predicting Basketball Possession Outcomes": {
    "zh": "用于预测篮球控球回合结果的多分辨率随机过程模型",
    "en": "A Multiresolution Stochastic Process Model for Predicting Basketball Possession Outcomes"
  },
  "A framework for the fine-grained evaluation of the instantaneous expected value of soccer possessions": {
    "zh": "细粒度评估足球控球瞬时预期价值的框架",
    "en": "A framework for the fine-grained evaluation of the instantaneous expected value of soccer possessions"
  },
  "Machine Learning": {
    "zh": "《机器学习》",
    "en": "Machine Learning"
  },
  "Using Big Data to Emulate a Target Trial When a Randomized Trial Is Not Available": {
    "zh": "无法开展随机试验时利用大数据模拟目标试验",
    "en": "Using Big Data to Emulate a Target Trial When a Randomized Trial Is Not Available"
  },
  "American Journal of Epidemiology": {
    "zh": "《美国流行病学杂志》",
    "en": "American Journal of Epidemiology"
  },
  "SoccerStories: A Kick-off for Visual Soccer Analysis": {
    "zh": "SoccerStories：足球可视分析的开端",
    "en": "SoccerStories: A Kick-off for Visual Soccer Analysis"
  },
  "IEEE Transactions on Visualization and Computer Graphics": {
    "zh": "《IEEE 可视化与计算机图形学汇刊》",
    "en": "IEEE Transactions on Visualization and Computer Graphics"
  },
  "Bring It to the Pitch: Combining Video and Movement Data to Enhance Team Sport Analysis": {
    "zh": "走进球场：结合视频与运动数据增强团队运动分析",
    "en": "Bring It to the Pitch: Combining Video and Movement Data to Enhance Team Sport Analysis"
  },
  "Visualizing the Spatio-Temporal Evolution of Gameplay using Storyline Visualization: A Study with League of Legends": {
    "zh": "利用故事线可视化呈现游戏过程的时空演变：以英雄联盟为例",
    "en": "Visualizing the Spatio-Temporal Evolution of Gameplay using Storyline Visualization: A Study with League of Legends"
  },
  "Proceedings of the ACM on Human-Computer Interaction": {
    "zh": "ACM 人机交互论文集",
    "en": "Proceedings of the ACM on Human-Computer Interaction"
  },
  "Identifying Team Style in Soccer Using Formations Learned from Spatiotemporal Tracking Data": {
    "zh": "利用从时空跟踪数据中学习的阵型识别足球团队风格",
    "en": "Identifying Team Style in Soccer Using Formations Learned from Spatiotemporal Tracking Data"
  },
  "2014 IEEE International Conference on Data Mining Workshop": {
    "zh": "2014 年 IEEE 数据挖掘国际会议研讨会",
    "en": "2014 IEEE International Conference on Data Mining Workshop"
  },
  "Strategies for Pulling the Goalie in Hockey": {
    "zh": "冰球比赛撤下守门员的策略",
    "en": "Strategies for Pulling the Goalie in Hockey"
  },
  "The American Statistician": {
    "zh": "《美国统计学家》",
    "en": "The American Statistician"
  },
  "Behavior under social pressure: Empty Italian stadiums and referee bias": {
    "zh": "社会压力下的行为：意大利空场比赛与裁判偏差",
    "en": "Behavior under social pressure: Empty Italian stadiums and referee bias"
  },
  "Economics Letters": {
    "zh": "《经济学快报》",
    "en": "Economics Letters"
  },
  "Causal effects of an absent crowd on performances and refereeing decisions during Covid-19": {
    "zh": "新冠疫情期间观众缺席对比赛表现与裁判判罚的因果影响",
    "en": "Causal effects of an absent crowd on performances and refereeing decisions during Covid-19"
  },
  "The central role of the propensity score in observational studies for causal effects": {
    "zh": "倾向评分在因果效应观察性研究中的核心作用",
    "en": "The central role of the propensity score in observational studies for causal effects"
  },
  "Biometrika": {
    "zh": "《生物统计》",
    "en": "Biometrika"
  },
  "Extracted full-data paper results": {
    "zh": "论文全量结果摘录",
    "en": "Extracted full-data paper results"
  },
  "Existing research outputs are copied at their original precision without recalculating statistics. A raw fit status is not a passed test; q values retain the JSON values, reported in the paper at the permutation resolution floor.": {
    "zh": "仅摘录既有研究输出，保留原始精度，不重新计算统计量。原始拟合状态不等同于通过检验；q 值保留 JSON 原值，论文按置换分辨率下限报告。",
    "en": "Existing research outputs are copied at their original precision without recalculating statistics. A raw fit status is not a passed test; q values retain the JSON values, reported in the paper at the permutation resolution floor."
  },
  "RQ4 full-data adjacent-season habit stability": {
    "zh": "RQ4 全量相邻赛季习惯稳定性",
    "en": "RQ4 full-data adjacent-season habit stability"
  },
  "Development seasons: 2021–22 through 2025": {
    "zh": "开发季：2021–22 至 2025",
    "en": "Development seasons: 2021–22 through 2025"
  },
  "paper2/fullres/results/rq4_habits_full/rq4_habits.json": {
    "zh": "paper2/fullres/results/rq4_habits_full/rq4_habits.json",
    "en": "paper2/fullres/results/rq4_habits_full/rq4_habits.json"
  },
  "P6.3 full-data roster push-up stability": {
    "zh": "P6.3 全量阵容前压稳定性",
    "en": "P6.3 full-data roster push-up stability"
  },
  "Training seasons versus 2025 validation": {
    "zh": "训练季与 2025 验证季",
    "en": "Training seasons versus 2025 validation"
  },
  "The source output marks finding=false. Eligible-roster support is insufficient; the paper retains this analysis in the supplement without claiming a stability finding.": {
    "zh": "原始输出标记 finding=false；合格阵容支持不足，论文仅保留在补充材料，不能作为稳定性发现。",
    "en": "The source output marks finding=false. Eligible-roster support is insufficient; the paper retains this analysis in the supplement without claiming a stability finding."
  },
  "day1/results/pushup_heterogeneity.json": {
    "zh": "day1/results/pushup_heterogeneity.json",
    "en": "day1/results/pushup_heterogeneity.json"
  },
  "Roster random slopes: training seasons → 2025": {
    "zh": "阵容随机斜率：训练季 → 2025",
    "en": "Roster random slopes: training seasons → 2025"
  },
  "Last-man share · 21-22 → 22-23": {
    "zh": "最后一人占比 · 21-22 → 22-23",
    "en": "Last-man share · 21-22 → 22-23"
  },
  "Last-man · 21-22→22-23": {
    "zh": "最后一人 · 21-22→22-23",
    "en": "Last-man · 21-22→22-23"
  },
  "Own-goal depth · 21-22 → 22-23": {
    "zh": "距己方球门深度 · 21-22 → 22-23",
    "en": "Own-goal depth · 21-22 → 22-23"
  },
  "Own-goal · 21-22→22-23": {
    "zh": "球门深度 · 21-22→22-23",
    "en": "Own-goal · 21-22→22-23"
  },
  "Own-third depth · 21-22 → 22-23": {
    "zh": "本方后场三分之一区域内深度 · 21-22 → 22-23",
    "en": "Own-third depth · 21-22 → 22-23"
  },
  "Own-third · 21-22→22-23": {
    "zh": "后场深度 · 21-22→22-23",
    "en": "Own-third · 21-22→22-23"
  },
  "Mean boost · 21-22 → 22-23": {
    "zh": "平均加速资源 · 21-22 → 22-23",
    "en": "Mean boost · 21-22 → 22-23"
  },
  "Mean boost · 21-22→22-23": {
    "zh": "平均加速资源 · 21-22→22-23",
    "en": "Mean boost · 21-22→22-23"
  },
  "Supersonic share · 21-22 → 22-23": {
    "zh": "超音速占比 · 21-22 → 22-23",
    "en": "Supersonic share · 21-22 → 22-23"
  },
  "Supersonic · 21-22→22-23": {
    "zh": "超音速占比 · 21-22→22-23",
    "en": "Supersonic · 21-22→22-23"
  },
  "Ball-proximity share · 21-22 → 22-23": {
    "zh": "近球占比 · 21-22 → 22-23",
    "en": "Ball-proximity share · 21-22 → 22-23"
  },
  "Ball proximity · 21-22→22-23": {
    "zh": "近球占比 · 21-22→22-23",
    "en": "Ball proximity · 21-22→22-23"
  },
  "Aerial share · 21-22 → 22-23": {
    "zh": "空中占比 · 21-22 → 22-23",
    "en": "Aerial share · 21-22 → 22-23"
  },
  "Aerial · 21-22→22-23": {
    "zh": "空中占比 · 21-22→22-23",
    "en": "Aerial · 21-22→22-23"
  },
  "Rotation-back speed · 21-22 → 22-23": {
    "zh": "回防速度 · 21-22 → 22-23",
    "en": "Rotation-back speed · 21-22 → 22-23"
  },
  "Rotation back · 21-22→22-23": {
    "zh": "回防速度 · 21-22→22-23",
    "en": "Rotation back · 21-22→22-23"
  },
  "Last-man share · 22-23 → 2024": {
    "zh": "最后一人占比 · 22-23 → 2024",
    "en": "Last-man share · 22-23 → 2024"
  },
  "Last-man · 22-23→2024": {
    "zh": "最后一人 · 22-23→2024",
    "en": "Last-man · 22-23→2024"
  },
  "Own-goal depth · 22-23 → 2024": {
    "zh": "距己方球门深度 · 22-23 → 2024",
    "en": "Own-goal depth · 22-23 → 2024"
  },
  "Own-goal · 22-23→2024": {
    "zh": "球门深度 · 22-23→2024",
    "en": "Own-goal · 22-23→2024"
  },
  "Own-third depth · 22-23 → 2024": {
    "zh": "本方后场三分之一区域内深度 · 22-23 → 2024",
    "en": "Own-third depth · 22-23 → 2024"
  },
  "Own-third · 22-23→2024": {
    "zh": "后场深度 · 22-23→2024",
    "en": "Own-third · 22-23→2024"
  },
  "Mean boost · 22-23 → 2024": {
    "zh": "平均加速资源 · 22-23 → 2024",
    "en": "Mean boost · 22-23 → 2024"
  },
  "Mean boost · 22-23→2024": {
    "zh": "平均加速资源 · 22-23→2024",
    "en": "Mean boost · 22-23→2024"
  },
  "Supersonic share · 22-23 → 2024": {
    "zh": "超音速占比 · 22-23 → 2024",
    "en": "Supersonic share · 22-23 → 2024"
  },
  "Supersonic · 22-23→2024": {
    "zh": "超音速占比 · 22-23→2024",
    "en": "Supersonic · 22-23→2024"
  },
  "Ball-proximity share · 22-23 → 2024": {
    "zh": "近球占比 · 22-23 → 2024",
    "en": "Ball-proximity share · 22-23 → 2024"
  },
  "Ball proximity · 22-23→2024": {
    "zh": "近球占比 · 22-23→2024",
    "en": "Ball proximity · 22-23→2024"
  },
  "Aerial share · 22-23 → 2024": {
    "zh": "空中占比 · 22-23 → 2024",
    "en": "Aerial share · 22-23 → 2024"
  },
  "Aerial · 22-23→2024": {
    "zh": "空中占比 · 22-23→2024",
    "en": "Aerial · 22-23→2024"
  },
  "Rotation-back speed · 22-23 → 2024": {
    "zh": "回防速度 · 22-23 → 2024",
    "en": "Rotation-back speed · 22-23 → 2024"
  },
  "Rotation back · 22-23→2024": {
    "zh": "回防速度 · 22-23→2024",
    "en": "Rotation back · 22-23→2024"
  },
  "Last-man share · 2024 → 2025": {
    "zh": "最后一人占比 · 2024 → 2025",
    "en": "Last-man share · 2024 → 2025"
  },
  "Last-man · 2024→2025": {
    "zh": "最后一人 · 2024→2025",
    "en": "Last-man · 2024→2025"
  },
  "Own-goal depth · 2024 → 2025": {
    "zh": "距己方球门深度 · 2024 → 2025",
    "en": "Own-goal depth · 2024 → 2025"
  },
  "Own-goal · 2024→2025": {
    "zh": "球门深度 · 2024→2025",
    "en": "Own-goal · 2024→2025"
  },
  "Own-third depth · 2024 → 2025": {
    "zh": "本方后场三分之一区域内深度 · 2024 → 2025",
    "en": "Own-third depth · 2024 → 2025"
  },
  "Own-third · 2024→2025": {
    "zh": "后场深度 · 2024→2025",
    "en": "Own-third · 2024→2025"
  },
  "Mean boost · 2024 → 2025": {
    "zh": "平均加速资源 · 2024 → 2025",
    "en": "Mean boost · 2024 → 2025"
  },
  "Mean boost · 2024→2025": {
    "zh": "平均加速资源 · 2024→2025",
    "en": "Mean boost · 2024→2025"
  },
  "Supersonic share · 2024 → 2025": {
    "zh": "超音速占比 · 2024 → 2025",
    "en": "Supersonic share · 2024 → 2025"
  },
  "Supersonic · 2024→2025": {
    "zh": "超音速占比 · 2024→2025",
    "en": "Supersonic · 2024→2025"
  },
  "Ball-proximity share · 2024 → 2025": {
    "zh": "近球占比 · 2024 → 2025",
    "en": "Ball-proximity share · 2024 → 2025"
  },
  "Ball proximity · 2024→2025": {
    "zh": "近球占比 · 2024→2025",
    "en": "Ball proximity · 2024→2025"
  },
  "Aerial share · 2024 → 2025": {
    "zh": "空中占比 · 2024 → 2025",
    "en": "Aerial share · 2024 → 2025"
  },
  "Aerial · 2024→2025": {
    "zh": "空中占比 · 2024→2025",
    "en": "Aerial · 2024→2025"
  },
  "Rotation-back speed · 2024 → 2025": {
    "zh": "回防速度 · 2024 → 2025",
    "en": "Rotation-back speed · 2024 → 2025"
  },
  "Rotation back · 2024→2025": {
    "zh": "回防速度 · 2024→2025",
    "en": "Rotation back · 2024→2025"
  },
  "## 2026-11-01 03:15 CET 更新": {
    "zh": "## 2026-11-01 03:15 CET 更新",
    "en": "## 2026-11-01 03:15 CET update"
  },
  "- P6.3 全量（41105126）COMPLETED：bootstrap 2000/2000（fit 20000），输出 results/pushup_heterogeneity.json。roster 跨赛季稳定性比较仅 n=4 单元（rho=-0.80），不足以作为发现，写入补充材料。": {
    "zh": "- P6.3 全量（41105126）COMPLETED：bootstrap 2000/2000（fit 20000），输出 results/pushup_heterogeneity.json。roster 跨赛季稳定性比较仅 n=4 单元（rho=-0.80），不足以作为发现，写入补充材料。",
    "en": "- Full-scale P6.3 (41105126) COMPLETED: bootstrap 2000/2000 (fit 20000); output: results/pushup_heterogeneity.json. The across-season roster stability comparison has only n=4 units (rho=-0.80), insufficient to support a finding; included in the supplement."
  },
  "- RQ4 全量（41105127）COMPLETED：results/rq4_habits_full；n=461 player-season 对，示例 rho 0.531/0.638/0.664/0.759，24 个相邻赛季相关全部为正（rho 0.45–0.84，BH q<0.05），已写入论文正文。": {
    "zh": "- RQ4 全量（41105127）COMPLETED：results/rq4_habits_full；n=461 player-season 对，示例 rho 0.531/0.638/0.664/0.759，24 个相邻赛季相关全部为正（rho 0.45–0.84，BH q<0.05），已写入论文正文。",
    "en": "- Full-scale RQ4 (41105127) COMPLETED: results/rq4_habits_full; n=461 player-season pairs, example rho values 0.531/0.638/0.664/0.759. All 24 adjacent-season correlations are positive (rho 0.45–0.84, BH q<0.05); incorporated into the main manuscript."
  },
  "- P4 全量（41105136@64G, 41105156@192G）与 P6.4 全量（41105139, 41105157）均 OUT_OF_MEMORY（约 23 min），未再重提；论文使用 medium 结果并在补充注明。": {
    "zh": "- P4 全量（41105136@64G, 41105156@192G）与 P6.4 全量（41105139, 41105157）均 OUT_OF_MEMORY（约 23 min），未再重提；论文使用 medium 结果并在补充注明。",
    "en": "- Full-scale P4 (41105136@64G, 41105156@192G) and full-scale P6.4 (41105139, 41105157) all ended OUT_OF_MEMORY (approximately 23 min); no further resubmissions. The paper uses medium-sample results and notes this in the supplement."
  },
  "- 论文：重写版（Codex 提交 7f9cd5a，Mac 快照）正文 7 页 + 补充 8 页；正在按统一风格（STIX 字体、Okabe-Ito、IEEE 尺寸）重做全部数据图。": {
    "zh": "- 论文：重写版（Codex 提交 7f9cd5a，Mac 快照）正文 7 页 + 补充 8 页；正在按统一风格（STIX 字体、Okabe-Ito、IEEE 尺寸）重做全部数据图。",
    "en": "- Paper: the rewritten version (Codex commit 7f9cd5a, Mac snapshot) has 7 main-text pages + 8 supplement pages. All data figures are being redrawn in a consistent style (STIX fonts, Okabe-Ito palette, IEEE dimensions)."
  },
  "- 空间可视化抽取：41105169、41105180 因输出路径守卫失败（目录名含 2026 / 非允许路径），41105191 已用 paper/figscripts/data/viz/full 重提。": {
    "zh": "- 空间可视化抽取：41105169、41105180 因输出路径守卫失败（目录名含 2026 / 非允许路径），41105191 已用 paper/figscripts/data/viz/full 重提。",
    "en": "- Spatial visualization extraction: 41105169 and 41105180 failed the output-path guard (directory name contains 2026 / path is not allowed); resubmitted as 41105191 with paper/figscripts/data/viz/full."
  },
  "## 2026-11-01 04:35 CET 更新": {
    "zh": "## 2026-11-01 04:35 CET 更新",
    "en": "## 2026-11-01 04:35 CET update"
  },
  "- 论文图第二轮（Codex fc1f46d）：Fig.1/2 合并为脚本矢量框架+场地示意（L(t)、D(t)、g(t)、非开球者终点）；Fig.3 单栏；Fig.4 分隔线、空心标记、压缩高度；Fig.5 单色单栏三标记；Fig.6 场地轮廓、等比例、共用灰度时间条；全部 Times 字体、Okabe-Ito 固定含义、原尺寸 include。正文 7 页 + 补充 9 页。": {
    "zh": "- 论文图第二轮（Codex fc1f46d）：Fig.1/2 合并为脚本矢量框架+场地示意（L(t)、D(t)、g(t)、非开球者终点）；Fig.3 单栏；Fig.4 分隔线、空心标记、压缩高度；Fig.5 单色单栏三标记；Fig.6 场地轮廓、等比例、共用灰度时间条；全部 Times 字体、Okabe-Ito 固定含义、原尺寸 include。正文 7 页 + 补充 9 页。",
    "en": "- Second figure revision (Codex fc1f46d): Fig.1/2 merged into a scripted vector framework and pitch schematic (L(t), D(t), g(t), non-kicker endpoints); Fig.3 uses one column; Fig.4 has separators, hollow markers and reduced height; Fig.5 uses one color, one column and three markers; Fig.6 has pitch outlines, equal aspect ratio and a shared grayscale time bar. Times fonts throughout, fixed Okabe-Ito color meanings, figures included at native size. Main text: 7 pages + supplement: 9 pages."
  },
  "- 已提交 41109756（paper-curves）：开发季 compact 上按既定 L(t) 定义计算剩余时间×比分状态的平均深度曲线与 bootstrap CI，用于替换 Fig.3；仅扫描 rlcs-21-22..rlcs-2025。": {
    "zh": "- 已提交 41109756（paper-curves）：开发季 compact 上按既定 L(t) 定义计算剩余时间×比分状态的平均深度曲线与 bootstrap CI，用于替换 Fig.3；仅扫描 rlcs-21-22..rlcs-2025。",
    "en": "- Submitted 41109756 (paper-curves): compute mean-depth curves and bootstrap CI by time remaining and score state from development-season compact data, using the established L(t) definition, to replace Fig.3; scan only rlcs-21-22..rlcs-2025."
  },
  "- P4/P6.4 全量两次 OOM，未重提，论文用 medium。": {
    "zh": "- P4/P6.4 全量两次 OOM，未重提，论文用 medium。",
    "en": "- Full-scale P4/P6.4 each ran out of memory twice; no resubmissions. The paper uses medium-sample results."
  },
  "## 2026-11-01 05:05 CET 更新": {
    "zh": "## 2026-11-01 05:05 CET 更新",
    "en": "## 2026-11-01 05:05 CET update"
  },
  "- 41109756（paper-curves）COMPLETED（15 min）：四个开发季 165 个 shard、2000 次 bootstrap 核验通过。Fig.3 改为 2025 验证季剩余时间 vs 平均深度 L(t) 的 leading/tied/trailing 曲线（95% series bootstrap 带，60 s late window），轴内标注调整交互 +453.4 [420.3, 485.2] uu；原六项估计移至补充 S7。Codex 提交 e47f417。正文 7 页 + 补充 9 页。": {
    "zh": "- 41109756（paper-curves）COMPLETED（15 min）：四个开发季 165 个 shard、2000 次 bootstrap 核验通过。Fig.3 改为 2025 验证季剩余时间 vs 平均深度 L(t) 的 leading/tied/trailing 曲线（95% series bootstrap 带，60 s late window），轴内标注调整交互 +453.4 [420.3, 485.2] uu；原六项估计移至补充 S7。Codex 提交 e47f417。正文 7 页 + 补充 9 页。",
    "en": "- 41109756 (paper-curves) COMPLETED (15 min): verification passed for 165 shards across four development seasons and 2000 bootstrap replicates. Fig.3 now shows leading/tied/trailing mean-depth L(t) curves against time remaining for the 2025 validation season (95% series-bootstrap bands, 60 s late window), with the adjusted interaction +453.4 [420.3, 485.2] uu annotated inside the axes. The original six estimates moved to supplement S7. Codex commit e47f417. Main text: 7 pages + supplement: 9 pages."
  },
  "## 2026-11-01 05:35 CET 更新": {
    "zh": "## 2026-11-01 05:35 CET 更新",
    "en": "## 2026-11-01 05:35 CET update"
  },
  "- 最终润色与第三轮图审阅（Codex 177e94f、2fa3904）：Fig.1 重做为 pipeline + (a)(b)(c) 三问题示意 teaser；Fig.2 曲线删图内小标题并入图注；Fig.3 kickoff 数值移至右侧列；Fig.5 图例紧凑、习惯名与表 III 一致；Fig.6 场地轮廓+比例尺；全文千位分隔符 55 处修复、newtx 字体统一；全文润色，数字与结论强度不变。正文 7 页 + 补充 9 页，逐页渲染检查通过。": {
    "zh": "- 最终润色与第三轮图审阅（Codex 177e94f、2fa3904）：Fig.1 重做为 pipeline + (a)(b)(c) 三问题示意 teaser；Fig.2 曲线删图内小标题并入图注；Fig.3 kickoff 数值移至右侧列；Fig.5 图例紧凑、习惯名与表 III 一致；Fig.6 场地轮廓+比例尺；全文千位分隔符 55 处修复、newtx 字体统一；全文润色，数字与结论强度不变。正文 7 页 + 补充 9 页，逐页渲染检查通过。",
    "en": "- Final polish and third figure review (Codex 177e94f, 2fa3904): Fig.1 rebuilt as a pipeline and (a)(b)(c) schematic teaser for the three questions; Fig.2 internal curve subtitle moved to the caption; Fig.3 kickoff values moved to a right-hand column; Fig.5 legend tightened and habit names aligned with Table III; Fig.6 has pitch outlines and a scale bar. Fixed 55 thousands separators throughout and standardized newtx fonts; polished the manuscript without changing numbers or the strength of conclusions. Main text: 7 pages + supplement: 9 pages; rendered pages passed review."
  },
  "## 2026-11-01 06:30 CET 更新": {
    "zh": "## 2026-11-01 06:30 CET 更新",
    "en": "## 2026-11-01 06:30 CET update"
  },
  "- 第四轮图审（Codex 4ac4366）：Fig.1 teaser 放大场地元素、g(t)/球/非开球者固定色、(c) 实色区分保持/交换排名、删统计术语；Fig.3 开球森林图 pooled 实心/分箱空心、表头对齐；Fig.4 图例上方一行、偏移对称；Fig.5 队友轨迹加深、统一比例尺与单一时间编码；全部图字体改为 TeX Gyre Termes（pdffonts 核查）。正文 7 页 + 补充 9 页，数字与结论不变。": {
    "zh": "- 第四轮图审（Codex 4ac4366）：Fig.1 teaser 放大场地元素、g(t)/球/非开球者固定色、(c) 实色区分保持/交换排名、删统计术语；Fig.3 开球森林图 pooled 实心/分箱空心、表头对齐；Fig.4 图例上方一行、偏移对称；Fig.5 队友轨迹加深、统一比例尺与单一时间编码；全部图字体改为 TeX Gyre Termes（pdffonts 核查）。正文 7 页 + 补充 9 页，数字与结论不变。",
    "en": "- Fourth figure review (Codex 4ac4366): Fig.1 teaser uses larger pitch elements, fixed colors for g(t)/ball/non-kickers, solid colors distinguishing retained/swapped ranks in (c), and no statistical terminology; Fig.3 kickoff forest plot uses filled pooled markers and hollow bin markers, with aligned headers; Fig.4 legend is a single row above the plot, with symmetric offsets; Fig.5 teammate trajectories are darker, with a consistent scale bar and a single time encoding. All figure fonts changed to TeX Gyre Termes (checked with pdffonts). Main text: 7 pages + supplement: 9 pages; numbers and conclusions unchanged."
  },
  "## 2026-11-01 06:45 CET 更新": {
    "zh": "## 2026-11-01 06:45 CET 更新",
    "en": "## 2026-11-01 06:45 CET update"
  },
  "- 收尾小修（Codex 343fe61）：Fig.3 开球森林图与数值列留白压缩；Fig.5 恢复球终点圆圈并入图例。正文 7 页 + 补充 9 页，16 页已人工逐页检查。": {
    "zh": "- 收尾小修（Codex 343fe61）：Fig.3 开球森林图与数值列留白压缩；Fig.5 恢复球终点圆圈并入图例。正文 7 页 + 补充 9 页，16 页已人工逐页检查。",
    "en": "- Final small fixes (Codex 343fe61): reduced whitespace between the Fig.3 kickoff forest plot and its value column; restored ball-endpoint circles in Fig.5 and added them to the legend. Main text: 7 pages + supplement: 9 pages; all 16 pages manually reviewed."
  },
  "## 2026-11-01 06:55 CET 更新": {
    "zh": "## 2026-11-01 06:55 CET 更新",
    "en": "## 2026-11-01 06:55 CET update"
  },
  "- 补充材料修补（Codex 6e56b34）：习惯名全文统一为表 III 名称（S1/S5 等）；S9 热图提高打印对比度（颜色标尺变换写入图注，数据不变）。": {
    "zh": "- 补充材料修补（Codex 6e56b34）：习惯名全文统一为表 III 名称（S1/S5 等）；S9 热图提高打印对比度（颜色标尺变换写入图注，数据不变）。",
    "en": "- Supplement fixes (Codex 6e56b34): habit names standardized throughout to match Table III (S1/S5, etc.); improved print contrast in the S9 heatmap (color-scale transformation documented in the caption; data unchanged)."
  },
  "## 2026-11-01 07:45 CET 更新": {
    "zh": "## 2026-11-01 07:45 CET 更新",
    "en": "## 2026-11-01 07:45 CET update"
  },
  "- 08:00 汇报基线：tag baseline-0800 = bace727（已推送）。": {
    "zh": "- 08:00 汇报基线：tag baseline-0800 = bace727（已推送）。",
    "en": "- Baseline for the 08:00 report: tag baseline-0800 = bace727 (pushed)."
  },
  "- 第五轮图审（Codex 1e7cd66、5d55fb9）：Fig.5 共同包围盒裁剪、单一灰度时间编码、比例尺、球终点圆圈；Fig.3 数值列对齐与 Pooled 分隔；Fig.4 marker 图例、n 移入图注、偏移加大；Fig.1 元素放大与线宽统一；q 值按 JSON 统一为 q < 0.0005（全部 24 个 q=1/2001，为 2000 次置换的下限）；结果段限定集中到 Limitations，无因果词。正文 7 页 + 补充 9 页，人工逐页检查。": {
    "zh": "- 第五轮图审（Codex 1e7cd66、5d55fb9）：Fig.5 共同包围盒裁剪、单一灰度时间编码、比例尺、球终点圆圈；Fig.3 数值列对齐与 Pooled 分隔；Fig.4 marker 图例、n 移入图注、偏移加大；Fig.1 元素放大与线宽统一；q 值按 JSON 统一为 q < 0.0005（全部 24 个 q=1/2001，为 2000 次置换的下限）；结果段限定集中到 Limitations，无因果词。正文 7 页 + 补充 9 页，人工逐页检查。",
    "en": "- Fifth figure review (Codex 1e7cd66, 5d55fb9): Fig.5 uses a common bounding-box crop, a single grayscale time encoding, a scale bar and ball-endpoint circles; Fig.3 value column aligned and Pooled separated; Fig.4 has a marker legend, n moved to the caption and larger offsets; Fig.1 elements enlarged and line widths standardized. q values harmonized with JSON as q < 0.0005 (all 24 q=1/2001, the floor from 2000 permutations); qualifications from the Results section consolidated in Limitations, with no causal wording. Main text: 7 pages + supplement: 9 pages; all pages manually reviewed."
  },
  "发现已收敛：全量前压交互 +453.4 uu [420.3,485.2]；RQ4 的 24 个相邻赛季相关均为正（ρ 0.45–0.84）。P6.3 阵容稳定性仅 n=4、ρ=-0.80，不作为发现。P4 全量 41105136/41105156 与 P6.4 全量 41105139/41105157 各两次 OOM，未重提；论文使用 medium 结果。控球条件化后净进球差 +0.086 [0.020,0.177]，因果门控仍失败，仅作关联。": {
    "zh": "发现已收敛：全量前压交互 +453.4 uu [420.3,485.2]；RQ4 的 24 个相邻赛季相关均为正（ρ 0.45–0.84）。P6.3 阵容稳定性仅 n=4、ρ=-0.80，不作为发现。P4 全量 41105136/41105156 与 P6.4 全量 41105139/41105157 各两次 OOM，未重提；论文使用 medium 结果。控球条件化后净进球差 +0.086 [0.020,0.177]，因果门控仍失败，仅作关联。",
    "en": "Findings consolidated: the full-sample push-up interaction is +453.4 uu [420.3,485.2]; all 24 adjacent-season RQ4 correlations are positive (ρ 0.45–0.84). P6.3 roster stability has only n=4 and ρ=-0.80, so it is not a finding. Full P4 jobs 41105136/41105156 and full P6.4 jobs 41105139/41105157 each ended OOM twice and were not resubmitted; the paper uses medium results. Possession-conditioned net goal difference is +0.086 [0.020,0.177], with failed causal gates; interpretation remains associational."
  },
  "finished 为 PROGRESS 首次记录分析收敛的时间；图文修订继续归入论文阶段。": {
    "zh": "finished 为 PROGRESS 首次记录分析收敛的时间；图文修订继续归入论文阶段。",
    "en": "The finished timestamp is the first PROGRESS entry documenting analysis consolidation; subsequent figure and text revisions belong to the manuscript phase."
  },
  "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 2d041a4，本地论文源 HEAD 7c3e20c。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。": {
    "zh": "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 2d041a4，本地论文源 HEAD 7c3e20c。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。",
    "en": "Prepared for IEEE Transactions on Games; 7 main-text pages and 9 supplementary pages have been reviewed page by page, and manuscript revision is in progress. Latest cluster commit: 2d041a4; local manuscript-source HEAD: 7c3e20c. The q-value honesty correction states that all 24 RQ4 BH q values are at the floor of 2,000 permutations: q≤1/2001≈0.0005 in the text and caption, and BH q<0.001 in the abstract. After two OOM failures each, full P4/P6.4 use medium results with limitations recorded in the supplement; no causal claims are made."
  },
  "started 取 PROGRESS 首个明确带时间的论文记录（2026-10-31 21:00 CET），并非另行估计的实际开工时刻。": {
    "zh": "started 取 PROGRESS 首个明确带时间的论文记录（2026-10-31 21:00 CET），并非另行估计的实际开工时刻。",
    "en": "The started timestamp uses the first explicitly timed manuscript entry in PROGRESS (2026-10-31 21:00 CET), rather than an inferred actual start time."
  },
  "PROGRESS.md: 2026-11-01 03:15 CET, 05:05 CET; 2026-10-31 22:55 CET": {
    "zh": "PROGRESS.md: 2026-11-01 03:15 CET, 05:05 CET; 2026-10-31 22:55 CET",
    "en": "PROGRESS.md: 2026-11-01 03:15 CET, 05:05 CET; 2026-10-31 22:55 CET"
  },
  "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4": {
    "zh": "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4",
    "en": "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4"
  },
  "全量末位前压交互（uu）": {
    "zh": "全量末位前压交互（uu）",
    "en": "Full-sample last-man push-up interaction (uu)"
  },
  "前压交互的验证系列赛": {
    "zh": "前压交互的验证系列赛",
    "en": "Validation series for the push-up interaction"
  },
  "全量开球 K1：落后−领先（uu）": {
    "zh": "全量开球 K1：落后−领先（uu）",
    "en": "Full kickoff K1: trailing−leading (uu)"
  },
  "相邻赛季习惯相关数": {
    "zh": "相邻赛季习惯相关数",
    "en": "Adjacent-season habit correlations"
  },
  "全量习惯稳定性 Spearman ρ 范围": {
    "zh": "全量习惯稳定性 Spearman ρ 范围",
    "en": "Full-sample habit stability: Spearman ρ range"
  },
  "全部 BH q 位于置换下限": {
    "zh": "全部 BH q 位于置换下限",
    "en": "All BH q values at the permutation floor"
  },
  "0.45–0.84": {
    "zh": "0.45–0.84",
    "en": "0.45–0.84"
  },
  "≤1/2001": {
    "zh": "≤1/2001",
    "en": "≤1/2001"
  },
  "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction; paper2/paper/main.tex abstract": {
    "zh": "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction; paper2/paper/main.tex abstract",
    "en": "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction; paper2/paper/main.tex abstract"
  },
  "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction.n_series": {
    "zh": "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction.n_series",
    "en": "paper2/fullres/results/prereg-full.q9X1KJYu/p6-variants.wq3lqisF/p6_variants.json # contrasts.p6_1_trailing_minus_leading_interaction.n_series"
  },
  "paper2/fullres/results/prereg-full.q9X1KJYu/p62.8NxjjUNm/results/p6_kickoff.json # K1.pooled; paper2/paper/main.tex abstract": {
    "zh": "paper2/fullres/results/prereg-full.q9X1KJYu/p62.8NxjjUNm/results/p6_kickoff.json # K1.pooled; paper2/paper/main.tex abstract",
    "en": "paper2/fullres/results/prereg-full.q9X1KJYu/p62.8NxjjUNm/results/p6_kickoff.json # K1.pooled; paper2/paper/main.tex abstract"
  },
  "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall": {
    "zh": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall",
    "en": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall"
  },
  "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.rho": {
    "zh": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.rho",
    "en": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.rho"
  },
  "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.q_value": {
    "zh": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.q_value",
    "en": "paper2/paper/sections/results_who.tex; paper2/fullres/results/rq4_habits_full/rq4_habits.json # transitions[*].habits[*].overall.q_value"
  },
  "已从论文主线剪枝：中样本学习词表 excess 0.0028 [0.0022,0.0033]，手工为 0.0085；校正后的留出预测增益为学习 -0.0016、手工 +0.0009 bit/跳。未支持学习语法优于手工表示的主张。": {
    "zh": "已从论文主线剪枝：中样本学习词表 excess 0.0028 [0.0022,0.0033]，手工为 0.0085；校正后的留出预测增益为学习 -0.0016、手工 +0.0009 bit/跳。未支持学习语法优于手工表示的主张。",
    "en": "Pruned from the manuscript focus: medium-sample learned-vocabulary excess is 0.0028 [0.0022,0.0033], versus 0.0085 for handcrafted tokens. Corrected held-out predictive gains are -0.0016 and +0.0009 bits/jump, respectively. These results do not support a claim that learned grammar outperforms handcrafted representations."
  },
  "原始交接缺口方向未作为独立正文发现。相关的 P5 轮转延迟分析测量门控失败，完整结果仅保留在补充审计中；不能据此声称风险机制已得到验证。": {
    "zh": "原始交接缺口方向未作为独立正文发现。相关的 P5 轮转延迟分析测量门控失败，完整结果仅保留在补充审计中；不能据此声称风险机制已得到验证。",
    "en": "The original handoff-gap direction is not retained as a separate main-text finding. The related P5 rotation-latency analysis fails its measurement gate and is retained only for supplementary audit; it does not establish a risk mechanism."
  },
  "注册的无覆盖比例主检验未通过 Holm（原始 p=0.049，Holm 0.099）。论文采用的是另行审计后的末位前压关联：全量交互 +453.4 uu [420.3,485.2]、1,499 个系列赛，详见 P6.1；不能把该结果当作原主检验通过。": {
    "zh": "注册的无覆盖比例主检验未通过 Holm（原始 p=0.049，Holm 0.099）。论文采用的是另行审计后的末位前压关联：全量交互 +453.4 uu [420.3,485.2]、1,499 个系列赛，详见 P6.1；不能把该结果当作原主检验通过。",
    "en": "The registered uncovered-fraction primary test fails Holm adjustment (raw p=0.049, Holm 0.099). The paper instead reports the separately audited last-man positioning association: full-sample interaction +453.4 uu [420.3,485.2] across 1,499 series, detailed under P6.1; this does not turn the original primary test into a pass."
  },
  "论文保留可解释习惯的相邻赛季秩稳定性：全量 40,683 个开发 replay，24 个相关均为正，ρ 0.45–0.84，BH q≤1/2001（2,000 次置换下限）。换队友后的保留率仍不可估，不作身份可识别性或因果持久性结论。": {
    "zh": "论文保留可解释习惯的相邻赛季秩稳定性：全量 40,683 个开发 replay，24 个相关均为正，ρ 0.45–0.84，BH q≤1/2001（2,000 次置换下限）。换队友后的保留率仍不可估，不作身份可识别性或因果持久性结论。",
    "en": "The paper retains adjacent-season rank stability of interpretable habits: 40,683 development replays, 24 positive correlations, ρ 0.45–0.84, and BH q≤1/2001 at the floor of 2,000 permutations. Retention after teammate changes remains unestimable; no identity-retrieval or causal-persistence claim is made."
  },
  "未纳入当前论文的独立发现；研究已收敛到防守站位、开球站位与可解释习惯稳定性。该方向没有可据以宣称通过的最终结果，剪枝不等于已证明零效应。": {
    "zh": "未纳入当前论文的独立发现；研究已收敛到防守站位、开球站位与可解释习惯稳定性。该方向没有可据以宣称通过的最终结果，剪枝不等于已证明零效应。",
    "en": "Not retained as a separate finding in the current manuscript, which focuses on defensive positioning, kickoff positioning, and interpretable habit stability. No final result supports a pass for this direction; pruning does not establish a zero effect."
  },
  "开发流程已完成；后续分析沿用已审计的测量定义与开发/验证范围。全量开发分析剔除 5 个未通过解码检查的 replay，实际纳入范围以各分析来源为准。": {
    "zh": "开发流程已完成；后续分析沿用已审计的测量定义与开发/验证范围。全量开发分析剔除 5 个未通过解码检查的 replay，实际纳入范围以各分析来源为准。",
    "en": "The development workflow is complete; subsequent analyses use audited measurement definitions and development/validation scope. Full development analyses exclude 5 replays that failed decoding checks; actual inclusion is documented by each analysis."
  },
  "原阵容指纹确认检验支持不足；后续全量 P6.3 的阵容斜率稳定性也仅有 4 个合格阵容，ρ=-0.800、区间 [-1,1]。不能将选手习惯秩稳定性当作阵容稳定性证据。": {
    "zh": "原阵容指纹确认检验支持不足；后续全量 P6.3 的阵容斜率稳定性也仅有 4 个合格阵容，ρ=-0.800、区间 [-1,1]。不能将选手习惯秩稳定性当作阵容稳定性证据。",
    "en": "The original roster-fingerprint confirmatory test lacks support. Subsequent full P6.3 roster-slope stability also has only 4 eligible rosters, ρ=-0.800, and interval [-1,1]. Player habit rank stability is not evidence of roster stability."
  },
  "保留为词表开发选择记录；RQ1 学习轮转语法方向已从当前论文主线剪枝，原验证选择分数不是最终发现检验。": {
    "zh": "保留为词表开发选择记录；RQ1 学习轮转语法方向已从当前论文主线剪枝，原验证选择分数不是最终发现检验。",
    "en": "Retained as a vocabulary-development selection record. The RQ1 learned-rotation-grammar direction is pruned from the current manuscript focus; the original validation selection score is not a final finding test."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 横向补偿增益为 -89.01 每 1000 uu/秒创新对应的反向速度（uu/秒），q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 横向补偿增益为 -89.01 每 1000 uu/秒创新对应的反向速度（uu/秒），q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Lateral compensation gain is -89.01 opposite velocity (uu/s) per 1000 uu/s innovation, q=0.0015; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 前进历史相对后退历史的阵型宽度差为 8.44 uu，q=0.898；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 前进历史相对后退历史的阵型宽度差为 8.44 uu，q=0.898；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Formation-width difference for forward versus backward history is 8.44 uu, q=0.898; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 高脆弱性相对低脆弱性的失球概率差为 0.3765 个百分点，q=0.00514；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 高脆弱性相对低脆弱性的失球概率差为 0.3765 个百分点，q=0.00514；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Concession-probability difference for high versus low brittleness is 0.3765 percentage points, q=0.00514; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 对手历史相对队友历史的预测损失差为 0.0001194 比特/动作，q=0.376；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 对手历史相对队友历史的预测损失差为 0.0001194 比特/动作，q=0.376；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Prediction-loss difference for opponent versus teammate history is 0.0001194 bits/action, q=0.376; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 恰好一人上前的超额概率为 2.372 个百分点，q=0.109；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 恰好一人上前的超额概率为 2.372 个百分点，q=0.109；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess probability of exactly one player approaching is 2.372 percentage points, q=0.109; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 阵容旋转方向的分半相关为 0.2158 相关系数，q=0.0882；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 阵容旋转方向的分半相关为 0.2158 相关系数，q=0.0882；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Split-half correlation of roster circulation direction is 0.2158, q=0.0882; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 宽间距下进攻者模糊性的额外减速概率为 34.97 个百分点，q=0.244；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 宽间距下进攻者模糊性的额外减速概率为 34.97 个百分点，q=0.244；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional slowing probability from attacker ambiguity at wide spacing is 34.97 percentage points, q=0.244; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 低响应多样性相对高多样性的额外回撤距离为 -28.78 uu，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 低响应多样性相对高多样性的额外回撤距离为 -28.78 uu，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional backward excursion for low versus high response diversity is -28.78 uu, q=0.0015; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 追随防守带来的通道净宽变化为 141.6 uu，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 追随防守带来的通道净宽变化为 141.6 uu，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Lane-clearance change associated with following defenders is 141.6 uu, q=0.0015; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 停顿后的对手加速响应概率差为 0.1841 个百分点，q=0.565；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 停顿后的对手加速响应概率差为 0.1841 个百分点，q=0.565；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Difference in opponent acceleration-response probability after a pause is 0.1841 percentage points, q=0.565; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 贯通通道相对封闭通道的失球概率差为 0.8971 个百分点，q=0.109；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 贯通通道相对封闭通道的失球概率差为 0.8971 个百分点，q=0.109；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Concession-probability difference for connected versus closed corridors is 0.8971 percentage points, q=0.109; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 失球前阵型面积残差的额外持续性为 -0.001378 相关系数差，q=0.764；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 失球前阵型面积残差的额外持续性为 -0.001378 相关系数差，q=0.764；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess persistence of formation-area residuals before conceding is -0.001378 in correlation difference, q=0.764; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 后排横向响应的额外放大增益为 -0.3057 倍增益，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 后排横向响应的额外放大增益为 -0.3057 倍增益，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Excess amplification gain of rear lateral response is -0.3057, q=0.0015; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 超出零模型的节拍调制概率为 0.4035 个百分点/0.1秒，q=0.0882；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 超出零模型的节拍调制概率为 0.4035 个百分点/0.1秒，q=0.0882；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Rhythmic probability modulation beyond the null is 0.4035 percentage points/0.1 seconds, q=0.0882; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 打破重复路线后的额外响应延迟为 -0.08444 秒，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 打破重复路线后的额外响应延迟为 -0.08444 秒，q=0.0015；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Additional response latency after breaking a repeated route is -0.08444 seconds, q=0.0015; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 队形稀有度每翻倍的推进距离变化为 57.92 uu/稀有度翻倍，q=0.063；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 队形稀有度每翻倍的推进距离变化为 57.92 uu/稀有度翻倍，q=0.063；证据较弱。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Change in forward progress per doubling of formation rarity is 57.92 uu/doubling rarity, q=0.063; weak evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "快筛 v2(41104885, 6,000 场, 358 系列): 超出独立球员习惯基线的空间互补概率为 0.891 个百分点，q=0.36；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。": {
    "zh": "快筛 v2(41104885, 6,000 场, 358 系列): 超出独立球员习惯基线的空间互补概率为 0.891 个百分点，q=0.36；未见清晰证据。 最终未进入论文主线，保留为探索性筛查记录，不作为确认发现。",
    "en": "Quick screen v2 (41104885, 6,000 games, 358 series): Spatial-complementarity probability beyond the independent-player-habit baseline is 0.891 percentage points, q=0.36; no clear evidence. Not retained in the final manuscript focus; preserved as exploratory screening, not a confirmatory finding."
  },
  "42/42 个规格单元通过低于独立基线比较，但所有种子的循环平移负对照区间排除 1，overall=FAIL；只保留为补充材料中的失败负对照，不再扩大或作为协作发现。": {
    "zh": "42/42 个规格单元通过低于独立基线比较，但所有种子的循环平移负对照区间排除 1，overall=FAIL；只保留为补充材料中的失败负对照，不再扩大或作为协作发现。",
    "en": "All 42/42 specification cells pass the below-independence comparison, but circular-shift negative-control intervals exclude 1 for every seed and overall=FAIL. Retained only as a failed negative control in the supplement, with no further scaling or coordination finding."
  },
  "B08 双人低 boost：负对照失败": {
    "zh": "B08 双人低 boost：负对照失败",
    "en": "B08 joint low boost: failed negative control"
  },
  "两种设计均未通过因果识别门控；原 medium 末段落后净进球关联 +0.066/10s [0.026,0.111] 不特异于落后状态。全量 P4 两次 OOM，论文保留 medium 描述性结果，不支持风险大于收益或因果收益。": {
    "zh": "两种设计均未通过因果识别门控；原 medium 末段落后净进球关联 +0.066/10s [0.026,0.111] 不特异于落后状态。全量 P4 两次 OOM，论文保留 medium 描述性结果，不支持风险大于收益或因果收益。",
    "en": "Both designs fail causal-identification gates. The original medium late-trailing net-goal association of +0.066/10s [0.026,0.111] is not specific to trailing states. Full P4 ended OOM twice; the paper retains descriptive medium results and does not establish risk exceeding benefit or a causal benefit."
  },
  "medium 控球条件化净进球差 +0.086 [0.020,0.177]；因果门控仍失败，且不具有落后紧迫性特异性。全量作业 41105136/41105156 两次 OOM，未重提，论文补充材料使用 medium。": {
    "zh": "medium 控球条件化净进球差 +0.086 [0.020,0.177]；因果门控仍失败，且不具有落后紧迫性特异性。全量作业 41105136/41105156 两次 OOM，未重提，论文补充材料使用 medium。",
    "en": "Medium possession-conditioned net goal difference is +0.086 [0.020,0.177]; causal gates still fail and the association is not specific to trailing urgency. Full jobs 41105136/41105156 ended OOM twice and were not resubmitted; the supplement uses medium results."
  },
  "P4 控球条件化敏感性": {
    "zh": "P4 控球条件化敏感性",
    "en": "P4 possession-conditioned sensitivity"
  },
  "全量轮转延迟 measurement_gate.passed=false、finding_eligible=false；1,500 uu 半径的 RMST 差 +1.462 s [1.294,1.633]，仅作补充审计，不能越过测量门控作为发现。": {
    "zh": "全量轮转延迟 measurement_gate.passed=false、finding_eligible=false；1,500 uu 半径的 RMST 差 +1.462 s [1.294,1.633]，仅作补充审计，不能越过测量门控作为发现。",
    "en": "Full-sample rotation latency has measurement_gate.passed=false and finding_eligible=false. The RMST contrast at radius 1,500 uu is +1.462 s [1.294,1.633], retained only for supplementary audit; it cannot bypass the measurement gate to become a finding."
  },
  "P5 轮转延迟：测量门控失败": {
    "zh": "P5 轮转延迟：测量门控失败",
    "en": "P5 rotation latency: failed measurement gate"
  },
  "评审分析已收敛：全量站位、开球 K1 与习惯稳定性进入正文；P6.3 支持不足，仅入补充；P6.4 全量两次 OOM，使用 medium 描述性分解。": {
    "zh": "评审分析已收敛：全量站位、开球 K1 与习惯稳定性进入正文；P6.3 支持不足，仅入补充；P6.4 全量两次 OOM，使用 medium 描述性分解。",
    "en": "Reviewer analyses are consolidated: full-sample positioning, kickoff K1, and habit stability appear in the main text. P6.3 lacks support and is supplementary; full P6.4 ended OOM twice and uses a descriptive medium decomposition."
  },
  "P6 评审分析：已完成并界定证据范围": {
    "zh": "P6 评审分析：已完成并界定证据范围",
    "en": "P6 reviewer analyses: completed with evidence limits"
  },
  "全量：领先方末段−早段 -192.1 uu [-226.5,-157.3]，落后方 +261.3 [226.2,297.4]；交互 +453.4 [420.3,485.2]，1,499 个系列赛。作为正文中的站位关联，不作因果解释。": {
    "zh": "全量：领先方末段−早段 -192.1 uu [-226.5,-157.3]，落后方 +261.3 [226.2,297.4]；交互 +453.4 [420.3,485.2]，1,499 个系列赛。作为正文中的站位关联，不作因果解释。",
    "en": "Full sample: leading late−earlier contrast -192.1 uu [-226.5,-157.3], trailing +261.3 [226.2,297.4]; interaction +453.4 [420.3,485.2] across 1,499 series. Reported in the main text as a positioning association without causal interpretation."
  },
  "P6.1 领先后撤与落后前压": {
    "zh": "P6.1 领先后撤与落后前压",
    "en": "P6.1 leading retreat and trailing advance"
  },
  "全量 K1 pooled：落后方非开球者前压 +447.1 uu [351.8,537.7]，21,000 个观测、1,504 个系列赛。K1 进入正文；K2 仍为 bootstrap 不完整的描述性关联，不能据此推出激进开球有因果收益。": {
    "zh": "全量 K1 pooled：落后方非开球者前压 +447.1 uu [351.8,537.7]，21,000 个观测、1,504 个系列赛。K1 进入正文；K2 仍为 bootstrap 不完整的描述性关联，不能据此推出激进开球有因果收益。",
    "en": "Full K1 pooled: trailing non-kickers are +447.1 uu farther forward [351.8,537.7], using 21,000 observations and 1,504 series. K1 appears in the main text; K2 remains descriptive with incomplete bootstrap and does not establish a causal benefit of aggressive kickoffs."
  },
  "P6.2 开球重置后的站位关联（K1）": {
    "zh": "P6.2 开球重置后的站位关联（K1）",
    "en": "P6.2 positioning after kickoff resets (K1)"
  },
  "全量加时相对常规末段平局的深度差为 -174.8 uu [-193.5,-155.8]，1,182 个系列赛；无预注册等价界，不宣称等价或时钟因果效应。": {
    "zh": "全量加时相对常规末段平局的深度差为 -174.8 uu [-193.5,-155.8]，1,182 个系列赛；无预注册等价界，不宣称等价或时钟因果效应。",
    "en": "Full overtime-minus-late-tied depth contrast is -174.8 uu [-193.5,-155.8] across 1,182 series. No equivalence margin was preregistered; no equivalence or causal clock effect is claimed."
  },
  "P6.6 加时站位对比": {
    "zh": "P6.6 加时站位对比",
    "en": "P6.6 overtime positioning contrast"
  },
  "全量队伍质心交互 +426.0 uu [395.8,457.4]，1,499 个系列赛，方向与末位指标一致；平均三人深度为质心加常数，不算另一项独立证据。": {
    "zh": "全量队伍质心交互 +426.0 uu [395.8,457.4]，1,499 个系列赛，方向与末位指标一致；平均三人深度为质心加常数，不算另一项独立证据。",
    "en": "Full team-centroid interaction is +426.0 uu [395.8,457.4] across 1,499 series, matching the last-man direction. Mean three-player depth is the centroid plus a constant and is not an additional independent piece of evidence."
  },
  "P6.7 站位定义稳健性": {
    "zh": "P6.7 站位定义稳健性",
    "en": "P6.7 robustness to positioning definition"
  },
  "全量抽取作业 41105069 已完成；后续 RQ4 习惯作业 41105127 已完成，实际使用 40,683 个开发 replay。抽取规模不充当各模型分析样本量，留出赛季不用于论文分析。": {
    "zh": "全量抽取作业 41105069 已完成；后续 RQ4 习惯作业 41105127 已完成，实际使用 40,683 个开发 replay。抽取规模不充当各模型分析样本量，留出赛季不用于论文分析。",
    "en": "Full extraction job 41105069 is complete, followed by completed RQ4 habit job 41105127 using 40,683 development replays. Extraction size is not substituted for model-specific sample sizes; the held-out season is not used in the paper analyses."
  },
  "RQ4 全量抽取与习惯分析：已完成": {
    "zh": "RQ4 全量抽取与习惯分析：已完成",
    "en": "RQ4 full extraction and habit analysis: complete"
  },
  "RQ4 全量可解释习惯秩稳定性": {
    "zh": "RQ4 全量可解释习惯秩稳定性",
    "en": "RQ4 full-sample interpretable habit rank stability"
  },
  "仅 medium 事后 ±3 比分截断：20 秒失球差 -0.037 [-0.049,-0.025]，2,000/2,000 次重采样。保留为描述性敏感性；不能把该完成状态移植到 bootstrap 不完整的全量 K2。": {
    "zh": "仅 medium 事后 ±3 比分截断：20 秒失球差 -0.037 [-0.049,-0.025]，2,000/2,000 次重采样。保留为描述性敏感性；不能把该完成状态移植到 bootstrap 不完整的全量 K2。",
    "en": "Medium post hoc score clipping at ±3 only: 20-second concession difference -0.037 [-0.049,-0.025], with 2,000/2,000 resamples. Retained as descriptive sensitivity; this completion status must not be transferred to full K2, whose bootstrap is incomplete."
  },
  "medium 仅原生验证 replay 的事后敏感性：L1 +1.37 s [1.02,1.69]；不能修复全量测量门控失败，只作补充审计。": {
    "zh": "medium 仅原生验证 replay 的事后敏感性：L1 +1.37 s [1.02,1.69]；不能修复全量测量门控失败，只作补充审计。",
    "en": "Medium post hoc sensitivity restricted to natively validated replays: L1 +1.37 s [1.02,1.69]. It does not repair the full-sample measurement-gate failure and remains supplementary audit only."
  },
  "全量作业 41105126 已完成。18 个稳定性/逆转比较均 finding=false；跨赛季阵容稳定性仅 4 个合格单元，ρ=-0.800、CI [-1,1]，其余支持或区间不足。仅入补充，不作为异质性发现。": {
    "zh": "全量作业 41105126 已完成。18 个稳定性/逆转比较均 finding=false；跨赛季阵容稳定性仅 4 个合格单元，ρ=-0.800、CI [-1,1]，其余支持或区间不足。仅入补充，不作为异质性发现。",
    "en": "Full job 41105126 is complete. All 18 stability/comeback comparisons have finding=false; cross-season roster stability has only 4 eligible units, ρ=-0.800 and CI [-1,1], while other comparisons lack support or intervals. Supplementary only, with no heterogeneity finding."
  },
  "P6.3 全量前压斜率异质性：证据不足": {
    "zh": "P6.3 全量前压斜率异质性：证据不足",
    "en": "P6.3 full-sample push-up slope heterogeneity: inconclusive"
  },
  "全量作业 41105139/41105157 两次 OOM，未重提；论文使用 medium 描述性 boost 系数分解。正的系数乘积不能解释负的总失球关联，代数比率不是因果中介比例。": {
    "zh": "全量作业 41105139/41105157 两次 OOM，未重提；论文使用 medium 描述性 boost 系数分解。正的系数乘积不能解释负的总失球关联，代数比率不是因果中介比例。",
    "en": "Full jobs 41105139/41105157 ended OOM twice and were not resubmitted. The paper uses the medium descriptive boost coefficient decomposition. A positive coefficient product does not explain the negative total concession association, and the algebraic ratio is not a causal mediation proportion."
  },
  "P6.4 boost 描述性分解：使用 medium": {
    "zh": "P6.4 boost 描述性分解：使用 medium",
    "en": "P6.4 descriptive boost decomposition: medium results"
  },
  "PROGRESS.md: 2026-10-31 19:40 CET": {
    "zh": "PROGRESS.md: 2026-10-31 19:40 CET",
    "en": "PROGRESS.md: 2026-10-31 19:40 CET"
  },
  "paper2/paper/sections/supplement_body.tex": {
    "zh": "paper2/paper/sections/supplement_body.tex",
    "en": "paper2/paper/sections/supplement_body.tex"
  },
  "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/results_push.tex": {
    "zh": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/results_push.tex",
    "en": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/results_push.tex"
  },
  "paper2/paper/sections/results_who.tex; paper2/paper/sections/supplement_body.tex": {
    "zh": "paper2/paper/sections/results_who.tex; paper2/paper/sections/supplement_body.tex",
    "en": "paper2/paper/sections/results_who.tex; paper2/paper/sections/supplement_body.tex"
  },
  "paper2/paper/main.tex; paper2/paper/sections/supplement_body.tex": {
    "zh": "paper2/paper/main.tex; paper2/paper/sections/supplement_body.tex",
    "en": "paper2/paper/main.tex; paper2/paper/sections/supplement_body.tex"
  },
  "PROGRESS.md: 2026-11-01 01:15 CET; paper2/paper/sections/data.tex": {
    "zh": "PROGRESS.md: 2026-11-01 01:15 CET; paper2/paper/sections/data.tex",
    "en": "PROGRESS.md: 2026-11-01 01:15 CET; paper2/paper/sections/data.tex"
  },
  "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/supplement_body.tex": {
    "zh": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/supplement_body.tex",
    "en": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/sections/supplement_body.tex"
  },
  "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/main.tex": {
    "zh": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/main.tex",
    "en": "PROGRESS.md: 2026-10-31 19:40 CET; paper2/paper/main.tex"
  },
  "results/screen_v2.json; paper2/paper/main.tex": {
    "zh": "results/screen_v2.json; paper2/paper/main.tex",
    "en": "results/screen_v2.json; paper2/paper/main.tex"
  },
  "results/b08_robust.json; paper2/paper/sections/supplement_body.tex": {
    "zh": "results/b08_robust.json; paper2/paper/sections/supplement_body.tex",
    "en": "results/b08_robust.json; paper2/paper/sections/supplement_body.tex"
  },
  "PROGRESS.md: 2026-10-31 21:15 CET; 2026-11-01 03:15 CET": {
    "zh": "PROGRESS.md: 2026-10-31 21:15 CET; 2026-11-01 03:15 CET",
    "en": "PROGRESS.md: 2026-10-31 21:15 CET; 2026-11-01 03:15 CET"
  },
  "PROGRESS.md: 2026-10-31 22:55 CET; 2026-11-01 03:15 CET": {
    "zh": "PROGRESS.md: 2026-10-31 22:55 CET; 2026-11-01 03:15 CET",
    "en": "PROGRESS.md: 2026-10-31 22:55 CET; 2026-11-01 03:15 CET"
  },
  "paper2/paper/sections/supplement_body.tex; PROGRESS.md: 2026-11-01 03:15 CET": {
    "zh": "paper2/paper/sections/supplement_body.tex; PROGRESS.md: 2026-11-01 03:15 CET",
    "en": "paper2/paper/sections/supplement_body.tex; PROGRESS.md: 2026-11-01 03:15 CET"
  },
  "paper2/paper/sections/results_push.tex": {
    "zh": "paper2/paper/sections/results_push.tex",
    "en": "paper2/paper/sections/results_push.tex"
  },
  "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.2": {
    "zh": "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.2",
    "en": "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.2"
  },
  "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.1/P6.6/P6.7": {
    "zh": "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.1/P6.6/P6.7",
    "en": "paper2/paper/sections/results_push.tex; paper2/docs/full_results.md: P6.1/P6.6/P6.7"
  },
  "PROGRESS.md: 2026-11-01 01:15 CET, 03:15 CET; paper2/paper/sections/results_who.tex": {
    "zh": "PROGRESS.md: 2026-11-01 01:15 CET, 03:15 CET; paper2/paper/sections/results_who.tex",
    "en": "PROGRESS.md: 2026-11-01 01:15 CET, 03:15 CET; paper2/paper/sections/results_who.tex"
  },
  "PROGRESS.md: 2026-11-01 00:15 CET; paper2/docs/full_results.md: P6.2": {
    "zh": "PROGRESS.md: 2026-11-01 00:15 CET; paper2/docs/full_results.md: P6.2",
    "en": "PROGRESS.md: 2026-11-01 00:15 CET; paper2/docs/full_results.md: P6.2"
  },
  "paper2/paper/sections/supplement_body.tex; results/pushup_heterogeneity.json": {
    "zh": "paper2/paper/sections/supplement_body.tex; results/pushup_heterogeneity.json",
    "en": "paper2/paper/sections/supplement_body.tex; results/pushup_heterogeneity.json"
  },
  "PROGRESS.md: 2026-11-01 03:15 CET; paper2/paper/sections/supplement_body.tex": {
    "zh": "PROGRESS.md: 2026-11-01 03:15 CET; paper2/paper/sections/supplement_body.tex",
    "en": "PROGRESS.md: 2026-11-01 03:15 CET; paper2/paper/sections/supplement_body.tex"
  },
  "《基于回放的 Rocket League 战术站位与选手习惯分析框架》": {
    "zh": "《基于回放的 Rocket League 战术站位与选手习惯分析框架》",
    "en": "A Replay-Based Framework for Tactical Positioning and Player Habits in Rocket League"
  },
  "作者信息仍待填写；论文在修订中。页数与提交来自快照记录；本地仅有 PDF 时，源码统计未知属于正常。": {
    "zh": "作者信息仍待填写；论文在修订中。页数与提交来自快照记录；本地仅有 PDF 时，源码统计未知属于正常。",
    "en": "Author information is still pending; the manuscript remains under revision. Page counts and commits come from snapshot records; unknown source statistics are expected when only PDFs are available locally."
  },
  "引言": {
    "zh": "引言",
    "en": "Introduction"
  },
  "相关工作": {
    "zh": "相关工作",
    "en": "Related work"
  },
  "数据": {
    "zh": "数据",
    "en": "Data"
  },
  "方法": {
    "zh": "方法",
    "en": "Methods"
  },
  "比分紧迫性下的防守站位": {
    "zh": "比分紧迫性下的防守站位",
    "en": "Defensive positioning under scoreboard urgency"
  },
  "跨赛季选手习惯稳定性": {
    "zh": "跨赛季选手习惯稳定性",
    "en": "Player habits persist across seasons"
  },
  "空间案例": {
    "zh": "空间案例",
    "en": "Spatial cases"
  },
  "讨论": {
    "zh": "讨论",
    "en": "Discussion"
  },
  "补充材料": {
    "zh": "补充材料",
    "en": "Supplementary material"
  },
  "PROGRESS.md: 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4": {
    "zh": "PROGRESS.md: 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4",
    "en": "PROGRESS.md: 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 2d041a4"
  },
  "中样本实验之后，全量抽取 41105069 已完成；全量 RQ4 习惯 41105127 与 P6.3 异质性 41105126 均已完成。RQ4 实际使用 40,683 个开发 replay，开发集剔除 5 个解码不合格 replay。论文采用全量开发/2025 验证结果；P4 与 P6.4 全量各两次 OOM，保留 medium 结果。": {
    "zh": "中样本实验之后，全量抽取 41105069 已完成；全量 RQ4 习惯 41105127 与 P6.3 异质性 41105126 均已完成。RQ4 实际使用 40,683 个开发 replay，开发集剔除 5 个解码不合格 replay。论文采用全量开发/2025 验证结果；P4 与 P6.4 全量各两次 OOM，保留 medium 结果。",
    "en": "Following medium-sample experiments, full extraction 41105069 is complete, as are full RQ4 habits 41105127 and P6.3 heterogeneity 41105126. RQ4 uses 40,683 development replays after excluding 5 development replays with failed decoding checks. The paper uses full development/2025 validation results; full P4 and P6.4 each ended OOM twice and retain medium results."
  },
  "paper2/paper/LIT_CHECK.md": {
    "zh": "paper2/paper/LIT_CHECK.md",
    "en": "paper2/paper/LIT_CHECK.md"
  },
  "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 2d041a4，本地论文源 HEAD 7c3e20c。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。 正文实际引用 27 条均已核对：26 条状态为 verified，TS2Vec 为 fixed（元数据已修正）。": {
    "zh": "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 2d041a4，本地论文源 HEAD 7c3e20c。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。 正文实际引用 27 条均已核对：26 条状态为 verified，TS2Vec 为 fixed（元数据已修正）。",
    "en": "Prepared for IEEE Transactions on Games; 7 main-text pages and 9 supplementary pages have been reviewed page by page, and manuscript revision is in progress. Latest cluster commit: 2d041a4; local manuscript-source HEAD: 7c3e20c. The q-value honesty correction states that all 24 RQ4 BH q values are at the floor of 2,000 permutations: q≤1/2001≈0.0005 in the text and caption, and BH q<0.001 in the abstract. After two OOM failures each, full P4/P6.4 use medium results with limitations recorded in the supplement; no causal claims are made. All 27 main-text citations have been checked: 26 have verified status, while TS2Vec has fixed status after a metadata correction."
  },
  "Bilingual purpose of each Slurm job name / 各作业名的中英文用途说明": {
    "zh": "各 Slurm 作业名的中英文用途说明；依据本地 PROGRESS 与实施文档。",
    "en": "Bilingual purposes for Slurm job names, based on local PROGRESS and implementation documents."
  },
  "PROGRESS.md#2026-11-01 03:15 CET; docs/P6_heterogeneity_implementation.md": {
    "zh": "PROGRESS.md#2026-11-01 03:15 CET; docs/P6_heterogeneity_implementation.md",
    "en": "PROGRESS.md#2026-11-01 03:15 CET; docs/P6_heterogeneity_implementation.md"
  },
  "PROGRESS.md#2026-11-01 03:15 CET; docs/RQ4_habits_implementation.md": {
    "zh": "PROGRESS.md#2026-11-01 03:15 CET; docs/RQ4_habits_implementation.md",
    "en": "PROGRESS.md#2026-11-01 03:15 CET; docs/RQ4_habits_implementation.md"
  },
  "PROGRESS.md#2026-11-01 03:15 CET; slurm/p4_possession.sh": {
    "zh": "PROGRESS.md#2026-11-01 03:15 CET; slurm/p4_possession.sh",
    "en": "PROGRESS.md#2026-11-01 03:15 CET; slurm/p4_possession.sh"
  },
  "PROGRESS.md#2026-11-01 03:15 CET; slurm/p6_mediation.sh": {
    "zh": "PROGRESS.md#2026-11-01 03:15 CET; slurm/p6_mediation.sh",
    "en": "PROGRESS.md#2026-11-01 03:15 CET; slurm/p6_mediation.sh"
  },
  "PROGRESS.md#2026-11-01 04:35 CET; PROGRESS.md#2026-11-01 05:05 CET": {
    "zh": "PROGRESS.md#2026-11-01 04:35 CET; PROGRESS.md#2026-11-01 05:05 CET",
    "en": "PROGRESS.md#2026-11-01 04:35 CET; PROGRESS.md#2026-11-01 05:05 CET"
  },
  "PROGRESS.md#2026-11-01 03:15 CET; /api/jobs#41105191": {
    "zh": "PROGRESS.md#2026-11-01 03:15 CET; /api/jobs#41105191",
    "en": "PROGRESS.md#2026-11-01 03:15 CET; /api/jobs#41105191"
  },
  "训练使用 2021-22、22-23、2024，验证使用 2025；2026 测试集保持封存。本次大屏更新只读取已有汇总，不打开测试数据。": {
    "zh": "训练使用 2021-22、22-23、2024，验证使用 2025；2026 测试集保持封存。本次大屏更新只读取已有汇总，不打开测试数据。",
    "en": "Training uses 2021-22, 22-23 and 2024; validation uses 2025. The 2026 test set remains sealed. This dashboard update reads existing summaries only and does not open test data."
  },
  "RQ4 可解释习惯的相邻赛季秩稳定性": {
    "zh": "RQ4 可解释习惯的相邻赛季秩稳定性",
    "en": "RQ4 Adjacent-season rank stability of interpretable habits"
  },
  "最终采用可解释习惯的相邻赛季 Spearman 秩相关、选手自助法区间与置换检验；原计划中的身份检索、阵容与俱乐部归因不作为主结论。": {
    "zh": "最终采用可解释习惯的相邻赛季 Spearman 秩相关、选手自助法区间与置换检验；原计划中的身份检索、阵容与俱乐部归因不作为主结论。",
    "en": "The final analysis uses adjacent-season Spearman rank correlations of interpretable habits, player-bootstrap intervals and permutation tests. Planned identity retrieval and attribution to rosters or clubs are excluded from the main conclusions."
  },
  "论文定稿与投稿": {
    "zh": "论文定稿与投稿",
    "en": "Manuscript finalization and submission"
  },
  "待作者信息补齐与投稿前终审": {
    "zh": "待作者信息补齐与投稿前终审",
    "en": "Pending author information and final pre-submission review"
  },
  "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 1ef1d69，本地论文源 HEAD 648cbee。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。": {
    "zh": "面向 IEEE Transactions on Games；正文 7 页、补充 9 页，图文已逐页检查，论文仍在修订中。最新集群提交 1ef1d69，本地论文源 HEAD 648cbee。q 值诚实性修正：24 个 RQ4 BH q 均处于 2,000 次置换下限，正文与图注写 q≤1/2001≈0.0005，摘要写 BH q<0.001。P4/P6.4 全量各两次 OOM 后使用 medium，补充材料注明限制；不作因果结论。",
    "en": "Prepared for IEEE Transactions on Games; 7 main-text pages and 9 supplementary pages have been reviewed page by page, and manuscript revision is in progress. Latest cluster commit: 1ef1d69; local manuscript-source HEAD: 648cbee. The q-value honesty correction states that all 24 RQ4 BH q values are at the floor of 2,000 permutations: q≤1/2001≈0.0005 in the text and caption, and BH q<0.001 in the abstract. After two OOM failures each, full P4/P6.4 use medium results with limitations recorded in the supplement; no causal claims are made."
  },
  "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 1ef1d69": {
    "zh": "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 1ef1d69",
    "en": "PROGRESS.md: 2026-10-31 21:00 CET; 2026-11-01 06:45 CET, 07:51 CET; paper2/paper/main.tex; user-supplied cluster commit 1ef1d69"
  }
};
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
      if (!explicit && Object.hasOwn(proseTranslations,text)) return proseTranslations[text][lang];
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
      const res=j.resource_type==='GPU'?`GPU × ${fmt(j.gpu_count)} · ${esc(str(j.gpu_model))}`:j.resource_type==='CPU'?'CPU · GPU × 0':unknown();
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
      card(t('最近活动','Recent activity'),recent?`<p>${raw(recent[0],'path')} · ${esc(time(recent[1].mtime))}</p><pre>${esc(sourceText(recent[1],'tail').split('\n').slice(-12).join('\n'))}</pre><a href="#/session">${t('全部日志','All logs')}</a>`:empty('暂无会话记录','No session logs'));
  }
  function barChart(items,label,unit) {
    const valid=items.filter(x=>num(x.value));if(!valid.length)return empty();
    let low=Math.min(0,...valid.map(x=>x.value)),high=Math.max(0,...valid.map(x=>x.value));if(low===high)high=low+1;
    const ticks=niceTicks(low,high);low=ticks.min;high=ticks.max;
    const w=1000,h=valid.length*48+100,left=260,right=150,x=v=>left+(v-low)/(high-low)*(w-left-right);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label+' ('+unit+')')}">`;
    ticks.values.forEach((v,i)=>{svg+=`<path class="grid-line" d="M${x(v)} 20V${h-65}"/><text x="${x(v)}" y="${h-40}" text-anchor="middle">${ticks.labels[i]}</text>`;});
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
  function niceTicks(low,high) {
    if (low===high) { low-=.5;high+=.5; }
    const raw=(high-low)/4,exponent=Math.floor(Math.log10(raw)),power=10**exponent;
    const multiple=[1,2,2.5,5,10].find(v=>raw/power<=v),step=multiple*power;
    const first=Math.floor(low/step),last=Math.ceil(high/step);
    // Integer multiples anchor the ticks at zero; rounding removes binary noise.
    const values=Array.from({length:last-first+1},(_,i)=>Number(((first+i)*step).toPrecision(15)));
    const decimals=Math.max(0,-exponent+(multiple===2.5?1:0));
    const labels=values.map(v=>v===0?'0':decimals>100?v.toString():v.toFixed(decimals).replace(/(\.\d*?[1-9])0+$|\.0+$/,'$1'));
    return {min:values[0],max:values[values.length-1],step,values,labels};
  }
  function forest(rows,unit) {
    if (!rows.length) return empty('没有可绘制的效应量与 95% 置信区间','No plottable effect estimates with 95% CIs',t('缺失、非数值或无效区间保留在表格中。','Missing, non-numeric or invalid intervals remain in the table.'));
    let lo=Math.min(0,...rows.flatMap(r=>[r.lo,r.estimate])), hi=Math.max(0,...rows.flatMap(r=>[r.hi,r.estimate]));
    const pad=(hi-lo||1)*.12;lo-=pad;hi+=pad;
    const ticks=niceTicks(lo,hi);lo=ticks.min;hi=ticks.max;
    const w=1000,h=100+rows.length*60,left=300,right=50,bottom=h-65,x=v=>left+(v-lo)/(hi-lo)*(w-left-right);
    let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(t('效应量及 95% 置信区间森林图','Forest plot of effect estimates and 95% confidence intervals'))}">`;
    ticks.values.forEach((v,i)=>{svg+=`<path class="grid-line" d="M${x(v)} 15 V${bottom}"/><text x="${x(v)}" y="${bottom+25}" text-anchor="middle">${ticks.labels[i]}</text>`;});
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
    if (!groups.has(state.resultGroup))state.resultGroup=[...groups].find(([,rows])=>rows.some(r=>r.source.startsWith('results/dash_full_summary.json/rq4/')))?.[0]||groups.keys().next().value;
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
    if(!groups.has(state.legacyGroup))state.legacyGroup=[...groups].find(([,rs])=>rs[0].file==='baseline_comparison'&&rs[0].metric==='top1')?.[0]||groups.keys().next().value;
    const rows=groups.get(state.legacyGroup),first=rows[0],metric=first.metric,unit=unitLabel(first.unit);
    const lower=r=>Array.isArray(r.lower_is_better)?r.lower_is_better.includes(metric):typeof r.lower_is_better==='boolean'?r.lower_is_better:null;
    const directions=rows.map(x=>lower(x.r)),comparable=first.unit&&directions.every(d=>d!==null&&d===directions[0]);
    const best=vals=>vals.length?(directions[0]?Math.min(...vals):Math.max(...vals)):null;
    const baseline=comparable?best(rows.filter(x=>x.r.is_baseline===true).map(x=>x.value)):null;
    const ours=comparable?best(rows.filter(x=>x.r.is_baseline===false).map(x=>x.value)):null;
    const delta=v=>baseline!==null?(v-baseline)*(directions[0]?-1:1):null;
    const label=x=>[localized(x.r,'task')||x.file,localized(x.r,'split')||unknown(),metricLabel({},x.metric),unitLabel(x.unit)].join(' · ');
    const toolbar=`<div class="controls"><label>${t('指标对比组','Metric comparison group')}<select id="legacy-group">${[...groups].map(([key,rs])=>`<option value="${esc(key)}" ${key===state.legacyGroup?'selected':''}>${esc(label(rs[0]))}</option>`).join('')}</select></label></div>`;
    return card(t('基线与方法指标','Baseline and method metrics'),toolbar+`<div class="kpis">${kpi(t('最佳基线','Best baseline'),baseline)}${kpi(t('本方法最优','Best method'),ours)}${kpi(t('方向归一化差值','Direction-normalized difference'),ours!==null?delta(ours):null)}</div>`+barChart(rows.map(x=>({name:localized(x.r,'method')||x.file,value:x.value,color:x.r.is_baseline===true?palette[0]:palette[3]})),metricLabel({},metric),unit)+table([t('方法','Method'),t('类型','Type'),t('指标','Metric'),t('数值','Value'),t('95% 置信区间','95% CI'),'Δ'],rows.map(x=>{const ci=obj(x.r.ci95)[metric];return [esc(localized(x.r,'method')||x.file),x.r.is_baseline===true?t('基线','Baseline'):x.r.is_baseline===false?t('本方法','Method'):unknown(),esc(metricLabel({},metric)),fmt(x.value),Array.isArray(ci)&&ci.length===2?`[${fmt(ci[0])}, ${fmt(ci[1])}]`:t('未保存','not saved'),fmt(delta(x.value))]}))+`<p class="muted">${t('只在任务、划分、指标、已声明单位和方向一致时计算最佳基线及差值；正值表示改善。缺失或冲突时显示未知。原始指标柱状图不表示统计显著性。','Best baselines and differences require matching task, split, metric, declared units and direction; positive differences indicate improvement. Missing or conflicting metadata is unknown. Raw metric bars do not imply statistical significance.')}</p>`);
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
    const snapshot=p.snapshot_updated?card(t('论文状态快照','Manuscript status snapshot'),`<p>${badge(p.status)} · ${esc(time(p.snapshot_updated))}</p><p>${esc(localized(p,'note'))}</p><div class="kpis">${kpi(t('正文页数','Main pages'),p.main_pages)}${kpi(t('补充材料页数','Supplement pages'),p.supplement_pages)}${kpi(t('集群论文提交','Cluster paper commit'),p.cluster_commit)}${kpi(t('本地论文源码提交','Local manuscript source commit'),p.manuscript_commit)}</div><p class="meta">${t('来源','Source')}: ${esc(localized(p,'snapshot_source'))}</p>`):'';
    const pdfPanel=card(t('论文 PDF','Paper PDF'),`<div class="kpis">${kpi(t('编译时间（PDF 创建元数据）','Compile time (PDF creation metadata)'),time(pdf.compiled))}${kpi(t('页数','Pages'),pdf.pages)}${kpi(t('PDF 文件提交','PDF file commit'),pdf.commit?pdf.commit.slice(0,12):null)}</div><p class="meta">${t('PDF 文件修改时间','PDF file modified')}: ${esc(time(pdf.modified))}</p>`+(pdf.available?`<p><a href="/paper.pdf" target="_blank" rel="noopener">${t('打开 PDF','Open PDF')}</a></p><iframe class="paper-pdf" src="/paper.pdf" title="${t('论文 PDF 预览','Paper PDF preview')}"></iframe>`:empty('尚无论文 PDF','No paper PDF available',t('等待 paper/main.pdf；不运行编译命令。','Waiting for paper/main.pdf; no compilation command is run.')))+`<p class="muted">${t('创建元数据缺失时编译时间未知；文件修改时间不等同于编译时间。PDF 文件提交不等同于编译所用源码提交。','Missing creation metadata leaves compile time unknown; file modification time is not compilation time. The PDF file commit does not establish the source commit used to compile it.')}</p>`);
    return snapshot+(p.reference?note(t('本地审阅模式：论文源码来自参考目录。','Local review mode: manuscript sources come from the reference directory.')):'')+`<div class="kpis">${kpi(t('总进度','Overall progress'),num(p.progress)?fmt(p.progress)+'%':null,t('明确完成章节 / 全部章节','Explicitly completed / all sections'))}${kpi(t('章节完成','Sections complete'),p.completed_sections,partial)}${kpi(t('字数（近似）','Word count (approximate)'),p.words,partial)}${kpi(t('图数','Figures'),p.figure_count,partial)}${kpi(t('论文最新提交','Latest paper commit'),p.commit?p.commit.slice(0,12):null)}</div>`+pdfPanel+
      card(t('章节进度','Section progress'),`<p class="muted">${t('自动扫描 paper/main.tex 及其 input/include。字数按英文词和汉字计数，图数按 figure 环境计数。含正文为草稿；TODO 保持草稿；仅章节内明确的 % dashboard-status: done 标记计为完成。缺失文件使总进度未知。','Automatically scans paper/main.tex and its input/include files. Counts English tokens and CJK characters; figures count figure environments. Text is a draft; TODOs remain drafts. Only explicit per-section % dashboard-status: done markers count as completed. Missing files make overall progress unknown.')}</p>`+(sections.length?table([t('章节','Section'),t('状态','Status'),t('字数','Words'),t('图数','Figures'),t('最新提交','Latest commit'),t('源文件','Source file')],sections.map(x=>[esc(localized(x,'name')),badge(x.status),fmt(x.words),fmt(x.figure_count),esc(x.commit?x.commit.slice(0,12):unknown()),raw(x.path,'path')])):empty('暂无论文源码','No manuscript sources',t('等待 paper/main.tex。','Waiting for paper/main.tex.'))))+
      card(t('投稿目标与引用','Target venue and citations'),`<p>${esc(localized(p,'target')||unknown())}</p><p>${esc(localized(p,'notes'))}</p><div class="kpis">${kpi(t('引用已核验','Verified citations'),cit.verified)}${kpi(t('引用总数','Total citations'),cit.total)}</div>`)+
      card(t('图表清单','Figures'),figures.length?table([t('编号','ID'),t('标题','Title'),t('状态','Status'),t('路径 / 备注','Path / notes')],figures.map(f=>[esc(str(f.id)),esc(localized(f,'title')||localized(f,'name')),badge(f.status),raw(f.path,'path')])):empty());
  }
  // Logs and Markdown are source documents, not interface labels. Preserve the
  // source in Chinese mode; translate exact known lines in English mode.
  function sourceText(record,key) {
    record=obj(record);
    const source=record[key+'_'+lang] ?? record[key] ?? '';
    return String(source).split('\n').map((line,i)=>{
      if(lang==='zh'||!cjk.test(line))return line;
      const translation=proseTranslations[line]?.en;
      return translation&&!cjk.test(translation)?translation:`[Source line ${i+1}: English translation unavailable]`;
    }).join('\n');
  }
  const sourceNotice=()=>note(t('原始研究记录：保留原文语言；英文版使用逐行核对的译文，缺少译文的行会明确说明。','Original research record: reviewed translations are matched by exact source line; unavailable English lines are explicitly identified.'));
  function logsView() {
    const logs=obj(state.data.logs),names=Object.keys(logs);
    if (!names.length)return card(t('会话日志','Session logs'),empty());
    if (!names.includes(state.log))state.log=names[0];
    const record=logs[state.log];
    return card(t('会话日志','Session logs'),`<div class="controls"><label>${t('日志文件','Log file')}<select id="log-file">${names.map(n=>`<option ${n===state.log?'selected':''}>${esc(n)}</option>`).join('')}</select></label><label>${t('筛选日志行','Filter log lines')}<input type="search" id="log-filter" value="${esc(state.logFilter)}"></label></div><p class="meta">${esc(time(record.mtime))}${record.truncated?' · '+t('仅显示末尾 20 KB','Last 20 KB only'):''}</p><pre id="log-output">${esc(logLines())}</pre><p class="meta">${t('带时区的日志时间转为 CET；未标注时区的时间保留原样。保留原始日志；英文版无法翻译的行会明确说明。','Timezone-qualified log timestamps convert to CET; unqualified times remain unchanged. Original log output is preserved; lines unavailable in English are explicitly identified.')}</p>`);
  }
  function logLines() { return sourceText(obj(obj(state.data.logs)[state.log]),'tail').replace(/\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})/g,match=>time(match)).split('\n').filter(line=>line.toLowerCase().includes(state.logFilter.toLowerCase())).join('\n')||t('没有匹配的日志行','No matching log lines'); }
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
    const text=sourceText(typeof state.data.progress==='string'?{text:state.data.progress}:state.data.progress,'text');
    // Source HTML and image references remain escaped; no external resources load.
    return card(t('研究进度文档','Research progress document'),sourceNotice()+(text?markdown(text):empty()),'PROGRESS.md');
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
