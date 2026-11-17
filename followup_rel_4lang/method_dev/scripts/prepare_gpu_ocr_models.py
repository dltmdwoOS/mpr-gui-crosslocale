"""Download only checksum-pinned PP-OCRv5 Paddle weights, reusing the personal cache."""
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent


def main():
    cfg = json.loads((ROOT / 'configs/gpu_ocr_screen_v1.json').read_text())['backends']['ppocrv5_cuda']
    folder = Path(cfg['model_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    downloads = []
    for name, spec in cfg['models'].items():
        downloads.extend((folder / name / filename, spec['url'] + '/' + filename, sha)
                         for filename, sha in spec['files'].items())
        if 'dictionary_url' in spec:
            downloads.append((folder / Path(spec['dictionary_url']).name,
                              spec['dictionary_url'], spec['dictionary_sha256']))
    for path, url, sha in downloads:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise ValueError('Existing model checksum differs: ' + str(path))
            print('CACHED ' + str(path.relative_to(folder)), flush=True)
            continue
        temp = path.with_suffix('.download')
        print('DOWNLOAD ' + str(path.relative_to(folder)), flush=True)
        with requests.get(url, stream=True, timeout=(20, 90)) as response:
            response.raise_for_status()
            with temp.open('wb') as f:
                for chunk in response.iter_content(1024 * 1024):
                    f.write(chunk)
        if hashlib.sha256(temp.read_bytes()).hexdigest() != sha:
            raise ValueError('Downloaded model checksum differs: ' + str(path))
        temp.replace(path)
    print('PP-OCRv5 multilingual Paddle weights verified.', flush=True)


if __name__ == '__main__':
    main()
