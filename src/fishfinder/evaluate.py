"""Model-vs-rules eval harness + promotion gate (HANDOFF §10 Phase 5, §2.5).

The gate is the real deliverable: it protects the rule scorer from a premature swap. A per-species
model is promoted only when there is enough labeled data *and* the model out-ranks the rules on a
held-out, time-based split. At the cold-start label counts this project has, the gate is expected to
decline — and it says so honestly. The same harness auto-promotes once labels cross the threshold,
with no code change.
"""

from . import model as model_mod
from . import scorer as scorer_mod

# §2.5 graduates a species at ~200 labeled catches per corridor. We keep that as the documented
# north star but gate on a far smaller, demoable floor so the machinery is exercisable today.
GRADUATION_TARGET = 200
MIN_PER_CLASS = 8  # minimum caught AND skunked labels before a model is even a candidate
TEST_FRACTION = 0.3
AUC_MARGIN = 0.05  # model must beat rules' held-out AUC by at least this to promote


def _auc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney AUC: P(random positive scores above random negative). None if single-class."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    # Rank all scores (average ranks for ties), sum ranks of positives.
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank across the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum_pos = sum(ranks[i] for i in range(len(scores)) if labels[i] == 1)
    return (rank_sum_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def _time_split(caught_at: list[str]) -> tuple[list[int], list[int]]:
    """Indices for (train, test): oldest labels train, most-recent TEST_FRACTION held out."""
    order = sorted(range(len(caught_at)), key=lambda i: caught_at[i])
    n_test = max(1, round(len(order) * TEST_FRACTION))
    train, test = order[:-n_test], order[-n_test:]
    return train, test


def holdout_report(
    feature_dicts: list[dict],
    y: list[int],
    caught_at: list[str],
    feature_names: list[str],
    rules_profile: dict,
) -> dict:
    """Train on the older split, compare model vs rules AUC on the held-out recent split, gate."""
    n_pos, n_neg = sum(y), len(y) - sum(y)
    report = {
        "n_labels": len(y),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "graduation_target": GRADUATION_TARGET,
        "model_auc": None,
        "rules_auc": None,
        "promote": False,
        "reason": "",
    }

    if n_pos < MIN_PER_CLASS or n_neg < MIN_PER_CLASS:
        report["reason"] = (
            f"insufficient labels ({n_pos} caught / {n_neg} skunked; "
            f"need ≥{MIN_PER_CLASS} of each) — rules remain champion"
        )
        return report

    train_idx, test_idx = _time_split(caught_at)
    train_x = [feature_dicts[i] for i in train_idx]
    train_y = [y[i] for i in train_idx]
    test_x = [feature_dicts[i] for i in test_idx]
    test_y = [y[i] for i in test_idx]

    if len(set(train_y)) < 2 or len(set(test_y)) < 2:
        report["reason"] = "held-out split is single-class — rules remain champion"
        return report

    fold = model_mod.train(train_x, train_y, feature_names)
    model_scores = [model_mod.score(f, fold)[0] for f in test_x]
    rules_scores = [scorer_mod.score(f, rules_profile)[0] for f in test_x]
    model_auc = _auc(model_scores, test_y)
    rules_auc = _auc(rules_scores, test_y)
    report["model_auc"] = model_auc
    report["rules_auc"] = rules_auc

    if model_auc is None or rules_auc is None:
        report["reason"] = "could not evaluate AUC on held-out split — rules remain champion"
        return report
    if model_auc >= rules_auc + AUC_MARGIN:
        report["promote"] = True
        report["reason"] = (
            f"model beats rules on held-out data (AUC {model_auc:.2f} vs {rules_auc:.2f})"
        )
    else:
        report["reason"] = (
            f"model does not beat rules by ≥{AUC_MARGIN:g} "
            f"(AUC {model_auc:.2f} vs {rules_auc:.2f}) — rules remain champion"
        )
    return report
