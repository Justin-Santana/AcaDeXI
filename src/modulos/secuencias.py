#Secuencias Didácticas de AcaDeXI: la planificación de unidades de aprendizaje (formato MINERD)
#ligada a las competencias, los indicadores y las tareas de la app.
#
#Los datos y la exportación a Word están en src/nucleo/secuencias.py. Acá solo está la interfaz:
#la lista de secuencias y el editor.
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QTabWidget,
    QTextEdit, QListWidget, QListWidgetItem, QFrame, QFileDialog, QFormLayout,
    QAbstractItemView, QMessageBox)

from src.nucleo import secuencias as logica
from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.nucleo.permisos import puede_editar, es_profesor_restringido, obtener_profesor_id, obtener_materias_permitidas
from src.nucleo.formato_hora import formatear_fecha
from src.interfaz.configuracion import anio_academico_actual
from src.interfaz.secuencias_widgets import TablaSesiones, COLORES_ESTADO, fecha_a_iso, iso_a_fecha, selector_fecha
from src.modulos.calificaciones import competencias_de_materia_grado, grados_de_materia


#Las materias activas que este usuario puede ver, como lista de (id, nombre). Un Profesor solo ve las suyas.
def _materias_disponibles(main_window):

    permitidas= obtener_materias_permitidas(main_window)

    conn= obtener_conexion()

    try:

        filas= conn.execute("SELECT id, nombre FROM materias WHERE COALESCE(estado,'Activa')='Activa' "
                            "ORDER BY nombre").fetchall()

    finally:
        conn.close()

    return [(fila["id"], fila["nombre"]) for fila in filas if permitidas is None or fila["id"] in permitidas]


def _crear_item_marcable(texto, marcado, dato=None):

    item= QListWidgetItem(texto)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setData(Qt.ItemDataRole.UserRole, dato)
    item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)

    return item


