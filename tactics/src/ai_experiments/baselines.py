"""Train-only linear and MLP metrics on handcrafted/common-channel summaries."""
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from pilot_encoder.models import supervised_contrastive_loss
from pilot_encoder.training import seed_everything
from tactics_code.style_retrieval import check_rows
from .evaluation import train_standardize


def fit_summary(values, games, config, checkpoint_dir, device='cpu', kind='linear'):
    check_rows(games)
    train = games.split.to_numpy() == 'train'
    # Explicit fit on all train games, independently of retrieval eligibility.
    values, transform = train_standardize(values, train)
    seed_everything(config['seed'])
    rng = np.random.default_rng(config['seed'])
    indices = np.flatnonzero(train)
    identities = sorted(set(games.iloc[indices].identity_id))
    groups = {identity: indices[games.iloc[indices].identity_id.to_numpy() == identity]
              for identity in identities}
    identities = [i for i in identities if len(groups[i]) >= 2]
    if len(identities) < 2:
        raise ValueError('Summary metric needs two train identities with two distinct games each')
    model = (nn.Linear(values.shape[1], 128) if kind == 'linear' else
             nn.Sequential(nn.Linear(values.shape[1], 128), nn.GELU(), nn.Linear(128, 128))).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    steps_per_epoch = int(np.ceil(len(indices)/(min(16, len(identities))*2)))
    steps = min(config['max_steps'], config['epochs']*steps_per_epoch)
    started, losses, norms = time.perf_counter(), [], []
    for _ in range(steps):
        if time.perf_counter()-started >= config['train_budget_seconds']:
            break
        chosen = rng.choice(len(identities), size=min(16, len(identities)), replace=False)
        batch = np.concatenate([rng.choice(groups[identities[i]], 2, replace=False) for i in chosen])
        labels = torch.as_tensor(np.repeat(chosen, 2), device=device)
        opt.zero_grad(set_to_none=True)
        z = F.normalize(model(torch.as_tensor(values[batch], dtype=torch.float32, device=device)), dim=-1)
        loss = supervised_contrastive_loss(z, labels)
        if not torch.isfinite(loss):
            raise FloatingPointError('Nonfinite summary loss')
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
        opt.step()
        losses.append(float(loss.detach()))
        norms.append(float(norm))
    if not losses:
        raise RuntimeError('No summary optimizer update within budget')
    model.eval()
    with torch.inference_mode():
        z = np.concatenate([F.normalize(model(torch.as_tensor(values[i:i+512], dtype=torch.float32,
                           device=device)), dim=-1).cpu().numpy() for i in range(0, len(values), 512)])
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    torch.save(dict(model=model.state_dict(), config=config, kind=kind, transform=transform), path/'last.pt')
    return z, dict(kind=kind, fit_split='train', parameters=sum(p.numel() for p in model.parameters()),
                   optimizer_steps=len(losses), requested_steps=steps, stopped_for_budget=len(losses)<steps,
                   final_loss=losses[-1], first_loss=losses[0], gradient_norm_max=max(norms),
                   seconds=time.perf_counter()-started, transform=transform)
