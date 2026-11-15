"""Inspect/download the pinned fixed Qwen3-8B LM into a personal HF cache."""
import argparse,hashlib,json,os,shutil
from pathlib import Path
MODEL='Qwen/Qwen3-8B'
REVISION='47719a242beab8f9aecc40ce3928b034dd5dd559'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hf-home',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--download',action='store_true')
    a=p.parse_args()
    from huggingface_hub import HfApi,snapshot_download
    info=HfApi().model_info(MODEL,revision=REVISION,files_metadata=True)
    if info.sha!=REVISION:raise ValueError('Revision mismatch')
    selected=[f for f in info.siblings if f.rfilename.endswith('.safetensors') or f.rfilename in
              ('config.json','generation_config.json','model.safetensors.index.json','tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','special_tokens_map.json','chat_template.jinja')]
    cache=a.hf_home.resolve()/'hub';snapshot=cache/'models--Qwen--Qwen3-8B'/'snapshots'/REVISION
    total=sum(f.size or 0 for f in selected)
    cached=sum(f.size or 0 for f in selected if (snapshot/f.rfilename).is_file() and (snapshot/f.rfilename).stat().st_size==f.size)
    ancestor=cache
    while not ancestor.exists():ancestor=ancestor.parent
    free=shutil.disk_usage(ancestor).free
    print(json.dumps({'model_id':MODEL,'revision':REVISION,'download_bytes':total,'existing_bytes':cached,'missing_bytes':total-cached,'free_bytes':free,'files':[f.rfilename for f in selected]},indent=2),flush=True)
    if not a.download:return
    if free<total-cached+4*2**30:raise RuntimeError('Insufficient free space including 4GiB headroom')
    path=Path(snapshot_download(MODEL,revision=REVISION,cache_dir=cache,max_workers=2,
                               allow_patterns=[f.rfilename for f in selected]))
    files=[]
    for f in selected:
        target=path/f.rfilename
        if target.stat().st_size!=f.size:raise ValueError('File size mismatch: '+f.rfilename)
        sha=hashlib.sha256()
        with target.open('rb') as handle:
            for chunk in iter(lambda:handle.read(4*1024*1024),b''):sha.update(chunk)
        if f.lfs and f.lfs.sha256!=sha.hexdigest():raise ValueError('LFS SHA-256 mismatch: '+f.rfilename)
        files.append({'file':f.rfilename,'bytes':f.size,'sha256':sha.hexdigest(),'lfs_sha256_verified':bool(f.lfs)})
    config=json.loads((path/'config.json').read_text());assert config['model_type']=='qwen3'
    index=json.loads((path/'model.safetensors.index.json').read_text())
    assert all((path/shard).is_file() for shard in set(index['weight_map'].values()))
    result={'model_id':MODEL,'revision':REVISION,'snapshot':str(path),'verified':True,'files':files,'bytes':total}
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.write_text(json.dumps(result,indent=2)+'\n')
    print('Verified snapshot:',path,flush=True)
if __name__=='__main__':main()
