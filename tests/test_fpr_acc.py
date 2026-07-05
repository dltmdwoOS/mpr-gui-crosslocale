from mpr_crosslocale.metrics.fpr_acc import fpr_acc


def test_fpr_acc_weighted_average():
    score = fpr_acc({"wf": 1.0, "ri": 0.0, "si": 1.0})
    assert score == (1.0 + 0.0 * 1.5 + 1.0 * 2.0) / 4.5
