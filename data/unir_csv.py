#!/usr/bin/env python3
"""
Une los 4 CSV originales de datos.madrid.es en una sola tabla (outer join por
columnas: se conservan TODAS las columnas de todos los ficheros).

    python3 data/unir_csv.py   ->  data/actividades_unidas.csv

Entradas (data/originales/, tal cual se descargan del portal):
  - 300107-2-agenda-actividades-eventos.csv   (Agenda, latin-1, ';')
  - 206717-4-agenda-eventos-bibliotecas.csv   (Bibliotecas, latin-1, ';', mismas columnas que Agenda)
  - 50064-45-talleres-culturales-cursos.csv   (Talleres, UTF-8 con BOM, ';')
  - 135161-1-conciertos-banda-sinfonica.csv   (Banda Sinfónica, UTF-8 con BOM, ';')

Reglas acordadas con el equipo:
  - Columnas equivalentes se juntan en una sola (tabla EQUIVALENCIAS).
  - El resto de columnas se mantienen con su nombre original y quedan vacías
    en las filas de los ficheros que no las tienen.
  - Bibliotecas: los eventos cuyo ID-EVENTO ya está en Agenda se descartan
    (se queda la versión de Agenda).
  - Los valores se copian tal cual, sin limpiar. Solo se construyen:
      FECHA y DIAS-SEMANA de Banda (de AÑO+MES+DÍA) y DIAS-SEMANA de Talleres
      (días con HORA_INICIO_<día> rellena).
  - CATEGORIA: una de las 15 categorías de CATEGORIAS_FINALES.
      Agenda/Bibliotecas: según TIPO, palabras clave del título/descripción,
      nombre del lugar y las reglas de revisión de "otros" (las mismas de
      descargar_y_normalizar.py). Talleres: "Cursos y talleres". Banda: "Música".
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from descargar_y_normalizar import CATEGORIAS, categoria_evento  # mismas reglas que el resto de datos

CARPETA = Path(__file__).resolve().parent
ORIG = CARPETA / "originales"

FICHEROS = {
    "Agenda": ("300107-2-agenda-actividades-eventos.csv", "latin-1"),
    "Bibliotecas": ("206717-4-agenda-eventos-bibliotecas.csv", "latin-1"),
    "Talleres": ("50064-45-talleres-culturales-cursos.csv", "utf-8-sig"),
    "Banda": ("135161-1-conciertos-banda-sinfonica.csv", "utf-8-sig"),
}

# columna unificada -> columna original en cada fichero (Bibliotecas = Agenda)
EQUIVALENCIAS = {
    "TITULO":       {"Agenda": "TITULO", "Talleres": "ACTIVIDAD_DESC", "Banda": "NOMBRE CONCIERTO"},
    "LUGAR":        {"Agenda": "NOMBRE-INSTALACION", "Talleres": "ORGANISMO_DESC", "Banda": "UBICACIÓN"},
    "DISTRITO":     {"Agenda": "DISTRITO-INSTALACION", "Talleres": "DISTRITO_DESC"},
    "FECHA":        {"Agenda": "FECHA"},
    "FECHA-FIN":    {"Agenda": "FECHA-FIN"},
    "HORA":         {"Agenda": "HORA"},
    "DIAS-SEMANA":  {"Agenda": "DIAS-SEMANA"},
    "PUBLICO":      {"Agenda": "AUDIENCIA", "Talleres": "DESTINATARIO_DESC"},
    "TIPO":         {"Agenda": "TIPO", "Banda": "TIPO"},
}

CATEGORIAS_FINALES = [
    "Cursos y talleres", "Música", "Teatro y circo", "Cine", "Deporte", "Infantil", "Conferencias",
    "Exposición", "Fiestas y festivales", "Danza", "Literatura y recitales", "Visitas e itinerarios",
    "Aire libre y medio ambiente", "Club de lectura", "Otros",
]


def categoria(fuente, f):
    if fuente == "Talleres":
        return "Cursos y talleres"
    if fuente == "Banda":
        return "Música"
    tipo = (f.get("TIPO") or "").replace("/contenido/actividades/", "/kos/actividades/")
    cat, _, _ = categoria_evento(tipo, f"{f.get('TITULO', '')} {f.get('DESCRIPCION', '')}", None,
                                 f.get("NOMBRE-INSTALACION", ""), f.get("TITULO", ""))
    nombre = CATEGORIAS.get(cat, "Otros")
    return nombre if nombre in CATEGORIAS_FINALES else "Otros"


MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                                     "agosto", "septiembre", "octubre", "noviembre", "diciembre"], 1)}
DIAS_TALLERES = [("LUNES", "L"), ("MARTES", "M"), ("MIERCOLES", "X"), ("JUEVES", "J"),
                 ("VIERNES", "V"), ("SABADO", "S"), ("DOMINGO", "D")]


def leer(nombre):
    fichero, codif = FICHEROS[nombre]
    with open(ORIG / fichero, encoding=codif, newline="") as f:
        filas = list(csv.reader(f, delimiter=";"))
    cab = [c.strip() for c in filas[0]]  # " ID-EVENTO" trae un espacio delante
    datos = []
    for fila in filas[1:]:
        if not any(v.strip() for v in fila):
            continue  # filas vacías al final del fichero
        datos.append({c: v for c, v in zip(cab, fila) if c})  # columnas sin nombre (vacías) fuera
    return [c for c in cab if c], datos


def main():
    tablas = {n: leer(n) for n in FICHEROS}

    # Bibliotecas: fuera los que ya están en Agenda
    ids_agenda = {f["ID-EVENTO"] for f in tablas["Agenda"][1]}
    cab_b, filas_b = tablas["Bibliotecas"]
    quitados = sum(1 for f in filas_b if f["ID-EVENTO"] in ids_agenda)
    tablas["Bibliotecas"] = (cab_b, [f for f in filas_b if f["ID-EVENTO"] not in ids_agenda])

    # Columnas de salida: FUENTE + unificadas + resto de columnas originales sin pareja
    usadas = {n: set() for n in FICHEROS}
    for mapa in EQUIVALENCIAS.values():
        for n, col in mapa.items():
            usadas[n].add(col)
    usadas["Bibliotecas"] = usadas["Agenda"]
    columnas = ["FUENTE", "CATEGORIA"] + list(EQUIVALENCIAS)
    for n, (cab, _) in tablas.items():
        for c in cab:
            if c not in usadas[n] and c not in columnas:
                columnas.append(c)

    salida = []
    for n, (cab, filas) in tablas.items():
        base = "Agenda" if n == "Bibliotecas" else n
        for f in filas:
            fila = {"FUENTE": n, "CATEGORIA": categoria(n, f)}
            for uni, mapa in EQUIVALENCIAS.items():
                if base in mapa:
                    fila[uni] = f.get(mapa[base], "")
            for c in cab:
                if c not in usadas[n]:
                    fila[c] = f.get(c, "")
            if n == "Banda":
                try:
                    mes = MESES[f["MES"].strip().lower()]
                    fila["FECHA"] = f"{int(f['AÑO']):04d}-{mes:02d}-{int(f['DÍA']):02d} 00:00:00.0"
                except (KeyError, ValueError):
                    pass
            if n == "Talleres":
                fila["DIAS-SEMANA"] = ",".join(letra for dia, letra in DIAS_TALLERES
                                               if f.get(f"HORA_INICIO_{dia}", "").strip())
            salida.append(fila)

    destino = CARPETA / "actividades_unidas.csv"
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, delimiter=";", restval="")
        w.writeheader()
        w.writerows(salida)

    print(f"{destino.name}: {len(salida)} filas, {len(columnas)} columnas")
    for n, (_, filas) in tablas.items():
        print(f"  {n}: {len(filas)} filas")
    print(f"  Bibliotecas descartadas por estar ya en Agenda: {quitados}")
    cuenta = {}
    for fila in salida:
        cuenta[fila["CATEGORIA"]] = cuenta.get(fila["CATEGORIA"], 0) + 1
    assert set(cuenta) <= set(CATEGORIAS_FINALES), set(cuenta) - set(CATEGORIAS_FINALES)
    print("  CATEGORIA:", dict(sorted(cuenta.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
