"""Pure-Python logistic regression scorer (HANDOFF §10 Phase 5).

Implements the same contract as the rule engine — ``score(features, profile) -> (score, reasons)``
— so a trained model is a hot-swappable, per-species drop-in for ``scorer.score`` (§2 invariant).
The "profile" here is a trained artifact (JSON-serializable) instead of a hand-written habitat
profile. Zero dependencies: training and inference are plain arithmetic, so the whole path ports to
a Cloudflare Pages Function unchanged.

Deliberately linear: at the cold-start label counts this project has (single digits per species),
a regularized linear model degrades gracefully toward the prior rather than memorizing noise, and
its signed coefficients read directly as the human ``reasons`` surface. Gradient boosting is the
right tool only once labels grow past the §2.5 graduation threshold.
"""

import math

# Training hyperparameters. L2 is intentionally strong — the dominant guard against overfitting a
# handful of labels. Overridable by callers, but these are sane cold-start defaults.
LEARNING_RATE = 0.1
ITERATIONS = 2000
L2 = 1.0
MAX_REASONS = 4

# Human-readable names for the reasons surface; falls back to the raw column name.
FEATURE_LABELS = {
    "sst_f": "sea surface temp",
    "sst_break_gradient": "temp break",
    "chlorophyll": "water color",
    "dist_to_stream_edge_nm": "distance to current edge",
    "wave_height_ft": "wave height",
    "wind_speed_kt": "wind speed",
    "wind_dir_deg": "wind direction",
    "pressure_mb": "pressure",
    "pressure_trend_3h": "pressure trend",
    "current_speed_kt": "current speed",
    "current_dir_deg": "current direction",
    "moon_illumination": "moon",
    "solunar_score": "solunar",
    "depth_ft": "depth",
}


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _column(feature_dicts: list[dict], name: str) -> list[float]:
    return [
        float(f[name]) for f in feature_dicts if f.get(name) is not None
    ]  # observed values only


def train(
    feature_dicts: list[dict],
    y: list[int],
    feature_names: list[str],
    *,
    iterations: int = ITERATIONS,
    lr: float = LEARNING_RATE,
    l2: float = L2,
) -> dict:
    """Fit logistic regression on standardized, mean-imputed features. Returns a JSON-ready artifact.

    Missing values are imputed with the per-feature training mean; features are z-scored so the
    learned coefficients are directly comparable for the reasons surface. Both the means and stds are
    stored so inference reproduces the exact transform.
    """
    n = len(y)
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for name in feature_names:
        observed = _column(feature_dicts, name)
        mean = sum(observed) / len(observed) if observed else 0.0
        var = sum((v - mean) ** 2 for v in observed) / len(observed) if observed else 0.0
        means[name] = mean
        stds[name] = math.sqrt(var) or 1.0  # guard constant/absent features

    # Standardized design matrix (imputed → z-scored).
    x = [
        [
            ((float(f.get(name)) if f.get(name) is not None else means[name]) - means[name])
            / stds[name]
            for name in feature_names
        ]
        for f in feature_dicts
    ]

    weights = [0.0] * len(feature_names)
    bias = 0.0
    for _ in range(iterations):
        grad_w = [0.0] * len(feature_names)
        grad_b = 0.0
        for i in range(n):
            pred = _sigmoid(bias + sum(weights[j] * x[i][j] for j in range(len(feature_names))))
            err = pred - y[i]
            grad_b += err
            for j in range(len(feature_names)):
                grad_w[j] += err * x[i][j]
        bias -= lr * grad_b / n
        for j in range(len(feature_names)):
            # L2 shrinks weights toward 0; bias is left unregularized.
            weights[j] -= lr * (grad_w[j] / n + l2 * weights[j] / n)

    return {
        "kind": "logreg",
        "feature_names": list(feature_names),
        "means": means,
        "stds": stds,
        "coef": weights,
        "intercept": bias,
        "n_pos": sum(y),
        "n_neg": len(y) - sum(y),
    }


def _standardize(features: dict, artifact: dict) -> list[float]:
    means, stds = artifact["means"], artifact["stds"]
    out = []
    for name in artifact["feature_names"]:
        raw = features.get(name)
        value = float(raw) if raw is not None else means[name]  # impute gaps with training mean
        out.append((value - means[name]) / stds[name])
    return out


def score(features: dict, artifact: dict) -> tuple[float, list[str]]:
    """Score one (zone, species) pair with a trained model. Same contract as ``scorer.score``."""
    x = _standardize(features, artifact)
    coef = artifact["coef"]
    z = artifact["intercept"] + sum(coef[j] * x[j] for j in range(len(coef)))
    prob = _sigmoid(z)

    # Reasons = the features that moved this score most (signed coef × standardized value).
    contributions = sorted(
        ((coef[j] * x[j], artifact["feature_names"][j]) for j in range(len(coef))),
        key=lambda c: abs(c[0]),
        reverse=True,
    )
    reasons = []
    for contrib, name in contributions[:MAX_REASONS]:
        if abs(contrib) < 1e-6:
            continue
        label = FEATURE_LABELS.get(name, name)
        raw = features.get(name)
        shown = f" ({raw:g})" if isinstance(raw, int | float) else ""
        reasons.append(f"{label}{shown} {'favorable' if contrib > 0 else 'unfavorable'}")
    if not reasons:
        reasons.append("model: no distinguishing conditions")
    return round(prob * 100, 1), reasons
