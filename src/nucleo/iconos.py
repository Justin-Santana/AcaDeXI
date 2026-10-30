import io
import os
import re
import sys
import unicodedata
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtGui import QIcon, QPixmap
from src.nucleo.rutas import obtener_carpeta_iconos


# -----------------------------------------
# bus de eventos de exito
# -----------------------------------------
CARPETA_ICONOS= obtener_carpeta_iconos()

#para cada módulo, los nombres de archivo que se aceptan como su icono, en orden de preferencia.
#un módulo con lista vacía no tiene icono propio todavía y sigue mostrando su emoji de respaldo.
ALIAS_ICONOS_SIDEBAR= {
    "Dashboard": ["dashboard"],
    "Estudiantes": ["estudiantes"],
    "Mis Estudiantes": ["estudiantes"],
    "Profesores": ["profesores", "prefesoresico", "profesoresico"],
    "Personal": ["personal"],
    "Materias": ["mismaterias", "materias"],
    "Mis Materias": ["mismaterias", "materias"],
    "Materiales": ["materiales"],
    "Asistencia": ["asistencia"],
    "Calificaciones": ["calificaciones"],
    "Calificaciones Técnicas": ["calificacionestecnicas"],
    "Politécnico": ["politecnico"],
    "Universidad": ["universidad"],
    "Banco de Tareas": ["bancodetareas"],
    "Secuencias Didácticas": ["secuencias", "secuenciasdidacticas"],
    "Horario": ["horario"],
    "Calendario": ["calendaria", "calendario"],
    "Observaciones": ["observaciones"],
    "Psicología": ["psicologia"],
    "Reportes": ["reportes"],
    "Copias de Seguridad": ["backup", "copiasdeseguridad"],
    "Sincronización": ["sincronizacion"],
    "Configuración": ["configuracion"],
}

_EXTENSIONES_IMAGEN= (".png", ".jpg", ".jpeg", ".bmp", ".ico")

_indice_sidebar_icons= None

_cache_pixmap_sidebar= {}

# -----------------------------------------
# iconos de la app
# -----------------------------------------
ICONO_APP= "schoolsys.ico"

LOGO_APP_GRANDE= "AcaDeXI_logo.png"       #el escudo grande, no el .ico de la ventana

ICONO_OK= "correctico.ico"

ICONO_ERROR= "eroico.ico"

ICONO_WARNING= "warningico.ico"

ICONO_LOGIN= "loginico.ico"

ICONO_DETALLE= "detalleico.ico"

ICONO_SETTING= "settingico.ico"

ICONO_TABLA= "tableico.ico"

ICONO_ASISTENTE= "asistenteico.ico"      #asistente de sincronización

ICONO_BUSQUEDA= "busquedaico.ico"        #búsqueda global

ICONO_CARGA= "cargaico.ico"              #diálogos que procesan o recalculan un archivo

ICONO_COLOR= "colorico.ico"              #selección de color

ICONO_RECORTE= "imagenrecortico.ico"     #foto: ver y recortar

ICONO_INFO= "infoico.ico"                #mensajes informativos

ICONO_SETUP= "setupico.ico"              #asistente de configuración inicial

ICONO_TUTORIAL= "tutorial.ico"           #tutorial guiado

ICONO_DOCUMENTO= "documentico.ico"       #documentos y paquetes .acdx o pdf

ICONO_FILTRO= "filtradoico.ico"          #ventanita de filtros

_cache= {}

_cache_pixmap_logo_app= {}

# -----------------------------------------
# carpetas donde puede estar la carpeta "iconos"
# -----------------------------------------
#en desarrollo es una sola; empaquetado con PyInstaller (--onedir) hay que probar también la
#carpeta _internal que queda junto al .exe, sin importar en qué disco la instaló Inno Setup.
def _carpetas_candidatas_iconos():

    candidatas= [CARPETA_ICONOS]

    if getattr(sys, "frozen", False):

        dentro_del_exe= getattr(sys, "_MEIPASS", None)
        if dentro_del_exe:
            candidatas.append(os.path.join(dentro_del_exe, "iconos"))
            candidatas.append(dentro_del_exe)

        carpeta_exe= os.path.dirname(os.path.abspath(sys.executable))
        candidatas.append(os.path.join(carpeta_exe, "_internal", "iconos"))
        candidatas.append(os.path.join(carpeta_exe, "_internal"))
        candidatas.append(os.path.join(carpeta_exe, "iconos"))
        candidatas.append(carpeta_exe)

    #sin carpetas repetidas y sin perder el orden de prioridad
    vistas= set()
    resultado= []
    for carpeta in candidatas:

        if carpeta and carpeta not in vistas:
            vistas.add(carpeta)
            resultado.append(carpeta)

    return resultado


