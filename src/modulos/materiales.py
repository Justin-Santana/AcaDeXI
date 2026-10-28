#Módulo Materiales de AcaDeXI.
#
#Inventario configurable de recursos de la institución: libros, equipos de
#laboratorio, herramientas de talleres técnicos, instrumentos musicales,
#uniformes deportivos... el catálogo de CATEGORÍAS es abierto y lo define
#cada institución (ver categorias_material en bd.py) -no viene una lista
#fija de "tipos de material" precargada por el sistema, porque lo que hace
#único a este módulo es precisamente que no asume de antemano qué necesita
#gestionar cada escuela.
#
#El ÍCONO de cada categoría se elige de un set curado de íconos vectoriales
#(ver iconos_categorias.py ▸ sección 3 "MATERIALES", `pixmap_categoria_material`)
#en vez de escribir un emoji de fuente a mano -por eso el campo `icono` de
#`categorias_material` puede tener una clave curada ("laboratorio", "taller"...)
#o, para categorías creadas antes de que existiera el selector, un emoji
#suelto: `pixmap_categoria_material` entiende ambos casos (ver esa función).
#
#RBAC granular POR USUARIO Y CATEGORÍA (no por rol fijo, ver permisos.py:
#categorias_material_permitidas / puede_editar_categoria_material):
#- Un rol gerencial (Administrador/Director/Coordinador) ve y administra
#SIEMPRE todas las categorías.
#- Cualquier otro usuario con el módulo "Materiales" otorgado (Profesor,
#Administrativo, o un cargo personalizado de Side Stepper) solo ve las
#categorías que se le asignaron explícitamente, y dentro de esas, solo
#puede editar las que se le marcaron con permiso de edición -las demás
#las ve en modo solo-consulta.
#- Ejemplo real: dos Administrativos comparten el mismo rol, pero uno
#tiene acceso de edición solo a "Libros" (bibliotecario) y otro solo a
#"Equipos de Laboratorio" (encargado de laboratorio); ninguno ve ni
#toca la categoría del otro, sin que haga falta inventar un rol nuevo
#por cada especialidad de inventario que tenga la institución.
#
#La asignación de qué categorías puede tocar cada usuario se hace desde
#este mismo módulo, en el botón "Permisos de acceso" (solo visible para
#roles gerenciales) -ver DialogoPermisosMateriales.
from datetime import datetime, date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTextEdit, QFrame, QSpinBox, QTableWidget, QTableWidgetItem, QDialog,
    QDialogButtonBox, QMessageBox, QCheckBox, QScrollArea, QGridLayout, QToolButton,
    QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, QSize as _QSize_emoji

from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, centrar_y_al_frente
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
                         tabla_pausada, agregar_boton_pantalla_completa,
                         agregar_boton_detalle)
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.filtro_vacio import EstadoVacioFiltro
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion
from src.nucleo.iconos_emoji import icono_emoji
from src.nucleo.iconos_categorias import (CATEGORIAS_SUGERIDAS_MATERIAL, icono_categoria_material,
                                pixmap_categoria_material)
from src.interfaz.dashboard import TarjetaIndicador
from src.interfaz.configuracion import conectar_tooltip_seleccion, IconoLupa
from src.modulos.calendario import PanelDesplegable
from src.nucleo.atajos import registrar_atajo
from src.nucleo.permisos import (tiene_acceso_gerencial, categorias_material_permitidas,
                       puede_editar_categoria_material, guardar_permisos_materiales_usuario,
                       obtener_permisos_materiales_usuario)

ESTADOS_MATERIAL= ["Disponible", "Agotado", "En mantenimiento", "De baja"]
TIPOS_MOVIMIENTO= ["Préstamo", "Devolución", "Baja", "Ingreso de inventario"]


