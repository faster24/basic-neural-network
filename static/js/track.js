// Behaviour tracking for x5 (payment dwell) and x6 (back/exit hesitation).
// The server ignores events when the shopper has no open cart session.
import { beacon } from './api.js';

const step = document.body.dataset.step;
const send = (type) => beacon('/api/session/events', { type, step });

if (step && document.body.dataset.needsAuth !== '1') {
  const nav = performance.getEntriesByType('navigation')[0];
  if (nav?.type === 'back_forward') send('back');
  send('step_enter');

  // Page restored from the back/forward cache: also a back navigation.
  addEventListener('pageshow', (e) => { if (e.persisted) { send('back'); send('step_enter'); } });

  // Tab/app switch away. Skip hides caused by our own navigation (links, or scripts that fire app:navigating).
  let leaving = false;
  addEventListener('click', (e) => { if (e.target.closest('a[href]')) leaving = true; });
  addEventListener('app:navigating', () => { leaving = true; });
  addEventListener('pagehide', () => { leaving = true; });
  addEventListener('pageshow', () => { leaving = false; });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && !leaving) send('tab_hidden');
  });

  // In-page "← back" buttons between checkout steps.
  document.querySelectorAll('.step-back').forEach((a) => a.addEventListener('click', () => send('back')));
}

// Privacy notice, shown until acknowledged on this device.
const banner = document.getElementById('privacy-banner');
if (banner) {
  let seen = false;
  try { seen = localStorage.getItem('privacyAck') === '1'; } catch { /* storage blocked */ }
  banner.hidden = seen;
  document.getElementById('privacy-ok')?.addEventListener('click', () => {
    banner.hidden = true;
    try { localStorage.setItem('privacyAck', '1'); } catch { /* ignore */ }
  });
}
