"""EXTRACT del pipeline ETL: lee el Excel crudo tal cual, sin transformarlo.

Fuente: data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx
  - "Producción (2)"          datos crudos y sucios de producción por turno.
  - "01_Catalogo_Productos"   catálogo limpio de productos.

Ejecutar:  python -m src.etl.extract
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx")

SHEET_PRODUCCION = "Producción (2)"
SHEET_CATALOGO = "01_Catalogo_Productos"


ABR_MAY_PATH = Path("entregables/excel/MetalurgicaAndina_DCruz_AprMay2026.xlsx")
SHEET_PEDIDOS = "04_Pedidos"


@dataclass(frozen=True)
class Dataset:
    """Un archivo fuente del caso y el contexto que hace falta para limpiarlo."""

    nombre: str
    path: Path
    sheet_produccion: str
    sheet_catalogo: str = SHEET_CATALOGO
    # Meses que el archivo declara contener; resuelve fechas slash (transform.py).
    meses_validos: frozenset[int] | None = None
    sheet_pedidos: str | None = None


MARZO = Dataset(nombre="marzo", path=RAW_PATH, sheet_produccion=SHEET_PRODUCCION)
ABR_MAY = Dataset(
    nombre="abril-mayo",
    path=ABR_MAY_PATH,
    sheet_produccion="02_Produccion_Sucia",
    # Hoja "Instrucciones" del archivo: "el rango de meses válido ahora es abril/mayo (4 o 5)".
    meses_validos=frozenset({4, 5}),
    sheet_pedidos=SHEET_PEDIDOS,
)
DATASETS = (MARZO, ABR_MAY)


def extract_dataset(ds: Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee producción y catálogo de un Dataset, sin transformar nada."""
    if not ds.path.exists():
        raise FileNotFoundError(f"No existe el dataset crudo: {ds.path}")
    produccion = pd.read_excel(ds.path, sheet_name=ds.sheet_produccion, engine="openpyxl")
    catalogo = pd.read_excel(ds.path, sheet_name=ds.sheet_catalogo, engine="openpyxl")
    return produccion, catalogo


def extract_pedidos(ds: Dataset) -> pd.DataFrame:
    """Lee la hoja cruda de pedidos de un Dataset (solo abril-mayo la trae)."""
    if ds.sheet_pedidos is None:
        raise ValueError(f"El dataset {ds.nombre!r} no trae hoja de pedidos")
    return pd.read_excel(ds.path, sheet_name=ds.sheet_pedidos, engine="openpyxl")


def extract(path: Path = RAW_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee las hojas de producción y catálogo del Excel crudo.

    No limpia, valida ni transforma nada: solo trae los datos tal cual
    están en el archivo fuente. Devuelve (produccion, catalogo).
    """
    if not path.exists():
        raise FileNotFoundError(f"No existe el dataset crudo: {path}")
    produccion = pd.read_excel(path, sheet_name=SHEET_PRODUCCION, engine="openpyxl")
    catalogo = pd.read_excel(path, sheet_name=SHEET_CATALOGO, engine="openpyxl")
    return produccion, catalogo


if __name__ == "__main__":
    df_produccion, df_catalogo = extract()
    print(f"Producción (2): {df_produccion.shape[0]} filas, {df_produccion.shape[1]} columnas")
    print(f"01_Catalogo_Productos: {df_catalogo.shape[0]} filas, {df_catalogo.shape[1]} columnas")
