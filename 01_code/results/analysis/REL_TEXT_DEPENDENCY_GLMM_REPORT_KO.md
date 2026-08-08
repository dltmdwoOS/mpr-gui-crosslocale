# REL Text-dependency GLMM 분석 보고서

작성일: 2026-08-07
상태: Generation-only primary GLMM 및 manifest provenance 검증 완료

## 1. 결론

최종 adjudication된 REL 366개 문항을 대상으로 item random intercept GLMM을 적합한 결과, GEE에서 관찰한 text-dependency moderation이 두 모델에서 다시 확인됐다.

- Qwen: `matched × text_dependency` LRT χ²(1) = 29.26, p = 6.34×10⁻⁸
- InternVL: `matched × text_dependency` LRT χ²(1) = 30.21, p = 3.88×10⁻⁸
- Independent의 adjusted concordance bonus는 두 모델 모두 약 0%p였다.
- Dependent의 adjusted concordance bonus는 Qwen +11.74%p, InternVL +12.31%p였다.
- Dependent-minus-independent probability difference-in-differences는 Qwen +12.13%p, InternVL +12.57%p였다.
- 세 GLMM 모두 정상 수렴했고 singular fit, Hessian 문제 또는 convergence warning이 없었다.

따라서 RQ3의 통계적 결론은 다음과 같이 정리할 수 있다.

> The large REL concordance association was strongly moderated by annotated text dependency. It was near zero in text-independent items and approximately 12 percentage points in text-dependent items in both VLMs.

이는 GEE보다 더 풍부한 language adjustment와 item-level heterogeneity를 허용한 뒤에도 유지되는 결과다. 다만 annotation은 관찰적 item 특성 분류이므로 text dependency가 성능 저하를 인과적으로 발생시켰다고 단정하지 않는다.

## 2. 분석 입력과 검증 범위

### 입력

| 항목 | 내용 |
|---|---|
| Annotation | `annotation/rel_text_dependency/outputs/rel_annotations_integrated_366.csv` |
| Qwen table | `01_code/data/derived/qwen_glmm.csv` |
| InternVL table | `01_code/data/derived/internvl_glmm.csv` |
| Outcome | `generation_correct` |
| Dimension | REL only |
| 모델별 관측치 | 13,176 = 366 items × 36 language cells |
| Final label | dependent 302, independent 64 |
| Annotator ID | `team_consensus` |
| Guideline | `pilot-v1+team-adjudication-v1` |
| Unresolved review | 0 |

분석 코드는 다음을 실행 전에 엄격하게 확인한다.

1. 분석 테이블에 REL 13,176행과 366개 item이 존재한다.
2. 각 item에 36개 query–GUI language cell이 정확히 존재한다.
3. 통합 annotation은 366행이고 `parallel_id` 중복이 없다.
4. label은 `dependent/independent`만 존재한다.
5. 모든 row가 `team_consensus`, review flag 0, 지정 guideline을 가진다.
6. 분석 테이블과 annotation의 366개 `parallel_id` 집합이 정확히 일치한다.

따라서 annotation label이 잘못된 item에 join되거나 일부 item이 누락된 상태로 적합된 것은 아니다.

## 3. Primary GLMM 명세

세 개의 nested model을 비교했다.

```r
# M0: dependency별 query/GUI 난이도만 허용
y ~ question_language * text_dependency +
    gui_language * text_dependency +
    (1 | parallel_id)

# M1: 공통 concordance association 추가
y ~ question_language * text_dependency +
    gui_language * text_dependency +
    matched_num +
    (1 | parallel_id)

# M2: primary interaction model
y ~ question_language * text_dependency +
    gui_language * text_dependency +
    matched_num * text_dependency +
    (1 | parallel_id)
```

M2는 text-dependent 문항에서 특정 query language 또는 GUI language 자체가 더 어려울 가능성을 별도로 허용한다. 따라서 primary interaction은 이러한 dependency-specific language difficulty를 통제한 뒤 남는 concordance moderation이다.

Primary hypothesis test는 M1과 M2의 1-df likelihood-ratio test다.

## 4. Raw 결과

