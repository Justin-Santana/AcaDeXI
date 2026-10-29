from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
QGridLayout, QSpinBox, QScrollArea, QFrame, QDialog, QMenu, QSizePolicy)
from PySide6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPainterPath, QBrush
from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso, preseleccionar_curso_y_seccion,
                                               poblar_combo_curso_opcional,
    poblar_combo_nivel_educativo, secciones_del_nivel_educativo)
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.nucleo.permisos import puede_editar
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, agregar_boton_pantalla_completa)
from src.nucleo.formato_hora import formatear_hora
from src.sincronizacion.sync_docente import exportar_paquete_docente
from src.interfaz.dashboard import TarjetaIndicador, AnilloProgreso
from src.interfaz.configuracion import (_fundido_entrada, _hex_a_rgba, TabWidgetNavegable, _normalizar, IconoLupa,
    NIVELES_ACADEMICOS, CICLOS_SECUNDARIA, niveles_academicos_habilitados,
    puede_tener_componente_tecnico, conectar_tooltip_seleccion)
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from src.modulos.calendario import PanelDesplegable
from PySide6.QtCore import QSize as _QSize_emoji
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro, EMOJI_SECCIONES_GRUPOS)

DIAS= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
TURNOS= ["Mañana", "Tarde", "Noche", "Tanda Extendida"]

#Modelo de evaluación de una materia: la mayoría usa el currículo académico normal por Competencias Específicas
#('Competencias'); en un Politécnico, un módulo técnico puede marcarse como 'Técnica (RA)' para evaluarse por
#Resultados de Aprendizaje ponderados en vez de por competencias (ver calificaciones_tecnicas.py). El combo
#solo se muestra si la institución es de tipo Politécnico — en cualquier otro tipo, toda materia queda en
#'Competencias' sin que el usuario tenga que pensar en esto.
MODELO_EVALUACION_COMPETENCIAS= "Competencias"
MODELO_EVALUACION_TECNICA= "Técnica (RA)"
OPCIONES_MODELO_EVALUACION= [
    ("Currículo académico (Competencias Específicas)", MODELO_EVALUACION_COMPETENCIAS),
    ("Módulo Técnico (Resultados de Aprendizaje - RA)", MODELO_EVALUACION_TECNICA),
]

_COLORES_TURNO= {"Mañana": "#F59E0B", "Tarde": "#3B82F6", "Noche": "#6366F1", "Tanda Extendida": "#10B981"}
_COLORES_TIPO_ASIGNACION= {"Auxiliar": "#3B82F6", "Suplente": "#F59E0B",
                             "Co-titular": "#8B5CF6", "Practicante": "#14B8A6"}


#Da color + negrita a una celda de tabla para que ciertos valores
#(estado, turno, tipo de asignación) se lean de un vistazo. No agrega
#widgets extra ni efectos gráficos: es solo texto+color sobre el
#QTableWidgetItem ya existente, así que el costo es prácticamente nulo
#incluso con tablas grandes.
def _colorear_texto(item, color_hex):

    item.setForeground(QColor(color_hex))
    fuente= item.font()
    fuente.setBold(True)
    item.setFont(fuente)


def _minutos(hora_txt):

    partes= hora_txt.strip().split(":")
    if len(partes) != 2:
        raise ValueError("Formato de hora inválido")
    h, m= int(partes[0]), int(partes[1])
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Hora fuera de rango")
    return h * 60 + m

def _se_solapan(inicio1, fin1, inicio2, fin2):

    return inicio1 < fin2 and inicio2 < fin1


#Barras animadas y originales con la cantidad de clases programadas por
#día de la semana: de un vistazo se ve qué días están más cargados de
#horario. Solo se repinta cuando cambian los datos o el tamaño (no hay
#temporizador continuo), así que el costo real es una animación de
#entrada de ~700ms una sola vez por refresco — insignificante incluso
#con muchos horarios, porque lo que se agrega son 6 barras, no una por
#horario.
class GraficoOcupacionSemanal(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._datos= []
        self._progreso= 0.0
        self._color_barra= QColor("#3B82F6")
        self._color_texto= QColor("#64748B")
        self._color_texto_prim= QColor("#0F172A")
        self.setMinimumHeight(130)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_tic)

    def _al_tic(self, valor):

        self._progreso= valor
        self.update()

    #datos: lista de tuplas (etiqueta_dia, cantidad).
    def poner_datos(self, datos, color_acento=None):

        self._datos= datos
        if color_acento:
            self._color_barra= QColor(color_acento)
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
        if not self._datos or not any(c for _, c in self._datos):
            painter.setPen(self._color_texto)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                              "Aún no hay horarios asignados a ninguna sección.")
            return

        maximo= max((cant for _, cant in self._datos), default=0) or 1
        #margen_sup reserva espacio fijo para el numerito encima de la barra más alta, para que nunca quede cortado
        #contra el borde del widget (antes la barra con más clases podía llegar casi hasta arriba y el texto se
        #dibujaba parcialmente fuera del área visible).
        margen_inf, margen_sup= 22, 24
        alto_disponible= self.height() - margen_inf - margen_sup
        n= len(self._datos)
        espacio= 12
        ancho_barra= max(18, (self.width() - espacio * (n + 1)) / n)

        x= espacio
        for dia, cantidad in self._datos:
            proporcion= cantidad / maximo
            h= alto_disponible * proporcion * self._progreso
            pos_y= margen_sup + (alto_disponible - h)

            gradiente= QLinearGradient(0, pos_y, 0, pos_y + max(h, 2))
            gradiente.setColorAt(0, self._color_barra.lighter(130))
            gradiente.setColorAt(1, self._color_barra)
            path= QPainterPath()
            radio= min(7, ancho_barra / 2)
            path.addRoundedRect(QRectF(x, pos_y, ancho_barra, max(h, 3)), radio, radio)
            painter.fillPath(path, QBrush(gradiente))

            if cantidad > 0 and self._progreso > 0.85:
                painter.setPen(self._color_texto_prim)
                f_valor= painter.font()
                f_valor.setPointSize(8)
                f_valor.setBold(True)
                painter.setFont(f_valor)
                y_texto= max(2, pos_y - 16)
                painter.drawText(QRectF(x - 4, y_texto, ancho_barra + 8, 14),
                                  Qt.AlignmentFlag.AlignCenter, str(cantidad))

            painter.setPen(self._color_texto)
            f_label= painter.font()
            f_label.setPointSize(8)
            f_label.setBold(False)
            painter.setFont(f_label)
            painter.drawText(QRectF(x - 4, self.height() - margen_inf + 3, ancho_barra + 8, margen_inf - 3),
                              Qt.AlignmentFlag.AlignCenter, dia[:3].upper())
            x += ancho_barra + espacio


