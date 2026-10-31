# The Grammar of Rotation: Coordination, Pressure, and Tactical Style in Professional Rocket League

**Target:** IEEE Transactions on Games  
**Design date:** 2026-10-31  
**Status:** Research design; hypotheses below are proposed findings, not observed results.

## 1. Research objective

Discover interesting, credible, interpretable regularities in professional Rocket League:

- What recurring coordination patterns emerge among three teammates?
- When does a rotation become vulnerable?
- How do teams redistribute risk under pressure?
- What persists across players, rosters, organizations, and seasons?
- Can pre-goal “势” be measured prospectively?

The contribution is a behavioral account supported by reproducible measurements, representative replays, uncertainty estimates, and held-out validation. Prediction and representation learning are instruments for this study. Beating baselines or SOTA is not a success criterion.

This direction supersedes `prompt.md`’s requests for four to six novel algorithms and explanations of why they should outperform baselines. Its data facts, venue whitelist, grouped splits, and reference-verification rules remain applicable.

## 2. TAGNet: provenance, complete-paper summary, and lessons

### 2.1 Identity and provenance

The supplied paper is:

**Xiang Zhang, RongQi Zhang, Guancheng Chen, Xinlei Cao, ChaoFan Yue, and Chunhong Yuan. “TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2.” IEEE Transactions on Games, 2026. DOI: 10.1109/TG.2026.3745970.**

