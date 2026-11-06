"""Checkout sessions in Firestore: one open session per user, from first item added to order or abandonment."""
import time

from google.cloud.firestore_v1.base_query import FieldFilter

from connect import db
from data import get_model, get_settings, now
from model import is_stale, score_session

COL = 'sessions'


def get_open(uid):
    """(ref, data) of the user's open session, or (None, None)."""
    docs = list(db.collection(COL)
                .where(filter=FieldFilter('uid', '==', uid))
                .where(filter=FieldFilter('status', '==', 'open'))
                .limit(1).stream())
    return (docs[0].reference, docs[0].to_dict()) if docs else (None, None)


def open_session(uid):
    t = now()
    data = {'uid': uid, 'status': 'open', 'started_at': t, 'last_activity_at': t,
            'cart': {}, 'events': [], 'distance_km': None, 'fee': None, 'payment_entered_at': None}
    ref = db.collection(COL).document()
    ref.set(data)
    return ref, data


def log_event(ref, data, event_type, **changes):
    """Append an event, apply field changes, bump last_activity_at. Mutates and saves `data`."""
    t = now()
    data['events'] = data.get('events', []) + [{'type': event_type, 'at': t}]
    data.update(changes, last_activity_at=t)
    # shortcut: read-modify-write without a transaction; fine for one shopper per session.
    ref.update({'events': data['events'], 'last_activity_at': t, **changes})


def close(ref, data, outcome, end_at, **extra):
    settings = get_settings()
    version = settings['active_model']
    fields = score_session(data, end_at, settings['caps'], get_model(version))
    ref.update({**fields, **extra, 'status': outcome, 'model_version': version, 'closed_at': now()})


def close_stale():
    """Mark open sessions idle longer than abandon_minutes as abandoned. Returns how many were closed."""
    minutes = get_settings()['abandon_minutes']
    t, closed = now(), 0
    for doc in db.collection(COL).where(filter=FieldFilter('status', '==', 'open')).stream():
        data = doc.to_dict()
        if is_stale(data, t, minutes):
            close(doc.reference, data, 'abandoned', data['last_activity_at'])
            closed += 1
    return closed


_last_run = 0.0


def close_stale_throttled(every_seconds=60):
    # shortcut: lazy trigger on incoming requests, move to Cloud Scheduler when hosted.
    global _last_run
    if time.monotonic() - _last_run >= every_seconds:
        _last_run = time.monotonic()
        close_stale()
