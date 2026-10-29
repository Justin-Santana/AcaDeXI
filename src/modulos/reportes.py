#Reportes.py - Reportes y Analítica Rediseño visual: cabecera tipo "hero", tarjetas KPI e indicadores
#circulares dibujados a mano con QPainter, mini-gráfico de barras propio, transiciones animadas entre pestañas,
#y barra de filtros (búsqueda + curso + sección) con paginación de 25 resultados en cada tabla. También
#incorpora una pestaña de "Vista previa y edición" (reportes_editor.py) para abrir, previsualizar y editar en
#el momento los CSV/Excel/PDF que este módulo exporta.
##Toda la lógica de datos/exportación original se conserva; lo que cambia es la presentación, el
#filtrado/paginación de las tablas y la aparición del visor de archivos.
#============================================================
import csv
import os
import unicodedata
from datetime import datetime
from src.nucleo.formato_hora import formatear_hora, formatear_fecha_hora

from PySide6.QtWidgets import (QToolTip, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QFileDialog, QGridLayout,
    QScrollArea, QFrame, QLineEdit, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy,
    QApplication, QDialog)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, Property)
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QLinearGradient, QFontMetrics, QPixmap, QIcon

from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo)
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.modulos.calificaciones import _datos_institucion, _dibujar_encabezado, _dibujar_pie_pagina
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, agregar_boton_pantalla_completa)
from src.modulos.reportes_editor import VisorEditorReportes
from src.interfaz.configuracion import (TabWidgetNavegable, anio_academico_actual, resolver_nota_minima,
    es_sistema_dominicano, conectar_tooltip_seleccion, estilo_flechas_navegacion_tabs)
from src.modulos.materias import MODELO_EVALUACION_TECNICA
from src.nucleo.permisos import obtener_profesor_id
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro,
                          EMOJI_PROFESOR, EMOJI_VISTA_EDICION, EMOJI_SECCIONES_GRUPOS,
                          html_icono_emoji)

TAM_PAGINA_REPORTES= 25


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica.
def _hex_a_rgba(color_hex, alpha):

    color_hex= (color_hex or "#2563EB").lstrip("#")
    #r, g, b: canales rojo, verde y azul (0 a 255) sacados del color hex para armar el rgba.
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Lee la paleta/tema activo de la ventana principal para que las tarjetas
#de este módulo respeten el tema y el modo claro/oscuro elegidos.
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
        return {"bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0", "txt_prim": "#0F172A",
                "txt_sec": "#64748B", "accent": "#2563EB", "accent_hv": "#1D4ED8"}


#Quita mayúsculas y acentos para que la búsqueda no sea estricta.
def _normalizar(texto):

    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


#Icono de la pestaña 'Estudiantes en Riesgo': un busto de persona (cabeza
#+ hombros) dibujado a mano en un solo tono gris neutro, sin ningún otro
#color -a diferencia del emoji EMOJI_ESTUDIANTE_RIESGO (colorido) que usan
#Dashboard y el resto de la app-, para que en la barra de pestañas se vea
#como un icono plano y sobrio en vez de un emoji llamativo.
def _icono_estudiante_gris(tamano=16, color="#94A3B8"):

    pix= QPixmap(tamano, tamano)
    pix.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(pix)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setBrush(QColor(color))
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setClipRect(0, 0, tamano, tamano)
    #Cabeza: círculo en el tercio superior.
    radio_cabeza= tamano * 0.19
    cx= tamano / 2
    cy_cabeza= tamano * 0.30
    pintor.drawEllipse(QPointF(cx, cy_cabeza), radio_cabeza, radio_cabeza)
    #Hombros/cuerpo: círculo grande cuya mitad superior queda recortada por el borde del pixmap, dejando ver solo
    #el "arco" de los hombros.
    radio_cuerpo= tamano * 0.34
    cy_cuerpo= tamano * 0.92
    pintor.drawEllipse(QPointF(cx, cy_cuerpo), radio_cuerpo, radio_cuerpo)
    pintor.end()
    return QIcon(pix)


#Fija el tamaño de página de un ControlPaginacion de forma defensiva
#(se prueba con varios nombres de atributo posibles) para que Reportes
#liste 25 resultados por página en cada tabla, tal como en el resto de
#módulos que ya personalizan este valor (ver calendario.py).
def _forzar_tam_pagina(control, valor=TAM_PAGINA_REPORTES):

    for atributo in ("tam_pagina", "por_pagina", "page_size", "_tam_pagina"):
        if hasattr(control, atributo):
            setattr(control, atributo, valor)
            break


#Icono de lupa dibujado a mano con QPainter para las barras de búsqueda.
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


#QPushButton normal que además "respira" con una sombra suave al pasar
#el mouse por encima. Solo anima mientras el cursor está sobre el botón.
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


#Indicador circular de porcentaje dibujado con QPainter, con animación
#de barrido del arco al cambiar de valor (sin temporizadores en reposo:
#solo repinta mientras la animación está corriendo).
class AnilloProgreso(QWidget):

    def __init__(self, color="#2563EB", grosor=9, parent=None):

        super().__init__(parent)
        self._valor= 0.0
        self._color= QColor(color)
        self._color_fondo= QColor(127, 127, 127, 55)
        self._color_texto= QColor("#0F172A")
        self._grosor= grosor
        self.setMinimumSize(84, 84)
        self._anim= None

    def _leer_valor(self):

        return self._valor

    #v: valor (0 a 100) que la animación le va dando a la propiedad 'valor'; se limita a ese rango.
    def _poner_valor(self, v):

        self._valor= max(0.0, min(100.0, v))
        self.update()

    valor= Property(float, _leer_valor, _poner_valor)

    def establecer_color(self, color_hex):

        self._color= QColor(color_hex)
        self.update()

    def establecer_color_texto(self, color_hex):

        self._color_texto= QColor(color_hex)
        self.update()

    def animar_a(self, nuevo_valor, duracion=700):

        nuevo_valor= max(0.0, min(100.0, nuevo_valor or 0.0))
        anim= QPropertyAnimation(self, b"valor", self)
        anim.setStartValue(self._valor)
        anim.setEndValue(nuevo_valor)
        anim.setDuration(duracion)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim= anim

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado= min(self.width(), self.height()) - self._grosor
        if lado <= 0:
            return
        rect= QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        pen_fondo= QPen(self._color_fondo, self._grosor)
        pen_fondo.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fondo)
        painter.drawArc(rect, 0, 360 * 16)
        pen_valor= QPen(self._color, self._grosor)
        pen_valor.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_valor)
        angulo_span= int(-self._valor / 100 * 360 * 16)
        painter.drawArc(rect, 90 * 16, angulo_span)
        painter.setPen(self._color_texto)
        fuente= painter.font()
        fuente.setBold(True)
        fuente.setPointSize(max(9, int(lado / 6)))
        painter.setFont(fuente)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._valor:.0f}%")


#Mini gráfico de barras dibujado a mano, sin dependencias externas,
#con una pequeña animación de "crecimiento" al cargar los datos.
class MiniBarras(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._categorias= []
        self._valores= []
        self._maximo= 1
        self._color= QColor("#6366F1")
        self._color_texto= QColor("#334155")
        self._progreso= 0.0
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._anim= None
        #Zonas (rect por columna, nombre completo) usadas para mostrar un
        #tooltip con el nombre íntegro de la materia al pasar el mouse:
        #las etiquetas debajo de cada barra se elide dinámicamente en paintEvent según el espacio disponible, así que
        #en varios casos el texto visible queda cortado ("Lengua Esp…") y solo el tooltip deja ver el nombre completo
        #-mismo comportamiento que ya tienen los mini-gráficos de materias.py y personal.py-.
        self._zonas_barras= []
        self.setMouseTracking(True)

    def _leer_progreso(self):

        return self._progreso

    #v: avance actual que la animación le da a la propiedad 'progreso'.
    def _poner_progreso(self, v):

        self._progreso= v
        self.update()

    progreso= Property(float, _leer_progreso, _poner_progreso)

    def establecer_color(self, color_hex):

        self._color= QColor(color_hex)
        self.update()

    def establecer_color_texto(self, color_hex):

        self._color_texto= QColor(color_hex)
        self.update()

    def establecer_datos(self, categorias, valores, maximo=None):

        self._categorias= list(categorias)
        self._valores= list(valores)
        self._maximo= maximo or (max(valores) if valores else 1) or 1
        self._progreso= 0.0
        anim= QPropertyAnimation(self, b"progreso", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(600)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim= anim
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._valores:
            self._zonas_barras= []
            painter.setPen(self._color_texto)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                            "Todavía no hay suficientes calificaciones para graficar.")
            return
        cantidad= len(self._valores)
        margen= 12
        ancho_disp= max(1, self.width() - margen * 2)
        alto_disp= max(1, self.height() - 46)
        espacio= ancho_disp / cantidad
        ancho_barra= max(10, espacio * 0.5)
        fuente_val= painter.font()
        fuente_val.setBold(True)
        fuente_val.setPointSize(9)
        fuente_cat= painter.font()
        fuente_cat.setPointSize(8)
        self._zonas_barras= []
        for i, (cat, val) in enumerate(zip(self._categorias, self._valores)):
            factor= (val / self._maximo) if self._maximo else 0
            h= alto_disp * max(0.0, min(1.0, factor)) * self._progreso
            pos_x= margen + i * espacio + (espacio - ancho_barra) / 2
            pos_y= alto_disp - h + 14
            ruta= QPainterPath()
            ruta.addRoundedRect(QRectF(pos_x, pos_y, ancho_barra, max(h, 0.0)), 6, 6)
            gradiente= QLinearGradient(0, pos_y, 0, pos_y + max(h, 1))
            gradiente.setColorAt(0, self._color.lighter(125))
            gradiente.setColorAt(1, self._color)
            painter.fillPath(ruta, gradiente)
            painter.setPen(self._color_texto)
            painter.setFont(fuente_val)
            painter.drawText(QRectF(pos_x - 12, pos_y - 16, ancho_barra + 24, 14),
                            Qt.AlignmentFlag.AlignCenter, f"{val:.1f}")
            painter.setFont(fuente_cat)
            #Antes se cortaba a un número fijo de caracteres (10-11) sin importar el espacio real disponible, así que con
            #pocas barras (mucho espacio libre) el nombre de la materia se veía "entrecortado" de forma innecesaria (p. ej.
            #"Lengua Esp…"). Ahora se elide dinámicamente según el ancho real de cada columna, usando todo el espacio
            #disponible.
            ancho_etiqueta= ancho_barra + 32
            fm= QFontMetrics(fuente_cat)
            rect_etiqueta= QRectF(pos_x - 16, alto_disp + 16, ancho_etiqueta, 20)
            texto_cat= fm.elidedText(cat, Qt.TextElideMode.ElideRight, int(ancho_etiqueta))
            painter.drawText(rect_etiqueta, Qt.AlignmentFlag.AlignCenter, texto_cat)
            #Zona sensible para el tooltip: solo el texto de la etiqueta (no la barra ni el resto de la columna), para que
            #el tooltip con el nombre completo aparezca únicamente al pasar el mouse sobre el texto, no sobre el gráfico.
            self._zonas_barras.append((rect_etiqueta, cat))

    def mouseMoveEvent(self, evento):

        pos= evento.position() if hasattr(evento, "position") else evento.pos()
        for rect, cat in self._zonas_barras:
            if rect.contains(pos):
                QToolTip.showText(evento.globalPosition().toPoint(), cat, self)
                break
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):

        QToolTip.hideText()
        super().leaveEvent(evento)


#Tarjeta con icono + valor grande animado (conteo), con una pequeña
#elevación de sombra al pasar el mouse por encima.
class TarjetaKPI(QFrame):

    def __init__(self, icono, titulo, color_acento="#2563EB", parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaKPI")
        self._color_acento= color_acento
        self._valor_actual= 0
        self._anim_valor= None

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setColor(QColor(0, 0, 0, 45))
        self._sombra.setOffset(0, 3)
        self._sombra.setBlurRadius(14)
        self.setGraphicsEffect(self._sombra)
        self._anim_sombra= QPropertyAnimation(self._sombra, b"blurRadius", self)
        self._anim_sombra.setDuration(180)
        self._anim_sombra.setEasingCurve(QEasingCurve.Type.OutCubic)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(16, 14, 16, 14)
        disposicion.setSpacing(4)

        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji(icono, 26))
        self.lbl_icono.setObjectName("IconoKPI")
        self.lbl_icono.setFixedSize(38, 38)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disposicion.addWidget(self.lbl_icono)

        self.lbl_valor= QLabel("--")
        self.lbl_valor.setObjectName("ValorKPI")
        disposicion.addWidget(self.lbl_valor)

        self.lbl_titulo= QLabel(titulo)
        self.lbl_titulo.setObjectName("TituloKPI")
        self.lbl_titulo.setWordWrap(True)
        disposicion.addWidget(self.lbl_titulo)

    def establecer_valor_animado(self, valor_final, sufijo=""):

        valor_inicial= self._valor_actual
        self._valor_actual= valor_final
        if valor_inicial == valor_final:
            self.lbl_valor.setText(f"{valor_final}{sufijo}")
            return
        anim= QVariantAnimation(self)
        anim.setStartValue(valor_inicial)
        anim.setEndValue(valor_final)
        anim.setDuration(500)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #v: valor intermedio de la animación; se muestra entero en la etiqueta junto con el sufijo.
        anim.valueChanged.connect(lambda v: self.lbl_valor.setText(f"{int(v)}{sufijo}"))
        anim.start()
        self._anim_valor= anim

    def enterEvent(self, evento):

        self._anim_sombra.stop()
        self._anim_sombra.setStartValue(self._sombra.blurRadius())
        self._anim_sombra.setEndValue(26)
        self._anim_sombra.start()
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._anim_sombra.stop()
        self._anim_sombra.setStartValue(self._sombra.blurRadius())
        self._anim_sombra.setEndValue(14)
        self._anim_sombra.start()
        super().leaveEvent(evento)


