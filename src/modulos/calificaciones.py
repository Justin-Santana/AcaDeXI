import os
import json
import math
import unicodedata
from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox, QLineEdit,
QMessageBox, QGridLayout, QFileDialog, QTabWidget, QScrollArea, QFrame,
QGraphicsOpacityEffect, QSizePolicy, QDialog, QCheckBox, QTextEdit, QDateEdit, QListWidget,
QListWidgetItem, QAbstractItemView, QDialogButtonBox, QSpinBox, QApplication)
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup,
    QRect, QRectF, QPointF, Property, Signal, QTimer, QDate)
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QFont, QPainterPath, QIcon, QPixmap,
    QLinearGradient, QConicalGradient, QRadialGradient)
from src.nucleo.bd import obtener_conexion, registrar_auditoria, get_app_data_dir, mostrar_columna_numero_lista
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo, interseccion_opcional)
from src.nucleo.iconos import mostrar_mensaje, centrar_y_al_frente, aplicar_icono_cabecera
from src.nucleo.permisos import (puede_editar, obtener_secciones_permitidas, obtener_materias_permitidas,
es_profesor_restringido, tiene_acceso_gerencial)
from src.interfaz.paginacion import (ControlPaginacion, agregar_boton_detalle, tabla_pausada, mostrar_texto_largo,
    aplicar_estructura_tabla, agregar_boton_pantalla_completa)
from src.interfaz.configuracion import (SISTEMA_DOMINICANO, COMPETENCIAS_FUNDAMENTALES_RD, NIVELES_DESEMPENO_RD,
    NIVEL_SIN_EVALUAR_RD, COLORES_NIVEL_DESEMPENO_RD, BANDAS_DESEMPENO_RD, es_sistema_dominicano,
    resolver_nota_minima, IconoLupa, TabWidgetNavegable, ajustar_combo_ancho_seguro, conectar_tooltip_seleccion,
    estilo_flechas_navegacion_tabs)
from src.modulos.materias import MODELO_EVALUACION_TECNICA
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.interfaz.intercambio_dialogs import DialogoExportarCalificaciones, DialogoImportarCalificaciones
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, quitar_emojis_texto,
                          icono_boton_filtro, pixmap_boton_filtro, _pluma,
                          EMOJI_VINCULAR, EMOJI_BOLETIN_PROMEDIOS, EMOJI_SEGUIMIENTO_RP,
                          EMOJI_EVALUACIONES_FINALES, EMOJI_CURRICULO_CE, EMOJI_NOTAS_COMPETENCIA,
                          EMOJI_COMPARTIR_CALIFICACIONES, EMOJI_DESEMPENO_INDIVIDUAL,
                          EMOJI_NOTA_COMPLETIVA, EMOJI_NOTA_EXTRAORDINARIA, EMOJI_NOTA_ESPECIAL)

try:
    from src.nucleo.hilo_trabajo import WorkerHilo
except Exception:  #pragma: no cover
    WorkerHilo= None

CATEGORIAS= ["Examen", "Práctica", "Tarea", "Participación", "Proyecto", "Examen Final"]
ESTADOS_PUBLICACION= ["Borrador", "Pendiente", "Publicada"]


def _acortar_placeholder_combo(combo, texto):
    """Reemplaza el texto del placeholder (ítem 0, sin dato asociado) de un
    combo de Curso/Sección/Estudiante. Ajuste puramente visual y LOCAL a
    ciertas pestañas de Calificaciones (Boletín, Historial Académico,
    Desempeño Individual, Seguimiento RP, Evaluaciones Finales, Notas por
    Competencia y Compartir Calificaciones): no modifica filtros_curso_seccion.py
    ni el resto de los combos de este mismo módulo (p.ej. Registrar Calificación
    o Registro Masivo siguen con el placeholder largo original). Si el ítem 0
    ya tiene un valor real seleccionado, no se toca."""
    if combo.count() > 0 and combo.itemData(0) is None:
        combo.setItemText(0, texto)


def _actualizar_estado_combo_estudiante(combo_curso, combo_seccion, combo_estudiante):
    """El combo de Estudiante de estas pestañas solo debe poder usarse una vez
    que ya se eligieron Curso y Sección (si no, la lista de estudiantes no
    tiene sentido o mezclaría estudiantes de secciones distintas). Mientras
    falte alguno de los dos, se deshabilita Y se marca visualmente (borde
    punteado, texto atenuado y tooltip) para que sea evidente que hay que
    completar los filtros de arriba primero, en vez de solo verse gris sin
    explicación."""
    listo= combo_curso.currentData() is not None and combo_seccion.currentData() is not None
    combo_estudiante.setEnabled(listo)
    if listo:
        combo_estudiante.setStyleSheet("")
        combo_estudiante.setToolTip("")
    else:
        combo_estudiante.setStyleSheet(
            "QComboBox:disabled { color: #64748B; background: rgba(100, 116, 139, 0.12); "
            "border: 1px dashed #64748B; border-radius: 6px; font-style: italic; }")
        combo_estudiante.setToolTip("Elige un grado y una sección primero.")


def _nivel_desde_nota(nota):
    """Clasifica una nota 0-100 en un nivel de desempeño usando las mismas
    bandas oficiales (Ordenanza 04-2023, MINERD) que ya se usan en Desempeño
    Individual, para que una Competencia Específica y una Competencia
    Fundamental se lean con el mismo lenguaje en toda la app."""
    if nota is None:
        return NIVEL_SIN_EVALUAR_RD
    for nivel, (piso, techo) in BANDAS_DESEMPENO_RD.items():
        if piso <= nota <= techo:
            return nivel
    return "Insuficiente" if nota < 65 else "Destacado"


def _registrar_historial_cambio(tabla_origen, registro_id, estudiante_id, campo,
                                 valor_anterior, valor_nuevo, usuario, motivo="", cursor=None):
    """Deja constancia en historial_cambios_calificaciones de un cambio de valor.
    No registra si el valor no cambió realmente (evita ruido en el historial).
    Si se pasa `cursor` (de una conexión ya abierta por el llamador), lo reutiliza en
    vez de abrir una conexión nueva — evita 'database is locked' cuando el llamador
    todavía tiene una transacción de escritura abierta sobre la misma BD SQLite."""
    if str(valor_anterior) == str(valor_nuevo):
        return
    fila= (tabla_origen, registro_id, estudiante_id, campo,
            "" if valor_anterior is None else str(valor_anterior),
            "" if valor_nuevo is None else str(valor_nuevo),
            usuario or "", motivo or "", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    sql= """INSERT INTO historial_cambios_calificaciones
             (tabla_origen, registro_id, estudiante_id, campo, valor_anterior, valor_nuevo,
              usuario, motivo, fecha) VALUES (?,?,?,?,?,?,?,?,?)"""
    if cursor is not None:
        cursor.execute(sql, fila)
        return
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute(sql, fila)
    conn.commit()
    conn.close()

_SIN_CARGAR= object()  #centinela: distingue "todavía no consultado" de "consultado y dio None/todos permitidos"


#Capa visual — componentes reutilizables (tarjetas, anillo, barra, animaciones)  IMPORTANTE: ninguno de estos
#widgets usa QGraphicsEffect (ni sombra ni opacidad permanente). Los QGraphicsEffect de Qt son notoriamente
#inestables cuando su contenedor se redimensiona en vivo (p. ej. al arrastrar el panel lateral): el repintado
#se corrompe y el widget puede quedar en blanco hasta el siguiente repaint forzado — eso era lo que hacía
#"desaparecer" las KPI. En su lugar, todo se pinta a mano en paintEvent(), que Qt siempre repinta correctamente
#sin importar cuántas veces cambie el tamaño del contenedor.
def _hex_a_rgba(color_hex, alpha):
    color_hex= color_hex.lstrip("#")
    r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _crear_pulso(objetivo, propiedad, minimo, maximo, duracion=950):
    """Animación de 'respiración' (sube y baja en bucle) sobre una propiedad Qt.
    Se usa para dar un latido sutil a lo que requiere atención."""
    grupo= QSequentialAnimationGroup(objetivo)
    subir= QPropertyAnimation(objetivo, propiedad)
    subir.setStartValue(minimo)
    subir.setEndValue(maximo)
    subir.setDuration(duracion)
    subir.setEasingCurve(QEasingCurve.Type.InOutSine)
    bajar= QPropertyAnimation(objetivo, propiedad)
    bajar.setStartValue(maximo)
    bajar.setEndValue(minimo)
    bajar.setDuration(duracion)
    bajar.setEasingCurve(QEasingCurve.Type.InOutSine)
    grupo.addAnimation(subir)
    grupo.addAnimation(bajar)
    grupo.setLoopCount(-1)
    return grupo


def _animar_click(boton):
    """Pequeño 'rebote' visual al presionar un botón."""
    geo= boton.geometry()
    if geo.width() <= 0 or geo.height() <= 0:
        return
    centro= geo.center()
    reducido= QRect(0, 0, max(1, int(geo.width() * 0.95)), max(1, int(geo.height() * 0.88)))
    reducido.moveCenter(centro)
    anim= QPropertyAnimation(boton, b"geometry")
    anim.setDuration(150)
    anim.setStartValue(geo)
    anim.setKeyValueAt(0.5, reducido)
    anim.setEndValue(geo)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    boton._anim_rebote= anim  #evita que el recolector de basura la corte a mitad de vuelo
    anim.start()


def _efecto_transicion(widget, duracion=220):
    """Fundido de entrada breve al cambiar de pestaña. A diferencia de las
    tarjetas, este SÍ usa un QGraphicsOpacityEffect transitorio — pero se
    quita del widget en cuanto termina la animación, así el widget vuelve de
    inmediato a su camino de repintado normal (rápido y sin riesgo) el resto
    del tiempo, en vez de quedar con un efecto pegado para siempre."""
    if widget is None:
        return
    efecto= QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(efecto)
    anim= QPropertyAnimation(efecto, b"opacity", widget)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(duracion)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._anim_fade= anim
    anim.start()


def _icono_punto(color, diametro=9, base=None, tam_base=18):
    """Genera un pequeño punto de color como QIcon, para marcar en la propia
    pestaña (sin abrirla) que esa sección tiene algo pendiente.

    Si se pasa `base` (un caracter de iconos_emoji, ej. EMOJI_SEGUIMIENTO_RP),
    el punto se dibuja SUPERPUESTO en la esquina superior derecha del icono
    de esa pestaña, en vez de reemplazarlo por completo: antes, al haber
    pendientes, la pestaña perdía su icono propio y quedaba solo con un
    punto suelto (y al no haber pendientes, sin icono alguno)."""
    if base is None:
        pix= QPixmap(diametro, diametro)
        pix.fill(Qt.GlobalColor.transparent)
        p= QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(0, 0, diametro, diametro)
        p.end()
        return QIcon(pix)
    pix= QPixmap(tam_base, tam_base)
    pix.fill(Qt.GlobalColor.transparent)
    p= QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawPixmap(0, 0, pixmap_emoji(base, tam_base))
    p.setPen(_pluma("white", 1.4))
    p.setBrush(QColor(color))
    cx, cy, r = tam_base * 0.80, tam_base * 0.20, tam_base * 0.19
    p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    p.end()
    return QIcon(pix)


def _normalizar_busqueda(texto):
    """Minúsculas y sin tildes/diacríticos, para que buscar 'jose' encuentre
    'José', 'MATEMATICA' encuentre 'Matemática', etc. — sin obligar al
    usuario a escribir el acento o respetar mayúsculas exactas."""
    if not texto:
        return ""
    descompuesto= unicodedata.normalize("NFKD", texto)
    sin_acentos= "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.casefold().strip()


class SearchBarCalificaciones(QWidget):
    """Barra de búsqueda con el mismo diseño visual que configuracion.py:
    icono de lupa dibujado con QPainter + QFrame con fondo semitransparente y
    border-radius 16px + QLineEdit sin borde ni fondo. Mantiene la misma
    interfaz que BusquedaConDebounce (señal texto_buscado, métodos .text(),
    .setText(), .clear(), .setPlaceholderText()) para no tener que cambiar el
    resto del código que ya la usa."""

    texto_buscado= Signal(str)

    def __init__(self, parent=None, delay_ms=200):
        super().__init__(parent)
        self._delay_ms= delay_ms
        self._timer= QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._emitir_busqueda)

        layout= QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.marco= QFrame()
        self.marco.setStyleSheet(
            "QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_marco= QHBoxLayout(self.marco)
        lay_marco.setContentsMargins(12, 0, 10, 0)
        lay_marco.setSpacing(6)

        self.icono_lupa= IconoLupa()
        lay_marco.addWidget(self.icono_lupa)

        self.line_edit= QLineEdit()
        limitar_campo_texto(self.line_edit, 300)
        self.line_edit.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        self.line_edit.textChanged.connect(self._on_texto_cambiado)
        lay_marco.addWidget(self.line_edit, 1)

        layout.addWidget(self.marco)
        #Tamaño fijo: sin esto, en pestañas donde el layout vertical tiene espacio sobrante y ningún otro widget lo
        #reclama, Qt lo reparte entre los widgets con política "Preferred" (como este) y la barra de búsqueda termina
        #estirándose a alturas absurdas. Fijarla asegura además que TODAS las searchbars del módulo midan siempre lo
        #mismo.
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _on_texto_cambiado(self, _texto):
        self._timer.stop()
        self._timer.start()

    def _emitir_busqueda(self):
        self.texto_buscado.emit(self.line_edit.text().strip())

    def text(self):
        return self.line_edit.text()

    def setText(self, texto):
        self.line_edit.setText(texto)

    def clear(self):
        self.line_edit.clear()

    def setPlaceholderText(self, texto):
        self.line_edit.setPlaceholderText(texto)

    def establecer_color_icono(self, color):
        """Cambia el color del icono de lupa — se llama desde actualizar_tema
        para que el icono se adapte al tema claro/oscuro, igual que en
        configuracion.py."""
        self.icono_lupa.establecer_color(color)


class TarjetaAlerta(QWidget):
    """Tarjeta compacta de resumen (ícono + valor + etiqueta), pintada a mano.
    Cuando se actualiza con alerta=True 'late' con un halo suave alrededor
    del borde; en su estado normal se queda quieta. El valor numérico además
    se anima contando desde el número anterior hasta el nuevo."""

    def __init__(self, icono, etiqueta, color, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 108)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._color= QColor(color)
        self._icono= icono
        self._etiqueta= etiqueta
        self._texto_valor= "0"
        self._valor_num= None
        self._valor_mostrado= 0.0
        self._glow= 0.26
        self._anim_glow= None
        self._anim_valor= None

    def _leer_glow(self):
        return self._glow

    def _poner_glow(self, v):
        self._glow= v
        self.update()

    glow= Property(float, _leer_glow, _poner_glow)

    def _leer_valor_mostrado(self):
        return self._valor_mostrado

    def _poner_valor_mostrado(self, v):
        self._valor_mostrado= v
        self._texto_valor= f"{v:.0f}"
        self.update()

    valor_mostrado= Property(float, _leer_valor_mostrado, _poner_valor_mostrado)

    def actualizar(self, valor, alerta=False, color=None):
        if color:
            self._color= QColor(color)
        if isinstance(valor, (int, float)):
            anterior= self._valor_num if self._valor_num is not None else valor
            self._valor_num= valor
            self._animar_conteo(anterior, valor)
        else:
            self._valor_num= None
            self._texto_valor= str(valor)
            self.update()
        self._alternar_pulso(alerta)

    def _animar_conteo(self, desde, hasta):
        if self._anim_valor:
            self._anim_valor.stop()
        if desde == hasta:
            self._valor_mostrado= hasta
            self._texto_valor= f"{hasta:.0f}"
            self.update()
            return
        anim= QPropertyAnimation(self, b"valor_mostrado", self)
        anim.setStartValue(float(desde))
        anim.setEndValue(float(hasta))
        anim.setDuration(480)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_valor= anim
        anim.start()

    def _alternar_pulso(self, activo):
        if self._anim_glow:
            self._anim_glow.stop()
            self._anim_glow= None
        if activo:
            self._anim_glow= _crear_pulso(self, b"glow", 0.24, 1.0, duracion=950)
            self._anim_glow.start()
        else:
            self._glow= 0.26
            self.update()

    def pausar(self):
        if self._anim_glow:
            self._anim_glow.pause()

    def reanudar(self):
        if self._anim_glow:
            self._anim_glow.resume()

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r= QRectF(self.rect()).adjusted(2, 2, -2, -2)
        radio= 14.0
        color= self._color
        g= max(0.0, min(1.0, self._glow))

        #Sombra en capas (simulada, sin QGraphicsEffect): un par de rectángulos apenas desplazados hacia abajo que se
        #van desvaneciendo, dan la sensación de elevación de una tarjeta 'flotando' sobre el fondo.
        for offset, alpha in ((5, 0.05), (2, 0.07)):
            sombra= QColor(0, 0, 0, int(255 * alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(sombra)
            painter.drawRoundedRect(r.adjusted(1, offset, -1, offset - 1), radio, radio)

        if g > 0.35:
            intensidad= (g - 0.35) / 0.65
            for i, factor in enumerate((7, 3.5)):
                halo= QColor(color)
                halo.setAlphaF(0.11 * intensidad * (1 - i * 0.45))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                expandir= factor * intensidad
                painter.drawRoundedRect(r.adjusted(-expandir, -expandir, expandir, expandir),
                                         radio + expandir, radio + expandir)

        #Fondo tipo 'vidrio': degradado vertical sutil (más claro arriba) en vez de un relleno plano, para dar
        #profundidad sin costo extra de repintado.
        fondo= QLinearGradient(r.topLeft(), r.bottomLeft())
        c_arriba= QColor(color); c_arriba.setAlphaF(0.10 + 0.09 * g)
        c_abajo= QColor(color); c_abajo.setAlphaF(0.04 + 0.05 * g)
        fondo.setColorAt(0.0, c_arriba)
        fondo.setColorAt(1.0, c_abajo)
        borde= QColor(color)
        borde.setAlphaF(0.30 + 0.45 * g)
        painter.setBrush(fondo)
        pluma= QPen(borde)
        pluma.setWidthF(1.3 + 0.6 * g)
        painter.setPen(pluma)
        painter.drawRoundedRect(r, radio, radio)

        #Filo superior brillante (un hilo de luz de 1px) que refuerza el efecto vidrio.
        brillo= QColor(255, 255, 255, 40)
        painter.setPen(QPen(brillo, 1))
        painter.drawLine(QPointF(r.left() + radio * 0.6, r.top() + 1),
                          QPointF(r.right() - radio * 0.6, r.top() + 1))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(r.left() + 12, r.top() + 6, r.width() - 24, 3), 1.5, 1.5)

        rect_icono= QRectF(r.left() + 12, r.top() + 10, r.width() - 24, 22)
        if self._icono:
            pix_icono= pixmap_emoji(self._icono, 20)
            if not pix_icono.isNull():
                painter.drawPixmap(int(rect_icono.left()), int(rect_icono.top()), pix_icono)

        f_valor= QFont()
        f_valor.setPointSizeF(19)
        f_valor.setBold(True)
        painter.setFont(f_valor)
        painter.setPen(color)
        rect_valor= QRectF(r.left() + 12, rect_icono.bottom() + 2, r.width() - 24, 27)
        painter.drawText(rect_valor, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._texto_valor)

        f_etq= QFont()
        f_etq.setPointSizeF(8.3)
        painter.setFont(f_etq)
        painter.setPen(color)
        alto_disponible= max(18.0, r.bottom() - (rect_valor.bottom() + 3) - 4)
        rect_etq= QRectF(r.left() + 12, rect_valor.bottom() + 3, r.width() - 24, alto_disponible)
        painter.drawText(rect_etq, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft |
                          Qt.AlignmentFlag.AlignTop, self._etiqueta)


class AnilloProgreso(QWidget):
    """Anillo de progreso pintado a mano, con barrido animado. Complementa a
    las tarjetas cuando lo que importa no es un conteo sino un porcentaje de
    avance (ej. '% de competencias evaluadas')."""

    def __init__(self, color, parent=None, diametro=84, grosor=9):
        super().__init__(parent)
        self._color= QColor(color)
        self._grosor= grosor
        self._progreso= 0.0
        self._texto= "0%"
        self.setFixedSize(diametro, diametro)
        self._anim= None

    def _leer_progreso(self):
        return self._progreso

    def _poner_progreso(self, v):
        self._progreso= v
        self.update()

    progreso= Property(float, _leer_progreso, _poner_progreso)

    def actualizar(self, fraccion, texto=None, color=None):
        fraccion= max(0.0, min(1.0, fraccion))
        if color:
            self._color= QColor(color)
        self._texto= texto if texto is not None else f"{int(round(fraccion * 100))}%"
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"progreso", self)
        anim.setStartValue(self._progreso)
        anim.setEndValue(fraccion)
        anim.setDuration(600)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim= anim
        anim.start()

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen= self._grosor / 2 + 2
        rect= QRectF(margen, margen, self.width() - 2 * margen, self.height() - 2 * margen)

        pista= QColor(self._color)
        pista.setAlphaF(0.14)
        pluma_pista= QPen(pista)
        pluma_pista.setWidthF(self._grosor)
        pluma_pista.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pluma_pista)
        painter.drawArc(rect, 90 * 16, -360 * 16)

        if self._progreso > 0:
            #Degradado cónico (más claro donde empieza el trazo, más intenso donde termina) para que el anillo se lea como
            #un barrido de luz, no una simple franja de color sólido.
            grad= QConicalGradient(rect.center(), 90)
            claro= QColor(self._color).lighter(145)
            grad.setColorAt(0.0, claro)
            grad.setColorAt(min(0.999, self._progreso), self._color)
            grad.setColorAt(1.0, claro)
            pluma= QPen(QBrush(grad), self._grosor)
            pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pluma)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * self._progreso))

            #Punto de brillo en la punta del trazo, como remate del barrido.
            angulo_rad= math.radians(90 - 360 * self._progreso)
            radio= rect.width() / 2
            px= rect.center().x() + radio * math.cos(angulo_rad)
            py= rect.center().y() - radio * math.sin(angulo_rad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 210))
            painter.drawEllipse(QPointF(px, py), self._grosor * 0.28, self._grosor * 0.28)

        painter.setPen(self._color)
        f= QFont()
        f.setPointSizeF(13)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._texto)


class BarraSegmentada(QWidget):
    """Barra horizontal proporcional (una franja por estado) con transición
    animada. Usa los mismos colores que las tarjetas, así que funciona como
    una 'leyenda visual' de la sección completa de un vistazo — no solo los
    números sueltos, sino su proporción real."""

    def __init__(self, parent=None, alto=20):
        super().__init__(parent)
        self.setMinimumHeight(alto)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._inicio= []  #[(fraccion, color), ...]
        self._fin= []
        self._t= 1.0
        self._anim= None

    def _leer_t(self):
        return self._t

    def _poner_t(self, v):
        self._t= v
        self.update()

    t= Property(float, _leer_t, _poner_t)

    def actualizar(self, datos):
        """datos: lista de (etiqueta, valor, color). Solo se pintan las franjas;
        las tarjetas de arriba ya hacen de leyenda con esos mismos colores."""
        total= sum(max(0, v) for _, v, _ in datos) or 1
        nuevo_fin= [(max(0, v) / total, color) for _, v, color in datos]
        anterior= self._interpolado() if (self._inicio and len(self._inicio) == len(nuevo_fin)) else\
            [(0.0, c) for _, c in nuevo_fin]
        self._inicio= anterior
        self._fin= nuevo_fin
        self._t= 0.0
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"t", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(550)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim= anim
        anim.start()

    def _interpolado(self):
        t= self._t
        return [(f0 + (f1 - f0) * t, c) for (f0, c), (f1, _) in zip(self._inicio, self._fin)]

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect= QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if rect.width() <= 0 or not self._fin:
            return
        radio= rect.height() / 2
        recorte= QPainterPath()
        recorte.addRoundedRect(rect, radio, radio)
        painter.setClipPath(recorte)
        painter.setPen(Qt.PenStyle.NoPen)
        x= rect.left()
        for frac, color in self._interpolado():
            ancho= frac * rect.width()
            if ancho <= 0:
                continue
            base= QColor(color)
            grad= QLinearGradient(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            grad.setColorAt(0.0, base.lighter(112))
            grad.setColorAt(1.0, base)
            painter.setBrush(grad)
            painter.drawRect(QRectF(x, rect.top(), ancho, rect.height()))
            x += ancho
        #Hilo de brillo superior (sheen), tipo vidrio, sobre toda la barra.
        brillo= QLinearGradient(QPointF(rect.left(), rect.top()), QPointF(rect.left(), rect.top() + rect.height() * 0.55))
        brillo.setColorAt(0.0, QColor(255, 255, 255, 55))
        brillo.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(brillo)
        painter.drawRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.55))
        painter.setClipping(False)


def _crear_panel_dashboard():
    """Contenedor con fondo sutil y bordes redondeados para agrupar visualmente
    una fila de tarjetas/gráficos de resumen (en vez de dejarlas flotando sueltas
    sobre el fondo de la pestaña, como antes). El color real se aplica desde
    actualizar_tema(), vía el objectName, así respeta claro/oscuro igual que
    el resto del módulo."""
    panel= QFrame()
    panel.setObjectName("PanelDashboard")
    lay= QHBoxLayout(panel)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(16)
    return panel


class GraficoDona(QWidget):
    """Anillo multi-segmento ('donut') pintado a mano: reparte el 100% entre
    varias categorías con un barrido animado por segmento y un total grande al
    centro. Es la versión 'de conjunto' de AnilloProgreso — en vez de una sola
    fracción, deja leer de un vistazo la composición completa de la sección
    (ej. cuántas materias Aprobadas/Reprobadas/En RP tiene el boletín), algo
    que una fila de tarjetas sueltas no transmite tan bien."""

    def __init__(self, parent=None, diametro=118, grosor=17):
        super().__init__(parent)
        self.setFixedSize(diametro, diametro)
        self._grosor= grosor
        self._segmentos_fin= []    #[(fraccion, color), ...]
        self._segmentos_inicio= []
        self._t= 1.0
        self._anim= None
        self._total_texto= "0"
        self._etiqueta= ""
        self._color_texto= QColor("#0F172A")
        self._color_etiqueta= QColor("#64748B")

    def _leer_t(self):
        return self._t

    def _poner_t(self, v):
        self._t= v
        self.update()

    t= Property(float, _leer_t, _poner_t)

    def establecer_color_texto(self, color_prim, color_sec=None):
        self._color_texto= QColor(color_prim)
        if color_sec:
            self._color_etiqueta= QColor(color_sec)
        self.update()

    def actualizar(self, datos, total_texto=None, etiqueta=""):
        """datos: lista de (nombre, valor, color_hex). Los valores <= 0 se
        ignoran para no dejar segmentos de ancho residual invisible."""
        datos= [(n, v, c) for n, v, c in datos if v and v > 0]
        total= sum(v for _, v, _ in datos) or 1
        nuevo_fin= [(v / total, c) for _, v, c in datos]
        anterior= self._interpolado() if (self._segmentos_inicio and
            len(self._segmentos_inicio) == len(nuevo_fin)) else [(0.0, c) for _, c in nuevo_fin]
        self._segmentos_inicio= anterior
        self._segmentos_fin= nuevo_fin
        self._etiqueta= etiqueta
        self._total_texto= total_texto if total_texto is not None else str(int(sum(v for _, v, _ in datos)))
        self._t= 0.0
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"t", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(650)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim= anim
        anim.start()

    def _interpolado(self):
        t= self._t
        return [(f0 + (f1 - f0) * t, c) for (f0, c), (f1, _) in zip(self._segmentos_inicio, self._segmentos_fin)]

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen= self._grosor / 2 + 3
        rect= QRectF(margen, margen, self.width() - 2 * margen, self.height() - 2 * margen)

        if not self._segmentos_fin:
            pista= QColor("#6B7280")
            pista.setAlphaF(0.16)
            pluma_pista= QPen(pista)
            pluma_pista.setWidthF(self._grosor)
            pluma_pista.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pluma_pista)
            painter.drawArc(rect, 90 * 16, -360 * 16)
        else:
            #Pequeño espacio entre segmentos (estilo donut 'separado') para que cada categoría se distinga aunque los
            #colores sean parecidos.
            n= len(self._segmentos_fin)
            espacio= min(2.4 * 16, (360 * 16 / max(n, 1)) * 0.12) if n > 1 else 0
            angulo= 90 * 16
            for frac, color in self._interpolado():
                extension= -int(360 * 16 * frac)
                if extension == 0:
                    continue
                ext_dibujo= extension + espacio if extension < -espacio else extension / 2 or extension
                pluma= QPen(QColor(color))
                pluma.setWidthF(self._grosor)
                pluma.setCapStyle(Qt.PenCapStyle.RoundCap if n > 1 else Qt.PenCapStyle.FlatCap)
                painter.setPen(pluma)
                painter.drawArc(rect, int(angulo), int(ext_dibujo))
                angulo += extension

        painter.setPen(self._color_texto)
        f= QFont()
        f.setPointSizeF(16)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._total_texto)


class MedidorGauge(QWidget):
    """Medidor semicircular (180°) pintado a mano, con 3 zonas de referencia
    fijas (rojo/ámbar/verde) como pista de fondo y un arco de valor animado
    encima, rematado por un punto de brillo. Da una lectura de 'salud general'
    de un vistazo (ej. % de materias al día en una sección) que una tarjeta
    numérica sola no transmite tan bien."""

    def __init__(self, parent=None, ancho=190, alto=150, grosor=15):
        super().__init__(parent)
        self.setFixedSize(ancho, alto)
        self._grosor= grosor
        self._valor= 0.0
        self._texto= "0%"
        self._etiqueta= ""
        self._anim= None
        self._color_texto= QColor("#0F172A")
        self._color_etiqueta= QColor("#64748B")

    def _leer_valor(self):
        return self._valor

    def _poner_valor(self, v):
        self._valor= v
        self.update()

    valor= Property(float, _leer_valor, _poner_valor)

    def establecer_color_texto(self, color_prim, color_sec=None):
        self._color_texto= QColor(color_prim)
        if color_sec:
            self._color_etiqueta= QColor(color_sec)
        self.update()

    def actualizar(self, fraccion, texto=None, etiqueta=None):
        fraccion= max(0.0, min(1.0, fraccion))
        self._texto= texto if texto is not None else f"{int(round(fraccion * 100))}%"
        if etiqueta is not None:
            self._etiqueta= etiqueta
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"valor", self)
        anim.setStartValue(self._valor)
        anim.setEndValue(fraccion)
        anim.setDuration(700)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim= anim
        anim.start()

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen= self._grosor / 2 + 4
        diametro= min(self.width() - 2 * margen, 2 * (self.height() - margen - 40))
        diametro= max(diametro, 40)
        rect= QRectF((self.width() - diametro) / 2, margen, diametro, diametro)
        centro= rect.center()
        radio= diametro / 2

        for color, ini, fin in (("#EF4444", 0.0, 0.4), ("#F59E0B", 0.4, 0.75), ("#10B981", 0.75, 1.0)):
            pista= QColor(color)
            pista.setAlphaF(0.24)
            pluma= QPen(pista)
            pluma.setWidthF(self._grosor)
            pluma.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pluma)
            angulo_inicio= 180 * 16 - int(ini * 180 * 16)
            extension= -int((fin - ini) * 180 * 16)
            painter.drawArc(rect, angulo_inicio, extension)

        if self._valor > 0.001:
            color_valor= "#EF4444" if self._valor < 0.4 else ("#F59E0B" if self._valor < 0.75 else "#10B981")
            grad= QConicalGradient(centro, 180)
            grad.setColorAt(0.0, QColor(color_valor).lighter(130))
            grad.setColorAt(0.5, QColor(color_valor))
            pluma_valor= QPen(QBrush(grad), self._grosor)
            pluma_valor.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pluma_valor)
            painter.drawArc(rect, 180 * 16, -int(180 * 16 * self._valor))

            angulo_rad= math.radians(180 - 180 * self._valor)
            px= centro.x() + radio * math.cos(angulo_rad)
            py= centro.y() - radio * math.sin(angulo_rad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.drawEllipse(QPointF(px, py), 5.5, 5.5)
            painter.setBrush(QColor(color_valor))
            painter.drawEllipse(QPointF(px, py), 3.2, 3.2)

        painter.setPen(self._color_texto)
        f= QFont()
        f.setPointSizeF(18)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(0, centro.y() + 4, self.width(), 30), Qt.AlignmentFlag.AlignCenter, self._texto)
        if self._etiqueta:
            painter.setPen(self._color_etiqueta)
            f2= QFont()
            f2.setPointSizeF(8.0)
            painter.setFont(f2)
            painter.drawText(QRectF(4, centro.y() + 32, self.width() - 8, 18),
                              Qt.AlignmentFlag.AlignCenter, self._etiqueta)


class TimelineEvaluacion(QWidget):
    """Diagrama horizontal de etapas (ej. Año → Completiva → Extraordinaria →
    Especial) pintado a mano: cada nodo crece y se ilumina cuando hay materias
    'esperando' en esa etapa ahora mismo, con el conteo dentro del propio nodo.
    Así se ve de un vistazo en qué parte de la cascada se concentra el trabajo
    pendiente, en vez de tener que leer una lista de números sueltos."""

    def __init__(self, parent=None, alto=100):
        super().__init__(parent)
        self.setMinimumHeight(alto)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._etapas= []          #[(etiqueta, color_hex, conteo), ...]
        self._radios_inicio= []
        self._radios_fin= []
        self._t= 1.0
        self._anim= None
        self._color_texto= QColor("#0F172A")

    def _leer_t(self):
        return self._t

    def _poner_t(self, v):
        self._t= v
        self.update()

    t= Property(float, _leer_t, _poner_t)

    def establecer_color_texto(self, color):
        self._color_texto= QColor(color)
        self.update()

    def actualizar(self, etapas):
        """etapas: lista de (etiqueta, color_hex, conteo), en el orden en que
        deben leerse de izquierda a derecha."""
        nuevo_fin= [16.0 if conteo > 0 else 9.0 for _, _, conteo in etapas]
        if len(self._radios_fin) == len(nuevo_fin) and self._etapas:
            anterior= self._interpolado()
        else:
            anterior= [9.0] * len(nuevo_fin)
        self._etapas= etapas
        self._radios_inicio= anterior
        self._radios_fin= nuevo_fin
        self._t= 0.0
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"t", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(520)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim= anim
        anim.start()

    def _interpolado(self):
        t= self._t
        return [r0 + (r1 - r0) * t for r0, r1 in zip(self._radios_inicio, self._radios_fin)]

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        n= len(self._etapas)
        if n == 0:
            #En vez de dejar el panel completamente en blanco (confuso: no se entiende qué es ese recuadro vacío), explica
            #qué va a mostrar y qué hacer para verlo.
            painter.setPen(QColor(148, 163, 184, 200))
            f= QFont()
            f.setPointSizeF(9.0)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "Selecciona estudiante y presiona \"Calcular\" para ver aquí\n"
                              "la cascada de evaluaciones (Año Completiva Extraordinaria Especial)")
            return
        radios= self._interpolado() if len(self._radios_fin) == n else [9.0] * n
        margen_h= 40.0
        y= 32.0
        ancho_util= max(1.0, self.width() - 2 * margen_h)
        xs= [margen_h + (ancho_util * i / (n - 1) if n > 1 else ancho_util / 2) for i in range(n)]

        pluma_base= QPen(QColor(148, 163, 184, 90), 3)
        painter.setPen(pluma_base)
        painter.drawLine(QPointF(xs[0], y), QPointF(xs[-1], y))

        for i in range(n - 1):
            _, color_a, conteo_a = self._etapas[i]
            _, color_b, conteo_b = self._etapas[i + 1]
            if conteo_a > 0 or conteo_b > 0:
                grad= QLinearGradient(QPointF(xs[i], y), QPointF(xs[i + 1], y))
                ca, cb = QColor(color_a), QColor(color_b)
                grad.setColorAt(0, ca)
                grad.setColorAt(1, cb)
                painter.setPen(QPen(QBrush(grad), 3))
                painter.drawLine(QPointF(xs[i], y), QPointF(xs[i + 1], y))

        for i, (etiqueta, color_hex, conteo) in enumerate(self._etapas):
            color= QColor(color_hex)
            r= radios[i]
            cx, cy = xs[i], y
            if conteo > 0:
                halo= QColor(color)
                halo.setAlphaF(0.20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(halo)
                painter.drawEllipse(QPointF(cx, cy), r + 9, r + 9)
            painter.setPen(QPen(color, 2.4))
            painter.setBrush(color if conteo > 0 else QColor(0, 0, 0, 0))
            painter.drawEllipse(QPointF(cx, cy), r, r)
            if conteo > 0:
                painter.setPen(Qt.GlobalColor.white)
                f= QFont()
                f.setPointSizeF(8.3)
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r),
                                  Qt.AlignmentFlag.AlignCenter, str(conteo))
            painter.setPen(self._color_texto)
            f2= QFont()
            f2.setPointSizeF(8.3)
            f2.setBold(conteo > 0)
            painter.setFont(f2)
            painter.drawText(QRectF(cx - 60, cy + r + 8, 120, 30),
                              Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                              etiqueta)


class LineaTendencia(QWidget):
    """Mini-gráfico de línea (sparkline) con relleno degradado, que se 'dibuja'
    de izquierda a derecha al actualizarse. Sirve para leer una tendencia (ej.
    promedio por periodo a lo largo del año) sin necesitar ejes ni una tabla
    aparte — el tipo de vistazo rápido que una tarjeta numérica no puede dar."""

    def __init__(self, parent=None, alto=68, color="#6366F1"):
        super().__init__(parent)
        self.setMinimumHeight(alto)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._color= QColor(color)
        self._valores= []
        self._umbral= None
        self._color_vacio= QColor(148, 163, 184, 200)
        self._t= 1.0
        self._anim= None

    def _leer_t(self):
        return self._t

    def _poner_t(self, v):
        self._t= v
        self.update()

    t= Property(float, _leer_t, _poner_t)

    def establecer_color_texto(self, color):
        self._color_vacio= QColor(color)
        self.update()

    def actualizar(self, valores, umbral=None, color=None):
        """valores: lista de números en orden cronológico (mínimo 2 para trazar
        una línea). umbral: valor de referencia (ej. nota mínima) que se marca
        como línea punteada de fondo."""
        if color:
            self._color= QColor(color)
        self._valores= [v for v in valores if v is not None]
        self._umbral= umbral
        self._t= 0.0
        if self._anim:
            self._anim.stop()
        anim= QPropertyAnimation(self, b"t", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(750)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim= anim
        anim.start()

    def paintEvent(self, event):
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect= QRectF(self.rect()).adjusted(6, 8, -6, -8)
        if len(self._valores) < 2 or rect.width() <= 0:
            painter.setPen(self._color_vacio)
            f= QFont()
            f.setPointSizeF(8.5)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "Sin suficientes periodos con notas para mostrar tendencia")
            return

        vmin, vmax = min(self._valores), max(self._valores)
        if vmax == vmin:
            vmin -= 1
            vmax += 1
        n= len(self._valores)
        pts_totales= [QPointF(
            rect.left() + rect.width() * (i / (n - 1) if n > 1 else 0),
            rect.bottom() - (v - vmin) / (vmax - vmin) * rect.height()
        ) for i, v in enumerate(self._valores)]

        cantidad= 1 + self._t * (n - 1)
        idx_completo= min(n - 1, int(cantidad))
        frac_extra= cantidad - idx_completo
        pts= list(pts_totales[:idx_completo + 1])
        if idx_completo < n - 1 and frac_extra > 0:
            a, b = pts_totales[idx_completo], pts_totales[idx_completo + 1]
            pts.append(QPointF(a.x() + (b.x() - a.x()) * frac_extra, a.y() + (b.y() - a.y()) * frac_extra))
        if len(pts) < 2:
            return

        if self._umbral is not None and vmin <= self._umbral <= vmax:
            y_umbral= rect.bottom() - (self._umbral - vmin) / (vmax - vmin) * rect.height()
            pluma_u= QPen(QColor(148, 163, 184, 140), 1)
            pluma_u.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pluma_u)
            painter.drawLine(QPointF(rect.left(), y_umbral), QPointF(rect.right(), y_umbral))

        relleno= QPainterPath()
        relleno.moveTo(pts[0].x(), rect.bottom())
        for p in pts:
            relleno.lineTo(p)
        relleno.lineTo(pts[-1].x(), rect.bottom())
        relleno.closeSubpath()
        grad= QLinearGradient(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        c_arriba= QColor(self._color); c_arriba.setAlphaF(0.32)
        c_abajo= QColor(self._color); c_abajo.setAlphaF(0.0)
        grad.setColorAt(0, c_arriba)
        grad.setColorAt(1, c_abajo)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawPath(relleno)

        linea= QPainterPath()
        linea.moveTo(pts[0])
        for p in pts[1:]:
            linea.lineTo(p)
        pluma= QPen(self._color, 2.6)
        pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pluma)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(linea)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        for p in pts_totales[:idx_completo]:
            painter.drawEllipse(p, 3.0, 3.0)
        if idx_completo == n - 1:
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(pts_totales[-1], 4.4, 4.4)
            painter.setBrush(self._color)
            painter.drawEllipse(pts_totales[-1], 2.6, 2.6)


