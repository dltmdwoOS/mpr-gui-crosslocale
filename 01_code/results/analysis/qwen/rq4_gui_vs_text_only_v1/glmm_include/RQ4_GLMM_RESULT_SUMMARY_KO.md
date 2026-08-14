# RQ4 REL query-alignment intervention GLMM 결과 요약

- Model: `Qwen/Qwen2.5-VL-7B-Instruct`
- Revision: `cc594898137f460bfe9f0759e9844b3ce807cfb5`
- Intervention: `gui_lexical`
- Random-effects structure: `item_plus_pair_primary`
- Independent adjusted intervention gain: +0.35%p
- Dependent adjusted intervention gain: +7.34%p
- Probability DID: +7.00%p
- Primary M1 vs M2 LRT: chi-square=35.663, df=1, p=2.345e-09

Primary outcome은 `generation_correct`이며 primary moderation은
`intervention × text_dependency`이다.

GEE sensitivity는 현재 구현·실행 범위에서 의도적으로 제외했으며,
필요 시 별도 후속 분석으로 수행한다.
