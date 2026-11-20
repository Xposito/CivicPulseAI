import csv
import unicodedata
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API de eventos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción cambia "*" por tu dominio
    allow_methods=["*"],
    allow_headers=["*"],
)

# main.py junto a la carpeta data/. Si main.py está dentro de data/, quita "data".
RUTA_CSV = Path(__file__).parent / "data" / "eventos.csv"

# Categorías de la web -> categorías del CSV que agrupan.
# "id" es lo que envía el HTML en ?categoria=...
GRUPOS = [
    {"id": "cursos_talleres", "nombre": "Cursos y talleres",          "csv": ["taller"],        "color": None},
    {"id": "musica",          "nombre": "Música",                     "csv": ["musica"],        "color": None},
    {"id": "teatro",          "nombre": "Teatro y circo",             "csv": ["teatro"],        "color": None},
    {"id": "cine",            "nombre": "Cine",                       "csv": ["cine"],          "color": None},
    {"id": "deporte",         "nombre": "Deporte",                    "csv": ["deporte"],       "color": None},
    {"id": "infantil",        "nombre": "Infantil",                   "csv": ["infantil"],      "color": None},
    {"id": "conferencias",    "nombre": "Conferencias",               "csv": ["conferencia"],   "color": None},
    {"id": "exposicion",      "nombre": "Exposición",                 "csv": ["exposicion"],    "color": None},
    {"id": "fiestas",         "nombre": "Fiestas y festivales",       "csv": ["fiestas"],       "color": "rosa"},
    {"id": "danza",           "nombre": "Danza",                      "csv": ["danza"],         "color": None},
    {"id": "literatura",      "nombre": "Literatura y recitales",     "csv": ["literatura"],    "color": None},
    {"id": "visitas",         "nombre": "Visitas e itinerarios",      "csv": ["visita_guiada"], "color": None},
    {"id": "aire_libre",      "nombre": "Aire libre y medio ambiente", "csv": ["aire_libre"],   "color": None},
    {"id": "club_lectura",    "nombre": "Club de lectura",            "csv": ["club_lectura"],  "color": None},
    {"id": "otros",           "nombre": "Otros",                      "csv": ["otros"],         "color": "gris"},
]

# Búsqueda inversa: categoría del CSV -> grupo
GRUPO_DE = {c: g for g in GRUPOS for c in g["csv"]}
GRUPO_OTROS = GRUPO_DE["otros"]  # categorías nuevas o desconocidas caen aquí


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


# ---------- Carga del CSV (una sola vez) ----------

@lru_cache(maxsize=1)
def cargar_eventos() -> list[dict]:
    eventos = []
    # utf-8-sig por si el CSV trae BOM (típico al guardar desde Excel)
    with open(RUTA_CSV, mode="r", encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f, delimiter=","):
            gratis = fila["gratis"].strip().lower() == "true"
            precio = 0.0 if gratis else a_numero(fila["precio_min"])  # None = precio desconocido

            grupo = GRUPO_DE.get(fila["categoria"], GRUPO_OTROS)

            eventos.append({
                # Datos para mostrar en el HTML
                "id": fila["id"],
                "titulo": fila["titulo"],
                "grupo": grupo["id"],
                "grupo_nombre": grupo["nombre"],
                "color": grupo["color"],
                "categoria": fila["categoria"],
                "categoria_nombre": fila["categoria_nombre"],
                "subcategoria": fila["subcategoria"],
                "gratis": gratis,
                "precio": precio,
                "precio_texto": fila["precio_texto"],
                "fecha_inicio": fila["fecha_inicio"],
                "fecha_fin": fila["fecha_fin"],
                "hora_inicio": fila["hora_inicio"],
                "hora_fin": fila["hora_fin"],
                "duracion_min": int(a_numero(fila["duracion_min"]) or 0),
                "estado": fila["estado"],
                "publico": fila["publico"],
                "lugar_nombre": fila["lugar_nombre"],
                "direccion": fila["direccion"],
                "distrito": fila["distrito"],
                "barrio": fila["barrio"],
                "lat": a_numero(fila["lat"]),
                "lon": a_numero(fila["lon"]),
                "descripcion": fila["descripcion"],
                "url": fila["url"],
                # Campos internos para filtrar (se quitan antes de responder)
                "_hora": a_hora(fila["hora_inicio"]),
            })
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
    categoria: Optional[str] = Query(None, description="id de /api/categorias; varias separadas por coma. Ej: musica,teatro"),
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

        # Duración
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