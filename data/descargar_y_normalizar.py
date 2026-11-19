#!/usr/bin/env python3
"""
Descarga los datasets oficiales del Portal de Datos Abiertos del Ayuntamiento
de Madrid (https://datos.madrid.es) y los unifica en un único JSON:

    data/actividades.json          -> todos los registros normalizados
    data/actividades.ejemplo.json  -> muestra pequeña para desarrollar

Uso (solo librería estándar de Python 3.9+, sin dependencias):

    python3 data/descargar_y_normalizar.py            # descarga y normaliza
    python3 data/descargar_y_normalizar.py --offline  # reutiliza data/raw/

El esquema de salida y el origen de cada campo están en data/ESQUEMA.md.
"""

import argparse
import html
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = "https://datos.madrid.es/egob/catalogo/"
FICHA = "https://datos.madrid.es/dataset/"

# Datasets de EVENTOS (tienen fecha). El orden importa: si un evento aparece en
# varios, se queda la versión del primero y se apuntan todos en "fuentes".
DATASETS_EVENTOS = [
    ("300107-0-agenda-actividades-eventos", "Agenda de actividades y eventos"),
    ("206974-0-agenda-eventos-culturales-100", "Actividades culturales y de ocio municipal en los próximos 100 días"),
    ("206717-0-agenda-eventos-bibliotecas", "Actividades gratuitas en Bibliotecas Municipales en los próximos 60 días"),
    ("212504-0-agenda-actividades-deportes", "Agenda de actividades deportivas"),
]

# Datasets de LUGARES (equipamientos fijos) y la categoría que reciben.
DATASETS_LUGARES = [
    ("201132-0-museos", "Museos de la ciudad de Madrid", "museo"),
    ("201747-0-bibliobuses-bibliotecas", "Bibliotecas de Madrid", "biblioteca"),
    ("200304-0-centros-culturales", "Centros culturales municipales (incluyen socioculturales y juveniles)", "centro_cultural"),
    ("200186-0-polideportivos", "Deportes. Centros deportivos municipales (polideportivos)", "deporte"),
]

# Lista CERRADA de categorías. El frontend puede usarla tal cual para los filtros.
CATEGORIAS = {
    "museo": "Museo",
    "exposicion": "Exposición",
    "teatro": "Teatro y circo",
    "musica": "Música",
    "danza": "Danza",
    "cine": "Cine",
    "infantil": "Infantil",
    "club_lectura": "Club de lectura",
    "literatura": "Literatura y recitales",
    "taller": "Cursos y talleres",
    "conferencia": "Conferencias",
    "deporte": "Deporte",
    "visita_guiada": "Visitas e itinerarios",
    "aire_libre": "Aire libre y medio ambiente",
    "fiestas": "Fiestas y festivales",
    "biblioteca": "Biblioteca",
    "centro_cultural": "Centro cultural",
    "otros": "Otros",
}

# Tipo del Ayuntamiento (campo "@type", lo que va tras ".../kos/actividades/")
# -> nuestra categoría. Se mira primero el tipo completo y luego el primer nivel.
MAPA_TIPOS = {
    "CursosTalleres": "taller",
    "TeatroPerformance": "teatro",
    "CircoMagia": "teatro",
    "Exposiciones": "exposicion",
    "CuentacuentosTiteresMarionetas": "infantil",
    "ActividadesEscolares": "infantil",
    "Campamentos": "infantil",
    "Musica": "musica",
    "ConferenciasColoquios": "conferencia",
    "CineActividadesAudiovisuales": "cine",
    "RecitalesPresentacionesActosLiterarios": "literatura",
    "ClubesLectura": "club_lectura",
    "DanzaBaile": "danza",
    "ExcursionesItinerariosVisitas": "visita_guiada",
    "ItinerariosOtrasActividadesAmbientales": "aire_libre",
    "ActividadesCalleArteUrbano": "aire_libre",
    "ActividadesDeportivas": "deporte",
    "FiestasNavidadesReyes": "fiestas",
    "Navidad": "fiestas",
    "Festivales": "fiestas",
    "Ferias": "fiestas",
    "ComemoracionesHomenajes": "fiestas",
    "ConcursosCertamenes": "otros",
    "EnLinea": "otros",
    # Estos dos no dicen el tipo real: se resuelven con palabras clave.
    "ProgramacionDestacadaAgendaCultura": None,
    "1ciudad21distritos": None,
}

