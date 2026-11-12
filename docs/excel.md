# Excel: qué hace cada libro y cada hoja

Todo lo que está aquí se leyó de los archivos con código (`openpyxl`): hojas, tablas,
fórmulas, tablas dinámicas y sus valores en caché. Lo que no se puede leer con código
(cómo se ven los gráficos, el formato del dashboard) está marcado `TODO(demian)`.

| Archivo | Periodo | Qué es |
|---|---|---|
| [`data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx`](../data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx) | Marzo 2026 | Caso original: 95 filas sucias, limpieza con fórmulas y 5 tablas dinámicas |
| [`entregables/excel/MetalurgicaAndina_DCruz_AprMay2026.xlsx`](../entregables/excel/MetalurgicaAndina_DCruz_AprMay2026.xlsx) | Abril-mayo 2026 | Libro de trabajo P1 a P8: limpieza, costos, calidad, entregas, listas dinámicas, dashboard y conclusión |
| [`entregables/excel/Consolidado_Pedidos_Produccion_DCruz_MarAbrMay2026.xlsx`](../entregables/excel/Consolidado_Pedidos_Produccion_DCruz_MarAbrMay2026.xlsx) | Marzo a mayo | Tablas finales `tbl_prd` (290 corridas) y `tbl_ped` (168 pedidos), solo valores |

## 1. Libro de abril-mayo (`MetalurgicaAndina_DCruz_AprMay2026.xlsx`)

15 hojas, 5 tablas con nombre, 8 tablas dinámicas, 5 gráficos y unas 7.200 celdas con fórmula.

### Hojas de entrada

| Hoja | Contenido |
|---|---|
| `Instrucciones` | Enunciado de la práctica (versión "Grupo 2"). Documenta el rango de meses válido (abril/mayo) y los **6 turnos confirmados por el supervisor** |
| `01_Catalogo_Productos` | 16 SKU con producto, categoría, costo, precio y peso |
| `02_Produccion_Sucia` | 210 filas: 105 de abril y 105 de mayo, con 10 duplicados exactos, 3 formatos de fecha, espacios y mayúsculas inconsistentes, 6 turnos vacíos y 7 paros vacíos |
| `04_Pedidos` | 112 pedidos de clientes |

### Hojas de trabajo

| Hoja | Entra | Sale | Decisión de limpieza o análisis |
|---|---|---|---|
| `P1_Produccion_Limpia` (tabla `Table1`, 210 filas) | `02_Produccion_Sucia` | Fecha corregida, línea, turno y SKU normalizados, marca de duplicado | Detecta el formato de fecha, resuelve las fechas con barras usando el rango de meses válido, llena turnos vacíos con la tabla de confirmaciones, marca duplicados sin borrarlos |
| `P2_NoDuplicados_Graficos` (`Table2`, 200 filas) | P1 sin duplicados | 2 tablas dinámicas línea × turno (producción y defectuosas) y 2 gráficos | Quita los 10 duplicados |
| `P3_Costos` (`Table24`) | P2 + catálogo | Costo total por corrida y tabla dinámica `PT_Costo_Mes` | Cruza con el catálogo por SKU; las 4 fechas sin resolver quedan en un grupo "REVISAR CON SUPERVISOR" |
| `P4_Calidad` (`Tabla_Calidad`) | P3 | % defectuosos, Cumple, Nivel de calidad, Problemático; 3 reportes con `COUNTIFS` y 3 tablas dinámicas que los verifican | Umbrales parametrizados en `DatosP4`, no escritos dentro de la fórmula |
| `DatosP4` | — | Tabla de parámetros: 1 %, 3 %, 30 min y sus etiquetas | Cambiar un umbral actualiza todo P4 |
| `P5_Entregas` (`Tabla_Pedidos`, 112 filas) | `04_Pedidos` + catálogo | Días de entrega, desvío, estado, ingreso, costo y margen por pedido; tabla dinámica `PT_Entregas` y 1 gráfico | Pedido sin fecha real = PENDIENTE (no se asume entregado) |
| `DatosP5` | — | Parámetros de estado de entrega: ≤ 0 días A TIEMPO, 1 a 3 LEVE, > 3 ATRASADO | |
| `P6_Listas` | `Tabla_Pedidos` | Lista de pedidos atrasados de la ciudad elegida y lista de clientes activos | Matrices dinámicas: cambian solas al cambiar la ciudad |
| `DatosP6` | `Tabla_Pedidos` | Lista de ciudades sin repetir | |
| `P7_Dashboard` | P4 y P5 | Resumen de calidad y de entregas con 2 gráficos | Lee la tabla dinámica con `GETPIVOTDATA` |
| `P8_Conclusion` | P2 y P4 | Paro total, por turno y por línea; % defectuoso ponderado; conclusión escrita | |

