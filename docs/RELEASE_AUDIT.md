# Release Audit

This audit describes the currently downloaded public MPR-GUI-Bench release.
It is generated from local files under `data/raw/mpr_gui_bench`.

## Summary

- Root: `data/raw/mpr_gui_bench`
- Images directory exists: `True`
- QAS directory exists: `True`
- Local JPG files under images: `3152`
- Local QAS JSONL files: `48`
- Dataset license from HF README: `cc-by-nc-4.0`
- Total QA rows: `13470`
- Missing asset references: `0`
- Malformed answer fields: `0`
- Non-label-only answer fields: `131`
- Hugging Face dataset SHA: `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`
- MPR-GUI-Bench GitHub commit: `e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba`

## Key Findings

- The downloaded public QA release contains `2,245` rows per language, not `2,156`.
- All `2,245` language-agnostic state keys have complete six-language coverage.
- All audited asset references resolve locally after normalizing `../images/...` paths.
- RI and SI are completely label-biased in the public option order: every audited RI/SI answer is `A`.
- The audit found no malformed answers under the conservative A/B/C/D label parser.

## Generated Artifacts

- Raw normalized assets: `data/raw/mpr_gui_bench/images/` and `data/raw/mpr_gui_bench/qas/`.
- Source metadata: `data/raw/mpr_gui_bench/SOURCE.json`.
- Machine-readable audit: `data/manifests/release_audit.json`.
- Sample manifest: `data/manifests/mpr_gui_manifest.jsonl`.
- Parallel index: `data/manifests/parallel_index.json`.
- Directed cross-locale pairs: `data/manifests/cross_locale_pairs.jsonl`.

## Rows By Language

| Language | Rows | Delta vs paper-reported 2,156 |
| --- | ---: | ---: |
| en | 2245 | +89 |
| fr | 2245 | +89 |
| ja | 2245 | +89 |
| ru | 2245 | +89 |
| th | 2245 | +89 |
| zh | 2245 | +89 |

## Language x Dimension Matrix

| Language | wf | wi | au | ap | ael | rel | ri | si | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |
| fr | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |
| ja | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |
| ru | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |
| th | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |
| zh | 365 | 366 | 366 | 366 | 366 | 366 | 25 | 25 | 2245 |

## Rows By Dimension

| Dimension | Rows |
| --- | ---: |
| ael | 2196 |
| ap | 2196 |
| au | 2196 |
| rel | 2196 |
| ri | 150 |
| si | 150 |
| wf | 2190 |
| wi | 2196 |

## Answer Label Distribution By File

