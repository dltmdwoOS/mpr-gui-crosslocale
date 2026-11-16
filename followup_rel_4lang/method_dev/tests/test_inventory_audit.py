import json
import pytest

from followup_rel_4lang.method_dev.scripts.audit_inventory_usage import user_payload


@pytest.mark.parametrize('prefix',['','<|vision_start|><|image_pad|><|vision_end|>'])
def test_reads_actual_user_json_including_inventory_with_chat_tokens_inside_strings(prefix):
    payload={'fields':{'A':'a label containing <|im_end|>'},'untrusted_unordered_visible_strings':['Search']}
    rendered='<|im_start|>system\nInventory mentioned here is not the input.\n<|im_end|>\n<|im_start|>user\n'+prefix+json.dumps(payload)+'<|im_end|>\n<|im_start|>assistant\n'
    assert user_payload({'rendered_prompt':rendered})==payload


def test_a_system_mention_does_not_fabricate_inventory_exposure():
    rendered='<|im_start|>system\nUse inventory.\n<|im_end|>\n<|im_start|>user\n{"referents":[]}<|im_end|>'
    assert 'untrusted_unordered_visible_strings' not in user_payload({'rendered_prompt':rendered})