### Fórmulas representativas (copiadas del archivo)

**Detectar el formato de fecha** (`P1!D5`):

```excel
=IF(ISNUMBER(SEARCH("/",C5)),"SLASH",IF(LEN(C5)=10,"ISO","MMM"))
```

**Resolver fechas con barras usando el rango de meses válido** (`P1!E5`). Si los dos números
pueden ser mes (4 o 5), no adivina y lo escala:

```excel
=IF(D5="SLASH",
   IF(AND(OR(VALUE(LEFT(C5,2))=4,VALUE(LEFT(C5,2))=5),OR(VALUE(MID(C5,4,2))=4,VALUE(MID(C5,4,2))=5)),
      "REVISAR CON SUPERVISOR",
      IF(OR(VALUE(MID(C5,4,2))=4,VALUE(MID(C5,4,2))=5),
         DATE(VALUE(RIGHT(C5,4)),VALUE(MID(C5,4,2)),VALUE(LEFT(C5,2))),
         DATE(VALUE(RIGHT(C5,4)),VALUE(LEFT(C5,2)),VALUE(MID(C5,4,2))))),
   DATEVALUE(C5))
```

**Normalizar línea y turno, con turnos confirmados por `VLOOKUP`** (`P1!F5`, `P1!G5`):

```excel
="Línea "&RIGHT(TRIM('02_Produccion_Sucia'!C2),1)
=IF(TRIM('02_Produccion_Sucia'!D2)="",IFERROR(VLOOKUP(B5,$R$5:$S$10,2,FALSE),"REVISAR"),PROPER(TRIM('02_Produccion_Sucia'!D2)))
```

**Marcar duplicados sin borrarlos** (`P1!L5`):

```excel
=IF(COUNTIF($B$5:B5,B5)>1,"Duplicado","Válido")
```

**Cruce con el catálogo** (`P3!L5`, `P3!N5`):

```excel
=XLOOKUP(H5,'01_Catalogo_Productos'!A:A,'01_Catalogo_Productos'!B:B)
=XLOOKUP(L5,'01_Catalogo_Productos'!B:B,'01_Catalogo_Productos'!D:D)
```

**Clasificación de calidad con umbrales en una hoja de parámetros** (`P4!S5`, `P4!T5`, `P4!U5`):

```excel
=IF([@[%_defectuosos]]<=DatosP4!$D$5,DatosP4!$C$5,DatosP4!$C$6)
=IFS([@[%_defectuosos]]<DatosP4!$D$2,DatosP4!$C$2,[@[%_defectuosos]]<=DatosP4!$D$3,DatosP4!$C$3,TRUE,DatosP4!$C$4)
=IF(AND([@[%_defectuosos]]>DatosP4!$D$6,[@[Tiempo_Paro_Min]]>DatosP4!$D$7),DatosP4!$C$7,"No")
```

**Reportes con `COUNTIFS` y `SUMIFS`** (`P4!X6`, `P4!X10`, `P8!F5`):

```excel
=COUNTIFS(Tabla_Calidad[Cumple],$W6,Tabla_Calidad[Turno],X$5)
=IFERROR(SUMIFS(Tabla_Calidad[Unidades_Defectuosas],Tabla_Calidad[Turno],X$5)/SUMIFS(Tabla_Calidad[Cantidad_Producida],Tabla_Calidad[Turno],X$5),0)
=SUMIFS(Table2[Tiempo_Paro_Min],Table2[Turno],E5)
```

**Estado de entrega** (`P5!M2`):

```excel
=IFS([@desvio]="",DatosP5!$C$5,[@desvio]<=DatosP5!$D$2,DatosP5!$C$2,[@desvio]<=DatosP5!$D$4,DatosP5!$C$3,TRUE,DatosP5!$C$4)
```

**Matrices dinámicas** (`P6!B10`, `P6!B27`):

