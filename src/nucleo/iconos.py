import os
import re
import sys
import unicodedata
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtGui import QIcon, QPixmap
from src.nucleo.rutas import get_iconos_dir


# ============================================================
# BUS DE EVENTOS DE ÉXITO — un único objeto Qt vivo durante toda la app.
# Se emite cada vez que un módulo reporta una operación exitosa con
# mostrar_mensaje("exito", ...). Existe para que tutoriales.py (Modo
# Detallado) pueda verificar que una acción real ocurrió -no que el
# usuario solo hizo clic en un botón- sin que ningún otro módulo
# (estudiantes.py, materias.py, calificaciones.py, horario.py...) tenga
# que agregar una señal propia: todos ya pasan por mostrar_mensaje("exito",
# ...) únicamente después de guardar con éxito en la base de datos, así
# que engancharse aquí es gratis y no toca ningún otro archivo del resto
# de la app.
# ============================================================
class _BusEventosUI(QObject):
    exito_reportado = Signal(object, str, str)  # (parent, titulo, texto)


eventos_ui = _BusEventosUI()

CARPETA_ICONOS = get_iconos_dir()


def _carpetas_candidatas_iconos():
    """Genera, en orden de prioridad, las carpetas donde puede estar
    "iconos" tanto en desarrollo como empaquetado con PyInstaller (--onedir).

    En --onedir, PyInstaller copia los datos agregados a una carpeta
    "_internal" junto al .exe, y expone su ruta en sys._MEIPASS. Esa ruta
    se resuelve en tiempo de ejecución a partir de la ubicación real del
    .exe, así que funciona sin importar en qué disco/carpeta lo instale
    Inno Setup.
    """
    candidatas = [CARPETA_ICONOS]

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidatas.append(os.path.join(meipass, "iconos"))
            candidatas.append(meipass)

        carpeta_exe = os.path.dirname(os.path.abspath(sys.executable))
        candidatas.append(os.path.join(carpeta_exe, "_internal", "iconos"))
        candidatas.append(os.path.join(carpeta_exe, "_internal"))
        candidatas.append(os.path.join(carpeta_exe, "iconos"))
        candidatas.append(carpeta_exe)

    # Sin duplicados, conservando el orden de prioridad.
    vistas = set()
    resultado = []
    for c in candidatas:
        if c and c not in vistas:
            vistas.add(c)
            resultado.append(c)
    return resultado


# ============================================================
# ICONOS DE LA SIDEBAR (reemplazo de los emojis del menú lateral)
# Viven en iconos/sidebar_icons/*.png. Usan LA MISMA lógica de resolución
# de rutas que _carpetas_candidatas_iconos (dev y PyInstaller --onedir),
# así que si "iconos" ya se empaqueta como carpeta de datos, "sidebar_icons"
# -al estar anidada dentro- se resuelve automáticamente sin tocar nada del
# instalador/spec de PyInstaller.
# ============================================================
def _carpetas_candidatas_sidebar_icons():
    candidatas = [os.path.join(c, "sidebar_icons") for c in _carpetas_candidatas_iconos()]
    vistas = set()
    resultado = []
    for c in candidatas:
        if c not in vistas:
            vistas.add(c)
            resultado.append(c)
    return resultado


