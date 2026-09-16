# 🏭 Metalúrgica Andina — QC de Producción

Pipeline de limpieza y análisis de calidad para datos de producción industrial
con formatos inconsistentes, basado en un caso real de la clase IIN2002 (USFQ).

## Contexto del caso

- `data/raw/CruzDemian_IIN2002_Caso_MetalurgicaAndina.xlsx`
  - **"Producción (2)"** — datos crudos y sucios: `ID_Registro`, `Fecha`,
    `Linea_Produccion`, `Turno`, `SKU`, `Cantidad_Producida`,
    `Unidades_Defectuosas`, `Tiempo_Paro_Min`.
  - **"01_Catalogo_Productos"** — catálogo limpio: `SKU`, `Producto`,
    `Categoria`, `Costo_Unitario_USD`, `Precio_Venta_USD`, `Peso_kg`.

## Arquitectura

Pipeline ETL (Extract → Transform → Load), mismo patrón del proyecto
hermano `world-cup-predictor`, con funciones puras y testeables en cada
capa:

- **Extract** (`src/etl/extract.py`) — lee ambas hojas tal cual, sin
  ninguna lógica de negocio.
- **Transform** (`src/etl/transform.py`) — limpia `Producción (2)`:
  fechas mixtas, `SKU`/`Linea_Produccion`/`Turno` normalizados,
  duplicados exactos removidos, `Tiempo_Paro_Min` faltante preservado
  como NaN. Cada decisión queda cuantificada en un
  `DataQualityReport`, no aplicada en abstracto.
- **Load** (`src/etl/load.py`) — une con el catálogo por `SKU`, calcula
  `Costo_total`/`Ventas_totales`/`Profit`/`Tasa_defectuosos`, clasifica
  la calidad en 3 niveles y agrega por Línea/Turno (equivalente a las
  tablas dinámicas del Excel original). Escribe todo en `data/processed/`.
- **CLI** (`src/cli.py`) — corre el pipeline completo y muestra un resumen.

### Fechas ambiguas: fail fast + escalación documentada

`Fecha` mezcla 3 formatos fila por fila sin convención global: ISO
("2026-03-02"), "DD-Mon-YY" ("02-Mar-26") y slash ("03/02/2026"). Las dos
primeras son inequívocas. El formato slash es ambiguo (MM/DD o DD/MM)
salvo que uno de los dos números sea >12 — ahí solo puede ser el día.

Para las filas genuinamente ambiguas (ambos números <=12), el pipeline
**no adivina**: mismo patrón de "fail fast + escalación documentada" que
`resilience.py` en `world-cup-predictor` — si algo no se puede resolver
sin contexto de negocio, se deja explícito en un artefacto en vez de
inventar un valor. `find_ambiguous_slash_dates` + `build_date_overrides_template`
generan `data/manual/date_overrides_template.csv` con esas filas;
`load_date_overrides` lee `data/manual/date_overrides.csv` si existe y lo
aplica solo a ellas — el pipeline nunca falla por su ausencia, esas
fechas simplemente quedan en el reporte de calidad como pendientes.

