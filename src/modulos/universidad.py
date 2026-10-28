from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGridLayout, QSpinBox, QCheckBox, QScrollArea, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QSize, QPropertyAnimation,
    QEasingCurve, QVariantAnimation, QParallelAnimationGroup)
from PySide6.QtGui import (QPainter, QPainterPath, QColor, QPen, QBrush, QFont,
    QFontMetrics, QPixmap, QIcon)
from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, agregar_boton_pantalla_completa)
from src.interfaz.configuracion import IconoLupa, _normalizar, _fundido_entrada, TabWidgetNavegable, conectar_tooltip_seleccion
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, quitar_emojis_texto,
                           EMOJI_TAB_FACULTADES, EMOJI_TAB_CARRERAS, EMOJI_TAB_PENSUM,
                           html_icono_emoji)
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion

#Paleta cíclica usada SOLO por las visualizaciones propias de este módulo (anillo, barra segmentada, malla
#curricular) para diferenciar series de datos. Es independiente del tema de color que el usuario elija en
#Configuración.
PALETA_SERIES= ["#6366F1", "#F97316", "#14B8A6", "#EC4899", "#8B5CF6",
                  "#0EA5E9", "#F59E0B", "#22C55E", "#EF4444", "#D946EF"]


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica.
def _hex_a_rgba(color_hex, alpha):

    color_hex= (color_hex or "#2563EB").lstrip("#")
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _color_serie(indice):

    return PALETA_SERIES[indice % len(PALETA_SERIES)]


_CACHE_PUNTOS= {}


#Pequeño círculo sólido dibujado con QPainter (mismo color que la
#porción de esa facultad en el anillo/leyenda), usado como icono en la
#columna de color de la tabla de Facultades. Cacheado por (color, size)
#-es un dibujo fijo, no hace falta rehacerlo en cada fila/recarga.
def _pixmap_punto(color_hex, size=12):

    clave= (color_hex, size)
    if clave in _CACHE_PUNTOS:
        return _CACHE_PUNTOS[clave]
    pm= QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter= QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(color_hex)))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    _CACHE_PUNTOS[clave]= pm
    return pm


#Lee la paleta/tema activo de la ventana principal para que los elementos
#visuales de este módulo respeten el tema y el modo claro/oscuro elegido.
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


#QPushButton normal (misma señal `clicked`, mismo objectName, mismo estilo
#por QSS/tema) que además 'respira' con una sombra suave al pasar el mouse por
#encima. Solo anima mientras el cursor está sobre el botón, así que no cuesta
#rendimiento en reposo.
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

    def enterEvent(self, event):

        if self.isEnabled():
            self._animar_sombra(16)
        super().enterEvent(event)

    def leaveEvent(self, event):

        self._animar_sombra(0)
        super().leaveEvent(event)


#Anillo (donut) animado que reemplaza a la típica 'tarjeta KPI': muestra
#cuántas carreras tiene cada facultad como proporciones de un círculo,
#dibujado a mano con QPainter y que se 'abre' con una animación al cargar.
class AnilloFacultades(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._segmentos= []
        self._total= 0
        self._progreso= 0.0
        self._color_texto= "#0F172A"
        self._color_sub= "#64748B"
        self._color_pista= "#E2E8F0"
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(750)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):

        self._progreso= float(v)
        self.update()

    def poner_colores(self, texto, sub, pista):

        self._color_texto= texto
        self._color_sub= sub
        self._color_pista= pista
        self.update()

    def establecer_datos(self, segmentos):

        self._segmentos= [segmento for segmento in segmentos if segmento["valor"] > 0]
        self._total= sum(segmento["valor"] for segmento in self._segmentos)
        self._anim.stop()
        self._progreso= 0.0
        self._anim.start()

    def sizeHint(self):

        return QSize(170, 170)

    def paintEvent(self, event):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado= min(self.width(), self.height()) - 16
        if lado <= 0:
            return
        pos_x= (self.width() - lado) / 2
        pos_y= (self.height() - lado) / 2
        grosor= max(12, int(lado * 0.16))
        rect= QRectF(pos_x + grosor / 2, pos_y + grosor / 2, lado - grosor, lado - grosor)

        pen_pista= QPen(QColor(self._color_pista))
        pen_pista.setWidth(grosor)
        pen_pista.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_pista)
        painter.drawArc(rect, 0, 360 * 16)

        if self._total > 0:
            angulo_actual= 90.0  #grados; convención Qt: positivo = antihorario
            hueco= 3.0
            for seg in self._segmentos:
                proporcion= seg["valor"] / self._total
                span_total= proporcion * 360.0
                span_visible= max(0.0, span_total - hueco) * self._progreso
                pen= QPen(QColor(seg["color"]))
                pen.setWidth(grosor)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawArc(rect, int(angulo_actual * 16), int(-span_visible * 16))
                angulo_actual -= span_total

        total_mostrado= int(round(self._total * self._progreso))
        painter.setPen(QColor(self._color_texto))
        fuente= QFont()
        fuente.setPointSize(max(13, int(lado * 0.13)))
        fuente.setBold(True)
        painter.setFont(fuente)
        rect_num= QRectF(pos_x, pos_y + lado * 0.30, lado, lado * 0.32)
        painter.drawText(rect_num, Qt.AlignmentFlag.AlignCenter, str(total_mostrado))

        painter.setPen(QColor(self._color_sub))
        fuente_sub= QFont()
        fuente_sub.setPointSize(max(8, int(lado * 0.07)))
        painter.setFont(fuente_sub)
        rect_sub= QRectF(pos_x, pos_y + lado * 0.56, lado, lado * 0.18)
        painter.drawText(rect_sub, Qt.AlignmentFlag.AlignCenter, "carreras")


#Barra tipo cápsula que reparte su ancho proporcionalmente entre categorías
#(aquí, tipos de asignación docente). Crece con una animación suave al cargar
#en vez de aparecer de golpe, como una tarjeta estática.
class BarraSegmentada(QWidget):

    ALTURA= 30

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedHeight(self.ALTURA)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._segmentos= []
        self._progreso= 0.0
        self._color_pista= "#E2E8F0"
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):

        self._progreso= float(v)
        self.update()

    def poner_color_pista(self, color):

        self._color_pista= color
        self.update()

    def establecer_datos(self, segmentos):

        self._segmentos= [segmento for segmento in segmentos if segmento["valor"] > 0]
        self._anim.stop()
        self._progreso= 0.0
        self._anim.start()

    def paintEvent(self, event):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radio= self.ALTURA / 2
        ruta_fondo= QPainterPath()
        ruta_fondo.addRoundedRect(QRectF(0, 0, self.width(), self.height()), radio, radio)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self._color_pista)))
        painter.drawPath(ruta_fondo)

        total= sum(segmento["valor"] for segmento in self._segmentos)
        if total <= 0:
            return
        painter.setClipPath(ruta_fondo)
        x= 0.0
        ancho_total= self.width() * self._progreso
        for seg in self._segmentos:
            ancho= (seg["valor"] / total) * ancho_total
            painter.setBrush(QBrush(QColor(seg["color"])))
            painter.drawRect(QRectF(x, 0, ancho + 1, self.height()))
            x += ancho


