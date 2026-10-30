#Calendario de AcaDeXI.
import unicodedata
from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
QGridLayout, QDateEdit, QTimeEdit, QTextEdit, QScrollArea, QFrame, QDialog,
QGraphicsOpacityEffect, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QDate, QTime, QPropertyAnimation, QEasingCurve, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QBrush, QPainter, QPen, QPixmap, QIcon
from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.interfaz.filtros_curso_seccion import poblar_combo_curso, cascada_seccion_por_curso, preseleccionar_curso_y_seccion
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.nucleo.permisos import tiene_acceso_gerencial
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         agregar_boton_detalle, tabla_pausada, mostrar_texto_largo,
                         agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import formatear_hora, formatear_fecha, aplicar_formato_widget_hora, aplicar_formato_widget_fecha
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro)

TIPOS_EVENTO= ["Institucional", "Examen", "Entrega", "Reunión", "Personal"]

#Colores e iconos semánticos por tipo de evento. Se mantienen fijos (no dependen del tema/accent activo) para
#que el código de color sea reconocible sin importar qué paleta de la app esté seleccionada.
TIPO_COLORES= {
    "Institucional": "#6366F1",
    "Examen": "#EF4444",
    "Entrega": "#F59E0B",
    "Reunión": "#A855F7",
    "Personal": "#10B981",
}

#El icono de cada tipo busca representar la acción, no solo decorar:
#Institucional = el edificio/la institución; Examen = la hoja que se
#responde; Entrega = una CAJA (algo que el estudiante entrega/envía, como
#un paquete); Reunión = varias personas reunidas (no un simple apretón de
#manos, que es más "acuerdo" que "reunión" en sí); Personal = la persona
#(el propio usuario), sin vínculo institucional.
TIPO_ICONOS= {
    "Institucional": "🏛",
    "Examen": "📝",
    "Entrega": "📦",
    "Reunión": "🧑‍🤝‍🧑",
    "Personal": "👤",
}


DIAS_SEMANA= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_SEMANA_ABBR= ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
MESES= ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


#Utilidades visuales (solo estética/animación — no tocan datos ni lógica)
#Convierte '#RRGGBB' a 'rgba(r, g, b, a)' para usar en hojas de estilo.
def _hex_a_rgba(hex_color, alpha):

    hex_color= (hex_color or "#000000").lstrip("#")
    if len(hex_color) < 6:
        hex_color= "000000"
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Quita mayúsculas y acentos para que el buscador no sea estricto:
#'reunion', 'Reunión' y 'REUNIÓN' encuentran lo mismo (mismo criterio
#que configuracion.py).
def _normalizar(texto):

    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


#Aparece/desaparece `widget` con un fundido de opacidad. Segura ante
#llamadas repetidas y rápidas: nunca deja un efecto huérfano ni un widget
#en un estado de visibilidad incorrecto.
def _fundido(widget, mostrar, duracion=200):

    efecto= widget.graphicsEffect()
    if not isinstance(efecto, QGraphicsOpacityEffect):
        efecto= QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efecto)
    inicio= efecto.opacity()
    if mostrar:
        widget.setVisible(True)
    anim= QPropertyAnimation(efecto, b"opacity", widget)
    anim.setDuration(duracion)
    anim.setStartValue(inicio)
    anim.setEndValue(1.0 if mostrar else 0.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic if mostrar else QEasingCurve.Type.InCubic)

    def _fin(w=widget, e=efecto, ocultar=not mostrar):

        if w.graphicsEffect() is e:
            w.setGraphicsEffect(None)
        if ocultar:
            w.setVisible(False)

    anim.finished.connect(_fin)
    widget._anim_fundido_activo= anim  #evita que Python recolecte el objeto a mitad de camino
    anim.start()


#Pulso de resplandor rojo (sin mover el widget, sin romper el layout) para
#señalar un campo inválido de forma dinámica en vez de un diálogo bloqueante.
def _glow_invalido(widget):

    efecto= QGraphicsDropShadowEffect(widget)
    efecto.setColor(QColor("#EF4444"))
    efecto.setOffset(0, 0)
    efecto.setBlurRadius(0)
    widget.setGraphicsEffect(efecto)
    anim= QPropertyAnimation(efecto, b"blurRadius", widget)
    anim.setDuration(480)
    anim.setKeyValueAt(0.0, 0)
    anim.setKeyValueAt(0.25, 20)
    anim.setKeyValueAt(0.6, 6)
    anim.setKeyValueAt(1.0, 0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _fin(w=widget, e=efecto):

        if w.graphicsEffect() is e:
            w.setGraphicsEffect(None)

    anim.finished.connect(_fin)
    widget._anim_glow_activo= anim
    anim.start()


#Dibuja a mano un icono circular verde con '+' (colapsado) o '−'
#(expandido) -mismo criterio que IconoLupa en horario.py: no depender de
#que el sistema tenga instalado un glifo/emoji concreto (el '+'/'−' de
#algunas fuentes se ve desalineado o directamente no existe)-. Es el
#icono que reemplaza a la flecha de texto (▸/▾) en el encabezado de
#PanelDesplegable, para que 'Añadir/Nueva ...' se lea de un vistazo como
#una acción de agregar en TODOS los módulos que usan este panel.
def _pixmap_circulo_mas_menos(expandido, diametro=18):

    pixmap= QPixmap(diametro, diametro)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter= QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color= QColor("#22C55E")
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    margen= 1.0
    painter.drawEllipse(QRectF(margen, margen, diametro - 2 * margen, diametro - 2 * margen))
    pen= QPen(QColor("#FFFFFF"), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    centro= diametro / 2
    brazo= diametro * 0.24
    painter.drawLine(QPointF(centro - brazo, centro), QPointF(centro + brazo, centro))
    if not expandido:
        painter.drawLine(QPointF(centro, centro - brazo), QPointF(centro, centro + brazo))
    painter.end()
    return pixmap


#Icono de lupa dibujado a mano con QPainter para la barra de búsqueda
#(mismo diseño que configuracion.py, horario.py y asistencia.py).
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


#Punto circular que 'respira' en bucle — usado para señalar 'hoy' o el
#próximo evento sin recurrir a tarjetas de indicador.
class _PuntoPulso(QWidget):

    def __init__(self, color="#22C55E", diametro=9, parent=None):

        super().__init__(parent)
        self._color= QColor(color)
        self._d= diametro
        self.setFixedSize(diametro, diametro)
        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(1.0)
        self.setGraphicsEffect(self._efecto)
        self._anim= QPropertyAnimation(self._efecto, b"opacity", self)
        self._anim.setDuration(1100)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.32)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def poner_color(self, color):

        self._color= QColor(color)
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._d, self._d)


#Contenedor tipo 'panel' con esquinas redondeadas y una sombra suave que
#se eleva al pasar el mouse. Es solo un envoltorio visual reutilizable
#(formulario, resumen, franja semanal) — no es una tarjeta de indicador/KPI.
class PanelFlotante(QFrame):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("PanelFlotanteCalendario")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._blur_normal= 14
        self._blur_hover= 24
        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setBlurRadius(self._blur_normal)
        self._sombra.setOffset(0, 3)
        self._sombra.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(self._sombra)

    def enterEvent(self, evento):

        self._animar_sombra(self._blur_hover)
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._animar_sombra(self._blur_normal)
        super().leaveEvent(evento)

    def _animar_sombra(self, destino):

        anim= QPropertyAnimation(self._sombra, b"blurRadius", self)
        anim.setDuration(200)
        anim.setStartValue(self._sombra.blurRadius())
        anim.setEndValue(destino)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_sombra_activa= anim
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def aplicar_colores(self, bg, borde):

        self.setStyleSheet(f"""
            QFrame#PanelFlotanteCalendario {{
                background-color: {bg};
                border: 1px solid {borde};
                border-radius: 14px;
            }}
        """)


#Chip de un día dentro de la franja 'Esta semana'. Muestra el número de
#día, hasta 3 puntos de color (uno por evento, más un '+N' si sobran) y,
#si es hoy, un punto que respira. Al hacer clic filtra la tabla por ese día.
class ChipDia(QFrame):

    clicked= Signal(str)

    def __init__(self, fecha, parent=None):

        super().__init__(parent)
        self.fecha= fecha
        self.fecha_iso= fecha.strftime("%Y-%m-%d")
        self.seleccionado= False
        self.setObjectName("ChipDia")
        self.setFixedSize(54, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        lay= QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 6)
        lay.setSpacing(3)

        self.lbl_dow= QLabel(DIAS_SEMANA_ABBR[fecha.weekday()])
        self.lbl_dow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_num= QLabel(str(fecha.day))
        self.lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._zona_pulso= QWidget()
        self._zona_pulso.setStyleSheet("background: transparent;")
        self._zona_pulso.setFixedHeight(9)
        self._lay_pulso= QHBoxLayout(self._zona_pulso)
        self._lay_pulso.setContentsMargins(0, 0, 0, 0)
        self._lay_pulso.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._fila_dots= QWidget()
        self._fila_dots.setStyleSheet("background: transparent;")
        self._lay_dots= QHBoxLayout(self._fila_dots)
        self._lay_dots.setContentsMargins(0, 0, 0, 0)
        self._lay_dots.setSpacing(3)
        self._lay_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(self.lbl_dow)
        lay.addWidget(self.lbl_num)
        lay.addWidget(self._zona_pulso)
        lay.addWidget(self._fila_dots)

    def poner_hoy(self, es_hoy):

        while self._lay_pulso.count():
            item= self._lay_pulso.takeAt(0)
            w= item.widget()
            if w:
                w.deleteLater()
        if es_hoy:
            self._lay_pulso.addWidget(_PuntoPulso("#22C55E", 7))

    def poner_eventos(self, tipos):

        while self._lay_dots.count():
            item= self._lay_dots.takeAt(0)
            w= item.widget()
            if w:
                w.deleteLater()
        max_dots= 3
        total= len(tipos)
        mostrar= tipos[:max_dots]
        extra= total - max_dots
        for tipo in mostrar:
            lbl_punto= QLabel()
            lbl_punto.setFixedSize(6, 6)
            color= TIPO_COLORES.get(tipo, "#94A3B8")
            lbl_punto.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            self._lay_dots.addWidget(lbl_punto)
        if extra > 0:
            lbl_extra_lbl= QLabel(f"+{extra}")
            lbl_extra_lbl.setStyleSheet("font-size: 9px; font-weight: 700; background: transparent;")
            self._lay_dots.addWidget(lbl_extra_lbl)

    def mousePressEvent(self, evento):

        self.clicked.emit(self.fecha_iso)
        super().mousePressEvent(evento)

    def aplicar_estilo(self, bg, borde, txt_prim, txt_sec, accent, es_hoy):

        if self.seleccionado:
            fondo= _hex_a_rgba(accent, 0.20)
            borde_final= accent
        elif es_hoy:
            fondo= _hex_a_rgba(accent, 0.08)
            borde_final= _hex_a_rgba(accent, 0.55)
        else:
            fondo= bg
            borde_final= borde
        self.setStyleSheet(f"""
            QFrame#ChipDia {{
                background-color: {fondo};
                border: 1.5px solid {borde_final};
                border-radius: 12px;
            }}
        """)
        self.lbl_dow.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {txt_sec}; "
            f"background: transparent; letter-spacing: 1px;")
        peso= "800" if (es_hoy or self.seleccionado) else "600"
        color_num= accent if (es_hoy or self.seleccionado) else txt_prim
        self.lbl_num.setStyleSheet(
            f"font-size: 16px; font-weight: {peso}; color: {color_num}; background: transparent;")


