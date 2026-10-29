#feedback.py — Avisos flotantes (toast) no bloqueantes, apilables, con ✕ y botón de acción opcional.
#
#Uso:
#mostrar_toast(self, "Guardado.", "exito")
#mostrar_toast(self, "Eliminó el aula.", "exito", accion= self.deshacer, texto_accion="Deshacer")
#
#Los avisos se pegan a la esquina inferior derecha de la ventana que contiene al widget y se apilan hacia arriba.
#Se pausan mientras el cursor está encima. Un aviso con el mismo texto que otro visible no se repite.
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


# -----------------------------------------
# constantes
# -----------------------------------------
COLORES= {"exito": "#16A34A", "error": "#DC2626", "info": "#2563EB", "advertencia": "#D97706"}
ICONOS= {"exito": "✔", "error": "✖", "info": "ℹ", "advertencia": "⚠"}
MARGEN= 20
SEPARACION= 8
MAX_VISIBLES= 5

#Los avisos visibles de cada ventana
_avisos_por_ventana= {}


class _Aviso(QFrame):

    def __init__(self, ventana, texto, tipo, accion, texto_accion, duracion):

        super().__init__(ventana)
        self.ventana= ventana
        self.texto= texto
        self.setObjectName("AvisoFlotante")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QFrame#AvisoFlotante {{ background-color: {COLORES.get(tipo, COLORES['info'])}; border-radius: 10px; }}"
            "QLabel { background: transparent; color: white; font-size: 13px; font-weight: 600; }"
            "QPushButton { background: rgba(255,255,255,0.22); color: white; border: none;"
            " border-radius: 6px; padding: 4px 10px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.38); }")

        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(14, 10, 10, 10)
        disposicion.setSpacing(10)

        lbl_icono= QLabel(ICONOS.get(tipo, ""))
        disposicion.addWidget(lbl_icono)

        lbl_texto= QLabel(texto)
        lbl_texto.setWordWrap(True)
        lbl_texto.setMaximumWidth(320)
        disposicion.addWidget(lbl_texto, 1)

        if accion is not None:
            btn_accion= QPushButton(texto_accion or "Deshacer")
            btn_accion.setCursor(Qt.CursorShape.PointingHandCursor)
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            btn_accion.clicked.connect(lambda: self._usar_accion(accion))
            disposicion.addWidget(btn_accion)

        btn_cerrar= QPushButton("✕")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setFixedWidth(28)
        btn_cerrar.setAccessibleName("Cerrar aviso")
        btn_cerrar.clicked.connect(self.cerrar)
        disposicion.addWidget(btn_cerrar)

        self._temporizador= QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.timeout.connect(self.cerrar)
        self._duracion= duracion

    def mostrar(self):

        self.adjustSize()
        self.show()
        self.raise_()
        self._temporizador.start(self._duracion)

    #Se cierra primero para que el aviso no quede encima si la acción abre otro
    def _usar_accion(self, accion):

        self.cerrar()
        accion()

    #Mientras el cursor está encima el aviso no se va
    def enterEvent(self, evento):

        self._temporizador.stop()
        super().enterEvent(evento)

    def leaveEvent(self, evento):

        self._temporizador.start(1500)
        super().leaveEvent(evento)

    def cerrar(self):

        avisos= _avisos_por_ventana.get(self.ventana, [])
        if self in avisos:
            avisos.remove(self)
        self.hide()
        self.deleteLater()
        _acomodar(self.ventana)


#Reposiciona la pila entera: el más viejo abajo, los nuevos arriba
def _acomodar(ventana):

    y= ventana.height() - MARGEN
    for aviso in _avisos_por_ventana.get(ventana, []):
        aviso.adjustSize()
        y-= aviso.height()
        aviso.move(max(ventana.width() - aviso.width() - MARGEN, 0), max(y, 0))
        aviso.raise_()
        y-= SEPARACION


#Escucha el cambio de tamaño de la ventana para que los avisos sigan pegados a la esquina
class _VigilaTamano(QObject):

    def eventFilter(self, objeto, evento):

        if evento.type() == QEvent.Type.Resize:
            _acomodar(objeto)
        return False


_vigilantes= {}


def mostrar_toast(widget, texto, tipo="info", accion=None, texto_accion="", duracion=4000):

    if widget is None or not texto:
        return None

    ventana= widget if isinstance(widget, QWidget) and widget.parentWidget() is None else widget.window()
    avisos= _avisos_por_ventana.setdefault(ventana, [])

    for existente in avisos:
        if existente.texto == texto:
            existente._temporizador.start(duracion)
            return existente

    if ventana not in _vigilantes:
        vigilante= _VigilaTamano(ventana)
        ventana.installEventFilter(vigilante)
        _vigilantes[ventana]= vigilante
        #*_: el índice que trae doubleClicked no se usa; el doble clic equivale a pulsar el botón de detalle
        ventana.destroyed.connect(lambda *_: _olvidar_ventana(ventana))

    #Si hay demasiados, se descarta el más viejo
    while len(avisos) >= MAX_VISIBLES:
        avisos[0].cerrar()

    aviso= _Aviso(ventana, texto, tipo, accion, texto_accion, duracion)
    avisos.append(aviso)
    aviso.mostrar()
    _acomodar(ventana)
    return aviso


def _olvidar_ventana(ventana):

    _avisos_por_ventana.pop(ventana, None)
    _vigilantes.pop(ventana, None)