#Base de los diálogos de este módulo: garantiza que la ventana se
#abra CENTRADA sobre la ventana principal de la app (igual que las
#ventanas de los demás módulos, ver iconos.centrar_y_al_frente).
#
#centrar_y_al_frente() en el __init__ no siempre basta: si el diálogo
#se construye antes de que su padre esté visible/mapeado, la posición
#se calcula contra la pantalla en vez de contra la ventana principal.
#Re-centrar en el PRIMER showEvent (solo la primera vez, para no pelear
#con el usuario si decide arrastrar la ventana) lo resuelve siempre.
#
#Además aplica el estilo de tooltip de AcaDeXI (panel del tema activo,
#texto primario, borde redondeado): los diálogos son ventanas de nivel
#superior APARTE, así que NO heredan el QToolTip global del módulo/ventana
#principal -sin esto, sus tooltips caían al estilo nativo gris de Qt,
#inconsistente con el resto de la app (mismo problema que ya resolvió
#banco_tareas.py/calendario.py repitiendo el bloque QToolTip adentro).
class _DialogoCentrado(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._centrado_inicial= False
        #Resolver la ventana principal desde el PADRE (no self.window():
        #este diálogo ya es una ventana top-level, así que window() se devolvería a sí mismo). Sube por la cadena de
        #padres hasta dar con el objeto que tenga la paleta del tema (ventana principal o módulo) -cubre también el
        #selector de íconos abierto desde el diálogo de categorías-.
        mw= parent.window() if parent is not None else None
        obj= mw
        while obj is not None and not hasattr(obj, "theme_palettes"):
            obj= obj.parentWidget()
        mw= obj
        if mw is not None and hasattr(mw, "main_window") and not getattr(mw, "theme_palettes", None):
            mw= mw.main_window
        qss= _qss_tooltip_tema(mw)
        if qss:
            self.setStyleSheet(qss)

    def showEvent(self, event):

        super().showEvent(event)
        if not self._centrado_inicial:
            self._centrado_inicial= True
            centrar_y_al_frente(self, self.parent())


#QSS del bloque QToolTip con la paleta del tema/modo activo de la
#app (mismos colores que usa el módulo en actualizar_tema). Devuelve ""
#si no hay paleta disponible (p. ej. pruebas sin main_window): en ese
#caso el diálogo conserva el estilo nativo, sin romper nada.
def _qss_tooltip_tema(main_window):

    mw= main_window
    paletas= getattr(mw, "theme_palettes", None) if mw is not None else None
    if not paletas:
        return ""
    tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
    paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
    if not paleta:
        return ""
    idx= 1 if getattr(mw, "modo_oscuro", True) else 0
    bg_panel= paleta["display_bg"][idx]
    bg_borde= paleta["btn_num_bg"][idx]
    txt_prim= paleta["text_primary"][idx]
    return f"""
        QToolTip {{
            background-color: {bg_panel};
            color: {txt_prim};
            border: 1px solid {bg_borde};
            padding: 6px 10px;
            border-radius: 6px;
        }}
    """


class ModuloMateriales(QWidget):

    def __init__(self, main_window=None, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.material_en_edicion= None
        #Caché de _categorias_visibles() (ver ese método): esta lista se consulta varias veces por cada refresco de
        #tabla (filtros, cada tecla del buscador...) y antes disparaba una consulta a la BD en cada una de esas veces.
        #Ahora se calcula una sola vez por ciclo de refresco -_poblar_combos_categoria() la fuerza a recalcularse
        #cuando de verdad puede haber cambiado (arranque, tras cerrar "Gestionar categorías")- y el resto de este
        #módulo reutiliza el mismo resultado sin volver a tocar la base de datos.
        self._cache_categorias= None
        self.pagina= ControlPaginacion(tamano_inicial=25)
        self.pagina.cambio.connect(self._cargar_tabla)

        #Página envuelta en QScrollArea (mismo patrón que materias.py/ profesores.py): cuando se despliega el
        #formulario de alta/edición, el contenido completo ya no cabe en la altura de la ventana y SIN este scroll Qt
        #aplastaba el formulario en la parte de abajo (campos encimados e ilegibles). Con el scroll, la página crece y
        #se navega verticalmente.
        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout_raiz.addWidget(scroll)
        contenido= QWidget()
        scroll.setWidget(contenido)

        layout= QVBoxLayout(contenido)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        #---------- Cabecera "hero" (mismo patrón que Materias/Observaciones) ----------
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera= QHBoxLayout(self.frame_cabecera)
        cabecera.setContentsMargins(22, 18, 22, 18)
        cabecera.setSpacing(14)

        self.lbl_icono_cabecera= QLabel()
        self.lbl_icono_cabecera.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_cabecera.setFixedSize(46, 46)
        self.lbl_icono_cabecera.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_cabecera, "Materiales", 22)
        cabecera.addWidget(self.lbl_icono_cabecera)

        col_titulos= QVBoxLayout()
        col_titulos.setSpacing(2)
        titulo= QLabel("Materiales")
        titulo.setObjectName("TituloCabeceraModulo")
        col_titulos.addWidget(titulo)
        self.lbl_subtitulo= QLabel("Inventario de recursos de la institución.")
        self.lbl_subtitulo.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo.setWordWrap(True)
        col_titulos.addWidget(self.lbl_subtitulo)
        cabecera.addLayout(col_titulos, 1)

        if self.main_window is not None and tiene_acceso_gerencial(self.main_window):
            btn_categorias= QPushButton("Gestionar categorías")
            btn_categorias.setObjectName("BtnAccionCabecera")
            btn_categorias.setIcon(icono_emoji("🗂"))
            btn_categorias.setIconSize(_QSize_emoji(16, 16))
            btn_categorias.clicked.connect(self._abrir_gestion_categorias)
            cabecera.addWidget(btn_categorias)

            btn_permisos= QPushButton("Permisos de acceso")
            btn_permisos.setObjectName("BtnAccionCabecera")
            btn_permisos.setIcon(icono_emoji("🔑"))
            btn_permisos.setIconSize(_QSize_emoji(16, 16))
            btn_permisos.clicked.connect(self._abrir_permisos_usuarios)
            cabecera.addWidget(btn_permisos)
        layout.addWidget(self.frame_cabecera)

        #---------- KPIs (reutiliza TarjetaIndicador de dashboard.py, igual que Materias: contador animado, tendencia y
        #elevación al pasar el mouse; se recalculan con cada refresco de tabla, según los filtros activos, para que se
        #sientan "vivos" en vez de un total estático) ----------
        fila_kpi= QHBoxLayout()
        fila_kpi.setSpacing(14)
        abre_categorias= self.main_window is not None and tiene_acceso_gerencial(self.main_window)
        self.kpi_total= TarjetaIndicador("📦", "Materiales en inventario", "#6366F1")
        self.kpi_disponibles= TarjetaIndicador("✅", "Unidades disponibles", "#22C55E")
        self.kpi_prestamo= TarjetaIndicador("🔁", "Unidades en préstamo", "#F59E0B")
        self.kpi_categorias= TarjetaIndicador(
            "🗂", "Categorías visibles", "#8B5CF6",
            on_click= self._abrir_gestion_categorias if abre_categorias else None)
        self._tarjetas_kpi= [self.kpi_total, self.kpi_disponibles, self.kpi_prestamo, self.kpi_categorias]
        for tarjeta in self._tarjetas_kpi:
            fila_kpi.addWidget(tarjeta, 1)
        layout.addLayout(fila_kpi)

        #---------- Filtros ----------
        self.tarjeta_filtros= QFrame()
        self.tarjeta_filtros.setObjectName("TarjetaFiltros")
        fila_filtros= QHBoxLayout(self.tarjeta_filtros)
        fila_filtros.setContentsMargins(12, 10, 12, 10)
        fila_filtros.setSpacing(8)

        self.combo_categoria_filtro= QComboBox()
        #Más ancho: nombres largos de categoría ("Equipos de Laboratorio", "Herramientas de Taller"...) se leían
        #cortados.
        self.combo_categoria_filtro.setMinimumWidth(230)
        fila_filtros.addWidget(QLabel("Categoría:"))
        fila_filtros.addWidget(self.combo_categoria_filtro)
        self.combo_categoria_filtro.setToolTip("Filtrar el inventario por una categoría de materiales concreta.")
        self.combo_categoria_filtro.currentIndexChanged.connect(self._refrescar)

        self.combo_estado_filtro= QComboBox()
        self.combo_estado_filtro.addItem("Todos los estados", None)
        for estado in ESTADOS_MATERIAL:
            self.combo_estado_filtro.addItem(estado, estado)
        self.combo_estado_filtro.currentIndexChanged.connect(self._refrescar)
        self.combo_estado_filtro.setToolTip("Filtrar por estado: Disponible, Agotado, En mantenimiento o De baja.")
        self.combo_estado_filtro.setMinimumWidth(190)
        #Mismo mecanismo de tooltips de combos que el resto de módulos (conectar_tooltip_seleccion, ver
        #configuracion.py): tooltip en cada registro de la lista y "Seleccionado: X" en el combo cerrado.
        conectar_tooltip_seleccion(self.combo_estado_filtro,
                                   "Filtrar por estado: Disponible, Agotado, En mantenimiento o De baja")
        fila_filtros.addWidget(QLabel("Estado:"))
        fila_filtros.addWidget(self.combo_estado_filtro)

        #Mismo diseño de búsqueda que el resto de la app (configuracion.py, politecnico.py, personal.py, psicologia.py,
        #observaciones.py, calendario.py, reportes.py...): marco en forma de píldora con la lupa dibujada a mano
        #(IconoLupa) y el campo sin borde por dentro. Antes esta barra usaba BusquedaConDebounce, un QLineEdit genérico
        #envuelto que se veía distinto -sin lupa, con borde propio- al de todos los demás módulos.
        marco_busqueda= QFrame()
        marco_busqueda.setStyleSheet(
            "QFrame { background: rgba(127,127,127,0.10); border-radius: 16px; }")
        lay_busqueda= QHBoxLayout(marco_busqueda)
        lay_busqueda.setContentsMargins(12, 0, 10, 0)
        lay_busqueda.setSpacing(6)
        lay_busqueda.addWidget(IconoLupa())
        self.buscador= QLineEdit()
        limitar_campo_texto(self.buscador, 150)
        self.buscador.setPlaceholderText("Buscar por nombre, código o ubicación…")
        self.buscador.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.buscador, 1)
        #Debounce manual (150ms) en vez de disparar la consulta en cada tecla -mismo intervalo que usa el resto de
        #módulos con este
        #patrón (ver politecnico.py/configuracion.py)-.
        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._refrescar)
        self.buscador.textChanged.connect(lambda _t: self._temporizador_busqueda.start())
        fila_filtros.addWidget(marco_busqueda, stretch=1)
        layout.addWidget(self.tarjeta_filtros)

        #---------- Tabla ----------
        self.tarjeta_tabla= QFrame()
        self.tarjeta_tabla.setObjectName("TarjetaTabla")
        lay_tabla= QVBoxLayout(self.tarjeta_tabla)
        #Márgenes/spacing idénticos a los de psicologia.py/estudiantes.py (TarjetaTabla) para que esta tabla se vea
        #igual que la del resto de módulos.
        lay_tabla.setContentsMargins(18, 16, 18, 14)
        lay_tabla.setSpacing(10)
        fila_cabecera_tabla= QHBoxLayout()
        fila_cabecera_tabla.addStretch()
        #Botón ⛶ que abre filtros + tabla + paginación (los mismos widgets, no una copia) dentro de un diálogo
        #maximizado -ver agregar_boton_pantalla_completa en paginacion.py-, para poder buscar/filtrar con la tabla
        #mucho más grande sin salir del módulo.
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla, [self.tarjeta_filtros, self.tarjeta_tabla, self.pagina],
            titulo= "Materiales", parent=self)
        lay_tabla.addLayout(fila_cabecera_tabla)
        self.tabla= QTableWidget()
        self.tabla.setColumnCount(7)
        self.tabla.setHorizontalHeaderLabels(
            ["Categoría", "Código", "Nombre", "Disponible / Total", "Ubicación", "Estado", "Actualizado"])
        aplicar_estructura_tabla(self.tabla)
        #Comportamiento/visual estándar de todas las tablas de la app:
        #filas enteras seleccionables, sin edición inline, colores alternos, filas de 40px sin la columna vertical de
        #numeración.
        _hdr= self.tabla.horizontalHeader()
        _hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        _hdr.setStretchLastSection(True)
        _hdr.setMinimumSectionSize(50)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.setMinimumHeight(400)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones_accion)
        #La paginación (botones ‹ › y contador de registros) vive FUERA de la tarjeta de la tabla, igual que en
        #observaciones.py: dentro de "TarjetaTabla" parecía parte de la tabla misma.
        lay_tabla.addWidget(self.tabla, 1)
        self.estado_vacio= EstadoVacioFiltro(self.tabla, icono="📦",
                                               texto_filtra_primero= "No tienes categorías de materiales asignadas todavía",
                                               texto_sin_resultados= "No hay materiales con los filtros actuales")
        layout.addWidget(self.tarjeta_tabla, stretch=1)
        layout.addWidget(self.pagina)

        #---------- Botonera ---------- "Nuevo material" ya NO es un botón aparte: ese rol lo cumple el encabezado del
        #panel colapsable de abajo (mismo "cosito" +/- que usan banco_tareas.py/observaciones.py/materias.py para su
        #alta) - un clic ahí despliega el formulario en blanco, sin duplicar la acción en dos lugares distintos de la
        #pantalla.
        fila_botones= QHBoxLayout()
        self.btn_editar= QPushButton("Editar")
        self.btn_editar.setObjectName("BtnAccionEditar")
        self.btn_editar.setIcon(icono_emoji("✏"))
        self.btn_editar.setIconSize(_QSize_emoji(16, 16))
        self.btn_editar.setToolTip("Cargar en el formulario el material seleccionado en la tabla para editarlo.")
        self.btn_editar.clicked.connect(self._cargar_seleccionado_en_formulario)
        fila_botones.addWidget(self.btn_editar)

        self.btn_movimiento= QPushButton("Registrar préstamo / devolución")
        self.btn_movimiento.setIcon(icono_emoji("🔁"))
        self.btn_movimiento.setIconSize(_QSize_emoji(16, 16))
        self.btn_movimiento.setToolTip("Registrar un préstamo, devolución, baja o ingreso de inventario del material seleccionado.")
        self.btn_movimiento.clicked.connect(self._abrir_movimiento)
        fila_botones.addWidget(self.btn_movimiento)

        self.btn_eliminar= QPushButton("Eliminar")
        self.btn_eliminar.setObjectName("BtnAccionEliminar")
        self.btn_eliminar.setIcon(icono_emoji("🗑"))
        self.btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        self.btn_eliminar.setToolTip("Eliminar del inventario el material seleccionado (requiere permiso de edición en su categoría).")
        self.btn_eliminar.clicked.connect(self._eliminar_seleccionado)
        fila_botones.addWidget(self.btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_botones, self.tabla, self, titulo="Detalle del Material")
        self.tabla.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_botones.addStretch()
        layout.addLayout(fila_botones)

        #---------- Formulario ("Nuevo material", colapsable) ---------- Mismo componente que usan banco_tareas.py
        #("Nueva tarea"),
        #observaciones.py ("Nueva observación") y materias.py: empieza
        #cerrado (no le gana protagonismo visual a la tabla) y su propio
        #encabezado -con el mismo ícono circular +/- verde de siempre- es el único punto de entrada para dar de alta un
        #material nuevo.
        self.panel_form_material= PanelDesplegable("Nuevo material")
        #Cada vez que se abre/cierra el panel a mano (clic en su encabezado): si lo que acaba de pasar es un CIERRE, se
        #limpia el formulario -si el usuario estaba editando un material y cerró sin guardar ni pulsar "Limpiar", que
        #la próxima vez que abra el panel encuentre un formulario en blanco y no arrastre por accidente esa edición a
        #medias-; si lo que pasó es una APERTURA, se desplaza el scroll para que el panel completo quede a la vista.
        self.panel_form_material.btn_cabecera.clicked.connect(self._al_alternar_panel_formulario)
        form= self.panel_form_material.cuerpo_layout()

        fila1= QHBoxLayout()
        self.combo_categoria_form= QComboBox()
        #Combo más ancho para que quepan nombres largos de categoría
        self.combo_categoria_form.setMinimumWidth(260)
        self.in_codigo_form= QLineEdit()
        self.in_codigo_form.setPlaceholderText("Código / ISBN / etiqueta interna (opcional)")
        limitar_campo_texto(self.in_codigo_form, 100)
        fila1.addWidget(QLabel("Categoría:"))
        fila1.addWidget(self.combo_categoria_form, 1)
        self.combo_categoria_form.setToolTip("Categoría a la que pertenece el material. Define quién puede verlo y editarlo.")
        form.addLayout(fila1)

        #El Código va DEBAJO del combo de categoría (pedía más ancho y amplitud; compartían una misma fila y se
        #apretaban mutuamente).
        fila_codigo= QHBoxLayout()
        fila_codigo.addWidget(QLabel("Código:"))
        fila_codigo.addWidget(self.in_codigo_form, 1)
        self.in_codigo_form.setToolTip("Código, ISBN o etiqueta interna para identificar el material (opcional).")
        form.addLayout(fila_codigo)

        self.in_nombre_form= QLineEdit()
        self.in_nombre_form.setPlaceholderText("Nombre del material")
        limitar_campo_texto(self.in_nombre_form, 200)
        form.addWidget(QLabel("Nombre:"))
        form.addWidget(self.in_nombre_form)

        self.txt_descripcion_form= QTextEdit()
        self.txt_descripcion_form.setPlaceholderText("Descripción, autor, marca/modelo, condición, etc. (opcional)")
        limitar_campo_texto(self.txt_descripcion_form, 3000)
        self.txt_descripcion_form.setMinimumHeight(70)
        form.addWidget(QLabel("Descripción:"))
        form.addWidget(self.txt_descripcion_form)

        fila2= QHBoxLayout()
        self.spin_total_form= QSpinBox()
        self.spin_total_form.setRange(0, 100000)
        self.spin_total_form.setValue(1)
        self.spin_total_form.valueChanged.connect(self._sincronizar_disponible_maximo)
        self.spin_disponible_form= QSpinBox()
        self.spin_disponible_form.setRange(0, 100000)
        self.spin_disponible_form.setValue(1)
        self.in_ubicacion_form= QLineEdit()
        self.in_ubicacion_form.setPlaceholderText("Ej. Biblioteca - Estante 3, Taller de Electricidad")
        limitar_campo_texto(self.in_ubicacion_form, 150)
        self.combo_estado_form= QComboBox()
        for estado in ESTADOS_MATERIAL:
            self.combo_estado_form.addItem(estado, estado)
        fila2.addWidget(QLabel("Cantidad total:"))
        fila2.addWidget(self.spin_total_form)
        self.spin_total_form.setToolTip("Número total de unidades de este material en el inventario.")
        fila2.addWidget(QLabel("Disponible:"))
        fila2.addWidget(self.spin_disponible_form)
        self.spin_disponible_form.setToolTip("Unidades disponibles ahora mismo (no prestadas ni dadas de baja).")
        fila2.addWidget(QLabel("Estado:"))
        fila2.addWidget(self.combo_estado_form)
        self.combo_estado_form.setToolTip("Situación general del material en el inventario.")
        conectar_tooltip_seleccion(self.combo_estado_form,
                                   "Situación general del material en el inventario")
        form.addLayout(fila2)
        form.addWidget(QLabel("Ubicación:"))
        form.addWidget(self.in_ubicacion_form)

        fila_botones_form= QHBoxLayout()
        btn_guardar_form= QPushButton("Guardar material")
        btn_guardar_form.setObjectName("BtnAccionAgregar")
        btn_guardar_form.setIcon(icono_emoji("💾"))
        btn_guardar_form.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_form.setToolTip("Guardar los datos del material en el inventario.")
        btn_guardar_form.clicked.connect(self._guardar)
        fila_botones_form.addWidget(btn_guardar_form)
        #"Limpiar" (no "Cancelar"): mismo botón/ícono que usan banco_tareas.py y observaciones.py junto a su "Guardar"
        #-deja el formulario listo para una captura nueva sin colapsar el panel; para colapsarlo basta con volver a
        #pulsar su propio encabezado.
        btn_limpiar_form= QPushButton("Limpiar")
        btn_limpiar_form.setObjectName("BtnAccionNeutro")
        btn_limpiar_form.setIcon(icono_emoji("🧹"))
        btn_limpiar_form.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_form.setToolTip("Vaciar el formulario (cancela la edición en curso, si había una).")
        btn_limpiar_form.clicked.connect(self._limpiar_formulario)
        fila_botones_form.addWidget(btn_limpiar_form)
        fila_botones_form.addStretch()
        form.addLayout(fila_botones_form)
        layout.addWidget(self.panel_form_material)

        self._poblar_combos_categoria()
        self._refrescar()
        self.actualizar_tema()  #por si el módulo se cargó de forma perezosa, ya con el tema definido

        self._titulo_modulo_atajos= "Materiales"
        self._configurar_atajos()

    #Atajos de teclado (ver atajos.py)
    def _configurar_atajos(self):

        #A diferencia de otros módulos (estudiantes.py, horario.py...), Materiales no reparte sus permisos por rol fijo
        #sino por categoría/usuario (ver RBAC en el docstring del módulo y _categorias_visibles): un Profesor puede
        #tener acceso de edición legítimo a una categoría entera. Por eso ningún atajo de acá se
        #registra con solo_no_docente=True -esa restricción no aplica a
        #este módulo- y en cambio cada acción sigue dependiendo, como siempre, de que el botón correspondiente esté
        #habilitado (_actualizar_botones_accion ya deja los botones deshabilitados cuando no hay selección o no hay
        #permiso).
        registrar_atajo(self, self.main_window, "Ctrl+F", "Buscar",
                         lambda: (self.buscador.setFocus(), self.buscador.selectAll()))
        registrar_atajo(self, self.main_window, "F5", "Actualizar tabla", self._refrescar)
        registrar_atajo(self, self.main_window, "Ctrl+N", "Nuevo material",
                         self._abrir_panel_nuevo_material)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Editar seleccionado",
                         lambda: self.btn_editar.click() if self.btn_editar.isEnabled() else None)
        registrar_atajo(self, self.main_window, "Ctrl+M", "Registrar préstamo / devolución",
                         lambda: self.btn_movimiento.click() if self.btn_movimiento.isEnabled() else None)
        registrar_atajo(self, self.main_window, "Delete", "Eliminar seleccionado",
                         lambda: self.btn_eliminar.click() if self.btn_eliminar.isEnabled() else None)

    #Despliega (si hace falta) el panel colapsable de alta y le pone
    #el foco al primer campo -mismo destino que ya usa el propio
    #encabezado del panel al hacer clic, ver PanelDesplegable-.
    def _abrir_panel_nuevo_material(self):

        if not self.panel_form_material.btn_cabecera.isEnabled():
            return
        if not self.panel_form_material._expandido:
            self.panel_form_material.btn_cabecera.click()
        self.combo_categoria_form.setFocus()

    #Categorías permitidas (núcleo del RBAC configurable de este módulo)
    #Lista [(id, nombre, icono)] de las categorías que el usuario
    #actual puede ver. Un rol gerencial ve TODAS; el resto, solo las que
    #se le asignaron en permisos_materiales_usuario (puede ser una lista
    #vacía: en ese caso el módulo se ve, pero sin ningún material).
    #
    #Cacheada en `self._cache_categorias` (ver el comentario en
    #`__init__`): pasar `forzar=True` descarta esa caché y vuelve a
    #consultar la base de datos -usarlo solo cuando de verdad pudo haber
    #cambiado el catálogo de categorías (arranque del módulo, tras
    #cerrar "Gestionar categorías").
    def _categorias_visibles(self, forzar=False):

        if not forzar and self._cache_categorias is not None:
            return self._cache_categorias
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre, icono FROM categorias_material ORDER BY nombre")
        todas= [(f["id"], f["nombre"], f["icono"]) for f in c.fetchall()]
        conn.close()
        if self.main_window is None:
            resultado= todas
        else:
            permitidas= categorias_material_permitidas(self.main_window)
            resultado= todas if permitidas is None else [
                (cid, nombre, icono) for cid, nombre, icono in todas if cid in permitidas]
        self._cache_categorias= resultado
        return resultado

    def _poblar_combos_categoria(self):

        categorias= self._categorias_visibles(forzar=True)
        self.combo_categoria_filtro.blockSignals(True)
        self.combo_categoria_filtro.clear()
        self.combo_categoria_filtro.addItem("Todas mis categorías", None)
        for cid, nombre, icono in categorias:
            self.combo_categoria_filtro.addItem(icono_categoria_material(icono, 16), nombre, cid)
        self.combo_categoria_filtro.blockSignals(False)
        #Mismo mecanismo estándar de tooltips de combos que el resto de
        #módulos (conectar_tooltip_seleccion, ver configuracion.py).
        conectar_tooltip_seleccion(self.combo_categoria_filtro,
                                   "Filtrar el inventario por una categoría de materiales concreta")

        self.combo_categoria_form.clear()
        categorias_editables= [(cid, nombre, icono) for cid, nombre, icono in categorias
                                 if self.main_window is None or puede_editar_categoria_material(self.main_window, cid)]
        for cid, nombre, icono in categorias_editables:
            self.combo_categoria_form.addItem(icono_categoria_material(icono, 16), nombre, cid)
        #Tooltip estándar por registro y "Seleccionado: ..." también en el combo del formulario (define quién puede
        #ver/editar el material).
        conectar_tooltip_seleccion(self.combo_categoria_form,
                                   "Categoría a la que pertenece el material; define quién puede verlo y editarlo")
        habilitar_alta= bool(categorias_editables)
        self.panel_form_material.btn_cabecera.setEnabled(habilitar_alta)
        self.panel_form_material.btn_cabecera.setToolTip(
            "" if habilitar_alta else "No tienes ninguna categoría con permiso de edición.")
        self.kpi_categorias.actualizar(len(categorias))

    #TABLA
    def _condiciones_filtro(self):

        condiciones= []
        parametros= []
        categorias= self._categorias_visibles()
        ids_visibles= [cid for cid, _n, _i in categorias]
        if not ids_visibles:
            return None, None  #sin ninguna categoría permitida: no se muestra nada
        categoria_id= self.combo_categoria_filtro.currentData()
        if categoria_id is not None:
            condiciones.append("materiales.categoria_id = ?")
            parametros.append(categoria_id)
        else:
            marcadores= ",".join("?" * len(ids_visibles))
            condiciones.append(f"materiales.categoria_id IN ({marcadores})")
            parametros.extend(ids_visibles)
        estado= self.combo_estado_filtro.currentData()
        if estado is not None:
            condiciones.append("materiales.estado = ?")
            parametros.append(estado)
        texto= self.buscador.text().strip()
        if texto:
            condiciones.append("(materiales.nombre LIKE ? OR materiales.codigo LIKE ? OR materiales.ubicacion LIKE ?)")
            parametros.extend([f"%{texto}%"] * 3)
        return condiciones, parametros

    def _refrescar(self):

        self.pagina.reiniciar()
        self._cargar_tabla()

    def _cargar_tabla(self):

        condiciones, parametros= self._condiciones_filtro()
        if condiciones is None:
            self.tabla.setRowCount(0)
            self.pagina.establecer_total(0)
            self.estado_vacio.actualizar(hay_filtro_elegido=False)
            self._actualizar_botones_accion()
            self.kpi_total.actualizar(0)
            self.kpi_disponibles.actualizar(0)
            self.kpi_prestamo.actualizar(0)
            return
        where= f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        conn= obtener_conexion()
        c= conn.cursor()
        #Una sola consulta agregada para el total (paginación) Y las sumas que alimentan las tarjetas KPI -antes esto
        #era solo un COUNT(*); sigue siendo UNA consulta, ahora simplemente trae más columnas, así que las tarjetas se
        #actualizan "en vivo" según el filtro activo sin costo adicional de ida y vuelta a la base de datos.
        c.execute(f"""SELECT COUNT(*) as n, COALESCE(SUM(materiales.cantidad_disponible),0) as disp,
                      COALESCE(SUM(materiales.cantidad_total),0) as total_unidades
                      FROM materiales JOIN categorias_material
                      ON materiales.categoria_id = categorias_material.id {where}""", parametros)
        resumen= c.fetchone()
        total= resumen["n"]
        self.pagina.establecer_total(total)
        self.kpi_total.actualizar(total)
        self.kpi_disponibles.actualizar(resumen["disp"])
        self.kpi_prestamo.actualizar(max(0, resumen["total_unidades"] - resumen["disp"]))

        inicio, _fin= self.pagina.rango_actual()
        tam= self.pagina.tamano_pagina() or total or 1
        c.execute(f"""SELECT materiales.*, categorias_material.nombre as categoria_nombre,
                      categorias_material.icono as categoria_icono
                      FROM materiales JOIN categorias_material ON materiales.categoria_id = categorias_material.id
                      {where} ORDER BY materiales.nombre LIMIT ? OFFSET ?""", parametros + [tam, inicio])
        filas= c.fetchall()
        conn.close()

        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(filas))
            for fila_idx, f in enumerate(filas):
                #Ícono vectorial de la categoría vía setIcon (antes se incrustaba el emoji crudo en el propio texto de la
                #celda, ver docstring del módulo): se ve nítido y consistente sin depender de que el sistema operativo tenga
                #ese glifo.
                item_cat= QTableWidgetItem(f["categoria_nombre"])
                item_cat.setIcon(icono_categoria_material(f["categoria_icono"], 18))
                item_cat.setData(Qt.ItemDataRole.UserRole, f["id"])
                item_cat.setData(Qt.ItemDataRole.UserRole + 1, f["categoria_id"])
                self.tabla.setItem(fila_idx, 0, item_cat)
                self.tabla.setItem(fila_idx, 1, QTableWidgetItem(f["codigo"] or "—"))
                self.tabla.setItem(fila_idx, 2, QTableWidgetItem(f["nombre"]))
                self.tabla.setItem(fila_idx, 3, QTableWidgetItem(f"{f['cantidad_disponible']} / {f['cantidad_total']}"))
                self.tabla.setItem(fila_idx, 4, QTableWidgetItem(f["ubicacion"] or "—"))
                self.tabla.setItem(fila_idx, 5, QTableWidgetItem(f["estado"]))
                self.tabla.setItem(fila_idx, 6, QTableWidgetItem(f["actualizado"] or "—"))
        ajustar_anchos_columnas(self.tabla)
        self.estado_vacio.actualizar(hay_filtro_elegido=True)
        self._actualizar_botones_accion()

    def _fila_seleccionada(self):

        if not self.tabla.selectedItems():
            return None, None
        item= self.tabla.item(self.tabla.currentRow(), 0)
        if item is None:
            return None, None
        return item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)

    def _actualizar_botones_accion(self):

        material_id, categoria_id= self._fila_seleccionada()
        hay_seleccion= material_id is not None
        puede_editar= hay_seleccion and (self.main_window is None
                                           or puede_editar_categoria_material(self.main_window, categoria_id))
        self.btn_editar.setEnabled(puede_editar)
        self.btn_eliminar.setEnabled(puede_editar)
        self.btn_movimiento.setEnabled(hay_seleccion)

    def _sincronizar_disponible_maximo(self, nuevo_total):

        self.spin_disponible_form.setMaximum(max(0, nuevo_total))
        if self.spin_disponible_form.value() > nuevo_total:
            self.spin_disponible_form.setValue(nuevo_total)

    #FORMULARIO
    #Conectado al clic del propio encabezado del panel (ver __init__):
    #se ejecuta DESPUÉS de que PanelDesplegable ya actualizó su estado
    #interno, así que `_expandido` refleja el estado nuevo.
    def _al_alternar_panel_formulario(self):

        if self.panel_form_material._expandido:
            self._hacer_visible_formulario()
        else:
            #Se acaba de colapsar (el usuario cerró sin guardar ni pulsar "Limpiar"): se limpia solo, para no dejar una
            #edición a medias esperando la próxima vez que abran el panel.
            self._limpiar_formulario()

    #Con la página dentro del QScrollArea, el panel desplegado puede
    #quedar por debajo del pliegue: desplaza el scroll hasta él (deferido
    #con QTimer para que el layout/la animación de apertura ya se hayan
    #asentado).
    def _hacer_visible_formulario(self):

        p= self.panel_form_material.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p= p.parentWidget()
        if p is not None:
            QTimer.singleShot(0, lambda: p.ensureWidgetVisible(self.panel_form_material, 0, 30))

    def _cargar_seleccionado_en_formulario(self):

        material_id, categoria_id= self._fila_seleccionada()
        if material_id is None:
            return
        if self.main_window is not None and not puede_editar_categoria_material(self.main_window, categoria_id):
            mostrar_mensaje("advertencia", "Sin permiso", "No tienes permiso de edición sobre esta categoría.", self)
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM materiales WHERE id=?", (material_id,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.material_en_edicion= material_id
        idx_cat= self.combo_categoria_form.findData(f["categoria_id"])
        if idx_cat < 0:
            mostrar_mensaje("advertencia", "Categoría no editable",
                             "Esta categoría ya no está entre las que puedes editar.", self)
            return
        self.combo_categoria_form.setCurrentIndex(idx_cat)
        self.in_codigo_form.setText(f["codigo"] or "")
        self.in_nombre_form.setText(f["nombre"])
        self.txt_descripcion_form.setPlainText(f["descripcion"] or "")
        self.spin_total_form.setValue(f["cantidad_total"])
        self.spin_disponible_form.setMaximum(max(0, f["cantidad_total"]))
        self.spin_disponible_form.setValue(f["cantidad_disponible"])
        self.in_ubicacion_form.setText(f["ubicacion"] or "")
        idx_estado= self.combo_estado_form.findData(f["estado"])
        self.combo_estado_form.setCurrentIndex(idx_estado if idx_estado >= 0 else 0)
        #De golpe (sin animación) al editar, igual que observaciones.py: el despliegue "por descubrimiento" de
        #edicion_feedback ya lo abriría solo, pero abrirlo aquí explícito evita cualquier parpadeo previo al banner y
        #dispara la animación de la MISMA forma cada vez.
        self.panel_form_material.expandir(True, animar=False)
        self._hacer_visible_formulario()
        #Banner "Editando: ..." + despliegue/scroll automático hasta el formulario -mismo mecanismo que
        #estudiantes/materias/observaciones (ver edicion_feedback.py), del que este módulo carecía hasta ahora.
        activar_modo_edicion(self.in_nombre_form, f"Editando material: {f['nombre'] or ''}")

    #Deja el formulario listo para una captura nueva: mismo papel que
    #el botón 'Limpiar' de banco_tareas.py/observaciones.py. NO colapsa
    #el panel -para eso está su propio encabezado- así que sirve tanto
    #para "ya guardé, quiero cargar otro material" como para "cancelar
    #esta edición sin perder de vista el formulario".
    def _limpiar_formulario(self):

        self.material_en_edicion= None
        if self.combo_categoria_form.count():
            self.combo_categoria_form.setCurrentIndex(0)
        self.in_codigo_form.clear()
        self.in_nombre_form.clear()
        self.txt_descripcion_form.clear()
        self.spin_total_form.setValue(1)
        self.spin_disponible_form.setValue(1)
        self.in_ubicacion_form.clear()
        self.combo_estado_form.setCurrentIndex(0)
        desactivar_modo_edicion(self.in_nombre_form)

    def _guardar(self):

        categoria_id= self.combo_categoria_form.currentData()
        nombre= self.in_nombre_form.text().strip()
        if categoria_id is None or not nombre:
            mostrar_mensaje("advertencia", "Faltan datos", "Elige una categoría y escribe el nombre del material.", self)
            return
        if self.main_window is not None and not puede_editar_categoria_material(self.main_window, categoria_id):
            mostrar_mensaje("advertencia", "Sin permiso", "No tienes permiso de edición sobre esta categoría.", self)
            return
        ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn= obtener_conexion()
        c= conn.cursor()
        if self.material_en_edicion is None:
            c.execute("""INSERT INTO materiales (categoria_id, codigo, nombre, descripcion, cantidad_total,
                         cantidad_disponible, ubicacion, estado, adquirido, actualizado)
                         VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (categoria_id, self.in_codigo_form.text().strip(), nombre,
                       self.txt_descripcion_form.toPlainText().strip(), self.spin_total_form.value(),
                       self.spin_disponible_form.value(), self.in_ubicacion_form.text().strip(),
                       self.combo_estado_form.currentData(), date.today().strftime("%Y-%m-%d"), ahora))
            accion= "Creó un material"
        else:
            c.execute("""UPDATE materiales SET categoria_id=?, codigo=?, nombre=?, descripcion=?, cantidad_total=?,
                         cantidad_disponible= ?, ubicacion=?, estado=?, actualizado=? WHERE id=?""",
                      (categoria_id, self.in_codigo_form.text().strip(), nombre,
                       self.txt_descripcion_form.toPlainText().strip(), self.spin_total_form.value(),
                       self.spin_disponible_form.value(), self.in_ubicacion_form.text().strip(),
                       self.combo_estado_form.currentData(), ahora, self.material_en_edicion))
            accion= "Editó un material"
        conn.commit()
        conn.close()
        registrar_auditoria("Materiales", accion,
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             nombre)
        self._limpiar_formulario()
        self._refrescar()
        mostrar_mensaje("exito", "Guardado", "El material se guardó correctamente.", self)

    def _eliminar_seleccionado(self):

        material_id, categoria_id= self._fila_seleccionada()
        if material_id is None:
            return
        if self.main_window is not None and not puede_editar_categoria_material(self.main_window, categoria_id):
            mostrar_mensaje("advertencia", "Sin permiso", "No tienes permiso de edición sobre esta categoría.", self)
            return
        respuesta= mostrar_mensaje("pregunta", "Eliminar material",
                                     "¿Eliminar este material del inventario? Esta acción no se puede deshacer.", self)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM materiales WHERE id=?", (material_id,))
        conn.commit()
        conn.close()
        registrar_auditoria("Materiales", "Eliminó un material",
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             f"Material ID {material_id}")
        self._refrescar()

    #PRÉSTAMOS / MOVIMIENTOS
    def _abrir_movimiento(self):

        material_id, _categoria_id= self._fila_seleccionada()
        if material_id is None:
            return
        #parent = self.window(): centrar_y_al_frente centra sobre la ventana
        #top-level (la ventana principal de la app), igual que el resto de módulos con sus ventanas.
        dialogo= DialogoMovimientoMaterial(self.main_window, material_id, self.window())
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._refrescar()

    #Gestión de categorías (solo roles gerenciales)
    def _abrir_gestion_categorias(self):

        dialogo= DialogoGestionCategorias(self.window())
        dialogo.exec()
        self._poblar_combos_categoria()
        self._refrescar()

    def _abrir_permisos_usuarios(self):

        dialogo= DialogoPermisosMateriales(self.window())
        dialogo.exec()

    #TEMA (claro/oscuro) — llamado por main.py cada vez que cambia, igual que el resto de módulos con elementos de
    #estilo propio (cabecera degradada, tarjetas KPI); ver el docstring de asistencia.py/materias.py para el mismo
    #patrón.
    def actualizar_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None) if mw is not None else None
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
        if not paleta:
            return
        idx= 1 if getattr(mw, "modo_oscuro", True) else 0

        bg_panel= paleta["display_bg"][idx]
        bg_borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        modo_oscuro= getattr(mw, "modo_oscuro", True)
        accent= paleta["btn_op_bg"][idx]
        accent_hover= paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else accent

        for tarjeta in self._tarjetas_kpi:
            tarjeta.aplicar_paleta(bg_panel, bg_borde, txt_prim, txt_sec, modo_oscuro)

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
            QPushButton#BtnAccionCabecera {{
                background-color: rgba(255, 255, 255, 40);
                color: white;
                border: 1px solid rgba(255, 255, 255, 90);
                border-radius: 9px;
                padding: 7px 14px;
                font-weight: 700;
            }}
            QPushButton#BtnAccionCabecera:hover {{
                background-color: rgba(255, 255, 255, 65);
            }}
        """)

        self.tarjeta_filtros.setStyleSheet(f"""
            QFrame#TarjetaFiltros {{
                background-color: {bg_panel};
                border: 1px solid {bg_borde};
                border-radius: 12px;
            }}
        """)
        self.tarjeta_tabla.setStyleSheet(f"""
            QFrame#TarjetaTabla {{
                background-color: {bg_panel};
                border: 1px solid {bg_borde};
                border-radius: 14px;
            }}
        """)
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)
        #Encabezado del panel colapsable "Nuevo material" (ver PanelDesplegable en calendario.py): su color de texto
        #depende del modo claro/oscuro y solo se recalcula al mostrarse por primera vez o llamando a esto.
        self.panel_form_material.actualizar_color_tema()


