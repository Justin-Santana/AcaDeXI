#Horario.py - calendario semanal dinámico (pintado a medida) v2
#Horario de AcaDeXI — vista semanal tipo calendario, con animaciones y
#carga diferida para que el módulo aparezca al instante desde la barra
#lateral.
#
#Notas de rendimiento (por qué se ve así):
#- La grilla semanal YA NO es un QTableWidget con texto multilínea: es un
#único QWidget que se dibuja con QPainter (VistaSemanalHorario). Eso evita
#el costo de crear cientos de QTableWidgetItem y de recalcular alturas de
#fila con resizeRowsToContents() cada vez que cambia un filtro, que era la
#causa principal de las trabadas al filtrar o hacer scroll.
#- Los datos institucionales y locales se leen de la base UNA sola vez por
#refresco (self._todas_clases). Escribir en el buscador o cambiar un
#filtro NO vuelve a consultar la base: solo se filtra la lista que ya
#está en memoria y se repinta, así que se siente instantáneo.
#- El __init__ del módulo ya NO llama a refrescar(): construye la UI vacía
#(con un estado de carga liviano) y deja que main.py haga su
#QTimer.singleShot(10, pagina.refrescar) de siempre. Así el clic en la
#barra lateral pinta la pantalla al toque; los datos llegan un instante
#después sin congelar la animación de navegación.
import unicodedata
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
QPushButton, QScrollArea, QFrame, QGridLayout, QLineEdit, QTimeEdit, QMessageBox,
QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsOpacityEffect, QDialog,
QColorDialog, QSizePolicy)
from PySide6.QtCore import (Qt, QTime, QTimer, QRectF, QPointF, QMarginsF, QPropertyAnimation, QEasingCurve,
QVariantAnimation, Signal)
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QFont, QFontMetrics, QPen, QBrush, QPixmap, QIcon

from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso, preseleccionar_curso_y_seccion,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo, interseccion_opcional)
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, ICONO_COLOR, ICONO_FILTRO, aplicar_icono_cabecera
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         agregar_boton_pantalla_completa)
from src.nucleo.permisos import (es_profesor_restringido, obtener_materias_permitidas,
    obtener_secciones_permitidas)
from src.nucleo.formato_hora import formatear_hora, aplicar_formato_widget_hora
from src.nucleo.datos_locales_docente import (listar_horario_local, obtener_entrada_horario_local,
    guardar_entrada_horario_local, eliminar_entrada_horario_local,
    obtener_colores_materias_local, guardar_color_materia_local, eliminar_color_materia_local)
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro, html_icono_emoji)

DIAS= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
DIAS_CORTOS= ["L", "M", "X", "J", "V", "S"]

#Paleta de colores para las "materias" del calendario: es intencional que sea independiente del tema de la app
#(como en Google Calendar), para poder distinguir materias de un vistazo aunque el tema activo sea monocolor.
_PALETA_CLASES= [
    ("#6366F1", "#4F46E5"), ("#10B981", "#059669"), ("#F59E0B", "#D97706"),
    ("#EC4899", "#DB2777"), ("#06B6D4", "#0891B2"), ("#8B5CF6", "#7C3AED"),
    ("#F43F5E", "#E11D48"), ("#84CC16", "#65A30D"), ("#3B82F6", "#2563EB"),
    ("#14B8A6", "#0D9488"), ("#F97316", "#EA580C"), ("#A855F7", "#9333EA"),
]

_COLORES_DEFECTO= {
    "texto": "#0F172A", "texto_sec": "#64748B", "panel": "#FFFFFF",
    "borde": "#E2E8F0", "acento": "#6366F1", "acento_hv": "#4F46E5",
}


def _minutos(hora_txt):

    try:

        h, m= hora_txt.strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


_CACHE_INDICE_COLOR_AUTOMATICO= {}


#Color para una materia/nota. Si el docente personalizó ese color
#(overrides), gana la personalización; si no, se usa el color automático
#de siempre (determinado por el propio texto, así es estable entre
#sesiones).
#
#El índice del color automático (sum(ord(c)...) % N) se cachea por texto:
#con una vista institucional completa el mismo nombre de materia se
#repite en decenas/cientos de clases, y antes ese cálculo se rehacía,
#idéntico, en cada una de ellas en cada repintado.
def _color_para(texto, overrides=None):

    if overrides and texto in overrides:
        return overrides[texto]
    if not texto:
        return _PALETA_CLASES[0]
    indice= _CACHE_INDICE_COLOR_AUTOMATICO.get(texto)
    if indice is None:
        indice= sum(ord(c) for c in texto) % len(_PALETA_CLASES)
        _CACHE_INDICE_COLOR_AUTOMATICO[texto]= indice
    return _PALETA_CLASES[indice]


#Quita mayúsculas y acentos para que el buscador no sea estricto:
#'matemáticas', 'Matemáticas' y 'MATEMATICAS' encuentran lo mismo.
def _normalizar(texto):

    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


def _colores_tema(main_window):

    try:

        paleta= main_window.theme_palettes[main_window.tema_actual]
        idx= 1 if main_window.modo_oscuro else 0
        return {
            "texto": paleta["text_primary"][idx],
            "texto_sec": paleta["text_secondary"][idx],
            "panel": paleta["display_bg"][idx],
            "borde": paleta["btn_num_bg"][idx],
            "acento": paleta["btn_op_bg"][idx],
            "acento_hv": paleta["btn_op_hover"][idx],
        }
    except Exception:
        return dict(_COLORES_DEFECTO)


#Panel desplegable (acordeón animado, para no abarrotar la pantalla)
#Ver la copia idéntica de esta función en calendario.py ▸
#PanelDesplegable: mismo icono circular verde ('+'/'−' dibujados a mano,
#sin depender de que el sistema tenga un glifo instalado) para que
#'Agregar una clase local' luzca igual que el resto de paneles
#colapsables de la app.
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


class PanelDesplegable(QWidget):

    def __init__(self, titulo, parent=None):

        super().__init__(parent)
        self._titulo= titulo
        self._expandido= False
        disposicion= QVBoxLayout(self)
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
        #Ver el mismo cambio en calendario.py ▸ PanelDesplegable: además del maximumHeight, se oculta de verdad
        #(setVisible(False)) mientras está colapsado, para que nunca deje un hueco vacío reservado en el layout de la
        #pestaña con formularios altos como "Agregar una clase local".
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


