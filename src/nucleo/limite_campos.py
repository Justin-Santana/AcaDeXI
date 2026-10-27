#Freno para que nadie pegue un documento entero dentro de un campo de texto y la ventana se
#quede pensando. En QLineEdit se usa el límite que ya trae Qt; en QTextEdit/QPlainTextEdit, que
#no tienen límite propio, se recorta el portapapeles antes de insertarlo, que sale mucho más
#barato que dejar entrar el texto gigante y borrarlo después. Se llama una sola vez por campo,
#justo después de crearlo:
#self.in_nombre= QLineEdit()
#limitar_campo_texto(self.in_nombre, 300)
#self.in_observacion= QTextEdit()
#limitar_campo_texto(self.in_observacion, 5000)
from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit

LIMITE_CAMPO_CORTO= 300    #nombre, dirección, correo, código
LIMITE_CAMPO_LARGO= 5000   #observaciones, descripciones, notas


#Se mete dentro del widget y recorta el texto del portapapeles antes de que Qt lo inserte.
class _FiltroPegadoLargo:

    def __init__(self, widget, limite):
        self.widget= widget
        self.limite= limite
        #Se guarda el método original para llamarlo con el texto ya recortado y no tener que
        #rehacer todo lo que hace Qt al pegar.
        self.insertar_original= widget.insertFromMimeData
        widget.insertFromMimeData= self.insertar_recortado

    #Cuántos caracteres todavía caben en el campo.
    def espacio_libre(self):
        return max(0, self.limite - len(self.widget.toPlainText()))

    def insertar_recortado(self, source):
        libre= self.espacio_libre()
        if libre <= 0:
            return
        if source.hasText() and len(source.text()) > libre:
            from PySide6.QtCore import QMimeData
            recortado= QMimeData()
            recortado.setText(source.text()[:libre])
            self.insertar_original(recortado)
            return
        self.insertar_original(source)


#Red de seguridad: si el texto creció por otra vía (autocompletado, código, deshacer), se recorta
#acá sin avisar y sin mover el cursor más de la cuenta.
def _truncar_si_excede(widget, limite):
    texto= widget.toPlainText()
    if len(texto) <= limite:
        return
    cursor= widget.textCursor()
    posicion= cursor.position()
    widget.blockSignals(True)
    widget.setPlainText(texto[:limite])
    widget.blockSignals(False)
    cursor.setPosition(min(posicion, limite))
    widget.setTextCursor(cursor)


#Aplica el límite que corresponde según el tipo de campo. Se puede llamar dos veces sobre el
#mismo widget sin que se duplique nada.
def limitar_campo_texto(widget, max_length=None):
    if isinstance(widget, QLineEdit):
        widget.setMaxLength(max_length or LIMITE_CAMPO_CORTO)
        return widget
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        limite= max_length or LIMITE_CAMPO_LARGO
        if getattr(widget, "_limite_pegado_aplicado", None) != limite:
            _FiltroPegadoLargo(widget, limite)
            widget.textChanged.connect(lambda w=widget, l=limite: _truncar_si_excede(w, l))
            widget._limite_pegado_aplicado= limite
        return widget
    return widget