#Variante de tarjeta KPI para métricas porcentuales: icono + título a
#la izquierda, anillo de progreso animado a la derecha.
class TarjetaKPIAnillo(QFrame):

    def __init__(self, icono, titulo, color="#22C55E", parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaKPI")

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setColor(QColor(0, 0, 0, 45))
        self._sombra.setOffset(0, 3)
        self._sombra.setBlurRadius(14)
        self.setGraphicsEffect(self._sombra)
        self._anim_sombra= QPropertyAnimation(self._sombra, b"blurRadius", self)
        self._anim_sombra.setDuration(180)
        self._anim_sombra.setEasingCurve(QEasingCurve.Type.OutCubic)

        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(18, 14, 18, 14)
        disposicion.setSpacing(16)

        self.anillo= AnilloProgreso(color=color)
        disposicion.addWidget(self.anillo)

        bloque= QVBoxLayout()
        bloque.setSpacing(4)
        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji(icono, 24))
        self.lbl_icono.setObjectName("IconoKPI")
        self.lbl_icono.setFixedSize(34, 34)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bloque.addWidget(self.lbl_icono)
        self.lbl_titulo= QLabel(titulo)
        self.lbl_titulo.setObjectName("TituloKPI")
        self.lbl_titulo.setWordWrap(True)
        bloque.addWidget(self.lbl_titulo)
        bloque.addStretch()
        disposicion.addLayout(bloque, 1)

    def establecer_porcentaje(self, valor):

        self.anillo.animar_a(valor)

    def enterEvent(self, evento):

        self._anim_sombra.stop()
        self._anim_sombra.setStartValue(self._sombra.blurRadius())
        self._anim_sombra.setEndValue(26)
        self._anim_sombra.start()
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._anim_sombra.stop()
        self._anim_sombra.setStartValue(self._sombra.blurRadius())
        self._anim_sombra.setEndValue(14)
        self._anim_sombra.start()
        super().leaveEvent(evento)


