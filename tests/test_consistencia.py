"""Prueba de consistencia: Excel de la clase vs pandas vs vistas SQL.

Los valores del Excel se LEEN con código (valores en caché de las tablas
dinámicas y fórmulas), nunca se copian a mano. Tres bloques:

  A. Abril-mayo: el libro de trabajo P1..P8 contra el pipeline y las vistas.
  B. Marzo: las tablas dinámicas del caso original.
  C. Tres meses: el consolidado contra el pipeline, fila por fila.

Donde las tres fuentes coinciden, el test lo exige. Donde NO coinciden, el
test afirma la diferencia exacta (qué filas, cuánto), para que la tabla
"Excel vs Python" del README no pueda quedar desactualizada en silencio.
"""
from __future__ import annotations

import sqlite3
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd
import pytest

from src.etl.extract import ABR_MAY_PATH, RAW_PATH
from src.pipeline import Resultado, run_all
from src.sql_load import build_database

CONSOLIDADO_PATH = Path("entregables/excel/Consolidado_Pedidos_Produccion_DCruz_MarAbrMay2026.xlsx")
TURNOS = ["Mañana", "Noche", "Tarde"]
LINEAS = ["Línea 1", "Línea 2", "Línea 3"]


# ---------------------------------------------------------------------------
# Fixtures: cada fuente se construye una sola vez
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resultado() -> Resultado:
    return run_all()


@pytest.fixture(scope="module")
def conn(resultado: Resultado) -> Iterator[sqlite3.Connection]:
    connection = build_database(resultado)
    yield connection
    connection.close()


def _abrir(path: Path) -> openpyxl.Workbook:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # extensiones de Excel que openpyxl no soporta
        return openpyxl.load_workbook(path, data_only=True)


@pytest.fixture(scope="module")
def xl_abr_may() -> openpyxl.Workbook:
    return _abrir(ABR_MAY_PATH)


@pytest.fixture(scope="module")
def xl_marzo() -> openpyxl.Workbook:
    return _abrir(RAW_PATH)


@pytest.fixture(scope="module")
def consolidado() -> pd.DataFrame:
    df = pd.read_excel(CONSOLIDADO_PATH, sheet_name="Produccion", header=1).iloc[:, 1:]
    return df.set_index("ID_Registro")


@pytest.fixture(scope="module")
def consolidado_pedidos() -> pd.DataFrame:
    return pd.read_excel(CONSOLIDADO_PATH, sheet_name="Pedidos", header=1).iloc[:, 1:]


def bloque(wb: openpyxl.Workbook, hoja: str, rango: str) -> list[list[Any]]:
    """Valores de un rango del Excel, fila por fila."""
    return [[c.value for c in fila] for fila in wb[hoja][rango]]


def cruzada(filas: list[list[Any]]) -> dict[tuple[str, str], float]:
    """Tabla dinámica con encabezado en la 1ª fila -> {(fila, columna): valor}."""
    columnas = filas[0][1:]
    return {(f[0], c): v for f in filas[1:] for c, v in zip(columnas, f[1:])}


def coinciden(*valores: float) -> bool:
    """True si todos los valores son iguales salvo redondeo de punto flotante."""
    return all(v == pytest.approx(valores[0]) for v in valores[1:])


def sql(conn: sqlite3.Connection, query: str) -> pd.DataFrame:
    return pd.read_sql_query(query, conn)


def parte(resultado: Resultado, origen: str) -> pd.DataFrame:
    return resultado.produccion[resultado.produccion["Origen"] == origen]


# ---------------------------------------------------------------------------
# A. Abril-mayo: libro de trabajo de la clase == pandas == SQL
# ---------------------------------------------------------------------------


def test_abr_may_filas_y_duplicados(resultado: Resultado, xl_abr_may: openpyxl.Workbook) -> None:
    estados = [f[0] for f in bloque(xl_abr_may, "P1_Produccion_Limpia", "L5:L214")]
    report = resultado.reportes["abril-mayo"]
    assert estados.count("Duplicado") == report.n_duplicados_removidos == 10
    assert estados.count("Válido") == len(parte(resultado, "abril-mayo")) == 200


