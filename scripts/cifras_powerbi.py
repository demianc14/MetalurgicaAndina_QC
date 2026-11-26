#!/usr/bin/env python3
"""Cifras del pipeline para comparar con las tarjetas de los informes de Power BI.

Lee lo que escribe `python -m src.cli` (no recalcula nada):
  - data/processed/produccion_3_meses.csv   (salida del pipeline de pandas)
  - data/processed/vistas/v_kpis.csv        (vista SQL v_kpis)

Uso:
  python -m src.cli > /dev/null
  python3 scripts/cifras_powerbi.py

Las cifras de docs/powerbi.md (columna "Pipeline") salen de este script.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PRODUCCION = RAIZ / "data" / "processed" / "produccion_3_meses.csv"
KPIS = RAIZ / "data" / "processed" / "vistas" / "v_kpis.csv"


def cifras_pipeline(produccion: pd.DataFrame) -> dict[str, float | int | str]:
    """Las mismas agregaciones que muestran las tarjetas, sobre la tabla limpia."""
    fechas = pd.to_datetime(produccion["Fecha"], errors="coerce")
    clasificacion = produccion["Clasificacion"].value_counts()
    return {
        "Corridas / registros": len(produccion),
        "Unidades producidas": int(produccion["Cantidad_Producida"].sum()),
        "Unidades defectuosas": int(produccion["Unidades_Defectuosas"].sum()),
        "Paro total (min)": float(produccion["Tiempo_Paro_Min"].sum()),
        "Paro promedio por registro (min)": round(float(produccion["Tiempo_Paro_Min"].mean()), 2),
        "Costo total (USD)": round(float(produccion["Costo_total"].sum()), 2),
        "Turnos problemáticos": int((produccion["Turno_problematico"] == "Sí").sum()),
        "Excelente / Aceptable / Crítico": " / ".join(
            str(int(clasificacion.get(c, 0))) for c in ("Excelente", "Aceptable", "Crítico")
        ),
        "Primera y última fecha": f"{fechas.min():%d/%m/%Y} a {fechas.max():%d/%m/%Y}",
        "Registros sin fecha": int(fechas.isna().sum()),
    }


def _imprimir(titulo: str, cifras: dict[str, float | int | str]) -> None:
    print(f"\n=== {titulo} ===")
    for nombre, valor in cifras.items():
        print(f"{nombre:<36} {valor}")


def main() -> int:
    try:
        produccion = pd.read_csv(PRODUCCION)
        kpis = pd.read_csv(KPIS)
    except FileNotFoundError as error:
        print(f"Falta {error.filename}: corre antes `python -m src.cli`.", file=sys.stderr)
        return 1

    _imprimir("Pipeline, tres meses", cifras_pipeline(produccion))
    _imprimir("Pipeline, marzo", cifras_pipeline(produccion[produccion["Origen"] == "marzo"]))

    print("\n=== Vista SQL v_kpis ===")
    print(kpis.to_string(index=False))
    totales = kpis[["corridas", "unidades_producidas", "unidades_defectuosas",
                    "paro_min", "costo_total"]].sum()
    print("total      " + "  ".join(f"{v:,.2f}" for v in totales))
    return 0


if __name__ == "__main__":
    sys.exit(main())
