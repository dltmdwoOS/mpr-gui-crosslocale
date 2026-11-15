"""Post-hoc quality and cost; gold annotations are never imported by candidate execution."""
import argparse,csv,json,sys
from pathlib import Path
from collections import Counter,defaultdict
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from evaluation import read,span_f1


def main():
    p=argparse.ArgumentParser();p.add_argument('--trial-dir',type=Path,required=True);p.add_argument('--oracle-spans',type=Path,required=True)
    a=p.parse_args();out=a.trial_dir/'quality.json'
    if out.exists():raise ValueError('Quality already scored; preserve existing result')
    if not (a.trial_dir/'COMPLETE').exists():raise ValueError('Incomplete trial')
    contract=json.loads((a.trial_dir/'contract.json').read_text());gold={r['pair_id']:r['referents'] for r in read(a.oracle_spans)}
    by_language=defaultdict(Counter);totals=Counter();review=[]
    path=a.trial_dir/'extractions.jsonl'
    if path.exists():
        for r in read(path):
            metric=span_f1(r['referents'],gold[r['pair_id']]);metric={k:metric[k] for k in ('tp','predicted','gold')}
            metric.update(mcqs=1,empty=not r['referents'],schema_failed=r['status']!='success',complete_span_set=metric['tp']==metric['predicted']==metric['gold'])
            totals.update(metric);by_language[r['source_language']].update(metric)
    rewrites=a.trial_dir/'rewritten.jsonl'
    if rewrites.exists():
        for r in read(rewrites):
            totals['pairs']+=1
            if r['inventory'] is not None:
                totals['inventory_failed_pairs']+=r['inventory']['status']=='failed'
                totals['inventory_empty_pairs']+=r['inventory']['status']=='empty'
            totals['fallback_original']+=r['generation_status']=='fallback_original';totals['no_edit_pairs']+=not r['edits'];totals['edits']+=len(r['edits'])
            for e in r['edits']:
                exact=any(e['field']==g['field'] and e['start']==g['start'] and e['end']==g['end'] for g in gold[r['pair_id']])
                totals['edit_spans_exact_annotation']+=exact
                review.append({'pair_id':r['pair_id'],'image_path':r['image_path'],'field':e['field'],'source':e['text'],'replacement':e['replacement'],
                               'span_exact_annotation':exact,'screen_correspondence':'','wrong_gui_element':'','context_change':'','notes':''})
    def rates(x):
        x=dict(x);tp=x.get('tp',0);pred=x.get('predicted',0);g=x.get('gold',0)
        return {**x,'precision':tp/pred if pred else None,'recall':tp/g if g else None,'f1':2*tp/(pred+g) if pred+g else None}
    result={'execution_mode':contract['execution_mode'],'empirical':contract['execution_mode']=='gpu','metrics':rates(totals),'by_source_language':{k:rates(v) for k,v in by_language.items()},
        'screen_matching_precision':None,'note':'Annotation span exactness is not screenshot matching accuracy. Direct methods expose edits only, not a complete extraction set. MOCK is not empirical evidence.'}
    with (a.trial_dir/'edit_review.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['pair_id','image_path','field','source','replacement','span_exact_annotation','screen_correspondence','wrong_gui_element','context_change','notes']);writer.writeheader();writer.writerows(review)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
