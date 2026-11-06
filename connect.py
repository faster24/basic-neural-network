import os

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# Use a service account. Path is relative to this file so the app can start from any folder.
if not firebase_admin._apps:
    cred = credentials.Certificate(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firebase-cred.json'))
    app = firebase_admin.initialize_app(cred)

db = firestore.client()
