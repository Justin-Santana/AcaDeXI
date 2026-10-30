#Banco de Tareas de AcaDeXI.
import unicodedata
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
QGridLayout, QDateEdit, QDoubleSpinBox, QTextEdit, QInputDialog, QScrollArea, QFrame,
QDialog, QCheckBox, QDialogButtonBox, QStackedWidget, QSizePolicy)
from PySide6.QtCore import Qt, QDate, QPropertyAnimation, QEasingCurve, QVariantAnimation, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from src.nucleo.bd import obtener_conexion, registrar_auditoria, mostrar_columna_numero_lista
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo, interseccion_opcional)
from src.nucleo.iconos import mostrar_mensaje, centrar_y_al_frente, aplicar_icono_cabecera
from src.nucleo.permisos import (puede_editar, obtener_profesor_id,
obtener_materias_permitidas, obtener_secciones_permitidas)
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         agregar_boton_detalle, mostrar_texto_largo,
                         agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import formatear_fecha, aplicar_formato_widget_fecha
from src.interfaz.configuracion import (COMPETENCIAS_FUNDAMENTALES_RD, es_sistema_dominicano, TarjetaSeccion, IconoLupa,
_fundido_entrada, TabWidgetNavegable, anio_academico_actual, conectar_tooltip_seleccion)
from src.modulos.calificaciones import competencias_de_materia_grado, grados_de_materia
from src.modulos.materias import MODELO_EVALUACION_TECNICA
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from src.modulos.calendario import PanelDesplegable
from src.nucleo.iconos import aplicar_icono_ventana, ICONO_FILTRO
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, icono_boton_filtro, pixmap_boton_filtro,
                          EMOJI_TAB_ENTREGAS, html_icono_emoji)

CATEGORIAS_TAREA= ["Tarea", "Examen", "Práctica", "Participación", "Proyecto", "Examen Final"]
ESTADOS_TAREA= ["Activa", "Archivada"]
ESTADOS_ENTREGA= ["Pendiente", "Entregada", "Atrasada", "No entregada"]

#Nota de diseño Este módulo NO define su propia paleta de colores de fondo/texto: se integra con el sistema de
#temas real de la app (main_window.theme_palettes / main_window.modo_oscuro), igual que configuracion.py. Por
#eso reutiliza
#TarjetaSeccion (mismo componente que usa Configuración) y solo fija a mano
#los colores SEMÁNTICOS de estado (verde/ámbar/rojo/gris), que deben verse igual sin importar el tema elegido.
#actualizar_tema() se llama automática- mente cuando el usuario cambia de tema — ver main.py ▸ aplicar_tema().
#============================================================
COLOR_EXITO= "#10B981"
COLOR_ALERTA= "#F59E0B"
COLOR_PELIGRO= "#EF4444"
COLOR_NEUTRO= "#64748B"

#Clasificación de una tarea por urgencia (además de su estado Activa/Archivada en la BD), usada por la barra de
#resumen, la leyenda, la cinta de alertas y la columna "Estado" de la tabla — una sola fuente de verdad para
#las 4.
SEGMENTOS_TAREAS= [
    ("vencida", "Vencidas", COLOR_PELIGRO),
    ("por_vencer", "Por vencer", COLOR_ALERTA),
    ("vigente", "Vigentes", COLOR_EXITO),
    ("archivada", "Archivadas", COLOR_NEUTRO),
]
ETIQUETAS_ESTADO_TAREA= {"vencida": "Vencida", "por_vencer": "Por vencer",
                          "vigente": "Vigente", "archivada": "Archivada"}
COLORES_ESTADO_TAREA= {clave: color for clave, _, color in SEGMENTOS_TAREAS}

SEGMENTOS_ENTREGAS= [
    ("Entregada", "Entregadas", COLOR_EXITO),
    ("Pendiente", "Pendientes", COLOR_ALERTA),
    ("Atrasada", "Atrasadas", COLOR_PELIGRO),
    ("No entregada", "No entregadas", COLOR_NEUTRO),
]
COLORES_ESTADO_ENTREGA= {clave: color for clave, _, color in SEGMENTOS_ENTREGAS}

COLORES_CATEGORIA= {
    "Tarea": "#6366F1", "Examen": COLOR_PELIGRO, "Práctica": "#0EA5E9",
    "Participación": COLOR_EXITO, "Proyecto": COLOR_ALERTA, "Examen Final": "#D946EF",
}

ALTURA_FILA= 40


#Reemplaza el texto del placeholder (ítem 0, sin dato asociado) de un
#combo de Curso/Sección poblado por filtros_curso_seccion.poblar_combo_curso /
#cascada_seccion_por_curso. Ajuste puramente visual y LOCAL a la pestaña
#Entregas de Banco de Tareas: no modifica filtros_curso_seccion.py, así que
#el resto de la app sigue mostrando el placeholder largo original. Si el
#ítem 0 ya tiene un curso/sección real seleccionado, no se toca.
def _acortar_placeholder_combo(combo, texto):

    if combo.count() > 0 and combo.itemData(0) is None:
        combo.setItemText(0, texto)


def _rgba(color_hex, alpha):

    color_hex= (color_hex or "#000000").lstrip("#")
    if len(color_hex) < 6:
        color_hex= "000000"
    #r, g, b: canales rojo, verde y azul (0-255) leídos del color hexadecimal.
    ##Se usan para armar el texto rgba(...).
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


#Minúsculas y sin acentos/diacríticos, para que la búsqueda encuentre
#'Práctica' al escribir 'practica', 'PRACTICA' o 'práctica' indistintamente.
def _normalizar_texto(texto):

    texto= (texto or "").lower()
    texto= unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


#Insignia de estado/categoría (QLabel liviano, sin QGraphicsEffect). Se
#coloca como cellWidget encima de la celda.
def _crear_chip(texto, color_hex):

    contenedor= QWidget()
    contenedor.setStyleSheet("background: transparent;")
    lay= QHBoxLayout(contenedor)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl_chip= QLabel(texto or "—")
    lbl_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl_chip.setStyleSheet(f"""
        background-color: {_rgba(color_hex, 0.16)};
        color: {color_hex};
        border: 1px solid {_rgba(color_hex, 0.45)};
        border-radius: 9px;
        padding: 3px 12px;
        font-weight: 700;
        font-size: 11px;
    """)
    lay.addWidget(lbl_chip, 0, Qt.AlignmentFlag.AlignCenter)
    return contenedor


#QTableWidgetItem SIN texto visible: se usa detrás de un cellWidget
#(chip) para que no se vea duplicado. Un simple `setForeground(transparente)`
#no basta, porque el estilo de fila seleccionada del tema fuerza el color
#del texto (`color: white`) y lo vuelve a mostrar al hacer clic en la fila;
#por eso aquí el texto del item queda vacío de verdad, y el valor real se
#guarda en Qt.ItemDataRole.UserRole para el código que necesite leerlo.
def _item_oculto(texto):

    item= QTableWidgetItem("")
    item.setData(Qt.ItemDataRole.UserRole, texto or "")
    #El detalle genérico de tablas usa el tooltip cuando la celda tiene un widget visual encima. Así el mismo
    #estado que comunica el chip también aparece en «Ver detalle», sin mostrar texto duplicado en la tabla.
    item.setToolTip(texto or "")
    return item


#Barra de progreso segmentada y animada — reemplaza a las tarjetas KPI.
#Cada segmento representa una categoría (p. ej. Vencidas/Por vencer/Vigentes/
#Archivadas) como un tramo de color cuyo ancho se anima suavemente cuando
#cambian los datos. Un clic en un segmento filtra la tabla por esa categoría
#(un segundo clic la quita). Se dibuja con QPainter (un solo widget, sin
#QGraphicsEffect ni sub-widgets), por lo que es muy liviana de repintar.
class BarraSegmentada(QWidget):

    segmento_clicado= Signal(str)

    def __init__(self, segmentos, parent=None):

        super().__init__(parent)
        self._segmentos= segmentos
        self._valores= {clave: 0 for clave, _, _ in segmentos}
        self._fracciones= {clave: 0.0 for clave, _, _ in segmentos}
        self._fracciones_inicio= dict(self._fracciones)
        self._fracciones_objetivo= dict(self._fracciones)
        self._claves_activas= None
        self._segmento_hover= None
        self._color_borde= "#334155"
        self._color_vacio= "#1E293B"
        self.setMinimumHeight(30)
        self.setMaximumHeight(30)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._en_paso_animacion)

    def aplicar_paleta(self, color_borde, color_vacio, _color_texto):

        self._color_borde= color_borde
        self._color_vacio= color_vacio
        self.update()

    def establecer_valores(self, valores):

        total= sum(valores.get(clave, 0) for clave, _, _ in self._segmentos) or 1
        self._fracciones_inicio= dict(self._fracciones)
        self._fracciones_objetivo= {clave: valores.get(clave, 0) / total for clave, _, _ in self._segmentos}
        self._valores= dict(valores)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _en_paso_animacion(self, t):

        for clave, _, _ in self._segmentos:
            ini= self._fracciones_inicio.get(clave, 0.0)
            fin= self._fracciones_objetivo.get(clave, 0.0)
            self._fracciones[clave]= ini + (fin - ini) * t
        self.update()

    def establecer_filtro_activo(self, claves_activas):

        self._claves_activas= set(claves_activas) if claves_activas else None
        self.update()

    def _segmento_en_x(self, pos_x):

        ancho= self.width()
        acumulado= 0.0
        for clave, _, _ in self._segmentos:
            frac= self._fracciones.get(clave, 0.0)
            inicio_px= acumulado * ancho
            fin_px= (acumulado + frac) * ancho
            if inicio_px <= pos_x < fin_px:
                return clave
            acumulado += frac
        return None

    def mouseMoveEvent(self, evento):

        clave= self._segmento_en_x(evento.position().x())
        if clave != self._segmento_hover:
            self._segmento_hover= clave
            etiqueta= next((et for cl, et, _ in self._segmentos if cl == clave), None)
            self.setToolTip(f"{etiqueta}: {self._valores.get(clave, 0)} — clic para filtrar" if etiqueta else "")
            self.update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):

        self._segmento_hover= None
        self.update()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            clave= self._segmento_en_x(evento.position().x())
            if clave:
                self.segmento_clicado.emit(clave)
        super().mousePressEvent(evento)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect= self.rect().adjusted(0, 4, 0, -4)
        radio= rect.height() / 2
        camino= QPainterPath()
        camino.addRoundedRect(float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height()),
                              radio, radio)
        painter.setClipPath(camino)
        painter.fillRect(rect, QColor(self._color_vacio))
        x= float(rect.x())
        for clave, _, color in self._segmentos:
            frac= self._fracciones.get(clave, 0.0)
            if frac <= 0.0008:
                continue
            ancho_seg= frac * rect.width()
            col= QColor(color)
            if self._claves_activas is not None and clave not in self._claves_activas:
                col.setAlpha(70)
            elif self._segmento_hover == clave:
                col= col.lighter(112)
            painter.fillRect(int(x), rect.y(), int(ancho_seg) + 1, rect.height(), col)
            x += ancho_seg
        painter.setClipping(False)
        pluma= QColor(self._color_borde)
        painter.setPen(pluma)
        painter.drawPath(camino)
        painter.end()


#Punto de la leyenda: un contador que 'cuenta' de forma animada hasta el
#valor nuevo. Hace de leyenda de la barra segmentada y, a la vez, de filtro:
#un clic filtra la tabla por esa categoría (otro clic lo quita).
class EtiquetaContadorClicable(QLabel):

    clicada= Signal()

    def __init__(self, etiqueta_texto, color, parent=None):

        super().__init__(parent)
        self._etiqueta_texto= etiqueta_texto
        self._color= color
        self._valor_actual= 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Filtrar por «{etiqueta_texto}» (clic de nuevo para quitar el filtro)")
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #v: valor actual de la animación (0 hasta el total); se convierte a entero y se muestra como
        #texto del contador.
        self._anim.valueChanged.connect(lambda v: self._refrescar_texto(int(v)))
        self._refrescar_texto(0)
        self.establecer_activa(False)

    def _refrescar_texto(self, valor):

        self.setText(f"●  <b>{valor}</b>  {self._etiqueta_texto}")

    def establecer_valor(self, valor):

        self._anim.stop()
        self._anim.setStartValue(self._valor_actual)
        self._anim.setEndValue(valor)
        self._anim.start()
        self._valor_actual= valor

    def establecer_activa(self, activa):

        fondo= _rgba(self._color, 0.16) if activa else "transparent"
        borde= self._color if activa else "transparent"
        self.setStyleSheet(f"""
            QLabel {{
                color: {self._color};
                background: {fondo};
                border: 1px solid {borde};
                border-radius: 8px;
                font-size: 12px;
                padding: 4px 10px;
            }}
            QLabel:hover {{ border: 1px solid {self._color}; }}
        """)

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit()
        super().mousePressEvent(evento)


