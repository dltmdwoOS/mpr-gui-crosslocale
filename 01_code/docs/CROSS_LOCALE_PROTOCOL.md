# Cross-Locale Protocol

The cross-locale study uses MPR-GUI's parallel screenshots as an oracle
interface-alignment resource.

Conditions:

- `canonical_matched`: question and GUI screenshot are in the same language.
- `raw_mismatch`: question language `Lq` is paired with the parallel GUI
  screenshot from language `Lg`, where `Lq != Lg`.
- `oracle_aligned`: counterfactual matched GUI for the same semantic state,
  used as the alignment upper reference for a directed mismatch pair.

Primary outputs:

- Top-1 constrained label accuracy.
- Probability assigned to the gold label.
- Entropy and top-1/top-2 margin.
- Jensen-Shannon divergence between matched, mismatch, and oracle distributions.
- Directed language-pair policy-shift matrices.

Controls:

- Question-only baseline.
- RI/SI option permutation with fixed seeds.
- Canonical public option order for comparison with the paper-style run.
