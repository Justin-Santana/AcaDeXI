"""Secuencias Didácticas de AcaDeXI: planificación de unidades de aprendizaje
(formato MINERD) ligada a las competencias, indicadores y tareas de la app.

La lógica de datos y la exportación a Word viven en src/nucleo/secuencias.py;
aquí solo está la interfaz (lista + editor)."""
import os

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QTabWidget,
    QTextEdit, QListWidget, QListWidgetItem, QDateEdit, QSpinBox, QCheckBox, QFrame,
    QFileDialog, QFormLayout, QAbstractItemView, QProgressBar, QInputDialog, QMessageBox)

from src.nucleo import secuencias as logica
from src.nucleo.bd import get_connection, registrar_auditoria
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.nucleo.permisos import puede_editar, es_profesor_restringido, obtener_profesor_id, obtener_materias_permitidas
from src.nucleo.formato_hora import formatear_fecha
from src.interfaz.configuracion import anio_academico_actual
from src.modulos.calificaciones import competencias_de_materia_grado, grados_de_materia

_FECHA_VACIA = QDate(2000, 1, 1)
COLORES_ESTADO = {"Borrador": "#64748B", "En curso": "#F59E0B", "Completada": "#10B981", "Archivada": "#94A3B8"}


def _fecha_a_iso(qdate):
    return None if qdate == _FECHA_VACIA else qdate.toString("yyyy-MM-dd")


def _iso_a_fecha(iso):
    d = QDate.fromString(str(iso or "")[:10], "yyyy-MM-dd")
    return d if d.isValid() else _FECHA_VACIA


def _selector_fecha():
    """QDateEdit que admite "sin fecha": la fecha mínima se muestra como '—'."""
    w = QDateEdit()
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd/MM/yyyy")
    w.setMinimumDate(_FECHA_VACIA)
    w.setSpecialValueText("—")
    w.setDate(_FECHA_VACIA)
    return w


def _materias_disponibles(main_window):
    permitidas = obtener_materias_permitidas(main_window)
    conn = get_connection()
    try:
        filas = conn.execute("SELECT id, nombre FROM materias WHERE COALESCE(estado,'Activa')='Activa' "
                             "ORDER BY nombre").fetchall()
    finally:
        conn.close()
    return [(f["id"], f["nombre"]) for f in filas if permitidas is None or f["id"] in permitidas]


