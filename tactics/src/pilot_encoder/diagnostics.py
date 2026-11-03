"""Train-batch observations only; no RNG, extra forward, selection or tuning."""
from __future__ import annotations

import math

import torch


@torch.no_grad()
def batch_diagnostics(embedding, labels, inputs, mask, temperature=0.1):
    """Distinguish uniform logits from identical embeddings on sampled batches.

    All values describe the existing training forward (dropout/augmentation on).
    Input summaries use valid frames; V3 includes all seven agent slots.
    These are observations, not success thresholds or stopping criteria.
    """
    z = embedding.detach()
    batch = len(z)
    self_pair = torch.eye(batch, device=z.device, dtype=torch.bool)
    same_identity = labels[:, None].eq(labels[None, :])
    positive = same_identity & ~self_pair
    negative = ~same_identity
    counts = positive.sum(dim=1)
    if batch < 2 or not bool((counts > 0).all()) or not bool(negative.any()):
        raise ValueError('Diagnostics require positive partners and negative identities')
    cosine = z @ z.T
    logits = cosine / temperature
    log_prob = logits.masked_fill(self_pair, -torch.inf).log_softmax(dim=1)
    probability = log_prob.exp()
    entropy = -(probability * log_prob.masked_fill(self_pair, 0)).sum(dim=1)
    valid = inputs.detach()[mask].reshape(-1, inputs.shape[-1])
    lengths = mask.sum(dim=1)
    return {
        'batch_size': batch,
        'positive_counts_min': int(counts.min()),
        'positive_counts_max': int(counts.max()),
        'uniform_loss_reference': math.log(batch - 1),
        'positive_only_loss_floor': float(counts.float().log().mean()),
        'mean_softmax_entropy': float(entropy.mean()),
        'mean_row_logit_std': float(logits[~self_pair].reshape(batch, batch - 1)
                                   .std(dim=1, unbiased=False).mean()),
        'positive_cosine_mean': float(cosine[positive].mean()),
        'negative_cosine_mean': float(cosine[negative].mean()),
        'embedding_std_mean': float(z.std(dim=0, unbiased=False).mean()),
        'embedding_norm_min': float(z.norm(dim=1).min()),
        'embedding_norm_max': float(z.norm(dim=1).max()),
        'valid_frames_min': int(lengths.min()),
        'valid_frames_max': int(lengths.max()),
        'input_channel_mean': valid.mean(dim=0).cpu().tolist(),
        'input_channel_std': valid.std(dim=0, unbiased=False).cpu().tolist(),
        'input_channel_abs_max': valid.abs().amax(dim=0).cpu().tolist(),
    }
