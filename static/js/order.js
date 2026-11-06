// Order status tracker; polls every 10 s until delivered or cancelled.
const track = document.getElementById('status-track');
const order = track.dataset.orderId;
const steps = [...track.querySelectorAll('li')];

function render(status) {
  const idx = steps.findIndex((li) => li.dataset.status === status);
  steps.forEach((li, i) => {
    li.classList.toggle('done', idx >= 0 && i <= idx);
    li.toggleAttribute('aria-current', i === idx);
  });
  document.getElementById('cancelled-msg').hidden = status !== 'cancelled';
}

async function poll() {
  try {
    const res = await fetch(`/api/orders/${order}`);
    if (res.ok) {
      const { status } = await res.json();
      render(status);
      if (status === 'delivered' || status === 'cancelled') return;
    }
  } catch { /* offline: try again */ }
  setTimeout(poll, 10000);
}

render(track.dataset.status);
setTimeout(poll, 10000);
