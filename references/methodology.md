# Methodology for source-bound experiment planning

Use this reference to construct or revise the supplied candidate plans from the actual case and its finite domains. This is a planning method, not a laboratory result, universal design template, or substitute for local review. Follow the case language and preserve every original `output_contract` field and `case_id`.

## 1. Establish the evidence boundary

- Read `case.json`, the task text, and the actual cited sources before interpreting labels or filenames. Retain all supplied candidate versions rather than silently merging them.
- Tag each material statement as `case_fact`, `scenario_contract`, `source_observation`, `external_method`, `derived_value`, `planning_assumption`, or `unknown`; attach a precise source locator and, for derived values, inputs plus formula.
- Treat organizer prices, stock, and booking windows as prospective scenario inputs. They authorize arithmetic within the scenario, not claims of real quotes, inventory, reservations, approvals, or future performance.
- Keep unknown values unknown: missing price, duration, yield, or availability is not zero or unlimited. Distinguish missing input, demonstrated infeasibility, and tool failure.
- Methods literature supports reasoning only; it does not supply case-specific settings, acceptance limits, material equivalence, or measured responses.
- Use deterministic helpers for domain membership, arithmetic, capacity, dependency/calendar checks, and output structure. Use the model for source interpretation, scientific alternatives, causal reasoning, and revision rationale—not to bypass a failed helper check.

## 2. Translate the goal before choosing conditions

For each candidate, record the primary question in a short `objective` block.

- For an engineering goal, specify the function or process, operating context, response metric, required performance or acceptance rule with its source, and verification conditions. Do not force causal or clinical terminology onto throughput, yield, feasibility, robustness, or measurement-validation goals.
- For a comparative goal, specify target scope, exactly versioned intervention and comparator, primary outcome and measurement time, population-level or run-level summary, and treatment of loss, rescue, replacement, or early stopping. Adapt the estimand discipline in [ICH E9(R1), A.3.3–A.3.4](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf) without importing clinical endpoints wholesale.
- State the scientific significance or engineering requirement separately from statistical significance. Non-significance is not equivalence; equivalence or non-inferiority needs a justified margin and suitable design.
- Write identification assumptions relevant to the system: consistency of intervention versions, independent assignment where claimed, interference or pooling, and limits on generalizing beyond the tested batches, donors, materials, or devices.
- If the objective is still ambiguous, give conditional alternatives and identify the decision owner; do not invent a goal from a domain label.

## 3. Operationalize variables and unit hierarchy

Create one row per intervention, outcome, blocking factor, nuisance variable, QC metric, and safety indicator with these fields:

`variable_id | role | operational_definition | material/matrix | method/instrument | unit | setting_or_measurement_range | time/position | derived_formula | performance_evidence | source_locator`

