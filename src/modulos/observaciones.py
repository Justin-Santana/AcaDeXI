#Observaciones de AcaDeXI.
#
#Rediseño del módulo (v2 — alineado al lenguaje visual real del resto de la
#app: cabecera tipo héroe, `TarjetaFiltros` de una sola fila, confirmación por
#destello de color en vez de notificaciones flotantes, sin tarjetas KPI).
#
#Modelo de datos:
#- El antiguo campo único "tipo" (Positiva/Negativa/Neutra/Académica/Conductual,
#con un par ambiguo) se reemplaza por dos dimensiones independientes:
#`naturaleza` (cómo fue: Positiva/Informativa/Negativa) y `categorías` (de
#qué trata: rendimiento, conducta, tareas... pueden combinarse varias).
#- El profesor escribe primero la descripción; el sistema sugiere categorías
#por palabras clave (chips dinámicos).
#- Categorías como "Problema disciplinario", "Requiere seguimiento" o
#"Comunicación con padres" marcan la observación como destacada.
#
#Se mantiene el RBAC exacto (gerencial vs. profesor restringido a sus
#secciones, permisos de edición/eliminación por autor).
import unicodedata
import re
from datetime import datetime, date, timedelta
from src.nucleo.formato_hora import formatear_hora, formatear_fecha

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QGridLayout, QTextEdit, QScrollArea, QFrame, QMessageBox, QSizePolicy, QLayout,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QDialog, QDialogButtonBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractScrollArea,
)
from PySide6.QtCore import (
    Qt, QTimer, QRect, QRectF, QPoint, QPointF, QSize, Signal, Property,
    QPropertyAnimation, QEasingCurve, QVariantAnimation,
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath

from src.nucleo.bd import obtener_conexion, registrar_auditoria, mostrar_columna_numero_lista
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso, preseleccionar_curso_y_seccion,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo, interseccion_opcional)
from src.nucleo.iconos import mostrar_mensaje, centrar_y_al_frente, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.modulos.calendario import PanelDesplegable
from src.nucleo.permisos import (tiene_acceso_gerencial, es_profesor_restringido,
                       obtener_profesor_id, obtener_secciones_permitidas, obtener_materias_permitidas)
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         tabla_pausada, mostrar_detalle_campos, mostrar_texto_largo,
                         agregar_boton_pantalla_completa)
from src.interfaz.configuracion import es_sistema_dominicano, resolver_nota_minima, conectar_tooltip_seleccion
from src.modulos.calificaciones import (competencias_de_materia_grado, grado_de_estudiante,
                             calcular_nota_final, _nivel_desde_nota, _sistema_calificacion_actual)
from src.modulos.calificaciones_tecnicas import DialogoAjusteRA, guardar_ajuste_ra
from src.modulos.banco_tareas import DialogoAjusteEntrega, guardar_ajuste_entrega, _hay_tareas_activas_en_materia
from src.modulos.materias import MODELO_EVALUACION_TECNICA
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, quitar_emojis_texto,
                          icono_boton_filtro, pixmap_boton_filtro)
from src.nucleo.iconos_categorias import icono_categoria, pixmap_categoria, pixmap_categoria_color, icono_categoria_color


#Catálogo: naturaleza + CATEGORÍAS (clave, color) -el icono real de cada naturaleza es un icono vectorial
#MULTICOLOR (ver iconos_categorias.py: pixmap_categoria_color), no un
#emoji de texto; por eso esta lista ya no guarda ningún emoji.
NATURALEZAS= [
    ("Positiva", "#10B981"),
    ("Informativa", "#64748B"),
    ("Negativa", "#EF4444"),
]
_COLOR_NATURALEZA= {clave: color for clave, color in NATURALEZAS}

#(clave, etiqueta, palabras clave para sugerencia automática) -el icono real es un icono vectorial MULTICOLOR
#(ver iconos_categorias.py), no un emoji. IMPORTANTE — "buena_conducta" vs "conducta": ambas claves se
#mantienen tal
#cual (se referencian por clave en la base de datos, no por etiqueta), pero
#sus palabras clave y etiquetas se separaron para que no se solapen. Antes "conducta" usaba la palabra genérica
#"conducta"/"comportamiento" como gatillo, y esa misma palabra aparece DENTRO de "buena conducta", así que
#escribir "buena conducta" sugería a la vez "Buena conducta" (correcto) y "Conducta" (incorrecto, por el
#solapamiento de substring). Ahora cada una exige su propia frase completa ("buena conducta"/"buen
#comportamiento" vs. "mala conducta"/"mal comportamiento") y las etiquetas quedan inequívocas.
CATEGORIAS= [
    ("rendimiento", "Rendimiento académico", ["rendimiento", "buena nota", "buenas notas", "mala nota",
                                               "malas notas", "calificaci", "sobresaliente", "desempeñ", "desempen"]),
    ("tareas", "Tareas", ["tarea", "no entreg", "sin entregar", "entreg"]),
    ("participacion", "Participación", ["particip", "interv"]),
    ("comprension", "Comprensión del tema", ["comprend", "entiende", "entender", "dificultad para entender"]),
    ("esfuerzo", "Esfuerzo y dedicación", ["esfuerzo", "dedicaci", "empeñ", "empen"]),
    ("equipo", "Trabajo en equipo", ["equipo", "compañer", "companer", "grupo", "colabora"]),
    ("buena_conducta", "Buena conducta", ["buena conducta", "buen comportamiento", "respetuos", "educad",
                                           "conducta ejemplar", "comportamiento ejemplar"]),
    ("conducta", "Conducta inadecuada", ["mala conducta", "mal comportamiento", "comportamiento inadecuado",
                                          "indisciplin", "pele", "interrump", "irrespet", "falta de respeto"]),
    ("conflicto", "Conflicto entre estudiantes", ["conflicto con", "conflicto entre", "discusion con",
                                                   "discusión con", "se pelearon", "altercado"]),
    ("puntualidad", "Puntualidad", ["puntual", "llegada tarde", "llegó tarde", "llego tarde"]),
    ("asistencia", "Asistencia", ["asistencia", "ausen", "falta a clase", "inasisten"]),
    ("actitud", "Actitud y motivación", ["actitud", "motivaci", "ánimo", "animo"]),
    ("bienestar", "Bienestar emocional", ["triste", "ansios", "estres", "estrés", "llor", "desanimad",
                                           "preocupad", "angusti"]),
    ("mejora", "Mejoría notable", ["mejoria notable", "mejoría notable", "mejoró mucho", "mejoro mucho",
                                   "gran progreso", "avance notable", "superación", "superacion"]),
    ("reconocimiento", "Reconocimiento / logro", ["reconocimiento", "logro", "premio", "destaca"]),
    ("comunicacion_padres", "Comunicación con padres", ["padres", "tutor", "acudiente", "llamar a casa"]),
    ("seguimiento", "Requiere seguimiento", ["seguimiento", "monitor", "vigilar"]),
    ("disciplinario", "Problema disciplinario grave", ["disciplinari", "sanci", "expulsi", "suspensi"]),
]
CATEGORIAS_POR_CLAVE= {clave: (clave, etiqueta, palabras) for clave, etiqueta, palabras in CATEGORIAS}

#Color de acento de cada categoría -usado para su icono vectorial en los chips de filtro Y en la columna
#"Categorías" de la tabla (ver iconos_categorias.py). Agrupados por tono: verdes para lo positivo, rojos para
#lo que requiere atención, y colores neutros/informativos para el resto.
COLOR_CATEGORIA= {
    "rendimiento": "#3B82F6",
    "tareas": "#8B5CF6",
    "participacion": "#0EA5E9",
    "comprension": "#F59E0B",
    "esfuerzo": "#F97316",
    "equipo": "#14B8A6",
    "buena_conducta": "#22C55E",
    "conducta": "#EF4444",
    "conflicto": "#EF4444",
    "puntualidad": "#F59E0B",
    "asistencia": "#22C55E",
    "actitud": "#6366F1",
    "bienestar": "#EC4899",
    "mejora": "#22C55E",
    "reconocimiento": "#CA8A04",
    "comunicacion_padres": "#0EA5E9",
    "seguimiento": "#64748B",
    "disciplinario": "#DC2626",
}
CLAVES_DESTACADAS= {"disciplinario", "seguimiento", "comunicacion_padres"}
MAX_SUGERENCIAS= 4  #tope de chips en la franja de sugerencias, para que no crezca sin control

#(título, naturaleza sugerida, categorías sugeridas, cuerpo — se antepone el nombre del estudiante
#seleccionado, o "El/la estudiante" si no hay ninguno)
PLANTILLAS= [
    ("Excelente desempeño", "Positiva", ["rendimiento", "reconocimiento"],
     "ha demostrado un rendimiento sobresaliente durante las últimas semanas, mostrando dominio de los "
     "temas y gran disposición para aprender."),
    ("Trabajo en equipo destacado", "Positiva", ["equipo", "participacion"],
     "trabaja muy bien en equipo, colabora activamente con sus compañeros y aporta al logro de los "
     "objetivos grupales."),
    ("Excelente participación", "Positiva", ["participacion", "esfuerzo"],
     "participa activamente en clase, aporta ideas valiosas y motiva a sus compañeros."),
    ("Incumplimiento de tareas", "Negativa", ["tareas", "seguimiento"],
     "no ha entregado las tareas asignadas en las últimas sesiones. Se recomienda dar seguimiento cercano."),
    ("Llegadas tardías", "Negativa", ["puntualidad", "asistencia"],
     "ha llegado tarde a clases de forma reiterada, lo que afecta su desempeño y concentración."),
    ("Problema disciplinario", "Negativa", ["conducta", "disciplinario"],
     "protagonizó un incidente de conducta que requiere la atención de Dirección/Coordinación."),
    ("Requiere reforzamiento", "Informativa", ["comprension", "seguimiento"],
     "muestra dificultades para comprender algunos temas de la materia y necesita reforzamiento adicional."),
    ("Mejoría notable", "Positiva", ["mejora", "esfuerzo"],
     "ha mostrado una mejoría notable en su desempeño y actitud durante las últimas semanas, resultado de un "
     "esfuerzo constante."),
    ("Ausencias reiteradas", "Negativa", ["asistencia", "seguimiento"],
     "ha faltado a clases de forma reiterada sin justificación, lo que está afectando su continuidad académica."),
    ("Conflicto con compañeros", "Negativa", ["conflicto", "conducta"],
     "estuvo involucrado(a) en un conflicto con compañeros de clase que fue necesario mediar de inmediato."),
    ("Bienestar emocional", "Informativa", ["bienestar", "seguimiento"],
     "mostró señales de tristeza/ansiedad durante la clase. Se recomienda dar seguimiento cercano y, de ser "
     "necesario, coordinar con la familia."),
]

_DIAS_SEMANA= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_MESES= ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_MESES_LARGO= ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica. Cada módulo de AcaDeXI mantiene su propia
#copia pequeña de estas (mismo criterio que estudiantes.py / profesores.py / asistencia.py) en vez de importar
#entre módulos de funcionalidad.
def _hex_a_rgba(color_hex, alpha):

    color_hex= (color_hex or "#2563EB").lstrip("#")
    if len(color_hex) < 6:
        color_hex= "2563EB"
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Lee la paleta/tema activo de la ventana principal para que las tarjetas de
#este módulo respeten el tema y el modo claro/oscuro que el usuario ya eligió
#(mismo helper que estudiantes.py / profesores.py, con el añadido de
#'txt_prim' que ya usa configuracion.py para textos sobre fondos propios).
def _colores_tema(main_window):

    try:

        paleta= main_window.theme_palettes[main_window.tema_actual]
        idx= 1 if getattr(main_window, "modo_oscuro", False) else 0
        return {
            "bg_panel": paleta["display_bg"][idx],
            "bg_btn": paleta["btn_num_bg"][idx],
            "txt_prim": paleta["text_primary"][idx],
            "txt_sec": paleta["text_secondary"][idx],
            "accent": paleta["btn_op_bg"][idx],
            "accent_hv": paleta["btn_op_hover"][idx],
        }
    except Exception:
        return {"bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0", "txt_prim": "#0F172A", "txt_sec": "#64748B",
                "accent": "#2563EB", "accent_hv": "#1D4ED8"}


#Quita mayúsculas y acentos para búsqueda/coincidencia no estricta
#(mismo criterio que horario.py / configuracion.py / estudiantes.py).
def _normalizar(texto):

    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


#True si `palabra_normalizada` aparece en `texto_normalizado` empezando
#en un límite de palabra real, no en medio de otra palabra. Antes se
#usaba un simple `in` (substring), lo que producía falsos positivos como
#la clave "nota" (Rendimiento académico) disparándose dentro de "mejoría
#noTAble", o "deber" (Tareas) dentro de "de-BER-ía". Solo se exige el
#límite al INICIO, no al final: varias claves son raíces a propósito
#(p. ej. "desempeñ" para que combine con "desempeño"/"desempeña", o
#"sanci" con "sanción"/"sancionado"), y exigir también el límite final
#rompería esa coincidencia intencional por sufijo.
def _contiene_palabra(texto_normalizado, palabra_normalizada):

    patron= r"(?<!\w)" + re.escape(palabra_normalizada)
    return re.search(patron, texto_normalizado) is not None


#'Hoy · 9:41 AM', 'Ayer · 3:10 PM', 'Martes · 8:00 AM' o, para fechas de
#hace una semana o más, la fecha completa en el formato elegido en
#Configuración ▸ Apariencia (dd/mm/aaaa, mm/dd/aaaa, aaaa-mm-dd o texto
#largo) en vez de un formato de mes fijo. La hora respeta igual el
#formato de 12h/24h configurado.
def _fecha_relativa(fecha_str, main_window=None):

    try:

        dt= datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return fecha_str or ""
    hoy= date.today()
    d= dt.date()
    hora= formatear_hora(dt.strftime("%H:%M"), main_window)
    if d == hoy:
        return f"Hoy · {hora}"
    if d == hoy - timedelta(days=1):
        return f"Ayer · {hora}"
    if 0 < (hoy - d).days < 7:
        return f"{_DIAS_SEMANA[d.weekday()]} · {hora}"
    return formatear_fecha(dt.strftime("%Y-%m-%d"), main_window)


#Solo la hora (respetando 12h/24h de Configuración), para mostrar en el
#detalle de una observación junto a la fecha relativa — que para fechas
#antiguas ya no incluye la hora. No se usa en la tabla visual.
def _hora_exacta(fecha_str, main_window=None):

    try:

        dt= datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "—"
    return formatear_hora(dt.strftime("%H:%M"), main_window)



#Fundido de entrada (fade-in) reutilizable — mismo patrón que
#asistencia.py para el contenido general del módulo.
def _animar_aparicion(widget, duracion=280):

    efecto= QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(efecto)
    anim= QPropertyAnimation(efecto, b"opacity", widget)
    anim.setDuration(duracion)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._anim_aparicion_ref= anim  #evita que el GC la recolecte a mitad de camino
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start()