The supplied document identifies itself as an accepted author version. Its identity is corroborated by the authors’ [citation record](https://github.com/weyoung-open-lab/TAGNet-CS2/blob/main/CITATION.cff), [AMiner’s journal listing](https://www.aminer.cn/academic/journal/ieee-transactions-on-games/5ea19965edb6e7d53c00ab7c), and an independently hosted [bibliographic listing](https://www.ablesci.com/assist/detail?id=7GAmbn). The live IEEE page presented a browser challenge; it was not counted as a successful web verification. No volume or issue is invented.

The summary below is based on the complete supplied PDF:

:codex-file-citation{path="/Users/derricklee/rlcs-p2/TAGNet_ToG2026.pdf" purpose="source"}

### 2.2 Method

TAGNet studies **697 CT-side rounds from 33 professional Dust2 matches**, collected in 2024–2025. The encoder split is by match: 23/5/5 matches, containing 486/95/116 rounds.

Each round contains five snapshots at 10, 12, 15, 18, and 20 seconds after freeze time:

- Five CT players form a fully connected graph.
- Each player has 22 features: 20 named-area indicators, health, and equipment value.
- Pairwise planar distance enters attention through a learned bias.
- A three-layer, width-64 graph encoder produces pooled snapshot embeddings.
- Three reconstruction heads recover place distribution, macro-area occupancy, and pairwise distances.
- A 25-dimensional context vector includes economy, score, utility, and previous-round information.
- A context projection and GRU produce a 64-dimensional round embedding.
- K-means selects six clusters using combined rankings of silhouette, Davies–Bouldin, and Calinski–Harabasz indices.

Two implementation details are important:

1. **The GRU and context projection are not trained.** Reconstruction reads the snapshot embeddings directly, so these modules retain seeded random initialization.
2. **Clustering and selection of K use all 697 round embeddings.** The encoder has a held-out split, but the vocabulary and subsequent descriptive analysis are transductive.

### 2.3 Findings

The six interpreted patterns span anchor defense, balanced formations, mid control, and aggressive forward positioning.

Reported findings include:

- Economy is associated with pattern choice: χ² = 96.25, Cramér’s V = 0.215, Holm-adjusted p < .001.
- Previous-round winner remains associated after correction.
- The overall current-score association is nonsignificant: p = .245.
- A separate paired comparison finds more C5 aggressive-pattern usage when trailing: mean .116 versus .031 when leading.
- For that C5 comparison, the full paper reports **raw p = .0020 and Holm-adjusted p = .0118**. The corrected claim is significant at .05, not p < .01.
- Cluster frequencies provide descriptive team fingerprints. No team–opponent association survives the reported Holm correction.
- Cross-seed clustering agreement is approximately ARI = .52.

Its reconstruction improvement is secondary to the tactical story. The paper itself reports handcrafted count-sequence clustering with better internal clustering indices.

### 2.4 What makes it interesting

TAGNet makes an intelligible chain from movement to meaning:

**recognizable configurations → their evolution → contextual associations → team differences.**

A reader can inspect the maps, understand a pattern, and ask when or why a team uses it. The findings invite discussion without requiring a model-performance leaderboard.

### 2.5 Limitations and implications for this study

| TAGNet limitation | RLCS design response |
|---|---|
| One map, 33 matches, early defensive phase only | Study continuous interaction across multiple seasons, with explicit context and sampling coverage |
| Temporal aggregator is fixed | Train temporal representations through objectives that depend on temporal outputs |
| Context enters clustering before associations with that context are tested | Keep tested context outside the primary vocabulary encoder |
| Vocabulary selected using all rounds | Fit vocabulary on training data; select using validation; freeze before test |
| Moderate seed agreement | Report semantic and assignment stability across seeds and K |
| Names initially rule-generated and checked by one expert | Use blinded independent raters, random members, medoids, and counterexamples |
| Score and economy associations are confounded | Separate descriptive association, conditional association, and causal claims |
| Fingerprints based on small team samples | Require repeated independent series and report fingerprint uncertainty |
| Static compactness can obscure useful temporal distinctions | Evaluate temporal structure and interpretation directly |

The intended advance is not simply a larger TAGNet. Rocket League supports questions about **handoffs, complementary responsibilities, recovery, temporal grammar, roster continuity, and pressure-dependent coordination**.

## 3. Related-work map

Only whitelisted research venues are retained. Dataset and tool entries are the requested exceptions. BibTeX keys correspond to `references.bib`.

| Research thread | Verified work | What it motivates here |
|---|---|---|
| Label-free esports patterns | `zhang2026tagnet`, IEEE ToG 2026 | Readable tactical vocabulary and context-linked behavioral findings |
| Rocket League behavior mining | `mathonat2020rocketleague`, IEEE CoG 2020 | Interpretable temporal patterns; distinguish its supervised individual skillshot recognition from our label-free team coordination study |
| Implicit coordination | `habaraduwa2025coordination`, IEEE ToG 2025 | Measure complementary responsibilities as well as synchronized movement |
| Changing multi-agent roles | `le2017coordinated`, ICML 2017 | Treat roles as dynamic coordination variables rather than fixed player slots |
| Permutation-invariant representations | `zaheer2017deepsets`, NeurIPS 2017 | Prevent arbitrary within-team player ordering from becoming a feature |
| Temporal self-supervision | `yue2022ts2vec`, AAAI 2022 | Learn representations at multiple temporal scales using valid augmentations |
| Interpretable trajectory generation | `zhan2019programmatic`, ICLR 2019 | Conditional trajectory examples and macro-intents; no implication of causal identification |
| Contextual value | `decroos2019actions`, KDD 2019 | Evaluate buildup beyond goals and immediate actions; adapt scoring/conceding probabilities to RLCS |

The Rocket League precedent explicitly combines labeled skillshots, pattern mining, and supervised classification. Our unit of interest is coordinated team behavior from the supplied replay features, without assuming controller inputs or tactical labels. [Primary paper](https://perso.liris.cnrs.fr/jboulica/cog2020.pdf).

The Dota 2 study relates movement synchrony to tournament performance. It motivates examining whether good coordination involves complementary movement rather than maximal synchrony. Its reported rank association should not be paraphrased without checking rank coding. [Institutional publication record](https://research.tilburguniversity.edu/en/publications/implicit-coordination-dynamics-a-synchrony-based-study-on-team-po-2/).

Latent roles, invariant pooling, and temporal contrastive representations motivate the measurement machinery, not novelty claims about their components. [Coordinated Multi-Agent Imitation Learning](https://proceedings.mlr.press/v70/le17a.html), [Deep Sets](https://papers.nips.cc/paper/2017/hash/f22e4747da1aa27e363d86d40ff442fe-Abstract.html), [TS2Vec](https://ojs.aaai.org/index.php/AAAI/article/view/20881).

Conditional trajectory generation provides interpretable examples but does not identify what would causally happen after a different player decision. [ICLR paper](https://iclr.cc/virtual/2019/poster/985).

The contextual action-value precedent received KDD 2019’s Applied Data Science Track best-paper award. Its useful lesson is to value buildup and defensive contributions in context. [Paper](https://www.kdd.org/kdd2019/accepted-papers/view/actions-speak-louder-than-goals-valuing-player-actions-in-soccer), [award record](https://www.kdd.org/awards/view/2019-sigkdd-best-paper-award-winners).

**Reference audit:** Retained research entries have at least three independently hosted corroborating pages. Different pages from the same repository do not count as independent sources. The mandatory exact Kaggle dataset has only a canonical-page verification; its exception is disclosed rather than fabricated. The supplied dataset counts are user-provided facts, not independently inferred from Kaggle.

## 4. Data contract and derived measurements

### 4.1 Available data

| Item | Supplied fact |
|---|---|
| Games | 49,259 |
| Frames | 591.2 million, nominally 30 fps |
| Seasons | 2021–22: 11,699; 2022–23: 15,410; 2024: 7,307; 2025: 7,081; 2026: 7,762 |
| Modes | 1v1: 1,586; 2v2: 786; 3v3: 46,793 |
| Remaining games | 94 games with odd player counts, as clarified by the user |
| Ball | Position, rotation, linear/angular velocity |
| Players | Position, rotation, velocities, boost, dodge/jump/double-jump flags, demolished-by |
| Other frame fields | Seconds remaining, game state, ball-has-been-hit |
| Metadata | Goals, teams, players, outcome |
| Grouping | Season/event/region/stage/series |
| Missingness | NaN for missing players |
| Tactical labels | None |

The mode counts sum to 49,165; adding the 94 odd-player-count games reconciles the season total.

A six-player roster defines primary 3v3 eligibility. Requiring six finite positions at every frame would incorrectly conflate demolitions, missing data, and game mode.

### 4.2 Measurement audit before modeling

Pin the parser revision and determine:

- Coordinate, rotation, angular-velocity, and boost conventions.
- Whether demolition indicators are events or persistent states.
- Whether player identifiers remain stable across games and seasons.
- Goal-time alignment with frames and clocks.
- Regulation, zero-second live play, overtime, kickoff, and post-goal states.
- Whether missing players indicate demolition, incomplete parsing, or absent roster slots.
- Whether event/stage paths actually determine bracket and elimination status.

Do not assume extra outputs described by a newer parser version exist in these arrays.

### 4.3 Coordinates and geometric roles

Use a focal-team coordinate system with the team attacking toward +y. Retain both teams and the ball.

For each player:

- `d_i(t)`: three-dimensional distance to ball.
- `r_i(t)`: within-team rank of `d_i(t)`.
- `closing_i(t) = -d d_i(t)/dt`.
- `depth_i(t) = y_ball(t) - y_i(t)`.
- Height, velocity, orientation, pairwise spacing, and relative velocity.

Ranks are **proximity roles**, not ground-truth tactical first/second/third men.

Initial hysteresis: change a rank only when the challenger is at least 100 verified game units closer for .3 seconds. Audit these provisional thresholds; test 50/100/200 units and .1/.2/.3 seconds. Mark near-ties and unavailable players as uncertain.

Define geometric cover using the **planar** own-goal-to-ball segment:

1. Project the player onto that segment.
2. Require projection within the segment.
3. Require lateral distance below 10% of field width.
4. Record cover count, depth, and distance continuously.

Handle near-zero segment length explicitly. Height and motion qualify this measurement; geometric cover does not guarantee a reachable save.

### 4.4 Touches and possession

**Do not treat `ball-has-been-hit` as a per-touch pulse.** Audit its actual semantics; it may be a kickoff latch.

At native 30 fps, define candidate contacts using:

- Ball–car proximity.
- A ball-velocity change inconsistent with recent free motion.
- A nearby local distance minimum.
- Exclusion or separate treatment of wall/floor/ceiling collisions.
- Rejection of simultaneous or ambiguous candidates.

Start with a 250-unit proximity threshold, ±2-frame temporal tolerance, and .15-second deduplication interval, subject to unit verification and training-only audit. Test threshold sensitivity. Estimate precision and missed-contact rates using independently reviewed clips.

Use “candidate touch” and “last confidently touching team,” not guaranteed possession. Primary rotation results must survive removal of all touch-derived features.

### 4.5 Context and outcomes

- Reconstruct score using goals strictly before the prediction time.
- Derive game outcomes from metadata.
- Derive series scores only from verified chronological game order and series membership.
- Identify overtime from audited state/clock behavior, not an assumed negative timer.
- Identify elimination pressure only when bracket format and pregame series state support it.
- Obtain historical opponent strength only from games preceding the analyzed game.

For horizon H, define:

`Y_H(t) ∈ {focal team scores first, opponent scores first, no goal}`

using the first goal in `(t, t+H]`.

A complete game ending without a goal before H is an observed absorbing end state. A truncated or corrupted replay is censored, not automatically a no-goal example. Report a sensitivity analysis excluding windows near game termination.

## 5. Representation and interpretation pipeline

### 5.1 Primary behavioral encoder

Each frame is a seven-node graph: six cars plus ball.

- Node features: geometry, motion, orientation, availability.
- Edge features: relative positions/velocities, distance, same-team relation.
- Shared spatial encoder: three attention/message-passing layers, initial width 128.
- Temporal encoder: a trained GRU or compact temporal Transformer.
- Outputs: player-equivariant states and a team-level representation using within-team pooling.

The primary vocabulary excludes:

**score, clock, team/player identity, season, event, stage, outcomes, and boost.**

Boost is omitted from the primary vocabulary because resource-dependent behavior is itself a research question. A resource-inclusive encoder is a separate descriptive sensitivity analysis. Exclusion avoids direct encoding of tested variables; it does not remove behavioral confounding.

Train with:

1. Masked reconstruction of node geometry/motion and pairwise relations.
2. Short future-state prediction at .5, 1, and 2 seconds.
3. Consistency under valid symmetry and player-index transformations.

Use normalized losses, initially:

`L = L_masked + L_future + 0.1 L_consistency`.

Apply reconstruction to equivariant node outputs rather than forcing an invariant pooled vector to recover arbitrary player-slot ordering. Select loss weights using reconstruction, stability, and blinded interpretation on development data—not hypothesis p-values.

A multiscale contrastive objective is an optional ablation. Avoid false negatives from nearby windows in the same series. Do not use time reversal or arbitrary spatial scaling as behavior-preserving augmentations.

### 5.2 Vocabulary and grammar

Fit PCA/scalers, encoder, cluster centers, and any motif-mining thresholds on training data.

Evaluate K ∈ {6, 8, 12, 16}. Select one primary configuration using 2025 reconstruction, stability, coverage, and blinded interpretation. Freeze it before 2026.

Separate:

- **Window motifs:** recurring six-second coordination patterns.
- **Role-event grammar:** sequences of persistent proximity-role changes.
- **Motif grammar:** transitions between non-overlapping window motifs.

Overlapping windows may support visualization but cannot establish higher-order grammar without a non-overlapping sensitivity analysis.

If discrete clusters are unstable, report continuous coordination axes and density structure. Do not force a tactical taxonomy.

### 5.3 Interpretation

For each motif show:

- A medoid.
- Random members from different series.
- A boundary case.
- A counterexample or failure case.
- Quantitative descriptors and uncertainty.

Use at least two independent knowledgeable raters, preferably three. Hide team, season, score, and future outcome during naming. Collect agreement and uncertainty before exposing context.

Human annotation is evaluation, not required tactical supervision. Attention maps alone do not establish an explanation.

## 6. Seven research questions

All questions inherit the grouped statistics, split discipline, and robustness protocol in Sections 8–9.

### RQ1. Does three-player rotation have a reusable grammar?

**Hypothesis.** Coordination contains recurring multi-step sequences beyond static geometry, first-order role transitions, and dwell times.

**Why fun.** Viewers may recognize “sentences” such as approach → withdrawal → cover → re-entry.

**Operationalization.**

Track persistent nearest-player changes and each player’s depth/closing speed. A descriptive relay candidate is `i → j → k → i` within eight seconds, with withdrawal by the previous nearest player. This is a transparent descriptor, not a tactical label.

Mine two- to four-token sequences from the frozen vocabulary, separately from direct role-event sequences.

**Method.** Temporal graph representations, clustering, run-length encoding, and sequence mining. Compare first-order semi-Markov and higher-order sequence descriptions.

**Statistical test.** One confirmatory global statistic measures excess higher-order structure. Generate null sequences preserving first-order transitions, state-specific dwell distributions, reset boundaries, and sequence lengths. Fit null parameters on training data. Aggregate statistics by series, with series-bootstrap confidence intervals. Correct individual motif tests separately.

**Robustness.** Five seeds, all specified K values, rank thresholds, 4/6/8-second windows, fps subsampling, season/event holdout, non-overlapping tokens, field mirror, team swap, and within-team permutations.

**Expected visualization.** Animated anonymous-car medoids, role ribbons, a small transition graph, and a common sequence beside a plausible counterexample.

### RQ2. Are dangerous moments associated with rotation handoff gaps?

**Hypothesis.** Short gaps or overlaps during responsibility transfer are associated with subsequent conceding risk after accounting for current game geometry.

**Why fun.** A decisive moment may be a half-second of uncovered space rather than an obviously bad formation.

**Operationalization.**

Anchor on persistent nearest-player handoffs. Measure:

- Time from the old nearest player’s sustained withdrawal to another player’s sustained approach.
- Fraction of the next second without geometric cover.
- Overlap: two teammates simultaneously closing on the ball within a provisional 1,000-unit radius for at least .2 seconds.
- Cover depth and retreat speed before and after the handoff.

Call these overlap/gap proxies, not definitive double commits. Use five-second future-goal outcomes, with 3/10-second sensitivity.

**Method.** Event-aligned descriptors and embeddings; distinguish covered handoff, uncovered handoff, overlap, and recovery.

**Statistical test.** Mixed-effects competing-outcome regression with team and series effects, adjusting for pre-handoff ball state, spacing, boost, score/time, season, and opponent. Report adjusted absolute-risk differences and series-bootstrap intervals. Match events on pre-event state as a sensitivity analysis.

**Robustness.** Threshold sweeps, exclusion of kickoffs and ambiguous ranks, no-touch versions, continuous rather than binary gap measures, seeds/K/fps/symmetry, and held-out seasons.

**Expected visualization.** Matched clips with similar starting ball states, handoff anatomy diagrams, and event-time cover curves.

**Interpretation limit.** A gap can reflect an already difficult situation. Association does not establish that changing that gap would prevent the goal.

### RQ3. Under pressure, do teams increase risk or redistribute responsibility?

**Hypothesis.** Late trailing play changes the distribution of coverage responsibilities; overtime may show a different response.

**Why fun.** “Clutch” could mean protecting the third player’s safety margin while another player becomes more aggressive.

**Operationalization.**

Primary contrast:

`[late − earlier, trailing by one] − [late − earlier, leading by one]`

where late is regulation time ≤60 seconds and earlier is 60–180 seconds.

Primary response: uncovered live-play fraction. Secondary responses: cover depth, rank-transition rate, overlap rate, role dwell times, and motif usage.

Analyze tied late regulation and overtime separately. Treat elimination-stage analyses as conditional on verified bracket data.

**Method.** Frozen vocabulary and continuous geometry measures; hierarchical regression with nonlinear time effects and score-by-time interactions.

**Statistical test.** Team/series mixed effects, context-standardized contrasts, and series-bootstrap intervals. Include current ball geometry, team resources, opponent strength, region, and season. The primary interaction enters the three-test Holm family.

**Robustness.** Late thresholds 30/60/90 seconds, within-team contrasts, matching/common-support checks, separate zero-second live play, overtime-duration adjustment, fps/symmetry/seeds/K, and season replication.

**Expected visualization.** Risk-versus-clock curves by score state, role-specific response plots, and matched late-trailing/overtime examples.

**Interpretation limit.** These are observable stakes and behaviors. They do not measure anxiety or psychological clutch ability.

### RQ4. Does style belong to a player, roster, or organization—and how does the meta evolve?

**Hypotheses.**

1. Context-standardized fingerprints repeat across independent series.
2. Player tendencies may persist through roster changes.
3. Seasonal differences can arise from changed motif usage, changed execution within motifs, or unfamiliar behavior.

**Why fun.** A player may bring a recognizable habit to a new roster, while an organization’s style changes after a transfer.

**Operationalization.**

Maintain distinct keys for player, exact three-player roster, and organization. Construct fingerprints from motif frequencies, transitions, proximity-role occupancy, coverage, and boost distributions.

Initially require at least 20 series across three events for a named roster fingerprint; evaluate threshold sensitivity. Compare fingerprints built from disjoint series.

For meta evolution, use the five supplied season labels. Decompose change into:

- Motif mixture.
- Within-motif continuous descriptors.
- Out-of-support/unassigned windows.

**Method.** Hierarchical compositional models, variance decomposition, and context standardization over common ball-zone/score/time/region support. Use frozen codebooks and an earliest-season-codebook sensitivity analysis.

**Statistical test.** Compare within-roster fingerprint distance across independent series halves against matched different-roster distances. Bootstrap complete series. For transfers, use matched player/roster controls and repeated-player effects. Seasonal models adjust for roster and event composition.

**Robustness.** Stable-ID audit, renaming checks, same-roster subsets, equal-series weighting, common-support restrictions, region/event holdout, seeds/K/fps/symmetry, and frozen 2026 evaluation.

**Expected visualization.** Fingerprint small multiples with intervals, player-transfer trajectories, and decomposition of meta change.

**Interpretation limit.** Roster changes are observational. Calendar differences cannot identify patch effects, coaching effects, or causal tactical progress.

### RQ5. Can pre-goal “势” be measured before the goal?

**Hypothesis.** Recent coordinated behavior contains prospective scoring information beyond the current game state.

**Why fun.** It tests the feeling that pressure is building, including attacks that eventually fail.

**Operationalization.**

Sample live-play times prospectively, without knowing whether a goal follows. Define:

`V10 = P(focal first goal within 10 s) − P(opponent first goal within 10 s)`.

Fit a history model using the previous six seconds and a snapshot model using the same current geometry, resources, score, and clock. Define:

`m(t) = V10_history(t) − V10_snapshot(t)`.

This measures historical predictive information. A value slope is an additional visualization, not independent proof of momentum.

**Method.** Calibrated competing-outcome models with series-level cross-fitting. Compare matched current states with different histories. Give snapshot and history models comparable capacity and calibration treatment.

**Statistical test.** Paired series-bootstrap differences in Brier score/log loss; test association of cross-fitted `m(t)` with actual future outcomes after current-state adjustment. Report calibration and overlap failures.

**Robustness.** Horizons 5/10/20 seconds, history shuffle controls, non-overlapping anchors, no pre-goal-only sampling, censoring sensitivity, season holdout, and architecture/seed/fps/symmetry checks.

**Expected visualization.** Prospective pressure timelines with confidence bands, successful attacks, failed pressure spells, and visually similar states with different histories.

**Counterfactual extension.** Retrieve observed alternative continuations from close historical matches. Only after calibration and support checks, use a conditional trajectory model to illustrate plausible alternatives. Label these **model-based scenarios**, not identified causal effects. State edits such as extra boost or a relocated defender are sensitivity analyses; they do not show what a feasible player action would have caused.

### RQ6. How do teammates compensate for low boost or demolition?

**Hypothesis.** Resource depletion and temporary absence are followed by recognizable role substitutions and coverage responses.

**Why fun.** It reveals support work that a goals-and-assists summary misses.

**Operationalization.**

After scale audit, mark low boost as <20% of maximum for at least .5 seconds; test 5/10/20%. Identify demolition onset from validated indicator transitions.

Measure teammate takeover latency, cover, approach speed, and role occupancy over the next three seconds. Separate true absence from parser missingness. Condition on pre-event geometry and teammates’ resources.

**Method.** Event-centered graph/temporal representations and matched response trajectories. Compare complementary responses with simple velocity synchrony.

**Statistical test.** Mixed-effects event-time models with player/team/series structure. Compare event trajectories with matched non-event trajectories and inspect pre-event trends. Bootstrap by series; include both exposure types in exploratory multiplicity control.

**Robustness.** Boost thresholds, demolition decoding, reset exclusion, missingness sensitivity, team-total-boost adjustment, no-touch versions, season holdout, and shared seed/K/fps/symmetry checks.

**Expected visualization.** Boost-and-role ribbons, takeover-latency distributions, and successful/failed compensation pairs.

**Interpretation limit.** No boost-pad state or controller intentions are supplied. Do not claim intentional boost stealing, sacrifice, or deliberate baiting.

### RQ7. Does a series contain a tactical conversation?

**Hypothesis.** A team’s later motif choices depend on earlier opponent behavior beyond its own previous behavior and game result.

**Why fun.** A best-of series may contain responses and counter-responses rather than repeated independent games.

**Operationalization.**

For consecutive games in a verified series, summarize context-standardized opponent behavior in game g and focal-team behavior in game g+1. Include own prior behavior, prior result, game index, pregame series score, and roster continuity.

A secondary event study compares behavior after conceding with matched non-goal times, excluding kickoff and accounting for the changed score.

**Method.** Hierarchical lagged compositional models and exploratory change-point analysis.

**Statistical test.** Test the incremental association of past opponent motifs with next-game focal motifs. Permute opponent histories only within matched season/region/stage/strength/roster-eligibility strata, keeping whole series blocks intact. If exchangeable matches are inadequate, report descriptive uncertainty without a permutation p-value.

**Robustness.** Sham boundaries, game-order trends, previous win/loss controls, same-opponent subsets, balanced series lengths, event holdout, and seed/K/fps/symmetry checks.

**Expected visualization.** A series timeline showing motif use, uncertainty, outcomes, and apparent responses.

**Interpretation limit.** This is evidence consistent with adaptation, not proof of coaching, communication, or deliberate opponent modeling.

## 7. Baselines as controls

| Control | Scientific purpose |
|---|---|
| Handcrafted descriptors + k-means | Can readable geometry already explain the patterns? |
| PCA + k-means | Is the result mostly low-dimensional variation? |
| Handcrafted rule descriptors without clustering | Do conclusions depend on a learned vocabulary? |
| GRU autoencoder | Is temporal structure useful without graphs? |
| Static graph encoder | What is lost without history? |
| TAGNet-style reconstruction + fixed seeded GRU | Faithful methodological control for the supplied paper |
| Same graph encoder + trained temporal aggregator | Is temporal learning useful for interpretation and stability? |
| Logistic/GBDT snapshot value model | Is claimed momentum already explained by current state? |
| Temporal MLP/GRU value model | Does a sophisticated graph model materially change the behavioral conclusion? |

TAGNet-style controls use RLCS-appropriate geometry/occupancy targets; they are adaptations, not exact CS2 reproductions.

Compare reconstruction only when targets and evaluation samples match. Do not rank methods by silhouette across unrelated feature spaces. A simple control supporting the same substantive result strengthens the study.

Predictive adequacy metrics:

- Goal/outcome models: log loss, Brier, classwise calibration, ECE with binning sensitivity, AUROC and AUPRC.
- Forecasting: ball/player ADE and FDE, with player correspondence preserved.
- Representations: stability, masked reconstruction, future prediction, and frozen probes of derived descriptors.
- Interpretation: blinded agreement, prototype representativeness, failure cases, and coverage.

No metric alone establishes tactical meaning.

## 8. Splits, sampling, and statistical protocol

### 8.1 Primary split

| Partition | Seasons | All-mode games before eligibility filtering |
|---|---|---:|
| Train | 2021–22, 2022–23, 2024 | 34,416 |
| Validation | 2025 | 7,081 |
| Test | 2026 | 7,762 |

Compute the actual 3v3-by-season cross-tab during P3; it is not supplied.

Keep complete series together. Resolve duplicates and conflicting group membership before splitting. Both team perspectives, all games, and all windows from a series remain in one partition.

No encoder adaptation, clustering, normalization, naming, threshold selection, or hyperparameter choice uses 2026.

### 8.2 Event-wise secondary evaluation

Use only pre-2026 data. Reserve whole events, including their constituent series, with season/region coverage recorded. Use nested event-grouped development folds and a preassigned held-out event set.

Refit every learned preprocessing component within each fold. This evaluation tests event transfer and does not replace the chronological 2026 confirmation.

### 8.3 Sampling

- Primary inputs: six seconds at 10 Hz, 60 frames.
- Native 30 Hz: event extraction and measurement audit.
- Sensitivity: 4/6/8-second windows and 5/10/15/30 Hz.
- Training: sample series, then games, then valid live-play times.
- Discovery sampling: balance training coverage across seasons/regions without using outcomes to select interesting clips.
- Inferential evaluation: deterministic prospective anchors six seconds apart, with a fixed randomized phase per game.
- Event analyses: retain all eligible events, then account for series dependence.
- Do not cross goals, kickoff resets, replay discontinuities, or game boundaries in input histories.
- Treat zero-second live play separately from a stopped clock.
- Record inclusion probabilities. Restore population weighting when estimating prevalence from balanced samples.

Outcome-enriched sampling is allowed for model fitting only with appropriate weighting/calibration. Test prevalence and behavioral estimates use the declared evaluation sampling.

### 8.4 Dependence and estimands

Frames are not independent observations.

Prefer team–series–context summaries for prevalence and continuous behavioral comparisons. For event/outcome models use hierarchical models and clustered uncertainty.

Typical structure:

`response ~ focal contrast + pre-event context + season + region + team effect + opponent effect + series effect`

Add event or roster structure when supported. Do not include mechanically redundant player/roster/team effects without identifiability checks.

Use:

- 2,000 complete-series bootstrap replicates, preserving both teams and all games.
- Event-bootstrap and multiway team/series sensitivity analyses where feasible.
- Overdispersion checks for counts/proportions.
- Restricted permutations appropriate to the specific exchangeability assumption.
- Absolute effects and confidence intervals, not p-values alone.

Random series intercepts do not automatically remove temporal autocorrelation; retain clustered/block uncertainty and aggregation.

### 8.5 Multiplicity and confirmation

Freeze at most three confirmatory contrasts before 2026:

1. RQ1 global higher-order grammar statistic.
2. RQ3 late-by-score coverage interaction.
3. RQ4 independent-series fingerprint persistence.

Apply Holm correction across these three tests at familywise .05.

RQ2 can replace RQ4 before test opening if identity coverage is inadequate and handoff measurements are validated. Record the substitution and rationale before seeing 2026 outcomes.

Pool all remaining tested exploratory contrasts—including individual motifs, contexts, horizons, and transfer comparisons—into one declared BH procedure at q = .05. Report the tested family and all results. Do not create independent significance opportunities by splitting exploratory tests into convenient families.

Seeds, K values, and fps settings are sensitivity analyses of the same data, not additional independent samples.

### 8.6 Symmetry

For a field transformation R:

- Positions and linear velocities transform as `Rv`.
- Angular velocities transform as `det(R) Rω`.
- Orientations must be converted and transformed consistently.
- Goal locations, score sign, team labels, and outcome classes transform with the perspective.

Test left/right reflection, team swap with appropriate field transformation, and within-team player permutations. Preserve player correspondence through time.

Require invariant team summaries or correctly equivariant outputs to numerical tolerance appropriate to the implementation. Investigate any materially different scientific conclusion under symmetry.

## 9. Ranked headline findings to pursue first

| Rank | Candidate headline | Why prioritize | Main gate |
|---|---|---|---|
| 1 | **Three-player rotation has a reusable temporal grammar** | Distinctively Rocket League; visually compelling; does not require accurate touches or future outcomes | Stable patterns beyond geometry, dwell time, and first-order transitions |
| 2 | **Pressure changes who provides cover** | Understandable behavioral contrast with clear context and measurable responses | Common support, reliable clocks/score, corrected interaction, 2026 replication |
| 3 | **Style persists across series, while roster and seasonal changes alter its expression** | Strong scouting and meta-evolution narrative | Stable identities and enough independent series |

RQ2 supplies a possible consequence of the grammar—handoff-associated vulnerability—without being required to rescue the paper. RQ5 momentum/counterfactual work is exploratory until prospective calibration and overlap pass.

A precise finding that pressure has little additional association after state adjustment is publishable evidence if the interval rules out meaningful changes.

## 10. P3: small, then scale

### P3-A. Data and measurement audit

Use approximately 100 complete training series across seasons, regions, and stages.

Deliver:

- Mode/season/event/series ledger and duplicate audit.
- Coordinate, clock, goal, boost, missingness, and demolition checks.
- At least 200 reviewed contact candidates plus sampled non-candidates.
- At least 100 reviewed rank/handoff events.
- Symmetry and player-index invariance checks.
- A measurement error report and exclusion policy.

If touch reliability is inadequate, continue with rotation analyses without touch supervision. If bracket interpretation fails, omit elimination claims.

### P3-B. Small discovery study

Use roughly 200 training series and a separately selected 2025 validation subset.

Run handcrafted/PCA, GRU, TAGNet-style, and trained graph-temporal controls. Start with three seeds, then extend promising configurations to five.

Deliver:

- A small atlas of patterns with random members and counterexamples.
- Blinded interpretation results.
- Preliminary prevalence and stability estimates.
- Feasibility counts for pressure cells and repeated rosters.
- Pilot uncertainty and power simulations based on independent series.

Progress only if measurements and at least one interpretable behavioral axis are credible. If discrete clusters fail, switch to continuous descriptions before confirmation.

### P3-C. Scale selectively

Increase to approximately 10% of training series, then the full training set if estimates or rare contexts remain imprecise.

Available environment: A100 80 GB SLURM nodes, torch 2.5.1, torch_geometric 2.8.1, torch_scatter, no pyg-lib.

Implementation plan:

- Seven-node dense graphs; no neighborhood-sampling dependency.
- Verify CUDA/PyG/torch_scatter compatibility in a smoke job.
- Use ordinary tensor operations if compiled graph extensions are unnecessary.
- Stream frame shards and cache compact derived features/embeddings.
- Use mixed precision after numerical checks.
- Benchmark throughput, memory, and I/O on a short job before estimating full cost.
- Use SLURM arrays for seeds and a limited ablation set.
- Avoid a full seed × K × fps × architecture grid; reuse embeddings where valid.

Start with batches of 32–64 windows and profile upward. Hardware availability does not justify unnecessary architecture complexity.

### P3-D. Freeze and confirm

Before opening 2026 results, freeze:

- Eligibility, sampling, and feature definitions.
- Vocabulary and semantic names.
- Primary contrasts and effect-size interpretation.
- Statistical formulas and correction families.
- Matching/calibration procedures.
- Robustness matrix and case-selection rules.

Then run one planned 2026 confirmation. Any post-test redesign becomes exploratory and requires new confirmation data.

## 11. P4 convergence criterion

P4 converges when the study supports **two or three interesting, credible, interpretable findings**, including precise nulls where appropriate.

Required evidence:

1. **Interpretability:** independent raters can describe the relevant behavior; random members support the interpretation.
2. **Measurement validity:** clock, rank, cover, and any used touch/resource events pass their audits.
3. **Statistical credibility:** meaningful effect estimates, grouped uncertainty, declared multiplicity control, and no frame-count pseudoreplication.
4. **Generalization:** the frozen analysis survives 2026 confirmation and event-wise sensitivity.
5. **Robustness:** conclusions remain defensible across seeds, reasonable K/threshold/window/fps choices, and valid symmetries.
6. **Honest scope:** confounded associations remain associations; scenarios remain model-based; unsupported identities or bracket labels are excluded.
7. **Representative evidence:** typical cases, failures, and counterexamples are reported.
8. **Reproducibility:** manifests, parser revision, grouping, exclusions, derived-feature definitions, seeds, and analysis code are recorded.

Before confirmation, set practically meaningful effect ranges using pilot measurement precision and blinded domain review—for example, seconds of handoff delay or percentage points of uncovered play. A tiny significant effect from millions of correlated frames is insufficient.

Stop scaling when additional data/model capacity no longer changes the substantive conclusions or materially narrows relevant uncertainty. Do not keep searching architectures or hypotheses until something becomes significant.

---

