import csv, json, reportlab, unicodedata
from datetime import datetime
from src.nucleo.formato_hora import aplicar_formato_widget_fecha, formatear_fecha_hora
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit, QMessageBox, QProgressBar,
QDoubleSpinBox, QFileDialog, QScrollArea, QFrame, QGraphicsOpacityEffect,
QGraphicsDropShadowEffect, QSizePolicy, QLineEdit, QDialog, QGridLayout)
from PySide6.QtCore import Qt, QDate, QPropertyAnimation, QEasingCurve, Property, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from src.nucleo.bd import obtener_conexion, registrar_auditoria, mostrar_columna_numero_lista
from src.nucleo.iconos import mostrar_mensaje, centrar_y_al_frente, aplicar_icono_cabecera
from src.nucleo.permisos import puede_editar, obtener_secciones_permitidas, obtener_materias_permitidas
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo, interseccion_opcional)
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         agregar_boton_detalle, agregar_boton_pantalla_completa)
from src.interfaz.configuracion import TabWidgetNavegable, conectar_tooltip_seleccion
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, quitar_emojis_texto,
                          icono_boton_filtro, pixmap_boton_filtro,
                          EMOJI_EXCUSADO, EMOJI_LICENCIA_MEDICA, EMOJI_PERMISO,
                          EMOJI_SECCIONES_GRUPOS)

ESTADOS_ASISTENCIA= ["Presente", "Ausente", "Tardanza", "Excusado", "Licencia Médica", "Permiso"]
UMBRAL_INASISTENCIA_DEFECTO= 25.0

#Colores semánticos por estado. Se usan como "acento" tanto en modo claro como oscuro (fondos traslúcidos +
#texto en el propio color), así que no dependen del tema activo.
COLORES_ESTADO= {
    "Presente": "#22C55E",
    "Ausente": "#EF4444",
    "Tardanza": "#F59E0B",
    "Excusado": "#3B82F6",
    "Licencia Médica": "#8B5CF6",
    "Permiso": "#06B6D4",
}
ICONOS_ESTADO= {
    "Presente": "✅", "Ausente": "❌", "Tardanza": "🕐", "Excusado": EMOJI_EXCUSADO,
    "Licencia Médica": EMOJI_LICENCIA_MEDICA, "Permiso": EMOJI_PERMISO,
}

#Valores configurables de asistencia Cada estado (Presente, Ausente, Tardanza, Excusado, Licencia Médica,
#Permiso...) se clasifica en una de estas 4 CATEGORÍAS DE CONTEO, que es lo que realmente determina cómo afecta
#las estadísticas (tarjetas de resumen, % de asistencia del grupo y el informe de riesgo de inasistencia). Por
#ejemplo, por predeterminado "Presente" cuenta como día asistido y "Excusado" no cuenta para nada — pero esto
#es AJUSTABLE desde el botón ⚙️ junto al resumen.
CATEGORIAS_CONTEO= ["Presente", "Ausente", "Tardanza", "Neutro"]

ETIQUETA_CATEGORIA= {
    "Presente": "Cuenta como Presente",
    "Ausente": "Cuenta como Ausente",
    "Tardanza": "Cuenta como Tardanza",
    "Neutro": "No cuenta (no afecta el % de asistencia)",
}

#Bucket usado por las 4 tarjetas de resumen (icono, color y etiqueta visible).
ICONO_CATEGORIA= {"Presente": "✅", "Ausente": "❌", "Tardanza": "🕐", "Neutro": "📄"}
COLOR_CATEGORIA= {"Presente": "#22C55E", "Ausente": "#EF4444", "Tardanza": "#F59E0B", "Neutro": "#3B82F6"}
TITULO_CATEGORIA= {"Presente": "Presentes", "Ausente": "Ausentes", "Tardanza": "Tardanzas", "Neutro": "Justificados"}

#Clasificación predeterminada de cada estado. El usuario puede reasignarla libremente desde el diálogo de
#configuración; esto es solo el punto de partida y lo que se recupera al presionar "Restablecer valores
#predeterminados".
VALORES_ESTADO_DEFECTO= {
    "Presente": "Presente",
    "Ausente": "Ausente",
    "Tardanza": "Tardanza",
    "Excusado": "Neutro",
    "Licencia Médica": "Neutro",
    "Permiso": "Neutro",
}


def cargar_valores_estado():
    """Lee de la BD la clasificación de estados configurada por el usuario y la
    completa con los valores predeterminados para cualquier estado nuevo que
    todavía no tenga un valor guardado (ej. si se agregó un estado en una
    actualización posterior). Nunca falla: ante cualquier problema devuelve
    los valores predeterminados."""
    valores= dict(VALORES_ESTADO_DEFECTO)
    try:
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT valores_estados_asistencia FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        crudo= fila["valores_estados_asistencia"] if fila else ""
        if crudo:
            guardado= json.loads(crudo)
            for estado in ESTADOS_ASISTENCIA:
                if estado in guardado and guardado[estado] in CATEGORIAS_CONTEO:
                    valores[estado]= guardado[estado]
    except Exception:
        pass
    return valores


def guardar_valores_estado(valores):
    """Persiste la clasificación de estados (dict estado -> categoría) en la BD."""
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE configuracion SET valores_estados_asistencia=? WHERE id=1",
              (json.dumps(valores, ensure_ascii=False),))
    conn.commit()
    conn.close()

_DIAS_ES= ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES= ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _acortar_placeholder_combo(combo, texto):
    """Reemplaza el texto del placeholder (ítem 0, sin dato asociado) de un
    combo de Curso/Sección poblado por filtros_curso_seccion.poblar_combo_curso /
    cascada_seccion_por_curso. Es un ajuste puramente visual y LOCAL a este
    módulo (Asistencia): no modifica filtros_curso_seccion.py, así que el resto
    de la app sigue mostrando el placeholder largo original. Si el ítem 0 ya
    tiene un curso/sección real seleccionado (no es placeholder), no se toca."""
    if combo.count() > 0 and combo.itemData(0) is None:
        combo.setItemText(0, texto)


def _fecha_larga_es(qdate):
    """Formatea una QDate en español ('martes 4 de agosto') sin depender de la
    configuración regional del sistema."""
    return f"{_DIAS_ES[qdate.dayOfWeek() - 1]} {qdate.day()} de {_MESES_ES[qdate.month() - 1]}"


def _normalizar(texto):
    """Quita mayúsculas y acentos para que el buscador no sea estricto:
    'jose', 'José' y 'JOSÉ' encuentran lo mismo (mismo criterio que configuracion.py)."""
    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", str(texto))
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower()


class IconoLupa(QWidget):
    """Icono de lupa dibujado a mano con QPainter para la barra de búsqueda
    (mismo diseño que configuracion.py)."""

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


def _etiqueta_con_icono(texto, emoji, size=15):
    """Etiqueta de formulario con un pequeño icono (dibujado con QPainter vía
    pixmap_emoji, igual que el resto de iconos del módulo) delante del texto."""
    contenedor= QWidget()
    lay= QHBoxLayout(contenedor)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lbl_icono= QLabel()
    lbl_icono.setPixmap(pixmap_emoji(emoji, size))
    lay.addWidget(lbl_icono)
    lay.addWidget(QLabel(texto))
    return contenedor


def _hex_a_rgb(color_hex):
    color_hex= color_hex.lstrip("#")
    return ",".join(str(int(color_hex[i:i + 2], 16)) for i in (0, 2, 4))


def _hex_a_rgba(color_hex, alpha):
    """Convierte un color '#RRGGBB' a una cadena rgba(...) con la opacidad indicada."""
    color_hex= (color_hex or "#2563EB").lstrip("#")
    r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _colores_tema(main_window):
    """Lee la paleta/tema activo de la ventana principal para que las tarjetas de
    este módulo respeten el tema y el modo claro/oscuro que el usuario ya eligió."""
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


def _boton_estado_color(texto, color, callback):
    """Botón tipo 'chip' con el color del estado, usado en 'Marcar todos: X'."""
    btn= QPushButton(texto)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    rgb= _hex_a_rgb(color)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: rgba({rgb}, 34);
            color: {color};
            border: 1px solid rgba({rgb}, 130);
            border-radius: 9px;
            padding: 7px 14px;
            font-weight: 700;
        }}
        QPushButton:hover {{ background-color: rgba({rgb}, 60); }}
        QPushButton:pressed {{ background-color: rgba({rgb}, 95); }}
    """)
    if callback is not None:
        btn.clicked.connect(callback)
    return btn


#Widgets animados reutilizables
class BarraAnimada(QProgressBar):
    """QProgressBar cuyo valor se desliza suavemente hacia el nuevo valor en vez
    de saltar de golpe. El texto '%p%' se actualiza solo, cuadro a cuadro."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animacion= QPropertyAnimation(self, b"value", self)
        self._animacion.setDuration(420)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)

    def poner_valor_animado(self, valor):
        self._animacion.stop()
        self._animacion.setStartValue(self.value())
        self._animacion.setEndValue(valor)
        self._animacion.start()


class ContadorAnimado(QLabel):
    """QLabel numérica que anima el conteo (efecto 'odómetro') al cambiar de valor."""

    def __init__(self, sufijo="", parent=None):
        super().__init__(parent)
        self._valor= 0
        self._sufijo= sufijo
        self._valor_objetivo= 0
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
        self.setText(f"{self._valor}{self._sufijo}")

    def establecer(self, valor):
        #Importante: comparamos contra el ÚLTIMO VALOR OBJETIVO pedido, no contra el valor instantáneo (a medio
        #animar). Si comparáramos contra self._valor, una animación en curso podría "pasar" casualmente por el nuevo
        #valor pedido a mitad de camino y esta función abandonaría sin redirigirla, dejándola terminar en el valor
        #VIEJO en vez del nuevo.
        if self._valor_objetivo == valor:
            return
        self._valor_objetivo= valor
        self._animacion.stop()
        self._animacion.setStartValue(self._valor)
        self._animacion.setEndValue(valor)
        self._animacion.start()


class TarjetaEstadistica(QFrame):
    """Tarjeta compacta de resumen (icono + número animado + etiqueta) con una
    ligera 'elevación' animada al pasar el mouse por encima."""

    def __init__(self, icono, titulo, color, parent=None):
        super().__init__(parent)
        self.setObjectName("TarjetaEstadistica")
        self._color= color
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.aplicar_paleta("#FFFFFF", "#E2E8F0", "#64748B")

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setBlurRadius(14)
        self._sombra.setOffset(0, 2)
        self._sombra.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(self._sombra)
        self._anim_sombra= QPropertyAnimation(self._sombra, b"blurRadius", self)
        self._anim_sombra.setDuration(160)

        layout= QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(1)

        lbl_icono= QLabel()
        lbl_icono.setPixmap(pixmap_emoji(icono, 24))
        layout.addWidget(lbl_icono)

        self.contador= ContadorAnimado()
        self.contador.setStyleSheet(f"font-size: 23px; font-weight: 800; color: {color};")
        layout.addWidget(self.contador)

        lbl_titulo= QLabel(titulo)
        lbl_titulo.setObjectName("DescModulo")
        lbl_titulo.setStyleSheet("font-size: 11px; font-weight: 600;")
        layout.addWidget(lbl_titulo)

    def aplicar_paleta(self, bg_panel, borde, txt_sec):
        """Actualiza los colores de la tarjeta para coincidir con el tema activo.
        El color semántico (verde/rojo/etc.) del borde izquierdo y del número
        no cambia: es el que distingue cada estado de un vistazo."""
        self.setStyleSheet(f"""
            QFrame#TarjetaEstadistica {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-left: 4px solid {self._color};
                border-radius: 12px;
            }}
            QFrame#TarjetaEstadistica QLabel {{ background: transparent; border: none; }}
        """)

    def establecer(self, valor):
        self.contador.establecer(valor)

    def enterEvent(self, event):
        self._animar_sombra(24)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animar_sombra(14)
        super().leaveEvent(event)

    def _animar_sombra(self, destino):
        self._anim_sombra.stop()
        self._anim_sombra.setStartValue(self._sombra.blurRadius())
        self._anim_sombra.setEndValue(destino)
        self._anim_sombra.start()