#Mapa curricular dibujado a mano: cada semestre es una columna y cada
#materia una ficha; las curvas conectan cada materia con su prerrequisito.
#Pasar el mouse sobre una ficha resalta su cadena de prerrequisito/dependientes.
class MallaCurricular(QWidget):

    ANCHO_COLUMNA= 196
    ALTO_FICHA= 52
    ESPACIO_V= 14
    MARGEN= 18

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setMouseTracking(True)
        self._nodos= {}
        self._por_semestre= {}
        self._dependientes= {}
        self._color_chip= "#EEF2FF"
        self._color_chip_borde= "#6366F1"
        self._color_electiva= "#FDF4FF"
        self._color_electiva_borde= "#D946EF"
        self._color_texto= "#1E1B4B"
        self._color_conector= "#94A3B8"
        self._color_acento= "#6366F1"
        self._hover_id= None
        self.setMinimumHeight(self.ALTO_FICHA + self.MARGEN * 2 + 34)

    def sizeHint(self):

        return self.minimumSize()

    def poner_colores(self, chip, chip_borde, texto, conector, acento,
                     electiva= None, electiva_borde=None):

        self._color_chip= chip
        self._color_chip_borde= chip_borde
        self._color_texto= texto
        self._color_conector= conector
        self._color_acento= acento
        #Antes estos dos quedaban fijos en "#FDF4FF"/"#D946EF" (colores pensados para modo claro) sin importar el tema,
        #así que en modo oscuro las materias electivas quedaban con fondo casi blanco y texto claro encima:
        #prácticamente ilegibles. Ahora, si el llamador no manda un color de electiva explícito, se deriva del acento
        #para que respete el tema/modo activo igual que el resto de la ficha.
        self._color_electiva= electiva or chip
        self._color_electiva_borde= electiva_borde or acento
        self.update()

    #filas: lista de dicts con materia_id, materia_nombre, semestre,
    #prerrequisito_id, electiva (ya filtrados por una sola carrera).
    def establecer_datos(self, filas):

        self._nodos= {}
        self._por_semestre= {}
        for fila in filas:
            mid= fila.get("materia_id")
            if mid is None or mid in self._nodos:
                continue
            sem= max(1, int(fila.get("semestre") or 1))
            self._nodos[mid]= {
                "nombre": fila.get("materia_nombre") or "—",
                "semestre": sem,
                "prereq_id": fila.get("prerrequisito_id"),
                "electiva": bool(fila.get("electiva")),
                "rect": None,
            }
            self._por_semestre.setdefault(sem, []).append(mid)

        self._dependientes= {}
        for mid, nodo in self._nodos.items():
            pid= nodo["prereq_id"]
            if pid in self._nodos:
                self._dependientes.setdefault(pid, []).append(mid)

        self._hover_id= None
        self.setToolTip("")
        self._recalcular_geometria()
        self.update()

    def _recalcular_geometria(self):

        if not self._por_semestre:
            self.setMinimumSize(0, self.ALTO_FICHA + self.MARGEN * 2 + 34)
            self.updateGeometry()
            return
        semestres= sorted(self._por_semestre.keys())
        max_filas= max(len(v) for v in self._por_semestre.values())
        ancho= self.MARGEN * 2 + len(semestres) * self.ANCHO_COLUMNA
        alto= self.MARGEN * 2 + 34 + max_filas * (self.ALTO_FICHA + self.ESPACIO_V)
        self.setMinimumSize(int(ancho), int(alto))
        for idx_col, sem in enumerate(semestres):
            pos_x= self.MARGEN + idx_col * self.ANCHO_COLUMNA + 8
            for fila, mid in enumerate(self._por_semestre[sem]):
                pos_y= self.MARGEN + 34 + fila * (self.ALTO_FICHA + self.ESPACIO_V)
                self._nodos[mid]["rect"]= QRectF(pos_x, pos_y, self.ANCHO_COLUMNA - 24, self.ALTO_FICHA)
        self.updateGeometry()

    def mouseMoveEvent(self, event):

        punto= event.position()
        nuevo_hover= None
        for mid, nodo in self._nodos.items():
            r= nodo["rect"]
            if r is not None and r.contains(punto):
                nuevo_hover= mid
                break
        if nuevo_hover != self._hover_id:
            self._hover_id= nuevo_hover
            if nuevo_hover is not None:
                nodo= self._nodos[nuevo_hover]
                extra= " · electiva" if nodo["electiva"] else ""
                self.setToolTip(f"{nodo['nombre']}{extra} · Semestre {nodo['semestre']}")
            self.update()

    def leaveEvent(self, event):

        if self._hover_id is not None:
            self._hover_id= None
            self.update()
        super().leaveEvent(event)

    def _relacionado_con_hover(self, mid):

        if self._hover_id is None:
            return True
        if mid == self._hover_id:
            return True
        nodo= self._nodos.get(self._hover_id)
        if nodo is not None and mid == nodo["prereq_id"]:
            return True
        if mid in self._dependientes.get(self._hover_id, []):
            return True
        return False

    def paintEvent(self, event):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._nodos:
            painter.setPen(QColor(self._color_conector))
            fuente= QFont()
            fuente.setPointSize(11)
            painter.setFont(fuente)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "Esta carrera todavía no tiene materias en el pensum.")
            return

        semestres= sorted(self._por_semestre.keys())
        fuente_header= QFont()
        fuente_header.setPointSize(10)
        fuente_header.setBold(True)
        painter.setFont(fuente_header)
        for idx_col, sem in enumerate(semestres):
            pos_x= self.MARGEN + idx_col * self.ANCHO_COLUMNA
            painter.setPen(QColor(self._color_acento))
            painter.drawText(QRectF(pos_x, 2, self.ANCHO_COLUMNA - 8, 24),
                              Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                              f"Semestre {sem}")

        #--- Conectores de prerrequisitos (se dibujan antes que las fichas) ---
        for mid, nodo in self._nodos.items():
            pid= nodo["prereq_id"]
            if pid not in self._nodos:
                continue
            origen= self._nodos[pid]["rect"]
            destino= nodo["rect"]
            if origen is None or destino is None:
                continue
            resaltado= self._hover_id is not None and (mid == self._hover_id or pid == self._hover_id)
            activo= self._relacionado_con_hover(mid) and self._relacionado_con_hover(pid)
            color= QColor(self._color_acento if resaltado else self._color_conector)
            color.setAlpha(235 if resaltado else (170 if activo else 55))
            pen= QPen(color)
            pen.setWidthF(2.4 if resaltado else 1.6)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            p1= QPointF(origen.right(), origen.center().y())
            p2= QPointF(destino.left(), destino.center().y())
            ruta= QPainterPath()
            ruta.moveTo(p1)
            medio_x= (p1.x() + p2.x()) / 2
            ruta.cubicTo(QPointF(medio_x, p1.y()), QPointF(medio_x, p2.y()), p2)
            painter.drawPath(ruta)

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            flecha= QPainterPath()
            flecha.moveTo(p2)
            flecha.lineTo(p2.x() - 7, p2.y() - 4)
            flecha.lineTo(p2.x() - 7, p2.y() + 4)
            flecha.closeSubpath()
            painter.drawPath(flecha)

        #--- Fichas de materias ---
        fuente_chip= QFont()
        fuente_chip.setPointSize(9)
        fuente_chip.setBold(True)
        metricas= QFontMetrics(fuente_chip)
        for mid, nodo in self._nodos.items():
            r= nodo["rect"]
            if r is None:
                continue
            activo= self._relacionado_con_hover(mid)
            es_hover= mid == self._hover_id
            if nodo["electiva"]:
                color_fondo= QColor(self._color_electiva)
                color_borde= QColor(self._color_electiva_borde)
            else:
                color_fondo= QColor(self._color_chip)
                color_borde= QColor(self._color_chip_borde)
            if not activo:
                color_fondo.setAlpha(70)
                color_borde.setAlpha(90)

            ruta= QPainterPath()
            ruta.addRoundedRect(r, 10, 10)
            painter.setBrush(QBrush(color_fondo))
            pen= QPen(color_borde)
            pen.setWidthF(2.4 if es_hover else 1.4)
            if nodo["electiva"]:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPath(ruta)

            texto= metricas.elidedText(nodo["nombre"], Qt.TextElideMode.ElideRight,
                                         max(10, int(r.width() - 16)))
            color_txt= QColor(self._color_texto)
            if not activo:
                color_txt.setAlpha(110)
            painter.setPen(color_txt)
            painter.setFont(fuente_chip)
            painter.drawText(r.adjusted(8, 0, -8, 0),
                              Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, texto)


