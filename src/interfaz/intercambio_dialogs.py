#Diálogos reutilizables de "Intercambio entre ediciones" (ver
#intercambio_datos.py). Un solo lugar para la UI de exportar/importar
#paquetes .acdxpkg, usado tanto desde estudiantes.py como desde
#calificaciones.py -y disponible para cualquier otro módulo que en el futuro
#quiera sumarse (Asistencia, Banco de Tareas...) sin reinventar el diálogo.
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QComboBox
from PySide6.QtCore import QSize

from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, centrar_y_al_frente
from src.nucleo.iconos_emoji import icono_emoji
from src.nucleo import intercambio_datos as intercambio


def _edicion_legible(codigo):

    return {
        "full": "AcaDeXI (Admin/Director)",
        "docentes": "AcaDeXI Docentes",
        "single_teacher": "AcaDeXI Single Teacher",
        "side_stepper": "AcaDeXI Side Stepper",
    }.get(codigo, codigo)


#Secciones/cursos disponibles como destino de importación en ESTA
#instalación, sin importar la edición: consulta bd.py (full/docentes) o
#bd_single_teacher.py (single_teacher) según corresponda, y devuelve
#[(id, etiqueta), ...]. side_stepper reutiliza el esquema de bd.py.
def _listar_secciones_destino(main_window):

    try:

        from src.nucleo.edicion import edicion_actual
        edicion= edicion_actual()
    except Exception:
        edicion= "full"
    if edicion == "single_teacher":
        from src.nucleo import bd_single_teacher
        conn= bd_single_teacher.obtener_conexion(main_window)
        c= conn.cursor()
        c.execute("SELECT id, nombre FROM secciones ORDER BY nombre")
        filas= [(fila["id"], fila["nombre"]) for fila in c.fetchall()]
        conn.close()
        return filas
    from src.nucleo.bd import obtener_conexion
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT secciones.id, (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                 FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id
                 ORDER BY grados.orden, secciones.nombre""")
    filas= [(fila["id"], fila["etiqueta"]) for fila in c.fetchall()]
    conn.close()
    return filas


class _DialogoBase(QDialog):

    def __init__(self, titulo, parent=None):

        super().__init__(parent)
        self.setWindowTitle(titulo)
        aplicar_icono_ventana(self)
        self.setMinimumWidth(420)
        self.layout_principal= QVBoxLayout(self)
        self.layout_principal.setContentsMargins(18, 18, 18, 18)
        self.layout_principal.setSpacing(12)


#ESTUDIANTES
class DialogoExportarEstudiantes(_DialogoBase):

    def __init__(self, main_window, seccion_id_actual=None, parent=None):

        super().__init__("Exportar estudiantes a otra edición de AcaDeXI", parent)
        self.main_window= main_window
        self.seccion_id_actual= seccion_id_actual

        lbl_info= QLabel(
            "Genera un archivo .acdxpkg con los estudiantes que puedes importar "
            "después en cualquier otra instalación de AcaDeXI (misma edición u otra: "
            "Full Institutional, Docentes, Single Teacher o Side Stepper).")
        lbl_info.setWordWrap(True)
        self.layout_principal.addWidget(lbl_info)

        self.lbl_alcance= QLabel(
            "Se exportará la sección actualmente filtrada." if seccion_id_actual is not None
            else "Se exportarán TODOS los estudiantes visibles para ti.")
        self.lbl_alcance.setWordWrap(True)
        self.layout_principal.addWidget(self.lbl_alcance)

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        btn_exportar= QPushButton("Exportar…")
        btn_exportar.setIcon(icono_emoji("📤"))
        btn_exportar.setIconSize(QSize(16, 16))
        btn_exportar.clicked.connect(self._exportar)
        fila_botones.addWidget(btn_exportar)
        self.layout_principal.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)

    def _exportar(self):

        ruta, _= QFileDialog.getSaveFileName(
            self, "Guardar paquete de estudiantes", "estudiantes" + intercambio.EXTENSION,
            f"Paquete AcaDeXI (*{intercambio.EXTENSION})")
        if not ruta:
            return
        if not ruta.endswith(intercambio.EXTENSION):
            ruta += intercambio.EXTENSION
        try:

            n= intercambio.exportar_estudiantes(self.main_window, ruta, seccion_id=self.seccion_id_actual)
            mostrar_mensaje("exito", "Exportado",
                             f"Se exportaron {n} estudiante(s) a:\n{ruta}", self)
            self.accept()
        except Exception as error:
            mostrar_mensaje("error", "No se pudo exportar", str(error), self)


class DialogoImportarEstudiantes(_DialogoBase):

    def __init__(self, main_window, parent=None):

        super().__init__("Importar estudiantes desde otra edición de AcaDeXI", parent)
        self.main_window= main_window
        self.ruta_seleccionada= None

        lbl_info= QLabel(
            "Importa un archivo .acdxpkg de estudiantes generado por cualquier edición de "
            "AcaDeXI. Un estudiante que ya exista aquí (mismo nombre, apellidos y fecha de "
            "nacimiento) se ACTUALIZA; si no existe, se crea nuevo en la sección que elijas abajo.")
        lbl_info.setWordWrap(True)
        self.layout_principal.addWidget(lbl_info)

        btn_elegir= QPushButton("Elegir archivo .acdxpkg…")

        btn_elegir.setIcon(icono_emoji("📂"))

        btn_elegir.setIconSize(QSize(16, 16))
        btn_elegir.clicked.connect(self._elegir_archivo)
        self.layout_principal.addWidget(btn_elegir)
        self.lbl_archivo= QLabel("Ningún archivo seleccionado todavía.")
        self.lbl_archivo.setWordWrap(True)
        self.layout_principal.addWidget(self.lbl_archivo)

        self.layout_principal.addWidget(QLabel("Sección/curso destino para estudiantes NUEVOS:"))
        self.combo_seccion_destino= QComboBox()
        self.combo_seccion_destino.addItem("— Ninguna (dejar sin sección) —", None)
        for id_seccion, etiqueta in _listar_secciones_destino(main_window):
            self.combo_seccion_destino.addItem(etiqueta, id_seccion)
        self.layout_principal.addWidget(self.combo_seccion_destino)

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        self.btn_importar= QPushButton("Importar")
        self.btn_importar.setIcon(icono_emoji("📥"))
        self.btn_importar.setIconSize(QSize(16, 16))
        self.btn_importar.clicked.connect(self._importar)
        fila_botones.addWidget(self.btn_importar)
        self.layout_principal.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)

    def _elegir_archivo(self):

        ruta, _= QFileDialog.getOpenFileName(
            self, "Elegir paquete de estudiantes", "", f"Paquete AcaDeXI (*{intercambio.EXTENSION})")
        if ruta:
            self.ruta_seleccionada= ruta
            self.lbl_archivo.setText(f"Archivo: {ruta}")

    def _importar(self):

        if not self.ruta_seleccionada:
            mostrar_mensaje("advertencia", "Falta el archivo", "Elige primero un archivo .acdxpkg.", self)
            return
        try:

            resultado= intercambio.importar_estudiantes(
                self.main_window, self.ruta_seleccionada,
                seccion_id_destino= self.combo_seccion_destino.currentData())
            mostrar_mensaje("exito", "Importado",
                             f"Creados: {resultado['creados']}\nActualizados: {resultado['actualizados']}", self)
            self.accept()
        except Exception as error:
            mostrar_mensaje("error", "No se pudo importar", str(error), self)


#CALIFICACIONES
class DialogoExportarCalificaciones(_DialogoBase):

    def __init__(self, main_window, materia_id, materia_nombre, periodo_id=None, periodo_nombre="", parent=None):

        super().__init__("Exportar calificaciones a otra edición de AcaDeXI", parent)
        self.main_window= main_window
        self.materia_id= materia_id
        self.periodo_id= periodo_id

        if materia_id is None:
            lbl_info= QLabel("Elige primero una Materia (y opcionalmente un Periodo) arriba antes de exportar.")
            lbl_info.setWordWrap(True)
            self.layout_principal.addWidget(lbl_info)
            self._exportable= False
        else:
            texto= f"Se exportarán las calificaciones de «{materia_nombre}»"
            texto += f", periodo «{periodo_nombre}»." if periodo_id else " (todos los periodos)."
            lbl_info= QLabel(texto)
            lbl_info.setWordWrap(True)
            self.layout_principal.addWidget(lbl_info)
            self._exportable= True

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        btn_exportar= QPushButton("Exportar…")
        btn_exportar.setIcon(icono_emoji("📤"))
        btn_exportar.setIconSize(QSize(16, 16))
        btn_exportar.setEnabled(self._exportable)
        btn_exportar.clicked.connect(self._exportar)
        fila_botones.addWidget(btn_exportar)
        self.layout_principal.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)

    def _exportar(self):

        ruta, _= QFileDialog.getSaveFileName(
            self, "Guardar paquete de calificaciones", "calificaciones" + intercambio.EXTENSION,
            f"Paquete AcaDeXI (*{intercambio.EXTENSION})")
        if not ruta:
            return
        if not ruta.endswith(intercambio.EXTENSION):
            ruta += intercambio.EXTENSION
        try:

            n= intercambio.exportar_calificaciones(self.main_window, ruta, self.materia_id, self.periodo_id)
            mostrar_mensaje("exito", "Exportado",
                             f"Se exportaron {n} calificación(es) a:\n{ruta}", self)
            self.accept()
        except Exception as error:
            mostrar_mensaje("error", "No se pudo exportar", str(error), self)


#A diferencia de Estudiantes, aquí SIEMPRE se pide Materia y Periodo
#DESTINO explícitos (ver intercambio_datos.importar_calificaciones): no
#se intenta adivinar a cuál corresponden por nombre, para no arriesgar
#mezclar calificaciones entre materias/periodos por una coincidencia de
#texto accidental.
class DialogoImportarCalificaciones(_DialogoBase):

    def __init__(self, main_window, combo_materia_origen, combo_periodo_origen, parent=None):

        super().__init__("Importar calificaciones desde otra edición de AcaDeXI", parent)
        self.main_window= main_window
        self.ruta_seleccionada= None

        lbl_info= QLabel(
            "Importa un archivo .acdxpkg de calificaciones. Solo se importa la nota de un "
            "estudiante si YA EXISTE aquí (mismo nombre, apellidos y fecha de nacimiento); "
            "importa primero sus estudiantes si hace falta.")
        lbl_info.setWordWrap(True)
        self.layout_principal.addWidget(lbl_info)

        btn_elegir= QPushButton("Elegir archivo .acdxpkg…")

        btn_elegir.setIcon(icono_emoji("📂"))

        btn_elegir.setIconSize(QSize(16, 16))
        btn_elegir.clicked.connect(self._elegir_archivo)
        self.layout_principal.addWidget(btn_elegir)
        self.lbl_archivo= QLabel("Ningún archivo seleccionado todavía.")
        self.lbl_archivo.setWordWrap(True)
        self.layout_principal.addWidget(self.lbl_archivo)

        self.layout_principal.addWidget(QLabel(
            "Las calificaciones se importarán a la Materia y Periodo ya elegidos "
            "arriba en esta pantalla."))
        self._combo_materia_origen= combo_materia_origen
        self._combo_periodo_origen= combo_periodo_origen

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        self.btn_importar= QPushButton("Importar")
        self.btn_importar.setIcon(icono_emoji("📥"))
        self.btn_importar.setIconSize(QSize(16, 16))
        self.btn_importar.clicked.connect(self._importar)
        fila_botones.addWidget(self.btn_importar)
        self.layout_principal.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)

    def _elegir_archivo(self):

        ruta, _= QFileDialog.getOpenFileName(
            self, "Elegir paquete de calificaciones", "", f"Paquete AcaDeXI (*{intercambio.EXTENSION})")
        if ruta:
            self.ruta_seleccionada= ruta
            self.lbl_archivo.setText(f"Archivo: {ruta}")

    def _importar(self):

        materia_id= self._combo_materia_origen.currentData()
        periodo_id= self._combo_periodo_origen.currentData()
        if not self.ruta_seleccionada:
            mostrar_mensaje("advertencia", "Falta el archivo", "Elige primero un archivo .acdxpkg.", self)
            return
        if materia_id is None or periodo_id is None:
            mostrar_mensaje("advertencia", "Falta Materia/Periodo",
                             "Elige una Materia y un Periodo destino arriba antes de importar.", self)
            return
        try:

            resultado= intercambio.importar_calificaciones(
                self.main_window, self.ruta_seleccionada, materia_id, periodo_id)
            texto= f"Importadas: {resultado['importadas']}"
            if resultado["estudiantes_faltantes"]:
                texto += ("\n\nNo se pudieron importar las notas de estos estudiantes porque no "
                          "existen aquí todavía:\n- " + "\n- ".join(resultado["estudiantes_faltantes"]))
            mostrar_mensaje("exito" if not resultado["estudiantes_faltantes"] else "advertencia",
                             "Importación completada", texto, self)
            self.accept()
        except Exception as error:
            mostrar_mensaje("error", "No se pudo importar", str(error), self)
