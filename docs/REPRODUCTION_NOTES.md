# Reproduction Notes

Canonical reproduction means evaluating the public MPR-GUI multiple-choice QA
files with matched query language and GUI language. It does not mean exact
reproduction of the paper's private harness unless the missing variables below
are resolved.

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