| Model | Dependency | Raw matched | Raw mismatch | Raw bonus |
|---|---|---:|---:|---:|
| Qwen | Independent | 66.67% | 67.14% | −0.47%p |
| Qwen | Dependent | 72.30% | 59.88% | +12.42%p |
| InternVL | Independent | 59.90% | 60.21% | −0.31%p |
| InternVL | Dependent | 61.87% | 48.72% | +13.15%p |

Dependent가 항상 어려운 것이 아니라 mismatch에서 선택적으로 크게 하락한다는 패턴이 두 모델에서 동일하다.

## 5. Formal model comparison

### 5.1 공통 matched association: M0 vs M1

| Model | χ²(1) | p | ΔAIC | 해석 |
|---|---:|---:|---:|---|
| Qwen | 151.08 | 1.01×10⁻³⁴ | −149.08 | dependency별 language difficulty를 통제해도 평균 matched association 존재 |
| InternVL | 149.79 | 1.93×10⁻³⁴ | −147.79 | 동일 |

### 5.2 Primary moderation: M1 vs M2

| Model | χ²(1) | p | ΔAIC | ΔBIC |
|---|---:|---:|---:|---:|
| Qwen | 29.26 | 6.34×10⁻⁸ | −27.26 | −19.77 |
| InternVL | 30.21 | 3.88×10⁻⁸ | −28.21 | −20.72 |

두 모델 모두 interaction을 추가한 M2가 likelihood, AIC와 BIC에서 명확하게 우수하다. 따라서 하나의 공통 matched coefficient만으로 REL 전체를 설명하는 것보다 dependency별 matched association을 허용하는 것이 데이터에 더 잘 맞는다.

## 6. Link-scale 결과

`emtrends`로 dependency별 matched slope를 직접 추정했다. 이는 sum-coded fixed-effect coefficient 하나를 임의로 해석하는 문제를 피한다.

| Model | Dependency | Matched OR | 95% CI | p |
|---|---|---:|---:|---:|
| Qwen | Independent | 0.968 | 0.702–1.334 | .841 |
| Qwen | Dependent | 2.647 | 2.289–3.061 | 2.07×10⁻³⁹ |
| InternVL | Independent | 0.981 | 0.724–1.330 | .902 |
| InternVL | Dependent | 2.571 | 2.236–2.957 | 4.53×10⁻⁴⁰ |

직접적인 interaction OR는 다음과 같다.

| Model | Interaction OR | 95% CI | Wald p |
|---|---:|---:|---:|
| Qwen | 2.735 | 1.923–3.890 | 2.16×10⁻⁸ |
| InternVL | 2.621 | 1.875–3.664 | 1.71×10⁻⁸ |

즉 item difficulty를 조건부로 보았을 때 dependent 문항의 matched odds multiplier는 independent 문항보다 약 2.6–2.7배 크다. Primary p-value는 위 Wald test가 아니라 M1–M2 likelihood-ratio test를 사용한다.

Independent의 비유의성을 “효과가 정확히 0임을 입증했다”로 해석해서는 안 된다. 다만 point estimate가 1에 매우 가깝고, probability-scale estimate도 거의 0이며, 두 모델에서 같은 패턴이라는 점이 moderation 해석을 지지한다.

## 7. Item-marginal adjusted probability 결과

확률 estimand는 기존 RQ1/RQ2와 맞춘 다음 quantity다.

1. 여섯 identity-diagonal language cell을 동일 가중한다.
2. 같은 diagonal covariate grid에서 `matched=1`과 counterfactual `matched=0`을 비교한다.
3. fitted item random-intercept distribution을 적분한다.
4. fixed-effect covariance에서 2,000개 MVN draw를 생성해 CI를 계산한다.
5. random-intercept SD는 plug-in 값으로 취급한다.

| Model | Dependency | Adjusted matched | Counterfactual mismatch | Bonus | 95% CI |
|---|---|---:|---:|---:|---:|
| Qwen | Independent | 67.77% | 68.16% | −0.39%p | −4.24–3.54%p |
| Qwen | Dependent | 71.67% | 59.93% | +11.74%p | 10.05–13.42%p |
| InternVL | Independent | 59.84% | 60.09% | −0.25%p | −4.37–3.83%p |
| InternVL | Dependent | 61.30% | 48.99% | +12.31%p | 10.44–14.06%p |

