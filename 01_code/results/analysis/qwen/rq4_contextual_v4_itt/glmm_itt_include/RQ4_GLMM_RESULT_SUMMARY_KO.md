# RQ4 REL query-alignment intervention GLMM 결과 요약

- Model: `Qwen/Qwen2.5-VL-7B-Instruct`
- Revision: `cc594898137f460bfe9f0759e9844b3ce807cfb5`
- Intervention: `contextual`
- Random-effects structure: `item_plus_pair_primary`
- Independent adjusted intervention gain: -2.10%p
- Dependent adjusted intervention gain: -2.81%p
- Probability DID: -0.72%p
- Primary M1 vs M2 LRT: chi-square=0.192, df=1, p=6.611e-01

Primary outcome은 `generation_correct`이며 primary moderation은
`intervention × text_dependency`이다.

GEE sensitivity는 현재 구현·실행 범위에서 의도적으로 제외했으며,
필요 시 별도 후속 분석으로 수행한다.
