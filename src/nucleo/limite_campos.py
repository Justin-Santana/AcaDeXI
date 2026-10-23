"""Protección compartida contra pegado de textos gigantes en los campos de
AcaDeXI (QLineEdit / QTextEdit / QPlainTextEdit), para TODOS los módulos.

Es el equivalente en PySide6/Qt de `limit_entry_length()` de Neo Calculator
(ver Neo_Calculator.py): antes, pegar un bloque de texto enorme (por ejemplo,
copiar sin querer un documento completo y pegarlo en el campo "Nombre") podía
sentirse como un cuelgue de la ventana, porque Qt tenía que medir y dibujar
ese texto gigante de una sola vez, además de guardarlo tal cual en la base de
datos.

Igual que en Neo Calculator, la idea es cortar el problema ANTES de que el
texto entre al campo, no recortarlo después:

- QLineEdit: Qt ya trae soporte nativo para esto -> basta con
  `setMaxLength(...)`. Internamente Qt rechaza cualquier inserción (tecleada
  o pegada) que haría que el campo superara ese límite, así que un pegado
  gigante nunca llega a procesarse por completo.

- QTextEdit / QPlainTextEdit: estos widgets NO tienen un `setMaxLength`
  nativo (están pensados para texto largo: observaciones, descripciones,
  notas). Para ellos se instala un filtro de eventos que intercepta
  Ctrl+V/Shift+Insert/clic derecho > Pegar (`QKeySequence.Paste`) y recorta
  el CONTENIDO DEL PORTAPAPELES antes de insertarlo -no el texto ya insertado
  después-, exactamente con el mismo espíritu que el `validate="key"` de Tk
  en Neo Calculator: se evita procesar el bloque gigante, en vez de dejarlo
  entrar y borrarlo recién después. Como red de seguridad adicional (por si
  el texto crece por otra vía, ej. autocompletado o código), también se
  recorta en `textChanged` si en algún momento se pasara del límite.

Uso: una sola llamada por campo, justo después de crearlo:

    from limite_campos import limitar_campo_texto
    self.in_nombre = QLineEdit()
    limitar_campo_texto(self.in_nombre, 300)

    self.in_observacion = QTextEdit()
    limitar_campo_texto(self.in_observacion, 5000)
"""
from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
from PySide6.QtGui import QKeySequence

# Límites por defecto según el tipo de campo, usados cuando no se pasa un
# `max_length` explícito. Pensados para dejar de sobra cualquier valor real
# (nombres, direcciones, correos, notas...) sin permitir un pegado gigante.
LIMITE_CAMPO_CORTO = 300     # QLineEdit genérico (nombre, dirección, correo, código...)
LIMITE_CAMPO_LARGO = 5000    # QTextEdit/QPlainTextEdit (observaciones, descripciones, notas)


class _FiltroPegadoLargo:
    """Recorta el texto del portapapeles ANTES de insertarlo en un
    QTextEdit/QPlainTextEdit, en vez de dejar que el widget procese el
    bloque completo y recortarlo después."""

    def __init__(self, widget, max_length):
        self.widget = widget
        self.max_length = max_length
        # Se guarda el método original para poder llamarlo con el texto ya
        # recortado, sin reimplementar todo lo que hace Qt al pegar (formato,
        # imágenes en rich text, etc. -aquí solo interesa el texto plano-).
        self._insert_original = widget.insertFromMimeData
        widget.insertFromMimeData = self._insertar_recortado

    def _espacio_disponible(self):
        largo_actual = len(self.widget.toPlainText())
        return max(0, self.max_length - largo_actual)

    def _insertar_recortado(self, source):
        disponible = self._espacio_disponible()
        if disponible <= 0:
            return
        if source.hasText() and len(source.text()) > disponible:
            from PySide6.QtCore import QMimeData
            recortado = QMimeData()
            recortado.setText(source.text()[:disponible])
            self._insert_original(recortado)
        else:
            self._insert_original(source)


def _truncar_si_excede(widget, max_length):
    """Red de seguridad: si por cualquier otra vía (autocompletado, código,
    deshacer/rehacer) el contenido superara el límite, se recorta aquí."""
    texto = widget.toPlainText()
    if len(texto) > max_length:
        cursor = widget.textCursor()
        posicion = cursor.position()
        widget.blockSignals(True)
        widget.setPlainText(texto[:max_length])
        widget.blockSignals(False)
        cursor.setPosition(min(posicion, max_length))
        widget.setTextCursor(cursor)


def limitar_campo_texto(widget, max_length=None):
    """Aplica el límite de longitud adecuado según el tipo de widget.
    Es seguro llamarla más de una vez sobre el mismo widget (no duplica el
    filtro de pegado en QTextEdit/QPlainTextEdit)."""
    if isinstance(widget, QLineEdit):
        widget.setMaxLength(max_length or LIMITE_CAMPO_CORTO)
        return widget

    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        limite = max_length or LIMITE_CAMPO_LARGO
        if getattr(widget, "_limite_pegado_aplicado", None) != limite:
            _FiltroPegadoLargo(widget, limite)
            widget.textChanged.connect(lambda w=widget, l=limite: _truncar_si_excede(w, l))
            widget._limite_pegado_aplicado = limite
        return widget

    return widget
