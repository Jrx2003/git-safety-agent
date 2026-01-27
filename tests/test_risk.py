from gsa.safety.risk import assess_risk


def test_risk_high_for_delete_branch():
    level, _ = assess_risk("git_delete_branch", {"force": False})
    assert level == "high"


def test_risk_high_for_file_write():
    level, _ = assess_risk("file_write", {"path": "a.txt"})
    assert level == "high"
