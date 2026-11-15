import json, unicodedata, re, csv, statistics as st, collections as C, os
B=os.path.dirname(os.path.abspath(__file__))+'/..'
EXCL={'rel::5/forest_9.jpg::zh::ru'}
spans=[json.loads(l) for l in open(B+'/work/T_gemma_first_spans.jsonl')]
spans=[s for s in spans if s['split']=='main']
cond={}
for l in open(B+'/addon/followup_rel_4lang/expA/expA_inputs/T_conditions.jsonl'):
    r=json.loads(l)
    if r['split']=='main': cond[r['pair_id']]=r

def norm(s):
    s=unicodedata.normalize('NFKC',s or '').casefold()
    return ''.join(c for c in s if not c.isspace() and not unicodedata.category(c).startswith('P'))
def nows(s): return ''.join((s or '').split())
def script(c):
    if not c.isalpha(): return None
    n=unicodedata.name(c,'')
    for k,v in (('CJK','CJK'),('HIRAGANA','CJK'),('KATAKANA','CJK'),('HANGUL','HANGUL'),('THAI','THAI'),('CYRILLIC','CYRILLIC'),('LATIN','LATIN')):
        if n.startswith(k) or (' '+k) in n[:25]: return v
    return 'OTHER'
def scripts(s): return {script(c) for c in s if script(c)}
QS={'en':'LATIN','zh':'CJK','th':'THAI','ru':'CYRILLIC'}
def foreign(s,q): return bool(scripts(s)-{QS[q]})
def ngr(s,n): return C.Counter(s[i:i+n] for i in range(len(s)-n+1))
def chrf(h,r,N=6,beta=2):
    h,r=nows(h),nows(r)
    if not h or not r: return 0.0
    P=[];R=[]
    for n in range(1,N+1):
        a,b=ngr(h,n),ngr(r,n)
        if not a or not b: continue
        ov=sum((a&b).values()); P.append(ov/sum(a.values())); R.append(ov/sum(b.values()))
    if not P: return 0.0
    p,r_=sum(P)/len(P),sum(R)/len(R)
    return 0.0 if p+r_==0 else 100*(1+beta**2)*p*r_/(beta**2*p+r_)
def lcs(a,b):
    a,b=nows(a),nows(b); best=0; prev=[0]*(len(b)+1)
    for i in range(1,len(a)+1):
        cur=[0]*(len(b)+1)
        for j in range(1,len(b)+1):
            if a[i-1]==b[j-1]:
                cur[j]=prev[j-1]+1; best=max(best,cur[j])
        prev=cur
    return best/max(len(nows(a)),len(nows(b)),1)
def mean(x): return sum(x)/len(x) if x else float('nan')
def med(x): return st.median(x) if x else float('nan')

P=C.defaultdict(list)
for s in spans: P[s['pair_id']].append(s)
rows=[]; empt=0; dropped_sub=C.Counter()
for pid,L in P.items():
    if pid in EXCL: continue
    q,g=L[0]['query_language'],L[0]['gui_language']
    n=len(L); f=lambda c:sum(c)/n
    Oe=[s['source_text']==s['screen_text'] for s in L]
    Te=[s['translation']==s['screen_text'] for s in L]
    On=[norm(s['source_text'])==norm(s['screen_text']) for s in L]
    Tn=[norm(s['translation'])==norm(s['screen_text']) for s in L]
    lost=sum(o and not t for o,t in zip(Oe,Te)); gained=sum(t and not o for o,t in zip(Oe,Te))
    def sub(a,b): # a contained in b, strictly, whitespace-removed
        a,b=nows(a),nows(b); return bool(a) and a!=b and a in b
    Tsub=[sub(s['translation'],s['screen_text']) for s in L]; Tsup=[sub(s['screen_text'],s['translation']) for s in L]
    Osub=[sub(s['source_text'],s['screen_text']) for s in L]; Osup=[sub(s['screen_text'],s['source_text']) for s in L]
    Of=[foreign(s['source_text'],q) for s in L]; Tf=[foreign(s['translation'],q) for s in L]
    c=cond[pid]; qt=c['question']; Tq=foreign(qt,q)
    stem=[s for s in L if s['field']=='question_stem']; opt=[s for s in L if s['field']!='question_stem']
    def fr(sub_,key): return sum(s[key]==s['screen_text'] for s in sub_)/len(sub_) if sub_ else ''
    rows.append(dict(pair_id=pid,parallel_id=L[0]['parallel_id'],query_language=q,gui_language=g,cell=q+'>'+g,
      n_spans=n,n_stem=len(stem),n_opt=len(opt),
      O_exact_frac=f(Oe),O_norm_frac=f(On),T_exact_frac=f(Te),T_norm_frac=f(Tn),
      delta_exact_T_minus_O=f(Te)-f(Oe),delta_norm_T_minus_O=f(Tn)-f(On),
      n_lost_exact=lost,n_gained_exact=gained,any_lost=int(lost>0),any_gained=int(gained>0),
      chrF_O=mean([chrf(s['source_text'],s['screen_text']) for s in L]),chrF_T=mean([chrf(s['translation'],s['screen_text']) for s in L]),
      lcs_O=mean([lcs(s['source_text'],s['screen_text']) for s in L]),lcs_T=mean([lcs(s['translation'],s['screen_text']) for s in L]),
      mixed_O_span=int(any(Of)),mixed_T_span=int(any(Tf)),mixed_T_questiontext=int(Tq),n_foreign_O=sum(Of),n_foreign_T=sum(Tf),
      T_sub_of_screen=sum(Tsub),T_super_of_screen=sum(Tsup),O_sub_of_screen=sum(Osub),O_super_of_screen=sum(Osup),
      stem_O_exact=fr(stem,'source_text'),stem_T_exact=fr(stem,'translation'),
      opt_O_exact=fr(opt,'source_text'),opt_T_exact=fr(opt,'translation'),
      n_untranslated=sum(bool(s['untranslated']) for s in L),
      n_empty_span=sum((not s['source_text'].strip()) or (not s['translation'].strip()) or (not s['screen_text'].strip()) for s in L)))