@pytest.mark.parametrize(
    ("rango", "columna", "columna_sql"),
    [
        ("M6:Q10", "Cantidad_Producida", "cantidad_producida"),
        ("M24:Q28", "Unidades_Defectuosas", "unidades_defectuosas"),
    ],
)
def test_abr_may_dinamica_linea_turno(
    resultado: Resultado,
    conn: sqlite3.Connection,
    xl_abr_may: openpyxl.Workbook,
    rango: str,
    columna: str,
    columna_sql: str,
) -> None:
    excel = cruzada(bloque(xl_abr_may, "P2_NoDuplicados_Graficos", rango))
    df = parte(resultado, "abril-mayo")
    pandas_ = df.groupby(["Linea_Produccion", "Turno"])[columna].sum()
    vista = sql(conn, "SELECT * FROM v_produccion_linea_turno WHERE origen = 'abril-mayo'")
    vista_ = vista.set_index(["linea", "turno"])[columna_sql]
    for linea in LINEAS:
        for turno in TURNOS:
            assert excel[(linea, turno)] == pandas_[(linea, turno)] == vista_[(linea, turno)]
    assert excel[("Grand Total", "Grand Total")] == df[columna].sum() == vista_.sum()


def test_abr_may_calidad_por_turno(
    resultado: Resultado, conn: sqlite3.Connection, xl_abr_may: openpyxl.Workbook
) -> None:
    """P4_Calidad: reportes COUNTIFS de nivel de calidad, cumple y problemáticos."""
    nivel = cruzada(bloque(xl_abr_may, "P4_Calidad", "W14:AA17"))
    cumple = cruzada(bloque(xl_abr_may, "P4_Calidad", "W5:AA7"))
    problematico = cruzada(bloque(xl_abr_may, "P4_Calidad", "W21:AA22"))
    df = parte(resultado, "abril-mayo")
    vista = sql(conn, "SELECT * FROM v_calidad_por_turno WHERE origen = 'abril-mayo'")
    vista = vista.set_index("turno")
    for turno in TURNOS:
        t = df[df["Turno"] == turno]
        for clasif, col in [("Excelente", "excelente"), ("Aceptable", "aceptable"),
                            ("Crítico", "critico")]:
            esperado = nivel[(clasif, turno)]
            assert esperado == (t["Clasificacion"] == clasif).sum() == vista.loc[turno, col]
        assert (cumple[("Si Cumple", turno)] == (t["Cumple"] == "Cumple").sum()
                == vista.loc[turno, "cumple"])
        assert (problematico[("Si", turno)] == (t["Turno_problematico"] == "Sí").sum()
                == vista.loc[turno, "problematicos"])
    totales = {c: nivel[(c, "Total")] for c in ("Excelente", "Aceptable", "Crítico")}
    assert totales == {"Excelente": 32, "Aceptable": 76, "Crítico": 92}
    assert problematico[("Si", "Total")] == (df["Turno_problematico"] == "Sí").sum() == 7


def test_abr_may_paro_y_defectos(
    resultado: Resultado, conn: sqlite3.Connection, xl_abr_may: openpyxl.Workbook
) -> None:
    """P8_Conclusion: paro por turno/línea (SUMIFS) y % defectuoso ponderado."""
    por_turno = {f[0]: f[1] for f in bloque(xl_abr_may, "P8_Conclusion", "E5:F8")}
    por_linea = {f[0]: (f[1], f[3]) for f in bloque(xl_abr_may, "P8_Conclusion", "E11:H14")}
    df = parte(resultado, "abril-mayo")
    v_turno = sql(conn, "SELECT * FROM v_paro_por_turno WHERE origen = 'abril-mayo'")
    v_linea = sql(conn, "SELECT * FROM v_paro_por_linea WHERE origen = 'abril-mayo'")
    for turno in TURNOS:
        assert (por_turno[turno] == df.loc[df["Turno"] == turno, "Tiempo_Paro_Min"].sum()
                == v_turno.set_index("turno").loc[turno, "paro_min"])
    for linea in LINEAS:
        sub = df[df["Linea_Produccion"] == linea]
        paro, pct = por_linea[linea]
        fila = v_linea.set_index("linea").loc[linea]
        assert paro == sub["Tiempo_Paro_Min"].sum() == fila["paro_min"]
        pct_pandas = sub["Unidades_Defectuosas"].sum() / sub["Cantidad_Producida"].sum()
        assert coinciden(pct, pct_pandas, fila["pct_defectuosos_ponderado"])
    assert por_turno["Total"] == df["Tiempo_Paro_Min"].sum() == 2555
    # AVERAGE de Excel ignora los vacíos igual que mean() de pandas ignora NaN.
    promedio_excel = xl_abr_may["P8_Conclusion"]["C7"].value
    assert promedio_excel == pytest.approx(df["Tiempo_Paro_Min"].mean())
    assert df["Tiempo_Paro_Min"].isna().sum() == 7


