const btnToggleCategoria = document.getElementById('btn-toggle-categoria');
const menuCategorias = document.getElementById('menu-categorias');
const textoCategoria = document.getElementById('texto-categoria');
const flechaCategoria = document.getElementById('flecha-categoria');
const inputFiltroCategoria = document.getElementById('filtro-categoria');

// Abrir o cerrar el desplegable de categorías
btnToggleCategoria.addEventListener('click', () => {
  const estaOculto = menuCategorias.classList.toggle('oculto');
  flechaCategoria.textContent = estaOculto ? '▼' : '▲';
});

// Seleccionar una o varias categorías.
// Los botones se crean desde la API después de cargar la página,
// así que escuchamos los clics en el menú (delegación) y no en cada botón.
menuCategorias.addEventListener('click', (ev) => {
  const boton = ev.target.closest('.btn-opcion-cat');
  if (!boton) return;

  const botonTodas = menuCategorias.querySelector('.btn-opcion-cat[data-valor=""]');

  if (boton === botonTodas) {
    // "Todas" quita el resto de categorías
    menuCategorias.querySelectorAll('.btn-opcion-cat').forEach((b) => b.classList.remove('activo'));
  } else {
    boton.classList.toggle('activo');
  }

  const elegidas = [...menuCategorias.querySelectorAll('.btn-opcion-cat.activo')]
    .filter((b) => b.dataset.valor);

  // Si no queda ninguna elegida, vuelve a "Todas"
  botonTodas.classList.toggle('activo', elegidas.length === 0);

  if (elegidas.length === 0) textoCategoria.textContent = 'Todas';
  else if (elegidas.length === 1) textoCategoria.textContent = elegidas[0].dataset.nombre;
  else textoCategoria.textContent = `${elegidas.length} categorías`;

  // El backend acepta varias separadas por coma: "musica,teatro"
  inputFiltroCategoria.value = elegidas.map((b) => b.dataset.valor).join(',');

  // Avisar a script_backend.js de que el filtro ha cambiado para que busque de nuevo
  inputFiltroCategoria.dispatchEvent(new Event('input'));

  // "Todas" cierra el menú; las demás lo dejan abierto para poder elegir varias
  if (boton === botonTodas) {
    menuCategorias.classList.add('oculto');
    flechaCategoria.textContent = '▼';
  }
});

const IMAGENES_CATEGORIA = {
  cursos_talleres: "img/cursos.png",
  musica: "img/musica.png",
  teatro: "img/espectaculos.png",
  cine: "img/espectaculos.png",
  danza: "img/musica.png",
  deporte: "img/deportes.png",
  infantil: "img/infantil.png",
  conferencias: "img/conferencias.png",
  exposicion: "img/exposicion.png",
  fiestas: "img/fiestas.png",
  literatura: "img/literatura.png",
  club_lectura: "img/literatura.png",
  visitas: "img/visitas.png",
  aire_libre: "img/medio ambiente.png",
  otros: "img/otros.png",
  default: "img/otros.png"
};

function obtenerImagenActividad(e) {
  return IMAGENES_CATEGORIA[e.grupo] || IMAGENES_CATEGORIA.default;
}