# -----------------------------------------
# iconos de la barra lateral
# -----------------------------------------
#viven en iconos/sidebar_icons/*.png y se resuelven con las mismas carpetas de arriba, así que
#si "iconos" ya va empaquetada, la subcarpeta viaja sola sin tocar el instalador.
def _carpetas_candidatas_sidebar_icons():

    candidatas= [os.path.join(carpeta, "sidebar_icons") for carpeta in _carpetas_candidatas_iconos()]

    vistas= set()
    resultado= []
    for carpeta in candidatas:

        if carpeta not in vistas:
            vistas.add(carpeta)
            resultado.append(carpeta)

    return resultado


#"Mis Materias.png" y "Calificaciones Técnicas" terminan en "mismaterias" y
#"calificacionestecnicas": solo letras y números en minúscula, sin acentos, para poder emparejar
#el nombre del archivo con el nombre del módulo sin depender de espacios ni tildes.
def _normalizar_clave(texto):

    sin_acentos= unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

    return re.sub(r"[^a-z0-9]", "", sin_acentos.lower())


#escanea TODAS las carpetas candidatas, sin detenerse en la primera que exista, y arma
#{clave: ruta}. Si un archivo aparece en dos carpetas gana la primera, que es la de más prioridad.
def _indice_archivos_sidebar_icons():

    global _indice_sidebar_icons

    if _indice_sidebar_icons is not None:
        return _indice_sidebar_icons

    indice= {}
    for carpeta in _carpetas_candidatas_sidebar_icons():

        if not os.path.isdir(carpeta):
            continue

        try:

            nombres= os.listdir(carpeta)

        except OSError:
            continue

        for nombre_archivo in nombres:

            base, extension= os.path.splitext(nombre_archivo)
            if extension.lower() not in _EXTENSIONES_IMAGEN:
                continue

            clave= _normalizar_clave(base)
            if clave not in indice:
                indice[clave]= os.path.join(carpeta, nombre_archivo)

    _indice_sidebar_icons= indice

    return indice


#ruta del archivo de icono de un módulo, o None si ese módulo todavía no tiene icono propio.
def ruta_icono_sidebar(nombre_modulo):

    claves= ALIAS_ICONOS_SIDEBAR.get(nombre_modulo) or []

    if not claves:
        return None

    indice= _indice_archivos_sidebar_icons()
    for clave in claves:

        ruta= indice.get(clave)
        if ruta:
            return ruta

    return None


# -----------------------------------------
# recortar el aire transparente del png
# -----------------------------------------
#cada icono viene con una cantidad distinta de margen alrededor del dibujo, así que al escalarlos
#a la misma caja unos se ven grandes y otros diminutos. Recortando primero al contenido real y
#escalando después, todos ocupan la misma proporción del chip.
def _recortar_margen_transparente(ruta):

    try:

        from PIL import Image

        with Image.open(ruta) as imagen:

            imagen= imagen.convert("RGBA")
            caja= imagen.getbbox()

            if not caja:
                return None

            recortada= imagen.crop(caja)
            buffer= io.BytesIO()
            recortada.save(buffer, format="PNG")

            return buffer.getvalue()

    except Exception:
        return None                   #sin Pillow o si el recorte falla, se usa el png tal cual


#pixmap del icono del módulo, ya recortado y escalado, o None si no hay icono disponible.
def pixmap_icono_sidebar(nombre_modulo, tamano=26):

    ruta= ruta_icono_sidebar(nombre_modulo)

    if not ruta:
        return None

    clave_cache= (ruta, tamano)
    if clave_cache in _cache_pixmap_sidebar:
        return _cache_pixmap_sidebar[clave_cache]

    datos_recortados= _recortar_margen_transparente(ruta)
    pixmap= QPixmap()
    cargado= pixmap.loadFromData(datos_recortados) if datos_recortados else False

    if not cargado:
        pixmap= QPixmap(ruta)

    if pixmap.isNull():
        _cache_pixmap_sidebar[clave_cache]= None
        return None

    pixmap= pixmap.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    _cache_pixmap_sidebar[clave_cache]= pixmap

    return pixmap


