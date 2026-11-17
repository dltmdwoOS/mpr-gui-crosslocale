"""Screenshot-only OCR adapter. No dataset, MCQ, answer or reference readers."""
import hashlib
import math
from pathlib import Path
import time

from .two_stage_v2.legacy import canonicalize_visible_strings


def serialize_detections(detections):
    """Keep raw box/text/confidence; never threshold or repair recognized text."""
    output = []
    for box, text, confidence in detections:
        coords = [[float(x), float(y)] for x, y in box]
        score = float(confidence)
        if len(coords) != 4 or not all(math.isfinite(v) for point in coords for v in point):
            raise ValueError('Invalid OCR quadrilateral')
        if not isinstance(text, str) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid OCR text/confidence')
        output.append({'bbox': coords, 'text': text, 'confidence': score})
    return output


def transcribe(reader, image_path):
    # The reader wrapper fixes all recognition settings; only image bytes are input.
    started = time.perf_counter()
    try:
        detections = serialize_detections(reader(image_path))
        strings = canonicalize_visible_strings([r['text'] for r in detections])
        return {'status': 'success' if strings else 'empty', 'visible_strings': strings,
                'original_strings': [r['text'] for r in detections], 'detections': detections,
                'errors': [], 'runtime_ms': (time.perf_counter() - started) * 1000,
                'query_content_exposed': False}
    except Exception as exc:
        # Failed images remain in the evaluation; CUDA/resource failures abort the stage.
        if isinstance(exc, (MemoryError,)) or 'out of memory' in str(exc).lower():
            raise
        return {'status': 'failed', 'visible_strings': [], 'original_strings': [],
                'detections': [], 'errors': [type(exc).__name__ + ': ' + str(exc)],
                'runtime_ms': (time.perf_counter() - started) * 1000,
                'query_content_exposed': False}


def reader_factory(language, config, model_dir, *, download=False):
    import easyocr
    import torch
    torch.set_num_threads(config['threads'])
    if config['device'] != 'cpu' and not torch.cuda.is_available():
        raise RuntimeError('Requested GPU OCR but CUDA is unavailable; no silent CPU fallback')
    return easyocr.Reader(config['languages'][language],
                          gpu=False if config['device'] == 'cpu' else config['device'],
                          model_storage_directory=str(model_dir),
                          user_network_directory=str(Path(model_dir).parent / 'user_network'),
                          download_enabled=download, verbose=False, **config['reader'])


def weight_manifest(model_dir):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(model_dir).glob('*.pth'))}
