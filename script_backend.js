// ================== CONFIGURACIÓN ==================
const API = "http://127.0.0.1:8000";
const POR_PAGINA = 40;
const SOL = { lat: 40.4168, lon: -3.7038 }; // Puerta del Sol, si no hay geolocalización

// ================== ELEMENTOS ==================
const btnAbrir = document.getElementById('btn-abrir-filtros');
const panelFiltros = document.getElementById('panel-filtros');
const iconoFlecha = document.getElementById('icono-flecha');
const btnAplicar = document.getElementById('btn-aplicar');
const btnMas = document.getElementById('btn-mas');
const lista = document.getElementById('lista-eventos');
const avisoSinResultados = document.getElementById('sin-resultados');

const selCategoria = document.getElementById('filtro-categoria');
const inputHora = document.getElementById('filtro-hora');
const inputPrecio = document.getElementById('filtro-precio');
const inputDistancia = document.getElementById('filtro-distancia');
const inputDuracion = document.getElementById('filtro-duracion');

// ================== ESTADO ==================
let ubicacion = SOL;
let resultados = [];   // eventos que cumplen los filtros
let mostrados = 0;     // cuántos se han pintado
let temporizador;

// ================== UTILIDADES ==================
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (n) => String(n).replace('.', ','); // 1.8 -> "1,8"

function distanciaKm(lat1, lon1, lat2, lon2) {   // fórmula de Haversine
  const R = 6371, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function formatoFecha(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('es-ES',
    { weekday: 'short', day: 'numeric', month: 'short' });
}

function textoFecha(e) {
  const hora = e.hora_inicio ? ` · ${e.hora_inicio}` : '';
  if (e.estado === 'en_curso') {
    return `En curso · hasta ${formatoFecha(e.fecha_fin)}`;
  }
  return `${formatoFecha(e.fecha_inicio)}${hora}`;
}

function textoDuracion(min) {
  if (min < 60) return `${min} min`;
  return `${num(Math.round((min / 60) * 10) / 10)} h`;
}

// ================== PANEL: abrir/cerrar ==================
function cerrarPanel() {
  panelFiltros.classList.add('oculto');
  btnAbrir.classList.remove('activo');
  iconoFlecha.textContent = '▼';
}

btnAbrir.addEventListener('click', () => {
  const estaOculto = panelFiltros.classList.toggle('oculto');
  btnAbrir.classList.toggle('activo', !estaOculto);
  iconoFlecha.textContent = estaOculto ? '▼' : '▲';
});

btnAplicar.addEventListener('click', cerrarPanel);

// ================== TEXTOS de los sliders ==================
inputPrecio.addEventListener('input', () => {
  const v = Number(inputPrecio.value);
  document.getElementById('valor-precio').textContent =
    v === Number(inputPrecio.max) ? 'Cualquiera' : v === 0 ? 'Gratis' : `${v} €`;
});
inputDistancia.addEventListener('input', () => {
  const v = Number(inputDistancia.value);
  document.getElementById('valor-distancia').textContent =
    v === Number(inputDistancia.max) ? 'Cualquiera' : `${v} km`;
});
inputDuracion.addEventListener('input', () => {
  const v = Number(inputDuracion.value);
  document.getElementById('valor-duracion').textContent =
    v === Number(inputDuracion.max) ? 'Cualquiera' : `${num(v)} h`;
});

// Cualquier cambio de filtro -> buscar (con pequeña espera para no saturar)
[selCategoria, inputHora, inputPrecio, inputDistancia, inputDuracion].forEach(el => {
  el.addEventListener('input', () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(buscar, 250);
  });
});

// ================== API ==================
async function cargarCategorias() {
  try {
    const res = await fetch(`${API}/api/categorias`);
    const cats = await res.json();
    // Un botón por categoría dentro del desplegable (script.js gestiona los clics)
    const menu = document.getElementById('menu-categorias');
    cats.forEach(c => menu.insertAdjacentHTML('beforeend',
      `<button type="button" class="btn-opcion-cat" data-valor="${esc(c.id)}" data-nombre="${esc(c.nombre)}">` +
      `${esc(c.nombre)} (${c.total})</button>`));
  } catch (err) {
    console.error('No se pudieron cargar las categorías', err);
  }
}

