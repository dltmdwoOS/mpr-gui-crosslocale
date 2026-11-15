#!/bin/bash
# 밤사이 자동 분석. sync_loop.sh가 서버 queue_results를 mirror/로 복사하면,
# 완료 표시가 있는 모델 묶음을 찾아 sha256 확인 → model_results_20261114/<key>/ 로 복사·풀기 → 고정 규칙 분석.
# 서버에는 아무것도 하지 않는다(읽기도 하지 않음). 기존 결과는 덮어쓰지 않는다.
# 로그: analysis_newmodels_20261114/auto_log.txt   멈추기: kill <PID>
R="/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스"
M="$R/server_sync_4090b_20261114/mirror/queue_results"
A="$R/analysis_newmodels_20261114"; L="$A/auto_log.txt"
say() { echo "$(date '+%F %T') $*" >> "$L"; }
end=$(( $(date +%s) + 36*3600 ))
say "auto start pid $$"
while [ "$(date +%s)" -lt "$end" ]; do
  # sizes queue: <key>/COMPLETE + SHA256SUMS
  for d in "$M"/*/; do
    k=$(basename "$d")
    case "$k" in qwen3_vl_4b|internvl35_4b|uitars_15_7b|minicpm|batch1_check_qwen3_8b|net_check*|6x6_*) continue;; esac  # r1: minicpm handled by hand (different package layout; a stale 4 KB package exists)
    [ -e "$A/$k" ] && continue
    [ -f "$A/.fail_$k" ] && continue
    ok=""
    if [ -f "$d/COMPLETE" ] && [ -f "$d/SHA256SUMS" ]; then ok=sums
    elif ls "$d"/*.tar.gz.sha256 >/dev/null 2>&1; then ok=each; fi
    [ -z "$ok" ] && continue
    B="$R/model_results_20261114/$k"; mkdir -p "$B/dl" "$B/unpacked"
    cp -p "$d"/*.tar.gz "$d"/SHA256SUMS "$d"/*.sha256 "$d"/COMPLETE "$B/dl/" 2>/dev/null
    if [ "$ok" = sums ]; then (cd "$B/dl" && shasum -a 256 -c SHA256SUMS) >> "$L" 2>&1; rc=$?
    else rc=0; for s in "$B"/dl/*.sha256; do h=$(cut -d' ' -f1 "$s"); f="$B/dl/$(basename "${s%.sha256}")"; [ "$(shasum -a 256 "$f" | cut -d' ' -f1)" = "$h" ] || rc=1; done; fi
    if [ $rc -ne 0 ]; then say "$k sha MISMATCH (partial copy?), retry next round"; rm -rf "$B/dl"; continue; fi
    say "$k sha ok"
    for t in "$B"/dl/*.tar.gz; do tar -xzf "$t" -C "$B/unpacked"; done
    u=$(find "$B/unpacked" -mindepth 1 -maxdepth 1 -type d | head -1); [ -d "$B/unpacked/rel_full" ] || [ -d "$B/unpacked/minicpm_rel" ] && u="$B/unpacked"
    say "$k unpacked to $u; analysis start"
    (cd "$A" && python3 run_frozen_analysis.py "$k" "$u" "$k") > "$A/auto_${k}_analysis.log" 2>&1
    if [ $? -eq 0 ]; then say "$k analysis done -> $A/$k/tables_KO.md"
    else say "$k analysis FAILED (see auto_${k}_analysis.log); raw results kept in $B"; touch "$A/.fail_$k"; rm -rf "$A/$k"; fi
  done
  # 6x6 packages: copy and verify only (GLMM needs R)
  for d in "$M"/6x6_*/; do
    [ -d "$d" ] || continue; k=$(basename "$d"); B="$R/model_results_20261114/$k"
    [ -f "$d/COMPLETE" ] || continue; [ -f "$B/SHA_OK" ] && continue
    grep -q "^SKIPPED" "$d/COMPLETE" 2>/dev/null && continue  # r2: skip markers (plan na), not results
    mkdir -p "$B"; cp -p "$d"/* "$B/" 2>/dev/null
    (cd "$B" && shasum -a 256 -c SHA256SUMS) >> "$L" 2>&1 && { touch "$B/SHA_OK"; say "$k copied, sha ok (6x6 analysis needs R; not run)"; } || say "$k sha mismatch, retry"
  done
  [ -f "$R/server_sync_4090b_20261114/mirror/QUEUE6_DONE" ] && { say "QUEUE6_DONE seen; auto stop"; break; }
  sleep 600
done
say "auto end"
