// Firebase Auth: every visitor gets an anonymous account; Google sign-in upgrades it (keeps the uid).
// The ID token is mirrored into the __session cookie, which the Flask server verifies.
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js';
import {
  getAuth, onIdTokenChanged, signInAnonymously, signInWithPopup, linkWithPopup,
  GoogleAuthProvider, signOut,
} from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js';

const config = JSON.parse(document.getElementById('firebase-config').textContent);
const auth = getAuth(initializeApp(config));
const provider = new GoogleAuthProvider();
const needsAuth = document.body.dataset.needsAuth === '1';

function setCookie(token) {
  // SameSite=Strict keeps other sites from sending authenticated POSTs (CSRF).
  document.cookie = token
    ? `__session=${token}; path=/; max-age=3600; SameSite=Strict`
    : '__session=; path=/; max-age=0; SameSite=Strict';
}

function reloadOnce() {
  // Server rendered a "signing in" shell; reload once now that the cookie is set (never loop).
  try {
    if (sessionStorage.getItem('authReloaded')) return;
    sessionStorage.setItem('authReloaded', '1');
  } catch { /* storage blocked: reload anyway */ }
  location.reload();
}

onIdTokenChanged(auth, async (user) => {
  if (!user) {
    setCookie('');
    if (!document.body.classList.contains('admin')) await signInAnonymously(auth);
    return;
  }
  setCookie(await user.getIdToken());
  if (needsAuth) reloadOnce();
  else try { sessionStorage.removeItem('authReloaded'); } catch { /* ignore */ }

  const btn = document.getElementById('google-signin');
  const email = document.getElementById('user-email');
  if (btn && !document.body.classList.contains('admin')) btn.hidden = !user.isAnonymous;
  if (email && !user.isAnonymous) { email.textContent = user.email; email.hidden = false; }
  const hint = document.getElementById('history-hint');
  if (hint) hint.hidden = !user.isAnonymous;
});

document.getElementById('google-signin')?.addEventListener('click', async () => {
  try {
    if (auth.currentUser?.isAnonymous) {
      try {
        await linkWithPopup(auth.currentUser, provider);
      } catch (e) {
        // This Google account already has its own uid: switch to it (the anonymous cart stays behind).
        if (e.code !== 'auth/credential-already-in-use') throw e;
        await signInWithPopup(auth, provider);
      }
    } else {
      await signInWithPopup(auth, provider);
    }
    setCookie(await auth.currentUser.getIdToken(true));
    location.reload();
  } catch (e) {
    if (e.code !== 'auth/popup-closed-by-user') alert(`Sign-in failed: ${e.message}`);
  }
});

document.getElementById('sign-out')?.addEventListener('click', async () => {
  await signOut(auth);
  setCookie('');
  location.href = '/';
});
