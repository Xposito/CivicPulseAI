import csv
import re
import unicodedata
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API de eventos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción cambia "*" por tu dominio
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# main.py junto a la carpeta data/. Si main.py está dentro de data/, quita "data".
RUTA_CSV = Path(__file__).parent / "data" / "actividades_unidas.csv"

# Los talleres (fuente "Talleres") son clases semanales sin fecha, sin precio y sin coordenadas.
# Son ~80 % del CSV. Ponlo en False si solo quieres eventos con fecha.
INCLUIR_TALLERES = True

# Categorías de la web -> categorías del CSV que agrupan (ya normalizadas: minúsculas y sin tildes).
# "id" es lo que envía el HTML en ?categoria=...
GRUPOS = [
    {"id": "cursos_talleres", "nombre": "Cursos y talleres",           "csv": ["cursos y talleres"],                          "color": None},
    {"id": "musica",          "nombre": "Música",                      "csv": ["musica", "danza"],                            "color": None},
    {"id": "espectaculos",    "nombre": "Espectáculos",                "csv": ["teatro y circo", "cine"],                     "color": None},
    {"id": "deporte",         "nombre": "Deporte",                     "csv": ["deporte"],                                    "color": None},
    {"id": "infantil",        "nombre": "Infantil",                    "csv": ["infantil"],                                   "color": None},
    {"id": "conferencias",    "nombre": "Conferencias",                "csv": ["conferencias"],                               "color": None},
    {"id": "exposicion",      "nombre": "Exposición",                  "csv": ["exposicion"],                                 "color": None},
    {"id": "fiestas",         "nombre": "Fiestas y festivales",        "csv": ["fiestas y festivales"],                       "color": "rosa"},
    {"id": "literatura",      "nombre": "Literatura",                  "csv": ["literatura y recitales", "club de lectura"],  "color": None},
    {"id": "visitas",         "nombre": "Visitas e itinerarios",       "csv": ["visitas e itinerarios"],                      "color": None},
    {"id": "aire_libre",      "nombre": "Aire libre y medio ambiente", "csv": ["aire libre y medio ambiente"],                "color": None},
    {"id": "otros",           "nombre": "Otros",                       "csv": ["otros"],                                      "color": "gris"},
]

# Búsqueda inversa: categoría del CSV -> grupo
GRUPO_DE = {c: g for g in GRUPOS for c in g["csv"]}
GRUPO_OTROS = GRUPO_DE["otros"]  # categorías nuevas o desconocidas caen aquí

# Días de la semana: columna de horario del CSV, letra de DIAS-SEMANA y nombre para mostrar
DIAS = [
    ("LUNES", "L", "lunes"), ("MARTES", "M", "martes"), ("MIERCOLES", "X", "miércoles"),
    ("JUEVES", "J", "jueves"), ("VIERNES", "V", "viernes"), ("SABADO", "S", "sábados"),
    ("DOMINGO", "D", "domingos"),
]
NOMBRE_DIA = {letra: nombre for _, letra, nombre in DIAS}


# ---------- Utilidades ----------

