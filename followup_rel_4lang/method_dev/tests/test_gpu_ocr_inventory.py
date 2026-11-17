from types import SimpleNamespace
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from followup_rel_4lang.method_dev.gpu_ocr_inventory import rapid_detections, require_paddle_cuda
from followup_rel_4lang.method_dev.ocr_inventory import transcribe
from run_gpu_ocr_screen import image_queue
from report_gpu_ocr_screen import cost_for, scores
from finalize_gpu_ocr_screen import checked_contrast


def test_registered_cpu_only_provider_is_rejected():
    with pytest.raises(RuntimeError, match='CPU-only'):
        require_paddle_cuda(False, 'cpu')
    with pytest.raises(RuntimeError, match='CPU-only'):
        require_paddle_cuda(True, 'cpu')
    require_paddle_cuda(True, 'gpu:0')


def test_partial_recognition_is_failure_instead_of_empty_success():
    bad = SimpleNamespace(boxes=[[[0, 0], [10, 0], [10, 10], [0, 10]]], txts=None, scores=None)
    result = transcribe(lambda _: rapid_detections(bad), 'image')
    assert result['status'] == 'failed'
    empty = SimpleNamespace(boxes=None, txts=None, scores=None)
    assert rapid_detections(empty) == []


def test_rapid_output_preserves_confidence_and_uses_same_normalization():
    box = [[0, 0], [10, 0], [10, 10], [0, 10]]
    output = SimpleNamespace(boxes=[box, box, box], txts=['ＡＢＣ', 'abc', 'ตั้งค่า'], scores=[0.01, 0.99, 0.8])
    result = transcribe(lambda _: rapid_detections(output), 'image')
    assert result['visible_strings'] == ['ABC', 'ตั้งค่า']
    assert result['original_strings'] == output.txts
    assert result['detections'][0]['confidence'] == 0.01


def test_known_language_is_the_only_language_selection_input():
    rows = [{'image_sha256': g + str(i), 'gui_language': g} for g in ('en', 'zh', 'th', 'ru') for i in range(2)]
    assert len(image_queue(rows + rows)) == 8
    assert [r['gui_language'] for r in image_queue(rows, smoke=True)] == ['en', 'zh', 'th', 'ru']
    with pytest.raises(ValueError, match='Incompatible'):
        image_queue([rows[0], {**rows[0], 'gui_language': 'ru'}])


def test_model_configuration_uses_actual_thai_and_russian_v5_recognizers():
    c = json.loads((ROOT / 'configs/gpu_ocr_screen_v1.json').read_text())['backends']['ppocrv5_cuda']
    assert c['recognizers']['th'] == 'th_PP-OCRv5_rec_mobile'
    assert c['recognizers']['ru'] == 'eslav_PP-OCRv5_rec_mobile'
    assert c['params']['Global.text_score'] == 0
    assert c['params']['Global.use_cls'] is False
    assert set(c['recognizers'].values()) | {c['detector']} == set(c['models'])
    assert c['runtime'] == 'paddle'
    assert all(all(len(sha) == 64 for sha in x['files'].values()) and '/v3.10.0/' in x['url'] for x in c['models'].values())


def test_recipe_cost_charges_shared_preprocessing_once_per_solver_recipe():
    c = cost_for(80, 20, 40, 100)
    assert c['total_seconds'] == 240 and c['seconds_per_pair'] == 1


def test_accuracy_includes_failed_and_invalid_predictions():
    predictions = [{'pair_id': 'p', 'execution_mode': 'gpu', 'generated_text': 'A',
                    'parsed_generated_label': 'A', 'status': 'failed'}]
    assert scores(predictions, {'p'}, {'p': {'gold_answer': 'A'}}) == {'p': 0}
    predictions[0]['execution_mode'] = 'mock'
    with pytest.raises(ValueError, match='provenance'):
        scores(predictions, {'p'}, {'p': {'gold_answer': 'A'}})


@pytest.mark.parametrize('stored', [
    {'recovery': 0, 'regression': 1, 'difference': -0.5},
    {'recovery': 1, 'regression': 0, 'difference': 0},
])
def test_paired_audit_rejects_inverted_transitions_or_wrong_denominator(stored):
    left, right = {'p': 1, 'q': 1}, {'p': 0, 'q': 1}
    checked_contrast(left, right, {'recovery': 1, 'regression': 0, 'difference': 0.5})
    with pytest.raises(ValueError):
        checked_contrast(left, right, stored)
