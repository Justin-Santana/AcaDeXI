#Secuencias Didácticas de la edición Single Teacher.
#
#Mismo esquema MINERD que src/modulos/secuencias.py, pero sobre bd_single_teacher: el curso del docente
#es una "sección" libre y las competencias específicas y los indicadores de logro se escriben como
#texto, una por línea. Los datos y el Word están en src/nucleo/secuencias_st.py.
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QTabWidget, QTextEdit, QListWidget,
    QListWidgetItem, QFormLayout, QAbstractItemView, QFileDialog, QMessageBox)

from src.nucleo import bd_single_teacher
from src.nucleo import secuencias as secuencias_comunes
from src.nucleo import secuencias_st as logica
from src.nucleo.iconos import mostrar_mensaje
from src.nucleo.formato_hora import formatear_fecha
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.configuracion import anio_academico_actual
from src.interfaz.secuencias_widgets import TablaSesiones, COLORES_ESTADO, fecha_a_iso, iso_a_fecha, selector_fecha
from src.interfaz.single_teacher_ui import _recargar_combo_cursos, _recargar_combo_materias, _recargar_combo_periodos


def _crear_item_marcable(texto, marcado, dato=None):

    item= QListWidgetItem(texto)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setData(Qt.ItemDataRole.UserRole, dato)
    item.setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)

    return item


