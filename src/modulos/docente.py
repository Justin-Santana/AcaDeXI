#Vistas propias del 'Modo Docente' (rol Profesor) de AcaDeXI.
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
QFrame, QScrollArea, QLayout, QColorDialog, QDialog, QMenu)
from PySide6.QtCore import (Qt, QTimer, QRect, QRectF, QPoint, QSize, QPropertyAnimation,
QEasingCurve, QVariantAnimation)
from PySide6.QtGui import QPainter, QColor, QPen
from src.nucleo.bd import obtener_conexion, registrar_auditoria, crear_backup, obtener_config_backup
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_COLOR
from src.nucleo.permisos import obtener_profesor_id
from src.sincronizacion.sync_docente import importar_paquete_docente
from src.interfaz.dashboard import PuntoPulso
from src.nucleo.formato_hora import formatear_hora
from src.nucleo.datos_locales_docente import (obtener_colores_materias_local, guardar_color_materia_local,
                                    eliminar_color_materia_local)
from src.nucleo.atajos import registrar_atajo
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, html_icono_emoji

DIAS_SEMANA= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
_PALETA_MATERIA= ["#6366F1", "#0D9488", "#8B5CF6", "#F59E0B", "#10B981",
                    "#EC4899", "#3B82F6", "#F97316", "#14B8A6", "#EF4444"]


def _hex_a_rgba(hex_color, alpha):

    hex_color= (hex_color or "#6366F1").lstrip("#")
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _color_para_materia(nombre):

    idx= sum(ord(ch) for ch in (nombre or "?")) % len(_PALETA_MATERIA)
    return _PALETA_MATERIA[idx]


def _minutos_desde_texto(hhmm):

    try:

        h, m= (hhmm or "").strip().split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


#Desliza un widget desde `offset_y` px por debajo hasta su posición final
#(ya calculada por el layout). Usa una animación de geometría (no de opacidad
#ni de efectos gráficos): es la forma más barata de dar una entrada animada,
#porque no obliga a Qt a recomponer el widget en un buffer aparte en cada
#frame, solo a reposicionarlo.
def _animar_entrada_geometria(widget, offset_y=16, duracion=260, retraso=0):

    geo_final= QRect(widget.geometry())
    geo_inicio= QRect(geo_final.x(), geo_final.y() + offset_y, geo_final.width(), geo_final.height())
    widget.setGeometry(geo_inicio)
    anim= QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duracion)
    anim.setStartValue(geo_inicio)
    anim.setEndValue(geo_final)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._anim_entrada= anim  #mantener referencia viva mientras corre
    QTimer.singleShot(retraso, anim.start)


#Layout de flujo (envuelve tarjetas a la siguiente línea según el ancho
#disponible). Recalcula posiciones sin recrear widgets, así que reflowar
#con el resize de la ventana es barato incluso con varias decenas de tarjetas.
class FlowLayout(QLayout):

    def __init__(self, parent=None, margin=0, spacing=12):

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