def test_abr_may_costo_total(
    resultado: Resultado, conn: sqlite3.Connection, xl_abr_may: openpyxl.Workbook
) -> None:
    costo_mes = {f[0]: f[1] for f in bloque(xl_abr_may, "P3_Costos", "U5:V8")}
    df = parte(resultado, "abril-mayo")
    kpi = sql(conn, "SELECT costo_total FROM v_kpis WHERE origen = 'abril-mayo'")
    assert costo_mes["Grand Total"] == pytest.approx(df["Costo_total"].sum())
    assert costo_mes["Grand Total"] == pytest.approx(kpi["costo_total"].iloc[0])
    # Abril coincide exacto; mayo NO (ver test_diferencia_fecha_0505).
    abril = df[pd.to_datetime(df["Fecha"]).dt.month == 4]
    assert costo_mes[4] == pytest.approx(abril["Costo_total"].sum())


def test_abr_may_pedidos_por_estado(
    resultado: Resultado, conn: sqlite3.Connection, xl_abr_may: openpyxl.Workbook
) -> None:
    """P5_Entregas: tabla dinámica PT_Entregas."""
    filas = bloque(xl_abr_may, "P5_Entregas", "U4:Z8")
    ped = resultado.pedidos
    vista = sql(conn, "SELECT * FROM v_entregas_por_estado").set_index("estado_entrega")
    for estado, n, ingreso, costo, margen, margen_prom in filas[:-1]:
        sub = ped[ped["estado_entrega"] == estado]
        fila = vista.loc[estado]
        assert n == len(sub) == fila["n_pedidos"]
        assert coinciden(ingreso, sub["ingreso_usd"].sum(), fila["ingreso_usd"])
        assert coinciden(costo, sub["costo_usd"].sum(), fila["costo_usd"])
        assert coinciden(margen, sub["margen_usd"].sum(), fila["margen_usd"])
        assert coinciden(margen_prom, sub["margen_usd"].mean(), fila["margen_promedio_usd"])
    assert filas[-1][1] == len(ped) == 112
    assert filas[-1][4] == pytest.approx(ped["margen_usd"].sum())


# ---------------------------------------------------------------------------
# B. Marzo: tablas dinámicas del caso original
# ---------------------------------------------------------------------------


def test_marzo_por_linea(
    resultado: Resultado, conn: sqlite3.Connection, xl_marzo: openpyxl.Workbook
) -> None:
    filas = bloque(xl_marzo, "02_Produccion", "AI59:AL62")
    df = parte(resultado, "marzo")
    vista = sql(conn, """
        SELECT linea, SUM(cantidad_producida) AS prod, SUM(unidades_defectuosas) AS def
        FROM v_produccion_linea_turno WHERE origen = 'marzo' GROUP BY linea
    """).set_index("linea")
    for linea, producido, defectuosos, tasa_promedio in filas[:-1]:
        sub = df[df["Linea_Produccion"] == linea]
        assert producido == sub["Cantidad_Producida"].sum() == vista.loc[linea, "prod"]
        assert defectuosos == sub["Unidades_Defectuosas"].sum() == vista.loc[linea, "def"]
        assert tasa_promedio == pytest.approx(sub["Tasa_defectuosos"].mean())
    assert filas[-1][1] == df["Cantidad_Producida"].sum() == 22934
    assert filas[-1][2] == df["Unidades_Defectuosas"].sum() == 691


def test_marzo_por_turno(
    resultado: Resultado, conn: sqlite3.Connection, xl_marzo: openpyxl.Workbook,
    consolidado: pd.DataFrame,
) -> None:
    """Producción línea × turno de marzo, incluidas las 3 corridas que llegan
    sin Turno (registros 8, 25 y 36): se llenan desde turno_overrides.csv y
    quedan igual que en el Excel."""
    excel = cruzada(bloque(xl_marzo, "02_Produccion", "AI11:AM15"))
    df = parte(resultado, "marzo")
    pandas_ = df.groupby(["Linea_Produccion", "Turno"])["Cantidad_Producida"].sum()
    vista = sql(conn, "SELECT * FROM v_produccion_linea_turno WHERE origen = 'marzo'")
    vista_ = vista.set_index(["linea", "turno"])["cantidad_producida"]
    for linea in LINEAS:
        for turno in TURNOS:
            assert excel[(linea, turno)] == pandas_[(linea, turno)] == vista_[(linea, turno)]
    assert resultado.reportes["marzo"].n_turnos_confirmados == 3
    por_id = df.set_index("ID_Registro")
    assert por_id.loc[[8, 25, 36], "Turno"].tolist() == ["Mañana", "Tarde", "Noche"]
    assert consolidado.loc[[8, 25, 36], "Turno"].tolist() == ["Mañana", "Tarde", "Noche"]