class EditorSecuencia(QDialog):
    """Crea o edita una secuencia: General · Pedagógico · Sesiones · Vínculos."""

    def __init__(self, main_window, secuencia_id=None, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.secuencia_id = secuencia_id
        self.setWindowTitle("Editar secuencia didáctica" if secuencia_id else "Nueva secuencia didáctica")
        self.resize(1080, 700)
        self._cargando = True
        self._build_ui()
        self._cargar_catalogos()
        if secuencia_id:
            self._cargar(logica.obtener_secuencia(secuencia_id))
        else:
            self._tabla_sesiones_poblar(logica.sesiones_base(3))
        self._cargando = False
        self._al_cambiar_materia()

    # ---------------- construcción ----------------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_general(), "General")
        self.tabs.addTab(self._tab_pedagogico(), "Pedagógico")
        self.tabs.addTab(self._tab_sesiones(), "Sesiones")
        self.tabs.addTab(self._tab_vinculos(), "Competencias y tareas")
        botones = QDialogButtonBox()
        self.btn_guardar = botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def _tab_general(self):
        w = QWidget(); f = QFormLayout(w)
        self.in_titulo = QLineEdit(); self.in_titulo.setPlaceholderText("Ej. Los textos narrativos")
        self.cb_materia = QComboBox(); self.cb_grado = QComboBox(); self.cb_seccion = QComboBox()
        self.cb_periodo = QComboBox()
        self.in_anio = QLineEdit(anio_academico_actual())
        self.cb_estado = QComboBox(); self.cb_estado.addItems(logica.ESTADOS_SECUENCIA)
        self.f_inicio = _selector_fecha(); self.f_fin = _selector_fecha()
        self.cb_materia.currentIndexChanged.connect(self._al_cambiar_materia)
        self.cb_grado.currentIndexChanged.connect(self._al_cambiar_grado)
        for etiqueta, campo in (("Título de la unidad *", self.in_titulo), ("Asignatura", self.cb_materia),
                                ("Grado", self.cb_grado), ("Sección", self.cb_seccion),
                                ("Período", self.cb_periodo), ("Año escolar", self.in_anio),
                                ("Estado", self.cb_estado), ("Fecha de inicio", self.f_inicio),
                                ("Fecha de fin", self.f_fin)):
            f.addRow(etiqueta, campo)
        return w

    def _tab_pedagogico(self):
        w = QWidget(); f = QFormLayout(w)
        self.in_eje = QLineEdit(); self.in_eje.setPlaceholderText("Eje transversal / descriptores")
        self.tx_situacion = QTextEdit()
        self.tx_situacion.setPlaceholderText("Situación de aprendizaje: contexto real y reto que enfrentan los estudiantes.")
        self.lista_fundamentales = QListWidget()
        for nombre in logica.COMPETENCIAS_FUNDAMENTALES:
            it = QListWidgetItem(nombre); it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked); self.lista_fundamentales.addItem(it)
        self.lista_fundamentales.setMaximumHeight(140)
        self.tx_conceptos = QTextEdit(); self.tx_procedimientos = QTextEdit(); self.tx_actitudes = QTextEdit()
        self.tx_estrategia = QTextEdit()
        self.tx_estrategia.setPlaceholderText("Estrategia de enseñanza y de aprendizaje (p. ej. aprendizaje basado en proyectos).")
        for etiqueta, campo in (("Eje transversal", self.in_eje), ("Situación de aprendizaje", self.tx_situacion),
                                ("Competencias fundamentales", self.lista_fundamentales),
                                ("Contenidos: conceptos", self.tx_conceptos),
                                ("Contenidos: procedimientos", self.tx_procedimientos),
                                ("Contenidos: actitudes y valores", self.tx_actitudes),
                                ("Estrategia", self.tx_estrategia)):
            f.addRow(etiqueta, campo)
        return w

    def _tab_sesiones(self):
        w = QWidget(); lay = QVBoxLayout(w)
        barra = QHBoxLayout()
        for texto, accion in (("Agregar sesión", self._agregar_sesion), ("Quitar sesión", self._quitar_sesion),
                              ("Subir", lambda: self._mover_sesion(-1)), ("Bajar", lambda: self._mover_sesion(1)),
                              ("Autocompletar fechas…", self._autocompletar_fechas)):
            b = QPushButton(texto); b.clicked.connect(accion); barra.addWidget(b)
        barra.addStretch(1)
        lay.addLayout(barra)
        self.col_sesion = ["Fecha", "Momento", "Actividades de aprendizaje", "Evidencias", "Instrumento de evaluación",
                           "Metacognición", "Recursos", "Min", "Realizada"]
        self.tabla = QTableWidget(0, len(self.col_sesion))
        self.tabla.setHorizontalHeaderLabels(self.col_sesion)
        self.tabla.setWordWrap(True)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setDefaultSectionSize(54)
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, ancho in enumerate((110, 110, 260, 160, 170, 160, 140, 60, 80)):
            self.tabla.setColumnWidth(i, ancho)
        lay.addWidget(self.tabla, 1)
        return w

    def _tab_vinculos(self):
        w = QWidget(); lay = QHBoxLayout(w)
        cols = []
        for titulo in ("Competencias específicas", "Indicadores de logro", "Tareas del Banco de Tareas"):
            caja = QVBoxLayout(); caja.addWidget(QLabel(titulo))
            lista = QListWidget(); lista.setWordWrap(True); caja.addWidget(lista, 1)
            lay.addLayout(caja, 1); cols.append(lista)
        self.lista_ce, self.lista_il, self.lista_tareas = cols
        self.lista_ce.itemChanged.connect(self._al_cambiar_competencias)
        return w

    # ---------------- catálogos y dependencias ----------------
    def _cargar_catalogos(self):
        self.cb_materia.blockSignals(True)
        self.cb_materia.addItem("— Sin asignatura —", None)
        for mid, nombre in _materias_disponibles(self.main_window):
            self.cb_materia.addItem(nombre, mid)
        self.cb_materia.blockSignals(False)
        conn = get_connection()
        try:
            self.cb_periodo.addItem("— Sin período —", None)
            for f in conn.execute("SELECT id, nombre, anio_academico FROM periodos ORDER BY anio_academico DESC, orden"):
                self.cb_periodo.addItem(f"{f['nombre']} ({f['anio_academico']})" if f["anio_academico"] else f["nombre"], f["id"])
        finally:
            conn.close()

    def _poblar_grados(self, previo):
        mid = self.cb_materia.currentData()
        self.cb_grado.blockSignals(True)
        self.cb_grado.clear(); self.cb_grado.addItem("— Sin grado —", None)
        grados = grados_de_materia(mid) if mid else []
        if not grados:  # materia sin horarios aún: se ofrecen todos los grados
            conn = get_connection()
            try:
                grados = [dict(f) for f in conn.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")]
            finally:
                conn.close()
        for g in grados:
            self.cb_grado.addItem(g["nombre"], g["id"])
        self.cb_grado.setCurrentIndex(max(self.cb_grado.findData(previo), 0))
        self.cb_grado.blockSignals(False)

    def _poblar_secciones(self, previo):
        gid = self.cb_grado.currentData()
        self.cb_seccion.blockSignals(True)
        self.cb_seccion.clear(); self.cb_seccion.addItem("— Todas —", None)
        if gid:
            conn = get_connection()
            try:
                for f in conn.execute("SELECT id, nombre FROM secciones WHERE grado_id=? ORDER BY nombre", (gid,)):
                    self.cb_seccion.addItem(f["nombre"], f["id"])
            finally:
                conn.close()
        self.cb_seccion.setCurrentIndex(max(self.cb_seccion.findData(previo), 0))
        self.cb_seccion.blockSignals(False)

    def _al_cambiar_materia(self):
        if self._cargando:
            return
        self._poblar_grados(self.cb_grado.currentData())
        self._al_cambiar_grado()

    def _al_cambiar_grado(self):
        if self._cargando:
            return
        self._poblar_secciones(self.cb_seccion.currentData())
        self._recargar_ce_y_tareas()

    def _marcados(self, lista):
        return [lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lista.count())
                if lista.item(i).checkState() == Qt.CheckState.Checked]

    def _poblar_checklist(self, lista, filas, texto, marcados):
        lista.blockSignals(True)
        lista.clear()
        for fila in filas:
            it = QListWidgetItem(texto(fila))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setData(Qt.ItemDataRole.UserRole, fila["id"])
            it.setCheckState(Qt.CheckState.Checked if fila["id"] in marcados else Qt.CheckState.Unchecked)
            lista.addItem(it)
        lista.blockSignals(False)

    def _recargar_ce_y_tareas(self):
        mid, gid = self.cb_materia.currentData(), self.cb_grado.currentData()
        previos_ce = set(self._marcados(self.lista_ce)) | set(getattr(self, "_ce_pendientes", ()))
        previos_t = set(self._marcados(self.lista_tareas)) | set(getattr(self, "_tareas_pendientes", ()))
        self._ce_pendientes = self._tareas_pendientes = ()
        self._poblar_checklist(self.lista_ce, competencias_de_materia_grado(mid, gid),
                               lambda f: f"{f['codigo']}. {f['descripcion']}", previos_ce)
        self._poblar_checklist(self.lista_tareas, logica.tareas_de_materia(mid, gid),
                               lambda f: f"{f['titulo']} ({f['categoria'] or 'Tarea'})", previos_t)
        self._al_cambiar_competencias()

    def _al_cambiar_competencias(self, *_):
        previos = set(self._marcados(self.lista_il)) | set(getattr(self, "_il_pendientes", ()))
        self._il_pendientes = ()
        self._poblar_checklist(
            self.lista_il, logica.indicadores_de_competencias(self._marcados(self.lista_ce)),
            lambda f: f"{f['codigo_competencia']} · {f['codigo']}: {f['descripcion']}", previos)

    # ---------------- sesiones ----------------
    def _tabla_sesiones_poblar(self, sesiones):
        self.tabla.setRowCount(0)
        for s in sesiones:
            self._agregar_fila(s)

    def _agregar_fila(self, s=None, posicion=None):
        s = s or logica.sesiones_base(2)[1]
        fila = self.tabla.rowCount() if posicion is None else posicion
        self.tabla.insertRow(fila)
        f = _selector_fecha(); f.setDate(_iso_a_fecha(s.get("fecha")))
        self.tabla.setCellWidget(fila, 0, f)
        m = QComboBox(); m.addItems(logica.MOMENTOS)
        m.setCurrentText(s.get("momento") if s.get("momento") in logica.MOMENTOS else "Desarrollo")
        self.tabla.setCellWidget(fila, 1, m)
        for col, clave in ((2, "actividad"), (3, "evidencia"), (5, "metacognicion"), (6, "recursos")):
            self.tabla.setItem(fila, col, QTableWidgetItem(s.get(clave) or ""))
        inst = QComboBox(); inst.setEditable(True)
        inst.addItems([""] + logica.INSTRUMENTOS_EVALUACION)
        inst.setCurrentText(s.get("instrumento") or "")
        self.tabla.setCellWidget(fila, 4, inst)
        mins = QSpinBox(); mins.setRange(0, 600); mins.setValue(int(s.get("duracion_min") or 0))
        self.tabla.setCellWidget(fila, 7, mins)
        chk = QCheckBox(); chk.setChecked(bool(s.get("realizada")))
        cont = QWidget(); hl = QHBoxLayout(cont); hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter); hl.addWidget(chk)
        self.tabla.setCellWidget(fila, 8, cont)

    def _sesiones_desde_tabla(self):
        out = []
        for r in range(self.tabla.rowCount()):
            txt = lambda c: (self.tabla.item(r, c).text().strip() if self.tabla.item(r, c) else "")
            out.append({
                "fecha": _fecha_a_iso(self.tabla.cellWidget(r, 0).date()),
                "momento": self.tabla.cellWidget(r, 1).currentText(),
                "actividad": txt(2), "evidencia": txt(3),
                "instrumento": self.tabla.cellWidget(r, 4).currentText().strip(),
                "metacognicion": txt(5), "recursos": txt(6),
                "duracion_min": self.tabla.cellWidget(r, 7).value(),
                "realizada": self.tabla.cellWidget(r, 8).findChild(QCheckBox).isChecked(),
            })
        return out

    def _agregar_sesion(self):
        actual = self.tabla.currentRow()
        self._agregar_fila(posicion=actual + 1 if actual >= 0 else None)

    def _quitar_sesion(self):
        r = self.tabla.currentRow()
        if r >= 0:
            self.tabla.removeRow(r)

    def _mover_sesion(self, delta):
        r = self.tabla.currentRow()
        nuevo = r + delta
        if r < 0 or not 0 <= nuevo < self.tabla.rowCount():
            return
        sesiones = self._sesiones_desde_tabla()
        sesiones[r], sesiones[nuevo] = sesiones[nuevo], sesiones[r]
        self._tabla_sesiones_poblar(sesiones)
        self.tabla.selectRow(nuevo)

    def _autocompletar_fechas(self):
        inicio = _fecha_a_iso(self.f_inicio.date())
        if not inicio:
            mostrar_mensaje("advertencia", "Fechas", "Primero indica la fecha de inicio en la pestaña General.", self)
            return
        texto, ok = QInputDialog.getText(
            self, "Días de clase", "Días de la semana con clase (1=lunes … 5=viernes), separados por coma:",
            text="1,2,3,4,5")
        if not ok:
            return
        try:
            dias = [int(x) - 1 for x in texto.replace(" ", "").split(",") if x]
            if not dias or any(not 0 <= d <= 6 for d in dias):
                raise ValueError
            sesiones = self._sesiones_desde_tabla()
            fechas = logica.distribuir_fechas(inicio, len(sesiones), dias)
        except ValueError:
            mostrar_mensaje("advertencia", "Fechas", "Escribe números del 1 al 7 separados por coma.", self)
            return
        for s, fch in zip(sesiones, fechas):
            s["fecha"] = fch
        self._tabla_sesiones_poblar(sesiones)
        if fechas:
            self.f_fin.setDate(_iso_a_fecha(fechas[-1]))

    # ---------------- cargar / guardar ----------------
    def _cargar(self, sec):
        if sec is None:
            return
        self.in_titulo.setText(sec["titulo"])
        self.cb_materia.setCurrentIndex(max(self.cb_materia.findData(sec["materia_id"]), 0))
        self._cargar_grado_y_vinculos(sec)
        self.cb_periodo.setCurrentIndex(max(self.cb_periodo.findData(sec["periodo_id"]), 0))
        self.in_anio.setText(sec.get("anio_academico") or "")
        self.cb_estado.setCurrentText(sec["estado"])
        self.f_inicio.setDate(_iso_a_fecha(sec["fecha_inicio"])); self.f_fin.setDate(_iso_a_fecha(sec["fecha_fin"]))
        self.in_eje.setText(sec.get("eje_transversal") or "")
        self.tx_situacion.setPlainText(sec.get("situacion_aprendizaje") or "")
        self.tx_conceptos.setPlainText(sec.get("contenido_conceptos") or "")
        self.tx_procedimientos.setPlainText(sec.get("contenido_procedimientos") or "")
        self.tx_actitudes.setPlainText(sec.get("contenido_actitudes") or "")
        self.tx_estrategia.setPlainText(sec.get("estrategia") or "")
        elegidas = set(sec["competencias_fundamentales_lista"])
        for i in range(self.lista_fundamentales.count()):
            it = self.lista_fundamentales.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.text() in elegidas else Qt.CheckState.Unchecked)
        self._tabla_sesiones_poblar(sec["sesiones"] or logica.sesiones_base(3))

    def _cargar_grado_y_vinculos(self, sec):
        """Al editar: fija grado/sección guardados y marca los vínculos existentes.
        Se hace en este orden (grado -> sección -> competencias -> indicadores) porque
        las competencias dependen de materia+grado; con grado vacío no habría nada que marcar."""
        self._poblar_grados(sec["grado_id"])
        self._poblar_secciones(sec["seccion_id"])
        self._ce_pendientes = {x["id"] for x in sec["competencias"]}
        self._il_pendientes = {x["id"] for x in sec["indicadores"]}
        self._tareas_pendientes = {x["id"] for x in sec["tareas"]}
        self._recargar_ce_y_tareas()

    def _datos(self):
        return {
            "titulo": self.in_titulo.text(), "materia_id": self.cb_materia.currentData(),
            "grado_id": self.cb_grado.currentData(), "seccion_id": self.cb_seccion.currentData(),
            "profesor_id": self._profesor_id(), "periodo_id": self.cb_periodo.currentData(),
            "anio_academico": self.in_anio.text().strip(), "eje_transversal": self.in_eje.text().strip(),
            "situacion_aprendizaje": self.tx_situacion.toPlainText().strip(),
            "competencias_fundamentales": logica.unir_competencias_fundamentales(
                [self.lista_fundamentales.item(i).text() for i in range(self.lista_fundamentales.count())
                 if self.lista_fundamentales.item(i).checkState() == Qt.CheckState.Checked]),
            "contenido_conceptos": self.tx_conceptos.toPlainText().strip(),
            "contenido_procedimientos": self.tx_procedimientos.toPlainText().strip(),
            "contenido_actitudes": self.tx_actitudes.toPlainText().strip(),
            "estrategia": self.tx_estrategia.toPlainText().strip(),
            "estado": self.cb_estado.currentText(),
            "fecha_inicio": _fecha_a_iso(self.f_inicio.date()), "fecha_fin": _fecha_a_iso(self.f_fin.date()),
        }

    def _profesor_id(self):
        pid = obtener_profesor_id(self.main_window)
        if pid is not None:
            return pid
        mid = self.cb_materia.currentData()
        if mid:
            conn = get_connection()
            try:
                f = conn.execute("SELECT profesor_id FROM materias WHERE id=?", (mid,)).fetchone()
            finally:
                conn.close()
            return f["profesor_id"] if f else None
        return None

    def _guardar(self):
        try:
            self.secuencia_id = logica.guardar_secuencia(
                self._datos(), self._marcados(self.lista_ce), self._marcados(self.lista_il),
                self._marcados(self.lista_tareas), self._sesiones_desde_tabla(), self.secuencia_id)
        except ValueError as e:
            mostrar_mensaje("advertencia", "Secuencia didáctica", str(e), self)
            return
        registrar_auditoria("Secuencias Didácticas", "Guardar secuencia",
                            getattr(self.main_window, "usuario_actual", None), self.in_titulo.text().strip())
        avisos = logica.validar_secuencia(logica.obtener_secuencia(self.secuencia_id))
        if avisos:
            mostrar_mensaje("info", "Secuencia guardada",
                            "Se guardó, pero conviene completar:\n\n• " + "\n• ".join(avisos), self)
        self.accept()