#Layout de flujo: envuelve los chips a la siguiente línea según el ancho
#disponible. Recalcula posiciones sin recrear widgets.
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

    def itemAt(self, index):

        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):

        return self._items.pop(index) if 0 <= index < len(self._items) else None

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
#Icono de lupa dibujado a mano con QPainter (mismo diseño exacto que el
#resto de barras de búsqueda de AcaDeXI: horario.py, estudiantes.py,
#profesores.py, configuracion.py, asistencia.py).
class IconoLupa(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(17, 17)
        self._color= "#64748B"

    def establecer_color(self, color):

        self._color= color
        self.update()

    def paintEvent(self, event):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen= QPen(QColor(self._color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1.5, 1.5, 9.5, 9.5))
        painter.drawLine(QPointF(9.7, 9.7), QPointF(15, 15))


#QLabel numérica que anima el conteo ('odómetro') al cambiar de valor.
#Mismo widget que asistencia.py, con plantilla de texto configurable.
class ContadorAnimado(QLabel):

    def __init__(self, plantilla_texto=None, parent=None):

        super().__init__(parent)
        self._valor= 0
        self._valor_objetivo= 0
        self._plantilla= plantilla_texto or (lambda v: str(v))
        self._animacion= QPropertyAnimation(self, b"valorAnimado", self)
        self._animacion.setDuration(480)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._refrescar_texto()

    def _obtener_valor(self):

        return self._valor

    def _fijar_valor(self, valor):

        self._valor= valor
        self._refrescar_texto()

    valorAnimado= Property(int, _obtener_valor, _fijar_valor)

    def _refrescar_texto(self):

        self.setText(self._plantilla(self._valor))

    def establecer(self, valor):

        #Se compara contra el ÚLTIMO VALOR OBJETIVO pedido, no contra el valor instantáneo a medio animar (si no, una
        #animación en curso podría "pasar" por el nuevo valor pedido a mitad de camino y esta función abandonaría
        #dejándola terminar en el valor viejo).
        if self._valor_objetivo == valor:
            return
        self._valor_objetivo= valor
        self._animacion.stop()
        self._animacion.setStartValue(self._valor)
        self._animacion.setEndValue(valor)
        self._animacion.start()


#Contenedor tipo tarjeta liviano: fondo translúcido neutro + borde
#redondeado (sin QGraphicsDropShadowEffect permanente — ese look ya se
#consigue de forma nativa y prácticamente gratis; ver materias.py). Solo el
#panel principal de un módulo (el formulario) pide sombra explícita, para
#poder animar un destello de color como confirmación de guardado.
class TarjetaPanel(QFrame):

    def __init__(self, titulo="", con_sombra=False, parent=None):

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
        raiz.setContentsMargins(18, 16, 18, 16)
        raiz.setSpacing(10)

        self.lbl_titulo= None
        if titulo:
            self.lbl_titulo= QLabel(titulo)
            self.lbl_titulo.setObjectName("TituloTarjetaInterna")
            raiz.addWidget(self.lbl_titulo)

        self.contenido= QVBoxLayout()
        self.contenido.setSpacing(10)
        raiz.addLayout(self.contenido)

    #Resplandor breve de color en el borde de la tarjeta, a modo de
    #confirmación visual (verde=éxito, ámbar=aviso). Requiere con_sombra=True.
    def destello(self, color_hex="#22C55E"):

        if self._sombra is None:
            return
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
        anim_color.start()
        anim_blur.start()
        self._anim_destello= (anim_color, anim_blur)

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


#Pastilla seleccionable con transición de color animada y una onda
#('ripple') pintada a mano con QPainter al pulsar. Se usa para elegir
#categorías, para los filtros y para la naturaleza.
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
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        lay= QHBoxLayout(self)
        lay.setContentsMargins(12, 5, 13, 5)
        lay.setSpacing(6)
        self.lbl_icono= QLabel()
        self.lbl_icono.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_icono.setFixedSize(16, 16)
        lay.addWidget(self.lbl_icono)
        self.lbl= QLabel()
        self.lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        f= self.lbl.font()
        f.setPointSize(10)
        f.setBold(True)
        self.lbl.setFont(f)
        lay.addWidget(self.lbl)
        self._actualizar_texto()

        self._anim= QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._actualizar_estilo()

    def _on_anim(self, valor):

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

    #Opcional: agrega un '(N)' al final del texto del chip — se usa en
    #los chips de naturaleza para mostrar cuántas observaciones hay de cada
    #tipo sin necesitar una fila de tarjetas KPI aparte.
    def establecer_contador(self, n):

        self._actualizar_texto(n)

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:
            self._agregar_ripple(event.position())
            self.establecer_marcado(not self._marcado)
        super().mousePressEvent(event)

    def enterEvent(self, event):

        self._hover= True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):

        self._hover= False
        self.update()
        super().leaveEvent(event)

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
        r= base.red() + (self._color_activo.red() - base.red()) * t
        g= base.green() + (self._color_activo.green() - base.green()) * t
        b= base.blue() + (self._color_activo.blue() - base.blue()) * t
        a= base.alpha() + (255 - base.alpha()) * t
        return QColor(int(r), int(g), int(b), int(a))

    def establecer_paleta(self, bg_inactivo, borde_inactivo, texto_inactivo):

        self._color_inactivo_bg= QColor(bg_inactivo)
        self._color_borde_inactivo= QColor(borde_inactivo)
        self._color_texto_inactivo= QColor(texto_inactivo)
        self._actualizar_estilo()

    def _actualizar_texto(self, n=None):

        sufijo= f"  ({n})" if n else ""
        self.lbl.setText(f"{self._texto_base}{sufijo}")
        self.updateGeometry()

    def _actualizar_estilo(self):

        color_texto= "white" if self._factor > 0.5 else self._color_texto_inactivo.name()
        self.lbl.setStyleSheet(f"background: transparent; color: {color_texto};")
        #El icono cambia de color EXACTAMENTE igual que el texto (blanco cuando el chip está marcado/activo, gris
        #cuando no), así se ve tan "apagado" o "encendido" como el resto de la pastilla -ver iconos_categorias.py,
        #hecho a propósito para esto-.
        self.lbl_icono.setPixmap(pixmap_categoria(self.clave, color_texto, 16))
        self.update()

    def paintEvent(self, event):

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
                r= radio_max * progreso
                alpha= max(0, int(90 * (1 - progreso)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, alpha))
                painter.drawEllipse(punto, r, r)


#Selector de naturaleza (🟢 Positiva / ⚪ Informativa / 🔴 Negativa) en
#forma de píldora deslizante, coloreada según la opción activa.
class SegmentadoNaturaleza(QWidget):

    cambiado= Signal(str)

    def __init__(self, parent=None):

        super().__init__(parent)
        self._valor= "Informativa"
        self.setFixedHeight(42)
        self.setMinimumWidth(320)

        self._fondo= QFrame(self)
        self._fondo.setObjectName("SegmentadoFondo")
        self._resaltado= QFrame(self)
        self._resaltado.setObjectName("SegmentadoResaltado")

        lay= QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)
        self._botones= []
        for clave, _color in NATURALEZAS:
            btn= QPushButton(f"  {clave}")
            btn.setIcon(icono_categoria_color(clave, 16))
            btn.setIconSize(QSize(16, 16))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setObjectName("SegmentadoBoton")
            btn.clicked.connect(lambda _=False, k=clave: self.establecer_valor(k))
            lay.addWidget(btn, 1)
            self._botones.append((clave, btn))
        self._botones[1][1].setChecked(True)
        self._resaltado.lower()
        self._fondo.lower()
        QTimer.singleShot(0, lambda: self._reposicionar_resaltado(animar=False))

    def resizeEvent(self, event):

        super().resizeEvent(event)
        self._fondo.setGeometry(self.rect())
        self._reposicionar_resaltado(animar=False)

    def valor(self):

        return self._valor

    def establecer_valor(self, clave, animar=True, emitir=True):

        self._valor= clave
        for k, btn in self._botones:
            btn.setChecked(k == clave)
        self._reposicionar_resaltado(animar=animar)
        color= _COLOR_NATURALEZA.get(clave, "#6366F1")
        self._resaltado.setStyleSheet(f"QFrame#SegmentadoResaltado {{ background-color: {color}; border-radius: 9px; }}")
        if emitir:
            self.cambiado.emit(clave)

    def _reposicionar_resaltado(self, animar=True):

        for k, btn in self._botones:
            if k == self._valor and btn.width() > 0:
                geo= btn.geometry()
                if animar and self._resaltado.isVisible():
                    anim= QPropertyAnimation(self._resaltado, b"geometry", self)
                    anim.setDuration(220)
                    anim.setStartValue(self._resaltado.geometry())
                    anim.setEndValue(geo)
                    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                    self._anim_resaltado= anim
                    anim.start()
                else:
                    self._resaltado.setGeometry(geo)
                break

    def aplicar_paleta(self, bg, borde, txt_sec):

        self._fondo.setStyleSheet(f"QFrame#SegmentadoFondo {{ background-color: {bg}; border: 1px solid {borde}; border-radius: 12px; }}")
        color= _COLOR_NATURALEZA.get(self._valor, "#6366F1")
        self._resaltado.setStyleSheet(f"QFrame#SegmentadoResaltado {{ background-color: {color}; border-radius: 9px; }}")
        for k, btn in self._botones:
            btn.setStyleSheet(f"""
                QPushButton#SegmentadoBoton {{
                    border: none; background: transparent; color: {txt_sec};
                    font-weight: 700; font-size: 11px; padding: 6px;
                }}
                QPushButton#SegmentadoBoton:checked {{ color: white; }}
            """)


#Barra horizontal animada (dibujada con QPainter) para mostrar la
#frecuencia de cada categoría: '[icono] Buena conducta ████████  12'.
class BarraFrecuencia(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._clave= ""
        self._etiqueta= ""
        self._color= QColor("#6366F1")
        self._color_pista= QColor(127, 127, 127, 40)
        self._color_texto= QColor("#64748B")
        self._progreso= 0.0
        self._cantidad= 0
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(480)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):

        self._progreso= v
        self.update()

    def establecer_datos(self, clave, etiqueta, color, cantidad, fraccion):

        self._clave= clave
        self._etiqueta= etiqueta
        self._color= QColor(color)
        self._cantidad= cantidad
        self.setToolTip(etiqueta)  #nombre completo por si el texto se elide (ver paintEvent)
        self._anim.stop()
        self._anim.setStartValue(self._progreso if self.isVisible() else 0.0)
        self._anim.setEndValue(max(0.0, min(1.0, fraccion)))
        self._anim.start()

    def establecer_colores(self, color_texto, color_pista):

        self._color_texto= QColor(color_texto)
        self._color_pista= QColor(color_pista)
        self.update()

    def paintEvent(self, event):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen_izq= 168
        alto_barra= 9
        y= (self.height() - alto_barra) / 2
        ancho_pista= max(10.0, self.width() - margen_izq - 40)
        rect_pista= QRectF(margen_izq, y, ancho_pista, alto_barra)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color_pista)
        painter.drawRoundedRect(rect_pista, alto_barra / 2, alto_barra / 2)
        ancho_lleno= rect_pista.width() * self._progreso
        if ancho_lleno > 1:
            rect_lleno= QRectF(rect_pista.x(), rect_pista.y(), ancho_lleno, alto_barra)
            grad= QLinearGradient(rect_lleno.topLeft(), rect_lleno.topRight())
            grad.setColorAt(0, self._color.lighter(125))
            grad.setColorAt(1, self._color)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(rect_lleno, alto_barra / 2, alto_barra / 2)
        #Icono vectorial MULTICOLOR real (mismo dibujo que la tabla y los chips) en vez del emoji de texto crudo que se
        #dibujaba antes con drawText -esto último dependía de que el sistema operativo tuviera una fuente con ese
        #glifo, con el mismo riesgo de "cuadritos" o inconsistencia entre equipos que motivó todo el sistema de iconos
        #vectoriales del resto de la app.
        if self._clave:
            pix_icono= pixmap_categoria_color(self._clave, 16)
            painter.drawPixmap(QPointF(0, (self.height() - 16) / 2).toPoint(), pix_icono)
        painter.setPen(self._color_texto)
        #Nombres de categoría largos ("Problema disciplinario grave") se recortaban por la IZQUIERDA al quedar
        #alineados a la derecha en un ancho fijo, tapando el inicio del texto detrás/encima del icono (se veía "oblema
        #disciplinario grave" sin la "Pr"). Con elidedText el texto se acorta con "…" ANTES de dibujarse, así que nunca
        #excede el ancho disponible ni se superpone con el icono.
        ancho_disponible_texto= margen_izq - 32
        texto_elidido= painter.fontMetrics().elidedText(
            self._etiqueta, Qt.TextElideMode.ElideRight, ancho_disponible_texto)
        painter.drawText(QRectF(22, 0, ancho_disponible_texto, self.height()),
                          Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                          texto_elidido)
        painter.drawText(QRectF(self.width() - 34, 0, 34, self.height()),
                          Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(self._cantidad))


