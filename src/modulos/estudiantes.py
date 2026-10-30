import os
import unicodedata
from datetime import datetime
from src.nucleo.formato_hora import aplicar_formato_widget_fecha
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QDateEdit, QGridLayout, QScrollArea, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy, QAbstractScrollArea, QDialog)
from PySide6.QtCore import (Qt, QDate, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve,
    QVariantAnimation, QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen
from src.nucleo.bd import (obtener_conexion, registrar_auditoria, obtener_carpeta_datos,
                resolver_nivel_academico_de_seccion, recalcular_numeros_lista, mostrar_columna_numero_lista)
from src.interfaz.filtros_curso_seccion import (poblar_combo_curso, cascada_seccion_por_curso,
    preseleccionar_curso_y_seccion)
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.nucleo.permisos import puede_editar, es_profesor_restringido, obtener_secciones_permitidas
from src.interfaz.foto_utils import seleccionar_y_recortar_foto, VisorFotoDialog
from src.interfaz.paginacion import (ControlPaginacion, agregar_boton_detalle, tabla_pausada,
    obtener_pixmap_circular_cacheado, ROL_RUTA_FOTO,
    configurar_columna_foto, pixmap_placeholder_foto_tabla, TAMANO_FOTO_TABLA, agregar_boton_pantalla_completa)
from src.nucleo.datos_locales_docente import (obtener_override_estudiante, listar_overrides_estudiantes,
    guardar_override_estudiante, eliminar_override_estudiante, aplicar_override)
from src.interfaz.configuracion import (NIVELES_ACADEMICOS, niveles_academicos_habilitados, puede_tener_componente_tecnico,
                            conectar_tooltip_seleccion)
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, html_icono_emoji,
                          icono_boton_filtro, pixmap_boton_filtro, EMOJI_IMPORTAR, EMOJI_EXPORTAR, EMOJI_FOTO_RECORTAR)
from src.interfaz.intercambio_dialogs import DialogoExportarEstudiantes, DialogoImportarEstudiantes
from src.interfaz.edicion_feedback import activar_modo_edicion, desactivar_modo_edicion

SEXOS= ["Masculino", "Femenino"]
ESTADOS= ["Activo", "Inactivo"]


#Utilidades visuales — puramente estéticas, no tocan datos ni lógica.
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
            "txt_sec": paleta["text_secondary"][idx],
            "txt_prim": paleta["text_primary"][idx],
            "accent": paleta["btn_op_bg"][idx],
            "accent_hv": paleta["btn_op_hover"][idx],
        }
    except Exception:
        return {"bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0", "txt_sec": "#64748B",
                "txt_prim": "#0F172A", "accent": "#2563EB", "accent_hv": "#1D4ED8"}


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


