# Python: el pipeline ETL en detalle

El mismo Extract → Transform → Load corre sobre los dos archivos fuente (marzo y
abril-mayo) y apila el resultado. Cada función de limpieza es pura y tiene su test.

| Capa | Archivo | Qué hace |
|---|---|---|
| Extract | [`src/etl/extract.py`](../src/etl/extract.py) | Lee las hojas crudas tal cual. Cada archivo fuente es un `Dataset` con su hoja y sus meses válidos |
| Transform | [`src/etl/transform.py`](../src/etl/transform.py) | Duplicados, fechas en 3 formatos, línea, turno, SKU y paros. Cada decisión queda contada en un `DataQualityReport` |
| Load | [`src/etl/load.py`](../src/etl/load.py) | Cruce con el catálogo, costo, ventas, profit, tasa de defectuosos, clasificación y agregaciones |
| Pedidos | [`src/etl/pedidos.py`](../src/etl/pedidos.py) | Desvío de entrega, estado y margen por pedido (abril-mayo) |
| Pipeline | [`src/pipeline.py`](../src/pipeline.py) | Corre los dos archivos y los apila en 290 corridas |
| SQL | [`src/sql_load.py`](../src/sql_load.py) | Carga el resultado en SQLite y crea las vistas |
| CLI | [`src/cli.py`](../src/cli.py) | Corre todo y muestra el reporte |

## Fechas: tres formatos y una regla para no adivinar

`Fecha` mezcla ISO (`2026-03-02`), día-mes abreviado (`02-Mar-26`, `03-Apr-26`) y barras
(`03/02/2026`). Las dos primeras son inequívocas. Las de barras pueden ser MM/DD o DD/MM
según la fila. `parse_date` las resuelve con estas reglas, de la más fuerte a la más débil:

1. Día y mes iguales (`05/05/2026`): no hay nada que decidir.
2. Uno de los dos números es mayor que 12: ese solo puede ser el día.
3. El archivo declara qué meses contiene (abril-mayo: 4 y 5). Si solo uno de los dos
   números es un mes válido, ese es el mes. Es la misma técnica de la fórmula del Excel y
   del paso `Fecha_Limpia` de Power Query.
4. Cualquier otro caso es ambiguo de verdad y el pipeline **no adivina**: la fecha queda
   vacía, la fila sale en el reporte de calidad y se resuelve en
   `data/manual/date_overrides.csv`.

**Marzo.** Las 26 fechas ambiguas ya están resueltas en `data/manual/date_overrides.csv`.
No se resolvieron adivinando: la hoja `02_Produccion` del Excel original tiene el trabajo
hecho con el supervisor (columnas `Fecha Fix`, `Fecha Ok` y `Comentario`), incluidos los
5 casos que la fórmula marcó "REVISAR CON SUPERVISOR" y quedaron con un comentario
explícito (por ejemplo, "Supervisor dijo 4 de marzo"). El archivo trae 2 filas más
(`03/03/2026`) que el propio supervisor anotó como no ambiguas; el pipeline las resuelve
solo y llega a la misma fecha.

**Abril-mayo.** Quedan 3 fechas sin resolver (`04/05/2026`: 4 de mayo o 5 de abril). El
Excel también las dejó en "REVISAR CON SUPERVISOR". No hay respaldo en el repo para
decidirlas, así que siguen pendientes.

## Turnos vacíos

Un turno vacío no se rellena con el más común. Solo se llena si hay una fila para ese
`ID_Registro` en `data/manual/turno_overrides.csv`, que dice qué respaldo tiene: la columna
`Tipo` (`confirmado_supervisor` o `inferido`) y la columna `Fuente`. Un override nunca pisa
un turno que sí venía registrado, y el reporte de calidad cuenta aparte los inferidos.

- **Abril-mayo:** los 6 turnos vacíos están confirmados por el supervisor en la hoja
  `Instrucciones` del archivo. Se aplican.
- **Marzo:** 3 filas (registros 8, 25 y 36) llegan sin turno y **no hay confirmación
  escrita** en el repo. El Excel original les asignó Mañana, Tarde y Noche sin comentario.
  El ejercicio de Power Query usa una tabla `Correcciones_Turno`, pero su contenido no está
  en el repo. La asignación se **infirió** de la guía del dashboard de la clase: de las 27
  combinaciones posibles, Mañana/Tarde/Noche es la única que reproduce su checkpoint de
  paro promedio por turno (15,3 / 12,3 / 15,3 min; `test_p3_paro_promedio_por_turno`).
  Se aplica con `Tipo = inferido`: es lo que el curso asumió, no un dato de la fila. Sin
  ella, esas 3 corridas quedarían como "turno no registrado".

## Paros vacíos

Un paro no registrado no es un paro de 0 minutos. `Tiempo_Paro_Min` vacío queda como
`NaN` (12 corridas: 5 de marzo y 7 de abril-mayo). Las sumas no cambian; los promedios sí,
porque no cuentan corridas sin dato.

Consecuencia: esas 12 corridas no pueden evaluarse como turno problemático. La regla pide
paro mayor a 30 minutos; sin dato, la fila queda en "No" por defecto, no porque se sepa
que no hubo problema.

## Reglas de clasificación

| Regla | Condición |
|---|---|
| Excelente | `Tasa_defectuosos <= 0.01` |
| Aceptable | `0.01 < Tasa_defectuosos <= 0.03` |
| Crítico | `Tasa_defectuosos > 0.03` |
| Cumple | Excelente o Aceptable |
| Turno problemático | Crítico **y** `Tiempo_Paro_Min > 30` (estricto) |

El Excel de abril-mayo y Power Query usan `< 0.01` para Excelente. Hoy da igual: ninguna
de las 290 corridas cae exactamente en 1 %. `test_frontera_excelente_es_latente` falla el
día que aparezca una, para obligar a decidir cuál regla es la del negocio.

## Capa SQL

[`sql/schema.sql`](../sql/schema.sql) define un modelo estrella mínimo:
`fact_produccion`, `fact_pedidos`, `dim_producto`, `dim_linea`, `dim_turno` y `dim_fecha`,
con llaves foráneas y restricciones `CHECK`. [`sql/vistas.sql`](../sql/vistas.sql) crea
10 vistas; cada una indica qué tabla dinámica del Excel o qué visual de Power BI
reproduce.

```bash
python -m src.sql_load
```

Escribe `data/processed/metalurgica.db` y un CSV por vista en `data/processed/vistas/`.

## Limitaciones

- **3 turnos de marzo son una inferencia**, no un dato (ver "Turnos vacíos"). Los totales
  por turno de marzo coinciden con el Excel por eso, no porque la fila lo diga.
- **Dataset chico:** 290 corridas en tres meses. Sirve para mostrar método, no para
  sacar conclusiones estadísticas.
- **Promedios sin ponderar:** `Tasa_defectuosos_promedio` por línea es un promedio simple
  de corridas. Con lotes de tamaño distinto conviene mirar el % ponderado
  (`v_paro_por_linea`, `v_calidad_por_turno`).
- **Pedidos de marzo:** su hoja cruda no está en el repo; solo existen ya procesados
  dentro del consolidado, así que Python cubre los 112 pedidos de abril-mayo.
- **Caso académico:** los datos son de un ejercicio de clase (IIN2002, USFQ), no de una
  empresa real.