# -----------------------------------------
# editor de una secuencia
# -----------------------------------------
class EditorSecuenciaST(QDialog):

    def __init__(self, main_window, secuencia_id=None, parent=None):

        super().__init__(parent or main_window)
        self.main_window= main_window
        self.secuencia_id= secuencia_id

        #Al editar, las tareas que ya estaban marcadas se guardan acá hasta que la lista se llene.
        self.tareas_pendientes= set()

        self.setWindowTitle("Editar secuencia didáctica" if secuencia_id else "Nueva secuencia didáctica")
        self.resize(1040, 680)

        self._build_ui()

        _recargar_combo_materias(main_window, self.combo_materia)
        _recargar_combo_cursos(main_window, self.combo_curso)
        _recargar_combo_periodos(main_window, self.combo_periodo)

        if secuencia_id:
            self._cargar(logica.obtener_secuencia(secuencia_id, main_window))
        else:
            self.tabla_sesiones.poblar(secuencias_comunes.sesiones_base(3))

        #estas señales se conectan al final para que llenar los combos de arriba no recargue las tareas
        self.combo_materia.currentIndexChanged.connect(self._recargar_tareas)
        self.combo_curso.currentIndexChanged.connect(self._recargar_tareas)
        self._recargar_tareas()

    #construcción
    def _build_ui(self):

        layout= QVBoxLayout(self)

        pestanas= QTabWidget()
        pestanas.addTab(self._crear_pestana_general(), "General")
        pestanas.addTab(self._crear_pestana_pedagogica(), "Pedagógico")
        pestanas.addTab(self._crear_pestana_sesiones(), "Sesiones")
        pestanas.addTab(self._crear_pestana_tareas(), "Tareas")
        layout.addWidget(pestanas, 1)

        botones= QDialogButtonBox()
        botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def _crear_pestana_general(self):

        pestana= QWidget()
        formulario= QFormLayout(pestana)

        self.in_titulo= QLineEdit()
        self.in_titulo.setPlaceholderText("Ej. Los textos narrativos")
        limitar_campo_texto(self.in_titulo)
        formulario.addRow("Título de la unidad *", self.in_titulo)

        self.combo_materia= QComboBox()
        formulario.addRow("Materia", self.combo_materia)

        self.combo_curso= QComboBox()
        formulario.addRow("Curso", self.combo_curso)

        self.combo_periodo= QComboBox()
        formulario.addRow("Período", self.combo_periodo)

        self.in_anio= QLineEdit(anio_academico_actual())
        formulario.addRow("Año escolar", self.in_anio)

        self.combo_estado= QComboBox()
        self.combo_estado.addItems(secuencias_comunes.ESTADOS_SECUENCIA)
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
        formulario.addRow("Eje transversal", self.in_eje)

        self.in_situacion= QTextEdit()
        self.in_situacion.setPlaceholderText("Situación de aprendizaje: contexto real y reto que enfrentan los estudiantes.")
        formulario.addRow("Situación de aprendizaje", self.in_situacion)

        self.lista_fundamentales= QListWidget()
        self.lista_fundamentales.setMaximumHeight(130)

        for nombre in secuencias_comunes.COMPETENCIAS_FUNDAMENTALES:
            self.lista_fundamentales.addItem(_crear_item_marcable(nombre, False))

        formulario.addRow("Competencias fundamentales", self.lista_fundamentales)

        self.in_competencias= QTextEdit()
        self.in_competencias.setPlaceholderText("Una competencia específica por línea")
        formulario.addRow("Competencias específicas", self.in_competencias)

        self.in_indicadores= QTextEdit()
        self.in_indicadores.setPlaceholderText("Un indicador de logro por línea")
        formulario.addRow("Indicadores de logro", self.in_indicadores)

        self.in_conceptos= QTextEdit()
        formulario.addRow("Contenidos: conceptos", self.in_conceptos)

        self.in_procedimientos= QTextEdit()
        formulario.addRow("Contenidos: procedimientos", self.in_procedimientos)

        self.in_actitudes= QTextEdit()
        formulario.addRow("Contenidos: actitudes y valores", self.in_actitudes)

        self.in_estrategia= QTextEdit()
        formulario.addRow("Estrategia", self.in_estrategia)

        return pestana

    def _crear_pestana_sesiones(self):

        pestana= QWidget()
        layout= QVBoxLayout(pestana)

        self.tabla_sesiones= TablaSesiones()

        barra= QHBoxLayout()

        btn_agregar= QPushButton("Agregar sesión")
        btn_agregar.clicked.connect(self.tabla_sesiones.agregar_despues_de_la_actual)
        barra.addWidget(btn_agregar)

        btn_quitar= QPushButton("Quitar sesión")
        btn_quitar.clicked.connect(self.tabla_sesiones.quitar_actual)
        barra.addWidget(btn_quitar)

        btn_subir= QPushButton("Subir")
        btn_subir.clicked.connect(lambda: self.tabla_sesiones.mover_actual(-1))
        barra.addWidget(btn_subir)

        btn_bajar= QPushButton("Bajar")
        btn_bajar.clicked.connect(lambda: self.tabla_sesiones.mover_actual(1))
        barra.addWidget(btn_bajar)

        btn_fechas= QPushButton("Autocompletar fechas…")
        btn_fechas.clicked.connect(self._autocompletar_fechas)
        barra.addWidget(btn_fechas)

        barra.addStretch(1)

        layout.addLayout(barra)
        layout.addWidget(self.tabla_sesiones, 1)

        return pestana

    def _crear_pestana_tareas(self):

        pestana= QWidget()
        layout= QVBoxLayout(pestana)

        layout.addWidget(QLabel("Tareas del Banco de Tareas que forman parte de esta secuencia"))

        self.lista_tareas= QListWidget()
        layout.addWidget(self.lista_tareas, 1)

        return pestana

    #tareas
    #Los ids de las tareas marcadas.
    def _tareas_marcadas(self):

        ids= []

        for posicion in range(self.lista_tareas.count()):

            item= self.lista_tareas.item(posicion)

            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))

        return ids

    #Vuelve a cargar las tareas de la materia y el curso elegidos, conservando las que estaban marcadas.
    def _recargar_tareas(self, *_):

        marcadas= set(self._tareas_marcadas()) | self.tareas_pendientes
        self.tareas_pendientes= set()

        self.lista_tareas.clear()

        tareas= logica.tareas_de_materia(self.combo_materia.currentData(), self.combo_curso.currentData(),
                                         self.main_window)

        for tarea in tareas:
            self.lista_tareas.addItem(_crear_item_marcable(tarea["titulo"], tarea["id"] in marcadas, tarea["id"]))

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
        self.combo_curso.setCurrentIndex(max(self.combo_curso.findData(secuencia["seccion_id"]), 0))
        self.combo_periodo.setCurrentIndex(max(self.combo_periodo.findData(secuencia["periodo_id"]), 0))
        self.in_anio.setText(secuencia.get("anio_academico") or "")
        self.combo_estado.setCurrentText(secuencia["estado"])
        self.in_fecha_inicio.setDate(iso_a_fecha(secuencia["fecha_inicio"]))
        self.in_fecha_fin.setDate(iso_a_fecha(secuencia["fecha_fin"]))

        self.in_eje.setText(secuencia.get("eje_transversal") or "")
        self.in_situacion.setPlainText(secuencia.get("situacion_aprendizaje") or "")
        self.in_competencias.setPlainText(secuencia.get("competencias_especificas") or "")
        self.in_indicadores.setPlainText(secuencia.get("indicadores_logro") or "")
        self.in_conceptos.setPlainText(secuencia.get("contenido_conceptos") or "")
        self.in_procedimientos.setPlainText(secuencia.get("contenido_procedimientos") or "")
        self.in_actitudes.setPlainText(secuencia.get("contenido_actitudes") or "")
        self.in_estrategia.setPlainText(secuencia.get("estrategia") or "")

        elegidas= set(secuencia["competencias_fundamentales_lista"])

        for posicion in range(self.lista_fundamentales.count()):
            item= self.lista_fundamentales.item(posicion)
            item.setCheckState(Qt.CheckState.Checked if item.text() in elegidas else Qt.CheckState.Unchecked)

        self.tabla_sesiones.poblar(secuencia["sesiones"] or secuencias_comunes.sesiones_base(3))
        self.tareas_pendientes= {tarea["id"] for tarea in secuencia["tareas"]}

    def _competencias_fundamentales_marcadas(self):

        nombres= []

        for posicion in range(self.lista_fundamentales.count()):

            item= self.lista_fundamentales.item(posicion)

            if item.checkState() == Qt.CheckState.Checked:
                nombres.append(item.text())

        return nombres

    def _datos(self):

        return {
            "titulo": self.in_titulo.text(),
            "materia_id": self.combo_materia.currentData(),
            "seccion_id": self.combo_curso.currentData(),
            "periodo_id": self.combo_periodo.currentData(),
            "anio_academico": self.in_anio.text().strip(),
            "eje_transversal": self.in_eje.text().strip(),
            "situacion_aprendizaje": self.in_situacion.toPlainText().strip(),
            "competencias_fundamentales": secuencias_comunes.unir_competencias_fundamentales(
                self._competencias_fundamentales_marcadas()),
            "competencias_especificas": "\n".join(logica.lineas(self.in_competencias.toPlainText())),
            "indicadores_logro": "\n".join(logica.lineas(self.in_indicadores.toPlainText())),
            "contenido_conceptos": self.in_conceptos.toPlainText().strip(),
            "contenido_procedimientos": self.in_procedimientos.toPlainText().strip(),
            "contenido_actitudes": self.in_actitudes.toPlainText().strip(),
            "estrategia": self.in_estrategia.toPlainText().strip(),
            "estado": self.combo_estado.currentText(),
            "fecha_inicio": fecha_a_iso(self.in_fecha_inicio.date()),
            "fecha_fin": fecha_a_iso(self.in_fecha_fin.date()),
        }

    def _guardar(self):

        try:
            self.secuencia_id= logica.guardar_secuencia(
                self._datos(), tareas_ids=self._tareas_marcadas(), sesiones=self.tabla_sesiones.sesiones(),
                secuencia_id=self.secuencia_id, main_window=self.main_window)

        except ValueError as error:
            mostrar_mensaje("advertencia", "Secuencia didáctica", str(error), self)
            return

        secuencia= logica.obtener_secuencia(self.secuencia_id, self.main_window)
        avisos= secuencias_comunes.validar_secuencia(secuencia)
        texto= "Secuencia guardada."

        if avisos:
            texto += "\n\nConviene completar:\n• " + "\n• ".join(avisos)

        mostrar_mensaje("exito", "Secuencia guardada", texto, self)
        self.accept()


