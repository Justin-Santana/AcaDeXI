"""Utilidades de formato de HORA y FECHA para AcaDeXI.

Filosofía: los datos se siguen guardando SIEMPRE internamente en 24 horas
("HH:MM") y en fecha ISO ("YYYY-MM-DD") en la base de datos; nada de este
módulo cambia eso. Lo único que cambia es cómo se *muestran* al usuario,
según la preferencia elegida en Configuración › Apariencia
(main_window.formato_hora / main_window.formato_fecha).

Así, aunque un docente elija "12 horas" y un administrador elija "24 horas",
ambos siguen leyendo/escribiendo la misma base de datos sin conflicto: el
formato es una preferencia puramente de presentación, por dispositivo.
"""
from datetime import datetime

FORMATO_HORA_DEFECTO = "24h"
FORMATO_FECHA_DEFECTO = "dmy"

FORMATOS_HORA = {
    "24h": "24 horas (14:30)",
    "12h": "12 horas (2:30 p. m.)",
}

FORMATOS_FECHA = {
    "dmy": "DD/MM/AAAA (09/08/2026)",
    "mdy": "MM/DD/AAAA (08/09/2026)",
    "ymd": "AAAA-MM-DD (2026-08-09)",
    "dmy_texto": "Texto largo (9 de agosto de 2026)",
}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


# ============================================================
# RESOLUCIÓN DE LA PREFERENCIA ACTIVA
# ============================================================
def _resolver_main_window(referencia):
    """Acepta directamente un main_window, o cualquier widget que tenga un
    atributo .main_window (o una cadena de ellos), y devuelve el main_window
    real (o None si no se pudo determinar)."""
    if referencia is None:
        return None
    if hasattr(referencia, "formato_hora") or hasattr(referencia, "formato_fecha"):
        return referencia
    vistos = set()
    actual = referencia
    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))
        siguiente = getattr(actual, "main_window", None)
        if siguiente is None:
            return None
        actual = siguiente
    return actual


def obtener_formato_hora(main_window=None):
    mw = _resolver_main_window(main_window)
    valor = getattr(mw, "formato_hora", FORMATO_HORA_DEFECTO) if mw else FORMATO_HORA_DEFECTO
    return valor if valor in FORMATOS_HORA else FORMATO_HORA_DEFECTO


def obtener_formato_fecha(main_window=None):
    mw = _resolver_main_window(main_window)
    valor = getattr(mw, "formato_fecha", FORMATO_FECHA_DEFECTO) if mw else FORMATO_FECHA_DEFECTO
    return valor if valor in FORMATOS_FECHA else FORMATO_FECHA_DEFECTO


# ============================================================
# FORMATEO DE HORA (entrada siempre "HH:MM" en 24h)
# ============================================================
def formatear_hora(hora_str, main_window=None):
    if not hora_str:
        return ""
    try:
        t = datetime.strptime(str(hora_str).strip()[:5], "%H:%M")
    except ValueError:
        return hora_str
    if obtener_formato_hora(main_window) == "12h":
        hora12 = t.hour % 12 or 12
        sufijo = "a. m." if t.hour < 12 else "p. m."
        return f"{hora12}:{t.minute:02d} {sufijo}"
    return f"{t.hour:02d}:{t.minute:02d}"


def formatear_rango_horas(hora_inicio, hora_fin, main_window=None, separador=" - "):
    return f"{formatear_hora(hora_inicio, main_window)}{separador}{formatear_hora(hora_fin, main_window)}"


# ============================================================
# FORMATEO DE FECHA (entrada siempre "YYYY-MM-DD", con o sin hora pegada)
# ============================================================
def formatear_fecha(fecha_str, main_window=None):
    if not fecha_str:
        return ""
    try:
        d = datetime.strptime(str(fecha_str).strip()[:10], "%Y-%m-%d")
    except ValueError:
        return fecha_str
    formato = obtener_formato_fecha(main_window)
    if formato == "mdy":
        return f"{d.month:02d}/{d.day:02d}/{d.year:04d}"
    if formato == "ymd":
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    if formato == "dmy_texto":
        return f"{d.day} de {MESES[d.month - 1]} de {d.year}"
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


def formatear_fecha_hora(fecha_hora_str, main_window=None, separador=" · "):
    """Para timestamps tipo 'YYYY-MM-DD HH:MM:SS' guardados por auditoría/registros."""
    if not fecha_hora_str:
        return ""
    texto = str(fecha_hora_str).strip()
    parte_fecha, parte_hora = (texto.split(" ", 1) + [""])[:2]
    fecha_fmt = formatear_fecha(parte_fecha, main_window)
    hora_fmt = formatear_hora(parte_hora[:5], main_window) if parte_hora else ""
    return f"{fecha_fmt}{separador}{hora_fmt}" if hora_fmt else fecha_fmt


# ============================================================
# FORMATOS DE VISUALIZACIÓN PARA WIDGETS QT (QTimeEdit / QDateEdit)
# Estos NO afectan el valor interno guardado (.time()/.date() siguen
# devolviendo el mismo QTime/QDate); solo cambian cómo se ve mientras el
# usuario lo edita.
# ============================================================
def qtime_display_format(main_window=None):
    return "hh:mm AP" if obtener_formato_hora(main_window) == "12h" else "HH:mm"


def qdate_display_format(main_window=None):
    formato = obtener_formato_fecha(main_window)
    if formato == "mdy":
        return "MM/dd/yyyy"
    if formato == "ymd":
        return "yyyy-MM-dd"
    return "dd/MM/yyyy"


def aplicar_formato_widget_hora(time_edit, main_window=None):
    """Aplica el formato de hora preferido a un QTimeEdit."""
    try:
        time_edit.setDisplayFormat(qtime_display_format(main_window))
    except Exception:
        pass


def aplicar_formato_widget_fecha(date_edit, main_window=None):
    """Aplica el formato de fecha preferido a un QDateEdit."""
    try:
        date_edit.setDisplayFormat(qdate_display_format(main_window))
    except Exception:
        pass
