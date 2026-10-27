#Piezas de interfaz que comparten las secuencias didácticas de la edición institucional
#(src/modulos/secuencias.py) y las de Single Teacher (src/modulos/secuencias_st.py).
from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDateEdit, QSpinBox,
                               QCheckBox, QWidget, QHBoxLayout, QAbstractItemView, QInputDialog)

from src.nucleo import secuencias as logica
from src.nucleo.iconos import mostrar_mensaje

#La fecha más baja posible hace de "sin fecha": se muestra como una raya.
FECHA_VACIA= QDate(2000, 1, 1)

COLORES_ESTADO= {"Borrador": "#64748B", "En curso": "#F59E0B", "Completada": "#10B981", "Archivada": "#94A3B8"}

#Posición de cada columna de la tabla de sesiones.
COLUMNA_FECHA= 0
COLUMNA_MOMENTO= 1
COLUMNA_ACTIVIDAD= 2
COLUMNA_EVIDENCIA= 3
COLUMNA_INSTRUMENTO= 4
COLUMNA_METACOGNICION= 5
COLUMNA_RECURSOS= 6
COLUMNA_MINUTOS= 7
COLUMNA_REALIZADA= 8


# -----------------------------------------
# fechas
# -----------------------------------------
def fecha_a_iso(fecha):

    return None if fecha == FECHA_VACIA else fecha.toString("yyyy-MM-dd")


def iso_a_fecha(texto_iso):

    fecha= QDate.fromString(str(texto_iso or "")[:10], "yyyy-MM-dd")

    return fecha if fecha.isValid() else FECHA_VACIA


#Un QDateEdit que admite "sin fecha".
def selector_fecha():

    in_fecha= QDateEdit()
    in_fecha.setCalendarPopup(True)
    in_fecha.setDisplayFormat("dd/MM/yyyy")
    in_fecha.setMinimumDate(FECHA_VACIA)
    in_fecha.setSpecialValueText("—")
    in_fecha.setDate(FECHA_VACIA)

    return in_fecha