# Palabras clave (sobre título + descripción, sin tildes) para los eventos
# cuyo tipo no viene o es genérico. Se prueban en este orden.
PALABRAS_CLAVE = [
    ("club_lectura", r"club de lectura|tertulia literaria"),
    ("infantil", r"cuentacuentos|titeres|marioneta|infantil|para ninos|bebes|peques"),
    ("cine", r"\bcine\b|cineforum|cineteca|pelicula|proyeccion|cortometraje|documental"),
    ("exposicion", r"exposicion|muestra fotografica|\bexpo\b"),
    ("musica", r"concierto|musica|orquesta|banda|coro\b|jazz|flamenco|recital de piano"),
    ("danza", r"danza|baile|ballet"),
    ("teatro", r"teatro|obra de|comedia|monologo|circo|magia|clown"),
    ("taller", r"taller|curso|clase"),
    ("conferencia", r"conferencia|charla|coloquio|mesa redonda|jornada"),
    ("literatura", r"presentacion del libro|poesia|lectura|recital"),
    ("visita_guiada", r"visita|ruta|itinerario|paseo"),
    ("deporte", r"deporte|deportiv|carrera|yoga|pilates|zumba|baloncesto|futbol"),
    ("fiestas", r"fiesta|navidad|carnaval|festival|feria|belen|cabalgata"),
]

# Último recurso: el nombre del lugar (p. ej. "Teatro Español" -> teatro).
PALABRAS_LUGAR = [
    ("cine", r"cineteca|cine\b"),
    ("teatro", r"teatro|naves del espanol|sala de teatro"),
    ("musica", r"auditorio|sala de conciertos|\bsala\b.*musica"),
    ("exposicion", r"museo|sala de exposiciones|galeria"),
]

# Duración típica (minutos) cuando la fuente no la da. Es una ESTIMACIÓN.
DURACION_ESTIMADA = {
    "museo": 90, "exposicion": 60, "teatro": 90, "musica": 90, "danza": 75,
    "cine": 110, "infantil": 60, "club_lectura": 90, "literatura": 60,
    "taller": 90, "conferencia": 60, "deporte": 60, "visita_guiada": 120,
    "aire_libre": 90, "fiestas": 120, "otros": 60,
}

DISTRITOS = {
    "Centro": "Centro", "Arganzuela": "Arganzuela", "Retiro": "Retiro",
    "Salamanca": "Salamanca", "Chamartin": "Chamartín", "Tetuan": "Tetuán",
    "Chamberi": "Chamberí", "Fuencarral-ElPardo": "Fuencarral-El Pardo",
    "Moncloa-Aravaca": "Moncloa-Aravaca", "Latina": "Latina",
    "Carabanchel": "Carabanchel", "Usera": "Usera",
    "PuenteDeVallecas": "Puente de Vallecas", "Moratalaz": "Moratalaz",
    "CiudadLineal": "Ciudad Lineal", "Hortaleza": "Hortaleza",
    "Villaverde": "Villaverde", "VillaDeVallecas": "Villa de Vallecas",
    "Vicalvaro": "Vicálvaro", "SanBlas-Canillejas": "San Blas-Canillejas",
    "Barajas": "Barajas",
}

PUBLICO = {
    "Niños": "infantil", "Familias": "familias", "Jovenes": "jovenes",
    "Mayores": "mayores", "PoblaciónGeneral": "general", "Mujeres": "mujeres",
    "Discapacitados": "diversidad_funcional",
    "EstudianteseInvestigadores": "estudiantes", "Consumidores": "general",
}

DIAS = {"MO": "lunes", "TU": "martes", "WE": "miercoles", "TH": "jueves",
        "FR": "viernes", "SA": "sabado", "SU": "domingo"}

# Caja aproximada del municipio de Madrid, para descartar coordenadas erróneas.
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 40.30, 40.65, -3.90, -3.50


# ---------------------------------------------------------------- utilidades

def sin_tildes(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def limpiar(texto):
    """Quita espacios raros y devuelve None si queda vacío."""
    if texto is None:
        return None
    t = re.sub(r"\s+", " ", html.unescape(str(texto)).replace("\xa0", " ")).strip()
    return t or None


def separar_camel(texto):
    """'SanPascual' -> 'San Pascual' (barrios vienen pegados en la URI)."""
    return re.sub(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])", " ", texto or "").strip() or None


