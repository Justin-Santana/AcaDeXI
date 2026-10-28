#Formato de hora y fecha para toda la app. Los datos se guardan siempre igual: en la base de datos
#la hora va en 24 horas ("HH:MM") y la fecha en ISO ("YYYY-MM-DD"). Lo único que cambia acá es cómo se
#muestran, según lo que el usuario eligió en Configuración > Apariencia. Así un docente puede ver 12
#horas y el administrador 24 horas, y los dos leen la misma base.
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


# -----------------------------------------
# qué formato eligió el usuario
# -----------------------------------------
#Las preferencias las guarda la ventana principal. Recibe la ventana o cualquier widget que cuelgue de
#ella (que la tiene en su atributo main_window) y devuelve la ventana, o None si no la encuentra.
def _ventana_con_formato(referencia):

    #se sube como máximo cinco niveles, de sobra para llegar a la ventana principal
    for _ in range(5):

        if referencia is None:
            return None

        if hasattr(referencia, "formato_hora") or hasattr(referencia, "formato_fecha"):
            return referencia

        referencia= getattr(referencia, "main_window", None)

    return None


def obtener_formato_hora(main_window=None):

    ventana= _ventana_con_formato(main_window)
    formato= getattr(ventana, "formato_hora", FORMATO_HORA_DEFECTO)

    return formato if formato in FORMATOS_HORA else FORMATO_HORA_DEFECTO


def obtener_formato_fecha(main_window=None):

    ventana= _ventana_con_formato(main_window)
    formato= getattr(ventana, "formato_fecha", FORMATO_FECHA_DEFECTO)

    return formato if formato in FORMATOS_FECHA else FORMATO_FECHA_DEFECTO


# -----------------------------------------
# convertir para mostrar
# -----------------------------------------
#Pasa una hora guardada en 24 horas ("HH:MM") al formato que eligió el usuario. Si el texto no es
#una hora, se devuelve tal cual.
def formatear_hora(texto_hora, main_window=None):

    if not texto_hora:
        return ""

    try:

        hora= datetime.strptime(str(texto_hora).strip()[:5], "%H:%M")

    except ValueError:
        return texto_hora

    if obtener_formato_hora(main_window) == "12h":
        hora_en_12= hora.hour % 12 or 12
        sufijo= "a. m." if hora.hour < 12 else "p. m."
        return f"{hora_en_12}:{hora.minute:02d} {sufijo}"

    return f"{hora.hour:02d}:{hora.minute:02d}"


#Para los horarios de clase: "08:00 - 09:30".
def formatear_rango_horas(hora_inicio, hora_fin, main_window=None, separador=" - "):

    return f"{formatear_hora(hora_inicio, main_window)}{separador}{formatear_hora(hora_fin, main_window)}"


#Pasa una fecha guardada en ISO ("YYYY-MM-DD", con o sin hora pegada) al formato elegido. Si el texto
#no es una fecha, se devuelve tal cual.
def formatear_fecha(texto_fecha, main_window=None):

    if not texto_fecha:
        return ""

    try:

        fecha= datetime.strptime(str(texto_fecha).strip()[:10], "%Y-%m-%d")

    except ValueError:
        return texto_fecha

    formato= obtener_formato_fecha(main_window)

    if formato == "mdy":
        return f"{fecha.month:02d}/{fecha.day:02d}/{fecha.year:04d}"

    if formato == "ymd":
        return f"{fecha.year:04d}-{fecha.month:02d}-{fecha.day:02d}"

    if formato == "dmy_texto":
        return f"{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"

    return f"{fecha.day:02d}/{fecha.month:02d}/{fecha.year:04d}"


#Para las marcas de tiempo de auditoría, que vienen como "YYYY-MM-DD HH:MM:SS".
def formatear_fecha_hora(texto_fecha_hora, main_window=None, separador=" · "):

    if not texto_fecha_hora:
        return ""

    texto= str(texto_fecha_hora).strip()
    parte_fecha, _, parte_hora= texto.partition(" ")
    fecha= formatear_fecha(parte_fecha, main_window)

    if not parte_hora:
        return fecha

    return f"{fecha}{separador}{formatear_hora(parte_hora[:5], main_window)}"


# -----------------------------------------
# widgets de Qt (QTimeEdit y QDateEdit)
# -----------------------------------------
#Cambian solo cómo se ve el valor mientras el usuario lo edita, no el valor guardado.
def qtime_display_format(main_window=None):

    return "hh:mm AP" if obtener_formato_hora(main_window) == "12h" else "HH:mm"


def qdate_display_format(main_window=None):

    formato= obtener_formato_fecha(main_window)

    if formato == "mdy":
        return "MM/dd/yyyy"

    if formato == "ymd":
        return "yyyy-MM-dd"

    return "dd/MM/yyyy"


#Si el widget no existe o no acepta el formato, se deja como está: no vale la pena romper la pantalla.
def aplicar_formato_widget_hora(in_hora, main_window=None):

    try:

        in_hora.setDisplayFormat(qtime_display_format(main_window))

    except Exception:
        pass


def aplicar_formato_widget_fecha(in_fecha, main_window=None):

    try:

        in_fecha.setDisplayFormat(qdate_display_format(main_window))

    except Exception:
        pass
