"""Download only the pinned transfer VLM into the personal Hugging Face cache."""
import argparse
import json
import os
from pathlib import Path
import shutil


def main():
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=root/'configs/transfer_qwen3_vl_4b_e1m0.json')
    p.add_argument('--download', action='store_true', help='Explicitly fetch checkpoint files; default only checks the local cache')
    a = p.parse_args()
    personal = Path('/home/jovyan/seungjae')
    os.environ.setdefault('XDG_CACHE_HOME', str(personal/'.cache'))
    os.environ.setdefault('HF_HOME', str(personal/'.cache/huggingface'))
    os.environ.setdefault('TORCH_HOME', str(personal/'.cache/torch'))
    os.environ.setdefault('PIP_CACHE_DIR', str(personal/'.cache/pip'))
    spec = json.loads(a.config.read_text())['vlm']
    if len(spec['revision']) != 40 or spec['family'] != 'qwen3_vl':
        raise ValueError('Pinned Qwen3-VL revision required')
    cache = Path(os.environ['HF_HOME']).resolve()/'hub'
    if not cache.is_relative_to(personal):
        raise ValueError('HF cache must remain in the personal workspace')
    if a.download:
        os.environ['HF_HUB_OFFLINE'] = '0'
        os.environ['TRANSFORMERS_OFFLINE'] = '0'
    from huggingface_hub import snapshot_download
    kwargs = dict(repo_id=spec['model_id'], revision=spec['revision'], cache_dir=str(cache),
                  allow_patterns=['*.json', '*.safetensors', '*.jinja', '*.txt', '*.model'], max_workers=3)
    try:
        existing = Path(snapshot_download(**kwargs, local_files_only=True))
        index = existing/'model.safetensors.index.json'
        complete = index.exists() and all((existing/n).exists() for n in set(json.loads(index.read_text())['weight_map'].values()))
    except FileNotFoundError:
        existing, complete = None, False
    if not complete and a.download:
        # A shared filesystem's free space is only an instantaneous check, not a personal quota.
        free = shutil.disk_usage(personal).free
        if free < 12*2**30:
            raise RuntimeError('Less than 12GiB filesystem free; stop before model download')
        existing = Path(snapshot_download(**kwargs, local_files_only=False))
        index = existing/'model.safetensors.index.json'
        complete = index.exists() and all((existing/n).exists() for n in set(json.loads(index.read_text())['weight_map'].values()))
    print(json.dumps({'model_id': spec['model_id'], 'revision': spec['revision'], 'snapshot': str(existing) if existing else None,
                      'weights_present': complete, 'download_requested': a.download}, ensure_ascii=False, indent=2))
    if a.download and not complete:
        raise RuntimeError('Pinned download incomplete')


if __name__ == '__main__':
    main()
