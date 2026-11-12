# Metalúrgica Andina: control de calidad de producción con Excel, Power BI y Python

[![CI](https://github.com/demianc14/MetalurgicaAndina_QC/actions/workflows/ci.yml/badge.svg)](https://github.com/demianc14/MetalurgicaAndina_QC/actions/workflows/ci.yml)

Tres meses de datos de producción de una metalúrgica (marzo a mayo de 2026), con errores de
captura: 305 filas sucias que quedan en 290 corridas limpias. El mismo problema está
resuelto con tres herramientas, y una prueba automática compara los resultados y explica
cada diferencia.

<!-- TODO(demian): captura del dashboard. Exportar desde Power BI y guardar en docs/img/powerbi_calidad_paros.png -->
![Dashboard de calidad y paros en Power BI](docs/img/powerbi_calidad_paros.png)

## Tres herramientas, un problema

| Herramienta | Qué hace aquí | Dónde verlo |
|---|---|---|
| **Excel** | Limpieza con fórmulas (`XLOOKUP`, `IFS`, `COUNTIFS`, `SUMIFS`, `FILTER`, `SORT`, `UNIQUE`, `GETPIVOTDATA`), 13 tablas dinámicas, umbrales en hojas de parámetros y un dashboard | [docs/excel.md](docs/excel.md) · [entregables/excel/](entregables/excel/) |
| **Power BI** | Dos dashboards: calidad y paros de los tres meses, y un ejercicio donde toda la limpieza se hace en Power Query (37 pasos en M). Un tercero, de tres páginas, está en construcción | [docs/powerbi.md](docs/powerbi.md) · [entregables/powerbi/](entregables/powerbi/) |
| **Python + SQL** | Pipeline ETL en pandas con reporte de calidad, modelo estrella en SQLite con 10 vistas, 108 tests y CI | [docs/python.md](docs/python.md) · [src/](src/) · [sql/](sql/) |

## Reporte de calidad de datos

Salida de `python -m src.cli`:

| Decisión de limpieza | Marzo | Abril-mayo |
|---|---|---|
| Filas originales | 95 | 210 |
| Duplicados exactos removidos | 5 | 10 |
| Corridas resultantes | 90 | 200 |
| SKU con espacios sobrantes, normalizados para el cruce | 14 | 26 |
| Turnos vacíos llenados con confirmación documentada | 3 | 6 |
| Turnos que quedan como "no registrado" | 0 | 0 |
| Paros vacíos (se dejan vacíos, no se convierten en 0) | 5 | 7 |
| Fechas ambiguas que siguen pendientes de supervisor | 0 | 3 |
| Clasificación: Excelente / Aceptable / Crítico | 11 / 36 / 43 | 32 / 76 / 92 |
| Corridas problemáticas (Crítico y paro > 30 min) | 2 | 7 |

Las 26 fechas ambiguas de marzo se resolvieron con el criterio del supervisor que ya
estaba documentado en el Excel original, no adivinando. Detalle en
[docs/python.md](docs/python.md).

## Excel vs Python: diferencias y por qué

[`tests/test_consistencia.py`](tests/test_consistencia.py) lee los valores del Excel con
código y los compara contra pandas y contra las vistas SQL.

**Coinciden en las tres fuentes** (Excel, pandas y SQL):

| Total | Valor |
|---|---|
| Corridas (tres meses) | 290 |
| Unidades producidas | 73.148 |
| Unidades defectuosas | 2.162 |
| Minutos de paro | 3.790 |
| Clasificación Excelente / Aceptable / Crítico | 43 / 112 / 135 |
| Corridas problemáticas | 9 |
| Producción por turno: Mañana / Noche / Tarde | 22.222 / 27.424 / 23.502 |
| Turno de cada corrida, fila por fila | 290 de 290 |
| Producción por línea y turno, marzo (tabla dinámica del caso original) | 9 celdas |
| Producción y defectuosas por línea y turno, abril-mayo (2 tablas dinámicas) | 18 celdas y sus totales |
| Calidad, cumplimiento y problemáticos por turno, abril-mayo | 15 celdas |
| Paro por turno y por línea, y % defectuoso ponderado por línea | 9 celdas |
| Pedidos, ingreso, costo y margen por estado de entrega (112 pedidos) | USD 141.841,43 de margen |
| Cantidades, línea, clasificación y % defectuosos, fila por fila | 290 de 290 |

**No coinciden**, y el test afirma la diferencia exacta:

| Qué difiere | Excel | Python | Por qué |
|---|---|---|---|
| Costo total de tres meses | USD 366.882,29 | USD 365.045,29 | En el consolidado, el registro 1 tiene SKU `MA-3001`; el dato crudo dice `MA-1001`. Esa sola fila explica los USD 1.837 |
| Fechas pendientes de supervisor | 4 | 3 | `05/05/2026` es 5 de mayo se lea como se lea. La fórmula del Excel la marca como ambigua; Python la resuelve. Mueve USD 864 de costo a mayo |
| Paro promedio por corrida | 13,39 min | 13,63 min | 5 paros vacíos de marzo son 0 en el consolidado y vacíos en Python. La suma no cambia, el promedio sí |
| Etiquetas de cumplimiento | `No Cumple` (43) y `No cumple` (92) | Una sola etiqueta | Mayúscula distinta entre marzo y abril-mayo. En un filtro de Excel o Power BI son dos categorías |

Hay una diferencia más que hoy no cambia ningún número: Excel y Power Query clasifican
Excelente con `< 1 %` y Python con `<= 1 %`. Ninguna corrida cae exactamente en 1 %, y un
test avisa si eso cambia.

**Power BI.** [`tests/test_guia_powerbi.py`](tests/test_guia_powerbi.py) comprueba que el
pipeline reproduce los 12 grupos de checkpoints de la guía del dashboard de marzo
(tarjetas, matrices y top 5 de sus tres páginas). Las cifras del dashboard de tres meses
están por confirmar contra capturas (`TODO(demian)`, ver [docs/powerbi.md](docs/powerbi.md)).

## Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m src.cli       # limpia los dos archivos, muestra el reporte y escribe data/processed/
python -m src.sql_load  # crea la base SQLite y exporta las vistas a CSV
pytest                  # 108 tests, incluida la prueba de consistencia
ruff check . && mypy src
```

Para abrir los entregables: los `.xlsx` de `entregables/excel/` necesitan Excel 365 (usan
matrices dinámicas) y los `.pbix` de `entregables/powerbi/` necesitan Power BI Desktop en
Windows.

## Mi rol y limitaciones

Proyecto individual de la clase IIN2002 Analítica y Power BI (USFQ, 2026). Todo el
trabajo es mío: la limpieza y los análisis en Excel, los dashboards de Power BI, y el
pipeline de Python, la capa SQL y la prueba de consistencia, que hice aparte para
comprobar los resultados del Excel. Los datos crudos y el enunciado son del curso.

- **Dataset chico:** 290 corridas. Muestra método, no permite conclusiones estadísticas.
- **Promedios sin ponderar** en algunas tablas dinámicas y en una matriz del dashboard;
  las vistas SQL incluyen el % ponderado por volumen.
- **Caso académico:** datos de un ejercicio de clase, no de una empresa real.
- **3 fechas de abril-mayo siguen sin resolver** porque no hay respaldo para decidirlas.
- **Los pedidos de marzo** no se pueden recalcular: su hoja cruda no está en el repo.
