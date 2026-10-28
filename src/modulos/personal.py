import os
import unicodedata
from PySide6.QtWidgets import (QToolTip, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QGridLayout,
    QDateEdit, QScrollArea, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QDialog)
from PySide6.QtCore import (Qt, QDate, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen
from src.nucleo.bd import obtener_conexion, registrar_auditoria, obtener_carpeta_datos
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.nucleo.permisos import puede_editar
from src.interfaz.foto_utils import seleccionar_y_recortar_foto, VisorFotoDialog
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, obtener_pixmap_circular_cacheado, ROL_RUTA_FOTO,
    configurar_columna_foto, pixmap_placeholder_foto_tabla, TAMANO_FOTO_TABLA, agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import aplicar_formato_widget_fecha
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, html_icono_emoji,
                          icono_boton_filtro, pixmap_boton_filtro, EMOJI_FOTO_RECORTAR)
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion

ESTADOS= ["Activo", "Inactivo"]
CARGOS_SUGERIDOS= ["Director", "Subdirector", "Coordinador Académico", "Coordinador de Convivencia",
    "Secretario(a)", "Asistente Administrativo", "Contador(a)", "Tesorero(a)",
    "Encargado de Admisiones", "Bibliotecario(a)", "Psicólogo(a)", "Recepcionista",
    "Personal de Mantenimiento", "Otro"]


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica. (mismo lenguaje visual que
#estudiantes.py/profesores.py, para que todos los módulos se sientan parte de la misma aplicación)
#Convierte un color '#RRGGBB' a una cadena rgba(...) con la opacidad indicada.
def _hex_a_rgba(color_hex, alpha):

    color_hex= (color_hex or "#2563EB").lstrip("#")
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Lee la paleta/tema activo de la ventana principal para que las tarjetas de
#este módulo respeten el tema y el modo claro/oscuro que el usuario ya eligió.
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


#Devuelve una copia circular (estilo avatar) de `pixmap`. Es solo otra forma
#de DIBUJAR la misma foto ya guardada: no altera el archivo ni el dato 'foto'
#que se guarda en la base de datos.
def _redondear_pixmap(pixmap, tamano):

    if pixmap is None or pixmap.isNull():
        return pixmap
    fuente= pixmap.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
    resultado= QPixmap(tamano, tamano)
    resultado.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(resultado)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    ruta= QPainterPath()
    ruta.addEllipse(0, 0, tamano, tamano)
    pintor.setClipPath(ruta)
    pos_x= (tamano - fuente.width()) // 2
    pos_y= (tamano - fuente.height()) // 2
    pintor.drawPixmap(pos_x, pos_y, fuente)
    pintor.end()
    return resultado


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


#QPushButton normal (misma señal `clicked`, mismo objectName, mismo estilo
#por QSS/tema) que además 'respira' con una sombra suave al pasar el mouse por
#encima. Solo anima mientras el cursor está sobre el botón —nunca en segundo
#plano—, así que no cuesta rendimiento en reposo.
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


#Anillo (donut) dibujado a mano con QPainter que compara el personal
#'Activo' contra 'Inactivo'. Reemplaza a una tarjeta KPI clásica: en vez de
#un número dentro de un rectángulo, el dato se lee en la proporción del
#propio anillo. Se 'dibuja' con un barrido animado cada vez que llegan
#datos nuevos, pero no corre ninguna animación en segundo plano cuando
#está en reposo (más liviano para el rendimiento del módulo).
class AnilloEstado(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(84, 84)
        self._activos= 0
        self._inactivos= 0
        self._progreso= 1.0
        self._color_activo= QColor("#22C55E")
        self._color_inactivo= QColor("#EF4444")
        self._color_pista= QColor(0, 0, 0, 30)
        self._color_texto= QColor("#1E293B")
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(750)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._al_progreso)

    def establecer_colores_tema(self, color_pista, color_texto):

        self._color_pista= QColor(color_pista)
        self._color_texto= QColor(color_texto)
        self.update()

    def establecer_datos(self, activos, inactivos, animar=True):

        self._activos= max(0, int(activos))
        self._inactivos= max(0, int(inactivos))
        if animar:
            self._anim.stop()
            self._progreso= 0.0
            self._anim.start()
        else:
            self._progreso= 1.0
            self.update()

    def _al_progreso(self, valor):

        self._progreso= valor
        self.update()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect= self.rect().adjusted(7, 7, -7, -7)
        grosor= 9

        pintor.setPen(QPen(self._color_pista, grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pintor.drawArc(rect, 0, 360 * 16)

        total= self._activos + self._inactivos
        if total > 0:
            angulo_inicio= 90 * 16
            ang_activo= int(360 * 16 * (self._activos / total) * self._progreso)
            pintor.setPen(QPen(self._color_activo, grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            pintor.drawArc(rect, angulo_inicio, -ang_activo)
            ang_inactivo= int(360 * 16 * (self._inactivos / total) * self._progreso)
            pintor.setPen(QPen(self._color_inactivo, grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            pintor.drawArc(rect, angulo_inicio - ang_activo, -ang_inactivo)

        pintor.setPen(self._color_texto)
        fuente= pintor.font()
        fuente.setPointSize(15)
        fuente.setBold(True)
        pintor.setFont(fuente)
        valor_mostrado= int(round(total * self._progreso)) if total else 0
        pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(valor_mostrado))
        pintor.end()


#Mini gráfico de barras horizontales, dibujado con QPainter, que muestra
#los cargos con más personas registradas. Cada barra 'crece' con una
#animación suave cuando llegan datos nuevos. Es otra alternativa a la
#tarjeta KPI: aquí el dato relevante (qué cargos predominan en la planta
#administrativa) se ve de un vistazo, en vez de solo un número suelto.
class BarrasDistribucion(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self._datos= []  #lista de (etiqueta, valor)
        self._filas_rect= []  #lista de (QRectF, etiqueta_completa) para tooltips
        self._progreso= 1.0
        self._color_barra= QColor("#2563EB")
        self._color_texto= QColor("#1E293B")
        self._color_texto_sec= QColor("#64748B")
        self._color_pista= QColor(0, 0, 0, 20)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._al_progreso)

    def establecer_colores_tema(self, color_barra, color_texto, color_texto_sec, color_pista):

        self._color_barra= QColor(color_barra)
        self._color_texto= QColor(color_texto)
        self._color_texto_sec= QColor(color_texto_sec)
        self._color_pista= QColor(color_pista)
        self.update()

    def establecer_datos(self, pares, animar=True):

        self._datos= list(pares)[:5]
        if animar:
            self._anim.stop()
            self._progreso= 0.0
            self._anim.start()
        else:
            self._progreso= 1.0
            self.update()

    def _al_progreso(self, valor):

        self._progreso= valor
        self.update()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._datos:
            pintor.setPen(self._color_texto_sec)
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aún no hay suficientes datos de cargos.")
            pintor.end()
            return

        maximo= max(valor for _, valor in self._datos) or 1
        cantidad= len(self._datos)
        alto_fila= self.height() / cantidad
        alto_barra= min(16, alto_fila * 0.42)
        ancho_etiqueta= 122
        ancho_valor= 26
        ancho_disponible= max(10, self.width() - ancho_etiqueta - ancho_valor - 10)

        fuente= pintor.font()
        fuente.setPointSize(9)
        pintor.setFont(fuente)

        self._filas_rect= []
        for i, (etiqueta, valor) in enumerate(self._datos):
            y_centro= alto_fila * i + alto_fila / 2

            pintor.setPen(self._color_texto)
            rect_etq= QRectF(0, y_centro - 9, ancho_etiqueta, 18)
            texto= etiqueta if len(etiqueta) <= 18 else etiqueta[:17] + "…"
            pintor.drawText(rect_etq, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), texto)
            #Guardamos toda la fila (etiqueta + barra + valor) junto con el nombre completo del cargo, para mostrarlo como
            #tooltip al pasar el cursor por encima (la etiqueta puede venir recortada con "…").
            rect_fila_completa= QRectF(0, alto_fila * i, self.width(), alto_fila)
            self._filas_rect.append((rect_fila_completa, etiqueta))

            x0= ancho_etiqueta
            rect_pista= QRectF(x0, y_centro - alto_barra / 2, ancho_disponible, alto_barra)
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(self._color_pista)
            pintor.drawRoundedRect(rect_pista, alto_barra / 2, alto_barra / 2)

            ancho_barra= ancho_disponible * (valor / maximo) * self._progreso
            if ancho_barra > 1:
                rect_barra= QRectF(x0, y_centro - alto_barra / 2, ancho_barra, alto_barra)
                pintor.setBrush(self._color_barra)
                pintor.drawRoundedRect(rect_barra, alto_barra / 2, alto_barra / 2)

            pintor.setPen(self._color_texto_sec)
            rect_valor= QRectF(x0 + ancho_disponible + 8, y_centro - 9, ancho_valor, 18)
            valor_mostrado= int(round(valor * self._progreso))
            pintor.drawText(rect_valor, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(valor_mostrado))
        pintor.end()

    def mouseMoveEvent(self, evento):

        pos= evento.position() if hasattr(evento, "position") else evento.pos()
        for rect_fila, etiqueta in self._filas_rect:
            if rect_fila.contains(pos):
                QToolTip.showText(evento.globalPosition().toPoint(), etiqueta, self)
                break
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):

        QToolTip.hideText()
        super().leaveEvent(evento)


#Fila de miniaturas circulares superpuestas ('team avatars') que muestra
#de un vistazo las fotos del personal más reciente. Es una capa puramente
#visual, compuesta en un único widget para que sea barata de repintar: no
#afecta la lista real de personal ni sus datos.
class PilaAvatares(QWidget):

    TAMANO= 34
    SOLAPE= 14

    def __init__(self, parent=None):

        super().__init__(parent)
        self._pixmaps= []
        self._extra= 0
        self._color_borde= QColor("#FFFFFF")
        self.setFixedHeight(self.TAMANO)
        self.setFixedWidth(self.TAMANO)

    def establecer_avatares(self, pixmaps, extra=0):

        self._pixmaps= list(pixmaps)[:5]
        self._extra= max(0, int(extra))
        paso= self.TAMANO - self.SOLAPE
        ancho= self.TAMANO + max(0, len(self._pixmaps) - 1) * paso
        if self._extra > 0:
            ancho += paso
        self.setFixedWidth(max(ancho, self.TAMANO))
        self.update()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        paso= self.TAMANO - self.SOLAPE
        x= 0
        for pix in self._pixmaps:
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.setPen(QPen(self._color_borde, 2))
            pintor.drawEllipse(x, 0, self.TAMANO, self.TAMANO)
            pintor.drawPixmap(x + 1, 1, self.TAMANO - 2, self.TAMANO - 2, pix)
            x += paso
        if self._extra > 0:
            pintor.setBrush(QColor(255, 255, 255, 60))
            pintor.setPen(QPen(self._color_borde, 2))
            pintor.drawEllipse(x, 0, self.TAMANO, self.TAMANO)
            pintor.setPen(self._color_borde)
            fuente= pintor.font()
            fuente.setBold(True)
            fuente.setPointSize(8)
            pintor.setFont(fuente)
            pintor.drawText(QRectF(x, 0, self.TAMANO, self.TAMANO), Qt.AlignmentFlag.AlignCenter, f"+{self._extra}")
        pintor.end()


class ModuloPersonal(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion= None
        self.foto_path= ""
        self._contador_valor_actual= 0
        self._construir_ui()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        #Módulo de personal administrativo: exclusivo de roles gerenciales, un Profesor no accede a esta pantalla.
        self._titulo_modulo_atajos= "Personal"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar seleccionado", self._cargar_seleccionado)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar", self._eliminar)

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

        #--- Cabecera tipo "hero": icono + título + descripción + fotos recientes + contador ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Personal")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Personal Administrativo y Directivos")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Fichas de perfil y cargo del personal directivo y administrativo, "
            "independientes de los profesores y de las cuentas de usuario genéricas.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        self.pila_avatares= PilaAvatares()
        self.pila_avatares.setToolTip("Fotografías más recientes del personal")
        self.pila_avatares.setVisible(False)
        cabecera_layout.addWidget(self.pila_avatares, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_contador= QLabel(f"{html_icono_emoji('🗂', 15)} 0 personas")
        self.chip_contador.setObjectName("ChipContador")
        self.chip_contador.setTextFormat(Qt.TextFormat.RichText)
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)
        disposicion.addWidget(self.frame_cabecera)

        #--- Panorama del personal: anillo Activo/Inactivo + barras por cargo --- (reemplaza a las tarjetas KPI
        #clásicas por gráficos dibujados a mano)
        self.frame_panorama= QFrame()
        self.frame_panorama.setObjectName("TarjetaPanorama")
        panorama_layout= QVBoxLayout(self.frame_panorama)
        panorama_layout.setContentsMargins(20, 16, 20, 16)
        panorama_layout.setSpacing(10)

        lbl_titulo_panorama= QLabel("Panorama del Personal")
        lbl_titulo_panorama.setObjectName("TituloTarjetaInterna")
        panorama_layout.addWidget(lbl_titulo_panorama)

        fila_panorama= QHBoxLayout()
        fila_panorama.setSpacing(22)

        col_izq= QHBoxLayout()
        col_izq.setSpacing(14)
        self.anillo_estado= AnilloEstado()
        col_izq.addWidget(self.anillo_estado, 0, Qt.AlignmentFlag.AlignVCenter)
        bloque_leyenda= QVBoxLayout()
        bloque_leyenda.setSpacing(4)
        lbl_leyenda_titulo= QLabel("Activo vs. Inactivo")
        lbl_leyenda_titulo.setObjectName("DescModulo")
        self.lbl_leyenda_activos= QLabel("● Activos: 0")
        self.lbl_leyenda_inactivos= QLabel("● Inactivos: 0")
        bloque_leyenda.addWidget(lbl_leyenda_titulo)
        bloque_leyenda.addWidget(self.lbl_leyenda_activos)
        bloque_leyenda.addWidget(self.lbl_leyenda_inactivos)
        bloque_leyenda.addStretch()
        col_izq.addLayout(bloque_leyenda)
        fila_panorama.addLayout(col_izq, 0)

        self.separador_panorama= QFrame()
        self.separador_panorama.setFrameShape(QFrame.Shape.VLine)
        fila_panorama.addWidget(self.separador_panorama)

        col_der= QVBoxLayout()
        col_der.setSpacing(6)
        lbl_barras_titulo= QLabel("Cargos con más personal")
        lbl_barras_titulo.setObjectName("DescModulo")
        col_der.addWidget(lbl_barras_titulo)
        self.barras_cargos= BarrasDistribucion()
        col_der.addWidget(self.barras_cargos)
        fila_panorama.addLayout(col_der, 1)

        panorama_layout.addLayout(fila_panorama)
        disposicion.addWidget(self.frame_panorama)

        #--- Panel de creación/edición ---
        self.panel_edicion= QFrame()
        self.panel_edicion.setObjectName("TarjetaFormulario")
        self._color_sombra_normal= QColor(0, 0, 0, 55)
        self._sombra_formulario= QGraphicsDropShadowEffect(self.panel_edicion)
        self._sombra_formulario.setColor(self._color_sombra_normal)
        self._sombra_formulario.setOffset(0, 4)
        self._sombra_formulario.setBlurRadius(22)
        self.panel_edicion.setGraphicsEffect(self._sombra_formulario)
        panel_layout= QVBoxLayout(self.panel_edicion)
        panel_layout.setContentsMargins(20, 18, 20, 16)
        panel_layout.setSpacing(12)

        lbl_titulo_ficha= QLabel("Ficha del Personal")
        lbl_titulo_ficha.setObjectName("TituloTarjetaInterna")
        panel_layout.addWidget(lbl_titulo_ficha)

        form= QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre, 300)
        self.in_nombre.setPlaceholderText("Nombre")
        self.in_apellidos= QLineEdit()
        limitar_campo_texto(self.in_apellidos, 300)
        self.in_apellidos.setPlaceholderText("Apellidos")
        self.combo_cargo= QComboBox()
        self.combo_cargo.setEditable(True)
        self.combo_cargo.addItems(CARGOS_SUGERIDOS)
        conectar_tooltip_seleccion(self.combo_cargo,
            "Cargo o puesto de la persona. Puedes elegir uno sugerido o escribir uno propio")
        self.in_departamento= QLineEdit()
        limitar_campo_texto(self.in_departamento, 300)
        self.in_departamento.setPlaceholderText("Departamento/Área")
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo, 200)
        self.in_correo.setPlaceholderText("Correo")
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono, 300)
        self.in_telefono.setPlaceholderText("Teléfono")
        self.in_direccion= QLineEdit()
        limitar_campo_texto(self.in_direccion, 300)
        self.in_direccion.setPlaceholderText("Dirección")
        self.date_ingreso= QDateEdit(calendarPopup=True)
        self.date_ingreso.setDate(QDate.currentDate())
        aplicar_formato_widget_fecha(self.date_ingreso, self.main_window)
        self.combo_estado= QComboBox()
        self.combo_estado.addItems(ESTADOS)
        conectar_tooltip_seleccion(self.combo_estado, "Estado laboral actual de la persona")
        lbl_cuenta= QLabel("Cuenta de acceso:")
        lbl_cuenta.setObjectName("DescModulo")
        self.combo_usuario= QComboBox()
        conectar_tooltip_seleccion(self.combo_usuario, "Cuenta de acceso (login) vinculada a esta ficha de personal")

        form.addWidget(self.in_nombre, 0, 0)
        form.addWidget(self.in_apellidos, 0, 1)
        form.addWidget(self.combo_cargo, 0, 2)
        form.addWidget(self.in_departamento, 1, 0)
        form.addWidget(self.in_correo, 1, 1)
        form.addWidget(self.in_telefono, 1, 2)
        form.addWidget(self.in_direccion, 2, 0)
        lbl_fecha= QLabel("Fecha de Ingreso:")
        lbl_fecha.setObjectName("DescModulo")
        form.addWidget(lbl_fecha, 2, 1)
        form.addWidget(self.date_ingreso, 2, 2)
        form.addWidget(self.combo_estado, 3, 0)
        form.addWidget(lbl_cuenta, 3, 1)
        form.addWidget(self.combo_usuario, 3, 2)
        panel_layout.addLayout(form)

        #--- Foto del personal ---
        fila_foto= QHBoxLayout()
        self.lbl_foto= QLabel("Sin\nfoto")
        self.lbl_foto.setFixedSize(70, 70)
        self.lbl_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_foto.setObjectName("AvatarFoto")
        self.lbl_foto.setCursor(Qt.CursorShape.PointingHandCursor)
        #Un solo clic manda directo al selector de imagen (igual que el botón "Elegir y Recortar Foto"). Para ver la
        #foto en grande está el botón "Ver Ampliada" — no se usa doble clic aquí porque el diálogo de selección, al ser
        #modal, se comería el segundo clic.
        self.lbl_foto.setToolTip("Clic para elegir foto")
        self.lbl_foto.mousePressEvent= lambda evento: self._elegir_foto()
        fila_foto.addWidget(self.lbl_foto)

        btn_foto= BotonAnimado("Elegir y Recortar Foto")
        btn_foto.setIcon(icono_emoji(EMOJI_FOTO_RECORTAR))
        btn_foto.setIconSize(_QSize_emoji(16, 16))
        btn_foto.clicked.connect(self._elegir_foto)
        fila_foto.addWidget(btn_foto)

        btn_ver_foto= BotonAnimado("Ver Ampliada")
        btn_ver_foto.setObjectName("BtnAccionNeutro")
        btn_ver_foto.clicked.connect(self._ver_foto_ampliada)
        fila_foto.addWidget(btn_ver_foto)

        btn_quitar_foto= BotonAnimado("Quitar Foto")
        btn_quitar_foto.setObjectName("BtnAccionNeutro")
        btn_quitar_foto.clicked.connect(self._quitar_foto)
        fila_foto.addWidget(btn_quitar_foto)
        fila_foto.addStretch()

        btn_guardar= BotonAnimado("Guardar")
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar)
        fila_foto.addWidget(btn_guardar)

        btn_limpiar= BotonAnimado("Limpiar")
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar)
        fila_foto.addWidget(btn_limpiar)
        panel_layout.addLayout(fila_foto)

        disposicion.addWidget(self.panel_edicion)

        #--- Búsqueda (mismo diseño que horario.py: no distingue mayúsculas ni acentos) ---
        self.frame_filtros= QFrame()
        self.frame_filtros.setObjectName("TarjetaFiltros")
        fila_busqueda= QHBoxLayout(self.frame_filtros)
        fila_busqueda.setContentsMargins(14, 10, 14, 10)
        fila_busqueda.setSpacing(10)

        self.marco_busqueda= QFrame()
        self.marco_busqueda.setStyleSheet("QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda= QHBoxLayout(self.marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda)
        self.in_buscar= QLineEdit()
        limitar_campo_texto(self.in_buscar, 150)
        self.in_buscar.setPlaceholderText("Buscar por nombre, cargo o departamento…")
        self.in_buscar.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_buscar, 1)
        fila_busqueda.addWidget(self.marco_busqueda, 1)

        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._filtro_cambio)
        self.in_buscar.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        #Filtros de Cargo y Estado: viven en la ventanita de "☰ Filtros" (ver _construir_dialogo_filtros), no apilados
        #en esta fila de búsqueda -mismo patrón que profesores.py/banco_tareas.py.
        self.combo_filtro_cargo= QComboBox()
        self.combo_filtro_cargo.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_cargo, "Filtrar por el cargo de la persona")

        self.combo_filtro_estado= QComboBox()
        self.combo_filtro_estado.addItem("Todos los estados", None)
        for estado in ESTADOS:
            self.combo_filtro_estado.addItem(estado, estado)
        self.combo_filtro_estado.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_estado, "Filtrar por el estado laboral de la persona")

        self.btn_filtros= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros)
        self.btn_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros.setObjectName("BtnAccionNeutro")
        self.btn_filtros.setToolTip("Abrir panel de filtros (cargo y estado)")
        self.btn_filtros.clicked.connect(self._abrir_dialogo_filtros)
        fila_busqueda.addWidget(self.btn_filtros)
        disposicion.addWidget(self.frame_filtros)
        self._construir_dialogo_filtros()

        #--- Tabla ---
        self.frame_tabla= QFrame()
        self.frame_tabla.setObjectName("TarjetaTabla")
        tabla_card_layout= QVBoxLayout(self.frame_tabla)
        tabla_card_layout.setContentsMargins(18, 16, 18, 14)
        tabla_card_layout.setSpacing(10)

        self.lbl_vacio= QLabel("No se encontraron registros con los filtros actuales.")
        self.lbl_vacio.setObjectName("AvisoVacio")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setVisible(False)
        tabla_card_layout.addWidget(self.lbl_vacio)


        self.tabla= QTableWidget(0, 9)
        aplicar_estructura_tabla(self.tabla)

        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Foto", "Nombre", "Apellidos", "Cargo", "Departamento", "Correo", "Teléfono", "Estado"])
        self.tabla.setColumnHidden(0, True)
        configurar_columna_foto(self.tabla, 1)
        header= self.tabla.horizontalHeader()
        #Mismo criterio que estudiantes.py: todas las columnas en Interactive (sin ninguna en Stretch) y
        #setStretchLastSection en False, para que el usuario pueda redimensionar cualquier columna a mano y sea la
        #tabla la que saque su propia barra de scroll horizontal cuando la suma de anchos no quepa, en vez de que una
        #columna Stretch (antes "Nombre" y, por setStretchLastSection(True), también "Estado") bloquee el arrastre y
        #absorba el espacio sobrante.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(90)
        self._anchos_base_columnas= {
            1: 56, 2: 150, 3: 150, 4: 140, 5: 170, 6: 170, 7: 120, 8: 100,
        }
        for col, ancho in self._anchos_base_columnas.items():
            self.tabla.setColumnWidth(col, ancho)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.setMinimumHeight(380)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla.verticalHeader().setVisible(False)
        tabla_card_layout.addWidget(self.tabla, 1)

        self.paginacion= ControlPaginacion()
        self.paginacion.cambio.connect(self._cargar_tabla)
        tabla_card_layout.addWidget(self.paginacion)

        agregar_boton_pantalla_completa(
            None, [self.tabla, self.paginacion],
            titulo= "Personal", parent=self)

        fila_acciones= QHBoxLayout()
        btn_editar= BotonAnimado("Cargar Seleccionado")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_seleccionado)
        fila_acciones.addWidget(btn_editar)

        btn_eliminar= BotonAnimado("Eliminar")
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar)
        fila_acciones.addWidget(btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla, self, titulo="Detalle del Personal Administrativo")
        self.tabla.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_acciones.addStretch()
        tabla_card_layout.addLayout(fila_acciones)

        disposicion.addWidget(self.frame_tabla, 1)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        self.actualizar_tema()

    #FOTO — mismo flujo/patrón que profesores.py: elegir y recortar, ver ampliada, quitar. Solo cambia el prefijo
    #del archivo guardado.
    def _elegir_foto(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "fotos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="pers")
        if not destino:
            return
        self.foto_path= destino
        self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(destino), 64))

    def _ver_foto_ampliada(self):

        if not self.foto_path or not os.path.exists(self.foto_path):
            mostrar_mensaje("advertencia", "Sin foto", "Esta persona no tiene una fotografía cargada.", self)
            return
        VisorFotoDialog(self.foto_path, self, titulo="Fotografía del Personal Administrativo").exec()

    def _quitar_foto(self):

        if not self.foto_path:
            mostrar_mensaje("advertencia", "Sin foto", "Esta persona no tiene una fotografía cargada.", self)
            return
        if mostrar_mensaje("pregunta", "Confirmar", "¿Quitar la fotografía de esta persona?", self) != QMessageBox.StandardButton.Yes:
            return
        self.foto_path= ""
        self.lbl_foto.setText("Sin\nfoto")
        self.lbl_foto.setPixmap(QPixmap())

    def _cargar_combo_usuarios(self):

        self.combo_usuario.clear()
        self.combo_usuario.addItem("Sin cuenta vinculada", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT usuarios.id, usuarios.username, usuarios.nombre_completo FROM usuarios
                     WHERE usuarios.rol IN ('Administrador', 'Director', 'Coordinador', 'Administrativo')
                     AND usuarios.id NOT IN (
                         SELECT usuario_id FROM personal_administrativo WHERE usuario_id IS NOT NULL
                         AND (?='' OR id != ?)
                     ) ORDER BY usuarios.username""", (self.id_edicion or "", self.id_edicion or -1))
        for fila in c.fetchall():
            etiqueta= fila["nombre_completo"] or fila["username"]
            self.combo_usuario.addItem(f"{etiqueta} ({fila['username']})", fila["id"])
        conn.close()

    def _guardar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para editar personal administrativo.", self)
            return
        if not self.in_nombre.text().strip():
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        usuario_id= self.combo_usuario.currentData()
        datos= (self.in_nombre.text().strip(), self.in_apellidos.text().strip(),
                 self.combo_cargo.currentText().strip(), self.in_departamento.text().strip(),
                 self.in_correo.text().strip(), self.in_telefono.text().strip(),
                 self.in_direccion.text().strip(), self.date_ingreso.date().toString("yyyy-MM-dd"),
                 self.combo_estado.currentText(), self.foto_path, usuario_id)
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            if self.id_edicion is None:
                c.execute("""INSERT INTO personal_administrativo (nombre, apellidos, cargo, departamento,
                             correo, telefono, direccion, fecha_ingreso, estado, foto, usuario_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?)""", datos)
                accion= "Registró personal administrativo"
            else:
                c.execute("""UPDATE personal_administrativo SET nombre=?, apellidos=?, cargo=?, departamento=?,
                             correo= ?, telefono=?, direccion=?, fecha_ingreso=?, estado=?, foto=?, usuario_id=?
                             WHERE id=?""", datos + (self.id_edicion,))
                accion= "Editó personal administrativo"
            conn.commit()
            conn.close()
        except Exception as error:
            self._destello("#EF4444")
            mostrar_mensaje("error", "Error", f"No se pudo guardar el registro:\n{error}", self)
            return
        registrar_auditoria("Personal", accion, self.main_window.usuario_actual, self.in_nombre.text().strip())
        self._destello("#22C55E")
        mostrar_mensaje("exito", "Guardado", "El registro se guardó correctamente.", self)
        self._limpiar()
        self._cargar_tabla()

    def _limpiar(self):

        self.id_edicion= None
        self.foto_path= ""
        self.lbl_foto.setText("Sin\nfoto")
        self.lbl_foto.setPixmap(QPixmap())
        for campo in (self.in_nombre, self.in_apellidos, self.in_departamento,
                      self.in_correo, self.in_telefono, self.in_direccion):
            campo.clear()
        self.combo_cargo.setCurrentIndex(0)
        self.date_ingreso.setDate(QDate.currentDate())
        self.combo_estado.setCurrentIndex(0)
        self._cargar_combo_usuarios()
        desactivar_modo_edicion(self.in_nombre)

    def _cargar_seleccionado(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", self)
            return
        id_p= int(self.tabla.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM personal_administrativo WHERE id=?", (id_p,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion= f["id"]
        self.in_nombre.setText(f["nombre"] or "")
        self.in_apellidos.setText(f["apellidos"] or "")
        self.combo_cargo.setCurrentText(f["cargo"] or "")
        self.in_departamento.setText(f["departamento"] or "")
        self.in_correo.setText(f["correo"] or "")
        self.in_telefono.setText(f["telefono"] or "")
        self.in_direccion.setText(f["direccion"] or "")
        if f["fecha_ingreso"]:
            self.date_ingreso.setDate(QDate.fromString(f["fecha_ingreso"], "yyyy-MM-dd"))
        self.combo_estado.setCurrentText(f["estado"] or "Activo")
        self.foto_path= (f["foto"] if "foto" in f.keys() else None) or ""
        if self.foto_path and os.path.exists(self.foto_path):
            self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(self.foto_path), 64))
        else:
            self.lbl_foto.setText("Sin\nfoto")
            self.lbl_foto.setPixmap(QPixmap())
        self._cargar_combo_usuarios()
        idx= self.combo_usuario.findData(f["usuario_id"])
        self.combo_usuario.setCurrentIndex(idx if idx >= 0 else 0)
        activar_modo_edicion(self.in_nombre,
                             f"Editando personal: {f['nombre'] or ''} {f['apellidos'] or ''}".strip())

    def _eliminar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para eliminar registros.", self)
            return
        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", self)
            return
        id_p= int(self.tabla.item(fila, 0).text())
        nombre= self.tabla.item(fila, 2).text()
        if mostrar_mensaje("pregunta", "Confirmar", f"¿Eliminar a '{nombre}'?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM personal_administrativo WHERE id=?", (id_p,))
        conn.commit()
        conn.close()
        registrar_auditoria("Personal", "Eliminó personal administrativo", self.main_window.usuario_actual, nombre)
        self._cargar_tabla()

    def _filtro_cambio(self, texto=""):

        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _cargar_tabla(self):

        texto= _normalizar(self.in_buscar.text().strip())
        filtro_cargo= self.combo_filtro_cargo.currentData()
        filtro_estado= self.combo_filtro_estado.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM personal_administrativo ORDER BY apellidos, nombre")
        filas= c.fetchall()
        conn.close()
        filtradas= filas
        if texto:
            filtradas= [filtrada for filtrada in filtradas
                        if texto in _normalizar(f"{filtrada['nombre']} {filtrada['apellidos']} {filtrada['cargo'] or ''} {filtrada['departamento'] or ''}")]
        if filtro_cargo is not None:
            filtradas= [filtrada for filtrada in filtradas if (filtrada["cargo"] or "") == filtro_cargo]
        if filtro_estado is not None:
            filtradas= [filtrada for filtrada in filtradas if (filtrada["estado"] or "Activo") == filtro_estado]
        self.paginacion.establecer_total(len(filtradas))
        inicio, fin= self.paginacion.rango_actual()
        pagina= filtradas[inicio:fin]
        self.lbl_vacio.setVisible(len(filtradas) == 0)
        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                item_foto= QTableWidgetItem()
                item_foto.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                foto_path= (f["foto"] if "foto" in f.keys() else None) or ""
                pixmap= obtener_pixmap_circular_cacheado(foto_path, TAMANO_FOTO_TABLA)
                if pixmap is not None:
                    item_foto.setData(Qt.ItemDataRole.DecorationRole, pixmap)
                    #Guarda la ruta real para que "Ver Detalle" pueda mostrar la foto en grande arriba de los demás datos.
                    item_foto.setData(ROL_RUTA_FOTO, foto_path)
                else:
                    item_foto.setData(Qt.ItemDataRole.DecorationRole,
                                       pixmap_placeholder_foto_tabla(TAMANO_FOTO_TABLA))
                self.tabla.setItem(i, 1, item_foto)
                self.tabla.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                self.tabla.setItem(i, 3, QTableWidgetItem(f["apellidos"] or ""))
                self.tabla.setItem(i, 4, QTableWidgetItem(f["cargo"] or ""))
                self.tabla.setItem(i, 5, QTableWidgetItem(f["departamento"] or ""))
                self.tabla.setItem(i, 6, QTableWidgetItem(f["correo"] or ""))
                self.tabla.setItem(i, 7, QTableWidgetItem(f["telefono"] or ""))
                item_estado= QTableWidgetItem(f["estado"] or "")
                if (f["estado"] or "") == "Activo":
                    item_estado.setForeground(QColor("#16A34A"))
                else:
                    item_estado.setForeground(QColor("#DC2626"))
                self.tabla.setItem(i, 8, item_estado)
            self.tabla.resizeRowsToContents()
            ajustar_anchos_columnas(self.tabla)
        self._animar_contador(len(filtradas))
        self._animar_fundido_tabla()
        self._actualizar_panorama(filas)

    #Recalcula el anillo Activo/Inactivo, las barras de cargos y la pila
    #de avatares recientes a partir del listado COMPLETO (sin filtro de
    #búsqueda), para que el panorama siempre refleje toda la planta.
    def _actualizar_panorama(self, filas, animar=True):

        activos= sum(1 for fila in filas if (fila["estado"] or "Activo") == "Activo")
        inactivos= len(filas) - activos
        self.anillo_estado.establecer_datos(activos, inactivos, animar=animar)
        self.lbl_leyenda_activos.setText(f"● Activos: {activos}")
        self.lbl_leyenda_inactivos.setText(f"● Inactivos: {inactivos}")

        conteo_cargos= {}
        for fila in filas:
            cargo= (fila["cargo"] or "").strip()
            if not cargo:
                continue
            conteo_cargos[cargo]= conteo_cargos.get(cargo, 0) + 1
        top_cargos= sorted(conteo_cargos.items(), key=lambda kv: kv[1], reverse=True)[:5]
        self.barras_cargos.establecer_datos(top_cargos, animar=animar)

        con_foto= [fila for fila in filas
                    if (fila["foto"] if "foto" in fila.keys() else None) and os.path.exists(fila["foto"])]
        con_foto= sorted(con_foto, key=lambda f: f["id"], reverse=True)[:5]
        pixmaps= [p for p in (obtener_pixmap_circular_cacheado(f["foto"], 32) for f in con_foto) if p is not None]
        if pixmaps:
            restantes= max(0, len(filas) - len(pixmaps))
            self.pila_avatares.establecer_avatares(pixmaps, restantes)
            self.pila_avatares.setVisible(True)
        else:
            self.pila_avatares.setVisible(False)

    def refrescar(self):

        self._cargar_combo_usuarios()
        self._cargar_combo_filtro_cargo()
        self._cargar_tabla()

    #Puebla el filtro de Cargo con los cargos que YA tiene asignados
    #el personal cargado (no la lista sugerida del formulario), para que
    #el filtro siempre refleje datos reales.
    def _cargar_combo_filtro_cargo(self):

        seleccion_previa= self.combo_filtro_cargo.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT cargo FROM personal_administrativo
                     WHERE cargo IS NOT NULL AND TRIM(cargo) != '' ORDER BY cargo""")
        cargos= [fila["cargo"] for fila in c.fetchall()]
        conn.close()
        self.combo_filtro_cargo.blockSignals(True)
        self.combo_filtro_cargo.clear()
        self.combo_filtro_cargo.addItem("Todos los cargos", None)
        for cargo in cargos:
            self.combo_filtro_cargo.addItem(cargo, cargo)
        idx= self.combo_filtro_cargo.findData(seleccion_previa)
        self.combo_filtro_cargo.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filtro_cargo.blockSignals(False)

    #Ventanita (no modal) con los filtros del listado de Personal:
    #Cargo y Estado, ambos opcionales -mismo patrón que
    #profesores.py/banco_tareas.py.
    def _construir_dialogo_filtros(self):

        self.dialogo_filtros= QDialog(self)
        self.dialogo_filtros.setObjectName("DialogoFiltros")
        self.dialogo_filtros.setWindowTitle("Filtros de Personal")
        aplicar_icono_ventana(self.dialogo_filtros, ICONO_FILTRO)
        self.dialogo_filtros.setModal(False)
        self.dialogo_filtros.setMinimumWidth(320)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)
        lay_dialogo.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

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

        lbl_subtitulo= QLabel("Ambos son opcionales: combínalos con la búsqueda de arriba, "
                            "la lista se actualiza al instante.")
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
        grid.addWidget(QLabel("Cargo:"), 0, 0)
        grid.addWidget(self.combo_filtro_cargo, 0, 1)
        grid.addWidget(QLabel("Estado:"), 1, 0)
        grid.addWidget(self.combo_filtro_estado, 1, 1)
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        btn_limpiar= QPushButton("Limpiar filtros")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_filtros)
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros.hide)
        fila_botones.addWidget(btn_cerrar)
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

        for combo in (self.combo_filtro_cargo, self.combo_filtro_estado):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.paginacion.reiniciar()
        self._cargar_tabla()

    #Sincroniza los colores de las tarjetas, el anillo y las barras de
    #este módulo con el tema/modo claro-oscuro actual de la app. Se llama al
    #construir la pantalla y cada vez que el usuario cambia de tema (ver
    #main.py).
    def actualizar_tema(self):

        colores= _colores_tema(self.main_window)
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
        self.frame_panorama.setStyleSheet(f"""
            QFrame#TarjetaPanorama {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 16px;
            }}
            QLabel#TituloTarjetaInterna {{
                font-size: 14px;
                font-weight: 800;
                color: {colores['accent']};
                background: transparent;
            }}
        """)
        self.separador_panorama.setStyleSheet(f"background-color: {colores['bg_btn']}; max-width: 1px;")
        self.lbl_leyenda_activos.setStyleSheet(
            "color: #16A34A; font-weight: 700; font-size: 12px; background: transparent;")
        self.lbl_leyenda_inactivos.setStyleSheet(
            "color: #DC2626; font-weight: 700; font-size: 12px; background: transparent;")
        self.anillo_estado.establecer_colores_tema(colores["bg_btn"], colores["txt_prim"])
        self.barras_cargos.establecer_colores_tema(
            colores["accent"], colores["txt_prim"], colores["txt_sec"], colores["bg_btn"])
        self.panel_edicion.setStyleSheet(f"""
            QFrame#TarjetaFormulario {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 16px;
            }}
            QLabel#TituloTarjetaInterna {{
                font-size: 14px;
                font-weight: 800;
                color: {colores['accent']};
                background: transparent;
            }}
        """)
        self.frame_filtros.setStyleSheet(f"""
            QFrame#TarjetaFiltros {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 14px;
            }}
        """)
        self.icono_busqueda.establecer_color(colores["txt_sec"])
        if hasattr(self, "dialogo_filtros"):
            self.dialogo_filtros.setStyleSheet(f"""
                QDialog#DialogoFiltros {{
                    background-color: {colores['bg_panel']};
                }}
                /* Repite aquí el mismo QToolTip que usa la ventana
                   principal: este diálogo es una ventana de nivel
                   superior aparte, y su propio setStyleSheet() reemplaza
                   -para todo lo que esté dentro- cualquier regla heredada,
                   incluido el QToolTip global. Sin esto, los tooltips de
                   los combos aquí adentro caían al estilo nativo de Qt
                   (gris claro/texto negro), inconsistente con el resto
                   de AcaDeXI. */
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
        self.frame_tabla.setStyleSheet(f"""
            QFrame#TarjetaTabla {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 14px;
            }}
            QLabel#AvisoVacio {{
                color: {colores['txt_sec']};
                font-size: 13px;
                font-weight: 600;
                padding: 18px;
                background: transparent;
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
        self.lbl_foto.setStyleSheet(f"""
            QLabel#AvatarFoto {{
                border: 3px solid {colores['accent']};
                border-radius: 35px;
                background-color: {colores['bg_btn']};
                color: {colores['txt_sec']};
                font-size: 10px;
                font-weight: 600;
            }}
        """)

    #ANIMACIONES — capa puramente visual: no participan en la lógica de negocio, permisos, validación ni guardado
    #de datos.
    #Actualiza el chip '🗂 N personas' de la cabecera con una pequeña
    #animación de conteo, en vez de un cambio brusco de texto.
    def _animar_contador(self, valor_final):

        def texto(v):

            return f"{html_icono_emoji('🗂', 15)} {v} persona" + ("s" if v != 1 else "")

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
        anim.valueChanged.connect(lambda v: self.chip_contador.setText(texto(int(v))))
        anim.start()
        self._anim_contador= anim  #referencia viva mientras corre la animación

    #Fundido breve al recargar la tabla, como confirmación visual de que
    #los datos se actualizaron. El efecto se retira apenas termina para no
    #afectar el rendimiento del scroll normal de la tabla el resto del
    #tiempo.
    def _animar_fundido_tabla(self):

        efecto= QGraphicsOpacityEffect(self.tabla)
        self.tabla.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self.tabla.setGraphicsEffect(None))
        anim.start()
        self._anim_tabla= anim  #referencia viva mientras corre la animación

    #Resplandor breve de color en el borde de la tarjeta del formulario,
    #a modo de confirmación visual (verde=éxito, rojo=aviso). Solo anima la
    #sombra ya existente de la tarjeta: no toca ningún dato ni campo.
    def _destello(self, color_hex="#22C55E"):

        if not hasattr(self, "_sombra_formulario"):
            return
        grupo= QParallelAnimationGroup(self)
        anim_color= QPropertyAnimation(self._sombra_formulario, b"color", self)
        anim_color.setKeyValueAt(0.0, self._color_sombra_normal)
        anim_color.setKeyValueAt(0.5, QColor(color_hex))
        anim_color.setKeyValueAt(1.0, self._color_sombra_normal)
        anim_color.setDuration(650)
        anim_blur= QPropertyAnimation(self._sombra_formulario, b"blurRadius", self)
        anim_blur.setKeyValueAt(0.0, 22)
        anim_blur.setKeyValueAt(0.5, 40)
        anim_blur.setKeyValueAt(1.0, 22)
        anim_blur.setDuration(650)
        grupo.addAnimation(anim_color)
        grupo.addAnimation(anim_blur)
        grupo.start()
        self._anim_destello= grupo  #referencia viva mientras corre la animación
