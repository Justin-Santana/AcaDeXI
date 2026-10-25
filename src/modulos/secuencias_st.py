"""Secuencias Didácticas de la edición Single Teacher.

Mismo esquema MINERD que src/modulos/secuencias.py, pero sobre bd_single_teacher: el curso del
docente es una "sección" libre y las competencias específicas e indicadores de logro se escriben
como texto (una por línea). Datos y Word en src/nucleo/secuencias_st.py."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QTabWidget, QTextEdit, QListWidget,
    QListWidgetItem, QFormLayout, QAbstractItemView, QFileDialog, QMessageBox)

from src.nucleo import bd_single_teacher as db
from src.nucleo import secuencias_st as logica
from src.nucleo.iconos import mostrar_mensaje
from src.nucleo.formato_hora import formatear_fecha
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.configuracion import anio_academico_actual
from src.interfaz.secuencias_widgets import (TablaSesiones, COLORES_ESTADO, fecha_a_iso, iso_a_fecha,
                                             selector_fecha)
from src.interfaz.single_teacher_ui import (_recargar_combo_cursos, _recargar_combo_materias,
                                            _recargar_combo_periodos)


class EditorSecuenciaST(QDialog):
    def __init__(self, main_window, secuencia_id=None, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.secuencia_id = secuencia_id
        self._tareas_pendientes = set()
        self.setWindowTitle("Editar secuencia didáctica" if secuencia_id else "Nueva secuencia didáctica")
        self.resize(1040, 680)
        self._build_ui()
        _recargar_combo_materias(main_window, self.cb_materia)
        _recargar_combo_cursos(main_window, self.cb_curso)
        _recargar_combo_periodos(main_window, self.cb_periodo)
        if secuencia_id:
            self._cargar(logica.obtener_secuencia(secuencia_id, main_window))
        else:
            self.tabla.poblar(logica.sesiones_base(3))
        self.cb_materia.currentIndexChanged.connect(self._recargar_tareas)
        self.cb_curso.currentIndexChanged.connect(self._recargar_tareas)
        self._recargar_tareas()

    # ---------------- construcción ----------------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        tabs = QTabWidget(); lay.addWidget(tabs, 1)

        g = QWidget(); f = QFormLayout(g)
        self.in_titulo = QLineEdit(); self.in_titulo.setPlaceholderText("Ej. Los textos narrativos")
        limitar_campo_texto(self.in_titulo)
        self.cb_materia, self.cb_curso, self.cb_periodo = QComboBox(), QComboBox(), QComboBox()
        self.in_anio = QLineEdit(anio_academico_actual())
        self.cb_estado = QComboBox(); self.cb_estado.addItems(logica.ESTADOS_SECUENCIA)
        self.f_inicio, self.f_fin = selector_fecha(), selector_fecha()
        for et, w in (("Título de la unidad *", self.in_titulo), ("Materia", self.cb_materia),
                      ("Curso", self.cb_curso), ("Período", self.cb_periodo), ("Año escolar", self.in_anio),
                      ("Estado", self.cb_estado), ("Fecha de inicio", self.f_inicio), ("Fecha de fin", self.f_fin)):
            f.addRow(et, w)
        tabs.addTab(g, "General")

        p = QWidget(); f = QFormLayout(p)
        self.in_eje = QLineEdit()
        self.tx_situacion = QTextEdit()
        self.tx_situacion.setPlaceholderText("Situación de aprendizaje: contexto real y reto que enfrentan los estudiantes.")
        self.lista_fund = QListWidget(); self.lista_fund.setMaximumHeight(130)
        for nombre in logica.COMPETENCIAS_FUNDAMENTALES:
            it = QListWidgetItem(nombre); it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked); self.lista_fund.addItem(it)
        self.tx_ce = QTextEdit(); self.tx_ce.setPlaceholderText("Una competencia específica por línea")
        self.tx_il = QTextEdit(); self.tx_il.setPlaceholderText("Un indicador de logro por línea")
        self.tx_conceptos, self.tx_procedimientos, self.tx_actitudes = QTextEdit(), QTextEdit(), QTextEdit()
        self.tx_estrategia = QTextEdit()
        for et, w in (("Eje transversal", self.in_eje), ("Situación de aprendizaje", self.tx_situacion),
                      ("Competencias fundamentales", self.lista_fund), ("Competencias específicas", self.tx_ce),
                      ("Indicadores de logro", self.tx_il), ("Contenidos: conceptos", self.tx_conceptos),
                      ("Contenidos: procedimientos", self.tx_procedimientos),
                      ("Contenidos: actitudes y valores", self.tx_actitudes), ("Estrategia", self.tx_estrategia)):
            f.addRow(et, w)
        tabs.addTab(p, "Pedagógico")

        s = QWidget(); sl = QVBoxLayout(s)
        self.tabla = TablaSesiones()
        barra = QHBoxLayout()
        for texto, accion in (("Agregar sesión", self.tabla.agregar_despues_de_la_actual),
                              ("Quitar sesión", self.tabla.quitar_actual),
                              ("Subir", lambda: self.tabla.mover_actual(-1)),
                              ("Bajar", lambda: self.tabla.mover_actual(1)),
                              ("Autocompletar fechas…", self._autocompletar_fechas)):
            b = QPushButton(texto); b.clicked.connect(accion); barra.addWidget(b)
        barra.addStretch(1)
        sl.addLayout(barra); sl.addWidget(self.tabla, 1)
        tabs.addTab(s, "Sesiones")

        t = QWidget(); tl = QVBoxLayout(t)
        tl.addWidget(QLabel("Tareas del Banco de Tareas que forman parte de esta secuencia"))
        self.lista_tareas = QListWidget(); tl.addWidget(self.lista_tareas, 1)
        tabs.addTab(t, "Tareas")

        botones = QDialogButtonBox()
        botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botones.accepted.connect(self._guardar); botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    # ---------------- datos ----------------
    def _marcadas(self):
        return [self.lista_tareas.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista_tareas.count())
                if self.lista_tareas.item(i).checkState() == Qt.CheckState.Checked]

    def _recargar_tareas(self, *_):
        previas = set(self._marcadas()) | self._tareas_pendientes
        self._tareas_pendientes = set()
        self.lista_tareas.clear()
        for t in logica.tareas_de_materia(self.cb_materia.currentData(), self.cb_curso.currentData(),
                                          self.main_window):
            it = QListWidgetItem(t["titulo"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setData(Qt.ItemDataRole.UserRole, t["id"])
            it.setCheckState(Qt.CheckState.Checked if t["id"] in previas else Qt.CheckState.Unchecked)
            self.lista_tareas.addItem(it)

    def _autocompletar_fechas(self):
        ultima = self.tabla.autocompletar_fechas(fecha_a_iso(self.f_inicio.date()), self)
        if ultima:
            self.f_fin.setDate(iso_a_fecha(ultima))

    def _cargar(self, sec):
        if sec is None:
            return
        self.in_titulo.setText(sec["titulo"])
        self.cb_materia.setCurrentIndex(max(self.cb_materia.findData(sec["materia_id"]), 0))
        self.cb_curso.setCurrentIndex(max(self.cb_curso.findData(sec["seccion_id"]), 0))
        self.cb_periodo.setCurrentIndex(max(self.cb_periodo.findData(sec["periodo_id"]), 0))
        self.in_anio.setText(sec.get("anio_academico") or "")
        self.cb_estado.setCurrentText(sec["estado"])
        self.f_inicio.setDate(iso_a_fecha(sec["fecha_inicio"])); self.f_fin.setDate(iso_a_fecha(sec["fecha_fin"]))
        self.in_eje.setText(sec.get("eje_transversal") or "")
        self.tx_situacion.setPlainText(sec.get("situacion_aprendizaje") or "")
        self.tx_ce.setPlainText(sec.get("competencias_especificas") or "")
        self.tx_il.setPlainText(sec.get("indicadores_logro") or "")
        self.tx_conceptos.setPlainText(sec.get("contenido_conceptos") or "")
        self.tx_procedimientos.setPlainText(sec.get("contenido_procedimientos") or "")
        self.tx_actitudes.setPlainText(sec.get("contenido_actitudes") or "")
        self.tx_estrategia.setPlainText(sec.get("estrategia") or "")
        elegidas = set(sec["competencias_fundamentales_lista"])
        for i in range(self.lista_fund.count()):
            it = self.lista_fund.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.text() in elegidas else Qt.CheckState.Unchecked)
        self.tabla.poblar(sec["sesiones"] or logica.sesiones_base(3))
        self._tareas_pendientes = {t["id"] for t in sec["tareas"]}

    def _datos(self):
        return {
            "titulo": self.in_titulo.text(), "materia_id": self.cb_materia.currentData(),
            "seccion_id": self.cb_curso.currentData(), "periodo_id": self.cb_periodo.currentData(),
            "anio_academico": self.in_anio.text().strip(), "eje_transversal": self.in_eje.text().strip(),
            "situacion_aprendizaje": self.tx_situacion.toPlainText().strip(),
            "competencias_fundamentales": logica.unir_competencias_fundamentales(
                [self.lista_fund.item(i).text() for i in range(self.lista_fund.count())
                 if self.lista_fund.item(i).checkState() == Qt.CheckState.Checked]),
            "competencias_especificas": "\n".join(logica.lineas(self.tx_ce.toPlainText())),
            "indicadores_logro": "\n".join(logica.lineas(self.tx_il.toPlainText())),
            "contenido_conceptos": self.tx_conceptos.toPlainText().strip(),
            "contenido_procedimientos": self.tx_procedimientos.toPlainText().strip(),
            "contenido_actitudes": self.tx_actitudes.toPlainText().strip(),
            "estrategia": self.tx_estrategia.toPlainText().strip(), "estado": self.cb_estado.currentText(),
            "fecha_inicio": fecha_a_iso(self.f_inicio.date()), "fecha_fin": fecha_a_iso(self.f_fin.date()),
        }

    def _guardar(self):
        try:
            self.secuencia_id = logica.guardar_secuencia(
                self._datos(), self._marcadas(), self.tabla.sesiones(), self.secuencia_id, self.main_window)
        except ValueError as e:
            mostrar_mensaje("advertencia", "Secuencia didáctica", str(e), self)
            return
        avisos = logica.validar_secuencia(logica.obtener_secuencia(self.secuencia_id, self.main_window))
        if avisos:
            mostrar_mensaje("info", "Secuencia guardada",
                            "Se guardó, pero conviene completar:\n\n• " + "\n• ".join(avisos), self)
        self.accept()


class ModuloSecuenciasST(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(14)
        titulo = QLabel("📝 Secuencias Didácticas")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        lay.addWidget(titulo)
        lay.addWidget(QLabel("Planifica tus unidades con el esquema del MINERD y expórtalas a Word."))

        filtros = QHBoxLayout()
        self.in_buscar = QLineEdit(); self.in_buscar.setPlaceholderText("Buscar por título o situación…")
        self.cb_materia = QComboBox(); self.cb_estado = QComboBox()
        self.cb_estado.addItem("Todos los estados", None)
        for e in logica.ESTADOS_SECUENCIA:
            self.cb_estado.addItem(e, e)
        filtros.addWidget(self.in_buscar, 2); filtros.addWidget(self.cb_materia, 1); filtros.addWidget(self.cb_estado, 1)
        lay.addLayout(filtros)
        self.in_buscar.textChanged.connect(self.refrescar)
        self.cb_materia.currentIndexChanged.connect(self.refrescar)
        self.cb_estado.currentIndexChanged.connect(self.refrescar)

        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Título", "Materia", "Curso", "Fechas", "Avance", "Estado"])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setMinimumHeight(240)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla.doubleClicked.connect(lambda *_: self._editar())
        lay.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        for texto, accion in (("Nueva secuencia", self._nueva), ("Editar", self._editar),
                              ("Duplicar", self._duplicar), ("Eliminar", self._eliminar)):
            b = QPushButton(texto); b.clicked.connect(accion); botones.addWidget(b)
            if texto == "Nueva secuencia":
                b.setObjectName("BtnAccionAgregar")
        botones.addStretch(1)
        b = QPushButton("Exportar a Word"); b.clicked.connect(self._exportar); botones.addWidget(b)
        lay.addLayout(botones)
        self.refrescar()

    def refrescar(self, *_):
        previa = self.cb_materia.currentData()
        self.cb_materia.blockSignals(True)
        self.cb_materia.clear(); self.cb_materia.addItem("Todas las materias", None)
        conn = db.get_connection(self.main_window)
        try:
            for f in conn.execute("SELECT id, nombre FROM materias ORDER BY nombre"):
                self.cb_materia.addItem(f["nombre"], f["id"])
        finally:
            conn.close()
        self.cb_materia.setCurrentIndex(max(self.cb_materia.findData(previa), 0))
        self.cb_materia.blockSignals(False)
        filas = logica.listar_secuencias(self.cb_materia.currentData(), None, self.cb_estado.currentData(),
                                         self.in_buscar.text(), self.main_window)
        self.tabla.setRowCount(len(filas))
        for r, f in enumerate(filas):
            fechas = " – ".join(x for x in (formatear_fecha(f["fecha_inicio"], self.main_window),
                                            formatear_fecha(f["fecha_fin"], self.main_window)) if x)
            valores = [f["titulo"], f["materia"] or "—", f["curso"] or "—", fechas or "—",
                       f"{f['sesiones_realizadas']}/{f['total_sesiones']} sesiones", f["estado"]]
            for c, v in enumerate(valores):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, f["id"])
                if c == 5:
                    it.setForeground(Qt.GlobalColor.white)
                    it.setBackground(QColor(COLORES_ESTADO.get(f["estado"], "#64748B")))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, c, it)

    def _id(self):
        fila = self.tabla.currentRow()
        if fila < 0 or self.tabla.item(fila, 0) is None:
            mostrar_mensaje("info", "Secuencias Didácticas", "Selecciona una secuencia de la tabla.", self)
            return None
        return self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)

    def _nueva(self):
        if EditorSecuenciaST(self.main_window, None, self).exec():
            self.refrescar()

    def _editar(self):
        sid = self._id()
        if sid and EditorSecuenciaST(self.main_window, sid, self).exec():
            self.refrescar()

    def _duplicar(self):
        sid = self._id()
        if sid:
            logica.duplicar_secuencia(sid, main_window=self.main_window)
            self.refrescar()

    def _eliminar(self):
        sid = self._id()
        if sid and QMessageBox.question(
                self, "Eliminar secuencia", "¿Eliminar esta secuencia y sus sesiones? No se borran tus tareas."
        ) == QMessageBox.StandardButton.Yes:
            logica.eliminar_secuencia(sid, self.main_window)
            self.refrescar()

    def _exportar(self):
        sid = self._id()
        if not sid:
            return
        sec = logica.obtener_secuencia(sid, self.main_window)
        base = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in sec["titulo"]).strip() or "secuencia"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar secuencia",
                                              os.path.join(os.path.expanduser("~"), base + ".docx"),
                                              "Documento de Word (*.docx)")
        if not ruta:
            return
        if not ruta.lower().endswith(".docx"):
            ruta += ".docx"
        try:
            logica.exportar_docx(sid, ruta, self.main_window)
        except Exception as e:
            mostrar_mensaje("error", "Exportar", f"No se pudo guardar el archivo:\n{e}", self)
            return
        mostrar_mensaje("exito", "Exportar", f"Secuencia exportada en:\n{ruta}", self)