def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: 'Música' -> 'musica'."""
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def a_numero(valor: str) -> Optional[float]:
    try:
        return float(valor.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def a_hora(valor: str) -> Optional[time]:
    try:
        return datetime.strptime(valor.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return None


def a_fecha(valor: str) -> Optional[date]:
    """'2027-01-27 00:00:00.0' -> date(2027, 1, 27)"""
    try:
        return datetime.strptime(valor.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def parsear_precio(texto: str, gratuito: str):
    """Devuelve (gratis, precio). precio=None si se desconoce.

    GRATUITO: '1' gratis, '0' de pago, '' desconocido.
    PRECIO es texto libre: '3 euros', 'Desde 27 euros', '15,75 euros - 21 euros', '6 a 22 euros'...
    Se toma el importe más bajo que aparezca junto a la palabra 'euro'.
    """
    texto = (texto or "").replace("\xa0", " ").strip()
    importes = [
        float(m.group(1).replace(",", "."))
        for m in re.finditer(r"(\d+(?:[.,]\d+)?)(?:\s*(?:a|-)\s*\d+(?:[.,]\d+)?)?\s*euro", texto, re.I)
    ]
    if gratuito.strip() == "1" or (not importes and re.search(r"gratuit|entrada libre|acceso libre", texto, re.I)):
        return True, 0.0
    return False, (min(importes) if importes else None)


def parsear_duracion(texto: str) -> Optional[int]:
    """'1 hora, 30 min' / '2 HORAS, 30 MIN' / '45 min' -> minutos."""
    h = re.search(r"(\d+)\s*hora", texto or "", re.I)
    m = re.search(r"(\d+)\s*min", texto or "", re.I)
    if not h and not m:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def horario_taller(fila: dict):
    """Primer día con horario -> (hora_inicio, duracion_min). Los talleres traen una columna por día."""
    for col, _, _ in DIAS:
        hora = fila.get(f"HORA_INICIO_{col}", "").strip()
        if hora:
            return hora, parsear_duracion(fila.get(f"DURACION_ACTIVIDAD_{col}", ""))
    return "", None


def texto_dias(dias_semana: str) -> str:
    """'L,X' -> 'lunes y miércoles'"""
    nombres = [NOMBRE_DIA[d] for d in dias_semana.replace(" ", "").split(",") if d in NOMBRE_DIA]
    if len(nombres) <= 1:
        return nombres[0] if nombres else ""
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def direccion(fila: dict) -> str:
    via = " ".join(p for p in (fila["CLASE-VIAL-INSTALACION"], fila["NOMBRE-VIA-INSTALACION"]) if p).strip()
    return f'{via}, {fila["NUM-INSTALACION"]}' if via and fila["NUM-INSTALACION"] else via


# ---------- Carga del CSV (una sola vez) ----------

@lru_cache(maxsize=1)
def cargar_eventos() -> list[dict]:
    hoy = date.today()
    eventos = []
    # utf-8-sig: el CSV trae BOM. delimiter=";": este CSV usa punto y coma.
    with open(RUTA_CSV, mode="r", encoding="utf-8-sig", newline="") as f:
        for n, fila in enumerate(csv.DictReader(f, delimiter=";")):
            es_taller = fila["FUENTE"] == "Talleres"
            if es_taller and not INCLUIR_TALLERES:
                continue

            inicio = a_fecha(fila["FECHA"])
            fin = a_fecha(fila["FECHA-FIN"]) or inicio

            # Descarta eventos con fecha ya pasada (también elimina la fuente "Banda", que es de 2025).
            if not es_taller and (fin is None or fin < hoy):
                continue

            if es_taller:
                hora_inicio, duracion = horario_taller(fila)
                estado = "recurrente"
            else:
                hora_inicio, duracion = fila["HORA"].strip(), None  # la agenda no trae duración
                en_curso = inicio and fin and inicio < fin and inicio <= hoy
                estado = "en_curso" if en_curso else "proximo"

            gratis, precio = parsear_precio(fila["PRECIO"], fila["GRATUITO"])
            if es_taller:
                gratis, precio = False, None  # los talleres no traen precio

            grupo = GRUPO_DE.get(normalizar(fila["CATEGORIA"]), GRUPO_OTROS)

            eventos.append({
                # Datos para mostrar en el HTML
                "id": fila["ID-EVENTO"] or f"{fila['FUENTE'].lower()}-{n}",
                "titulo": fila["TITULO"],
                "grupo": grupo["id"],
                "grupo_nombre": grupo["nombre"],
                "color": grupo["color"],
                "categoria": normalizar(fila["CATEGORIA"]),
                "categoria_nombre": fila["CATEGORIA"],
                "subcategoria": "",
                "gratis": gratis,
                "precio": precio,
                "precio_texto": fila["PRECIO"].replace("\xa0", " ").strip(),
                "fecha_inicio": inicio.isoformat() if inicio else "",
                "fecha_fin": fin.isoformat() if fin else "",
                "hora_inicio": hora_inicio,
                "hora_fin": "",
                "duracion_min": duracion,  # None = desconocida
                "estado": estado,
                "dias_texto": texto_dias(fila["DIAS-SEMANA"]) if es_taller else "",
                "publico": fila["PUBLICO"].strip(),
                "lugar_nombre": fila["LUGAR"],
                "direccion": direccion(fila),
                "distrito": fila["DISTRITO"].title(),
                "barrio": fila["BARRIO-INSTALACION"].title(),
                "lat": a_numero(fila["LATITUD"]),
                "lon": a_numero(fila["LONGITUD"]),
                "descripcion": fila["DESCRIPCION"],
                "url": fila["URL-ACTIVIDAD"] or fila["CONTENT-URL"],
                # Campos internos para filtrar (se quitan antes de responder)
                "_hora": a_hora(hora_inicio),
            })

    # Primero los eventos con fecha (por fecha y hora); los talleres, al final.
    eventos.sort(key=lambda e: (e["estado"] == "recurrente", e["fecha_inicio"], e["hora_inicio"]))
    return eventos


def publico(evento: dict) -> dict:
    return {k: v for k, v in evento.items() if not k.startswith("_")}


# ---------- Endpoints ----------

@app.get("/api/categorias")
def obtener_categorias():
    """Categorías de la web (con número de eventos) para pintar los filtros en el HTML."""
    cuenta = {}
    for e in cargar_eventos():
        cuenta[e["grupo"]] = cuenta.get(e["grupo"], 0) + 1
    return [
        {"id": g["id"], "nombre": g["nombre"], "color": g["color"], "total": cuenta.get(g["id"], 0)}
        for g in GRUPOS
    ]


@app.get("/api/eventos")
def obtener_eventos(
    categoria: Optional[str] = Query(None, description="id de /api/categorias; varias separadas por coma. Ej: musica,espectaculos"),
    duracion_min: Optional[int] = Query(None, ge=0, description="Minutos"),
    duracion_max: Optional[int] = Query(None, ge=0, description="Minutos"),
    inicio_desde: Optional[str] = Query(None, pattern=r"^\d{2}:\d{2}$", description="HH:MM"),
    inicio_hasta: Optional[str] = Query(None, pattern=r"^\d{2}:\d{2}$", description="HH:MM"),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
):
    cats = {normalizar(c) for c in categoria.split(",") if c.strip()} if categoria else None
    desde = a_hora(inicio_desde) if inicio_desde else None
    hasta = a_hora(inicio_hasta) if inicio_hasta else None

    resultados = []

    for e in cargar_eventos():
        # Categoría (por grupo de la web; admite varias)
        if cats and e["grupo"] not in cats:
            continue

        # Duración (los eventos sin duración conocida quedan fuera si filtras por duración)
        if duracion_min is not None or duracion_max is not None:
            if e["duracion_min"] is None:
                continue
            if duracion_min is not None and e["duracion_min"] < duracion_min:
                continue
            if duracion_max is not None and e["duracion_min"] > duracion_max:
                continue

        # Hora de inicio (los eventos sin hora quedan fuera si filtras por hora)
        if desde or hasta:
            if e["_hora"] is None:
                continue
            if desde and e["_hora"] < desde:
                continue
            if hasta and e["_hora"] > hasta:
                continue

        # Precio (los eventos con precio desconocido quedan fuera si filtras por precio)
        if precio_min is not None or precio_max is not None:
            if e["precio"] is None:
                continue
            if precio_min is not None and e["precio"] < precio_min:
                continue
            if precio_max is not None and e["precio"] > precio_max:
                continue

        resultados.append(publico(e))

    return {"total": len(resultados), "eventos": resultados}

app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")
#ola