def test_tres_meses_por_turno(resultado: Resultado, consolidado: pd.DataFrame) -> None:
    p = resultado.produccion
    assert set(p["Turno"]) == set(TURNOS)
    excel = consolidado.groupby("Turno")["Cantidad_Producida"].sum().to_dict()
    assert excel == p.groupby("Turno")["Cantidad_Producida"].sum().to_dict()
    assert excel == {"Mañana": 22222, "Noche": 27424, "Tarde": 23502}
    turnos = p.set_index("ID_Registro").loc[consolidado.index, "Turno"]
    assert (consolidado["Turno"] == turnos).all()


# ---------------------------------------------------------------------------
# C. Tres meses: consolidado vs pandas vs SQL
# ---------------------------------------------------------------------------


def test_tres_meses_mismas_corridas(resultado: Resultado, consolidado: pd.DataFrame) -> None:
    assert len(consolidado) == len(resultado.produccion) == 290
    assert set(consolidado.index) == set(resultado.produccion["ID_Registro"])


def test_tres_meses_totales(
    resultado: Resultado, conn: sqlite3.Connection, consolidado: pd.DataFrame
) -> None:
    p = resultado.produccion
    kpis = sql(conn, "SELECT SUM(unidades_producidas) AS prod, SUM(unidades_defectuosas) AS def,"
                     " SUM(paro_min) AS paro FROM v_kpis").iloc[0]
    assert consolidado["Cantidad_Producida"].sum() == p["Cantidad_Producida"].sum() == kpis["prod"]
    assert (consolidado["Unidades_Defectuosas"].sum() == p["Unidades_Defectuosas"].sum()
            == kpis["def"])
    assert consolidado["Tiempo_Paro_Min"].sum() == p["Tiempo_Paro_Min"].sum() == kpis["paro"]
    assert p["Cantidad_Producida"].sum() == 73148


def test_tres_meses_fila_por_fila(resultado: Resultado, consolidado: pd.DataFrame) -> None:
    """Cantidades, línea y clasificación coinciden en las 290 corridas."""
    p = resultado.produccion.set_index("ID_Registro").loc[consolidado.index]
    assert (consolidado["Cantidad_Producida"] == p["Cantidad_Producida"]).all()
    assert (consolidado["Unidades_Defectuosas"] == p["Unidades_Defectuosas"]).all()
    assert (consolidado["Línea_Produccion"] == p["Linea_Produccion"]).all()
    assert (consolidado["Calidad_3Niveles"] == p["Clasificacion"]).all()
    assert (consolidado["Problematico"].eq("Si") == p["Turno_problematico"].eq("Sí")).all()
    assert consolidado["%_defectuosos"].to_numpy() == pytest.approx(
        p["Tasa_defectuosos"].to_numpy())


def test_tres_meses_clasificacion(
    resultado: Resultado, conn: sqlite3.Connection, consolidado: pd.DataFrame
) -> None:
    vista = sql(conn, "SELECT SUM(excelente) AS e, SUM(aceptable) AS a, SUM(critico) AS c,"
                      " SUM(problematicos) AS p FROM v_calidad_por_turno").iloc[0]
    conteo_excel = consolidado["Calidad_3Niveles"].value_counts()
    conteo_pandas = resultado.produccion["Clasificacion"].value_counts()
    for clasif, col in [("Excelente", "e"), ("Aceptable", "a"), ("Crítico", "c")]:
        assert conteo_excel[clasif] == conteo_pandas[clasif] == vista[col]
    assert conteo_pandas.to_dict() == {"Crítico": 135, "Aceptable": 112, "Excelente": 43}
    assert (consolidado["Problematico"] == "Si").sum() == vista["p"] == 9


def test_frontera_excelente_es_latente(resultado: Resultado) -> None:
    """Excel y Power Query usan '< 1%' para Excelente; Python usa '<= 1%'.

    Hoy no cambia nada: ninguna de las 290 corridas cae exactamente en 1%.
    Si este test falla, apareció una corrida en la frontera y hay que
    decidir cuál de las dos reglas es la del negocio.
    """
    assert not (resultado.produccion["Tasa_defectuosos"] == 0.01).any()


