"""Report aggregation (spec §4 anonymity + §8 scoring). Pure — no DB.

Turns a participant's submitted reviews into an anonymity-gated report. A
relationship category is shown only when it clears the min-n threshold (self &
manager always attributed); below threshold it is hidden and its ratings never
reach the output (indicator B6, fail-closed). Per competency:

  category score = mean of that relationship's observed ratings (pooled),
  others composite = mean of the visible *others* category means (NOT pooled),
  gap = self − others,  Johari from (self, others).
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from hr.evaluation360.domain import scoring
from hr.evaluation360.domain import anonymity


def build_participant_report(reviews, competency_ids, min_n: int = anonymity.DEFAULT_MIN_N):
    """Aggregate one participant's report.

    ``reviews``: one entry per submitted assignment —
        {'relationship': str, 'answers': [{'competency_id', 'rating', 'not_observed'}]}
    ``competency_ids``: competencies to report on, in display order.
    """
    # Anonymity n is per relationship *category*, counted in reviewers (not answers).
    reviewer_counts: dict[str, int] = defaultdict(int)
    for r in reviews:
        reviewer_counts[r['relationship']] += 1
    visible, hidden = anonymity.apply_anonymity(dict(reviewer_counts), min_n)
    visible_set = set(visible)

    competencies = []
    for cid in competency_ids:
        pooled: dict[str, list] = defaultdict(list)
        for r in reviews:
            rel = r['relationship']
            for a in r['answers']:
                if a.get('competency_id') == cid and not a.get('not_observed') and a.get('rating') is not None:
                    pooled[rel].append(a['rating'])

        categories = {}
        for rel in reviewer_counts:
            shown = rel in visible_set
            if shown:
                # Fail-closed guard: never emit a below-threshold, non-attributed score.
                anonymity.assert_renderable(rel, reviewer_counts[rel], min_n)
            ratings = pooled.get(rel, [])
            categories[rel] = {
                'n': reviewer_counts[rel],
                'score': round(mean(ratings), 3) if (shown and ratings) else None,
                'hidden': not shown,
            }

        self_score = categories.get('self', {}).get('score')
        others_scores = [
            c['score'] for rel, c in categories.items()
            if rel != 'self' and not c['hidden'] and c['score'] is not None
        ]
        others = scoring.others_composite(others_scores)
        competencies.append({
            'competency_id': cid,
            'self': self_score,
            'others': others,
            'gap': scoring.gap(self_score, others),
            'johari': scoring.johari_quadrant(self_score, others),
            'categories': categories,
        })

    return {
        'competencies': competencies,
        'visible_relationships': visible,
        'hidden_relationships': hidden,
    }
