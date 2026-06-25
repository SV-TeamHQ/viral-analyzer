import json
import os
import pytest

from scripts.rank_and_select import rank_and_select, calculate_outlier_score


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_sample_posts():
    with open(os.path.join(FIXTURES_DIR, "sample_raw_posts.json")) as f:
        return json.load(f)


class TestCalculateOutlierScore:
    def test_outlier_above_median(self):
        score = calculate_outlier_score(
            post_engagement=5200,
            account_median=1050,
        )
        assert round(score, 1) == 5.0

    def test_outlier_at_median(self):
        score = calculate_outlier_score(
            post_engagement=1000,
            account_median=1000,
        )
        assert score == 1.0

    def test_zero_median_returns_zero(self):
        score = calculate_outlier_score(
            post_engagement=500,
            account_median=0,
        )
        assert score == 0.0


class TestRankAndSelect:
    def test_selects_top_per_handle(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        creator1_posts = [p for p in result if p["handle"] == "creator1"]
        creator2_posts = [p for p in result if p["handle"] == "creator2"]
        assert len(creator1_posts) == 3
        assert len(creator2_posts) == 3

    def test_adds_outlier_score(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        for post in result:
            assert "outlier_score" in post
            assert isinstance(post["outlier_score"], float)

    def test_ranked_by_outlier_score_descending(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        scores = [p["outlier_score"] for p in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_post_is_highest_outlier(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=3)
        assert result[0]["id"] == "A1"

    def test_limits_when_fewer_posts_than_top_per_handle(self):
        posts = load_sample_posts()
        result = rank_and_select(posts, top_per_handle=10)
        creator1_posts = [p for p in result if p["handle"] == "creator1"]
        assert len(creator1_posts) == 4