#Franja de alerta compacta (mismo patrón que banco_tareas.py): solo
#aparece cuando hay algo que atender. Entra/sale animando su altura máxima
#— una propiedad normal de QWidget, no requiere QGraphicsEffect, así que es
#barata y no afecta la fluidez del scroll. Un clic filtra la línea de
#tiempo por destacadas.
class CintaAlerta(QFrame):

    clicada= Signal()

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("CintaAlerta")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)
        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_categoria_color("destacadas", 16))
        lay.addWidget(self.lbl_icono)
        self.lbl_texto= QLabel("")
        lay.addWidget(self.lbl_texto, 1)
        self.lbl_accion= QLabel("Ver ")
        lay.addWidget(self.lbl_accion)

        self._anim= QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._visible_actual= False
        self._color= "#F59E0B"

    def aplicar_paleta(self, color="#F59E0B"):

        self._color= color
        self.setStyleSheet(f"""
            QFrame#CintaAlerta {{
                background-color: {_hex_a_rgba(color, 0.14)};
                border: 1px solid {_hex_a_rgba(color, 0.45)};
                border-radius: 10px;
            }}
        """)
        self.lbl_texto.setStyleSheet(f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {color};")
        self.lbl_accion.setStyleSheet(f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {color};")

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

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit()
        super().mousePressEvent(event)


#Tabla de registros — columnas y helpers de contenido Reemplaza la antigua lista de "tarjetas" (QFrame apiladas
#+ animación de entrada geometry-based) por una QTableWidget real: escalable con muchos registros, con las
#barras de scroll nativas de la tabla en vez de estirar la página, y sin el bugueo visual que sufría la línea
#de tiempo (tarjetas gestionadas por un layout mientras a la vez se les forzaba una geometría animada). El
#lenguaje visual de las tarjetas (icono+color por naturaleza, marca de destacada, categorías como chips) se
#conserva, pero con iconos vectoriales
#MULTICOLOR (ver iconos_categorias.py) en vez de emojis de texto: la
#columna "Tipo" y la columna "Categorías" muestran icono + color + nombre por naturaleza/categoría, y cada fila
#se tiñe suavemente con el color de su naturaleza (ver `_color_fila_qcolor` y `_cargar_tabla`).
COL_ID= 0
COL_NUMERO= 1
COL_TIPO= 2
COL_DESTACADA= 3
COL_ESTUDIANTE= 4
COL_GRADO= 5
COL_SECCION= 6
COL_FECHA= 7
COL_CATEGORIAS= 8
COL_DESCRIPCION= 9
ENCABEZADOS_TABLA= ["ID", "No.", "Tipo", "", "Estudiante", "Curso", "Sección", "Fecha", "Categorías", "Descripción"]


#Igual que `_hex_a_rgba` pero devuelve un QColor real (no un string
#CSS), porque QTableWidgetItem.setBackground necesita un QBrush/QColor:
#es lo que tiñe cada fila de la tabla con el color de su naturaleza.
def _color_fila_qcolor(color_hex, alpha_255):

    color_hex= (color_hex or "#64748B").lstrip("#")
    if len(color_hex) < 6:
        color_hex= "64748B"
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return QColor(r, g, b, alpha_255)


#'Rendimiento académico · Reconocimiento / logro' (o '—' si no tiene
#ninguna). Se usa como texto alternativo -tooltip, diálogo de detalle,
#exportaciones- allí donde no aplica un icono (ver también
#`_widget_categorias_fila`, que es lo que se ve en la tabla).
def _texto_categorias_fila(fila):

    claves= [c for c in (fila["categorias"] or "").split(",") if c]
    partes= []
    for clave in claves:
        info= CATEGORIAS_POR_CLAVE.get(clave)
        if info:
            _c, etiqueta_c, _p= info
            partes.append(etiqueta_c)
    return " · ".join(partes) if partes else "—"


#Fila de icono + ETIQUETA -uno por categoría- para la columna
#"Categorías" de la tabla. Antes solo mostraba el icono (monocromo) y la
#etiqueta quedaba escondida en el tooltip, así que dos categorías con
#forma parecida a tamaño chico eran difíciles de distinguir sin pasar el
#mouse por encima. Ahora cada icono es MULTICOLOR (ver
#`pixmap_categoria_color` en iconos_categorias.py) y va acompañado de su
#nombre corto, visible siempre -el tooltip se conserva solo como refuerzo
#para el nombre completo, no como único lugar donde aparece el texto.
def _widget_categorias_fila(fila, color_texto="#64748B"):

    claves= [c for c in (fila["categorias"] or "").split(",") if c]
    if not claves:
        lbl= QLabel("—")
        lbl.setStyleSheet(f"color: {color_texto};")
        return lbl

    contenedor= QWidget()
    lay= QHBoxLayout(contenedor)
    lay.setContentsMargins(2, 0, 2, 0)
    lay.setSpacing(10)
    etiquetas= []
    for clave in claves:
        info= CATEGORIAS_POR_CLAVE.get(clave)
        if not info:
            continue
        _c, etiqueta_c, _p= info
        grupo= QWidget()
        lay_grupo= QHBoxLayout(grupo)
        lay_grupo.setContentsMargins(0, 0, 0, 0)
        lay_grupo.setSpacing(4)
        lbl_icono= QLabel()
        lbl_icono.setPixmap(pixmap_categoria_color(clave, 17))
        lay_grupo.addWidget(lbl_icono)
        lbl_texto= QLabel()
        lbl_texto.setStyleSheet(f"color: {color_texto}; font-size: 11px;")
        #Con varias categorías largas en una fila angosta, el texto se cortaba a mitad de palabra contra el borde de la
        #celda (sin indicar que seguía habiendo más). Se limita el ancho y se elide con "…"; el tooltip de abajo sigue
        #mostrando el nombre completo.
        lbl_texto.setMaximumWidth(150)
        lbl_texto.setText(lbl_texto.fontMetrics().elidedText(
            etiqueta_c, Qt.TextElideMode.ElideRight, 150))
        lay_grupo.addWidget(lbl_texto)
        grupo.setToolTip(etiqueta_c)
        lay.addWidget(grupo)
        etiquetas.append(etiqueta_c)
    lay.addStretch()
    contenedor.setToolTip(" · ".join(etiquetas))
    return contenedor


#Módulo principal
#Sugerencia pequeña y descartable que aparece justo después de guardar una
#observación: ofrece (sin obligar a nada) sumar o restar puntos en la
#competencia que el docente elija, coherente con lo que acaba de registrar.
#Se anima igual que CintaAlerta, para no interrumpir el flujo del docente.
#Tiene un botón principal (ajustar competencia/RA) y uno secundario opcional
#(marcar entrega en Banco de Tareas), que solo aparece cuando aplica -ver
#_guardar en ModuloObservaciones.
class CintaAjusteCompetencia(QFrame):

    ajustar= Signal()
    ajustar_secundario= Signal()
    descartada= Signal()

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("CintaAjusteCompetencia")
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(8)
        self.lbl_texto= QLabel("")
        self.lbl_texto.setWordWrap(True)
        lay.addWidget(self.lbl_texto, 1)
        self.btn_secundario= QPushButton("")
        self.btn_secundario.setObjectName("ChipSugerida")
        self.btn_secundario.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_secundario.clicked.connect(self.ajustar_secundario.emit)
        self.btn_secundario.setVisible(False)
        lay.addWidget(self.btn_secundario)
        self.btn_ajustar= QPushButton("Ajustar competencia")
        self.btn_ajustar.setIcon(icono_emoji("📚"))
        self.btn_ajustar.setIconSize(_QSize_emoji(16, 16))
        self.btn_ajustar.setObjectName("ChipSugerida")
        self.btn_ajustar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ajustar.clicked.connect(self.ajustar.emit)
        lay.addWidget(self.btn_ajustar)
        btn_cerrar= QPushButton("")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setFixedWidth(28)
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(lambda: (self.descartada.emit(), self.ocultar()))
        lay.addWidget(btn_cerrar)

        self._anim= QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._visible_actual= False

        self.setStyleSheet("""
            QFrame#CintaAjusteCompetencia {
                background-color: rgba(99, 102, 241, 0.12);
                border: 1px solid rgba(99, 102, 241, 0.35);
                border-radius: 10px;
            }
        """)
        self.lbl_texto.setStyleSheet(
            "background: transparent; border: none; font-size: 12px; color: #6366F1;")

    def mostrar_para(self, texto, texto_boton=None, texto_boton_secundario=None):

        self.lbl_texto.setText(texto)
        if texto_boton:
            self.btn_ajustar.setText(texto_boton)
        if texto_boton_secundario:
            self.btn_secundario.setText(texto_boton_secundario)
            self.btn_secundario.setVisible(True)
        else:
            self.btn_secundario.setVisible(False)
        if not self._visible_actual:
            self._visible_actual= True
            self._anim.stop()
            self._anim.setStartValue(self.maximumHeight())
            self._anim.setEndValue(42)
            self._anim.start()

    def ocultar(self):

        if self._visible_actual:
            self._visible_actual= False
            self._anim.stop()
            self._anim.setStartValue(self.maximumHeight())
            self._anim.setEndValue(0)
            self._anim.start()


#Deja sumar o restar puntos en la Competencia Específica que el docente elija,
#a raíz de una observación. No es obligatorio ni automático: el docente decide la
#materia, la competencia, el período y cuánto pesa el ajuste. Por debajo, esto crea
#una evidencia normal (categoría "Ajuste por Observación") vinculada a esa
#competencia, así que entra en el mismo cálculo automático que cualquier otra nota
#— no un número suelto sin trazabilidad.
class DialogoAjusteCompetencia(QDialog):

    def __init__(self, estudiante_id, texto_observacion, naturaleza, parent=None, materia_id_sugerida=None):

        super().__init__(parent)
        self.estudiante_id= estudiante_id
        self.setWindowTitle("Ajustar Competencia por Observación")
        self.setMinimumWidth(460)

        layout= QVBoxLayout(self)
        info= QLabel("Esto crea una pequeña evidencia (\"Ajuste por Observación\") vinculada a la "
                       "competencia que elijas, con un peso modesto — no reemplaza las evidencias "
                       "académicas normales, solo las complementa.")
        info.setWordWrap(True)
        layout.addWidget(info)

        cita= QLabel(f"“{texto_observacion[:140]}{'…' if len(texto_observacion) > 140 else ''}”")
        cita.setWordWrap(True)
        cita.setStyleSheet("font-style: italic; color: #6B7280;")
        layout.addWidget(cita)

        form= QGridLayout()
        self.grado_id= grado_de_estudiante(estudiante_id)
        self.combo_materia= QComboBox()
        conn= obtener_conexion()
        c= conn.cursor()
        if self.grado_id is not None:
            c.execute("""SELECT DISTINCT materias.id, materias.nombre FROM competencias_especificas
                         JOIN materias ON competencias_especificas.materia_id = materias.id
                         WHERE competencias_especificas.grado_id=? ORDER BY materias.nombre""",
                      (self.grado_id,))
            for f in c.fetchall():
                self.combo_materia.addItem(f["nombre"], f["id"])
        c.execute("SELECT id, nombre FROM periodos ORDER BY id")
        periodos= [dict(f) for f in c.fetchall()]
        conn.close()
        self.combo_materia.currentIndexChanged.connect(self._cargar_competencias)
        conectar_tooltip_seleccion(self.combo_materia, "Materia de la observación")
        if materia_id_sugerida is not None:
            idx_sugerida= self.combo_materia.findData(materia_id_sugerida)
            if idx_sugerida >= 0:
                self.combo_materia.setCurrentIndex(idx_sugerida)
        form.addWidget(QLabel("Materia:"), 0, 0)
        form.addWidget(self.combo_materia, 0, 1)
        self.combo_competencia= QComboBox()
        conectar_tooltip_seleccion(self.combo_competencia, "Competencia específica evaluada")
        form.addWidget(QLabel("Competencia:"), 1, 0)
        form.addWidget(self.combo_competencia, 1, 1)
        self.combo_periodo= QComboBox()
        for p in periodos:
            self.combo_periodo.addItem(p["nombre"], p["id"])
        conectar_tooltip_seleccion(self.combo_periodo, "Periodo académico de la observación")
        form.addWidget(QLabel("Periodo:"), 2, 0)
        form.addWidget(self.combo_periodo, 2, 1)

        self.spin_ajuste= QSpinBox()
        self.spin_ajuste.setRange(-20, 20)
        self.spin_ajuste.setSuffix(" pts")
        self.spin_ajuste.setValue(5 if naturaleza == "Positiva" else (-5 if naturaleza == "Negativa" else 0))
        form.addWidget(QLabel("Ajuste (+/-):"), 3, 0)
        form.addWidget(self.spin_ajuste, 3, 1)
        layout.addLayout(form)

        if self.combo_materia.count() == 0:
            aviso= QLabel("El grado de este estudiante todavía no tiene Competencias Específicas"
                            "definidas en ninguna materia (Calificaciones ▸ Currículo).")
            aviso.setWordWrap(True)
            layout.addWidget(aviso)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        self._cargar_competencias()
        centrar_y_al_frente(self, parent)

    def _cargar_competencias(self):

        self.combo_competencia.clear()
        materia_id= self.combo_materia.currentData()
        if materia_id is None or self.grado_id is None:
            return
        for comp in competencias_de_materia_grado(materia_id, self.grado_id):
            self.combo_competencia.addItem(f"{comp['codigo']} — {comp['descripcion']}", comp["id"])

    def datos(self):

        return {
            "materia_id": self.combo_materia.currentData(),
            "competencia_id": self.combo_competencia.currentData(),
            "periodo_id": self.combo_periodo.currentData(),
            "ajuste": self.spin_ajuste.value(),
        }


class ModuloObservaciones(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion= None
        self.gerencial= tiene_acceso_gerencial(main_window)
        self.restringido= es_profesor_restringido(main_window)
        self.observaciones_pagina= []  #filas sqlite de la página actual (evita re-consultar al editar/eliminar)
        self._firma_tema_aplicada= None
        self._filtro_naturaleza= None
        self._sugerencias_descartadas= False
        self.paginacion= ControlPaginacion(tamano_inicial=10)
        self._build_ui()
        self._aplicar_tema_visual()
        self.refrescar()
        QTimer.singleShot(0, lambda: _animar_aparicion(self._contenido, 320))
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Observaciones"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar observación", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar)
        registrar_atajo(self, self.main_window, "Ctrl+D", "Ver detalle", self._ver_detalle_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Editar observación seleccionada",
                         self._editar_seleccionada)
        #Eliminar una observación es un registro de conducta/seguimiento institucional: se deja fuera del Modo Docente
        #por atajo, igual que el resto de acciones destructivas sobre datos institucionales.
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar observación seleccionada",
                         self._eliminar_seleccionada, solo_no_docente=True)

    #Construcción de interfaz
    def _build_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        self.scroll= QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        self._contenido= contenido
        layout= QVBoxLayout(contenido)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)

        #--- Cabecera tipo "hero": icono + título + subtítulo + contador animado ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("🗒", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Observaciones")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(2)
        titulo_modulo= "Mis Observaciones" if self.restringido else "Observaciones"
        self.lbl_titulo_cabecera= QLabel(titulo_modulo)
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel("Bitácora de comportamiento y seguimiento por estudiante.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo, 1)

        self.chip_contador= ContadorAnimado(lambda v: f"{v} observación" + ("es" if v != 1 else ""))
        self.chip_contador.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.frame_cabecera)

        #--- Cinta de destacadas (oculta hasta que haya alguna) ---
        self.cinta_destacadas= CintaAlerta()
        self.cinta_destacadas.clicada.connect(self._al_pulsar_banner_destacadas)
        layout.addWidget(self.cinta_destacadas)

        #--- Filtros: una sola fila (buscador + botón "☰ Filtros"), igual que el resto de módulos de AcaDeXI, con un
        #desplegable opcional para las dimensiones propias de observaciones (naturaleza / categoría) -eso es "🔧 Más
        #filtros", que NO se toca-. Área Técnica/Carrera/Curso/Sección viven en la ventana de "☰ Filtros", separada de
        #"🔧 Más filtros". ---
        self.tarjeta_filtros= TarjetaPanel()
        filtros_raiz= self.tarjeta_filtros.contenido

        #Área Técnica (Politécnico) / Carrera (Universidad), y Curso/Sección:
        #antes vivían siempre visibles arriba de la barra de búsqueda; ahora viven en la ventana de "☰ Filtros" (mismo
        #patrón que calendario.py/banco_tareas.py/politecnico.py). Solo se muestran/pueblan si la institución tiene ese
        #módulo activo (en "Personalizado" pueden aparecer ambos a la vez).
        self.lbl_filtro_especialidad= QLabel("Área Técnica:")
        self.combo_filtro_especialidad= QComboBox()
        self.combo_filtro_especialidad.currentIndexChanged.connect(self._filtro_tecnico_listado_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad, "Filtrar por área técnica del estudiante (Politécnico)")

        self.lbl_filtro_carrera= QLabel("Carrera:")
        self.combo_filtro_carrera= QComboBox()
        self.combo_filtro_carrera.currentIndexChanged.connect(self._filtro_tecnico_listado_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_carrera, "Filtrar por carrera del estudiante (Universidad)")

        self.combo_filtro_grado= QComboBox()
        self.combo_filtro_grado.setToolTip("Filtrar por curso/grado")
        self.combo_filtro_grado.currentIndexChanged.connect(self._grado_filtro_cambio)

        self.combo_filtro_seccion= QComboBox()
        self.combo_filtro_seccion.setToolTip("Filtrar por sección")
        self.combo_filtro_seccion.currentIndexChanged.connect(self._filtro_tecnico_listado_cambio)

        self._construir_dialogo_filtros_listado()

        fila_busqueda= QHBoxLayout()
        fila_busqueda.setSpacing(10)
        self.marco_busqueda= QFrame()
        lay_busqueda= QHBoxLayout(self.marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda)
        self.in_buscar= QLineEdit()
        limitar_campo_texto(self.in_buscar, 150)
        self.in_buscar.setPlaceholderText("Buscar por estudiante, sección o contenido de la observación…")
        lay_busqueda.addWidget(self.in_buscar, 1)
        fila_busqueda.addWidget(self.marco_busqueda, 1)
        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._filtro_cambio)
        self.in_buscar.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        self.btn_filtros_listado= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_listado)
        self.btn_filtros_listado.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_listado.setObjectName("BtnAccionNeutro")
        self.btn_filtros_listado.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filtros_listado.setToolTip("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_listado.clicked.connect(self._abrir_dialogo_filtros_listado)
        fila_busqueda.addWidget(self.btn_filtros_listado)

        self.btn_mas_filtros= QPushButton("Más filtros")
        icono_boton_filtro(self.btn_mas_filtros)
        self.btn_mas_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_mas_filtros.setObjectName("BtnMasFiltros")
        self.btn_mas_filtros.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mas_filtros.clicked.connect(self._alternar_panel_avanzado)
        fila_busqueda.addWidget(self.btn_mas_filtros)
        filtros_raiz.addLayout(fila_busqueda)

        self.marco_resumen_filtros_listado= QWidget()
        self.layout_resumen_filtros_listado= FlowLayout(self.marco_resumen_filtros_listado, margin=0, spacing=12)
        filtros_raiz.addWidget(self.marco_resumen_filtros_listado)

        #Panel avanzado colapsable: naturaleza (con contador) + destacadas + categorías.
        self.panel_avanzado= QWidget()
        self.panel_avanzado.setMaximumHeight(0)
        layout_avanzado= QVBoxLayout(self.panel_avanzado)
        layout_avanzado.setContentsMargins(0, 10, 0, 0)
        layout_avanzado.setSpacing(8)

        fila_nivel_avanzado= QHBoxLayout()
        fila_nivel_avanzado.addWidget(QLabel("Nivel Educativo:"))
        self.combo_filtro_nivel= QComboBox()
        self.combo_filtro_nivel.currentIndexChanged.connect(self._nivel_filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel, "Filtrar por nivel educativo (se combina con Curso/Sección)")
        fila_nivel_avanzado.addWidget(self.combo_filtro_nivel)
        fila_nivel_avanzado.addStretch()
        layout_avanzado.addLayout(fila_nivel_avanzado)

        marco_chips_naturaleza= QWidget()
        layout_nat_filtro= FlowLayout(marco_chips_naturaleza, margin=0, spacing=6)
        self.chips_filtro_naturaleza= {}
        chip_todas= Chip("todas", "Todas", color_activo="#6366F1")
        chip_todas.establecer_marcado(True, animar=False, emitir=False)
        chip_todas.alternado.connect(lambda _m, k="todas": self._clic_filtro_naturaleza(k))
        layout_nat_filtro.addWidget(chip_todas)
        self.chips_filtro_naturaleza["todas"]= chip_todas
        for clave, color in NATURALEZAS:
            chip= Chip(clave, clave, color_activo=color)
            chip.alternado.connect(lambda _m, k=clave: self._clic_filtro_naturaleza(k))
            layout_nat_filtro.addWidget(chip)
            self.chips_filtro_naturaleza[clave]= chip
        self.chip_destacadas= Chip("destacadas", "Destacadas", color_activo="#F59E0B")
        self.chip_destacadas.alternado.connect(lambda _m: self._filtro_cambio())
        layout_nat_filtro.addWidget(self.chip_destacadas)
        layout_avanzado.addWidget(marco_chips_naturaleza)

        marco_chips_cat_filtro= QWidget()
        layout_cat_filtro= FlowLayout(marco_chips_cat_filtro, margin=0, spacing=6)
        self.chips_categoria_filtro= {}
        for clave, etiqueta, _palabras in CATEGORIAS:
            chip= Chip(clave, etiqueta, color_activo="#6366F1")
            chip.alternado.connect(lambda _m: self._filtro_cambio())
            layout_cat_filtro.addWidget(chip)
            self.chips_categoria_filtro[clave]= chip
        layout_avanzado.addWidget(marco_chips_cat_filtro)

        fila_limpiar= QHBoxLayout()
        fila_limpiar.addStretch()
        btn_limpiar_filtros= QPushButton("Limpiar filtros")
        btn_limpiar_filtros.setIcon(icono_emoji("🧹"))
        btn_limpiar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_filtros.setObjectName("BtnAccionNeutro")
        btn_limpiar_filtros.clicked.connect(self._limpiar_filtros)
        fila_limpiar.addWidget(btn_limpiar_filtros)
        layout_avanzado.addLayout(fila_limpiar)

        filtros_raiz.addWidget(self.panel_avanzado)
        layout.addWidget(self.tarjeta_filtros)

        #--- Registros (tabla) — va justo debajo de los filtros, arriba de "categorías frecuentes" y del formulario de
        #captura, para que lo que el docente/gerencia consulta con más frecuencia (el historial) esté visible sin tener
        #que bajar toda la pantalla.
        ##Se reemplaza la antigua lista de tarjetas apiladas (con animación de entrada por geometría, que se
        #desincronizaba con el layout y
        #producía el bugueo visual reportado) por una QTableWidget real:
        #escalable con muchos registros —con SU PROPIO scroll, sin estirar la página— pero conservando el mismo
        #lenguaje visual que las tarjetas: icono+color por naturaleza, ⭐ para destacadas, un tinte de fila suave con el
        #color de la naturaleza (en vez del borde de color de la tarjeta) y categorías legibles. Doble clic — o el
        #botón "🔎 Ver Detalle" — abre la observación completa: tipo, categorías y la descripción sin truncar. ---

        self.frame_tabla= QFrame()
        self.frame_tabla.setObjectName("TarjetaTabla")
        tabla_card_layout= QVBoxLayout(self.frame_tabla)
        tabla_card_layout.setContentsMargins(18, 16, 18, 14)
        tabla_card_layout.setSpacing(10)

        self.lbl_vacio= QLabel("No hay observaciones que coincidan con los filtros actuales.")
        self.lbl_vacio.setObjectName("AvisoVacio")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setVisible(False)
        tabla_card_layout.addWidget(self.lbl_vacio)

        self.tabla= QTableWidget(0, len(ENCABEZADOS_TABLA))
        aplicar_estructura_tabla(self.tabla)

        self.tabla.setHorizontalHeaderLabels(ENCABEZADOS_TABLA)
        self.tabla.setColumnHidden(COL_ID, True)
        header= self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #La última columna (Descripción) sí se estira: es la que más se quiere leer de un vistazo, y a diferencia de
        #una tabla de datos tabulares "cerrados" (como estudiantes.py) aquí conviene que aproveche todo el ancho
        #sobrante en vez de dejarlo vacío.
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(60)
        anchos_base= {COL_NUMERO: 48, COL_TIPO: 118, COL_DESTACADA: 40, COL_ESTUDIANTE: 170, COL_GRADO: 90,
                       COL_SECCION: 90, COL_FECHA: 118, COL_CATEGORIAS: 260}
        for col, ancho in anchos_base.items():
            self.tabla.setColumnWidth(col, ancho)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        #Sin rayado clásico alternado: el tinte por naturaleza (positiva/ informativa/negativa) ya cumple ese rol de
        #separar filas visualmente y, a diferencia del rayado, también aporta información.
        self.tabla.setAlternatingRowColors(False)
        self.tabla.setWordWrap(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(38)
        self.tabla.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabla.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.tabla.setMinimumHeight(260)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tabla.cellDoubleClicked.connect(lambda fila, _col: self._abrir_detalle_fila(fila))
        tabla_card_layout.addWidget(self.tabla, 1)

        layout.addWidget(self.frame_tabla)

        #La paginación y los botones de acción sobre la fila seleccionada quedan fuera de la tarjeta de la tabla (antes
        #vivían dentro de "TarjetaTabla" y visualmente parecían parte de la tabla misma).
        layout.addWidget(self.paginacion)

        #Botón ⛶ que abre filtros + tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo
        #maximizado -mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-. Se
        #agrega recién aquí, junto al título "Registros", porque necesita self.paginacion ya construido.
        agregar_boton_pantalla_completa(
            None, [self.tarjeta_filtros, self.frame_tabla, self.paginacion],
            titulo= "Observaciones", parent=self)

        fila_acciones_tabla= QHBoxLayout()
        self.btn_ver_detalle_tabla= QPushButton("Ver Detalle")
        self.btn_ver_detalle_tabla.setIcon(icono_emoji("👁"))
        self.btn_ver_detalle_tabla.setIconSize(_QSize_emoji(16, 16))
        self.btn_ver_detalle_tabla.setObjectName("BtnAccionNeutro")
        self.btn_ver_detalle_tabla.clicked.connect(self._ver_detalle_seleccionada)
        fila_acciones_tabla.addWidget(self.btn_ver_detalle_tabla)
        self.btn_editar_seleccionada= QPushButton("Editar seleccionada")
        self.btn_editar_seleccionada.setIcon(icono_emoji("✏"))
        self.btn_editar_seleccionada.setIconSize(_QSize_emoji(16, 16))
        self.btn_editar_seleccionada.setObjectName("BtnAccionEditar")
        self.btn_editar_seleccionada.clicked.connect(self._editar_seleccionada)
        fila_acciones_tabla.addWidget(self.btn_editar_seleccionada)
        self.btn_eliminar_seleccionada= QPushButton("Eliminar seleccionada")
        self.btn_eliminar_seleccionada.setIcon(icono_emoji("🗑"))
        self.btn_eliminar_seleccionada.setIconSize(_QSize_emoji(16, 16))
        self.btn_eliminar_seleccionada.setObjectName("BtnAccionEliminar")
        self.btn_eliminar_seleccionada.clicked.connect(self._eliminar_seleccionada)
        fila_acciones_tabla.addWidget(self.btn_eliminar_seleccionada)
        fila_acciones_tabla.addStretch()
        layout.addLayout(fila_acciones_tabla)

        #--- Categorías más frecuentes ---
        self.tarjeta_frecuentes= TarjetaPanel("Categorías más frecuentes")
        self.barras_frecuencia= []
        for _ in range(5):
            b= BarraFrecuencia()
            b.setVisible(False)
            self.tarjeta_frecuentes.contenido.addWidget(b)
            self.barras_frecuencia.append(b)
        self.lbl_sin_datos_frecuentes= QLabel("Aún no hay observaciones suficientes para mostrar tendencias.")
        self.lbl_sin_datos_frecuentes.setObjectName("DescModulo")
        self.tarjeta_frecuentes.contenido.addWidget(self.lbl_sin_datos_frecuentes)
        layout.addWidget(self.tarjeta_frecuentes)

        #--- Formulario de nueva observación ---
        self.tarjeta_form= TarjetaPanel("Nueva observación", con_sombra=True)
        form= self.tarjeta_form.contenido

        desc_form= QLabel("Describe lo que pasó; te sugeriremos las categorías.")
        desc_form.setObjectName("DescModulo")
        form.addWidget(desc_form)

        #Área Técnica (Politécnico) / Carrera (Universidad, o Personalizado con el módulo correspondiente activo): en
        #su propia fila, dentro de un cuadrito propio, ARRIBA de Curso/Sección/Estudiante (igual que en Asistencia y en
        #Pasantías de Politécnico). Solo acotan las opciones del combo "Estudiante" de abajo; no son un dato que se
        #guarde con la observación.
        frame_filtro_tecnico_form= QFrame()
        frame_filtro_tecnico_form.setObjectName("CuadroFiltroTecnico")
        frame_filtro_tecnico_form.setStyleSheet(
            "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
            "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
        fila_filtro_tecnico_form= QHBoxLayout(frame_filtro_tecnico_form)
        fila_filtro_tecnico_form.setContentsMargins(14, 10, 14, 10)
        fila_filtro_tecnico_form.setSpacing(16)
        self.lbl_filtro_especialidad_form= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_form= QComboBox()
        self.combo_filtro_especialidad_form.setMinimumWidth(210)
        self.combo_filtro_especialidad_form.currentIndexChanged.connect(self._cargar_combo_estudiantes)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_form,
                                    "Filtrar el combo de Estudiante por área técnica (Politécnico)")
        fila_filtro_tecnico_form.addWidget(self.lbl_filtro_especialidad_form)
        fila_filtro_tecnico_form.addWidget(self.combo_filtro_especialidad_form)

        self.lbl_filtro_carrera_form= QLabel("Carrera:")
        self.combo_filtro_carrera_form= QComboBox()
        self.combo_filtro_carrera_form.setMinimumWidth(210)
        self.combo_filtro_carrera_form.currentIndexChanged.connect(self._cargar_combo_estudiantes)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_form,
                                    "Filtrar el combo de Estudiante por carrera (Universidad)")
        fila_filtro_tecnico_form.addWidget(self.lbl_filtro_carrera_form)
        fila_filtro_tecnico_form.addWidget(self.combo_filtro_carrera_form)
        fila_filtro_tecnico_form.addStretch()
        form.addWidget(frame_filtro_tecnico_form)

        fila_seleccion= QGridLayout()
        fila_seleccion.setHorizontalSpacing(12)
        fila_seleccion.setVerticalSpacing(6)
        self.combo_grado_form= QComboBox()
        self.combo_grado_form.currentIndexChanged.connect(self._grado_form_cambio)
        self.combo_seccion_form= QComboBox()
        self.combo_seccion_form.currentIndexChanged.connect(self._cargar_combo_estudiantes)
        self.combo_estudiante= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante, "Estudiante al que corresponde la observación")
        self.combo_materia_obs= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_obs,
            "Opcional: si la observación surgió en una materia o módulo técnico puntual, "
            "elígela aquí. Al guardar, la sugerencia de ajuste te llevará al lugar correcto "
            "(Ajustar Competencia o Calificaciones Técnicas) según el modelo de esa materia.")
        fila_seleccion.addWidget(QLabel("Curso:"), 0, 0)
        fila_seleccion.addWidget(self.combo_grado_form, 0, 1)
        fila_seleccion.addWidget(QLabel("Sección:"), 0, 2)
        fila_seleccion.addWidget(self.combo_seccion_form, 0, 3)
        fila_seleccion.addWidget(QLabel("Estudiante:"), 1, 0)
        fila_seleccion.addWidget(self.combo_estudiante, 1, 1, 1, 3)
        fila_seleccion.addWidget(QLabel("Materia/Módulo:"), 2, 0)
        fila_seleccion.addWidget(self.combo_materia_obs, 2, 1, 1, 3)
        form.addLayout(fila_seleccion)
        self._cargar_combo_materias_obs()

        self.in_texto= QTextEdit()
        limitar_campo_texto(self.in_texto, 5000)
        self.in_texto.setPlaceholderText(
            "Ej.: Amanda participa muchísimo, siempre entrega las tareas y ayuda a sus compañeros…")
        self.in_texto.setFixedHeight(76)
        self._temporizador_sugerencias= QTimer(self)
        self._temporizador_sugerencias.setSingleShot(True)
        self._temporizador_sugerencias.setInterval(350)
        self._temporizador_sugerencias.timeout.connect(self._actualizar_sugerencias)
        self.in_texto.textChanged.connect(self._on_texto_observacion_cambiado)
        form.addWidget(self.in_texto)

        self.marco_sugerencias= QWidget()
        self.marco_sugerencias.setObjectName("MarcoSugerencias")
        self.marco_sugerencias.setVisible(False)
        fila_sug= QHBoxLayout(self.marco_sugerencias)
        fila_sug.setContentsMargins(8, 6, 8, 6)
        fila_sug.setSpacing(6)
        lbl_sug= QLabel("Sugerencias:")
        lbl_sug.setObjectName("DescModulo")
        fila_sug.addWidget(lbl_sug)
        marco_chips_sug= QWidget()
        self.layout_sugerencias= FlowLayout(marco_chips_sug, margin=0, spacing=6)
        fila_sug.addWidget(marco_chips_sug, 1)
        self.btn_cerrar_sugerencias= QPushButton("")
        self.btn_cerrar_sugerencias.setIcon(icono_emoji("✖"))
        self.btn_cerrar_sugerencias.setIconSize(_QSize_emoji(16, 16))
        self.btn_cerrar_sugerencias.setObjectName("BtnCerrarSugerencias")
        self.btn_cerrar_sugerencias.setFixedSize(22, 22)
        self.btn_cerrar_sugerencias.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar_sugerencias.setToolTip("Ocultar sugerencias")
        self.btn_cerrar_sugerencias.clicked.connect(self._descartar_sugerencias)
        fila_sug.addWidget(self.btn_cerrar_sugerencias, 0, Qt.AlignmentFlag.AlignTop)
        form.addWidget(self.marco_sugerencias)

        lbl_naturaleza= QLabel("¿Cómo fue?")
        lbl_naturaleza.setObjectName("DescModulo")
        form.addWidget(lbl_naturaleza)
        self.segmentado= SegmentadoNaturaleza()
        form.addWidget(self.segmentado)

        lbl_categorias= QLabel("¿De qué trata? (puedes elegir varias)")
        lbl_categorias.setObjectName("DescModulo")
        form.addWidget(lbl_categorias)
        marco_categorias= QWidget()
        self.layout_categorias= FlowLayout(marco_categorias, margin=0, spacing=8)
        self.chips_categoria= {}
        for clave, etiqueta, _palabras in CATEGORIAS:
            chip= Chip(clave, etiqueta, color_activo="#6366F1")
            self.layout_categorias.addWidget(chip)
            self.chips_categoria[clave]= chip
        form.addWidget(marco_categorias)

        lbl_plantillas= QLabel("Plantillas rápidas")
        lbl_plantillas.setObjectName("DescModulo")
        form.addWidget(lbl_plantillas)
        marco_plantillas= QWidget()
        layout_plantillas= FlowLayout(marco_plantillas, margin=0, spacing=6)
        for plantilla in PLANTILLAS:
            titulo, naturaleza_sugerida, categorias_sugeridas, _cuerpo= plantilla
            btn= QPushButton(titulo)
            #Icono multicolor de la plantilla: la primera categoría sugerida si tiene alguna (más específico), si no la
            #naturaleza sugerida -así TODAS las plantillas quedan con icono, ninguna se ve "pelada" al lado de las demás.
            clave_icono= categorias_sugeridas[0] if categorias_sugeridas else naturaleza_sugerida.lower()
            btn.setIcon(icono_categoria_color(clave_icono, 16))
            btn.setIconSize(QSize(16, 16))
            btn.setObjectName("ChipPlantilla")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, p=plantilla: self._aplicar_plantilla(p))
            layout_plantillas.addWidget(btn)
        form.addWidget(marco_plantillas)

        fila_botones_form= QHBoxLayout()
        btn_guardar= QPushButton("Guardar Observación")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar)
        fila_botones_form.addWidget(btn_guardar)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar)
        fila_botones_form.addWidget(btn_limpiar)
        fila_botones_form.addStretch()
        form.addLayout(fila_botones_form)

        #Sugerencia no intrusiva (opcional): tras guardar, ofrece reflejar la observación en una competencia sin
        #interrumpir ni obligar a nada.
        self.cinta_ajuste= CintaAjusteCompetencia()
        self.cinta_ajuste.ajustar.connect(self._al_pulsar_ajustar)
        self.cinta_ajuste.ajustar_secundario.connect(self._abrir_ajuste_entrega)
        form.addWidget(self.cinta_ajuste)

        self.panel_form_observacion= PanelDesplegable("Nueva observación")
        self.panel_form_observacion.cuerpo_layout().addWidget(self.tarjeta_form)
        layout.addWidget(self.panel_form_observacion)

        self.scroll.setWidget(contenido)
        layout_raiz.addWidget(self.scroll, 1)

        self.paginacion.cambio.connect(self._cargar_tabla)

    #Panel avanzado de filtros (colapsable, tipo acordeón)
    def _alternar_panel_avanzado(self):

        expandido= self.panel_avanzado.maximumHeight() > 0
        anim= QPropertyAnimation(self.panel_avanzado, b"maximumHeight", self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if expandido:
            anim.setStartValue(self.panel_avanzado.height())
            anim.setEndValue(0)
        else:
            anim.setStartValue(0)
            objetivo= self.panel_avanzado.sizeHint().height()
            anim.setEndValue(objetivo)
            #Al terminar de expandir se libera el máximo para que pueda seguir creciendo solo si el contenido cambia (más
            #chips, ventana más angosta que hace que las filas se reacomoden, etc.).
            anim.finished.connect(lambda: self.panel_avanzado.setMaximumHeight(16777215)
                                   if self.panel_avanzado.maximumHeight() > 0 else None)
        self._anim_panel_avanzado= anim
        anim.start()
        self._actualizar_texto_boton_filtros()

    def _filtros_avanzados_activos(self):

        n= 0
        if self._filtro_naturaleza:
            n += 1
        if self.chip_destacadas.esta_marcado():
            n += 1
        n += sum(1 for chip in self.chips_categoria_filtro.values() if chip.esta_marcado())
        return n

    def _actualizar_texto_boton_filtros(self):

        n= self._filtros_avanzados_activos()
        self.btn_mas_filtros.setText(f"Más filtros ({n})" if n else "Más filtros")

    #Carga de combos: curso (grado) → SECCIÓN → ESTUDIANTE
    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo). Mismo criterio usado en estudiantes.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la institución es de tipo Universidad (o Personalizado con el
    #módulo Universidad activo). Mismo criterio usado en estudiantes.py.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    #Igual que en Estudiantes: el combo de Área Técnica solo se muestra si
    #la institución tiene el módulo Politécnico activo.
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
        for f in c.fetchall():
            combo.addItem(f["nombre"], f["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Igual que en Estudiantes: el combo de Carrera solo se muestra si la
    #institución tiene el módulo Universidad activo.
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
        for f in c.fetchall():
            combo.addItem(f["nombre"], f["id"])
        conn.close()
        idx= combo.findData(actual)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _secciones_permitidas_ids(self):

        base= obtener_secciones_permitidas(self.main_window) if self.restringido else None
        nivel= self.combo_filtro_nivel.currentData() if hasattr(self, "combo_filtro_nivel") else None
        return interseccion_opcional(base, secciones_del_nivel_educativo(nivel))

    def _nivel_filtro_cambio(self):

        self._cargar_combos_filtro()
        self._filtro_cambio()

    #Ventanita (no modal) con Curso/Grado, Sección, Área Técnica y
    #Carrera para la tabla de "Registros" — separada de "🔧 Más filtros"
    #(que sigue igual: Nivel Educativo, Naturaleza, Categorías,
    #Destacadas). Mismo patrón que calendario.py/banco_tareas.py.
    def _construir_dialogo_filtros_listado(self):

        self.dialogo_filtros_listado= QDialog(self)
        self.dialogo_filtros_listado.setObjectName("DialogoFiltrosObs")
        self.dialogo_filtros_listado.setWindowTitle("Filtros de Observaciones")
        aplicar_icono_ventana(self.dialogo_filtros_listado, ICONO_FILTRO)
        self.dialogo_filtros_listado.setModal(False)
        self.dialogo_filtros_listado.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_listado)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        icono_encabezado= QLabel()
        pixmap_boton_filtro(icono_encabezado, 20)
        icono_encabezado.setObjectName("IconoEncabezadoFiltrosObs")
        fila_encabezado.addWidget(icono_encabezado)
        titulo_encabezado= QLabel("Filtros")
        titulo_encabezado.setObjectName("TituloEncabezadoFiltrosObs")
        fila_encabezado.addWidget(titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        subtitulo= QLabel("Todos son opcionales; se combinan con la búsqueda y con \" Más filtros\".")
        subtitulo.setObjectName("SubtituloFiltrosObs")
        subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltrosObs")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            (None, self.combo_filtro_especialidad),
            (None, self.combo_filtro_carrera),
            ("Curso/Grado:", self.combo_filtro_grado),
            ("Sección:", self.combo_filtro_seccion),
        ):
            if combo is self.combo_filtro_especialidad:
                grid.addWidget(self.lbl_filtro_especialidad, fila, 0)
            elif combo is self.combo_filtro_carrera:
                grid.addWidget(self.lbl_filtro_carrera, fila, 0)
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
        btn_limpiar.clicked.connect(self._limpiar_filtros_listado)
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_listado.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_listado(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_listado.parent() is not _fc:
            self.dialogo_filtros_listado.setParent(_fc)
        self.dialogo_filtros_listado.show()
        self.dialogo_filtros_listado.raise_()
        self.dialogo_filtros_listado.activateWindow()

    def _limpiar_filtros_listado(self):

        for combo in (self.combo_filtro_especialidad, self.combo_filtro_carrera, self.combo_filtro_grado):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._grado_filtro_cambio()

    #Como Curso/Sección/Área Técnica/Carrera ahora viven en la ventana
    #de Filtros (oculta por defecto), esta fila deja a la vista, sin abrir
    #la ventana, qué se está mostrando en la tabla -icono vectorial real
    #(pixmap_emoji en un QLabel aparte, ver iconos_emoji.py) junto al
    #texto, no un emoji incrustado en el string como antes.
    def _actualizar_resumen_filtros_listado(self):

        if not hasattr(self, "marco_resumen_filtros_listado"):
            return
        while self.layout_resumen_filtros_listado.count():
            item= self.layout_resumen_filtros_listado.takeAt(0)
            w= item.widget()
            if w:
                w.deleteLater()

        color_texto= self._colores["txt_sec"] if hasattr(self, "_colores") else "#64748B"

        def _agregar(glifo, texto):

            grupo= QWidget()
            lay= QHBoxLayout(grupo)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lbl_icono= QLabel()
            lbl_icono.setPixmap(pixmap_emoji(glifo, 15))
            lay.addWidget(lbl_icono)
            lbl_texto= QLabel(texto)
            lbl_texto.setStyleSheet(f"color: {color_texto}; font-size: 11px;")
            lay.addWidget(lbl_texto)
            self.layout_resumen_filtros_listado.addWidget(grupo)

        if self.combo_filtro_grado.currentData() is not None:
            _agregar("🎓", self.combo_filtro_grado.currentText())
        if self.combo_filtro_seccion.currentData() is not None:
            _agregar("🏫", self.combo_filtro_seccion.currentText())
        if self._es_politecnico() and self.combo_filtro_especialidad.currentData() is not None:
            _agregar("🧩", self.combo_filtro_especialidad.currentText())
        if self._es_universidad() and self.combo_filtro_carrera.currentData() is not None:
            _agregar("🎓", self.combo_filtro_carrera.currentText())

    def _cargar_combos_filtro(self):

        permitidas= self._secciones_permitidas_ids()
        poblar_combo_curso(self.combo_filtro_grado, incluir_todos=False, secciones_permitidas=permitidas)
        cascada_seccion_por_curso(self.combo_filtro_grado, self.combo_filtro_seccion,
                                   incluir_todas= False, secciones_permitidas=permitidas)

    def _cargar_combos_form(self):

        permitidas= self._secciones_permitidas_ids()
        poblar_combo_curso(self.combo_grado_form, incluir_todos=False, secciones_permitidas=permitidas)
        cascada_seccion_por_curso(self.combo_grado_form, self.combo_seccion_form,
                                   incluir_todas= False, secciones_permitidas=permitidas)

    def _grado_filtro_cambio(self):

        permitidas= self._secciones_permitidas_ids()
        cascada_seccion_por_curso(self.combo_filtro_grado, self.combo_filtro_seccion,
                                   incluir_todas= False, secciones_permitidas=permitidas)
        self._actualizar_resumen_filtros_listado()
        self._filtro_cambio()

    def _filtro_tecnico_listado_cambio(self):

        self._actualizar_resumen_filtros_listado()
        self._filtro_cambio()

    def _grado_form_cambio(self):

        permitidas= self._secciones_permitidas_ids()
        cascada_seccion_por_curso(self.combo_grado_form, self.combo_seccion_form,
                                   incluir_todas= False, secciones_permitidas=permitidas)
        self._cargar_combo_estudiantes()

    #Igual que en Estudiantes/Asistencia/Pasantías: los combos de Área
    #Técnica y Carrera del formulario solo se muestran/pueblan si la
    #institución tiene ese módulo activo.
    def _cargar_filtro_tecnico_form(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_form.setVisible(es_poli)
        self.combo_filtro_especialidad_form.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_form.currentData()
            self.combo_filtro_especialidad_form.blockSignals(True)
            self.combo_filtro_especialidad_form.clear()
            self.combo_filtro_especialidad_form.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_form.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_form.findData(actual)
            self.combo_filtro_especialidad_form.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_form.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_form.setVisible(es_uni)
        self.combo_filtro_carrera_form.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_form.currentData()
            self.combo_filtro_carrera_form.blockSignals(True)
            self.combo_filtro_carrera_form.clear()
            self.combo_filtro_carrera_form.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_form.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_carrera_form.findData(actual)
            self.combo_filtro_carrera_form.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_form.blockSignals(False)

    def _cargar_combo_estudiantes(self):

        self.combo_estudiante.clear()
        #Placeholder real (sin datos) primero: evita que, con los filtros
        #amplios (p.ej. "Todos los cursos"), quede seleccionado por accidente
        #el primer estudiante de la lista sin que el usuario lo haya elegido.
        self.combo_estudiante.addItem("Selecciona un estudiante…", None)
        secciones_permitidas= self._secciones_permitidas_ids()
        seccion_form= self.combo_seccion_form.currentData()
        especialidad_id= (self.combo_filtro_especialidad_form.currentData()
                            if hasattr(self, "combo_filtro_especialidad_form") and self._es_politecnico() else None)
        carrera_id= (self.combo_filtro_carrera_form.currentData()
                      if hasattr(self, "combo_filtro_carrera_form") and self._es_universidad() else None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre, apellidos, seccion_id, especialidad_id, carrera_id FROM estudiantes
                     WHERE estado='Activo' ORDER BY apellidos, nombre""")
        for f in c.fetchall():
            if secciones_permitidas is not None and f["seccion_id"] not in secciones_permitidas:
                continue
            if seccion_form is not None and f["seccion_id"] != seccion_form:
                continue
            if especialidad_id is not None and f["especialidad_id"] != especialidad_id:
                continue
            if carrera_id is not None and f["carrera_id"] != carrera_id:
                continue
            self.combo_estudiante.addItem(f"{f['nombre']} {f['apellidos'] or ''}".strip(), f["id"])
        conn.close()

    #Lista de materias/módulos elegibles para asociar a la observación
    #(opcional). No se filtra por curso/sección como el estudiante —
    #igual que el combo de materia de Asistencia, solo respeta qué
    #materias tiene permitidas este usuario.
    def _cargar_combo_materias_obs(self):

        seleccion_previa= self.combo_materia_obs.currentData()
        self.combo_materia_obs.blockSignals(True)
        self.combo_materia_obs.clear()
        self.combo_materia_obs.addItem("— Sin materia específica —", None)
        permitidas= obtener_materias_permitidas(self.main_window)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM materias WHERE estado='Activa' ORDER BY nombre")
        for f in c.fetchall():
            if permitidas is not None and f["id"] not in permitidas:
                continue
            self.combo_materia_obs.addItem(f["nombre"], f["id"])
        conn.close()
        idx= self.combo_materia_obs.findData(seleccion_previa)
        self.combo_materia_obs.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_materia_obs.blockSignals(False)

    #Sugerencias dinámicas de categoría
    def _on_texto_observacion_cambiado(self):

        #Cada vez que el docente sigue escribiendo se vuelve a "armar" la franja de sugerencias, aunque la haya cerrado
        #con la ✕ antes: cerrar solo descarta las sugerencias vigentes en ese momento, no apaga la función para el
        #resto de la redacción.
        self._sugerencias_descartadas= False
        self._temporizador_sugerencias.start()

    def _descartar_sugerencias(self):

        self._sugerencias_descartadas= True
        self._reconstruir_chips_sugeridas([])

    def _actualizar_sugerencias(self):

        if self._sugerencias_descartadas:
            return
        texto= _normalizar(self.in_texto.toPlainText())
        seleccionadas= {clave for clave, chip in self.chips_categoria.items() if chip.esta_marcado()}
        candidatas= []
        if texto:
            for clave, etiqueta, palabras in CATEGORIAS:
                if clave in seleccionadas:
                    continue
                coincidencias= sum(1 for p in palabras if _contiene_palabra(texto, _normalizar(p)))
                if coincidencias:
                    candidatas.append((coincidencias, clave, etiqueta))
        #Más palabras clave encontradas para una categoría = más señal de
        #que es relevante, así que las mejor sustentadas van primero. Y se limita a un puñado (MAX_SUGERENCIAS) para
        #que la franja no crezca sin control con textos largos que rocen media docena de temas.
        candidatas.sort(key=lambda c: c[0], reverse=True)
        sugeridas= [(clave, etiqueta) for _n, clave, etiqueta in candidatas[:MAX_SUGERENCIAS]]
        self._reconstruir_chips_sugeridas(sugeridas)

    def _reconstruir_chips_sugeridas(self, sugeridas):

        while self.layout_sugerencias.count():
            item= self.layout_sugerencias.takeAt(0)
            w= item.widget()
            if w:
                w.deleteLater()
        if not sugeridas:
            self.marco_sugerencias.setVisible(False)
            return
        self.marco_sugerencias.setVisible(True)
        for clave, etiqueta in sugeridas:
            btn= QPushButton(f"+ {etiqueta}")
            btn.setIcon(icono_categoria_color(clave, 14))
            btn.setIconSize(QSize(14, 14))
            btn.setObjectName("ChipSugerida")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _=False, k=clave: self._aceptar_sugerencia(k))
            self.layout_sugerencias.addWidget(btn)
        #Sin animación de entrada aquí a propósito: estos chips se crean y muestran dinámicamente (a diferencia de los
        #de categoría, que se arman una sola vez al construir la UI), así que cuando se anima su geometría "a mano" el
        #contenedor todavía no tiene su ancho real calculado por Qt y el chip queda estirado a un tamaño incorrecto (se
        #ve como un bloque sólido sin texto legible). Mostrarlos directamente deja que el FlowLayout los dimensione
        #correctamente.

    def _aceptar_sugerencia(self, clave):

        chip= self.chips_categoria.get(clave)
        if chip:
            chip.establecer_marcado(True)
        self._actualizar_sugerencias()

    #PLANTILLAS
    def _aplicar_plantilla(self, plantilla):

        _titulo, naturaleza, claves, cuerpo= plantilla
        nombre_est= self.combo_estudiante.currentText().strip()
        sujeto= nombre_est.split(" ")[0] if nombre_est else "El/La estudiante"
        self.in_texto.setPlainText(f"{sujeto} {cuerpo}")
        self.segmentado.establecer_valor(naturaleza)
        #Cada plantilla representa un set de categorías cerrado: antes de marcar las suyas hay que desmarcar cualquier
        #chip que haya quedado seleccionado de una plantilla o selección manual anterior, o si no los filtros se van
        #acumulando entre una plantilla y otra.
        claves_set= set(claves)
        for clave, chip in self.chips_categoria.items():
            chip.establecer_marcado(clave in claves_set)
        self._actualizar_sugerencias()

    #GUARDAR / EDITAR / ELIMINAR
    def _tipo_legado(self, naturaleza):

        return {"Positiva": "Positiva", "Informativa": "Neutra", "Negativa": "Negativa"}.get(naturaleza, "Neutra")

    def _guardar(self):

        estudiante_id= self.combo_estudiante.currentData()
        materia_id= self.combo_materia_obs.currentData()
        if estudiante_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona un estudiante.", self)
            return
        if not self.in_texto.toPlainText().strip():
            mostrar_mensaje("advertencia", "Datos incompletos", "Escribe el contenido de la observación.", self)
            return
        if self.id_edicion is not None and not self._puede_editar_id(self.id_edicion):
            mostrar_mensaje("advertencia", "Sin permisos", "Solo puedes editar tus propias observaciones.", self)
            return

        naturaleza= self.segmentado.valor()
        claves_categorias= sorted(clave for clave, chip in self.chips_categoria.items() if chip.esta_marcado())
        categorias_txt= ",".join(claves_categorias)
        destacada= 1 if (set(claves_categorias) & CLAVES_DESTACADAS) else 0
        tipo_legado= self._tipo_legado(naturaleza)

        profesor_id= obtener_profesor_id(self.main_window) if self.restringido else None
        usuario_id= getattr(self.main_window, "id_usuario_actual", None)
        texto= self.in_texto.toPlainText().strip()

        conn= obtener_conexion()
        try:

            c= conn.cursor()
            if self.id_edicion is None:
                c.execute("""INSERT INTO observaciones
                             (estudiante_id, profesor_id, usuario_id, fecha, tipo, texto, naturaleza, categorias,
                              destacada, materia_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?)""",
                          (estudiante_id, profesor_id, usuario_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           tipo_legado, texto, naturaleza, categorias_txt, destacada, materia_id))
                observacion_id_nueva= c.lastrowid
                accion= "Registró observación"
            else:
                c.execute("""UPDATE observaciones SET estudiante_id=?, tipo=?, texto=?, naturaleza=?, categorias=?,
                             destacada= ?, materia_id=? WHERE id=?""",
                          (estudiante_id, tipo_legado, texto, naturaleza, categorias_txt, destacada, materia_id,
                           self.id_edicion))
                observacion_id_nueva= None
                accion= "Editó observación"
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            mostrar_mensaje("advertencia", "No se pudo guardar",
                             "Ocurrió un problema guardando la observación. Intenta de nuevo.", self)
            return
        conn.close()
        registrar_auditoria("Observaciones", accion, self.main_window.usuario_actual,
                             self.combo_estudiante.currentText())
        self.tarjeta_form.destello("#22C55E")

        #Sugerencias no intrusivas: solo para observaciones NUEVAS (no al editar).
        #Hay dos, independientes entre sí, y pueden aparecer juntas o por separado:
        #- Ajustar competencia / RA técnico: solo tiene sentido en el sistema
        #dominicano (es el que usa Competencias Específicas y Resultados de
        #Aprendizaje), y solo si la observación quedó ligada a una materia.
        #- Marcar entrega: no depende del sistema de calificación -cualquier
        #institución puede usar Banco de Tareas-, solo de que la observación se haya etiquetado con la categoría "📝
        #Tareas" y esa materia tenga al menos una tarea activa donde marcar el estado.
        if observacion_id_nueva is not None:
            ofrece_calificacion= es_sistema_dominicano(_sistema_calificacion_actual()) and materia_id is not None
            ofrece_entrega= ("tareas" in claves_categorias and materia_id is not None
                               and _hay_tareas_activas_en_materia(materia_id))

            es_tecnica= False
            texto_principal, boton_principal= None, None
            if ofrece_calificacion:
                #Si la observación quedó ligada a una materia con modelo "Técnica (RA)" (Politécnico), no tiene sentido ofrecer
                #"Ajustar competencia" -ese modelo no usa Competencias Específicas-; se ofrece en su lugar ajustar un Resultado
                #de Aprendizaje de ese módulo. Con una materia de modelo Competencias, se conserva el flujo de ajuste de
                #siempre.
                conn2= obtener_conexion()
                c2= conn2.cursor()
                c2.execute("SELECT modelo_evaluacion FROM materias WHERE id=?", (materia_id,))
                f2= c2.fetchone()
                conn2.close()
                es_tecnica= (f2["modelo_evaluacion"] if f2 else None) == MODELO_EVALUACION_TECNICA
                if es_tecnica:
                    mensajes= {"Positiva": "¿Sumar puntos en este módulo técnico por esto? (opcional)",
                                "Negativa": "¿Restar puntos en este módulo técnico por esto? (opcional)",
                                "Informativa": "¿Reflejar esto en este módulo técnico? (opcional)"}
                    texto_principal= mensajes.get(naturaleza, mensajes["Informativa"])
                    boton_principal= "Ajustar RA técnico"
                else:
                    mensajes= {"Positiva": "¿Sumar puntos en alguna competencia por esto? (opcional)",
                                "Negativa": "¿Restar puntos en alguna competencia por esto? (opcional)",
                                "Informativa": "¿Reflejar esto en alguna competencia? (opcional)"}
                    texto_principal= mensajes.get(naturaleza, mensajes["Informativa"])
                    boton_principal= "Ajustar competencia"

            if texto_principal or ofrece_entrega:
                self._ultimo_ajuste= {
                    "estudiante_id": estudiante_id, "observacion_id": observacion_id_nueva,
                    "texto": texto, "naturaleza": naturaleza, "materia_id": materia_id,
                    "es_tecnica": es_tecnica,
                    #Sin sugerencia de calificación, el botón PRINCIPAL pasa a abrir directamente "Marcar entrega" (no tendría
                    #sentido un botón principal vacío con la acción real escondida en el secundario).
                    "solo_entrega": texto_principal is None,
                }
                if texto_principal:
                    self.cinta_ajuste.mostrar_para(
                        texto_principal, texto_boton=boton_principal,
                        texto_boton_secundario= "Marcar entrega" if ofrece_entrega else None)
                else:
                    self.cinta_ajuste.mostrar_para(
                        "¿Marcar el estado de esta entrega por esto? (opcional)",
                        texto_boton= "Marcar entrega")
            else:
                self.cinta_ajuste.ocultar()
        else:
            self.cinta_ajuste.ocultar()

        self._limpiar()
        self.paginacion.reiniciar()
        self._cargar_tabla()

    #Despacha el clic en el botón PRINCIPAL de la cinta de sugerencia, según
    #lo que se resolvió al guardar la observación (ver _guardar): 'Ajustar
    #competencia', 'Ajustar RA técnico', o -si esa fue la única sugerencia
    #aplicable- 'Marcar entrega'. El botón SECUNDARIO ('Marcar entrega', cuando
    #aparece junto a una de calificación) va directo por su propia señal
    #(ajustar_secundario -> _abrir_ajuste_entrega, conectado en _build_ui).
    def _al_pulsar_ajustar(self):

        datos_previos= getattr(self, "_ultimo_ajuste", None)
        if not datos_previos:
            return
        if datos_previos.get("solo_entrega"):
            self._abrir_ajuste_entrega()
        elif datos_previos.get("es_tecnica"):
            self._abrir_ajuste_ra()
        else:
            self._abrir_ajuste_competencia()

    def _abrir_ajuste_ra(self):

        datos_previos= getattr(self, "_ultimo_ajuste", None)
        if not datos_previos:
            return
        dialogo= DialogoAjusteRA(self.main_window, datos_previos["estudiante_id"], datos_previos["texto"],
                                   datos_previos["naturaleza"], self,
                                   materia_id_sugerida= datos_previos.get("materia_id"))
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        d= dialogo.datos()
        if d["ra_id"] is None or d["materia_id"] is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Selecciona un módulo técnico con Resultados de Aprendizaje y un RA.", self)
            return
        if d["ajuste"] is None and not d["domina"]:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Elige si el estudiante es Competente o No Competente.", self)
            return
        guardar_ajuste_ra(self.main_window, datos_previos["estudiante_id"], d["ra_id"], d["anio"],
                           d["ajuste"], d["domina"], datos_previos["texto"])
        self.cinta_ajuste.ocultar()
        mostrar_mensaje("exito", "Ajuste registrado",
                         "Se registró el ajuste en el Resultado de Aprendizaje elegido.", self)

    def _abrir_ajuste_entrega(self):

        datos_previos= getattr(self, "_ultimo_ajuste", None)
        if not datos_previos:
            return
        dialogo= DialogoAjusteEntrega(datos_previos["estudiante_id"], datos_previos["texto"],
                                        datos_previos["naturaleza"], datos_previos.get("materia_id"), self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        d= dialogo.datos()
        if d["tarea_id"] is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona una tarea.", self)
            return
        guardar_ajuste_entrega(self.main_window, datos_previos["estudiante_id"], d["tarea_id"], d["estado"],
                                datos_previos["texto"])
        self.cinta_ajuste.ocultar()
        mostrar_mensaje("exito", "Entrega marcada",
                         f"Se marcó la entrega como \"{d['estado']}\".", self)

    def _abrir_ajuste_competencia(self):

        datos_previos= getattr(self, "_ultimo_ajuste", None)
        if not datos_previos:
            return
        dialogo= DialogoAjusteCompetencia(datos_previos["estudiante_id"], datos_previos["texto"],
                                            datos_previos["naturaleza"], self,
                                            materia_id_sugerida= datos_previos.get("materia_id"))
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        d= dialogo.datos()
        if d["competencia_id"] is None or d["periodo_id"] is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Selecciona una materia con Competencias Específicas y un periodo.", self)
            return

        conn= obtener_conexion()
        c= conn.cursor()
        #Nota base: la nota ya calculada de esa competencia en ese periodo (si hay evidencias), o la nota mínima
        #institucional si todavía no hay ninguna.
        c.execute("""SELECT calificaciones.valor as valor, calificaciones.peso as peso
                     FROM calificacion_competencia
                     JOIN calificaciones ON calificacion_competencia.calificacion_id = calificaciones.id
                     WHERE calificacion_competencia.competencia_id=? AND calificaciones.estudiante_id=?
                     AND calificaciones.periodo_id=? AND calificaciones.estado_publicacion != 'Borrador'""",
                  (d["competencia_id"], datos_previos["estudiante_id"], d["periodo_id"]))
        evidencias= [dict(f) for f in c.fetchall()]
        c.execute("""SELECT metodo_calculo, nota_minima, nota_minima_primaria, nota_minima_secundaria,
                     sistema_calificacion FROM configuracion WHERE id=1""")
        cfg= c.fetchone()
        metodo= cfg["metodo_calculo"] if cfg else "Promedio Ponderado"
        #Nota mínima institucional (fallback cuando no hay evidencias todavía):
        #se resuelve por nivel educativo del Grado del estudiante, igual que en
        #Calificaciones (ver resolver_nota_minima en configuracion.py).
        c.execute("""SELECT grados.nivel_educativo as nivel FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id WHERE estudiantes.id=?""",
                  (datos_previos["estudiante_id"],))
        f_nivel= c.fetchone()
        nivel_educativo= f_nivel["nivel"] if f_nivel else None
        nota_minima_institucional= resolver_nota_minima(cfg, nivel_educativo=nivel_educativo) if cfg else 70
        base= calcular_nota_final(evidencias, metodo) if evidencias else nota_minima_institucional
        nueva_nota= max(0, min(100, (base or 0) + d["ajuste"]))

        signo= "+" if d["ajuste"] >= 0 else ""
        texto_obs= datos_previos["texto"]
        c.execute("""INSERT INTO calificaciones (estudiante_id, materia_id, periodo_id, categoria,
                     descripcion, valor, peso, estado_publicacion, origen_observacion_id)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (datos_previos["estudiante_id"], d["materia_id"], d["periodo_id"], "Ajuste por Observación",
                   f"Ajuste por observación ({signo}{d['ajuste']} pts): {texto_obs[:80]}",
                   nueva_nota, 15, "Publicada", datos_previos["observacion_id"]))
        calificacion_id= c.lastrowid
        c.execute("INSERT OR IGNORE INTO calificacion_competencia (calificacion_id, competencia_id) VALUES (?,?)",
                  (calificacion_id, d["competencia_id"]))
        conn.commit()
        conn.close()
        registrar_auditoria("Observaciones", "Ajustó competencia desde una observación",
                             self.main_window.usuario_actual,
                             f"Estudiante ID {datos_previos['estudiante_id']} - {signo}{d['ajuste']} pts")
        self.cinta_ajuste.ocultar()
        mostrar_mensaje("exito", "Ajuste registrado",
                         f"Se registró el ajuste ({signo}{d['ajuste']} pts) en la competencia elegida.", self)

    def _puede_editar_fila(self, fila):

        if self.gerencial:
            return True
        return fila["usuario_id"] == getattr(self.main_window, "id_usuario_actual", None)

    def _puede_editar_id(self, id_obs):

        for fila in self.observaciones_pagina:
            if fila["id"] == id_obs:
                return self._puede_editar_fila(fila)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT usuario_id FROM observaciones WHERE id=?", (id_obs,))
        f= c.fetchone()
        conn.close()
        return bool(f) and self._puede_editar_fila(f)

    def _cargar_para_editar(self, id_obs):

        fila= next((f for f in self.observaciones_pagina if f["id"] == id_obs), None)
        if fila is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT * FROM observaciones WHERE id=?", (id_obs,))
            fila= c.fetchone()
            conn.close()
        if fila is None:
            return
        if not self._puede_editar_fila(fila):
            mostrar_mensaje("advertencia", "Sin permisos", "Solo puedes editar tus propias observaciones.", self)
            return
        self.id_edicion= fila["id"]
        preseleccionar_curso_y_seccion(self.combo_grado_form, self.combo_seccion_form,
                                        fila["seccion_id"], incluir_todas=False)
        self._cargar_combo_estudiantes()
        idx= self.combo_estudiante.findData(fila["estudiante_id"])
        self.combo_estudiante.setCurrentIndex(idx if idx >= 0 else 0)
        self._cargar_combo_materias_obs()
        idx_materia= self.combo_materia_obs.findData(fila["materia_id"])
        self.combo_materia_obs.setCurrentIndex(idx_materia if idx_materia >= 0 else 0)
        self.in_texto.setPlainText(fila["texto"] or "")
        self.segmentado.establecer_valor(fila["naturaleza"] or "Informativa", animar=False)
        claves_activas= set((fila["categorias"] or "").split(","))
        for clave, chip in self.chips_categoria.items():
            chip.establecer_marcado(clave in claves_activas, animar=False, emitir=False)
        self._sugerencias_descartadas= False
        self._actualizar_sugerencias()
        if hasattr(self, "panel_form_observacion"):
            self.panel_form_observacion.expandir(True, animar=False)  #de golpe al editar
        self.scroll.verticalScrollBar().setValue(0)
        activar_modo_edicion(self.in_texto, "Editando observación")

    def _eliminar_id(self, id_obs):

        fila= next((f for f in self.observaciones_pagina if f["id"] == id_obs), None)
        if fila is None or not self._puede_editar_fila(fila):
            mostrar_mensaje("advertencia", "Sin permisos", "Solo puedes eliminar tus propias observaciones.", self)
            return
        estudiante= fila["nombre_est"] or ""
        if mostrar_mensaje("pregunta", "Confirmar", f"¿Eliminar esta observación de '{estudiante}'?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            c.execute("DELETE FROM observaciones WHERE id=?", (id_obs,))
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            mostrar_mensaje("advertencia", "No se pudo eliminar",
                             "Ocurrió un problema eliminando la observación. Intenta de nuevo.", self)
            return
        conn.close()
        registrar_auditoria("Observaciones", "Eliminó observación", self.main_window.usuario_actual, estudiante)
        self._cargar_tabla()

    def _limpiar(self):

        self.id_edicion= None
        self.in_texto.clear()
        self.segmentado.establecer_valor("Informativa", animar=False)
        for chip in self.chips_categoria.values():
            chip.establecer_marcado(False, animar=False, emitir=False)
        self._sugerencias_descartadas= False
        self._reconstruir_chips_sugeridas([])
        self._cargar_combo_estudiantes()
        self._cargar_combo_materias_obs()
        desactivar_modo_edicion(self.in_texto)

    #FILTROS
    def _clic_filtro_naturaleza(self, clave_clicada):

        for clave, chip in self.chips_filtro_naturaleza.items():
            chip.establecer_marcado(clave == clave_clicada, animar=True, emitir=False)
        self._filtro_naturaleza= None if clave_clicada == "todas" else clave_clicada
        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _al_pulsar_banner_destacadas(self):

        if self.panel_avanzado.maximumHeight() == 0:
            self._alternar_panel_avanzado()
        self.chip_destacadas.establecer_marcado(True)

    def _limpiar_filtros(self):

        self.in_buscar.blockSignals(True)
        self.in_buscar.clear()
        self.in_buscar.blockSignals(False)
        self.combo_filtro_grado.blockSignals(True)
        self.combo_filtro_grado.setCurrentIndex(0)
        self.combo_filtro_grado.blockSignals(False)
        self._grado_filtro_cambio()
        for clave, chip in self.chips_filtro_naturaleza.items():
            chip.establecer_marcado(clave == "todas", animar=False, emitir=False)
        self._filtro_naturaleza= None
        self.chip_destacadas.establecer_marcado(False, animar=False, emitir=False)
        for chip in self.chips_categoria_filtro.values():
            chip.establecer_marcado(False, animar=False, emitir=False)
        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _filtro_cambio(self):

        self.paginacion.reiniciar()
        self._cargar_tabla()

    #Carga de la línea de tiempo
    def _observaciones_filtradas(self):

        texto_filtro= _normalizar(self.in_buscar.text().strip())
        seccion_filtro= self.combo_filtro_seccion.currentData()
        grado_filtro= self.combo_filtro_grado.currentData()
        secciones_permitidas= self._secciones_permitidas_ids()
        categorias_filtro= {clave for clave, chip in self.chips_categoria_filtro.items() if chip.esta_marcado()}
        solo_destacadas= self.chip_destacadas.esta_marcado()
        especialidad_filtro= self.combo_filtro_especialidad.currentData() if self._es_politecnico() else None
        carrera_filtro= self.combo_filtro_carrera.currentData() if self._es_universidad() else None

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT observaciones.*,
                            (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as nombre_est,
                            estudiantes.seccion_id as seccion_id,
                            estudiantes.especialidad_id as especialidad_id,
                            estudiantes.carrera_id as carrera_id,
                            estudiantes.numero_lista as numero_lista_est,
                            grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                            secciones.grado_id as grado_id,
                            materias.nombre as materia_nombre, materias.modelo_evaluacion as materia_modelo
                     FROM observaciones
                     LEFT JOIN estudiantes ON observaciones.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN materias ON observaciones.materia_id = materias.id
                     ORDER BY observaciones.fecha DESC, observaciones.id DESC""")
        filas= c.fetchall()
        conn.close()

        visibles= []
        for f in filas:
            if secciones_permitidas is not None and f["seccion_id"] not in secciones_permitidas:
                continue
            if grado_filtro is not None and f["grado_id"] != grado_filtro:
                continue
            if seccion_filtro is not None and f["seccion_id"] != seccion_filtro:
                continue
            if especialidad_filtro is not None and f["especialidad_id"] != especialidad_filtro:
                continue
            if carrera_filtro is not None and f["carrera_id"] != carrera_filtro:
                continue
            if self._filtro_naturaleza and (f["naturaleza"] or "Informativa") != self._filtro_naturaleza:
                continue
            if solo_destacadas and not f["destacada"]:
                continue
            if categorias_filtro:
                claves_fila= set((f["categorias"] or "").split(","))
                if not (claves_fila & categorias_filtro):
                    continue
            if texto_filtro:
                objetivo= " ".join([
                    f["nombre_est"] or "", f["grado_nombre"] or "", f["seccion_nombre"] or "", f["texto"] or "",
                ])
                if texto_filtro not in _normalizar(objetivo):
                    continue
            visibles.append(f)
        return visibles

    def _cargar_tabla(self):

        visibles= self._observaciones_filtradas()

        self._actualizar_estadisticas(visibles)

        self.paginacion.establecer_total(len(visibles))
        inicio, fin= self.paginacion.rango_actual()
        pagina= visibles[inicio:fin]
        self.observaciones_pagina= pagina

        #El Número de Lista solo tiene sentido con UNA sección concreta a la vista (es un "1..n dentro de esa sección")
        #y, si la institución usa Área Técnica/Carrera, también con esas concretas -ver
        #bd.mostrar_columna_numero_lista-; si cualquiera de esos filtros está en "Todas/Todos", se oculta la columna en
        #vez de mostrar números de distintos grupos mezclados sin ningún orden real.
        seccion_filtro_actual= self.combo_filtro_seccion.currentData()
        especialidad_filtro_actual= self.combo_filtro_especialidad.currentData() if self._es_politecnico() else None
        carrera_filtro_actual= self.combo_filtro_carrera.currentData() if self._es_universidad() else None
        mostrar_columna_numero= mostrar_columna_numero_lista(
            self.main_window, seccion_filtro_actual, especialidad_filtro_actual, carrera_filtro_actual)
        self.tabla.setColumnHidden(COL_NUMERO, not mostrar_columna_numero)

        #`tabla_pausada` desactiva repintado/orden/señales de la QTableWidget mientras se llena (ver paginacion.py): en
        #vez de agregar/animar widgets uno a uno como antes, aquí se rellenan celdas de texto, que Qt ya sabe pintar de
        #forma correcta y eficiente sin necesidad de ningún truco de geometría animada — por eso la tabla no puede
        #"bugearse visualmente" del modo en que lo hacía la lista de tarjetas.
        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(pagina))
            self.lbl_vacio.setVisible(not pagina)
            self.tabla.setVisible(bool(pagina))
            txt_sec= self._colores["txt_sec"]
            for i, fila in enumerate(pagina):
                naturaleza= fila["naturaleza"] or "Informativa"
                color= _COLOR_NATURALEZA.get(naturaleza, "#64748B")
                destacada= bool(fila["destacada"])
                alpha_tinte= 46 if self._modo_oscuro_actual else 30

                item_id= QTableWidgetItem(str(fila["id"]))
                item_numero= QTableWidgetItem()
                if mostrar_columna_numero:
                    numero_lista= fila["numero_lista_est"] if "numero_lista_est" in fila.keys() else None
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_tipo= QTableWidgetItem(f" {naturaleza}")
                item_tipo.setIcon(icono_categoria_color(naturaleza, 16))
                item_tipo.setForeground(QColor(color))
                f_tipo= item_tipo.font()
                f_tipo.setBold(True)
                item_tipo.setFont(f_tipo)
                item_destacada= QTableWidgetItem()
                item_destacada.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if destacada:
                    item_destacada.setIcon(icono_emoji("⭐"))
                    item_destacada.setToolTip("Observación destacada — requiere atención")
                item_estudiante= QTableWidgetItem(fila["nombre_est"] or "—")
                f_est= item_estudiante.font()
                f_est.setBold(True)
                item_estudiante.setFont(f_est)
                item_seccion= QTableWidgetItem(fila["seccion_nombre"] or "—")
                item_seccion.setForeground(QColor(txt_sec))
                item_grado= QTableWidgetItem(fila["grado_nombre"] or "—")
                item_grado.setForeground(QColor(txt_sec))
                item_fecha= QTableWidgetItem(_fecha_relativa(fila["fecha"], self.main_window))
                item_fecha.setForeground(QColor(txt_sec))
                item_categorias= QTableWidgetItem("")
                texto_completo= (fila["texto"] or "").strip()
                preview= texto_completo if len(texto_completo) <= 140 else texto_completo[:140].rstrip() + "…"
                item_descripcion= QTableWidgetItem(preview or "—")
                item_descripcion.setToolTip(texto_completo)

                items_fila= [item_id, item_numero, item_tipo, item_destacada, item_estudiante, item_grado,
                              item_seccion, item_fecha, item_categorias, item_descripcion]
                #Tinte suave de toda la fila con el color de su naturaleza — así se conserva, dentro de una tabla real, la
                #misma lectura visual "de un vistazo" que daba el borde de color de las
                #tarjetas (verde=positiva, gris=informativa, rojo=negativa).
                fondo_fila= _color_fila_qcolor(color, alpha_tinte)
                for col, item in enumerate(items_fila):
                    item.setBackground(fondo_fila)
                    self.tabla.setItem(i, col, item)
                #La columna "Categorías" usa un widget con los iconos reales (una fila puede tener varias categorías a la vez,
                #y un QTableWidgetItem solo admite UN icono) en vez de texto; el item de arriba solo aporta el tinte de fondo
                #de la fila.
                widget_categorias= _widget_categorias_fila(fila, txt_sec)
                widget_categorias.setAutoFillBackground(False)
                self.tabla.setCellWidget(i, COL_CATEGORIAS, widget_categorias)
            ajustar_anchos_columnas(self.tabla)

        for boton in (self.btn_editar_seleccionada, self.btn_eliminar_seleccionada):
            boton.setEnabled(bool(pagina))

    #DETALLE / acciones sobre la fila seleccionada
    def _fila_por_indice_tabla(self, indice):

        if 0 <= indice < len(self.observaciones_pagina):
            return self.observaciones_pagina[indice]
        return None

    def _abrir_detalle_fila(self, indice_tabla):

        fila= self._fila_por_indice_tabla(indice_tabla)
        if fila is None:
            return
        naturaleza= fila["naturaleza"] or "Informativa"
        campos= [
            ("Tipo (naturaleza)", naturaleza),
            ("Categorías", _texto_categorias_fila(fila)),
            ("Destacada", "Sí — requiere atención" if fila["destacada"] else "No"),
            ("Estudiante", fila["nombre_est"] or "—"),
            ("Curso", fila["grado_nombre"] or "—"),
            ("Sección", fila["seccion_nombre"] or "—"),
            ("Materia / Módulo", fila["materia_nombre"] or "—"),
            ("Fecha", _fecha_relativa(fila["fecha"], self.main_window)),
            ("Hora exacta", _hora_exacta(fila["fecha"], self.main_window)),
        ]
        texto_completo= (fila["texto"] or "").strip() or "— Sin descripción —"
        extra_botones= [("Ver descripción completa",
                           lambda: mostrar_texto_largo(self, "Descripción completa", texto_completo))]
        mostrar_detalle_campos(self, f"Observación · {fila['nombre_est'] or '—'}", campos,
                                extra_botones= extra_botones)

    def _ver_detalle_seleccionada(self):

        indice= self.tabla.currentRow()
        if indice < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", self)
            return
        self._abrir_detalle_fila(indice)

    def _editar_seleccionada(self):

        fila= self._fila_por_indice_tabla(self.tabla.currentRow())
        if fila is None:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", self)
            return
        self._cargar_para_editar(fila["id"])

    def _eliminar_seleccionada(self):

        fila= self._fila_por_indice_tabla(self.tabla.currentRow())
        if fila is None:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", self)
            return
        self._eliminar_id(fila["id"])

    #ESTADÍSTICAS (integradas en la cabecera y en los chips de filtro — sin una fila aparte de tarjetas KPI)

    def _actualizar_estadisticas(self, visibles):

        self.chip_contador.establecer(len(visibles))

        conteo_naturaleza= {"Positiva": 0, "Informativa": 0, "Negativa": 0}
        for f in visibles:
            clave= f["naturaleza"] or "Informativa"
            if clave in conteo_naturaleza:
                conteo_naturaleza[clave] += 1
        self.chips_filtro_naturaleza["todas"].establecer_contador(len(visibles))
        for clave, chip in self.chips_filtro_naturaleza.items():
            if clave != "todas":
                chip.establecer_contador(conteo_naturaleza.get(clave, 0))

        destacadas= [f for f in visibles if f["destacada"]]
        self.chip_destacadas.establecer_contador(len(destacadas))
        if destacadas:
            self.cinta_destacadas.mostrar_mensaje(
                f"{len(destacadas)} observación(es) importante(s) requieren tu atención")
        else:
            self.cinta_destacadas.ocultar()

        conteo= {}
        for f in visibles:
            for clave in (f["categorias"] or "").split(","):
                if clave:
                    conteo[clave]= conteo.get(clave, 0) + 1
        top= sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)[:5]
        maximo= top[0][1] if top else 0
        for i, barra in enumerate(self.barras_frecuencia):
            if i < len(top):
                clave, cantidad= top[i]
                info= CATEGORIAS_POR_CLAVE.get(clave)
                if info:
                    _c, etiqueta, _p= info
                    barra.establecer_datos(clave, etiqueta, self._colores["accent"], cantidad,
                                            cantidad / maximo if maximo else 0)
                    barra.setVisible(True)
                else:
                    barra.setVisible(False)
            else:
                barra.setVisible(False)
        self.lbl_sin_datos_frecuentes.setVisible(not top)

    def resizeEvent(self, event):

        super().resizeEvent(event)
        #Si el panel avanzado está expandido y el ancho cambia (lo que puede reacomodar los chips en más o menos
        #filas), se sigue el nuevo alto natural en vez de dejarlo recortado o con hueco de sobra.
        if self.panel_avanzado.maximumHeight() > 0:
            self.panel_avanzado.setMaximumHeight(16777215)

    #ENTRADA / TEMA / REFRESCO
    def refrescar(self):

        if hasattr(self, "combo_filtro_nivel"):
            poblar_combo_nivel_educativo(self.combo_filtro_nivel)
        self._cargar_combos_filtro()
        self._cargar_combos_form()
        self._cargar_filtro_tecnico_form()
        self._cargar_combo_estudiantes()
        self._cargar_especialidades_combo_filtro()
        self._cargar_carreras_combo_filtro()
        self._actualizar_resumen_filtros_listado()
        self.lbl_vacio.setVisible(False)
        QTimer.singleShot(0, self._cargar_tabla)

    def actualizar_tema(self):

        self._aplicar_tema_visual()

    def _aplicar_tema_visual(self):

        mw= self.main_window
        tema_actual= getattr(mw, "tema_actual", None)
        modo_oscuro= getattr(mw, "modo_oscuro", True)
        firma= (tema_actual, modo_oscuro)
        if getattr(self, "_firma_tema_aplicada", None) == firma:
            return
        self._firma_tema_aplicada= firma
        self._modo_oscuro_actual= modo_oscuro

        colores= _colores_tema(mw)
        self._colores= colores
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        bg_panel, borde, txt_prim, txt_sec, accent, accent_hv= (
            colores["bg_panel"], colores["bg_btn"], colores["txt_prim"], colores["txt_sec"],
            colores["accent"], colores["accent_hv"])

        #--- Cabecera héroe ---
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 {accent_hv});
                border-radius: 18px;
            }}
            QLabel#IconoCabeceraModulo {{
                background-color: rgba(255, 255, 255, 40); border-radius: 23px; font-size: 22px; color: white;
            }}
            QLabel#TituloCabeceraModulo {{ font-size: 22px; font-weight: 800; color: white; background: transparent; }}
            QLabel#SubtituloCabeceraModulo {{ font-size: 12px; color: rgba(255,255,255,210); background: transparent; }}
        """)
        self.chip_contador.setStyleSheet("""
            QLabel#ChipContador {
                background-color: rgba(255, 255, 255, 40); color: white; border-radius: 14px;
                padding: 7px 16px; font-weight: 700; font-size: 12px;
            }
        """)

        self.cinta_destacadas.aplicar_paleta("#F59E0B")

        for panel in (self.tarjeta_filtros, self.tarjeta_frecuentes, self.tarjeta_form):
            panel.aplicar_paleta(colores)

        bg_chip_inactivo= _hex_a_rgba(txt_sec, 0.14)
        borde_chip_inactivo= _hex_a_rgba(txt_sec, 0.35)
        for chip in self.findChildren(Chip):
            chip.establecer_paleta(bg_chip_inactivo, borde_chip_inactivo, txt_sec)

        self.icono_busqueda.establecer_color(txt_sec)
        self.marco_busqueda.setStyleSheet(f"QFrame {{ background: {_hex_a_rgba(txt_sec, 0.10)}; border-radius: 16px; }}")
        self.in_buscar.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")

        self.segmentado.aplicar_paleta(bg_panel, borde, txt_sec)

        for barra in self.barras_frecuencia:
            barra.establecer_colores(txt_sec, _hex_a_rgba(txt_sec, 0.18))

        accent_suave= _hex_a_rgba(accent, 0.16 if modo_oscuro else 0.10)

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QLabel#DescModulo {{ color: {txt_sec}; background: transparent; font-size: 12px; }}
            QLabel#TituloSeccionModulo {{
                color: {txt_prim}; background: transparent; font-size: 14px; font-weight: 800;
                padding: 2px 0 0 2px;
            }}
            QComboBox {{
                border: 1px solid {borde}; border-radius: 9px; padding: 7px 10px;
                background-color: {bg_panel}; color: {txt_prim};
            }}
            QTextEdit {{
                border: 1px solid {borde}; border-radius: 9px; padding: 8px 10px;
                background-color: {bg_panel}; color: {txt_prim}; selection-background-color: {accent};
            }}
            QTextEdit:focus {{ border: 2px solid {accent}; }}

            QPushButton {{ border-radius: 10px; padding: 9px 16px; font-weight: 600; }}
            QPushButton#BtnAccionAgregar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669); color: white;
            }}
            QPushButton#BtnAccionNeutro {{ background-color: {_hex_a_rgba(txt_sec, 0.16)}; color: {txt_prim}; }}
            QPushButton#BtnAccionEditar {{ background-color: #3B82F6; color: white; }}
            QPushButton#BtnAccionEditar:hover {{ background-color: #2563EB; }}
            QPushButton#BtnAccionEliminar {{ background-color: #EF4444; color: white; }}
            QPushButton#BtnAccionEliminar:hover {{ background-color: #DC2626; }}
            QPushButton#BtnMasFiltros {{
                background-color: {accent_suave}; color: {accent}; padding: 8px 14px; font-size: 12px;
            }}
            QPushButton#BtnMasFiltros:hover {{ background-color: {_hex_a_rgba(accent, 0.26)}; }}
            QPushButton#ChipPlantilla {{
                background: {accent_suave}; color: {accent}; border-radius: 15px; padding: 5px 12px;
                font-weight: 700; font-size: 10px; border: 1px dashed {accent};
            }}
            QPushButton#ChipPlantilla:hover {{ background: {_hex_a_rgba(accent, 0.28)}; }}
            QPushButton#ChipSugerida {{
                background: #F59E0B; color: #1A1200; border-radius: 13px;
                padding: 4px 10px; font-weight: 700; font-size: 10px; border: 1px solid #F59E0B;
            }}
            QPushButton#ChipSugerida:hover {{ background: #FBBF24; border-color: #FBBF24; }}
            QWidget#MarcoSugerencias {{
                background: {_hex_a_rgba('#F59E0B', 0.10)}; border: 1px solid {_hex_a_rgba('#F59E0B', 0.35)};
                border-radius: 10px;
            }}
            QPushButton#BtnCerrarSugerencias {{
                background-color: transparent; color: {txt_sec}; border-radius: 11px;
                padding: 0px; font-weight: 700; font-size: 11px;
            }}
            QPushButton#BtnCerrarSugerencias:hover {{ background-color: {_hex_a_rgba(txt_sec, 0.18)}; }}

            QFrame#TarjetaTabla {{
                background-color: {bg_panel}; border: 1px solid {borde}; border-radius: 14px;
            }}
            QLabel#AvisoVacio {{
                color: {txt_sec}; font-size: 13px; font-weight: 600; padding: 18px; background: transparent;
            }}
            QTableWidget {{
                background-color: transparent; border: none; gridline-color: transparent;
                font-size: 12px; color: {txt_prim};
            }}
            QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {borde}; border-right: 1px solid {borde}; }}
            QTableWidget::item:selected {{
                background-color: {_hex_a_rgba(accent, 0.30 if modo_oscuro else 0.18)}; color: {txt_prim};
            }}
            QHeaderView::section {{
                background-color: {_hex_a_rgba(txt_sec, 0.12)}; color: {txt_sec};
                padding: 8px 10px; border: none; border-bottom: 2px solid {borde};
                border-right: 1px solid {borde};
                font-weight: 800; font-size: 11px; text-transform: uppercase;
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
        """)

        if hasattr(self, "dialogo_filtros_listado"):
            self.dialogo_filtros_listado.setStyleSheet(f"""
                QDialog#DialogoFiltrosObs {{
                    background-color: {bg_panel};
                }}
                QLabel#IconoEncabezadoFiltrosObs {{
                    background-color: {accent};
                    color: white;
                    border-radius: 15px;
                    min-width: 30px; max-width: 30px;
                    min-height: 30px; max-height: 30px;
                    font-size: 14px;
                    qproperty-alignment: AlignCenter;
                }}
                QLabel#TituloEncabezadoFiltrosObs {{
                    font-size: 16px;
                    font-weight: 800;
                    color: {txt_prim};
                    background: transparent;
                }}
                QLabel#SubtituloFiltrosObs {{
                    font-size: 11.5px;
                    color: {txt_sec};
                    background: transparent;
                }}
                QFrame#SeparadorFiltrosObs {{
                    background-color: {borde};
                    max-height: 1px;
                    border: none;
                }}
                QLabel {{
                    color: {txt_prim};
                    font-weight: 700;
                    font-size: 12.5px;
                    background: transparent;
                }}
            """)
        if hasattr(self, "marco_resumen_filtros_listado"):
            self._actualizar_resumen_filtros_listado()
        #colores del tema activo (ver _cargar_tabla), así que si el tema cambia con la tabla ya poblada, se vuelve a
        #cargar para que las filas existentes adopten la paleta nueva (no aplica en el arranque inicial, donde la tabla
        #todavía está vacía y `refrescar()` se encarga de la primera carga).
        if getattr(self, "tabla", None) is not None and self.tabla.rowCount() > 0:
            self._cargar_tabla()