#el mismo icono de la fila del módulo en la barra lateral, pero a tamaño de emoji, para listas
#como el Buscador Global. Si no hay png, se usa el icono vectorial de iconos_auto.py; si tampoco,
#un QIcon vacío y quien llama decide qué hacer.
def icono_qicon_modulo(nombre_modulo, tamano=18):

    pixmap= pixmap_icono_sidebar(nombre_modulo, tamano) if nombre_modulo else None

    if pixmap is not None:
        return QIcon(pixmap)

    if nombre_modulo:

        from src.nucleo.iconos_auto import icono_para_texto

        icono_vectorial= icono_para_texto(nombre_modulo)
        if not icono_vectorial.isNull():
            return icono_vectorial

    return QIcon()


#pone en la etiqueta el icono de la cabecera de un módulo: primero el png de la barra lateral,
#después el vectorial, y si el módulo es None se limpia lo que hubiera de una llamada anterior
#(los carruseles de tutoriales reutilizan el mismo QLabel paso a paso).
def aplicar_icono_cabecera(label, nombre_modulo, tamano=30):

    pixmap= pixmap_icono_sidebar(nombre_modulo, tamano) if nombre_modulo else None

    if pixmap is not None:
        label.setText("")
        label.setPixmap(pixmap)
        return

    if nombre_modulo:

        from src.nucleo.iconos_auto import icono_para_texto

        icono_vectorial= icono_para_texto(nombre_modulo)
        if not icono_vectorial.isNull():
            label.setText("")
            label.setPixmap(icono_vectorial.pixmap(tamano, tamano))
            return

    label.setPixmap(QPixmap())


#busca el archivo del icono en las carpetas candidatas y lo deja en caché. Si no aparece devuelve
#un QIcon vacío, que Qt dibuja como nada.
def obtener_icono(nombre_archivo):

    if nombre_archivo in _cache:
        return _cache[nombre_archivo]

    icono= QIcon()
    for carpeta in _carpetas_candidatas_iconos():

        ruta= os.path.join(carpeta, nombre_archivo)
        if os.path.exists(ruta):
            icono= QIcon(ruta)
            break

    _cache[nombre_archivo]= icono

    return icono


def icono_app():

    return obtener_icono(ICONO_APP)


#el escudo grande, para cuando la institución todavía no cargó su propio logo en el login. No es
#el icono de la ventana: ese sigue siendo icono_app().
def pixmap_logo_app(tamano=132):

    if tamano in _cache_pixmap_logo_app:
        return _cache_pixmap_logo_app[tamano]

    pixmap= None
    for carpeta in _carpetas_candidatas_iconos():

        ruta= os.path.join(carpeta, LOGO_APP_GRANDE)
        if os.path.exists(ruta):

            candidato= QPixmap(ruta)
            if not candidato.isNull():
                pixmap= candidato.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
            break

    _cache_pixmap_logo_app[tamano]= pixmap

    return pixmap


#pone el icono de la app, o uno más específico si se pasa el nombre del archivo, como icono de la
#ventana. Sirve para que el tutorial o el buscador tengan su propio icono en la barra de tareas.
def aplicar_icono_ventana(ventana, icono=None):

    ventana.setWindowIcon(obtener_icono(icono) if icono else icono_app())


# -----------------------------------------
# centrar ventanas
# -----------------------------------------
#centra la ventana sobre su padre, o sobre la pantalla si no hay padre, y la trae al frente. Sin
#lo de WindowStaysOnTopHint el diálogo podía abrirse detrás de la ventana y había que buscarlo.
def _centrar_ventana(ventana, parent=None):

    ventana.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    ventana.adjustSize()

    centro= None

    if parent is not None:

        try:

            ventana_padre= parent.window()
            if ventana_padre is not None and ventana_padre.isVisible():
                centro= ventana_padre.frameGeometry().center()

        except Exception:
            centro= None

    if centro is None:

        pantalla= QApplication.primaryScreen()
        if pantalla:
            centro= pantalla.availableGeometry().center()

    if centro is not None:
        geometria= ventana.frameGeometry()
        geometria.moveCenter(centro)
        ventana.move(geometria.topLeft())

    ventana.raise_()
    ventana.activateWindow()


#igual que la de arriba, pero para los diálogos propios. No llama a adjustSize() porque esos
#diálogos ya fijaron su tamaño con resize() y adjustSize() los encogería al mínimo.
#siempre_encima=False lo usan los asistentes de varios pasos: se centran pero no quedan fijos encima de todo.
def centrar_y_al_frente(ventana, parent=None, siempre_encima=True):

    if siempre_encima:
        ventana.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    centro= None

    #con una tabla en pantalla completa abierta se centra sobre ella, no sobre la ventana de atrás
    try:

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        activa= dialogo_pantalla_completa_activo()
        if activa is not None and activa.isVisible():
            centro= activa.frameGeometry().center()

    except Exception:
        pass

    if parent is not None:

        try:

            ventana_padre= parent.window()
            if ventana_padre is not None and ventana_padre.isVisible():
                centro= ventana_padre.frameGeometry().center()

        except Exception:
            centro= None

    if centro is None:

        pantalla= QApplication.primaryScreen()
        if pantalla:
            centro= pantalla.availableGeometry().center()

    if centro is not None:
        geometria= ventana.frameGeometry()
        geometria.moveCenter(centro)
        ventana.move(geometria.topLeft())

    ventana.raise_()
    ventana.activateWindow()