# -----------------------------------------
# editor de una secuencia
# -----------------------------------------
#Crea o edita una secuencia. Tiene cuatro pestañas: General, Pedagógico, Sesiones y Competencias y tareas.
class EditorSecuencia(QDialog):

    def __init__(self, main_window, secuencia_id=None, parent=None):

        super().__init__(parent or main_window)
        self.main_window= main_window
        self.secuencia_id= secuencia_id

        #Al editar, lo que ya estaba marcado se guarda acá mientras las listas se llenan, porque cada
        #lista depende de la anterior (materia y grado > competencias > indicadores).
        self.competencias_pendientes= set()
        self.indicadores_pendientes= set()
        self.tareas_pendientes= set()

        self.setWindowTitle("Editar secuencia didáctica" if secuencia_id else "Nueva secuencia didáctica")
        self.resize(1080, 700)

        #mientras se carga, los cambios de materia y grado no deben recargar las listas
        self._cargando= True

        self._construir_ui()
        self._cargar_catalogos()

        if secuencia_id:
            self._cargar(logica.obtener_secuencia(secuencia_id))
        else:
            self.tabla_sesiones.poblar(logica.sesiones_base(3))

        self._cargando= False
        self._al_cambiar_materia()

    #construcción
    def _construir_ui(self):

        disposicion= QVBoxLayout(self)

        pestanas= QTabWidget()
        pestanas.addTab(self._crear_pestana_general(), "General")
        pestanas.addTab(self._crear_pestana_pedagogica(), "Pedagógico")
        pestanas.addTab(self._crear_pestana_sesiones(), "Sesiones")
        pestanas.addTab(self._crear_pestana_vinculos(), "Competencias y tareas")
        disposicion.addWidget(pestanas, 1)

        botones= QDialogButtonBox()
        self.btn_guardar= botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)

    def _crear_pestana_general(self):

        pestana= QWidget()
        formulario= QFormLayout(pestana)

        self.in_titulo= QLineEdit()
        self.in_titulo.setPlaceholderText("Ej. Los textos narrativos")
        formulario.addRow("Título de la unidad *", self.in_titulo)

        self.combo_materia= QComboBox()
        self.combo_materia.currentIndexChanged.connect(self._al_cambiar_materia)
        formulario.addRow("Asignatura", self.combo_materia)

        self.combo_grado= QComboBox()
        self.combo_grado.currentIndexChanged.connect(self._al_cambiar_grado)
        formulario.addRow("Grado", self.combo_grado)

        self.combo_seccion= QComboBox()
        formulario.addRow("Sección", self.combo_seccion)

        self.combo_periodo= QComboBox()
        formulario.addRow("Período", self.combo_periodo)

        self.in_anio= QLineEdit(anio_academico_actual())
        formulario.addRow("Año escolar", self.in_anio)

        self.combo_estado= QComboBox()
        self.combo_estado.addItems(logica.ESTADOS_SECUENCIA)
        formulario.addRow("Estado", self.combo_estado)

        self.in_fecha_inicio= selector_fecha()
        formulario.addRow("Fecha de inicio", self.in_fecha_inicio)

        self.in_fecha_fin= selector_fecha()
        formulario.addRow("Fecha de fin", self.in_fecha_fin)

        return pestana

    def _crear_pestana_pedagogica(self):

        pestana= QWidget()
        formulario= QFormLayout(pestana)

        self.in_eje= QLineEdit()
        self.in_eje.setPlaceholderText("Eje transversal / descriptores")
        formulario.addRow("Eje transversal", self.in_eje)

        self.in_situacion= QTextEdit()
        self.in_situacion.setPlaceholderText("Situación de aprendizaje: contexto real y reto que enfrentan los estudiantes.")
        formulario.addRow("Situación de aprendizaje", self.in_situacion)

        self.lista_fundamentales= QListWidget()
        self.lista_fundamentales.setMaximumHeight(140)

        for nombre in logica.COMPETENCIAS_FUNDAMENTALES:
            self.lista_fundamentales.addItem(_crear_item_marcable(nombre, False))

        formulario.addRow("Competencias fundamentales", self.lista_fundamentales)

        self.in_conceptos= QTextEdit()
        formulario.addRow("Contenidos: conceptos", self.in_conceptos)

        self.in_procedimientos= QTextEdit()
        formulario.addRow("Contenidos: procedimientos", self.in_procedimientos)

        self.in_actitudes= QTextEdit()
        formulario.addRow("Contenidos: actitudes y valores", self.in_actitudes)

        self.in_estrategia= QTextEdit()
        self.in_estrategia.setPlaceholderText("Estrategia de enseñanza y de aprendizaje (p. ej. aprendizaje basado en proyectos).")
        formulario.addRow("Estrategia", self.in_estrategia)

        return pestana

    def _crear_pestana_sesiones(self):

        pestana= QWidget()
        disposicion= QVBoxLayout(pestana)

        self.tabla_sesiones= TablaSesiones()

        barra= QHBoxLayout()

        btn_agregar= QPushButton("Agregar sesión")
        btn_agregar.clicked.connect(self.tabla_sesiones.agregar_despues_de_la_actual)
        barra.addWidget(btn_agregar)

        btn_quitar= QPushButton("Quitar sesión")
        btn_quitar.clicked.connect(self.tabla_sesiones.quitar_actual)
        barra.addWidget(btn_quitar)

        btn_subir= QPushButton("Subir")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        btn_subir.clicked.connect(lambda: self.tabla_sesiones.mover_actual(-1))
        barra.addWidget(btn_subir)

        btn_bajar= QPushButton("Bajar")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        btn_bajar.clicked.connect(lambda: self.tabla_sesiones.mover_actual(1))
        barra.addWidget(btn_bajar)

        btn_fechas= QPushButton("Autocompletar fechas…")
        btn_fechas.clicked.connect(self._autocompletar_fechas)
        barra.addWidget(btn_fechas)

        barra.addStretch(1)

        disposicion.addLayout(barra)
        disposicion.addWidget(self.tabla_sesiones, 1)

        return pestana

    def _crear_pestana_vinculos(self):

        pestana= QWidget()
        disposicion= QHBoxLayout(pestana)

        self.lista_competencias= self._crear_columna_de_lista(disposicion, "Competencias específicas")
        self.lista_competencias.itemChanged.connect(self._al_cambiar_competencias)

        self.lista_indicadores= self._crear_columna_de_lista(disposicion, "Indicadores de logro")
        self.lista_tareas= self._crear_columna_de_lista(disposicion, "Tareas del Banco de Tareas")

        return pestana

    #Una columna con un título arriba y una lista debajo. Devuelve la lista.
    def _crear_columna_de_lista(self, disposicion, titulo):

        columna= QVBoxLayout()
        columna.addWidget(QLabel(titulo))

        lista= QListWidget()
        lista.setWordWrap(True)
        columna.addWidget(lista, 1)

        disposicion.addLayout(columna, 1)

        return lista

    #listas que dependen unas de otras
    def _cargar_catalogos(self):

        self.combo_materia.blockSignals(True)
        self.combo_materia.addItem("— Sin asignatura —", None)

        for materia_id, nombre in _materias_disponibles(self.main_window):
            self.combo_materia.addItem(nombre, materia_id)

        self.combo_materia.blockSignals(False)

        self.combo_periodo.addItem("— Sin período —", None)

        conn= obtener_conexion()

        try:

            filas= conn.execute("SELECT id, nombre, anio_academico FROM periodos ORDER BY anio_academico DESC, orden")

            for fila in filas:
                etiqueta= f"{fila['nombre']} ({fila['anio_academico']})" if fila["anio_academico"] else fila["nombre"]
                self.combo_periodo.addItem(etiqueta, fila["id"])

        finally:
            conn.close()

    #Llena el combo de grados con los de la materia elegida. Si la materia todavía no tiene horarios,
    #se ofrecen todos los grados.
    def _poblar_grados(self, grado_previo):

        materia_id= self.combo_materia.currentData()

        self.combo_grado.blockSignals(True)
        self.combo_grado.clear()
        self.combo_grado.addItem("— Sin grado —", None)

        grados= grados_de_materia(materia_id) if materia_id else []

        if not grados:

            conn= obtener_conexion()

            try:

                grados= [dict(fila) for fila in conn.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")]

            finally:
                conn.close()

        for grado in grados:
            self.combo_grado.addItem(grado["nombre"], grado["id"])

        self.combo_grado.setCurrentIndex(max(self.combo_grado.findData(grado_previo), 0))
        self.combo_grado.blockSignals(False)

    def _poblar_secciones(self, seccion_previa):

        grado_id= self.combo_grado.currentData()

        self.combo_seccion.blockSignals(True)
        self.combo_seccion.clear()
        self.combo_seccion.addItem("— Todas —", None)

        if grado_id:

            conn= obtener_conexion()

            try:

                for fila in conn.execute("SELECT id, nombre FROM secciones WHERE grado_id=? ORDER BY nombre", (grado_id,)):
                    self.combo_seccion.addItem(fila["nombre"], fila["id"])

            finally:
                conn.close()

        self.combo_seccion.setCurrentIndex(max(self.combo_seccion.findData(seccion_previa), 0))
        self.combo_seccion.blockSignals(False)

    def _al_cambiar_materia(self):

        if self._cargando:
            return

        self._poblar_grados(self.combo_grado.currentData())
        self._al_cambiar_grado()

    def _al_cambiar_grado(self):

        if self._cargando:
            return

        self._poblar_secciones(self.combo_seccion.currentData())
        self._recargar_competencias_y_tareas()

    #Los ids de los elementos marcados de una lista.
    def _marcados(self, lista):

        ids= []

        for posicion in range(lista.count()):

            item= lista.item(posicion)

            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))

        return ids

    def _nombres_marcados(self, lista):

        nombres= []

        for posicion in range(lista.count()):

            item= lista.item(posicion)

            if item.checkState() == Qt.CheckState.Checked:
                nombres.append(item.text())

        return nombres

    #Vacía la lista y la llena con las filas dadas, marcando las que estaban marcadas antes.
    def _poblar_lista_marcable(self, lista, filas, armar_texto, marcados):

        lista.blockSignals(True)
        lista.clear()

        for fila in filas:
            lista.addItem(_crear_item_marcable(armar_texto(fila), fila["id"] in marcados, fila["id"]))

        lista.blockSignals(False)

    #Al cambiar la materia o el grado se vuelven a cargar las competencias y las tareas, conservando lo
    #que ya estaba marcado.
    def _recargar_competencias_y_tareas(self):

        materia_id= self.combo_materia.currentData()
        grado_id= self.combo_grado.currentData()

        competencias_marcadas= set(self._marcados(self.lista_competencias)) | self.competencias_pendientes
        tareas_marcadas= set(self._marcados(self.lista_tareas)) | self.tareas_pendientes
        self.competencias_pendientes= set()
        self.tareas_pendientes= set()

        self._poblar_lista_marcable(self.lista_competencias, competencias_de_materia_grado(materia_id, grado_id),
                                    #fila: registro de la lista; la lambda arma el texto que se ve en cada casilla
                                    lambda fila: f"{fila['codigo']}. {fila['descripcion']}", competencias_marcadas)
        self._poblar_lista_marcable(self.lista_tareas, logica.tareas_de_materia(materia_id, grado_id),
                                    #fila: registro de la lista; la lambda arma el texto que se ve en cada casilla
                                    lambda fila: f"{fila['titulo']} ({fila['categoria'] or 'Tarea'})", tareas_marcadas)

        self._al_cambiar_competencias()

    #Los indicadores que se ofrecen son los de las competencias marcadas.
    def _al_cambiar_competencias(self, *_):

        indicadores_marcados= set(self._marcados(self.lista_indicadores)) | self.indicadores_pendientes
        self.indicadores_pendientes= set()

        indicadores= logica.indicadores_de_competencias(self._marcados(self.lista_competencias))

        self._poblar_lista_marcable(self.lista_indicadores, indicadores,
                                    #fila: registro de la lista; la lambda arma el texto que se ve en cada casilla
                                    lambda fila: f"{fila['codigo_competencia']} · {fila['codigo']}: {fila['descripcion']}",
                                    indicadores_marcados)

    def _autocompletar_fechas(self):

        ultima= self.tabla_sesiones.autocompletar_fechas(fecha_a_iso(self.in_fecha_inicio.date()), self)

        if ultima:
            self.in_fecha_fin.setDate(iso_a_fecha(ultima))

    #cargar y guardar
    def _cargar(self, secuencia):

        if secuencia is None:
            return

        self.in_titulo.setText(secuencia["titulo"])
        self.combo_materia.setCurrentIndex(max(self.combo_materia.findData(secuencia["materia_id"]), 0))
        self._cargar_grado_y_vinculos(secuencia)
        self.combo_periodo.setCurrentIndex(max(self.combo_periodo.findData(secuencia["periodo_id"]), 0))
        self.in_anio.setText(secuencia.get("anio_academico") or "")
        self.combo_estado.setCurrentText(secuencia["estado"])
        self.in_fecha_inicio.setDate(iso_a_fecha(secuencia["fecha_inicio"]))
        self.in_fecha_fin.setDate(iso_a_fecha(secuencia["fecha_fin"]))

        self.in_eje.setText(secuencia.get("eje_transversal") or "")
        self.in_situacion.setPlainText(secuencia.get("situacion_aprendizaje") or "")
        self.in_conceptos.setPlainText(secuencia.get("contenido_conceptos") or "")
        self.in_procedimientos.setPlainText(secuencia.get("contenido_procedimientos") or "")
        self.in_actitudes.setPlainText(secuencia.get("contenido_actitudes") or "")
        self.in_estrategia.setPlainText(secuencia.get("estrategia") or "")

        elegidas= set(secuencia["competencias_fundamentales_lista"])

        for posicion in range(self.lista_fundamentales.count()):
            item= self.lista_fundamentales.item(posicion)
            item.setCheckState(Qt.CheckState.Checked if item.text() in elegidas else Qt.CheckState.Unchecked)

        self.tabla_sesiones.poblar(secuencia["sesiones"] or logica.sesiones_base(3))

    #Al editar se fijan primero el grado y la sección guardados y después se marcan los vínculos. El
    #orden importa: las competencias dependen de la materia y el grado, y con el grado vacío no habría
    #nada que marcar.
    def _cargar_grado_y_vinculos(self, secuencia):

        self._poblar_grados(secuencia["grado_id"])
        self._poblar_secciones(secuencia["seccion_id"])

        self.competencias_pendientes= {competencia["id"] for competencia in secuencia["competencias"]}
        self.indicadores_pendientes= {indicador["id"] for indicador in secuencia["indicadores"]}
        self.tareas_pendientes= {tarea["id"] for tarea in secuencia["tareas"]}

        self._recargar_competencias_y_tareas()

    def _datos(self):

        return {
            "titulo": self.in_titulo.text(),
            "materia_id": self.combo_materia.currentData(),
            "grado_id": self.combo_grado.currentData(),
            "seccion_id": self.combo_seccion.currentData(),
            "profesor_id": self._profesor_id(),
            "periodo_id": self.combo_periodo.currentData(),
            "anio_academico": self.in_anio.text().strip(),
            "eje_transversal": self.in_eje.text().strip(),
            "situacion_aprendizaje": self.in_situacion.toPlainText().strip(),
            "competencias_fundamentales": logica.unir_competencias_fundamentales(
                self._nombres_marcados(self.lista_fundamentales)),
            "contenido_conceptos": self.in_conceptos.toPlainText().strip(),
            "contenido_procedimientos": self.in_procedimientos.toPlainText().strip(),
            "contenido_actitudes": self.in_actitudes.toPlainText().strip(),
            "estrategia": self.in_estrategia.toPlainText().strip(),
            "estado": self.combo_estado.currentText(),
            "fecha_inicio": fecha_a_iso(self.in_fecha_inicio.date()),
            "fecha_fin": fecha_a_iso(self.in_fecha_fin.date()),
        }

    #Si quien guarda es un Profesor, la secuencia queda a su nombre. Si no, al del profesor titular de la materia.
    def _profesor_id(self):

        profesor_id= obtener_profesor_id(self.main_window)

        if profesor_id is not None:
            return profesor_id

        materia_id= self.combo_materia.currentData()

        if not materia_id:
            return None

        conn= obtener_conexion()

        try:

            fila= conn.execute("SELECT profesor_id FROM materias WHERE id=?", (materia_id,)).fetchone()

        finally:
            conn.close()

        return fila["profesor_id"] if fila else None

    def _guardar(self):

        try:

            self.secuencia_id= logica.guardar_secuencia(
                self._datos(),
                competencias_ids=self._marcados(self.lista_competencias),
                indicadores_ids=self._marcados(self.lista_indicadores),
                tareas_ids=self._marcados(self.lista_tareas),
                sesiones=self.tabla_sesiones.sesiones(),
                secuencia_id=self.secuencia_id)

        except ValueError as error:
            mostrar_mensaje("advertencia", "Secuencia didáctica", str(error), self)
            return

        registrar_auditoria("Secuencias Didácticas", "Guardar secuencia",
                            getattr(self.main_window, "usuario_actual", None), self.in_titulo.text().strip())

        avisos= logica.validar_secuencia(logica.obtener_secuencia(self.secuencia_id))
        texto= "Secuencia guardada."

        if avisos:
            texto += "\n\nConviene completar:\n• " + "\n• ".join(avisos)

        mostrar_mensaje("exito", "Secuencia guardada", texto, self)
        self.accept()


