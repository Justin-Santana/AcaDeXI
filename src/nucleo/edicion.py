"""Estado de edicion actual de AcaDeXI.

Extraido de ``main.py`` (capa de edicion centralizada) para que modulos como
``permisos`` puedan consultar la edicion sin depender del lanzador principal.

Resuelve la edicion una sola vez al arranque (cacheado): ``full`` por defecto,
o ``docentes`` / ``single_teacher`` / ``side_stepper`` segun la clave de
desinstalacion registrada en Windows.
"""
from __future__ import annotations

import sys

# Cache resuelto una sola vez al arranque.
_EDICION_ACTUAL_CACHE = None

# (subclave del registro, nombre de edicion)
_CLAVES_REGISTRO_POR_EDICION = (
    ("AcaDeXI_Docentes", "docentes"),
    ("AcaDeXI_SingleTeacher", "single_teacher"),
    ("AcaDeXI_SideStepper", "side_stepper"),
)


def _detectar_edicion_desde_registro() -> str:
    if sys.platform != "win32":
        return "full"
    try:
        import winreg
    except Exception:
        return "full"
    for subclave, edicion in _CLAVES_REGISTRO_POR_EDICION:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{subclave}",
            ):
                return edicion
        except OSError:
            continue
        except Exception:
            continue
    return "full"


def edicion_actual() -> str:
    """Devuelve la edicion de esta copia instalada de AcaDeXI.

    ``full`` si no aplica ninguna clave (o en plataformas no Windows/errores de
    registro). Resuelto una sola vez al arranque (cacheado).
    """
    global _EDICION_ACTUAL_CACHE
    if _EDICION_ACTUAL_CACHE is not None:
        return _EDICION_ACTUAL_CACHE
    _EDICION_ACTUAL_CACHE = _detectar_edicion_desde_registro()
    return _EDICION_ACTUAL_CACHE


def instalado_con_setup_docentes() -> bool:
    """Wrapper retrocompatible: todo el codigo existente que ya llama a esta
    funcion sigue funcionando sin cambios. NUNCA vuelvas a leer el registro
    fuera de edicion_actual()."""
    return edicion_actual() == "docentes"
