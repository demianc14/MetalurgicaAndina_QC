"""Tests del extract (E de ETL). Sin lógica de negocio: solo valida que ambas
hojas cargan y traen las columnas esperadas, tal cual vienen en el crudo."""
from src.etl.extract import extract


def test_extract_devuelve_dos_dataframes_no_vacios():
    produccion, catalogo = extract()
    assert not produccion.empty
    assert not catalogo.empty


def test_extract_produccion_tiene_columnas_esperadas():
    produccion, _ = extract()
    columnas_esperadas = {
        "ID_Registro",
        "Fecha",
        "Linea_Produccion",
        "Turno",
        "SKU",
        "Cantidad_Producida",
        "Unidades_Defectuosas",
        "Tiempo_Paro_Min",
    }
    assert columnas_esperadas.issubset(set(produccion.columns))


def test_extract_catalogo_tiene_columnas_esperadas():
    _, catalogo = extract()
    columnas_esperadas = {
        "SKU",
        "Producto",
        "Categoria",
        "Costo_Unitario_USD",
        "Precio_Venta_USD",
        "Peso_kg",
    }
    assert columnas_esperadas.issubset(set(catalogo.columns))
