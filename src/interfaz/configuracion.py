#Configuracion.py - completo con paginación y botones debajo de la tabla de usuarios (sin el botón "ver
#detalle" en usuarios)
import os
import re
from src.nucleo.atajos import TECLAS_ATAJO_DISPONIBLES, TECLA_ATAJO_POR_DEFECTO, registrar_atajo
import sys
import shutil
import unicodedata
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QCheckBox,
    QGridLayout, QScrollArea, QFormLayout,
    QDateEdit, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QToolButton
)
from PySide6.QtCore import (Qt, QUrl, QObject, QEvent, QTimer, QRectF, QPointF, QPoint,
    QPropertyAnimation, QVariantAnimation, QEasingCurve, QSize)
from PySide6.QtGui import QPixmap, QDesktopServices, QColor, QPainter, QPen
from src.nucleo.bd import (obtener_conexion, hash_password, verificar_contrasena, registrar_auditoria, crear_backup,
                restaurar_backup, obtener_carpeta_datos, obtener_historial_backups,
                CRITERIOS_NUMERO_LISTA, DESCRIPCION_CRITERIO_NUMERO_LISTA, CRITERIO_APELLIDOS_NOMBRE,
                CRITERIO_MANUAL, obtener_criterio_numero_lista, recalcular_numeros_lista_todas_secciones)
from src.sincronizacion.sincronizacion import obtener_estado, subir_cambios, descargar_novedades
from src.sincronizacion.sync_docente import exportar_paquete_docente
from src.nucleo.iconos import aplicar_icono_ventana, mostrar_mensaje, centrar_y_al_frente, ICONO_SETUP, aplicar_icono_cabecera, ICONO_COLOR
from src.nucleo.permisos import ROLES, es_admin, listar_roles_side_stepper_configurados
from src.interfaz.foto_utils import seleccionar_y_recortar_foto, VisorFotoDialog
from src.interfaz.paginacion import (ControlPaginacion, agregar_boton_detalle, tabla_pausada, aplicar_estructura_tabla,
    agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import FORMATOS_HORA, FORMATOS_FECHA, formatear_fecha_hora
from src.nucleo.limite_campos import limitar_campo_texto
from src.servicios.alarmas import PanelAlarmas
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, EMOJI_COPIA_SEGURIDAD, EMOJI_AUDITORIA, EMOJI_TUTORIAL,
                           EMOJI_TAB_ACADEMICO, EMOJI_TAB_USUARIOS_ROLES, EMOJI_TAB_AUDITORIA,
                           EMOJI_FOTO_RECORTAR)
from src.nucleo.rutas import obtener_carpeta_raiz


#Utilidades visuales (solo estética/animación — no tocan datos ni lógica)
#Convierte '#RRGGBB' a 'rgba(r, g, b, a)' para usar en hojas de estilo.
def _hex_a_rgba(hex_color, alpha):

    hex_color= (hex_color or "#000000").lstrip("#")
    if len(hex_color) < 6:
        hex_color= "000000"
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Toma un color 'rgba(r, g, b, a)' (semitransparente) y lo funde sobre un
#color de fondo '#RRGGBB' sólido, devolviendo el resultado como un
#'#RRGGBB' SÓLIDO equivalente (misma composición visual, sin canal alfa).
#
#Se usa para el hover de las flechitas de scroll de las pestañas
#(`estilo_flechas_navegacion_tabs`): esos botones se repintan en cada clic
#y, al estar dentro de ventanas con fondo translúcido (WA_TranslucentBackground),
#Qt no siempre limpia el área antes de repintar un color con alfa, así que
#el semitransparente se va acumulando sobre sí mismo con cada uso hasta
#volverse opaco y tapar la flecha. Aplanar el color de antemano a un
#sólido con el MISMO resultado visual (matemáticamente: alpha*color +
#(1-alpha)*fondo) evita ese acumulado por completo, sin cambiar cómo se ve.
def _aplanar_color_sobre(color_rgba, hex_fondo):

    coincidencia= re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color_rgba or "")
    if not coincidencia:
        return color_rgba
    r, g, b, a= int(coincidencia.group(1)), int(coincidencia.group(2)), int(coincidencia.group(3)), float(coincidencia.group(4))
    hex_fondo= (hex_fondo or "#000000").lstrip("#")
    if len(hex_fondo) < 6:
        hex_fondo= "000000"
    fr, fg, fb= int(hex_fondo[0:2], 16), int(hex_fondo[2:4], 16), int(hex_fondo[4:6], 16)
    rr= round(a * r + (1 - a) * fr)
    rg= round(a * g + (1 - a) * fg)
    rb= round(a * b + (1 - a) * fb)
    return f"#{rr:02X}{rg:02X}{rb:02X}"


#Quita mayúsculas y acentos para que el buscador no sea estricto:
#'jose', 'José' y 'JOSÉ' encuentran lo mismo. (mismo criterio que horario.py)
def _normalizar(texto):

    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


#Icono de lupa dibujado a mano con QPainter para la barra de búsqueda
#(mismo diseño que horario.py).
class IconoLupa(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(17, 17)
        self._color= "#64748B"

    def establecer_color(self, color):

        self._color= color
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen= QPen(QColor(self._color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1.5, 1.5, 9.5, 9.5))
        painter.drawLine(QPointF(9.7, 9.7), QPointF(15, 15))


#Filtro de eventos reutilizable: al pasar el mouse sobre un botón o tarjeta,
#'eleva' suavemente su sombra (más difusa y con más separación) y la vuelve a
#bajar al salir. Es puramente decorativo — no intercepta ni modifica clics.
class _RealceHover(QObject):

    def __init__(self, blur_normal=0, blur_hover=22, offset_hover=6, parent=None):

        super().__init__(parent)
        self._blur_normal= blur_normal
        self._blur_hover= blur_hover
        self._offset_hover= offset_hover

    def eventFilter(self, objeto, evento):

        tipo= evento.type()
        if tipo == QEvent.Type.Enter and objeto.isEnabled():
            self._animar(objeto, self._blur_hover)
        elif tipo == QEvent.Type.Leave:
            self._animar(objeto, self._blur_normal)
        return False

    def _animar(self, widget, destino_blur):

        efecto= widget.graphicsEffect()
        if not isinstance(efecto, QGraphicsDropShadowEffect):
            efecto= QGraphicsDropShadowEffect(widget)
            efecto.setColor(QColor(0, 0, 0, 90))
            efecto.setOffset(0, 2)
            efecto.setBlurRadius(self._blur_normal)
            widget.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"blurRadius", widget)
        anim.setDuration(200)
        anim.setStartValue(efecto.blurRadius())
        anim.setEndValue(destino_blur)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        offset_anim= QPropertyAnimation(efecto, b"yOffset", widget)
        offset_anim.setDuration(200)
        offset_anim.setStartValue(efecto.yOffset())
        offset_anim.setEndValue(self._offset_hover if destino_blur == self._blur_hover else 2)
        offset_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        offset_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


#Aplica un fundido de entrada (opacidad 0→1) a `widget`. Se usa al cambiar
#de pestaña o de paso del asistente, para que la transición se sienta fluida
#en vez de un salto brusco.
def _fundido_entrada(widget, duracion=260):

    efecto= QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(efecto)
    anim= QPropertyAnimation(efecto, b"opacity", widget)
    anim.setDuration(duracion)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutSine)
    #Guardamos la referencia en el widget para que Python no la recolecte a mitad de camino.
    widget._anim_fundido= anim

    def _limpiar():

        widget.setGraphicsEffect(None)
    anim.finished.connect(_limpiar)
    anim.start()


#Evita que uno o más QComboBox se inflen más allá de lo razonable por
#culpa de un ítem largo (placeholder tipo "Selecciona primero un
#curso/grado...", nombre completo de estudiante, título de tarea, etc.).
#
#Por defecto un QComboBox pide como ancho mínimo el necesario para
#mostrar su ítem MÁS LARGO sin recortar. Eso ignora los stretch
#factors de layouts (QGridLayout/QHBoxLayout) que lo contienen y puede
#empujar toda una fila, tarjeta o incluso la ventana completa más
#ancha que la pantalla — descuadrando el resto de los campos. El texto
#largo se sigue mostrando completo al desplegar la lista; solo el
#propio combo deja de inflarse para "adelantarse" a acomodarlo.
#Úsalo justo después de crear el/los combo(s), antes o después de
#poblarlos (aplica igual en ambos casos).
def ajustar_combo_ancho_seguro(*combos, min_len=16):

    for combo in combos:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(min_len)


#Deja siempre visible, en tooltip, el NOMBRE COMPLETO de un combo de
#Área Técnica/Carrera (u otro combo angosto parecido), tanto CERRADO
#como con la lista DESPLEGADA:
#
#- Cerrado: el tooltip del propio combo muestra el ítem seleccionado
#(encima de su descripción/ayuda de siempre, si se pasa `texto_base`),
#útil cuando el texto queda truncado con "..." por lo angosto del
#combo.
#- Desplegado: cada fila de la lista lleva su propio tooltip con su
#texto completo (vía Qt.ToolTipRole), así que pasar el mouse por
#CUALQUIER opción -esté o no seleccionada, se vea o no truncada- la
#muestra completa, sin tener que elegirla primero.
#
#Se conecta tanto a currentIndexChanged (para el tooltip del combo
#cerrado) como a las inserciones de filas del modelo (para el tooltip de
#cada ítem de la lista), así que ambos se mantienen al día solos con
#cada cambio de selección o repoblado del combo.
#
#SEGURA de llamar más de una vez sobre el MISMO combo (por ejemplo, un
#combo de Curso/Sección que se repuebla en cada cambio de filtro, como
#los de filtros_curso_seccion.py): la primera vez conecta las señales;
#las siguientes solo actualizan `texto_base` y refrescan el tooltip ya
#con la selección actual -no vuelve a apilar conexiones duplicadas.
def conectar_tooltip_seleccion(combo, texto_base=""):

    combo._tooltip_seleccion_texto_base= texto_base

    def _refrescar_tooltip_combo(_indice=None):

        seleccionado= combo.currentText().strip()
        base= getattr(combo, "_tooltip_seleccion_texto_base", "")
        if seleccionado and base:
            combo.setToolTip(f"{base}\n\nSeleccionado: {seleccionado}")
        elif seleccionado:
            combo.setToolTip(seleccionado)
        else:
            combo.setToolTip(base)

    if getattr(combo, "_tooltip_seleccion_conectado", False):
        _refrescar_tooltip_combo()
        return

    def _refrescar_tooltips_items(_padre=None, primero=None, ultimo=None):

        if primero is None:
            primero, ultimo= 0, combo.count() - 1
        for i in range(primero, ultimo + 1):
            texto= combo.itemText(i)
            if texto:
                combo.setItemData(i, texto, Qt.ItemDataRole.ToolTipRole)

    combo.currentIndexChanged.connect(_refrescar_tooltip_combo)
    combo.model().rowsInserted.connect(_refrescar_tooltips_items)
    combo._tooltip_seleccion_conectado= True
    _refrescar_tooltip_combo()
    _refrescar_tooltips_items()


#QTabWidget que garantiza la navegación entre pestañas con las flechas
#izquierda/derecha del teclado.
#
#QTabBar ya trae esto "de fábrica", pero solo funciona si la barra de
#pestañas tiene el foco de teclado en ese momento — y en la práctica eso
#no siempre pasa (por ejemplo si el foco quedó en otro control de la
#pestaña, o si algo más arriba en la jerarquía de widgets no lo deja
#llegar). Esta clase lo resuelve de dos formas: 1) le da foco explícito a
#la barra apenas se hace clic en una pestaña, para que las flechas
#funcionen de inmediato después; y 2) maneja Left/Right ella misma como
#respaldo — Qt propaga los eventos de teclado no consumidos hacia el
#widget padre, así que aunque el foco esté en cualquier otro punto sin
#uso propio de las flechas (un botón, una etiqueta, el área en blanco de
#la pestaña...), el evento termina llegando aquí de todos modos.
class TabWidgetNavegable(QTabWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.tabBar().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabBarClicked.connect(lambda _i: self.tabBar().setFocus())
        #Mismo problema que QStackedWidget: por defecto, el tamaño mínimo de un QTabWidget se calcula tomando en cuenta
        #TODAS sus pestañas, no solo la que está visible. Si una pestaña que el usuario nunca
        #abrió (p. ej. "Entregas") contiene un combo que se llena con
        #texto largo (títulos de tareas), su ancho mínimo se filtra igual y ensancha la pestaña visible ("Catálogo de
        #Tareas"), aunque esa pestaña por sí sola quepa perfecto. Esto hace que solo se considere la pestaña actual, y
        #se refresca al cambiar de pestaña.
        self.currentChanged.connect(lambda _i: self.updateGeometry())
        #Ver _enganchar_botones_scroll: evita que las flechitas de scroll de la barra se vayan "manchando" con el uso
        #repetido.
        self._botones_scroll_enganchados= set()
        self.tabBar().installEventFilter(self)

    def eventFilter(self, objeto, evento):

        if objeto is self.tabBar() and evento.type() == QEvent.Type.ChildPolished:
            self._enganchar_botones_scroll()
        return super().eventFilter(objeto, evento)

    #Qt crea sus propias flechitas de scroll (QToolButton) como hijas
    #del QTabBar SOLO cuando las pestañas no caben todas y hacen falta -
    #no existen desde el principio, aparecen sobre la marcha. Se
    #"enganchan" apenas aparecen para forzar un repintado COMPLETO y
    #limpio de la barra cada vez que se usan.
    #
    #Por qué hace falta: estas ventanas son translúcidas
    #(WA_TranslucentBackground) para el efecto de fondo difuminado. En
    #esa configuración Qt a veces optimiza el repintado dibujando solo
    #el rectángulo "dañado" (el botón) sin limpiar antes ese pedazo del
    #backing store -así que los píxeles semitransparentes del borde
    #redondeado (antialiasing) se van componiendo unos sobre otros con
    #cada clic. Con el uso repetido (mantener presionado también cuenta:
    #el autorepeat dispara 'clicked' varias veces por segundo) ese
    #residuo se acumula hasta volverse un bloque sólido que tapa la
    #flecha -exactamente el bug reportado. Forzar un repaint() síncrono
    #de TODA la barra en cada clic impide que el residuo llegue a
    #acumularse: cada uso deja la barra perfectamente limpia otra vez,
    #sin cambiar en nada cómo se ve.
    def _enganchar_botones_scroll(self):

        for boton in self.tabBar().findChildren(QToolButton):
            if boton in self._botones_scroll_enganchados:
                continue
            self._botones_scroll_enganchados.add(boton)
            boton.clicked.connect(self._repintar_barra_limpia)

    def _repintar_barra_limpia(self):

        barra= self.tabBar()
        QTimer.singleShot(0, barra.repaint)

    def sizeHint(self):

        w= self.currentWidget()
        if w is None:
            return super().sizeHint()
        cromo= super().sizeHint()
        return QSize(w.sizeHint().width(), cromo.height())

    def minimumSizeHint(self):

        w= self.currentWidget()
        if w is None:
            return super().minimumSizeHint()
        cromo= super().minimumSizeHint()
        #Ancho: solo el de la pestaña actualmente visible (así una pestaña nunca abierta, como "Entregas", no infla a
        #las demás). Alto: se conserva el de Qt para no romper la barra de pestañas.
        return QSize(w.minimumSizeHint().width(), cromo.height())

    def keyPressEvent(self, evento):

        if self.count() > 1 and evento.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            paso= -1 if evento.key() == Qt.Key.Key_Left else 1
            self.setCurrentIndex((self.currentIndex() + paso) % self.count())
            self.tabBar().setFocus()
            evento.accept()
            return
        super().keyPressEvent(evento)


#QSS para las flechitas ('«' '»') que Qt agrega solas a la derecha de un
#QTabBar cuando las pestañas no caben todas en el ancho disponible.
#
#Sin este QSS, ese control se dibuja con el estilo NATIVO del sistema
#operativo (una cajita gris de Windows, por ejemplo) que no combina en
#absoluto con el diseño "píldora" plano del resto de la barra de
#pestañas -de ahí que se vea tan fuera de lugar-. Esto lo viste con el
#mismo lenguaje visual: fondo redondeado a juego con el panel, hover con
#el color de acento suavizado, y el degradado del acento al presionar.
#
#Se expone como función (y no como un bloque de QSS ya armado) porque
#Calificaciones, Configuración y Reportes arman cada uno su propio
#grupo de colores del tema con nombres de variables distintos; cada
#módulo llama a esta función con SUS variables y concatena el resultado
#al QSS que ya arma para `self.tabs` (junto al de QTabBar::tab), en vez
#de mantener tres copias casi idénticas de este bloque desperdigadas.
def estilo_flechas_navegacion_tabs(accent, accent_hover, bg_panel, bg_boton, accent_suave):

    #El hover se recibe semitransparente (rgba con alfa), pero aquí se "aplana" a un sólido equivalente antes de
    #usarlo: estos botones se repintan en cada clic de scroll y, al vivir dentro de ventanas translúcidas, un fondo
    #con alfa se va acumulando sobre sí mismo con el uso repetido hasta volverse opaco y tapar la flecha por
    #completo. El aplanado da el MISMO color visual, así que el aspecto no cambia.
    accent_suave_solido= _aplanar_color_sobre(accent_suave, bg_panel)
    return f"""
        QTabBar {{
            background: transparent;
        }}
        QTabBar::scroller {{
            background: transparent;
            width: 34px;
            margin-left: 4px;
        }}
        QTabBar QToolButton {{
            background: {bg_panel};
            border: 1px solid {bg_boton};
            border-radius: 8px;
            padding: 2px;
        }}
        QTabBar QToolButton:hover {{
            background: {accent_suave_solido};
            border-color: {accent};
        }}
        QTabBar QToolButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {accent}, stop:1 {accent_hover});
            border-color: {accent};
        }}
        QTabBar QToolButton:disabled {{
            background: {bg_panel};
            border-color: {bg_boton};
        }}
    """


#Contenedor de sección con aspecto de 'tarjeta' moderna: encabezado con
#icono + título (y descripción opcional), sombra suave que se eleva al pasar
#el mouse, y un layout interno (`contenido`) donde el código existente agrega
#sus widgets/formularios tal cual los tenía. Es solo un contenedor visual:
#no cambia qué controles existen ni cómo funcionan.
class TarjetaSeccion(QFrame):

    def __init__(self, icono="", titulo="", descripcion=None, parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaSeccion")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setBlurRadius(14)
        self._sombra.setOffset(0, 3)
        self._sombra.setColor(QColor(0, 0, 0, 50))
        self.setGraphicsEffect(self._sombra)

        raiz= QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 18)
        raiz.setSpacing(10)

        if titulo:
            fila_titulo= QHBoxLayout()
            fila_titulo.setSpacing(10)
            if icono:
                self.lbl_icono= QLabel()
                self.lbl_icono.setPixmap(pixmap_emoji(icono, 22))
                self.lbl_icono.setObjectName("TarjetaSeccionBadge")
                self.lbl_icono.setFixedSize(34, 34)
                self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
                fila_titulo.addWidget(self.lbl_icono)
            self.lbl_titulo= QLabel(titulo)
            self.lbl_titulo.setObjectName("TarjetaSeccionTitulo")
            fila_titulo.addWidget(self.lbl_titulo, 1)
            raiz.addLayout(fila_titulo)

        if descripcion:
            self.lbl_desc= QLabel(descripcion)
            self.lbl_desc.setObjectName("DescModulo")
            self.lbl_desc.setWordWrap(True)
            raiz.addWidget(self.lbl_desc)

        self.contenido= QVBoxLayout()
        self.contenido.setSpacing(10)
        raiz.addLayout(self.contenido)

    def aplicar_paleta(self, bg_panel, borde, txt_prim, txt_sec, accent, modo_oscuro):

        self.setStyleSheet(f"""
            QFrame#TarjetaSeccion {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-radius: 14px;
            }}
        """)
        if hasattr(self, "lbl_titulo"):
            self.lbl_titulo.setStyleSheet(
                f"color: {txt_prim}; font-size: 15px; font-weight: 700; background: transparent;")
        if hasattr(self, "lbl_icono"):
            alpha= 0.24 if modo_oscuro else 0.13
            self.lbl_icono.setStyleSheet(
                f"background-color: {_hex_a_rgba(accent, alpha)}; border-radius: 17px; "
                f"font-size: 15px; color: {accent};")

    def enterEvent(self, evento):

        self._animar_sombra(24)
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._animar_sombra(14)
        super().leaveEvent(evento)

    def _animar_sombra(self, destino):

        anim= QPropertyAnimation(self._sombra, b"blurRadius", self)
        anim.setDuration(220)
        anim.setStartValue(self._sombra.blurRadius())
        anim.setEndValue(destino)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

TIPOS_INSTITUCION= ["Escuela", "Politécnico", "Universidad", "Personalizado"]
DIVISIONES_PERIODO= ["Trimestres", "Cuatrimestres", "Semestres", "Bimestres", "Periodos"]
METODOS_CALCULO= ["Promedio Simple", "Promedio Ponderado", "Mayor Nota", "Suma de Puntos"]
IDIOMAS= ["Español", "Inglés", "Portugués"]
SISTEMA_DOMINICANO= "República Dominicana (P1-P4, Currículo por Competencias)"
SISTEMAS_CALIFICACION= ["Numérico (Personalizado)", "Estados Unidos (Letras A-F, GPA 4.0)", SISTEMA_DOMINICANO]

#Competencias Fundamentales del currículo dominicano (MINERD), usadas en el "Desempeño Individual del
#Estudiante" del Informe de Aprendizaje / Boletín.
COMPETENCIAS_FUNDAMENTALES_RD= [
    "Ética y Ciudadana",
    "Comunicativa",
    "Pensamiento Lógico, Creativo y Crítico",
    "Resolución de Problemas",
    "Científica y Tecnológica",
    "Ambiental y de la Salud",
    "Desarrollo Personal y Espiritual",
]
NOMBRES_PERIODOS_RD= ["P1", "P2", "P3", "P4"]


#Centra `dialogo` sobre su ventana padre (o sobre la pantalla si no hay
#padre visible) y se asegura de que aparezca POR ENCIMA de todas las demás
#ventanas de la app, aunque el usuario haya cambiado de ventana mientras
#tanto. Sin esto, en apps con varias ventanas los diálogos pueden abrirse
#"detrás" y el usuario tiene que buscarlos en la barra de tareas.
def _centrar_y_al_frente(dialogo, parent):

    dialogo.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    referencia= parent if (parent is not None and parent.isVisible()) else None
    if referencia is not None:
        geo_padre= referencia.frameGeometry()
        dialogo.adjustSize()
        pos_x= geo_padre.x() + (geo_padre.width() - dialogo.width()) // 2
        pos_y= geo_padre.y() + (geo_padre.height() - dialogo.height()) // 2
        dialogo.move(max(0, pos_x), max(0, pos_y))
    else:
        pantalla= dialogo.screen() if hasattr(dialogo, "screen") and dialogo.screen() else None
        if pantalla is not None:
            geo= pantalla.availableGeometry()
            dialogo.adjustSize()
            pos_x= geo.x() + (geo.width() - dialogo.width()) // 2
            pos_y= geo.y() + (geo.height() - dialogo.height()) // 2
            dialogo.move(max(0, pos_x), max(0, pos_y))
    dialogo.raise_()
    dialogo.activateWindow()


#Abre en el explorador de archivos del sistema la carpeta que contiene
#`ruta` (funciona tanto si `ruta` es un archivo como una carpeta).
def _abrir_carpeta_contenedora(ruta):

    carpeta= ruta if os.path.isdir(ruta) else os.path.dirname(ruta)
    if carpeta and os.path.isdir(carpeta):
        QDesktopServices.openUrl(QUrl.fromLocalFile(carpeta))


#Muestra un diálogo de éxito con la ruta guardada y un botón extra
#para abrir esa carpeta directamente, en vez de solo mostrar el texto.
def _preguntar_abrir_carpeta(parent, ruta, titulo, mensaje):

    caja= QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Information)
    caja.setWindowTitle(titulo)
    caja.setText(mensaje)
    btn_abrir= caja.addButton("Abrir Carpeta", QMessageBox.ButtonRole.ActionRole)
    caja.addButton("Cerrar", QMessageBox.ButtonRole.AcceptRole)
    _centrar_y_al_frente(caja, parent)
    caja.exec()
    if caja.clickedButton() is btn_abrir:
        _abrir_carpeta_contenedora(ruta)

#Niveles de desempeño de la evaluación cualitativa por Competencias Fundamentales (Ordenanza 04-2023, Sistema
#de Evaluación de los Aprendizajes, MINERD). "Sin Evaluar (NE)" es el estado inicial/neutro: NUNCA debe usarse
#como si fuera un nivel logrado, es solo un marcador de que el docente todavía no ha registrado ese renglón.
NIVEL_SIN_EVALUAR_RD= "Sin Evaluar (NE)"
NIVELES_DESEMPENO_RD= [NIVEL_SIN_EVALUAR_RD, "Destacado", "Logrado", "En Proceso", "Insuficiente"]

#Bandas numéricas oficiales de cada nivel (referencial, para mostrarlas como ayuda en pantalla).
BANDAS_DESEMPENO_RD= {
    "Destacado": (89, 100),
    "Logrado": (77, 88),
    "En Proceso": (65, 76),
    "Insuficiente": (0, 64),
}

#Colores de apoyo visual para distinguir cada nivel de un vistazo (evita que todas las filas se vean idénticas,
#que fue el problema reportado en la pantalla de Desempeño Individual).
COLORES_NIVEL_DESEMPENO_RD= {
    NIVEL_SIN_EVALUAR_RD: "#6B7280",   #gris - pendiente
    "Destacado": "#10B981",            #verde
    "Logrado": "#3B82F6",              #azul
    "En Proceso": "#F59E0B",           #ámbar
    "Insuficiente": "#EF4444",         #rojo
}


def es_sistema_dominicano(sistema):

    return sistema == SISTEMA_DOMINICANO


#Niveles educativos que distingue AcaDeXI para la nota mínima aprobatoria del Sistema Dominicano (Ordenanza
#04-2023, MINERD). Nivel Inicial/Preescolar queda deliberadamente fuera: no es una opción válida aquí y no
#tiene lógica propia en ningún módulo de la app.
NIVELES_EDUCATIVOS= ["Primaria", "Secundaria"]

#Piso/techo de la nota mínima aprobatoria por nivel, Sistema Dominicano (Ordenanza 04-2023, MINERD —
#confirmado: Primaria 65). Los spinboxes de Primaria/Secundaria (wizard y Configuración > Calificaciones) usan
#estos límites: al elegir el Sistema Dominicano se autocompletan con el piso de cada nivel, y no se puede
#escribir un valor fuera de [piso, techo]. Para Secundaria no hay techo normativo distinto del máximo de la
#escala, así que se deja abierto por arriba (solo con piso).
NOTA_MIN_PRIMARIA_PISO= 65
NOTA_MIN_PRIMARIA_TECHO= 70
NOTA_MIN_SECUNDARIA_PISO= 70
NOTA_MIN_SECUNDARIA_TECHO= 1000


#Lee `campo` de `fila` (sqlite3.Row o dict) tolerando que la columna no
#exista (bases de datos viejas ya migradas en memoria, tests, etc.).
def _valor_o_defecto(fila, campo, defecto=None):

    if fila is None:
        return defecto
    try:

        valor= fila[campo]
    except (IndexError, KeyError):
        return defecto
    return valor if valor is not None else defecto


#Nota mínima aprobatoria a usar, dada la fila `cfg` de `configuracion`
#(sqlite3.Row o dict con al menos nota_minima/nota_minima_primaria/
#nota_minima_secundaria/sistema_calificacion).
#
#- Si el sistema NO es el Dominicano: siempre `nota_minima` (comportamiento
#de siempre, sin cambios — Numérico Personalizado y Estados Unidos usan
#un único valor global).
#- Si el sistema SÍ es el Dominicano: usa `nota_minima_primaria` o
#`nota_minima_secundaria` según `nivel_educativo`. Si ese valor no está
#configurado (instalación recién migrada, o grado sin `nivel_educativo`
#clasificado, o `nivel_educativo` None/desconocido) cae de vuelta a
#`nota_minima` para no dejar nunca un cálculo sin nota mínima.
def resolver_nota_minima(cfg, sistema=None, nivel_educativo=None):

    sistema= sistema if sistema is not None else _valor_o_defecto(cfg, "sistema_calificacion", "")
    generica= _valor_o_defecto(cfg, "nota_minima", 70)
    if not es_sistema_dominicano(sistema):
        return generica
    if nivel_educativo == "Primaria":
        return _valor_o_defecto(cfg, "nota_minima_primaria", generica)
    if nivel_educativo == "Secundaria":
        return _valor_o_defecto(cfg, "nota_minima_secundaria", generica)
    return generica