class DialogoValoresAsistencia(QDialog):
    """Pequeño diálogo de configuración: para cada estado de asistencia
    (Presente, Ausente, Tardanza, Excusado, Licencia Médica, Permiso...)
    permite elegir qué categoría cuenta a la hora de calcular las tarjetas
    de resumen, el % de asistencia del grupo y el informe de riesgo de
    inasistencia. Incluye un botón para restablecer los valores
    predeterminados sin necesidad de ajustarlos uno por uno."""

    def __init__(self, parent, main_window, valores_actuales):
        super().__init__(parent)
        self.main_window= main_window
        self.setWindowTitle("Valores de Asistencia")
        self.setMinimumWidth(460)
        self._combos= {}

        layout= QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        encabezado= QLabel("Valores de Asistencia")
        f= encabezado.font()
        f.setBold(True)
        f.setPointSize(13)
        encabezado.setFont(f)
        layout.addWidget(encabezado)

        info= QLabel(
            "Define qué representa cada estado a la hora de contar la asistencia. "
            "Por ejemplo: 'Presente' cuenta como día asistido, mientras que 'Excusado' "
            "o 'Licencia Médica' pueden no afectar el % de asistencia.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(info)

        grid= QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for fila, estado in enumerate(ESTADOS_ASISTENCIA):
            fila_etiqueta= QHBoxLayout()
            fila_etiqueta.setSpacing(6)
            lbl_icono= QLabel()
            lbl_icono.setPixmap(pixmap_emoji(ICONOS_ESTADO.get(estado, ""), 18))
            fila_etiqueta.addWidget(lbl_icono)
            lbl= QLabel(estado)
            f_lbl= lbl.font()
            f_lbl.setBold(True)
            lbl.setFont(f_lbl)
            fila_etiqueta.addWidget(lbl)
            fila_etiqueta.addStretch()
            grid.addLayout(fila_etiqueta, fila, 0)

            combo= QComboBox()
            for categoria in CATEGORIAS_CONTEO:
                combo.addItem(ETIQUETA_CATEGORIA[categoria], categoria)
            idx= combo.findData(valores_actuales.get(estado, VALORES_ESTADO_DEFECTO.get(estado, "Neutro")))
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            conectar_tooltip_seleccion(combo, f"Cómo cuenta '{estado}' en las estadísticas de asistencia")
            grid.addWidget(combo, fila, 1)
            self._combos[estado]= combo
        layout.addLayout(grid)

        botones= QHBoxLayout()
        btn_restablecer= QPushButton("Restablecer valores predeterminados")
        btn_restablecer.setIcon(icono_emoji("♻"))
        btn_restablecer.setIconSize(_QSize_emoji(16, 16))
        btn_restablecer.setObjectName("BtnAccionNeutro")
        btn_restablecer.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restablecer.clicked.connect(self._restablecer)
        botones.addWidget(btn_restablecer)
        botones.addStretch()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.setObjectName("BtnAccionNeutro")
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.clicked.connect(self.reject)
        botones.addWidget(btn_cancelar)
        btn_guardar= QPushButton("Guardar")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.clicked.connect(self.accept)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

        centrar_y_al_frente(self, parent)

    def _restablecer(self):
        """Solo cambia las selecciones dentro del diálogo (a los valores
        predeterminados); no guarda nada todavía, así el usuario puede
        seguir ajustando o presionar Cancelar para no aplicar el cambio."""
        for estado, combo in self._combos.items():
            idx= combo.findData(VALORES_ESTADO_DEFECTO.get(estado, "Neutro"))
            combo.setCurrentIndex(idx if idx >= 0 else 0)

    def valores(self):
        return {estado: combo.currentData() for estado, combo in self._combos.items()}


#FlowLayout: layout tipo "wrap" (como texto que hace salto de línea). Coloca los widgets uno tras otro y, en
#cuanto ya no caben en el ancho disponible, salta a la fila de abajo — así el contenedor crece en ALTURA (nunca
#empuja el ancho de la ventana ni desborda la pantalla). Es el reemplazo de QHBoxLayout para la barra de chips
#de filtros: con pocos filtros ocupa una sola fila; con muchos, se acomoda solo en 2, 3 o las filas que hagan
#falta, sin romper el layout del módulo.
from PySide6.QtWidgets import QLayout
from PySide6.QtCore import QSize, QRect, QPoint


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing_h=8, spacing_v=8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._spacing_h= spacing_h
        self._spacing_v= spacing_v
        self._items= []

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self):
        return self._spacing_h

    def verticalSpacing(self):
        return self._spacing_v

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._hacer_layout(QRect(0, 0, width, 0), probar=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._hacer_layout(rect, probar=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        tam= QSize()
        for item in self._items:
            tam= tam.expandedTo(item.minimumSize())
        margenes= self.contentsMargins()
        tam += QSize(margenes.left() + margenes.right(), margenes.top() + margenes.bottom())
        return tam

    def _hacer_layout(self, rect, probar):
        margenes= self.contentsMargins()
        ancho_disponible= rect.width() - margenes.left() - margenes.right()
        x= rect.x() + margenes.left()
        y= rect.y() + margenes.top()
        line_height= 0

        for item in self._items:
            tam= item.sizeHint()
            siguiente_x= x + tam.width() + self._spacing_h
            if siguiente_x - self._spacing_h > rect.x() + margenes.left() + ancho_disponible and line_height > 0:
                x= rect.x() + margenes.left()
                y= y + line_height + self._spacing_v
                siguiente_x= x + tam.width() + self._spacing_h
                line_height= 0
            if not probar:
                item.setGeometry(QRect(QPoint(x, y), tam))
            x= siguiente_x
            line_height= max(line_height, tam.height())

        return y + line_height - rect.y() + margenes.bottom()


class ModuloAsistencia(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window= main_window
        #Clasificación estado -> categoría de conteo (Presente/Ausente/Tardanza/
        #Neutro), configurable desde el botón ⚙️ junto al resumen.
        self._valores_estado= cargar_valores_estado()
        self._build_ui()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):
        self._titulo_modulo_atajos= "Asistencia"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Registrar asistencia", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+I", "Generar informe de inasistencia",
                         self._generar_informe_inasistencia)
        #Configurar los "valores de estado" (qué cuenta como Presente/Ausente/ Tardanza) es una decisión institucional,
        #no algo que un docente deba poder tocar desde un atajo — igual que ya oculta/protege el resto de la app para
        #esta clase de ajustes.
        registrar_atajo(self, self.main_window, "Ctrl+Shift+V", "Configurar valores de estado",
                         self._abrir_valores_estado, solo_no_docente=True)

    #Construcción de interfaz
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

        layout.addWidget(self._crear_cabecera())

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        #Qt dibuja de forma nativa una "línea base" que conecta la barra de pestañas con el panel de contenido,
        #independiente de lo que diga el
        #stylesheet (::pane border:none no la quita). Es esa línea recta la
        #que se veía debajo de las pestañas-píldora; se desactiva así.
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                padding: 9px 20px; margin-right: 6px; border-radius: 9px; font-weight: 600;
                background: rgba(127,127,127,20);
                outline: none;
            }
            QTabBar::tab:focus { outline: none; }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6);
                color: white;
            }
            QTabBar::tab:!selected:hover { background: rgba(127,127,127,35); }
        """)
        self.tabs.currentChanged.connect(self._al_cambiar_tab)
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._tab_registro(), "Registro Diario")
        self.tabs.addTab(self._tab_alertas(), "Alertas de Inasistencia")

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        #Entrada suave del módulo al abrirse.
        QTimer.singleShot(0, lambda: self._animar_aparicion(contenido, 380))
        self.actualizar_tema()

    def _crear_cabecera(self):
        self.frame_cabecera= QFrame()
        tarjeta= self.frame_cabecera
        tarjeta.setObjectName("CabeceraAsistencia")
        tarjeta.setStyleSheet("""
            QFrame#CabeceraAsistencia {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(99,102,241,60), stop:1 rgba(139,92,246,32));
                border: 1px solid rgba(139,92,246,90);
                border-radius: 16px;
            }
            QFrame#CabeceraAsistencia QLabel { background: transparent; border: none; }
        """)
        sombra= QGraphicsDropShadowEffect(tarjeta)
        sombra.setBlurRadius(26)
        sombra.setOffset(0, 5)
        sombra.setColor(QColor(76, 29, 149, 90))
        tarjeta.setGraphicsEffect(sombra)
        #Se guarda la referencia para que actualizar_tema() pueda recolorear la sombra según el tema activo. Si no se
        #hace, la sombra queda "morada" fija sin importar el tema/color que elija el usuario (por eso se veía un brillo
        #violeta detrás de una cabecera roja).
        self._sombra_cabecera= sombra

        layout= QHBoxLayout(tarjeta)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(14)

        icono= QLabel()
        icono.setPixmap(pixmap_emoji("✅", 20))
        icono.setStyleSheet("font-size: 28px;")
        aplicar_icono_cabecera(icono, "Asistencia", tamano=28)
        layout.addWidget(icono)

        columna= QVBoxLayout()
        columna.setSpacing(2)
        titulo= QLabel("Asistencia y Registro Diario")
        titulo.setObjectName("TituloCabeceraAsistencia")
        columna.addWidget(titulo)
        subtitulo= QLabel("Registra la asistencia por sección y vigila el ausentismo en tiempo real.")
        subtitulo.setObjectName("SubtituloCabeceraAsistencia")
        columna.addWidget(subtitulo)
        layout.addLayout(columna, 1)

        self.lbl_fecha_hoy= QLabel(_fecha_larga_es(QDate.currentDate()))
        self.lbl_fecha_hoy.setStyleSheet("""
            background-color: rgba(255,255,255,28);
            border-radius: 10px;
            padding: 7px 16px;
            font-weight: 700;
            color: white;
        """)
        layout.addWidget(self.lbl_fecha_hoy, 0, Qt.AlignmentFlag.AlignVCenter)

        return tarjeta

    def _resumen_filtros_texto(self, partes):
        """Arma la línea de resumen ('Curso: 1ro A · Sección: A · …') a partir
        de [(etiqueta, combo_o_texto), ...], omitiendo lo vacío/'Todas'/'Todos'.
        Mismo criterio que usan Calificaciones y Calificaciones Técnicas, para
        que las ventanas de "☰ Filtros" se vean y se comporten igual en
        todos los módulos."""
        trozos= []
        for etiqueta, valor in partes:
            if isinstance(valor, QComboBox):
                if valor.count() == 0 or not valor.isVisible():
                    continue
                texto= valor.currentText().strip()
            else:
                texto= (valor or "").strip()
            if not texto or texto.lower().startswith("todas") or texto.lower().startswith("todos") or texto == "—":
                continue
            trozos.append(f"{etiqueta}: {texto}")
        return "" + " · ".join(trozos) if trozos else ""

    #Chips de filtros activos (versión visual de _resumen_filtros_texto) Cada etiqueta ("Curso", "Sección", etc.)
    #tiene un icono y un color propios, para que la barra de "filtro activo" se lea de un vistazo en vez de ser una
    #sola línea de texto plano pegada con "·".
    _ICONO_CHIP_FILTRO= {
        #Nivel educativo (Primaria/Secundaria...) y Curso (grado) son "etapas escolares": escuela y libros. Sección usa
        #su ficha propia.
        "Nivel": "🏫", "Curso": "📚", "Sección": EMOJI_SECCIONES_GRUPOS, "Materia": "📖",
        #Módulo técnico: herramientas (distinto de la materia académica 📖).
        "Módulo": "🔧",
        #Área Técnica (especialidad del Politécnico): pieza de rompecabezas, mismo icono que ya usa Observaciones para
        #el filtro de especialidad (la llave inglesa 🛠 se confundía con "Herramientas" genéricas). Sin el modificador
        #de variación U+FE0F ("️") al final -con él el texto ya no coincide exactamente con la clave registrada en
        #iconos_emoji.py (que guarda el emoji "pelado"), así que el icono
        #caía al dibujo de respaldo genérico en vez del propio.
        "Área Técnica": "🧩", "Carrera": "🎓", "Fecha": "📅", "Umbral": "🎚",
    }
    _COLOR_CHIP_FILTRO= {
        "Nivel": "#8B5CF6", "Curso": "#3B82F6", "Sección": "#06B6D4", "Materia": "#22C55E",
        "Módulo": "#F97316", "Área Técnica": "#F59E0B", "Carrera": "#EC4899",
        "Fecha": "#64748B", "Umbral": "#F59E0B",
    }

    def _crear_chip_filtro(self, etiqueta, texto):
        """Crea una 'píldora' (icono + texto, fondo traslúcido del color de
        la etiqueta) para representar un filtro activo. Es el reemplazo
        visual de un simple 'Etiqueta: valor' dentro de la barra de resumen."""
        color= self._COLOR_CHIP_FILTRO.get(etiqueta, "#3B82F6")
        icono= self._ICONO_CHIP_FILTRO.get(etiqueta, "🔎")
        chip= QFrame()
        chip.setObjectName("ChipFiltroActivo")
        chip.setStyleSheet(f"""
            #ChipFiltroActivo {{
                background-color: {color}26;
                border: 1px solid {color}55;
                border-radius: 12px;
            }}
        """)
        lay= QHBoxLayout(chip)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(6)
        lbl_icono= QLabel()
        lbl_icono.setPixmap(pixmap_emoji(icono, 14))
        lbl_icono.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(lbl_icono)
        lbl_texto= QLabel(texto)
        lbl_texto.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 12px; background: transparent; border: none;")
        lay.addWidget(lbl_texto)
        return chip

    def _actualizar_chips_filtros(self, contenedor_layout, partes):
        """Vacía `contenedor_layout` y lo repuebla con un chip por cada
        filtro activo en `partes` (mismo formato que _resumen_filtros_texto:
        [(etiqueta, combo_o_texto), ...]). Si no hay ninguno, deja un chip
        neutro indicándolo, para que la barra nunca se vea vacía/rota."""
        while contenedor_layout.count():
            item= contenedor_layout.takeAt(0)
            widget= item.widget()
            if widget is not None:
                widget.deleteLater()

        activos= []
        for etiqueta, valor in partes:
            if isinstance(valor, QComboBox):
                if valor.count() == 0 or not valor.isVisible():
                    continue
                texto= valor.currentText().strip()
            else:
                texto= (valor or "").strip()
            if not texto or texto.lower().startswith("todas") or texto.lower().startswith("todos") or texto == "—":
                continue
            activos.append((etiqueta, f"{etiqueta}: {texto}"))

        if not activos:
            vacio= QLabel("Sin filtros aplicados — mostrando todo")
            vacio.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 12px;")
            contenedor_layout.addWidget(vacio)
        else:
            for etiqueta, texto in activos:
                contenedor_layout.addWidget(self._crear_chip_filtro(etiqueta, texto))

    def _tab_registro(self):
        w= QWidget()
        layout= QVBoxLayout(w)
        layout.setSpacing(14)

        #--- Filtros --- Los combos de filtro (Nivel, Curso, Sección, Materia, Fecha, y los técnicos de Área/Carrera)
        #NO van expandidos en la pestaña: con varios activos a la vez empujaban la tabla y rompían el ancho disponible
        #junto al sidebar (igual que ya se resolvió en Estudiantes). En vez de eso viven dentro de una ventanita aparte
        #que se abre con este botón (ver _construir_dialogo_filtros_registro / _abrir_dialogo_filtros_registro), no
        #modal, para poder dejarla abierta mientras se ajustan los combos y la tabla de atrás se sigue actualizando en
        #vivo.
        fila_filtros_registro= QHBoxLayout()
        fila_filtros_registro.setSpacing(10)
        cont_chips_registro= QWidget()
        self.lay_chips_registro= FlowLayout(cont_chips_registro, margin=0, spacing_h=8, spacing_v=8)
        #Altura máxima ~3 filas de chips (cada chip ronda los 28-30px de alto con su spacing). Si algún día hay más
        #filtros activos que eso, el contenedor no sigue creciendo sin límite: aparece scroll vertical en vez de
        #desbordar/romper el módulo.
        cont_chips_registro.setMaximumHeight(110)
        self._scroll_chips_registro= QScrollArea()
        self._scroll_chips_registro.setWidget(cont_chips_registro)
        self._scroll_chips_registro.setWidgetResizable(True)
        self._scroll_chips_registro.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_chips_registro.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_chips_registro.setMaximumHeight(110)
        self._scroll_chips_registro.setStyleSheet("background: transparent;")
        fila_filtros_registro.addWidget(self._scroll_chips_registro, 1)
        self.btn_filtros_registro= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_registro)
        self.btn_filtros_registro.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_registro.setObjectName("BtnAccionNeutro")
        self.btn_filtros_registro.setToolTip(
            "Abrir panel de filtros (nivel educativo, curso, sección, materia, fecha, "
            "área técnica/carrera)")
        self.btn_filtros_registro.clicked.connect(self._abrir_dialogo_filtros_registro)
        fila_filtros_registro.addWidget(self.btn_filtros_registro)
        layout.addLayout(fila_filtros_registro)

        #Los combos siguen siendo atributos normales del módulo (igual que
        #antes) pero se crean sin insertarlos en ninguna fila visible aquí:
        #se colocan dentro del diálogo, ver _construir_dialogo_filtros_registro.
        self.combo_filtro_nivel= QComboBox()
        self.combo_filtro_nivel.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filtro_nivel.setMinimumContentsLength(14)
        self.combo_filtro_nivel.currentIndexChanged.connect(self._nivel_filtro_registro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel, "Filtrar el listado de Cursos/Secciones por nivel educativo")

        self.combo_curso= QComboBox()
        self.combo_curso.setMinimumWidth(150)
        self.combo_curso.currentIndexChanged.connect(self._curso_registro_cambio)

        self.combo_seccion= QComboBox()
        self.combo_seccion.setMinimumWidth(170)
        self.combo_seccion.currentIndexChanged.connect(self._cargar_lista)

        self.combo_materia= QComboBox()
        self.combo_materia.setMinimumWidth(170)
        conectar_tooltip_seleccion(self.combo_materia,
            "Materia (o Módulo Técnico, en un Politécnico) para la que se toma asistencia")

        self.date_fecha= QDateEdit(calendarPopup=True)
        self.date_fecha.setDate(QDate.currentDate())
        aplicar_formato_widget_fecha(self.date_fecha, self.main_window)
        self.date_fecha.dateChanged.connect(self._cargar_lista)

        #OPTIMIZACIÓN DE LAYOUT: setMinimumWidth() arriba solo fija un PISO. Por defecto un QComboBox también se
        #autoajusta (AdjustToContents) al texto más largo que reciba — y el placeholder de combo_seccion es "Selecciona
        #primero un curso/grado...", un texto largo. Con AdjustToMinimumContentsLengthWithIcon el combo pide un ancho
        #acotado y previsible sin importar qué tan largo sea el placeholder o las opciones cargadas.
        for _combo in (self.combo_curso, self.combo_seccion, self.combo_materia):
            _combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            _combo.setMinimumContentsLength(14)

        #Área Técnica (Politécnico) / Carrera (Universidad): filtran qué estudiantes de la sección elegida se MUESTRAN
        #en la lista (igual que el buscador de nombre); el guardado sigue considerando la sección completa. Solo se
        #muestran (dentro del diálogo) si la institución tiene ese módulo activo -ver _filtro_estudiantes_cambio.
        self.lbl_filtro_especialidad_asis= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_asis= QComboBox()
        self.combo_filtro_especialidad_asis.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filtro_especialidad_asis.setMinimumContentsLength(18)
        self.combo_filtro_especialidad_asis.setMinimumWidth(210)
        self.combo_filtro_especialidad_asis.currentIndexChanged.connect(self._filtro_estudiantes_cambio)
        #Además de filtrar qué estudiantes se muestran, el Área Técnica elegida aquí también acota el combo de Materia
        #(ver _cargar_materias_combo): en un Politécnico, cada módulo/materia pertenece a un área técnica específica,
        #así que al elegir el área el combo de Materia debe limitarse a SUS módulos -no mezclar materias de otras
        #especialidades en la lista de asistencia.
        self.combo_filtro_especialidad_asis.currentIndexChanged.connect(self._cargar_materias_combo)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_asis,
                                    "Filtrar la lista por área técnica del estudiante (Politécnico)")

        self.lbl_filtro_carrera_asis= QLabel("Carrera:")
        self.combo_filtro_carrera_asis= QComboBox()
        self.combo_filtro_carrera_asis.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filtro_carrera_asis.setMinimumContentsLength(18)
        self.combo_filtro_carrera_asis.setMinimumWidth(210)
        self.combo_filtro_carrera_asis.currentIndexChanged.connect(self._filtro_estudiantes_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_asis,
                                    "Filtrar la lista por carrera del estudiante (Universidad)")

        self._construir_dialogo_filtros_registro()

        #--- Resumen del día (tarjetas animadas) --- Las 4 tarjetas representan las CATEGORÍAS de conteo (no los
        #estados literales): "Justificados" agrupa todo lo que el usuario haya marcado como Neutro (Excusado, Licencia
        #Médica, Permiso...) en el botón ⚙️. Envueltas en un QWidget real (self.marco_resumen_asistencia) -y no solo un
        #QHBoxLayout suelto- porque agregar_boton_pantalla_completa (ver más abajo) solo puede mover WIDGETS al diálogo
        #de pantalla completa, no layouts sueltos.
        self.marco_resumen_asistencia= QWidget()
        fila_resumen= QHBoxLayout(self.marco_resumen_asistencia)
        fila_resumen.setContentsMargins(0, 0, 0, 0)
        fila_resumen.setSpacing(12)
        self.tarjeta_presentes= TarjetaEstadistica(
            ICONO_CATEGORIA["Presente"], TITULO_CATEGORIA["Presente"], COLOR_CATEGORIA["Presente"])
        self.tarjeta_ausentes= TarjetaEstadistica(
            ICONO_CATEGORIA["Ausente"], TITULO_CATEGORIA["Ausente"], COLOR_CATEGORIA["Ausente"])
        self.tarjeta_tardanzas= TarjetaEstadistica(
            ICONO_CATEGORIA["Tardanza"], TITULO_CATEGORIA["Tardanza"], COLOR_CATEGORIA["Tardanza"])
        self.tarjeta_excusados= TarjetaEstadistica(
            ICONO_CATEGORIA["Neutro"], TITULO_CATEGORIA["Neutro"], COLOR_CATEGORIA["Neutro"])
        for tarjeta in (self.tarjeta_presentes, self.tarjeta_ausentes, self.tarjeta_tardanzas, self.tarjeta_excusados):
            fila_resumen.addWidget(tarjeta)

        self.btn_valores_estado= QPushButton("")
        self.btn_valores_estado.setIcon(icono_emoji("✅"))
        self.btn_valores_estado.setIconSize(_QSize_emoji(16, 16))
        self.btn_valores_estado.setToolTip(
            "Ajustar qué cuenta cada estado de asistencia (Presente, Ausente, Tardanza o Neutro)")
        self.btn_valores_estado.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_valores_estado.setFixedSize(34, 34)
        self.btn_valores_estado.setStyleSheet("""
            QPushButton {
                background: rgba(127,127,127,0.14);
                border: none;
                border-radius: 17px;
                font-size: 15px;
            }
            QPushButton:hover { background: rgba(127,127,127,0.26); }
            QPushButton:pressed { background: rgba(127,127,127,0.36); }
        """)
        self.btn_valores_estado.clicked.connect(self._abrir_valores_estado)
        fila_resumen.addWidget(self.btn_valores_estado, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.marco_resumen_asistencia)

        #--- Búsqueda de estudiantes (mismo diseño y criterio que configuracion.py) ---
        self.marco_busqueda_estudiantes= QFrame()
        self.marco_busqueda_estudiantes.setStyleSheet(
            "QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda= QHBoxLayout(self.marco_busqueda_estudiantes)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        self.icono_busqueda_estudiantes= IconoLupa()
        lay_busqueda.addWidget(self.icono_busqueda_estudiantes)
        self.in_buscar_estudiantes= QLineEdit()
        limitar_campo_texto(self.in_buscar_estudiantes, 150)
        self.in_buscar_estudiantes.setPlaceholderText("Buscar estudiante por nombre o apellido…")
        self.in_buscar_estudiantes.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_buscar_estudiantes, 1)
        layout.addWidget(self.marco_busqueda_estudiantes)

        #Debounce de 150ms: evita re-filtrar/repintar la tabla en cada tecla cuando se escribe rápido, igual que en
        #configuracion.py.
        self._temporizador_busqueda_estudiantes= QTimer(self)
        self._temporizador_busqueda_estudiantes.setSingleShot(True)
        self._temporizador_busqueda_estudiantes.setInterval(150)
        self._temporizador_busqueda_estudiantes.timeout.connect(self._filtro_estudiantes_cambio)
        self.in_buscar_estudiantes.textChanged.connect(
            lambda _t: self._temporizador_busqueda_estudiantes.start())


        self.tabla= QTableWidget(0, 3)
        aplicar_estructura_tabla(self.tabla)
        self.estado_vacio_registro= EstadoVacioFiltro(self.tabla)

        self.tabla.setHorizontalHeaderLabels(["No.", "Estudiante", "Estado"])
        header= self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(0, 48)
        self.tabla.setColumnWidth(2, 190)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(True)
        self.tabla.setMinimumHeight(380)
        self.tabla.verticalHeader().setVisible(False)
        #Alto de fila fijo: evita medir el contenido de cada fila (resizeRowsToContents) en cada refresco, lo que
        #mantiene la tabla fluida incluso con muchos estudiantes.
        self.tabla.verticalHeader().setDefaultSectionSize(46)
        self.tabla.setStyleSheet("QTableWidget::item:hover { background-color: rgba(127,127,127,30); }")
        layout.addWidget(self.tabla, 1)

        #Paginación (mismo control que el resto de la app)
        self.paginacion_registro= ControlPaginacion()
        self.paginacion_registro.cambio.connect(self._on_cambio_pagina_registro)
        #Envuelta en un QWidget real (self.marco_paginacion_registro) por la misma razón que
        #self.marco_resumen_asistencia arriba: solo widgets pueden entrar a la lista de
        #agregar_boton_pantalla_completa.
        self.marco_paginacion_registro= QWidget()
        fila_paginacion= QHBoxLayout(self.marco_paginacion_registro)
        fila_paginacion.setContentsMargins(0, 0, 0, 0)
        fila_paginacion.addStretch()
        fila_paginacion.addWidget(self.paginacion_registro)
        fila_paginacion.addStretch()
        layout.addWidget(self.marco_paginacion_registro)

        #"Marcar todos": un botón tipo "chip" por estado (como en la versión original). Con los 2 estados nuevos
        #(Licencia Médica, Permiso) ya son 6 en total, así que se acomodan en una cuadrícula de 3 columnas (2 filas) en
        #vez de una sola fila, para que no se desborden. También envuelta en un QWidget real (self.marco_marcar_todos),
        #ver el mismo comentario de arriba.
        self.marco_marcar_todos= QWidget()
        grid_marcar= QGridLayout(self.marco_marcar_todos)
        grid_marcar.setContentsMargins(0, 0, 0, 0)
        grid_marcar.setHorizontalSpacing(8)
        grid_marcar.setVerticalSpacing(8)
        COLUMNAS_MARCAR= 3
        for indice, estado in enumerate(ESTADOS_ASISTENCIA):
            color= COLORES_ESTADO.get(estado, "#6366F1")
            texto= f"Marcar todos: {estado}"
            btn= _boton_estado_color(texto, color, None)
            btn.setIcon(icono_emoji(ICONOS_ESTADO.get(estado, "")))
            btn.setIconSize(_QSize_emoji(16, 16))
            btn.clicked.connect(lambda checked=False, e=estado, b=btn: self._marcar_todos(e, b))
            fila, columna = divmod(indice, COLUMNAS_MARCAR)
            grid_marcar.addWidget(btn, fila, columna)
        layout.addWidget(self.marco_marcar_todos)

        self.barra_porcentaje= BarraAnimada()
        self.barra_porcentaje.setFormat("Asistencia del grupo: %p%")
        self.barra_porcentaje.setToolTip(
            "Calculado solo sobre estudiantes marcados como Presente/Ausente/Tardanza. "
            "Los estados 'Neutro' (Excusado, Licencia Médica, Permiso...) no se cuentan "
            "ni a favor ni en contra — ajustable desde el botón.")
        self.barra_porcentaje.setFixedHeight(26)
        layout.addWidget(self.barra_porcentaje)

        btn_guardar= QPushButton("Guardar Registro de Asistencia")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(btn_guardar)
        self._btn_guardar= btn_guardar

        #Botón ⛶ de pantalla completa: en pantalla completa solo se llevan el buscador, la tabla, la paginación y
        #"Guardar" -los marcadores "Marcar todos", las tarjetas de resumen y la barra de % del grupo se quedan en la
        #vista normal, para que la tabla ocupe toda la altura posible en el diálogo maximizado.
        agregar_boton_pantalla_completa(
            None,
            [self.marco_busqueda_estudiantes, self.tabla,
             self.marco_paginacion_registro, self._btn_guardar],
            titulo="Asistencia", parent=self)

        return w

    def _tab_alertas(self):
        w= QWidget()
        layout= QVBoxLayout(w)
        layout.setSpacing(14)
        info= QLabel("El sistema calcula automáticamente el % de inasistencia (Ausente + Tardanza) "
                      "por estudiante y marca en alerta a quienes superen el umbral configurado.")
        info.setObjectName("DescModulo")
        info.setWordWrap(True)
        layout.addWidget(info)

        #--- Filtros --- Mismo criterio que en Registro Diario: los combos (Área Técnica/ Carrera, Nivel Educativo,
        #Curso, Sección, Umbral) viven dentro de una ventanita aparte que se abre con este botón (ver
        #_construir_dialogo_filtros_alertas / _abrir_dialogo_filtros_alertas), no modal, para no desbordar la pestaña
        #ni empujar la tabla.
        fila_filtros_alertas= QHBoxLayout()
        fila_filtros_alertas.setSpacing(10)
        cont_chips_alertas= QWidget()
        self.lay_chips_alertas= FlowLayout(cont_chips_alertas, margin=0, spacing_h=8, spacing_v=8)
        cont_chips_alertas.setMaximumHeight(110)
        self._scroll_chips_alertas= QScrollArea()
        self._scroll_chips_alertas.setWidget(cont_chips_alertas)
        self._scroll_chips_alertas.setWidgetResizable(True)
        self._scroll_chips_alertas.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_chips_alertas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_chips_alertas.setMaximumHeight(110)
        self._scroll_chips_alertas.setStyleSheet("background: transparent;")
        fila_filtros_alertas.addWidget(self._scroll_chips_alertas, 1)
        self.btn_filtros_alertas= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_alertas)
        self.btn_filtros_alertas.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_alertas.setObjectName("BtnAccionNeutro")
        self.btn_filtros_alertas.setToolTip(
            "Abrir panel de filtros (área técnica/carrera, nivel educativo, curso, "
            "sección, umbral de alerta)")
        self.btn_filtros_alertas.clicked.connect(self._abrir_dialogo_filtros_alertas)
        fila_filtros_alertas.addWidget(self.btn_filtros_alertas)

        btn_generar= QPushButton("Generar Informe Automático")
        btn_generar.setIcon(icono_emoji("📊"))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAjustar")
        btn_generar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_generar.clicked.connect(self._generar_informe_inasistencia)
        fila_filtros_alertas.addWidget(btn_generar)
        layout.addLayout(fila_filtros_alertas)
        self._btn_generar_informe= btn_generar

        #Los combos siguen siendo atributos normales del módulo, creados sin insertarlos en ninguna fila visible aquí:
        #se colocan dentro del diálogo, ver _construir_dialogo_filtros_alertas.
        self.lbl_filtro_especialidad_alerta= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_alerta= QComboBox()
        self.combo_filtro_especialidad_alerta.setMinimumWidth(210)
        self.combo_filtro_especialidad_alerta.currentIndexChanged.connect(self._calcular_inasistencia)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_alerta,
                                    "Filtrar el informe por área técnica (Politécnico)")

        self.lbl_filtro_carrera_alerta= QLabel("Carrera:")
        self.combo_filtro_carrera_alerta= QComboBox()
        self.combo_filtro_carrera_alerta.setMinimumWidth(210)
        self.combo_filtro_carrera_alerta.currentIndexChanged.connect(self._calcular_inasistencia)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_alerta, "Filtrar el informe por carrera (Universidad)")

        self.combo_filtro_nivel_alerta= QComboBox()
        self.combo_filtro_nivel_alerta.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filtro_nivel_alerta.setMinimumContentsLength(14)
        self.combo_filtro_nivel_alerta.currentIndexChanged.connect(self._nivel_filtro_alerta_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel_alerta, "Filtrar el informe por nivel educativo")

        self.spin_umbral= QDoubleSpinBox()
        self.spin_umbral.setRange(1, 100)
        self.spin_umbral.setSuffix(" %")
        self.spin_umbral.setValue(UMBRAL_INASISTENCIA_DEFECTO)

        self.combo_curso_alerta= QComboBox()
        self.combo_curso_alerta.currentIndexChanged.connect(self._curso_alerta_cambio)

        self.combo_seccion_alerta= QComboBox()

        #Mismo ajuste que en Registro Diario: evita que estos combos se inflen con el placeholder largo de
        #poblar_combo_curso / cascada_seccion_por_curso y desborden la ventanita de filtros.
        for _combo in (self.combo_curso_alerta, self.combo_seccion_alerta):
            _combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            _combo.setMinimumContentsLength(14)

        self._construir_dialogo_filtros_alertas()

        self.tabla_alertas= QTableWidget(0, 7)
        aplicar_estructura_tabla(self.tabla_alertas)

        self.tabla_alertas.setHorizontalHeaderLabels(
            ["Estudiante", "Curso", "Sección", "Presentes", "Ausencias/Tardanzas", "% Inasistencia", "Estado"])
        header= self.tabla_alertas.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_alertas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_alertas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_alertas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_alertas.setAlternatingRowColors(True)
        self.tabla_alertas.setWordWrap(True)
        self.tabla_alertas.setMinimumHeight(380)
        self.tabla_alertas.verticalHeader().setVisible(False)
        self.tabla_alertas.verticalHeader().setDefaultSectionSize(42)
        self.tabla_alertas.setStyleSheet("QTableWidget::item:hover { background-color: rgba(127,127,127,30); }")
        layout.addWidget(self.tabla_alertas, 1)

        #Paginación para alertas
        self.paginacion_alertas= ControlPaginacion()
        self.paginacion_alertas.cambio.connect(self._generar_informe_inasistencia)
        layout.addWidget(self.paginacion_alertas)

        self.lbl_resumen_alertas= QLabel("Genera el informe para ver el resumen.")
        self.lbl_resumen_alertas.setObjectName("DescModulo")
        layout.addWidget(self.lbl_resumen_alertas)

        fila_exportar= QHBoxLayout()
        btn_pdf= QPushButton("Exportar Informe (PDF)")
        btn_pdf.setIcon(icono_emoji("\uE002"))
        btn_pdf.setIconSize(_QSize_emoji(16, 16))
        btn_pdf.setObjectName("BtnAccionEditar")
        btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pdf.clicked.connect(self._exportar_informe_pdf)
        fila_exportar.addWidget(btn_pdf)
        btn_csv= QPushButton("Exportar Informe (CSV)")
        btn_csv.setIcon(icono_emoji("\uE002"))
        btn_csv.setIconSize(_QSize_emoji(16, 16))
        btn_csv.setObjectName("BtnAccionNeutro")
        btn_csv.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_csv.clicked.connect(self._exportar_informe_csv)
        fila_exportar.addWidget(btn_csv)
        fila_exportar.addStretch()
        layout.addLayout(fila_exportar)

        return w

    #Ventanas de filtrado (una por pestaña: Registro Diario y Alertas)
    def _construir_dialogo_filtros_registro(self):
        """Crea (una sola vez) la ventanita con los filtros de Registro
        Diario. No es modal: se puede dejar abierta mientras se ajustan
        los combos y la tabla de atrás se sigue actualizando en vivo."""
        self.dialogo_filtros_registro= QDialog(self)
        self.dialogo_filtros_registro.setObjectName("DialogoFiltrosAsis")
        self.dialogo_filtros_registro.setWindowTitle("Filtros de Registro Diario")
        self.dialogo_filtros_registro.setModal(False)
        self.dialogo_filtros_registro.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_registro)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        icono_encabezado= QLabel()
        pixmap_boton_filtro(icono_encabezado, 20)
        icono_encabezado.setObjectName("IconoEncabezadoFiltrosAsis")
        fila_encabezado.addWidget(icono_encabezado)
        titulo_encabezado= QLabel("Filtros")
        titulo_encabezado.setObjectName("TituloEncabezadoFiltrosAsis")
        fila_encabezado.addWidget(titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        subtitulo= QLabel("Elige curso, sección, materia y fecha; la tabla se actualiza al instante.")
        subtitulo.setObjectName("SubtituloFiltrosAsis")
        subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(subtitulo)

        self.linea_separadora_filtros_registro= QFrame()
        self.linea_separadora_filtros_registro.setFrameShape(QFrame.Shape.HLine)
        self.linea_separadora_filtros_registro.setObjectName("SeparadorFiltrosAsis")
        lay_dialogo.addWidget(self.linea_separadora_filtros_registro)

        #'Materia' / 'Módulo Técnico' según el tipo de institución (mismo criterio que Banco de Tareas: en un
        #Politécnico este combo también lista módulos técnicos, así que el label lo refleja).
        self.lbl_materia_registro= QLabel(
            "Materia / Módulo Técnico:" if self._es_politecnico() else "Materia:")
        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            ("Nivel Educativo:", self.combo_filtro_nivel),
            (None, self.combo_filtro_especialidad_asis),  #etiqueta propia: self.lbl_filtro_especialidad_asis
            (None, self.combo_filtro_carrera_asis),        #etiqueta propia: self.lbl_filtro_carrera_asis
            ("Curso:", self.combo_curso),
            ("Sección:", self.combo_seccion),
            (None, self.combo_materia),                    #etiqueta propia: self.lbl_materia_registro
            ("Fecha:", self.date_fecha),
        ):
            if combo is self.combo_filtro_especialidad_asis:
                grid.addWidget(self.lbl_filtro_especialidad_asis, fila, 0)
            elif combo is self.combo_filtro_carrera_asis:
                grid.addWidget(self.lbl_filtro_carrera_asis, fila, 0)
            elif combo is self.combo_materia:
                grid.addWidget(self.lbl_materia_registro, fila, 0)
            elif combo is self.date_fecha:
                grid.addWidget(_etiqueta_con_icono(etiqueta, "📅"), fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar_filtros= QPushButton("Cerrar")
        btn_cerrar_filtros.setIcon(icono_emoji("✖"))
        btn_cerrar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar_filtros.setObjectName("BtnAccionNeutro")
        btn_cerrar_filtros.clicked.connect(self.dialogo_filtros_registro.hide)
        fila_botones.addWidget(btn_cerrar_filtros)
        lay_dialogo.addLayout(fila_botones)

        #Deja a la vista, sin tener que abrir el diálogo, qué se está acotando -mismo criterio que
        #Calificaciones/Calificaciones Técnicas-.
        for combo in (self.combo_filtro_nivel, self.combo_filtro_especialidad_asis,
                      self.combo_filtro_carrera_asis, self.combo_curso, self.combo_seccion,
                      self.combo_materia):
            combo.currentIndexChanged.connect(self._actualizar_resumen_filtros_registro)
        self.date_fecha.dateChanged.connect(self._actualizar_resumen_filtros_registro)
        self._actualizar_resumen_filtros_registro()

    def _etiqueta_chip_materia_registro(self):
        """Etiqueta del chip de materia del Registro Diario: en un Politécnico
        distingue 'Módulo' (módulo técnico, modelo 'Técnica (RA)') de
        'Materia' académica; en el resto de instituciones es siempre 'Materia'."""
        if not self._es_politecnico():
            return "Materia"
        dato= self.combo_materia.currentData()
        if dato is not None and dato in getattr(self, "_materias_tecnicas_asis", set()):
            return "Módulo"
        return "Materia"

    def _actualizar_resumen_filtros_registro(self):
        if not hasattr(self, "lay_chips_registro"):
            return
        self._actualizar_chips_filtros(self.lay_chips_registro, [
            ("Nivel", self.combo_filtro_nivel), ("Curso", self.combo_curso),
            ("Sección", self.combo_seccion),
            (self._etiqueta_chip_materia_registro(), self.combo_materia),
            ("Área Técnica", self.combo_filtro_especialidad_asis),
            ("Carrera", self.combo_filtro_carrera_asis),
            ("Fecha", self.date_fecha.date().toString("yyyy-MM-dd")),
        ])

    def _abrir_dialogo_filtros_registro(self):
        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_registro.parent() is not _fc:
            self.dialogo_filtros_registro.setParent(_fc)
        self.dialogo_filtros_registro.show()
        self.dialogo_filtros_registro.raise_()
        self.dialogo_filtros_registro.activateWindow()

    def _construir_dialogo_filtros_alertas(self):
        """Crea (una sola vez) la ventanita con los filtros de Alertas de
        Inasistencia. No es modal, igual que la de Registro Diario."""
        self.dialogo_filtros_alertas= QDialog(self)
        self.dialogo_filtros_alertas.setObjectName("DialogoFiltrosAsis")
        self.dialogo_filtros_alertas.setWindowTitle("Filtros de Alertas de Inasistencia")
        self.dialogo_filtros_alertas.setModal(False)
        self.dialogo_filtros_alertas.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_alertas)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        icono_encabezado= QLabel()
        pixmap_boton_filtro(icono_encabezado, 20)
        icono_encabezado.setObjectName("IconoEncabezadoFiltrosAsis")
        fila_encabezado.addWidget(icono_encabezado)
        titulo_encabezado= QLabel("Filtros")
        titulo_encabezado.setObjectName("TituloEncabezadoFiltrosAsis")
        fila_encabezado.addWidget(titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        subtitulo= QLabel("Combina los filtros que necesites antes de generar el informe.")
        subtitulo.setObjectName("SubtituloFiltrosAsis")
        subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(subtitulo)

        self.linea_separadora_filtros_alertas= QFrame()
        self.linea_separadora_filtros_alertas.setFrameShape(QFrame.Shape.HLine)
        self.linea_separadora_filtros_alertas.setObjectName("SeparadorFiltrosAsis")
        lay_dialogo.addWidget(self.linea_separadora_filtros_alertas)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            (None, self.combo_filtro_especialidad_alerta),  #etiqueta propia: self.lbl_filtro_especialidad_alerta
            (None, self.combo_filtro_carrera_alerta),        #etiqueta propia: self.lbl_filtro_carrera_alerta
            ("Nivel Educativo:", self.combo_filtro_nivel_alerta),
            ("Curso:", self.combo_curso_alerta),
            ("Sección:", self.combo_seccion_alerta),
            ("Umbral de alerta (% inasistencia):", self.spin_umbral),
        ):
            if combo is self.combo_filtro_especialidad_alerta:
                grid.addWidget(self.lbl_filtro_especialidad_alerta, fila, 0)
            elif combo is self.combo_filtro_carrera_alerta:
                grid.addWidget(self.lbl_filtro_carrera_alerta, fila, 0)
            elif combo is self.spin_umbral:
                grid.addWidget(_etiqueta_con_icono(etiqueta, "🎚"), fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar_filtros= QPushButton("Cerrar")
        btn_cerrar_filtros.setIcon(icono_emoji("✖"))
        btn_cerrar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar_filtros.setObjectName("BtnAccionNeutro")
        btn_cerrar_filtros.clicked.connect(self.dialogo_filtros_alertas.hide)
        fila_botones.addWidget(btn_cerrar_filtros)
        lay_dialogo.addLayout(fila_botones)

        for combo in (self.combo_filtro_especialidad_alerta, self.combo_filtro_carrera_alerta,
                      self.combo_filtro_nivel_alerta, self.combo_curso_alerta, self.combo_seccion_alerta):
            combo.currentIndexChanged.connect(self._actualizar_resumen_filtros_alertas)
        self.spin_umbral.valueChanged.connect(self._actualizar_resumen_filtros_alertas)
        self._actualizar_resumen_filtros_alertas()

    def _actualizar_resumen_filtros_alertas(self):
        if not hasattr(self, "lay_chips_alertas"):
            return
        self._actualizar_chips_filtros(self.lay_chips_alertas, [
            ("Nivel", self.combo_filtro_nivel_alerta), ("Curso", self.combo_curso_alerta),
            ("Sección", self.combo_seccion_alerta),
            ("Área Técnica", self.combo_filtro_especialidad_alerta),
            ("Carrera", self.combo_filtro_carrera_alerta),
            ("Umbral", f"{self.spin_umbral.value():.0f}%"),
        ])

    def _abrir_dialogo_filtros_alertas(self):
        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_alertas.parent() is not _fc:
            self.dialogo_filtros_alertas.setParent(_fc)
        self.dialogo_filtros_alertas.show()
        self.dialogo_filtros_alertas.raise_()
        self.dialogo_filtros_alertas.activateWindow()

    #Animaciones auxiliares
    def _animar_aparicion(self, widget, duracion=240):
        """Fundido de entrada (fade-in) reutilizable para tablas, pestañas y el
        contenido general del módulo."""
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

    def _flash(self, widget):
        """Parpadeo breve de opacidad para dar feedback táctil a un botón (sin
        efectos gráficos persistentes, así que solo se usa en widgets simples)."""
        if widget is None:
            return
        efecto= QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", widget)
        anim.setDuration(240)
        anim.setKeyValueAt(0, 1.0)
        anim.setKeyValueAt(0.5, 0.4)
        anim.setKeyValueAt(1, 1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        widget._anim_flash_ref= anim
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()

    def _al_cambiar_tab(self, indice):
        widget= self.tabs.widget(indice)
        if widget is not None:
            self._animar_aparicion(widget, 220)

    #Alertas: carga de datos
    def _cargar_especialidad_carrera_filtro_alerta(self):
        """Igual que en la pestaña principal (Registro Diario): los combos de
        Área Técnica y Carrera solo se muestran/pueblan si la institución
        tiene ese módulo activo."""
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_alerta.setVisible(es_poli)
        self.combo_filtro_especialidad_alerta.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_alerta.currentData()
            self.combo_filtro_especialidad_alerta.blockSignals(True)
            self.combo_filtro_especialidad_alerta.clear()
            self.combo_filtro_especialidad_alerta.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_alerta.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_alerta.findData(actual)
            self.combo_filtro_especialidad_alerta.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_alerta.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_alerta.setVisible(es_uni)
        self.combo_filtro_carrera_alerta.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_alerta.currentData()
            self.combo_filtro_carrera_alerta.blockSignals(True)
            self.combo_filtro_carrera_alerta.clear()
            self.combo_filtro_carrera_alerta.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_alerta.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_carrera_alerta.findData(actual)
            self.combo_filtro_carrera_alerta.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_alerta.blockSignals(False)

    def _cargar_secciones_alerta(self):
        permitidas= self._secciones_permitidas_con_nivel_alerta()
        poblar_combo_curso(self.combo_curso_alerta, incluir_todos=False, secciones_permitidas=permitidas)
        _acortar_placeholder_combo(self.combo_curso_alerta, "Selecciona un grado")
        self._filtrar_secciones_alerta_por_curso()

    def _secciones_permitidas_con_nivel_alerta(self):
        permitidas= obtener_secciones_permitidas(self.main_window)
        nivel= self.combo_filtro_nivel_alerta.currentData() if hasattr(self, "combo_filtro_nivel_alerta") else None
        return interseccion_opcional(permitidas, secciones_del_nivel_educativo(nivel))

    def _nivel_filtro_alerta_cambio(self):
        self._cargar_secciones_alerta()

    def _curso_alerta_cambio(self):
        self._filtrar_secciones_alerta_por_curso()

    def _filtrar_secciones_alerta_por_curso(self):
        permitidas= self._secciones_permitidas_con_nivel_alerta()
        cascada_seccion_por_curso(self.combo_curso_alerta, self.combo_seccion_alerta,
                                   incluir_todas=False, secciones_permitidas=permitidas)
        #Antes de elegir curso el placeholder es "Selecciona curso"; una vez elegido un curso/grado real,
        #cascada_seccion_por_curso repuebla combo_seccion_alerta con sus secciones y un nuevo placeholder propio, que
        #aquí se acorta a "Selecciona sección".
        if self.combo_curso_alerta.currentData() is None:
            _acortar_placeholder_combo(self.combo_seccion_alerta, "Selecciona curso")
        else:
            _acortar_placeholder_combo(self.combo_seccion_alerta, "Selecciona sección")

    def _calcular_inasistencia(self):
        seccion_id= self.combo_seccion_alerta.currentData()
        curso_id= self.combo_curso_alerta.currentData() if hasattr(self, "combo_curso_alerta") else None
        permitidas= obtener_secciones_permitidas(self.main_window)
        conn= obtener_conexion()
        c= conn.cursor()

        condiciones= ["estudiantes.estado='Activo'"]
        parametros= []
        if seccion_id is not None:
            condiciones.append("estudiantes.seccion_id=?")
            parametros.append(seccion_id)
        elif curso_id is not None:
            condiciones.append("secciones.grado_id=?")
            parametros.append(curso_id)
        if permitidas is not None:
            if not permitidas:
                conn.close()
                return []
            marcadores= ",".join("?" for _ in permitidas)
            condiciones.append(f"estudiantes.seccion_id IN ({marcadores})")
            parametros.extend(permitidas)
        especialidad_id= self.combo_filtro_especialidad_alerta.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_filtro_carrera_alerta.currentData() if self._es_universidad() else None
        if especialidad_id == 0:
            condiciones.append("estudiantes.especialidad_id IS NULL")
        elif especialidad_id is not None:
            condiciones.append("estudiantes.especialidad_id=?")
            parametros.append(especialidad_id)
        if carrera_id == 0:
            condiciones.append("estudiantes.carrera_id IS NULL")
        elif carrera_id is not None:
            condiciones.append("estudiantes.carrera_id=?")
            parametros.append(carrera_id)

        c.execute(f"""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos, estudiantes.seccion_id,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE {' AND '.join(condiciones)}
                     ORDER BY estudiantes.apellidos, estudiantes.nombre""", parametros)
        estudiantes= c.fetchall()

        #Antes: hasta 3 consultas SQL por estudiante (3N en total). Ahora: una sola consulta agregada para TODOS los
        #estudiantes, sin importar cuántos sean. Los estados que cuentan para "presentes"/"inasistencias" se arman
        #según
        #self._valores_estado (configurable), no están fijos en el SQL. Los
        #estados marcados como Neutro (Excusado, Licencia Médica, Permiso...) quedan fuera del cálculo por completo: ni
        #suman inasistencia ni infl an el total, tal como se espera de una ausencia justificada.
        estados_presente= [e for e, cat in self._valores_estado.items() if cat == "Presente"]
        estados_inasistencia= [e for e, cat in self._valores_estado.items() if cat in ("Ausente", "Tardanza")]

        def _clausula_in(estados):
            if not estados:
                return "0", []  #ningún estado en esta categoría: condición siempre falsa
            return f"estado IN ({','.join('?' for _ in estados)})", list(estados)

        cond_presente, params_presente = _clausula_in(estados_presente)
        cond_inasistencia, params_inasistencia = _clausula_in(estados_inasistencia)
        c.execute(f"""SELECT estudiante_id,
                            SUM(CASE WHEN {cond_presente} THEN 1 ELSE 0 END) as presentes,
                            SUM(CASE WHEN {cond_inasistencia} THEN 1 ELSE 0 END) as inasistencias
                     FROM asistencia GROUP BY estudiante_id""", params_presente + params_inasistencia)
        agregados= {r["estudiante_id"]: r for r in c.fetchall()}
        conn.close()

        resultado= []
        for est in estudiantes:
            agr= agregados.get(est["id"])
            presentes= agr["presentes"] if agr else 0
            inasistencias= agr["inasistencias"] if agr else 0
            #El total excluye los registros Neutro a propósito: una licencia médica o un permiso no debe "diluir" ni
            #perjudicar el % de inasistencia del estudiante.
            total= presentes + inasistencias
            porcentaje= round((inasistencias / total) * 100, 1) if total else 0
            resultado.append({
                "id": est["id"],
                "nombre": f"{est['nombre']} {est['apellidos'] or ''}",
                "grado": est["grado_nombre"] or "",
                "seccion": est["seccion_nombre"] or "",
                "presentes": presentes,
                "inasistencias": inasistencias,
                "porcentaje": porcentaje,
                "total": total,
            })
        resultado.sort(key=lambda x: x["porcentaje"], reverse=True)
        return resultado

    def _generar_informe_inasistencia(self):
        umbral= self.spin_umbral.value()
        datos= self._calcular_inasistencia()
        self._datos_informe_actual= datos
        self._umbral_informe_actual= umbral

        self.paginacion_alertas.establecer_total(len(datos))
        inicio, fin = self.paginacion_alertas.rango_actual()
        pagina= datos[inicio:fin]

        self.tabla_alertas.setUpdatesEnabled(False)
        self.tabla_alertas.setRowCount(len(pagina))
        en_alerta= 0
        for i, d in enumerate(pagina):
            en_alerta_fila= d["porcentaje"] >= umbral and d["total"] > 0
            color= COLORES_ESTADO["Ausente"] if en_alerta_fila else COLORES_ESTADO["Presente"]
            tinte= QColor(color)
            tinte.setAlpha(26)
            if en_alerta_fila:
                en_alerta += 1
            valores= [d["nombre"], d["grado"], d["seccion"], str(d["presentes"]), str(d["inasistencias"]),
                       f"{d['porcentaje']}%", "ALERTA" if en_alerta_fila else "Normal"]
            for col, texto in enumerate(valores):
                item= QTableWidgetItem(texto)
                item.setBackground(tinte)
                if col == 6:
                    item.setForeground(QColor(color))
                    fuente= item.font()
                    fuente.setBold(True)
                    item.setFont(fuente)
                self.tabla_alertas.setItem(i, col, item)
        ajustar_anchos_columnas(self.tabla_alertas)
        self.tabla_alertas.setUpdatesEnabled(True)
        self._animar_aparicion(self.tabla_alertas, 220)
        self._flash(self._btn_generar_informe)

        self.lbl_resumen_alertas.setText(
            f"Estudiantes evaluados: {len(datos)}  |  Umbral: {umbral}%  |  "
            f"Estudiantes en alerta de inasistencia: {en_alerta}")
        registrar_auditoria("Asistencia", "Generó informe automático de inasistencia",
                            self.main_window.usuario_actual, f"Umbral {umbral}% - {en_alerta} en alerta")

    def _exportar_informe_csv(self):
        if not getattr(self, "_datos_informe_actual", None):
            mostrar_mensaje("advertencia", "Sin datos", "Genera el informe antes de exportar.", self)
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar Informe de Inasistencia",
                                              "informe_inasistencia.csv", "CSV (*.csv)")
        if not ruta:
            return
        umbral= self._umbral_informe_actual
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            writer= csv.writer(f)
            writer.writerow(["Estudiante", "Sección", "Presentes", "Ausencias/Tardanzas",
                             "% Inasistencia", "Estado"])
            for d in self._datos_informe_actual:
                estado= "ALERTA" if d["porcentaje"] >= umbral and d["total"] > 0 else "Normal"
                writer.writerow([d["nombre"], d["seccion"], d["presentes"], d["inasistencias"],
                                 f"{d['porcentaje']}%", estado])
        registrar_auditoria("Asistencia", "Exportó informe de inasistencia (CSV)",
                            self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Informe guardado en:\n{ruta}", self)

    def _exportar_informe_pdf(self):
        if not getattr(self, "_datos_informe_actual", None):
            mostrar_mensaje("advertencia", "Sin datos", "Genera el informe antes de exportar.", self)
            return
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'reportlab' (pip install reportlab) para exportar en PDF.", self)
            return
        from src.modulos.calificaciones import _datos_institucion, _dibujar_encabezado, _dibujar_pie_pagina
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar Informe de Inasistencia",
                                              "informe_inasistencia.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        umbral= self._umbral_informe_actual
        en_alerta= [d for d in self._datos_informe_actual if d["porcentaje"] >= umbral and d["total"] > 0]
        institucion= _datos_institucion()
        ancho, alto = letter
        cvs= canvas.Canvas(ruta, pagesize=letter)
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Informe Automático de Inasistencia")
        cvs.setFont("Helvetica", 9)
        cvs.drawString(50, y, f"Generado: {formatear_fecha_hora(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.main_window)}   |   "
                              f"Umbral de alerta: {umbral}%   |   Estudiantes en alerta: {len(en_alerta)}")
        y -= 22
        cvs.setFont("Helvetica-Bold", 10)
        cvs.drawString(50, y, "Estudiante")
        cvs.drawString(280, y, "Sección")
        cvs.drawString(400, y, "% Inasistencia")
        cvs.drawString(500, y, "Estado")
        y -= 8
        cvs.line(50, y, ancho - 50, y)
        y -= 16
        cvs.setFont("Helvetica", 9)
        for d in self._datos_informe_actual:
            estado= "ALERTA" if d["porcentaje"] >= umbral and d["total"] > 0 else "Normal"
            cvs.drawString(50, y, d["nombre"][:32])
            cvs.drawString(280, y, (d["seccion"] or "")[:18])
            cvs.drawString(400, y, f"{d['porcentaje']}%")
            cvs.drawString(500, y, estado)
            y -= 14
            if y < 110:
                _dibujar_pie_pagina(cvs, ancho, institucion, incluir_firma=False)
                cvs.showPage()
                y= alto - 60
        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.save()
        registrar_auditoria("Asistencia", "Exportó informe de inasistencia (PDF)",
                            self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Exportado", f"Informe guardado en:\n{ruta}", self)

    def _cargar_secciones(self):
        permitidas= self._secciones_permitidas_con_nivel()
        poblar_combo_curso(self.combo_curso, incluir_todos=False, secciones_permitidas=permitidas)
        _acortar_placeholder_combo(self.combo_curso, "Selecciona un grado")
        self._filtrar_secciones_registro_por_curso()

    def _secciones_permitidas_con_nivel(self):
        """RBAC de Profesor (si aplica) combinado con el filtro de Nivel
        Educativo elegido, para que Curso/Sección solo ofrezcan lo válido
        para ambos criterios a la vez (igual patrón que ya usa
        secciones_permitidas en todos los combos de este módulo)."""
        permitidas= obtener_secciones_permitidas(self.main_window)
        nivel= self.combo_filtro_nivel.currentData() if hasattr(self, "combo_filtro_nivel") else None
        return interseccion_opcional(permitidas, secciones_del_nivel_educativo(nivel))

    def _nivel_filtro_registro_cambio(self):
        self._cargar_secciones()
        self._cargar_lista()

    def _curso_registro_cambio(self):
        self._filtrar_secciones_registro_por_curso()

    def _filtrar_secciones_registro_por_curso(self):
        permitidas= self._secciones_permitidas_con_nivel()
        cascada_seccion_por_curso(self.combo_curso, self.combo_seccion,
                                   incluir_todas=False, secciones_permitidas=permitidas)
        #Solo se acorta el placeholder "sin curso elegido todavía". Una vez que el usuario elige un curso real,
        #combo_seccion se repuebla con sus secciones reales (y su propio placeholder de cascada_seccion_por_curso), que
        #aquí NO se debe tocar.
        if self.combo_curso.currentData() is None:
            _acortar_placeholder_combo(self.combo_seccion, "Selecciona curso")
        self._cargar_lista()

    def _cargar_materias_combo(self):
        """Lista de Materias del selector de 'Registro Diario'. Si la
        institución es un Politécnico (o Personalizado con el módulo
        Politécnico activo) y hay un Área Técnica elegida en el filtro de
        arriba, se limita ESTRICTAMENTE a los módulos técnicos de esa
        área -mismo criterio que 'Asignar Clase' en materias.py
        (_cargar_combo_h_materia)-, para no mezclar materias de otras
        especialidades en la lista de asistencia. Sin área técnica elegida
        (o en una institución que no es Politécnico), se comporta como
        antes: todas las materias activas que el usuario tiene permitidas."""
        actual= self.combo_materia.currentData()
        #IDs de materias que son Módulos Técnicos (modelo 'Técnica (RA)'):
        #permite que los chips de filtro digan "Módulo: X" en vez de "Materia: X" cuando la selección lo es (solo
        #relevante en un Politécnico -ver _actualizar_resumen_filtros_registro).
        self._materias_tecnicas_asis= set()
        self.combo_materia.blockSignals(True)
        self.combo_materia.clear()
        self.combo_materia.addItem("General (todo el día)", None)
        especialidad_id= (self.combo_filtro_especialidad_asis.currentData()
                            if self._es_politecnico() and hasattr(self, "combo_filtro_especialidad_asis")
                            else None)
        permitidas_materias= obtener_materias_permitidas(self.main_window)
        conn= obtener_conexion()
        c= conn.cursor()
        if especialidad_id is not None:
            c.execute("""SELECT id, nombre, modelo_evaluacion FROM materias
                         WHERE estado='Activa' AND especialidad_id=? ORDER BY nombre""", (especialidad_id,))
        else:
            c.execute("SELECT id, nombre, modelo_evaluacion FROM materias WHERE estado='Activa' ORDER BY nombre")
        for f in c.fetchall():
            if permitidas_materias is not None and f["id"] not in permitidas_materias:
                continue
            if (f["modelo_evaluacion"] or "") == "Técnica (RA)":
                self._materias_tecnicas_asis.add(f["id"])
            self.combo_materia.addItem(f["nombre"], f["id"])
        conn.close()
        idx= self.combo_materia.findData(actual)
        #Si la materia que estaba elegida ya no aparece (por ejemplo, era de otra área técnica y se acaba de acotar el
        #combo), se cae de vuelta a "General" en lugar de dejar una selección fantasma.
        self.combo_materia.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_materia.blockSignals(False)

    def _capturar_estado_actual(self):
        if not hasattr(self, "_registros_asistencia"):
            self._registros_asistencia= {}
        for i in range(self.tabla.rowCount()):
            item= self.tabla.item(i, 1)
            combo= self.tabla.cellWidget(i, 2)
            if item and combo:
                est_id= item.data(Qt.ItemDataRole.UserRole)
                self._registros_asistencia[est_id]= combo.currentText()

    def _on_cambio_pagina_registro(self):
        #Se llama cuando el usuario cambia de página: primero guardamos en memoria lo marcado en la página que se está
        #por reemplazar (para no perder cambios sin guardar) y luego pintamos la nueva página.
        self._capturar_estado_actual()
        self._renderizar_pagina()

    def _es_politecnico(self):
        """True si la institución es de tipo Politécnico (o Personalizado con el
        módulo Politécnico activo). Mismo criterio usado en estudiantes.py."""
        try:
            tipo, personalizados = self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    def _es_universidad(self):
        """True si la institución es de tipo Universidad (o Personalizado con el
        módulo Universidad activo). Mismo criterio usado en estudiantes.py."""
        try:
            tipo, personalizados = self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    def _cargar_especialidad_carrera_filtro_asistencia(self):
        """Igual que en Estudiantes: los combos de Área Técnica y Carrera solo
        se muestran/pueblan si la institución tiene ese módulo activo."""
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_asis.setVisible(es_poli)
        self.combo_filtro_especialidad_asis.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_asis.currentData()
            self.combo_filtro_especialidad_asis.blockSignals(True)
            self.combo_filtro_especialidad_asis.clear()
            self.combo_filtro_especialidad_asis.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_asis.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_asis.findData(actual)
            self.combo_filtro_especialidad_asis.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_asis.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_asis.setVisible(es_uni)
        self.combo_filtro_carrera_asis.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_asis.currentData()
            self.combo_filtro_carrera_asis.blockSignals(True)
            self.combo_filtro_carrera_asis.clear()
            self.combo_filtro_carrera_asis.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_asis.addItem(f["nombre"], f["id"])
            conn.close()
            idx= self.combo_filtro_carrera_asis.findData(actual)
            self.combo_filtro_carrera_asis.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_asis.blockSignals(False)

    def _estudiantes_filtrados(self):
        """Lista de estudiantes de la sección que coinciden con el texto de
        búsqueda (por nombre o apellido, sin distinguir mayúsculas/acentos) y,
        si aplica, con el área técnica/carrera elegidas. Solo afecta qué se
        MUESTRA/pagina; el guardado y las tarjetas de resumen del día siguen
        considerando la sección completa."""
        campo= getattr(self, "in_buscar_estudiantes", None)
        texto= _normalizar(campo.text().strip()) if campo else ""
        especialidad_id= (self.combo_filtro_especialidad_asis.currentData()
                            if self._es_politecnico() else None)
        carrera_id= self.combo_filtro_carrera_asis.currentData() if self._es_universidad() else None
        resultado= self._estudiantes_seccion
        if especialidad_id is not None:
            resultado= [est for est in resultado if est["especialidad_id"] == especialidad_id]
        if carrera_id is not None:
            resultado= [est for est in resultado if est["carrera_id"] == carrera_id]
        if texto:
            resultado= [est for est in resultado
                         if texto in _normalizar(f"{est['nombre']} {est['apellidos'] or ''}")]
        return resultado

    def _filtro_estudiantes_cambio(self):
        self._capturar_estado_actual()
        self.paginacion_registro.reiniciar()
        self._renderizar_pagina()

    def _cargar_lista(self):
        seccion_id= self.combo_seccion.currentData()
        if seccion_id is None:
            self.tabla.setRowCount(0)
            self._estudiantes_seccion= []
            self._registros_asistencia= {}
            self.paginacion_registro.establecer_total(0)
            self._actualizar_estadisticas()
            self.estado_vacio_registro.actualizar(hay_filtro_elegido=False)
            return
        materia_id= self.combo_materia.currentData()
        fecha= self.date_fecha.date().toString("yyyy-MM-dd")
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre, apellidos, especialidad_id, carrera_id, numero_lista FROM estudiantes
                     WHERE seccion_id=? AND estado='Activo'
                     ORDER BY numero_lista IS NULL, numero_lista, apellidos, nombre""",
                  (seccion_id,))
        self._estudiantes_seccion= c.fetchall()
        c.execute("""SELECT estudiante_id, estado FROM asistencia
                     WHERE seccion_id=? AND fecha=? AND (materia_id=? OR (? IS NULL AND materia_id IS NULL))""",
                  (seccion_id, fecha, materia_id, materia_id))
        self._registros_asistencia= {r["estudiante_id"]: r["estado"] for r in c.fetchall()}
        conn.close()
        self.paginacion_registro.reiniciar()
        self._renderizar_pagina()

    def _estilizar_combo_estado(self, combo, estado):
        color= COLORES_ESTADO.get(estado, "#6366F1")
        colores= _colores_tema(self.main_window)
        combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 4px 10px;
                font-weight: 700;
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background-color: {colores['bg_panel']}; color: {colores['txt_prim']};
                selection-background-color: {color}; selection-color: white;
                outline: none;
            }}
        """)

    def _on_cambio_estado_fila(self, estudiante_id, estado, combo):
        self._registros_asistencia[estudiante_id]= estado
        self._estilizar_combo_estado(combo, estado)
        self._actualizar_estadisticas()

    def _renderizar_pagina(self):
        estudiantes= self._estudiantes_filtrados()
        self.paginacion_registro.establecer_total(len(estudiantes))
        inicio, fin = self.paginacion_registro.rango_actual()
        pagina= estudiantes[inicio:fin]

        #El "No." solo se muestra si además de la Sección (obligatoria para llegar hasta aquí) también se filtró Área
        #Técnica/Carrera cuando la institución las usa -ver bd.mostrar_columna_numero_lista- para no mezclar numeración
        #de varias áreas técnicas/carreras dentro de la misma sección como si fuera un único orden.
        especialidad_id_actual= (self.combo_filtro_especialidad_asis.currentData()
                                   if self._es_politecnico() else None)
        carrera_id_actual= self.combo_filtro_carrera_asis.currentData() if self._es_universidad() else None
        mostrar_columna_numero= mostrar_columna_numero_lista(
            self.main_window, self.combo_seccion.currentData(), especialidad_id_actual, carrera_id_actual)
        self.tabla.setColumnHidden(0, not mostrar_columna_numero)

        #setUpdatesEnabled(False) evita repintados intermedios mientras se llena
        #la tabla: con secciones grandes, la diferencia de fluidez es notoria.
        self.tabla.setUpdatesEnabled(False)
        self.tabla.setRowCount(len(pagina))
        for i, est in enumerate(pagina):
            if mostrar_columna_numero:
                item_numero= QTableWidgetItem()
                numero_lista= est["numero_lista"] if "numero_lista" in est.keys() else None
                item_numero.setData(Qt.ItemDataRole.DisplayRole, numero_lista if numero_lista is not None else "—")
                item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_numero.setFlags(item_numero.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if numero_lista is None:
                    item_numero.setToolTip(
                        "Aún no se ha calculado (ve a Estudiantes y usa 'Recalcular Números de Lista').")
                self.tabla.setItem(i, 0, item_numero)
            nombre_item= QTableWidgetItem(f"{est['nombre']} {est['apellidos'] or ''}")
            nombre_item.setFlags(nombre_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            nombre_item.setData(Qt.ItemDataRole.UserRole, est["id"])
            self.tabla.setItem(i, 1, nombre_item)
            combo= QComboBox()
            combo.addItems(ESTADOS_ASISTENCIA)
            combo.setMinimumWidth(170)
            estado_actual= self._registros_asistencia.get(est["id"], "Presente")
            combo.setCurrentText(estado_actual)
            conectar_tooltip_seleccion(combo, f"Estado de asistencia de {est['nombre']}")
            self._estilizar_combo_estado(combo, estado_actual)
            combo.currentTextChanged.connect(
                lambda estado, eid=est["id"], cb=combo: self._on_cambio_estado_fila(eid, estado, cb))
            self.tabla.setCellWidget(i, 2, combo)
        ajustar_anchos_columnas(self.tabla)
        self.tabla.setUpdatesEnabled(True)
        self._animar_aparicion(self.tabla, 200)
        self._actualizar_estadisticas()
        self.estado_vacio_registro.actualizar(hay_filtro_elegido=self.combo_seccion.currentData() is not None)

    def _marcar_todos(self, estado, boton=None):
        for est in self._estudiantes_seccion:
            self._registros_asistencia[est["id"]]= estado
        for i in range(self.tabla.rowCount()):
            combo= self.tabla.cellWidget(i, 2)
            if combo:
                combo.blockSignals(True)
                combo.setCurrentText(estado)
                self._estilizar_combo_estado(combo, estado)
                combo.blockSignals(False)
        self._actualizar_estadisticas()
        self._flash(boton)

    def _actualizar_estadisticas(self):
        """Recalcula las tarjetas de resumen y la barra de porcentaje a partir de
 TODA la sección (no solo la página visible), con animaciones suaves.
 Los conteos se agrupan por CATEGORÍA (self._valores_estado), no por el
 nombre literal del estado, así que respetan los valores configurados
 en el botón ⚙."""
        total= len(self._estudiantes_seccion)
        conteos_categoria= {categoria: 0 for categoria in CATEGORIAS_CONTEO}
        for est in self._estudiantes_seccion:
            estado= self._registros_asistencia.get(est["id"], "Presente")
            categoria= self._valores_estado.get(estado, "Neutro")
            conteos_categoria[categoria]= conteos_categoria.get(categoria, 0) + 1

        self.tarjeta_presentes.establecer(conteos_categoria.get("Presente", 0))
        self.tarjeta_ausentes.establecer(conteos_categoria.get("Ausente", 0))
        self.tarjeta_tardanzas.establecer(conteos_categoria.get("Tardanza", 0))
        self.tarjeta_excusados.establecer(conteos_categoria.get("Neutro", 0))

        #Los estudiantes en categoría Neutro (Excusado, Licencia Médica, Permiso...) se excluyen del cálculo del % de
        #asistencia, igual que en el informe de riesgo de inasistencia. Si no se hiciera así, un estudiante excusado
        #restaría del % exactamente igual que uno
        #ausente (ninguno suma al numerador, pero ambos sí al denominador),
        #lo cual contradice la idea de que "Neutro" no debería afectar nada.
        total_computable= total - conteos_categoria.get("Neutro", 0)
        porcentaje= round((conteos_categoria.get("Presente", 0) / total_computable) * 100) if total_computable else 0
        self.barra_porcentaje.poner_valor_animado(porcentaje)

    def _abrir_valores_estado(self):
        """Abre el diálogo de configuración de valores y, si se guarda,
        persiste el cambio y refresca de inmediato las tarjetas/informe para
        que el efecto se vea sin tener que salir del módulo."""
        dialogo= DialogoValoresAsistencia(self, self.main_window, self._valores_estado)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._valores_estado= dialogo.valores()
            guardar_valores_estado(self._valores_estado)
            self._actualizar_estadisticas()
            if hasattr(self, "_datos_informe_actual"):
                self._datos_informe_actual= None
            registrar_auditoria("Asistencia", "Actualizó valores de conteo de asistencia",
                                self.main_window.usuario_actual, str(self._valores_estado))
            mostrar_mensaje("exito", "Guardado",
                            "Los valores de asistencia se actualizaron correctamente.", self)

    def _guardar(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para registrar asistencia.", self)
            return
        seccion_id= self.combo_seccion.currentData()
        if seccion_id is None:
            mostrar_mensaje("advertencia", "Sin sección", "Selecciona una sección.", self)
            return
        materia_id= self.combo_materia.currentData()
        fecha= self.date_fecha.date().toString("yyyy-MM-dd")
        self._capturar_estado_actual()
        conn= obtener_conexion()
        c= conn.cursor()
        for est in self._estudiantes_seccion:
            est_id= est["id"]
            estado= self._registros_asistencia.get(est_id, "Presente")
            c.execute("""SELECT id FROM asistencia WHERE estudiante_id=? AND seccion_id=? AND fecha=?
                         AND (materia_id=? OR (? IS NULL AND materia_id IS NULL))""",
                      (est_id, seccion_id, fecha, materia_id, materia_id))
            existente= c.fetchone()
            if existente:
                c.execute("UPDATE asistencia SET estado=? WHERE id=?", (estado, existente["id"]))
            else:
                c.execute("""INSERT INTO asistencia (estudiante_id, seccion_id, materia_id, fecha, estado)
                             VALUES (?,?,?,?,?)""", (est_id, seccion_id, materia_id, fecha, estado))
        conn.commit()
        conn.close()
        registrar_auditoria("Asistencia", "Registró asistencia", self.main_window.usuario_actual,
                            f"Sección ID {seccion_id} - {fecha}")
        self._actualizar_estadisticas()

        texto_original= self._btn_guardar.text()
        self._btn_guardar.setText("¡Guardado!")
        self._btn_guardar.setEnabled(False)
        QTimer.singleShot(1400, lambda: (self._btn_guardar.setText(texto_original), self._btn_guardar.setEnabled(True)))
        mostrar_mensaje("exito", "Guardado", "El registro de asistencia se guardó correctamente.", self)

    def refrescar(self):
        if hasattr(self, "combo_filtro_nivel"):
            poblar_combo_nivel_educativo(self.combo_filtro_nivel)
        if hasattr(self, "combo_filtro_nivel_alerta"):
            poblar_combo_nivel_educativo(self.combo_filtro_nivel_alerta)
        self._cargar_secciones()
        #El filtro de Área Técnica se puebla ANTES que Materia: en un Politécnico, _cargar_materias_combo lee la
        #especialidad actualmente elegida en ese combo para acotar sus opciones (ver _cargar_materias_combo), así que
        #necesita existir/estar actualizado primero.
        self._cargar_especialidad_carrera_filtro_asistencia()
        self._cargar_materias_combo()
        self._cargar_lista()
        self._cargar_especialidad_carrera_filtro_alerta()
        self._cargar_secciones_alerta()

    def actualizar_tema(self):
        """Sincroniza los colores de las tarjetas y acentos de este módulo con el
        tema/modo claro-oscuro actual de la app. Se llama al construir la pantalla
        y cada vez que el usuario cambia de tema (ver main.py)."""
        colores= _colores_tema(self.main_window)
        bg_panel= colores["bg_panel"]
        bg_btn= colores["bg_btn"]
        txt_prim= colores["txt_prim"]
        txt_sec= colores["txt_sec"]
        accent= colores["accent"]
        accent_hv= colores["accent_hv"]
        accent_suave= _hex_a_rgba(accent, 0.16)
        borde_suave= _hex_a_rgba(bg_btn, 0.7)

        #--- Pestañas --- QTabWidget::pane sin borde: con setDocumentMode(True) el "pane" ya no necesita marco propio,
        #y ese borde dibujaba una línea recta que cortaba justo debajo de las pestañas-píldora, rompiendo el diseño.
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{
                padding: 9px 20px; margin-right: 6px; border-radius: 9px; font-weight: 600;
                background: {bg_btn}; color: {txt_sec};
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {accent_hv});
                color: white;
            }}
            QTabBar::tab:!selected:hover {{ background: {accent_suave}; color: {txt_prim}; }}
        """)

        #--- Cabecera ---
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#CabeceraAsistencia {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {accent_hv});
                border: 1px solid {accent_hv};
                border-radius: 16px;
            }}
            QFrame#CabeceraAsistencia QLabel {{ background: transparent; border: none; }}
            QLabel#TituloCabeceraAsistencia {{
                font-size: 22px;
                font-weight: 800;
                color: white;
            }}
            QLabel#SubtituloCabeceraAsistencia {{
                font-size: 13px;
                color: rgba(255, 255, 255, 220);
            }}
        """)
        self.lbl_fecha_hoy.setStyleSheet("""
            background-color: rgba(255,255,255,28);
            border-radius: 10px;
            padding: 7px 16px;
            font-weight: 700;
            color: white;
        """)
        #La sombra de la cabecera debe seguir el color de acento del tema:
        #antes quedaba fija en morado (QColor(76,29,149,...)) sin importar el tema elegido, así que se veía un brillo
        #violeta aunque el degradado de la cabecera fuera rojo/verde/etc., como en la captura.
        r, g, b = int(accent.lstrip("#")[0:2], 16), int(accent.lstrip("#")[2:4], 16), int(accent.lstrip("#")[4:6], 16)
        self._sombra_cabecera.setColor(QColor(r, g, b, 90))

        #--- Buscador de estudiantes ---
        if hasattr(self, "icono_busqueda_estudiantes"):
            self.icono_busqueda_estudiantes.establecer_color(txt_sec)

        #--- Ventanas de filtrado (Registro Diario y Alertas) --- Mismo diseño/estilo que la ventana de "☰ Filtros" de
        #Calificaciones y Calificaciones Técnicas: solo cambia el sufijo del objectName para no chocar con el QSS de
        #esos otros módulos.
        for dialogo_filtros in (getattr(self, "dialogo_filtros_registro", None),
                                getattr(self, "dialogo_filtros_alertas", None)):
            if dialogo_filtros is not None:
                dialogo_filtros.setStyleSheet(f"""
                    QDialog#DialogoFiltrosAsis {{
                        background-color: {bg_panel};
                    }}
                    QToolTip {{
                        background-color: {bg_panel};
                        color: {txt_prim};
                        border: 1px solid {bg_btn};
                        padding: 6px 10px;
                        border-radius: 6px;
                    }}
                    QLabel#IconoEncabezadoFiltrosAsis {{
                        background-color: {accent};
                        color: white;
                        border-radius: 15px;
                        min-width: 30px; max-width: 30px;
                        min-height: 30px; max-height: 30px;
                        font-size: 14px;
                        qproperty-alignment: AlignCenter;
                    }}
                    QLabel#TituloEncabezadoFiltrosAsis {{
                        font-size: 16px;
                        font-weight: 800;
                        color: {txt_prim};
                        background: transparent;
                    }}
                    QLabel#SubtituloFiltrosAsis {{
                        font-size: 11.5px;
                        color: {txt_sec};
                        background: transparent;
                    }}
                    QFrame#SeparadorFiltrosAsis {{
                        background-color: {bg_btn};
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

        #--- Tarjetas de estadística ---
        for tarjeta in (self.tarjeta_presentes, self.tarjeta_ausentes,
                        self.tarjeta_tardanzas, self.tarjeta_excusados):
            tarjeta.aplicar_paleta(bg_panel, bg_btn, txt_sec)

        #--- Tablas (hover) ---
        self.tabla.setStyleSheet(f"""
            QTableWidget::item:hover {{ background-color: {accent_suave}; }}
        """)
        self.tabla_alertas.setStyleSheet(f"""
            QTableWidget::item:hover {{ background-color: {accent_suave}; }}
        """)