| File | Rows | Dimension | Language | A | B | C | D | Missing assets | SHA256 |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `abs_el_en.jsonl` | 366 | ael | en | 69 | 133 | 105 | 59 | 0 | `cbbb1ef690dd` |
| `abs_el_fr.jsonl` | 366 | ael | fr | 69 | 133 | 105 | 59 | 0 | `c3e0ec632629` |
| `abs_el_ja.jsonl` | 366 | ael | ja | 69 | 133 | 105 | 59 | 0 | `04b7e2e506ae` |
| `abs_el_ru.jsonl` | 366 | ael | ru | 69 | 133 | 105 | 59 | 0 | `5c743b579690` |
| `abs_el_th.jsonl` | 366 | ael | th | 69 | 133 | 105 | 59 | 0 | `942f7414edcb` |
| `abs_el_zh.jsonl` | 366 | ael | zh | 69 | 133 | 105 | 59 | 0 | `f04c757db57a` |
| `ap_en.jsonl` | 366 | ap | en | 136 | 105 | 87 | 38 | 0 | `aae81e18e7af` |
| `ap_fr.jsonl` | 366 | ap | fr | 136 | 105 | 87 | 38 | 0 | `e3857061cf36` |
| `ap_ja.jsonl` | 366 | ap | ja | 136 | 105 | 87 | 38 | 0 | `08ad546d3805` |
| `ap_ru.jsonl` | 366 | ap | ru | 136 | 105 | 87 | 38 | 0 | `658e0a9e876a` |
| `ap_th.jsonl` | 366 | ap | th | 136 | 105 | 87 | 38 | 0 | `90a9330bdb55` |
| `ap_zh.jsonl` | 366 | ap | zh | 136 | 105 | 87 | 38 | 0 | `d01a706ec4e4` |
| `au_en.jsonl` | 366 | au | en | 153 | 133 | 66 | 14 | 0 | `a4ef184d2bd8` |
| `au_fr.jsonl` | 366 | au | fr | 153 | 133 | 66 | 14 | 0 | `0c43b371d5eb` |
| `au_ja.jsonl` | 366 | au | ja | 153 | 133 | 66 | 14 | 0 | `09c8f08f4e20` |
| `au_ru.jsonl` | 366 | au | ru | 153 | 133 | 66 | 14 | 0 | `71455fa46464` |
| `au_th.jsonl` | 366 | au | th | 153 | 133 | 66 | 14 | 0 | `cb051d33b7f0` |
| `au_zh.jsonl` | 366 | au | zh | 153 | 133 | 66 | 14 | 0 | `a75562cc4a60` |
| `knowledge_rich_en.jsonl` | 25 | ri | en | 25 | 0 | 0 | 0 | 0 | `08dbdab04d65` |
| `knowledge_rich_fr.jsonl` | 25 | ri | fr | 25 | 0 | 0 | 0 | 0 | `485c46fa3eea` |
| `knowledge_rich_ja.jsonl` | 25 | ri | ja | 25 | 0 | 0 | 0 | 0 | `c460a9b2fa73` |
| `knowledge_rich_ru.jsonl` | 25 | ri | ru | 25 | 0 | 0 | 0 | 0 | `d5f986fc4390` |
| `knowledge_rich_th.jsonl` | 25 | ri | th | 25 | 0 | 0 | 0 | 0 | `5c646c1698fe` |
| `knowledge_rich_zh.jsonl` | 25 | ri | zh | 25 | 0 | 0 | 0 | 0 | `4bbcff172ddb` |
| `knowledge_sparse_en.jsonl` | 25 | si | en | 25 | 0 | 0 | 0 | 0 | `97a4c0f698bd` |
| `knowledge_sparse_fr.jsonl` | 25 | si | fr | 25 | 0 | 0 | 0 | 0 | `7a7174a9aa6c` |
| `knowledge_sparse_ja.jsonl` | 25 | si | ja | 25 | 0 | 0 | 0 | 0 | `00bca50e8c70` |
| `knowledge_sparse_ru.jsonl` | 25 | si | ru | 25 | 0 | 0 | 0 | 0 | `69c0373a6121` |
| `knowledge_sparse_th.jsonl` | 25 | si | th | 25 | 0 | 0 | 0 | 0 | `e3126bc7a2fc` |
| `knowledge_sparse_zh.jsonl` | 25 | si | zh | 25 | 0 | 0 | 0 | 0 | `bd55bab5da2c` |
| `rel_el_en.jsonl` | 366 | rel | en | 139 | 114 | 79 | 34 | 0 | `742a793bfede` |
| `rel_el_fr.jsonl` | 366 | rel | fr | 139 | 114 | 79 | 34 | 0 | `29e532a39eb4` |
| `rel_el_ja.jsonl` | 366 | rel | ja | 139 | 114 | 79 | 34 | 0 | `77591f6f3829` |
| `rel_el_ru.jsonl` | 366 | rel | ru | 139 | 114 | 79 | 34 | 0 | `ffcb7ffb6971` |
| `rel_el_th.jsonl` | 366 | rel | th | 139 | 114 | 79 | 34 | 0 | `fed9249bd5b2` |
| `rel_el_zh.jsonl` | 366 | rel | zh | 139 | 114 | 79 | 34 | 0 | `56113e66ebf2` |
| `wf_en.jsonl` | 365 | wf | en | 102 | 144 | 96 | 23 | 0 | `56f943ba937d` |
| `wf_fr.jsonl` | 365 | wf | fr | 102 | 144 | 96 | 23 | 0 | `485299570b00` |
| `wf_ja.jsonl` | 365 | wf | ja | 102 | 144 | 96 | 23 | 0 | `ec69dcae0cb7` |
| `wf_ru.jsonl` | 365 | wf | ru | 102 | 144 | 96 | 23 | 0 | `cf9226c7160d` |
| `wf_th.jsonl` | 365 | wf | th | 102 | 144 | 96 | 23 | 0 | `61d48ca20e72` |
| `wf_zh.jsonl` | 365 | wf | zh | 102 | 144 | 96 | 23 | 0 | `39fb43259868` |
| `wi_en.jsonl` | 366 | wi | en | 149 | 141 | 63 | 13 | 0 | `6e9ab15db13f` |
| `wi_fr.jsonl` | 366 | wi | fr | 149 | 141 | 63 | 13 | 0 | `c84a4ecad88b` |
| `wi_ja.jsonl` | 366 | wi | ja | 149 | 141 | 63 | 13 | 0 | `93f8c314172b` |
| `wi_ru.jsonl` | 366 | wi | ru | 149 | 141 | 63 | 13 | 0 | `0c1b82159e1e` |
| `wi_th.jsonl` | 366 | wi | th | 149 | 141 | 63 | 13 | 0 | `5917ffb4047c` |
| `wi_zh.jsonl` | 366 | wi | zh | 149 | 141 | 63 | 13 | 0 | `c26e00645410` |

