# Entity identity and decision-sensitive review

The released NRC cohort uses reliable recipient UEIs. Every transaction has a UEI, so there is no live missing-identifier linkage problem to solve. The application preserves distinct UEIs even when the business names match. A parent-recipient comparison is a separate aggregation lens; a shared name or parent does not establish that two legal recipients are the same entity.

The research experiment asks a counterfactual: **when identifiers are hidden, which identity question is most useful to review because it can change a procurement conclusion?** It uses actual observed names, city/state values and obligations. It does not label fraud or misconduct, and does not test fraud detection.

## Reproduce

From the repository root, after installing requirements and obtaining the public snapshot:

```sh
python -m civicledger.linkage --replicates 20
python -m pytest tests/test_linkage.py -q
```

The default snapshot is `data/processed/transactions.csv`. Outputs live in `data/linkage/`: benchmark summaries, held-out feature files, separate label files, all held-out pair predictions, raw review replicate results and the explorer payload. All seeds are recorded. No separately billed API is used.

## Observations, labels and leakage controls

An observation is one distinct `(UEI, reported recipient name, city, state)` tuple in the three-year transaction snapshot. Transactions with the same tuple are grouped, retaining their signed net obligations and transaction count. This prevents thousands of identical transaction rows from inflating apparent linkage accuracy. One source award URL is retained for evidence.

UEI is the identifier-backed reference label. DUNS is largely absent in this cohort and is not needed. A fixed SHA-256 hash of each UEI assigns its observations to train (60%), calibration (20%) or test (20%) buckets. No recipient crosses splits. Names, cities and states are the only comparison features. UEI, DUNS, parent IDs, award IDs, URLs, spending, dates and split labels never enter the comparison model. Train identity labels estimate comparison parameters; calibration labels fit the probability mapping; test labels evaluate the frozen model and simulate review answers.

The natural cohort has 581 feature observations from 537 UEIs. Every UEI has one observed name; positive pairs chiefly represent city or state changes. This is a limited linkage challenge. The held-out test includes 113 observations, 103 entities, 6,328 all-pairs comparisons and only 11 matching pairs. A perfect result here cannot establish general alias-resolution performance. Same-name/different-UEI collisions exist in the full cohort but need not appear in the deterministic test split.

## Baselines, probabilities and error costs

Four methods share the same test pairs:

1. Exact raw-name equality.
2. Conservative normalized-name equality: uppercase, punctuation to spaces, trim. No legal suffix or informative token is silently removed.
3. A Fellegi–Sunter model evaluated with Splink 5.0.0 and an independent transparent likelihood-ratio calculation. Name comparison levels are exact, Jaro–Winkler similarity at least 0.95, at least 0.85, and other. City/state use exact agreement, disagreement, or missing. Train-labelled matching and nonmatching pairs estimate `m` and `u` level distributions with 0.5 additive smoothing. Missing comparisons contribute no likelihood ratio. The prior is the train pair match prevalence with 0.5 smoothing. Splink runs inference over all test pairs with those frozen parameters; the exported verification compares every probability against the transparent calculation.
4. The same probabilities calibrated using isotonic regression on calibration entities. Jeffreys beta(0.5, 0.5) smoothing within each fitted plateau avoids interpreting eight observed matches as certainty. A second monotone fit maps the smoothed rates. Neither test labels nor monetary consequences tune calibration.

The decision threshold is 0.5. Reports include precision, recall, F1, average precision, Brier score, expected calibration error (10 bins), bin counts and predicted/observed match rates. The illustrative error cost is `10 × false merges + missed links`, fixed before test evaluation. Pair-level Jeffreys intervals show finite support but are descriptive: pairs sharing observations are dependent, so these intervals can be optimistic. Calibration depends on pair prevalence; it does not automatically transfer to a candidate-block or real missing-ID population. Low Brier/ECE in this rare-match population must be read alongside positive-pair errors.

The source has only three comparison fields. City and state are correlated, violating the strict conditional-independence approximation. The calibrated scores are tested on held-out entities but are not universal business-identity probabilities. UEI agreement is also a proxy label rather than independent human adjudication or a beneficial-ownership registry.

## Coherent identity scenarios

The candidate graph connects pairs with calibrated score at least 0.05. For each connected component of at most seven observations, the implementation enumerates every set partition. A partition represents a complete, transitive entity grouping. Its composite-likelihood weight is

```
w(P) ∝ product over within-cluster pairs p(i,j)
       × product over separated pairs [1 − p(i,j)]
```

Weights normalize across the component's partitions. Independent components may be sampled, but edges are never sampled independently. A triangle cannot simultaneously state A=B, B=C and A≠C. A review answer conditions the entire set of component partitions, propagating transitive consequences. Contradictory answers with no supported partition raise an explicit error.

Components larger than seven are kept separate and listed as excluded rather than arbitrarily split. Disconnected matches are outside the scenario support. Both limitations can leave errors that review cannot fix. The finite graph cut and cluster-product weights are modelling assumptions, not an exhaustive identity posterior. **Calibrated pair scores do not make these cluster weights calibrated probabilities.** Scenario ranges and quantiles are sensitivity summaries, not confidence or credible intervals.

Each scenario recomputes positive-net concentration after summing signed obligations inside its clusters:

```
cluster_net = sum(signed federal_action_obligation in cluster)
exposure = max(cluster_net, 0)
HHI = 10000 × sum[(exposure / sum(exposure))²]
```

Negative transactions and negative-net observations remain present. Clipping occurs only after grouping for this nonnegative-share concentration definition; signed net obligations are separately reported. The denominator can change when a positive and negative observation are grouped. This is deliberate and tested.

## Review policies and original contribution

