# RQ4 REL query-alignment intervention GLMM 결과 요약

- Model: `OpenGVLab/InternVL2_5-8B`
- Revision: `e9e4c0dc1db56bfab10458671519b7fa3dd29463`
- Intervention: `contextual`
- Random-effects structure: `item_plus_pair_primary`
- Independent adjusted intervention gain: -4.67%p
- Dependent adjusted intervention gain: +2.53%p
- Probability DID: +7.20%p
- Primary M1 vs M2 LRT: chi-square=28.667, df=1, p=8.597e-08

Primary outcome은 `generation_correct`이며 primary moderation은
`intervention × text_dependency`이다.

GEE sensitivity는 현재 구현·실행 범위에서 의도적으로 제외했으며,
필요 시 별도 후속 분석으로 수행한다.
