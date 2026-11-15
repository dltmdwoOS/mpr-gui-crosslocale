"""Freeze a completed calibration run; never optimize against evaluation predictions."""
import argparse,json,hashlib
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--calibration-run',type=Path,required=True)
    p.add_argument('--split',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh frozen config path required')
    config=json.loads(a.config.read_text());contract=json.loads((a.calibration_run/'contract.json').read_text())
    if contract['partition']!='calibration' or contract['mode']!='gpu' or contract['config']!=config:
        raise ValueError('Need actual calibration run under exactly this config')
    split=json.loads(a.split.read_text())['items'];expected={pid for pid,v in split.items() if v=='calibration'}
    rows=[json.loads(l) for l in (a.calibration_run/'rewritten.jsonl').read_text().splitlines() if l.strip()]
    if {r['parallel_id'] for r in rows}!=expected or len(rows)!=len(expected)*12*4:
        raise ValueError('Incomplete calibration cohort or duplicate/missing rows')
    ids={(r['pair_id'],r['condition']) for r in rows}
    if len(ids)!=len(rows):raise ValueError('Duplicate rows')
    config.update(calibration_frozen=True,calibration_run_contract_sha256=hashlib.sha256((a.calibration_run/'contract.json').read_bytes()).hexdigest(),
                  calibration_method_edits_informed_by='calibration only; disclose any prior internal evaluation access')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(config,indent=2)+'\n')
if __name__=='__main__':main()
