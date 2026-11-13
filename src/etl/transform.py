"""TRANSFORM del pipeline ETL: limpieza de "Producción (2)" con criterios
documentados y cuantificados, no "se limpiaron los datos" en abstracto.

Cada función de limpieza es pura (recibe datos, devuelve datos nuevos, sin
I/O) y testeable en aislamiento. El único I/O vive en `load_date_overrides`
(lee un CSV opcional) y en el bloque `__main__` (escribe la plantilla y
corre el pipeline completo).

Patrón de fechas ambiguas: mismo criterio de "fail fast + escalación
documentada" que `resilience.py` en world-cup-predictor — cuando el
pipeline no puede resolver algo sin adivinar, no adivina. Lo deja explícito
en un artefacto (`data/manual/date_overrides_template.csv`) para que una
persona con el criterio de negocio correcto lo decida, y lee el resultado
(`data/manual/date_overrides.csv`) si ya existe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

MANUAL_DIR = Path("data/manual")
DATE_OVERRIDES_TEMPLATE_PATH = MANUAL_DIR / "date_overrides_template.csv"
DATE_OVERRIDES_PATH = MANUAL_DIR / "date_overrides.csv"
TURNO_OVERRIDES_PATH = MANUAL_DIR / "turno_overrides.csv"

TURNO_NO_REGISTRADO = "turno no registrado"

# ---------------------------------------------------------------------------
# Fechas: 3 formatos mezclados fila por fila, sin convención global.
#   ISO        "2026-03-02"  inequívoco
#   DD-Mon-YY  "02-Mar-26"   inequívoco (abreviatura de mes en español)
#   slash      "03/02/2026"  AMBIGUO: MM/DD o DD/MM según la fila
# ---------------------------------------------------------------------------

DateFormat = Literal["iso", "mmm", "slash"]

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MMM_RE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{2})$")
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

# Se mapean los 12 meses en español y en inglés: marzo usa "Mar" (igual en
# ambos idiomas), pero abril-mayo trae "Apr" (inglés). Mapear todos evita
# fallar silenciosamente ante un mes que no vimos en la muestra.
_MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}


def classify_date_format(raw: str) -> DateFormat:
    """Clasifica el formato de una fecha cruda sin parsearla.

    Separar "clasificar" de "parsear" deja aislado el caso ambiguo (slash)
    antes de intentar resolverlo, en vez de mezclar detección y parseo en
    una sola función que tendría que decidir a ciegas.
    """
    raw = raw.strip()
    if _ISO_RE.match(raw):
        return "iso"
    if _MMM_RE.match(raw):
        return "mmm"
    if _SLASH_RE.match(raw):
        return "slash"
    raise ValueError(f"Formato de fecha no reconocido: {raw!r}")


def _resolve_slash(a: int, b: int, meses_validos: frozenset[int] | None) -> int | None:
    """Devuelve el MES de una fecha slash "a/b/yyyy", o None si es ambigua.

    Reglas, de la más fuerte a la más débil:
      1. a == b ("05/05/2026"): día y mes coinciden, no hay nada que decidir.
      2. Uno de los dos es >12: ese solo puede ser el día.
      3. `meses_validos` (contexto de negocio documentado: el archivo solo
         contiene esos meses): si exactamente UNO de los dos números es un
         mes válido, ese es el mes. Es la misma técnica que la fórmula del
         Excel (Sesión 2) y el paso "Fecha_Limpia" de Power Query.
      4. Cualquier otro caso es genuinamente ambiguo: None, no se adivina.
    """
    if a == b:
        return a
    if a > 12 or b > 12:
        return b if a > 12 else a
    if meses_validos is not None:
        a_ok, b_ok = a in meses_validos, b in meses_validos
        if a_ok != b_ok:
            return a if a_ok else b
    return None


def is_slash_ambiguous(raw: str, meses_validos: frozenset[int] | None = None) -> bool:
    """True si una fecha en formato slash no se puede resolver sin contexto.

    Si uno de los dos primeros números es >12, ese solo puede ser el día
    (ningún mes pasa de 12): no es ambiguo. Si AMBOS son <=12, p.ej.
    "03/02/2026", podría ser 3-feb (MM/DD) o 2-mar (DD/MM) — genuinamente
    ambiguo salvo que `meses_validos` descarte una de las dos lecturas
    (ver `_resolve_slash`). No se adivina cuál convención aplica esa fila.
    """
    m = _SLASH_RE.match(raw.strip())
    if not m:
        raise ValueError(f"No es una fecha en formato slash: {raw!r}")
    return _resolve_slash(int(m.group(1)), int(m.group(2)), meses_validos) is None


def parse_date(raw: str, meses_validos: frozenset[int] | None = None) -> date | None:
    """Parsea una fecha cruda a `date`, o None si es slash y ambigua.

    None es intencional, no un error: la resolución de fechas ambiguas
    vive fuera de esta función, en `data/manual/date_overrides.csv`
    (ver `resolve_dates`). `parse_date` nunca adivina.
    """
    raw = raw.strip()
    fmt = classify_date_format(raw)

    if fmt == "iso":
        return date.fromisoformat(raw)

    if fmt == "mmm":
        m = _MMM_RE.match(raw)
        assert m is not None
        day, mes_abbr, yy = m.group(1), m.group(2), m.group(3)
        mes = _MESES_ABREV.get(mes_abbr.lower())
        if mes is None:
            raise ValueError(f"Mes no reconocido en fecha 'DD-Mon-YY': {raw!r}")
        return date(2000 + int(yy), mes, int(day))

    # slash
    m = _SLASH_RE.match(raw)
    assert m is not None
    a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    month = _resolve_slash(a, b, meses_validos)
    if month is None:
        return None
    day = b if month == a else a
    return date(year, month, day)


def find_ambiguous_slash_dates(
    df: pd.DataFrame, meses_validos: frozenset[int] | None = None
) -> pd.DataFrame:
    """Devuelve las filas (ID_Registro, Fecha) cuya fecha slash es ambigua.

    Insumo directo para `build_date_overrides_template`: es el conjunto de
    filas que una persona, no el pipeline, tiene que resolver.
    """
    rows = []
    for idr, raw in zip(df["ID_Registro"], df["Fecha"]):
        raw = str(raw).strip()
        if classify_date_format(raw) == "slash" and is_slash_ambiguous(raw, meses_validos):
            rows.append({"ID_Registro": idr, "Fecha": raw})
    return pd.DataFrame(rows, columns=["ID_Registro", "Fecha"])


def build_date_overrides_template(
    ambiguous: pd.DataFrame, path: Path = DATE_OVERRIDES_TEMPLATE_PATH
) -> Path:
    """Escribe la plantilla de fechas ambiguas para resolución manual.

    Columnas: ID_Registro, Fecha_Original, Fecha_Resuelta (vacía). Se llena
    a mano con el mismo criterio de negocio que se usó en el Excel
    original con el supervisor, y se guarda como
    `data/manual/date_overrides.csv` (ISO en Fecha_Resuelta, p.ej.
    "2026-03-02") para que `load_date_overrides` la recoja.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    template = ambiguous.rename(columns={"Fecha": "Fecha_Original"}).copy()
    template["Fecha_Resuelta"] = ""
    template.to_csv(path, index=False)
    return path


