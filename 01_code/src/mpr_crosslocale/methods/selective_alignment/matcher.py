"""Conservative retrieval. Similarity is a rank score, not a calibrated probability."""
from .inventory import normalize


def match(ref, translation, entries, threshold, margin, scorer=None):
    if ref['kind']=='icon':return {'span_id':ref['span_id'],'decision':'abstain','reason':'nontext_icon','candidates':[]}
    candidates=[]
    for e in entries:
        exact=normalize(translation)==normalize(e['text'])
        score=1.0 if exact else float(scorer(translation,e['text'])) if scorer else 0.0
        candidates.append({'text':e['text'],'score':score,'normalized_exact':exact})
    candidates.sort(key=lambda x:(-x['score'],x['text']))
    result={'span_id':ref['span_id'],'candidates':candidates[:5],'decision':'abstain'}
    if not candidates:return {**result,'reason':'inventory_empty_or_failed'}
    top=candidates[0];gap=top['score']-(candidates[1]['score'] if len(candidates)>1 else 0)
    if top['score']<threshold:return {**result,'reason':'low_similarity_or_missing_evidence'}
    if len(candidates)>1 and gap<margin:return {**result,'reason':'ambiguous_candidates'}
    return {**result,'decision':'match','reason':'normalized_exact' if top['normalized_exact'] else 'semantic_retrieval',
            'replacement':top['text'],'score_margin':gap}


class LabseScorer:
    def __init__(self, model_path):
        from sentence_transformers import SentenceTransformer
        self.model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True)
        self.cache={}
    def __call__(self,a,b):
        for text in (a,b):
            if text not in self.cache:self.cache[text]=self.model.encode(text,normalize_embeddings=True)
        return self.cache[a] @ self.cache[b]