The review unit is a pair question: “Do these two observations share the reference recipient identifier?” In the experiment an oracle supplies the hidden UEI equality. Each policy receives the same pair budget and candidate components:

- Random chooses an unanswered informative pair uniformly.
- Uncertainty-only chooses the largest `q(1−q)` under current partition weights.
- Decision-sensitive chooses the largest expected reduction in the declared decision loss:

```
Var(HHI / 10000)
+ 0.1 × mean Var(top-three cluster membership by observed record)
```

For a binary query with same-entity probability `q`, its value is `q(1−q) × ||E[D|same] − E[D|separate]||²`, where `D` is the scaled HHI and membership vector. The factor 0.1 is fixed before evaluation and expresses an illustrative decision preference. It should be changed and retested for other policy decisions. This policy can prefer a less uncertain match that moves a conclusion over a highly uncertain, financially immaterial match.

The implementation uses coherent sampled worlds to estimate query consequences and then conditions exact component partitions on each answer. It reruns all metrics after each answer. Outputs include HHI absolute error against the hidden-identifier partition; 95% scenario quantile width; Kendall rank association of the modal sampled partition's grouped exposures against the reference; and `1 − 4 × mean variance(top-three membership)` as scenario membership stability. The rank association is agreement with the reference, while membership stability compares the supported scenarios.

Twenty fixed random seeds compare natural observed-record policies at equal budgets. The seed variation captures Monte Carlo and review-order variation, not a population confidence interval. A simulated pair query does not measure human review time. The study is an original implementation and bounded test of decision-sensitive identity review, not a claim of a new general linkage algorithm or established improvement across public procurement.

## Synthetic stress tests are separate

The stress benchmark adds artificial name variants to each source observation: legal-suffix removal and deterministic character swaps/deletions, plus simulated city/state missingness. Each original amount is split across its three copies, preserving signed totals. Entity splits remain inherited from the original identifier. A separate model and calibrator are fitted on the synthetic train/calibration entities. The synthetic policy experiment uses a fixed hash-selected subset of 30 test entities, up to five pair reviews and repeated seeds.

These artificial variants test mechanism and failure behavior. They are not observed reporting errors, not evidence that the real cohort has unresolved identity problems, and not a substitute for a larger, adjudicated external linkage dataset. The explorer labels this content as an experiment. Natural exact matching is an important baseline even when it wins.

## Sources

- [Splink documentation](https://moj-analytical-services.github.io/splink/) describes the Fellegi–Sunter basis, multiple-field requirements and correlation limitations.
- [Splink comparison creator](https://github.com/moj-analytical-services/splink/blob/master/splink/internals/comparison_creator.py) supports explicit comparison probabilities.
- [Splink training source](https://github.com/moj-analytical-services/splink/blob/master/splink/internals/linker_components/training.py) documents supervised label training and standard parameter estimation.
- [USAspending API source](https://github.com/fedspendingtransparency/usaspending-api) defines the transaction download contracts; the repository's retrieval manifest records the exact cohort and source snapshot.

## Bounded findings

The natural held-out benchmark gives precision and recall of 1.00 for exact name, normalized name, and the learned baseline on its eleven positive pairs. Exact matching already solves this particular held-out challenge. Calibrating the learned model improves its Brier score from approximately 0.0001005 to 0.00002468, but does not establish an advantage over the exact baseline. The test is small and has no within-UEI name variation.

In the real-record masked-identifier review experiment, the reference HHI is 2362.8120 within the held-out subset. Supported sampled scenarios span about 2350.6905–2362.8121 before review. At five pair reviews, mean HHI absolute error across twenty fixed seeds is 0.0270 for decision-sensitive review, 0.4467 for random review and 0.3822 for uncertainty-only review. The corresponding standard deviations are approximately 0.0053, 0.2002 and 0.1545. These are small differences in practical concentration terms. They show a mechanism advantage under the declared HHI objective, not a large change in procurement assessment.

The natural experiment's top-three observed-record membership survives all sampled scenarios, and its modal-partition rank association with the reference is 1.00. The conclusion is therefore stable despite the HHI sensitivity. Rank association uses observed records with each record assigned its cluster exposure, so entities with more location variants receive more weight than an entity-level ranking would. Conditional queue previews name the three grouped exposure clusters under each answer and explicitly report whether the selected observations change. Modal sampled support is not a confidence claim. A stable procurement-review shortlist is a useful negative result; the demo does not manufacture an unstable decision.

The synthetic stress benchmark is harder: exact-name recall is approximately 0.071, while the held-out calibrated model has precision 0.946 and recall 0.968. These figures describe invented perturbations of the source observations. In its thirty-entity policy subset, all three policies converge to the same HHI error of about 42.74 after five reviews, while the sampled scenario width is zero. That residual error is a model-support warning: candidate blocking eliminates true links in this stress subset (no component exceeds the size limit here); oversized-component exclusion can cause similar failures in other cohorts, and review within the retained support cannot recover it. A narrow scenario range alone does not establish correctness. The synthetic experiment does not show a five-review decision-sensitive advantage.

## Input lineage

Every final benchmark, review experiment and explorer payload records `source.snapshot_id` and `source.public_csv_sha256`. The adapter hashes the actual input bytes and rejects a mismatch with the retrieval manifest. Feature artifacts and label files derive from that exact public snapshot. A later source refresh requires recomputing linkage before combining outputs; cached linkage from a different digest must not be served with a newer warehouse.

The support audit makes that stress failure visible: all 11 natural reference links lie within enumerated components, while 8 of 126 synthetic reference links fall outside retained component support (support recall 118/126, about 0.9365). The synthetic reference partition is therefore unsupported. Both experiments export these counts and `reference_partition_supported`; later review results must be read with this flag.
