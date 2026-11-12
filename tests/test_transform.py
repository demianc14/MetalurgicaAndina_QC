"""Tests del transform. Cada test ancla una decisión de negocio documentada
en transform.py, no solo el comportamiento accidental del código."""
from datetime import date

import pandas as pd
import pytest

from src.etl.extract import ABR_MAY, extract, extract_dataset
from src.etl.transform import (
    TURNO_NO_REGISTRADO,
    classify_date_format,
    clean_tiempo_paro_min,
    deduplicate_exact,
    find_ambiguous_slash_dates,
    is_slash_ambiguous,
    load_date_overrides,
    load_turno_overrides,
    normalize_linea_produccion,
    normalize_sku,
    normalize_turno,
    parse_date,
    resolve_dates,
    resolve_turnos,
    transform,
)

# --- classify_date_format / is_slash_ambiguous -----------------------------


@pytest.mark.parametrize("raw,expected", [
    ("2026-03-02", "iso"),
    ("02-Mar-26", "mmm"),
    ("03/02/2026", "slash"),
])
def test_classify_date_format(raw, expected):
    assert classify_date_format(raw) == expected


def test_classify_date_format_rechaza_formato_desconocido():
    with pytest.raises(ValueError):
        classify_date_format("2026/03/02")


@pytest.mark.parametrize("raw,expected", [
    ("03/02/2026", True),   # ambos <=12: ambiguo
    ("13/03/2026", False),  # 13 solo puede ser día
    ("03/13/2026", False),  # 13 solo puede ser día
])
def test_is_slash_ambiguous(raw, expected):
    assert is_slash_ambiguous(raw) == expected


# --- parse_date --------------------------------------------------------


def test_parse_date_iso():
    assert parse_date("2026-03-02") == date(2026, 3, 2)


def test_parse_date_mmm():
    assert parse_date("02-Mar-26") == date(2026, 3, 2)


def test_parse_date_slash_dia_mayor_a_12_no_es_ambiguo():
    assert parse_date("13/03/2026") == date(2026, 3, 13)
    assert parse_date("03/13/2026") == date(2026, 3, 13)


def test_parse_date_slash_ambiguo_devuelve_none_sin_adivinar():
    assert parse_date("03/02/2026") is None


# --- normalize_linea_produccion / normalize_turno -----------------------


@pytest.mark.parametrize("raw", ["Línea 1", "LÍNEA 1", "linea 1", " Línea 1 ", "línea 1"])
def test_normalize_linea_produccion_variantes(raw):
    assert normalize_linea_produccion(raw) == "Línea 1"


def test_normalize_linea_produccion_rechaza_valor_no_reconocido():
    with pytest.raises(ValueError):
        normalize_linea_produccion("Planta Sur")


@pytest.mark.parametrize("raw,expected", [(" MA-1001", "MA-1001"), ("MA-1001", "MA-1001")])
def test_normalize_sku_quita_espacios(raw, expected):
    assert normalize_sku(raw) == expected


@pytest.mark.parametrize("raw", ["Mañana", "MAÑANA", "mañana", " Mañana "])
def test_normalize_turno_variantes(raw):
    assert normalize_turno(raw) == "Mañana"


def test_normalize_turno_nan_no_asume_valor():
    assert normalize_turno(float("nan")) == TURNO_NO_REGISTRADO


def test_normalize_turno_rechaza_valor_no_reconocido():
    with pytest.raises(ValueError):
        normalize_turno("Madrugada")


# --- clean_tiempo_paro_min -----------------------------------------------


def test_clean_tiempo_paro_min_preserva_nan_no_lo_convierte_a_cero():
    serie = pd.Series([10.0, None, 0.0, float("nan")])
    limpio = clean_tiempo_paro_min(serie)
    assert limpio.tolist()[0] == 10.0
    assert pd.isna(limpio.iloc[1])
    assert limpio.tolist()[2] == 0.0
    assert pd.isna(limpio.iloc[3])


