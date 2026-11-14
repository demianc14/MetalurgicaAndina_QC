"""LOAD del pipeline ETL: une Producción limpia con el catálogo, calcula
métricas financieras y de calidad, clasifica y agrega — equivalente a las
tablas dinámicas del Excel original — y persiste todo en data/processed/.

Cada función de cálculo es pura y testeable en aislamiento. El único I/O
vive en `load()` (escribe los CSV finales).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

PROCESSED_DIR = Path("data/processed")
PRODUCCION_ENRIQUECIDA_PATH = PROCESSED_DIR / "produccion_enriquecida.csv"
POR_LINEA_TURNO_PATH = PROCESSED_DIR / "produccion_por_linea_turno.csv"
RESUMEN_POR_LINEA_PATH = PROCESSED_DIR / "resumen_por_linea.csv"

Clasificacion = Literal["Excelente", "Aceptable", "Crítico"]

# Límites cerrados hacia abajo (<=), no estrictos.
UMBRAL_EXCELENTE = 0.01
UMBRAL_ACEPTABLE = 0.03
# Estricto (>), no >=.
UMBRAL_PARO_PROBLEMATICO_MIN = 30


# ---------------------------------------------------------------------------
# Join con el catálogo
# ---------------------------------------------------------------------------


def join_con_catalogo(produccion: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Une Producción (ya limpia) con 01_Catalogo_Productos por SKU.

    Merge "left": toda fila de producción se conserva aunque falte en el
    catálogo. Si algún SKU de producción no matchea, falla explícito
    (fail fast) en vez de dejar Costo_Unitario_USD/Precio_Venta_USD en NaN
    silencioso, lo que produciría un Profit incorrecto sin avisar.
    """
    merged = produccion.merge(catalogo, on="SKU", how="left", validate="many_to_one")
    huerfanos = sorted(merged.loc[merged["Producto"].isna(), "SKU"].unique())
    if huerfanos:
        raise ValueError(f"SKU de producción sin match en el catálogo: {huerfanos}")
    return merged


# ---------------------------------------------------------------------------
# Métricas por fila
# ---------------------------------------------------------------------------


