"""Unit tests for the pure model/measurement code (no Firestore). Run: pytest"""
from datetime import datetime, timedelta, timezone

import pytest

from model import (DEFAULT_CAPS, DEFAULT_INPUTS, DEFAULT_MODEL, INPUT_NAMES, build_raw, compute_cart_abandon,
                   delivery_fee, haversine_km, is_stale, late_night, normalize, score_session, TZ)


def bkk(h, m=0):
    return datetime(2026, 11, 6, h, m, tzinfo=TZ)


def test_model_matches_original_api_output():
    # Value the original app.py returned for the default inputs.
    assert compute_cart_abandon([DEFAULT_INPUTS[n] for n in INPUT_NAMES], DEFAULT_MODEL) == pytest.approx(0.38912234987625993)


@pytest.mark.parametrize('dt,expected', [
    (bkk(3), 1.0), (bkk(0), 1.0), (bkk(5), 0.5), (bkk(6), 0.0),
    (bkk(12), 0.0), (bkk(20), 0.0), (bkk(21), 0.25), (bkk(22), 0.5),
])
def test_late_night_curve(dt, expected):
    assert late_night(dt) == pytest.approx(expected)


def test_late_night_converts_utc_to_bangkok():
    assert late_night(datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc)) == 1.0  # 03:00 in Bangkok


def test_normalize_scales_and_clamps():
    raw = {'time': bkk(12), 'cart_value': 500, 'delivery_fee': 40, 'distance': 30,
           'payment_dwell_time': 60, 'back_exit_behavior': 9}
    assert normalize(raw, DEFAULT_CAPS) == pytest.approx({
        'time': 0.0, 'cart_value': 0.5, 'delivery_fee': 0.4, 'distance': 1.0,
        'payment_dwell_time': 0.5, 'back_exit_behavior': 1.0,
    })


@pytest.mark.parametrize('bad', [{'cart_value': None}, {'distance': -1}, {'time': '12:00'}, {'delivery_fee': True}])
def test_normalize_rejects_bad_values(bad):
    raw = {'time': bkk(12), 'cart_value': 1, 'delivery_fee': 1, 'distance': 1,
           'payment_dwell_time': 1, 'back_exit_behavior': 1, **bad}
    with pytest.raises(ValueError):
        normalize(raw)


def test_haversine_and_fee_tiers():
    # Siam -> Sala Daeng is ~2 km in a straight line.
    assert haversine_km(13.7466, 100.5347, 13.7290, 100.5340) == pytest.approx(1.96, abs=0.05)
    assert haversine_km(13.7, 100.5, 13.7, 100.5) == 0
    assert delivery_fee(2.9) == 20
    assert delivery_fee(3.0) == 20
    assert delivery_fee(6) == 40
    assert delivery_fee(15) == 60
    assert delivery_fee(15.1) is None


def _session(**over):
    t0 = datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc)  # 23:00 Bangkok
    s = {
        'status': 'open', 'started_at': t0, 'last_activity_at': t0 + timedelta(minutes=5),
        'cart': {'a': {'name': 'A', 'price': 100, 'qty': 2}, 'b': {'name': 'B', 'price': 50, 'qty': 1}},
        'distance_km': 6.0, 'fee': 40, 'payment_entered_at': t0 + timedelta(minutes=4),
        'events': [{'type': 'add_item'}, {'type': 'back'}, {'type': 'remove_item'}, {'type': 'tab_hidden'},
                   {'type': 'step_enter'}],
    }
    s.update(over)
    return s


def test_build_raw_measures_session():
    s = _session()
    raw = build_raw(s, s['last_activity_at'])
    assert raw['cart_value'] == 250
    assert raw['delivery_fee'] == 40
    assert raw['distance'] == 6.0
    assert raw['payment_dwell_time'] == 60
    assert raw['back_exit_behavior'] == 3


def test_score_session_flags_incomplete_without_address():
    s = _session(distance_km=None, fee=None, payment_entered_at=None)
    out = score_session(s, s['last_activity_at'], DEFAULT_CAPS, DEFAULT_MODEL)
    assert out['incomplete'] is True
    assert out['inputs']['distance'] == 0 and out['inputs']['payment_dwell_time'] == 0
    assert out['inputs']['time'] == pytest.approx(0.75)  # 23:00
    assert 0 < out['score'] < 2
    assert out['raw']['time'].startswith('2026-11-06T23:00')


def test_is_stale():
    s = _session()
    later = s['last_activity_at'] + timedelta(minutes=31)
    assert is_stale(s, later, 30)
    assert not is_stale(s, s['last_activity_at'] + timedelta(minutes=29), 30)
    assert not is_stale({**s, 'status': 'paid'}, later, 30)
