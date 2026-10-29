#Politecnico.py - Módulo Técnico (Politécnico) Rediseño visual: tarjetas de cristal, anillo/barras dibujadas
#con QPainter (sin tarjetas KPI), buscador con lupa igual al de configuracion.py, carga diferida por pestaña
#para que abrir el módulo se sienta instantáneo.
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
QGridLayout, QSpinBox, QDoubleSpinBox, QColorDialog, QScrollArea, QFrame,
QSizePolicy, QDialog, QMenu)
from PySide6.QtCore import (Qt, QTimer, QRectF, QSize, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QParallelAnimationGroup, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from src.nucleo.bd import obtener_conexion, registrar_auditoria, mostrar_columna_numero_lista
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso, interseccion_opcional,
                                               poblar_combo_curso_opcional, modulos_tecnicos_por_area_y_curso,
                                               curso_admite_componente_tecnico)
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, agregar_boton_pantalla_completa, mostrar_detalle_fila)
from src.interfaz.configuracion import (IconoLupa, _normalizar, TarjetaSeccion, _hex_a_rgba, _fundido_entrada,
    TabWidgetNavegable, secciones_con_componente_tecnico_valido, conectar_tooltip_seleccion, estilo_flechas_navegacion_tabs)
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from src.modulos.calendario import PanelDesplegable
from src.nucleo.iconos import aplicar_icono_ventana, ICONO_FILTRO, ICONO_COLOR
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, html_icono_emoji, icono_boton_filtro, pixmap_boton_filtro,
                          EMOJI_TALLERES_LABORATORIOS, EMOJI_AREAS_TECNICAS,
                          EMOJI_EMPRESA_PASANTIA, EMOJI_CONTROL_PASANTIAS,
                          EMOJI_PROFESOR)

ESTADOS_PASANTIA= ["En curso", "Finalizada", "Suspendida"]


#Muestra las horas acumuladas de una pasantía como '2 horas' (o
#'1 hora' en singular) en vez del número "pelado" que se guarda en la
#base de datos -mismo criterio que el sufijo " horas" del spinbox del
#formulario, para que lo que se ve al registrar coincida con lo que se
#ve luego en la tabla.
def _formatear_horas(valor):

    n= valor or 0
    n= int(n) if float(n).is_integer() else n
    return f"{n} hora" if n == 1 else f"{n} horas"
RUBROS_SUGERIDOS= ["Tecnología / Software", "Electrónica", "Contabilidad / Finanzas",
 "Manufactura / Industrial", "Salud", "Turismo y Hotelería", "Comercio y Ventas",
 "Construcción", "Logística y Transporte", "Agroindustria", "Educación",
 "Gobierno / Sector Público", "Otro"]

#Paleta de refuerzo para agrupaciones dinámicas (p. ej. empresas por rubro) cuando no hay un color propio
#definido por el usuario (como sí lo tienen las especialidades).
PALETA_SERIES_POLI= ["#6366F1", "#F97316", "#14B8A6", "#EC4899", "#8B5CF6",
                       "#0EA5E9", "#F59E0B", "#22C55E", "#EF4444", "#94A3B8"]

SEGMENTOS_TALLERES= [
    ("vinculado", "Vinculados", "#22C55E"),
    ("sin_vincular", "Sin vincular", "#F59E0B"),
]
SEGMENTOS_PASANTIAS= [
    ("En curso", "En curso", "#0EA5E9"),
    ("Finalizada", "Finalizadas", "#22C55E"),
    ("Suspendida", "Suspendidas", "#EF4444"),
]


#Lee la paleta/tema activo de la ventana principal (mismo criterio que
#universidad.py) para que los elementos visuales de este módulo respeten
#el tema y el modo claro/oscuro elegido, con un respaldo seguro si algo
#no está disponible todavía.
def _colores_tema_politecnico(main_window):

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


#Widgets dibujados a mano (reemplazan a las tarjetas KPI clásicas)
#Círculo que muestra el color elegido para una especialidad, con un
#pequeño 'rebote' animado cada vez que el color cambia — confirmación
#visual inmediata en vez de un simple botón plano.
class MuestraColor(QWidget):

    def __init__(self, color="#6366F1", parent=None):

        super().__init__(parent)
        self.setFixedSize(34, 34)
        self._color= QColor(color)
        self._escala= 1.0
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.setKeyValueAt(0.0, 0.55)
        self._anim.setKeyValueAt(1.0, 1.0)
        self._anim.valueChanged.connect(self._al_animar)

    def _al_animar(self, v):

        self._escala= float(v)
        self.update()

    def establecer_color(self, color_hex):

        self._color= QColor(color_hex)
        self._anim.stop()
        self._anim.start()
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado= min(self.width(), self.height()) * self._escala
        margen= (self.width() - lado) / 2
        rect= QRectF(margen, margen, lado, lado).adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(255, 255, 255, 170), 2))
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(rect)


#Anillo (donut) animado dibujado con QPainter: reparte proporciones de
#un círculo entre categorías con sus propios colores y 'se abre' con una
#animación suave al cargar los datos, en vez de aparecer de golpe.
class AnilloDonut(QWidget):

    def __init__(self, etiqueta_central="", parent=None):

        super().__init__(parent)
        self._etiqueta_central= etiqueta_central
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
        self._anim.valueChanged.connect(self._al_animar)

    def _al_animar(self, v):

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

        return QSize(165, 165)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado= min(self.width(), self.height()) - 16
        if lado <= 0:
            return
        pos_x= (self.width() - lado) / 2
        pos_y= (self.height() - lado) / 2
        grosor= max(11, int(lado * 0.15))
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
        fuente.setPointSize(max(12, int(lado * 0.12)))
        fuente.setBold(True)
        painter.setFont(fuente)
        rect_num= QRectF(pos_x, pos_y + lado * 0.30, lado, lado * 0.32)
        painter.drawText(rect_num, Qt.AlignmentFlag.AlignCenter, str(total_mostrado))

        if self._etiqueta_central:
            painter.setPen(QColor(self._color_sub))
            fuente_sub= QFont()
            fuente_sub.setPointSize(max(8, int(lado * 0.065)))
            painter.setFont(fuente_sub)
            rect_sub= QRectF(pos_x, pos_y + lado * 0.56, lado, lado * 0.18)
            painter.drawText(rect_sub, Qt.AlignmentFlag.AlignCenter, self._etiqueta_central)


#Barra tipo cápsula que reparte su ancho proporcionalmente entre
#categorías, con transición animada al cambiar los datos (sustituye a las
#tarjetas KPI clásicas). Si `interactiva=True`, además se puede hacer clic
#en un tramo para filtrar la tabla, con un tooltip al pasar el mouse.
class BarraSegmentadaPill(QWidget):

    segmento_clicado= Signal(str)
    ALTURA= 26

    def __init__(self, interactiva=False, parent=None):

        super().__init__(parent)
        self._interactiva= interactiva
        self.setFixedHeight(self.ALTURA)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._segmentos= []  #[{"clave","etiqueta","valor","color"}]
        self._fracciones= {}
        self._fracciones_inicio= {}
        self._fracciones_objetivo= {}
        self._color_pista= "#E2E8F0"
        self._color_borde= "#CBD5E1"
        self._claves_activas= None
        self._segmento_hover= None
        if interactiva:
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(500)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._en_paso)

    def poner_colores(self, pista, borde):

        self._color_pista= pista
        self._color_borde= borde
        self.update()

    def establecer_datos(self, segmentos):

        self._segmentos= list(segmentos)
        total= sum(segmento["valor"] for segmento in self._segmentos) or 1
        self._fracciones_inicio= dict(self._fracciones)
        self._fracciones_objetivo= {segmento["clave"]: segmento["valor"] / total for segmento in self._segmentos}
        self._fracciones= {segmento["clave"]: self._fracciones.get(segmento["clave"], 0.0) for segmento in self._segmentos}
        self._anim.stop()
        self._anim.start()

    def _en_paso(self, t):

        for segmento in self._segmentos:
            clave= segmento["clave"]
            ini= self._fracciones_inicio.get(clave, 0.0)
            fin= self._fracciones_objetivo.get(clave, 0.0)
            self._fracciones[clave]= ini + (fin - ini) * float(t)
        self.update()

    def establecer_filtro_activo(self, claves_activas):

        self._claves_activas= set(claves_activas) if claves_activas else None
        self.update()

    def _segmento_en_x(self, pos_x):

        if self.width() <= 0:
            return None
        acumulado= 0.0
        for segmento in self._segmentos:
            frac= self._fracciones.get(segmento["clave"], 0.0)
            inicio_px= acumulado * self.width()
            fin_px= (acumulado + frac) * self.width()
            if inicio_px <= pos_x < fin_px:
                return segmento["clave"]
            acumulado += frac
        return None

    def mouseMoveEvent(self, evento):

        clave= self._segmento_en_x(evento.position().x())
        if clave != self._segmento_hover:
            self._segmento_hover= clave
            seg= next((segmento for segmento in self._segmentos if segmento["clave"] == clave), None)
            if seg:
                sufijo= " — clic para filtrar" if self._interactiva else ""
                self.setToolTip(f"{seg['etiqueta']}: {seg['valor']}{sufijo}")
            else:
                self.setToolTip("")
            self.update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):

        self._segmento_hover= None
        self.update()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento):

        if self._interactiva and evento.button() == Qt.MouseButton.LeftButton:
            clave= self._segmento_en_x(evento.position().x())
            if clave:
                self.segmento_clicado.emit(clave)
        super().mousePressEvent(evento)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radio= self.height() / 2
        ruta= QPainterPath()
        ruta.addRoundedRect(QRectF(0, 0, self.width(), self.height()), radio, radio)
        painter.setClipPath(ruta)
        painter.fillRect(self.rect(), QColor(self._color_pista))
        x= 0.0
        for segmento in self._segmentos:
            frac= self._fracciones.get(segmento["clave"], 0.0)
            if frac <= 0.0008:
                continue
            ancho= frac * self.width()
            color= QColor(segmento["color"])
            if self._claves_activas is not None and segmento["clave"] not in self._claves_activas:
                color.setAlpha(70)
            elif self._segmento_hover == segmento["clave"]:
                color= color.lighter(112)
            painter.fillRect(QRectF(x, 0, ancho + 1, self.height()), color)
            x += ancho
        painter.setClipping(False)
        pen= QPen(QColor(self._color_borde))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(ruta)


