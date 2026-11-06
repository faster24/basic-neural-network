"""Firebase ID-token auth. The browser (static/js/auth.js) keeps a fresh token in the __session cookie.

The cookie is SameSite=Strict, which is what protects the form/JSON POSTs from CSRF.
"""
import json
import os
from functools import wraps

import firebase_admin
from firebase_admin import auth as fb_auth
from flask import g, jsonify, render_template, request

import connect  # noqa: F401  (initializes the default firebase_admin app, used for Firestore)

# Sign-in can live in a different Firebase project than Firestore. Tokens are checked against the
# project in firebase-web.json; verifying only needs the project id (Google's public certs, no secret).
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firebase-web.json')) as _f:
    AUTH_PROJECT = json.load(_f)['projectId']
AUTH_APP = firebase_admin.initialize_app(firebase_admin.get_app().credential,
                                         {'projectId': AUTH_PROJECT}, name='web-auth')

ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}


def current_user():
    """Verified user dict {uid, email, anonymous} or None. Cached per request."""
    if 'user' not in g:
        g.user = None
        token = request.cookies.get('__session') or request.headers.get('Authorization', '').removeprefix('Bearer ')
        if token:
            try:
                claims = fb_auth.verify_id_token(token, app=AUTH_APP, clock_skew_seconds=10)
                g.user = {
                    'uid': claims['uid'],
                    'email': (claims.get('email') or '').lower(),
                    'anonymous': claims.get('firebase', {}).get('sign_in_provider') == 'anonymous',
                }
            except (ValueError, fb_auth.InvalidIdTokenError, fb_auth.ExpiredIdTokenError,
                    fb_auth.RevokedIdTokenError, fb_auth.CertificateFetchError):
                g.user = None
    return g.user


def is_admin(user):
    return bool(user and not user['anonymous'] and user['email'] in ADMIN_EMAILS)


def require_user(view):
    """Pages: render a 'signing in' shell that reloads once auth.js has a token. /api: 401."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        if request.path.startswith('/api/'):
            return jsonify(error='not signed in'), 401
        return render_template('signing_in.html', needs_auth=True), 401
    return wrapper


def require_admin(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if is_admin(user):
            return view(*args, **kwargs)
        if user is None:
            return render_template('signing_in.html', needs_auth=True), 401
        return render_template('admin/login.html', user=user), 403
    return wrapper
