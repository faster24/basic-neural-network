// Delivery pin on an OpenStreetMap/Leaflet map. The server computes distance and fee.
import { post } from './api.js';

const el = document.getElementById('map');
const store = [Number(el.dataset.storeLat), Number(el.dataset.storeLng)];
const quote = document.getElementById('quote');
const next = document.getElementById('to-payment');

const map = L.map(el).setView(store, 13);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);
L.circleMarker(store, { radius: 7, color: '#c2410c' }).addTo(map).bindTooltip('Store');
L.circle(store, { radius: Number(el.dataset.maxKm) * 1000, color: '#c2410c', weight: 1, fillOpacity: 0.04 }).addTo(map);

let saved = null;
try { saved = JSON.parse(sessionStorage.getItem('deliveryPin')); } catch { /* none */ }
const marker = L.marker(saved || store, { draggable: true }).addTo(map);

function setNext(enabled) {
  next.classList.toggle('disabled', !enabled);
  next.setAttribute('aria-disabled', String(!enabled));
}
next.addEventListener('click', (e) => { if (next.classList.contains('disabled')) e.preventDefault(); });

let seq = 0;
async function update(latlng) {
  const mine = ++seq;
  setNext(false);
  quote.textContent = 'Checking distance…';
  try {
    const res = await post('/api/address', { lat: latlng.lat, lng: latlng.lng });
    if (mine !== seq) return;
    quote.textContent = `${res.km.toFixed(1)} km away · delivery fee ฿${res.fee}`;
    try { sessionStorage.setItem('deliveryPin', JSON.stringify({ lat: latlng.lat, lng: latlng.lng })); } catch { /* ignore */ }
    setNext(true);
  } catch (err) {
    if (mine === seq) quote.textContent = err.message;
  }
}

marker.on('dragend', () => update(marker.getLatLng()));
map.on('click', (e) => { marker.setLatLng(e.latlng); update(e.latlng); });

if (saved) {
  map.setView(saved, 15);
  update(marker.getLatLng());
} else if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const here = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      marker.setLatLng(here);
      map.setView(here, 15);
      update(here);
    },
    () => { quote.textContent = 'Location not available — drag the pin to your address.'; },
    { timeout: 8000 },
  );
}
