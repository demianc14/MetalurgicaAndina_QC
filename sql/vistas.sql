-- Vistas que reproducen las tablas dinámicas y reportes del Excel de la clase.
-- Cada vista indica qué hoja/rango del Excel reproduce.

DROP VIEW IF EXISTS v_produccion_linea_turno;
DROP VIEW IF EXISTS v_calidad_por_turno;
DROP VIEW IF EXISTS v_paro_por_turno;
DROP VIEW IF EXISTS v_paro_por_linea;
DROP VIEW IF EXISTS v_costo_por_mes;
DROP VIEW IF EXISTS v_margen_por_linea;
DROP VIEW IF EXISTS v_defectos_por_categoria;
DROP VIEW IF EXISTS v_top_sku_defectos;
DROP VIEW IF EXISTS v_entregas_por_estado;
DROP VIEW IF EXISTS v_kpis;

-- P2_NoDuplicados_Graficos: "Sum of Cantidad_Producida" y "Sum of Unidades_Defectuosas".
CREATE VIEW v_produccion_linea_turno AS
SELECT f.origen,
       l.linea,
       t.turno,
       COUNT(*)                    AS corridas,
       SUM(f.cantidad_producida)   AS cantidad_producida,
       SUM(f.unidades_defectuosas) AS unidades_defectuosas
FROM fact_produccion f
JOIN dim_linea l ON l.linea_id = f.linea_id
JOIN dim_turno t ON t.turno_id = f.turno_id
GROUP BY f.origen, l.linea, t.turno;

-- P4_Calidad: reportes 1 a 3 (cumple, nivel de calidad y problemáticos por turno).
CREATE VIEW v_calidad_por_turno AS
SELECT f.origen,
       t.turno,
       COUNT(*)                                                     AS corridas,
       SUM(f.clasificacion = 'Excelente')                           AS excelente,
       SUM(f.clasificacion = 'Aceptable')                           AS aceptable,
       SUM(f.clasificacion = 'Crítico')                             AS critico,
       SUM(f.cumple = 'Cumple')                                     AS cumple,
       SUM(f.turno_problematico = 'Sí')                             AS problematicos,
       1.0 * SUM(f.unidades_defectuosas) / SUM(f.cantidad_producida) AS pct_defectuosos_ponderado
FROM fact_produccion f
JOIN dim_turno t ON t.turno_id = f.turno_id
GROUP BY f.origen, t.turno;

-- P8_Conclusion: minutos de paro por turno. SUM ignora NULL (paro no registrado).
CREATE VIEW v_paro_por_turno AS
SELECT f.origen,
       t.turno,
       SUM(f.tiempo_paro_min)          AS paro_min,
       SUM(f.tiempo_paro_min IS NULL)  AS corridas_sin_dato_de_paro
FROM fact_produccion f
JOIN dim_turno t ON t.turno_id = f.turno_id
GROUP BY f.origen, t.turno;

-- P8_Conclusion: minutos de paro y % defectuosos ponderado por línea.
CREATE VIEW v_paro_por_linea AS
SELECT f.origen,
       l.linea,
       SUM(f.tiempo_paro_min)                                        AS paro_min,
       1.0 * SUM(f.unidades_defectuosas) / SUM(f.cantidad_producida) AS pct_defectuosos_ponderado
FROM fact_produccion f
JOIN dim_linea l ON l.linea_id = f.linea_id
GROUP BY f.origen, l.linea;

-- P3_Costos: "Costo total por mes". mes NULL = fecha ambigua pendiente de supervisor.
CREATE VIEW v_costo_por_mes AS
SELECT d.mes,
       COUNT(*)           AS corridas,
       SUM(f.costo_total) AS costo_total
FROM fact_produccion f
LEFT JOIN dim_fecha d ON d.fecha = f.fecha
GROUP BY d.mes;

-- Margen (ventas - costo) de lo producido, por línea.
CREATE VIEW v_margen_por_linea AS
SELECT f.origen,
       l.linea,
       SUM(f.ventas_totales) AS ventas_totales,
       SUM(f.costo_total)    AS costo_total,
       SUM(f.profit)         AS margen
FROM fact_produccion f
JOIN dim_linea l ON l.linea_id = f.linea_id
GROUP BY f.origen, l.linea;

-- Power BI: "Unidades defectuosas por categoría" y mezcla de calidad por categoría.
CREATE VIEW v_defectos_por_categoria AS
SELECT p.categoria,
       COUNT(*)                           AS corridas,
       SUM(f.unidades_defectuosas)        AS unidades_defectuosas,
       SUM(f.clasificacion = 'Excelente') AS excelente,
       SUM(f.clasificacion = 'Aceptable') AS aceptable,
       SUM(f.clasificacion = 'Crítico')   AS critico
FROM fact_produccion f
JOIN dim_producto p ON p.sku = f.sku
GROUP BY p.categoria;

-- Power BI: "Top 5 SKU por unidades defectuosas".
CREATE VIEW v_top_sku_defectos AS
SELECT f.sku,
       p.producto,
       SUM(f.unidades_defectuosas) AS unidades_defectuosas
FROM fact_produccion f
JOIN dim_producto p ON p.sku = f.sku
GROUP BY f.sku, p.producto
ORDER BY unidades_defectuosas DESC, f.sku
LIMIT 5;

-- P5_Entregas: tabla dinámica PT_Entregas.
CREATE VIEW v_entregas_por_estado AS
SELECT estado_entrega,
       COUNT(*)        AS n_pedidos,
       SUM(ingreso_usd) AS ingreso_usd,
       SUM(costo_usd)   AS costo_usd,
       SUM(margen_usd)  AS margen_usd,
       AVG(margen_usd)  AS margen_promedio_usd
FROM fact_pedidos
GROUP BY estado_entrega;

-- Tarjetas (KPI) de los dashboards de Power BI.
CREATE VIEW v_kpis AS
SELECT origen,
       COUNT(*)                  AS corridas,
       SUM(cantidad_producida)   AS unidades_producidas,
       SUM(unidades_defectuosas) AS unidades_defectuosas,
       SUM(tiempo_paro_min)      AS paro_min,
       SUM(costo_total)          AS costo_total
FROM fact_produccion
GROUP BY origen;
