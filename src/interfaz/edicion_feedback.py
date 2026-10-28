#Feedback visual de EDICIÓN para AcaDeXI.
#
#Provee un banner persistente ("estás editando") que se ancla automáticamente
#encima del formulario correspondiente, más un desplazamiento animado que
#lleva la vista hasta el formulario sin que el usuario mueva el scrollbar.
#
#Diseñado para ser ligero:
#- El banner se crea UNA sola vez por formulario (queda cacheado como
#propiedad del widget padre) y solo se muestra/oculta.
#- La animación de desplazamiento dura ~320 ms y solo corre al hacer clic
#en "Cargar", no consume recursos mientras está inactiva.

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer)
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QTabWidget)

from src.nucleo.iconos_emoji import pixmap_emoji

_DURACION_FADE= 220
_DURACION_SCROLL= 320
_ESPERA_SCROLL= 90  #ms: espera a que el layout asiente tras cargar datos


#Franja constante que indica que hay un registro en edición.
class BannerEdicion(QFrame):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("BannerEdicion")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(34)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)
        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji("✏", 15))
        self.lbl_icono.setFixedSize(18, 18)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_texto= QLabel("")
        self.lbl_texto.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.lbl_icono)
        lay.addWidget(self.lbl_texto)
        lay.addStretch()
        self._anim_fade= None
        self._anim_scroll= None
        self.hide()

    def activar(self, texto):

        self.lbl_texto.setText(texto)
        self._aplicar_estilo()
        if not self.isVisible():
            self.show()
            #Fundido de entrada (una sola vez por activación, muy barato)
            try:

                from PySide6.QtWidgets import QGraphicsOpacityEffect
                efecto= QGraphicsOpacityEffect(self)
                self.setGraphicsEffect(efecto)
                anim= QPropertyAnimation(efecto, b"opacity", self)
                anim.setDuration(_DURACION_FADE)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.finished.connect(lambda: self.setGraphicsEffect(None))
                anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
                self._anim_fade= anim
            except Exception:
                self.setGraphicsEffect(None)

    def desactivar(self):

        self.hide()

    def changeEvent(self, evento):

        super().changeEvent(evento)
        #_aplicar_estilo() se llamaba solo desde activar() -al mostrar el
        #banner por primera vez para un formulario-, así que si el usuario cambiaba de tema con el banner YA abierto
        #(formulario en edición mientras se togglea modo claro/oscuro), el color se quedaba congelado con el que tenía
        #al momento de aparecer, aunque el resto de la app sí se hubiera puesto al día.
        ##Cuando main_window cambia de tema, aplica un nuevo stylesheet sobre sí misma (ver main.py ▸
        #_aplicar_estilos_globales_tema), y Qt propaga eso como un StyleChange también hacia los descendientes -aunque,
        #como este banner, tengan su propio stylesheet puesto-, para que puedan recalcular lo que dependa de reglas
        #heredadas. Enganchando ese evento, el banner se repinta solo, sin que main.py (ni cada módulo con un
        #formulario) tenga que acordarse de este widget en particular.
        ##Guard de reentrancia: _aplicar_estilo() llama a self.setStyleSheet(), que a su vez DISPARA otro StyleChange
        #sobre sí mismo -sin este guard, quedaría llamándose a sí mismo sin parar.
        if evento.type() in (QEvent.Type.StyleChange, QEvent.Type.PaletteChange):
            if not getattr(self, "_actualizando_estilo_por_tema", False):
                self._actualizando_estilo_por_tema= True
                try:

                    self._aplicar_estilo()
                finally:
                    self._actualizando_estilo_por_tema= False

    def _aplicar_estilo(self):

        #Antes se tomaba el color de texto de self.palette().color(WindowText), asumiendo que reflejaría el tema activo
        #-pero un QFrame anclado dentro de un formulario no siempre hereda una paleta actualizada al
        #vuelo (ver el mismo problema que resuelve formato_hora.py subiendo
        #la cadena de padres en vez de confiar en la paleta local), así que en modo oscuro el texto podía quedar oscuro
        #sobre el fondo azulado translúcido del banner -difícil de leer-. Ahora se sube por la cadena de padres
        #buscando main_window.modo_oscuro directamente (la misma fuente de verdad que usa el resto de la app para
        #pintar sus temas), y se fija el color en consecuencia: blanco en modo oscuro, negro en modo claro -igual que
        #el resto de "etiquetas planas" de la app (ver main_window._aplicar_estilos_globales_tema,
        #"color_etiqueta_plana")-. El texto además pasa a bold (antes 600, ahora 700) para que el banner se note más de
        #un vistazo -el color solo no bastaba para que resaltara lo suficiente sobre el fondo-.
        color_txt= "#FFFFFF" if self._modo_oscuro_activo() else "#000000"
        self.setStyleSheet(f"""
            QFrame#BannerEdicion {{
                background-color: rgba(37, 99, 235, 0.10);
                border: 1px solid rgba(37, 99, 235, 0.45);
                border-radius: 8px;
            }}
            QFrame#BannerEdicion QLabel {{
                color: {color_txt};
                background: transparent;
                border: none;
            }}
        """)
        self.lbl_texto.setStyleSheet(f"color: {color_txt}; font-weight: 700;")

    #Sube por la cadena de padres reales del widget (no por
    #main_window/parentWidget encadenados a mano, sino directamente
    #parentWidget() -el banner vive insertado dentro del layout del
    #propio formulario-) buscando el primer ancestro con un atributo
    #`modo_oscuro` (main_window lo tiene siempre). Si no se encuentra
    #ninguno -banner huérfano, o llamado antes de insertarse en un
    #árbol real-, se cae a la paleta activa como respaldo, igual que
    #antes.
    def _modo_oscuro_activo(self):

        vistos= set()
        actual= self.parentWidget()
        while actual is not None and id(actual) not in vistos:
            vistos.add(id(actual))
            if hasattr(actual, "modo_oscuro"):
                return bool(actual.modo_oscuro)
            actual= actual.parentWidget()
        #Respaldo: como antes, se infiere del brillo del color de texto que trae la paleta activa (si es un color
        #claro, se asume tema oscuro de fondo).
        return self.palette().color(QPalette.ColorRole.WindowText).lightness() > 128


