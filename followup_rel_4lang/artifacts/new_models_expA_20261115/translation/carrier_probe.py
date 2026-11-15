"""Probe: translate spans inside a short UI carrier phrase, then extract the quoted part."""
import json,re,sys
from pathlib import Path
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from huggingface_hub import snapshot_download
CODES={"en":"eng_Latn","zh":"zho_Hans","th":"tha_Thai","ru":"rus_Cyrl"}
CARRIER={"en":'The on-screen label "{}"',"zh":'屏幕上的标签“{}”',"th":'ป้ายบนหน้าจอ "{}"',"ru":'Надпись на экране «{}»'}
Q=re.compile(r'["“«「『]([^"”»」』]+)["”»」』]')
p=snapshot_download("facebook/nllb-200-distilled-1.3B",revision="7be3e24664b38ce1cac29b8aeed6911aa0cf0576")
tok=AutoTokenizer.from_pretrained(p); m=AutoModelForSeq2SeqLM.from_pretrained(p).eval()
rows=[json.loads(l) for l in open("work/smoke_nllb.jsonl")]
out=open("work/smoke_carrier.jsonl","w")
for r in rows:
    tok.src_lang=CODES[r["src_lang"]]
    enc=tok([CARRIER[r["src_lang"]].format(r["text"])],return_tensors="pt")
    with torch.no_grad(): g=m.generate(**enc,forced_bos_token_id=tok.convert_tokens_to_ids(CODES[r["tgt_lang"]]),num_beams=4,do_sample=False,max_new_tokens=64)
    full=tok.decode(g[0],skip_special_tokens=True); mm=Q.search(full)
    out.write(json.dumps({**r,"carrier_full":full,"carrier_span":mm.group(1).strip() if mm else None},ensure_ascii=False)+"\n")
