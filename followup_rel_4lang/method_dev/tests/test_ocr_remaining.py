import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_ocr_remaining as runner
from report_ocr_remaining import ocr_seconds
from followup_rel_4lang.method_dev.tests.test_visual_selective_rewrite import fixture


def cohort_rows(count, excluded=False):
    result = []
    for i in range(count):
        item = 'rel::5/forest_9.jpg' if excluded and i == 0 else f'rel::unit_{i}.png'
        for src in ('en', 'zh', 'th', 'ru'):
            for gui in ('en', 'zh', 'th', 'ru'):
                if src == gui:
                    continue
                row = fixture()
                row.update(parallel_id=item, pair_id=item + '::' + src + '::' + gui,
                           source_language=src, gui_language=gui,
                           image_sha256=hashlib.sha256((item + gui).encode()).hexdigest())
                result.append(row)
    return result


def test_selection_preserves_excluded_row_in_execution_and_main_denominator():
    rows = cohort_rows(20, excluded=True)
    assert runner.validate_remaining_rows(rows, 'selection') == {
        'executed_pairs': 240, 'primary_pairs': 239, 'items': 20, 'images': 80}
    with pytest.raises(ValueError):
        runner.validate_remaining_rows([r for r in rows if r['pair_id'] != runner.EXCLUDED], 'selection')


def test_internal_counts_and_duplicate_pair_rejection():
    rows = cohort_rows(118)
    assert runner.validate_remaining_rows(rows, 'internal_evaluation')['primary_pairs'] == 1416
    with pytest.raises(ValueError):
        runner.validate_remaining_rows(rows + [rows[0]], 'internal_evaluation')


def test_method_input_rejects_gold_fields():
    rows = cohort_rows(20, excluded=True)
    rows[0]['gold_answer'] = 'A'
    with pytest.raises(ValueError):
        runner.validate_remaining_rows(rows, 'selection')


def test_shared_cache_links_preserve_original_and_detect_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'REPO', tmp_path)
    source = tmp_path / 'screen'
    source.mkdir()
    key = 'a' * 64
    path = source / (key + '.json')
    path.write_text(json.dumps({'cache_key': key, 'visible_strings': ['ตั้งค่า'], 'runtime_ms': 100}))
    target = tmp_path / 'shared'
    assert runner.cache_links(source, target) == 1
    assert (target / path.name).is_symlink()
    assert runner.cache_links(source, target) == 1
    assert json.loads(path.read_text())['visible_strings'] == ['ตั้งค่า']
    # A conflicting new-run file must never overwrite the Screen record.
    other = tmp_path / 'other'
    other.mkdir()
    (other / path.name).write_text(json.dumps({'cache_key': key, 'visible_strings': ['different']}))
    with pytest.raises(ValueError, match='Conflicting'):
        runner.cache_links(source, other)
    assert json.loads(path.read_text())['visible_strings'] == ['ตั้งค่า']


def test_pooled_ocr_runtime_deduplicates_cached_calls_and_rejects_conflicts():
    record = {'cache_key': 'image1', 'runtime_ms': 1200}
    assert ocr_seconds([record, copy.deepcopy(record)]) == 1.2
    with pytest.raises(ValueError, match='Conflicting'):
        ocr_seconds([record, {**record, 'runtime_ms': 1300}])