# --- deduplicate_exact -----------------------------------------------------


def test_deduplicate_exact_reporta_cuantas_remueve():
    df = pd.DataFrame({"ID_Registro": [1, 1, 2], "valor": ["a", "a", "b"]})
    deduped, n_removidas = deduplicate_exact(df)
    assert len(deduped) == 2
    assert n_removidas == 1


def test_deduplicate_exact_no_toca_filas_con_mismo_id_pero_distinto_valor():
    df = pd.DataFrame({"ID_Registro": [1, 1], "valor": ["a", "b"]})
    deduped, n_removidas = deduplicate_exact(df)
    assert len(deduped) == 2
    assert n_removidas == 0


# --- resolve_dates con overrides ------------------------------------------


def test_resolve_dates_aplica_override_solo_a_filas_ambiguas():
    df = pd.DataFrame({
        "ID_Registro": [1, 2],
        "Fecha": ["2026-03-02", "03/02/2026"],  # 1 inequívoca, 2 ambigua
    })
    overrides = {2: date(2026, 2, 3)}
    fechas, ambiguas = resolve_dates(df, overrides)
    assert fechas.tolist() == [date(2026, 3, 2), date(2026, 2, 3)]
    assert ambiguas.empty


def test_resolve_dates_sin_override_deja_ambigua_sin_resolver():
    df = pd.DataFrame({"ID_Registro": [1], "Fecha": ["03/02/2026"]})
    fechas, ambiguas = resolve_dates(df, overrides=None)
    assert fechas.iloc[0] is None
    assert list(ambiguas["ID_Registro"]) == [1]


def test_load_date_overrides_devuelve_vacio_si_no_existe(tmp_path):
    assert load_date_overrides(tmp_path / "no_existe.csv") == {}


def test_load_date_overrides_ignora_filas_sin_llenar(tmp_path):
    path = tmp_path / "date_overrides.csv"
    path.write_text(
        "ID_Registro,Fecha_Original,Fecha_Resuelta\n"
        "1,03/02/2026,2026-02-03\n"
        "2,03/05/2026,\n"
    )
    overrides = load_date_overrides(path)
    assert overrides == {1: date(2026, 2, 3)}


# --- transform() end-to-end sobre el dataset real -------------------------


def test_transform_sobre_dataset_real_cuantifica_cada_decision():
    """Ancla los conteos reales del caso: 95 filas crudas, 5 duplicados
    exactos (90 filas resultantes), 3 turnos no registrados, 5
    Tiempo_Paro_Min faltantes. Las 28 fechas slash ambiguas SÍ están
    resueltas en este repo (data/manual/date_overrides.csv, recuperado de
    la hoja "02_Produccion" del Excel original — ver README), así que acá
    quedan en 0 sin resolver."""
    df_produccion, _ = extract()
    cleaned, report = transform(df_produccion)

    assert report.n_filas_originales == 95
    assert report.n_duplicados_removidos == 5
    assert len(cleaned) == 90
    assert len(report.turnos_no_registrados) == 3
    assert len(report.paros_faltantes) == 5
    assert len(report.fechas_ambiguas_sin_resolver) == 0
    assert cleaned["Fecha"].notna().all()


def test_transform_linea_y_turno_quedan_en_set_canonico():
    df_produccion, _ = extract()
    cleaned, _ = transform(df_produccion)
    assert set(cleaned["Linea_Produccion"]) <= {"Línea 1", "Línea 2", "Línea 3"}
    assert set(cleaned["Turno"]) <= {"Mañana", "Tarde", "Noche", TURNO_NO_REGISTRADO}


