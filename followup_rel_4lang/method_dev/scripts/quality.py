"""Post-hoc span diagnostics and independent screenshot matching review export."""
import argparse,csv,json,sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE))
from evaluation import read,span_f1


def main():
    p=argparse.ArgumentParser();p.add_argument('--rewritten',type=Path,required=True);p.add_argument('--oracle-spans',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    if a.output_dir.exists():raise ValueError('Fresh output required')
    rows=[r for r in read(a.rewritten) if r['condition']=='GUI_SEL'];gold={r['pair_id']:r['referents'] for r in read(a.oracle_spans)}
    metrics=Counter();review=[];reasons=Counter();per_gui={}
    for r in rows:
        q=span_f1(r['extracted_referents'],gold[r['pair_id']])
        for key in ['tp','predicted','gold']:metrics[key]+=q[key]
        metrics['pairs']+=1;metrics['empty_extraction']+=not r['extracted_referents']
        metrics['inventory_failed']+=r['inventory']['status']=='failed';metrics['inventory_empty']+=r['inventory']['status']=='empty'
        metrics['matched']+=len(r['selected_matches']);metrics['rewritten']+=len(r['edits'])
        metrics['fallback_pairs']+=bool(r['fallback_reasons']);reasons.update(r['fallback_reasons'])
        per_gui.setdefault(r['gui_language'],Counter()).update(pairs=1,matched=len(r['selected_matches']),edits=len(r['edits']))
        for m in r['candidate_matches']:
            ref=next(x for x in r['extracted_referents'] if x['span_id']==m['span_id'])
            review.append({'pair_id':r['pair_id'],'image_path':r['image_path'],'field':ref['field'],'source':ref['text'],
                           'decision':m['decision'],'proposed_gui_string':m.get('replacement',''),'reason':m['reason'],
                           'screenshot_correspondence':'','ocr_missing':'','wrong_gui_element':'','review_notes':''})
    output=dict(metrics);pcount=metrics['predicted'];gcount=metrics['gold'];tp=metrics['tp']
    output.update(span_precision=tp/pcount if pcount else None,span_recall=tp/gcount if gcount else None,
                  span_f1=2*tp/(pcount+gcount) if pcount+gcount else None,
                  matching_coverage=metrics['matched']/pcount if pcount else None,
                  matching_precision=None,incorrect_replacement_rate=None,
                  reason='Matching precision requires independent screenshot review, not parallel-QAS equality',
                  fallback_reasons=dict(reasons),by_gui=per_gui)
    a.output_dir.mkdir(parents=True);(a.output_dir/'quality.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    keys=['pair_id','image_path','field','source','decision','proposed_gui_string','reason','screenshot_correspondence','ocr_missing','wrong_gui_element','review_notes']
    with (a.output_dir/'matching_review.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(review)
    print(json.dumps(output,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
