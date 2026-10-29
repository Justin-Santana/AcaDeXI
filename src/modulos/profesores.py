import os
import unicodedata
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QGridLayout,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QCheckBox, QDialog)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen
from src.nucleo.bd import obtener_conexion, registrar_auditoria, obtener_carpeta_datos
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.nucleo.permisos import puede_editar, es_profesor_restringido
from src.interfaz.foto_utils import seleccionar_y_recortar_foto, VisorFotoDialog
from src.interfaz.paginacion import (aplicar_estructura_tabla, ajustar_anchos_columnas, ControlPaginacion,
    agregar_boton_detalle, tabla_pausada, obtener_pixmap_circular_cacheado, ROL_RUTA_FOTO,
    configurar_columna_foto, pixmap_placeholder_foto_tabla, TAMANO_FOTO_TABLA, agregar_boton_pantalla_completa)
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, html_icono_emoji,
                          icono_boton_filtro, pixmap_boton_filtro, EMOJI_PROFESOR, EMOJI_FOTO_RECORTAR)
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion

ESTADOS= ["Activo", "Inactivo"]


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica. (mismo lenguaje visual que
#estudiantes.py, para que ambos módulos se sientan parte de la misma aplicación)
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


class ModuloProfesores(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion= None
        self.foto_path= ""
        #Este módulo es exclusivo de roles gerenciales (Admin/Director/Coordinador).
        #Un usuario con rol Profesor no debe poder gestionar el listado de profesores:
        #su propia información ya la ve/gestiona desde el "Modo Docente".
        self.acceso_restringido= es_profesor_restringido(main_window)
        self._contador_valor_actual= 0
        self._construir_ui()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Profesores"
        #Ver comentario de self.acceso_restringido más arriba: un Profesor no debe gestionar el listado de profesores.
        #Todos los atajos mutables se omiten por completo en Modo Docente.
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar profesor",
                         self._guardar, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario",
                         self._limpiar, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar profesor seleccionado",
                         self._cargar_seleccionado, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar profesor",
                         self._eliminar, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+Z", "Deshacer eliminación",
                         self._deshacer_eliminacion, solo_no_docente=True)

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

        #--- Cabecera tipo "hero": icono + título + descripción (+ contador animado) ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel("")
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Profesores")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Profesores")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        subtitulo= ("Esta sección es exclusiva de roles gerenciales"
                     if self.acceso_restringido else
                     "Administra el personal docente: contacto, especialidad y cuenta de acceso")
        self.lbl_subtitulo_cabecera= QLabel(subtitulo)
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        if not self.acceso_restringido:
            self.chip_contador= QLabel(f"{html_icono_emoji(EMOJI_PROFESOR, 15)} 0 profesores")
            self.chip_contador.setObjectName("ChipContador")
            self.chip_contador.setTextFormat(Qt.TextFormat.RichText)
            cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)
        disposicion.addWidget(self.frame_cabecera)

        if self.acceso_restringido:
            #Vista de acceso denegado para el rol Profesor/Docente.
            self.frame_restringido= QFrame()
            self.frame_restringido.setObjectName("TarjetaFormulario")
            marco_layout= QVBoxLayout(self.frame_restringido)
            marco_layout.setContentsMargins(30, 34, 30, 34)
            marco_layout.setSpacing(10)
            lbl_candado= QLabel()
            lbl_candado.setPixmap(pixmap_emoji("🔒", 20))
            lbl_candado.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_candado.setStyleSheet("font-size: 40px; background: transparent;")
            marco_layout.addWidget(lbl_candado)
            lbl= QLabel(
                "Acceso restringido\n\n"
                "La gestión del listado de Profesores es exclusiva de roles "
                "gerenciales (Administrador/Director/Coordinador).\n\n"
                "Tus propias materias, horario y secciones guía están disponibles "
                "en el módulo 'Mis Materias' del Modo Docente.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setObjectName("DescModulo")
            marco_layout.addWidget(lbl)
            disposicion.addWidget(self.frame_restringido, 1)
            scroll.setWidget(contenido)
            layout_raiz.addWidget(scroll, 1)
            self.actualizar_tema()
            return

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

        lbl_titulo_ficha= QLabel("Ficha del Profesor")
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
        self.in_especialidad= QLineEdit()
        limitar_campo_texto(self.in_especialidad, 300)
        self.in_especialidad.setPlaceholderText("Especialidad Académica")
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo, 200)
        self.in_correo.setPlaceholderText("Correo")
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono, 300)
        self.in_telefono.setPlaceholderText("Teléfono")
        self.in_horario= QLineEdit()
        limitar_campo_texto(self.in_horario, 300)
        self.in_horario.setPlaceholderText("Horario Laboral (ej. L-V 8am-2pm)")
        self.combo_estado= QComboBox()
        self.combo_estado.addItems(ESTADOS)
        conectar_tooltip_seleccion(self.combo_estado, "Estado laboral actual del profesor")
        lbl_cuenta= QLabel("Cuenta de acceso:")
        lbl_cuenta.setObjectName("DescModulo")
        self.combo_usuario= QComboBox()
        conectar_tooltip_seleccion(self.combo_usuario, "Cuenta de acceso (login) vinculada a este profesor")
        #Solo aplica en instituciones con módulo Politécnico activo: si este profesor también da clase de módulos
        #técnicos (además de, o en vez de, materias académicas normales), y en qué área técnica lo hace. Es
        #independiente de "Especialidad Académica" (texto libre, ej. "Matemáticas"): esto es su área técnica formal del
        #catálogo de Politécnico, la misma que usan Módulos Técnicos y Estudiantes.
        self.chk_imparte_tecnico= QCheckBox("Imparte módulo(s) técnico(s)")
        self.chk_imparte_tecnico.setToolTip(
            "Marca esta casilla si el profesor imparte Módulos Técnicos (Politécnico), "
            "además de o en vez de materias académicas normales.")
        self.chk_imparte_tecnico.toggled.connect(self._imparte_tecnico_cambio)
        self.combo_especialidad_tecnica= QComboBox()
        conectar_tooltip_seleccion(self.combo_especialidad_tecnica,
            "Área técnica principal en la que este profesor imparte módulos técnicos.")
        form.addWidget(self.in_nombre, 0, 0)
        form.addWidget(self.in_apellidos, 0, 1)
        form.addWidget(self.in_especialidad, 0, 2)
        form.addWidget(self.in_correo, 1, 0)
        form.addWidget(self.in_telefono, 1, 1)
        form.addWidget(self.in_horario, 1, 2)
        form.addWidget(self.combo_estado, 2, 0)
        form.addWidget(lbl_cuenta, 2, 1)
        form.addWidget(self.combo_usuario, 2, 2)
        form.addWidget(self.chk_imparte_tecnico, 3, 0)
        form.addWidget(self.combo_especialidad_tecnica, 3, 1, 1, 2)
        panel_layout.addLayout(form)

        #--- Foto del profesor ---
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
        self.in_buscar.setPlaceholderText("Buscar profesor…")
        self.in_buscar.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_buscar, 1)
        fila_busqueda.addWidget(self.marco_busqueda, 1)

        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._filtro_cambio)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador de búsqueda
        self.in_buscar.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        #Filtros de módulos técnicos: solo tienen sentido (y solo se muestran) en una institución con el módulo
        #Politécnico activo — ver
        #_actualizar_visibilidad_tecnico(). Igual que en Estudiantes, si no
        #aplican quedan ocultos y NO se usan como condición de filtrado, para no "romper" la búsqueda en instituciones
        #sin Politécnico. Estos combos viven en la ventanita de "☰ Filtros" (ver _construir_dialogo_filtros), no
        #apilados en esta fila de búsqueda.
        self.combo_filtro_imparte_tecnico= QComboBox()
        self.combo_filtro_imparte_tecnico.addItem("Todos", None)
        self.combo_filtro_imparte_tecnico.addItem("Imparte técnico", 1)
        self.combo_filtro_imparte_tecnico.addItem("No imparte técnico", 0)
        self.combo_filtro_imparte_tecnico.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_imparte_tecnico,
                                    "Filtrar por si el profesor imparte módulos técnicos")

        self.combo_filtro_area_tecnica= QComboBox()
        self.combo_filtro_area_tecnica.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_area_tecnica, "Filtrar por el área técnica que imparte el profesor")

        self.combo_filtro_estado= QComboBox()
        self.combo_filtro_estado.addItem("Todos los estados", None)
        for estado in ESTADOS:
            self.combo_filtro_estado.addItem(estado, estado)
        self.combo_filtro_estado.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_estado, "Filtrar por el estado laboral del profesor")

        self.btn_filtros= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros)
        self.btn_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros.setObjectName("BtnAccionNeutro")
        self.btn_filtros.setToolTip("Abrir panel de filtros (estado, módulos técnicos y área técnica)")
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

        self.lbl_vacio= QLabel("No se encontraron profesores con los filtros actuales.")
        self.lbl_vacio.setObjectName("AvisoVacio")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setVisible(False)
        tabla_card_layout.addWidget(self.lbl_vacio)


        self.tabla= QTableWidget(0, 10)
        aplicar_estructura_tabla(self.tabla)

        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Foto", "Nombre", "Apellidos", "Especialidad", "Área Técnica", "Correo", "Teléfono",
             "Estado", "Usuario Login"])
        self.tabla.setColumnHidden(0, True)
        configurar_columna_foto(self.tabla, 1)
        header= self.tabla.horizontalHeader()
        #Mismo criterio que estudiantes.py: TODAS las columnas en Interactive (ninguna en Stretch) y
        #setStretchLastSection en False. Antes, la columna "Nombre" (Stretch) y la última "Usuario Login" (por
        #setStretchLastSection(True)) competían entre sí por el espacio
        #sobrante y, al ser columnas Stretch, el usuario NO podía arrastrar su borde para ensancharlas/achicarlas a
        #mano -de ahí que "no dejara tocar algunos campos"-. Con todo en Interactive, cada columna se redimensiona
        #libremente y es la propia tabla la que saca su barra de scroll horizontal cuando la suma de anchos no cabe.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(90)
        #Anchos "de reposo" de cada columna (ver _ajustar_anchos_columnas de estudiantes.py / ajustar_anchos_columnas
        #de paginacion.py): sirven de piso para que una página con valores cortos no deje la tabla amontonada, y la
        #función respeta un techo para que un valor anormalmente largo tampoco la desborde.
        self._anchos_base_columnas= {
            1: 56, 2: 150, 3: 150, 4: 150, 5: 170, 6: 170, 7: 120, 8: 100, 9: 140,
        }
        for col, ancho in self._anchos_base_columnas.items():
            self.tabla.setColumnWidth(col, ancho)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        #Sin wrap, igual que estudiantes.py: un valor largo se queda en una sola línea y es la columna (dentro de su
        #techo) la que se ensancha para ese registro puntual, no el texto el que se parte en varias líneas dentro de la
        #celda.
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
            titulo= "Profesores", parent=self)

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

        self.btn_deshacer= BotonAnimado("Deshacer última eliminación")
        self.btn_deshacer.setObjectName("BtnAccionDeshacer")
        self.btn_deshacer.clicked.connect(self._deshacer_eliminacion)
        self.btn_deshacer.setVisible(False)
        fila_acciones.addWidget(self.btn_deshacer)
        self._ultima_eliminacion= None

        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla, self, titulo="Detalle del Profesor")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_acciones.addStretch()
        tabla_card_layout.addLayout(fila_acciones)

        disposicion.addWidget(self.frame_tabla, 1)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        self.actualizar_tema()

    def _elegir_foto(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "fotos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="prof")
        if not destino:
            return
        self.foto_path= destino
        self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(destino), 64))

    def _ver_foto_ampliada(self):

        if not self.foto_path or not os.path.exists(self.foto_path):
            mostrar_mensaje("advertencia", "Sin foto", "Este profesor no tiene una fotografía cargada.", self)
            return
        VisorFotoDialog(self.foto_path, self, titulo="Fotografía del Profesor").exec()

    def _quitar_foto(self):

        if not self.foto_path:
            mostrar_mensaje("advertencia", "Sin foto", "Este profesor no tiene una fotografía cargada.", self)
            return
        if mostrar_mensaje("pregunta", "Confirmar", "¿Quitar la fotografía de este profesor?", self) != QMessageBox.StandardButton.Yes:
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
                     WHERE usuarios.rol='Profesor' AND usuarios.id NOT IN (
                         SELECT usuario_id FROM profesores WHERE usuario_id IS NOT NULL
                         AND (?='' OR id != ?)
                     ) ORDER BY usuarios.username""", (self.id_edicion or "", self.id_edicion or -1))
        for fila in c.fetchall():
            etiqueta= fila["nombre_completo"] or fila["username"]
            self.combo_usuario.addItem(f"{etiqueta} ({fila['username']})", fila["id"])
        conn.close()

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo) — solo entonces tiene sentido preguntar si un
    #profesor imparte módulos técnicos y en qué área.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    def _cargar_combo_especialidad_tecnica(self):

        combo= self.combo_especialidad_tecnica
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— Selecciona un área técnica —", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _imparte_tecnico_cambio(self, marcado):

        self.combo_especialidad_tecnica.setEnabled(marcado)
        if not marcado:
            self.combo_especialidad_tecnica.setCurrentIndex(0)

    #Muestra/oculta todo lo relacionado a módulos técnicos: solo tiene
    #sentido en una institución con el módulo Politécnico activo. Si se oculta,
    #los filtros también se resetean a "Todos" para que no se queden aplicando
    #(invisibles) un filtro que ya no debería tener efecto.
    def _actualizar_visibilidad_tecnico(self):

        visible= self._es_politecnico()
        self.chk_imparte_tecnico.setVisible(visible)
        self.combo_especialidad_tecnica.setVisible(visible)
        if not visible:
            self.chk_imparte_tecnico.setChecked(False)
        self.tabla.setColumnHidden(5, not visible)
        self.combo_filtro_imparte_tecnico.setVisible(visible)
        self.combo_filtro_area_tecnica.setVisible(visible)
        if hasattr(self, "lbl_filtro_imparte_tecnico"):
            self.lbl_filtro_imparte_tecnico.setVisible(visible)
            self.lbl_filtro_area_tecnica.setVisible(visible)
        if not visible:
            self.combo_filtro_imparte_tecnico.setCurrentIndex(0)
            self.combo_filtro_area_tecnica.setCurrentIndex(0)

    def _cargar_combo_filtro_area_tecnica(self):

        combo= self.combo_filtro_area_tecnica
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todas las áreas técnicas", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Ventanita (no modal) con los filtros del listado de Profesores:
    #Estado, "Imparte técnico" y Área Técnica (los dos últimos solo
    #visibles/aplicables con el módulo Politécnico activo). Mismo patrón
    #que banco_tareas.py/calendario.py/horario.py.
    def _construir_dialogo_filtros(self):

        self.dialogo_filtros= QDialog(self)
        self.dialogo_filtros.setObjectName("DialogoFiltros")
        self.dialogo_filtros.setWindowTitle("Filtros de Profesores")
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

        lbl_subtitulo= QLabel("Todos son opcionales: combínalos con la búsqueda de arriba, "
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
        grid.addWidget(QLabel("Estado:"), 0, 0)
        grid.addWidget(self.combo_filtro_estado, 0, 1)
        self.lbl_filtro_imparte_tecnico= QLabel("Módulos técnicos:")
        grid.addWidget(self.lbl_filtro_imparte_tecnico, 1, 0)
        grid.addWidget(self.combo_filtro_imparte_tecnico, 1, 1)
        self.lbl_filtro_area_tecnica= QLabel("Área Técnica:")
        grid.addWidget(self.lbl_filtro_area_tecnica, 2, 0)
        grid.addWidget(self.combo_filtro_area_tecnica, 2, 1)
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

        for combo in (self.combo_filtro_estado, self.combo_filtro_imparte_tecnico, self.combo_filtro_area_tecnica):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _guardar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para editar profesores.", self)
            return
        if not self.in_nombre.text().strip():
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        usuario_id= self.combo_usuario.currentData()
        imparte_tecnico= 1 if (self._es_politecnico() and self.chk_imparte_tecnico.isChecked()) else 0
        especialidad_tecnica_id= self.combo_especialidad_tecnica.currentData() if imparte_tecnico else None
        datos= (self.in_nombre.text().strip(), self.in_apellidos.text().strip(),
                 self.in_especialidad.text().strip(), self.in_correo.text().strip(),
                 self.in_telefono.text().strip(), self.in_horario.text().strip(),
                 self.combo_estado.currentText(), self.foto_path, usuario_id,
                 imparte_tecnico, especialidad_tecnica_id)
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            if self.id_edicion is None:
                c.execute("""INSERT INTO profesores (nombre, apellidos, especialidad, correo, telefono,
                             horario_laboral, estado, foto, usuario_id, imparte_tecnico, especialidad_tecnica_id)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?)""", datos)
                accion= "Registró profesor"
            else:
                c.execute("""UPDATE profesores SET nombre=?, apellidos=?, especialidad=?, correo=?,
                             telefono= ?, horario_laboral=?, estado=?, foto=?, usuario_id=?, imparte_tecnico=?,
                             especialidad_tecnica_id= ? WHERE id=?""",
                          datos + (self.id_edicion,))
                accion= "Editó profesor"
            conn.commit()
            conn.close()
        except Exception as error:
            self._destello("#EF4444")
            mostrar_mensaje("error", "Error", f"No se pudo guardar el profesor:\n{error}", self)
            return
        registrar_auditoria("Profesores", accion, self.main_window.usuario_actual, self.in_nombre.text().strip())
        self._destello("#22C55E")
        mostrar_mensaje("exito", "Guardado", "El profesor se guardó correctamente.", self)
        self._limpiar()
        self.refrescar()

    def _limpiar(self):

        self.id_edicion= None
        self.foto_path= ""
        self.lbl_foto.setText("Sin\nfoto")
        self.lbl_foto.setPixmap(QPixmap())
        for campo in (self.in_nombre, self.in_apellidos, self.in_especialidad,
                      self.in_correo, self.in_telefono, self.in_horario):
            campo.clear()
        self.combo_estado.setCurrentIndex(0)
        self.chk_imparte_tecnico.setChecked(False)
        self.combo_especialidad_tecnica.setCurrentIndex(0)
        self._cargar_combo_usuarios()
        desactivar_modo_edicion(self.in_nombre)

    def _cargar_seleccionado(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un profesor de la tabla.", self)
            return
        id_prof= int(self.tabla.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM profesores WHERE id=?", (id_prof,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self.id_edicion= f["id"]
        self.in_nombre.setText(f["nombre"] or "")
        self.in_apellidos.setText(f["apellidos"] or "")
        self.in_especialidad.setText(f["especialidad"] or "")
        self.in_correo.setText(f["correo"] or "")
        self.in_telefono.setText(f["telefono"] or "")
        self.in_horario.setText(f["horario_laboral"] or "")
        self.combo_estado.setCurrentText(f["estado"] or "Activo")
        self.foto_path= f["foto"] or "" if "foto" in f.keys() else ""
        if self.foto_path and os.path.exists(self.foto_path):
            self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(self.foto_path), 64))
        else:
            self.lbl_foto.setText("Sin\nfoto")
            self.lbl_foto.setPixmap(QPixmap())
        self._cargar_combo_usuarios()
        idx= self.combo_usuario.findData(f["usuario_id"])
        self.combo_usuario.setCurrentIndex(idx if idx >= 0 else 0)
        self._cargar_combo_especialidad_tecnica()
        imparte= bool(f["imparte_tecnico"]) if "imparte_tecnico" in f.keys() else False
        self.chk_imparte_tecnico.setChecked(imparte)
        if imparte and "especialidad_tecnica_id" in f.keys():
            idx_esp= self.combo_especialidad_tecnica.findData(f["especialidad_tecnica_id"])
            self.combo_especialidad_tecnica.setCurrentIndex(idx_esp if idx_esp >= 0 else 0)
        activar_modo_edicion(self.in_nombre,
                             f"Editando profesor: {f['nombre'] or ''} {f['apellidos'] or ''}".strip())

    def _eliminar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para eliminar profesores.", self)
            return
        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un profesor de la tabla.", self)
            return
        id_prof= int(self.tabla.item(fila, 0).text())
        nombre= self.tabla.item(fila, 2).text()
        if mostrar_mensaje("pregunta", "Confirmar", f"¿Eliminar a '{nombre}'?", self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        fila_completa= c.execute("SELECT * FROM profesores WHERE id=?", (id_prof,)).fetchone()
        if fila_completa is None:
            conn.close()
            return
        datos_respaldo= dict(fila_completa)
        c.execute("DELETE FROM profesores WHERE id=?", (id_prof,))
        conn.commit()
        conn.close()
        registrar_auditoria("Profesores", "Eliminó profesor", self.main_window.usuario_actual, nombre)

        #Guardamos un respaldo de la última eliminación para poder deshacerla. Solo se conserva UN nivel de deshacer
        #(la última acción).
        self._ultima_eliminacion= datos_respaldo
        self.btn_deshacer.setVisible(True)
        self.btn_deshacer.setEnabled(True)

        self.refrescar()

    #Restaura el último profesor eliminado desde esta pantalla, tal cual
    #estaba (mismo id y mismos datos). Solo funciona una vez por eliminación.
    def _deshacer_eliminacion(self):

        if not self._ultima_eliminacion:
            return
        datos= self._ultima_eliminacion
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("""INSERT INTO profesores
                         (id, nombre, apellidos, especialidad, correo, telefono,
                          horario_laboral, estado, foto, usuario_id, imparte_tecnico, especialidad_tecnica_id)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (datos["id"], datos["nombre"], datos["apellidos"], datos["especialidad"],
                       datos["correo"], datos["telefono"], datos["horario_laboral"], datos["estado"],
                       datos["foto"], datos["usuario_id"], datos.get("imparte_tecnico") or 0,
                       datos.get("especialidad_tecnica_id")))
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "No se pudo deshacer",
                             f"No fue posible restaurar al profesor (puede que ya exista un registro con "
                             f"algún conflicto): {error}", self)
            conn.close()
            return
        conn.close()
        registrar_auditoria("Profesores", "Deshizo eliminación de profesor",
                             self.main_window.usuario_actual, datos.get("nombre", ""))
        self._ultima_eliminacion= None
        self.btn_deshacer.setVisible(False)
        mostrar_mensaje("info", "Restaurado", f"'{datos['nombre']}' fue restaurado correctamente.", self)
        self.refrescar()

    def _filtro_cambio(self, texto=""):

        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _cargar_tabla(self):

        texto= _normalizar(self.in_buscar.text().strip())
        filtro_imparte= self.combo_filtro_imparte_tecnico.currentData()\
            if self.combo_filtro_imparte_tecnico.isVisible() else None
        filtro_area= self.combo_filtro_area_tecnica.currentData()\
            if self.combo_filtro_area_tecnica.isVisible() else None
        filtro_estado= self.combo_filtro_estado.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT profesores.*, usuarios.username as username,
                     especialidades.nombre as especialidad_tecnica_nombre
                     FROM profesores
                     LEFT JOIN usuarios ON profesores.usuario_id = usuarios.id
                     LEFT JOIN especialidades ON profesores.especialidad_tecnica_id = especialidades.id
                     ORDER BY apellidos, nombre""")
        filas= c.fetchall()
        conn.close()
        filtradas= []
        #f: fila del resultado de la consulta
        for f in filas:
            if texto and texto not in _normalizar(f"{f['nombre']} {f['apellidos']}"):
                continue
            if filtro_imparte is not None and (f["imparte_tecnico"] or 0) != filtro_imparte:
                continue
            if filtro_area is not None and f["especialidad_tecnica_id"] != filtro_area:
                continue
            if filtro_estado is not None and (f["estado"] or "Activo") != filtro_estado:
                continue
            filtradas.append(f)
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
                    #Sin foto guardada todavía: círculo placeholder con silueta, en vez de dejar la celda completamente vacía.
                    item_foto.setData(Qt.ItemDataRole.DecorationRole,
                                       pixmap_placeholder_foto_tabla(TAMANO_FOTO_TABLA))
                self.tabla.setItem(i, 1, item_foto)
                self.tabla.setItem(i, 2, QTableWidgetItem(f["nombre"] or ""))
                self.tabla.setItem(i, 3, QTableWidgetItem(f["apellidos"] or ""))
                self.tabla.setItem(i, 4, QTableWidgetItem(f["especialidad"] or ""))
                if "imparte_tecnico" in f.keys() and f["imparte_tecnico"]:
                    texto_tecnico= f["especialidad_tecnica_nombre"] or "Sí (sin área definida)"
                else:
                    texto_tecnico= "—"
                self.tabla.setItem(i, 5, QTableWidgetItem(texto_tecnico))
                self.tabla.setItem(i, 6, QTableWidgetItem(f["correo"] or ""))
                self.tabla.setItem(i, 7, QTableWidgetItem(f["telefono"] or ""))
                item_estado= QTableWidgetItem(f["estado"] or "")
                if (f["estado"] or "") == "Activo":
                    item_estado.setForeground(QColor("#16A34A"))
                else:
                    item_estado.setForeground(QColor("#DC2626"))
                self.tabla.setItem(i, 8, item_estado)
                self.tabla.setItem(i, 9, QTableWidgetItem(f["username"] or "Sin vincular"))
            self.tabla.resizeRowsToContents()
            ajustar_anchos_columnas(self.tabla)
        self._animar_contador(len(filtradas))
        self._animar_fundido_tabla()

    def refrescar(self):

        if self.acceso_restringido:
            return
        self._cargar_combo_usuarios()
        self._cargar_combo_especialidad_tecnica()
        self._cargar_combo_filtro_area_tecnica()
        self._actualizar_visibilidad_tecnico()
        self._cargar_tabla()

    #Sincroniza los colores de las tarjetas y acentos de este módulo con el
    #tema/modo claro-oscuro actual de la app. Se llama al construir la pantalla
    #y cada vez que el usuario cambia de tema (ver main.py).
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
        if hasattr(self, "chip_contador"):
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
        if self.acceso_restringido:
            if hasattr(self, "frame_restringido"):
                self.frame_restringido.setStyleSheet(f"""
                    QFrame#TarjetaFormulario {{
                        background-color: {colores['bg_panel']};
                        border: 1px solid {colores['bg_btn']};
                        border-radius: 16px;
                    }}
                """)
            return
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
    #Actualiza el chip '👨🏫 N profesores' de la cabecera con una pequeña
    #animación de conteo, en vez de un cambio brusco de texto.
    def _animar_contador(self, valor_final):

        if not hasattr(self, "chip_contador"):
            return

        def texto(v):

            return f"{html_icono_emoji(EMOJI_PROFESOR, 15)} {v} profesor" + ("es" if v != 1 else "")
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
        #v: valor actual del slider, que se muestra como porcentaje
        anim.valueChanged.connect(lambda v: self.chip_contador.setText(texto(int(v))))
        anim.start()
        self._anim_contador= anim  #referencia viva mientras corre la animación

    #Fundido breve al recargar la tabla, como confirmación visual de que los
    #datos se actualizaron. El efecto se retira apenas termina para no afectar
    #el rendimiento del scroll normal de la tabla el resto del tiempo.
    def _animar_fundido_tabla(self):

        efecto= QGraphicsOpacityEffect(self.tabla)
        self.tabla.setGraphicsEffect(efecto)
        anim= QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        anim.finished.connect(lambda: self.tabla.setGraphicsEffect(None))
        anim.start()
        self._anim_tabla= anim  #referencia viva mientras corre la animación

    #Resplandor breve de color en el borde de la tarjeta del formulario, a
    #modo de confirmación visual (verde=éxito, rojo=aviso). Solo anima la
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