class ModuloEstudiantes(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.id_edicion= None
        self.foto_path= ""
        self._especialidad_disponible= False
        self._carrera_disponible= False
        self._construir_ui()
        self.refrescar()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Estudiantes"
        #_guardar ya distingue internamente entre "guardar override local del docente" (datos_locales_docente.py) y
        #"guardar en la BD institucional" según es_profesor_restringido, así que el atajo es seguro para ambos roles
        #sin necesidad de duplicar esa lógica aquí.
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar estudiante", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+L", "Limpiar formulario", self._limpiar)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Cargar estudiante seleccionado",
                         self._cargar_seleccionado)
        registrar_atajo(self, self.main_window, "Ctrl+Shift+F", "Filtros avanzados",
                         self._abrir_dialogo_filtros)
        #Eliminar un estudiante (y deshacer esa eliminación) es una acción sobre la ficha institucional, no sobre el
        #override local del docente: se omite por completo en Modo Docente.
        registrar_atajo(self, self.main_window, "Ctrl+Del", "Eliminar estudiante",
                         self._eliminar, solo_no_docente=True)
        registrar_atajo(self, self.main_window, "Ctrl+Z", "Deshacer eliminación",
                         self._deshacer_eliminacion, solo_no_docente=True)

    #Navegación desde otros módulos (p. ej. la tarjeta "Mis Secciones" del Dashboard de Docente: en vez de llevar a
    #una pantalla aparte, aterriza aquí mismo con el filtro de Curso/Sección ya abierto y listo para elegir, porque
    #para un docente "ver sus secciones" es, en la práctica, ver quién está en cada una).
    def showEvent(self, evento):

        super().showEvent(evento)
        pendiente= getattr(self.main_window, "_pestana_pendiente_dashboard", None)
        if pendiente == "secciones":
            self.main_window._pestana_pendiente_dashboard= None
            self._abrir_dialogo_filtros()
            QTimer.singleShot(0, self.combo_filtro_grado.showPopup)

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

        restringido_ui= es_profesor_restringido(self.main_window)

        #--- Cabecera tipo "hero": icono + título + descripción + contador animado ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Estudiantes")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        titulo_modulo= "Mis Estudiantes" if restringido_ui else "Estudiantes"
        self.lbl_titulo_cabecera= QLabel(titulo_modulo)
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        subtitulo_modulo= ("Personaliza los datos de contacto de tus estudiantes en este equipo"
                             if restringido_ui else
                             "Administra la ficha completa de los estudiantes de la institución")
        self.lbl_subtitulo_cabecera= QLabel(subtitulo_modulo)
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        self.chip_contador= QLabel(f"{html_icono_emoji('👥', 15)} 0 estudiantes")
        self.chip_contador.setObjectName("ChipContador")
        self.chip_contador.setTextFormat(Qt.TextFormat.RichText)
        self._contador_valor_actual= 0
        cabecera_layout.addWidget(self.chip_contador, 0, Qt.AlignmentFlag.AlignVCenter)

        if restringido_ui:
            self.btn_info_docente= BotonAnimado("¿Cómo funciona esto?")
            self.btn_info_docente.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #6366F1, stop:1 #8B5CF6);
                    color: white;
                    border: none;
                    border-radius: 16px;
                    padding: 7px 16px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4F46E5, stop:1 #7C3AED);
                }
                QPushButton:pressed {
                    background: #4338CA;
                }
            """)
            self.btn_info_docente.clicked.connect(self._mostrar_info_docente)
            cabecera_layout.addWidget(self.btn_info_docente)
        disposicion.addWidget(self.frame_cabecera)

        #--- Panel de creación/edición (oculto por completo para Profesor) ---
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

        titulo_ficha= ("Ficha del estudiante (personalización local)" if restringido_ui
                         else "Ficha del estudiante")
        lbl_titulo_ficha= QLabel(titulo_ficha)
        lbl_titulo_ficha.setObjectName("TituloTarjetaInterna")
        panel_layout.addWidget(lbl_titulo_ficha)

        #--- Formulario ---
        form_frame= QGridLayout()
        self.in_matricula= QLineEdit()
        limitar_campo_texto(self.in_matricula, 300)
        self.in_matricula.setPlaceholderText("Matrícula (autogenerada)")
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre, 300)
        self.in_nombre.setPlaceholderText("Nombre")
        self.in_apellidos= QLineEdit()
        limitar_campo_texto(self.in_apellidos, 300)
        self.in_apellidos.setPlaceholderText("Apellidos")
        self.combo_sexo= QComboBox()
        self.combo_sexo.addItems(SEXOS)
        conectar_tooltip_seleccion(self.combo_sexo, "Sexo del estudiante")
        self.in_date_nacimiento= QDateEdit(calendarPopup=True)
        self.in_date_nacimiento.setDate(QDate(2010, 1, 1))
        aplicar_formato_widget_fecha(self.in_date_nacimiento, self.main_window)
        self.in_documento= QLineEdit()
        limitar_campo_texto(self.in_documento, 300)
        self.in_documento.setPlaceholderText("Documento de Identidad")
        self.in_direccion= QLineEdit()
        limitar_campo_texto(self.in_direccion, 300)
        self.in_direccion.setPlaceholderText("Dirección")
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono, 300)
        self.in_telefono.setPlaceholderText("Teléfono")
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo, 200)
        self.in_correo.setPlaceholderText("Correo")
        self.in_tutor= QLineEdit()
        limitar_campo_texto(self.in_tutor, 300)
        self.in_tutor.setPlaceholderText("Tutor / Padre 1 (obligatorio)")
        self.in_tutor2= QLineEdit()
        limitar_campo_texto(self.in_tutor2, 300)
        self.in_tutor2.setPlaceholderText("Tutor / Padre 2 (opcional)")
        #Curso/Grado va PRIMERO y es obligatorio: acota de una vez la lista de Secciones a las de ese curso (igual que
        #en la pestaña de Horarios de Materias). Mientras no se elija un curso, Sección queda vacía, para que no pueda
        #quedar seleccionada por accidente una sección de otro curso.
        self.combo_grado_ficha= QComboBox()
        self.combo_grado_ficha.setToolTip("Grado/curso del estudiante (obligatorio) — elige primero aquí para "
                                           "acotar la lista de secciones de abajo")
        self.combo_grado_ficha.addItem("Selecciona un curso/grado…", None)
        self.combo_grado_ficha.currentIndexChanged.connect(self._grado_ficha_cambio)
        self.combo_seccion= QComboBox()
        self.combo_seccion.setToolTip("Sección a la que pertenece el estudiante (obligatorio)")
        self.combo_seccion.addItem("Selecciona primero un curso/grado…", None)
        self.combo_seccion.currentIndexChanged.connect(self._actualizar_profesor_guia)
        self.combo_estado= QComboBox()
        self.combo_estado.addItems(ESTADOS)
        conectar_tooltip_seleccion(self.combo_estado, "Estado de matrícula del estudiante (Activo/Inactivo)")
        self.combo_especialidad_estudiante= QComboBox()
        conectar_tooltip_seleccion(self.combo_especialidad_estudiante,
            "Área técnica del estudiante (obligatorio en Politécnico). Se usa para filtrar "
            "estudiantes por área técnica.")
        self.combo_carrera_estudiante= QComboBox()
        conectar_tooltip_seleccion(self.combo_carrera_estudiante,
            "Carrera del estudiante (obligatorio en Universidad). Se usa para filtrar "
            "estudiantes por carrera.")

        #Los campos se van colocando en una grilla de 4 columnas, en orden. Para el docente (que no ve Matrícula) se
        #omite ese campo del flujo, así el resto no deja huecos ni queda desalineado.
        restringido_ui= es_profesor_restringido(self.main_window)
        campos_en_orden= []
        if not restringido_ui:
            campos_en_orden.append(self.in_matricula)
        campos_en_orden += [self.in_nombre, self.in_apellidos, self.combo_sexo, self.in_date_nacimiento,
                             self.in_documento, self.in_direccion, self.in_telefono, self.in_correo,
                             self.in_tutor, self.in_tutor2, self.combo_grado_ficha, self.combo_seccion,
                             self.combo_estado, self.combo_especialidad_estudiante, self.combo_carrera_estudiante]
        for indice, campo in enumerate(campos_en_orden):
            fila, columna= divmod(indice, 4)
            form_frame.addWidget(campo, fila, columna)

        fila_ultima, _= divmod(len(campos_en_orden) - 1, 4)
        fila_siguiente= fila_ultima + 1  #siempre una fila nueva y vacía, sin importar en qué
        #columna haya terminado la grilla de campos (evita que esta fila se solape con la última).

        self.lbl_profesor_guia= QLabel("Profesor guía: —")
        self.lbl_profesor_guia.setObjectName("DescModulo")

        btn_regenerar_matricula= BotonAnimado("Autogenerar Matrícula")
        btn_regenerar_matricula.setObjectName("BtnAccionNeutro")
        btn_regenerar_matricula.clicked.connect(self._autogenerar_matricula)

        if restringido_ui:
            #Sin botón de matrícula: la etiqueta del profesor guía ocupa toda la fila.
            form_frame.addWidget(self.lbl_profesor_guia, fila_siguiente, 0, 1, 4)
        else:
            form_frame.addWidget(btn_regenerar_matricula, fila_siguiente, 0)
            form_frame.addWidget(self.lbl_profesor_guia, fila_siguiente, 1, 1, 3)
        panel_layout.addLayout(form_frame)

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

        self.btn_restablecer_local= BotonAnimado("Restablecer al original")
        self.btn_restablecer_local.setObjectName("BtnAccionNeutro")
        self.btn_restablecer_local.setToolTip(
            "Elimina tu personalización local (datos de contacto/foto) y vuelve a mostrar "
            "los datos oficiales de Dirección/Coordinación para este estudiante.")
        self.btn_restablecer_local.clicked.connect(self._restablecer_override)
        self.btn_restablecer_local.setVisible(es_profesor_restringido(self.main_window))
        fila_foto.addWidget(self.btn_restablecer_local)

        btn_importar= BotonAnimado("Importar Excel/CSV")
        btn_importar.setObjectName("BtnAccionAjustar")
        btn_importar.setIcon(icono_emoji(EMOJI_IMPORTAR))
        btn_importar.setIconSize(_QSize_emoji(16, 16))
        btn_importar.clicked.connect(self._importar_excel_csv)
        fila_foto.addWidget(btn_importar)

        panel_layout.addLayout(fila_foto)

        #Intercambio entre ediciones (ver intercambio_datos.py): a diferencia de "Importar Excel/CSV" (institucional,
        #oculto para el Profesor más abajo), esto también se ofrece al Profesor -en Single Teacher es, de hecho, la
        #única vía de intercambiar datos con otra instalación, porque no hay overrides institucionales de por medio. Va
        #en una fila propia, debajo de la fila de foto/Importar Excel, para no ensanchar el panel.
        fila_intercambio= QHBoxLayout()
        fila_intercambio.setSpacing(8)
        fila_intercambio.addStretch()

        btn_exportar_intercambio= BotonAnimado("Exportar a otra edición")
        btn_exportar_intercambio.setObjectName("BtnAccionNeutro")
        btn_exportar_intercambio.setIcon(icono_emoji(EMOJI_EXPORTAR))
        btn_exportar_intercambio.setIconSize(_QSize_emoji(16, 16))
        btn_exportar_intercambio.setToolTip(
            "Genera un archivo .acdxpkg con estos estudiantes para importarlo en otra "
            "instalación de AcaDeXI (misma edición u otra).")
        btn_exportar_intercambio.clicked.connect(self._abrir_exportar_intercambio)
        fila_intercambio.addWidget(btn_exportar_intercambio)

        btn_importar_intercambio= BotonAnimado("Importar de otra edición")
        btn_importar_intercambio.setObjectName("BtnAccionNeutro")
        btn_importar_intercambio.setIcon(icono_emoji(EMOJI_IMPORTAR))
        btn_importar_intercambio.setIconSize(_QSize_emoji(16, 16))
        btn_importar_intercambio.setToolTip(
            "Importa un archivo .acdxpkg de estudiantes generado por otra instalación de AcaDeXI.")
        btn_importar_intercambio.clicked.connect(self._abrir_importar_intercambio)
        fila_intercambio.addWidget(btn_importar_intercambio)

        panel_layout.addLayout(fila_intercambio)

        disposicion.addWidget(self.panel_edicion)
        #El panel es visible también para el Profesor: puede retocar localmente TODOS los datos de SUS estudiantes (ver
        #_guardar_override_local). Solo se ocultan las herramientas que son inherentemente institucionales: generar una
        #matrícula oficial nueva y la importación masiva desde Excel/CSV.
        if es_profesor_restringido(self.main_window):
            btn_regenerar_matricula.setVisible(False)
            btn_importar.setVisible(False)
            #La matrícula es un dato institucional: el docente puede ver/editar todo lo demás de sus estudiantes, pero
            #nunca la matrícula.
            self.in_matricula.setVisible(False)

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
        self.in_buscar.setPlaceholderText("Buscar por nombre, apellido o matrícula…")
        self.in_buscar.setStyleSheet("QLineEdit { border: none; background: transparent; padding: 8px 0; }")
        lay_busqueda.addWidget(self.in_buscar, 1)
        fila_busqueda.addWidget(self.marco_busqueda, 1)

        self._temporizador_busqueda= QTimer(self)
        self._temporizador_busqueda.setSingleShot(True)
        self._temporizador_busqueda.setInterval(150)
        self._temporizador_busqueda.timeout.connect(self._filtro_cambio)
        #_t: texto escrito que no se usa; cada tecla reinicia el temporizador de búsqueda
        self.in_buscar.textChanged.connect(lambda _t: self._temporizador_busqueda.start())

        #Los combos de filtro (Grado, Sección, Área Técnica, Carrera, Sexo, Estado) NO van en esta barra: con varios
        #activos a la vez, empujan la tabla y rompen el ancho disponible junto al sidebar. En vez de eso, viven dentro
        #de un diálogo aparte que se abre con este botón (ver _construir_dialogo_filtros / _abrir_dialogo_filtros).
        self.btn_filtros= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros)
        self.btn_filtros.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros.setObjectName("BtnAccionNeutro")
        self.btn_filtros.setToolTip("Abrir panel de filtros (grado, sección, área técnica, carrera, sexo, estado)")
        self.btn_filtros.clicked.connect(self._abrir_dialogo_filtros)
        fila_busqueda.addWidget(self.btn_filtros)
        disposicion.addWidget(self.frame_filtros)

        #Combos de filtro: se crean aquí (siguen siendo atributos normales del módulo, igual que antes) pero se colocan
        #dentro del diálogo, no en fila_busqueda. self._especialidad_disponible/self._carrera_disponible (ver
        #_cargar_especialidades_combo_filtro/_cargar_carreras_combo_filtro) controlan si esos dos filtros aplican — NO
        #se usa combo.isVisible(), porque con el diálogo cerrado todo widget dentro reporta isVisible() en False aunque
        #el usuario sí haya elegido un valor.
        self.combo_filtro_nivel= QComboBox()
        self.combo_filtro_nivel.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_nivel,
            "Filtrar por nivel educativo (Primaria/Secundaria/Preparatoria/Universidad). Se combina con "
            "el resto de filtros -por ejemplo, Secundaria + un Grado + una Sección a la vez.")

        self.combo_filtro_grado= QComboBox()
        self.combo_filtro_grado.setToolTip("Filtrar la tabla por grado")
        self.combo_filtro_grado.currentIndexChanged.connect(self._grado_filtro_cambio)

        self.combo_filtro_seccion= QComboBox()
        self.combo_filtro_seccion.setToolTip("Filtrar la tabla por sección")
        self.combo_filtro_seccion.currentIndexChanged.connect(self._filtro_cambio)

        self.lbl_filtro_especialidad= QLabel("Área Técnica:")
        self.combo_filtro_especialidad= QComboBox()
        self.combo_filtro_especialidad.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_especialidad,
                                    "Filtrar por área técnica del estudiante (Politécnico)")

        self.lbl_filtro_carrera= QLabel("Carrera:")
        self.combo_filtro_carrera= QComboBox()
        self.combo_filtro_carrera.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_carrera, "Filtrar por carrera del estudiante (Universidad)")

        self.combo_filtro_sexo= QComboBox()
        self.combo_filtro_sexo.addItem("Todos (M/F)", None)
        for sexo in SEXOS:
            self.combo_filtro_sexo.addItem(sexo, sexo)
        self.combo_filtro_sexo.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_sexo, "Filtrar por sexo del estudiante")

        self.combo_filtro_estado= QComboBox()
        self.combo_filtro_estado.addItem("Todos los estados", None)
        for estado in ESTADOS:
            self.combo_filtro_estado.addItem(estado, estado)
        self.combo_filtro_estado.currentIndexChanged.connect(self._filtro_cambio)
        conectar_tooltip_seleccion(self.combo_filtro_estado, "Filtrar por estado del estudiante")

        self._construir_dialogo_filtros()

        #--- Tabla --- En Modo Docente la columna 1 muestra la Foto (como en Profesores del modo admin) en vez de la
        #Matrícula: el docente puede editar todo lo demás de sus estudiantes, pero la matrícula es un dato
        #institucional y no debe ni verse ni editarse desde aquí. En Director/Admin la tabla se mantiene igual que
        #siempre (Matrícula visible).
        self.frame_tabla= QFrame()
        self.frame_tabla.setObjectName("TarjetaTabla")
        tabla_card_layout= QVBoxLayout(self.frame_tabla)
        tabla_card_layout.setContentsMargins(18, 16, 18, 14)
        tabla_card_layout.setSpacing(10)

        self.lbl_vacio= QLabel("No se encontraron estudiantes con los filtros actuales.")
        self.lbl_vacio.setObjectName("AvisoVacio")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setVisible(False)
        tabla_card_layout.addWidget(self.lbl_vacio)


        self.tabla= QTableWidget(0, 14)
        etiqueta_col1= "Foto" if restringido_ui else "Matrícula"
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "No.", etiqueta_col1, "Nombre", "Apellidos", "Sexo", "Grado", "Sección", "Área Técnica",
             "Carrera", "Teléfono", "Tutor 1", "Tutor 2", "Estado"])
        self.tabla.setColumnHidden(0, True)
        header= self.tabla.horizontalHeader()
        #Interactive en todas las columnas (incluida la 2, que antes se forzaba a Stretch): así cada columna conserva
        #un ancho mínimo legible y, si la suma supera el ancho visible de la tabla, es la tabla la que saca su propia
        #barra horizontal en vez de aplastar
        #el contenido. setStretchLastSection en False por la misma razón:
        #con él activo la última columna siempre "rellenaba" el espacio sobrante y nunca dejaba que apareciera el
        #scroll horizontal.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(90)
        #"No." (columna 1) es la excepción: es solo un número corto (1, 2,
        #3...), así que se le permite un ancho más angosto que el resto de
        #columnas, en vez de forzarla a los mismos 90px de una Matrícula o un Nombre.
        self.tabla.setColumnWidth(1, 48)
        header.resizeSection(1, 48)
        #Anchos "de reposo": lo que ocupa cada columna con un valor normal. Se guardan para poder volver a ellos cada
        #vez que se recarga la
        #tabla (ver _ajustar_anchos_columnas) y así nunca quedan más
        #angostas que esto, aunque sí pueden crecer más si un registro trae un valor demasiado largo.
        self._anchos_base_columnas= {
            2: (TAMANO_FOTO_TABLA + 22) if restringido_ui else 110,
            3: 150, 4: 150, 5: 100, 6: 110, 7: 110, 8: 140, 9: 140, 10: 110, 11: 150, 12: 150, 13: 100,
        }
        for col, ancho in self._anchos_base_columnas.items():
            self.tabla.setColumnWidth(col, ancho)
        if restringido_ui:
            #Ver configurar_columna_foto en paginacion.py: fija setIconSize al mismo tamaño de la miniatura circular para
            #que la fila reserve el alto correcto y la foto no se vea "cortada".
            configurar_columna_foto(self.tabla, 1)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        #Sin wrap: un valor largo (nombre, tutor, etc.) se queda en una sola línea. Combinado con
        #_ajustar_anchos_columnas(), eso hace que sea la columna la que se ensancha para ese registro puntual —y por lo
        #tanto la tabla la que saca su barra horizontal— en vez de que el texto se parta en varias líneas dentro de la
        #celda.
        self.tabla.setWordWrap(False)
        self.tabla.verticalHeader().setVisible(False)
        #La tabla es su propia área de scroll (QTableWidget hereda de QAbstractScrollArea), así que le damos un tamaño
        #acotado —no ilimitado— y dejamos que sean SUS barras (vertical y horizontal) las que aparezcan al crecer el
        #contenido, en vez de dejar que la tabla empuje hacia abajo el resto de la página (paginación, botones) o que
        #la página entera se convierta en la única que scrollea.
        self.tabla.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabla.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.tabla.setMinimumHeight(420)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tabla_card_layout.addWidget(self.tabla, 1)

        self.paginacion= ControlPaginacion(tamano_inicial=10)
        self.paginacion.cambio.connect(self._cargar_tabla)
        tabla_card_layout.addWidget(self.paginacion)

        agregar_boton_pantalla_completa(
            None, [self.tabla, self.paginacion],
            titulo= "Estudiantes", parent=self)

        fila_acciones= QHBoxLayout()
        self.btn_editar= BotonAnimado("Cargar Seleccionado")
        self.btn_editar.setIcon(icono_emoji("✏"))
        self.btn_editar.setIconSize(_QSize_emoji(16, 16))
        self.btn_editar.setObjectName("BtnAccionEditar")
        self.btn_editar.clicked.connect(self._cargar_seleccionado)
        fila_acciones.addWidget(self.btn_editar)

        self.btn_eliminar= BotonAnimado("Eliminar")
        self.btn_eliminar.setObjectName("BtnAccionEliminar")
        self.btn_eliminar.clicked.connect(self._eliminar)
        fila_acciones.addWidget(self.btn_eliminar)
        btn_detalle= agregar_boton_detalle(fila_acciones, self.tabla, self, titulo="Detalle del Estudiante")
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla.doubleClicked.connect(lambda *_: btn_detalle.click())
        fila_acciones.addStretch()
        tabla_card_layout.addLayout(fila_acciones)
        self.btn_deshacer= BotonAnimado("Deshacer última eliminación")
        self.btn_deshacer.setObjectName("BtnAccionDeshacer")
        self.btn_deshacer.clicked.connect(self._deshacer_eliminacion)
        self.btn_deshacer.setVisible(False)
        fila_acciones.addWidget(self.btn_deshacer)
        self._ultima_eliminacion= None
        if es_profesor_restringido(self.main_window):
            #El profesor SÍ puede cargar un estudiante para retocar sus datos locales, y también puede eliminar, pero solo
            #estudiantes de SUS secciones (ver validación en _eliminar). Cuenta con "Deshacer" por si se equivoca.
            self.btn_editar.setVisible(True)

        disposicion.addWidget(self.frame_tabla, 1)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        self.actualizar_tema()

    def _titulo(self, texto):

        lbl= QLabel(texto)
        lbl.setObjectName("TituloModulo")
        return lbl

    def _mostrar_info_docente(self):

        mostrar_mensaje("info", "Mis Estudiantes · Modo Docente",
            "Puedes personalizar todos los datos de tus estudiantes: nombre, apellidos, sexo, fecha de "
            "nacimiento, documento, dirección, teléfono, correo, tutores, sección y estado, además de "
            "ponerles una foto.\n\n"
            "La única excepción es la matrícula: es un dato institucional, no se muestra en esta "
            "tabla y no puedes editarla. Si está mal, pide la corrección a Dirección/Coordinación.\n\n"
            "1⃣ Selecciona un estudiante en la tabla y pulsa 'Cargar Seleccionado'.\n"
            "2⃣ Edita lo que necesites y pulsa 'Guardar'.\n"
            "3⃣ ¿Te equivocaste? Usa 'Restablecer al original' para volver a los datos oficiales.\n\n"
            "Todo esto se guarda SOLO en este equipo (tu Modo Docente). Dirección/Coordinación nunca "
            "ve ni recibe estos cambios: ellos siguen viendo sus propios datos oficiales.\n\n"
            "No es recomendable registrar estudiantes nuevos manualmente aquí (no podrás, de hecho:"
            "solo puedes editar estudiantes que ya existen). Si falta alguien, lo correcto es pedir que "
            "te reexporten el paquete oficial desde Copias de Seguridad ▸ Importar Estudiantes y Cursos.",
            self)

    def _elegir_foto(self):

        if es_profesor_restringido(self.main_window) and self.id_edicion is None:
            mostrar_mensaje("advertencia", "Selecciona un estudiante",
                           "Primero usa 'Cargar Seleccionado' para elegir a cuál de tus estudiantes"
                           "le vas a poner una foto.", self)
            return
        carpeta= "fotos_docente_local" if es_profesor_restringido(self.main_window) else "fotos"
        destino_dir= os.path.join(obtener_carpeta_datos(), carpeta)
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="est")
        if not destino:
            return
        self.foto_path= destino
        self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(destino), 64))

    def _ver_foto_ampliada(self):

        if not self.foto_path or not os.path.exists(self.foto_path):
            mostrar_mensaje("advertencia", "Sin foto", "Este estudiante no tiene una fotografía cargada.", self)
            return
        VisorFotoDialog(self.foto_path, self, titulo="Fotografía del Estudiante").exec()

    def _quitar_foto(self):

        if not self.foto_path:
            mostrar_mensaje("advertencia", "Sin foto", "Este estudiante no tiene una fotografía cargada.", self)
            return
        if mostrar_mensaje("pregunta", "Confirmar", "¿Quitar la fotografía de este estudiante?", self) != QMessageBox.StandardButton.Yes:
            return
        self.foto_path= ""
        self.lbl_foto.setText("Sin\nfoto")
        self.lbl_foto.setPixmap(QPixmap())

    def _secciones_permitidas_ids(self):

        return obtener_secciones_permitidas(self.main_window)

    #Crea (una sola vez) la ventanita con todos los filtros. No es modal:
    #se puede dejar abierta mientras se ajustan los combos y la tabla de
    #atrás se sigue actualizando en vivo, igual que antes.
    def _construir_dialogo_filtros(self):

        self.dialogo_filtros= QDialog(self)
        self.dialogo_filtros.setObjectName("DialogoFiltros")
        self.dialogo_filtros.setWindowTitle("Filtros de Estudiantes")
        self.dialogo_filtros.setModal(False)
        self.dialogo_filtros.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros)
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

        self.linea_separadora_filtros= QFrame()
        self.linea_separadora_filtros.setFrameShape(QFrame.Shape.HLine)
        self.linea_separadora_filtros.setObjectName("SeparadorFiltros")
        lay_dialogo.addWidget(self.linea_separadora_filtros)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            ("Nivel Educativo:", self.combo_filtro_nivel),
            (None, self.combo_filtro_especialidad),   #etiqueta propia: self.lbl_filtro_especialidad
            (None, self.combo_filtro_carrera),         #etiqueta propia: self.lbl_filtro_carrera
            ("Grado/Curso:", self.combo_filtro_grado),
            ("Sección:", self.combo_filtro_seccion),
            ("Sexo:", self.combo_filtro_sexo),
            ("Estado:", self.combo_filtro_estado),
        ):
            if combo is self.combo_filtro_especialidad:
                grid.addWidget(self.lbl_filtro_especialidad, fila, 0)
            elif combo is self.combo_filtro_carrera:
                grid.addWidget(self.lbl_filtro_carrera, fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        btn_limpiar_filtros= QPushButton("Limpiar filtros")
        btn_limpiar_filtros.setIcon(icono_emoji("🧹"))
        btn_limpiar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_limpiar_filtros.setObjectName("BtnAccionNeutro")
        btn_limpiar_filtros.clicked.connect(self._limpiar_filtros)
        fila_botones.addWidget(btn_limpiar_filtros)
        fila_botones.addStretch()
        btn_cerrar_filtros= QPushButton("Cerrar")
        btn_cerrar_filtros.setIcon(icono_emoji("✖"))
        btn_cerrar_filtros.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar_filtros.setObjectName("BtnAccionNeutro")
        btn_cerrar_filtros.clicked.connect(self.dialogo_filtros.hide)
        fila_botones.addWidget(btn_cerrar_filtros)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros.parent() is not _fc:
            self.dialogo_filtros.setParent(_fc)
        self.dialogo_filtros.show()
        self.dialogo_filtros.raise_()
        self.dialogo_filtros.activateWindow()

    #Regresa los seis filtros a 'Todos' de un solo golpe. El cambio de
    #combo_filtro_grado ya dispara la cascada de sección y _filtro_cambio
    #por sí solo (ver _grado_filtro_cambio), así que no hace falta llamar
    #_filtro_cambio() de nuevo para ese combo.
    def _limpiar_filtros(self):

        self.combo_filtro_nivel.setCurrentIndex(0)
        self.combo_filtro_grado.setCurrentIndex(0)
        self.combo_filtro_especialidad.setCurrentIndex(0)
        self.combo_filtro_carrera.setCurrentIndex(0)
        self.combo_filtro_sexo.setCurrentIndex(0)
        self.combo_filtro_estado.setCurrentIndex(0)

    #Repuebla el filtro de Nivel Educativo con solo los niveles que esta
    #institución tiene habilitados (misma fuente de verdad que usa
    #Materias > Secciones para el combo de Nivel Educativo del Grado:
    #niveles_academicos_habilitados en configuracion.py).
    def _cargar_niveles_combo_filtro(self):

        combo= self.combo_filtro_nivel
        seleccion_previa= combo.currentData() if combo.count() else None
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM configuracion WHERE id=1")
        cfg= c.fetchone()
        conn.close()
        habilitados= niveles_academicos_habilitados(cfg) if cfg else NIVELES_ACADEMICOS
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Todos los niveles", None)
        for nivel in NIVELES_ACADEMICOS:
            if nivel in habilitados:
                combo.addItem(nivel, nivel)
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _cargar_grados_combo_filtro(self):

        poblar_combo_curso(self.combo_filtro_grado, incluir_todos=False,
                            secciones_permitidas= self._secciones_permitidas_ids())

    def _grado_filtro_cambio(self):

        cascada_seccion_por_curso(self.combo_filtro_grado, self.combo_filtro_seccion,
                                   incluir_todas= False, secciones_permitidas=self._secciones_permitidas_ids())
        self._filtro_cambio()

    #Igual que _cargar_grados_combo_filtro pero para el combo de Grado
    #de la ficha de alta/edición del estudiante (obligatorio, acota
    #self.combo_seccion, no la tabla).
    def _cargar_grados_combo_ficha(self):

        poblar_combo_curso(self.combo_grado_ficha, incluir_todos=False,
                            secciones_permitidas= self._secciones_permitidas_ids())

    #Repuebla 'Sección' con solo las secciones del curso/grado elegido en
    #'Curso/Grado'. Mientras no se elija un curso, 'Sección' queda vacía
    #(con un placeholder sin datos), así que no puede quedar seleccionada
    #por accidente una sección de otro curso (igual que en la pestaña de
    #Horarios de Materias).
    def _grado_ficha_cambio(self, _indice=None, seccion_id_preseleccionar=None):

        cascada_seccion_por_curso(self.combo_grado_ficha, self.combo_seccion,
                                   incluir_todas= False, secciones_permitidas=self._secciones_permitidas_ids())
        if seccion_id_preseleccionar is not None:
            idx= self.combo_seccion.findData(seccion_id_preseleccionar)
            self.combo_seccion.setCurrentIndex(idx if idx >= 0 else 0)
        self._actualizar_profesor_guia()

    def _cargar_especialidades_combo_filtro(self):

        combo= self.combo_filtro_especialidad
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            filas= c.fetchall()
        except Exception:
            filas= []
        conn.close()
        if not filas:
            #Institución sin módulo Politécnico / sin especialidades configuradas:
            #no tiene sentido mostrar este filtro dentro del diálogo.
            self._especialidad_disponible= False
            combo.setVisible(False)
            self.lbl_filtro_especialidad.setVisible(False)
            combo.blockSignals(False)
            return
        self._especialidad_disponible= True
        combo.setVisible(True)
        self.lbl_filtro_especialidad.setVisible(True)
        combo.addItem("Todas las áreas técnicas", None)
        for fila in filas:
            combo.addItem(fila["nombre"], fila["id"])
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Igual que el combo de Carrera de la ficha (_cargar_carrera_ficha_combo):
    #solo se muestra cuando la institución es de tipo Universidad (o
    #Personalizado con el módulo Universidad activo), sin importar si ya
    #hay carreras cargadas o no. Antes este filtro se mostraba/ocultaba
    #según si la tabla `carreras` tenía filas, lo que era inconsistente
    #con el resto de la app: una institución que NO es Universidad pero
    #conserva carreras viejas en la base (p. ej. tras cambiar el tipo de
    #institución) igual lo mostraba, y una Universidad recién configurada
    #sin carreras aún cargadas no lo mostraba.
    def _cargar_carreras_combo_filtro(self):

        combo= self.combo_filtro_carrera
        es_uni= self._es_universidad()
        self._carrera_disponible= es_uni
        combo.setVisible(es_uni)
        self.lbl_filtro_carrera.setVisible(es_uni)
        if not es_uni:
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
            return
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            filas= c.fetchall()
        except Exception:
            filas= []
        conn.close()
        combo.addItem("Todas las carreras", None)
        for fila in filas:
            combo.addItem(fila["nombre"], fila["id"])
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _actualizar_profesor_guia(self):

        seccion_id= self.combo_seccion.currentData()
        if seccion_id is None:
            self.lbl_profesor_guia.setText("Profesor guía: —")
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT (profesores.nombre || ' ' || IFNULL(profesores.apellidos,'')) as nombre
                     FROM secciones LEFT JOIN profesores ON secciones.profesor_guia_id = profesores.id
                     WHERE secciones.id=?""", (seccion_id,))
        fila= c.fetchone()
        conn.close()
        nombre= (fila["nombre"] or "").strip() if fila else ""
        self.lbl_profesor_guia.setText(f"Profesor guía: {nombre if nombre else 'Sin asignar'}")
        self._actualizar_disponibilidad_especialidad_ficha(seccion_id)

    #Oculta (no solo deshabilita) el combo de Área Técnica de la ficha si
    #la sección elegida no es Secundaria - Segundo Ciclo (misma regla que
    #valida _guardar(): puede_tener_componente_tecnico). Solo aplica cuando
    #la institución es Politécnico -en cualquier otro caso el combo ya está
    #oculto por _cargar_especialidad_ficha_combo() vía _es_politecnico().
    #
    #Antes esto solo deshabilitaba el combo (quedaba visible mostrando
    #"— Selecciona un área técnica —" en gris) sin importar la sección,
    #así que un estudiante de Primaria en una institución "Personalizado"
    #con Politécnico Y Primaria activos a la vez veía un campo obligatorio
    #que ni siquiera podía llenar -bloqueando el guardado. Ver el mismo
    #arreglo en Materias > Cursos y Secciones.
    def _actualizar_disponibilidad_especialidad_ficha(self, seccion_id):

        if not self._es_politecnico() or not hasattr(self, "combo_especialidad_estudiante"):
            return
        nivel_sec, ciclo_sec= resolver_nivel_academico_de_seccion(seccion_id)
        tipo_inst, _= self.main_window._tipo_institucion()
        permite= seccion_id is None or puede_tener_componente_tecnico(nivel_sec, ciclo_sec, tipo_inst)
        self.combo_especialidad_estudiante.setVisible(permite)
        self.combo_especialidad_estudiante.setEnabled(True)
        if not permite:
            self.combo_especialidad_estudiante.setCurrentIndex(0)
            conectar_tooltip_seleccion(self.combo_especialidad_estudiante,
                "La sección elegida no es Secundaria - Segundo Ciclo: un estudiante ahí no puede tener "
                "Área Técnica (componente exclusivo del Politécnico en Secundaria, Segundo Ciclo).")
        else:
            conectar_tooltip_seleccion(self.combo_especialidad_estudiante,
                                        "Área técnica del estudiante (obligatorio en Politécnico).")

    def _generar_matricula(self):

        anio= datetime.now().strftime("%Y")
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT matricula FROM estudiantes WHERE matricula LIKE ? ORDER BY matricula DESC LIMIT 1",
                  (f"{anio}-%",))
        fila= c.fetchone()
        conn.close()
        if fila and fila["matricula"]:
            try:

                consecutivo= int(fila["matricula"].split("-")[-1]) + 1
            except (ValueError, IndexError):
                consecutivo= 1
        else:
            consecutivo= 1
        return f"{anio}-{consecutivo:04d}"

    def _autogenerar_matricula(self):

        self.in_matricula.setText(self._generar_matricula())

    def _matricula_disponible(self, matricula, excluyendo_id=None):

        if not matricula:
            return True
        conn= obtener_conexion()
        c= conn.cursor()
        if excluyendo_id is None:
            c.execute("SELECT id FROM estudiantes WHERE matricula=?", (matricula,))
        else:
            c.execute("SELECT id FROM estudiantes WHERE matricula=? AND id!=?", (matricula, excluyendo_id))
        fila= c.fetchone()
        conn.close()
        return fila is None

    ALIAS_COLUMNAS= {
        "matricula": "matricula", "matrícula": "matricula",
        "nombre": "nombre", "nombres": "nombre",
        "apellidos": "apellidos", "apellido": "apellidos",
        "sexo": "sexo", "genero": "sexo", "género": "sexo",
        "fecha_nacimiento": "fecha_nacimiento", "fecha de nacimiento": "fecha_nacimiento",
        "documento": "documento", "documento de identidad": "documento", "cedula": "documento", "cédula": "documento",
        "direccion": "direccion", "dirección": "direccion",
        "telefono": "telefono", "teléfono": "telefono",
        "correo": "correo", "email": "correo", "correo electronico": "correo",
        "tutor": "tutor", "tutor/padre": "tutor", "padre": "tutor",
        "estado": "estado",
    }

    def _abrir_exportar_intercambio(self):

        seccion_id= self.combo_filtro_seccion.currentData() if hasattr(self, "combo_filtro_seccion") else None
        DialogoExportarEstudiantes(self.main_window, seccion_id_actual=seccion_id, parent=self).exec()

    def _abrir_importar_intercambio(self):

        dialogo= DialogoImportarEstudiantes(self.main_window, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._cargar_tabla()

    def _importar_excel_csv(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para importar estudiantes.", self)
            return
        if es_profesor_restringido(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos",
                           "Los profesores no pueden importar estudiantes directamente. Pide a Dirección/"
                           "Coordinación que te exporte el paquete de Estudiantes y Cursos e impórtalo desde "
                           "Copias de Seguridad.", self)
            return
        ruta, _= QFileDialog.getOpenFileName(
            self, "Importar Estudiantes", "", "Excel/CSV (*.xlsx *.xls *.csv)")
        if not ruta:
            return
        try:

            filas_crudas= self._leer_filas_importacion(ruta)
        except Exception as error:
            mostrar_mensaje("error", "Error al leer el archivo", f"No se pudo leer el archivo:\n{error}", self)
            return
        if not filas_crudas:
            mostrar_mensaje("advertencia", "Archivo vacío",
                           "No se encontraron filas de datos en el archivo seleccionado.", self)
            return
        insertados, duplicados, sin_nombre= 0, 0, 0
        conn= obtener_conexion()
        c= conn.cursor()
        for fila in filas_crudas:
            nombre= (fila.get("nombre") or "").strip()
            if not nombre:
                sin_nombre += 1
                continue
            matricula= (fila.get("matricula") or "").strip()
            if not matricula:
                matricula= self._generar_matricula()
            if not self._matricula_disponible(matricula):
                duplicados += 1
                continue
            sexo= (fila.get("sexo") or "").strip().capitalize()
            if sexo not in SEXOS:
                sexo= SEXOS[0]
            estado= (fila.get("estado") or "").strip().capitalize()
            if estado not in ESTADOS:
                estado= "Activo"
            c.execute("""INSERT INTO estudiantes (matricula, nombre, apellidos, sexo, fecha_nacimiento,
                         documento, direccion, telefono, correo, tutor, foto, seccion_id, estado)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                matricula, nombre, (fila.get("apellidos") or "").strip(), sexo,
                (fila.get("fecha_nacimiento") or "").strip(), (fila.get("documento") or "").strip(),
                (fila.get("direccion") or "").strip(), (fila.get("telefono") or "").strip(),
                (fila.get("correo") or "").strip(), (fila.get("tutor") or "").strip(),
                "", None, estado))
            insertados += 1
        conn.commit()
        conn.close()
        registrar_auditoria("Estudiantes", "Importación masiva desde Excel/CSV",
                            self.main_window.usuario_actual, f"{insertados} registros desde {ruta}")
        self._cargar_tabla()
        resumen= f"Estudiantes importados: {insertados}"
        if duplicados:
            resumen += f"\nOmitidos por matrícula duplicada: {duplicados}"
        if sin_nombre:
            resumen += f"\nOmitidos por falta de nombre: {sin_nombre}"
        mostrar_mensaje("exito", "Importación completada", resumen, self)

    def _leer_filas_importacion(self, ruta):

        extension= os.path.splitext(ruta)[1].lower()
        filas= []
        if extension == ".csv":
            import csv
            with open(ruta, "r", newline="", encoding="utf-8-sig") as f:
                lector= csv.reader(f)
                encabezados= next(lector, None)
                if not encabezados:
                    return []
                claves= self._normalizar_encabezados(encabezados)
                for cruda in lector:
                    if not any((c or "").strip() for c in cruda):
                        continue
                    filas.append({claves[i]: (cruda[i] if i < len(cruda) else "")
                                 for i in range(len(claves)) if claves[i]})
        else:
            try:

                import openpyxl
            except ImportError:
                raise RuntimeError("Instala 'openpyxl' (pip install openpyxl) para importar archivos Excel.")
            wb= openpyxl.load_workbook(ruta, data_only=True)
            hoja= wb.active
            filas_iter= hoja.iter_rows(values_only=True)
            encabezados= next(filas_iter, None)
            if not encabezados:
                return []
            claves= self._normalizar_encabezados([str(encabezado or "") for encabezado in encabezados])
            for cruda in filas_iter:
                if not any(v not in (None, "") for v in cruda):
                    continue
                fila= {}
                for i, clave in enumerate(claves):
                    if not clave:
                        continue
                    valor= cruda[i] if i < len(cruda) else ""
                    fila[clave]= "" if valor is None else str(valor)
                filas.append(fila)
        return filas

    def _normalizar_encabezados(self, encabezados):

        return [self.ALIAS_COLUMNAS.get((encabezado or "").strip().lower(), None) for encabezado in encabezados]

    def _guardar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para editar estudiantes.", self)
            return
        if es_profesor_restringido(self.main_window):
            self._guardar_override_local()
            return
        if not self.in_nombre.text().strip():
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        if not self.in_tutor.text().strip():
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos", "Debes colocar al menos un Tutor / Padre.", self)
            return
        matricula= self.in_matricula.text().strip()
        if not matricula:
            matricula= self._generar_matricula()
            self.in_matricula.setText(matricula)
        if not self._matricula_disponible(matricula, excluyendo_id=self.id_edicion):
            mostrar_mensaje("advertencia", "Matrícula duplicada",
                           f"La matrícula '{matricula}' ya está en uso por otro estudiante.\n"
                           "Usa 'Autogenerar Matrícula' o ingresa una diferente.", self)
            return
        #Si la institución es "Personalizado" y tiene AMBOS módulos activos (Politécnico Y Universidad a la vez), Área
        #Técnica y Carrera pasan a ser OPCIONALES: un mismo estudiante normalmente pertenece a una sola de las dos
        #ramas, así que obligar a elegir las dos termina forzando datos que no aplican. Si solo uno de los dos módulos
        #está
        #activo (o la institución es puramente Politécnico/Universidad, sin
        #"Personalizado" de por medio), ese único campo sigue siendo obligatorio exactamente como antes -ver
        #_ambos_modulos_tecnicos_activos.
        ambos_activos= self._ambos_modulos_tecnicos_activos()
        seccion_id_actual= self.combo_seccion.currentData()
        #El Área Técnica solo es obligatoria si, además de ser Politécnico, la Sección elegida admite componente
        #técnico (Secundaria - Segundo Ciclo). Si el estudiante quedó en una sección de Primaria, Preparatoria,
        #Universidad o Secundaria-Primer Ciclo, el combo ni siquiera se muestra
        #(_actualizar_disponibilidad_especialidad_ficha) y por lo tanto tampoco debe exigirse aquí -mismo criterio que
        #en Materias > Cursos y Secciones.
        nivel_sec_actual, ciclo_sec_actual= resolver_nivel_academico_de_seccion(seccion_id_actual)
        tipo_inst_actual, _= self.main_window._tipo_institucion()
        permite_tecnico_actual= seccion_id_actual is None or puede_tener_componente_tecnico(
            nivel_sec_actual, ciclo_sec_actual, tipo_inst_actual)
        if (self._es_politecnico() and not ambos_activos and permite_tecnico_actual
                and self.combo_especialidad_estudiante.currentData() is None):
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es un Politécnico: selecciona el Área Técnica del estudiante.", self)
            return
        if self._es_universidad() and not ambos_activos and self.combo_carrera_estudiante.currentData() is None:
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Esta institución es una Universidad: selecciona la Carrera del estudiante.", self)
            return
        if self.combo_grado_ficha.currentData() is None or self.combo_seccion.currentData() is None:
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos",
                           "Selecciona el Curso/Grado y la Sección del estudiante.", self)
            return
        seccion_id= self.combo_seccion.currentData()
        especialidad_id= self.combo_especialidad_estudiante.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_carrera_estudiante.currentData() if self._es_universidad() else None
        if especialidad_id is not None:
            #Validación lógica (no solo visual): un Área Técnica solo es académicamente válida para un estudiante de
            #Secundaria - Segundo
            #Ciclo (República Dominicana). Reutiliza la misma regla de
            #Materias > Secciones (puede_tener_componente_tecnico), en vez de duplicarla, para que nunca puedan
            #desalinearse.
            nivel_sec, ciclo_sec= resolver_nivel_academico_de_seccion(seccion_id)
            tipo_inst, _= self.main_window._tipo_institucion()
            if not puede_tener_componente_tecnico(nivel_sec, ciclo_sec, tipo_inst):
                self._destello("#EF4444")
                mostrar_mensaje("advertencia", "Combinación inválida",
                               "El Área Técnica solo es válida para estudiantes de Secundaria - Segundo "
                               "Ciclo. La sección elegida no pertenece a ese nivel/ciclo (clasifícalo en "
                               "Materias > Secciones, o elige otra sección).", self)
                return
        datos= (
            matricula, self.in_nombre.text().strip(), self.in_apellidos.text().strip(),
            self.combo_sexo.currentText(), self.in_date_nacimiento.date().toString("yyyy-MM-dd"),
            self.in_documento.text().strip(), self.in_direccion.text().strip(), self.in_telefono.text().strip(),
            self.in_correo.text().strip(), self.in_tutor.text().strip(), self.in_tutor2.text().strip(),
            self.foto_path, seccion_id, self.combo_estado.currentText(), especialidad_id, carrera_id
        )
        try:

            conn= obtener_conexion()
            c= conn.cursor()
            seccion_anterior_id= None
            if self.id_edicion is not None:
                fila_previa= c.execute("SELECT seccion_id FROM estudiantes WHERE id=?",
                                         (self.id_edicion,)).fetchone()
                seccion_anterior_id= fila_previa["seccion_id"] if fila_previa else None
            if self.id_edicion is None:
                c.execute("""INSERT INTO estudiantes (matricula, nombre, apellidos, sexo, fecha_nacimiento,
                             documento, direccion, telefono, correo, tutor, tutor2, foto, seccion_id, estado,
                             especialidad_id, carrera_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", datos)
                accion= "Registró estudiante"
            else:
                c.execute("""UPDATE estudiantes SET matricula=?, nombre=?, apellidos=?, sexo=?,
                             fecha_nacimiento= ?, documento=?, direccion=?, telefono=?, correo=?, tutor=?,
                             tutor2= ?, foto=?, seccion_id=?, estado=?, especialidad_id=?, carrera_id=?
                             WHERE id=?""",
                          datos + (self.id_edicion,))
                accion= "Editó estudiante"
            conn.commit()
            conn.close()
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar el estudiante:\n{error}", self)
            return
        #El Número de Lista es POR SECCIÓN: al registrar un estudiante nuevo, o al mover uno de sección, hay que
        #recalcular tanto la sección de
        #destino (para ubicar al recién llegado en su lugar alfabético) como
        #la de origen si cambió (para "cerrar el hueco" que deja el que se fue, en vez de dejar un número salteado). Si
        #el criterio configurado es Manual, recalcular_numeros_lista() no hace nada -se respeta.
        recalcular_numeros_lista(seccion_id)
        if seccion_anterior_id and seccion_anterior_id != seccion_id:
            recalcular_numeros_lista(seccion_anterior_id)
        registrar_auditoria("Estudiantes", accion, self.main_window.usuario_actual, self.in_nombre.text().strip())
        self._destello("#22C55E")
        mostrar_mensaje("exito", "Guardado", "El estudiante se guardó correctamente.", self)
        self._limpiar()
        self.refrescar()

    #Guarda los retoques del Profesor SOLO en su almacén local (Modo Docente),
    #sin tocar la base de datos institucional.
    def _guardar_override_local(self):

        if self.id_edicion is None:
            mostrar_mensaje("advertencia", "Selecciona un estudiante",
                           "Usa 'Cargar Seleccionado' para elegir a cuál de tus estudiantes le vas a"
                           "personalizar los datos. No puedes registrar estudiantes nuevos desde aquí; "
                           "pide a Dirección/Coordinación que los registre y te reexporte el paquete.", self)
            return
        if not self.in_nombre.text().strip():
            self._destello("#EF4444")
            mostrar_mensaje("advertencia", "Datos incompletos", "El nombre es obligatorio.", self)
            return
        campos= {
            #La matrícula no se incluye: es un dato institucional y el docente no puede modificarla (ver
            #guardar_override_estudiante).
            "nombre": self.in_nombre.text().strip(),
            "apellidos": self.in_apellidos.text().strip(),
            "sexo": self.combo_sexo.currentText(),
            "fecha_nacimiento": self.in_date_nacimiento.date().toString("yyyy-MM-dd"),
            "documento": self.in_documento.text().strip(),
            "direccion": self.in_direccion.text().strip(),
            "telefono": self.in_telefono.text().strip(),
            "correo": self.in_correo.text().strip(),
            "tutor": self.in_tutor.text().strip(),
            "tutor2": self.in_tutor2.text().strip(),
            "seccion_id": self.combo_seccion.currentData(),
            "estado": self.combo_estado.currentText(),
            "foto": self.foto_path,
            "especialidad_id": self.combo_especialidad_estudiante.currentData() if self._es_politecnico() else None,
            "carrera_id": self.combo_carrera_estudiante.currentData() if self._es_universidad() else None,
        }
        guardar_override_estudiante(self.main_window, self.id_edicion, campos)
        registrar_auditoria("Estudiantes", "Personalizó datos locales (Modo Docente)",
                            self.main_window.usuario_actual, self.in_nombre.text().strip())
        self._destello("#22C55E")
        mostrar_mensaje("exito", "Guardado localmente",
                       "Tus cambios se guardaron en este equipo (Modo Docente). Dirección/Coordinación no "
                       "verá ni recibirá esta información: sigue viendo los datos oficiales.", self)
        self._limpiar()
        self.refrescar()

    def _restablecer_override(self):

        if self.id_edicion is None:
            mostrar_mensaje("advertencia", "Selecciona un estudiante",
                           "Usa 'Cargar Seleccionado' para elegir el estudiante cuya personalización"
                           "local quieres eliminar.", self)
            return
        if mostrar_mensaje("pregunta", "Confirmar",
                          "¿Eliminar tu personalización local de este estudiante y volver a mostrar "
                          "los datos oficiales?", self) != QMessageBox.StandardButton.Yes:
            return
        eliminar_override_estudiante(self.main_window, self.id_edicion)
        mostrar_mensaje("exito", "Restablecido", "Se eliminó tu personalización local.", self)
        self._limpiar()
        self.refrescar()

    def _limpiar(self):

        self.id_edicion= None
        self.foto_path= ""
        self.lbl_foto.setText("Sin\nfoto")
        self.lbl_foto.setPixmap(QPixmap())
        for campo in (self.in_matricula, self.in_nombre, self.in_apellidos, self.in_documento,
                      self.in_direccion, self.in_telefono, self.in_correo, self.in_tutor, self.in_tutor2):
            campo.clear()
        self.combo_sexo.setCurrentIndex(0)
        self.combo_estado.setCurrentIndex(0)
        self.combo_especialidad_estudiante.setCurrentIndex(0)
        self.combo_carrera_estudiante.setCurrentIndex(0)
        self.in_date_nacimiento.setDate(QDate(2010, 1, 1))
        self.combo_grado_ficha.blockSignals(True)
        self.combo_grado_ficha.setCurrentIndex(0)
        self.combo_grado_ficha.blockSignals(False)
        self.combo_seccion.blockSignals(True)
        self.combo_seccion.clear()
        self.combo_seccion.addItem("Selecciona primero un curso/grado…", None)
        self.combo_seccion.blockSignals(False)
        self.lbl_profesor_guia.setText("Profesor guía: —")
        if not es_profesor_restringido(self.main_window):
            self.in_matricula.setText(self._generar_matricula())
        desactivar_modo_edicion(self.in_matricula)

    def _cargar_seleccionado(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un estudiante de la tabla.", self)
            return
        id_est= int(self.tabla.item(fila, 0).text())
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM estudiantes WHERE id=?", (id_est,))
        #f: fila consultada; None si no existe
        f= c.fetchone()
        conn.close()
        if not f:
            return
        restringido= es_profesor_restringido(self.main_window)
        datos= aplicar_override(f, obtener_override_estudiante(self.main_window, id_est)) if restringido else dict(f)
        self.id_edicion= f["id"]
        self.in_matricula.setText(datos["matricula"] or "")
        self.in_nombre.setText(datos["nombre"] or "")
        self.in_apellidos.setText(datos["apellidos"] or "")
        self.combo_sexo.setCurrentText(datos["sexo"] or "Masculino")
        if datos["fecha_nacimiento"]:
            self.in_date_nacimiento.setDate(QDate.fromString(datos["fecha_nacimiento"], "yyyy-MM-dd"))
        self.in_documento.setText(datos["documento"] or "")
        self.in_direccion.setText(datos["direccion"] or "")
        self.in_telefono.setText(datos["telefono"] or "")
        self.in_correo.setText(datos["correo"] or "")
        self.in_tutor.setText(datos["tutor"] or "")
        self.in_tutor2.setText(datos["tutor2"] or "")
        self.foto_path= datos["foto"] or ""
        if self.foto_path and os.path.exists(self.foto_path):
            self.lbl_foto.setPixmap(_redondear_pixmap(QPixmap(self.foto_path), 64))
        else:
            self.lbl_foto.setPixmap(QPixmap())
            self.lbl_foto.setText("Sin\nfoto")
        preseleccionar_curso_y_seccion(self.combo_grado_ficha, self.combo_seccion,
                                        datos.get("seccion_id"), incluir_todas=False)
        self._actualizar_profesor_guia()
        self.combo_estado.setCurrentText(datos["estado"] or "Activo")
        if self._es_politecnico():
            especialidad_id= datos.get("especialidad_id") if isinstance(datos, dict) else None
            if especialidad_id is None:
                especialidad_id= f["especialidad_id"]
            idx_esp= self.combo_especialidad_estudiante.findData(especialidad_id)
            self.combo_especialidad_estudiante.setCurrentIndex(idx_esp if idx_esp >= 0 else 0)
        if self._es_universidad():
            carrera_id= datos.get("carrera_id") if isinstance(datos, dict) else None
            if carrera_id is None:
                carrera_id= f["carrera_id"] if "carrera_id" in f.keys() else None
            idx_car= self.combo_carrera_estudiante.findData(carrera_id)
            self.combo_carrera_estudiante.setCurrentIndex(idx_car if idx_car >= 0 else 0)
        nombre_est= (datos.get("nombre") if isinstance(datos, dict) else None) or ""
        apellidos_est= (datos.get("apellidos") if isinstance(datos, dict) else None) or ""
        activar_modo_edicion(self.in_matricula,
                             f"Editando estudiante: {nombre_est} {apellidos_est}".strip())

    def _eliminar(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no tiene permiso para eliminar estudiantes.", self)
            return
        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un estudiante de la tabla.", self)
            return
        id_est= int(self.tabla.item(fila, 0).text())
        nombre= self.tabla.item(fila, 3).text()

        restringido= es_profesor_restringido(self.main_window)
        if restringido:
            #Un profesor solo puede eliminar estudiantes de secciones donde da clase/guía; nunca estudiantes de otras
            #secciones.
            permitidas= obtener_secciones_permitidas(self.main_window)
            conn= obtener_conexion()
            fila_est= conn.execute("SELECT seccion_id FROM estudiantes WHERE id=?", (id_est,)).fetchone()
            conn.close()
            seccion_est= fila_est["seccion_id"] if fila_est else None
            if permitidas is not None and seccion_est not in permitidas:
                mostrar_mensaje("advertencia", "Sin permisos",
                                 "Solo puedes eliminar estudiantes de tus propias secciones.", self)
                return

        mensaje_confirm= f"¿Eliminar a '{nombre}'?"
        if restringido:
            mensaje_confirm += "\n\nPodrás deshacer esta acción inmediatamente después si te equivocas."
        if mostrar_mensaje("pregunta", "Confirmar", mensaje_confirm, self) != QMessageBox.StandardButton.Yes:
            return

        conn= obtener_conexion()
        c= conn.cursor()
        fila_completa= c.execute("SELECT * FROM estudiantes WHERE id=?", (id_est,)).fetchone()
        if fila_completa is None:
            conn.close()
            return
        datos_respaldo= dict(fila_completa)
        c.execute("DELETE FROM estudiantes WHERE id=?", (id_est,))
        conn.commit()
        conn.close()
        registrar_auditoria("Estudiantes", "Eliminó estudiante", self.main_window.usuario_actual, nombre)
        #Cierra el hueco que deja el estudiante eliminado en la numeración de su sección (para que no quede, p.ej., un
        #"3" salteado entre el "2" y el "4" el resto del año).
        recalcular_numeros_lista(datos_respaldo.get("seccion_id"))

        #Guardamos un respaldo de la última eliminación para poder deshacerla. Solo se conserva UN nivel de deshacer
        #(la última acción).
        self._ultima_eliminacion= datos_respaldo
        self.btn_deshacer.setVisible(True)
        self.btn_deshacer.setEnabled(True)

        self.refrescar()

    #Restaura el último estudiante eliminado desde esta pantalla, tal cual
    #estaba (mismo id y mismos datos). Solo funciona una vez por eliminación.
    def _deshacer_eliminacion(self):

        if not self._ultima_eliminacion:
            return
        datos= self._ultima_eliminacion
        conn= obtener_conexion()
        c= conn.cursor()
        try:

            c.execute("""INSERT INTO estudiantes
                         (id, matricula, nombre, apellidos, sexo, fecha_nacimiento, documento,
                          direccion, telefono, correo, tutor, tutor2, foto, seccion_id, estado)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (datos["id"], datos["matricula"], datos["nombre"], datos["apellidos"], datos["sexo"],
                       datos["fecha_nacimiento"], datos["documento"], datos["direccion"], datos["telefono"],
                       datos["correo"], datos["tutor"], datos["tutor2"], datos["foto"],
                       datos["seccion_id"], datos["estado"]))
            conn.commit()
        except Exception as error:
            conn.rollback()
            mostrar_mensaje("error", "No se pudo deshacer",
                             f"No fue posible restaurar al estudiante (puede que ya exista un registro con la "
                             f"misma matrícula u otro conflicto): {error}", self)
            conn.close()
            return
        conn.close()
        registrar_auditoria("Estudiantes", "Deshizo eliminación de estudiante",
                             self.main_window.usuario_actual, datos.get("nombre", ""))
        recalcular_numeros_lista(datos.get("seccion_id"))
        self._ultima_eliminacion= None
        self.btn_deshacer.setVisible(False)
        mostrar_mensaje("info", "Restaurado", f"'{datos['nombre']}' fue restaurado correctamente.", self)
        self.refrescar()

    def _filtro_cambio(self, texto=""):

        self.paginacion.reiniciar()
        self._cargar_tabla()

    def _cargar_tabla(self):

        texto= _normalizar(self.in_buscar.text().strip())
        nivel_filtro= self.combo_filtro_nivel.currentData()
        seccion_id= self.combo_filtro_seccion.currentData()
        grado_id= self.combo_filtro_grado.currentData()
        especialidad_id= self.combo_filtro_especialidad.currentData() if self._especialidad_disponible else None
        carrera_id_filtro= self.combo_filtro_carrera.currentData() if self._carrera_disponible else None
        sexo_filtro= self.combo_filtro_sexo.currentData()
        estado_filtro= self.combo_filtro_estado.currentData()
        permitidas= self._secciones_permitidas_ids()
        restringido= es_profesor_restringido(self.main_window)
        overrides= listar_overrides_estudiantes(self.main_window) if restringido else {}
        conn= obtener_conexion()
        c= conn.cursor()
        mapa_secciones_solas= {}
        mapa_grados= {}
        if restringido:
            c.execute("""SELECT secciones.id, secciones.nombre as seccion_sola, grados.nombre as grado_sola,
                         (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                         FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id""")
            filas_sec= c.fetchall()
            mapa_secciones_solas= {fs["id"]: fs["seccion_sola"] for fs in filas_sec}
            mapa_grados= {fs["id"]: fs["grado_sola"] for fs in filas_sec}
        c.execute("""SELECT estudiantes.*, secciones.nombre as seccion_nombre_sola,
                     grados.nombre as grado_nombre_sola,
                     (grados.nombre || ' - ' || secciones.nombre) as seccion_nombre,
                     secciones.grado_id as grado_id_seccion, secciones.especialidad_id as especialidad_id_seccion,
                     grados.nivel_educativo as nivel_educativo_grado,
                     especialidades.nombre as especialidad_nombre, carreras.nombre as carrera_nombre
                     FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     LEFT JOIN grados ON secciones.grado_id = grados.id
                     LEFT JOIN especialidades ON estudiantes.especialidad_id = especialidades.id
                     LEFT JOIN carreras ON estudiantes.carrera_id = carreras.id
                     ORDER BY grados.nombre, secciones.nombre,
                              estudiantes.numero_lista IS NULL, estudiantes.numero_lista,
                              estudiantes.apellidos, estudiantes.nombre""")
        filas= c.fetchall()
        conn.close()
        filtradas= []
        #f: fila del resultado de la consulta
        for f in filas:
            if permitidas is not None and f["seccion_id"] not in permitidas:
                continue
            if nivel_filtro:
                #Universitario se reconoce por tener Carrera asignada (dato que ya existía) -no por `grados.nivel_educativo`,
                #ya que un estudiante de Universidad normalmente no pasa por Sección/Grado. Ver
                #resolver_nivel_academico_estudiante() en bd.py, la misma regla usada aquí en línea para no pagar una consulta
                #aparte por cada fila de la tabla.
                nivel_de_esta_fila= "Universidad" if f["carrera_id"] is not None else f["nivel_educativo_grado"]
                if nivel_de_esta_fila != nivel_filtro:
                    continue
            if seccion_id and f["seccion_id"] != seccion_id:
                continue
            if grado_id and f["grado_id_seccion"] != grado_id:
                continue
            if especialidad_id and f["especialidad_id"] != especialidad_id:
                continue
            if carrera_id_filtro and f["carrera_id"] != carrera_id_filtro:
                continue
            if sexo_filtro and (f["sexo"] or "") != sexo_filtro:
                continue
            if estado_filtro and (f["estado"] or "") != estado_filtro:
                continue
            texto_fila= _normalizar(f"{f['nombre']} {f['apellidos']} {f['matricula']}")
            if texto and texto not in texto_fila:
                continue
            filtradas.append(f)
        self.paginacion.establecer_total(len(filtradas))
        inicio, fin= self.paginacion.rango_actual()
        pagina= filtradas[inicio:fin]
        self.lbl_vacio.setVisible(len(filtradas) == 0)
        #El "No." solo tiene sentido con una Sección concreta filtrada (y, si la institución usa Área Técnica/Carrera,
        #también esas concretas -ver bd.mostrar_columna_numero_lista-): con varias secciones a la vista mezclaría
        #numeraciones de distintos grupos sin ningún orden real, así que se oculta la columna entera.
        mostrar_columna_numero= mostrar_columna_numero_lista(
            self.main_window, seccion_id, especialidad_id, carrera_id_filtro)
        self.tabla.setColumnHidden(1, not mostrar_columna_numero)
        with tabla_pausada(self.tabla):
            self.tabla.setRowCount(len(pagina))
            for i, f in enumerate(pagina):
                datos= aplicar_override(f, overrides.get(f["id"])) if restringido else f
                self.tabla.setItem(i, 0, QTableWidgetItem(str(f["id"])))
                if mostrar_columna_numero:
                    item_numero= QTableWidgetItem()
                    numero_lista= f["numero_lista"] if "numero_lista" in f.keys() else None
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                    item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if numero_lista is None:
                        item_numero.setToolTip("Aún no se ha calculado (usa 'Recalcular Números de Lista').")
                    self.tabla.setItem(i, 1, item_numero)
                if restringido:
                    item_foto= QTableWidgetItem()
                    item_foto.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    foto_path= datos["foto"] or ""
                    pixmap= obtener_pixmap_circular_cacheado(foto_path, TAMANO_FOTO_TABLA)
                    if pixmap is not None:
                        item_foto.setData(Qt.ItemDataRole.DecorationRole, pixmap)
                        #Guarda la ruta real (no solo el pixmap chico de la tabla) para que el diálogo de "Ver Detalle" pueda mostrar
                        #la foto en grande arriba de los demás datos.
                        item_foto.setData(ROL_RUTA_FOTO, foto_path)
                    else:
                        item_foto.setData(Qt.ItemDataRole.DecorationRole,
                                           pixmap_placeholder_foto_tabla(TAMANO_FOTO_TABLA))
                    self.tabla.setItem(i, 2, item_foto)
                else:
                    item_matricula= QTableWidgetItem(datos["matricula"] or "")
                    #La columna aquí muestra la Matrícula (no la Foto), pero
                    #el estudiante sí puede tener una fotografía guardada:
                    #se deja la ruta como respaldo (sin decoración, para no tapar el texto de la matrícula) para que "Ver Detalle"
                    #pueda mostrarla en grande arriba de los demás datos, igual que ya ocurre en Modo Docente. Ver
                    #mostrar_detalle_fila en paginacion.py.
                    foto_path_admin= datos["foto"] or ""
                    if foto_path_admin and os.path.exists(foto_path_admin):
                        item_matricula.setData(ROL_RUTA_FOTO, foto_path_admin)
                    self.tabla.setItem(i, 2, item_matricula)
                nombre_item= QTableWidgetItem(datos["nombre"] or "")
                if restringido and f["id"] in overrides:
                    nombre_item.setToolTip("Este estudiante tiene datos personalizados localmente por ti.")
                self.tabla.setItem(i, 3, nombre_item)
                self.tabla.setItem(i, 4, QTableWidgetItem(datos["apellidos"] or ""))
                self.tabla.setItem(i, 5, QTableWidgetItem(datos["sexo"] or ""))
                grado_texto= mapa_grados.get(datos["seccion_id"], f["grado_nombre_sola"]) if restringido\
                    else f["grado_nombre_sola"]
                self.tabla.setItem(i, 6, QTableWidgetItem(grado_texto or ""))
                seccion_texto= mapa_secciones_solas.get(datos["seccion_id"], f["seccion_nombre_sola"])\
                    if restringido else f["seccion_nombre_sola"]
                self.tabla.setItem(i, 7, QTableWidgetItem(seccion_texto or ""))
                self.tabla.setItem(i, 8, QTableWidgetItem(f["especialidad_nombre"] or "—"))
                self.tabla.setItem(i, 9, QTableWidgetItem(f["carrera_nombre"] or "—"))
                self.tabla.setItem(i, 10, QTableWidgetItem(datos["telefono"] or ""))
                self.tabla.setItem(i, 11, QTableWidgetItem(datos["tutor"] or ""))
                self.tabla.setItem(i, 12, QTableWidgetItem(datos["tutor2"] or ""))
                item_estado= QTableWidgetItem(datos["estado"] or "")
                if (datos["estado"] or "") == "Activo":
                    item_estado.setForeground(QColor("#16A34A"))
                else:
                    item_estado.setForeground(QColor("#DC2626"))
                self.tabla.setItem(i, 13, item_estado)
            self.tabla.resizeRowsToContents()
            self._ajustar_anchos_columnas()
        self._animar_contador(len(filtradas))
        self._animar_fundido_tabla()

    #Ensancha una columna por encima de su ancho base solo cuando algún
    #registro de la página actual lo necesita (un nombre, tutor, etc.
    #demasiado largo). El resto de columnas se queda en su ancho normal,
    #así que la tabla solo saca la barra horizontal cuando de verdad hay
    #un valor "demasiado grande" que no cabe.
    def _ajustar_anchos_columnas(self):

        for col, base in self._anchos_base_columnas.items():
            if self.tabla.isColumnHidden(col):
                continue
            self.tabla.resizeColumnToContents(col)
            if self.tabla.columnWidth(col) < base:
                self.tabla.setColumnWidth(col, base)

    def refrescar(self):

        seccion_actual= self.combo_seccion.currentData()
        self._cargar_grados_combo_ficha()
        self._grado_ficha_cambio(seccion_id_preseleccionar=seccion_actual)
        self._cargar_niveles_combo_filtro()
        self._cargar_grados_combo_filtro()
        cascada_seccion_por_curso(self.combo_filtro_grado, self.combo_filtro_seccion,
                                   incluir_todas= False, secciones_permitidas=self._secciones_permitidas_ids())
        self._cargar_especialidades_combo_filtro()
        self._cargar_especialidad_ficha_combo()
        self._cargar_carreras_combo_filtro()
        self._cargar_carrera_ficha_combo()
        self.tabla.setColumnHidden(8, not self._es_politecnico())
        self.tabla.setColumnHidden(9, not self._es_universidad())
        self._actualizar_profesor_guia()
        if self.id_edicion is None and not self.in_matricula.text().strip() and not es_profesor_restringido(self.main_window):
            self.in_matricula.setText(self._generar_matricula())
        self._cargar_tabla()

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo) — solo entonces se pide/usa el Área Técnica
    #del estudiante.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la institución es de tipo Universidad (o Personalizado con el
    #módulo Universidad activo) — solo entonces se pide/usa la Carrera del
    #estudiante. Independiente de _es_politecnico(): en 'Personalizado' ambos
    #módulos pueden estar activos a la vez (por ejemplo, un politécnico que
    #también ofrece carreras universitarias), y en ese caso un mismo
    #estudiante puede tener área técnica Y carrera al mismo tiempo.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    #True solo cuando la institución es "Personalizado" y tiene
    #Politécnico Y Universidad activos a la vez -el único caso en el que
    #Área Técnica y Carrera dejan de ser obligatorias (ver el guardado
    #del formulario). Si la institución es puramente Politécnico o
    #puramente Universidad, o si "Personalizado" solo tiene UNO de los
    #dos módulos activo, esto es False y el campo correspondiente sigue
    #siendo obligatorio como siempre.
    def _ambos_modulos_tecnicos_activos(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Personalizado" and "Politécnico" in personalizados and "Universidad" in personalizados

    def _cargar_especialidad_ficha_combo(self):

        combo= self.combo_especialidad_estudiante
        es_poli= self._es_politecnico()
        combo.setVisible(es_poli)
        if not es_poli:
            return
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

    def _cargar_carrera_ficha_combo(self):

        combo= self.combo_carrera_estudiante
        es_uni= self._es_universidad()
        combo.setVisible(es_uni)
        if not es_uni:
            return
        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— Selecciona una carrera —", None)
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
        for fila in c.fetchall():
            combo.addItem(fila["nombre"], fila["id"])
        conn.close()
        idx= combo.findData(seleccion_previa)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    #Sincroniza los colores de las tarjetas y acentos de este módulo con el
    #tema/modo claro-oscuro actual de la app. Se llama al construir la pantalla
    #y cada vez que el usuario cambia de tema (ver main.py).
    def actualizar_tema(self):

        colores= _colores_tema(self.main_window)
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
        self.dialogo_filtros.setStyleSheet(f"""
            QDialog#DialogoFiltros {{
                background-color: {colores['bg_panel']};
            }}
            /* Repite aquí el mismo QToolTip que usa la ventana principal:
               este diálogo es una ventana de nivel superior aparte, y su
               propio setStyleSheet() reemplaza -para todo lo que esté
               dentro- cualquier regla heredada, incluido el QToolTip
               global. Sin esto, los tooltips de los combos aquí adentro
               caían al estilo nativo de Qt (gris claro/texto negro),
               inconsistente con el resto de AcaDeXI. */
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
            QComboBox {{
                background-color: {colores['bg_btn']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 22px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                border: 1px solid {colores['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                selection-background-color: {colores['accent']};
                selection-color: white;
                border: 1px solid {colores['bg_btn']};
                outline: none;
            }}
        """)
        self.icono_busqueda.establecer_color(colores["txt_sec"])
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
        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {colores['bg_panel']};
                color: {colores['txt_prim']};
                border: 1px solid {colores['bg_btn']};
                padding: 6px 10px;
                border-radius: 6px;
            }}
        """)

    #ANIMACIONES — capa puramente visual: no participan en la lógica de negocio, permisos, validación ni guardado
    #de datos.
    #Actualiza el chip '👥 N estudiantes' de la cabecera con una pequeña
    #animación de conteo, en vez de un cambio brusco de texto.
    def _animar_contador(self, valor_final):

        def texto(v):

            return f"{html_icono_emoji('👥', 15)} {v} estudiante" + ("s" if v != 1 else "")
        valor_inicial= getattr(self, "_contador_valor_actual", 0)
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