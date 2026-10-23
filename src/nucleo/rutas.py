"""Resolución centralizada de rutas de AcaDeXI.

Dos conceptos distintos (no mezclar):

* ``get_app_root_dir()``: dónde vive la instalación. Empaquetado → carpeta del
  .exe (ahí el administrador coloca ``AcaDeXI_Docentes_Setup.exe``, ver
  instalador.py); desarrollo → raíz del repositorio.
* ``get_bundle_dir()`` / ``get_iconos_dir()`` / ``buscar_dato()``: recursos que
  PyInstaller empaqueta (``_internal`` = ``sys._MEIPASS``). En desarrollo salen
  de ``src/assets/``, ``docs/`` y ``servidor/``. El diseño del bundle no cambia, así que los
  .iss siguen funcionando.

Este módulo no importa de otros paquetes de ``src``. Todas las funciones
devuelven ``str`` (compatibles con ``os.path``).
"""
from __future__ import annotations

import os
import sys

_RAIZ_DEV = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def esta_empaquetado() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_root_dir() -> str:
    if esta_empaquetado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _RAIZ_DEV


def get_bundle_dir() -> str:
    if esta_empaquetado():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.join(get_app_root_dir(), "_internal")
    return os.path.join(_RAIZ_DEV, "src", "assets")


def get_iconos_dir() -> str:
    return os.path.join(get_bundle_dir(), "iconos")


def _carpetas_datos():
    if esta_empaquetado():
        exe = get_app_root_dir()
        return [get_bundle_dir(), os.path.join(exe, "_internal"), exe]
    r = _RAIZ_DEV
    return [os.path.join(r, "servidor"), os.path.join(r, "docs"),
            os.path.join(r, "src", "assets"), r]


def buscar_dato(nombre: str) -> str:
    """Ruta de un archivo suelto empaquetado (guía PDF, servidor, etc.) o ''."""
    for c in _carpetas_datos():
        p = os.path.join(c, nombre)
        if os.path.isfile(p):
            return p
    return ""