Probability-scale difference-in-differences는 다음과 같다.

| Model | Dependent bonus − independent bonus | 95% CI |
|---|---:|---:|
| Qwen | +12.13%p | 7.99–16.42%p |
| InternVL | +12.57%p | 8.01–17.02%p |

두 CI가 0을 명확히 배제한다. 이 결과가 논문의 가장 직접적이고 해석하기 쉬운 primary effect-size 보고값이다.

## 8. GEE와 비교해 GLMM이 추가로 확정한 것

| Model | GEE adjusted DID | GLMM adjusted DID | GEE interaction OR | GLMM interaction OR |
|---|---:|---:|---:|---:|
| Qwen | +12.86%p | +12.13%p | 1.814 | 2.735 |
| InternVL | +13.61%p | +12.57%p | 1.765 | 2.621 |

확률 차이는 GEE와 GLMM에서 1%p 이내로 유사하다. 반면 OR는 GLMM에서 더 크다. 이는 모순이 아니다.

- GEE OR: population-averaged association
- GLMM OR: 같은 item random effect를 조건부로 한 subject/item-specific association
- Logistic OR는 non-collapsible하며, item heterogeneity가 클수록 conditional OR와 marginal OR가 달라질 수 있다.

따라서 모델 간 효과 크기를 비교할 때는 OR보다 standardized probability difference를 우선하는 것이 안전하다.

GLMM이 새로 제공한 핵심 가치는 다음과 같다.

1. 36개 cell이 같은 item에 속한다는 반복측정 구조를 item random intercept로 모델링했다.
2. dependency별 query-language 및 GUI-language 난이도를 허용했다.
3. interaction 없는 모델과 있는 모델을 likelihood로 직접 비교했다.
4. item heterogeneity를 적분한 probability-scale estimand를 산출했다.
5. GEE의 working-correlation 접근을 다른 dependence model로 재현했다.

## 9. Model diagnostics와 item heterogeneity

| Model | M2 random-intercept SD | Latent-scale ICC | Max gradient | Hessian min eigenvalue | Singular |
|---|---:|---:|---:|---:|---|
| Qwen | 2.358 | 0.628 | 0.00132 | 41.08 | No |
| InternVL | 2.197 | 0.595 | 0.00088 | 48.16 | No |

모든 M0–M2 model은 다음 조건을 만족했다.

- 13,176 observations 사용
- singular fit 아님
- convergence message 없음
- maximum absolute gradient가 작음
- Hessian minimum eigenvalue가 충분히 양수

Latent-scale ICC 약 0.60–0.63은 item 간 기본 난이도 이질성이 매우 크다는 뜻이다. 이는 item random intercept를 포함한 GLMM 사용이 실질적으로 필요했음을 보여준다.

## 10. 해석

현재 결과가 직접 지지하는 문장은 다음이다.

> Across both VLMs, the query–GUI language concordance association in REL was concentrated in items annotated as text-dependent. After allowing query- and GUI-language difficulty to vary by dependency class and accounting for repeated observations within items, the adjusted concordance bonus was approximately 12 percentage points for text-dependent items and near zero for text-independent items.

기제 해석은 별도로 제한한다.

> This moderation pattern is consistent with a failure mode involving text-mediated cross-lingual element grounding, but the observational annotation does not causally identify the underlying mechanism.

즉 GLMM은 “text-mediated grounding과 일치하는 선택적 vulnerability”를 강하게 지지하지만, OCR 실패, 번역 실패 또는 특정 내부 representation failure 중 무엇이 원인인지는 직접 식별하지 않는다.

## 11. 남은 주의점

### 11.1 Manifest provenance quick fix 완료

초기 audit에서 Windows working tree의 raw-byte hash와 Git-staged manifest hash가 다르게 보였으나, 원인은 데이터 내용이 아니라 CRLF/LF line ending 차이였다.

- Windows CRLF raw bytes: `00c3e324…`
- Git-staged LF bytes: `fa8f6ea6…`

운영체제에 독립적인 provenance를 위해 CRLF와 CR을 LF로 정규화한 뒤 SHA-256을 계산하는 정책으로 통일했다. Canonical hash는 다음과 같다.

