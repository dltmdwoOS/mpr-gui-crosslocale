# Reproduction Notes

Canonical reproduction means evaluating the public MPR-GUI multiple-choice QA
files with matched query language and GUI language. It does not mean exact
reproduction of the paper's private harness unless the missing variables below
are resolved.

Current canonical target:

- Evaluation status: public-release reproduction.
- Hugging Face revision: `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`.
- GitHub QAS revision: `e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba`.
- Public rows per language: `2,245`.
- Total public QA rows: `13,470`.
- Replay lock file: `data/manifests/source_lock.json`.

Unresolved reproduction variables:

- Exact public-vs-paper manifest or filtering rules.
- Model revisions and software versions.
- Official prompt templates.
- Generation parameters and answer parser.
- Multi-image episode frame ordering.
- Image preprocessing and maximum resolution.
- GUI-XLI memory construction data and reasoning traces.
- GUI-XLI top-k, hook location, token position, alpha grid, and validation set.

Default local profile:

- Prompt profile: `mpr_direct_v1`.
- Generation: deterministic, `do_sample=false`.
- Answer parsing: conservative first-label parser.
- Episode ordering: numeric natural sort.
- Metrics: exact match, normalized label accuracy, FPR-ACC, label bias.

Manifest invariant checks are intentionally pinned to the current public
release. If the upstream release changes, `scripts/audit_release.sh` should
fail until the release change is deliberately audited.