#Aviso flotante no bloqueante que aparece brevemente sobre el contenido
#del módulo y se desvanece solo. Sustituye a los diálogos emergentes para
#confirmaciones rápidas (guardado, eliminado, validaciones) sin interrumpir
#el flujo de trabajo.
class _ToastFlotante(QFrame):

    def __init__(self, parent):

        super().__init__(parent)
        self.setObjectName("ToastCalendario")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(16, 10, 16, 10)
        disposicion.setSpacing(10)
        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji("📅", 20))
        self.lbl_icono.setStyleSheet("font-size: 15px; background: transparent; color: white;")
        self.lbl_texto= QLabel("")
        self.lbl_texto.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent; color: white;")
        self.lbl_texto.setWordWrap(True)
        self.lbl_texto.setMaximumWidth(280)
        disposicion.addWidget(self.lbl_icono)
        disposicion.addWidget(self.lbl_texto, 1)
        self.hide()

        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(0.0)
        self.setGraphicsEffect(self._efecto)

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setBlurRadius(24)
        self._sombra.setOffset(0, 6)
        self._sombra.setColor(QColor(0, 0, 0, 90))
        #Nota: no se puede tener dos QGraphicsEffect en el mismo widget a la vez, así que el brillo de sombra se logra
        #con el propio fondo + borde del toast.

        self._timer_oculto= QTimer(self)
        self._timer_oculto.setSingleShot(True)
        self._timer_oculto.timeout.connect(self._ocultar)

    def mostrar(self, texto, tipo="exito"):

        colores= {"exito": "#16A34A", "error": "#DC2626", "info": "#2563EB", "advertencia": "#D97706"}
        iconos= {"exito": "", "error": "", "info": "ℹ", "advertencia": ""}
        color= colores.get(tipo, "#16A34A")
        self.setStyleSheet(f"""
            QFrame#ToastCalendario {{
                background-color: {color};
                border-radius: 10px;
            }}
        """)
        self.lbl_icono.setText(iconos.get(tipo, ""))
        self.lbl_texto.setText(texto)
        self.adjustSize()
        self._reposicionar()
        self.show()
        self.raise_()

        anim_in= QPropertyAnimation(self._efecto, b"opacity", self)
        anim_in.setDuration(220)
        anim_in.setStartValue(self._efecto.opacity())
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in= anim_in
        anim_in.start()

        self._timer_oculto.start(2600)

    def _reposicionar(self):

        padre= self.parentWidget()
        if padre is None:
            return
        pos_x= padre.width() - self.width() - 26
        self.move(max(pos_x, 12), 16)

    def _ocultar(self):

        anim_out= QPropertyAnimation(self._efecto, b"opacity", self)
        anim_out.setDuration(320)
        anim_out.setStartValue(self._efecto.opacity())
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        anim_out.finished.connect(self.hide)
        self._anim_out= anim_out
        anim_out.start()


#Bloque colapsable con un encabezado clicable (icono ⊕/⊖ + título).
#Empieza cerrado por defecto -mismo widget que usa horario.py para
#'Agregar una clase local'-; aquí se usa para que el formulario de
#'Registrar evento' no le gane protagonismo visual a los eventos que ya
#existen, pero siga a un clic de distancia para quien sí lo necesite.
class PanelDesplegable(QWidget):

    def __init__(self, titulo, parent=None):

        super().__init__(parent)
        self._titulo= titulo
        self._expandido= False
        disposicion= QVBoxLayout(self)
        #6px arriba/abajo: aire propio y "correcto" respecto a lo que va antes y después en la pestaña (antes solo
        #tenía márgenes 0, y sin el hueco vacío que dejaba el bug de altura, el encabezado quedaba pegado directamente
        #a la barra segmentada/buscador de al lado). No se toca el spacing lateral (0) porque el ancho ya lo resuelve
        #el propio layout de la pestaña.
        disposicion.setContentsMargins(0, 6, 0, 6)
        disposicion.setSpacing(0)

        self.btn_cabecera= QPushButton(f" {titulo}")
        self.btn_cabecera.setIcon(QIcon(_pixmap_circulo_mas_menos(False)))
        self.btn_cabecera.setIconSize(_QSize_emoji(18, 18))
        self.btn_cabecera.setCursor(Qt.CursorShape.PointingHandCursor)
        self._aplicar_color_tema()
        self.btn_cabecera.clicked.connect(self._alternar)
        disposicion.addWidget(self.btn_cabecera)

        self.contenedor= QWidget()
        self.contenedor.setMaximumHeight(0)
        #Además de limitar la altura máxima a 0, se oculta de verdad (setVisible(False)) mientras está colapsado. Con
        #formularios muy
        #altos (p. ej. "Nueva tarea" de Banco de Tareas, con más de 10
        #campos) solo el maximumHeight podía dejar un hueco vacío visible debajo del encabezado -el layout interno del
        #formulario seguía reclamando su tamaño mínimo-. Un widget genuinamente oculto NUNCA reserva espacio en el
        #layout del padre, así que este es el único mecanismo 100% confiable para que "colapsado" signifique
        #"prácticamente no ocupa nada" en todos los casos.
        self.contenedor.setVisible(False)
        self.contenedor_layout= QVBoxLayout(self.contenedor)
        self.contenedor_layout.setContentsMargins(4, 12, 4, 4)
        disposicion.addWidget(self.contenedor)

        self._anim= QPropertyAnimation(self.contenedor, b"maximumHeight")
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.finished.connect(self._al_terminar_animacion)

    def cuerpo_layout(self):

        return self.contenedor_layout

    def _alternar(self):

        self.expandir(not self._expandido)

    #Color del texto del encabezado según el modo claro/oscuro:
    #negro (casi) puro en claro, blanco en oscuro. El fondo gris
    #translúcido funciona igual en ambos modos.
    def _aplicar_color_tema(self):

        modo_oscuro= getattr(self.window(), "modo_oscuro", False)
        color= "#FFFFFF" if modo_oscuro else "#0F172A"
        self.btn_cabecera.setStyleSheet(f"""
            QPushButton {{ text-align: left; padding: 9px 14px; border-radius: 10px;
                          background: rgba(127,127,127,0.10); font-weight: 700;
                          color: {color}; }}
            QPushButton:hover {{ background: rgba(127,127,127,0.18); }}
        """)

    #Refresca el color del texto del encabezado al cambiar de tema en
    #runtime; el showEvent solo dispara la primera vez que se muestra.
    def actualizar_color_tema(self):

        self._aplicar_color_tema()

    def showEvent(self, evento):

        #Al mostrarse la ventana ya está enganchada al main window, así que aquí el modo claro/oscuro se conoce con
        #certeza (en __init__ puede no estarlo todavía si el panel se crea antes de asignar el padre).
        try:

            self._aplicar_color_tema()
        except RuntimeError:
            pass
        super().showEvent(evento)

    def _al_terminar_animacion(self):

        #Solo se oculta de verdad cuando TERMINA la animación de cierre -mientras se está abriendo tiene que permanecer
        #visible para que se vea crecer-. Si en el ínterin el usuario volvió a abrirlo, este
        #callback llega con self._expandido=True y no hace nada.
        if not self._expandido:
            self.contenedor.setVisible(False)

    def expandir(self, expandir=True, animar=True):

        self._expandido= expandir
        self.btn_cabecera.setIcon(QIcon(_pixmap_circulo_mas_menos(expandir)))
        if expandir:
            self.contenedor.setVisible(True)
        #Forzar el cálculo del layout antes de medir: sin esto, sizeHint() puede devolver un alto desactualizado si el
        #formulario acaba de repoblarse y la animación terminaría recortando el contenido.
        self.contenedor_layout.activate()
        destino= self.contenedor_layout.sizeHint().height() + 12 if expandir else 0
        if not animar:
            #Apertura/cierre instantáneo (p. ej. al entrar en modo edición).
            #Al abrir, SIN tope de altura (16777215 = QWIDGETSIZE_MAX): fijar
            #maximumHeight = sizeHint() + 12 subestimaba el alto real cuando
            #el formulario acababa de repoblarse (el layout todavía no había asentado), y el panel quedaba más corto que su
            #contenido RECORTANDO los campos/botones de abajo.
            self.contenedor.setMaximumHeight(16777215 if expandir else 0)
            if not expandir:
                self.contenedor.setVisible(False)
            return
        self._anim.stop()
        self._anim.setStartValue(self.contenedor.maximumHeight())
        self._anim.setEndValue(destino)
        self._anim.start()