#Módulo principal
class ModuloReportes(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._paneles= {}
        self._cache_materias_docente= None
        self._indices_pestanas= {}
        #Se define ANTES de _construir_ui(): al agregar la primera pestaña con
        #self.tabs.addTab(...), Qt puede disparar currentChanged de
        #inmediato (para la pestaña 0), y ese handler
        #(_construir_visor_editor_diferido) ya comprueba self.visor_editor -si el atributo todavía no existiera en ese
        #punto, reventaba con AttributeError apenas se abría el módulo.
        self.visor_editor= None
        self._rutas_recientes_reportes= []
        self._construir_ui()
        self.refrescar()
        self.actualizar_tema()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Reportes"
        registrar_atajo(self, self.main_window, "F5", "Actualizar todos los reportes", self.refrescar)
        registrar_atajo(self, self.main_window, "Ctrl+Shift+X", "Exportar reporte institucional (CSV)",
                         self._exportar_institucional_csv)

    #Navegación desde otros módulos (p. ej. la tarjeta KPI "Estudiantes en Riesgo" del Dashboard, tanto el
    #institucional como el de Docentes)
    def showEvent(self, evento):

        super().showEvent(evento)
        pendiente= getattr(self.main_window, "_pestana_pendiente_dashboard", None)
        if pendiente:
            self.main_window._pestana_pendiente_dashboard= None
            indice= self._indices_pestanas.get(pendiente)
            if indice is not None:
                self.tabs.setCurrentIndex(indice)

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
        disposicion.setSpacing(18)

        #--- Cabecera tipo "hero" ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Reportes")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Reportes y Analítica")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Indicadores institucionales, rendimiento académico y exportación de reportes")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo, 1)

        self.chip_actualizado= QLabel("--")
        self.chip_actualizado.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_actualizado, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_actualizar_todo= BotonAnimado("Actualizar todo")
        self.btn_actualizar_todo.clicked.connect(self.refrescar)
        cabecera_layout.addWidget(self.btn_actualizar_todo)

        disposicion.addWidget(self.frame_cabecera)

        #--- Pestañas con transición animada ---
        #TabWidgetNavegable (la misma que usan Configuración y el consolidado
        #de Asistencia) para poder moverse entre pestañas con las flechas izquierda/derecha del teclado, sin importar
        #dónde haya quedado el foco.
        self.tabs= TabWidgetNavegable()
        self.tabs.currentChanged.connect(self._animar_cambio_tab)
        self.tabs.currentChanged.connect(self._construir_visor_editor_diferido)
        disposicion.addWidget(self.tabs)
        if self._es_docente():
            #Un docente NO debería ver analítica de todo el colegio (Institucional, Cuadro de Honor, Rendimiento Técnico,
            #PDF con gráficos institucionales): solo lo que le compete a él mismo, y ya filtrado a sus propias materias.
            self._indices_pestanas["riesgo"]= self.tabs.count()
            self.tabs.addTab(self._tab_riesgo(), "Estudiantes en Riesgo")
            self.tabs.addTab(self._tab_excelencia(), "Mis Mejores Estudiantes")
            self.tabs.addTab(self._tab_asistencia(), "Consolidado de Asistencia")
            self.tabs.addTab(self._tab_exportacion_masiva(), "Exportación Masiva (Excel)")
            self.tabs.addTab(self._tab_vista_previa(), "Vista Previa y Edición")
        else:
            self.tabs.addTab(self._tab_institucional(), "Institucional")
            self._indices_pestanas["riesgo"]= self.tabs.count()
            self.tabs.addTab(self._tab_riesgo(), "Estudiantes en Riesgo")
            self.tabs.addTab(self._tab_excelencia(), "Cuadro de Honor")
            self.tabs.addTab(self._tab_asistencia(), "Consolidado de Asistencia")
            if self._es_politecnico():
                self.tabs.addTab(self._tab_rendimiento_tecnico(), "Rendimiento Técnico")
            self.tabs.addTab(self._tab_pdf_graficos(), "Reportes PDF con Gráficos")
            self.tabs.addTab(self._tab_exportacion_masiva(), "Exportación Masiva (Excel)")
            self.tabs.addTab(self._tab_vista_previa(), "Vista Previa y Edición")

        #Iconos explícitos de pestaña (con prioridad sobre el iconizador automático de iconos_auto.py): "Estudiantes en
        #Riesgo" reutiliza el mismo icono de estudiante+alerta del Dashboard, y "Vista Previa y Edición" tiene un icono
        #propio -un archivo que se ve y se edita a la vez- en vez de quedar sin ninguno o con uno genérico.
        self.tabs.setTabIcon(self._indices_pestanas["riesgo"], _icono_estudiante_gris())
        self.tabs.setTabIcon(self.tabs.count() - 1, icono_emoji(EMOJI_VISTA_EDICION))

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    def _es_personalizado(self):

        try:

            tipo, _personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado"

    def _ambos_modulos_tecnicos_activos(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado" and "Politécnico" in personalizados and "Universidad" in personalizados

    def _es_docente(self):

        #OJO: el rol se guarda/compara en toda la app como "Profesor" (ver configuracion.py: `rol in ("Profesor",
        #"Administrativo")`), no como "Docente". Con el valor equivocado esta función nunca daba True y el profesor
        #terminaba viendo TODAS las pestañas institucionales.
        return getattr(self.main_window, "rol_actual", None) == "Profesor"

    #IDs de las materias que imparte el docente logueado -como titular o
    #como co-docente (materia_profesores)-. Se cachea en la instancia
    #porque este módulo la consulta varias veces (riesgo, asistencia,
    #exportaciones) y las materias de alguien no cambian mientras tiene la
    #sesión abierta.
    def _materias_docente(self):

        if not self._es_docente():
            return None  #None = "sin restricción" (no es docente)
        if self._cache_materias_docente is not None:
            return self._cache_materias_docente
        profesor_id= obtener_profesor_id(self.main_window)
        if profesor_id is None:
            self._cache_materias_docente= set()
            return self._cache_materias_docente
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT materias.id FROM materias
                     LEFT JOIN materia_profesores ON materia_profesores.materia_id = materias.id
                     WHERE materias.profesor_id=? OR materia_profesores.profesor_id=?""",
                  (profesor_id, profesor_id))
        self._cache_materias_docente= {fila["id"] for fila in c.fetchall()}
        conn.close()
        return self._cache_materias_docente

    #Devuelve (fragmento_sql, parametros) para añadir a un WHERE/AND y
    #restringir `columna_materia_id` a las materias del docente logueado.
    #Si no es docente (o no tiene materias), devuelve ("", []) -sin
    #restricción- para no tocar el comportamiento de Administrador/
    #Director/Coordinador.
    def _filtro_sql_materias_docente(self, columna_materia_id):

        materias= self._materias_docente()
        if materias is None:
            return "", []
        if not materias:
            return f" AND {columna_materia_id} IS NULL AND 0", []  #docente sin materias: no ve nada
        placeholders= ",".join("?" for _ in materias)
        return f" AND {columna_materia_id} IN ({placeholders})", list(materias)

    def _animar_cambio_tab(self, indice):

        widget= self.tabs.widget(indice)
        if widget is None:
            return
        efecto= QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        self._anim_tab= anim

    def _animar_chip(self, chip, valor, singular, plural=None):

        plural= plural or (singular + "s")
        texto= f"🔎 {valor} " + (singular if valor == 1 else plural)
        chip.setText(texto)

    def _animar_fundido_tabla(self, tabla):

        efecto= QGraphicsOpacityEffect(tabla)
        tabla.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        anim.finished.connect(lambda: tabla.setGraphicsEffect(None))
        anim.start()
        tabla._anim_fundido= anim  #referencia viva mientras corre la animación

    #Barra de filtros reutilizable (búsqueda + curso + sección / búsqueda + especialidad, según la tabla)
    #Crea la barra de filtros compartida por las pestañas de listado
    #(Riesgo, Excelencia, Asistencia, Rendimiento Técnico): una sola fila
    #SIEMPRE VISIBLE con buscador + "✖ Limpiar" + contador de resultados,
    #y un botón "☰ Filtros" que abre una ventanita (no modal) con Nivel
    #Educativo, Área Técnica/Carrera y Curso/Sección (o Especialidad, en
    #la variante con_especialidad) — mismo patrón que
    #calendario.py/banco_tareas.py/observaciones.py. Los widgets viven
    #exactamente igual que antes (mismos objetos, mismas señales); lo
    #único que cambia es dónde se dibujan.
    def _crear_barra_filtros(self, placeholder_busqueda, con_curso_seccion=True, con_especialidad=False,
                              titulo_filtros= "Filtros"):

        frame= QFrame()
        frame.setObjectName("TarjetaFiltros")
        lay_frame= QVBoxLayout(frame)
        lay_frame.setContentsMargins(14, 10, 14, 10)
        lay_frame.setSpacing(8)

        combo_nivel= None
        if con_curso_seccion:
            combo_nivel= QComboBox()
            conectar_tooltip_seleccion(combo_nivel, "Filtrar por nivel educativo (se combina con Curso/Sección)")

        lbl_filtro_especialidad_rep= None
        combo_filtro_especialidad_rep= None
        lbl_filtro_carrera_rep= None
        combo_filtro_carrera_rep= None
        if con_curso_seccion:
            lbl_filtro_especialidad_rep= QLabel("Área Técnica:")
            combo_filtro_especialidad_rep= QComboBox()
            combo_filtro_especialidad_rep.setToolTip("Filtrar por área técnica del estudiante (Politécnico)")
            conectar_tooltip_seleccion(combo_filtro_especialidad_rep,
                "Filtrar por área técnica del estudiante (Politécnico)")

            lbl_filtro_carrera_rep= QLabel("Carrera:")
            combo_filtro_carrera_rep= QComboBox()
            combo_filtro_carrera_rep.setToolTip("Filtrar por carrera del estudiante (Universidad)")
            conectar_tooltip_seleccion(combo_filtro_carrera_rep, "Filtrar por carrera del estudiante (Universidad)")

            es_poli= self._es_politecnico()
            es_uni= self._es_universidad()
            lbl_filtro_especialidad_rep.setVisible(es_poli)
            combo_filtro_especialidad_rep.setVisible(es_poli)
            lbl_filtro_carrera_rep.setVisible(es_uni)
            combo_filtro_carrera_rep.setVisible(es_uni)

        combo_curso= None
        combo_seccion= None
        if con_curso_seccion:
            combo_curso= QComboBox()
            combo_curso.setToolTip("Filtrar por curso/grado")
            combo_seccion= QComboBox()
            combo_seccion.setToolTip("Filtrar por sección")

        combo_especialidad= None
        if con_especialidad:
            combo_especialidad= QComboBox()
            conectar_tooltip_seleccion(combo_especialidad, "Filtrar por especialidad")

        fila= QHBoxLayout()
        fila.setSpacing(10)
        lay_frame.addLayout(fila)

        marco_busqueda= QFrame()
        marco_busqueda.setObjectName("MarcoBusqueda")
        lay_busqueda= QHBoxLayout(marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        icono= IconoLupa()
        lay_busqueda.addWidget(icono)
        in_buscar= QLineEdit()
        limitar_campo_texto(in_buscar, 150)
        in_buscar.setPlaceholderText(placeholder_busqueda)
        in_buscar.setObjectName("InputBusquedaFiltro")
        lay_busqueda.addWidget(in_buscar, 1)
        fila.addWidget(marco_busqueda, 1)

        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnLimpiarFiltro")
        btn_limpiar.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.addWidget(btn_limpiar)

        lbl_chip_resultado= QLabel("0 resultados")
        lbl_chip_resultado.setObjectName("ChipResultadoFiltro")
        fila.addWidget(lbl_chip_resultado)

        dialogo_filtros= None
        btn_filtros= None
        if con_curso_seccion or con_especialidad:
            btn_filtros= QPushButton("Filtros")
            icono_boton_filtro(btn_filtros)
            btn_filtros.setIconSize(_QSize_emoji(16, 16))
            btn_filtros.setObjectName("BtnAccionNeutro")
            btn_filtros.setCursor(Qt.CursorShape.PointingHandCursor)
            fila.addWidget(btn_filtros)

            dialogo_filtros= QDialog(self)
            dialogo_filtros.setObjectName("DialogoFiltrosReportes")
            dialogo_filtros.setWindowTitle(titulo_filtros)
            aplicar_icono_ventana(dialogo_filtros, ICONO_FILTRO)
            dialogo_filtros.setModal(False)
            dialogo_filtros.setMinimumWidth(340)
            lay_dialogo= QVBoxLayout(dialogo_filtros)
            lay_dialogo.setContentsMargins(20, 18, 20, 18)
            lay_dialogo.setSpacing(12)

            fila_encabezado= QHBoxLayout()
            fila_encabezado.setSpacing(8)
            lbl_icono_encabezado= QLabel()
            pixmap_boton_filtro(lbl_icono_encabezado, 20)
            lbl_icono_encabezado.setObjectName("IconoEncabezadoFiltrosRep")
            fila_encabezado.addWidget(lbl_icono_encabezado)
            lbl_titulo_encabezado= QLabel("Filtros")
            lbl_titulo_encabezado.setObjectName("TituloEncabezadoFiltrosRep")
            fila_encabezado.addWidget(lbl_titulo_encabezado)
            fila_encabezado.addStretch()
            lay_dialogo.addLayout(fila_encabezado)

            lbl_subtitulo= QLabel("Todos son opcionales; se combinan con la búsqueda.")
            lbl_subtitulo.setObjectName("SubtituloFiltrosRep")
            lbl_subtitulo.setWordWrap(True)
            lay_dialogo.addWidget(lbl_subtitulo)

            separador= QFrame()
            separador.setFrameShape(QFrame.Shape.HLine)
            separador.setObjectName("SeparadorFiltrosRep")
            lay_dialogo.addWidget(separador)

            grid= QGridLayout()
            grid.setSpacing(10)
            grid.setColumnStretch(1, 1)
            fila_grid= 0
            if con_curso_seccion:
                grid.addWidget(QLabel("Nivel Educativo:"), fila_grid, 0)
                grid.addWidget(combo_nivel, fila_grid, 1)
                fila_grid += 1
                grid.addWidget(lbl_filtro_especialidad_rep, fila_grid, 0)
                grid.addWidget(combo_filtro_especialidad_rep, fila_grid, 1)
                fila_grid += 1
                grid.addWidget(lbl_filtro_carrera_rep, fila_grid, 0)
                grid.addWidget(combo_filtro_carrera_rep, fila_grid, 1)
                fila_grid += 1
                grid.addWidget(QLabel("Curso/Grado:"), fila_grid, 0)
                grid.addWidget(combo_curso, fila_grid, 1)
                fila_grid += 1
                grid.addWidget(QLabel("Sección:"), fila_grid, 0)
                grid.addWidget(combo_seccion, fila_grid, 1)
                fila_grid += 1
            if con_especialidad:
                grid.addWidget(QLabel("Especialidad:"), fila_grid, 0)
                grid.addWidget(combo_especialidad, fila_grid, 1)
                fila_grid += 1
            lay_dialogo.addLayout(grid)

            fila_botones= QHBoxLayout()
            fila_botones.addStretch()
            btn_cerrar= QPushButton("Cerrar")
            btn_cerrar.setIcon(icono_emoji("✖"))
            btn_cerrar.setIconSize(_QSize_emoji(16, 16))
            btn_cerrar.setObjectName("BtnAccionNeutro")
            btn_cerrar.clicked.connect(dialogo_filtros.hide)
            fila_botones.addWidget(btn_cerrar)
            lay_dialogo.addLayout(fila_botones)

            def _abrir_dialogo(_checked=False, d=dialogo_filtros):

                d.show()
                d.raise_()
                d.activateWindow()
            btn_filtros.clicked.connect(_abrir_dialogo)
            self._dialogos_filtros_reportes= getattr(self, "_dialogos_filtros_reportes", [])
            self._dialogos_filtros_reportes.append(dialogo_filtros)

        return {
            "frame": frame, "icono": icono, "buscar": in_buscar,
            "combo_nivel": combo_nivel, "combo_curso": combo_curso, "combo_seccion": combo_seccion,
            "combo_especialidad": combo_especialidad,
            "combo_filtro_especialidad_rep": combo_filtro_especialidad_rep,
            "combo_filtro_carrera_rep": combo_filtro_carrera_rep,
            "lbl_filtro_especialidad_rep": lbl_filtro_especialidad_rep,
            "lbl_filtro_carrera_rep": lbl_filtro_carrera_rep,
            "btn_limpiar": btn_limpiar, "chip": lbl_chip_resultado,
            "dialogo_filtros": dialogo_filtros, "btn_filtros": btn_filtros,
        }

    def _conectar_filtros(self, panel, recargar_fn):

        debounce= QTimer(self)
        debounce.setSingleShot(True)
        debounce.setInterval(180)

        def _al_disparar_debounce():

            panel["paginacion"].reiniciar()
            recargar_fn()

        debounce.timeout.connect(_al_disparar_debounce)
        panel["_debounce"]= debounce
        #_t: texto escrito en el buscador (no se usa); cada cambio solo reinicia el temporizador debounce.
        panel["buscar"].textChanged.connect(lambda _t: debounce.start())

        if panel.get("combo_nivel") is not None:
            def _en_cambio_nivel():

                self._cargar_combo_cursos(panel["combo_curso"], panel.get("combo_nivel"))
                if panel.get("combo_seccion") is not None:
                    self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"], panel.get("combo_nivel"))
                panel["paginacion"].reiniciar()
                recargar_fn()
            #_i: índice elegido en el combo (no se usa); solo avisa al manejador. Igual en los combos siguientes.
            panel["combo_nivel"].currentIndexChanged.connect(lambda _i: _en_cambio_nivel())

        if panel.get("combo_curso") is not None:
            def _en_cambio_curso():

                if panel.get("combo_seccion") is not None:
                    self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"], panel.get("combo_nivel"))
                panel["paginacion"].reiniciar()
                recargar_fn()
            #_i: índice o ítem que trae la señal y no se usa
            panel["combo_curso"].currentIndexChanged.connect(lambda _i: _en_cambio_curso())

        if panel.get("combo_seccion") is not None:
            def _en_cambio_seccion():

                panel["paginacion"].reiniciar()
                recargar_fn()
            #_i: índice o ítem que trae la señal y no se usa
            panel["combo_seccion"].currentIndexChanged.connect(lambda _i: _en_cambio_seccion())

        if panel.get("combo_especialidad") is not None:
            def _en_cambio_especialidad():

                panel["paginacion"].reiniciar()
                recargar_fn()
            #_i: índice o ítem que trae la señal y no se usa
            panel["combo_especialidad"].currentIndexChanged.connect(lambda _i: _en_cambio_especialidad())

        if panel.get("combo_filtro_especialidad_rep") is not None:
            def _en_cambio_filtro_tecnico_rep():

                panel["paginacion"].reiniciar()
                recargar_fn()
            #_i: índice elegido (no se usa); ambos combos técnicos llaman al mismo manejador de filtro.
            panel["combo_filtro_especialidad_rep"].currentIndexChanged.connect(
                lambda _i: _en_cambio_filtro_tecnico_rep())
            panel["combo_filtro_carrera_rep"].currentIndexChanged.connect(
                #_i: índice o ítem que trae la señal y no se usa
                lambda _i: _en_cambio_filtro_tecnico_rep())

        def _limpiar():

            panel["buscar"].blockSignals(True)
            panel["buscar"].clear()
            panel["buscar"].blockSignals(False)
            if panel.get("combo_nivel") is not None:
                panel["combo_nivel"].blockSignals(True)
                panel["combo_nivel"].setCurrentIndex(0)
                panel["combo_nivel"].blockSignals(False)
                self._cargar_combo_cursos(panel["combo_curso"], panel.get("combo_nivel"))
            if panel.get("combo_curso") is not None:
                panel["combo_curso"].blockSignals(True)
                panel["combo_curso"].setCurrentIndex(0)
                panel["combo_curso"].blockSignals(False)
                if panel.get("combo_seccion") is not None:
                    self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"], panel.get("combo_nivel"))
            if panel.get("combo_seccion") is not None:
                panel["combo_seccion"].blockSignals(True)
                panel["combo_seccion"].setCurrentIndex(0)
                panel["combo_seccion"].blockSignals(False)
            if panel.get("combo_especialidad") is not None:
                panel["combo_especialidad"].blockSignals(True)
                panel["combo_especialidad"].setCurrentIndex(0)
                panel["combo_especialidad"].blockSignals(False)
            if panel.get("combo_filtro_especialidad_rep") is not None:
                panel["combo_filtro_especialidad_rep"].blockSignals(True)
                panel["combo_filtro_especialidad_rep"].setCurrentIndex(0)
                panel["combo_filtro_especialidad_rep"].blockSignals(False)
                panel["combo_filtro_carrera_rep"].blockSignals(True)
                panel["combo_filtro_carrera_rep"].setCurrentIndex(0)
                panel["combo_filtro_carrera_rep"].blockSignals(False)
            panel["paginacion"].reiniciar()
            recargar_fn()

        panel["btn_limpiar"].clicked.connect(_limpiar)

    def _cargar_combo_cursos(self, combo, combo_nivel=None):

        if combo_nivel is not None:
            poblar_combo_nivel_educativo(combo_nivel)
        nivel= combo_nivel.currentData() if combo_nivel is not None else None
        poblar_combo_curso(combo, incluir_todos=False, secciones_permitidas=secciones_del_nivel_educativo(nivel))

    #Repuebla combo_seccion en cascada según combo_curso (o "Todas las
    #secciones" mezcladas si no se pasa combo_curso / está en "Todos").
    def _cargar_combo_secciones(self, combo_seccion, combo_curso=None, combo_nivel=None):

        if combo_curso is None:
            combo_curso= QComboBox()
            combo_curso.addItem("Todos los cursos", None)
        nivel= combo_nivel.currentData() if combo_nivel is not None else None
        cascada_seccion_por_curso(combo_curso, combo_seccion, secciones_permitidas=secciones_del_nivel_educativo(nivel))

    def _cargar_combo_especialidades(self, combo):

        combo.blockSignals(True)
        seleccion_previa= combo.currentData()
        combo.clear()
        combo.addItem("Todas las especialidades", None)
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            filas= c.fetchall()
        except Exception:
            filas= []
        conn.close()
        for fila in filas:
            combo.addItem(fila["nombre"], fila["id"])
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Puebla los combos de Área Técnica/Carrera del panel compartido de
    #filtros de reportes (ver _crear_barra_filtros). Igual que en el resto
    #de la app: solo se muestran si la institución tiene ese módulo
    #activo, y en modo Personalizado se agrega la opción "No Área
    #Técnica"/"No Carrera" (dato=0, distinto de None='Todas').
    def _cargar_combo_especialidad_carrera_rep(self, panel):

        combo_esp= panel.get("combo_filtro_especialidad_rep")
        combo_car= panel.get("combo_filtro_carrera_rep")
        if combo_esp is None:
            return
        es_poli= self._es_politecnico()
        es_uni= self._es_universidad()
        panel["lbl_filtro_especialidad_rep"].setVisible(es_poli)
        combo_esp.setVisible(es_poli)
        if es_poli:
            actual= combo_esp.currentData()
            combo_esp.blockSignals(True)
            combo_esp.clear()
            combo_esp.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                combo_esp.addItem(fila["nombre"], fila["id"])
            conn.close()
            if self._es_personalizado():
                combo_esp.addItem("No Área Técnica", 0)
            idx= combo_esp.findData(actual)
            combo_esp.setCurrentIndex(idx if idx >= 0 else 0)
            combo_esp.blockSignals(False)

        panel["lbl_filtro_carrera_rep"].setVisible(es_uni)
        combo_car.setVisible(es_uni)
        if es_uni:
            actual= combo_car.currentData()
            combo_car.blockSignals(True)
            combo_car.clear()
            combo_car.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                combo_car.addItem(fila["nombre"], fila["id"])
            conn.close()
            if self._es_personalizado():
                combo_car.addItem("No Carrera", 0)
            idx= combo_car.findData(actual)
            combo_car.setCurrentIndex(idx if idx >= 0 else 0)
            combo_car.blockSignals(False)

    #Filtra en Python una lista de sqlite3.Row de estudiantes según la
    #búsqueda de texto y los combos de curso/sección/área técnica/carrera
    #del panel dado.
    def _aplicar_filtros_estudiante(self, filas, panel):

        texto= _normalizar(panel["buscar"].text().strip())
        grado_id= panel["combo_curso"].currentData() if panel.get("combo_curso") else None
        seccion_id= panel["combo_seccion"].currentData() if panel.get("combo_seccion") else None
        especialidad_id= (panel["combo_filtro_especialidad_rep"].currentData()
                            if panel.get("combo_filtro_especialidad_rep") is not None
                            and self._es_politecnico() else None)
        carrera_id= (panel["combo_filtro_carrera_rep"].currentData()
                      if panel.get("combo_filtro_carrera_rep") is not None
                      and self._es_universidad() else None)
        resultado= []
        for fila in filas:
            claves= fila.keys()
            if grado_id is not None and "grado_id" in claves and fila["grado_id"] != grado_id:
                continue
            if seccion_id is not None and "seccion_id" in claves and fila["seccion_id"] != seccion_id:
                continue
            if especialidad_id is not None and "especialidad_id" in claves:
                if especialidad_id == 0 and fila["especialidad_id"] is not None:
                    continue
                if especialidad_id != 0 and fila["especialidad_id"] != especialidad_id:
                    continue
            if carrera_id is not None and "carrera_id" in claves:
                if carrera_id == 0 and fila["carrera_id"] is not None:
                    continue
                if carrera_id != 0 and fila["carrera_id"] != carrera_id:
                    continue
            if texto:
                partes= [fila["nombre"] if "nombre" in claves else "",
                          fila["apellidos"] if "apellidos" in claves else "",
                          fila["matricula"] if "matricula" in claves else ""]
                objetivo= _normalizar(" ".join(parte or "" for parte in partes))
                if texto not in objetivo:
                    continue
            resultado.append(fila)
        return resultado

    #---------------- INSTITUCIONAL ----------------
    def _tab_institucional(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(16)

        grid= QGridLayout()
        grid.setSpacing(14)
        self.kpi_estudiantes= TarjetaKPI("🎓", "Estudiantes inscritos", "#2563EB")
        #Mismo icono de "profesor" que usa la Tarjeta de Indicador de Profesores en el Dashboard (antes: 👥 genérico),
        #para que la misma idea se vea igual en toda la app.
        self.kpi_profesores= TarjetaKPI(EMOJI_PROFESOR, "Docentes activos", "#7C3AED")
        self.kpi_materias= TarjetaKPI("📘", "Materias impartidas", "#0EA5E9")
        self.kpi_secciones= TarjetaKPI(EMOJI_SECCIONES_GRUPOS, "Secciones / Grupos", "#F59E0B")
        grid.addWidget(self.kpi_estudiantes, 0, 0)
        grid.addWidget(self.kpi_profesores, 0, 1)
        grid.addWidget(self.kpi_materias, 0, 2)
        grid.addWidget(self.kpi_secciones, 0, 3)

        self.kpi_asistencia= TarjetaKPIAnillo("✅", "Asistencia promedio global", "#22C55E")
        self.kpi_reprobacion= TarjetaKPIAnillo("📉", "Tasa de reprobación", "#EF4444")
        grid.addWidget(self.kpi_asistencia, 1, 0, 1, 2)
        grid.addWidget(self.kpi_reprobacion, 1, 2, 1, 2)
        disposicion.addLayout(grid)

        panel_grafico= QFrame()
        panel_grafico.setObjectName("TarjetaFormulario")
        lay_graf= QVBoxLayout(panel_grafico)
        lay_graf.setContentsMargins(20, 16, 20, 16)
        lbl_graf_titulo= QLabel("Promedio general por materia (Top 6)")
        lbl_graf_titulo.setObjectName("TituloTarjetaInterna")
        lay_graf.addWidget(lbl_graf_titulo)
        self.mini_barras_materias= MiniBarras()
        lay_graf.addWidget(self.mini_barras_materias)
        disposicion.addWidget(panel_grafico)

        btn_exportar= BotonAnimado("Exportar Reporte Institucional (CSV)")
        btn_exportar.setObjectName("BtnAccionEditar")
        btn_exportar.clicked.connect(self._exportar_institucional_csv)
        disposicion.addWidget(btn_exportar)
        disposicion.addStretch()
        return contenedor

    def _cargar_institucional(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT COUNT(*) n FROM estudiantes WHERE estado='Activo'")
        total_estudiantes= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) n FROM profesores WHERE estado='Activo'")
        total_profesores= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) n FROM materias WHERE estado='Activa'")
        total_materias= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) n FROM secciones")
        total_secciones= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) n FROM asistencia")
        total_asistencia= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) n FROM asistencia WHERE estado='Presente'")
        presentes= c.fetchone()["n"]
        c.execute("""SELECT nota_minima, nota_minima_primaria, nota_minima_secundaria,
                     sistema_calificacion FROM configuracion WHERE id=1""")
        cfg= c.fetchone()
        #Reprobación institucional: la nota mínima ya no es un único número — en el Sistema Dominicano depende del
        #nivel educativo (Primaria/ Secundaria) del Grado de cada estudiante (ver resolver_nota_minima en
        #configuracion.py), así que el promedio de cada estudiante se compara contra SU nota mínima, no una global.
        c.execute("""SELECT calificaciones.estudiante_id as estudiante_id, AVG(calificaciones.valor) as prom,
                     grados.nivel_educativo as nivel
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE calificaciones.estado_publicacion != 'Borrador'
                     GROUP BY calificaciones.estudiante_id""")
        promedios= c.fetchall()
        c.execute("""SELECT materias.nombre as materia, AVG(calificaciones.valor) as promedio
                     FROM calificaciones LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     WHERE materias.nombre IS NOT NULL AND calificaciones.estado_publicacion != 'Borrador'
                     GROUP BY calificaciones.materia_id ORDER BY promedio DESC LIMIT 6""")
        top_materias= c.fetchall()
        conn.close()

        porcentaje_asistencia= round((presentes / total_asistencia) * 100, 1) if total_asistencia else 0.0
        if promedios:
            reprobados= sum(1 for promedio in promedios
                              if (promedio["prom"] or 0) < resolver_nota_minima(cfg, nivel_educativo=promedio["nivel"]))
            tasa_reprobacion= round((reprobados / len(promedios)) * 100, 1)
        else:
            tasa_reprobacion= 0.0

        self.kpi_estudiantes.establecer_valor_animado(total_estudiantes)
        self.kpi_profesores.establecer_valor_animado(total_profesores)
        self.kpi_materias.establecer_valor_animado(total_materias)
        self.kpi_secciones.establecer_valor_animado(total_secciones)
        self.kpi_asistencia.establecer_porcentaje(porcentaje_asistencia)
        self.kpi_reprobacion.establecer_porcentaje(tasa_reprobacion)

        #Se guardan como texto plano para la exportación CSV, independiente de la animación visual de las tarjetas.
        self._texto_total_estudiantes= str(total_estudiantes)
        self._texto_total_profesores= str(total_profesores)
        self._texto_total_materias= str(total_materias)
        self._texto_total_secciones= str(total_secciones)
        self._texto_asistencia= f"{porcentaje_asistencia}%"
        self._texto_reprobacion= f"{tasa_reprobacion}%"

        if top_materias:
            #Se pasa el nombre completo de la materia; MiniBarras.paintEvent se encarga de elidirlo dinámicamente según el
            #espacio real disponible para cada barra (ver comentario en esa clase).
            categorias= [top_materia["materia"] for top_materia in top_materias]
            valores= [round(top_materia["promedio"], 1) for top_materia in top_materias]
            self.mini_barras_materias.establecer_datos(categorias, valores, maximo=100)
        else:
            self.mini_barras_materias.establecer_datos([], [])

    def _exportar_institucional_csv(self):

        ruta, _= QFileDialog.getSaveFileName(self, "Exportar Reporte", "reporte_institucional.csv", "CSV (*.csv)")
        if not ruta:
            return
        #f: archivo CSV abierto para escritura; el writer vuelca ahí los indicadores.
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            writer= csv.writer(f)
            writer.writerow(["Indicador", "Valor"])
            writer.writerow(["Estudiantes inscritos", getattr(self, "_texto_total_estudiantes", "0")])
            writer.writerow(["Docentes activos", getattr(self, "_texto_total_profesores", "0")])
            writer.writerow(["Materias impartidas", getattr(self, "_texto_total_materias", "0")])
            writer.writerow(["Secciones/Grupos", getattr(self, "_texto_total_secciones", "0")])
            writer.writerow(["Asistencia promedio global", getattr(self, "_texto_asistencia", "0%")])
            writer.writerow(["Tasa de reprobación", getattr(self, "_texto_reprobacion", "0%")])
            writer.writerow(["Generado", formatear_fecha_hora(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.main_window)])
        registrar_auditoria("Reportes", "Exportó reporte institucional", self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Reporte guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    #---------------- RIESGO ----------------
    def _tab_riesgo(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        if self._es_docente():
            disposicion.addWidget(QLabel("Tus estudiantes con promedio por debajo de la nota mínima aprobatoria, "
                               "calculado solo con las materias que tú impartes:"))
        else:
            disposicion.addWidget(QLabel("Estudiantes con promedio por debajo de la nota mínima aprobatoria:"))

        panel= self._crear_barra_filtros("Buscar por nombre, apellido o matrícula…",
                                           titulo_filtros= "Filtros de Estudiantes en Riesgo")
        disposicion.addWidget(panel["frame"])

        fila_cabecera_tabla_riesgo= QHBoxLayout()
        fila_cabecera_tabla_riesgo.addStretch()
        disposicion.addLayout(fila_cabecera_tabla_riesgo)

        self.tabla_riesgo= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_riesgo)

        self.tabla_riesgo.setHorizontalHeaderLabels(["Estudiante", "Promedio General", "Curso", "Sección"])
        header= self.tabla_riesgo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_riesgo.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_riesgo.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_riesgo.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_riesgo.setAlternatingRowColors(True)
        self.tabla_riesgo.setWordWrap(True)
        self.tabla_riesgo.setMinimumHeight(380)
        self.tabla_riesgo.verticalHeader().setVisible(False)
        disposicion.addWidget(self.tabla_riesgo, 1)

        panel["paginacion"]= ControlPaginacion()
        _forzar_tam_pagina(panel["paginacion"])
        panel["paginacion"].cambio.connect(self._cargar_riesgo)
        panel["tabla"]= self.tabla_riesgo
        disposicion.addWidget(panel["paginacion"])
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_riesgo, [self.tabla_riesgo, panel["paginacion"]],
            titulo= "Estudiantes en Riesgo", parent=self)
        self._paneles["riesgo"]= panel
        self._conectar_filtros(panel, self._cargar_riesgo)
        self._cargar_combo_cursos(panel["combo_curso"], panel.get("combo_nivel"))
        self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"])
        self._cargar_combo_especialidad_carrera_rep(panel)

        fila_botones= QHBoxLayout()
        btn_actualizar= BotonAnimado("Actualizar")
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_riesgo)
        fila_botones.addWidget(btn_actualizar)

        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla_riesgo, self, titulo="Detalle del Estudiante en Riesgo")
        #*_: argumentos de la señal que se descartan; el doble clic en una fila pulsa el botón de detalle.
        self.tabla_riesgo.doubleClicked.connect(lambda *_: btn_detalle.click())

        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        return contenedor

    def _cargar_riesgo(self):

        panel= self._paneles["riesgo"]
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT nota_minima, nota_minima_primaria, nota_minima_secundaria,
                     sistema_calificacion FROM configuracion WHERE id=1""")
        cfg= c.fetchone()
        #Umbral de riesgo por nivel educativo (ver resolver_nota_minima en configuracion.py): si el sistema no es el
        #Dominicano, los tres valores resultan iguales (nota_minima general), igual que antes de este cambio.
        nota_min_primaria= resolver_nota_minima(cfg, nivel_educativo="Primaria")
        nota_min_secundaria= resolver_nota_minima(cfg, nivel_educativo="Secundaria")
        nota_min_general= resolver_nota_minima(cfg, nivel_educativo=None)
        #Si es un docente, el promedio "de riesgo" se calcula SOLO con las calificaciones de las materias que él
        #imparte -no con el promedio general del estudiante en todas sus materias, que no le compete.
        filtro_materia, params_materia= self._filtro_sql_materias_docente("calificaciones.materia_id")
        c.execute(f"""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos, estudiantes.matricula,
                     secciones.id as seccion_id, secciones.grado_id,
                     estudiantes.especialidad_id, estudiantes.carrera_id,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                     AVG(calificaciones.valor) as promedio
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE calificaciones.estado_publicacion != 'Borrador'{filtro_materia}
                     GROUP BY calificaciones.estudiante_id
                     HAVING promedio < (CASE grados.nivel_educativo
                                            WHEN 'Primaria' THEN ?
                                            WHEN 'Secundaria' THEN ?
                                            ELSE ? END)
                     ORDER BY promedio ASC""",
                  (*params_materia, nota_min_primaria, nota_min_secundaria, nota_min_general))
        filas= c.fetchall()
        conn.close()

        filas_filtradas= self._aplicar_filtros_estudiante(filas, panel)
        panel["paginacion"].establecer_total(len(filas_filtradas))
        inicio, fin= panel["paginacion"].rango_actual()
        pagina= filas_filtradas[inicio:fin]

        with tabla_pausada(self.tabla_riesgo):
            self.tabla_riesgo.setRowCount(len(pagina))
            #f: fila (registro de la consulta) del estudiante en riesgo que se pinta en la fila i de la tabla.
            for i, f in enumerate(pagina):
                self.tabla_riesgo.setItem(i, 0, QTableWidgetItem(f"{f['nombre']} {f['apellidos'] or ''}"))
                self.tabla_riesgo.setItem(i, 1, QTableWidgetItem(f"{f['promedio']:.2f}"))
                self.tabla_riesgo.setItem(i, 2, QTableWidgetItem(f["grado_nombre"] or "—"))
                self.tabla_riesgo.setItem(i, 3, QTableWidgetItem(f["seccion_nombre"] or "—"))
            ajustar_anchos_columnas(self.tabla_riesgo)
        self._animar_chip(panel["chip"], len(filas_filtradas), "estudiante en riesgo", "estudiantes en riesgo")
        self._animar_fundido_tabla(self.tabla_riesgo)

    #---------------- EXCELENCIA ----------------
    def _tab_excelencia(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        if self._es_docente():
            disposicion.addWidget(QLabel("Tus estudiantes con mejor promedio, calculado solo con las materias que "
                               "tú impartes:"))
        else:
            disposicion.addWidget(QLabel("Ranking de Excelencia Académica (mejores promedios):"))

        panel= self._crear_barra_filtros("Buscar por nombre, apellido o matrícula…",
                                           titulo_filtros= "Filtros del Cuadro de Honor")
        disposicion.addWidget(panel["frame"])

        fila_cabecera_tabla_excelencia= QHBoxLayout()
        fila_cabecera_tabla_excelencia.addStretch()
        disposicion.addLayout(fila_cabecera_tabla_excelencia)

        self.tabla_excelencia= QTableWidget(0, 5)
        aplicar_estructura_tabla(self.tabla_excelencia)

        self.tabla_excelencia.setHorizontalHeaderLabels(["Puesto", "Estudiante", "Promedio General", "Curso",
                                                           "Sección"])
        header= self.tabla_excelencia.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_excelencia.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_excelencia.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_excelencia.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_excelencia.setAlternatingRowColors(True)
        self.tabla_excelencia.setWordWrap(True)
        self.tabla_excelencia.setMinimumHeight(380)
        self.tabla_excelencia.verticalHeader().setVisible(False)
        disposicion.addWidget(self.tabla_excelencia, 1)

        panel["paginacion"]= ControlPaginacion()
        _forzar_tam_pagina(panel["paginacion"])
        panel["paginacion"].cambio.connect(self._cargar_excelencia)
        panel["tabla"]= self.tabla_excelencia
        disposicion.addWidget(panel["paginacion"])
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_excelencia, [self.tabla_excelencia, panel["paginacion"]],
            titulo= "Cuadro de Honor", parent=self)
        self._paneles["excelencia"]= panel
        self._conectar_filtros(panel, self._cargar_excelencia)
        self._cargar_combo_cursos(panel["combo_curso"], panel.get("combo_nivel"))
        self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"])
        self._cargar_combo_especialidad_carrera_rep(panel)

        fila_botones= QHBoxLayout()
        btn_actualizar= BotonAnimado("Actualizar")
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_excelencia)
        fila_botones.addWidget(btn_actualizar)

        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla_excelencia, self, titulo="Detalle del Estudiante Destacado")
        #*_: argumentos de la señal que se descartan; el doble clic en una fila pulsa el botón de detalle.
        self.tabla_excelencia.doubleClicked.connect(lambda *_: btn_detalle.click())

        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        return contenedor

    def _cargar_excelencia(self):

        panel= self._paneles["excelencia"]
        conn= obtener_conexion()
        c= conn.cursor()
        #Sin LIMIT fijo: con la paginación de 25 por página el "Cuadro de Honor" completo queda navegable en vez de
        #truncarse a los primeros 20 lugares como antes. Si es un docente, igual que en "Estudiantes en Riesgo", el
        #promedio se calcula SOLO con las calificaciones de las materias que él imparte -no con el promedio general del
        #estudiante en todas sus materias, que no le compete.
        filtro_materia, params_materia= self._filtro_sql_materias_docente("calificaciones.materia_id")
        c.execute(f"""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos, estudiantes.matricula,
                     secciones.id as seccion_id, secciones.grado_id,
                     estudiantes.especialidad_id, estudiantes.carrera_id,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                     AVG(calificaciones.valor) as promedio
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE calificaciones.estado_publicacion != 'Borrador'{filtro_materia}
                     GROUP BY calificaciones.estudiante_id
                     ORDER BY promedio DESC""", params_materia)
        filas= c.fetchall()
        conn.close()

        #El "puesto" se calcula sobre el ranking COMPLETO antes de filtrar, para que no cambie según lo que el usuario
        #esté buscando.
        #f: fila del ranking; se arma un dict id de estudiante -> puesto (posición + 1).
        puestos= {f["id"]: i + 1 for i, f in enumerate(filas)}

        filas_filtradas= self._aplicar_filtros_estudiante(filas, panel)
        panel["paginacion"].establecer_total(len(filas_filtradas))
        inicio, fin= panel["paginacion"].rango_actual()
        pagina= filas_filtradas[inicio:fin]

        with tabla_pausada(self.tabla_excelencia):
            self.tabla_excelencia.setRowCount(len(pagina))
            #f: fila del estudiante destacado de la página actual, pintada en la fila i de la tabla.
            for i, f in enumerate(pagina):
                self.tabla_excelencia.setItem(i, 0, QTableWidgetItem(str(puestos.get(f["id"], "—"))))
                self.tabla_excelencia.setItem(i, 1, QTableWidgetItem(f"{f['nombre']} {f['apellidos'] or ''}"))
                self.tabla_excelencia.setItem(i, 2, QTableWidgetItem(f"{f['promedio']:.2f}"))
                self.tabla_excelencia.setItem(i, 3, QTableWidgetItem(f["grado_nombre"] or "—"))
                self.tabla_excelencia.setItem(i, 4, QTableWidgetItem(f["seccion_nombre"] or "—"))
            ajustar_anchos_columnas(self.tabla_excelencia)
        self._animar_chip(panel["chip"], len(filas_filtradas), "estudiante destacado", "estudiantes destacados")
        self._animar_fundido_tabla(self.tabla_excelencia)

    #NOTA: btn_detalle en _tab_excelencia reutiliza el mismo diálogo de detalle para Administrador/Director y
    #Docente; el título del diálogo ("Detalle del Estudiante Destacado") es suficientemente genérico como para no
    #requerir texto distinto según el rol.

    #---------------- ASISTENCIA ----------------
    def _tab_asistencia(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        if self._es_docente():
            disposicion.addWidget(QLabel("Porcentaje de asistencia por estudiante, contando solo las clases de "
                               "las materias que tú impartes:"))
        else:
            disposicion.addWidget(QLabel("Porcentaje de asistencia por estudiante:"))

        panel= self._crear_barra_filtros("Buscar por nombre, apellido o matrícula…",
                                           titulo_filtros= "Filtros de Asistencia")
        disposicion.addWidget(panel["frame"])

        fila_cabecera_tabla_asistencia_rep= QHBoxLayout()
        fila_cabecera_tabla_asistencia_rep.addStretch()
        disposicion.addLayout(fila_cabecera_tabla_asistencia_rep)

        self.tabla_asistencia= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_asistencia)

        self.tabla_asistencia.setHorizontalHeaderLabels(
            ["Estudiante", "Presente", "Ausente/Tardanza", "% Asistencia"])
        header= self.tabla_asistencia.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_asistencia.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_asistencia.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_asistencia.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_asistencia.setAlternatingRowColors(True)
        self.tabla_asistencia.setWordWrap(True)
        self.tabla_asistencia.setMinimumHeight(380)
        self.tabla_asistencia.verticalHeader().setVisible(False)
        disposicion.addWidget(self.tabla_asistencia, 1)

        panel["paginacion"]= ControlPaginacion()
        _forzar_tam_pagina(panel["paginacion"])
        panel["paginacion"].cambio.connect(self._cargar_asistencia)
        panel["tabla"]= self.tabla_asistencia
        disposicion.addWidget(panel["paginacion"])
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_asistencia_rep, [self.tabla_asistencia, panel["paginacion"]],
            titulo= "Asistencia por Estudiante", parent=self)
        self._paneles["asistencia"]= panel
        self._conectar_filtros(panel, self._cargar_asistencia)
        self._cargar_combo_cursos(panel["combo_curso"], panel.get("combo_nivel"))
        self._cargar_combo_secciones(panel["combo_seccion"], panel["combo_curso"])
        self._cargar_combo_especialidad_carrera_rep(panel)

        fila_botones= QHBoxLayout()
        btn_actualizar= BotonAnimado("Actualizar")
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_asistencia)
        fila_botones.addWidget(btn_actualizar)

        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla_asistencia, self, titulo="Detalle de Asistencia del Estudiante")
        #*_: argumentos de la señal que se descartan; el doble clic en una fila pulsa el botón de detalle.
        self.tabla_asistencia.doubleClicked.connect(lambda *_: btn_detalle.click())

        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        return contenedor

    def _cargar_asistencia(self):

        panel= self._paneles["asistencia"]
        conn= obtener_conexion()
        c= conn.cursor()
        #Si es un docente, el consolidado solo debe contar la asistencia tomada en SUS materias -cada registro de
        #asistencia ya está atado a una materia y una fecha concretas, así que filtrar por materia_id ya deja fuera,
        #automáticamente, cualquier día/clase que no sea suya.
        filtro_materia, params_materia= self._filtro_sql_materias_docente("asistencia.materia_id")
        #Una sola consulta agregada en vez de 2 SELECT por estudiante: con cientos de estudiantes esto evita cientos de
        #idas y vueltas a la base de datos y mantiene la tabla fluida al filtrar/paginar.
        c.execute(f"""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos, estudiantes.matricula,
                     secciones.id as seccion_id, secciones.grado_id,
                     estudiantes.especialidad_id, estudiantes.carrera_id,
                     SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                     SUM(CASE WHEN asistencia.estado IS NOT NULL AND asistencia.estado!='Presente' THEN 1 ELSE 0 END) as ausencias
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN asistencia ON asistencia.estudiante_id = estudiantes.id{filtro_materia}
                     WHERE estudiantes.estado='Activo'
                     GROUP BY estudiantes.id
                     ORDER BY estudiantes.apellidos, estudiantes.nombre""", params_materia)
        filas= c.fetchall()
        conn.close()

        filas_filtradas= self._aplicar_filtros_estudiante(filas, panel)
        panel["paginacion"].establecer_total(len(filas_filtradas))
        inicio, fin= panel["paginacion"].rango_actual()
        pagina= filas_filtradas[inicio:fin]

        with tabla_pausada(self.tabla_asistencia):
            self.tabla_asistencia.setRowCount(len(pagina))
            #f: fila de asistencia de un estudiante; se calcula su porcentaje y se pinta en la fila i.
            for i, f in enumerate(pagina):
                presentes= f["presentes"] or 0
                ausencias= f["ausencias"] or 0
                total= presentes + ausencias
                porcentaje= round((presentes / total) * 100, 1) if total else 0
                self.tabla_asistencia.setItem(i, 0, QTableWidgetItem(f"{f['nombre']} {f['apellidos'] or ''}"))
                self.tabla_asistencia.setItem(i, 1, QTableWidgetItem(str(presentes)))
                self.tabla_asistencia.setItem(i, 2, QTableWidgetItem(str(ausencias)))
                self.tabla_asistencia.setItem(i, 3, QTableWidgetItem(f"{porcentaje}%"))
            ajustar_anchos_columnas(self.tabla_asistencia)
        self._animar_chip(panel["chip"], len(filas_filtradas), "estudiante", "estudiantes")
        self._animar_fundido_tabla(self.tabla_asistencia)

    #---------------- RENDIMIENTO TÉCNICO (Politécnico) ----------------
    def _tab_rendimiento_tecnico(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        lbl_info= QLabel("Rendimiento académico desglosado por materia técnica y especialidad, "
                      "independiente del reporte general de rendimiento institucional.")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        panel= self._crear_barra_filtros("Buscar por materia o especialidad…",
                                          con_curso_seccion= False, con_especialidad=True,
                                          titulo_filtros= "Filtros de Rendimiento Técnico")
        disposicion.addWidget(panel["frame"])

        fila_cabecera_tabla_rend_tecnico= QHBoxLayout()
        fila_cabecera_tabla_rend_tecnico.addStretch()
        disposicion.addLayout(fila_cabecera_tabla_rend_tecnico)

        self.tabla_rendimiento_tecnico= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_rendimiento_tecnico)

        self.tabla_rendimiento_tecnico.setHorizontalHeaderLabels(
            ["Especialidad", "Materia Técnica", "Evaluados", "Promedio", "Aprobados", "Reprobados"])
        header= self.tabla_rendimiento_tecnico.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_rendimiento_tecnico.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_rendimiento_tecnico.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_rendimiento_tecnico.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_rendimiento_tecnico.setAlternatingRowColors(True)
        self.tabla_rendimiento_tecnico.setWordWrap(True)
        self.tabla_rendimiento_tecnico.setMinimumHeight(380)
        self.tabla_rendimiento_tecnico.verticalHeader().setVisible(False)
        disposicion.addWidget(self.tabla_rendimiento_tecnico, 1)

        panel["paginacion"]= ControlPaginacion()
        _forzar_tam_pagina(panel["paginacion"])
        panel["paginacion"].cambio.connect(self._cargar_rendimiento_tecnico)
        panel["tabla"]= self.tabla_rendimiento_tecnico
        disposicion.addWidget(panel["paginacion"])
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_rend_tecnico, [self.tabla_rendimiento_tecnico, panel["paginacion"]],
            titulo= "Rendimiento Técnico", parent=self)
        self._paneles["rendimiento_tecnico"]= panel

        def _recargar():

            panel["paginacion"].reiniciar()
            self._cargar_rendimiento_tecnico()

        debounce= QTimer(self)
        debounce.setSingleShot(True)
        debounce.setInterval(180)
        debounce.timeout.connect(_recargar)
        panel["_debounce"]= debounce
        #_t: texto del buscador (no se usa); cada cambio solo reinicia el temporizador debounce.
        panel["buscar"].textChanged.connect(lambda _t: debounce.start())
        #_i: índice elegido en el combo (no se usa); solo dispara la recarga.
        panel["combo_especialidad"].currentIndexChanged.connect(lambda _i: _recargar())

        def _limpiar():

            panel["buscar"].blockSignals(True)
            panel["buscar"].clear()
            panel["buscar"].blockSignals(False)
            panel["combo_especialidad"].blockSignals(True)
            panel["combo_especialidad"].setCurrentIndex(0)
            panel["combo_especialidad"].blockSignals(False)
            _recargar()
        panel["btn_limpiar"].clicked.connect(_limpiar)
        self._cargar_combo_especialidades(panel["combo_especialidad"])

        fila_botones= QHBoxLayout()
        btn_actualizar= BotonAnimado("Actualizar")
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_rendimiento_tecnico)
        fila_botones.addWidget(btn_actualizar)

        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla_rendimiento_tecnico, self, titulo="Detalle de Rendimiento Técnico")
        #*_: argumentos de la señal que se descartan; el doble clic en una fila pulsa el botón de detalle.
        self.tabla_rendimiento_tecnico.doubleClicked.connect(lambda *_: btn_detalle.click())

        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)

        btn_pdf= BotonAnimado("Exportar Rendimiento Técnico (PDF)")
        btn_pdf.setObjectName("BtnAccionAgregar")
        btn_pdf.clicked.connect(self._exportar_rendimiento_tecnico_pdf)
        disposicion.addWidget(btn_pdf)

        return contenedor

    def _obtener_rendimiento_tecnico(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT nota_minima FROM configuracion WHERE id=1")
        fila_cfg= c.fetchone()
        #Fuera de alcance del cambio de nota mínima por nivel (Primaria/ Secundaria): esto es Rendimiento Técnico de
        #Educación Técnico-
        #Profesional (ETP, Politécnico) — post-secundaria y ajena a esa
        #clasificación, igual que calificaciones_tecnicas.py. Sigue usando la nota mínima general de siempre.
        nota_minima= (fila_cfg["nota_minima"] if fila_cfg else None) or 70
        anio= anio_academico_actual()
        #Las materias con modelo_evaluacion='Técnica (RA)' (Politécnico) NUNCA guardan
        #filas en `calificaciones` -su nota se calcula siempre en caliente a partir de calificacion_ra +
        #resultados_aprendizaje, igual que en 📐 Calificaciones
        #Técnicas (ver calificaciones_tecnicas.py). La Calificación Final (C.F.) de un
        #estudiante en una materia es el promedio ponderado por peso de sus RA.
        c.execute("""SELECT calificacion_ra.estudiante_id as estudiante_id,
                     resultados_aprendizaje.materia_id as materia_id,
                     resultados_aprendizaje.peso as peso, calificacion_ra.nota as nota
                     FROM calificacion_ra
                     JOIN resultados_aprendizaje ON resultados_aprendizaje.id = calificacion_ra.resultado_aprendizaje_id
                     JOIN materias ON materias.id = resultados_aprendizaje.materia_id
                     WHERE calificacion_ra.anio_academico=? AND calificacion_ra.nota IS NOT NULL
                       AND materias.modelo_evaluacion=? AND materias.especialidad_id IS NOT NULL
                     ORDER BY materia_id, estudiante_id""", (anio, MODELO_EVALUACION_TECNICA))
        filas_ra= c.fetchall()

        c.execute("""SELECT materias.id, materias.nombre as materia,
                     especialidades.id as especialidad_id, especialidades.nombre as especialidad
                     FROM materias LEFT JOIN especialidades ON materias.especialidad_id = especialidades.id
                     WHERE materias.modelo_evaluacion=? AND materias.especialidad_id IS NOT NULL""",
                  (MODELO_EVALUACION_TECNICA,))
        info_materias= {fila["id"]: dict(fila) for fila in c.fetchall()}
        conn.close()

        #Agrupa (materia_id, estudiante_id) -> lista de (nota, peso), luego calcula
        #la C.F. de cada estudiante como promedio ponderado (igual criterio que 📐 Calificaciones Técnicas). Solo se
        #cuenta un estudiante como "evaluado" si tiene al menos un RA calificado en esa materia.
        agrupado= {}
        #f: fila de un RA calificado; se agrupa por (materia, estudiante) con su nota y peso.
        for f in filas_ra:
            clave= (f["materia_id"], f["estudiante_id"])
            agrupado.setdefault(clave, []).append((f["nota"], f["peso"] or 0))

        por_materia= {}
        for (materia_id, estudiante_id), notas_pesos in agrupado.items():
            #p: peso de cada nota; n: nota. C.F. ponderada, o promedio simple si los pesos suman 0.
            suma_pesos= sum(p for _, p in notas_pesos)
            cf= (sum(n * p for n, p in notas_pesos) / suma_pesos) if suma_pesos > 0\
                else (sum(n for n, _ in notas_pesos) / len(notas_pesos))
            por_materia.setdefault(materia_id, []).append(cf)

        resultado= []
        for materia_id, cfs in por_materia.items():
            info= info_materias.get(materia_id)
            if not info:
                continue
            evaluados= len(cfs)
            aprobados= sum(1 for cf in cfs if cf >= nota_minima)
            resultado.append({
                "especialidad_id": info["especialidad_id"],
                "especialidad": info["especialidad"] or "Sin especialidad",
                "materia": info["materia"],
                "evaluados": evaluados,
                "promedio": round(sum(cfs) / evaluados, 2) if evaluados else 0.0,
                "aprobados": aprobados,
                "reprobados": evaluados - aprobados,
            })
        #f: dict de resumen de una materia; ordena por especialidad y luego por nombre de materia.
        resultado.sort(key=lambda f: (f["especialidad"], f["materia"]))
        return resultado

    def _filtrar_rendimiento_tecnico(self, filas, panel):

        texto= _normalizar(panel["buscar"].text().strip())
        especialidad_id= panel["combo_especialidad"].currentData() if panel.get("combo_especialidad") else None
        resultado= []
        for fila in filas:
            if especialidad_id is not None and fila["especialidad_id"] != especialidad_id:
                continue
            if texto:
                objetivo= _normalizar(f"{fila['materia']} {fila['especialidad']}")
                if texto not in objetivo:
                    continue
            resultado.append(fila)
        return resultado

    def _cargar_rendimiento_tecnico(self):

        if not hasattr(self, "tabla_rendimiento_tecnico"):
            return
        panel= self._paneles.get("rendimiento_tecnico")
        filas= self._obtener_rendimiento_tecnico()
        filas_filtradas= self._filtrar_rendimiento_tecnico(filas, panel) if panel else filas

        panel["paginacion"].establecer_total(len(filas_filtradas))
        inicio, fin= panel["paginacion"].rango_actual()
        pagina= filas_filtradas[inicio:fin]

        with tabla_pausada(self.tabla_rendimiento_tecnico):
            self.tabla_rendimiento_tecnico.setRowCount(len(pagina))
            #f: dict de rendimiento de una materia técnica de la página actual, pintado en la fila i.
            for i, f in enumerate(pagina):
                self.tabla_rendimiento_tecnico.setItem(i, 0, QTableWidgetItem(f["especialidad"]))
                self.tabla_rendimiento_tecnico.setItem(i, 1, QTableWidgetItem(f["materia"]))
                self.tabla_rendimiento_tecnico.setItem(i, 2, QTableWidgetItem(str(f["evaluados"])))
                self.tabla_rendimiento_tecnico.setItem(i, 3, QTableWidgetItem(f"{f['promedio']}"))
                self.tabla_rendimiento_tecnico.setItem(i, 4, QTableWidgetItem(str(f["aprobados"])))
                self.tabla_rendimiento_tecnico.setItem(i, 5, QTableWidgetItem(str(f["reprobados"])))
            ajustar_anchos_columnas(self.tabla_rendimiento_tecnico)
        self._animar_chip(panel["chip"], len(filas_filtradas), "materia técnica", "materias técnicas")
        self._animar_fundido_tabla(self.tabla_rendimiento_tecnico)

    def _exportar_rendimiento_tecnico_pdf(self):

        recursos= self._cargar_reportlab_graphics()
        if recursos is None:
            return
        letter, canvas, Drawing, String, VerticalBarChart, Pie, colors= recursos
        filas= self._obtener_rendimiento_tecnico()
        if not filas:
            mostrar_mensaje("advertencia", "Sin datos",
                           "No hay calificaciones registradas en materias técnicas para generar el reporte.", self)
            return
        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Reporte de Rendimiento Técnico",
                                               "reporte_rendimiento_tecnico.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        total_aprobados= sum(fila["aprobados"] for fila in filas)
        total_reprobados= sum(fila["reprobados"] for fila in filas)
        institucion= _datos_institucion()
        ancho, alto= letter
        cvs= canvas.Canvas(ruta, pagesize=letter)
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Reporte de Rendimiento por Materia Técnica")
        cvs.setFont("Helvetica", 9)
        cvs.drawString(50, y, f"Generado: {formatear_fecha_hora(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.main_window)}   |   "
                              f"Materias técnicas evaluadas: {len(filas)}")
        y -= 20
        self._dibujar_pie(cvs, Drawing, Pie, colors, 50, y - 220, 250, 240,
                          "Aprobados vs. Reprobados (Técnica)", ["Aprobados", "Reprobados"],
                          [total_aprobados, total_reprobados],
                          [colors.HexColor("#22C55E"), colors.HexColor("#EF4444")])
        #f: dict de resumen de una materia; se ordena por promedio descendente para tomar las 8 mejores.
        top_materias= sorted(filas, key=lambda f: f["promedio"], reverse=True)[:8]
        categorias= [top_materia["materia"][:12] for top_materia in top_materias]
        valores= [top_materia["promedio"] for top_materia in top_materias]
        self._dibujar_barras(cvs, Drawing, VerticalBarChart, colors, 310, y - 220, 250, 240,
                            "Promedio por Materia Técnica (Top 8)", categorias, valores,
                            colors.HexColor("#F59E0B"))
        y2= y - 250
        cvs.setFont("Helvetica-Bold", 11)
        cvs.drawString(50, y2, "Detalle por Especialidad / Materia Técnica")
        y2 -= 16
        cvs.setFont("Helvetica-Bold", 8)
        cvs.drawString(50, y2, "Especialidad")
        cvs.drawString(200, y2, "Materia")
        cvs.drawString(350, y2, "Evaluados")
        cvs.drawString(420, y2, "Promedio")
        cvs.drawString(490, y2, "Estado")
        y2 -= 12
        cvs.setFont("Helvetica", 8)
        for fila in filas:
            if y2 < 60:
                cvs.showPage()
                y2= alto - 60
            cvs.drawString(50, y2, fila["especialidad"][:24])
            cvs.drawString(200, y2, fila["materia"][:24])
            cvs.drawString(355, y2, str(fila["evaluados"]))
            cvs.drawString(422, y2, f"{fila['promedio']}")
            cvs.drawString(490, y2, f"{fila['aprobados']} aprob. / {fila['reprobados']} reprob.")
            y2 -= 12
        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.showPage()
        cvs.save()
        registrar_auditoria("Reportes", "Exportó reporte de rendimiento por materia técnica (PDF)",
                            self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Reporte guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    #---------------- REPORTES PDF CON GRÁFICOS ----------------
    def _tab_pdf_graficos(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        lbl_info= QLabel("Genera reportes PDF con el logotipo institucional y gráficos de barras/pastel "
                      "sobre el rendimiento académico y la asistencia general. Los archivos generados "
                      "quedan disponibles al instante en la pestaña «Vista Previa y Edición».")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)
        btn_rendimiento= BotonAnimado("Exportar Reporte de Rendimiento Académico (PDF)")
        btn_rendimiento.setObjectName("BtnAccionAgregar")
        btn_rendimiento.clicked.connect(self._exportar_rendimiento_pdf)
        disposicion.addWidget(btn_rendimiento)
        btn_asistencia_pdf= BotonAnimado("Exportar Reporte de Asistencia General (PDF)")
        btn_asistencia_pdf.setObjectName("BtnAccionEditar")
        btn_asistencia_pdf.clicked.connect(self._exportar_asistencia_pdf)
        disposicion.addWidget(btn_asistencia_pdf)
        disposicion.addStretch()
        return contenedor

    def _cargar_reportlab_graphics(self):

        try:

            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.graphics.shapes import Drawing, String
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            from reportlab.graphics.charts.piecharts import Pie
            from reportlab.lib import colors
            return letter, canvas, Drawing, String, VerticalBarChart, Pie, colors
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'reportlab' (pip install reportlab) para exportar reportes en PDF.", self)
            return None

    def _dibujar_pie(self, cvs, Drawing, Pie, colors, pos_x, y, ancho, alto, titulo, etiquetas, valores, paleta_colores):

        from reportlab.graphics.shapes import String
        dibujo= Drawing(ancho, alto)
        pie= Pie()
        pie.x= 40
        pie.y= 15
        pie.width= min(ancho, alto) - 60
        pie.height= pie.width
        pie.data= valores
        #e: etiqueta y v: valor de cada porción; la leyenda queda como 'etiqueta (valor)'.
        pie.labels= [f"{e} ({v})" for e, v in zip(etiquetas, valores)]
        pie.simpleLabels= 1
        pie.slices.strokeWidth= 0.5
        for i, color in enumerate(paleta_colores):
            if i < len(pie.data):
                pie.slices[i].fillColor= color
        dibujo.add(pie)
        dibujo.add(String(ancho / 2, alto - 14, titulo, textAnchor="middle", fontSize=10, fontName="Helvetica-Bold"))
        dibujo.drawOn(cvs, pos_x, y)

    def _dibujar_barras(self, cvs, Drawing, VerticalBarChart, colors, pos_x, y, ancho, alto, titulo,
                        categorias, valores, color_barra):

        from reportlab.graphics.shapes import String
        dibujo= Drawing(ancho, alto)
        grafico= VerticalBarChart()
        grafico.x= 45
        grafico.y= 30
        grafico.width= ancho - 65
        grafico.height= alto - 55
        grafico.data= [valores]
        grafico.categoryAxis.categoryNames= categorias
        grafico.categoryAxis.labels.angle= 25
        grafico.categoryAxis.labels.dy= -10
        grafico.categoryAxis.labels.fontSize= 6.5
        grafico.valueAxis.valueMin= 0
        maximo= max(valores) if valores else 100
        grafico.valueAxis.valueMax= max(10, maximo * 1.15)
        grafico.bars[0].fillColor= color_barra
        dibujo.add(grafico)
        dibujo.add(String(ancho / 2, alto - 14, titulo, textAnchor="middle", fontSize=10, fontName="Helvetica-Bold"))
        dibujo.drawOn(cvs, pos_x, y)

    def _exportar_rendimiento_pdf(self):

        recursos= self._cargar_reportlab_graphics()
        if recursos is None:
            return
        letter, canvas, Drawing, String, VerticalBarChart, Pie, colors= recursos
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT nota_minima, nota_minima_primaria, nota_minima_secundaria,
                     sistema_calificacion FROM configuracion WHERE id=1""")
        cfg= c.fetchone()
        #Igual que en _cargar_institucional: cada estudiante se compara contra la nota mínima de SU nivel educativo, no
        #una sola global.
        c.execute("""SELECT calificaciones.estudiante_id as estudiante_id,
                     AVG(calificaciones.valor) as promedio, grados.nivel_educativo as nivel
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE calificaciones.estado_publicacion != 'Borrador'
                     GROUP BY calificaciones.estudiante_id""")
        filas_promedios= c.fetchall()
        promedios= [filas_promedio["promedio"] for filas_promedio in filas_promedios]
        c.execute("""SELECT materias.nombre as materia, AVG(calificaciones.valor) as promedio
                     FROM calificaciones LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     WHERE materias.nombre IS NOT NULL AND calificaciones.estado_publicacion != 'Borrador'
                     GROUP BY calificaciones.materia_id ORDER BY promedio DESC LIMIT 8""")
        materias_prom= c.fetchall()
        conn.close()
        if not promedios:
            mostrar_mensaje("advertencia", "Sin datos", "No hay calificaciones registradas para generar el reporte.", self)
            return
        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Reporte de Rendimiento",
                                               "reporte_rendimiento.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        aprobados= sum(1 for filas_promedio in filas_promedios
                         if (filas_promedio["promedio"] or 0) >= resolver_nota_minima(cfg, nivel_educativo=filas_promedio["nivel"]))
        reprobados= len(promedios) - aprobados
        #La nota mínima ya no es un único número institucional cuando el sistema es el Dominicano (Primaria/Secundaria
        #difieren) — se muestra ambos valores en ese caso en vez de uno solo que podría no aplicarle a todos los
        #estudiantes evaluados.
        if cfg and es_sistema_dominicano(cfg["sistema_calificacion"]):
            texto_nota_minima= (f"Primaria {resolver_nota_minima(cfg, nivel_educativo='Primaria')} / "
                                  f"Secundaria {resolver_nota_minima(cfg, nivel_educativo='Secundaria')}")
        else:
            texto_nota_minima= str(resolver_nota_minima(cfg, nivel_educativo=None))
        institucion= _datos_institucion()
        ancho, alto= letter
        cvs= canvas.Canvas(ruta, pagesize=letter)
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Reporte de Rendimiento Académico")
        cvs.setFont("Helvetica", 9)
        cvs.drawString(50, y, f"Generado: {formatear_fecha_hora(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.main_window)}   |   "
                              f"Estudiantes evaluados: {len(promedios)}   |   Nota mínima: {texto_nota_minima}")
        y -= 20
        self._dibujar_pie(cvs, Drawing, Pie, colors, 50, y - 220, 250, 240,
                          "Aprobados vs. Reprobados", ["Aprobados", "Reprobados"],
                          [aprobados, reprobados], [colors.HexColor("#22C55E"), colors.HexColor("#EF4444")])
        if materias_prom:
            categorias= [m["materia"][:12] for m in materias_prom]
            valores= [round(m["promedio"], 1) for m in materias_prom]
            self._dibujar_barras(cvs, Drawing, VerticalBarChart, colors, 310, y - 220, 250, 240,
                                "Promedio por Materia (Top 8)", categorias, valores,
                                colors.HexColor("#6366F1"))
        y2= y - 250
        cvs.setFont("Helvetica-Bold", 11)
        cvs.drawString(50, y2, "Resumen")
        y2 -= 16
        cvs.setFont("Helvetica", 9)
        promedio_general= sum(promedios) / len(promedios)
        tasa_reprobacion= round((reprobados / len(promedios)) * 100, 1)
        cvs.drawString(50, y2, f"Promedio general institucional: {promedio_general:.2f}")
        y2 -= 14
        cvs.drawString(50, y2, f"Tasa de reprobación: {tasa_reprobacion}%")
        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.showPage()
        cvs.save()
        registrar_auditoria("Reportes", "Exportó reporte de rendimiento académico (PDF)",
                            self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Reporte guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    def _exportar_asistencia_pdf(self):

        recursos= self._cargar_reportlab_graphics()
        if recursos is None:
            return
        letter, canvas, Drawing, String, VerticalBarChart, Pie, colors= recursos
        conn= obtener_conexion()
        c= conn.cursor()
        estados= ["Presente", "Ausente", "Tardanza", "Excusado"]
        conteos= []
        for estado in estados:
            c.execute("SELECT COUNT(*) n FROM asistencia WHERE estado=?", (estado,))
            conteos.append(c.fetchone()["n"])
        c.execute("""SELECT (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                     COUNT(*) as total
                     FROM asistencia
                     LEFT JOIN secciones ON asistencia.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     GROUP BY asistencia.seccion_id
                     ORDER BY seccion_nombre""")
        por_seccion= c.fetchall()
        conn.close()
        if sum(conteos) == 0:
            mostrar_mensaje("advertencia", "Sin datos", "No hay registros de asistencia para generar el reporte.", self)
            return
        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Reporte de Asistencia",
                                               "reporte_asistencia.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        institucion= _datos_institucion()
        ancho, alto= letter
        cvs= canvas.Canvas(ruta, pagesize=letter)
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Reporte General de Asistencia")
        cvs.setFont("Helvetica", 9)
        cvs.drawString(50, y, f"Generado: {formatear_fecha_hora(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.main_window)}   |   "
                              f"Registros totales: {sum(conteos)}")
        y -= 20
        colores_estados= [colors.HexColor("#22C55E"), colors.HexColor("#EF4444"),
                          colors.HexColor("#F59E0B"), colors.HexColor("#3B82F6")]
        self._dibujar_pie(cvs, Drawing, Pie, colors, 50, y - 220, 250, 240,
                          "Distribución de Asistencia", estados, conteos, colores_estados)
        if por_seccion:
            #f: fila de asistencia de una sección; se usa su nombre (12 caracteres) y su % de presentes.
            categorias= [f["seccion_nombre"][:12] if f["seccion_nombre"] else "—" for f in por_seccion][:8]
            valores= [round((f["presentes"] / f["total"]) * 100, 1) if f["total"] else 0
                      for f in por_seccion][:8]
            self._dibujar_barras(cvs, Drawing, VerticalBarChart, colors, 310, y - 220, 250, 240,
                                "% Asistencia por Sección", categorias, valores,
                                colors.HexColor("#22C55E"))
        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.showPage()
        cvs.save()
        registrar_auditoria("Reportes", "Exportó reporte general de asistencia (PDF)",
                            self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Reporte guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    #---------------- EXPORTACIÓN MASIVA (XLSX) ----------------
    def _tab_exportacion_masiva(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        if self._es_docente():
            lbl_info= QLabel("Genera listados en formato Excel (.xlsx) con estilos, encabezados congelados y "
                          "anchos de columna ajustados. Las calificaciones y la asistencia se exportan "
                          "solo de las materias que tú impartes. Ábrelos directamente en «Vista Previa y "
                          "Edición» para revisarlos o retocarlos sin salir de AcaDeXI.")
        else:
            lbl_info= QLabel("Genera listados institucionales completos en formato Excel (.xlsx) con estilos, "
                          "encabezados congelados y anchos de columna ajustados. Ábrelos directamente en "
                          "«Vista Previa y Edición» para revisarlos o retocarlos sin salir de AcaDeXI.")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)
        btn_estudiantes= BotonAnimado("Exportar Listado de Estudiantes (XLSX)")
        btn_estudiantes.setObjectName("BtnAccionAgregar")
        btn_estudiantes.clicked.connect(self._exportar_estudiantes_xlsx)
        disposicion.addWidget(btn_estudiantes)
        btn_notas= BotonAnimado("Exportar Notas / Calificaciones (XLSX)")
        btn_notas.setObjectName("BtnAccionEditar")
        btn_notas.clicked.connect(self._exportar_notas_xlsx)
        disposicion.addWidget(btn_notas)
        btn_asistencia= BotonAnimado("Exportar Consolidado de Asistencia (XLSX)")
        btn_asistencia.setObjectName("BtnAccionAjustar")
        btn_asistencia.clicked.connect(self._exportar_asistencia_xlsx)
        disposicion.addWidget(btn_asistencia)
        disposicion.addStretch()
        return contenedor

    def _cargar_openpyxl(self):

        try:

            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            return openpyxl
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'openpyxl' (pip install openpyxl) para exportar en Excel.", self)
            return None

    def _hoja_con_estilos(self, wb, titulo_hoja, encabezados, filas, anchos=None):

        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        ws= wb.active
        ws.title= titulo_hoja
        color_encabezado= PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        fuente_encabezado= Font(color="FFFFFF", bold=True, size=11)
        alineacion_centro= Alignment(horizontal="center", vertical="center")
        borde_fino= Border(bottom=Side(style="thin", color="CBD5E1"))
        for col_idx, encabezado in enumerate(encabezados, start=1):
            celda= ws.cell(row=1, column=col_idx, value=encabezado)
            celda.fill= color_encabezado
            celda.font= fuente_encabezado
            celda.alignment= alineacion_centro
        for fila_idx, fila in enumerate(filas, start=2):
            for col_idx, valor in enumerate(fila, start=1):
                celda= ws.cell(row=fila_idx, column=col_idx, value=valor)
                celda.border= borde_fino
                if fila_idx % 2 == 0:
                    celda.fill= PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        ws.freeze_panes= "A2"
        anchos= anchos or [18] * len(encabezados)
        for col_idx, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width= ancho
        ws.auto_filter.ref= ws.dimensions
        return ws

    def _exportar_estudiantes_xlsx(self):

        if self._cargar_openpyxl() is None:
            return
        import openpyxl
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT estudiantes.matricula, estudiantes.nombre, estudiantes.apellidos, estudiantes.sexo,
                     estudiantes.fecha_nacimiento, estudiantes.documento, estudiantes.telefono, estudiantes.correo,
                     estudiantes.tutor, (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     estudiantes.estado
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     ORDER BY estudiantes.apellidos, estudiantes.nombre""")
        filas= [tuple(fila) for fila in c.fetchall()]
        conn.close()
        ruta, _= QFileDialog.getSaveFileName(self, "Exportar Estudiantes", "estudiantes.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        wb= openpyxl.Workbook()
        encabezados= ["Matrícula", "Nombre", "Apellidos", "Sexo", "Fecha Nac.", "Documento",
                       "Teléfono", "Correo", "Tutor/Padre", "Sección", "Estado"]
        anchos= [14, 18, 18, 12, 12, 16, 14, 24, 20, 22, 10]
        self._hoja_con_estilos(wb, "Estudiantes", encabezados, filas, anchos)
        wb.save(ruta)
        registrar_auditoria("Reportes", "Exportó listado de estudiantes (XLSX)", self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Listado de estudiantes guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    def _exportar_notas_xlsx(self):

        if self._cargar_openpyxl() is None:
            return
        import openpyxl
        conn= obtener_conexion()
        c= conn.cursor()
        #Igual que en la pestaña de Vista/Riesgo: si quien exporta es un docente, el Excel de calificaciones solo debe
        #traer SUS materias.
        filtro_materia, params_materia= self._filtro_sql_materias_docente("calificaciones.materia_id")
        c.execute(f"""SELECT (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as estudiante,
                     materias.nombre as materia, periodos.nombre as periodo, calificaciones.categoria,
                     calificaciones.descripcion, calificaciones.valor, calificaciones.peso
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     LEFT JOIN periodos ON calificaciones.periodo_id = periodos.id
                     WHERE calificaciones.estado_publicacion != 'Borrador'{filtro_materia}
                     ORDER BY estudiantes.apellidos, periodos.orden""", params_materia)
        filas= [tuple(fila) for fila in c.fetchall()]
        conn.close()
        ruta, _= QFileDialog.getSaveFileName(self, "Exportar Notas", "calificaciones.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        wb= openpyxl.Workbook()
        encabezados= ["Estudiante", "Materia", "Periodo", "Categoría", "Descripción", "Valor", "Peso (%)"]
        anchos= [22, 18, 14, 14, 26, 10, 10]
        self._hoja_con_estilos(wb, "Calificaciones", encabezados, filas, anchos)
        wb.save(ruta)
        registrar_auditoria("Reportes", "Exportó notas (XLSX)", self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Listado de calificaciones guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    def _exportar_asistencia_xlsx(self):

        if self._cargar_openpyxl() is None:
            return
        import openpyxl
        conn= obtener_conexion()
        c= conn.cursor()
        #Mismo criterio que en el consolidado en pantalla: si es un docente, solo su/s materia/s (lo que
        #automáticamente limita esto a los días que él impartió esa clase, porque cada registro de asistencia ya está
        #atado a una materia y una fecha concretas).
        filtro_materia, params_materia= self._filtro_sql_materias_docente("asistencia.materia_id")
        #Igual que en la tabla en pantalla: una sola consulta agregada en vez de 4 SELECT por estudiante.
        c.execute(f"""SELECT estudiantes.nombre, estudiantes.apellidos,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                     SUM(CASE WHEN asistencia.estado='Ausente' THEN 1 ELSE 0 END) as ausentes,
                     SUM(CASE WHEN asistencia.estado='Tardanza' THEN 1 ELSE 0 END) as tardanzas,
                     SUM(CASE WHEN asistencia.estado='Excusado' THEN 1 ELSE 0 END) as excusados
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN asistencia ON asistencia.estudiante_id = estudiantes.id{filtro_materia}
                     WHERE estudiantes.estado='Activo'
                     GROUP BY estudiantes.id
                     ORDER BY estudiantes.apellidos""", params_materia)
        filas_bd= c.fetchall()
        conn.close()
        filas= []
        for est in filas_bd:
            presentes= est["presentes"] or 0
            ausentes= est["ausentes"] or 0
            tardanzas= est["tardanzas"] or 0
            excusados= est["excusados"] or 0
            total= presentes + ausentes + tardanzas + excusados
            porcentaje= round((presentes / total) * 100, 1) if total else 0
            filas.append((f"{est['nombre']} {est['apellidos'] or ''}", est["seccion_nombre"] or "",
                          presentes, ausentes, tardanzas, excusados, f"{porcentaje}%"))
        ruta, _= QFileDialog.getSaveFileName(self, "Exportar Asistencia", "consolidado_asistencia.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        wb= openpyxl.Workbook()
        encabezados= ["Estudiante", "Sección", "Presente", "Ausente", "Tardanza", "Excusado", "% Asistencia"]
        anchos= [22, 22, 10, 10, 10, 10, 14]
        self._hoja_con_estilos(wb, "Asistencia", encabezados, filas, anchos)
        wb.save(ruta)
        registrar_auditoria("Reportes", "Exportó consolidado de asistencia (XLSX)", self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Consolidado de asistencia guardado en:\n{ruta}", self)
        self._registrar_archivo_reciente(ruta)

    #---------------- VISTA PREVIA Y EDICIÓN ----------------
    #OJO -causa real del "congelamiento"/ventana fantasma al entrar a
    #Reportes-: antes VisorEditorReportes (un widget pesado, con CUATRO
    #páginas completas -hoja de cálculo, PDF, Word- y decenas de
    #QToolButton con su propio QSS) se construía aquí mismo, de forma
    #síncrona, en el momento en que se arma TODO el módulo -aunque el
    #usuario nunca hubiera abierto esta pestaña-. Eso bloqueaba el hilo
    #principal casi un segundo, y Windows muestra su overlay "fantasma"
    #(blanco/atenuado) de ventana no responde durante ese bloqueo -lo que
    #se percibía como una ventana que "aparece y tarda en desaparecer".
    #Ahora esta pestaña solo pone un marcador de posición ligero, y el
    #editor pesado real se construye la PRIMERA vez que el usuario
    #realmente entra a esta pestaña (ver _construir_visor_editor_diferido,
    #conectado a tabs.currentChanged).
    def _tab_vista_previa(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 4, 0, 0)
        lbl_info= QLabel("Abre aquí los reportes que generes (CSV, Excel, Word o PDF): se abren en una vista "
                      "grande y cómoda donde puedes escribir directamente, dar formato, filtrar/ordenar, "
                      "exportarlos a otros formatos e imprimirlos, y en PDF navegar, rotar, insertar o "
                      "eliminar páginas, añadir una marca de agua o combinar documentos.")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)
        self._contenedor_visor_editor= QWidget()
        QVBoxLayout(self._contenedor_visor_editor).setContentsMargins(0, 0, 0, 0)
        disposicion.addWidget(self._contenedor_visor_editor, 1)
        self.visor_editor= None  #se crea de verdad recién al elegir un archivo (ver más abajo)
        self._rutas_recientes_reportes= getattr(self, "_rutas_recientes_reportes", [])
        self._indice_pestana_vista_previa= self.tabs.count() if hasattr(self, "tabs") else None
        return contenedor

    #Conectado a tabs.currentChanged: al entrar por primera vez a la
    #pestaña "Vista Previa y Edición" solo pone un marcador de posición
    #LIVIANO (botón "Abrir archivo" + recientes de esta sesión, si hay) -
    #instantáneo, sin construir nada pesado todavía. El editor pesado de
    #verdad (VisorEditorReportes, con sus 4 páginas y toda su cinta de
    #opciones) recién se construye cuando el usuario elige un archivo de
    #verdad -ver _placeholder_elegir_archivo/_terminar_de_abrir_editor-,
    #que es el único momento en el que hay trabajo pesado real que hacer
    #de todas formas. Así, entrar a la pestaña es instantáneo, y la
    #"ventana fantasma" (el bloqueo real de CPU al construir el editor)
    #solo puede llegar a notarse DESPUÉS de elegir un archivo -nunca
    #antes-.
    def _construir_visor_editor_diferido(self, indice):

        if self.visor_editor is not None or getattr(self, "_placeholder_visor_construido", False):
            return
        if indice != getattr(self, "_indice_pestana_vista_previa", None):
            return
        self._placeholder_visor_construido= True
        self._mostrar_placeholder_visor_editor()

    #Construye el marcador de posición liviano (botón "Abrir
    #archivo…" + recientes de esta sesión) y lo agrega al contenedor.
    #Factorizado aparte de _construir_visor_editor_diferido porque
    #también hace falta volver a mostrarlo cuando el usuario presiona
    #"Terminar de editar" y se destruye el editor pesado -ver
    #_terminar_editor_reportes()-, no solo la primera vez que se entra
    #a la pestaña.
    def _mostrar_placeholder_visor_editor(self):

        contenedor= QWidget()
        cl= QVBoxLayout(contenedor)
        cl.addStretch()
        lbl_icono= QLabel("")
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from src.nucleo.iconos_emoji import pixmap_emoji
        lbl_icono.setPixmap(pixmap_emoji("📄", 46))
        cl.addWidget(lbl_icono)
        lbl_texto= QLabel("Abre un PDF, Excel, Word o CSV para previsualizarlo y editarlo aquí.")
        lbl_texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_texto.setObjectName("DescModulo")
        lbl_texto.setWordWrap(True)
        cl.addWidget(lbl_texto)
        btn_abrir= BotonAnimado("Abrir archivo")
        btn_abrir.setObjectName("BtnAccionAgregar")
        fila_btn= QHBoxLayout()
        fila_btn.addStretch()
        fila_btn.addWidget(btn_abrir)
        fila_btn.addStretch()
        cl.addLayout(fila_btn)
        btn_abrir.clicked.connect(self._placeholder_elegir_archivo)
        if self._rutas_recientes_reportes:
            lbl_rec= QLabel("O abre un reporte reciente de esta sesión:")
            lbl_rec.setObjectName("DescModulo")
            lbl_rec.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(lbl_rec)
            for ruta in self._rutas_recientes_reportes[:5]:
                btn_rec= QPushButton(f"📄 {os.path.basename(ruta)}")
                btn_rec.setCursor(Qt.CursorShape.PointingHandCursor)
                #r: ruta del reporte reciente, fijada como valor por defecto para que cada botón abra la suya.
                btn_rec.clicked.connect(lambda _=False, r=ruta: self._terminar_de_abrir_editor(r))
                fila_rec= QHBoxLayout()
                fila_rec.addStretch()
                fila_rec.addWidget(btn_rec)
                fila_rec.addStretch()
                cl.addLayout(fila_rec)
        cl.addStretch()
        self._contenedor_visor_editor.layout().addWidget(contenedor)
        self._placeholder_visor_editor= contenedor

    #Botón "Abrir archivo" del marcador de posición liviano: el
    #diálogo de selección es nativo del sistema operativo (no lo
    #construye Qt "pesado", así que no bloquea nada) y, recién DESPUÉS
    #de que el usuario elija de verdad un archivo, se construye el
    #editor real -que es cuando corresponde ver cualquier indicador de
    #carga, no antes.
    def _placeholder_elegir_archivo(self):

        from src.modulos.reportes_editor import FILTRO_ABRIR
        ruta, _= QFileDialog.getOpenFileName(self, "Abrir reporte", "", FILTRO_ABRIR)
        if ruta:
            self._terminar_de_abrir_editor(ruta)

    #Ya con un archivo elegido de verdad: AHORA sí se muestra un
    #"Cargando…" y se construye el editor pesado -en dos pasos, igual
    #que antes, para que el mensaje llegue a pintarse antes del bloqueo
    #real de CPU-.
    def _terminar_de_abrir_editor(self, ruta):

        if self.visor_editor is not None:
            self.visor_editor.abrir_archivo(ruta)
            return
        layout= self._contenedor_visor_editor.layout()
        if getattr(self, "_placeholder_visor_editor", None) is not None:
            layout.removeWidget(self._placeholder_visor_editor)
            self._placeholder_visor_editor.deleteLater()
            self._placeholder_visor_editor= None
        etiqueta_carga= QLabel("⏳ Cargando editor…")
        etiqueta_carga.setObjectName("DescModulo")
        etiqueta_carga.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(etiqueta_carga)
        QApplication.processEvents()

        def _construir_de_verdad():

            self.visor_editor= VisorEditorReportes(self.main_window)
            self.visor_editor.solicitud_terminar_edicion.connect(self._terminar_editor_reportes)
            layout.removeWidget(etiqueta_carga)
            etiqueta_carga.deleteLater()
            layout.addWidget(self.visor_editor)
            self.visor_editor.actualizar_tema()
            #Los reportes que se exportaron desde otras pestañas ANTES de que este editor existiera (ver
            #_registrar_archivo_reciente) se le pasan ahora, para que aparezcan en su combo de "Archivos recientes" como si
            #siempre hubiera estado abierto.
            #r: ruta de un reporte exportado antes de crear el editor; se agrega a sus archivos recientes.
            for r in reversed(self._rutas_recientes_reportes):
                self.visor_editor.agregar_reciente(r)
            self.visor_editor.abrir_archivo(ruta)

        QTimer.singleShot(0, _construir_de_verdad)

    #Conectado a la señal VisorEditorReportes.solicitud_terminar_edicion,
    #que se emite al presionar "Terminar de editar" en el panel de
    #bienvenida del editor. A diferencia de solo salir de pantalla
    #completa (donde el archivo -workbook de Excel, PDF abierto,
    #contenido de Word- sigue vivo en memoria por si el usuario quiere
    #"Continuar editando"), esto destruye la instancia entera de
    #VisorEditorReportes -el widget pesado con sus 4 páginas y toda su
    #cinta de opciones- y deja la pestaña otra vez en el mismo estado
    #liviano (marcador de posición) que tiene la primera vez que se
    #entra a ella, para no seguir gastando memoria/CPU sin necesidad.
    def _terminar_editor_reportes(self):

        if getattr(self, "visor_editor", None) is None:
            return
        disposicion= self._contenedor_visor_editor.layout()
        disposicion.removeWidget(self.visor_editor)
        self.visor_editor.deleteLater()
        self.visor_editor= None
        self._mostrar_placeholder_visor_editor()

    #Avisa al visor de la nueva pestaña que se acaba de generar un
    #archivo, para que aparezca de inmediato en «Archivos recientes».
    #Se guarda además en self._rutas_recientes_reportes -que vive en
    #ESTE módulo, no en el editor- para que quede disponible incluso si
    #el editor pesado todavía no se construyó (el usuario nunca entró a
    #esa pestaña, o entró pero no eligió ningún archivo todavía): al
    #construirlo se le pasan todas de una vez (ver
    #_terminar_de_abrir_editor).
    def _registrar_archivo_reciente(self, ruta):

        if not ruta:
            return
        self._rutas_recientes_reportes= getattr(self, "_rutas_recientes_reportes", [])
        self._rutas_recientes_reportes= [rutas_recientes_reporte for rutas_recientes_reporte in self._rutas_recientes_reportes if rutas_recientes_reporte != ruta]
        self._rutas_recientes_reportes.insert(0, ruta)
        self._rutas_recientes_reportes= self._rutas_recientes_reportes[:10]
        if getattr(self, "visor_editor", None) is not None:
            self.visor_editor.agregar_reciente(ruta)

    #------------------------------------------------------------
    def refrescar(self):

        #Para un docente, varias de estas pestañas ni siquiera se
        #construyeron (ver _construir_ui): solo refrescamos lo que exista.
        #OJO: antes se comprobaba `hasattr(self, "tabla_institucional")`, pero esa pestaña nunca crea ninguna tabla con
        #ese nombre -crea tarjetas KPI (self.kpi_estudiantes, etc.)-, así que esa condición era SIEMPRE False y
        #_cargar_institucional() nunca se llamaba: la pestaña "Institucional" se quedaba en blanco/con ceros para
        #siempre, incluso pulsando "🔄 Actualizar todo".
        if hasattr(self, "kpi_estudiantes"):
            self._cargar_institucional()
        self._cargar_riesgo()
        if hasattr(self, "tabla_excelencia"):
            self._cargar_excelencia()
        self._cargar_asistencia()
        if hasattr(self, "tabla_rendimiento_tecnico"):
            self._cargar_rendimiento_tecnico()
        #Icono de reloj dibujado con QPainter (mismo dibujo que ya usa el resto de la app), insertado como <img> inline
        #en vez del emoji real para no depender de una fuente de emojis del sistema.
        self.chip_actualizado.setText(
            f"{html_icono_emoji('🕒', 14)} Actualizado "
            f"{formatear_hora(datetime.now().strftime('%H:%M'), self.main_window)}")

    def actualizar_tema(self):

        colores= _colores_tema(self.main_window)
        #Barra de pestañas: mismo diseño "píldora" con degradado que en Configuración y Asistencia (se estiliza aparte,
        #solo sobre self.tabs, para no forzar un repintado de todo el módulo).
        accent_suave= _hex_a_rgba(colores['accent'], 0.16)
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
                background: {colores['bg_btn']};
                color: {colores['txt_sec']};
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colores['accent']}, stop:1 {colores['accent_hv']});
                color: white;
            }}
            QTabBar::tab:!selected:hover {{
                background: {accent_suave};
                color: {colores['txt_prim']};
            }}
        """ + estilo_flechas_navegacion_tabs(colores['accent'], colores['accent_hv'], colores['bg_panel'],
                                              colores['bg_btn'], accent_suave))
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
        self.chip_actualizado.setStyleSheet("""
            QLabel#ChipContador {
                background-color: rgba(255, 255, 255, 40);
                color: white;
                border-radius: 14px;
                padding: 7px 16px;
                font-weight: 700;
                font-size: 12px;
            }
        """)
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QFrame#TarjetaKPI {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 16px;
            }}
            QLabel#IconoKPI {{
                background-color: {_hex_a_rgba(colores['accent'], 35)};
                border-radius: 10px;
                font-size: 18px;
            }}
            QLabel#ValorKPI {{
                font-size: 26px;
                font-weight: 800;
                color: {colores['txt_prim']};
                background: transparent;
            }}
            QLabel#TituloKPI {{
                font-size: 12px;
                color: {colores['txt_sec']};
                background: transparent;
            }}
            QFrame#TarjetaFormulario {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 16px;
            }}
            QLabel#TituloTarjetaInterna {{
                font-size: 14px;
                font-weight: 800;
                color: {colores['txt_prim']};
                background: transparent;
            }}
            QFrame#TarjetaFiltros {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 14px;
            }}
            QFrame#MarcoBusqueda {{
                background: rgba(127,127,127,0.10);
                border-radius: 12px;
            }}
            QLineEdit#InputBusquedaFiltro {{
                border: none;
                background: transparent;
                padding: 8px 0;
            }}
            QLabel#ChipResultadoFiltro {{
                background-color: {_hex_a_rgba(colores['accent'], 28)};
                color: {colores['accent']};
                border-radius: 12px;
                padding: 5px 12px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton#BtnLimpiarFiltro {{
                background: transparent;
                color: {colores['txt_sec']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 10px;
                padding: 5px 10px;
            }}
            QPushButton#BtnLimpiarFiltro:hover {{
                background-color: {colores['bg_btn']};
            }}
        """)
        for anillo in (getattr(self, "kpi_asistencia", None), getattr(self, "kpi_reprobacion", None)):
            if anillo is not None:
                anillo.anillo.establecer_color_texto(colores["txt_prim"])
        if hasattr(self, "mini_barras_materias"):
            self.mini_barras_materias.establecer_color_texto(colores["txt_sec"])
        if getattr(self, "visor_editor", None) is not None:
            self.visor_editor.actualizar_tema()

        estilo_dialogo_filtros= f"""
            QDialog#DialogoFiltrosReportes {{
                background-color: {colores['bg_panel']};
            }}
            /* Repite aquí el mismo QToolTip que usa la ventana principal:
               este diálogo es una ventana de nivel superior aparte, y su
               propio setStyleSheet() reemplaza -para todo lo que esté
               dentro- cualquier regla heredada, incluido el QToolTip global.
               Sin esto, los tooltips de los combos aquí adentro caían al
               estilo nativo de Qt (gris claro/texto negro), inconsistente
               con el resto de AcaDeXI. */
            QToolTip {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QLabel#IconoEncabezadoFiltrosRep {{
                background-color: {colores['accent']};
                color: white;
                border-radius: 15px;
                min-width: 30px; max-width: 30px;
                min-height: 30px; max-height: 30px;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }}
            QLabel#TituloEncabezadoFiltrosRep {{
                font-size: 16px;
                font-weight: 800;
                color: {colores['txt_prim']};
                background: transparent;
            }}
            QLabel#SubtituloFiltrosRep {{
                font-size: 11.5px;
                color: {colores['txt_sec']};
                background: transparent;
            }}
            QFrame#SeparadorFiltrosRep {{
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
        """
        for dialogo in getattr(self, "_dialogos_filtros_reportes", []):
            dialogo.setStyleSheet(estilo_dialogo_filtros)