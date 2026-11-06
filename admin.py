"""Admin pages: orders, menu, store settings, model weights, abandonment analytics, CSV export."""
import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from google.cloud.firestore_v1.base_query import FieldFilter

from auth import require_admin
from connect import db
from data import (create_model_version, get_model, get_product, get_settings, list_model_versions,
                  list_products, now, save_product, save_settings)
from model import INPUT_NAMES, TZ
from sessions import close_stale
from shop import ORDER_STATUSES, PAYMENT_METHODS

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.get('/')
@require_admin
def index():
    return redirect(url_for('admin.orders'))


# ---------- orders ----------

@bp.get('/orders')
@require_admin
def orders():
    show = request.args.get('show', 'active')
    docs = db.collection('orders').order_by('created_at', direction='DESCENDING').limit(200).stream()
    items = [{'id': d.id, **d.to_dict()} for d in docs]
    if show == 'active':
        items = [o for o in items if o['status'] not in ('delivered', 'cancelled')]
    return render_template('admin/orders.html', orders=items, statuses=ORDER_STATUSES, show=show,
                           methods=PAYMENT_METHODS)


@bp.post('/orders/<order_id>/status')
@require_admin
def set_status(order_id):
    status = request.form.get('status')
    if status not in ORDER_STATUSES:
        flash('Unknown status')
    else:
        db.collection('orders').document(order_id).update({'status': status, 'updated_at': now()})
    return redirect(url_for('admin.orders', show=request.args.get('show', 'active')))


# ---------- menu ----------

@bp.get('/products')
@require_admin
def products():
    return render_template('admin/products.html', products=list_products(include_hidden=True))


@bp.route('/products/new', methods=['GET', 'POST'], defaults={'pid': None})
@bp.route('/products/<pid>', methods=['GET', 'POST'])
@require_admin
def edit_product(pid):
    product = get_product(pid) if pid else {}
    if pid and product is None:
        return redirect(url_for('admin.products'))
    if request.method == 'POST':
        f = request.form
        try:
            price = float(f['price'])
            if price < 0:
                raise ValueError
        except (KeyError, ValueError):
            flash('Price must be a non-negative number')
            return render_template('admin/product_form.html', product={**product, **f.to_dict()}), 400
        name = f.get('name', '').strip()
        if not name:
            flash('Name is required')
            return render_template('admin/product_form.html', product={**product, **f.to_dict()}), 400
        save_product(pid, {
            'name': name,
            'description': f.get('description', '').strip(),
            'category': f.get('category', '').strip() or 'Other',
            'price': price,
            'image_url': f.get('image_url', '').strip(),
            'hidden': f.get('hidden') == 'on',
        })
        flash(f'Saved {name}')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', product=product)


# ---------- settings + model ----------

def _parse_tiers(text):
    """'3:20, 7:40, 15:60' -> [[3, 20], [7, 40], [15, 60]] (ascending km)."""
    tiers = []
    for part in text.split(','):
        km, fee = part.split(':')
        tiers.append([float(km), float(fee)])
    if not tiers or any(k <= 0 or f < 0 for k, f in tiers) or tiers != sorted(tiers):
        raise ValueError
    return tiers


@bp.route('/settings', methods=['GET', 'POST'])
@require_admin
def settings():
    s = get_settings()
    if request.method == 'POST':
        f = request.form
        try:
            new = {
                **s,
                'name': f['name'].strip() or s['name'],
                'hours': f['hours'].strip(),
                'lat': float(f['lat']),
                'lng': float(f['lng']),
                'fee_tiers': _parse_tiers(f['fee_tiers']),
                'abandon_minutes': int(f['abandon_minutes']),
                'caps': {n: float(f[f'cap_{n}']) for n in INPUT_NAMES[1:]},
            }
            if new['abandon_minutes'] < 1 or any(v <= 0 for v in new['caps'].values()):
                raise ValueError
        except (KeyError, ValueError):
            flash('Invalid value: check tiers (km:fee, ascending), numbers, caps > 0, timeout >= 1')
            return render_template('admin/settings.html', s=s, inputs=INPUT_NAMES), 400
        save_settings(new)
        flash('Settings saved')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', s=s, inputs=INPUT_NAMES)