## Parallel Coverage

| Dimension | Unique state keys | Complete 6-language states | Coverage histogram |
| --- | ---: | ---: | --- |
| ael | 366 | 366 | `{6: 366}` |
| ap | 366 | 366 | `{6: 366}` |
| au | 366 | 366 | `{6: 366}` |
| rel | 366 | 366 | `{6: 366}` |
| ri | 25 | 25 | `{6: 25}` |
| si | 25 | 25 | `{6: 25}` |
| wf | 365 | 365 | `{6: 365}` |
| wi | 366 | 366 | `{6: 366}` |

## Non-Label-Only Answer Fields

These answer fields parse cleanly to A/B/C/D but include extra answer text. Normalized label accuracy should be reported next to raw exact match.

- `abs_el_en.jsonl` line 85: `C. Lower-left quadrant` -> `C`
- `abs_el_fr.jsonl` line 85: `C. Lower-left quadrant` -> `C`
- `abs_el_ja.jsonl` line 85: `C. Lower-left quadrant` -> `C`
- `abs_el_ru.jsonl` line 84: `C. Lower-left quadrant` -> `C`
- `abs_el_th.jsonl` line 85: `C. Lower-left quadrant` -> `C`
- `abs_el_zh.jsonl` line 85: `C. Lower-left quadrant` -> `C`
- `au_en.jsonl` line 323: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `au_fr.jsonl` line 322: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `au_ja.jsonl` line 322: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `au_ru.jsonl` line 322: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `au_th.jsonl` line 323: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `au_zh.jsonl` line 323: `A. A new screen detailing monetization options will slide in, replacing the current menu.` -> `A`
- `wf_en.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_en.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_en.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_en.jsonl` line 173: `D. Delete` -> `D`
- `wf_en.jsonl` line 195: `B. Turn on Deep Focus mode` -> `B`
- `wf_en.jsonl` line 223: `B. Flash Off` -> `B`
- `wf_fr.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_fr.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_fr.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_fr.jsonl` line 173: `D. Delete` -> `D`
- `wf_fr.jsonl` line 195: `B. Turn on Deep Focus mode` -> `B`
- `wf_fr.jsonl` line 223: `B. Flash Off` -> `B`
- `wf_ja.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_ja.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_ja.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_ja.jsonl` line 168: `D. Delete` -> `D`
- `wf_ja.jsonl` line 194: `B. Turn on Deep Focus mode` -> `B`
- `wf_ja.jsonl` line 222: `B. Flash Off` -> `B`
- `wf_ru.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_ru.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_ru.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_ru.jsonl` line 172: `D. Delete` -> `D`
- `wf_ru.jsonl` line 194: `B. Turn on Deep Focus mode` -> `B`
- `wf_ru.jsonl` line 222: `B. Flash Off` -> `B`
- `wf_th.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_th.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_th.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_th.jsonl` line 169: `D. Delete` -> `D`
- `wf_th.jsonl` line 195: `B. Turn on Deep Focus mode` -> `B`
- `wf_th.jsonl` line 223: `B. Flash Off` -> `B`
- `wf_zh.jsonl` line 74: `D. Deleting a current task` -> `D`
- `wf_zh.jsonl` line 112: `A. Setting a song as a ringtone` -> `A`
- `wf_zh.jsonl` line 117: `C. Messaging app` -> `C`
- `wf_zh.jsonl` line 172: `D. Delete` -> `D`
- `wf_zh.jsonl` line 195: `B. Turn on Deep Focus mode` -> `B`
- `wf_zh.jsonl` line 223: `B. Flash Off` -> `B`
- `wi_en.jsonl` line 29: `C. Tap the shutter button` -> `C`
- `wi_en.jsonl` line 39: `B. Swiping left or right at the bottom mode selector bar.` -> `B`
- ... 81 more


## Episode Frame Counts

| Frames per episode row | Count |
| ---: | ---: |
| 2 | 24 |
| 3 | 96 |
| 4 | 18 |
| 5 | 30 |
| 6 | 53 |
| 7 | 61 |
| 8 | 18 |

## Interpretation Notes

- The canonical reproduction should use the public option order unchanged.
- Normalized label accuracy should parse labels from mixed answer strings such as `C. ...`.
- If RI/SI label distributions are highly concentrated, report permutation-controlled and question-only baselines.
- GUI-XLI remains an independent reimplementation unless official harness, memory data, and hook code become available.