```text
fa8f6ea6393dd5ecb60740a83bff2e50bd18934771e673d744d98e798b5af4f1
```

분석 코드도 더 이상 hard-coded hash만 신뢰하지 않는다. 실행 시 canonical manifest 파일을 읽어 newline-normalized SHA-256을 계산하고, 통합 CSV의 모든 `manifest_sha256` 값과 일치하는지 검증한다. 기본 manifest 경로는 위 파일이며 필요하면 여섯 번째 CLI 인자로 다른 경로를 명시할 수 있다. Annotation UI와 preparation report도 같은 정책을 사용한다.

기존 `fa8f…` 값은 canonical content에 대해 올바른 값이었다. 문제는 raw-byte hash 정책이 운영체제별 line ending을 구분했던 데 있으며, label·`parallel_id`·manifest 의미 내용에는 불일치가 없었다. 따라서 numerical estimates에는 변화가 없다.

### 11.2 Random-slope sensitivity

현재 primary GLMM은 item random intercept만 포함한다. 각 item이 matched와 mismatch 6/30 cell을 모두 가지므로 가능한 경우 `(1 + matched_num | parallel_id)` sensitivity가 추가적인 방어가 될 수 있다. 다만 이미 GEE와 GLMM의 probability result가 매우 유사하므로 primary conclusion이 뒤집힐 가능성은 낮아 보인다.

### 11.3 Probability CI 범위

확률 CI는 fixed-effect covariance를 전파하지만 random-intercept SD 불확실성은 포함하지 않는다. 따라서 full parametric bootstrap CI는 아니다. 논문에서는 코드에 기록된 estimand와 CI 방법을 그대로 명시한다.

### 11.4 Source locale anomaly

확인된 exact cross-locale duplicate item은 다음 두 개다.

- `rel::1/booking_5.jpg`: FR image = JA image
- `rel::5/forest_5.jpg`: TH image = FR image

현재 GLMM에는 benchmark-as-released 상태로 포함돼 있다. 2/366 item을 제외한 sensitivity는 아직 이 GLMM에서 수행하지 않았다. 효과 크기에 큰 영향을 줄 가능성은 낮지만, pure language-match 해석을 위해서는 두 item 제외 결과를 확인하는 편이 안전하다.

## 12. 최종 판단

| 평가 항목 | 상태 |
|---|---|
| Final adjudicated label join | 완료 |
| Primary GLMM interaction | 두 모델에서 강하게 지지 |
| Adjusted probability effect | Independent ≈ 0, dependent ≈ +12%p |
| GEE–GLMM consistency | 높음 |
| Model convergence/diagnostics | 양호 |
| Imbalance robustness | 기존 분석으로 충분히 확인 |
| Manifest provenance | 실제 file hash runtime 검증 완료 |
| Source anomaly sensitivity | 권장, 아직 미수행 |

통계적으로 RQ3는 사실상 닫혔다. 남은 핵심 작업은 새로운 robustness를 계속 추가하는 것이 아니라 필요하면 두 source-anomaly item 제외 sensitivity를 짧게 확인한 뒤 진단이 예측하는 mitigation으로 넘어가는 것이다.

## 13. 주요 산출물

Qwen:

```text
01_code/results/analysis/qwen/rel_text_dependency_adjudicated_v1/
```

InternVL:

```text
01_code/results/analysis/internvl/rel_text_dependency_adjudicated_v1/
```

각 디렉토리의 핵심 파일은 다음과 같다.

- `rel_textdep_lrt_generation_correct.csv`: primary likelihood-ratio test
- `rel_textdep_matched_trends_generation_correct.csv`: dependency별 conditional matched OR
- `rel_textdep_interaction_or_generation_correct.csv`: conditional interaction OR
- `rel_textdep_adjusted_bonuses_generation_correct.csv`: dependency별 adjusted probability bonus
- `rel_textdep_probability_did_generation_correct.csv`: probability-scale moderation
- `rel_textdep_diagnostics_generation_correct.csv`: convergence와 random-effect diagnostics
- `rel_textdep_input_audit.csv`: 입력 및 annotation provenance record