#True si `lay` (o un layout anidado) contiene directamente `widget`.
def _contiene(lay, widget, prof=0):

    if lay is None or prof > 4:
        return False
    for i in range(lay.count()):
        it= lay.itemAt(i)
        if it.widget() is widget:
            return True
        if it.layout() is not None and _contiene(it.layout(), widget, prof + 1):
            return True
    return False


def _banner_de(widget):

    b= widget.property("_banner_edicion")
    return b if isinstance(b, BannerEdicion) else None


#Devuelve el banner del formulario de `ancla`, creándolo la primera vez
#e insertándolo justo encima de la fila de botones del formulario.
def anclar_banner(ancla):

    padre= ancla.parentWidget() or ancla
    b= _banner_de(padre)
    if b is not None:
        return b
    b= BannerEdicion()
    lay= padre.layout()
    colocado= False
    if lay is not None:
        for i in range(lay.count()):
            it= lay.itemAt(i)
            if it.widget() is ancla or (it.layout() is not None
                                        and _contiene(it.layout(), ancla)):
                lay.insertWidget(i, b)
                colocado= True
                break
        if not colocado:
            lay.insertWidget(0, b)
    else:
        b.setParent(padre)
    b.hide()
    padre.setProperty("_banner_edicion", b)
    return b


def _es_descendiente(hijo, ancestro):

    w= hijo
    while w is not None:
        if w is ancestro:
            return True
        w= w.parentWidget()
    return False