class ModuloMaterias(QWidget):

    def __init__(self, main_window):

        #Sin padre de Qt todavía; ver nota equivalente en calificaciones.py (evita la "ventana fantasma" al cargar el
        #módulo perezosamente).
        super().__init__()
        self.main_window= main_window
        self.id_edicion_materia= None
        self.id_edicion_seccion= None
        self.id_edicion_aula= None
        self.id_edicion_horario= None
        self._construir_ui()
        self.refrescar()
        self.actualizar_tema()  #por si el módulo se cargó de forma perezosa, ya con el tema definido
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        #Módulo exclusivo de roles gerenciales (Materias, Secciones y Aulas institucionales): un Profesor no llega a
        #esta pantalla, así que no hace falta ningún gateo de Modo Docente aquí.
        self._titulo_modulo_atajos= "Materias"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar materia", self._guardar_materia)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar_materia)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar materia seleccionada",
                         self._cargar_materia_seleccionada)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar materia", self._eliminar_materia)
        registrar_atajo(self, self.main_window, "F5", "Actualizar lista de materias", self._cargar_materias)

    #True si ya existe otra materia ACADÉMICA (no técnica) con el mismo
    #nombre, comparado sin distinguir mayúsculas/acentos. Los módulos
    #técnicos (área técnica + modelo RA) viven en el mismo `materias` pero
    #se comparan aparte, en politecnico.py, porque son un catálogo distinto
    #de cara al usuario.
    def _nombre_duplicado_materia(self, nombre, id_excluir=None):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre FROM materias
                     WHERE especialidad_id IS NULL
                       AND (modelo_evaluacion IS NULL OR modelo_evaluacion != ?)""",
                  (MODELO_EVALUACION_TECNICA,))
        filas= c.fetchall()
        conn.close()
        objetivo= _normalizar(nombre or "")
        for fila in filas:
            if id_excluir is not None and fila["id"] == id_excluir:
                continue
            if _normalizar(fila["nombre"] or "") == objetivo:
                return True
        return False

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
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Materias")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Materias, Cursos y Horarios")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Un vistazo rápido a tu oferta académica, antes de entrar al detalle en cada pestaña.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        disposicion.addWidget(self.frame_cabecera)

        disposicion.addWidget(self._construir_resumen())

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        #Ver nota en configuracion.py: quita la línea base nativa que Qt dibuja bajo la barra de pestañas y que el
        #stylesheet no puede eliminar.
        self.tabs.tabBar().setDrawBase(False)
        disposicion.addWidget(self.tabs)
        self.tabs.addTab(self._tab_materias(), "Materias")
        self.tabs.addTab(self._tab_secciones(), icono_emoji(EMOJI_SECCIONES_GRUPOS), "Cursos y Secciones")
        self.tabs.addTab(self._tab_aulas(), "Aulas y Laboratorios")
        self.tabs.addTab(self._tab_horarios(), "Horarios")
        self.tabs.addTab(self._tab_asignaciones(), "Co-Docentes")
        #Transición suave (fundido) al cambiar de pestaña, en vez de un salto brusco.
        self.tabs.currentChanged.connect(lambda i: _fundido_entrada(self.tabs.widget(i), 220))

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

    #Fila de indicadores KPI (reutiliza la tarjeta animada del Dashboard) más
    #un anillo de progreso con el % de materias activas, para ver de un vistazo
    #el tamaño y la salud de la oferta académica antes de entrar al detalle.
    def _construir_resumen(self):

        fila= QWidget()
        disposicion= QHBoxLayout(fila)
        disposicion.setContentsMargins(0, 0, 0, 0)
        disposicion.setSpacing(14)
        self.tarjeta_kpi_materias= TarjetaIndicador("📘", "Materias registradas", "#8B5CF6")
        self.tarjeta_kpi_activas= TarjetaIndicador("✅", "Materias activas", "#10B981")
        self.tarjeta_kpi_secciones= TarjetaIndicador(EMOJI_SECCIONES_GRUPOS, "Secciones", "#F59E0B")
        self.tarjeta_kpi_horarios= TarjetaIndicador("📅", "Clases programadas", "#3B82F6")
        self._tarjetas_kpi= [self.tarjeta_kpi_materias, self.tarjeta_kpi_activas,
                               self.tarjeta_kpi_secciones, self.tarjeta_kpi_horarios]
        for tarjeta in self._tarjetas_kpi:
            disposicion.addWidget(tarjeta, 1)

        contenedor_anillo= QFrame()
        contenedor_anillo.setObjectName("TarjetaFormulario")
        contenedor_anillo.setStyleSheet("""
            QFrame#TarjetaFormulario {
                background-color: rgba(127, 127, 127, 0.07);
                border: 1px solid rgba(127, 127, 127, 0.16);
                border-radius: 14px;
            }
        """)
        lay_anillo= QVBoxLayout(contenedor_anillo)
        lay_anillo.setContentsMargins(14, 10, 14, 10)
        lay_anillo.setSpacing(4)
        self.anillo_activas= AnilloProgreso()
        self.anillo_activas.setFixedSize(88, 88)
        lay_anillo.addWidget(self.anillo_activas, 0, Qt.AlignmentFlag.AlignCenter)
        lbl_anillo= QLabel("% Activas")
        lbl_anillo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_anillo.setObjectName("DescModulo")
        lay_anillo.addWidget(lbl_anillo)
        disposicion.addWidget(contenedor_anillo)

        return fila

    #Envuelve un formulario en una tarjeta con look moderno (fondo translúcido
    #neutro, que se adapta bien tanto a modo claro como oscuro sin necesitar
    #recalcular colores por tema).
    #
    #Rendimiento: a propósito NO lleva QGraphicsDropShadowEffect. Un efecto
    #gráfico permanente obliga a Qt a recomponer la tarjeta en un buffer aparte
    #en cada repintado (incluido cada frame del colapso animado del sidebar);
    #el look de "tarjeta" ya se logra con el fondo translúcido + borde
    #redondeado, que se pintan de forma nativa y son prácticamente gratis.
    def _tarjeta_formulario(self, titulo_seccion=None):

        frame= QFrame()
        frame.setObjectName("TarjetaFormulario")
        frame.setStyleSheet("""
            QFrame#TarjetaFormulario {
                background-color: rgba(127, 127, 127, 0.07);
                border: 1px solid rgba(127, 127, 127, 0.16);
                border-radius: 14px;
            }
        """)
        contenedor= QVBoxLayout(frame)
        contenedor.setContentsMargins(18, 16, 18, 16)
        contenedor.setSpacing(10)
        if titulo_seccion:
            lbl= QLabel(titulo_seccion)
            fuente= lbl.font()
            fuente.setBold(True)
            fuente.setPointSize(11)
            lbl.setFont(fuente)
            lbl.setStyleSheet("background: transparent;")
            contenedor.addWidget(lbl)
        grid= QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        contenedor.addLayout(grid)
        return frame, grid

    #Crea una barra de búsqueda con debounce, mismo diseño (lupa dibujada +
    #marco redondeado) que se usa en Configuración/Estudiantes, para poder
    #filtrar tablas largas sin tener que pasar de página en página.
    #Devuelve (frame, line_edit).
    def _barra_busqueda(self, placeholder, al_cambiar):

        frame= QFrame()
        frame.setObjectName("TarjetaFiltros")
        #Fixed en el eje vertical: esta barra tiene una altura "de diseño" (la del QLineEdit + su padding) y nunca debe
        #estirarse aunque el layout que la contiene tenga espacio vertical de sobra -eso fue justo lo que pasaba antes
        #cuando el panel "Añadir…" de arriba estaba colapsado: al no haber ningún addStretch() al final de `lr` (ver
        #_tab_aulas y hermanas), Qt repartía el sobrante entre los widgets del layout, incluida esta barra, dejándola
        #con una forma ovalada/estirada rarísima en vez de su altura normal.
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        fila= QHBoxLayout(frame)
        fila.setContentsMargins(14, 8, 14, 8)
        fila.setSpacing(10)

        marco= QFrame()
        marco.setStyleSheet("QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay= QHBoxLayout(marco)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(6)
        lay.addWidget(IconoLupa())
        in_campo= QLineEdit()
        limitar_campo_texto(in_campo, 300)
        in_campo.setPlaceholderText(placeholder)
        in_campo.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay.addWidget(in_campo, 1)
        fila.addWidget(marco, 1)

        temporizador= QTimer(self)
        temporizador.setSingleShot(True)
        temporizador.setInterval(150)
        temporizador.timeout.connect(al_cambiar)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador de búsqueda
        in_campo.textChanged.connect(lambda _t: temporizador.start())
        return frame, in_campo

    #Agrega el botón '☰ Filtros' a la derecha de una barra de búsqueda ya
    #creada con `_barra_busqueda` (mismo diseño/ubicación que en Estudiantes,
    #Horario, Calendario y Banco de Tareas). Devuelve el botón.
    def _agregar_boton_filtros(self, frame_busqueda, callback_abrir):

        btn_filtros= QPushButton("Filtros")
        icono_boton_filtro(btn_filtros)
        btn_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_filtros.setObjectName("BtnAccionNeutro")
        btn_filtros.clicked.connect(callback_abrir)
        frame_busqueda.layout().addWidget(btn_filtros)
        return btn_filtros

    #Ventanita NO modal con los filtros de una pestaña -mismo patrón que
    #usan Estudiantes/Horario/Calendario/Banco de Tareas (DialogoFiltros)-:
    #se puede dejar abierta mientras se ajustan los combos, y la tabla de
    #atrás se sigue actualizando en vivo.
    #
    #`campos`: lista de tuplas (etiqueta_o_None, widget). Si la etiqueta es
    #None, se asume que el propio widget ya trae su primer ítem tipo
    #"Todos los..." y no hace falta QLabel aparte.
    #Devuelve el QDialog ya armado (todavía sin mostrar).
    def _construir_dialogo_filtros(self, titulo, campos):

        dialogo= QDialog(self)
        dialogo.setObjectName("DialogoFiltros")
        dialogo.setWindowTitle(titulo)
        aplicar_icono_ventana(dialogo, ICONO_FILTRO)
        dialogo.setModal(False)
        dialogo.setMinimumWidth(320)
        lay_dialogo= QVBoxLayout(dialogo)
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

        lbl_subtitulo= QLabel("Combina los filtros que necesites; la tabla se actualiza al instante.")
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
        for fila_idx, (etiqueta, widget) in enumerate(campos):
            if etiqueta:
                grid.addWidget(QLabel(etiqueta), fila_idx, 0)
                grid.addWidget(widget, fila_idx, 1)
            else:
                grid.addWidget(widget, fila_idx, 0, 1, 2)
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        btn_limpiar= QPushButton("Limpiar filtros")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        btn_limpiar.clicked.connect(lambda: self._limpiar_combos_filtro([w for _, w in campos]))
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(dialogo.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)
        return dialogo

    #Regresa a 'Todos'/índice 0 cada combo de una ventana de filtros.
    #Los widgets que no sean QComboBox (p. ej. un QLabel colado como fila
    #completa) se ignoran sin error.
    def _limpiar_combos_filtro(self, widgets):

        for widget in widgets:
            if isinstance(widget, QComboBox) and widget.count():
                widget.blockSignals(True)
                widget.setCurrentIndex(0)
                widget.blockSignals(False)
        #Si algún combo tenía señales bloqueadas al limpiar, dispara un solo refresco al final en vez de uno por combo.
        if widgets:
            primero= widgets[0]
            if isinstance(primero, QComboBox):
                primero.currentIndexChanged.emit(primero.currentIndex())

    def _abrir_dialogo(self, dialogo):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and dialogo.parent() is not _fc:
            dialogo.setParent(_fc)
        dialogo.show()
        dialogo.raise_()
        dialogo.activateWindow()

    #Envuelve uno o más widgets (típicamente el formulario de 'Añadir'
    #de una pestaña, y su cuadrito de filtro técnico si tiene) en
    #un PanelDesplegable colapsable -el mismo 'cosito de ocultar' que usa
    #Politécnico en todas sus pestañas- para que el formulario no le gane
    #protagonismo visual a la tabla de abajo, pero siga a un clic de
    #distancia para quien lo necesite. Empieza cerrado por defecto.
    def _envolver_en_panel(self, layout_padre, titulo, *widgets):

        panel= PanelDesplegable(titulo)
        for widget in widgets:
            panel.cuerpo_layout().addWidget(widget)
        layout_padre.addWidget(panel)
        return panel

    #Tarjeta que agrupa tabla + paginación + botones de acción de una pestaña,
    #para que se lea como un panel propio en vez de elementos sueltos. Sin sombra
    #permanente por la misma razón de rendimiento que `_tarjeta_formulario`.
    def _tarjeta_resultados(self):

        frame= QFrame()
        frame.setObjectName("TarjetaFormulario")
        frame.setStyleSheet("""
            QFrame#TarjetaFormulario {
                background-color: rgba(127, 127, 127, 0.05);
                border: 1px solid rgba(127, 127, 127, 0.14);
                border-radius: 14px;
            }
        """)
        contenedor= QVBoxLayout(frame)
        contenedor.setContentsMargins(16, 14, 16, 14)
        contenedor.setSpacing(10)
        return frame, contenedor

    def actualizar_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        #Refrescar colores de los encabezados colapsables (PanelDesplegable)
        for panel in self.findChildren(PanelDesplegable):
            panel.actualizar_color_tema()
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
        idx= 1 if getattr(mw, "modo_oscuro", True) else 0

        bg_panel= paleta["display_bg"][idx]
        bg_borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        modo_oscuro= getattr(mw, "modo_oscuro", True)
        accent= paleta["btn_op_bg"][idx]

        for tarjeta in getattr(self, "_tarjetas_kpi", []):
            tarjeta.aplicar_paleta(bg_panel, bg_borde, txt_prim, txt_sec, modo_oscuro)
        if hasattr(self, "anillo_activas"):
            self.anillo_activas.poner_colores(bg_borde, txt_prim)
        if hasattr(self, "grafico_ocupacion"):
            self.grafico_ocupacion.poner_colores(txt_sec, txt_prim)

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)

        #Ventanas de filtro (una por pestaña: Materias, Secciones, Aulas, Horarios, Co-Docentes). Mismo diseño que el
        #DialogoFiltros de Estudiantes/Horario/Calendario/Banco de Tareas -círculo de acento con el ícono ☰, título
        #grande y separador sutil-, para que se vea igual en todo el sistema, esté donde esté.
        estilo_dialogo_filtros= f"""
            QDialog#DialogoFiltros {{
                background-color: {bg_panel};
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
            }}
            QLabel#SubtituloFiltros {{
                font-size: 11px;
                color: {txt_sec};
            }}
            QFrame#SeparadorFiltros {{
                background-color: {bg_borde};
                max-height: 1px;
                border: none;
            }}
        """
        for nombre_dialogo in ("dialogo_filtros_materias", "dialogo_filtros_secciones",
                                "dialogo_filtros_aulas", "dialogo_filtros_horarios",
                                "dialogo_filtros_asignaciones"):
            dialogo= getattr(self, nombre_dialogo, None)
            if dialogo is not None:
                dialogo.setStyleSheet(estilo_dialogo_filtros)

        accent_hover_cab= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent
        if hasattr(self, "frame_cabecera"):
            self.frame_cabecera.setStyleSheet(f"""
                QFrame#TarjetaCabecera {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {accent}, stop:1 {accent_hover_cab});
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

        #El selector de pestañas se estiliza aparte (solo self.tabs, no todo el módulo), igual que en configuracion.py.
        #Mismo diseño "píldora" con degradado.
        accent_suave= _hex_a_rgba(accent, 0.16 if modo_oscuro else 0.10)
        accent_hover= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent
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
                background: {bg_borde};
                color: {txt_sec};
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
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

    def _actualizar_kpis(self):

        conn= obtener_conexion()
        c= conn.cursor()
        #Una sola consulta con subconsultas en vez de 4 idas y vueltas separadas.
        c.execute("""SELECT
                        (SELECT COUNT(*) FROM materias WHERE especialidad_id IS NULL
                            AND (modelo_evaluacion IS NULL OR modelo_evaluacion != 'Técnica (RA)')) as total_materias,
                        (SELECT COUNT(*) FROM materias WHERE estado='Activa' AND especialidad_id IS NULL
                            AND (modelo_evaluacion IS NULL OR modelo_evaluacion != 'Técnica (RA)')) as activas,
                        (SELECT COUNT(*) FROM secciones) as total_secciones,
                        (SELECT COUNT(*) FROM horarios) as total_horarios""")
        fila= c.fetchone()
        conn.close()
        total_materias, activas= fila["total_materias"], fila["activas"]
        self.tarjeta_kpi_materias.actualizar(total_materias)
        self.tarjeta_kpi_activas.actualizar(activas)
        self.tarjeta_kpi_secciones.actualizar(fila["total_secciones"])
        self.tarjeta_kpi_horarios.actualizar(fila["total_horarios"])
        porcentaje_activas= (activas / total_materias * 100) if total_materias else 0
        self.anillo_activas.poner_valor(porcentaje_activas, "#10B981")

    def _tab_materias(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)
        frame_form, form= self._tarjeta_formulario("Datos de la Materia")
        self.lbl_nota_tecnicos= QLabel(
            "ℹ Esta pestaña es solo para materias académicas normales. Los módulos técnicos"
            "(con área técnica y evaluación por Resultados de Aprendizaje) se crean y gestionan "
            "desde el módulo Politécnico.")
        self.lbl_nota_tecnicos.setWordWrap(True)
        self.lbl_nota_tecnicos.setObjectName("DescModulo")
        disposicion.addWidget(self.lbl_nota_tecnicos)
        self.m_codigo= QLineEdit()
        limitar_campo_texto(self.m_codigo, 300)
        self.m_codigo.setPlaceholderText("Código (autogenerado)")
        self.m_codigo.setReadOnly(True)
        self.m_codigo.setToolTip(
            "Autogenerado. Clic derecho para escribirlo manualmente o para "
            "volver a autogenerado.")
        self.m_codigo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.m_codigo.customContextMenuRequested.connect(self._menu_contextual_codigo_materia)
        self._codigo_materia_manual= False
        self.m_nombre= QLineEdit()
        limitar_campo_texto(self.m_nombre, 300)
        self.m_nombre.setPlaceholderText("Nombre de la Materia")
        self.m_nombre.textChanged.connect(self._previsualizar_codigo_materia)
        self.m_creditos= QSpinBox()
        self.m_creditos.setRange(0, 20)
        self.m_creditos.setToolTip(
            "Créditos académicos: el 'peso' o valor en horas de estudio que tiene esta materia "
            "dentro del plan de estudios. A más créditos, mayor carga académica representa la "
            "materia (suele influir en el cálculo de promedios ponderados y en la carga horaria "
            "total del estudiante)."
        )
        self.m_profesor= QComboBox()
        conectar_tooltip_seleccion(self.m_profesor,
            "Profesor titular de la materia. 'Sin asignar' = aún no tiene profesor titular")
        self.m_estado= QComboBox()
        self.m_estado.addItems(["Activa", "Inactiva"])
        conectar_tooltip_seleccion(self.m_estado, "Estado de la materia: Activa = disponible para horarios y matrícula")
        self.m_curso= QComboBox()
        conectar_tooltip_seleccion(self.m_curso,
            "Curso/Grado al que se vincula esta materia (OPCIONAL). 'Sin curso específico' = disponible "
            "para cualquier curso.")
        poblar_combo_curso_opcional(self.m_curso)
        form.addWidget(self.m_codigo, 0, 0)
        form.addWidget(self.m_nombre, 0, 1)
        form.addWidget(self.m_creditos, 0, 2)
        form.addWidget(self.m_profesor, 1, 0)
        form.addWidget(self.m_estado, 1, 1)
        form.addWidget(self.m_curso, 2, 0)

        btn_guardar= QPushButton("Guardar Materia")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_materia)
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_materia)
        form.addWidget(btn_limpiar, 3, 1)
        btn_exportar_profesor= QPushButton("Exportar paquete para el profesor seleccionado")
        btn_exportar_profesor.setIcon(icono_emoji("\uE002"))
        btn_exportar_profesor.setIconSize(_QSize_emoji(16, 16))
        btn_exportar_profesor.setObjectName("BtnAccionAjustar")
        btn_exportar_profesor.setToolTip(
            "Genera un paquete de Estudiantes y Cursos (Excel) acotado solo a las materias/secciones/"
            "estudiantes del profesor elegido arriba en 'Profesor', para compartírselo y que lo "
            "importe en su Modo Docente.")
        btn_exportar_profesor.clicked.connect(self._exportar_paquete_profesor_seleccionado)
        form.addWidget(btn_exportar_profesor, 3, 2, 1, 2)
        self._envolver_en_panel(disposicion, "Añadir Materia", frame_form)

        frame_resultados, lr= self._tarjeta_resultados()
        barra_busqueda, self.busq_materias= self._barra_busqueda(
            "Buscar por código, nombre o profesor…", self._filtro_materias_cambio)

        #--- Ventana de filtros (Profesor / Estado) ---
        self.filtro_materias_profesor= QComboBox()
        self.filtro_materias_profesor.addItem("Todos los profesores", None)
        self.filtro_materias_profesor.currentIndexChanged.connect(self._filtro_materias_cambio)
        conectar_tooltip_seleccion(self.filtro_materias_profesor, "Filtrar la lista por profesor titular")
        self.filtro_materias_estado= QComboBox()
        self.filtro_materias_estado.addItem("Todos los estados", None)
        self.filtro_materias_estado.addItem("Activa", "Activa")
        self.filtro_materias_estado.addItem("Inactiva", "Inactiva")
        self.filtro_materias_estado.currentIndexChanged.connect(self._filtro_materias_cambio)
        conectar_tooltip_seleccion(self.filtro_materias_estado, "Filtrar la lista por estado de la materia")
        self.dialogo_filtros_materias= self._construir_dialogo_filtros("Filtros de Materias", [
            ("Profesor:", self.filtro_materias_profesor),
            ("Estado:", self.filtro_materias_estado),
        ])
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._agregar_boton_filtros(barra_busqueda, lambda: self._abrir_dialogo(self.dialogo_filtros_materias))
        lr.addWidget(barra_busqueda)


        self.tabla_materias= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_materias)

        self.tabla_materias.setHorizontalHeaderLabels(
            ["ID", "Código", "Nombre", "Créditos", "Profesor", "Estado"])
        self.tabla_materias.horizontalHeaderItem(3).setToolTip(
            "Créditos académicos: el 'peso' o valor en horas de estudio que tiene la materia "
            "dentro del plan de estudios. A más créditos, mayor carga académica representa."
        )
        self.tabla_materias.setColumnHidden(0, True)
        header= self.tabla_materias.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_materias.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_materias.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_materias.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_materias.setAlternatingRowColors(True)
        self.tabla_materias.setWordWrap(True)
        self.tabla_materias.setMinimumHeight(220)
        self.tabla_materias.verticalHeader().setVisible(False)
        lr.addWidget(self.tabla_materias, 1)

        self.paginacion_materias= ControlPaginacion()
        self.paginacion_materias.cambio.connect(self._cargar_materias)
        lr.addWidget(self.paginacion_materias)

        agregar_boton_pantalla_completa(
            None, [self.tabla_materias, self.paginacion_materias],
            titulo= "Materias", parent=self)

        fila_botones= QHBoxLayout()
        btn_actualizar_mat= QPushButton("Actualizar")
        btn_actualizar_mat.setIcon(icono_emoji("🔄"))
        btn_actualizar_mat.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_mat.setObjectName("BtnAccionNeutro")
        btn_actualizar_mat.clicked.connect(self._cargar_materias)
        fila_botones.addWidget(btn_actualizar_mat)
        btn_editar= QPushButton("Cargar")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_materia_seleccionada)
        fila_botones.addWidget(btn_editar)
        btn_eliminar= QPushButton("Eliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_materia)
        fila_botones.addWidget(btn_eliminar)
        btn_detalle_mat= agregar_boton_detalle(fila_botones, self.tabla_materias, self, titulo="Detalle de la Materia")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_materias.doubleClicked.connect(lambda *_: btn_detalle_mat.click())
        fila_botones.addStretch()
        lr.addLayout(fila_botones)
        lr.addStretch()
        disposicion.addWidget(frame_resultados, 1)
        return contenedor

    def _exportar_paquete_profesor_seleccionado(self):

        profesor_id= self.m_profesor.currentData()
        if profesor_id is None:
            mostrar_mensaje("advertencia", "Sin profesor seleccionado",
                           "Elige un profesor en el campo 'Profesor' (arriba) para exportarle su paquete "
                           "de materias, secciones y estudiantes.", self)
            return
        profesor_nombre= self.m_profesor.currentText().strip()
        exportar_paquete_docente(self.main_window, self, profesor_id=profesor_id, profesor_nombre=profesor_nombre)

    def _previsualizar_codigo_materia(self):

        if self._codigo_materia_manual:
            return
        if self.id_edicion_materia is None:
            self.m_codigo.setText(self._generar_codigo_materia() if self.m_nombre.text().strip() else "")

    #Clic derecho sobre el campo "Código": alterna entre escribirlo a
    #mano y dejarlo autogenerado de nuevo. Si ya está en modo manual
    #-sea porque se pidió con este mismo menú, o porque se cargó una
    #materia existente para editarla (ver _cargar_materia_seleccionada)-,
    #el menú ofrece volver a autogenerado; si no, ofrece pasar a
    #manual.
    def _menu_contextual_codigo_materia(self, pos):

        menu= QMenu(self)
        if self._codigo_materia_manual:
            accion= menu.addAction(icono_emoji("🔄"), "Volver a autogenerado")
        else:
            accion= menu.addAction(icono_emoji("✏"), "Escribir código manualmente")
        if menu.exec(self.m_codigo.mapToGlobal(pos)) == accion:
            if self._codigo_materia_manual:
                self._codigo_materia_manual= False
                self.m_codigo.setReadOnly(True)
                self._previsualizar_codigo_materia()
            else:
                self._codigo_materia_manual= True
                self.m_codigo.setReadOnly(False)
                self.m_codigo.setFocus()
                self.m_codigo.selectAll()

    def _generar_codigo_materia(self):

        base= "".join(w[0] for w in self.m_nombre.text().strip().upper().split()[:3]) or "MAT"
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT codigo FROM materias WHERE codigo LIKE ?", (f"{base}-%",))
        existentes= {fila["codigo"] for fila in c.fetchall()}
        conn.close()
        n= 1
        while f"{base}-{n:03d}" in existentes:
            n += 1
        return f"{base}-{n:03d}"

    def _guardar_materia(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede editar materias.", self)
            return
        nombre= self.m_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        if self._nombre_duplicado_materia(nombre, self.id_edicion_materia):
            mostrar_mensaje("advertencia", "Materia duplicada",
                             f"Ya existe una materia llamada «{nombre}».", self)
            return
        if not self.m_codigo.text().strip():
            self.m_codigo.setText(self._generar_codigo_materia())
        #Esta pestaña solo maneja materias académicas normales: nunca tienen área técnica ni modelo RA. Los módulos
        #técnicos se crean y editan en el módulo Politécnico ("🛠 Módulos Técnicos").
        datos= (self.m_codigo.text().strip(), nombre, self.m_creditos.value(),
                 None, self.m_profesor.currentData(), self.m_estado.currentText(),
                 MODELO_EVALUACION_COMPETENCIAS, self.m_curso.currentData())
        conn= obtener_conexion()
        try:

            c= conn.cursor()
            if self.id_edicion_materia is None:
                c.execute("""INSERT INTO materias (codigo, nombre, creditos, especialidad_id, profesor_id, estado,
                             modelo_evaluacion, grado_id) VALUES (?,?,?,?,?,?,?,?)""", datos)
                accion= "Registró materia"
            else:
                c.execute("""UPDATE materias SET codigo=?, nombre=?, creditos=?, especialidad_id=?, profesor_id=?,
                             estado= ?, modelo_evaluacion=?, grado_id=? WHERE id=?""", datos + (self.id_edicion_materia,))
                accion= "Editó materia"
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "Error de base de datos", f"No se pudo guardar la materia:\n{error}", self)
            return
        finally:
            conn.close()
        registrar_auditoria("Materias", accion, self.main_window.usuario_actual, nombre)
        self._limpiar_materia()
        self._cargar_materias()

    def _limpiar_materia(self):

        self.id_edicion_materia= None
        self.m_codigo.clear()
        #Vuelve al modo autogenerado por defecto para una materia nueva; si el usuario quiere un código propio, siempre
        #puede pedirlo de nuevo con clic derecho (ver _menu_contextual_codigo_materia).
        self._codigo_materia_manual= False
        self.m_codigo.setReadOnly(True)
        self.m_nombre.clear()
        self.m_creditos.setValue(0)
        self.m_profesor.setCurrentIndex(0)
        self.m_estado.setCurrentIndex(0)
        self.m_curso.setCurrentIndex(0)
        self.tabla_materias.clearSelection()
        desactivar_modo_edicion(self.m_nombre)

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo) — solo entonces tiene sentido pedir el Área
    #Técnica en Cursos y Secciones, o mostrar el módulo Politécnico.
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

    #Muestra/oculta lo que solo tiene sentido en un Politécnico: el campo
    #Área Técnica de Cursos y Secciones (en un colegio regular no existen
    #'áreas técnicas', así que no se le pide al usuario que piense en eso).
    #Los módulos técnicos en sí (materias RA) ya no viven en este módulo,
    #sino en Politécnico. La visibilidad final también depende del Nivel/
    #Ciclo elegido -ver _actualizar_ciclo_y_especialidad_seccion-, por eso
    #se recalcula aquí también (por ejemplo, al cambiar el tipo de
    #institución en Configuración sin haber tocado el combo de Nivel).
    def _actualizar_visibilidad_modelo_evaluacion(self):

        self._actualizar_ciclo_y_especialidad_seccion()

    #Repuebla el combo de Nivel Educativo con solo los niveles que esta
    #institución tiene habilitados (Configuración > Académico) — igual
    #principio que el resto de combos "en cascada" del proyecto: no
    #ofrecer opciones que no tengan sentido para el contexto actual.
    def _poblar_nivel_educativo_seccion(self):

        seleccion_previa= self.s_nivel_educativo.currentData() if self.s_nivel_educativo.count() else None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM configuracion WHERE id=1")
        cfg= c.fetchone()
        conn.close()
        habilitados= niveles_academicos_habilitados(cfg) if cfg else NIVELES_ACADEMICOS
        self.s_nivel_educativo.blockSignals(True)
        self.s_nivel_educativo.clear()
        self.s_nivel_educativo.addItem("— Sin clasificar —", None)
        for nivel in NIVELES_ACADEMICOS:
            if nivel in habilitados:
                self.s_nivel_educativo.addItem(nivel, nivel)
        idx= self.s_nivel_educativo.findData(seleccion_previa)
        self.s_nivel_educativo.setCurrentIndex(idx if idx >= 0 else 0)
        self.s_nivel_educativo.blockSignals(False)

    #El Ciclo solo tiene sentido si el nivel elegido es Secundaria, y el
    #Área Técnica solo es académicamente válida en Secundaria - Segundo
    #Ciclo (República Dominicana): ver puede_tener_componente_tecnico() en
    #configuracion.py, la única lógica que decide esto en todo el sistema.
    #
    #Tanto Área Técnica como Carrera se OCULTAN por completo (no solo se
    #deshabilitan) cuando el Nivel/Ciclo elegido no admite ese componente
    #-por ejemplo, Primaria o Secundaria Primer Ciclo en una institución
    #Personalizada con Politécnico Y Primaria activos a la vez-, para que
    #no queden combos visibles pidiendo un dato que ni siquiera es válido
    #para ese curso.
    def _actualizar_ciclo_y_especialidad_seccion(self):

        nivel= self.s_nivel_educativo.currentData()
        self.s_ciclo_secundaria.setVisible(nivel == "Secundaria")
        if nivel != "Secundaria":
            self.s_ciclo_secundaria.setCurrentIndex(0)
        ciclo= self.s_ciclo_secundaria.currentData()
        permite_tecnico= (not nivel) or puede_tener_componente_tecnico(nivel, ciclo, self._tipo_institucion())
        visible_especialidad= self._es_politecnico() and permite_tecnico
        self.s_especialidad.setVisible(visible_especialidad)
        self.s_especialidad.setEnabled(True)
        if not visible_especialidad:
            self.s_especialidad.setCurrentIndex(0)
            if self._es_politecnico():
                self.s_especialidad.setToolTip(
                    "Esta institución es un Politécnico, pero el nivel/ciclo elegido para este curso "
                    "(Primer Ciclo de Secundaria, Primaria, Preparatoria o Universidad) no puede tener "
                    "Área Técnica -es un componente exclusivo de Secundaria, Segundo Ciclo.")
        else:
            self.s_especialidad.setToolTip(
                "Área técnica del curso/sección (obligatorio en Politécnico). Se usa para filtrar "
                "estudiantes, materias y secciones por área técnica.")

        #Carrera: mismo principio, pero para Universidad -solo tiene sentido cuando el Nivel elegido es Universidad (o
        #todavía no se ha clasificado el curso).
        permite_carrera= (not nivel) or nivel == "Universidad"
        visible_carrera= self._es_universidad() and permite_carrera
        self.s_carrera.setVisible(visible_carrera)
        if not visible_carrera:
            self.s_carrera.setCurrentIndex(0)

    def _tipo_institucion(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT tipo_institucion FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        return (fila["tipo_institucion"] if fila else None) or "Escuela"

    def _cargar_materia_seleccionada(self):

        fila= self.tabla_materias.currentRow()
        if fila < 0:
            return
        id_mat= int(self.tabla_materias.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM materias WHERE id=?", (id_mat,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_materia= f["id"]
        self.m_codigo.setText(f["codigo"] or "")
        #Al cargar una materia ya existente para editarla, el código deja de ser de solo lectura: es la otra puerta de
        #entrada (junto con el clic derecho) para poder escribirlo a mano.
        self._codigo_materia_manual= True
        self.m_codigo.setReadOnly(False)
        self.m_nombre.setText(f["nombre"] or "")
        self.m_creditos.setValue(f["creditos"] or 0)
        idx_curso= self.m_curso.findData(f["grado_id"])
        self.m_curso.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
        idx2= self.m_profesor.findData(f["profesor_id"])
        self.m_profesor.setCurrentIndex(idx2 if idx2 >= 0 else 0)
        self.m_estado.setCurrentText(f["estado"] or "Activa")
        activar_modo_edicion(self.m_nombre, f"Editando materia: {f['nombre'] or ''}")

    def _eliminar_materia(self):

        fila= self.tabla_materias.currentRow()
        if fila < 0:
            return
        id_mat= int(self.tabla_materias.item(fila, 0).text())
        nombre= self.tabla_materias.item(fila, 2).text()
        if mostrar_mensaje("pregunta", "Confirmar", f"¿Eliminar la materia '{nombre}'?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM materias WHERE id=?", (id_mat,))
        conn.commit()
        conn.close()
        registrar_auditoria("Materias", "Eliminó materia", self.main_window.usuario_actual, nombre)
        self._cargar_materias()

    def _filtro_materias_cambio(self):

        self.paginacion_materias.reiniciar()
        self._cargar_materias()

    def _cargar_materias(self):

        conn= obtener_conexion()
        c= conn.cursor()
        #Esta tabla solo muestra materias académicas normales: los módulos
        #técnicos (área técnica asignada / modelo RA) se gestionan y listan
        #aparte, en el módulo Politécnico.
        c.execute("""SELECT materias.*, (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as prof_nombre
                     FROM materias LEFT JOIN profesores ON materias.profesor_id = profesores.id
                     WHERE materias.especialidad_id IS NULL
                       AND (materias.modelo_evaluacion IS NULL OR materias.modelo_evaluacion != ?)
                     ORDER BY materias.nombre""", (MODELO_EVALUACION_TECNICA,))
        filas= c.fetchall()
        conn.close()
        profesor_filtro= self.filtro_materias_profesor.currentData() if hasattr(self, "filtro_materias_profesor") else None
        if profesor_filtro is not None:
            filas= [fila for fila in filas if fila["profesor_id"] == profesor_filtro]
        estado_filtro= self.filtro_materias_estado.currentData() if hasattr(self, "filtro_materias_estado") else None
        if estado_filtro:
            filas= [fila for fila in filas if (fila["estado"] or "Activa") == estado_filtro]
        texto= _normalizar(self.busq_materias.text().strip())
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['codigo']} {fila['nombre']} {fila['prof_nombre']}")]
        self.paginacion_materias.establecer_total(len(filas))
        inicio, fin= self.paginacion_materias.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_materias):
            self.tabla_materias.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_materias.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_materias.setItem(i, 1, QTableWidgetItem(f["codigo"] or ""))
                self.tabla_materias.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_materias.setItem(i, 3, QTableWidgetItem(str(f["creditos"] or 0)))
                self.tabla_materias.setItem(i, 4, QTableWidgetItem(f["prof_nombre"] or ""))
                item_estado= QTableWidgetItem(f["estado"] or "")
                _colorear_texto(item_estado, "#10B981" if (f["estado"] or "Activa") == "Activa" else "#94A3B8")
                self.tabla_materias.setItem(i, 5, item_estado)
            ajustar_anchos_columnas(self.tabla_materias)

    def _tab_secciones(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)
        frame_form, form= self._tarjeta_formulario("Datos de la Sección")
        self.s_grado= QLineEdit()
        limitar_campo_texto(self.s_grado, 300)
        self.s_grado.setPlaceholderText("Grado/Curso (ej. 5to)")
        self.s_nivel_educativo= QComboBox()
        self.s_nivel_educativo.addItem("— Sin clasificar —", None)
        conectar_tooltip_seleccion(self.s_nivel_educativo,
            "Nivel educativo del Grado/Curso. Se usa para calcular la nota mínima aprobatoria correcta "
            "(Sistema Dominicano), para los filtros de Estudiantes, y para validar si el curso puede "
            "tener Área Técnica. Solo se ofrecen los niveles habilitados en Configuración > Académico. "
            "Déjalo 'Sin clasificar' si no aplica.")
        self.s_ciclo_secundaria= QComboBox()
        self.s_ciclo_secundaria.addItem("— Sin clasificar —", None)
        for ciclo in CICLOS_SECUNDARIA:
            self.s_ciclo_secundaria.addItem(ciclo, ciclo)
        conectar_tooltip_seleccion(self.s_ciclo_secundaria,
            "Ciclo dentro de Secundaria (sistema dominicano). Solo el Segundo Ciclo puede tener Área "
            "Técnica/modalidad técnico-profesional; el Primer Ciclo nunca la tiene.")
        self.s_nivel_educativo.currentIndexChanged.connect(self._actualizar_ciclo_y_especialidad_seccion)
        self.s_ciclo_secundaria.currentIndexChanged.connect(self._actualizar_ciclo_y_especialidad_seccion)
        self._poblar_nivel_educativo_seccion()
        self.s_nombre= QLineEdit()
        limitar_campo_texto(self.s_nombre, 300)
        self.s_nombre.setPlaceholderText("Sección (ej. A)")
        self.s_turno= QComboBox()
        self.s_turno.addItems(TURNOS)
        conectar_tooltip_seleccion(self.s_turno, "Turno en el que opera esta sección")
        self.s_aula= QComboBox()
        conectar_tooltip_seleccion(self.s_aula, "Aula fija asignada a la sección. 'Sin asignar' = aún no tiene aula fija")
        self.s_especialidad= QComboBox()
        conectar_tooltip_seleccion(self.s_especialidad,
            "Área técnica del curso/sección (obligatorio en Politécnico). Se usa para filtrar "
            "estudiantes, materias y secciones por área técnica.")
        self.s_carrera= QComboBox()
        conectar_tooltip_seleccion(self.s_carrera,
            "Carrera del curso/sección (opcional, solo en Universidad). No es obligatorio: la mayoría de "
            "estudiantes universitarios ya se matriculan directamente por Carrera. Úsalo solo si además "
            "quieres clasificar este Curso/Sección por Carrera para los filtros del sistema.")
        self.s_profesor_guia= QComboBox()
        conectar_tooltip_seleccion(self.s_profesor_guia,
            "Profesor guía/tutor de la sección. 'Sin asignar' = aún no tiene profesor guía")
        #Aplica el estado inicial de visibilidad del Ciclo (y de habilitado/ deshabilitado del Área Técnica) apenas se
        #crean todos los combos que
        #usa (necesita self.s_especialidad, creado arriba). Antes esto solo
        #se calculaba al DISPARARSE currentIndexChanged, así que con "— Sin clasificar —" seleccionado por defecto (el
        #índice con el que arranca el combo, que no dispara el signal) el combo de Ciclo se quedaba visible desde el
        #inicio hasta el primer cambio manual.
        self._actualizar_ciclo_y_especialidad_seccion()
        form.addWidget(self.s_grado, 0, 0)
        form.addWidget(self.s_nombre, 0, 1)
        form.addWidget(self.s_turno, 0, 2)
        form.addWidget(self.s_aula, 1, 0)
        form.addWidget(self.s_especialidad, 1, 1)
        form.addWidget(self.s_profesor_guia, 1, 2)
        form.addWidget(self.s_nivel_educativo, 2, 0)
        form.addWidget(self.s_ciclo_secundaria, 2, 1)
        form.addWidget(self.s_carrera, 2, 2)
        btn_guardar= QPushButton("Guardar Sección")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_seccion)
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_seccion)
        form.addWidget(btn_limpiar, 3, 1)
        self._envolver_en_panel(disposicion, "Añadir Sección", frame_form)

        frame_resultados, lr= self._tarjeta_resultados()
        barra_busqueda, self.busq_secciones= self._barra_busqueda(
            "Buscar por grado, sección, aula, área técnica, carrera o profesor guía…", self._filtro_secciones_cambio)

        #--- Ventana de filtros (Nivel Educativo / Turno) --- Mismo patrón (y misma fuente de verdad,
        #niveles_academicos_habilitados) que ya usan Estudiantes/Asistencia/Calificaciones/Horario/
        #Observaciones/Reportes/Banco de Tareas: útil sobre todo en una institución "Personalizado" con varios niveles
        #activos a la vez.
        self.combo_filtro_nivel_seccion= QComboBox()
        self.combo_filtro_nivel_seccion.currentIndexChanged.connect(self._filtro_secciones_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel_seccion, "Filtrar la lista de Cursos y Secciones por nivel educativo")
        self.combo_filtro_turno_seccion= QComboBox()
        self.combo_filtro_turno_seccion.addItem("Todos los turnos", None)
        for turno in TURNOS:
            self.combo_filtro_turno_seccion.addItem(turno, turno)
        self.combo_filtro_turno_seccion.currentIndexChanged.connect(self._filtro_secciones_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_turno_seccion, "Filtrar la lista de Cursos y Secciones por turno")
        self.dialogo_filtros_secciones= self._construir_dialogo_filtros("Filtros de Cursos y Secciones", [
            ("Nivel Educativo:", self.combo_filtro_nivel_seccion),
            ("Turno:", self.combo_filtro_turno_seccion),
        ])
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._agregar_boton_filtros(barra_busqueda, lambda: self._abrir_dialogo(self.dialogo_filtros_secciones))
        lr.addWidget(barra_busqueda)


        self.tabla_secciones= QTableWidget(0, 8)
        aplicar_estructura_tabla(self.tabla_secciones)

        self.tabla_secciones.setHorizontalHeaderLabels(
            ["ID", "Grado/Curso", "Sección", "Turno", "Aula", "Área Técnica", "Carrera", "Profesor Guía"])
        self.tabla_secciones.setColumnHidden(0, True)
        header= self.tabla_secciones.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_secciones.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_secciones.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_secciones.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_secciones.setAlternatingRowColors(True)
        self.tabla_secciones.setWordWrap(True)
        self.tabla_secciones.setMinimumHeight(220)
        self.tabla_secciones.verticalHeader().setVisible(False)
        lr.addWidget(self.tabla_secciones, 1)

        self.paginacion_secciones= ControlPaginacion()
        self.paginacion_secciones.cambio.connect(self._cargar_secciones)
        lr.addWidget(self.paginacion_secciones)

        agregar_boton_pantalla_completa(
            None, [self.tabla_secciones, self.paginacion_secciones],
            titulo= "Cursos y Secciones", parent=self)

        fila_botones= QHBoxLayout()
        btn_actualizar_sec= QPushButton("Actualizar")
        btn_actualizar_sec.setIcon(icono_emoji("🔄"))
        btn_actualizar_sec.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_sec.setObjectName("BtnAccionNeutro")
        btn_actualizar_sec.clicked.connect(self._cargar_secciones)
        fila_botones.addWidget(btn_actualizar_sec)
        btn_editar= QPushButton("Cargar")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionEditar")
        btn_editar.clicked.connect(self._cargar_seccion_seleccionada)
        fila_botones.addWidget(btn_editar)
        btn_eliminar= QPushButton("Eliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_seccion)
        fila_botones.addWidget(btn_eliminar)
        btn_detalle_sec= agregar_boton_detalle(fila_botones, self.tabla_secciones, self, titulo="Detalle de la Sección")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_secciones.doubleClicked.connect(lambda *_: btn_detalle_sec.click())
        fila_botones.addStretch()
        lr.addLayout(fila_botones)
        lr.addStretch()
        disposicion.addWidget(frame_resultados, 1)
        return contenedor

    def _guardar_seccion(self):

        if not self.s_grado.text().strip() or not self.s_nombre.text().strip():
            mostrar_mensaje("advertencia", "Datos incompletos", "Grado y sección son obligatorios.", self)
            return
        nivel_educativo= self.s_nivel_educativo.currentData()
        ciclo_secundaria= self.s_ciclo_secundaria.currentData() if nivel_educativo == "Secundaria" else None
        #El Área Técnica solo es obligatoria si, además de ser un Politécnico, el Nivel/Ciclo de ESTE curso admite
        #componente técnico (ver puede_tener_componente_tecnico). Si el usuario ya clasificó el curso como Primaria,
        #Preparatoria, Universidad o Secundaria-Primer Ciclo, el combo ni siquiera se muestra
        #(_actualizar_ciclo_y_especialidad_seccion) y por lo tanto tampoco debe exigirse aquí.
        permite_tecnico= (not nivel_educativo) or puede_tener_componente_tecnico(
            nivel_educativo, ciclo_secundaria, self._tipo_institucion())
        if self._es_politecnico() and permite_tecnico and self.s_especialidad.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos",
                             "Esta institución es un Politécnico: selecciona el Área Técnica del curso/sección.", self)
            return
        #Validación lógica (no solo visual): un Área Técnica nunca es válida fuera de Secundaria - Segundo Ciclo, sin
        #importar cómo haya quedado habilitado o no el combo en pantalla (ver puede_tener_componente_tecnico).
        if (self.s_especialidad.currentData() is not None
                and not puede_tener_componente_tecnico(nivel_educativo, ciclo_secundaria, self._tipo_institucion())):
            mostrar_mensaje("advertencia", "Combinación inválida",
                             "El Área Técnica solo es válida para cursos de Secundaria - Segundo Ciclo. "
                             "Cambia el Nivel Educativo/Ciclo del curso o quita el Área Técnica.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id FROM grados WHERE nombre=?", (self.s_grado.text().strip(),))
        g= c.fetchone()
        if g:
            grado_id= g["id"]
            #El curso también "recuerda" el área técnica más reciente que se le asignó desde una sección, para poder
            #filtrar por área técnica a nivel de curso.
            if self.s_especialidad.currentData() is not None:
                c.execute("UPDATE grados SET especialidad_id=? WHERE id=?",
                          (self.s_especialidad.currentData(), grado_id))
            #Mismo criterio para la Carrera (Universidad): el Curso "recuerda" la última Carrera que se le asignó desde una
            #sección, igual que ya hace con el Área Técnica de Politécnico.
            if self.s_carrera.currentData() is not None:
                c.execute("UPDATE grados SET carrera_id=? WHERE id=?",
                          (self.s_carrera.currentData(), grado_id))
            #Mismo criterio para el nivel educativo (Primaria/Secundaria/Preparatoria/ Universidad) y el ciclo: se guardan
            #a nivel de Grado/Curso, no de Sección, así que se actualizan aquí igual que la especialidad. "Sin clasificar"
            #(None) se guarda tal cual: permite revertir una clasificación puesta por error.
            c.execute("UPDATE grados SET nivel_educativo=?, ciclo_secundaria=? WHERE id=?",
                      (nivel_educativo, ciclo_secundaria, grado_id))
        else:
            c.execute("INSERT INTO grados (nombre, especialidad_id, carrera_id, nivel_educativo, ciclo_secundaria) "
                      "VALUES (?,?,?,?,?)",
                      (self.s_grado.text().strip(), self.s_especialidad.currentData(),
                       self.s_carrera.currentData(), nivel_educativo, ciclo_secundaria))
            grado_id= c.lastrowid
        datos= (grado_id, self.s_nombre.text().strip(), self.s_turno.currentText(),
                 self.s_aula.currentData(), self.s_especialidad.currentData(), self.s_carrera.currentData(),
                 self.s_profesor_guia.currentData())
        if self.id_edicion_seccion is None:
            c.execute("""INSERT INTO secciones (grado_id, nombre, turno, aula_id, especialidad_id, carrera_id,
                         profesor_guia_id) VALUES (?,?,?,?,?,?,?)""", datos)
            accion= "Registró sección"
        else:
            c.execute("""UPDATE secciones SET grado_id=?, nombre=?, turno=?, aula_id=?, especialidad_id=?,
                         carrera_id= ?, profesor_guia_id=? WHERE id=?""", datos + (self.id_edicion_seccion,))
            accion= "Editó sección"
        conn.commit()
        conn.close()
        registrar_auditoria("Secciones", accion, self.main_window.usuario_actual,
                            f"{self.s_grado.text()} - {self.s_nombre.text()}")
        self._limpiar_seccion()
        self.refrescar()

    def _limpiar_seccion(self):

        #BUG corregido: antes solo se limpiaban Grado y Sección, así que Turno, Aula, Especialidad y Profesor Guía
        #quedaban con el valor de la última sección cargada/guardada. Eso hacía que una sección nueva pudiera guardarse
        #por accidente con el profesor guía (u otro dato) de la anterior, sin que el usuario lo notara.
        self.id_edicion_seccion= None
        self.s_grado.clear()
        self.s_nivel_educativo.setCurrentIndex(0)
        self.s_ciclo_secundaria.setCurrentIndex(0)
        self.s_nombre.clear()
        self.s_turno.setCurrentIndex(0)
        self.s_aula.setCurrentIndex(0)
        self.s_especialidad.setCurrentIndex(0)
        self.s_carrera.setCurrentIndex(0)
        self.s_profesor_guia.setCurrentIndex(0)
        self.tabla_secciones.clearSelection()
        #Por si Nivel/Ciclo ya estaban en índice 0 (no dispara currentIndexChanged):
        #recalcula visibilidad igualmente, para que Ciclo no quede visible por error.
        self._actualizar_ciclo_y_especialidad_seccion()
        desactivar_modo_edicion(self.s_nombre)

    def _cargar_seccion_seleccionada(self):

        fila= self.tabla_secciones.currentRow()
        if fila < 0:
            return
        id_sec= int(self.tabla_secciones.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT secciones.*, grados.nombre as grado_nombre, grados.nivel_educativo as nivel_educativo,
                     grados.ciclo_secundaria as ciclo_secundaria
                     FROM secciones
                     LEFT JOIN grados ON secciones.grado_id = grados.id WHERE secciones.id=?""", (id_sec,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_seccion= f["id"]
        self.s_grado.setText(f["grado_nombre"] or "")
        idx_nivel= self.s_nivel_educativo.findData(f["nivel_educativo"])
        self.s_nivel_educativo.setCurrentIndex(idx_nivel if idx_nivel >= 0 else 0)
        idx_ciclo= self.s_ciclo_secundaria.findData(f["ciclo_secundaria"])
        self.s_ciclo_secundaria.setCurrentIndex(idx_ciclo if idx_ciclo >= 0 else 0)
        self._actualizar_ciclo_y_especialidad_seccion()
        self.s_nombre.setText(f["nombre"] or "")
        self.s_turno.setCurrentText(f["turno"] or "Mañana")
        idx= self.s_aula.findData(f["aula_id"])
        self.s_aula.setCurrentIndex(idx if idx >= 0 else 0)
        idx2= self.s_especialidad.findData(f["especialidad_id"])
        self.s_especialidad.setCurrentIndex(idx2 if idx2 >= 0 else 0)
        idx4= self.s_carrera.findData(f["carrera_id"])
        self.s_carrera.setCurrentIndex(idx4 if idx4 >= 0 else 0)
        idx3= self.s_profesor_guia.findData(f["profesor_guia_id"])
        self.s_profesor_guia.setCurrentIndex(idx3 if idx3 >= 0 else 0)
        activar_modo_edicion(self.s_nombre, f"Editando sección: {f['nombre'] or ''}")

    def _eliminar_seccion(self):

        fila= self.tabla_secciones.currentRow()
        if fila < 0:
            return
        id_sec= int(self.tabla_secciones.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta sección?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM secciones WHERE id=?", (id_sec,))
        conn.commit()
        conn.close()
        registrar_auditoria("Secciones", "Eliminó sección", self.main_window.usuario_actual, str(id_sec))
        self.refrescar()

    def _filtro_secciones_cambio(self):

        self.paginacion_secciones.reiniciar()
        self._cargar_secciones()

    def _cargar_secciones(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT secciones.*, grados.nombre as grado_nombre, aulas.nombre as aula_nombre,
                     especialidades.nombre as especialidad_nombre, carreras.nombre as carrera_nombre,
                     (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as prof_nombre
                     FROM secciones
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN aulas ON secciones.aula_id = aulas.id
                     LEFT JOIN especialidades ON secciones.especialidad_id = especialidades.id
                     LEFT JOIN carreras ON secciones.carrera_id = carreras.id
                     LEFT JOIN profesores ON secciones.profesor_guia_id = profesores.id
                     ORDER BY grados.orden, secciones.nombre""")
        filas= c.fetchall()
        conn.close()
        nivel_filtro= self.combo_filtro_nivel_seccion.currentData() if hasattr(self, "combo_filtro_nivel_seccion") else None
        if nivel_filtro:
            ids_nivel= secciones_del_nivel_educativo(nivel_filtro)
            filas= [fila for fila in filas if fila["id"] in ids_nivel]
        turno_filtro= self.combo_filtro_turno_seccion.currentData() if hasattr(self, "combo_filtro_turno_seccion") else None
        if turno_filtro:
            filas= [fila for fila in filas if fila["turno"] == turno_filtro]
        texto= _normalizar(self.busq_secciones.text().strip())
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['grado_nombre']} {fila['nombre']} {fila['turno']} {fila['aula_nombre']} "
                f"{fila['especialidad_nombre']} {fila['carrera_nombre']} {fila['prof_nombre']}")]
        self.paginacion_secciones.establecer_total(len(filas))
        inicio, fin= self.paginacion_secciones.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_secciones):
            self.tabla_secciones.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_secciones.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_secciones.setItem(i, 1, QTableWidgetItem(f["grado_nombre"] or ""))
                self.tabla_secciones.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                item_turno= QTableWidgetItem(f["turno"] or "")
                _colorear_texto(item_turno, _COLORES_TURNO.get(f["turno"], "#94A3B8"))
                self.tabla_secciones.setItem(i, 3, item_turno)
                self.tabla_secciones.setItem(i, 4, QTableWidgetItem(f["aula_nombre"] or ""))
                self.tabla_secciones.setItem(i, 5, QTableWidgetItem(f["especialidad_nombre"] or "—"))
                self.tabla_secciones.setItem(i, 6, QTableWidgetItem(f["carrera_nombre"] or "—"))
                self.tabla_secciones.setItem(i, 7, QTableWidgetItem(f["prof_nombre"] or ""))
            ajustar_anchos_columnas(self.tabla_secciones)

    def _tab_aulas(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)
        frame_form, form= self._tarjeta_formulario("Datos del Espacio Físico")
        self.a_nombre= QLineEdit()
        limitar_campo_texto(self.a_nombre, 300)
        self.a_nombre.setPlaceholderText("Nombre del Aula/Laboratorio")
        self.a_tipo= QComboBox()
        self.a_tipo.addItems(["Aula", "Laboratorio", "Taller"])
        conectar_tooltip_seleccion(self.a_tipo, "Tipo de espacio físico")
        self.a_capacidad= QSpinBox()
        self.a_capacidad.setRange(1, 200)
        self.a_capacidad.setValue(30)
        self.a_capacidad.setToolTip("Capacidad máxima de estudiantes que caben en el espacio")
        form.addWidget(self.a_nombre, 0, 0)
        form.addWidget(self.a_tipo, 0, 1)
        form.addWidget(self.a_capacidad, 0, 2)
        btn_guardar= QPushButton("Guardar Aula")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_aula)
        form.addWidget(btn_guardar, 1, 0)
        btn_limpiar_aula= QPushButton("Limpiar")
        btn_limpiar_aula.setIcon(icono_emoji("🧹"))
        btn_limpiar_aula.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_aula.setObjectName("BtnAccionNeutro")
        btn_limpiar_aula.clicked.connect(self._limpiar_aula)
        form.addWidget(btn_limpiar_aula, 1, 1)
        self._envolver_en_panel(disposicion, "Añadir Aula", frame_form)

        frame_resultados, lr= self._tarjeta_resultados()
        barra_busqueda, self.busq_aulas= self._barra_busqueda(
            "Buscar por nombre o tipo…", self._filtro_aulas_cambio)

        #--- Ventana de filtros (Tipo de espacio) ---
        self.combo_filtro_tipo_aula= QComboBox()
        self.combo_filtro_tipo_aula.addItem("Todos los tipos", None)
        self.combo_filtro_tipo_aula.addItem("Aula", "Aula")
        self.combo_filtro_tipo_aula.addItem("Laboratorio", "Laboratorio")
        self.combo_filtro_tipo_aula.addItem("Taller", "Taller")
        self.combo_filtro_tipo_aula.currentIndexChanged.connect(self._filtro_aulas_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_tipo_aula, "Filtrar la lista por tipo de espacio físico")
        self.dialogo_filtros_aulas= self._construir_dialogo_filtros("Filtros de Aulas y Laboratorios", [
            ("Tipo:", self.combo_filtro_tipo_aula),
        ])
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._agregar_boton_filtros(barra_busqueda, lambda: self._abrir_dialogo(self.dialogo_filtros_aulas))
        lr.addWidget(barra_busqueda)


        self.tabla_aulas= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_aulas)

        self.tabla_aulas.setHorizontalHeaderLabels(["ID", "Nombre", "Tipo", "Capacidad"])
        self.tabla_aulas.setColumnHidden(0, True)
        header= self.tabla_aulas.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_aulas.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_aulas.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_aulas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_aulas.setAlternatingRowColors(True)
        self.tabla_aulas.setWordWrap(True)
        self.tabla_aulas.setMinimumHeight(220)
        self.tabla_aulas.verticalHeader().setVisible(False)
        lr.addWidget(self.tabla_aulas, 1)

        self.paginacion_aulas= ControlPaginacion()
        self.paginacion_aulas.cambio.connect(self._cargar_aulas)
        lr.addWidget(self.paginacion_aulas)

        agregar_boton_pantalla_completa(
            None, [self.tabla_aulas, self.paginacion_aulas],
            titulo= "Aulas y Laboratorios", parent=self)

        fila_acciones_aulas= QHBoxLayout()
        btn_actualizar_aulas= QPushButton("Actualizar")
        btn_actualizar_aulas.setIcon(icono_emoji("🔄"))
        btn_actualizar_aulas.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_aulas.setObjectName("BtnAccionNeutro")
        btn_actualizar_aulas.clicked.connect(self._cargar_aulas)
        fila_acciones_aulas.addWidget(btn_actualizar_aulas)
        btn_editar_aula= QPushButton("Cargar")
        btn_editar_aula.setIcon(icono_emoji("✏"))
        btn_editar_aula.setIconSize(_QSize_emoji(16, 16))
        btn_editar_aula.setObjectName("BtnAccionEditar")
        btn_editar_aula.clicked.connect(self._cargar_aula_seleccionada)
        fila_acciones_aulas.addWidget(btn_editar_aula)
        btn_eliminar= QPushButton("Eliminar Aula Seleccionada")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_aula)
        fila_acciones_aulas.addWidget(btn_eliminar)
        btn_detalle_aula= agregar_boton_detalle(fila_acciones_aulas, self.tabla_aulas, self, titulo="Detalle del Aula")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_aulas.doubleClicked.connect(lambda *_: btn_detalle_aula.click())
        fila_acciones_aulas.addStretch()
        lr.addLayout(fila_acciones_aulas)
        lr.addStretch()
        disposicion.addWidget(frame_resultados, 1)
        return contenedor

    def _limpiar_aula(self):

        self.id_edicion_aula= None
        self.a_nombre.clear()
        self.a_tipo.setCurrentIndex(0)
        self.a_capacidad.setValue(30)
        self.tabla_aulas.clearSelection()
        desactivar_modo_edicion(self.a_nombre)

    def _cargar_aula_seleccionada(self):

        fila= self.tabla_aulas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un aula de la tabla.", self)
            return
        id_aula= int(self.tabla_aulas.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM aulas WHERE id=?", (id_aula,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_aula= f["id"]
        self.a_nombre.setText(f["nombre"] or "")
        self.a_tipo.setCurrentText(f["tipo"] or "Aula")
        self.a_capacidad.setValue(f["capacidad"] or 1)
        activar_modo_edicion(self.a_nombre, f"Editando aula: {f['nombre'] or ''}")

    def _guardar_aula(self):

        if not self.a_nombre.text().strip():
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        if self.id_edicion_aula is None:
            c.execute("INSERT INTO aulas (nombre, tipo, capacidad) VALUES (?,?,?)",
                      (self.a_nombre.text().strip(), self.a_tipo.currentText(), self.a_capacidad.value()))
            accion= "Agregó aula"
        else:
            c.execute("UPDATE aulas SET nombre=?, tipo=?, capacidad=? WHERE id=?",
                      (self.a_nombre.text().strip(), self.a_tipo.currentText(), self.a_capacidad.value(),
                       self.id_edicion_aula))
            accion= "Editó aula"
        conn.commit()
        conn.close()
        registrar_auditoria("Aulas", accion, self.main_window.usuario_actual, self.a_nombre.text().strip())
        self._limpiar_aula()
        self.refrescar()

    def _eliminar_aula(self):

        fila= self.tabla_aulas.currentRow()
        if fila < 0:
            return
        id_aula= int(self.tabla_aulas.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM aulas WHERE id=?", (id_aula,))
        conn.commit()
        conn.close()
        registrar_auditoria("Aulas", "Eliminó aula", self.main_window.usuario_actual, str(id_aula))
        self.refrescar()

    def _filtro_aulas_cambio(self):

        self.paginacion_aulas.reiniciar()
        self._cargar_aulas()

    def _cargar_aulas(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM aulas ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        tipo_filtro= self.combo_filtro_tipo_aula.currentData() if hasattr(self, "combo_filtro_tipo_aula") else None
        if tipo_filtro:
            filas= [fila for fila in filas if fila["tipo"] == tipo_filtro]
        texto= _normalizar(self.busq_aulas.text().strip())
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(f"{fila['nombre']} {fila['tipo']}")]
        self.paginacion_aulas.establecer_total(len(filas))
        inicio, fin= self.paginacion_aulas.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_aulas):
            self.tabla_aulas.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_aulas.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_aulas.setItem(i, 1, QTableWidgetItem(f["nombre"] or ""))
                self.tabla_aulas.setItem(i, 2, QTableWidgetItem(f["tipo"] or ""))
                self.tabla_aulas.setItem(i, 3, QTableWidgetItem(str(f["capacidad"] or 0)))
            ajustar_anchos_columnas(self.tabla_aulas)

    def _tab_horarios(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)

        frame_grafico, lg= self._tarjeta_resultados()
        lbl_grafico= QLabel("Clases programadas por día")
        f_lbl= lbl_grafico.font()
        f_lbl.setBold(True)
        f_lbl.setPointSize(11)
        lbl_grafico.setFont(f_lbl)
        lbl_grafico.setStyleSheet("background: transparent;")
        lg.addWidget(lbl_grafico)
        self.grafico_ocupacion= GraficoOcupacionSemanal()
        lg.addWidget(self.grafico_ocupacion)
        disposicion.addWidget(frame_grafico)

        frame_form, form= self._tarjeta_formulario("Asignar Clase")
        #Curso/Grado va PRIMERO y es obligatorio: acota de una vez la lista de Secciones a las de ese curso (antes se
        #elegía directo la Sección, ya mezclando todos los cursos, y encima el combo arrancaba con la primera sección
        #de la lista ya seleccionada — así que "Sección" en realidad nunca era obligatoria, se guardaba el valor por
        #defecto si el usuario no tocaba el combo).
        self.h_curso= QComboBox()
        self.h_curso.setToolTip("Curso/Grado al que pertenece la sección (obligatorio)")
        self.h_curso.addItem("Selecciona un curso/grado…", None)
        self.h_curso.currentIndexChanged.connect(self._al_cambiar_curso_horario)
        self.h_seccion= QComboBox()
        self.h_seccion.setToolTip("Sección a la que se asigna esta clase (obligatorio)")
        self.h_seccion.addItem("Selecciona primero un curso/grado…", None)
        self.h_materia= QComboBox()
        conectar_tooltip_seleccion(self.h_materia, "Materia o Módulo Técnico que se dicta en este horario")
        self.h_dia= QComboBox()
        self.h_dia.addItems(DIAS)
        conectar_tooltip_seleccion(self.h_dia, "Día de la semana en que se dicta la clase")
        self.h_hora_inicio= QLineEdit()
        limitar_campo_texto(self.h_hora_inicio, 300)
        self.h_hora_inicio.setPlaceholderText("Hora inicio (08:00)")
        self.h_hora_fin= QLineEdit()
        limitar_campo_texto(self.h_hora_fin, 300)
        self.h_hora_fin.setPlaceholderText("Hora fin (09:00)")
        self.h_aula= QComboBox()
        conectar_tooltip_seleccion(self.h_aula, "Aula donde se dicta la clase. 'Sin asignar' = sin aula fija para esta clase")
        form.addWidget(self.h_curso, 0, 0)
        form.addWidget(self.h_seccion, 0, 1)
        form.addWidget(self.h_materia, 0, 2)
        form.addWidget(self.h_dia, 1, 0)
        form.addWidget(self.h_hora_inicio, 1, 1)
        form.addWidget(self.h_hora_fin, 1, 2)
        form.addWidget(self.h_aula, 2, 0)
        btn_guardar= QPushButton("Guardar Horario")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_horario)
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar_horario= QPushButton("Limpiar")
        btn_limpiar_horario.setIcon(icono_emoji("🧹"))
        btn_limpiar_horario.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_horario.setObjectName("BtnAccionNeutro")
        btn_limpiar_horario.clicked.connect(self._limpiar_horario_form)
        form.addWidget(btn_limpiar_horario, 3, 1)

        #Área Técnica (Politécnico) / Carrera (Universidad): en SU PROPIA fila, dentro de un cuadrito con aire
        #alrededor, nunca apretados junto a Curso/Sección/Materia. Van ANTES del formulario de Curso/Sección/Materia
        #(se eligen primero) — al elegir Área Técnica, "Sección" se acota a las de esa especialidad y "Materia/Módulo
        #Técnico" se acota a los módulos de esa área — pedido explícito: los módulos que salen en el combo deben ser
        #únicamente los de esa área técnica.
        frame_filtro_tecnico_horario= QFrame()
        frame_filtro_tecnico_horario.setObjectName("CuadroFiltroTecnico")
        frame_filtro_tecnico_horario.setStyleSheet(
            "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
            "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
        fila_filtro_tecnico_horario= QHBoxLayout(frame_filtro_tecnico_horario)
        fila_filtro_tecnico_horario.setContentsMargins(14, 10, 14, 10)
        fila_filtro_tecnico_horario.setSpacing(16)
        self.lbl_filtro_especialidad_horario= QLabel("Área Técnica:")
        self.h_filtro_especialidad= QComboBox()
        self.h_filtro_especialidad.setToolTip(
            "Acota Sección y Materia/Módulo Técnico a esta área técnica (Politécnico)")
        self.h_filtro_especialidad.setMinimumWidth(210)
        conectar_tooltip_seleccion(self.h_filtro_especialidad,
            "Acota Sección y Materia/Módulo Técnico a esta área técnica (Politécnico)")
        self.h_filtro_especialidad.currentIndexChanged.connect(self._filtro_tecnico_horario_cambio)
        fila_filtro_tecnico_horario.addWidget(self.lbl_filtro_especialidad_horario)
        fila_filtro_tecnico_horario.addWidget(self.h_filtro_especialidad)

        self.lbl_filtro_carrera_horario= QLabel("Carrera:")
        self.h_filtro_carrera= QComboBox()
        self.h_filtro_carrera.setToolTip("Acota Sección a las que tienen estudiantes de esta carrera (Universidad)")
        self.h_filtro_carrera.setMinimumWidth(210)
        conectar_tooltip_seleccion(self.h_filtro_carrera,
            "Acota Sección a las que tienen estudiantes de esta carrera (Universidad)")
        self.h_filtro_carrera.currentIndexChanged.connect(self._filtro_tecnico_horario_cambio)
        fila_filtro_tecnico_horario.addWidget(self.lbl_filtro_carrera_horario)
        fila_filtro_tecnico_horario.addWidget(self.h_filtro_carrera)
        fila_filtro_tecnico_horario.addStretch()
        self._envolver_en_panel(disposicion, "Asignar Clase", frame_filtro_tecnico_horario, frame_form)

        frame_resultados, lr= self._tarjeta_resultados()
        barra_busqueda, self.busq_horarios= self._barra_busqueda(
            "Buscar por sección, materia/módulo técnico o aula…", self._filtro_horarios_cambio)

        #--- Ventana de filtros (Curso/Grado, Sección, Día) --- Combos INDEPENDIENTES de los del formulario "Asignar
        #Clase" de arriba (h_curso/h_seccion): esos son para elegir dónde crear una clase nueva; estos son solo para
        #acotar qué se ve en la tabla de abajo.
        self.filtro_horarios_curso= QComboBox()
        self.filtro_horarios_seccion= QComboBox()
        poblar_combo_curso(self.filtro_horarios_curso, incluir_todos=True)
        cascada_seccion_por_curso(self.filtro_horarios_curso, self.filtro_horarios_seccion, incluir_todas=True)
        self.filtro_horarios_curso.currentIndexChanged.connect(self._al_cambiar_filtro_curso_horarios)
        self.filtro_horarios_seccion.currentIndexChanged.connect(self._filtro_horarios_cambio)
        conectar_tooltip_seleccion(self.filtro_horarios_curso, "Filtrar la lista de horarios por curso/grado")
        conectar_tooltip_seleccion(self.filtro_horarios_seccion, "Filtrar la lista de horarios por sección")
        self.filtro_horarios_dia= QComboBox()
        self.filtro_horarios_dia.addItem("Todos los días", None)
        for dia in DIAS:
            self.filtro_horarios_dia.addItem(dia, dia)
        self.filtro_horarios_dia.currentIndexChanged.connect(self._filtro_horarios_cambio)
        conectar_tooltip_seleccion(self.filtro_horarios_dia, "Filtrar la lista de horarios por día de la semana")
        self.dialogo_filtros_horarios= self._construir_dialogo_filtros("Filtros de Horarios", [
            ("Curso/Grado:", self.filtro_horarios_curso),
            ("Sección:", self.filtro_horarios_seccion),
            ("Día:", self.filtro_horarios_dia),
        ])
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._agregar_boton_filtros(barra_busqueda, lambda: self._abrir_dialogo(self.dialogo_filtros_horarios))
        lr.addWidget(barra_busqueda)


        self.tabla_horarios= QTableWidget(0, 7)
        aplicar_estructura_tabla(self.tabla_horarios)

        self.tabla_horarios.setHorizontalHeaderLabels(
            ["ID", "Curso", "Sección", "Materia / Módulo Técnico", "Día", "Horario", "Aula"])
        self.tabla_horarios.setColumnHidden(0, True)
        header= self.tabla_horarios.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla_horarios.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_horarios.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_horarios.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_horarios.setAlternatingRowColors(True)
        self.tabla_horarios.setWordWrap(True)
        self.tabla_horarios.setMinimumHeight(220)
        self.tabla_horarios.verticalHeader().setVisible(False)
        lr.addWidget(self.tabla_horarios, 1)

        self.paginacion_horarios= ControlPaginacion()
        self.paginacion_horarios.cambio.connect(self._cargar_horarios)
        lr.addWidget(self.paginacion_horarios)

        agregar_boton_pantalla_completa(
            None, [self.tabla_horarios, self.paginacion_horarios],
            titulo= "Horarios", parent=self)

        fila_acciones_horarios= QHBoxLayout()
        btn_actualizar_horarios= QPushButton("Actualizar")
        btn_actualizar_horarios.setIcon(icono_emoji("🔄"))
        btn_actualizar_horarios.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar_horarios.setObjectName("BtnAccionNeutro")
        btn_actualizar_horarios.clicked.connect(self._cargar_horarios)
        fila_acciones_horarios.addWidget(btn_actualizar_horarios)
        btn_editar_horario= QPushButton("Cargar")
        btn_editar_horario.setIcon(icono_emoji("✏"))
        btn_editar_horario.setIconSize(_QSize_emoji(16, 16))
        btn_editar_horario.setObjectName("BtnAccionEditar")
        btn_editar_horario.clicked.connect(self._cargar_horario_seleccionado)
        fila_acciones_horarios.addWidget(btn_editar_horario)
        btn_eliminar= QPushButton("Eliminar Horario Seleccionado")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_horario)
        fila_acciones_horarios.addWidget(btn_eliminar)
        btn_detalle_hor= agregar_boton_detalle(fila_acciones_horarios, self.tabla_horarios, self, titulo="Detalle del Horario")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_horarios.doubleClicked.connect(lambda *_: btn_detalle_hor.click())
        fila_acciones_horarios.addStretch()
        lr.addLayout(fila_acciones_horarios)
        lr.addStretch()
        disposicion.addWidget(frame_resultados, 1)
        return contenedor

    #Repuebla 'Sección' con solo las secciones del curso/grado elegido en
    #'Curso/Grado'. Mientras no se elija un curso, 'Sección' queda vacía
    #(con un placeholder sin datos), así que no puede quedar seleccionada
    #por accidente una sección de otro curso.
    #
    #Si además hay un Área Técnica/Carrera elegidos en el cuadrito de
    #abajo, la lista de secciones se acota más: Área Técnica usa
    #secciones.especialidad_id directamente; Carrera (dato por
    #estudiante, no por sección) se resuelve viendo qué secciones tienen
    #al menos un estudiante activo de esa carrera.
    def _al_cambiar_curso_horario(self, _indice=None, seccion_id_preseleccionar=None):

        cascada_seccion_por_curso(self.h_curso, self.h_seccion, incluir_todas=False)

        especialidad_id= self.h_filtro_especialidad.currentData() if self._es_politecnico() else None
        carrera_id= self.h_filtro_carrera.currentData() if self._es_universidad() else None
        if especialidad_id is not None or carrera_id is not None:
            secciones_carrera= None
            if carrera_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                             WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
                secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
                conn.close()
            actual= self.h_seccion.currentData()
            for i in range(self.h_seccion.count() - 1, 0, -1):
                seccion_id= self.h_seccion.itemData(i)
                if seccion_id is None:
                    continue
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT especialidad_id FROM secciones WHERE id=?", (seccion_id,))
                fila_sec= c.fetchone()
                conn.close()
                especialidad_seccion= fila_sec["especialidad_id"] if fila_sec else None
                if especialidad_id is not None and especialidad_seccion != especialidad_id:
                    self.h_seccion.removeItem(i)
                    continue
                if secciones_carrera is not None and seccion_id not in secciones_carrera:
                    self.h_seccion.removeItem(i)
            idx= self.h_seccion.findData(actual)
            self.h_seccion.setCurrentIndex(idx if idx >= 0 else 0)

        if seccion_id_preseleccionar is not None:
            idx= self.h_seccion.findData(seccion_id_preseleccionar)
            self.h_seccion.setCurrentIndex(idx if idx >= 0 else 0)

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera del
    #formulario 'Asignar Clase' solo se muestran/pueblan si la
    #institución tiene ese módulo activo.
    def _cargar_filtro_tecnico_horario(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_horario.setVisible(es_poli)
        self.h_filtro_especialidad.setVisible(es_poli)
        if es_poli:
            actual= self.h_filtro_especialidad.currentData()
            self.h_filtro_especialidad.blockSignals(True)
            self.h_filtro_especialidad.clear()
            self.h_filtro_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.h_filtro_especialidad.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.h_filtro_especialidad.findData(actual)
            self.h_filtro_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.h_filtro_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_horario.setVisible(es_uni)
        self.h_filtro_carrera.setVisible(es_uni)
        if es_uni:
            actual= self.h_filtro_carrera.currentData()
            self.h_filtro_carrera.blockSignals(True)
            self.h_filtro_carrera.clear()
            self.h_filtro_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.h_filtro_carrera.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.h_filtro_carrera.findData(actual)
            self.h_filtro_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.h_filtro_carrera.blockSignals(False)

    def _filtro_tecnico_horario_cambio(self):

        self._al_cambiar_curso_horario()
        self._cargar_combo_h_materia()

    #Materia/Módulo Técnico de 'Asignar Clase'. Si hay un Área Técnica
    #elegida, se filtra ESTRICTAMENTE a los módulos de esa área — pedido
    #explícito: al elegir curso+sección+área técnica, el combo debe
    #listar únicamente los módulos de esa área.
    def _cargar_combo_h_materia(self):

        especialidad_id= self.h_filtro_especialidad.currentData() if self._es_politecnico() else None
        actual= self.h_materia.currentData()
        self.h_materia.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        if especialidad_id is not None:
            c.execute("""SELECT id, nombre FROM materias
                         WHERE estado='Activa' AND especialidad_id=? ORDER BY nombre""", (especialidad_id,))
        else:
            c.execute("SELECT id, nombre FROM materias WHERE estado='Activa' ORDER BY nombre")
        for fila in c.fetchall():
            self.h_materia.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= self.h_materia.findData(actual)
        self.h_materia.setCurrentIndex(idx if idx >= 0 else 0)

    def _limpiar_horario_form(self):

        self.id_edicion_horario= None
        self.h_curso.setCurrentIndex(0)
        self.h_seccion.setCurrentIndex(0)
        if hasattr(self, "h_filtro_especialidad"):
            self.h_filtro_especialidad.setCurrentIndex(0)
        if hasattr(self, "h_filtro_carrera"):
            self.h_filtro_carrera.setCurrentIndex(0)
        self._cargar_combo_h_materia()
        self.h_materia.setCurrentIndex(0)
        self.h_dia.setCurrentIndex(0)
        self.h_hora_inicio.clear()
        self.h_hora_fin.clear()
        self.h_aula.setCurrentIndex(0)
        self.tabla_horarios.clearSelection()
        desactivar_modo_edicion(self.h_hora_inicio)

    def _cargar_horario_seleccionado(self):

        fila= self.tabla_horarios.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un horario de la tabla.", self)
            return
        id_h= int(self.tabla_horarios.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM horarios WHERE id=?", (id_h,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion_horario= f["id"]
        preseleccionar_curso_y_seccion(self.h_curso, self.h_seccion, f["seccion_id"], incluir_todas=False)
        idx_mat= self.h_materia.findData(f["materia_id"])
        self.h_materia.setCurrentIndex(idx_mat if idx_mat >= 0 else 0)
        self.h_dia.setCurrentText(f["dia"] or DIAS[0])
        self.h_hora_inicio.setText(f["hora_inicio"] or "")
        self.h_hora_fin.setText(f["hora_fin"] or "")
        idx_aula= self.h_aula.findData(f["aula_id"])
        self.h_aula.setCurrentIndex(idx_aula if idx_aula >= 0 else 0)
        activar_modo_edicion(self.h_hora_inicio, "Editando franja de horario")

    def _guardar_horario(self):

        if self.h_curso.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona el curso/grado.", self)
            return
        if self.h_seccion.currentData() is None or self.h_materia.currentData() is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona sección y materia.", self)
            return
        dia= self.h_dia.currentText()
        hora_inicio_txt= self.h_hora_inicio.text().strip()
        hora_fin_txt= self.h_hora_fin.text().strip()
        try:

            nuevo_inicio= _minutos(hora_inicio_txt)
            nuevo_fin= _minutos(hora_fin_txt)
        except ValueError:
            mostrar_mensaje("advertencia", "Hora inválida",
                           "Ingresa las horas en formato HH:MM (ej. 08:00).", self)
            return
        if nuevo_fin <= nuevo_inicio:
            mostrar_mensaje("advertencia", "Rango inválido",
                           "La hora de fin debe ser posterior a la hora de inicio.", self)
            return
        materia_id= self.h_materia.currentData()
        aula_id= self.h_aula.currentData()
        conflicto= self._detectar_conflicto_horario(dia, nuevo_inicio, nuevo_fin, materia_id, aula_id,
                                                       excluir_id= self.id_edicion_horario)
        if conflicto:
            mostrar_mensaje("advertencia", "Cruce de horario detectado", conflicto, self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        if self.id_edicion_horario is None:
            c.execute("""INSERT INTO horarios (seccion_id, materia_id, dia, hora_inicio, hora_fin, aula_id)
                         VALUES (?,?,?,?,?,?)""",
                      (self.h_seccion.currentData(), materia_id, dia, hora_inicio_txt, hora_fin_txt, aula_id))
            accion= "Asignó horario"
        else:
            c.execute("""UPDATE horarios SET seccion_id=?, materia_id=?, dia=?, hora_inicio=?, hora_fin=?,
                         aula_id= ? WHERE id=?""",
                      (self.h_seccion.currentData(), materia_id, dia, hora_inicio_txt, hora_fin_txt, aula_id,
                       self.id_edicion_horario))
            accion= "Editó horario"
        conn.commit()
        conn.close()
        registrar_auditoria("Horarios", accion, self.main_window.usuario_actual,
                            f"{dia} {hora_inicio_txt}-{hora_fin_txt}")
        self._limpiar_horario_form()
        self.refrescar()

    def _detectar_conflicto_horario(self, dia, nuevo_inicio, nuevo_fin, materia_id, aula_id, excluir_id=None):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT horarios.id, horarios.hora_inicio, horarios.hora_fin, horarios.aula_id,
                     materias.id as materia_id, materias.nombre as materia_nombre,
                     materias.profesor_id, (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as profesor_nombre,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre, aulas.nombre as aula_nombre
                     FROM horarios
                     LEFT JOIN materias ON horarios.materia_id = materias.id
                     LEFT JOIN profesores ON materias.profesor_id = profesores.id
                     LEFT JOIN secciones ON horarios.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN aulas ON horarios.aula_id = aulas.id
                     WHERE horarios.dia=?""", (dia,))
        filas= c.fetchall()
        conn.close()
        conn2= obtener_conexion()
        c2= conn2.cursor()
        c2.execute("SELECT profesor_id FROM materias WHERE id=?", (materia_id,))
        fila_prof= c2.fetchone()
        conn2.close()
        nuevo_profesor_id= fila_prof["profesor_id"] if fila_prof else None
        for fila in filas:
            if excluir_id is not None and fila["id"] == excluir_id:
                continue
            try:

                existente_inicio= _minutos(fila["hora_inicio"])
                existente_fin= _minutos(fila["hora_fin"])
            except (ValueError, TypeError, AttributeError):
                continue
            if not _se_solapan(nuevo_inicio, nuevo_fin, existente_inicio, existente_fin):
                continue
            if nuevo_profesor_id is not None and fila["profesor_id"] == nuevo_profesor_id:
                return (f"El profesor '{fila['profesor_nombre'].strip()}' ya tiene clase de "
                        f"'{fila['materia_nombre']}' en {fila['seccion_nombre']} el {dia} de "
                        f"{formatear_hora(fila['hora_inicio'], self.main_window)} a "
                        f"{formatear_hora(fila['hora_fin'], self.main_window)}.")
            if aula_id is not None and fila["aula_id"] == aula_id:
                return (f"El aula '{fila['aula_nombre']}' ya está ocupada el {dia} de "
                        f"{formatear_hora(fila['hora_inicio'], self.main_window)} a "
                        f"{formatear_hora(fila['hora_fin'], self.main_window)} por '{fila['materia_nombre']}' "
                        f"en {fila['seccion_nombre']}.")
        return None

    def _eliminar_horario(self):

        fila= self.tabla_horarios.currentRow()
        if fila < 0:
            return
        id_h= int(self.tabla_horarios.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM horarios WHERE id=?", (id_h,))
        conn.commit()
        conn.close()
        registrar_auditoria("Horarios", "Eliminó horario", self.main_window.usuario_actual, str(id_h))
        self.refrescar()

    #Cascada del combo 'Curso/Grado' de la ventana de FILTROS de Horarios
    #(no confundir con self.h_curso, el del formulario 'Asignar Clase').
    def _al_cambiar_filtro_curso_horarios(self):

        cascada_seccion_por_curso(self.filtro_horarios_curso, self.filtro_horarios_seccion, incluir_todas=True)
        self._filtro_horarios_cambio()

    def _filtro_horarios_cambio(self):

        self.paginacion_horarios.reiniciar()
        self._cargar_horarios()

    def _cargar_horarios(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT horarios.*, grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                     materias.nombre as materia_nombre, aulas.nombre as aula_nombre
                     FROM horarios
                     LEFT JOIN secciones ON horarios.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN materias ON horarios.materia_id = materias.id
                     LEFT JOIN aulas ON horarios.aula_id = aulas.id
                     ORDER BY horarios.dia, horarios.hora_inicio""")
        filas= c.fetchall()
        conn.close()

        #El gráfico de ocupación siempre refleja el TOTAL real (sin filtro de búsqueda), para que siga siendo un
        #resumen fiable de toda la oferta.
        conteos_por_dia= {}
        for f in filas:
            conteos_por_dia[f["dia"]]= conteos_por_dia.get(f["dia"], 0) + 1
        self.grafico_ocupacion.poner_datos([(dia, conteos_por_dia.get(dia, 0)) for dia in DIAS], "#3B82F6")

        seccion_filtro= self.filtro_horarios_seccion.currentData() if hasattr(self, "filtro_horarios_seccion") else None
        if seccion_filtro is not None:
            filas= [fila for fila in filas if fila["seccion_id"] == seccion_filtro]
        dia_filtro= self.filtro_horarios_dia.currentData() if hasattr(self, "filtro_horarios_dia") else None
        if dia_filtro:
            filas= [fila for fila in filas if fila["dia"] == dia_filtro]
        texto= _normalizar(self.busq_horarios.text().strip())
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['grado_nombre']} {fila['seccion_nombre']} {fila['materia_nombre']} {fila['dia']} {fila['aula_nombre']}")]

        self.paginacion_horarios.establecer_total(len(filas))
        inicio, fin= self.paginacion_horarios.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_horarios):
            self.tabla_horarios.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_horarios.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_horarios.setItem(i, 1, QTableWidgetItem(f["grado_nombre"] or ""))
                self.tabla_horarios.setItem(i, 2, QTableWidgetItem(f["seccion_nombre"] or ""))
                self.tabla_horarios.setItem(i, 3, QTableWidgetItem(f["materia_nombre"] or ""))
                self.tabla_horarios.setItem(i, 4, QTableWidgetItem(f["dia"] or ""))
                self.tabla_horarios.setItem(i, 5, QTableWidgetItem(
                    f"{formatear_hora(f['hora_inicio'], self.main_window)} - "
                    f"{formatear_hora(f['hora_fin'], self.main_window)}"))
                self.tabla_horarios.setItem(i, 6, QTableWidgetItem(f["aula_nombre"] or ""))
            ajustar_anchos_columnas(self.tabla_horarios)

    def _tab_asignaciones(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)
        lbl_desc= QLabel("Asigna co-docentes a una materia académica (además del profesor titular definido en "
                       "la pestaña 'Materias'): auxiliares, suplentes, etc. Estos profesores también verán la "
                       "materia, sus estudiantes y su horario en su Modo Docente, y pueden recibir su propio "
                       "paquete individual exportado desde Configuración ▸ Seguridad. Para asignar varios "
                       "profesores a un Módulo Técnico, usa la pestaña 'Profesores por Módulo' del módulo"
                       "Politécnico.")
        lbl_desc.setObjectName("DescModulo")
        lbl_desc.setWordWrap(True)
        disposicion.addWidget(lbl_desc)
        frame_form, form= self._tarjeta_formulario("Nueva Asignación")
        self.ap_materia= QComboBox()
        conectar_tooltip_seleccion(self.ap_materia, "Materia académica a la que se asigna este co-docente")
        #Igual que en Horarios: primero se elige el Grado/Curso (opcional) y eso acota las opciones de Sección, en vez
        #de mezclar todas las secciones de todos los grados en un solo combo largo.
        self.ap_curso= QComboBox()
        self.ap_curso.currentIndexChanged.connect(self._al_cambiar_curso_asignacion)
        self.ap_seccion= QComboBox()
        self.ap_profesor= QComboBox()
        conectar_tooltip_seleccion(self.ap_profesor, "Profesor que se asigna como co-docente")
        self.ap_tipo= QComboBox()
        self.ap_tipo.addItems(["Auxiliar", "Suplente", "Co-titular", "Practicante"])
        conectar_tooltip_seleccion(self.ap_tipo, "Rol del co-docente en esta materia/sección")
        form.addWidget(QLabel("Materia:"), 0, 0)
        form.addWidget(self.ap_materia, 0, 1)
        form.addWidget(QLabel("Profesor:"), 0, 2)
        form.addWidget(self.ap_profesor, 0, 3)
        form.addWidget(QLabel("Grado/Curso (opcional):"), 1, 0)
        form.addWidget(self.ap_curso, 1, 1)
        form.addWidget(QLabel("Sección (opcional):"), 1, 2)
        form.addWidget(self.ap_seccion, 1, 3)
        form.addWidget(QLabel("Tipo de asignación:"), 2, 0)
        form.addWidget(self.ap_tipo, 2, 1)
        btn_guardar= QPushButton("Asignar Co-Docente")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar_asignacion)
        self.btn_guardar_asignacion= btn_guardar  #referencia: cambia a "Actualizar" al editar
        form.addWidget(btn_guardar, 3, 0)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar.setObjectName("BtnAccionNeutro")
        btn_limpiar.clicked.connect(self._limpiar_asignacion)
        form.addWidget(btn_limpiar, 3, 1)

        #Área Técnica (Politécnico) / Carrera (Universidad): en SU PROPIA fila, con aire alrededor, nunca apretados
        #junto a Materia/ Profesor/Curso/Sección. Van ANTES del formulario (se eligen primero). Solo acotan "Sección" a
        #esa área técnica o a las que tienen estudiantes de esa carrera (Materia no se acota aquí: esta pestaña ya
        #excluye los módulos técnicos por diseño — solo asigna co-docentes a materias académicas).
        frame_filtro_tecnico_asignacion= QFrame()
        frame_filtro_tecnico_asignacion.setObjectName("CuadroFiltroTecnico")
        frame_filtro_tecnico_asignacion.setStyleSheet(
            "QFrame#CuadroFiltroTecnico { background: rgba(99, 102, 241, 0.06); "
            "border: 1px solid rgba(99, 102, 241, 0.18); border-radius: 10px; }")
        fila_filtro_tecnico_asignacion= QHBoxLayout(frame_filtro_tecnico_asignacion)
        fila_filtro_tecnico_asignacion.setContentsMargins(14, 10, 14, 10)
        fila_filtro_tecnico_asignacion.setSpacing(16)
        self.lbl_filtro_especialidad_asignacion= QLabel("Área Técnica:")
        self.ap_filtro_especialidad= QComboBox()
        self.ap_filtro_especialidad.setToolTip("Acota 'Sección' a esta área técnica (Politécnico)")
        self.ap_filtro_especialidad.setMinimumWidth(210)
        conectar_tooltip_seleccion(self.ap_filtro_especialidad, "Acota 'Sección' a esta área técnica (Politécnico)")
        self.ap_filtro_especialidad.currentIndexChanged.connect(self._al_cambiar_curso_asignacion)
        fila_filtro_tecnico_asignacion.addWidget(self.lbl_filtro_especialidad_asignacion)
        fila_filtro_tecnico_asignacion.addWidget(self.ap_filtro_especialidad)

        self.lbl_filtro_carrera_asignacion= QLabel("Carrera:")
        self.ap_filtro_carrera= QComboBox()
        self.ap_filtro_carrera.setToolTip(
            "Acota 'Sección' a las que tienen estudiantes de esta carrera (Universidad)")
        self.ap_filtro_carrera.setMinimumWidth(210)
        conectar_tooltip_seleccion(self.ap_filtro_carrera,
            "Acota 'Sección' a las que tienen estudiantes de esta carrera (Universidad)")
        self.ap_filtro_carrera.currentIndexChanged.connect(self._al_cambiar_curso_asignacion)
        fila_filtro_tecnico_asignacion.addWidget(self.lbl_filtro_carrera_asignacion)
        fila_filtro_tecnico_asignacion.addWidget(self.ap_filtro_carrera)
        fila_filtro_tecnico_asignacion.addStretch()
        self._envolver_en_panel(disposicion, "Nueva Asignación", frame_filtro_tecnico_asignacion, frame_form)

        frame_resultados, lr= self._tarjeta_resultados()
        barra_busqueda, self.busq_asignaciones= self._barra_busqueda(
            "Buscar por materia, sección, profesor o tipo…", self._filtro_asignaciones_cambio)

        #--- Ventana de filtros (Tipo de asignación) ---
        self.filtro_asignaciones_tipo= QComboBox()
        self.filtro_asignaciones_tipo.addItem("Todos los tipos", None)
        for tipo in ["Auxiliar", "Suplente", "Co-titular", "Practicante"]:
            self.filtro_asignaciones_tipo.addItem(tipo, tipo)
        self.filtro_asignaciones_tipo.currentIndexChanged.connect(self._filtro_asignaciones_cambio)
        conectar_tooltip_seleccion(self.filtro_asignaciones_tipo, "Filtrar la lista por tipo de asignación del co-docente")
        self.dialogo_filtros_asignaciones= self._construir_dialogo_filtros("Filtros de Co-Docentes", [
            ("Tipo de asignación:", self.filtro_asignaciones_tipo),
        ])
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._agregar_boton_filtros(barra_busqueda, lambda: self._abrir_dialogo(self.dialogo_filtros_asignaciones))
        lr.addWidget(barra_busqueda)


        self.tabla_asignaciones= QTableWidget(0, 6)
        aplicar_estructura_tabla(self.tabla_asignaciones)

        self.tabla_asignaciones.setHorizontalHeaderLabels(
            ["ID", "Materia", "Grado", "Sección", "Profesor", "Tipo"])
        self.tabla_asignaciones.setColumnHidden(0, True)
        header= self.tabla_asignaciones.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_asignaciones.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_asignaciones.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla_asignaciones.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_asignaciones.setAlternatingRowColors(True)
        self.tabla_asignaciones.setWordWrap(True)
        self.tabla_asignaciones.setMinimumHeight(220)
        self.tabla_asignaciones.verticalHeader().setVisible(False)
        lr.addWidget(self.tabla_asignaciones, 1)

        self.paginacion_asignaciones= ControlPaginacion()
        self.paginacion_asignaciones.cambio.connect(self._cargar_asignaciones)
        lr.addWidget(self.paginacion_asignaciones)

        agregar_boton_pantalla_completa(
            None, [self.tabla_asignaciones, self.paginacion_asignaciones],
            titulo= "Co-Docentes", parent=self)

        fila_botones= QHBoxLayout()
        btn_actualizar= QPushButton("Actualizar")
        btn_actualizar.setIcon(icono_emoji("🔄"))
        btn_actualizar.setIconSize(_QSize_emoji(16, 16))
        btn_actualizar.setObjectName("BtnAccionNeutro")
        btn_actualizar.clicked.connect(self._cargar_asignaciones)
        fila_botones.addWidget(btn_actualizar)
        btn_cargar= QPushButton("Cargar Seleccionada")
        btn_cargar.setIcon(icono_emoji("✏"))
        btn_cargar.setIconSize(_QSize_emoji(16, 16))
        btn_cargar.setObjectName("BtnAccionEditar")
        btn_cargar.setToolTip("Carga la asignación seleccionada en el formulario para editarla")
        btn_cargar.clicked.connect(self._cargar_asignacion_seleccionada)
        fila_botones.addWidget(btn_cargar)
        btn_eliminar= QPushButton("Eliminar Asignación")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_asignacion)
        fila_botones.addWidget(btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla_asignaciones, self,
                                           titulo= "Detalle de la Asignación")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_asignaciones.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_botones.addStretch()
        lr.addLayout(fila_botones)
        lr.addStretch()
        disposicion.addWidget(frame_resultados, 1)
        return contenedor

    def _al_cambiar_curso_asignacion(self, _indice=None, seccion_id_preseleccionar=None):

        cascada_seccion_por_curso(self.ap_curso, self.ap_seccion, incluir_todas=False)

        especialidad_id= self.ap_filtro_especialidad.currentData() if self._es_politecnico() else None
        carrera_id= self.ap_filtro_carrera.currentData() if self._es_universidad() else None
        if especialidad_id is not None or carrera_id is not None:
            secciones_carrera= None
            if carrera_id is not None:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("""SELECT DISTINCT seccion_id FROM estudiantes
                             WHERE carrera_id=? AND estado='Activo' AND seccion_id IS NOT NULL""", (carrera_id,))
                secciones_carrera= {fila["seccion_id"] for fila in c.fetchall()}
                conn.close()
            actual= self.ap_seccion.currentData()
            for i in range(self.ap_seccion.count() - 1, 0, -1):
                seccion_id= self.ap_seccion.itemData(i)
                if seccion_id is None:
                    continue
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT especialidad_id FROM secciones WHERE id=?", (seccion_id,))
                fila_sec= c.fetchone()
                conn.close()
                especialidad_seccion= fila_sec["especialidad_id"] if fila_sec else None
                if especialidad_id is not None and especialidad_seccion != especialidad_id:
                    self.ap_seccion.removeItem(i)
                    continue
                if secciones_carrera is not None and seccion_id not in secciones_carrera:
                    self.ap_seccion.removeItem(i)
            idx= self.ap_seccion.findData(actual)
            self.ap_seccion.setCurrentIndex(idx if idx >= 0 else 0)

        if seccion_id_preseleccionar is not None:
            idx= self.ap_seccion.findData(seccion_id_preseleccionar)
            self.ap_seccion.setCurrentIndex(idx if idx >= 0 else 0)

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera de
    #'Asignar Profesor' solo se muestran/pueblan si la institución tiene
    #ese módulo activo.
    def _cargar_filtro_tecnico_asignacion(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_asignacion.setVisible(es_poli)
        self.ap_filtro_especialidad.setVisible(es_poli)
        if es_poli:
            actual= self.ap_filtro_especialidad.currentData()
            self.ap_filtro_especialidad.blockSignals(True)
            self.ap_filtro_especialidad.clear()
            self.ap_filtro_especialidad.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.ap_filtro_especialidad.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.ap_filtro_especialidad.findData(actual)
            self.ap_filtro_especialidad.setCurrentIndex(idx if idx >= 0 else 0)
            self.ap_filtro_especialidad.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_asignacion.setVisible(es_uni)
        self.ap_filtro_carrera.setVisible(es_uni)
        if es_uni:
            actual= self.ap_filtro_carrera.currentData()
            self.ap_filtro_carrera.blockSignals(True)
            self.ap_filtro_carrera.clear()
            self.ap_filtro_carrera.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.ap_filtro_carrera.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.ap_filtro_carrera.findData(actual)
            self.ap_filtro_carrera.setCurrentIndex(idx if idx >= 0 else 0)
            self.ap_filtro_carrera.blockSignals(False)

    def _limpiar_asignacion(self):

        self.ap_materia.setCurrentIndex(0)
        if hasattr(self, "ap_filtro_especialidad"):
            self.ap_filtro_especialidad.setCurrentIndex(0)
        if hasattr(self, "ap_filtro_carrera"):
            self.ap_filtro_carrera.setCurrentIndex(0)
        self.ap_curso.setCurrentIndex(0)
        self.ap_seccion.setCurrentIndex(0)
        self.ap_profesor.setCurrentIndex(0)
        self.ap_tipo.setCurrentIndex(0)
        self.tabla_asignaciones.clearSelection()
        #Sale del modo edición (si estaba editando una asignación)
        self._id_asignacion_editando= None
        if hasattr(self, "btn_guardar_asignacion"):
            self.btn_guardar_asignacion.setText("Asignar Co-Docente")

    #Carga la asignación de co-docente seleccionada en el formulario
    #(arriba) para poder editarla y guardarla con 'Actualizar'.
    def _cargar_asignacion_seleccionada(self):

        fila= self.tabla_asignaciones.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una asignación de la tabla.", self)
            return
        id_asig= int(self.tabla_asignaciones.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT mp.materia_id, mp.profesor_id, mp.seccion_id, mp.tipo_asignacion,
                            secciones.grado_id
                     FROM materia_profesores mp
                     LEFT JOIN secciones ON secciones.id = mp.seccion_id
                     WHERE mp.id=?""", (id_asig,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if f is None:
            mostrar_mensaje("advertencia", "No encontrada",
                            "Esta asignación ya no existe (quizá se eliminó desde otro equipo).", self)
            return
        self._id_asignacion_editando= id_asig
        self.ap_materia.blockSignals(True)
        idx_m= self.ap_materia.findData(f["materia_id"])
        self.ap_materia.setCurrentIndex(idx_m if idx_m >= 0 else 0)
        self.ap_materia.blockSignals(False)
        #Curso/Sección en cascada: primero el grado de la sección (repopulate el combo de secciones) y luego la sección
        #exacta.
        self.ap_curso.blockSignals(True)
        idx_g= self.ap_curso.findData(f["grado_id"]) if f["grado_id"] is not None else 0
        self.ap_curso.setCurrentIndex(idx_g if idx_g >= 0 else 0)
        self.ap_curso.blockSignals(False)
        self._al_cambiar_curso_asignacion(seccion_id_preseleccionar=f["seccion_id"])
        idx_p= self.ap_profesor.findData(f["profesor_id"])
        self.ap_profesor.setCurrentIndex(idx_p if idx_p >= 0 else 0)
        idx_t= self.ap_tipo.findText(f["tipo_asignacion"] or "Auxiliar")
        self.ap_tipo.setCurrentIndex(idx_t if idx_t >= 0 else 0)
        if hasattr(self, "btn_guardar_asignacion"):
            self.btn_guardar_asignacion.setText("Actualizar Asignación")
        #Abre el panel colapsable del formulario (de golpe) y lleva la vista hasta él con el banner "Editando..." —
        #mismo feedback que el resto de pestañas/módulos.
        activar_modo_edicion(self.ap_materia, f"Editando asignación #{id_asig}")

    def _guardar_asignacion(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede asignar co-docentes.", self)
            return
        materia_id= self.ap_materia.currentData()
        profesor_id= self.ap_profesor.currentData()
        if materia_id is None or profesor_id is None:
            mostrar_mensaje("advertencia", "Datos incompletos", "Selecciona la materia y el profesor.", self)
            return
        seccion_id= self.ap_seccion.currentData()
        tipo= self.ap_tipo.currentText()
        editando= getattr(self, "_id_asignacion_editando", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id FROM materia_profesores
                     WHERE materia_id=? AND profesor_id=? AND id IS NOT ?
                     AND (seccion_id=? OR (seccion_id IS NULL AND ? IS NULL))""",
                  (materia_id, profesor_id, editando, seccion_id, seccion_id))
        if c.fetchone():
            conn.close()
            mostrar_mensaje("advertencia", "Ya existe",
                           "Ese profesor ya está asignado a esta materia (y sección).", self)
            return
        if editando is not None:
            c.execute("""UPDATE materia_profesores
                         SET materia_id=?, profesor_id=?, seccion_id=?, tipo_asignacion=?
                         WHERE id=?""", (materia_id, profesor_id, seccion_id, tipo, editando))
            detalle_aud= f"#{editando}: {self.ap_profesor.currentText()} -> {self.ap_materia.currentText()} ({tipo})"
        else:
            c.execute("""INSERT INTO materia_profesores (materia_id, profesor_id, seccion_id, tipo_asignacion)
                         VALUES (?,?,?,?)""", (materia_id, profesor_id, seccion_id, tipo))
            detalle_aud= f"{self.ap_profesor.currentText()} -> {self.ap_materia.currentText()} ({tipo})"
        conn.commit()
        conn.close()
        registrar_auditoria("Materias",
                            "Editó asignación de co-docente" if editando is not None else "Asignó co-docente",
                            self.main_window.usuario_actual, detalle_aud)
        if editando is not None:
            mostrar_mensaje("exito", "Actualizada", "La asignación se actualizó correctamente.", self)
        else:
            mostrar_mensaje("exito", "Asignado", "El co-docente se asignó correctamente.", self)
        self._limpiar_asignacion()
        self._cargar_asignaciones()

    def _eliminar_asignacion(self):

        fila= self.tabla_asignaciones.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una asignación de la tabla.", self)
            return
        id_asig= int(self.tabla_asignaciones.item(fila, 0).text())
        if mostrar_mensaje("pregunta", "Confirmar", "¿Eliminar esta asignación de co-docente?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM materia_profesores WHERE id=?", (id_asig,))
        conn.commit()
        conn.close()
        registrar_auditoria("Materias", "Eliminó asignación de co-docente", self.main_window.usuario_actual, str(id_asig))
        self._cargar_asignaciones()

    def _filtro_asignaciones_cambio(self):

        self.paginacion_asignaciones.reiniciar()
        self._cargar_asignaciones()

    def _cargar_asignaciones(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT materia_profesores.id, materias.nombre as materia_nombre,
                     grados.nombre as grado_nombre, secciones.nombre as seccion_nombre,
                     (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as profesor_nombre,
                     materia_profesores.tipo_asignacion
                     FROM materia_profesores
                     LEFT JOIN materias ON materia_profesores.materia_id = materias.id
                     LEFT JOIN secciones ON materia_profesores.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN profesores ON materia_profesores.profesor_id = profesores.id
                     WHERE materias.modelo_evaluacion IS NULL OR materias.modelo_evaluacion != 'Técnica (RA)'
                     ORDER BY materias.nombre""")
        filas= c.fetchall()
        conn.close()
        tipo_filtro= self.filtro_asignaciones_tipo.currentData() if hasattr(self, "filtro_asignaciones_tipo") else None
        if tipo_filtro:
            filas= [fila for fila in filas if fila["tipo_asignacion"] == tipo_filtro]
        texto= _normalizar(self.busq_asignaciones.text().strip())
        if texto:
            filas= [fila for fila in filas if texto in _normalizar(
                f"{fila['materia_nombre']} {fila['grado_nombre'] or ''} {fila['seccion_nombre'] or 'Todas sus secciones'} "
                f"{fila['profesor_nombre']} {fila['tipo_asignacion']}")]
        self.paginacion_asignaciones.establecer_total(len(filas))
        inicio, fin= self.paginacion_asignaciones.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_asignaciones):
            self.tabla_asignaciones.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                self.tabla_asignaciones.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                self.tabla_asignaciones.setItem(i, 1, QTableWidgetItem(f["materia_nombre"] or ""))
                self.tabla_asignaciones.setItem(i, 2, QTableWidgetItem(f["grado_nombre"] or ""))
                self.tabla_asignaciones.setItem(i, 3, QTableWidgetItem(f["seccion_nombre"] or "Todas"))
                self.tabla_asignaciones.setItem(i, 4, QTableWidgetItem(f["profesor_nombre"] or ""))
                item_tipo= QTableWidgetItem(f["tipo_asignacion"] or "")
                _colorear_texto(item_tipo, _COLORES_TIPO_ASIGNACION.get(f["tipo_asignacion"], "#94A3B8"))
                self.tabla_asignaciones.setItem(i, 5, item_tipo)
            ajustar_anchos_columnas(self.tabla_asignaciones)

    def _cargar_combos(self):

        conn= obtener_conexion()
        c= conn.cursor()
        self.s_especialidad.clear()
        self.s_especialidad.addItem("— Selecciona un área técnica —" if self._es_politecnico() else "Sin área técnica", None)
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            self.s_especialidad.addItem(fila["nombre"], fila["id"])
        self.s_carrera.clear()
        self.s_carrera.addItem("Sin carrera", None)
        c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
        for fila in c.fetchall():
            self.s_carrera.addItem(fila["nombre"], fila["id"])
        for combo in (self.m_profesor, self.s_profesor_guia):
            combo.clear()
            combo.addItem("Sin asignar", None)
        c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre")
        for fila in c.fetchall():
            texto= f"{fila['nombre']} {fila['apellidos'] or ''}".strip()
            self.m_profesor.addItem(texto, fila["id"])
            self.s_profesor_guia.addItem(texto, fila["id"])
        if hasattr(self, "filtro_materias_profesor"):
            seleccion_previa= self.filtro_materias_profesor.currentData()
            self.filtro_materias_profesor.blockSignals(True)
            self.filtro_materias_profesor.clear()
            self.filtro_materias_profesor.addItem("Todos los profesores", None)
            c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre")
            for fila in c.fetchall():
                self.filtro_materias_profesor.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
            idx_fp= self.filtro_materias_profesor.findData(seleccion_previa)
            self.filtro_materias_profesor.setCurrentIndex(idx_fp if idx_fp >= 0 else 0)
            self.filtro_materias_profesor.blockSignals(False)
        for combo in (self.s_aula, self.h_aula):
            combo.clear()
            combo.addItem("Sin asignar", None)
        c.execute("SELECT id, nombre FROM aulas ORDER BY nombre")
        for fila in c.fetchall():
            self.s_aula.addItem(fila["nombre"], fila["id"])
            self.h_aula.addItem(fila["nombre"], fila["id"])
        curso_previo= self.h_curso.currentData()
        poblar_combo_curso(self.h_curso, incluir_todos=False, seleccion_previa=curso_previo)
        self._cargar_filtro_tecnico_horario()
        self._al_cambiar_curso_horario()
        self._cargar_combo_h_materia()
        if hasattr(self, "filtro_horarios_curso"):
            poblar_combo_curso(self.filtro_horarios_curso, incluir_todos=True)
            cascada_seccion_por_curso(self.filtro_horarios_curso, self.filtro_horarios_seccion, incluir_todas=True)
        self.ap_materia.clear()
        #Los módulos técnicos (modelo_evaluacion='Técnica (RA)') se excluyen: sus
        #co-docentes se asignan desde la pestaña "👨🏫 Profesores por Módulo" del módulo Politécnico, para no tener dos
        #lugares distintos haciendo lo mismo.
        c.execute("""SELECT id, nombre FROM materias
                     WHERE modelo_evaluacion IS NULL OR modelo_evaluacion != 'Técnica (RA)'
                     ORDER BY nombre""")
        for fila in c.fetchall():
            self.ap_materia.addItem(fila["nombre"], fila["id"])
        curso_previo_ap= self.ap_curso.currentData()
        poblar_combo_curso(self.ap_curso, incluir_todos=False, seleccion_previa=curso_previo_ap)
        self._cargar_filtro_tecnico_asignacion()
        self._al_cambiar_curso_asignacion()
        self.ap_profesor.clear()
        c.execute("SELECT id, nombre, apellidos FROM profesores WHERE estado='Activo' ORDER BY nombre")
        for fila in c.fetchall():
            self.ap_profesor.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
        conn.close()

    def refrescar(self):

        self._actualizar_visibilidad_modelo_evaluacion()
        #Igual que ya hace Estudiantes (tabla.setColumnHidden 7/8 según _es_politecnico/_es_universidad): en una
        #institución que no es Politécnico ni Universidad (p. ej. una Escuela normal, o un Personalizado sin esos
        #módulos) las columnas "Área Técnica" y "Carrera" de la tabla de Secciones no aportan nada -solo mostrarían "—"
        #en todas las filas- así que se ocultan por completo en vez de dejarlas visibles y vacías.
        self.tabla_secciones.setColumnHidden(5, not self._es_politecnico())
        self.tabla_secciones.setColumnHidden(6, not self._es_universidad())
        if hasattr(self, "combo_filtro_nivel_seccion"):
            poblar_combo_nivel_educativo(self.combo_filtro_nivel_seccion)
        self._cargar_combos()
        self._cargar_materias()
        self._cargar_secciones()
        self._cargar_aulas()
        self._cargar_horarios()
        self._cargar_asignaciones()
        self._actualizar_kpis()