cols=list(rows[0].keys())
with open(B+'/diagnostics_inputs_20261114/per_pair_features.csv','w',newline='') as fh:
    w=csv.DictWriter(fh,cols); w.writeheader(); w.writerows(rows)

def summ(R,key):
    sp=[x for x in R]; N=len(R); S=sum(x['n_spans'] for x in R)
    ssum=lambda k:sum(x[k] for x in R)
    d=dict(group=key,n_pairs=N,n_spans=S,
      O_exact_span_frac=ssum('O_exact_frac') and sum(x['O_exact_frac']*x['n_spans'] for x in R)/S,
      O_norm_span_frac=sum(x['O_norm_frac']*x['n_spans'] for x in R)/S,
      T_exact_span_frac=sum(x['T_exact_frac']*x['n_spans'] for x in R)/S,
      T_norm_span_frac=sum(x['T_norm_frac']*x['n_spans'] for x in R)/S,
      mean_pair_delta_exact=mean([x['delta_exact_T_minus_O'] for x in R]),
      spans_lost_exact=ssum('n_lost_exact'),spans_gained_exact=ssum('n_gained_exact'),
      pairs_any_lost=ssum('any_lost'),pairs_any_gained=ssum('any_gained'),
      chrF_O_mean=mean([x['chrF_O'] for x in R]),chrF_O_median=med([x['chrF_O'] for x in R]),
      chrF_T_mean=mean([x['chrF_T'] for x in R]),chrF_T_median=med([x['chrF_T'] for x in R]),
      lcs_O_mean=mean([x['lcs_O'] for x in R]),lcs_O_median=med([x['lcs_O'] for x in R]),
      lcs_T_mean=mean([x['lcs_T'] for x in R]),lcs_T_median=med([x['lcs_T'] for x in R]),
      mixed_O_span_rate=mean([x['mixed_O_span'] for x in R]),mixed_T_span_rate=mean([x['mixed_T_span'] for x in R]),
      mixed_T_questiontext_rate=mean([x['mixed_T_questiontext'] for x in R]),
      T_sub_span_frac=ssum('T_sub_of_screen')/S,T_super_span_frac=ssum('T_super_of_screen')/S,
      O_sub_span_frac=ssum('O_sub_of_screen')/S,O_super_span_frac=ssum('O_super_of_screen')/S,
      n_stem_spans=ssum('n_stem'),n_opt_spans=ssum('n_opt'),
      stem_O_exact=sum(x['stem_O_exact']*x['n_stem'] for x in R if x['n_stem'])/ssum('n_stem'),
      stem_T_exact=sum(x['stem_T_exact']*x['n_stem'] for x in R if x['n_stem'])/ssum('n_stem'),
      opt_O_exact=sum(x['opt_O_exact']*x['n_opt'] for x in R if x['n_opt'])/ssum('n_opt'),
      opt_T_exact=sum(x['opt_T_exact']*x['n_opt'] for x in R if x['n_opt'])/ssum('n_opt'))
    return d
def wr(name,key):
    G=C.defaultdict(list)
    for r in rows: G[r[key]].append(r)
    out=[summ(G[k],k) for k in sorted(G)]
    with open(B+'/diagnostics_inputs_20261114/'+name,'w',newline='') as fh:
        w=csv.DictWriter(fh,list(out[0].keys())); w.writeheader()
        for o in out: w.writerow({k:(round(v,4) if isinstance(v,float) else v) for k,v in o.items()})
    return out
g=wr('summary_by_gui.csv','gui_language'); c=wr('summary_by_cell.csv','cell')
# extras printed
print('pairs',len(rows),'spans',sum(r['n_spans'] for r in rows),'empty',sum(r['n_empty_span'] for r in rows),'untranslated',sum(r['n_untranslated'] for r in rows))
for o in g+[summ(rows,'ALL')]: print({k:(round(v,3) if isinstance(v,float) else v) for k,v in o.items()})
for o in c: print(o['group'],o['n_pairs'],round(o['O_exact_span_frac'],3),round(o['T_exact_span_frac'],3),o['pairs_any_lost'],round(o['mixed_O_span_rate'],2),round(o['mixed_T_span_rate'],2),round(o['mixed_T_questiontext_rate'],2))
# data checks
bad=sum(1 for s in spans if s['pair_id'] not in EXCL and s['translation'] not in cond[s['pair_id']]['question'])
print('T translation not literally in T question:',bad)
print('match-field vs recomputed disagreements:',sum(1 for s in spans if (s['match']=='exact')!=(s['translation']==s['screen_text'])), sum(1 for s in spans if (s['match']in('exact','normalized'))!=(norm(s['translation'])==norm(s['screen_text']))))
print('source_equals_screen disagreements:',sum(1 for s in spans if s['source_equals_screen']!=(s['source_text']==s['screen_text'])))
print('ref_id dup spans:',sum(v>1 for v in C.Counter((s['pair_id'],s['ref_id']) for s in spans).values()))
