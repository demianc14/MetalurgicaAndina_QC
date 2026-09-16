"""Tests de Load: join, métricas, clasificación (con fronteras exactas) y
agregaciones. Cada test ancla una regla de negocio documentada en load.py."""
import pandas as pd
import pytest

from src.etl.extract import extract
from src.etl.load import (
    aggregate_defectuosos_por_linea,
    aggregate_por_linea_turno,
    aggregate_tasa_promedio_por_linea,
    build_dataset,
    classify,
    classify_calidad,
    compute_financials,
    cumple,
    join_con_catalogo,
    turno_problematico,
)
from src.etl.transform import transform

# --- join_con_catalogo -----------------------------------------------------


def test_join_con_catalogo_trae_columnas_del_catalogo():
    produccion = pd.DataFrame({"SKU": ["A"], "Cantidad_Producida": [10]})
    catalogo = pd.DataFrame({
        "SKU": ["A"], "Producto": ["Widget"], "Costo_Unitario_USD": [1.0],
        "Precio_Venta_USD": [2.0],
    })
    joined = join_con_catalogo(produccion, catalogo)
    assert joined.loc[0, "Producto"] == "Widget"


def test_join_con_catalogo_falla_ante_sku_huerfano():
    produccion = pd.DataFrame({"SKU": ["NO-EXISTE"], "Cantidad_Producida": [10]})
    catalogo = pd.DataFrame({
        "SKU": ["A"], "Producto": ["Widget"], "Costo_Unitario_USD": [1.0],
        "Precio_Venta_USD": [2.0],
    })
    with pytest.raises(ValueError, match="NO-EXISTE"):
        join_con_catalogo(produccion, catalogo)


# --- compute_financials ------------------------------------------------


def test_compute_financials_formulas_del_caso():
    df = pd.DataFrame({
        "Cantidad_Producida": [100],
        "Unidades_Defectuosas": [5],
        "Costo_Unitario_USD": [2.0],
        "Precio_Venta_USD": [3.5],
    })
    out = compute_financials(df)
    assert out.loc[0, "Costo_total"] == 200.0
    assert out.loc[0, "Ventas_totales"] == 350.0
    assert out.loc[0, "Profit"] == 150.0
    assert out.loc[0, "Tasa_defectuosos"] == pytest.approx(0.05)


# --- classify_calidad: 3 niveles con fronteras exactas ----------------------


@pytest.mark.parametrize("tasa,esperado", [
    (0.0, "Excelente"),
    (0.005, "Excelente"),
    (0.01, "Excelente"),        # frontera exacta: <=1% sigue siendo Excelente
    (0.010001, "Aceptable"),    # justo sobre la frontera
    (0.02, "Aceptable"),
    (0.03, "Aceptable"),        # frontera exacta: <=3% sigue siendo Aceptable
    (0.030001, "Crítico"),      # justo sobre la frontera
    (0.05, "Crítico"),
    (1.0, "Crítico"),
])
def test_classify_calidad_fronteras_exactas(tasa, esperado):
    assert classify_calidad(tasa) == esperado


@pytest.mark.parametrize("clasificacion,esperado", [
    ("Excelente", "Cumple"),
    ("Aceptable", "Cumple"),
    ("Crítico", "No cumple"),
])
def test_cumple(clasificacion, esperado):
    assert cumple(clasificacion) == esperado


# --- turno_problematico ----------------------------------------------------


@pytest.mark.parametrize("clasificacion,paro,esperado", [
    ("Crítico", 31, "Sí"),
    ("Crítico", 30, "No"),      # frontera exacta: 30 no es > 30
    ("Crítico", 29, "No"),
    ("Aceptable", 45, "No"),    # no crítico: da igual el paro
    ("Excelente", 100, "No"),
])
def test_turno_problematico_regla_exacta(clasificacion, paro, esperado):
    assert turno_problematico(clasificacion, paro) == esperado


def test_turno_problematico_con_paro_faltante_no_se_marca_si_sin_dato():
    """Con Tiempo_Paro_Min faltante (NaN), la fila no se marca 'Sí' porque
    no se sabe si superó los 30 min; cae a 'No' por la regla por defecto."""
    assert turno_problematico("Crítico", float("nan")) == "No"


# --- classify() aplicado a un DataFrame -----------------------------------


def test_classify_agrega_las_tres_columnas():
    df = pd.DataFrame({
        "Tasa_defectuosos": [0.005, 0.02, 0.05],
        "Tiempo_Paro_Min": [0.0, 0.0, 45.0],
    })
    out = classify(df)
    assert out["Clasificacion"].tolist() == ["Excelente", "Aceptable", "Crítico"]
    assert out["Cumple"].tolist() == ["Cumple", "Cumple", "No cumple"]
    assert out["Turno_problematico"].tolist() == ["No", "No", "Sí"]


# --- pipeline completo sobre el dataset real --------------------------------


def _dataset_real() -> pd.DataFrame:
    produccion_raw, catalogo = extract()
    produccion_limpia, _ = transform(produccion_raw)
    return build_dataset(produccion_limpia, catalogo)


def test_build_dataset_sobre_caso_real_no_pierde_filas():
    dataset = _dataset_real()
    assert len(dataset) == 90
    assert set(dataset["Clasificacion"]) <= {"Excelente", "Aceptable", "Crítico"}


def test_build_dataset_clasificacion_coincide_con_excel_original():
    """Ancla contra la hoja oculta "02_Produccion" del Excel original: 11
    Excelente, 36 Aceptable, 43 Crítico, verificado recalculando
    Tasa_defectuosos de forma independiente (no leyendo esa hoja)."""
    dataset = _dataset_real()
    counts = dataset["Clasificacion"].value_counts()
    assert counts["Excelente"] == 11
    assert counts["Aceptable"] == 36
    assert counts["Crítico"] == 43


def test_aggregate_por_linea_turno_total_general_coincide_con_excel_original():
    """El total general (22934) coincide con la tabla dinámica del Excel
    original. Los totales por turno NO coinciden a propósito: el Excel
    original reparte silenciosamente los 3 turnos no registrados entre
    Mañana/Noche/Tarde sin documentarlo; este pipeline los deja aparte en
    su propia columna "turno no registrado" (ver transform.normalize_turno)."""
    dataset = _dataset_real()
    pivot = aggregate_por_linea_turno(dataset)
    assert pivot.loc["Total general", "Total general"] == 22934
    assert "turno no registrado" in pivot.columns
    assert pivot.loc["Total general", "turno no registrado"] == 895


def test_aggregate_defectuosos_y_tasa_por_linea():
    dataset = _dataset_real()
    defectuosos = aggregate_defectuosos_por_linea(dataset)
    tasa = aggregate_tasa_promedio_por_linea(dataset)
    assert set(defectuosos.index) == {"Línea 1", "Línea 2", "Línea 3"}
    assert (tasa >= 0).all() and (tasa <= 1).all()
