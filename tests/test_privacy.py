"""Privacidad del repo: lo que no debe publicarse no está versionado.

- Ningún .pbix versionado: guardan por dentro la URL de OneDrive
  institucional (con el usuario de la universidad).
- .gitignore ignora los .pbix y la guía del profesor.
- Ningún archivo versionado (texto, o el XML dentro de un .xlsx/.docx)
  contiene una URL de SharePoint/OneDrive.
- Ningún .xlsx versionado trae `creator` ni `lastModifiedBy` con contenido,
  rutas locales (/Users/..., C:\\Users\\..., /home/...) ni `refreshedBy`
  en sus tablas dinámicas. Se arregla con
  `python3 scripts/limpiar_metadatos_xlsx.py`.

Usa `git ls-files`: si el directorio no es un repo git, los tests se saltan.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

import openpyxl
import pytest

ESTE_ARCHIVO = Path(__file__).resolve()
URL_ONEDRIVE = re.compile(rb"https?://[^\s\"'<>]*(sharepoint\.com|onedrive\.live\.com|1drv\.ms)")
EXTENSIONES_ZIP = {".xlsx", ".xlsm", ".docx", ".pptx"}
SCRIPT_LIMPIEZA = ESTE_ARCHIVO.parents[1] / "scripts" / "limpiar_metadatos_xlsx.py"

NS_DC = "{http://purl.org/dc/elements/1.1/}"
NS_CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
RUTA_LOCAL = re.compile(rb"/Users/|/home/|[A-Za-z]:\\Users\\|file:///")
REFRESHED_BY = re.compile(rb'refreshedBy="[^"]+"')


def _git(*args: str) -> list[str]:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("no es un repositorio git")
    return [line for line in out.stdout.splitlines() if line]


def _versionados() -> list[Path]:
    return [Path(p) for p in _git("ls-files")]


def _contenidos(path: Path) -> list[tuple[str, bytes]]:
    """Bytes del archivo, o de cada miembro si es un contenedor zip de Office."""
    if path.suffix.lower() in EXTENSIONES_ZIP:
        with zipfile.ZipFile(path) as z:
            return [(f"{path}!{n}", z.read(n)) for n in z.namelist()]
    return [(str(path), path.read_bytes())]


def test_ningun_pbix_versionado() -> None:
    pbix = [p for p in _versionados() if p.suffix.lower() == ".pbix"]
    assert pbix == []


@pytest.mark.parametrize(
    "ruta",
    [
        "entregables/powerbi/Metalurgica Andina Calidad y Paros v1.pbix",
        "entregables/powerbi/Cruz_Demian_PQ_Produccion.pbix",
        "otro/dashboard_nuevo.pbix",
        "IIN2002_PQ_Dashboards-4D2L.docx",
        "entregables/IIN2002_PQ_Dashboards-4D2L.pdf",
    ],
)
def test_gitignore_cubre(ruta: str) -> None:
    assert _git("check-ignore", "--no-index", ruta) == [ruta]


def test_sin_urls_de_onedrive_en_archivos_versionados() -> None:
    hallazgos = []
    for path in _versionados():
        if path.resolve() == ESTE_ARCHIVO or not path.is_file():
            continue
        for nombre, datos in _contenidos(path):
            if URL_ONEDRIVE.search(datos):
                hallazgos.append(nombre)
    assert hallazgos == []


# ---------------------------------------------------------------------------
# Metadatos dentro de los .xlsx
# ---------------------------------------------------------------------------


def metadatos_xlsx(path: Path) -> list[tuple[str, str]]:
    """Metadatos personales de un .xlsx como (categoría, detalle).

    Independiente de scripts/limpiar_metadatos_xlsx.py a propósito: el test
    no debe confiar en el mismo código que arregla el problema.
    """
    hallazgos: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as z:
        if "docProps/core.xml" in z.namelist():
            core = ElementTree.fromstring(z.read("docProps/core.xml"))
            for etiqueta, nombre in ((NS_DC + "creator", "creator"),
                                     (NS_CP + "lastModifiedBy", "lastModifiedBy")):
                elemento = core.find(etiqueta)
                if elemento is not None and (elemento.text or "").strip():
                    hallazgos.append((nombre, f"{nombre}={elemento.text!r}"))
        for parte in z.namelist():
            datos = z.read(parte)
            if RUTA_LOCAL.search(datos):
                hallazgos.append(("ruta", f"{parte}: ruta local"))
            if REFRESHED_BY.search(datos):
                hallazgos.append(("refreshedBy", f"{parte}: refreshedBy"))
    return hallazgos


def _xlsx_versionados() -> list[Path]:
    return [p for p in _versionados() if p.suffix.lower() == ".xlsx"]


def _con(categorias: set[str]) -> list[str]:
    return [
        f"{p}: {detalle}"
        for p in _xlsx_versionados()
        for categoria, detalle in metadatos_xlsx(p)
        if categoria in categorias
    ]


def test_xlsx_sin_creator_ni_last_modified_by() -> None:
    assert _con({"creator", "lastModifiedBy"}) == []


def test_xlsx_sin_rutas_locales() -> None:
    assert _con({"ruta"}) == []


def test_xlsx_sin_refreshed_by() -> None:
    assert _con({"refreshedBy"}) == []


# --- el detector y el script se prueban contra un .xlsx sucio ---------------


def _xlsx_sucio(destino: Path) -> Path:
    """Un .xlsx con todos los metadatos que no deben publicarse."""
    wb = openpyxl.Workbook()
    wb.active["A1"] = "dato"
    wb.active["B1"] = "=1+1"
    wb.properties.creator = "Ana Pérez"
    wb.properties.lastModifiedBy = "Luis Gómez"
    wb.save(destino)
    sucio = destino.with_name("sucio.xlsx")
    absoluta = (b'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-'
                b'compatibility/2006"><mc:Choice Requires="x15"><x15ac:absPath url="/Users/ana/'
                b'Documentos/" xmlns:x15ac="http://schemas.microsoft.com/office/spreadsheetml/'
                b'2010/11/ac"/></mc:Choice></mc:AlternateContent>')
    with zipfile.ZipFile(destino) as zin, zipfile.ZipFile(sucio, "w", zipfile.ZIP_DEFLATED) as out:
        for item in zin.infolist():
            datos = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                datos = datos.replace(b"<bookViews>", absoluta + b"<bookViews>", 1)
            out.writestr(item, datos)
        out.writestr(
            "xl/pivotCache/pivotCacheDefinition1.xml",
            b'<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
            b'2006/main" refreshedBy="Ana Perez" refreshedDate="46000"/>',
        )
    return sucio


def _cargar_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("limpiar_metadatos_xlsx", SCRIPT_LIMPIEZA)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_detector_ve_los_metadatos_de_un_xlsx_sucio(tmp_path: Path) -> None:
    sucio = _xlsx_sucio(tmp_path / "base.xlsx")
    categorias = {categoria for categoria, _ in metadatos_xlsx(sucio)}
    assert categorias == {"creator", "lastModifiedBy", "ruta", "refreshedBy"}


def test_el_script_limpia_sin_tocar_los_datos(tmp_path: Path) -> None:
    sucio = _xlsx_sucio(tmp_path / "base.xlsx")
    limpiar: Callable[[Path], bool] = _cargar_script().limpiar
    assert limpiar(sucio) is True
    assert metadatos_xlsx(sucio) == []
    hoja = openpyxl.load_workbook(sucio).active
    assert (hoja["A1"].value, hoja["B1"].value) == ("dato", "=1+1")
    assert limpiar(sucio) is False  # idempotente: la segunda pasada no escribe


def test_el_script_en_modo_check_falla_con_un_xlsx_sucio(tmp_path: Path) -> None:
    sucio = _xlsx_sucio(tmp_path / "base.xlsx")
    main: Callable[[list[str]], int] = _cargar_script().main
    assert main(["--check", str(sucio)]) == 1
    assert main([str(sucio)]) == 0
    assert main(["--check", str(sucio)]) == 0
