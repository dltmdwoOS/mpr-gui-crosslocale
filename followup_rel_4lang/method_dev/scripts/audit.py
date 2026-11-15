"""Privileged data adapter and oracle reconstruction diagnostics. Never imported by method code."""
import argparse,hashlib,json,random,sys
from collections import defaultdict,Counter
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO)]
from mpr_crosslocale.methods.selective_alignment.schemas import FIELDS,fields,digest,validate_input
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.data.rel_followup import verify_bundle,unpack
ROOT=REPO/'followup_rel_4lang'
EXP=ROOT/'artifacts/new_models_expA_20261115'
TRANS=EXP/'translation'
EXCLUDED='rel::5/forest_9.jpg::zh::ru'


def read(p):return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def jsonl(p,rows):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=ROOT/'method_dev/artifacts/dataset_audit');a=p.parse_args()
    if a.output_dir.exists():raise ValueError('Fresh audit directory required')
    before={str(p.relative_to(REPO)):sha(p) for folder in [TRANS,EXP/'rules',ROOT/'rstem_ropts_inputs'] for p in folder.rglob('*') if p.is_file()}
    lock=json.loads((ROOT/'dataset_lock.json').read_text());bundle=ROOT/'bundles/rel_all_366.tar.gz'
    assert sha(bundle)==lock['bundle_sha256'] and bundle.stat().st_size==lock['bundle_bytes']
    if not (ROOT/'data/rel_all_366/conditions_4lang.jsonl').exists():unpack(bundle,ROOT,ROOT/'dataset_lock.json')
    manifest=verify_bundle(ROOT,images=False)
    data=ROOT/'data/rel_all_366';assert sha(data/'conditions_4lang.jsonl')==lock['conditions_sha256']
    tlock=json.loads((TRANS/'addon/followup_rel_4lang/expA/expA_inputs/expA_lock.json').read_text())
    frozen_t=TRANS/'addon/followup_rel_4lang/expA/expA_inputs/T_conditions.jsonl'
    assert sha(frozen_t)==tlock['T_conditions.jsonl']
    assert sha(data/'reference_mappings.jsonl')==tlock['source_reference_mappings.jsonl']
    assert sha(ROOT/'rstem_ropts_inputs/mixed_conditions.jsonl')==tlock['source_mixed_conditions.jsonl']
    for name,expected in tlock['translations'].items():assert sha(TRANS/name)==expected
    mixed=read(ROOT/'rstem_ropts_inputs/mixed_conditions.jsonl');by_pair={r['pair_id']:r for r in mixed}
    cond={(r['pair_id'],r['condition']):r for r in read(data/'conditions_4lang.jsonl')}
    mappings={r['parallel_id']:r for r in read(data/'reference_mappings.jsonl')}
    ts={r['pair_id']:r for r in read(TRANS/'work/T_gemma_first_conditions.jsonl')}
    saved_trans={}
    for r in read(TRANS/'work/translations_gemma.jsonl')+read(TRANS/'work/translations_gemma_parsefail.jsonl'):
        if r.get('parse_ok'):
            saved_trans.update({(r['parallel_id'],r['src_lang'],r['tgt_lang'],x):y for x,y in zip(r['inputs'],r['translations'],strict=True)})
    assert set(ts)==set(by_pair)=={r['pair_id'] for r in read(frozen_t)}
    inputs=[];oracle=[];labels=[];images={};counts=Counter()
    for pid,m in sorted(by_pair.items()):
        o,r=cond[pid,'O'],cond[pid,'R'];q,g=o['query_language'],o['gui_language']
        mp=mappings[o['parallel_id']]['spans'];target={s['ref_id']:s['text'] for f in FIELDS for s in mp[g].get(f,[])}
        spanlist=[{**s,'field':f,'span_id':s['ref_id']} for f in FIELDS for s in mp[q].get(f,[])]
        redits=[{**s,'replacement':target[s['ref_id']]} for s in spanlist]
        tedits=[{**s,'replacement':saved_trans[o['parallel_id'],q,g,s['text']]} for s in spanlist]
        assert apply_edits(o,redits,reject_collisions=False)==fields(r),('R',pid)
        assert apply_edits(o,tedits,reject_collisions=False)==fields(ts[pid]),('T',pid)
        assert m['gold_answer']==ts[pid]['gold_answer']==o['gold_answer']==r['gold_answer']
        assert m['image_path'].endswith(o['image_path']) and ts[pid]['image_sha256']==m['image_sha256']
        row={k:o[k] for k in ['pair_id','parallel_id','question_stem','options','option_order']}
        row.update(source_language=q,gui_language=g,image_path='followup_rel_4lang/'+o['image_path'],image_sha256=m['image_sha256'])
        validate_input(row);inputs.append(row);counts[m['split']]+=1
        oracle.append({'pair_id':pid,'oracle_span':True,'referents':spanlist})
        labels.append({'pair_id':pid,'parallel_id':o['parallel_id'],'split':m['split'],'gold_answer':o['gold_answer'],'primary_included':pid!=EXCLUDED})
        images[row['image_path']]=row['image_sha256']
    assert counts=={'main':1896,'pilot':48}
    main_ids={r['parallel_id'] for r in labels if r['split']=='main'};assert len(main_ids)==158
    # Union exact image hashes and same app+screen stem across IDs. No labels/outcomes used.
    parent={i:i for i in main_ids}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(x,y):parent[find(y)]=find(x)
    owner={}
    for row in inputs:
        if row['parallel_id'] not in main_ids:continue
        for key in [('sha',row['image_sha256']),('state',row['parallel_id'].split('::',1)[1])]:
            if key in owner:union(row['parallel_id'],owner[key])
            else:owner[key]=row['parallel_id']
    grouped=defaultdict(list)
    for i in sorted(main_ids):grouped[find(i)].append(i)
    clusters=sorted(grouped.values());random.Random(20261115).shuffle(clusters)
    calibration=set()
    for cluster in clusters:
        if len(calibration)<40:calibration.update(cluster)
    assignment={i:'calibration' if i in calibration else 'internal_evaluation' for i in sorted(main_ids)}
    split={'seed':20261115,'grouping':'union exact screenshot SHA-256 or identical state key after rel::; no perceptual near-duplicate claim',
           'groups':clusters,'items':assignment,'item_counts':dict(Counter(assignment.values())),
           'evaluation_untouched_by_new_method_tuning':True,'historically_observed_development_cohort':True}
    seen_images={};missing=[]
    for path,expected in images.items():
        pth=REPO/path
        if pth.exists():assert sha(pth)==expected,path;seen_images[path]=expected
        else:missing.append(path)
    for rel,h in before.items():assert sha(REPO/rel)==h,'Frozen input changed'
    primary=sum(r['split']=='main' and r['primary_included'] for r in labels);assert primary==1895
    result={'base_commit':'e4aff7ace7248f1dd4e5a5dac0d4f679b33c6b5a','bundle_verified':True,'T_lock_verified':True,
            'R_reconstruction_exact':len(inputs),'T_gemma_first_reconstruction_exact':len(inputs),'pair_counts':dict(counts),
            'main_primary_pairs':primary,'excluded_pair':EXCLUDED,'unique_screens':len(images),'verified_images':len(seen_images),
            'missing_images':missing,'source_hf':manifest['source'],'split_counts':split['item_counts'],
            'first_T_vs_final_T_same_sha':sha(TRANS/'work/T_gemma_first_conditions.jsonl')==sha(frozen_t),
            'frozen_inputs_sha256':before,'note':'Final T artifact may differ from first-pass T; both separately locked. No target expressions in method inputs.'}
    write(a.output_dir/'audit.json',result);write(a.output_dir/'split.json',split)
    jsonl(a.output_dir/'method_inputs.jsonl',inputs);jsonl(a.output_dir/'oracle_spans_DIAGNOSTIC_ONLY.jsonl',oracle)
    jsonl(a.output_dir/'evaluation_labels_PRIVATE.jsonl',labels)
    print(json.dumps({k:v for k,v in result.items() if k not in ['frozen_inputs_sha256','missing_images']},indent=2))

if __name__=='__main__':main()
