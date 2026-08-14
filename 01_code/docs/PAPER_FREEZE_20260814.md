# Short-paper repository freeze — 2026-08-14

## Scope

This freeze closes RQ1–RQ4 for short-paper writing. No new model, translator,
prompt, intervention, decoding configuration, validator rule, or primary
outcome should be selected after this point without opening a separately named
post-freeze study.

## Evidence hierarchy

1. **RQ1 — Existence:** adjusted query–GUI concordance association in both VLMs.
2. **RQ2 — Capability localization:** the association is heterogeneous and
   largest for REL.
3. **RQ3 — Moderator:** the REL association is concentrated in the adjudicated
   text-dependent subset.
4. **RQ4 — Diagnosis-informed intervention:** the two-stage target-GUI-
   conditioned localization method selectively and partially improves that
   same subset in both VLMs.

RQ4 is an adaptively developed exploratory intervention study. Within the
frozen final intervention, the primary analysis is the exact-pair GLMM comparing
original mismatch with the two-stage condition. Text-only and the direct
two-stage-versus-text-only comparison are secondary method-level analyses.

## Freeze records

- Annotation provenance:
  `results/analysis/paper_freeze_20260814/annotation_provenance.json`
- RQ4 large-artifact and model manifest:
  `results/analysis/paper_freeze_20260814/rq4_artifact_manifest.json`
- Query/layout leakage audit:
  `results/analysis/paper_freeze_20260814/rq4_layout_leakage_audit.json`
- Development history: `docs/RQ4_DEVELOPMENT_HISTORY.md`

## RQ4 frozen results

### Original mismatch versus two-stage

| Model | Independent gain | Dependent gain | DID | Primary LRT |
|---|---:|---:|---:|---:|
| Qwen | -1.77%p | +4.22%p | +5.99%p | chi-square(1)=21.22, p=4.10e-6 |
| InternVL | -2.43%p | +8.80%p | +11.23%p | chi-square(1)=65.95, p=4.63e-16 |

### Original mismatch versus text-only

| Model | Independent gain | Dependent gain | DID | Interaction p |
|---|---:|---:|---:|---:|
| Qwen | -2.10%p | -2.81%p | -0.72%p | .661 |
| InternVL | -4.67%p | +2.53%p | +7.20%p | 8.60e-8 |

### Two-stage versus text-only

| Model | Independent gain | Dependent gain | DID | Interaction p |
|---|---:|---:|---:|---:|
| Qwen | +0.35%p | +7.34%p | +7.00%p | 2.35e-9 |
| InternVL | +2.43%p | +6.31%p | +3.88%p | 5.16e-4 |

All six GLMM ladders retained the item-plus-pair random-intercept structure,
were non-singular, had no convergence messages, and had positive Hessian
minimum eigenvalues.

## Large-file policy

Raw inference, translation JSONL files, paired 21,960-row tables, and RDS model
checkpoints are not committed as ordinary Git blobs. They are fixed by SHA-256
in the artifact manifest. Compact CSV/JSON summaries, model specifications,
session information, audit outputs, and the code needed to recreate paired
tables are retained in Git.

## Reproduction entry points

- Original/intervention pair validation:
  `src/mpr_crosslocale/interventions/validate_rel_nllb_results.py`
- Direct text-only/two-stage paired-table builder:
  `analysis/build_rq4_method_comparison.py`
- Pair-aware GLMM:
  `analysis/rel_nllb_intervention_glmm.R` (legacy filename; intervention-generic)
- Layout/query leakage audit:
  `analysis/audit_rq4_layout_freeze.py`

Use a separate GLMM output directory for each comparison because fitted RDS
checkpoints are keyed by output path. The committed compact result directories
exclude those RDS checkpoints and the large paired input tables.

## Branch consolidation

The historical branches form a strict ancestor chain ending at `rq4`:

```text
main -> test -> vast-standalone -> glmm -> rel-annotation-ui -> rq4
                                                           -> paper-freeze-20260814
```

No unique commit is lost by retiring the intermediate branch labels after the
freeze branch has been pushed and reviewed. Keep `main` as the original default
baseline and retain `rq4` until the paper-freeze branch is accepted. Remote
branch deletion is intentionally a separate explicit operation because it can
affect collaborators.