def load_date_overrides(path: Path = DATE_OVERRIDES_PATH) -> dict[int, date]:
    """Lee data/manual/date_overrides.csv si existe; {} si no.

    El pipeline nunca falla por la ausencia de este archivo: mientras no
    exista (o mientras algunas filas sigan con Fecha_Resuelta vacía), esas
    fechas ambiguas quedan como None y se reportan en el resumen de
    calidad de datos, en vez de bloquear todo el ETL.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ID_Registro": int})
    overrides: dict[int, date] = {}
    for _, row in df.iterrows():
        resuelta = row.get("Fecha_Resuelta")
        if pd.isna(resuelta) or str(resuelta).strip() == "":
            continue  # todavía no llenada a mano
        overrides[int(row["ID_Registro"])] = date.fromisoformat(str(resuelta).strip())
    return overrides


def resolve_dates(
    df: pd.DataFrame,
    overrides: dict[int, date] | None = None,
    meses_validos: frozenset[int] | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Resuelve toda la columna Fecha a `date`, aplicando overrides a las filas ambiguas.

    Devuelve (serie_fechas, df_ambiguas_sin_resolver). Las fechas
    inequívocas se parsean directo con `parse_date`. Las slash ambiguas se
    buscan en `overrides` por ID_Registro; si no están ahí, la fecha queda
    en None y la fila se reporta en el segundo elemento.
    """
    overrides = overrides or {}
    resolved: list[date | None] = []
    unresolved_rows = []
    for idr, raw in zip(df["ID_Registro"], df["Fecha"]):
        raw_str = str(raw).strip()
        parsed = parse_date(raw_str, meses_validos)
        if parsed is None:
            parsed = overrides.get(int(idr))
        if parsed is None:
            unresolved_rows.append({"ID_Registro": idr, "Fecha_Original": raw_str})
        resolved.append(parsed)
    fechas = pd.Series(resolved, index=df.index, name="Fecha", dtype="object")
    ambiguas = pd.DataFrame(unresolved_rows, columns=["ID_Registro", "Fecha_Original"])
    return fechas, ambiguas


