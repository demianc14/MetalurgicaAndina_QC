"""Pipeline de los tres meses: marzo (caso original) + abril-mayo (práctica).

Corre el MISMO Extract -> Transform -> Load sobre cada archivo fuente y
apila el resultado. Es el equivalente reproducible del consolidado que en
la clase se armó copiando filas limpias de un Excel debajo del otro.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.etl.extract import ABR_MAY, DATASETS, Dataset, extract_dataset, extract_pedidos
from src.etl.load import PROCESSED_DIR, build_dataset
from src.etl.pedidos import build_pedidos
from src.etl.transform import DataQualityReport, transform

PRODUCCION_3_MESES_PATH = PROCESSED_DIR / "produccion_3_meses.csv"
PEDIDOS_PATH = PROCESSED_DIR / "pedidos_abr_may.csv"


@dataclass
class Resultado:
    """Salida del pipeline completo."""

    produccion: pd.DataFrame  # marzo + abril + mayo, una fila por corrida
    pedidos: pd.DataFrame  # abril-mayo
    reportes: dict[str, DataQualityReport]


def run_dataset(ds: Dataset) -> tuple[pd.DataFrame, DataQualityReport]:
    """Extract -> Transform -> Load (sin escribir) de un solo archivo fuente."""
    produccion_raw, catalogo = extract_dataset(ds)
    limpia, report = transform(produccion_raw, meses_validos=ds.meses_validos)
    dataset = build_dataset(limpia, catalogo)
    dataset.insert(0, "Origen", ds.nombre)
    return dataset, report


def run_all() -> Resultado:
    """Corre los datasets del caso y los apila."""
    partes: list[pd.DataFrame] = []
    reportes: dict[str, DataQualityReport] = {}
    for ds in DATASETS:
        dataset, report = run_dataset(ds)
        partes.append(dataset)
        reportes[ds.nombre] = report
    produccion = pd.concat(partes, ignore_index=True)
    if produccion["ID_Registro"].duplicated().any():
        raise ValueError("ID_Registro repetido entre archivos: no se pueden apilar")
    _, catalogo = extract_dataset(ABR_MAY)
    pedidos = build_pedidos(extract_pedidos(ABR_MAY), catalogo)
    return Resultado(produccion=produccion, pedidos=pedidos, reportes=reportes)


def write(resultado: Resultado, dir_path: Path = PROCESSED_DIR) -> dict[str, Path]:
    """Escribe los CSV de tres meses en data/processed/."""
    dir_path.mkdir(parents=True, exist_ok=True)
    produccion_path = dir_path / PRODUCCION_3_MESES_PATH.name
    pedidos_path = dir_path / PEDIDOS_PATH.name
    resultado.produccion.to_csv(produccion_path, index=False)
    resultado.pedidos.to_csv(pedidos_path, index=False)
    return {"produccion_3_meses": produccion_path, "pedidos_abr_may": pedidos_path}
