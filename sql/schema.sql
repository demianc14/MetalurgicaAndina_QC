-- Modelo estrella mínimo sobre la salida limpia del pipeline de Python.
-- Lo carga src/sql_load.py (SQLite). Una fila de fact_produccion = una corrida.

DROP VIEW IF EXISTS v_kpis;
DROP TABLE IF EXISTS fact_produccion;
DROP TABLE IF EXISTS fact_pedidos;
DROP TABLE IF EXISTS dim_producto;
DROP TABLE IF EXISTS dim_linea;
DROP TABLE IF EXISTS dim_turno;
DROP TABLE IF EXISTS dim_fecha;

CREATE TABLE dim_producto (
    sku                TEXT PRIMARY KEY,
    producto           TEXT NOT NULL,
    categoria          TEXT NOT NULL,
    costo_unitario_usd REAL NOT NULL,
    precio_venta_usd   REAL NOT NULL,
    peso_kg            REAL NOT NULL
);

CREATE TABLE dim_linea (
    linea_id INTEGER PRIMARY KEY,
    linea    TEXT NOT NULL UNIQUE
);

-- Incluye 'turno no registrado': un turno vacío sin confirmación no se inventa.
CREATE TABLE dim_turno (
    turno_id INTEGER PRIMARY KEY,
    turno    TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_fecha (
    fecha TEXT PRIMARY KEY,          -- ISO yyyy-mm-dd
    anio  INTEGER NOT NULL,
    mes   INTEGER NOT NULL,
    dia   INTEGER NOT NULL
);

CREATE TABLE fact_produccion (
    id_registro          INTEGER PRIMARY KEY,
    origen               TEXT NOT NULL,                       -- archivo fuente
    fecha                TEXT REFERENCES dim_fecha (fecha),   -- NULL = fecha ambigua pendiente
    linea_id             INTEGER NOT NULL REFERENCES dim_linea (linea_id),
    turno_id             INTEGER NOT NULL REFERENCES dim_turno (turno_id),
    sku                  TEXT NOT NULL REFERENCES dim_producto (sku),
    cantidad_producida   INTEGER NOT NULL CHECK (cantidad_producida > 0),
    unidades_defectuosas INTEGER NOT NULL CHECK (unidades_defectuosas >= 0),
    tiempo_paro_min      REAL,                                -- NULL = paro no registrado (no es 0)
    costo_total          REAL NOT NULL,
    ventas_totales       REAL NOT NULL,
    profit               REAL NOT NULL,
    tasa_defectuosos     REAL NOT NULL,
    clasificacion        TEXT NOT NULL CHECK (clasificacion IN ('Excelente', 'Aceptable', 'Crítico')),
    cumple               TEXT NOT NULL CHECK (cumple IN ('Cumple', 'No cumple')),
    turno_problematico   TEXT NOT NULL CHECK (turno_problematico IN ('Sí', 'No'))
);

CREATE TABLE fact_pedidos (
    id_pedido                TEXT PRIMARY KEY,
    fecha_pedido             TEXT NOT NULL,
    fecha_entrega_programada TEXT NOT NULL,
    fecha_entrega_real       TEXT,                            -- NULL = pendiente
    cliente                  TEXT NOT NULL,
    sku                      TEXT NOT NULL REFERENCES dim_producto (sku),
    cantidad                 INTEGER NOT NULL,
    ciudad_destino           TEXT NOT NULL,
    desvio                   INTEGER,
    estado_entrega           TEXT NOT NULL,
    ingreso_usd              REAL NOT NULL,
    costo_usd                REAL NOT NULL,
    margen_usd               REAL NOT NULL
);