# ---------------------------------------------------------------------------
# Linea_Produccion / Turno: mismo valor semántico escrito con mayúsculas,
# tildes y espacios inconsistentes fila por fila.
# ---------------------------------------------------------------------------

_LINEA_RE = re.compile(r"(?i)^\s*l[ií]nea\s+(\d+)\s*$")
_TURNO_CANONICO = {"mañana": "Mañana", "tarde": "Tarde", "noche": "Noche"}


def normalize_sku(raw: str) -> str:
    """Quita espacios sobrantes de SKU.

    El crudo tiene un espacio inicial inconsistente (" MA-1001" vs
    "MA-1001") para el mismo SKU. Sin este trim, el join contra
    01_Catalogo_Productos por SKU en la capa Load perdería esas filas de
    forma silenciosa (quedarían sin match y sin costo/precio).
    """
    return str(raw).strip()


def normalize_linea_produccion(raw: str) -> str:
    """Normaliza Linea_Produccion a su forma canónica "Línea N".

    El crudo mezcla mayúsculas, tildes ausentes y espacios sobrantes
    ("LÍNEA 1", "linea 1", " Línea 1 ") para el mismo valor. Se normaliza
    por el número de línea, no por comparación de texto exacto; si el
    valor no calza con el patrón esperado, falla explícito en vez de
    devolver basura silenciosa.
    """
    m = _LINEA_RE.match(str(raw))
    if not m:
        raise ValueError(f"Linea_Produccion no reconocida: {raw!r}")
    return f"Línea {m.group(1)}"


def normalize_turno(raw: object) -> str:
    """Normaliza Turno a su forma canónica, o a 'turno no registrado'.

    El crudo mezcla mayúsculas/minúsculas y espacios ("MAÑANA", "noche ",
    " Tarde") para el mismo turno. Un Turno vacío (NaN) NO se asume: se
    etiqueta explícitamente como 'turno no registrado' para que quede
    visible en el reporte de calidad de datos, en vez de esconderse detrás
    de un valor por defecto arbitrario (p.ej. rellenar con el turno más
    común habría inventado un dato que no existe).
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return TURNO_NO_REGISTRADO
    canonical = _TURNO_CANONICO.get(str(raw).strip().lower())
    if canonical is None:
        raise ValueError(f"Turno no reconocido: {raw!r}")
    return canonical


def load_turno_overrides(path: Path = TURNO_OVERRIDES_PATH) -> dict[int, str]:
    """Lee data/manual/turno_overrides.csv si existe; {} si no.

    Mismo patrón que las fechas: un Turno vacío no se rellena con el turno
    más común. Solo se llena si hay una fila documentada para ese
    ID_Registro, con su respaldo en las columnas `Tipo` y `Fuente`
    ("confirmado_supervisor" o "inferido", ver `load_turnos_inferidos`).
    Sin archivo, o sin fila para ese ID, el turno queda como
    'turno no registrado'.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ID_Registro": int})
    return {
        int(idr): normalize_turno(turno)
        for idr, turno in zip(df["ID_Registro"], df["Turno_Asignado"])
    }