#Diálogo: selector de ícono de categoría
#Grilla de íconos vectoriales (ver iconos_categorias.py ▸ sección
#MATERIALES) para elegir el ícono de una categoría con un clic, en vez de
#escribir un emoji a mano -en muchos equipos Windows/Linux no hay un
#teclado de emojis a la vista, y el resultado antes dependía de qué
#fuente tuviera instalada el sistema operativo.
class _DialogoSelectorIconoMaterial(_DialogoCentrado):

    def __init__(self, valor_actual=None, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Elegir ícono de categoría")
        aplicar_icono_ventana(self)
        self.clave_elegida= None
        clave_actual= (valor_actual or "").strip().lower()

        layout= QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        info= QLabel("Elige el ícono que mejor represente esta categoría de inventario.")
        info.setWordWrap(True)
        layout.addWidget(info)

        contenedor_grid= QWidget()
        grid= QGridLayout(contenedor_grid)
        grid.setSpacing(8)
        columnas= 4
        for i, (clave, etiqueta) in enumerate(CATEGORIAS_SUGERIDAS_MATERIAL):
            btn= QToolButton()
            btn.setIcon(icono_categoria_material(clave, 30))
            btn.setIconSize(_QSize_emoji(30, 30))
            btn.setText(etiqueta)
            #Tooltip con la etiqueta completa: el texto del botón puede
            #elidirse (p. ej. "Libros / Bibliote…") pero con el tooltip
            #siempre se puede leer el nombre entero antes de elegir.
            btn.setToolTip(etiqueta)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            #Botones más anchos/altos que antes (102x78): con el ancho anterior etiquetas como "Libros / Biblioteca"
            #quedaban cortadas.
            btn.setFixedSize(124, 88)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(clave == clave_actual)
            btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid rgba(148, 163, 184, 0.45);
                    border-radius: 10px;
                    padding: 6px;
                }
                QToolButton:hover {
                    border-color: #6366F1;
                    background-color: rgba(99, 102, 241, 0.12);
                }
                QToolButton:checked {
                    border-color: #6366F1;
                    background-color: rgba(99, 102, 241, 0.20);
                }
            """)
            btn.clicked.connect(lambda _checked=False, c=clave: self._elegir(c))
            grid.addWidget(btn, i // columnas, i % columnas)
        layout.addWidget(contenedor_grid)

        fila_icono_botones= QHBoxLayout()
        fila_icono_botones.addStretch()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setObjectName("BtnAccionNeutro")
        btn_cancelar.clicked.connect(self.reject)
        fila_icono_botones.addWidget(btn_cancelar)
        layout.addLayout(fila_icono_botones)

        #La grilla tiene 4 columnas de 124px: sin este ancho mínimo la ventana podía abrirse aplastando los botones y
        #elidiendo los textos.
        self.setMinimumWidth(596)
        centrar_y_al_frente(self, parent)

    def _elegir(self, clave):

        self.clave_elegida= clave
        self.accept()


#Diálogo: gestión de categorías
class DialogoGestionCategorias(_DialogoCentrado):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Categorías de Materiales")
        aplicar_icono_ventana(self)
        #Tamaños holgados: antes con 460px de ancho y una tabla sin alto mínimo los textos quedaban cortados al abrir
        #la ventana.
        self.setMinimumSize(680, 520)
        layout= QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        info= QLabel("Define las categorías de materiales que gestiona tu institución "
                       "(por ejemplo: Libros, Equipos de Laboratorio, Herramientas de Taller...).")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tabla= QTableWidget()
        self.tabla.setColumnCount(3)
        self.tabla.setHorizontalHeaderLabels(["Icono", "Nombre", "Descripción"])
        aplicar_estructura_tabla(self.tabla)
        #Mismo comportamiento estándar que la tabla principal del módulo y el resto de la app: filas de 40px, selección
        #por fila, colores alternos y alto mínimo holgado para que el texto respire.
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        #Nombre y Descripción son EDITABLES in-place (doble clic): el cambio se guarda en la BD al terminar la edición
        #(_celda_editada). El ícono no se edita aquí (se cambia eliminando y volviendo a crear, o se elige al crear la
        #categoría en la fila de abajo).
        self.tabla.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked |
            QTableWidget.EditTrigger.EditKeyPressed)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.setMinimumHeight(240)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        _hdr_cat= self.tabla.horizontalHeader()
        _hdr_cat.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        _hdr_cat.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla.setColumnWidth(0, 56)
        self.tabla.setColumnWidth(1, 210)
        self.tabla.itemChanged.connect(self._celda_editada)
        self._cargando= False  #ignora itemChanged mientras se llena la tabla
        layout.addWidget(self.tabla, 1)

        pista= QLabel("\U0001F4A1 Doble clic sobre el Nombre o la Descripción de una fila para editarla "
                       "directamente en la tabla (los cambios se guardan solos).")
        pista.setWordWrap(True)
        pista.setStyleSheet("color: palette(mid);")
        layout.addWidget(pista)

        fila_nueva= QHBoxLayout()
        fila_nueva.setSpacing(8)
        self.lbl_preview_icono= QLabel()
        self.lbl_preview_icono.setFixedSize(30, 30)
        self.lbl_preview_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_icono.setPixmap(pixmap_categoria_material("otro", 26))
        fila_nueva.addWidget(self.lbl_preview_icono)

        self.in_icono= QLineEdit()
        self.in_icono.setText("otro")
        self.in_icono.setToolTip("Clave del ícono elegido (usa el botón \"Elegir ícono…\"), o pega un emoji propio.")
        self.in_icono.setFixedWidth(90)
        limitar_campo_texto(self.in_icono, 40)
        self.in_icono.textChanged.connect(self._previsualizar_icono)
        fila_nueva.addWidget(self.in_icono)

        btn_elegir_icono= QPushButton("Elegir ícono…")
        btn_elegir_icono.setIcon(icono_categoria_material("otro", 16))
        btn_elegir_icono.setToolTip("Elegir el ícono de esta categoría de una grilla, en vez de escribirlo a mano.")
        btn_elegir_icono.clicked.connect(self._abrir_selector_icono)
        fila_nueva.addWidget(btn_elegir_icono)

        self.in_nombre= QLineEdit()
        self.in_nombre.setPlaceholderText("Nombre de la nueva categoría")
        self.in_nombre.setToolTip("Nombre visible de la nueva categoría (debe ser único).")
        limitar_campo_texto(self.in_nombre, 100)
        fila_nueva.addWidget(self.in_nombre, stretch=1)

        btn_agregar= QPushButton("Agregar")
        btn_agregar.setObjectName("BtnAccionAgregar")
        btn_agregar.setIcon(icono_emoji("➕"))
        btn_agregar.setIconSize(_QSize_emoji(16, 16))
        btn_agregar.setToolTip("Crear esta categoría con el ícono y nombre indicados arriba.")
        btn_agregar.clicked.connect(self._agregar)
        fila_nueva.addWidget(btn_agregar)
        layout.addLayout(fila_nueva)

        fila_botones= QHBoxLayout()
        btn_eliminar= QPushButton("Eliminar seleccionada")
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setToolTip("Eliminar la categoría seleccionada y TODOS los materiales que contenga.")
        btn_eliminar.clicked.connect(self._eliminar)
        fila_botones.addWidget(btn_eliminar)
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.setToolTip("Cerrar esta ventana.")
        btn_cerrar.clicked.connect(self.accept)
        fila_botones.addWidget(btn_cerrar)
        layout.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)
        self._cargar()

    def _previsualizar_icono(self, texto):

        self.lbl_preview_icono.setPixmap(pixmap_categoria_material(texto.strip() or "otro", 26))

    def _abrir_selector_icono(self):

        dialogo= _DialogoSelectorIconoMaterial(self.in_icono.text().strip(), self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.clave_elegida:
            self.in_icono.setText(dialogo.clave_elegida)

    def _cargar(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM categorias_material ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        self._cargando= True  #evita que setItem dispare _celda_editada
        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(filas))
            for i, f in enumerate(filas):
                #Ícono vectorial vía setIcon (ver iconos_categorias.py): antes esta celda mostraba el glifo de emoji crudo
                #guardado en la BD.
                item_icono= QTableWidgetItem("")
                item_icono.setIcon(icono_categoria_material(f["icono"], 22))
                item_icono.setData(Qt.ItemDataRole.UserRole, f["id"])
                #El ícono NO es editable in-place: solo se elige al crear la
                #categoría (o cambiando su clave desde la fila de abajo antes
                #de agregar una nueva).
                item_icono.setFlags(item_icono.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item_icono.setToolTip(f["nombre"])
                self.tabla.setItem(i, 0, item_icono)
                item_nombre= QTableWidgetItem(f["nombre"])
                item_nombre.setToolTip(f"{f['nombre']} (doble clic para editar)")
                item_nombre.setData(Qt.ItemDataRole.UserRole, f["id"])
                self.tabla.setItem(i, 1, item_nombre)
                desc= f["descripcion"] or ""
                item_desc= QTableWidgetItem(desc)
                item_desc.setToolTip((desc or "Sin descripción (doble clic para agregar una)") if len(desc) < 200 else desc)
                item_desc.setData(Qt.ItemDataRole.UserRole, f["id"])
                if not desc:
                    #Pista visual de que la descripción está vacía y editable
                    f_item= item_desc.font()
                    f_item.setItalic(True)
                    item_desc.setFont(f_item)
                    item_desc.setForeground(self.palette().mid())
                    item_desc.setText("")
                self.tabla.setItem(i, 2, item_desc)
        self._cargando= False
        ajustar_anchos_columnas(self.tabla)

    #Guarda en la BD la edición in-place del Nombre o la Descripción
    #de una categoría. Se ignora mientras la tabla se está llenando
    #(self._cargando) y si la celda editada es el ícono (no editable).
    def _celda_editada(self, item):

        if self._cargando or item is None:
            return
        columna= item.column()
        if columna == 0:
            return
        categoria_id= item.data(Qt.ItemDataRole.UserRole)
        texto= item.text().strip()
        if columna == 1:
            #Nombre: obligatorio y único
            if not texto:
                mostrar_mensaje("advertencia", "Nombre vacío",
                                "El nombre de la categoría no puede quedar vacío.", self)
                self._cargar()
                return
            conn= obtener_conexion()
            c= conn.cursor()
            try:

                c.execute("UPDATE categorias_material SET nombre=? WHERE id=?", (texto, categoria_id))
                conn.commit()
            except Exception:
                mostrar_mensaje("advertencia", "Categoría existente",
                                "Ya existe otra categoría con ese nombre.", self)
                conn.close()
                self._cargar()
                return
            conn.close()
            item.setToolTip(f"{texto} (doble clic para editar)")
            #Los combos del módulo se refrescan solos al cerrar esta
            #ventana (ver _abrir_gestion_categorias en ModuloMateriales).
        else:
            #Descripción: opcional
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("UPDATE categorias_material SET descripcion=? WHERE id=?", (texto, categoria_id))
            conn.commit()
            conn.close()
            fuente= item.font()
            fuente.setItalic(False)
            item.setFont(fuente)
            item.setForeground(self.palette().text())

    def _agregar(self):

        nombre= self.in_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Falta el nombre", "Escribe el nombre de la nueva categoría.", self)
            return
        icono= self.in_icono.text().strip() or "otro"
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("INSERT INTO categorias_material (nombre, icono) VALUES (?,?)", (nombre, icono))
            conn.commit()
        except Exception:
            mostrar_mensaje("advertencia", "Categoría existente", "Ya existe una categoría con ese nombre.", self)
            conn.close()
            return
        conn.close()
        self.in_nombre.clear()
        self.in_icono.setText("otro")
        self._cargar()

    def _eliminar(self):

        if not self.tabla.selectedItems():
            return
        item= self.tabla.item(self.tabla.currentRow(), 0)
        categoria_id= item.data(Qt.ItemDataRole.UserRole)
        respuesta= mostrar_mensaje("pregunta", "Eliminar categoría",
                                     "Se eliminará la categoría y TODOS los materiales que contenga. ¿Continuar?", self)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM categorias_material WHERE id=?", (categoria_id,))
        conn.commit()
        conn.close()
        self._cargar()


#Diálogo: permisos de acceso por usuario
#Permite a un rol gerencial elegir un usuario y marcar, categoría por
#categoría, si la ve (checkbox) y si además puede editarla (segundo
#checkbox, solo habilitado si la primera está marcada).
class DialogoPermisosMateriales(_DialogoCentrado):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Permisos de acceso a Materiales")
        aplicar_icono_ventana(self)
        #Compacto: tabla con filas ceñidas en vez de la grilla+scroll de antes, que dejaba una franja de espacio en
        #blanco enorme entre la cabecera y las categorías cuando había pocas.
        self.setMinimumSize(520, 440)
        layout= QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info= QLabel("Marca a qué categorías puede acceder el usuario y si además puede "
                       "editarlas (si no, solo consulta). Los roles gerenciales tienen "
                       "acceso total y no aparecen en la lista.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.combo_usuario= QComboBox()
        self.combo_usuario.setMinimumHeight(34)
        self.combo_usuario.setToolTip("Usuario al que se le asignarán los permisos de acceso marcados abajo.")
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre_completo, username, rol FROM usuarios
                     WHERE rol NOT IN ('Administrador','Director','Coordinador') AND activo=1
                     ORDER BY nombre_completo""")
        self._usuarios= c.fetchall()
        c.execute("SELECT id, nombre, icono FROM categorias_material ORDER BY nombre")
        self._categorias= c.fetchall()
        conn.close()
        for u in self._usuarios:
            self.combo_usuario.addItem(f"{u['nombre_completo']} ({u['rol']})", u["id"])
        self.combo_usuario.currentIndexChanged.connect(self._cargar_permisos_usuario)
        conectar_tooltip_seleccion(self.combo_usuario, "Usuario al que se le asignarán los permisos")
        layout.addWidget(self.combo_usuario)

        self._avisos= []
        if not self._usuarios:
            #Sin usuarios no-gerenciales no hay nada que configurar: se avisa en lugar de mostrar una tabla muerta de
            #checkboxes inútiles.
            self._avisos.append(QLabel("No hay usuarios no gerenciales (Profesor/Administrativo u otros) "
                                       "activos en el sistema a quienes asignar permisos de Materiales."))
        if not self._categorias:
            #Sin categorías creadas aún no hay nada que asignar: se avisa para que no parezca que la ventana "no funciona".
            self._avisos.append(QLabel("Todavía no hay categorías de materiales. Créalas primero "
                                       "con el botón \u201cGestionar categorías\u201d del módulo."))
        for aviso in self._avisos:
            aviso.setWordWrap(True)
            aviso.setStyleSheet("color: #F59E0B; font-weight: 600;")
            layout.addWidget(aviso)

        #---------- Tabla de permisos (mismo look que las tablas de la app) ----------
        self.tarjeta_tabla= QFrame()
        self.tarjeta_tabla.setObjectName("TarjetaTabla")
        lay_tabla= QVBoxLayout(self.tarjeta_tabla)
        lay_tabla.setContentsMargins(10, 10, 10, 10)
        self.tabla= QTableWidget(len(self._categorias), 3)
        self.tabla.setHorizontalHeaderLabels(["Categoría", "Ver", "Editar"])
        aplicar_estructura_tabla(self.tabla)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.setMinimumHeight(180)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        hdr= self.tabla.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(1, 64)
        self.tabla.setColumnWidth(2, 72)
        self.tabla.itemChanged.connect(self._check_cambiado)
        self._llenando= False
        lay_tabla.addWidget(self.tabla, 1)
        layout.addWidget(self.tarjeta_tabla, 1)

        #fila -> id de categoría, para leer/guardar los checks de la tabla
        self._ids_fila= [cat["id"] for cat in self._categorias]

        self.botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.botones.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(self._usuarios))
        self.botones.accepted.connect(self._guardar)
        self.botones.rejected.connect(self.reject)
        layout.addWidget(self.botones)

        self._pintar_categorias()
        centrar_y_al_frente(self, parent)
        if self._usuarios:
            self._cargar_permisos_usuario()

    #Llena la tabla con una fila por categoría: nombre con su ícono
    #vectorial y dos checkboxes centrados (Ver / Editar).
    def _pintar_categorias(self):

        self._llenando= True
        with tabla_pausada(self.tabla):
            for i, cat in enumerate(self._categorias):
                item_cat= QTableWidgetItem(f"  {cat['nombre']}")
                item_cat.setIcon(icono_categoria_material(cat["icono"], 18))
                item_cat.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item_cat.setToolTip(f"Acceso a la categoría \u201c{cat['nombre']}\u201d")
                self.tabla.setItem(i, 0, item_cat)

                item_ver= QTableWidgetItem()
                item_ver.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item_ver.setCheckState(Qt.CheckState.Unchecked)
                item_ver.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(i, 1, item_ver)

                item_editar= QTableWidgetItem()
                #Sin "Ver" marcado, "Editar" no aplica: se deshabilita
                item_editar.setFlags(Qt.ItemFlag.ItemIsUserCheckable)
                item_editar.setCheckState(Qt.CheckState.Unchecked)
                item_editar.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_editar.setToolTip("Marca también \u201cVer\u201d para poder habilitar la edición")
                self.tabla.setItem(i, 2, item_editar)
        self._llenando= False

    #Al marcar/desmarcar “Ver”, habilita o deshabilita el
    #checkbox “Editar” de la misma fila (editar implica ver).
    def _check_cambiado(self, item):

        if self._llenando or item.column() != 1:
            return
        item_editar= self.tabla.item(item.row(), 2)
        if item_editar is None:
            return
        permitido= item.checkState() == Qt.CheckState.Checked
        flags= item_editar.flags()
        if permitido:
            item_editar.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
        else:
            item_editar.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
            item_editar.setCheckState(Qt.CheckState.Unchecked)

    def _cargar_permisos_usuario(self):

        usuario_id= self.combo_usuario.currentData()
        permisos= obtener_permisos_materiales_usuario(usuario_id) if usuario_id else {}
        self._llenando= True
        with tabla_pausada(self.tabla):
            for fila, cat_id in enumerate(self._ids_fila):
                tiene= cat_id in permisos
                puede_editar= bool(permisos.get(cat_id, False))
                item_ver= self.tabla.item(fila, 1)
                item_ver.setCheckState(Qt.CheckState.Checked if tiene else Qt.CheckState.Unchecked)
                item_editar= self.tabla.item(fila, 2)
                flags= item_editar.flags()
                if tiene:
                    item_editar.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
                    item_editar.setCheckState(Qt.CheckState.Checked if puede_editar else Qt.CheckState.Unchecked)
                else:
                    item_editar.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
                    item_editar.setCheckState(Qt.CheckState.Unchecked)
        self._llenando= False

    def _guardar(self):

        usuario_id= self.combo_usuario.currentData()
        if usuario_id is None:
            self.reject()
            return
        categorias_con_edicion= {}
        for fila, cat_id in enumerate(self._ids_fila):
            if self.tabla.item(fila, 1).checkState() == Qt.CheckState.Checked:
                categorias_con_edicion[cat_id]= \
                    self.tabla.item(fila, 2).checkState() == Qt.CheckState.Checked
        guardar_permisos_materiales_usuario(usuario_id, categorias_con_edicion)
        mostrar_mensaje("exito", "Permisos guardados", "Los permisos de acceso se actualizaron correctamente.", self)
        self.accept()