async function buscar() {
  const params = new URLSearchParams();

  // Una o varias categorías separadas por coma: "musica,teatro"
  if (selCategoria.value) params.set('categoria', selCategoria.value);
  if (inputHora.value) params.set('inicio_desde', inputHora.value);

  // Solo se envía el límite si el slider NO está al máximo (= "Cualquiera").
  // Así no se descartan eventos sin precio/duración conocidos.
  if (Number(inputPrecio.value) < Number(inputPrecio.max))
    params.set('precio_max', inputPrecio.value);
  if (Number(inputDuracion.value) < Number(inputDuracion.max))
    params.set('duracion_max', Math.round(Number(inputDuracion.value) * 60)); // h -> min

  let eventos;
  try {
    const res = await fetch(`${API}/api/eventos?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    eventos = (await res.json()).eventos;
  } catch (err) {
    console.error(err);
    lista.querySelectorAll('.tarjeta').forEach(t => t.remove());
    avisoSinResultados.querySelector('p').textContent =
      'No se pudo conectar con el servidor. ¿Está encendido?';
    avisoSinResultados.classList.remove('oculto');
    btnMas.classList.add('oculto');
    return;
  }

  // Calcular distancia (solo 450 de 1610 eventos tienen coordenadas)
  eventos.forEach(e => {
    e.distancia = (e.lat != null && e.lon != null)
      ? distanciaKm(ubicacion.lat, ubicacion.lon, e.lat, e.lon)
      : null;
  });

  // El filtro de distancia se aplica aquí, solo si no está al máximo
  if (Number(inputDistancia.value) < Number(inputDistancia.max)) {
    const max = Number(inputDistancia.value);
    eventos = eventos.filter(e => e.distancia !== null && e.distancia <= max);
    eventos.sort((a, b) => a.distancia - b.distancia);
  }

  resultados = eventos;
  mostrados = 0;
  lista.querySelectorAll('.tarjeta').forEach(t => t.remove());
  avisoSinResultados.querySelector('p').textContent = 'No hay eventos con esos filtros.';
  avisoSinResultados.classList.toggle('oculto', resultados.length > 0);

  btnAplicar.textContent =
    `Ver ${resultados.length} ${resultados.length === 1 ? 'evento' : 'eventos'}`;

  pintarMas();
}

// ================== PINTAR TARJETAS ==================
function tarjetaHTML(e) {
  const precio = e.gratis ? 'Gratis' : (e.precio != null ? `${num(e.precio)} €` : 'Consultar precio');
  const km = e.distancia != null ? `<span class="dato">${num(e.distancia.toFixed(1))} km</span>` : '';
  const lugar = [e.lugar_nombre, e.distrito].filter(Boolean).join(' · ');
  const enlace = e.url
    ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">Más información</a>` : '';
  const imagen = obtenerImagenActividad(e);

  return `
        <article class="tarjeta" data-color="${esc(e.color || '')}">
          <div class="tarjeta-info">
            <p class="fecha">${esc(textoFecha(e))}</p>
            <h2>${esc(e.titulo)}</h2>
            <p class="lugar">${esc(lugar)}</p>
            <div class="detalles">
              <span class="dato">${esc(e.grupo_nombre)}</span>
              <span class="dato">${esc(precio)}</span>
              ${km}
              <span class="dato">${esc(textoDuracion(e.duracion_min))}</span>
            </div>
            ${enlace}
          </div>
          <img class="tarjeta-img" src="${esc(imagen)}" alt="${esc(e.grupo_nombre || 'Evento')}" loading="lazy">
        </article>`;
}

function pintarMas() {
  const trozo = resultados.slice(mostrados, mostrados + POR_PAGINA);
  avisoSinResultados.insertAdjacentHTML('beforebegin', trozo.map(tarjetaHTML).join(''));
  mostrados += trozo.length;
  btnMas.classList.toggle('oculto', mostrados >= resultados.length);
}

btnMas.addEventListener('click', pintarMas);

// ================== ARRANQUE ==================
function obtenerUbicacion() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve();
    navigator.geolocation.getCurrentPosition(
      (pos) => { ubicacion = { lat: pos.coords.latitude, lon: pos.coords.longitude }; resolve(); },
      () => resolve(),               // si la deniega, se usa la Puerta del Sol
      { timeout: 4000 }
    );
  });
}

(async () => {
  cargarCategorias();
  await obtenerUbicacion();
  buscar();
})();