def load_turnos_inferidos(path: Path = TURNO_OVERRIDES_PATH) -> set[int]:
    """IDs cuyo turno en turno_overrides.csv es una inferencia, no un dato.

    "inferido" = el turno no viene en la fila ni hay confirmación escrita;
    se dedujo de otra evidencia (ver la columna `Fuente`). El reporte de
    calidad los cuenta aparte para que no pasen por datos confirmados.
    """
    if not path.exists():
        return set()
    df = pd.read_csv(path, dtype={"ID_Registro": int})
    return {int(i) for i in df.loc[df["Tipo"] == "inferido", "ID_Registro"]}


def resolve_turnos(
    df: pd.DataFrame, overrides: dict[int, str] | None = None
) -> tuple[pd.Series, int]:
    """Normaliza Turno y aplica confirmaciones a las filas vacías.

    Devuelve (serie_turnos, n_confirmados). Un override NUNCA pisa un
    turno que sí venía registrado: solo llena los vacíos.
    """
    overrides = overrides or {}
    turnos: list[str] = []
    n_confirmados = 0
    for idr, raw in zip(df["ID_Registro"], df["Turno"]):
        turno = normalize_turno(raw)
        if turno == TURNO_NO_REGISTRADO and int(idr) in overrides:
            turno = overrides[int(idr)]
            n_confirmados += 1
        turnos.append(turno)
    return pd.Series(turnos, index=df.index, name="Turno"), n_confirmados


# ---------------------------------------------------------------------------
# Tiempo_Paro_Min: faltantes se dejan como NaN explícito.
# ---------------------------------------------------------------------------


def clean_tiempo_paro_min(series: pd.Series) -> pd.Series:
    """Fuerza Tiempo_Paro_Min a numérico, preservando los NaN explícitos.

    Decisión de negocio: un paro no registrado NO es un paro de 0 minutos.
    Convertir NaN a 0 subestimaría sistemáticamente el tiempo de paro en
    cualquier agregación (suma, promedio, paro por línea) sobre esta
    columna. El NaN se deja tal cual y se cuenta aparte en el reporte de
    calidad de datos.
    """
    return pd.to_numeric(series, errors="coerce")


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------


