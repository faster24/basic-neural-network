import json
import os

from flask import Flask, Request, request
from flask_restful import Api

import admin
import forcing_terms
import shop
from model import TZ
from sessions import close_stale, close_stale_throttled

BASE = os.path.dirname(os.path.abspath(__file__))


# Werkzeug >= 2.1 raises 415 when request.json is read on a non-JSON request,
# which breaks reqparse's default ('json', 'values') lookup for form data.
# Return None instead so reqparse falls through to form/query values.
class LenientJSONRequest(Request):
    def on_json_loading_failed(self, e):
        if e is None:
            return None
        return super().on_json_loading_failed(e)


app = Flask(__name__)
app.request_class = LenientJSONRequest
# shortcut: random key means flash messages reset on restart; set SECRET_KEY when hosted.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)

# Firebase *web* config (public, not a secret). Copy it from Firebase console -> Project settings -> Your apps.
with open(os.path.join(BASE, 'firebase-web.json')) as f:
    FIREBASE_WEB_CONFIG = json.load(f)

api = Api(app)
forcing_terms.register(api)
app.register_blueprint(shop.bp)
app.register_blueprint(admin.bp)


@app.context_processor
def inject_firebase():
    return {'firebase_config': FIREBASE_WEB_CONFIG}


@app.template_filter('local')
def local_time(dt, fmt='%d %b %Y %H:%M'):
    """Firestore timestamps are UTC; show them in the store's time zone."""
    return dt.astimezone(TZ).strftime(fmt) if dt else ''


@app.before_request
def lazy_close_stale():
    if request.path.startswith(('/api/', '/admin')):
        close_stale_throttled()


@app.cli.command('close-stale')
def close_stale_command():
    """Mark idle checkout sessions as abandoned."""
    print(f'closed {close_stale()} session(s)')


if __name__ == '__main__':
    # Open the shop at http://localhost:5000: geolocation and Firebase sign-in need localhost or HTTPS.
    app.run(host='0.0.0.0', port=5000)