def test_find_ambiguous_slash_dates_sobre_dataset_real():
    """Marzo trae 28 fechas slash con ambos números <=12. Dos son
    "03/03/2026" (día = mes): no hay nada que decidir, así que quedan 26
    genuinamente ambiguas."""
    df_produccion, _ = extract()
    deduped, _ = deduplicate_exact(df_produccion)
    ambiguas = find_ambiguous_slash_dates(deduped)
    assert len(ambiguas) == 26
    assert list(ambiguas.columns) == ["ID_Registro", "Fecha"]


def test_date_overrides_csv_del_repo_cubre_las_filas_ambiguas():
    """data/manual/date_overrides.csv (recuperado de "02_Produccion" del
    Excel original) cubre las 26 filas ambiguas, más las 2 "03/03/2026"
    que el propio supervisor anotó como no ambiguas — y ahí el override
    dice lo mismo que el parseo automático."""
    df_produccion, _ = extract()
    deduped, _ = deduplicate_exact(df_produccion)
    ambiguas = set(find_ambiguous_slash_dates(deduped)["ID_Registro"])
    overrides = load_date_overrides()
    assert ambiguas <= set(overrides)
    assert set(overrides) - ambiguas == {11, 13}
    assert overrides[11] == overrides[13] == parse_date("03/03/2026") == date(2026, 3, 3)


# ---------------------------------------------------------------------------
# Abril-mayo: meses válidos, abreviaturas en inglés y turnos confirmados
# ---------------------------------------------------------------------------

ABR_MAY_MESES = frozenset({4, 5})


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("04/15/2026", date(2026, 4, 15)),  # 15 solo puede ser día
        ("04/02/2026", date(2026, 4, 2)),   # 2 no es un mes válido del archivo
        ("02/04/2026", date(2026, 4, 2)),   # mismo día, escrito DD/MM
        ("05/05/2026", date(2026, 5, 5)),   # día = mes: nada que decidir
        ("04/05/2026", None),               # 4-may o 5-abr: ambiguo de verdad
        ("05/04/2026", None),
    ],
)
def test_parse_date_con_meses_validos(raw, esperado):
    assert parse_date(raw, ABR_MAY_MESES) == esperado


def test_parse_date_sin_meses_validos_no_usa_contexto():
    assert parse_date("04/02/2026") is None
    assert is_slash_ambiguous("04/02/2026")
    assert not is_slash_ambiguous("04/02/2026", ABR_MAY_MESES)


def test_parse_date_abreviatura_en_ingles():
    assert parse_date("03-Apr-26") == date(2026, 4, 3)
    assert parse_date("03-Abr-26") == date(2026, 4, 3)


def test_resolve_turnos_solo_llena_vacios():
    df = pd.DataFrame({"ID_Registro": [1, 2, 3], "Turno": [float("nan"), " NOCHE ", None]})
    turnos, n = resolve_turnos(df, {1: "Mañana", 2: "Tarde"})
    assert turnos.tolist() == ["Mañana", "Noche", TURNO_NO_REGISTRADO]
    assert n == 1


def test_turno_overrides_del_repo_son_los_seis_de_abril_mayo():
    overrides = load_turno_overrides()
    assert overrides == {
        2134: "Mañana", 2095: "Tarde", 2009: "Noche",
        2204: "Mañana", 2302: "Tarde", 2182: "Noche",
    }


def test_transform_abril_mayo_sobre_dataset_real():
    produccion_raw, _ = extract_dataset(ABR_MAY)
    cleaned, report = transform(produccion_raw, meses_validos=ABR_MAY.meses_validos)
    assert report.n_filas_originales == 210
    assert report.n_duplicados_removidos == 10
    assert len(cleaned) == 200
    assert report.n_turnos_confirmados == 6
    assert len(report.turnos_no_registrados) == 0
    assert len(report.paros_faltantes) == 7
    assert sorted(report.fechas_ambiguas_sin_resolver["ID_Registro"]) == [2175, 2178, 2179]
    meses = {f.month for f in cleaned["Fecha"] if f is not None}
    assert meses == {4, 5}
