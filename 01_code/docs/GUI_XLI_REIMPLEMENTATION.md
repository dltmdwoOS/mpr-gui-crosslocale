# GUI-XLI Reimplementation

This track is an independent reimplementation based on the public paper
description, not an exact official reproduction.

Default assumptions are versioned in
`configs/experiments/gui_xli_reimplementation.yaml`:

- Hook location: block output.
- Injected position: last token.
- Retrieval: cosine similarity over memory keys.
- Retrieval top-k: 3 until official value is confirmed.
- Memory source: held-out parallel subset created locally.
- Norm preservation: rescale the updated hidden state to the original norm.

Every GUI-XLI result must report these assumptions next to the score.
