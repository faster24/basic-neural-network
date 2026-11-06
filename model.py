"""Cart-abandonment model (see network.jpg) and the input measurements that feed it.

Pure functions only (no Firestore), so they can be unit-tested directly.
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

TZ = ZoneInfo('Asia/Bangkok')

# Input layer x1..x6, in the column order of W1.
INPUT_NAMES = ['time', 'cart_value', 'delivery_fee', 'distance', 'payment_dwell_time', 'back_exit_behavior']

# Default (already normalized) input values, shown by GET /input_variables.
DEFAULT_INPUTS = {
    'time': 0.2,                # x1
    'cart_value': 0.2,          # x2
    'delivery_fee': 0.9,        # x3
    'distance': 0.9,            # x4
    'payment_dwell_time': 0.9,  # x5
    'back_exit_behavior': 0.9,  # x6
}

# Model v1. shortcut: placeholder weights, fit them from the CSV export.
DEFAULT_MODEL = {
    'W1': [
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],  # H1 brand_love
        [0.6, 0.5, 0.4, 0.3, 0.2, 0.1],  # H2 program_love
    ],
    'omega': 0.5,
    'wH1': 0.88,
    'wH2': 0.87,
    'eta': 0.9,
}

# Raw value that maps to 1.0 for each input (THB, km, seconds, event count).
DEFAULT_CAPS = {
    'cart_value': 1000,
    'delivery_fee': 100,
    'distance': 15,
    'payment_dwell_time': 120,
    'back_exit_behavior': 5,
}

# [max_km, fee_THB], ascending. Beyond the last tier: no delivery.
DEFAULT_FEE_TIERS = [[3, 20], [7, 40], [15, 60]]

HESITATION_EVENTS = {'back', 'remove_item', 'tab_hidden'}


def compute_cart_abandon(x, model=DEFAULT_MODEL):
    """Run the network on 6 normalized inputs (INPUT_NAMES order); return the final cart-abandon value."""
    W1 = np.array(model['W1'], dtype=float)
    x = np.array(x, dtype=float)
    dt = 0.01
    eta, omega, wH1, wH2 = model['eta'], model['omega'], model['wH1'], model['wH2']
    array_length = 800

    # Hidden layer 1 (fully connected): scaled sum of all inputs per node
    brand_love, program_love = W1 @ x / W1.sum(axis=1)

    # Hidden layer 2: both nodes take both hidden-1 nodes
    disappointment = omega * program_love + (1 - omega) * brand_love  # H4
    convenience = wH1 * brand_love + wH2 * program_love               # H5

    # Output Y: cart abandon moves toward the aggregated impact over time
    aggregated = (1 - disappointment) * convenience
    cart_abandon = np.zeros(array_length)
    cart_abandon[0] = 0.1
    for t in range(1, array_length):
        cart_abandon[t] = cart_abandon[t-1] + eta * (aggregated - cart_abandon[t-1]) * dt
    return float(cart_abandon[-1])


def late_night(dt):
    """0 by day, ramps 20:00->00:00 up to 1, stays 1 until 04:00, ramps down to 0 by 06:00 (Bangkok time)."""
    local = dt.astimezone(TZ)
    h = local.hour + local.minute / 60
    if h < 4:
        return 1.0
    if h < 6:
        return (6 - h) / 2
    if h < 20:
        return 0.0
    return (h - 20) / 4


def _clamp01(v):
    return min(max(v, 0.0), 1.0)


def normalize(raw, caps=DEFAULT_CAPS):
    """Raw measurements -> {input_name: 0..1}. raw['time'] is a tz-aware datetime, others are numbers."""
    if not isinstance(raw.get('time'), datetime):
        raise ValueError('time must be a datetime')
    out = {'time': late_night(raw['time'])}
    for name in INPUT_NAMES[1:]:
        v = raw.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or v < 0:
            raise ValueError(f'{name} must be a non-negative number')
        out[name] = _clamp01(v / caps[name])
    return out


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def delivery_fee(km, tiers=DEFAULT_FEE_TIERS):
    """Fee in THB for a distance, or None if out of delivery range."""
    for max_km, fee in tiers:
        if km <= max_km:
            return fee
    return None


def hesitation_count(events):
    return sum(1 for e in events if e.get('type') in HESITATION_EVENTS)


def build_raw(session, end_at):
    """Raw measurements of a checkout session at the moment it closes."""
    pay_at = session.get('payment_entered_at')
    return {
        'time': session['started_at'],
        'cart_value': float(sum(i['price'] * i['qty'] for i in session.get('cart', {}).values())),
        'delivery_fee': float(session.get('fee') or 0),
        'distance': float(session.get('distance_km') or 0),
        'payment_dwell_time': max((end_at - pay_at).total_seconds(), 0.0) if pay_at else 0.0,
        'back_exit_behavior': hesitation_count(session.get('events', [])),
    }


def score_session(session, end_at, caps, model):
    """Fields to store on a closing session: raw values, normalized inputs, score, incomplete flag."""
    raw = build_raw(session, end_at)
    inputs = normalize(raw, caps)
    return {
        'raw': {**raw, 'time': raw['time'].astimezone(TZ).isoformat()},
        'inputs': inputs,
        'score': compute_cart_abandon([inputs[n] for n in INPUT_NAMES], model),
        'incomplete': session.get('distance_km') is None,
    }


def is_stale(session, now, minutes):
    return session.get('status') == 'open' and (now - session['last_activity_at']).total_seconds() > minutes * 60
