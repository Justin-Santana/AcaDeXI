#-----------------------------------------
#estado vacío para tablas con filtro obligatorio
#Cuando la tabla depende de un filtro que el usuario todavía no eligió (curso, materia, rango de
#fechas), antes quedaba vacía sin decir nada y parecía que no había datos o que había fallado la
#carga. Este módulo pone encima de la tabla un cartel centrado con un icono y un texto, que se
#muestra solo cuando no hay nada que mostrar.
#Se usa una vez, justo después de crear la tabla:
#self.tabla= QTableWidget()
#self.estado_vacio= EstadoVacioFiltro(self.tabla)
#y después, cada vez que se repuebla según el filtro:
#self.estado_vacio.actualizar(hay_filtro_elegido=curso_id is not None)
#-----------------------------------------
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from src.nucleo.iconos_emoji import pixmap_emoji

TEXTO_FILTRA_PRIMERO= "Filtra primero para revelar el contenido"
TEXTO_SIN_RESULTADOS= "No hay resultados con los filtros actuales"


#cartel centrado sobre la tabla. Se acomoda solo cuando la tabla cambia de tamaño, así que ningún
#módulo tiene que acordarse de moverlo a mano.
class EstadoVacioFiltro(QWidget):

    def __init__(self, tabla, icono="🔍", texto_filtra_primero=TEXTO_FILTRA_PRIMERO,
                 texto_sin_resultados= TEXTO_SIN_RESULTADOS):

        super().__init__(tabla)

        self.tabla= tabla
        self.texto_filtra_primero= texto_filtra_primero
        self.texto_sin_resultados= texto_sin_resultados

        #los clics pasan de largo: el cartel no debe robarle el mouse a la tabla
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        layout= QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji(icono, 40))
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icono)

        self.lbl_texto= QLabel(self.texto_filtra_primero)
        self.lbl_texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_texto.setWordWrap(True)
        self.lbl_texto.setStyleSheet("color: rgba(128,128,128,0.85); font-size: 13px; font-weight: 500;")
        layout.addWidget(self.lbl_texto)

        self.hide()
        tabla.installEventFilter(self)

    def eventFilter(self, obj, event):

        if obj is self.tabla and event.type() in (event.Type.Resize, event.Type.Show):
            self._reubicar()

        return False

    def _reubicar(self):

        self.setGeometry(0, 0, self.tabla.width(), self.tabla.height())
        self.raise_()

    #se llama después de repoblar la tabla. hay_filtro_elegido dice si el filtro ya tiene valor
    #(aunque el resultado hayan sido 0 filas) y vacio se pasa a mano en los widgets que no son
    #tablas, como la malla curricular, que se dibuja a pulso y no tiene rowCount().
    def actualizar(self, hay_filtro_elegido, vacio=None):

        if vacio is None:
            filas= self.tabla.rowCount() if hasattr(self.tabla, "rowCount") else self.tabla.topLevelItemCount()
            vacio= filas == 0

        if not vacio:
            self.hide()
            return

        self.lbl_texto.setText(self.texto_filtra_primero if not hay_filtro_elegido else self.texto_sin_resultados)
        self._reubicar()
        self.show()
