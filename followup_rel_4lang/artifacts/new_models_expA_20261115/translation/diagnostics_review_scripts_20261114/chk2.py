import json,collections,math
import numpy as np
from difflib import SequenceMatcher
B="/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스/"
P=collections.defaultdict(dict)
for l in open(B+"expA_results_20261114/qwen3/expA_qwen3/full/predictions.jsonl"):
    l=l.strip()
    if l:
        r=json.loads(l)
        if r['split']=='main': P[r['pair_id']][r['condition']]=r
S=collections.defaultdict(list)
for l in open(B+"expA_translation_20261112/work/T_gemma_first_spans.jsonl"):
    s=json.loads(l)
    if s['split']=='main': S[s['pair_id']].append(s)
def sim(a,b): return SequenceMatcher(None,a.replace(' ','').casefold(),b.replace(' ','').casefold()).ratio()
feat={}
for p,ss in S.items():
    if p not in P or len(P[p])<3: continue
    near=0;dupT=0;dupR=0;nd=0
    tr=[s['translation'] for s in ss]; sc=[s['screen_text'] for s in ss]
    opts=[s for s in ss if s['field'] in 'ABCD']
    ot=[s['translation'] for s in opts]; osc=[s['screen_text'] for s in opts]; osrc=[s['source_text'] for s in opts]
    dupT=len(set(ot))<len(ot) and len(set(osrc))==len(osrc)
    for i,s in enumerate(ss):
        if s['translation']!=s['screen_text']:
            nd+=1
            own=sim(s['translation'],s['screen_text'])
            oth=max([sim(s['translation'],x) for j,x in enumerate(sc) if j!=i and x!=s['screen_text']] or [0])
            if oth>own and oth>=0.5: near+=1
    feat[p]=dict(g=ss[0]['gui_language'],near=near>0,dupT=dupT,nd=nd)
def show(n,ps):
    if not ps: print(n,'n=0');return
    a=lambda c:100*np.mean([P[p][c]['generation_correct'] for p in ps])
    print(f"{n:28s} n={len(ps):4d} O={a('O'):5.1f} T={a('T'):5.1f} R={a('R'):5.1f} T-O={a('T')-a('O'):+6.1f}")
for g in ['th','rest']:
    for k in ['near','dupT']:
        for v in [False,True]:
            show(f"gui={g} {k}={v}",[p for p in feat if (feat[p]['g']=='th')==(g=='th') and feat[p][k]==v])
for g in 'en zh th ru'.split(): print(g,'near pairs',sum(f['near'] for f in feat.values() if f['g']==g),'dupT',sum(f['dupT'] for f in feat.values() if f['g']==g))
