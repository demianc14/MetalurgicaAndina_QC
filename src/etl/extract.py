"""EXTRACT del pipeline ETL: lee el Excel crudo tal cual, sin transformarlo.

Fuente: data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx
  - "Producción (2)"          datos crudos y sucios de producción por turno.
  - "01_Catalogo_Productos"   catálogo limpio de productos.

Ejecutar:  python -m src.etl.extract
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx")

SHEET_PRODUCCION = "Producción (2)"
SHEET_CATALOGO = "01_Catalogo_Productos"


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
