"""Privileged evaluation boundary. Joins labels only after transformations finish."""
import argparse,gzip,json,sys
from pathlib import Path
from collections import Counter,defaultdict
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(REPO)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest
PRIMARY=[('GUI_SEL','O'),('GUI_SEL','TXT_SEL'),('GUI_SEL','GUI_FULL')]

def read(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8') as f:return [json.loads(l) for l in f if l.strip()]

def load_predictions(path):
    result={}
    for r in read(path):
        if r.get('execution_mode')=='mock':raise ValueError('Mock predictions cannot be empirical evidence')
        condition={'T':'T_REF','R':'R_REF'}.get(r['condition'],r['condition'])
        key=(r['pair_id'],condition)
        if key in result:raise ValueError('Duplicate prediction ID; resolve attempts explicitly first')
        result[key]={**r,'condition':condition}
    return result

def span_f1(predicted,gold):
    p={(r['field'],r['start'],r['end']) for r in predicted};g={(r['field'],r['start'],r['end']) for r in gold}
    hit=len(p&g);return {'tp':hit,'predicted':len(p),'gold':len(g),'precision':hit/len(p) if p else None,
                         'recall':hit/len(g) if g else None,'f1':2*hit/(len(p)+len(g)) if p or g else None}

def contrasts(rows,labels,replicates=10000,seed=20261115):
    import numpy as np
    eligible={r['pair_id']:r for r in labels if r['primary_included'] and r['split']=='main'}
    required={'O','T_REF','R_REF','TXT_FULL','GUI_FULL','TXT_SEL','GUI_SEL'}
    selected={key:value for key,value in rows.items() if key[0] in eligible}
    for pid in eligible:
        if {c for p,c in selected if p==pid}!=required:raise ValueError('Missing paired conditions: '+pid)
    correct={k:int(v.get('status')=='success' and v.get('parsed_generated_label')==eligible[k[0]]['gold_answer']) for k,v in selected.items()}
    items=sorted({r['parallel_id'] for r in eligible.values()});by_item=defaultdict(list)
    for pid,lab in eligible.items():by_item[lab['parallel_id']].append(pid)
    rng=np.random.default_rng(seed); draws=rng.integers(0,len(items),size=(replicates,len(items)))
    counts=np.array([len(by_item[i]) for i in items]);out=[]
    for left,right in PRIMARY+[('GUI_SEL','R_REF'),('GUI_SEL','T_REF'),('TXT_SEL','TXT_FULL')]:
        sums=np.array([sum(correct[p,left]-correct[p,right] for p in by_item[i]) for i in items])
        observed=sums.sum()/counts.sum();bs=sums[draws].sum(1)/counts[draws].sum(1)
        pvalue=(1+int((np.abs(bs-observed)>=abs(observed)).sum()))/(replicates+1)
        out.append({'contrast':f'{left}-{right}','difference':float(observed),'ci95':[float(x) for x in np.quantile(bs,[.025,.975])],
                    'bootstrap_centered_p_exploratory':pvalue,'pair_count':len(eligible),'semantic_items':len(items),
                    'incorrect_to_correct':sum(correct[p,left]>correct[p,right] for p in eligible),
                    'correct_to_incorrect':sum(correct[p,left]<correct[p,right] for p in eligible)})
    ordered=sorted(out[:3],key=lambda r:r['bootstrap_centered_p_exploratory']);adjusted=0
    for rank,r in enumerate(ordered):
        adjusted=max(adjusted,min(1,(3-rank)*r['bootstrap_centered_p_exploratory']));r['holm_primary_p']=adjusted
    descriptive={c:{'n':len(eligible),'accuracy':sum(correct[p,c] for p in eligible)/len(eligible)} for c in sorted(required)}
    pairs=defaultdict(list)
    for pid in eligible:pairs[pid.rsplit('::',2)[1]+'->'+pid.rsplit('::',1)[1]].append(pid)
    pair_acc={direction:{c:sum(correct[p,c] for p in ids)/len(ids) for c in sorted(required)} for direction,ids in pairs.items()}
    gui_acc={g:{c:sum(correct[p,c] for p in eligible if p.rsplit('::',1)[1]==g)/sum(p.rsplit('::',1)[1]==g for p in eligible) for c in sorted(required)} for g in sorted({p.rsplit('::',1)[1] for p in eligible})}
    return {'outcome':'generation; missing/failed/unparsed output counts as incorrect','replicates':replicates,'seed':seed,
            'accuracy':descriptive,'contrasts':out,'by_language_pair':pair_acc,'by_gui_language':gui_acc,
            'worst_pair':{c:min(v[c] for v in pair_acc.values()) for c in required}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--predictions',nargs='+',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--baseline',type=Path,help='Historical ExpA O/T/R predictions; import T/R only and report O agreement')
    p.add_argument('--split',type=Path,required=True);p.add_argument('--partition',choices=['calibration','internal_evaluation'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh output required')
    rows={}
    for path in a.predictions:
        incoming=load_predictions(path)
        if set(incoming)&set(rows):raise ValueError('Overlapping predictions')
        rows.update(incoming)
    historical=load_predictions(a.baseline) if a.baseline else {}
    anchor_pairs=[pid for pid,c in rows if c=='O' and (pid,'O') in historical]
    agreement={'n':len(anchor_pairs),'same_label':sum(rows[p,'O'].get('parsed_generated_label')==historical[p,'O'].get('parsed_generated_label') for p in anchor_pairs)}
    for key,r in historical.items():
        if key[1] in ('T_REF','R_REF'):
            if key in rows:raise ValueError('Duplicate reference prediction')
            rows[key]=r
    split=json.loads(a.split.read_text())['items'];labels=[r for r in read(a.labels) if split.get(r['parallel_id'])==a.partition]
    result=contrasts(rows,labels);result['historical_O_anchor_agreement']=agreement;a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