#Chip de leyenda con conteo animado; si es interactivo, se puede pulsar
#para filtrar la tabla por esa categoría (mismo gesto que el tramo de la
#barra al que acompaña).
class ContadorClicable(QLabel):

    clicada= Signal()

    def __init__(self, etiqueta_texto, color, interactiva=False, parent=None):

        super().__init__(parent)
        self._etiqueta= etiqueta_texto
        self._color= color
        self._valor_actual= 0
        self._interactiva= interactiva
        if interactiva:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Filtrar por «{etiqueta_texto}» (clic de nuevo para quitar el filtro)")
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(500)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #v: valor animado (decimal) que se redondea a entero para el texto
        self._anim.valueChanged.connect(lambda v: self._refrescar_texto(int(v)))
        self._refrescar_texto(0)
        self.establecer_activa(False)

    def _refrescar_texto(self, valor):

        self.setText(f"●  <b>{valor}</b>  {self._etiqueta}")

    def establecer_valor(self, valor):

        self._anim.stop()
        self._anim.setStartValue(self._valor_actual)
        self._anim.setEndValue(valor)
        self._anim.start()
        self._valor_actual= valor

    def establecer_activa(self, activa):

        fondo= _hex_a_rgba(self._color, 0.16) if activa else "transparent"
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
        """)

    def mousePressEvent(self, evento):

        if self._interactiva and evento.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit()
        super().mousePressEvent(evento)


#MÓDULO
#Módulo condicional activado cuando tipo_institucion = 'Politécnico'.
class ModuloPolitecnico(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion_empresa= None
        self.id_edicion_pasantia= None
        self.id_edicion_especialidad= None
        self.id_edicion_modulo_tecnico= None
        self._pestanas_cargadas= set()
        self._filtro_talleres_vinculo= None
        self._filtro_pasantias_estado= None
        self._valor_chip_especialidades= 0
        self._valor_chip_empresas= 0
        self._valor_chip_pasantias= 0
        self._construir_ui()
        #Cargamos los datos en el siguiente ciclo del bucle de eventos: así la pantalla se pinta de inmediato al
        #presionar el módulo en la barra lateral y los datos aparecen un instante después, sin bloquear el clic (mismo
        #patrón que universidad.py).
        QTimer.singleShot(0, self.refrescar)
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        #Módulo institucional del Politécnico (Áreas Técnicas, Empresas, Pasantías): exclusivo de roles gerenciales.
        self._titulo_modulo_atajos= "Politécnico"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar área técnica",
                         self._guardar_especialidad)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar_especialidad)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar área técnica seleccionada",
                         self._cargar_especialidad_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar área técnica",
                         self._eliminar_especialidad)
        registrar_atajo(self, self.main_window, "F5", "Actualizar", self._cargar_especialidades)

    #True si ya existe otra fila de `tabla` con el mismo `nombre`
    #(comparado sin distinguir mayúsculas/acentos vía _normalizar).
    #`filtro_extra`, si se pasa, es (condicion_sql, parametros) para acotar
    #la comparación en vez de compararlo contra toda la tabla — por
    #ejemplo, solo los módulos técnicos dentro de `materias`.
    def _nombre_duplicado(self, tabla, nombre, id_excluir=None, filtro_extra=None):

        conn= obtener_conexion()
        c= conn.cursor()
        query= f"SELECT id, nombre FROM {tabla}"
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
            if _normalizar(fila["nombre"] or "") == objetivo:
                return True
        return False

    #---------------- ESTRUCTURA GENERAL ----------------
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

        disposicion.addWidget(self._construir_cabecera())

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        disposicion.addWidget(self.tabs)
        self.tabs.addTab(self._tab_especialidades(), "Áreas Técnicas")
        self.tabs.addTab(self._tab_modulos_tecnicos(), "Módulos Técnicos")
        self.tabs.addTab(self._tab_asignaciones_tecnicas(), "Profesores por Módulo")
        self.tabs.addTab(self._tab_talleres(), "Talleres y Laboratorios")
        self.tabs.addTab(self._tab_empresas(), "Empresas de Pasantía")
        self.tabs.addTab(self._tab_pasantias(), "Control de Pasantías")
        self.tabs.setTabIcon(0, icono_emoji(EMOJI_AREAS_TECNICAS))
        self.tabs.setTabIcon(1, icono_emoji("🧰"))
        self.tabs.setTabIcon(2, icono_emoji(EMOJI_PROFESOR))
        self.tabs.setTabIcon(3, icono_emoji(EMOJI_TALLERES_LABORATORIOS))
        self.tabs.setTabIcon(4, icono_emoji(EMOJI_EMPRESA_PASANTIA))
        self.tabs.setTabIcon(5, icono_emoji(EMOJI_CONTROL_PASANTIAS))
        self.tabs.currentChanged.connect(self._cambio_pestana)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)
        self.actualizar_tema()

    def _construir_cabecera(self):

        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("CabeceraPolitecnico")
        cab= QHBoxLayout(self.frame_cabecera)
        cab.setContentsMargins(22, 18, 22, 18)
        cab.setSpacing(14)

        lbl_icono= QLabel("")
        lbl_icono.setObjectName("IconoCabeceraPolitecnico")
        lbl_icono.setFixedSize(46, 46)
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(lbl_icono, "Politécnico")
        cab.addWidget(lbl_icono)

        bloque= QVBoxLayout()
        bloque.setSpacing(2)
        lbl_titulo= QLabel("Módulo Técnico · Politécnico")
        lbl_titulo.setObjectName("TituloCabeceraPolitecnico")
        lbl_subtitulo= QLabel("Áreas técnicas, talleres, empresas aliadas y pasantías en un solo lugar")
        lbl_subtitulo.setObjectName("SubtituloCabeceraPolitecnico")
        lbl_subtitulo.setWordWrap(True)
        bloque.addWidget(lbl_titulo)
        bloque.addWidget(lbl_subtitulo)
        cab.addLayout(bloque, 1)

        self.chip_especialidades= QLabel("0 áreas técnicas")
        self.chip_especialidades.setObjectName("ChipResumenPolitecnico")
        cab.addWidget(self.chip_especialidades, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_empresas= QLabel("0 empresas aliadas")
        self.chip_empresas.setObjectName("ChipResumenPolitecnico")
        cab.addWidget(self.chip_empresas, 0, Qt.AlignmentFlag.AlignVCenter)

        self.chip_pasantias= QLabel("0 pasantías en curso")
        self.chip_pasantias.setObjectName("ChipResumenPolitecnico")
        cab.addWidget(self.chip_pasantias, 0, Qt.AlignmentFlag.AlignVCenter)

        return self.frame_cabecera

    #Barra de búsqueda con lupa dibujada a mano e insensible a mayúsculas/
    #acentos — mismo diseño y comportamiento que en Configuración, para que
    #todos los módulos del sistema busquen exactamente igual.
    def _crear_barra_busqueda(self, placeholder, callback_filtro):

        marco= QFrame()
        marco.setObjectName("MarcoBusquedaPolitecnico")
        lay= QHBoxLayout(marco)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(6)
        icono= IconoLupa()
        lay.addWidget(icono)
        in_campo= QLineEdit()
        limitar_campo_texto(in_campo, 300)
        in_campo.setPlaceholderText(placeholder)
        in_campo.setObjectName("CampoBusquedaPolitecnico")
        lay.addWidget(in_campo, 1)

        temporizador= QTimer(self)
        temporizador.setSingleShot(True)
        temporizador.setInterval(150)
        temporizador.timeout.connect(callback_filtro)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador
        in_campo.textChanged.connect(lambda _t: temporizador.start())

        self._iconos_busqueda= getattr(self, "_iconos_busqueda", [])
        self._iconos_busqueda.append(icono)
        return marco, in_campo

    #Ventanita (no modal) de "☰ Filtros", mismo patrón que usan
    #calendario.py/banco_tareas.py/calificaciones_tecnicas.py: devuelve
    #(dialogo, grid) para que cada pestaña agregue sus propios combos.
    #Todas comparten el objectName "DialogoFiltrosPoli" para heredar el
    #mismo estilo del tema activo desde un solo lugar.
    def _crear_ventana_filtros(self, titulo_ventana, subtitulo):

        dialogo= QDialog(self)
        dialogo.setObjectName("DialogoFiltrosPoli")
        dialogo.setWindowTitle(titulo_ventana)
        aplicar_icono_ventana(dialogo, ICONO_FILTRO)
        dialogo.setModal(False)
        dialogo.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(dialogo)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        lbl_icono_encabezado= QLabel()
        pixmap_boton_filtro(lbl_icono_encabezado, 20)
        lbl_icono_encabezado.setObjectName("IconoEncabezadoFiltrosPoli")
        fila_encabezado.addWidget(lbl_icono_encabezado)
        lbl_titulo_encabezado= QLabel("Filtros")
        lbl_titulo_encabezado.setObjectName("TituloEncabezadoFiltrosPoli")
        fila_encabezado.addWidget(lbl_titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        lbl_subtitulo= QLabel(subtitulo)
        lbl_subtitulo.setObjectName("SubtituloFiltrosPoli")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltrosPoli")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        lay_dialogo.addLayout(grid)

        self._filas_botones_dialogo_filtros= getattr(self, "_filas_botones_dialogo_filtros", [])
        return dialogo, grid, lay_dialogo

    #Agrega la fila de botones "✖ Limpiar filtros" / "Cerrar" al final
    #de una ventana de filtros creada con `_crear_ventana_filtros`.
    def _cerrar_ventana_filtros(self, dialogo, lay_dialogo, callback_limpiar=None):

        fila_botones= QHBoxLayout()
        if callback_limpiar is not None:
            btn_limpiar= QPushButton("Limpiar filtros")
            btn_limpiar.setIcon(icono_emoji("🧹"))
            btn_limpiar.setIconSize(_QSize_emoji(16, 16))
            btn_limpiar.setObjectName("BtnAccionNeutro")
            btn_limpiar.clicked.connect(callback_limpiar)
            fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(dialogo.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_ventana(self, dialogo):

        dialogo.show()
        dialogo.raise_()
        dialogo.activateWindow()

    #Resplandor breve en la sombra de una tarjeta como confirmación
    #visual tras guardar/eliminar (verde=éxito, rojo=aviso).
    def _destello(self, tarjeta, color_hex="#22C55E"):

        if tarjeta is None or not hasattr(tarjeta, "_sombra"):
            return
        sombra= tarjeta._sombra
        color_normal= QColor(0, 0, 0, 50)
        grupo= QParallelAnimationGroup(self)
        anim_color= QPropertyAnimation(sombra, b"color", self)
        anim_color.setKeyValueAt(0.0, color_normal)
        anim_color.setKeyValueAt(0.5, QColor(color_hex))
        anim_color.setKeyValueAt(1.0, color_normal)
        anim_color.setDuration(650)
        anim_blur= QPropertyAnimation(sombra, b"blurRadius", self)
        anim_blur.setKeyValueAt(0.0, 14)
        anim_blur.setKeyValueAt(0.5, 32)
        anim_blur.setKeyValueAt(1.0, 14)
        anim_blur.setDuration(650)
        grupo.addAnimation(anim_color)
        grupo.addAnimation(anim_blur)
        grupo.start()
        self._anim_destello= grupo

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
        #v: valor animado (decimal) que se redondea a entero para el chip
        anim.valueChanged.connect(lambda v: chip.setText(formato(int(v))))
        anim.start()
        setattr(self, f"_anim_{atributo}", anim)

    def showEvent(self, evento):

        super().showEvent(evento)
        #Si el Dashboard pidió saltar directo a una pestaña (el selector
        #"Materias / Módulos" pone _pestana_pendiente_politecnico = 1 para
        #caer en "Módulos Técnicos" en vez de "Áreas Técnicas"), se consume aquí al mostrarse el módulo. Mismo patrón
        #que reportes.py con _pestana_pendiente_dashboard.
        pendiente= getattr(self.main_window, "_pestana_pendiente_politecnico", None)
        if pendiente is not None:
            self.main_window._pestana_pendiente_politecnico= None
            if isinstance(pendiente, int) and 0 <= pendiente < self.tabs.count() \
                    and self.tabs.isTabVisible(pendiente):
                self.tabs.setCurrentIndex(pendiente)

    def _cambio_pestana(self, indice):

        widget_actual= self.tabs.widget(indice)
        if widget_actual is not None:
            _fundido_entrada(widget_actual, 240)
        if indice in self._pestanas_cargadas:
            return
        self._pestanas_cargadas.add(indice)
        if indice == 0:
            self._cargar_especialidades()
            self._cargar_donut_especialidades()
        elif indice == 1:
            self._cargar_modulos_tecnicos()
        elif indice == 2:
            self._cargar_asignaciones_tecnicas()
        elif indice == 3:
            self._cargar_talleres()
            self._cargar_barra_talleres()
        elif indice == 4:
            self._cargar_empresas()
            self._cargar_barra_empresas()
        elif indice == 5:
            self._cargar_pasantias()
            self._cargar_barra_pasantias()

    #---------------- ESPECIALIDADES ----------------
    def _tab_especialidades(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        t_donut= TarjetaSeccion(EMOJI_TALLERES_LABORATORIOS, "Talleres y laboratorios por área técnica",
            "Cada arco representa cuántos talleres/laboratorios están vinculados a cada "
            "área técnica, con el color que tú elegiste para ella.")
        fila_donut= QHBoxLayout()
        fila_donut.setSpacing(22)
        self.anillo_especialidades= AnilloDonut("talleres")
        fila_donut.addWidget(self.anillo_especialidades, 0, Qt.AlignmentFlag.AlignTop)
        self.contenedor_leyenda_esp= QWidget()
        self.layout_leyenda_esp= QVBoxLayout(self.contenedor_leyenda_esp)
        self.layout_leyenda_esp.setContentsMargins(0, 6, 0, 0)
        self.layout_leyenda_esp.setSpacing(6)
        fila_donut.addWidget(self.contenedor_leyenda_esp, 1, Qt.AlignmentFlag.AlignTop)
        t_donut.contenido.addLayout(fila_donut)
        disposicion.addWidget(t_donut)

        self.tarjeta_form_especialidad= TarjetaSeccion("✏", "Nueva Área Técnica")
        form= QGridLayout()
        form.setSpacing(10)
        self.e_nombre= QLineEdit()
        self.e_nombre.setPlaceholderText("Nombre (ej. Informática)")
        limitar_campo_texto(self.e_nombre, 300)
        self.e_nombre.setToolTip("Nombre del área técnica")
        self.e_nombre.textChanged.connect(self._actualizar_codigo_especialidad)
        self.e_codigo= QLineEdit()
        self.e_codigo.setPlaceholderText("Código (autogenerado)")
        limitar_campo_texto(self.e_codigo, 300)
        self.e_codigo.setReadOnly(True)
        self.e_codigo.setToolTip(
            "Autogenerado. Clic derecho para escribirlo manualmente o para "
            "volver a autogenerado.")
        self.e_codigo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.e_codigo.customContextMenuRequested.connect(self._menu_contextual_codigo_especialidad)
        self._codigo_especialidad_manual= False
        self.color_seleccionado= "#6366F1"
        self.muestra_color= MuestraColor(self.color_seleccionado)
        btn_color= QPushButton("Elegir Color")
        btn_color.setIcon(icono_emoji("🎨"))
        btn_color.setIconSize(_QSize_emoji(16, 16))
        btn_color.setObjectName("BtnAccionNeutro")
        btn_color.setToolTip("Color con el que se identificará esta área técnica en el sistema")
        btn_color.clicked.connect(self._elegir_color)
        fila_color= QHBoxLayout()
        fila_color.setSpacing(8)
        fila_color.addWidget(self.muestra_color)
        fila_color.addWidget(btn_color, 1)
        form.addWidget(self.e_nombre, 0, 0)
        form.addWidget(self.e_codigo, 0, 1)
        form.addLayout(fila_color, 0, 2)
        btn_guardar= QPushButton("Guardar Área Técnica")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_especialidad)
        form.addWidget(btn_guardar, 1, 0)
        self.tarjeta_form_especialidad.contenido.addLayout(form)
        self.panel_form_especialidad= PanelDesplegable("Nueva Área Técnica")
        self.panel_form_especialidad.cuerpo_layout().addWidget(self.tarjeta_form_especialidad)
        disposicion.addWidget(self.panel_form_especialidad)

        self.tarjeta_tabla_especialidades= TarjetaSeccion(EMOJI_AREAS_TECNICAS, "Áreas Técnicas registradas")
        fila_cabecera_tabla_especialidades= QHBoxLayout()
        fila_cabecera_tabla_especialidades.addStretch()
        self.tarjeta_tabla_especialidades.contenido.addLayout(fila_cabecera_tabla_especialidades)
        marco_busqueda, self.in_buscar_especialidades= self._crear_barra_busqueda(
            "Buscar por nombre o código…", self._filtro_especialidades_cambio)
        self.tarjeta_tabla_especialidades.contenido.addWidget(marco_busqueda)

        self.tabla_especialidades= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_especialidades)

        self.tabla_especialidades.setHorizontalHeaderLabels(["ID", "Nombre", "Código", "Color"])
        header= self.tabla_especialidades.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  #"Nombre"
        self.tabla_especialidades.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_especialidades.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_especialidades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_especialidades.setAlternatingRowColors(True)
        self.tabla_especialidades.setWordWrap(True)
        self.tabla_especialidades.setMinimumHeight(340)
        self.tabla_especialidades.verticalHeader().setVisible(False)
        #El ID interno no se muestra (solo se usa internamente para editar/ eliminar); lo que identifica a la
        #especialidad de cara al usuario es su Código, igual que en Materias.
        self.tabla_especialidades.setColumnHidden(0, True)
        self.tarjeta_tabla_especialidades.contenido.addWidget(self.tabla_especialidades, 1)

        self.paginacion_especialidades= ControlPaginacion()
        self.paginacion_especialidades.cambio.connect(self._cargar_especialidades)
        self.tarjeta_tabla_especialidades.contenido.addWidget(self.paginacion_especialidades)

        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_especialidades, [self.tabla_especialidades, self.paginacion_especialidades],
            titulo= "Áreas Técnicas", parent=self)

        fila_acciones_esp= QHBoxLayout()
        btn_actualizar_esp= QPushButton("Actualizar")
        btn_actualizar_esp.setIcon(icono_emoji("🔄"))
        btn_actualizar_esp.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_esp.setObjectName("BtnAccionNeutro")
        btn_actualizar_esp.clicked.connect(self._cargar_especialidades)
        fila_acciones_esp.addWidget(btn_actualizar_esp)
        btn_limpiar_esp= QPushButton("Limpiar")
        btn_limpiar_esp.setIcon(icono_emoji("🧹"))
        btn_limpiar_esp.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_esp.setObjectName("BtnAccionNeutro")
        btn_limpiar_esp.clicked.connect(self._limpiar_especialidad)
        fila_acciones_esp.addWidget(btn_limpiar_esp)
        btn_cargar_esp= QPushButton("Cargar Seleccionada")
        btn_cargar_esp.setIcon(icono_emoji("✏"))
        btn_cargar_esp.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_esp.setObjectName("BtnAccionEditar")
        btn_cargar_esp.clicked.connect(self._cargar_especialidad_seleccionada)
        fila_acciones_esp.addWidget(btn_cargar_esp)
        btn_eliminar= QPushButton("Eliminar Área Técnica Seleccionada")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_especialidad)
        fila_acciones_esp.addWidget(btn_eliminar)
        btn_detalle_esp= agregar_boton_detalle(fila_acciones_esp, self.tabla_especialidades, self, titulo="Detalle del Área Técnica")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_especialidades.doubleClicked.connect(lambda *_: btn_detalle_esp.click())
        fila_acciones_esp.addStretch()
        self.tarjeta_tabla_especialidades.contenido.addLayout(fila_acciones_esp)
        disposicion.addWidget(self.tarjeta_tabla_especialidades)
        disposicion.addStretch()
        return contenedor

    def _limpiar_especialidad(self):

        self.id_edicion_especialidad= None
        self.e_nombre.clear()
        self.e_codigo.clear()
        self._codigo_especialidad_manual= False
        self.e_codigo.setReadOnly(True)
        self.color_seleccionado= "#6366F1"
        self.muestra_color.establecer_color(self.color_seleccionado)
        self.tabla_especialidades.clearSelection()
        desactivar_modo_edicion(self.e_nombre)

    #Autocódigo con el mismo criterio que `_generar_codigo_materia` en
    #materias.py: iniciales de hasta 3 palabras del nombre + sufijo
    #numérico de 3 dígitos (p. ej. 'Informática' -> 'I-001').
    def _generar_codigo_especialidad(self, excluir_id=None):

        nombre= self.e_nombre.text().strip()
        base= "".join(w[0] for w in nombre.upper().split()[:3]) or "ESP"
        conn= obtener_conexion()
        c= conn.cursor()
        if excluir_id is not None:
            c.execute("SELECT codigo FROM especialidades WHERE codigo LIKE ? AND id != ?",
                      (f"{base}-%", excluir_id))
        else:
            c.execute("SELECT codigo FROM especialidades WHERE codigo LIKE ?", (f"{base}-%",))
        existentes= {fila["codigo"] for fila in c.fetchall()}
        conn.close()
        n= 1
        while f"{base}-{n:03d}" in existentes:
            n += 1
        return f"{base}-{n:03d}"

    def _actualizar_codigo_especialidad(self, texto=None):

        if self._codigo_especialidad_manual:
            return
        if not self.e_nombre.text().strip():
            self.e_codigo.clear()
            return
        self.e_codigo.setText(self._generar_codigo_especialidad(excluir_id=self.id_edicion_especialidad))

    #Clic derecho sobre el campo "Código" del área técnica: alterna
    #entre escribirlo a mano y dejarlo autogenerado de nuevo -mismo
    #patrón que `_menu_contextual_codigo_materia` en materias.py.
    def _menu_contextual_codigo_especialidad(self, pos):

        menu= QMenu(self)
        if self._codigo_especialidad_manual:
            accion= menu.addAction(icono_emoji("🔄"), "Volver a autogenerado")
        else:
            accion= menu.addAction(icono_emoji("✏"), "Escribir código manualmente")
        if menu.exec(self.e_codigo.mapToGlobal(pos)) == accion:
            if self._codigo_especialidad_manual:
                self._codigo_especialidad_manual= False
                self.e_codigo.setReadOnly(True)
                self._actualizar_codigo_especialidad()
            else:
                self._codigo_especialidad_manual= True
                self.e_codigo.setReadOnly(False)
                self.e_codigo.setFocus()
                self.e_codigo.selectAll()

    def _elegir_color(self):

        dialogo_color= QColorDialog(QColor(self.color_seleccionado), self)
        aplicar_icono_ventana(dialogo_color, ICONO_COLOR)
        if dialogo_color.exec() != QDialog.DialogCode.Accepted:
            return
        color= dialogo_color.selectedColor()
        if color.isValid():
            self.color_seleccionado= color.name()
            self.muestra_color.establecer_color(self.color_seleccionado)

    def _guardar_especialidad(self):

        nombre= self.e_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        if self._nombre_duplicado("especialidades", nombre, self.id_edicion_especialidad):
            mostrar_mensaje("advertencia", "Área técnica duplicada",
                             f"Ya existe un área técnica llamada «{nombre}».", self)
            self._destello(self.tarjeta_form_especialidad, "#EF4444")
            return
        if not self.e_codigo.text().strip():
            self.e_codigo.setText(self._generar_codigo_especialidad(excluir_id=self.id_edicion_especialidad))
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            if self.id_edicion_especialidad is None:
                c.execute("INSERT INTO especialidades (nombre, codigo, color) VALUES (?,?,?)",
                          (nombre, self.e_codigo.text().strip(), self.color_seleccionado))
                accion= "Agregó área técnica"
            else:
                c.execute("UPDATE especialidades SET nombre=?, codigo=?, color=? WHERE id=?",
                          (nombre, self.e_codigo.text().strip(), self.color_seleccionado,
                           self.id_edicion_especialidad))
                accion= "Editó área técnica"
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo guardar el área técnica:\n{error}", self)
            return
        finally:
            conn.close()
        registrar_auditoria("Politécnico", accion, self.main_window.usuario_actual, nombre)
        self._destello(self.tarjeta_form_especialidad, "#22C55E")
        self._limpiar_especialidad()
        self._cargar_especialidades()
        self._cargar_donut_especialidades()
        self._cargar_combos_talleres()
        self._cargar_combos_modulos_tecnicos()
        self._cargar_resumen_cabecera()

    def _cargar_especialidad_seleccionada(self):

        fila= self.tabla_especialidades.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un área técnica de la tabla.", self)
            return
        id_esp= int(self.tabla_especialidades.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM especialidades WHERE id=?", (id_esp,))
        #f: fila de la especialidad; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_especialidad= f["id"]
        self.e_nombre.blockSignals(True)
        self.e_nombre.setText(f["nombre"] or "")
        self.e_nombre.blockSignals(False)
        self.e_codigo.setText(f["codigo"] or "")
        #Al cargar un área técnica ya existente para editarla, el código deja de ser de solo lectura: es la otra puerta
        #de entrada (junto con el clic derecho) para poder escribirlo a mano.
        self._codigo_especialidad_manual= True
        self.e_codigo.setReadOnly(False)
        self.color_seleccionado= f["color"] or "#6366F1"
        self.muestra_color.establecer_color(self.color_seleccionado)
        if hasattr(self, "panel_form_especialidad"):
            self.panel_form_especialidad.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.e_nombre, f"Editando área técnica: {f['nombre'] or ''}")

    def _eliminar_especialidad(self):

        fila= self.tabla_especialidades.currentRow()
        if fila < 0:
            return
        id_esp= int(self.tabla_especialidades.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta área técnica?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM especialidades WHERE id=?", (id_esp,))
        conn.commit()
        conn.close()
        if self.id_edicion_especialidad == id_esp:
            self._limpiar_especialidad()
        registrar_auditoria("Politécnico", "Eliminó área técnica", self.main_window.usuario_actual, str(id_esp))
        self._destello(self.tarjeta_tabla_especialidades, "#EF4444")
        self._cargar_especialidades()
        self._cargar_donut_especialidades()
        self._cargar_combos_talleres()
        self._cargar_talleres()
        self._cargar_barra_talleres()
        self._cargar_combos_modulos_tecnicos()
        self._cargar_resumen_cabecera()

    def _filtro_especialidades_cambio(self):

        self.paginacion_especialidades.reiniciar()
        self._cargar_especialidades()

    def _cargar_especialidades(self):

        texto= _normalizar(self.in_buscar_especialidades.text().strip()) if hasattr(
            self, "in_buscar_especialidades") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM especialidades ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(f"{fila['nombre'] or ''} {fila['codigo'] or ''}")]
        self.paginacion_especialidades.establecer_total(len(filas))
        inicio, fin= self.paginacion_especialidades.rango_actual()
        filas= filas[inicio:fin]
        with tabla_pausada(self.tabla_especialidades):
            self.tabla_especialidades.setRowCount(len(filas))
            for i, f in enumerate(filas):
                self.tabla_especialidades.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_especialidades.setItem(i, 1, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_especialidades.setItem(i, 2, QTableWidgetItem(f["codigo"] or ""))
                item_color= QTableWidgetItem(f["color"] or "")
                item_color.setBackground(QColor(f["color"] or "#6366F1"))
                self.tabla_especialidades.setItem(i, 3, item_color)
            ajustar_anchos_columnas(self.tabla_especialidades)

    def _cargar_donut_especialidades(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT especialidades.id, especialidades.nombre, especialidades.color,
                     COUNT(aulas.id) as total FROM especialidades
                     LEFT JOIN aulas ON aulas.especialidad_id = especialidades.id
                     AND aulas.tipo IN ('Taller', 'Laboratorio')
                     GROUP BY especialidades.id ORDER BY especialidades.nombre""")
        filas= c.fetchall()
        conn.close()
        segmentos= [{"etiqueta": fila["nombre"], "valor": fila["total"], "color": fila["color"] or "#6366F1"}
                     for fila in filas]
        if hasattr(self, "anillo_especialidades"):
            self.anillo_especialidades.establecer_datos(segmentos)
            self._actualizar_leyenda_esp(segmentos)

    def _actualizar_leyenda_esp(self, segmentos):

        while self.layout_leyenda_esp.count():
            item= self.layout_leyenda_esp.takeAt(0)
            wdg= item.widget()
            if wdg is not None:
                wdg.deleteLater()
        visibles= [segmento for segmento in segmentos if segmento["valor"] > 0]
        if not visibles:
            lbl= QLabel("Aún no hay talleres/laboratorios vinculados a ninguna área técnica.")
            lbl.setObjectName("DescModulo")
            lbl.setWordWrap(True)
            self.layout_leyenda_esp.addWidget(lbl)
            return
        for seg in visibles:
            contenedor= QWidget()
            fila= QHBoxLayout(contenedor)
            fila.setContentsMargins(0, 0, 0, 0)
            fila.setSpacing(8)
            lbl_punto= QLabel()
            lbl_punto.setFixedSize(10, 10)
            lbl_punto.setStyleSheet(f"background-color:{seg['color']}; border-radius:5px;")
            fila.addWidget(lbl_punto)
            lbl_texto= QLabel(f"{seg['etiqueta']}  ·  {seg['valor']}")
            lbl_texto.setObjectName("DescModulo")
            fila.addWidget(lbl_texto, 1)
            self.layout_leyenda_esp.addWidget(contenedor)
        self.layout_leyenda_esp.addStretch()

    #---------------- MÓDULOS TÉCNICOS (materias RA por área técnica) ----------------
    def _tab_modulos_tecnicos(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        desc= TarjetaSeccion("🧰", "Módulos Técnicos",
            "Los módulos técnicos son las 'materias' propias del Politécnico: siempre "
            "pertenecen a un Área Técnica y se evalúan por Resultados de Aprendizaje (RA) "
            "ponderados en vez del currículo académico por competencias (eso se ve en "
            "Calificaciones Técnicas). Las materias académicas normales se administran en el "
            "módulo Materias, Cursos y Horarios.")
        disposicion.addWidget(desc)

        self.tarjeta_form_modulo= TarjetaSeccion("✏", "Nuevo Módulo Técnico")
        form= QGridLayout()
        form.setSpacing(10)
        self.mt_codigo= QLineEdit()
        self.mt_codigo.setPlaceholderText("Código (autogenerado)")
        limitar_campo_texto(self.mt_codigo, 300)
        self.mt_codigo.setReadOnly(True)
        self.mt_codigo.setToolTip(
            "Autogenerado. Clic derecho para escribirlo manualmente o para "
            "volver a autogenerado.")
        self.mt_codigo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mt_codigo.customContextMenuRequested.connect(self._menu_contextual_codigo_modulo)
        self._codigo_modulo_manual= False
        self.mt_nombre= QLineEdit()
        self.mt_nombre.setPlaceholderText("Nombre del Módulo Técnico")
        limitar_campo_texto(self.mt_nombre, 300)
        self.mt_nombre.textChanged.connect(self._previsualizar_codigo_modulo)
        self.mt_creditos= QSpinBox()
        self.mt_creditos.setRange(0, 20)
        self.mt_creditos.setToolTip("Créditos académicos del módulo técnico dentro del plan de estudios.")
        self.mt_especialidad= QComboBox()
        conectar_tooltip_seleccion(self.mt_especialidad, "Área técnica a la que pertenece este módulo (obligatorio).")
        self.mt_profesor= QComboBox()
        conectar_tooltip_seleccion(self.mt_profesor,
            "Profesor titular del módulo técnico. 'Sin asignar' = aún no tiene profesor titular")
        self.mt_estado= QComboBox()
        self.mt_estado.addItems(["Activa", "Inactiva"])
        conectar_tooltip_seleccion(self.mt_estado, "Estado del módulo: Activa = disponible para horarios y matrícula")
        self.mt_curso= QComboBox()
        conectar_tooltip_seleccion(self.mt_curso,
            "Curso/Grado al que se vincula este módulo (OPCIONAL). Si lo dejas en 'Sin curso específico', "
            "el módulo puede asignarse a cualquier curso de su área. Solo cursos de Secundaria - Segundo Ciclo.")
        form.addWidget(self.mt_codigo, 0, 0)
        form.addWidget(self.mt_nombre, 0, 1)
        form.addWidget(self.mt_creditos, 0, 2)
        form.addWidget(self.mt_especialidad, 1, 0)
        form.addWidget(self.mt_profesor, 1, 1)
        form.addWidget(self.mt_estado, 1, 2)
        form.addWidget(self.mt_curso, 2, 0)
        btn_guardar= QPushButton("Guardar Módulo Técnico")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_modulo_tecnico)
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_modulo_tecnico)
        form.addWidget(btn_limpiar, 3, 1)
        self.tarjeta_form_modulo.contenido.addLayout(form)
        self.panel_form_modulo= PanelDesplegable("Nuevo Módulo Técnico")
        self.panel_form_modulo.cuerpo_layout().addWidget(self.tarjeta_form_modulo)
        disposicion.addWidget(self.panel_form_modulo)

        self.tarjeta_tabla_modulos= TarjetaSeccion("🧰", "Módulos Técnicos registrados")
        marco_busqueda, self.in_buscar_modulos= self._crear_barra_busqueda(
            "Buscar por código, nombre, área técnica o profesor…", self._filtro_modulos_cambio)
        fila_busqueda_modulos= QHBoxLayout()
        fila_busqueda_modulos.addWidget(marco_busqueda, 1)
        self.mt_filtro_especialidad= QComboBox()
        conectar_tooltip_seleccion(self.mt_filtro_especialidad, "Filtrar por área técnica")
        self.mt_filtro_estado= QComboBox()
        self.mt_filtro_estado.addItem("Todos los estados", None)
        self.mt_filtro_estado.addItems(["Activa", "Inactiva"])
        conectar_tooltip_seleccion(self.mt_filtro_estado, "Filtrar por estado del módulo")
        self.mt_filtro_especialidad.currentIndexChanged.connect(self._filtro_modulos_cambio)
        self.mt_filtro_estado.currentIndexChanged.connect(self._filtro_modulos_cambio)
        btn_filtros_modulos= QPushButton("Filtros")
        icono_boton_filtro(btn_filtros_modulos)
        btn_filtros_modulos.setIconSize(_QSize_emoji(16, 16))
        btn_filtros_modulos.setObjectName("BtnAccionNeutro")
        btn_filtros_modulos.setToolTip("Filtrar por área técnica y estado")
        dialogo_mt, grid_mt, lay_mt= self._crear_ventana_filtros(
            "Filtros de Módulos Técnicos", "Todos son opcionales; se combinan con la búsqueda de arriba.")
        self.dialogo_filtros_modulos= dialogo_mt
        grid_mt.addWidget(QLabel("Área Técnica:"), 0, 0)
        grid_mt.addWidget(self.mt_filtro_especialidad, 0, 1)
        grid_mt.addWidget(QLabel("Estado:"), 1, 0)
        grid_mt.addWidget(self.mt_filtro_estado, 1, 1)
        self._cerrar_ventana_filtros(dialogo_mt, lay_mt, callback_limpiar=self._limpiar_filtros_modulos)
        #clicked no manda datos y el diálogo de filtros a abrir ya queda fijado aquí
        btn_filtros_modulos.clicked.connect(lambda: self._abrir_ventana(self.dialogo_filtros_modulos))
        fila_busqueda_modulos.addWidget(btn_filtros_modulos)
        self.tarjeta_tabla_modulos.contenido.addLayout(fila_busqueda_modulos)

        self.tabla_modulos_tecnicos= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_modulos_tecnicos)

        self.tabla_modulos_tecnicos.setHorizontalHeaderLabels(
            ["ID", "Código", "Nombre", "Área Técnica", "Profesor", "Estado"])
        header= self.tabla_modulos_tecnicos.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_modulos_tecnicos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_modulos_tecnicos.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_modulos_tecnicos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_modulos_tecnicos.setAlternatingRowColors(True)
        self.tabla_modulos_tecnicos.setWordWrap(True)
        self.tabla_modulos_tecnicos.setMinimumHeight(300)
        self.tabla_modulos_tecnicos.verticalHeader().setVisible(False)
        self.tabla_modulos_tecnicos.setColumnHidden(0, True)
        self.tarjeta_tabla_modulos.contenido.addWidget(self.tabla_modulos_tecnicos, 1)

        self.paginacion_modulos_tecnicos= ControlPaginacion()
        self.paginacion_modulos_tecnicos.cambio.connect(self._cargar_modulos_tecnicos)
        self.tarjeta_tabla_modulos.contenido.addWidget(self.paginacion_modulos_tecnicos)

        agregar_boton_pantalla_completa(
            fila_busqueda_modulos, [self.tabla_modulos_tecnicos, self.paginacion_modulos_tecnicos],
            titulo= "Módulos Técnicos", parent=self)

        fila_acciones= QHBoxLayout()
        btn_actualizar= QPushButton("Actualizar")
        btn_actualizar.setIcon(icono_emoji("🔄"))
        btn_actualizar.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_modulos_tecnicos)
        fila_acciones.addWidget(btn_actualizar)
        btn_cargar= QPushButton("Cargar Seleccionado")
        btn_cargar.setIcon(icono_emoji("✏"))
        btn_cargar.setIconSize(_QSize_emoji(16, 16))
        btn_cargar.setObjectName("BtnAccionEditar")
        btn_cargar.clicked.connect(self._cargar_modulo_tecnico_seleccionado)
        fila_acciones.addWidget(btn_cargar)
        btn_eliminar= QPushButton("Eliminar Módulo Seleccionado")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_modulo_tecnico)
        fila_acciones.addWidget(btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla_modulos_tecnicos, self,
                                             titulo= "Detalle del Módulo Técnico")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_modulos_tecnicos.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_acciones.addStretch()
        self.tarjeta_tabla_modulos.contenido.addLayout(fila_acciones)
        disposicion.addWidget(self.tarjeta_tabla_modulos)
        disposicion.addStretch()
        return contenedor

    def _previsualizar_codigo_modulo(self, _texto=None):

        if self._codigo_modulo_manual:
            return
        if not self.mt_nombre.text().strip():
            self.mt_codigo.clear()
            return
        self.mt_codigo.setText(self._generar_codigo_modulo(excluir_id=self.id_edicion_modulo_tecnico))

    #Clic derecho sobre el campo "Código" del módulo técnico: alterna
    #entre escribirlo a mano y dejarlo autogenerado de nuevo -mismo
    #patrón que `_menu_contextual_codigo_materia` en materias.py.
    def _menu_contextual_codigo_modulo(self, pos):

        menu= QMenu(self)
        if self._codigo_modulo_manual:
            accion= menu.addAction(icono_emoji("🔄"), "Volver a autogenerado")
        else:
            accion= menu.addAction(icono_emoji("✏"), "Escribir código manualmente")
        if menu.exec(self.mt_codigo.mapToGlobal(pos)) == accion:
            if self._codigo_modulo_manual:
                self._codigo_modulo_manual= False
                self.mt_codigo.setReadOnly(True)
                self._previsualizar_codigo_modulo()
            else:
                self._codigo_modulo_manual= True
                self.mt_codigo.setReadOnly(False)
                self.mt_codigo.setFocus()
                self.mt_codigo.selectAll()

    def _generar_codigo_modulo(self, excluir_id=None):

        nombre= self.mt_nombre.text().strip()
        base= "".join(w[0] for w in nombre.upper().split()[:3]) or "MT"
        conn= obtener_conexion()
        c= conn.cursor()
        if excluir_id is not None:
            c.execute("SELECT codigo FROM materias WHERE codigo LIKE ? AND id != ?", (f"{base}-%", excluir_id))
        else:
            c.execute("SELECT codigo FROM materias WHERE codigo LIKE ?", (f"{base}-%",))
        existentes= {fila["codigo"] for fila in c.fetchall()}
        conn.close()
        n= 1
        while f"{base}-{n:03d}" in existentes:
            n += 1
        return f"{base}-{n:03d}"

    def _limpiar_modulo_tecnico(self):

        self.id_edicion_modulo_tecnico= None
        self.mt_codigo.clear()
        self._codigo_modulo_manual= False
        self.mt_codigo.setReadOnly(True)
        self.mt_nombre.clear()
        self.mt_creditos.setValue(0)
        self.mt_especialidad.setCurrentIndex(0)
        self.mt_profesor.setCurrentIndex(0)
        self.mt_estado.setCurrentIndex(0)
        self.mt_curso.setCurrentIndex(0)
        self.tabla_modulos_tecnicos.clearSelection()
        desactivar_modo_edicion(self.mt_nombre)

    def _guardar_modulo_tecnico(self):

        nombre= self.mt_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        if self.mt_especialidad.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Todo Módulo Técnico debe tener un Área Técnica asignada.", self)
            return
        if self._nombre_duplicado("materias", nombre, self.id_edicion_modulo_tecnico,
                                   filtro_extra= ("modelo_evaluacion = ?", ["Técnica (RA)"])):
            mostrar_mensaje("advertencia", "Módulo duplicado",
                             f"Ya existe un módulo técnico llamado «{nombre}».", self)
            self._destello(self.tarjeta_form_modulo, "#EF4444")
            return
        grado_id= self.mt_curso.currentData()
        if grado_id is not None and not curso_admite_componente_tecnico(grado_id):
            mostrar_mensaje("advertencia", "Combinación inválida",
                             "Los módulos técnicos solo pueden vincularse a cursos de Secundaria - Segundo Ciclo.", self)
            self._destello(self.tarjeta_form_modulo, "#EF4444")
            return
        if not self.mt_codigo.text().strip():
            self.mt_codigo.setText(self._generar_codigo_modulo(excluir_id=self.id_edicion_modulo_tecnico))
        datos= (self.mt_codigo.text().strip(), nombre, self.mt_creditos.value(),
                 self.mt_especialidad.currentData(), self.mt_profesor.currentData(), self.mt_estado.currentText(),
                 "Técnica (RA)", grado_id)
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            if self.id_edicion_modulo_tecnico is None:
                c.execute("""INSERT INTO materias (codigo, nombre, creditos, especialidad_id, profesor_id, estado,
                             modelo_evaluacion, grado_id) VALUES (?,?,?,?,?,?,?,?)""", datos)
                accion= "Registró módulo técnico"
            else:
                c.execute("""UPDATE materias SET codigo=?, nombre=?, creditos=?, especialidad_id=?, profesor_id=?,
                             estado= ?, modelo_evaluacion=?, grado_id=? WHERE id=?""", datos + (self.id_edicion_modulo_tecnico,))
                accion= "Editó módulo técnico"
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo guardar el módulo técnico:\n{error}", self)
            return
        finally:
            conn.close()
        registrar_auditoria("Politécnico", accion, self.main_window.usuario_actual, nombre)
        self._destello(self.tarjeta_form_modulo, "#22C55E")
        self._limpiar_modulo_tecnico()
        self._cargar_modulos_tecnicos()
        if hasattr(self, "at_modulo"):
            self._cargar_combos_asignaciones_tecnicas()

    def _cargar_modulo_tecnico_seleccionado(self):

        fila= self.tabla_modulos_tecnicos.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un módulo técnico de la tabla.", self)
            return
        id_mod= int(self.tabla_modulos_tecnicos.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM materias WHERE id=?", (id_mod,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_modulo_tecnico= f["id"]
        self.mt_codigo.setText(f["codigo"] or "")
        #Al cargar un módulo técnico ya existente para editarlo, el código deja de ser de solo lectura: es la otra
        #puerta de entrada (junto con el clic derecho) para poder escribirlo a mano.
        self._codigo_modulo_manual= True
        self.mt_codigo.setReadOnly(False)
        self.mt_nombre.blockSignals(True)
        self.mt_nombre.setText(f["nombre"] or "")
        self.mt_nombre.blockSignals(False)
        self.mt_creditos.setValue(f["creditos"] or 0)
        idx= self.mt_especialidad.findData(f["especialidad_id"])
        self.mt_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
        idx2= self.mt_profesor.findData(f["profesor_id"])
        self.mt_profesor.setCurrentIndex(idx2 if idx2 >= 0 else 0)
        idx_curso= self.mt_curso.findData(f["grado_id"])
        self.mt_curso.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
        self.mt_estado.setCurrentText(f["estado"] or "Activa")
        if hasattr(self, "panel_form_modulo"):
            self.panel_form_modulo.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.mt_nombre, f"Editando módulo técnico: {f['nombre'] or ''}")

    def _eliminar_modulo_tecnico(self):

        fila= self.tabla_modulos_tecnicos.currentRow()
        if fila < 0:
            return
        id_mod= int(self.tabla_modulos_tecnicos.item(fila, 0).text())
        nombre= self.tabla_modulos_tecnicos.item(fila, 2).text()
        if mostrar_mensaje(
            "pregunta", "Confirmar",
            f"¿Eliminar el módulo técnico '{nombre}'? También se eliminarán todas las "
            "asignaciones de profesores (titular y demás) que tenga.", self
        ) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            c.execute("DELETE FROM materias WHERE id=?", (id_mod,))
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo eliminar el módulo técnico:\n{error}", self)
            return
        finally:
            conn.close()
        if self.id_edicion_modulo_tecnico == id_mod:
            self._limpiar_modulo_tecnico()
        registrar_auditoria("Politécnico", "Eliminó módulo técnico", self.main_window.usuario_actual, nombre)
        self._destello(self.tarjeta_tabla_modulos, "#EF4444")
        self._cargar_modulos_tecnicos()
        if hasattr(self, "at_modulo"):
            self._cargar_combos_asignaciones_tecnicas()
            self._cargar_asignaciones_tecnicas()

    def _filtro_modulos_cambio(self):

        self.paginacion_modulos_tecnicos.reiniciar()
        self._cargar_modulos_tecnicos()

    def _limpiar_filtros_modulos(self):

        self.mt_filtro_especialidad.blockSignals(True)
        self.mt_filtro_especialidad.setCurrentIndex(0)
        self.mt_filtro_especialidad.blockSignals(False)
        self.mt_filtro_estado.blockSignals(True)
        self.mt_filtro_estado.setCurrentIndex(0)
        self.mt_filtro_estado.blockSignals(False)
        self._filtro_modulos_cambio()

    def _cargar_combos_modulos_tecnicos(self):

        conn= obtener_conexion()
        c= conn.cursor()
        self.mt_especialidad.clear()
        self.mt_especialidad.addItem("— Selecciona un área técnica —", None)
        poblar_combo_curso_opcional(self.mt_curso, solo_con_componente_tecnico=True)
        if hasattr(self, "mt_filtro_especialidad"):
            actual= self.mt_filtro_especialidad.currentData()
            self.mt_filtro_especialidad.blockSignals(True)
            self.mt_filtro_especialidad.clear()
            self.mt_filtro_especialidad.addItem("Todas las áreas técnicas", None)
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            self.mt_especialidad.addItem(fila["nombre"], fila["id"])
            if hasattr(self, "mt_filtro_especialidad"):
                self.mt_filtro_especialidad.addItem(fila["nombre"], fila["id"])
        if hasattr(self, "mt_filtro_especialidad"):
            idx= self.mt_filtro_especialidad.findData(actual)
            self.mt_filtro_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.mt_filtro_especialidad.blockSignals(False)
        self.mt_profesor.clear()
        self.mt_profesor.addItem("Sin asignar", None)
        c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre")
        for fila in c.fetchall():
            self.mt_profesor.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
        conn.close()

    def _cargar_modulos_tecnicos(self):

        if not hasattr(self, "mt_especialidad") or self.mt_especialidad.count() == 0:
            self._cargar_combos_modulos_tecnicos()
        texto= _normalizar(self.in_buscar_modulos.text().strip()) if hasattr(self, "in_buscar_modulos") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT materias.*, especialidades.nombre as especialidad_nombre,
                     (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as prof_nombre
                     FROM materias
                     LEFT JOIN especialidades ON materias.especialidad_id = especialidades.id
                     LEFT JOIN profesores ON materias.profesor_id = profesores.id
                     WHERE materias.modelo_evaluacion = 'Técnica (RA)'
                     ORDER BY materias.nombre""")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['codigo'] or ''} {fila['nombre'] or ''} {fila['especialidad_nombre'] or ''} {fila['prof_nombre'] or ''}")]
        especialidad_id_f= self.mt_filtro_especialidad.currentData() if hasattr(self, "mt_filtro_especialidad") else None
        if especialidad_id_f is not None:
            filas= [fila for fila in filas if fila["especialidad_id"] == especialidad_id_f]
        estado_f= self.mt_filtro_estado.currentText() if hasattr(self, "mt_filtro_estado") else None
        if estado_f and self.mt_filtro_estado.currentIndex() != 0:
            filas= [fila for fila in filas if fila["estado"] == estado_f]
        self.paginacion_modulos_tecnicos.establecer_total(len(filas))
        inicio, fin= self.paginacion_modulos_tecnicos.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_modulos_tecnicos):
            self.tabla_modulos_tecnicos.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_modulos_tecnicos.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_modulos_tecnicos.setItem(i, 1, QTableWidgetItem(f["codigo"] or ""))
                self.tabla_modulos_tecnicos.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_modulos_tecnicos.setItem(i, 3, QTableWidgetItem(f["especialidad_nombre"] or "—"))
                self.tabla_modulos_tecnicos.setItem(i, 4, QTableWidgetItem(f["prof_nombre"] or ""))
                self.tabla_modulos_tecnicos.setItem(i, 5, QTableWidgetItem(f["estado"] or ""))
            ajustar_anchos_columnas(self.tabla_modulos_tecnicos)

    #---------------- PROFESORES POR MÓDULO TÉCNICO (co-docentes) ---------------- Reutiliza la misma tabla
    #`materia_profesores` que ya usa la pestaña "Asignaciones" de materias.py (esa tabla no distingue entre materia
    #académica y módulo técnico: es un simple materia_id + profesor_id + seccion_id opcional + tipo_asignacion).
    #Por eso NO hace falta ningún
    #cambio de esquema ni tocar los códigos autogenerados (mt_codigo, etc.):
    #el código identifica al módulo en sí, no a una asignación de profesor, así que varias asignaciones conviven
    #perfectamente bajo un solo código. Esta pestaña es solo un atajo más cómodo, con el combo de "Materia" acotado
    #a únicamente módulos técnicos, para no tener que salir del módulo Politécnico a asignar co-docentes.
    def _tab_asignaciones_tecnicas(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        #Icono de profesor de la app (docente frente a un pizarrón, el mismo de la tab bar de esta pestaña), en vez del
        #👥 genérico.
        desc= TarjetaSeccion(EMOJI_PROFESOR, "Profesores por Módulo",
            "Aquí se asignan los docentes de un Módulo Técnico: se puede asignar más de un "
            "profesor al mismo módulo (por ejemplo, uno distinto por cada curso, sección o "
            "turno en que se imparte), además del profesor titular definido en 'Módulos "
            "Técnicos'. Usa tipos como co-titular en otra sección, auxiliar, suplente o "
            "practicante según corresponda. (La asignación de co-docentes de materias "
            "académicas normales se hace aparte, en Materias ▸ Co-Docentes.)")
        disposicion.addWidget(desc)

        self.tarjeta_form_asig_tecnica= TarjetaSeccion("➕", "Nueva Asignación")

        #Área Técnica: acota tanto el Grado/Curso y Sección de abajo (solo se listan los cursos de esa área técnica)
        #como el propio combo de Módulo Técnico (solo se listan los módulos de esa área). Pasa a la ventana de "☰
        #Filtros" (mismo patrón que Pasantías/Banco de Tareas): solo NARROWS opciones, no es un dato que se guarde en
        #la asignación. Grado/Curso y Sección de abajo SÍ son datos propios de la asignación (seccion_id opcional) y
        #por eso se quedan en el formulario. Solo se muestra si la institución tiene el módulo Politécnico activo
        #(Personalizado incluido); no aplica "Carrera" aquí porque los Módulos Técnicos no se asocian a una carrera de
        #Universidad, solo a un área técnica.
        self.lbl_filtro_especialidad_asig= QLabel("Área Técnica:")
        self.at_filtro_especialidad= QComboBox()
        conectar_tooltip_seleccion(self.at_filtro_especialidad,
            "Elige un área técnica: acota Grado/Curso, Sección y Módulo Técnico del formulario, "
            "y también filtra la tabla de abajo")
        self.at_filtro_especialidad.currentIndexChanged.connect(self._filtro_area_asignacion_tecnica_cambio)

        form= QGridLayout()
        form.setSpacing(10)
        self.at_modulo= QComboBox()
        conectar_tooltip_seleccion(self.at_modulo, "Módulo Técnico al que se asigna este profesor")
        #Igual que en Horarios/Asignaciones de materias.py: primero se elige el Grado/Curso (opcional) y eso acota las
        #opciones de Sección.
        self.at_curso= QComboBox()
        self.at_curso.currentIndexChanged.connect(self._al_cambiar_curso_asignacion_tecnica)
        self.at_seccion= QComboBox()
        self.at_profesor= QComboBox()
        conectar_tooltip_seleccion(self.at_profesor, "Profesor que se asigna al módulo técnico")
        self.at_tipo= QComboBox()
        self.at_tipo.addItems(["Titular", "Auxiliar", "Suplente", "Co-titular", "Practicante"])
        conectar_tooltip_seleccion(self.at_tipo,
            "'Titular' aquí significa titular DE ESA SECCIÓN/CURSO en particular — útil cuando "
            "varios profesores dan el mismo módulo, cada uno en un curso distinto.")
        form.addWidget(QLabel("Módulo Técnico:"), 0, 0)
        form.addWidget(self.at_modulo, 0, 1)
        form.addWidget(QLabel("Profesor:"), 0, 2)
        form.addWidget(self.at_profesor, 0, 3)
        form.addWidget(QLabel("Grado/Curso (opcional):"), 1, 0)
        form.addWidget(self.at_curso, 1, 1)
        form.addWidget(QLabel("Sección (opcional):"), 1, 2)
        form.addWidget(self.at_seccion, 1, 3)
        form.addWidget(QLabel("Tipo de asignación:"), 2, 0)
        form.addWidget(self.at_tipo, 2, 1)
        btn_guardar= QPushButton("Asignar Profesor")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_asignacion_tecnica)
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_asignacion_tecnica)
        form.addWidget(btn_limpiar, 3, 1)
        self.tarjeta_form_asig_tecnica.contenido.addLayout(form)
        self.panel_form_asig_tecnica= PanelDesplegable("Nueva Asignación")
        self.panel_form_asig_tecnica.cuerpo_layout().addWidget(self.tarjeta_form_asig_tecnica)
        disposicion.addWidget(self.panel_form_asig_tecnica)

        self.tarjeta_tabla_asig_tecnica= TarjetaSeccion(EMOJI_PROFESOR, "Profesores asignados")
        marco_busqueda, self.in_buscar_asig_tecnica= self._crear_barra_busqueda(
            "Buscar por módulo, curso, sección, profesor o tipo…", self._filtro_asignaciones_tecnicas_cambio)
        fila_busqueda_asig= QHBoxLayout()
        fila_busqueda_asig.addWidget(marco_busqueda, 1)
        self.at_filtro_tipo= QComboBox()
        self.at_filtro_tipo.addItem("Todos los tipos", None)
        self.at_filtro_tipo.addItems(["Titular", "Auxiliar", "Suplente", "Co-titular", "Practicante"])
        conectar_tooltip_seleccion(self.at_filtro_tipo, "Filtrar por tipo de asignación")
        self.at_filtro_tipo.currentIndexChanged.connect(self._filtro_asignaciones_tecnicas_cambio)
        btn_filtros_asig= QPushButton("Filtros")
        icono_boton_filtro(btn_filtros_asig)
        btn_filtros_asig.setIconSize(_QSize_emoji(16, 16))
        btn_filtros_asig.setObjectName("BtnAccionNeutro")
        btn_filtros_asig.setToolTip("Filtrar por área técnica y tipo de asignación")
        dialogo_at, grid_at, lay_at= self._crear_ventana_filtros(
            "Filtros de Profesores por Módulo",
            "Área Técnica acota también el formulario \"Nueva Asignación\" de arriba. Todos son opcionales.")
        self.dialogo_filtros_asig_tecnica= dialogo_at
        grid_at.addWidget(self.lbl_filtro_especialidad_asig, 0, 0)
        grid_at.addWidget(self.at_filtro_especialidad, 0, 1)
        grid_at.addWidget(QLabel("Tipo de asignación:"), 1, 0)
        grid_at.addWidget(self.at_filtro_tipo, 1, 1)
        self._cerrar_ventana_filtros(dialogo_at, lay_at, callback_limpiar=self._limpiar_filtros_asig_tecnica)
        #clicked no manda datos y el diálogo de filtros a abrir ya queda fijado aquí
        btn_filtros_asig.clicked.connect(lambda: self._abrir_ventana(self.dialogo_filtros_asig_tecnica))
        fila_busqueda_asig.addWidget(btn_filtros_asig)
        self.tarjeta_tabla_asig_tecnica.contenido.addLayout(fila_busqueda_asig)

        self.tabla_asig_tecnica= QTableWidget(0, 6)
        self.tabla_asig_tecnica.setHorizontalHeaderLabels(
            ["ID", "Módulo Técnico", "Grado", "Sección", "Profesor", "Tipo"])
        header= self.tabla_asig_tecnica.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_asig_tecnica.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_asig_tecnica.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_asig_tecnica.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_asig_tecnica.setAlternatingRowColors(True)
        self.tabla_asig_tecnica.setWordWrap(True)
        self.tabla_asig_tecnica.setMinimumHeight(280)
        self.tabla_asig_tecnica.verticalHeader().setVisible(False)
        self.tabla_asig_tecnica.setColumnHidden(0, True)
        aplicar_estructura_tabla(self.tabla_asig_tecnica)
        self.tarjeta_tabla_asig_tecnica.contenido.addWidget(self.tabla_asig_tecnica, 1)

        self.paginacion_asig_tecnica= ControlPaginacion()
        self.paginacion_asig_tecnica.cambio.connect(self._cargar_asignaciones_tecnicas)
        self.tarjeta_tabla_asig_tecnica.contenido.addWidget(self.paginacion_asig_tecnica)

        agregar_boton_pantalla_completa(
            fila_busqueda_asig, [self.tabla_asig_tecnica, self.paginacion_asig_tecnica],
            titulo= "Profesores Asignados", parent=self)

        fila_acciones= QHBoxLayout()
        btn_actualizar= QPushButton("Actualizar")
        btn_actualizar.setIcon(icono_emoji("🔄"))
        btn_actualizar.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_asignaciones_tecnicas)
        fila_acciones.addWidget(btn_actualizar)
        btn_eliminar= QPushButton("Eliminar Asignación")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_asignacion_tecnica)
        fila_acciones.addWidget(btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla_asig_tecnica, self,
                                             titulo= "Detalle de la Asignación")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_asig_tecnica.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_acciones.addStretch()
        self.tarjeta_tabla_asig_tecnica.contenido.addLayout(fila_acciones)
        disposicion.addWidget(self.tarjeta_tabla_asig_tecnica)
        disposicion.addStretch()
        return contenedor

    #Set de `secciones.id` cuyo Grado tiene asignada la especialidad
    #elegida en `at_filtro_especialidad` (grados.especialidad_id). None si
    #el combo está en "Todas las áreas técnicas" (sin restricción) o el
    #módulo Politécnico no está activo.
    def _secciones_de_especialidad_asignacion(self):

        if not hasattr(self, "at_filtro_especialidad") or not self._es_politecnico():
            return None
        especialidad_id= self.at_filtro_especialidad.currentData()
        if especialidad_id is None:
            return None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT secciones.id FROM secciones
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE grados.especialidad_id=?""", (especialidad_id,))
        ids= {fila["id"] for fila in c.fetchall()}
        conn.close()
        return ids

    #Igual que en los demás módulos: el combo de Área Técnica de esta
    #pestaña solo se muestra/puebla si la institución tiene el módulo
    #Politécnico activo.
    def _cargar_filtro_especialidad_asignacion_tecnica(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_asig.setVisible(es_poli)
        self.at_filtro_especialidad.setVisible(es_poli)
        if not es_poli:
            return
        actual= self.at_filtro_especialidad.currentData()
        self.at_filtro_especialidad.blockSignals(True)
        self.at_filtro_especialidad.clear()
        self.at_filtro_especialidad.addItem("Todas las áreas técnicas", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            self.at_filtro_especialidad.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= self.at_filtro_especialidad.findData(actual)
        self.at_filtro_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
        self.at_filtro_especialidad.blockSignals(False)

    #Al cambiar el Área Técnica: recarga Grado/Curso (y en cascada
    #Sección) restringidos a esa área, y recarga Módulo Técnico para que
    #solo aparezcan los módulos de esa misma área.
    def _filtro_area_asignacion_tecnica_cambio(self):

        curso_previo= self.at_curso.currentData() if self.at_curso.count() else None
        permitidas= interseccion_opcional(secciones_con_componente_tecnico_valido(),
                                            self._secciones_de_especialidad_asignacion())
        poblar_combo_curso(self.at_curso, incluir_todos=False, seleccion_previa=curso_previo,
                            secciones_permitidas= permitidas)
        self._al_cambiar_curso_asignacion_tecnica()
        self._cargar_modulos_tecnicos_combo_asignacion()

    #Puebla `at_modulo` con los Módulos Técnicos, acotados al Área
    #Técnica elegida en `at_filtro_especialidad` (si hay alguna elegida).
    def _cargar_modulos_tecnicos_combo_asignacion(self):

        especialidad_id= (self.at_filtro_especialidad.currentData()
                            if hasattr(self, "at_filtro_especialidad") and self._es_politecnico() else None)
        modulo_previo= self.at_modulo.currentData() if self.at_modulo.count() else None
        self.at_modulo.blockSignals(True)
        self.at_modulo.clear()
        grado_id= self.at_curso.currentData() if self.at_curso.count() else None
        for modulo_id_, nombre_ in modulos_tecnicos_por_area_y_curso(especialidad_id, grado_id):
            self.at_modulo.addItem(nombre_, modulo_id_)
        idx= self.at_modulo.findData(modulo_previo)
        self.at_modulo.setCurrentIndex(idx if idx >= 0 else 0)
        self.at_modulo.blockSignals(False)

    def _al_cambiar_curso_asignacion_tecnica(self, _indice=None, seccion_id_preseleccionar=None):

        permitidas= interseccion_opcional(secciones_con_componente_tecnico_valido(),
                                            self._secciones_de_especialidad_asignacion())
        cascada_seccion_por_curso(self.at_curso, self.at_seccion, incluir_todas=False,
                                   secciones_permitidas= permitidas)
        if seccion_id_preseleccionar is not None:
            idx= self.at_seccion.findData(seccion_id_preseleccionar)
            self.at_seccion.setCurrentIndex(idx if idx >= 0 else 0)
        #Al cambiar de curso, los módulos disponibles se acotan a ese curso (y a su área).
        self._cargar_modulos_tecnicos_combo_asignacion()

    def _limpiar_asignacion_tecnica(self):

        self.at_modulo.setCurrentIndex(0)
        self.at_curso.setCurrentIndex(0)
        self.at_seccion.setCurrentIndex(0)
        self.at_profesor.setCurrentIndex(0)
        self.at_tipo.setCurrentIndex(0)
        self.tabla_asig_tecnica.clearSelection()

    def _guardar_asignacion_tecnica(self):

        modulo_id= self.at_modulo.currentData()
        profesor_id= self.at_profesor.currentData()
        if modulo_id is None or profesor_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Selecciona el módulo técnico y el profesor.", self)
            return
        seccion_id= self.at_seccion.currentData()
        if seccion_id is not None and seccion_id not in secciones_con_componente_tecnico_valido():
            mostrar_mensaje("advertencia", "Combinación inválida",
                             "La sección elegida no es Secundaria - Segundo Ciclo: no puede tener módulos "
                             "técnicos asignados. Clasifícala en Materias > Secciones, o deja Sección vacía.", self)
            self._destello(self.tarjeta_form_asig_tecnica, "#EF4444")
            return
        if seccion_id is not None:
            conn_v= obtener_conexion()
            cv= conn_v.cursor()
            cv.execute("SELECT grado_id FROM secciones WHERE id=?", (seccion_id,))
            fila_seccion= cv.fetchone()
            cv.execute("SELECT grado_id FROM materias WHERE id=?", (modulo_id,))
            fila_modulo= cv.fetchone()
            conn_v.close()
            if (fila_modulo and fila_modulo["grado_id"] is not None and fila_seccion
                    and fila_seccion["grado_id"] != fila_modulo["grado_id"]):
                mostrar_mensaje("advertencia", "Curso no coincide",
                                 "Este módulo técnico está vinculado a otro curso. Elige una sección de ese mismo curso.", self)
                self._destello(self.tarjeta_form_asig_tecnica, "#EF4444")
                return
        tipo= self.at_tipo.currentText()
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            c.execute("""SELECT id FROM materia_profesores
                         WHERE materia_id=? AND profesor_id=? AND
                         (seccion_id=? OR (seccion_id IS NULL AND ? IS NULL))""",
                      (modulo_id, profesor_id, seccion_id, seccion_id))
            if c.fetchone():
                mostrar_mensaje("advertencia", "Ya existe",
                                 "Ese profesor ya está asignado a este módulo técnico (y sección).", self)
                self._destello(self.tarjeta_form_asig_tecnica, "#EF4444")
                return
            c.execute("""INSERT INTO materia_profesores (materia_id, profesor_id, seccion_id, tipo_asignacion)
                         VALUES (?,?,?,?)""", (modulo_id, profesor_id, seccion_id, tipo))
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo guardar la asignación:\n{error}", self)
            return
        finally:
            conn.close()
        registrar_auditoria("Politécnico", "Asignó profesor a módulo técnico", self.main_window.usuario_actual,
                            f"{self.at_profesor.currentText()} -> {self.at_modulo.currentText()} ({tipo})")
        self._destello(self.tarjeta_form_asig_tecnica, "#22C55E")
        self._limpiar_asignacion_tecnica()
        self._cargar_asignaciones_tecnicas()

    def _eliminar_asignacion_tecnica(self):

        fila= self.tabla_asig_tecnica.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una asignación de la tabla.", self)
            return
        id_asig= int(self.tabla_asig_tecnica.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta asignación de profesor?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            c.execute("DELETE FROM materia_profesores WHERE id=?", (id_asig,))
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo eliminar la asignación:\n{error}", self)
            return
        finally:
            conn.close()
        registrar_auditoria("Politécnico", "Eliminó asignación de profesor a módulo técnico",
                            self.main_window.usuario_actual, str(id_asig))
        self._destello(self.tarjeta_tabla_asig_tecnica, "#EF4444")
        self._cargar_asignaciones_tecnicas()

    def _filtro_asignaciones_tecnicas_cambio(self):

        self.paginacion_asig_tecnica.reiniciar()
        self._cargar_asignaciones_tecnicas()

    def _limpiar_filtros_asig_tecnica(self):

        self.at_filtro_tipo.blockSignals(True)
        self.at_filtro_tipo.setCurrentIndex(0)
        self.at_filtro_tipo.blockSignals(False)
        #at_filtro_especialidad SÍ dispara su propia cascada de Curso/Sección/
        #Módulo (ver _filtro_area_asignacion_tecnica_cambio), así que se deja
        #que dispare su señal normalmente en vez de bloquearla.
        self.at_filtro_especialidad.setCurrentIndex(0)
        self._filtro_asignaciones_tecnicas_cambio()

    def _cargar_combos_asignaciones_tecnicas(self):

        self._cargar_filtro_especialidad_asignacion_tecnica()

        self.at_profesor.clear()
        self.at_profesor.addItem("Sin asignar", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre")
        for fila in c.fetchall():
            self.at_profesor.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
        conn.close()

        self._cargar_modulos_tecnicos_combo_asignacion()

        curso_previo= self.at_curso.currentData() if self.at_curso.count() else None
        #Solo se ofrecen cursos que académicamente pueden tener componente
        #técnico (Secundaria, no Primer Ciclo — ver puede_tener_componente_tecnico
        #en configuracion.py), Y ADEMÁS, si hay un Área Técnica elegida arriba, solo los cursos de esa área (ver
        #_secciones_de_especialidad_asignacion).
        permitidas= interseccion_opcional(secciones_con_componente_tecnico_valido(),
                                            self._secciones_de_especialidad_asignacion())
        poblar_combo_curso(self.at_curso, incluir_todos=False, seleccion_previa=curso_previo,
                            secciones_permitidas= permitidas)
        self._al_cambiar_curso_asignacion_tecnica()

    def _cargar_asignaciones_tecnicas(self):

        if not hasattr(self, "at_modulo") or self.at_modulo.count() == 0:
            self._cargar_combos_asignaciones_tecnicas()
        texto= _normalizar(self.in_buscar_asig_tecnica.text().strip()) if hasattr(
            self, "in_buscar_asig_tecnica") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT materia_profesores.id, materias.nombre as modulo_nombre,
                     materias.especialidad_id as especialidad_id_modulo,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                     (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as profesor_nombre,
                     materia_profesores.tipo_asignacion
                     FROM materia_profesores
                     LEFT JOIN materias ON materia_profesores.materia_id = materias.id
                     LEFT JOIN secciones ON materia_profesores.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN profesores ON materia_profesores.profesor_id = profesores.id
                     WHERE materias.modelo_evaluacion = 'Técnica (RA)'
                     ORDER BY materias.nombre""")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['modulo_nombre'] or ''} {fila['grado_nombre'] or ''} "
                f"{fila['seccion_nombre'] or 'Todas sus secciones'} "
                f"{fila['profesor_nombre'] or ''} {fila['tipo_asignacion'] or ''}")]
        especialidad_id_f= (self.at_filtro_especialidad.currentData()
                              if hasattr(self, "at_filtro_especialidad") else None)
        if especialidad_id_f is not None:
            filas= [fila for fila in filas if fila["especialidad_id_modulo"] == especialidad_id_f]
        if hasattr(self, "at_filtro_tipo") and self.at_filtro_tipo.currentIndex() != 0:
            tipo_f= self.at_filtro_tipo.currentText()
            filas= [fila for fila in filas if fila["tipo_asignacion"] == tipo_f]
        self.paginacion_asig_tecnica.establecer_total(len(filas))
        inicio, fin= self.paginacion_asig_tecnica.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_asig_tecnica):
            self.tabla_asig_tecnica.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_asig_tecnica.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_asig_tecnica.setItem(i, 1, QTableWidgetItem(f["modulo_nombre"] or ""))
                self.tabla_asig_tecnica.setItem(i, 2, QTableWidgetItem(f["grado_nombre"] or ""))
                self.tabla_asig_tecnica.setItem(i, 3, QTableWidgetItem(f["seccion_nombre"] or "Todas"))
                self.tabla_asig_tecnica.setItem(i, 4, QTableWidgetItem(f["profesor_nombre"] or ""))
                self.tabla_asig_tecnica.setItem(i, 5, QTableWidgetItem(f["tipo_asignacion"] or ""))
            ajustar_anchos_columnas(self.tabla_asig_tecnica)

    #---------------- TALLERES Y LABORATORIOS ----------------
    def _tab_talleres(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)

        disposicion.setSpacing(14)

        lbl_info= QLabel("Vincula cada Taller/Laboratorio (definido en Materias Aulas y Laboratorios) "
                      "con el área técnica a la que pertenece.")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(18)
        self.barra_talleres= BarraSegmentadaPill(interactiva=True)
        self.barra_talleres.segmento_clicado.connect(self._alternar_filtro_talleres)
        fila_resumen.addWidget(self.barra_talleres, 2)
        leyenda_t= QHBoxLayout()
        leyenda_t.setSpacing(4)
        self.etiquetas_leyenda_talleres= {}
        for clave, etiqueta_txt, color in SEGMENTOS_TALLERES:
            lbl= ContadorClicable(etiqueta_txt, color, interactiva=True)
            #el valor por defecto fija la clave de esta vuelta del bucle; si no, todos usarían la última
            lbl.clicada.connect(lambda c=clave: self._alternar_filtro_talleres(c))
            leyenda_t.addWidget(lbl)
            self.etiquetas_leyenda_talleres[clave]= lbl
        fila_resumen.addLayout(leyenda_t, 1)
        disposicion.addLayout(fila_resumen)

        self.tarjeta_form_taller= TarjetaSeccion("🔗", "Vincular Taller/Laboratorio")
        form= QGridLayout()
        form.setSpacing(10)
        self.t_espacio= QComboBox()
        conectar_tooltip_seleccion(self.t_espacio, "Taller o laboratorio a vincular con un área técnica")
        self.t_especialidad= QComboBox()
        conectar_tooltip_seleccion(self.t_especialidad, "Área técnica a la que pertenece este taller/laboratorio")
        form.addWidget(QLabel("Taller/Laboratorio:"), 0, 0)
        form.addWidget(self.t_espacio, 0, 1)
        form.addWidget(QLabel("Área Técnica:"), 0, 2)
        form.addWidget(self.t_especialidad, 0, 3)
        btn_vincular= QPushButton("Vincular")
        btn_vincular.setIcon(icono_emoji("➕"))
        btn_vincular.setIconSize(_QSize_emoji(16, 16))
        btn_vincular.setObjectName("BtnAccionAgregar")
        btn_vincular.clicked.connect(self._vincular_taller)
        form.addWidget(btn_vincular, 1, 0)
        btn_desvincular= QPushButton("Desvincular")
        btn_desvincular.setIcon(icono_emoji("🗑"))
        btn_desvincular.setIconSize(_QSize_emoji(16, 16))
        btn_desvincular.setObjectName("BtnAccionEliminar")
        btn_desvincular.clicked.connect(self._desvincular_taller)
        form.addWidget(btn_desvincular, 1, 1)
        self.tarjeta_form_taller.contenido.addLayout(form)
        self.panel_form_taller= PanelDesplegable("Vincular Taller/Laboratorio")
        self.panel_form_taller.cuerpo_layout().addWidget(self.tarjeta_form_taller)
        disposicion.addWidget(self.panel_form_taller)

        self.tarjeta_tabla_talleres= TarjetaSeccion(EMOJI_TALLERES_LABORATORIOS, "Talleres y Laboratorios")
        fila_cabecera_tabla_talleres= QHBoxLayout()
        fila_cabecera_tabla_talleres.addStretch()
        self.tarjeta_tabla_talleres.contenido.addLayout(fila_cabecera_tabla_talleres)
        marco_busqueda, self.in_buscar_talleres= self._crear_barra_busqueda(
            "Buscar por taller/laboratorio, tipo o área técnica…", self._filtro_talleres_cambio)
        self.tarjeta_tabla_talleres.contenido.addWidget(marco_busqueda)

        self.tabla_talleres= QTableWidget(0, 5)
        aplicar_estructura_tabla(self.tabla_talleres)

        self.tabla_talleres.setHorizontalHeaderLabels(
            ["ID", "Taller/Laboratorio", "Tipo", "Capacidad", "Área Técnica Vinculada"])
        header= self.tabla_talleres.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  #"Taller/Laboratorio"
        self.tabla_talleres.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_talleres.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_talleres.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_talleres.setAlternatingRowColors(True)
        self.tabla_talleres.setWordWrap(True)
        self.tabla_talleres.setMinimumHeight(340)
        self.tabla_talleres.verticalHeader().setVisible(False)
        self.tarjeta_tabla_talleres.contenido.addWidget(self.tabla_talleres, 1)

        self.paginacion_talleres= ControlPaginacion()
        self.paginacion_talleres.cambio.connect(self._cargar_talleres)
        self.tarjeta_tabla_talleres.contenido.addWidget(self.paginacion_talleres)

        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_talleres, [self.tabla_talleres, self.paginacion_talleres],
            titulo= "Talleres y Laboratorios", parent=self)

        fila_acciones_taller= QHBoxLayout()
        btn_actualizar_taller= QPushButton("Actualizar")
        btn_actualizar_taller.setIcon(icono_emoji("🔄"))
        btn_actualizar_taller.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_taller.setObjectName("BtnAccionNeutro")
        btn_actualizar_taller.clicked.connect(self._cargar_talleres)
        fila_acciones_taller.addWidget(btn_actualizar_taller)
        btn_cargar_taller= QPushButton("Cargar Seleccionado")
        btn_cargar_taller.setIcon(icono_emoji("✏"))
        btn_cargar_taller.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_taller.setObjectName("BtnAccionEditar")
        btn_cargar_taller.clicked.connect(self._cargar_taller_seleccionado)
        fila_acciones_taller.addWidget(btn_cargar_taller)
        agregar_boton_detalle(fila_acciones_taller, self.tabla_talleres, self, titulo="Detalle del Taller/Laboratorio")
        self.tabla_talleres.doubleClicked.connect(
            #indice: celda con doble clic; se muestra el detalle de su fila
            lambda indice: mostrar_detalle_fila(self, self.tabla_talleres, indice.row(),
                                                titulo= "Detalle del Taller/Laboratorio"))
        fila_acciones_taller.addStretch()
        self.tarjeta_tabla_talleres.contenido.addLayout(fila_acciones_taller)
        disposicion.addWidget(self.tarjeta_tabla_talleres)
        disposicion.addStretch()
        return contenedor

    def _alternar_filtro_talleres(self, valor):

        self._filtro_talleres_vinculo= None if self._filtro_talleres_vinculo == valor else valor
        self.barra_talleres.establecer_filtro_activo(
            {self._filtro_talleres_vinculo} if self._filtro_talleres_vinculo else None)
        for clave, lbl in self.etiquetas_leyenda_talleres.items():
            lbl.establecer_activa(self._filtro_talleres_vinculo == clave)
        self.paginacion_talleres.reiniciar()
        self._cargar_talleres()

    def _cargar_barra_talleres(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT COUNT(*) as n FROM aulas WHERE tipo IN ('Taller','Laboratorio')
                     AND especialidad_id IS NOT NULL""")
        vinculados= c.fetchone()["n"]
        c.execute("""SELECT COUNT(*) as n FROM aulas WHERE tipo IN ('Taller','Laboratorio')
                     AND especialidad_id IS NULL""")
        sin_vincular= c.fetchone()["n"]
        conn.close()
        conteo= {"vinculado": vinculados, "sin_vincular": sin_vincular}
        if hasattr(self, "barra_talleres"):
            self.barra_talleres.establecer_datos([
                {"clave": clave, "etiqueta": etiqueta, "valor": conteo.get(clave, 0), "color": color}
                for clave, etiqueta, color in SEGMENTOS_TALLERES
            ])
        for clave, lbl in getattr(self, "etiquetas_leyenda_talleres", {}).items():
            lbl.establecer_valor(conteo.get(clave, 0))

    def _cargar_combos_talleres(self):

        self.t_espacio.clear()
        self.t_especialidad.clear()
        self.t_especialidad.addItem("Sin área técnica", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre, tipo FROM aulas WHERE tipo IN ('Taller', 'Laboratorio') ORDER BY nombre")
        for fila in c.fetchall():
            self.t_espacio.addItem(f"{fila['nombre']} ({fila['tipo']})", fila["id"])
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            self.t_especialidad.addItem(fila["nombre"], fila["id"])
        conn.close()

    def _vincular_taller(self):

        aula_id= self.t_espacio.currentData()
        if aula_id is None:
            mostrar_mensaje("advertencia", "Sin talleres/laboratorios",
                           "Primero crea un espacio de tipo Taller o Laboratorio en Materias Aulas y Laboratorios.", self)
            return
        especialidad_id= self.t_especialidad.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE aulas SET especialidad_id=? WHERE id=?", (especialidad_id, aula_id))
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", "Vinculó taller/laboratorio a área técnica",
                            self.main_window.usuario_actual,
                            f"Espacio ID {aula_id} - Área Técnica ID {especialidad_id}")
        self._destello(self.tarjeta_form_taller, "#22C55E")
        self._cargar_talleres()
        self._cargar_barra_talleres()
        self._cargar_donut_especialidades()

    def _desvincular_taller(self):

        fila= self.tabla_talleres.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un taller/laboratorio de la tabla.", self)
            return
        aula_id= int(self.tabla_talleres.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE aulas SET especialidad_id=NULL WHERE id=?", (aula_id,))
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", "Desvinculó taller/laboratorio de área técnica",
                            self.main_window.usuario_actual, f"Espacio ID {aula_id}")
        self._destello(self.tarjeta_form_taller, "#EF4444")
        self._cargar_talleres()
        self._cargar_barra_talleres()
        self._cargar_donut_especialidades()

    def _cargar_taller_seleccionado(self):

        fila= self.tabla_talleres.currentRow()
        if fila < 0:
            return
        aula_id= int(self.tabla_talleres.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT especialidad_id FROM aulas WHERE id=?", (aula_id,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        idx= self.t_espacio.findData(aula_id)
        self.t_espacio.setCurrentIndex(idx if idx >= 0 else 0)
        idx2= self.t_especialidad.findData(f["especialidad_id"] if f else None)
        self.t_especialidad.setCurrentIndex(idx2 if idx2 >= 0 else 0)
        if hasattr(self, "panel_form_taller"):
            self.panel_form_taller.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.t_espacio, "Editando taller/laboratorio")

    def _filtro_talleres_cambio(self):

        self.paginacion_talleres.reiniciar()
        self._cargar_talleres()

    def _cargar_talleres(self):

        texto= _normalizar(self.in_buscar_talleres.text().strip()) if hasattr(self, "in_buscar_talleres") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT aulas.id, aulas.nombre, aulas.tipo, aulas.capacidad, aulas.especialidad_id,
                     especialidades.nombre as especialidad_nombre
                     FROM aulas LEFT JOIN especialidades ON aulas.especialidad_id = especialidades.id
                     WHERE aulas.tipo IN ('Taller', 'Laboratorio') ORDER BY aulas.nombre""")
        filas= c.fetchall()
        conn.close()
        if self._filtro_talleres_vinculo == "vinculado":
            filas= [fila for fila in filas if fila["especialidad_id"] is not None]
        elif self._filtro_talleres_vinculo == "sin_vincular":
            filas= [fila for fila in filas if fila["especialidad_id"] is None]
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['nombre'] or ''} {fila['tipo'] or ''} {fila['especialidad_nombre'] or ''}")]
        self.paginacion_talleres.establecer_total(len(filas))
        inicio, fin= self.paginacion_talleres.rango_actual()
        filas= filas[inicio:fin]
        with tabla_pausada(self.tabla_talleres):
            self.tabla_talleres.setRowCount(len(filas))
            for i, f in enumerate(filas):
                self.tabla_talleres.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_talleres.setItem(i, 1, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_talleres.setItem(i, 2, QTableWidgetItem(f["tipo"] or ""))
                self.tabla_talleres.setItem(i, 3, QTableWidgetItem(str(f["capacidad"] or 0)))
                self.tabla_talleres.setItem(i, 4, QTableWidgetItem(f["especialidad_nombre"] or "Sin vincular"))
            ajustar_anchos_columnas(self.tabla_talleres)

    #---------------- EMPRESAS DE PASANTÍA ----------------
    def _tab_empresas(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        lbl_info= QLabel("Catálogo de empresas aliadas para pasantías: rubro, ubicación, contacto y cupos disponibles.")
        lbl_info.setObjectName("DescModulo")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        self.tarjeta_barra_empresas= TarjetaSeccion(EMOJI_EMPRESA_PASANTIA, "Empresas aliadas por rubro")
        self.barra_empresas= BarraSegmentadaPill(interactiva=False)
        self.tarjeta_barra_empresas.contenido.addWidget(self.barra_empresas)
        self.contenedor_leyenda_empresas= QWidget()
        self.layout_leyenda_empresas= QHBoxLayout(self.contenedor_leyenda_empresas)
        self.layout_leyenda_empresas.setContentsMargins(0, 6, 0, 0)
        self.layout_leyenda_empresas.setSpacing(4)
        self.tarjeta_barra_empresas.contenido.addWidget(self.contenedor_leyenda_empresas)
        disposicion.addWidget(self.tarjeta_barra_empresas)

        self.tarjeta_form_empresa= TarjetaSeccion("➕", "Nueva empresa")
        form= QGridLayout()
        form.setSpacing(10)
        self.emp_nombre= QLineEdit()
        self.emp_nombre.setPlaceholderText("Nombre de la Empresa")
        limitar_campo_texto(self.emp_nombre, 300)
        self.emp_rubro= QComboBox()
        self.emp_rubro.setEditable(True)
        self.emp_rubro.addItems(RUBROS_SUGERIDOS)
        conectar_tooltip_seleccion(self.emp_rubro, "Rubro / sector de la empresa")
        self.emp_ubicacion= QLineEdit()
        self.emp_ubicacion.setPlaceholderText("Ubicación (ciudad/dirección)")
        limitar_campo_texto(self.emp_ubicacion, 300)
        self.emp_contacto= QLineEdit()
        self.emp_contacto.setPlaceholderText("Contacto")
        limitar_campo_texto(self.emp_contacto, 300)
        self.emp_telefono= QLineEdit()
        self.emp_telefono.setPlaceholderText("Teléfono")
        limitar_campo_texto(self.emp_telefono, 300)
        self.emp_cupos= QSpinBox()
        self.emp_cupos.setRange(0, 500)
        self.emp_cupos.setToolTip("Cantidad de cupos de pasantía disponibles en esta empresa")
        form.addWidget(self.emp_nombre, 0, 0)
        form.addWidget(self.emp_rubro, 0, 1)
        form.addWidget(self.emp_ubicacion, 0, 2)
        form.addWidget(self.emp_contacto, 1, 0)
        form.addWidget(self.emp_telefono, 1, 1)
        form.addWidget(self.emp_cupos, 1, 2)
        btn_guardar= QPushButton("Guardar Empresa")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_empresa)
        form.addWidget(btn_guardar, 2, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_empresa)
        form.addWidget(btn_limpiar, 2, 1)
        self.tarjeta_form_empresa.contenido.addLayout(form)
        self.panel_form_empresa= PanelDesplegable("Nueva empresa")
        self.panel_form_empresa.cuerpo_layout().addWidget(self.tarjeta_form_empresa)
        disposicion.addWidget(self.panel_form_empresa)

        self.tarjeta_tabla_empresas= TarjetaSeccion(EMOJI_EMPRESA_PASANTIA, "Empresas registradas")
        fila_cabecera_tabla_empresas= QHBoxLayout()
        fila_cabecera_tabla_empresas.addStretch()
        self.tarjeta_tabla_empresas.contenido.addLayout(fila_cabecera_tabla_empresas)
        marco_busqueda, self.in_buscar_empresas= self._crear_barra_busqueda(
            "Buscar por empresa, rubro, ubicación o contacto…", self._filtro_empresas_cambio)
        self.tarjeta_tabla_empresas.contenido.addWidget(marco_busqueda)

        self.tabla_empresas= QTableWidget(0, 7)
        aplicar_estructura_tabla(self.tabla_empresas)

        self.tabla_empresas.setHorizontalHeaderLabels(
            ["ID", "Empresa", "Rubro", "Ubicación", "Contacto", "Teléfono", "Cupos"])
        header= self.tabla_empresas.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  #"Empresa"
        self.tabla_empresas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_empresas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_empresas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_empresas.setAlternatingRowColors(True)
        self.tabla_empresas.setWordWrap(True)
        self.tabla_empresas.setMinimumHeight(340)
        self.tabla_empresas.verticalHeader().setVisible(False)
        self.tarjeta_tabla_empresas.contenido.addWidget(self.tabla_empresas, 1)

        self.paginacion_empresas= ControlPaginacion()
        self.paginacion_empresas.cambio.connect(self._cargar_empresas)
        self.tarjeta_tabla_empresas.contenido.addWidget(self.paginacion_empresas)

        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_empresas, [self.tabla_empresas, self.paginacion_empresas],
            titulo= "Empresas Registradas", parent=self)

        fila_acciones= QHBoxLayout()
        btn_actualizar_emp= QPushButton("Actualizar")
        btn_actualizar_emp.setIcon(icono_emoji("🔄"))
        btn_actualizar_emp.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_emp.setObjectName("BtnAccionNeutro")
        btn_actualizar_emp.clicked.connect(self._cargar_empresas)
        fila_acciones.addWidget(btn_actualizar_emp)
        btn_editar= QPushButton("Cargar Seleccionada")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_seleccionado_empresa)
        fila_acciones.addWidget(btn_editar)
        btn_eliminar= QPushButton("Eliminar Empresa")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_empresa)
        fila_acciones.addWidget(btn_eliminar)
        agregar_boton_detalle(fila_acciones, self.tabla_empresas, self, titulo="Detalle de la Empresa")
        self.tabla_empresas.doubleClicked.connect(
            #indice: celda con doble clic; se muestra el detalle de su fila
            lambda indice: mostrar_detalle_fila(self, self.tabla_empresas, indice.row(),
                                                titulo= "Detalle de la Empresa"))
        fila_acciones.addStretch()
        self.tarjeta_tabla_empresas.contenido.addLayout(fila_acciones)
        disposicion.addWidget(self.tarjeta_tabla_empresas)
        disposicion.addStretch()
        return contenedor

    def _guardar_empresa(self):

        if not self.emp_nombre.text().strip():
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        datos= (self.emp_nombre.text().strip(), self.emp_rubro.currentText().strip(),
                 self.emp_ubicacion.text().strip(), self.emp_contacto.text().strip(),
                 self.emp_telefono.text().strip(), self.emp_cupos.value())
        conn= obtener_conexion()
        c= conn.cursor()
        if self.id_edicion_empresa is None:
            c.execute("""INSERT INTO empresas_pasantia (nombre, rubro, ubicacion, contacto, telefono, cupos)
                         VALUES (?,?,?,?,?,?)""", datos)
            accion= "Agregó empresa de pasantía"
        else:
            c.execute("""UPDATE empresas_pasantia SET nombre=?, rubro=?, ubicacion=?, contacto=?,
                         telefono= ?, cupos=? WHERE id=?""", datos + (self.id_edicion_empresa,))
            accion= "Editó empresa de pasantía"
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", accion, self.main_window.usuario_actual, self.emp_nombre.text().strip())
        self._destello(self.tarjeta_form_empresa, "#22C55E")
        self._limpiar_empresa()
        self._cargar_empresas()
        self._cargar_barra_empresas()
        self._cargar_resumen_cabecera()

    def _limpiar_empresa(self):

        self.id_edicion_empresa= None
        self.emp_nombre.clear()
        self.emp_rubro.setCurrentIndex(-1)
        self.emp_rubro.clearEditText()
        self.emp_ubicacion.clear()
        self.emp_contacto.clear()
        self.emp_telefono.clear()
        self.emp_cupos.setValue(0)
        self.tabla_empresas.clearSelection()
        desactivar_modo_edicion(self.emp_nombre)

    def _cargar_seleccionado_empresa(self):

        fila= self.tabla_empresas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una empresa de la tabla.", self)
            return
        id_emp= int(self.tabla_empresas.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM empresas_pasantia WHERE id=?", (id_emp,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_empresa= f["id"]
        self.emp_nombre.setText(f["nombre"] or "")
        self.emp_rubro.setCurrentText(f["rubro"] or "")
        self.emp_ubicacion.setText(f["ubicacion"] or "")
        self.emp_contacto.setText(f["contacto"] or "")
        self.emp_telefono.setText(f["telefono"] or "")
        self.emp_cupos.setValue(f["cupos"] or 0)
        if hasattr(self, "panel_form_empresa"):
            self.panel_form_empresa.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.emp_nombre, f"Editando empresa: {f['nombre'] or ''}")

    def _eliminar_empresa(self):

        fila= self.tabla_empresas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una empresa de la tabla.", self)
            return
        id_emp= int(self.tabla_empresas.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta empresa?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM empresas_pasantia WHERE id=?", (id_emp,))
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", "Eliminó empresa", self.main_window.usuario_actual, str(id_emp))
        self._destello(self.tarjeta_tabla_empresas, "#EF4444")
        self._limpiar_empresa()
        self._cargar_empresas()
        self._cargar_barra_empresas()
        self._cargar_resumen_cabecera()

    def _filtro_empresas_cambio(self):

        self.paginacion_empresas.reiniciar()
        self._cargar_empresas()

    def _cargar_empresas(self):

        texto= _normalizar(self.in_buscar_empresas.text().strip()) if hasattr(self, "in_buscar_empresas") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM empresas_pasantia ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['nombre'] or ''} {fila['rubro'] or ''} {fila['ubicacion'] or ''} {fila['contacto'] or ''}")]
        self.paginacion_empresas.establecer_total(len(filas))
        inicio, fin= self.paginacion_empresas.rango_actual()
        filas= filas[inicio:fin]
        with tabla_pausada(self.tabla_empresas):
            self.tabla_empresas.setRowCount(len(filas))
            for i, f in enumerate(filas):
                self.tabla_empresas.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_empresas.setItem(i, 1, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_empresas.setItem(i, 2, QTableWidgetItem(f["rubro"] or ""))
                self.tabla_empresas.setItem(i, 3, QTableWidgetItem(f["ubicacion"] or ""))
                self.tabla_empresas.setItem(i, 4, QTableWidgetItem(f["contacto"] or ""))
                self.tabla_empresas.setItem(i, 5, QTableWidgetItem(f["telefono"] or ""))
                self.tabla_empresas.setItem(i, 6, QTableWidgetItem(str(f["cupos"] or 0)))
            ajustar_anchos_columnas(self.tabla_empresas)

    def _cargar_barra_empresas(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT COALESCE(NULLIF(TRIM(rubro), ''), 'Sin rubro') as rubro, COUNT(*) as total
                     FROM empresas_pasantia GROUP BY rubro ORDER BY total DESC""")
        filas= c.fetchall()
        conn.close()
        principales= filas[:5]
        resto= filas[5:]
        segmentos= []
        for i, f in enumerate(principales):
            segmentos.append({"clave": f["rubro"], "etiqueta": f["rubro"], "valor": f["total"],
                               "color": PALETA_SERIES_POLI[i % len(PALETA_SERIES_POLI)]})
        if resto:
            segmentos.append({"clave": "__otros__", "etiqueta": "Otros",
                               "valor": sum(f["total"] for f in resto), "color": "#94A3B8"})
        if hasattr(self, "barra_empresas"):
            self.barra_empresas.establecer_datos(segmentos)
            self._actualizar_leyenda_empresas(segmentos)

    def _actualizar_leyenda_empresas(self, segmentos):

        while self.layout_leyenda_empresas.count():
            item= self.layout_leyenda_empresas.takeAt(0)
            wdg= item.widget()
            if wdg is not None:
                wdg.deleteLater()
        if not segmentos:
            lbl= QLabel("Aún no hay empresas registradas.")
            lbl.setObjectName("DescModulo")
            self.layout_leyenda_empresas.addWidget(lbl)
            return
        for seg in segmentos:
            contenedor= QWidget()
            fila= QHBoxLayout(contenedor)
            fila.setContentsMargins(0, 0, 0, 0)
            fila.setSpacing(6)
            lbl_punto= QLabel()
            lbl_punto.setFixedSize(9, 9)
            lbl_punto.setStyleSheet(f"background-color:{seg['color']}; border-radius:4px;")
            fila.addWidget(lbl_punto)
            lbl_texto= QLabel(f"{seg['etiqueta']} · {seg['valor']}")
            lbl_texto.setObjectName("DescModulo")
            fila.addWidget(lbl_texto)
            self.layout_leyenda_empresas.addWidget(contenedor)
        self.layout_leyenda_empresas.addStretch()

    #---------------- CONTROL DE PASANTÍAS ----------------
    def _tab_pasantias(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setSpacing(14)

        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(18)
        self.barra_pasantias= BarraSegmentadaPill(interactiva=True)
        self.barra_pasantias.segmento_clicado.connect(self._alternar_filtro_pasantias)
        fila_resumen.addWidget(self.barra_pasantias, 2)
        leyenda_p= QHBoxLayout()
        leyenda_p.setSpacing(4)
        self.etiquetas_leyenda_pasantias= {}
        for clave, etiqueta_txt, color in SEGMENTOS_PASANTIAS:
            lbl= ContadorClicable(etiqueta_txt, color, interactiva=True)
            #el valor por defecto fija la clave de esta vuelta del bucle; si no, todos usarían la última
            lbl.clicada.connect(lambda c=clave: self._alternar_filtro_pasantias(c))
            leyenda_p.addWidget(lbl)
            self.etiquetas_leyenda_pasantias[clave]= lbl
        fila_resumen.addLayout(leyenda_p, 1)
        disposicion.addLayout(fila_resumen)

        self.tarjeta_form_pasantia= TarjetaSeccion("➕", "Registrar pasantía")

        #Área Técnica / Carrera / Curso / Sección / Buscar estudiante pasan a la ventana de "☰ Filtros" (mismo patrón
        #que Banco de Tareas ▸ Entregas): siguen acotando las opciones del combo "Estudiante" de abajo, y AHORA TAMBIÉN
        #filtran la tabla "Pasantías registradas". Se crean aquí como atributos normales del módulo; se colocan dentro
        #del diálogo en _construir_dialogo_filtros_pasantias.
        self.lbl_filtro_especialidad_pasantia= QLabel("Área Técnica:")
        self.p_filtro_especialidad= QComboBox()
        self.p_filtro_especialidad.setToolTip("Filtrar por área técnica del estudiante")
        conectar_tooltip_seleccion(self.p_filtro_especialidad, "Filtrar por área técnica del estudiante")
        self.p_filtro_especialidad.currentIndexChanged.connect(self._filtro_tecnico_pasantia_cambio)

        self.lbl_filtro_carrera_pasantia= QLabel("Carrera:")
        self.p_filtro_carrera= QComboBox()
        self.p_filtro_carrera.setToolTip("Filtrar por carrera del estudiante")
        conectar_tooltip_seleccion(self.p_filtro_carrera, "Filtrar por carrera del estudiante")
        self.p_filtro_carrera.currentIndexChanged.connect(self._filtro_tecnico_pasantia_cambio)

        self.p_filtro_curso= QComboBox()
        self.p_filtro_curso.setToolTip("Filtrar por curso/grado del estudiante")
        conectar_tooltip_seleccion(self.p_filtro_curso, "Filtrar por curso/grado del estudiante")
        self.p_filtro_curso.currentIndexChanged.connect(self._filtro_curso_pasantia_cambio)

        self.p_filtro_seccion= QComboBox()
        self.p_filtro_seccion.setToolTip("Filtrar por sección del estudiante")
        conectar_tooltip_seleccion(self.p_filtro_seccion, "Filtrar por sección del estudiante")
        self.p_filtro_seccion.currentIndexChanged.connect(self._filtro_estudiantes_pasantia_cambio)

        marco_buscar_est, self.p_buscar_estudiante= self._crear_barra_busqueda(
            "Buscar estudiante por nombre, apellido o matrícula…", self._filtro_estudiantes_pasantia_cambio)
        self._construir_dialogo_filtros_pasantias(marco_buscar_est)

        form= QGridLayout()
        form.setSpacing(10)
        self.p_estudiante= QComboBox()
        conectar_tooltip_seleccion(self.p_estudiante,
            "Estudiante que realiza la pasantía (usa \" Filtros\" para ubicarlo más rápido)")
        self.p_empresa= QComboBox()
        conectar_tooltip_seleccion(self.p_empresa, "Empresa donde el estudiante realiza la pasantía")
        self.p_horas= QDoubleSpinBox()
        self.p_horas.setRange(0, 5000)
        self.p_horas.setDecimals(0)
        self.p_horas.setSuffix(" horas")
        self.p_horas.setToolTip("Horas acumuladas de la pasantía")
        self.p_estado= QComboBox()
        self.p_estado.addItems(ESTADOS_PASANTIA)
        conectar_tooltip_seleccion(self.p_estado, "Estado actual de la pasantía (En curso, Finalizada, Suspendida)")
        self.p_desempeno= QLineEdit()
        self.p_desempeno.setPlaceholderText("Desempeño técnico (observaciones)")
        limitar_campo_texto(self.p_desempeno, 300)
        form.addWidget(self.p_estudiante, 0, 0)
        form.addWidget(self.p_empresa, 0, 1)
        form.addWidget(self.p_horas, 0, 2)
        form.addWidget(self.p_estado, 1, 0)
        form.addWidget(self.p_desempeno, 1, 1, 1, 2)
        btn_guardar= QPushButton("Registrar Pasantía")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_pasantia)
        form.addWidget(btn_guardar, 2, 0)
        btn_limpiar_pas= QPushButton("Limpiar")
        btn_limpiar_pas.setIcon(icono_emoji("🧹"))
        btn_limpiar_pas.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_pas.setObjectName("BtnAccionNeutro")
        btn_limpiar_pas.clicked.connect(self._limpiar_pasantia)
        form.addWidget(btn_limpiar_pas, 2, 1)
        self.tarjeta_form_pasantia.contenido.addLayout(form)
        self.panel_form_pasantia= PanelDesplegable("Registrar pasantía")
        self.panel_form_pasantia.cuerpo_layout().addWidget(self.tarjeta_form_pasantia)
        disposicion.addWidget(self.panel_form_pasantia)

        self.lbl_resumen_filtros_pasantias= QLabel("")
        self.lbl_resumen_filtros_pasantias.setWordWrap(True)
        self.lbl_resumen_filtros_pasantias.setTextFormat(Qt.TextFormat.RichText)
        disposicion.addWidget(self.lbl_resumen_filtros_pasantias)

        self.tarjeta_tabla_pasantias= TarjetaSeccion(EMOJI_CONTROL_PASANTIAS, "Pasantías registradas")
        marco_busqueda, self.in_buscar_pasantias= self._crear_barra_busqueda(
            "Buscar por estudiante, empresa o estado…", self._filtro_pasantias_cambio)
        fila_busqueda_pasantias= QHBoxLayout()
        fila_busqueda_pasantias.addWidget(marco_busqueda, 1)
        self.btn_filtros_pasantias= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_pasantias)
        self.btn_filtros_pasantias.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_pasantias.setObjectName("BtnAccionNeutro")
        self.btn_filtros_pasantias.setToolTip("Filtrar por área técnica, carrera, curso y sección del estudiante")
        #clicked no manda datos y el diálogo de filtros a abrir ya queda fijado aquí
        self.btn_filtros_pasantias.clicked.connect(lambda: self._abrir_ventana(self.dialogo_filtros_pasantias))
        fila_busqueda_pasantias.addWidget(self.btn_filtros_pasantias)
        self.tarjeta_tabla_pasantias.contenido.addLayout(fila_busqueda_pasantias)


        self.tabla_pasantias= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_pasantias)

        self.tabla_pasantias.setHorizontalHeaderLabels(
            ["No.", "ID", "Estudiante", "Empresa", "Horas Acumuladas", "Estado"])
        header= self.tabla_pasantias.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  #"Estudiante"
        self.tabla_pasantias.setColumnWidth(0, 48)
        self.tabla_pasantias.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_pasantias.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_pasantias.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_pasantias.setAlternatingRowColors(True)
        self.tabla_pasantias.setWordWrap(True)
        self.tabla_pasantias.setMinimumHeight(340)
        self.tabla_pasantias.verticalHeader().setVisible(False)
        self.tarjeta_tabla_pasantias.contenido.addWidget(self.tabla_pasantias, 1)

        self.paginacion_pasantias= ControlPaginacion()
        self.paginacion_pasantias.cambio.connect(self._cargar_pasantias)
        self.tarjeta_tabla_pasantias.contenido.addWidget(self.paginacion_pasantias)

        agregar_boton_pantalla_completa(
            fila_busqueda_pasantias, [self.tabla_pasantias, self.paginacion_pasantias],
            titulo= "Pasantías Registradas", parent=self)

        fila_acciones_pas= QHBoxLayout()
        btn_actualizar_pas= QPushButton("Actualizar")
        btn_actualizar_pas.setIcon(icono_emoji("🔄"))
        btn_actualizar_pas.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_pas.setObjectName("BtnAccionNeutro")
        btn_actualizar_pas.clicked.connect(self._cargar_pasantias)
        fila_acciones_pas.addWidget(btn_actualizar_pas)
        btn_cargar_pas= QPushButton("Cargar Seleccionada")
        btn_cargar_pas.setIcon(icono_emoji("✏"))
        btn_cargar_pas.setIconSize(_QSize_emoji(16, 16))
        btn_cargar_pas.setObjectName("BtnAccionEditar")
        btn_cargar_pas.clicked.connect(self._cargar_pasantia_seleccionada)
        fila_acciones_pas.addWidget(btn_cargar_pas)
        btn_eliminar= QPushButton("Eliminar Pasantía Seleccionada")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_pasantia)
        fila_acciones_pas.addWidget(btn_eliminar)
        btn_detalle_pas= agregar_boton_detalle(fila_acciones_pas, self.tabla_pasantias, self, titulo="Detalle de la Pasantía")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_pasantias.doubleClicked.connect(lambda *_: btn_detalle_pas.click())
        fila_acciones_pas.addStretch()
        self.tarjeta_tabla_pasantias.contenido.addLayout(fila_acciones_pas)
        disposicion.addWidget(self.tarjeta_tabla_pasantias)
        disposicion.addStretch()
        return contenedor

    #Ventanita (no modal) con Área Técnica, Carrera, Curso, Sección y
    #el buscador de estudiante — mismo patrón que
    #`_construir_dialogo_filtros_tareas` de banco_tareas.py. Estos
    #combos acotan tanto el combo "Estudiante" del formulario de arriba
    #como, ahora, la propia tabla "Pasantías registradas" (según el
    #curso/sección/área técnica/carrera real del estudiante de cada
    #pasantía).
    def _construir_dialogo_filtros_pasantias(self, marco_buscar_est):

        dialogo, grid, lay_dialogo= self._crear_ventana_filtros(
            "Filtros de Pasantías",
            "Acotan tanto el combo \"Estudiante\" del formulario de arriba como la tabla "
            "\"Pasantías registradas\". Todos son opcionales.")
        self.dialogo_filtros_pasantias= dialogo
        fila= 0
        grid.addWidget(QLabel("Buscar estudiante:"), fila, 0)
        grid.addWidget(marco_buscar_est, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_filtro_especialidad_pasantia, fila, 0)
        grid.addWidget(self.p_filtro_especialidad, fila, 1)
        fila += 1
        grid.addWidget(self.lbl_filtro_carrera_pasantia, fila, 0)
        grid.addWidget(self.p_filtro_carrera, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Curso/Grado:"), fila, 0)
        grid.addWidget(self.p_filtro_curso, fila, 1)
        fila += 1
        grid.addWidget(QLabel("Sección:"), fila, 0)
        grid.addWidget(self.p_filtro_seccion, fila, 1)
        self._cerrar_ventana_filtros(dialogo, lay_dialogo, callback_limpiar=self._limpiar_filtros_pasantias)

    def _limpiar_filtros_pasantias(self):

        self.p_buscar_estudiante.blockSignals(True)
        self.p_buscar_estudiante.clear()
        self.p_buscar_estudiante.blockSignals(False)
        for combo in (self.p_filtro_especialidad, self.p_filtro_carrera, self.p_filtro_curso):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._cargar_filtro_seccion_pasantia()
        self._filtro_estudiantes_pasantia_cambio()

    #Como Área Técnica/Carrera/Curso/Sección/Buscar ahora viven en la
    #ventana de Filtros (oculta por defecto), esta línea deja a la vista,
    #sin abrir el diálogo, qué se está mostrando en la tabla.
    def _actualizar_resumen_filtros_pasantias(self):

        if not hasattr(self, "lbl_resumen_filtros_pasantias"):
            return
        #Iconos dibujados con QPainter (mismos dibujos que ya usa el resto de la app, ver _cargar_resumen_cabecera más
        #abajo), insertados como <img> inline en vez del emoji real para no depender de una fuente de emojis del
        #sistema ni desentonar con el resto de la UI.
        partes= []
        if self._es_politecnico() and self.p_filtro_especialidad.currentData() is not None:
            partes.append(f"{html_icono_emoji('🧩', 14)} {self.p_filtro_especialidad.currentText()}")
        if self._es_universidad() and self.p_filtro_carrera.currentData() is not None:
            partes.append(f"{html_icono_emoji('🎓', 14)} {self.p_filtro_carrera.currentText()}")
        if self.p_filtro_curso.currentData() is not None:
            partes.append(f"{html_icono_emoji('🎓', 14)} {self.p_filtro_curso.currentText()}")
        if self.p_filtro_seccion.currentData() is not None:
            partes.append(f"{html_icono_emoji('🏫', 14)} {self.p_filtro_seccion.currentText()}")
        if self.p_buscar_estudiante.text().strip():
            partes.append(f"{html_icono_emoji('🔍', 14)} «{self.p_buscar_estudiante.text().strip()}»")
        self.lbl_resumen_filtros_pasantias.setText(" · ".join(partes))

    def _filtro_tecnico_pasantia_cambio(self):

        self._filtro_estudiantes_pasantia_cambio()

    def _alternar_filtro_pasantias(self, valor):

        self._filtro_pasantias_estado= None if self._filtro_pasantias_estado == valor else valor
        self.barra_pasantias.establecer_filtro_activo(
            {self._filtro_pasantias_estado} if self._filtro_pasantias_estado else None)
        for clave, lbl in self.etiquetas_leyenda_pasantias.items():
            lbl.establecer_activa(self._filtro_pasantias_estado == clave)
        self.paginacion_pasantias.reiniciar()
        self._cargar_pasantias()

    def _cargar_barra_pasantias(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT estado, COUNT(*) as n FROM pasantias GROUP BY estado")
        conteo= {fila["estado"]: fila["n"] for fila in c.fetchall()}
        conn.close()
        if hasattr(self, "barra_pasantias"):
            self.barra_pasantias.establecer_datos([
                {"clave": clave, "etiqueta": etiqueta, "valor": conteo.get(clave, 0), "color": color}
                for clave, etiqueta, color in SEGMENTOS_PASANTIAS
            ])
        for clave, lbl in getattr(self, "etiquetas_leyenda_pasantias", {}).items():
            lbl.establecer_valor(conteo.get(clave, 0))

    def _limpiar_pasantia(self):

        self.id_edicion_pasantia= None
        if hasattr(self, "p_buscar_estudiante"):
            self.p_buscar_estudiante.clear()
        if hasattr(self, "p_filtro_curso"):
            self.p_filtro_curso.setCurrentIndex(0)
        if hasattr(self, "p_filtro_seccion"):
            self.p_filtro_seccion.setCurrentIndex(0)
        self.p_estudiante.setCurrentIndex(0)
        self.p_empresa.setCurrentIndex(0)
        self.p_horas.setValue(0)
        self.p_estado.setCurrentIndex(0)
        self.p_desempeno.clear()
        self.tabla_pasantias.clearSelection()
        desactivar_modo_edicion(self.p_desempeno)

    def _cargar_pasantia_seleccionada(self):

        fila= self.tabla_pasantias.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una pasantía de la tabla.", self)
            return
        id_p= int(self.tabla_pasantias.item(fila, 1).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM pasantias WHERE id=?", (id_p,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_pasantia= f["id"]
        #Limpiamos los filtros de curso/sección/búsqueda para asegurarnos de que el estudiante de la pasantía cargada
        #esté entre las opciones del combo, sin importar qué filtro haya quedado activo.
        if hasattr(self, "p_buscar_estudiante"):
            self.p_buscar_estudiante.clear()
        if hasattr(self, "p_filtro_curso"):
            self.p_filtro_curso.setCurrentIndex(0)
        if hasattr(self, "p_filtro_seccion"):
            self.p_filtro_seccion.setCurrentIndex(0)
        idx_est= self.p_estudiante.findData(f["estudiante_id"])
        self.p_estudiante.setCurrentIndex(idx_est if idx_est >= 0 else 0)
        idx_emp= self.p_empresa.findData(f["empresa_id"])
        self.p_empresa.setCurrentIndex(idx_emp if idx_emp >= 0 else 0)
        self.p_horas.setValue(f["horas_acumuladas"] or 0)
        self.p_estado.setCurrentText(f["estado"] or "")
        self.p_desempeno.setText(f["desempeno"] or "")
        if hasattr(self, "panel_form_pasantia"):
            self.panel_form_pasantia.expandir(True, animar=False)  #de golpe al editar
        activar_modo_edicion(self.p_desempeno, "Editando pasantía")

    def _cargar_combos_pasantias(self):

        self.p_empresa.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        #Traemos también matrícula, curso y sección de cada estudiante activo para poder filtrar el combo por
        #curso/sección y por texto de búsqueda.
        c.execute("""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos, estudiantes.matricula,
                     estudiantes.especialidad_id as especialidad_id, estudiantes.carrera_id as carrera_id,
                     secciones.id as seccion_id, secciones.nombre as seccion_nombre,
                     grados.id as grado_id, grados.nombre as grado_nombre
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     WHERE estudiantes.estado='Activo'
                     ORDER BY grados.orden, secciones.nombre, estudiantes.apellidos""")
        self._estudiantes_pasantia= [dict(fila) for fila in c.fetchall()]
        c.execute("SELECT id, nombre FROM empresas_pasantia ORDER BY nombre")
        for fila in c.fetchall():
            self.p_empresa.addItem(fila["nombre"], fila["id"])
        conn.close()

        poblar_combo_curso(self.p_filtro_curso, incluir_todos=False)
        self._cargar_filtro_seccion_pasantia()
        self._cargar_filtro_especialidad_carrera_pasantia()
        self._filtro_estudiantes_pasantia_cambio()

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

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera de
    #Pasantías solo se muestran/pueblan si la institución tiene ese
    #módulo activo.
    def _cargar_filtro_especialidad_carrera_pasantia(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_pasantia.setVisible(es_poli)
        self.p_filtro_especialidad.setVisible(es_poli)
        if es_poli:
            actual= self.p_filtro_especialidad.currentData()
            self.p_filtro_especialidad.blockSignals(True)
            self.p_filtro_especialidad.clear()
            self.p_filtro_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.p_filtro_especialidad.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.p_filtro_especialidad.findData(actual)
            self.p_filtro_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.p_filtro_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_pasantia.setVisible(es_uni)
        self.p_filtro_carrera.setVisible(es_uni)
        if es_uni:
            actual= self.p_filtro_carrera.currentData()
            self.p_filtro_carrera.blockSignals(True)
            self.p_filtro_carrera.clear()
            self.p_filtro_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.p_filtro_carrera.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.p_filtro_carrera.findData(actual)
            self.p_filtro_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.p_filtro_carrera.blockSignals(False)

    #Recarga el combo de sección según el curso elegido (o todas).
    def _cargar_filtro_seccion_pasantia(self):

        cascada_seccion_por_curso(self.p_filtro_curso, self.p_filtro_seccion, incluir_todas=False)

    def _filtro_curso_pasantia_cambio(self):

        self._cargar_filtro_seccion_pasantia()
        self._filtro_estudiantes_pasantia_cambio()

    #Recalcula las opciones del combo 'Estudiante' según los filtros de
    #búsqueda, curso y sección, conservando la selección previa si sigue
    #siendo válida.
    def _filtro_estudiantes_pasantia_cambio(self):

        id_previo= self.p_estudiante.currentData()
        texto= _normalizar(self.p_buscar_estudiante.text().strip()) if hasattr(self, "p_buscar_estudiante") else ""
        grado_id= self.p_filtro_curso.currentData() if hasattr(self, "p_filtro_curso") else None
        seccion_id= self.p_filtro_seccion.currentData() if hasattr(self, "p_filtro_seccion") else None
        especialidad_id= (self.p_filtro_especialidad.currentData()
                            if hasattr(self, "p_filtro_especialidad") and self._es_politecnico() else None)
        carrera_id= (self.p_filtro_carrera.currentData()
                      if hasattr(self, "p_filtro_carrera") and self._es_universidad() else None)
        self.p_estudiante.blockSignals(True)
        self.p_estudiante.clear()
        #Placeholder real (sin datos) primero: evita que, con los filtros
        #amplios (p.ej. "Todos los cursos"), quede seleccionado por accidente
        #el primer estudiante de la lista sin que el usuario lo haya elegido.
        self.p_estudiante.addItem("Selecciona un estudiante…", None)
        #f: fila de un estudiante con pasantía; se filtra por curso y sección
        for f in getattr(self, "_estudiantes_pasantia", []):
            if grado_id is not None and f["grado_id"] != grado_id:
                continue
            if seccion_id is not None and f["seccion_id"] != seccion_id:
                continue
            if especialidad_id is not None and f.get("especialidad_id") != especialidad_id:
                continue
            if carrera_id is not None and f.get("carrera_id") != carrera_id:
                continue
            if texto and texto not in _normalizar(
                    f"{f['nombre'] or ''} {f['apellidos'] or ''} {f['matricula'] or ''}"):
                continue
            self.p_estudiante.addItem(f"{f['nombre']} {f['apellidos'] or ''}", f["id"])
        idx= self.p_estudiante.findData(id_previo)
        self.p_estudiante.setCurrentIndex(idx if idx >= 0 else 0)
        self.p_estudiante.blockSignals(False)
        self._actualizar_resumen_filtros_pasantias()
        if hasattr(self, "paginacion_pasantias"):
            self.paginacion_pasantias.reiniciar()
            self._cargar_pasantias()

    def _guardar_pasantia(self):

        est_id= self.p_estudiante.currentData()
        emp_id= self.p_empresa.currentData()
        if est_id is None or emp_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona estudiante y empresa.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        if getattr(self, "id_edicion_pasantia", None) is None:
            c.execute("""INSERT INTO pasantias (estudiante_id, empresa_id, horas_acumuladas, estado, desempeno)
                         VALUES (?,?,?,?,?)""",
                      (est_id, emp_id, self.p_horas.value(), self.p_estado.currentText(), self.p_desempeno.text().strip()))
            accion= "Registró pasantía"
        else:
            c.execute("""UPDATE pasantias SET estudiante_id=?, empresa_id=?, horas_acumuladas=?, estado=?,
                         desempeno= ? WHERE id=?""",
                      (est_id, emp_id, self.p_horas.value(), self.p_estado.currentText(),
                       self.p_desempeno.text().strip(), self.id_edicion_pasantia))
            accion= "Editó pasantía"
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", accion, self.main_window.usuario_actual, str(est_id))
        self._destello(self.tarjeta_form_pasantia, "#22C55E")
        self._limpiar_pasantia()
        self._cargar_pasantias()
        self._cargar_barra_pasantias()
        self._cargar_resumen_cabecera()

    def _eliminar_pasantia(self):

        fila= self.tabla_pasantias.currentRow()
        if fila < 0:
            return
        id_p= int(self.tabla_pasantias.item(fila, 1).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar este registro de pasantía?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM pasantias WHERE id=?", (id_p,))
        conn.commit()
        conn.close()
        registrar_auditoria("Politécnico", "Eliminó pasantía", self.main_window.usuario_actual, str(id_p))
        self._destello(self.tarjeta_tabla_pasantias, "#EF4444")
        self._cargar_pasantias()
        self._cargar_barra_pasantias()
        self._cargar_resumen_cabecera()

    def _filtro_pasantias_cambio(self):

        self.paginacion_pasantias.reiniciar()
        self._cargar_pasantias()

    def _cargar_pasantias(self):

        texto= _normalizar(self.in_buscar_pasantias.text().strip()) if hasattr(self, "in_buscar_pasantias") else ""
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT pasantias.*, (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as est_nombre,
                     empresas_pasantia.nombre as emp_nombre,
                     estudiantes.especialidad_id as especialidad_id_est,
                     estudiantes.carrera_id as carrera_id_est,
                     estudiantes.numero_lista as numero_lista_est,
                     secciones.id as seccion_id_est, secciones.grado_id as grado_id_est
                     FROM pasantias
                     LEFT JOIN estudiantes ON pasantias.estudiante_id = estudiantes.id
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN empresas_pasantia ON pasantias.empresa_id = empresas_pasantia.id
                     ORDER BY pasantias.id DESC""")
        filas= c.fetchall()
        conn.close()
        if self._filtro_pasantias_estado:
            filas= [fila for fila in filas if fila["estado"] == self._filtro_pasantias_estado]
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                    f"{fila['est_nombre'] or ''} {fila['emp_nombre'] or ''} {fila['estado'] or ''}")]

        #Filtros de la ventana "☰ Filtros" (Área Técnica/Carrera/Curso/ Sección del estudiante de la pasantía) — mismo
        #criterio que Banco de Tareas ▸ Entregas: acotan también la tabla ya generada, no solo el combo "Estudiante"
        #del formulario de arriba.
        especialidad_id_f= (self.p_filtro_especialidad.currentData()
                              if hasattr(self, "p_filtro_especialidad") and self._es_politecnico() else None)
        carrera_id_f= (self.p_filtro_carrera.currentData()
                        if hasattr(self, "p_filtro_carrera") and self._es_universidad() else None)
        curso_id_f= self.p_filtro_curso.currentData() if hasattr(self, "p_filtro_curso") else None
        seccion_id_f= self.p_filtro_seccion.currentData() if hasattr(self, "p_filtro_seccion") else None
        if especialidad_id_f is not None:
            filas= [fila for fila in filas if fila["especialidad_id_est"] == especialidad_id_f]
        if carrera_id_f is not None:
            filas= [fila for fila in filas if fila["carrera_id_est"] == carrera_id_f]
        if seccion_id_f is not None:
            filas= [fila for fila in filas if fila["seccion_id_est"] == seccion_id_f]
        elif curso_id_f is not None:
            filas= [fila for fila in filas if fila["grado_id_est"] == curso_id_f]

        #Con una sección concreta seleccionada (y, si la institución lo exige, también Área Técnica/Carrera concretas
        #-ver bd.mostrar_columna_numero_lista-), se reordena por Número de Lista; en cualquier otro caso se deja el
        #orden por id/fecha de registro de siempre, porque mezclar numero_lista de varias secciones/áreas
        #técnicas/carreras no tendría un orden con sentido.
        mostrar_columna_numero= mostrar_columna_numero_lista(
            self.main_window, seccion_id_f, especialidad_id_f, carrera_id_f)
        if mostrar_columna_numero:
            #f: fila de la pasantía; las que no tienen número de lista van al final
            filas= sorted(filas, key=lambda f: (
                f["numero_lista_est"] is None, f["numero_lista_est"] or 0))
        self.tabla_pasantias.setColumnHidden(0, not mostrar_columna_numero)

        self.paginacion_pasantias.establecer_total(len(filas))
        inicio, fin= self.paginacion_pasantias.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_pasantias):
            self.tabla_pasantias.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                if mostrar_columna_numero:
                    numero_lista= f["numero_lista_est"]
                    item_numero= QTableWidgetItem()
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                    item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla_pasantias.setItem(i, 0, item_numero)
                self.tabla_pasantias.setItem(i, 1, QTableWidgetItem(str(f["id"])))
                self.tabla_pasantias.setItem(i, 2, QTableWidgetItem(f["est_nombre"] or ""))
                self.tabla_pasantias.setItem(i, 3, QTableWidgetItem(f["emp_nombre"] or ""))
                self.tabla_pasantias.setItem(i, 4, QTableWidgetItem(_formatear_horas(f["horas_acumuladas"])))
                self.tabla_pasantias.setItem(i, 5, QTableWidgetItem(f["estado"] or ""))
            ajustar_anchos_columnas(self.tabla_pasantias)

    #---------------- RESUMEN / TEMA ----------------
    def _cargar_resumen_cabecera(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT COUNT(*) as n FROM especialidades")
        total_especialidades= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM empresas_pasantia")
        total_empresas= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM pasantias WHERE estado='En curso'")
        total_pasantias_curso= c.fetchone()["n"]
        conn.close()
        if not hasattr(self, "chip_especialidades"):
            return
        #Iconos dibujados con QPainter (mismos dibujos que ya usa el resto de la app), insertados como <img> inline en
        #vez del emoji real para no depender de una fuente de emojis del sistema.
        self._animar_valor_chip(self.chip_especialidades, "_valor_chip_especialidades", total_especialidades,
                                 #v: cantidad actual del chip animado; el texto pasa a plural si no es 1
                                 lambda v: f"{html_icono_emoji('🎨', 14)} {v} área" + ("s técnicas" if v != 1 else " técnica"))
        self._animar_valor_chip(self.chip_empresas, "_valor_chip_empresas", total_empresas,
                                 #v: cantidad actual del chip animado; el texto pasa a plural si no es 1
                                 lambda v: f"{html_icono_emoji('🏢', 14)} {v} empresa" + ("s" if v != 1 else "") + " aliada" + ("s" if v != 1 else ""))
        self._animar_valor_chip(self.chip_pasantias, "_valor_chip_pasantias", total_pasantias_curso,
                                 #v: cantidad actual del chip animado; el texto pasa a plural si no es 1
                                 lambda v: f"{html_icono_emoji('🎓', 14)} {v} pasantía" + ("s" if v != 1 else "") + " en curso")

    #Refresca combos e indicadores (donut/barras/chips) y la pestaña
    #visible; el resto de pestañas se cargan solas la primera vez que el
    #usuario las visita (ver _cambio_pestana), así entrar al módulo se
    #siente instantáneo.
    def refrescar(self):

        self._cargar_combos_talleres()
        self._cargar_combos_pasantias()
        self._cargar_combos_modulos_tecnicos()
        self._cargar_combos_asignaciones_tecnicas()
        self._cargar_resumen_cabecera()
        self._pestanas_cargadas= set()
        self._cambio_pestana(self.tabs.currentIndex())

    #Sincroniza los colores del módulo (cabecera, tarjetas, anillo,
    #barras y buscadores) con el tema/modo claro-oscuro actual de la app.
    def actualizar_tema(self):

        colores= _colores_tema_politecnico(self.main_window)
        bg_panel= colores["bg_panel"]
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        borde= colores["bg_btn"]
        txt_prim= colores["txt_prim"]
        txt_sec= colores["txt_sec"]
        accent= colores["accent"]
        accent_hv= colores["accent_hv"]
        modo_oscuro= getattr(self.main_window, "modo_oscuro", False)

        #Politécnico y Calificaciones Técnicas son módulos hermanos del área técnica: deben compartir el mismo "skin"
        #de cristal entre ellos (fondos translúcidos con el color de acento, tabla y cabecera de pestañas a juego),
        #aunque ese vidriado sea distinto al de los módulos generales (Materias, Estudiantes, etc.). El estilo de acá
        #está calcado, valor por valor, del actualizar_tema() de CalificacionesTecnicas -ver
        #TarjetaFormularioCT/TarjetaCabeceraCT ahí- para que ambos luzcan idénticos. Ojo: CT tampoco toca
        #QLineEdit/QComboBox/QSpinBox ni QTableWidget::item, así que acá tampoco se tocan -esos sí deben seguir
        #heredando el QSS global de main.py, igual que en CT.
        estilo_tarjeta_cristal= f"""
            QFrame#TarjetaSeccion {{
                background-color: {_hex_a_rgba(accent, 0.05)};
                border: 1px solid {_hex_a_rgba(txt_sec, 0.20)};
                border-radius: 14px;
            }}
        """
        for tarjeta in self.findChildren(TarjetaSeccion):
            tarjeta.aplicar_paleta(bg_panel, borde, txt_prim, txt_sec, accent, modo_oscuro)
            tarjeta.setStyleSheet(estilo_tarjeta_cristal)
        for icono in getattr(self, "_iconos_busqueda", []):
            icono.establecer_color(txt_sec)
        for anillo in self.findChildren(AnilloDonut):
            anillo.poner_colores(txt_prim, txt_sec, borde)
        for barra in self.findChildren(BarraSegmentadaPill):
            barra.poner_colores(borde, borde)

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QFrame#CabeceraPolitecnico {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_hex_a_rgba(accent, 0.20 if modo_oscuro else 0.10)},
                    stop:1 {_hex_a_rgba(accent, 0.03)});
                border: 1px solid {_hex_a_rgba(accent, 0.30)};
                border-radius: 16px;
            }}
            QLabel#IconoCabeceraPolitecnico {{
                background-color: {_hex_a_rgba(accent, 0.22)};
                border-radius: 23px;
                font-size: 22px;
                color: {accent};
            }}
            QLabel#TituloCabeceraPolitecnico {{
                font-size: 18px;
                font-weight: 800;
                color: {txt_prim};
                background: transparent;
            }}
            QLabel#SubtituloCabeceraPolitecnico {{
                font-size: 12px;
                color: {txt_sec};
                background: transparent;
            }}
            QLabel#ChipResumenPolitecnico {{
                background-color: {_hex_a_rgba(accent, 0.16)};
                color: {accent};
                border: 1px solid {_hex_a_rgba(accent, 0.30)};
                border-radius: 14px;
                padding: 7px 14px;
                font-weight: 700;
                font-size: 12px;
            }}
            QFrame#MarcoBusquedaPolitecnico {{
                background-color: {_hex_a_rgba(txt_sec, 0.10)};
                border-radius: 16px;
            }}
            QLineEdit#CampoBusquedaPolitecnico {{
                border: none;
                background: transparent;
                padding: 8px 0;
                color: {txt_prim};
            }}
            QTableWidget {{
                background-color: {bg_panel};
                alternate-background-color: {_hex_a_rgba(accent, 0.06)};
                gridline-color: {_hex_a_rgba(txt_sec, 0.15)};
                color: {txt_prim};
                border: 1px solid {borde};
                border-radius: 10px;
            }}
            QHeaderView::section {{
                background-color: {_hex_a_rgba(accent, 0.18)};
                color: {txt_prim};
                padding: 6px;
                border: none;
                font-weight: 600;
            }}
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background: {_hex_a_rgba(txt_sec, 0.10)};
                color: {txt_sec};
                padding: 9px 20px;
                margin-right: 8px;
                margin-bottom: 4px;
                border-radius: 12px;
                border: 1px solid {_hex_a_rgba(txt_sec, 0.16)};
                font-weight: 600;
                font-size: 13px;
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {accent_hv});
                color: white;
                border: 1px solid transparent;
                font-weight: 700;
            }}
            QTabBar::tab:!selected:hover {{
                background-color: {_hex_a_rgba(accent, 0.20)};
                color: {txt_prim};
                border: 1px solid {_hex_a_rgba(accent, 0.35)};
            }}
        """ + estilo_flechas_navegacion_tabs(accent, accent_hv, bg_panel, borde, _hex_a_rgba(accent, 0.16)))

        estilo_dialogo_filtros= f"""
            QDialog#DialogoFiltrosPoli {{
                background-color: {bg_panel};
            }}
            /* Repite aquí el mismo QToolTip que usa la ventana principal:
               este diálogo es una ventana de nivel superior aparte, y su
               propio setStyleSheet() reemplaza -para todo lo que esté
               dentro- cualquier regla heredada, incluido el QToolTip global.
               Sin esto, los tooltips de los combos aquí adentro caían al
               estilo nativo de Qt (gris claro/texto negro), inconsistente
               con el resto de AcaDeXI. */
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QLabel#IconoEncabezadoFiltrosPoli {{
                background-color: {accent};
                color: white;
                border-radius: 15px;
                min-width: 30px; max-width: 30px;
                min-height: 30px; max-height: 30px;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }}
            QLabel#TituloEncabezadoFiltrosPoli {{
                font-size: 16px;
                font-weight: 800;
                color: {txt_prim};
                background: transparent;
            }}
            QLabel#SubtituloFiltrosPoli {{
                font-size: 11.5px;
                color: {txt_sec};
                background: transparent;
            }}
            QFrame#SeparadorFiltrosPoli {{
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
        """
        for dialogo in self.findChildren(QDialog, "DialogoFiltrosPoli"):
            dialogo.setStyleSheet(estilo_dialogo_filtros)
        for lbl_resumen in (getattr(self, "lbl_resumen_filtros_pasantias", None),):
            if lbl_resumen is not None:
                lbl_resumen.setStyleSheet(f"color: {txt_sec}; font-size: 11.5px; background: transparent;")