#Recorre TODOS los ancestros del banner y, para cada uno que sea un
#QTabWidget cambia a la pestaña que lo contiene, y para cada QScrollArea
#(puede haber scrolls anidados) desplaza su barra vertical hasta dejar el
#banner visible arriba. Devuelve True si ya no queda nada por desplazar
#(todo en su sitio y con la geometría asentada).
def _desplazar_todo(banner, animado):

    en_sitio= True
    anims= []
    actual= banner.parentWidget()
    saltos= 0
    while actual is not None and saltos < 15:
        if isinstance(actual, QTabWidget):
            for i in range(actual.count()):
                if _es_descendiente(banner, actual.widget(i)):
                    if actual.currentIndex() != i:
                        actual.setCurrentIndex(i)
                        en_sitio= False  #geometría recién cambiada
                    break
        elif isinstance(actual, QScrollArea):
            contenido= actual.widget()
            if contenido is not None:
                try:

                    destino= banner.mapTo(contenido, QPoint(0, 0)).y() - 14
                except RuntimeError:
                    return False
                bar= actual.verticalScrollBar()
                destino= max(0, min(destino, bar.maximum()))
                if bar.value() != destino:
                    en_sitio= False
                    if animado:
                        anim= QPropertyAnimation(bar, b"value", banner)
                        anim.setDuration(_DURACION_SCROLL)
                        anim.setStartValue(bar.value())
                        anim.setEndValue(destino)
                        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
                        anims.append(anim)
                    else:
                        bar.setValue(destino)
        actual= actual.parentWidget()
        saltos += 1
    if anims:
        banner._anim_scroll= anims[0]
    return en_sitio


#Lleva la vista (tab activa + TODOS los scrolls ancestros) hasta el
#banner, animado, y con verificación/reintentos posteriores: el layout
#puede seguir moviéndose un rato (combos repoblados, tarjetas que crecen),
#así que se corrige al instante en varios pases hasta que ya no quede
#nada por ajustar.
def _desplazar_hasta(banner, _pase=0):

    _desplazar_todo(banner, animado=True)
    #Pases de corrección (sin animación): cubren tanto el final de la propia animación de scroll como cualquier
    #reacomodo tardío del layout.
    for retardo in (400, 800, 1400):
        QTimer.singleShot(retardo, lambda: _desplazar_todo(banner, animado=False))


#Despliega cualquier panel colapsable (PanelDesplegable o equivalente:
#cualquier ancestro con `expandir()` y `_expandido=False`) que contenga al
#formulario del `ancla`. Así, en TODOS los módulos, al darle a "editar" se
#abre el formulario aunque el panel esté cerrado —igual que ya hacía
#Observaciones a mano—. Es idempotente: si el módulo ya lo expandió antes
#de llamarnos (o ya estaba abierto), no toca nada y no re-anima.
#
#Devuelve True si expandió al menos uno (el scroll debe esperar a que
#termine la animación de apertura antes de calcular el destino).
def _expandir_paneles_ancestros(ancla):

    expandido= False
    w= ancla.parentWidget()
    saltos= 0
    while w is not None and saltos < 15:
        expandir= getattr(w, "expandir", None)
        if callable(expandir) and getattr(w, "_expandido", None) is False:
            try:

                #animar=False: al llegar aquí por "editar", el panel se abre
                #DE GOLPE. Con la animación de apertura (260 ms de maximumHeight) el contenido se ve entrecortado/recortado
                #mientras crece, y además obligaba a esperar antes de poder scrollear con destino confiable.
                try:

                    expandir(True, animar=False)
                except TypeError:
                    expandir(True)  #variante sin parámetro `animar`
                expandido= True
            except Exception:
                pass
        w= w.parentWidget()
        saltos += 1
    return expandido


#Muestra el banner "Editando: ..." sobre el formulario de `ancla`,
#despliega el panel colapsable que lo contenga (si está cerrado) y
#desplaza la vista hacia él. Pensado para llamarse al final de cada
#`_cargar_*_seleccionada()`.
def activar_modo_edicion(ancla, texto):

    if ancla is None:
        return
    _expandir_paneles_ancestros(ancla)
    banner= anclar_banner(ancla)
    banner.activar(texto)
    #El desplazamiento se difiere un instante para que el layout ya haya asentado los cambios del formulario
    #(combos repoblados, panel que se acaba de abrir DE GOLPE, etc.). La corrección post-animación de
    #_desplazar_hasta cubre cualquier reacomodo tardío que quede.
    QTimer.singleShot(_ESPERA_SCROLL, lambda: _desplazar_hasta(banner))


#Oculta el banner al limpiar/guardar el formulario.
def desactivar_modo_edicion(ancla):

    if ancla is None:
        return
    padre= ancla.parentWidget()
    if padre is None:
        return
    b= _banner_de(padre)
    if b is not None:
        b.desactivar()
