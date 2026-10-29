#Módulo Psicología de AcaDeXI.
#
#Módulo EXCLUSIVO de la edición Side Stepper: solo un cargo personalizado al
#que se le otorgó el módulo "Psicología" (ver
#permisos.MODULOS_EXTRA_SIDE_STEPPER, permisos.guardar_permisos_side_stepper)
#puede acceder, además de los roles gerenciales (Administrador/Director/
#Coordinador) para supervisión institucional -ver permisos.puede_ver_psicologia.
#Ningún Profesor, Administrativo ni el rol fijo "Profesor" de Side Stepper
#puede verlo, aunque sí vean Observaciones.
#
#Deliberadamente COPIA el patrón de interacción de observaciones.py
#(naturaleza + categorías + texto libre + destacada, filtros por
#Curso/Sección, banner de edición, paginación), porque para quien usa la
#app se siente como "la Observaciones del psicólogo" -pero los datos NUNCA
#se mezclan: viven en su propia tabla `psicologia` (ver bd.inicializar_bd),
#así que un cambio en Observaciones (o un export/import entre ediciones)
#jamás toca, expone ni sobrescribe un registro de Psicología por accidente.
#
#Campos propios que Observaciones no tiene:
#- confidencial: siempre 1 (de momento no hay UI que lo desactive; se deja
#la columna para un futuro "resumen no confidencial" opcional).
#- estado_caso: Abierto / En seguimiento / Cerrado / Derivado — para que el
#psicólogo lleve el expediente de un caso a través del tiempo, no solo
#una bitácora de eventos sueltos como Observaciones.
#- proxima_cita: fecha opcional de seguimiento, se resalta en la tabla si
#ya venció y el caso sigue abierto.
#
# -----------------------------------------
# rediseño visual (v2)
# -----------------------------------------
#mismo lenguaje visual que el resto de la app
#Este módulo vivía con una pantalla "de solo funcionalidad" (formulario
#plano siempre visible, tarjetas sin colores de tema, sin cabecera tipo
#héroe) mientras el resto de AcaDeXI (Profesores, Estudiantes, Materias,
#Observaciones...) ya usa un lenguaje visual consistente. Este archivo
#alinea Psicología a ese mismo lenguaje, reutilizando exactamente los
#mismos nombres de objeto/QSS que ya pinta el tema activo de la app
#(TarjetaCabecera, TarjetaFiltros, TarjetaTabla, BtnAccionAgregar/Editar/
#Eliminar/Neutro) y el mismo componente de tarjetas KPI que ya usa
#Materias (`dashboard.TarjetaIndicador`), en vez de inventar un estilo
#nuevo. Como cada módulo de AcaDeXI mantiene su propia copia pequeña de
#los widgets puramente visuales (ver el mismo criterio documentado en
#observaciones.py/profesores.py: "en vez de importar entre módulos de
#funcionalidad"), este archivo trae sus propias copias de `BotonAnimado`,
#`IconoLupa`, `Chip`, `FlowLayout`, `SegmentadoPildora` y `CintaAlerta`.
#
#Además de la piel visual, se suman mejoras de experiencia que faltaban:
#- `actualizar_tema()`: antes NO EXISTÍA -el módulo nunca se repintaba al
#cambiar de tema/modo oscuro (main.py llama a este método en cada
#página que lo define; sin él, Psicología se quedaba con los colores
#del arranque)-. Ahora sí, igual que todos los demás módulos.
#- Panel de alta/edición COLAPSABLE (antes un `QFrame.show()/hide()` sin
#animar): se integra con `edicion_feedback.activar_modo_edicion`, que
#ya sabe expandir automáticamente cualquier panel ancestro con
#`expandir()`/`_expandido` al editar un registro -exactamente el mismo
#mecanismo que usan Observaciones y otros módulos-.
#- Fila de indicadores (Total, Abiertos, En seguimiento, Citas vencidas)
#para que el psicólogo vea la carga de casos de un vistazo, sin tener
#que filtrar manualmente.
#- Cinta de alerta cuando hay citas de seguimiento vencidas, con acceso
#directo a filtrarlas.
#- Chips rápidos "Destacados"/"Vencidas" además del combo de estado.
#- Deshacer la última eliminación (dato sensible: un borrado accidental
#de una nota confidencial no debería ser irreversible sin más).
#- Atajos de teclado (Ctrl+G/N/E/Del/Z), igual que Profesores/Estudiantes.
#- Búsqueda con debounce (150 ms) en vez de refrescar en cada tecla.
#No se tocó ningún dato, columna, permiso ni consulta de negocio: todo lo
#anterior es estrictamente presentación/experiencia.
from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTextEdit, QFrame, QDateEdit, QCheckBox, QScrollArea, QLayout, QDialog, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QMenu,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QMessageBox,
)
from PySide6.QtCore import (
    Qt, QTimer, QDate, QRect, QRectF, QPoint, QPointF, QSize, Signal,
    QPropertyAnimation, QEasingCurve, QVariantAnimation, QParallelAnimationGroup,
)
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QIcon, QPixmap, QAction

from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.filtros_curso_seccion import poblar_combo_curso, cascada_seccion_por_curso
from src.modulos.calendario import PanelDesplegable
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                        tabla_pausada, mostrar_texto_largo, mostrar_detalle_campos,
                        agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import formatear_fecha
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.nucleo.atajos import registrar_atajo
from src.interfaz.dashboard import TarjetaIndicador
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro
from src.nucleo.permisos import puede_ver_psicologia, tiene_acceso_gerencial


#Catálogo propio de psicología (deliberadamente distinto del de Observaciones: aquí el vocabulario es
#clínico/orientador, no académico)
NATURALEZAS= [("Positiva", "#10B981"), ("Informativa", "#64748B"), ("Negativa", "#EF4444")]
_COLOR_NATURALEZA= {clave: color for clave, color in NATURALEZAS}

CATEGORIAS= [
    ("evaluacion", "Evaluación psicológica"),
    ("terapia_individual", "Terapia individual"),
    ("terapia_familiar", "Terapia familiar / orientación a padres"),
    ("conducta", "Manejo de conducta"),
    ("emocional", "Apoyo emocional"),
    ("aprendizaje", "Dificultades de aprendizaje"),
    ("crisis", "Intervención en crisis"),
    ("derivacion", "Derivación externa"),
    ("seguimiento", "Seguimiento de caso"),
    ("mediacion", "Mediación de conflicto"),
]
ETIQUETA_CATEGORIA= {clave: etiqueta for clave, etiqueta in CATEGORIAS}

#Color de acento por categoría -mismo espíritu que observaciones.py:
#tonos cálidos/rojizos para lo urgente, fríos/neutros para lo rutinario.
COLOR_CATEGORIA= {
    "evaluacion": "#3B82F6",
    "terapia_individual": "#8B5CF6",
    "terapia_familiar": "#EC4899",
    "conducta": "#F59E0B",
    "emocional": "#14B8A6",
    "aprendizaje": "#0EA5E9",
    "crisis": "#EF4444",
    "derivacion": "#6366F1",
    "seguimiento": "#64748B",
    "mediacion": "#22C55E",
}

ESTADOS_CASO= ["Abierto", "En seguimiento", "Cerrado", "Derivado"]
COLOR_ESTADO_CASO= {
    "Abierto": "#3B82F6", "En seguimiento": "#F59E0B", "Cerrado": "#10B981", "Derivado": "#8B5CF6",
}

_OPCIONES_NATURALEZA= [(clave, clave, color) for clave, color in NATURALEZAS]
_OPCIONES_ESTADO= [(estado, estado, COLOR_ESTADO_CASO[estado]) for estado in ESTADOS_CASO]

_DIAS_SEMANA= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

HEADERS_TABLA= ["", "Fecha", "Estudiante", "Curso", "Naturaleza", "Categorías", "Estado del caso", "Próxima cita"]
COL_DESTACADA= 0
COL_FECHA= 1
COL_ESTUDIANTE= 2
COL_SECCION= 3
COL_NATURALEZA= 4
COL_CATEGORIAS= 5
COL_ESTADO= 6
COL_PROXIMA= 7


def _texto_categorias(claves_csv):

    claves= [c for c in (claves_csv or "").split(",") if c]
    return ", ".join(ETIQUETA_CATEGORIA.get(c, c) for c in claves) if claves else "—"


#'Hoy' / 'Ayer' / día de la semana (última semana) / fecha completa en
#el formato elegido en Configuración ▸ Apariencia -para el resto de
#casos-. Variante de un solo día (sin hora) de la misma idea que usa
#observaciones.py, porque aquí `fecha` se guarda como YYYY-MM-DD, sin
#componente de hora.
def _fecha_relativa_dia(fecha_str, main_window=None):

    try:

        d= datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return fecha_str or "—"
    hoy= date.today()
    if d == hoy:
        return "Hoy"
    if d == hoy - timedelta(days=1):
        return "Ayer"
    if 0 < (hoy - d).days < 7:
        return _DIAS_SEMANA[d.weekday()]
    return formatear_fecha(fecha_str, main_window)


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica. Copia local propia de este módulo (mismo
#criterio que estudiantes.py / profesores.py / observaciones.py: cada módulo mantiene la suya en vez de
#importar entre módulos de funcionalidad).
def _hex_a_rgba(color_hex, alpha):

    color_hex= (color_hex or "#2563EB").lstrip("#")
    if len(color_hex) < 6:
        color_hex= "2563EB"
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Igual que `_hex_a_rgba` pero como QColor real, para
#QTableWidgetItem.setBackground (tiñe cada fila con el color de su
#estado del caso, ver `_cargar_tabla`).
def _color_fila_qcolor(color_hex, alpha_255):

    color_hex= (color_hex or "#64748B").lstrip("#")
    if len(color_hex) < 6:
        color_hex= "64748B"
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return QColor(r, g, b, alpha_255)


#Arma el texto de la columna 'Curso' (antes 'Sección'): grado + sección
#del estudiante, y si aplica -Politécnico/Universidad-, también su área
#técnica o carrera. Requiere que la fila `f` venga de una consulta con
#los alias grado_nombre/seccion_nombre/area_nombre/carrera_nombre (ver
#los JOIN en `_cargar_tabla` y `_ver_detalle`).
def _texto_curso_completo(f):

    if f["grado_nombre"]:
        base= f["grado_nombre"]
        if f["seccion_nombre"]:
            base += f" - {f['seccion_nombre']}"
    else:
        base= "—"
    extra= f["area_nombre"] or f["carrera_nombre"]
    return f"{base} · {extra}" if extra else base


#Lee la paleta/tema activo de la ventana principal para que las tarjetas de
#este módulo respeten el tema y el modo claro/oscuro que el usuario ya eligió.
def _colores_tema(main_window):

    try:

        paleta= main_window.theme_palettes[main_window.tema_actual]
        modo_oscuro= bool(getattr(main_window, "modo_oscuro", False))
        idx= 1 if modo_oscuro else 0
        bg_btn= paleta["btn_num_bg"][idx]
        return {
            "bg_panel": paleta["display_bg"][idx],
            "bg_btn": bg_btn,
            #"Riel" de los segmentados y fondo de los chips: en modo claro -de CUALQUIER tema, no solo Colorful- va blanco
            #en vez del gris neutro que usan los botones normales; el borde (que sigue usando bg_btn) ya alcanza para
            #distinguirlo del fondo de la tarjeta. En modo oscuro se deja el gris de siempre, porque ahí blanco puro no
            #combina con el resto de la paleta oscura.
            "bg_track": paleta["display_bg"][idx] if not modo_oscuro else bg_btn,
            "txt_prim": paleta["text_primary"][idx],
            "txt_sec": paleta["text_secondary"][idx],
            "accent": paleta["btn_op_bg"][idx],
            "accent_hv": paleta["btn_op_hover"][idx],
        }
    except Exception:
        return {"bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0", "bg_track": "#FFFFFF", "txt_prim": "#0F172A",
                "txt_sec": "#64748B", "accent": "#2563EB", "accent_hv": "#1D4ED8"}


_cache_punto= {}


#Pequeño círculo sólido de `color_hex` (cacheado), usado como icono de
#identidad de color en los segmentados y como icono de los botones —
#versión self-contained, sin depender de iconos_categorias.py (ese
#archivo está pensado para las categorías propias de Observaciones).
def _pixmap_punto(color_hex, size=10):

    llave= (color_hex, size)
    pix= _cache_punto.get(llave)
    if pix is not None:
        return pix
    pix= QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(pix)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(color_hex))
    pintor.drawEllipse(0, 0, size, size)
    pintor.end()
    _cache_punto[llave]= pix
    return pix