- Distinguish an allowed setting domain from a device's operating range and from the measurement method's validated/reportable range. Resolution, calibration, selectivity, detection/quantification limits, and matrix suitability must support the intended decision; unknown performance stays unknown.
- For every derived outcome, give only the formula for the chosen derivation: exact raw inputs, background or reference treatment, normalization, aggregation level, units, and handling of missing or below-limit readings. Do not list unrelated formulas.
- Explain why the primary outcome represents the scientific construct or engineering function rather than merely being easy to measure. Apply the fit-for-purpose distinction in [ICH Q2(R2), §§1–3](https://database.ich.org/sites/default/files/ICH_Q2(R2)_Guideline_2023_1130.pdf) without importing pharmaceutical validation examples as universal thresholds.

Then draw the unit hierarchy before assigning `n`:

`inference scope -> independently assignable experimental units (EUs) -> independent runs/batches -> wells, sections, fields, cells, or readings (observation units)`

- An EU must be independently allocated, independently exposed to the intervention, and sufficiently free from interference for the intended contrast. Multiple readings within one EU improve measurement precision but do not create independent treatment replication; see [Lazic et al., 2018](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.2005282).
- Report counts at every level, including shared clusters, donors, cages, preparation batches, and repeated runs. Identify whole-plot units when a factor can only change for an entire batch or device load.
- Prespecify whether observations are aggregated to EU summaries or analyzed with an appropriate hierarchical model. A model cannot repair the absence of independent EUs.

**Freeze the primary estimand and analysis path.** Write the ordered map `source readings -> occasion summaries -> experimental-unit summaries -> treatment/cluster traits -> composite or primary contrast`. For repeated measurements, specify the time window, aggregation or longitudinal model, weighting, and whether the aggregate or individual readings undergo normalization, reciprocals, ratios, or logarithms. `mean(f(x))` need not equal `f(mean(x))`; the order belongs to the scientific question, not to whichever implementation is shortest. Preserve sampling and missingness in this map so technical observations cannot dominate weights or masquerade as independent units.

**Resolve informative zero and loss explicitly.** Distinguish a genuine zero allowed by the measurement domain, an unmeasurable outcome caused by loss/death, missingness for other reasons, and below-detection measurements. If a proposed ratio or logarithm is undefined at a genuine zero, report that incompatibility rather than adding an arbitrary constant. Keep the biological/engineering zero as a result, prespecify an allowed separate or alternative estimand/sensitivity analysis with its changed interpretation, and assess whether complete-case selection removes exactly the units the target question is about. Monotonic reversal of an ordinal score does not establish meaningful equal spacing, a natural zero, or a defensible retention ratio. Such a transformation remains an assumption needing approval or an explicitly changed target, even if numerically convenient.

Do not end at a direction label when the complete operational algebra is absent. State which pieces are sourced, which proposed rules remain conditional, and what the decision owner must freeze before unblinding or execution. This does not abolish a useful conditional plan; it prevents claiming reproduction of a source estimator that was never fully specified.

## 4. Derive controls and bias control from alternatives

For each control, complete:

`alternative explanation -> exact control condition -> inference enabled -> residual alternative -> validity consequence if failed`

- Consider only controls that address real alternatives: untreated baseline for natural state, vehicle/sham for handling or solvent, active/reference comparator for relative performance, and dose/condition levels for response shape.
- Keep scientific comparison groups separate from assay and process QC such as blanks, no-template/no-enzyme controls, calibration checks, positive detection controls, and internal process controls. Do not count QC as a biological or engineering treatment group.
- A positive detection control supports interpretation of a sample non-detect only within its demonstrated scope; it does not prove a mechanism. A failed required control affects run validity, not the biological null.
- If no concurrent control can identify the target contrast, limit the claim or redesign; historical observations are not automatically exchangeable controls.

Build a `batch_by_treatment` allocation table containing every treatment, scientific control, and required QC by date, preparation batch, plate/load, device, and operator where relevant.

- Block a small number of important, controllable nuisance factors and randomize allocation and processing/readout order within blocks where feasible. Do not allow treatment and batch to be completely confounded and then promise computational removal.
- Respect hard-to-change factors with restricted randomization or a split-unit structure. Record the randomized object, method, constraints, and seed as `planned` until actually generated.
- State the purpose and feasibility of allocation concealment and blinding at intervention, outcome measurement, and analysis. If safety or visible treatment prevents one stage, retain feasible blinded measurement/analysis and disclose residual bias.

**Turn source safeguards into an audit table.** For each source-supported requirement, retain `locator -> exact artifact/specimen/actor -> bias or failure excluded -> blinded party/acceptance owner`. Do not replace this with “randomization/blinding planned.” Where the source requires image, SEM, or indentation readout to be blind to both family and treatment, preserve both clauses, the responsible observer, and the rule that specimen order cannot reveal treatment. Independent scorers and consensus can be process QC; they are not independent experimental units. An image or another technical count is a measurement, not a new biological replicate.

**Track physical loops as well as EUs.** A tank, vial, well, or individual may be nested inside an experimental loop/circuit while not being an independently plumbed treatment loop. If there is only one physical loop per treatment, do not turn many nested recordings into independent loop-level replication. State what that limits (chemistry versus block/family versus measurement observations) and how the loop-term enters the intended inference instead of demanding a generic loop count.

Retain source-version conflicts: for example, textual group size conflicts with a figure/table caption, or bibliographic differences between a preprint and publisher version. Do not silently choose the convenient statement or merge colored plot points, wavelengths, molecule types, device series, or instrument modes. Each candidate needs its applicable scope or an explicit unresolved source question, with the relevant consultation.

## 5. Select the design for the actual question

| Goal | Candidate structure to consider | Required disclosure |
|---|---|---|
| One prespecified comparison | Completely randomized, paired, or randomized block design | Primary contrast and EU |
| Interactions among a small number of factors | Full factorial only when those interactions justify its runs | Estimable interactions and run burden |
| Early multi-factor screening | Purpose-fit fractional factorial or screening design | Aliasing and required follow-up |
| Local continuous optimization | Response-surface design with suitable center/validation runs | Model region, curvature, prediction uncertainty |
| Fixed-total component proportions | Mixture design | Sum and component bounds |
| Irregular finite candidates under a prespecified model | Model-based optimal or exchange design | Model dependence and non-global algorithm risk |

Use [NIST §5.3.3](https://www.itl.nist.gov/div898/handbook/pri/section3/pri33.htm) to distinguish comparative, screening, response-surface, mixture, and regression goals. Do not default to full factorial, omit necessary confirmation of a predicted optimum, or hide information lost by a smaller design.

## 6. Compile run-level resources and calendars

Define the atomic run or batch explicitly, then create a row for every planned run:

`candidate/version | run/step | batch | treatment/control/QC | EU count | observation count | sample amount | each reagent amount | device/session | setup+processing time | operator | predecessors | allowed window`

- Sum samples, reagents, consumables, and device sessions across treatment EUs, scientific controls, assay QC, technical observations when they consume resources, and any explicitly authorized reserve. Never count technical observations as independent EUs merely to inflate `n`.
- State batch capacity in the same units as demand (samples, wells, volume, load, or time), including spaces consumed by controls/QC. Allocate all demand to batches and show capacity remainder; do not report only per-treatment needs.
- Document whether a control, master mix, prepared sample, or device session may be shared. Reuse only when scientifically valid, contractually allowed, and compatible with timing/stability; avoid both double counting and unsupported sharing.
- Multiply quantities only along the actual hierarchy. Apply ceiling/package rounding only when that exact contract requires whole packs or billed increments; otherwise use its stated proportional rule. Preserve unrounded and rounded quantities and the rounding basis.
- Build the schedule from dependencies, delivery and holding limits, explicit windows, setup/changeover, and exclusive shared resources. Parallel tasks shorten elapsed time only when they share no constrained person, device, or material.
- Calculate each candidate independently. Unknown prices or windows block the corresponding determination rather than becoming free or available. A feasible result means feasible under the supplied scenario contract only.

**Keep the offered catalogue separate from actual demand.** Start each calculation from the candidate's own `run/step → service_id → material/sample/observation` edges, then include its required control and QC demand. A service appearing in a price table, shared instrument pool, or sibling candidate is not thereby a requested service. Do not derive purification, optical panels, instrument modes, or any other measurement merely because it could be offered. If a source excludes an operation, an instrument modality, or an isolate-dependent diagnostic, carry that exclusion through calculations, bookings, narrative, and revisions. Required early identity/QC work is not a hypothetical future batch for synthesis planning, nor an optional charge to remove for economy; if a source-fixed pack supplies it, preserve the pack's actual coverage and granularity rather than inventing individual line items.

**Check temporal meaning and allocation confounding.** For every prerequisite identity/activation/calibration/release gate, map the exact source obligation to evidence, predecessor, and interval. A gate scheduled after the work it must release cannot yield a merely resource-feasible pass; if terms such as “before release” are ambiguous, make the interpretation and conditional decision explicit instead of assuming convenient sequencing. Where actual dates and parameter/configuration allocation coexist, cross-tabulate them and inspect whether configuration and day/window are entangled. A shared late block or a common environmental label does not guarantee additive, configuration-independent balance. Do not claim variance reduction, a paired design or a shared calibration model, or an identified contrast without its assumptions and unit-level covariance; if a proposed correction model is not supported by the source and design, delimit the inference to an appropriate descriptive/conditional scope.

Evaluate failure-triggered recalibration and compensation as real additional resource consumption, not as a discretionary footnote. Recompute every affected source-supported booking, cumulative cost, unit capacity, window quota, and global deadline before claiming that a fallback exists. If headroom is insufficient, preserve that failure and identify the required change in design, resource, or authorized scope.

## 7. Justify independent sample size, precision, and power

- State the primary analysis unit, model, sidedness, multiplicity policy, and whether the goal is estimation precision, hypothesis-testing power, or engineering acceptance. Technical replicates do not enter as independent group sizes.
- For precision goals, specify the confidence interval or other interval, target width/half-width with source, model assumptions, and EU-level variance inputs. Calculate only with a formula matching that exact interval and design.
- For power, require a defined primary contrast and analysis, scientifically meaningful effect `delta`, applicable EU-level variability, `alpha`, target power `1-beta`, and justified attrition/exclusion assumptions. Paired, clustered, repeated-measure, non-normal, interaction, split-plot, and sequential designs need their own formula or simulation.
- Use `statistics.NormalDist` only as a normal quantile/CDF implementation when the normal approximation is clearly applicable and `delta`, common EU-level `sigma`, `alpha`, and `beta` are explicitly sourced. For the specific equal-size, two-independent-group, common-variance normal comparison only:

  `n_per_group = ceil(2 * sigma^2 * (NormalDist().inv_cdf(1-alpha/2) + NormalDist().inv_cdf(1-beta))^2 / delta^2)`

  This formula does not establish applicability, supply its inputs, or cover other designs. Any sourced loss inflation and subsequent capacity/cost recomputation must be shown separately.
- If required inputs are absent or the model is unsupported, mark sample-size justification `underspecified`; name missing inputs. Report clearly labelled assumption-based sensitivity, attainable CI precision, or detectable-effect curves over feasible independent-EU counts instead of fabricated power.
- Never shrink `delta`, borrow an unjustified small-pilot variance, or choose `alpha`/`beta` to fit the budget. If all feasible sizes are uninformative for the primary goal, say so and propose changing the question or resources.

## 8. Search finite domains and rank without hiding tradeoffs

- Construct candidates only from allowed discrete sets/intervals and scientific compatibility rules. Exhaustively enumerate the feasible set when tractable; describe a result as globally optimal only after complete enumeration or a valid optimality certificate for the stated objective.
- For a sampled, heuristic, time-limited, or request-limited search, record algorithm, seed if used, visited candidates, stopping rule, and unexplored remainder. Label the result `best_found_under_search`, not global optimum.
- Apply hard safety/ethics and explicit case constraints first, then scientific identifiability and measurement/run validity, then scenario feasibility. Among survivors, compare primary information/precision/robustness before cost and duration using lexicographic priorities or Pareto fronts; do not collapse them into an invented weighted score.
- Preserve any organizer-specified hard thresholds and rubrics exactly. Show which scientific information is sacrificed by a cheaper or faster candidate rather than letting price compensate for an invalid primary contrast.
- Do not claim a predicted optimum has a measured future effect. Optimization based on one dataset needs independent confirmation or an explicitly exploratory label.

## 9. Recompute, version, and stop cleanly

- Every parameter, source, or logic change triggers full recomputation of design validity, unit counts, run table, package rounding, stock, cost, capacity, calendar, sample-size justification where affected, risks, and output validation—not just the edited field.
- For each version retain `version_id`, `parent_id`, input/source/helper versions, exact field diff, reason and evidence, old/new validation results, unresolved conflicts, and whether analyses are planned or exploratory. Replay deterministic checks on the same version and record any differences honestly. Never drop an original parent or replace it with null just because an audit covering only current candidates cannot resolve that external source version; preserve the original snapshot, resolve the source relationship truthfully, or report that specific verification as pending.
- After revision, inspect statements that described an old missing link, constraint, or failure. Move them to the explicitly labeled original scope or adapt them to the new conditional state; do not leave a now-contradictory claim in the repaired plan. Every validation pointer must resolve to a real artifact that actually covers the cited original/revised version and failure/approval scope. A final repaired-candidate report does not automatically contain the original failure; reference the actual original report separately when needed.
- Permit at most two externally motivated correction rounds, each tied to a concrete helper failure, source/constraint correction, or identified scientific validity problem. Avoid cosmetic loops and unbounded retesting; save an honest partial result if budget or evidence runs out.
- Audit lineage changes themselves: unique parents/dam and sire usage, shared cohort identities, independent EUs, and changes in relevant relatedness or coverage. Never claim “other demands unchanged” solely because cost quantities and booking counts are identical; altered relatedness may change both identifiability and precision.
- For every directional or inverse transformation, link its parameter–formula–scope to the source or explicitly mark it as a proposed operationalization, not a recovered original algorithm. Before logarithms, retain positivity, missingness/death/detection-limit rules, and exactly which entity is normalized.
- Treat duplicated statuses as a consistency gate, not a pass badge: derive them from a single per-version snapshot, and distinguish original versus repaired scope. Use [state-consistency.md](state-consistency.md) for mapped comparisons and explicitly record `not_run` where no appropriate comparison is available.
- Before release, replay the finite-domain and resource helpers, verify the original output schema and candidate lineage, and ensure that every scientific claim, unknown, assumption, and proposed action has the correct status and source.
