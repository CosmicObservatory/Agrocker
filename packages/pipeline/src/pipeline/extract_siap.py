"""Extraccion de produccion agricola DGSIAP.

Los datos abiertos de DGSIAP (nube.agricultura.gob.mx/datosAbiertos)
publican CSV por ano, nivel municipal, con superficie, produccion,
rendimiento y precio. El extractor:

1. Descubre los enlaces CSV desde la pagina de datos abiertos (o usa
   SIAP_BASE_URL / SIAP_LOCAL_DIR si se configuran).
2. Descarga y parsea cada CSV (latin-1) normalizando columnas.
3. Agrega municipio -> estado canonico y carga en production.db.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import requests

from agrodb import canonical_state, get_conn, load_states
from pipeline.config import Config

log = logging.getLogger(__name__)

OPEN_DATA_URL = "https://nube.agricultura.gob.mx/datosAbiertos/Agricola.php"

# Mapeo flexible de encabezados DGSIAP -> columnas internas
_HEADER_MAP = {
    "estado": "estado",
    "entidad": "estado",
    "municipio": "municipio",
    "ciclo": "ciclo",
    "clave": "clave_cultivo",
    "cveproducto": "clave_cultivo",
    "cve_cultivo": "clave_cultivo",
    "cultivo": "cultivo",
    "descripcion": "cultivo",
    "modalidad": "tipo_riego",
    "tipode riego": "tipo_riego",
    "tipo de riego": "tipo_riego",
    "tipo_riego": "tipo_riego",
    "anio": "anio",
    "year": "anio",
    "superficie": "superficie_ha",
    "superficie sembrada": "superficie_ha",
    "produccion": "produccion_t",
    "producción": "produccion_t",
    "volumen": "produccion_t",
    "rendimiento": "rendimiento_t_ha",
    "precio medio": "precio_ton",
    "precio": "precio_ton",
}


def _discover_csv_urls(cfg: Config) -> list[str]:
    if cfg.siap_base_url:
        return [cfg.siap_base_url]
    try:
        html = requests.get(OPEN_DATA_URL, timeout=30).text
    except requests.RequestException as exc:
        log.error("No se pudo obtener la pagina de datos abiertos: %s", exc)
        return []
    urls = re.findall(r'href=["\']([^"\']+\.csv[^"\']*)', html, flags=re.I)
    urls = [u if u.startswith("http") else f"https://nube.agricultura.gob.mx{u}"
            for u in urls]
    log.info("CSV DGSIAP descubiertos: %s", len(urls))
    return urls


def _local_csvs(cfg: Config) -> list[Path]:
    if not cfg.siap_local_dir:
        return []
    return sorted(Path(cfg.siap_local_dir).glob("*.csv"))


def _normalize(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename = {}
    for col in df.columns:
        key = re.sub(r"\s+", " ", col).strip()
        if key in _HEADER_MAP:
            rename[col] = _HEADER_MAP[key]
    df = df.rename(columns=rename)

    # Anio desde el nombre del archivo si no hay columna
    m = re.search(r"(19|20)\d{2}", source_name)
    if "anio" not in df.columns and m:
        df["anio"] = int(m.group(0))

    for col in ("estado", "municipio", "cultivo", "ciclo", "tipo_riego"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        else:
            df[col] = ""
    if "estado" in df.columns:
        df["estado"] = df["estado"].map(lambda s: canonical_state(s) or s)
    for col in ("anio", "superficie_ha", "produccion_t", "rendimiento_t_ha", "precio_ton"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA
    keep = [
        "estado", "municipio", "clave_cultivo", "cultivo", "anio",
        "ciclo", "tipo_riego", "superficie_ha", "produccion_t",
        "rendimiento_t_ha", "precio_ton",
    ]
    for col in keep:
        if col not in df.columns:
            df[col] = "" if col not in ("anio",) else pd.NA
    df["clave_cultivo"] = df["clave_cultivo"].fillna("").astype(str)
    return df[keep]


def _load_csv(path_or_url: str) -> pd.DataFrame | None:
    try:
        if path_or_url.startswith("http"):
            resp = requests.get(path_or_url, timeout=120)
            resp.raise_for_status()
            df = pd.read_csv(
                pd.io.common.BytesIO(resp.content), sep=None, engine="python",
                encoding="latin-1", low_memory=False,
            )
        else:
            df = pd.read_csv(path_or_url, sep=None, engine="python",
                             encoding="latin-1", low_memory=False)
    except Exception as exc:  # CSVs DGSIAP tienen formatos irregulares
        log.warning("No se pudo parsear %s: %s", path_or_url, exc)
        return None
    return df


def _fixture_production() -> pd.DataFrame:
    """Muestra sintetica determinista para demo sin CSVs DGSIAP."""
    import random
    rng = random.Random(7)
    from agrodb import load_states
    rows = []
    base_yield = {
        "maiz": 3.8, "frijol": 1.2, "trigo": 3.5, "sorgo": 2.8,
        "cebada": 3.0, "avena": 2.6, "soya": 2.2, "algodon": 1.5,
        "canola": 1.8, "fresa": 22.0, "tomate": 35.0, "cebolla": 22.0,
        "ajo": 10.0, "chile seco": 1.6, "papa": 22.0,
    }
    for estado in load_states():
        e = estado["nombre"]
        for nombre, y0 in base_yield.items():
            for anio in range(2020, 2026):
                ciclo = "PV" if rng.random() < 0.6 else "OI"
                riego = "asegurado" if ciclo == "OI" else rng.choice(
                    ["temporal", "asegurado"])
                y = y0 * rng.uniform(0.7, 1.3)
                sup = round(rng.uniform(500, 80000), 1)
                rows.append({
                    "estado": e, "municipio": "(estado)",
                    "clave_cultivo": nombre[:10], "cultivo": nombre.upper(),
                    "anio": anio, "ciclo": ciclo, "tipo_riego": riego,
                    "superficie_ha": sup, "produccion_t": round(sup * y, 1),
                    "rendimiento_t_ha": round(y, 3),
                    "precio_ton": round(rng.uniform(4000, 25000), 0),
                })
    return pd.DataFrame(rows)


def run(cfg: Config) -> dict:
    """Punto de entrada del extractor DGSIAP."""
    conn = get_conn("production.db", cfg.db_dir)

    # Catalogo geoespacial de referencia
    for s in load_states():
        conn.execute(
            "INSERT OR IGNORE INTO geo_states (clave, nombre, lat, lon) VALUES (?,?,?,?)",
            (s["clave"], s["nombre"], s["lat"], s["lon"]),
        )
    conn.commit()

    files = _local_csvs(cfg)
    urls = _discover_csv_urls(cfg) if not files else []
    total_rows = 0

    for url in urls:
        df = _load_csv(url)
        if df is None or df.empty:
            continue
        df = _normalize(df, url)
        total_rows += _insert(conn, df)
        log.info("Cargado %s: %s filas", url.rsplit("/", 1)[-1], len(df))

    for path in files:
        df = _load_csv(str(path))
        if df is None or df.empty:
            continue
        df = _normalize(df, path.name)
        total_rows += _insert(conn, df)
        log.info("Cargado %s: %s filas", path.name, len(df))

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM production").fetchone()[0]
    if n == 0:
        df = _fixture_production()
        total_rows += _insert(conn, df)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM production").fetchone()[0]
        log.warning("DGSIAP sin datos reales: %s filas fixture de produccion", len(df))
    conn.close()
    log.info("Produccion DGSIAP: %s filas nuevas, %s en production.db", total_rows, n)
    return {"rows_new": total_rows, "total": n}


def _insert(conn, df: pd.DataFrame) -> int:
    rows = [
        (
            r.estado, r.municipio, str(r.clave_cultivo), r.cultivo,
            int(r.anio), r.ciclo, r.tipo_riego,
            _num(r.superficie_ha), _num(r.produccion_t),
            _num(r.rendimiento_t_ha), _num(r.precio_ton),
        )
        for r in df.itertuples(index=False)
        if pd.notna(r.anio)
    ]
    conn.executemany(
        """INSERT OR REPLACE INTO production
           (estado, municipio, clave_cultivo, cultivo, anio, ciclo, tipo_riego,
            superficie_ha, produccion_t, rendimiento_t_ha, precio_ton)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return len(rows)


def _num(v) -> float | None:
    try:
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
