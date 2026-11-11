"""Catalogo de cultivos de referencia y datos semilla.

Los parametros agronomicos son editables: se cargan en la tabla `crops`
de production.db con INSERT OR IGNORE, por lo que el usuario puede
actualizarlos directamente en SQLite sin perderlos en re-ejecuciones.
"""

from __future__ import annotations

import logging

from agrodb import get_conn

log = logging.getLogger(__name__)

# clave, nombre, ciclo_meses, t_min, t_opt_min, t_opt_max, t_max,
# precip_anual_mm, riego_recomendado, rend_potencial_t_ha, precio_ref_ton
DEFAULT_CROPS = [
    ("maiz", "Maiz", 6, 10, 18, 34, 40, 700, "ambos", 4.5, 5200),
    ("frijol", "Frijol", 4, 12, 20, 28, 35, 500, "temporal", 1.5, 18000),
    ("trigo", "Trigo", 6, 8, 15, 25, 32, 450, "asegurado", 4.0, 6200),
    ("sorgo", "Sorgo", 4, 15, 22, 32, 38, 400, "temporal", 3.0, 4800),
    ("cebada", "Cebada", 5, 5, 12, 22, 30, 400, "asegurado", 3.5, 5600),
    ("avena", "Avena", 5, 5, 12, 22, 30, 450, "asegurado", 3.0, 7000),
    ("soya", "Soya", 4, 15, 22, 30, 38, 600, "ambos", 2.5, 9800),
    ("algodon", "Algodon", 7, 15, 22, 32, 40, 700, "asegurado", 1.8, 15000),
    ("canola", "Canola", 5, 5, 12, 22, 28, 500, "ambos", 2.0, 11000),
    ("fresa", "Fresa", 6, 5, 15, 25, 32, 900, "asegurado", 25.0, 25000),
    ("tomate", "Tomate", 4, 15, 20, 28, 35, 800, "asegurado", 40.0, 14000),
    ("cebolla", "Cebolla", 5, 10, 18, 26, 33, 600, "ambos", 25.0, 12000),
    ("ajo", "Ajo", 7, 10, 18, 26, 33, 500, "ambos", 12.0, 35000),
    ("chile", "Chile seco", 5, 15, 22, 30, 38, 500, "temporal", 1.8, 22000),
    ("papa", "Papa", 4, 10, 16, 24, 30, 600, "asegurado", 25.0, 9000),
]


def seed_crops(conn) -> int:
    conn.executemany(
        """INSERT OR IGNORE INTO crops
           (clave, nombre, ciclo_productivo_meses, temp_min, temp_opt_min,
            temp_opt_max, temp_max, precip_annual_mm, riego_recomendado,
            rendimiento_potencial_t_ha, precio_ref_ton)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        DEFAULT_CROPS,
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM crops").fetchone()[0]
    log.info("Catalogo de cultivos: %s cultivos", n)
    return n