```excel
=SORT(FILTER(Tabla_Pedidos,(Tabla_Pedidos[Ciudad_Destino]=$C$4)*(Tabla_Pedidos[estado_entrega]=DatosP5!$C$4),"Sin pedidos atrasados"),12,-1)
=SORT(UNIQUE(Tabla_Pedidos[Cliente]))
```

**Dashboard leyendo una tabla dinámica y buscando el máximo** (`P7!I7`, `P8!C8`):

```excel
=GETPIVOTDATA("Nº pedidos",P5_Entregas!$U$3,"estado_entrega","A TIEMPO")
=INDEX(E5:E7,MATCH(MAX(F5:F7),F5:F7,0))
```

### Tablas dinámicas

| Nombre | Hoja | Qué resume | Vista SQL equivalente |
|---|---|---|---|
| `PivotTable1` | P2 | Suma de `Cantidad_Producida`, línea × turno | `v_produccion_linea_turno` |
| `PivotTable2` | P2 | Suma de `Unidades_Defectuosas`, línea × turno | `v_produccion_linea_turno` |
| `PT_Costo_Mes` | P3 | Costo total por mes | `v_costo_por_mes` |
| `PT_Cumple`, `PT_Nivel`, `PT_Problematico` | P4 | Conteo de corridas por turno | `v_calidad_por_turno` |
| `PT_Entregas` | P5 | Pedidos, ingreso, costo y margen por estado de entrega | `v_entregas_por_estado` |
| `PivotTable1` | P5 | Margen por estado de entrega | `v_entregas_por_estado` |

### Resultados que da el Excel (valores en caché, verificados en `tests/test_consistencia.py`)

- 200 corridas válidas, 50.214 unidades producidas, 1.471 defectuosas (2,93 % ponderado).
- Nivel de calidad: 32 Excelente, 76 Aceptable, 92 Crítico. 7 corridas problemáticas (3 en la mañana, 4 en la noche).
- 2.555 minutos de paro (42,6 horas); la noche es el turno con más paro (1.020 min).
- Costo de producción: USD 277.203,46.
- 112 pedidos: 29 a tiempo, 29 con atraso leve, 26 atrasados, 28 pendientes. Margen total USD 141.841,43; un pedido a tiempo deja en promedio USD 918 más de margen que uno atrasado.

## 2. Caso original de marzo (`CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx`)

| Hoja | Contenido |
|---|---|
| `Producción (2)` (tabla `Tablaproduccion2`) | 95 filas crudas |
| `01_Catalogo_Productos` | Catálogo de 16 SKU |
| `02_Produccion` (tabla `Tablaproduccion1`, 90 filas, 1.720 fórmulas) | Limpieza con columnas `Fecha Tipo`, `Fecha Fix`, `Fecha Ok` y `Comentario` del supervisor; costo, ventas y profit; clasificación; 5 tablas dinámicas y 4 gráficos |

Tablas dinámicas de `02_Produccion`: producción línea × turno, defectuosas línea × turno,
producción por línea, resumen por línea (producción, defectuosas y tasa promedio) y
producción por día.

## 3. Consolidado (`Consolidado_Pedidos_Produccion_DCruz_MarAbrMay2026.xlsx`)

| Hoja | Tabla | Filas | Columnas |
|---|---|---|---|
| `Produccion` | `tbl_prd` | 290 (90 de marzo + 200 de abril-mayo) | ID, fecha, línea, turno, SKU, cantidades, paro, categoría, costo, % defectuosos, estado de calidad, nivel de calidad, problemático |
| `Pedidos` | `tbl_ped` | 168 (56 de marzo + 112 de abril-mayo) | Pedido, fechas, cliente, SKU, cantidad, ciudad, desvío, estado, precio, costo, ingreso y margen |

No tiene fórmulas: son los valores finales pegados, listos para ser la fuente de Power BI.
Al compararlo fila por fila contra los datos crudos aparecieron 4 diferencias; están en el
[README](../README.md#excel-vs-python-diferencias-y-por-qué).

## Pendiente

- `TODO(demian)`: captura del dashboard (`P7_Dashboard`) en `docs/img/excel_dashboard.png`.
- `TODO(demian)`: los 4 gráficos de marzo y los 5 de abril-mayo no se pueden describir con código más allá de que existen; agrega una línea sobre qué muestra cada uno si quieres destacarlos.
