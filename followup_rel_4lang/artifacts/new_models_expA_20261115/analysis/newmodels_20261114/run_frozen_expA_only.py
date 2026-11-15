"""실험 A만 있는 모델(InternVL2.5-8B)용. run_frozen_analysis.py의 함수를 그대로 쓰고, REL 부분만 뺀다.
사용: python3 run_frozen_expA_only.py <model_key> <expa_full 폴더> <out_dir>
고정 규칙 sha와 진단 코드 sha를 확인하고 다르면 멈춘다. 원본 코드는 수정하지 않는다."""
import importlib.util, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rfa", HERE / "run_frozen_analysis.py")
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)

model, ef, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=False)
rules_sha = F.sha(F.RULES)
assert rules_sha in F.RULES_FROZEN.read_text(), "rules sha mismatch -> stop"
dfz = (F.EXPA_DIR / "DIAGNOSTIC_PLAN_THAI_KO.FROZEN.txt").read_text()
assert F.sha(F.DIAG) in dfz, "diag sha mismatch -> stop"
pred = ef / "predictions.jsonl"
R = dict(model_key=model, provenance=dict(rules_sha256=rules_sha, diag_sha256=F.sha(F.DIAG), analyze_expA_sha256=F.sha(F.ANALYZE),
         predictions_sha256=F.sha(pred), note="Exp A only; REL not run for this model in this batch"))
R["gate"] = json.loads((ef / "gate_expa_complete.json").read_text())
A = F.load_mod(F.ANALYZE, "analyze_expA")
R["expa"], R["expa_complete_pairs"] = F.expa_analysis(A, pred)
rows = A.load_predictions(pred)
ea = out / "expA_analyze"
subprocess.run([sys.executable, "-I", str(F.ANALYZE), model, str(pred), str(ea)], check=True, capture_output=True)
ps = json.loads((ea / "summary.json").read_text())["sets"]["primary_full|generation_correct"]
chk = R["expa"]["all4"]["generation_correct"]
assert abs(chk["T_minus_O"]["pp"] - ps["T_minus_O"]["pp"]) < 1e-9
r = subprocess.run([sys.executable, "-I", str(F.DIAG), model, str(pred), str(out / "diag_expA")], capture_output=True, text=True)
R["diag"] = dict(returncode=r.returncode, stderr_tail=r.stderr[-500:])
R["parse_failures"] = F.pfail_table(rows, "ExpA")
R["agreement"] = {"ExpA": F.agreement(rows)}
(out / "results.json").write_text(json.dumps(R, ensure_ascii=False, indent=1, default=str))
print("done", model)
