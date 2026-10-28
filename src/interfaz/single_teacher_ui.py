#Capa de UI propia de AcaDeXI Single Teacher.
#
#Conectada a bd_single_teacher.py (Pieza 3 del prompt de arquitectura de las
#4 ediciones), NO a bd.py. A propósito, estos módulos son más simples que
#sus equivalentes institucionales (estudiantes.py, calificaciones.py...):
#no hay RBAC por fila, no hay overrides, no hay múltiples profesores ni
#matrícula institucional que generar -un solo docente, dueño directo de
#todos sus datos. Reutilizan el mismo lenguaje visual de la app (mismos
#objectName de botones/tarjetas que ya estiliza la hoja de estilos global)
#pero sin la complejidad adicional que esa ausencia de jerarquía hace
#innecesaria.
#
#Cada clase se registra en main.py (_fabricas_modulos, rama "single_teacher")
#y aparece en el menú lateral con el mismo nombre con el que se navega desde
#el tour interactivo (ver tutoriales.PASOS_SINGLE_TEACHER): los textos
#visibles de botones y el nombre de cada módulo están escritos para calzar
#exactamente con esos pasos -si cambias un texto aquí, actualiza también el
#paso correspondiente en tutoriales.py.
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QDateEdit, QDoubleSpinBox,
    QTextEdit, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QFrame, QFileDialog)
from PySide6.QtCore import Qt, QDate, QSize

from src.nucleo import bd_single_teacher as db
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, centrar_y_al_frente
from src.nucleo.iconos_emoji import icono_emoji
from src.nucleo.formato_hora import aplicar_formato_widget_fecha, formatear_fecha
from src.interfaz.paginacion import aplicar_estructura_tabla, ajustar_anchos_columnas
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.filtro_vacio import EstadoVacioFiltro


def _combo_agregar_filas(combo, filas, campo_texto="nombre"):

    combo.clear()
    combo.addItem("Selecciona…", None)
    for fila in filas:
        combo.addItem(fila[campo_texto], fila["id"])


def _tabla_solo_lectura(tabla):

    tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    tabla.verticalHeader().setVisible(False)
    tabla.horizontalHeader().setStretchLastSection(True)


