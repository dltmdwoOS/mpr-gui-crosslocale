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

- Prompt profile: `mpr_minimal_v1` for primary canonical reproduction.
- Prompt sensitivity profile: `mpr_label_only_v1`.
- Generation: deterministic, `do_sample=false`.
- Answer parsing: conservative first-label parser.
- Episode ordering: numeric natural sort.
- Metrics: exact match, normalized label accuracy, FPR-ACC, label bias.
- First model: `Qwen/Qwen2.5-VL-7B-Instruct`.
- Pinned Qwen model revision: `cc594898137f460bfe9f0759e9844b3ce807cfb5`.

Manifest invariant checks are intentionally pinned to the current public
release. If the upstream release changes, `scripts/audit_release.sh` should
fail until the release change is deliberately audited.

Before renting a GPU for a full run:

```bash
scripts/run_canonical.sh --dry-run --limit 8
scripts/processor_preflight.sh --limit 48
```

Then run a small model smoke subset:

```bash
scripts/run_canonical.sh \
  --limit 48 \
  --resume \
  --output results/raw/canonical_reproduction/qwen25vl_smoke.jsonl
```