def test_diferencia_sku_registro_1(resultado: Resultado, consolidado: pd.DataFrame) -> None:
    """DIFERENCIA CONOCIDA: el consolidado tiene el SKU del registro 1 cambiado.

    El dato crudo dice MA-1001 (tornillo, USD 0.15); el consolidado dice
    MA-3001 (engranaje, USD 8.50). Es la única fila con SKU distinto y
    explica toda la diferencia de costo total entre Excel y Python.
    """
    p = resultado.produccion.set_index("ID_Registro").loc[consolidado.index]
    distintos = consolidado.index[consolidado["SKU"] != p["SKU"]].tolist()
    assert distintos == [1]
    assert (consolidado.loc[1, "SKU"], p.loc[1, "SKU"]) == ("MA-3001", "MA-1001")

    diferencia = consolidado["Costo_total"].sum() - p["Costo_total"].sum()
    assert diferencia == pytest.approx(1837.00)
    assert diferencia == pytest.approx(consolidado.loc[1, "Costo_total"] - p.loc[1, "Costo_total"])
    resto = consolidado.index.difference([1])
    assert consolidado.loc[resto, "Costo_total"].to_numpy() == pytest.approx(
        p.loc[resto, "Costo_total"].to_numpy())


def test_diferencia_fecha_0505(
    resultado: Resultado, conn: sqlite3.Connection, xl_abr_may: openpyxl.Workbook,
    consolidado: pd.DataFrame,
) -> None:
    """DIFERENCIA CONOCIDA: el Excel deja 4 fechas en 'REVISAR CON SUPERVISOR'; Python, 3.

    "05/05/2026" es 5 de mayo se lea como se lea (día = mes). La fórmula del
    Excel la marca como ambigua igual; Python la resuelve. Las tres
    "04/05/2026" sí son ambiguas (4 de mayo o 5 de abril) en ambos lados.
    """
    pendientes_excel = consolidado.index[consolidado["Fecha"] == "REVISAR CON SUPERVISOR"]
    p = resultado.produccion.set_index("ID_Registro")
    pendientes_python = p.index[p["Fecha"].isna()]
    assert sorted(pendientes_excel) == [2175, 2178, 2179, 2190]
    assert sorted(pendientes_python) == [2175, 2178, 2179]
    assert str(p.loc[2190, "Fecha"]) == "2026-05-05"

    costo_mes = {f[0]: f[1] for f in bloque(xl_abr_may, "P3_Costos", "U5:V8")}
    vista = sql(conn, "SELECT * FROM v_costo_por_mes").set_index("mes")["costo_total"]
    costo_2190 = p.loc[2190, "Costo_total"]
    assert vista.loc[5.0] == pytest.approx(costo_mes[5] + costo_2190)
    assert vista[vista.index.isna()].iloc[0] == pytest.approx(
        costo_mes["REVISAR CON SUPERVISOR"] - costo_2190)


def test_diferencia_paros_vacios_de_marzo(
    resultado: Resultado, consolidado: pd.DataFrame
) -> None:
    """DIFERENCIA CONOCIDA: 5 paros vacíos de marzo son 0 en el consolidado y NaN en Python.

    La suma no cambia (0 no suma), pero el promedio sí: el consolidado
    divide entre 5 corridas más.
    """
    p = resultado.produccion.set_index("ID_Registro").loc[consolidado.index]
    solo_python = p.index[p["Tiempo_Paro_Min"].isna() & consolidado["Tiempo_Paro_Min"].notna()]
    assert sorted(solo_python) == [40, 42, 55, 72, 80]
    assert (consolidado.loc[solo_python, "Tiempo_Paro_Min"] == 0).all()
    assert consolidado["Tiempo_Paro_Min"].isna().sum() == 7
    assert p["Tiempo_Paro_Min"].isna().sum() == 12
    assert consolidado["Tiempo_Paro_Min"].mean() < p["Tiempo_Paro_Min"].mean()


def test_diferencia_etiqueta_no_cumple(consolidado: pd.DataFrame) -> None:
    """DIFERENCIA CONOCIDA: el consolidado mezcla 'No Cumple' (marzo) y 'No cumple' (abr-may).

    Para Excel y Power BI son dos categorías distintas en un filtro o
    leyenda. Python usa una sola etiqueta.
    """
    conteo = consolidado["Estado_calidad"].value_counts().to_dict()
    assert conteo == {"Si Cumple": 155, "No cumple": 92, "No Cumple": 43}


def test_pedidos_abr_may_vs_consolidado(
    resultado: Resultado, consolidado_pedidos: pd.DataFrame
) -> None:
    """Los 112 pedidos de abril-mayo coinciden uno a uno con el consolidado."""
    ped = resultado.pedidos.set_index("ID_Pedido")
    cons = consolidado_pedidos.set_index("ID_Pedido")
    assert len(cons) == 168
    assert len(ped) == 112
    comunes = cons.loc[ped.index]
    assert (comunes["estado_entrega"] == ped["estado_entrega"]).all()
    assert comunes["margen_usd"].to_numpy() == pytest.approx(ped["margen_usd"].to_numpy())