# -----------------------------------------
# mensajes al usuario
# -----------------------------------------
#todos los avisos de la app pasan por acá: "info", "exito", "error", "advertencia" o "pregunta".
#Toma el tema activo para que el cuadro respete el modo claro u oscuro, y devuelve lo que eligió
#el usuario. Si hay una tabla en pantalla completa, el aviso cuelga de ese diálogo y no de la
#ventana principal, que quedaría tapada por el modal.
def mostrar_mensaje(tipo, titulo, texto, parent=None):

    mapa_icono= {
        "info": (QMessageBox.Icon.Information, ICONO_INFO),
        "exito": (QMessageBox.Icon.Information, ICONO_OK),
        "error": (QMessageBox.Icon.Critical, ICONO_ERROR),
        "advertencia": (QMessageBox.Icon.Warning, ICONO_WARNING),
        "pregunta": (QMessageBox.Icon.Question, ICONO_LOGIN),
    }
    icono_qt, icono_archivo= mapa_icono.get(tipo, (QMessageBox.Icon.Information, ICONO_OK))

    try:

        from src.interfaz.paginacion import padre_de_dialogo
        parent= padre_de_dialogo(parent)

    except Exception:
        pass

    box= QMessageBox(parent)
    box.setWindowTitle(titulo)
    box.setText(texto)
    box.setIcon(icono_qt)
    box.setWindowIcon(obtener_icono(icono_archivo))

    if tipo == "pregunta":
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    else:
        box.setStandardButtons(QMessageBox.StandardButton.Ok)

    origen_tema= parent
    if origen_tema is not None and not hasattr(origen_tema, "theme_palettes"):
        origen_tema= getattr(parent, "main_window", None)

    if origen_tema is not None and hasattr(origen_tema, "theme_palettes"):

        try:

            paleta= origen_tema.theme_palettes.get(origen_tema.tema_actual, {})
            indice= 1 if getattr(origen_tema, "modo_oscuro", True) else 0
            fondo= paleta.get("display_bg", ("#FFFFFF", "#1E293B"))[indice]
            texto_color= paleta.get("text_primary", ("#0F172A", "#F8FAFC"))[indice]
            acento= paleta.get("btn_op_bg", ("#6366F1", "#4F46E5"))[indice]
            acento_hover= paleta.get("btn_op_hover", ("#4F46E5", "#4338CA"))[indice]
            box.setStyleSheet(f"""
                QMessageBox {{ background-color: {fondo}; }}
                QMessageBox QLabel {{ color: {texto_color}; font-size: 13px; background-color: transparent; }}
                QPushButton {{
                    background-color: {acento}; color: white; border: none;
                    border-radius: 6px; padding: 8px 22px; font-weight: bold; min-width: 70px;
                }}
                QPushButton:hover {{ background-color: {acento_hover}; }}
            """)

        except Exception:
            pass

    else:
        box.setStyleSheet("""
            QMessageBox { background-color: #FFFFFF; }
            QMessageBox QLabel { color: #0F172A; font-size: 13px; background-color: transparent; }
            QPushButton {
                background-color: #6366F1; color: white; border: none;
                border-radius: 6px; padding: 8px 22px; font-weight: bold; min-width: 70px;
            }
            QPushButton:hover { background-color: #4F46E5; }
        """)

    _centrar_ventana(box, parent)

    resultado= box.exec()

    #la señal va DESPUÉS de cerrar el aviso, no antes: si se emite antes, el tutorial avanza
    #mientras el cuadro sigue abierto y el usuario nunca llega a ver el avance.
    if tipo == "exito":
        eventos_ui.exito_reportado.emit(parent, titulo, texto)

    return resultado


#un solo objeto vivo durante toda la app. Se emite cada vez que un módulo reporta una operación
#exitosa con mostrar_mensaje("exito", ...), y lo escucha tutoriales.py para saber que la acción
#ocurrió de verdad, no que el usuario solo hizo clic en un botón.
class _BusEventosUI(QObject):

    exito_reportado= Signal(object, str, str)   #(parent, titulo, texto)


eventos_ui= _BusEventosUI()
