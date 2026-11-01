"""Train-only co-occurring-player additions to frozen identity-balanced batches."""
from __future__ import annotations

import numpy as np

from .training import IdentitySampler


class ContextIdentitySampler(IdentitySampler):
    """Keep base epoch size fixed; add paired same-replay hard-negative anchors.

    The extra examples use the existing global identity labels, so they cannot
    turn same-player windows into negatives. Added identities are absent from
    the base batch and are unique within the augmentation. The sampler only
    retains training metadata and never accesses feature arrays or eligibility.
    """

    def __init__(self, window_games, games, batch_identities=16, windows_per_identity=4, seed=42):
        super().__init__(window_games, games, batch_identities, windows_per_identity, seed)
        self.window_games = np.asarray(window_games)
        self.label_by_identity = {identity: label for label, identity in enumerate(self.identities)}
        self.replay_by_game = {}
        self.games_by_replay = {}
        for identity in self.identities:
            for game in self.by_identity[identity]:
                # Every game in this map has already passed the parent's TRAIN
                # season/split checks. No validation replay/identity is retained.
                row = games.iloc[game]
                replay_key = (str(row.season), str(row.replay_id))
                self.replay_by_game[game] = replay_key
                self.games_by_replay.setdefault(replay_key, []).append((identity, game))
        for key, entries in self.games_by_replay.items():
            if len({identity for identity, _ in entries}) != len(entries):
                raise ValueError('Duplicate train player-game in co-occurrence sampler')
            self.games_by_replay[key] = sorted(entries)
        self.batches_sampled = 0
        self.context_identities_added = 0
        self.context_windows_added = 0
        self.cooccurring_windows_added = 0
        self.cross_game_positive_pairs = 0
        self.base_anchor_opportunities = 0
        self.max_observed_batch_size = 0
        self.last_additions = []

    def sample(self):
        base_indices, base_labels = super().sample()
        chosen_labels = list(dict.fromkeys(base_labels.tolist()))
        excluded = {self.identities[label] for label in chosen_labels}
        indices, labels = base_indices.tolist(), base_labels.tolist()
        self.last_additions = []
        for label in chosen_labels:
            anchor = int(self.rng.choice(base_indices[base_labels == label]))
            anchor_game = int(self.window_games[anchor])
            replay = self.replay_by_game[anchor_game]
            candidates = [(identity, game) for identity, game in self.games_by_replay[replay]
                          if identity not in excluded]
            self.base_anchor_opportunities += 1
            if not candidates:
                continue
            identity, context_game = candidates[int(self.rng.integers(len(candidates)))]
            bag = self.by_identity[identity]
            first = int(self.rng.choice(bag[context_game]))
            other_games = [game for game in sorted(bag) if game != context_game]
            second_game = int(self.rng.choice(other_games)) if other_games else context_game
            second = int(self.rng.choice(bag[second_game]))
            indices.extend((first, second))
            labels.extend((self.label_by_identity[identity],) * 2)
            excluded.add(identity)
            self.context_identities_added += 1
            self.context_windows_added += 2
            self.cooccurring_windows_added += 1 + int(second_game == context_game)
            self.cross_game_positive_pairs += int(second_game != context_game)
            self.last_additions.append({'anchor_window': anchor, 'context_window': first,
                                        'positive_window': second,
                                        'identity_label': self.label_by_identity[identity]})
        self.batches_sampled += 1
        self.max_observed_batch_size = max(self.max_observed_batch_size, len(indices))
        return np.asarray(indices, dtype=np.int64), np.asarray(labels, dtype=np.int64)

    def report(self):
        return {'batches_sampled': self.batches_sampled,
                'base_batch_size': self.batch_size,
                'maximum_batch_size': self.batch_size + 2 * self.batch_identities,
                'max_observed_batch_size': self.max_observed_batch_size,
                'base_anchor_opportunities': self.base_anchor_opportunities,
                'context_identities_added': self.context_identities_added,
                'context_windows_added': self.context_windows_added,
                'cooccurring_windows_added': self.cooccurring_windows_added,
                'cross_game_positive_pairs': self.cross_game_positive_pairs,
                'source': 'train-only usable player-games; no eligibility filter',
                'epoch_steps_use_base_batch_size': True}
