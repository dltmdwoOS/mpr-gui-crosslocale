# RQ4 development history

This file records the internal development path so the final paper does not
implicitly present the intervention as prospectively confirmatory.

## 1. NLLB field-wise engineering pilot

- Translator: `facebook/nllb-200-distilled-600M`.
- Stem and options were translated independently.
- Context-sensitive GUI labels and short options were frequently malformed or
  poorly localized.
- This condition is retained for engineering provenance and is not treated as
  a scientific negative intervention result.

## 2. Qwen3 contextual text-only method

- Translator: frozen `Qwen/Qwen3-8B` revision.
- The complete MCQ was translated jointly with structured JSON output.
- Translation was technically valid, but downstream recovery was inconsistent:
  Qwen showed no text-dependency moderation, whereas InternVL showed a smaller
  selective response.
- This is the preceding text-only method and a secondary method-level baseline.

## 3. RQ3-informed target-GUI lexical localization

- Stage 1 extracted visible strings from each target GUI without access to the
  question, options, gold label, dependency annotation, or model outcomes.
- Raw extraction order was removed through normalization, deduplication, and
  deterministic lexical sorting.
- Stage 2 used the sorted lexical inventory and source MCQ, but not the image,
  coordinates, bounding boxes, extraction order, gold, or dependency label.
- This is the final RQ4 intervention. It was selected adaptively after RQ3 and
  the preceding engineering attempts, so it is described as a
  diagnosis-informed exploratory intervention study.

## Frozen interpretation

The primary estimand is the effect of the complete two-stage method relative to
the original mismatch, moderated by text dependency. The direct comparison
with text-only is a method-level ablation: translator identity, revision,
deterministic decoding, MCQ structure, and downstream protocol are held fixed,
but inventory-specific prompts and validation logic differ.

Permitted claim:

> The text-dependent subgroup identified in RQ3 also exhibited selective
> response to the subsequent diagnosis-informed intervention.

Claims not supported by this design:

- text dependency causally causes the original concordance association;
- lexical mismatch is the sole causal mechanism;
- the text-only versus two-stage contrast isolates lexical inventory as its
  only manipulated component;
- the human-parallel matched endpoint is a causal oracle.
