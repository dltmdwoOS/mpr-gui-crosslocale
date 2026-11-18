from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import finalize_gpu_ocr_remaining as completion
from mpr_crosslocale.methods.selective_alignment.schemas import digest


@pytest.mark.parametrize('change', ['question', 'image', 'gold'])
def test_completed_queue_cannot_be_rebound_to_different_inputs(change):
    row = {'pair_id': 'p', 'parallel_id': 'item', 'image_path': 'image.png', 'modified_question': 'Which?'}
    predictions = {'p': {'rendered_prompt': 'rendered Which?'}}
    labels = {'p': {'gold_answer': 'A'}}
    expected = digest([{'pair_id': 'p', 'parallel_id': 'item',
                        'image_paths': [str(completion.REPO / 'image.png')], 'question_raw': 'Which?',
                        'gold_label': 'A', 'rendered_prompt': 'rendered Which?'}])
    completion.check_queue([row], predictions, labels, expected)
    if change == 'question':
        row['modified_question'] = 'Changed?'
    elif change == 'image':
        row['image_path'] = 'other.png'
    else:
        labels['p']['gold_answer'] = 'B'
    with pytest.raises(ValueError, match='queue differs'):
        completion.check_queue([row], predictions, labels, expected)
