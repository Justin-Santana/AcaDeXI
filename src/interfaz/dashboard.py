from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QProgressBar,
    QDialog, QPushButton)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QSequentialAnimationGroup)
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QPixmap, QFontDatabase
from datetime import datetime, timedelta
import os
import sqlite3
from src.nucleo.bd import obtener_conexion, inicializar_bd
from src.nucleo.formato_hora import formatear_fecha_hora, obtener_formato_hora
from src.nucleo.permisos import es_profesor_restringido, obtener_profesor_id, modulo_visible
from src.interfaz.configuracion import SISTEMA_DOMINICANO
from src.nucleo.atajos import registrar_atajo
from src.interfaz.paginacion import aplicar_estructura_tabla, ajustar_anchos_columnas
from src.nucleo.iconos_emoji import (pixmap_emoji, html_icono_emoji,
                           EMOJI_PROFESOR, EMOJI_SECCIONES_GRUPOS, EMOJI_ESTUDIANTE_RIESGO,
                           EMOJI_SALUDO_DIA, EMOJI_SALUDO_NOCHE)
from src.nucleo.iconos import aplicar_icono_cabecera


#Fuente de emojis En Windows, si un QLabel con un emoji "compuesto" (con ZWJ, como 🧑‍🏫, o con selector de
#variación, como ⚠️/🌤️) usa la fuente por defecto de la UI, Qt puede terminar dibujando los glifos por separado
#en vez de la ligadura combinada: se ve "entrecortado" (dos mitades de emoji superpuestas/cortadas) en lugar de
#un solo ícono. Forzamos explícitamente una fuente de emoji real (con fallback a la fuente normal si no existe,
#p. ej. en Linux/Mac) para que esos glifos se compongan correctamente.
_FUENTES_EMOJI= ["Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji"]


def _aplicar_fuente_emoji(label, tamano_pt=None):

    fuente= label.font()
    disponibles= set(QFontDatabase.families())
    familias= [fam for fam in _FUENTES_EMOJI if fam in disponibles] or _FUENTES_EMOJI[:1]
    familias.append(fuente.family())
    fuente.setFamilies(familias)
    if tamano_pt:
        fuente.setPointSize(tamano_pt)
    label.setFont(fuente)


#Utilidades de color
def _hex_a_rgba(hex_color, alpha):

    hex_color= hex_color.lstrip("#")
    #r, g, b: componentes rojo, verde y azul (0-255) leídos del color hexadecimal de 6 dígitos.
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _color_por_umbral_asistencia(valor):

    if valor >= 85:
        return "#10B981"
    if valor >= 60:
        return "#F59E0B"
    return "#EF4444"


_COLORES_MODULO= {
    "Estudiantes": "#6366F1",
    "Profesores": "#0D9488",
    "Personal": "#0D9488",
    "Materias": "#8B5CF6",
    "Secciones": "#F59E0B",
    "Asistencia": "#10B981",
    "Calificaciones": "#EC4899",
    "Configuración": "#64748B",
    "Configuracion": "#64748B",
    "Sistema": "#475569",
    "Horario": "#3B82F6",
    "Calendario": "#3B82F6",
    "Observaciones": "#F97316",
    "Banco de Tareas": "#14B8A6",
    "Reportes": "#0891B2",
    "Sincronización": "#0EA5E9",
}
_PALETA_MODULO_RESPALDO= ["#6366F1", "#0D9488", "#8B5CF6", "#F59E0B",
                           "#10B981", "#EC4899", "#3B82F6", "#F97316"]


def _color_para_modulo(nombre):

    if nombre in _COLORES_MODULO:
        return _COLORES_MODULO[nombre]
    idx= sum(ord(ch) for ch in (nombre or "?")) % len(_PALETA_MODULO_RESPALDO)
    return _PALETA_MODULO_RESPALDO[idx]


#Widgets visuales personalizados
#Punto circular animado (respira) que indica datos en vivo.
class PuntoPulso(QWidget):

    def __init__(self, color="#22C55E", diametro=9, parent=None):

        super().__init__(parent)
        self._color= QColor(color)
        self._diametro= diametro
        self.setFixedSize(diametro, diametro)
        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(1.0)
        self.setGraphicsEffect(self._efecto)

        self._anim= QSequentialAnimationGroup(self)
        subir= QPropertyAnimation(self._efecto, b"opacity")
        subir.setStartValue(0.35)
        subir.setEndValue(1.0)
        subir.setDuration(900)
        subir.setEasingCurve(QEasingCurve.Type.InOutSine)
        bajar= QPropertyAnimation(self._efecto, b"opacity")
        bajar.setStartValue(1.0)
        bajar.setEndValue(0.35)
        bajar.setDuration(900)
        bajar.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.addAnimation(subir)
        self._anim.addAnimation(bajar)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def poner_color(self, color):

        self._color= QColor(color)
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(0, 0, self._diametro, self._diametro)


