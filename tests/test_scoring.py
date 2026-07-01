import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from viral_core.scoring import outlier_score


def test_outlier_score_basic():
    assert outlier_score(500, 100) == 5.0

def test_outlier_score_rounds_to_two_decimals():
    assert outlier_score(100, 3) == 33.33

def test_outlier_score_zero_median_is_zero():
    assert outlier_score(500, 0) == 0.0

def test_outlier_score_reexported_from_package():
    from viral_core import outlier_score as top_level
    assert top_level(500, 100) == 5.0

def test_calculate_outlier_score_alias_still_importable():
    from scripts.rank_and_select import calculate_outlier_score
    assert calculate_outlier_score(500, 100) == 5.0