def deduplicate_exact(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Elimina filas exactamente duplicadas (mismo ID_Registro y mismos valores).

    Devuelve (df_deduplicado, n_removidas). Usa keep="first": ante un
    duplicado exacto (todas las columnas iguales) no hay ningún criterio
    de negocio que decidir, es ruido de captura duplicada en el sistema
    origen.
    """
    before = len(df)
    deduped = df.drop_duplicates(keep="first").reset_index(drop=True)
    return deduped, before - len(deduped)


# ---------------------------------------------------------------------------
# Orquestación + reporte de calidad de datos
# ---------------------------------------------------------------------------


@dataclass
class DataQualityReport:
    """Cuantifica cada decisión de limpieza tomada sobre "Producción (2)"."""

    n_filas_originales: int
    n_duplicados_removidos: int
    fechas_ambiguas_sin_resolver: pd.DataFrame
    turnos_no_registrados: pd.DataFrame
    paros_faltantes: pd.DataFrame
    # Turnos vacíos llenados desde turno_overrides.csv (confirmados + inferidos).
    n_turnos_confirmados: int = 0
    # De esos, cuántos son inferencia y no confirmación escrita.
    n_turnos_inferidos: int = 0
    n_sku_normalizados: int = 0

    def resumen(self) -> str:
        return "\n".join([
            "=== Reporte de calidad de datos: Producción ===",
            f"Filas originales:              {self.n_filas_originales}",
            f"Duplicados exactos removidos:  {self.n_duplicados_removidos}",
            f"Fechas ambiguas sin resolver:  {len(self.fechas_ambiguas_sin_resolver)}"
            + ("  (ver data/manual/date_overrides_template.csv)"
               if len(self.fechas_ambiguas_sin_resolver) else ""),
            f"SKU con espacios normalizados: {self.n_sku_normalizados}",
            f"Turnos vacíos llenados:        {self.n_turnos_confirmados}"
            "  (data/manual/turno_overrides.csv)",
            f"  confirmados por supervisor:  {self.n_turnos_confirmados - self.n_turnos_inferidos}",
            f"  inferidos, no son dato:      {self.n_turnos_inferidos}",
            f"Turnos no registrados:         {len(self.turnos_no_registrados)}",
            f"Tiempo_Paro_Min faltante:      {len(self.paros_faltantes)}",
        ])


def transform(
    df: pd.DataFrame, meses_validos: frozenset[int] | None = None
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Limpia "Producción (2)" y arma el reporte de calidad de datos.

    Orden deliberado: dedupe primero, para no contar fechas ambiguas o
    turnos no registrados dos veces en filas que son puro ruido de captura
    duplicada. Después fechas y normalización categórica, que son
    independientes entre sí.

    `meses_validos` es contexto de negocio opcional para las fechas slash
    (ver `_resolve_slash`). Sin él, el comportamiento es el original.
    """
    n_filas_originales = len(df)
    deduped, n_duplicados = deduplicate_exact(df)

    overrides = load_date_overrides()
    fechas, fechas_ambiguas = resolve_dates(deduped, overrides, meses_validos)
    turnos, n_turnos_confirmados = resolve_turnos(deduped, load_turno_overrides())

    out = deduped.copy()
    out["Fecha"] = fechas
    out["SKU"] = deduped["SKU"].apply(normalize_sku)
    out["Linea_Produccion"] = deduped["Linea_Produccion"].apply(normalize_linea_produccion)
    out["Turno"] = turnos
    out["Tiempo_Paro_Min"] = clean_tiempo_paro_min(deduped["Tiempo_Paro_Min"])

    turnos_no_registrados = out.loc[
        out["Turno"] == TURNO_NO_REGISTRADO, ["ID_Registro", "Linea_Produccion"]
    ].reset_index(drop=True)
    paros_faltantes = out.loc[
        out["Tiempo_Paro_Min"].isna(), ["ID_Registro", "Fecha", "Linea_Produccion", "Turno"]
    ].reset_index(drop=True)

    report = DataQualityReport(
        n_filas_originales=n_filas_originales,
        n_duplicados_removidos=n_duplicados,
        fechas_ambiguas_sin_resolver=fechas_ambiguas,
        turnos_no_registrados=turnos_no_registrados,
        paros_faltantes=paros_faltantes,
        n_turnos_confirmados=n_turnos_confirmados,
        n_turnos_inferidos=int(
            (deduped["Turno"].isna() & deduped["ID_Registro"].isin(load_turnos_inferidos())).sum()
        ),
        n_sku_normalizados=int((deduped["SKU"].astype(str) != out["SKU"]).sum()),
    )
    return out, report


if __name__ == "__main__":
    from src.etl.extract import extract

    df_produccion, _ = extract()
    deduped_preview, _ = deduplicate_exact(df_produccion)
    ambiguas = find_ambiguous_slash_dates(deduped_preview)
    if not DATE_OVERRIDES_TEMPLATE_PATH.exists():
        build_date_overrides_template(ambiguas, DATE_OVERRIDES_TEMPLATE_PATH)
        print(f"Plantilla escrita: {DATE_OVERRIDES_TEMPLATE_PATH} "
              f"({len(ambiguas)} fechas ambiguas)")

    cleaned, report = transform(df_produccion)
    print(report.resumen())