#Franja de alerta compacta: solo aparece cuando hay algo que atender
#(tareas vencidas, entregas atrasadas...). Entra/sale animando su altura
#máxima — una propiedad normal de QWidget, no requiere QGraphicsEffect, así
#que es barata y no afecta la fluidez del scroll. Un clic filtra la tabla.
class CintaAlerta(QFrame):

    clicada= Signal()

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("CintaAlerta")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        self.setStyleSheet(f"""
            QFrame#CintaAlerta {{
                background-color: {_rgba(COLOR_ALERTA, 0.14)};
                border: 1px solid {_rgba(COLOR_ALERTA, 0.45)};
                border-radius: 10px;
            }}
        """)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        self.lbl_texto= QLabel("")
        self.lbl_texto.setStyleSheet(
            f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {COLOR_ALERTA};")
        lay.addWidget(self.lbl_texto, 1)
        lbl_accion= QLabel("Ver ")
        lbl_accion.setStyleSheet(
            f"background: transparent; border: none; font-weight: 700; font-size: 12px; color: {COLOR_ALERTA};")
        lay.addWidget(lbl_accion)

        self._anim= QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._visible_actual= False

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


def _sistema_calificacion_actual():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT sistema_calificacion FROM configuracion WHERE id=1")
    cfg= c.fetchone()
    conn.close()
    return cfg["sistema_calificacion"] if cfg else "Numérico (Personalizado)"


#Selector múltiple de Competencias Fundamentales (MINERD) para una tarea.
class DialogoCompetencias(QDialog):

    def __init__(self, seleccionadas, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Competencias Fundamentales de la tarea")
        self.setMinimumWidth(430)
        disposicion= QVBoxLayout(self)
        disposicion.setSpacing(8)
        lbl_info= QLabel("Marca las competencias fundamentales que esta tarea ayuda a desarrollar "
                      "(currículo por competencias, MINERD). Puedes marcar varias.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)
        self._checks= []
        for competencia in COMPETENCIAS_FUNDAMENTALES_RD:
            chk= QCheckBox(competencia)
            chk.setChecked(competencia in seleccionadas)
            disposicion.addWidget(chk)
            self._checks.append(chk)
        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def seleccionadas(self):

        return [chk.text() for chk in self._checks if chk.isChecked()]


#Selector de Competencias Específicas (currículo dinámico) para una tarea del
#Banco de Tareas. Una tarea no tiene un grado fijo propio (la misma materia puede
#darse en varios grados), así que se agrupan las CE por cada grado en el que la
#materia se imparte. Al calificar una entrega de esta tarea, estas CE se copian
#automáticamente a la evidencia (calificacion_competencia) — ver _calificar_entrega.
class DialogoCompetenciasEspecificasTarea(QDialog):

    def __init__(self, materia_id, seleccionadas_ids=None, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Vincular tarea a Competencias Específicas (CE)")
        self.setMinimumWidth(480)
        self.setMinimumHeight(420)
        seleccionadas_ids= set(seleccionadas_ids or [])
        self._checks= []

        disposicion= QVBoxLayout(self)
        lbl_info= QLabel("Marca las Competencias Específicas del currículo que esta tarea evalúa. Al "
                       "calificar una entrega, la evidencia quedará vinculada automáticamente a estas "
                       "mismas CE, para que aparezca en Notas por Competencia sin trabajo extra.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        area= QScrollArea()
        area.setWidgetResizable(True)
        contenedor= QWidget()
        contenido= QVBoxLayout(contenedor)
        grados= grados_de_materia(materia_id)
        if not grados:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")
            grados= [dict(fila) for fila in c.fetchall()]
            conn.close()
        if not grados:
            contenido.addWidget(QLabel("No hay grados configurados todavía en el sistema."))
        for grado in grados:
            competencias= competencias_de_materia_grado(materia_id, grado["id"])
            if not competencias:
                continue
            lbl_grado= QLabel(f"— {grado['nombre']} —")
            lbl_grado.setStyleSheet("font-weight: 600; margin-top: 6px;")
            contenido.addWidget(lbl_grado)
            for comp in competencias:
                chk= QCheckBox(f"{comp['codigo']} — {comp['descripcion']}")
                chk.setChecked(comp["id"] in seleccionadas_ids)
                chk.setProperty("competencia_id", comp["id"])
                contenido.addWidget(chk)
                self._checks.append(chk)
        if not self._checks:
            contenido.addWidget(QLabel("Esta materia todavía no tiene Competencias Específicas definidas "
                                        "en ningún grado. Defínelas en Calificaciones ▸ Currículo (CE)."))
        contenido.addStretch()
        area.setWidget(contenedor)
        disposicion.addWidget(area, 1)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def seleccionadas(self):

        return [chk.property("competencia_id") for chk in self._checks if chk.isChecked()]


#Selector de Resultados de Aprendizaje (RA) para una tarea del Banco de
#Tareas, cuando la materia de la tarea usa el modelo técnico (Politécnico:
#materias.modelo_evaluacion= MODELO_EVALUACION_TECNICA). A diferencia de las
#Competencias Específicas, un RA se define directamente sobre la materia (no
#por grado), así que aquí no hace falta agrupar. Al calificar una entrega,
#estos RA se copian automáticamente hacia `calificacion_ra` — ver
#_calificar_entrega — para que 📐 Calificaciones Técnicas quede sincronizado.
class DialogoResultadosAprendizajeTarea(QDialog):

    def __init__(self, materia_id, seleccionadas_ids=None, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Vincular tarea a Resultados de Aprendizaje (RA)")
        self.setMinimumWidth(480)
        self.setMinimumHeight(380)
        seleccionadas_ids= set(seleccionadas_ids or [])
        self._checks= []

        disposicion= QVBoxLayout(self)
        lbl_info= QLabel("Marca los Resultados de Aprendizaje (RA) del módulo técnico que esta tarea evalúa. "
                       "Al calificar una entrega, la nota se copiará automáticamente a esos RA en "
                       "Calificaciones Técnicas, sin que tengas que registrarla dos veces.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        area= QScrollArea()
        area.setWidgetResizable(True)
        contenedor= QWidget()
        contenido= QVBoxLayout(contenedor)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, codigo, descripcion FROM resultados_aprendizaje
                     WHERE materia_id=? AND estado='Activo' ORDER BY orden, codigo""", (materia_id,))
        ras= [dict(fila) for fila in c.fetchall()]
        conn.close()
        for ra in ras:
            chk= QCheckBox(f"{ra['codigo']} — {ra['descripcion']}")
            chk.setChecked(ra["id"] in seleccionadas_ids)
            chk.setProperty("ra_id", ra["id"])
            contenido.addWidget(chk)
            self._checks.append(chk)
        if not self._checks:
            contenido.addWidget(QLabel("Esta materia todavía no tiene Resultados de Aprendizaje definidos. "
                                        "Defínelos en Calificaciones Técnicas ▸ Resultados de Aprendizaje."))
        contenido.addStretch()
        area.setWidget(contenedor)
        disposicion.addWidget(area, 1)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)
        centrar_y_al_frente(self, parent)


    def seleccionadas(self):

        return [chk.property("ra_id") for chk in self._checks if chk.isChecked()]


#Ajuste de entrega desde observaciones (ver observaciones.py)  Cuando una observación queda etiquetada con la
#categoría "📝 Tareas" y tiene una materia asociada, se ofrece marcar directamente el estado de entrega de una
#tarea de esa materia para el estudiante -sin salir de Observaciones-. Por debajo, esto crea o actualiza la
#MISMA fila de `tarea_entregas` que usa la pestaña Entregas de este módulo (nunca un dato paralelo): si el
#estudiante todavía no tenía una fila para esa tarea (p. ej. no se había generado su lista de entregas
#todavía), se crea; si ya la tenía, se actualiza su estado.
class DialogoAjusteEntrega(QDialog):

    def __init__(self, estudiante_id, texto_observacion, naturaleza, materia_id, parent=None):

        super().__init__(parent)
        self.estudiante_id= estudiante_id
        self.setWindowTitle("Marcar Entrega por Observación")
        self.setMinimumWidth(460)

        disposicion= QVBoxLayout(self)
        lbl_info= QLabel("Esto marca el estado de entrega de este estudiante en la tarea que elijas, "
                       "dentro de la pestaña Entregas normal — no crea una tarea nueva, solo actualiza "
                       "(o crea, si todavía no existía) su fila de entrega.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        lbl_cita= QLabel(f"“{texto_observacion[:140]}{'…' if len(texto_observacion) > 140 else ''}”")
        lbl_cita.setWordWrap(True)
        lbl_cita.setStyleSheet("font-style: italic; color: #6B7280;")
        disposicion.addWidget(lbl_cita)

        form= QGridLayout()
        self.combo_tarea= QComboBox()
        self._cargar_tareas(materia_id)
        form.addWidget(QLabel("Tarea:"), 0, 0)
        form.addWidget(self.combo_tarea, 0, 1)

        self.combo_estado= QComboBox()
        for estado in ESTADOS_ENTREGA:
            self.combo_estado.addItem(estado, estado)
        estado_sugerido= {"Positiva": "Entregada", "Negativa": "Atrasada"}.get(naturaleza)
        if estado_sugerido:
            idx= self.combo_estado.findData(estado_sugerido)
            if idx >= 0:
                self.combo_estado.setCurrentIndex(idx)
        form.addWidget(QLabel("Estado:"), 1, 0)
        form.addWidget(self.combo_estado, 1, 1)
        disposicion.addLayout(form)

        self.aviso= QLabel("Esta materia todavía no tiene tareas activas en el Banco de Tareas.")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(self.combo_tarea.count() == 0)
        disposicion.addWidget(self.aviso)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)
        centrar_y_al_frente(self, parent)

    def _cargar_tareas(self, materia_id):

        if materia_id is None:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, titulo, fecha_entrega FROM tareas
                     WHERE materia_id=? AND estado='Activa' ORDER BY fecha_entrega DESC""", (materia_id,))
        filas= c.fetchall()
        conn.close()
        for fila in filas:
            etiqueta= fila["titulo"] + (f" ({fila['fecha_entrega']})" if fila["fecha_entrega"] else "")
            self.combo_tarea.addItem(etiqueta, fila["id"])

    def datos(self):

        return {"tarea_id": self.combo_tarea.currentData(), "estado": self.combo_estado.currentData()}


#Usado por observaciones.py para decidir si vale la pena ofrecer
#'Marcar entrega' -no tiene sentido mostrar el botón si la materia
#todavía no tiene ninguna tarea cargada en el Banco de Tareas.
def _hay_tareas_activas_en_materia(materia_id):

    if materia_id is None:
        return False
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT 1 FROM tareas WHERE materia_id=? AND estado='Activa' LIMIT 1", (materia_id,))
    hay= c.fetchone() is not None
    conn.close()
    return hay


#Crea o actualiza la fila de `tarea_entregas` de este estudiante para
#esa tarea (mismo UPSERT por (tarea_id, estudiante_id) que usa el resto
#del módulo), a partir de un ajuste hecho desde Observaciones.
def guardar_ajuste_entrega(main_window, estudiante_id, tarea_id, estado, texto_obs):

    conn= obtener_conexion()
    c= conn.cursor()
    fecha_real= datetime.now().strftime("%Y-%m-%d") if estado == "Entregada" else None
    c.execute("""INSERT INTO tarea_entregas (tarea_id, estudiante_id, estado_entrega, fecha_entrega_real, observacion)
                 VALUES (?,?,?,?,?)
                 ON CONFLICT(tarea_id, estudiante_id) DO UPDATE SET
                    estado_entrega= excluded.estado_entrega, fecha_entrega_real=excluded.fecha_entrega_real,
                    observacion= excluded.observacion""",
              (tarea_id, estudiante_id, estado, fecha_real, f"Ajuste por observación: {texto_obs[:80]}"))
    conn.commit()
    conn.close()
    registrar_auditoria("Banco de Tareas", "Marcó entrega desde una observación", main_window.usuario_actual,
                         f"Estudiante ID {estudiante_id} - Tarea ID {tarea_id} - Estado {estado}")


class ModuloBancoTareas(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion_tarea= None
        self._filtro_tareas= None
        self._filtro_entregas= None
        self._conteo_tareas_actual= {}
        self._conteo_entregas_actual= {}
        self._tareas_todas_cache= []
        self._entregas_todas_cache= []
        self._construir_ui()
        self._aplicar_tema_visual()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Banco de Tareas"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar tarea", self._guardar_tarea)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar_tarea)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar tarea seleccionada",
                         self._cargar_tarea_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar tarea", self._eliminar_tarea)
        registrar_atajo(self, self.main_window, "Ctrl+Shift+C", "Calificar entrega seleccionada",
                         self._calificar_entrega)

    #Construcción de la interfaz
    def _construir_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        #OJO: la barra horizontal NO debe forzarse a "AlwaysOff". Si el contenido interno (grid de 4 columnas, botones
        #largos, etc.) llega a necesitar más ancho del disponible, sin una barra horizontal que absorba ese excedente,
        #el QScrollArea empuja ese ancho hacia arriba y termina descuadrando la ventana COMPLETA (incluido el sidebar)
        #— es justo lo que se veía en el bug reportado. Con "AsNeeded" (igual que el resto de módulos, ver
        #configuracion.py), si algún día el contenido no cabe, aparece un scroll horizontal *dentro* de este módulo en
        #vez de romper el layout de toda la app.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(12)

        #--- Cabecera tipo "hero": icono + título + descripción + contador ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Banco de Tareas")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Banco de Tareas")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Catálogo de tareas y actividades por materia, con seguimiento de entregas "
            "por estudiante ligado directamente a Calificaciones.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        self.chip_contador= QLabel("0 tareas")
        self.chip_contador.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_entregas= QLabel("0 entregas")
        self.chip_entregas.setObjectName("ChipContador")
        cabecera_layout.addWidget(self.chip_entregas, 0, Qt.AlignmentFlag.AlignVCenter)

        disposicion.addWidget(self.frame_cabecera)

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        #Ver nota en configuracion.py: quita la línea base nativa que Qt dibuja bajo la barra de pestañas y que el
        #stylesheet no puede eliminar.
        self.tabs.tabBar().setDrawBase(False)
        disposicion.addWidget(self.tabs)
        self.tabs.addTab(self._tab_tareas(), "Catálogo de Tareas")
        self.tabs.addTab(self._tab_entregas(), "Entregas")
        #Iconos explícitos de pestaña: "Catálogo de Tareas" NO se toca porque el iconizador automático ya le pone 📋
        #(tarea), que es coherente. "Entregas" en cambio heredaba la bandeja de importar/exportar (EMOJI_IMPORTAR,
        #keyword genérico 'entrega'), así que se le asigna un icono propio: bandeja de recepción + documento + check.
        self.tabs.setTabIcon(1, icono_emoji(EMOJI_TAB_ENTREGAS))
        self.tabs.currentChanged.connect(self._al_cambiar_tab)
        #Transición suave (fundido) al cambiar de pestaña, en vez de un salto brusco.
        self.tabs.currentChanged.connect(lambda i: _fundido_entrada(self.tabs.widget(i), 220))

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    #Feedback visual breve en el botón que disparó la acción: cambia de
    #texto/color un momento y luego vuelve a su estilo normal (el de su
    #objectName, definido por el tema global). No usa QGraphicsEffect.
    def _pulso_exito(self, boton, texto_temporal="¡Listo!"):

        if boton is None:
            return
        texto_original= boton.text()
        boton.setText(texto_temporal)
        boton.setStyleSheet(
            f"background-color: {COLOR_EXITO}; color: white; border-radius: 8px; "
            "padding: 9px 16px; font-weight: 700;")

        def _restaurar():

            boton.setText(texto_original)
            boton.setStyleSheet("")
        QTimer.singleShot(900, _restaurar)

    #Barra de búsqueda con lupa dibujada a mano e insensible a mayúsculas/
    #acentos — mismo diseño y comportamiento que en Configuración, para que
    #todos los módulos del sistema busquen exactamente igual.
    def _crear_barra_busqueda(self, placeholder, callback_filtro):

        marco= QFrame()
        marco.setStyleSheet("QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay= QHBoxLayout(marco)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(6)
        icono= IconoLupa()
        lay.addWidget(icono)
        in_campo= QLineEdit()
        limitar_campo_texto(in_campo, 300)
        in_campo.setPlaceholderText(placeholder)
        in_campo.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay.addWidget(in_campo, 1)

        temporizador= QTimer(self)
        temporizador.setSingleShot(True)
        temporizador.setInterval(150)
        temporizador.timeout.connect(callback_filtro)
        #_t: texto nuevo del campo (no se usa); lambda que solo reinicia el temporizador de búsqueda
        #diferida.
        in_campo.textChanged.connect(lambda _t: temporizador.start())

        self._iconos_busqueda= getattr(self, "_iconos_busqueda", [])
        self._iconos_busqueda.append(icono)
        return marco, in_campo

    #Pestaña: Catálogo de Tareas
    def _tab_tareas(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(12)

        self.cinta_alerta_tareas= CintaAlerta()
        self.cinta_alerta_tareas.clicada.connect(self._al_clic_alerta_tareas)
        disposicion.addWidget(self.cinta_alerta_tareas)

        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(16)
        self.barra_tareas= BarraSegmentada(SEGMENTOS_TAREAS)
        self.barra_tareas.segmento_clicado.connect(self._alternar_filtro_tareas)
        fila_resumen.addWidget(self.barra_tareas, 2)

        leyenda= QHBoxLayout()
        leyenda.setSpacing(2)
        self.etiquetas_leyenda_tareas= {}
        for clave, etiqueta_txt, color in SEGMENTOS_TAREAS:
            lbl= EtiquetaContadorClicable(etiqueta_txt, color)
            #c: clave del segmento de la leyenda, fijada con c=clave en cada vuelta; filtra tareas
            #por ese segmento.
            lbl.clicada.connect(lambda c=clave: self._alternar_filtro_tareas(c))
            leyenda.addWidget(lbl)
            self.etiquetas_leyenda_tareas[clave]= lbl
        fila_resumen.addLayout(leyenda, 3)
        disposicion.addLayout(fila_resumen)

        tarjeta_form= TarjetaSeccion(icono="📋", titulo="Nueva tarea")
        form= QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.combo_materia= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia, "Materia a la que pertenece esta tarea")
        self.combo_materia.currentIndexChanged.connect(self._actualizar_visibilidad_ce_ra)
        self.in_titulo= QLineEdit()
        limitar_campo_texto(self.in_titulo, 300)
        self.in_titulo.setPlaceholderText("Título de la tarea")
        self.combo_categoria= QComboBox()
        self.combo_categoria.addItems(CATEGORIAS_TAREA)
        conectar_tooltip_seleccion(self.combo_categoria, "Tipo de actividad (Tarea, Examen, Práctica, etc.)")
        self.combo_periodo= QComboBox()
        conectar_tooltip_seleccion(self.combo_periodo, "Periodo académico al que corresponde esta tarea")
        #OPTIMIZACIÓN DE LAYOUT: por defecto un QComboBox pide como ancho mínimo el necesario para mostrar su ítem MÁS
        #LARGO sin recortar (p. ej. "Administración de Base de Datos (ADB-001)"). Eso ignora los stretch factors del
        #QGridLayout y empuja la tarjeta —y la ventana— más ancha que la pantalla, descuadrando el resto de
        #campos (lo que se ve en el screenshot). Al fijar un
        #sizeAdjustPolicy con longitud mínima de contenido, el combo pide un ancho razonable y deja que sea el layout
        #(columnas del grid) quien reparta el espacio; el texto largo se sigue mostrando completo al desplegar la
        #lista, solo que el propio combo no se infla para acomodarlo.
        for _combo in (self.combo_materia, self.combo_categoria, self.combo_periodo):
            _combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            _combo.setMinimumContentsLength(18)
        self.date_asignacion= QDateEdit(calendarPopup=True)
        self.date_asignacion.setDate(QDate.currentDate())
        self.date_entrega= QDateEdit(calendarPopup=True)
        self.date_entrega.setDate(QDate.currentDate().addDays(7))
        aplicar_formato_widget_fecha(self.date_asignacion, self.main_window)
        aplicar_formato_widget_fecha(self.date_entrega, self.main_window)
        self.spin_peso= QDoubleSpinBox()
        self.spin_peso.setRange(0, 100)
        self.spin_peso.setSuffix(" %")
        self.spin_peso.setToolTip("Peso sugerido de esta tarea en el cálculo de la nota final")
        self.spin_valor_max= QDoubleSpinBox()
        self.spin_valor_max.setRange(1, 1000)
        self.spin_valor_max.setValue(100)
        self.spin_valor_max.setToolTip("Valor o puntaje máximo que puede obtener un estudiante en esta tarea")
        self.combo_estado_tarea= QComboBox()
        self.combo_estado_tarea.addItems(ESTADOS_TAREA)
        conectar_tooltip_seleccion(self.combo_estado_tarea, "Estado de la tarea: Activa (visible) o Archivada")
        self._competencias_tarea_seleccionadas= []
        self.lbl_competencias_tarea= QLabel("Competencias (RD):")
        self.btn_competencias_tarea= QPushButton("Seleccionar competencias")
        self.btn_competencias_tarea.setIcon(icono_emoji("📋"))
        self.btn_competencias_tarea.setIconSize(_QSize_emoji(16, 16))
        self.btn_competencias_tarea.setObjectName("BtnAccionNeutro")
        self.btn_competencias_tarea.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_competencias_tarea.setToolTip(
            "Competencias Fundamentales del currículo dominicano (MINERD) a las que aporta esta tarea")
        self.btn_competencias_tarea.clicked.connect(self._elegir_competencias_tarea)
        self._ce_tarea_seleccionadas= []
        self.btn_ce_tarea= QPushButton("Vincular a Competencias Específicas")
        self.btn_ce_tarea.setIcon(icono_emoji("📋"))
        self.btn_ce_tarea.setIconSize(_QSize_emoji(16, 16))
        self.btn_ce_tarea.setObjectName("BtnAccionNeutro")
        self.btn_ce_tarea.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ce_tarea.setToolTip(
            "Vincula esta tarea a las Competencias Específicas del currículo (por materia+grado). Al "
            "calificar una entrega, la evidencia quedará vinculada automáticamente a estas CE.")
        self.btn_ce_tarea.clicked.connect(self._elegir_ce_tarea)
        self._ra_tarea_seleccionadas= []
        self.btn_ra_tarea= QPushButton("Vincular a Resultados de Aprendizaje (RA)")
        self.btn_ra_tarea.setIcon(icono_emoji("📋"))
        self.btn_ra_tarea.setIconSize(_QSize_emoji(16, 16))
        self.btn_ra_tarea.setObjectName("BtnAccionNeutro")
        self.btn_ra_tarea.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ra_tarea.setToolTip(
            "Vincula esta tarea a los Resultados de Aprendizaje (RA) del módulo técnico (Politécnico). Al "
            "calificar una entrega, la nota quedará copiada automáticamente hacia esos RA en Calificaciones "
            "Técnicas.")
        self.btn_ra_tarea.clicked.connect(self._elegir_ra_tarea)
        self.btn_ra_tarea.setVisible(False)
        #btn_ce_tarea y btn_ra_tarea son mutuamente excluyentes (nunca aplican los dos a la vez a una misma tarea, ver
        #_actualizar_visibilidad_ce_ra) y antes se colocaban SUELTOS en la misma celda del grid, alternando solo con
        #.setVisible(). Eso podía dejar un instante (p. ej. al cambiar de materia, antes de que Qt repintara) en que
        #ambos quedaban dibujados uno encima del otro -el "doble borde" que se veía en el formulario-. Un
        #QStackedWidget garantiza a nivel de layout que solo uno de los dos existe visualmente en esa celda en todo
        #momento.
        self.stack_ce_ra_tarea= QStackedWidget()
        self.stack_ce_ra_tarea.addWidget(self.btn_ce_tarea)
        self.stack_ce_ra_tarea.addWidget(self.btn_ra_tarea)
        self.in_descripcion= QTextEdit()
        limitar_campo_texto(self.in_descripcion, 5000)
        self.in_descripcion.setPlaceholderText("Instrucciones / descripción (opcional)")
        self.in_descripcion.setFixedHeight(60)

        #ALCANCE (opcional): por defecto una tarea aplica a TODAS las
        #secciones que cursan la materia (igual que siempre). Si se llenan estos campos, la tarea —con SU PROPIA fecha
        #de entrega— queda restringida a ese curso/sección/área técnica/carrera. Así, una misma materia impartida en
        #varios cursos puede tener fechas de entrega distintas por grupo: se crea una tarea por grupo en vez de una
        #sola fecha global para todos.
        self.combo_curso_tarea= QComboBox()
        self.combo_curso_tarea.setToolTip(
            "Opcional: restringe esta tarea a un curso/grado (deja 'Todos' si la fecha de entrega "
            "es la misma para todas las secciones que cursan la materia)")
        self.combo_curso_tarea.currentIndexChanged.connect(self._curso_tarea_cambio)
        self.combo_seccion_tarea= QComboBox()
        self.combo_seccion_tarea.setToolTip("Opcional: restringe esta tarea a una sección concreta")
        self.lbl_filtro_especialidad_tarea= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_tarea= QComboBox()
        self.combo_filtro_especialidad_tarea.setToolTip(
            "Opcional: restringe esta tarea a un área técnica (Politécnico)")
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_tarea,
            "Opcional: restringe esta tarea a un área técnica (Politécnico)")
        self.lbl_filtro_carrera_tarea= QLabel("Carrera:")
        self.combo_filtro_carrera_tarea= QComboBox()
        self.combo_filtro_carrera_tarea.setToolTip("Opcional: restringe esta tarea a una carrera (Universidad)")
        conectar_tooltip_seleccion(self.combo_filtro_carrera_tarea,
            "Opcional: restringe esta tarea a una carrera (Universidad)")
        #combo_curso_tarea/combo_seccion_tarea se dejan CON EL TAMAÑO POR DEFECTO de Qt -sin
        #AdjustToMinimumContentsLengthWithIcon ni setMinimumContentsLength-, igual que sus equivalentes h_curso/
        #h_seccion en materias.py (pestaña Horario): son el mismo tipo de combo "Curso/Sección" que aparece en el resto
        #de módulos y debe verse exactamente igual ahí también. Los otros dos (Área Técnica/ Carrera) sí llevan el
        #ajuste de ancho, igual que en Horario.
        for _combo in (self.combo_filtro_especialidad_tarea, self.combo_filtro_carrera_tarea):
            _combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            _combo.setMinimumContentsLength(16)
        self.lbl_materia_tarea_form= QLabel("Materia:")
        form.addWidget(self.lbl_materia_tarea_form, 0, 0)
        form.addWidget(self.combo_materia, 0, 1)
        form.addWidget(QLabel("Categoría:"), 0, 2)
        form.addWidget(self.combo_categoria, 0, 3)
        form.addWidget(self.in_titulo, 1, 0, 1, 2)
        form.addWidget(QLabel("Periodo:"), 1, 2)
        form.addWidget(self.combo_periodo, 1, 3)
        form.addWidget(QLabel("Fecha asignación:"), 2, 0)
        form.addWidget(self.date_asignacion, 2, 1)
        form.addWidget(QLabel("Fecha entrega:"), 2, 2)
        form.addWidget(self.date_entrega, 2, 3)
        form.addWidget(QLabel("Peso sugerido:"), 3, 0)
        form.addWidget(self.spin_peso, 3, 1)
        form.addWidget(QLabel("Valor máximo:"), 3, 2)
        form.addWidget(self.spin_valor_max, 3, 3)
        form.addWidget(QLabel("Estado:"), 4, 0)
        form.addWidget(self.combo_estado_tarea, 4, 1)
        form.addWidget(self.lbl_competencias_tarea, 4, 2)
        form.addWidget(self.btn_competencias_tarea, 4, 3)
        form.addWidget(self.stack_ce_ra_tarea, 5, 0, 1, 4)
        form.addWidget(QLabel("Instrucciones / descripción (opcional):"), 6, 0, 1, 4)
        form.addWidget(self.in_descripcion, 7, 0, 1, 4)
        #Reparto fijo de las 4 columnas del grid (etiqueta/campo/etiqueta/campo) para que ninguna columna se "robe"
        #ancho de las demás cuando algún combo/campo recibe un valor largo. Con esto el card mantiene un ancho estable
        #y predecible sin importar el contenido cargado.
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 0)
        form.setColumnStretch(3, 1)
        tarjeta_form.contenido.addLayout(form)

        #Alcance opcional: en SU PROPIO cuadrito, con aire alrededor, nunca apretado junto a los demás campos del
        #formulario.
        frame_alcance_tarea= QFrame()
        frame_alcance_tarea.setObjectName("CuadroFiltroTecnico")
        frame_alcance_tarea.setStyleSheet(
            "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
            "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
        lay_alcance= QVBoxLayout(frame_alcance_tarea)
        lay_alcance.setContentsMargins(14, 10, 14, 10)
        lay_alcance.setSpacing(6)
        lbl_alcance= QLabel("Alcance de la tarea (opcional — deja en \"Todos\" para que aplique a "
                              "todas las secciones que cursan la materia)")
        lbl_alcance.setWordWrap(True)
        lbl_alcance.setStyleSheet("font-weight: 600;")
        lay_alcance.addWidget(lbl_alcance)
        #Dos filas en vez de una sola con los 4 combos juntos: una fila con los 4 combos anchos (Curso/Sección/Área
        #Técnica/Carrera) siempre se termina "inflando" con el ancho de sus ítems más largos (ver
        #AdjustToMinimumContentsLengthWithIcon más abajo) y eso empuja todo el card -y con él, toda la pestaña- mucho
        #más ancho de lo que cabe en pantalla. Repartiéndolos en dos filas de 2 combos cada una el ancho total queda
        #acotado sin importar qué tan largos sean los nombres de áreas técnicas/carreras cargados.
        fila_alcance_2= QHBoxLayout()
        fila_alcance_2.setSpacing(16)
        fila_alcance_2.addWidget(self.lbl_filtro_especialidad_tarea)
        fila_alcance_2.addWidget(self.combo_filtro_especialidad_tarea)
        fila_alcance_2.addWidget(self.lbl_filtro_carrera_tarea)
        fila_alcance_2.addWidget(self.combo_filtro_carrera_tarea)
        fila_alcance_2.addStretch()
        lay_alcance.addLayout(fila_alcance_2)
        fila_alcance_1= QHBoxLayout()
        fila_alcance_1.setSpacing(16)
        fila_alcance_1.addWidget(QLabel("Curso:"))
        fila_alcance_1.addWidget(self.combo_curso_tarea)
        fila_alcance_1.addWidget(QLabel("Sección:"))
        fila_alcance_1.addWidget(self.combo_seccion_tarea)
        fila_alcance_1.addStretch()
        lay_alcance.addLayout(fila_alcance_1)
        tarjeta_form.contenido.addWidget(frame_alcance_tarea)

        fila_botones_form= QHBoxLayout()
        self.btn_guardar_tarea= QPushButton("Guardar Tarea")
        self.btn_guardar_tarea.setIcon(icono_emoji("💾"))
        self.btn_guardar_tarea.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_tarea.clicked.connect(self._guardar_tarea)
        fila_botones_form.addWidget(self.btn_guardar_tarea)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_tarea)
        fila_botones_form.addWidget(btn_limpiar)
        fila_botones_form.addStretch()
        tarjeta_form.contenido.addLayout(fila_botones_form)

        self.panel_form_tarea= PanelDesplegable("Nueva tarea")
        self.panel_form_tarea.cuerpo_layout().addWidget(tarjeta_form)
        disposicion.addWidget(self.panel_form_tarea)

        fila_busqueda_tareas= QHBoxLayout()
        marco_busqueda_tareas, self.in_buscar_tareas= self._crear_barra_busqueda(
            "Buscar por título, materia o categoría…", self._filtro_tareas_cambio)
        fila_busqueda_tareas.addWidget(marco_busqueda_tareas, 1)
        self.btn_filtros_tareas= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_tareas)
        self.btn_filtros_tareas.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_tareas.setObjectName("BtnAccionNeutro")
        self.btn_filtros_tareas.setToolTip(
            "Filtrar las tareas listadas por curso, sección, área técnica/carrera y materia")
        self.btn_filtros_tareas.clicked.connect(self._abrir_dialogo_filtros_tareas)
        fila_busqueda_tareas.addWidget(self.btn_filtros_tareas)
        disposicion.addLayout(fila_busqueda_tareas)


        self.tabla_tareas= QTableWidget(0, 9)
        aplicar_estructura_tabla(self.tabla_tareas)

        self.tabla_tareas.setHorizontalHeaderLabels(
            ["ID", "Materia", "Título", "Categoría", "Entrega", "Peso", "Estado", "Competencia(s)", "Alcance"])
        self.tabla_tareas.setColumnHidden(0, True)
        header= self.tabla_tareas.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.tabla_tareas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_tareas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_tareas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_tareas.setAlternatingRowColors(True)
        self.tabla_tareas.setWordWrap(False)
        self.tabla_tareas.setShowGrid(False)
        self.tabla_tareas.setMinimumHeight(360)
        #Preferred (no Expanding) en vertical: dentro del QScrollArea con
        #widgetResizable=True de _construir_ui, un widget Expanding se estira
        #para llenar TODO el espacio libre del viewport cuando el contenido de la pestaña es más corto que la ventana
        #-exactamente lo que pasaba al colapsar "Nueva tarea": la tabla se inflaba para ocupar el hueco que dejaba el
        #formulario cerrado-. Con Preferred, la tabla conserva una altura estable y ese espacio sobrante lo absorbe el
        #l.addStretch() del final en vez de la tabla.
        self.tabla_tareas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.tabla_tareas.verticalHeader().setVisible(False)
        self.tabla_tareas.verticalHeader().setDefaultSectionSize(ALTURA_FILA)
        disposicion.addWidget(self.tabla_tareas, 1)

        self.paginacion_tareas= ControlPaginacion()
        self.paginacion_tareas.cambio.connect(self._cargar_tareas)
        disposicion.addWidget(self.paginacion_tareas)

        #Botón ⛶ que abre la tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo maximizado
        #-mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-.
        agregar_boton_pantalla_completa(
            None, [self.tabla_tareas, self.paginacion_tareas],
            titulo= "Tareas", parent=self)

        fila_botones= QHBoxLayout()
        btn_editar= QPushButton("Cargar Seleccionada")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_tarea_seleccionada)
        fila_botones.addWidget(btn_editar)
        btn_eliminar= QPushButton("Eliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_tarea)
        fila_botones.addWidget(btn_eliminar)
        btn_detalle_tareas= agregar_boton_detalle(
            fila_botones, self.tabla_tareas, self, titulo="Detalle de la Tarea",
            proveedor_extra_botones= self._boton_ver_descripcion_tarea)
        self.tabla_tareas.doubleClicked.connect(lambda *_: btn_detalle_tareas.click())
        fila_botones.addStretch()
        disposicion.addLayout(fila_botones)
        disposicion.addStretch()        #Combos del diálogo de filtros del CATÁLOGO (distintos de los del
        #formulario "Nueva tarea"): filtran qué tareas YA CREADAS se listan en la tabla, todos opcionales, mismo patrón
        #que calendario.py.
        self.combo_filtro_cat_curso= QComboBox()
        self.combo_filtro_cat_curso.currentIndexChanged.connect(self._curso_filtro_cat_cambio)
        self.combo_filtro_cat_seccion= QComboBox()
        #_: índice nuevo del combo (no se usa); lambda que solo llama a _filtro_cat_cambio sin
        #argumentos.
        self.combo_filtro_cat_seccion.currentIndexChanged.connect(lambda _: self._filtro_cat_cambio())
        self.lbl_filtro_cat_especialidad= QLabel("Área Técnica:")
        self.combo_filtro_cat_especialidad= QComboBox()
        self.combo_filtro_cat_especialidad.currentIndexChanged.connect(self._filtro_tecnico_cat_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_cat_especialidad,
            "Filtrar tareas por el área técnica a la que están restringidas (Politécnico)")
        self.lbl_filtro_cat_carrera= QLabel("Carrera:")
        self.combo_filtro_cat_carrera= QComboBox()
        self.combo_filtro_cat_carrera.currentIndexChanged.connect(self._filtro_tecnico_cat_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_cat_carrera,
            "Filtrar tareas por la carrera a la que están restringidas (Universidad)")
        self.lbl_filtro_cat_materia= QLabel("Materia (opcional):")
        self.combo_filtro_cat_materia= QComboBox()
        #_: índice nuevo del combo (no se usa); lambda que solo llama a _filtro_cat_cambio sin
        #argumentos.
        self.combo_filtro_cat_materia.currentIndexChanged.connect(lambda _: self._filtro_cat_cambio())
        self._construir_dialogo_filtros_tareas()

        return contenedor

    #Ventanita (no modal) con los filtros del CATÁLOGO de tareas — Curso,
    #Sección, Área Técnica, Carrera y Materia, todos opcionales. Mismo
    #patrón que usan calendario.py/estudiantes.py/horario.py: los combos
    #viven aquí para no apilarlos en la pantalla principal, y la tabla de
    #atrás se sigue actualizando en vivo mientras el diálogo queda abierto.
    #Una tarea sin alcance restringido (curso/sección/área técnica/carrera
    #en "Todos") se sigue mostrando con cualquier filtro elegido, porque
    #significa que aplica a todo el mundo.
    def _construir_dialogo_filtros_tareas(self):

        self.dialogo_filtros_tareas= QDialog(self)
        self.dialogo_filtros_tareas.setObjectName("DialogoFiltros")
        self.dialogo_filtros_tareas.setWindowTitle("Filtros del Catálogo de Tareas")
        aplicar_icono_ventana(self.dialogo_filtros_tareas, ICONO_FILTRO)
        self.dialogo_filtros_tareas.setModal(False)
        self.dialogo_filtros_tareas.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_tareas)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)
        #Sin esto, el diálogo no se reduce cuando alguna fila (p. ej. Área Técnica/Carrera) se oculta por no aplicar a
        #la institución, y deja una franja en blanco al final de la ventana.
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

        lbl_subtitulo= QLabel("Todos son opcionales: combina los que necesites, la lista se actualiza al instante. "
                            "Una tarea sin alcance restringido siempre aparece, sin importar el filtro elegido.")
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
        for etiqueta, combo in (
            (None, self.combo_filtro_cat_especialidad),
            (None, self.combo_filtro_cat_carrera),
            ("Curso/Grado:", self.combo_filtro_cat_curso),
            ("Sección:", self.combo_filtro_cat_seccion),
            (None, self.combo_filtro_cat_materia),
        ):
            if combo is self.combo_filtro_cat_especialidad:
                grid.addWidget(self.lbl_filtro_cat_especialidad, fila, 0)
            elif combo is self.combo_filtro_cat_carrera:
                grid.addWidget(self.lbl_filtro_cat_carrera, fila, 0)
            elif combo is self.combo_filtro_cat_materia:
                grid.addWidget(self.lbl_filtro_cat_materia, fila, 0)
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
        btn_limpiar.clicked.connect(self._limpiar_filtros_tareas)
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_tareas.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_tareas(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_tareas.parent() is not _fc:
            self.dialogo_filtros_tareas.setParent(_fc)
        self.dialogo_filtros_tareas.show()
        self.dialogo_filtros_tareas.raise_()
        self.dialogo_filtros_tareas.activateWindow()

    def _limpiar_filtros_tareas(self):

        for combo in (self.combo_filtro_cat_especialidad, self.combo_filtro_cat_carrera,
                      self.combo_filtro_cat_curso):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._filtrar_secciones_cat_por_curso()
        self.combo_filtro_cat_materia.blockSignals(True)
        self.combo_filtro_cat_materia.setCurrentIndex(0)
        self.combo_filtro_cat_materia.blockSignals(False)
        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    #Puebla los 5 combos del diálogo de filtros del Catálogo. Curso y
    #Materia parten en 'Todos' (filtro 100% opcional, a diferencia del
    #Alcance del formulario donde Curso restringe la propia tarea).
    def _cargar_filtros_catalogo(self):

        poblar_combo_curso(self.combo_filtro_cat_curso, incluir_todos=True)
        self._cargar_filtro_tecnico_catalogo()
        self._filtrar_secciones_cat_por_curso()
        self._cargar_materia_filtro_catalogo()

    def _cargar_filtro_tecnico_catalogo(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_cat_especialidad.setVisible(es_poli)
        self.combo_filtro_cat_especialidad.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_cat_especialidad.currentData()
            self.combo_filtro_cat_especialidad.blockSignals(True)
            self.combo_filtro_cat_especialidad.clear()
            self.combo_filtro_cat_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_cat_especialidad.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_cat_especialidad.findData(actual)
            self.combo_filtro_cat_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_cat_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_cat_carrera.setVisible(es_uni)
        self.combo_filtro_cat_carrera.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_cat_carrera.currentData()
            self.combo_filtro_cat_carrera.blockSignals(True)
            self.combo_filtro_cat_carrera.clear()
            self.combo_filtro_cat_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_cat_carrera.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_cat_carrera.findData(actual)
            self.combo_filtro_cat_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_cat_carrera.blockSignals(False)

    def _filtro_tecnico_cat_cambio(self):

        self._filtrar_secciones_cat_por_curso()
        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    def _cargar_materia_filtro_catalogo(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_cat_materia.setText(
            "Materia / Módulo Técnico (opcional):" if es_poli else "Materia (opcional):")
        especialidad_id= self.combo_filtro_cat_especialidad.currentData() if es_poli else None
        actual= self.combo_filtro_cat_materia.currentData()
        self.combo_filtro_cat_materia.blockSignals(True)
        self.combo_filtro_cat_materia.clear()
        self.combo_filtro_cat_materia.addItem(
            "Todas las materias / módulos" if es_poli else "Todas las materias", None)
        conn= obtener_conexion()
        c= conn.cursor()
        if especialidad_id is not None:
            c.execute("""SELECT id, nombre FROM materias
                         WHERE estado='Activa' AND especialidad_id=? ORDER BY nombre""", (especialidad_id,))
        else:
            c.execute("SELECT id, nombre FROM materias WHERE estado='Activa' ORDER BY nombre")
        for fila in c.fetchall():
            self.combo_filtro_cat_materia.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= self.combo_filtro_cat_materia.findData(actual)
        self.combo_filtro_cat_materia.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filtro_cat_materia.blockSignals(False)

    def _curso_filtro_cat_cambio(self):

        self._filtrar_secciones_cat_por_curso()
        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    def _filtro_cat_cambio(self):

        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    #Filtro 100% opcional (a diferencia del Alcance del formulario):
    #se puede filtrar por Sección sin elegir Curso, o al revés. Si además
    #hay un Área Técnica/Carrera elegidos, la lista de secciones se acota
    #más -mismo criterio que en calendario.py.
    def _filtrar_secciones_cat_por_curso(self):

        cascada_seccion_por_curso(self.combo_filtro_cat_curso, self.combo_filtro_cat_seccion, incluir_todas=True)
        especialidad_id= (self.combo_filtro_cat_especialidad.currentData()
                            if self._es_politecnico() else None)
        carrera_id= self.combo_filtro_cat_carrera.currentData() if self._es_universidad() else None
        if especialidad_id is not None or carrera_id is not None:
            secciones_carrera= None
            if carrera_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                             WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
                secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
                conn.close()
            actual= self.combo_filtro_cat_seccion.currentData()
            for i in range(self.combo_filtro_cat_seccion.count() - 1, 0, -1):
                seccion_id= self.combo_filtro_cat_seccion.itemData(i)
                if seccion_id is None:
                    continue
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT especialidad_id FROM secciones WHERE id=?", (seccion_id,))
                fila_sec= c.fetchone()
                conn.close()
                especialidad_seccion= fila_sec["especialidad_id"] if fila_sec else None
                if especialidad_id is not None and especialidad_seccion != especialidad_id:
                    self.combo_filtro_cat_seccion.removeItem(i)
                    continue
                if secciones_carrera is not None and seccion_id not in secciones_carrera:
                    self.combo_filtro_cat_seccion.removeItem(i)
            idx= self.combo_filtro_cat_seccion.findData(actual)
            self.combo_filtro_cat_seccion.setCurrentIndex(idx if idx >= 0 else 0)

    #Botón extra del diálogo 'Detalle de la Tarea': la descripción no es
    #columna de la tabla (se quedaría corta/truncada ahí), así que se
    #consulta aparte y se muestra completa en su propia ventana.
    def _boton_ver_descripcion_tarea(self, fila):

        id_item= self.tabla_tareas.item(fila, 0)
        if id_item is None:
            return []
        id_t= int(id_item.text())

        def _abrir_descripcion():

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT descripcion FROM tareas WHERE id=?", (id_t,))
            fila_bd= c.fetchone()
            conn.close()
            texto= fila_bd["descripcion"] if fila_bd else ""
            mostrar_texto_largo(self, "Descripción de la Tarea", texto)

        return [("Ver Descripción completa", _abrir_descripcion)]

    def _guardar_tarea(self):

        if not self.in_titulo.text().strip():
            mostrar_mensaje("advertencia", "Datos incompletos", "El título de la tarea es obligatorio.", self)
            return
        materia_id= self.combo_materia.currentData()
        if materia_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona una materia.", self)
            return
        profesor_id= obtener_profesor_id(self.main_window)
        competencias_txt= ", ".join(self._competencias_tarea_seleccionadas) if es_sistema_dominicano(
            _sistema_calificacion_actual()) else ""
        curso_id_tarea= self.combo_curso_tarea.currentData()
        seccion_id_tarea= self.combo_seccion_tarea.currentData()
        #Área Técnica/Carrera dejan de ser "alcance opcional" y pasan a ser OBLIGATORIAS cuando la institución es
        #puramente Politécnico o puramente Universidad (o "Personalizado" con solo uno de los dos módulos activo): en
        #esos casos toda tarea pertenece necesariamente a un área técnica/carrera, así que dejarla sin elegir dejaría
        #el alcance ambiguo. Si "Personalizado" tiene AMBOS módulos activos a la vez, ninguno de los dos es obligatorio
        #-mismo criterio que en el guardado de Estudiantes-.
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        if self._es_politecnico() and not ambos_activos and self.combo_filtro_especialidad_tarea.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica de la tarea.", self)
            return
        if self._es_universidad() and not ambos_activos and self.combo_filtro_carrera_tarea.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera de la tarea.", self)
            return
        especialidad_id_tarea= (self.combo_filtro_especialidad_tarea.currentData()
                                  if self._es_politecnico() else None)
        carrera_id_tarea= self.combo_filtro_carrera_tarea.currentData() if self._es_universidad() else None
        datos= (
            materia_id, self.combo_periodo.currentData(), profesor_id,
            self.in_titulo.text().strip(), self.in_descripcion.toPlainText().strip(),
            self.combo_categoria.currentText(),
            self.date_asignacion.date().toString("yyyy-MM-dd"),
            self.date_entrega.date().toString("yyyy-MM-dd"),
            self.spin_peso.value(), self.spin_valor_max.value(), self.combo_estado_tarea.currentText(),
            competencias_txt, curso_id_tarea, seccion_id_tarea, especialidad_id_tarea, carrera_id_tarea,
        )
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            if self.id_edicion_tarea is None:
                c.execute("""INSERT INTO tareas (materia_id, periodo_id, profesor_id, titulo, descripcion,
                             categoria, fecha_asignacion, fecha_entrega, peso, valor_maximo, estado, competencias,
                             curso_id, seccion_id, especialidad_id, carrera_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", datos)
                tarea_id_guardada= c.lastrowid
                accion= "Creó tarea en Banco de Tareas"
            else:
                c.execute("""UPDATE tareas SET materia_id=?, periodo_id=?, profesor_id=?, titulo=?, descripcion=?,
                             categoria= ?, fecha_asignacion=?, fecha_entrega=?, peso=?, valor_maximo=?, estado=?,
                             competencias= ?, curso_id=?, seccion_id=?, especialidad_id=?, carrera_id=?
                             WHERE id=?""", datos + (self.id_edicion_tarea,))
                tarea_id_guardada= self.id_edicion_tarea
                accion= "Editó tarea en Banco de Tareas"
            if es_sistema_dominicano(_sistema_calificacion_actual()):
                #Sincroniza el vínculo tarea <-> Competencias Específicas (motor curricular
                #dinámico). Se guarda como plantilla; al calificar una entrega, se copia a calificacion_competencia para que la
                #evidencia quede vinculada automáticamente.
                c.execute("DELETE FROM tarea_competencia WHERE tarea_id=?", (tarea_id_guardada,))
                for competencia_id in self._ce_tarea_seleccionadas:
                    c.execute("INSERT OR IGNORE INTO tarea_competencia (tarea_id, competencia_id) VALUES (?,?)",
                              (tarea_id_guardada, competencia_id))
            #Igual que arriba, pero para el modelo técnico (Politécnico): sincroniza el
            #vínculo tarea <-> Resultados de Aprendizaje. Se guarda como plantilla; al
            #calificar una entrega se copia hacia calificacion_ra (ver _calificar_entrega).
            if self._materia_es_tecnica(materia_id):
                c.execute("DELETE FROM tarea_ra WHERE tarea_id=?", (tarea_id_guardada,))
                for ra_id in self._ra_tarea_seleccionadas:
                    c.execute("INSERT OR IGNORE INTO tarea_ra (tarea_id, resultado_aprendizaje_id) VALUES (?,?)",
                              (tarea_id_guardada, ra_id))
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar la tarea:\n{error}", self)
            return
        registrar_auditoria("Banco de Tareas", accion, self.main_window.usuario_actual, self.in_titulo.text().strip())
        mostrar_mensaje("exito", "Guardado", "La tarea se guardó correctamente.", self)
        self._pulso_exito(self.btn_guardar_tarea, "¡Guardado!")
        self._limpiar_tarea()
        self._cargar_tareas()
        self._cargar_combo_tareas_entrega()

    def _elegir_competencias_tarea(self):

        dialogo= DialogoCompetencias(self._competencias_tarea_seleccionadas, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._competencias_tarea_seleccionadas= dialogo.seleccionadas()
            self._actualizar_boton_competencias()

    def _actualizar_boton_competencias(self):

        cantidad= len(self._competencias_tarea_seleccionadas)
        if cantidad == 0:
            self.btn_competencias_tarea.setText("Seleccionar competencias")
        elif cantidad == 1:
            self.btn_competencias_tarea.setText(f"🎯 {self._competencias_tarea_seleccionadas[0]}")
        else:
            self.btn_competencias_tarea.setText(f"🎯 {cantidad} competencias seleccionadas")

    def _elegir_ce_tarea(self):

        materia_id= self.combo_materia.currentData()
        if materia_id is None:
            mostrar_mensaje("advertencia", "Falta la materia", "Selecciona primero una materia.", self)
            return
        dialogo= DialogoCompetenciasEspecificasTarea(materia_id, self._ce_tarea_seleccionadas, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._ce_tarea_seleccionadas= dialogo.seleccionadas()
            self._actualizar_boton_ce_tarea()

    def _actualizar_boton_ce_tarea(self):

        cantidad= len(self._ce_tarea_seleccionadas)
        if cantidad == 0:
            self.btn_ce_tarea.setText("Vincular a Competencias Específicas")
        elif cantidad == 1:
            self.btn_ce_tarea.setText("1 Competencia Específica vinculada")
        else:
            self.btn_ce_tarea.setText(f"🧩 {cantidad} Competencias Específicas vinculadas")

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo). Mismo criterio usado en estudiantes.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la materia usa el modelo técnico (Resultados de Aprendizaje),
    #el mismo criterio que usa calificaciones_tecnicas.py para decidir qué
    #materias aparecen ahí en vez de en Calificaciones normal.
    def _materia_es_tecnica(self, materia_id):

        if materia_id is None:
            return False
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT modelo_evaluacion FROM materias WHERE id=?", (materia_id,))
        fila= c.fetchone()
        conn.close()
        return bool(fila) and fila["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA

    #Ajusta labels, tooltips y encabezados que mencionan 'Materia' para que
    #también reflejen 'Módulo Técnico' cuando la institución es Politécnico —
    #igual que hace materias.py (p. ej. 'Materia / Módulo Técnico' en Horario).
    #En una institución que no es Politécnico, todo queda con el texto
    #original ('Materia' a secas), ya que ahí nunca existen módulos técnicos.
    def _actualizar_textos_politecnico(self):

        es_poli= self._es_politecnico()
        texto_materia= "Materia / Módulo Técnico:" if es_poli else "Materia:"
        self.lbl_materia_tarea_form.setText(texto_materia)
        self.combo_materia.setToolTip(
            "Materia (o Módulo Técnico, si la institución es Politécnico) a la que pertenece esta tarea"
            if es_poli else "Materia a la que pertenece esta tarea")

        self.tabla_tareas.setHorizontalHeaderItem(1, QTableWidgetItem(
            "Materia / Módulo" if es_poli else "Materia"))
        self.tabla_tareas.setHorizontalHeaderItem(7, QTableWidgetItem(
            "Competencia(s) / RA" if es_poli else "Competencia(s)"))

        self.lbl_materia_filtro_entrega.setText("Materia / Módulo:" if es_poli else "Materia:")
        self.combo_materia_filtro_entrega.setToolTip(
            "Filtra la lista de tareas por materia o módulo técnico antes de elegir cuál revisar"
            if es_poli else "Filtra la lista de tareas por materia antes de elegir cuál revisar")
        self.chk_solo_tecnicos_entrega.setVisible(es_poli)
        if not es_poli and self.chk_solo_tecnicos_entrega.isChecked():
            self.chk_solo_tecnicos_entrega.blockSignals(True)
            self.chk_solo_tecnicos_entrega.setChecked(False)
            self.chk_solo_tecnicos_entrega.blockSignals(False)

        self.lbl_tarea_filtro_entrega.setText("Tarea / Módulo:" if es_poli else "Tarea:")
        self.combo_tarea_entrega.setToolTip(
            "Tarea (académica o de módulo técnico) de la que se listan las entregas de los estudiantes"
            if es_poli else "Tarea de la que se listan las entregas de los estudiantes")
        if hasattr(self, "tarjeta_top_entregas") and hasattr(self.tarjeta_top_entregas, "lbl_desc"):
            if es_poli:
                self.tarjeta_top_entregas.lbl_desc.setText(
                    "Elige el curso y la sección para acotar de dónde salen los estudiantes, y luego pulsa "
                    "\"Generar/Actualizar Lista\". Solo se toman estudiantes activos de secciones donde "
                    "además se imparte la materia o módulo técnico de la tarea (según Horarios). Usa "
                    "\" Solo módulos técnicos\" para encontrar rápido las entregas de un módulo técnico."
                    "Doble clic en una fila para ver el detalle.")
            else:
                self.tarjeta_top_entregas.lbl_desc.setText(
                    "Elige el curso y la sección para acotar de dónde salen los estudiantes, "
                    "y luego pulsa \"Generar/Actualizar Lista\". Solo se toman estudiantes activos "
                    "de secciones donde además se imparte la materia de la tarea (según Horarios). "
                    "Doble clic en una fila para ver el detalle.")

    #Alterna entre el botón de Competencias Específicas (currículo por
    #competencias, MINERD) y el de Resultados de Aprendizaje (módulo técnico
    #de Politécnico) según el modelo de evaluación de la materia elegida en
    #el formulario. Nunca se muestran los dos a la vez para una misma tarea
    #(se controla con self.stack_ce_ra_tarea, no con .setVisible() suelto en
    #cada botón, para que sea imposible que ambos rendericen superpuestos).
    def _actualizar_visibilidad_ce_ra(self):

        materia_id= self.combo_materia.currentData()
        es_tecnica= self._materia_es_tecnica(materia_id)
        dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        mostrar_ra= es_tecnica
        mostrar_ce= dominicano and not es_tecnica
        if mostrar_ra:
            self.stack_ce_ra_tarea.setCurrentWidget(self.btn_ra_tarea)
        elif mostrar_ce:
            self.stack_ce_ra_tarea.setCurrentWidget(self.btn_ce_tarea)
        self.stack_ce_ra_tarea.setVisible(mostrar_ra or mostrar_ce)
        if not es_tecnica and self._ra_tarea_seleccionadas:
            self._ra_tarea_seleccionadas= []
            self._actualizar_boton_ra_tarea()

    def _elegir_ra_tarea(self):

        materia_id= self.combo_materia.currentData()
        if materia_id is None:
            mostrar_mensaje("advertencia", "Falta la materia", "Selecciona primero una materia.", self)
            return
        dialogo= DialogoResultadosAprendizajeTarea(materia_id, self._ra_tarea_seleccionadas, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._ra_tarea_seleccionadas= dialogo.seleccionadas()
            self._actualizar_boton_ra_tarea()

    def _actualizar_boton_ra_tarea(self):

        cantidad= len(self._ra_tarea_seleccionadas)
        if cantidad == 0:
            self.btn_ra_tarea.setText("Vincular a Resultados de Aprendizaje (RA)")
        elif cantidad == 1:
            self.btn_ra_tarea.setText("1 Resultado de Aprendizaje vinculado")
        else:
            self.btn_ra_tarea.setText(f"📐 {cantidad} Resultados de Aprendizaje vinculados")

    def _limpiar_tarea(self):

        self.id_edicion_tarea= None
        self.in_titulo.clear()
        self.in_descripcion.clear()
        self.combo_categoria.setCurrentIndex(0)
        self.date_asignacion.setDate(QDate.currentDate())
        self.date_entrega.setDate(QDate.currentDate().addDays(7))
        self.spin_peso.setValue(0)
        self.spin_valor_max.setValue(100)
        self.combo_estado_tarea.setCurrentIndex(0)
        self._competencias_tarea_seleccionadas= []
        self._actualizar_boton_competencias()
        self._ce_tarea_seleccionadas= []
        self._actualizar_boton_ce_tarea()
        self._ra_tarea_seleccionadas= []
        self._actualizar_boton_ra_tarea()
        self._actualizar_visibilidad_ce_ra()
        self.combo_curso_tarea.setCurrentIndex(0)
        self._curso_tarea_cambio()
        if self._es_politecnico():
            self.combo_filtro_especialidad_tarea.setCurrentIndex(0)
        if self._es_universidad():
            self.combo_filtro_carrera_tarea.setCurrentIndex(0)
        desactivar_modo_edicion(self.in_titulo)

    def _cargar_tarea_seleccionada(self):

        fila= self.tabla_tareas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una tarea de la tabla.", self)
            return
        id_t= int(self.tabla_tareas.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM tareas WHERE id=?", (id_t,))
        #f: fila de la tarea (SELECT * FROM tareas) con sus datos; None si no existe.
        f= c.fetchone()
        c.execute("SELECT competencia_id FROM tarea_competencia WHERE tarea_id=?", (id_t,))
        #r: cada fila de tarea_competencia; se guarda su competencia_id en la lista de competencias
        #seleccionadas.
        self._ce_tarea_seleccionadas= [r["competencia_id"] for r in c.fetchall()]
        c.execute("SELECT resultado_aprendizaje_id FROM tarea_ra WHERE tarea_id=?", (id_t,))
        #r: cada fila de tarea_ra; se guarda su resultado_aprendizaje_id en la lista de RA
        #seleccionados.
        self._ra_tarea_seleccionadas= [r["resultado_aprendizaje_id"] for r in c.fetchall()]
        conn.close()
        if not f:
            return
        self.id_edicion_tarea= f["id"]
        if hasattr(self, "panel_form_tarea"):
            self.panel_form_tarea.expandir(True, animar=False)  #de golpe al editar
        idx= self.combo_materia.findData(f["materia_id"])
        self.combo_materia.setCurrentIndex(idx if idx >= 0 else 0)
        self.in_titulo.setText(f["titulo"] or "")
        self.in_descripcion.setPlainText(f["descripcion"] or "")
        self.combo_categoria.setCurrentText(f["categoria"] or "Tarea")
        idxp= self.combo_periodo.findData(f["periodo_id"])
        self.combo_periodo.setCurrentIndex(idxp if idxp >= 0 else 0)
        if f["fecha_asignacion"]:
            self.date_asignacion.setDate(QDate.fromString(f["fecha_asignacion"], "yyyy-MM-dd"))
        if f["fecha_entrega"]:
            self.date_entrega.setDate(QDate.fromString(f["fecha_entrega"], "yyyy-MM-dd"))
        self.spin_peso.setValue(f["peso"] or 0)
        self.spin_valor_max.setValue(f["valor_maximo"] or 100)
        self.combo_estado_tarea.setCurrentText(f["estado"] or "Activa")
        try:

            competencias_guardadas= f["competencias"] or ""
        except (KeyError, IndexError):
            competencias_guardadas= ""
        self._competencias_tarea_seleccionadas= [c.strip() for c in competencias_guardadas.split(",") if c.strip()]
        self._actualizar_boton_competencias()
        self._actualizar_boton_ce_tarea()
        self._actualizar_boton_ra_tarea()
        self._actualizar_visibilidad_ce_ra()

        #Alcance guardado (puede no existir en bases muy viejas antes de la migración de columnas — de ahí el
        #try/except defensivo).
        try:

            curso_guardado= f["curso_id"]
            seccion_guardada= f["seccion_id"]
            especialidad_guardada= f["especialidad_id"]
            carrera_guardada= f["carrera_id"]
        except (KeyError, IndexError):
            curso_guardado= seccion_guardada= especialidad_guardada= carrera_guardada= None
        idxc= self.combo_curso_tarea.findData(curso_guardado)
        self.combo_curso_tarea.setCurrentIndex(idxc if idxc >= 0 else 0)
        self._curso_tarea_cambio()
        idxs= self.combo_seccion_tarea.findData(seccion_guardada)
        self.combo_seccion_tarea.setCurrentIndex(idxs if idxs >= 0 else 0)
        if self._es_politecnico():
            idxe= self.combo_filtro_especialidad_tarea.findData(especialidad_guardada)
            self.combo_filtro_especialidad_tarea.setCurrentIndex(idxe if idxe >= 0 else 0)
        if self._es_universidad():
            idxca= self.combo_filtro_carrera_tarea.findData(carrera_guardada)
            self.combo_filtro_carrera_tarea.setCurrentIndex(idxca if idxca >= 0 else 0)
        activar_modo_edicion(self.in_titulo, f"Editando tarea: {f['titulo'] or ''}")

    def _filtro_tareas_cambio(self, texto=""):

        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    def _eliminar_tarea(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede eliminar tareas.", self)
            return
        fila= self.tabla_tareas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una tarea de la tabla.", self)
            return
        id_t= int(self.tabla_tareas.item(fila, 0).text())
        titulo= self.tabla_tareas.item(fila, 2).text()
        if mostrar_mensaje("pregunta", "Confirmar",
                          f"¿Eliminar la tarea '{titulo}'? Esto también elimina sus registros de entrega "
                          "(las calificaciones ya generadas NO se eliminan).", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM tareas WHERE id=?", (id_t,))
        conn.commit()
        conn.close()
        registrar_auditoria("Banco de Tareas", "Eliminó tarea", self.main_window.usuario_actual, titulo)
        self._cargar_tareas()
        self._cargar_combo_tareas_entrega()

    def _materias_permitidas_ids(self):

        return obtener_materias_permitidas(self.main_window)

    def _cargar_combo_materias(self):

        self.combo_materia.clear()
        permitidas= self._materias_permitidas_ids()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, codigo, nombre, modelo_evaluacion FROM materias WHERE estado='Activa' ORDER BY nombre")
        for fila in c.fetchall():
            if permitidas is not None and fila["id"] not in permitidas:
                continue
            etiqueta= fila["nombre"] + (f" ({fila['codigo']})" if fila["codigo"] else "")
            if fila["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA:
                etiqueta= f"🛠 {etiqueta}"
            self.combo_materia.addItem(etiqueta, fila["id"])
        conn.close()

    def _cargar_combo_periodos(self):

        for combo in (self.combo_periodo,):
            combo.clear()
            combo.addItem("Sin periodo específico", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
        for fila in c.fetchall():
            self.combo_periodo.addItem(fila["nombre"], fila["id"])
        conn.close()

    #Clasifica una tarea en vencida / por_vencer (≤7 días) / vigente /
    #archivada. Es la única fuente de verdad para la barra de resumen, la
    #leyenda, la cinta de alertas y la columna 'Estado' de la tabla.
    @staticmethod
    def _clasificar_tarea(tarea):

        if tarea["estado"] != "Activa":
            return "archivada"
        if not tarea["fecha_entrega"]:
            return "vigente"
        try:

            fecha= datetime.strptime(tarea["fecha_entrega"], "%Y-%m-%d").date()
        except ValueError:
            return "vigente"
        hoy= datetime.now().date()
        if fecha < hoy:
            return "vencida"
        if fecha <= hoy + timedelta(days=7):
            return "por_vencer"
        return "vigente"

    def _cargar_tareas(self):

        texto= _normalizar_texto(self.in_buscar_tareas.text().strip())
        permitidas= self._materias_permitidas_ids()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT tareas.*, materias.nombre as materia_nombre, materias.modelo_evaluacion
                     FROM tareas LEFT JOIN materias ON tareas.materia_id = materias.id
                     ORDER BY tareas.fecha_entrega DESC, tareas.id DESC""")
        filas= c.fetchall()
        #Nombres para la columna "Alcance" (curso/sección/área técnica/carrera que cada tarea tiene restringidos, si
        #tiene alguno). Se cargan una sola vez por refresco de tabla, no por fila, para no golpear la BD.
        c.execute("SELECT id, nombre FROM grados")
        self._nombres_grado_tarea= {fila["id"]: fila["nombre"] for fila in c.fetchall()}
        c.execute("SELECT id, nombre FROM secciones")
        self._nombres_seccion_tarea= {fila["id"]: fila["nombre"] for fila in c.fetchall()}
        c.execute("SELECT id, nombre FROM especialidades")
        self._nombres_especialidad_tarea= {fila["id"]: fila["nombre"] for fila in c.fetchall()}
        c.execute("SELECT id, nombre FROM carreras")
        self._nombres_carrera_tarea= {fila["id"]: fila["nombre"] for fila in c.fetchall()}
        #RA vinculados por tarea (solo aplica a materias con modelo técnico), para mostrarlos en la columna
        #"Competencia(s) / RA" igual que se hace con las CE.
        c.execute("""SELECT tarea_ra.tarea_id, resultados_aprendizaje.codigo
                     FROM tarea_ra JOIN resultados_aprendizaje
                          ON tarea_ra.resultado_aprendizaje_id = resultados_aprendizaje.id
                     ORDER BY resultados_aprendizaje.orden, resultados_aprendizaje.codigo""")
        ra_por_tarea= {}
        for fila in c.fetchall():
            ra_por_tarea.setdefault(fila["tarea_id"], []).append(fila["codigo"])
        conn.close()
        #Conjunto permitido por rol, ANTES del texto de búsqueda: sirve tanto para paginar el resultado filtrado como
        #para el resumen (barra + leyenda + alertas), que muestra el panorama general sin depender de lo que se esté
        #buscando en ese momento.
        permitidas_lista= [fila for fila in filas if permitidas is None or fila["materia_id"] in permitidas]
        self._actualizar_resumen_tareas(permitidas_lista)

        filtradas= permitidas_lista
        if texto:
            filtradas= [filtrada for filtrada in filtradas if texto in _normalizar_texto(
                        f"{filtrada['titulo'] or ''} {filtrada['materia_nombre'] or ''} {filtrada['categoria'] or ''} "
                        f"{self._valor_columna(filtrada, 'competencias') or ''}")]
        if self._filtro_tareas:
            filtradas= [filtrada for filtrada in filtradas if self._clasificar_tarea(filtrada) == self._filtro_tareas]

        #Filtros de Curso/Sección/Área Técnica/Carrera/Materia (diálogo "☰ Filtros"):
        #una tarea sin ese dato restringido (None) siempre pasa el filtro, porque significa que su alcance es "Todos"
        #-aplica sin importar qué se filtre-.
        curso_id_f= self.combo_filtro_cat_curso.currentData() if hasattr(self, "combo_filtro_cat_curso") else None
        seccion_id_f= (self.combo_filtro_cat_seccion.currentData()
                        if hasattr(self, "combo_filtro_cat_seccion") else None)
        especialidad_id_f= (self.combo_filtro_cat_especialidad.currentData()
                              if hasattr(self, "combo_filtro_cat_especialidad") and self._es_politecnico() else None)
        carrera_id_f= (self.combo_filtro_cat_carrera.currentData()
                        if hasattr(self, "combo_filtro_cat_carrera") and self._es_universidad() else None)
        materia_id_f= (self.combo_filtro_cat_materia.currentData()
                        if hasattr(self, "combo_filtro_cat_materia") else None)

        #f: fila de tarea a evaluar; devuelve True si cumple los filtros de curso, sección, área,
        #carrera y materia.
        def _pasa_filtro_alcance(f):

            try:

                curso_id_t, seccion_id_t= f["curso_id"], f["seccion_id"]
                especialidad_id_t, carrera_id_t= f["especialidad_id"], f["carrera_id"]
            except (KeyError, IndexError):
                curso_id_t= seccion_id_t= especialidad_id_t= carrera_id_t= None
            if curso_id_f is not None and curso_id_t is not None and curso_id_t != curso_id_f:
                return False
            if seccion_id_f is not None and seccion_id_t is not None and seccion_id_t != seccion_id_f:
                return False
            if especialidad_id_f is not None and especialidad_id_t is not None and especialidad_id_t != especialidad_id_f:
                return False
            if carrera_id_f is not None and carrera_id_t is not None and carrera_id_t != carrera_id_f:
                return False
            if materia_id_f is not None and f["materia_id"] != materia_id_f:
                return False
            return True

        if curso_id_f is not None or seccion_id_f is not None or especialidad_id_f is not None\
                or carrera_id_f is not None or materia_id_f is not None:
            filtradas= [filtrada for filtrada in filtradas if _pasa_filtro_alcance(filtrada)]

        self.paginacion_tareas.establecer_total(len(filtradas))
        inicio, fin= self.paginacion_tareas.rango_actual()
        pagina= filtradas[inicio:fin]

        #setUpdatesEnabled(False) evita repintar la tabla en cada setItem();
        #con altura de fila fija ya no hace falta resizeRowsToContents() (medir cada celda es lo más costoso al
        #refrescar una tabla grande).
        self.tabla_tareas.setUpdatesEnabled(False)
        try:

            self.tabla_tareas.setRowCount(len(pagina))
            #i: número de fila de la tabla; f: fila (registro) de la tarea de la página actual que
            #se pinta en ella.
            for i, f in enumerate(pagina):
                self.tabla_tareas.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                nombre_materia= f["materia_nombre"] or ""
                if f["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA and nombre_materia:
                    nombre_materia= f"🛠 {nombre_materia}"
                self.tabla_tareas.setItem(i, 1, QTableWidgetItem(nombre_materia))
                item_titulo= QTableWidgetItem(f["titulo"] or "")
                item_titulo.setToolTip(f["titulo"] or "")
                self.tabla_tareas.setItem(i, 2, item_titulo)
                self.tabla_tareas.setItem(i, 3, _item_oculto(f["categoria"] or ""))
                self.tabla_tareas.setCellWidget(i, 3, _crear_chip(
                    f["categoria"] or "", COLORES_CATEGORIA.get(f["categoria"], COLOR_NEUTRO)))
                self.tabla_tareas.setItem(i, 4, QTableWidgetItem(formatear_fecha(f["fecha_entrega"], self.main_window)))
                self.tabla_tareas.setItem(i, 5, QTableWidgetItem(f"{f['peso'] or 0:.0f}%"))
                clave_estado= self._clasificar_tarea(f)
                self.tabla_tareas.setItem(i, 6, _item_oculto(ETIQUETAS_ESTADO_TAREA[clave_estado]))
                self.tabla_tareas.setCellWidget(i, 6, _crear_chip(
                    ETIQUETAS_ESTADO_TAREA[clave_estado], COLORES_ESTADO_TAREA[clave_estado]))
                competencias_txt= self._valor_columna(f, "competencias") or ""
                if f["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA:
                    competencias_txt= ", ".join(ra_por_tarea.get(f["id"], []))
                item_comp= QTableWidgetItem(competencias_txt)
                if competencias_txt:
                    item_comp.setToolTip(competencias_txt)
                self.tabla_tareas.setItem(i, 7, item_comp)
                self.tabla_tareas.setItem(i, 8, QTableWidgetItem(self._texto_alcance_tarea(f)))
            ajustar_anchos_columnas(self.tabla_tareas)
        finally:
            self.tabla_tareas.setUpdatesEnabled(True)

    #Texto corto para la columna 'Alcance': qué curso/sección/área
    #técnica/carrera tiene restringidos esta tarea, o 'Todas las
    #secciones' si no tiene ninguna restricción (comportamiento de
    #siempre: la fecha de entrega es la misma para toda la materia).
    def _texto_alcance_tarea(self, f):

        try:

            curso_id, seccion_id= f["curso_id"], f["seccion_id"]
            especialidad_id, carrera_id= f["especialidad_id"], f["carrera_id"]
        except (KeyError, IndexError):
            return "Todas las secciones"
        partes= []
        if seccion_id is not None:
            curso_nombre= self._nombres_grado_tarea.get(curso_id, "")
            seccion_nombre= self._nombres_seccion_tarea.get(seccion_id, "")
            partes.append(f"{curso_nombre} {seccion_nombre}".strip())
        elif curso_id is not None:
            partes.append(self._nombres_grado_tarea.get(curso_id, ""))
        if especialidad_id == 0:
            partes.append("Sin área técnica")
        elif especialidad_id is not None:
            partes.append(self._nombres_especialidad_tarea.get(especialidad_id, ""))
        if carrera_id == 0:
            partes.append("Sin carrera")
        elif carrera_id is not None:
            partes.append(self._nombres_carrera_tarea.get(carrera_id, ""))
        return " · ".join(parte for parte in partes if parte) or "Todas las secciones"

    def _actualizar_resumen_tareas(self, tareas):

        conteo= {"vencida": 0, "por_vencer": 0, "vigente": 0, "archivada": 0}
        for tarea in tareas:
            conteo[self._clasificar_tarea(tarea)] += 1
        self._conteo_tareas_actual= conteo
        total_tareas= sum(conteo.values())
        #Icono de portapapeles dibujado con QPainter (mismo dibujo que ya usa el resto de la app), insertado como <img>
        #inline en vez del emoji real para no depender de una fuente de emojis del sistema.
        self.chip_contador.setText(
            f"{html_icono_emoji('📋', 14)} {total_tareas} tarea{'s' if total_tareas != 1 else ''}")
        self.barra_tareas.establecer_valores(conteo)
        for clave, lbl in self.etiquetas_leyenda_tareas.items():
            lbl.establecer_valor(conteo.get(clave, 0))
        if conteo["vencida"] > 0:
            self.cinta_alerta_tareas.mostrar_mensaje(
                f"⚠ {conteo['vencida']} tarea(s) ya vencieron y siguen activas — revísalas o archívalas.")
        elif conteo["por_vencer"] > 0:
            self.cinta_alerta_tareas.mostrar_mensaje(
                f"⏰ {conteo['por_vencer']} tarea(s) vencen en los próximos 7 días.")
        else:
            self.cinta_alerta_tareas.ocultar()

    def _al_clic_alerta_tareas(self):

        if self._conteo_tareas_actual.get("vencida", 0) > 0:
            self._alternar_filtro_tareas("vencida")
        elif self._conteo_tareas_actual.get("por_vencer", 0) > 0:
            self._alternar_filtro_tareas("por_vencer")

    def _alternar_filtro_tareas(self, valor):

        self._filtro_tareas= None if self._filtro_tareas == valor else valor
        self.barra_tareas.establecer_filtro_activo({self._filtro_tareas} if self._filtro_tareas else None)
        for clave, lbl in self.etiquetas_leyenda_tareas.items():
            lbl.establecer_activa(self._filtro_tareas == clave)
        self.paginacion_tareas.reiniciar()
        self._cargar_tareas()

    #Acceso seguro a una columna de sqlite3.Row que puede no existir en bases de datos
    #antiguas si la migración todavía no corrió (evita KeyError).
    @staticmethod
    def _valor_columna(fila, columna):

        try:

            return fila[columna]
        except (KeyError, IndexError):
            return None

    #Pestaña: Entregas
    def _tab_entregas(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(12)

        self.cinta_alerta_entregas= CintaAlerta()
        self.cinta_alerta_entregas.clicada.connect(lambda: self._alternar_filtro_entregas("atrasadas_no_entregadas"))
        disposicion.addWidget(self.cinta_alerta_entregas)

        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(16)
        self.barra_entregas= BarraSegmentada(SEGMENTOS_ENTREGAS)
        self.barra_entregas.segmento_clicado.connect(self._alternar_filtro_entregas)
        fila_resumen.addWidget(self.barra_entregas, 2)

        leyenda= QHBoxLayout()
        leyenda.setSpacing(2)
        self.etiquetas_leyenda_entregas= {}
        for clave, etiqueta_txt, color in SEGMENTOS_ENTREGAS:
            lbl= EtiquetaContadorClicable(etiqueta_txt, color)
            #c: clave del segmento de la leyenda, fijada con c=clave en cada vuelta; filtra entregas
            #por ese segmento.
            lbl.clicada.connect(lambda c=clave: self._alternar_filtro_entregas(c))
            leyenda.addWidget(lbl)
            self.etiquetas_leyenda_entregas[clave]= lbl
        fila_resumen.addLayout(leyenda, 3)
        disposicion.addLayout(fila_resumen)

        tarjeta_top= TarjetaSeccion(
            icono= "📥", titulo="Tarea a revisar",
            descripcion= "Abre \" Filtros\" para elegir el nivel educativo, curso, sección, área técnica/carrera "
                       "y materia de donde deben salir los estudiantes; luego elige la Tarea/Módulo aquí y pulsa "
                       "\"Generar/Actualizar Lista\". Solo se toman estudiantes activos de secciones donde además "
                       "se imparte la materia de la tarea (según Horarios). Doble clic en una fila para ver el "
                       "detalle.")
        self.tarjeta_top_entregas= tarjeta_top

        #Nivel Educativo, Área Técnica/Carrera, Curso/Sección, Materia y "Solo módulos técnicos" pasan a la ventana de
        #"☰ Filtros" (mismo patrón que Catálogo de Tareas / Calificaciones Técnicas): son los datos que acotan de dónde
        #salen los estudiantes al generar la lista, y ahora también filtran la tabla ya generada, así que viven aparte
        #para no apilar combos en la tarjeta principal. Se crean aquí como atributos normales del módulo; se colocan
        #dentro del diálogo en _construir_dialogo_filtros_entregas.
        self.combo_filtro_nivel_entrega= QComboBox()
        self.combo_filtro_nivel_entrega.currentIndexChanged.connect(self._nivel_entrega_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel_entrega, "Filtrar por nivel educativo (se combina con Curso/Sección)")

        self.lbl_filtro_especialidad_entrega= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_entrega= QComboBox()
        self.combo_filtro_especialidad_entrega.setToolTip(
            "Acota los estudiantes a un área técnica antes de generar la lista, y filtra las entregas ya generadas")
        self.combo_filtro_especialidad_entrega.currentIndexChanged.connect(self._filtro_tecnico_entrega_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_entrega,
            "Acota los estudiantes a un área técnica antes de generar la lista, y filtra las entregas ya generadas")

        self.lbl_filtro_carrera_entrega= QLabel("Carrera:")
        self.combo_filtro_carrera_entrega= QComboBox()
        self.combo_filtro_carrera_entrega.setToolTip(
            "Acota los estudiantes a una carrera antes de generar la lista, y filtra las entregas ya generadas")
        self.combo_filtro_carrera_entrega.currentIndexChanged.connect(self._filtro_tecnico_entrega_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_carrera_entrega,
            "Acota los estudiantes a una carrera antes de generar la lista, y filtra las entregas ya generadas")

        self.combo_curso_entrega= QComboBox()
        self.combo_curso_entrega.setToolTip(
            "Acota los estudiantes a un curso/grado antes de generar la lista, y filtra las entregas ya generadas")
        self.combo_curso_entrega.currentIndexChanged.connect(self._curso_entrega_cambio)

        self.combo_seccion_entrega= QComboBox()
        self.combo_seccion_entrega.setToolTip(
            "Acota los estudiantes a una sección concreta antes de generar la lista, y filtra las entregas ya generadas")
        self.combo_seccion_entrega.currentIndexChanged.connect(self._seccion_entrega_cambio)

        self.lbl_materia_filtro_entrega= QLabel("Materia:")
        self.combo_materia_filtro_entrega= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_filtro_entrega,
            "Filtra la lista de tareas por materia antes de elegir cuál revisar")
        self.combo_materia_filtro_entrega.currentIndexChanged.connect(self._cargar_combo_tareas_entrega)

        self.chk_solo_tecnicos_entrega= QCheckBox("Solo módulos técnicos")
        self.chk_solo_tecnicos_entrega.setToolTip(
            "Muestra solo las tareas/entregas de módulos técnicos (evaluados por Resultados de "
            "Aprendizaje) para encontrarlas rápido entre las materias académicas normales.")
        self.chk_solo_tecnicos_entrega.setVisible(False)
        self.chk_solo_tecnicos_entrega.stateChanged.connect(self._alternar_solo_tecnicos_entrega)

        fila= QHBoxLayout()
        self.lbl_tarea_filtro_entrega= QLabel("Tarea:")
        fila.addWidget(self.lbl_tarea_filtro_entrega)
        self.combo_tarea_entrega= QComboBox()
        conectar_tooltip_seleccion(self.combo_tarea_entrega, "Tarea de la que se listan las entregas de los estudiantes")
        self.combo_tarea_entrega.currentIndexChanged.connect(self._cargar_entregas)
        fila.addWidget(self.combo_tarea_entrega, 1)
        #combo_tarea_entrega se llena con "título de la tarea — materia", que puede ser un texto largo (ver
        #_cargar_combo_tareas_entrega).
        for _combo in (self.combo_curso_entrega, self.combo_seccion_entrega,
                       self.combo_filtro_especialidad_entrega, self.combo_filtro_carrera_entrega,
                       self.combo_materia_filtro_entrega, self.combo_tarea_entrega):
            _combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            _combo.setMinimumContentsLength(16)
        self.btn_generar_entregas= QPushButton("Generar/Actualizar Lista")
        self.btn_generar_entregas.setIcon(icono_emoji("🔄"))
        self.btn_generar_entregas.setIconSize(_QSize_emoji(16, 16))
        self.btn_generar_entregas.setObjectName("BtnAccionAjustar")
        self.btn_generar_entregas.clicked.connect(self._generar_entregas_faltantes)
        fila.addWidget(self.btn_generar_entregas)
        tarjeta_top.contenido.addLayout(fila)
        disposicion.addWidget(tarjeta_top)

        self.lbl_resumen_filtros_entregas= QLabel("")
        self.lbl_resumen_filtros_entregas.setWordWrap(True)
        disposicion.addWidget(self.lbl_resumen_filtros_entregas)

        marco_busqueda_entregas, self.in_buscar_entregas= self._crear_barra_busqueda(
            "Buscar por estudiante o estado de entrega…", self._filtro_entregas_cambio)
        fila_busqueda_entregas= QHBoxLayout()
        fila_busqueda_entregas.addWidget(marco_busqueda_entregas, 1)
        self.btn_filtros_entregas= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_entregas)
        self.btn_filtros_entregas.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_entregas.setObjectName("BtnAccionNeutro")
        self.btn_filtros_entregas.clicked.connect(self._abrir_dialogo_filtros_entregas)
        fila_busqueda_entregas.addWidget(self.btn_filtros_entregas)
        disposicion.addLayout(fila_busqueda_entregas)


        self.tabla_entregas= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_entregas)
        self.estado_vacio_entregas= EstadoVacioFiltro(
            self.tabla_entregas, texto_filtra_primero="Elige una tarea para ver sus entregas")

        self.tabla_entregas.setHorizontalHeaderLabels(
            ["No.", "ID Entrega", "Estudiante", "Estado de Entrega", "Fecha Entrega Real", "Calificación"])
        header= self.tabla_entregas.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.tabla_entregas.setColumnWidth(0, 48)
        self.tabla_entregas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_entregas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_entregas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_entregas.setAlternatingRowColors(True)
        self.tabla_entregas.setWordWrap(False)
        self.tabla_entregas.setShowGrid(False)
        self.tabla_entregas.setMinimumHeight(360)
        self.tabla_entregas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.tabla_entregas.verticalHeader().setVisible(False)
        self.tabla_entregas.verticalHeader().setDefaultSectionSize(ALTURA_FILA)
        disposicion.addWidget(self.tabla_entregas, 1)

        self.paginacion_entregas= ControlPaginacion()
        self.paginacion_entregas.cambio.connect(self._cargar_entregas)
        disposicion.addWidget(self.paginacion_entregas)

        #Botón ⛶ que abre la tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo maximizado
        #-mismo mecanismo que materiales.py, ver agregar_boton_pantalla_completa en paginacion.py-.
        agregar_boton_pantalla_completa(
            None, [self.tabla_entregas, self.paginacion_entregas],
            titulo= "Entregas", parent=self)

        fila_acciones= QHBoxLayout()
        self.btn_cambiar_estado_entrega= QPushButton("Cambiar Estado de Entrega")
        self.btn_cambiar_estado_entrega.setIcon(icono_emoji("📂"))
        self.btn_cambiar_estado_entrega.setIconSize(_QSize_emoji(16, 16))
        self.btn_cambiar_estado_entrega.setObjectName("BtnAccionAjustar")
        self.btn_cambiar_estado_entrega.clicked.connect(self._cambiar_estado_entrega)
        fila_acciones.addWidget(self.btn_cambiar_estado_entrega)
        self.btn_calificar_entrega= QPushButton("Calificar Entrega Seleccionada")
        self.btn_calificar_entrega.setIcon(icono_emoji("➕"))
        self.btn_calificar_entrega.setIconSize(_QSize_emoji(16, 16))
        self.btn_calificar_entrega.setObjectName("BtnAccionAgregar")
        self.btn_calificar_entrega.clicked.connect(self._calificar_entrega)
        fila_acciones.addWidget(self.btn_calificar_entrega)
        btn_detalle_entregas= agregar_boton_detalle(fila_acciones, self.tabla_entregas, self, titulo="Detalle de la Entrega")
        self.tabla_entregas.doubleClicked.connect(lambda *_: btn_detalle_entregas.click())
        fila_acciones.addStretch()
        disposicion.addLayout(fila_acciones)
        disposicion.addStretch()

        self._construir_dialogo_filtros_entregas()

        return contenedor

    #Ventanita (no modal) con TODOS los filtros de la pestaña
    #"Entregas": Nivel Educativo, Área Técnica/Carrera, Curso/Sección,
    #Materia, "Solo módulos técnicos" y Estado de Entrega — mismo patrón
    #que `_construir_dialogo_filtros_tareas` del Catálogo. Nivel/Curso/
    #Sección/Área Técnica/Carrera/Materia determinan a qué estudiantes se
    #les genera la entrega (al pulsar "Generar/Actualizar Lista") y
    #también acotan la tabla ya generada; el combo de Estado de Entrega
    #queda sincronizado en ambas direcciones con la barra segmentada de
    #arriba.
    def _construir_dialogo_filtros_entregas(self):

        self.dialogo_filtros_entregas= QDialog(self)
        self.dialogo_filtros_entregas.setObjectName("DialogoFiltros")
        self.dialogo_filtros_entregas.setWindowTitle("Filtros de Entregas")
        aplicar_icono_ventana(self.dialogo_filtros_entregas, ICONO_FILTRO)
        self.dialogo_filtros_entregas.setModal(False)
        self.dialogo_filtros_entregas.setMinimumWidth(360)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_entregas)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)
        #Igual que en el diálogo de filtros del Catálogo: evita que quede una franja en blanco al final cuando se
        #ocultan filas (Nivel/Área Técnica/Carrera) que no aplican a la institución.
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

        lbl_subtitulo= QLabel("Curso/Grado y Sección acotan de dónde salen los estudiantes al generar la lista "
                            "(con \"Generar/Actualizar Lista\", en la tarjeta de arriba); todos estos filtros "
                            "también acotan la tabla de entregas ya generada.")
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
        grid.addWidget(QLabel("Nivel Educativo:"), fila, 0)
        grid.addWidget(self.combo_filtro_nivel_entrega, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_filtro_especialidad_entrega, fila, 0)
        grid.addWidget(self.combo_filtro_especialidad_entrega, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_filtro_carrera_entrega, fila, 0)
        grid.addWidget(self.combo_filtro_carrera_entrega, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Curso:"), fila, 0)
        grid.addWidget(self.combo_curso_entrega, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Sección:"), fila, 0)
        grid.addWidget(self.combo_seccion_entrega, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_materia_filtro_entrega, fila, 0)
        grid.addWidget(self.combo_materia_filtro_entrega, fila, 1)
        fila += 1
        grid.addWidget(self.chk_solo_tecnicos_entrega, fila, 0, 1, 2)
        fila += 1
        separador2= QFrame()
        separador2.setFrameShape(QFrame.Shape.HLine)
        separador2.setObjectName("SeparadorFiltros")
        grid.addWidget(separador2, fila, 0, 1, 2)
        fila += 1
        grid.addWidget(QLabel("Estado de entrega:"), fila, 0)
        self.combo_filtro_estado_entrega= QComboBox()
        self.combo_filtro_estado_entrega.addItem("Todos los estados", None)
        for clave, etiqueta_txt, _color in SEGMENTOS_ENTREGAS:
            self.combo_filtro_estado_entrega.addItem(etiqueta_txt, clave)
        self.combo_filtro_estado_entrega.addItem("Vencidas y sin entregar", "atrasadas_no_entregadas")
        conectar_tooltip_seleccion(self.combo_filtro_estado_entrega, "Estado de Entrega")
        self.combo_filtro_estado_entrega.currentIndexChanged.connect(self._filtro_estado_entrega_dialogo_cambio)
        grid.addWidget(self.combo_filtro_estado_entrega, fila, 1)
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        btn_limpiar= QPushButton("Limpiar filtros")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(lambda: self._alternar_filtro_entregas(None))
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_entregas.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_entregas(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_entregas.parent() is not _fc:
            self.dialogo_filtros_entregas.setParent(_fc)
        self.dialogo_filtros_entregas.show()
        self.dialogo_filtros_entregas.raise_()
        self.dialogo_filtros_entregas.activateWindow()

    #Como Nivel/Curso/Sección/Área Técnica/Carrera/Materia ahora viven
    #en la ventana de Filtros (oculta por defecto), esta línea deja a la
    #vista, sin abrir el diálogo, qué se está mostrando/generando.
    def _actualizar_resumen_filtros_entregas(self):

        if not hasattr(self, "lbl_resumen_filtros_entregas"):
            return
        partes= []
        if self.combo_filtro_nivel_entrega.currentData() is not None:
            partes.append(f"📊 {self.combo_filtro_nivel_entrega.currentText()}")
        if self.combo_curso_entrega.currentData() is not None:
            partes.append(f"🎓 {self.combo_curso_entrega.currentText()}")
        if self.combo_seccion_entrega.currentData() is not None:
            partes.append(f"🏫 {self.combo_seccion_entrega.currentText()}")
        if self._es_politecnico() and self.combo_filtro_especialidad_entrega.currentData() is not None:
            partes.append(f"🧩 {self.combo_filtro_especialidad_entrega.currentText()}")
        if self._es_universidad() and self.combo_filtro_carrera_entrega.currentData() is not None:
            partes.append(f"🎓 {self.combo_filtro_carrera_entrega.currentText()}")
        if self.combo_materia_filtro_entrega.currentData() is not None:
            partes.append(f"📘 {self.combo_materia_filtro_entrega.currentText()}")
        if self.chk_solo_tecnicos_entrega.isVisible() and self.chk_solo_tecnicos_entrega.isChecked():
            partes.append("Solo módulos técnicos")
        self.lbl_resumen_filtros_entregas.setText(" · ".join(partes) if partes else
            "Sin filtros: elige Curso/Sección en \" Filtros\" para generar la lista.")

    #El combo del diálogo FIJA el estado elegido (a diferencia de
    #`_alternar_filtro_entregas`, que ALTERNA -clic de nuevo en lo mismo
    #lo apaga-, porque en un combo no tiene sentido "volver a elegir lo
    #mismo" para desactivarlo: para eso está la opción 'Todos los
    #estados').
    def _filtro_estado_entrega_dialogo_cambio(self):

        valor= self.combo_filtro_estado_entrega.currentData()
        if valor == self._filtro_entregas:
            return
        self._filtro_entregas= None  #para que el toggle de abajo lo deje justo en `valor`
        self._alternar_filtro_entregas(valor)

    def _al_cambiar_tab(self, indice):

        if self.tabs.tabText(indice).startswith(""):
            self._cargar_combos_curso_seccion_entrega()
            self._cargar_combo_tareas_entrega()

    def _curso_tarea_cambio(self):

        #etiquetas_cortas_sin_curso=True: en este combo el Curso YA está a
        #la vista justo al lado (es el propio "Alcance" de la tarea), así que repetir el curso dentro de cada ítem de
        #Sección ("5to - A") es redundante -alcanza con el nombre corto ("A") como en el resto de combos de Sección de
        #la app-.
        cascada_seccion_por_curso(self.combo_curso_tarea, self.combo_seccion_tarea, incluir_todas=True,
                                   etiquetas_cortas_sin_curso= True)

    #Alcance opcional de la tarea: Curso/Sección con 'Todos' de entrada
    #(a diferencia de Entregas, aquí SÍ debe poder quedar sin restringir),
    #y Área Técnica/Carrera igual que en el resto de la app.
    def _cargar_combos_alcance_tarea(self):

        poblar_combo_curso(self.combo_curso_tarea, incluir_todos=True)
        cascada_seccion_por_curso(self.combo_curso_tarea, self.combo_seccion_tarea, incluir_todas=True,
                                   etiquetas_cortas_sin_curso= True)

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_tarea.setVisible(es_poli)
        self.combo_filtro_especialidad_tarea.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_tarea.currentData()
            self.combo_filtro_especialidad_tarea.blockSignals(True)
            self.combo_filtro_especialidad_tarea.clear()
            self.combo_filtro_especialidad_tarea.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_tarea.addItem(fila["nombre"], fila["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_especialidad_tarea, "No Área Técnica")
            idx= self.combo_filtro_especialidad_tarea.findData(actual)
            self.combo_filtro_especialidad_tarea.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_tarea.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_tarea.setVisible(es_uni)
        self.combo_filtro_carrera_tarea.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_tarea.currentData()
            self.combo_filtro_carrera_tarea.blockSignals(True)
            self.combo_filtro_carrera_tarea.clear()
            self.combo_filtro_carrera_tarea.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_tarea.addItem(fila["nombre"], fila["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_carrera_tarea, "No Carrera")
            idx= self.combo_filtro_carrera_tarea.findData(actual)
            self.combo_filtro_carrera_tarea.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_tarea.blockSignals(False)

    def _cargar_combos_curso_seccion_entrega(self):

        poblar_combo_nivel_educativo(self.combo_filtro_nivel_entrega)
        permitidas= self._secciones_permitidas_con_nivel_entrega()
        poblar_combo_curso(self.combo_curso_entrega, incluir_todos=False, secciones_permitidas=permitidas)
        _acortar_placeholder_combo(self.combo_curso_entrega, "Selecciona un grado")
        self._filtrar_secciones_entrega_por_curso()
        self._cargar_combo_materia_filtro_entrega()

    def _secciones_permitidas_con_nivel_entrega(self):

        permitidas= obtener_secciones_permitidas(self.main_window)
        nivel= self.combo_filtro_nivel_entrega.currentData() if hasattr(self, "combo_filtro_nivel_entrega") else None
        return interseccion_opcional(permitidas, secciones_del_nivel_educativo(nivel))

    def _nivel_entrega_cambio(self):

        permitidas= self._secciones_permitidas_con_nivel_entrega()
        poblar_combo_curso(self.combo_curso_entrega, incluir_todos=False, secciones_permitidas=permitidas)
        _acortar_placeholder_combo(self.combo_curso_entrega, "Selecciona un grado")
        self._filtrar_secciones_entrega_por_curso()
        self._actualizar_resumen_filtros_entregas()
        self._cargar_entregas()

    #Materias con tareas activas, para el filtro de la pestaña Entregas.
    #Las materias con modelo técnico (RA) se marcan con 🛠 para poder
    #distinguirlas/buscarlas a simple vista entre las materias académicas
    #normales. Si "🛠 Solo módulos técnicos" está marcado, solo se listan
    #esas — así se pueden encontrar rápido sus entregas.
    def _cargar_combo_materia_filtro_entrega(self):

        sel= self.combo_materia_filtro_entrega.currentData()
        self.combo_materia_filtro_entrega.blockSignals(True)
        self.combo_materia_filtro_entrega.clear()
        solo_tecnicos= (hasattr(self, "chk_solo_tecnicos_entrega")
                          and self.chk_solo_tecnicos_entrega.isVisible()
                          and self.chk_solo_tecnicos_entrega.isChecked())
        self.combo_materia_filtro_entrega.addItem(
            "Todos los módulos técnicos" if solo_tecnicos else "Todas las materias", None)
        permitidas= self._materias_permitidas_ids()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT materias.id, materias.codigo, materias.nombre, materias.modelo_evaluacion
                     FROM materias JOIN tareas ON tareas.materia_id = materias.id
                     WHERE tareas.estado='Activa' ORDER BY materias.nombre""")
        for fila in c.fetchall():
            if permitidas is not None and fila["id"] not in permitidas:
                continue
            es_tecnica= fila["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA
            if solo_tecnicos and not es_tecnica:
                continue
            etiqueta= fila["nombre"] + (f" ({fila['codigo']})" if fila["codigo"] else "")
            if es_tecnica:
                etiqueta= f"🛠 {etiqueta}"
            self.combo_materia_filtro_entrega.addItem(etiqueta, fila["id"])
        conn.close()
        idx= self.combo_materia_filtro_entrega.findData(sel)
        self.combo_materia_filtro_entrega.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_materia_filtro_entrega.blockSignals(False)

    def _filtro_tecnico_entrega_cambio(self):

        self._filtrar_secciones_entrega_por_curso()
        self._actualizar_resumen_filtros_entregas()
        self._cargar_entregas()

    def _curso_entrega_cambio(self):

        self._filtrar_secciones_entrega_por_curso()
        self._actualizar_resumen_filtros_entregas()
        self._cargar_entregas()

    def _seccion_entrega_cambio(self):

        self._actualizar_resumen_filtros_entregas()
        self._cargar_entregas()

    def _filtrar_secciones_entrega_por_curso(self):

        permitidas= self._secciones_permitidas_con_nivel_entrega()
        cascada_seccion_por_curso(self.combo_curso_entrega, self.combo_seccion_entrega,
                                   incluir_todas= False, secciones_permitidas=permitidas)
        #Solo se acorta el placeholder "sin curso elegido todavía". Una vez elegido un curso real,
        #combo_seccion_entrega se repuebla con sus secciones reales (y su propio placeholder de
        #cascada_seccion_por_curso), que aquí NO se debe tocar.
        if self.combo_curso_entrega.currentData() is None:
            _acortar_placeholder_combo(self.combo_seccion_entrega, "Selecciona curso")

    #Al marcar/desmarcar '🛠 Solo módulos técnicos', reconstruye tanto el
    #filtro de materia como el de tarea, para que la lista de entregas
    #quede acotada de una sola vez a los módulos técnicos (o vuelva a
    #incluir todas las materias).
    def _alternar_solo_tecnicos_entrega(self):

        self._cargar_combo_materia_filtro_entrega()
        self._cargar_combo_tareas_entrega()

    def _cargar_combo_tareas_entrega(self):

        actual= self.combo_tarea_entrega.currentData()
        self.combo_tarea_entrega.blockSignals(True)
        self.combo_tarea_entrega.clear()
        permitidas= self._materias_permitidas_ids()
        materia_filtro= (self.combo_materia_filtro_entrega.currentData()
                           if hasattr(self, "combo_materia_filtro_entrega") else None)
        solo_tecnicos= (hasattr(self, "chk_solo_tecnicos_entrega")
                          and self.chk_solo_tecnicos_entrega.isVisible()
                          and self.chk_solo_tecnicos_entrega.isChecked())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT tareas.id, tareas.titulo, tareas.materia_id, materias.nombre as materia_nombre,
                     materias.modelo_evaluacion
                     FROM tareas LEFT JOIN materias ON tareas.materia_id = materias.id
                     WHERE tareas.estado='Activa' ORDER BY tareas.fecha_entrega DESC""")
        for fila in c.fetchall():
            if permitidas is not None and fila["materia_id"] not in permitidas:
                continue
            if materia_filtro is not None and fila["materia_id"] != materia_filtro:
                continue
            es_tecnica= fila["modelo_evaluacion"] == MODELO_EVALUACION_TECNICA
            if solo_tecnicos and not es_tecnica:
                continue
            prefijo= "🛠 " if es_tecnica else ""
            self.combo_tarea_entrega.addItem(f"{prefijo}{fila['titulo']} — {fila['materia_nombre'] or ''}", fila["id"])
        conn.close()
        idx= self.combo_tarea_entrega.findData(actual)
        self.combo_tarea_entrega.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_tarea_entrega.blockSignals(False)
        self._actualizar_resumen_filtros_entregas()
        self._cargar_entregas()

    #True si la institución es de tipo Universidad (o Personalizado con el
    #módulo Universidad activo). Mismo criterio usado en estudiantes.py.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    #True si tipo_institucion es exactamente 'Personalizado'. Solo en este
    #modo una misma institución puede tener a la vez estudiantes con área
    #técnica, estudiantes con carrera, y estudiantes sin ninguna de las dos
    #cosas -de ahí que las opciones "No Área Técnica"/"No Carrera" (ver
    #_agregar_opcion_ninguna) solo tengan sentido aquí: en Politécnico o
    #Universidad "puros" todo estudiante activo pertenece siempre a una
    #especialidad/carrera, así que esa opción no aplicaría a nadie.
    def _es_personalizado(self):

        try:

            tipo, _personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado"

    #True solo cuando la institución es "Personalizado" y tiene
    #Politécnico Y Universidad activos a la vez -el único caso en el que
    #Área Técnica y Carrera dejan de ser obligatorias. Si la institución
    #es puramente Politécnico o puramente Universidad, o si "Personalizado"
    #solo tiene UNO de los dos módulos activo, esto es False y el campo
    #correspondiente sigue siendo obligatorio. Mismo criterio que en
    #estudiantes.py.
    def _ambos_modulos_tecnicos_activos(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado" and "Politécnico" in personalizados and "Universidad" in personalizados

    #Añade al final del combo la opción "ninguna" (dato=0, distinto de
    #None= 'Todas/Todos') usada para restringir explícitamente una tarea a
    #estudiantes SIN área técnica o SIN carrera asignada. Solo se llama en
    #modo Personalizado -ver _es_personalizado-, porque es el único caso en
    #que puede haber estudiantes activos sin ese dato.
    def _agregar_opcion_ninguna(self, combo, texto):

        if self._es_personalizado():
            combo.addItem(texto, 0)

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera de
    #'Entregas' solo se muestran/pueblan si la institución tiene ese
    #módulo activo.
    def _cargar_especialidad_carrera_filtro_entrega(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_entrega.setVisible(es_poli)
        self.combo_filtro_especialidad_entrega.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_entrega.currentData()
            self.combo_filtro_especialidad_entrega.blockSignals(True)
            self.combo_filtro_especialidad_entrega.clear()
            self.combo_filtro_especialidad_entrega.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_entrega.addItem(fila["nombre"], fila["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_especialidad_entrega, "No Área Técnica")
            idx= self.combo_filtro_especialidad_entrega.findData(actual)
            self.combo_filtro_especialidad_entrega.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_entrega.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_entrega.setVisible(es_uni)
        self.combo_filtro_carrera_entrega.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_entrega.currentData()
            self.combo_filtro_carrera_entrega.blockSignals(True)
            self.combo_filtro_carrera_entrega.clear()
            self.combo_filtro_carrera_entrega.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_entrega.addItem(fila["nombre"], fila["id"])
            conn.close()
            self._agregar_opcion_ninguna(self.combo_filtro_carrera_entrega, "No Carrera")
            idx= self.combo_filtro_carrera_entrega.findData(actual)
            self.combo_filtro_carrera_entrega.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_entrega.blockSignals(False)

    def _estudiantes_de_la_materia(self, materia_id, seccion_id=None, curso_id=None,
                                    especialidad_id= None, carrera_id=None):

        condiciones= ["horarios.materia_id=?", "estudiantes.estado='Activo'"]
        parametros= [materia_id]
        if seccion_id is not None:
            condiciones.append("estudiantes.seccion_id=?")
            parametros.append(seccion_id)
        elif curso_id is not None:
            condiciones.append("secciones.grado_id=?")
            parametros.append(curso_id)
        #especialidad_id/carrera_id == 0 es la opción explícita "No Área
        #Técnica"/"No Carrera" (ver _agregar_opcion_ninguna, solo existe en modo Personalizado): busca estudiantes que
        #NO tienen ese dato, en vez de comparar por igualdad contra el id 0 (que no existe).
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
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(f"""SELECT DISTINCT estudiantes.id, estudiantes.nombre, estudiantes.apellidos
                     FROM estudiantes
                     JOIN horarios ON horarios.seccion_id = estudiantes.seccion_id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     WHERE {' AND '.join(condiciones)}
                     ORDER BY estudiantes.apellidos, estudiantes.nombre""", parametros)
        filas= c.fetchall()
        conn.close()
        return filas

    def _generar_entregas_faltantes(self):

        tarea_id= self.combo_tarea_entrega.currentData()
        if tarea_id is None:
            mostrar_mensaje("advertencia", "Sin tarea", "Selecciona una tarea primero.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT materia_id, curso_id, seccion_id, especialidad_id, carrera_id FROM tareas WHERE id=?",
                  (tarea_id,))
        fila= c.fetchone()
        conn.close()
        if not fila:
            return
        #Si la tarea ya tiene su propio alcance (curso/sección/área técnica/ carrera), ese manda sobre los filtros de
        #esta pestaña — la tarea ya "sabe" a quién aplica. Si la tarea quedó sin alcance ("Todos"), se usan los filtros
        #manuales de aquí como hasta ahora. Si la tarea ya tiene su propio alcance (curso/sección/área técnica/
        #carrera), ese manda sobre los filtros de esta pestaña — la tarea ya "sabe" a quién aplica. Si la tarea quedó
        #sin alcance ("Todos"), se usan los filtros manuales de aquí como hasta ahora -y, en ese caso, Área
        #Técnica/Carrera son OBLIGATORIOS si la institución es puramente Politécnico/Universidad (mismo criterio que al
        #guardar la tarea; ver _guardar_tarea)-.
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        if fila["especialidad_id"] is None and self._es_politecnico() and not ambos_activos\
                and self.combo_filtro_especialidad_entrega.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica antes de generar "
                           "las entregas.", self)
            return
        if fila["carrera_id"] is None and self._es_universidad() and not ambos_activos\
                and self.combo_filtro_carrera_entrega.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera antes de generar "
                           "las entregas.", self)
            return
        seccion_id= fila["seccion_id"] if fila["seccion_id"] is not None else (
            self.combo_seccion_entrega.currentData() if hasattr(self, "combo_seccion_entrega") else None)
        curso_id= fila["curso_id"] if fila["curso_id"] is not None else (
            self.combo_curso_entrega.currentData() if hasattr(self, "combo_curso_entrega") else None)
        especialidad_id= fila["especialidad_id"] if fila["especialidad_id"] is not None else (
            self.combo_filtro_especialidad_entrega.currentData() if self._es_politecnico() else None)
        carrera_id= fila["carrera_id"] if fila["carrera_id"] is not None else (
            self.combo_filtro_carrera_entrega.currentData() if self._es_universidad() else None)
        estudiantes= self._estudiantes_de_la_materia(fila["materia_id"], seccion_id, curso_id,
                                                        especialidad_id, carrera_id)
        if not estudiantes:
            mostrar_mensaje("advertencia", "Sin estudiantes",
                           "No se encontraron estudiantes activos que cumplan el curso/sección elegidos "
                           "y tengan la materia de la tarea en su horario.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        creados= 0
        for est in estudiantes:
            c.execute("SELECT id FROM tarea_entregas WHERE tarea_id=? AND estudiante_id=?", (tarea_id, est["id"]))
            if c.fetchone() is None:
                c.execute("""INSERT INTO tarea_entregas (tarea_id, estudiante_id, estado_entrega)
                             VALUES (?,?,?)""", (tarea_id, est["id"], "Pendiente"))
                creados += 1
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Lista actualizada",
                       f"Se agregaron {creados} estudiante(s) nuevo(s) a la lista de entregas." if creados
                       else "La lista ya estaba al día.", self)
        if creados:
            self._pulso_exito(self.btn_generar_entregas, "¡Actualizado!")
        self._cargar_entregas()

    def _cargar_entregas(self):

        tarea_id= self.combo_tarea_entrega.currentData()
        if tarea_id is None:
            self.tabla_entregas.setRowCount(0)
            self.paginacion_entregas.establecer_total(0)
            self._actualizar_resumen_entregas([])
            self.estado_vacio_entregas.actualizar(hay_filtro_elegido=False)
            return
        texto= _normalizar_texto(self.in_buscar_entregas.text().strip())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT materia_id FROM tareas WHERE id=?", (tarea_id,))
        f_tarea= c.fetchone()
        materia_id= f_tarea["materia_id"] if f_tarea else None
        if self._materia_es_tecnica(materia_id):
            #Modelo técnico: la nota no vive en `calificaciones` sino en `calificacion_ra` (una fila por RA vinculado a la
            #tarea, ver tarea_ra). Se muestra el promedio de esos RA para el año académico vigente.
            anio= anio_academico_actual()
            c.execute("""SELECT tarea_entregas.*,
                         (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as nombre_est,
                         secciones.id as seccion_id_est, secciones.grado_id as grado_id_est,
                         estudiantes.especialidad_id as especialidad_id_est,
                         estudiantes.carrera_id as carrera_id_est,
                         estudiantes.numero_lista as numero_lista_est,
                         (SELECT AVG(calificacion_ra.nota) FROM calificacion_ra
                          JOIN tarea_ra ON tarea_ra.resultado_aprendizaje_id = calificacion_ra.resultado_aprendizaje_id
                          WHERE tarea_ra.tarea_id = tarea_entregas.tarea_id
                            AND calificacion_ra.estudiante_id = tarea_entregas.estudiante_id
                            AND calificacion_ra.anio_academico = ?) as nota
                         FROM tarea_entregas
                         LEFT JOIN estudiantes ON tarea_entregas.estudiante_id = estudiantes.id
                         LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                         WHERE tarea_entregas.tarea_id=?
                         ORDER BY nombre_est""", (anio, tarea_id))
        else:
            c.execute("""SELECT tarea_entregas.*, (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as nombre_est,
                         secciones.id as seccion_id_est, secciones.grado_id as grado_id_est,
                         estudiantes.especialidad_id as especialidad_id_est,
                         estudiantes.carrera_id as carrera_id_est,
                         estudiantes.numero_lista as numero_lista_est,
                         calificaciones.valor as nota
                         FROM tarea_entregas
                         LEFT JOIN estudiantes ON tarea_entregas.estudiante_id = estudiantes.id
                         LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                         LEFT JOIN calificaciones ON tarea_entregas.calificacion_id = calificaciones.id
                         WHERE tarea_entregas.tarea_id=?
                         ORDER BY nombre_est""", (tarea_id,))
        todas= c.fetchall()
        conn.close()
        self._actualizar_resumen_entregas(todas)

        filas= todas
        if texto:
            filas= [fila for fila in filas if texto in _normalizar_texto(
                    f"{fila['nombre_est'] or ''} {fila['estado_entrega'] or ''}")]
        if self._filtro_entregas == "atrasadas_no_entregadas":
            filas= [fila for fila in filas if fila["estado_entrega"] in ("Atrasada", "No entregada")]
        elif self._filtro_entregas:
            filas= [fila for fila in filas if fila["estado_entrega"] == self._filtro_entregas]

        #Filtros de Curso/Sección/Área Técnica/Carrera (misma fila de combos que se usa para "Generar/Actualizar
        #Lista"): acotan también qué entregas YA GENERADAS se muestran en la tabla, según el curso/ sección/área
        #técnica/carrera real del estudiante.
        curso_id_f= self.combo_curso_entrega.currentData() if hasattr(self, "combo_curso_entrega") else None
        seccion_id_f= self.combo_seccion_entrega.currentData() if hasattr(self, "combo_seccion_entrega") else None
        especialidad_id_f= (self.combo_filtro_especialidad_entrega.currentData()
                              if hasattr(self, "combo_filtro_especialidad_entrega") and self._es_politecnico()
                              else None)
        carrera_id_f= (self.combo_filtro_carrera_entrega.currentData()
                        if hasattr(self, "combo_filtro_carrera_entrega") and self._es_universidad() else None)
        if seccion_id_f is not None:
            filas= [fila for fila in filas if self._valor_columna(fila, "seccion_id_est") == seccion_id_f]
        elif curso_id_f is not None:
            filas= [fila for fila in filas if self._valor_columna(fila, "grado_id_est") == curso_id_f]
        if especialidad_id_f == 0:
            filas= [fila for fila in filas if self._valor_columna(fila, "especialidad_id_est") is None]
        elif especialidad_id_f is not None:
            filas= [fila for fila in filas if self._valor_columna(fila, "especialidad_id_est") == especialidad_id_f]
        if carrera_id_f == 0:
            filas= [fila for fila in filas if self._valor_columna(fila, "carrera_id_est") is None]
        elif carrera_id_f is not None:
            filas= [fila for fila in filas if self._valor_columna(fila, "carrera_id_est") == carrera_id_f]

        #El Número de Lista solo tiene sentido cuando se ve UNA sección concreta a la vez (es un número "1..n dentro de
        #esa sección"): si el filtro está en "Todos los cursos/secciones" o en un curso
        #completo (varias secciones), mostrarlo mezclaría numeraciones de
        #distintas secciones sin ningún orden real, así que se oculta la columna entera en vez de mostrar números
        #confusos. Lo mismo pasa si la institución usa Área Técnica/Carrera y esas quedaron en "Todas": ver
        #bd.mostrar_columna_numero_lista.
        mostrar_columna_numero= mostrar_columna_numero_lista(
            self.main_window, seccion_id_f, especialidad_id_f, carrera_id_f)
        self.tabla_entregas.setColumnHidden(0, not mostrar_columna_numero)
        if mostrar_columna_numero:
            #f: fila de entrega; la lambda devuelve la clave de orden (sin número al final, luego
            #por número de lista).
            filas= sorted(filas, key=lambda f: (
                self._valor_columna(f, "numero_lista_est") is None,
                self._valor_columna(f, "numero_lista_est") or 0))

        self.paginacion_entregas.establecer_total(len(filas))
        inicio, fin= self.paginacion_entregas.rango_actual()
        pagina= filas[inicio:fin]


        self.tabla_entregas.setUpdatesEnabled(False)
        try:

            self.tabla_entregas.setRowCount(len(pagina))
            #i: número de fila de la tabla; f: fila (registro) de la entrega de la página actual que
            #se pinta en ella.
            for i, f in enumerate(pagina):
                if mostrar_columna_numero:
                    numero_lista= self._valor_columna(f, "numero_lista_est")
                    item_numero= QTableWidgetItem()
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                    item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla_entregas.setItem(i, 0, item_numero)
                self.tabla_entregas.setItem(i, 1, QTableWidgetItem(str(f["id"])))
                self.tabla_entregas.setItem(i, 2, QTableWidgetItem(f["nombre_est"] or ""))
                estado_txt= f["estado_entrega"] or ""
                self.tabla_entregas.setItem(i, 3, _item_oculto(estado_txt))
                self.tabla_entregas.setCellWidget(i, 3, _crear_chip(
                    estado_txt, COLORES_ESTADO_ENTREGA.get(estado_txt, COLOR_NEUTRO)))
                self.tabla_entregas.setItem(i, 4, QTableWidgetItem(
                    formatear_fecha(f["fecha_entrega_real"], self.main_window)))
                nota_txt= f"{f['nota']:.2f}" if f["nota"] is not None else "Sin calificar"
                self.tabla_entregas.setItem(i, 5, QTableWidgetItem(nota_txt))
            ajustar_anchos_columnas(self.tabla_entregas)
        finally:
            self.tabla_entregas.setUpdatesEnabled(True)
        self.estado_vacio_entregas.actualizar(hay_filtro_elegido=True)

    def _actualizar_resumen_entregas(self, entregas):

        conteo= {"Entregada": 0, "Pendiente": 0, "Atrasada": 0, "No entregada": 0}
        for entrega in entregas:
            estado= entrega["estado_entrega"] or "Pendiente"
            if estado in conteo:
                conteo[estado] += 1
        self._conteo_entregas_actual= conteo
        total_entregadas= conteo.get("Entregada", 0)
        self.chip_entregas.setText(f"✅ {total_entregadas} entregada{'s' if total_entregadas != 1 else ''}")
        self.barra_entregas.establecer_valores(conteo)
        for clave, lbl in self.etiquetas_leyenda_entregas.items():
            lbl.establecer_valor(conteo.get(clave, 0))
        urgentes= conteo["Atrasada"] + conteo["No entregada"]
        if urgentes > 0:
            self.cinta_alerta_entregas.mostrar_mensaje(
                f"⚠ {urgentes} estudiante(s) atrasados o sin registrar entrega todavía.")
        else:
            self.cinta_alerta_entregas.ocultar()

    def _alternar_filtro_entregas(self, valor):

        self._filtro_entregas= None if self._filtro_entregas == valor else valor
        if self._filtro_entregas == "atrasadas_no_entregadas":
            self.barra_entregas.establecer_filtro_activo({"Atrasada", "No entregada"})
        elif self._filtro_entregas:
            self.barra_entregas.establecer_filtro_activo({self._filtro_entregas})
        else:
            self.barra_entregas.establecer_filtro_activo(None)
        for clave, lbl in self.etiquetas_leyenda_entregas.items():
            activa= (self._filtro_entregas == clave) or (
                self._filtro_entregas == "atrasadas_no_entregadas" and clave in ("Atrasada", "No entregada"))
            lbl.establecer_activa(activa)
        if hasattr(self, "combo_filtro_estado_entrega"):
            idx= self.combo_filtro_estado_entrega.findData(self._filtro_entregas)
            self.combo_filtro_estado_entrega.blockSignals(True)
            self.combo_filtro_estado_entrega.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_estado_entrega.blockSignals(False)
        self.paginacion_entregas.reiniciar()
        self._cargar_entregas()

    def _filtro_entregas_cambio(self, texto=""):

        self.paginacion_entregas.reiniciar()
        self._cargar_entregas()

    def _cambiar_estado_entrega(self):

        fila= self.tabla_entregas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una entrega de la tabla.", self)
            return
        id_entrega= int(self.tabla_entregas.item(fila, 1).text())
        estado_actual= self.tabla_entregas.item(fila, 3).data(Qt.ItemDataRole.UserRole) or ""
        estado, ok= QInputDialog.getItem(self, "Cambiar Estado de Entrega", "Nuevo estado:",
                                          ESTADOS_ENTREGA, ESTADOS_ENTREGA.index(estado_actual)
                                          if estado_actual in ESTADOS_ENTREGA else 0, False)
        if not ok:
            return
        fecha_real= datetime.now().strftime("%Y-%m-%d") if estado == "Entregada" else None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE tarea_entregas SET estado_entrega=?, fecha_entrega_real=? WHERE id=?",
                  (estado, fecha_real, id_entrega))
        conn.commit()
        conn.close()
        registrar_auditoria("Banco de Tareas", "Actualizó estado de entrega", self.main_window.usuario_actual, estado)
        self._pulso_exito(self.btn_cambiar_estado_entrega, "¡Actualizado!")
        self._cargar_entregas()

    def _calificar_entrega(self):

        fila= self.tabla_entregas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una entrega de la tabla.", self)
            return
        id_entrega= int(self.tabla_entregas.item(fila, 1).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT tarea_entregas.*, tareas.materia_id, tareas.periodo_id, tareas.categoria,
                     tareas.titulo, tareas.peso, tareas.valor_maximo
                     FROM tarea_entregas JOIN tareas ON tarea_entregas.tarea_id = tareas.id
                     WHERE tarea_entregas.id=?""", (id_entrega,))
        entrega= c.fetchone()
        if not entrega:
            conn.close()
            return

        #Materias con modelo técnico (Politécnico) no se califican en `calificaciones` sino en `calificacion_ra`, por
        #Resultado de Aprendizaje — ver calificaciones_tecnicas.py. La tarea debe estar vinculada a al menos un RA.
        if self._materia_es_tecnica(entrega["materia_id"]):
            c.execute("SELECT resultado_aprendizaje_id FROM tarea_ra WHERE tarea_id=?", (entrega["tarea_id"],))
            #r: cada fila de tarea_ra; se guarda su resultado_aprendizaje_id (RA vinculados a la
            #tarea).
            ra_ids= [r["resultado_aprendizaje_id"] for r in c.fetchall()]
            if not ra_ids:
                conn.close()
                mostrar_mensaje("advertencia", "Sin RA vinculados",
                               "Esta tarea pertenece a un módulo técnico pero no está vinculada a ningún "
                               "Resultado de Aprendizaje (RA). Edítala y usa \" Vincular a Resultados de "
                               "Aprendizaje\" antes de calificar.", self)
                return
            valor, ok= QInputDialog.getDouble(
                self, "Calificar Entrega (RA)", f"Nota (máx. {entrega['valor_maximo']:.0f}):",
                entrega["valor_maximo"] or 100, 0, entrega["valor_maximo"] or 1000, 2)
            if not ok:
                conn.close()
                return
            anio= anio_academico_actual()
            ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            usuario= self.main_window.usuario_actual
            for ra_id in ra_ids:
                c.execute("""INSERT INTO calificacion_ra (estudiante_id, resultado_aprendizaje_id, anio_academico,
                             nota, usuario, actualizado) VALUES (?,?,?,?,?,?)
                             ON CONFLICT(estudiante_id, resultado_aprendizaje_id, anio_academico) DO UPDATE SET
                                nota= excluded.nota, usuario=excluded.usuario, actualizado=excluded.actualizado""",
                          (entrega["estudiante_id"], ra_id, anio, valor, usuario, ahora))
            c.execute("UPDATE tarea_entregas SET estado_entrega=? WHERE id=?",
                      ("Entregada" if entrega["estado_entrega"] == "Pendiente" else entrega["estado_entrega"],
                       id_entrega))
            conn.commit()
            conn.close()
            registrar_auditoria("Banco de Tareas", "Calificó tarea técnica (RA)",
                                 self.main_window.usuario_actual, entrega["titulo"])
            mostrar_mensaje("exito", "Calificado",
                           "La entrega se calificó y quedó reflejada en Calificaciones Técnicas.", self)
            self._pulso_exito(self.btn_calificar_entrega, "¡Calificado!")
            self._cargar_entregas()
            return

        valor, ok= QInputDialog.getDouble(
            self, "Calificar Entrega", f"Nota (máx. {entrega['valor_maximo']:.0f}):",
            entrega["valor_maximo"] or 100, 0, entrega["valor_maximo"] or 1000, 2)
        if not ok:
            conn.close()
            return
        if entrega["calificacion_id"]:
            c.execute("UPDATE calificaciones SET valor=? WHERE id=?", (valor, entrega["calificacion_id"]))
            calificacion_id= entrega["calificacion_id"]
            accion= "Actualizó calificación de tarea"
        else:
            c.execute("""INSERT INTO calificaciones (estudiante_id, materia_id, periodo_id, categoria,
                         descripcion, valor, peso) VALUES (?,?,?,?,?,?,?)""",
                      (entrega["estudiante_id"], entrega["materia_id"], entrega["periodo_id"],
                       entrega["categoria"], entrega["titulo"], valor, entrega["peso"]))
            calificacion_id= c.lastrowid
            c.execute("UPDATE tarea_entregas SET calificacion_id=?, estado_entrega=? WHERE id=?",
                      (calificacion_id, "Entregada" if entrega["estado_entrega"] == "Pendiente"
                       else entrega["estado_entrega"], id_entrega))
            accion= "Calificó tarea (creó calificación)"
        #Copia el vínculo tarea <-> Competencias Específicas (definido en el formulario
        #de la tarea) hacia la evidencia recién calificada, para que quede reflejada automáticamente en 📐 Notas por
        #Competencia sin que el docente repita el trabajo.
        if es_sistema_dominicano(_sistema_calificacion_actual()):
            c.execute("SELECT competencia_id FROM tarea_competencia WHERE tarea_id=?", (entrega["tarea_id"],))
            #r: cada fila de tarea_competencia; se guarda su competencia_id (competencias vinculadas
            #a la tarea).
            competencia_ids= [r["competencia_id"] for r in c.fetchall()]
            c.execute("DELETE FROM calificacion_competencia WHERE calificacion_id=?", (calificacion_id,))
            for competencia_id in competencia_ids:
                c.execute("""INSERT OR IGNORE INTO calificacion_competencia (calificacion_id, competencia_id)
                             VALUES (?,?)""", (calificacion_id, competencia_id))
        conn.commit()
        conn.close()
        registrar_auditoria("Banco de Tareas", accion, self.main_window.usuario_actual, entrega["titulo"])
        mostrar_mensaje("exito", "Calificado", "La entrega se calificó y quedó reflejada en Calificaciones.", self)
        self._pulso_exito(self.btn_calificar_entrega, "¡Calificado!")
        self._cargar_entregas()

    #Ciclo de vida / tema
    def refrescar(self):

        self._actualizar_textos_politecnico()
        self._cargar_combo_materias()
        self._cargar_combo_periodos()
        self._cargar_combos_alcance_tarea()
        self._cargar_filtros_catalogo()
        self._cargar_tareas()
        self._cargar_combos_curso_seccion_entrega()
        self._cargar_especialidad_carrera_filtro_entrega()
        self._cargar_combo_tareas_entrega()
        dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        es_poli= self._es_politecnico()
        self.lbl_competencias_tarea.setVisible(dominicano)
        self.btn_competencias_tarea.setVisible(dominicano)
        self.tabla_tareas.setColumnHidden(7, not (dominicano or es_poli))
        if not dominicano:
            self._competencias_tarea_seleccionadas= []
            self._ce_tarea_seleccionadas= []
        self._actualizar_visibilidad_ce_ra()

    #Se llama automáticamente (ver main.py ▸ aplicar_tema) cada vez que el
    #usuario cambia el tema/modo oscuro de la aplicación, para que este
    #módulo se mantenga sincronizado con el resto del sistema.
    def actualizar_tema(self):

        self._aplicar_tema_visual()

    def _aplicar_tema_visual(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or next(iter(paletas.values()))
        modo_oscuro= getattr(mw, "modo_oscuro", True)
        idx= 1 if modo_oscuro else 0

        bg_panel= paleta["display_bg"][idx]
        borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        accent= paleta["btn_op_bg"][idx]

        for tarjeta in self.findChildren(TarjetaSeccion):
            tarjeta.aplicar_paleta(bg_panel, borde, txt_prim, txt_sec, accent, modo_oscuro)
        for barra in self.findChildren(BarraSegmentada):
            barra.aplicar_paleta(borde, bg_panel, txt_sec)
        for icono in getattr(self, "_iconos_busqueda", []):
            icono.establecer_color(txt_sec)

        #El selector de pestañas se estiliza aparte (solo self.tabs, no todo el módulo) por la misma razón que en
        #configuracion.py: aplicar un setStyleSheet al contenedor entero repolirira de más. Mismo diseño "píldora" con
        #degradado que en configuracion.py/asistencia.py.
        accent_suave= _rgba(accent, 0.16 if modo_oscuro else 0.10)
        accent_hover= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent

        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {accent_hover});
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
        for chip in (self.chip_contador, self.chip_entregas):
            chip.setStyleSheet("""
                QLabel#ChipContador {
                    background-color: rgba(255, 255, 255, 40);
                    color: white;
                    border-radius: 14px;
                    padding: 7px 16px;
                    font-weight: 700;
                    font-size: 12px;
                }
            """)

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
                background: {borde};
                color: {txt_sec};
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {accent_hover});
                color: white;
            }}
            QTabBar::tab:!selected:hover {{
                background: {accent_suave};
                color: {txt_prim};
            }}
        """)

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QFrame#TarjetaSeccion QLineEdit, QFrame#TarjetaSeccion QComboBox,
            QFrame#TarjetaSeccion QDateEdit, QFrame#TarjetaSeccion QDoubleSpinBox,
            QFrame#TarjetaSeccion QTextEdit {{
                border: 1px solid {borde};
                border-radius: 9px;
                padding: 8px 10px;
                background-color: {bg_panel};
                color: {txt_prim};
                selection-background-color: {accent};
            }}
            QFrame#TarjetaSeccion QLineEdit:focus, QFrame#TarjetaSeccion QComboBox:focus,
            QFrame#TarjetaSeccion QDateEdit:focus, QFrame#TarjetaSeccion QDoubleSpinBox:focus,
            QFrame#TarjetaSeccion QTextEdit:focus {{
                border: 2px solid {accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg_panel};
                color: {txt_prim};
                selection-background-color: {accent};
                selection-color: white;
                outline: none;
            }}
            QTableWidget::item:hover {{
                background-color: {_rgba(txt_sec, 0.12)};
            }}
        """)

        if hasattr(self, "dialogo_filtros_tareas"):
            self.dialogo_filtros_tareas.setStyleSheet(f"""
                QDialog#DialogoFiltros {{
                    background-color: {bg_panel};
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
                    background-color: {bg_panel};
                    color: {txt_prim};
                    border: 1px solid {borde};
                    padding: 6px 10px;
                    border-radius: 6px;
                }}
                QLabel#IconoEncabezadoFiltros {{
                    background-color: {accent};
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
                    color: {txt_prim};
                    background: transparent;
                }}
                QLabel#SubtituloFiltros {{
                    font-size: 11.5px;
                    color: {txt_sec};
                    background: transparent;
                }}
                QFrame#SeparadorFiltros {{
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
        if hasattr(self, "dialogo_filtros_entregas"):
            #Mismo estilo del diálogo de filtros del Catálogo -objectName compartido "DialogoFiltros"-, aplicado también
            #aquí porque cada QDialog tiene su propia hoja de estilos independiente en Qt.
            self.dialogo_filtros_entregas.setStyleSheet(self.dialogo_filtros_tareas.styleSheet())
        if hasattr(self, "lbl_resumen_filtros_entregas"):
            self.lbl_resumen_filtros_entregas.setStyleSheet(
                f"color: {txt_sec}; font-size: 11.5px; background: transparent;")
