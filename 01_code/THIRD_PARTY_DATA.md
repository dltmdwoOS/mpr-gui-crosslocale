# Third-Party Data

This repository contains code under the repository license, but the MPR-GUI-Bench
data is third-party material.

## MPR-GUI-Bench

- Hugging Face dataset: `chenruihan/MPR-GUI-Bench`
- GitHub QA repository: `https://github.com/chenruihan32/MPR-GUI-Bench`
- Dataset license shown in the Hugging Face README: `CC-BY-NC-4.0`
- Downloaded Hugging Face revision: `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`
- Downloaded GitHub revision: `e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba`

## Local Artifacts

The local raw data under `data/raw/mpr_gui_bench/` is not tracked by git.

The generated manifests under `data/manifests/` include dataset-derived
content such as questions, answers, paths, and parsed options. Treat these
artifacts as derived from MPR-GUI-Bench and therefore subject to the dataset
license and non-commercial restriction.

The frozen follow-up archive `followup_rel_4lang/bundles/rel_all_366.tar.gz`
contains dataset-derived questions, options, answers, reference mappings, and
source metadata. It is distributed under the same `CC-BY-NC-4.0` dataset terms,
not the repository's MIT code license. Screenshots remain outside Git and are
downloaded from the pinned Hugging Face revision, with per-file SHA-256 checks.

The repository's code license does not relicense the MPR-GUI-Bench data or
dataset-derived artifacts.

## Reproducible Download

The current release can be replayed with:

```bash
scripts/download_mpr_gui.sh --source-lock data/manifests/source_lock.json
scripts/audit_release.sh
```

You can also pass the revisions explicitly:

```bash
scripts/download_mpr_gui.sh \
  --hf-revision c1edb808d424a2fa7bc4a2e601d39b431b04acd5 \
  --github-ref e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba
```
