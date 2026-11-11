"""Helpers de conexion SQLite.

Convencion: el pipeline escribe; el dashboard abre en modo solo lectura.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from agrodb.schemas import SCHEMAS

DB_DIR = Path(os.environ.get("DB_DIR", "data"))


def db_path(name: str, db_dir: Path | str | None = None) -> Path:
    """Ruta absoluta de una base de datos por nombre (p. ej. 'weather.db')."""
    directory = Path(db_dir) if db_dir else DB_DIR
    return directory / name


def get_conn(name: str, db_dir: Path | str | None = None) -> sqlite3.Connection:
    """Conexion de escritura (crea el directorio y el esquema si no existen)."""
    path = db_path(name, db_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMAS[name])
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_ro_conn(name: str, db_dir: Path | str | None = None) -> sqlite3.Connection:
    """Conexion de solo lectura. Falla si la base no existe."""
    path = db_path(name, db_dir)
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def init_dbs(db_dir: Path | str | None = None) -> dict[str, Path]:
    """Crea las 3 bases con su esquema. Devuelve {nombre: ruta}."""
    paths = {}
    for name in SCHEMAS:
        conn = get_conn(name, db_dir)
        conn.close()
        paths[name] = db_path(name, db_dir)
    return paths
