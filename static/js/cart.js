// "Add" buttons on the menu and +/- buttons in the cart.
import { post } from './api.js';

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.add-to-cart, .qty-btn');
  if (!btn) return;
  btn.disabled = true;
  try {
    const delta = Number(btn.dataset.delta || 1);
    const res = await post('/api/cart', { product_id: btn.dataset.productId, delta });
    const badge = document.getElementById('cart-count');
    badge.textContent = res.count;
    badge.hidden = res.count === 0;
    if (btn.classList.contains('qty-btn')) {
      dispatchEvent(new Event('app:navigating'));
      location.reload();
    } else {
      btn.textContent = `Added (${res.qty})`;
    }
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
  }
});
