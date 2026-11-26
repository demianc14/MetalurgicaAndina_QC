"""Las capturas de Power BI se ven en el README y no publican autores ajenos.

- Toda imagen que enlazan el README o docs/*.md existe en el repo.
- Están las 7 capturas de los informes D2, D3 y D4 (Power BI Service).
- Ninguna imagen ni PDF versionado (.jpg, .jpeg, .png, .pdf) trae en sus
  metadatos un autor o "modificado por" distinto de Demian. Vacío está bien.

Los .xlsx se revisan aparte en test_privacy.py (allí el autor debe ir vacío).
Solo biblioteca estándar: el detector lee EXIF, XMP, PNG y PDF a mano.
"""
from __future__ import annotations

import re
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
AUTOR_PERMITIDO = "demian"
SUFIJOS_MEDIOS = {".jpg", ".jpeg", ".png", ".pdf"}

CAPTURAS = [
    "D2-calidad-y-paros.jpg",
    "D3-1-resumen.jpg",
    "D3-2-produccion.jpg",
    "D4-1-resumen.jpg",
    "D4-2-produccion.jpg",
    "D4-3-calidad.jpg",
    "D4-4-paros-y-costos.jpg",
]

IMAGEN_MD = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")

# Etiquetas de autor / modificado por en XMP (JPEG, PNG y PDF las comparten).
XMP_AUTOR = re.compile(
    rb"<(dc:creator|pdf:Author|xmp:Author|xmpMM:LastModifiedBy|"
    rb"photoshop:AuthorsPosition|exif:Artist|tiff:Artist)\b[^>]*>(.*?)</\1>",
    re.S,
)
XMP_ATRIBUTO = re.compile(rb'(?:pdf:Author|tiff:Artist|exif:Artist)="([^"]*)"')
RDF_LI = re.compile(rb"<rdf:li[^>]*>(.*?)</rdf:li>", re.S)
PDF_AUTOR = re.compile(rb"/(Author|LastModifiedBy|ModifiedBy)\s*\(((?:\\.|[^\\)])*)\)")
PNG_CLAVES = {b"Author", b"Artist", b"Creator", b"Last Modified By"}
EXIF_ARTIST, EXIF_XPAUTHOR = 0x013B, 0x9C9D


# ---------------------------------------------------------------------------
# Detector de autores
# ---------------------------------------------------------------------------


def _exif_autores(tiff: bytes) -> list[str]:
    """Artist y XPAuthor del IFD0 de un bloque TIFF/EXIF."""
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return []
    orden = "<" if tiff[:2] == b"II" else ">"
    (ifd,) = struct.unpack(orden + "I", tiff[4:8])
    if ifd + 2 > len(tiff):
        return []
    (n,) = struct.unpack(orden + "H", tiff[ifd:ifd + 2])
    autores = []
    for i in range(n):
        base = ifd + 2 + 12 * i
        if base + 12 > len(tiff):
            break
        etiqueta, _tipo, cuenta = struct.unpack(orden + "HHI", tiff[base:base + 8])
        if etiqueta not in (EXIF_ARTIST, EXIF_XPAUTHOR):
            continue
        if cuenta <= 4:
            valor = tiff[base + 8:base + 8 + cuenta]
        else:
            (offset,) = struct.unpack(orden + "I", tiff[base + 8:base + 12])
            valor = tiff[offset:offset + cuenta]
        codificacion = "utf-16-le" if etiqueta == EXIF_XPAUTHOR else "latin-1"
        autores.append(valor.decode(codificacion, "replace").strip("\x00 "))
    return autores


def _jpeg_exif(datos: bytes) -> list[str]:
    autores: list[str] = []
    i = 2
    while i + 4 <= len(datos) and datos[i] == 0xFF:
        marca = datos[i + 1]
        if marca in (0xD9, 0xDA):  # fin de imagen / inicio de los píxeles
            break
        (largo,) = struct.unpack(">H", datos[i + 2:i + 4])
        segmento = datos[i + 4:i + 2 + largo]
        if marca == 0xE1 and segmento.startswith(b"Exif\x00\x00"):
            autores += _exif_autores(segmento[6:])
        i += 2 + largo
    return autores


def _png_textos(datos: bytes) -> list[str]:
    autores: list[str] = []
    i = 8
    while i + 8 <= len(datos):
        (largo,) = struct.unpack(">I", datos[i:i + 4])
        tipo, cuerpo = datos[i + 4:i + 8], datos[i + 8:i + 8 + largo]
        if tipo in (b"tEXt", b"zTXt", b"iTXt"):
            clave, _, resto = cuerpo.partition(b"\x00")
            if clave in PNG_CLAVES:
                if tipo == b"zTXt":
                    resto = zlib.decompress(resto[1:])
                elif tipo == b"iTXt":
                    comprimido = resto[:1] == b"\x01"
                    resto = resto[2:].split(b"\x00", 2)[-1]
                    resto = zlib.decompress(resto) if comprimido else resto
                codificacion = "utf-8" if tipo == b"iTXt" else "latin-1"
                autores.append(resto.decode(codificacion, "replace"))
        elif tipo == b"eXIf":
            autores += _exif_autores(cuerpo)
        i += 12 + largo
    return autores


