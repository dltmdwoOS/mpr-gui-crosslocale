import json,collections
import numpy as np
B="/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스/"
P=collections.defaultdict(dict)
for l in open(B+"expA_results_20261114/qwen3/expA_qwen3/full/predictions.jsonl"):
    l=l.strip()
    if l:
        r=json.loads(l)
        if r['split']=='main': P[r['pair_id']][r['condition']]=r
pairs=[p for p in P if len(P[p])==3]
item=np.array([P[p]['O']['parallel_id'] for p in pairs]); th=np.array([P[p]['O']['gui_language']=='th' for p in pairs])
c={k:np.array([P[p][k]['generation_correct'] for p in pairs],float) for k in 'OTR'}
items=sorted(set(item)); idx={i:np.where(item==i)[0] for i in items}
def stats(ix):
    t=th[ix]; d=lambda a,b:(c[a][ix][t].mean()-c[b][ix][t].mean())-(c[a][ix][~t].mean()-c[b][ix][~t].mean())
    return [100*d('T','O'),100*d('R','O'),100*d('R','T'),100*(c['T'][ix][t].mean()-c['O'][ix][t].mean()),100*(c['T'][ix][~t].mean()-c['O'][ix][~t].mean())]
rng=np.random.default_rng(20261114)
bb=np.array([stats(np.concatenate([idx[i] for i in rng.choice(items,len(items))])) for _ in range(5000)])
pt=stats(np.arange(len(pairs)))
for n,v,col in zip(['DiD T-O','DiD R-O','DiD R-T','T-O th','T-O rest'],pt,bb.T):
    print(n,round(v,2),'90%',np.percentile(col,[5,95]).round(2),'95%',np.percentile(col,[2.5,97.5]).round(2),'sd',col.std().round(2))
print('corr DiD T-O vs DiD R-O',np.corrcoef(bb[:,0],bb[:,1])[0,1])