class ModuloCalendario(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion= None
        self.gerencial= tiene_acceso_gerencial(main_window)
        self.filtro_tipo_actual= None
        self.filtro_fecha_actual= None
        self._eventos_todos= []
        self._construir_ui()
        self.refrescar()
        self.actualizar_tema()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Calendario"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar evento", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar evento seleccionado",
                         self._cargar_seleccionado)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar evento", self._eliminar)

    #Construcción de la interfaz
    def _construir_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(16)

        #--- Cabecera tipo "hero": icono + título + descripción + fecha/contador ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Calendario")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Calendario")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Eventos institucionales (exámenes, entregas, reuniones) y personales. "
            "Independiente del horario regular de clases.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        self.chip_contador= QLabel("0 eventos")
        self.chip_contador.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_hoy= QLabel("")
        self.lbl_hoy.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.lbl_hoy, 0, Qt.AlignmentFlag.AlignVCenter)

        disposicion.addWidget(self.frame_cabecera)

        #--- Panel: próximo evento ---
        self.panel_proximo= PanelFlotante()
        lay_proximo= QHBoxLayout(self.panel_proximo)
        lay_proximo.setContentsMargins(20, 16, 20, 16)
        lay_proximo.setSpacing(14)
        self._pulso_proximo= _PuntoPulso("#94A3B8", 12)
        lay_proximo.addWidget(self._pulso_proximo, 0, Qt.AlignmentFlag.AlignVCenter)
        col_proximo= QVBoxLayout()
        col_proximo.setSpacing(2)
        self.lbl_proximo_eyebrow= QLabel("PRÓXIMO EVENTO")
        self.lbl_proximo_titulo= QLabel("—")
        self.lbl_proximo_titulo.setStyleSheet(
            "font-size: 18px; font-weight: 800; background: transparent;")
        self.lbl_proximo_fecha= QLabel("")
        col_proximo.addWidget(self.lbl_proximo_eyebrow)
        col_proximo.addWidget(self.lbl_proximo_titulo)
        col_proximo.addWidget(self.lbl_proximo_fecha)
        lay_proximo.addLayout(col_proximo, 1)
        self.lbl_proximo_cuenta= QLabel("")
        self.lbl_proximo_cuenta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_proximo.addWidget(self.lbl_proximo_cuenta, 0, Qt.AlignmentFlag.AlignVCenter)
        disposicion.addWidget(self.panel_proximo)

        #--- Panel: franja de la semana ---
        self.panel_semana= PanelFlotante()
        lay_semana= QVBoxLayout(self.panel_semana)
        lay_semana.setContentsMargins(18, 14, 18, 16)
        lay_semana.setSpacing(10)
        self.lbl_semana_titulo= QLabel("Esta semana")
        self.lbl_semana_titulo.setStyleSheet(
            "font-size: 13px; font-weight: 700; background: transparent;")
        lay_semana.addWidget(self.lbl_semana_titulo)
        fila_dias= QHBoxLayout()
        fila_dias.setSpacing(8)
        fila_dias.addStretch()
        self.chips_semana= []
        hoy= date.today()
        lunes= hoy - timedelta(days=hoy.weekday())
        for i in range(7):
            chip= ChipDia(lunes + timedelta(days=i))
            chip.clicked.connect(self._al_click_dia)
            self.chips_semana.append(chip)
            fila_dias.addWidget(chip)
        fila_dias.addStretch()
        lay_semana.addLayout(fila_dias)
        disposicion.addWidget(self.panel_semana)

        #--- Panel: formulario de registro (colapsado por defecto — ver PanelDesplegable arriba: la app se ve menos
        #cargada al abrir el módulo y quien solo quiere revisar los eventos ya cargados no tiene que lidiar con el
        #formulario completo. Un clic en el encabezado lo despliega cuando sí hace falta crear/editar algo). ---
        self.panel_registro= PanelDesplegable("Registrar evento")
        self.panel_formulario= PanelFlotante()
        self.panel_registro.cuerpo_layout().addWidget(self.panel_formulario)
        lay_form_outer= QVBoxLayout(self.panel_formulario)
        lay_form_outer.setContentsMargins(20, 16, 20, 18)
        lay_form_outer.setSpacing(12)

        fila_form_header= QHBoxLayout()
        fila_form_header.addStretch()
        self.lbl_estado_form= QLabel("Nuevo evento")
        fila_form_header.addWidget(self.lbl_estado_form)
        lay_form_outer.addLayout(fila_form_header)

        form= QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        self.in_titulo= QLineEdit()
        self.in_titulo.setPlaceholderText("Título del evento")
        limitar_campo_texto(self.in_titulo, 300)
        self.combo_tipo= QComboBox()
        self.combo_tipo.addItems(TIPOS_EVENTO)
        conectar_tooltip_seleccion(self.combo_tipo, "Tipo de evento")
        self.combo_tipo.currentTextChanged.connect(self._sync_visibilidad_por_tipo)
        self.date_fecha= QDateEdit(calendarPopup=True)
        self.date_fecha.setDate(QDate.currentDate())
        self.in_time_hora= QTimeEdit()
        self.in_time_hora.setTime(QTime(8, 0))
        aplicar_formato_widget_fecha(self.date_fecha, self.main_window)
        aplicar_formato_widget_hora(self.in_time_hora, self.main_window)
        self.combo_curso= QComboBox()
        self.combo_curso.currentIndexChanged.connect(self._curso_evento_cambio)
        self.combo_seccion= QComboBox()
        self.combo_materia= QComboBox()
        self.in_desc= QTextEdit()
        self.in_desc.setPlaceholderText("Detalle (opcional)")
        limitar_campo_texto(self.in_desc, 5000)
        self.in_desc.setFixedHeight(70)
        self.lbl_curso= QLabel("Curso/Grado (opcional):")
        self.lbl_seccion= QLabel("Sección (opcional):")
        self.lbl_materia= QLabel("Materia (opcional):")
        form.addWidget(self.in_titulo, 0, 0, 1, 2)
        form.addWidget(QLabel("Tipo:"), 0, 2)
        form.addWidget(self.combo_tipo, 0, 3)
        form.addWidget(QLabel("Fecha:"), 1, 0)
        form.addWidget(self.date_fecha, 1, 1)
        form.addWidget(QLabel("Hora:"), 1, 2)
        form.addWidget(self.in_time_hora, 1, 3)
        form.addWidget(self.lbl_curso, 2, 0)
        form.addWidget(self.combo_curso, 2, 1)
        form.addWidget(self.lbl_seccion, 2, 2)
        form.addWidget(self.combo_seccion, 2, 3)
        form.addWidget(self.lbl_materia, 3, 0)
        form.addWidget(self.combo_materia, 3, 1)
        form.addWidget(self.in_desc, 4, 0, 1, 4)
        if not self.gerencial:
            self.combo_tipo.clear()
            self.combo_tipo.addItems(["Personal"])

        #Área Técnica (Politécnico) / Carrera (Universidad): en SU PROPIA fila, dentro de un cuadrito con aire
        #alrededor — nunca apretados junto a Curso/Sección/Materia. Van ANTES del formulario (se eligen primero).
        #Acotan el combo de Sección (a secciones de esa área técnica) y el de Materia/Módulo Técnico (a los módulos de
        #esa área técnica), igual que en el resto de la app. Solo se muestran si la institución tiene ese módulo
        #activo.
        frame_filtro_tecnico_evento= QFrame()
        frame_filtro_tecnico_evento.setObjectName("CuadroFiltroTecnico")
        frame_filtro_tecnico_evento.setStyleSheet(
            "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
            "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
        fila_filtro_tecnico_evento= QHBoxLayout(frame_filtro_tecnico_evento)
        fila_filtro_tecnico_evento.setContentsMargins(14, 10, 14, 10)
        fila_filtro_tecnico_evento.setSpacing(16)
        self.lbl_filtro_especialidad_evento= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_evento= QComboBox()
        self.combo_filtro_especialidad_evento.setMinimumWidth(210)
        self.combo_filtro_especialidad_evento.currentIndexChanged.connect(self._filtro_tecnico_evento_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_evento,
            "Acota Sección y Materia/Módulo Técnico a esta área técnica (Politécnico)")
        fila_filtro_tecnico_evento.addWidget(self.lbl_filtro_especialidad_evento)
        fila_filtro_tecnico_evento.addWidget(self.combo_filtro_especialidad_evento)

        self.lbl_filtro_carrera_evento= QLabel("Carrera:")
        self.combo_filtro_carrera_evento= QComboBox()
        self.combo_filtro_carrera_evento.setMinimumWidth(210)
        self.combo_filtro_carrera_evento.currentIndexChanged.connect(self._filtro_tecnico_evento_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_evento,
            "Acota Sección a las que tienen estudiantes de esta carrera (Universidad)")
        fila_filtro_tecnico_evento.addWidget(self.lbl_filtro_carrera_evento)
        fila_filtro_tecnico_evento.addWidget(self.combo_filtro_carrera_evento)
        fila_filtro_tecnico_evento.addStretch()
        lay_form_outer.addWidget(frame_filtro_tecnico_evento)
        lay_form_outer.addLayout(form)

        fila_botones_form= QHBoxLayout()
        fila_botones_form.setSpacing(10)
        self.btn_guardar= QPushButton("Guardar Evento")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones_form.addWidget(self.btn_guardar)
        self.btn_limpiar= QPushButton("Limpiar")
        self.btn_limpiar.setIcon(icono_emoji("🧹"))
        self.btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        self.btn_limpiar.setObjectName("BtnAccionNeutro")
        self.btn_limpiar.clicked.connect(self._limpiar)
        fila_botones_form.addWidget(self.btn_limpiar)
        fila_botones_form.addStretch()
        lay_form_outer.addLayout(fila_botones_form)
        disposicion.addWidget(self.panel_registro)

        #--- Búsqueda (mismo diseño y criterio que configuracion.py) + botón de filtros de la LISTA de eventos (Curso,
        #Sección, Área Técnica, Carrera, Materia/Módulo — todos opcionales). Esto es aparte del Área Técnica/Carrera
        #que vive DENTRO del formulario de "Registrar evento": aquel acota los combos al crear un evento nuevo; este
        #filtra qué eventos YA CREADOS se listan en la tabla. Igual que en horario.py/estudiantes.py, viven en una
        #ventanita aparte para no apilar combos en la pantalla principal. ---
        fila_busqueda= QHBoxLayout()
        self.marco_busqueda= QFrame()
        self.marco_busqueda.setStyleSheet(
            "QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda= QHBoxLayout(self.marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda)
        self.in_busqueda= QLineEdit()
        limitar_campo_texto(self.in_busqueda, 150)
        self.in_busqueda.setPlaceholderText("Buscar por título, tipo o detalle…")
        self.in_busqueda.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_busqueda, 1)
        fila_busqueda.addWidget(self.marco_busqueda, 1)

        self.btn_filtros_vista= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_vista)
        self.btn_filtros_vista.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_vista.setObjectName("BtnAccionNeutro")
        self.btn_filtros_vista.setToolTip(
            "Filtrar los eventos listados por curso, sección, área técnica/carrera y materia/módulo")
        self.btn_filtros_vista.clicked.connect(self._abrir_dialogo_filtros_vista)
        fila_busqueda.addWidget(self.btn_filtros_vista)
        disposicion.addLayout(fila_busqueda)

        #Combos del diálogo de filtros de la lista: se crean aquí como atributos normales del módulo, pero se colocan
        #dentro del diálogo (ver _construir_dialogo_filtros_vista), no en esta pantalla.
        self.combo_filtro_vista_curso= QComboBox()
        self.combo_filtro_vista_curso.currentIndexChanged.connect(self._curso_filtro_vista_cambio)
        self.combo_filtro_vista_seccion= QComboBox()
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_vista_seccion.currentIndexChanged.connect(lambda _: self._filtro_vista_cambio())
        self.lbl_filtro_vista_especialidad= QLabel("Área Técnica:")
        self.combo_filtro_vista_especialidad= QComboBox()
        self.combo_filtro_vista_especialidad.currentIndexChanged.connect(self._filtro_tecnico_vista_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_vista_especialidad,
            "Filtrar los eventos por área técnica de la sección (Politécnico)")
        self.lbl_filtro_vista_carrera= QLabel("Carrera:")
        self.combo_filtro_vista_carrera= QComboBox()
        self.combo_filtro_vista_carrera.currentIndexChanged.connect(self._filtro_tecnico_vista_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_vista_carrera,
            "Filtrar los eventos por carrera: solo secciones con estudiantes de esa carrera (Universidad)")
        self.lbl_filtro_vista_materia= QLabel("Materia (opcional):")
        self.combo_filtro_vista_materia= QComboBox()
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_vista_materia.currentIndexChanged.connect(lambda _: self._filtro_vista_cambio())
        self._construir_dialogo_filtros_vista()

        #Debounce de 150ms: evita re-filtrar/repintar la tabla en cada tecla cuando se escribe rápido, igual que en
        #configuracion.py.
        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._filtro_busqueda_cambio)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador de búsqueda
        self.in_busqueda.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        #--- Filtro dinámico por tipo (chips) ---
        fila_chips= QHBoxLayout()
        fila_chips.setSpacing(8)
        lbl_filtrar= QLabel("Filtrar:")
        lbl_filtrar.setObjectName("DescModulo")
        fila_chips.addWidget(lbl_filtrar)
        self.chips_filtro= []
        chip_todos= self._crear_chip_filtro("Todos", None)
        fila_chips.addWidget(chip_todos)
        self.chips_filtro.append((chip_todos, "#64748B", None))
        for t in TIPOS_EVENTO:
            color= TIPO_COLORES.get(t, "#64748B")
            chip= self._crear_chip_filtro(t, t, TIPO_ICONOS.get(t))
            fila_chips.addWidget(chip)
            self.chips_filtro.append((chip, color, t))
        fila_chips.addStretch()
        disposicion.addLayout(fila_chips)
        self._restilizar_chips_filtro()

        #--- Indicador de filtro por día (aparece/desaparece con la franja semanal) ---
        self.fila_filtro_fecha= QWidget()
        lay_ff= QHBoxLayout(self.fila_filtro_fecha)
        lay_ff.setContentsMargins(0, 0, 0, 0)
        lay_ff.setSpacing(2)
        self.lbl_filtro_fecha= QLabel("")
        lay_ff.addWidget(self.lbl_filtro_fecha)
        self.btn_limpiar_filtro_fecha= QPushButton("")
        self.btn_limpiar_filtro_fecha.setIcon(icono_emoji("🧹"))
        self.btn_limpiar_filtro_fecha.setIconSize(_QSize_emoji(16, 16))
        self.btn_limpiar_filtro_fecha.setFixedWidth(26)
        self.btn_limpiar_filtro_fecha.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limpiar_filtro_fecha.clicked.connect(self._limpiar_filtro_fecha)
        lay_ff.addWidget(self.btn_limpiar_filtro_fecha)
        lay_ff.addStretch()
        self.fila_filtro_fecha.setVisible(False)
        disposicion.addWidget(self.fila_filtro_fecha)

        #Tabla estilo Omega POS Columnas: ID(oculta), Fecha, Hora, Título, Curso, Sección, Materia/Módulo, Tipo,
        #Detalle — Curso/Sección/Materia se muestran igual que en el módulo de
        #Observaciones (tabla de referencia), para que se vea de un vistazo
        #a qué grupo pertenece cada evento sin tener que abrir el detalle.

        self.tabla= QTableWidget(0, 9)
        aplicar_estructura_tabla(self.tabla)

        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Fecha", "Hora", "Título", "Curso", "Sección", "Materia/Módulo", "Tipo", "Detalle"])
        self.tabla.setColumnHidden(0, True)
        header= self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(True)
        self.tabla.setMinimumHeight(380)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(38)
        self.tabla.setColumnWidth(1, 100)
        self.tabla.setColumnWidth(2, 100)
        self.tabla.setColumnWidth(3, 200)
        self.tabla.setColumnWidth(4, 110)
        self.tabla.setColumnWidth(5, 100)
        self.tabla.setColumnWidth(6, 150)
        self.tabla.setColumnWidth(7, 155)
        disposicion.addWidget(self.tabla, 1)
        self.paginacion= ControlPaginacion()
        #Calendario lista eventos (títulos cortos), así que 10 por página se lee más cómodo que el valor por defecto
        #usado en otros módulos con filas más densas. Se intenta de forma defensiva por si el nombre del atributo
        #cambia en una futura versión de ControlPaginacion.
        for _atributo in ("tam_pagina", "por_pagina", "page_size", "_tam_pagina"):
            if hasattr(self.paginacion, _atributo):
                setattr(self.paginacion, _atributo, 10)
                break
        self.paginacion.cambio.connect(self._aplicar_filtros_y_tabla)
        disposicion.addWidget(self.paginacion)

        #Botón ⛶ que abre la tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo maximizado
        #-mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-. Se agrega recién
        #aquí porque necesita self.paginacion ya construido.
        agregar_boton_pantalla_completa(
            None, [self.tabla, self.paginacion],
            titulo= "Calendario", parent=self)
        fila_botones= QHBoxLayout()
        btn_editar= QPushButton("Cargar Seleccionado")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_seleccionado)
        fila_botones.addWidget(btn_editar)
        btn_eliminar= QPushButton("Eliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar)
        fila_botones.addWidget(btn_eliminar)
        def _extra_botones_detalle(fila_sel):

            item_desc= self.tabla.item(fila_sel, 8)
            texto_completo= (item_desc.text() if item_desc else "").strip()
            return [("Ver detalle completo",
                      #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                      lambda: mostrar_texto_largo(self, "Detalle completo", texto_completo))]

        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla, self, titulo="Detalle del Evento",
                                             proveedor_extra_botones= _extra_botones_detalle)
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        #Aviso flotante (toast) — se superpone al contenido, no forma parte del layout.
        self.toast= _ToastFlotante(self)

        self.lbl_hoy.setText(self._formatear_fecha_larga(date.today()).capitalize())

    def resizeEvent(self, evento):

        super().resizeEvent(evento)
        if hasattr(self, "toast"):
            self.toast._reposicionar()

    #FORMULARIO: mostrar/ocultar sección y materia según el tipo elegido
    def _sync_visibilidad_por_tipo(self, texto):

        if not texto:
            return
        mostrar= (texto != "Personal")
        for w in (self.lbl_curso, self.combo_curso, self.lbl_seccion, self.combo_seccion,
                  self.lbl_materia, self.combo_materia):
            _fundido(w, mostrar, duracion=200)

    def _crear_chip_filtro(self, texto, dato, icono=None):

        btn= QPushButton(texto)
        if icono:
            btn.setIcon(icono_emoji(icono))
            btn.setIconSize(_QSize_emoji(14, 14))
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setChecked(dato == self.filtro_tipo_actual)
        #el primer parámetro absorbe el checked de la señal y no se usa; el valor por defecto fija el de esta vuelta del bucle
        btn.clicked.connect(lambda _=False, d=dato: self._al_filtro_tipo(d))
        return btn

    def _al_filtro_tipo(self, dato):

        self.filtro_tipo_actual= dato
        for chip, color, d in self.chips_filtro:
            chip.setChecked(d == dato)
        self._restilizar_chips_filtro()
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    def _restilizar_chips_filtro(self):

        for chip, color, dato in self.chips_filtro:
            if chip.isChecked():
                chip.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: white;
                        border: none;
                        border-radius: 14px;
                        padding: 6px 14px;
                        font-weight: 700;
                        font-size: 12px;
                    }}
                """)
            else:
                suave= _hex_a_rgba(color, 0.14)
                borde= _hex_a_rgba(color, 0.40)
                hover= _hex_a_rgba(color, 0.24)
                chip.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {suave};
                        color: {color};
                        border: 1px solid {borde};
                        border-radius: 14px;
                        padding: 6px 14px;
                        font-weight: 600;
                        font-size: 12px;
                    }}
                    QPushButton:hover {{ background-color: {hover}; }}
                """)

    #Carga de datos (una sola consulta reutilizada por el resumen y la tabla)
    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo). Mismo criterio usado en materias.py,
    #estudiantes.py y banco_tareas.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la institución es de tipo Universidad (o Personalizado con el
    #módulo Universidad activo). Mismo criterio usado en materias.py,
    #estudiantes.py y banco_tareas.py.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    def _cargar_combos(self):

        poblar_combo_curso(self.combo_curso, incluir_todos=False)
        self._cargar_filtro_tecnico_evento()
        self._filtrar_secciones_evento_por_curso()
        self._cargar_materias_combo_evento()
        poblar_combo_curso(self.combo_filtro_vista_curso, incluir_todos=True)
        self._cargar_filtro_tecnico_vista()
        self._filtrar_secciones_vista_por_curso()
        self._cargar_materias_combo_vista()

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera del
    #formulario 'Registrar evento' solo se muestran/pueblan si la
    #institución tiene ese módulo activo.
    def _cargar_filtro_tecnico_evento(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_evento.setVisible(es_poli)
        self.combo_filtro_especialidad_evento.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_evento.currentData()
            self.combo_filtro_especialidad_evento.blockSignals(True)
            self.combo_filtro_especialidad_evento.clear()
            self.combo_filtro_especialidad_evento.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_evento.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_evento.findData(actual)
            self.combo_filtro_especialidad_evento.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_evento.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_evento.setVisible(es_uni)
        self.combo_filtro_carrera_evento.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_evento.currentData()
            self.combo_filtro_carrera_evento.blockSignals(True)
            self.combo_filtro_carrera_evento.clear()
            self.combo_filtro_carrera_evento.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_evento.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_carrera_evento.findData(actual)
            self.combo_filtro_carrera_evento.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_evento.blockSignals(False)

    def _filtro_tecnico_evento_cambio(self):

        self._filtrar_secciones_evento_por_curso()
        self._cargar_materias_combo_evento()

    def _cargar_materias_combo_evento(self):

        #El combo mezcla materias académicas y módulos técnicos (no se filtra por modelo_evaluacion salvo que se haya
        #elegido un Área Técnica), así que en Politécnico el label y el tooltip lo dejan claro — mismo criterio ligero
        #que usa materias.py.
        es_poli= self._es_politecnico()
        self.lbl_materia.setText("Materia / Módulo Técnico (opcional):" if es_poli else "Materia (opcional):")
        conectar_tooltip_seleccion(self.combo_materia,
            "Materia o módulo técnico relacionado con este evento (opcional)"
            if es_poli else "Materia relacionada con este evento (opcional)")

        especialidad_id= self.combo_filtro_especialidad_evento.currentData() if es_poli else None
        actual= self.combo_materia.currentData()
        self.combo_materia.clear()
        self.combo_materia.addItem("— Ninguna —", None)
        conn= obtener_conexion()
        c= conn.cursor()
        if especialidad_id is not None:
            #Un Área Técnica elegida SÍ filtra estrictamente el combo de Materia/Módulo Técnico a esa área — pedido
            #explícito: al elegir curso+sección+área técnica, el combo debe listar únicamente los módulos de esa área.
            c.execute("""SELECT id, nombre FROM materias
                         WHERE estado='Activa' AND especialidad_id=? ORDER BY nombre""", (especialidad_id,))
        else:
            c.execute("SELECT id, nombre FROM materias WHERE estado='Activa' ORDER BY nombre")
        for fila in c.fetchall():
            self.combo_materia.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= self.combo_materia.findData(actual)
        self.combo_materia.setCurrentIndex(idx if idx >= 0 else 0)

    def _curso_evento_cambio(self):

        self._filtrar_secciones_evento_por_curso()

    #Recarga 'Sección' con solo las secciones del curso elegido en 'Curso/Grado'.
    #Igual que en TODOS los módulos de AcaDeXI (patrón de referencia: 'Asignar Clase'
    #en Horarios de Materias), Curso es obligatorio primero — sin excepciones, ni
    #siquiera para un campo opcional como este: mientras no se elija un curso,
    #Sección queda vacía con el placeholder 'Selecciona primero un curso/grado…'.
    #
    #Si además hay un Área Técnica/Carrera elegidos, la lista de secciones se
    #acota más: Área Técnica usa secciones.especialidad_id directamente;
    #Carrera (dato por estudiante, no por sección) se resuelve viendo qué
    #secciones tienen al menos un estudiante activo de esa carrera.
    def _filtrar_secciones_evento_por_curso(self, seccion_id_preseleccionar=None):

        cascada_seccion_por_curso(self.combo_curso, self.combo_seccion, incluir_todas=False)

        especialidad_id= (self.combo_filtro_especialidad_evento.currentData()
                            if self._es_politecnico() else None)
        carrera_id= self.combo_filtro_carrera_evento.currentData() if self._es_universidad() else None
        if especialidad_id is not None or carrera_id is not None:
            secciones_carrera= None
            if carrera_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                             WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
                secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
                conn.close()
            actual= self.combo_seccion.currentData()
            #Se recorre de atrás hacia adelante para poder remover ítems sin que los índices restantes se corran bajo los
            #pies del bucle.
            for i in range(self.combo_seccion.count() - 1, 0, -1):
                seccion_id= self.combo_seccion.itemData(i)
                if seccion_id is None:
                    continue
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT especialidad_id FROM secciones WHERE id=?", (seccion_id,))
                fila_sec= c.fetchone()
                conn.close()
                especialidad_seccion= fila_sec["especialidad_id"] if fila_sec else None
                if especialidad_id is not None and especialidad_seccion != especialidad_id:
                    self.combo_seccion.removeItem(i)
                    continue
                if secciones_carrera is not None and seccion_id not in secciones_carrera:
                    self.combo_seccion.removeItem(i)
            idx= self.combo_seccion.findData(actual)
            self.combo_seccion.setCurrentIndex(idx if idx >= 0 else 0)

        if seccion_id_preseleccionar is not None:
            idx= self.combo_seccion.findData(seccion_id_preseleccionar)
            self.combo_seccion.setCurrentIndex(idx if idx >= 0 else 0)

    #Filtros de la lista de eventos (ventanita aparte, todos opcionales)
    #Ventanita (no modal) con los filtros de la TABLA de eventos —
    #distinta del formulario 'Registrar evento'. Mismo patrón que usan
    #estudiantes.py y horario.py: todos los combos viven aquí para no
    #apilarlos en la pantalla principal, y la tabla de atrás se sigue
    #actualizando en vivo mientras el diálogo queda abierto.
    def _construir_dialogo_filtros_vista(self):

        self.dialogo_filtros_vista= QDialog(self)
        self.dialogo_filtros_vista.setObjectName("DialogoFiltros")
        self.dialogo_filtros_vista.setWindowTitle("Filtros de Calendario")
        aplicar_icono_ventana(self.dialogo_filtros_vista, ICONO_FILTRO)
        self.dialogo_filtros_vista.setModal(False)
        self.dialogo_filtros_vista.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_vista)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        lbl_icono_encabezado= QLabel()
        pixmap_boton_filtro(lbl_icono_encabezado, 20)
        lbl_icono_encabezado.setObjectName("IconoEncabezadoFiltros")
        fila_encabezado.addWidget(lbl_icono_encabezado)
        lbl_titulo_encabezado= QLabel("Filtros")
        lbl_titulo_encabezado.setObjectName("TituloEncabezadoFiltros")
        fila_encabezado.addWidget(lbl_titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        lbl_subtitulo= QLabel("Todos son opcionales: combina los que necesites, la lista se actualiza al instante.")
        lbl_subtitulo.setObjectName("SubtituloFiltros")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        self.linea_separadora_filtros_vista= QFrame()
        self.linea_separadora_filtros_vista.setFrameShape(QFrame.Shape.HLine)
        self.linea_separadora_filtros_vista.setObjectName("SeparadorFiltros")
        lay_dialogo.addWidget(self.linea_separadora_filtros_vista)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            (None, self.combo_filtro_vista_especialidad),   #etiqueta propia: lbl_filtro_vista_especialidad
            (None, self.combo_filtro_vista_carrera),        #etiqueta propia: lbl_filtro_vista_carrera
            ("Curso/Grado:", self.combo_filtro_vista_curso),
            ("Sección:", self.combo_filtro_vista_seccion),
            (None, self.combo_filtro_vista_materia),        #etiqueta propia: lbl_filtro_vista_materia
        ):
            if combo is self.combo_filtro_vista_especialidad:
                grid.addWidget(self.lbl_filtro_vista_especialidad, fila, 0)
            elif combo is self.combo_filtro_vista_carrera:
                grid.addWidget(self.lbl_filtro_vista_carrera, fila, 0)
            elif combo is self.combo_filtro_vista_materia:
                grid.addWidget(self.lbl_filtro_vista_materia, fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        btn_limpiar= QPushButton("Limpiar filtros")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_filtros_vista)
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_vista.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_vista(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_vista.parent() is not _fc:
            self.dialogo_filtros_vista.setParent(_fc)
        self.dialogo_filtros_vista.show()
        self.dialogo_filtros_vista.raise_()
        self.dialogo_filtros_vista.activateWindow()

    def _limpiar_filtros_vista(self):

        self.combo_filtro_vista_especialidad.blockSignals(True)
        self.combo_filtro_vista_especialidad.setCurrentIndex(0)
        self.combo_filtro_vista_especialidad.blockSignals(False)
        self.combo_filtro_vista_carrera.blockSignals(True)
        self.combo_filtro_vista_carrera.setCurrentIndex(0)
        self.combo_filtro_vista_carrera.blockSignals(False)
        self.combo_filtro_vista_curso.blockSignals(True)
        self.combo_filtro_vista_curso.setCurrentIndex(0)
        self.combo_filtro_vista_curso.blockSignals(False)
        self._filtrar_secciones_vista_por_curso()
        self.combo_filtro_vista_materia.blockSignals(True)
        self.combo_filtro_vista_materia.setCurrentIndex(0)
        self.combo_filtro_vista_materia.blockSignals(False)
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    #Puebla Área Técnica/Carrera del diálogo de filtros de la lista;
    #solo se muestran si la institución tiene ese módulo activo (mismo
    #criterio que en el formulario 'Registrar evento').
    def _cargar_filtro_tecnico_vista(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_vista_especialidad.setVisible(es_poli)
        self.combo_filtro_vista_especialidad.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_vista_especialidad.currentData()
            self.combo_filtro_vista_especialidad.blockSignals(True)
            self.combo_filtro_vista_especialidad.clear()
            self.combo_filtro_vista_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_vista_especialidad.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_vista_especialidad.findData(actual)
            self.combo_filtro_vista_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_vista_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_vista_carrera.setVisible(es_uni)
        self.combo_filtro_vista_carrera.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_vista_carrera.currentData()
            self.combo_filtro_vista_carrera.blockSignals(True)
            self.combo_filtro_vista_carrera.clear()
            self.combo_filtro_vista_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_vista_carrera.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_vista_carrera.findData(actual)
            self.combo_filtro_vista_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_vista_carrera.blockSignals(False)

    def _filtro_tecnico_vista_cambio(self):

        self._filtrar_secciones_vista_por_curso()
        self._cargar_materias_combo_vista()
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    #Igual que en el formulario: en Politécnico el combo mezcla materias
    #académicas y módulos técnicos, así que el label y el tooltip lo
    #aclaran; si además hay un Área Técnica elegida en el filtro, la lista
    #se acota estrictamente a los módulos de esa área.
    def _cargar_materias_combo_vista(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_vista_materia.setText(
            "Materia / Módulo Técnico (opcional):" if es_poli else "Materia (opcional):")
        conectar_tooltip_seleccion(self.combo_filtro_vista_materia,
            "Filtrar por materia o módulo técnico relacionado con el evento (opcional)"
            if es_poli else "Filtrar por materia relacionada con el evento (opcional)")

        especialidad_id= self.combo_filtro_vista_especialidad.currentData() if es_poli else None
        actual= self.combo_filtro_vista_materia.currentData()
        self.combo_filtro_vista_materia.blockSignals(True)
        self.combo_filtro_vista_materia.clear()
        self.combo_filtro_vista_materia.addItem(
            "Todas las materias / módulos" if es_poli else "Todas las materias", None)
        conn= obtener_conexion()
        c= conn.cursor()
        if especialidad_id is not None:
            c.execute("""SELECT id, nombre FROM materias
                         WHERE estado='Activa' AND especialidad_id=? ORDER BY nombre""", (especialidad_id,))
        else:
            c.execute("SELECT id, nombre FROM materias WHERE estado='Activa' ORDER BY nombre")
        for fila in c.fetchall():
            self.combo_filtro_vista_materia.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= self.combo_filtro_vista_materia.findData(actual)
        self.combo_filtro_vista_materia.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filtro_vista_materia.blockSignals(False)

    def _curso_filtro_vista_cambio(self):

        self._filtrar_secciones_vista_por_curso()
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    def _filtro_vista_cambio(self):

        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    #A diferencia del formulario 'Registrar evento' (donde Curso es
    #obligatorio antes que Sección), este filtro es 100% opcional: se
    #puede filtrar por Sección sin elegir Curso, o al revés. Si además hay
    #un Área Técnica/Carrera elegidos, la lista de secciones se acota más
    #-mismo criterio que _filtrar_secciones_evento_por_curso-.
    def _filtrar_secciones_vista_por_curso(self):

        cascada_seccion_por_curso(self.combo_filtro_vista_curso, self.combo_filtro_vista_seccion,
                                   incluir_todas= True)

        especialidad_id= (self.combo_filtro_vista_especialidad.currentData()
                            if self._es_politecnico() else None)
        carrera_id= self.combo_filtro_vista_carrera.currentData() if self._es_universidad() else None
        if especialidad_id is not None or carrera_id is not None:
            secciones_carrera= None
            if carrera_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                             WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
                secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
                conn.close()
            actual= self.combo_filtro_vista_seccion.currentData()
            for i in range(self.combo_filtro_vista_seccion.count() - 1, 0, -1):
                seccion_id= self.combo_filtro_vista_seccion.itemData(i)
                if seccion_id is None:
                    continue
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT especialidad_id FROM secciones WHERE id=?", (seccion_id,))
                fila_sec= c.fetchone()
                conn.close()
                especialidad_seccion= fila_sec["especialidad_id"] if fila_sec else None
                if especialidad_id is not None and especialidad_seccion != especialidad_id:
                    self.combo_filtro_vista_seccion.removeItem(i)
                    continue
                if secciones_carrera is not None and seccion_id not in secciones_carrera:
                    self.combo_filtro_vista_seccion.removeItem(i)
            idx= self.combo_filtro_vista_seccion.findData(actual)
            self.combo_filtro_vista_seccion.setCurrentIndex(idx if idx >= 0 else 0)

    #Consulta la base de datos una sola vez y a partir de ese resultado
    #actualiza el banner de próximo evento, la franja semanal y la tabla.
    #Cambiar de página o de filtro NO vuelve a consultar la base de datos:
    #solo re-filtra la lista ya cargada, para que la navegación sea fluida.
    def _cargar_datos(self):

        usuario_id= getattr(self.main_window, "id_usuario_actual", None)
        conn= obtener_conexion()
        c= conn.cursor()
        #Mismo patrón de JOIN que usa Observaciones para mostrar Curso/Sección (y aquí también Materia/Módulo)
        #directamente en la tabla.
        c.execute("""SELECT eventos.*,
                            grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                            materias.nombre as materia_nombre,
                            secciones.grado_id as grado_id, secciones.especialidad_id as especialidad_id
                     FROM eventos
                     LEFT JOIN secciones ON eventos.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN materias ON eventos.materia_id = materias.id
                     ORDER BY eventos.fecha, eventos.hora""")
        filas= c.fetchall()
        conn.close()
        visibles= []
        for fila in filas:
            if fila["visibilidad"] == "Personal" and fila["usuario_id"] != usuario_id:
                continue
            visibles.append(fila)
        self._eventos_todos= visibles
        total= len(visibles)
        self.chip_contador.setText(f"{total} evento{'s' if total!= 1 else ''}")
        self._actualizar_banner_proximo()
        self._actualizar_franja_semana()
        self._aplicar_filtros_y_tabla()

    def _filtro_busqueda_cambio(self):

        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    def _aplicar_filtros_y_tabla(self):

        termino= _normalizar(self.in_busqueda.text().strip()) if hasattr(self, "in_busqueda") else ""
        grado_id= self.combo_filtro_vista_curso.currentData() if hasattr(self, "combo_filtro_vista_curso") else None
        seccion_id= (self.combo_filtro_vista_seccion.currentData()
                      if hasattr(self, "combo_filtro_vista_seccion") else None)
        especialidad_id= (self.combo_filtro_vista_especialidad.currentData()
                            if hasattr(self, "combo_filtro_vista_especialidad") and self._es_politecnico() else None)
        carrera_id= (self.combo_filtro_vista_carrera.currentData()
                      if hasattr(self, "combo_filtro_vista_carrera") and self._es_universidad() else None)
        materia_id= (self.combo_filtro_vista_materia.currentData()
                      if hasattr(self, "combo_filtro_vista_materia") else None)

        secciones_carrera= None
        if carrera_id is not None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                         WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
            secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
            conn.close()

        filtrados= []
        for eventos_todo in self._eventos_todos:
            if self.filtro_tipo_actual and eventos_todo["tipo"] != self.filtro_tipo_actual:
                continue
            if self.filtro_fecha_actual and eventos_todo["fecha"] != self.filtro_fecha_actual:
                continue
            if grado_id is not None and eventos_todo["grado_id"] != grado_id:
                continue
            if seccion_id is not None and eventos_todo["seccion_id"] != seccion_id:
                continue
            if especialidad_id is not None and eventos_todo["especialidad_id"] != especialidad_id:
                continue
            if secciones_carrera is not None and eventos_todo["seccion_id"] not in secciones_carrera:
                continue
            if materia_id is not None and eventos_todo["materia_id"] != materia_id:
                continue
            if termino:
                texto_busqueda= _normalizar(
                    f"{eventos_todo['titulo'] or ''} {eventos_todo['tipo'] or ''} {eventos_todo['descripcion'] or ''}")
                if termino not in texto_busqueda:
                    continue
            filtrados.append(eventos_todo)
        self.paginacion.establecer_total(len(filtrados))
        inicio, fin= self.paginacion.rango_actual()
        self._poblar_tabla(filtrados[inicio:fin])

    def _poblar_tabla(self, pagina):

        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                tipo= f["tipo"] or "Personal"
                titulo_raw= f["titulo"] or ""

                self.tabla.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla.setItem(i, 1, QTableWidgetItem(formatear_fecha(f["fecha"], self.main_window) or ""))
                self.tabla.setItem(i, 2, QTableWidgetItem(self._formatear_hora(f["hora"]) or (f["hora"] or "")))

                item_titulo= QTableWidgetItem(titulo_raw)
                item_titulo.setData(Qt.ItemDataRole.UserRole, titulo_raw)
                self.tabla.setItem(i, 3, item_titulo)

                #Curso / Sección / Materia — solo aplican a eventos institucionales ligados a un grupo (los "Personal" no
                #llevan sección/materia).
                self.tabla.setItem(i, 4, QTableWidgetItem(f["grado_nombre"] or "—"))
                self.tabla.setItem(i, 5, QTableWidgetItem(f["seccion_nombre"] or "—"))
                self.tabla.setItem(i, 6, QTableWidgetItem(f["materia_nombre"] or "—"))

                #El texto del item se deja vacío a propósito: en QTableWidget el widget de celda (la "píldora" de color) NO
                #reemplaza la pintura del item subyacente, sino que se dibuja encima. Si el item tuviera texto, quedaría
                #visible detrás de la píldora, mezclado y encimado. El valor real del tipo queda disponible por
                #UserRole/tooltip para cualquier código (p. ej. el diálogo de detalle) que lo necesite.
                item_tipo= QTableWidgetItem("")
                item_tipo.setData(Qt.ItemDataRole.UserRole, tipo)
                item_tipo.setToolTip(tipo)
                self.tabla.setItem(i, 7, item_tipo)
                self.tabla.setCellWidget(i, 7, self._crear_pill_tipo(tipo))

                self.tabla.setItem(i, 8, QTableWidgetItem(f["descripcion"] or ""))
            ajustar_anchos_columnas(self.tabla)

    def _crear_pill_tipo(self, tipo):

        color= TIPO_COLORES.get(tipo, "#64748B")
        cont= QWidget()
        #Transparente a eventos de mouse: así el clic/doble clic sigue llegando a la tabla (selección de fila, detalle
        #con doble clic) en vez de quedar atrapado por este widget decorativo.
        cont.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        cont.setStyleSheet("background: transparent;")
        lay= QHBoxLayout(cont)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_pill= QLabel(tipo)
        lbl_pill.setStyleSheet(f"""
            background-color: {_hex_a_rgba(color, 0.16)};
            color: {color};
            border-radius: 9px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 12px;
        """)
        lay.addWidget(lbl_pill)
        return cont

    #Resumen dinámico: próximo evento + franja de la semana
    def _actualizar_banner_proximo(self):

        hoy= date.today()
        candidatos= []
        #f: evento del calendario; solo cuentan los de hoy en adelante
        for f in self._eventos_todos:
            fecha_ev= self._parsear_fecha(f["fecha"])
            if fecha_ev and fecha_ev >= hoy:
                candidatos.append((fecha_ev, f["hora"] or "", f))
        #t: (fecha, hora, evento); los más próximos primero
        candidatos.sort(key=lambda t: (t[0], t[1]))

        if not candidatos:
            self._pulso_proximo.poner_color("#94A3B8")
            self.lbl_proximo_eyebrow.setText("PRÓXIMO EVENTO")
            self.lbl_proximo_titulo.setText("No hay eventos próximos")
            self.lbl_proximo_fecha.setText("Agrega uno nuevo desde el formulario de abajo")
            self.lbl_proximo_cuenta.setVisible(False)
            self.lbl_proximo_cuenta.setText("")
        else:
            fecha_ev, _hora_orden, f= candidatos[0]
            tipo= f["tipo"] or "Personal"
            color_tipo= TIPO_COLORES.get(tipo, "#64748B")
            self._pulso_proximo.poner_color(color_tipo)
            self.lbl_proximo_eyebrow.setText(f"PRÓXIMO · {tipo.upper()}")
            self.lbl_proximo_titulo.setText(f["titulo"] or "(sin título)")
            hora_legible= self._formatear_hora(f["hora"])
            fecha_legible= self._formatear_fecha_larga(fecha_ev)
            texto_fecha= fecha_legible + (f" · {hora_legible}" if hora_legible else "")
            self.lbl_proximo_fecha.setText(texto_fecha)
            self.lbl_proximo_cuenta.setVisible(True)
            self.lbl_proximo_cuenta.setText(self._texto_cuenta_regresiva(fecha_ev))
            self.lbl_proximo_cuenta.setStyleSheet(f"""
                background-color: {_hex_a_rgba(color_tipo, 0.16)};
                color: {color_tipo};
                font-weight: 800;
                font-size: 13px;
                padding: 6px 14px;
                border-radius: 12px;
            """)
        self._colorear_textos_proximo()

    def _colorear_textos_proximo(self):

        c= self._colores_tema()
        self.lbl_proximo_eyebrow.setStyleSheet(
            f"font-size: 11px; font-weight: 800; letter-spacing: 1px; "
            f"color: {c['txt_sec']}; background: transparent;")
        self.lbl_proximo_fecha.setStyleSheet(
            f"font-size: 13px; color: {c['txt_sec']}; background: transparent;")

    def _actualizar_franja_semana(self):

        eventos_por_dia= {}
        for eventos_todo in self._eventos_todos:
            fecha_ev= self._parsear_fecha(eventos_todo["fecha"])
            if fecha_ev:
                eventos_por_dia.setdefault(fecha_ev, []).append(eventos_todo["tipo"] or "Personal")
        for chip in self.chips_semana:
            chip.poner_eventos(eventos_por_dia.get(chip.fecha, []))
            chip.seleccionado= (chip.fecha_iso == self.filtro_fecha_actual)
        self._aplicar_estilos_semana()

    def _aplicar_estilos_semana(self):

        c= self._colores_tema()
        hoy= date.today()
        for chip in self.chips_semana:
            chip.poner_hoy(chip.fecha == hoy)
            chip.aplicar_estilo(c["bg_panel"], c["bg_btn"], c["txt_prim"], c["txt_sec"],
                                 c["accent"], chip.fecha == hoy)

    def _al_click_dia(self, fecha_iso):

        self.filtro_fecha_actual= None if self.filtro_fecha_actual == fecha_iso else fecha_iso
        for chip in self.chips_semana:
            chip.seleccionado= (chip.fecha_iso == self.filtro_fecha_actual)
        self._aplicar_estilos_semana()
        self._actualizar_indicador_filtro_fecha()
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    def _limpiar_filtro_fecha(self):

        self.filtro_fecha_actual= None
        for chip in self.chips_semana:
            chip.seleccionado= False
        self._aplicar_estilos_semana()
        self._actualizar_indicador_filtro_fecha()
        self.paginacion.reiniciar()
        self._aplicar_filtros_y_tabla()

    def _actualizar_indicador_filtro_fecha(self):

        if self.filtro_fecha_actual:
            fecha_obj= self._parsear_fecha(self.filtro_fecha_actual)
            texto= self._formatear_fecha_larga(fecha_obj) if fecha_obj else self.filtro_fecha_actual
            self.lbl_filtro_fecha.setText(f"Mostrando solo: {texto}")
            _fundido(self.fila_filtro_fecha, True)
        else:
            _fundido(self.fila_filtro_fecha, False)

    #Formato de fechas / HORAS (texto en español, sin depender del locale)
    def _parsear_fecha(self, fecha_str):

        if not fecha_str:
            return None
        try:

            return datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _formatear_fecha_larga(self, fecha_obj):

        dia_semana= DIAS_SEMANA[fecha_obj.weekday()]
        mes= MESES[fecha_obj.month - 1]
        return f"{dia_semana} {fecha_obj.day} de {mes}"

    def _formatear_hora(self, hora_str):

        #Respeta el formato de hora elegido en Configuración › Apariencia (24h o 12h); el dato sigue guardándose
        #siempre en 24h.
        return formatear_hora(hora_str, self.main_window)

    def _texto_cuenta_regresiva(self, fecha_evento):

        delta= (fecha_evento - date.today()).days
        if delta == 0:
            return "Hoy"
        if delta == 1:
            return "Mañana"
        if delta > 1:
            return f"En {delta} días"
        return "Hoy"

    #TEMA / paleta de colores
    def _colores_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None) or {}
        paleta= paletas.get(getattr(mw, "tema_actual", None))
        if not paleta and paletas:
            paleta= next(iter(paletas.values()))
        if not paleta:
            #Valores de respaldo razonables si el tema aún no está disponible.
            paleta= {
                "display_bg": ("#FFFFFF", "#1E293B"),
                "btn_num_bg": ("#E2E8F0", "#334155"),
                "text_primary": ("#0F172A", "#F8FAFC"),
                "text_secondary": ("#64748B", "#94A3B8"),
                "btn_op_bg": ("#2563EB", "#3B82F6"),
                "btn_op_hover": ("#1D4ED8", "#2563EB"),
            }
        idx= 1 if getattr(mw, "modo_oscuro", False) else 0
        return {
            "bg_panel": paleta.get("display_bg", ("#FFFFFF", "#1E293B"))[idx],
            "bg_btn": paleta.get("btn_num_bg", ("#E2E8F0", "#334155"))[idx],
            "txt_prim": paleta.get("text_primary", ("#0F172A", "#F8FAFC"))[idx],
            "txt_sec": paleta.get("text_secondary", ("#64748B", "#94A3B8"))[idx],
            "accent": paleta.get("btn_op_bg", ("#2563EB", "#3B82F6"))[idx],
            "accent_hv": paleta.get("btn_op_hover", paleta.get("btn_op_bg", ("#1D4ED8", "#2563EB")))[idx],
        }

    def actualizar_tema(self):

        c= self._colores_tema()
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {c['bg_panel']};
                color: {c['txt_prim']};
                border: 1px solid {c['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        if hasattr(self, "frame_cabecera"):
            self.frame_cabecera.setStyleSheet(f"""
                QFrame#TarjetaCabecera {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {c['accent']}, stop:1 {c['accent_hv']});
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
                QLabel#ChipContador {{
                    background-color: rgba(255, 255, 255, 40);
                    color: white;
                    border-radius: 14px;
                    padding: 7px 16px;
                    font-weight: 700;
                    font-size: 12px;
                }}
            """)
        if hasattr(self, "icono_busqueda"):
            self.icono_busqueda.establecer_color(c["txt_sec"])
        if hasattr(self, "panel_proximo"):
            self.panel_proximo.aplicar_colores(c["bg_panel"], c["bg_btn"])
        if hasattr(self, "panel_semana"):
            self.panel_semana.aplicar_colores(c["bg_panel"], c["bg_btn"])
        if hasattr(self, "panel_formulario"):
            self.panel_formulario.aplicar_colores(c["bg_panel"], c["bg_btn"])
        if hasattr(self, "lbl_filtro_fecha"):
            self.lbl_filtro_fecha.setStyleSheet(f"""
                background-color: {_hex_a_rgba(c['accent'], 0.12)};
                color: {c['accent']};
                font-weight: 600;
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 10px;
            """)
        if hasattr(self, "btn_limpiar_filtro_fecha"):
            self.btn_limpiar_filtro_fecha.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {c['txt_sec']};
                    border: none;
                    font-weight: 700;
                    font-size: 13px;
                    padding: 2px 6px;
                }}
                QPushButton:hover {{ color: {c['accent']}; }}
            """)
        if hasattr(self, "_eventos_todos"):
            self._colorear_textos_proximo()
        if hasattr(self, "chips_semana"):
            self._aplicar_estilos_semana()
        if hasattr(self, "chips_filtro"):
            self._restilizar_chips_filtro()
        if hasattr(self, "lbl_estado_form"):
            self._actualizar_estado_form(self.id_edicion is not None, self.in_titulo.text())
        if hasattr(self, "dialogo_filtros_vista"):
            self.dialogo_filtros_vista.setStyleSheet(f"""
                QDialog#DialogoFiltros {{
                    background-color: {c['bg_panel']};
                }}
                /* Repite aqui el mismo QToolTip que usa la ventana
                   principal: este dialogo es una ventana de nivel
                   superior aparte, y su propio setStyleSheet()
                   reemplaza -para todo lo que este dentro- cualquier
                   regla heredada, incluido el QToolTip global. Sin
                   esto, los tooltips de los combos aqui adentro
                   caian al estilo nativo de Qt (gris claro/texto
                   negro), inconsistente con el resto de AcaDeXI. */
                QToolTip {{
                    background-color: {c['bg_panel']};
                    color: {c['txt_prim']};
                    border: 1px solid {c['bg_btn']};
                    padding: 6px 10px;
                    border-radius: 6px;
                }}
                QLabel#IconoEncabezadoFiltros {{
                    background-color: {c['accent']};
                    color: white;
                    border-radius: 15px;
                    min-width: 30px; max-width: 30px;
                    min-height: 30px; max-height: 30px;
                    font-size: 14px;
                    qproperty-alignment: AlignCenter;
                }}
                QLabel#TituloEncabezadoFiltros {{
                    font-size: 16px;
                    font-weight: 800;
                    color: {c['txt_prim']};
                    background: transparent;
                }}
                QLabel#SubtituloFiltros {{
                    font-size: 11.5px;
                    color: {c['txt_sec']};
                    background: transparent;
                }}
                QFrame#SeparadorFiltros {{
                    background-color: {c['bg_btn']};
                    max-height: 1px;
                    border: none;
                }}
                QLabel {{
                    color: {c['txt_prim']};
                    font-weight: 700;
                    font-size: 12.5px;
                    background: transparent;
                }}
            """)

    #ACCIONES: guardar / cargar / eliminar
    def _guardar(self):

        if not self.in_titulo.text().strip():
            self.toast.mostrar("El título del evento es obligatorio.", "advertencia")
            _glow_invalido(self.in_titulo)
            return
        tipo= self.combo_tipo.currentText()
        visibilidad= "Personal" if tipo == "Personal" else "Institucional"
        usuario_id= getattr(self.main_window, "id_usuario_actual", None)
        if self.id_edicion is not None and not self.gerencial:
            if not self._es_evento_propio(self.id_edicion):
                self.toast.mostrar("Solo puedes editar tus propios eventos personales.", "advertencia")
                return
        datos= (self.in_titulo.text().strip(), self.in_desc.toPlainText().strip(), tipo,
                 self.date_fecha.date().toString("yyyy-MM-dd"), self.in_time_hora.time().toString("HH:mm"),
                 self.combo_seccion.currentData(), self.combo_materia.currentData(), usuario_id, visibilidad)
        conn= obtener_conexion()
        c= conn.cursor()
        if self.id_edicion is None:
            c.execute("""INSERT INTO eventos (titulo, descripcion, tipo, fecha, hora, seccion_id,
                         materia_id, usuario_id, visibilidad) VALUES (?,?,?,?,?,?,?,?,?)""", datos)
            accion= "Creó evento en Calendario"
            mensaje_toast= "Evento creado correctamente."
        else:
            c.execute("""UPDATE eventos SET titulo=?, descripcion=?, tipo=?, fecha=?, hora=?,
                         seccion_id= ?, materia_id=?, usuario_id=?, visibilidad=? WHERE id=?""",
                      datos + (self.id_edicion,))
            accion= "Editó evento en Calendario"
            mensaje_toast= "Evento actualizado correctamente."
            #Re-arma su alarma: al cambiar fecha/hora debe volver a sonar en el nuevo momento (borra las marcas de "ya
            #disparada").
            try:

                from src.servicios.alarmas import rearmar_alarmas_evento
                rearmar_alarmas_evento(self.id_edicion)
            except Exception:
                pass
        conn.commit()
        conn.close()
        registrar_auditoria("Calendario", accion, self.main_window.usuario_actual, self.in_titulo.text().strip())
        self.toast.mostrar(mensaje_toast, "exito")
        self._limpiar()
        self._cargar_datos()

    def _es_evento_propio(self, id_evento):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT usuario_id, visibilidad FROM eventos WHERE id=?", (id_evento,))
        fila= c.fetchone()
        conn.close()
        if not fila:
            return False
        return fila["visibilidad"] == "Personal" and fila["usuario_id"] == getattr(self.main_window, "id_usuario_actual", None)

    def _actualizar_estado_form(self, editando, titulo=""):

        if editando:
            texto= (titulo or "").strip() or "evento"
            if len(texto) > 28:
                texto= texto[:27].rstrip() + "…"
            self.lbl_estado_form.setText(f"Editando: {texto}")
            self.lbl_estado_form.setStyleSheet(
                "font-size: 12px; font-weight: 800; color: #F59E0B; background: transparent;")
            self.btn_guardar.setText("Guardar cambios")
            self.btn_limpiar.setText("Cancelar edición")
        else:
            self.lbl_estado_form.setText("Nuevo evento")
            c= self._colores_tema()
            self.lbl_estado_form.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {c['txt_sec']}; background: transparent;")
            self.btn_guardar.setText("Guardar Evento")
            self.btn_limpiar.setText("Limpiar")

    def _limpiar(self):

        self.id_edicion= None
        self.in_titulo.clear()
        self.in_desc.clear()
        self.combo_tipo.setCurrentIndex(0)
        self.date_fecha.setDate(QDate.currentDate())
        self.in_time_hora.setTime(QTime(8, 0))
        if hasattr(self, "combo_filtro_especialidad_evento"):
            self.combo_filtro_especialidad_evento.setCurrentIndex(0)
        if hasattr(self, "combo_filtro_carrera_evento"):
            self.combo_filtro_carrera_evento.setCurrentIndex(0)
        self._cargar_combos()
        self._actualizar_estado_form(False)
        desactivar_modo_edicion(self.in_titulo)

    def _cargar_seleccionado(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            self.toast.mostrar("Selecciona un evento de la tabla.", "advertencia")
            return
        item_id= self.tabla.item(fila, 0)
        if item_id is None:
            return
        id_ev= int(item_id.text())
        if not self.gerencial and not self._es_evento_propio(id_ev):
            self.toast.mostrar("Solo puedes editar tus propios eventos personales.", "advertencia")
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM eventos WHERE id=?", (id_ev,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            self.toast.mostrar("El evento ya no existe.", "error")
            return
        self.id_edicion= f["id"]
        self.panel_registro.expandir(True, animar=False)  #de golpe al editar
        self.in_titulo.setText(f["titulo"] or "")
        self.in_desc.setPlainText(f["descripcion"] or "")
        idx= self.combo_tipo.findText(f["tipo"] or "")
        self.combo_tipo.setCurrentIndex(idx if idx >= 0 else 0)
        self.date_fecha.setDate(QDate.fromString(f["fecha"], "yyyy-MM-dd"))
        if f["hora"]:
            self.in_time_hora.setTime(QTime.fromString(f["hora"], "HH:mm"))
        self._cargar_combos()
        preseleccionar_curso_y_seccion(self.combo_curso, self.combo_seccion, f["seccion_id"],
                                        incluir_todas= False)
        idx_m= self.combo_materia.findData(f["materia_id"])
        self.combo_materia.setCurrentIndex(idx_m if idx_m >= 0 else 0)
        self._actualizar_estado_form(True, f["titulo"] or "")
        activar_modo_edicion(self.in_titulo, f"Editando evento: {f['titulo'] or ''}")

    def _eliminar(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            self.toast.mostrar("Selecciona un evento de la tabla.", "advertencia")
            return
        item_id= self.tabla.item(fila, 0)
        if item_id is None:
            return
        id_ev= int(item_id.text())
        if not self.gerencial and not self._es_evento_propio(id_ev):
            self.toast.mostrar("Solo puedes eliminar tus propios eventos personales.", "advertencia")
            return
        item_titulo= self.tabla.item(fila, 3)
        titulo= (item_titulo.data(Qt.ItemDataRole.UserRole) if item_titulo else "") or\
                 (item_titulo.text() if item_titulo else "")
        if mostrar_mensaje("pregunta", "Confirmar", f"¿Eliminar el evento '{titulo}'?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM eventos WHERE id=?", (id_ev,))
        conn.commit()
        conn.close()
        #Limpia también las marcas de alarma de este evento.
        try:

            from src.servicios.alarmas import rearmar_alarmas_evento
            rearmar_alarmas_evento(id_ev)
        except Exception:
            pass
        registrar_auditoria("Calendario", "Eliminó evento", self.main_window.usuario_actual, titulo)
        self.toast.mostrar("Evento eliminado.", "exito")
        self._cargar_datos()

    #Puntos de entrada llamados desde main.py
    def refrescar(self):

        self._cargar_combos()
        self._cargar_datos()