# -----------------------------------------
# pantalla principal: la lista de secuencias
# -----------------------------------------
class ModuloSecuenciasDidacticas(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window

        self._construir_ui()
        self.actualizar_tema()
        self.refrescar()

    def _construir_ui(self):

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(12)

        disposicion.addWidget(self._crear_cabecera())
        disposicion.addLayout(self._crear_filtros())
        disposicion.addWidget(self._crear_tabla(), 1)
        disposicion.addLayout(self._crear_botones())

    def _crear_cabecera(self):

        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")

        disposicion= QHBoxLayout(self.frame_cabecera)
        disposicion.setContentsMargins(22, 18, 22, 18)
        disposicion.setSpacing(14)

        self.lbl_icono= QLabel("")
        self.lbl_icono.setObjectName("IconoCabeceraModulo")
        self.lbl_icono.setFixedSize(46, 46)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono, "Secuencias Didácticas")
        disposicion.addWidget(self.lbl_icono)

        textos= QVBoxLayout()
        textos.setSpacing(2)

        lbl_titulo= QLabel("Secuencias Didácticas")
        lbl_titulo.setObjectName("TituloCabeceraModulo")
        textos.addWidget(lbl_titulo)

        lbl_subtitulo= QLabel("Planifica tus unidades de aprendizaje con el esquema del MINERD: situación de aprendizaje, "
                              "competencias, indicadores de logro y sesiones con evidencias e instrumentos.")
        lbl_subtitulo.setWordWrap(True)
        lbl_subtitulo.setObjectName("SubtituloCabeceraModulo")
        textos.addWidget(lbl_subtitulo)

        disposicion.addLayout(textos, 1)

        self.lbl_contador= QLabel("0 secuencias")
        self.lbl_contador.setObjectName("ChipContador")
        disposicion.addWidget(self.lbl_contador)

        return self.frame_cabecera

    def _crear_filtros(self):

        filtros= QHBoxLayout()

        self.in_buscar= QLineEdit()
        self.in_buscar.setPlaceholderText("Buscar por título o situación…")
        self.in_buscar.textChanged.connect(self.refrescar)
        filtros.addWidget(self.in_buscar, 2)

        self.combo_materia= QComboBox()
        self.combo_materia.currentIndexChanged.connect(self.refrescar)
        filtros.addWidget(self.combo_materia, 1)

        self.combo_estado= QComboBox()
        self.combo_estado.addItem("Todos los estados", None)

        for estado in logica.ESTADOS_SECUENCIA:
            self.combo_estado.addItem(estado, estado)

        self.combo_estado.currentIndexChanged.connect(self.refrescar)
        filtros.addWidget(self.combo_estado, 1)

        return filtros

    def _crear_tabla(self):

        self.tabla_secuencias= QTableWidget(0, 7)
        self.tabla_secuencias.setHorizontalHeaderLabels(
            ["Título", "Asignatura", "Grado / Sección", "Período", "Fechas", "Avance", "Estado"])
        self.tabla_secuencias.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_secuencias.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_secuencias.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_secuencias.verticalHeader().setVisible(False)
        self.tabla_secuencias.setMinimumHeight(260)
        self.tabla_secuencias.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for columna in range(1, 7):
            self.tabla_secuencias.horizontalHeader().setSectionResizeMode(columna, QHeaderView.ResizeMode.ResizeToContents)

        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        self.tabla_secuencias.doubleClicked.connect(lambda *_: self._editar())

        return self.tabla_secuencias

    def _crear_botones(self):

        botones= QHBoxLayout()

        self.btn_nueva= QPushButton("Nueva secuencia")
        self.btn_nueva.clicked.connect(self._nueva)
        botones.addWidget(self.btn_nueva)

        self.btn_editar= QPushButton("Editar")
        self.btn_editar.clicked.connect(self._editar)
        botones.addWidget(self.btn_editar)

        self.btn_duplicar= QPushButton("Duplicar")
        self.btn_duplicar.clicked.connect(self._duplicar)
        botones.addWidget(self.btn_duplicar)

        self.btn_eliminar= QPushButton("Eliminar")
        self.btn_eliminar.clicked.connect(self._eliminar)
        botones.addWidget(self.btn_eliminar)

        botones.addStretch(1)

        self.btn_word= QPushButton("Exportar a Word")
        self.btn_word.clicked.connect(self._exportar)
        botones.addWidget(self.btn_word)

        #quien no puede editar solo mira y exporta
        if not puede_editar(self.main_window):
            for boton in (self.btn_nueva, self.btn_editar, self.btn_duplicar, self.btn_eliminar):
                boton.setEnabled(False)

        return botones

    def actualizar_tema(self):

        ventana= self.main_window
        paletas= getattr(ventana, "theme_palettes", None)

        if not paletas:
            return

        paleta= paletas.get(getattr(ventana, "tema_actual", "")) or next(iter(paletas.values()))
        indice= 1 if getattr(ventana, "modo_oscuro", True) else 0
        acento= paleta["btn_op_bg"][indice]
        hover= paleta["btn_op_hover"][indice] if "btn_op_hover" in paleta else acento

        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {acento},stop:1 {hover});
                border-radius: 18px; }}
            QLabel#IconoCabeceraModulo {{ background-color: rgba(255,255,255,40); border-radius: 23px;
                font-size: 22px; color: white; }}
            QLabel#TituloCabeceraModulo {{ font-size: 22px; font-weight: 800; color: white; background: transparent; }}
            QLabel#SubtituloCabeceraModulo {{ font-size: 12px; color: rgba(255,255,255,210); background: transparent; }}
            QLabel#ChipContador {{ background-color: rgba(255,255,255,40); color: white; border-radius: 12px;
                padding: 4px 12px; font-weight: 700; }}""")

    #datos
    #Un Profesor solo ve las secuencias de sus materias y las que él creó.
    def _filtros_de_acceso(self):

        if es_profesor_restringido(self.main_window):
            return obtener_profesor_id(self.main_window), obtener_materias_permitidas(self.main_window)

        return None, None

    def refrescar(self, *_):

        profesor_id, materias_permitidas= self._filtros_de_acceso()

        materia_previa= self.combo_materia.currentData()

        self.combo_materia.blockSignals(True)
        self.combo_materia.clear()
        self.combo_materia.addItem("Todas las asignaturas", None)

        for materia_id, nombre in _materias_disponibles(self.main_window):
            self.combo_materia.addItem(nombre, materia_id)

        self.combo_materia.setCurrentIndex(max(self.combo_materia.findData(materia_previa), 0))
        self.combo_materia.blockSignals(False)

        secuencias= logica.listar_secuencias(
            profesor_id=profesor_id, materias_permitidas=materias_permitidas,
            materia_id=self.combo_materia.currentData(), estado=self.combo_estado.currentData(),
            texto=self.in_buscar.text())

        self.tabla_secuencias.setRowCount(len(secuencias))

        for fila, secuencia in enumerate(secuencias):
            self._llenar_fila(fila, secuencia)

        plural= "s" if len(secuencias) != 1 else ""
        self.lbl_contador.setText(f"{len(secuencias)} secuencia{plural}")

    def _llenar_fila(self, fila, secuencia):

        fechas= " – ".join(fecha for fecha in (formatear_fecha(secuencia["fecha_inicio"], self.main_window),
                                               formatear_fecha(secuencia["fecha_fin"], self.main_window)) if fecha)
        grado_y_seccion= " ".join(texto for texto in (secuencia["grado"], secuencia["seccion"]) if texto)

        valores= [secuencia["titulo"], secuencia["materia"] or "—", grado_y_seccion or "—",
                  secuencia["periodo"] or "—", fechas or "—",
                  f"{secuencia['sesiones_realizadas']}/{secuencia['total_sesiones']} sesiones", secuencia["estado"]]

        for columna, valor in enumerate(valores):

            item= QTableWidgetItem(valor)

            #el id de la secuencia viaja escondido en la primera celda
            if columna == 0:
                item.setData(Qt.ItemDataRole.UserRole, secuencia["id"])

            #la última columna es el estado y va con su color
            if columna == 6:
                item.setForeground(Qt.GlobalColor.white)
                item.setBackground(QColor(COLORES_ESTADO.get(secuencia["estado"], "#64748B")))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tabla_secuencias.setItem(fila, columna, item)

    #El id de la secuencia seleccionada, o None (con un aviso) si no hay ninguna.
    def _id_seleccionado(self):

        fila= self.tabla_secuencias.currentRow()

        if fila < 0 or self.tabla_secuencias.item(fila, 0) is None:
            mostrar_mensaje("info", "Secuencias Didácticas", "Selecciona una secuencia de la tabla.", self)
            return None

        return self.tabla_secuencias.item(fila, 0).data(Qt.ItemDataRole.UserRole)

    #acciones
    def _nueva(self):

        if EditorSecuencia(self.main_window, None, self).exec():
            self.refrescar()

    def _editar(self):

        secuencia_id= self._id_seleccionado()

        if secuencia_id and puede_editar(self.main_window) and EditorSecuencia(self.main_window, secuencia_id, self).exec():
            self.refrescar()

    def _duplicar(self):

        secuencia_id= self._id_seleccionado()

        if secuencia_id:
            logica.duplicar_secuencia(secuencia_id)
            self.refrescar()

    def _eliminar(self):

        secuencia_id= self._id_seleccionado()

        if not secuencia_id:
            return

        respuesta= QMessageBox.question(
            self, "Eliminar secuencia",
            "¿Eliminar esta secuencia y sus sesiones? No se borran las tareas ni las competencias vinculadas.")

        if respuesta != QMessageBox.StandardButton.Yes:
            return

        logica.eliminar_secuencia(secuencia_id)
        registrar_auditoria("Secuencias Didácticas", "Eliminar secuencia",
                            getattr(self.main_window, "usuario_actual", None), str(secuencia_id))
        self.refrescar()

    def _exportar(self):

        secuencia_id= self._id_seleccionado()

        if not secuencia_id:
            return

        secuencia= logica.obtener_secuencia(secuencia_id)

        #el título se vuelve un nombre de archivo válido: lo que no es letra, número, espacio, _ o - pasa a _
        nombre_sugerido= "".join(letra if letra.isalnum() or letra in " _-" else "_" for letra in secuencia["titulo"]).strip() or "secuencia"

        ruta, _= QFileDialog.getSaveFileName(
            self, "Exportar secuencia", os.path.join(os.path.expanduser("~"), nombre_sugerido + ".docx"),
            "Documento de Word (*.docx)")

        if not ruta:
            return

        if not ruta.lower().endswith(".docx"):
            ruta += ".docx"

        try:

            logica.exportar_docx(secuencia_id, ruta)

        except Exception as error:
            #puede fallar por permisos o porque el archivo está abierto en Word
            mostrar_mensaje("error", "Exportar", f"No se pudo guardar el archivo:\n{error}", self)
            return

        mostrar_mensaje("exito", "Exportar", f"Secuencia exportada en:\n{ruta}", self)