class ModuloSecuenciasDidacticas(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._build_ui()
        self.actualizar_tema()
        self.refrescar()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 25, 30, 25); lay.setSpacing(12)
        self.frame_cabecera = QFrame(); self.frame_cabecera.setObjectName("TarjetaCabecera")
        cab = QHBoxLayout(self.frame_cabecera); cab.setContentsMargins(22, 18, 22, 18); cab.setSpacing(14)
        self.lbl_icono = QLabel(""); self.lbl_icono.setObjectName("IconoCabeceraModulo")
        self.lbl_icono.setFixedSize(46, 46); self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono, "Secuencias Didácticas")
        cab.addWidget(self.lbl_icono)
        bloque = QVBoxLayout(); bloque.setSpacing(2)
        t = QLabel("Secuencias Didácticas"); t.setObjectName("TituloCabeceraModulo")
        s = QLabel("Planifica tus unidades de aprendizaje con el esquema del MINERD: situación de aprendizaje, "
                   "competencias, indicadores de logro y sesiones con evidencias e instrumentos."); s.setWordWrap(True)
        s.setObjectName("SubtituloCabeceraModulo")
        bloque.addWidget(t); bloque.addWidget(s); cab.addLayout(bloque, 1)
        self.chip_contador = QLabel("0 secuencias"); self.chip_contador.setObjectName("ChipContador")
        cab.addWidget(self.chip_contador)
        lay.addWidget(self.frame_cabecera)

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

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(["Título", "Asignatura", "Grado / Sección", "Período", "Fechas", "Avance", "Estado"])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setMinimumHeight(260)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 7):
            self.tabla.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.doubleClicked.connect(lambda *_: self._editar())
        lay.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        self.btn_nueva = QPushButton("Nueva secuencia"); self.btn_editar = QPushButton("Editar")
        self.btn_duplicar = QPushButton("Duplicar"); self.btn_eliminar = QPushButton("Eliminar")
        self.btn_word = QPushButton("Exportar a Word")
        self.btn_nueva.clicked.connect(self._nueva); self.btn_editar.clicked.connect(self._editar)
        self.btn_duplicar.clicked.connect(self._duplicar); self.btn_eliminar.clicked.connect(self._eliminar)
        self.btn_word.clicked.connect(self._exportar)
        for b in (self.btn_nueva, self.btn_editar, self.btn_duplicar, self.btn_eliminar):
            botones.addWidget(b)
        botones.addStretch(1); botones.addWidget(self.btn_word)
        lay.addLayout(botones)
        if not puede_editar(self.main_window):
            for b in (self.btn_nueva, self.btn_editar, self.btn_duplicar, self.btn_eliminar):
                b.setEnabled(False)

    def actualizar_tema(self):
        mw = self.main_window
        paletas = getattr(mw, "theme_palettes", None)
        if not paletas:
            return
        paleta = paletas.get(getattr(mw, "tema_actual", "")) or next(iter(paletas.values()))
        idx = 1 if getattr(mw, "modo_oscuro", True) else 0
        acento = paleta["btn_op_bg"][idx]
        hover = paleta["btn_op_hover"][idx] if "btn_op_hover" in paleta else acento
        self.frame_cabecera.setStyleSheet(f"""
            QFrame#TarjetaCabecera {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {acento},stop:1 {hover});
                border-radius: 18px; }}
            QLabel#IconoCabeceraModulo {{ background-color: rgba(255,255,255,40); border-radius: 23px;
                font-size: 22px; color: white; }}
            QLabel#TituloCabeceraModulo {{ font-size: 22px; font-weight: 800; color: white; background: transparent; }}
            QLabel#SubtituloCabeceraModulo {{ font-size: 12px; color: rgba(255,255,255,210); background: transparent; }}
            QLabel#ChipContador {{ background-color: rgba(255,255,255,40); color: white; border-radius: 12px;
                padding: 4px 12px; font-weight: 700; }}""")

    # ---------------- datos ----------------
    def _filtros_acceso(self):
        if es_profesor_restringido(self.main_window):
            return obtener_profesor_id(self.main_window), obtener_materias_permitidas(self.main_window)
        return None, None

    def refrescar(self, *_):
        prof, permitidas = self._filtros_acceso()
        previa = self.cb_materia.currentData()
        self.cb_materia.blockSignals(True)
        self.cb_materia.clear(); self.cb_materia.addItem("Todas las asignaturas", None)
        for mid, nombre in _materias_disponibles(self.main_window):
            self.cb_materia.addItem(nombre, mid)
        self.cb_materia.setCurrentIndex(max(self.cb_materia.findData(previa), 0))
        self.cb_materia.blockSignals(False)
        filas = logica.listar_secuencias(prof, permitidas, self.cb_materia.currentData(), None,
                                         self.cb_estado.currentData(), self.in_buscar.text())
        self.tabla.setRowCount(len(filas))
        for r, f in enumerate(filas):
            fechas = " – ".join(x for x in (formatear_fecha(f["fecha_inicio"], self.main_window),
                                            formatear_fecha(f["fecha_fin"], self.main_window)) if x)
            valores = [f["titulo"], f["materia"] or "—",
                       " ".join(x for x in (f["grado"], f["seccion"]) if x) or "—", f["periodo"] or "—",
                       fechas or "—", f"{f['sesiones_realizadas']}/{f['total_sesiones']} sesiones", f["estado"]]
            for c, v in enumerate(valores):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, f["id"])
                if c == 6:
                    it.setForeground(Qt.GlobalColor.white)
                    from PySide6.QtGui import QColor
                    it.setBackground(QColor(COLORES_ESTADO.get(f["estado"], "#64748B")))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, c, it)
        self.chip_contador.setText(f"{len(filas)} secuencia{'s' if len(filas) != 1 else ''}")

    def _id_seleccionado(self):
        fila = self.tabla.currentRow()
        if fila < 0 or self.tabla.item(fila, 0) is None:
            mostrar_mensaje("info", "Secuencias Didácticas", "Selecciona una secuencia de la tabla.", self)
            return None
        return self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)

    # ---------------- acciones ----------------
    def _nueva(self):
        if EditorSecuencia(self.main_window, None, self).exec():
            self.refrescar()

    def _editar(self):
        sid = self._id_seleccionado()
        if sid and puede_editar(self.main_window) and EditorSecuencia(self.main_window, sid, self).exec():
            self.refrescar()

    def _duplicar(self):
        sid = self._id_seleccionado()
        if sid:
            logica.duplicar_secuencia(sid)
            self.refrescar()

    def _eliminar(self):
        sid = self._id_seleccionado()
        if not sid:
            return
        if QMessageBox.question(self, "Eliminar secuencia", "¿Eliminar esta secuencia y sus sesiones? "
                                "No se borran las tareas ni las competencias vinculadas.") != QMessageBox.StandardButton.Yes:
            return
        logica.eliminar_secuencia(sid)
        registrar_auditoria("Secuencias Didácticas", "Eliminar secuencia",
                            getattr(self.main_window, "usuario_actual", None), str(sid))
        self.refrescar()

    def _exportar(self):
        sid = self._id_seleccionado()
        if not sid:
            return
        sec = logica.obtener_secuencia(sid)
        sugerido = "".join(ch if ch.isalnum() or ch in " _-" else "_" for ch in sec["titulo"]).strip() or "secuencia"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar secuencia", os.path.join(os.path.expanduser("~"), sugerido + ".docx"),
                                              "Documento de Word (*.docx)")
        if not ruta:
            return
        if not ruta.lower().endswith(".docx"):
            ruta += ".docx"
        try:
            logica.exportar_docx(sid, ruta)
        except Exception as e:  # permisos, archivo abierto en Word, etc.
            mostrar_mensaje("error", "Exportar", f"No se pudo guardar el archivo:\n{e}", self)
            return
        mostrar_mensaje("exito", "Exportar", f"Secuencia exportada en:\n{ruta}", self)
