"""CLI del pipeline ETL completo.

Uso:
  python -m src.cli
"""
from __future__ import annotations

from src.etl.extract import extract
from src.etl.load import aggregate_por_linea_turno, build_dataset, load, resumen_por_linea
from src.etl.transform import transform


def main() -> None:
    produccion_raw, catalogo = extract()
    print(f"Extract: {len(produccion_raw)} filas de producción, {len(catalogo)} SKUs en catálogo")

    produccion_limpia, report = transform(produccion_raw)
    print()
    print(report.resumen())

    dataset = build_dataset(produccion_limpia, catalogo)
    paths = load(dataset)

    print("\n=== Load: archivos escritos ===")
    for name, path in paths.items():
        print(f"{name}: {path}")

    print("\n=== Producción por Línea y Turno ===")
    print(aggregate_por_linea_turno(dataset))

    print("\n=== Resumen por Línea ===")
    print(resumen_por_linea(dataset).round(4))

    print("\n=== Clasificación de calidad ===")
    print(dataset["Clasificacion"].value_counts())
    print(f"\nTurnos problemáticos (Crítico + paro > 30 min): "
          f"{(dataset['Turno_problematico'] == 'Sí').sum()}")


if __name__ == "__main__":
    main()