def _normalizar_clave(texto):
    """'Mis Materias.png' / 'banco de tareas' / 'Calificaciones Técnicas' ->
    todas se reducen a solo letras/números en minúscula sin acentos, para
    poder emparejar el NOMBRE DE ARCHIVO (indicador de qué icono es) con el
    nombre del módulo sin depender de espacios, mayúsculas o tildes exactos."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


# Para cada módulo de la sidebar, lista de claves normalizadas de nombre de
# archivo (sin extensión) que se aceptan como su icono, en orden de
# preferencia. Un módulo con lista vacía/None no tiene icono propio todavía
# y conserva su emoji como respaldo (ver ModuloNavItem en main.py).
ALIAS_ICONOS_SIDEBAR = {
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
    "Horario": ["horario"],
    "Calendario": ["calendaria", "calendario"],
    "Observaciones": ["observaciones"],
    "Psicología": ["psicologia"],
    "Reportes": ["reportes"],
    "Copias de Seguridad": ["backup", "copiasdeseguridad"],
    "Sincronización": ["sincronizacion"],
    "Configuración": ["configuracion"],
}

_EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".bmp", ".ico")
_indice_sidebar_icons = None
_cache_pixmap_sidebar = {}


def _indice_archivos_sidebar_icons():
    """Escanea TODAS las carpetas candidatas (no se detiene en la primera
    que exista) y arma {clave_normalizada: ruta_completa}, dando prioridad
    a la primera carpeta donde aparezca cada archivo (respeta el orden de
    prioridad dev -> _internal -> junto al .exe de _carpetas_candidatas_iconos)."""
    global _indice_sidebar_icons
    if _indice_sidebar_icons is not None:
        return _indice_sidebar_icons
    indice = {}
    for carpeta in _carpetas_candidatas_sidebar_icons():
        if not os.path.isdir(carpeta):
            continue
        try:
            nombres = os.listdir(carpeta)
        except OSError:
            continue
        for nombre_archivo in nombres:
            base, ext = os.path.splitext(nombre_archivo)
            if ext.lower() not in _EXTENSIONES_IMAGEN:
                continue
            clave = _normalizar_clave(base)
            if clave not in indice:
                indice[clave] = os.path.join(carpeta, nombre_archivo)
    _indice_sidebar_icons = indice
    return indice


def ruta_icono_sidebar(nombre_modulo):
    """Devuelve la ruta del archivo de icono para `nombre_modulo` (el mismo
    texto que aparece en el menú lateral, ej. "Estudiantes"), o None si ese
    módulo todavía no tiene un icono propio en sidebar_icons/ (en ese caso
    el llamador debe seguir mostrando el emoji de respaldo)."""
    claves = ALIAS_ICONOS_SIDEBAR.get(nombre_modulo) or []
    if not claves:
        return None
    indice = _indice_archivos_sidebar_icons()
    for clave in claves:
        ruta = indice.get(clave)
        if ruta:
            return ruta
    return None


def _recortar_margen_transparente(ruta):
    """Devuelve los bytes PNG del icono recortado a su contenido real (sin el
    margen transparente que trae cada PNG, que varía de un archivo a otro).

    Esta es la causa real de que algunos iconos de la sidebar se vean
    "chiquitos" aunque el chip donde se dibujan mida siempre lo mismo: cada
    ícono viene con una cantidad distinta de aire alrededor del dibujo, así
    que escalarlos todos al mismo tamaño de CAJA no los deja del mismo
    tamaño VISUAL -uno con poco margen llena el chip, uno con mucho margen
    queda diminuto en el centro-. Recortando primero al bounding box del
    contenido no transparente, y recién después escalando, todos terminan
    ocupando la misma proporción del chip.

    Devuelve None si Pillow no está disponible o el recorte falla por
    cualquier motivo -en ese caso el llamador debe seguir usando el PNG
    original tal cual, tal como se hacía antes de esto."""
    try:
        from PIL import Image
        import io
        with Image.open(ruta) as img:
            img = img.convert("RGBA")
            caja = img.getbbox()
            if not caja:
                return None
            recortada = img.crop(caja)
            buffer = io.BytesIO()
            recortada.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception:
        return None


def pixmap_icono_sidebar(nombre_modulo, tamano=26):
    """QPixmap ya recortado (sin margen transparente sobrante) y escalado,
    listo para un QLabel, o None si no hay icono (ni el archivo existe/está
    corrupto) para `nombre_modulo`."""
    ruta = ruta_icono_sidebar(nombre_modulo)
    if not ruta:
        return None
    clave_cache = (ruta, tamano)
    if clave_cache in _cache_pixmap_sidebar:
        return _cache_pixmap_sidebar[clave_cache]
    datos_recortados = _recortar_margen_transparente(ruta)
    pixmap = QPixmap()
    cargado = pixmap.loadFromData(datos_recortados) if datos_recortados else False
    if not cargado:
        pixmap = QPixmap(ruta)  # Pillow no disponible o recorte falló: PNG tal cual
    if pixmap.isNull():
        _cache_pixmap_sidebar[clave_cache] = None
        return None
    pixmap = pixmap.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    _cache_pixmap_sidebar[clave_cache] = pixmap
    return pixmap


def icono_qicon_modulo(nombre_modulo, tamano=18):
    """QIcon con el MISMO icono que ya usa la fila de ese módulo en la
    sidebar (o su cabecera "hero"), pero reducido a tamaño de emoji -
    pensado para listas de resultados como el Buscador Global, donde cada
    fila necesita un icono chiquito y coherente con el resto de la app, en
    vez de un dibujo QPainter aparte (y potencialmente distinto) elegido a
    mano solo para esa lista.

    Sigue EXACTAMENTE la misma cadena de prioridad que ModuloNavItem (la
    fila real de la sidebar) y aplicar_icono_cabecera:
      1. El PNG real de sidebar_icons/ para `nombre_modulo`, si existe.
      2. Si no hay PNG todavía, el icono VECTORIAL coherente de
         iconos_auto.py -el mismo mapa semántico que ya usan los
         botones/pestañas de ese módulo-, nunca un emoji crudo suelto.
      3. QIcon() vacío si de verdad no hay ninguno de los dos -el llamador
         decide qué hacer (p. ej. no llamar setIcon en absoluto)."""
    pixmap = pixmap_icono_sidebar(nombre_modulo, tamano) if nombre_modulo else None
    if pixmap is not None:
        return QIcon(pixmap)
    if nombre_modulo:
        from src.nucleo.iconos_auto import icono_para_texto
        icono_vectorial = icono_para_texto(nombre_modulo)
        if not icono_vectorial.isNull():
            return icono_vectorial
    return QIcon()


def aplicar_icono_cabecera(label, nombre_modulo, tamano=30):
    """Pone en `label` el icono de la cabecera "hero" de un módulo (el mismo
    patrón repetido en Asistencia, Horario, Materias, Reportes, etc., y
    también reutilizado por los carruseles de tutoriales.py).

    Prioridad, de más a menos específico:
      1. El PNG real de sidebar_icons/ para `nombre_modulo`, si existe
         -mismos nombres/alias que ya usa la sidebar, ver ALIAS_ICONOS_SIDEBAR-.
      2. Si no hay PNG (todavía no se diseñó uno para ese módulo, o
         `sidebar_icons/` no está disponible en este equipo), el icono
         VECTORIAL coherente que ya usan los botones/pestañas de ese mismo
         módulo -el mismo mapa semántico de iconos_auto.py-, así la cabecera
         nunca se queda en blanco ni depende de que el sistema operativo
         tenga una fuente de emojis instalada.
      3. Si `nombre_modulo` es None (pasos "de interfaz general" o de cierre
         de un tutorial) y no hay ningún icono que asignar, se limpia
         cualquier pixmap que hubiera quedado de una llamada anterior con
         OTRO módulo sobre el mismo QLabel -necesario en los carruseles de
         tutoriales.py, donde un mismo QLabel se reutiliza paso a paso-."""
    pixmap = pixmap_icono_sidebar(nombre_modulo, tamano) if nombre_modulo else None
    if pixmap is not None:
        label.setText("")
        label.setPixmap(pixmap)
        return

    if nombre_modulo:
        from src.nucleo.iconos_auto import icono_para_texto
        icono_vectorial = icono_para_texto(nombre_modulo)
        if not icono_vectorial.isNull():
            label.setText("")
            label.setPixmap(icono_vectorial.pixmap(tamano, tamano))
            return

    label.setPixmap(QPixmap())


ICONO_APP = "schoolsys.ico"
LOGO_APP_GRANDE = "AcaDeXI_logo.png"       # Logo grande de la app (shield), NO el .ico de la ventana

ICONO_OK = "correctico.ico"
ICONO_ERROR = "eroico.ico"
ICONO_WARNING = "warningico.ico"
ICONO_LOGIN = "loginico.ico"
ICONO_DETALLE = "detalleico.ico"
ICONO_SETTING = "settingico.ico"
ICONO_TABLA = "tableico.ico"
ICONO_ASISTENTE = "asistenteico.ico"      # Asistente de Sincronización
ICONO_BUSQUEDA = "busquedaico.ico"        # Búsqueda Global
ICONO_CARGA = "cargaico.ico"              # Diálogos que procesan/recalculan un archivo cargado
ICONO_COLOR = "colorico.ico"              # Selección de color (marca de agua, etc.)
ICONO_RECORTE = "imagenrecortico.ico"     # Foto: ver / recortar
ICONO_INFO = "infoico.ico"                # Mensajes informativos (distinto de "éxito")
ICONO_SETUP = "setupico.ico"              # Asistente de Configuración Inicial (Wizard)
ICONO_TUTORIAL = "tutorial.ico"           # Tutorial guiado / Modo Detallado
ICONO_DOCUMENTO = "documentico.ico"       # Generación de documentos/paquetes (.acdx, PDF)
ICONO_FILTRO = "filtradoico.ico"          # Ventanita de "Filtros" (Estudiantes, Horario, etc.)

_cache = {}


def get_icon(nombre_archivo):
    if nombre_archivo in _cache:
        return _cache[nombre_archivo]
    icono = QIcon()
    for carpeta in _carpetas_candidatas_iconos():
        ruta = os.path.join(carpeta, nombre_archivo)
        if os.path.exists(ruta):
            icono = QIcon(ruta)
            break
    _cache[nombre_archivo] = icono
    return icono


def icono_app():
    return get_icon(ICONO_APP)


_cache_pixmap_logo_app = {}


def pixmap_logo_app(tamano=132):
    """QPixmap del logo GRANDE de AcaDeXI (el escudo, LOGO_APP_GRANDE),
    escalado a `tamano` conservando proporción, o None si el archivo no
    está disponible en ninguna carpeta candidata. Pensado para el respaldo
    del login cuando la institución todavía no cargó su propio logo -ver
    login.py-, NO para el icono pequeño de ventana (eso sigue siendo
    icono_app()/ICONO_APP)."""
    if tamano in _cache_pixmap_logo_app:
        return _cache_pixmap_logo_app[tamano]
    pixmap = None
    for carpeta in _carpetas_candidatas_iconos():
        ruta = os.path.join(carpeta, LOGO_APP_GRANDE)
        if os.path.exists(ruta):
            candidato = QPixmap(ruta)
            if not candidato.isNull():
                pixmap = candidato.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
            break
    _cache_pixmap_logo_app[tamano] = pixmap
    return pixmap


def aplicar_icono_ventana(ventana, icono=None):
    """Aplica el icono de la app -o uno más específico (ver ICONO_* arriba)-
    como windowIcon de `ventana`. Pasar `icono` (nombre de archivo, ej.
    ICONO_TUTORIAL) para que ventanas concretas -tutoriales, asistentes,
    buscador, etc.- muestren un icono propio en vez del genérico de AcaDeXI;
    si se omite, se conserva el comportamiento de siempre (icono de la app)."""
    ventana.setWindowIcon(get_icon(icono) if icono else icono_app())


def _centrar_ventana(ventana, parent=None):
    """Centra `ventana` sobre la ventana `parent` (o, si no hay parent
    utilizable, sobre la pantalla principal) SOLO como posición inicial:
    el usuario sigue pudiendo arrastrarla a otro lugar con total libertad,
    esto únicamente evita que aparezca "tirada" en una esquina lejana.

    Además fuerza que `ventana` se muestre POR ENCIMA de cualquier otra
    ventana de la app (WindowStaysOnTopHint) y la activa/trae al frente.
    Sin esto, si el usuario cambió a otra ventana/app mientras se generaba
    el mensaje, el diálogo podía abrirse "detrás" y había que buscarlo."""
    ventana.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    ventana.adjustSize()
    centro = None
    if parent is not None:
        try:
            ventana_top = parent.window()
            if ventana_top is not None and ventana_top.isVisible():
                centro = ventana_top.frameGeometry().center()
        except Exception:
            centro = None
    if centro is None:
        pantalla = QApplication.primaryScreen()
        if pantalla:
            centro = pantalla.availableGeometry().center()
    if centro is not None:
        geo = ventana.frameGeometry()
        geo.moveCenter(centro)
        ventana.move(geo.topLeft())
    ventana.raise_()
    ventana.activateWindow()


def centrar_y_al_frente(ventana, parent=None):
    """Alias público de `_centrar_ventana`, pensado para que cualquier
    QDialog personalizado de la app (no solo los mensajes de
    `mostrar_mensaje`) se abra centrado sobre su ventana padre y por
    delante de cualquier otra ventana. Llamar al final del __init__,
    después de construir la UI.

    A diferencia de `_centrar_ventana` (usada por los QMessageBox, que no
    tienen tamaño propio hasta que se calcula su contenido), esta versión
    NO llama a adjustSize(): varios diálogos personalizados fijan su
    tamaño explícitamente con resize()/setMinimumWidth() antes de esta
    llamada, y adjustSize() los encogería de vuelta a su sizeHint()."""
    ventana.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    centro = None
    # Con una tabla en pantalla completa activa (diálogo modal), se centra
    # sobre ELLA y no sobre la ventana principal, que quedaría tapada.
    try:
        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        activa = dialogo_pantalla_completa_activo()
        if activa is not None and activa.isVisible():
            centro = activa.frameGeometry().center()
    except Exception:
        pass
    if parent is not None:
        try:
            ventana_top = parent.window()
            if ventana_top is not None and ventana_top.isVisible():
                centro = ventana_top.frameGeometry().center()
        except Exception:
            centro = None
    if centro is None:
        pantalla = QApplication.primaryScreen()
        if pantalla:
            centro = pantalla.availableGeometry().center()
    if centro is not None:
        geo = ventana.frameGeometry()
        geo.moveCenter(centro)
        ventana.move(geo.topLeft())
    ventana.raise_()
    ventana.activateWindow()


def mostrar_mensaje(tipo, titulo, texto, parent=None):
    mapa_icono = {
        "info": (QMessageBox.Icon.Information, ICONO_INFO),
        "exito": (QMessageBox.Icon.Information, ICONO_OK),
        "error": (QMessageBox.Icon.Critical, ICONO_ERROR),
        "advertencia": (QMessageBox.Icon.Warning, ICONO_WARNING),
        "pregunta": (QMessageBox.Icon.Question, ICONO_LOGIN),
    }
    icono_qt, icono_archivo = mapa_icono.get(tipo, (QMessageBox.Icon.Information, ICONO_OK))

    # Si hay una tabla en pantalla completa (diálogo MODAL), el mensaje debe
    # colgar de ESE diálogo: parentado a la ventana principal quedaría por
    # detrás del modal, inaccesible para el usuario.
    try:
        from src.interfaz.paginacion import padre_de_dialogo
        parent = padre_de_dialogo(parent)
    except Exception:
        pass

    box = QMessageBox(parent)
    box.setWindowTitle(titulo)
    box.setText(texto)
    box.setIcon(icono_qt)
    box.setWindowIcon(get_icon(icono_archivo))

    if tipo == "pregunta":
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    else:
        box.setStandardButtons(QMessageBox.StandardButton.Ok)

    origen_tema = parent
    if origen_tema is not None and not hasattr(origen_tema, "theme_palettes"):
        origen_tema = getattr(parent, "main_window", None)

    if origen_tema is not None and hasattr(origen_tema, "theme_palettes"):
        try:
            paleta = origen_tema.theme_palettes.get(origen_tema.tema_actual, {})
            idx = 1 if getattr(origen_tema, "modo_oscuro", True) else 0
            bg = paleta.get("display_bg", ("#FFFFFF", "#1E293B"))[idx]
            txt = paleta.get("text_primary", ("#0F172A", "#F8FAFC"))[idx]
            accent = paleta.get("btn_op_bg", ("#6366F1", "#4F46E5"))[idx]
            accent_hv = paleta.get("btn_op_hover", ("#4F46E5", "#4338CA"))[idx]
            box.setStyleSheet(f"""
                QMessageBox {{ background-color: {bg}; }}
                QMessageBox QLabel {{ color: {txt}; font-size: 13px; background-color: transparent; }}
                QPushButton {{
                    background-color: {accent}; color: white; border: none;
                    border-radius: 6px; padding: 8px 22px; font-weight: bold; min-width: 70px;
                }}
                QPushButton:hover {{ background-color: {accent_hv}; }}
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

    resultado = box.exec()

    # BUG CORREGIDO: esta señal se emitía ANTES de crear/mostrar el propio
    # QMessageBox (arriba del todo, antes de `box = QMessageBox(parent)`).
    # tutoriales.py (Modo Detallado) la escucha para saber que una acción
    # real ya ocurrió y, al recibirla, agenda el avance automático del paso
    # 650ms después (ver AsistenteSpotlight._on_exito_reportado). Como
    # box.exec() es MODAL y bloquea hasta que el usuario lo cierra -algo
    # que puede tardar bastante más de 650ms-, ese avance automático se
    # disparaba MIENTRAS el cuadro "Guardado" seguía abierto en pantalla
    # (los timers de Qt sí se siguen procesando dentro del bucle anidado de
    # un exec() modal): el tutorial cambiaba de paso -y a veces hasta de
    # módulo, si el próximo paso navega a otra pantalla- por debajo del
    # aviso, todavía visible, de "¡Guardado!". El usuario nunca llegaba a
    # ver ningún avance ni feedback real (ya había pasado, oculto detrás
    # del cuadro) y terminaba sintiendo que había que usar "Saltar este
    # paso" a la fuerza. Ahora se emite DESPUÉS de que el usuario cierra el
    # aviso -el avance automático refleja una confirmación que el usuario
    # ya vio y aceptó, no una que todavía no había llegado a mostrarse.
    if tipo == "exito":
        eventos_ui.exito_reportado.emit(parent, titulo, texto)

    return resultado