def _sistema_calificacion_actual():
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT sistema_calificacion FROM configuracion WHERE id=1")
    cfg= c.fetchone()
    conn.close()
    return cfg["sistema_calificacion"] if cfg else "Numérico (Personalizado)"
def calcular_nota_final(calificaciones, metodo):
    if not calificaciones:
        return None
    if metodo == "Promedio Simple":
        return sum(c["valor"] for c in calificaciones) / len(calificaciones)
    if metodo == "Mayor Nota":
        return max(c["valor"] for c in calificaciones)
    if metodo == "Suma de Puntos":
        return sum(c["valor"] * (c["peso"] / 100 if c["peso"] else 1) for c in calificaciones)
    total_peso= sum(c["peso"] for c in calificaciones)
    if total_peso <= 0:
        return sum(c["valor"] for c in calificaciones) / len(calificaciones)
    return sum(c["valor"] * (c["peso"] / total_peso) for c in calificaciones)
def _datos_institucion():
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT nombre_institucion, logo_path, direccion, telefono, correo,
                 firma_path, pie_pagina FROM configuracion WHERE id=1""")
    cfg= c.fetchone()
    conn.close()
    if not cfg:
        return {"nombre": "AcaDeXI", "logo": None, "direccion": "", "telefono": "", "correo": "",
                "firma": None, "pie_pagina": ""}
    return {
        "nombre": cfg["nombre_institucion"] or "AcaDeXI",
        "logo": cfg["logo_path"] if cfg["logo_path"] and os.path.exists(cfg["logo_path"]) else None,
        "direccion": cfg["direccion"] or "",
        "telefono": cfg["telefono"] or "",
        "correo": cfg["correo"] or "",
        "firma": cfg["firma_path"] if cfg["firma_path"] and os.path.exists(cfg["firma_path"]) else None,
        "pie_pagina": cfg["pie_pagina"] or "",
    }
def _dibujar_encabezado(cvs, ancho, alto, institucion, subtitulo):
    from reportlab.lib.utils import ImageReader
    y= alto - 55
    if institucion["logo"]:
        try:
            img= ImageReader(institucion["logo"])
            iw, ih = img.getSize()
            alto_img= 50
            ancho_img= alto_img * (iw / ih)
            cvs.drawImage(img, 50, y - 30, width=ancho_img, height=alto_img,
                          preserveAspectRatio= True, mask='auto')
        except Exception:
            pass
    cvs.setFont("Helvetica-Bold", 16)
    cvs.drawCentredString(ancho / 2, y, institucion["nombre"])
    y -= 20
    if institucion["direccion"] or institucion["telefono"] or institucion["correo"]:
        cvs.setFont("Helvetica", 8)
        linea= "  |   ".join(x for x in (institucion["direccion"], institucion["telefono"], institucion["correo"]) if x)
        cvs.drawCentredString(ancho / 2, y, linea)
        y -= 18
    cvs.setFont("Helvetica-Bold", 13)
    cvs.drawCentredString(ancho / 2, y, subtitulo)
    y -= 25
    return y
def _dibujar_pie_pagina(cvs, ancho, institucion, incluir_firma=True):
    from reportlab.lib.utils import ImageReader
    y_firma= 95
    if incluir_firma and institucion.get("firma"):
        try:
            img= ImageReader(institucion["firma"])
            iw, ih = img.getSize()
            alto_img= 40
            ancho_img= alto_img * (iw / ih)
            x_firma= ancho - 60 - ancho_img
            cvs.drawImage(img, x_firma, y_firma, width=ancho_img, height=alto_img,
                          preserveAspectRatio= True, mask='auto')
            cvs.setFont("Helvetica", 8)
            cvs.line(x_firma, y_firma - 4, x_firma + ancho_img, y_firma - 4)
            cvs.drawCentredString(x_firma + ancho_img / 2, y_firma - 14, "Firma Autorizada")
        except Exception:
            pass
    cvs.setFont("Helvetica", 7.5)
    cvs.setFillGray(0.4)
    cvs.line(50, 60, ancho - 50, 60)
    pie_texto= institucion.get("pie_pagina") or ""
    if pie_texto:
        cvs.drawCentredString(ancho / 2, 48, pie_texto)
    cvs.drawCentredString(ancho / 2, 36, f"Documento generado por AcaDeXI el {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    cvs.setFillGray(0)


def _envolver_texto(cvs, texto, fuente, tamano, ancho_max):
    """Divide `texto` en líneas que no excedan `ancho_max` puntos con la
    fuente/tamaño dados, partiendo siempre por palabra completa (nunca a
    mitad de una). Evita el problema de nombres de materia largos
    desbordando la celda o teniendo que truncarlos con "..." -en vez de
    eso la fila simplemente crece lo que haga falta."""
    palabras= (texto or "").split()
    if not palabras:
        return [""]
    lineas= []
    actual= palabras[0]
    for palabra in palabras[1:]:
        candidata= f"{actual} {palabra}"
        if cvs.stringWidth(candidata, fuente, tamano) <= ancho_max:
            actual= candidata
        else:
            lineas.append(actual)
            actual= palabra
    lineas.append(actual)
    return lineas


def _recortar_a_ancho(cvs, texto, fuente, tamano, ancho_max):
    """Para celdas de UNA sola línea (estado, encabezados de tarjeta) que no
    pueden crecer en alto: si el texto no cabe, lo recorta con "…" en vez de
    dejar que reportlab lo dibuje encimado o fuera de la celda."""
    texto= texto or ""
    if cvs.stringWidth(texto, fuente, tamano) <= ancho_max:
        return texto
    while texto and cvs.stringWidth(texto + "…", fuente, tamano) > ancho_max:
        texto= texto[:-1]
    return (texto + "…") if texto else ""


def competencias_de_materia_grado(materia_id, grado_id, solo_activas=True):
    """Devuelve las Competencias Específicas (codigo, descripcion...) definidas en el
    currículo para una materia+grado, en el orden en que deben dibujarse en pantalla.
    Motor dinámico: no hay columnas fijas CE1/CE2/CE3, se itera lo que exista."""
    if materia_id is None or grado_id is None:
        return []
    conn= obtener_conexion()
    c= conn.cursor()
    condicion_estado= "AND estado='Activa'" if solo_activas else ""
    c.execute(f"""SELECT * FROM competencias_especificas
                 WHERE materia_id=? AND grado_id=? {condicion_estado}
                 ORDER BY orden, codigo""", (materia_id, grado_id))
    filas= [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


def grado_de_estudiante(estudiante_id):
    if estudiante_id is None:
        return None
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT secciones.grado_id FROM estudiantes
                 LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                 WHERE estudiantes.id=?""", (estudiante_id,))
    f= c.fetchone()
    conn.close()
    return f["grado_id"] if f else None


