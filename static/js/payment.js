// Payment step. Card/wallet are simulated: their fields are checked locally and never sent.
import { post } from './api.js';

const form = document.getElementById('pay-form');
const err = document.getElementById('pay-error');
const btn = document.getElementById('place-order');
const panels = { card: document.getElementById('card-fields'), wallet: document.getElementById('wallet-fields') };

function method() {
  return form.querySelector('input[name=payment_method]:checked').value;
}
function showPanel() {
  for (const [k, p] of Object.entries(panels)) p.hidden = k !== method();
}
form.addEventListener('change', showPanel);
showPanel();

function simulatedCheck(m) {
  const digits = (id) => document.getElementById(id).value.replace(/\D/g, '');
  if (m === 'card') {
    if (digits('card-number').length < 12) return 'Enter a card number (any 12+ digits, demo only).';
    if (!/^\d{2}\/\d{2}$/.test(document.getElementById('card-exp').value.trim())) return 'Expiry must be MM/YY.';
    if (digits('card-cvc').length < 3) return 'Enter a 3-digit CVC.';
  }
  if (m === 'wallet' && digits('wallet-phone').length < 9) return 'Enter your e-wallet phone number.';
  return null;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  err.hidden = true;
  const m = method();
  const problem = simulatedCheck(m);
  let pin = null;
  try { pin = JSON.parse(sessionStorage.getItem('deliveryPin')); } catch { /* none */ }
  const fail = (msg) => { err.textContent = msg; err.hidden = false; };
  if (problem) return fail(problem);
  if (!pin) return fail('Delivery location missing — go back and set your address.');

  btn.disabled = true;
  try {
    const res = await post('/api/orders', { payment_method: m, lat: pin.lat, lng: pin.lng });
    try { sessionStorage.removeItem('deliveryPin'); } catch { /* ignore */ }
    dispatchEvent(new Event('app:navigating'));
    location.href = `/orders/${res.order_id}`;
  } catch (ex) {
    fail(ex.message);
    btn.disabled = false;
  }
});
