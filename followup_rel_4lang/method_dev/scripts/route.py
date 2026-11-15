"""RFA extension; consume identical GUI_SEL referents and a frozen calibration pivot policy."""
import argparse,json,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from backend import TransformersBackend
from mpr_crosslocale.methods.selective_alignment.context_router import route_context
from mpr_crosslocale.methods.selective_alignment.schemas import fields,render,digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--rewritten',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--pivot-policy',type=Path,required=True);p.add_argument('--model',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();policy=json.loads(a.pivot_policy.read_text());config=json.loads(a.config.read_text())
    if not policy.get('calibration_frozen') or policy.get('chosen_from')!='calibration':raise ValueError('Need frozen calibration-only pivot policy')
    pivot=policy['model_pivots'][a.model]
    if pivot not in ('en','zh','th','ru'):raise ValueError('Invalid pivot')
    meta=json.loads((a.rewritten.parent/'contract.json').read_text())
    if meta['mode']!='gpu':raise ValueError('Mock cannot serve as RFA empirical input')
    if a.output.exists():raise ValueError('Fresh output required')
    backend=TransformersBackend(config,REPO);a.output.parent.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(l) for l in a.rewritten.read_text().splitlines() if l.strip()]
    with a.output.open('w') as out:
        for row in rows:
            if row['condition']!='GUI_SEL':continue
            refs=row['extracted_referents'];replacement={e['span_id']:e['replacement'] for e in row['edits']}
            protected=[{**r,'replacement':replacement.get(r['span_id'],r['text'])} for r in refs]
            for condition,target in [('GUI_SEL_EN','en'),('GUI_SEL_MODEL_PIVOT',pivot)]:
                started=time.perf_counter();reasons=[];aligned=fields(row)
                try:
                    translated=route_context(aligned,protected,lambda text:backend('context',text,{}),target)
                    status='success'
                except Exception as exc:translated=aligned;status='fallback_aligned_context';reasons=[str(exc)]
                record={**row,'condition':condition,'question_stem':translated['question_stem'],'options':{k:translated[k] for k in 'ABCD'},
                    'modified_question':render(translated),'context_language':target,'generation_status':status,'fallback_reasons':reasons,
                    'routing_runtime_ms':(time.perf_counter()-started)*1000,'pivot_policy_sha256':digest(policy),
                    'third_language':target not in (row['source_language'],row['gui_language']),
                    'semantic_preservation':'placeholder and digit checks only; direction/negation meaning requires independent review'}
                out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
    a.output.with_suffix('.calls.json').write_text(json.dumps(backend.calls,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
