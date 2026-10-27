#Freno para que nadie pegue un documento entero dentro de un campo de texto y la ventana se quede
#pensando. En un QLineEdit se usa el límite que ya trae Qt. QTextEdit y QPlainTextEdit no tienen
#límite propio, así que se recorta el portapapeles justo antes de insertarlo: sale mucho más barato
#que dejar entrar el texto gigante y borrarlo después. Se llama una sola vez por campo, justo
#después de crearlo:
#self.in_nombre= QLineEdit()
#limitar_campo_texto(self.in_nombre, 300)
#self.in_observacion= QTextEdit()
#limitar_campo_texto(self.in_observacion, 5000)
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit

LIMITE_CAMPO_CORTO= 300    #nombre, dirección, correo, código
LIMITE_CAMPO_LARGO= 5000   #observaciones, descripciones, notas


#Se mete dentro de un QTextEdit o QPlainTextEdit y vigila que el texto no pase del límite, por dos
#caminos: recorta lo que se pega y, si el texto creció de otra forma (autocompletado, código,
#deshacer), lo corta después.
class LimitadorDeTexto:

    def __init__(self, widget, limite):

        self.widget= widget
        self.limite= limite

        #Se guarda el método de pegar original de Qt para llamarlo con el texto ya recortado y no
        #tener que rehacer todo lo que Qt hace al pegar.
        self.pegar_original= widget.insertFromMimeData
        widget.insertFromMimeData= self.pegar_recortado
        widget.textChanged.connect(self.recortar_si_se_paso)

    #Cuántos caracteres todavía caben en el campo.
    def espacio_libre(self):

        return max(0, self.limite - len(self.widget.toPlainText()))

    def pegar_recortado(self, contenido):

        libre= self.espacio_libre()

        if libre <= 0:
            return

        if contenido.hasText() and len(contenido.text()) > libre:
            recortado= QMimeData()
            recortado.setText(contenido.text()[:libre])
            self.pegar_original(recortado)
            return

        self.pegar_original(contenido)

    #Corta el texto sin avisar y sin mover el cursor más de lo necesario.
    def recortar_si_se_paso(self):

        texto= self.widget.toPlainText()

        if len(texto) <= self.limite:
            return

        cursor= self.widget.textCursor()
        posicion= cursor.position()

        #sin esto, setPlainText volvería a disparar textChanged
        self.widget.blockSignals(True)
        self.widget.setPlainText(texto[:self.limite])
        self.widget.blockSignals(False)

        cursor.setPosition(min(posicion, self.limite))
        self.widget.setTextCursor(cursor)


#Aplica el límite que corresponde según el tipo de campo. Se puede llamar dos veces sobre el mismo
#widget: la segunda vez solo cambia el límite, no agrega otro vigilante.
def limitar_campo_texto(widget, max_length=None):

    if isinstance(widget, QLineEdit):
        widget.setMaxLength(max_length or LIMITE_CAMPO_CORTO)
        return widget

    if isinstance(widget, (QTextEdit, QPlainTextEdit)):

        limite= max_length or LIMITE_CAMPO_LARGO
        limitador= getattr(widget, "limitador_de_texto", None)

        if limitador is None:
            widget.limitador_de_texto= LimitadorDeTexto(widget, limite)
        else:
            limitador.limite= limite

    return widget