@bp.route('/model', methods=['GET', 'POST'])
@require_admin
def model():
    active = get_settings()['active_model']
    weights = get_model(active)
    if request.method == 'POST':
        f = request.form
        try:
            new = {
                'W1': [[float(f[f'w_{r}_{c}']) for c in range(6)] for r in range(2)],
                **{k: float(f[k]) for k in ('omega', 'wH1', 'wH2', 'eta')},
            }
            if any(sum(row) == 0 for row in new['W1']):
                raise ValueError
        except (KeyError, ValueError):
            flash('All weights must be numbers, and each W1 row must not sum to 0')
            return render_template('admin/model.html', m=weights, active=active,
                                   versions=list_model_versions(), inputs=INPUT_NAMES), 400
        version = create_model_version(new)
        flash(f'Saved as {version}; new sessions are scored with it')
        return redirect(url_for('admin.model'))
    return render_template('admin/model.html', m=weights, active=active,
                           versions=list_model_versions(), inputs=INPUT_NAMES)


# ---------- analytics + export ----------

def _closed_sessions():
    """Closed sessions in the ?from/?to date range (Bangkok dates), newest first; ?complete=1 drops incomplete."""
    today = datetime.now(TZ).date()
    try:
        start = datetime.fromisoformat(request.args.get('from') or str(today - timedelta(days=29))).date()
        end = datetime.fromisoformat(request.args.get('to') or str(today)).date()
    except ValueError:
        start, end = today - timedelta(days=29), today
    lo = datetime.combine(start, datetime.min.time(), TZ)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), TZ)
    docs = (db.collection('sessions')
            .where(filter=FieldFilter('started_at', '>=', lo))
            .where(filter=FieldFilter('started_at', '<', hi)).stream())
    rows = [{'id': d.id, **d.to_dict()} for d in docs]
    rows = [r for r in rows if r['status'] != 'open']
    if request.args.get('complete') == '1':
        rows = [r for r in rows if not r.get('incomplete')]
    rows.sort(key=lambda r: r['started_at'], reverse=True)
    return rows, start, end


@bp.get('/analytics')
@require_admin
def analytics():
    close_stale()
    rows, start, end = _closed_sessions()
    daily = defaultdict(lambda: {'total': 0, 'abandoned': 0, 'score': 0.0})
    for r in rows:
        d = daily[r['started_at'].astimezone(TZ).date().isoformat()]
        d['total'] += 1
        d['abandoned'] += r['status'] == 'abandoned'
        d['score'] += r.get('score', 0)
    days = sorted(daily)
    chart = {
        'labels': days,
        'abandon_rate': [round(daily[d]['abandoned'] / daily[d]['total'] * 100, 1) for d in days],
        'avg_score': [round(daily[d]['score'] / daily[d]['total'], 3) for d in days],
    }
    total = len(rows)
    summary = {
        'total': total,
        'abandoned': sum(r['status'] == 'abandoned' for r in rows),
        'avg_score': sum(r.get('score', 0) for r in rows) / total if total else 0,
    }
    return render_template('admin/analytics.html', rows=rows[:300], chart=chart, summary=summary,
                           start=start, end=end, complete=request.args.get('complete') == '1',
                           inputs=INPUT_NAMES, tz=TZ)


@bp.get('/export.csv')
@require_admin
def export_csv():
    rows, start, end = _closed_sessions()
    raw_cols = [f'raw_{n}' for n in INPUT_NAMES]
    x_cols = [f'x{i + 1}_{n}' for i, n in enumerate(INPUT_NAMES)]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['session_id', 'started_at', 'outcome', 'score', 'model_version', 'incomplete', 'order_id',
                *raw_cols, *x_cols])
    for r in rows:
        raw, x = r.get('raw', {}), r.get('inputs', {})
        w.writerow([r['id'], r['started_at'].astimezone(TZ).isoformat(), r['status'], r.get('score'),
                    r.get('model_version'), r.get('incomplete'), r.get('order_id', ''),
                    *[raw.get(n) for n in INPUT_NAMES], *[x.get(n) for n in INPUT_NAMES]])
    name = f'sessions_{start}_{end}.csv'
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={name}'})