#DASHBOARD
class ModuloDashboardST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo= QLabel("📊 Tu vistazo rápido")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        self.lbl_resumen= QLabel()
        self.lbl_resumen.setWordWrap(True)
        layout.addWidget(self.lbl_resumen)
        layout.addStretch()
        self._cargar()

    def _cargar(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT COUNT(*) as n FROM estudiantes")
        n_estudiantes= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM secciones")
        n_secciones= c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM materias")
        n_materias= c.fetchone()["n"]
        hoy= datetime.now().strftime("%Y-%m-%d")
        c.execute("SELECT COUNT(*) as n FROM asistencia WHERE fecha=? AND estado='Presente'", (hoy,))
        presentes_hoy= c.fetchone()["n"]
        conn.close()
        self.lbl_resumen.setText(
            f"👤 Estudiantes: {n_estudiantes}\n"
            f"🏫 Cursos: {n_secciones}\n"
            f"📘 Materias: {n_materias}\n"
            f"✅ Presentes registrados hoy: {presentes_hoy}\n\n"
            "Eres dueño directo de estos datos: no hay ninguna Dirección/Coordinación por encima "
            "revisando ni aprobando lo que registras aquí.")


#CURSOS (diálogo reutilizado desde Estudiantes/Materias/Horario/Tareas)
class DialogoGestionarCursos(QDialog):

    def __init__(self, main_window, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.setWindowTitle("Gestionar mis cursos")
        aplicar_icono_ventana(self)
        self.setMinimumWidth(420)
        layout= QVBoxLayout(self)

        form= QHBoxLayout()
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre)
        self.in_nombre.setPlaceholderText("Nombre del curso (ej. 8vo A - Matemáticas 2026)")
        form.addWidget(self.in_nombre, 1)
        self.combo_nivel= QComboBox()
        self.combo_nivel.addItems(["Primaria", "Secundaria", "Preparatoria", "Universidad"])
        form.addWidget(self.combo_nivel)
        btn_agregar= QPushButton("Agregar")
        btn_agregar.setIcon(icono_emoji("➕"))
        btn_agregar.setIconSize(QSize(16, 16))
        btn_agregar.setObjectName("BtnAccionAgregar")
        btn_agregar.clicked.connect(self._agregar)
        form.addWidget(btn_agregar)
        layout.addLayout(form)

        self.tabla= QTableWidget(0, 2)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Curso", "Nivel"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        btn_eliminar= QPushButton("Eliminar curso seleccionado")

        btn_eliminar.setIcon(icono_emoji("🗑️"))

        btn_eliminar.setIconSize(QSize(16, 16))
        btn_eliminar.clicked.connect(self._eliminar)
        layout.addWidget(btn_eliminar)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.accept)
        botones.accepted.connect(self.accept)
        layout.addWidget(botones)

        self._cargar_tabla()
        centrar_y_al_frente(self, parent)

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT id, nombre, nivel_educativo FROM secciones ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            item_nombre= QTableWidgetItem(f["nombre"])
            item_nombre.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.tabla.setItem(i, 0, item_nombre)
            self.tabla.setItem(i, 1, QTableWidgetItem(f["nivel_educativo"] or ""))

    def _agregar(self):

        nombre= self.in_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Falta el nombre", "Escribe un nombre para el curso.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("INSERT INTO secciones (nombre, nivel_educativo) VALUES (?,?)",
                  (nombre, self.combo_nivel.currentText()))
        conn.commit()
        conn.close()
        self.in_nombre.clear()
        self._cargar_tabla()

    def _eliminar(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un curso de la tabla.", self)
            return
        id_seccion= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("UPDATE estudiantes SET seccion_id=NULL WHERE seccion_id=?", (id_seccion,))
        c.execute("DELETE FROM secciones WHERE id=?", (id_seccion,))
        conn.commit()
        conn.close()
        self._cargar_tabla()


def _recargar_combo_cursos(main_window, combo):

    conn= db.obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("SELECT id, nombre FROM secciones ORDER BY nombre")
    _combo_agregar_filas(combo, c.fetchall())
    conn.close()


#ESTUDIANTES
class ModuloEstudiantesST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        self._id_edicion= None
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        fila_titulo= QHBoxLayout()
        titulo= QLabel("🎓 Estudiantes")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        fila_titulo.addWidget(titulo)
        fila_titulo.addStretch()
        btn_cursos= QPushButton("Gestionar mis cursos")
        btn_cursos.setIcon(icono_emoji("🏫"))
        btn_cursos.setIconSize(QSize(16, 16))
        btn_cursos.clicked.connect(self._abrir_cursos)
        fila_titulo.addWidget(btn_cursos)
        layout.addLayout(fila_titulo)

        form= QGridLayout()
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre)
        self.in_apellidos= QLineEdit()
        limitar_campo_texto(self.in_apellidos)
        self.in_fecha_nacimiento= QDateEdit()
        self.in_fecha_nacimiento.setCalendarPopup(True)
        self.in_fecha_nacimiento.setDate(QDate.currentDate().addYears(-10))
        aplicar_formato_widget_fecha(self.in_fecha_nacimiento, main_window)
        self.combo_sexo= QComboBox()
        self.combo_sexo.addItems(["Masculino", "Femenino"])
        self.combo_curso= QComboBox()
        self.in_tutor= QLineEdit()
        limitar_campo_texto(self.in_tutor)
        self.in_telefono= QLineEdit()
        limitar_campo_texto(self.in_telefono)
        self.in_correo= QLineEdit()
        limitar_campo_texto(self.in_correo)
        form.addWidget(QLabel("Nombre:"), 0, 0)
        form.addWidget(self.in_nombre, 0, 1)
        form.addWidget(QLabel("Apellidos:"), 0, 2)
        form.addWidget(self.in_apellidos, 0, 3)
        form.addWidget(QLabel("Fecha de nacimiento:"), 1, 0)
        form.addWidget(self.in_fecha_nacimiento, 1, 1)
        form.addWidget(QLabel("Sexo:"), 1, 2)
        form.addWidget(self.combo_sexo, 1, 3)
        form.addWidget(QLabel("Curso:"), 2, 0)
        form.addWidget(self.combo_curso, 2, 1)
        form.addWidget(QLabel("Tutor:"), 2, 2)
        form.addWidget(self.in_tutor, 2, 3)
        form.addWidget(QLabel("Teléfono:"), 3, 0)
        form.addWidget(self.in_telefono, 3, 1)
        form.addWidget(QLabel("Correo:"), 3, 2)
        form.addWidget(self.in_correo, 3, 3)
        layout.addLayout(form)

        fila_botones= QHBoxLayout()
        self.btn_guardar= QPushButton("Guardar")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.btn_guardar)
        btn_limpiar= QPushButton("Limpiar")
        btn_limpiar.setIcon(icono_emoji("🧹"))
        btn_limpiar.setIconSize(QSize(16, 16))
        btn_limpiar.clicked.connect(self._limpiar)
        fila_botones.addWidget(btn_limpiar)
        fila_botones.addStretch()
        layout.addLayout(fila_botones)

        self.tabla= QTableWidget(0, 4)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Apellidos", "Curso", "Tutor"])
        _tabla_solo_lectura(self.tabla)
        self.tabla.cellDoubleClicked.connect(self._editar_seleccionado)
        layout.addWidget(self.tabla, 1)

        btn_eliminar= QPushButton("Eliminar seleccionado")

        btn_eliminar.setIcon(icono_emoji("🗑️"))

        btn_eliminar.setIconSize(QSize(16, 16))
        btn_eliminar.clicked.connect(self._eliminar)
        layout.addWidget(btn_eliminar)

        self._recargar_todo()

    def _recargar_todo(self):

        _recargar_combo_cursos(self.main_window, self.combo_curso)
        self._cargar_tabla()

    def _abrir_cursos(self):

        DialogoGestionarCursos(self.main_window, parent=self).exec()
        self._recargar_todo()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT estudiantes.*, secciones.nombre as curso_nombre FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                     ORDER BY estudiantes.apellidos, estudiantes.nombre""")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            item_nombre= QTableWidgetItem(f["nombre"])
            item_nombre.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.tabla.setItem(i, 0, item_nombre)
            self.tabla.setItem(i, 1, QTableWidgetItem(f["apellidos"] or ""))
            self.tabla.setItem(i, 2, QTableWidgetItem(f["curso_nombre"] or ""))
            self.tabla.setItem(i, 3, QTableWidgetItem(f["tutor"] or ""))

    def _limpiar(self):

        self._id_edicion= None
        self.in_nombre.clear()
        self.in_apellidos.clear()
        self.in_tutor.clear()
        self.in_telefono.clear()
        self.in_correo.clear()
        self.combo_curso.setCurrentIndex(0)
        self.btn_guardar.setText("💾 Guardar")

    def _guardar(self):

        nombre= self.in_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Falta el nombre", "El nombre del estudiante es obligatorio.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        valores= (nombre, self.in_apellidos.text().strip(), self.combo_sexo.currentText(),
                   self.in_fecha_nacimiento.date().toString("yyyy-MM-dd"), self.in_tutor.text().strip(),
                   self.in_telefono.text().strip(), self.in_correo.text().strip(), self.combo_curso.currentData())
        if self._id_edicion is None:
            c.execute("""INSERT INTO estudiantes (nombre, apellidos, sexo, fecha_nacimiento, tutor,
                         telefono, correo, seccion_id) VALUES (?,?,?,?,?,?,?,?)""", valores)
        else:
            c.execute("""UPDATE estudiantes SET nombre=?, apellidos=?, sexo=?, fecha_nacimiento=?, tutor=?,
                         telefono= ?, correo=?, seccion_id=? WHERE id=?""", (*valores, self._id_edicion))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", f"Estudiante «{nombre}» guardado correctamente.", self)
        self._limpiar()
        self._cargar_tabla()

    def _editar_seleccionado(self, fila, _col):

        id_estudiante= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT * FROM estudiantes WHERE id=?", (id_estudiante,))
        f= c.fetchone()
        conn.close()
        if not f:
            return
        self._id_edicion= id_estudiante
        self.in_nombre.setText(f["nombre"] or "")
        self.in_apellidos.setText(f["apellidos"] or "")
        self.in_tutor.setText(f["tutor"] or "")
        self.in_telefono.setText(f["telefono"] or "")
        self.in_correo.setText(f["correo"] or "")
        if f["fecha_nacimiento"]:
            self.in_fecha_nacimiento.setDate(QDate.fromString(f["fecha_nacimiento"], "yyyy-MM-dd"))
        idx_sexo= self.combo_sexo.findText(f["sexo"] or "")
        self.combo_sexo.setCurrentIndex(idx_sexo if idx_sexo >= 0 else 0)
        idx_curso= self.combo_curso.findData(f["seccion_id"])
        self.combo_curso.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
        self.btn_guardar.setText("💾 Guardar cambios")

    def _eliminar(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un estudiante de la tabla.", self)
            return
        id_estudiante= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        respuesta= QMessageBox.question(self, "Confirmar", "¿Eliminar este estudiante y todos sus datos asociados?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("DELETE FROM estudiantes WHERE id=?", (id_estudiante,))
        conn.commit()
        conn.close()
        self._limpiar()
        self._cargar_tabla()


#MATERIAS
class ModuloMateriasST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("📘 Materias")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QHBoxLayout()
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre)
        self.in_nombre.setPlaceholderText("Nombre de la materia (ej. Matemáticas)")
        form.addWidget(self.in_nombre, 1)
        self.chk_tecnica= QCheckBox("Es técnica (habilita Calificaciones Técnicas)")
        form.addWidget(self.chk_tecnica)
        self.btn_guardar= QPushButton("Guardar Materia")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        form.addWidget(self.btn_guardar)
        layout.addLayout(form)

        self.tabla= QTableWidget(0, 2)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Materia", "Técnica"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        btn_eliminar= QPushButton("Eliminar materia seleccionada")

        btn_eliminar.setIcon(icono_emoji("🗑️"))

        btn_eliminar.setIconSize(QSize(16, 16))
        btn_eliminar.clicked.connect(self._eliminar)
        layout.addWidget(btn_eliminar)

        self._cargar_tabla()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT id, nombre, es_tecnica FROM materias ORDER BY nombre")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            item= QTableWidgetItem(f["nombre"])
            item.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.tabla.setItem(i, 0, item)
            self.tabla.setItem(i, 1, QTableWidgetItem("Sí" if f["es_tecnica"] else "No"))

    def _guardar(self):

        nombre= self.in_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Falta el nombre", "Escribe el nombre de la materia.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("INSERT INTO materias (nombre, es_tecnica) VALUES (?,?)",
                  (nombre, 1 if self.chk_tecnica.isChecked() else 0))
        conn.commit()
        conn.close()
        self.in_nombre.clear()
        self.chk_tecnica.setChecked(False)
        self._cargar_tabla()

    def _eliminar(self):

        fila= self.tabla.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una materia de la tabla.", self)
            return
        id_materia= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("DELETE FROM materias WHERE id=?", (id_materia,))
        conn.commit()
        conn.close()
        self._cargar_tabla()


def _recargar_combo_materias(main_window, combo):

    conn= db.obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("SELECT id, nombre FROM materias ORDER BY nombre")
    _combo_agregar_filas(combo, c.fetchall())
    conn.close()


def _recargar_combo_periodos(main_window, combo):

    conn= db.obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
    filas= c.fetchall()
    conn.close()
    if not filas:
        #Single Teacher no pasa por ningún wizard institucional que precargue periodos: se crean 2 por defecto la
        #primera vez que algún módulo los necesita, para no obligar al docente a crear periodos manualmente antes de
        #poder registrar su primera nota.
        conn= db.obtener_conexion(main_window)
        c= conn.cursor()
        c.execute("INSERT INTO periodos (nombre, orden) VALUES ('Periodo 1', 1), ('Periodo 2', 2)")
        conn.commit()
        c.execute("SELECT id, nombre FROM periodos ORDER BY orden")
        filas= c.fetchall()
        conn.close()
    _combo_agregar_filas(combo, filas)


#ASISTENCIA
class ModuloAsistenciaST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("✅ Asistencia")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        fila_filtro= QHBoxLayout()
        fila_filtro.addWidget(QLabel("Curso:"))
        self.combo_curso= QComboBox()
        self.combo_curso.currentIndexChanged.connect(self._cargar_tabla)
        fila_filtro.addWidget(self.combo_curso, 1)
        fila_filtro.addWidget(QLabel("Fecha:"))
        self.in_fecha= QDateEdit()
        self.in_fecha.setCalendarPopup(True)
        self.in_fecha.setDate(QDate.currentDate())
        aplicar_formato_widget_fecha(self.in_fecha, main_window)
        self.in_fecha.dateChanged.connect(self._cargar_tabla)
        fila_filtro.addWidget(self.in_fecha)
        layout.addLayout(fila_filtro)

        self.tabla= QTableWidget(0, 2)

        aplicar_estructura_tabla(self.tabla)
        self.estado_vacio= EstadoVacioFiltro(self.tabla, texto_filtra_primero="Elige un curso para pasar lista")
        self.tabla.setHorizontalHeaderLabels(["Estudiante", "Estado"])
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.verticalHeader().setVisible(False)
        layout.addWidget(self.tabla, 1)

        self.btn_guardar= QPushButton("Guardar")

        self.btn_guardar.setIcon(icono_emoji("💾"))

        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(self.btn_guardar)

        _recargar_combo_cursos(main_window, self.combo_curso)

    def _cargar_tabla(self):

        seccion_id= self.combo_curso.currentData()
        self.tabla.setRowCount(0)
        if seccion_id is None:
            self.estado_vacio.actualizar(hay_filtro_elegido=False)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT id, nombre, apellidos FROM estudiantes WHERE seccion_id=? ORDER BY apellidos", (seccion_id,))
        estudiantes= c.fetchall()
        fecha= self.in_fecha.date().toString("yyyy-MM-dd")
        c.execute("SELECT estudiante_id, estado FROM asistencia WHERE seccion_id=? AND fecha=?", (seccion_id, fecha))
        estados_previos= {fila["estudiante_id"]: fila["estado"] for fila in c.fetchall()}
        conn.close()

        self.tabla.setRowCount(len(estudiantes))
        for i, est in enumerate(estudiantes):
            item_nombre= QTableWidgetItem(f"{est['nombre']} {est['apellidos'] or ''}".strip())
            item_nombre.setData(Qt.ItemDataRole.UserRole, est["id"])
            item_nombre.setFlags(item_nombre.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabla.setItem(i, 0, item_nombre)
            combo_estado= QComboBox()
            combo_estado.addItems(["Presente", "Ausente", "Tardanza", "Justificado"])
            combo_estado.setCurrentText(estados_previos.get(est["id"], "Presente"))
            self.tabla.setCellWidget(i, 1, combo_estado)
        self.estado_vacio.actualizar(hay_filtro_elegido=True)

    def _guardar(self):

        seccion_id= self.combo_curso.currentData()
        if seccion_id is None:
            mostrar_mensaje("advertencia", "Falta el curso", "Elige un curso primero.", self)
            return
        fecha= self.in_fecha.date().toString("yyyy-MM-dd")
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("DELETE FROM asistencia WHERE seccion_id=? AND fecha=?", (seccion_id, fecha))
        for fila in range(self.tabla.rowCount()):
            id_estudiante= self.tabla.item(fila, 0).data(Qt.ItemDataRole.UserRole)
            estado= self.tabla.cellWidget(fila, 1).currentText()
            c.execute("INSERT INTO asistencia (estudiante_id, seccion_id, fecha, estado) VALUES (?,?,?,?)",
                      (id_estudiante, seccion_id, fecha, estado))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", f"Asistencia del {formatear_fecha(fecha, self.main_window)} guardada.", self)


#CALIFICACIONES
class ModuloCalificacionesST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("📝 Calificaciones")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QGridLayout()
        self.combo_curso= QComboBox()
        self.combo_curso.currentIndexChanged.connect(self._cargar_estudiantes)
        self.combo_estudiante= QComboBox()
        self.combo_materia= QComboBox()
        self.combo_periodo= QComboBox()
        self.in_descripcion= QLineEdit()
        self.in_descripcion.setPlaceholderText("Ej. Examen Parcial 1")
        limitar_campo_texto(self.in_descripcion)
        self.spin_valor= QDoubleSpinBox()
        self.spin_valor.setRange(0, 1000)
        self.spin_valor.setDecimals(2)
        self.spin_peso= QDoubleSpinBox()
        self.spin_peso.setRange(0, 100)
        self.spin_peso.setSuffix(" %")
        form.addWidget(QLabel("Curso:"), 0, 0)
        form.addWidget(self.combo_curso, 0, 1)
        form.addWidget(QLabel("Estudiante:"), 0, 2)
        form.addWidget(self.combo_estudiante, 0, 3)
        form.addWidget(QLabel("Materia:"), 1, 0)
        form.addWidget(self.combo_materia, 1, 1)
        form.addWidget(QLabel("Periodo:"), 1, 2)
        form.addWidget(self.combo_periodo, 1, 3)
        form.addWidget(QLabel("Descripción:"), 2, 0)
        form.addWidget(self.in_descripcion, 2, 1, 1, 3)
        form.addWidget(QLabel("Valor:"), 3, 0)
        form.addWidget(self.spin_valor, 3, 1)
        form.addWidget(QLabel("Peso:"), 3, 2)
        form.addWidget(self.spin_peso, 3, 3)
        layout.addLayout(form)

        self.btn_guardar= QPushButton("Registrar Calificación")

        self.btn_guardar.setIcon(icono_emoji("💾"))

        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(self.btn_guardar)

        self.tabla= QTableWidget(0, 4)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Estudiante", "Materia", "Descripción", "Valor"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        _recargar_combo_cursos(main_window, self.combo_curso)
        _recargar_combo_materias(main_window, self.combo_materia)
        _recargar_combo_periodos(main_window, self.combo_periodo)
        self._cargar_tabla()

    def _cargar_estudiantes(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        seccion_id= self.combo_curso.currentData()
        if seccion_id is None:
            self.combo_estudiante.clear()
            self.combo_estudiante.addItem("Selecciona primero un curso…", None)
        else:
            c.execute("SELECT id, nombre, apellidos FROM estudiantes WHERE seccion_id=? ORDER BY apellidos",
                      (seccion_id,))
            filas= c.fetchall()
            self.combo_estudiante.clear()
            self.combo_estudiante.addItem("Selecciona…", None)
            for fila in filas:
                self.combo_estudiante.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
        conn.close()

    def _guardar(self):

        estudiante_id= self.combo_estudiante.currentData()
        materia_id= self.combo_materia.currentData()
        periodo_id= self.combo_periodo.currentData()
        if not all([estudiante_id, materia_id, periodo_id]):
            mostrar_mensaje("advertencia", "Faltan datos", "Elige curso, estudiante, materia y periodo.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""INSERT INTO calificaciones (estudiante_id, materia_id, periodo_id, categoria,
                     descripcion, valor, peso) VALUES (?,?,?,?,?,?,?)""",
                  (estudiante_id, materia_id, periodo_id, "Evaluación",
                   self.in_descripcion.text().strip(), self.spin_valor.value(), self.spin_peso.value()))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", "Calificación registrada correctamente.", self)
        self.in_descripcion.clear()
        self.spin_valor.setValue(0)
        self.spin_peso.setValue(0)
        self._cargar_tabla()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT calificaciones.descripcion, calificaciones.valor,
                     (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as est,
                     materias.nombre as mat
                     FROM calificaciones
                     JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     JOIN materias ON calificaciones.materia_id = materias.id
                     ORDER BY calificaciones.id DESC LIMIT 200""")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(f["est"]))
            self.tabla.setItem(i, 1, QTableWidgetItem(f["mat"]))
            self.tabla.setItem(i, 2, QTableWidgetItem(f["descripcion"] or ""))
            self.tabla.setItem(i, 3, QTableWidgetItem(str(f["valor"])))


#Banco de tareas
class ModuloBancoTareasST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("🗒️ Banco de Tareas")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QGridLayout()
        self.combo_curso= QComboBox()
        self.combo_materia= QComboBox()
        self.in_titulo= QLineEdit()
        self.in_titulo.setPlaceholderText("Título de la tarea")
        limitar_campo_texto(self.in_titulo)
        self.in_descripcion= QTextEdit()
        self.in_descripcion.setFixedHeight(60)
        limitar_campo_texto(self.in_descripcion)
        self.in_fecha_entrega= QDateEdit()
        self.in_fecha_entrega.setCalendarPopup(True)
        self.in_fecha_entrega.setDate(QDate.currentDate().addDays(7))
        aplicar_formato_widget_fecha(self.in_fecha_entrega, main_window)
        form.addWidget(QLabel("Curso:"), 0, 0)
        form.addWidget(self.combo_curso, 0, 1)
        form.addWidget(QLabel("Materia:"), 0, 2)
        form.addWidget(self.combo_materia, 0, 3)
        form.addWidget(QLabel("Título:"), 1, 0)
        form.addWidget(self.in_titulo, 1, 1, 1, 3)
        form.addWidget(QLabel("Descripción:"), 2, 0)
        form.addWidget(self.in_descripcion, 2, 1, 1, 3)
        form.addWidget(QLabel("Fecha de entrega:"), 3, 0)
        form.addWidget(self.in_fecha_entrega, 3, 1)
        layout.addLayout(form)

        self.btn_guardar= QPushButton("Guardar Tarea")

        self.btn_guardar.setIcon(icono_emoji("💾"))

        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(self.btn_guardar)

        self.tabla= QTableWidget(0, 3)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Título", "Curso", "Entrega"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        _recargar_combo_cursos(main_window, self.combo_curso)
        _recargar_combo_materias(main_window, self.combo_materia)
        self._cargar_tabla()

    def _guardar(self):

        titulo= self.in_titulo.text().strip()
        if not titulo:
            mostrar_mensaje("advertencia", "Falta el título", "Escribe un título para la tarea.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""INSERT INTO tareas (materia_id, seccion_id, titulo, descripcion, fecha_entrega)
                     VALUES (?,?,?,?,?)""",
                  (self.combo_materia.currentData(), self.combo_curso.currentData(), titulo,
                   self.in_descripcion.toPlainText().strip(), self.in_fecha_entrega.date().toString("yyyy-MM-dd")))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", f"Tarea «{titulo}» guardada.", self)
        self.in_titulo.clear()
        self.in_descripcion.clear()
        self._cargar_tabla()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT tareas.titulo, tareas.fecha_entrega, secciones.nombre as curso
                     FROM tareas LEFT JOIN secciones ON tareas.seccion_id = secciones.id
                     ORDER BY tareas.id DESC""")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(f["titulo"]))
            self.tabla.setItem(i, 1, QTableWidgetItem(f["curso"] or ""))
            self.tabla.setItem(i, 2, QTableWidgetItem(formatear_fecha(f["fecha_entrega"], self.main_window)))


#HORARIO
class ModuloHorarioST(QWidget):

    DIAS= ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("📅 Horario")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QGridLayout()
        self.combo_curso= QComboBox()
        self.combo_materia= QComboBox()
        self.combo_dia= QComboBox()
        self.combo_dia.addItems(self.DIAS)
        self.in_hora_inicio= QLineEdit()
        self.in_hora_inicio.setPlaceholderText("08:00")
        limitar_campo_texto(self.in_hora_inicio)
        self.in_hora_fin= QLineEdit()
        self.in_hora_fin.setPlaceholderText("09:00")
        limitar_campo_texto(self.in_hora_fin)
        self.in_aula= QLineEdit()
        self.in_aula.setPlaceholderText("Aula/lugar (opcional)")
        limitar_campo_texto(self.in_aula)
        form.addWidget(QLabel("Curso:"), 0, 0)
        form.addWidget(self.combo_curso, 0, 1)
        form.addWidget(QLabel("Materia:"), 0, 2)
        form.addWidget(self.combo_materia, 0, 3)
        form.addWidget(QLabel("Día:"), 1, 0)
        form.addWidget(self.combo_dia, 1, 1)
        form.addWidget(QLabel("Hora inicio (HH:MM):"), 1, 2)
        form.addWidget(self.in_hora_inicio, 1, 3)
        form.addWidget(QLabel("Hora fin (HH:MM):"), 2, 0)
        form.addWidget(self.in_hora_fin, 2, 1)
        form.addWidget(QLabel("Aula:"), 2, 2)
        form.addWidget(self.in_aula, 2, 3)
        layout.addLayout(form)

        self.btn_guardar= QPushButton("Guardar Horario")

        self.btn_guardar.setIcon(icono_emoji("💾"))

        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(self.btn_guardar)

        self.tabla= QTableWidget(0, 4)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Día", "Hora", "Materia", "Curso"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        _recargar_combo_cursos(main_window, self.combo_curso)
        _recargar_combo_materias(main_window, self.combo_materia)
        self._cargar_tabla()

    def _guardar(self):

        if not self.in_hora_inicio.text().strip() or not self.in_hora_fin.text().strip():
            mostrar_mensaje("advertencia", "Faltan horas", "Escribe la hora de inicio y de fin (formato HH:MM).", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""INSERT INTO horario (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto)
                     VALUES (?,?,?,?,?,?)""",
                  (self.combo_materia.currentData(), self.combo_curso.currentData(), self.combo_dia.currentText(),
                   self.in_hora_inicio.text().strip(), self.in_hora_fin.text().strip(), self.in_aula.text().strip()))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", "Bloque de horario agregado.", self)
        self.in_hora_inicio.clear()
        self.in_hora_fin.clear()
        self.in_aula.clear()
        self._cargar_tabla()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT horario.dia, horario.hora_inicio, horario.hora_fin,
                     materias.nombre as materia, secciones.nombre as curso
                     FROM horario
                     LEFT JOIN materias ON horario.materia_id = materias.id
                     LEFT JOIN secciones ON horario.seccion_id = secciones.id
                     ORDER BY horario.dia, horario.hora_inicio""")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(f["dia"]))
            self.tabla.setItem(i, 1, QTableWidgetItem(f"{f['hora_inicio']} - {f['hora_fin']}"))
            self.tabla.setItem(i, 2, QTableWidgetItem(f["materia"] or ""))
            self.tabla.setItem(i, 3, QTableWidgetItem(f["curso"] or ""))


#OBSERVACIONES
class ModuloObservacionesST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("📔 Observaciones")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QGridLayout()
        self.combo_curso= QComboBox()
        self.combo_curso.currentIndexChanged.connect(self._cargar_estudiantes)
        self.combo_estudiante= QComboBox()
        self.combo_tipo= QComboBox()
        self.combo_tipo.addItems(["Positiva", "Neutral", "Negativa"])
        self.in_descripcion= QTextEdit()
        self.in_descripcion.setFixedHeight(70)
        limitar_campo_texto(self.in_descripcion)
        form.addWidget(QLabel("Curso:"), 0, 0)
        form.addWidget(self.combo_curso, 0, 1)
        form.addWidget(QLabel("Estudiante:"), 0, 2)
        form.addWidget(self.combo_estudiante, 0, 3)
        form.addWidget(QLabel("Tipo:"), 1, 0)
        form.addWidget(self.combo_tipo, 1, 1)
        form.addWidget(QLabel("Descripción:"), 2, 0)
        form.addWidget(self.in_descripcion, 2, 1, 1, 3)
        layout.addLayout(form)

        self.btn_guardar= QPushButton("Guardar Observación")

        self.btn_guardar.setIcon(icono_emoji("💾"))

        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setObjectName("BtnAccionAgregar")
        self.btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(self.btn_guardar)

        self.tabla= QTableWidget(0, 3)

        aplicar_estructura_tabla(self.tabla)
        self.tabla.setHorizontalHeaderLabels(["Estudiante", "Tipo", "Fecha"])
        _tabla_solo_lectura(self.tabla)
        layout.addWidget(self.tabla, 1)

        _recargar_combo_cursos(main_window, self.combo_curso)
        self._cargar_tabla()

    def _cargar_estudiantes(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        seccion_id= self.combo_curso.currentData()
        self.combo_estudiante.clear()
        if seccion_id is None:
            self.combo_estudiante.addItem("Selecciona primero un curso…", None)
        else:
            c.execute("SELECT id, nombre, apellidos FROM estudiantes WHERE seccion_id=? ORDER BY apellidos",
                      (seccion_id,))
            self.combo_estudiante.addItem("Selecciona…", None)
            for fila in c.fetchall():
                self.combo_estudiante.addItem(f"{fila['nombre']} {fila['apellidos'] or ''}".strip(), fila["id"])
        conn.close()

    def _guardar(self):

        estudiante_id= self.combo_estudiante.currentData()
        if estudiante_id is None:
            mostrar_mensaje("advertencia", "Falta el estudiante", "Elige un curso y un estudiante primero.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("INSERT INTO observaciones (estudiante_id, fecha, tipo, descripcion) VALUES (?,?,?,?)",
                  (estudiante_id, datetime.now().strftime("%Y-%m-%d"), self.combo_tipo.currentText(),
                   self.in_descripcion.toPlainText().strip()))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", "Observación registrada.", self)
        self.in_descripcion.clear()
        self._cargar_tabla()

    def _cargar_tabla(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT observaciones.tipo, observaciones.fecha,
                     (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as est
                     FROM observaciones JOIN estudiantes ON observaciones.estudiante_id = estudiantes.id
                     ORDER BY observaciones.id DESC LIMIT 200""")
        filas= c.fetchall()
        conn.close()
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(f["est"]))
            self.tabla.setItem(i, 1, QTableWidgetItem(f["tipo"]))
            self.tabla.setItem(i, 2, QTableWidgetItem(formatear_fecha(f["fecha"], self.main_window)))