#Tarjeta KPI con insignia de color, valor animado, tendencia y elevación al pasar el mouse.
class TarjetaIndicador(QFrame):

    def __init__(self, icono, titulo, color_acento="#6366F1", sufijo="", decimales=0,
                 invertir_tendencia= False, al_click=None, parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaIndicadorViva")
        self._icono= icono
        self._color_acento= color_acento
        self._sufijo= sufijo
        self._decimales= decimales
        self._invertir= invertir_tendencia
        self._valor_actual= 0.0
        self._inicializada= False
        self._paleta= None
        self._al_click= al_click
        if al_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setMinimumHeight(122)

        self._sombra= QGraphicsDropShadowEffect(self)
        self._sombra.setBlurRadius(16)
        self._sombra.setOffset(0, 5)
        self._sombra.setColor(QColor(0, 0, 0, 55))
        self.setGraphicsEffect(self._sombra)

        raiz= QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 14)
        raiz.setSpacing(8)

        fila_top= QHBoxLayout()
        fila_top.setSpacing(6)
        self.lbl_badge= QLabel()
        self.lbl_badge.setPixmap(pixmap_emoji(icono, 30))
        self.lbl_badge.setFixedSize(40, 40)
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila_top.addWidget(self.lbl_badge)
        fila_top.addStretch()
        self.lbl_tendencia= QLabel("")
        self.lbl_tendencia.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.lbl_tendencia.setStyleSheet("background: transparent;")
        fila_top.addWidget(self.lbl_tendencia)
        raiz.addLayout(fila_top)

        self.lbl_valor= QLabel(self._formatear(0))
        f_valor= self.lbl_valor.font()
        f_valor.setPointSize(22)
        f_valor.setBold(True)
        self.lbl_valor.setFont(f_valor)
        raiz.addWidget(self.lbl_valor)

        self.lbl_titulo= QLabel(titulo)
        raiz.addWidget(self.lbl_titulo)

        self._anim= QVariantAnimation(self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar_tic)

    def _formatear(self, valor):

        if self._decimales:
            return f"{valor:.{self._decimales}f}{self._sufijo}"
        return f"{int(round(valor))}{self._sufijo}"

    def _al_animar_tic(self, valor):

        self._valor_actual= valor
        self.lbl_valor.setText(self._formatear(valor))

    def poner_color_acento(self, color):

        if color and color != self._color_acento:
            self._color_acento= color
            self._pintar_acento()

    def poner_titulo(self, texto):

        self.lbl_titulo.setText(texto)

    def poner_icono(self, icono):

        self._icono= icono
        self.lbl_badge.setPixmap(pixmap_emoji(icono, 30))

    def actualizar(self, nuevo_valor, color_acento=None):

        if color_acento:
            self.poner_color_acento(color_acento)

        anterior= self._valor_actual
        primera_vez= not self._inicializada
        self._inicializada= True

        if not primera_vez:
            diff= round(nuevo_valor - anterior, self._decimales)
            if diff != 0:
                es_mejora= (diff > 0) if not self._invertir else (diff < 0)
                color_tend= "#10B981" if es_mejora else "#EF4444"
                flecha= "▲" if diff > 0 else "▼"
                texto_diff= f"{abs(diff):.{self._decimales}f}" if self._decimales else f"{int(abs(diff))}"
                self.lbl_tendencia.setText(f"{flecha} {texto_diff}")
                self.lbl_tendencia.setStyleSheet(
                    f"color: {color_tend}; font-size: 11px; font-weight: 800; background: transparent;")
            else:
                self.lbl_tendencia.setText("")

        self._anim.stop()
        self._anim.setStartValue(float(anterior))
        self._anim.setEndValue(float(nuevo_valor))
        self._anim.start()

    def aplicar_paleta(self, bg_panel, borde, txt_prim, txt_sec, modo_oscuro):

        self._paleta= (bg_panel, borde, txt_prim, txt_sec, modo_oscuro)
        self._pintar_normal()
        self.lbl_titulo.setStyleSheet(
            f"color: {txt_sec}; font-size: 12px; font-weight: 600; background: transparent;")
        self._pintar_acento()

    def _pintar_normal(self):

        if not self._paleta:
            return
        bg_panel, borde, _txt_prim, _txt_sec, _modo_oscuro= self._paleta
        self.setStyleSheet(f"""
            QFrame#TarjetaIndicadorViva {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-radius: 14px;
            }}
        """)

    def _pintar_hover(self):

        if not self._paleta:
            return
        bg_panel, _borde, _txt_prim, _txt_sec, modo_oscuro= self._paleta
        #Tinte del acento sobre el fondo + borde grueso del color del acento:
        #así el hover se nota igual de bien en modo oscuro que en modo claro, en vez de depender solo de la sombra (que
        #en modo claro casi no se ve).
        alpha_fondo= 0.16 if modo_oscuro else 0.10
        fondo_hover= _hex_a_rgba(self._color_acento, alpha_fondo)
        self.setStyleSheet(f"""
            QFrame#TarjetaIndicadorViva {{
                background-color: {fondo_hover};
                border: 2px solid {self._color_acento};
                border-radius: 14px;
            }}
        """)

    def _pintar_acento(self):

        modo_oscuro= self._paleta[4] if self._paleta else True
        alpha= 0.26 if modo_oscuro else 0.14
        badge_bg= _hex_a_rgba(self._color_acento, alpha)
        self.lbl_badge.setStyleSheet(
            f"background-color: {badge_bg}; border-radius: 20px; color: {self._color_acento};")
        self.lbl_valor.setStyleSheet(f"color: {self._color_acento}; background: transparent;")

    def enterEvent(self, evento):

        if self._al_click:
            self._pintar_hover()
            self._animar_sombra(34, offset_y=9, alpha=110)
        else:
            self._animar_sombra(20)
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        if self._al_click:
            self._pintar_normal()
            self._animar_sombra(16, offset_y=5, alpha=55)
        else:
            self._animar_sombra(16)
        super().leaveEvent(evento)

    def mousePressEvent(self, evento):

        if self._al_click and evento.button() == Qt.MouseButton.LeftButton:
            self._al_click()
        super().mousePressEvent(evento)

    def _animar_sombra(self, destino_blur, offset_y=None, alpha=None):

        anim_blur= QPropertyAnimation(self._sombra, b"blurRadius", self)
        anim_blur.setDuration(220)
        anim_blur.setStartValue(self._sombra.blurRadius())
        anim_blur.setEndValue(destino_blur)
        anim_blur.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        if offset_y is not None:
            anim_off= QPropertyAnimation(self._sombra, b"offset", self)
            anim_off.setDuration(220)
            anim_off.setStartValue(self._sombra.offset())
            anim_off.setEndValue(QPointF(0, offset_y))
            anim_off.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        if alpha is not None:
            color_actual= self._sombra.color()
            color_nuevo= QColor(color_actual)
            color_nuevo.setAlpha(alpha)
            self._sombra.setColor(color_nuevo)


#Anillo de progreso circular animado para mostrar un porcentaje.
class AnilloProgreso(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._valor= 0.0
        self._color= QColor("#10B981")
        self._pista= QColor("#E2E8F0")
        self._texto_color= QColor("#0F172A")
        self.setMinimumSize(150, 150)

        self._anim= QVariantAnimation(self)
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_tic)

    def _al_tic(self, valor):

        self._valor= valor
        self.update()

    def poner_valor(self, nuevo_valor, color=None):

        if color:
            self._color= QColor(color)
        self._anim.stop()
        self._anim.setStartValue(float(self._valor))
        self._anim.setEndValue(float(max(0, min(100, nuevo_valor))))
        self._anim.start()

    def poner_colores(self, color_pista, color_texto):

        self._pista= QColor(color_pista)
        self._texto_color= QColor(color_texto)
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        lado= min(self.width(), self.height()) - 16
        if lado <= 0:
            return
        rect= QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        grosor= max(10, int(lado * 0.11))
        rect_arco= rect.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2)

        pen_fondo= QPen(self._pista)
        pen_fondo.setWidth(grosor)
        pen_fondo.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fondo)
        painter.drawArc(rect_arco, 0, 360 * 16)

        if self._valor > 0:
            pen_valor= QPen(self._color)
            pen_valor.setWidth(grosor)
            pen_valor.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_valor)
            angulo= int(360 * 16 * (self._valor / 100))
            painter.drawArc(rect_arco, 90 * 16, -angulo)

        painter.setPen(self._texto_color)
        fuente= painter.font()
        fuente.setPointSize(max(12, int(lado * 0.16)))
        fuente.setBold(True)
        painter.setFont(fuente)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._valor:.0f}%")


#Gráfico de barras animado con la tendencia de asistencia de los últimos días.
class GraficoBarrasSemanal(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._datos= []
        self._progreso= 0.0
        self._color_texto= QColor("#64748B")
        self._color_texto_prim= QColor("#0F172A")
        self.setMinimumHeight(150)

        self._anim= QVariantAnimation(self)
        self._anim.setDuration(750)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_tic)

    def _al_tic(self, valor):

        self._progreso= valor
        self.update()

    def poner_datos(self, datos):

        self._datos= datos
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def poner_colores(self, color_texto, color_texto_prim):

        self._color_texto= QColor(color_texto)
        self._color_texto_prim= QColor(color_texto_prim)
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._datos:
            return

        margen_inf= 20
        margen_sup= 24
        alto_disponible= self.height() - margen_inf - margen_sup
        cantidad= len(self._datos)
        espacio= 10
        ancho_barra= max(12, (self.width() - espacio * (cantidad + 1)) / cantidad)

        x= espacio
        for etiqueta, valor in self._datos:
            valor_clamp= max(0, min(100, valor))
            h= alto_disponible * (valor_clamp / 100) * self._progreso
            pos_y= margen_sup + (alto_disponible - h)
            color= QColor(_color_por_umbral_asistencia(valor_clamp))

            path= QPainterPath()
            radio= min(6, ancho_barra / 2)
            path.addRoundedRect(QRectF(x, pos_y, ancho_barra, max(h, 2)), radio, radio)
            painter.fillPath(path, QBrush(color))

            if valor > 0 and self._progreso > 0.85:
                painter.setPen(self._color_texto_prim)
                f_valor= painter.font()
                f_valor.setPointSize(8)
                f_valor.setBold(True)
                painter.setFont(f_valor)
                rect_valor= QRectF(x - 4, pos_y - 16, ancho_barra + 8, 14)
                painter.drawText(rect_valor, Qt.AlignmentFlag.AlignCenter, f"{valor:.0f}")

            painter.setPen(self._color_texto)
            f_label= painter.font()
            f_label.setPointSize(9)
            f_label.setBold(False)
            painter.setFont(f_label)
            rect_label= QRectF(x - 4, self.height() - margen_inf + 3, ancho_barra + 8, margen_inf - 3)
            painter.drawText(rect_label, Qt.AlignmentFlag.AlignCenter, etiqueta)

            x += ancho_barra + espacio


