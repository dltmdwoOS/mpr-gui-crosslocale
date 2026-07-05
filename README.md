# mpr-gui-crosslocale

Workspace for reproducing the public MPR-GUI-Bench evaluation and starting a
cross-locale GUI reasoning study.

This repository intentionally separates three tracks:

- `canonical_reproduction`: paper-style evaluation on the public matched
  language screenshots and QA files.
- `cross_locale_oracle`: controlled query-language and GUI-language mismatch
  experiments using parallel MPR-GUI samples.
- `gui_xli_reimplementation`: an independent, paper-faithful reimplementation
  of GUI-XLI, because the official evaluation harness, model adapters, memory
  data, and hook code are not public in the currently referenced materials.

## Current Scope

The first goal is not to claim exact reproduction of every paper result. It is
to make the public release auditable, run canonical multiple-choice evaluation,
and build a reliable parallel sample index for cross-locale experiments.

## Layout

- `configs/`: data, model, and experiment configs.
- `src/mpr_crosslocale/`: package code for data loading, inference, metrics,
  interventions, and analysis.
- `scripts/`: command-line entry points for download, auditing, and runs.
- `tests/`: small invariants for parsing, path handling, metrics, and ordering.
- `data/raw/`: local downloaded MPR-GUI assets, ignored by git.
- `data/derived/`: generated manifests, indices, and derived artifacts, ignored
  by git.
- `results/`: raw model outputs and summaries.
- `docs/`: release audit, reproduction notes, and protocol documents.

## Data License Note

Code in this repository is MIT-licensed. MPR-GUI-Bench data is third-party
material; the downloaded Hugging Face README declares `CC-BY-NC-4.0`.
Generated manifests that include questions, answers, paths, or parsed options
should be treated as dataset-derived artifacts. See `THIRD_PARTY_DATA.md`.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Download and audit scripts are scaffolded in `scripts/`. They are intentionally
conservative until the public dataset license, exact manifest, and official
evaluation variables are confirmed.
