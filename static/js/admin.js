// Analytics charts (Chart.js loaded from CDN before this file).
const data = JSON.parse(document.getElementById('chart-data').textContent);
const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#c2410c';
const ink = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#666';

function line(id, values, max) {
  new Chart(document.getElementById(id), {
    type: 'line',
    data: { labels: data.labels, datasets: [{ data: values, borderColor: accent, backgroundColor: accent, tension: 0.2 }] },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { min: 0, max, ticks: { color: ink } }, x: { ticks: { color: ink } } },
    },
  });
}
line('rate-chart', data.abandon_rate, 100);
line('score-chart', data.avg_score, undefined);
