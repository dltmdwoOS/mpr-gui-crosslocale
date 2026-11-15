"""Freeze larger development cohorts without touching the 118-item internal evaluation."""
import argparse,hashlib,json,math,sys
from pathlib import Path
from collections import Counter,defaultdict
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(REPO)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,validate_input
EXCLUDED='rel::5/forest_9.jpg::zh::ru'


def build(rows,split,spec):
    for r in rows:validate_input(r)
    assignment=split['items'];by_item=defaultdict(list)
    for r in rows:by_item[r['parallel_id']].append(r)
    if set(assignment)-set(by_item):raise ValueError('Missing main items')
    owners=defaultdict(set)
    for r in rows:
        for k in [('sha',r['image_sha256']),('state',r['parallel_id'].split('::',1)[1])]:owners[k].add(r['parallel_id'])
    # Partition existing semantic groups jointly, never split repeated screenshots.
    parent={i:i for i in by_item}
    def find(x):
        while parent[x]!=x:x=parent[x]
        return x
    for ids in owners.values():
        ids=sorted(ids)
        for i in ids[1:]:parent[find(i)]=find(ids[0])
    groups=defaultdict(list)
    for i in sorted(parent):groups[find(i)].append(i)
    for ids in groups.values():
        partitions={assignment.get(i,'legacy_pilot') for i in ids}
        if len(partitions)>1:raise ValueError('Existing split crosses duplicate screen groups')
    cal=[i for i,v in assignment.items() if v=='calibration'];target=spec['screen_calibration_items']
    if any(len(ids)>1 and ids[0] in cal for ids in groups.values()):raise ValueError('Grouped calibration requires explicit group-level allocation; do not silently split')
    buckets=defaultdict(list)
    for i in cal:buckets[i.split('::',1)[1].split('/')[0]].append(i)
    quotas={k:math.floor(target*len(v)/len(cal)) for k,v in buckets.items()}
    order=sorted(buckets,key=lambda k:(-(target*len(buckets[k])/len(cal)-quotas[k]),k))
    for k in order[:target-sum(quotas.values())]:quotas[k]+=1
    rank=lambda i:digest([spec['seed'],'search-v1',i])
    screen_main={i for k,v in buckets.items() for i in sorted(v,key=rank)[:quotas[k]]}
    legacy={i for i in by_item if i not in assignment};probe=set(sorted(legacy,key=rank)[:spec['probe_legacy_items']])
    cohorts={'probe':probe,'screen':legacy|screen_main,'selection':set(cal)-screen_main}
    if len(screen_main)!=target:raise ValueError('Wrong screen size')
    if cohorts['screen'] & cohorts['selection']:raise ValueError('Cohort overlap')
    evaluation={i for i,v in assignment.items() if v=='internal_evaluation'}
    if any(ids&evaluation for ids in cohorts.values()):raise ValueError('Internal evaluation leak')
    result={}
    for name,ids in cohorts.items():
        selected=sorted((r for r in rows if r['parallel_id'] in ids),key=lambda r:r['pair_id'])
        result[name]={'item_ids':sorted(ids),'semantic_items':len(ids),'pairs':len(selected),'main_primary_pairs':sum(r['parallel_id'] in assignment and r['pair_id']!=EXCLUDED for r in selected),
            'legacy_pairs':sum(r['parallel_id'] in legacy for r in selected),'unique_source_mcqs':len({(r['parallel_id'],r['source_language']) for r in selected}),
            'unique_images':len({r['image_sha256'] for r in selected}),'by_direction':dict(Counter(r['source_language']+'->'+r['gui_language'] for r in selected)),
            'inputs_sha256':digest(selected)}
    manifest={'version':spec['version'],'seed':spec['seed'],'split_sha256':digest(split),'spec_sha256':digest(spec),'input_sha256':digest(rows),
        'cohorts':result,'screen_calibration_items':sorted(screen_main),'selection_items':sorted(set(cal)-screen_main),
        'internal_evaluation_untouched':True,'internal_evaluation_items':len(evaluation),'historically_observed_development_data':True,
        'selection_reuse_policy':'selection may be observed once per frozen shortlist; any subsequent changes contaminate selection and must be recorded',
        'excluded_main_pair':EXCLUDED,'calibration_app_quotas':quotas}
    return manifest,{name:[r for r in sorted(rows,key=lambda r:r['pair_id']) if r['parallel_id'] in ids] for name,ids in cohorts.items()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--split',type=Path,required=True)
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    if a.output_dir.exists():raise ValueError('Fresh directory required')
    rows=[json.loads(l) for l in a.inputs.read_text().splitlines() if l.strip()]
    manifest,cohorts=build(rows,json.loads(a.split.read_text()),json.loads(a.spec.read_text()))
    a.output_dir.mkdir(parents=True)
    for name,selected in cohorts.items():(a.output_dir/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected))
    (a.output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{x:v[x] for x in ['semantic_items','pairs','unique_source_mcqs','unique_images','main_primary_pairs','legacy_pairs']} for k,v in manifest['cohorts'].items()},indent=2))
if __name__=='__main__':main()