def _xmp(datos: bytes) -> list[str]:
    autores = []
    for _etiqueta, contenido in XMP_AUTOR.findall(datos):
        items = RDF_LI.findall(contenido) or [contenido]
        autores += [x.decode("utf-8", "replace") for x in items]
    autores += [x.decode("utf-8", "replace") for x in XMP_ATRIBUTO.findall(datos)]
    return autores


def autores(path: Path) -> list[str]:
    """Autores y "modificado por" que un archivo declara en sus metadatos."""
    datos = path.read_bytes()
    sufijo = path.suffix.lower()
    encontrados = _xmp(datos)
    if sufijo in (".jpg", ".jpeg") and datos[:2] == b"\xff\xd8":
        encontrados += _jpeg_exif(datos)
    elif sufijo == ".png" and datos[:8] == b"\x89PNG\r\n\x1a\n":
        encontrados += _png_textos(datos)
    elif sufijo == ".pdf":
        encontrados += [v.decode("latin-1") for _, v in PDF_AUTOR.findall(datos)]
    return [a.strip() for a in encontrados if a.strip()]


def ajenos(path: Path) -> list[str]:
    return [a for a in autores(path) if AUTOR_PERMITIDO not in a.lower()]


# ---------------------------------------------------------------------------
# Tests sobre el repo
# ---------------------------------------------------------------------------


def _versionados() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True,
                             text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("no es un repositorio git")
    return [RAIZ / p for p in out.stdout.splitlines() if p]


def _markdown() -> list[Path]:
    return [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]


def test_toda_imagen_enlazada_existe() -> None:
    rotas = []
    for md in _markdown():
        for destino in IMAGEN_MD.findall(md.read_text(encoding="utf-8")):
            if destino.startswith(("http://", "https://")):
                continue
            if not (md.parent / destino).is_file():
                rotas.append(f"{md.relative_to(RAIZ)} -> {destino}")
    assert rotas == []


@pytest.mark.parametrize("nombre", CAPTURAS)
def test_captura_existe_y_esta_enlazada(nombre: str) -> None:
    assert (RAIZ / "docs" / "img" / nombre).is_file()
    texto = "\n".join(md.read_text(encoding="utf-8") for md in _markdown())
    assert f"img/{nombre}" in texto


def test_imagenes_y_pdf_sin_autores_ajenos() -> None:
    medios = [p for p in _versionados() if p.suffix.lower() in SUFIJOS_MEDIOS]
    hallazgos = {str(p.relative_to(RAIZ)): ajenos(p) for p in medios if ajenos(p)}
    assert hallazgos == {}


# ---------------------------------------------------------------------------
# El detector se prueba con archivos sucios fabricados aquí
# ---------------------------------------------------------------------------

AJENO = "Ana Pérez"


def _jpeg_con_artist(nombre: str) -> bytes:
    valor = nombre.encode("latin-1") + b"\x00"
    if len(valor) <= 4:  # TIFF guarda en línea los valores de hasta 4 bytes
        entrada = struct.pack("<HHI", EXIF_ARTIST, 2, len(valor)) + valor.ljust(4, b"\x00")
        valor = b""
    else:
        entrada = struct.pack("<HHII", EXIF_ARTIST, 2, len(valor), 26)
    ifd = struct.pack("<H", 1) + entrada
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd + b"\x00\x00\x00\x00" + valor
    app1 = b"Exif\x00\x00" + tiff
    return (b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
            + b"\xff\xda\x00\x02\xff\xd9")


def _png_con_author(nombre: str) -> bytes:
    cuerpo = b"Author\x00" + nombre.encode("latin-1")
    chunk = struct.pack(">I", len(cuerpo)) + b"tEXt" + cuerpo + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk


def _xmp_creator(nombre: str) -> bytes:
    return ("<x:xmpmeta><dc:creator><rdf:Seq><rdf:li>" + nombre
            + "</rdf:li></rdf:Seq></dc:creator></x:xmpmeta>").encode()


@pytest.mark.parametrize(
    ("nombre", "datos"),
    [
        ("exif.jpg", _jpeg_con_artist(AJENO)),
        ("xmp.jpg", b"\xff\xd8" + _xmp_creator(AJENO)),
        ("texto.png", _png_con_author(AJENO)),
        ("info.pdf", f"%PDF-1.4\n<< /Author ({AJENO}) >>".encode("latin-1")),
        ("modificado.pdf", f"%PDF-1.4\n<< /LastModifiedBy ({AJENO}) >>".encode("latin-1")),
        ("xmp.pdf", b"%PDF-1.4\n" + _xmp_creator(AJENO)),
    ],
)
def test_el_detector_ve_un_autor_ajeno(tmp_path: Path, nombre: str, datos: bytes) -> None:
    archivo = tmp_path / nombre
    archivo.write_bytes(datos)
    assert ajenos(archivo) == [AJENO]


@pytest.mark.parametrize("autor", ["Demian Cruz", ""])
def test_el_detector_acepta_a_demian_o_vacio(tmp_path: Path, autor: str) -> None:
    archivo = tmp_path / "ok.jpg"
    archivo.write_bytes(_jpeg_con_artist(autor))
    assert ajenos(archivo) == []
