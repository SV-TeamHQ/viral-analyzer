"""Outlier-score formula shared across stages.

A post's outlier score is its engagement divided by the account's median
engagement — how many times more viral than the account's typical post.
"""


def outlier_score(post_engagement: int | float, account_median: float) -> float:
    if account_median == 0:
        return 0.0
    return round(post_engagement / account_median, 2)
