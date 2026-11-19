const params = new URLSearchParams({ categoria: "musica", precio_max: 20 });
    const res = await fetch(`http://127.0.0.1:8000/api/eventos?${params}`);
    const { total, eventos } = await res.json();
    const btnAbrir = document.getElementById('btn-abrir-filtros');
    const panelFiltros = document.getElementById('panel-filtros');
    const iconoFlecha = document.getElementById('icono-flecha');
    const btnAplicar = document.getElementById('btn-aplicar');

    // 1. Abrir o cerrar el desplegable al pulsar el botón
    btnAbrir.addEventListener('click', () => {
      const estaOculto = panelFiltros.classList.toggle('oculto');
      btnAbrir.classList.toggle('activo', !estaOculto);
      iconoFlecha.textContent = estaOculto ? '▼' : '▲';
    });

    // 2. Actualizar los textos al mover cada barra deslizante
    const inputPrecio = document.getElementById('filtro-precio');
    const textoPrecio = document.getElementById('valor-precio');
    inputPrecio.addEventListener('input', () => {
      textoPrecio.textContent = inputPrecio.value == 0 ? 'Gratis' : `${inputPrecio.value} €`;
    });

    const inputDistancia = document.getElementById('filtro-distancia');
    const textoDistancia = document.getElementById('valor-distancia');
    inputDistancia.addEventListener('input', () => {
      textoDistancia.textContent = `${inputDistancia.value} km`;
    });

    const inputDuracion = document.getElementById('filtro-duracion');
    const textoDuracion = document.getElementById('valor-duracion');
    inputDuracion.addEventListener('input', () => {
      textoDuracion.textContent = `${inputDuracion.value} h`;
    });

    // 3. Cerrar el panel al pulsar "Aplicar filtros"
    btnAplicar.addEventListener('click', () => {
      panelFiltros.classList.add('oculto');
      btnAbrir.classList.remove('activo');
      iconoFlecha.textContent = '▼';
    });

    function filtrarEventos() {
      const maxPrecio = Number(inputPrecio.value);
      const maxDistancia = Number(inputDistancia.value);
      const maxDuracion = Number(inputDuracion.value);

      let visibles = 0;

      tarjetas.forEach((tarjeta) => {
        const precio = Number(tarjeta.dataset.precio);
        const distancia = Number(tarjeta.dataset.distancia);
        const duracion = Number(tarjeta.dataset.duracion);

        // Comprueba si el evento cumple los tres límites
        const cumple = precio <= maxPrecio &&
                       distancia <= maxDistancia &&
                       duracion <= maxDuracion;

        tarjeta.classList.toggle('oculto', !cumple);
        if (cumple) visibles++;
      });

      btnAplicar.textContent = `Ver ${visibles} ${visibles === 1 ? 'evento' : 'eventos'}`;
      avisoSinResultados.classList.toggle('oculto', visibles > 0);
    }  