#REPORTES
#Exportación simple a Excel (mismo patrón liviano que otros módulos
#de la app usan con openpyxl) más los dos botones de Intercambio entre
#ediciones (ver intercambio_dialogs.py), que para Single Teacher son la
#vía principal de llevar datos a otra instalación (no hay overrides ni
#.acdx institucional del que depender).
class ModuloReportesST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo= QLabel("📈 Reportes")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        info= QLabel("Exporta tus datos a Excel, o intercambia estudiantes/calificaciones con otra "
                       "instalación de AcaDeXI (misma edición u otra).")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_excel_estudiantes= QPushButton("Exportar Estudiantes a Excel")

        btn_excel_estudiantes.setIcon(icono_emoji("📊"))

        btn_excel_estudiantes.setIconSize(QSize(16, 16))
        btn_excel_estudiantes.setObjectName("BtnAccionAgregar")
        btn_excel_estudiantes.clicked.connect(self._exportar_estudiantes_excel)
        layout.addWidget(btn_excel_estudiantes)

        btn_excel_calificaciones= QPushButton("Exportar Calificaciones a Excel")

        btn_excel_calificaciones.setIcon(icono_emoji("📊"))

        btn_excel_calificaciones.setIconSize(QSize(16, 16))
        btn_excel_calificaciones.clicked.connect(self._exportar_calificaciones_excel)
        layout.addWidget(btn_excel_calificaciones)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separador)

        btn_exportar_intercambio= QPushButton("Exportar Estudiantes a otra edición")

        btn_exportar_intercambio.setIcon(icono_emoji("📤"))

        btn_exportar_intercambio.setIconSize(QSize(16, 16))
        btn_exportar_intercambio.clicked.connect(self._exportar_intercambio)
        layout.addWidget(btn_exportar_intercambio)

        btn_importar_intercambio= QPushButton("Importar Estudiantes de otra edición")

        btn_importar_intercambio.setIcon(icono_emoji("📥"))

        btn_importar_intercambio.setIconSize(QSize(16, 16))
        btn_importar_intercambio.clicked.connect(self._importar_intercambio)
        layout.addWidget(btn_importar_intercambio)

        layout.addStretch()

    def _exportar_estudiantes_excel(self):

        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Excel", "estudiantes.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        import openpyxl
        wb= openpyxl.Workbook()
        ws= wb.active
        ws.append(["Nombre", "Apellidos", "Curso", "Tutor", "Teléfono", "Correo"])
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT estudiantes.*, secciones.nombre as curso FROM estudiantes
                     LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id ORDER BY apellidos""")
        for fila in c.fetchall():
            ws.append([fila["nombre"], fila["apellidos"], fila["curso"], fila["tutor"], fila["telefono"], fila["correo"]])
        conn.close()
        wb.save(ruta)
        mostrar_mensaje("exito", "Exportado", f"Se guardó en:\n{ruta}", self)

    def _exportar_calificaciones_excel(self):

        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Excel", "calificaciones.xlsx", "Excel (*.xlsx)")
        if not ruta:
            return
        import openpyxl
        wb= openpyxl.Workbook()
        ws= wb.active
        ws.append(["Estudiante", "Materia", "Periodo", "Descripción", "Valor", "Peso"])
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""SELECT (estudiantes.nombre || ' ' || IFNULL(estudiantes.apellidos,'')) as est,
                     materias.nombre as mat, periodos.nombre as per, calificaciones.descripcion,
                     calificaciones.valor, calificaciones.peso
                     FROM calificaciones
                     JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                     JOIN materias ON calificaciones.materia_id = materias.id
                     LEFT JOIN periodos ON calificaciones.periodo_id = periodos.id""")
        for fila in c.fetchall():
            ws.append([fila["est"], fila["mat"], fila["per"], fila["descripcion"], fila["valor"], fila["peso"]])
        conn.close()
        wb.save(ruta)
        mostrar_mensaje("exito", "Exportado", f"Se guardó en:\n{ruta}", self)

    def _exportar_intercambio(self):

        from src.interfaz.intercambio_dialogs import DialogoExportarEstudiantes
        DialogoExportarEstudiantes(self.main_window, seccion_id_actual=None, parent=self).exec()

    def _importar_intercambio(self):

        from src.interfaz.intercambio_dialogs import DialogoImportarEstudiantes
        DialogoImportarEstudiantes(self.main_window, parent=self).exec()