**Nota sobre este repo en particular:** las 28 filas ambiguas del caso ya
están resueltas en `data/manual/date_overrides.csv`. No las resolví yo
adivinando: mientras exploraba el Excel original encontré una hoja oculta,
`02_Produccion`, con el trabajo de limpieza ya hecho con el supervisor
(columnas `Fecha Fix`/`Fecha Ok`/`Comentario`). Recuperé esos 28 valores
de ahí — incluidos los 5 casos donde ni el criterio automático del
Excel supo resolverlos ("REVISAR CON SUPERVISOR") y quedaron con un
comentario explícito (p.ej. "Supervisor dijo 4 de marzo"). Es la misma
decisión de negocio ya tomada una vez, portada, no inventada de nuevo.
Si en el futuro aparecen filas ambiguas nuevas sin ese respaldo, el
template sigue generándose vacío para llenarlo a mano.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m src.cli    # corre Extract -> Transform -> Load y muestra el resumen
pytest                # tests del ETL
ruff check .          # lint
mypy src              # tipos
```

## Reglas de clasificación de calidad

| Regla | Condición |
|---|---|
| `Clasificacion = "Excelente"` | `Tasa_defectuosos <= 0.01` |
| `Clasificacion = "Aceptable"` | `0.01 < Tasa_defectuosos <= 0.03` |
| `Clasificacion = "Crítico"` | `Tasa_defectuosos > 0.03` |
| `Cumple` | `"Cumple"` si Excelente o Aceptable, si no `"No cumple"` |
| `Turno_problematico` | `"Sí"` si Crítico **y** `Tiempo_Paro_Min > 30` (estricto), si no `"No"` |

Verificadas de forma independiente (recalculando `Tasa_defectuosos` desde
`Unidades_Defectuosas`/`Cantidad_Producida`, sin leer las columnas ya
clasificadas del Excel) contra las 90 filas de la hoja `02_Produccion`:
coinciden en las 90, incluidas ambas fronteras exactas (0.01 y 0.03) y el
caso límite `Tiempo_Paro_Min == 30` (no problemático, porque la regla es
estricta). No se encontró ninguna inconsistencia.

## Reporte de calidad de datos (hoja "Producción (2)")

Cuantificado por `python -m src.cli` sobre el dataset real:

| Decisión de limpieza | Cantidad |
|---|---|
| Filas originales | 95 |
| Duplicados exactos removidos (mismo `ID_Registro` y mismos valores) | 5 |
| Filas resultantes | 90 |
| Fechas slash ambiguas | 28 (resueltas vía `date_overrides.csv`, ver arriba) |
| `SKU` con espacio inicial inconsistente, normalizado para el join | 9 |
| `Turno` no registrado (NaN, no se asumió ningún valor) | 3 |
| `Tiempo_Paro_Min` faltante (NaN explícito, no convertido a 0) | 5 |
| Clasificación final: Excelente / Aceptable / Crítico | 11 / 36 / 43 |
| Turnos problemáticos (Crítico + paro > 30 min) | 2 |

## Limitaciones honestas

- **3 filas quedan con `Turno = "turno no registrado"` a propósito.** No
  se les asignó Mañana/Tarde/Noche porque no hay ningún dato en la fila
  que lo indique — inventar uno (p.ej. el turno más común) habría sido un
  dato falso disfrazado de limpio. Esto es una decisión correcta, no una
  limitación del pipeline: la limitación real es que esas 3 filas no se
  pueden usar en ningún análisis agrupado por turno sin perderlas o
  sesgar el resultado, así que quedan en su propia categoría visible
  (`aggregate_por_linea_turno` les da una columna aparte) en vez de
  desaparecer. **Diferencia real con el Excel original:** ahí esas mismas
  3 filas sí fueron asignadas a un turno (Mañana/Noche/Tarde, una a cada
  uno, sin ningún comentario que lo justifique) — a diferencia de las
  fechas, que sí tienen criterio documentado. Por eso el total general de
  `aggregate_por_linea_turno` (22934) coincide exactamente con la tabla
  dinámica del Excel original, pero los totales por turno individual no:
  este pipeline no reproduce ese supuesto sin respaldo.
- **5 filas con `Tiempo_Paro_Min` faltante no pueden evaluarse para
  `Turno_problematico`.** La regla necesita `Tiempo_Paro_Min > 30`; sin
  ese dato, la fila cae a `"No"` por la rama por defecto de la regla, no
  porque se sepa que el turno no fue problemático. Si alguna de esas 5
  filas es en realidad Crítica y tuvo un paro largo, este pipeline no lo
  va a mostrar como problemático. Quedan señaladas aparte en el reporte
  de calidad para que no se pierdan silenciosamente en los agregados.
- **Las 28 fechas ambiguas se resolvieron recuperando una decisión de
  negocio ya tomada** (ver arriba), no con un criterio nuevo. Si se
  agregan filas nuevas al dataset con fechas slash ambiguas y sin
  respaldo similar, sí van a quedar pendientes de revisión manual real —
  el pipeline no vuelve a adivinar solo porque encontró la respuesta una
  vez.
- **El dataset es chico (95 filas crudas, 90 después de deduplicar).**
  Los promedios por Línea (`Tasa_defectuosos_promedio`) no están
  ponderados por volumen — con lotes de tamaño tan distinto entre SKUs,
  esa tasa promedio simple puede no representar bien el impacto real en
  unidades defectuosas; para eso conviene mirar
  `Unidades_Defectuosas_total` junto a la tasa, no la tasa sola.

## Estado

- [x] Extract: lee ambas hojas del Excel sin transformarlas.
- [x] Transform: fechas mixtas, normalización de `SKU`/`Linea_Produccion`/
      `Turno`, duplicados exactos y `Tiempo_Paro_Min` faltante — con
      reporte de calidad de datos cuantificado.
- [x] Load: join con catálogo, métricas financieras, clasificación de
      calidad y agregaciones por Línea/Turno en `data/processed/`.
