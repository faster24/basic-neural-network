"""Firestore access for store settings, model versions and products."""
from datetime import datetime, timezone

from connect import db
from model import DEFAULT_CAPS, DEFAULT_FEE_TIERS, DEFAULT_MODEL

DEFAULT_SETTINGS = {
    'name': 'Kirin Kitchen',
    'lat': 13.7466,   # Siam, Bangkok
    'lng': 100.5347,
    'hours': '10:00 – 02:00',
    'fee_tiers': DEFAULT_FEE_TIERS,
    'caps': DEFAULT_CAPS,
    'abandon_minutes': 30,
    'active_model': 'v1',
}


def now():
    return datetime.now(timezone.utc)


def get_settings():
    doc = db.collection('settings').document('store').get()
    stored = doc.to_dict() if doc.exists else {}
    # Firestore can't store nested arrays, so tiers are kept as [{'max_km','fee'}].
    if 'fee_tiers' in stored:
        stored['fee_tiers'] = [[t['max_km'], t['fee']] for t in stored['fee_tiers']]
    return {**DEFAULT_SETTINGS, **stored, 'caps': {**DEFAULT_CAPS, **stored.get('caps', {})}}


def save_settings(settings):
    data = {**settings, 'fee_tiers': [{'max_km': k, 'fee': f} for k, f in settings['fee_tiers']]}
    db.collection('settings').document('store').set(data)


def _model_to_doc(model):
    return {**model, 'W1': {'H1': model['W1'][0], 'H2': model['W1'][1]}}


def get_model(version):
    doc = db.collection('models').document(version).get()
    if not doc.exists:
        if version == 'v1':
            return dict(DEFAULT_MODEL)
        raise LookupError(f'model {version} not found')
    d = doc.to_dict()
    return {**d, 'W1': [d['W1']['H1'], d['W1']['H2']]}


def list_model_versions():
    return sorted((d.id for d in db.collection('models').stream()), key=lambda v: int(v[1:]))


def create_model_version(model):
    """Save weights as the next version and make it active. Returns the new version id."""
    versions = list_model_versions() or ['v1']
    version = f'v{int(versions[-1][1:]) + 1}'
    db.collection('models').document(version).set({**_model_to_doc(model), 'created_at': now()})
    db.collection('settings').document('store').set({'active_model': version}, merge=True)
    return version


def seed_model_v1():
    ref = db.collection('models').document('v1')
    if not ref.get().exists:
        ref.set({**_model_to_doc(DEFAULT_MODEL), 'created_at': now()})


def list_products(include_hidden=False):
    items = [{'id': d.id, **d.to_dict()} for d in db.collection('products').stream()]
    if not include_hidden:
        items = [p for p in items if not p.get('hidden')]
    return sorted(items, key=lambda p: (p.get('category', ''), p.get('name', '')))


def get_product(pid):
    doc = db.collection('products').document(pid).get()
    return {'id': doc.id, **doc.to_dict()} if doc.exists else None


def save_product(pid, product):
    ref = db.collection('products').document(pid) if pid else db.collection('products').document()
    ref.set(product)
    return ref.id