# -----------------------------------------
# pantalla principal: la lista de secuencias
# -----------------------------------------
class ModuloSecuenciasST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window

        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        lbl_titulo= QLabel("📝 Secuencias Didácticas")
        lbl_titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(lbl_titulo)

        layout.addWidget(QLabel("Planifica tus unidades con el esquema del MINERD y expórtalas a Word."))

        layout.addLayout(self._crear_filtros())
        layout.addWidget(self._crear_tabla(), 1)
        layout.addLayout(self._crear_botones())

        self.refrescar()

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

        for estado in secuencias_comunes.ESTADOS_SECUENCIA:
            self.combo_estado.addItem(estado, estado)

        self.combo_estado.currentIndexChanged.connect(self.refrescar)
        filtros.addWidget(self.combo_estado, 1)

        return filtros

    def _crear_tabla(self):

        self.tabla_secuencias= QTableWidget(0, 6)
        self.tabla_secuencias.setHorizontalHeaderLabels(["Título", "Materia", "Curso", "Fechas", "Avance", "Estado"])
        self.tabla_secuencias.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_secuencias.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_secuencias.verticalHeader().setVisible(False)
        self.tabla_secuencias.setMinimumHeight(240)
        self.tabla_secuencias.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_secuencias.doubleClicked.connect(lambda *_: self._editar())

        return self.tabla_secuencias

    def _crear_botones(self):

        botones= QHBoxLayout()

        #el nombre de objeto "BtnAccionAgregar" le da el estilo del botón principal
        self.btn_nueva= QPushButton("Nueva secuencia")
        self.btn_nueva.setObjectName("BtnAccionAgregar")
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

        return botones

    #datos
    def refrescar(self, *_):

        materia_previa= self.combo_materia.currentData()

        self.combo_materia.blockSignals(True)
        self.combo_materia.clear()
        self.combo_materia.addItem("Todas las materias", None)

        conn= bd_single_teacher.obtener_conexion(self.main_window)

        try:
            for fila in conn.execute("SELECT id, nombre FROM materias ORDER BY nombre"):
                self.combo_materia.addItem(fila["nombre"], fila["id"])

        finally:
            conn.close()

        self.combo_materia.setCurrentIndex(max(self.combo_materia.findData(materia_previa), 0))
        self.combo_materia.blockSignals(False)

        secuencias= logica.listar_secuencias(
            materia_id=self.combo_materia.currentData(), estado=self.combo_estado.currentData(),
            texto=self.in_buscar.text(), main_window=self.main_window)

        self.tabla_secuencias.setRowCount(len(secuencias))

        for fila, secuencia in enumerate(secuencias):
            self._llenar_fila(fila, secuencia)

    def _llenar_fila(self, fila, secuencia):

        fechas= " – ".join(fecha for fecha in (formatear_fecha(secuencia["fecha_inicio"], self.main_window),
                                               formatear_fecha(secuencia["fecha_fin"], self.main_window)) if fecha)

        valores= [secuencia["titulo"], secuencia["materia"] or "—", secuencia["curso"] or "—", fechas or "—",
                  f"{secuencia['sesiones_realizadas']}/{secuencia['total_sesiones']} sesiones", secuencia["estado"]]

        for columna, valor in enumerate(valores):

            item= QTableWidgetItem(valor)

            #el id de la secuencia viaja escondido en la primera celda
            if columna == 0:
                item.setData(Qt.ItemDataRole.UserRole, secuencia["id"])

            #la última columna es el estado y va con su color
            if columna == 5:
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

        if EditorSecuenciaST(self.main_window, None, self).exec():
            self.refrescar()

    def _editar(self):

        secuencia_id= self._id_seleccionado()

        if secuencia_id and EditorSecuenciaST(self.main_window, secuencia_id, self).exec():
            self.refrescar()

    def _duplicar(self):

        secuencia_id= self._id_seleccionado()

        if secuencia_id:
            logica.duplicar_secuencia(secuencia_id, main_window=self.main_window)
            self.refrescar()

    def _eliminar(self):

        secuencia_id= self._id_seleccionado()

        if not secuencia_id:
            return

        respuesta= QMessageBox.question(
            self, "Eliminar secuencia", "¿Eliminar esta secuencia y sus sesiones? No se borran tus tareas.")

        if respuesta == QMessageBox.StandardButton.Yes:
            logica.eliminar_secuencia(secuencia_id, self.main_window)
            self.refrescar()

    def _exportar(self):

        secuencia_id= self._id_seleccionado()

        if not secuencia_id:
            return

        secuencia= logica.obtener_secuencia(secuencia_id, self.main_window)

        #el título se vuelve un nombre de archivo válido: lo que no es letra, número, espacio, _ o - pasa a _
        nombre_sugerido= "".join(letra if letra.isalnum() or letra in " _-" else "_" for letra in secuencia["titulo"]).strip() or "secuencia"

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar secuencia", os.path.join(os.path.expanduser("~"), nombre_sugerido + ".docx"),
            "Documento de Word (*.docx)")

        if not ruta:
            return

        if not ruta.lower().endswith(".docx"):
            ruta += ".docx"

        try:
            logica.exportar_docx(secuencia_id, ruta, self.main_window)

        except Exception as error:
            mostrar_mensaje("error", "Exportar", f"No se pudo guardar el archivo:\n{error}", self)
            return

        mostrar_mensaje("exito", "Exportar", f"Secuencia exportada en:\n{ruta}", self)
