"""Tests for report aggregation (spec §4 anonymity + §8 scoring)."""
from hr.evaluation360.domain.aggregation import build_participant_report


def review(relationship, ratings_by_comp):
    """Build one submitted review. rating None → 'Not observed'."""
    answers = [
        {'competency_id': cid, 'rating': None, 'not_observed': True} if rating is None
        else {'competency_id': cid, 'rating': rating, 'not_observed': False}
        for cid, rating in ratings_by_comp.items()
    ]
    return {'relationship': relationship, 'answers': answers}


def test_peer_category_hidden_below_threshold_fail_closed():
    reviews = [review('self', {1: 5}), review('manager', {1: 4}),
               review('peer', {1: 3}), review('peer', {1: 3})]  # only 2 peers
    rep = build_participant_report(reviews, [1])
    comp = rep['competencies'][0]
    assert comp['categories']['peer']['hidden'] is True
    assert comp['categories']['peer']['score'] is None      # ratings never leak
    assert 'peer' in rep['hidden_relationships']
    # others composite must exclude the hidden peer category → only manager (4)
    assert comp['others'] == 4.0
    assert comp['self'] == 5.0
    assert comp['gap'] == 1.0


def test_peer_category_visible_at_threshold():
    reviews = [review('self', {1: 5}), review('manager', {1: 4})] + [review('peer', {1: 3})] * 3
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['categories']['peer']['hidden'] is False
    assert comp['categories']['peer']['score'] == 3.0
    assert comp['others'] == 3.5   # mean of manager(4) and peer(3)


def test_others_is_mean_of_means_not_pooled():
    # 1 manager @5, 3 peers @2 → mean-of-means = (5+2)/2 = 3.5, NOT pooled (5+2+2+2)/4 = 2.75
    reviews = [review('manager', {1: 5})] + [review('peer', {1: 2})] * 3
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['categories']['manager']['score'] == 5.0
    assert comp['categories']['peer']['score'] == 2.0
    assert comp['others'] == 3.5


def test_manager_attributed_at_n1():
    reviews = [review('self', {1: 4}), review('manager', {1: 2})]
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['categories']['manager']['hidden'] is False   # attributed even at n=1
    assert comp['categories']['manager']['score'] == 2.0


def test_not_observed_excluded_from_category_mean():
    reviews = [review('peer', {1: 4}), review('peer', {1: 4}), review('peer', {1: None})]
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['categories']['peer']['n'] == 3       # 3 reviewers count for anonymity
    assert comp['categories']['peer']['score'] == 4.0  # the not-observed rating dropped


def test_not_observed_category_excluded_from_composite_and_denominator():
    """C1 end-to-end: a visible category whose members all marked 'not observed'
    contributes no score — excluded from the others composite AND its n, while
    still counting as reviewers for the anonymity gate."""
    reviews = [review('self', {1: 5}), review('manager', {1: 4})] + [review('peer', {1: None})] * 3
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['categories']['peer']['n'] == 3          # reviewers still count (anonymity)
    assert comp['categories']['peer']['hidden'] is False  # cleared the n>=3 gate…
    assert comp['categories']['peer']['score'] is None    # …but observed nothing here
    assert comp['others'] == 4.0                          # composite = manager only
    assert comp['others_n'] == 1                          # denominator excludes the not-observed peers


def test_johari_blind_spot():
    reviews = [review('self', {1: 5})] + [review('peer', {1: 2})] * 3
    comp = build_participant_report(reviews, [1])['competencies'][0]
    assert comp['self'] == 5.0 and comp['others'] == 2.0
    assert comp['johari'] == 'blind_spot'   # self high, others low


# ── Others denominator (n) — the report must never hide the sample size ──────

def test_others_n_counts_visible_non_self_reviewers():
    reviews = [review('self', {1: 5}), review('manager', {1: 4})] \
        + [review('peer', {1: 3})] * 3 + [review('direct_report', {1: 4})] * 3
    rep = build_participant_report(reviews, [1])
    comp = rep['competencies'][0]
    assert comp['others_n'] == 7   # 1 manager + 3 peers + 3 direct reports behind "others"
    assert rep['others_n'] == 7    # report-level: distinct visible non-self reviewers


def test_others_n_excludes_hidden_peer_group():
    reviews = [review('self', {1: 5}), review('manager', {1: 4}),
               review('peer', {1: 3}), review('peer', {1: 3})]  # only 2 peers → hidden
    rep = build_participant_report(reviews, [1])
    comp = rep['competencies'][0]
    assert comp['categories']['peer']['hidden'] is True   # notice, not values
    assert comp['others'] == 4.0                           # only the manager contributes
    assert comp['others_n'] == 1                           # denominator excludes hidden peers
    assert rep['others_n'] == 1
