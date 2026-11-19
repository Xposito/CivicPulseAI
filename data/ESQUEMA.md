# Datos: fuentes, esquema y decisiones

Todos los datos salen del **Portal de Datos Abiertos del Ayuntamiento de Madrid**
(<https://datos.madrid.es>), con licencia **CC BY 4.0**. Hay que citar la fuente
en la web, por ejemplo en el pie: "Datos: Ayuntamiento de Madrid".

## Cómo regenerar los datos

```bash
python3 data/descargar_y_normalizar.py            # descarga los 8 datasets y genera el JSON
python3 data/descargar_y_normalizar.py --offline  # rehace el JSON con lo que ya hay en data/raw/
```

Solo necesita Python 3.9 o superior, sin librerías externas. Genera estos ficheros:

| Fichero | Qué es |
|---|---|
| `data/actividades.json` | Todos los registros normalizados (unos 1.950) |
| `data/actividades.ejemplo.json` | Muestra de 34 registros variados (2 eventos por categoría + 1 lugar por tipo) para desarrollar y hacer pruebas |
| `data/banda_sinfonica.json` | Conciertos y plantilla de la Banda Sinfónica Municipal (aparte, ver abajo) |
| `data/raw/*` | Descargas originales sin tocar (no se suben a git) |

Los datasets se actualizan cada día. Conviene ejecutar el script la mañana de la
entrega para que no salgan eventos ya pasados.

## Fuentes

| # | Dataset (nombre oficial) | Tipo | Ficha | Descarga JSON |
|---|---|---|---|---|
| 1 | Agenda de actividades y eventos | eventos | [ficha](https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos) | <https://datos.madrid.es/egob/catalogo/300107-0-agenda-actividades-eventos.json> |
| 2 | Actividades culturales y de ocio municipal en los próximos 100 días | eventos | [ficha](https://datos.madrid.es/dataset/206974-0-agenda-eventos-culturales-100) | <https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json> |
| 3 | Actividades gratuitas en Bibliotecas Municipales en los próximos 60 días | eventos | [ficha](https://datos.madrid.es/dataset/206717-0-agenda-eventos-bibliotecas) | <https://datos.madrid.es/egob/catalogo/206717-0-agenda-eventos-bibliotecas.json> |
| 4 | Agenda de actividades deportivas | eventos | [ficha](https://datos.madrid.es/dataset/212504-0-agenda-actividades-deportes) | <https://datos.madrid.es/egob/catalogo/212504-0-agenda-actividades-deportes.json> |
| 5 | Museos de la ciudad de Madrid | lugares | [ficha](https://datos.madrid.es/dataset/201132-0-museos) | <https://datos.madrid.es/egob/catalogo/201132-0-museos.json> |
| 6 | Bibliotecas de Madrid | lugares | [ficha](https://datos.madrid.es/dataset/201747-0-bibliobuses-bibliotecas) | <https://datos.madrid.es/egob/catalogo/201747-0-bibliobuses-bibliotecas.json> |
| 7 | Centros culturales municipales (incluyen socioculturales y juveniles) | lugares | [ficha](https://datos.madrid.es/dataset/200304-0-centros-culturales) | <https://datos.madrid.es/egob/catalogo/200304-0-centros-culturales.json> |
| 8 | Deportes. Centros deportivos municipales (polideportivos) | lugares | [ficha](https://datos.madrid.es/dataset/200186-0-polideportivos) | <https://datos.madrid.es/egob/catalogo/200186-0-polideportivos.json> |

Los datasets 1 a 4 se solapan: un mismo evento puede aparecer en varios. Se
quitan los duplicados por su `id` y en el campo `fuentes` se guardan todos los
datasets donde aparece.

## Cruce de datasets

Cada evento de la agenda trae en `relation.@id` el identificador del lugar donde
se celebra, por ejemplo `.../entidadesyorganismos/1945-centro-cultural-casa-vacas.json`.
Ese número es el mismo `id` que usan los datasets de lugares (5 a 8). Con él:

- a cada evento se le añade `lugar_id`, que apunta a su lugar, y `horario_texto`, que es el horario de apertura del lugar;
- si al evento le faltan coordenadas o dirección, se copian las del lugar;
- cada lugar recibe `num_eventos`, el número de eventos próximos que tiene.

Si no hay `relation`, se intenta casar el nombre del lugar del evento
(`event-location`) con el nombre de un lugar. Así se enlazan alrededor del 63 %
de los eventos.

## Formato de `actividades.json`

```jsonc
{
  "generado": "2026-11-19T11:20:00",
  "fecha_referencia": "2026-11-19",   // se descartan los eventos que terminaron antes de esta fecha
  "licencia": "...",
  "fuentes": [ { "id", "nombre", "tipo", "ficha", "descarga" } ],
  "categorias": [ { "id": "museo", "nombre": "Museo" }, ... ],   // lista cerrada
  "total": 1954,
  "actividades": [ /* registros como el de abajo */ ]
}
```

Todos los registros tienen los mismos campos. `tipo_registro` dice si es un
**evento** (tiene fechas) o un **lugar** (museo, biblioteca, centro cultural o
polideportivo, que está abierto según su horario). Un campo sin dato vale `null`.

### Origen de cada campo

Hay tres tipos de origen: **directo** (se copia de la fuente, como mucho limpiando espacios),
**derivado** (se calcula a partir de campos de la fuente con una regla fija) y
**estimado** (no está en la fuente y se pone un valor razonable, marcado como tal).

| Campo | Tipo | Ejemplo | Sale de (evento) | Sale de (lugar) | Origen |
|---|---|---|---|---|---|
| `id` | string | `"evento-50147284"` | `id` | `id` | directo, con prefijo |
| `tipo_registro` | `"evento"` \| `"lugar"` | | dataset 1-4 | dataset 5-8 | derivado |
| `titulo` | string | | `title` | `title` | directo |
| `descripcion` | string\|null | | `description` | `organization.organization-desc` | directo |
| `categoria` | id de la lista cerrada | `"teatro"` | `@type` → tabla de abajo | según el dataset | derivado |
| `categoria_origen` | string (solo eventos) | `"fuente"` | `fuente`: sale de `@type`. `palabras_clave`: sale del título o la descripción. `nombre_lugar`: sale del nombre del lugar. `por_defecto`: no se pudo deducir | — | informativo |
| `subcategoria` | string\|null | `"Cuentacuentos Titeres Marionetas"` | último tramo de `@type` | tramo de `@type` | directo |
| `publico` | string[] | `["infantil","familias"]` | `audience` (Niños→infantil, Familias→familias, Jovenes→jovenes, Mayores→mayores…) | `[]` | derivado |
| `para_ninos` | bool | | `true` si la categoría es `infantil` o el público incluye infantil o familias | `false` | derivado |
| `gratis` | bool\|null | | `free` (1 = gratis). También `true` si `price` dice "gratuito" o "entrada libre" | `true` si `organization.services` o la descripción dicen "entrada gratuita" o "libre". Si no, `null` | directo o derivado |
| `precio_texto` | string\|null | `"Desde 27 euros"` | `price` | — | directo |
| `precio_min` | number\|null (€) | `27` | número más bajo junto a "euros" o "€" en `price`. Si es gratis, `0` | `0` si es gratis | derivado |
| `precio_origen` | string\|null | | `fuente`, `texto_precio` o `texto_servicios` | | informativo |
| `fecha_inicio` | `AAAA-MM-DD` | | `dtstart` | `null` | directo |
| `fecha_fin` | `AAAA-MM-DD` | | `dtend` (solo la fecha) | `null` | directo |
| `hora_inicio` | `HH:MM`\|null | `"19:00"` | `time`. Si viene vacío, la hora de `dtstart` | `null` | directo |
| `hora_fin` | `HH:MM`\|null | `"20:00"` | `hora_inicio` + `duracion_min` | `null` | **derivado** (ojo: suele usar la duración estimada) |
| `dias_semana` | string[]\|null | `["lunes","miercoles"]` | `recurrence.days` (MO, TU…) | `null` | derivado |
| `dias_excluidos` | `AAAA-MM-DD`[] | | `excluded-days` | `[]` | derivado |
| `duracion_min` | int\|null | `90` | "Duración: X minutos/horas" en `description`. Si no aparece, tabla de abajo | museos: 90 estimados. Resto: `null` | derivado o **estimado** |
| `duracion_origen` | `"descripcion"` \| `"estimada"` \| null | | | | informativo |
| `horario_texto` | string\|null | | horario del lugar enlazado (cruce) | `organization.schedule` | directo |
| `lugar_nombre` | string\|null | | `event-location` | `title` | directo |
| `lugar_id` | string\|null | `"lugar-1945"` | número de `relation.@id` (cruce) | `null` | derivado |
| `direccion` | string\|null | `"Paseo Colombia 1"` | `address.area.street-address`, o la del lugar enlazado | `address.street-address` | directo o cruce |
| `codigo_postal` | string\|null | | `address.area.postal-code` | `address.postal-code` | directo |
| `distrito` | string\|null | `"Retiro"` | final de `address.district.@id` | ídem | derivado (con tildes) |
| `barrio` | string\|null | | final de `address.area.@id` | ídem | derivado |
| `lat`, `lon` | number\|null | `40.419066` | `location.latitude/longitude`, o las del lugar enlazado | ídem | directo o cruce |
| `coordenadas_origen` | string\|null (solo eventos) | | `fuente` o `lugar_relacionado` | — | informativo |
| `num_eventos` | int (solo lugares) | | — | eventos enlazados a este lugar | derivado (cruce) |
| `url` | string | | `link` (página en madrid.es) | `relation` | directo |
| `fuente` / `fuentes` | string / string[] | | id del dataset | id del dataset | — |

### Lo que NO viene en la fuente y cómo lo resolvemos

- **Hora de fin y duración.** `dtend` siempre trae la hora `23:59`, así que solo
  dice el último día y no a qué hora acaba. La duración solo aparece escrita
  en la descripción en el 8 % de los eventos. Para el resto se usa una duración
  típica según la categoría, marcada con `duracion_origen: "estimada"`. En la
  tarjeta conviene mostrarla como "~90 min".
- **Cercanía.** No es un dato de la fuente. Se calcula en el backend con la
  fórmula de Haversine, usando `lat`/`lon` y la posición del usuario. Hay unos
  150 eventos sin coordenadas (online o repartidos por toda la ciudad): el
  endpoint debería dejarlos fuera del mapa.
- **Precio en número.** La fuente da un texto libre (`price`). `precio_min` es
  el número más bajo que aparece en ese texto. Por ejemplo, "Desde 15,75 euros"
  da 15.75.
- **Precio de museos y polideportivos.** No viene en ningún campo. Solo
  marcamos `gratis: true` cuando la descripción lo dice. Si no, `null`, que en
  la web se puede mostrar como "Consultar".
- **Eventos recurrentes.** Un taller que va "todos los lunes de septiembre a
  junio" es un único registro con `fecha_inicio`, `fecha_fin` y
  `dias_semana: ["lunes"]`. Para saber si hay sesión en un día concreto, se
  comprueba que la fecha esté entre `fecha_inicio` y `fecha_fin`, que caiga en uno
  de los `dias_semana` (si los hay) y que no esté en `dias_excluidos`.

### Categorías (lista cerrada)

| id | Tipos del Ayuntamiento (`@type`) que entran |
|---|---|
| `museo` | todo el dataset de museos |
| `exposicion` | Exposiciones |
| `teatro` | TeatroPerformance, CircoMagia |
| `musica` | Musica (y subtipos: Jazz, Flamenco, Coro…) |
| `danza` | DanzaBaile |
| `cine` | CineActividadesAudiovisuales |
| `infantil` | CuentacuentosTiteresMarionetas, ActividadesEscolares, Campamentos |
| `club_lectura` | ClubesLectura |
| `literatura` | RecitalesPresentacionesActosLiterarios |
| `taller` | CursosTalleres (y subtipos) |
| `conferencia` | ConferenciasColoquios |
| `deporte` | ActividadesDeportivas (y subtipos) y todo el dataset de polideportivos |
| `visita_guiada` | ExcursionesItinerariosVisitas |
| `aire_libre` | ItinerariosOtrasActividadesAmbientales, ActividadesCalleArteUrbano |
| `fiestas` | FiestasNavidadesReyes, Navidad, Festivales, Ferias, ComemoracionesHomenajes |
| `biblioteca` | todo el dataset de bibliotecas |
| `centro_cultural` | todo el dataset de centros culturales |
| `otros` | ConcursosCertamenes, EnLinea y lo que no encaja en ninguna otra |

Los tipos `ProgramacionDestacadaAgendaCultura` y `1ciudad21distritos`, y los
eventos sin `@type`, no dicen de qué va la actividad. Para esos se buscan
palabras clave en el título y la descripción ("concierto" → música,
"cuentacuentos" → infantil…). Si no hay ninguna, se mira el nombre del lugar
("Teatro…" → teatro, "Cineteca" → cine). La lista completa está en
`PALABRAS_CLAVE` y `PALABRAS_LUGAR` dentro del script.

"Infantil" es a la vez una categoría y un público: un concierto para familias
tiene `categoria: "musica"` y `para_ninos: true`. Para el filtro "para niños"
hay que usar `para_ninos`.

### Duraciones estimadas (minutos)

museo 90 · exposición 60 · teatro 90 · música 90 · danza 75 · cine 110 ·
infantil 60 · club de lectura 90 · literatura 60 · taller 90 · conferencia 60 ·
deporte 60 · visita guiada 120 · aire libre 90 · fiestas 120 · otros 60.

## Banda Sinfónica Municipal de Madrid (`banda_sinfonica.json`)

Fuente: **Conciertos y plantilla de la Banda Sinfónica Municipal de Madrid**,
[ficha](https://datos.madrid.es/dataset/135161-0-conciertos-y-personal-de-la-banda-sinfonica-municipal-de-madrid).
Son dos CSV separados por `;`, en UTF-8 con BOM. Las URLs exactas están en el campo `fuente.descarga` del JSON.
Ojo: la banda es del **Ayuntamiento**, no de la Comunidad de Madrid.

Va en un fichero aparte porque **todos los conciertos son de 2025**, así que ya
han pasado. Además no traen hora, precio ni dirección, y si se metieran en
`actividades.json` el filtro de fechas los quitaría. Sirven para una tarjeta o
sección "Banda Sinfónica" con el histórico, la programación habitual y la
plantilla. Tampoco aparece ningún concierto de la banda en la agenda actual
(datasets 1-4).

**`conciertos[]`** (36):

| Campo | Sale de | Origen |
|---|---|---|
| `titulo` | `NOMBRE CONCIERTO` | directo |
| `tipo`, `ciclo` | `TIPO`, `CICLO` | directo (en `ciclo` se unifican las mayúsculas) |
| `fecha` | `AÑO` + `MES` (en texto) + `DÍA` → `AAAA-MM-DD` | derivado |
| `dia_semana` | se calcula a partir de `fecha` | derivado |
| `lugar_nombre` | `UBICACIÓN`: solo el nombre ("Teatro Monumental", "Templete del Retiro"…), **sin coordenadas** | directo |
| `artistas_invitados` | `ARTISTAS INVITADAS/OS` ("No aplica" → `null`) | directo |
| `para_ninos` | `true` si `TIPO` contiene "Escolar" o "Familiar" | derivado |

**`plantilla[]`** (93 puestos): `puesto`, `categoria`, `instrumento`,
`tipo_instrumento`, `relacion` y `sexo`, que salen de las columnas del mismo
nombre del CSV. **No trae nombres de personas.**

`resumen_conciertos` y `resumen_plantilla` son recuentos ya hechos para pintar
gráficos sin calcular nada: conciertos por lugar, ciclo y día de la semana, y
plantilla por tipo de instrumento, instrumento, sexo, categoría y relación
laboral, además del número de vacantes.

Lo que se ve en los datos: en primavera y verano la banda toca **los domingos en
el Templete del Retiro**, y en otoño e invierno **los martes en el Teatro
Monumental**. Es el patrón habitual, no una programación publicada para 2026.
