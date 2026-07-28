# Cross-locale generation GLMM analysis

This directory contains the analysis pipeline used for the first frozen
cross-locale results for Qwen2.5-VL-7B-Instruct and InternVL2.5-8B.

## Analysis scope

The primary binary outcome is `generation_correct`: the parsed generated A-D
label equals the gold label. The frozen analysis includes:

1. Full 6x6 RQ1 random-intercept GLMM.
2. Full 6x6 RQ2 dimension-interaction GLMM.
3. Item-specific matched random-slope sensitivity.
4. Thai-excluded 5x5 RQ1 random-intercept GLMM.
5. Item-cluster bootstrap descriptive summaries.

`scoring_correct` is retained in the validated derived tables but is not part
of this primary result set. Scoring-outcome models, 5x5 RQ2, Thai-specific
adjusted models, and formal joint cross-model comparisons are deferred
analyses.

## Statistical specifications

RQ1:

```r
correct ~
    question_language
  + gui_language
  + dimension
  + matched
  + (1 | parallel_id)
```

RQ2:

```r
correct ~
    question_language * dimension
  + gui_language * dimension
  + matched * dimension
  + (1 | parallel_id)
```

Random-slope sensitivity:

```r
(1 + matched || parallel_id)
```

The primary models use an item random intercept because every semantic item is
measured repeatedly across language conditions.

## Adjusted probabilities

Reported probability differences are item-marginal standardized contrasts.
The code uses 15-point Gaussian quadrature to integrate predicted
probabilities over the fitted normal item-intercept distribution. It does not
set the item random effect to zero and does not average observed item BLUPs.

Confidence intervals use 2,000 multivariate-normal fixed-coefficient draws.
The fitted item-intercept standard deviation is treated as a plug-in value, so
variance-component uncertainty is not propagated into these intervals.

For RQ2, dimension heterogeneity is first tested with an omnibus
likelihood-ratio test. Dimension-specific matched trends use Holm correction.
Probability-scale confidence intervals are pointwise intervals used to
describe effect size.

## Dependencies

Python dependencies are installed with the project. The R analyses require:

```r
install.packages(c(
  "lme4", "broom.mixed", "dplyr", "readr", "tidyr",
  "tibble", "MASS", "emmeans"
))
```

The commands below assume the `mpr-r-analysis` Conda environment and are run
from `01_code`.

## Build and validate analysis tables

```powershell
python -m mpr_crosslocale.analysis.build_glmm_table `
  --input results/summaries/6x6_qwen.zip `
  --git-revision HEAD `
  --output data/derived/qwen_glmm.csv `
  --validation-out results/analysis/qwen_validation.json

python -m mpr_crosslocale.analysis.build_glmm_table `
  --input results/summaries/6x6_internvl.zip `
  --git-revision HEAD `
  --output data/derived/internvl_glmm.csv `
  --validation-out results/analysis/internvl_validation.json
```

Omit `--git-revision HEAD` when the source ZIP is not tracked in the current
Git revision. Derived analysis tables are reproducible and ignored by Git.

## Descriptive bootstrap

```powershell
python -m mpr_crosslocale.analysis.descriptive_glmm `
  --table qwen=data/derived/qwen_glmm.csv `
  --table internvl=data/derived/internvl_glmm.csv `
  --csv-out results/analysis/descriptive_bootstrap.csv `
  --json-out results/analysis/descriptive_details.json `
  --bootstrap-replicates 5000 `
  --seed 42
```

The output retains an explicit `outcome` column. The frozen primary
interpretation uses only `generation_correct`.

## Full 6x6 RQ1

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rq1_glmm.R data/derived/qwen_glmm.csv `
  results/analysis/qwen/rq1_generation generation_correct 1

conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rq1_glmm.R data/derived/internvl_glmm.csv `
  results/analysis/internvl/rq1_generation generation_correct 1
```

## Full 6x6 RQ2

The frozen RQ2 results use the `fast` setting, which retains the same model,
likelihood, `bobyqa` optimizer, and `nAGQ = 1`, but skips the expensive
post-fit finite-difference gradient/Hessian calculation. Output directories
retain `_fast` to preserve this provenance.

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rq2_glmm.R data/derived/qwen_glmm.csv `
  results/analysis/qwen/rq2_generation_fast generation_correct fast 1

conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rq2_glmm.R data/derived/internvl_glmm.csv `
  results/analysis/internvl/rq2_generation_fast generation_correct fast 1
```

Each fitted model is checkpointed separately as an ignored RDS file, so a
rerun resumes from completed checkpoints.

## Random-slope sensitivity

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/random_slope_sensitivity.R data/derived/qwen_glmm.csv `
  results/analysis/qwen/random_slope_generation_fast `
  generation_correct fast 1

conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/random_slope_sensitivity.R data/derived/internvl_glmm.csv `
  results/analysis/internvl/random_slope_generation_fast `
  generation_correct fast 1
```

InternVL estimates the additional matched-slope variance at the zero boundary,
producing a singular fit that collapses to the random-intercept structure.
Qwen estimates a positive matched-slope variance without a singular fit. The
fixed-effect conclusions remain consistent with the primary models.

## Thai-excluded 5x5 RQ1

The final `rq1` argument prevents the optional 5x5 RQ2 models from being fit.

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/core5_glmm.R data/derived/qwen_glmm.csv `
  results/analysis/qwen/core5_rq1_generation standard 1 rq1

conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/core5_glmm.R data/derived/internvl_glmm.csv `
  results/analysis/internvl/core5_rq1_generation standard 1 rq1
```

## Interpretation order

1. Validation JSON and descriptive checks.
2. Convergence and singularity diagnostics.
3. Omnibus likelihood-ratio tests.
4. Item-marginal standardized probability differences.
5. Holm-adjusted dimension-specific matched trends.
6. Random-slope and Thai-excluded robustness analyses.

The `matched` coefficient is an association induced by the controlled language
pairing. It should not be presented as evidence for a general causal mechanism
outside this benchmark, prompt profile, and model configuration.

## Deferred analyses

The following scripts or analysis ideas are intentionally excluded from the
first frozen result set:

- `scoring_correct` GLMMs.
- Thai-excluded 5x5 RQ2.
- `thai_specific_glmm.R`.
- `compare_models_glmm.R`.
- `compare_models_rq2_glmm.R`.
- Qualitative REL/AEL error annotation.

These analyses should be committed with their results only if their associated
claims are promoted in a later research phase.