#Ícono de lupa (dibujado a mano, no depende de que el sistema tenga instalado el glifo del emoji 🔎 — en algunos
#Windows se ve como "|||")
class IconoLupa(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(17, 17)
        self._color= _COLORES_DEFECTO["texto_sec"]

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


#Mini gráfico de barras: carga de clases por día (animado)
#Barras de carga semanal (una por día, aunque el número de columnas que
#llegue a `establecer_datos` puede variar: instituciones sin sábado, por
#ejemplo, envían menos). Tanto el tamaño mínimo como todo lo que se dibuja
#(ancho de barra, tipografías, márgenes) se recalculan a partir de la
#cantidad de valores y del espacio real disponible, así que el gráfico se
#ve bien igual de apretado con 3 columnas que con 10, y también aprovecha
#el espacio extra si el contenedor le da más lugar (no se queda "flotando"
#en una esquina con tamaño fijo).
class CargaSemanalWidget(QWidget):

    ANCHO_MIN_POR_BARRA= 36
    ALTO_MIN= 96

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._valores= [0] * 6
        self._valores_animados= [0.0] * 6
        self._origen= [0.0] * 6
        self._colores= dict(_COLORES_DEFECTO)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(480)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._paso_animacion)
        self._actualizar_tamano_minimo()

    def _actualizar_tamano_minimo(self):

        n= max(len(self._valores), 1)
        self.setMinimumSize(self.ANCHO_MIN_POR_BARRA * n, self.ALTO_MIN)

    def establecer_colores(self, colores):

        self._colores= colores
        self.update()

    def establecer_datos(self, valores):

        self._origen= list(self._valores_animados)
        cambio_cantidad= len(valores) != len(self._valores)
        self._valores= valores
        if cambio_cantidad:
            #La cantidad de columnas cambió (p. ej. cambió de institución o de semana con distinta cantidad de días con
            #clase): ajustamos el arranque de la animación y el tamaño mínimo a la nueva cantidad.
            self._valores_animados= [0.0] * len(valores)
            self._origen= [0.0] * len(valores)
            self._actualizar_tamano_minimo()
            self.updateGeometry()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _paso_animacion(self, t):

        self._valores_animados= [o + (v - o) * t for o, v in zip(self._origen, self._valores)]
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho, alto= self.width(), self.height()
        cantidad= len(self._valores_animados)
        if cantidad == 0:
            return

        #Tipografías proporcionales al alto disponible: con más espacio se ven más grandes (aprovechan el lugar); con
        #poco espacio se achican en vez de desbordarse o solaparse.
        escala= max(0.75, min(1.35, alto / self.ALTO_MIN))
        pt_titulo= max(8, round(9 * escala))
        pt_valor= max(7, round(8 * escala))
        pt_etq= max(7, round(8 * escala))

        titulo= QFont(self.font())
        titulo.setPointSize(pt_titulo)
        titulo.setBold(True)
        painter.setFont(titulo)
        painter.setPen(QColor(self._colores["texto_sec"]))
        alto_titulo= pt_titulo + 8
        painter.drawText(QRectF(0, 0, ancho, alto_titulo), Qt.AlignmentFlag.AlignLeft, "CARGA SEMANAL")

        #El área de arriba reserva SIEMPRE dos franjas fijas: el título y, debajo, el número encima de la barra más
        #alta. Antes pad_sup solo dejaba lugar para el título, así que en columnas angostas (la primera, justo debajo
        #del título) el número quedaba tapado/pegado al texto "CARGA SEMANAL" y no se veía — este es el bug reportado.
        alto_valor= pt_valor + 6
        pad_sup= alto_titulo + 2 + alto_valor
        pad_inf= max(16, round(alto * 0.18))
        alto_disp= max(alto - pad_sup - pad_inf, 10)
        maximo= max(max(self._valores) if self._valores else 0, 1)
        espacio= ancho / cantidad
        #El ancho de barra ya no tiene un tope fijo de 24px: escala con el espacio real por columna, así con pocas
        #columnas las barras se ven más gruesas y con muchas no se aplastan más de lo necesario.
        ancho_barra= max(6, min(espacio * 0.6, 44))
        #Ancho reservado para el número/etiqueta de cada columna: nunca más que el espacio de su propia columna (con un
        #pequeño margen), para que con valores grandes (muchas materias en un día) el texto se achique en vez de
        #"dispararse" sobre las columnas vecinas.
        ancho_texto_col= max(espacio - 4, 16)

        f_valor= QFont(self.font())
        f_valor.setPointSize(pt_valor)
        f_valor.setBold(True)
        f_etq= QFont(self.font())
        f_etq.setPointSize(pt_etq)

        for i, v in enumerate(self._valores_animados):
            cx= espacio * i + espacio / 2
            h= (v / maximo) * alto_disp if maximo else 0
            y_top= pad_sup + (alto_disp - h)
            rect= QRectF(cx - ancho_barra / 2, y_top, ancho_barra, max(h, 3))
            grad= QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, QColor(self._colores["acento"]))
            grad.setColorAt(1, QColor(self._colores["acento_hv"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(rect, 6, 6)

            valor_real= self._valores[i] if i < len(self._valores) else 0
            if valor_real:
                texto_valor= str(valor_real)
                f_valor_col= QFont(f_valor)
                metrica_valor= QFontMetrics(f_valor_col)
                #Si el número no entra en el ancho de su propia columna (valores de dos, tres o más dígitos cuando hay muchas
                #materias en un día), lo vamos achicando hasta que quepa, en vez de dejar que se monte sobre los números
                #vecinos.
                while (metrica_valor.horizontalAdvance(texto_valor) > ancho_texto_col
                       and f_valor_col.pointSize() > 6):
                    f_valor_col.setPointSize(f_valor_col.pointSize() - 1)
                    metrica_valor= QFontMetrics(f_valor_col)
                painter.setFont(f_valor_col)
                painter.setPen(QColor(self._colores["texto"]))
                painter.drawText(QRectF(cx - ancho_texto_col / 2, y_top - alto_valor,
                                         ancho_texto_col, alto_valor - 2),
                                  Qt.AlignmentFlag.AlignCenter, texto_valor)
            painter.setFont(f_etq)
            painter.setPen(QColor(self._colores["texto_sec"]))
            painter.drawText(QRectF(cx - ancho_texto_col / 2, alto - pad_inf + 3, ancho_texto_col, 14),
                              Qt.AlignmentFlag.AlignCenter, DIAS_CORTOS[i])


#ANILLO: proporción de clases institucionales vs. locales (animado)
class AnilloProporcionWidget(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(88, 88)
        self._fraccion_animada= 0.0
        self._texto_centro= "0"
        self._colores= dict(_COLORES_DEFECTO)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._paso)

    def establecer_colores(self, colores):

        self._colores= colores
        self.update()

    def establecer(self, institucionales, locales):

        total= institucionales + locales
        objetivo= (institucionales / total) if total else 0.0
        self._texto_centro= str(total)
        self._anim.stop()
        self._anim.setStartValue(self._fraccion_animada)
        self._anim.setEndValue(objetivo)
        self._anim.start()

    def _paso(self, v):

        self._fraccion_animada= v
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grosor= 9
        rect= QRectF(grosor / 2 + 2, grosor / 2 + 2,
                       self.width() - grosor - 4, self.height() - grosor - 4)

        pen_local= QPen(QColor("#F59E0B"), grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_local)
        painter.drawArc(rect, 0, 360 * 16)

        pen_inst= QPen(QColor(self._colores["acento"]), grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_inst)
        span= int(360 * self._fraccion_animada * 16)
        if span:
            painter.drawArc(rect, 90 * 16, -span)

        fuente= QFont(self.font())
        fuente.setPointSize(13)
        fuente.setBold(True)
        painter.setFont(fuente)
        painter.setPen(QColor(self._colores["texto"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._texto_centro)


#Calendario semanal (pintado a medida, con hover y clic al detalle)
class VistaSemanalHorario(QWidget):

    clase_activada= Signal(dict)
    overflow_activado= Signal(list)

    ALTO_CABECERA= 46
    ALTO_FILA= 70
    ESPACIO_FILA= 14
    ANCHO_GUTTER= 84
    MOSTRAR_MAX= 3

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setMouseTracking(True)
        self._clases= []
        self._franjas= []
        self._hitboxes= []
        self._celda_hitboxes= {}
        self._indice_hover= -1
        hoy= datetime.now().weekday()
        self._hoy_idx= hoy if hoy < 6 else -1
        self._colores= dict(_COLORES_DEFECTO)
        self._colores_materias= {}
        self.main_window= None  #lo asigna el widget contenedor tras crear la vista
        self.setMinimumHeight(self.ALTO_CABECERA + 70)

        #Los 3 iconos que puede llevar un chip (casa/grado/aula) son SIEMPRE el mismo emoji al mismo tamaño -no cambian
        #por clase-, así que se rasterizan UNA sola vez aquí en vez de en cada chip de cada repintado. Con una vista
        #institucional completa (600-800 clases) eso son hasta ~1800 rasterizados de emoji evitados por cada repintado:
        #eran, con diferencia, lo más caro de dibujar.
        self._pm_casa= pixmap_emoji("🏠", 13)
        self._pm_curso= pixmap_emoji("🎓", 12)
        self._pm_aula= pixmap_emoji("📍", 12)

        #OJO: el QGraphicsOpacityEffect NO se deja puesto de forma permanente. Un QGraphicsEffect activo obliga a Qt a
        #renderizar el widget entero a un pixmap fuera de pantalla y componerlo; dentro de un QScrollArea eso provoca
        #que ese pixmap quede "cacheado" con el recorte de la posición de scroll en la que se creó, así que al
        #desplazarte los chips que antes estaban fuera de vista aparecen cortados/fantasma en la parte de arriba (el
        #bug reportado). Por eso el efecto solo se crea justo antes del fundido de entrada y se quita apenas termina;
        #en reposo (que es como pasa la enorme mayoría del tiempo, incluido mientras se hace scroll) el widget se pinta
        #de forma normal, sin ese pixmap.
        self._efecto= None
        self._anim_opacidad= None

    def establecer_colores(self, colores):

        self._colores= colores
        self.update()

    #overrides: {texto_materia_o_nota: (color, color_hv)} con las
    #personalizaciones del docente. Repinta al instante.
    def establecer_colores_materias(self, overrides):

        self._colores_materias= overrides or {}
        self.update()

    def establecer_clases(self, clases, animar=True):

        self._clases= clases
        self._franjas= sorted({(c["hora_inicio"], c["hora_fin"]) for c in clases},
                                #t: franja (inicio, fin); se ordenan por la hora de inicio en minutos
                                key= lambda t: _minutos(t[0]))
        alto_total= self.ALTO_CABECERA + len(self._franjas) * (self.ALTO_FILA + self.ESPACIO_FILA) + 14
        self.setFixedHeight(max(alto_total, self.ALTO_CABECERA + 70))
        self._recalcular_geometria()
        self.update()
        if animar:
            self._iniciar_fundido_entrada()

    def _iniciar_fundido_entrada(self):

        if self._anim_opacidad is not None:
            self._anim_opacidad.stop()
        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(0.35)
        self.setGraphicsEffect(self._efecto)
        self._anim_opacidad= QPropertyAnimation(self._efecto, b"opacity")
        self._anim_opacidad.setDuration(240)
        self._anim_opacidad.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_opacidad.setStartValue(0.35)
        self._anim_opacidad.setEndValue(1.0)
        self._anim_opacidad.finished.connect(self._quitar_efecto_opacidad)
        self._anim_opacidad.start()

    def _quitar_efecto_opacidad(self):

        #Quitamos el efecto (en vez de solo dejarlo en opacidad 1.0) para que el widget vuelva a pintarse de forma
        #normal, sin el pixmap cacheado que causaba el recorte de chips al hacer scroll.
        self.setGraphicsEffect(None)
        self._efecto= None

    def resizeEvent(self, evento):

        super().resizeEvent(evento)
        self._recalcular_geometria()

    def _recalcular_geometria(self):

        self._hitboxes= []
        self._celda_hitboxes= {}
        ancho_dias= max(self.width() - self.ANCHO_GUTTER, 90)
        ancho_col= ancho_dias / len(DIAS)
        self._ancho_col= ancho_col

        celdas= {}
        for c in self._clases:
            try:

                col= DIAS.index(c["dia"])
            except ValueError:
                continue
            franja= (c["hora_inicio"], c["hora_fin"])
            celdas.setdefault((franja, col), []).append(c)

        for fila_idx, franja in enumerate(self._franjas):
            pos_y= self.ALTO_CABECERA + fila_idx * (self.ALTO_FILA + self.ESPACIO_FILA)
            for col in range(len(DIAS)):
                items= celdas.get((franja, col), [])
                if not items:
                    continue
                x0= self.ANCHO_GUTTER + col * ancho_col
                mostrados= items[:self.MOSTRAR_MAX]
                resto= items[self.MOSTRAR_MAX:]
                n_chips= len(mostrados) + (1 if resto else 0)
                margen= 4
                ancho_chip= max((ancho_col - margen * (n_chips + 1)) / n_chips, 20)

                def _agregar(rect, item, fila_idx=fila_idx, col=col):

                    #idx es la posición en self._hitboxes -se usa para que
                    #self._indice_hover (que paintEvent compara por índice)
                    #siga siendo válido aunque el hover se detecte por la ruta rápida (celda) en vez de recorriendo toda la lista.
                    idx= len(self._hitboxes)
                    self._hitboxes.append((rect, item))
                    self._celda_hitboxes.setdefault((fila_idx, col), []).append((idx, rect, item))

                for i, item in enumerate(mostrados):
                    pos_x= x0 + margen + i * (ancho_chip + margen)
                    _agregar(QRectF(pos_x, pos_y, ancho_chip, self.ALTO_FILA), item)
                if resto:
                    pos_x= x0 + margen + len(mostrados) * (ancho_chip + margen)
                    _agregar(QRectF(pos_x, pos_y, ancho_chip, self.ALTO_FILA), {"_overflow": resto})

    def _fila_y(self, indice):

        return self.ALTO_CABECERA + indice * (self.ALTO_FILA + self.ESPACIO_FILA)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho= self.width()
        ancho_col= getattr(self, "_ancho_col", (ancho - self.ANCHO_GUTTER) / len(DIAS))

        #Región realmente dañada (event.rect()), no todo el widget. Cuando el hover invalida solo el rect de un chip
        #(ver mouseMoveEvent), "clip" aquí es ese rect pequeño, y todo lo que sigue lo usa para saltarse el trabajo
        #caro (gradientes, sombras, iconos, texto) de las filas y chips que ni siquiera se van a ver en este repintado.
        clip= QRectF(evento.rect())

        #Fondo tipo "panel" con esquinas redondeadas
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._colores["panel"]))
        painter.drawRoundedRect(QRectF(0, 0, ancho, self.height()), 12, 12)

        #Antes esto rellenaba filas alternas con un color de fondo (efecto "cebra"), que sumado a los chips ya
        #coloreados hacía que todo se viera apretado y saturado -el "eyesore" reportado-. Se cambió por líneas finas de
        #separación entre filas/columnas (inspirado, solo ligeramente, en el diseño de tabla clásica de aSc Horarios):
        #dan la misma sensación de orden y guían el ojo fila por fila, pero sin pelear visualmente con el color de cada
        #chip. El espacio entre filas también se agrandó (ESPACIO_FILA) para que respiren.
        ##Rendimiento: con horarios institucionales completos puede haber muchísimas franjas horarias distintas (grilla
        #muy alta). En vez de dibujar TODAS las líneas/etiquetas de hora aunque el usuario solo esté viendo 8 filas por
        #la ventana/scroll, se calcula el rango de filas que realmente cae dentro de "clip" y solo esas se dibujan.
        fila_alto= self.ALTO_FILA + self.ESPACIO_FILA
        primera_fila= max(0, int((clip.top() - self.ALTO_CABECERA) / fila_alto) - 1)
        ultima_fila= min(len(self._franjas) - 1,
                           int((clip.bottom() - self.ALTO_CABECERA) / fila_alto) + 1)

        pen_separador= QPen(_con_alfa(self._colores["borde"], 90), 1)
        painter.setPen(pen_separador)
        for i in range(max(primera_fila, 0), min(ultima_fila, len(self._franjas) - 1) + 2):
            pos_y= self._fila_y(i) - self.ESPACIO_FILA / 2
            painter.drawLine(QPointF(self.ANCHO_GUTTER - 10, pos_y), QPointF(ancho - 10, pos_y))
        if clip.top() <= self.ALTO_CABECERA:
            for col in range(len(DIAS) + 1):
                pos_x= self.ANCHO_GUTTER + col * ancho_col
                painter.drawLine(QPointF(pos_x, self.ALTO_CABECERA - 4),
                                  QPointF(pos_x, self._fila_y(len(self._franjas)) - self.ESPACIO_FILA / 2))

        #Cabecera de días (solo si el área dañada la incluye)
        if clip.top() <= self.ALTO_CABECERA:
            f_dia= QFont(self.font())
            f_dia.setPointSize(10)
            f_dia.setBold(True)
            for col, nombre in enumerate(DIAS):
                pos_x= self.ANCHO_GUTTER + col * ancho_col
                rect= QRectF(pos_x + 5, 6, ancho_col - 10, self.ALTO_CABECERA - 12)
                if col == self._hoy_idx:
                    grad= QLinearGradient(rect.topLeft(), rect.topRight())
                    grad.setColorAt(0, QColor(self._colores["acento"]))
                    grad.setColorAt(1, QColor(self._colores["acento_hv"]))
                    painter.setBrush(QBrush(grad))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 9, 9)
                    painter.setPen(QColor("#FFFFFF"))
                else:
                    painter.setPen(QColor(self._colores["texto_sec"]))
                painter.setFont(f_dia)
                etiqueta= nombre if col != self._hoy_idx else f"{nombre} • HOY"
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, etiqueta)

        #Etiquetas de hora (gutter) -solo las filas visibles
        f_hora= QFont(self.font())
        f_hora.setPointSize(8)
        painter.setFont(f_hora)
        painter.setPen(QColor(self._colores["texto_sec"]))
        for i in range(max(primera_fila, 0), min(ultima_fila, len(self._franjas) - 1) + 1):
            ini, fin= self._franjas[i]
            pos_y= self._fila_y(i)
            rect= QRectF(4, pos_y, self.ANCHO_GUTTER - 8, self.ALTO_FILA)
            ini_fmt= formatear_hora(ini, self.main_window)
            fin_fmt= formatear_hora(fin, self.main_window)
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                              f"{ini_fmt}\n{fin_fmt}")

        #Chips de clases. Se crean las fuentes/métricas UNA sola vez por
        #repintado (antes _pintar_chip creaba un QFontMetrics nuevo por
        #cada chip, cientos de veces por repintado) y se salta por completo
        #el trabajo de dibujar cualquier chip que no intersecte "clip":
        #con hover, eso reduce el repintado de 600-800 chips a 1 o 2.
        f_titulo= QFont(self.font())
        f_titulo.setPointSize(9)
        f_titulo.setBold(True)
        f_sub= QFont(self.font())
        f_sub.setPointSize(8)
        metrica_titulo= QFontMetrics(f_titulo)
        metrica_sub= QFontMetrics(f_sub)
        for indice, (rect, item) in enumerate(self._hitboxes):
            if not rect.intersects(clip):
                continue
            en_hover= (indice == self._indice_hover)
            if "_overflow" in item:
                self._pintar_chip_overflow(painter, rect, item["_overflow"], en_hover, f_titulo)
                continue
            self._pintar_chip(painter, rect, item, en_hover, f_titulo, f_sub, metrica_titulo, metrica_sub)

    def _pintar_chip(self, painter, rect, item, en_hover, f_titulo, f_sub, metrica, metrica2):

        base, base_hv= _color_para(item.get("materia_nombre") or item.get("notas") or "",
                                     self._colores_materias)
        es_local= bool(item.get("es_local"))
        elevacion= 3 if en_hover else 1

        sombra= rect.translated(0, elevacion)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawRoundedRect(sombra, 9, 9)

        grad= QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(base))
        grad.setColorAt(1, QColor(base_hv))
        painter.setBrush(QBrush(grad))
        if es_local:
            painter.setPen(QPen(QColor("#FFFFFF"), 1.6, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.drawRoundedRect(rect, 9, 9)

        if en_hover:
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)

        interior= rect.adjusted(7, 5, -7, -5)
        titulo= item.get("materia_nombre") or item.get("notas") or "(sin materia)"

        #Curso/Sección en su propia línea (igual que en el resto de la app:
        #Curso y Sección se muestran como su propio dato, no mezclados y aplastados junto con el aula en una sola línea
        #que se corta).
        curso_seccion= " ".join(p for p in (item.get("grado_nombre"), item.get("seccion_nombre_sola")) if p)
        if not curso_seccion:
            curso_seccion= item.get("seccion_nombre") or ""
        aula_texto= item.get("aula_nombre") or ""

        painter.setFont(f_titulo)
        painter.setPen(QColor("#FFFFFF"))
        #"Local" ya se marca con el borde punteado del propio chip (más arriba); el icono de casa aquí solo refuerza
        #visualmente esa misma idea, dibujado como pixmap real -no como caracter de texto, que dependía de la fuente de
        #emoji del sistema operativo y se veía distinto (y a veces monocromo o como cuadro) según el equipo. Los
        #pixmaps ya vienen rasterizados una sola vez desde __init__ (self._pm_*), no se regeneran chip por chip.
        icono_casa= self._pm_casa if es_local else None
        self._dibujar_linea_chip(painter, interior, interior.y(), 18, titulo,
                                  metrica, icono_casa)

        painter.setFont(f_sub)
        painter.setPen(QColor(255, 255, 255, 225))
        y_linea= interior.y() + 19
        if curso_seccion:
            self._dibujar_linea_chip(painter, interior, y_linea, 15, curso_seccion,
                                      metrica2, self._pm_curso)
            y_linea += 15
        #El aula solo se dibuja si todavía cabe dentro del chip (chips en franjas muy cortas se quedan solo con el
        #título y el curso/sección).
        if aula_texto and y_linea + 14 <= interior.y() + interior.height():
            self._dibujar_linea_chip(painter, interior, y_linea, 14, aula_texto,
                                      metrica2, self._pm_aula)

    #Dibuja una línea de texto del chip, con un icono real (QPixmap,
    #NO un caracter emoji dentro del string) opcional a la izquierda.
    #Centraliza el desplazamiento del texto para que el icono nunca
    #quede pisando las letras ni descuadrado entre título/curso/aula.
    def _dibujar_linea_chip(self, painter, interior, y, alto, texto, metrica, icono=None):

        x= interior.x()
        ancho_disponible= interior.width()
        if icono is not None and not icono.isNull():
            tam= icono.width()
            y_icono= y + (alto - tam) / 2
            painter.drawPixmap(QRectF(x, y_icono, tam, tam), icono, QRectF(icono.rect()))
            avance= tam + 4
            x += avance
            ancho_disponible -= avance
        painter.drawText(QRectF(x, y, max(ancho_disponible, 0), alto),
                          Qt.AlignmentFlag.AlignLeft,
                          metrica.elidedText(texto, Qt.TextElideMode.ElideRight, int(max(ancho_disponible, 0))))

    def _pintar_chip_overflow(self, painter, rect, items, en_hover, f_titulo):

        painter.setPen(QPen(QColor(self._colores["texto_sec"]), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(_con_alfa(self._colores["borde"], 140 if en_hover else 90))
        painter.drawRoundedRect(rect, 9, 9)
        painter.setFont(f_titulo)
        painter.setPen(QColor(self._colores["texto"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"+{len(items)}\nmás")

    #Fila/columna bajo el cursor, calculadas directamente por
    #aritmética -O(1)-, sin tocar self._hitboxes.
    def _celda_en(self, punto):

        fila_alto= self.ALTO_FILA + self.ESPACIO_FILA
        rel_y= punto.y() - self.ALTO_CABECERA
        if rel_y < 0 or fila_alto <= 0:
            return None
        fila= int(rel_y // fila_alto)
        if rel_y - fila * fila_alto > self.ALTO_FILA:
            return None  #cayó en el espacio en blanco entre filas
        if fila < 0 or fila >= len(self._franjas):
            return None
        ancho_col= getattr(self, "_ancho_col", None)
        if not ancho_col:
            return None
        rel_x= punto.x() - self.ANCHO_GUTTER
        if rel_x < 0:
            return None
        col= int(rel_x // ancho_col)
        if col < 0 or col >= len(DIAS):
            return None
        return fila, col

    #Encuentra el chip bajo el cursor. Antes recorría self._hitboxes
    #completo (podían ser 600-800 en una vista institucional completa)
    #por cada evento de mouse. Ahora primero calcula en qué celda
    #fila/columna cayó el cursor (_celda_en, O(1)) y solo revisa los
    #3-4 chips que puede haber en esa celda -el resto del horario ni
    #se toca.
    def _item_en(self, punto):

        idx, _rect, item= self._item_en_detalle(punto)
        return item

    def _item_en_detalle(self, punto):

        celda= self._celda_en(punto)
        if celda is None:
            return None, None, None
        for idx, rect, item in self._celda_hitboxes.get(celda, ()):
            if rect.contains(punto):
                return idx, rect, item
        return None, None, None

    def mousePressEvent(self, evento):

        punto= evento.position()
        item= self._item_en(punto)
        if item is not None:
            if "_overflow" in item:
                self.overflow_activado.emit(item["_overflow"])
            else:
                self.clase_activada.emit(item)
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):

        punto= evento.position()
        nuevo, rect_nuevo, item_hover= self._item_en_detalle(punto)
        nuevo= -1 if nuevo is None else nuevo
        if nuevo != self._indice_hover:
            rect_anterior= (self._hitboxes[self._indice_hover][0]
                              if 0 <= self._indice_hover < len(self._hitboxes) else None)
            self._indice_hover= nuevo
            self.setCursor(Qt.CursorShape.PointingHandCursor if nuevo >= 0 else Qt.CursorShape.ArrowCursor)
            #Con celdas muy llenas (varias clases institucionales encimadas en la misma franja) el chip queda tan angosto
            #que el título ni siquiera alcanza a mostrar una letra ("..."). En vez de dejar esa info solo accesible con un
            #clic, el tooltip la muestra al pasar el mouse -sin rasterizar iconos ni tocar la base de datos de nuevo, así
            #que no cuesta nada mostrarlo en cada hover.
            self.setToolTip(self._texto_tooltip(item_hover) if item_hover is not None else "")
            #Antes esto llamaba a self.update() sin argumentos, lo que obliga a Qt a repintar los 600-800 chips del horario
            #institucional completo por cada pixel que se movía el mouse -de ahí la sensación de traba al pasar por encima
            #del calendario-. Invalidando solo el rectángulo del chip que deja de resaltarse y el que empieza a resaltarse
            #(con un margen para la sombra), paintEvent recorta el resto del trabajo casi por completo (ver el chequeo de
            #"clip" ahí).
            margen_sombra= QMarginsF(2, 2, 2, 6)
            if rect_anterior is not None:
                self.update(rect_anterior.marginsAdded(margen_sombra).toAlignedRect())
            if rect_nuevo is not None:
                self.update(rect_nuevo.marginsAdded(margen_sombra).toAlignedRect())
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):

        if self._indice_hover != -1:
            rect_anterior= (self._hitboxes[self._indice_hover][0]
                              if self._indice_hover < len(self._hitboxes) else None)
            self._indice_hover= -1
            self.setToolTip("")
            if rect_anterior is not None:
                self.update(rect_anterior.marginsAdded(QMarginsF(2, 2, 2, 6)).toAlignedRect())
            else:
                self.update()
        super().leaveEvent(evento)

    def _texto_tooltip(self, item):

        if "_overflow" in item:
            resto= item["_overflow"]
            lineas= [f"• {it.get('materia_nombre') or it.get('notas') or '(sin materia)'}"
                      for it in resto[:6]]
            texto= f"<b>{len(resto)} clases más en esta franja</b><br>" + "<br>".join(lineas)
            if len(resto) > 6:
                texto += f"<br>… y {len(resto) - 6} más"
            texto += "<br><br><i>Haz clic para ver el detalle completo</i>"
            return texto

        titulo= item.get("materia_nombre") or item.get("notas") or "(sin materia)"
        curso_seccion= " ".join(p for p in (item.get("grado_nombre"), item.get("seccion_nombre_sola")) if p)
        if not curso_seccion:
            curso_seccion= item.get("seccion_nombre") or ""
        partes= [f"<b>{titulo}</b>"]
        if curso_seccion:
            partes.append(curso_seccion)
        partes.append(f"{html_icono_emoji('🕒')} {formatear_hora(item.get('hora_inicio', ''), self.main_window)} - "
                       f"{formatear_hora(item.get('hora_fin', ''), self.main_window)}")
        if item.get("aula_nombre"):
            partes.append(f"{html_icono_emoji('📍')} {item['aula_nombre']}")
        return "<br>".join(partes)


def _con_alfa(hex_color, alfa):

    color= QColor(hex_color)
    color.setAlpha(alfa)
    return color


#Módulo principal
class ModuloHorario(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.restringido= es_profesor_restringido(self.main_window)
        self.id_edicion_local= None
        self._todas_clases= []
        self._entradas_locales= []
        self._cargado_una_vez= False
        self._colores_materias= {}

        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._temporizador_busqueda.timeout.connect(lambda: self._aplicar_filtros(animar=False))

        #Construimos solo la UI (sin tocar la base de datos) para que el módulo se pinte de inmediato al hacer clic en
        #la barra lateral. main.py llama a refrescar() ~10ms después de crear la página.
        self._construir_ui()
        self._refrescar_colores_tema()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Horario"
        #Las clases "locales" (datos_locales_docente.py) son 100% del equipo/docente actual, y el formulario
        #correspondiente (y sus widgets internos, que estos cuatro atajos tocan directamente) solo se construye más
        #abajo cuando self.restringido es True (Modo Docente) -ver _construir_ui-. Para Dirección/Coordinación/Admin ese
        #formulario NO EXISTE: si estos atajos se registraran igual, un Ctrl+G/Ctrl+L/Ctrl+E/Ctrl+Del ahí reventaría
        #contra widgets inexistentes, y encima aparecerían en la ventanita de ayuda como si fueran una acción
        #disponible que no lo es. Por eso solo se registran para el propio docente restringido.
        if self.restringido:
            registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar clase local", self._guardar_local)
            registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario local",
                             self._limpiar_form_local)
            registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar clase local seleccionada",
                             self._cargar_local_seleccionada)
            registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar clase local", self._eliminar_local)
        registrar_atajo(self, self.main_window, "F5", "Actualizar horario", self.refrescar)

    #--------------------------------------------------------
    def _construir_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.verticalScrollBar().setSingleStep(24)  #scroll más suave, sin saltos bruscos

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(14)

        #--- Cabecera tipo "hero": icono + título + descripción + fecha ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("📅", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Horario")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Horario")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        if self.restringido:
            texto_desc= ("Tu horario semanal: las clases institucionales que Dirección/Coordinación ya "
                          "programó, junto con las entradas que tú agregues (marcadas Local). Toca "
                          "cualquier clase del calendario para ver el detalle.")
        else:
            texto_desc= ("Horario semanal institucional. Toca cualquier clase del calendario para ver el "
                          "detalle. Para crear o modificar horarios, ve a Materias ▸ Horarios.")
        self.lbl_subtitulo_cabecera= QLabel(texto_desc)
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        #Chip "Hoy es...": el pin ahora es un icono real (pixmap dibujado con QPainter) en su propia etiqueta, en vez
        #del caracter 📌 pegado al texto -así se ve igual en todos los sistemas operativos.
        self.contenedor_fecha_hoy= QWidget()
        self.contenedor_fecha_hoy.setObjectName("ChipContador")
        _fila_fecha_hoy= QHBoxLayout(self.contenedor_fecha_hoy)
        _fila_fecha_hoy.setContentsMargins(14, 0, 14, 0)
        _fila_fecha_hoy.setSpacing(6)
        self._icono_fecha_hoy= QLabel()
        self._icono_fecha_hoy.setPixmap(pixmap_emoji("📌", 13))
        self._icono_fecha_hoy.setStyleSheet("background: transparent;")
        _fila_fecha_hoy.addWidget(self._icono_fecha_hoy)
        self.lbl_fecha_hoy= QLabel(self._texto_fecha_hoy())
        self.lbl_fecha_hoy.setStyleSheet("background: transparent;")
        _fila_fecha_hoy.addWidget(self.lbl_fecha_hoy)
        cabecera_layout.addWidget(self.contenedor_fecha_hoy, 0, Qt.AlignmentFlag.AlignVCenter)

        if self.restringido:
            self.btn_info_docente= QPushButton("¿Cómo funciona esto?")
            self.btn_info_docente.setIcon(icono_emoji("🧑"))
            self.btn_info_docente.setIconSize(_QSize_emoji(16, 16))
            self.btn_info_docente.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_info_docente.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6);
                    color: white; border: none; border-radius: 16px; padding: 7px 16px; font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #7C3AED);
                }
                QPushButton:pressed { background: #4338CA; }
            """)
            self.btn_info_docente.clicked.connect(self._mostrar_info_docente)
            cabecera_layout.addWidget(self.btn_info_docente, 0, Qt.AlignmentFlag.AlignVCenter)

        disposicion.addWidget(self.frame_cabecera)

        #--- Resumen visual: barras de carga + anillo + leyenda ---
        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(22)
        self.carga_semanal= CargaSemanalWidget()
        fila_resumen.addWidget(self.carga_semanal, 1)
        if self.restringido:
            bloque_anillo= QVBoxLayout()
            bloque_anillo.setSpacing(2)
            lbl_anillo_titulo= QLabel("vs")
            lbl_anillo_titulo.setObjectName("DescModulo")
            lbl_anillo_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.anillo_proporcion= AnilloProporcionWidget()
            bloque_anillo.addWidget(lbl_anillo_titulo)
            bloque_anillo.addWidget(self.anillo_proporcion, 0, Qt.AlignmentFlag.AlignCenter)
            fila_resumen.addLayout(bloque_anillo)
        fila_resumen.addLayout(self._construir_leyenda())
        disposicion.addLayout(fila_resumen)

        #--- Buscador (fila propia, con todo el ancho disponible) --- Antes el buscador compartía una sola fila con la
        #etiqueta "Filtrar por:", 3 combos y 2 botones. Con curso+sección+materia ya pidiendo 170/190/190px de mínimo
        #cada uno más los botones, casi no quedaba espacio para el buscador y su placeholder se veía
        #cortado ("Buscar mat…"). Separarlo en su propia fila le da todo
        #el ancho disponible.
        fila_busqueda= QHBoxLayout()
        marco_busqueda= QFrame()
        marco_busqueda.setStyleSheet("""
            QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }
        """)
        lay_busqueda= QHBoxLayout(marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda)
        self.in_busqueda= QLineEdit()
        limitar_campo_texto(self.in_busqueda, 150)
        self.in_busqueda.setPlaceholderText("Buscar materia, sección, aula o nota…")
        self.in_busqueda.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        #_: valor que trae la señal y aquí no se usa
        self.in_busqueda.textChanged.connect(lambda _: self._temporizador_busqueda.start())
        lay_busqueda.addWidget(self.in_busqueda, 1)
        fila_busqueda.addWidget(marco_busqueda, 1)

        #--- Filtros: en vez de apilar Nivel Educativo, Curso/Sección/Materia y Área Técnica/Carrera como filas
        #separadas (quedaba muy cargado de combos, uno debajo del otro), todos viven dentro de una ventanita aparte -no
        #modal- que se abre con este botón, igual que en
        #estudiantes.py (ver _construir_dialogo_filtros / _abrir_dialogo_filtros).
        #Los combos en sí se siguen creando como atributos normales del
        #módulo (más abajo); lo único que cambia es DÓNDE se colocan.
        self.btn_filtros= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros)
        self.btn_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros.setObjectName("BtnAccionNeutro")
        self.btn_filtros.setToolTip("Abrir panel de filtros (nivel educativo, curso, sección, materia, "
                                     "área técnica/carrera)")
        self.btn_filtros.clicked.connect(self._abrir_dialogo_filtros)
        fila_busqueda.addWidget(self.btn_filtros)

        btn_colores= QPushButton("Colores de materias")
        btn_colores.setIcon(icono_emoji("🎨"))
        btn_colores.setIconSize(_QSize_emoji(16, 16))
        btn_colores.setObjectName("BtnAccionNeutro")
        btn_colores.setToolTip("Elige un color propio para cada materia en tu calendario "
                                "(solo se ve en este equipo)")
        btn_colores.clicked.connect(self._abrir_colores_materias)
        fila_busqueda.addWidget(btn_colores)
        disposicion.addLayout(fila_busqueda)

        #--- Combos de filtro: se crean aquí (siguen siendo atributos normales del módulo) pero NO se agregan a ningún
        #layout visible de esta pantalla — viven dentro del diálogo de filtros. ---
        self.combo_filtro_nivel= QComboBox()
        self.combo_filtro_nivel.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filtro_nivel.currentIndexChanged.connect(self._nivel_filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel, "Filtrar por nivel educativo (se combina con Curso/Sección)")

        self.combo_filtro_curso= QComboBox()
        self.combo_filtro_curso.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filtro_curso.setMinimumWidth(170)
        self.combo_filtro_curso.currentIndexChanged.connect(self._curso_filtro_cambio)
        self.combo_filtro_seccion= QComboBox()
        self.combo_filtro_seccion.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filtro_seccion.setMinimumWidth(190)
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_seccion.currentIndexChanged.connect(lambda _: self._aplicar_filtros(animar=False))
        self.combo_filtro_materia= QComboBox()
        self.combo_filtro_materia.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_filtro_materia.setMinimumWidth(190)
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_materia.currentIndexChanged.connect(lambda _: self._aplicar_filtros(animar=False))
        conectar_tooltip_seleccion(self.combo_filtro_materia, "Filtrar por materia")

        #--- Área Técnica (Politécnico) / Carrera (Universidad): solo se
        #muestran (dentro del diálogo) si la institución tiene ese módulo
        #activo. Área Técnica filtra por la especialidad de la sección (secciones.especialidad_id); Carrera filtra por
        #si la sección tiene algún estudiante activo de esa carrera. ---
        self.lbl_filtro_especialidad_hor= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_hor= QComboBox()
        self.combo_filtro_especialidad_hor.setMinimumWidth(210)
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_especialidad_hor.currentIndexChanged.connect(lambda _: self._aplicar_filtros(animar=False))
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_hor,
                                    "Filtrar por área técnica de la sección (Politécnico)")

        self.lbl_filtro_carrera_hor= QLabel("Carrera:")
        self.combo_filtro_carrera_hor= QComboBox()
        self.combo_filtro_carrera_hor.setMinimumWidth(210)
        #_: valor que trae la señal y aquí no se usa
        self.combo_filtro_carrera_hor.currentIndexChanged.connect(lambda _: self._aplicar_filtros(animar=False))
        conectar_tooltip_seleccion(self.combo_filtro_carrera_hor,
            "Filtrar por carrera: muestra solo secciones con estudiantes de esa carrera (Universidad)")

        self._construir_dialogo_filtros()

        #--- Panel desplegable: agregar clase local (solo docente) ---
        if self.restringido:
            self.panel_local= PanelDesplegable("Agregar una clase local (solo en este equipo)")
            cuerpo= self.panel_local.cuerpo_layout()

            lbl_aviso= QLabel(
                "No es recomendable crear tu horario manualmente aquí. Lo ideal es que Dirección/"
                "Coordinación programe tus clases en el módulo institucional y te reexporte el paquete "
                "desde Copias de Seguridad ▸ Importar Estudiantes y Cursos. Usa este panel solo para "
                "casos puntuales. Lo que agregues aquí se guarda SOLO en este equipo.")
            lbl_aviso.setObjectName("DescModulo")
            lbl_aviso.setWordWrap(True)
            cuerpo.addWidget(lbl_aviso)

            form_local= QGridLayout()
            form_local.setHorizontalSpacing(12)
            form_local.setVerticalSpacing(10)
            form_local.setColumnStretch(1, 1)
            form_local.setColumnStretch(3, 1)

            #Área Técnica (Politécnico) / Carrera (Universidad): en SU PROPIA fila, ARRIBA de Materia/Curso/Sección (se
            #eligen primero) — acota qué secciones aparecen en "Curso"/"Sección" de abajo. Solo se muestran si la
            #institución tiene ese módulo activo. Igual que el resto del módulo, no se guarda como dato nuevo -es un filtro
            #para armar la lista de secciones-.
            frame_filtro_tecnico_local= QFrame()
            frame_filtro_tecnico_local.setObjectName("CuadroFiltroTecnico")
            frame_filtro_tecnico_local.setStyleSheet(
                "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
                "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
            fila_filtro_tecnico_local= QHBoxLayout(frame_filtro_tecnico_local)
            fila_filtro_tecnico_local.setContentsMargins(14, 10, 14, 10)
            fila_filtro_tecnico_local.setSpacing(16)
            self.lbl_filtro_especialidad_local= QLabel("Área Técnica:")
            self.combo_filtro_especialidad_local= QComboBox()
            self.combo_filtro_especialidad_local.setMinimumWidth(210)
            self.combo_filtro_especialidad_local.currentIndexChanged.connect(self._cargar_combos_edicion_local)
            conectar_tooltip_seleccion(self.combo_filtro_especialidad_local,
                "Acota Curso/Sección a esta área técnica (Politécnico)")
            fila_filtro_tecnico_local.addWidget(self.lbl_filtro_especialidad_local)
            fila_filtro_tecnico_local.addWidget(self.combo_filtro_especialidad_local)
            self.lbl_filtro_carrera_local= QLabel("Carrera:")
            self.combo_filtro_carrera_local= QComboBox()
            self.combo_filtro_carrera_local.setMinimumWidth(210)
            self.combo_filtro_carrera_local.currentIndexChanged.connect(self._cargar_combos_edicion_local)
            conectar_tooltip_seleccion(self.combo_filtro_carrera_local,
                "Acota Curso/Sección a las que tienen estudiantes de esta carrera (Universidad)")
            fila_filtro_tecnico_local.addWidget(self.lbl_filtro_carrera_local)
            fila_filtro_tecnico_local.addWidget(self.combo_filtro_carrera_local)
            fila_filtro_tecnico_local.addStretch()
            cuerpo.addWidget(frame_filtro_tecnico_local)

            self.combo_materia_local= QComboBox()
            self.combo_materia_local.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.combo_materia_local.setMinimumWidth(190)
            conectar_tooltip_seleccion(self.combo_materia_local, "Materia de esta clase local")
            self.combo_curso_local= QComboBox()
            self.combo_curso_local.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.combo_curso_local.setMinimumWidth(190)
            self.combo_curso_local.currentIndexChanged.connect(self._curso_local_cambio)
            self.combo_seccion_local= QComboBox()
            self.combo_seccion_local.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.combo_seccion_local.setMinimumWidth(190)
            self.combo_dia_local= QComboBox()
            self.combo_dia_local.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.combo_dia_local.setMinimumWidth(190)
            self.combo_dia_local.addItems(DIAS)
            conectar_tooltip_seleccion(self.combo_dia_local, "Día de la semana de esta clase local")
            self.time_inicio_local= QTimeEdit()
            self.time_inicio_local.setTime(QTime(8, 0))
            self.time_fin_local= QTimeEdit()
            self.time_fin_local.setTime(QTime(9, 0))
            aplicar_formato_widget_hora(self.time_inicio_local, self.main_window)
            aplicar_formato_widget_hora(self.time_fin_local, self.main_window)
            self.in_aula_local= QLineEdit()
            self.in_aula_local.setPlaceholderText("Aula (opcional)")
            limitar_campo_texto(self.in_aula_local, 300)
            self.in_notas_local= QLineEdit()
            self.in_notas_local.setPlaceholderText("Notas (opcional)")
            limitar_campo_texto(self.in_notas_local, 300)
            form_local.addWidget(QLabel("Materia:"), 0, 0)
            form_local.addWidget(self.combo_materia_local, 0, 1)
            form_local.addWidget(QLabel("Curso:"), 0, 2)
            form_local.addWidget(self.combo_curso_local, 0, 3)
            form_local.addWidget(QLabel("Sección:"), 1, 0)
            form_local.addWidget(self.combo_seccion_local, 1, 1)
            form_local.addWidget(QLabel("Día:"), 1, 2)
            form_local.addWidget(self.combo_dia_local, 1, 3)
            form_local.addWidget(QLabel("Hora inicio:"), 2, 0)
            form_local.addWidget(self.time_inicio_local, 2, 1)
            form_local.addWidget(QLabel("Hora fin:"), 2, 2)
            form_local.addWidget(self.time_fin_local, 2, 3)
            form_local.addWidget(self.in_aula_local, 3, 0, 1, 2)
            form_local.addWidget(self.in_notas_local, 3, 2, 1, 2)
            cuerpo.addLayout(form_local)

            fila_botones_local= QHBoxLayout()
            btn_guardar_local= QPushButton("Guardar Clase Local")
            btn_guardar_local.setIcon(icono_emoji("💾"))
            btn_guardar_local.setIconSize(_QSize_emoji(16, 16))
            btn_guardar_local.setObjectName("BtnAccionAgregar")
            btn_guardar_local.clicked.connect(self._guardar_local)
            fila_botones_local.addWidget(btn_guardar_local)
            btn_limpiar_local= QPushButton("Limpiar")
            btn_limpiar_local.setIcon(icono_emoji("🧹"))
            btn_limpiar_local.setIconSize(_QSize_emoji(16, 16))
            btn_limpiar_local.setObjectName("BtnAccionNeutro")
            btn_limpiar_local.clicked.connect(self._limpiar_form_local)
            fila_botones_local.addWidget(btn_limpiar_local)
            fila_botones_local.addStretch()
            cuerpo.addLayout(fila_botones_local)

            fila_cabecera_tabla_local= QHBoxLayout()
            fila_cabecera_tabla_local.addWidget(QLabel("Mis clases locales:"))
            fila_cabecera_tabla_local.addStretch()
            cuerpo.addLayout(fila_cabecera_tabla_local)
            self.tabla_local= QTableWidget(0, 7)
            aplicar_estructura_tabla(self.tabla_local)

            self.tabla_local.setHorizontalHeaderLabels(
                ["ID", "Día", "Hora", "Materia", "Curso", "Sección", "Aula"])
            self.tabla_local.setColumnHidden(0, True)
            header_local= self.tabla_local.horizontalHeader()
            header_local.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header_local.setStretchLastSection(True)
            self.tabla_local.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.tabla_local.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.tabla_local.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.tabla_local.setAlternatingRowColors(True)
            self.tabla_local.setMinimumHeight(140)
            self.tabla_local.verticalHeader().setVisible(False)
            self._efecto_tabla_local= QGraphicsOpacityEffect(self.tabla_local)
            self._efecto_tabla_local.setOpacity(1.0)
            self.tabla_local.setGraphicsEffect(self._efecto_tabla_local)
            self._anim_tabla_local= QPropertyAnimation(self._efecto_tabla_local, b"opacity")
            self._anim_tabla_local.setDuration(220)
            self._anim_tabla_local.setEasingCurve(QEasingCurve.Type.OutCubic)
            cuerpo.addWidget(self.tabla_local, 1)

            self.paginacion_local= ControlPaginacion()
            self.paginacion_local.cambio.connect(self._poblar_tabla_local)
            fila_paginacion_local= QHBoxLayout()
            fila_paginacion_local.addStretch()
            fila_paginacion_local.addWidget(self.paginacion_local)
            fila_paginacion_local.addStretch()
            cuerpo.addLayout(fila_paginacion_local)

            #Botón ⛶ que abre la tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo maximizado
            #-mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-.
            agregar_boton_pantalla_completa(
                fila_cabecera_tabla_local, [self.tabla_local, self.paginacion_local],
                titulo= "Mis clases locales", parent=self)

            fila_acciones_local= QHBoxLayout()
            btn_cargar_local= QPushButton("Cargar Seleccionada")
            btn_cargar_local.setIcon(icono_emoji("✏"))
            btn_cargar_local.setIconSize(_QSize_emoji(16, 16))
            btn_cargar_local.setObjectName("BtnAccionEditar")
            btn_cargar_local.clicked.connect(self._cargar_local_seleccionada)
            fila_acciones_local.addWidget(btn_cargar_local)
            btn_eliminar_local= QPushButton("Eliminar")
            btn_eliminar_local.setIcon(icono_emoji("🗑"))
            btn_eliminar_local.setIconSize(_QSize_emoji(16, 16))
            btn_eliminar_local.setObjectName("BtnAccionEliminar")
            btn_eliminar_local.clicked.connect(self._eliminar_local)
            fila_acciones_local.addWidget(btn_eliminar_local)
            fila_acciones_local.addStretch()
            cuerpo.addLayout(fila_acciones_local)

            disposicion.addWidget(self.panel_local)
            self.panel_local.expandir(False, animar=False)

        #--- Calendario semanal --- Icono real (QPixmap dibujado con QPainter) en vez del emoji ⏳ suelto en el texto
        #-antes dependía de la fuente de emoji del sistema operativo y se veía distinto entre equipos.
        self.lbl_cargando= QWidget()
        _fila_cargando= QHBoxLayout(self.lbl_cargando)
        _fila_cargando.setContentsMargins(0, 0, 0, 0)
        _fila_cargando.setSpacing(6)
        _fila_cargando.addStretch()
        lbl__icono_cargando= QLabel()
        lbl__icono_cargando.setPixmap(pixmap_emoji("⏳", 15))
        _fila_cargando.addWidget(lbl__icono_cargando)
        lbl__txt_cargando= QLabel("Preparando tu horario…")
        lbl__txt_cargando.setObjectName("DescModulo")
        _fila_cargando.addWidget(lbl__txt_cargando)
        _fila_cargando.addStretch()
        disposicion.addWidget(self.lbl_cargando)

        self.lbl_vacio= QLabel("No hay clases que coincidan con la búsqueda o los filtros.")
        self.lbl_vacio.setObjectName("DescModulo")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setVisible(False)
        disposicion.addWidget(self.lbl_vacio)

        self.canvas= VistaSemanalHorario()
        self.canvas.main_window= self.main_window
        self.canvas.clase_activada.connect(self._mostrar_detalle_clase)
        self.canvas.overflow_activado.connect(self._mostrar_detalle_overflow)
        self.canvas.setVisible(False)
        disposicion.addWidget(self.canvas)

        fila_botones= QHBoxLayout()
        btn_actualizar= QPushButton("Actualizar")
        btn_actualizar.setIcon(icono_emoji("🔄"))
        btn_actualizar.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self.refrescar)
        fila_botones.addWidget(btn_actualizar)
        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        disposicion.addStretch()
        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    def _construir_leyenda(self):

        lay= QVBoxLayout()
        lay.setSpacing(4)
        lay.addWidget(self._fila_leyenda("#6366F1", "Institucional"))
        if self.restringido:
            lay.addWidget(self._fila_leyenda("#F59E0B", "Local (solo este equipo)"))
        lay.addStretch()
        return lay

    def _fila_leyenda(self, color, texto):

        fila= QWidget()
        h= QHBoxLayout(fila)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        lbl_punto= QLabel("●")
        lbl_punto.setStyleSheet(f"color: {color}; font-size: 14px;")
        h.addWidget(lbl_punto)
        lbl= QLabel(texto)
        lbl.setObjectName("DescModulo")
        h.addWidget(lbl)
        h.addStretch()
        return fila

    def _texto_fecha_hoy(self):

        try:

            hoy= datetime.now()
            if hoy.weekday() < 6:
                return f"Hoy es {DIAS[hoy.weekday()]}, {hoy.day:02d}/{hoy.month:02d}/{hoy.year}."
            return f"Hoy es Domingo, {hoy.day:02d}/{hoy.month:02d}/{hoy.year}. Sin clases programadas."
        except Exception:
            return ""

    #--------------------------------------------------------
    def _mostrar_info_docente(self):

        mostrar_mensaje("info", "Horario · Modo Docente",
            "Aquí ves tu horario semanal: las clases que Dirección/Coordinación ya programó "
            "institucionalmente, junto con las entradas que tú agregues manualmente (marcadas "
            "con Local).\n\n"
            "Usa el buscador para encontrar una clase por materia, sección, aula o nota (no "
            "importa si usas mayúsculas o acentos). También puedes filtrar por sección o materia.\n\n"
            "Toca cualquier clase del calendario para ver su detalle completo.\n\n"
            "1⃣ Para añadir una clase puntual, abre 'Agregar una clase local', completa el"
            "formulario y pulsa 'Guardar Clase Local'.\n"
            "2⃣ Para editar una clase local existente, selecciónala en la tabla 'Mis clases"
            "locales' y pulsa 'Cargar Seleccionada'.\n"
            "3⃣ Para eliminar una clase local, selecciónala y pulsa 'Eliminar'.\n\n"
            "Todo lo que agregues aquí se guarda SOLO en este equipo (tu Modo Docente). "
            "Dirección/Coordinación no ve ni recibe estos cambios.", self)

    #Diálogo para elegir un color propio por materia en ESTE calendario.
    #Se guarda por usuario, solo en este equipo (no lo ven otros roles).
    def _abrir_colores_materias(self):

        claves= []
        vistos= set()
        for c in self._todas_clases:
            clave= c.get("materia_nombre") or c.get("notas") or ""
            if clave and clave not in vistos:
                vistos.add(clave)
                claves.append(clave)
        #t: nombre de la materia; se ordena sin tildes ni mayúsculas
        claves.sort(key=lambda t: _normalizar(t))

        if not claves:
            mostrar_mensaje("info", "Sin materias", "Todavía no hay clases en tu calendario para colorear.", self)
            return

        dialogo= QDialog(self)
        dialogo.setWindowTitle("Colores de materias")
        aplicar_icono_ventana(dialogo, ICONO_COLOR)
        dialogo.resize(420, 480)
        layout_dlg= QVBoxLayout(dialogo)

        lbl_info= QLabel("Elige un color para cada materia de tu calendario. Se guarda solo en "
                       "este equipo y no afecta lo que ven otros roles.")
        lbl_info.setWordWrap(True)
        layout_dlg.addWidget(lbl_info)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        contenedor= QWidget()
        lay_contenedor= QVBoxLayout(contenedor)
        lay_contenedor.setSpacing(8)

        for clave in claves:
            fila= QHBoxLayout()
            fila.addWidget(QLabel(clave), 1)

            base, base_hv= _color_para(clave, self._colores_materias)
            btn_swatch= QPushButton("Cambiar")
            btn_swatch.setIcon(icono_emoji("🎨"))
            btn_swatch.setIconSize(_QSize_emoji(16, 16))
            btn_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_swatch.setStyleSheet(
                f"QPushButton {{ background-color: {base}; color: white; border: none; "
                f"border-radius: 8px; padding: 6px 12px; font-weight: 600; }}"
            )
            #el primer parámetro absorbe el checked de la señal y no se usa; el valor por defecto fija el de esta vuelta del bucle
            btn_swatch.clicked.connect(lambda _=False, k=clave, b=btn_swatch: self._elegir_color_materia(k, b))
            fila.addWidget(btn_swatch)

            btn_reset= QPushButton("")
            btn_reset.setIcon(icono_emoji("♻"))
            btn_reset.setIconSize(_QSize_emoji(16, 16))
            btn_reset.setToolTip("Restablecer al color automático")
            btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_reset.setFixedWidth(30)
            #el primer parámetro absorbe el checked de la señal y no se usa; el valor por defecto fija el de esta vuelta del bucle
            btn_reset.clicked.connect(lambda _=False, k=clave, b=btn_swatch: self._restablecer_color_materia(k, b))
            fila.addWidget(btn_reset)

            lay_contenedor.addLayout(fila)

        lay_contenedor.addStretch()
        scroll.setWidget(contenedor)
        layout_dlg.addWidget(scroll, 1)

        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(dialogo.accept)
        layout_dlg.addWidget(btn_cerrar)

        dialogo.exec()

    def _elegir_color_materia(self, clave, boton):

        base, _= _color_para(clave, self._colores_materias)
        dialogo_color= QColorDialog(QColor(base), self)
        dialogo_color.setWindowTitle(f"Color para '{clave}'")
        aplicar_icono_ventana(dialogo_color, ICONO_COLOR)
        if dialogo_color.exec() != QDialog.DialogCode.Accepted:
            return
        color= dialogo_color.selectedColor()
        if not color.isValid():
            return
        color_hex= color.name()
        color_hv= color.darker(115).name()
        guardar_color_materia_local(self.main_window, clave, color_hex, color_hv)
        self._colores_materias[clave]= (color_hex, color_hv)
        boton.setStyleSheet(
            f"QPushButton {{ background-color: {color_hex}; color: white; border: none; "
            f"border-radius: 8px; padding: 6px 12px; font-weight: 600; }}"
        )
        self.canvas.establecer_colores_materias(self._colores_materias)

    def _restablecer_color_materia(self, clave, boton):

        eliminar_color_materia_local(self.main_window, clave)
        self._colores_materias.pop(clave, None)
        base, _= _color_para(clave, self._colores_materias)
        boton.setStyleSheet(
            f"QPushButton {{ background-color: {base}; color: white; border: none; "
            f"border-radius: 8px; padding: 6px 12px; font-weight: 600; }}"
        )
        self.canvas.establecer_colores_materias(self._colores_materias)

    def _mostrar_detalle_clase(self, item):

        mostrar_mensaje("info", "Detalle de la Clase", self._texto_detalle(item), self)

    #Antes esto armaba un solo bloque de HTML gigante y se lo pasaba a
    #mostrar_mensaje() (un QMessageBox de tamaño fijo). Con pocas clases
    #no se notaba, pero con decenas -como en una franja compartida por
    #muchos cursos institucionales- el QMessageBox no tiene forma de
    #crecer ni de hacer scroll: el texto se comprime, los iconos se
    #amontonan y la ventana queda rota (ver captura del bug). Un diálogo
    #propio con QScrollArea no tiene ese límite: cabe una clase o
    #quinientas, siempre legible.
    #
    #Rendimiento: _texto_detalle() usa html_icono_emoji(), que RASTERIZA
    #cada emoji a una imagen incrustada en el HTML (necesario para que
    #el QMessageBox de _mostrar_detalle_clase, que no acepta QIcon, los
    #pinte). Repetir eso ~7 veces por clase x 85 clases = cientos de
    #rasterizados síncronos ANTES de que la ventana llegue a pintarse:
    #de ahí la demora y el "no responde". Aquí no hace falta ese truco
    #-el QLabel de esta tarjeta sí acepta emoji normal en el texto- así
    #que se usa un texto liviano sin rasterizar nada. Y para que la
    #ventana aparezca al instante incluso con listas enormes, las
    #tarjetas se agregan en tandas vía QTimer en vez de todas de un
    #tirón: la ventana nunca se congela ni el SO la marca como
    #'no responde', sin importar cuántas clases haya.
    def _mostrar_detalle_overflow(self, items):

        dialogo= QDialog(self)
        dialogo.setWindowTitle(f"{len(items)} clases en esta franja")
        aplicar_icono_ventana(dialogo, ICONO_FILTRO)
        dialogo.resize(460, 620)
        c= _colores_tema(self.main_window)

        layout_dlg= QVBoxLayout(dialogo)
        layout_dlg.setContentsMargins(0, 0, 0, 0)
        layout_dlg.setSpacing(0)

        cabecera= QFrame()
        cabecera.setObjectName("CabeceraOverflowHorario")
        lyt_cab= QVBoxLayout(cabecera)
        lyt_cab.setContentsMargins(22, 18, 22, 16)
        lbl_titulo= QLabel(f"📅 {len(items)} clases en esta misma franja horaria")
        lbl_titulo.setObjectName("TituloOverflowHorario")
        lbl_titulo.setWordWrap(True)
        lyt_cab.addWidget(lbl_titulo)
        lbl_sub= QLabel("Coinciden todas en el mismo día y horario. Revísalas una por una abajo:")
        lbl_sub.setObjectName("SubOverflowHorario")
        lbl_sub.setWordWrap(True)
        lyt_cab.addWidget(lbl_sub)
        layout_dlg.addWidget(cabecera)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        contenedor= QWidget()
        lyt_lista= QVBoxLayout(contenedor)
        lyt_lista.setContentsMargins(18, 16, 18, 16)
        lyt_lista.setSpacing(10)
        scroll.setWidget(contenedor)
        layout_dlg.addWidget(scroll, 1)

        pie= QFrame()
        lyt_pie= QHBoxLayout(pie)
        lyt_pie.setContentsMargins(18, 12, 18, 16)
        lyt_pie.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(dialogo.accept)
        lyt_pie.addWidget(btn_cerrar)
        layout_dlg.addWidget(pie)

        dialogo.setStyleSheet(f"""
            QDialog {{ background-color: {c['panel']}; }}
            QFrame#CabeceraOverflowHorario {{
                background-color: {c['acento']};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
            QLabel#TituloOverflowHorario {{
                color: white; font-size: 15px; font-weight: 700; background: transparent;
            }}
            QLabel#SubOverflowHorario {{
                color: rgba(255, 255, 255, 0.88); font-size: 11px; background: transparent;
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QPushButton {{
                background-color: {c['acento']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 22px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['acento_hv']}; }}
        """)

        #Tandas de 15: cada tanda se agrega en su propio ciclo del event
        #loop (QTimer con delay 0), así la interfaz respira entre tandas
        #y la ventana queda siempre pintada y respondiendo, sin importar si son 85 clases o 850.
        TANDA= 15

        def _agregar_tanda(inicio=0):

            fin= min(inicio + TANDA, len(items))
            for it in items[inicio:fin]:
                lyt_lista.addWidget(self._tarjeta_overflow(it, c))
            if fin < len(items):
                #se difiere al siguiente ciclo de eventos, cuando el widget ya está armado
                QTimer.singleShot(0, lambda: _agregar_tanda(fin))
            else:
                lyt_lista.addStretch()

        #se difiere al siguiente ciclo de eventos, cuando el widget ya está armado
        QTimer.singleShot(0, lambda: _agregar_tanda(0))
        dialogo.exec()

    #Tarjeta liviana para el diálogo de overflow: texto con emoji
    #normal (sin rasterizar), a diferencia de _texto_detalle().
    def _tarjeta_overflow(self, item, c):

        clave= item.get("materia_nombre") or item.get("notas") or ""
        color_barra, _= _color_para(clave, self._colores_materias)

        tarjeta= QFrame()
        tarjeta.setObjectName("TarjetaOverflowHorario")
        tarjeta.setStyleSheet(f"""
            QFrame#TarjetaOverflowHorario {{
                background-color: {c['panel']};
                border: 1px solid {c['borde']};
                border-left: 4px solid {color_barra};
                border-radius: 10px;
            }}
        """)
        lyt_tarjeta= QVBoxLayout(tarjeta)
        lyt_tarjeta.setContentsMargins(14, 10, 14, 10)
        lbl= QLabel(self._texto_detalle_ligero(item))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet(f"color: {c['texto']}; background: transparent; font-size: 12px;")
        lyt_tarjeta.addWidget(lbl)
        return tarjeta

    #Misma info que _texto_detalle(), pero con emoji de texto plano
    #en vez de html_icono_emoji(): esta versión se usa donde se repite
    #muchas veces seguidas (overflow con decenas/cientos de clases) y no
    #puede pagar el costo de rasterizar cada icono cada vez.
    def _texto_detalle_ligero(self, item):

        partes= [f"📚 Materia: {item.get('materia_nombre') or '(sin materia)'}"]
        curso= item.get("grado_nombre")
        seccion_sola= item.get("seccion_nombre_sola")
        if curso:
            partes.append(f"🎓 Curso: {curso}")
        if seccion_sola:
            partes.append(f"🏫 Sección: {seccion_sola}")
        elif item.get("seccion_nombre"):
            partes.append(f"🏫 Sección: {item['seccion_nombre']}")
        if self._es_politecnico() and item.get("especialidad_nombre"):
            partes.append(f"🛠️ Área técnica: {item['especialidad_nombre']}")
        if self._es_universidad() and item.get("carreras_nombres"):
            partes.append(f"🎓 Carrera: {item['carreras_nombres']}")
        partes.append(f"📅 Día: {item.get('dia', '')}")
        partes.append(f"🕒 Horario: {formatear_hora(item.get('hora_inicio', ''), self.main_window)} - "
                       f"{formatear_hora(item.get('hora_fin', ''), self.main_window)}")
        if item.get("aula_nombre"):
            partes.append(f"📍 Aula: {item['aula_nombre']}")
        if item.get("notas"):
            partes.append(f"📝 Notas: {item['notas']}")
        partes.append("Clase local (solo en este equipo)" if item.get("es_local") else "Clase institucional")
        return "<br>".join(partes)

    def _texto_detalle(self, item):

        #Cada línea lleva su icono real (imagen incrustada vía html_icono_emoji, dibujada con QPainter) en vez del
        #caracter emoji suelto de antes -mostrar_mensaje() usa un QMessageBox, que solo puede mostrar imágenes dentro
        #de texto enriquecido (HTML), nunca un QIcon aparte.
        partes= [f"{html_icono_emoji('📚')} Materia: {item.get('materia_nombre') or '(sin materia)'}"]
        curso= item.get("grado_nombre")
        seccion_sola= item.get("seccion_nombre_sola")
        if curso:
            partes.append(f"{html_icono_emoji('🎓')} Curso: {curso}")
        if seccion_sola:
            partes.append(f"{html_icono_emoji('🏫')} Sección: {seccion_sola}")
        elif item.get("seccion_nombre"):
            partes.append(f"{html_icono_emoji('🏫')} Sección: {item['seccion_nombre']}")
        if self._es_politecnico() and item.get("especialidad_nombre"):
            partes.append(f"{html_icono_emoji('🛠️')} Área técnica: {item['especialidad_nombre']}")
        if self._es_universidad() and item.get("carreras_nombres"):
            partes.append(f"{html_icono_emoji('🎓')} Carrera: {item['carreras_nombres']}")
        partes.append(f"{html_icono_emoji('📅')} Día: {item.get('dia', '')}")
        partes.append(f"{html_icono_emoji('🕒')} Horario: {formatear_hora(item.get('hora_inicio', ''), self.main_window)} - "
                       f"{formatear_hora(item.get('hora_fin', ''), self.main_window)}")
        if item.get("aula_nombre"):
            partes.append(f"{html_icono_emoji('📍')} Aula: {item['aula_nombre']}")
        if item.get("notas"):
            partes.append(f"{html_icono_emoji('📝')} Notas: {item['notas']}")
        partes.append("Clase local (solo en este equipo)" if item.get("es_local") else "Clase institucional")
        return "<br>".join(partes)

    #Filtros y búsqueda (todo en memoria, sin volver a tocar la BD)
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

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera solo
    #se muestran/pueblan si la institución tiene ese módulo activo.
    def _cargar_especialidad_carrera_filtro_horario(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_hor.setVisible(es_poli)
        self.combo_filtro_especialidad_hor.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_hor.currentData()
            self.combo_filtro_especialidad_hor.blockSignals(True)
            self.combo_filtro_especialidad_hor.clear()
            self.combo_filtro_especialidad_hor.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_hor.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_hor.findData(actual)
            self.combo_filtro_especialidad_hor.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_hor.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_hor.setVisible(es_uni)
        self.combo_filtro_carrera_hor.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_hor.currentData()
            self.combo_filtro_carrera_hor.blockSignals(True)
            self.combo_filtro_carrera_hor.clear()
            self.combo_filtro_carrera_hor.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_hor.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_carrera_hor.findData(actual)
            self.combo_filtro_carrera_hor.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_hor.blockSignals(False)

    #Secciones que tienen al menos un estudiante activo de esa carrera.
    #Las secciones no llevan carrera_id propio (es un dato por estudiante,
    #no por grupo — a diferencia de especialidad_id, que sí vive en
    #`secciones`), así que se resuelve con una consulta aparte.
    def _secciones_de_la_carrera(self, carrera_id):

        if carrera_id is None:
            return None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                     WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
        secciones= {fila["seccion_id"] for fila in c.fetchall()}
        conn.close()
        return secciones

    #Crea (una sola vez) la ventanita con todos los filtros. No es modal:
    #se puede dejar abierta mientras se ajustan los combos y el calendario
    #de atrás se sigue actualizando en vivo -mismo patrón que en
    #estudiantes.py-.
    def _construir_dialogo_filtros(self):

        self.dialogo_filtros= QDialog(self)
        self.dialogo_filtros.setObjectName("DialogoFiltros")
        self.dialogo_filtros.setWindowTitle("Filtros de Horario")
        aplicar_icono_ventana(self.dialogo_filtros, ICONO_FILTRO)
        self.dialogo_filtros.setModal(False)
        self.dialogo_filtros.setMinimumWidth(340)
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

        lbl_subtitulo= QLabel("Combina los filtros que necesites; el calendario se actualiza al instante.")
        lbl_subtitulo.setObjectName("SubtituloFiltros")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        self.linea_separadora_filtros= QFrame()
        self.linea_separadora_filtros.setFrameShape(QFrame.Shape.HLine)
        self.linea_separadora_filtros.setObjectName("SeparadorFiltros")
        lay_dialogo.addWidget(self.linea_separadora_filtros)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            ("Nivel Educativo:", self.combo_filtro_nivel),
            (None, self.combo_filtro_especialidad_hor),   #etiqueta propia: self.lbl_filtro_especialidad_hor
            (None, self.combo_filtro_carrera_hor),        #etiqueta propia: self.lbl_filtro_carrera_hor
            ("Curso/Grado:", self.combo_filtro_curso),
            ("Sección:", self.combo_filtro_seccion),
            ("Materia:", self.combo_filtro_materia),
        ):
            if combo is self.combo_filtro_especialidad_hor:
                grid.addWidget(self.lbl_filtro_especialidad_hor, fila, 0)
            elif combo is self.combo_filtro_carrera_hor:
                grid.addWidget(self.lbl_filtro_carrera_hor, fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

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

    def _limpiar_filtros(self):

        self.in_busqueda.blockSignals(True)
        self.in_busqueda.clear()
        self.in_busqueda.blockSignals(False)
        self.combo_filtro_curso.blockSignals(True)
        self.combo_filtro_curso.setCurrentIndex(0)
        self.combo_filtro_curso.blockSignals(False)
        self._filtrar_secciones_por_curso()
        self.combo_filtro_seccion.blockSignals(True)
        self.combo_filtro_seccion.setCurrentIndex(0)
        self.combo_filtro_seccion.blockSignals(False)
        self.combo_filtro_materia.blockSignals(True)
        self.combo_filtro_materia.setCurrentIndex(0)
        self.combo_filtro_materia.blockSignals(False)
        if hasattr(self, "combo_filtro_especialidad_hor"):
            self.combo_filtro_especialidad_hor.blockSignals(True)
            self.combo_filtro_especialidad_hor.setCurrentIndex(0)
            self.combo_filtro_especialidad_hor.blockSignals(False)
        if hasattr(self, "combo_filtro_carrera_hor"):
            self.combo_filtro_carrera_hor.blockSignals(True)
            self.combo_filtro_carrera_hor.setCurrentIndex(0)
            self.combo_filtro_carrera_hor.blockSignals(False)
        self._aplicar_filtros(animar=False)

    def _aplicar_filtros(self, animar=True):

        curso_id= self.combo_filtro_curso.currentData() if hasattr(self, "combo_filtro_curso") else None
        seccion_id= self.combo_filtro_seccion.currentData() if hasattr(self, "combo_filtro_seccion") else None
        materia_id= self.combo_filtro_materia.currentData() if hasattr(self, "combo_filtro_materia") else None
        termino= _normalizar(self.in_busqueda.text()) if hasattr(self, "in_busqueda") else ""
        especialidad_id= (self.combo_filtro_especialidad_hor.currentData()
                            if hasattr(self, "combo_filtro_especialidad_hor") and self._es_politecnico() else None)
        carrera_id= (self.combo_filtro_carrera_hor.currentData()
                      if hasattr(self, "combo_filtro_carrera_hor") and self._es_universidad() else None)
        secciones_carrera= self._secciones_de_la_carrera(carrera_id) if carrera_id is not None else None

        resultado= []
        conteo_dias= [0] * 6
        institucionales= 0
        locales= 0
        for c in self._todas_clases:
            if curso_id is not None and c.get("grado_id") != curso_id:
                continue
            if seccion_id is not None and c.get("seccion_id") != seccion_id:
                continue
            if materia_id is not None and c.get("materia_id") != materia_id:
                continue
            if especialidad_id is not None and c.get("especialidad_id") != especialidad_id:
                continue
            if secciones_carrera is not None and c.get("seccion_id") not in secciones_carrera:
                continue
            if termino:
                texto_busqueda= _normalizar(" ".join(str(c.get(k) or "") for k in
                    ("materia_nombre", "seccion_nombre", "aula_nombre", "notas")))
                if termino not in texto_busqueda:
                    continue
            resultado.append(c)
            if c.get("es_local"):
                locales += 1
            else:
                institucionales += 1
            try:

                conteo_dias[DIAS.index(c["dia"])] += 1
            except ValueError:
                pass

        self.carga_semanal.establecer_datos(conteo_dias)
        if self.restringido and hasattr(self, "anillo_proporcion"):
            self.anillo_proporcion.establecer(institucionales, locales)

        if not self._cargado_una_vez:
            return  #aún no llegan datos reales; el estado de "cargando" sigue visible

        hay_resultados= bool(resultado)
        self.canvas.setVisible(hay_resultados)
        self.lbl_vacio.setVisible(not hay_resultados)
        if hay_resultados:
            self.canvas.establecer_clases(resultado, animar=animar)

    def _curso_filtro_cambio(self):

        self._filtrar_secciones_por_curso()
        self._aplicar_filtros(animar=False)

    def _secciones_permitidas_con_nivel(self):

        base= obtener_secciones_permitidas(self.main_window)
        nivel= self.combo_filtro_nivel.currentData() if hasattr(self, "combo_filtro_nivel") else None
        return interseccion_opcional(base, secciones_del_nivel_educativo(nivel))

    def _nivel_filtro_cambio(self):

        secciones_permitidas= self._secciones_permitidas_con_nivel()
        poblar_combo_curso(self.combo_filtro_curso, incluir_todos=False, secciones_permitidas=secciones_permitidas)
        self._filtrar_secciones_por_curso()
        self._aplicar_filtros(animar=False)

    #Recarga el combo de sección para que solo muestre las secciones
    #del curso elegido (o todas, si no hay curso seleccionado).
    def _filtrar_secciones_por_curso(self):

        cascada_seccion_por_curso(self.combo_filtro_curso, self.combo_filtro_seccion,
                                   incluir_todas= False,
                                   secciones_permitidas= self._secciones_permitidas_con_nivel())

    #--------------------------------------------------------
    def _cargar_combos_filtro(self):

        self.combo_filtro_materia.blockSignals(True)
        sel_materia= self.combo_filtro_materia.currentData()
        self.combo_filtro_materia.clear()
        self.combo_filtro_materia.addItem("Todas las materias", None)

        conn= obtener_conexion()
        c= conn.cursor()
        if self.restringido:
            materias_permitidas= obtener_materias_permitidas(self.main_window) or set()
            if materias_permitidas:
                marcadores= ",".join("?" * len(materias_permitidas))
                c.execute(f"SELECT id, nombre FROM materias WHERE id IN ({marcadores}) ORDER BY nombre",
                          tuple(materias_permitidas))
                for fila in c.fetchall():
                    self.combo_filtro_materia.addItem(fila["nombre"], fila["id"])
        else:
            c.execute("SELECT id, nombre FROM materias ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_materia.addItem(fila["nombre"], fila["id"])
        conn.close()

        secciones_permitidas= self._secciones_permitidas_con_nivel()
        poblar_combo_curso(self.combo_filtro_curso, incluir_todos=False, secciones_permitidas=secciones_permitidas)
        self._filtrar_secciones_por_curso()

        idx= self.combo_filtro_materia.findData(sel_materia)
        self.combo_filtro_materia.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filtro_materia.blockSignals(False)

    def _poblar_filtro_tecnico_local(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_local.setVisible(es_poli)
        self.combo_filtro_especialidad_local.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_local.currentData()
            self.combo_filtro_especialidad_local.blockSignals(True)
            self.combo_filtro_especialidad_local.clear()
            self.combo_filtro_especialidad_local.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_local.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_local.findData(actual)
            self.combo_filtro_especialidad_local.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_local.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_local.setVisible(es_uni)
        self.combo_filtro_carrera_local.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_local.currentData()
            self.combo_filtro_carrera_local.blockSignals(True)
            self.combo_filtro_carrera_local.clear()
            self.combo_filtro_carrera_local.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_local.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_carrera_local.findData(actual)
            self.combo_filtro_carrera_local.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_local.blockSignals(False)

    def _cargar_combos_edicion_local(self):

        materias_permitidas= obtener_materias_permitidas(self.main_window)
        secciones_permitidas= obtener_secciones_permitidas(self.main_window)
        if hasattr(self, "combo_filtro_especialidad_local"):
            self._poblar_filtro_tecnico_local()
            especialidad_id= (self.combo_filtro_especialidad_local.currentData()
                                if self._es_politecnico() else None)
            carrera_id= (self.combo_filtro_carrera_local.currentData()
                          if self._es_universidad() else None)
            if especialidad_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT id FROM secciones WHERE especialidad_id=?", (especialidad_id,))
                secciones_permitidas= interseccion_opcional(secciones_permitidas,
                                                               {fila["id"] for fila in c.fetchall()})
                conn.close()
            if carrera_id is not None:
                secciones_permitidas= interseccion_opcional(
                    secciones_permitidas, self._secciones_de_la_carrera(carrera_id))
        seleccion_materia= self.combo_materia_local.currentData()
        self.combo_materia_local.blockSignals(True)
        self.combo_materia_local.clear()
        self.combo_materia_local.addItem("— Ninguna —", None)
        conn= obtener_conexion()
        c= conn.cursor()
        if materias_permitidas is not None:
            if materias_permitidas:
                marcadores= ",".join("?" * len(materias_permitidas))
                c.execute(f"SELECT id, nombre FROM materias WHERE id IN ({marcadores}) ORDER BY nombre",
                          tuple(materias_permitidas))
                for fila in c.fetchall():
                    self.combo_materia_local.addItem(fila["nombre"], fila["id"])
        else:
            c.execute("SELECT id, nombre FROM materias ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_materia_local.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx_m= self.combo_materia_local.findData(seleccion_materia)
        self.combo_materia_local.setCurrentIndex(idx_m if idx_m >= 0 else 0)
        self.combo_materia_local.blockSignals(False)

        poblar_combo_curso(self.combo_curso_local, incluir_todos=False, secciones_permitidas=secciones_permitidas)
        self._filtrar_secciones_local_por_curso()

    def _curso_local_cambio(self):

        self._filtrar_secciones_local_por_curso()

    #Recarga 'Sección' con solo las secciones del curso elegido — igual que
    #TODOS los combos Curso->Sección de AcaDeXI: Curso obligatorio primero,
    #sin excepciones.
    def _filtrar_secciones_local_por_curso(self):

        cascada_seccion_por_curso(self.combo_curso_local, self.combo_seccion_local, incluir_todas=False,
                                   secciones_permitidas= obtener_secciones_permitidas(self.main_window))

    def _limpiar_form_local(self):

        self.id_edicion_local= None
        if self.combo_curso_local.count():
            self.combo_curso_local.setCurrentIndex(0)
        if self.combo_materia_local.count():
            self.combo_materia_local.setCurrentIndex(0)
        if self.combo_seccion_local.count():
            self.combo_seccion_local.setCurrentIndex(0)
        self.combo_dia_local.setCurrentIndex(0)
        self.time_inicio_local.setTime(QTime(8, 0))
        self.time_fin_local.setTime(QTime(9, 0))
        self.in_aula_local.clear()
        self.in_notas_local.clear()
        desactivar_modo_edicion(self.in_aula_local)

    def _guardar_local(self):

        materia_id= self.combo_materia_local.currentData()
        seccion_id= self.combo_seccion_local.currentData()
        dia= self.combo_dia_local.currentText()
        hora_inicio= self.time_inicio_local.time().toString("HH:mm")
        hora_fin= self.time_fin_local.time().toString("HH:mm")
        if materia_id is None and not self.in_notas_local.text().strip():
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Selecciona al menos una materia o escribe una nota que identifique esta clase.", self)
            return
        if hora_fin <= hora_inicio:
            mostrar_mensaje("advertencia", "Horario inválido", "La hora de fin debe ser posterior a la de inicio.", self)
            return
        guardar_entrada_horario_local(self.main_window, self.id_edicion_local, materia_id, seccion_id,
                                      dia, hora_inicio, hora_fin, self.in_aula_local.text().strip(),
                                      self.in_notas_local.text().strip())
        registrar_auditoria("Horario", "Guardó clase local (Modo Docente)",
                            self.main_window.usuario_actual, f"{dia} {hora_inicio}-{hora_fin}")
        mostrar_mensaje("exito", "Guardado",
                       "Tu clase local se guardó solo en este equipo (Modo Docente).", self)
        self._limpiar_form_local()
        self.refrescar()

    def _cargar_local_seleccionada(self):

        fila= self.tabla_local.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una clase local de la tabla.", self)
            return
        id_local= int(self.tabla_local.item(fila, 0).text())
        entrada= obtener_entrada_horario_local(self.main_window, id_local)
        if not entrada:
            return
        self.id_edicion_local= id_local
        self._cargar_combos_edicion_local()
        idx_m= self.combo_materia_local.findData(entrada["materia_id"])
        self.combo_materia_local.setCurrentIndex(idx_m if idx_m >= 0 else 0)
        preseleccionar_curso_y_seccion(self.combo_curso_local, self.combo_seccion_local,
                                        entrada["seccion_id"], incluir_todas=False)
        idx_d= self.combo_dia_local.findText(entrada["dia"] or "")
        self.combo_dia_local.setCurrentIndex(idx_d if idx_d >= 0 else 0)
        if entrada["hora_inicio"]:
            self.time_inicio_local.setTime(QTime.fromString(entrada["hora_inicio"], "HH:mm"))
        if entrada["hora_fin"]:
            self.time_fin_local.setTime(QTime.fromString(entrada["hora_fin"], "HH:mm"))
        self.in_aula_local.setText(entrada["aula_texto"] or "")
        self.in_notas_local.setText(entrada["notas"] or "")
        self.panel_local.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.in_aula_local, "Editando clase local")

    def _eliminar_local(self):

        fila= self.tabla_local.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una clase local de la tabla.", self)
            return
        id_local= int(self.tabla_local.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta clase local?", self) != QMessageBox.StandardButton.Yes:
            return
        eliminar_entrada_horario_local(self.main_window, id_local)
        registrar_auditoria("Horario", "Eliminó clase local (Modo Docente)", self.main_window.usuario_actual, "")
        self._limpiar_form_local()
        self.refrescar()

    def _poblar_tabla_local(self):

        self.tabla_local.setUpdatesEnabled(False)
        self.tabla_local.setSortingEnabled(False)
        self.paginacion_local.establecer_total(len(self._entradas_locales))
        inicio, fin= self.paginacion_local.rango_actual()
        pagina= self._entradas_locales[inicio:fin]
        self.tabla_local.setRowCount(len(pagina))
        for i, e in enumerate(pagina):
            self.tabla_local.setItem(i, 0, QTableWidgetItem(str(e["id"])))
            self.tabla_local.setItem(i, 1, QTableWidgetItem(e["dia"] or ""))
            self.tabla_local.setItem(i, 2, QTableWidgetItem(
                f"{formatear_hora(e['hora_inicio'], self.main_window)} - "
                f"{formatear_hora(e['hora_fin'], self.main_window)}"))
            self.tabla_local.setItem(i, 3, QTableWidgetItem(e["materia_nombre"]))
            self.tabla_local.setItem(i, 4, QTableWidgetItem(e.get("grado_nombre", "")))
            self.tabla_local.setItem(i, 5, QTableWidgetItem(e.get("seccion_nombre_sola", "")))
            self.tabla_local.setItem(i, 6, QTableWidgetItem(e["aula_nombre"] or ""))
        ajustar_anchos_columnas(self.tabla_local)
        self.tabla_local.setUpdatesEnabled(True)
        self._anim_tabla_local.stop()
        self._efecto_tabla_local.setOpacity(0.3)
        self._anim_tabla_local.setStartValue(0.3)
        self._anim_tabla_local.setEndValue(1.0)
        self._anim_tabla_local.start()

    #Carga de datos (una sola pasada por refresco, sin consultas N+1)
    def _cargar_datos(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT horarios.dia, horarios.hora_inicio, horarios.hora_fin,
                     materias.nombre as materia_nombre, horarios.materia_id,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre, horarios.seccion_id,
                     secciones.grado_id as grado_id, secciones.especialidad_id as especialidad_id,
                     especialidades.nombre as especialidad_nombre,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre_sola,
                     aulas.nombre as aula_nombre
                     FROM horarios
                     LEFT JOIN materias ON horarios.materia_id = materias.id
                     LEFT JOIN secciones ON horarios.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN aulas ON horarios.aula_id = aulas.id
                     LEFT JOIN especialidades ON secciones.especialidad_id = especialidades.id
                     ORDER BY horarios.hora_inicio""")
        institucionales= [dict(fila, es_local=False, notas="") for fila in c.fetchall()]

        if self.restringido:
            materias_permitidas= obtener_materias_permitidas(self.main_window) or set()
            institucionales= [institucionale for institucionale in institucionales if institucionale["materia_id"] in materias_permitidas]

        #Carrera(s) por sección (solo si aplica Universidad): la carrera es un
        #dato del estudiante, no de la sección, así que se resuelve aparte agrupando las carreras de los estudiantes
        #activos de cada sección.
        if self._es_universidad():
            seccion_ids_uni= {institucionale["seccion_id"] for institucionale in institucionales if institucionale.get("seccion_id")}
            carreras_por_seccion= {}
            if seccion_ids_uni:
                marcadores= ",".join("?" * len(seccion_ids_uni))
                c.execute(f"""SELECT DISTINCT estudiantes.seccion_id, carreras.nombre as carrera_nombre
                              FROM estudiantes
                              JOIN carreras ON estudiantes.carrera_id = carreras.id
                              WHERE estudiantes.estado='Activo' AND estudiantes.seccion_id IN ({marcadores})
                              ORDER BY carreras.nombre""", tuple(seccion_ids_uni))
                for fila in c.fetchall():
                    carreras_por_seccion.setdefault(fila["seccion_id"], []).append(fila["carrera_nombre"])
            for institucionale in institucionales:
                nombres= carreras_por_seccion.get(institucionale.get("seccion_id")) or []
                institucionale["carreras_nombres"]= ", ".join(nombres)

        self._entradas_locales= []
        if self.restringido:
            entradas= listar_horario_local(self.main_window)
            if entradas:
                materia_ids= {entrada["materia_id"] for entrada in entradas if entrada["materia_id"]}
                seccion_ids= {entrada["seccion_id"] for entrada in entradas if entrada["seccion_id"]}
                nombres_materia= {}
                if materia_ids:
                    marcadores= ",".join("?" * len(materia_ids))
                    c.execute(f"SELECT id, nombre FROM materias WHERE id IN ({marcadores})", tuple(materia_ids))
                    nombres_materia= {fila["id"]: fila["nombre"] for fila in c.fetchall()}
                etiquetas_seccion= {}
                grados_nombre_seccion= {}
                secciones_nombre_sola= {}
                grados_seccion= {}
                especialidad_nombre_seccion= {}
                if seccion_ids:
                    marcadores= ",".join("?" * len(seccion_ids))
                    c.execute(f"""SELECT secciones.id, secciones.nombre as seccion_nombre,
                                  grados.nombre as grado_nombre, secciones.grado_id as grado_id,
                                  especialidades.nombre as especialidad_nombre
                                  FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id
                                  LEFT JOIN especialidades ON secciones.especialidad_id = especialidades.id
                                  WHERE secciones.id IN ({marcadores})""", tuple(seccion_ids))
                    for fila in c.fetchall():
                        etiquetas_seccion[fila["id"]]= f"{fila['grado_nombre'] or ''} - {fila['seccion_nombre'] or ''}"
                        secciones_nombre_sola[fila["id"]]= fila["seccion_nombre"]
                        grados_nombre_seccion[fila["id"]]= fila["grado_nombre"]
                        grados_seccion[fila["id"]]= fila["grado_id"]
                        especialidad_nombre_seccion[fila["id"]]= fila["especialidad_nombre"]
                carreras_por_seccion_local= {}
                if seccion_ids and self._es_universidad():
                    marcadores= ",".join("?" * len(seccion_ids))
                    c.execute(f"""SELECT DISTINCT estudiantes.seccion_id, carreras.nombre as carrera_nombre
                                  FROM estudiantes
                                  JOIN carreras ON estudiantes.carrera_id = carreras.id
                                  WHERE estudiantes.estado='Activo' AND estudiantes.seccion_id IN ({marcadores})
                                  ORDER BY carreras.nombre""", tuple(seccion_ids))
                    for fila in c.fetchall():
                        carreras_por_seccion_local.setdefault(fila["seccion_id"], []).append(fila["carrera_nombre"])
                for entrada in entradas:
                    self._entradas_locales.append({
                        "id": entrada["id"], "dia": entrada["dia"], "hora_inicio": entrada["hora_inicio"], "hora_fin": entrada["hora_fin"],
                        "materia_id": entrada["materia_id"], "seccion_id": entrada["seccion_id"],
                        "grado_id": grados_seccion.get(entrada["seccion_id"]),
                        "materia_nombre": nombres_materia.get(entrada["materia_id"], "") or entrada["notas"] or "(sin materia)",
                        #"seccion_nombre" combinada (Curso - Sección): usada por el canvas/chips del calendario, igual que las clases
                        #institucionales, para que se vean igual.
                        "seccion_nombre": etiquetas_seccion.get(entrada["seccion_id"], "") or "",
                        #Campos separados: usados por la tabla "Clase Local" (Curso | Sección aparte).
                        "grado_nombre": grados_nombre_seccion.get(entrada["seccion_id"], "") or "",
                        "seccion_nombre_sola": secciones_nombre_sola.get(entrada["seccion_id"], "") or "",
                        "especialidad_nombre": especialidad_nombre_seccion.get(entrada["seccion_id"]) or "",
                        "carreras_nombres": ", ".join(carreras_por_seccion_local.get(entrada["seccion_id"], [])),
                        "aula_nombre": entrada["aula_texto"], "notas": entrada["notas"], "es_local": True,
                    })
        conn.close()
        self._todas_clases= institucionales + self._entradas_locales
        self._colores_materias= obtener_colores_materias_local(self.main_window)
        self.canvas.establecer_colores_materias(self._colores_materias)

    #--------------------------------------------------------
    def _refrescar_colores_tema(self):

        colores= _colores_tema(self.main_window)
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        self.carga_semanal.establecer_colores(colores)
        self.canvas.establecer_colores(colores)
        if hasattr(self, "icono_busqueda"):
            self.icono_busqueda.establecer_color(colores["texto_sec"])
        if self.restringido and hasattr(self, "anillo_proporcion"):
            self.anillo_proporcion.establecer_colores(colores)
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {colores['panel']};
                color: {colores['texto']};
                border: 1px solid {colores['borde']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        if hasattr(self, "frame_cabecera"):
            self.frame_cabecera.setStyleSheet(f"""
                QFrame#TarjetaCabecera {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {colores['acento']}, stop:1 {colores['acento_hv']});
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
                #ChipContador {{
                    background-color: rgba(255, 255, 255, 40);
                    color: white;
                    border-radius: 14px;
                    padding: 7px 16px;
                    font-weight: 700;
                    font-size: 12px;
                }}
            """)
        if hasattr(self, "dialogo_filtros"):
            self.dialogo_filtros.setStyleSheet(f"""
                QDialog#DialogoFiltros {{
                    background-color: {colores['panel']};
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
                    background-color: {colores['panel']};
                    color: {colores['texto']};
                    border: 1px solid {colores['borde']};
                    padding: 6px 10px;
                    border-radius: 6px;
                }}
                QLabel#IconoEncabezadoFiltros {{
                    background-color: {colores['acento']};
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
                    color: {colores['texto']};
                    background: transparent;
                }}
                QLabel#SubtituloFiltros {{
                    font-size: 11.5px;
                    color: {colores['texto_sec']};
                    background: transparent;
                }}
                QFrame#SeparadorFiltros {{
                    background-color: {colores['borde']};
                    max-height: 1px;
                    border: none;
                }}
                QLabel {{
                    color: {colores['texto']};
                    font-weight: 700;
                    font-size: 12.5px;
                    background: transparent;
                }}
            """)

    def refrescar(self):

        if hasattr(self, "combo_filtro_nivel"):
            poblar_combo_nivel_educativo(self.combo_filtro_nivel)
        self._cargar_combos_filtro()
        self._cargar_especialidad_carrera_filtro_horario()
        self._cargar_datos()
        if self.restringido:
            self._cargar_combos_edicion_local()
            self._poblar_tabla_local()
        self._cargado_una_vez= True
        self.lbl_cargando.setVisible(False)
        self._aplicar_filtros(animar=True)

    def actualizar_tema(self):

        self._refrescar_colores_tema()