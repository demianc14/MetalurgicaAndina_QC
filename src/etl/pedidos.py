"""Pedidos de abril-mayo: desvío de entrega, estado y margen por pedido.

Equivalente en pandas de la hoja "P5_Entregas" del Excel de la clase. Los
pedidos de marzo no están en este módulo porque su hoja cruda original no
forma parte del repo (solo existen ya procesados dentro del consolidado).

Reglas (hoja "DatosP5" del Excel):
  PENDIENTE  sin Fecha_Entrega_Real
  A TIEMPO   desvío <= 0 días
  LEVE       desvío de 1 a 3 días
  ATRASADO   desvío > 3 días
"""
from __future__ import annotations

import pandas as pd

LIMITE_A_TIEMPO_DIAS = 0
LIMITE_LEVE_DIAS = 3


def estado_entrega(desvio: float) -> str:
    """Clasifica el desvío (días entre entrega real y programada)."""
    if pd.isna(desvio):
        return "PENDIENTE"
    if desvio <= LIMITE_A_TIEMPO_DIAS:
        return "A TIEMPO"
    if desvio <= LIMITE_LEVE_DIAS:
        return "LEVE"
    return "ATRASADO"


def build_pedidos(pedidos: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Agrega desvío, estado_entrega e ingreso/costo/margen a cada pedido."""
    precios = catalogo[["SKU", "Precio_Venta_USD", "Costo_Unitario_USD"]]
    out = pedidos.merge(precios, on="SKU", how="left", validate="many_to_one")
    huerfanos = sorted(out.loc[out["Precio_Venta_USD"].isna(), "SKU"].unique())
    if huerfanos:
        raise ValueError(f"SKU de pedidos sin match en el catálogo: {huerfanos}")
    real = pd.to_datetime(out["Fecha_Entrega_Real"])
    programada = pd.to_datetime(out["Fecha_Entrega_Programada"])
    out["desvio"] = (real - programada).dt.days
    out["estado_entrega"] = out["desvio"].apply(estado_entrega)
    out["ingreso_usd"] = out["Precio_Venta_USD"] * out["Cantidad"]
    out["costo_usd"] = out["Costo_Unitario_USD"] * out["Cantidad"]
    out["margen_usd"] = out["ingreso_usd"] - out["costo_usd"]
    return out


def resumen_por_estado(df: pd.DataFrame) -> pd.DataFrame:
    """Nº de pedidos, ingreso, costo y margen por estado_entrega."""
    return df.groupby("estado_entrega").agg(
        n_pedidos=("ID_Pedido", "count"),
        ingreso_usd=("ingreso_usd", "sum"),
        costo_usd=("costo_usd", "sum"),
        margen_usd=("margen_usd", "sum"),
        margen_promedio_usd=("margen_usd", "mean"),
    )
