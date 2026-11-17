"""Screenshot-only CUDA OCR adapters. No MCQ/reference/answer file access."""
import hashlib
from importlib import metadata
from pathlib import Path

from .ocr_inventory import reader_factory, transcribe


def weights(config):
    folder = Path(config['model_dir'])
    if config['engine'] == 'easyocr':
        names = ['craft_mlt_25k.pth', 'english_g2.pth', 'zh_sim_g2.pth',
                 'thai.pth', 'cyrillic_g2.pth']
        return {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in names}
    result = {}
    for name, spec in config['models'].items():
        for filename, expected in spec['files'].items():
            relative = name + '/' + filename
            sha = hashlib.sha256((folder / relative).read_bytes()).hexdigest()
            if sha != expected:
                raise ValueError('PP-OCRv5 model checksum differs: ' + relative)
            result[relative] = sha
        if 'dictionary_url' in spec:
            filename = Path(spec['dictionary_url']).name
            sha = hashlib.sha256((folder / filename).read_bytes()).hexdigest()
            if sha != spec['dictionary_sha256']:
                raise ValueError('PP-OCRv5 dictionary checksum differs: ' + filename)
            result[filename] = sha
    return result


def require_paddle_cuda(compiled_with_cuda, device):
    if not compiled_with_cuda or device != 'gpu:0':
        raise RuntimeError('Paddle CUDA unavailable; refusing CPU-only OCR')


def rapid_detections(output):
    boxes, texts, scores = output.boxes, output.txts, output.scores
    if boxes is None and texts is None and scores is None:
        return []
    if boxes is None or texts is None or scores is None or not len(boxes) == len(texts) == len(scores):
        raise ValueError('Incomplete PP-OCRv5 detection/recognition output')
    return list(zip(boxes, texts, scores))


class CudaReader:
    def __init__(self, language, config, *, profile_dir=None):
        import torch
        import cv2
        cv2.setNumThreads(3)
        torch.set_num_threads(3)
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; refusing CPU-only OCR')
        if config['device'] != 'cuda:0' or metadata.version(config['engine']) != config['package_version']:
            raise ValueError('Unexpected OCR version/device')
        self.engine_name = config['engine']
        self.engine = None
        self.profiler = None
        self.provenance = {'device': config['device'], 'package_version': config['package_version']}
        self.peak_allocated_bytes = None
        if config['engine'] == 'easyocr':
            self.engine = reader_factory(language, {**config, 'threads': 3}, config['model_dir'])
            for name in ('detector', 'recognizer'):
                if next(getattr(self.engine, name).parameters()).device.type != 'cuda':
                    raise RuntimeError('EasyOCR component is not on CUDA: ' + name)
            self.readtext = config['readtext']
            self.provenance['component_devices'] = {'detector': 'cuda:0', 'recognizer': 'cuda:0'}
        else:
            # Reuse CUDA/cuDNN already loaded by PyTorch; PP workers are isolated
            # from all LM/VLM workers and never load a transformer checkpoint.
            import paddle
            if paddle.__version__ != config['paddle_version']:
                raise ValueError('Unexpected Paddle version')
            paddle.set_device('gpu:0')
            require_paddle_cuda(paddle.is_compiled_with_cuda(), paddle.get_device())
            from rapidocr import RapidOCR
            from rapidocr.utils.typings import ModelType, OCRVersion, LangRec, LangDet, EngineType
            rec = config['models'][config['recognizers'][language]]
            params = {**config['params'], 'Global.model_root_dir': config['model_dir'],
                      'Det.model_dir': str(Path(config['model_dir']) / config['detector']),
                      'Rec.lang_type': config['language_codes'][language],
                      'Rec.model_dir': str(Path(config['model_dir']) / config['recognizers'][language]),
                      'Rec.rec_keys_path': str(Path(config['model_dir']) / Path(rec['dictionary_url']).name)}
            for key in ('Det.ocr_version', 'Rec.ocr_version'):
                params[key] = OCRVersion(params[key])
            for key in ('Det.model_type', 'Rec.model_type'):
                params[key] = ModelType(params[key])
            params['Det.lang_type'] = LangDet(params['Det.lang_type'])
            params['Rec.lang_type'] = LangRec(params['Rec.lang_type'])
            for key in ('Det.engine_type', 'Rec.engine_type'):
                params[key] = EngineType(params[key])
            from rapidocr.inference_engine.paddle.main import PaddleInferSession
            original_predictor = PaddleInferSession.init_predictor
            checked_components = []
            def checked_predictor(session, options, version):
                if not options.use_gpu():
                    raise RuntimeError('Paddle predictor is CPU-only')
                checked_components.append(True)
                return original_predictor(session, options, version)
            PaddleInferSession.init_predictor = checked_predictor
            try:
                self.engine = RapidOCR(params=params)
                self.engine._load_det_model()
                self.engine._load_rec_model()
            finally:
                PaddleInferSession.init_predictor = original_predictor
            if len(checked_components) != 2:
                raise RuntimeError('Paddle GPU component verification incomplete')
            self.provenance.update(paddle_version=paddle.__version__, paddle_device=paddle.get_device(),
                                   detector_gpu=True, recognizer_gpu=True)
            if profile_dir is not None:
                from paddle.profiler import Profiler, ProfilerTarget, export_chrome_tracing
                folder = Path(profile_dir) / language
                folder.mkdir()
                self.profile_dir = folder
                self.profiler = Profiler(targets=[ProfilerTarget.CPU, ProfilerTarget.GPU],
                                         on_trace_ready=export_chrome_tracing(str(folder)))

    def __call__(self, image_path):
        import torch
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        if self.profiler:
            self.profiler.start()
        if self.engine_name == 'easyocr':
            output = self.engine.readtext(image_path, **self.readtext)
        else:
            output = rapid_detections(self.engine(image_path))
        torch.cuda.synchronize()
        if self.profiler:
            self.profiler.stop()
        self.peak_allocated_bytes = torch.cuda.max_memory_allocated()
        return output

    def inventory(self, image_path):
        result = transcribe(self, str(image_path))
        return {**result, 'gpu_provenance': self.provenance,
                'torch_peak_allocated_bytes': self.peak_allocated_bytes,
                'memory_note': 'Torch statistic excludes Paddle allocations.'}

    def finish_profiles(self):
        return [str(p) for p in self.profile_dir.glob('*.json')] if self.profiler else []