#Fila de punto de color + etiqueta -una por categoría- para la
#columna "Categorías" de la tabla (una fila puede tener varias a la
#vez; un QTableWidgetItem solo admite un icono, por eso va como
#cellWidget, igual que observaciones.py).
def _widget_categorias_fila(categorias_csv, color_texto="#64748B"):

    claves= [c for c in (categorias_csv or "").split(",") if c]
    if not claves:
        lbl= QLabel("—")
        lbl.setStyleSheet(f"color: {color_texto}; background: transparent;")
        return lbl

    contenedor= QWidget()
    lay= QHBoxLayout(contenedor)
    lay.setContentsMargins(2, 0, 2, 0)
    lay.setSpacing(10)
    nombres= []
    for clave in claves:
        etiqueta= ETIQUETA_CATEGORIA.get(clave)
        if not etiqueta:
            continue
        color= COLOR_CATEGORIA.get(clave, "#64748B")
        grupo= QWidget()
        lay_g= QHBoxLayout(grupo)
        lay_g.setContentsMargins(0, 0, 0, 0)
        lay_g.setSpacing(5)
        lbl_punto= QLabel()
        lbl_punto.setFixedSize(9, 9)
        lbl_punto.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        lay_g.addWidget(lbl_punto)
        lbl_txt= QLabel()
        lbl_txt.setStyleSheet(f"color: {color_texto}; font-size: 11px; background: transparent;")
        lbl_txt.setMaximumWidth(150)
        lbl_txt.setText(lbl_txt.fontMetrics().elidedText(etiqueta, Qt.TextElideMode.ElideRight, 150))
        lay_g.addWidget(lbl_txt)
        grupo.setToolTip(etiqueta)
        lay.addWidget(grupo)
        nombres.append(etiqueta)
    lay.addStretch()
    contenedor.setToolTip(" · ".join(nombres))
    return contenedor


#Layout de flujo — envuelve los chips de categoría a la siguiente línea según el ancho disponible (para que la
#tarjeta se adapte a ventanas angostas en vez de recortar categorías). Copia local, ver nota de módulo más
#arriba.
class FlowLayout(QLayout):

    def __init__(self, parent=None, margin=0, spacing=8):

        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items= []

    def addItem(self, item):

        self._items.append(item)

    def count(self):

        return len(self._items)

    def itemAt(self, indice):

        return self._items[indice] if 0 <= indice < len(self._items) else None

    def takeAt(self, indice):

        return self._items.pop(indice) if 0 <= indice < len(self._items) else None

    def expandingDirections(self):

        return Qt.Orientation(0)

    def hasHeightForWidth(self):

        return True

    def heightForWidth(self, width):

        return self._hacer_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):

        super().setGeometry(rect)
        self._hacer_layout(rect, False)

    def sizeHint(self):

        return self.minimumSize()

    def minimumSize(self):

        tam= QSize()
        for item in self._items:
            tam= tam.expandedTo(item.minimumSize())
        m= self.contentsMargins()
        tam += QSize(m.left() + m.right(), m.top() + m.bottom())
        return tam

    def _hacer_layout(self, rect, solo_calcular):

        x, y= rect.x(), rect.y()
        alto_linea= 0
        espacio= self.spacing()
        for item in self._items:
            ancho_item= item.sizeHint().width()
            siguiente_x= x + ancho_item + espacio
            if siguiente_x - espacio > rect.right() and alto_linea > 0:
                x= rect.x()
                y= y + alto_linea + espacio
                siguiente_x= x + ancho_item + espacio
                alto_linea= 0
            if not solo_calcular:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x= siguiente_x
            alto_linea= max(alto_linea, item.sizeHint().height())
        return y + alto_linea - rect.y()


#Widgets visuales
#Icono de lupa dibujado a mano (mismo diseño que el resto de barras
#de búsqueda de AcaDeXI: horario.py, estudiantes.py, profesores.py).
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


#QPushButton normal (mismo objectName/estilo por QSS/tema) que además
#'respira' con una sombra suave al pasar el mouse por encima. Solo anima
#mientras el cursor está sobre el botón, así que no cuesta rendimiento
#en reposo.
class BotonAnimado(QPushButton):

    def __init__(self, texto="", parent=None):

        super().__init__(texto, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setColor(QColor(0, 0, 0, 70))
        self._sombra.setOffset(0, 3)
        self._sombra.setBlurRadius(0)
        self.setGraphicsEffect(self._sombra)
        self._anim= QPropertyAnimation(self._sombra, b"blurRadius", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animar_sombra(self, hasta):

        self._anim.stop()
        self._anim.setStartValue(self._sombra.blurRadius())
        self._anim.setEndValue(hasta)
        self._anim.start()

    def enterEvent(self, evento):

        if self.isEnabled():
            self._animar_sombra(18)
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._animar_sombra(0)
        super().leaveEvent(evento)


#Pastilla seleccionable con transición de color animada y una onda
#('ripple') pintada a mano al pulsar. Se usa para categorías y para los
#filtros rápidos (Destacados/Vencidas). Cada chip lleva un punto de
#color FIJO (su identidad), y el fondo de la pastilla se anima entre
#'apagado' (gris translúcido) y 'encendido' (su color) al marcarse.
class Chip(QFrame):

    alternado= Signal(bool)

    def __init__(self, clave, texto, color_activo="#6366F1", parent=None):

        super().__init__(parent)
        self.clave= clave
        self._texto_base= texto
        self._marcado= False
        self._hover= False
        self._factor= 0.0  #0 = inactivo, 1 = activo (interpolación de color)
        self._color_activo= QColor(color_activo)
        self._color_inactivo_bg= QColor(127, 127, 127, 26)
        self._color_borde_inactivo= QColor(127, 127, 127, 70)
        self._color_texto_inactivo= QColor("#64748B")
        self._ripples= []

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        lay= QHBoxLayout(self)
        lay.setContentsMargins(14, 7, 15, 7)
        lay.setSpacing(8)
        self.lbl_punto= QLabel()
        self.lbl_punto.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_punto.setFixedSize(10, 10)
        self.lbl_punto.setPixmap(_pixmap_punto(color_activo, 10))
        lay.addWidget(self.lbl_punto)
        self.lbl= QLabel()
        self.lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        fuente= self.lbl.font()
        fuente.setPointSize(10)
        fuente.setBold(True)
        self.lbl.setFont(fuente)
        lay.addWidget(self.lbl)
        self._actualizar_texto()

        self._anim= QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)
        self._actualizar_estilo()

    def _al_animar(self, valor):

        self._factor= valor
        self._actualizar_estilo()

    def esta_marcado(self):

        return self._marcado

    def establecer_marcado(self, marcado, animar=True, emitir=True):

        if marcado == self._marcado:
            return
        self._marcado= marcado
        if animar:
            self._anim.stop()
            self._anim.setStartValue(self._factor)
            self._anim.setEndValue(1.0 if marcado else 0.0)
            self._anim.start()
        else:
            self._factor= 1.0 if marcado else 0.0
            self._actualizar_estilo()
        if emitir:
            self.alternado.emit(marcado)

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            self._agregar_ripple(evento.position())
            self.establecer_marcado(not self._marcado)
        super().mousePressEvent(evento)

    def enterEvent(self, evento):

        self._hover= True
        self.update()
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._hover= False
        self.update()
        super().leaveEvent(evento)

    def _agregar_ripple(self, punto):

        anim= QVariantAnimation(self)
        anim.setDuration(420)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        entrada= [QPointF(punto), anim]
        self._ripples.append(entrada)
        anim.valueChanged.connect(self.update)

        def _terminar():

            if entrada in self._ripples:
                self._ripples.remove(entrada)
            self.update()
        anim.finished.connect(_terminar)
        anim.start()

    def _color_mezclado(self):

        base= self._color_inactivo_bg
        if self._hover and not self._marcado:
            base= QColor(base)
            base.setAlpha(min(255, base.alpha() + 34))
        t= self._factor
        #r: rojo interpolado entre el color base y el activo según t (0 a 1)
        r= base.red() + (self._color_activo.red() - base.red()) * t
        g= base.green() + (self._color_activo.green() - base.green()) * t
        b= base.blue() + (self._color_activo.blue() - base.blue()) * t
        #a: transparencia interpolada entre la base y opaco (255) según t (0 a 1)
        a= base.alpha() + (255 - base.alpha()) * t
        return QColor(int(r), int(g), int(b), int(a))

    def establecer_paleta(self, bg_inactivo, borde_inactivo, texto_inactivo):

        self._color_inactivo_bg= QColor(bg_inactivo)
        self._color_borde_inactivo= QColor(borde_inactivo)
        self._color_texto_inactivo= QColor(texto_inactivo)
        self._actualizar_estilo()

    def _actualizar_texto(self):

        self.lbl.setText(self._texto_base)
        self.updateGeometry()

    def _actualizar_estilo(self):

        color_texto= "white" if self._factor > 0.5 else self._color_texto_inactivo.name()
        self.lbl.setStyleSheet(f"background: transparent; color: {color_texto};")
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect= QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radio= rect.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color_mezclado())
        painter.drawRoundedRect(rect, radio, radio)
        if self._factor < 0.98:
            pen= QPen(self._color_borde_inactivo, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radio, radio)
        if self._ripples:
            path= QPainterPath()
            path.addRoundedRect(rect, radio, radio)
            painter.setClipPath(path)
            radio_max= max(self.width(), self.height()) * 1.3
            for punto, anim in self._ripples:
                progreso= anim.currentValue()
                if progreso is None:
                    continue
                #r: radio actual de la onda; crece con el progreso hasta radio_max
                r= radio_max * progreso
                alpha= max(0, int(90 * (1 - progreso)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, alpha))
                painter.drawEllipse(punto, r, r)


#Selector en forma de píldora. Generaliza `SegmentadoNaturaleza`
#(observaciones.py) a cualquier lista de (clave, etiqueta, color) -aquí
#se usa tanto para "Tipo de caso" (naturaleza) como para "Estado del
#caso"-.
#
#La opción activa se marca SOLO con el estado nativo :checked de cada
#QPushButton (fondo de su propio color + texto blanco), resuelto por Qt
#en cada repintado. Antes había además un QFrame "resaltado" que se
#movía a mano por encima de los botones (geometría calculada en
#_reposicionar_resaltado, con reintentos en showEvent/resizeEvent/
#singleShot(0) para cubrir el caso de nacer dentro de un panel
#colapsable todavía cerrado). Ese cálculo manual dependía de que el
#layout ya tuviera geometría válida en el momento exacto en que se
#disparaba cada uno de esos eventos, así que cuando el panel se abría
#en el momento "equivocado" el resaltado se quedaba con una geometría
#vieja o directamente no se movía -de ahí que la selección se viera
#marcada unas veces sí y otras no-. Al depender únicamente de
#QPushButton:checked ya no hay ninguna geometría que calcular ni
#reposicionar: el propio Qt pinta el estado correcto siempre, sin
#importar cuándo se vuelve visible el widget.
class SegmentadoPildora(QWidget):

    cambiado= Signal(str)

    def __init__(self, opciones, valor_inicial=None, parent=None):

        super().__init__(parent)
        self._opciones= opciones
        self._colores_opcion= {clave: color for clave, _et, color in opciones}
        self._valor= valor_inicial if valor_inicial is not None else opciones[0][0]
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._fondo= QFrame(self)
        self._fondo.setObjectName("SegmentadoFondo")

        #Espacio entre botones: además de verse mejor, evita que dos etiquetas largas se perciban "pegadas" cuando
        #ambas están cerca de su ancho mínimo.
        lay= QHBoxLayout(self)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(4)
        self._botones= []
        ancho_min_total= 0
        for clave, etiqueta, color in opciones:
            btn= QPushButton(f" {etiqueta}")
            btn.setIcon(QIcon(_pixmap_punto(color, 10)))
            btn.setIconSize(QSize(10, 10))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setObjectName("SegmentadoBoton")
            #el primer parámetro absorbe el checked de la señal y no se usa; el valor por defecto fija el de esta vuelta del bucle
            btn.clicked.connect(lambda _=False, k=clave: self.establecer_valor(k))
            #Ancho mínimo calculado a partir del propio texto (en vez de un
            #setMinimumWidth(260) fijo repartido entre TODAS las opciones):
            #con 3 o 4 etiquetas -algunas largas, como "En seguimiento"- ese reparto fijo se quedaba corto y forzaba a Qt a
            #comprimir los botones por debajo de su tamaño natural. Ese achique es precisamente lo que hacía que una opción
            #(p. ej. "Positiva") terminara pintándose fuera de su carril, invadiendo visualmente la fila de abajo. Con un
            #mínimo por botón que sí le entra al texto + icono, el widget completo pide el ancho que realmente necesita y
            #dos filas nunca vuelven a superponerse.
            ancho_texto= btn.fontMetrics().horizontalAdvance(etiqueta)
            btn.setMinimumWidth(ancho_texto + 46)
            lay.addWidget(btn, 1)
            self._botones.append((clave, btn))
            ancho_min_total += ancho_texto + 46 + lay.spacing()
        self.setMinimumWidth(ancho_min_total + 10)
        for k, btn in self._botones:
            btn.setChecked(k == self._valor)
        self._fondo.lower()

    def resizeEvent(self, evento):

        super().resizeEvent(evento)
        self._fondo.setGeometry(self.rect())

    def valor(self):

        return self._valor

    def establecer_valor(self, clave, animar=True, emitir=True):

        self._valor= clave
        for k, btn in self._botones:
            btn.setChecked(k == clave)
        if emitir:
            self.cambiado.emit(clave)

    def aplicar_paleta(self, bg, borde, txt_sec):

        self._fondo.setStyleSheet(
            f"QFrame#SegmentadoFondo {{ background-color: {bg}; border: 1px solid {borde}; border-radius: 12px; }}")
        for k, btn in self._botones:
            color= self._colores_opcion.get(k, "#6366F1")
            btn.setStyleSheet(f"""
                QPushButton#SegmentadoBoton {{
                    border: none; background: transparent; color: {txt_sec};
                    font-weight: 700; font-size: 11px; padding: 10px 14px; border-radius: 9px;
                }}
                QPushButton#SegmentadoBoton:checked {{ background-color: {color}; color: white; }}
            """)