#Muestra u oculta, en un QFormLayout, la fila (etiqueta + campo) de
#`campo_widget`. Usado para alternar entre "Nota Mínima Aprobatoria" (un
#solo campo) y sus dos variantes por nivel (Primaria/Secundaria) según el
#Sistema de Calificación elegido, sin reconstruir el formulario.
def _alternar_fila_form(form, campo_widget, visible):

    campo_widget.setVisible(visible)
    etiqueta= form.labelForField(campo_widget)
    if etiqueta is not None:
        etiqueta.setVisible(visible)


#Nivel académico transversal (Primaria / Secundaria / Preparatoria / Universidad) — dimensión académica
#reutilizada por TODOS los módulos que trabajan con estudiantes, cursos, secciones o carreras. Única lógica
#coherente: qué niveles existen (NIVELES_ACADEMICOS), qué niveles ofrece ESTA institución
#(niveles_academicos_habilitados), y si algo (típicamente, componente técnico) es válido para un nivel/ciclo
#dado (puede_tener_componente_tecnico). Todo lo demás (filtros de Estudiantes, combos de Materias/Politécnico,
#Buscador global, etc.) debe llamar a estas funciones en vez de repetir la regla por su cuenta.
NIVELES_ACADEMICOS= ["Primaria", "Secundaria", "Preparatoria", "Universidad"]

#Dentro de Secundaria, República Dominicana distingue dos ciclos; el segundo es el único que puede tener
#modalidad técnico-profesional. Esto vive como constante separada (no mezclada en NIVELES_ACADEMICOS) porque es
#una subdivisión de UN nivel, no un nivel más -así el resto del sistema (fuera de este archivo y de
#materias.py/calificaciones_tecnicas.py) puede seguir pensando en 4 niveles simples sin tener que conocer el
#ciclo.
CICLOS_SECUNDARIA= ["Primer Ciclo", "Segundo Ciclo"]


#Niveles que ESTA institución realmente ofrece, según su
#tipo_institucion (reutiliza el mismo patrón que ya usaba
#`modulos_personalizados` para decidir si Politécnico/Universidad están
#activos dentro de 'Personalizado' — ver _actualizar_visibilidad_modulos_personalizados).
#
#- Universidad     -> siempre y solo ['Universidad'] (se deduce del tipo,
#no hace falta que nadie lo configure a mano).
#- Politécnico     -> siempre y solo ['Secundaria'] (un Politécnico
#dominicano trabaja el nivel Secundaria con modalidad técnica en 2do
#ciclo -ver puede_tener_componente_tecnico).
#- Escuela         -> lo que la institución haya marcado en
#`niveles_educativos_habilitados` (Configuración > Académico), sin
#incluir nunca 'Universidad' (una Escuela no matricula por Carrera).
#Si todavía no ha configurado nada (instalación recién migrada), el
#valor por defecto es ['Primaria', 'Secundaria'] -el comportamiento de
#siempre, para no romper nada retroactivamente.
#- Personalizado   -> totalmente flexible: exactamente lo que la
#institución haya marcado, SIN ninguna restricción adicional
#hardcodeada aquí (puede incluir Universidad si así lo decide, igual
#que ya puede activar el módulo Universidad vía `modulos_personalizados`).
#Si no ha configurado nada todavía, no se asume ningún nivel -evita que
#un Personalizado recién creado "adivine" un valor que no pidió.
def niveles_academicos_habilitados(cfg):

    tipo= _valor_o_defecto(cfg, "tipo_institucion", "Escuela")
    dominicano= es_sistema_dominicano(_valor_o_defecto(cfg, "sistema_calificacion", ""))
    guardados= [n for n in (_valor_o_defecto(cfg, "niveles_educativos_habilitados", "") or "").split(",")
                 if n in NIVELES_ACADEMICOS]
    if dominicano:
        #Con el Sistema Dominicano, "Preparatoria" no es un nivel aparte: es el Segundo Ciclo de Secundaria (ver
        #CICLOS_SECUNDARIA). Se filtra aquí también -no solo en la UI de Configuración- para que ningún otro punto del
        #sistema (filtros, validaciones, etc.) pueda llegar a ofrecerlo por una vía distinta a la pantalla de
        #Configuración.
        guardados= [guardado for guardado in guardados if guardado != "Preparatoria"]
    if tipo == "Universidad":
        return ["Universidad"]
    if tipo == "Politécnico":
        return ["Secundaria"]
    if tipo == "Personalizado":
        return guardados
    #Escuela (o cualquier tipo desconocido/futuro): igual que Escuela.
    return guardados or ["Primaria", "Secundaria"]


#True si es académicamente válido asignarle a este nivel/ciclo algo
#del componente técnico-profesional (área técnica/especialidad,
#materias con modelo_evaluacion='Técnica (RA)', Calificaciones Técnicas).
#
#Reglas:
#- Universidad NUNCA (el componente técnico-profesional del Politécnico
#es un concepto de Secundaria, no de educación superior).
#- Primaria/Preparatoria NUNCA.
#- Secundaria: solo Segundo Ciclo. Un grado de Secundaria sin `ciclo`
#todavía clasificado (instalación existente, o institución que no usa
#Politécnico) se trata como válido -no se bloquea retroactivamente a
#nadie; es responsabilidad de la institución clasificar sus grados de
#Secundaria por ciclo (Materias > Secciones) para que la restricción
#de Primer Ciclo empiece a aplicar.
#- Si la institución ni siquiera tiene el componente técnico activo
#(no es 'Politécnico' y, siendo 'Personalizado', no marcó el módulo
#Politécnico), tampoco es válido sin importar el nivel/ciclo -eso ya
#lo decide `modulos_personalizados`/tipo_institucion en otros lados;
#esta función solo añade la restricción de nivel/ciclo encima.
def puede_tener_componente_tecnico(nivel, ciclo, tipo_institucion):

    if nivel != "Secundaria":
        return False
    return ciclo != "Primer Ciclo"


#Set de `secciones.id` cuyo Grado es académicamente elegible para
#componente técnico-profesional (Secundaria, no-Primer-Ciclo — ver
#puede_tener_componente_tecnico). Pensado para pasarse como
#`secciones_permitidas` a poblar_combo_curso/cascada_seccion_por_curso
#(filtros_curso_seccion.py) en las pantallas de Politécnico, reutilizando
#el mismo mecanismo de filtrado que ya usa el RBAC de Profesor -así el
#combo de Curso/Sección de una asignación técnica no ofrece, de entrada,
#cursos que no pueden tener nada técnico.
def secciones_con_componente_tecnico_valido():

    from src.nucleo.bd import obtener_conexion
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT secciones.id as id, grados.nivel_educativo as nivel, grados.ciclo_secundaria as ciclo "
              "FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id")
    ids= {fila["id"] for fila in c.fetchall() if puede_tener_componente_tecnico(fila["nivel"], fila["ciclo"], None)}
    conn.close()
    return ids


def anio_academico_actual():

    ahora= datetime.now()
    if ahora.month >= 8:
        return f"{ahora.year}-{ahora.year + 1}"
    return f"{ahora.year - 1}-{ahora.year}"


def _escala_y_minima_por_sistema(sistema):

    if sistema == "Estados Unidos (Letras A-F, GPA 4.0)":
        return 100, 60
    if sistema == SISTEMA_DOMINICANO:
        return 100, 70
    return None, None


