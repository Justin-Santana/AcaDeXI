#Prueba aislada del patrón de rescate usado en observaciones.py.
#
#Reproduce el bug: un diálogo de filtros parentado a un diálogo de pantalla
#completa con WA_DeleteOnClose moría con él (y sus combos con él), dejando
#referencias Python que lanzaban RuntimeError. Aquí se valida que
#`aboutToBeDestroyed` + `setParent()` lo salva.
import sys
from PySide6.QtWidgets import QApplication, QDialog, QComboBox, QVBoxLayout
from PySide6.QtCore import Qt

app= QApplication(sys.argv)


def vivo(objeto):

    import shiboken6
    return objeto is not None and shiboken6.isValid(objeto)


class Modulo:

    def __init__(self):

        self.combo= QComboBox()
        self.combo.addItem("A", 1)
        self.dialogo= QDialog()
        lay= QVBoxLayout(self.dialogo)
        lay.addWidget(self.combo)

    def abrir(self, fc):

        if vivo(self.dialogo) and self.dialogo.parent() is not fc:
            self.dialogo.setParent(fc)
            fc.aboutToBeDestroyed.connect(self.rescatar)

    def rescatar(self, *_):

        d= self.dialogo
        if not vivo(d):
            return
        d.setParent(self)
        d.hide()


m= Modulo()
fc= QDialog()
fc.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
m.abrir(fc)
assert m.dialogo.parent() is fc
fc.deleteLater()          #mismo efecto que cerrar el diálogo de pantalla completa
app.processEvents()
assert vivo(m.dialogo), "el diálogo de filtros murió: no se rescató"
assert vivo(m.combo), "el combo murió: no se rescató"
assert m.combo.currentData() == 1
print("OK: diálogo y combo sobreviven al cierre de la pantalla completa")