#Módulo condicional activado cuando tipo_institucion = 'Universidad'.
class ModuloUniversidad(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion_facultad= None
        self.id_edicion_carrera= None
        self.id_edicion_pensum= None
        self._pestanas_cargadas= set()
        self._colores_facultad= {}
        self._cache_iconos_punto= {}
        self._valor_chip_facultades= 0
        self._valor_chip_carreras= 0
        self._color_sombra_normal= QColor(0, 0, 0, 45)
        self._build_ui()
        #Cargamos los datos en el siguiente ciclo del bucle de eventos: así la pantalla se pinta de inmediato al
        #presionar el módulo en la barra lateral y los datos aparecen un instante después, sin bloquear el clic.
        QTimer.singleShot(0, self.refrescar)
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        #Módulo institucional de Universidad (Facultades, Carreras, Pensum):
        #exclusivo de roles gerenciales.
        self._titulo_modulo_atajos= "Universidad"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar facultad", self._guardar_facultad)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar_facultad)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar facultad seleccionada",
                         self._cargar_facultad_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar facultad", self._eliminar_facultad)
        registrar_atajo(self, self.main_window, "F5", "Actualizar", self._cargar_facultades)

    #Construcción de la interfaz
    def _build_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        layout= QVBoxLayout(contenido)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(16)

        layout.addWidget(self._construir_cabecera())

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        #Ver nota en configuracion.py: quita la línea base nativa que Qt dibuja bajo la barra de pestañas y que el
        #stylesheet no puede eliminar.
        self.tabs.tabBar().setDrawBase(False)
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._tab_facultades(), "Facultades")
        self.tabs.addTab(self._tab_carreras(), "Carreras")
        self.tabs.addTab(self._tab_pensum(), "Malla Curricular")
        self.tabs.setTabIcon(0, icono_emoji(EMOJI_TAB_FACULTADES))
        self.tabs.setTabIcon(1, icono_emoji(EMOJI_TAB_CARRERAS))
        self.tabs.setTabIcon(2, icono_emoji(EMOJI_TAB_PENSUM))

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        #La carga pesada de cada pestaña se difiere hasta que el usuario la visita por primera vez (ver
        #_cambio_pestana), para que entrar al módulo sea instantáneo aunque haya muchos datos.
        self.tabs.currentChanged.connect(self._cambio_pestana)
        #Transición suave (fundido) al cambiar de pestaña, en vez de un salto brusco.
        self.tabs.currentChanged.connect(lambda i: _fundido_entrada(self.tabs.widget(i), 220))
        self.actualizar_tema()

    def _construir_cabecera(self):

        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabeceraUniversidad")
        cab= QHBoxLayout(self.frame_cabecera)
        cab.setContentsMargins(22, 18, 22, 18)
        cab.setSpacing(14)

        self.lbl_icono_cabecera= QLabel()
        self.lbl_icono_cabecera.setObjectName("IconoCabeceraUniversidad")
        self.lbl_icono_cabecera.setFixedSize(46, 46)
        self.lbl_icono_cabecera.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_cabecera, "Universidad")
        cab.addWidget(self.lbl_icono_cabecera)

        bloque= QVBoxLayout()
        bloque.setSpacing(2)
        titulo= QLabel("Módulo Superior · Universidad")
        titulo.setObjectName("TituloCabeceraUniversidad")
        subtitulo= QLabel("Facultades, carreras, mallas curriculares y asignación docente en un solo lugar")
        subtitulo.setObjectName("SubtituloCabeceraUniversidad")
        subtitulo.setWordWrap(True)
        bloque.addWidget(titulo)
        bloque.addWidget(subtitulo)
        cab.addLayout(bloque, 1)

        self.chip_facultades= QLabel("0 facultades")
        self.chip_facultades.setObjectName("ChipResumenUniversidad")
        cab.addWidget(self.chip_facultades, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_carreras= QLabel("0 carreras")
        self.chip_carreras.setObjectName("ChipResumenUniversidad")
        cab.addWidget(self.chip_carreras, 0, Qt.AlignmentFlag.AlignVCenter)

        return self.frame_cabecera

    #Contenedor tipo 'tarjeta de cristal' (fondo + borde + sombra suave)
    #reutilizado por todas las secciones del módulo, en vez del look plano
    #de formularios sueltos sobre la pantalla.
    def _crear_tarjeta(self):

        frame= QFrame()
        frame.setObjectName("PanelUniversidad")
        layout= QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        sombra= QGraphicsDropShadowEffect(frame)
        sombra.setColor(self._color_sombra_normal)
        sombra.setOffset(0, 3)
        sombra.setBlurRadius(20)
        frame.setGraphicsEffect(sombra)
        return frame, layout, sombra

    #Barra de búsqueda con lupa dibujada a mano e insensible a mayúsculas/
    #acentos — mismo diseño y comportamiento que en Configuración, para que
    #todos los módulos del sistema busquen exactamente igual. `callback_filtro`
    #se llama (con un pequeño debounce) cada vez que el texto cambia.
    def _crear_barra_busqueda(self, placeholder, callback_filtro):

        marco= QFrame()
        marco.setStyleSheet("QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay= QHBoxLayout(marco)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(6)
        icono= IconoLupa()
        lay.addWidget(icono)
        campo= QLineEdit()
        limitar_campo_texto(campo, 300)
        campo.setPlaceholderText(placeholder)
        campo.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay.addWidget(campo, 1)

        temporizador= QTimer(self)
        temporizador.setSingleShot(True)
        temporizador.setInterval(150)
        temporizador.timeout.connect(callback_filtro)
        campo.textChanged.connect(lambda _t: temporizador.start())

        self._iconos_busqueda= getattr(self, "_iconos_busqueda", [])
        self._iconos_busqueda.append(icono)
        return marco, campo

    #Validación y robustez — helpers reutilizables por las distintas pestañas para evitar duplicados y para que un
    #error de BD (integridad, bloqueo, etc.) se muestre como aviso en vez de romper la ventana.
    #True si ya existe otra fila de `tabla` con el mismo `nombre` (comparado
    #sin distinguir mayúsculas/acentos, vía _normalizar). `filtro_extra`, si se
    #pasa, es una tupla (condicion_sql, parametros) para acotar la comparación
    #-por ejemplo, a la misma facultad- en vez de compararlo contra toda la tabla.
    def _nombre_duplicado(self, tabla, nombre, id_excluir=None, columna="nombre", filtro_extra=None):

        conn= obtener_conexion()
        c= conn.cursor()
        query= f"SELECT id, {columna} FROM {tabla}"
        parametros= []
        if filtro_extra:
            query += f" WHERE {filtro_extra[0]}"
            parametros.extend(filtro_extra[1])
        c.execute(query, parametros)
        filas= c.fetchall()
        conn.close()
        objetivo= _normalizar(nombre or "")
        for fila in filas:
            if id_excluir is not None and fila["id"] == id_excluir:
                continue
            if _normalizar(fila[columna] or "") == objetivo:
                return True
        return False

    #Ejecuta `funcion` (que recibe conn, cursor y hace su propio INSERT/UPDATE/
    #DELETE) dentro de un try/except: si algo falla (violación de integridad,
    #BD bloqueada, etc.) se muestra un aviso claro en vez de dejar una excepción
    #sin capturar. Devuelve True si se guardó y se hizo commit, False si falló.
    def _operacion_bd_segura(self, funcion, mensaje_error="No se pudo completar la operación"):

        conn= obtener_conexion()
        try:

            c= conn.cursor()
            funcion(conn, c)
            conn.commit()
            return True
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"{mensaje_error}:\n{error}", self)
            return False
        finally:
            conn.close()

    #ANIMACIONES — capa puramente visual: no participan en la lógica de negocio, permisos, validación ni guardado
    #de datos.
    #Resplandor breve de color en el borde de una tarjeta, a modo de
    #confirmación visual (verde=éxito, rojo=aviso) tras guardar o eliminar.
    def _destello(self, sombra, color_hex="#22C55E"):

        if sombra is None:
            return
        grupo= QParallelAnimationGroup(self)
        anim_color= QPropertyAnimation(sombra, b"color", self)
        anim_color.setKeyValueAt(0.0, self._color_sombra_normal)
        anim_color.setKeyValueAt(0.5, QColor(color_hex))
        anim_color.setKeyValueAt(1.0, self._color_sombra_normal)
        anim_color.setDuration(600)
        anim_blur= QPropertyAnimation(sombra, b"blurRadius", self)
        anim_blur.setKeyValueAt(0.0, 20)
        anim_blur.setKeyValueAt(0.5, 38)
        anim_blur.setKeyValueAt(1.0, 20)
        anim_blur.setDuration(600)
        grupo.addAnimation(anim_color)
        grupo.addAnimation(anim_blur)
        grupo.start()
        self._anim_destello= grupo

    #Fundido breve al recargar una tabla, como confirmación visual de que
    #los datos se actualizaron. El efecto se retira apenas termina.
    def _animar_fundido_tabla(self, tabla):

        efecto= QGraphicsOpacityEffect(tabla)
        tabla.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: tabla.setGraphicsEffect(None))
        anim.start()
        self._anim_tabla= anim

    #Aparición suave (fade-in) para paneles que se reconstruyen del todo,
    #como la malla curricular al cambiar de carrera.
    def _animar_entrada(self, widget):

        efecto= QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        self._anim_entrada= anim

    #Anima el conteo mostrado en un chip de la cabecera (cuenta hacia
    #arriba/abajo en vez de saltar directo al número nuevo).
    def _animar_valor_chip(self, chip, atributo, valor_final, formato):

        valor_inicial= getattr(self, atributo, 0)
        setattr(self, atributo, valor_final)
        if valor_inicial == valor_final:
            chip.setText(formato(valor_final))
            return
        anim= QVariantAnimation(self)
        anim.setStartValue(valor_inicial)
        anim.setEndValue(valor_final)
        anim.setDuration(400)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: chip.setText(formato(int(v))))
        anim.start()
        setattr(self, f"_anim_{atributo}", anim)

    #Pequeño círculo de color, cacheado, usado para etiquetar filas de
    #la tabla de carreras según su facultad (evita crear un QPixmap nuevo
    #en cada refresco).
    def _icono_punto(self, color_hex):

        if color_hex in self._cache_iconos_punto:
            return self._cache_iconos_punto[color_hex]
        pix= QPixmap(12, 12)
        pix.fill(Qt.GlobalColor.transparent)
        pintor= QPainter(pix)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(color_hex))
        pintor.drawEllipse(0, 0, 12, 12)
        pintor.end()
        icono= QIcon(pix)
        self._cache_iconos_punto[color_hex]= icono
        return icono

    #Carga perezosa por pestaña
    def _cambio_pestana(self, index):

        if index in self._pestanas_cargadas:
            return
        self._pestanas_cargadas.add(index)
        if index == 0:
            self._cargar_facultades()
        elif index == 1:
            self._cargar_carreras()
        elif index == 2:
            self._cargar_pensum()
            self._reconstruir_malla()

    #---------------- FACULTADES ----------------
    def _tab_facultades(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        tarjeta_dist, layout_dist, _= self._crear_tarjeta()
        titulo_dist= QLabel("Distribución de carreras por facultad")
        titulo_dist.setObjectName("TituloTarjetaUniversidad")
        layout_dist.addWidget(titulo_dist)
        fila_dist= QHBoxLayout()
        fila_dist.setSpacing(22)
        self.anillo_facultades= AnilloFacultades()
        fila_dist.addWidget(self.anillo_facultades, 0, Qt.AlignmentFlag.AlignTop)
        self.contenedor_leyenda_donut= QWidget()
        self.layout_leyenda_donut= QVBoxLayout(self.contenedor_leyenda_donut)
        self.layout_leyenda_donut.setContentsMargins(0, 4, 0, 0)
        self.layout_leyenda_donut.setSpacing(6)
        fila_dist.addWidget(self.contenedor_leyenda_donut, 1, Qt.AlignmentFlag.AlignTop)
        layout_dist.addLayout(fila_dist)
        disposicion.addWidget(tarjeta_dist)

        self.tarjeta_form_facultad, layout_form, self.sombra_form_facultad= self._crear_tarjeta()
        titulo_form= QLabel("Nueva facultad")
        titulo_form.setObjectName("TituloTarjetaUniversidad")
        layout_form.addWidget(titulo_form)
        fila= QHBoxLayout()
        self.f_nombre= QLineEdit()
        self.f_nombre.setPlaceholderText("Nombre de la Facultad")
        limitar_campo_texto(self.f_nombre, 300)
        self.f_nombre.setToolTip("Nombre de la facultad (ej. Facultad de Ingeniería)")
        fila.addWidget(self.f_nombre)
        self.btn_guardar_facultad= BotonAnimado("Agregar Facultad")
        self.btn_guardar_facultad.setObjectName("BtnAccionAgregar")
        self.btn_guardar_facultad.clicked.connect(self._guardar_facultad)
        fila.addWidget(self.btn_guardar_facultad)
        layout_form.addLayout(fila)
        disposicion.addWidget(self.tarjeta_form_facultad)

        tarjeta_tabla, layout_tabla, _= self._crear_tarjeta()
        marco_busqueda_fac, self.in_buscar_facultades= self._crear_barra_busqueda(
            "Buscar facultad por nombre…", self._filtro_facultades_cambio)
        layout_tabla.addWidget(marco_busqueda_fac)
        self.tabla_facultades= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_facultades)

        #Columna 0 (ID) se mantiene -la usan _cargar_facultad_seleccionada/
        #_eliminar_facultad para saber sobre qué fila operar- pero oculta:
        #es un dato interno, no algo que el usuario necesite ver. La columna 1 es un punto de color (mismo color que su
        #porción en el anillo/leyenda de arriba) y la 3 muestra cuántas carreras tiene, para que la tabla no se sienta
        #un simple listado de nombres.
        self.tabla_facultades.setHorizontalHeaderLabels(["ID", "", "Facultad", "Carreras"])
        header= self.tabla_facultades.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self.tabla_facultades.setColumnHidden(0, True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tabla_facultades.setColumnWidth(1, 34)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tabla_facultades.setColumnWidth(3, 90)
        self.tabla_facultades.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_facultades.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_facultades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_facultades.setAlternatingRowColors(True)
        self.tabla_facultades.setWordWrap(True)
        self.tabla_facultades.setMinimumHeight(320)
        self.tabla_facultades.verticalHeader().setVisible(False)
        layout_tabla.addWidget(self.tabla_facultades, 1)
        self.paginacion_facultades= ControlPaginacion()
        self.paginacion_facultades.cambio.connect(self._cargar_facultades)
        layout_tabla.addWidget(self.paginacion_facultades)
        agregar_boton_pantalla_completa(
            None, [self.tabla_facultades, self.paginacion_facultades],
            titulo= "Facultades", parent=self)
        fila_acciones_fac= QHBoxLayout()
        btn_actualizar_fac= BotonAnimado("Actualizar")
        btn_actualizar_fac.setObjectName("BtnAccionNeutro")
        btn_actualizar_fac.clicked.connect(self._cargar_facultades)
        fila_acciones_fac.addWidget(btn_actualizar_fac)
        btn_limpiar_fac= BotonAnimado("Limpiar")
        btn_limpiar_fac.setObjectName("BtnAccionNeutro")
        btn_limpiar_fac.clicked.connect(self._limpiar_facultad)
        fila_acciones_fac.addWidget(btn_limpiar_fac)
        btn_cargar_fac= BotonAnimado("Cargar Seleccionada")
        btn_cargar_fac.setIcon(icono_emoji("✏"))
        btn_cargar_fac.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_fac.setObjectName("BtnAccionEditar")
        btn_cargar_fac.clicked.connect(self._cargar_facultad_seleccionada)
        fila_acciones_fac.addWidget(btn_cargar_fac)
        btn_eliminar= BotonAnimado("Eliminar Facultad Seleccionada")
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_facultad)
        fila_acciones_fac.addWidget(btn_eliminar)
        btn_detalle_fac= agregar_boton_detalle(fila_acciones_fac, self.tabla_facultades, self, titulo="Detalle de la Facultad")
        self.tabla_facultades.doubleClicked.connect(lambda *_: btn_detalle_fac.click())
        fila_acciones_fac.addStretch()
        layout_tabla.addLayout(fila_acciones_fac)
        disposicion.addWidget(tarjeta_tabla)
        disposicion.addStretch()
        return contenedor

    def _limpiar_facultad(self):

        self.id_edicion_facultad= None
        self.btn_guardar_facultad.setText("Agregar Facultad")
        self.f_nombre.clear()
        self.tabla_facultades.clearSelection()
        desactivar_modo_edicion(self.f_nombre)

    def _cargar_facultad_seleccionada(self):

        fila= self.tabla_facultades.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una facultad de la tabla.", self)
            return
        id_fac= int(self.tabla_facultades.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM facultades WHERE id=?", (id_fac,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_facultad= f["id"]
        self.f_nombre.setText(f["nombre"] or "")
        self.btn_guardar_facultad.setText("Guardar Cambios")
        activar_modo_edicion(self.f_nombre, f"Editando facultad: {f['nombre'] or ''}")

    def _guardar_facultad(self):

        nombre= self.f_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        if self._nombre_duplicado("facultades", nombre, self.id_edicion_facultad):
            mostrar_mensaje("advertencia", "Facultad duplicada",
                             f"Ya existe una facultad llamada «{nombre}».", self)
            self._destello(self.sombra_form_facultad, "#EF4444")
            return

        def _accion(conn, c):

            if self.id_edicion_facultad is None:
                c.execute("INSERT INTO facultades (nombre) VALUES (?)", (nombre,))
            else:
                c.execute("UPDATE facultades SET nombre=? WHERE id=?", (nombre, self.id_edicion_facultad))

        exito= self._operacion_bd_segura(_accion, "No se pudo guardar la facultad")
        if not exito:
            return
        accion= "Editó facultad" if self.id_edicion_facultad is not None else "Agregó facultad"
        registrar_auditoria("Universidad", accion, self.main_window.usuario_actual, nombre)
        self._limpiar_facultad()
        self._cargar_facultades()
        self._cargar_facultades_combo()
        self._cargar_datos_donut()
        self._destello(self.sombra_form_facultad, "#22C55E")

    def _eliminar_facultad(self):

        fila= self.tabla_facultades.currentRow()
        if fila < 0:
            return
        id_fac= int(self.tabla_facultades.item(fila, 0).text())
        if mostrar_mensaje(
            "pregunta", "Confirmar",
            "¿Eliminar esta facultad? También se eliminarán todas sus carreras "
            "y, con ellas, el pensum (materias y prerrequisitos) que tengan asignado.",
            self
        ) != QMessageBox.StandardButton.Yes:
            return

        def _accion(conn, c):

            c.execute("DELETE FROM facultades WHERE id=?", (id_fac,))

        exito= self._operacion_bd_segura(_accion, "No se pudo eliminar la facultad")
        if not exito:
            return
        self._destello(self.sombra_form_facultad, "#EF4444")
        registrar_auditoria("Universidad", "Eliminó facultad", self.main_window.usuario_actual, str(id_fac))
        self._cargar_facultades()
        self._cargar_facultades_combo()
        self._cargar_datos_donut()

    def _filtro_facultades_cambio(self):

        self.paginacion_facultades.reiniciar()
        self._cargar_facultades()

    def _cargar_facultades(self):

        texto= _normalizar(self.in_buscar_facultades.text().strip()) if hasattr(self, "in_buscar_facultades") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        #Se trae también cuántas carreras tiene cada facultad (misma cuenta que ya calcula _cargar_datos_donut para el
        #anillo) para poder mostrarla en la tabla: así deja de ser un simple listado de nombres y da una idea real del
        #tamaño de cada facultad de un vistazo.
        c.execute("""SELECT facultades.id, facultades.nombre, COUNT(carreras.id) as total_carreras
                     FROM facultades LEFT JOIN carreras ON carreras.facultad_id = facultades.id
                     GROUP BY facultades.id ORDER BY facultades.nombre""")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(fila["nombre"] or "")]
        self.paginacion_facultades.establecer_total(len(filas))
        inicio, fin= self.paginacion_facultades.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_facultades):
            self.tabla_facultades.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                #El color del punto es el MISMO que usa la porción de esta facultad en el anillo/leyenda de arriba (índice
                #alfabético, igual que allá) para que la tabla se lea como una extensión de esa visualización y no como algo
                #aparte.
                color= _color_serie(inicio + i)
                self.tabla_facultades.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                item_punto= QTableWidgetItem()
                item_punto.setIcon(QIcon(_pixmap_punto(color, 12)))
                item_punto.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla_facultades.setItem(i, 1, item_punto)
                self.tabla_facultades.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                item_total= QTableWidgetItem(str(f["total_carreras"]))
                item_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla_facultades.setItem(i, 3, item_total)
            ajustar_anchos_columnas(self.tabla_facultades)
        self._animar_fundido_tabla(self.tabla_facultades)

    def _cargar_datos_donut(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT facultades.id, facultades.nombre, COUNT(carreras.id) as total
                     FROM facultades LEFT JOIN carreras ON carreras.facultad_id = facultades.id
                     GROUP BY facultades.id ORDER BY facultades.nombre""")
        filas= c.fetchall()
        conn.close()
        self._colores_facultad= {}
        segmentos= []
        for i, f in enumerate(filas):
            color= _color_serie(i)
            self._colores_facultad[f["nombre"]]= color
            segmentos.append({"etiqueta": f["nombre"], "valor": f["total"], "color": color})
        if hasattr(self, "anillo_facultades"):
            self.anillo_facultades.establecer_datos(segmentos)
            self._actualizar_leyenda_donut(segmentos)
        total_facultades= len(filas)
        total_carreras= sum(fila["total"] for fila in filas)
        if hasattr(self, "chip_facultades"):
            #Iconos dibujados con QPainter (mismos dibujos que ya usa el resto de la app), insertados como <img> inline en
            #vez del emoji real para no depender de una fuente de emojis del sistema.
            self._animar_valor_chip(self.chip_facultades, "_valor_chip_facultades", total_facultades,
                                     lambda v: f"{html_icono_emoji('🏛', 14)} {v} facultad" + ("es" if v != 1 else ""))
            self._animar_valor_chip(self.chip_carreras, "_valor_chip_carreras", total_carreras,
                                     lambda v: f"{html_icono_emoji('🎓', 14)} {v} carrera" + ("s" if v != 1 else ""))

    def _actualizar_leyenda_donut(self, segmentos):

        while self.layout_leyenda_donut.count():
            item= self.layout_leyenda_donut.takeAt(0)
            w= item.widget()
            if w is not None:
                w.deleteLater()
        if not segmentos:
            lbl= QLabel("Aún no hay facultades registradas.")
            lbl.setObjectName("AvisoVacioUniversidad")
            lbl.setWordWrap(True)
            self.layout_leyenda_donut.addWidget(lbl)
            return
        for seg in segmentos:
            fila= QHBoxLayout()
            fila.setSpacing(8)
            punto= QLabel()
            punto.setFixedSize(10, 10)
            punto.setStyleSheet(f"background-color:{seg['color']}; border-radius:5px;")
            fila.addWidget(punto)
            texto= QLabel(f"{seg['etiqueta']}  ·  {seg['valor']}")
            texto.setObjectName("LeyendaTextoUniversidad")
            fila.addWidget(texto, 1)
            contenedor= QWidget()
            contenedor.setLayout(fila)
            self.layout_leyenda_donut.addWidget(contenedor)
        self.layout_leyenda_donut.addStretch()

    #---------------- CARRERAS ----------------
    def _tab_carreras(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        self.tarjeta_form_carrera, layout_form, self.sombra_form_carrera= self._crear_tarjeta()
        titulo_form= QLabel("Nueva carrera")
        titulo_form.setObjectName("TituloTarjetaUniversidad")
        layout_form.addWidget(titulo_form)
        form= QGridLayout()
        self.car_nombre= QLineEdit()
        self.car_nombre.setPlaceholderText("Nombre de la Carrera")
        limitar_campo_texto(self.car_nombre, 300)
        self.car_nombre.setToolTip("Nombre de la carrera (ej. Ingeniería en Sistemas)")
        self.car_facultad= QComboBox()
        conectar_tooltip_seleccion(self.car_facultad, "Facultad a la que pertenece esta carrera")
        form.addWidget(self.car_nombre, 0, 0)
        form.addWidget(self.car_facultad, 0, 1)
        self.btn_guardar_carrera= BotonAnimado("Agregar Carrera")
        self.btn_guardar_carrera.setObjectName("BtnAccionAgregar")
        self.btn_guardar_carrera.clicked.connect(self._guardar_carrera)
        form.addWidget(self.btn_guardar_carrera, 1, 0)
        layout_form.addLayout(form)
        disposicion.addWidget(self.tarjeta_form_carrera)

        tarjeta_tabla, layout_tabla, _= self._crear_tarjeta()
        marco_busqueda_car, self.in_buscar_carreras= self._crear_barra_busqueda(
            "Buscar carrera por nombre o facultad…", self._filtro_carreras_cambio)
        layout_tabla.addWidget(marco_busqueda_car)
        self.tabla_carreras= QTableWidget(0, 3)
        aplicar_estructura_tabla(self.tabla_carreras)

        self.tabla_carreras.setHorizontalHeaderLabels(["ID", "Carrera", "Facultad"])
        header= self.tabla_carreras.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.tabla_carreras.setColumnHidden(0, True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_carreras.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_carreras.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_carreras.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_carreras.setAlternatingRowColors(True)
        self.tabla_carreras.setWordWrap(True)
        self.tabla_carreras.setMinimumHeight(320)
        self.tabla_carreras.verticalHeader().setVisible(False)
        layout_tabla.addWidget(self.tabla_carreras, 1)
        self.paginacion_carreras= ControlPaginacion()
        self.paginacion_carreras.cambio.connect(self._cargar_carreras)
        layout_tabla.addWidget(self.paginacion_carreras)
        agregar_boton_pantalla_completa(
            None, [self.tabla_carreras, self.paginacion_carreras],
            titulo= "Carreras", parent=self)
        fila_acciones_car= QHBoxLayout()
        btn_actualizar_car= BotonAnimado("Actualizar")
        btn_actualizar_car.setObjectName("BtnAccionNeutro")
        btn_actualizar_car.clicked.connect(self._cargar_carreras)
        fila_acciones_car.addWidget(btn_actualizar_car)
        btn_limpiar_car= BotonAnimado("Limpiar")
        btn_limpiar_car.setObjectName("BtnAccionNeutro")
        btn_limpiar_car.clicked.connect(self._limpiar_carrera)
        fila_acciones_car.addWidget(btn_limpiar_car)
        btn_cargar_car= BotonAnimado("Cargar Seleccionada")
        btn_cargar_car.setIcon(icono_emoji("✏"))
        btn_cargar_car.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_car.setObjectName("BtnAccionEditar")
        btn_cargar_car.clicked.connect(self._cargar_carrera_seleccionada)
        fila_acciones_car.addWidget(btn_cargar_car)
        btn_eliminar= BotonAnimado("Eliminar Carrera Seleccionada")
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_carrera)
        fila_acciones_car.addWidget(btn_eliminar)
        btn_detalle_car= agregar_boton_detalle(fila_acciones_car, self.tabla_carreras, self, titulo="Detalle de la Carrera")
        self.tabla_carreras.doubleClicked.connect(lambda *_: btn_detalle_car.click())
        fila_acciones_car.addStretch()
        layout_tabla.addLayout(fila_acciones_car)
        disposicion.addWidget(tarjeta_tabla)
        disposicion.addStretch()
        return contenedor

    def _limpiar_carrera(self):

        self.id_edicion_carrera= None
        self.btn_guardar_carrera.setText("Agregar Carrera")
        self.car_nombre.clear()
        self.car_facultad.setCurrentIndex(0)
        desactivar_modo_edicion(self.car_nombre)
        self.tabla_carreras.clearSelection()

    def _cargar_facultades_combo(self):

        seleccion_previa= self.car_facultad.currentData()
        self.car_facultad.blockSignals(True)
        self.car_facultad.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM facultades ORDER BY nombre")
        for fila in c.fetchall():
            self.car_facultad.addItem(fila["nombre"], fila["id"])
        conn.close()
        if seleccion_previa is not None:
            idx= self.car_facultad.findData(seleccion_previa)
            self.car_facultad.setCurrentIndex(idx if idx >= 0 else 0)
        self.car_facultad.blockSignals(False)

    def _cargar_carrera_seleccionada(self):

        fila= self.tabla_carreras.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una carrera de la tabla.", self)
            return
        id_car= int(self.tabla_carreras.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM carreras WHERE id=?", (id_car,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_carrera= f["id"]
        self.car_nombre.setText(f["nombre"] or "")
        idx= self.car_facultad.findData(f["facultad_id"])
        self.car_facultad.setCurrentIndex(idx if idx >= 0 else 0)
        self.btn_guardar_carrera.setText("Guardar Cambios")
        activar_modo_edicion(self.car_nombre, f"Editando carrera: {f['nombre'] or ''}")

    def _guardar_carrera(self):

        nombre= self.car_nombre.text().strip()
        facultad_id= self.car_facultad.currentData()
        if not nombre or facultad_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Nombre y facultad son obligatorios.", self)
            return
        if self._nombre_duplicado("carreras", nombre, self.id_edicion_carrera,
                                   filtro_extra= ("facultad_id = ?", [facultad_id])):
            mostrar_mensaje("advertencia", "Carrera duplicada",
                             f"Ya existe una carrera llamada «{nombre}» en esta facultad.", self)
            self._destello(self.sombra_form_carrera, "#EF4444")
            return

        def _accion(conn, c):

            if self.id_edicion_carrera is None:
                c.execute("INSERT INTO carreras (nombre, facultad_id) VALUES (?,?)", (nombre, facultad_id))
            else:
                c.execute("UPDATE carreras SET nombre=?, facultad_id=? WHERE id=?",
                          (nombre, facultad_id, self.id_edicion_carrera))

        exito= self._operacion_bd_segura(_accion, "No se pudo guardar la carrera")
        if not exito:
            return
        accion= "Editó carrera" if self.id_edicion_carrera is not None else "Agregó carrera"
        registrar_auditoria("Universidad", accion, self.main_window.usuario_actual, nombre)
        self._limpiar_carrera()
        self._cargar_carreras()
        self._cargar_datos_donut()
        if hasattr(self, "pen_carrera"):
            self._cargar_combos_pensum()
        self._destello(self.sombra_form_carrera, "#22C55E")

    def _eliminar_carrera(self):

        fila= self.tabla_carreras.currentRow()
        if fila < 0:
            return
        id_car= int(self.tabla_carreras.item(fila, 0).text())
        if mostrar_mensaje(
            "pregunta", "Confirmar",
            "¿Eliminar esta carrera? También se eliminará todo el pensum "
            "(materias y prerrequisitos) asignado a ella.",
            self
        ) != QMessageBox.StandardButton.Yes:
            return

        def _accion(conn, c):

            c.execute("DELETE FROM carreras WHERE id=?", (id_car,))

        exito= self._operacion_bd_segura(_accion, "No se pudo eliminar la carrera")
        if not exito:
            return
        self._destello(self.sombra_form_carrera, "#EF4444")
        registrar_auditoria("Universidad", "Eliminó carrera", self.main_window.usuario_actual, str(id_car))
        self._cargar_carreras()
        self._cargar_datos_donut()
        if hasattr(self, "pen_carrera"):
            self._cargar_combos_pensum()

    def _filtro_carreras_cambio(self):

        self.paginacion_carreras.reiniciar()
        self._cargar_carreras()

    def _cargar_carreras(self):

        texto= _normalizar(self.in_buscar_carreras.text().strip()) if hasattr(self, "in_buscar_carreras") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT carreras.*, facultades.nombre as facultad_nombre FROM carreras
                     LEFT JOIN facultades ON carreras.facultad_id = facultades.id ORDER BY carreras.nombre""")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['nombre'] or ''} {fila['facultad_nombre'] or ''}")]
        self.paginacion_carreras.establecer_total(len(filas))
        inicio, fin= self.paginacion_carreras.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_carreras):
            self.tabla_carreras.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_carreras.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_carreras.setItem(i, 1, QTableWidgetItem(f["nombre"] or ""))
                nombre_fac= f["facultad_nombre"] or "Sin facultad"
                color= self._colores_facultad.get(nombre_fac, "#94A3B8")
                item_fac= QTableWidgetItem(self._icono_punto(color), nombre_fac)
                self.tabla_carreras.setItem(i, 2, item_fac)
            ajustar_anchos_columnas(self.tabla_carreras)
        self._animar_fundido_tabla(self.tabla_carreras)

    #---------------- PENSUM / MALLA CURRICULAR ----------------
    def _tab_pensum(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        self.tarjeta_malla, layout_malla, _= self._crear_tarjeta()
        fila_malla_titulo= QHBoxLayout()
        titulo_malla= QLabel("Mapa curricular")
        titulo_malla.setObjectName("TituloTarjetaUniversidad")
        fila_malla_titulo.addWidget(titulo_malla)
        fila_malla_titulo.addStretch()
        fila_malla_titulo.addWidget(QLabel("Carrera:"))
        self.malla_filtro_carrera= QComboBox()
        self.malla_filtro_carrera.setToolTip("Carrera cuya malla curricular quieres visualizar")
        self.malla_filtro_carrera.setMinimumWidth(220)
        conectar_tooltip_seleccion(self.malla_filtro_carrera, "Carrera cuya malla curricular quieres visualizar")
        self.malla_filtro_carrera.currentIndexChanged.connect(self._reconstruir_malla)
        fila_malla_titulo.addWidget(self.malla_filtro_carrera)
        layout_malla.addLayout(fila_malla_titulo)

        ayuda_malla= QLabel("Cada ficha es una materia; las flechas apuntan de su prerrequisito hacia ella. "
                              "Pasa el mouse sobre una materia para resaltar su cadena. Borde punteado = electiva.")
        ayuda_malla.setObjectName("DescModulo")
        ayuda_malla.setWordWrap(True)
        layout_malla.addWidget(ayuda_malla)

        self.malla= MallaCurricular()
        self.estado_vacio_malla= EstadoVacioFiltro(
            self.malla, texto_filtra_primero="Elige una carrera para revelar su malla curricular")
        self.malla_scroll= QScrollArea()
        self.malla_scroll.setWidgetResizable(True)
        self.malla_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.malla_scroll.setFixedHeight(300)
        self.malla_scroll.setWidget(self.malla)
        layout_malla.addWidget(self.malla_scroll)
        disposicion.addWidget(self.tarjeta_malla)

        self.tarjeta_form_pensum, layout_form, self.sombra_form_pensum= self._crear_tarjeta()
        titulo_form= QLabel("Agregar materia al pensum")
        titulo_form.setObjectName("TituloTarjetaUniversidad")
        layout_form.addWidget(titulo_form)
        form= QGridLayout()
        self.pen_carrera= QComboBox()
        conectar_tooltip_seleccion(self.pen_carrera, "Carrera a la que se agrega esta materia en el pensum")
        self.pen_carrera.currentIndexChanged.connect(self._actualizar_prerrequisitos_disponibles)
        self.pen_materia= QComboBox()
        conectar_tooltip_seleccion(self.pen_materia, "Materia que se incluirá en el pensum de la carrera")
        self.pen_materia.currentIndexChanged.connect(self._actualizar_prerrequisitos_disponibles)
        self.pen_semestre= QSpinBox()
        self.pen_semestre.setRange(1, 20)
        self.pen_semestre.setToolTip("Semestre en el que se cursa esta materia (1-20)")
        self.pen_prerrequisito= QComboBox()
        conectar_tooltip_seleccion(self.pen_prerrequisito,
            "Materia que debe aprobarse antes de cursar esta (opcional). Solo se listan "
            "materias que ya estén en el pensum de la carrera elegida arriba.")
        self.pen_electiva= QCheckBox("Es materia electiva")
        self.pen_electiva.setToolTip("Marca esta casilla si la materia es electiva (no obligatoria)")
        form.addWidget(self.pen_carrera, 0, 0)
        form.addWidget(self.pen_materia, 0, 1)
        form.addWidget(self.pen_semestre, 0, 2)
        form.addWidget(self.pen_prerrequisito, 1, 0)
        form.addWidget(self.pen_electiva, 1, 1)
        self.btn_guardar_pensum= BotonAnimado("Agregar al Pensum")
        self.btn_guardar_pensum.setObjectName("BtnAccionAgregar")
        self.btn_guardar_pensum.clicked.connect(self._guardar_pensum)
        form.addWidget(self.btn_guardar_pensum, 2, 0)
        layout_form.addLayout(form)
        disposicion.addWidget(self.tarjeta_form_pensum)

        tarjeta_tabla, layout_tabla, _= self._crear_tarjeta()
        marco_busqueda_pensum, self.in_buscar_pensum= self._crear_barra_busqueda(
            "Buscar por carrera o materia…", self._filtro_pensum_cambio)
        layout_tabla.addWidget(marco_busqueda_pensum)
        self.tabla_pensum= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_pensum)

        self.tabla_pensum.setHorizontalHeaderLabels(
            ["ID", "Carrera", "Materia", "Semestre", "Prerrequisito", "Electiva"])
        header= self.tabla_pensum.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_pensum.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_pensum.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_pensum.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_pensum.setAlternatingRowColors(True)
        self.tabla_pensum.setWordWrap(True)
        self.tabla_pensum.setMinimumHeight(320)
        self.tabla_pensum.verticalHeader().setVisible(False)
        layout_tabla.addWidget(self.tabla_pensum, 1)
        self.paginacion_pensum= ControlPaginacion()
        self.paginacion_pensum.cambio.connect(self._cargar_pensum)
        layout_tabla.addWidget(self.paginacion_pensum)
        agregar_boton_pantalla_completa(
            None, [self.tabla_pensum, self.paginacion_pensum],
            titulo= "Pensum", parent=self)
        fila_acciones_pensum= QHBoxLayout()
        btn_actualizar_pensum= BotonAnimado("Actualizar")
        btn_actualizar_pensum.setObjectName("BtnAccionNeutro")
        btn_actualizar_pensum.clicked.connect(self._cargar_pensum)
        fila_acciones_pensum.addWidget(btn_actualizar_pensum)
        btn_limpiar_pensum= BotonAnimado("Limpiar")
        btn_limpiar_pensum.setObjectName("BtnAccionNeutro")
        btn_limpiar_pensum.clicked.connect(self._limpiar_pensum)
        fila_acciones_pensum.addWidget(btn_limpiar_pensum)
        btn_cargar_pensum= BotonAnimado("Cargar Seleccionada")
        btn_cargar_pensum.setIcon(icono_emoji("✏"))
        btn_cargar_pensum.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_pensum.setObjectName("BtnAccionEditar")
        btn_cargar_pensum.clicked.connect(self._cargar_pensum_seleccionado)
        fila_acciones_pensum.addWidget(btn_cargar_pensum)
        btn_eliminar= BotonAnimado("Eliminar del Pensum")
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_pensum)
        fila_acciones_pensum.addWidget(btn_eliminar)
        btn_detalle_pen= agregar_boton_detalle(fila_acciones_pensum, self.tabla_pensum, self, titulo="Detalle del Pensum")
        self.tabla_pensum.doubleClicked.connect(lambda *_: btn_detalle_pen.click())
        fila_acciones_pensum.addStretch()
        layout_tabla.addLayout(fila_acciones_pensum)
        disposicion.addWidget(tarjeta_tabla)
        disposicion.addStretch()
        return contenedor

    def _limpiar_pensum(self):

        self.id_edicion_pensum= None
        self.btn_guardar_pensum.setText("Agregar al Pensum")
        self.pen_carrera.setCurrentIndex(0)
        self.pen_materia.setCurrentIndex(0)
        desactivar_modo_edicion(self.pen_semestre)
        self.pen_semestre.setValue(1)
        self.pen_prerrequisito.setCurrentIndex(0)
        self.pen_electiva.setChecked(False)
        self.tabla_pensum.clearSelection()

    def _cargar_pensum_seleccionado(self):

        fila= self.tabla_pensum.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro del pensum en la tabla.", self)
            return
        id_p= int(self.tabla_pensum.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM pensum WHERE id=?", (id_p,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_pensum= f["id"]
        idx_car= self.pen_carrera.findData(f["carrera_id"])
        self.pen_carrera.setCurrentIndex(idx_car if idx_car >= 0 else 0)
        idx_mat= self.pen_materia.findData(f["materia_id"])
        self.pen_materia.setCurrentIndex(idx_mat if idx_mat >= 0 else 0)
        self.pen_semestre.setValue(f["semestre"] or 1)
        idx_prereq= self.pen_prerrequisito.findData(f["prerrequisito_id"])
        self.pen_prerrequisito.setCurrentIndex(idx_prereq if idx_prereq >= 0 else 0)
        self.pen_electiva.setChecked(bool(f["electiva"]))
        self.btn_guardar_pensum.setText("Guardar Cambios")
        activar_modo_edicion(self.pen_semestre, "Editando registro del pensum")

    def _cargar_combos_pensum(self):

        self.pen_carrera.blockSignals(True)
        self.pen_materia.blockSignals(True)
        self.pen_carrera.clear()
        self.pen_materia.clear()
        seleccion_malla_previa= self.malla_filtro_carrera.currentData() if hasattr(self, "malla_filtro_carrera") else None
        if hasattr(self, "malla_filtro_carrera"):
            self.malla_filtro_carrera.blockSignals(True)
            self.malla_filtro_carrera.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
        for fila in c.fetchall():
            self.pen_carrera.addItem(fila["nombre"], fila["id"])
            if hasattr(self, "malla_filtro_carrera"):
                self.malla_filtro_carrera.addItem(fila["nombre"], fila["id"])
        c.execute("SELECT id, nombre FROM materias ORDER BY nombre")
        for fila in c.fetchall():
            self.pen_materia.addItem(fila["nombre"], fila["id"])
        conn.close()
        if hasattr(self, "malla_filtro_carrera"):
            if seleccion_malla_previa is not None:
                idx= self.malla_filtro_carrera.findData(seleccion_malla_previa)
                self.malla_filtro_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.malla_filtro_carrera.blockSignals(False)
        self.pen_carrera.blockSignals(False)
        self.pen_materia.blockSignals(False)
        #El combo de prerrequisitos depende de la carrera/materia elegidas (ver
        #_actualizar_prerrequisitos_disponibles), así que se repuebla al final.
        self._actualizar_prerrequisitos_disponibles()

    #Repuebla `pen_prerrequisito` solo con materias que ya estén en el pensum
    #de la carrera elegida en `pen_carrera` (y nunca con la propia materia que se
    #está agregando/editando en `pen_materia`), para que sea imposible elegir en
    #la interfaz un prerrequisito de otra carrera o que la materia sea prerrequisito
    #de sí misma. La validación final (orden de semestre, ciclos) se hace igual al
    #guardar, por si el valor ya estaba puesto antes de cambiar carrera/materia.
    def _actualizar_prerrequisitos_disponibles(self):

        if not hasattr(self, "pen_prerrequisito"):
            return
        carrera_id= self.pen_carrera.currentData()
        materia_actual= self.pen_materia.currentData()
        seleccion_previa= self.pen_prerrequisito.currentData()
        self.pen_prerrequisito.blockSignals(True)
        self.pen_prerrequisito.clear()
        self.pen_prerrequisito.addItem("Ninguno", None)
        if carrera_id is not None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT DISTINCT materias.id, materias.nombre
                         FROM pensum LEFT JOIN materias ON pensum.materia_id = materias.id
                         WHERE pensum.carrera_id = ? ORDER BY materias.nombre""", (carrera_id,))
            for fila in c.fetchall():
                if materia_actual is not None and fila["id"] == materia_actual:
                    continue
                self.pen_prerrequisito.addItem(fila["nombre"], fila["id"])
            conn.close()
        idx= self.pen_prerrequisito.findData(seleccion_previa)
        self.pen_prerrequisito.setCurrentIndex(idx if idx >= 0 else 0)
        self.pen_prerrequisito.blockSignals(False)

    def _guardar_pensum(self):

        carrera_id= self.pen_carrera.currentData()
        materia_id= self.pen_materia.currentData()
        if carrera_id is None or materia_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona carrera y materia.", self)
            return

        prerrequisito_id= self.pen_prerrequisito.currentData()
        semestre= self.pen_semestre.value()
        electiva= 1 if self.pen_electiva.isChecked() else 0
        id_actual= self.id_edicion_pensum

        if prerrequisito_id is not None and prerrequisito_id == materia_id:
            mostrar_mensaje("advertencia", "Prerrequisito inválido",
                             "Una materia no puede ser prerrequisito de sí misma.", self)
            self._destello(self.sombra_form_pensum, "#EF4444")
            return

        conn= obtener_conexion()
        c= conn.cursor()
        try:

            #1) La misma materia no puede repetirse en el pensum de una carrera.
            c.execute("SELECT id FROM pensum WHERE carrera_id=? AND materia_id=? AND id != ?",
                      (carrera_id, materia_id, id_actual or 0))
            if c.fetchone():
                mostrar_mensaje("advertencia", "Materia duplicada",
                                 "Esta materia ya está incluida en el pensum de esa carrera.", self)
                self._destello(self.sombra_form_pensum, "#EF4444")
                return

            if prerrequisito_id is not None:
                #2) El prerrequisito debe pertenecer al pensum de la MISMA carrera.
                c.execute("SELECT semestre FROM pensum WHERE carrera_id=? AND materia_id=?",
                          (carrera_id, prerrequisito_id))
                fila_prereq= c.fetchone()
                if fila_prereq is None:
                    mostrar_mensaje("advertencia", "Prerrequisito inválido",
                                     "El prerrequisito elegido no pertenece al pensum de esta carrera. "
                                     "Agrégalo primero al pensum antes de usarlo como prerrequisito.", self)
                    self._destello(self.sombra_form_pensum, "#EF4444")
                    return

                #3) El prerrequisito debe ser de un semestre anterior.
                if fila_prereq["semestre"] is not None and fila_prereq["semestre"] >= semestre:
                    mostrar_mensaje("advertencia", "Prerrequisito inválido",
                                     "El prerrequisito debe pertenecer a un semestre anterior al de esta materia.",
                                     self)
                    self._destello(self.sombra_form_pensum, "#EF4444")
                    return

                #4) Detección de ciclos: A no puede depender (directa o indirectamente) de algo que a su vez dependa de A.
                c.execute("SELECT materia_id, prerrequisito_id FROM pensum WHERE carrera_id=? AND id != ?",
                          (carrera_id, id_actual or 0))
                grafo= {}
                for fila in c.fetchall():
                    if fila["prerrequisito_id"] is not None:
                        grafo.setdefault(fila["materia_id"], set()).add(fila["prerrequisito_id"])
                grafo.setdefault(materia_id, set()).add(prerrequisito_id)

                visitado, en_pila= set(), set()

                def _tiene_ciclo(nodo):

                    visitado.add(nodo)
                    en_pila.add(nodo)
                    for vecino in grafo.get(nodo, ()):
                        if vecino not in visitado:
                            if _tiene_ciclo(vecino):
                                return True
                        elif vecino in en_pila:
                            return True
                    en_pila.discard(nodo)
                    return False

                if _tiene_ciclo(materia_id):
                    mostrar_mensaje("advertencia", "Prerrequisito inválido",
                                     "Ese prerrequisito crearía un ciclo de dependencias entre materias.", self)
                    self._destello(self.sombra_form_pensum, "#EF4444")
                    return

            if id_actual is None:
                c.execute("""INSERT INTO pensum (carrera_id, materia_id, semestre, prerrequisito_id, electiva)
                             VALUES (?,?,?,?,?)""",
                          (carrera_id, materia_id, semestre, prerrequisito_id, electiva))
                accion= "Agregó materia al pensum"
            else:
                c.execute("""UPDATE pensum SET carrera_id=?, materia_id=?, semestre=?, prerrequisito_id=?,
                             electiva= ? WHERE id=?""",
                          (carrera_id, materia_id, semestre, prerrequisito_id, electiva, id_actual))
                accion= "Editó materia del pensum"
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo guardar el pensum:\n{error}", self)
            return
        finally:
            conn.close()

        registrar_auditoria("Universidad", accion, self.main_window.usuario_actual,
                            f"Carrera {carrera_id} - Materia {materia_id}")
        self._limpiar_pensum()
        self._cargar_pensum()
        self._reconstruir_malla()
        self._destello(self.sombra_form_pensum, "#22C55E")

    def _eliminar_pensum(self):

        fila= self.tabla_pensum.currentRow()
        if fila < 0:
            return
        id_p= int(self.tabla_pensum.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta materia del pensum?", self) != QMessageBox.StandardButton.Yes:
            return

        def _accion(conn, c):

            c.execute("DELETE FROM pensum WHERE id=?", (id_p,))

        exito= self._operacion_bd_segura(_accion, "No se pudo eliminar la materia del pensum")
        if not exito:
            return
        self._destello(self.sombra_form_pensum, "#EF4444")
        registrar_auditoria("Universidad", "Eliminó materia del pensum", self.main_window.usuario_actual, str(id_p))
        self._cargar_pensum()
        self._reconstruir_malla()

    def _filtro_pensum_cambio(self):

        self.paginacion_pensum.reiniciar()
        self._cargar_pensum()

    def _cargar_pensum(self):

        texto= _normalizar(self.in_buscar_pensum.text().strip()) if hasattr(self, "in_buscar_pensum") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT pensum.*, carreras.nombre as carrera_nombre, materias.nombre as materia_nombre,
                     prereq.nombre as prereq_nombre FROM pensum
                     LEFT JOIN carreras ON pensum.carrera_id = carreras.id
                     LEFT JOIN materias ON pensum.materia_id = materias.id
                     LEFT JOIN materias prereq ON pensum.prerrequisito_id = prereq.id
                     ORDER BY carreras.nombre, pensum.semestre""")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['carrera_nombre'] or ''} {fila['materia_nombre'] or ''}")]
        self.paginacion_pensum.establecer_total(len(filas))
        inicio, fin= self.paginacion_pensum.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_pensum):
            self.tabla_pensum.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_pensum.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_pensum.setItem(i, 1, QTableWidgetItem(f["carrera_nombre"] or ""))
                self.tabla_pensum.setItem(i, 2, QTableWidgetItem(f["materia_nombre"] or ""))
                self.tabla_pensum.setItem(i, 3, QTableWidgetItem(str(f["semestre"] or 1)))
                self.tabla_pensum.setItem(i, 4, QTableWidgetItem(f["prereq_nombre"] or "Ninguno"))
                self.tabla_pensum.setItem(i, 5, QTableWidgetItem("Sí" if f["electiva"] else "No"))
            ajustar_anchos_columnas(self.tabla_pensum)
        self._animar_fundido_tabla(self.tabla_pensum)

    def _reconstruir_malla(self):

        if not hasattr(self, "malla"):
            return
        carrera_id= self.malla_filtro_carrera.currentData()
        if carrera_id is None:
            self.malla.establecer_datos([])
            self.estado_vacio_malla.actualizar(hay_filtro_elegido=False, vacio=True)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT pensum.materia_id, materias.nombre as materia_nombre, pensum.semestre,
                     pensum.prerrequisito_id, pensum.electiva
                     FROM pensum LEFT JOIN materias ON pensum.materia_id = materias.id
                     WHERE pensum.carrera_id = ? ORDER BY pensum.semestre""", (carrera_id,))
        filas= [dict(row) for row in c.fetchall()]
        conn.close()
        self.malla.establecer_datos(filas)
        self.estado_vacio_malla.actualizar(hay_filtro_elegido=True, vacio=not filas)
        self._animar_entrada(self.tarjeta_malla)

    #Refresco global y tema
    #Refresca combos, indicadores visuales (anillo/barra/chips) y la
    #pestaña que esté visible. El resto de pestañas se recargan solas la
    #primera vez que el usuario las abre (ver _cambio_pestana): así entrar
    #al módulo se siente instantáneo aunque haya mucha información.
    def refrescar(self):

        self._cargar_facultades_combo()
        self._cargar_combos_pensum()
        self._cargar_datos_donut()
        self._pestanas_cargadas= set()
        self._cambio_pestana(self.tabs.currentIndex())

    #Sincroniza colores del módulo (cabecera, tarjetas, anillo, barra y
    #malla curricular) con el tema/modo claro-oscuro actual de la app.
    #
    #Look propio de Universidad: tarjeta de cabecera con "lomo" de acento a
    #la izquierda (en vez del bloque de degradado sólido de otros módulos),
    #insignia circular de icono en color sólido, chips con contorno (no
    #rellenos) y pestañas con el mismo estilo "píldora" que politecnico.py.
    #Solo estética: no cambia objectNames, layout ni lógica.
    def actualizar_tema(self):

        colores= _colores_tema(self.main_window)
        modo_oscuro= getattr(self.main_window, "modo_oscuro", False)
        self.setStyleSheet(f"""
            QFrame#TarjetaCabeceraUniversidad {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-left: 5px solid {colores['accent']};
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 18px;
                border-bottom-right-radius: 18px;
            }}
            QLabel#IconoCabeceraUniversidad {{
                background-color: {colores['accent']};
                border-radius: 23px;
                font-size: 22px;
                color: white;
            }}
            QLabel#TituloCabeceraUniversidad {{
                font-size: 21px;
                font-weight: 800;
                color: {colores['txt_prim']};
                background: transparent;
            }}
            QLabel#SubtituloCabeceraUniversidad {{
                font-size: 12px;
                color: {colores['txt_sec']};
                background: transparent;
            }}
            QLabel#ChipResumenUniversidad {{
                background-color: transparent;
                color: {colores['accent']};
                border: 1.5px solid {colores['accent']};
                border-radius: 14px;
                padding: 6px 13px;
                font-weight: 700;
                font-size: 12px;
            }}
            QFrame#PanelUniversidad {{
                background-color: {colores['bg_panel']};
                border: 1px solid {colores['bg_btn']};
                border-top: 3px solid {colores['accent']};
                border-radius: 16px;
            }}
            QLabel#TituloTarjetaUniversidad {{
                font-size: 14px;
                font-weight: 800;
                color: {colores['accent']};
                background: transparent;
            }}
            QLabel#LeyendaTextoUniversidad {{
                font-size: 12px;
                color: {colores['txt_prim']};
                background: transparent;
            }}
            QLabel#AvisoVacioUniversidad {{
                font-size: 12px;
                color: {colores['txt_sec']};
                background: transparent;
                font-style: italic;
            }}
        """)
        if hasattr(self, "anillo_facultades"):
            self.anillo_facultades.poner_colores(colores["txt_prim"], colores["txt_sec"], colores["bg_btn"])
        if hasattr(self, "malla"):
            #Las electivas se pintan con un tinte magenta/violeta para distinguirlas a simple vista de las materias
            #normales (además del borde punteado). En claro usamos el tono pastel original; en oscuro usamos un violeta
            #oscuro para que el texto (claro) siga siendo legible sobre el fondo de la ficha.
            if modo_oscuro:
                color_electiva, color_electiva_borde= "#3B0764", "#E879F9"
            else:
                color_electiva, color_electiva_borde= "#FDF4FF", "#D946EF"
            self.malla.poner_colores(colores["bg_btn"], colores["accent"], colores["txt_prim"],
                                    colores["txt_sec"], colores["accent"],
                                    color_electiva, color_electiva_borde)
        for icono in getattr(self, "_iconos_busqueda", []):
            icono.establecer_color(colores["txt_sec"])

        #El selector de pestañas usa el mismo estilo "píldora" que politecnico.py: fondo translúcido, bordes
        #redondeados, gradiente en la pestaña seleccionada y resplandor de acento al pasar el mouse.
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background: {_hex_a_rgba(colores['txt_sec'], 0.10)};
                color: {colores['txt_sec']};
                padding: 9px 20px;
                margin-right: 8px;
                margin-bottom: 4px;
                border-radius: 12px;
                border: 1px solid {_hex_a_rgba(colores['txt_sec'], 0.16)};
                font-weight: 600;
                font-size: 13px;
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colores['accent']}, stop:1 {colores['accent_hv']});
                color: white;
                border: 1px solid transparent;
                font-weight: 700;
            }}
            QTabBar::tab:!selected:hover {{
                background-color: {_hex_a_rgba(colores['accent'], 0.20)};
                color: {colores['txt_prim']};
                border: 1px solid {_hex_a_rgba(colores['accent'], 0.35)};
            }}
        """)
