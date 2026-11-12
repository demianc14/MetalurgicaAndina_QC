"""Checkpoints de la guía de la clase "De la tabla de producción sucia a tres
dashboards en Power BI" (IIN2002), contra el pipeline de Python sobre marzo.

La guía trae, paso a paso, los valores que debe mostrar cada tarjeta y cada
visual del dashboard de tres páginas (Producción, Calidad, Paros y costos).
Estos tests comprueban que pandas llega a los mismos números, así que el
dashboard se puede validar sin abrir Power BI.

Los valores esperados están copiados de los checkpoints de la guía, con la
misma precisión con la que ella los muestra.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.pipeline import run_all


@pytest.fixture(scope="module")
def marzo() -> pd.DataFrame:
    p = run_all().produccion
    return p[p["Origen"] == "marzo"]


# --- Página 1: Producción ---------------------------------------------------


def test_p1_tarjetas(marzo: pd.DataFrame) -> None:
    assert marzo["Cantidad_Producida"].sum() == 22934
    assert marzo["Unidades_Defectuosas"].sum() == 691
    assert round(marzo["Costo_total"].sum() / 1000, 2) == 87.84


def test_p1_produccion_por_linea_y_categoria(marzo: pd.DataFrame) -> None:
    por_linea = marzo.groupby("Linea_Produccion")["Cantidad_Producida"].sum().to_dict()
    assert por_linea == {"Línea 1": 7994, "Línea 2": 7681, "Línea 3": 7259}
    por_categoria = marzo.groupby("Categoria")["Cantidad_Producida"].sum().to_dict()
    assert por_categoria == {
        "Tornillería": 8096, "Soportes": 5890, "Bisagras": 4810, "Engranajes": 4138,
    }


def test_p1_produccion_diaria(marzo: pd.DataFrame) -> None:
    diaria = marzo.groupby("Fecha")["Cantidad_Producida"].sum()
    assert len(diaria) == 13
    assert (diaria.idxmax(), diaria.max()) == (date(2026, 3, 2), 2582)
    assert (diaria.idxmin(), diaria.min()) == (date(2026, 3, 5), 920)


def test_p1_interaccion_linea_1(marzo: pd.DataFrame) -> None:
    linea_1 = marzo[marzo["Linea_Produccion"] == "Línea 1"]
    assert linea_1["Cantidad_Producida"].sum() == 7994
    assert linea_1["Unidades_Defectuosas"].sum() == 235
    assert round(linea_1["Costo_total"].sum() / 1000, 2) == 33.75


# --- Página 2: Calidad ------------------------------------------------------


def test_p2_tarjetas(marzo: pd.DataFrame) -> None:
    assert len(marzo) == 90
    assert (marzo["Turno_problematico"] == "Sí").sum() == 2
    assert (marzo["Clasificacion"] == "Crítico").sum() == 43


def test_p2_calidad_por_linea(marzo: pd.DataFrame) -> None:
    conteo = marzo.groupby(["Linea_Produccion", "Clasificacion"]).size()
    esperado = {"Línea 1": (3, 13, 15), "Línea 2": (4, 11, 15), "Línea 3": (4, 12, 13)}
    for linea, valores in esperado.items():
        obtenido = tuple(conteo[(linea, c)] for c in ("Excelente", "Aceptable", "Crítico"))
        assert obtenido == valores


def test_p2_top_5_productos_defectuosas(marzo: pd.DataFrame) -> None:
    top = marzo.groupby("Producto")["Unidades_Defectuosas"].sum().nlargest(5)
    assert top.to_dict() == {
        "Arandela Plana M8": 77,
        'Bisagra Industrial 4"': 74,
        'Bisagra Reforzada 5"': 65,
        "Soporte Ángulo 50mm": 49,
        "Tornillo Allen M6x30": 46,
    }


def test_p2_tabla_turnos_problematicos(marzo: pd.DataFrame) -> None:
    filas = marzo[marzo["Turno_problematico"] == "Sí"].set_index("ID_Registro")
    assert sorted(filas.index) == [16, 89]
    f16, f89 = filas.loc[16], filas.loc[89]
    assert (f16["Fecha"], f16["Linea_Produccion"], f16["Turno"], f16["Producto"]) == (
        date(2026, 3, 3), "Línea 3", "Tarde", "Tuerca M8")
    assert (round(f16["Tasa_defectuosos"] * 100, 2), f16["Tiempo_Paro_Min"]) == (5.32, 45)
    assert (f89["Fecha"], f89["Linea_Produccion"], f89["Turno"], f89["Producto"]) == (
        date(2026, 3, 18), "Línea 1", "Noche", 'Bisagra Industrial 4"')
    assert (round(f89["Tasa_defectuosos"] * 100, 2), f89["Tiempo_Paro_Min"]) == (5.98, 45)


# --- Página 3: Paros y costos -----------------------------------------------


def test_p3_tarjetas_de_paro(marzo: pd.DataFrame) -> None:
    """14.5 es el promedio sobre los 85 registros con dato; con los 5 vacíos
    contados como 0 daría 13.7. Es la decisión de no convertir vacíos en 0."""
    assert marzo["Tiempo_Paro_Min"].sum() == 1235
    assert marzo["Tiempo_Paro_Min"].notna().sum() == 85
    assert round(marzo["Tiempo_Paro_Min"].mean(), 1) == 14.5
    assert round(marzo["Tiempo_Paro_Min"].sum() / len(marzo), 1) == 13.7


def test_p3_paro_promedio_por_turno(marzo: pd.DataFrame) -> None:
    """Este checkpoint solo se cumple con los 3 turnos vacíos de marzo
    asignados como en data/manual/turno_overrides.csv (8 Mañana, 25 Tarde,
    36 Noche). Sin ellos da 15.5 / 11.4 / 15.7."""
    promedio = marzo.groupby("Turno")["Tiempo_Paro_Min"].mean().round(1).to_dict()
    assert promedio == {"Mañana": 15.3, "Tarde": 12.3, "Noche": 15.3}


def test_p3_matriz_de_costos(marzo: pd.DataFrame) -> None:
    matriz = marzo.pivot_table(
        index="Categoria", columns="Linea_Produccion", values="Costo_total", aggfunc="sum"
    ).round(0)
    esperado = {
        "Bisagras": (9109, 4627, 4733),
        "Engranajes": (20772, 13459, 20092),
        "Soportes": (3534, 5904, 4731),
        "Tornillería": (332, 318, 231),
    }
    for categoria, valores in esperado.items():
        assert tuple(matriz.loc[categoria, ["Línea 1", "Línea 2", "Línea 3"]]) == valores
    assert round(marzo.loc[marzo["Categoria"] == "Engranajes", "Costo_total"].sum()) == 54323


def test_p3_top_5_productos_por_costo(marzo: pd.DataFrame) -> None:
    top = marzo.groupby("Producto")["Costo_total"].sum().nlargest(5).round(0)
    assert top.to_dict() == {
        "Engranaje Helicoidal 20D": 18286,
        "Engranaje Cónico 25D": 16844,
        "Engranaje Recto 30D": 12130,
        'Bisagra Reforzada 5"': 8126,
        "Engranaje Recto 20D": 7064,
    }
