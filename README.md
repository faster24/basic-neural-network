# Cart-abandonment delivery shop (MVP)

Single-store, mobile-first delivery shop. Every checkout records the 6 model inputs
(late-night time, cart value, delivery fee, distance, payment dwell time, back/exit hesitation),
scores them with the network in `model.py` (see `network.jpg`), and labels the session paid or abandoned.

## Setup (once)
1. Firebase console → Project settings → Your apps → add a **Web app**. Copy its config into
   `firebase-web.json` (template: `firebase-web.example.json`).
2. Authentication → Sign-in method: enable **Anonymous** and **Google**. Check `localhost` is an authorized domain.
3. Keep the service-account key at `firebase-cred.json` (gitignored).
4. `uv pip install --python .venv/bin/python -r requirements.txt`
5. `.venv/bin/python seed.py`: creates store settings, model v1 and a demo menu (re-runnable).

## Run
```sh
ADMIN_EMAILS=you@gmail.com .venv/bin/flask --app app run
```
- Shop: http://localhost:5000 (use `localhost`: map location and sign-in need it or HTTPS)
- Admin: http://localhost:5000/admin (sign in with a Google account listed in `ADMIN_EMAILS`)
- Close idle carts now: `.venv/bin/flask --app app close-stale` (also runs automatically, at most once a minute, on `/api` and `/admin` requests)

## Test
`.venv/bin/python -m pytest`

## Where things are
| File | What |
|---|---|
| `model.py` | Network, input measurement and normalization (pure, unit-tested) |
| `sessions.py` | Checkout session lifecycle in Firestore, `close_stale` |
| `shop.py` / `admin.py` | Customer and admin pages + JSON API |
| `forcing_terms.py` | Original `/forcing_terms` REST API (unchanged behaviour) |
| `static/js/track.js` | Records back / tab-switch / step events |
