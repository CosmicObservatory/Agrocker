"""Catalogo canonico de estados de Mexico.

Fuente geometrica: mexico_states.geojson (32 entidades, click_that_hood).
Los centroides se aproximan promediando las coordenadas de los anillos
exteriores; son suficientes para muestrear clima a nivel estatal.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

_GEOJSON = Path(__file__).with_name("mexico_states.geojson")

# Aliases: nombre normalizado (sin acentos, mayusculas) -> nombre canonico del geojson
_ALIASES = {
    "DISTRITO FEDERAL": "Distrito Federal",
    "CDMX": "Distrito Federal",
    "MEXICO DF": "Distrito Federal",
    "CIUDAD DE MEXICO": "Distrito Federal",
    "MICHOACAN": "Michoacán de Ocampo",
    "MICHOACAN DE OCAMPO": "Michoacán de Ocampo",
    "VERACRUZ": "Veracruz de Ignacio de la Llave",
    "VERACRUZ DE IGNACIO DE LA LLAVE": "Veracruz de Ignacio de la Llave",
    "QUERETARO": "Querétaro",
    "YUCATAN": "Yucatán",
    "COAHUILA": "Coahuila de Zaragoza",
    "NUEVO LEON": "Nuevo León",
    "SAN LUIS POTOSI": "San Luis Potosí",
    "BAJA CALIFORNIA SUR": "Baja California Sur",
    "AGUASCALIENTES": "Aguascalientes",
    "DURANGO": "Durango",
    "MEXICO": "México",
    "MORELOS": "Morelos",
    "TLAXCALA": "Tlaxcala",
    "PUEBLA": "Puebla",
    "HIDALGO": "Hidalgo",
    "GUANAJUATO": "Guanajuato",
    "JALISCO": "Jalisco",
    "CHIHUAHUA": "Chihuahua",
    "SONORA": "Sonora",
    "SINALOA": "Sinaloa",
    "NAYARIT": "Nayarit",
    "COLIMA": "Colima",
    "ZACATECAS": "Zacatecas",
    "TAMAULIPAS": "Tamaulipas",
    "CAMPECHE": "Campeche",
    "QUINTANA ROO": "Quintana Roo",
    "YUCATAN": "Yucatán",
    "CHIAPAS": "Chiapas",
    "TABASCO": "Tabasco",
    "OAXACA": "Oaxaca",
    "GUERRERO": "Guerrero",
}


def _norm(name: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn"
    ).strip().upper()


@lru_cache(maxsize=1)
def load_states() -> list[dict]:
    """Devuelve [{clave, nombre, lat, lon}] para las 32 entidades."""
    data = json.loads(_GEOJSON.read_text(encoding="utf-8"))
    states = []
    for i, feat in enumerate(data["features"], start=1):
        nombre = feat["properties"]["name"]
        coords = _exterior_coords(feat["geometry"])
        if not coords:
            continue
        lat = sum(c[1] for c in coords) / len(coords)
        lon = sum(c[0] for c in coords) / len(coords)
        states.append(
            {"clave": f"{i:02d}", "nombre": nombre, "lat": lat, "lon": lon}
        )
    return states


def _exterior_coords(geom: dict) -> list[list[float]]:
    """Coordenadas del primer anillo exterior de la primera parte."""
    gtype = geom["type"]
    coords = geom["coordinates"]
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = coords[0][0]
    else:
        return []
    # Submuestreo para no promediar millones de vértices
    step = max(1, len(ring) // 2000)
    return ring[::step]


def canonical_state(name: str) -> str | None:
    """Normaliza un nombre de estado (p. ej. desde DGSIAP) al canonico."""
    key = _norm(name)
    if key in _ALIASES:
        return _ALIASES[key]
    for state in load_states():
        if _norm(state["nombre"]) == key:
            return state["nombre"]
    return None