#CONFIGURACIÓN
class ModuloConfiguracionST(QWidget):

    def __init__(self, main_window):

        super().__init__()
        self.main_window= main_window
        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo= QLabel("⚙️ Configuración")
        titulo.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(titulo)

        form= QFormLayout()
        self.in_nombre_docente= QLineEdit()
        limitar_campo_texto(self.in_nombre_docente)
        form.addRow("Tu nombre:", self.in_nombre_docente)
        self.spin_nota_min_primaria= QDoubleSpinBox()
        self.spin_nota_min_primaria.setRange(0, 1000)
        form.addRow("Nota mínima aprobatoria (Primaria):", self.spin_nota_min_primaria)
        self.spin_nota_min_secundaria= QDoubleSpinBox()
        self.spin_nota_min_secundaria.setRange(0, 1000)
        form.addRow("Nota mínima aprobatoria (Secundaria):", self.spin_nota_min_secundaria)
        layout.addLayout(form)

        btn_guardar= QPushButton("Guardar")

        btn_guardar.setIcon(icono_emoji("💾"))

        btn_guardar.setIconSize(QSize(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._guardar)
        layout.addWidget(btn_guardar)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separador)

        btn_tutorial= QPushButton("Ver tutorial de nuevo")

        btn_tutorial.setIcon(icono_emoji("🧭"))

        btn_tutorial.setIconSize(QSize(16, 16))
        btn_tutorial.clicked.connect(self._ver_tutorial_de_nuevo)
        layout.addWidget(btn_tutorial)

        layout.addStretch()
        self._cargar()

    def _cargar(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("SELECT * FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        if fila:
            self.in_nombre_docente.setText(fila["nombre_docente"] or "")
            self.spin_nota_min_primaria.setValue(fila["nota_minima_primaria"] or 70)
            self.spin_nota_min_secundaria.setValue(fila["nota_minima_secundaria"] or 70)

    def _guardar(self):

        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("""UPDATE configuracion SET nombre_docente=?, nota_minima_primaria=?,
                     nota_minima_secundaria= ? WHERE id=1""",
                  (self.in_nombre_docente.text().strip(), self.spin_nota_min_primaria.value(),
                   self.spin_nota_min_secundaria.value()))
        conn.commit()
        conn.close()
        mostrar_mensaje("exito", "Guardado", "Configuración actualizada.", self)

    def _ver_tutorial_de_nuevo(self):

        from src.inicio.tutoriales import ofrecer_tutorial
        ofrecer_tutorial(self.main_window, "single_teacher", forzar=True)


#Wizard de primer arranque
#Primer arranque de Single Teacher (ver main.py, edicion_actual()):
#a diferencia de WizardConfiguracion (institucional, largo), este es
#intencionalmente corto -nombre del docente y, opcionalmente, su primer
#curso- porque no hay nada institucional que configurar.
class WizardSingleTeacher(QDialog):

    def __init__(self, main_window, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.setWindowTitle("Bienvenido a AcaDeXI Single Teacher")
        aplicar_icono_ventana(self)
        self.setMinimumWidth(480)

        layout= QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        intro= QLabel(
            "Eres dueño directo de tus datos: no hay ninguna institución detrás. Cuéntanos un poco "
            "de ti para empezar (puedes cambiar esto luego en Configuración).")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form= QFormLayout()
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre)
        form.addRow("Tu nombre:", self.in_nombre)
        self.in_curso= QLineEdit()
        limitar_campo_texto(self.in_curso)
        self.in_curso.setPlaceholderText("Ej. 8vo A - Matemáticas 2026 (opcional, puedes agregarlo después)")
        form.addRow("Tu primer curso:", self.in_curso)
        self.combo_nivel= QComboBox()
        self.combo_nivel.addItems(["Primaria", "Secundaria", "Preparatoria", "Universidad"])
        form.addRow("Nivel educativo:", self.combo_nivel)
        layout.addLayout(form)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Empezar")
        botones.accepted.connect(self._finalizar)
        layout.addWidget(botones)

        centrar_y_al_frente(self, parent)

    def _finalizar(self):

        nombre= self.in_nombre.text().strip()
        if not nombre:
            mostrar_mensaje("advertencia", "Falta tu nombre", "Escribe tu nombre para continuar.", self)
            return
        conn= db.obtener_conexion(self.main_window)
        c= conn.cursor()
        c.execute("UPDATE configuracion SET nombre_docente=? WHERE id=1", (nombre,))
        curso= self.in_curso.text().strip()
        if curso:
            c.execute("INSERT INTO secciones (nombre, nivel_educativo) VALUES (?,?)",
                      (curso, self.combo_nivel.currentText()))
        conn.commit()
        conn.close()
        db.marcar_wizard_completado(self.main_window, nombre)
        self.accept()