def descargar(slug, carpeta_raw, offline):
    ruta = carpeta_raw / f"{slug}.json"
    if not offline:
        url = f"{BASE}{slug}.json"
        print(f"  descargando {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "civicpulse-hackathon"})
        with urllib.request.urlopen(req, timeout=120) as r:  # sigue la redirección 302
            ruta.write_bytes(r.read())
    # Algunos ficheros traen caracteres de control dentro de textos: strict=False.
    return json.loads(ruta.read_text(encoding="utf-8"), strict=False)["@graph"]


def direccion(reg):
    """Los eventos traen calle/CP dentro de address.area; los lugares en address."""
    adr = reg.get("address") or {}
    area = adr.get("area") or {}
    calle = area.get("street-address") or adr.get("street-address")
    cp = area.get("postal-code") or adr.get("postal-code")
    dist_uri = (adr.get("district") or {}).get("@id", "")
    barrio_uri = area.get("@id", "")
    dist = dist_uri.split("/Distrito/")[-1] if "/Distrito/" in dist_uri else ""
    barrio = barrio_uri.split("/Barrio/")[-1] if "/Barrio/" in barrio_uri else ""
    return {
        "direccion": limpiar(calle.title() if calle else None),
        "codigo_postal": limpiar(cp),
        "distrito": DISTRITOS.get(dist),
        "barrio": separar_camel(barrio),
    }


def coordenadas(reg):
    loc = reg.get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None
    if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
        return round(lat, 6), round(lon, 6)
    return None, None


def id_lugar_relacionado(evento):
    """relation.@id = '.../entidadesyorganismos/2190-teatro-espanol.json' -> '2190'."""
    uri = (evento.get("relation") or {}).get("@id") or ""
    m = re.search(r"/entidadesyorganismos/(\d+)", uri)
    return m.group(1) if m else None


def categoria_evento(tipo_uri, texto, por_defecto, nombre_lugar=""):
    tipo = tipo_uri.split("/kos/actividades/")[-1] if "/kos/actividades/" in tipo_uri else ""
    sub = None
    if tipo:
        partes = tipo.split("/")
        sub = separar_camel(partes[-1])
        cat = MAPA_TIPOS.get(tipo, MAPA_TIPOS.get(partes[0], "otros"))
        if cat:
            return cat, sub, "fuente"
    t = sin_tildes(texto)
    for cat, patron in PALABRAS_CLAVE:
        if re.search(patron, t):
            return cat, sub, "palabras_clave"
    t = sin_tildes(nombre_lugar)
    for cat, patron in PALABRAS_LUGAR:
        if re.search(patron, t):
            return cat, sub, "nombre_lugar"
    return por_defecto or "otros", sub, "por_defecto"


def precio(free, texto):
    """Devuelve (gratis, precio_texto, precio_min, origen)."""
    txt = limpiar(texto)
    t = sin_tildes(txt or "")
    if free in (1, "1", True):
        return True, txt, 0.0, "fuente"
    if re.search(r"gratu|gratis|entrada libre|acceso libre", t):
        return True, txt, 0.0, "texto_precio"
    numeros = [float(n.replace(",", ".")) for n in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:€|euro)", t)]
    if numeros:
        return False, txt, min(numeros), "texto_precio"
    if free in (0, "0"):
        return False, txt, None, "fuente"
    return None, txt, None, None


def duracion_de_texto(texto):
    """Busca 'Duración: 60 minutos', '2 horas y media', '90 min'... en la descripción."""
    t = sin_tildes(texto or "")
    m = re.search(r"duracion[^0-9]{0,40}?(\d+(?:[.,]\d+)?)\s*(minutos|min\b|'|horas?|h\b)(\s*y\s*media)?", t)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    if m.group(2).startswith("h"):
        n = n * 60 + (30 if m.group(3) else 0)
    n = int(round(n))
    return n if 5 <= n <= 600 else None


def fecha_iso(texto):
    """'2027-01-27 18:00:00.0' -> date"""
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def dias_excluidos(texto):
    out = []
    for trozo in (texto or "").split(";"):
        try:
            out.append(datetime.strptime(trozo.strip(), "%d/%m/%Y").date().isoformat())
        except ValueError:
            pass
    return out


def sumar_minutos(hora, minutos):
    if not hora or minutos is None:
        return None
    h = datetime.strptime(hora, "%H:%M") + timedelta(minutes=minutos)
    return h.strftime("%H:%M")


def ficha(slug):
    return f"{FICHA}{slug}"


# ---------------------------------------------------------------- lugares

def normalizar_lugares(carpeta_raw, offline):
    lugares = {}
    for slug, nombre, cat in DATASETS_LUGARES:
        for r in descargar(slug, carpeta_raw, offline):
            org = r.get("organization") or {}
            lat, lon = coordenadas(r)
            servicios = limpiar(org.get("services"))
            desc = limpiar(org.get("organization-desc"))
            gratis, precio_txt, precio_min, origen_precio = None, None, None, None
            if re.search(r"(entrada|acceso|visita)s? (gratuit|libre)", sin_tildes((servicios or "") + " " + (desc or ""))):
                gratis, precio_min, origen_precio = True, 0.0, "texto_servicios"
            tipo = (r.get("@type") or "").split("/entidadesYorganismos/")[-1]
            dur = duracion_de_texto(org.get("schedule"))
            if cat == "museo":
                dur_origen = "descripcion" if dur else "estimada"
                dur = dur or DURACION_ESTIMADA["museo"]
            else:
                dur_origen = "descripcion" if dur else None
            lid = r["id"]
            if lid in lugares:  # mismo equipamiento en dos datasets
                lugares[lid]["fuentes"].append(slug)
                continue
            lugares[lid] = {
                "id": f"lugar-{lid}",
                "tipo_registro": "lugar",
                "titulo": limpiar(r.get("title")),
                "descripcion": desc,
                "categoria": cat,
                "subcategoria": separar_camel(tipo.split("/")[0]) if tipo else None,
                "publico": [],
                "para_ninos": False,
                "gratis": gratis,
                "precio_texto": precio_txt,
                "precio_min": precio_min,
                "precio_origen": origen_precio,
                "fecha_inicio": None,
                "fecha_fin": None,
                "hora_inicio": None,
                "hora_fin": None,
                "dias_semana": None,
                "dias_excluidos": [],
                "duracion_min": dur,
                "duracion_origen": dur_origen,
                "horario_texto": limpiar(org.get("schedule")),
                "lugar_nombre": limpiar(r.get("title")),
                "lugar_id": None,
                **direccion(r),
                "lat": lat,
                "lon": lon,
                "num_eventos": 0,
                "url": limpiar(r.get("relation")),
                "fuente": slug,
                "fuentes": [slug],
            }
    return lugares


# ---------------------------------------------------------------- eventos

def normalizar_eventos(carpeta_raw, offline, lugares, hoy):
    eventos = {}
    por_nombre = {sin_tildes(l["titulo"]): l for l in lugares.values() if l["titulo"]}
    descartados_pasados = 0
    for slug, _nombre in DATASETS_EVENTOS:
        defecto = "deporte" if "deportes" in slug else None
        for r in descargar(slug, carpeta_raw, offline):
            eid = r.get("id")
            if eid in eventos:
                if slug not in eventos[eid]["fuentes"]:
                    eventos[eid]["fuentes"].append(slug)
                continue
            f_ini, f_fin = fecha_iso(r.get("dtstart")), fecha_iso(r.get("dtend"))
            if f_fin and f_fin < hoy:
                descartados_pasados += 1
                continue

            titulo = limpiar(r.get("title"))
            desc = limpiar(r.get("description"))
            cat, sub, cat_origen = categoria_evento(r.get("@type") or "", f"{titulo} {desc or ''}", defecto,
                                                    r.get("event-location") or "")

            publico = []
            for a in (r.get("audience") or "").split(","):
                p = PUBLICO.get(a.strip())
                if p and p not in publico:
                    publico.append(p)
            para_ninos = cat == "infantil" or "infantil" in publico or "familias" in publico

            gratis, precio_txt, precio_min, precio_origen = precio(r.get("free"), r.get("price"))

            hora = limpiar(r.get("time"))
            if hora and not re.fullmatch(r"\d{2}:\d{2}", hora):
                hora = None
            if not hora and r.get("dtstart", "")[11:16] not in ("", "00:00"):
                hora = r["dtstart"][11:16]

            dur = duracion_de_texto(desc)
            dur_origen = "descripcion" if dur else "estimada"
            dur = dur or DURACION_ESTIMADA.get(cat, 60)

            rec = r.get("recurrence") or {}
            dias = [DIAS[d] for d in (rec.get("days") or "").split(",") if d in DIAS] or None

            # --- cruce con el dataset de lugares
            lugar = lugares.get(id_lugar_relacionado(r) or "")
            nombre_lugar = limpiar(r.get("event-location"))
            if not lugar and nombre_lugar:
                lugar = por_nombre.get(sin_tildes(nombre_lugar))
            lat, lon = coordenadas(r)
            coord_origen = "fuente" if lat is not None else None
            adr = direccion(r)
            if lugar:
                lugar["num_eventos"] += 1
                if lat is None and lugar["lat"] is not None:
                    lat, lon, coord_origen = lugar["lat"], lugar["lon"], "lugar_relacionado"
                for k in ("direccion", "codigo_postal", "distrito", "barrio"):
                    adr[k] = adr[k] or lugar[k]

            eventos[eid] = {
                "id": f"evento-{eid}",
                "tipo_registro": "evento",
                "titulo": titulo,
                "descripcion": desc,
                "categoria": cat,
                "categoria_origen": cat_origen,
                "subcategoria": sub,
                "publico": publico,
                "para_ninos": para_ninos,
                "gratis": gratis,
                "precio_texto": precio_txt,
                "precio_min": precio_min,
                "precio_origen": precio_origen,
                "fecha_inicio": f_ini.isoformat() if f_ini else None,
                "fecha_fin": f_fin.isoformat() if f_fin else None,
                "hora_inicio": hora,
                "hora_fin": sumar_minutos(hora, dur),
                "dias_semana": dias,
                "dias_excluidos": dias_excluidos(r.get("excluded-days")),
                "duracion_min": dur,
                "duracion_origen": dur_origen,
                "horario_texto": lugar["horario_texto"] if lugar else None,
                "lugar_nombre": nombre_lugar or (lugar["titulo"] if lugar else None),
                "lugar_id": lugar["id"] if lugar else None,
                **adr,
                "lat": lat,
                "lon": lon,
                "coordenadas_origen": coord_origen,
                "url": limpiar(r.get("link")),
                "fuente": slug,
                "fuentes": [slug],
            }
    return eventos, descartados_pasados


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="no descargar, usar data/raw/")
    ap.add_argument("--hoy", help="fecha de referencia AAAA-MM-DD (por defecto, hoy)")
    args = ap.parse_args()

    carpeta = Path(__file__).resolve().parent
    raw = carpeta / "raw"
    raw.mkdir(exist_ok=True)
    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()

    lugares = normalizar_lugares(raw, args.offline)
    eventos, pasados = normalizar_eventos(raw, args.offline, lugares, hoy)

    registros = list(eventos.values()) + list(lugares.values())
    registros.sort(key=lambda x: (x["tipo_registro"], x["fecha_inicio"] or "", x["titulo"] or ""))

    fuentes = [
        {"id": s, "nombre": n, "tipo": "eventos", "ficha": ficha(s), "descarga": f"{BASE}{s}.json"}
        for s, n in DATASETS_EVENTOS
    ] + [
        {"id": s, "nombre": n, "tipo": "lugares", "ficha": ficha(s), "descarga": f"{BASE}{s}.json"}
        for s, n, _ in DATASETS_LUGARES
    ]
    salida = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "fecha_referencia": hoy.isoformat(),
        "licencia": "Datos: Ayuntamiento de Madrid, Portal de Datos Abiertos (CC BY 4.0)",
        "fuentes": fuentes,
        "categorias": [{"id": k, "nombre": v} for k, v in CATEGORIAS.items()],
        "total": len(registros),
        "actividades": registros,
    }
    (carpeta / "actividades.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    # Muestra variada: 2 por categoría (eventos con coordenadas) + 1 lugar por tipo.
    muestra, vistos = [], {}
    for x in registros:
        clave = (x["tipo_registro"], x["categoria"])
        tope = 2 if x["tipo_registro"] == "evento" else 1
        if x["lat"] is not None and vistos.get(clave, 0) < tope:
            vistos[clave] = vistos.get(clave, 0) + 1
            muestra.append(x)
    (carpeta / "actividades.ejemplo.json").write_text(
        json.dumps({**salida, "total": len(muestra), "actividades": muestra}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # Resumen por pantalla
    ev = list(eventos.values())
    def pct(n, d):
        return f"{n} ({100 * n / d:.0f}%)" if d else "0"
    print(f"Eventos: {len(ev)} (descartados por ya terminados: {pasados})")
    print(f"Lugares: {len(lugares)}")
    print(f"  eventos con coordenadas: {pct(sum(1 for e in ev if e['lat'] is not None), len(ev))}")
    print(f"  eventos enlazados a un lugar: {pct(sum(1 for e in ev if e['lugar_id']), len(ev))}")
    print(f"  eventos con hora de inicio: {pct(sum(1 for e in ev if e['hora_inicio']), len(ev))}")
    print(f"  eventos con duración real (no estimada): {pct(sum(1 for e in ev if e['duracion_origen'] == 'descripcion'), len(ev))}")
    print(f"  eventos gratis: {pct(sum(1 for e in ev if e['gratis']), len(ev))}")
    cats = {}
    for e in registros:
        cats[e["categoria"]] = cats.get(e["categoria"], 0) + 1
    print("  por categoría:", dict(sorted(cats.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
