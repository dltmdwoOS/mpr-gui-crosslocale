import json
import unittest
from copy import deepcopy
from followup_rel_4lang.method_dev import editor_matrix as m
from mpr_crosslocale.methods.selective_alignment.schemas import fields


def row():
    return {'pair_id': 'test', 'parallel_id': 'test', 'source_language': 'en', 'gui_language': 'zh',
            'image_path': 'unused.png', 'image_sha256': 'unused', 'question_stem': 'What is below Settings beside Search?',
            'options': dict(zip('ABCD', ['Alpha', 'Beta', 'Gamma', 'Delta'])), 'option_order': list('ABCD')}


class Backend:
    def __init__(self, *responses):
        self.responses, self.inputs = iter(responses), []
    def __call__(self, stage, role, system, user):
        self.inputs.append(user)
        return {'raw_output': json.dumps(next(self.responses), ensure_ascii=False),
                'runtime_ms': 0, 'stage': stage, 'cache_hit': False}


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.row, self.inv = row(), {'status': 'success', 'visible_strings': ['设置', '搜索']}

    def test_multiple_unicode_edits_preserve_context_and_options(self):
        out, edits, _ = m.validate_joint(self.row, self.inv, [{'text': 'Search', 'replacement': '搜索'}, {'text': 'Settings', 'replacement': '设置'}])
        self.assertEqual(out['question_stem'], 'What is below 设置 beside 搜索?')
        self.assertEqual([out[k] for k in 'ABCD'], list(self.row['options'].values()))
        self.assertEqual(len({e['span_id'] for e in edits}), 2)

    def test_ambiguous_no_occurrence_abstains(self):
        self.row['question_stem'] = 'Settings near Settings'
        out, edits, abstain = m.validate_joint(self.row, self.inv, [{'text': 'Settings', 'replacement': '设置'}])
        self.assertEqual(out, fields(self.row)); self.assertFalse(edits); self.assertEqual(len(abstain), 1)

    def test_explicit_occurrence(self):
        self.row['question_stem'] = 'Settings near Settings'
        out, _, _ = m.validate_joint(self.row, self.inv, [{'text': 'Settings', 'replacement': '设置', 'occurrence': 1}])
        self.assertEqual(out['question_stem'], 'Settings near 设置')

    def test_overlapping_edits_rejected(self):
        self.inv['visible_strings'].append('X')
        with self.assertRaises(ValueError):
            m.validate_joint(self.row, self.inv, [{'text': 'Settings', 'replacement': '设置'}, {'text': 'Settings beside', 'replacement': 'X'}])

    def test_target_not_inventory_and_source_translated_rejected(self):
        for edit in ({'text': 'Settings', 'replacement': '不存在'}, {'text': '设置', 'replacement': '设置'}):
            with self.assertRaises(ValueError): m.validate_joint(self.row, self.inv, [edit])

    def test_new_duplicate_options_rejected(self):
        with self.assertRaises(ValueError): m.validate_options(self.row, dict(zip('ABCD', ['x', 'x', 'y', 'z'])))

    def test_hybrid_preserves_valid_stem_during_options_repair(self):
        backend = Backend({'stem_edits': [{'text': 'Settings', 'replacement': '设置'}], 'options': {'A': 'x'}},
                          {'options': dict(zip('ABCD', ['甲', '乙', '丙', '丁']))})
        result = m.rewrite(self.row, self.inv, None, backend, 'J', 'H')
        self.assertEqual(result['output']['question_stem'], 'What is below 设置 beside Search?')
        self.assertEqual(result['output']['A'], '甲')
        self.assertEqual(result['attempts'][1]['requested_components'], ['options'])

    def test_hybrid_preserves_options_when_stem_never_valid(self):
        opts = dict(zip('ABCD', ['甲', '乙', '丙', '丁']))
        backend = Backend({'stem_edits': [{'text': 'absent', 'replacement': '设置'}], 'options': opts},
                          {'stem_edits': [{'text': 'absent', 'replacement': '设置'}]})
        result = m.rewrite(self.row, self.inv, None, backend, 'J', 'H')
        self.assertEqual(result['status'], 'partial_fallback')
        self.assertEqual(result['output']['question_stem'], self.row['question_stem'])
        self.assertEqual(result['output']['A'], '甲')

    def test_failed_d_extraction_keeps_stem_but_translates_options(self):
        backend = Backend({'translations': {}, 'options': dict(zip('ABCD', ['甲', '乙', '丙', '丁']))})
        result = m.rewrite(self.row, self.inv, None, backend, 'D', 'H')
        self.assertEqual(result['component_status']['stem'], 'fallback_original')
        self.assertEqual(result['output']['A'], '甲')

    def test_gold_rejected_and_no_io_api(self):
        with self.assertRaises(ValueError): m.payload({**self.row, 'gold_answer': 'A'}, self.inv, None, 'J', 'S')
        self.assertNotIn('image_path', m.payload(self.row, self.inv, None, 'J', 'S'))

    def test_relation_only_not_allowed(self):
        with self.assertRaises(ValueError):
            m.validate_joint(self.row, self.inv, [{'text': 'below', 'replacement': '设置'}])

    def test_s_keeps_options(self):
        result = m.rewrite(self.row, self.inv, None, Backend({'stem_edits': []}), 'J', 'S')
        self.assertEqual(result['output'], fields(self.row))


if __name__ == '__main__':
    unittest.main()
