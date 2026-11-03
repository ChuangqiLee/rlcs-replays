"""Training-only representation/optimizer diagnostics; no retrieval claims."""
from __future__ import annotations

import math

import numpy as np


def _distribution(values):
    values = np.asarray(values)
    if not values.size:
        return {"count": 0, "mean": None, "sd": None, "q05": None, "q50": None, "q95": None}
    return {"count": int(values.size), "mean": float(values.mean()), "sd": float(values.std()),
            **dict(zip(("q05", "q50", "q95"), np.quantile(values, [.05, .5, .95]).tolist()))}


def embedding_diagnostics(embeddings, labels, *, max_pairs_examples=512, seed=42):
    """Diagnose finite train embeddings, using bounded deterministic pair samples.

    Effective rank uses centered covariance energy, not uncentered vector norm.
    Constant nonzero embeddings therefore have rank zero despite unit norms.
    Caller must pass training-only labels/vectors; no evaluation fitting occurs.
    """
    x = np.asarray(embeddings, dtype=np.float64)
    labels = np.asarray(labels)
    if x.ndim != 2 or len(x) < 2 or labels.shape != (len(x),):
        raise ValueError("Need at least two aligned embedding/label rows")
    if not np.isfinite(x).all() or max_pairs_examples < 2:
        raise ValueError("Embeddings must be finite and pair cap >=2")
    centered = x - x.mean(axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    energy = singular**2
    if energy.sum() <= 1e-20:
        rank = 0.
        numeric_rank = 0
    else:
        weights = energy[energy > 0] / energy.sum()
        rank = float(np.exp(-np.sum(weights * np.log(weights))))
        numeric_rank = int(np.count_nonzero(singular > singular[0] * 1e-6))
    indices = np.random.default_rng(seed).choice(len(x), min(len(x), max_pairs_examples), replace=False)
    pair_x, pair_labels = x[indices], labels[indices]
    norms = np.linalg.norm(pair_x, axis=1)
    unit = np.divide(pair_x, norms[:, None], out=np.zeros_like(pair_x), where=norms[:, None] > 1e-12)
    cosine = np.clip(np.einsum("ij,kj->ik", unit, unit, optimize=False), -1., 1.)
    valid = np.triu(np.ones_like(cosine, dtype=bool), k=1)
    valid &= (norms[:, None] > 1e-12) & (norms[None, :] > 1e-12)
    same = pair_labels[:, None] == pair_labels[None, :]
    within, between = _distribution(cosine[valid & same]), _distribution(cosine[valid & ~same])
    return {"n_examples": len(x), "dimension": x.shape[1], "n_identities": len(np.unique(labels)),
            "mean_feature_variance": float(x.var(axis=0).mean()),
            "max_feature_variance": float(x.var(axis=0).max()),
            "effective_rank_centered_covariance": rank, "numerical_rank": numeric_rank,
            "embedding_norm": _distribution(np.linalg.norm(x, axis=1)),
            "zero_norm_examples": int(np.sum(np.linalg.norm(x, axis=1) <= 1e-12)),
            "pair_sample_examples": len(indices), "pair_seed": seed,
            "pairwise_cosine": _distribution(cosine[valid]),
            "same_identity_cosine": within, "different_identity_cosine": between,
            "same_minus_different_cosine": (within["mean"] - between["mean"])
                if within["count"] and between["count"] else None,
            "uniform_self_excluded_supcon_loss": math.log(len(x) - 1),
            "interpretation": "Training-only diagnostic; a uniform-like loss alone does not prove collapse"}


def parameter_snapshot(model):
    """CPU clone before a diagnostic update; bounded by the small model size."""
    return {name: parameter.detach().cpu().clone() for name, parameter in model.named_parameters()}


def optimizer_diagnostics(model, before=None):
    """Call after backward/update; distinguish missing, zero and nonfinite grads."""
    import torch
    squared_gradient, squared_update = 0., 0.
    count, missing, nonfinite, changed = 0, [], [], 0
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        count += parameter.numel()
        if parameter.grad is None:
            missing.append(name)
        else:
            grad = parameter.grad.detach().float()
            if not bool(torch.isfinite(grad).all()):
                nonfinite.append(name)
            squared_gradient += float(torch.sum(grad**2).cpu())
        if before is not None:
            delta = parameter.detach().cpu() - before[name]
            squared_update += float(torch.sum(delta.double()**2))
            changed += int(torch.count_nonzero(delta))
    return {"trainable_parameters": count,
            "gradient_l2_norm": math.sqrt(squared_gradient) if math.isfinite(squared_gradient) else None,
            "missing_gradient_parameters": missing, "nonfinite_gradient_parameters": nonfinite,
            "parameter_delta_l2_norm": math.sqrt(squared_update)
                if before is not None and math.isfinite(squared_update) else None,
            "changed_parameter_elements": changed if before is not None else None}
