"""Pure numerical tests; parquet integration lives in test_pipeline.py."""
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from tactics_code.tokens import (Grammar, bh, build_encoder, choose_codebook,
    embed, fit_encoder, grammar_test, invariant_features, rle, sequence_records)


def test_invariance_and_resource_exclusion():
    rng = np.random.default_rng(91)
    ball = rng.normal(size=(71, 6)).astype(np.float32)
    players = rng.normal(size=(71, 6, 8)).astype(np.float32)
    players[4:7, 1, :6] = np.nan
    original = invariant_features(ball, players)
    changed = players[:, [2, 0, 1, 4, 5, 3]].copy()
    changed[:, :, 6:] = rng.normal(100, 200, changed[:, :, 6:].shape)
    actual = invariant_features(ball, changed)
    assert actual.shape == (71, 44)
    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, original, rtol=1e-6, atol=1e-7)


def test_encoder_trains_temporal_and_future_parameters():
    torch = pytest.importorskip('torch')
    torch.manual_seed(52)
    model = build_encoder(44, 12)
    x = torch.randn(4, 40, 44)
    hidden, pred = model(x)
    loss = (pred - x).square().mean() + (model.future[0](hidden[:, :-5]) - x[:, 5:]).square().mean()
    loss.backward()
    for parameter in [model.gru.weight_hh_l0, model.gru.weight_ih_l0,
                      model.reconstruct.weight, model.future[0].weight]:
        assert parameter.grad is not None and parameter.grad.abs().sum().item() > 0


def test_masked_fit_keeps_scaler_training_only():
    pytest.importorskip('torch')
    rng = np.random.default_rng(9)
    train = rng.normal(size=(12, 40, 44)).astype(np.float32)
    val = rng.normal(1000, 1, size=(4, 40, 44)).astype(np.float32)
    args = SimpleNamespace(seed=42, device='cpu', hidden=8, learning_rate=.001,
                           fps=10, epochs=1, batch_size=4)
    metrics = []
    run = SimpleNamespace(metric=lambda **kwargs: metrics.append(kwargs))
    model, scaler, device, loss = fit_encoder(train, val, args, run)
    np.testing.assert_allclose(scaler.mean_, train.reshape(-1, 44).mean(axis=0), atol=1e-7)
    assert np.isfinite(loss)
    assert {row['split'] for row in metrics} == {'train', 'val'}
    z = embed(model, scaler, device, val, 2)
    assert z.shape == (4, 8) and np.isfinite(z).all()


def test_rle_and_semi_markov_preserve_state_dwells_and_lengths():
    states, dwell = rle([1, 1, 2, 2, 2, 0, 0])
    np.testing.assert_array_equal(states, [1, 2, 0])
    np.testing.assert_array_equal(dwell, [2, 3, 2])
    grammar = Grammar([[0, 0, 1, 1, 1, 2, 2, 0, 0], [1, 1, 1, 2, 2, 0, 0]], 3)
    np.testing.assert_array_equal(np.diag(grammar.first), 0)
    np.testing.assert_allclose(grammar.first.sum(axis=1), 1)
    rng = np.random.default_rng(7)
    for length in (1, 2, 40, 1001):
        sampled = grammar.simulate(length, rng)
        assert len(sampled) == length
        sampled_states, sampled_dwell = rle(sampled)
        for state, duration in zip(sampled_states[:-1], sampled_dwell[:-1]):
            assert duration in grammar.dwells[state]


def test_sequences_never_bridge_gaps_reset_or_team_boundaries():
    records = []
    for replay, team, segment, start in [('a', 0, 0, 0), ('a', 0, 0, 40),
                                        ('a', 0, 0, 120), ('a', 0, 1, 160),
                                        ('a', 1, 1, 200), ('b', 1, 1, 240)]:
        records.append(dict(replay_id=replay, focal_team=team, segment=segment,
                            start_index=start, stop_index=start + 40, series_id='series',
                            split='val', token=len(records) % 3))
    sequences = list(sequence_records(records))
    assert [len(seq) for _, _, seq in sequences] == [2, 1, 1, 1, 1]


def test_grammar_fit_does_not_use_heldout_season(monkeypatch):
    pattern = np.tile([0, 1, 2, 0, 2, 1], 30)
    rows = [('train-a', 'train', pattern), ('val-a', 'val', pattern),
            ('val-b', 'val', pattern), (None, 'val', pattern),
            ('test-a', 'test', np.tile([1, 2], 100))]
    monkeypatch.setattr('tactics_code.tokens.sequence_rows', lambda *_: iter(rows))
    args = SimpleNamespace(max_motifs=12, min_motif_count=2, seed=1, nulls=9, bootstrap=19)
    result, fitted = grammar_test(Path('unused.parquet'), 3, 'val', args)
    expected = Grammar([pattern], 3)
    np.testing.assert_allclose(fitted.first, expected.first)
    np.testing.assert_allclose(fitted.second, expected.second)
    assert result['n_series'] == 2
    assert result['status'] == 'ok'
    assert result['excess_gain_bits'] > 0
    assert result['ci95'][0] <= result['excess_gain_bits'] <= result['ci95'][1]
    assert 0 <= result['p_value'] <= 1
    assert all(row['q_value'] >= row['p_value'] for row in result['motifs'])


def test_codebook_has_no_fabricated_validation_gate():
    rng = np.random.default_rng(25)
    a = rng.normal(size=(20, 4))
    scaler, model, candidates, stable = choose_codebook(a, np.empty((0, 4)), [2, 30], 1)
    assert not stable and model.n_clusters == 2
    assert candidates[1]['eligible'] is False
    np.testing.assert_allclose(scaler.mean_, a.mean(axis=0))


def test_bh_known_values():
    np.testing.assert_allclose(bh([.01, .04, .03]), [.03, .04, .04])


def test_window_iterator_excludes_heldout_before_feature_use_and_no_reset_crossing(monkeypatch):
    from tactics_code.tokens import windows
    from tactics_code.extract import extract_replay
    from tests.synthetic import make_replay, STATE_MAP
    frame, index, manifest = make_replay(seconds=40)
    extracted = extract_replay(frame, index, {index['replay_id']: manifest}, {}, STATE_MAP)
    test_meta, test_arrays = extracted[0]
    test_meta = dict(test_meta, split='test')
    # Bad fps would raise if held-out metadata reached feature extraction.
    test_meta['fps'] = 99
    monkeypatch.setattr('tactics_code.data.iter_compact', lambda _, **kwargs: iter([*extracted, (test_meta, test_arrays)]))
    result = list(windows(Path('unused'), 4, 10, 42, {'train', 'val'}))
    assert result
    for row, x, raw in result:
        assert row['split'] == 'train'
        assert x.shape == (40, 44)
        assert raw['ball'].shape == (40, 6)
        arrays = extracted[row['focal_team']][1]
        segment = arrays['segment'][row['start_index']:row['stop_index']]
        assert np.all(segment == segment[0]) and segment[0] >= 0