# -----------------------------------------
# tabla de sesiones
# -----------------------------------------
#Tabla editable con las mismas columnas que el Word del MINERD, más los minutos y si la sesión ya
#se dio.
class TablaSesiones(QTableWidget):

    COLUMNAS= ["Fecha", "Momento", "Actividades de aprendizaje", "Evidencias", "Instrumento de evaluación",
               "Metacognición", "Recursos", "Min", "Realizada"]

    def __init__(self, parent=None):

        super().__init__(0, len(self.COLUMNAS), parent)

        self.setHorizontalHeaderLabels(self.COLUMNAS)
        self.setWordWrap(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setDefaultSectionSize(54)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        for columna, ancho in enumerate((110, 110, 260, 160, 170, 160, 140, 60, 80)):
            self.setColumnWidth(columna, ancho)

    def poblar(self, sesiones):

        self.setRowCount(0)

        for sesion in sesiones:
            self.agregar(sesion)

    #Agrega una fila con los datos de la sesión, al final o en la posición indicada. Sin sesión, la fila
    #sale con la segunda sesión de la plantilla de dos, que es de Cierre.
    def agregar(self, sesion=None, posicion=None):

        sesion= sesion or logica.sesiones_base(2)[1]
        fila= self.rowCount() if posicion is None else posicion
        self.insertRow(fila)

        in_fecha= selector_fecha()
        in_fecha.setDate(iso_a_fecha(sesion.get("fecha")))
        self.setCellWidget(fila, COLUMNA_FECHA, in_fecha)

        combo_momento= QComboBox()
        combo_momento.addItems(logica.MOMENTOS)
        momento= sesion.get("momento")
        combo_momento.setCurrentText(momento if momento in logica.MOMENTOS else "Desarrollo")
        self.setCellWidget(fila, COLUMNA_MOMENTO, combo_momento)

        self.setItem(fila, COLUMNA_ACTIVIDAD, QTableWidgetItem(sesion.get("actividad") or ""))
        self.setItem(fila, COLUMNA_EVIDENCIA, QTableWidgetItem(sesion.get("evidencia") or ""))
        self.setItem(fila, COLUMNA_METACOGNICION, QTableWidgetItem(sesion.get("metacognicion") or ""))
        self.setItem(fila, COLUMNA_RECURSOS, QTableWidgetItem(sesion.get("recursos") or ""))

        combo_instrumento= QComboBox()
        combo_instrumento.setEditable(True)
        combo_instrumento.addItems([""] + logica.INSTRUMENTOS_EVALUACION)
        combo_instrumento.setCurrentText(sesion.get("instrumento") or "")
        self.setCellWidget(fila, COLUMNA_INSTRUMENTO, combo_instrumento)

        in_minutos= QSpinBox()
        in_minutos.setRange(0, 600)
        in_minutos.setValue(int(sesion.get("duracion_min") or 0))
        self.setCellWidget(fila, COLUMNA_MINUTOS, in_minutos)

        chk_realizada= QCheckBox()
        chk_realizada.setChecked(bool(sesion.get("realizada")))

        #la casilla va dentro de un widget con layout para que quede centrada en la celda
        contenedor= QWidget()
        layout_casilla= QHBoxLayout(contenedor)
        layout_casilla.setContentsMargins(0, 0, 0, 0)
        layout_casilla.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_casilla.addWidget(chk_realizada)
        self.setCellWidget(fila, COLUMNA_REALIZADA, contenedor)

    def _texto_de_celda(self, fila, columna):

        item= self.item(fila, columna)

        return item.text().strip() if item else ""

    #Lee la tabla y devuelve la lista de sesiones, en el mismo formato que usa la lógica.
    def sesiones(self):

        sesiones= []

        for fila in range(self.rowCount()):
            sesiones.append({
                "fecha": fecha_a_iso(self.cellWidget(fila, COLUMNA_FECHA).date()),
                "momento": self.cellWidget(fila, COLUMNA_MOMENTO).currentText(),
                "actividad": self._texto_de_celda(fila, COLUMNA_ACTIVIDAD),
                "evidencia": self._texto_de_celda(fila, COLUMNA_EVIDENCIA),
                "instrumento": self.cellWidget(fila, COLUMNA_INSTRUMENTO).currentText().strip(),
                "metacognicion": self._texto_de_celda(fila, COLUMNA_METACOGNICION),
                "recursos": self._texto_de_celda(fila, COLUMNA_RECURSOS),
                "duracion_min": self.cellWidget(fila, COLUMNA_MINUTOS).value(),
                "realizada": self.cellWidget(fila, COLUMNA_REALIZADA).findChild(QCheckBox).isChecked(),
            })

        return sesiones

    def agregar_despues_de_la_actual(self):

        actual= self.currentRow()

        if actual < 0:
            self.agregar()
        else:
            self.agregar(posicion=actual + 1)

    def quitar_actual(self):

        fila= self.currentRow()

        if fila >= 0:
            self.removeRow(fila)

    #Sube (-1) o baja (+1) la sesión seleccionada. Se lee la tabla, se intercambian las dos sesiones y
    #se vuelve a dibujar todo.
    def mover_actual(self, desplazamiento):

        fila= self.currentRow()
        destino= fila + desplazamiento

        if fila < 0 or not 0 <= destino < self.rowCount():
            return

        sesiones= self.sesiones()
        sesiones[fila], sesiones[destino]= sesiones[destino], sesiones[fila]
        self.poblar(sesiones)
        self.selectRow(destino)

    #Reparte las sesiones desde la fecha de inicio en los días de clase que el docente indique. Devuelve
    #la última fecha asignada (ISO), o None si canceló o escribió algo que no sirve.
    def autocompletar_fechas(self, inicio_iso, padre=None):

        padre= padre or self

        if not inicio_iso:
            mostrar_mensaje("advertencia", "Fechas", "Primero indica la fecha de inicio.", padre)
            return None

        texto, aceptado= QInputDialog.getText(
            padre, "Días de clase",
            "Días de la semana con clase (1=lunes … 5=viernes), separados por coma:", text="1,2,3,4,5")

        if not aceptado:
            return None

        try:

            dias= [int(numero) - 1 for numero in texto.replace(" ", "").split(",") if numero]

            if not dias or any(not 0 <= dia <= 6 for dia in dias):
                raise ValueError

            sesiones= self.sesiones()
            fechas= logica.distribuir_fechas(inicio_iso, len(sesiones), dias)

        except ValueError:
            mostrar_mensaje("advertencia", "Fechas", "Escribe números del 1 al 7 separados por coma.", padre)
            return None

        for sesion, fecha in zip(sesiones, fechas):
            sesion["fecha"]= fecha

        self.poblar(sesiones)

        return fechas[-1] if fechas else None
