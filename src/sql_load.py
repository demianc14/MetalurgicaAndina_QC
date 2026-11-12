"""Capa SQL: carga la salida limpia en SQLite (modelo estrella) y crea las vistas.

Uso:
  python -m src.sql_load     # escribe data/processed/metalurgica.db y los CSV de las vistas

`sql/schema.sql` define el modelo y `sql/vistas.sql` las vistas que
reproducen las tablas dinámicas del Excel. Los CSV de las vistas pueden
ser la fuente de Power BI: datos ya limpios y reproducibles.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.etl.extract import ABR_MAY, extract_dataset
from src.etl.load import PROCESSED_DIR
from src.pipeline import Resultado, run_all

SQL_DIR = Path("sql")
DB_PATH = PROCESSED_DIR / "metalurgica.db"
VISTAS_DIR = PROCESSED_DIR / "vistas"


def _iso(serie: pd.Series) -> pd.Series:
    """Fechas a texto ISO; los faltantes quedan como None (NULL en SQL)."""
    fechas = pd.to_datetime(serie)
    return fechas.dt.strftime("%Y-%m-%d").where(fechas.notna(), None)


def build_database(resultado: Resultado, db_path: Path | str = ":memory:") -> sqlite3.Connection:
    """Crea el modelo estrella, lo llena con `resultado` y crea las vistas."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))

    p = resultado.produccion
    _, catalogo = extract_dataset(ABR_MAY)  # el catálogo es idéntico en ambos archivos

    catalogo.rename(columns=str.lower).to_sql("dim_producto", conn, if_exists="append", index=False)

    lineas = sorted(p["Linea_Produccion"].unique())
    turnos = sorted(p["Turno"].unique())
    conn.executemany("INSERT INTO dim_linea VALUES (?, ?)", list(enumerate(lineas, start=1)))
    conn.executemany("INSERT INTO dim_turno VALUES (?, ?)", list(enumerate(turnos, start=1)))
    linea_id = {linea: i for i, linea in enumerate(lineas, start=1)}
    turno_id = {turno: i for i, turno in enumerate(turnos, start=1)}

    fechas = pd.to_datetime(p["Fecha"]).dropna().drop_duplicates().sort_values()
    pd.DataFrame({
        "fecha": fechas.dt.strftime("%Y-%m-%d"),
        "anio": fechas.dt.year,
        "mes": fechas.dt.month,
        "dia": fechas.dt.day,
    }).to_sql("dim_fecha", conn, if_exists="append", index=False)

    pd.DataFrame({
        "id_registro": p["ID_Registro"],
        "origen": p["Origen"],
        "fecha": _iso(p["Fecha"]),
        "linea_id": p["Linea_Produccion"].map(linea_id),
        "turno_id": p["Turno"].map(turno_id),
        "sku": p["SKU"],
        "cantidad_producida": p["Cantidad_Producida"],
        "unidades_defectuosas": p["Unidades_Defectuosas"],
        "tiempo_paro_min": p["Tiempo_Paro_Min"],
        "costo_total": p["Costo_total"],
        "ventas_totales": p["Ventas_totales"],
        "profit": p["Profit"],
        "tasa_defectuosos": p["Tasa_defectuosos"],
        "clasificacion": p["Clasificacion"],
        "cumple": p["Cumple"],
        "turno_problematico": p["Turno_problematico"],
    }).to_sql("fact_produccion", conn, if_exists="append", index=False)

    ped = resultado.pedidos
    pd.DataFrame({
        "id_pedido": ped["ID_Pedido"],
        "fecha_pedido": _iso(ped["Fecha_Pedido"]),
        "fecha_entrega_programada": _iso(ped["Fecha_Entrega_Programada"]),
        "fecha_entrega_real": _iso(ped["Fecha_Entrega_Real"]),
        "cliente": ped["Cliente"],
        "sku": ped["SKU"],
        "cantidad": ped["Cantidad"],
        "ciudad_destino": ped["Ciudad_Destino"],
        "desvio": ped["desvio"].astype("Int64"),
        "estado_entrega": ped["estado_entrega"],
        "ingreso_usd": ped["ingreso_usd"],
        "costo_usd": ped["costo_usd"],
        "margen_usd": ped["margen_usd"],
    }).to_sql("fact_pedidos", conn, if_exists="append", index=False)

    conn.executescript((SQL_DIR / "vistas.sql").read_text(encoding="utf-8"))
    conn.commit()
    return conn


def vistas(conn: sqlite3.Connection) -> list[str]:
    """Nombres de las vistas creadas por sql/vistas.sql."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name")
    return [name for (name,) in rows]


def export_vistas(conn: sqlite3.Connection, dir_path: Path = VISTAS_DIR) -> dict[str, Path]:
    """Escribe cada vista como CSV (fuente posible para Power BI)."""
    dir_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for vista in vistas(conn):
        path = dir_path / f"{vista}.csv"
        pd.read_sql_query(f"SELECT * FROM {vista}", conn).to_csv(path, index=False)
        paths[vista] = path
    return paths


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    conn = build_database(run_all(), DB_PATH)
    for vista, path in export_vistas(conn).items():
        n = conn.execute(f"SELECT COUNT(*) FROM {vista}").fetchone()[0]
        print(f"{vista}: {n} filas -> {path}")
    conn.close()
    print(f"Base SQLite: {DB_PATH}")


if __name__ == "__main__":
    main()
