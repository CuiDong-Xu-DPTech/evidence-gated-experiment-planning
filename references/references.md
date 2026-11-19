# Method sources

These references motivated the workflow. They are not replacements for the actual case sources, current local SOPs, expert judgment, or appropriate law/ethics review. Cross-domain borrowing is structural; no regulatory scope or performance guarantee is claimed.

## Experimental questions, measurements, and controls

- ICH, **E9(R1): Addendum on Estimands and Sensitivity Analysis in Clinical Trials** (2019), A.3.3–A.3.4. Goal → design → measurement → analysis; its clinical terminology must be adapted, not forced onto all experiments. [Official guideline](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf).
- Hernán and Robins, **Causal Inference: What If** (2020), chapters 1–3. Define intervention, comparator, target scope, and identification assumptions before claiming an effect. [Authors' official copy](https://miguelhernan.org/whatifbook).
- Percie du Sert et al., **The ARRIVE guidelines 2.0** and explanation/elaboration (2020), particularly design, sample-size justification, inclusion/exclusion, randomization, blinding, and outcome measurement. [DOI 10.1371/journal.pbio.3000410 and 10.1371/journal.pbio.3000411](https://doi.org/10.1371/journal.pbio.3000411).
- ICH, **Q2(R2): Validation of Analytical Procedures** (2023), §§1–3. Performance, limits, range, precision, and criteria are tied to intended use, not treated as universal checklist numbers. [Official guideline](https://database.ich.org/sites/default/files/ICH_Q2(R2)_Guideline_2023_1130.pdf).
- Lazic, Clarke-Williams, and Munafò, **What exactly is ‘N’ in cell culture and animal experiments?** (2018). Distinguish experimental units from observations/technical repetitions. [DOI 10.1371/journal.pbio.2005282](https://doi.org/10.1371/journal.pbio.2005282).
- Lakens, **Sample Size Justification** (2022). Separate power, precision, and resource-constrained justification; never conceal missing effect/variance assumptions. [DOI 10.1525/collabra.33267](https://doi.org/10.1525/collabra.33267).
- NIST/SEMATECH, **e-Handbook of Statistical Methods**, [randomized block designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm), [design selection](https://www.itl.nist.gov/div898/handbook/pri/section3/pri33.htm), and [D-optimal choices](https://www.itl.nist.gov/div898/handbook/pri/section5/pri521.htm). Block known nuisances where appropriate; randomize properly; disclose model/aliasing restrictions in reduced designs. No default full factorial or D-optimality is assumed here.

## Risk, validity, and change control

- ICH, **Q9(R1): Quality Risk Management** (2023), §§4–5 and Annex I.2–I.3. Assess → control → communicate → review, including residual and newly introduced risk. Cross-domain use does not assert pharmaceutical regulatory coverage. [Official guideline](https://database.ich.org/sites/default/files/ICH_Q9%28R1%29_Guideline_Step4_2022_1219.pdf).
- IEC, **60812:2018 — Failure modes and effects analysis (FMEA and FMECA)**. Failure functions, effects, causes, and criticality are structured; severity rankings do not establish safety. [Official record](https://webstore.iec.ch/en/publication/26359).
- NASA, **GSFC-HDBK-8004: Fault Management Handbook** (2024). Detection signature, isolation, mitigation, and recovery are connected; its spaceflight severity rules are not universal laboratory limits. [Official handbook](https://standards.nasa.gov/sites/default/files/standards/GSFC/Baseline/0/GSFC-HDBK-8004_Approved_1.pdf).
- WHO, **Laboratory Biosafety Manual**, fourth edition (2020). Evidence-based local risk assessment precedes work; no generic visual checklist substitutes for it. [Official publication](https://www.who.int/publications/i/item/9789240011311).
- U.S. HHS, **Common Rule**, §§46.108, 46.109, 46.111, illustrating explicit human-subject review requirements only within its applicable legal scope. Other settings and countries require their own competent bodies. [Regulatory text](https://www.hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46/revised-common-rule-regulatory-text/index.html).

## Exact records, provenance, and external verification

- W3C, **PROV-DM** (2013), for entity/activity/agent and used/generated/derived/revised relationships; such links support traceability rather than truth by themselves. [Recommendation](https://www.w3.org/TR/prov-dm/).
- W3C, **Web Annotation Data Model** (2017), §4.2, for text quote/position selectors and their version limitations. [Recommendation](https://www.w3.org/TR/annotation-model/).
- IETF, **RFC 6901 JSON Pointer**, **RFC 6902 JSON Patch**, and **RFC 8785 JSON Canonicalization Scheme**, for source locators, executable change records, and hashable stable objects. Array order remains meaningful; decimal values represented as strings avoid unintended binary/rounding semantics. [6901](https://www.rfc-editor.org/rfc/rfc6901), [6902](https://www.rfc-editor.org/rfc/rfc6902), [8785](https://www.rfc-editor.org/rfc/rfc8785).
- NIST, **Special Publication 811**, chapter 7, for value × unit conventions and preserving meaningful precision. [Official guide](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-7-rules-and-style-conventions-expressing-values).
- Kambhampati et al., **LLM-Modulo Frameworks** (2024), a position paper motivating generated plans checked and repaired through external verifiers, not a guarantee of scientific correctness. [arXiv:2402.01817](https://arxiv.org/abs/2402.01817).
- Valmeekam et al., **PlanBench** (2023), and Huang et al., **Large Language Models Cannot Self-Correct Reasoning Yet** (2024), for separating language plausibility from constraint satisfaction and avoiding unsupported claims of unaided self-correction. [PlanBench](https://arxiv.org/abs/2206.10498), [self-correction limitations](https://arxiv.org/abs/2310.01798).
- Kolisch, **Serial and parallel resource-constrained project scheduling methods** (1996), for exact scheduling-construction concepts; resource availability changes calendar time beyond a simple precedence critical path. [DOI 10.1016/0377-2217(95)00357-6](https://doi.org/10.1016/0377-2217(95)00357-6).

The composition in this Skill is an engineering integration. It is not presented as a new general planning theory or a measured improvement over the platform baseline. Official evaluation supplies that evidence separately.
