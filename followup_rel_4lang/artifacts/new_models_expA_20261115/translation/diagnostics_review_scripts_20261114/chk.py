import json,csv,math,collections,random
import numpy as np
B="/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스/"
rows={}
for l in open(B+"expA_results_20261114/qwen3/expA_qwen3/full/predictions.jsonl"):
    l=l.strip()
    if not l: continue
    r=json.loads(l)
    if r['split']!='main': continue
    rows[r['input_id']]=r
P=collections.defaultdict(dict)
for r in rows.values(): P[r['pair_id']][r['condition']]=r
F={r['pair_id']:r for r in csv.DictReader(open(B+"expA_translation_20261112/diagnostics_inputs_20261114/per_pair_features.csv"))}
pairs=[p for p in P if p in F and len(P[p])==3]
print('pairs',len(pairs), 'statuses',collections.Counter(r['status'] for r in rows.values()), 'parse',collections.Counter(r['parse_success'] for r in rows.values()))
gp=[r['gold_probability'] for r in rows.values()]
print('goldprob min',min(gp),'n<1e-6',sum(g<1e-6 for g in gp),'n>0.999',sum(g>0.999 for g in gp),'n',len(gp))
print('sum label probs: min',min(sum(r['label_probabilities'].values()) for r in rows.values()))
def acc(ps,c): return 100*np.mean([P[p][c]['generation_correct'] for p in ps]) if ps else float('nan')
def to(ps): return acc(ps,'T')-acc(ps,'O')
def show(name,ps): print(f"{name:32s} n={len(ps):4d} O={acc(ps,'O'):5.1f} T={acc(ps,'T'):5.1f} R={acc(ps,'R'):5.1f} T-O={to(ps):+6.1f}  dlogp={np.mean([math.log(max(P[p]['T']['gold_probability'],1e-12))-math.log(max(P[p]['O']['gold_probability'],1e-12)) for p in ps]) if ps else 0:+.3f}")
print('--cells')
for q in 'en zh th ru'.split():
    for g in 'en zh th ru'.split():
        if q!=g: show(f"{q}>{g}",[p for p in pairs if F[p]['query_language']==q and F[p]['gui_language']==g])
print('--by query lang')
for q in 'en zh th ru'.split(): show('q='+q,[p for p in pairs if F[p]['query_language']==q])
print('-- non-th screens, by query th vs not')
show('gui!=th,q=th',[p for p in pairs if F[p]['gui_language']!='th' and F[p]['query_language']=='th'])
show('gui!=th,q!=th',[p for p in pairs if F[p]['gui_language']!='th' and F[p]['query_language']!='th'])
print('--gui x any_lost')
for g in 'en zh th ru'.split():
    for a in '01': show(f"gui={g} lost={a}",[p for p in pairs if F[p]['gui_language']==g and F[p]['any_lost']==a])
show('all lost=1',[p for p in pairs if F[p]['any_lost']=='1']); show('all lost=0',[p for p in pairs if F[p]['any_lost']=='0'])
print('--gui(th/rest) x T_exact bin')
def bin(x):
    x=float(x); return '0' if x==0 else '(0,.5)' if x<.5 else '[.5,1)' if x<1 else '1'
for g in ['th','rest']:
    for b in ['0','(0,.5)','[.5,1)','1']:
        show(f"gui={g} Tex={b}",[p for p in pairs if (F[p]['gui_language']=='th')==(g=='th') and bin(F[p]['T_exact_frac'])==b])
print('--gui x stem_T_exact')
for g in ['th','rest']:
    for b in ['0.0','1.0']:
        show(f"gui={g} stemT={b}",[p for p in pairs if (F[p]['gui_language']=='th')==(g=='th') and F[p]['stem_T_exact']==b])
print('--gui x mixed_O_span (O already has foreign script)')
for g in ['th','rest']:
    for b in '01': show(f"gui={g} mixedO={b}",[p for p in pairs if (F[p]['gui_language']=='th')==(g=='th') and F[p]['mixed_O_span']==b])
print('--gold position')
for g in ['th','rest']:
    for a in 'ABCD': show(f"gui={g} gold={a}",[p for p in pairs if (F[p]['gui_language']=='th')==(g=='th') and P[p]['O']['gold_answer']==a])
print('gold same across cond',all(len({P[p][c]['gold_answer'] for c in 'OTR'})==1 for p in pairs))
print('pred label dist', {c:collections.Counter(P[p][c]['parsed_generated_label'] for p in pairs) for c in 'OTR'})
# regression w/ item cluster bootstrap
y=np.array([P[p]['T']['generation_correct']-P[p]['O']['generation_correct'] for p in pairs],float)
yl=np.array([math.log(max(P[p]['T']['gold_probability'],1e-12))-math.log(max(P[p]['O']['gold_probability'],1e-12)) for p in pairs])
th=np.array([F[p]['gui_language']=='th' for p in pairs],float)
de=np.array([float(F[p]['delta_exact_T_minus_O']) for p in pairs]); dc=np.array([(float(F[p]['chrF_T'])-float(F[p]['chrF_O']))/100 for p in pairs])
lost=np.array([float(F[p]['any_lost']) for p in pairs])
item=np.array([F[p]['parallel_id'] for p in pairs]); items=sorted(set(item)); idx={i:np.where(item==i)[0] for i in items}
def fit(X,yy,ix): return np.linalg.lstsq(X[ix],yy[ix],rcond=None)[0]
one=np.ones(len(pairs))
models={'th only':np.c_[one,th],'th+d_exact':np.c_[one,th,de],'th+d_exact+d_chrf':np.c_[one,th,de,dc],'th+d_chrf':np.c_[one,th,dc],'d_exact only':np.c_[one,de],'th+de+th*de':np.c_[one,th,de,th*de]}
rng=np.random.default_rng(20261114)
bs=[np.concatenate([idx[i] for i in rng.choice(items,len(items))]) for _ in range(1000)]
for yn,yy in [('acc',y),('logp',yl)]:
  for n,X in models.items():
    b=fit(X,yy,np.arange(len(pairs))); bb=np.array([fit(X,yy,ix) for ix in bs])
    print(yn,n,' '.join(f"{v:+.3f}[{lo:+.3f},{hi:+.3f}]" for v,lo,hi in zip(b,np.percentile(bb,2.5,0),np.percentile(bb,97.5,0))))
print('corr th,de',np.corrcoef(th,de)[0,1],'mean de th/rest',de[th==1].mean(),de[th==0].mean(),'dc',dc[th==1].mean(),dc[th==0].mean())
# P3 power: lost diff bootstrap
d=[ (y[ix][lost[ix]==1].mean()-y[ix][lost[ix]==0].mean()) if (lost[ix]==1).any() else np.nan for ix in bs]
print('lost1-lost0 acc',y[lost==1].mean()-y[lost==0].mean(),np.nanpercentile(d,[2.5,97.5]),'n lost',int(lost.sum()),'items w/ lost',len(set(item[lost==1])))
# item composition: O acc on th screens vs same items on other screens
# transition table
for g in ['th','rest']:
    ps=[p for p in pairs if (F[p]['gui_language']=='th')==(g=='th')]
    print(g,collections.Counter((P[p]['O']['generation_correct'],P[p]['T']['generation_correct']) for p in ps))
# floors: extreme logp diffs
print('logp diff pctiles',np.percentile(yl,[0,1,5,50,95,99,100]))
# monolingual baseline unavailable; R acc by gui shown above
