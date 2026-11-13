"""Privacidad del repo: lo que no debe publicarse no está versionado.

- Ningún .pbix versionado: guardan por dentro la URL de OneDrive
  institucional (con el usuario de la universidad).
- .gitignore ignora los .pbix y la guía del profesor.
- Ningún archivo versionado (texto, o el XML dentro de un .xlsx/.docx)
  contiene una URL de SharePoint/OneDrive.

Usa `git ls-files`: si el directorio no es un repo git, los tests se saltan.
"""
from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

import pytest

ESTE_ARCHIVO = Path(__file__).resolve()
URL_ONEDRIVE = re.compile(rb"https?://[^\s\"'<>]*(sharepoint\.com|onedrive\.live\.com|1drv\.ms)")
EXTENSIONES_ZIP = {".xlsx", ".xlsm", ".docx", ".pptx"}


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