#Franja compacta que solo aparece cuando hay algo que atender (mismo
#patrón que observaciones.py/banco_tareas.py): entra/sale animando su
#altura máxima. Un clic filtra la tabla por citas vencidas.
class CintaAlerta(QFrame):

    clicada= Signal()

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("CintaAlertaPsicologia")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)
        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji("⚠", 16))
        lay.addWidget(self.lbl_icono)
        self.lbl_texto= QLabel("")
        lay.addWidget(self.lbl_texto, 1)
        self.lbl_accion= QLabel("Ver vencidas ›")
        lay.addWidget(self.lbl_accion)

        self._anim= QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._visible_actual= False

    def aplicar_paleta(self, color="#F59E0B"):

        self.setStyleSheet(f"""
            QFrame#CintaAlertaPsicologia {{
                background-color: {_hex_a_rgba(color, 0.14)};
                border: 1px solid {_hex_a_rgba(color, 0.45)};
                border-radius: 10px;
            }}
        """)
        self.lbl_texto.setStyleSheet(
            f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {color};")
        self.lbl_accion.setStyleSheet(
            f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {color};")

    def mostrar_mensaje(self, texto):

        self.lbl_texto.setText(texto)
        if not self._visible_actual:
            self._visible_actual= True
            self._anim.stop()
            self._anim.setStartValue(self.maximumHeight())
            self._anim.setEndValue(38)
            self._anim.start()

    def ocultar(self):

        if self._visible_actual:
            self._visible_actual= False
            self._anim.stop()
            self._anim.setStartValue(self.maximumHeight())
            self._anim.setEndValue(0)
            self._anim.start()

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit()
        super().mousePressEvent(evento)


#Contenedor tipo tarjeta liviano que va DENTRO de `calendario.
#PanelDesplegable` (fondo translúcido neutro + borde redondeado + sombra
#con la que se anima el destello de guardado). Es el mismo patrón que
#usa observaciones.py: el panel colapsable (icono ⊕/⊖ + título, ver
#calendario.PanelDesplegable) se encarga de expandir/colapsar, y esta
#tarjeta de aquí adentro es la que realmente sostiene los campos del
#formulario y sabe destellar en verde/rojo tras guardar.
class TarjetaPanel(QFrame):

    def __init__(self, titulo="", con_sombra=True, parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaPanel")
        self._con_sombra= con_sombra
        self._sombra= None
        self._color_sombra_normal= QColor(0, 0, 0, 55)
        if con_sombra:
            self._sombra= QGraphicsDropShadowEffect(self)
            self._sombra.setColor(self._color_sombra_normal)
            self._sombra.setOffset(0, 4)
            self._sombra.setBlurRadius(20)
            self.setGraphicsEffect(self._sombra)

        raiz= QVBoxLayout(self)
        raiz.setContentsMargins(30, 28, 30, 30)
        raiz.setSpacing(18)

        self.lbl_titulo= None
        if titulo:
            self.lbl_titulo= QLabel(titulo)
            self.lbl_titulo.setObjectName("TituloTarjetaInterna")
            raiz.addWidget(self.lbl_titulo)

        #Espaciado más generoso entre cada bloque del formulario (antes 10px, todo quedaba pegado). Cada "bloque"
        #(label + su control) agrupa su propio espaciado interno más ajustado -ver los QWidget contenedores que arma
        #_construir_ui-, así el aire extra aquí solo separa secciones distintas entre sí, no cada elemento suelto.
        self.contenido= QVBoxLayout()
        self.contenido.setSpacing(28)
        raiz.addLayout(self.contenido)

    #Resplandor breve de color en el borde de la tarjeta, a modo de
    #confirmación visual (verde=éxito, rojo=aviso). Requiere con_sombra=True.
    def destello(self, color_hex="#22C55E"):

        if self._sombra is None:
            return
        grupo= QParallelAnimationGroup(self)
        anim_color= QPropertyAnimation(self._sombra, b"color", self)
        anim_color.setKeyValueAt(0.0, self._color_sombra_normal)
        anim_color.setKeyValueAt(0.5, QColor(color_hex))
        anim_color.setKeyValueAt(1.0, self._color_sombra_normal)
        anim_color.setDuration(650)
        anim_blur= QPropertyAnimation(self._sombra, b"blurRadius", self)
        anim_blur.setKeyValueAt(0.0, 20)
        anim_blur.setKeyValueAt(0.5, 36)
        anim_blur.setKeyValueAt(1.0, 20)
        anim_blur.setDuration(650)
        grupo.addAnimation(anim_color)
        grupo.addAnimation(anim_blur)
        grupo.start()
        self._anim_destello= grupo

    def aplicar_paleta(self, colores):

        self.setStyleSheet(f"""
            QFrame#TarjetaPanel {{
                background-color: {_hex_a_rgba(colores['txt_sec'], 0.07)};
                border: 1px solid {_hex_a_rgba(colores['txt_sec'], 0.16)};
                border-radius: 14px;
            }}
        """)
        if self.lbl_titulo is not None:
            self.lbl_titulo.setStyleSheet(
                f"color: {colores['accent']}; font-size: 13px; font-weight: 800; background: transparent;")
        if self._sombra is not None:
            self._color_sombra_normal= QColor(0, 0, 0, 55)
            self._sombra.setColor(self._color_sombra_normal)


#Página de navegación de Psicología. Se autoprotege con
#permisos.puede_ver_psicologia: aunque main.py ya oculta el módulo del
#menú a quien no lo tiene, esta comprobación es una segunda capa (igual
#que hacen Reportes/Configuración) por si algún día se navega aquí por
#otra vía (atajo, deep-link, etc.).
class ModuloPsicologia(QWidget):

    def __init__(self, main_window=None, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.registro_en_edicion= None
        self._ultimo_eliminado= None
        self._contador_valor_actual= 0
        self._vencidas_actual= 0
        self.pagina= ControlPaginacion(tamano_inicial=25)
        self.pagina.cambio.connect(self._cargar_tabla)

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        if main_window is not None and not puede_ver_psicologia(main_window):
            lbl_aviso= QLabel("No tienes acceso al módulo de Psicología.")
            lbl_aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_aviso.setStyleSheet("font-size: 14px; font-weight: 600; padding: 40px;")
            layout_raiz.addWidget(lbl_aviso)
            self._bloqueado= True
            return
        self._bloqueado= False

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(18)

        #---------- Cabecera tipo "hero" ----------
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Psicología")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Psicología")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Expedientes y seguimiento psicológico de los estudiantes — información confidencial.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        #Antes era un QLabel con el emoji 🔒 incrustado en el propio texto -depende de que el sistema operativo tenga
        #una fuente con ese glifo, ver el porqué en iconos_emoji.py-. Ahora es un pequeño contenedor con el candado
        #dibujado a mano (mismo sistema de iconos QPainter que usa el resto de la app) + una etiqueta de texto aparte,
        #igual de compacto pero consistente en cualquier equipo.
        self.chip_confidencial= QFrame()
        self.chip_confidencial.setObjectName("ChipConfidencial")
        lay_chip_conf= QHBoxLayout(self.chip_confidencial)
        lay_chip_conf.setContentsMargins(14, 7, 14, 7)
        lay_chip_conf.setSpacing(6)
        lbl_icono_chip_conf= QLabel()
        lbl_icono_chip_conf.setPixmap(pixmap_emoji("🔒", 13))
        lbl_icono_chip_conf.setStyleSheet("background: transparent;")
        lay_chip_conf.addWidget(lbl_icono_chip_conf)
        lbl_texto_chip_conf= QLabel("Confidencial")
        lbl_texto_chip_conf.setStyleSheet(
            "background: transparent; color: white; font-weight: 700; font-size: 11.5px;")
        lay_chip_conf.addWidget(lbl_texto_chip_conf)
        cabecera_layout.addWidget(self.chip_confidencial, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_contador= QLabel("0 casos")
        self.chip_contador.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)
        disposicion.addWidget(self.frame_cabecera)

        #---------- Alerta de citas vencidas ----------
        self.cinta_alerta= CintaAlerta()
        self.cinta_alerta.clicada.connect(self._ver_vencidas)
        disposicion.addWidget(self.cinta_alerta)

        #---------- Indicadores (KPI) ----------
        fila_kpis= QHBoxLayout()
        fila_kpis.setSpacing(14)
        self.tarjeta_kpi_total= TarjetaIndicador("📋", "Casos registrados", "#6366F1")
        self.tarjeta_kpi_abiertos= TarjetaIndicador("📂", "Casos abiertos", COLOR_ESTADO_CASO["Abierto"])
        self.tarjeta_kpi_seguimiento= TarjetaIndicador("🔁", "En seguimiento", COLOR_ESTADO_CASO["En seguimiento"])
        self.tarjeta_kpi_vencidas= TarjetaIndicador("⚠", "Citas vencidas", "#EF4444")
        for tarjeta in (self.tarjeta_kpi_total, self.tarjeta_kpi_abiertos,
                        self.tarjeta_kpi_seguimiento, self.tarjeta_kpi_vencidas):
            fila_kpis.addWidget(tarjeta, 1)
        disposicion.addLayout(fila_kpis)

        #---------- Filtros ----------
        self.frame_filtros= QFrame()
        self.frame_filtros.setObjectName("TarjetaFiltros")
        fila_filtros= QHBoxLayout(self.frame_filtros)
        fila_filtros.setContentsMargins(14, 10, 14, 10)
        fila_filtros.setSpacing(10)

        self.marco_busqueda= QFrame()
        self.marco_busqueda.setStyleSheet("QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda= QHBoxLayout(self.marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda)
        self.in_busqueda= QLineEdit()
        limitar_campo_texto(self.in_busqueda, 200)
        self.in_busqueda.setPlaceholderText("Buscar por estudiante o contenido…")
        self.in_busqueda.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_busqueda, 1)
        fila_filtros.addWidget(self.marco_busqueda, 1)

        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._refrescar)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador de búsqueda
        self.in_busqueda.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        #Los combos/chips de filtro siguen existiendo exactamente igual que
        #antes (misma lógica, mismas señales) pero ya NO se insertan en la
        #fila visible de filtros -eso obligaba a la tarjeta (y por lo tanto a todo el módulo) a estirarse de ancho para
        #hacerles espacio a los 3 combos + 2 chips + botón "Limpiar"-. Ahora viven dentro de una ventanita de filtros
        #aparte (ver `_construir_dialogo_filtros`), exactamente el mismo patrón que ya usa Estudiantes con su botón
        #"Filtros": la fila visible queda solo con la búsqueda + un botón que abre esa ventana, así el módulo puede ser
        #bastante más angosto sin sacrificar ningún filtro.
        self.combo_curso_filtro= QComboBox()
        self.combo_seccion_filtro= QComboBox()
        poblar_combo_curso(self.combo_curso_filtro, incluir_todos=True)
        cascada_seccion_por_curso(self.combo_curso_filtro, self.combo_seccion_filtro, incluir_todas=True)
        conectar_tooltip_seleccion(self.combo_curso_filtro, "Filtrar por curso")
        conectar_tooltip_seleccion(self.combo_seccion_filtro, "Filtrar por sección")
        self.combo_curso_filtro.currentIndexChanged.connect(
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            lambda: cascada_seccion_por_curso(self.combo_curso_filtro, self.combo_seccion_filtro, incluir_todas=True))
        self.combo_curso_filtro.currentIndexChanged.connect(self._refrescar)
        self.combo_seccion_filtro.currentIndexChanged.connect(self._refrescar)

        self.combo_estado_caso_filtro= QComboBox()
        self.combo_estado_caso_filtro.addItem("Todos los estados", None)
        for estado in ESTADOS_CASO:
            self.combo_estado_caso_filtro.addItem(estado, estado)
        conectar_tooltip_seleccion(self.combo_estado_caso_filtro, "Filtrar por estado del caso")
        self.combo_estado_caso_filtro.currentIndexChanged.connect(self._refrescar)

        #Área Técnica (Politécnico) / Carrera (Universidad): mismos combos, mismo criterio de visibilidad (solo
        #aparecen si la institución tiene ese módulo activo) y mismas consultas que usan estudiantes.py y
        #observaciones.py -antes psicologia.py no los tenía en absoluto-.
        self.lbl_filtro_especialidad= QLabel("Área Técnica:")
        self.combo_filtro_especialidad= QComboBox()
        self.combo_filtro_especialidad.currentIndexChanged.connect(self._refrescar)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad,
                                    "Filtrar por área técnica del estudiante (Politécnico)")

        self.lbl_filtro_carrera= QLabel("Carrera:")
        self.combo_filtro_carrera= QComboBox()
        self.combo_filtro_carrera.currentIndexChanged.connect(self._refrescar)
        conectar_tooltip_seleccion(self.combo_filtro_carrera,
                                    "Filtrar por carrera del estudiante (Universidad)")
        self._cargar_especialidades_combo_filtro()
        self._cargar_carreras_combo_filtro()

        self.chip_destacadas= Chip("destacadas", "Destacados", color_activo="#F59E0B")
        #_m: estado del chip que no se usa; solo se vuelve a filtrar
        self.chip_destacadas.alternado.connect(lambda _m: self._refrescar())
        self.chip_vencidas= Chip("vencidas", "Vencidas", color_activo="#EF4444")
        #_m: estado del chip que no se usa; solo se vuelve a filtrar
        self.chip_vencidas.alternado.connect(lambda _m: self._refrescar())

        self.btn_filtros= BotonAnimado("Filtros")
        self.btn_filtros.setObjectName("BtnAccionNeutro")
        icono_boton_filtro(self.btn_filtros)
        self.btn_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros.setToolTip("Abrir panel de filtros (área técnica/carrera, curso, sección, "
                                     "estado del caso, destacados, citas vencidas)")
        self.btn_filtros.clicked.connect(self._abrir_dialogo_filtros)
        fila_filtros.addWidget(self.btn_filtros)

        disposicion.addWidget(self.frame_filtros)
        self._construir_dialogo_filtros()

        #---------- Tabla ----------
        self.frame_tabla= QFrame()
        self.frame_tabla.setObjectName("TarjetaTabla")
        lay_tabla= QVBoxLayout(self.frame_tabla)
        lay_tabla.setContentsMargins(18, 16, 18, 14)
        lay_tabla.setSpacing(10)

        fila_cabecera_tabla= QHBoxLayout()
        fila_cabecera_tabla.addStretch()
        #Botón ⛶ que abre filtros + tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo
        #maximizado -mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-.
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla, [self.frame_filtros, self.frame_tabla],
            titulo= "Psicología", parent=self)
        lay_tabla.addLayout(fila_cabecera_tabla)

        self.tabla= QTableWidget()
        self.tabla.setColumnCount(len(HEADERS_TABLA))
        self.tabla.setHorizontalHeaderLabels(HEADERS_TABLA)
        aplicar_estructura_tabla(self.tabla)
        header= self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(50)
        #Anchos compactados (v3) respecto al diseño original -180/120/112/ 240/140/130- para que el módulo entero ocupe
        #menos ancho de pantalla sin perder legibilidad: "Categorías" y "Estudiante" eran las columnas más generosas y
        #las que más aportaban al ancho total, así que son las que más se recortan (los textos largos ya se elidían con
        #tooltip, ver `_widget_categorias_fila`). A cambio, la tabla gana un poco de alto (ver `setMinimumHeight`/
        #`setMaximumHeight` más abajo) para seguir mostrando un número cómodo de filas sin scroll.
        self._anchos_base_columnas= {
            COL_DESTACADA: 34, COL_FECHA: 86, COL_ESTUDIANTE: 150, COL_SECCION: 96,
            COL_NATURALEZA: 96, COL_CATEGORIAS: 170, COL_ESTADO: 118, COL_PROXIMA: 108,
        }
        self.tabla._anchos_base_columnas= self._anchos_base_columnas
        for col, ancho in self._anchos_base_columnas.items():
            self.tabla.setColumnWidth(col, ancho)
        #"Categorías" es la que se estira para absorber el ancho sobrante de la tarjeta (en vez de dejar, como antes,
        #una franja en blanco a la derecha de "Próxima cita" -ver `header.setStretchLastSection(False)`
        #de arriba, que deja TODAS las demás columnas en ancho fijo/manual-):
        #es la columna cuyo contenido varía más en longitud (puede tener varias categorías o ninguna) y la que más se
        #beneficia de espacio extra cuando la ventana es ancha, sin que las columnas de datos
        #cortos (Fecha, Sección, Estado...) se vean estiradas sin sentido.
        header.setSectionResizeMode(COL_CATEGORIAS, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.setMinimumHeight(400)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones_accion)
        #_i: índice o ítem que trae la señal y no se usa
        self.tabla.itemDoubleClicked.connect(lambda _i: self._ver_detalle())
        lay_tabla.addWidget(self.tabla, 1)
        self.estado_vacio= EstadoVacioFiltro(self.tabla, icono="🧠",
                                               texto_sin_resultados= "No hay registros con los filtros actuales")
        lay_tabla.addWidget(self.pagina)
        disposicion.addWidget(self.frame_tabla, stretch=1)

        #---------- Botonera de acciones sobre la fila seleccionada ---------- Ya NO hay un botón "Nuevo registro"
        #aparte: el panel colapsable de
        #abajo ("+ Nuevo registro de Psicología") es en sí mismo el punto de
        #entrada para agregar -se abre con solo tocar su cabecera-, exactamente igual que el panel "Nueva observación"
        #de observaciones.py. Tener ADEMÁS un botón separado que hiciera lo mismo era redundante.
        fila_botones= QHBoxLayout()
        self.btn_ver= BotonAnimado("Ver detalle")
        self.btn_ver.setIcon(icono_emoji("🔎"))
        self.btn_ver.setIconSize(_QSize_emoji(16, 16))
        self.btn_ver.clicked.connect(self._ver_detalle)
        fila_botones.addWidget(self.btn_ver)
        self.btn_editar= BotonAnimado("Editar")
        self.btn_editar.setObjectName("BtnAccionEditar")
        self.btn_editar.setIcon(icono_emoji("✏"))
        self.btn_editar.setIconSize(_QSize_emoji(16, 16))
        self.btn_editar.clicked.connect(self._cargar_seleccionada_en_formulario)
        fila_botones.addWidget(self.btn_editar)
        self.btn_eliminar= BotonAnimado("Eliminar")
        self.btn_eliminar.setObjectName("BtnAccionEliminar")
        self.btn_eliminar.setIcon(icono_emoji("🗑"))
        self.btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        self.btn_eliminar.clicked.connect(self._eliminar_seleccionada)
        fila_botones.addWidget(self.btn_eliminar)
        fila_botones.addStretch()
        self.btn_deshacer= BotonAnimado("Deshacer eliminación")
        self.btn_deshacer.setObjectName("BtnAccionNeutro")
        self.btn_deshacer.setIcon(icono_emoji("↩"))
        self.btn_deshacer.setIconSize(_QSize_emoji(16, 16))
        self.btn_deshacer.clicked.connect(self._deshacer_eliminacion)
        self.btn_deshacer.setVisible(False)
        fila_botones.addWidget(self.btn_deshacer)
        disposicion.addLayout(fila_botones)
        self._actualizar_botones_accion()

        #---------- Formulario (alta/edición), colapsable ---------- Mismo "cosito colapsable" que usa el resto de la
        #app -Observaciones, Materiales, Politécnico, Calendario, Materias, Horario-: el `calendario.PanelDesplegable`
        #compartido, con su icono circular verde ⊕/⊖ dibujado a mano (ver `_pixmap_circulo_mas_menos` en calendario.py)
        #en vez del chevron de texto que tenía antes esta implementación local. El título NO cambia al editar -igual
        #que "Nueva observación" en observaciones.py-: la diferencia entre alta y edición ya la comunica el banner
        #naranja de `edicion_feedback` que aparece encima del formulario, no el título del panel.
        self.panel_formulario= PanelDesplegable("Nuevo registro de Psicología")
        #Por dentro, el mismo patrón de dos capas que observaciones.py: el panel colapsable solo pone el encabezado
        #clicable y la animación de expandir/colapsar; la "tarjeta" de verdad -con su sombra y el destello verde/rojo
        #tras guardar- es este TarjetaPanel de aquí.
        self.tarjeta_form= TarjetaPanel(con_sombra=True)
        self.panel_formulario.cuerpo_layout().addWidget(self.tarjeta_form)
        form= self.tarjeta_form.contenido

        #Pequeño helper local: cada "bloque" del formulario es una etiqueta + su control, con un espaciado interno
        #chico y fijo (8px) -el aire GRANDE entre bloques ya lo pone `self.tarjeta_form.contenido` (22px). Separar
        #ambos espaciados es lo que evita el efecto "todo pegado": antes una sola lista plana de widgets en el mismo
        #QVBoxLayout no podía distinguir "espacio dentro de un campo" de "espacio entre campos distintos".
        def _bloque(etiqueta_texto, widget_control, stretch=0):

            contenedor= QWidget()
            #Fondo explícitamente transparente: sin esto, cada bloque hereda el fondo gris genérico que el QSS global de la
            #app aplica a cualquier QWidget plano -de ahí los "cosos" grises feos detrás de cada campo del formulario-. El
            #único fondo que debe verse en todo este formulario es el de la tarjeta que lo envuelve (self.tarjeta_form), no
            #el de cada bloque individual.
            contenedor.setStyleSheet("background: transparent;")
            lay_bloque= QVBoxLayout(contenedor)
            lay_bloque.setContentsMargins(0, 0, 0, 0)
            lay_bloque.setSpacing(8)
            lbl= QLabel(etiqueta_texto)
            lbl.setObjectName("DescModulo")
            lay_bloque.addWidget(lbl)
            lay_bloque.addWidget(widget_control)
            return contenedor, lbl

        #---------- Curso / Sección / Estudiante ---------- Antes iban en una sola fila con "Curso:" y su combo pegados
        #codo a codo con "Sección:" y el suyo; con 3 etiquetas + 3 combos en una sola línea angosta, todo se sentía
        #amontonado. Ahora cada campo es su propio bloque (etiqueta arriba, combo abajo) y las tres columnas respiran
        #con 24px de separación entre sí. ---------- Área Técnica / Carrera (opcional, solo si aplica) ---------- Mismo
        #criterio que ya usan los filtros de la tabla (_es_politecnico / _es_universidad): estos dos combos solo sirven
        #para acotar la lista de estudiantes de abajo, no se guardan como campo propio del caso -el registro ya queda
        #ligado al estudiante concreto que se elija-.
        fila0= QHBoxLayout()
        fila0.setSpacing(28)
        self.combo_area_tecnica_form= QComboBox()
        self.combo_area_tecnica_form.setMinimumHeight(38)
        self.combo_area_tecnica_form.currentIndexChanged.connect(self._poblar_estudiantes_form)
        conectar_tooltip_seleccion(self.combo_area_tecnica_form,
                                    "Filtrar estudiantes por área técnica (Politécnico)")
        self.combo_carrera_form= QComboBox()
        self.combo_carrera_form.setMinimumHeight(38)
        self.combo_carrera_form.currentIndexChanged.connect(self._poblar_estudiantes_form)
        conectar_tooltip_seleccion(self.combo_carrera_form,
                                    "Filtrar estudiantes por carrera (Universidad)")
        self.bloque_area_tecnica_form, _= _bloque("Área Técnica:", self.combo_area_tecnica_form)
        self.bloque_carrera_form, _= _bloque("Carrera:", self.combo_carrera_form)
        fila0.addWidget(self.bloque_area_tecnica_form)
        fila0.addWidget(self.bloque_carrera_form)
        fila0.addStretch()
        self._cargar_areas_tecnicas_combo_form()
        self._cargar_carreras_combo_form()
        form.addLayout(fila0)

        fila1= QHBoxLayout()
        fila1.setSpacing(28)
        self.combo_curso_form= QComboBox()
        self.combo_curso_form.setMinimumHeight(38)
        self.combo_seccion_form= QComboBox()
        self.combo_seccion_form.setMinimumHeight(38)
        poblar_combo_curso(self.combo_curso_form, incluir_todos=False)
        cascada_seccion_por_curso(self.combo_curso_form, self.combo_seccion_form, incluir_todas=False)
        conectar_tooltip_seleccion(self.combo_curso_form, "Curso del estudiante")
        conectar_tooltip_seleccion(self.combo_seccion_form, "Sección del estudiante")
        self.combo_curso_form.currentIndexChanged.connect(
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            lambda: cascada_seccion_por_curso(self.combo_curso_form, self.combo_seccion_form, incluir_todas=False))
        self.combo_seccion_form.currentIndexChanged.connect(self._poblar_estudiantes_form)
        self.combo_estudiante_form= QComboBox()
        self.combo_estudiante_form.setMinimumHeight(38)
        conectar_tooltip_seleccion(self.combo_estudiante_form, "Estudiante al que corresponde este registro")
        bloque_curso, _= _bloque("Curso:", self.combo_curso_form)
        bloque_seccion, _= _bloque("Sección:", self.combo_seccion_form)
        bloque_estudiante, _= _bloque("Estudiante:", self.combo_estudiante_form)
        fila1.addWidget(bloque_curso)
        fila1.addWidget(bloque_seccion)
        fila1.addWidget(bloque_estudiante, 1)
        form.addLayout(fila1)

        #---------- Tipo de caso (naturaleza) ----------
        bloque_naturaleza= QWidget()
        bloque_naturaleza.setStyleSheet("background: transparent;")
        lay_naturaleza= QVBoxLayout(bloque_naturaleza)
        lay_naturaleza.setContentsMargins(0, 0, 0, 0)
        lay_naturaleza.setSpacing(8)
        lbl_naturaleza= QLabel("Tipo de caso")
        lbl_naturaleza.setObjectName("DescModulo")
        lay_naturaleza.addWidget(lbl_naturaleza)
        self.segmentado_naturaleza= SegmentadoPildora(_OPCIONES_NATURALEZA, valor_inicial="Informativa")
        lay_naturaleza.addWidget(self.segmentado_naturaleza)
        form.addWidget(bloque_naturaleza)

        #---------- Estado del caso ----------
        bloque_estado= QWidget()
        bloque_estado.setStyleSheet("background: transparent;")
        lay_estado= QVBoxLayout(bloque_estado)
        lay_estado.setContentsMargins(0, 0, 0, 0)
        lay_estado.setSpacing(8)
        lbl_estado= QLabel("Estado del caso")
        lbl_estado.setObjectName("DescModulo")
        lay_estado.addWidget(lbl_estado)
        self.segmentado_estado= SegmentadoPildora(_OPCIONES_ESTADO, valor_inicial="Abierto")
        lay_estado.addWidget(self.segmentado_estado)
        form.addWidget(bloque_estado)

        #---------- Próxima cita / Marcar como destacado ---------- Antes iba todo en una sola QHBoxLayout angosta
        #(etiqueta + combo + 12px + checkbox), pegada justo debajo de la píldora de estado: ahí es exactamente donde se
        #veía la opción "Positiva" invadiendo esta
        #fila (ver el fix en SegmentadoPildora más arriba). Además de ese
        #arreglo de raíz, aquí se le da a esta fila su propio "bloque" con más aire arriba/abajo y más separación
        #horizontal entre el campo de fecha y el checkbox, para que ya no puedan sentirse como que comparten espacio.
        bloque_cita= QWidget()
        bloque_cita.setStyleSheet("background: transparent;")
        fila2= QHBoxLayout(bloque_cita)
        fila2.setContentsMargins(0, 0, 0, 0)
        fila2.setSpacing(10)
        lbl_proxima_cita= QLabel("Próxima cita:")
        self.fecha_proxima_cita_form= QDateEdit()
        self.fecha_proxima_cita_form.setCalendarPopup(True)
        self.fecha_proxima_cita_form.setSpecialValueText("Sin próxima cita")
        self.fecha_proxima_cita_form.setDate(self.fecha_proxima_cita_form.minimumDate())
        self.fecha_proxima_cita_form.setMinimumHeight(38)
        self.fecha_proxima_cita_form.setMinimumWidth(190)
        #Clic derecho -> "Quitar próxima cita": la única forma de volver a
        #"Sin próxima cita" antes era ir abriendo el calendario y buscando una fecha anterior a la mínima, lo cual no
        #es intuitivo ni siempre posible. Con un menú contextual se vuelve un atajo directo, igual
        #que "clic derecho -> cortar/pegar" en cualquier campo de texto.
        self.fecha_proxima_cita_form.setToolTip("Clic derecho para quitar la próxima cita")
        self.fecha_proxima_cita_form.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fecha_proxima_cita_form.customContextMenuRequested.connect(
            self._menu_contextual_proxima_cita)
        self.chk_destacada_form= QCheckBox("Marcar como destacado")
        fila2.addWidget(lbl_proxima_cita)
        fila2.addWidget(self.fecha_proxima_cita_form)
        fila2.addSpacing(36)
        fila2.addWidget(self.chk_destacada_form)
        fila2.addStretch()
        form.addWidget(bloque_cita)

        #---------- Categorías ----------
        bloque_categorias= QWidget()
        bloque_categorias.setStyleSheet("background: transparent;")
        lay_bloque_categorias= QVBoxLayout(bloque_categorias)
        lay_bloque_categorias.setContentsMargins(0, 0, 0, 0)
        lay_bloque_categorias.setSpacing(10)
        lbl_categorias= QLabel("¿De qué trata el caso? (puede elegir varias)")
        lbl_categorias.setObjectName("DescModulo")
        lay_bloque_categorias.addWidget(lbl_categorias)
        marco_categorias= QWidget()
        marco_categorias.setStyleSheet("background: transparent;")
        #Más espacio entre chips (antes 8px) y más aire vertical entre renglones cuando el FlowLayout tiene que
        #envolver línea -con 10 categorías en varias filas, 8px se sentía justo-.
        self.layout_categorias= FlowLayout(marco_categorias, margin=0, spacing=12)
        self._chips_categorias= {}
        for clave, etiqueta in CATEGORIAS:
            chip= Chip(clave, etiqueta, color_activo=COLOR_CATEGORIA.get(clave, "#6366F1"))
            self.layout_categorias.addWidget(chip)
            self._chips_categorias[clave]= chip
        lay_bloque_categorias.addWidget(marco_categorias)
        form.addWidget(bloque_categorias)

        #---------- Notas / descripción ----------
        bloque_descripcion= QWidget()
        bloque_descripcion.setStyleSheet("background: transparent;")
        lay_bloque_descripcion= QVBoxLayout(bloque_descripcion)
        lay_bloque_descripcion.setContentsMargins(0, 0, 0, 0)
        lay_bloque_descripcion.setSpacing(8)
        lbl_descripcion= QLabel("Notas / descripción del caso:")
        lbl_descripcion.setObjectName("DescModulo")
        lay_bloque_descripcion.addWidget(lbl_descripcion)
        self.txt_descripcion_form= QTextEdit()
        self.txt_descripcion_form.setObjectName("TxtDescripcionForm")
        self.txt_descripcion_form.setPlaceholderText(
            "Describe la sesión, evaluación o seguimiento realizado. Este contenido es confidencial.")
        limitar_campo_texto(self.txt_descripcion_form, 8000)
        self.txt_descripcion_form.setMinimumHeight(120)
        lay_bloque_descripcion.addWidget(self.txt_descripcion_form)
        form.addWidget(bloque_descripcion)

        #Igual que chip_confidencial más arriba: candado dibujado a mano en vez del emoji 🔒 suelto dentro del texto, en
        #su propia etiqueta, alineado arriba porque el texto puede ocupar dos líneas.
        self.nota_confidencial= QFrame()
        self.nota_confidencial.setObjectName("NotaConfidencial")
        lay_nota_conf= QHBoxLayout(self.nota_confidencial)
        lay_nota_conf.setContentsMargins(14, 12, 14, 12)
        lay_nota_conf.setSpacing(10)
        lbl_icono_nota_conf= QLabel()
        lbl_icono_nota_conf.setPixmap(pixmap_emoji("🔒", 14))
        lbl_icono_nota_conf.setStyleSheet("background: transparent;")
        lay_nota_conf.addWidget(lbl_icono_nota_conf, 0, Qt.AlignmentFlag.AlignTop)
        self.lbl_texto_nota_confidencial= QLabel(
            "Este registro es confidencial: solo lo puede ver el/la psicólogo/a responsable "
            "y los roles gerenciales de la institución.")
        self.lbl_texto_nota_confidencial.setWordWrap(True)
        self.lbl_texto_nota_confidencial.setStyleSheet("background: transparent;")
        lay_nota_conf.addWidget(self.lbl_texto_nota_confidencial, 1)
        form.addWidget(self.nota_confidencial)

        fila_botones_form= QHBoxLayout()
        fila_botones_form.setContentsMargins(0, 6, 0, 0)
        fila_botones_form.setSpacing(12)
        self.btn_cancelar_form= BotonAnimado("Cancelar")
        self.btn_cancelar_form.setObjectName("BtnAccionNeutro")
        self.btn_cancelar_form.setIcon(icono_emoji("✖"))
        self.btn_cancelar_form.setIconSize(_QSize_emoji(16, 16))
        self.btn_cancelar_form.clicked.connect(self._cerrar_formulario)
        fila_botones_form.addWidget(self.btn_cancelar_form)
        fila_botones_form.addStretch()
        self.btn_guardar_form= BotonAnimado("Guardar registro")
        self.btn_guardar_form.setObjectName("BtnAccionAgregar")
        self.btn_guardar_form.setIcon(icono_emoji("💾"))
        self.btn_guardar_form.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_form.clicked.connect(self._guardar)
        fila_botones_form.addWidget(self.btn_guardar_form)
        form.addLayout(fila_botones_form)

        disposicion.addWidget(self.panel_formulario)
        #Sin esto, cuando la ventana es más alta que el contenido, el sobrante de espacio queda repartido de forma
        #ambigua entre los widgets de
        #arriba (dejando huecos raros, como el que se veía debajo de la
        #botonera). Con el stretch al final, ese sobrante se va SIEMPRE después del panel, como margen inferior normal
        #de una página.
        disposicion.addStretch(1)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        self._poblar_estudiantes_form()
        self.actualizar_tema()  #aplica colores/estilos (la tabla aún no tiene datos)
        self._refrescar()  #única carga real de datos + reinicio de paginación
        if self.main_window is not None:
            self._registrar_atajos_teclado()

    #Atajos de teclado
    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Psicología"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar registro de Psicología", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+N", "Nuevo registro de Psicología", self._nuevo)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Editar registro seleccionado",
                         self._cargar_seleccionada_en_formulario)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar registro seleccionado",
                         self._eliminar_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+Z", "Deshacer eliminación", self._deshacer_eliminacion)
        #Los de abajo son nuevos: siguen el mismo patrón que ya usa este
        #método (mismo callback que el botón correspondiente), solo que
        #sobre acciones que antes no tenían tecla asignada.
        registrar_atajo(self, self.main_window, "Ctrl+F", "Buscar",
                         #la lambda agrupa varias llamadas que se ejecutan juntas al dispararse la señal
                         lambda: (self.in_busqueda.setFocus(), self.in_busqueda.selectAll()))
        registrar_atajo(self, self.main_window, "F5", "Actualizar tabla", self._refrescar)
        registrar_atajo(self, self.main_window, "Ctrl+D", "Ver detalle del registro seleccionado",
                         #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                         lambda: self.btn_ver.click() if self.btn_ver.isEnabled() else None)
        registrar_atajo(self, self.main_window, "Ctrl+Shift+F", "Abrir panel de filtros",
                         self._abrir_dialogo_filtros)

    #TEMA / ESTILO
    #Sincroniza los colores de las tarjetas y acentos de este módulo con
    #el tema/modo claro-oscuro actual de la app. Se llama al construir la
    #pantalla y cada vez que el usuario cambia de tema (ver main.py) —
    #antes este método NO EXISTÍA, así que el módulo nunca se repintaba.
    def actualizar_tema(self):

        if getattr(self, "_bloqueado", True):
            return
        colores= _colores_tema(self.main_window)
        self._modo_oscuro= bool(getattr(self.main_window, "modo_oscuro", False)) if self.main_window else False

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {colores['accent']}, stop:1 {colores['accent_hv']});
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
        self.chip_contador.setStyleSheet("""
            QLabel#ChipContador {
                background-color: rgba(255, 255, 255, 40);
                color: white;
                border-radius: 14px;
                padding: 7px 16px;
                font-weight: 700;
                font-size: 12px;
            }
        """)
        self.chip_confidencial.setStyleSheet("""
            QFrame#ChipConfidencial {
                background-color: rgba(255, 255, 255, 26);
                border-radius: 14px;
            }
        """)
        self.cinta_alerta.aplicar_paleta("#F59E0B")
        #Las 4 tarjetas KPI (dashboard.TarjetaIndicador) necesitan que se les llame aplicar_paleta() para pintarse -sin
        #esto se quedan con el estilo por defecto de Qt (sin tarjeta, sin insignia de color, sin texto de acento),
        #aunque el valor sí se actualice bien-. Mismos 5 parámetros y mismo origen de colores que usa materias.py.
        for tarjeta in (self.tarjeta_kpi_total, self.tarjeta_kpi_abiertos,
                        self.tarjeta_kpi_seguimiento, self.tarjeta_kpi_vencidas):
            tarjeta.aplicar_paleta(colores["bg_panel"], colores["bg_btn"], colores["txt_prim"],
                                    colores["txt_sec"], self._modo_oscuro)
        self.frame_filtros.setStyleSheet(f"""
            QFrame#TarjetaFiltros {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 14px;
            }}
        """)
        self.icono_busqueda.establecer_color(colores["txt_sec"])
        self.chip_destacadas.establecer_paleta(colores["bg_track"], colores["bg_btn"], colores["txt_sec"])
        self.chip_vencidas.establecer_paleta(colores["bg_track"], colores["bg_btn"], colores["txt_sec"])
        for chip in self._chips_categorias.values():
            chip.establecer_paleta(colores["bg_track"], colores["bg_btn"], colores["txt_sec"])

        self.frame_tabla.setStyleSheet(f"""
            QFrame#TarjetaTabla {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 14px;
            }}
            QTableWidget QScrollBar:vertical {{
                background: transparent; width: 10px; margin: 2px; border: none;
            }}
            QTableWidget QScrollBar::handle:vertical {{
                background: {colores['bg_btn']}; border-radius: 5px; min-height: 30px;
            }}
            QTableWidget QScrollBar::handle:vertical:hover {{ background: {colores['accent']}; }}
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
                background: {colores['bg_btn']}; border-radius: 5px; min-width: 30px;
            }}
            QTableWidget QScrollBar::handle:horizontal:hover {{ background: {colores['accent']}; }}
            QTableWidget QScrollBar::add-line:horizontal, QTableWidget QScrollBar::sub-line:horizontal {{
                width: 0px; border: none; background: transparent;
            }}
            QTableWidget QScrollBar::add-page:horizontal, QTableWidget QScrollBar::sub-page:horizontal {{
                background: transparent; border: none;
            }}
        """)

        self.panel_formulario.actualizar_color_tema()
        self.tarjeta_form.aplicar_paleta(colores)
        self.segmentado_naturaleza.aplicar_paleta(colores["bg_track"], colores["bg_btn"], colores["txt_sec"])
        self.segmentado_estado.aplicar_paleta(colores["bg_track"], colores["bg_btn"], colores["txt_sec"])
        self.nota_confidencial.setStyleSheet(f"""
            QFrame#NotaConfidencial {{
                background-color: {_hex_a_rgba(colores['accent'], 0.08)};
                border: 1px solid {_hex_a_rgba(colores['accent'], 0.22)};
                border-radius: 8px;
            }}
        """)
        self.lbl_texto_nota_confidencial.setStyleSheet(
            f"background: transparent; color: {colores['txt_sec']}; font-size: 11px; font-style: italic;")

        #Estilo propio para los campos del formulario (combos + fecha):
        #caja bien delimitada (borde visible + fondo propio + esquinas redondeadas) y un borde de acento al enfocar, en
        #vez de depender solo del QSS genérico de QComboBox/QDateEdit que pone main.py -ese solo define un borde 1px
        #muy sutil del mismo gris del fondo, que aquí se perdía contra el resto de controles ya rediseñados.
        ##Dos detalles que se quedaron sueltos la primera vez que se armó
        #este bloque:
        #1) Sin una regla "::down-arrow" propia, el triangulito nativo de Qt para abrir el calendario de "Próxima cita"
        #quedaba oscuro sobre fondo oscuro (o al revés) -invisible según el tema-, así que ahora se dibuja a mano con
        #el color secundario del tema, siempre visible sin importar el modo claro/oscuro. Los combos
        #normales (Curso, Sección, Estudiante, etc.) se dejan con su
        #flechita nativa de Qt -solo la fecha necesitaba este arreglo-. 2) Un widget con su PROPIO stylesheet (como
        #cada combo de aquí, vía setStyleSheet) deja de heredar el "QToolTip {...}" que puso más arriba
        #`self.setStyleSheet(...)`: Qt no combina el stylesheet de un widget con el de sus ancestros, usa el más
        #cercano nada más -mismo motivo por el que el diálogo de filtros necesita su propio QToolTip más abajo-. Por
        #eso el QToolTip también se repite aquí, dentro de este mismo bloque.
        ##El bloque "QComboBox QAbstractItemView { ... }" de aquí abajo es el que pinta la LISTA desplegable (lo que se
        #ve al abrir el combo), no la caja cerrada. Esa lista es una ventana emergente aparte -mismo caso que un
        #QDialog de nivel superior-, así que NO hereda ningún estilo puesto en un ancestro: si un combo no tiene este
        #bloque puesto DIRECTAMENTE en sí mismo, su desplegable cae al estilo nativo de Qt (fondo blanco, texto negro)
        #sin importar el tema, y en modo oscuro queda ilegible/con colores que no combinan -exactamente el bug
        #reportado-. Por eso se aplica a TODOS los combos del módulo, no solo a los del formulario.
        estilo_campo= f"""
            QComboBox, QDateEdit, QTextEdit#TxtDescripcionForm {{
                background-color: {colores['bg_panel']};
                border: 1.5px solid {colores['bg_btn']};
                border-radius: 8px;
                padding: 6px 10px;
                color: {colores['txt_prim']};
            }}
            QComboBox:hover, QDateEdit:hover, QTextEdit#TxtDescripcionForm:hover {{
                border-color: {_hex_a_rgba(colores['accent'], 0.55)};
            }}
            QComboBox:focus, QDateEdit:focus, QTextEdit#TxtDescripcionForm:focus {{
                border-color: {colores['accent']};
            }}
            QComboBox::drop-down, QDateEdit::drop-down {{
                border: none;
                width: 26px;
            }}
            QDateEdit::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
                border-left: 7px solid transparent;
                border-right: 7px solid transparent;
                border-top: 9px solid {colores['txt_sec']};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                selection-background-color: {colores['accent']};
                selection-color: white;
                outline: none;
            }}
            QToolTip {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """
        for campo in (self.combo_curso_form, self.combo_seccion_form, self.combo_estudiante_form,
                      self.combo_area_tecnica_form, self.combo_carrera_form, self.fecha_proxima_cita_form,
                      self.combo_curso_filtro, self.combo_seccion_filtro, self.combo_estado_caso_filtro,
                      self.combo_filtro_especialidad, self.combo_filtro_carrera, self.txt_descripcion_form):
            campo.setStyleSheet(estilo_campo)

        #Calendario emergente de "Próxima cita" (QDateEdit.setCalendarPopup):
        #es, otra vez, una ventana de nivel superior aparte -por eso no basta con el estilo del QDateEdit de arriba-, y
        #por defecto Qt lo pinta siempre en blanco/negro sin importar el tema, así que en modo oscuro quedaba
        #deslumbrando sobre el resto de la tarjeta oscura. Se estiliza aquí, en el propio QCalendarWidget interno.
        calendario_widget= self.fecha_proxima_cita_form.calendarWidget()
        if calendario_widget is not None:
            calendario_widget.setStyleSheet(f"""
                QCalendarWidget {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                }}
                QCalendarWidget QWidget {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                }}
                QCalendarWidget QToolButton {{
                    background-color: transparent;
                    color: {colores['txt_prim']};
                    font-weight: 700;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 8px;
                    icon-size: 16px;
                }}
                QCalendarWidget QToolButton:hover {{
                    background-color: {colores['bg_btn']};
                }}
                QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
                QCalendarWidget QMenu {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                    border: 1px solid {colores['bg_btn']};
                }}
                QCalendarWidget QSpinBox {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                    border: 1px solid {colores['bg_btn']};
                    border-radius: 4px;
                    padding: 2px;
                }}
                QCalendarWidget QAbstractItemView {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                    selection-background-color: {colores['accent']};
                    selection-color: white;
                    outline: none;
                }}
                QCalendarWidget QAbstractItemView:disabled {{
                    color: {colores['txt_sec']};
                }}
                QCalendarWidget #qt_calendar_navigationbar {{
                    background-color: {colores['bg_btn']};
                }}
            """)

        #Ventanita de "Filtros": mismo estilo (icono circular de acento, título, subtítulo tenue y separador) que usa
        #el resto de módulos con esta misma ventana -antes se quedaba con el look por defecto de Qt porque nunca se le
        #aplicaba ningún stylesheet-.
        if hasattr(self, "dialogo_filtros"):
            self.dialogo_filtros.setStyleSheet(f"""
                QDialog#DialogoFiltros {{
                    background-color: {colores['bg_panel']};
                }}
                /* El diálogo de filtros es una ventana de nivel superior
                   aparte de ModuloPsicologia -no un hijo normal dentro del
                   mismo árbol-, así que NO hereda el QToolTip definido más
                   abajo en self.setStyleSheet(...): sin repetirlo aquí, los
                   tooltips de los combos/chips de este diálogo caían al
                   estilo nativo de Qt (fondo blanco, texto negro), que en
                   modo oscuro se ve fuera de lugar. Mismo patrón que usa
                   calendario.dialogo_filtros_vista. */
                QToolTip {{
                    background-color: {colores['bg_panel']};
                    color: {colores['txt_prim']};
                    border: 1px solid {colores['bg_btn']};
                    padding: 6px 10px;
                    border-radius: 6px;
                }}
                QLabel#IconoEncabezadoFiltros {{
                    background-color: {colores['accent']};
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
                    color: {colores['txt_prim']};
                    background: transparent;
                }}
                QLabel#SubtituloFiltros {{
                    font-size: 11.5px;
                    color: {colores['txt_sec']};
                    background: transparent;
                }}
                QFrame#SeparadorFiltros {{
                    background-color: {colores['bg_btn']};
                    max-height: 1px;
                    border: none;
                }}
                QLabel {{
                    color: {colores['txt_prim']};
                    font-weight: 700;
                    font-size: 12.5px;
                    background: transparent;
                }}
            """)
        #Si la tabla ya tenía datos cargados (es decir, esto es un cambio de tema en caliente, no la construcción
        #inicial), se recarga para que el tinte de fila (según estado del caso) use la opacidad correcta de modo
        #claro/oscuro. En la construcción inicial se deja que sea `_refrescar()` -llamado justo después- quien haga la
        #única carga real, para no consultar la base de datos dos veces.
        if getattr(self, "_tabla_cargada_una_vez", False):
            self._cargar_tabla()

    #ANIMACIONES — capa puramente visual
    def _animar_contador(self, valor_final):

        if valor_final is None:
            return

        def texto(v):

            return f"{v} caso" + ("s" if v != 1 else "")
        valor_inicial= self._contador_valor_actual
        self._contador_valor_actual= valor_final
        if valor_inicial == valor_final:
            self.chip_contador.setText(texto(valor_final))
            return
        anim= QVariantAnimation(self)
        anim.setStartValue(valor_inicial)
        anim.setEndValue(valor_final)
        anim.setDuration(350)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #v: valor actual del slider, que se muestra como porcentaje
        anim.valueChanged.connect(lambda v: self.chip_contador.setText(texto(int(v))))
        anim.start()
        self._anim_contador= anim

    def _animar_fundido_tabla(self):

        efecto= QGraphicsOpacityEffect(self.tabla)
        self.tabla.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        anim.finished.connect(lambda: self.tabla.setGraphicsEffect(None))
        anim.start()
        self._anim_tabla= anim

    #Carga de datos
    def _condiciones_filtro(self, excluir_estado=False):

        condiciones= []
        parametros= []
        curso_id= self.combo_curso_filtro.currentData()
        seccion_id= self.combo_seccion_filtro.currentData()
        if seccion_id is not None:
            condiciones.append("estudiantes.seccion_id = ?")
            parametros.append(seccion_id)
        elif curso_id is not None:
            condiciones.append("estudiantes.seccion_id IN (SELECT id FROM secciones WHERE grado_id=?)")
            parametros.append(curso_id)
        especialidad_id= (self.combo_filtro_especialidad.currentData()
                            if self._es_politecnico() else None)
        if especialidad_id is not None:
            condiciones.append("estudiantes.especialidad_id = ?")
            parametros.append(especialidad_id)
        carrera_id= (self.combo_filtro_carrera.currentData()
                      if self._es_universidad() else None)
        if carrera_id is not None:
            condiciones.append("estudiantes.carrera_id = ?")
            parametros.append(carrera_id)
        if not excluir_estado:
            estado_caso= self.combo_estado_caso_filtro.currentData()
            if estado_caso is not None:
                condiciones.append("psicologia.estado_caso = ?")
                parametros.append(estado_caso)
        texto= self.in_busqueda.text().strip()
        if texto:
            condiciones.append("(estudiantes.nombre || ' ' || estudiantes.apellidos LIKE ? OR psicologia.texto LIKE ?)")
            parametros.extend([f"%{texto}%", f"%{texto}%"])
        if self.chip_destacadas.esta_marcado():
            condiciones.append("psicologia.destacada = 1")
        if self.chip_vencidas.esta_marcado():
            hoy= date.today().strftime("%Y-%m-%d")
            condiciones.append("(psicologia.proxima_cita IS NOT NULL AND psicologia.proxima_cita < ? "
                                "AND psicologia.estado_caso NOT IN ('Cerrado','Derivado'))")
            parametros.append(hoy)
        #Un psicólogo sin acceso gerencial solo ve SUS PROPIOS registros (los que él mismo abrió); un rol gerencial ve
        #todos, para poder supervisar la carga de casos del departamento de Psicología.
        if self.main_window is not None and not tiene_acceso_gerencial(self.main_window):
            id_usuario= getattr(self.main_window, "id_usuario_actual", None)
            condiciones.append("psicologia.psicologo_usuario_id = ?")
            parametros.append(id_usuario)
        return condiciones, parametros

    def _refrescar(self):

        self.pagina.reiniciar()
        self._cargar_tabla()

    def _cargar_tabla(self):

        if getattr(self, "_bloqueado", True):
            return
        condiciones, parametros= self._condiciones_filtro()
        where= f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""SELECT COUNT(*) as n FROM psicologia
                      JOIN estudiantes ON psicologia.estudiante_id = estudiantes.id
                      {where}""", parametros)
        total= c.fetchone()["n"]
        self.pagina.establecer_total(total)
        inicio, _fin= self.pagina.rango_actual()
        tam= self.pagina.tamano_pagina() or total or 1
        c.execute(f"""SELECT psicologia.*, estudiantes.nombre as est_nombre, estudiantes.apellidos as est_apellidos,
                      secciones.nombre as seccion_nombre, grados.nombre as grado_nombre,
                      especialidades.nombre as area_nombre, carreras.nombre as carrera_nombre
                      FROM psicologia
                      JOIN estudiantes ON psicologia.estudiante_id = estudiantes.id
                      LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                      LEFT JOIN grados ON secciones.grado_id = grados.id
                      LEFT JOIN especialidades ON estudiantes.especialidad_id = especialidades.id
                      LEFT JOIN carreras ON estudiantes.carrera_id = carreras.id
                      {where}
                      ORDER BY psicologia.fecha DESC, psicologia.id DESC
                      LIMIT ? OFFSET ?""", parametros + [tam, inicio])
        filas= c.fetchall()
        conn.close()

        hoy= date.today().strftime("%Y-%m-%d")
        modo_oscuro= bool(getattr(self.main_window, "modo_oscuro", False)) if self.main_window else False
        alpha_tinte= 46 if modo_oscuro else 30
        color_txt_sec= self._colores_txt_sec()

        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(filas))
            for fila_idx, f in enumerate(filas):
                estado= f["estado_caso"] or "Abierto"
                color_estado= COLOR_ESTADO_CASO.get(estado, "#64748B")
                naturaleza= f["naturaleza"] or "Informativa"
                color_nat= _COLOR_NATURALEZA.get(naturaleza, "#64748B")
                vencida= bool(f["proxima_cita"] and f["proxima_cita"] < hoy and estado not in ("Cerrado", "Derivado"))

                item_destacada= QTableWidgetItem()
                item_destacada.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if f["destacada"]:
                    item_destacada.setIcon(icono_emoji("⭐"))
                    item_destacada.setToolTip("Caso destacado")
                self.tabla.setItem(fila_idx, COL_DESTACADA, item_destacada)

                self.tabla.setItem(fila_idx, COL_FECHA, QTableWidgetItem(_fecha_relativa_dia(f["fecha"], self.main_window)))

                item_est= QTableWidgetItem(f"{f['est_nombre']} {f['est_apellidos']}")
                item_est.setData(Qt.ItemDataRole.UserRole, f["id"])
                f_est= item_est.font()
                f_est.setBold(True)
                item_est.setFont(f_est)
                self.tabla.setItem(fila_idx, COL_ESTUDIANTE, item_est)

                curso_txt= _texto_curso_completo(f)
                self.tabla.setItem(fila_idx, COL_SECCION, QTableWidgetItem(curso_txt))

                item_nat= QTableWidgetItem(naturaleza)
                item_nat.setForeground(QColor(color_nat))
                f_nat= item_nat.font()
                f_nat.setBold(True)
                item_nat.setFont(f_nat)
                self.tabla.setItem(fila_idx, COL_NATURALEZA, item_nat)

                self.tabla.setItem(fila_idx, COL_CATEGORIAS, QTableWidgetItem(""))
                widget_categorias= _widget_categorias_fila(f["categorias"], color_txt_sec)
                self.tabla.setCellWidget(fila_idx, COL_CATEGORIAS, widget_categorias)

                item_estado= QTableWidgetItem(estado)
                item_estado.setForeground(QColor(color_estado))
                f_estado= item_estado.font()
                f_estado.setBold(True)
                item_estado.setFont(f_estado)
                self.tabla.setItem(fila_idx, COL_ESTADO, item_estado)

                if f["proxima_cita"]:
                    texto_prox= formatear_fecha(f["proxima_cita"], self.main_window)
                else:
                    texto_prox= "—"
                item_prox= QTableWidgetItem(texto_prox)
                if vencida:
                    #Antes se anteponía el emoji ⚠ suelto al texto; ahora es el mismo triángulo de alerta dibujado a mano que usa
                    #el resto de la app (icono_emoji), puesto como icono real del item en vez de un carácter de texto.
                    item_prox.setIcon(icono_emoji("⚠"))
                    item_prox.setForeground(QColor("#EF4444"))
                    f_prox= item_prox.font()
                    f_prox.setBold(True)
                    item_prox.setFont(f_prox)
                    item_prox.setToolTip("Esta cita ya venció y el caso sigue abierto")
                self.tabla.setItem(fila_idx, COL_PROXIMA, item_prox)

                #Tinte suave de toda la fila según el estado del caso -misma idea que observaciones.py con la naturaleza-, para
                #leer de un vistazo qué casos siguen abiertos/en seguimiento.
                fondo_fila= _color_fila_qcolor(color_estado, alpha_tinte)
                for col in range(self.tabla.columnCount()):
                    item= self.tabla.item(fila_idx, col)
                    if item is not None:
                        item.setBackground(fondo_fila)

        ajustar_anchos_columnas(self.tabla, techos={COL_CATEGORIAS: 280})
        self.estado_vacio.actualizar(hay_filtro_elegido=True)
        self._actualizar_botones_accion()
        self._animar_contador(total)
        self._actualizar_kpis(*self._condiciones_filtro(excluir_estado=True))
        self._animar_fundido_tabla()
        self._tabla_cargada_una_vez= True

    def _colores_txt_sec(self):

        try:

            return _colores_tema(self.main_window)["txt_sec"]
        except Exception:
            return "#64748B"

    def _actualizar_kpis(self, condiciones, parametros):

        where= f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        hoy= date.today().strftime("%Y-%m-%d")
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""SELECT
                      COUNT(*) as total,
                      SUM(CASE WHEN psicologia.estado_caso='Abierto' THEN 1 ELSE 0 END) as abiertos,
                      SUM(CASE WHEN psicologia.estado_caso='En seguimiento' THEN 1 ELSE 0 END) as seguimiento,
                      SUM(CASE WHEN psicologia.proxima_cita IS NOT NULL AND psicologia.proxima_cita < ?
                               AND psicologia.estado_caso NOT IN ('Cerrado','Derivado') THEN 1 ELSE 0 END) as vencidas
                      FROM psicologia
                      JOIN estudiantes ON psicologia.estudiante_id = estudiantes.id
                      {where}""", [hoy] + parametros)
        fila= c.fetchone()
        conn.close()
        self.tarjeta_kpi_total.actualizar(fila["total"] or 0)
        self.tarjeta_kpi_abiertos.actualizar(fila["abiertos"] or 0)
        self.tarjeta_kpi_seguimiento.actualizar(fila["seguimiento"] or 0)
        self.tarjeta_kpi_vencidas.actualizar(fila["vencidas"] or 0)
        self._vencidas_actual= fila["vencidas"] or 0
        self._actualizar_alerta_vencidas()

    def _actualizar_alerta_vencidas(self):

        n= self._vencidas_actual
        if n > 0:
            plural= "s" if n != 1 else ""
            self.cinta_alerta.mostrar_mensaje(
                f"{n} cita{plural} de seguimiento vencida{plural} — el caso sigue abierto")
        else:
            self.cinta_alerta.ocultar()

    def _ver_vencidas(self):

        self.chip_vencidas.establecer_marcado(True)
        self._refrescar()

    def _fila_id_seleccionada(self):

        seleccion= self.tabla.selectedItems()
        if not seleccion:
            return None
        item= self.tabla.item(self.tabla.currentRow(), COL_ESTUDIANTE)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _actualizar_botones_accion(self):

        hay_seleccion= self._fila_id_seleccionada() is not None
        self.btn_ver.setEnabled(hay_seleccion)
        self.btn_editar.setEnabled(hay_seleccion)
        self.btn_eliminar.setEnabled(hay_seleccion)

    #True si la institución es de tipo Politécnico (o Personalizado con
    #el módulo Politécnico activo). Mismo criterio usado en
    #estudiantes.py/observaciones.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la institución es de tipo Universidad (o Personalizado con
    #el módulo Universidad activo). Mismo criterio usado en
    #estudiantes.py/observaciones.py.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    #Igual que en Estudiantes/Observaciones: el combo de Área Técnica
    #solo se muestra si la institución tiene el módulo Politécnico
    #activo.
    def _cargar_especialidades_combo_filtro(self):

        combo= self.combo_filtro_especialidad
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad.setVisible(es_poli)
        combo.setVisible(es_poli)
        if not es_poli:
            return
        actual= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todas las áreas técnicas", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Igual que en Estudiantes/Observaciones: el combo de Carrera solo
    #se muestra si la institución tiene el módulo Universidad activo.
    def _cargar_carreras_combo_filtro(self):

        combo= self.combo_filtro_carrera
        es_uni= self._es_universidad()
        self.lbl_filtro_carrera.setVisible(es_uni)
        combo.setVisible(es_uni)
        if not es_uni:
            return
        actual= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todas las carreras", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _limpiar_filtros(self):

        self.combo_curso_filtro.setCurrentIndex(0)
        cascada_seccion_por_curso(self.combo_curso_filtro, self.combo_seccion_filtro, incluir_todas=True)
        self.combo_estado_caso_filtro.setCurrentIndex(0)
        self.combo_filtro_especialidad.setCurrentIndex(0)
        self.combo_filtro_carrera.setCurrentIndex(0)
        self.chip_destacadas.establecer_marcado(False, animar=False, emitir=False)
        self.chip_vencidas.establecer_marcado(False, animar=False, emitir=False)
        self.in_busqueda.clear()
        self._refrescar()

    #Crea (una sola vez) la ventanita con los filtros de curso/sección,
    #estado del caso y los chips rápidos. No es modal: se puede dejar
    #abierta mientras se ajustan los combos y la tabla de atrás se sigue
    #actualizando en vivo -mismo patrón que `estudiantes._construir_dialogo_filtros`.
    def _construir_dialogo_filtros(self):

        self.dialogo_filtros= QDialog(self)
        self.dialogo_filtros.setObjectName("DialogoFiltros")
        self.dialogo_filtros.setWindowTitle("Filtros de Psicología")
        aplicar_icono_ventana(self.dialogo_filtros, ICONO_FILTRO)
        self.dialogo_filtros.setModal(False)
        self.dialogo_filtros.setMinimumWidth(320)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros)
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

        lbl_subtitulo= QLabel("Combina los filtros que necesites; la tabla se actualiza al instante.")
        lbl_subtitulo.setObjectName("SubtituloFiltros")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltros")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        grid.addWidget(self.lbl_filtro_especialidad, fila, 0)
        grid.addWidget(self.combo_filtro_especialidad, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_filtro_carrera, fila, 0)
        grid.addWidget(self.combo_filtro_carrera, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Curso:"), fila, 0)
        grid.addWidget(self.combo_curso_filtro, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Sección:"), fila, 0)
        grid.addWidget(self.combo_seccion_filtro, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Estado del caso:"), fila, 0)
        grid.addWidget(self.combo_estado_caso_filtro, fila, 1)
        lay_dialogo.addLayout(grid)

        fila_chips= QHBoxLayout()
        fila_chips.setSpacing(8)
        fila_chips.addWidget(self.chip_destacadas)
        fila_chips.addWidget(self.chip_vencidas)
        fila_chips.addStretch()
        lay_dialogo.addLayout(fila_chips)

        fila_botones= QHBoxLayout()
        btn_limpiar_filtros= QPushButton("Limpiar filtros")
        btn_limpiar_filtros.setIcon(icono_emoji("🧹"))
        btn_limpiar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_filtros.setObjectName("BtnAccionNeutro")
        btn_limpiar_filtros.clicked.connect(self._limpiar_filtros)
        fila_botones.addWidget(btn_limpiar_filtros)
        fila_botones.addStretch()
        btn_cerrar_filtros= QPushButton("Cerrar")
        btn_cerrar_filtros.setIcon(icono_emoji("✖"))
        btn_cerrar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar_filtros.setObjectName("BtnAccionNeutro")
        btn_cerrar_filtros.clicked.connect(self.dialogo_filtros.hide)
        fila_botones.addWidget(btn_cerrar_filtros)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros.parent() is not _fc:
            self.dialogo_filtros.setParent(_fc)
        self.dialogo_filtros.show()
        self.dialogo_filtros.raise_()
        self.dialogo_filtros.activateWindow()

    #FORMULARIO
    #Menú de clic derecho sobre el campo 'Próxima cita': su única
    #opción de momento es volver a 'Sin próxima cita' (equivalente a
    #dejar el campo en su valor mínimo, que es como se guarda un
    #proxima_cita= None). Se deja como menú -en vez de un botón "x" fijo
    #siempre visible- para no añadir otro elemento más a una fila que ya
    #tiene bastante; si en el futuro se necesitan más acciones aquí, este
    #es el lugar natural para sumarlas.
    def _menu_contextual_proxima_cita(self, posicion):

        tiene_cita= (self.fecha_proxima_cita_form.date()
                      != self.fecha_proxima_cita_form.minimumDate())
        menu= QMenu(self.fecha_proxima_cita_form)
        accion_quitar= QAction("Quitar próxima cita", menu)
        accion_quitar.setEnabled(tiene_cita)
        accion_quitar.triggered.connect(
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            lambda: self.fecha_proxima_cita_form.setDate(self.fecha_proxima_cita_form.minimumDate()))
        menu.addAction(accion_quitar)
        menu.exec(self.fecha_proxima_cita_form.mapToGlobal(posicion))

    #Igual que `_cargar_especialidades_combo_filtro`, pero para el combo
    #del formulario de alta/edición: solo se muestra si la institución
    #tiene el módulo Politécnico activo.
    def _cargar_areas_tecnicas_combo_form(self):

        combo= self.combo_area_tecnica_form
        es_poli= self._es_politecnico()
        self.bloque_area_tecnica_form.setVisible(es_poli)
        if not es_poli:
            return
        actual= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todas las áreas técnicas", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Igual que `_cargar_carreras_combo_filtro`, pero para el combo del
    #formulario de alta/edición: solo se muestra si la institución tiene
    #el módulo Universidad activo.
    def _cargar_carreras_combo_form(self):

        combo= self.combo_carrera_form
        es_uni= self._es_universidad()
        self.bloque_carrera_form.setVisible(es_uni)
        if not es_uni:
            return
        actual= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todas las carreras", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _poblar_estudiantes_form(self):

        seccion_id= self.combo_seccion_form.currentData()
        self.combo_estudiante_form.clear()
        if seccion_id is None:
            self.combo_estudiante_form.addItem("Selecciona primero una sección…", None)
            return
        condiciones= ["seccion_id=?", "estado='Activo'"]
        parametros= [seccion_id]
        #Filtro adicional opcional por área técnica/carrera -mismos campos que usa la ficha del estudiante
        #(estudiantes.especialidad_id / estudiantes.carrera_id)-, solo si el combo correspondiente está
        #visible (institución Politécnico/Universidad) y con una opción
        #puntual seleccionada (no "Todas las...").
        area_id= self.combo_area_tecnica_form.currentData() if self._es_politecnico() else None
        if area_id is not None:
            condiciones.append("especialidad_id=?")
            parametros.append(area_id)
        carrera_id= self.combo_carrera_form.currentData() if self._es_universidad() else None
        if carrera_id is not None:
            condiciones.append("carrera_id=?")
            parametros.append(carrera_id)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""SELECT id, nombre, apellidos FROM estudiantes WHERE {' AND '.join(condiciones)}
                     ORDER BY apellidos, nombre""", parametros)
        filas= c.fetchall()
        conn.close()
        if not filas:
            self.combo_estudiante_form.addItem("Sin estudiantes activos en esta sección", None)
        for fila in filas:
            self.combo_estudiante_form.addItem(f"{fila['nombre']} {fila['apellidos']}", fila["id"])

    #Resetea los campos a un estado 'nuevo, en blanco', SIN decidir si
    #el panel debe quedar expandido o colapsado -eso lo decide quien
    #llame a este método-. Se reutiliza en tres momentos: al abrir el
    #panel para un alta desde cero (`_nuevo`), justo después de guardar
    #(`_guardar` deja el panel ABIERTO para poder cargar varios registros
    #seguidos sin reabrirlo cada vez -mismo comportamiento que
    #`observaciones._limpiar`-) y al cancelar/cerrar (`_cerrar_formulario`).
    def _limpiar_formulario(self):

        self.registro_en_edicion= None
        self._cargar_areas_tecnicas_combo_form()
        self._cargar_carreras_combo_form()
        self.combo_curso_form.setCurrentIndex(0)
        cascada_seccion_por_curso(self.combo_curso_form, self.combo_seccion_form, incluir_todas=False)
        self.segmentado_naturaleza.establecer_valor("Informativa", animar=False)
        self.segmentado_estado.establecer_valor("Abierto", animar=False)
        self.fecha_proxima_cita_form.setDate(self.fecha_proxima_cita_form.minimumDate())
        self.chk_destacada_form.setChecked(False)
        for chip in self._chips_categorias.values():
            chip.establecer_marcado(False, animar=False, emitir=False)
        self.txt_descripcion_form.clear()
        desactivar_modo_edicion(self.combo_estudiante_form)

    #Abre el panel colapsable en blanco. Ya no hay un botón visible
    #para esto -la propia cabecera '+ Nuevo registro de Psicología' hace
    #de botón-, pero el método se conserva para el atajo Ctrl+N.
    def _nuevo(self):

        if getattr(self, "_bloqueado", True):
            return
        self._limpiar_formulario()
        self.panel_formulario.expandir(True)
        self.combo_estudiante_form.setFocus()

    def _cargar_seleccionada_en_formulario(self):

        id_reg= self._fila_id_seleccionada()
        if id_reg is None:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT psicologia.*, estudiantes.seccion_id as seccion_id
                     FROM psicologia JOIN estudiantes ON psicologia.estudiante_id = estudiantes.id
                     WHERE psicologia.id=?""", (id_reg,))
        fila= c.fetchone()
        conn.close()
        if not fila:
            return
        self.registro_en_edicion= id_reg
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT grado_id FROM secciones WHERE id=?", (fila["seccion_id"],))
        fila_sec= c.fetchone()
        conn.close()
        idx_curso= self.combo_curso_form.findData(fila_sec["grado_id"] if fila_sec else None)
        self.combo_curso_form.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
        cascada_seccion_por_curso(self.combo_curso_form, self.combo_seccion_form, incluir_todas=False)
        idx_sec= self.combo_seccion_form.findData(fila["seccion_id"])
        self.combo_seccion_form.setCurrentIndex(idx_sec if idx_sec >= 0 else 0)
        self._poblar_estudiantes_form()
        idx_est= self.combo_estudiante_form.findData(fila["estudiante_id"])
        self.combo_estudiante_form.setCurrentIndex(idx_est if idx_est >= 0 else 0)
        self.segmentado_naturaleza.establecer_valor(fila["naturaleza"] or "Informativa", animar=False)
        self.segmentado_estado.establecer_valor(fila["estado_caso"] or "Abierto", animar=False)
        if fila["proxima_cita"]:
            self.fecha_proxima_cita_form.setDate(QDate.fromString(fila["proxima_cita"], "yyyy-MM-dd"))
        else:
            self.fecha_proxima_cita_form.setDate(self.fecha_proxima_cita_form.minimumDate())
        self.chk_destacada_form.setChecked(bool(fila["destacada"]))
        claves_activas= set((fila["categorias"] or "").split(","))
        for clave, chip in self._chips_categorias.items():
            chip.establecer_marcado(clave in claves_activas, animar=False, emitir=False)
        self.txt_descripcion_form.setPlainText(fila["texto"] or "")
        #activar_modo_edicion se encarga de: (1) expandir este panel si estaba colapsado -ver
        #PanelDesplegable.expandir/_expandido más arriba-, (2) mostrar el banner "Editando: ..." y (3) desplazar la
        #vista hasta el formulario. Es la misma infraestructura compartida que ya usan Observaciones/Profesores/etc.
        activar_modo_edicion(self.combo_estudiante_form, f"Editando registro de "
                              f"{self.combo_estudiante_form.currentText()}")

    #Cancela y CIERRA el panel (a diferencia de `_limpiar_formulario`,
    #que solo vacía los campos y deja que quien llame decida si
    #colapsar). Es lo que dispara el botón 'Cancelar' del formulario.
    def _cerrar_formulario(self):

        self._limpiar_formulario()
        self.panel_formulario.expandir(False)

    def _guardar(self):

        if getattr(self, "_bloqueado", True):
            return
        estudiante_id= self.combo_estudiante_form.currentData()
        if estudiante_id is None:
            self.tarjeta_form.destello("#EF4444")
            mostrar_mensaje("advertencia", "Falta el estudiante", "Selecciona un curso, sección y estudiante.", self)
            return
        texto= self.txt_descripcion_form.toPlainText().strip()
        if not texto:
            self.tarjeta_form.destello("#EF4444")
            mostrar_mensaje("advertencia", "Falta la descripción", "Escribe una nota o descripción del caso.", self)
            return
        naturaleza= self.segmentado_naturaleza.valor()
        estado_caso= self.segmentado_estado.valor()
        categorias= ",".join(clave for clave, chip in self._chips_categorias.items() if chip.esta_marcado())
        proxima_cita= (self.fecha_proxima_cita_form.date().toString("yyyy-MM-dd")
                         if self.fecha_proxima_cita_form.date() != self.fecha_proxima_cita_form.minimumDate() else None)
        destacada= 1 if self.chk_destacada_form.isChecked() else 0
        id_usuario= getattr(self.main_window, "id_usuario_actual", None) if self.main_window else None

        conn= obtener_conexion()
        c= conn.cursor()
        if self.registro_en_edicion is None:
            c.execute("""INSERT INTO psicologia (estudiante_id, psicologo_usuario_id, fecha, naturaleza,
                         categorias, texto, destacada, confidencial, proxima_cita, estado_caso)
                         VALUES (?,?,?,?,?,?,?,1,?,?)""",
                      (estudiante_id, id_usuario, date.today().strftime("%Y-%m-%d"), naturaleza,
                       categorias, texto, destacada, proxima_cita, estado_caso))
            accion= "Creó un registro de Psicología"
        else:
            c.execute("""UPDATE psicologia SET naturaleza=?, categorias=?, texto=?, destacada=?,
                         proxima_cita= ?, estado_caso=? WHERE id=?""",
                      (naturaleza, categorias, texto, destacada, proxima_cita, estado_caso,
                       self.registro_en_edicion))
            accion= "Editó un registro de Psicología"
        conn.commit()
        conn.close()
        registrar_auditoria("Psicología", accion,
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             f"Estudiante ID {estudiante_id}")
        self.tarjeta_form.destello("#22C55E")
        #A diferencia de antes (que cerraba/colapsaba el panel tras guardar), ahora se deja ABIERTO y solo se vacían
        #los campos: si el psicólogo tiene que registrar varias notas seguidas (por ejemplo, de varios estudiantes de
        #una misma sesión grupal) no tiene que reabrir el panel cada vez -mismo comportamiento que observaciones.py-.
        self._limpiar_formulario()
        self._refrescar()
        mostrar_mensaje("exito", "Guardado", "El registro se guardó correctamente.", self)

    #Ver detalle / ELIMINAR / DESHACER
    def _ver_detalle(self):

        id_reg= self._fila_id_seleccionada()
        if id_reg is None:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT psicologia.*, estudiantes.nombre as est_nombre, estudiantes.apellidos as est_apellidos,
                     estudiantes.foto as est_foto,
                     secciones.nombre as seccion_nombre, grados.nombre as grado_nombre,
                     especialidades.nombre as area_nombre, carreras.nombre as carrera_nombre
                     FROM psicologia
                     JOIN estudiantes ON psicologia.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN especialidades ON estudiantes.especialidad_id = especialidades.id
                     LEFT JOIN carreras ON estudiantes.carrera_id = carreras.id
                     WHERE psicologia.id=?""", (id_reg,))
        fila= c.fetchone()
        conn.close()
        if not fila:
            return
        campos= [
            ("Estudiante", f"{fila['est_nombre']} {fila['est_apellidos']}"),
            ("Curso", _texto_curso_completo(fila)),
            ("Fecha", formatear_fecha(fila["fecha"], self.main_window)),
            ("Naturaleza", fila["naturaleza"] or "—"),
            ("Categorías", _texto_categorias(fila["categorias"])),
            ("Estado del caso", fila["estado_caso"] or "—"),
            ("Próxima cita", formatear_fecha(fila["proxima_cita"], self.main_window)
                if fila["proxima_cita"] else "Sin próxima cita"),
            ("Destacado", "Sí" if fila["destacada"] else "No"),
        ]
        titulo= f"{fila['est_nombre']} {fila['est_apellidos']} — Expediente de Psicología"
        texto_completo= (fila["texto"] or "").strip()
        extra_botones= [("Ver nota completa",
                           #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                           lambda: mostrar_texto_largo(self, "Nota / descripción del caso", texto_completo))]
        #Misma fotografía del estudiante que muestra Estudiantes.py -en grande, arriba del detalle-, para reconocerlo
        #de un vistazo al revisar el expediente (ver DialogoDetalleRegistro.foto_path en paginacion.py, que ya sabe
        #recortarla en círculo con anillo de acento y no dibuja nada si el estudiante no tiene foto cargada).
        mostrar_detalle_campos(self, titulo, campos, extra_botones=extra_botones, foto_path=fila["est_foto"])

    def _eliminar_seleccionada(self):

        if getattr(self, "_bloqueado", True):
            return
        id_reg= self._fila_id_seleccionada()
        if id_reg is None:
            return
        respuesta= mostrar_mensaje("pregunta", "Eliminar registro",
                                     "¿Eliminar este registro de Psicología? Podrás deshacerlo con el botón "
                                     "'Deshacer eliminación' mientras no cierres el módulo.", self)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        fila_completa= c.execute("SELECT * FROM psicologia WHERE id=?", (id_reg,)).fetchone()
        if fila_completa is None:
            conn.close()
            return
        datos_respaldo= dict(fila_completa)
        c.execute("DELETE FROM psicologia WHERE id=?", (id_reg,))
        conn.commit()
        conn.close()
        registrar_auditoria("Psicología", "Eliminó un registro de Psicología",
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             f"Registro ID {id_reg}")
        #Se conserva UN nivel de deshacer (la última eliminación), igual que Profesores/Estudiantes -particularmente
        #valioso aquí, porque una nota de Psicología borrada por error es información sensible que no debería perderse
        #sin una segunda oportunidad-.
        self._ultimo_eliminado= datos_respaldo
        self.btn_deshacer.setVisible(True)
        self.btn_deshacer.setEnabled(True)
        self._refrescar()

    def _deshacer_eliminacion(self):

        if not self._ultimo_eliminado:
            return
        datos= self._ultimo_eliminado
        columnas= list(datos.keys())
        marcadores= ",".join("?" for _ in columnas)
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute(f"INSERT INTO psicologia ({','.join(columnas)}) VALUES ({marcadores})",
                      [datos[col] for col in columnas])
            conn.commit()
        except Exception as error:
            conn.rollback()
            conn.close()
            mostrar_mensaje("error", "No se pudo deshacer",
                             f"No fue posible restaurar el registro (puede que ya exista uno con "
                             f"algún conflicto): {error}", self)
            return
        conn.close()
        registrar_auditoria("Psicología", "Deshizo eliminación de un registro de Psicología",
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             f"Registro ID {datos.get('id')}")
        self._ultimo_eliminado= None
        self.btn_deshacer.setVisible(False)
        mostrar_mensaje("info", "Restaurado", "El registro fue restaurado correctamente.", self)
        self._refrescar()
