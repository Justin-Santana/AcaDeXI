"""Piezas de interfaz compartidas por las secuencias didácticas de la edición
institucional (src/modulos/secuencias.py) y de Single Teacher (secuencias_st.py)."""
from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDateEdit, QSpinBox,
                               QCheckBox, QWidget, QHBoxLayout, QAbstractItemView, QInputDialog)

from src.nucleo import secuencias as logica
from src.nucleo.iconos import mostrar_mensaje

FECHA_VACIA = QDate(2000, 1, 1)
COLORES_ESTADO = {"Borrador": "#64748B", "En curso": "#F59E0B", "Completada": "#10B981", "Archivada": "#94A3B8"}


def fecha_a_iso(qdate):
    return None if qdate == FECHA_VACIA else qdate.toString("yyyy-MM-dd")


def iso_a_fecha(iso):
    d = QDate.fromString(str(iso or "")[:10], "yyyy-MM-dd")
    return d if d.isValid() else FECHA_VACIA


def selector_fecha():
    """QDateEdit que admite "sin fecha": la fecha mínima se muestra como '—'."""
    w = QDateEdit()
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd/MM/yyyy")
    w.setMinimumDate(FECHA_VACIA)
    w.setSpecialValueText("—")
    w.setDate(FECHA_VACIA)
    return w


class TablaSesiones(QTableWidget):
    """Tabla editable de sesiones: Fecha, Momento, Actividades, Evidencias, Instrumento,
    Metacognición, Recursos, Min y Realizada (mismas columnas que el Word del MINERD)."""
    COLUMNAS = ["Fecha", "Momento", "Actividades de aprendizaje", "Evidencias", "Instrumento de evaluación",
                "Metacognición", "Recursos", "Min", "Realizada"]

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLUMNAS), parent)
        self.setHorizontalHeaderLabels(self.COLUMNAS)
        self.setWordWrap(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setDefaultSectionSize(54)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, ancho in enumerate((110, 110, 260, 160, 170, 160, 140, 60, 80)):
            self.setColumnWidth(i, ancho)

    def poblar(self, sesiones):
        self.setRowCount(0)
        for s in sesiones:
            self.agregar(s)

    def agregar(self, s=None, posicion=None):
        s = s or logica.sesiones_base(2)[1]
        fila = self.rowCount() if posicion is None else posicion
        self.insertRow(fila)
        f = selector_fecha(); f.setDate(iso_a_fecha(s.get("fecha")))
        self.setCellWidget(fila, 0, f)
        m = QComboBox(); m.addItems(logica.MOMENTOS)
        m.setCurrentText(s.get("momento") if s.get("momento") in logica.MOMENTOS else "Desarrollo")
        self.setCellWidget(fila, 1, m)
        for col, clave in ((2, "actividad"), (3, "evidencia"), (5, "metacognicion"), (6, "recursos")):
            self.setItem(fila, col, QTableWidgetItem(s.get(clave) or ""))
        inst = QComboBox(); inst.setEditable(True)
        inst.addItems([""] + logica.INSTRUMENTOS_EVALUACION)
        inst.setCurrentText(s.get("instrumento") or "")
        self.setCellWidget(fila, 4, inst)
        mins = QSpinBox(); mins.setRange(0, 600); mins.setValue(int(s.get("duracion_min") or 0))
        self.setCellWidget(fila, 7, mins)
        chk = QCheckBox(); chk.setChecked(bool(s.get("realizada")))
        cont = QWidget(); hl = QHBoxLayout(cont); hl.setContentsMargins(0, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter); hl.addWidget(chk)
        self.setCellWidget(fila, 8, cont)

    def sesiones(self):
        out = []
        for r in range(self.rowCount()):
            txt = lambda c: (self.item(r, c).text().strip() if self.item(r, c) else "")
            out.append({
                "fecha": fecha_a_iso(self.cellWidget(r, 0).date()),
                "momento": self.cellWidget(r, 1).currentText(),
                "actividad": txt(2), "evidencia": txt(3),
                "instrumento": self.cellWidget(r, 4).currentText().strip(),
                "metacognicion": txt(5), "recursos": txt(6),
                "duracion_min": self.cellWidget(r, 7).value(),
                "realizada": self.cellWidget(r, 8).findChild(QCheckBox).isChecked(),
            })
        return out

    def agregar_despues_de_la_actual(self):
        actual = self.currentRow()
        self.agregar(posicion=actual + 1 if actual >= 0 else None)

    def quitar_actual(self):
        r = self.currentRow()
        if r >= 0:
            self.removeRow(r)

    def mover_actual(self, delta):
        r = self.currentRow()
        nuevo = r + delta
        if r < 0 or not 0 <= nuevo < self.rowCount():
            return
        sesiones = self.sesiones()
        sesiones[r], sesiones[nuevo] = sesiones[nuevo], sesiones[r]
        self.poblar(sesiones)
        self.selectRow(nuevo)

    def autocompletar_fechas(self, inicio_iso, padre=None):
        """Reparte las sesiones desde `inicio_iso` en los días de clase que pida el docente.
        Devuelve la última fecha asignada (ISO) o None si se canceló o hubo error."""
        if not inicio_iso:
            mostrar_mensaje("advertencia", "Fechas", "Primero indica la fecha de inicio.", padre or self)
            return None
        texto, ok = QInputDialog.getText(
            padre or self, "Días de clase",
            "Días de la semana con clase (1=lunes … 5=viernes), separados por coma:", text="1,2,3,4,5")
        if not ok:
            return None
        try:
            dias = [int(x) - 1 for x in texto.replace(" ", "").split(",") if x]
            if not dias or any(not 0 <= d <= 6 for d in dias):
                raise ValueError
            sesiones = self.sesiones()
            fechas = logica.distribuir_fechas(inicio_iso, len(sesiones), dias)
        except ValueError:
            mostrar_mensaje("advertencia", "Fechas", "Escribe números del 1 al 7 separados por coma.", padre or self)
            return None
        for s, fch in zip(sesiones, fechas):
            s["fecha"] = fch
        self.poblar(sesiones)
        return fechas[-1] if fechas else None