#Diálogo: préstamo / DEVOLUCIÓN
class DialogoMovimientoMaterial(_DialogoCentrado):

    def __init__(self, main_window, material_id, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.material_id= material_id
        self.setWindowTitle("Registrar movimiento de material")
        aplicar_icono_ventana(self)
        #Ancho mayor (antes 420px): los placeholders largos como "Nombre de quien recibe/entrega (opcional)" quedaban
        #recortados.
        self.setMinimumWidth(540)
        layout= QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM materiales WHERE id=?", (material_id,))
        self.material= c.fetchone()
        conn.close()

        layout.addWidget(QLabel(f"Material: {self.material['nombre']}  "
                                 f"(disponibles: {self.material['cantidad_disponible']} de {self.material['cantidad_total']})"))

        self.combo_tipo= QComboBox()
        for tipo in TIPOS_MOVIMIENTO:
            self.combo_tipo.addItem(tipo, tipo)
        self.combo_tipo.setToolTip(
            "Préstamo resta unidades disponibles; Devolución las repone; Baja retira unidades "
            "definitivamente del inventario; Ingreso de inventario suma unidades nuevas.")
        conectar_tooltip_seleccion(self.combo_tipo, "Tipo de movimiento a registrar")
        layout.addWidget(QLabel("Tipo de movimiento:"))
        layout.addWidget(self.combo_tipo)

        self.spin_cantidad= QSpinBox()
        self.spin_cantidad.setRange(1, max(1, self.material["cantidad_total"]))
        self.spin_cantidad.setValue(1)
        self.spin_cantidad.setToolTip("Cantidad de unidades que involucra este movimiento.")
        layout.addWidget(QLabel("Cantidad:"))
        layout.addWidget(self.spin_cantidad)

        self.in_responsable= QLineEdit()
        self.in_responsable.setPlaceholderText("Nombre de quien recibe/entrega (opcional)")
        self.in_responsable.setToolTip("Quién recibe (préstamo) o devuelve (devolución) el material, si aplica.")
        limitar_campo_texto(self.in_responsable, 150)
        layout.addWidget(QLabel("Responsable:"))
        layout.addWidget(self.in_responsable)

        self.txt_observacion= QTextEdit()
        self.txt_observacion.setMaximumHeight(70)
        self.txt_observacion.setToolTip("Nota adicional sobre este movimiento (condición del material, motivo, etc.).")
        limitar_campo_texto(self.txt_observacion, 500)
        layout.addWidget(QLabel("Observación (opcional):"))
        layout.addWidget(self.txt_observacion)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        centrar_y_al_frente(self, parent)

    def _guardar(self):

        tipo= self.combo_tipo.currentData()
        cantidad= self.spin_cantidad.value()
        disponible= self.material["cantidad_disponible"]
        total= self.material["cantidad_total"]

        if tipo == "Préstamo" and cantidad > disponible:
            mostrar_mensaje("advertencia", "Cantidad no disponible",
                             f"Solo hay {disponible} disponible(s) para préstamo.", self)
            return

        conn= obtener_conexion()
        c= conn.cursor()
        if tipo == "Préstamo":
            nueva_disponible= disponible - cantidad
        elif tipo == "Devolución":
            nueva_disponible= min(total, disponible + cantidad)
        elif tipo == "Baja":
            nueva_disponible= max(0, disponible - cantidad)
            c.execute("UPDATE materiales SET cantidad_total = MAX(0, cantidad_total - ?) WHERE id=?",
                      (cantidad, self.material_id))
        else:  #Ingreso de inventario
            nueva_disponible= disponible + cantidad
            c.execute("UPDATE materiales SET cantidad_total = cantidad_total + ? WHERE id=?",
                      (cantidad, self.material_id))

        c.execute("UPDATE materiales SET cantidad_disponible=?, actualizado=? WHERE id=?",
                  (nueva_disponible, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.material_id))
        id_usuario= getattr(self.main_window, "id_usuario_actual", None) if self.main_window else None
        c.execute("""INSERT INTO material_movimientos (material_id, tipo, cantidad, responsable, fecha,
                     observacion, usuario_id) VALUES (?,?,?,?,?,?,?)""",
                  (self.material_id, tipo, cantidad, self.in_responsable.text().strip(),
                   date.today().strftime("%Y-%m-%d"), self.txt_observacion.toPlainText().strip(), id_usuario))
        conn.commit()
        conn.close()
        registrar_auditoria("Materiales", f"Registró un movimiento ({tipo}) de material",
                             getattr(self.main_window, "usuario_actual", "Sistema") if self.main_window else "Sistema",
                             f"{self.material['nombre']} x{cantidad}")
        self.accept()