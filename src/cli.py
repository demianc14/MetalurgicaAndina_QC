"""CLI del pipeline ETL completo (marzo + abril-mayo).

Uso:
  python -m src.cli
"""
from __future__ import annotations

from src.etl.load import aggregate_por_linea_turno, load, resumen_por_linea
from src.etl.pedidos import resumen_por_estado
from src.pipeline import run_all, write
from src.sql_load import build_database, export_vistas


def main() -> None:
    resultado = run_all()
    produccion = resultado.produccion

    for nombre, report in resultado.reportes.items():
        print(f"\n##### Archivo fuente: {nombre}")
        print(report.resumen())
        parte = produccion[produccion["Origen"] == nombre]
        print(f"Filas resultantes:             {len(parte)}")
        print("Clasificación (Excelente / Aceptable / Crítico): "
              + " / ".join(str((parte["Clasificacion"] == c).sum())
                           for c in ("Excelente", "Aceptable", "Crítico")))
        print(f"Turnos problemáticos (Crítico + paro > 30 min): "
              f"{(parte['Turno_problematico'] == 'Sí').sum()}")

    # Salidas históricas del caso original (solo marzo).
    marzo = produccion[produccion["Origen"] == "marzo"].drop(columns="Origen")
    paths = load(marzo)
    paths.update(write(resultado))

    print("\n=== Tres meses: producción por Línea y Turno ===")
    print(aggregate_por_linea_turno(produccion))

    print("\n=== Tres meses: resumen por Línea ===")
    print(resumen_por_linea(produccion).round(4))

    print("\n=== Tres meses: totales ===")
    print(f"Corridas:             {len(produccion)}")
    print(f"Unidades producidas:  {produccion['Cantidad_Producida'].sum()}")
    print(f"Unidades defectuosas: {produccion['Unidades_Defectuosas'].sum()}")
    print(f"Paro (min):           {produccion['Tiempo_Paro_Min'].sum():.0f}")
    print(f"Costo total (USD):    {produccion['Costo_total'].sum():,.2f}")

    print("\n=== Pedidos abril-mayo por estado de entrega ===")
    print(resumen_por_estado(resultado.pedidos).round(2))

    conn = build_database(resultado)
    paths.update(export_vistas(conn))
    conn.close()

    print("\n=== Archivos escritos ===")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
