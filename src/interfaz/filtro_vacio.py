"""Estado vacío reutilizable para tablas cuyo contenido depende de un filtro
obligatorio (Curso/Sección, Materia, rango de fechas...) que el usuario
todavía no eligió.

Antes, cada módulo dejaba la tabla simplemente VACÍA mientras no se
eligiera el filtro -sin ningún mensaje-, lo que se podía confundir con "no
hay datos" o con un error de carga. Este módulo agrega, encima de la
tabla, un overlay centrado con un ícono + texto (mismo sistema de iconos
QPainter de iconos_emoji.py) que se muestra/oculta solo según haya o no
contenido.

Uso típico (una vez, justo después de crear la tabla):

    from filtro_vacio import EstadoVacioFiltro
    self.tabla = QTableWidget()
    self.estado_vacio = EstadoVacioFiltro(self.tabla)

Y luego, cada vez que se repuebla la tabla según el filtro activo:

    self.estado_vacio.actualizar(hay_filtro_elegido=curso_id is not None)

`actualizar()` decide solo si mostrar el overlay: se muestra cuando
`hay_filtro_elegido` es False, O cuando es True pero la tabla igual quedó
sin filas (ese segundo caso usa el texto de "sin resultados", no el de
"filtra primero" -son mensajes distintos, ver `texto_sin_resultados`)."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from src.nucleo.iconos_emoji import pixmap_emoji

TEXTO_FILTRA_PRIMERO = "Filtra primero para revelar el contenido"
TEXTO_SIN_RESULTADOS = "No hay resultados con los filtros actuales"


class EstadoVacioFiltro(QWidget):
    """Overlay centrado sobre `tabla` (QTableWidget/QTreeWidget/cualquier
    widget con .viewport()). Se posiciona solo, siguiendo el tamaño de la
    tabla; no altera el layout existente."""

    def __init__(self, tabla, icono="🔍", texto_filtra_primero=TEXTO_FILTRA_PRIMERO,
                 texto_sin_resultados=TEXTO_SIN_RESULTADOS):
        super().__init__(tabla)
        self.tabla = tabla
        self.texto_filtra_primero = texto_filtra_primero
        self.texto_sin_resultados = texto_sin_resultados
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        self.lbl_icono = QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji(icono, 40))
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_icono)

        self.lbl_texto = QLabel(self.texto_filtra_primero)
        self.lbl_texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_texto.setWordWrap(True)
        self.lbl_texto.setStyleSheet("color: rgba(128,128,128,0.85); font-size: 13px; font-weight: 500;")
        lay.addWidget(self.lbl_texto)

        self.hide()
        # Reajusta la geometría del overlay cada vez que la tabla cambia de
        # tamaño (resize de ventana, panel colapsable, etc.) sin que cada
        # módulo tenga que acordarse de llamarlo a mano.
        tabla.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.tabla and event.type() in (event.Type.Resize, event.Type.Show):
            self._reubicar()
        return False

    def _reubicar(self):
        self.setGeometry(0, 0, self.tabla.width(), self.tabla.height())
        self.raise_()

    def actualizar(self, hay_filtro_elegido, vacio=None):
        """Llamar después de repoblar la tabla. `hay_filtro_elegido`: True
        si el/los filtro(s) obligatorios ya tienen un valor elegido (aunque
        el resultado haya quedado en 0 filas). `vacio`: para widgets que no
        son QTableWidget/QTreeWidget (ej. MallaCurricular, un QWidget
        pintado a mano) y por lo tanto no tienen .rowCount(): pásalo
        explícitamente (True/False) en vez de dejar que se autodetecte."""
        if vacio is None:
            filas = self.tabla.rowCount() if hasattr(self.tabla, "rowCount") else self.tabla.topLevelItemCount()
            vacio = filas == 0
        if not vacio:
            self.hide()
            return
        self.lbl_texto.setText(self.texto_filtra_primero if not hay_filtro_elegido else self.texto_sin_resultados)
        self._reubicar()
        self.show()
