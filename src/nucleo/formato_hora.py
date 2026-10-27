#Formato de hora y fecha para toda la app. Los datos se guardan siempre igual, en la base de
#datos la hora va en 24 horas ("HH:MM") y la fecha en ISO ("YYYY-MM-DD"); lo único que cambia acá
#es cómo se muestran, según lo que el usuario eligió en Configuración › Apariencia. Así un
#docente puede tener 12 horas y el administrador 24 horas y los dos siguen leyendo la misma base.
from datetime import datetime

FORMATO_HORA_DEFECTO= "24h"
FORMATO_FECHA_DEFECTO= "dmy"

FORMATOS_HORA= {
    "24h": "24 horas (14:30)",
    "12h": "12 horas (2:30 p. m.)",
}

FORMATOS_FECHA= {
    "dmy": "DD/MM/AAAA (09/08/2026)",
    "mdy": "MM/DD/AAAA (08/09/2026)",
    "ymd": "AAAA-MM-DD (2026-08-09)",
    "dmy_texto": "Texto largo (9 de agosto de 2026)",
}

MESES= ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre"]


#Acepta la ventana principal o cualquier widget que cuelgue de ella y devuelve la ventana, que es
#la que guarda las preferencias. Devuelve None si no la encuentra.
def _ventana_de(referencia):
    if referencia is None:
        return None
    if hasattr(referencia, "formato_hora") or hasattr(referencia, "formato_fecha"):
        return referencia
    vistas= set()
    actual= referencia
    while actual is not None and id(actual) not in vistas:
        vistas.add(id(actual))
        actual= getattr(actual, "main_window", None)
        if actual is not None and (hasattr(actual, "formato_hora") or hasattr(actual, "formato_fecha")):
            return actual
    return None


def obtener_formato_hora(main_window=None):
    ventana= _ventana_de(main_window)
    valor= getattr(ventana, "formato_hora", FORMATO_HORA_DEFECTO) if ventana else FORMATO_HORA_DEFECTO
    return valor if valor in FORMATOS_HORA else FORMATO_HORA_DEFECTO


def obtener_formato_fecha(main_window=None):
    ventana= _ventana_de(main_window)
    valor= getattr(ventana, "formato_fecha", FORMATO_FECHA_DEFECTO) if ventana else FORMATO_FECHA_DEFECTO
    return valor if valor in FORMATOS_FECHA else FORMATO_FECHA_DEFECTO


#Pasa una hora guardada en 24 horas ("HH:MM") al formato que eligió el usuario.
def formatear_hora(hora_str, main_window=None):
    if not hora_str:
        return ""
    try:
        hora= datetime.strptime(str(hora_str).strip()[:5], "%H:%M")
    except ValueError:
        return hora_str
    if obtener_formato_hora(main_window) == "12h":
        hora12= hora.hour % 12 or 12
        sufijo= "a. m." if hora.hour < 12 else "p. m."
        return f"{hora12}:{hora.minute:02d} {sufijo}"
    return f"{hora.hour:02d}:{hora.minute:02d}"


#Para horarios de clase: "08:00 - 09:30".
def formatear_rango_horas(hora_inicio, hora_fin, main_window=None, separador=" - "):
    return f"{formatear_hora(hora_inicio, main_window)}{separador}{formatear_hora(hora_fin, main_window)}"


#Pasa una fecha guardada en ISO ("YYYY-MM-DD", con o sin hora pegada) al formato elegido.
def formatear_fecha(fecha_str, main_window=None):
    if not fecha_str:
        return ""
    try:
        fecha= datetime.strptime(str(fecha_str).strip()[:10], "%Y-%m-%d")
    except ValueError:
        return fecha_str
    formato= obtener_formato_fecha(main_window)
    if formato == "mdy":
        return f"{fecha.month:02d}/{fecha.day:02d}/{fecha.year:04d}"
    if formato == "ymd":
        return f"{fecha.year:04d}-{fecha.month:02d}-{fecha.day:02d}"
    if formato == "dmy_texto":
        return f"{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"
    return f"{fecha.day:02d}/{fecha.month:02d}/{fecha.year:04d}"


#Para las marcas de tiempo de auditoría, que vienen como "YYYY-MM-DD HH:MM:SS".
def formatear_fecha_hora(fecha_hora_str, main_window=None, separador=" · "):
    if not fecha_hora_str:
        return ""
    texto= str(fecha_hora_str).strip()
    parte_fecha, _, parte_hora= texto.partition(" ")
    fecha= formatear_fecha(parte_fecha, main_window)
    if not parte_hora:
        return fecha
    return f"{fecha}{separador}{formatear_hora(parte_hora[:5], main_window)}"


#Formatos de los widgets de Qt (QTimeEdit/QDateEdit). No cambian el valor guardado, solo cómo se
#ve mientras el usuario lo edita.
def qtime_display_format(main_window=None):
    return "hh:mm AP" if obtener_formato_hora(main_window) == "12h" else "HH:mm"


def qdate_display_format(main_window=None):
    formato= obtener_formato_fecha(main_window)
    if formato == "mdy":
        return "MM/dd/yyyy"
    if formato == "ymd":
        return "yyyy-MM-dd"
    return "dd/MM/yyyy"


def aplicar_formato_widget_hora(time_edit, main_window=None):
    try:
        time_edit.setDisplayFormat(qtime_display_format(main_window))
    except Exception:
        pass


def aplicar_formato_widget_fecha(date_edit, main_window=None):
    try:
        date_edit.setDisplayFormat(qdate_display_format(main_window))
    except Exception:
        pass
