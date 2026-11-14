#!/usr/bin/env python3
"""Limpia los metadatos personales de archivos .xlsx antes de publicarlos.

Un .xlsx es un zip de XML y guarda, además de los datos, quién lo creó y
dónde estaba en el disco. Este script vacía, sin tocar celdas, fórmulas,
tablas ni tablas dinámicas:

  - docProps/core.xml:  creator y lastModifiedBy (se dejan vacíos)
  - docProps/app.xml:   Company y Manager
  - xl/workbook.xml:    la ruta local de la carpeta (x15ac:absPath)
  - xl/externalLinks:   rutas locales de vínculos a otros libros
                        (el vínculo se conserva, apuntando a "libro_externo.xlsx")
  - xl/pivotCache:      refreshedBy (quién actualizó la tabla dinámica)

Es idempotente: sobre un archivo ya limpio no escribe nada.

Uso:
  python3 scripts/limpiar_metadatos_xlsx.py            # limpia todos los .xlsx versionados
  python3 scripts/limpiar_metadatos_xlsx.py a.xlsx b.xlsx
  python3 scripts/limpiar_metadatos_xlsx.py --check    # no escribe; sale con 1 si queda algo

Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

EXTERNO_NEUTRO = "libro_externo.xlsx"

_RUTA_LOCAL = r"(?:/Users/|/home/|file:///|[A-Za-z]:[\\/])"
# Lo que no debe quedar en ninguna parte del archivo.
RESIDUOS = {
    "ruta local": re.compile(rb"/Users/|/home/|[A-Za-z]:\\Users\\|file:///"),
    "x15ac:absPath": re.compile(rb"absPath"),
    "refreshedBy": re.compile(rb'refreshedBy="[^"]+"'),
    "creator": re.compile(rb"<dc:creator[^>]*>[^<]+</dc:creator>"),
    "lastModifiedBy": re.compile(rb"<cp:lastModifiedBy[^>]*>[^<]+</cp:lastModifiedBy>"),
    "Company/Manager": re.compile(rb"<(Company|Manager)>[^<]+</(Company|Manager)>"),
}


def _limpiar_parte(nombre: str, xml: str) -> str:
    if nombre == "docProps/core.xml":
        xml = re.sub(r"(<dc:creator[^>]*>)[^<]*(</dc:creator>)", r"\1\2", xml)
        xml = re.sub(r"(<cp:lastModifiedBy[^>]*>)[^<]*(</cp:lastModifiedBy>)", r"\1\2", xml)
    elif nombre == "docProps/app.xml":
        xml = re.sub(r"(<Company>)[^<]*(</Company>)", r"\1\2", xml)
        xml = re.sub(r"(<Manager>)[^<]*(</Manager>)", r"\1\2", xml)
    elif nombre == "xl/workbook.xml":
        xml = re.sub(
            r'<mc:AlternateContent[^>]*>\s*<mc:Choice Requires="x15">\s*'
            r"<x15ac:absPath[^>]*/>\s*</mc:Choice>\s*</mc:AlternateContent>",
            "",
            xml,
        )
    elif nombre.endswith(".rels"):
        xml = re.sub(rf'(Target=")({_RUTA_LOCAL}[^"]*)(")', rf"\g<1>{EXTERNO_NEUTRO}\g<3>", xml)
    elif re.fullmatch(r"xl/pivotCache/pivotCacheDefinition\d+\.xml", nombre):
        xml = re.sub(r'\s+refreshedBy="[^"]*"', "", xml)
    return xml


def problemas(path: Path) -> list[str]:
    """Qué metadatos personales quedan en el archivo (lista vacía = limpio)."""
    hallazgos = []
    with zipfile.ZipFile(path) as z:
        for nombre in z.namelist():
            datos = z.read(nombre)
            for etiqueta, patron in RESIDUOS.items():
                if patron.search(datos):
                    hallazgos.append(f"{nombre}: {etiqueta}")
    return hallazgos


def limpiar(path: Path) -> bool:
    """Reescribe `path` sin metadatos personales. True si cambió algo."""
    with zipfile.ZipFile(path) as z:
        items = z.infolist()
        originales = {i.filename: z.read(i.filename) for i in items}
    nuevos: dict[str, bytes] = {}
    for nombre, datos in originales.items():
        if not nombre.endswith((".xml", ".rels")):
            nuevos[nombre] = datos
            continue
        limpio = _limpiar_parte(nombre, datos.decode("utf-8")).encode("utf-8")
        if limpio != datos:
            ElementTree.fromstring(limpio)  # si el XML quedó mal formado, aborta antes de escribir
        nuevos[nombre] = limpio
    if nuevos == originales:
        return False
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w") as out:
            for item in items:  # mismo orden, fechas y compresión que el original
                out.writestr(item, nuevos[item.filename])
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return True


def _versionados() -> list[Path]:
    salida = subprocess.run(
        ["git", "ls-files", "*.xlsx"], capture_output=True, text=True, check=True
    ).stdout
    return [Path(p) for p in salida.splitlines() if p]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("archivos", nargs="*", type=Path, help="por defecto, los .xlsx versionados")
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si queda algo")
    args = ap.parse_args(argv)
    archivos = args.archivos or _versionados()
    if not archivos:
        print("No hay archivos .xlsx.")
        return 0
    sucio = False
    for path in archivos:
        if not args.check and limpiar(path):
            print(f"limpiado: {path}")
        restos = problemas(path)
        if restos:
            sucio = True
            print(f"CON METADATOS: {path}")
            for r in restos:
                print(f"  - {r}")
        elif args.check:
            print(f"limpio: {path}")
    return 1 if sucio else 0


if __name__ == "__main__":
    sys.exit(main())
