"""Customer pages and JSON API: menu -> cart -> address -> payment -> order status."""
from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from google.cloud.firestore_v1.base_query import FieldFilter

from auth import current_user, require_user
from connect import db
from data import get_product, get_settings, list_products, now
from model import delivery_fee, haversine_km
from sessions import close, get_open, log_event, open_session

bp = Blueprint('shop', __name__)

ORDER_STATUSES = ['new', 'preparing', 'out_for_delivery', 'delivered', 'cancelled']
PAYMENT_METHODS = {'cod': 'Cash on delivery', 'card': 'Card (simulated)', 'wallet': 'E-wallet (simulated)'}
CLIENT_EVENTS = {'step_enter', 'back', 'tab_hidden'}
STEPS = {'menu', 'cart', 'address', 'payment'}
MAX_QTY = 50


def subtotal(cart):
    return sum(i['price'] * i['qty'] for i in cart.values())


def cart_count(cart):
    return sum(i['qty'] for i in cart.values())


def json_body():
    # force: navigator.sendBeacon may not send an application/json content type
    return request.get_json(force=True, silent=True) or {}


def quote(settings, lat, lng):
    """Validate a pin; returns (km, fee) or raises ValueError with a customer-facing message."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError('Invalid location')
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError('Invalid location')
    km = haversine_km(settings['lat'], settings['lng'], lat, lng)
    fee = delivery_fee(km, settings['fee_tiers'])
    if fee is None:
        raise ValueError(f'Sorry, {km:.1f} km is outside our delivery area '
                         f'(max {settings["fee_tiers"][-1][0]} km).')
    return round(km, 2), fee


# ---------- pages ----------

@bp.app_context_processor
def inject_cart():
    """Cart badge + store name for every page (one cheap query when signed in)."""
    if request.blueprint == 'admin' or request.path.startswith('/api/'):
        return {}
    user = current_user()
    cart = (get_open(user['uid'])[1] or {}).get('cart', {}) if user else {}
    return {'cart_count': cart_count(cart), 'store': get_settings()}


@bp.get('/')
def menu():
    q = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '')
    products = list_products()
    categories = sorted({p.get('category', '') for p in products})
    if category:
        products = [p for p in products if p.get('category') == category]
    if q:
        products = [p for p in products
                    if q in f"{p['name']} {p.get('description', '')} {p.get('category', '')}".lower()]
    return render_template('menu.html', products=products, categories=categories, q=q, category=category, step='menu')


@bp.get('/cart')
@require_user
def cart():
    _, session = get_open(current_user()['uid'])
    items = (session or {}).get('cart', {})
    return render_template('cart.html', items=items, subtotal=subtotal(items), step='cart')


@bp.get('/checkout/address')
@require_user
def address():
    _, session = get_open(current_user()['uid'])
    if not session or not session['cart']:
        return redirect(url_for('shop.cart'))
    return render_template('address.html', subtotal=subtotal(session['cart']), step='address')


@bp.get('/checkout/payment')
@require_user
def payment():
    _, session = get_open(current_user()['uid'])
    if not session or not session['cart']:
        return redirect(url_for('shop.cart'))
    if session.get('fee') is None:
        return redirect(url_for('shop.address'))
    sub = subtotal(session['cart'])
    return render_template('payment.html', items=session['cart'], subtotal=sub, fee=session['fee'],
                           km=session['distance_km'], total=sub + session['fee'], methods=PAYMENT_METHODS,
                           step='payment')


def _own_order(order_id):
    doc = db.collection('orders').document(order_id).get()
    if not doc.exists or doc.get('uid') != current_user()['uid']:
        abort(404)
    return {'id': doc.id, **doc.to_dict()}


@bp.get('/orders/<order_id>')
@require_user
def order(order_id):
    return render_template('order.html', order=_own_order(order_id), statuses=ORDER_STATUSES[:4],
                           methods=PAYMENT_METHODS)


@bp.get('/orders')
@require_user
def history():
    orders = [{'id': d.id, **d.to_dict()} for d in
              db.collection('orders').where(filter=FieldFilter('uid', '==', current_user()['uid'])).stream()]
    orders.sort(key=lambda o: o['created_at'], reverse=True)
    return render_template('history.html', orders=orders)


@bp.get('/privacy')
def privacy():
    return render_template('privacy.html')


# ---------- JSON API ----------

@bp.post('/api/cart')
@require_user
def api_cart():
    """Body {product_id, delta}: change a cart quantity. Opens a session on the first add."""
    body = json_body()
    try:
        delta = int(body.get('delta', 0))
    except (TypeError, ValueError):
        return jsonify(error='delta must be an integer'), 400
    product = get_product(str(body.get('product_id', ''))) if delta else None
    if not product or product.get('hidden'):
        return jsonify(error='unknown product'), 400

    uid = current_user()['uid']
    ref, session = get_open(uid)
    if session is None:
        if delta < 0:
            return jsonify(error='cart is empty'), 400
        ref, session = open_session(uid)

    cart = dict(session['cart'])
    qty = min(cart.get(product['id'], {}).get('qty', 0) + delta, MAX_QTY)
    if qty > 0:
        cart[product['id']] = {'name': product['name'], 'price': product['price'], 'qty': qty}
    else:
        cart.pop(product['id'], None)
    log_event(ref, session, 'add_item' if delta > 0 else 'remove_item', cart=cart)
    return jsonify(count=cart_count(cart), subtotal=subtotal(cart), qty=max(qty, 0))


@bp.post('/api/session/events')
@require_user
def api_event():
    """Body {type, step}: behaviour events from track.js. Ignored when no checkout session is open."""
    body = json_body()
    kind, step = body.get('type'), body.get('step')
    if kind not in CLIENT_EVENTS or step not in STEPS:
        return jsonify(error='bad event'), 400
    ref, session = get_open(current_user()['uid'])
    if session is None:
        return '', 204
    changes = {'payment_entered_at': now()} if (kind, step) == ('step_enter', 'payment') else {}
    log_event(ref, session, kind, **changes)
    return '', 204


@bp.post('/api/address')
@require_user
def api_address():
    """Body {lat, lng}: quote distance + fee. Coordinates are not stored on the session."""
    ref, session = get_open(current_user()['uid'])
    if session is None:
        return jsonify(error='cart is empty'), 400
    body = json_body()
    try:
        km, fee = quote(get_settings(), body.get('lat'), body.get('lng'))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    log_event(ref, session, 'set_address', distance_km=km, fee=fee)
    return jsonify(km=km, fee=fee)


@bp.post('/api/orders')
@require_user
def api_place_order():
    """Body {payment_method, lat, lng}: place the order and close the session as paid."""
    uid = current_user()['uid']
    ref, session = get_open(uid)
    if not session or not session['cart']:
        return jsonify(error='cart is empty'), 400
    body = json_body()
    method = body.get('payment_method')
    if method not in PAYMENT_METHODS:
        return jsonify(error='choose a payment method'), 400
    try:
        km, fee = quote(get_settings(), body.get('lat'), body.get('lng'))
    except ValueError as e:
        return jsonify(error=str(e)), 400

    # Prices come from Firestore, never from the client or the cart snapshot.
    items = []
    for pid, line in session['cart'].items():
        product = get_product(pid)
        if not product or product.get('hidden'):
            return jsonify(error=f'{line["name"]} is no longer available, please update your cart'), 409
        items.append({'product_id': pid, 'name': product['name'], 'price': product['price'], 'qty': line['qty']})
    sub = sum(i['price'] * i['qty'] for i in items)

    t = now()
    order_ref = db.collection('orders').document()
    order_ref.set({'uid': uid, 'session_id': ref.id, 'items': items, 'subtotal': sub, 'fee': fee,
                   'total': sub + fee, 'distance_km': km, 'payment_method': method,
                   'lat': float(body['lat']), 'lng': float(body['lng']),
                   'status': 'new', 'created_at': t, 'updated_at': t})
    session.update(distance_km=km, fee=fee, cart={i['product_id']: i for i in items})
    close(ref, session, 'paid', t, order_id=order_ref.id, distance_km=km, fee=fee)
    return jsonify(order_id=order_ref.id), 201


@bp.get('/api/orders/<order_id>')
@require_user
def api_order(order_id):
    o = _own_order(order_id)
    return jsonify(status=o['status'])