def compute_financials(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega Costo_total, Ventas_totales, Profit y Tasa_defectuosos.

    Fórmulas del caso: Costo_total = Costo_Unitario_USD * Cantidad_Producida;
    Ventas_totales = Precio_Venta_USD * Cantidad_Producida;
    Profit = Ventas_totales - Costo_total;
    Tasa_defectuosos = Unidades_Defectuosas / Cantidad_Producida.
    """
    out = df.copy()
    out["Costo_total"] = out["Costo_Unitario_USD"] * out["Cantidad_Producida"]
    out["Ventas_totales"] = out["Precio_Venta_USD"] * out["Cantidad_Producida"]
    out["Profit"] = out["Ventas_totales"] - out["Costo_total"]
    out["Tasa_defectuosos"] = out["Unidades_Defectuosas"] / out["Cantidad_Producida"]
    return out


def classify_calidad(tasa_defectuosos: float) -> Clasificacion:
    """Clasifica Tasa_defectuosos en 3 niveles, límites cerrados hacia abajo.

    Excelente: <=1%. Aceptable: >1% y <=3%. Crítico: >3%. Una tasa de
    exactamente 1.0% es Excelente (no Aceptable) y exactamente 3.0% es
    Aceptable (no Crítico): son fronteras cerradas (<=), no estrictas.

    Verificado contra las 90 filas ya clasificadas en el Excel original
    (hoja oculta "02_Produccion", recalculando Tasa_defectuosos desde
    Unidades_Defectuosas/Cantidad_Producida de forma independiente): las 90
    coinciden, incluidas las fronteras. No se encontró ninguna
    inconsistencia con estas reglas.
    """
    if tasa_defectuosos <= UMBRAL_EXCELENTE:
        return "Excelente"
    if tasa_defectuosos <= UMBRAL_ACEPTABLE:
        return "Aceptable"
    return "Crítico"


def cumple(clasificacion: Clasificacion) -> str:
    """'Cumple' si Excelente o Aceptable; 'No cumple' si Crítico."""
    return "Cumple" if clasificacion in ("Excelente", "Aceptable") else "No cumple"


def turno_problematico(clasificacion: Clasificacion, tiempo_paro_min: float) -> str:
    """'Sí' si Crítico y el paro superó 30 min; 'No' en cualquier otro caso.

    Estricto (>30, no >=30): verificado contra el Excel original — una
    fila Crítico con Tiempo_Paro_Min == 30 exactamente quedó marcada 'No'.

    Si Tiempo_Paro_Min es NaN (paro no registrado), "NaN > 30" es False en
    pandas, así que la fila cae a 'No' por la rama por defecto de la
    regla — no porque se sepa que el turno no fue problemático. Esas filas
    ya están señaladas aparte en `DataQualityReport.paros_faltantes`
    (transform.py); no se ocultan, solo no se cuentan como "Sí" sin dato.
    """
    if clasificacion == "Crítico" and tiempo_paro_min > UMBRAL_PARO_PROBLEMATICO_MIN:
        return "Sí"
    return "No"


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica classify_calidad/cumple/turno_problematico fila por fila."""
    out = df.copy()
    out["Clasificacion"] = out["Tasa_defectuosos"].apply(classify_calidad)
    out["Cumple"] = out["Clasificacion"].apply(cumple)
    out["Turno_problematico"] = [
        turno_problematico(c, p)
        for c, p in zip(out["Clasificacion"], out["Tiempo_Paro_Min"])
    ]
    return out


# ---------------------------------------------------------------------------
# Agregaciones (equivalentes a las tablas dinámicas del Excel original)
# ---------------------------------------------------------------------------


def aggregate_por_linea_turno(df: pd.DataFrame) -> pd.DataFrame:
    """Cantidad_Producida total por Línea (filas) y Turno (columnas).

    Equivalente a la tabla dinámica "Suma de Cantidad_Producida" del Excel
    original. A diferencia de esa tabla, las filas con Turno no registrado
    NO se reparten entre Mañana/Tarde/Noche (ahí sí se habían asumido sin
    documentarlo): aparecen en su propia columna "turno no registrado",
    así el total general sigue cuadrando sin inventar a qué turno
    pertenecen.
    """
    return df.pivot_table(
        index="Linea_Produccion",
        columns="Turno",
        values="Cantidad_Producida",
        aggfunc="sum",
        fill_value=0,
        margins=True,
        margins_name="Total general",
    )


def aggregate_defectuosos_por_linea(df: pd.DataFrame) -> pd.Series:
    """Unidades_Defectuosas totales por Línea."""
    return df.groupby("Linea_Produccion")["Unidades_Defectuosas"].sum()


def aggregate_tasa_promedio_por_linea(df: pd.DataFrame) -> pd.Series:
    """Tasa_defectuosos promedio (simple, no ponderada por volumen) por Línea."""
    return df.groupby("Linea_Produccion")["Tasa_defectuosos"].mean()


def resumen_por_linea(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla resumen por Línea: producción total, defectuosos y tasa promedio."""
    return pd.DataFrame({
        "Cantidad_Producida_total": df.groupby("Linea_Produccion")["Cantidad_Producida"].sum(),
        "Unidades_Defectuosas_total": aggregate_defectuosos_por_linea(df),
        "Tasa_defectuosos_promedio": aggregate_tasa_promedio_por_linea(df),
    })


# ---------------------------------------------------------------------------
# Orquestación + persistencia
# ---------------------------------------------------------------------------


def build_dataset(produccion: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Une, calcula y clasifica: produccion limpia + catálogo -> dataset final."""
    joined = join_con_catalogo(produccion, catalogo)
    with_financials = compute_financials(joined)
    return classify(with_financials)


def load(df: pd.DataFrame, dir_path: Path = PROCESSED_DIR) -> dict[str, Path]:
    """Escribe el dataset enriquecido y las agregaciones en data/processed/."""
    dir_path.mkdir(parents=True, exist_ok=True)

    enriquecida_path = dir_path / PRODUCCION_ENRIQUECIDA_PATH.name
    por_linea_turno_path = dir_path / POR_LINEA_TURNO_PATH.name
    resumen_linea_path = dir_path / RESUMEN_POR_LINEA_PATH.name

    df.to_csv(enriquecida_path, index=False)
    aggregate_por_linea_turno(df).to_csv(por_linea_turno_path)
    resumen_por_linea(df).to_csv(resumen_linea_path)

    return {
        "produccion_enriquecida": enriquecida_path,
        "produccion_por_linea_turno": por_linea_turno_path,
        "resumen_por_linea": resumen_linea_path,
    }


if __name__ == "__main__":
    from src.etl.extract import extract
    from src.etl.transform import transform

    produccion_raw, catalogo = extract()
    produccion_limpia, report = transform(produccion_raw)
    print(report.resumen())

    dataset = build_dataset(produccion_limpia, catalogo)
    paths = load(dataset)
    print("\n=== Load ===")
    for name, path in paths.items():
        print(f"{name}: {path}")