def grados_de_materia(materia_id):
    """Grados en los que se imparte una materia, según los horarios ya armados
    (una materia puede darse en varios grados: distintas CE por cada uno)."""
    if materia_id is None:
        return []
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT DISTINCT grados.id, grados.nombre FROM horarios
                 LEFT JOIN secciones ON horarios.seccion_id = secciones.id
                 LEFT JOIN grados ON secciones.grado_id = grados.id
                 WHERE horarios.materia_id=? AND grados.id IS NOT NULL
                 ORDER BY grados.orden, grados.nombre""", (materia_id,))
    filas= [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


class DialogoCompetenciasEspecificas(QDialog):
    """Permite marcar con cuáles Competencias Específicas (CE) del currículo de la
    materia+grado se vincula una evidencia (examen, proyecto, práctica...). Una sola
    evidencia puede calificar varias CE a la vez — esa es justo la idea central del
    modelo curricular dinámico de MINERD."""

    def __init__(self, materia_id, grado_id, seleccionadas_ids=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vincular a Competencias Específicas")
        self.setMinimumWidth(460)
        self._seleccionadas_ids= set(seleccionadas_ids or [])
        self._competencias= competencias_de_materia_grado(materia_id, grado_id)

        layout= QVBoxLayout(self)
        info= QLabel("Marca las Competencias Específicas (CE) que esta evidencia califica. "
                       "Una evidencia (examen, proyecto, práctica) puede validar varias CE a la vez.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.lista= QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        if not self._competencias:
            self.lista.addItem("No hay Competencias Específicas definidas para esta materia y grado "
                                "(configúralas en la pestaña Currículo).")
            self.lista.setEnabled(False)
        for comp in self._competencias:
            item= QListWidgetItem(f"{comp['codigo']} — {comp['descripcion']}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if comp["id"] in self._seleccionadas_ids
                                else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, comp["id"])
            self.lista.addItem(item)
        layout.addWidget(self.lista)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def seleccionadas(self):
        ids= []
        for i in range(self.lista.count()):
            item= self.lista.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids


class DialogoRecuperacionPedagogica(QDialog):
    """Submódulo de RP: fecha, actividades realizadas, observación del docente,
    responsable y la nota resultante. Reemplaza el antiguo QInputDialog de una sola
    cifra, que no dejaba constancia de qué se hizo para reforzar al estudiante."""

    def __init__(self, datos_actuales=None, docente_sugerido="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recuperación Pedagógica (RP)")
        self.setMinimumWidth(440)
        datos_actuales= datos_actuales or {}

        layout= QVBoxLayout(self)
        info= QLabel("Registra el proceso de Recuperación Pedagógica: qué se hizo para reforzar "
                       "al estudiante y la nota obtenida al final del proceso.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form= QGridLayout()
        form.addWidget(QLabel("Fecha:"), 0, 0)
        self.fecha= QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("yyyy-MM-dd")
        fecha_previa= datos_actuales.get("fecha")
        self.fecha.setDate(QDate.fromString(fecha_previa[:10], "yyyy-MM-dd") if fecha_previa
                            else QDate.currentDate())
        form.addWidget(self.fecha, 0, 1)

        form.addWidget(QLabel("Docente responsable:"), 0, 2)
        self.docente= QLineEdit(datos_actuales.get("docente_responsable") or docente_sugerido)
        limitar_campo_texto(self.docente, 300)
        form.addWidget(self.docente, 0, 3)

        form.addWidget(QLabel("Nota RP (0-100):"), 1, 0)
        self.nota= QDoubleSpinBox()
        self.nota.setRange(0, 100)
        self.nota.setDecimals(2)
        self.nota.setValue(datos_actuales.get("nota_rp") or 0)
        form.addWidget(self.nota, 1, 1)
        layout.addLayout(form)

        layout.addWidget(QLabel("Actividades realizadas durante la RP:"))
        self.actividades= QTextEdit()
        limitar_campo_texto(self.actividades, 5000)
        self.actividades.setPlainText(datos_actuales.get("actividades_realizadas") or "")
        self.actividades.setMaximumHeight(80)
        layout.addWidget(self.actividades)

        layout.addWidget(QLabel("Observación del docente:"))
        self.observacion= QTextEdit()
        limitar_campo_texto(self.observacion, 5000)
        self.observacion.setPlainText(datos_actuales.get("observacion") or "")
        self.observacion.setMaximumHeight(80)
        layout.addWidget(self.observacion)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def datos(self):
        return {
            "fecha": self.fecha.date().toString("yyyy-MM-dd"),
            "docente_responsable": self.docente.text().strip(),
            "nota_rp": self.nota.value(),
            "actividades_realizadas": self.actividades.toPlainText().strip(),
            "observacion": self.observacion.toPlainText().strip(),
        }


class DialogoEvaluacionFinal(QDialog):
    """Registro de una etapa de la cascada final (Completiva/Extraordinaria/Especial)
    con nota, observación del proceso y responsable de la evaluación."""

    def __init__(self, titulo, datos_actuales=None, docente_sugerido="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(420)
        datos_actuales= datos_actuales or {}

        layout= QVBoxLayout(self)
        form= QGridLayout()
        form.addWidget(QLabel("Nota obtenida (0-100):"), 0, 0)
        self.nota= QDoubleSpinBox()
        self.nota.setRange(0, 100)
        self.nota.setDecimals(2)
        self.nota.setValue(datos_actuales.get("nota") or 0)
        form.addWidget(self.nota, 0, 1)
        form.addWidget(QLabel("Responsable:"), 1, 0)
        self.responsable= QLineEdit(datos_actuales.get("responsable") or docente_sugerido)
        limitar_campo_texto(self.responsable, 300)
        form.addWidget(self.responsable, 1, 1)
        layout.addLayout(form)

        layout.addWidget(QLabel("Observación del proceso:"))
        self.observacion= QTextEdit()
        limitar_campo_texto(self.observacion, 5000)
        self.observacion.setPlainText(datos_actuales.get("observacion") or "")
        self.observacion.setMaximumHeight(80)
        layout.addWidget(self.observacion)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def datos(self):
        return {"nota": self.nota.value(), "responsable": self.responsable.text().strip(),
                "observacion": self.observacion.toPlainText().strip()}


class DialogoIndicadoresLogro(QDialog):
    """CRUD de Indicadores de Logro (IL) de una Competencia Específica. Los
    indicadores son el detalle fino de qué se observa para dar por lograda una
    competencia; una evidencia puede marcar cuáles de ellos validó."""

    def __init__(self, competencia_id, codigo_ce, puede_editar_flag=True, parent=None):
        super().__init__(parent)
        self.competencia_id= competencia_id
        self.puede_editar_flag= puede_editar_flag
        self.id_edicion= None
        self.setWindowTitle(f"Indicadores de Logro — {codigo_ce}")
        self.setMinimumSize(520, 420)

        layout= QVBoxLayout(self)
        info= QLabel("Los Indicadores de Logro describen qué se observa concretamente para dar por "
                       "alcanzada esta competencia. Son opcionales pero recomendados para justificar "
                       "cada evidencia con precisión.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tabla= QTableWidget(0, 3)
        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Código", "Descripción", "Orden"])
        #"Descripción" (col 1) ya absorbe el espacio sobrante como Stretch; con setStretchLastSection(True) también
        #activo, "Orden" (última columna) competiría por ese mismo espacio y quedaría absurdamente ancha. Se desactiva
        #para que solo "Descripción" se estire.
        self.tabla.horizontalHeader().setStretchLastSection(False)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        layout.addWidget(self.tabla, 1)

        form= QGridLayout()
        self.in_codigo= QLineEdit(); self.in_codigo.setPlaceholderText("Código (ej. IL1)")
        limitar_campo_texto(self.in_codigo, 300)
        self.in_descripcion= QLineEdit(); self.in_descripcion.setPlaceholderText("Descripción del indicador")
        limitar_campo_texto(self.in_descripcion, 300)
        self.spin_orden= QSpinBox(); self.spin_orden.setRange(1, 99); self.spin_orden.setValue(1)
        form.addWidget(QLabel("Código:"), 0, 0); form.addWidget(self.in_codigo, 0, 1)
        form.addWidget(QLabel("Orden:"), 0, 2); form.addWidget(self.spin_orden, 0, 3)
        form.addWidget(self.in_descripcion, 1, 0, 1, 4)
        layout.addLayout(form)

        fila_botones= QHBoxLayout()
        self.btn_guardar= QPushButton("Guardar Indicador")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.btn_guardar)
        btn_cargar= QPushButton("Cargar Seleccionado")
        btn_cargar.setIcon(icono_emoji("✏"))
        btn_cargar.setIconSize(_QSize_emoji(16, 16))
        btn_cargar.setObjectName("BtnAccionEditar")
        btn_cargar.clicked.connect(self._cargar_seleccionado)
        fila_botones.addWidget(btn_cargar)
        self.btn_eliminar= QPushButton("Eliminar")
        self.btn_eliminar.setIcon(icono_emoji("🗑"))
        self.btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        self.btn_eliminar.setObjectName("BtnAccionEliminar")
        self.btn_eliminar.clicked.connect(self._eliminar)
        fila_botones.addWidget(self.btn_eliminar)
        fila_botones.addStretch()
        layout.addLayout(fila_botones)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.accept)
        botones.accepted.connect(self.accept)
        layout.addWidget(botones)

        if not puede_editar_flag:
            self.btn_guardar.setEnabled(False)
            self.btn_eliminar.setEnabled(False)
            self.in_codigo.setEnabled(False)
            self.in_descripcion.setEnabled(False)
            self.spin_orden.setEnabled(False)

        self._cargar_tabla()
        centrar_y_al_frente(self, parent)


    def _cargar_tabla(self):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM indicadores_logro WHERE competencia_id=? ORDER BY orden, codigo",
                  (self.competencia_id,))
        filas= [dict(f) for f in c.fetchall()]
        conn.close()
        self.tabla.setRowCount(len(filas))
        with tabla_pausada(self.tabla):
            for i, f in enumerate(filas):
                item_cod= QTableWidgetItem(f["codigo"])
                item_cod.setData(Qt.ItemDataRole.UserRole, f["id"])
                self.tabla.setItem(i, 0, item_cod)
                self.tabla.setItem(i, 1, QTableWidgetItem(f["descripcion"]))
                self.tabla.setItem(i, 2, QTableWidgetItem(str(f["orden"])))
        self.spin_orden.setValue(len(filas) + 1)

    def _guardar(self):
        codigo= self.in_codigo.text().strip()
        descripcion= self.in_descripcion.text().strip()
        if not codigo or not descripcion:
            mostrar_mensaje("advertencia", "Datos incompletos", "Completa código y descripción.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        try:
            if self.id_edicion is None:
                c.execute("""INSERT INTO indicadores_logro (competencia_id, codigo, descripcion, orden)
                             VALUES (?,?,?,?)""",
                          (self.competencia_id, codigo, descripcion, self.spin_orden.value()))
            else:
                c.execute("UPDATE indicadores_logro SET codigo=?, descripcion=?, orden=? WHERE id=?",
                          (codigo, descripcion, self.spin_orden.value(), self.id_edicion))
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            mostrar_mensaje("advertencia", "Código repetido",
                             f"Ya existe un indicador con código '{codigo}' en esta competencia.", self)
            return
        conn.close()
        self.id_edicion= None
        self.in_codigo.clear()
        self.in_descripcion.clear()
        self.btn_guardar.setText("Guardar Indicador")
        self._cargar_tabla()
        desactivar_modo_edicion(self.in_codigo)

    def _cargar_seleccionado(self):
        fila= self.tabla.currentRow()
        if fila < 0:
            return
        self.id_edicion= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        self.in_codigo.setText(self.tabla.item(fila, 0).text())
        self.in_descripcion.setText(self.tabla.item(fila, 1).text())
        self.spin_orden.setValue(int(self.tabla.item(fila, 2).text()))
        self.btn_guardar.setText("Actualizar Indicador")
        activar_modo_edicion(self.in_codigo,
                             f"Editando indicador: {self.in_descripcion.text()}")

    def _eliminar(self):
        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un indicador de la tabla.", self)
            return
        indicador_id= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM indicadores_logro WHERE id=?", (indicador_id,))
        conn.commit()
        conn.close()
        self._cargar_tabla()


class _IndicadorCargaGiratorio(QWidget):
    """Spinner circular animado, dibujado a mano con QPainter (mismo diseño
    que el de main.py, autocontenido aquí para no crear una dependencia
    cruzada entre módulos), usado como contenido de las pestañas perezosas
    mientras se construyen.

    La animación sigue el patrón "Material Design" de progreso indeterminado:
    el arco no gira con largo fijo, sino que crece y encoge mientras rota.
    Quien lo use debe llamar a `.detener()` justo antes de
    reemplazarlo/descartarlo."""

    _DURACION_CICLO_MS= 1400
    _LARGO_MIN= 22
    _LARGO_MAX= 300

    def __init__(self, texto="Cargando…", color="#4F8EF7", color_texto="#8A94A6", parent=None):
        super().__init__(parent)
        self._color= QColor(color)
        self._color_texto= QColor(color_texto)
        self._texto= texto
        self._transcurrido_ms= 0
        self.setMinimumHeight(140)
        self._timer= QTimer(self)
        self._timer.timeout.connect(self._avanzar)
        self._timer.start(16)  #~60 fps

    def detener(self):
        self._timer.stop()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if not self._timer.isActive():
            self._timer.start(16)
        super().showEvent(event)

    def _avanzar(self):
        self._transcurrido_ms= (self._transcurrido_ms + 16) % self._DURACION_CICLO_MS
        self.update()

    def paintEvent(self, event):
        fase= (self._transcurrido_ms / self._DURACION_CICLO_MS) * 2 * math.pi
        rotacion_base= (self._transcurrido_ms / self._DURACION_CICLO_MS) * 720
        largo= self._LARGO_MIN + (self._LARGO_MAX - self._LARGO_MIN) * (0.5 - 0.5 * math.cos(fase))
        inicio= rotacion_base + largo * 0.5

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radio= 18
        centro_x= self.width() / 2
        centro_y= self.height() / 2 - 16
        rect= QRectF(centro_x - radio, centro_y - radio, radio * 2, radio * 2)

        pen_pista= QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 40))
        pen_pista.setWidth(4)
        pen_pista.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_pista)
        painter.drawEllipse(rect)

        pen_arco= QPen(self._color)
        pen_arco.setWidth(4)
        pen_arco.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arco)
        painter.drawArc(rect, int(-inicio * 16), int(largo * 16))

        painter.setPen(self._color_texto)
        rect_texto= QRect(0, int(centro_y + radio + 14), self.width(), 24)
        painter.drawText(rect_texto, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._texto)
        painter.end()


class ModuloCalificaciones(QWidget):
    def __init__(self, main_window):
        #Sin padre de Qt todavía: main.py lo asigna al insertar el módulo en el stack, ya construido (ver
        #_asegurar_modulo_cargado en main.py).
        super().__init__()
        self.main_window= main_window
        self.id_edicion= None
        self._tabs_cargados= set()  #índices de pestañas cuyos combos/tablas ya se poblaron
        self._tarjetas_alerta= []  #tarjetas con 'latido' — se pausan/reanudan según visibilidad
        self._firma_tema_aplicada= None
        self._invalidar_cache()
        self._build_ui()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.actualizar_tema()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):
        self._titulo_modulo_atajos= "Calificaciones"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Registrar calificación", self._guardar_calificacion)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar_formulario)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar calificación seleccionada",
                         self._cargar_calificacion_seleccionada)
        #Borrar una calificación ya registrada es una acción delicada (afecta el historial académico): no se ofrece por
        #atajo en Modo Docente, igual que ya limita datos_locales_docente.py con los datos institucionales.
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar calificación",
                         self._eliminar_calificacion, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+B", "Generar boletín", self._generar_boletin_click)
        registrar_atajo(self, self.main_window, "Ctrl+Shift+P", "Cerrar/abrir periodo",
                         self._alternar_bloqueo_periodo, solo_no_docente=True)

    def _invalidar_cache(self):
        """Limpia el caché de listas base (secciones, materias, periodos, estudiantes,
        permisos) usado durante una 'sesión' de refrescar(). Evita repetir la MISMA
        consulta (ej. 'listar secciones') una vez por cada pestaña/combo que la necesita:
        antes se repetía hasta 5-6 veces solo para abrir el módulo."""
        self._cache_secciones_etiquetadas= None
        self._cache_secciones_con_grado= None
        self._cache_grados= None
        self._cache_materias_activas= None
        self._cache_periodos= None
        self._cache_estudiantes_activos= None
        self._cache_estudiantes_todos= None
        self._cache_permitidas_secciones= _SIN_CARGAR
        self._cache_permitidas_materias= _SIN_CARGAR

    def _grados_lista(self):
        """(id, nombre) de todos los Cursos/Grados, en orden curricular."""
        if self._cache_grados is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")
            self._cache_grados= [(f["id"], f["nombre"]) for f in c.fetchall()]
            conn.close()
        return self._cache_grados

    def _secciones_con_grado(self):
        """Como _secciones_etiquetadas pero incluye grado_id — necesario para poder
        filtrar 'qué secciones pertenecen a este curso' en los combos en cascada."""
        if self._cache_secciones_con_grado is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT secciones.id, secciones.grado_id, secciones.nombre as nombre_plano,
                         (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                         FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id ORDER BY etiqueta""")
            self._cache_secciones_con_grado= [dict(f) for f in c.fetchall()]
            conn.close()
        return self._cache_secciones_con_grado

    def _poblar_combo_curso(self, combo, incluir_todos=False):
        """Llena un combo de Curso/Grado. 'Todos los cursos' queda como opción 0 salvo
        que incluir_todos=False (formularios que exigen elegir un curso concreto antes
        de poder elegir Sección, igual que en la pestaña de Horarios de Materias)."""
        poblar_combo_curso(combo, incluir_todos=incluir_todos)

    def _filtrar_seccion_por_curso(self, combo_curso, combo_seccion, incluir_todas=False):
        """Recarga combo_seccion mostrando solo las secciones del curso elegido en
        combo_curso (o todas, filtradas igual por permisos, si el curso es 'Todos').
        Este es el patrón 'Curso -> Sección' en cascada compartido por TODOS los
        módulos de AcaDeXI (ver filtros_curso_seccion.py), porque filtrar solo por
        sección no alcanza en colegios con varios cursos.

        Cuando incluir_todas=False (formularios que exigen una sección concreta, p.ej.
        Registrar Calificación), NO se listan secciones de otros cursos mezcladas
        mientras no se elija un curso: se deja un placeholder vacío, igual que en la
        pestaña de Horarios de Materias, para que no quede seleccionada por accidente
        una sección de un curso distinto al que se ve en 'Curso'."""
        cascada_seccion_por_curso(combo_curso, combo_seccion, incluir_todas=incluir_todas,
                                   secciones_permitidas= self._permitidas_secciones())

    def _poblar_combo_curso_corto(self, combo):
        """Igual que _poblar_combo_curso, pero con el placeholder acortado a
        'Selecciona un grado'. Usado SOLO en Boletín/Promedios, Historial
        Académico, Desempeño Individual, Seguimiento RP, Evaluaciones Finales,
        Notas por Competencia y Compartir Calificaciones."""
        self._poblar_combo_curso(combo, incluir_todos=False)
        _acortar_placeholder_combo(combo, "Selecciona grado")

    def _filtrar_seccion_por_curso_corto(self, combo_curso, combo_seccion):
        """Igual que _filtrar_seccion_por_curso, pero con el placeholder de
        Sección acortado: 'Selecciona curso' mientras no se ha elegido un
        curso, y 'Elige sección' ya con las secciones de ese curso cargadas.
        Usado SOLO en Boletín/Promedios, Historial Académico, Desempeño
        Individual, Seguimiento RP, Evaluaciones Finales, Notas por
        Competencia y Compartir Calificaciones."""
        self._filtrar_seccion_por_curso(combo_curso, combo_seccion, incluir_todas=False)
        if combo_curso.currentData() is None:
            _acortar_placeholder_combo(combo_seccion, "Selecciona curso")
        else:
            _acortar_placeholder_combo(combo_seccion, "Elige sección")

    #---- listas base cacheadas (una sola consulta por apertura del módulo) ----
    def _secciones_etiquetadas(self):
        if self._cache_secciones_etiquetadas is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT secciones.id, (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                         FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id ORDER BY etiqueta""")
            self._cache_secciones_etiquetadas= [(f["id"], f["etiqueta"]) for f in c.fetchall()]
            conn.close()
        return self._cache_secciones_etiquetadas

    def _materias_activas(self):
        if self._cache_materias_activas is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT id, nombre FROM materias
                         WHERE estado='Activa' AND especialidad_id IS NULL
                           AND (modelo_evaluacion IS NULL OR modelo_evaluacion != ?)
                         ORDER BY nombre""", (MODELO_EVALUACION_TECNICA,))
            self._cache_materias_activas= [(f["id"], f["nombre"]) for f in c.fetchall()]
            conn.close()
        return self._cache_materias_activas

    def _periodos_lista(self):
        if self._cache_periodos is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
            self._cache_periodos= [(f["id"], f["nombre"]) for f in c.fetchall()]
            conn.close()
        return self._cache_periodos

    def _estudiantes_activos(self):
        """Todos los estudiantes con estado='Activo' (id, nombre, apellidos, seccion_id,
        especialidad_id, carrera_id). Se filtra por sección, área técnica/carrera y por
        permisos en Python, en vez de repetir la consulta SQL para cada combo que
        necesita 'los estudiantes de tal sección'."""
        if self._cache_estudiantes_activos is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT id, nombre, apellidos, seccion_id, especialidad_id, carrera_id FROM estudiantes
                         WHERE estado='Activo' ORDER BY apellidos, nombre""")
            self._cache_estudiantes_activos= [dict(f) for f in c.fetchall()]
            conn.close()
        return self._cache_estudiantes_activos

    def _estudiantes_todos(self):
        if self._cache_estudiantes_todos is None:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT id, nombre, apellidos, seccion_id, especialidad_id, carrera_id
                         FROM estudiantes ORDER BY apellidos, nombre""")
            self._cache_estudiantes_todos= [dict(f) for f in c.fetchall()]
            conn.close()
        return self._cache_estudiantes_todos

    #Área técnica / CARRERA — mismo criterio y comportamiento que en banco_tareas.py (y estudiantes.py): combos de
    #filtro adicionales que solo se muestran si la institución tiene el módulo correspondiente activo, y que en
    #modo "Personalizado" pueden restringir explícitamente a estudiantes sin área técnica / sin carrera (opción "🚫
    #No...").
    def _crear_fila_filtro_tecnico(self, callback):
        """Crea la fila de Área Técnica/Carrera reutilizable (mismo patrón que
        Registro/Boletín/Historial), conectada a `callback` cada vez que el
        usuario cambia alguno de los dos combos. Devuelve
        (fila_layout, lbl_especialidad, combo_especialidad, lbl_carrera, combo_carrera)."""
        fila= QHBoxLayout()
        fila.setSpacing(10)
        lbl_especialidad= QLabel("Área Técnica:")
        combo_especialidad= QComboBox()
        combo_especialidad.setToolTip("Filtrar por área técnica del estudiante (Politécnico)")
        combo_especialidad.currentIndexChanged.connect(callback)
        conectar_tooltip_seleccion(combo_especialidad, "Filtrar por área técnica del estudiante (Politécnico)")
        lbl_carrera= QLabel("Carrera:")
        combo_carrera= QComboBox()
        combo_carrera.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        combo_carrera.currentIndexChanged.connect(callback)
        conectar_tooltip_seleccion(combo_carrera, "Filtrar por carrera del estudiante (Universidad)")
        fila.addWidget(lbl_especialidad)
        fila.addWidget(combo_especialidad)
        fila.addWidget(lbl_carrera)
        fila.addWidget(combo_carrera)
        fila.addStretch()
        return fila, lbl_especialidad, combo_especialidad, lbl_carrera, combo_carrera

    def _crear_combos_filtro_tecnico(self, callback):
        """Igual que _crear_fila_filtro_tecnico pero sin envolver los combos
        en su propia fila visible: se usa cuando Área Técnica/Carrera van a
        vivir dentro de la ventana de '☰ Filtros' junto con Curso/Sección,
        en vez de en una fila aparte de la pantalla principal."""
        lbl_especialidad= QLabel("Área Técnica:")
        combo_especialidad= QComboBox()
        combo_especialidad.setToolTip("Filtrar por área técnica del estudiante (Politécnico)")
        combo_especialidad.currentIndexChanged.connect(callback)
        conectar_tooltip_seleccion(combo_especialidad, "Filtrar por área técnica del estudiante (Politécnico)")
        lbl_carrera= QLabel("Carrera:")
        combo_carrera= QComboBox()
        combo_carrera.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        combo_carrera.currentIndexChanged.connect(callback)
        conectar_tooltip_seleccion(combo_carrera, "Filtrar por carrera del estudiante (Universidad)")
        return lbl_especialidad, combo_especialidad, lbl_carrera, combo_carrera

    def _reemplazar_por_filtros(self, layout_padre, nombre, titulo_dialogo, campos, subtitulo=None):
        """Arma la ventana de '☰ Filtros' con `campos` [(etiqueta, widget), ...]
        y coloca en `layout_padre` la fila compacta de reemplazo (resumen +
        botón). Guarda el diálogo, el label de resumen y el botón como
        self.dialogo_filtros_<nombre>, self.lbl_resumen_filtros_<nombre> y
        self.btn_filtros_<nombre> para que el resto de la pestaña los use."""
        if subtitulo is None:
            subtitulo= ("Curso y Sección acotan qué estudiante puedes elegir abajo. "
                         "Área Técnica y Carrera son opcionales.")
        dialogo= self._crear_dialogo_filtros(titulo_dialogo, subtitulo, campos)
        setattr(self, f"dialogo_filtros_{nombre}", dialogo)
        fila= QHBoxLayout()
        fila.setSpacing(10)
        lbl_resumen= QLabel("")
        lbl_resumen.setWordWrap(True)
        fila.addWidget(lbl_resumen, 1)
        setattr(self, f"lbl_resumen_filtros_{nombre}", lbl_resumen)
        btn= self._crear_boton_filtros("Filtrar por curso, sección, área técnica/carrera")
        btn.clicked.connect(lambda: self._abrir_dialogo_filtros(dialogo))
        setattr(self, f"btn_filtros_{nombre}", btn)
        fila.addWidget(btn)
        layout_padre.addLayout(fila)
        return dialogo, lbl_resumen

    def _actualizar_resumen_filtros_generico(self, nombre, partes):
        lbl= getattr(self, f"lbl_resumen_filtros_{nombre}", None)
        if lbl is None:
            return
        lbl.setText(self._resumen_filtros_texto(partes))

    def _conectar_resumen_filtros(self, nombre, partes):
        """partes: [(etiqueta, combo), ...]. Conecta cada combo para refrescar
        el resumen de '☰ Filtros' de `nombre` cuando cambie, y hace un
        primer refresco inmediato."""
        actualizar= lambda: self._actualizar_resumen_filtros_generico(nombre, partes)
        for _etiqueta, combo in partes:
            combo.currentIndexChanged.connect(actualizar)
        actualizar()

    def _poblar_filtro_tecnico(self, lbl_especialidad, combo_especialidad, lbl_carrera, combo_carrera):
        """Puebla/oculta un par de combos Área Técnica/Carrera creado con
        _crear_fila_filtro_tecnico, igual que en Banco de Tareas: solo se
        muestran si la institución tiene ese módulo activo."""
        es_poli= self._es_politecnico()
        lbl_especialidad.setVisible(es_poli)
        combo_especialidad.setVisible(es_poli)
        if es_poli:
            actual= combo_especialidad.currentData()
            combo_especialidad.blockSignals(True)
            combo_especialidad.clear()
            combo_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                combo_especialidad.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(combo_especialidad, "No Área Técnica")
            idx= combo_especialidad.findData(actual)
            combo_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            combo_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        lbl_carrera.setVisible(es_uni)
        combo_carrera.setVisible(es_uni)
        if es_uni:
            actual= combo_carrera.currentData()
            combo_carrera.blockSignals(True)
            combo_carrera.clear()
            combo_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                combo_carrera.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(combo_carrera, "No Carrera")
            idx= combo_carrera.findData(actual)
            combo_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            combo_carrera.blockSignals(False)

    def _filtrar_por_tecnico(self, filas, combo_especialidad, combo_carrera, campo_especialidad="especialidad_id",
                              campo_carrera= "carrera_id"):
        """Filtra en Python una lista de dicts de estudiantes según los combos
        de Área Técnica/Carrera dados (mismo criterio que _cargar_estudiantes_combo)."""
        especialidad_id= combo_especialidad.currentData() if self._es_politecnico() else None
        carrera_id= combo_carrera.currentData() if self._es_universidad() else None
        if especialidad_id is None and carrera_id is None:
            return filas
        resultado= []
        for f in filas:
            if especialidad_id == 0 and f.get(campo_especialidad) is not None:
                continue
            if especialidad_id not in (None, 0) and f.get(campo_especialidad) != especialidad_id:
                continue
            if carrera_id == 0 and f.get(campo_carrera) is not None:
                continue
            if carrera_id not in (None, 0) and f.get(campo_carrera) != carrera_id:
                continue
            resultado.append(f)
        return resultado

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

    def _es_personalizado(self):
        """True si tipo_institucion es exactamente 'Personalizado'. Solo en este
        modo una misma institución puede tener a la vez estudiantes con área
        técnica, estudiantes con carrera, y estudiantes sin ninguna de las dos
        cosas -de ahí que las opciones "No Área Técnica"/"No Carrera" (ver
        _agregar_opcion_ninguna) solo tengan sentido aquí: en Politécnico o
        Universidad "puros" todo estudiante activo pertenece siempre a una
        especialidad/carrera, así que esa opción no aplicaría a nadie."""
        try:
            tipo, _personalizados = self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado"

    def _agregar_opcion_ninguna(self, combo, texto):
        """Añade al final del combo la opción "ninguna" (dato=0, distinto de
        None= 'Todas/Todos'). Solo se llama en modo Personalizado -ver
        _es_personalizado-, porque es el único caso en que puede haber
        estudiantes activos sin ese dato."""
        if self._es_personalizado():
            combo.addItem(texto, 0)

    def _ambos_modulos_tecnicos_activos(self):
        """True solo cuando la institución es "Personalizado" y tiene
        Politécnico Y Universidad activos a la vez -el único caso en el que
        Área Técnica y Carrera dejan de ser obligatorias. Si la institución
        es puramente Politécnico o puramente Universidad, o si "Personalizado"
        solo tiene UNO de los dos módulos activo, esto es False y el campo
        correspondiente sigue siendo obligatorio. Mismo criterio que en
        estudiantes.py / banco_tareas.py."""
        try:
            tipo, personalizados = self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado" and "Politécnico" in personalizados and "Universidad" in personalizados

    def _permitidas_secciones(self):
        if self._cache_permitidas_secciones is _SIN_CARGAR:
            p= obtener_secciones_permitidas(self.main_window)
            self._cache_permitidas_secciones= set(p) if p is not None else None
        return self._cache_permitidas_secciones

    def _permitidas_materias(self):
        if self._cache_permitidas_materias is _SIN_CARGAR:
            p= obtener_materias_permitidas(self.main_window)
            self._cache_permitidas_materias= set(p) if p is not None else None
        return self._cache_permitidas_materias

    #---- carga perezosa: solo se pueblan combos/tablas de la pestaña que se ve ----
    def _on_tab_changed(self, idx):
        if idx in self._tabs_cargados:
            _efecto_transicion(self.tabs.currentWidget())
            return
        self._tabs_cargados.add(idx)
        #No construimos el contenido real aquí mismo: en este punto la pestaña ya es la visible en pantalla (Qt la
        #muestra antes de emitir esta señal) con el spinner de _agregar_tab_perezosa girando. Le damos 120ms -varios
        #frames de animación real, no un solo frame que se percibiría como un parpadeo- antes de construir
        #combos/tablas/consultas a la BD.
        QTimer.singleShot(120, lambda: self._cargar_tab_diferido(idx))

    def _agregar_tab_perezosa(self, constructor, titulo):
        """Inserta una pestaña con un spinner "Cargando…" de inmediato (NUNCA
        vacía del todo) y recuerda cómo construir su contenido real;
        _construir_tab_si_hace_falta() lo hace la primera vez que el usuario
        la visita (ver _cargar_tab_diferido)."""
        placeholder= QWidget()
        layout_carga= QVBoxLayout(placeholder)
        c= self._paleta()
        spinner= _IndicadorCargaGiratorio("Cargando…", color=c["accent"], color_texto=c["txt_sec"])
        placeholder.spinner= spinner  #referencia para poder detenerlo antes de descartar
        layout_carga.addStretch()
        layout_carga.addWidget(spinner)
        layout_carga.addStretch()
        idx= self.tabs.addTab(placeholder, titulo)
        self._constructores_tabs_pendientes[idx]= (constructor, placeholder)
        return idx

    def _construir_tab_si_hace_falta(self, idx):
        entrada= self._constructores_tabs_pendientes.pop(idx, None)
        if entrada is None:
            return
        constructor, placeholder = entrada
        spinner= getattr(placeholder, "spinner", None)
        if spinner is not None:
            spinner.detener()
        #Quitamos el layout temporal del "Cargando…" para poder construir el contenido real desde cero sobre el mismo
        #placeholder (un widget no puede recibir un segundo QVBoxLayout mientras ya tenga uno puesto). El truco
        #estándar de Qt para "soltar" un layout de un widget es pasárselo a otro widget desechable.
        layout_viejo= placeholder.layout()
        if layout_viejo is not None:
            QWidget().setLayout(layout_viejo)
        constructor(placeholder)  #construye el contenido DENTRO del placeholder ya insertado
        #El contenido real reemplaza al spinner con un fundido suave en vez de un corte seco -mismo efecto que ya se
        #usaba al cambiar entre pestañas ya cargadas- así la transición se siente intencional.
        _efecto_transicion(placeholder)
        #Esta pestaña no existía cuando _build_ui() conectó el rebote a los botones iniciales, así que lo hacemos ahora
        #para los suyos.
        for boton in placeholder.findChildren(QPushButton):
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.pressed.connect(lambda b=boton: _animar_click(b))

    def _cargar_tab(self, idx):
        """Fuerza la carga inmediata de una pestaña (sin esperar a que el
        usuario haga clic en ella) — se usa, por ejemplo, al abrir el módulo
        por primera vez para la pestaña que queda visible de entrada."""
        if idx in self._tabs_cargados:
            return
        self._tabs_cargados.add(idx)
        self._cargar_tab_diferido(idx)

    def _cargar_tab_diferido(self, idx):
        self._construir_tab_si_hace_falta(idx)
        if idx == 0:
            self._cargar_secciones_combo()
            self._cargar_materias_combo()
            self._cargar_periodos_combo()
            self._cargar_especialidad_carrera_registro()
            self._cargar_estudiantes_combo()  #ya dispara _cargar_registro_estudiante()
        elif idx == 1:
            self._cargar_periodos_combo()  #llena combo_periodo_boletin / combo_periodo_masivo
            self._poblar_combo_curso_corto(self.combo_curso_boletin)
            self._filtrar_seccion_por_curso_corto(self.combo_curso_boletin, self.combo_seccion_boletin)
            self._cargar_especialidad_carrera_boletin()
            self._cargar_estudiantes_boletin()
            self._cargar_secciones_masivo()
        elif idx == 2:
            self._poblar_combo_curso_corto(self.combo_curso_historial)
            self._filtrar_seccion_por_curso_corto(self.combo_curso_historial, self.combo_seccion_historial)
            self._cargar_especialidad_carrera_historial()
            self._cargar_estudiantes_historial()
        elif idx == getattr(self, "idx_tab_desempeno", -1):
            self._poblar_filtro_tecnico(self.lbl_filtro_especialidad_desempeno, self.combo_filtro_especialidad_desempeno,
                                         self.lbl_filtro_carrera_desempeno, self.combo_filtro_carrera_desempeno)
            self._cargar_secciones_desempeno()
            self._cargar_estudiantes_desempeno()
            self._cargar_periodos_desempeno()
        elif idx == getattr(self, "idx_tab_seguimiento", -1):
            self._poblar_filtro_tecnico(self.lbl_filtro_especialidad_seguimiento, self.combo_filtro_especialidad_seguimiento,
                                         self.lbl_filtro_carrera_seguimiento, self.combo_filtro_carrera_seguimiento)
            self._cargar_secciones_seguimiento()
            self._cargar_periodos_seguimiento()
        elif idx == getattr(self, "idx_tab_evaluaciones_finales", -1):
            self._poblar_filtro_tecnico(self.lbl_filtro_especialidad_finales, self.combo_filtro_especialidad_finales,
                                         self.lbl_filtro_carrera_finales, self.combo_filtro_carrera_finales)
            self._cargar_secciones_finales()
            self._cargar_estudiantes_finales()
        elif idx == getattr(self, "idx_tab_curriculo", -1):
            self._cargar_materias_curriculo()
        elif idx == getattr(self, "idx_tab_competencias_especificas", -1):
            self._poblar_filtro_tecnico(self.lbl_filtro_especialidad_competencias, self.combo_filtro_especialidad_competencias,
                                         self.lbl_filtro_carrera_competencias, self.combo_filtro_carrera_competencias)
            self._cargar_secciones_competencias()
            self._cargar_estudiantes_competencias()
            self._cargar_periodos_competencias()
        elif idx == getattr(self, "idx_tab_compartir", -1):
            self._poblar_filtro_tecnico(self.lbl_filtro_especialidad_compartir, self.combo_filtro_especialidad_compartir,
                                         self.lbl_filtro_carrera_compartir, self.combo_filtro_carrera_compartir)
            self._cargar_secciones_compartir()
            self._cargar_periodos_compartir()
            self._cargar_paquetes_importados()

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
        layout.setSpacing(18)

        #--- Cabecera tipo "hero": icono + título + descripción --- Mismo diseño (objectName, gradiente y estructura)
        #que usan Reportes, Estudiantes, Profesores, Materias, etc. — antes Calificaciones era el único módulo sin esta
        #cabecera.
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("📊", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Calificaciones")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Calificaciones")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Registro, seguimiento y publicación de las calificaciones por estudiante")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo, 1)

        layout.addWidget(self.frame_cabecera)

        self.tabs= TabWidgetNavegable()
        layout.addWidget(self.tabs)
        #Solo la pestaña visible al abrir el módulo (Registro) se construye de inmediato; las demás quedan como
        #placeholders vacíos y su contenido
        #real (tablas, tarjetas de alerta, combos) se construye la primera vez
        #que el usuario hace clic en ellas — así abrir 'Calificaciones' desde la barra lateral no paga el costo de
        #armar 6 pestañas completas.
        self._constructores_tabs_pendientes= {}
        self.tabs.addTab(self._tab_registro(), "Registrar Calificación")
        idx_boletin= self._agregar_tab_perezosa(self._tab_boletin, "Boletín / Promedios")
        self.tabs.setTabIcon(idx_boletin, icono_emoji(EMOJI_BOLETIN_PROMEDIOS))
        self._agregar_tab_perezosa(self._tab_historial, "Historial Académico")
        self.idx_tab_desempeno= self._agregar_tab_perezosa(
            self._tab_desempeno_individual, "Desempeño Individual")
        self.tabs.setTabIcon(self.idx_tab_desempeno, icono_emoji(EMOJI_DESEMPENO_INDIVIDUAL))
        self.idx_tab_seguimiento= self._agregar_tab_perezosa(
            self._tab_seguimiento_rd, "Seguimiento (RP / Incompletos)")
        self.tabs.setTabIcon(self.idx_tab_seguimiento, icono_emoji(EMOJI_SEGUIMIENTO_RP))
        self.idx_tab_evaluaciones_finales= self._agregar_tab_perezosa(
            self._tab_evaluaciones_finales, "Evaluaciones Finales")
        self.tabs.setTabIcon(self.idx_tab_evaluaciones_finales, icono_emoji(EMOJI_EVALUACIONES_FINALES))
        self.idx_tab_curriculo= self._agregar_tab_perezosa(
            self._tab_curriculo_rd, "Currículo (CE)")
        self.tabs.setTabIcon(self.idx_tab_curriculo, icono_emoji(EMOJI_CURRICULO_CE))
        self.idx_tab_competencias_especificas= self._agregar_tab_perezosa(
            self._tab_competencias_especificas, "Notas por Competencia")
        self.tabs.setTabIcon(self.idx_tab_competencias_especificas, icono_emoji(EMOJI_NOTAS_COMPETENCIA))
        self.idx_tab_compartir= self._agregar_tab_perezosa(
            self._tab_compartir_calificaciones, "Compartir Calificaciones")
        self.tabs.setTabIcon(self.idx_tab_compartir, icono_emoji(EMOJI_COMPARTIR_CALIFICACIONES))

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        #Un único punto para dar 'vida' a TODOS los botones del módulo (rebote al presionar) sin tener que tocar cada
        #conexión .clicked existente.
        for boton in self.findChildren(QPushButton):
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.pressed.connect(lambda b=boton: _animar_click(b))
    #---------------- REGISTRO ---------------- Ventana de "☰ FILTROS" — reutilizable en todas las pestañas del
    #módulo. Mismo patrón visual/funcional que ya usan Calendario, Banco de Tareas y Calificaciones Técnicas: una
    #ventanita no modal donde viven los combos que acotan qué se ve en la tabla/formulario de abajo (curso,
    #sección, área técnica, carrera, periodo, etc.), para no apilarlos permanentemente en la pantalla principal. Se
    #arma una vez por pestaña, en su _tab_*.
    def _crear_boton_filtros(self, tooltip="Filtrar resultados"):
        btn= QPushButton("Filtros")
        #Icono dedicado de "Filtros" (el mismo que usan Estudiantes/ Materias/etc.), NO una lupa: la lupa es "buscar"
        #(texto libre), mientras que esto abre la ventanita de Curso/Sección/Área Técnica. `icono_boton_filtro` además
        #auto-registra el botón para refrescar su color si cambia el tema claro/oscuro.
        icono_boton_filtro(btn)
        btn.setObjectName("BtnAccionNeutro")
        btn.setToolTip(tooltip)
        return btn

    def _abrir_dialogo_filtros(self, dialogo):
        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and dialogo.parent() is not _fc:
            dialogo.setParent(_fc)
        dialogo.show()
        dialogo.raise_()
        dialogo.activateWindow()

    def _estilo_dialogo_filtros_qss(self, c=None):
        """QSS de la ventana '☰ Filtros', en un solo lugar para que TODAS las
        pestañas (Registro, Boletín, Historial, Desempeño, Seguimiento,
        Evaluaciones Finales, Notas por Competencia, Compartir) se vean
        exactamente igual sin importar cuándo se construyan -algunas
        pestañas se cargan de forma perezosa (ver _agregar_tab_perezosa),
        posiblemente mucho después de actualizar_tema()-. Antes este bloque
        vivía SOLO dentro de actualizar_tema() y se aplicaba con un loop por
        nombre; una pestaña construida después de esa llamada se quedaba sin
        estilo (Qt por defecto, gris) hasta el próximo cambio de tema."""
        if c is None:
            c= self._paleta()
        return f"""
            QDialog#DialogoFiltrosCalif {{
                background-color: {c['bg_panel']};
            }}
            /* Repite aquí el mismo QToolTip que usa la ventana principal:
               este diálogo es una ventana de nivel superior aparte, y su
               propio setStyleSheet() reemplaza -para todo lo que esté
               dentro- cualquier regla heredada, incluido el QToolTip global.
               Sin esto, los tooltips de los combos aquí adentro caían al
               estilo nativo de Qt (gris claro/texto negro), inconsistente
               con el resto de AcaDeXI. */
            QToolTip {{
                background-color: {c['bg_panel']};
                color: {c['txt_prim']};
                border: 1px solid {c['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QLabel#IconoEncabezadoFiltrosCalif {{
                background-color: {c['accent']};
                color: white;
                border-radius: 15px;
                min-width: 30px; max-width: 30px;
                min-height: 30px; max-height: 30px;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }}
            QLabel#TituloEncabezadoFiltrosCalif {{
                font-size: 16px;
                font-weight: 800;
                color: {c['txt_prim']};
                background: transparent;
            }}
            QLabel#SubtituloFiltrosCalif {{
                font-size: 11.5px;
                color: {c['txt_sec']};
                background: transparent;
            }}
            QFrame#SeparadorFiltrosCalif {{
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
        """

    def _crear_dialogo_filtros(self, titulo_ventana, subtitulo, campos):
        """campos: lista de (etiqueta, widget). `etiqueta` puede ser un str
        (se envuelve en QLabel) o un QLabel ya existente (p. ej. uno con
        emoji que se muestra/oculta según Politécnico/Universidad), o None
        si el widget debe ocupar las dos columnas del grid."""
        dialogo= QDialog(self)
        dialogo.setObjectName("DialogoFiltrosCalif")
        dialogo.setWindowTitle(titulo_ventana)
        #Se aplica el estilo compartido ya en la construcción -no se espera al próximo actualizar_tema()- para que
        #pestañas cargadas de forma
        #perezosa (todas menos "Registro", la única que se carga de
        #entrada) luzcan igual desde el primer instante en que el usuario abre su ventana de Filtros, en vez de
        #mostrarse sin estilo hasta que alguien cambie el tema claro/oscuro.
        dialogo.setStyleSheet(self._estilo_dialogo_filtros_qss())
        try:
            from src.nucleo.iconos import aplicar_icono_ventana, ICONO_FILTRO
            aplicar_icono_ventana(dialogo, ICONO_FILTRO)
        except Exception:
            pass
        dialogo.setModal(False)
        dialogo.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(dialogo)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        icono_encabezado= QLabel()
        pixmap_boton_filtro(icono_encabezado, 20)
        icono_encabezado.setObjectName("IconoEncabezadoFiltrosCalif")
        fila_encabezado.addWidget(icono_encabezado)
        titulo_encabezado= QLabel("Filtros")
        titulo_encabezado.setObjectName("TituloEncabezadoFiltrosCalif")
        fila_encabezado.addWidget(titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        if subtitulo:
            lbl_subtitulo= QLabel(subtitulo)
            lbl_subtitulo.setObjectName("SubtituloFiltrosCalif")
            lbl_subtitulo.setWordWrap(True)
            lay_dialogo.addWidget(lbl_subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltrosCalif")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, widget in campos:
            if etiqueta is None:
                grid.addWidget(widget, fila, 0, 1, 2)
            else:
                grid.addWidget(QLabel(etiqueta) if isinstance(etiqueta, str) else etiqueta, fila, 0)
                grid.addWidget(widget, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(dialogo.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)
        return dialogo

    def _resumen_filtros_texto(self, partes):
        """Arma la línea de resumen ('Curso: 1ro A · Sección: A · …') a
        partir de [(etiqueta, combo_o_texto), ...], omitiendo lo vacío/'Todas'."""
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

    #Panel colapsable de "añadir" — mismo 'cosito de ocultar' que ya usan Materias y Banco de Tareas
    #(PanelDesplegable de calendario.py): el formulario de captura/edición no le gana protagonismo visual a la
    #tabla de abajo, pero sigue a un clic ("➕ Añadir") para quien lo necesite. Empieza cerrado por defecto.
    def _envolver_en_panel(self, layout_padre, titulo, *widgets):
        from src.modulos.calendario import PanelDesplegable
        panel= PanelDesplegable(titulo)
        for widget in widgets:
            panel.cuerpo_layout().addWidget(widget)
        layout_padre.addWidget(panel)
        return panel

    def _tab_registro(self):
        w= QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(18)
        form= QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        self.combo_curso= QComboBox()
        self.combo_curso.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso(self.combo_curso, self.combo_seccion, incluir_todas=False),
                      self._cargar_estudiantes_combo()))
        self.combo_seccion= QComboBox()
        self.combo_seccion.currentIndexChanged.connect(self._cargar_estudiantes_combo)
        #Filtro adicional por Área Técnica (Politécnico) / Carrera (Universidad), igual que en Banco de Tareas: solo se
        #muestran si la institución tiene el módulo correspondiente activo (ver _cargar_especialidad_carrera_registro).
        self.lbl_filtro_especialidad_registro= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_registro= QComboBox()
        self.combo_filtro_especialidad_registro.setToolTip(
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.combo_filtro_especialidad_registro.currentIndexChanged.connect(self._cargar_estudiantes_combo)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_registro,
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.lbl_filtro_carrera_registro= QLabel("Carrera:")
        self.combo_filtro_carrera_registro= QComboBox()
        self.combo_filtro_carrera_registro.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        self.combo_filtro_carrera_registro.currentIndexChanged.connect(self._cargar_estudiantes_combo)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_registro,
            "Filtrar por carrera del estudiante (Universidad)")
        self.combo_estudiante= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante, "Estudiante al que se le registra la calificación")
        self.combo_materia= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia, "Materia de la calificación")
        self.combo_periodo= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo, "Periodo académico de la calificación")
        self.combo_categoria= QComboBox(); self.combo_categoria.addItems(CATEGORIAS)
        conectar_tooltip_seleccion(self.combo_categoria, "Tipo de actividad evaluada (Examen, Tarea, Práctica, etc.)")
        ajustar_combo_ancho_seguro(self.combo_curso, self.combo_seccion, self.combo_estudiante,
                                    self.combo_materia, self.combo_periodo, self.combo_categoria,
                                    self.combo_filtro_especialidad_registro, self.combo_filtro_carrera_registro)
        self.in_descripcion= QTextEdit(); self.in_descripcion.setPlaceholderText("Descripción (ej. Examen Parcial 1)")
        limitar_campo_texto(self.in_descripcion, 5000)
        self.in_descripcion.setFixedHeight(60)
        self.in_descripcion.setObjectName("InputDescripcionCalificacion")
        self.spin_valor= QDoubleSpinBox(); self.spin_valor.setRange(0, 1000); self.spin_valor.setDecimals(2)
        self.spin_peso= QDoubleSpinBox(); self.spin_peso.setRange(0, 100); self.spin_peso.setSuffix(" %")
        lbl_curso= QLabel("Curso:"); lbl_curso.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_seccion= QLabel("Sección:"); lbl_seccion.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_estudiante= QLabel("Estudiante:"); lbl_estudiante.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_materia= QLabel("Materia:"); lbl_materia.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_periodo= QLabel("Periodo:"); lbl_periodo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_categoria= QLabel("Categoría:"); lbl_categoria.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        #Curso/Sección/Área Técnica/Carrera pasan a la ventana de "☰ Filtros"
        #(mismo patrón que Calendario/Banco de Tareas/Calificaciones Técnicas):
        #solo acotan qué estudiante aparece en el combo de abajo, así que no necesitan ocupar espacio permanente en el
        #formulario principal.
        self.dialogo_filtros_registro= self._crear_dialogo_filtros(
            "Filtros de Registro de Calificación",
            "Curso y Sección acotan qué estudiante puedes elegir abajo. Área Técnica y Carrera son opcionales.",
            [(self.lbl_filtro_especialidad_registro, self.combo_filtro_especialidad_registro),
             (self.lbl_filtro_carrera_registro, self.combo_filtro_carrera_registro),
             (lbl_curso, self.combo_curso),
             (lbl_seccion, self.combo_seccion)])
        fila_filtros_registro= QHBoxLayout()
        self.lbl_resumen_filtros_registro= QLabel("")
        self.lbl_resumen_filtros_registro.setWordWrap(True)
        fila_filtros_registro.addWidget(self.lbl_resumen_filtros_registro, 1)
        self.btn_filtros_registro= self._crear_boton_filtros("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_registro.clicked.connect(lambda: self._abrir_dialogo_filtros(self.dialogo_filtros_registro))
        fila_filtros_registro.addWidget(self.btn_filtros_registro)
        form.addLayout(fila_filtros_registro, 0, 0, 1, 4)
        self.combo_curso.currentIndexChanged.connect(self._actualizar_resumen_filtros_registro)
        self.combo_seccion.currentIndexChanged.connect(self._actualizar_resumen_filtros_registro)
        self.combo_filtro_especialidad_registro.currentIndexChanged.connect(self._actualizar_resumen_filtros_registro)
        self.combo_filtro_carrera_registro.currentIndexChanged.connect(self._actualizar_resumen_filtros_registro)

        form.addWidget(lbl_estudiante, 2, 0); form.addWidget(self.combo_estudiante, 2, 1)
        form.addWidget(lbl_materia, 2, 2); form.addWidget(self.combo_materia, 2, 3)
        form.addWidget(lbl_periodo, 3, 0); form.addWidget(self.combo_periodo, 3, 1)
        form.addWidget(lbl_categoria, 3, 2); form.addWidget(self.combo_categoria, 3, 3)

        #Las columnas de las etiquetas (0 y 2) NO deben crecer: solo ocupan el ancho de su texto. Las columnas de los
        #campos (1 y 3) absorben todo el espacio extra, así la etiqueta queda pegada a su control en vez de dejar un
        #hueco cuando la ventana es ancha.
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 0)
        form.setColumnStretch(3, 1)

        #El campo Descripción se separa visualmente del resto de los combos (arriba y abajo) para que no quede "pegado"
        #a los datos estructurados; es texto libre y merece su propio espacio dentro del formulario.
        form.setRowMinimumHeight(4, 14)
        lbl_descripcion= QLabel("Descripción:")
        form.addWidget(lbl_descripcion, 5, 0, 1, 4)
        form.addWidget(self.in_descripcion, 6, 0, 1, 4)
        form.setRowMinimumHeight(7, 14)

        lbl_valor= QLabel("Valor:"); lbl_valor.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_peso= QLabel("Peso:"); lbl_peso.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(lbl_valor, 8, 0); form.addWidget(self.spin_valor, 8, 1)
        form.addWidget(lbl_peso, 8, 2); form.addWidget(self.spin_peso, 8, 3)

        #Estado de publicación (Borrador/Pendiente/Publicada): una nota puede guardarse como borrador mientras el
        #docente aún la está trabajando, sin que aparezca todavía en el boletín ni sea visible para el
        #estudiante/tutor.
        self.lbl_estado_publicacion= QLabel("Estado:")
        self.lbl_estado_publicacion.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.combo_estado_publicacion= QComboBox()
        self.combo_estado_publicacion.addItems(ESTADOS_PUBLICACION)
        self.combo_estado_publicacion.setCurrentText("Publicada")
        conectar_tooltip_seleccion(self.combo_estado_publicacion,
            "Estado de publicación de la calificación: Borrador (no visible aún), "
            "Pendiente o Publicada (visible en el boletín y para el estudiante/tutor)")
        form.addWidget(self.lbl_estado_publicacion, 9, 2)
        form.addWidget(self.combo_estado_publicacion, 9, 3)

        form.setRowMinimumHeight(10, 12)

        #Vínculo con el currículo: a qué Competencias Específicas (CE) de la materia+grado del estudiante corresponde
        #esta evidencia. Solo aplica en Modo República Dominicana (se oculta/ignora en el sistema genérico).
        self._ce_vinculadas_registro= []
        self.btn_vincular_competencias= QPushButton("Vincular a Competencias Específicas")
        self.btn_vincular_competencias.setIcon(icono_emoji(EMOJI_VINCULAR))
        self.btn_vincular_competencias.setIconSize(_QSize_emoji(16, 16))
        self.btn_vincular_competencias.setObjectName("BtnAccionNeutro")
        self.btn_vincular_competencias.setToolTip(
            "Marca a cuáles Competencias Específicas del currículo (definidas en la pestaña "
            "Currículo) evalúa esta evidencia. Una evidencia puede validar varias CE a la vez.")
        self.btn_vincular_competencias.clicked.connect(self._elegir_competencias_registro)
        form.addWidget(self.btn_vincular_competencias, 11, 0, 1, 2)

        self.btn_guardar= QPushButton("Registrar Calificación")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar_calificacion)
        form.addWidget(self.btn_guardar, 12, 0, 1, 1)

        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_formulario)
        form.addWidget(btn_limpiar, 12, 1, 1, 1)

        btn_historial_cambios= QPushButton("Historial de Cambios")
        btn_historial_cambios.setIcon(icono_emoji("🕒"))
        btn_historial_cambios.setIconSize(_QSize_emoji(16, 16))
        btn_historial_cambios.setObjectName("BtnAccionNeutro")
        btn_historial_cambios.setToolTip("Ver quién cambió esta calificación, cuándo y qué valor tenía antes.")
        btn_historial_cambios.clicked.connect(self._ver_historial_calificacion)
        form.addWidget(btn_historial_cambios, 12, 2, 1, 2)

        #Intercambio entre ediciones (ver intercambio_datos.py). Usa la Materia/Periodo ya elegidos arriba en este
        #mismo formulario.
        btn_exportar_intercambio= QPushButton("Exportar a otra edición")
        btn_exportar_intercambio.setIcon(icono_emoji("📤"))
        btn_exportar_intercambio.setIconSize(_QSize_emoji(16, 16))
        btn_exportar_intercambio.setObjectName("BtnAccionNeutro")
        btn_exportar_intercambio.setToolTip(
            "Exporta las calificaciones de la Materia/Periodo elegidos arriba para "
            "importarlas en otra instalación de AcaDeXI.")
        btn_exportar_intercambio.clicked.connect(self._abrir_exportar_intercambio_calificaciones)
        form.addWidget(btn_exportar_intercambio, 13, 0, 1, 2)

        btn_importar_intercambio= QPushButton("Importar de otra edición")
        btn_importar_intercambio.setIcon(icono_emoji("📥"))
        btn_importar_intercambio.setIconSize(_QSize_emoji(16, 16))
        btn_importar_intercambio.setObjectName("BtnAccionNeutro")
        btn_importar_intercambio.setToolTip(
            "Importa un archivo .acdxpkg de calificaciones hacia la Materia/Periodo elegidos arriba.")
        btn_importar_intercambio.clicked.connect(self._abrir_importar_intercambio_calificaciones)
        form.addWidget(btn_importar_intercambio, 13, 2, 1, 2)

        frame_form_registro= QWidget()
        lay_frame_form_registro= QVBoxLayout(frame_form_registro)
        lay_frame_form_registro.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_registro.addLayout(form)
        self._envolver_en_panel(l, "Registrar / Editar Calificación", frame_form_registro)

        self.combo_materia.currentIndexChanged.connect(self._actualizar_boton_competencias_registro)
        self.combo_estudiante.currentIndexChanged.connect(self._actualizar_boton_competencias_registro)
        #Búsqueda flexible: no distingue mayúsculas/minúsculas ni acentos (mismo diseño visual que la searchbar de
        #configuracion.py)
        l.addSpacing(10)
        titulo_tabla_registro= QLabel("Calificaciones registradas")
        titulo_tabla_registro.setObjectName("DescModulo")
        l.addWidget(titulo_tabla_registro)
        self.in_buscar_registro= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_registro.setPlaceholderText(
            "Buscar por materia, periodo, categoría o descripción (ignora tildes y mayúsculas)...")
        self.in_buscar_registro.texto_buscado.connect(self._aplicar_busqueda_registro)
        l.addWidget(self.in_buscar_registro)
        l.addSpacing(6)


        #Tabla estilo Omega POS (registro de calificaciones)
        self.tabla_registro= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_registro)
        self.estado_vacio_registro= EstadoVacioFiltro(self.tabla_registro)
        self.tabla_registro.setHorizontalHeaderLabels(
            ["Estado", "Materia", "Periodo", "Categoría", "Descripción", "Valor"])
        header= self.tabla_registro.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #"Descripción" ya es Stretch; con StretchLastSection activo, "Valor" (última columna) competiría por el mismo
        #espacio sobrante.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  #"Descripción"
        self.tabla_registro.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_registro.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_registro.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_registro.setAlternatingRowColors(True)
        self.tabla_registro.setWordWrap(True)
        self.tabla_registro.setMinimumHeight(220)
        self.tabla_registro.verticalHeader().setVisible(False)
        l.addWidget(self.tabla_registro, 1)

        self.paginacion_registro= ControlPaginacion(tamano_inicial=25)
        self.paginacion_registro.cambio.connect(self._cargar_registro_estudiante)
        l.addWidget(self.paginacion_registro)
        l.addSpacing(8)

        agregar_boton_pantalla_completa(
            None,
            [self.in_buscar_registro, self.tabla_registro, self.paginacion_registro],
            titulo= "Calificaciones registradas", parent=self)


        #Botones de acción debajo de la tabla
        fila_acciones= QHBoxLayout()
        fila_acciones.setSpacing(10)
        btn_cargar= QPushButton("Cargar Seleccionada para Editar")
        btn_cargar.setIcon(icono_emoji("✏"))
        btn_cargar.setIconSize(_QSize_emoji(16, 16))
        btn_cargar.setObjectName("BtnAccionEditar")
        btn_cargar.clicked.connect(self._cargar_calificacion_seleccionada)
        fila_acciones.addWidget(btn_cargar)
        
        btn_eliminar= QPushButton("Eliminar Calificación")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_calificacion)
        fila_acciones.addWidget(btn_eliminar)

        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla_registro, self, 
                                             titulo= "Detalle de la Calificación",
                                             proveedor_extra_botones= self._boton_ver_descripcion_calificacion)
        self.tabla_registro.doubleClicked.connect(lambda *_: btn_detalle.click())
        
        fila_acciones.addStretch()
        l.addLayout(fila_acciones)
        
        self.combo_estudiante.currentIndexChanged.connect(self._cargar_registro_estudiante)
        l.addStretch(1)
        return w

    def _boton_ver_descripcion_calificacion(self, fila):
        """Botón extra del diálogo 'Detalle de la Calificación', igual que en
        Banco de Tareas: la descripción se consulta aparte y se muestra
        completa en su propia ventana, sin depender de cómo se vea truncada
        en la celda de la tabla."""
        id_item= self.tabla_registro.item(fila, 0)
        if id_item is None:
            return []
        id_cal= id_item.data(Qt.ItemDataRole.UserRole)

        def _abrir_descripcion():
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT descripcion FROM calificaciones WHERE id=?", (id_cal,))
            fila_bd= c.fetchone()
            conn.close()
            texto= fila_bd["descripcion"] if fila_bd else ""
            mostrar_texto_largo(self, "Descripción de la Calificación", texto)

        return [("Ver Descripción completa", _abrir_descripcion)]

    def _cargar_secciones_combo(self):
        self._poblar_combo_curso(self.combo_curso, incluir_todos=False)
        self._filtrar_seccion_por_curso(self.combo_curso, self.combo_seccion, incluir_todas=False)
    def _cargar_estudiantes_combo(self):
        self.combo_estudiante.clear()
        seccion_id= self.combo_seccion.currentData()
        if seccion_id is None:
            #Sin sección elegida todavía (p.ej. curso aún no seleccionado), no se
            #listan estudiantes: forzar a elegir Curso -> Sección primero evita
            #registrar por error una calificación a un estudiante equivocado.
            return
        permitidas= self._permitidas_secciones()
        especialidad_id= self.combo_filtro_especialidad_registro.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_filtro_carrera_registro.currentData() if self._es_universidad() else None
        for f in self._estudiantes_activos():
            if f["seccion_id"] != seccion_id:
                continue
            if permitidas is not None and f["seccion_id"] not in permitidas:
                continue
            if especialidad_id == 0 and f["especialidad_id"] is not None:
                continue
            elif especialidad_id not in (None, 0) and f["especialidad_id"] != especialidad_id:
                continue
            if carrera_id == 0 and f["carrera_id"] is not None:
                continue
            elif carrera_id not in (None, 0) and f["carrera_id"] != carrera_id:
                continue
            self.combo_estudiante.addItem(f"{f['nombre']} {f['apellidos'] or ''}", f["id"])
        self._cargar_registro_estudiante()
        self._actualizar_resumen_filtros_registro()

    def _actualizar_resumen_filtros_registro(self):
        """Como Curso/Sección/Área Técnica/Carrera ahora viven en la ventana
        de Filtros (oculta por defecto), esta línea deja a la vista, sin
        tener que abrir el diálogo, qué se está acotando."""
        if not hasattr(self, "lbl_resumen_filtros_registro"):
            return
        self.lbl_resumen_filtros_registro.setText(self._resumen_filtros_texto([
            ("Curso", self.combo_curso), ("Sección", self.combo_seccion),
            ("Área Técnica", self.combo_filtro_especialidad_registro),
            ("Carrera", self.combo_filtro_carrera_registro),
        ]))

    def _cargar_especialidad_carrera_registro(self):
        """Igual que en Banco de Tareas: los combos de Área Técnica y Carrera de
        'Registrar Calificación' solo se muestran/pueblan si la institución tiene
        ese módulo activo."""
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_registro.setVisible(es_poli)
        self.combo_filtro_especialidad_registro.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_registro.currentData()
            self.combo_filtro_especialidad_registro.blockSignals(True)
            self.combo_filtro_especialidad_registro.clear()
            self.combo_filtro_especialidad_registro.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_registro.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_especialidad_registro, "No Área Técnica")
            idx= self.combo_filtro_especialidad_registro.findData(actual)
            self.combo_filtro_especialidad_registro.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_registro.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_registro.setVisible(es_uni)
        self.combo_filtro_carrera_registro.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_registro.currentData()
            self.combo_filtro_carrera_registro.blockSignals(True)
            self.combo_filtro_carrera_registro.clear()
            self.combo_filtro_carrera_registro.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_registro.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_carrera_registro, "No Carrera")
            idx= self.combo_filtro_carrera_registro.findData(actual)
            self.combo_filtro_carrera_registro.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_registro.blockSignals(False)
    def _cargar_materias_combo(self):
        self.combo_materia.clear()
        permitidas_materias= self._permitidas_materias()
        for id_materia, nombre in self._materias_activas():
            if permitidas_materias is not None and id_materia not in permitidas_materias:
                continue
            self.combo_materia.addItem(nombre, id_materia)
    def _cargar_periodos_combo(self):
        for combo in (self.combo_periodo, getattr(self, "combo_periodo_boletin", None),
                      getattr(self, "combo_periodo_masivo", None)):
            if combo is None:
                continue
            combo.clear()
        for id_periodo, nombre in self._periodos_lista():
            self.combo_periodo.addItem(nombre, id_periodo)
            if hasattr(self, "combo_periodo_boletin"):
                self.combo_periodo_boletin.addItem(nombre, id_periodo)
            if hasattr(self, "combo_periodo_masivo"):
                self.combo_periodo_masivo.addItem(nombre, id_periodo)
    def _guardar_calificacion(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar calificaciones.", self)
            return
        estudiante_id= self.combo_estudiante.currentData()
        materia_id= self.combo_materia.currentData()
        periodo_id= self.combo_periodo.currentData()
        if estudiante_id is None or materia_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona estudiante, materia y periodo.", self)
            return
        #Área Técnica/Carrera son OBLIGATORIOS al registrar si la institución es puramente Politécnico o puramente
        #Universidad (o "Personalizado" con solo uno de los dos módulos activo). Si "Personalizado" tiene AMBOS módulos
        #activos a la vez, ninguno de los dos es obligatorio -mismo criterio que en el guardado de Estudiantes/Banco de
        #Tareas-.
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        if self._es_politecnico() and not ambos_activos and self.combo_filtro_especialidad_registro.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica antes de "
                           "registrar la calificación.", self)
            return
        if self._es_universidad() and not ambos_activos and self.combo_filtro_carrera_registro.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera antes de "
                           "registrar la calificación.", self)
            return
        if self._periodo_esta_bloqueado(periodo_id) and not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Periodo cerrado",
                             "Este periodo fue cerrado por Dirección/Coordinación y ya no admite cambios. "
                             "Solo un rol gerencial puede reabrirlo desde la pestaña Boletín.", self)
            return
        if self.id_edicion is not None:
            conn_chk= obtener_conexion()
            fila_chk= conn_chk.cursor().execute(
                "SELECT solo_lectura, importado_de FROM calificaciones WHERE id=?", (self.id_edicion,)).fetchone()
            conn_chk.close()
            if fila_chk and fila_chk["solo_lectura"] and not tiene_acceso_gerencial(self.main_window):
                mostrar_mensaje("advertencia", "Nota importada (solo lectura)",
                                 f"Esta calificación fue importada de {fila_chk['importado_de'] or 'otro docente'} "
                                 "y no se puede editar desde aquí.", self)
                return
        estado_pub= (self.combo_estado_publicacion.currentText()
                      if hasattr(self, "combo_estado_publicacion") else "Publicada")
        conn= obtener_conexion()
        c= conn.cursor()
        valores_nuevos= (estudiante_id, materia_id, periodo_id, self.combo_categoria.currentText(),
                           self.in_descripcion.toPlainText().strip(), self.spin_valor.value(), self.spin_peso.value(),
                           estado_pub)
        if self.id_edicion is None:
            c.execute("""INSERT INTO calificaciones (estudiante_id, materia_id, periodo_id, categoria,
                         descripcion, valor, peso, estado_publicacion) VALUES (?,?,?,?,?,?,?,?)""",
                      valores_nuevos)
            calificacion_id= c.lastrowid
            accion= "Registró calificación"
        else:
            calificacion_id= self.id_edicion
            #Historial de cambios: se compara contra lo que había antes de sobrescribir.
            c.execute("SELECT * FROM calificaciones WHERE id=?", (calificacion_id,))
            anterior= c.fetchone()
            c.execute("""UPDATE calificaciones SET estudiante_id=?, materia_id=?, periodo_id=?,
                         categoria= ?, descripcion=?, valor=?, peso=?, estado_publicacion=? WHERE id=?""",
                      valores_nuevos + (calificacion_id,))
            if anterior is not None:
                usuario= self.main_window.usuario_actual
                for campo, idx_campo in (("valor", "valor"), ("peso", "peso"), ("categoria", "categoria"),
                                          ("estado_publicacion", "estado_publicacion")):
                    _registrar_historial_cambio("calificaciones", calificacion_id, estudiante_id, campo,
                                                 anterior[idx_campo], valores_nuevos[
                                                     ["estudiante_id", "materia_id", "periodo_id", "categoria",
                                                      "descripcion", "valor", "peso", "estado_publicacion"].index(idx_campo)],
                                                 usuario, cursor=c)
            accion= "Editó calificación"

        #Sincroniza el vínculo evidencia <-> Competencias Específicas con lo marcado
        #en el botón "Vincular a Competencias Específicas" (motor curricular dinámico).
        if es_sistema_dominicano(_sistema_calificacion_actual()):
            c.execute("DELETE FROM calificacion_competencia WHERE calificacion_id=?", (calificacion_id,))
            for competencia_id in self._ce_vinculadas_registro:
                c.execute("""INSERT OR IGNORE INTO calificacion_competencia (calificacion_id, competencia_id)
                             VALUES (?,?)""", (calificacion_id, competencia_id))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", accion, self.main_window.usuario_actual,
                            f"Estudiante {estudiante_id} - {self.combo_categoria.currentText()}")
        self.id_edicion= None
        self.btn_guardar.setText("Registrar Calificación")
        self.in_descripcion.clear()
        self.spin_valor.setValue(0)
        self._cargar_registro_estudiante()

    def _periodo_esta_bloqueado(self, periodo_id, anio_academico=None):
        if periodo_id is None:
            return False
        anio= anio_academico or self._anio_academico_actual()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT bloqueado FROM periodo_bloqueo WHERE periodo_id=? AND anio_academico=?",
                  (periodo_id, anio))
        f= c.fetchone()
        conn.close()
        return bool(f and f["bloqueado"])

    def _actualizar_estado_bloqueo_periodo(self):
        if not hasattr(self, "btn_bloqueo_periodo"):
            return
        periodo_id= self.combo_periodo_boletin.currentData()
        bloqueado= self._periodo_esta_bloqueado(periodo_id)
        if bloqueado:
            self.btn_bloqueo_periodo.setText("Periodo Cerrado — Reabrir")
        else:
            self.btn_bloqueo_periodo.setText("Cerrar Periodo")
        self.btn_bloqueo_periodo.setVisible(tiene_acceso_gerencial(self.main_window))

    def _alternar_bloqueo_periodo(self):
        if not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                             "Solo un rol gerencial (Director, Coordinador o Administrador) puede cerrar "
                             "o reabrir un periodo.", self)
            return
        periodo_id= self.combo_periodo_boletin.currentData()
        if periodo_id is None:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un periodo primero.", self)
            return
        anio= self._anio_academico_actual()
        bloqueado_actual= self._periodo_esta_bloqueado(periodo_id, anio)
        nuevo_estado= 0 if bloqueado_actual else 1
        if not bloqueado_actual:
            #Validación académica (punto pedido): avisar si se va a cerrar un periodo que todavía no tiene ninguna
            #calificación registrada — probablemente sea un error, aunque se permite continuar si el gerencial confirma.
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT COUNT(*) as n FROM calificaciones WHERE periodo_id=?", (periodo_id,))
            n= c.fetchone()["n"]
            conn.close()
            if n == 0:
                resp= mostrar_mensaje("pregunta", "Periodo sin calificaciones",
                    "Este periodo todavía no tiene ninguna calificación registrada. "
                    "¿Cerrarlo de todas formas?", self)
                if resp != QMessageBox.StandardButton.Yes:
                    return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""INSERT INTO periodo_bloqueo (periodo_id, anio_academico, bloqueado, bloqueado_por, fecha_bloqueo)
                     VALUES (?,?,?,?,?)
                     ON CONFLICT(periodo_id, anio_academico) DO UPDATE SET
                        bloqueado= excluded.bloqueado, bloqueado_por=excluded.bloqueado_por,
                        fecha_bloqueo= excluded.fecha_bloqueo""",
                  (periodo_id, anio, nuevo_estado, self.main_window.usuario_actual,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        accion= "Cerró el periodo" if nuevo_estado else "Reabrió el periodo"
        registrar_auditoria("Calificaciones", accion, self.main_window.usuario_actual,
                            f"Periodo ID {periodo_id} - Año {anio}")
        self._actualizar_estado_bloqueo_periodo()
        mostrar_mensaje("exito", "Listo",
                         "El periodo fue cerrado." if nuevo_estado else "El periodo fue reabierto.", self)

    def _elegir_competencias_registro(self):
        materia_id= self.combo_materia.currentData()
        estudiante_id= self.combo_estudiante.currentData()
        grado_id= grado_de_estudiante(estudiante_id)
        if materia_id is None or grado_id is None:
            mostrar_mensaje("advertencia", "Faltan datos",
                             "Selecciona primero un estudiante (con sección) y una materia.", self)
            return
        dialogo= DialogoCompetenciasEspecificas(materia_id, grado_id, self._ce_vinculadas_registro, self)
        if dialogo.exec():
            self._ce_vinculadas_registro= dialogo.seleccionadas()
            self._actualizar_boton_competencias_registro()

    def _actualizar_boton_competencias_registro(self):
        if not hasattr(self, "btn_vincular_competencias"):
            return
        n= len(self._ce_vinculadas_registro)
        if n == 0:
            self.btn_vincular_competencias.setText("Vincular a Competencias Específicas")
        elif n == 1:
            self.btn_vincular_competencias.setText("1 Competencia Específica vinculada")
        else:
            self.btn_vincular_competencias.setText(f"{n} Competencias Específicas vinculadas")

    def _abrir_exportar_intercambio_calificaciones(self):
        materia_id= self.combo_materia.currentData()
        periodo_id= self.combo_periodo.currentData()
        DialogoExportarCalificaciones(
            self.main_window, materia_id, self.combo_materia.currentText(),
            periodo_id= periodo_id, periodo_nombre=self.combo_periodo.currentText(), parent=self).exec()

    def _abrir_importar_intercambio_calificaciones(self):
        dialogo= DialogoImportarCalificaciones(
            self.main_window, self.combo_materia, self.combo_periodo, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._cargar_registro_estudiante()

    def _ver_historial_calificacion(self):
        fila= self.tabla_registro.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una calificación de la tabla.", self)
            return
        id_calificacion= self.tabla_registro.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT campo, valor_anterior, valor_nuevo, usuario, motivo, fecha
                     FROM historial_cambios_calificaciones
                     WHERE tabla_origen='calificaciones' AND registro_id=?
                     ORDER BY fecha DESC""", (id_calificacion,))
        filas= c.fetchall()
        conn.close()
        dialogo= QDialog(self)
        dialogo.setWindowTitle(f"Historial de cambios — Calificación #{id_calificacion}")
        dialogo.setMinimumSize(560, 360)
        layout= QVBoxLayout(dialogo)
        if not filas:
            layout.addWidget(QLabel("Esta calificación no tiene cambios registrados en el historial "
                                     "(o fue creada antes de esta función)."))
        else:
            tabla= QTableWidget(len(filas), 5)
            aplicar_estructura_tabla(tabla)
            tabla.setHorizontalHeaderLabels(["Campo", "Valor Anterior", "Valor Nuevo", "Usuario", "Fecha"])
            tabla.horizontalHeader().setStretchLastSection(True)
            tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tabla.verticalHeader().setVisible(False)
            for i, f in enumerate(filas):
                tabla.setItem(i, 0, QTableWidgetItem(f["campo"] or ""))
                tabla.setItem(i, 1, QTableWidgetItem(f["valor_anterior"] or ""))
                tabla.setItem(i, 2, QTableWidgetItem(f["valor_nuevo"] or ""))
                tabla.setItem(i, 3, QTableWidgetItem(f["usuario"] or ""))
                tabla.setItem(i, 4, QTableWidgetItem(f["fecha"] or ""))
            layout.addWidget(tabla, 1)
        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(dialogo.reject)
        botones.accepted.connect(dialogo.accept)
        layout.addWidget(botones)
        dialogo.exec()
    def _cargar_registro_estudiante(self):
        estudiante_id= self.combo_estudiante.currentData()
        if estudiante_id is None:
            self.tabla_registro.setRowCount(0)
            self.paginacion_registro.establecer_total(0)
            self.estado_vacio_registro.actualizar(hay_filtro_elegido=False)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT calificaciones.*, materias.nombre as materia_nombre, periodos.nombre as periodo_nombre
                     FROM calificaciones
                     LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     LEFT JOIN periodos ON calificaciones.periodo_id = periodos.id
                     WHERE estudiante_id=? ORDER BY calificaciones.id DESC""", (estudiante_id,))
        filas= c.fetchall()
        conn.close()
        self.paginacion_registro.establecer_total(len(filas))
        inicio, fin = self.paginacion_registro.rango_actual()
        filas= filas[inicio:fin]
        self.tabla_registro.setRowCount(len(filas))
        with tabla_pausada(self.tabla_registro):
            for i, f in enumerate(filas):
                estado_pub= f["estado_publicacion"] or "Publicada"
                item_estado= QTableWidgetItem(estado_pub)
                #El ID interno de calificaciones sigue viajando con la fila (lo necesitan _cargar_calificacion_seleccionada,
                #_eliminar_calificacion, _ver_historial_calificacion y _boton_ver_descripcion_calificacion), solo que ya no se
                #muestra como texto: antes era un número interno sin significado para el docente, así que se reemplaza por el
                #estado de publicación (que sí es información útil que hoy no se ve en ningún otro lado de esta tabla) y el ID
                #pasa a dato oculto.
                item_estado.setData(Qt.ItemDataRole.UserRole, f["id"])
                item_estado.setForeground(QColor({"Publicada": "#10B981", "Pendiente": "#F59E0B",
                                                    "Borrador": "#9CA3AF"}.get(estado_pub, "#9CA3AF")))
                self.tabla_registro.setItem(i, 0, item_estado)
                candado= "" if f["solo_lectura"] else ""
                self.tabla_registro.setItem(i, 1, QTableWidgetItem(candado + (f["materia_nombre"] or "")))
                self.tabla_registro.setItem(i, 2, QTableWidgetItem(f["periodo_nombre"] or ""))
                categoria_txt= f["categoria"] or ""
                if f["solo_lectura"]:
                    categoria_txt += f" (importada de {f['importado_de'] or '—'})"
                self.tabla_registro.setItem(i, 3, QTableWidgetItem(categoria_txt))
                self.tabla_registro.setItem(i, 4, QTableWidgetItem(f["descripcion"] or ""))
                self.tabla_registro.setItem(i, 5, QTableWidgetItem(str(f["valor"])))
        if hasattr(self, "in_buscar_registro"):
            self._aplicar_busqueda_registro(self.in_buscar_registro.text())
        self.estado_vacio_registro.actualizar(hay_filtro_elegido=True)

    def _filtrar_tabla_texto(self, tabla, texto, columnas):
        """Helper genérico: oculta/muestra filas de `tabla` según si el texto
        (normalizado, sin tildes ni mayúsculas) aparece en alguna de las
        `columnas` indicadas. Reutilizado por las searchbars de las pestañas
        que no necesitan lógica de filtrado propia."""
        consulta= _normalizar_busqueda(texto)
        for fila in range(tabla.rowCount()):
            if not consulta:
                tabla.setRowHidden(fila, False)
                continue
            partes= []
            for col in columnas:
                item= tabla.item(fila, col)
                if item:
                    partes.append(item.text())
            tabla.setRowHidden(fila, consulta not in _normalizar_busqueda(" ".join(partes)))

    def _aplicar_busqueda_registro(self, texto=""):
        """Filtra las filas ya cargadas por materia, periodo, categoría o
        descripción, sin exigir tildes ni mayúsculas/minúsculas exactas."""
        if not hasattr(self, "tabla_registro"):
            return
        consulta= _normalizar_busqueda(texto)
        for fila in range(self.tabla_registro.rowCount()):
            if not consulta:
                self.tabla_registro.setRowHidden(fila, False)
                continue
            partes= []
            for col in (1, 2, 3, 4):  #Materia, Periodo, Categoría, Descripción
                item= self.tabla_registro.item(fila, col)
                if item:
                    partes.append(item.text())
            self.tabla_registro.setRowHidden(fila, consulta not in _normalizar_busqueda(" ".join(partes)))
    def _eliminar_calificacion(self):
        fila= self.tabla_registro.currentRow()
        if fila < 0:
            return
        id_cal= self.tabla_registro.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT solo_lectura, importado_de FROM calificaciones WHERE id=?", (id_cal,))
        f= c.fetchone()
        if f and f["solo_lectura"] and not tiene_acceso_gerencial(self.main_window):
            conn.close()
            mostrar_mensaje("advertencia", "Nota importada (solo lectura)",
                             f"Esta calificación fue importada de {f['importado_de'] or 'otro docente'} y no "
                             "se puede eliminar desde aquí. Un rol gerencial puede deshacer el paquete "
                             "completo en la pestaña Compartir Calificaciones.", self)
            return
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta calificación?", self) != QMessageBox.StandardButton.Yes:
            conn.close()
            return
        c.execute("DELETE FROM calificaciones WHERE id=?", (id_cal,))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", "Eliminó calificación", self.main_window.usuario_actual, str(id_cal))
        self._cargar_registro_estudiante()
    #---------------- BOLETÍN ----------------
    def _tab_boletin(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        #Área Técnica/Carrera van PRIMERO, en su propia fila: se eligen antes que Curso/Sección (mismo orden que en las
        #demás pestañas). Están en su propia fila -no a la derecha de nada- para que la pestaña crezca en ALTO y no en
        #ANCHO cuando ambos combos están visibles a la vez (institución "Personalizado").
        self.lbl_filtro_especialidad_boletin= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_boletin= QComboBox()
        self.combo_filtro_especialidad_boletin.setToolTip(
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.combo_filtro_especialidad_boletin.currentIndexChanged.connect(self._cargar_estudiantes_boletin)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_boletin,
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.lbl_filtro_carrera_boletin= QLabel("Carrera:")
        self.combo_filtro_carrera_boletin= QComboBox()
        self.combo_filtro_carrera_boletin.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        self.combo_filtro_carrera_boletin.currentIndexChanged.connect(self._cargar_estudiantes_boletin)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_boletin,
            "Filtrar por carrera del estudiante (Universidad)")
        self.combo_curso_boletin= QComboBox()
        self.combo_curso_boletin.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso_corto(self.combo_curso_boletin, self.combo_seccion_boletin),
                      self._cargar_estudiantes_boletin()))
        self.combo_seccion_boletin= QComboBox()
        self.combo_seccion_boletin.currentIndexChanged.connect(self._cargar_estudiantes_boletin)

        #Área Técnica/Carrera/Curso/Sección pasan a la ventana de "☰ Filtros" (mismo patrón que la pestaña Registrar
        #Calificación): solo acotan qué estudiante aparece abajo.
        self.dialogo_filtros_boletin= self._crear_dialogo_filtros(
            "Filtros del Boletín",
            "Curso y Sección acotan qué estudiante puedes elegir abajo. Área Técnica y Carrera son opcionales.",
            [(self.lbl_filtro_especialidad_boletin, self.combo_filtro_especialidad_boletin),
             (self.lbl_filtro_carrera_boletin, self.combo_filtro_carrera_boletin),
             ("Curso:", self.combo_curso_boletin),
             ("Sección:", self.combo_seccion_boletin)])
        fila_filtro_tecnico_boletin= QHBoxLayout()
        fila_filtro_tecnico_boletin.setSpacing(10)
        self.lbl_resumen_filtros_boletin= QLabel("")
        self.lbl_resumen_filtros_boletin.setWordWrap(True)
        fila_filtro_tecnico_boletin.addWidget(self.lbl_resumen_filtros_boletin, 1)
        self.btn_filtros_boletin= self._crear_boton_filtros("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_boletin.clicked.connect(lambda: self._abrir_dialogo_filtros(self.dialogo_filtros_boletin))
        fila_filtro_tecnico_boletin.addWidget(self.btn_filtros_boletin)
        l.addLayout(fila_filtro_tecnico_boletin)
        self.combo_curso_boletin.currentIndexChanged.connect(self._actualizar_resumen_filtros_boletin)
        self.combo_seccion_boletin.currentIndexChanged.connect(self._actualizar_resumen_filtros_boletin)
        self.combo_filtro_especialidad_boletin.currentIndexChanged.connect(self._actualizar_resumen_filtros_boletin)
        self.combo_filtro_carrera_boletin.currentIndexChanged.connect(self._actualizar_resumen_filtros_boletin)

        fila_filtros= QHBoxLayout()
        fila_filtros.setSpacing(10)
        self.combo_estudiante_boletin= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante_boletin, "Estudiante cuyo boletín se muestra")
        fila_filtros.addWidget(QLabel("Estudiante:"))
        fila_filtros.addWidget(self.combo_estudiante_boletin)
        self.combo_periodo_boletin= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo_boletin, "Periodo académico del boletín")
        fila_filtros.addWidget(QLabel("Periodo:"))
        fila_filtros.addWidget(self.combo_periodo_boletin)
        #Con 4 combos + botón en una sola fila, un min_len parejo de 16 (pensado para combos sueltos con nombres
        #largos, ej. materias) es demasiado: la suma de los 4 anchos fijos ya supera el espacio disponible con la
        #sidebar expandida. Cada combo recibe aquí solo el mínimo que necesita para su contenido real (Qt trunca con
        #"…" si algo no cabe, y el desplegable siempre muestra el texto completo igual).
        ajustar_combo_ancho_seguro(self.combo_curso_boletin, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_seccion_boletin, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_filtro_especialidad_boletin, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_filtro_carrera_boletin, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_estudiante_boletin, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_periodo_boletin, min_len=6)
        btn_generar= QPushButton("Generar Boletín")
        btn_generar.setIcon(icono_emoji(EMOJI_BOLETIN_PROMEDIOS))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.clicked.connect(self._generar_boletin_click)
        fila_filtros.addWidget(btn_generar)
        #Cierre de periodo (punto pedido): visible siempre, pero solo un rol gerencial puede accionarlo. Al cerrarse,
        #Registro/Desempeño/RP dejan de aceptar cambios de roles no gerenciales para ese periodo.
        self.btn_bloqueo_periodo= QPushButton("Cerrar Periodo")
        self.btn_bloqueo_periodo.setIcon(icono_emoji("🔒"))
        self.btn_bloqueo_periodo.setIconSize(_QSize_emoji(16, 16))
        self.btn_bloqueo_periodo.setObjectName("BtnAccionEliminar")
        self.btn_bloqueo_periodo.clicked.connect(self._alternar_bloqueo_periodo)
        self.btn_bloqueo_periodo.setVisible(tiene_acceso_gerencial(self.main_window))
        fila_filtros.addWidget(self.btn_bloqueo_periodo)
        self.combo_periodo_boletin.currentIndexChanged.connect(self._actualizar_estado_bloqueo_periodo)
        fila_filtros.addStretch()
        l.addLayout(fila_filtros)
        l.addSpacing(10)


        #Tabla estilo Omega POS (boletín)
        self.tabla_boletin= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_boletin)
        self.estado_vacio_boletin= EstadoVacioFiltro(self.tabla_boletin,
                                                        texto_filtra_primero= "Elige estudiante y periodo, luego genera el boletín")
        self.tabla_boletin.setHorizontalHeaderLabels(["Materia", "Nota Final", "Estado", "RP"])
        header= self.tabla_boletin.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #OJO: NO combinar setStretchLastSection(True) con una columna ya puesta en modo Stretch (ver "Materia" abajo).
        #Ambas compiten por el espacio sobrante del header, y como "Nota Final"/"Estado" quedan con un ancho
        #interactivo mínimo pequeño, casi todo ese sobrante termina cayendo en la última columna ("RP"), que se ve
        #absurdamente ancha (el bug reportado). "Materia" ya es la columna Stretch que debe absorber el espacio libre;
        #a "RP" (y a "Nota Final"/"Estado") les damos un ancho fijo razonable en su lugar, para que la tabla se vea
        #equilibrada sin importar cuánto espacio sobre.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  #"Materia"
        self.tabla_boletin.setColumnWidth(1, 100)   #"Nota Final"
        self.tabla_boletin.setColumnWidth(2, 110)   #"Estado"
        self.tabla_boletin.setColumnWidth(3, 140)   #"RP"
        self.tabla_boletin.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_boletin.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_boletin.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_boletin.setAlternatingRowColors(True)
        self.tabla_boletin.setWordWrap(True)
        self.tabla_boletin.setMinimumHeight(340)
        self.tabla_boletin.verticalHeader().setVisible(False)
        l.addWidget(self.tabla_boletin, 1)
        self.paginacion_boletin= ControlPaginacion(tamano_inicial=25)
        self.paginacion_boletin.cambio.connect(self._generar_boletin)
        l.addWidget(self.paginacion_boletin)
        l.addSpacing(10)

        agregar_boton_pantalla_completa(
            None, [self.tabla_boletin, self.paginacion_boletin],
            titulo= "Boletín", parent=self)

        self.lbl_promedio_general= QLabel("Promedio General: --")
        self.lbl_promedio_general.setObjectName("DescModulo")
        panel_resumen_boletin= _crear_panel_dashboard()
        fila_promedio= panel_resumen_boletin.layout()
        self.tarjeta_promedio_boletin= TarjetaAlerta("📈", "Promedio General", "#10B981")
        self._tarjetas_alerta.append(self.tarjeta_promedio_boletin)
        fila_promedio.addWidget(self.tarjeta_promedio_boletin)
        self.dona_boletin= GraficoDona(diametro=104, grosor=14)
        col_dona_boletin= QVBoxLayout()
        col_dona_boletin.setSpacing(2)
        col_dona_boletin.addWidget(self.dona_boletin, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_dona_boletin= QLabel("")
        self.lbl_dona_boletin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_dona_boletin.setObjectName("DescModulo")
        col_dona_boletin.addWidget(self.lbl_dona_boletin)
        fila_promedio.addLayout(col_dona_boletin)
        columna_promedio= QVBoxLayout()
        columna_promedio.addWidget(self.lbl_promedio_general)
        columna_promedio.addStretch()
        fila_promedio.addLayout(columna_promedio, 1)
        l.addWidget(panel_resumen_boletin)
        fila_acciones_boletin= QHBoxLayout()
        btn_pdf= QPushButton("Exportar Boletín a PDF")
        btn_pdf.setIcon(icono_emoji("\uE002"))
        btn_pdf.setIconSize(_QSize_emoji(16, 16))
        btn_pdf.setObjectName("BtnAccionEditar")
        btn_pdf.clicked.connect(self._exportar_pdf)
        fila_acciones_boletin.addWidget(btn_pdf)
        self.btn_rp= QPushButton("Registrar Nota de Recuperación Pedagógica (RP)")
        self.btn_rp.setIcon(icono_emoji("✏"))
        self.btn_rp.setIconSize(_QSize_emoji(16, 16))
        self.btn_rp.setObjectName("BtnAccionAjustar")
        self.btn_rp.clicked.connect(self._registrar_rp)
        self.btn_rp.setVisible(False)
        fila_acciones_boletin.addWidget(self.btn_rp)
        btn_detalle_bol= agregar_boton_detalle(fila_acciones_boletin, self.tabla_boletin, self,
                                                 titulo= "Detalle de la Nota")
        self.tabla_boletin.doubleClicked.connect(lambda *_: btn_detalle_bol.click())
        fila_acciones_boletin.addStretch()
        l.addLayout(fila_acciones_boletin)
        #--- Exportación masiva por Curso (todas sus secciones a la vez) ---
        linea= QLabel("Exportación Masiva de Boletines (todo un curso, incluye todas sus secciones):")
        linea.setObjectName("DescModulo")
        l.addWidget(linea)
        fila_masiva= QHBoxLayout()
        self.combo_curso_masivo= QComboBox()
        fila_masiva.addWidget(QLabel("Curso:"))
        fila_masiva.addWidget(self.combo_curso_masivo)
        self.combo_especialidad_masivo= QComboBox()
        conectar_tooltip_seleccion(self.combo_especialidad_masivo, "Área técnica para el registro masivo (Politécnico)")
        fila_masiva.addWidget(QLabel("Área Técnica:"))
        fila_masiva.addWidget(self.combo_especialidad_masivo)
        self.combo_periodo_masivo= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo_masivo, "Periodo académico del registro masivo")
        fila_masiva.addWidget(QLabel("Periodo:"))
        fila_masiva.addWidget(self.combo_periodo_masivo)
        ajustar_combo_ancho_seguro(self.combo_curso_masivo, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_especialidad_masivo, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_periodo_masivo, min_len=6)
        btn_masivo= QPushButton("Exportar Boletines por Curso (PDF)")
        btn_masivo.setIcon(icono_emoji("\uE002"))
        btn_masivo.setIconSize(_QSize_emoji(16, 16))
        btn_masivo.setObjectName("BtnAccionAjustar")
        btn_masivo.clicked.connect(self._exportar_boletines_masivo)
        fila_masiva.addWidget(btn_masivo)
        fila_masiva.addStretch()
        l.addLayout(fila_masiva)
        l.addStretch(1)
        return w
    def _cargar_estudiantes_boletin(self):
        self.combo_estudiante_boletin.clear()
        self.combo_estudiante_boletin.addItem("Elige estudiante", None)
        seccion_id= self.combo_seccion_boletin.currentData()
        permitidas= self._permitidas_secciones()
        especialidad_id= self.combo_filtro_especialidad_boletin.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_filtro_carrera_boletin.currentData() if self._es_universidad() else None
        for f in self._estudiantes_activos():
            if seccion_id is not None and f["seccion_id"] != seccion_id:
                continue
            if permitidas is not None and f["seccion_id"] not in permitidas:
                continue
            if especialidad_id == 0 and f["especialidad_id"] is not None:
                continue
            elif especialidad_id not in (None, 0) and f["especialidad_id"] != especialidad_id:
                continue
            if carrera_id == 0 and f["carrera_id"] is not None:
                continue
            elif carrera_id not in (None, 0) and f["carrera_id"] != carrera_id:
                continue
            self.combo_estudiante_boletin.addItem(f"{f['nombre']} {f['apellidos'] or ''}", f["id"])
        _actualizar_estado_combo_estudiante(self.combo_curso_boletin, self.combo_seccion_boletin,
                                             self.combo_estudiante_boletin)
        self._actualizar_resumen_filtros_boletin()

    def _actualizar_resumen_filtros_boletin(self):
        if not hasattr(self, "lbl_resumen_filtros_boletin"):
            return
        self.lbl_resumen_filtros_boletin.setText(self._resumen_filtros_texto([
            ("Curso", self.combo_curso_boletin), ("Sección", self.combo_seccion_boletin),
            ("Área Técnica", self.combo_filtro_especialidad_boletin),
            ("Carrera", self.combo_filtro_carrera_boletin),
        ]))

    def _cargar_especialidad_carrera_boletin(self):
        """Igual que en Banco de Tareas: los combos de Área Técnica y Carrera de
        'Boletín / Promedios' solo se muestran/pueblan si la institución tiene
        ese módulo activo."""
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_boletin.setVisible(es_poli)
        self.combo_filtro_especialidad_boletin.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_boletin.currentData()
            self.combo_filtro_especialidad_boletin.blockSignals(True)
            self.combo_filtro_especialidad_boletin.clear()
            self.combo_filtro_especialidad_boletin.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_boletin.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_especialidad_boletin, "No Área Técnica")
            idx= self.combo_filtro_especialidad_boletin.findData(actual)
            self.combo_filtro_especialidad_boletin.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_boletin.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_boletin.setVisible(es_uni)
        self.combo_filtro_carrera_boletin.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_boletin.currentData()
            self.combo_filtro_carrera_boletin.blockSignals(True)
            self.combo_filtro_carrera_boletin.clear()
            self.combo_filtro_carrera_boletin.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_boletin.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_carrera_boletin, "No Carrera")
            idx= self.combo_filtro_carrera_boletin.findData(actual)
            self.combo_filtro_carrera_boletin.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_boletin.blockSignals(False)
    def _cargar_secciones_masivo(self):
        self._poblar_combo_curso(self.combo_curso_masivo, incluir_todos=False)
        _acortar_placeholder_combo(self.combo_curso_masivo, "Selecciona curso")
        self._poblar_combo_especialidad_masivo()

    def _poblar_combo_especialidad_masivo(self):
        """Llena el combo de Área Técnica para filtrar la exportación masiva de
        boletines. 'Todas las áreas' queda como opción 0 (sin dato asociado),
        de modo que un curso sin especialidades definidas se pueda exportar
        igual sin necesidad de elegir una."""
        seleccion_previa= self.combo_especialidad_masivo.currentData()
        self.combo_especialidad_masivo.blockSignals(True)
        self.combo_especialidad_masivo.clear()
        self.combo_especialidad_masivo.addItem("Todas las áreas", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for f in c.fetchall():
            self.combo_especialidad_masivo.addItem(f["nombre"], f["id"])
        conn.close()
        if seleccion_previa is not None:
            idx= self.combo_especialidad_masivo.findData(seleccion_previa)
            if idx >= 0:
                self.combo_especialidad_masivo.setCurrentIndex(idx)
        self.combo_especialidad_masivo.blockSignals(False)
    def _obtener_metodo_y_minima(self, estudiante_id=None, seccion_id=None):
        """`nota_minima` resuelta correctamente para el Sistema Dominicano: si se
        pasa `estudiante_id` o `seccion_id`, se usa el nivel_educativo (Primaria/
        Secundaria) del Grado/Curso correspondiente (ver resolver_nota_minima()
        en configuracion.py); un estudiante y su sección comparten siempre el
        mismo Grado, así que basta pasar cualquiera de los dos que ya se tenga
        a mano en el sitio de la llamada. Sin ninguno de los dos (o para
        sistemas que no sean el Dominicano) se usa la nota mínima general,
        exactamente como antes."""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT metodo_calculo, nota_minima, nota_minima_primaria, nota_minima_secundaria,
                     sistema_calificacion FROM configuracion WHERE id=1""")
        cfg= c.fetchone()
        nivel_educativo= None
        if estudiante_id is not None:
            c.execute("""SELECT grados.nivel_educativo as nivel FROM estudiantes
                         LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                         LEFT JOIN grados ON secciones.grado_id = grados.id WHERE estudiantes.id=?""",
                      (estudiante_id,))
            f= c.fetchone()
            nivel_educativo= f["nivel"] if f else None
        elif seccion_id is not None:
            c.execute("""SELECT grados.nivel_educativo as nivel FROM secciones
                         LEFT JOIN grados ON secciones.grado_id = grados.id WHERE secciones.id=?""",
                      (seccion_id,))
            f= c.fetchone()
            nivel_educativo= f["nivel"] if f else None
        conn.close()
        if not cfg:
            return "Promedio Ponderado", 70
        return cfg["metodo_calculo"], resolver_nota_minima(cfg, nivel_educativo=nivel_educativo)
    def _notas_por_materia(self, estudiante_id, periodo_id, metodo):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT calificaciones.*, materias.nombre as materia_nombre FROM calificaciones
                     LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     WHERE estudiante_id=? AND periodo_id=?""", (estudiante_id, periodo_id))
        filas= c.fetchall()
        conn.close()
        por_materia= {}
        for f in filas:
            por_materia.setdefault(f["materia_nombre"] or "Sin materia", []).append(
                {"valor": f["valor"], "peso": f["peso"]})
        resultado= {}
        for materia, calif in por_materia.items():
            resultado[materia]= calcular_nota_final(calif, metodo)
        return resultado
    def _notas_por_materia_id(self, estudiante_id, periodo_id, metodo):
        """Como _notas_por_materia, pero conserva materia_id (necesario para la RP)."""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT calificaciones.*, materias.id as materia_id, materias.nombre as materia_nombre
                     FROM calificaciones LEFT JOIN materias ON calificaciones.materia_id = materias.id
                     WHERE estudiante_id=? AND periodo_id=?""", (estudiante_id, periodo_id))
        filas= c.fetchall()
        conn.close()
        por_materia= {}
        for f in filas:
            clave= f["materia_id"]
            if clave not in por_materia:
                por_materia[clave]= {"nombre": f["materia_nombre"] or "Sin materia", "notas": []}
            por_materia[clave]["notas"].append({"valor": f["valor"], "peso": f["peso"]})
        resultado= []
        for materia_id, datos in por_materia.items():
            resultado.append({"materia_id": materia_id, "materia_nombre": datos["nombre"],
                               "nota_final": calcular_nota_final(datos["notas"], metodo)})
        return resultado
    def _obtener_rp(self, estudiante_id, materia_id, periodo_id):
        if materia_id is None or estudiante_id is None or periodo_id is None:
            return None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT nota_rp FROM recuperacion_pedagogica
                     WHERE estudiante_id=? AND materia_id=? AND periodo_id=?""",
                  (estudiante_id, materia_id, periodo_id))
        f= c.fetchone()
        conn.close()
        return f["nota_rp"] if f else None
    def _obtener_rp_completa(self, estudiante_id, materia_id, periodo_id):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT * FROM recuperacion_pedagogica
                     WHERE estudiante_id=? AND materia_id=? AND periodo_id=?""",
                  (estudiante_id, materia_id, periodo_id))
        f= c.fetchone()
        conn.close()
        return dict(f) if f else None
    def _guardar_rp(self, estudiante_id, materia_id, periodo_id, nota_rp, observacion="",
                     actividades_realizadas= "", docente_responsable="", fecha=None):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""INSERT INTO recuperacion_pedagogica
                     (estudiante_id, materia_id, periodo_id, nota_rp, fecha, observacion,
                      actividades_realizadas, docente_responsable)
                     VALUES (?,?,?,?,?,?,?,?)
                     ON CONFLICT(estudiante_id, materia_id, periodo_id) DO UPDATE SET
                        nota_rp= excluded.nota_rp, fecha=excluded.fecha, observacion=excluded.observacion,
                        actividades_realizadas= excluded.actividades_realizadas,
                        docente_responsable= excluded.docente_responsable""",
                  (estudiante_id, materia_id, periodo_id, nota_rp,
                   fecha or datetime.now().strftime("%Y-%m-%d %H:%M:%S"), observacion,
                   actividades_realizadas, docente_responsable))
        conn.commit()
        conn.close()
    def _estado_materia_texto(self, nota_final, nota_minima, rp, dominicano):
        if nota_final >= nota_minima:
            return ("Competencia Alcanzada" if dominicano else "Aprobado"), (f"{rp:.2f}" if rp is not None else "-")
        if not dominicano:
            return "Reprobado", "-"
        if rp is None:
            return "Requiere RP", "-"
        return ("RP Superada" if rp >= nota_minima else "RP Pendiente"), f"{rp:.2f}"
    def _materias_de_seccion(self, seccion_id):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT materias.id, materias.nombre FROM horarios
                     LEFT JOIN materias ON horarios.materia_id = materias.id
                     WHERE horarios.seccion_id=? AND materias.id IS NOT NULL
                     ORDER BY materias.nombre""", (seccion_id,))
        filas= c.fetchall()
        conn.close()
        return filas
    def _construir_filas_boletin(self, estudiante_id, periodo_id, metodo, nota_minima, dominicano):
        entradas= self._notas_por_materia_id(estudiante_id, periodo_id, metodo)
        filas= []
        for e in entradas:
            rp= self._obtener_rp(estudiante_id, e["materia_id"], periodo_id) if dominicano else None
            estado, rp_txt = self._estado_materia_texto(e["nota_final"], nota_minima, rp, dominicano)
            filas.append({"materia_id": e["materia_id"], "materia_nombre": e["materia_nombre"],
                           "nota_final": e["nota_final"], "estado": estado, "rp_txt": rp_txt})
        return filas
    def _validar_alcance_tecnico_boletin(self):
        """Área Técnica/Carrera son OBLIGATORIOS antes de generar un boletín si
        la institución es puramente Politécnico o puramente Universidad (o
        "Personalizado" con solo uno de los dos módulos activo). Solo se llama
        desde el botón/atajo "Generar Boletín" -no desde la paginación ni
        desde llamadas internas- para no interrumpir con un aviso cada vez
        que se repagina o se refresca la tabla."""
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        if self._es_politecnico() and not ambos_activos and self.combo_filtro_especialidad_boletin.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica antes de "
                           "generar el boletín.", self)
            return False
        if self._es_universidad() and not ambos_activos and self.combo_filtro_carrera_boletin.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera antes de "
                           "generar el boletín.", self)
            return False
        return True

    def _generar_boletin_click(self):
        if not self._validar_alcance_tecnico_boletin():
            return
        self._generar_boletin()

    def _generar_boletin(self):
        estudiante_id= self.combo_estudiante_boletin.currentData()
        periodo_id= self.combo_periodo_boletin.currentData()
        if estudiante_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona un estudiante y un periodo.", self)
            self.estado_vacio_boletin.actualizar(hay_filtro_elegido=False)
            return
        metodo, nota_minima = self._obtener_metodo_y_minima(estudiante_id=estudiante_id)
        dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        filas= self._construir_filas_boletin(estudiante_id, periodo_id, metodo, nota_minima, dominicano)
        self.paginacion_boletin.establecer_total(len(filas))
        inicio, fin = self.paginacion_boletin.rango_actual()
        pagina= filas[inicio:fin]
        self.tabla_boletin.setRowCount(len(pagina))
        with tabla_pausada(self.tabla_boletin):
            for i, fila in enumerate(pagina):
                item_materia= QTableWidgetItem(fila["materia_nombre"])
                item_materia.setData(Qt.ItemDataRole.UserRole, fila["materia_id"])
                self.tabla_boletin.setItem(i, 0, item_materia)
                self.tabla_boletin.setItem(i, 1, QTableWidgetItem(f"{fila['nota_final']:.2f}"))
                self.tabla_boletin.setItem(i, 2, QTableWidgetItem(fila["estado"]))
                self.tabla_boletin.setItem(i, 3, QTableWidgetItem(fila["rp_txt"]))
        notas= [f["nota_final"] for f in filas]
        promedio_general= sum(notas) / len(notas) if notas else 0
        self.lbl_promedio_general.setText(f"Promedio General: {promedio_general:.2f}  |  Método: {metodo}")
        if hasattr(self, "tarjeta_promedio_boletin"):
            en_riesgo= bool(notas) and promedio_general < nota_minima
            color= "#EF4444" if en_riesgo else "#10B981"
            self.tarjeta_promedio_boletin.actualizar(f"{promedio_general:.2f}" if notas else "--",
                                                      alerta= en_riesgo, color=color)
        if hasattr(self, "dona_boletin"):
            colores_estado= {"Competencia Alcanzada": "#10B981", "Aprobado": "#10B981",
                               "RP Superada": "#3B82F6", "RP Pendiente": "#F59E0B",
                               "Requiere RP": "#EF4444", "Reprobado": "#EF4444"}
            conteo= {}
            for f in filas:
                conteo[f["estado"]]= conteo.get(f["estado"], 0) + 1
            self.dona_boletin.actualizar(
                [(estado, cant, colores_estado.get(estado, "#94A3B8")) for estado, cant in conteo.items()],
                total_texto= str(len(filas)), etiqueta="materias")
            if hasattr(self, "lbl_dona_boletin"):
                self.lbl_dona_boletin.setText("materias")
        self.estado_vacio_boletin.actualizar(hay_filtro_elegido=True)

    def _registrar_rp(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar notas de RP.", self)
            return
        fila= self.tabla_boletin.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una materia del boletín.", self)
            return
        materia_id= self.tabla_boletin.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        estudiante_id= self.combo_estudiante_boletin.currentData()
        periodo_id= self.combo_periodo_boletin.currentData()
        if materia_id is None or estudiante_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "No se pudo identificar la materia seleccionada.", self)
            return
        if self._periodo_esta_bloqueado(periodo_id) and not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Periodo cerrado",
                             "Este periodo fue cerrado y ya no admite cambios de RP.", self)
            return
        actual= self._obtener_rp_completa(estudiante_id, materia_id, periodo_id) or {}
        dialogo= DialogoRecuperacionPedagogica(actual, self.main_window.usuario_actual, self)
        if not dialogo.exec():
            return
        datos= dialogo.datos()
        self._guardar_rp(estudiante_id, materia_id, periodo_id, datos["nota_rp"], datos["observacion"],
                          datos["actividades_realizadas"], datos["docente_responsable"], datos["fecha"])
        registrar_auditoria("Calificaciones", "Registró Recuperación Pedagógica (RP)",
                            self.main_window.usuario_actual,
                            f"Estudiante ID {estudiante_id} - Materia ID {materia_id} - Periodo ID {periodo_id}: "
                            f"{datos['nota_rp']}")
        self._generar_boletin()
    def _dibujar_boletin_pagina(self, cvs, ancho, alto, institucion, estudiante_txt, periodo_txt,
                                 filas, promedio_general, metodo, mostrar_rp=False, nota_minima=None):
        """Diseño en tarjeta + tabla con bandas de color (en vez de simples
        líneas de texto): encabezado de tabla con fondo de color, filas
        zebra para lectura rápida, estado con color semántico, y el nombre
        de cada materia se ENVUELVE en varias líneas si hace falta (nunca se
        corta ni se sale de su columna, sin importar cuán largo sea)."""
        from reportlab.lib.colors import HexColor

        COLOR_BANDA= HexColor("#4F46E5")
        COLOR_BANDA_TEXTO= HexColor("#FFFFFF")
        COLOR_ZEBRA= HexColor("#F5F6FA")
        COLOR_BORDE= HexColor("#E2E4EA")
        COLOR_TEXTO= HexColor("#1F2430")
        COLOR_TARJETA= HexColor("#F3F4F8")
        COLORES_ESTADO= {"Competencia Alcanzada": "#10B981", "Aprobado": "#10B981",
                          "RP Superada": "#3B82F6", "RP Pendiente": "#F59E0B",
                          "Requiere RP": "#EF4444", "Reprobado": "#EF4444"}

        margen= 50
        ancho_util= ancho - 2 * margen

        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Boletín de Calificaciones")

        #--- Tarjeta con los datos del estudiante/periodo ---
        alto_tarjeta= 40
        cvs.setFillColor(COLOR_TARJETA)
        cvs.roundRect(margen, y - alto_tarjeta, ancho_util, alto_tarjeta, 6, fill=1, stroke=0)
        cvs.setFillColor(COLOR_TEXTO)
        cvs.setFont("Helvetica-Bold", 10.5)
        cvs.drawString(margen + 14, y - 17, _recortar_a_ancho(cvs, f"Estudiante: {estudiante_txt}",
                                                               "Helvetica-Bold", 10.5, ancho_util * 0.6))
        cvs.setFont("Helvetica", 9)
        cvs.drawString(margen + 14, y - 31, f"Periodo: {periodo_txt}")
        cvs.setFont("Helvetica", 8.5)
        cvs.drawRightString(ancho - margen - 14, y - 17, f"Método: {metodo}")
        cvs.drawRightString(ancho - margen - 14, y - 31, f"Emitido: {datetime.now().strftime('%Y-%m-%d')}")
        y -= alto_tarjeta + 16

        #--- Columnas de la tabla (proporcionales al ancho disponible) ---
        if mostrar_rp:
            col_materia_w= ancho_util * 0.46
            col_nota_w= ancho_util * 0.16
            col_estado_w= ancho_util * 0.24
            col_rp_w= ancho_util * 0.14
        else:
            col_materia_w= ancho_util * 0.56
            col_nota_w= ancho_util * 0.20
            col_estado_w= ancho_util * 0.24
            col_rp_w= 0

        x_materia= margen
        x_nota= x_materia + col_materia_w
        x_estado= x_nota + col_nota_w
        x_rp= x_estado + col_estado_w

        def _dibujar_cabecera_tabla(y_top):
            alto_enc= 22
            cvs.setFillColor(COLOR_BANDA)
            cvs.roundRect(margen, y_top - alto_enc, ancho_util, alto_enc, 4, fill=1, stroke=0)
            cvs.rect(margen, y_top - alto_enc, ancho_util, alto_enc / 2, fill=1, stroke=0)
            cvs.setFillColor(COLOR_BANDA_TEXTO)
            cvs.setFont("Helvetica-Bold", 8.5)
            cvs.drawString(x_materia + 10, y_top - 15, "MATERIA")
            cvs.drawCentredString(x_nota + col_nota_w / 2, y_top - 15, "NOTA FINAL")
            cvs.drawCentredString(x_estado + col_estado_w / 2, y_top - 15, "ESTADO")
            if mostrar_rp:
                cvs.drawCentredString(x_rp + col_rp_w / 2, y_top - 15, "RP")
            return y_top - alto_enc

        y= _dibujar_cabecera_tabla(y)

        alto_linea= 11
        cvs.setFont("Helvetica", 9)
        zebra= False
        for fila in filas:
            lineas_materia= _envolver_texto(cvs, fila["materia_nombre"], "Helvetica", 9, col_materia_w - 20)
            alto_fila= max(len(lineas_materia) * alto_linea + 8, 22)

            if y - alto_fila < 118:
                _dibujar_pie_pagina(cvs, ancho, institucion, incluir_firma=False)
                cvs.showPage()
                y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Boletín de Calificaciones")
                y= _dibujar_cabecera_tabla(y)
                zebra= False

            if zebra:
                cvs.setFillColor(COLOR_ZEBRA)
                cvs.rect(margen, y - alto_fila, ancho_util, alto_fila, fill=1, stroke=0)
            zebra= not zebra

            cvs.setStrokeColor(COLOR_BORDE)
            cvs.setLineWidth(0.5)
            cvs.rect(margen, y - alto_fila, ancho_util, alto_fila, fill=0, stroke=1)

            #Nombre de materia, centrado verticalmente, envuelto en N líneas
            bloque_alto= len(lineas_materia) * alto_linea
            y_texto= y - (alto_fila - bloque_alto) / 2 - alto_linea + 2
            cvs.setFillColor(COLOR_TEXTO)
            cvs.setFont("Helvetica", 9)
            for linea in lineas_materia:
                cvs.drawString(x_materia + 10, y_texto, linea)
                y_texto -= alto_linea

            y_centro= y - alto_fila / 2 - 3
            cvs.setFont("Helvetica-Bold", 9)
            cvs.drawCentredString(x_nota + col_nota_w / 2, y_centro, f"{fila['nota_final']:.2f}")

            color_estado= HexColor(COLORES_ESTADO.get(fila["estado"], "#4B5563"))
            cvs.setFillColor(color_estado)
            cvs.setFont("Helvetica-Bold", 8)
            estado_txt= _recortar_a_ancho(cvs, fila["estado"], "Helvetica-Bold", 8, col_estado_w - 8)
            cvs.drawCentredString(x_estado + col_estado_w / 2, y_centro, estado_txt)
            cvs.setFillColor(COLOR_TEXTO)

            if mostrar_rp:
                cvs.setFont("Helvetica", 8.5)
                cvs.drawCentredString(x_rp + col_rp_w / 2, y_centro, fila["rp_txt"] or "—")

            y -= alto_fila

        if not filas:
            cvs.setFont("Helvetica-Oblique", 9.5)
            cvs.setFillColor(HexColor("#6B7280"))
            cvs.drawCentredString(ancho / 2, y - 20, "No hay calificaciones registradas para este periodo.")
            cvs.setFillColor(COLOR_TEXTO)
            y -= 36

        #--- Promedio general, en una tarjeta destacada ---
        y -= 14
        color_promedio= "#10B981"
        if nota_minima is not None and filas:
            color_promedio= "#EF4444" if promedio_general < nota_minima else "#10B981"
        alto_badge= 30
        cvs.setFillColor(HexColor(color_promedio))
        cvs.roundRect(margen, y - alto_badge, ancho_util, alto_badge, 6, fill=1, stroke=0)
        cvs.setFillColor(HexColor("#FFFFFF"))
        cvs.setFont("Helvetica-Bold", 12)
        cvs.drawCentredString(ancho / 2, y - alto_badge / 2 - 4, f"Promedio General: {promedio_general:.2f}")
        cvs.setFillColor(COLOR_TEXTO)
    def _exportar_pdf(self):
        if self.tabla_boletin.rowCount() == 0:
            mostrar_mensaje("advertencia", "Sin datos", "Genera el boletín antes de exportar.", self)
            return
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'reportlab' (pip install reportlab) para exportar boletines en PDF.", self)
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Boletín", "boletin.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        institucion= _datos_institucion()
        estudiante_id= self.combo_estudiante_boletin.currentData()

        #Boletín Oficial RD (ver boletin_minerd.py): grilla MINERD completa con competencias fundamentales, cascada de
        #evaluación, etc. Se activa desde Configuración > Calificaciones; si no, sigue el boletín simple de siempre
        #(código sin cambios más abajo).
        try:
            from src.boletines.boletin_minerd import formato_boletin_general, exportar_boletin_general_oficial_pdf
        except ImportError:
            formato_boletin_general= lambda: "simple"
        if formato_boletin_general() == "oficial_rd":
            boletin= exportar_boletin_general_oficial_pdf(estudiante_id, ruta, institucion)
            if boletin is None:
                mostrar_mensaje("error", "Sin datos", "No se encontró el estudiante seleccionado.", self)
                return
            registrar_auditoria("Calificaciones", "Exportó boletín PDF (formato oficial RD)",
                               self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Boletín exportado", f"Boletín guardado en:\n{ruta}", self)
            return

        periodo_id= self.combo_periodo_boletin.currentData()
        metodo, nota_minima = self._obtener_metodo_y_minima(estudiante_id=estudiante_id)
        dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        filas= self._construir_filas_boletin(estudiante_id, periodo_id, metodo, nota_minima, dominicano)
        notas= [f["nota_final"] for f in filas]
        promedio_general= sum(notas) / len(notas) if notas else 0
        estudiante_txt= self.combo_estudiante_boletin.currentText()
        periodo_txt= self.combo_periodo_boletin.currentText()
        if WorkerHilo is not None:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)

            def _tarea_boletin():
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfgen import canvas as _canvas
                _cvs= _canvas.Canvas(ruta, pagesize=letter)
                _ancho, _alto = letter
                self._dibujar_boletin_pagina(_cvs, _ancho, _alto, institucion,
                                             estudiante_txt, periodo_txt,
                                             filas, promedio_general, metodo,
                                             mostrar_rp= dominicano, nota_minima=nota_minima)
                _dibujar_pie_pagina(_cvs, _ancho, institucion)
                _cvs.save()

            def _on_boletin_ok(_):
                from PySide6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
                registrar_auditoria("Calificaciones", "Exportó boletín PDF",
                                   self.main_window.usuario_actual, ruta)
                mostrar_mensaje("exito", "Boletín exportado",
                               f"Boletín guardado en:\n{ruta}", self)

            self._hilo_boletin_simple= WorkerHilo(_tarea_boletin)
            self._hilo_boletin_simple.terminado.connect(_on_boletin_ok)
            self._hilo_boletin_simple.error.connect(lambda msg: (
                QApplication.restoreOverrideCursor(),
                mostrar_mensaje("error", "Error al exportar", msg.split("\n")[0], self)))
            self._hilo_boletin_simple.start()
        else:
            cvs= canvas.Canvas(ruta, pagesize=letter)
            ancho, alto = letter
            self._dibujar_boletin_pagina(cvs, ancho, alto, institucion,
                                         estudiante_txt, periodo_txt,
                                         filas, promedio_general, metodo, mostrar_rp=dominicano,
                                         nota_minima= nota_minima)
            _dibujar_pie_pagina(cvs, ancho, institucion)
            cvs.save()
            registrar_auditoria("Calificaciones", "Exportó boletín PDF",
                               self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Boletín exportado", f"Boletín guardado en:\n{ruta}", self)
    def _exportar_boletines_masivo(self):
        curso_id= self.combo_curso_masivo.currentData()
        periodo_id= self.combo_periodo_masivo.currentData()
        if curso_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona un curso y un periodo.", self)
            return
        permitidas= self._permitidas_secciones()
        secciones_del_curso= [s["id"] for s in self._secciones_con_grado() if s["grado_id"] == curso_id
                                and (permitidas is None or s["id"] in permitidas)]
        if not secciones_del_curso:
            mostrar_mensaje("advertencia", "Sin secciones", "Este curso no tiene secciones disponibles para ti.", self)
            return

        #Boletín Oficial RD (Fase 3, ver boletin_completo.py): un solo PDF con el boletín completo (todas las materias
        #de todos los docentes + página técnica si aplica) de cada estudiante del curso. Sustituye por completo el
        #flujo del boletín simple de abajo cuando el formato oficial está activo -el periodo elegido en este diálogo no
        #aplica aquí porque el boletín oficial siempre muestra los 4 períodos del año en una sola grilla, no uno a la
        #vez.
        try:
            from src.boletines.boletin_minerd import formato_boletin_general
            from src.boletines.boletin_completo import exportar_boletines_multiples_secciones_pdf
        except ImportError:
            formato_boletin_general= lambda: "simple"
        if formato_boletin_general() == "oficial_rd":
            curso_nombre= self.combo_curso_masivo.currentText().replace(" ", "_").replace("/", "-")
            ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Boletines Masivos",
                                                  f"boletines_{curso_nombre}.pdf", "PDF (*.pdf)")
            if not ruta:
                return
            institucion= _datos_institucion()
            resultado= exportar_boletines_multiples_secciones_pdf(secciones_del_curso, ruta, institucion)
            if resultado["generados"] == 0:
                mostrar_mensaje("advertencia", "Sin estudiantes",
                               "No hay estudiantes activos con datos para ese curso.", self)
                return
            registrar_auditoria("Calificaciones", "Exportó boletines masivos (formato oficial RD)",
                               self.main_window.usuario_actual, ruta)
            aviso_omitidos= (f"\n({len(resultado['omitidos'])} estudiante(s) omitido(s) por datos incompletos)"
                              if resultado["omitidos"] else "")
            mostrar_mensaje("exito", "Boletines exportados",
                           f"{resultado['generados']} boletines guardados en:\n{ruta}{aviso_omitidos}", self)
            return

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'reportlab' (pip install reportlab) para exportar boletines en PDF.", self)
            return
        especialidad_id= self.combo_especialidad_masivo.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        marcadores= ",".join("?" * len(secciones_del_curso))
        parametros= list(secciones_del_curso)
        filtro_especialidad= ""
        if especialidad_id is not None:
            filtro_especialidad= " AND especialidad_id=?"
            parametros.append(especialidad_id)
        c.execute(f"""SELECT id, nombre, apellidos FROM estudiantes
                     WHERE seccion_id IN ({marcadores}) AND estado='Activo'{filtro_especialidad}
                     ORDER BY apellidos""",
                  parametros)
        estudiantes= c.fetchall()
        conn.close()
        if not estudiantes:
            mostrar_mensaje("advertencia", "Sin estudiantes",
                           "No hay estudiantes activos para ese curso"
                           + (" y área técnica" if especialidad_id is not None else "") + ".", self)
            return
        curso_nombre= self.combo_curso_masivo.currentText().replace(" ", "_").replace("/", "-")
        if especialidad_id is not None:
            curso_nombre += "_" + self.combo_especialidad_masivo.currentText().replace(" ", "_").replace("/", "-")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Boletines Masivos",
                                              f"boletines_{curso_nombre}.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        institucion= _datos_institucion()
        #Todo el curso comparte el mismo Grado (y por lo tanto el mismo nivel educativo), así que basta resolver la
        #nota mínima con cualquiera de sus secciones — se usa la primera de la lista ya filtrada arriba.
        metodo, nota_minima = self._obtener_metodo_y_minima(seccion_id=secciones_del_curso[0])
        dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        periodo_txt= self.combo_periodo_masivo.currentText()
        #El loop de generación de boletines (queries DB por cada estudiante + dibujado en reportlab + cvs.save()) puede
        #tardar decenas de segundos con cursos grandes. Todo ello es I/O puro o cómputo sin tocar Qt, así que es seguro
        #moverlo a un WorkerHilo.
        if WorkerHilo is not None:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)
            btn= getattr(self, "btn_exportar_masivo", None)
            if btn:
                btn.setEnabled(False)

            def _tarea_masiva():
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfgen import canvas as _canvas
                _cvs= _canvas.Canvas(ruta, pagesize=letter)
                _ancho, _alto = letter
                for est in estudiantes:
                    estudiante_txt= f"{est['nombre']} {est['apellidos'] or ''}"
                    filas= self._construir_filas_boletin(
                        est["id"], periodo_id, metodo, nota_minima, dominicano)
                    if not filas:
                        continue
                    notas= [f["nota_final"] for f in filas]
                    promedio_general= sum(notas) / len(notas) if notas else 0
                    self._dibujar_boletin_pagina(_cvs, _ancho, _alto, institucion,
                                                 estudiante_txt, periodo_txt,
                                                 filas, promedio_general, metodo,
                                                 mostrar_rp= dominicano,
                                                 nota_minima= nota_minima)
                    _dibujar_pie_pagina(_cvs, _ancho, institucion)
                    _cvs.showPage()
                _cvs.save()
                return len(estudiantes)

            def _on_masivo_ok(total):
                from PySide6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
                if btn:
                    btn.setEnabled(True)
                registrar_auditoria(
                    "Calificaciones", "Exportó boletines masivos (PDF)",
                    self.main_window.usuario_actual,
                    f"Curso ID {curso_id} (secciones {secciones_del_curso})"
                    + (f" - Área Técnica ID {especialidad_id}" if especialidad_id is not None else "")
                    + f" - {periodo_txt} - {total} estudiantes")
                mostrar_mensaje("exito", "Boletines exportados",
                               f"Se generaron boletines para {total} estudiantes en:\n{ruta}", self)

            def _on_masivo_error(msg):
                from PySide6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
                if btn:
                    btn.setEnabled(True)
                mostrar_mensaje("error", "Error al exportar",
                               msg.split("\n")[0], self)

            self._hilo_boletin_masivo= WorkerHilo(_tarea_masiva)
            self._hilo_boletin_masivo.terminado.connect(_on_masivo_ok)
            self._hilo_boletin_masivo.error.connect(_on_masivo_error)
            self._hilo_boletin_masivo.start()
        else:
            #Fallback síncrono
            cvs= canvas.Canvas(ruta, pagesize=letter)
            ancho, alto = letter
            for est in estudiantes:
                estudiante_txt= f"{est['nombre']} {est['apellidos'] or ''}"
                filas= self._construir_filas_boletin(est["id"], periodo_id, metodo, nota_minima, dominicano)
                if not filas:
                    continue
                notas= [f["nota_final"] for f in filas]
                promedio_general= sum(notas) / len(notas) if notas else 0
                self._dibujar_boletin_pagina(cvs, ancho, alto, institucion, estudiante_txt, periodo_txt,
                                             filas, promedio_general, metodo, mostrar_rp=dominicano,
                                             nota_minima= nota_minima)
                _dibujar_pie_pagina(cvs, ancho, institucion)
                cvs.showPage()
            cvs.save()
            registrar_auditoria("Calificaciones", "Exportó boletines masivos (PDF)", self.main_window.usuario_actual,
                                f"Curso ID {curso_id} (secciones {secciones_del_curso})"
                                + (f" - Área Técnica ID {especialidad_id}" if especialidad_id is not None else "")
                                + f" - {periodo_txt} - {len(estudiantes)} estudiantes")
            mostrar_mensaje("exito", "Boletines exportados",
                           f"Se generaron boletines para {len(estudiantes)} estudiantes en:\n{ruta}", self)
    #---------------- HISTORIAL ACADÉMICO (multi-periodo) ----------------
    def _tab_historial(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        #Área Técnica/Carrera van PRIMERO, en su propia fila (mismo orden que en las demás pestañas): así se elige área
        #técnica/carrera antes que Curso/Sección, y la pestaña crece en ALTO -no en ANCHO- cuando ambos combos están
        #visibles a la vez (institución "Personalizado").
        self.lbl_filtro_especialidad_historial= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_historial= QComboBox()
        self.combo_filtro_especialidad_historial.setToolTip(
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.combo_filtro_especialidad_historial.currentIndexChanged.connect(self._cargar_estudiantes_historial)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_historial,
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.lbl_filtro_carrera_historial= QLabel("Carrera:")
        self.combo_filtro_carrera_historial= QComboBox()
        self.combo_filtro_carrera_historial.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        self.combo_filtro_carrera_historial.currentIndexChanged.connect(self._cargar_estudiantes_historial)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_historial,
            "Filtrar por carrera del estudiante (Universidad)")
        self.combo_curso_historial= QComboBox()
        self.combo_curso_historial.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso_corto(self.combo_curso_historial, self.combo_seccion_historial),
                      self._cargar_estudiantes_historial()))
        self.combo_seccion_historial= QComboBox()
        self.combo_seccion_historial.currentIndexChanged.connect(self._cargar_estudiantes_historial)

        self.dialogo_filtros_historial= self._crear_dialogo_filtros(
            "Filtros del Historial",
            "Curso y Sección acotan qué estudiante puedes elegir abajo. Área Técnica y Carrera son opcionales.",
            [(self.lbl_filtro_especialidad_historial, self.combo_filtro_especialidad_historial),
             (self.lbl_filtro_carrera_historial, self.combo_filtro_carrera_historial),
             ("Curso:", self.combo_curso_historial),
             ("Sección:", self.combo_seccion_historial)])
        fila_filtro_tecnico_historial= QHBoxLayout()
        fila_filtro_tecnico_historial.setSpacing(10)
        self.lbl_resumen_filtros_historial= QLabel("")
        self.lbl_resumen_filtros_historial.setWordWrap(True)
        fila_filtro_tecnico_historial.addWidget(self.lbl_resumen_filtros_historial, 1)
        self.btn_filtros_historial= self._crear_boton_filtros("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_historial.clicked.connect(lambda: self._abrir_dialogo_filtros(self.dialogo_filtros_historial))
        fila_filtro_tecnico_historial.addWidget(self.btn_filtros_historial)
        l.addLayout(fila_filtro_tecnico_historial)
        self.combo_curso_historial.currentIndexChanged.connect(self._actualizar_resumen_filtros_historial)
        self.combo_seccion_historial.currentIndexChanged.connect(self._actualizar_resumen_filtros_historial)
        self.combo_filtro_especialidad_historial.currentIndexChanged.connect(self._actualizar_resumen_filtros_historial)
        self.combo_filtro_carrera_historial.currentIndexChanged.connect(self._actualizar_resumen_filtros_historial)

        fila= QHBoxLayout()
        fila.setSpacing(10)
        self.combo_estudiante_historial= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante_historial, "Estudiante cuyo historial académico se muestra")
        fila.addWidget(QLabel("Estudiante:"))
        fila.addWidget(self.combo_estudiante_historial)
        ajustar_combo_ancho_seguro(self.combo_curso_historial, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_seccion_historial, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_filtro_especialidad_historial, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_filtro_carrera_historial, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_estudiante_historial, min_len=14)
        btn_generar= QPushButton("Generar Historial")
        btn_generar.setIcon(icono_emoji("🕒"))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.clicked.connect(self._generar_historial_click)
        fila.addWidget(btn_generar)
        fila.addStretch()
        l.addLayout(fila)
        l.addSpacing(8)
        #Búsqueda flexible: no distingue mayúsculas/minúsculas ni acentos (mismo diseño visual que la searchbar de
        #configuracion.py)
        self.in_buscar_historial= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_historial.setPlaceholderText(
            "Buscar por periodo, materia o estado (ignora tildes y mayúsculas)...")
        self.in_buscar_historial.texto_buscado.connect(self._aplicar_busqueda_historial)
        l.addWidget(self.in_buscar_historial)
        l.addSpacing(6)


        #Tabla estilo Omega POS (historial)
        self.tabla_historial= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_historial)
        self.tabla_historial.setHorizontalHeaderLabels(["Periodo", "Materia", "Nota Final", "Estado"])
        header= self.tabla_historial.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #"Materia" ya es Stretch; con StretchLastSection activo, "Estado" (última columna) competiría por el mismo
        #espacio sobrante.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  #"Materia"
        self.tabla_historial.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_historial.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_historial.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_historial.setAlternatingRowColors(True)
        self.tabla_historial.setWordWrap(True)
        self.tabla_historial.setMinimumHeight(340)
        self.tabla_historial.verticalHeader().setVisible(False)
        l.addWidget(self.tabla_historial, 1)
        self.paginacion_historial= ControlPaginacion(tamano_inicial=25)
        self.paginacion_historial.cambio.connect(self._repaginar_historial)
        l.addWidget(self.paginacion_historial)
        l.addSpacing(10)

        agregar_boton_pantalla_completa(
            None,
            [self.in_buscar_historial, self.tabla_historial, self.paginacion_historial],
            titulo= "Historial Académico", parent=self)

        self.lbl_promedio_acumulado= QLabel("Promedio Acumulado General: --")
        self.lbl_promedio_acumulado.setObjectName("DescModulo")
        l.addWidget(self.lbl_promedio_acumulado)
        panel_tendencia= _crear_panel_dashboard()
        lay_tendencia= panel_tendencia.layout()
        lbl_tendencia= QLabel("Tendencia por periodo:")
        lbl_tendencia.setObjectName("DescModulo")
        lay_tendencia.addWidget(lbl_tendencia)
        self.sparkline_historial= LineaTendencia()
        lay_tendencia.addWidget(self.sparkline_historial, 1)
        l.addWidget(panel_tendencia)
        fila_acciones_hist= QHBoxLayout()
        btn_pdf= QPushButton("Exportar Historial Académico a PDF")
        btn_pdf.setIcon(icono_emoji("\uE002"))
        btn_pdf.setIconSize(_QSize_emoji(16, 16))
        btn_pdf.setObjectName("BtnAccionEditar")
        btn_pdf.clicked.connect(self._exportar_historial_pdf)
        fila_acciones_hist.addWidget(btn_pdf)
        btn_detalle_hist= agregar_boton_detalle(fila_acciones_hist, self.tabla_historial, self,
                                                  titulo= "Detalle del Historial")
        self.tabla_historial.doubleClicked.connect(lambda *_: btn_detalle_hist.click())
        fila_acciones_hist.addStretch()
        l.addLayout(fila_acciones_hist)
        l.addStretch(1)
        return w
    def _cargar_estudiantes_historial(self):
        self.combo_estudiante_historial.clear()
        self.combo_estudiante_historial.addItem("Elige estudiante", None)
        seccion_id= self.combo_seccion_historial.currentData()
        permitidas= self._permitidas_secciones()
        especialidad_id= self.combo_filtro_especialidad_historial.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_filtro_carrera_historial.currentData() if self._es_universidad() else None
        for f in self._estudiantes_todos():
            if seccion_id is not None and f["seccion_id"] != seccion_id:
                continue
            if permitidas is not None and f["seccion_id"] not in permitidas:
                continue
            if especialidad_id == 0 and f["especialidad_id"] is not None:
                continue
            elif especialidad_id not in (None, 0) and f["especialidad_id"] != especialidad_id:
                continue
            if carrera_id == 0 and f["carrera_id"] is not None:
                continue
            elif carrera_id not in (None, 0) and f["carrera_id"] != carrera_id:
                continue
            self.combo_estudiante_historial.addItem(f"{f['nombre']} {f['apellidos'] or ''}", f["id"])
        _actualizar_estado_combo_estudiante(self.combo_curso_historial, self.combo_seccion_historial,
                                             self.combo_estudiante_historial)
        self._actualizar_resumen_filtros_historial()

    def _actualizar_resumen_filtros_historial(self):
        if not hasattr(self, "lbl_resumen_filtros_historial"):
            return
        self.lbl_resumen_filtros_historial.setText(self._resumen_filtros_texto([
            ("Curso", self.combo_curso_historial), ("Sección", self.combo_seccion_historial),
            ("Área Técnica", self.combo_filtro_especialidad_historial),
            ("Carrera", self.combo_filtro_carrera_historial),
        ]))

    def _cargar_especialidad_carrera_historial(self):
        """Igual que en Banco de Tareas: los combos de Área Técnica y Carrera de
        'Historial Académico' solo se muestran/pueblan si la institución tiene
        ese módulo activo."""
        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_historial.setVisible(es_poli)
        self.combo_filtro_especialidad_historial.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_historial.currentData()
            self.combo_filtro_especialidad_historial.blockSignals(True)
            self.combo_filtro_especialidad_historial.clear()
            self.combo_filtro_especialidad_historial.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_especialidad_historial.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_especialidad_historial, "No Área Técnica")
            idx= self.combo_filtro_especialidad_historial.findData(actual)
            self.combo_filtro_especialidad_historial.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_historial.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_historial.setVisible(es_uni)
        self.combo_filtro_carrera_historial.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_historial.currentData()
            self.combo_filtro_carrera_historial.blockSignals(True)
            self.combo_filtro_carrera_historial.clear()
            self.combo_filtro_carrera_historial.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for f in c.fetchall():
                self.combo_filtro_carrera_historial.addItem(f["nombre"], f["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_carrera_historial, "No Carrera")
            idx= self.combo_filtro_carrera_historial.findData(actual)
            self.combo_filtro_carrera_historial.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_historial.blockSignals(False)
    def _historial_datos(self, estudiante_id, metodo):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre, orden FROM periodos ORDER BY orden")
        periodos= c.fetchall()
        filas= []
        promedios_periodo= []
        for periodo in periodos:
            notas_por_materia= self._notas_por_materia(estudiante_id, periodo["id"], metodo)
            if not notas_por_materia:
                continue
            for materia, nota_final in notas_por_materia.items():
                filas.append((periodo["nombre"], materia, nota_final))
            promedio= sum(notas_por_materia.values()) / len(notas_por_materia)
            promedios_periodo.append(promedio)
        conn.close()
        return filas, promedios_periodo
    def _validar_alcance_tecnico_historial(self):
        """Área Técnica/Carrera son OBLIGATORIOS antes de generar un historial si
        la institución es puramente Politécnico o puramente Universidad (o
        "Personalizado" con solo uno de los dos módulos activo). Solo se llama
        desde el botón "Generar Historial" -no desde la paginación- para no
        interrumpir con un aviso cada vez que se repagina la tabla."""
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        if self._es_politecnico() and not ambos_activos and self.combo_filtro_especialidad_historial.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica antes de "
                           "generar el historial.", self)
            return False
        if self._es_universidad() and not ambos_activos and self.combo_filtro_carrera_historial.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera antes de "
                           "generar el historial.", self)
            return False
        return True

    def _generar_historial_click(self):
        if not self._validar_alcance_tecnico_historial():
            return
        self._generar_historial()

    def _generar_historial(self):
        estudiante_id= self.combo_estudiante_historial.currentData()
        if estudiante_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona un estudiante.", self)
            return
        metodo, nota_minima = self._obtener_metodo_y_minima(estudiante_id=estudiante_id)
        filas, promedios_periodo = self._historial_datos(estudiante_id, metodo)
        self._historial_filas= filas
        self._historial_nota_minima= nota_minima
        acumulado= sum(promedios_periodo) / len(promedios_periodo) if promedios_periodo else 0
        texto= f"Promedio Acumulado General: {acumulado:.2f}  ({len(promedios_periodo)} periodo(s) con notas)"
        if es_sistema_dominicano(_sistema_calificacion_actual()) and promedios_periodo:
            condicion= "PROMOVIDO" if acumulado >= nota_minima else "RECUPERACIÓN PEDAGÓGICA"
            texto += f"  |  Condición: {condicion}"
        self.lbl_promedio_acumulado.setText(texto)
        if hasattr(self, "sparkline_historial"):
            self.sparkline_historial.actualizar(promedios_periodo, umbral=nota_minima)
        self.paginacion_historial.establecer_total(len(filas))
        self._repaginar_historial()
    def _repaginar_historial(self):
        filas= getattr(self, "_historial_filas", [])
        nota_minima= getattr(self, "_historial_nota_minima", 70)
        inicio, fin = self.paginacion_historial.rango_actual()
        pagina= filas[inicio:fin]
        self.tabla_historial.setRowCount(len(pagina))
        with tabla_pausada(self.tabla_historial):
            for i, (periodo_nombre, materia, nota_final) in enumerate(pagina):
                self.tabla_historial.setItem(i, 0, QTableWidgetItem(periodo_nombre))
                self.tabla_historial.setItem(i, 1, QTableWidgetItem(materia))
                self.tabla_historial.setItem(i, 2, QTableWidgetItem(f"{nota_final:.2f}"))
                estado= "Aprobado" if nota_final >= nota_minima else "Reprobado"
                self.tabla_historial.setItem(i, 3, QTableWidgetItem(estado))
        if hasattr(self, "in_buscar_historial"):
            self._aplicar_busqueda_historial(self.in_buscar_historial.text())

    def _aplicar_busqueda_historial(self, texto=""):
        """Filtra las filas ya cargadas por periodo, materia o estado, sin
        exigir tildes ni mayúsculas/minúsculas exactas."""
        if not hasattr(self, "tabla_historial"):
            return
        consulta= _normalizar_busqueda(texto)
        for fila in range(self.tabla_historial.rowCount()):
            if not consulta:
                self.tabla_historial.setRowHidden(fila, False)
                continue
            partes= []
            for col in (0, 1, 3):  #Periodo, Materia, Estado
                item= self.tabla_historial.item(fila, col)
                if item:
                    partes.append(item.text())
            self.tabla_historial.setRowHidden(fila, consulta not in _normalizar_busqueda(" ".join(partes)))
    def _exportar_historial_pdf(self):
        if self.tabla_historial.rowCount() == 0:
            mostrar_mensaje("advertencia", "Sin datos", "Genera el historial antes de exportar.", self)
            return
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                           "Instala 'reportlab' (pip install reportlab) para exportar en PDF.", self)
            return
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Historial Académico", "historial_academico.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        institucion= _datos_institucion()
        estudiante_txt= self.combo_estudiante_historial.currentText()
        cvs= canvas.Canvas(ruta, pagesize=letter)
        ancho, alto = letter
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, "Historial Académico Acumulado")
        cvs.setFont("Helvetica", 11)
        cvs.drawString(60, y, f"Estudiante: {estudiante_txt}")
        y -= 16
        cvs.drawString(60, y, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")
        y -= 30
        cvs.setFont("Helvetica-Bold", 10)
        cvs.drawString(60, y, "Periodo")
        cvs.drawString(220, y, "Materia")
        cvs.drawString(420, y, "Nota Final")
        cvs.drawString(500, y, "Estado")
        y -= 8
        cvs.line(60, y, ancho - 60, y)
        y -= 16
        cvs.setFont("Helvetica", 9)
        for fila in range(self.tabla_historial.rowCount()):
            periodo= self.tabla_historial.item(fila, 0).text()
            materia= self.tabla_historial.item(fila, 1).text()
            nota= self.tabla_historial.item(fila, 2).text()
            estado= self.tabla_historial.item(fila, 3).text()
            cvs.drawString(60, y, periodo)
            cvs.drawString(220, y, materia)
            cvs.drawString(420, y, nota)
            cvs.drawString(500, y, estado)
            y -= 15
            if y < 110:
                _dibujar_pie_pagina(cvs, ancho, institucion, incluir_firma=False)
                cvs.showPage()
                y= alto - 60
        y -= 10
        cvs.setFont("Helvetica-Bold", 11)
        cvs.drawString(60, y, self.lbl_promedio_acumulado.text())
        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.save()
        registrar_auditoria("Calificaciones", "Exportó historial académico PDF", self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Historial exportado", f"Historial guardado en:\n{ruta}", self)

    #---------------- DESEMPEÑO INDIVIDUAL (Sistema Dominicano · Competencias Fundamentales) ----------------
    def _tab_desempeno_individual(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(14)
        aviso= QLabel("Calificación cualitativa por Competencias Fundamentales.")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)
        self.lbl_filtro_especialidad_desempeno, self.combo_filtro_especialidad_desempeno,\
            self.lbl_filtro_carrera_desempeno, self.combo_filtro_carrera_desempeno =\
            self._crear_combos_filtro_tecnico(self._cargar_estudiantes_desempeno)
        self.combo_curso_desempeno= QComboBox()
        self.combo_curso_desempeno.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso_corto(self.combo_curso_desempeno, self.combo_seccion_desempeno),
                      self._cargar_estudiantes_desempeno()))
        self.combo_seccion_desempeno= QComboBox()
        self.combo_seccion_desempeno.currentIndexChanged.connect(self._cargar_estudiantes_desempeno)
        self._reemplazar_por_filtros(l, "desempeno", "Filtros de Desempeño Individual",
            [(self.lbl_filtro_especialidad_desempeno, self.combo_filtro_especialidad_desempeno),
             (self.lbl_filtro_carrera_desempeno, self.combo_filtro_carrera_desempeno),
             ("Curso:", self.combo_curso_desempeno),
             ("Sección:", self.combo_seccion_desempeno)])
        self._conectar_resumen_filtros("desempeno", [
            ("Curso", self.combo_curso_desempeno), ("Sección", self.combo_seccion_desempeno),
            ("Área Técnica", self.combo_filtro_especialidad_desempeno),
            ("Carrera", self.combo_filtro_carrera_desempeno)])
        fila= QHBoxLayout()
        fila.setSpacing(10)
        self.combo_estudiante_desempeno= QComboBox()
        self.combo_estudiante_desempeno.currentIndexChanged.connect(self._cargar_desempeno)
        conectar_tooltip_seleccion(self.combo_estudiante_desempeno, "Estudiante cuyo desempeño individual se muestra")
        fila.addWidget(QLabel("Estudiante:"))
        fila.addWidget(self.combo_estudiante_desempeno)
        self.combo_periodo_desempeno= QComboBox()
        self.combo_periodo_desempeno.currentIndexChanged.connect(self._cargar_desempeno)
        conectar_tooltip_seleccion(self.combo_periodo_desempeno, "Periodo académico del desempeño individual")
        fila.addWidget(QLabel("Periodo:"))
        fila.addWidget(self.combo_periodo_desempeno)
        ajustar_combo_ancho_seguro(self.combo_curso_desempeno, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_seccion_desempeno, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_estudiante_desempeno, min_len=13)
        ajustar_combo_ancho_seguro(self.combo_periodo_desempeno, min_len=6)
        l.addLayout(fila)
        l.addSpacing(8)

        self.tabla_desempeno= QTableWidget(len(COMPETENCIAS_FUNDAMENTALES_RD), 3)
        aplicar_estructura_tabla(self.tabla_desempeno)
        self.tabla_desempeno.setHorizontalHeaderLabels(["Competencia Fundamental", "Nivel de Desempeño", "Observación"])
        header= self.tabla_desempeno.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tabla_desempeno.setColumnWidth(1, 190)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_desempeno.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_desempeno.setAlternatingRowColors(True)
        self.tabla_desempeno.verticalHeader().setVisible(False)
        self.tabla_desempeno.setMinimumHeight(340)
        self._combos_nivel_desempeno= []
        self._campos_observacion_desempeno= []
        for i, competencia in enumerate(COMPETENCIAS_FUNDAMENTALES_RD):
            self.tabla_desempeno.setItem(i, 0, QTableWidgetItem(competencia))
            self.tabla_desempeno.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
            combo_nivel= QComboBox()
            combo_nivel.addItems(NIVELES_DESEMPENO_RD)
            combo_nivel.setMinimumHeight(30)
            conectar_tooltip_seleccion(combo_nivel, f"Nivel de desempeño en '{competencia}'")
            combo_nivel.currentTextChanged.connect(
                lambda texto, cb=combo_nivel: self._colorear_nivel_desempeno(cb, texto))
            self._colorear_nivel_desempeno(combo_nivel, combo_nivel.currentText())
            combo_nivel.currentTextChanged.connect(self._actualizar_resumen_desempeno)
            self.tabla_desempeno.setCellWidget(i, 1, combo_nivel)
            self._combos_nivel_desempeno.append(combo_nivel)
            in_obs= QLineEdit()
            limitar_campo_texto(in_obs, 300)
            in_obs.setPlaceholderText("Observación (opcional)")
            in_obs.setMinimumHeight(30)
            self.tabla_desempeno.setCellWidget(i, 2, in_obs)
            self._campos_observacion_desempeno.append(in_obs)
            self.tabla_desempeno.setRowHeight(i, 40)
        l.addWidget(self.tabla_desempeno, 1)
        l.addSpacing(10)

        self.lbl_resumen_desempeno= QLabel("")
        self.lbl_resumen_desempeno.setObjectName("DescModulo")
        panel_resumen_desempeno= _crear_panel_dashboard()
        fila_resumen= panel_resumen_desempeno.layout()
        fila_resumen.setSpacing(14)
        self.anillo_desempeno= AnilloProgreso("#10B981")
        fila_resumen.addWidget(self.anillo_desempeno)
        self.dona_desempeno= GraficoDona(diametro=128, grosor=16)
        col_dona_desempeno= QVBoxLayout()
        col_dona_desempeno.setSpacing(2)
        col_dona_desempeno.addWidget(self.dona_desempeno, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_dona_desempeno= QLabel("")
        self.lbl_dona_desempeno.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_dona_desempeno.setObjectName("DescModulo")
        col_dona_desempeno.addWidget(self.lbl_dona_desempeno)
        fila_resumen.addLayout(col_dona_desempeno)
        self.tarjeta_resumen_desempeno= TarjetaAlerta("📝", "Pendientes por evaluar", "#F59E0B")
        self._tarjetas_alerta.append(self.tarjeta_resumen_desempeno)
        fila_resumen.addWidget(self.tarjeta_resumen_desempeno)
        columna_resumen= QVBoxLayout()
        columna_resumen.addWidget(self.lbl_resumen_desempeno)
        columna_resumen.addStretch()
        fila_resumen.addLayout(columna_resumen, 1)
        l.addWidget(panel_resumen_desempeno)
        self._actualizar_resumen_desempeno()

        leyenda= QLabel(
            "Escala: Destacado 89-100 · Logrado 77-88 · En Proceso 65-76 · Insuficiente < 65. "
            "'Sin Evaluar (NE)' significa que ese renglón aún no se ha calificado.")
        leyenda.setWordWrap(True)
        leyenda.setObjectName("DescModulo")
        l.addWidget(leyenda)

        btn_guardar= QPushButton("Guardar Desempeño Individual")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_desempeno)
        l.addWidget(btn_guardar)
        l.addStretch(1)
        return w

    def _colorear_nivel_desempeno(self, combo, nivel):
        """Da un color distintivo a cada nivel para que las filas dejen de verse todas
        iguales (antes todas mostraban 'Satisfactorio' sin ninguna señal visual de que
        aún no se había evaluado nada)."""
        color= COLORES_NIVEL_DESEMPENO_RD.get(nivel, "#6B7280")
        combo.setStyleSheet(
            f"QComboBox {{ font-weight: 600; color: {color}; border: 1px solid {color}55; "
            f"border-radius: 6px; padding: 2px 6px; }}")

    def _actualizar_resumen_desempeno(self, *_):
        if not hasattr(self, "_combos_nivel_desempeno") or not hasattr(self, "lbl_resumen_desempeno"):
            return
        estudiante_id= self.combo_estudiante_desempeno.currentData()\
            if hasattr(self, "combo_estudiante_desempeno") else None
        if estudiante_id is None:
            #Todavía no hay un estudiante real cargado (p. ej. la sección no tiene estudiantes activos, o el usuario aún no
            #eligió ninguno). No hay nada que evaluar todavía, así que NO mostramos ninguna alerta — antes esto se
            #disparaba con el estado inicial vacío de los combos y marcaba 'pendiente' aunque no hubiera datos reales.
            if hasattr(self, "tarjeta_resumen_desempeno"):
                self.tarjeta_resumen_desempeno.actualizar("—", alerta=False, color="#6B7280")
            if hasattr(self, "anillo_desempeno"):
                self.anillo_desempeno.actualizar(0.0, texto="—", color="#6B7280")
            if hasattr(self, "dona_desempeno"):
                self.dona_desempeno.actualizar([], total_texto="—", etiqueta="competencias")
            if hasattr(self, "lbl_dona_desempeno"):
                self.lbl_dona_desempeno.setText("competencias")
            if hasattr(self, "idx_tab_desempeno"):
                self.tabs.setTabIcon(self.idx_tab_desempeno, icono_emoji(EMOJI_DESEMPENO_INDIVIDUAL))
            self.lbl_resumen_desempeno.setText(
                "Selecciona una sección con estudiantes activos y un estudiante para ver su desempeño.")
            return
        total= len(self._combos_nivel_desempeno)
        evaluadas= sum(1 for c in self._combos_nivel_desempeno if c.currentText() != NIVEL_SIN_EVALUAR_RD)
        pendientes= total - evaluadas
        if hasattr(self, "tarjeta_resumen_desempeno"):
            self.tarjeta_resumen_desempeno.actualizar(pendientes, alerta=pendientes > 0)
        if hasattr(self, "anillo_desempeno"):
            fraccion= (evaluadas / total) if total else 0
            color= "#10B981" if pendientes == 0 else "#F59E0B"
            self.anillo_desempeno.actualizar(fraccion, color=color)
        if hasattr(self, "dona_desempeno"):
            conteo= {}
            for c in self._combos_nivel_desempeno:
                nivel= c.currentText()
                conteo[nivel]= conteo.get(nivel, 0) + 1
            self.dona_desempeno.actualizar(
                [(nivel, cant, COLORES_NIVEL_DESEMPENO_RD.get(nivel, "#94A3B8")) for nivel, cant in conteo.items()],
                total_texto= str(total), etiqueta="competencias")
            if hasattr(self, "lbl_dona_desempeno"):
                self.lbl_dona_desempeno.setText("competencias")
        if hasattr(self, "idx_tab_desempeno"):
            self.tabs.setTabIcon(
                self.idx_tab_desempeno,
                _icono_punto("#F59E0B", base=EMOJI_DESEMPENO_INDIVIDUAL) if pendientes > 0
                else icono_emoji(EMOJI_DESEMPENO_INDIVIDUAL))
        if evaluadas == total:
            self.lbl_resumen_desempeno.setText(f"✅ Las {total} competencias fundamentales están evaluadas.")
        else:
            self.lbl_resumen_desempeno.setText(
                f"⚠ {evaluadas} de {total} competencias evaluadas · faltan {pendientes} por registrar.")

    def _cargar_secciones_desempeno(self):
        self._poblar_combo_curso_corto(self.combo_curso_desempeno)
        self._filtrar_seccion_por_curso_corto(self.combo_curso_desempeno, self.combo_seccion_desempeno)

    def _cargar_estudiantes_desempeno(self):
        self.combo_estudiante_desempeno.clear()
        self.combo_estudiante_desempeno.addItem("Elige estudiante", None)
        seccion_id= self.combo_seccion_desempeno.currentData()
        permitidas= self._permitidas_secciones()
        candidatos= self._filtrar_por_tecnico(self._estudiantes_activos(),
            self.combo_filtro_especialidad_desempeno, self.combo_filtro_carrera_desempeno)
        for f in candidatos:
            if seccion_id is not None and f["seccion_id"] != seccion_id:
                continue
            if permitidas is not None and f["seccion_id"] not in permitidas:
                continue
            self.combo_estudiante_desempeno.addItem(f"{f['nombre']} {f['apellidos'] or ''}", f["id"])
        _actualizar_estado_combo_estudiante(self.combo_curso_desempeno, self.combo_seccion_desempeno,
                                             self.combo_estudiante_desempeno)

    def _cargar_periodos_desempeno(self):
        self.combo_periodo_desempeno.clear()
        for id_periodo, nombre in self._periodos_lista():
            self.combo_periodo_desempeno.addItem(nombre, id_periodo)

    def _cargar_desempeno(self):
        if not hasattr(self, "_combos_nivel_desempeno"):
            return
        estudiante_id= self.combo_estudiante_desempeno.currentData()
        periodo_id= self.combo_periodo_desempeno.currentData()
        for combo in self._combos_nivel_desempeno:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)  #"Sin Evaluar (NE)" por defecto: nunca asumimos un nivel logrado
            combo.blockSignals(False)
            self._colorear_nivel_desempeno(combo, combo.currentText())
        for campo in self._campos_observacion_desempeno:
            campo.clear()
        if estudiante_id is None or periodo_id is None:
            self._actualizar_resumen_desempeno()
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT competencia, nivel, observacion FROM desempeno_individual
                     WHERE estudiante_id=? AND periodo_id=?""", (estudiante_id, periodo_id))
        guardados= {f["competencia"]: (f["nivel"], f["observacion"]) for f in c.fetchall()}
        conn.close()
        for i, competencia in enumerate(COMPETENCIAS_FUNDAMENTALES_RD):
            if competencia in guardados:
                nivel, observacion = guardados[competencia]
                idx= self._combos_nivel_desempeno[i].findText(nivel or "")
                if idx >= 0:
                    self._combos_nivel_desempeno[i].blockSignals(True)
                    self._combos_nivel_desempeno[i].setCurrentIndex(idx)
                    self._combos_nivel_desempeno[i].blockSignals(False)
                    self._colorear_nivel_desempeno(self._combos_nivel_desempeno[i], nivel or "")
                self._campos_observacion_desempeno[i].setText(observacion or "")
        self._actualizar_resumen_desempeno()

    def _guardar_desempeno(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar desempeño individual.", self)
            return
        estudiante_id= self.combo_estudiante_desempeno.currentData()
        periodo_id= self.combo_periodo_desempeno.currentData()
        if estudiante_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona estudiante y periodo.", self)
            return
        if self._periodo_esta_bloqueado(periodo_id) and not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Periodo cerrado",
                             "Este periodo fue cerrado y ya no admite cambios de Desempeño Individual.", self)
            return
        pendientes= [COMPETENCIAS_FUNDAMENTALES_RD[i] for i, combo in enumerate(self._combos_nivel_desempeno)
                      if combo.currentText() == NIVEL_SIN_EVALUAR_RD]
        if pendientes:
            resp= mostrar_mensaje("pregunta", "Competencias sin evaluar",
                "Todavía quedan " + str(len(pendientes)) + " competencia(s) marcadas como 'Sin Evaluar (NE)':\n"
                "• " + "\n• ".join(pendientes) + "\n\n¿Guardar de todas formas?", self)
            if resp != QMessageBox.StandardButton.Yes:
                return
        ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn= obtener_conexion()
        c= conn.cursor()
        for i, competencia in enumerate(COMPETENCIAS_FUNDAMENTALES_RD):
            nivel= self._combos_nivel_desempeno[i].currentText()
            observacion= self._campos_observacion_desempeno[i].text().strip()
            c.execute("""INSERT INTO desempeno_individual
                         (estudiante_id, periodo_id, competencia, nivel, observacion, actualizado)
                         VALUES (?,?,?,?,?,?)
                         ON CONFLICT(estudiante_id, periodo_id, competencia) DO UPDATE SET
                            nivel= excluded.nivel, observacion=excluded.observacion, actualizado=excluded.actualizado""",
                      (estudiante_id, periodo_id, competencia, nivel, observacion, ahora))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", "Registró Desempeño Individual", self.main_window.usuario_actual,
                            f"Estudiante ID {estudiante_id} - Periodo ID {periodo_id}")
        mostrar_mensaje("exito", "Guardado", "El desempeño individual se guardó correctamente.", self)

    #---------------- SEGUIMIENTO RD (incompletos / RP / desempeño pendiente) ----------------
    ESTADOS_SEGUIMIENTO= ["Todos", "Sin Calificar", "Requiere RP", "RP Pendiente", "RP Superada",
                           "Competencia Alcanzada"]
    COLORES_ESTADO_SEGUIMIENTO= {
        "Sin Calificar": "#6B7280", "Requiere RP": "#EF4444", "RP Pendiente": "#F59E0B",
        "RP Superada": "#3B82F6", "Competencia Alcanzada": "#10B981",
    }

    def _tab_seguimiento_rd(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        aviso= QLabel("Identifica de un vistazo a quién le falta calificar, Recuperación Pedagógica "
                       "o Desempeño Individual.")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)

        self.lbl_filtro_especialidad_seguimiento, self.combo_filtro_especialidad_seguimiento,\
            self.lbl_filtro_carrera_seguimiento, self.combo_filtro_carrera_seguimiento =\
            self._crear_combos_filtro_tecnico(self._generar_seguimiento)

        self.combo_filtro_nivel_seguimiento= QComboBox()
        self.combo_filtro_nivel_seguimiento.currentIndexChanged.connect(self._nivel_seguimiento_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel_seguimiento, "Filtrar por nivel educativo (se combina con Curso/Sección)")

        self.combo_curso_seguimiento= QComboBox()
        self.combo_curso_seguimiento.currentIndexChanged.connect(self._filtrar_seccion_seguimiento_por_curso)
        self.combo_seccion_seguimiento= QComboBox()
        self.combo_filtro_estado_seguimiento= QComboBox()
        self.combo_filtro_estado_seguimiento.addItems(self.ESTADOS_SEGUIMIENTO)
        conectar_tooltip_seleccion(self.combo_filtro_estado_seguimiento, "Filtrar por estado del plan de seguimiento")

        self._reemplazar_por_filtros(l, "seguimiento", "Filtros de Seguimiento",
            [(self.lbl_filtro_especialidad_seguimiento, self.combo_filtro_especialidad_seguimiento),
             (self.lbl_filtro_carrera_seguimiento, self.combo_filtro_carrera_seguimiento),
             ("Nivel Educativo:", self.combo_filtro_nivel_seguimiento),
             ("Curso:", self.combo_curso_seguimiento),
             ("Sección:", self.combo_seccion_seguimiento),
             ("Ver solo:", self.combo_filtro_estado_seguimiento)],
            subtitulo= "Nivel, Curso y Sección acotan a quién se le da seguimiento. Área Técnica, Carrera "
                       "y 'Ver solo' son opcionales.")
        self._conectar_resumen_filtros("seguimiento", [
            ("Nivel", self.combo_filtro_nivel_seguimiento),
            ("Curso", self.combo_curso_seguimiento), ("Sección", self.combo_seccion_seguimiento),
            ("Área Técnica", self.combo_filtro_especialidad_seguimiento),
            ("Carrera", self.combo_filtro_carrera_seguimiento),
            ("Ver solo", self.combo_filtro_estado_seguimiento)])

        fila= QHBoxLayout()
        self.combo_periodo_seguimiento= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo_seguimiento, "Periodo académico del seguimiento")
        fila.addWidget(QLabel("Periodo:"))
        fila.addWidget(self.combo_periodo_seguimiento)
        ajustar_combo_ancho_seguro(self.combo_curso_seguimiento, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_seccion_seguimiento, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_periodo_seguimiento, min_len=6)
        ajustar_combo_ancho_seguro(self.combo_filtro_estado_seguimiento, min_len=10)
        btn_generar= QPushButton("Generar Seguimiento")
        btn_generar.setIcon(icono_emoji(EMOJI_SEGUIMIENTO_RP))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAjustar")
        btn_generar.clicked.connect(self._generar_seguimiento)
        fila.addWidget(btn_generar)
        fila.addStretch()
        l.addLayout(fila)

        #--- Tarjetas de alerta dinámicas: un vistazo instantáneo de la sección ---
        self.tarjetas_seguimiento= {}
        panel_tarjetas_seguimiento= _crear_panel_dashboard()
        fila_tarjetas= panel_tarjetas_seguimiento.layout()
        fila_tarjetas.setSpacing(10)
        iconos_estado= {"Sin Calificar": "📝", "Requiere RP": "🔁", "RP Pendiente": "🕒",
                        "RP Superada": "🏆", "Competencia Alcanzada": "🎯"}
        for estado in self.ESTADOS_SEGUIMIENTO[1:]:  #sin "Todos"
            tarjeta= TarjetaAlerta(iconos_estado.get(estado, ""), estado,
                                     self.COLORES_ESTADO_SEGUIMIENTO[estado])
            self.tarjetas_seguimiento[estado]= tarjeta
            self._tarjetas_alerta.append(tarjeta)
            fila_tarjetas.addWidget(tarjeta)
        self.tarjeta_desempeno_incompleto= TarjetaAlerta("⚠", "Desempeño Incompleto", "#F59E0B")
        self._tarjetas_alerta.append(self.tarjeta_desempeno_incompleto)
        fila_tarjetas.addWidget(self.tarjeta_desempeno_incompleto)
        fila_tarjetas.addStretch()

        #El panel completo (6 tarjetas) pide bastante más ancho mínimo que las demás pestañas de este módulo. Si se
        #agrega directo al layout vertical de la pestaña, ese ancho mínimo se propaga hacia arriba por todo el árbol de
        #widgets — incluido el QScrollArea raíz del módulo, que tiene el scroll horizontal apagado — y termina forzando
        #a la ventana principal a crecer/recalcular su geometría apenas se construye esta pestaña (que es perezosa:
        #solo se arma al entrar a ella por primera vez). Eso es lo que "rompía" la resolución del módulo entero al ir a
        #Seguimiento. Envolverlo en su propio QScrollArea horizontal aísla ese ancho mínimo: si no entra, aparece una
        #barra de scroll aquí mismo en vez de forzar a toda la ventana.
        scroll_tarjetas= QScrollArea()
        scroll_tarjetas.setWidgetResizable(True)
        scroll_tarjetas.setFrameShape(QFrame.Shape.NoFrame)
        scroll_tarjetas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_tarjetas.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_tarjetas.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        scroll_tarjetas.setWidget(panel_tarjetas_seguimiento)
        scroll_tarjetas.setFixedHeight(panel_tarjetas_seguimiento.sizeHint().height() + 8)
        l.addWidget(scroll_tarjetas)

        #--- Barra proporcional: la 'forma' completa de la sección de un vistazo ---
        self.barra_seguimiento= BarraSegmentada()
        l.addWidget(self.barra_seguimiento)

        self.lbl_resumen_seguimiento= QLabel("")
        self.lbl_resumen_seguimiento.setWordWrap(True)
        self.lbl_resumen_seguimiento.setObjectName("DescModulo")
        l.addWidget(self.lbl_resumen_seguimiento)
        l.addSpacing(8)

        #--- Búsqueda flexible: no distingue mayúsculas/minúsculas ni acentos --- (mismo diseño visual que la searchbar
        #de configuracion.py)
        self.in_buscar_seguimiento= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_seguimiento.setPlaceholderText("Buscar estudiante o materia (ignora tildes y mayúsculas)...")
        self.in_buscar_seguimiento.texto_buscado.connect(self._aplicar_busqueda_seguimiento)
        l.addWidget(self.in_buscar_seguimiento)
        l.addSpacing(6)


        self.tabla_seguimiento= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_seguimiento)
        self.tabla_seguimiento.setHorizontalHeaderLabels(
            ["No.", "Estudiante", "Materia", "Nota Final", "Estado", "Nota RP"])
        header= self.tabla_seguimiento.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #"Estudiante" ya es Stretch; con StretchLastSection activo, "Nota RP" (última columna) competiría por el mismo
        #espacio sobrante.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_seguimiento.setColumnWidth(0, 48)
        self.tabla_seguimiento.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_seguimiento.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_seguimiento.setAlternatingRowColors(True)
        self.tabla_seguimiento.verticalHeader().setVisible(False)
        self.tabla_seguimiento.setMinimumHeight(220)
        l.addWidget(self.tabla_seguimiento, 1)

        self.paginacion_seguimiento= ControlPaginacion(tamano_inicial=25)
        self.paginacion_seguimiento.cambio.connect(self._repaginar_seguimiento)
        l.addWidget(self.paginacion_seguimiento)
        l.addSpacing(14)

        agregar_boton_pantalla_completa(
            None,
            [self.in_buscar_seguimiento, self.tabla_seguimiento, self.paginacion_seguimiento],
            titulo= "Seguimiento", parent=self)


        lbl_incompleto= QLabel("Desempeño Individual (Competencias Fundamentales) incompleto en este periodo:")
        lbl_incompleto.setObjectName("DescModulo")
        l.addWidget(lbl_incompleto)
        self.tabla_desempeno_incompleto= QTableWidget(0, 2)
        aplicar_estructura_tabla(self.tabla_desempeno_incompleto)
        self.tabla_desempeno_incompleto.setHorizontalHeaderLabels(
            ["Estudiante", "Competencias evaluadas"])
        header2= self.tabla_desempeno_incompleto.horizontalHeader()
        #"Estudiante" ya es Stretch; con StretchLastSection activo, "Competencias evaluadas" (última columna)
        #competiría por el mismo espacio sobrante.
        header2.setStretchLastSection(False)
        header2.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_desempeno_incompleto.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_desempeno_incompleto.setAlternatingRowColors(True)
        self.tabla_desempeno_incompleto.verticalHeader().setVisible(False)
        self.tabla_desempeno_incompleto.setMinimumHeight(130)
        l.addWidget(self.tabla_desempeno_incompleto, 1)
        l.addStretch(1)

        return w

    def _cargar_secciones_seguimiento(self):
        poblar_combo_nivel_educativo(self.combo_filtro_nivel_seguimiento)
        poblar_combo_curso(self.combo_curso_seguimiento, incluir_todos=False,
                            secciones_permitidas= self._permitidas_secciones_con_nivel_seguimiento())
        _acortar_placeholder_combo(self.combo_curso_seguimiento, "Selecciona grado")
        self._filtrar_seccion_seguimiento_por_curso()

    def _permitidas_secciones_con_nivel_seguimiento(self):
        nivel= self.combo_filtro_nivel_seguimiento.currentData() if hasattr(
            self, "combo_filtro_nivel_seguimiento") else None
        return interseccion_opcional(self._permitidas_secciones(), secciones_del_nivel_educativo(nivel))

    def _nivel_seguimiento_cambio(self):
        poblar_combo_curso(self.combo_curso_seguimiento, incluir_todos=False,
                            secciones_permitidas= self._permitidas_secciones_con_nivel_seguimiento())
        _acortar_placeholder_combo(self.combo_curso_seguimiento, "Selecciona grado")
        self._filtrar_seccion_seguimiento_por_curso()

    def _filtrar_seccion_seguimiento_por_curso(self):
        cascada_seccion_por_curso(self.combo_curso_seguimiento, self.combo_seccion_seguimiento,
                                   incluir_todas= False,
                                   secciones_permitidas= self._permitidas_secciones_con_nivel_seguimiento())
        if self.combo_curso_seguimiento.currentData() is None:
            _acortar_placeholder_combo(self.combo_seccion_seguimiento, "Selecciona curso")
        else:
            _acortar_placeholder_combo(self.combo_seccion_seguimiento, "Elige sección")

    def _cargar_periodos_seguimiento(self):
        self.combo_periodo_seguimiento.clear()
        for id_periodo, nombre in self._periodos_lista():
            self.combo_periodo_seguimiento.addItem(nombre, id_periodo)

    def _notas_y_rp_seccion(self, estudiante_ids, periodo_id, metodo):
        """Trae en 2 consultas (en vez de una por cada estudiante × materia) las notas
        finales y las notas de RP de todos los estudiantes de una sección para un
        periodo. Antes, generar el seguimiento de una sección de N estudiantes con M
        materias hacía hasta N*(1+M) conexiones a la BD; ahora son solo 2."""
        if not estudiante_ids:
            return {}, {}
        conn= obtener_conexion()
        c= conn.cursor()
        marcadores= ",".join("?" * len(estudiante_ids))
        c.execute(f"""SELECT estudiante_id, materia_id, valor, peso FROM calificaciones
                      WHERE periodo_id=? AND estudiante_id IN ({marcadores})
                      AND estado_publicacion != 'Borrador'""",
                  (periodo_id, *estudiante_ids))
        agrupado= {}
        for f in c.fetchall():
            clave= (f["estudiante_id"], f["materia_id"])
            agrupado.setdefault(clave, []).append({"valor": f["valor"], "peso": f["peso"]})
        notas= {clave: calcular_nota_final(calif, metodo) for clave, calif in agrupado.items()}

        c.execute(f"""SELECT estudiante_id, materia_id, nota_rp FROM recuperacion_pedagogica
                      WHERE periodo_id=? AND estudiante_id IN ({marcadores})""",
                  (periodo_id, *estudiante_ids))
        rp= {(f["estudiante_id"], f["materia_id"]): f["nota_rp"] for f in c.fetchall()}
        conn.close()
        return notas, rp

    def _generar_seguimiento(self, *_args):
        seccion_id= self.combo_seccion_seguimiento.currentData()
        periodo_id= self.combo_periodo_seguimiento.currentData()
        if seccion_id is None or periodo_id is None:
            #Si el cambio vino de los combos de Área Técnica/Carrera (antes de elegir Sección/Periodo), no interrumpimos
            #con un aviso: eso solo tiene sentido cuando el usuario pulsa el botón "Generar" a propósito -ver
            #_tab_seguimiento_rd, donde el botón sí llama a esta misma función-.
            if self.sender() in (self.combo_filtro_especialidad_seguimiento, self.combo_filtro_carrera_seguimiento):
                return
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona una sección y un periodo.", self)
            return
        permitidas_secciones= obtener_secciones_permitidas(self.main_window)
        if permitidas_secciones is not None and seccion_id not in permitidas_secciones:
            mostrar_mensaje("advertencia", "Sin acceso", "No tienes acceso a esa sección.", self)
            return
        permitidas_materias= obtener_materias_permitidas(self.main_window)
        metodo, nota_minima = self._obtener_metodo_y_minima(seccion_id=seccion_id)

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre, apellidos, especialidad_id, carrera_id, numero_lista FROM estudiantes
                     WHERE seccion_id=? AND estado='Activo'
                     ORDER BY numero_lista IS NULL, numero_lista, apellidos, nombre""", (seccion_id,))
        estudiantes= self._filtrar_por_tecnico([dict(f) for f in c.fetchall()],
            self.combo_filtro_especialidad_seguimiento, self.combo_filtro_carrera_seguimiento)
        conn.close()
        materias= self._materias_de_seccion(seccion_id)
        if permitidas_materias is not None:
            materias= [m for m in materias if m["id"] in permitidas_materias]

        filtro_estado= self.combo_filtro_estado_seguimiento.currentText()
        contadores= {e: 0 for e in self.ESTADOS_SEGUIMIENTO if e != "Todos"}
        filas_resultado= []
        notas_todas, rp_todas = self._notas_y_rp_seccion(
            [est["id"] for est in estudiantes], periodo_id, metodo)
        for est in estudiantes:
            nombre_est= f"{est['nombre']} {est['apellidos'] or ''}"
            for mat in materias:
                nota_final= notas_todas.get((est["id"], mat["id"]))
                if nota_final is not None:
                    rp= rp_todas.get((est["id"], mat["id"]))
                    estado, rp_txt = self._estado_materia_texto(nota_final, nota_minima, rp, True)
                    nota_txt= f"{nota_final:.2f}"
                else:
                    estado, rp_txt, nota_txt = "Sin Calificar", "-", "-"
                contadores[estado]= contadores.get(estado, 0) + 1
                if filtro_estado != "Todos" and estado != filtro_estado:
                    continue
                filas_resultado.append((est["numero_lista"], nombre_est, mat["nombre"], nota_txt, estado, rp_txt))

        self._seguimiento_filas= filas_resultado
        self.paginacion_seguimiento.establecer_total(len(filas_resultado))
        #El "No." solo se muestra si, además de la Sección (obligatoria para llegar hasta aquí), también se filtró Área
        #Técnica/Carrera cuando la institución las usa -ver bd.mostrar_columna_numero_lista.
        especialidad_id_seg= (self.combo_filtro_especialidad_seguimiento.currentData()
                                if self._es_politecnico() else None)
        carrera_id_seg= (self.combo_filtro_carrera_seguimiento.currentData()
                           if self._es_universidad() else None)
        self._mostrar_columna_numero_seguimiento= mostrar_columna_numero_lista(
            self.main_window, seccion_id, especialidad_id_seg, carrera_id_seg)
        self.tabla_seguimiento.setColumnHidden(0, not self._mostrar_columna_numero_seguimiento)
        self._repaginar_seguimiento()

        ESTADOS_QUE_REQUIEREN_ACCION= {"Sin Calificar", "Requiere RP", "RP Pendiente"}
        for estado, tarjeta in self.tarjetas_seguimiento.items():
            valor= contadores.get(estado, 0)
            tarjeta.actualizar(valor, alerta=(estado in ESTADOS_QUE_REQUIEREN_ACCION and valor > 0))

        if hasattr(self, "barra_seguimiento"):
            self.barra_seguimiento.actualizar(
                [(estado, contadores.get(estado, 0), self.COLORES_ESTADO_SEGUIMIENTO[estado])
                 for estado in self.ESTADOS_SEGUIMIENTO[1:]])

        if hasattr(self, "gauge_seguimiento"):
            total_registros= sum(contadores.values())
            al_dia= contadores.get("Competencia Alcanzada", 0) + contadores.get("RP Superada", 0)
            fraccion= (al_dia / total_registros) if total_registros else 0.0
            self.gauge_seguimiento.actualizar(fraccion, etiqueta="Al día en la sección")

        hay_pendientes= any(contadores.get(e, 0) > 0 for e in ESTADOS_QUE_REQUIEREN_ACCION)
        if hasattr(self, "idx_tab_seguimiento"):
            self.tabs.setTabIcon(
                self.idx_tab_seguimiento,
                _icono_punto("#EF4444", base=EMOJI_SEGUIMIENTO_RP) if hay_pendientes
                else icono_emoji(EMOJI_SEGUIMIENTO_RP))

        resumen= "  ·  ".join(f"{k}: {v}" for k, v in contadores.items())
        total_evaluaciones= sum(contadores.values())
        self.lbl_resumen_seguimiento.setText(
            f"Total materia-estudiante evaluadas: {total_evaluaciones}  —  {resumen}" if total_evaluaciones
            else "No hay materias con horario asignado a esta sección, o no hay estudiantes activos.")

        self._generar_desempeno_incompleto(estudiantes, periodo_id)

    def _repaginar_seguimiento(self):
        """Muestra solo la página actual de la tabla de seguimiento, igual que
        _repaginar_historial hace con el historial académico."""
        filas= getattr(self, "_seguimiento_filas", [])
        inicio, fin = self.paginacion_seguimiento.rango_actual()
        pagina= filas[inicio:fin]
        mostrar_columna_numero= getattr(self, "_mostrar_columna_numero_seguimiento", False)
        self.tabla_seguimiento.setRowCount(len(pagina))
        with tabla_pausada(self.tabla_seguimiento):
            for i, (numero_lista, nombre_est, materia_nombre, nota_txt, estado, rp_txt) in enumerate(pagina):
                if mostrar_columna_numero:
                    item_numero= QTableWidgetItem()
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                    item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla_seguimiento.setItem(i, 0, item_numero)
                self.tabla_seguimiento.setItem(i, 1, QTableWidgetItem(nombre_est))
                self.tabla_seguimiento.setItem(i, 2, QTableWidgetItem(materia_nombre))
                self.tabla_seguimiento.setItem(i, 3, QTableWidgetItem(nota_txt))
                item_estado= QTableWidgetItem(estado)
                color= self.COLORES_ESTADO_SEGUIMIENTO.get(estado)
                if color:
                    item_estado.setForeground(QColor(color))
                    font= item_estado.font()
                    font.setBold(True)
                    item_estado.setFont(font)
                self.tabla_seguimiento.setItem(i, 4, item_estado)
                self.tabla_seguimiento.setItem(i, 5, QTableWidgetItem(rp_txt))
        self.tabla_seguimiento.resizeRowsToContents()
        if hasattr(self, "in_buscar_seguimiento"):
            self._aplicar_busqueda_seguimiento(self.in_buscar_seguimiento.text())

    def _aplicar_busqueda_seguimiento(self, texto=""):
        """Filtra las filas ya generadas por nombre de estudiante o materia,
        sin exigir tildes ni respetar mayúsculas/minúsculas exactas."""
        if not hasattr(self, "tabla_seguimiento"):
            return
        consulta= _normalizar_busqueda(texto)
        for fila in range(self.tabla_seguimiento.rowCount()):
            if not consulta:
                self.tabla_seguimiento.setRowHidden(fila, False)
                continue
            item_nombre= self.tabla_seguimiento.item(fila, 1)
            item_materia= self.tabla_seguimiento.item(fila, 2)
            texto_fila= _normalizar_busqueda(
                f"{item_nombre.text() if item_nombre else ''} {item_materia.text() if item_materia else ''}")
            self.tabla_seguimiento.setRowHidden(fila, consulta not in texto_fila)

    def _generar_desempeno_incompleto(self, estudiantes, periodo_id):
        total_competencias= len(COMPETENCIAS_FUNDAMENTALES_RD)
        estudiante_ids= [est["id"] for est in estudiantes]
        conteos= {}
        if estudiante_ids:
            conn= obtener_conexion()
            c= conn.cursor()
            marcadores= ",".join("?" * len(estudiante_ids))
            c.execute(f"""SELECT estudiante_id, COUNT(*) as n FROM desempeno_individual
                          WHERE periodo_id=? AND nivel IS NOT NULL AND nivel<>?
                                AND estudiante_id IN ({marcadores})
                          GROUP BY estudiante_id""",
                      (periodo_id, NIVEL_SIN_EVALUAR_RD, *estudiante_ids))
            conteos= {f["estudiante_id"]: f["n"] for f in c.fetchall()}
            conn.close()
        filas= []
        for est in estudiantes:
            evaluadas= conteos.get(est["id"], 0)
            if evaluadas < total_competencias:
                filas.append((f"{est['nombre']} {est['apellidos'] or ''}", evaluadas, total_competencias))
        self.tabla_desempeno_incompleto.setRowCount(len(filas))
        with tabla_pausada(self.tabla_desempeno_incompleto):
            for i, (nombre_est, evaluadas, total) in enumerate(filas):
                self.tabla_desempeno_incompleto.setItem(i, 0, QTableWidgetItem(nombre_est))
                item= QTableWidgetItem(f"{evaluadas} de {total}")
                if evaluadas == 0:
                    item.setForeground(QColor(self.COLORES_ESTADO_SEGUIMIENTO["Requiere RP"]))
                else:
                    item.setForeground(QColor(self.COLORES_ESTADO_SEGUIMIENTO["RP Pendiente"]))
                self.tabla_desempeno_incompleto.setItem(i, 1, item)
        self.tabla_desempeno_incompleto.resizeRowsToContents()
        if hasattr(self, "tarjeta_desempeno_incompleto"):
            self.tarjeta_desempeno_incompleto.actualizar(len(filas), alerta=len(filas) > 0)

    #---------------- EVALUACIONES FINALES (Completiva / Extraordinaria / Especial) ---------------- Ordenanza
    #04-2023 (MINERD): si al cierre del año, después de la RP, la materia sigue por debajo del mínimo, puede pasar
    #a Completiva (50% nota del año + 50% examen), luego a Extraordinaria (30% + 70%) y, como última instancia, a
    #Especial. AcaDeXI calcula el resultado de cada etapa en cuanto el docente registra su nota, pero NO decide por
    #sí solo cuándo una materia avanza de una etapa a la siguiente, ni si el estudiante repite el grado: cada nota
    #se registra cuando el docente decide evaluar ahí, y la decisión final del año la registra manualmente el
    #docente/Coordinación.
    ETAPAS_FINALES_COLOR= {
        "Año": "#10B981", "Completiva": "#3B82F6", "Extraordinaria": "#F59E0B",
        "Especial": "#8B5CF6", "Pendiente de Completiva": "#EF4444",
        "Pendiente de Extraordinaria": "#EF4444", "Pendiente de Especial": "#EF4444",
    }
    DECISIONES_PROMOCION= ["Pendiente", "Promovido", "Evaluación Especial Autorizada", "Repite el Grado"]

    def _tab_evaluaciones_finales(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        aviso= QLabel("Cascada del año: Nota del Año Completiva Extraordinaria Especial. "
                       "AcaDeXI calcula cada etapa; tú decides si pasa a la siguiente y la decisión final.")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)

        panel_cascada= _crear_panel_dashboard()
        lay_cascada= panel_cascada.layout()
        self.timeline_finales= TimelineEvaluacion()
        lay_cascada.addWidget(self.timeline_finales, 1)
        l.addWidget(panel_cascada)

        self.lbl_filtro_especialidad_finales, self.combo_filtro_especialidad_finales,\
            self.lbl_filtro_carrera_finales, self.combo_filtro_carrera_finales =\
            self._crear_combos_filtro_tecnico(self._cargar_estudiantes_finales)

        self.combo_curso_finales= QComboBox()
        self.combo_curso_finales.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso_corto(self.combo_curso_finales, self.combo_seccion_finales),
                      self._cargar_estudiantes_finales()))
        self.combo_seccion_finales= QComboBox()
        self.combo_seccion_finales.currentIndexChanged.connect(self._cargar_estudiantes_finales)

        self._reemplazar_por_filtros(l, "finales", "Filtros de Evaluaciones Finales",
            [(self.lbl_filtro_especialidad_finales, self.combo_filtro_especialidad_finales),
             (self.lbl_filtro_carrera_finales, self.combo_filtro_carrera_finales),
             ("Curso:", self.combo_curso_finales),
             ("Sección:", self.combo_seccion_finales)])
        self._conectar_resumen_filtros("finales", [
            ("Curso", self.combo_curso_finales), ("Sección", self.combo_seccion_finales),
            ("Área Técnica", self.combo_filtro_especialidad_finales),
            ("Carrera", self.combo_filtro_carrera_finales)])

        fila= QHBoxLayout()
        self.combo_estudiante_finales= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante_finales, "Estudiante cuya evaluación final se registra")
        fila.addWidget(QLabel("Estudiante:"))
        fila.addWidget(self.combo_estudiante_finales)
        self.in_anio_finales= QLineEdit()
        limitar_campo_texto(self.in_anio_finales, 300)
        self.in_anio_finales.setPlaceholderText("Año académico (ej. 2026-2027)")
        fila.addWidget(QLabel("Año Académico:"))
        fila.addWidget(self.in_anio_finales)
        ajustar_combo_ancho_seguro(self.combo_curso_finales, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_seccion_finales, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_estudiante_finales, min_len=13)
        btn_generar= QPushButton("Calcular")
        btn_generar.setIcon(icono_emoji(EMOJI_EVALUACIONES_FINALES))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAjustar")
        btn_generar.clicked.connect(self._generar_evaluaciones_finales)
        fila.addWidget(btn_generar)
        l.addLayout(fila)
        l.addSpacing(8)

        self.in_buscar_finales= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_finales.setPlaceholderText(
            "Buscar por materia, etapa o resultado (ignora tildes y mayúsculas)...")
        self.in_buscar_finales.texto_buscado.connect(
            lambda t: self._filtrar_tabla_texto(self.tabla_finales, t, (0, 2, 5)))
        l.addWidget(self.in_buscar_finales)
        l.addSpacing(6)


        self.tabla_finales= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_finales)
        self.tabla_finales.setHorizontalHeaderLabels(
            ["Materia", "Nota del Año", "Etapa Actual", "Nota Registrada", "Nota Final de la Etapa", "Resultado"])
        header= self.tabla_finales.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #"Materia" ya es Stretch; con StretchLastSection activo, "Resultado" (última columna) competiría por el mismo
        #espacio.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_finales.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_finales.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_finales.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_finales.setAlternatingRowColors(True)
        self.tabla_finales.verticalHeader().setVisible(False)
        self.tabla_finales.setMinimumHeight(200)
        l.addWidget(self.tabla_finales, 1)

        agregar_boton_pantalla_completa(
            None, [self.in_buscar_finales, self.tabla_finales],
            titulo= "Evaluaciones Finales", parent=self)


        fila_botones= QHBoxLayout()
        btn_completiva= QPushButton("Registrar Nota Completiva")
        btn_completiva.setIcon(icono_emoji(EMOJI_NOTA_COMPLETIVA))
        btn_completiva.setIconSize(_QSize_emoji(16, 16))
        btn_completiva.clicked.connect(lambda: self._registrar_evaluacion_final("completiva"))
        fila_botones.addWidget(btn_completiva)
        btn_extraordinaria= QPushButton("Registrar Nota Extraordinaria")
        btn_extraordinaria.setIcon(icono_emoji(EMOJI_NOTA_EXTRAORDINARIA))
        btn_extraordinaria.setIconSize(_QSize_emoji(16, 16))
        btn_extraordinaria.clicked.connect(lambda: self._registrar_evaluacion_final("extraordinaria"))
        fila_botones.addWidget(btn_extraordinaria)
        btn_especial= QPushButton("Registrar Nota Especial")
        btn_especial.setIcon(icono_emoji(EMOJI_NOTA_ESPECIAL))
        btn_especial.setIconSize(_QSize_emoji(16, 16))
        btn_especial.clicked.connect(lambda: self._registrar_evaluacion_final("especial"))
        fila_botones.addWidget(btn_especial)
        fila_botones.addStretch()
        l.addLayout(fila_botones)

        self.lbl_resumen_finales= QLabel("")
        self.lbl_resumen_finales.setWordWrap(True)
        self.lbl_resumen_finales.setObjectName("DescModulo")
        fila_resumen_finales= QHBoxLayout()
        self.tarjeta_resumen_finales= TarjetaAlerta("📘", "Materias Pendientes", "#EF4444")
        self._tarjetas_alerta.append(self.tarjeta_resumen_finales)
        fila_resumen_finales.addWidget(self.tarjeta_resumen_finales)
        columna_resumen_finales= QVBoxLayout()
        columna_resumen_finales.addWidget(self.lbl_resumen_finales)
        columna_resumen_finales.addStretch()
        fila_resumen_finales.addLayout(columna_resumen_finales, 1)
        l.addLayout(fila_resumen_finales)

        fila_decision= QHBoxLayout()
        fila_decision.addWidget(QLabel("Decisión final del año para este estudiante:"))
        self.combo_decision_final= QComboBox()
        self.combo_decision_final.addItems(self.DECISIONES_PROMOCION)
        conectar_tooltip_seleccion(self.combo_decision_final, "Decisión final de promoción para este estudiante")
        fila_decision.addWidget(self.combo_decision_final)
        btn_guardar_decision= QPushButton("Guardar Decisión")
        btn_guardar_decision.setIcon(icono_emoji("💾"))
        btn_guardar_decision.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_decision.setObjectName("BtnAccionAgregar")
        btn_guardar_decision.clicked.connect(self._guardar_decision_promocion)
        fila_decision.addWidget(btn_guardar_decision)
        fila_decision.addStretch()
        self.in_observacion_decision= QLineEdit()
        limitar_campo_texto(self.in_observacion_decision, 300)
        self.in_observacion_decision.setPlaceholderText("Observación de la decisión (opcional)")
        nota_decision= QLabel("Esta decisión (promoción, Evaluación Especial o repitencia) la registra el "
                               "docente/Coordinación manualmente; AcaDeXI solo la guarda y la muestra, no la calcula.")
        nota_decision.setWordWrap(True)
        nota_decision.setObjectName("DescModulo")
        frame_form_decision= QWidget()
        lay_frame_form_decision= QVBoxLayout(frame_form_decision)
        lay_frame_form_decision.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_decision.setSpacing(10)
        lay_frame_form_decision.addLayout(fila_decision)
        lay_frame_form_decision.addWidget(self.in_observacion_decision)
        lay_frame_form_decision.addWidget(nota_decision)
        self._envolver_en_panel(l, "Registrar Decisión Final de Promoción", frame_form_decision)
        l.addStretch(1)
        return w

    def _cargar_secciones_finales(self):
        self._poblar_combo_curso_corto(self.combo_curso_finales)
        self._filtrar_seccion_por_curso_corto(self.combo_curso_finales, self.combo_seccion_finales)
        if not self.in_anio_finales.text().strip():
            self.in_anio_finales.setText(self._anio_academico_actual())

    def _cargar_estudiantes_finales(self):
        self.combo_estudiante_finales.clear()
        seccion_id= self.combo_seccion_finales.currentData()
        if seccion_id is None:
            self.combo_estudiante_finales.addItem("Elige estudiante", None)
            _actualizar_estado_combo_estudiante(self.combo_curso_finales, self.combo_seccion_finales,
                                                 self.combo_estudiante_finales)
            return
        for f in self._filtrar_por_tecnico(self._estudiantes_activos(), self.combo_filtro_especialidad_finales,
                                            self.combo_filtro_carrera_finales):
            if f["seccion_id"] != seccion_id:
                continue
            self.combo_estudiante_finales.addItem(f"{f['nombre']} {f['apellidos'] or ''}".strip(), f["id"])
        _actualizar_estado_combo_estudiante(self.combo_curso_finales, self.combo_seccion_finales,
                                             self.combo_estudiante_finales)

    def _anio_academico_actual(self):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT anio_academico FROM configuracion WHERE id=1")
        f= c.fetchone()
        conn.close()
        return (f["anio_academico"] if f and f["anio_academico"] else "") or ""

    def _periodos_del_anio(self, anio_academico):
        conn= obtener_conexion()
        c= conn.cursor()
        if anio_academico:
            c.execute("SELECT id, nombre FROM periodos WHERE anio_academico=? ORDER BY orden", (anio_academico,))
            filas= c.fetchall()
            if not filas:
                #Compatibilidad: bases donde 'periodos' no trae anio_academico cargado.
                c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
                filas= c.fetchall()
        else:
            c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
            filas= c.fetchall()
        conn.close()
        return filas

    def _nota_periodo_efectiva(self, estudiante_id, materia_id, periodo_id, metodo):
        """Nota de un periodo para una materia. Si el docente ya registró la RP de ese
        periodo, la RP reemplaza la nota (así se refleja el refuerzo/nueva valoración,
        ej. P4=62 -> RP -> P4=74). Si no hay RP, se usa la nota calculada normalmente."""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT valor, peso FROM calificaciones
                     WHERE estudiante_id=? AND materia_id=? AND periodo_id=?
                     AND estado_publicacion != 'Borrador'""",
                  (estudiante_id, materia_id, periodo_id))
        calif= [{"valor": f["valor"], "peso": f["peso"]} for f in c.fetchall()]
        conn.close()
        rp= self._obtener_rp(estudiante_id, materia_id, periodo_id)
        if rp is not None:
            return rp
        if not calif:
            return None
        return calcular_nota_final(calif, metodo)

    def _nota_anual_materia(self, estudiante_id, materia_id, metodo, anio_academico):
        """Promedio de los periodos del año (P1-P4) ya considerando la RP donde se haya
        registrado. Solo se promedian los periodos que efectivamente tienen nota."""
        periodos= self._periodos_del_anio(anio_academico)
        notas= []
        for p in periodos:
            n= self._nota_periodo_efectiva(estudiante_id, materia_id, p["id"], metodo)
            if n is not None:
                notas.append(n)
        if not notas:
            return None
        return sum(notas) / len(notas)

    def _obtener_evaluacion_final(self, tabla, columna, estudiante_id, materia_id, anio_academico):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""SELECT {columna} FROM {tabla}
                     WHERE estudiante_id=? AND materia_id=? AND anio_academico=?""",
                  (estudiante_id, materia_id, anio_academico))
        f= c.fetchone()
        conn.close()
        return f[columna] if f else None

    def _obtener_evaluacion_final_completa(self, tabla, columna, estudiante_id, materia_id, anio_academico):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"SELECT * FROM {tabla} WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
                  (estudiante_id, materia_id, anio_academico))
        f= c.fetchone()
        conn.close()
        if not f:
            return {}
        d= dict(f)
        d["nota"]= d.get(columna)
        return d

    def _guardar_evaluacion_final(self, tabla, columna, estudiante_id, materia_id, anio_academico, nota,
                                   observacion= "", responsable=""):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""INSERT INTO {tabla}
                     (estudiante_id, materia_id, anio_academico, {columna}, fecha, observacion, responsable)
                     VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(estudiante_id, materia_id, anio_academico) DO UPDATE SET
                        {columna}=excluded.{columna}, fecha=excluded.fecha,
                        observacion= excluded.observacion, responsable=excluded.responsable""",
                  (estudiante_id, materia_id, anio_academico, nota,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), observacion, responsable))
        conn.commit()
        conn.close()

    def _obtener_completiva(self, estudiante_id, materia_id, anio):
        return self._obtener_evaluacion_final("evaluacion_completiva", "nota_completiva",
                                               estudiante_id, materia_id, anio)

    def _guardar_completiva(self, estudiante_id, materia_id, anio, nota, observacion="", responsable=""):
        self._guardar_evaluacion_final("evaluacion_completiva", "nota_completiva",
                                        estudiante_id, materia_id, anio, nota, observacion, responsable)

    def _obtener_extraordinaria(self, estudiante_id, materia_id, anio):
        return self._obtener_evaluacion_final("evaluacion_extraordinaria", "nota_extraordinaria",
                                               estudiante_id, materia_id, anio)

    def _guardar_extraordinaria(self, estudiante_id, materia_id, anio, nota, observacion="", responsable=""):
        self._guardar_evaluacion_final("evaluacion_extraordinaria", "nota_extraordinaria",
                                        estudiante_id, materia_id, anio, nota, observacion, responsable)

    def _obtener_especial(self, estudiante_id, materia_id, anio):
        return self._obtener_evaluacion_final("evaluacion_especial", "nota_especial",
                                               estudiante_id, materia_id, anio)

    def _guardar_especial(self, estudiante_id, materia_id, anio, nota, observacion="", responsable=""):
        self._guardar_evaluacion_final("evaluacion_especial", "nota_especial",
                                        estudiante_id, materia_id, anio, nota, observacion, responsable)

    def _resultado_final_materia(self, estudiante_id, materia_id, metodo, nota_minima, anio):
        """Aplica la cascada Año -> Completiva -> Extraordinaria -> Especial. Cada etapa
        solo se evalúa si el docente ya registró su nota; si no la ha registrado, la
        materia queda marcada como pendiente EN esa etapa (no se avanza ni se decide nada
        por ella). El resultado 'aprobado' es None mientras falte una nota por registrar
        en la etapa donde está actualmente."""
        nota_anual= self._nota_anual_materia(estudiante_id, materia_id, metodo, anio)
        resultado= {"materia_id": materia_id, "nota_anual": nota_anual, "etapa": "Año",
                     "nota_etapa": None, "nota_final": nota_anual, "aprobado": None}
        if nota_anual is None:
            return resultado
        if nota_anual >= nota_minima:
            resultado["aprobado"]= True
            return resultado

        nota_completiva= self._obtener_completiva(estudiante_id, materia_id, anio)
        if nota_completiva is None:
            resultado.update({"etapa": "Pendiente de Completiva", "aprobado": False, "nota_final": nota_anual})
            return resultado
        final_completiva= (nota_anual * 0.5) + (nota_completiva * 0.5)
        resultado.update({"etapa": "Completiva", "nota_etapa": nota_completiva, "nota_final": final_completiva})
        if final_completiva >= nota_minima:
            resultado["aprobado"]= True
            return resultado

        nota_extra= self._obtener_extraordinaria(estudiante_id, materia_id, anio)
        if nota_extra is None:
            resultado.update({"etapa": "Pendiente de Extraordinaria", "aprobado": False})
            return resultado
        final_extra= (nota_anual * 0.3) + (nota_extra * 0.7)
        resultado.update({"etapa": "Extraordinaria", "nota_etapa": nota_extra, "nota_final": final_extra})
        if final_extra >= nota_minima:
            resultado["aprobado"]= True
            return resultado

        nota_especial= self._obtener_especial(estudiante_id, materia_id, anio)
        if nota_especial is None:
            resultado.update({"etapa": "Pendiente de Especial", "aprobado": False})
            return resultado
        resultado.update({"etapa": "Especial", "nota_etapa": nota_especial, "nota_final": nota_especial,
                           "aprobado": nota_especial >= nota_minima})
        return resultado

    def _generar_evaluaciones_finales(self):
        estudiante_id= self.combo_estudiante_finales.currentData()
        seccion_id= self.combo_seccion_finales.currentData()
        anio= self.in_anio_finales.text().strip() or self._anio_academico_actual()
        if estudiante_id is None or seccion_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona una sección y un estudiante.", self)
            return
        metodo, nota_minima = self._obtener_metodo_y_minima(estudiante_id=estudiante_id)
        materias= self._materias_de_seccion(seccion_id)
        permitidas_materias= obtener_materias_permitidas(self.main_window)
        if permitidas_materias is not None:
            materias= [m for m in materias if m["id"] in permitidas_materias]

        self._resultados_finales_actuales= []
        pendientes= []
        for mat in materias:
            r= self._resultado_final_materia(estudiante_id, mat["id"], metodo, nota_minima, anio)
            r["materia_nombre"]= mat["nombre"]
            self._resultados_finales_actuales.append(r)
            if r["aprobado"] is False:
                pendientes.append(mat["nombre"])

        self.tabla_finales.setRowCount(len(self._resultados_finales_actuales))
        with tabla_pausada(self.tabla_finales):
            for i, r in enumerate(self._resultados_finales_actuales):
                item_mat= QTableWidgetItem(r["materia_nombre"])
                item_mat.setData(Qt.ItemDataRole.UserRole, r["materia_id"])
                self.tabla_finales.setItem(i, 0, item_mat)
                self.tabla_finales.setItem(i, 1,
                    QTableWidgetItem(f"{r['nota_anual']:.2f}" if r["nota_anual"] is not None else "-"))
                item_etapa= QTableWidgetItem(r["etapa"])
                color= self.ETAPAS_FINALES_COLOR.get(r["etapa"])
                if color:
                    item_etapa.setForeground(QColor(color))
                    font= item_etapa.font(); font.setBold(True); item_etapa.setFont(font)
                self.tabla_finales.setItem(i, 2, item_etapa)
                self.tabla_finales.setItem(i, 3,
                    QTableWidgetItem(f"{r['nota_etapa']:.2f}" if r["nota_etapa"] is not None else "-"))
                self.tabla_finales.setItem(i, 4,
                    QTableWidgetItem(f"{r['nota_final']:.2f}" if r["nota_final"] is not None else "-"))
                if r["aprobado"] is True:
                    resultado_txt= "Aprobado"
                elif r["aprobado"] is False:
                    resultado_txt= "No Alcanzado"
                else:
                    resultado_txt= "Sin Calificar"
                self.tabla_finales.setItem(i, 5, QTableWidgetItem(resultado_txt))
        self.tabla_finales.resizeRowsToContents()
        if hasattr(self, "in_buscar_finales"):
            self._filtrar_tabla_texto(self.tabla_finales, self.in_buscar_finales.text(), (0, 2, 5))

        if pendientes:
            self.lbl_resumen_finales.setText(
                f"ℹ Informativo: {len(pendientes)} materia(s) sin alcanzar el mínimo en su etapa actual —"
                + ", ".join(pendientes) +
                ". Esto es solo un dato de referencia; tú decides si corresponde Evaluación Especial "
                "o si el estudiante repite el grado, y registras esa decisión abajo.")
        else:
            self.lbl_resumen_finales.setText(
                "Ninguna materia calculada está por debajo del mínimo en su etapa actual.")
        if hasattr(self, "tarjeta_resumen_finales"):
            self.tarjeta_resumen_finales.actualizar(len(pendientes), alerta=len(pendientes) > 0)
        if hasattr(self, "idx_tab_evaluaciones_finales"):
            self.tabs.setTabIcon(
                self.idx_tab_evaluaciones_finales,
                _icono_punto("#EF4444", base=EMOJI_EVALUACIONES_FINALES) if pendientes
                else icono_emoji(EMOJI_EVALUACIONES_FINALES))
        if hasattr(self, "timeline_finales"):
            #Cada materia 'vive' en la etapa que le corresponde ahora mismo:
            #o bien todavía sin calificar en 'Año', o esperando que se registre
            #la nota de la etapa siguiente ('Pendiente de X' -> nodo X), o ya
            #perdida definitivamente en 'Especial'. Así el nodo que se ilumina es literalmente donde el docente tiene
            #trabajo pendiente.
            conteo_cascada= {"Año": 0, "Completiva": 0, "Extraordinaria": 0, "Especial": 0}
            for r in self._resultados_finales_actuales:
                etapa= r["etapa"]
                if etapa == "Año" and r["aprobado"] is None:
                    conteo_cascada["Año"] += 1
                elif etapa.startswith("Pendiente de "):
                    base= etapa.replace("Pendiente de ", "")
                    if base in conteo_cascada:
                        conteo_cascada[base] += 1
                elif etapa == "Especial" and r["aprobado"] is False:
                    conteo_cascada["Especial"] += 1
            self.timeline_finales.actualizar([
                ("Año", self.ETAPAS_FINALES_COLOR["Año"], conteo_cascada["Año"]),
                ("Completiva", self.ETAPAS_FINALES_COLOR["Completiva"], conteo_cascada["Completiva"]),
                ("Extraordinaria", self.ETAPAS_FINALES_COLOR["Extraordinaria"], conteo_cascada["Extraordinaria"]),
                ("Especial", self.ETAPAS_FINALES_COLOR["Especial"], conteo_cascada["Especial"]),
            ])

        self._cargar_decision_promocion(estudiante_id, anio)

    def _registrar_evaluacion_final(self, etapa):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar esta nota.", self)
            return
        fila= self.tabla_finales.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una materia de la tabla.", self)
            return
        materia_id= self.tabla_finales.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        estudiante_id= self.combo_estudiante_finales.currentData()
        anio= self.in_anio_finales.text().strip() or self._anio_academico_actual()
        if materia_id is None or estudiante_id is None or not anio:
            mostrar_mensaje("advertencia", "Datos incompletos", "No se pudo identificar la materia o el año académico.", self)
            return

        etiquetas= {"completiva": "Evaluación Completiva", "extraordinaria": "Evaluación Extraordinaria",
                     "especial": "Evaluación Especial"}
        tablas= {"completiva": ("evaluacion_completiva", "nota_completiva"),
                  "extraordinaria": ("evaluacion_extraordinaria", "nota_extraordinaria"),
                  "especial": ("evaluacion_especial", "nota_especial")}
        guardar= {"completiva": self._guardar_completiva, "extraordinaria": self._guardar_extraordinaria,
                  "especial": self._guardar_especial}[etapa]
        tabla, columna = tablas[etapa]

        actual= self._obtener_evaluacion_final_completa(tabla, columna, estudiante_id, materia_id, anio)
        dialogo= DialogoEvaluacionFinal(etiquetas[etapa], actual, self.main_window.usuario_actual, self)
        if not dialogo.exec():
            return
        datos= dialogo.datos()
        guardar(estudiante_id, materia_id, anio, datos["nota"], datos["observacion"], datos["responsable"])
        registrar_auditoria("Calificaciones", f"Registró nota de {etiquetas[etapa]}",
                            self.main_window.usuario_actual,
                            f"Estudiante ID {estudiante_id} - Materia ID {materia_id} - Año {anio}: {datos['nota']}")
        self._generar_evaluaciones_finales()

    def _cargar_decision_promocion(self, estudiante_id, anio):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT decision, observacion FROM decision_promocion
                     WHERE estudiante_id=? AND anio_academico=?""", (estudiante_id, anio))
        f= c.fetchone()
        conn.close()
        idx= self.combo_decision_final.findText(f["decision"] if f else "Pendiente")
        self.combo_decision_final.setCurrentIndex(idx if idx >= 0 else 0)
        self.in_observacion_decision.setText((f["observacion"] if f else "") or "")

    def _guardar_decision_promocion(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar esta decisión.", self)
            return
        estudiante_id= self.combo_estudiante_finales.currentData()
        anio= self.in_anio_finales.text().strip() or self._anio_academico_actual()
        if estudiante_id is None or not anio:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona un estudiante y un año académico.", self)
            return
        decision= self.combo_decision_final.currentText()
        observacion= self.in_observacion_decision.text().strip()
        #Cierre de año (punto pedido): se guarda junto con la decisión la lista de materias que quedaron pendientes en
        #su etapa actual, tomada de la última vez que se pulsó "🔄 Calcular" en esta pestaña para este estudiante/año.
        pendientes_actuales= getattr(self, "_resultados_finales_actuales", None) or []
        materias_pendientes= ", ".join(
            r["materia_nombre"] for r in pendientes_actuales if r.get("aprobado") is False)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""INSERT INTO decision_promocion
                     (estudiante_id, anio_academico, decision, observacion, usuario, fecha, materias_pendientes)
                     VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(estudiante_id, anio_academico) DO UPDATE SET
                        decision= excluded.decision, observacion=excluded.observacion,
                        usuario= excluded.usuario, fecha=excluded.fecha,
                        materias_pendientes= excluded.materias_pendientes""",
                  (estudiante_id, anio, decision, observacion, self.main_window.usuario_actual,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), materias_pendientes))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", "Registró decisión final de promoción",
                            self.main_window.usuario_actual,
                            f"Estudiante ID {estudiante_id} - Año {anio}: {decision}")
        mostrar_mensaje("exito", "Guardado", "La decisión final del año académico se guardó correctamente.", self)

    #---------------- CURRÍCULO (Competencias Específicas / Indicadores) ----------------
    def _tab_curriculo_rd(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        aviso= QLabel("Define aquí las Competencias Específicas de cada materia+grado, con sus "
                       "Indicadores de Logro. Aparecerán al registrar evidencias y en Notas por Competencia.")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)

        self._puede_editar_curriculo= tiene_acceso_gerencial(self.main_window)
        if not self._puede_editar_curriculo:
            solo_lectura= QLabel("Tu rol solo puede consultar el currículo.")
            solo_lectura.setWordWrap(True)
            solo_lectura.setObjectName("DescModulo")
            l.addWidget(solo_lectura)

        fila_filtro= QHBoxLayout()
        self.combo_materia_curriculo= QComboBox()
        self.combo_materia_curriculo.currentIndexChanged.connect(self._cargar_grados_curriculo)
        conectar_tooltip_seleccion(self.combo_materia_curriculo, "Materia cuyo currículo se edita")
        fila_filtro.addWidget(QLabel("Materia:"))
        fila_filtro.addWidget(self.combo_materia_curriculo)
        self.combo_grado_curriculo= QComboBox()
        self.combo_grado_curriculo.currentIndexChanged.connect(self._cargar_competencias_curriculo)
        conectar_tooltip_seleccion(self.combo_grado_curriculo, "Grado/Curso cuyo currículo se edita")
        fila_filtro.addWidget(QLabel("Grado:"))
        fila_filtro.addWidget(self.combo_grado_curriculo)
        ajustar_combo_ancho_seguro(self.combo_materia_curriculo, self.combo_grado_curriculo)
        fila_filtro.addStretch()
        l.addLayout(fila_filtro)
        l.addSpacing(8)

        self.in_buscar_curriculo= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_curriculo.setPlaceholderText(
            "Buscar por código, descripción o competencia fundamental (ignora tildes y mayúsculas)...")
        self.in_buscar_curriculo.texto_buscado.connect(
            lambda t: self._filtrar_tabla_texto(self.tabla_curriculo, t, (0, 1, 2)))
        l.addWidget(self.in_buscar_curriculo)
        l.addSpacing(6)


        self.tabla_curriculo= QTableWidget(0, 5)
        aplicar_estructura_tabla(self.tabla_curriculo)
        self.tabla_curriculo.setHorizontalHeaderLabels(
            ["Código", "Descripción de la Competencia", "Competencia Fundamental", "Orden", "Indicadores"])
        header= self.tabla_curriculo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        #La columna Stretch no es la última; con StretchLastSection activo, "Indicadores" (última) competiría por el
        #mismo espacio.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_curriculo.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_curriculo.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_curriculo.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_curriculo.setAlternatingRowColors(True)
        self.tabla_curriculo.verticalHeader().setVisible(False)
        self.tabla_curriculo.setMinimumHeight(340)
        l.addWidget(self.tabla_curriculo, 1)
        l.addSpacing(12)

        agregar_boton_pantalla_completa(
            None, [self.in_buscar_curriculo, self.tabla_curriculo],
            titulo= "Currículo", parent=self)


        fila_form= QGridLayout()
        fila_form.setHorizontalSpacing(14)
        fila_form.setVerticalSpacing(10)
        self.in_codigo_ce= QLineEdit(); self.in_codigo_ce.setPlaceholderText("Código (ej. CE1, CE-05)")
        limitar_campo_texto(self.in_codigo_ce, 300)
        self.in_descripcion_ce= QLineEdit(); self.in_descripcion_ce.setPlaceholderText(
            "Descripción de la competencia (ej. Resolución de problemas lógicos)")
        limitar_campo_texto(self.in_descripcion_ce, 300)
        self.combo_fundamental_ce= QComboBox()
        self.combo_fundamental_ce.addItem("(sin mapear)", "")
        for cf in COMPETENCIAS_FUNDAMENTALES_RD:
            self.combo_fundamental_ce.addItem(cf, cf)
        ajustar_combo_ancho_seguro(self.combo_fundamental_ce)
        conectar_tooltip_seleccion(self.combo_fundamental_ce,
            "Competencia Fundamental (RD) a la que se mapea esta competencia específica")
        self.spin_orden_ce= QSpinBox(); self.spin_orden_ce.setRange(1, 99); self.spin_orden_ce.setValue(1)
        fila_form.addWidget(QLabel("Código:"), 0, 0); fila_form.addWidget(self.in_codigo_ce, 0, 1)
        fila_form.addWidget(QLabel("Orden:"), 0, 2); fila_form.addWidget(self.spin_orden_ce, 0, 3)
        fila_form.addWidget(self.in_descripcion_ce, 1, 0, 1, 2)
        fila_form.addWidget(QLabel("Mapea a Competencia Fundamental:"), 1, 2)
        fila_form.addWidget(self.combo_fundamental_ce, 1, 3)

        fila_botones_ce= QHBoxLayout()
        self.id_edicion_ce= None
        btn_guardar_ce= QPushButton("Guardar Competencia Específica")
        btn_guardar_ce.setIcon(icono_emoji("💾"))
        btn_guardar_ce.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_ce.setObjectName("BtnAccionAgregar")
        btn_guardar_ce.clicked.connect(self._guardar_competencia_curriculo)
        fila_botones_ce.addWidget(btn_guardar_ce)
        btn_editar_ce= QPushButton("Cargar Seleccionada")
        btn_editar_ce.setIcon(icono_emoji("✏"))
        btn_editar_ce.setIconSize(_QSize_emoji(16, 16))
        btn_editar_ce.setObjectName("BtnAccionEditar")
        btn_editar_ce.clicked.connect(self._cargar_competencia_seleccionada_curriculo)
        fila_botones_ce.addWidget(btn_editar_ce)
        btn_indicadores_ce= QPushButton("Indicadores de Logro")
        btn_indicadores_ce.setIcon(icono_emoji("🏆"))
        btn_indicadores_ce.setIconSize(_QSize_emoji(16, 16))
        btn_indicadores_ce.setObjectName("BtnAccionAjustar")
        btn_indicadores_ce.clicked.connect(self._abrir_indicadores_curriculo)
        fila_botones_ce.addWidget(btn_indicadores_ce)
        btn_eliminar_ce= QPushButton("Eliminar")
        btn_eliminar_ce.setIcon(icono_emoji("🗑"))
        btn_eliminar_ce.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar_ce.setObjectName("BtnAccionEliminar")
        btn_eliminar_ce.clicked.connect(self._eliminar_competencia_curriculo)
        fila_botones_ce.addWidget(btn_eliminar_ce)
        fila_botones_ce.addStretch()

        frame_form_ce= QWidget()
        lay_frame_form_ce= QVBoxLayout(frame_form_ce)
        lay_frame_form_ce.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_ce.setSpacing(10)
        lay_frame_form_ce.addLayout(fila_form)
        lay_frame_form_ce.addLayout(fila_botones_ce)
        self._envolver_en_panel(l, "Añadir Competencia Específica", frame_form_ce)
        l.addStretch(1)
        return w

    def _cargar_materias_curriculo(self):
        self.combo_materia_curriculo.clear()
        for id_materia, nombre in self._materias_activas():
            self.combo_materia_curriculo.addItem(nombre, id_materia)

    def _cargar_grados_curriculo(self):
        self.combo_grado_curriculo.clear()
        materia_id= self.combo_materia_curriculo.currentData()
        for grado in grados_de_materia(materia_id):
            self.combo_grado_curriculo.addItem(grado["nombre"], grado["id"])
        if self.combo_grado_curriculo.count() == 0:
            #La materia todavía no tiene horarios asignados a ningún grado: se listan todos los grados existentes igual,
            #para no bloquear la definición del currículo.
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")
            for f in c.fetchall():
                self.combo_grado_curriculo.addItem(f["nombre"], f["id"])
            conn.close()

    def _cargar_competencias_curriculo(self):
        materia_id= self.combo_materia_curriculo.currentData()
        grado_id= self.combo_grado_curriculo.currentData()
        self._limpiar_form_ce()
        if materia_id is None or grado_id is None:
            self.tabla_curriculo.setRowCount(0)
            return
        competencias= competencias_de_materia_grado(materia_id, grado_id, solo_activas=False)
        conn= obtener_conexion()
        c= conn.cursor()
        self.tabla_curriculo.setRowCount(len(competencias))
        with tabla_pausada(self.tabla_curriculo):
            for i, comp in enumerate(competencias):
                item_cod= QTableWidgetItem(comp["codigo"])
                item_cod.setData(Qt.ItemDataRole.UserRole, comp["id"])
                self.tabla_curriculo.setItem(i, 0, item_cod)
                self.tabla_curriculo.setItem(i, 1, QTableWidgetItem(comp["descripcion"]))
                self.tabla_curriculo.setItem(i, 2, QTableWidgetItem(comp.get("competencia_fundamental") or "—"))
                self.tabla_curriculo.setItem(i, 3, QTableWidgetItem(str(comp["orden"])))
                c.execute("SELECT COUNT(*) as n FROM indicadores_logro WHERE competencia_id=?", (comp["id"],))
                n_ind= c.fetchone()["n"]
                self.tabla_curriculo.setItem(i, 4, QTableWidgetItem(f"{n_ind} indicador(es)"))
        conn.close()
        if hasattr(self, "in_buscar_curriculo"):
            self._filtrar_tabla_texto(self.tabla_curriculo, self.in_buscar_curriculo.text(), (0, 1, 2))

    def _limpiar_form_ce(self):
        self.id_edicion_ce= None
        self.in_codigo_ce.clear()
        self.in_descripcion_ce.clear()
        self.combo_fundamental_ce.setCurrentIndex(0)
        self.spin_orden_ce.setValue((self.tabla_curriculo.rowCount() or 0) + 1)
        desactivar_modo_edicion(self.in_codigo_ce)

    def _guardar_competencia_curriculo(self):
        if not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                             "Solo un rol gerencial puede modificar el currículo.", self)
            return
        materia_id= self.combo_materia_curriculo.currentData()
        grado_id= self.combo_grado_curriculo.currentData()
        codigo= self.in_codigo_ce.text().strip()
        descripcion= self.in_descripcion_ce.text().strip()
        if materia_id is None or grado_id is None or not codigo or not descripcion:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Selecciona materia y grado, y completa código y descripción.", self)
            return
        fundamental= self.combo_fundamental_ce.currentData() or ""
        orden= self.spin_orden_ce.value()
        conn= obtener_conexion()
        c= conn.cursor()
        try:
            if self.id_edicion_ce is None:
                c.execute("""INSERT INTO competencias_especificas
                             (materia_id, grado_id, codigo, descripcion, competencia_fundamental, orden)
                             VALUES (?,?,?,?,?,?)""",
                          (materia_id, grado_id, codigo, descripcion, fundamental, orden))
                accion= "Creó Competencia Específica"
            else:
                c.execute("""UPDATE competencias_especificas SET codigo=?, descripcion=?,
                             competencia_fundamental= ?, orden=? WHERE id=?""",
                          (codigo, descripcion, fundamental, orden, self.id_edicion_ce))
                accion= "Editó Competencia Específica"
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            mostrar_mensaje("advertencia", "Código repetido",
                             f"Ya existe una competencia con código '{codigo}' para esta materia y grado.", self)
            return
        conn.close()
        registrar_auditoria("Calificaciones", accion, self.main_window.usuario_actual,
                            f"{codigo} - {descripcion}")
        self._cargar_competencias_curriculo()

    def _cargar_competencia_seleccionada_curriculo(self):
        fila= self.tabla_curriculo.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una competencia de la tabla.", self)
            return
        competencia_id= self.tabla_curriculo.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM competencias_especificas WHERE id=?", (competencia_id,))
        comp= c.fetchone()
        conn.close()
        if not comp:
            return
        self.id_edicion_ce= competencia_id
        self.in_codigo_ce.setText(comp["codigo"])
        self.in_descripcion_ce.setText(comp["descripcion"])
        idx_fund= self.combo_fundamental_ce.findData(comp["competencia_fundamental"] or "")
        self.combo_fundamental_ce.setCurrentIndex(idx_fund if idx_fund >= 0 else 0)
        self.spin_orden_ce.setValue(comp["orden"] or 1)
        activar_modo_edicion(self.in_codigo_ce,
                             f"Editando competencia: {comp['codigo'] or ''}")

    def _eliminar_competencia_curriculo(self):
        if not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                             "Solo un rol gerencial puede modificar el currículo.", self)
            return
        fila= self.tabla_curriculo.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una competencia de la tabla.", self)
            return
        competencia_id= self.tabla_curriculo.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        if mostrar_mensaje("pregunta", "Confirmar",
                            "¿Eliminar esta Competencia Específica? También se eliminarán sus Indicadores "
                            "de Logro y se desvinculará de cualquier evidencia ya registrada.", self)\
                != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM competencias_especificas WHERE id=?", (competencia_id,))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", "Eliminó Competencia Específica",
                            self.main_window.usuario_actual, str(competencia_id))
        self._limpiar_form_ce()
        self._cargar_competencias_curriculo()

    def _abrir_indicadores_curriculo(self):
        fila= self.tabla_curriculo.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una competencia de la tabla.", self)
            return
        competencia_id= self.tabla_curriculo.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        codigo_ce= self.tabla_curriculo.item(fila, 0).text()
        dialogo= DialogoIndicadoresLogro(competencia_id, codigo_ce, tiene_acceso_gerencial(self.main_window), self)
        dialogo.exec()
        self._cargar_competencias_curriculo()

    #---------------- NOTAS POR COMPETENCIA (auto-calculadas desde evidencias) ----------------
    def _tab_competencias_especificas(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(16)
        aviso= QLabel("Notas por Competencia Específica: se calculan automáticamente promediando (según "
                       "el método de cálculo configurado) las evidencias que vinculaste a cada CE en la "
                       "pestaña Registrar Calificación. Puedes agregar una observación por competencia; "
                       "la nota se recalcula con el botón .")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)

        self.lbl_filtro_especialidad_competencias, self.combo_filtro_especialidad_competencias,\
            self.lbl_filtro_carrera_competencias, self.combo_filtro_carrera_competencias =\
            self._crear_combos_filtro_tecnico(self._cargar_estudiantes_competencias)

        self.combo_curso_competencias= QComboBox()
        self.combo_curso_competencias.currentIndexChanged.connect(
            lambda: (self._filtrar_seccion_por_curso_corto(self.combo_curso_competencias,
                                                      self.combo_seccion_competencias),
                      self._cargar_estudiantes_competencias()))
        self.combo_seccion_competencias= QComboBox()
        self.combo_seccion_competencias.currentIndexChanged.connect(self._cargar_estudiantes_competencias)

        self._reemplazar_por_filtros(l, "competencias", "Filtros de Notas por Competencia",
            [(self.lbl_filtro_especialidad_competencias, self.combo_filtro_especialidad_competencias),
             (self.lbl_filtro_carrera_competencias, self.combo_filtro_carrera_competencias),
             ("Curso:", self.combo_curso_competencias),
             ("Sección:", self.combo_seccion_competencias)])
        self._conectar_resumen_filtros("competencias", [
            ("Curso", self.combo_curso_competencias), ("Sección", self.combo_seccion_competencias),
            ("Área Técnica", self.combo_filtro_especialidad_competencias),
            ("Carrera", self.combo_filtro_carrera_competencias)])

        fila_filtro= QGridLayout()
        fila_filtro.setHorizontalSpacing(10)
        fila_filtro.setVerticalSpacing(8)
        self.combo_estudiante_competencias= QComboBox()
        conectar_tooltip_seleccion(self.combo_estudiante_competencias, "Estudiante cuyas notas por competencia se registran")
        fila_filtro.addWidget(QLabel("Estudiante:"), 0, 0)
        fila_filtro.addWidget(self.combo_estudiante_competencias, 0, 1)
        self.combo_materia_competencias= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_competencias, "Materia cuyas competencias se registran")
        fila_filtro.addWidget(QLabel("Materia:"), 0, 2)
        fila_filtro.addWidget(self.combo_materia_competencias, 0, 3)
        self.combo_periodo_competencias= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo_competencias, "Periodo académico de las notas por competencia")
        fila_filtro.addWidget(QLabel("Periodo:"), 1, 0)
        fila_filtro.addWidget(self.combo_periodo_competencias, 1, 1)
        ajustar_combo_ancho_seguro(self.combo_curso_competencias, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_seccion_competencias, min_len=11)
        ajustar_combo_ancho_seguro(self.combo_estudiante_competencias, min_len=14)
        ajustar_combo_ancho_seguro(self.combo_materia_competencias, min_len=13)
        ajustar_combo_ancho_seguro(self.combo_periodo_competencias, min_len=6)
        btn_calcular= QPushButton("Calcular")
        btn_calcular.setIcon(icono_emoji(EMOJI_NOTAS_COMPETENCIA))
        btn_calcular.setIconSize(_QSize_emoji(16, 16))
        btn_calcular.setObjectName("BtnAccionAjustar")
        btn_calcular.clicked.connect(self._generar_notas_competencias)
        fila_filtro.addWidget(btn_calcular, 1, 2, 1, 2)
        l.addLayout(fila_filtro)
        l.addSpacing(8)

        self.in_buscar_competencias= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_competencias.setPlaceholderText(
            "Buscar por competencia, nivel u observación (ignora tildes y mayúsculas)...")
        self.in_buscar_competencias.texto_buscado.connect(
            lambda t: self._filtrar_tabla_texto(self.tabla_competencias, t, (0, 2, 5)))
        l.addWidget(self.in_buscar_competencias)
        l.addSpacing(6)


        self.tabla_competencias= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_competencias)
        self.tabla_competencias.setHorizontalHeaderLabels(
            ["Competencia Específica", "Nota", "Nivel", "Evidencias", "Última Evidencia", "Observación"])
        header= self.tabla_competencias.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tabla_competencias.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_competencias.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_competencias.setAlternatingRowColors(True)
        self.tabla_competencias.verticalHeader().setVisible(False)
        self.tabla_competencias.setMinimumHeight(340)
        l.addWidget(self.tabla_competencias, 1)

        agregar_boton_pantalla_completa(
            None, [self.in_buscar_competencias, self.tabla_competencias],
            titulo= "Competencias", parent=self)


        fila_obs= QHBoxLayout()
        self.in_observacion_competencia= QLineEdit()
        limitar_campo_texto(self.in_observacion_competencia, 300)
        self.in_observacion_competencia.setPlaceholderText(
            "Observación para la competencia seleccionada arriba...")
        fila_obs.addWidget(self.in_observacion_competencia, 1)
        btn_guardar_obs= QPushButton("Guardar Observación")
        btn_guardar_obs.setIcon(icono_emoji("💾"))
        btn_guardar_obs.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_obs.setObjectName("BtnAccionAgregar")
        btn_guardar_obs.clicked.connect(self._guardar_observacion_competencia)
        fila_obs.addWidget(btn_guardar_obs)
        frame_form_obs_competencia= QWidget()
        lay_frame_form_obs_competencia= QVBoxLayout(frame_form_obs_competencia)
        lay_frame_form_obs_competencia.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_obs_competencia.addLayout(fila_obs)
        self._envolver_en_panel(l, "Registrar Observación de Competencia", frame_form_obs_competencia)
        self.tabla_competencias.itemSelectionChanged.connect(self._al_seleccionar_fila_competencia)

        self.lbl_alerta_curricular= QLabel("")
        self.lbl_alerta_curricular.setWordWrap(True)
        self.lbl_alerta_curricular.setObjectName("DescModulo")
        l.addWidget(self.lbl_alerta_curricular)
        l.addStretch(1)
        return w

    def _cargar_secciones_competencias(self):
        self._poblar_combo_curso_corto(self.combo_curso_competencias)
        self._filtrar_seccion_por_curso_corto(self.combo_curso_competencias, self.combo_seccion_competencias)

    def _cargar_estudiantes_competencias(self):
        self.combo_estudiante_competencias.clear()
        self.combo_materia_competencias.clear()
        seccion_id= self.combo_seccion_competencias.currentData()
        if seccion_id is None:
            self.combo_estudiante_competencias.addItem("Elige estudiante", None)
            _actualizar_estado_combo_estudiante(self.combo_curso_competencias, self.combo_seccion_competencias,
                                                 self.combo_estudiante_competencias)
            return
        for f in self._filtrar_por_tecnico(self._estudiantes_activos(), self.combo_filtro_especialidad_competencias,
                                            self.combo_filtro_carrera_competencias):
            if f["seccion_id"] != seccion_id:
                continue
            self.combo_estudiante_competencias.addItem(f"{f['nombre']} {f['apellidos'] or ''}".strip(), f["id"])
        for mat in self._materias_de_seccion(seccion_id):
            self.combo_materia_competencias.addItem(mat["nombre"], mat["id"])
        _actualizar_estado_combo_estudiante(self.combo_curso_competencias, self.combo_seccion_competencias,
                                             self.combo_estudiante_competencias)

    def _cargar_periodos_competencias(self):
        self.combo_periodo_competencias.clear()
        for id_periodo, nombre in self._periodos_lista():
            self.combo_periodo_competencias.addItem(nombre, id_periodo)

    def _generar_notas_competencias(self):
        estudiante_id= self.combo_estudiante_competencias.currentData()
        materia_id= self.combo_materia_competencias.currentData()
        periodo_id= self.combo_periodo_competencias.currentData()
        if estudiante_id is None or materia_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona sección, estudiante, materia y periodo.", self)
            return
        grado_id= grado_de_estudiante(estudiante_id)
        competencias= competencias_de_materia_grado(materia_id, grado_id)
        metodo, _ = self._obtener_metodo_y_minima()
        conn= obtener_conexion()
        c= conn.cursor()

        self._competencias_actuales= competencias
        self.tabla_competencias.setRowCount(len(competencias))
        sin_evidencia= []
        with tabla_pausada(self.tabla_competencias):
            for i, comp in enumerate(competencias):
                c.execute("""SELECT calificaciones.valor as valor, calificaciones.peso as peso,
                             calificaciones.descripcion as descripcion, calificaciones.categoria as categoria
                             FROM calificacion_competencia
                             JOIN calificaciones ON calificacion_competencia.calificacion_id = calificaciones.id
                             WHERE calificacion_competencia.competencia_id=? AND calificaciones.estudiante_id=?
                             AND calificaciones.periodo_id=? AND calificaciones.estado_publicacion != 'Borrador'
                             ORDER BY calificaciones.id""", (comp["id"], estudiante_id, periodo_id))
                evidencias= [dict(f) for f in c.fetchall()]
                nota= calcular_nota_final(evidencias, metodo) if evidencias else None

                c.execute("""SELECT observacion, modo_nota, fecha_evaluacion FROM competencia_periodo
                             WHERE estudiante_id=? AND competencia_id=? AND periodo_id=?""",
                          (estudiante_id, comp["id"], periodo_id))
                guardado= c.fetchone()
                observacion_guardada= guardado["observacion"] if guardado else ""

                item_nombre= QTableWidgetItem(f"{comp['codigo']} — {comp['descripcion']}")
                item_nombre.setData(Qt.ItemDataRole.UserRole, comp["id"])
                self.tabla_competencias.setItem(i, 0, item_nombre)
                self.tabla_competencias.setItem(i, 1, QTableWidgetItem(f"{nota:.2f}" if nota is not None else "—"))
                nivel= _nivel_desde_nota(nota)
                item_nivel= QTableWidgetItem(nivel)
                color_nivel= COLORES_NIVEL_DESEMPENO_RD.get(nivel)
                if color_nivel:
                    item_nivel.setForeground(QColor(color_nivel))
                self.tabla_competencias.setItem(i, 2, item_nivel)
                self.tabla_competencias.setItem(i, 3, QTableWidgetItem(str(len(evidencias))))
                self.tabla_competencias.setItem(i, 4, QTableWidgetItem(
                    evidencias[-1]["descripcion"] if evidencias else "—"))
                self.tabla_competencias.setItem(i, 5, QTableWidgetItem(observacion_guardada or ""))

                if not evidencias:
                    sin_evidencia.append(comp["codigo"])

                #Guarda/actualiza la nota consolidada automática de esta CE-período, sin pisar la observación que ya hubiera
                #escrito el docente.
                c.execute("""INSERT INTO competencia_periodo
                             (estudiante_id, competencia_id, periodo_id, nota, modo_nota, observacion,
                              fecha_evaluacion, actualizado)
                             VALUES (?,?,?,?,'Automática',?,?,?)
                             ON CONFLICT(estudiante_id, competencia_id, periodo_id) DO UPDATE SET
                                nota= excluded.nota, fecha_evaluacion=excluded.fecha_evaluacion,
                                actualizado= excluded.actualizado""",
                          (estudiante_id, comp["id"], periodo_id, nota, observacion_guardada,
                           datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        if hasattr(self, "in_buscar_competencias"):
            self._filtrar_tabla_texto(self.tabla_competencias, self.in_buscar_competencias.text(), (0, 2, 5))

        if not competencias:
            self.lbl_alerta_curricular.setText(
                "Esta materia todavía no tiene Competencias Específicas definidas para el grado de este"
                "estudiante. Defínelas en la pestaña Currículo (CE).")
        elif sin_evidencia:
            self.lbl_alerta_curricular.setText(
                "Integridad curricular:" + ", ".join(sin_evidencia) +
                " no tiene(n) ninguna evidencia vinculada en este periodo todavía.")
        else:
            self.lbl_alerta_curricular.setText("Todas las Competencias Específicas de esta materia "
                                                "tienen al menos una evidencia registrada en este periodo.")

    def _al_seleccionar_fila_competencia(self):
        fila= self.tabla_competencias.currentRow()
        if fila < 0:
            self.in_observacion_competencia.clear()
            return
        item_obs= self.tabla_competencias.item(fila, 5)
        self.in_observacion_competencia.setText(item_obs.text() if item_obs else "")

    def _guardar_observacion_competencia(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede editar observaciones.", self)
            return
        fila= self.tabla_competencias.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una competencia de la tabla.", self)
            return
        competencia_id= self.tabla_competencias.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        estudiante_id= self.combo_estudiante_competencias.currentData()
        periodo_id= self.combo_periodo_competencias.currentData()
        observacion= self.in_observacion_competencia.text().strip()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""UPDATE competencia_periodo SET observacion=?, actualizado=?
                     WHERE estudiante_id=? AND competencia_id=? AND periodo_id=?""",
                  (observacion, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   estudiante_id, competencia_id, periodo_id))
        conn.commit()
        conn.close()
        self.tabla_competencias.setItem(fila, 5, QTableWidgetItem(observacion))
        mostrar_mensaje("exito", "Guardado", "Observación de la competencia guardada.", self)

    #---------------- COMPARTIR CALIFICACIONES ENTRE DOCENTES ---------------- Un docente que imparte una materia
    #EXPORTA sus notas de una sección+periodo a un archivo .acnotas (JSON). El profesor titular de esa sección (que
    #no necesariamente da esa materia) lo IMPORTA, y las notas quedan guardadas contra sus estudiantes para poder
    #armar el boletín completo. Las filas importadas quedan de SOLO LECTURA: no se editan a mano desde la app, el
    #"registro físico" de quien las generó ya es la fuente de verdad.
    def _tab_compartir_calificaciones(self, w=None):
        w= w if w is not None else QWidget()
        l= QVBoxLayout(w)
        l.setSpacing(14)
        aviso= QLabel("Comparte calificaciones entre docentes: si tú impartes una materia, expórtala "
                       "aquí para dársela al profesor titular de la sección. Si eres titular, importa el "
                       "archivo que te compartieron para completar el boletín de tus estudiantes con "
                       "materias que no impartes tú. Las notas importadas quedan de solo lectura.")
        aviso.setWordWrap(True)
        aviso.setObjectName("DescModulo")
        l.addWidget(aviso)

        self.lbl_filtro_especialidad_compartir, self.combo_filtro_especialidad_compartir,\
            self.lbl_filtro_carrera_compartir, self.combo_filtro_carrera_compartir =\
            self._crear_combos_filtro_tecnico(lambda: None)

        #--- Exportar ---
        fila_exp= QHBoxLayout()
        fila_exp.setSpacing(10)
        self.combo_curso_compartir= QComboBox()
        self.combo_curso_compartir.currentIndexChanged.connect(
            lambda: self._filtrar_seccion_por_curso_corto(self.combo_curso_compartir, self.combo_seccion_compartir))
        self.combo_seccion_compartir= QComboBox()

        self._reemplazar_por_filtros(l, "compartir", "Filtros de Compartir Calificaciones",
            [(self.lbl_filtro_especialidad_compartir, self.combo_filtro_especialidad_compartir),
             (self.lbl_filtro_carrera_compartir, self.combo_filtro_carrera_compartir),
             ("Curso:", self.combo_curso_compartir),
             ("Sección:", self.combo_seccion_compartir)],
            subtitulo= "Curso y Sección acotan qué exportas. Área Técnica y Carrera son opcionales.")
        self._conectar_resumen_filtros("compartir", [
            ("Curso", self.combo_curso_compartir), ("Sección", self.combo_seccion_compartir),
            ("Área Técnica", self.combo_filtro_especialidad_compartir),
            ("Carrera", self.combo_filtro_carrera_compartir)])

        self.combo_materia_compartir= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_compartir, "Materia cuyas calificaciones se exportan/comparten")
        fila_exp.addWidget(QLabel("Materia:"))
        fila_exp.addWidget(self.combo_materia_compartir)
        self.combo_periodo_compartir= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo_compartir, "Periodo académico de las calificaciones a compartir")
        fila_exp.addWidget(QLabel("Periodo:"))
        fila_exp.addWidget(self.combo_periodo_compartir)
        ajustar_combo_ancho_seguro(self.combo_curso_compartir, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_seccion_compartir, min_len=10)
        ajustar_combo_ancho_seguro(self.combo_materia_compartir, min_len=12)
        ajustar_combo_ancho_seguro(self.combo_periodo_compartir, min_len=6)
        btn_exportar= QPushButton("Exportar Calificaciones (.acnotas)")
        btn_exportar.setIcon(icono_emoji("\uE002"))
        btn_exportar.setIconSize(_QSize_emoji(16, 16))
        btn_exportar.setObjectName("BtnAccionAgregar")
        btn_exportar.clicked.connect(self._exportar_paquete_calificaciones)
        frame_form_exportar= QWidget()
        lay_frame_form_exportar= QVBoxLayout(frame_form_exportar)
        lay_frame_form_exportar.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_exportar.addLayout(fila_exp)
        lay_frame_form_exportar.addWidget(btn_exportar)
        self._envolver_en_panel(l, "Exportar mis calificaciones", frame_form_exportar)

        #--- Importar ---
        info_imp= QLabel("Los estudiantes se emparejan por matrícula (el dato oficial), no por nombre, "
                           "así que solo se importan los que ya existen en tu sección con esa matrícula.")
        info_imp.setWordWrap(True)
        info_imp.setObjectName("DescModulo")
        btn_importar= QPushButton("Importar Archivo de Calificaciones (.acnotas)")
        btn_importar.setIcon(icono_emoji("\uE001"))
        btn_importar.setIconSize(_QSize_emoji(16, 16))
        btn_importar.setObjectName("BtnAccionAjustar")
        btn_importar.clicked.connect(self._importar_paquete_calificaciones)
        frame_form_importar= QWidget()
        lay_frame_form_importar= QVBoxLayout(frame_form_importar)
        lay_frame_form_importar.setContentsMargins(0, 0, 0, 0)
        lay_frame_form_importar.addWidget(info_imp)
        lay_frame_form_importar.addWidget(btn_importar)
        self._envolver_en_panel(l, "Importar calificaciones que me compartieron", frame_form_importar)

        lbl_hist= QLabel("Paquetes ya importados en este equipo")
        lbl_hist.setStyleSheet("font-weight: 600; margin-top: 6px;")
        l.addWidget(lbl_hist)
        self.in_buscar_paquetes= SearchBarCalificaciones(self, delay_ms=200)
        self.in_buscar_paquetes.setPlaceholderText(
            "Buscar por materia, sección, periodo o docente (ignora tildes y mayúsculas)...")
        self.in_buscar_paquetes.texto_buscado.connect(
            lambda t: self._filtrar_tabla_texto(self.tabla_paquetes, t, (0, 1, 2, 3)))
        l.addWidget(self.in_buscar_paquetes)
        l.addSpacing(6)


        self.tabla_paquetes= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_paquetes)
        self.tabla_paquetes.setHorizontalHeaderLabels(
            ["Materia", "Sección", "Periodo", "Exportado por", "Importado el", "Filas"])
        header= self.tabla_paquetes.horizontalHeader()
        header.setStretchLastSection(True)
        self.tabla_paquetes.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_paquetes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_paquetes.setAlternatingRowColors(True)
        self.tabla_paquetes.verticalHeader().setVisible(False)
        self.tabla_paquetes.setMinimumHeight(180)
        l.addWidget(self.tabla_paquetes, 1)
        l.addSpacing(8)

        agregar_boton_pantalla_completa(
            None, [self.in_buscar_paquetes, self.tabla_paquetes],
            titulo= "Paquetes importados", parent=self)

        btn_deshacer= QPushButton("Deshacer Importación Seleccionada")
        btn_deshacer.setIcon(icono_emoji("🗑"))
        btn_deshacer.setIconSize(_QSize_emoji(16, 16))
        btn_deshacer.setObjectName("BtnAccionEliminar")
        btn_deshacer.setToolTip("Elimina TODAS las notas que entraron con el paquete seleccionado "
                                 "(por si se importó el archivo equivocado).")
        btn_deshacer.clicked.connect(self._deshacer_paquete_importado)
        l.addWidget(btn_deshacer)
        return w

    def _cargar_secciones_compartir(self):
        self._poblar_combo_curso_corto(self.combo_curso_compartir)
        self._filtrar_seccion_por_curso_corto(self.combo_curso_compartir, self.combo_seccion_compartir)
        self.combo_materia_compartir.clear()
        for id_materia, nombre in self._materias_activas():
            self.combo_materia_compartir.addItem(nombre, id_materia)

    def _cargar_periodos_compartir(self):
        self.combo_periodo_compartir.clear()
        for id_periodo, nombre in self._periodos_lista():
            self.combo_periodo_compartir.addItem(nombre, id_periodo)

    def _exportar_paquete_calificaciones(self):
        seccion_id= self.combo_seccion_compartir.currentData()
        materia_id= self.combo_materia_compartir.currentData()
        periodo_id= self.combo_periodo_compartir.currentData()
        if seccion_id is None or materia_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Faltan datos", "Selecciona sección, materia y periodo.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT calificaciones.*, estudiantes.matricula as matricula_estudiante,
                     estudiantes.especialidad_id as _est_especialidad_id, estudiantes.carrera_id as _est_carrera_id
                     FROM calificaciones
                     JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     WHERE estudiantes.seccion_id=? AND calificaciones.materia_id=?
                     AND calificaciones.periodo_id=? AND calificaciones.estado_publicacion != 'Borrador'""",
                  (seccion_id, materia_id, periodo_id))
        filas_calif= self._filtrar_por_tecnico([dict(f) for f in c.fetchall()],
            self.combo_filtro_especialidad_compartir, self.combo_filtro_carrera_compartir,
            campo_especialidad= "_est_especialidad_id", campo_carrera="_est_carrera_id")
        if not filas_calif:
            conn.close()
            mostrar_mensaje("advertencia", "Nada que exportar",
                             "No hay calificaciones publicadas para esa sección, materia y periodo.", self)
            return
        #Adjunta las Competencias Específicas vinculadas a cada fila, con su código y descripción (no solo el id), para
        #que el archivo funcione también si el que importa todavía no tiene ese currículo cargado exactamente igual.
        for f in filas_calif:
            c.execute("""SELECT competencias_especificas.codigo, competencias_especificas.descripcion,
                         competencias_especificas.grado_id
                         FROM calificacion_competencia
                         JOIN competencias_especificas
                            ON calificacion_competencia.competencia_id = competencias_especificas.id
                         WHERE calificacion_competencia.calificacion_id=?""", (f["id"],))
            f["competencias"]= [dict(r) for r in c.fetchall()]
        c.execute("SELECT nombre FROM materias WHERE id=?", (materia_id,))
        materia_nombre= (c.fetchone() or {"nombre": "Materia"})["nombre"]
        c.execute("""SELECT (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                     FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id WHERE secciones.id=?""",
                  (seccion_id,))
        seccion_txt= (c.fetchone() or {"etiqueta": "Sección"})["etiqueta"]
        c.execute("SELECT nombre FROM periodos WHERE id=?", (periodo_id,))
        periodo_txt= (c.fetchone() or {"nombre": "Periodo"})["nombre"]
        conn.close()

        paquete_id= f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{materia_id}-{seccion_id}-{periodo_id}"
        paquete= {
            "version": 1,
            "paquete_id": paquete_id,
            "materia_nombre": materia_nombre,
            "seccion_nombre": seccion_txt,
            "periodo_nombre": periodo_txt,
            "exportado_por": self.main_window.usuario_actual,
            "fecha_exportacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notas": [
                {"matricula": f["matricula_estudiante"], "categoria": f["categoria"],
                 "descripcion": f["descripcion"], "valor": f["valor"], "peso": f["peso"],
                 "competencias": f["competencias"]}
                for f in filas_calif if f["matricula_estudiante"]
            ],
        }
        if not paquete["notas"]:
            mostrar_mensaje("advertencia", "Sin matrícula",
                             "Ninguno de estos estudiantes tiene matrícula registrada; sin ese dato no se "
                             "pueden emparejar de forma confiable al importar. Completa la matrícula en "
                             "Estudiantes antes de exportar.", self)
            return
        nombre_sugerido= f"{materia_nombre}_{seccion_txt}_{periodo_txt}.acnotas".replace(" ", "_").replace("/", "-")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Paquete de Calificaciones",
                                              nombre_sugerido, "Paquete AcaDeXI (*.acnotas)")
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8") as archivo:
                json.dump(paquete, archivo, ensure_ascii=False, indent=2)
        except OSError as e:
            mostrar_mensaje("error", "Error al guardar", f"No se pudo escribir el archivo:\n{e}", self)
            return
        registrar_auditoria("Calificaciones", "Exportó paquete de calificaciones", self.main_window.usuario_actual,
                            f"{materia_nombre} - {seccion_txt} - {periodo_txt} ({len(paquete['notas'])} notas)")
        mostrar_mensaje("exito", "Exportado",
                         f"Se exportaron {len(paquete['notas'])} calificaciones a:\n{ruta}", self)

    def _importar_paquete_calificaciones(self):
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede importar calificaciones.", self)
            return
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir Paquete de Calificaciones", "",
                                              "Paquete AcaDeXI (*.acnotas);;JSON (*.json)")
        if not ruta:
            return
        try:
            with open(ruta, "r", encoding="utf-8") as archivo:
                paquete= json.load(archivo)
        except (OSError, json.JSONDecodeError) as e:
            mostrar_mensaje("error", "Archivo inválido", f"No se pudo leer el archivo:\n{e}", self)
            return
        notas= paquete.get("notas") or []
        if not notas:
            mostrar_mensaje("advertencia", "Paquete vacío", "Este archivo no trae ninguna calificación.", self)
            return

        materia_id= self.combo_materia_compartir.currentData()
        seccion_id= self.combo_seccion_compartir.currentData()
        periodo_id= self.combo_periodo_compartir.currentData()
        if materia_id is None or seccion_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Faltan datos",
                             "Selecciona a qué Curso, Sección, Materia y Periodo de TU sistema corresponde "
                             "este paquete (arriba, en 'Exportar mis calificaciones' se usan los mismos "
                             "combos) antes de importar.", self)
            return

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, matricula FROM estudiantes WHERE seccion_id=?", (seccion_id,))
        matricula_a_id= {f["matricula"]: f["id"] for f in c.fetchall() if f["matricula"]}

        insertadas, sin_emparejar, duplicadas = 0, 0, 0
        ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exportado_por= paquete.get("exportado_por", "Desconocido")
        paquete_id= paquete.get("paquete_id") or f"import-{ahora}"
        for nota in notas:
            estudiante_id= matricula_a_id.get(nota.get("matricula"))
            if estudiante_id is None:
                sin_emparejar += 1
                continue
            #Evita duplicar si el mismo paquete ya se importó antes.
            c.execute("""SELECT id FROM calificaciones WHERE estudiante_id=? AND materia_id=? AND periodo_id=?
                         AND categoria=? AND descripcion=? AND origen_exportacion_id=?""",
                      (estudiante_id, materia_id, periodo_id, nota.get("categoria"), nota.get("descripcion"),
                       paquete_id))
            if c.fetchone():
                duplicadas += 1
                continue
            c.execute("""INSERT INTO calificaciones (estudiante_id, materia_id, periodo_id, categoria,
                         descripcion, valor, peso, estado_publicacion, solo_lectura, importado_de,
                         importado_en, origen_exportacion_id)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (estudiante_id, materia_id, periodo_id, nota.get("categoria") or "Importada",
                       nota.get("descripcion") or "", nota.get("valor") or 0, nota.get("peso") or 0,
                       "Publicada", 1, exportado_por, ahora, paquete_id))
            calificacion_id= c.lastrowid
            insertadas += 1
            #Reata el vínculo a Competencias Específicas por código+grado, si esa CE ya existe en este sistema (si no
            #existe, simplemente no se vincula: la nota se importa igual, solo que no aparecerá en Notas por Competencia).
            for comp in nota.get("competencias") or []:
                c.execute("""SELECT id FROM competencias_especificas
                             WHERE materia_id=? AND grado_id=? AND codigo=?""",
                          (materia_id, comp.get("grado_id"), comp.get("codigo")))
                comp_local= c.fetchone()
                if comp_local:
                    c.execute("""INSERT OR IGNORE INTO calificacion_competencia (calificacion_id, competencia_id)
                                 VALUES (?,?)""", (calificacion_id, comp_local["id"]))

        if insertadas:
            c.execute("""INSERT INTO paquetes_calificaciones
                         (id, materia_id, seccion_id, periodo_id, exportado_por, fecha_exportacion,
                          importado_por, fecha_importacion, cantidad_filas, nombre_archivo)
                         VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (paquete_id, materia_id, seccion_id, periodo_id, exportado_por,
                       paquete.get("fecha_exportacion", ""), self.main_window.usuario_actual, ahora,
                       insertadas, os.path.basename(ruta)))
        conn.commit()
        conn.close()

        if insertadas:
            registrar_auditoria("Calificaciones", "Importó paquete de calificaciones",
                                self.main_window.usuario_actual,
                                f"{paquete.get('materia_nombre', '')} — {insertadas} notas de {exportado_por}")
        mensaje= f"Se importaron {insertadas} calificaciones."
        if duplicadas:
            mensaje += f"\n{duplicadas} ya estaban importadas (se ignoraron)."
        if sin_emparejar:
            mensaje += (f"\n{sin_emparejar} no se pudieron emparejar: ningún estudiante de esta sección "
                        "tiene esa matrícula.")
        mostrar_mensaje("exito" if insertadas else "advertencia",
                        "Importación completada" if insertadas else "Nada importado", mensaje, self)
        self._cargar_paquetes_importados()

    def _cargar_paquetes_importados(self):
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT paquetes_calificaciones.*, materias.nombre as materia_nombre,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     periodos.nombre as periodo_nombre
                     FROM paquetes_calificaciones
                     LEFT JOIN materias ON paquetes_calificaciones.materia_id = materias.id
                     LEFT JOIN secciones ON paquetes_calificaciones.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN periodos ON paquetes_calificaciones.periodo_id = periodos.id
                     ORDER BY paquetes_calificaciones.fecha_importacion DESC""")
        filas= [dict(f) for f in c.fetchall()]
        conn.close()
        self.tabla_paquetes.setRowCount(len(filas))
        with tabla_pausada(self.tabla_paquetes):
            for i, f in enumerate(filas):
                item_materia= QTableWidgetItem(f["materia_nombre"] or "—")
                item_materia.setData(Qt.ItemDataRole.UserRole, f["id"])
                self.tabla_paquetes.setItem(i, 0, item_materia)
                self.tabla_paquetes.setItem(i, 1, QTableWidgetItem(f["seccion_nombre"] or "—"))
                self.tabla_paquetes.setItem(i, 2, QTableWidgetItem(f["periodo_nombre"] or "—"))
                self.tabla_paquetes.setItem(i, 3, QTableWidgetItem(f["exportado_por"] or "—"))
                self.tabla_paquetes.setItem(i, 4, QTableWidgetItem(f["fecha_importacion"] or "—"))
                self.tabla_paquetes.setItem(i, 5, QTableWidgetItem(str(f["cantidad_filas"])))
        if hasattr(self, "in_buscar_paquetes"):
            self._filtrar_tabla_texto(self.tabla_paquetes, self.in_buscar_paquetes.text(), (0, 1, 2, 3))

    def _deshacer_paquete_importado(self):
        if not tiene_acceso_gerencial(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                             "Solo un rol gerencial puede deshacer una importación completa.", self)
            return
        fila= self.tabla_paquetes.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un paquete de la tabla.", self)
            return
        paquete_id= self.tabla_paquetes.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        if mostrar_mensaje("pregunta", "Confirmar",
                            "¿Eliminar TODAS las calificaciones que entraron con este paquete? Esta acción "
                            "no se puede deshacer.", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM calificaciones WHERE origen_exportacion_id=?", (paquete_id,))
        eliminadas= c.rowcount
        c.execute("DELETE FROM paquetes_calificaciones WHERE id=?", (paquete_id,))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones", "Deshizo importación de paquete de calificaciones",
                            self.main_window.usuario_actual, f"{paquete_id} ({eliminadas} notas eliminadas)")
        mostrar_mensaje("exito", "Deshecho", f"Se eliminaron {eliminadas} calificaciones importadas.", self)
        self._cargar_paquetes_importados()

    def _limpiar_formulario(self):
        """Limpia el formulario de registro de calificaciones."""
        self.id_edicion= None
        self.btn_guardar.setText("Registrar Calificación")
        self.combo_curso.setCurrentIndex(0)
        self.combo_seccion.setCurrentIndex(0)
        self.combo_estudiante.setCurrentIndex(0)
        self.combo_materia.setCurrentIndex(0)
        self.combo_periodo.setCurrentIndex(0)
        self.combo_categoria.setCurrentIndex(0)
        self.in_descripcion.clear()
        self.spin_valor.setValue(0)
        self.spin_peso.setValue(0)
        if hasattr(self, "combo_estado_publicacion"):
            self.combo_estado_publicacion.setCurrentText("Publicada")
        self._ce_vinculadas_registro= []
        self._actualizar_boton_competencias_registro()
        desactivar_modo_edicion(self.in_descripcion)

    def _cargar_calificacion_seleccionada(self):
        """Carga una calificación seleccionada de la tabla en el formulario para editar."""
        fila= self.tabla_registro.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una calificación de la tabla.", self)
            return
        id_calificacion= self.tabla_registro.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT calificaciones.*, estudiantes.seccion_id
                     FROM calificaciones
                     LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     WHERE calificaciones.id=?""", (id_calificacion,))
        f= c.fetchone()
        if f is not None:
            c.execute("SELECT competencia_id FROM calificacion_competencia WHERE calificacion_id=?",
                      (id_calificacion,))
            self._ce_vinculadas_registro= [r["competencia_id"] for r in c.fetchall()]
        conn.close()
        if not f:
            return

        self.id_edicion= id_calificacion

        #Cargar combos
        self._cargar_secciones_combo()
        self._cargar_materias_combo()
        self._cargar_periodos_combo()

        #Seleccionar la sección del estudiante (sin disparar recarga automática)
        self.combo_seccion.blockSignals(True)
        idx_sec= self.combo_seccion.findData(f["seccion_id"])
        if idx_sec >= 0:
            self.combo_seccion.setCurrentIndex(idx_sec)
        self.combo_seccion.blockSignals(False)
        #Reflejar también el curso correspondiente (sin re-disparar el filtrado en cascada, que ya dejó listada la
        #sección correcta arriba).
        grado_de_seccion= next((s["grado_id"] for s in self._secciones_con_grado()
                                  if s["id"] == f["seccion_id"]), None)
        self.combo_curso.blockSignals(True)
        idx_curso= self.combo_curso.findData(grado_de_seccion)
        self.combo_curso.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
        self.combo_curso.blockSignals(False)
        self._cargar_estudiantes_combo()

        #Seleccionar el estudiante
        idx_est= self.combo_estudiante.findData(f["estudiante_id"])
        if idx_est >= 0:
            self.combo_estudiante.setCurrentIndex(idx_est)

        #Seleccionar materia
        idx_mat= self.combo_materia.findData(f["materia_id"])
        if idx_mat >= 0:
            self.combo_materia.setCurrentIndex(idx_mat)

        #Seleccionar periodo (antes se usaba findText con un campo inexistente)
        idx_per= self.combo_periodo.findData(f["periodo_id"])
        if idx_per >= 0:
            self.combo_periodo.setCurrentIndex(idx_per)

        #Seleccionar categoría
        idx_cat= self.combo_categoria.findText(f["categoria"] or "")
        if idx_cat >= 0:
            self.combo_categoria.setCurrentIndex(idx_cat)

        if hasattr(self, "combo_estado_publicacion"):
            idx_pub= self.combo_estado_publicacion.findText(
                f["estado_publicacion"] if "estado_publicacion" in f.keys() and f["estado_publicacion"] else "Publicada")
            self.combo_estado_publicacion.setCurrentIndex(idx_pub if idx_pub >= 0 else 2)
        self._actualizar_boton_competencias_registro()

        #Cargar los valores
        self.in_descripcion.setPlainText(f["descripcion"] or "")
        self.spin_valor.setValue(f["valor"] or 0)
        self.spin_peso.setValue(f["peso"] or 0)
        self.btn_guardar.setText("Actualizar Calificación")
        activar_modo_edicion(self.in_descripcion,
                             f"Editando calificación #{id_calificacion}")
    
    def refrescar(self):
        self._invalidar_cache()
        self._tabs_cargados= set()
        sistema= _sistema_calificacion_actual()
        es_dominicano= es_sistema_dominicano(sistema)
        self.tabs.setTabVisible(self.idx_tab_desempeno, es_dominicano)
        self.tabs.setTabVisible(self.idx_tab_seguimiento, es_dominicano)
        self.tabs.setTabVisible(self.idx_tab_evaluaciones_finales, es_dominicano)
        self.tabs.setTabVisible(self.idx_tab_curriculo, es_dominicano)
        self.tabs.setTabVisible(self.idx_tab_competencias_especificas, es_dominicano)
        if hasattr(self, "btn_rp"):
            self.btn_rp.setVisible(es_dominicano)
        if hasattr(self, "combo_estado_publicacion"):
            self.lbl_estado_publicacion.setVisible(es_dominicano)
            self.combo_estado_publicacion.setVisible(es_dominicano)
        if hasattr(self, "btn_vincular_competencias"):
            self.btn_vincular_competencias.setVisible(es_dominicano)
        #Solo se cargan los combos/tablas de la pestaña que el usuario está viendo ahora mismo; las demás se cargan la
        #primera vez que se les hace clic (ver _on_tab_changed). Antes, abrir el módulo disparaba ~20 consultas para
        #poblar las 6 pestañas de una vez, aunque solo se fuera a ver una.
        self._cargar_tab(self.tabs.currentIndex())
    def actualizar_tema(self):
        c= self._paleta()
        firma= (c["accent"], c["bg_panel"], c["bg_btn"])
        if self._firma_tema_aplicada == firma:
            return  #mismo tema ya aplicado: evita reconstruir el QSS sin necesidad
        self._firma_tema_aplicada= firma
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        from src.modulos.calendario import PanelDesplegable
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        #Colorear los iconos de lupa de las searchbars con el color secundario del tema, igual que hace
        #configuracion.py con su searchbar de usuarios.
        for searchbar in self.findChildren(SearchBarCalificaciones):
            searchbar.establecer_color_icono(c["txt_sec"])
        #Los widgets pintados a mano (dona, gauge, timeline, sparkline) reciben su color de texto igual que cualquier
        #otro control: no queda fijo en un tono que se vea mal si el usuario cambia a modo oscuro.
        for w in self.findChildren(GraficoDona):
            w.establecer_color_texto(c["txt_prim"], c["txt_sec"])
        for w in self.findChildren(MedidorGauge):
            w.establecer_color_texto(c["txt_prim"], c["txt_sec"])
        for w in self.findChildren(TimelineEvaluacion):
            w.establecer_color_texto(c["txt_prim"])
        for w in self.findChildren(LineaTendencia):
            w.establecer_color_texto(c["txt_sec"])

        accent_suave= _hex_a_rgba(c["accent"], 0.12)
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {c['bg_panel']};
                color: {c['txt_prim']};
                border: 1px solid {c['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QTabWidget::pane {{
                border: 1px solid {c['bg_btn']};
                border-radius: 10px;
                top: -1px;
                background-color: {c['bg_panel']};
            }}
            QFrame#PanelDashboard {{
                background-color: {_hex_a_rgba(c['accent'], 0.05)};
                border: 1px solid {_hex_a_rgba(c['accent'], 0.16)};
                border-radius: 16px;
            }}
        """)

        #Estilo de la ventana de "☰ Filtros", compartido por todas las pestañas del módulo (mismo diseño que
        #Calificaciones Técnicas). La construcción del QSS vive en _estilo_dialogo_filtros_qss() -la misma que ya se
        #aplica al crear cada diálogo (ver _crear_dialogo_filtros)- para que no puedan desincronizarse dos copias del
        #mismo estilo. Este loop solo se encarga de RE-aplicarlo cuando cambia el tema, a cualquier diálogo que ya
        #exista a esta
        #altura (los que se creen después, perezosamente, ya nacen
        #estilados por _crear_dialogo_filtros).
        estilo_dialogo_filtros= self._estilo_dialogo_filtros_qss(c)
        for nombre in ("registro", "boletin", "historial", "desempeno", "seguimiento",
                       "finales", "competencias", "compartir"):
            dialogo= getattr(self, f"dialogo_filtros_{nombre}", None)
            if dialogo is not None:
                dialogo.setStyleSheet(estilo_dialogo_filtros)
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c['accent']}, stop:1 {c['accent_hover']});
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
        #El selector de pestañas se estiliza aparte (solo self.tabs, no todo el módulo) por la misma razón que en
        #configuracion.py: un setStyleSheet en el contenedor raíz obliga a Qt a repolir cada control de las 9 pestañas,
        #aunque solo cambien unas pocas reglas de QTabBar. Mismo diseño "píldora" con degradado que usa
        #configuracion.py, para que se vea como un solo sistema visual y no como dos módulos distintos.
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
                background: {c['bg_btn']};
                color: {c['txt_sec']};
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['accent']}, stop:1 {c['accent_hover']});
                color: white;
            }}
            QTabBar::tab:!selected:hover {{
                background: {accent_suave};
                color: {c['txt_prim']};
            }}
        """ + estilo_flechas_navegacion_tabs(c['accent'], c['accent_hover'], c['bg_panel'], c['bg_btn'], accent_suave))

    def _paleta(self):
        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        tema= getattr(mw, "tema_actual", None)
        if not paletas or tema not in paletas:
            return {"accent": "#6366F1", "accent_hover": "#4F46E5", "bg_panel": "#FFFFFF",
                    "bg_btn": "#E2E8F0", "txt_prim": "#0F172A", "txt_sec": "#64748B"}
        p= paletas[tema]
        idx= 1 if getattr(mw, "modo_oscuro", False) else 0
        accent= p["btn_op_bg"][idx]
        return {"accent": accent, "accent_hover": p["btn_op_hover"][idx] if "btn_op_hover" in p else accent,
                "bg_panel": p["display_bg"][idx], "bg_btn": p["btn_num_bg"][idx],
                "txt_prim": p["text_primary"][idx], "txt_sec": p["text_secondary"][idx]}

    def hideEvent(self, event):
        super().hideEvent(event)
        #El módulo pasa a segundo plano (otra pestaña de la sidebar está activa): pausamos el 'latido' de las tarjetas
        #de alerta para no gastar ciclos de CPU en animaciones que nadie está viendo.
        for tarjeta in self._tarjetas_alerta:
            tarjeta.pausar()

    def showEvent(self, event):
        super().showEvent(event)
        for tarjeta in self._tarjetas_alerta:
            tarjeta.reanudar()