#Botón redondeado, moderno y divertido que abre un diálogo con la explicación
#de la pantalla, en vez de un párrafo largo siempre visible.
def _boton_info(texto, callback):

    btn= QPushButton(texto)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6);
            color: white;
            border: none;
            border-radius: 16px;
            padding: 7px 16px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #7C3AED);
        }
        QPushButton:pressed {
            background: #4338CA;
        }
    """)
    btn.clicked.connect(callback)
    return btn

#Widgets visuales de "mis materias"
#Pastilla con ícono + número animado (cuenta hacia el valor nuevo) + etiqueta.
class PastillaContador(QFrame):

    def __init__(self, icono, color, parent=None):

        super().__init__(parent)
        self.setObjectName("PastillaContadorDocente")
        self._color= color
        self._valor_actual= 0
        fila= QHBoxLayout(self)
        fila.setContentsMargins(13, 6, 15, 6)
        fila.setSpacing(7)
        lbl_icono= QLabel()
        from src.nucleo.iconos_emoji import pixmap_emoji
        lbl_icono.setPixmap(pixmap_emoji(icono, 15))
        lbl_icono.setStyleSheet("background: transparent;")
        fila.addWidget(lbl_icono)
        self.lbl_valor= QLabel("0")
        fuente= self.lbl_valor.font()
        fuente.setBold(True)
        fuente.setPointSize(13)
        self.lbl_valor.setFont(fuente)
        fila.addWidget(self.lbl_valor)
        self.lbl_texto= QLabel("")
        fila.addWidget(self.lbl_texto)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(550)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self.lbl_valor.setText(str(int(v))))

    def poner_texto(self, texto):

        self.lbl_texto.setText(texto)

    def poner_valor(self, nuevo):

        if nuevo == self._valor_actual:
            return
        self._anim.stop()
        self._anim.setStartValue(float(self._valor_actual))
        self._anim.setEndValue(float(nuevo))
        self._valor_actual= nuevo
        self._anim.start()

    def aplicar_paleta(self, bg_panel, borde, txt_sec):

        self.setStyleSheet(f"""
            QFrame#PastillaContadorDocente {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-radius: 15px;
            }}
        """)
        self.lbl_valor.setStyleSheet(f"color: {self._color}; background: transparent;")
        self.lbl_texto.setStyleSheet(f"color: {txt_sec}; font-size: 11px; background: transparent;")

    #Variante translúcida en blanco, para usarse sobre la cabecera con degradado.
    def aplicar_paleta_clara(self):

        self.setStyleSheet("""
            QFrame#PastillaContadorDocente {
                background-color: rgba(255, 255, 255, 40);
                border: none;
                border-radius: 15px;
            }
        """)
        self.lbl_valor.setStyleSheet("color: white; background: transparent;")
        self.lbl_texto.setStyleSheet("color: rgba(255, 255, 255, 210); font-size: 11px; background: transparent;")


#Tarjeta de una materia asignada al docente: código, créditos y estado,
#con acento de color propio y elevación animada al pasar el mouse.
class TarjetaMateria(QFrame):

    def __init__(self, codigo, nombre, creditos, estado, color, parent=None, al_cambiar_color=None):

        super().__init__(parent)
        self.setObjectName("TarjetaMateriaDocente")
        self.setFixedWidth(246)
        self.setFixedHeight(128)
        self._color= color
        self._nombre_materia= nombre or ""
        self._al_cambiar_color= al_cambiar_color
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        if al_cambiar_color:
            self.setToolTip("Clic derecho para cambiar el color de esta materia")
        #Sin QGraphicsDropShadowEffect a propósito: un efecto gráfico permanente obliga a Qt a recomponer esta tarjeta
        #en un buffer aparte en CADA repintado (incluido cada frame del colapso animado del sidebar). El hover se
        #resuelve 100% con QSS (`:hover`), que es prácticamente gratis.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        raiz= QVBoxLayout(self)
        raiz.setContentsMargins(16, 13, 16, 13)
        raiz.setSpacing(6)

        fila_top= QHBoxLayout()
        self.badge= QLabel()
        self.badge.setPixmap(pixmap_emoji("🧑", 20))
        self.badge.setFixedSize(32, 32)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            f"background-color: {_hex_a_rgba(color, 0.20)}; border-radius: 16px; font-size: 14px;")
        fila_top.addWidget(self.badge)
        fila_top.addStretch()
        activa= (estado or "Activa") == "Activa"
        color_estado= "#10B981" if activa else "#94A3B8"
        self.lbl_estado= QLabel(estado or "Activa")
        self.lbl_estado.setStyleSheet(f"""
            background-color: {_hex_a_rgba(color_estado, 0.18)};
            color: {color_estado};
            border-radius: 9px;
            padding: 2px 10px;
            font-size: 10px;
            font-weight: 700;
        """)
        fila_top.addWidget(self.lbl_estado)
        raiz.addLayout(fila_top)

        self.lbl_nombre= QLabel(nombre or "Materia")
        self.lbl_nombre.setWordWrap(True)
        f_nombre= self.lbl_nombre.font()
        f_nombre.setPointSize(12)
        f_nombre.setBold(True)
        self.lbl_nombre.setFont(f_nombre)
        self.lbl_nombre.setStyleSheet("background: transparent;")
        raiz.addWidget(self.lbl_nombre, 1)

        fila_bottom= QHBoxLayout()
        self.lbl_codigo= QLabel(codigo or "—")
        self.lbl_codigo.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 11px; background: transparent;")
        fila_bottom.addWidget(self.lbl_codigo)
        fila_bottom.addStretch()
        #Icono real (pixmap dibujado con QPainter) en vez del emoji 🎓 pegado al texto -antes dependía de la fuente de
        #emoji del sistema operativo y se veía distinto entre equipos.
        self.creditos_contenedor= QWidget()
        self.creditos_contenedor.setStyleSheet("background: transparent;")
        _fila_creditos= QHBoxLayout(self.creditos_contenedor)
        _fila_creditos.setContentsMargins(0, 0, 0, 0)
        _fila_creditos.setSpacing(4)
        lbl__icono_creditos= QLabel()
        lbl__icono_creditos.setPixmap(pixmap_emoji("🎓", 14))
        lbl__icono_creditos.setStyleSheet("background: transparent;")
        _fila_creditos.addWidget(lbl__icono_creditos)
        self.lbl_creditos= QLabel(f"{creditos} créd.")
        self.lbl_creditos.setStyleSheet("background: transparent;")
        _fila_creditos.addWidget(self.lbl_creditos)
        self.creditos_contenedor.setToolTip(
            "Créditos académicos: el 'peso' o valor en horas de estudio que tiene esta materia "
            "dentro del plan de estudios. A más créditos, mayor carga académica representa la "
            "materia (suele influir en el cálculo de promedios ponderados y en la carga horaria "
            "total del estudiante)."
        )
        fila_bottom.addWidget(self.creditos_contenedor)
        raiz.addLayout(fila_bottom)

    def aplicar_paleta(self, bg_panel, borde, txt_prim, txt_sec):

        self._paleta= (bg_panel, borde, txt_prim, txt_sec)
        self._repintar()

    def _repintar(self):

        if not getattr(self, "_paleta", None):
            return
        bg_panel, borde, txt_prim, txt_sec= self._paleta
        self.setStyleSheet(f"""
            QFrame#TarjetaMateriaDocente {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-left: 4px solid {self._color};
                border-radius: 14px;
            }}
            QFrame#TarjetaMateriaDocente:hover {{
                border: 1px solid {self._color};
                border-left: 4px solid {self._color};
            }}
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        self.lbl_nombre.setStyleSheet(f"color: {txt_prim}; background: transparent;")
        self.lbl_creditos.setStyleSheet(f"""
            QLabel {{ color: {txt_sec}; font-size: 11px; background: transparent; }}
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        self.badge.setStyleSheet(
            f"background-color: {_hex_a_rgba(self._color, 0.20)}; border-radius: 16px; font-size: 14px;")
        self.lbl_codigo.setStyleSheet(
            f"color: {self._color}; font-weight: 700; font-size: 11px; background: transparent;")

    #Aplica un nuevo color de acento (personalización guardada por el
    #docente) sin tener que recrear la tarjeta.
    def actualizar_color(self, color):

        self._color= color
        self._repintar()

    def contextMenuEvent(self, evento):

        if not self._al_cambiar_color:
            return
        menu= QMenu(self)
        accion_color= menu.addAction(icono_emoji("🎨"), "Cambiar color de esta materia")
        accion_reset= menu.addAction(icono_emoji("♻"), "Volver al color automático")
        elegida= menu.exec(evento.globalPos())
        if elegida == accion_color:
            dialogo_color= QColorDialog(QColor(self._color), self)
            dialogo_color.setWindowTitle(f"Color para «{self._nombre_materia}»")
            aplicar_icono_ventana(dialogo_color, ICONO_COLOR)
            if dialogo_color.exec() == QDialog.DialogCode.Accepted:
                color_elegido= dialogo_color.selectedColor()
                if color_elegido.isValid():
                    self._al_cambiar_color(self._nombre_materia, color_elegido.name())
        elif elegida == accion_reset:
            self._al_cambiar_color(self._nombre_materia, None)


#Bloque de una clase dentro del horario semanal visual. Color propio por
#materia, se eleva y revela los detalles completos (sección, aula, horas)
#en un tooltip al pasar el mouse, sin necesidad de abrir nada.
class ChipClaseHorario(QFrame):

    def __init__(self, materia, seccion, aula, hora_ini, hora_fin, color, parent=None,
                 clave= None, al_cambiar_color=None, main_window=None):

        super().__init__(parent)
        self.setObjectName("ChipClaseHorario")
        self._color= color
        self._materia= materia
        self._clave= clave if clave is not None else materia
        self._al_cambiar_color= al_cambiar_color
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        hora_ini_fmt= formatear_hora(hora_ini, main_window) if main_window else hora_ini
        hora_fin_fmt= formatear_hora(hora_fin, main_window) if main_window else hora_fin
        #Los tooltips de Qt admiten HTML: el icono del reloj va como imagen
        #incrustada (html_icono_emoji), no como el emoji 🕐 suelto de antes
        #-así se ve igual en todos los sistemas operativos.
        detalle= f"{materia}<br>{seccion or 'Sección no especificada'}<br>{html_icono_emoji('🕐')} {hora_ini_fmt} - {hora_fin_fmt}"
        if aula:
            detalle += f"<br>{html_icono_emoji('📍')} {aula}"
        if al_cambiar_color:
            detalle += "\n Clic derecho para cambiar el color de esta materia"
        self.setToolTip(detalle)

        #Sin QGraphicsDropShadowEffect: con varias decenas de clases en el horario, un efecto por chip forzaría
        #recomponer todas esas capas en cada repintado (incluido cada frame de una animación de la ventana). El hover
        #se resuelve con QSS aclarando el color de fondo, que es prácticamente gratis.
        self._aplicar_color(color)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(8, 5, 5, 5)
        disposicion.setSpacing(1)
        lbl_materia= QLabel(materia)
        lbl_materia.setWordWrap(True)
        fuente= lbl_materia.font()
        fuente.setPointSize(9)
        fuente.setBold(True)
        lbl_materia.setFont(fuente)
        lbl_materia.setStyleSheet("color: white; background: transparent;")
        disposicion.addWidget(lbl_materia)
        texto_detalle= seccion or ""
        if aula:
            texto_detalle= f"{texto_detalle} · {aula}" if texto_detalle else aula
        lbl_detalle= QLabel(texto_detalle)
        lbl_detalle.setWordWrap(True)
        f2= lbl_detalle.font()
        f2.setPointSize(8)
        lbl_detalle.setFont(f2)
        lbl_detalle.setStyleSheet("color: rgba(255,255,255,0.90); background: transparent;")
        disposicion.addWidget(lbl_detalle)
        disposicion.addStretch()

    def _aplicar_color(self, color):

        self._color= color
        color_claro= QColor(color).lighter(122).name()
        self.setStyleSheet(f"""
            QFrame#ChipClaseHorario {{ background-color: {color}; border-radius: 8px; }}
            QFrame#ChipClaseHorario:hover {{ background-color: {color_claro}; }}
        """)

    def contextMenuEvent(self, evento):

        if not self._al_cambiar_color:
            return
        menu= QMenu(self)
        accion_color= menu.addAction(icono_emoji("🎨"), "Cambiar color de esta materia")
        accion_reset= menu.addAction(icono_emoji("♻"), "Volver al color automático")
        elegida= menu.exec(evento.globalPos())
        if elegida == accion_color:
            dialogo_color= QColorDialog(QColor(self._color), self)
            dialogo_color.setWindowTitle(f"Color para «{self._materia}»")
            aplicar_icono_ventana(dialogo_color, ICONO_COLOR)
            if dialogo_color.exec() == QDialog.DialogCode.Accepted:
                color_elegido= dialogo_color.selectedColor()
                if color_elegido.isValid():
                    self._aplicar_color(color_elegido.name())
                    self._al_cambiar_color(self._clave, color_elegido.name())
        elif elegida == accion_reset:
            self._al_cambiar_color(self._clave, None)


#Vista visual del horario semanal del docente: columnas por día, bloques
#de clase posicionados y dimensionados según su hora real. Reemplaza la
#tabla plana por algo que se entiende de un vistazo.
#
#Rendimiento: el fondo (líneas de hora, cabeceras de día) se pinta una sola
#vez por repintado en `paintEvent` (nada de temporizadores); los bloques de
#clase son widgets reales (así el hover/tooltip funciona nativo) que solo
#se recrean cuando cambian los datos, no en cada resize — en un resize solo
#se reposicionan (`_reflow`), que es una operación O(n) muy barata para las
#pocas decenas de clases que tiene el horario de un solo docente.
class PanelHorarioSemanal(QWidget):

    ALTO_POR_HORA= 58
    ANCHO_COL_HORA= 48
    MARGEN_SUP= 30

    def __init__(self, parent=None, main_window=None):

        super().__init__(parent)
        self.main_window= main_window
        self._entradas= []
        self._pares= []
        self._dias_visibles= DIAS_SEMANA[:5]
        self._hora_min= 7 * 60
        self._hora_max= 17 * 60
        self._color_linea= QColor("#E2E8F0")
        self._color_texto= QColor("#64748B")
        self._resolver_color= None
        self._al_color_cambiada= None
        self.setMinimumHeight(300)

    #resolver_color(materia) -> color hex a usar (respeta la
    #personalización local del docente si existe). al_color_cambiada(clave,
    #color_o_None) se llama cuando el docente elige/reinicia un color desde
    #el menú contextual de un chip.
    def configurar_colores(self, resolver_color, al_color_cambiada):

        self._resolver_color= resolver_color
        self._al_color_cambiada= al_color_cambiada

    #Repinta en el acto todos los chips visibles de esta materia, sin
    #reconstruir el panel entero.
    def actualizar_color_materia(self, clave, color):

        for e, chip in self._pares:
            if e["materia"] == clave:
                chip._aplicar_color(color)

    def poner_colores(self, color_linea, color_texto):

        self._color_linea= QColor(color_linea)
        self._color_texto= QColor(color_texto)
        self.update()

    #entradas: lista de dicts con dia, hora_inicio, hora_fin, materia, seccion, aula.
    def poner_entradas(self, entradas):

        self._entradas= entradas
        dias_con_clase= {entrada["dia"] for entrada in entradas if entrada["dia"] in DIAS_SEMANA}
        self._dias_visibles= [d for d in DIAS_SEMANA if d in dias_con_clase] or DIAS_SEMANA[:5]

        minutos= []
        for entrada in entradas:
            ini= _minutos_desde_texto(entrada["hora_inicio"])
            fin= _minutos_desde_texto(entrada["hora_fin"])
            if ini is not None:
                minutos.append(ini)
            if fin is not None:
                minutos.append(fin)
        if minutos:
            self._hora_min= max(0, (min(minutos) // 60) * 60 - 30)
            self._hora_max= ((max(minutos) // 60) + 1) * 60 + 30
        else:
            self._hora_min, self._hora_max= 7 * 60, 17 * 60

        alto_total= self.MARGEN_SUP + int((self._hora_max - self._hora_min) / 60 * self.ALTO_POR_HORA) + 14
        self.setMinimumHeight(max(300, alto_total))
        self._reconstruir_chips()

    def _reconstruir_chips(self):

        for _, chip in self._pares:
            chip.deleteLater()
        self._pares= []
        for entrada in self._entradas:
            if entrada["dia"] not in self._dias_visibles:
                continue
            color= self._resolver_color(entrada["materia"]) if self._resolver_color else _color_para_materia(entrada["materia"])
            chip= ChipClaseHorario(entrada["materia"], entrada["seccion"], entrada["aula"],
                                     entrada["hora_inicio"], entrada["hora_fin"], color, self,
                                     clave= entrada["materia"], al_cambiar_color=self._al_color_cambiada,
                                     main_window= self.main_window)
            chip.show()
            self._pares.append((entrada, chip))
        self._reflow()
        for i, (_, chip) in enumerate(self._pares):
            _animar_entrada_geometria(chip, offset_y=14, duracion=260, retraso=min(i, 12) * 25)
        self.update()

    def resizeEvent(self, evento):

        super().resizeEvent(evento)
        self._reflow()

    def _reflow(self):

        if not self._dias_visibles or self.width() <= 0:
            return
        ancho_disponible= max(60, self.width() - self.ANCHO_COL_HORA - 8)
        cantidad= len(self._dias_visibles)
        ancho_col= ancho_disponible / cantidad
        for e, chip in self._pares:
            try:

                dia_idx= self._dias_visibles.index(e["dia"])
            except ValueError:
                continue
            ini= _minutos_desde_texto(e["hora_inicio"])
            fin= _minutos_desde_texto(e["hora_fin"])
            if ini is None:
                ini= self._hora_min
            if fin is None or fin <= ini:
                fin= ini + 45
            pos_y= self.MARGEN_SUP + int((ini - self._hora_min) / 60 * self.ALTO_POR_HORA)
            h= max(34, int((fin - ini) / 60 * self.ALTO_POR_HORA) - 3)
            pos_x= self.ANCHO_COL_HORA + 8 + dia_idx * ancho_col
            chip.setGeometry(int(pos_x) + 2, pos_y, max(10, int(ancho_col) - 8), h)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._entradas:
            painter.setPen(self._color_texto)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "Aún no tienes clases en tu horario.")
            return

        ancho_disponible= max(60, self.width() - self.ANCHO_COL_HORA - 8)
        cantidad= len(self._dias_visibles)
        ancho_col= ancho_disponible / cantidad

        f_dia= painter.font()
        f_dia.setPointSize(9)
        f_dia.setBold(True)
        painter.setFont(f_dia)
        for i, dia in enumerate(self._dias_visibles):
            pos_x= self.ANCHO_COL_HORA + 8 + i * ancho_col
            painter.setPen(self._color_texto)
            painter.drawText(QRectF(pos_x, 4, ancho_col - 4, 20), Qt.AlignmentFlag.AlignCenter, dia[:3].upper())

        pen_linea= QPen(self._color_linea)
        pen_linea.setWidth(1)
        f_hora= painter.font()
        f_hora.setPointSize(8)
        f_hora.setBold(False)
        painter.setFont(f_hora)
        hora= self._hora_min
        alto_total= int((self._hora_max - self._hora_min) / 60 * self.ALTO_POR_HORA)
        while hora <= self._hora_max:
            pos_y= self.MARGEN_SUP + int((hora - self._hora_min) / 60 * self.ALTO_POR_HORA)
            painter.setPen(pen_linea)
            painter.drawLine(self.ANCHO_COL_HORA, pos_y, self.width(), pos_y)
            painter.setPen(self._color_texto)
            etiqueta= f"{hora // 60:02d}:{hora % 60:02d}"
            painter.drawText(QRectF(0, pos_y - 7, self.ANCHO_COL_HORA - 4, 14),
                              Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, etiqueta)
            hora += 60

        painter.setPen(pen_linea)
        for i in range(cantidad + 1):
            pos_x= self.ANCHO_COL_HORA + 8 + i * ancho_col
            painter.drawLine(int(pos_x), self.MARGEN_SUP - 6, int(pos_x), self.MARGEN_SUP + alto_total)


#Mis materias (solo lectura, filtrado por profesor)
class ModuloMisMaterias(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._tarjetas_materia= []
        self._paleta= None
        self._firma_materias= None
        self._firma_horario= None
        #Colores de materia personalizados por este docente en este equipo (ver datos_locales_docente.py): {clave:
        #(color, color_hv)}.
        self._colores_override= obtener_colores_materias_local(main_window)
        self._construir_ui()
        self._actualizar_textos_politecnico()
        self.refrescar()
        self.actualizar_tema()  #por si el módulo se cargó de forma perezosa, ya con el tema definido
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Mis Materias"
        registrar_atajo(self, self.main_window, "F5", "Actualizar", self.refrescar)

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo). Mismo criterio usado en materias.py,
    #estudiantes.py y banco_tareas.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #Ajusta el subtítulo y el mensaje de "sin materias" para que también
    #mencionen los módulos técnicos cuando la institución es Politécnico —
    #esta pantalla ya mezcla materias académicas y módulos técnicos del
    #docente (misma consulta, sin filtrar por modelo_evaluacion), así que
    #solo cambia el texto, igual que hace materias.py.
    def _actualizar_textos_politecnico(self):

        es_poli= self._es_politecnico()
        self.lbl_subtitulo_cabecera.setText(
            "Tus materias y módulos técnicos asignados, con tu horario de un vistazo más abajo."
            if es_poli else "Tus materias asignadas, con tu horario de un vistazo más abajo.")
        self.lbl_vacio_materias.setText(
            "Aún no tienes materias ni módulos técnicos asignados. En cuanto Coordinación/Dirección"
            "te asigne uno, aparecerá aquí automáticamente."
            if es_poli else
            "Aún no tienes materias asignadas. En cuanto Coordinación/Dirección te asigne una,"
            "aparecerá aquí automáticamente.")

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

        #--- Cabecera tipo "hero": icono + título + descripción + contadores ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("💡", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Mis Materias")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        fila_titulo_punto= QHBoxLayout()
        fila_titulo_punto.setSpacing(8)
        self.lbl_titulo_cabecera= QLabel("Mis Materias")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        fila_titulo_punto.addWidget(self.lbl_titulo_cabecera)
        self.punto_vivo= PuntoPulso("#22C55E", 9, self)
        self.punto_vivo.setToolTip("Datos en vivo desde tu ficha de profesor")
        fila_titulo_punto.addWidget(self.punto_vivo)
        fila_titulo_punto.addStretch()
        bloque_titulo_cabecera.addLayout(fila_titulo_punto)
        self.lbl_subtitulo_cabecera= QLabel(
            "Tus materias asignadas, con tu horario de un vistazo más abajo.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        self.pastilla_materias= PastillaContador("📘", "#8B5CF6", self)
        self.pastilla_materias.poner_texto("materias")
        cabecera_layout.addWidget(self.pastilla_materias)
        self.pastilla_clases= PastillaContador("📅", "#3B82F6", self)
        self.pastilla_clases.poner_texto("clases/semana")
        cabecera_layout.addWidget(self.pastilla_clases)
        cabecera_layout.addWidget(_boton_info("¿Qué es esto?", self._mostrar_info))
        disposicion.addWidget(self.frame_cabecera)


        self.contenedor_materias= QWidget()
        FlowLayout(self.contenedor_materias, margin=0, spacing=14)
        disposicion.addWidget(self.contenedor_materias)

        self.lbl_vacio_materias= QLabel(
            "Aún no tienes materias asignadas. En cuanto Coordinación/Dirección te asigne una,"
            "aparecerá aquí automáticamente.")
        self.lbl_vacio_materias.setObjectName("DescModulo")
        self.lbl_vacio_materias.setWordWrap(True)
        self.lbl_vacio_materias.setVisible(False)
        disposicion.addWidget(self.lbl_vacio_materias)

        lbl_horario= QLabel("Mi Horario de Clases")
        lbl_horario.setObjectName("DescModulo")
        disposicion.addWidget(lbl_horario)

        self.panel_horario= PanelHorarioSemanal(main_window=self.main_window)
        self.panel_horario.configurar_colores(self._color_efectiva, self._cambiar_color_materia)
        disposicion.addWidget(self.panel_horario)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    def _mostrar_info(self):

        texto_materias= "las materias y módulos técnicos que impartes" if self._es_politecnico()\
            else "las materias que impartes"
        mostrar_mensaje("info", "Mis Materias",
            f"Aquí ves {texto_materias} actualmente, con tus secciones y tu horario asignado.\n\n"
            "Esta pantalla es solo de consulta: para crear una materia nueva, cambiarte de sección o "
            "ajustar tu horario oficial, contacta a Coordinación/Dirección.\n\n"
            "¿Quieres anotar una clase que aún no aparece aquí? Puedes hacerlo desde el módulo "
            "Horario, en tu panel de clases locales.", self)

    #Color a usar para una materia: el que personalizó el docente
    #(guardado localmente en este equipo) si existe, o si no, el
    #automático de siempre.
    def _color_efectiva(self, materia):

        override= self._colores_override.get(materia)
        return (override[0] if override and override[0] else None) or _color_para_materia(materia)

    #Callback del menú contextual de un chip del horario: guarda (o
    #borra) la personalización y repinta en el acto la tarjeta de esa
    #materia y todos sus chips, sin recargar nada de la base de datos.
    def _cambiar_color_materia(self, clave, color_hex):

        if color_hex is None:
            eliminar_color_materia_local(self.main_window, clave)
            self._colores_override.pop(clave, None)
        else:
            color_hv= QColor(color_hex).lighter(122).name()
            guardar_color_materia_local(self.main_window, clave, color_hex, color_hv)
            self._colores_override[clave]= (color_hex, color_hv)
        nuevo_color= self._color_efectiva(clave)
        for tarjeta in self._tarjetas_materia:
            if tarjeta._nombre_materia == clave:
                tarjeta.actualizar_color(nuevo_color)
        self.panel_horario.actualizar_color_materia(clave, nuevo_color)

    def refrescar(self):

        profesor_id= obtener_profesor_id(self.main_window)
        conn= obtener_conexion()
        c= conn.cursor()
        if profesor_id is None:
            self._firma_materias= None
            self._firma_horario= None
            self._poblar_materias([])
            self.panel_horario.poner_entradas([])
            self.pastilla_materias.poner_valor(0)
            self.pastilla_clases.poner_valor(0)
            conn.close()
            return
        c.execute("""SELECT DISTINCT materias.codigo, materias.nombre, materias.creditos, materias.estado
                     FROM materias
                     LEFT JOIN materia_profesores ON materia_profesores.materia_id = materias.id
                     WHERE materias.profesor_id=? OR materia_profesores.profesor_id=?
                     ORDER BY materias.nombre""", (profesor_id, profesor_id))
        filas= c.fetchall()

        c.execute("""SELECT DISTINCT horarios.dia, horarios.hora_inicio, horarios.hora_fin,
                     materias.nombre as materia_nombre,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     aulas.nombre as aula_nombre
                     FROM horarios
                     LEFT JOIN materias ON horarios.materia_id = materias.id
                     LEFT JOIN materia_profesores ON materia_profesores.materia_id = materias.id
                     LEFT JOIN secciones ON horarios.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN aulas ON horarios.aula_id = aulas.id
                     WHERE materias.profesor_id=? OR materia_profesores.profesor_id=?
                     ORDER BY horarios.dia, horarios.hora_inicio""", (profesor_id, profesor_id))
        filas_h= c.fetchall()
        conn.close()

        #Rendimiento: `refrescar()` corre cada vez que se navega a este módulo desde el sidebar, no solo la primera
        #vez. La mayoría de esas veces los datos no cambiaron desde la última visita, así que comparamos una "firma"
        #liviana antes de reconstruir tarjetas/horario — si nada cambió, no se recrea ni un solo widget (ni se repiten
        #las animaciones de entrada).
        firma_materias= tuple((fila["codigo"], fila["nombre"], fila["creditos"], fila["estado"]) for fila in filas)
        if firma_materias != self._firma_materias:
            self._firma_materias= firma_materias
            self._poblar_materias(filas)

        entradas= [{
            "dia": f["dia"], "hora_inicio": f["hora_inicio"], "hora_fin": f["hora_fin"],
            "materia": f["materia_nombre"] or "Clase", "seccion": f["seccion_nombre"] or "",
            "aula": f["aula_nombre"] or "",
        } for f in filas_h]
        firma_horario= tuple(tuple(entrada.values()) for entrada in entradas)
        if firma_horario != self._firma_horario:
            self._firma_horario= firma_horario
            self.panel_horario.poner_entradas(entradas)

        self.pastilla_materias.poner_valor(len(filas))
        self.pastilla_clases.poner_valor(len(entradas))

    def _poblar_materias(self, filas):

        flow= self.contenedor_materias.layout()
        for tarjeta in self._tarjetas_materia:
            flow.removeWidget(tarjeta)
            tarjeta.deleteLater()
        self._tarjetas_materia= []

        hay_datos= len(filas) > 0
        self.lbl_vacio_materias.setVisible(not hay_datos)
        self.contenedor_materias.setVisible(hay_datos)

        for fila in filas:
            color= self._color_efectiva(fila["nombre"])
            tarjeta= TarjetaMateria(fila["codigo"], fila["nombre"], fila["creditos"] or 0, fila["estado"], color,
                                      self.contenedor_materias, al_cambiar_color=self._cambiar_color_materia)
            flow.addWidget(tarjeta)
            tarjeta.show()
            self._tarjetas_materia.append(tarjeta)
            if self._paleta:
                tarjeta.aplicar_paleta(*self._paleta)
        QTimer.singleShot(20, self._animar_entrada_materias)

    def _animar_entrada_materias(self):

        for i, tarjeta in enumerate(self._tarjetas_materia):
            _animar_entrada_geometria(tarjeta, offset_y=18, duracion=280, retraso=min(i, 10) * 40)

    def actualizar_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
        idx= 1 if getattr(mw, "modo_oscuro", True) else 0

        bg_panel= paleta["display_bg"][idx]
        bg_borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]

        self._paleta= (bg_panel, bg_borde, txt_prim, txt_sec)
        for tarjeta in self._tarjetas_materia:
            tarjeta.aplicar_paleta(*self._paleta)
        self.pastilla_materias.aplicar_paleta_clara()
        self.pastilla_clases.aplicar_paleta_clara()
        self.panel_horario.poner_colores(bg_borde, txt_sec)

        accent= paleta["btn_op_bg"][idx]
        accent_hv= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {accent_hv});
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
#Copias de seguridad (vista simplificada)
class ModuloCopiasSeguridadDocente(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._construir_ui()
        self.refrescar()
        #Igual que en Mis Materias: si este módulo se carga de forma
        #perezosa (no en el arranque), hay que pintar la cabecera con el
        #tema ya definido; si no, se queda sin el degradado "bonito" hasta que el usuario cambie de tema manualmente.
        self.actualizar_tema()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        #Este módulo (pese a vivir en docente.py) es exclusivo de roles gerenciales -ver main.py, que solo lo agrega al
        #menú si rol_actual está en ROLES_GERENCIALES-, así que aquí no aplica ninguna restricción de Modo Docente.
        self._titulo_modulo_atajos= "Copias de Seguridad"
        registrar_atajo(self, self.main_window, "Ctrl+B", "Crear backup ahora", self._crear_backup)
        registrar_atajo(self, self.main_window, "Ctrl+I", "Importar estudiantes y cursos",
                         self._importar_datos)
    def _construir_ui(self):

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(14)

        #--- Cabecera tipo "hero": icono + título + descripción ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("💡", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Copias de Seguridad")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Copias de Seguridad")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Crea backups manuales e importa el paquete de estudiantes y cursos que te asignó Dirección.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        cabecera_layout.addWidget(_boton_info("¿Qué es esto?", self._mostrar_info))
        disposicion.addWidget(self.frame_cabecera)

        self.lbl_estado= QLabel("")
        self.lbl_estado.setObjectName("DescModulo")
        disposicion.addWidget(self.lbl_estado)
        fila= QHBoxLayout()
        btn_crear= QPushButton("Crear Backup Ahora")
        btn_crear.setIcon(icono_emoji("➕"))
        btn_crear.setIconSize(_QSize_emoji(16, 16))
        btn_crear.setObjectName("BtnAccionAgregar")
        btn_crear.clicked.connect(self._crear_backup)
        fila.addWidget(btn_crear)
        fila.addStretch()
        disposicion.addLayout(fila)

        linea= QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        disposicion.addWidget(linea)
        disposicion.addWidget(self._titulo_seccion("Estudiantes y Cursos"))
        fila_import= QHBoxLayout()
        btn_importar= QPushButton("Importar Estudiantes y Cursos")
        btn_importar.setIcon(icono_emoji("\uE001"))
        btn_importar.setIconSize(_QSize_emoji(16, 16))
        btn_importar.setObjectName("BtnAccionAjustar")
        btn_importar.clicked.connect(self._importar_datos)
        fila_import.addWidget(btn_importar)
        fila_import.addStretch()
        disposicion.addLayout(fila_import)

        disposicion.addStretch()

    def _mostrar_info(self):

        mostrar_mensaje("info", "Copias de Seguridad · Modo Docente",
            "Backup manual: crea una copia de seguridad de la base de datos desde este equipo cuando"
            "quieras. La configuración de backup automático (modo y carpeta institucional) la define "
            "Dirección/Coordinación desde Configuración.\n\n"
            "Importar Estudiantes y Cursos: trae el paquete de estudiantes, secciones y materias que "
            "Dirección/Coordinación/Administración exportó para ti. No puedes crear cursos ni elegir qué "
            "estudiantes pertenecen a cada uno: solo puedes traer lo que ya fue configurado para ti.\n\n"
            "Tranquilo: si has personalizado datos en 'Mis Estudiantes' (Modo Docente), esas "
            "personalizaciones se guardan aparte y NO se pierden al reimportar.", self)

    def _titulo_seccion(self, texto):

        lbl= QLabel(texto)
        lbl.setObjectName("DescModulo")
        return lbl

    def _importar_datos(self):

        importar_paquete_docente(self.main_window, self)

    def _crear_backup(self):

        try:

            cfg= obtener_config_backup()
            ruta= crear_backup(cfg["carpeta"] or None, tipo="Manual (Modo Docente)",
                               usuario= self.main_window.usuario_actual)
            registrar_auditoria("Seguridad", "Creó backup (Modo Docente)", self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Backup creado", f"Copia de seguridad guardada en:\n{ruta}", self)
            self.refrescar()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo crear el backup:\n{error}", self)
    def refrescar(self):

        cfg= obtener_config_backup()
        texto= f"Último backup: {cfg['ultima_fecha']}" if cfg["ultima_fecha"] else "Aún no se ha creado ningún backup."
        if cfg["carpeta"]:
            texto += f"\nCarpeta adicional configurada: {cfg['carpeta']}"
        self.lbl_estado.setText(texto)
    def actualizar_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
        idx= 1 if getattr(mw, "modo_oscuro", True) else 0
        accent= paleta["btn_op_bg"][idx]
        accent_hv= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {accent_hv});
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