#Indicador de progreso del wizard (stepper dibujado a mano)
#Indicador de progreso del asistente: una línea con un círculo
#numerado por paso, que se rellena de color de acento a medida que se
#avanza y marca con un check los pasos ya completados. Reemplaza la
#barra de progreso plana + el contador de texto que había antes -de un
#vistazo se ve cuánto falta y hacia dónde se puede volver, sin tener que
#leer "Paso 3 / 7".
#
#Se dibuja a mano con QPainter usando solo primitivas simples (líneas,
#círculos, texto) -sin pixmaps ni efectos de por medio-, así que
#repintar en cada fotograma de la animación de avance (ver `ir_a`) es
#prácticamente gratis, incluso en equipos modestos.
class WizardStepper(QWidget):

    def __init__(self, total_pasos, parent=None):

        super().__init__(parent)
        self._total= max(total_pasos, 1)
        self._indice_actual= 0
        self._progreso_visual= 0.0
        self.setFixedHeight(30)
        self.setMinimumWidth(220)
        self._color_accent= "#2563EB"
        self._color_muted= "#CBD5E1"
        self._color_fondo_circulo= "#FFFFFF"
        self._color_texto_muted= "#94A3B8"
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_valor_animado)

    def establecer_colores(self, accent, muted, fondo_circulo, texto_muted):

        self._color_accent= accent
        self._color_muted= muted
        self._color_fondo_circulo= fondo_circulo
        self._color_texto_muted= texto_muted
        self.update()

    def _al_valor_animado(self, valor):

        self._progreso_visual= valor
        self.update()

    #Anima la línea/círculos hasta `indice` (0-based). Segura de
    #llamar aunque el widget aún no se haya pintado ni una vez.
    def ir_a(self, indice):

        indice= max(0, min(indice, self._total - 1))
        self._anim.stop()
        self._anim.setStartValue(float(self._progreso_visual))
        self._anim.setEndValue(float(indice))
        self._indice_actual= indice
        self._anim.start()

    def paintEvent(self, evento):

        if self._total < 2:
            return
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radio= 9.0
        margen= radio + 3
        pos_y= self.height() / 2
        ancho_util= max(1.0, self.width() - margen * 2)
        paso_x= ancho_util / (self._total - 1)

        pen_base= QPen(QColor(self._color_muted), 2.4)
        pen_base.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_base)
        painter.drawLine(QPointF(margen, pos_y), QPointF(margen + ancho_util, pos_y))

        progreso_x= margen + paso_x * min(self._progreso_visual, self._total - 1)
        pen_progreso= QPen(QColor(self._color_accent), 2.4)
        pen_progreso.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_progreso)
        painter.drawLine(QPointF(margen, pos_y), QPointF(progreso_x, pos_y))

        fuente= painter.font()
        fuente.setPixelSize(10)
        fuente.setBold(True)
        painter.setFont(fuente)

        for i in range(self._total):
            cx= margen + paso_x * i
            completado= i < self._indice_actual
            actual= i == self._indice_actual
            if completado:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(self._color_accent))
                painter.drawEllipse(QPointF(cx, pos_y), radio, radio)
                pluma= QPen(QColor("#FFFFFF"), 1.8)
                pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
                pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pluma)
                painter.drawLine(QPointF(cx - 3.2, pos_y + 0.3), QPointF(cx - 0.7, pos_y + 2.8))
                painter.drawLine(QPointF(cx - 0.7, pos_y + 2.8), QPointF(cx + 3.8, pos_y - 3.2))
            elif actual:
                halo= QColor(self._color_accent)
                halo.setAlpha(45)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                painter.drawEllipse(QPointF(cx, pos_y), radio + 5, radio + 5)
                painter.setPen(QPen(QColor(self._color_accent), 2.2))
                painter.setBrush(QColor(self._color_fondo_circulo))
                painter.drawEllipse(QPointF(cx, pos_y), radio, radio)
                painter.setPen(QColor(self._color_accent))
                painter.drawText(QRectF(cx - radio, pos_y - radio, radio * 2, radio * 2),
                                  Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                painter.setPen(QPen(QColor(self._color_muted), 1.6))
                painter.setBrush(QColor(self._color_fondo_circulo))
                painter.drawEllipse(QPointF(cx, pos_y), radio, radio)
                painter.setPen(QColor(self._color_texto_muted))
                painter.drawText(QRectF(cx - radio, pos_y - radio, radio * 2, radio * 2),
                                  Qt.AlignmentFlag.AlignCenter, str(i + 1))


#Wizard de configuración inicial (8 PASOS)
class WizardConfiguracion(QDialog):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.setWindowTitle("Asistente de Configuración Inicial - AcaDeXI")
        aplicar_icono_ventana(self, ICONO_SETUP)
        self.setMinimumSize(760, 620)
        self.logo_path= ""
        self._construir_ui()
        self._aplicar_tema()
        centrar_y_al_frente(self, main_window)

    def _construir_ui(self):

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(0, 0, 0, 0)
        disposicion.setSpacing(0)

        header= QFrame()
        header.setObjectName("WizardHeader")
        header.setFixedHeight(104)
        header_v= QVBoxLayout(header)
        header_v.setContentsMargins(34, 16, 34, 16)
        header_v.setSpacing(12)

        h_layout= QHBoxLayout()
        h_layout.setSpacing(12)
        self.lbl_badge_paso= QLabel()
        self.lbl_badge_paso.setPixmap(pixmap_emoji("🧭", 20))
        self.lbl_badge_paso.setObjectName("WizardBadgePaso")
        self.lbl_badge_paso.setFixedSize(38, 38)
        self.lbl_badge_paso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(self.lbl_badge_paso)
        self.lbl_paso= QLabel("Bienvenida")
        self.lbl_paso.setObjectName("WizardPasoLabel")
        h_layout.addWidget(self.lbl_paso)
        h_layout.addStretch()
        self.lbl_contador= QLabel("Paso 1 de 8")
        self.lbl_contador.setObjectName("WizardContador")
        h_layout.addWidget(self.lbl_contador)
        header_v.addLayout(h_layout)

        self.stepper= WizardStepper(8)
        header_v.addWidget(self.stepper)
        disposicion.addWidget(header)

        #Contenedor con margen alrededor del stack: dentro se ve la tarjeta elevada de cada paso (ver _nueva_pagina)
        #"flotando" sobre el fondo del diálogo, en vez de pegada borde a borde como antes.
        contenedor_stack= QWidget()
        contenedor_stack.setObjectName("WizardStackContenedor")
        contenedor_stack_layout= QVBoxLayout(contenedor_stack)
        contenedor_stack_layout.setContentsMargins(26, 20, 26, 10)
        self.stack= QStackedWidget()
        contenedor_stack_layout.addWidget(self.stack)
        disposicion.addWidget(contenedor_stack, 1)

        self._crear_paso_bienvenida()
        self._crear_paso1_institucion()
        self._crear_paso2_logo()
        self._crear_paso3_tipo()
        self._crear_paso4_calificaciones()
        self._crear_paso5_periodo()
        self._crear_paso6_admin()
        self._crear_paso7_final()

        pie= QFrame()
        pie.setObjectName("WizardPie")
        pie.setFixedHeight(68)
        pie_layout= QHBoxLayout(pie)
        pie_layout.setContentsMargins(30, 0, 30, 0)
        self.btn_atras= QPushButton("Atrás")
        self.btn_atras.setIcon(icono_emoji("⬅"))
        self.btn_atras.setIconSize(_QSize_emoji(16, 16))
        self.btn_atras.setObjectName("BtnAccionNeutro")
        self.btn_atras.clicked.connect(self._anterior)
        pie_layout.addWidget(self.btn_atras)
        pie_layout.addStretch()
        self.btn_siguiente= QPushButton("Siguiente ")
        self.btn_siguiente.setIcon(icono_emoji("➡"))
        self.btn_siguiente.setIconSize(_QSize_emoji(16, 16))
        self.btn_siguiente.clicked.connect(self._siguiente)
        pie_layout.addWidget(self.btn_siguiente)
        disposicion.addWidget(pie)

        self.stack.currentChanged.connect(self._actualizar_encabezado)
        self._actualizar_encabezado(0)
        #Fundido de entrada solo para la primera página al abrir el asistente; los cambios de página posteriores usan
        #la transición direccional de
        #_ir_a_paso (más barata: solo anima la página entrante).
        _fundido_entrada(self.stack.currentWidget())

        #Realce (sombra que se eleva) al pasar el mouse sobre los botones del asistente.
        self._realce_wizard= _RealceHover(0, 18, 5, self)
        for boton in self.findChildren(QPushButton):
            boton.installEventFilter(self._realce_wizard)

    def _titulos(self):

        return ["Bienvenida", "Datos de la Institución", "Logotipo", "Tipo de Institución",
                "Sistema de Calificaciones", "Periodo Académico", "Usuario Administrador", "Finalización"]

    def _iconos_pasos(self):

        return ["👋", "🏛", "🖼", "🏫", "📊", "🗓", "👤", "🏁"]

    def _actualizar_encabezado(self, indice):

        titulos= self._titulos()
        iconos= self._iconos_pasos()
        self.lbl_paso.setText(titulos[indice])
        self.lbl_badge_paso.setPixmap(pixmap_emoji(iconos[indice] if indice < len(iconos) else "🧭", 20))
        self.lbl_contador.setText(f"Paso {indice + 1} de {len(titulos)}")
        self.btn_atras.setEnabled(indice > 0)
        ultimo= indice == len(titulos) - 1
        self.btn_siguiente.setText("Finalizar " if ultimo else "Siguiente ")
        self.btn_siguiente.setIcon(icono_emoji("🏁" if ultimo else "➡"))
        self.btn_siguiente.setIconSize(_QSize_emoji(16, 16))
        self.stepper.ir_a(indice)

    def _crear_paso_bienvenida(self):

        w, l= self._nueva_pagina()
        l.addStretch()
        lbl_hero= QLabel()
        lbl_hero.setPixmap(pixmap_emoji("👋", 64))
        lbl_hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_hero)
        lbl_titulo= QLabel("Bienvenido a AcaDeXI")
        lbl_titulo.setObjectName("WizardTitulo")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_titulo)
        lbl_desc= QLabel("Este asistente te guiará en 7 pasos para configurar la identidad institucional, "
                      "el tipo de centro educativo, la escala de evaluación, el año académico y las "
                      "credenciales del Director. Al finalizar, AcaDeXI generará automáticamente la "
                      "estructura de la base de datos.")
        lbl_desc.setObjectName("WizardDesc")
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_desc)
        l.addSpacing(18)

        linea= QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        l.addWidget(linea)
        l.addSpacing(10)

        lbl_aviso_docente= QLabel("¿Eres Docente/Personal y tu Administrador/Director ya te entregó tu "
                               "archivo de Perfil Institucional (.acdx)? No necesitas completar este "
                               "asistente — impórtalo directamente y quedas listo.")
        lbl_aviso_docente.setObjectName("WizardDesc")
        lbl_aviso_docente.setWordWrap(True)
        lbl_aviso_docente.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_aviso_docente)
        fila_importar= QHBoxLayout()
        fila_importar.addStretch()
        btn_importar= QPushButton("Importar Perfil Institucional (.acdx)")
        btn_importar.setIcon(icono_emoji("\uE001"))
        btn_importar.setIconSize(_QSize_emoji(16, 16))
        btn_importar.setObjectName("BtnAccionAjustar")
        btn_importar.clicked.connect(self._importar_perfil_desde_wizard)
        fila_importar.addWidget(btn_importar)
        fila_importar.addStretch()
        l.addLayout(fila_importar)

        l.addStretch()
        self.stack.addWidget(w)

    #Permite a un Docente/Personal saltarse por completo este asistente
    #importando el .acdx que le entregó su Administrador/Director (el mismo
    #botón que existe en el login, pero disponible ANTES del wizard, ya que
    #antes el wizard bloqueaba la app entera sin dejar llegar al login —
    #incluso en instalaciones hechas con el instalador de Docentes/Personal,
    #donde el wizard nunca debería aparecer).
    def _importar_perfil_desde_wizard(self):

        from src.interfaz.perfil import (leer_perfil_archivo, aplicar_perfil, EXTENSION,
                            perfil_incluye_bd_base, local_ya_tiene_usuarios, aplicar_bd_base)
        ruta, _= QFileDialog.getOpenFileName(
            self, "Importar Perfil Institucional", "", f"Perfil AcaDeXI (*{EXTENSION})")
        if not ruta:
            return
        try:

            datos= leer_perfil_archivo(ruta)
        except Exception as error:
            mostrar_mensaje("error", "Perfil inválido", str(error), self)
            return

        if not perfil_incluye_bd_base(datos):
            mostrar_mensaje("advertencia", "Este perfil no trae la BD Base",
                "Este archivo .acdx no incluye la Base de Datos Institucional Base, así que no basta "
                "para saltar este asistente (no trae la estructura de tu institución).\n\n"
                "Pide a tu Administrador/Director que lo genere marcando 'Incluir la BD Base "
                "Institucional en este perfil'. Si tú eres quien configura la institución por primera "
                "vez, completa este asistente normalmente con 'Siguiente '.", self)
            return

        if local_ya_tiene_usuarios():
            if mostrar_mensaje("pregunta", "Reemplazar base de datos local",
                "Este equipo ya tiene datos guardados localmente. ¿Deseas reemplazarlos por la Base de "
                "Datos Institucional que trae este perfil? Se hará un respaldo de la actual antes de "
                "reemplazarla.", self) != QMessageBox.StandardButton.Yes:
                return
        try:

            aplicar_bd_base(datos)
        except Exception as error:
            mostrar_mensaje("error", "Error",
                            f"No se pudo aplicar la base de datos incluida en el perfil:\n{error}", self)
            return
        aplicar_perfil(self.main_window, datos)
        mostrar_mensaje("exito", "Perfil importado",
            "Tu perfil institucional se importó correctamente. A continuación verás la pantalla de "
            "inicio de sesión: entra con tu usuario y tu contraseña.", self)
        self.accept()

    def _crear_paso1_institucion(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Datos de la Institución"))
        form= QFormLayout()
        form.setSpacing(12)
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre, 300)
        self.in_direccion= QLineEdit()
        limitar_campo_texto(self.in_direccion, 300)
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono, 300)
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo, 200)
        self.in_sitio_web= QLineEdit()
        limitar_campo_texto(self.in_sitio_web, 200)
        form.addRow("Nombre de la Institución:", self.in_nombre)
        form.addRow("Dirección:", self.in_direccion)
        form.addRow("Teléfono:", self.in_telefono)
        form.addRow("Correo Institucional:", self.in_correo)
        form.addRow("Sitio Web:", self.in_sitio_web)
        l.addLayout(form)
        l.addStretch()
        self.stack.addWidget(w)

    def _crear_paso2_logo(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Selección de Logotipo"))
        l.addWidget(QLabel("Carga la imagen oficial del centro educativo. Se usará en reportes y en el login."))
        self.lbl_preview_logo= QLabel("Sin logotipo seleccionado")
        self.lbl_preview_logo.setFixedSize(160, 160)
        self.lbl_preview_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_logo.setObjectName("PreviewLogo")
        fila= QHBoxLayout()
        fila.addStretch()
        fila.addWidget(self.lbl_preview_logo)
        fila.addStretch()
        l.addLayout(fila)
        btn= QPushButton("Cargar Logotipo")
        btn.setIcon(icono_emoji("📂"))
        btn.setIconSize(_QSize_emoji(16, 16))
        btn.clicked.connect(self._elegir_logo)
        fila2= QHBoxLayout()
        fila2.addStretch()
        fila2.addWidget(btn)
        fila2.addStretch()
        l.addLayout(fila2)
        l.addStretch()
        self.stack.addWidget(w)

    def _elegir_logo(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "logos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="logo")
        if not destino:
            return
        self.logo_path= destino
        pixmap= QPixmap(destino).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
        self.lbl_preview_logo.setPixmap(pixmap)

    def _crear_paso3_tipo(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Tipo de Institución"))
        l.addWidget(QLabel("Selecciona la modalidad institucional. AcaDeXI adaptará sus módulos automáticamente."))
        self.combo_tipo= QComboBox()
        self.combo_tipo.addItems(TIPOS_INSTITUCION)
        conectar_tooltip_seleccion(self.combo_tipo, "Tipo de institución (adapta los módulos disponibles)")
        l.addWidget(self.combo_tipo)
        self.lbl_info_tipo= QLabel()
        self.lbl_info_tipo.setWordWrap(True)
        self.lbl_info_tipo.setObjectName("WizardDesc")
        l.addWidget(self.lbl_info_tipo)
        self.combo_tipo.currentTextChanged.connect(self._actualizar_info_tipo)
        self._actualizar_info_tipo(self.combo_tipo.currentText())
        l.addStretch()
        self.stack.addWidget(w)

    def _actualizar_info_tipo(self, tipo):

        info= {
            "Escuela": "Activa: Estudiantes, Profesores, Materias, Asistencia, Calificaciones Estándar y Boletines.",
            "Politécnico": "Activa además: Especialidades Técnicas, Talleres/Laboratorios, Empresas de Pasantía y Registro de Horas Prácticas.",
            "Universidad": "Activa además: Facultades, Carreras, Créditos Académicos, Pensum, Prerrequisitos y Materias Electivas.",
            "Personalizado": "Podrás activar o desactivar manualmente cualquier módulo técnico o universitario desde Configuración.",
        }
        self.lbl_info_tipo.setText(info.get(tipo, ""))

    def _crear_paso4_calificaciones(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Sistema de Calificaciones"))
        form= QFormLayout()
        form.setSpacing(12)
        self.combo_sistema_calificacion= QComboBox()
        self.combo_sistema_calificacion.addItems(SISTEMAS_CALIFICACION)
        conectar_tooltip_seleccion(self.combo_sistema_calificacion,
                                    "Escala y método con el que se calculan e interpretan las notas")
        self.spin_escala= QDoubleSpinBox()
        self.spin_escala.setRange(1, 1000)
        self.spin_escala.setValue(100)
        self.spin_nota_min= QDoubleSpinBox()
        self.spin_nota_min.setRange(0, 1000)
        self.spin_nota_min.setValue(70)
        self.spin_nota_min_primaria= QDoubleSpinBox()
        self.spin_nota_min_primaria.setRange(NOTA_MIN_PRIMARIA_PISO, NOTA_MIN_PRIMARIA_TECHO)
        self.spin_nota_min_primaria.setValue(NOTA_MIN_PRIMARIA_PISO)
        self.spin_nota_min_primaria.setToolTip(
            f"Mínimo {NOTA_MIN_PRIMARIA_PISO}, puedes subirlo hasta {NOTA_MIN_PRIMARIA_TECHO}.")
        self.spin_nota_min_secundaria= QDoubleSpinBox()
        self.spin_nota_min_secundaria.setRange(NOTA_MIN_SECUNDARIA_PISO, NOTA_MIN_SECUNDARIA_TECHO)
        self.spin_nota_min_secundaria.setValue(NOTA_MIN_SECUNDARIA_PISO)
        self.combo_metodo= QComboBox()
        self.combo_metodo.addItems(METODOS_CALCULO)
        conectar_tooltip_seleccion(self.combo_metodo, "Fórmula usada para calcular la nota final de una materia")
        form.addRow("Sistema de Calificación:", self.combo_sistema_calificacion)
        form.addRow("Escala Máxima (ej. 10, 20, 100):", self.spin_escala)
        form.addRow("Nota Mínima Aprobatoria:", self.spin_nota_min)
        form.addRow("Nota Mínima Aprobatoria — Primaria:", self.spin_nota_min_primaria)
        form.addRow("Nota Mínima Aprobatoria — Secundaria:", self.spin_nota_min_secundaria)
        form.addRow("Método de Cálculo de Nota Final:", self.combo_metodo)
        self.form_calificaciones= form
        l.addLayout(form)
        self.lbl_info_sistema= QLabel()
        self.lbl_info_sistema.setWordWrap(True)
        self.lbl_info_sistema.setObjectName("WizardDesc")
        l.addWidget(self.lbl_info_sistema)
        self.combo_sistema_calificacion.currentTextChanged.connect(self._sync_sistema_calificacion)
        self.combo_sistema_calificacion.currentTextChanged.connect(self._sync_periodo_por_sistema)
        #A diferencia de _sync_sistema_calificacion (que solo muestra/oculta y habilita/deshabilita), esto SOLO se
        #dispara cuando el usuario elige una opción con el mouse/teclado (QComboBox.activated), nunca cuando el combo
        #cambia por código (p. ej. al cargar una configuración guardada más adelante) — así el autocompletado a 65/70
        #no pisa un valor ya guardado, solo aplica quien de verdad está cambiando el sistema ahora.
        self.combo_sistema_calificacion.activated.connect(self._restablecer_nota_min_nivel_defecto)
        self._sync_sistema_calificacion(self.combo_sistema_calificacion.currentText())
        l.addStretch()
        self.stack.addWidget(w)

    #Autocompleta Primaria/Secundaria con su piso normativo (65/70) cuando
    #el usuario ELIGE el Sistema Dominicano — nunca al cargar un valor ya
    #guardado (ver el comentario junto a la conexión de `activated`).
    def _restablecer_nota_min_nivel_defecto(self, *_):

        if self.combo_sistema_calificacion.currentText() != SISTEMA_DOMINICANO:
            return
        self.spin_nota_min_primaria.setValue(NOTA_MIN_PRIMARIA_PISO)
        self.spin_nota_min_secundaria.setValue(NOTA_MIN_SECUNDARIA_PISO)

    def _sync_sistema_calificacion(self, sistema):

        escala, minima= _escala_y_minima_por_sistema(sistema)
        dominicano= sistema == SISTEMA_DOMINICANO
        #En el Sistema Dominicano, la nota mínima aprobatoria varía entre Primaria y Secundaria (Ordenanza 04-2023,
        #MINERD): se ocultan el campo único y se muestran los dos campos por nivel en su lugar. Para cualquier otro
        #sistema se mantiene el campo único de siempre.
        _alternar_fila_form(self.form_calificaciones, self.spin_nota_min, not dominicano)
        _alternar_fila_form(self.form_calificaciones, self.spin_nota_min_primaria, dominicano)
        _alternar_fila_form(self.form_calificaciones, self.spin_nota_min_secundaria, dominicano)
        if escala is not None:
            self.spin_escala.setValue(escala)
            self.spin_escala.setEnabled(False)
            if dominicano:
                #A diferencia de la escala (fija en 0-100), la nota mínima por nivel SÍ queda editable: Primaria se
                #autocompleta en 65 (piso normativo, Ordenanza 04-2023) y admite subirse hasta 70; Secundaria se autocompleta
                #en 70 y no tiene techo normativo distinto del máximo de la escala. Ver
                #_restablecer_nota_min_nivel_defecto (solo aplica al elegir el
                #sistema con el mouse/teclado, no al cargar un valor guardado).
                self.spin_nota_min.setEnabled(False)
                self.lbl_info_sistema.setText(
                    f"Escala fija 0-100, 4 Períodos (P1-P4). Nota mínima: Primaria "
                    f"{NOTA_MIN_PRIMARIA_PISO} (hasta {NOTA_MIN_PRIMARIA_TECHO}), Secundaria "
                    f"{NOTA_MIN_SECUNDARIA_PISO}. Por debajo del mínimo activa Recuperación Pedagógica.")
            else:
                self.spin_nota_min.setValue(minima)
                self.spin_nota_min.setEnabled(False)
                self.lbl_info_sistema.setText(
                    "Sistema de Estados Unidos: escala fija 0-100 (equivalente porcentual de las letras "
                    "A-F) y nota mínima aprobatoria de 60 (D-). Los boletines mostrarán la letra "
                    "correspondiente junto a la nota numérica.")
        else:
            self.spin_escala.setEnabled(True)
            self.spin_nota_min.setEnabled(True)
            self.lbl_info_sistema.setText(
                "Sistema numérico personalizado: define libremente la escala máxima y la nota "
                "mínima aprobatoria (ej. 0-10, 0-20, 0-100).")

    def _sync_periodo_por_sistema(self, sistema):

        if not hasattr(self, "combo_division"):
            return
        if es_sistema_dominicano(sistema):
            self.combo_division.setCurrentText("Periodos")
            self.spin_cantidad.setValue(4)
            self.combo_division.setEnabled(False)
            self.spin_cantidad.setEnabled(False)
        else:
            self.combo_division.setEnabled(True)
            self.spin_cantidad.setEnabled(True)

    def _crear_paso5_periodo(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Periodo Académico"))
        form= QFormLayout()
        form.setSpacing(12)
        self.in_anio= QLineEdit(anio_academico_actual())
        limitar_campo_texto(self.in_anio, 300)
        self.in_anio.setToolTip("Se ajusta automáticamente según la fecha del sistema; puedes editarlo si lo necesitas.")
        self.combo_division= QComboBox()
        self.combo_division.addItems(DIVISIONES_PERIODO)
        conectar_tooltip_seleccion(self.combo_division, "Cómo se divide el año académico (trimestres, semestres, etc.)")
        self.spin_cantidad= QSpinBox()
        self.spin_cantidad.setRange(1, 12)
        self.spin_cantidad.setValue(3)
        form.addRow("Año Académico:", self.in_anio)
        form.addRow("División Periódica:", self.combo_division)
        form.addRow("Cantidad de Periodos:", self.spin_cantidad)
        l.addLayout(form)
        l.addStretch()
        self.stack.addWidget(w)

    def _crear_paso6_admin(self):

        w, l= self._nueva_pagina()
        l.addWidget(self._titulo_paso("Crear Usuario Administrador"))
        fila_seguridad= QHBoxLayout()
        fila_seguridad.setSpacing(6)
        lbl_icono_seguridad= QLabel()
        lbl_icono_seguridad.setPixmap(pixmap_emoji("🔒", 14))
        fila_seguridad.addWidget(lbl_icono_seguridad)
        lbl_seguridad= QLabel("Estas credenciales se protegen con hash seguro Argon2id.")
        lbl_seguridad.setObjectName("WizardDesc")
        fila_seguridad.addWidget(lbl_seguridad)
        fila_seguridad.addStretch()
        l.addLayout(fila_seguridad)
        form= QFormLayout()
        form.setSpacing(12)
        self.in_admin_nombre= QLineEdit()
        limitar_campo_texto(self.in_admin_nombre, 300)
        self.in_admin_user= QLineEdit()
        limitar_campo_texto(self.in_admin_user, 300)
        self.in_admin_pass= QLineEdit()
        limitar_campo_texto(self.in_admin_pass, 128)
        self.in_admin_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_admin_pass2= QLineEdit()
        limitar_campo_texto(self.in_admin_pass2, 128)
        self.in_admin_pass2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Nombre completo del Director:", self.in_admin_nombre)
        form.addRow("Usuario:", self.in_admin_user)
        form.addRow("Contraseña:", self.in_admin_pass)
        form.addRow("Confirmar Contraseña:", self.in_admin_pass2)
        l.addLayout(form)
        l.addStretch()
        self.stack.addWidget(w)

    def _crear_paso7_final(self):

        w, l= self._nueva_pagina()
        l.addStretch()
        lbl_hero= QLabel()
        lbl_hero.setPixmap(pixmap_emoji("🏁", 64))
        lbl_hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_hero)
        lbl_titulo= QLabel("Todo Listo")
        lbl_titulo.setObjectName("WizardTitulo")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_titulo)
        lbl_desc= QLabel("AcaDeXI generará el esquema de datos de la institución y desplegará el panel principal. "
                      "Presiona Finalizar para continuar.")
        lbl_desc.setObjectName("WizardDesc")
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl_desc)
        l.addStretch()
        self.stack.addWidget(w)

    def _titulo_paso(self, texto):

        lbl= QLabel(texto)
        lbl.setObjectName("WizardSubtitulo")
        return lbl

    #Crea el contenedor de una página del asistente: una tarjeta
    #elevada (bordes redondeados, sombra suave) centrada dentro del área
    #de contenido, con el fondo del diálogo asomando alrededor -el mismo
    #efecto de "tarjeta flotante" que ya usan otras ventanas de la app.
    #Devuelve (contenedor, layout_interno); cada _crear_pasoN sigue
    #llenando su formulario igual que antes, solo cambia el punto de
    #partida (antes era un QWidget liso con márgenes grandes).
    def _nueva_pagina(self):

        contenedor= QWidget()
        externo= QVBoxLayout(contenedor)
        externo.setContentsMargins(0, 0, 0, 0)
        tarjeta= QFrame()
        tarjeta.setObjectName("WizardCard")
        tarjeta.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sombra= QGraphicsDropShadowEffect(tarjeta)
        sombra.setColor(QColor(0, 0, 0, 55))
        sombra.setOffset(0, 3)
        sombra.setBlurRadius(24)
        tarjeta.setGraphicsEffect(sombra)
        externo.addWidget(tarjeta)
        disposicion= QVBoxLayout(tarjeta)
        disposicion.setContentsMargins(46, 36, 46, 32)
        disposicion.setSpacing(12)
        return contenedor, disposicion

    #Cambia de página con una transición corta de deslizamiento +
    #fundido (~220ms), en el sentido del avance -desde la derecha al
    #pulsar 'Siguiente', desde la izquierda al pulsar 'Atrás'- para que
    #se sienta como un paso hacia adelante/atrás y no un salto brusco.
    #
    #Deliberadamente barata: solo se anima la página ENTRANTE (posición
    #+ opacidad); la saliente no se toca ni se vuelve a pintar, así el
    #costo es el mismo que el fundido simple que había antes, pero se ve
    #bastante más vivo.
    def _ir_a_paso(self, nuevo_idx, direccion=1):

        self.stack.setCurrentIndex(nuevo_idx)
        pagina= self.stack.currentWidget()
        ancho= max(self.stack.width(), 1)
        offset= int(ancho * 0.05) * (1 if direccion > 0 else -1)
        pagina.move(offset, 0)
        efecto= QGraphicsOpacityEffect(pagina)
        pagina.setGraphicsEffect(efecto)

        anim_pos= QPropertyAnimation(pagina, b"pos", pagina)
        anim_pos.setDuration(220)
        anim_pos.setStartValue(QPoint(offset, 0))
        anim_pos.setEndValue(QPoint(0, 0))
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op= QPropertyAnimation(efecto, b"opacity", pagina)
        anim_op.setDuration(200)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _limpiar():

            pagina.setGraphicsEffect(None)
        anim_pos.finished.connect(_limpiar)
        #Se guardan las referencias en la página para que Python no las recolecte a mitad de camino (mismo patrón que
        #_fundido_entrada).
        pagina._anim_pos_wizard= anim_pos
        pagina._anim_op_wizard= anim_op
        anim_pos.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        anim_op.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _anterior(self):

        if self.stack.currentIndex() > 0:
            self._ir_a_paso(self.stack.currentIndex() - 1, direccion=-1)

    def _siguiente(self):

        idx= self.stack.currentIndex()
        if idx == 1 and not self.in_nombre.text().strip():
            mostrar_mensaje("advertencia", "Falta información", "Ingresa el nombre de la institución.", self)
            return
        if idx == 5 and not self.in_anio.text().strip():
            mostrar_mensaje("advertencia", "Falta información", "Ingresa el año académico.", self)
            return
        if idx == 6:
            if not self.in_admin_user.text().strip() or not self.in_admin_pass.text():
                mostrar_mensaje("advertencia", "Falta información", "Completa usuario y contraseña.", self)
                return
            if len(self.in_admin_pass.text()) < 4:
                mostrar_mensaje("advertencia", "Contraseña muy corta", "Usa al menos 4 caracteres.", self)
                return
            if self.in_admin_pass.text() != self.in_admin_pass2.text():
                mostrar_mensaje("advertencia", "No coincide", "Las contraseñas no coinciden.", self)
                return
        if idx == len(self._titulos()) - 1:
            self._finalizar()
            return
        self._ir_a_paso(idx + 1, direccion=1)

    def _finalizar(self):

        try:

            conn= obtener_conexion()
            c= conn.cursor()
            sistema_texto= self.combo_sistema_calificacion.currentText()
            #Si se eligió el Sistema Dominicano, la nota mínima "general" (usada como fallback para grados sin
            #nivel_educativo clasificado) se guarda como el mayor de los dos valores por nivel, para no dejar pasar por
            #error a nadie que quede sin clasificar.
            if es_sistema_dominicano(sistema_texto):
                nota_min_general= max(self.spin_nota_min_primaria.value(), self.spin_nota_min_secundaria.value())
            else:
                nota_min_general= self.spin_nota_min.value()
            c.execute("""UPDATE configuracion SET
                nombre_institucion= ?, direccion=?, telefono=?, correo=?, sitio_web=?, logo_path=?,
                tipo_institucion= ?, escala_maxima=?, nota_minima=?, nota_minima_primaria=?, nota_minima_secundaria=?,
                metodo_calculo= ?, sistema_calificacion=?,
                anio_academico= ?, division_periodo=?, cantidad_periodos=?, wizard_completado=1
                WHERE id=1""",
                (self.in_nombre.text().strip(), self.in_direccion.text().strip(),
                 self.in_telefono.text().strip(), self.in_correo.text().strip(),
                 self.in_sitio_web.text().strip(), self.logo_path,
                 self.combo_tipo.currentText(), self.spin_escala.value(), nota_min_general,
                 self.spin_nota_min_primaria.value(), self.spin_nota_min_secundaria.value(),
                 self.combo_metodo.currentText(), sistema_texto,
                 self.in_anio.text().strip(),
                 self.combo_division.currentText(), self.spin_cantidad.value()))
            sistema_elegido= self.combo_sistema_calificacion.currentText()
            if es_sistema_dominicano(sistema_elegido):
                for i, nombre_p in enumerate(NOMBRES_PERIODOS_RD):
                    c.execute("INSERT INTO periodos (nombre, anio_academico, orden) VALUES (?, ?, ?)",
                              (nombre_p, self.in_anio.text().strip(), i + 1))
            else:
                for i in range(self.spin_cantidad.value()):
                    c.execute("INSERT INTO periodos (nombre, anio_academico, orden) VALUES (?, ?, ?)",
                              (f"{self.combo_division.currentText()[:-1]} {i + 1}", self.in_anio.text().strip(), i + 1))
            hash_pw= hash_password(self.in_admin_pass.text())
            c.execute("""INSERT INTO usuarios (username, password, nombre_completo, rol, activo, fecha_creacion)
                         VALUES (?, ?, ?, 'Administrador', 1, ?)""",
                      (self.in_admin_user.text().strip(), hash_pw,
                       self.in_admin_nombre.text().strip() or self.in_admin_user.text().strip(),
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo completar la configuración:\n{error}", self)
            return
        registrar_auditoria("Configuración", "Asistente inicial completado", self.in_admin_user.text().strip(),
                            f"Institución: {self.in_nombre.text().strip()} | Tipo: {self.combo_tipo.currentText()}")
        self.accept()

    def _aplicar_tema(self):

        paleta= self.main_window.theme_palettes.get(
            self.main_window.tema_actual, self.main_window.theme_palettes["Indigo"])
        idx= 1 if self.main_window.modo_oscuro else 0
        bg_window, bg_panel= paleta["window_bg"][idx], paleta["display_bg"][idx]
        txt_prim, txt_sec= paleta["text_primary"][idx], paleta["text_secondary"][idx]
        bg_btn, accent= paleta["btn_num_bg"][idx], paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg_window}; }}
            QFrame#WizardHeader, QFrame#WizardPie {{ background-color: {bg_panel}; }}
            QLabel#WizardBadgePaso {{
                background-color: {_hex_a_rgba(accent, 0.22 if self.main_window.modo_oscuro else 0.12)};
                border-radius: 17px; font-size: 15px; color: {accent};
            }}
            QLabel#WizardPasoLabel {{ font-size: 19px; font-weight: bold; color: {accent}; }}
            QLabel#WizardContador {{
                font-size: 12px; font-weight: 600; color: {accent};
                background-color: {_hex_a_rgba(accent, 0.16)};
                padding: 4px 12px; border-radius: 10px;
            }}
            QWidget#WizardStackContenedor {{ background-color: transparent; }}
            QFrame#WizardCard {{
                background-color: {bg_panel};
                border-radius: 18px;
                border: 1px solid {_hex_a_rgba(txt_sec, 0.14)};
            }}
            QLabel#WizardTitulo {{ font-size: 26px; font-weight: 800; color: {accent}; }}
            QLabel#WizardSubtitulo {{ font-size: 20px; font-weight: bold; color: {txt_prim}; margin-bottom: 10px; }}
            QLabel#WizardDesc {{ font-size: 13px; color: {txt_sec}; }}
            QLabel#PreviewLogo {{ border: 2px dashed {bg_btn}; border-radius: 10px; color: {txt_sec}; }}
            QLabel#PreviewLogo:hover {{ border-color: {accent}; color: {accent}; }}
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
                background-color: {bg_panel}; border: 2px solid {bg_btn}; color: {txt_prim};
                padding: 7px 9px; border-radius: 9px;
            }}
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
                border: 2px solid {accent};
            }}
            QLabel {{ color: {'#FFFFFF' if self.main_window.modo_oscuro else '#000000'}; background: transparent; }}
            QPushButton {{
                background-color: {accent}; color: white; border: none; border-radius: 9px;
                padding: 10px 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hv_accent}; }}
            QPushButton:disabled {{ background-color: {bg_btn}; color: {txt_sec}; }}
            QPushButton#BtnAccionNeutro {{ background-color: {bg_btn}; color: {txt_prim}; }}
        """)
        self.stepper.establecer_colores(accent, bg_btn, bg_panel, txt_sec)


#Módulo de configuración (ajustes generales)
class ModuloConfiguracion(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._titulo_modulo_atajos= "Configuración"
        self._construir_ui()
        self._configurar_atajos()
        self.refrescar()

    #Atajos de teclado (ver atajos.py)
    def _configurar_atajos(self):

        #Ctrl+1..Ctrl+7: salto directo a cada pestaña, en el mismo orden en que aparecen en self.tabs (ver _construir_ui).
        #Se lee el texto real de cada pestaña -ya construidas en este punto, _construir_ui corrió antes- para que la
        #ventanita de ayuda muestre "Ir a Institución" en vez de un genérico "Ir a la pestaña 1".
        for i in range(self.tabs.count()):
            titulo= self.tabs.tabText(i).split(" ", 1)[-1]  #sin el emoji
            registrar_atajo(self, self.main_window, f"Ctrl+{i + 1}",
                             f"Ir a {titulo}", lambda idx=i: self._ir_a_pestana(idx))

    def _ir_a_pestana(self, indice):

        if 0 <= indice < self.tabs.count() and self.tabs.isTabVisible(indice):
            self.tabs.setCurrentIndex(indice)

    def _construir_ui(self):

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(30, 25, 30, 20)
        disposicion.setSpacing(14)

        #--- Cabecera tipo "hero": icono + título + descripción ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Configuración")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Configuración")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Personaliza tu institución, gestiona usuarios y controla el sistema")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        disposicion.addWidget(self.frame_cabecera)

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        #Ver nota en asistencia.py: quita la línea base nativa que Qt dibuja bajo la barra de pestañas y que el
        #stylesheet no puede eliminar.
        self.tabs.tabBar().setDrawBase(False)
        disposicion.addWidget(self.tabs)
        self.tab_institucion= self._tab_institucion()
        self.tab_academico= self._tab_academico()
        self.tab_apariencia= self._tab_apariencia()
        self.tab_usuarios= self._tab_usuarios()
        self.tab_seguridad= self._tab_seguridad()
        self.tab_auditoria= self._tab_auditoria()
        self.tab_mi_cuenta= self._tab_mi_cuenta()
        self.tabs.addTab(self.tab_institucion, "Institución")
        self.tabs.addTab(self.tab_academico, "Académico")
        self.tabs.addTab(self.tab_apariencia, "Apariencia")
        self.tabs.addTab(self.tab_usuarios, "Usuarios y Roles")
        self.tabs.addTab(self.tab_seguridad, "Seguridad y Backups")
        self.tabs.addTab(self.tab_auditoria, "Auditoría")
        self.tabs.addTab(self.tab_mi_cuenta, "Mi Cuenta")

        #Iconos explícitos de pestaña (patrón de calificaciones_tecnicas.py / politecnico.py): solo se rediseñan las
        #pestañas cuyo icono automático era inexistente o se repetía dentro de esta misma tab bar. NO se tocan:
        #"Institución" 🏛, "Apariencia" 🎨, "Seguridad y Backups" 🛡 y "Mi Cuenta" 👤 (ya son coherentes con su contenido).
        #SÍ se cambian: "Académico" (no coincidía con ningún keyword y keyword y quedaba sin icono), "Usuarios y Roles"
        #(caía en 👤, idéntico a "Mi Cuenta") y "Auditoría" (caía en 🛡, idéntico a "Seguridad y Backups").
        self.tabs.setTabIcon(1, icono_emoji(EMOJI_TAB_ACADEMICO))
        self.tabs.setTabIcon(3, icono_emoji(EMOJI_TAB_USUARIOS_ROLES))
        self.tabs.setTabIcon(5, icono_emoji(EMOJI_TAB_AUDITORIA))

        #Transición suave (fundido) al cambiar de pestaña, en vez de un salto brusco.
        self.tabs.currentChanged.connect(lambda i: _fundido_entrada(self.tabs.widget(i), 220))
        #Al volver a "Usuarios y Roles" se re-arma el combo de rol: si el Director acaba de configurar/borrar un cargo
        #personalizado en "Permisos de Side Stepper" (otra pestaña/pantalla) sin cerrar Configuración, este selector
        #debe reflejarlo sin pedir reabrir el módulo entero.
        self.tabs.currentChanged.connect(
            lambda i: self._poblar_combo_rol_usuarios() if self.tabs.widget(i) is self.tab_usuarios else None)

        #Sombra que se eleva al pasar el mouse, aplicada a todos los botones del módulo.
        self._realce_botones= _RealceHover(0, 16, 4, self)
        for boton in self.findChildren(QPushButton):
            boton.installEventFilter(self._realce_botones)

        self._aplicar_tema_visual()

    #---------------- INSTITUCIÓN / BRANDING (sin cambios) ----------------
    def _tab_institucion(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_institucion= []

        t_datos= TarjetaSeccion("🏛", "Datos Generales")
        form= QFormLayout()
        form.setSpacing(10)
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre, 300)
        self.in_direccion= QLineEdit()
        limitar_campo_texto(self.in_direccion, 300)
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono, 300)
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo, 200)
        self.in_sitio_web= QLineEdit()
        limitar_campo_texto(self.in_sitio_web, 200)
        form.addRow("Nombre de la Institución:", self.in_nombre)
        form.addRow("Dirección:", self.in_direccion)
        form.addRow("Teléfono:", self.in_telefono)
        form.addRow("Correo Institucional:", self.in_correo)
        form.addRow("Sitio Web:", self.in_sitio_web)
        t_datos.contenido.addLayout(form)
        disposicion.addWidget(t_datos)
        self._tarjetas_institucion.append(t_datos)

        t_imagen= TarjetaSeccion("🖼", "Logotipo y Firma Digital",
                                   "Se usan en los reportes y boletines generados por el sistema.")
        fila_logo= QHBoxLayout()
        self.lbl_logo_actual= QLabel("Sin logotipo")
        self.lbl_logo_actual.setFixedSize(90, 90)
        self.lbl_logo_actual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo_actual.setObjectName("PreviewLogo")
        self.lbl_logo_actual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_logo_actual.setToolTip("Clic para elegir y recortar el logotipo")
        self.lbl_logo_actual.mousePressEvent= lambda evento: self._cambiar_logo()
        fila_logo.addWidget(self.lbl_logo_actual)
        btn_logo= QPushButton("Cambiar y Recortar Logotipo")
        btn_logo.setIcon(icono_emoji(EMOJI_FOTO_RECORTAR))
        btn_logo.setIconSize(_QSize_emoji(16, 16))
        btn_logo.clicked.connect(self._cambiar_logo)
        fila_logo.addWidget(btn_logo)
        btn_ver_logo= QPushButton("Ver Ampliado")
        btn_ver_logo.setIcon(icono_emoji("🖼"))
        btn_ver_logo.setIconSize(_QSize_emoji(16, 16))
        btn_ver_logo.setObjectName("BtnAccionNeutro")
        btn_ver_logo.clicked.connect(self._ver_logo_ampliado)
        fila_logo.addWidget(btn_ver_logo)
        fila_logo.addStretch()
        t_imagen.contenido.addLayout(fila_logo)
        lbl_linea_firma= QLabel("Firma Digital para Reportes:")
        lbl_linea_firma.setObjectName("DescModulo")
        t_imagen.contenido.addWidget(lbl_linea_firma)
        fila_firma= QHBoxLayout()
        self.lbl_firma_actual= QLabel("Sin firma")
        self.lbl_firma_actual.setFixedSize(90, 50)
        self.lbl_firma_actual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_firma_actual.setObjectName("PreviewLogo")
        self.lbl_firma_actual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_firma_actual.setToolTip("Clic para elegir y recortar la firma")
        self.lbl_firma_actual.mousePressEvent= lambda evento: self._cambiar_firma()
        fila_firma.addWidget(self.lbl_firma_actual)
        btn_firma= QPushButton("Cambiar y Recortar Firma")
        btn_firma.setIcon(icono_emoji(EMOJI_FOTO_RECORTAR))
        btn_firma.setIconSize(_QSize_emoji(16, 16))
        btn_firma.clicked.connect(self._cambiar_firma)
        fila_firma.addWidget(btn_firma)
        btn_ver_firma= QPushButton("Ver Ampliada")
        btn_ver_firma.setIcon(icono_emoji("✍"))
        btn_ver_firma.setIconSize(_QSize_emoji(16, 16))
        btn_ver_firma.setObjectName("BtnAccionNeutro")
        btn_ver_firma.clicked.connect(self._ver_firma_ampliada)
        fila_firma.addWidget(btn_ver_firma)
        btn_quitar_firma= QPushButton("Quitar Firma")
        btn_quitar_firma.setIcon(icono_emoji("🗑"))
        btn_quitar_firma.setIconSize(_QSize_emoji(16, 16))
        btn_quitar_firma.setObjectName("BtnAccionEliminar")
        btn_quitar_firma.clicked.connect(self._quitar_firma)
        fila_firma.addWidget(btn_quitar_firma)
        fila_firma.addStretch()
        t_imagen.contenido.addLayout(fila_firma)
        disposicion.addWidget(t_imagen)
        self._tarjetas_institucion.append(t_imagen)

        t_pie= TarjetaSeccion("📄", "Pie de Página de Reportes")
        self.in_pie_pagina= QLineEdit()
        limitar_campo_texto(self.in_pie_pagina, 300)
        self.in_pie_pagina.setPlaceholderText("Ej. Documento oficial de AcaDeXI - Prohibida su alteración")
        t_pie.contenido.addWidget(self.in_pie_pagina)
        btn_guardar= QPushButton("Guardar Datos Institucionales")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionEditar")
        btn_guardar.clicked.connect(self._guardar_institucion)
        t_pie.contenido.addWidget(btn_guardar)
        disposicion.addWidget(t_pie)
        self._tarjetas_institucion.append(t_pie)

        disposicion.addStretch()
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        return scroll

    def _cambiar_logo(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "logos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="logo")
        if not destino:
            return
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("UPDATE configuracion SET logo_path=? WHERE id=1", (destino,))
            conn.commit()
            conn.close()
            self._cargar_logo(destino)
            mostrar_mensaje("exito", "Logotipo actualizado", "El logotipo se actualizó correctamente.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo actualizar el logotipo:\n{error}", self)

    def _ver_logo_ampliado(self):

        ruta= getattr(self.main_window, "logo_path_actual", None) or ""
        if not ruta:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT logo_path FROM configuracion WHERE id=1")
            fila= c.fetchone()
            conn.close()
            ruta= fila["logo_path"] if fila else None
        if not ruta or not os.path.exists(ruta):
            mostrar_mensaje("advertencia", "Sin logotipo", "Aún no se ha cargado un logotipo.", self)
            return
        VisorFotoDialog(ruta, self, titulo="Logotipo Institucional").exec()

    def _cargar_logo(self, ruta):

        if ruta and os.path.exists(ruta):
            pixmap= QPixmap(ruta).scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo_actual.setPixmap(pixmap)
        else:
            self.lbl_logo_actual.setText("Sin logotipo")

    def _cambiar_firma(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "logos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="firma")
        if not destino:
            return
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("UPDATE configuracion SET firma_path=? WHERE id=1", (destino,))
            conn.commit()
            conn.close()
            self._cargar_firma(destino)
            mostrar_mensaje("exito", "Firma actualizada", "La firma digital se actualizó correctamente.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo actualizar la firma:\n{error}", self)

    def _quitar_firma(self):

        if mostrar_mensaje("pregunta", "Confirmar", "¿Quitar la firma digital de los reportes?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE configuracion SET firma_path='' WHERE id=1")
        conn.commit()
        conn.close()
        self._cargar_firma(None)
        registrar_auditoria("Configuración", "Quitó la firma digital", self.main_window.usuario_actual)

    def _ver_firma_ampliada(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT firma_path FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        ruta= fila["firma_path"] if fila else None
        if not ruta or not os.path.exists(ruta):
            mostrar_mensaje("advertencia", "Sin firma", "Aún no se ha cargado una firma digital.", self)
            return
        VisorFotoDialog(ruta, self, titulo="Firma Digital Institucional").exec()

    def _cargar_firma(self, ruta):

        if ruta and os.path.exists(ruta):
            pixmap= QPixmap(ruta).scaled(84, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.lbl_firma_actual.setPixmap(pixmap)
        else:
            self.lbl_firma_actual.setText("Sin firma")

    def _guardar_institucion(self):

        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""UPDATE configuracion SET nombre_institucion=?, direccion=?, telefono=?,
                         correo= ?, sitio_web=?, pie_pagina=? WHERE id=1""",
                      (self.in_nombre.text().strip(), self.in_direccion.text().strip(),
                       self.in_telefono.text().strip(), self.in_correo.text().strip(),
                       self.in_sitio_web.text().strip(), self.in_pie_pagina.text().strip()))
            conn.commit()
            conn.close()
            registrar_auditoria("Configuración", "Actualizó datos institucionales",
                               self.main_window.usuario_actual)
            mostrar_mensaje("exito", "Guardado", "Los datos institucionales se guardaron correctamente.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar:\n{error}", self)

    #---------------- ACADÉMICO (sin cambios) ----------------
    def _tab_academico(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_academico= []

        #Icono propio de la pestaña (el mismo dibujo del birrete+libro de la tab bar), en vez del ⚙ genérico que no
        #decía nada de lo académico.
        t_config= TarjetaSeccion(EMOJI_TAB_ACADEMICO, "Configuración Académica")
        form= QFormLayout()
        form.setSpacing(10)
        self.combo_tipo= QComboBox()
        self.combo_tipo.addItems(TIPOS_INSTITUCION)
        self.combo_sistema_calificacion= QComboBox()
        self.combo_sistema_calificacion.addItems(SISTEMAS_CALIFICACION)
        self.spin_escala= QDoubleSpinBox()
        self.spin_escala.setRange(1, 1000)
        self.spin_nota_min= QDoubleSpinBox()
        self.spin_nota_min.setRange(0, 1000)
        self.spin_nota_min_primaria= QDoubleSpinBox()
        self.spin_nota_min_primaria.setRange(NOTA_MIN_PRIMARIA_PISO, NOTA_MIN_PRIMARIA_TECHO)
        self.spin_nota_min_primaria.setToolTip(
            f"Mínimo {NOTA_MIN_PRIMARIA_PISO}, puedes subirlo hasta {NOTA_MIN_PRIMARIA_TECHO}.")
        self.spin_nota_min_secundaria= QDoubleSpinBox()
        self.spin_nota_min_secundaria.setRange(NOTA_MIN_SECUNDARIA_PISO, NOTA_MIN_SECUNDARIA_TECHO)
        self.combo_metodo= QComboBox()
        self.combo_metodo.addItems(METODOS_CALCULO)
        self.in_anio= QLineEdit()
        limitar_campo_texto(self.in_anio, 300)
        self.combo_division= QComboBox()
        self.combo_division.addItems(DIVISIONES_PERIODO)
        self.combo_tipo.setToolTip("Modalidad institucional; determina qué módulos adicionales se activan")
        self.combo_sistema_calificacion.setToolTip("Escala y método con el que se calculan e interpretan las notas")
        self.spin_escala.setToolTip("Valor máximo posible de una calificación (ej. 10, 20, 100)")
        self.spin_nota_min.setToolTip("Nota mínima para considerar una materia aprobada")
        self.combo_metodo.setToolTip("Fórmula usada para calcular la nota final de una materia")
        self.combo_division.setToolTip("Cómo se divide el año académico (trimestres, semestres, etc.)")
        conectar_tooltip_seleccion(self.combo_tipo, self.combo_tipo.toolTip())
        conectar_tooltip_seleccion(self.combo_sistema_calificacion, self.combo_sistema_calificacion.toolTip())
        conectar_tooltip_seleccion(self.combo_metodo, self.combo_metodo.toolTip())
        conectar_tooltip_seleccion(self.combo_division, self.combo_division.toolTip())
        form.addRow("Tipo de Institución:", self.combo_tipo)
        form.addRow("Sistema de Calificación:", self.combo_sistema_calificacion)
        form.addRow("Escala Máxima:", self.spin_escala)
        form.addRow("Nota Mínima Aprobatoria:", self.spin_nota_min)
        form.addRow("Nota Mínima Aprobatoria — Primaria:", self.spin_nota_min_primaria)
        form.addRow("Nota Mínima Aprobatoria — Secundaria:", self.spin_nota_min_secundaria)
        form.addRow("Método de Cálculo:", self.combo_metodo)
        self.form_academico= form
        fila_anio= QHBoxLayout()
        fila_anio.addWidget(self.in_anio)
        btn_anio_actual= QPushButton("Usar Año Actual")
        btn_anio_actual.setIcon(icono_emoji("📆"))
        btn_anio_actual.setIconSize(_QSize_emoji(16, 16))
        btn_anio_actual.setObjectName("BtnAccionNeutro")
        btn_anio_actual.clicked.connect(self._usar_anio_academico_actual)
        fila_anio.addWidget(btn_anio_actual)
        form.addRow("Año Académico:", fila_anio)
        form.addRow("División Periódica:", self.combo_division)
        t_config.contenido.addLayout(form)

        #Boletín Oficial RD (ver boletin_minerd.py / boletin_primaria_minerd.py / boletin_tecnico_minerd.py):
        #interruptor de formato + colores de banda por nivel. Solo tiene sentido con el Sistema Dominicano -se
        #muestra/oculta junto con el resto de los controles específicos de RD en _sync_sistema_calificacion_config.
        form_boletin= QFormLayout()
        form_boletin.setSpacing(10)
        self.combo_formato_boletin= QComboBox()
        self.combo_formato_boletin.addItem("Boletín simple (lista por materia)", "simple")
        self.combo_formato_boletin.addItem("Boletín Oficial RD (formato MINERD)", "oficial_rd")
        self.combo_formato_boletin.setToolTip(
            "'Oficial RD' reproduce la grilla del boletín impreso del MINERD (competencias "
            "fundamentales, cascada de evaluación, etc.); 'Simple' es la lista por materia de siempre.")
        conectar_tooltip_seleccion(self.combo_formato_boletin, self.combo_formato_boletin.toolTip())
        form_boletin.addRow("Formato del Boletín:", self.combo_formato_boletin)

        self.btn_color_banda_secundaria= QPushButton()
        self.btn_color_banda_secundaria.setToolTip("Color de la banda de título del Boletín de Secundaria")
        self.btn_color_banda_secundaria.clicked.connect(lambda: self._elegir_color_boletin("Secundaria"))
        form_boletin.addRow("Color del Boletín — Secundaria:", self.btn_color_banda_secundaria)

        self.btn_color_banda_primaria= QPushButton()
        self.btn_color_banda_primaria.setToolTip("Color de la banda de título del Informe de Aprendizaje de Primaria")
        self.btn_color_banda_primaria.clicked.connect(lambda: self._elegir_color_boletin("Primaria"))
        form_boletin.addRow("Color del Informe — Primaria:", self.btn_color_banda_primaria)

        self.form_boletin_oficial= form_boletin
        t_config.contenido.addLayout(form_boletin)
        self._colores_boletin_elegidos= {"Secundaria": "#1F9E9E", "Primaria": "#E8863C"}
        self._refrescar_botones_color_boletin()
        self.combo_sistema_calificacion.currentTextChanged.connect(self._sync_sistema_calificacion_config)
        #Igual que en el wizard: solo se autocompleta 65/70 cuando el usuario elige el sistema con el mouse/teclado,
        #nunca al cargar la configuración ya guardada (_cargar_datos hace setCurrentText, que NO dispara `activated`).
        self.combo_sistema_calificacion.activated.connect(self._restablecer_nota_min_nivel_defecto)
        self.lbl_info_sistema_config= QLabel()
        self.lbl_info_sistema_config.setWordWrap(True)
        self.lbl_info_sistema_config.setObjectName("DescModulo")
        t_config.contenido.addWidget(self.lbl_info_sistema_config)
        self._sync_sistema_calificacion_config(self.combo_sistema_calificacion.currentText())
        lbl_aviso= QLabel("Cambiar el 'Tipo de Institución' activa o desactiva los módulos"
                       "de Politécnico / Universidad al reiniciar la navegación lateral.")
        lbl_aviso.setWordWrap(True)
        lbl_aviso.setObjectName("DescModulo")
        t_config.contenido.addWidget(lbl_aviso)
        disposicion.addWidget(t_config)
        self._tarjetas_academico.append(t_config)

        self.grupo_modulos_personalizados= TarjetaSeccion(
            "", "Módulos del Modo Personalizado",
            "Selecciona qué módulos adicionales activar de forma independiente:")
        self.chk_mod_politecnico= QCheckBox("Politécnico (Especialidades, Empresas, Pasantías)")
        self.chk_mod_universidad= QCheckBox("Universidad (Facultades, Carreras, Pensum)")
        self.grupo_modulos_personalizados.contenido.addWidget(self.chk_mod_politecnico)
        self.grupo_modulos_personalizados.contenido.addWidget(self.chk_mod_universidad)
        disposicion.addWidget(self.grupo_modulos_personalizados)
        self._tarjetas_academico.append(self.grupo_modulos_personalizados)
        self.combo_tipo.currentTextChanged.connect(self._actualizar_visibilidad_modulos_personalizados)

        #Niveles educativos que ofrece la institución: mismo patrón visual que el grupo de arriba. Para
        #Politécnico/Universidad el nivel ya se deduce del tipo (ver niveles_academicos_habilitados), así que aquí solo
        #se deja elegir para Escuela y Personalizado -en Personalizado, sin ninguna restricción de cuáles combinar
        #entre sí.
        self.grupo_niveles_educativos= TarjetaSeccion(
            "", "Niveles Educativos que ofrece la institución",
            "Solo los niveles marcados aquí estarán disponibles al crear Cursos/Grados, "
            "filtrar Estudiantes, etc. en el resto del sistema:")
        self.chk_nivel= {}
        for nivel in NIVELES_ACADEMICOS:
            chk= QCheckBox(nivel)
            self.chk_nivel[nivel]= chk
            self.grupo_niveles_educativos.contenido.addWidget(chk)
        disposicion.addWidget(self.grupo_niveles_educativos)
        self._tarjetas_academico.append(self.grupo_niveles_educativos)
        self.combo_tipo.currentTextChanged.connect(self._actualizar_visibilidad_niveles_educativos)
        self.combo_sistema_calificacion.currentTextChanged.connect(self._actualizar_visibilidad_niveles_educativos)

        self.grupo_numero_lista= TarjetaSeccion(
            "", "Número de Lista de los Estudiantes",
            self._texto_intro_numero_lista(self.combo_sistema_calificacion.currentText()))
        self.combo_criterio_lista= QComboBox()
        self.combo_criterio_lista.addItems(CRITERIOS_NUMERO_LISTA)
        for criterio in CRITERIOS_NUMERO_LISTA:
            idx= self.combo_criterio_lista.findText(criterio)
            self.combo_criterio_lista.setItemData(
                idx, DESCRIPCION_CRITERIO_NUMERO_LISTA[criterio], Qt.ItemDataRole.ToolTipRole)
        conectar_tooltip_seleccion(
            self.combo_criterio_lista,
            "Cómo se calcula el número de lista de cada estudiante dentro de su sección.")
        self.lbl_info_criterio_lista= QLabel()
        self.lbl_info_criterio_lista.setWordWrap(True)
        self.lbl_info_criterio_lista.setObjectName("DescModulo")
        self.combo_criterio_lista.currentTextChanged.connect(self._actualizar_info_criterio_lista)
        #La institución no tiene por qué ser dominicana: el texto de arriba (self.grupo_numero_lista.lbl_desc) solo
        #habla de la convención "por Apellido" cuando el Sistema de Calificación elegido es el Dominicano; en cualquier
        #otro sistema pasa a un texto genérico que no asume ninguna región. Ver _texto_intro_numero_lista.
        self.combo_sistema_calificacion.currentTextChanged.connect(self._actualizar_intro_numero_lista)
        self.grupo_numero_lista.contenido.addWidget(self.combo_criterio_lista)
        self.grupo_numero_lista.contenido.addWidget(self.lbl_info_criterio_lista)
        btn_recalcular_lista= QPushButton("Recalcular Ahora (todas las secciones)")
        btn_recalcular_lista.setIcon(icono_emoji("🔄"))
        btn_recalcular_lista.setIconSize(_QSize_emoji(16, 16))
        btn_recalcular_lista.setObjectName("BtnAccionNeutro")
        btn_recalcular_lista.setToolTip(
            "Vuelve a numerar a TODOS los estudiantes activos de TODAS las secciones con el criterio "
            "de arriba. Útil, por ejemplo, después de importar un lote grande de estudiantes.")
        btn_recalcular_lista.clicked.connect(self._recalcular_numeros_lista_manual)
        self.grupo_numero_lista.contenido.addWidget(btn_recalcular_lista)
        disposicion.addWidget(self.grupo_numero_lista)
        self._tarjetas_academico.append(self.grupo_numero_lista)

        btn_guardar= QPushButton("Guardar Configuración Académica")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionEditar")
        btn_guardar.clicked.connect(self._guardar_academico)
        disposicion.addWidget(btn_guardar)

        disposicion.addStretch()
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        return scroll

    def _actualizar_visibilidad_modulos_personalizados(self, tipo=None):

        tipo= tipo if tipo is not None else self.combo_tipo.currentText()
        self.grupo_modulos_personalizados.setVisible(tipo == "Personalizado")

    def _actualizar_visibilidad_niveles_educativos(self, _valor=None):

        tipo= self.combo_tipo.currentText()
        #Solo editable cuando el nivel no se deduce automáticamente del tipo de institución (ver
        #niveles_academicos_habilitados en el módulo).
        editable= tipo in ("Escuela", "Personalizado")
        self.grupo_niveles_educativos.setVisible(editable)
        if not editable:
            return
        dominicano= es_sistema_dominicano(self.combo_sistema_calificacion.currentText())
        for nivel, chk in self.chk_nivel.items():
            #Personalizado: sin restricciones, cualquier combinación. Escuela: nunca ofrece Universidad (se matricula por
            #Carrera, concepto que Escuela no maneja).
            habilitar= tipo == "Personalizado" or nivel != "Universidad"
            if tipo == "Escuela" and nivel == "Universidad":
                chk.setChecked(False)
            #Sistema Dominicano: "Preparatoria" no existe como tal en RD -lo que otros sistemas llaman Preparatoria es,
            #aquí, el Segundo Ciclo de Secundaria (ver CICLOS_SECUNDARIA), que ya queda cubierto con el nivel Secundaria +
            #el Ciclo del Grado. Ofrecer ambos a la vez sería redundante y confundiría qué Grado va en cuál. Se aplica sin
            #importar el tipo de institución (incluido Personalizado): es una regla del sistema de calificación, no de la
            #modalidad institucional.
            if nivel == "Preparatoria" and dominicano:
                habilitar= False
                chk.setChecked(False)
                chk.setToolTip("No aplica con el Sistema Dominicano: lo que aquí se conoce como "
                                "'Preparatoria' es el Segundo Ciclo de Secundaria (clasifícalo así en "
                                "Materias > Secciones), no un nivel aparte.")
            else:
                chk.setToolTip("")
            chk.setEnabled(habilitar)

    def _usar_anio_academico_actual(self):

        self.in_anio.setText(anio_academico_actual())

    #Texto de introducción de la tarjeta "Número de Lista de los
    #Estudiantes": cambia según el Sistema de Calificación elegido arriba
    #(Dominicano vs cualquier otro), sin nombrar a ningún organismo
    #regulador -cada institución define su propio criterio de numeración
    #por aula, así que aquí solo se describe la convención, no quién la
    #exige.
    def _texto_intro_numero_lista(self, sistema_texto):

        if es_sistema_dominicano(sistema_texto):
            return ("No existe un criterio único de numeración por aula: cada institución define el "
                     "suyo. Aquí eliges cómo AcaDeXI numera a cada estudiante DENTRO de su Sección (1, "
                     "2, 3... por sección, no global) para pasar lista, exámenes, etc. La convención más "
                     "común en el país es alfabética, por Primer Apellido.")
        return ("Cada institución define su propio criterio de numeración por aula. Aquí eliges cómo "
                "AcaDeXI numera a cada estudiante DENTRO de su Sección (1, 2, 3... por sección, no "
                "global) para pasar lista, exámenes, etc.")

    def _actualizar_intro_numero_lista(self, sistema_texto=None):

        sistema_texto= sistema_texto or self.combo_sistema_calificacion.currentText()
        if hasattr(self.grupo_numero_lista, "lbl_desc"):
            self.grupo_numero_lista.lbl_desc.setText(self._texto_intro_numero_lista(sistema_texto))

    def _actualizar_info_criterio_lista(self, criterio=None):

        criterio= criterio or self.combo_criterio_lista.currentText()
        self.lbl_info_criterio_lista.setText(DESCRIPCION_CRITERIO_NUMERO_LISTA.get(criterio, ""))

    #Fuerza un recálculo puntual de TODAS las secciones con el criterio
    #actualmente elegido en el combo (SIN necesidad de haber presionado
    #"Guardar Configuración Académica" antes: es una acción inmediata,
    #igual que el resto de botones de esta pestaña).
    def _recalcular_numeros_lista_manual(self):

        criterio= self.combo_criterio_lista.currentText()
        if criterio == CRITERIO_MANUAL:
            if mostrar_mensaje(
                "pregunta", "Criterio en Manual",
                "El criterio elegido es 'Manual': AcaDeXI no numera automáticamente. ¿Quieres de "
                "todos modos recalcular ahora mismo con 'Apellidos y Nombre' (la convención más común "
                "en la región), solo esta vez, sin cambiar tu configuración?", self) != QMessageBox.StandardButton.Yes:
                return
            criterio= CRITERIO_APELLIDOS_NOMBRE
        recalcular_numeros_lista_todas_secciones(criterio)
        registrar_auditoria("Configuración", "Recalculó Números de Lista (todas las secciones)",
                           self.main_window.usuario_actual, criterio)
        mostrar_mensaje("exito", "Números de Lista recalculados",
                       f"Se recalcularon todas las secciones usando el criterio: {criterio}.", self)

    #Ver el método homónimo en WizardConfiguracion: autocompleta Primaria/
    #Secundaria con su piso normativo (65/70) solo cuando el usuario elige
    #el Sistema Dominicano con el mouse/teclado, nunca al cargar un valor
    #ya guardado en `configuracion`.
    def _restablecer_nota_min_nivel_defecto(self, *_):

        if self.combo_sistema_calificacion.currentText() != SISTEMA_DOMINICANO:
            return
        self.spin_nota_min_primaria.setValue(NOTA_MIN_PRIMARIA_PISO)
        self.spin_nota_min_secundaria.setValue(NOTA_MIN_SECUNDARIA_PISO)

    #Pinta cada botón con el color que tiene elegido (en vez de un
    #texto tipo '#1F9E9E' que no dice nada de un vistazo).
    def _refrescar_botones_color_boletin(self):

        for nivel, boton in (("Secundaria", self.btn_color_banda_secundaria),
                             ("Primaria", self.btn_color_banda_primaria)):
            color= self._colores_boletin_elegidos.get(nivel, "#1F9E9E")
            boton.setText(color)
            boton.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")

    def _elegir_color_boletin(self, nivel):

        from PySide6.QtWidgets import QColorDialog, QDialog
        from PySide6.QtGui import QColor
        actual= QColor(self._colores_boletin_elegidos.get(nivel, "#1F9E9E"))
        #Instancia propia (en vez del atajo estático QColorDialog.getColor) para poder ponerle ICONO_COLOR
        #("colorico.ico") antes de mostrarla -mismo criterio que toda ventana de elegir color en AcaDeXI (ver
        #_elegir_color_con_icono en reportes_editor.py)-: el atajo estático arma su diálogo por dentro y no deja
        #tocarlo antes de exec().
        dialogo= QColorDialog(actual, self)
        dialogo.setWindowTitle(f"Color del Boletín — {nivel}")
        aplicar_icono_ventana(dialogo, ICONO_COLOR)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            color= dialogo.selectedColor()
            if color.isValid():
                self._colores_boletin_elegidos[nivel]= color.name()
                self._refrescar_botones_color_boletin()

    def _sync_sistema_calificacion_config(self, sistema):

        escala, minima= _escala_y_minima_por_sistema(sistema)
        dominicano= es_sistema_dominicano(sistema)
        _alternar_fila_form(self.form_academico, self.spin_nota_min, not dominicano)
        _alternar_fila_form(self.form_academico, self.spin_nota_min_primaria, dominicano)
        _alternar_fila_form(self.form_academico, self.spin_nota_min_secundaria, dominicano)
        if escala is not None:
            self.spin_escala.setValue(escala)
            self.spin_escala.setEnabled(False)
            if dominicano:
                self.spin_nota_min.setEnabled(False)
            else:
                self.spin_nota_min.setValue(minima)
                self.spin_nota_min.setEnabled(False)
        else:
            self.spin_escala.setEnabled(True)
            self.spin_nota_min.setEnabled(True)
        if dominicano:
            self.combo_division.setCurrentText("Periodos")
            self.combo_division.setEnabled(False)
            self.lbl_info_sistema_config.setText(
                f"Se crearán/usarán los períodos P1-P4 del año académico. Nota mínima: Primaria "
                f"{NOTA_MIN_PRIMARIA_PISO} (hasta {NOTA_MIN_PRIMARIA_TECHO}), Secundaria "
                f"{NOTA_MIN_SECUNDARIA_PISO}.")
        else:
            self.combo_division.setEnabled(True)
            self.lbl_info_sistema_config.setText("")
        #El Boletín Oficial RD (formato MINERD) solo tiene sentido con el Sistema Dominicano -con otro sistema no hay
        #competencias fundamentales ni cascada de evaluación que dibujar.
        if hasattr(self, "form_boletin_oficial"):
            _alternar_fila_form(self.form_boletin_oficial, self.combo_formato_boletin, dominicano)
            _alternar_fila_form(self.form_boletin_oficial, self.btn_color_banda_secundaria, dominicano)
            _alternar_fila_form(self.form_boletin_oficial, self.btn_color_banda_primaria, dominicano)

    def _guardar_academico(self):

        try:

            modulos_personalizados= ""
            if self.combo_tipo.currentText() == "Personalizado":
                seleccionados= []
                if self.chk_mod_politecnico.isChecked():
                    seleccionados.append("Politécnico")
                if self.chk_mod_universidad.isChecked():
                    seleccionados.append("Universidad")
                modulos_personalizados= ",".join(seleccionados)
            #Niveles educativos: solo se guarda lo que la persona marcó cuando es editable (Escuela/Personalizado); para
            #Politécnico y Universidad se deduce del tipo -no depende de estos checkboxes (ver
            #niveles_academicos_habilitados), pero igual se guarda lo marcado para que, si luego cambian el tipo a Escuela/
            #Personalizado, no pierdan la selección que ya tenían hecha.
            niveles_marcados= ",".join(n for n, chk in self.chk_nivel.items() if chk.isChecked())
            conn= obtener_conexion()
            c= conn.cursor()
            sistema_texto= self.combo_sistema_calificacion.currentText()
            if es_sistema_dominicano(sistema_texto):
                #Ver la misma nota en el wizard (_finalizar): el campo general (fallback para grados sin nivel_educativo) se
                #guarda como el mayor de los dos valores por nivel.
                nota_min_general= max(self.spin_nota_min_primaria.value(), self.spin_nota_min_secundaria.value())
            else:
                nota_min_general= self.spin_nota_min.value()
            criterio_lista_anterior= obtener_criterio_numero_lista()
            criterio_lista_nuevo= self.combo_criterio_lista.currentText()
            c.execute("""UPDATE configuracion SET tipo_institucion=?, escala_maxima=?, nota_minima=?,
                         nota_minima_primaria= ?, nota_minima_secundaria=?,
                         metodo_calculo= ?, sistema_calificacion=?, anio_academico=?, division_periodo=?, idioma=?,
                         modulos_personalizados= ?, niveles_educativos_habilitados=?, criterio_numero_lista=?
                         WHERE id=1""",
                      (self.combo_tipo.currentText(), self.spin_escala.value(), nota_min_general,
                       self.spin_nota_min_primaria.value(), self.spin_nota_min_secundaria.value(),
                       self.combo_metodo.currentText(), sistema_texto,
                       self.in_anio.text().strip(),
                       self.combo_division.currentText(), self.combo_idioma.currentText(),
                       modulos_personalizados, niveles_marcados, criterio_lista_nuevo))
            #Boletín Oficial RD: formato + colores por nivel (ver boletin_minerd.py). Se guarda en la misma transacción que
            #el resto de lo académico porque vive en la misma tabla `configuracion`. Envuelto en try/except: si
            #boletin_minerd.py no está instalado en esta copia, esas columnas no existen todavía y no deben tumbar el
            #guardado del resto de la configuración académica.
            if hasattr(self, "combo_formato_boletin"):
                try:

                    c.execute("UPDATE configuracion SET formato_boletin_general=? WHERE id=1",
                              (self.combo_formato_boletin.currentData(),))
                    c.execute("""UPDATE configuracion SET boletin_color_banda_secundaria=?,
                                 boletin_color_banda_primaria= ? WHERE id=1""",
                              (self._colores_boletin_elegidos.get("Secundaria", "#1F9E9E"),
                               self._colores_boletin_elegidos.get("Primaria", "#E8863C")))
                except Exception:
                    pass
            if es_sistema_dominicano(sistema_texto):
                anio= self.in_anio.text().strip()
                c.execute("SELECT nombre FROM periodos WHERE anio_academico=?", (anio,))
                existentes= {fila["nombre"] for fila in c.fetchall()}
                for i, nombre_p in enumerate(NOMBRES_PERIODOS_RD):
                    if nombre_p not in existentes:
                        c.execute("INSERT INTO periodos (nombre, anio_academico, orden) VALUES (?, ?, ?)",
                                  (nombre_p, anio, i + 1))
            conn.commit()
            conn.close()
            #El recálculo va DESPUÉS de cerrar esta conexión (recalcular_numeros_lista abre la suya propia) y solo si el
            #criterio de verdad cambió: si la persona solo vino a tocar la escala o el año, no tiene sentido reescribir de
            #golpe el numero_lista de todos los estudiantes.
            if criterio_lista_nuevo != criterio_lista_anterior and criterio_lista_nuevo != CRITERIO_MANUAL:
                recalcular_numeros_lista_todas_secciones(criterio_lista_nuevo)
            registrar_auditoria("Configuración", "Actualizó configuración académica",
                               self.main_window.usuario_actual)
            self.main_window.recargar_modulos_dinamicos()
            mostrar_mensaje("exito", "Guardado", "Configuración académica actualizada. Los módulos "
                            "dinámicos se han actualizado en la barra lateral.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar:\n{error}", self)

    #---------------- APARIENCIA (sin cambios) ----------------
    def _tab_apariencia(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_apariencia= []

        t_tema= TarjetaSeccion("🎨", "Tema y Preferencias Visuales")
        #NOTA: esta sección usaba QFormLayout, pero combinarlo con combos más altos (min-height) causaba que Qt
        #calculara mal el alto de cada fila y las etiquetas/combos terminaran superpuestos. Se reconstruye con filas
        #QHBoxLayout normales (label + combo), el mismo patrón usado en otras partes de la app, que no tiene ese
        #problema.
        _ancho_label_tema= 130  #ancho fijo para que los 4 combos queden alineados
        form= QVBoxLayout()
        form.setSpacing(30)

        def _fila_tema(texto, combo):

            fila= QHBoxLayout()
            fila.setSpacing(12)
            lbl= QLabel(texto)
            lbl.setFixedWidth(_ancho_label_tema)
            lbl.setFixedHeight(31)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            fila.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            fila.addWidget(combo, 1, Qt.AlignmentFlag.AlignVCenter)
            form.addLayout(fila)

        self.combo_tema= QComboBox()
        self.combo_tema.addItems(list(self.main_window.theme_palettes.keys()))
        self.combo_tema.setMinimumHeight(33)
        conectar_tooltip_seleccion(self.combo_tema, "Paleta de colores con la que se verá el programa")
        _fila_tema("Tema de color:", self.combo_tema)

        self.combo_idioma= QComboBox()
        self.combo_idioma.addItems(IDIOMAS)
        self.combo_idioma.setMinimumHeight(33)
        conectar_tooltip_seleccion(self.combo_idioma, "Idioma de la interfaz de AcaDeXI")
        _fila_tema("Idioma:", self.combo_idioma)

        self.combo_formato_hora= QComboBox()
        for clave, etiqueta in FORMATOS_HORA.items():
            self.combo_formato_hora.addItem(etiqueta, clave)
        self.combo_formato_hora.setMinimumHeight(33)
        conectar_tooltip_seleccion(self.combo_formato_hora,
            "Cómo se muestran las horas en Calendario, Horario, Banco de Tareas, Materias,\n"
            "Personal, Profesores, Estudiantes y Dashboard. Los datos siguen guardándose\n"
            "igual; esto solo cambia cómo se ven en este equipo.")
        _fila_tema("Formato de hora:", self.combo_formato_hora)

        self.combo_formato_fecha= QComboBox()
        for clave, etiqueta in FORMATOS_FECHA.items():
            self.combo_formato_fecha.addItem(etiqueta, clave)
        self.combo_formato_fecha.setMinimumHeight(33)
        conectar_tooltip_seleccion(self.combo_formato_fecha,
            "Cómo se muestran las fechas en Calendario, Horario, Banco de Tareas, Materias,\n"
            "Personal, Profesores, Estudiantes y Dashboard.")
        _fila_tema("Formato de fecha:", self.combo_formato_fecha)

        t_tema.contenido.addLayout(form)
        #Espacio extra antes de los checkboxes: con el form más alto (combos + espaciado agrandados arriba), sin este
        #respiro "Modo oscuro" quedaba pegado/encima de la última fila.
        t_tema.contenido.addSpacing(28)
        self.chk_oscuro= QCheckBox("Modo oscuro")
        t_tema.contenido.addWidget(self.chk_oscuro)
        self.chk_login_translucido= QCheckBox("Panel de login translúcido")
        t_tema.contenido.addWidget(self.chk_login_translucido)
        btn_aplicar= QPushButton("Aplicar Apariencia")
        btn_aplicar.setIcon(icono_emoji("💾"))
        btn_aplicar.setIconSize(_QSize_emoji(16, 16))
        btn_aplicar.setObjectName("BtnAccionEditar")
        btn_aplicar.clicked.connect(self._aplicar_apariencia)
        t_tema.contenido.addWidget(btn_aplicar)
        disposicion.addWidget(t_tema)
        self._tarjetas_apariencia.append(t_tema)

        #--- Accesibilidad visual ---
        t_accesibilidad= TarjetaSeccion("👁", "Accesibilidad Visual")
        lbl_desc_accesibilidad= QLabel(
            "Ajustes pensados para personas con baja visión o dificultad para "
            "distinguir texto con poco contraste. Se guardan por equipo, igual "
            "que el tema.")
        lbl_desc_accesibilidad.setObjectName("DescModulo")
        lbl_desc_accesibilidad.setWordWrap(True)
        t_accesibilidad.contenido.addWidget(lbl_desc_accesibilidad)
        self.chk_etiquetas_recuadro= QCheckBox(
            "Etiquetas con recuadro")
        self.chk_etiquetas_recuadro.setToolTip(
            "Pensado para personas con dificultades visuales: agrega un fondo "
            "en forma de recuadro detrás de cada etiqueta de los formularios "
            "(\"Curso:\", \"Sección:\", \"Fecha:\", etc.) en TODOS los módulos, "
            "para que sea más fácil distinguir dónde empieza y termina cada "
            "campo.\n\n"
            "Desactivado (por defecto): las etiquetas se ven de forma normal, "
            "sin recuadro de fondo.")
        t_accesibilidad.contenido.addWidget(self.chk_etiquetas_recuadro)
        btn_aplicar_accesibilidad= QPushButton("Aplicar Accesibilidad")
        btn_aplicar_accesibilidad.setIcon(icono_emoji("💾"))
        btn_aplicar_accesibilidad.setIconSize(_QSize_emoji(16, 16))
        btn_aplicar_accesibilidad.setObjectName("BtnAccionEditar")
        btn_aplicar_accesibilidad.clicked.connect(self._aplicar_accesibilidad)
        t_accesibilidad.contenido.addWidget(btn_aplicar_accesibilidad)
        disposicion.addWidget(t_accesibilidad)
        self._tarjetas_apariencia.append(t_accesibilidad)

        disposicion.addStretch()
        return contenido

    def _aplicar_accesibilidad(self):

        self.main_window.etiquetas_con_recuadro= self.chk_etiquetas_recuadro.isChecked()
        self.main_window.guardar_configuracion()
        self.main_window.aplicar_tema()
        mostrar_mensaje("exito", "Accesibilidad aplicada",
                         "Los cambios de accesibilidad visual se aplicaron correctamente.", self)

    def _aplicar_apariencia(self):

        self.main_window.tema_actual= self.combo_tema.currentText()
        self.main_window.modo_oscuro= self.chk_oscuro.isChecked()
        self.main_window.login_translucido= self.chk_login_translucido.isChecked()
        self.main_window.formato_hora= self.combo_formato_hora.currentData()
        self.main_window.formato_fecha= self.combo_formato_fecha.currentData()
        self.main_window.guardar_configuracion()
        self.main_window.aplicar_tema()
        #El interruptor ☀️/🌙 y su texto en el pie del sidebar se pintan a mano (InterruptorTema) y no forman parte del
        #stylesheet que actualiza
        #aplicar_tema(): hay que refrescarlos explícitamente aquí, igual que
        #hace animar_cambio_tema() cuando el interruptor se toca directamente, para que reflejen el modo claro/oscuro
        #recién aplicado desde aquí.
        if hasattr(self.main_window, "btn_tema"):
            self.main_window.btn_tema.poner_encendido(self.main_window.modo_oscuro)
        if hasattr(self.main_window, "lbl_tema_texto"):
            self.main_window.lbl_tema_texto.setText(
                "Modo oscuro" if self.main_window.modo_oscuro else "Modo claro")
        #El idioma todavía solo está disponible en Español: si eligieron otro, se avisa y se guarda "Español" de todas
        #formas (sin tocar el resto de configuraciones de esta pestaña, que sí se aplican normalmente arriba). El combo
        #se regresa a "Español" para que la UI no quede mostrando un idioma que en realidad no se guardó.
        idioma_seleccionado= self.combo_idioma.currentText()
        idioma_no_disponible= idioma_seleccionado != "Español"
        idioma_a_guardar= "Español" if idioma_no_disponible else idioma_seleccionado
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("UPDATE configuracion SET idioma=? WHERE id=1", (idioma_a_guardar,))
            conn.commit()
            conn.close()
            registrar_auditoria("Configuración", "Actualizó idioma", self.main_window.usuario_actual,
                               idioma_a_guardar)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar el idioma:\n{error}", self)
            return
        if idioma_no_disponible:
            self.combo_idioma.setCurrentText("Español")
            mostrar_mensaje("info", "Idioma no disponible",
                             f"El idioma \"{idioma_seleccionado}\" todavía no está implementado.\n\n"
                             "Por ahora, el Español es el único idioma disponible en AcaDeXI.\n\n"
                             "El resto de la apariencia (tema, formatos de hora y fecha) sí se "
                             "aplicó correctamente.", self)
        else:
            mostrar_mensaje("exito", "Apariencia aplicada",
                             "El tema, el idioma y los formatos de hora/fecha se aplicaron correctamente.\n\n"
                             "Los módulos que ya estaban abiertos (Calendario, Horario, Banco de Tareas, "
                             "Materias, Personal, Profesores, Estudiantes y Dashboard) mostrarán el nuevo "
                             "formato la próxima vez que se abran o se actualicen.", self)

    #---------------- USUARIOS Y ROLES (CON PAGINACIÓN Y BOTONES DEBAJO DE LA TABLA, SIN "VER DETALLE") ----------------
    def _tab_usuarios(self):

        #Envolver en scroll
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_usuarios= []

        t_form= TarjetaSeccion("👤", "Crear / Editar Usuario")
        form= QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.in_u_nombre= QLineEdit()
        limitar_campo_texto(self.in_u_nombre, 300)
        self.in_u_nombre.setPlaceholderText("Nombre completo")
        self.in_u_user= QLineEdit()
        limitar_campo_texto(self.in_u_user, 300)
        self.in_u_user.setPlaceholderText("Usuario")
        self.in_u_pass= QLineEdit()
        limitar_campo_texto(self.in_u_pass, 128)
        self.in_u_pass.setPlaceholderText("Contraseña")
        self.in_u_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.combo_u_rol= QComboBox()
        self._poblar_combo_rol_usuarios()
        conectar_tooltip_seleccion(self.combo_u_rol, self._tooltip_combo_rol_usuarios())
        self.in_u_correo= QLineEdit()
        limitar_campo_texto(self.in_u_correo, 200)
        self.in_u_correo.setPlaceholderText("Correo")
        form.addWidget(self.in_u_nombre, 0, 0)
        form.addWidget(self.in_u_user, 0, 1)
        form.addWidget(self.in_u_pass, 0, 2)
        form.addWidget(self.combo_u_rol, 1, 0)
        form.addWidget(self.in_u_correo, 1, 1)
        btn_crear= QPushButton("Crear Usuario")
        btn_crear.setIcon(icono_emoji("➕"))
        btn_crear.setIconSize(_QSize_emoji(16, 16))
        btn_crear.setObjectName("BtnAccionAgregar")
        btn_crear.clicked.connect(self._crear_usuario)
        form.addWidget(btn_crear, 1, 2)
        t_form.contenido.addLayout(form)
        disposicion.addWidget(t_form)
        self._tarjetas_usuarios.append(t_form)

        t_tabla= TarjetaSeccion("👥", "Usuarios Registrados")

        fila_cabecera_tabla_usuarios= QHBoxLayout()
        fila_cabecera_tabla_usuarios.addStretch()
        t_tabla.contenido.addLayout(fila_cabecera_tabla_usuarios)

        #--- Búsqueda (mismo diseño que horario.py: no distingue mayúsculas ni acentos) ---
        self.marco_busqueda_usuarios= QFrame()
        self.marco_busqueda_usuarios.setStyleSheet(
            "QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda_usuarios= QHBoxLayout(self.marco_busqueda_usuarios)
        lay_busqueda_usuarios.setContentsMargins(12, 0, 10, 0)
        lay_busqueda_usuarios.setSpacing(6)
        self.icono_busqueda_usuarios= IconoLupa()
        lay_busqueda_usuarios.addWidget(self.icono_busqueda_usuarios)
        self.in_buscar_usuarios= QLineEdit()
        limitar_campo_texto(self.in_buscar_usuarios, 150)
        self.in_buscar_usuarios.setPlaceholderText("Buscar por usuario, nombre, rol o correo…")
        self.in_buscar_usuarios.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda_usuarios.addWidget(self.in_buscar_usuarios, 1)
        t_tabla.contenido.addWidget(self.marco_busqueda_usuarios)

        self._temporizador_busqueda_usuarios= QTimer(self)
        self._temporizador_busqueda_usuarios.setSingleShot(True)
        self._temporizador_busqueda_usuarios.setInterval(150)
        self._temporizador_busqueda_usuarios.timeout.connect(self._filtro_usuarios_cambio)
        self.in_buscar_usuarios.textChanged.connect(lambda _t: self._temporizador_busqueda_usuarios.start())

        #Tabla estilo Omega POS (usuarios)
        self.tabla_usuarios= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_usuarios)
        self.tabla_usuarios.setHorizontalHeaderLabels(
            ["ID", "Usuario", "Nombre Completo", "Rol", "Correo", "Estado"])
        self.tabla_usuarios.setColumnHidden(0, True)
        header= self.tabla_usuarios.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_usuarios.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_usuarios.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_usuarios.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_usuarios.setAlternatingRowColors(True)
        self.tabla_usuarios.setWordWrap(True)
        self.tabla_usuarios.setMinimumHeight(380)
        self.tabla_usuarios.verticalHeader().setVisible(False)
        t_tabla.contenido.addWidget(self.tabla_usuarios, 1)

        #Paginación - con espaciado mejorado para que el combobox no quede entrecortado
        self.paginacion_usuarios= ControlPaginacion()
        self.paginacion_usuarios.cambio.connect(self._cargar_usuarios)
        #Envuelta en un QWidget real (no solo el QHBoxLayout de centrado) porque agregar_boton_pantalla_completa solo
        #puede mover WIDGETS al diálogo de pantalla completa -mismo motivo documentado en asistencia.py para
        #self.marco_paginacion_registro-.
        self.marco_paginacion_usuarios= QWidget()
        paginacion_wrapper= QHBoxLayout(self.marco_paginacion_usuarios)
        paginacion_wrapper.setContentsMargins(0, 0, 0, 0)
        paginacion_wrapper.addStretch()
        paginacion_wrapper.addWidget(self.paginacion_usuarios)
        paginacion_wrapper.addStretch()
        t_tabla.contenido.addWidget(self.marco_paginacion_usuarios)

        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_usuarios, [self.tabla_usuarios, self.marco_paginacion_usuarios],
            titulo= "Usuarios Registrados", parent=self)

        #Botones de acción debajo de la tabla
        fila_botones= QHBoxLayout()
        btn_actualizar= QPushButton("Actualizar Usuarios")
        btn_actualizar.setIcon(icono_emoji("🔄"))
        btn_actualizar.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_usuarios)
        fila_botones.addWidget(btn_actualizar)

        btn_cargar= QPushButton("Cargar Usuario")
        btn_cargar.setIcon(icono_emoji("✏"))
        btn_cargar.setIconSize(_QSize_emoji(16, 16))
        btn_cargar.setObjectName("BtnAccionEditar")
        btn_cargar.clicked.connect(self._cargar_usuario_seleccionado)
        fila_botones.addWidget(btn_cargar)

        btn_guardar_usuario= QPushButton("Guardar Cambios")
        btn_guardar_usuario.setIcon(icono_emoji("💾"))
        btn_guardar_usuario.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_usuario.setObjectName("BtnAccionAgregar")
        btn_guardar_usuario.clicked.connect(self._guardar_usuario)
        fila_botones.addWidget(btn_guardar_usuario)

        btn_limpiar_usuario= QPushButton("Limpiar")
        btn_limpiar_usuario.setIcon(icono_emoji("🧹"))
        btn_limpiar_usuario.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_usuario.setObjectName("BtnAccionNeutro")
        btn_limpiar_usuario.clicked.connect(self._limpiar_usuario)
        fila_botones.addWidget(btn_limpiar_usuario)

        btn_activar= QPushButton("Activar/Desactivar")
        btn_activar.setIcon(icono_emoji("🔘"))
        btn_activar.setIconSize(_QSize_emoji(16, 16))
        btn_activar.setObjectName("BtnAccionAjustar")
        btn_activar.clicked.connect(self._alternar_usuario)
        fila_botones.addWidget(btn_activar)

        btn_eliminar= QPushButton("Eliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_usuario)
        fila_botones.addWidget(btn_eliminar)

        btn_perfil= QPushButton("Generar Perfil (.acdx)")
        btn_perfil.setIcon(icono_emoji("👤"))
        btn_perfil.setIconSize(_QSize_emoji(16, 16))
        btn_perfil.setObjectName("BtnAccionAjustar")
        btn_perfil.clicked.connect(self._generar_perfil_usuario)
        fila_botones.addWidget(btn_perfil)

        #El botón visible se quita, pero se sigue creando (oculto) para poder reutilizar su lógica de apertura del
        #diálogo de detalle: el doble clic en la tabla sigue funcionando exactamente igual que antes.
        btn_detalle_usuario= agregar_boton_detalle(
            fila_botones, self.tabla_usuarios, self, titulo="Detalle del Usuario")
        btn_detalle_usuario.setVisible(False)
        self.tabla_usuarios.doubleClicked.connect(lambda *_: btn_detalle_usuario.click())

        fila_botones.addStretch()
        t_tabla.contenido.addLayout(fila_botones)
        disposicion.addWidget(t_tabla)
        self._tarjetas_usuarios.append(t_tabla)

        #------------------------------------------------------------------
        #MÓDULO DE PSICOLOGÍA PARA ADMINISTRADORES — visible SOLO para el rol "Administrador" (ni Director ni
        #Coordinador, aunque ambos tengan acceso gerencial al resto de esta pestaña): es un interruptor personal,
        #pensado para el caso de una institución donde el propio Administrador ejerce también de psicólogo/a y quiere
        #el módulo sin tener que crear un cargo personalizado en Side Stepper (ver permisos.puede_ver_psicologia). Se
        #guarda en `configuracion.psicologia_habilitada_admin` -es una preferencia institucional, no por usuario, igual
        #que el resto de esta pestaña.
        t_psicologia= TarjetaSeccion("🧠", "Módulo de Psicología")
        self.tarjeta_psicologia_admin= t_psicologia
        lbl_info_psic= QLabel(
            "Habilita el módulo de Psicología para la cuenta de Administrador, de modo "
            "que puedas gestionar expedientes psicológicos sin depender de un cargo "
            "personalizado en Side Stepper.")
        lbl_info_psic.setWordWrap(True)
        t_psicologia.contenido.addWidget(lbl_info_psic)
        self.chk_psicologia_admin= QCheckBox("Habilitar Psicología para el rol Administrador")
        self.chk_psicologia_admin.toggled.connect(self._guardar_psicologia_admin)
        t_psicologia.contenido.addWidget(self.chk_psicologia_admin)
        disposicion.addWidget(t_psicologia)
        self._tarjetas_usuarios.append(t_psicologia)

        scroll.setWidget(contenido)
        #No usar layout_raiz porque ya estamos dentro de una pestaña de QTabWidget
        return scroll

    def _tooltip_combo_rol_usuarios(self):

        if self._edicion_es_side_stepper():
            return ("Rol del usuario; define a qué módulos tendrá acceso. En Side Stepper "
                    "también puedes elegir (o escribir) un cargo personalizado ya configurado "
                    "en \"Permisos de Side Stepper\" -por ejemplo, \"Psicólogo/a\"-.")
        return "Rol del usuario; define a qué módulos tendrá acceso"

    def _edicion_es_side_stepper(self):

        try:

            from src.nucleo.edicion import edicion_actual
            return edicion_actual() == "side_stepper"
        except Exception:
            return False

    #Rellena el selector de rol de "Crear / Editar Usuario" con los 5
    #roles fijos y, en Side Stepper, también con los cargos
    #PERSONALIZADOS ya configurados en "Permisos de Side Stepper" (ver
    #side_stepper_config.py) -típicamente uno llamado "Psicólogo/a", pero
    #el nombre es libre-. Sin esto, un Director podía configurar un
    #cargo con el módulo "Psicología" otorgado, pero no había forma de
    #asignárselo a nadie desde esta tabla: solo existía el flujo de
    #autorregistro (WizardCrearCuentaSideStepper), lo que dejaba a medio
    #camino el sentido de tener esa configuración. Se conserva la
    #selección actual si sigue existiendo entre las opciones nuevas.
    def _poblar_combo_rol_usuarios(self):

        actual= self.combo_u_rol.currentText() if self.combo_u_rol.count() else None
        self.combo_u_rol.blockSignals(True)
        self.combo_u_rol.clear()
        self.combo_u_rol.addItems(ROLES)
        es_side_stepper= self._edicion_es_side_stepper()
        #Editable SOLO en Side Stepper: en las otras 3 ediciones los roles son un catálogo cerrado (PERMISOS_TECHO) y
        #escribir cualquier cosa aquí dejaría al usuario sin ningún módulo asignado por accidente.
        self.combo_u_rol.setEditable(es_side_stepper)
        if es_side_stepper:
            try:

                cargos_personalizados= sorted(
                    info["rol"] for info in listar_roles_side_stepper_configurados()
                    if info["rol"] not in ROLES)
            except Exception:
                cargos_personalizados= []
            if cargos_personalizados:
                self.combo_u_rol.insertSeparator(self.combo_u_rol.count())
                self.combo_u_rol.addItems(cargos_personalizados)
        if actual is not None:
            idx= self.combo_u_rol.findText(actual)
            if idx >= 0:
                self.combo_u_rol.setCurrentIndex(idx)
            elif es_side_stepper:
                self.combo_u_rol.setCurrentText(actual)
        self.combo_u_rol.blockSignals(False)

    def _crear_usuario(self):

        user= self.in_u_user.text().strip()
        pw= self.in_u_pass.text().strip()
        if not user or not pw:
            mostrar_mensaje("advertencia", "Datos incompletos", "Usuario y contraseña son obligatorios.", self)
            return
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""INSERT INTO usuarios (username, password, nombre_completo, rol, correo,
                         activo, fecha_creacion) VALUES (?, ?, ?, ?, ?, 1, ?)""",
                      (user, hash_password(pw), self.in_u_nombre.text().strip(),
                       self.combo_u_rol.currentText(), self.in_u_correo.text().strip(),
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
            registrar_auditoria("Usuarios", "Creó usuario", self.main_window.usuario_actual, user)
            self.in_u_nombre.clear()
            self.in_u_user.clear()
            self.in_u_pass.clear()
            self.in_u_correo.clear()
            self._cargar_usuarios()
            mostrar_mensaje("exito", "Usuario creado", f"Se creó la cuenta '{user}'.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo crear el usuario:\n{error}", self)

    def _guardar_psicologia_admin(self, activo):

        if getattr(self, "_cargando_psicologia_admin", False):
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE configuracion SET psicologia_habilitada_admin=? WHERE id=1", (1 if activo else 0,))
        conn.commit()
        conn.close()
        registrar_auditoria(
            "Configuración",
            "Habilitó Psicología para Administrador" if activo else "Deshabilitó Psicología para Administrador",
            getattr(self.main_window, "usuario_actual", "Sistema"), "")
        #El menú lateral necesita reconstruirse para reflejar el cambio de
        #inmediato (mostrar/ocultar "Psicología") sin pedirle al usuario
        #que cierre sesión -mismo método que usa main.py cada vez que cambian los permisos del usuario logueado en
        #caliente.
        if hasattr(self.main_window, "_aplicar_permisos_por_rol"):
            self.main_window._aplicar_permisos_por_rol()

    def _limpiar_usuario(self):

        self.in_u_nombre.clear()
        self.in_u_user.clear()
        self.in_u_pass.clear()
        self.in_u_correo.clear()
        self.combo_u_rol.setCurrentIndex(0)
        self.tabla_usuarios.clearSelection()
        desactivar_modo_edicion(self.in_u_nombre)

    def _filtro_usuarios_cambio(self):

        self.paginacion_usuarios.reiniciar()
        self._cargar_usuarios()

    def _cargar_usuarios(self):

        texto= _normalizar(self.in_buscar_usuarios.text().strip()) if hasattr(self, "in_buscar_usuarios") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM usuarios ORDER BY id DESC")
        filas= c.fetchall()
        conn.close()

        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['username']} {fila['nombre_completo'] or ''} {fila['rol']} {fila['correo'] or ''}")]

        self.paginacion_usuarios.establecer_total(len(filas))
        inicio, fin= self.paginacion_usuarios.rango_actual()
        pagina= filas[inicio:fin]

        with tabla_pausada(self.tabla_usuarios):
            self.tabla_usuarios.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_usuarios.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_usuarios.setItem(i, 1, QTableWidgetItem(f["username"]))
                self.tabla_usuarios.setItem(i, 2, QTableWidgetItem(f["nombre_completo"] or ""))
                self.tabla_usuarios.setItem(i, 3, QTableWidgetItem(f["rol"]))
                self.tabla_usuarios.setItem(i, 4, QTableWidgetItem(f["correo"] or ""))
                item_estado= QTableWidgetItem("Activo" if f["activo"] else "Inactivo")
                #Mismo criterio de color que estudiantes.py: verde para Activo, rojo para Inactivo, así se distingue de un
                #vistazo en la tabla.
                item_estado.setForeground(QColor("#16A34A") if f["activo"] else QColor("#DC2626"))
                self.tabla_usuarios.setItem(i, 5, item_estado)

    def _fila_usuario_seleccionada(self):

        fila= self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un usuario de la tabla.", self)
            return None
        return int(self.tabla_usuarios.item(fila, 0).text())

    def _alternar_usuario(self):

        id_usuario= self._fila_usuario_seleccionada()
        if id_usuario is None:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE usuarios SET activo = 1 - activo WHERE id=?", (id_usuario,))
        conn.commit()
        conn.close()
        registrar_auditoria("Usuarios", "Cambió estado de usuario", self.main_window.usuario_actual, str(id_usuario))
        self._cargar_usuarios()

    def _cargar_usuario_seleccionado(self):

        fila= self.tabla_usuarios.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un usuario de la tabla.", self)
            return
        id_usuario= int(self.tabla_usuarios.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE id=?", (id_usuario,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.in_u_nombre.setText(f["nombre_completo"] or "")
        self.in_u_user.setText(f["username"] or "")
        self.in_u_pass.clear()
        self.in_u_pass.setPlaceholderText("(dejar vacío para no cambiar la contraseña)")
        self.combo_u_rol.setCurrentText(f["rol"] or "Profesor")
        self.in_u_correo.setText(f["correo"] or "")
        activar_modo_edicion(self.in_u_nombre,
                             f"Editando usuario: {f['username'] or ''}")

    def _guardar_usuario(self):

        id_usuario= self._fila_usuario_seleccionada()
        if id_usuario is None:
            return

        nombre= self.in_u_nombre.text().strip()
        user= self.in_u_user.text().strip()
        rol= self.combo_u_rol.currentText()
        correo= self.in_u_correo.text().strip()
        pw= self.in_u_pass.text().strip()

        if not user:
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre de usuario es obligatorio.", self)
            return

        if pw and not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Permiso denegado",
                            "Solo un Administrador puede cambiar la contraseña de un usuario.", self)
            return

        try:

            conn= obtener_conexion()
            c= conn.cursor()
            if pw:
                c.execute("""UPDATE usuarios SET username=?, password=?, nombre_completo=?,
                             rol= ?, correo=? WHERE id=?""",
                          (user, hash_password(pw), nombre, rol, correo, id_usuario))
            else:
                c.execute("""UPDATE usuarios SET username=?, nombre_completo=?, rol=?,
                             correo= ? WHERE id=?""",
                          (user, nombre, rol, correo, id_usuario))
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar los cambios del usuario:\n{error}", self)
            return

        accion= "Actualizó usuario (con cambio de contraseña)" if pw else "Actualizó usuario"
        registrar_auditoria("Usuarios", accion, self.main_window.usuario_actual, user)
        self._limpiar_usuario()
        self._cargar_usuarios()
        mostrar_mensaje("exito", "Guardado", f"Se guardaron los cambios de '{user}'.", self)

    def _eliminar_usuario(self):

        id_usuario= self._fila_usuario_seleccionada()
        if id_usuario is None:
            return
        fila= self.tabla_usuarios.currentRow()
        rol= self.tabla_usuarios.item(fila, 3).text()
        rol_actual= getattr(self.main_window, "rol_actual", None)

        if rol == "Director":
            if rol_actual not in ("Administrador", "Director"):
                mostrar_mensaje("advertencia", "Operación no permitida",
                               "Solo Administradores o el Director pueden eliminar cuentas de Director.", self)
                return
            mostrar_mensaje("advertencia", "Operación no permitida", "No se puede eliminar la cuenta del Director.", self)
            return

        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar este usuario permanentemente?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM usuarios WHERE id=?", (id_usuario,))
        conn.commit()
        conn.close()
        registrar_auditoria("Usuarios", "Eliminó usuario", self.main_window.usuario_actual, str(id_usuario))
        self._cargar_usuarios()

    def _generar_perfil_usuario(self):

        id_usuario= self._fila_usuario_seleccionada()
        if id_usuario is None:
            return
        fila= self.tabla_usuarios.currentRow()
        username= self.tabla_usuarios.item(fila, 1).text()
        from src.interfaz.perfil import DialogoGenerarPerfil
        dialogo= DialogoGenerarPerfil(self.main_window, id_usuario, username)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            registrar_auditoria("Usuarios", "Generó perfil institucional (.acdx)",
                                self.main_window.usuario_actual, username)

    #---------------- MI CUENTA (autoservicio: cualquier rol con acceso a Configuración) ----------------
    def _tab_mi_cuenta(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(14)

        lbl_desc= QLabel("Gestiona tu propia cuenta: cambia tu contraseña o exporta tu Perfil Institucional "
                      "(.acdx) actualizado para importarlo en otro equipo. Desde aquí solo puedes ver y "
                      "modificar tu propia cuenta, nunca la de otro usuario.")
        lbl_desc.setObjectName("DescModulo")
        lbl_desc.setWordWrap(True)
        disposicion.addWidget(lbl_desc)

        self._tarjetas_mi_cuenta= []

        t_pass= TarjetaSeccion("🔒", "Cambiar mi Contraseña")
        form_pass= QFormLayout()
        form_pass.setSpacing(10)
        self.in_mi_pass_actual= QLineEdit()
        limitar_campo_texto(self.in_mi_pass_actual, 128)
        self.in_mi_pass_actual.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_mi_pass_actual.setPlaceholderText("Contraseña actual")
        self.in_mi_pass_nueva= QLineEdit()
        limitar_campo_texto(self.in_mi_pass_nueva, 128)
        self.in_mi_pass_nueva.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_mi_pass_nueva.setPlaceholderText("Nueva contraseña (mínimo 4 caracteres)")
        self.in_mi_pass_confirmar= QLineEdit()
        limitar_campo_texto(self.in_mi_pass_confirmar, 128)
        self.in_mi_pass_confirmar.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_mi_pass_confirmar.setPlaceholderText("Confirmar nueva contraseña")
        form_pass.addRow("Contraseña actual:", self.in_mi_pass_actual)
        form_pass.addRow("Nueva contraseña:", self.in_mi_pass_nueva)
        form_pass.addRow("Confirmar nueva contraseña:", self.in_mi_pass_confirmar)
        t_pass.contenido.addLayout(form_pass)
        btn_cambiar_pass= QPushButton("Cambiar mi Contraseña")
        btn_cambiar_pass.setIcon(icono_emoji("🔑"))
        btn_cambiar_pass.setIconSize(_QSize_emoji(16, 16))
        btn_cambiar_pass.setObjectName("BtnAccionAgregar")
        btn_cambiar_pass.clicked.connect(self._cambiar_mi_password)
        t_pass.contenido.addWidget(btn_cambiar_pass)
        disposicion.addWidget(t_pass)
        self._tarjetas_mi_cuenta.append(t_pass)

        t_perfil= TarjetaSeccion(
            "", "Exportar mi Perfil Institucional (.acdx)",
            "Genera tu propio archivo .acdx actualizado, con tu contraseña vigente incluida y "
            "cifrada con un PIN que tú mismo defines, para poder importarlo directamente en otro "
            "equipo sin escribirla de nuevo. El PIN NO viaja dentro del archivo: comunícatelo a ti "
            "mismo por otra vía (anótalo aparte) o, si es para otra persona, dáselo por un canal "
            "distinto al del archivo. Guarda el .acdx en un lugar seguro de todas formas: aunque "
            "sin el PIN nadie puede recuperar tu contraseña, el resto del perfil (usuario, rol, "
            "institución) sí queda legible por quien tenga la clave de la app.")
        btn_exportar_mi_perfil= QPushButton("Exportar mi Perfil (.acdx)")
        btn_exportar_mi_perfil.setIcon(icono_emoji("\uE002"))
        btn_exportar_mi_perfil.setIconSize(_QSize_emoji(16, 16))
        btn_exportar_mi_perfil.setObjectName("BtnAccionEditar")
        btn_exportar_mi_perfil.clicked.connect(self._exportar_mi_perfil)
        t_perfil.contenido.addWidget(btn_exportar_mi_perfil)
        disposicion.addWidget(t_perfil)
        self._tarjetas_mi_cuenta.append(t_perfil)

        #---------------- Preferencias de la aplicación en este equipo ---------------- Es una preferencia por
        #dispositivo (como el tema o el idioma en Apariencia), no una config institucional, así que vive aquí en Mi
        #Cuenta: esta pestaña es visible para TODOS los roles, incluido Profesor, a diferencia de "Seguridad y Backups"
        #(solo gerencial). Así el Modo Docente también puede configurarla.
        t_app= TarjetaSeccion("⚙", "Preferencias de la Aplicación")
        self.chk_minimizar_bandeja= QCheckBox(
            "Ejecutar en segundo plano al cerrar la ventana (bandeja del sistema)")
        self.chk_minimizar_bandeja.setToolTip(
            "Activado (por defecto): al hacer clic en la 'X' de la ventana, AcaDeXI no se "
            "cierra — se oculta y sigue ejecutándose en segundo plano con un icono en la "
            "bandeja del sistema (junto al reloj de Windows). Haz doble clic en ese icono para "
            "volver a abrir la ventana, o clic derecho ▸ Salir para cerrar la aplicación de "
            "verdad.\n\n"
            "Desactivado: la 'X' cierra la aplicación normalmente, como cualquier programa "
            "tradicional.\n\n"
            "Es una preferencia de este equipo, no de la institución: cada usuario la "
            "configura para su propia sesión de Windows, sin importar su rol.")
        t_app.contenido.addWidget(self.chk_minimizar_bandeja)

        #--- Tecla para ver la ventanita de atajos de teclado --- Decisión 100% del propio usuario, por eso vive acá
        #(Mi Cuenta, visible para todos los roles) y no en Apariencia, que es la config visual de la
        #institución/equipo.
        linea_atajos= QFrame()
        linea_atajos.setFrameShape(QFrame.Shape.HLine)
        t_app.contenido.addWidget(linea_atajos)
        lbl_desc_atajos= QLabel(
            "AcaDeXI tiene atajos de teclado en la mayoría de los módulos. Para "
            "descubrirlos, mantén presionada la tecla que elijas aquí: mientras la "
            "mantengas abajo aparece una ventanita con los atajos del módulo que "
            "tengas abierto en ese momento, y desaparece sola al soltarla (no "
            "interrumpe nada de lo que estés haciendo).")
        lbl_desc_atajos.setObjectName("DescModulo")
        lbl_desc_atajos.setWordWrap(True)
        t_app.contenido.addWidget(lbl_desc_atajos)
        fila_atajos= QHBoxLayout()
        fila_atajos.setSpacing(12)
        lbl_tecla_atajos= QLabel("Tecla para ver los atajos:")
        fila_atajos.addWidget(lbl_tecla_atajos, 0, Qt.AlignmentFlag.AlignVCenter)
        self.combo_tecla_atajos= QComboBox()
        self.combo_tecla_atajos.addItems(list(TECLAS_ATAJO_DISPONIBLES.keys()))
        self.combo_tecla_atajos.setMinimumHeight(33)
        conectar_tooltip_seleccion(self.combo_tecla_atajos,
            "Tecla que hay que mantener presionada para que aparezca la ventanita "
            "de atajos. Cámbiala si esta tecla choca con algo de tu teclado, tu "
            "sistema operativo o tu software de accesibilidad.")
        fila_atajos.addWidget(self.combo_tecla_atajos, 1, Qt.AlignmentFlag.AlignVCenter)
        t_app.contenido.addLayout(fila_atajos)

        btn_guardar_app= QPushButton("Guardar Preferencia")
        btn_guardar_app.setIcon(icono_emoji("💾"))
        btn_guardar_app.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_app.setObjectName("BtnAccionEditar")
        btn_guardar_app.clicked.connect(self._guardar_preferencias_app)
        t_app.contenido.addWidget(btn_guardar_app)
        disposicion.addWidget(t_app)
        self._tarjetas_mi_cuenta.append(t_app)

        #---------------- Alarmas y Recordatorios ---------------- Igual que el resto de esta pestaña: es una
        #preferencia 100% del propio usuario/equipo (tono, volumen, efecto visual, recordatorios manuales), no
        #institucional, así que vive aquí y no en Apariencia ni en Seguridad. Visible para todos los roles, incluido
        #Profesor.
        t_alarmas= TarjetaSeccion(
            "", "Alarmas y Recordatorios",
            "Personaliza el tono, el volumen y el efecto visual con que AcaDeXI te avisa "
            "cuando empieza un evento del Calendario, una clase de tu horario, o un "
            "recordatorio que crees tú mismo aquí abajo.")
        self.panel_alarmas= PanelAlarmas(self.main_window)
        t_alarmas.contenido.addWidget(self.panel_alarmas)
        disposicion.addWidget(t_alarmas)
        self._tarjetas_mi_cuenta.append(t_alarmas)

        #---------------- "Calificaciones Técnicas" en mi menú (solo Profesor) ---------------- Decisión manual del
        #propio docente en instituciones donde el módulo técnico es algo puntual: activarla NO depende de si imparte o
        #no una materia técnica (especialidad_id). Solo aplica al rol Profesor -los roles gerenciales siempre ven el
        #módulo cuando la institución es Politécnico, sin este checkbox- y solo tiene efecto si la institución
        #configurada es de tipo Politécnico (si no, el módulo no existe para nadie, esté marcado o no).
        ##EXCEPCIÓN: si la institución ES Politécnico (o "Personalizado" con el módulo Politécnico activo), se asume que
        #es la norma para todos los docentes, así que se activa sola (ver main.py ▸ mostrar_login) y este checkbox
        #queda fijo/informativo — no tiene sentido pedirle al docente que la "active" cuando ya está encendida para
        #todos.
        self.t_calif_tecnicas= None
        self.btn_guardar_calif_tecnicas= None
        if getattr(self.main_window, "rol_actual", None) == "Profesor":
            t_calif= TarjetaSeccion(
                "", "Mostrar \"Calificaciones Técnicas\" en mi menú",
                "Actívalo si quieres ver el módulo de Calificaciones Técnicas en tu barra lateral. "
                "Es tu propia decisión: puedes activarlo aunque no impartas una materia técnica, o "
                "dejarlo desactivado aunque sí la impartas. Solo aparece si tu institución está "
                "configurada como Politécnico. Si tu institución ES un Politécnico, esta opción se "
                "activa automáticamente para todos los docentes y el checkbox queda fijo (ya no hace "
                "falta activarla a mano).")
            self.chk_calif_tecnicas= QCheckBox("Mostrar \"Calificaciones Técnicas\" en mi menú")
            t_calif.contenido.addWidget(self.chk_calif_tecnicas)
            self.btn_guardar_calif_tecnicas= QPushButton("Guardar Preferencia")
            self.btn_guardar_calif_tecnicas.setIcon(icono_emoji("💾"))
            self.btn_guardar_calif_tecnicas.setIconSize(_QSize_emoji(16, 16))
            self.btn_guardar_calif_tecnicas.setObjectName("BtnAccionEditar")
            self.btn_guardar_calif_tecnicas.clicked.connect(self._guardar_preferencia_calif_tecnicas)
            t_calif.contenido.addWidget(self.btn_guardar_calif_tecnicas)
            disposicion.addWidget(t_calif)
            self._tarjetas_mi_cuenta.append(t_calif)
            self.t_calif_tecnicas= t_calif
            self._actualizar_estado_calif_tecnicas()

        #---------------- Tutorial de primer uso (repetible manualmente) ---------------- En Modo Docente (rol
        #Profesor) solo existe UN tutorial -el propio del sistema para ese rol-, así que no se ofrece el general por
        #separado ni se usa la etiqueta "Modo Docente": de cara al docente es, simplemente, "el tutorial del sistema".
        es_docente= getattr(self.main_window, "rol_actual", None) == "Profesor"
        try:

            from src.nucleo.edicion import edicion_actual
            _edicion_tutorial= edicion_actual()
        except Exception:
            _edicion_tutorial= "full"
        t_tutorial= TarjetaSeccion(
            EMOJI_TUTORIAL, "Tutorial de AcaDeXI",
            "Repite el recorrido de bienvenida cuando quieras."
            if es_docente else
            "Repite el recorrido de bienvenida cuando quieras. El tutorial general cubre la app "
            "completa; el del Modo Docente solo aparece si tu rol es Profesor.")
        if _edicion_tutorial == "single_teacher":
            btn_tutorial_single_teacher= QPushButton("Ver tutorial de nuevo")
            btn_tutorial_single_teacher.setIcon(icono_emoji(EMOJI_TUTORIAL))
            btn_tutorial_single_teacher.setIconSize(_QSize_emoji(16, 16))
            btn_tutorial_single_teacher.setObjectName("BtnAccionEditar")
            btn_tutorial_single_teacher.clicked.connect(self._ver_tutorial_single_teacher_de_nuevo)
            t_tutorial.contenido.addWidget(btn_tutorial_single_teacher)
        elif _edicion_tutorial == "side_stepper":
            btn_tutorial_side_stepper= QPushButton("Ver tutorial de nuevo")
            btn_tutorial_side_stepper.setIcon(icono_emoji(EMOJI_TUTORIAL))
            btn_tutorial_side_stepper.setIconSize(_QSize_emoji(16, 16))
            btn_tutorial_side_stepper.setObjectName("BtnAccionEditar")
            btn_tutorial_side_stepper.clicked.connect(self._ver_tutorial_side_stepper_de_nuevo)
            t_tutorial.contenido.addWidget(btn_tutorial_side_stepper)
        elif es_docente:
            btn_tutorial_docente= QPushButton("Ver tutorial del sistema de nuevo")
            btn_tutorial_docente.setIcon(icono_emoji(EMOJI_TUTORIAL))
            btn_tutorial_docente.setIconSize(_QSize_emoji(16, 16))
            btn_tutorial_docente.setObjectName("BtnAccionEditar")
            btn_tutorial_docente.clicked.connect(self._ver_tutorial_docente_de_nuevo)
            t_tutorial.contenido.addWidget(btn_tutorial_docente)
        else:
            btn_tutorial_general= QPushButton("Ver tutorial general de nuevo")
            btn_tutorial_general.setIcon(icono_emoji(EMOJI_TUTORIAL))
            btn_tutorial_general.setIconSize(_QSize_emoji(16, 16))
            btn_tutorial_general.setObjectName("BtnAccionEditar")
            btn_tutorial_general.clicked.connect(self._ver_tutorial_general_de_nuevo)
            t_tutorial.contenido.addWidget(btn_tutorial_general)
        disposicion.addWidget(t_tutorial)
        self._tarjetas_mi_cuenta.append(t_tutorial)

        disposicion.addStretch()
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        return scroll

    def _ver_tutorial_general_de_nuevo(self):

        from src.inicio.tutoriales import ofrecer_tutorial
        ofrecer_tutorial(self.main_window, "general", forzar=True)

    def _ver_tutorial_docente_de_nuevo(self):

        from src.inicio.tutoriales import ofrecer_tutorial
        ofrecer_tutorial(self.main_window, "docente", forzar=True)

    def _ver_tutorial_single_teacher_de_nuevo(self):

        from src.inicio.tutoriales import ofrecer_tutorial
        ofrecer_tutorial(self.main_window, "single_teacher", forzar=True)

    def _ver_tutorial_side_stepper_de_nuevo(self):

        from src.inicio.tutoriales import ofrecer_tutorial
        ofrecer_tutorial(self.main_window, "side_stepper", forzar=True)

    def _cambiar_mi_password(self):

        id_usuario= getattr(self.main_window, "id_usuario_actual", None)
        if id_usuario is None:
            mostrar_mensaje("advertencia", "Sin sesión", "No se detectó un usuario con sesión iniciada.", self)
            return
        actual= self.in_mi_pass_actual.text().strip()
        nueva= self.in_mi_pass_nueva.text().strip()
        confirmar= self.in_mi_pass_confirmar.text().strip()
        if not actual or not nueva:
            mostrar_mensaje("advertencia", "Datos incompletos", "Completa tu contraseña actual y la nueva.", self)
            return
        if len(nueva) < 4:
            mostrar_mensaje("advertencia", "Contraseña muy corta", "Usa al menos 4 caracteres.", self)
            return
        if nueva != confirmar:
            mostrar_mensaje("advertencia", "No coincide",
                            "La nueva contraseña y su confirmación no coinciden.", self)
            return
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT password FROM usuarios WHERE id=?", (id_usuario,))
            fila= c.fetchone()
            if not fila or not verificar_contrasena(actual, fila["password"]):
                conn.close()
                mostrar_mensaje("error", "Contraseña incorrecta", "Tu contraseña actual no es correcta.", self)
                return
            c.execute("UPDATE usuarios SET password=? WHERE id=?", (hash_password(nueva), id_usuario))
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo cambiar la contraseña:\n{error}", self)
            return
        registrar_auditoria("Seguridad", "Cambió su propia contraseña", self.main_window.usuario_actual)
        self.in_mi_pass_actual.clear()
        self.in_mi_pass_nueva.clear()
        self.in_mi_pass_confirmar.clear()
        mostrar_mensaje("exito", "Contraseña actualizada", "Tu contraseña se cambió correctamente. Recuerda "
                        "usarla la próxima vez que inicies sesión (y actualiza tu perfil .acdx si lo usas "
                        "para iniciar sesión).", self)

    def _exportar_mi_perfil(self):

        from src.interfaz.perfil import DialogoExportarPerfilPropio
        if getattr(self.main_window, "id_usuario_actual", None) is None:
            mostrar_mensaje("advertencia", "Sin sesión", "No se detectó un usuario con sesión iniciada.", self)
            return
        dialogo= DialogoExportarPerfilPropio(self.main_window)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            registrar_auditoria("Usuarios", "Exportó su propio perfil institucional (.acdx)",
                                self.main_window.usuario_actual)

    def _guardar_preferencias_app(self):

        #_establecer_minimizar_a_bandeja ya llama a guardar_configuracion() por su cuenta y sincroniza el checkbox del menú de la
        #bandeja del sistema.
        if hasattr(self.main_window, "_establecer_minimizar_a_bandeja"):
            self.main_window._establecer_minimizar_a_bandeja(self.chk_minimizar_bandeja.isChecked())
        self.main_window.tecla_atajos= self.combo_tecla_atajos.currentText()
        self.main_window.guardar_configuracion()
        mostrar_mensaje("exito", "Guardado",
                         "Preferencia de la aplicación actualizada.\n\n"
                         f"Ahora hay que mantener presionada la tecla "
                         f"\"{self.main_window.tecla_atajos}\" para ver la ventanita de atajos.", self)

    #Si la institución es un Politécnico (o "Personalizado" con el
    #módulo Politécnico activo), "Calificaciones Técnicas" se activa sola
    #para todos los docentes (ver main.py ▸ mostrar_login) y este checkbox
    #pasa a ser solo informativo: se muestra marcado y bloqueado, en vez
    #de sugerir un control que en la práctica ya no decide nada.
    def _actualizar_estado_calif_tecnicas(self):

        if getattr(self, "chk_calif_tecnicas", None) is None:
            return
        tipo_inst, personalizados_inst= self.main_window._tipo_institucion()
        es_politecnico_inst= (tipo_inst == "Politécnico"
                                or (tipo_inst == "Personalizado" and "Politécnico" in personalizados_inst))
        self.chk_calif_tecnicas.setEnabled(not es_politecnico_inst)
        if getattr(self, "btn_guardar_calif_tecnicas", None) is not None:
            self.btn_guardar_calif_tecnicas.setEnabled(not es_politecnico_inst)
        if es_politecnico_inst:
            self.chk_calif_tecnicas.setChecked(True)
            self.chk_calif_tecnicas.setToolTip(
                "Activa automáticamente para todos los docentes: esta institución está "
                "configurada como Politécnico.")
        else:
            self.chk_calif_tecnicas.setToolTip("")

    def _guardar_preferencia_calif_tecnicas(self):

        from src.nucleo.permisos import guardar_preferencia_calif_tecnicas
        if getattr(self.main_window, "id_usuario_actual", None) is None:
            mostrar_mensaje("advertencia", "Sin sesión", "No se detectó un usuario con sesión iniciada.", self)
            return
        activo= self.chk_calif_tecnicas.isChecked()
        guardar_preferencia_calif_tecnicas(self.main_window, activo)
        #Refresca de inmediato la barra lateral, sin esperar a un nuevo login.
        if hasattr(self.main_window, "_aplicar_permisos_por_rol"):
            self.main_window._aplicar_permisos_por_rol()
        registrar_auditoria(
            "Configuración",
            f"{'Activó' if activo else 'Desactivó'} ver \"Calificaciones Técnicas\" en su menú",
            self.main_window.usuario_actual)
        mostrar_mensaje("exito", "Guardado", "Preferencia actualizada.", self)

    #---------------- SEGURIDAD Y BACKUPS ----------------
    def _tab_seguridad(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_seguridad= []

        #---------------- Inicio de sesión ----------------
        t_login= TarjetaSeccion("🔑", "Inicio de Sesión")
        self.chk_requerir_login= QCheckBox("Requerir inicio de sesión al abrir la aplicación")
        t_login.contenido.addWidget(self.chk_requerir_login)
        #(El checkbox de "ejecutar en segundo plano" vive ahora en la pestaña Mi Cuenta — ver
        #_tab_mi_cuenta/_guardar_preferencias_app — porque es una preferencia de equipo visible también para el rol
        #Profesor, no una config de seguridad institucional.)
        btn_guardar_seg= QPushButton("Guardar Preferencias de Seguridad")
        btn_guardar_seg.setIcon(icono_emoji("💾"))
        btn_guardar_seg.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_seg.setObjectName("BtnAccionEditar")
        btn_guardar_seg.clicked.connect(self._guardar_seguridad)
        t_login.contenido.addWidget(btn_guardar_seg)
        disposicion.addWidget(t_login)
        self._tarjetas_seguridad.append(t_login)

        #---------------- Correo (SMTP) ----------------
        t_smtp= TarjetaSeccion("✉", "Correo (SMTP)",
                                 "Para recuperación de contraseña por correo.")
        form_smtp= QFormLayout()
        form_smtp.setSpacing(10)
        self.in_smtp_host= QLineEdit()
        limitar_campo_texto(self.in_smtp_host, 300)
        self.in_smtp_host.setPlaceholderText("smtp.gmail.com")
        self.spin_smtp_puerto= QSpinBox()
        self.spin_smtp_puerto.setRange(1, 65535)
        self.spin_smtp_puerto.setValue(587)
        self.spin_smtp_puerto.setToolTip("Puerto del servidor SMTP (ej. 587 para TLS, 465 para SSL)")
        self.in_smtp_usuario= QLineEdit()
        limitar_campo_texto(self.in_smtp_usuario, 300)
        self.in_smtp_usuario.setPlaceholderText("cuenta@dominio.com")
        self.in_smtp_password= QLineEdit()
        limitar_campo_texto(self.in_smtp_password, 128)
        self.in_smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_smtp_password.setPlaceholderText("Contraseña o clave de aplicación")
        self.in_smtp_remitente= QLineEdit()
        limitar_campo_texto(self.in_smtp_remitente, 300)
        self.in_smtp_remitente.setPlaceholderText("AcaDeXI <cuenta@dominio.com>")
        self.combo_smtp_seguridad= QComboBox()
        self.combo_smtp_seguridad.addItems(["TLS", "SSL", "Ninguna"])
        conectar_tooltip_seleccion(self.combo_smtp_seguridad, "Tipo de cifrado/seguridad usado por el servidor de correo")
        form_smtp.addRow("Servidor SMTP:", self.in_smtp_host)
        form_smtp.addRow("Puerto:", self.spin_smtp_puerto)
        form_smtp.addRow("Usuario SMTP:", self.in_smtp_usuario)
        form_smtp.addRow("Contraseña SMTP:", self.in_smtp_password)
        form_smtp.addRow("Remitente:", self.in_smtp_remitente)
        form_smtp.addRow("Seguridad:", self.combo_smtp_seguridad)
        t_smtp.contenido.addLayout(form_smtp)
        btn_guardar_smtp= QPushButton("Guardar Configuración de Correo")
        btn_guardar_smtp.setIcon(icono_emoji("💾"))
        btn_guardar_smtp.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_smtp.setObjectName("BtnAccionEditar")
        btn_guardar_smtp.clicked.connect(self._guardar_smtp)
        btn_probar_smtp= QPushButton("Enviar Correo de Prueba")
        btn_probar_smtp.setIcon(icono_emoji("✉"))
        btn_probar_smtp.setIconSize(_QSize_emoji(16, 16))
        btn_probar_smtp.setObjectName("BtnAccionAjustar")
        btn_probar_smtp.clicked.connect(self._probar_smtp)
        fila_smtp_btn= QHBoxLayout()
        fila_smtp_btn.addWidget(btn_guardar_smtp)
        fila_smtp_btn.addWidget(btn_probar_smtp)
        fila_smtp_btn.addStretch()
        t_smtp.contenido.addLayout(fila_smtp_btn)
        disposicion.addWidget(t_smtp)
        self._tarjetas_seguridad.append(t_smtp)

        #---------------- Copias de Seguridad (Backup) ----------------
        t_backup= TarjetaSeccion(EMOJI_COPIA_SEGURIDAD, "Copias de Seguridad (Backup)")
        fila_backup_cfg= QGridLayout()
        fila_backup_cfg.setHorizontalSpacing(12)
        fila_backup_cfg.setVerticalSpacing(8)
        fila_backup_cfg.addWidget(QLabel("Backup automático:"), 0, 0)
        self.combo_backup_modo= QComboBox()
        self.combo_backup_modo.addItems(["Manual", "Al cerrar", "Diario", "Semanal", "Mensual"])
        conectar_tooltip_seleccion(self.combo_backup_modo, "Frecuencia con la que se creará automáticamente una copia de seguridad")
        fila_backup_cfg.addWidget(self.combo_backup_modo, 0, 1)
        fila_backup_cfg.addWidget(QLabel("Modo de destino:"), 1, 0)
        self.lbl_modo_destino= QLabel("Local (interno) + carpeta personalizada opcional abajo")
        self.lbl_modo_destino.setObjectName("DescModulo")
        fila_backup_cfg.addWidget(self.lbl_modo_destino, 1, 1)
        fila_backup_cfg.addWidget(QLabel("Carpeta Personalizada (opcional):"), 2, 0)
        self.in_backup_carpeta= QLineEdit()
        limitar_campo_texto(self.in_backup_carpeta, 300)
        self.in_backup_carpeta.setPlaceholderText("Disco externo, o carpeta local de Drive/OneDrive/Dropbox/NAS")
        fila_backup_cfg.addWidget(self.in_backup_carpeta, 2, 1)
        btn_examinar_backup= QPushButton("")
        btn_examinar_backup.setIcon(icono_emoji("📁"))
        btn_examinar_backup.setIconSize(_QSize_emoji(16, 16))
        btn_examinar_backup.setObjectName("BtnAccionNeutro")
        btn_examinar_backup.clicked.connect(self._elegir_carpeta_backup)
        fila_backup_cfg.addWidget(btn_examinar_backup, 2, 2)
        t_backup.contenido.addLayout(fila_backup_cfg)
        self.chk_backups_gerenciales= QCheckBox(
            "Mostrar también 'Copias de Seguridad' en el menú lateral de Administrador/Director/Coordinador")
        self.chk_backups_gerenciales.setToolTip(
            "Por defecto está oculto para estos roles, ya que aquí mismo (Configuración ▸ Seguridad) "
            "tienen la misma función. El rol Profesor siempre la ve, porque no tiene acceso a Configuración.")
        t_backup.contenido.addWidget(self.chk_backups_gerenciales)
        btn_guardar_backup_cfg= QPushButton("Guardar Preferencias de Backup")
        btn_guardar_backup_cfg.setIcon(icono_emoji("💾"))
        btn_guardar_backup_cfg.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_backup_cfg.setObjectName("BtnAccionEditar")
        btn_guardar_backup_cfg.clicked.connect(self._guardar_config_backup)
        t_backup.contenido.addWidget(btn_guardar_backup_cfg)
        self.lbl_ultimo_backup= QLabel("")
        self.lbl_ultimo_backup.setObjectName("DescModulo")
        t_backup.contenido.addWidget(self.lbl_ultimo_backup)
        fila_backup= QHBoxLayout()
        btn_crear_backup= QPushButton("Crear Backup Ahora")
        btn_crear_backup.setIcon(icono_emoji(EMOJI_COPIA_SEGURIDAD))
        btn_crear_backup.setIconSize(_QSize_emoji(16, 16))
        btn_crear_backup.setObjectName("BtnAccionAgregar")
        btn_crear_backup.clicked.connect(self._crear_backup)
        btn_restaurar= QPushButton("Restaurar Backup")
        btn_restaurar.setIcon(icono_emoji("♻"))
        btn_restaurar.setIconSize(_QSize_emoji(16, 16))
        btn_restaurar.setObjectName("BtnAccionAjustar")
        btn_restaurar.clicked.connect(self._restaurar_backup)
        fila_backup.addWidget(btn_crear_backup)
        fila_backup.addWidget(btn_restaurar)
        fila_backup.addStretch()
        t_backup.contenido.addLayout(fila_backup)
        disposicion.addWidget(t_backup)
        self._tarjetas_seguridad.append(t_backup)

        #---------------- Estudiantes y Cursos para Modo Docente ----------------
        t_docente= TarjetaSeccion(
            "", "Estudiantes y Cursos para Modo Docente",
            "Genera un paquete con los grados, secciones, materias y estudiantes matriculados "
            "(configurados aquí por Dirección/Coordinación/Administración) para que los profesores "
            "lo importen en su propia instalación (Modo Docente). Los docentes no pueden elegir "
            "qué estudiantes están en cada curso ni crear cursos: solo importan lo que tú exportas.\n"
            "Puedes exportar el paquete institucional completo, o un paquete individual acotado "
            "solo a las materias/secciones/estudiantes de un profesor específico (como titular o "
            "como co-docente asignado en Materias ▸ Co-Docentes).")
        fila_export_docente= QHBoxLayout()
        self.combo_profesor_export_docente= QComboBox()
        self.combo_profesor_export_docente.setMinimumWidth(260)
        conectar_tooltip_seleccion(self.combo_profesor_export_docente,
                                    "Profesor para el cual se exportará el paquete de Estudiantes y Cursos")
        fila_export_docente.addWidget(self.combo_profesor_export_docente)
        btn_exportar_docente= QPushButton("Exportar Estudiantes y Cursos")
        btn_exportar_docente.setIcon(icono_emoji("\uE002"))
        btn_exportar_docente.setIconSize(_QSize_emoji(16, 16))
        btn_exportar_docente.setObjectName("BtnAccionAjustar")
        btn_exportar_docente.clicked.connect(self._exportar_paquete_docente_click)
        self.btn_exportar_docente= btn_exportar_docente
        fila_export_docente.addWidget(btn_exportar_docente)
        fila_export_docente.addStretch()
        t_docente.contenido.addLayout(fila_export_docente)
        disposicion.addWidget(t_docente)
        self._tarjetas_seguridad.append(t_docente)

        #---------------- Historial de Copias de Seguridad ----------------
        t_historial= TarjetaSeccion("🕒", "Historial de Copias de Seguridad",
                                      "Últimas 100 copias registradas por el sistema.")
        fila_hist_backup= QHBoxLayout()
        fila_hist_backup.addStretch()
        btn_actualizar_backups= QPushButton("Actualizar")
        btn_actualizar_backups.setIcon(icono_emoji("🔄"))
        btn_actualizar_backups.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_backups.setObjectName("BtnAccionNeutro")
        btn_actualizar_backups.clicked.connect(self._cargar_historial_backups)
        fila_hist_backup.addWidget(btn_actualizar_backups)
        t_historial.contenido.addLayout(fila_hist_backup)

        self.tabla_backups= QTableWidget(0, 5)
        aplicar_estructura_tabla(self.tabla_backups)
        self.tabla_backups.setHorizontalHeaderLabels(["Fecha", "Tipo", "Destino", "Tamaño", "Estado"])
        header_backups= self.tabla_backups.horizontalHeader()
        header_backups.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_backups.setStretchLastSection(True)
        header_backups.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_backups.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_backups.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_backups.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_backups.setAlternatingRowColors(True)
        self.tabla_backups.setWordWrap(True)
        self.tabla_backups.verticalHeader().setVisible(False)
        t_historial.contenido.addWidget(self.tabla_backups, 1)

        fila_botones_backups= QHBoxLayout()
        btn_detalle_backup= agregar_boton_detalle(
            fila_botones_backups, self.tabla_backups, self, titulo="Detalle de la Copia de Seguridad")
        self.tabla_backups.doubleClicked.connect(lambda *_: btn_detalle_backup.click())
        fila_botones_backups.addStretch()
        t_historial.contenido.addLayout(fila_botones_backups)

        agregar_boton_pantalla_completa(
            fila_hist_backup, [self.tabla_backups], titulo="Historial de Copias de Seguridad", parent=self)

        disposicion.addWidget(t_historial)
        self._tarjetas_seguridad.append(t_historial)

        #---------------- BD Base Institucional ----------------
        t_bd_base= TarjetaSeccion(
            "", "BD Base Institucional",
            "Copia curada de la base de datos (estructura institucional: grados, secciones, "
            "materias, usuarios...) que se usa como punto de partida para Docentes/Personal, en "
            "vez de tu base de datos actual con tus datos personales. Guárdala aquí ANTES de "
            "generar perfiles .acdx con base de datos incluida.")
        self.lbl_estado_bd_base= QLabel("")
        self.lbl_estado_bd_base.setObjectName("DescModulo")
        self.lbl_estado_bd_base.setWordWrap(True)
        t_bd_base.contenido.addWidget(self.lbl_estado_bd_base)
        fila_bd_base= QHBoxLayout()
        self.btn_guardar_bd_base= QPushButton("Guardar Copia Actual como BD Base")
        self.btn_guardar_bd_base.setIcon(icono_emoji("💾"))
        self.btn_guardar_bd_base.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_bd_base.setObjectName("BtnAccionAgregar")
        self.btn_guardar_bd_base.clicked.connect(self._guardar_bd_base)
        fila_bd_base.addWidget(self.btn_guardar_bd_base)
        self.btn_quitar_bd_base= QPushButton("Quitar BD Base")
        self.btn_quitar_bd_base.setIcon(icono_emoji("🗑"))
        self.btn_quitar_bd_base.setIconSize(_QSize_emoji(16, 16))
        self.btn_quitar_bd_base.setObjectName("BtnAccionEliminar")
        self.btn_quitar_bd_base.clicked.connect(self._quitar_bd_base)
        fila_bd_base.addWidget(self.btn_quitar_bd_base)
        fila_bd_base.addStretch()
        t_bd_base.contenido.addLayout(fila_bd_base)
        disposicion.addWidget(t_bd_base)
        self._tarjetas_seguridad.append(t_bd_base)

        #---------------- Perfil Institucional (.acdx) para un Usuario ----------------
        t_perfil= TarjetaSeccion(
            "", "Perfil Institucional (.acdx) para un Usuario",
            "Genera el archivo .acdx de cualquier usuario en un solo paso: elige la persona en el "
            "diálogo y luego dónde guardarlo — sin tener que ir primero a Usuarios y Roles a "
            "buscarla y seleccionarla en la tabla.")
        fila_perfil= QHBoxLayout()
        self.btn_generar_perfil_usuario= QPushButton("Generar Perfil (.acdx) para un Usuario")
        self.btn_generar_perfil_usuario.setIcon(icono_emoji("👤"))
        self.btn_generar_perfil_usuario.setIconSize(_QSize_emoji(16, 16))
        self.btn_generar_perfil_usuario.setObjectName("BtnAccionAgregar")
        self.btn_generar_perfil_usuario.clicked.connect(self._generar_perfil_usuario_libre)
        fila_perfil.addWidget(self.btn_generar_perfil_usuario)
        fila_perfil.addStretch()
        t_perfil.contenido.addLayout(fila_perfil)
        disposicion.addWidget(t_perfil)
        self._tarjetas_seguridad.append(t_perfil)

        #---------------- Instalador para Docentes/Personal (.exe) ----------------
        t_instalador= TarjetaSeccion(
            "", "Instalador para Docentes/Personal (.exe)",
            "Este instalador NO trae ninguna base de datos: solo instala la aplicación. Es el "
            "MISMO archivo para todos — se compila UNA sola vez con Inno Setup a partir de "
            "AcaDeXI_Docentes.iss. Entrega ese instalador + el .acdx de cada persona (Usuarios y "
            "Roles Generar Perfil, con la BD Base incluida) y así, al instalar e importar su "
            "acdx, cada quien queda listo: perfil, contraseña y estructura institucional en un "
            "solo paso. Si incluiste su contraseña al generar el .acdx, no olvides darle también "
            "el PIN por separado (llamada, WhatsApp, etc.) — sin él, tendrá que escribir su "
            "contraseña manualmente al importar.")
        fila_instalador= QHBoxLayout()
        self.btn_exportar_instalador_docentes= QPushButton("Exportar Instalador para Docentes/Personal")
        self.btn_exportar_instalador_docentes.setIcon(icono_emoji("\uE002"))
        self.btn_exportar_instalador_docentes.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar_instalador_docentes.setObjectName("BtnAccionAgregar")
        self.btn_exportar_instalador_docentes.clicked.connect(self._exportar_instalador_docentes)
        fila_instalador.addWidget(self.btn_exportar_instalador_docentes)
        fila_instalador.addStretch()
        t_instalador.contenido.addLayout(fila_instalador)
        disposicion.addWidget(t_instalador)
        self._tarjetas_seguridad.append(t_instalador)

        #---------------- Exportar Side Stepper (roles no-docentes) ----------------
        t_side_stepper= TarjetaSeccion(
            "", "Exportar Side Stepper (roles no-docentes)",
            "Para Coordinación u otros cargos no-docentes. A diferencia de Docentes, aquí tú "
            "decides qué módulos tendrá cada rol de ESTA copia en particular antes de "
            "exportarla — incluso puedes crear un rol nuevo si ninguno de los 5 roles fijos "
            "describe bien el cargo (ej. \"Bibliotecario\"). El instalador es el MISMO archivo "
            "siempre (AcaDeXI_SideStepper_Setup.exe, compilado UNA vez con Inno Setup a partir "
            "de AcaDeXI_SideStepper.iss); lo que cambia por copia es el paquete de permisos que "
            "generas abajo.")
        fila_ss_1= QHBoxLayout()
        btn_configurar_side_stepper= QPushButton("Configurar roles y módulos…")
        btn_configurar_side_stepper.setIcon(icono_emoji("⚙"))
        btn_configurar_side_stepper.setIconSize(_QSize_emoji(16, 16))
        btn_configurar_side_stepper.setObjectName("BtnAccionNeutro")
        btn_configurar_side_stepper.clicked.connect(self._abrir_configuracion_side_stepper)
        fila_ss_1.addWidget(btn_configurar_side_stepper)
        fila_ss_1.addStretch()
        t_side_stepper.contenido.addLayout(fila_ss_1)

        fila_ss_2= QHBoxLayout()
        self.btn_exportar_permisos_side_stepper= QPushButton("Exportar paquete de permisos")
        self.btn_exportar_permisos_side_stepper.setIcon(icono_emoji("📄"))
        self.btn_exportar_permisos_side_stepper.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar_permisos_side_stepper.clicked.connect(self._exportar_paquete_permisos_side_stepper)
        fila_ss_2.addWidget(self.btn_exportar_permisos_side_stepper)
        self.btn_exportar_instalador_side_stepper= QPushButton("Exportar Instalador para Side Stepper")
        self.btn_exportar_instalador_side_stepper.setIcon(icono_emoji("\uE002"))
        self.btn_exportar_instalador_side_stepper.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar_instalador_side_stepper.setObjectName("BtnAccionAgregar")
        self.btn_exportar_instalador_side_stepper.clicked.connect(self._exportar_instalador_side_stepper)
        fila_ss_2.addWidget(self.btn_exportar_instalador_side_stepper)
        fila_ss_2.addStretch()
        t_side_stepper.contenido.addLayout(fila_ss_2)
        disposicion.addWidget(t_side_stepper)
        self._tarjetas_seguridad.append(t_side_stepper)

        #---------------- Sincronización ----------------
        t_sync= TarjetaSeccion(
            "", "Sincronización",
            "Usa la misma carpeta configurada arriba (o en Sincronización, si eres Profesor). "
            "Compara por hash contra la última versión conocida por este equipo para detectar "
            "cambios remotos, cambios locales sin subir, o conflictos.")
        self.lbl_estado_sync= QLabel("")
        self.lbl_estado_sync.setObjectName("DescModulo")
        self.lbl_estado_sync.setWordWrap(True)
        t_sync.contenido.addWidget(self.lbl_estado_sync)
        fila_sync= QHBoxLayout()
        btn_subir_sync= QPushButton("Subir Cambios")
        btn_subir_sync.setIcon(icono_emoji("\uE002"))
        btn_subir_sync.setIconSize(_QSize_emoji(16, 16))
        btn_subir_sync.setObjectName("BtnAccionAgregar")
        btn_subir_sync.clicked.connect(self._subir_cambios_sync)
        fila_sync.addWidget(btn_subir_sync)
        btn_descargar_sync= QPushButton("Descargar Novedades")
        btn_descargar_sync.setIcon(icono_emoji("\uE001"))
        btn_descargar_sync.setIconSize(_QSize_emoji(16, 16))
        btn_descargar_sync.setObjectName("BtnAccionAjustar")
        btn_descargar_sync.clicked.connect(self._descargar_novedades_sync)
        fila_sync.addWidget(btn_descargar_sync)
        btn_verificar_sync= QPushButton("Verificar Ahora")
        btn_verificar_sync.setIcon(icono_emoji("🔄"))
        btn_verificar_sync.setIconSize(_QSize_emoji(16, 16))
        btn_verificar_sync.setObjectName("BtnAccionNeutro")
        btn_verificar_sync.clicked.connect(self._refrescar_estado_sync)
        fila_sync.addWidget(btn_verificar_sync)
        fila_sync.addStretch()
        t_sync.contenido.addLayout(fila_sync)
        disposicion.addWidget(t_sync)
        self._tarjetas_seguridad.append(t_sync)

        disposicion.addStretch()
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        return scroll

    def _refrescar_estado_bd_base(self):

        from src.nucleo.bd import info_bd_base
        info= info_bd_base()
        if info:
            self.lbl_estado_bd_base.setText(
                f"✅ BD Base guardada el {formatear_fecha_hora(info['modificado'], self.main_window)} "
                f"({info['tamano_kb']} KB).")
        else:
            self.lbl_estado_bd_base.setText(
                "Todavía no se ha guardado ninguna BD Base. Los perfiles.acdx y paquetes de"
                "instalación usarán la base de datos actual (con tus datos personales) hasta que "
                "guardes una.")

    def _guardar_bd_base(self):

        from src.nucleo.bd import guardar_bd_base_desde_actual
        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden gestionar la BD Base.", self)
            return
        if mostrar_mensaje(
                "pregunta", "Guardar BD Base",
                "Esto copiará la base de datos ACTUAL (tal como está ahora mismo) como la nueva 'BD "
                "Base Institucional', reemplazando la anterior si existía.\n\nAsegúrate de que no "
                "contenga datos personales tuyos que no quieras distribuir a Docentes/Personal (por "
                "ejemplo, revisa/depura registros de prueba antes de continuar).\n\n¿Deseas continuar?",
                self) != QMessageBox.StandardButton.Yes:
            return
        try:

            ruta= guardar_bd_base_desde_actual()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar la BD Base:\n{error}", self)
            return
        registrar_auditoria("Seguridad", "Guardó/actualizó la BD Base Institucional",
                            self.main_window.usuario_actual)
        self._refrescar_estado_bd_base()
        _preguntar_abrir_carpeta(self, ruta, "BD Base guardada",
                                 f"La BD Base Institucional se guardó correctamente en:\n{ruta}")

    def _quitar_bd_base(self):

        from src.nucleo.bd import eliminar_bd_base, existe_bd_base
        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden gestionar la BD Base.", self)
            return
        if not existe_bd_base():
            mostrar_mensaje("info", "Sin BD Base", "No hay ninguna BD Base guardada actualmente.", self)
            return
        if mostrar_mensaje("pregunta", "Quitar BD Base",
                           "¿Eliminar la BD Base Institucional guardada? Los perfiles .acdx y paquetes "
                           "de instalación futuros usarán la base de datos actual hasta que guardes "
                           "una nueva.", self) != QMessageBox.StandardButton.Yes:
            return
        eliminar_bd_base()
        registrar_auditoria("Seguridad", "Eliminó la BD Base Institucional", self.main_window.usuario_actual)
        self._refrescar_estado_bd_base()
        mostrar_mensaje("exito", "BD Base eliminada", "La BD Base Institucional se eliminó.", self)

    #Igual que 'Generar Perfil (.acdx)' de la pestaña Usuarios y Roles, pero
    #sin necesitar una fila ya seleccionada: el propio diálogo deja elegir
    #el usuario primero.
    def _generar_perfil_usuario_libre(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden generar perfiles institucionales.", self)
            return
        from src.interfaz.perfil import DialogoGenerarPerfil
        dialogo= DialogoGenerarPerfil(self.main_window)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            registrar_auditoria("Seguridad", "Generó perfil institucional (.acdx)",
                                self.main_window.usuario_actual, dialogo.username or "")

    #Copia el instalador (.exe) ya compilado para Docentes/Personal a la carpeta elegida.
    #Primero intenta la función del módulo 'instalador' (por compatibilidad); si esa no lo
    #encuentra, hace una búsqueda propia más amplia (ver _localizar_instalador_docentes)
    #antes de rendirse.
    def _exportar_instalador_docentes(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden exportar el instalador.", self)
            return

        ruta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino para el instalador")
        if not ruta:
            return

        try:

            try:

                from src.servicios.instalador import exportar_instalador_docentes
                destino= exportar_instalador_docentes(ruta)
            except FileNotFoundError:
                origen= self._localizar_instalador_docentes()
                destino= os.path.join(ruta, os.path.basename(origen))
                shutil.copy2(origen, destino)
        except FileNotFoundError as error:
            mostrar_mensaje("advertencia", "Instalador no encontrado", str(error), self)
            return
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo exportar el instalador:\n{error}", self)
            return
        registrar_auditoria("Seguridad", "Exportó instalador para Docentes/Personal",
                            self.main_window.usuario_actual, destino)
        mostrar_mensaje("exito", "Instalador exportado",
                        f"El instalador se copió en:\n{destino}\n\nEs el mismo archivo para todos: "
                        "entrégaselo junto con el .acdx de cada persona (Usuarios y Roles Generar "
                        "Perfil).", self)

    def _abrir_configuracion_side_stepper(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden configurar Side Stepper.", self)
            return
        from src.interfaz.side_stepper_config import DialogoExportarSideStepper
        DialogoExportarSideStepper(self.main_window, parent=self).exec()

    def _exportar_paquete_permisos_side_stepper(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden exportar Side Stepper.", self)
            return
        ruta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino para el paquete de permisos")
        if not ruta:
            return
        try:

            from src.servicios.instalador import exportar_paquete_permisos_side_stepper
            destino= exportar_paquete_permisos_side_stepper(ruta)
        except ValueError as error:
            mostrar_mensaje("advertencia", "Nada que exportar", str(error), self)
            return
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo exportar el paquete de permisos:\n{error}", self)
            return
        registrar_auditoria("Seguridad", "Exportó paquete de permisos para Side Stepper",
                            self.main_window.usuario_actual, destino)
        mostrar_mensaje("exito", "Paquete de permisos exportado",
                        f"Se guardó en:\n{destino}\n\nEntrégalo junto con el instalador; la persona lo "
                        "importa en el primer arranque para quedar con el rol y los módulos que configuraste.",
                        self)

    def _exportar_instalador_side_stepper(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo Administradores/Directores pueden exportar el instalador.", self)
            return
        ruta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino para el instalador")
        if not ruta:
            return
        try:

            from src.servicios.instalador import exportar_instalador_side_stepper
            destino= exportar_instalador_side_stepper(ruta)
        except FileNotFoundError as error:
            mostrar_mensaje("advertencia", "Instalador no encontrado", str(error), self)
            return
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo exportar el instalador:\n{error}", self)
            return
        registrar_auditoria("Seguridad", "Exportó instalador para Side Stepper",
                            self.main_window.usuario_actual, destino)
        mostrar_mensaje("exito", "Instalador exportado",
                        f"El instalador se copió en:\n{destino}\n\nEs el mismo archivo siempre: entrégaselo "
                        "junto con el paquete de permisos (Exportar paquete de permisos).", self)

    #Busca 'AcaDeXI_Docentes_Setup.exe' en todas las carpetas donde razonablemente puede
    #haber quedado tras compilarlo con Inno Setup: junto al ejecutable de AcaDeXI, dentro de
    #su carpeta '_internal' (así queda al empaquetar con PyInstaller en modo carpeta, ej.
    #AcaDeXI\AcaDeXI.exe + AcaDeXI\_internal\...), y junto a main.py cuando se ejecuta en
    #modo desarrollo (sin empaquetar). Devuelve la ruta completa si lo encuentra, o lanza
    #FileNotFoundError con el detalle de dónde se buscó.
    def _localizar_instalador_docentes(self):

        nombre= "AcaDeXI_Docentes_Setup.exe"
        carpetas= []

        if getattr(sys, "frozen", False):
            carpeta_exe= os.path.dirname(sys.executable)
            carpetas.append(carpeta_exe)
            carpetas.append(os.path.join(carpeta_exe, "_internal"))

        if sys.argv and sys.argv[0]:
            carpeta_script= os.path.dirname(os.path.abspath(sys.argv[0]))
            carpetas.append(carpeta_script)
            carpetas.append(os.path.join(carpeta_script, "_internal"))

        carpeta_modulo= obtener_carpeta_raiz()
        carpetas.append(carpeta_modulo)
        carpetas.append(os.path.join(carpeta_modulo, "_internal"))

        #Quitamos duplicados (p. ej. cuando exe y script coinciden) manteniendo el orden.
        vistas= set()
        carpetas_unicas= []
        for c in carpetas:
            clave= os.path.normcase(os.path.normpath(c))
            if clave not in vistas:
                vistas.add(clave)
                carpetas_unicas.append(c)

        for carpeta in carpetas_unicas:
            candidato= os.path.join(carpeta, nombre)
            if os.path.isfile(candidato):
                return candidato

        lista= "\n".join(f"• {c}" for c in carpetas_unicas)
        raise FileNotFoundError(
            f"No se encontró '{nombre}' en ninguna de estas carpetas:\n{lista}\n\n"
            "Debes compilarlo una sola vez con Inno Setup a partir de AcaDeXI_Docentes.iss y "
            f"colocar el .exe resultante con ese nombre exacto ('{nombre}') junto al ejecutable "
            "de AcaDeXI, o dentro de su carpeta '_internal'."
        )

    def _guardar_smtp(self):

        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""UPDATE configuracion SET smtp_host=?, smtp_puerto=?, smtp_usuario=?,
                         smtp_password= ?, smtp_remitente=?, smtp_seguridad=? WHERE id=1""",
                      (self.in_smtp_host.text().strip(), self.spin_smtp_puerto.value(),
                       self.in_smtp_usuario.text().strip(), self.in_smtp_password.text(),
                       self.in_smtp_remitente.text().strip(), self.combo_smtp_seguridad.currentText()))
            conn.commit()
            conn.close()
            registrar_auditoria("Configuración", "Actualizó configuración SMTP", self.main_window.usuario_actual)
            mostrar_mensaje("exito", "Guardado", "La configuración de correo (SMTP) se guardó correctamente.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar la configuración SMTP:\n{error}", self)

    def _probar_smtp(self):

        destino= self.in_smtp_usuario.text().strip()
        if not destino:
            mostrar_mensaje("advertencia", "Sin destinatario", "Ingresa un usuario SMTP para enviarte la prueba.", self)
            return
        try:

            from src.nucleo.bd import enviar_correo
            enviar_correo(destino, "AcaDeXI - Correo de prueba",
                          "Este es un correo de prueba de la configuración SMTP de AcaDeXI.\n"
                          "Si lo recibiste, la configuración es correcta.")
            mostrar_mensaje("exito", "Enviado", f"Se envió un correo de prueba a {destino}.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error al enviar", str(error), self)

    def _guardar_seguridad(self):

        self.main_window.requerir_login= self.chk_requerir_login.isChecked()
        self.main_window.guardar_configuracion()
        mostrar_mensaje("exito", "Guardado", "Preferencias de seguridad actualizadas.", self)

    def _elegir_carpeta_backup(self):

        carpeta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta destino de backups")
        if carpeta:
            self.in_backup_carpeta.setText(carpeta)

    def _guardar_config_backup(self):

        from src.nucleo.bd import guardar_config_backup, guardar_mostrar_backups_gerenciales
        carpeta= self.in_backup_carpeta.text().strip()
        guardar_config_backup(self.combo_backup_modo.currentText(), carpeta)
        guardar_mostrar_backups_gerenciales(self.chk_backups_gerenciales.isChecked())
        self.main_window.carpeta_sincronizacion= carpeta
        self.main_window.guardar_configuracion()
        registrar_auditoria("Seguridad", "Actualizó preferencias de backup automático",
                            self.main_window.usuario_actual, self.combo_backup_modo.currentText())
        mostrar_mensaje("exito", "Guardado", "Preferencias de backup automático actualizadas.", self)
        self._refrescar_estado_sync()
        if hasattr(self.main_window, "_aplicar_permisos_por_rol"):
            self.main_window._aplicar_permisos_por_rol()

    def _cargar_config_backup(self):

        from src.nucleo.bd import obtener_config_backup, mostrar_backups_gerenciales
        cfg= obtener_config_backup()
        self.combo_backup_modo.setCurrentText(cfg["modo"])
        self.in_backup_carpeta.setText(cfg["carpeta"])
        self.chk_backups_gerenciales.setChecked(mostrar_backups_gerenciales())
        self.lbl_ultimo_backup.setText(
            f"Último backup: {formatear_fecha_hora(cfg['ultima_fecha'], self.main_window)}"
            if cfg["ultima_fecha"] else "Aún no se ha creado ningún backup.")
        self._cargar_historial_backups()
        self._refrescar_estado_sync()

    def _cargar_historial_backups(self):

        filas= obtener_historial_backups(100)
        with tabla_pausada(self.tabla_backups):
            self.tabla_backups.setRowCount(len(filas))
            for i, f in enumerate(filas):
                self.tabla_backups.setItem(i, 0, QTableWidgetItem(
                    formatear_fecha_hora(f["fecha"], self.main_window) if f["fecha"] else ""))
                self.tabla_backups.setItem(i, 1, QTableWidgetItem(f["tipo"] or ""))
                self.tabla_backups.setItem(i, 2, QTableWidgetItem(f["destino"] or ""))
                self.tabla_backups.setItem(i, 3, QTableWidgetItem(f"{f['tamano_kb']:.1f} KB" if f["tamano_kb"] else ""))
                self.tabla_backups.setItem(i, 4, QTableWidgetItem("Exitoso" if f["exitoso"] else "Fallido"))

    def _cargar_combo_profesor_export_docente(self):

        combo= self.combo_profesor_export_docente
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Paquete institucional completo (todos)", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre, apellidos")
        for fila in c.fetchall():
            etiqueta= f"👤 Solo: {fila['nombre']} {fila['apellidos'] or ''}".strip()
            combo.addItem(etiqueta, fila["id"])
        conn.close()
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _exportar_paquete_docente_click(self):

        profesor_id= self.combo_profesor_export_docente.currentData()
        profesor_nombre= None
        if profesor_id is not None:
            profesor_nombre= self.combo_profesor_export_docente.currentText().replace("Solo: ", "").strip()
        exportar_paquete_docente(self.main_window, self, profesor_id=profesor_id, profesor_nombre=profesor_nombre)

    def _crear_backup(self):

        try:

            ruta= crear_backup(self.in_backup_carpeta.text().strip() or None,
                                tipo= "Manual", usuario=self.main_window.usuario_actual)
            registrar_auditoria("Seguridad", "Creó backup", self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Backup creado", f"Copia de seguridad guardada en:\n{ruta}", self)
            self._cargar_config_backup()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo crear el backup:\n{error}", self)

    def _restaurar_backup(self):

        ruta, _= QFileDialog.getOpenFileName(self, "Seleccionar Backup", os.path.join(obtener_carpeta_datos(), "backups"),
                                               "Base de Datos (*.db)")
        if not ruta:
            return
        if mostrar_mensaje("pregunta", "Confirmar Restauración",
                           "Esto reemplazará TODOS los datos actuales. ¿Continuar?", self) != QMessageBox.StandardButton.Yes:
            return
        try:

            restaurar_backup(ruta)
            registrar_auditoria("Seguridad", "Restauró backup", self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Restaurado", "La base de datos fue restaurada. Reinicia la aplicación.", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo restaurar el backup:\n{error}", self)

    #---------------- SINCRONIZACIÓN ----------------
    def _refrescar_estado_sync(self):

        estado= obtener_estado(self.main_window)
        textos= {
            "sin_carpeta": "No hay carpeta de sincronización configurada (usa la Carpeta Personalizada de arriba).",
            "sin_copia_remota": "Carpeta configurada, pero aún no hay copia allí. Usa 'Subir Cambios'.",
            "sincronizado": "Sincronizado: este equipo y la carpeta compartida tienen la misma versión.",
            "hay_novedades": "Hay novedades en la carpeta compartida. Usa 'Descargar Novedades'.",
            "cambios_locales": "Tienes cambios locales sin subir. Usa 'Subir Cambios'.",
            "conflicto": "Conflicto: este equipo y la carpeta compartida cambiaron por separado.",
        }
        self.lbl_estado_sync.setText(textos.get(estado["estado"], ""))

    def _subir_cambios_sync(self):

        try:

            estado= obtener_estado(self.main_window)
            if estado["estado"] == "conflicto":
                if mostrar_mensaje("pregunta", "Conflicto de sincronización",
                        "Este equipo Y la carpeta compartida tienen cambios distintos. Subir AHORA "
                        "sobrescribirá la copia compartida. ¿Confirmas?", self) != QMessageBox.StandardButton.Yes:
                    return
            destino= subir_cambios(self.main_window)
            registrar_auditoria("Sistema", "Subió cambios a carpeta sincronizada", self.main_window.usuario_actual, destino)
            mostrar_mensaje("exito", "Subido", f"Cambios subidos a:\n{destino}", self)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo subir:\n{error}", self)
        self._refrescar_estado_sync()

    def _descargar_novedades_sync(self):

        try:

            estado= obtener_estado(self.main_window)
            if estado["estado"] == "conflicto":
                if mostrar_mensaje("pregunta", "Conflicto de sincronización",
                        "Este equipo Y la carpeta compartida tienen cambios distintos. Descargar AHORA "
                        "sobrescribirá los datos de este equipo (se hará backup automático antes). "
                        "¿Confirmas?", self) != QMessageBox.StandardButton.Yes:
                    return
            respaldo= descargar_novedades(self.main_window)
            registrar_auditoria("Sistema", "Descargó novedades de carpeta sincronizada", self.main_window.usuario_actual, respaldo)
            mostrar_mensaje("exito", "Actualizado", f"Novedades descargadas. Respaldo previo en:\n{respaldo}\n\n"
                           "Reinicia la aplicación.", self)
            self._cargar_config_backup()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo descargar:\n{error}", self)
        self._refrescar_estado_sync()

    #---------------- AUDITORÍA (sin cambios) ----------------
    def _tab_auditoria(self):

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(4, 10, 10, 10)
        disposicion.setSpacing(16)
        self._tarjetas_auditoria= []

        lbl_desc_intro= QLabel("Captura detallada de las acciones del sistema: creación, "
                             "modificación y eliminación de registros, inicios y cierres de sesión.")
        lbl_desc_intro.setObjectName("DescModulo")
        lbl_desc_intro.setWordWrap(True)
        disposicion.addWidget(lbl_desc_intro)

        t_interruptor= TarjetaSeccion(
            "", "Preferencia de Auditoría",
            "Mientras esté desactivado, las acciones del sistema NO se guardarán en la bitácora "
            "(el propio cambio de esta preferencia sí queda registrado, para dejar constancia de "
            "quién la activó o desactivó).")
        self.chk_auditoria_activa= QCheckBox("Activar Registro de Auditoría (recomendado)")
        t_interruptor.contenido.addWidget(self.chk_auditoria_activa)
        self.lbl_auditoria_desactivada= QLabel(
            "El registro de auditoría está desactivado. Los eventos del sistema no se están guardando.")
        self.lbl_auditoria_desactivada.setObjectName("DescModulo")
        self.lbl_auditoria_desactivada.setWordWrap(True)
        self.lbl_auditoria_desactivada.setVisible(False)
        t_interruptor.contenido.addWidget(self.lbl_auditoria_desactivada)
        btn_guardar_auditoria= QPushButton("Guardar Preferencia de Auditoría")
        btn_guardar_auditoria.setIcon(icono_emoji("💾"))
        btn_guardar_auditoria.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_auditoria.setObjectName("BtnAccionEditar")
        btn_guardar_auditoria.clicked.connect(self._guardar_auditoria_activa)
        t_interruptor.contenido.addWidget(btn_guardar_auditoria)
        disposicion.addWidget(t_interruptor)
        self._tarjetas_auditoria.append(t_interruptor)

        t_bitacora= TarjetaSeccion(EMOJI_AUDITORIA, "Bitácora de Actividad")
        fila_filtros= QGridLayout()
        fila_filtros.setHorizontalSpacing(12)
        fila_filtros.setVerticalSpacing(8)
        self.date_auditoria_desde= QDateEdit(calendarPopup=True)
        self.date_auditoria_desde.setDate(self._qdate_hace_dias(30))
        self.date_auditoria_hasta= QDateEdit(calendarPopup=True)
        self.date_auditoria_hasta.setDate(self._qdate_hoy())
        self.combo_auditoria_modulo= QComboBox()
        self.combo_auditoria_modulo.addItem("Todos los módulos", None)
        conectar_tooltip_seleccion(self.combo_auditoria_modulo, "Filtra la bitácora por módulo del sistema")
        self.combo_auditoria_usuario= QComboBox()
        self.combo_auditoria_usuario.addItem("Todos los usuarios", None)
        conectar_tooltip_seleccion(self.combo_auditoria_usuario, "Filtra la bitácora por usuario que realizó la acción")
        fila_filtros.addWidget(QLabel("Desde:"), 0, 0)
        fila_filtros.addWidget(self.date_auditoria_desde, 0, 1)
        fila_filtros.addWidget(QLabel("Hasta:"), 0, 2)
        fila_filtros.addWidget(self.date_auditoria_hasta, 0, 3)
        fila_filtros.addWidget(QLabel("Módulo:"), 1, 0)
        fila_filtros.addWidget(self.combo_auditoria_modulo, 1, 1)
        fila_filtros.addWidget(QLabel("Usuario:"), 1, 2)
        fila_filtros.addWidget(self.combo_auditoria_usuario, 1, 3)
        t_bitacora.contenido.addLayout(fila_filtros)
        fila_botones_filtro= QHBoxLayout()
        btn_filtrar= QPushButton("Filtrar")
        btn_filtrar.setIcon(icono_emoji("🔍"))
        btn_filtrar.setIconSize(_QSize_emoji(16, 16))
        btn_filtrar.setObjectName("BtnAccionEditar")
        btn_filtrar.clicked.connect(self._cargar_auditoria)
        btn_limpiar_filtro= QPushButton("Limpiar Filtros")
        btn_limpiar_filtro.setIcon(icono_emoji("🧹"))
        btn_limpiar_filtro.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_filtro.setObjectName("BtnAccionNeutro")
        btn_limpiar_filtro.clicked.connect(self._limpiar_filtros_auditoria)
        fila_botones_filtro.addWidget(btn_filtrar)
        fila_botones_filtro.addWidget(btn_limpiar_filtro)
        fila_botones_filtro.addStretch()
        t_bitacora.contenido.addLayout(fila_botones_filtro)

        self.tabla_auditoria= QTableWidget(0, 5)
        aplicar_estructura_tabla(self.tabla_auditoria)
        self.tabla_auditoria.setObjectName("TablaAuditoria")
        self.tabla_auditoria.setHorizontalHeaderLabels(["Fecha", "Módulo", "Acción", "Usuario", "Detalle"])
        header= self.tabla_auditoria.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tabla_auditoria.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_auditoria.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_auditoria.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_auditoria.setAlternatingRowColors(True)
        self.tabla_auditoria.setWordWrap(True)
        self.tabla_auditoria.setMinimumHeight(380)
        self.tabla_auditoria.verticalHeader().setVisible(False)
        t_bitacora.contenido.addWidget(self.tabla_auditoria, 1)

        self.paginacion_auditoria= ControlPaginacion()
        self.paginacion_auditoria.cambio.connect(self._cargar_auditoria)
        t_bitacora.contenido.addWidget(self.paginacion_auditoria)

        agregar_boton_pantalla_completa(
            fila_botones_filtro, [self.tabla_auditoria, self.paginacion_auditoria],
            titulo= "Bitácora de Actividad", parent=self)

        self.lbl_conteo_auditoria= QLabel("")
        self.lbl_conteo_auditoria.setObjectName("DescModulo")
        t_bitacora.contenido.addWidget(self.lbl_conteo_auditoria)

        fila_botones_auditoria= QHBoxLayout()
        btn_detalle_auditoria= agregar_boton_detalle(
            fila_botones_auditoria, self.tabla_auditoria, self, titulo="Detalle del Registro de Auditoría")
        self.tabla_auditoria.doubleClicked.connect(lambda *_: btn_detalle_auditoria.click())
        fila_botones_auditoria.addStretch()
        t_bitacora.contenido.addLayout(fila_botones_auditoria)

        disposicion.addWidget(t_bitacora)
        self._tarjetas_auditoria.append(t_bitacora)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        return scroll

    def _guardar_auditoria_activa(self):

        if not es_admin(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                            "Solo un Administrador o Director puede activar o desactivar el "
                            "registro de auditoría.", self)
            return
        activar= self.chk_auditoria_activa.isChecked()
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("UPDATE configuracion SET auditoria_activa=? WHERE id=1", (1 if activar else 0,))
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar la preferencia de auditoría:\n{error}", self)
            return
        accion= "Activó el registro de auditoría" if activar else "Desactivó el registro de auditoría"
        registrar_auditoria("Configuración", accion, self.main_window.usuario_actual)
        self.lbl_auditoria_desactivada.setVisible(not activar)
        mostrar_mensaje("exito", "Guardado",
                        "El registro de auditoría fue " + ("activado." if activar else "desactivado."), self)
        self._cargar_auditoria()

    def _qdate_hoy(self):

        from PySide6.QtCore import QDate
        return QDate.currentDate()

    def _qdate_hace_dias(self, dias):

        from PySide6.QtCore import QDate
        return QDate.currentDate().addDays(-dias)

    def _limpiar_filtros_auditoria(self):

        self.date_auditoria_desde.setDate(self._qdate_hace_dias(30))
        self.date_auditoria_hasta.setDate(self._qdate_hoy())
        self.combo_auditoria_modulo.setCurrentIndex(0)
        self.combo_auditoria_usuario.setCurrentIndex(0)
        self._cargar_auditoria()

    def _cargar_combos_auditoria(self):

        modulo_sel= self.combo_auditoria_modulo.currentData()
        usuario_sel= self.combo_auditoria_usuario.currentData()
        self.combo_auditoria_modulo.blockSignals(True)
        self.combo_auditoria_usuario.blockSignals(True)
        self.combo_auditoria_modulo.clear()
        self.combo_auditoria_modulo.addItem("Todos los módulos", None)
        self.combo_auditoria_usuario.clear()
        self.combo_auditoria_usuario.addItem("Todos los usuarios", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT DISTINCT modulo FROM auditoria ORDER BY modulo")
        for fila in c.fetchall():
            if fila["modulo"]:
                self.combo_auditoria_modulo.addItem(fila["modulo"], fila["modulo"])
        c.execute("SELECT DISTINCT usuario FROM auditoria ORDER BY usuario")
        for fila in c.fetchall():
            if fila["usuario"]:
                self.combo_auditoria_usuario.addItem(fila["usuario"], fila["usuario"])
        conn.close()
        if modulo_sel:
            idx= self.combo_auditoria_modulo.findData(modulo_sel)
            if idx >= 0:
                self.combo_auditoria_modulo.setCurrentIndex(idx)
        if usuario_sel:
            idx= self.combo_auditoria_usuario.findData(usuario_sel)
            if idx >= 0:
                self.combo_auditoria_usuario.setCurrentIndex(idx)
        self.combo_auditoria_modulo.blockSignals(False)
        self.combo_auditoria_usuario.blockSignals(False)

    def _cargar_auditoria(self):

        self._cargar_combos_auditoria()
        desde= self.date_auditoria_desde.date().toString("yyyy-MM-dd") + " 00:00:00"
        hasta= self.date_auditoria_hasta.date().toString("yyyy-MM-dd") + " 23:59:59"
        modulo= self.combo_auditoria_modulo.currentData()
        usuario= self.combo_auditoria_usuario.currentData()

        consulta_count= "SELECT COUNT(*) as total FROM auditoria WHERE fecha BETWEEN ? AND ?"
        parametros_count= [desde, hasta]
        if modulo:
            consulta_count += " AND modulo=?"
            parametros_count.append(modulo)
        if usuario:
            consulta_count += " AND usuario=?"
            parametros_count.append(usuario)

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(consulta_count, parametros_count)
        total_registros= c.fetchone()["total"]

        self.paginacion_auditoria.establecer_total(total_registros)
        inicio, fin= self.paginacion_auditoria.rango_actual()

        consulta= "SELECT * FROM auditoria WHERE fecha BETWEEN ? AND ?"
        parametros= [desde, hasta]
        if modulo:
            consulta += " AND modulo=?"
            parametros.append(modulo)
        if usuario:
            consulta += " AND usuario=?"
            parametros.append(usuario)
        consulta += " ORDER BY id DESC LIMIT ? OFFSET ?"
        parametros.extend([fin - inicio, inicio])

        c.execute(consulta, parametros)
        filas= c.fetchall()
        conn.close()

        with tabla_pausada(self.tabla_auditoria):
            self.tabla_auditoria.setRowCount(len(filas))
            for i, f in enumerate(filas):
                modulo= f["modulo"] or "Sistema"
                item_modulo= QTableWidgetItem(f"●  {modulo}")
                from src.interfaz.dashboard import _color_para_modulo  #import diferido para evitar circularidad
                item_modulo.setForeground(QColor(_color_para_modulo(modulo)))
                fuente_modulo= item_modulo.font()
                fuente_modulo.setBold(True)
                item_modulo.setFont(fuente_modulo)

                self.tabla_auditoria.setItem(i, 0, QTableWidgetItem(
                    formatear_fecha_hora(f["fecha"], self.main_window) if f["fecha"] else ""))
                self.tabla_auditoria.setItem(i, 1, item_modulo)
                self.tabla_auditoria.setItem(i, 2, QTableWidgetItem(f["accion"]))
                self.tabla_auditoria.setItem(i, 3, QTableWidgetItem(f["usuario"]))
                self.tabla_auditoria.setItem(i, 4, QTableWidgetItem(f["detalle"] or ""))

        self.lbl_conteo_auditoria.setText(f"Mostrando {len(filas)} de {total_registros} registro(s) de auditoría.")

    #---------------- CARGA GENERAL ----------------
    def refrescar(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM configuracion WHERE id=1")
        cfg= c.fetchone()
        conn.close()
        if cfg:
            self.in_nombre.setText(cfg["nombre_institucion"] or "")
            self.in_direccion.setText(cfg["direccion"] or "")
            self.in_telefono.setText(cfg["telefono"] or "")
            self.in_correo.setText(cfg["correo"] or "")
            self.in_sitio_web.setText(cfg["sitio_web"] or "")
            self._cargar_logo(cfg["logo_path"])
            self._cargar_firma(cfg["firma_path"])
            self.in_pie_pagina.setText(cfg["pie_pagina"] or "")
            self.combo_tipo.setCurrentText(cfg["tipo_institucion"] or "Escuela")
            modulos_personalizados= (cfg["modulos_personalizados"] or "").split(",")
            self.chk_mod_politecnico.setChecked("Politécnico" in modulos_personalizados)
            self.chk_mod_universidad.setChecked("Universidad" in modulos_personalizados)
            self._actualizar_visibilidad_modulos_personalizados(cfg["tipo_institucion"] or "Escuela")
            niveles_guardados= (_valor_o_defecto(cfg, "niveles_educativos_habilitados", "") or "").split(",")
            if not any(niveles_guardados) and (cfg["tipo_institucion"] or "Escuela") == "Escuela":
                #Instalación existente que nunca configuró niveles: mismo valor por defecto que usa
                #niveles_academicos_habilitados() para no mostrarle a la institución una pantalla vacía que sugiera que perdió
                #Primaria/Secundaria de golpe.
                niveles_guardados= ["Primaria", "Secundaria"]
            for nivel, chk in self.chk_nivel.items():
                chk.setChecked(nivel in niveles_guardados)
            self._actualizar_visibilidad_niveles_educativos(cfg["tipo_institucion"] or "Escuela")
            self.spin_escala.setValue(cfg["escala_maxima"] or 100)
            self.spin_nota_min.setValue(cfg["nota_minima"] or 70)
            self.spin_nota_min_primaria.setValue(_valor_o_defecto(cfg, "nota_minima_primaria", cfg["nota_minima"] or 70))
            self.spin_nota_min_secundaria.setValue(_valor_o_defecto(cfg, "nota_minima_secundaria", cfg["nota_minima"] or 70))
            self.combo_metodo.setCurrentText(cfg["metodo_calculo"] or "Promedio Ponderado")
            try:

                self.combo_sistema_calificacion.setCurrentText(
                    cfg["sistema_calificacion"] or "Numérico (Personalizado)")
            except (IndexError, KeyError):
                self.combo_sistema_calificacion.setCurrentText("Numérico (Personalizado)")
            self.in_anio.setText(cfg["anio_academico"] or "")
            self.combo_division.setCurrentText(cfg["division_periodo"] or "Trimestres")
            #Boletín Oficial RD: si boletin_minerd.py no está instalado
            #todavía (o la migración no corrió), _valor_o_defecto simplemente
            #devuelve el valor por defecto sin reventar la carga del resto.
            if hasattr(self, "combo_formato_boletin"):
                idx_formato= self.combo_formato_boletin.findData(
                    _valor_o_defecto(cfg, "formato_boletin_general", "simple"))
                self.combo_formato_boletin.setCurrentIndex(idx_formato if idx_formato >= 0 else 0)
                self._colores_boletin_elegidos= {
                    "Secundaria": _valor_o_defecto(cfg, "boletin_color_banda_secundaria", "#1F9E9E"),
                    "Primaria": _valor_o_defecto(cfg, "boletin_color_banda_primaria", "#E8863C"),
                }
                self._refrescar_botones_color_boletin()
            criterio_lista_guardado= _valor_o_defecto(cfg, "criterio_numero_lista", CRITERIO_APELLIDOS_NOMBRE)
            idx_criterio= self.combo_criterio_lista.findText(criterio_lista_guardado)
            self.combo_criterio_lista.setCurrentIndex(idx_criterio if idx_criterio >= 0 else 0)
            self._actualizar_info_criterio_lista(self.combo_criterio_lista.currentText())
            self.combo_idioma.setCurrentText(cfg["idioma"] or "Español")
            self.combo_tema.setCurrentText(self.main_window.tema_actual)
            self.chk_oscuro.setChecked(self.main_window.modo_oscuro)
            self.chk_login_translucido.setChecked(getattr(self.main_window, "login_translucido", True))
            self.combo_tecla_atajos.setCurrentText(
                getattr(self.main_window, "tecla_atajos", TECLA_ATAJO_POR_DEFECTO))
            idx_hora= self.combo_formato_hora.findData(getattr(self.main_window, "formato_hora", "24h"))
            self.combo_formato_hora.setCurrentIndex(idx_hora if idx_hora >= 0 else 0)
            idx_fecha= self.combo_formato_fecha.findData(getattr(self.main_window, "formato_fecha", "dmy"))
            self.combo_formato_fecha.setCurrentIndex(idx_fecha if idx_fecha >= 0 else 0)
            self.chk_etiquetas_recuadro.setChecked(
                getattr(self.main_window, "etiquetas_con_recuadro", False))
            self.chk_requerir_login.setChecked(getattr(self.main_window, "requerir_login", True))
            self.chk_minimizar_bandeja.setChecked(getattr(self.main_window, "minimizar_a_bandeja", True))
            if getattr(self, "chk_calif_tecnicas", None) is not None:
                self.chk_calif_tecnicas.setChecked(getattr(self.main_window, "mostrar_calif_tecnicas", False))
                self._actualizar_estado_calif_tecnicas()
            self.in_smtp_host.setText(cfg["smtp_host"] or "")
            self.spin_smtp_puerto.setValue(cfg["smtp_puerto"] or 587)
            self.in_smtp_usuario.setText(cfg["smtp_usuario"] or "")
            self.in_smtp_password.setText(cfg["smtp_password"] or "")
            self.in_smtp_remitente.setText(cfg["smtp_remitente"] or "")
            self.combo_smtp_seguridad.setCurrentText(cfg["smtp_seguridad"] or "TLS")
            self._cargar_config_backup()
            auditoria_activa= cfg["auditoria_activa"]
            auditoria_activa= True if auditoria_activa is None else bool(auditoria_activa)
            self.chk_auditoria_activa.setChecked(auditoria_activa)
            self.lbl_auditoria_desactivada.setVisible(not auditoria_activa)
            self._cargando_psicologia_admin= True
            self.chk_psicologia_admin.setChecked(bool(_valor_o_defecto(cfg, "psicologia_habilitada_admin", 0)))
            self._cargando_psicologia_admin= False
        self._cargar_usuarios()
        self._cargar_auditoria()
        self._cargar_combo_profesor_export_docente()
        self._refrescar_estado_bd_base()
        self.aplicar_permisos_por_rol()

    def aplicar_permisos_por_rol(self):

        rol= getattr(self.main_window, "rol_actual", None)
        permitido= es_admin(self.main_window)
        es_restringido= rol in ("Profesor", "Administrativo")

        for i in range(self.tabs.count()):
            texto= self.tabs.tabText(i)
            if es_restringido:
                visible= texto in ("Apariencia", "Mi Cuenta")
                self.tabs.setTabVisible(i, visible)
                self.tabs.setTabEnabled(i, visible)
            else:
                self.tabs.setTabVisible(i, True)
                if texto == "Mi Cuenta":
                    self.tabs.setTabEnabled(i, True)
                elif texto != "Institución":
                    self.tabs.setTabEnabled(i, permitido or texto == "Auditoría")
                else:
                    self.tabs.setTabEnabled(i, True)

        if es_restringido:
            idx_apariencia= next(
                (i for i in range(self.tabs.count()) if self.tabs.tabText(i) == "Apariencia"), None)
            if idx_apariencia is not None:
                self.tabs.setCurrentIndex(idx_apariencia)

        self.chk_auditoria_activa.setEnabled(permitido)
        if hasattr(self, "in_u_pass"):
            self.in_u_pass.setEnabled(permitido)
            self.in_u_pass.setPlaceholderText(
                "Contraseña" if permitido else "Solo un Administrador puede cambiar la contraseña")
        
        #Ocultar botones de exportación si no es admin
        if hasattr(self, "btn_exportar_docente"):
            puede_exportar_docente= permitido or (rol == "Coordinador")
            self.btn_exportar_docente.setVisible(puede_exportar_docente)
            self.combo_profesor_export_docente.setVisible(puede_exportar_docente)
        if hasattr(self, "btn_guardar_bd_base"):
            self.btn_guardar_bd_base.setVisible(permitido)
        if hasattr(self, "btn_quitar_bd_base"):
            self.btn_quitar_bd_base.setVisible(permitido)
        if hasattr(self, "btn_generar_perfil_usuario"):
            self.btn_generar_perfil_usuario.setVisible(permitido)
        if hasattr(self, "btn_exportar_instalador_docentes"):
            self.btn_exportar_instalador_docentes.setVisible(permitido)

        #La tarjeta "Módulo de Psicología" es EXCLUSIVA del rol Administrador -a diferencia del resto de esta pestaña,
        #ni
        #siquiera Director/Coordinador la ven (ver bd.py:
        #psicologia_habilitada_admin y permisos.puede_ver_psicologia)-.
        if hasattr(self, "tarjeta_psicologia_admin"):
            solo_administrador= rol is None or rol == "Administrador"
            self.tarjeta_psicologia_admin.setVisible(solo_administrador)

    #Se llama automáticamente (ver main.py ▸ aplicar_tema) cada vez que el usuario
    #cambia el tema/modo oscuro de la aplicación, para que las tarjetas y estilos
    #propios de este módulo se mantengan sincronizados con el resto del sistema.
    def actualizar_tema(self):

        self._aplicar_tema_visual()

    #Construye y aplica la hoja de estilos moderna del módulo (pestañas, tarjetas,
    #campos, tablas, scrollbars) usando los colores del tema actual de la aplicación.
    #Es puramente visual: no lee ni modifica ningún dato.
    def _aplicar_tema_visual(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        modo_oscuro= getattr(mw, "modo_oscuro", True)

        #Optimización: esta función puede llamarse varias veces sin que el tema realmente haya cambiado (p.ej. al
        #refrescar o cambiar de pestaña). Reconstruir y reaplicar dos hojas de estilo completas es costoso porque Qt
        #tiene que "repolir" (repolish) todo el árbol de widgets del módulo. Si la firma (tema, modo) es la misma que
        #la última vez, no se hace nada.
        firma= (tema_actual, modo_oscuro)
        if getattr(self, "_firma_tema_aplicada", None) == firma:
            return
        self._firma_tema_aplicada= firma

        paleta= paletas.get(tema_actual) or next(iter(paletas.values()))
        idx= 1 if modo_oscuro else 0

        bg_panel= paleta["display_bg"][idx]
        borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        accent= paleta["btn_op_bg"][idx]

        for tarjeta in self.findChildren(TarjetaSeccion):
            tarjeta.aplicar_paleta(bg_panel, borde, txt_prim, txt_sec, accent, modo_oscuro)

        accent_suave= _hex_a_rgba(accent, 0.16 if modo_oscuro else 0.10)
        separador_col= _hex_a_rgba(borde, 0.55 if not modo_oscuro else 0.8)
        accent_hover_cab= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent

        if hasattr(self, "frame_cabecera"):
            self.frame_cabecera.setStyleSheet(f"""
                QFrame#TarjetaCabecera {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {accent}, stop:1 {accent_hover_cab});
                    border-radius: 18px;
                }}
                QLabel#IconoCabeceraModulo {{
                    background-color: rgba(255, 255, 255, 40);
                    border-radius: 23px;
                    font-size: 22px;
                    color: white;
                }}
                QLabel#TituloCabeceraModulo {{
                    font-size: 22px;
                    font-weight: 800;
                    color: white;
                    background: transparent;
                }}
                QLabel#SubtituloCabeceraModulo {{
                    font-size: 12px;
                    color: rgba(255, 255, 255, 210);
                    background: transparent;
                }}
            """)

        if hasattr(self, "icono_busqueda_usuarios"):
            self.icono_busqueda_usuarios.establecer_color(txt_sec)

        #El selector de pestañas se estiliza aparte, aplicando la hoja de estilo directamente a self.tabs en vez de
        #incluirla en la hoja de estilo de todo el módulo (self.setStyleSheet más abajo). Un setStyleSheet en un widget
        #contenedor obliga a Qt a repolir TODOS sus descendientes (cada QLineEdit, QComboBox, tabla, etc. de las 7
        #pestañas, aunque estén ocultas), aunque solo cambien 3 reglas de QTabBar. Aplicarla solo a self.tabs limita
        #ese costo al widget de pestañas, mismo diseño "píldora" con degradado que en asistencia.py.
        accent_hover= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                padding: 9px 20px;
                margin-right: 6px;
                border-radius: 9px;
                font-weight: 600;
                font-size: 13px;
                background: {borde};
                color: {txt_sec};
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {accent_hover});
                color: white;
            }}
            QTabBar::tab:!selected:hover {{
                background: {accent_suave};
                color: {txt_prim};
            }}
        """ + estilo_flechas_navegacion_tabs(accent, accent_hover, bg_panel, borde, accent_suave))

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QFrame#TarjetaSeccion QLineEdit, QFrame#TarjetaSeccion QComboBox,
            QFrame#TarjetaSeccion QSpinBox, QFrame#TarjetaSeccion QDoubleSpinBox,
            QFrame#TarjetaSeccion QDateEdit {{
                border: 2px solid {borde};
                border-radius: 9px;
                padding: 7px 10px;
                background-color: {bg_panel};
                color: {txt_prim};
                selection-background-color: {accent};
            }}
            QFrame#TarjetaSeccion QLineEdit:focus, QFrame#TarjetaSeccion QComboBox:focus,
            QFrame#TarjetaSeccion QSpinBox:focus, QFrame#TarjetaSeccion QDoubleSpinBox:focus,
            QFrame#TarjetaSeccion QDateEdit:focus {{
                border: 2px solid {accent};
            }}

            QPushButton {{
                border-radius: 10px;
                padding: 9px 16px;
                font-weight: 600;
            }}

            QTableWidget {{
                border: 1px solid {borde};
                border-radius: 12px;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 6px;
                border-bottom: 1px solid {separador_col};
                border-right: 1px solid {separador_col};
            }}
            QTableWidget::item:hover {{
                background-color: {accent_suave};
            }}
            QTableWidget::item:selected {{
                background-color: {accent};
                color: #ffffff;
            }}
            QHeaderView::section {{
                padding: 8px;
                font-weight: 700;
                border: none;
                border-bottom: 2px solid {borde};
                border-right: 1px solid {separador_col};
            }}
            QTableWidget QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 2px; border: none;
            }}
            QTableWidget QScrollBar::handle:vertical {{
                background: {borde}; border-radius: 5px; min-height: 30px;
            }}
            QTableWidget QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            QTableWidget QScrollBar::add-line:vertical, QTableWidget QScrollBar::sub-line:vertical {{
                height: 0px; border: none; background: transparent;
            }}
            QTableWidget QScrollBar::add-page:vertical, QTableWidget QScrollBar::sub-page:vertical {{
                background: transparent; border: none;
            }}
            QTableWidget QScrollBar:horizontal {{
                background: transparent; height: 10px; margin: 2px; border: none;
            }}
            QTableWidget QScrollBar::handle:horizontal {{
                background: {borde}; border-radius: 5px; min-width: 30px;
            }}
            QTableWidget QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
            QTableWidget QScrollBar::add-line:horizontal, QTableWidget QScrollBar::sub-line:horizontal {{
                width: 0px; border: none; background: transparent;
            }}
            QTableWidget QScrollBar::add-page:horizontal, QTableWidget QScrollBar::sub-page:horizontal {{
                background: transparent; border: none;
            }}

            /* Auditoría: mismo esquema de colores que la tabla de
               "Últimas Acciones del Sistema" del Dashboard (fondo
               transparente, encabezado con bg_panel, sin bordes propios). */
            QTableWidget#TablaAuditoria {{
                background-color: transparent;
                gridline-color: transparent;
                color: {txt_prim};
                border: none;
                border-radius: 0px;
            }}
            QTableWidget#TablaAuditoria QHeaderView::section {{
                background-color: {bg_panel};
                color: {txt_sec};
                border: none;
                border-bottom: 2px solid {borde};
                border-right: 1px solid {separador_col};
                padding: 4px;
            }}
            QTableWidget#TablaAuditoria::item {{
                border-bottom: 1px solid {separador_col};
                border-right: 1px solid {separador_col};
            }}

            QLabel#PreviewLogo {{
                border: 2px dashed {borde};
                border-radius: 12px;
                color: {txt_sec};
                font-size: 11px;
            }}
            QLabel#PreviewLogo:hover {{
                border-color: {accent};
                color: {accent};
            }}

            QCheckBox {{
                spacing: 8px;
            }}
        """)