#Una fila 'Sección — barra animada — %' para el detalle de asistencia.
class FilaAsistenciaSeccion(QWidget):

    def __init__(self, nombre, parent=None):

        super().__init__(parent)
        fila= QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)

        self.lbl_nombre= QLabel(nombre)
        self.lbl_nombre.setFixedWidth(170)
        self.lbl_nombre.setToolTip(nombre)
        fila.addWidget(self.lbl_nombre)

        self.barra= QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(14)
        fila.addWidget(self.barra, 1)

        self.lbl_valor= QLabel("0%")
        self.lbl_valor.setFixedWidth(44)
        self.lbl_valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fila.addWidget(self.lbl_valor)

        self._anim= QPropertyAnimation(self.barra, b"value", self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def poner_nombre(self, nombre):

        self.lbl_nombre.setText(nombre)
        self.lbl_nombre.setToolTip(nombre)

    def aplicar_color_nombre(self, color_texto, bg_panel=None, borde=None):

        #lbl_nombre tiene su propio tooltip (el nombre puede venir truncado por el ancho fijo de 170px). Como este
        #QLabel recibe su propio
        #setStyleSheet() aquí abajo, eso reemplaza -para el tooltip de ESTE
        #widget- cualquier regla QToolTip heredada de la ventana principal. Sin repetir el bloque QToolTip aquí, el
        #tooltip caía al estilo nativo de Qt (fondo negro/gris, sin bordes), inconsistente con el resto de AcaDeXI. Ver
        #el mismo patrón en calendario.py, banco_tareas.py, calificaciones.py, etc.
        bg_panel= bg_panel or "#1E293B"
        borde= borde or "#334155"
        self.lbl_nombre.setStyleSheet(f"""
            QLabel {{
                color: {color_texto};
                background: transparent;
            }}
            QToolTip {{
                background-color: {bg_panel};
                color: {color_texto};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)

    def poner_valor(self, pct, color_texto="#0F172A"):

        color= _color_por_umbral_asistencia(pct)
        self.barra.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(148, 163, 184, 0.28);
                border: none;
                border-radius: 7px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 7px;
            }}
        """)
        self.lbl_valor.setText(f"{pct:.0f}%")
        self.lbl_valor.setStyleSheet(f"color: {color}; font-weight: 700; background: transparent;")
        self.lbl_nombre.setStyleSheet(f"color: {color_texto}; background: transparent;")
        self._anim.stop()
        self._anim.setStartValue(self.barra.value())
        self._anim.setEndValue(int(round(max(0, min(100, pct)))))
        self._anim.start()


#Lista de secciones/cursos con su % de asistencia, cada una con su propia
#barra animada. Reutiliza las filas existentes entre refrescos (por clave)
#para que la animación parta del valor anterior en vez de reiniciar en 0.
class PanelDetalleAsistencia(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._layout= QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(9)
        self._filas= {}
        self._color_texto= "#0F172A"
        self._bg_panel= None
        self._borde= None

    #datos: lista de tuplas (clave, nombre, porcentaje), en el orden deseado.
    def poner_datos(self, datos):

        claves_nuevas= [dato[0] for dato in datos]
        for clave in list(self._filas):
            if clave not in claves_nuevas:
                fila= self._filas.pop(clave)
                self._layout.removeWidget(fila)
                fila.deleteLater()
        for i, (clave, nombre, pct) in enumerate(datos):
            fila= self._filas.get(clave)
            if fila is None:
                fila= FilaAsistenciaSeccion(nombre)
                self._filas[clave]= fila
                self._layout.insertWidget(i, fila)
            else:
                fila.poner_nombre(nombre)
                self._layout.insertWidget(i, fila)
            fila.poner_valor(pct, self._color_texto)
            fila.aplicar_color_nombre(self._color_texto, self._bg_panel, self._borde)

    def poner_colores(self, color_texto, bg_panel=None, borde=None):

        self._color_texto= color_texto
        self._bg_panel= bg_panel
        self._borde= borde
        for fila in self._filas.values():
            fila.aplicar_color_nombre(color_texto, bg_panel, borde)


#Helpers de celdas para la tabla de actividad (QTableWidgetItem simples: setCellWidget() daba filas con alto 0
#en este entorno, así que se evita por completo)
def _item_modulo(modulo, color):

    item= QTableWidgetItem(f"●  {modulo}")
    item.setForeground(QColor(color))
    fuente= item.font()
    fuente.setBold(True)
    item.setFont(fuente)
    return item


def _item_usuario(nombre):

    nombre= nombre or "Sistema"
    return QTableWidgetItem(nombre)


#Módulo principal del dashboard
class ModuloDashboard(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._colores_actuales= None
        self._tarjetas= []
        self._construir_ui()
        self.actualizar_tema()
        self._actualizar_reloj()
        self.refrescar()

        self._timer_reloj= QTimer(self)
        self._timer_reloj.timeout.connect(self._actualizar_reloj)
        self._timer_reloj.start(1000)

        self._timer_autorefresh= QTimer(self)
        self._timer_autorefresh.timeout.connect(self._autorefrescar)
        self._timer_autorefresh.start(120000)

        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Dashboard"
        registrar_atajo(self, self.main_window, "F5", "Actualizar panel", self.refrescar)

    #Ahorro de recursos en segundo plano El reloj en vivo se recalcula y repinta cada segundo para siempre mientras
    #la app viva, aunque la ventana esté oculta en la bandeja del sistema y nadie pueda verlo. MainWindow llama a
    #estos métodos desde su hideEvent/showEvent (ver main.py) para que ese trabajo se detenga por completo mientras
    #la app está en segundo plano, en vez de solo confiar en el chequeo de isVisible() del autorefresh (que evita
    #la consulta a la BD, pero no evita que el timer del reloj siga despertando el proceso 60 veces por minuto).
    def pausar_actualizaciones(self):

        self._timer_reloj.stop()
        self._timer_autorefresh.stop()

    def reanudar_actualizaciones(self):

        if not self._timer_reloj.isActive():
            self._actualizar_reloj()
            self._timer_reloj.start(1000)
        if not self._timer_autorefresh.isActive():
            self._timer_autorefresh.start(120000)
            self._autorefrescar()

    #Construcción de interfaz
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
        disposicion.setSpacing(20)

        #--- Encabezado: título + saludo/reloj en vivo ---
        fila_header= QHBoxLayout()
        fila_header.setSpacing(12)

        #Logo de la institución (si Configuración tiene uno cargado). Se actualiza en cada refrescar() por si el
        #Director lo cambia mientras la app está abierta.
        self.lbl_logo_institucion= QLabel()
        self.lbl_logo_institucion.setFixedSize(100, 100)
        self.lbl_logo_institucion.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo_institucion.setScaledContents(False)
        self.lbl_logo_institucion.setVisible(False)
        fila_header.addWidget(self.lbl_logo_institucion)

        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(2)
        self.lbl_bienvenida= QLabel("Dashboard")
        self.lbl_bienvenida.setObjectName("TituloModulo")
        _aplicar_fuente_emoji(self.lbl_bienvenida)
        bloque_titulo.addWidget(self.lbl_bienvenida)
        self.lbl_institucion= QLabel("")
        self.lbl_institucion.setObjectName("DescModulo")
        bloque_titulo.addWidget(self.lbl_institucion)
        fila_header.addLayout(bloque_titulo, 1)

        bloque_reloj= QVBoxLayout()
        bloque_reloj.setSpacing(3)
        self.lbl_saludo= QLabel("")
        self.lbl_saludo.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_saludo.setTextFormat(Qt.TextFormat.RichText)
        bloque_reloj.addWidget(self.lbl_saludo)
        self.lbl_reloj= QLabel("")
        self.lbl_reloj.setAlignment(Qt.AlignmentFlag.AlignRight)
        bloque_reloj.addWidget(self.lbl_reloj)
        fila_header.addLayout(bloque_reloj)

        disposicion.addLayout(fila_header)

        #--- Tarjetas KPI (clicables: llevan al módulo correspondiente) ---
        grid= QGridLayout()
        grid.setSpacing(16)
        self.tarjeta_estudiantes= TarjetaIndicador("🎓", "Estudiantes Activos", "#6366F1",
                                                      #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                                                      al_click= lambda: self._ir_a_modulo("Estudiantes"))
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._al_click_profesores= lambda: self._ir_a_modulo("Profesores")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._al_click_horario_docente= lambda: self._ir_a_modulo("Horario")
        self.tarjeta_profesores= TarjetaIndicador(EMOJI_PROFESOR, "Profesores Activos", "#0D9488",
                                                     al_click= self._al_click_profesores)
        self.tarjeta_materias= TarjetaIndicador("📘", "Materias", "#8B5CF6",
                                                   #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                                                   al_click= lambda: self._ir_a_modulo("Materias"))
        #"Secciones/Grupos" (institucional) va a Materias, que tiene la pestaña "Cursos y Secciones". Para el docente
        #("Mis Secciones") NO reutilizamos ese mismo destino: "Mis Materias" ya muestra su horario semanal completo,
        #así que aterrizar ahí también sería indistinguible de "Mis Clases (semanales)". En su lugar, "Mis Secciones"
        #lleva a "Mis Estudiantes" con el filtro de Curso/Sección abierto de una vez: para un docente, "ver sus
        #secciones" es, en la práctica, ver quién está en cada una.
        self._al_click_secciones= lambda: self._ir_a_modulo("Materias")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._al_click_secciones_docente= lambda: self._ir_a_modulo("Mis Estudiantes", pestana="secciones")
        self.tarjeta_secciones= TarjetaIndicador(EMOJI_SECCIONES_GRUPOS, "Secciones/Grupos", "#F59E0B",
                                                    al_click= self._al_click_secciones)
        self.tarjeta_asistencia_hoy= TarjetaIndicador("✅", "Asistencia Hoy", "#10B981",
                                                         sufijo= "%", decimales=1,
                                                         #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                                                         al_click= lambda: self._ir_a_modulo("Asistencia"))
        self.tarjeta_riesgo= TarjetaIndicador(EMOJI_ESTUDIANTE_RIESGO, "Estudiantes en Riesgo", "#EF4444",
                                                invertir_tendencia= True,
                                                #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
                                                al_click= lambda: self._ir_a_modulo(
                                                    "Reportes", pestana="riesgo"))
        self._tarjetas= [self.tarjeta_estudiantes, self.tarjeta_profesores, self.tarjeta_materias,
                           self.tarjeta_secciones, self.tarjeta_asistencia_hoy, self.tarjeta_riesgo]
        self._modo_tarjetas_docente= None  #None = aún no determinado; True/False = último modo aplicado
        grid.addWidget(self.tarjeta_estudiantes, 0, 0)
        grid.addWidget(self.tarjeta_profesores, 0, 1)
        grid.addWidget(self.tarjeta_materias, 0, 2)
        grid.addWidget(self.tarjeta_secciones, 1, 0)
        grid.addWidget(self.tarjeta_asistencia_hoy, 1, 1)
        grid.addWidget(self.tarjeta_riesgo, 1, 2)
        disposicion.addLayout(grid)

        #--- Panel resumen: anillo de asistencia + tendencia semanal ---
        self.panel_resumen= QFrame()
        self.panel_resumen.setObjectName("PanelResumen")
        fila_resumen= QHBoxLayout(self.panel_resumen)
        fila_resumen.setContentsMargins(24, 20, 24, 18)
        fila_resumen.setSpacing(28)

        bloque_anillo= QVBoxLayout()
        bloque_anillo.setSpacing(8)
        self.lbl_titulo_anillo= QLabel("Asistencia de hoy")
        bloque_anillo.addWidget(self.lbl_titulo_anillo)
        fila_anillo= QHBoxLayout()
        fila_anillo.addStretch()
        self.anillo_asistencia= AnilloProgreso()
        fila_anillo.addWidget(self.anillo_asistencia)
        fila_anillo.addStretch()
        bloque_anillo.addLayout(fila_anillo)
        bloque_anillo.addStretch()
        fila_resumen.addLayout(bloque_anillo)

        self.linea_separadora= QFrame()
        self.linea_separadora.setFixedWidth(1)
        fila_resumen.addWidget(self.linea_separadora)

        bloque_semana= QVBoxLayout()
        bloque_semana.setSpacing(8)
        self.lbl_titulo_semana= QLabel("Tendencia de asistencia · últimos 7 días")
        bloque_semana.addWidget(self.lbl_titulo_semana)
        self.grafico_semanal= GraficoBarrasSemanal()
        bloque_semana.addWidget(self.grafico_semanal, 1)
        self.lbl_promedio_semanal= QLabel("")
        bloque_semana.addWidget(self.lbl_promedio_semanal)
        fila_resumen.addLayout(bloque_semana, 1)

        disposicion.addWidget(self.panel_resumen)

        #--- Panel: asistencia detallada por curso/sección (esta semana) ---
        self.panel_detalle= QFrame()
        self.panel_detalle.setObjectName("PanelResumen")
        layout_detalle= QVBoxLayout(self.panel_detalle)
        layout_detalle.setContentsMargins(24, 20, 24, 20)
        layout_detalle.setSpacing(10)
        self.lbl_titulo_detalle= QLabel("Asistencia por curso/sección · esta semana")
        _aplicar_fuente_emoji(self.lbl_titulo_detalle)
        layout_detalle.addWidget(self.lbl_titulo_detalle)
        self.panel_barras_seccion= PanelDetalleAsistencia()
        layout_detalle.addWidget(self.panel_barras_seccion)
        self.lbl_detalle_vacio= QLabel("Aún no hay asistencia registrada esta semana.")
        self.lbl_detalle_vacio.setObjectName("DescModulo")
        self.lbl_detalle_vacio.setVisible(False)
        layout_detalle.addWidget(self.lbl_detalle_vacio)
        disposicion.addWidget(self.panel_detalle)

        #--- Panel: últimas acciones del sistema (auditoría, máx. 10) ---
        self.panel_actividad= QFrame()
        self.panel_actividad.setObjectName("PanelResumen")
        layout_actividad= QVBoxLayout(self.panel_actividad)
        layout_actividad.setContentsMargins(24, 20, 24, 20)
        layout_actividad.setSpacing(10)
        self.lbl_titulo_actividad= QLabel("Últimas Acciones del Sistema")
        _aplicar_fuente_emoji(self.lbl_titulo_actividad)
        layout_actividad.addWidget(self.lbl_titulo_actividad)
        self.tabla_actividad= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_actividad)
        self.tabla_actividad.setHorizontalHeaderLabels(["Fecha", "Módulo", "Acción", "Usuario"])
        header_act= self.tabla_actividad.horizontalHeader()
        header_act.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_act.setStretchLastSection(True)
        header_act.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_actividad.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabla_actividad.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_actividad.setAlternatingRowColors(True)
        self.tabla_actividad.setMinimumHeight(320)
        self.tabla_actividad.verticalHeader().setVisible(False)
        layout_actividad.addWidget(self.tabla_actividad, 1)
        disposicion.addWidget(self.panel_actividad)

        disposicion.addStretch()

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    def _ir_a_modulo(self, nombre, pestana=None):

        mw= self.main_window
        #Los docentes (rol Profesor) no tienen acceso a la gestión completa de Profesores/Estudiantes/Materias: su
        #información propia vive en el Modo
        #Docente (Mis Estudiantes / Mis Materias).
        if es_profesor_restringido(mw):
            if nombre == "Profesores":
                return
            if nombre == "Estudiantes":
                nombre= "Mis Estudiantes"
            elif nombre == "Materias":
                nombre= "Mis Materias"
        modulos= getattr(mw, "modulos", None)
        if not modulos or nombre not in modulos or not hasattr(mw, "nav_list"):
            return
        if pestana:
            #El módulo destino (p. ej. Reportes) lee y consume este "banderín" en su propio showEvent para saltar directo a
            #la pestaña indicada, tanto para el Dashboard institucional como para el de Docentes.
            mw._pestana_pendiente_dashboard= pestana
        indice= modulos.index(nombre)
        if mw.nav_list.currentRow() == indice:
            #Ya estamos en ese módulo (p. ej. el sidebar no cambió de fila):
            #forzamos el cambio de vista igualmente para refrescar el contenido.
            if hasattr(mw, "cambiar_vista"):
                mw.cambiar_vista(indice)
        else:
            mw.nav_list.setCurrentRow(indice)

    #True si la institución actual es un Politécnico -o "Personalizado"
    #con el módulo Politécnico activo-, es decir, cuando además del
    #currículo académico normal (Materias) existe formación técnica
    #(Módulos Técnicos, ver politecnico.py). `_tipo_institucion` ya
    #devuelve ("Escuela", []) ante cualquier error, así que no hace
    #falta try/except aquí también.
    def _es_politecnico_activo(self):

        mw= self.main_window
        if not hasattr(mw, "_tipo_institucion"):
            return False
        tipo, personalizados= mw._tipo_institucion()
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #El selector Materias/Módulos solo aparece si, además de que la
    #institución sea de tipo Politécnico, el ROL actual de verdad tiene
    #acceso al módulo "Politécnico" del menú lateral (respeta permisos
    #recortados en Side Stepper, por ejemplo). Si no lo tiene, la tarjeta
    #se comporta exactamente como antes: rótulo "Materias" y va directo
    #a materias.py, sin ofrecer una opción que de todos modos no podría
    #usar.
    def _puede_elegir_modulos_tecnicos(self):

        mw= self.main_window
        modulos= getattr(mw, "modulos", None) or []
        if "Politécnico" not in modulos:
            return False
        rol_actual= getattr(mw, "rol_actual", None)
        return modulo_visible(rol_actual, "Politécnico")

    #Selector rápido que aparece al hacer click en la tarjeta "Materias/
    #Módulos" cuando la institución tiene ambos mundos (currículo
    #académico + formación técnica): deja elegir entre ir a Materias
    #(materias.py) o a Módulos Técnicos (politecnico.py), en vez de
    #adivinar cuál de los dos quería el usuario.
    def _mostrar_selector_materias_modulos(self):

        bg_panel, bg_borde, txt_prim, txt_sec, accent, modo_oscuro= (
            self._colores_actuales if getattr(self, "_colores_actuales", None)
            else ("#1E293B", "#334155", "#F8FAFC", "#94A3B8", "#8B5CF6", True))

        dialogo= QDialog(self)
        dialogo.setWindowTitle("Materias / Módulos")
        dialogo.setModal(True)
        dialogo.setMinimumWidth(440)
        dialogo.setStyleSheet(f"QDialog {{ background: {bg_panel}; }}")

        disposicion= QVBoxLayout(dialogo)
        disposicion.setContentsMargins(26, 24, 26, 24)
        disposicion.setSpacing(18)

        titulo= QLabel("¿A dónde querés ir?")
        titulo.setStyleSheet(
            f"color: {txt_prim}; font-size: 16px; font-weight: 700; background: transparent;")
        lbl_subtitulo= QLabel(
            "Esta institución tiene currículo académico y formación técnica por separado.")
        lbl_subtitulo.setWordWrap(True)
        lbl_subtitulo.setStyleSheet(f"color: {txt_sec}; font-size: 11.5px; background: transparent;")
        disposicion.addWidget(titulo)
        disposicion.addWidget(lbl_subtitulo)

        fila_opciones= QHBoxLayout()
        fila_opciones.setSpacing(14)
        disposicion.addLayout(fila_opciones)

        def _crear_opcion(nombre_icono, titulo_op, subtitulo_op, color):

            btn_boton= QPushButton()
            btn_boton.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_boton.setMinimumHeight(148)
            btn_boton.setStyleSheet(f"""
                QPushButton {{
                    background: {_hex_a_rgba(color, 0.16 if modo_oscuro else 0.10)};
                    color: {txt_prim};
                    border: 1.5px solid {_hex_a_rgba(color, 0.4)};
                    border-radius: 14px;
                }}
                QPushButton:hover {{
                    background: {_hex_a_rgba(color, 0.28 if modo_oscuro else 0.20)};
                    border: 1.5px solid {color};
                }}
                QPushButton:pressed {{
                    background: {_hex_a_rgba(color, 0.36 if modo_oscuro else 0.28)};
                }}
            """)
            #El contenido ya NO va en un solo setText (antes:"📘\n\nMaterias\n Currículo académico regular"): el texto se
            #recortaba con "…" y el emoji dependía de la fuente del sistema. Ahora es un layout real con el MISMO icono
            #vectorial (QPainter) que la cabecera del módulo en el menú lateral, más título y descripción en QLabels
            #propios (con wordWrap) para que SIEMPRE se vea el texto entero.
            contenido= QVBoxLayout(btn_boton)
            contenido.setContentsMargins(18, 16, 18, 16)
            contenido.setSpacing(7)
            lbl_icono= QLabel()
            lbl_icono.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            lbl_icono.setStyleSheet("background: transparent;")
            aplicar_icono_cabecera(lbl_icono, nombre_icono, tamano=36)
            contenido.addWidget(lbl_icono)
            lbl_titulo= QLabel(titulo_op)
            lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl_titulo.setWordWrap(True)
            lbl_titulo.setStyleSheet(
                f"color: {txt_prim}; font-size: 14px; font-weight: 700; background: transparent;")
            contenido.addWidget(lbl_titulo)
            lbl_sub= QLabel(subtitulo_op)
            lbl_sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl_sub.setWordWrap(True)
            lbl_sub.setStyleSheet(
                f"color: {txt_sec}; font-size: 11.5px; background: transparent;")
            contenido.addWidget(lbl_sub)
            return btn_boton

        btn_materias= _crear_opcion("Materias", "Materias", "Currículo académico regular", "#8B5CF6")
        btn_modulos= _crear_opcion("Politécnico", "Módulos Técnicos", "Formación técnica (RA)", "#0D9488")
        fila_opciones.addWidget(btn_materias)
        fila_opciones.addWidget(btn_modulos)

        def _ir_a_materias():

            dialogo.accept()
            self._ir_a_modulo("Materias")

        def _ir_a_modulos_tecnicos():

            dialogo.accept()
            #Pide saltar directo a la pestaña "Módulos Técnicos" (índice 1) del módulo Politécnico: el showEvent del módulo
            #consume este "banderín" apenas se muestra la vista.
            self.main_window._pestana_pendiente_politecnico= 1
            self._ir_a_modulo("Politécnico")

        btn_materias.clicked.connect(_ir_a_materias)
        btn_modulos.clicked.connect(_ir_a_modulos_tecnicos)

        dialogo.exec()

    def _actualizar_logo(self, logo_path):

        if logo_path and os.path.isfile(logo_path):
            pixmap= QPixmap(logo_path)
            if not pixmap.isNull():
                pixmap= pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
                self.lbl_logo_institucion.setPixmap(pixmap)
                self.lbl_logo_institucion.setVisible(True)
                return
        self.lbl_logo_institucion.clear()
        self.lbl_logo_institucion.setVisible(False)

    #RELOJ / SALUDO / AUTOREFRESCO
    def _actualizar_reloj(self):

        ahora= datetime.now()
        hora= ahora.hour
        #Solo 2 iconos para todo el saludo: sol (mañana + tarde, ambas "de día") y luna (noche) -el mismo criterio
        #horario de siempre, solo que ahora comparten un único icono vectorial "de día" en vez de dos emojis de sol
        #distintos (☀ para mañana, 🌤 para tarde).
        if 5 <= hora < 12:
            saludo, icono= "Buenos días", EMOJI_SALUDO_DIA
        elif 12 <= hora < 19:
            saludo, icono= "Buenas tardes", EMOJI_SALUDO_DIA
        else:
            saludo, icono= "Buenas noches", EMOJI_SALUDO_NOCHE

        dias= ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses= ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_txt= f"{dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]}"

        self.lbl_saludo.setText(f"{html_icono_emoji(icono, 18)} {saludo}")
        if obtener_formato_hora(self.main_window) == "12h":
            hora12= ahora.hour % 12 or 12
            sufijo= "a. m." if ahora.hour < 12 else "p. m."
            hora_txt= f"{hora12}:{ahora.minute:02d}:{ahora.second:02d} {sufijo}"
        else:
            hora_txt= ahora.strftime('%H:%M:%S')
        self.lbl_reloj.setText(f"{fecha_txt.capitalize()} · {hora_txt}")

    def _autorefrescar(self):

        if self.isVisible():
            self.refrescar()

    #Refresco de datos
    def refrescar(self):

        conn= obtener_conexion()
        c= conn.cursor()

        #Auto-sanación: si la BD con la que se abrió esta sesión quedó con un esquema desactualizado (por ejemplo, una
        #migración de bd.py que no llegó a aplicarse -o que se agregó después de que este archivo ya existía en
        #disco-), una consulta a una columna nueva como calificaciones.estado_publicacion revienta con "no such column"
        #en vez de mostrar el Dashboard. En lugar de dejar caer la excepción, se reintenta UNA vez tras forzar
        #inicializar_bd() (que agrega cualquier columna/tabla faltante sin tocar los datos existentes).
        try:

            c.execute("SELECT estado_publicacion FROM calificaciones LIMIT 1")
        except sqlite3.OperationalError:
            conn.close()
            inicializar_bd()
            conn= obtener_conexion()
            c= conn.cursor()

        restringido= es_profesor_restringido(self.main_window)
        profesor_id= obtener_profesor_id(self.main_window) if restringido else None

        if restringido:
            #"Mis Clases (semanales)" ahora lleva al docente directo a su Horario.
            self.tarjeta_profesores._al_click= self._al_click_horario_docente
            self.tarjeta_profesores.setCursor(Qt.CursorShape.PointingHandCursor)
            #"Mis Secciones" lleva a Mis Estudiantes con el filtro de Curso/Sección
            #abierto (ver comentario en __init__): antes apuntaba al mismo lugar
            #que "Mis Materias" (que ya trae el horario semanal incluido), así que dos tarjetas distintas terminaban en la
            #misma pantalla.
            self.tarjeta_secciones._al_click= self._al_click_secciones_docente
            self.tarjeta_secciones.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.tarjeta_profesores._al_click= self._al_click_profesores
            self.tarjeta_profesores.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tarjeta_secciones._al_click= self._al_click_secciones
            self.tarjeta_secciones.setCursor(Qt.CursorShape.PointingHandCursor)

        #La tarjeta de Materias es la única cuyo rótulo y destino dependen de algo más que el modo
        #docente/institucional: también del tipo de
        #institución (Politécnico, o Personalizado con el módulo Politécnico
        #activo) y de si el rol actual tiene permiso de ver "Politécnico" en el menú. Por eso se recalcula en CADA
        #refresco (es una consulta barata: _tipo_institucion ya cachea con try/except) y no solo cuando cambia el modo
        #docente/institucional.
        if restringido:
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            self.tarjeta_materias._al_click= lambda: self._ir_a_modulo("Materias")
        elif self._es_politecnico_activo() and self._puede_elegir_modulos_tecnicos():
            self.tarjeta_materias._al_click= self._mostrar_selector_materias_modulos
        else:
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            self.tarjeta_materias._al_click= lambda: self._ir_a_modulo("Materias")
        self.tarjeta_materias.setCursor(Qt.CursorShape.PointingHandCursor)

        #Solo re-etiquetamos las tarjetas cuando el modo realmente cambia (la instancia del Dashboard persiste entre
        #inicios/cierres de sesión, así que un docente que cierra sesión y entra un Director no debe seguir viendo las
        #etiquetas del docente).
        if self._modo_tarjetas_docente != restringido:
            self._modo_tarjetas_docente= restringido
            if restringido:
                self.tarjeta_estudiantes.poner_titulo("Mis Estudiantes")
                self.tarjeta_materias.poner_titulo("Mis Materias")
                self.tarjeta_secciones.poner_titulo("Mis Secciones")
                self.tarjeta_profesores.poner_icono(EMOJI_PROFESOR)
                self.tarjeta_profesores.poner_titulo("Mis Clases (semanales)")
            else:
                self.tarjeta_estudiantes.poner_titulo("Estudiantes Activos")
                self.tarjeta_secciones.poner_titulo("Secciones/Grupos")
                self.tarjeta_profesores.poner_icono(EMOJI_PROFESOR)
                self.tarjeta_profesores.poner_titulo("Profesores Activos")

        #El rótulo "Materias" vs "Materias/Módulos" se decide con el mismo criterio de arriba (tipo de institución +
        #permiso real sobre "Politécnico"), independientemente de si el modo docente cambió o no -así que vive FUERA
        #del `if` de arriba, para no quedar pegado al rótulo viejo si alguien cambia el tipo de institución en
        #Configuración sin cerrar sesión.
        if restringido:
            self.tarjeta_materias.poner_titulo("Mis Materias")
        elif self._es_politecnico_activo() and self._puede_elegir_modulos_tecnicos():
            self.tarjeta_materias.poner_titulo("Materias/Módulos")
        else:
            self.tarjeta_materias.poner_titulo("Materias")

        c.execute("SELECT nombre_institucion, tipo_institucion, anio_academico, logo_path "
                   "FROM configuracion WHERE id=1")
        cfg= c.fetchone()
        if cfg:
            self.lbl_institucion.setText(
                f"{cfg['nombre_institucion'] or 'AcaDeXI'}  •  {cfg['tipo_institucion'] or ''}  •  "
                f"Año académico {cfg['anio_academico'] or ''}")
            self._actualizar_logo(cfg["logo_path"])

        if restringido and profesor_id is not None:
            #Materias del docente = las que dicta como titular (materias.profesor_id)
            #MÁS las que dicta como co-docente/asignación (materia_profesores). Antes este módulo solo miraba
            #materias.profesor_id, así que un co-docente no veía sus estudiantes/secciones/asistencia/riesgo reales en el
            #Dashboard, aunque sí los veía correctamente en Horario, Calificaciones, Asistencia, Banco de Tareas y Reportes
            #(que ya usan materia_profesores). Se unifica aquí con el mismo criterio que usa el resto del sistema.
            c.execute("""SELECT DISTINCT materias.id FROM materias
                         LEFT JOIN materia_profesores ON materia_profesores.materia_id = materias.id
                         WHERE materias.profesor_id=? OR materia_profesores.profesor_id=?""",
                      (profesor_id, profesor_id))
            #f: cada fila de la consulta; se toma su id para listar las materias del docente (o [-1] si no hay).
            materias_docente= [f["id"] for f in c.fetchall()] or [-1]
            ph= ",".join("?" for _ in materias_docente)

            #--- KPIs acotados a lo que el docente realmente puede ver/gestionar ---
            c.execute(f"""SELECT COUNT(DISTINCT estudiantes.id) n FROM estudiantes
                         JOIN horarios ON horarios.seccion_id = estudiantes.seccion_id
                         WHERE horarios.materia_id IN ({ph}) AND estudiantes.estado='Activo'""", materias_docente)
            self.tarjeta_estudiantes.actualizar(c.fetchone()["n"])

            c.execute(f"SELECT COUNT(*) n FROM horarios WHERE horarios.materia_id IN ({ph})", materias_docente)
            self.tarjeta_profesores.actualizar(c.fetchone()["n"])

            c.execute(f"SELECT COUNT(*) n FROM materias WHERE id IN ({ph}) AND estado='Activa'", materias_docente)
            self.tarjeta_materias.actualizar(c.fetchone()["n"])

            c.execute(f"""SELECT COUNT(DISTINCT horarios.seccion_id) n FROM horarios
                         WHERE horarios.materia_id IN ({ph})""", materias_docente)
            self.tarjeta_secciones.actualizar(c.fetchone()["n"])

            hoy= datetime.now().strftime("%Y-%m-%d")
            c.execute(f"""SELECT COUNT(*) n FROM asistencia
                         WHERE asistencia.fecha=? AND asistencia.estado='Presente'
                           AND asistencia.materia_id IN ({ph})""",
                      (hoy, *materias_docente))
            presentes_hoy= c.fetchone()["n"]
            c.execute(f"""SELECT COUNT(*) n FROM asistencia
                         WHERE asistencia.fecha=? AND asistencia.materia_id IN ({ph})""",
                      (hoy, *materias_docente))
            total_hoy= c.fetchone()["n"]
            porcentaje_hoy= round((presentes_hoy / total_hoy) * 100, 1) if total_hoy else 0.0

            color_asistencia= _color_por_umbral_asistencia(porcentaje_hoy)
            self.tarjeta_asistencia_hoy.actualizar(porcentaje_hoy, color_acento=color_asistencia)
            self.anillo_asistencia.poner_valor(porcentaje_hoy, color_asistencia)

            #Riesgo académico: "por debajo de la nota mínima" ya no es un único número — en el Sistema Dominicano depende
            #del nivel educativo (Primaria/Secundaria) del Grado del estudiante (ver resolver_nota_minima en
            #configuracion.py). Se resuelve con un JOIN hasta `grados` en vez de la vieja subconsulta plana a
            #`configuracion`, para no perder esa distinción aquí. Un estudiante sin sección/grado, o un grado sin
            #nivel_educativo clasificado, cae al `nota_minima` general (igual que antes de este cambio).
            c.execute(f"""
                SELECT COUNT(DISTINCT calificaciones.estudiante_id) as n
                FROM calificaciones
                LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                LEFT JOIN grados ON secciones.grado_id = grados.id
                JOIN configuracion cfg ON cfg.id = 1
                WHERE calificaciones.materia_id IN ({ph})
                  AND calificaciones.estado_publicacion != 'Borrador'
                  AND calificaciones.valor < (
                      CASE WHEN cfg.sistema_calificacion = ? THEN
                          CASE grados.nivel_educativo
                              WHEN 'Primaria' THEN COALESCE(cfg.nota_minima_primaria, cfg.nota_minima)
                              WHEN 'Secundaria' THEN COALESCE(cfg.nota_minima_secundaria, cfg.nota_minima)
                              ELSE cfg.nota_minima
                          END
                      ELSE cfg.nota_minima END)
            """, (*materias_docente, SISTEMA_DOMINICANO))
            en_riesgo= c.fetchone()["n"]
        else:
            #--- KPIs institucionales (roles gerenciales/administrativos) ---
            c.execute("SELECT COUNT(*) n FROM estudiantes WHERE estado='Activo'")
            self.tarjeta_estudiantes.actualizar(c.fetchone()["n"])

            c.execute("SELECT COUNT(*) n FROM profesores WHERE estado='Activo'")
            self.tarjeta_profesores.actualizar(c.fetchone()["n"])

            c.execute("SELECT COUNT(*) n FROM materias WHERE estado='Activa'")
            self.tarjeta_materias.actualizar(c.fetchone()["n"])

            c.execute("SELECT COUNT(*) n FROM secciones")
            self.tarjeta_secciones.actualizar(c.fetchone()["n"])

            hoy= datetime.now().strftime("%Y-%m-%d")
            c.execute("SELECT COUNT(*) n FROM asistencia WHERE fecha=? AND estado='Presente'", (hoy,))
            presentes_hoy= c.fetchone()["n"]
            c.execute("SELECT COUNT(*) n FROM asistencia WHERE fecha=?", (hoy,))
            total_hoy= c.fetchone()["n"]
            porcentaje_hoy= round((presentes_hoy / total_hoy) * 100, 1) if total_hoy else 0.0

            color_asistencia= _color_por_umbral_asistencia(porcentaje_hoy)
            self.tarjeta_asistencia_hoy.actualizar(porcentaje_hoy, color_acento=color_asistencia)
            self.anillo_asistencia.poner_valor(porcentaje_hoy, color_asistencia)

            #Riesgo académico (usando la nota mínima configurada, por nivel educativo del Grado cuando el sistema es el
            #Dominicano — ver el comentario en la rama de arriba para el mismo cálculo restringido a un Profesor).
            c.execute("""
                SELECT COUNT(DISTINCT calificaciones.estudiante_id) as n
                FROM calificaciones
                LEFT JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                LEFT JOIN grados ON secciones.grado_id = grados.id
                JOIN configuracion cfg ON cfg.id = 1
                WHERE calificaciones.estado_publicacion != 'Borrador'
                  AND calificaciones.valor < (
                      CASE WHEN cfg.sistema_calificacion = ? THEN
                          CASE grados.nivel_educativo
                              WHEN 'Primaria' THEN COALESCE(cfg.nota_minima_primaria, cfg.nota_minima)
                              WHEN 'Secundaria' THEN COALESCE(cfg.nota_minima_secundaria, cfg.nota_minima)
                              ELSE cfg.nota_minima
                          END
                      ELSE cfg.nota_minima END)
            """, (SISTEMA_DOMINICANO,))
            en_riesgo= c.fetchone()["n"]

        color_riesgo= "#10B981" if en_riesgo == 0 else ("#F59E0B" if en_riesgo < 5 else "#EF4444")
        self.tarjeta_riesgo.actualizar(en_riesgo, color_acento=color_riesgo)

        #Tendencia de asistencia de la semana actual, SIEMPRE en orden Lunes → Domingo (antes se mostraba una ventana
        #móvil de "últimos 7 días", que podía empezar en cualquier día de la semana; ahora es la semana calendario
        #actual).
        hoy_dt= datetime.now()
        lunes_dt= hoy_dt - timedelta(days=hoy_dt.weekday())
        domingo_dt= lunes_dt + timedelta(days=6)
        lunes_str= lunes_dt.strftime("%Y-%m-%d")
        domingo_str= domingo_dt.strftime("%Y-%m-%d")

        if restringido and profesor_id is not None:
            c.execute(f"""
                SELECT asistencia.fecha as fecha,
                       SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                       COUNT(*) as total
                FROM asistencia
                WHERE asistencia.fecha BETWEEN ? AND ? AND asistencia.materia_id IN ({ph})
                GROUP BY asistencia.fecha
            """, (lunes_str, domingo_str, *materias_docente))
        else:
            c.execute("""
                SELECT fecha,
                       SUM(CASE WHEN estado='Presente' THEN 1 ELSE 0 END) as presentes,
                       COUNT(*) as total
                FROM asistencia
                WHERE fecha BETWEEN ? AND ?
                GROUP BY fecha
            """, (lunes_str, domingo_str))
        #f: cada fila de asistencia de la semana; se indexa por su fecha para buscarla luego por día.
        filas_semana= {f["fecha"]: f for f in c.fetchall()}
        dias_es= ["L", "M", "X", "J", "V", "S", "D"]
        datos_semana= []
        for i in range(7):
            dia= lunes_dt + timedelta(days=i)
            clave= dia.strftime("%Y-%m-%d")
            fila= filas_semana.get(clave)
            if fila and fila["total"]:
                pct= round((fila["presentes"] / fila["total"]) * 100, 1)
            else:
                pct= 0.0
            datos_semana.append((dias_es[i], pct))
        self.grafico_semanal.poner_datos(datos_semana)
        #v: porcentaje de asistencia de cada día (el segundo valor de la tupla); se promedian los 7.
        promedio_semana= round(sum(v for _, v in datos_semana) / len(datos_semana), 1) if datos_semana else 0.0
        self.lbl_promedio_semanal.setText(f"Promedio de la semana: {promedio_semana}%")

        #--- Detalle: % de asistencia por curso/sección, misma semana ---
        if restringido and profesor_id is not None:
            c.execute(f"""
                SELECT asistencia.seccion_id as seccion_id,
                       (grados.nombre || ' - ' || secciones.nombre) as etiqueta,
                       SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                       COUNT(*) as total
                FROM asistencia
                LEFT JOIN secciones ON secciones.id = asistencia.seccion_id
                LEFT JOIN grados ON secciones.grado_id = grados.id
                WHERE asistencia.fecha BETWEEN ? AND ? AND asistencia.materia_id IN ({ph})
                GROUP BY asistencia.seccion_id
            """, (lunes_str, domingo_str, *materias_docente))
        else:
            c.execute("""
                SELECT asistencia.seccion_id as seccion_id,
                       (grados.nombre || ' - ' || secciones.nombre) as etiqueta,
                       SUM(CASE WHEN asistencia.estado='Presente' THEN 1 ELSE 0 END) as presentes,
                       COUNT(*) as total
                FROM asistencia
                LEFT JOIN secciones ON secciones.id = asistencia.seccion_id
                LEFT JOIN grados ON secciones.grado_id = grados.id
                WHERE asistencia.fecha BETWEEN ? AND ?
                GROUP BY asistencia.seccion_id
            """, (lunes_str, domingo_str))
        filas_secciones= c.fetchall()
        datos_secciones= []
        #f: cada fila por sección (id, etiqueta, presentes y total); se calcula su % de asistencia.
        for f in filas_secciones:
            if not f["total"]:
                continue
            pct= round((f["presentes"] / f["total"]) * 100, 1)
            etiqueta= f["etiqueta"] or "Sin sección"
            datos_secciones.append((f["seccion_id"], etiqueta, pct))
        #Las secciones con menor asistencia primero: son las que más atención necesitan.
        #Lambda: d es una tupla (seccion_id, etiqueta, pct); devuelve d[2], el %, como clave de orden.
        datos_secciones.sort(key=lambda d: d[2])
        datos_secciones= datos_secciones[:8]
        self.panel_barras_seccion.poner_datos(datos_secciones)
        self.lbl_detalle_vacio.setVisible(len(datos_secciones) == 0)
        self.panel_barras_seccion.setVisible(len(datos_secciones) > 0)

        #--- Últimas acciones del sistema (auditoría), máximo 10 ---
        rol_actual= getattr(self.main_window, "rol_actual", None)
        mostrar_actividad= modulo_visible(rol_actual, "Configuración")
        self.panel_actividad.setVisible(mostrar_actividad)
        if mostrar_actividad:
            c.execute("SELECT fecha, modulo, accion, usuario FROM auditoria ORDER BY id DESC LIMIT 10")
            filas_actividad= c.fetchall()
            self.tabla_actividad.setRowCount(len(filas_actividad))
            #f: cada registro de auditoría; i es su número de fila en la tabla de actividad.
            for i, f in enumerate(filas_actividad):
                color= _COLORES_MODULO.get(f["modulo"], "#64748B")
                self.tabla_actividad.setItem(i, 0, QTableWidgetItem(
                    formatear_fecha_hora(f["fecha"], self.main_window) if f["fecha"] else ""))
                self.tabla_actividad.setItem(i, 1, _item_modulo(f["modulo"] or "Sistema", color))
                self.tabla_actividad.setItem(i, 2, QTableWidgetItem(f["accion"] or ""))
                self.tabla_actividad.setItem(i, 3, _item_usuario(f["usuario"]))
            self.tabla_actividad.resizeRowsToContents()
            ajustar_anchos_columnas(self.tabla_actividad)

        conn.close()

    #TEMA
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
        accent= paleta["btn_op_bg"][idx]
        modo_oscuro= getattr(mw, "modo_oscuro", True)

        self._colores_actuales= (bg_panel, bg_borde, txt_prim, txt_sec, accent, modo_oscuro)

        for tarjeta in self._tarjetas:
            tarjeta.aplicar_paleta(bg_panel, bg_borde, txt_prim, txt_sec, modo_oscuro)

        self.lbl_saludo.setStyleSheet(
            f"color: {txt_prim}; font-size: 13px; font-weight: 700; background: transparent;")
        self.lbl_reloj.setStyleSheet(
            f"color: {txt_sec}; font-size: 11px; background: transparent;")

        self.panel_resumen.setStyleSheet(f"""
            QFrame#PanelResumen {{
                background-color: {bg_panel};
                border: 1px solid {bg_borde};
                border-radius: 16px;
            }}
        """)
        self.linea_separadora.setStyleSheet(f"color: {bg_borde}; background-color: {bg_borde};")

        for lbl in (self.lbl_titulo_anillo, self.lbl_titulo_semana):
            lbl.setStyleSheet(
                f"color: {txt_prim}; font-size: 13px; font-weight: 700; background: transparent;")
        self.lbl_promedio_semanal.setStyleSheet(
            f"color: {txt_sec}; font-size: 11px; background: transparent;")

        self.anillo_asistencia.poner_colores(bg_borde, txt_prim)
        self.grafico_semanal.poner_colores(txt_sec, txt_prim)

        for panel in (self.panel_detalle, self.panel_actividad):
            panel.setStyleSheet(f"""
                QFrame#PanelResumen {{
                    background-color: {bg_panel};
                    border: 1px solid {bg_borde};
                    border-radius: 16px;
                }}
            """)

        for lbl in (self.lbl_titulo_detalle, self.lbl_titulo_actividad):
            lbl.setStyleSheet(
                f"color: {txt_prim}; font-size: 13px; font-weight: 700; background: transparent;")
        self.lbl_detalle_vacio.setStyleSheet(
            f"color: {txt_sec}; font-size: 11px; background: transparent;")

        self.panel_barras_seccion.poner_colores(txt_prim, bg_panel, bg_borde)

        self.tabla_actividad.setStyleSheet(f"""
            QTableWidget {{
                background-color: transparent;
                gridline-color: {bg_borde};
                color: {txt_prim};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {bg_panel};
                color: {txt_sec};
                border: none;
                border-bottom: 1px solid {bg_borde};
                padding: 4px;
            }}
        """)