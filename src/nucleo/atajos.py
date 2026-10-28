#Sistema de Atajos de Teclado de AcaDeXI.
#
#Este módulo tiene dos responsabilidades:
#
#1) Un registro liviano de atajos por módulo (`registrar_atajo`), que crea un
#QShortcut de verdad y además "anota" el atajo en el widget para que la
#ventanita de ayuda (ver abajo) pueda mostrarlo. Cada módulo llama a esta
#función en su __init__, apuntando a un método que YA existe (el mismo que
#usa el botón correspondiente) — no se inventa lógica nueva, solo se le
#pone una tecla al lado.
#
#IMPORTANTE — MODO DOCENTE: `registrar_atajo` recibe `solo_no_docente`.
#Cuando main_window.rol_actual == "Profesor" y ese flag está en True, el
#atajo NI SIQUIERA SE CREA (no hay QShortcut, no aparece en la ventanita de
#ayuda, no queda ninguna referencia viva). Así se evita que un docente
#descubra —por la ventanita de atajos o por la propia tecla— una acción
#institucional que no debe ejecutar (borrar un estudiante, editar la
#matrícula, etc.), consistente con la separación que ya aplica
#datos_locales_docente.py para los datos "de la fuente de verdad".
#
#2) GestorAtajos: un QObject instalado como event filter de la QApplication
#que detecta cuándo el usuario MANTIENE presionada una tecla configurable
#(por defecto Alt) y, solo mientras la mantiene presionada, muestra una
#ventanita flotante y asíncrona con los atajos del módulo visible en ese
#momento. No es un QMessageBox, no bloquea nada, no roba el foco, no
#intercepta clics: es puramente informativa y desaparece sola al soltar
#la tecla.
#
#OJO CON ALT "SOLO": En Windows, tocar y soltar Alt sin combinarla con
#nada más activa el modo nativo de "mnemónicos" del sistema (el
#recuadrito/subrayado que resalta el primer control enfocable de la
#ventana). Como usamos esa misma tecla para nuestro propio gesto, hay que
#CONSUMIR (no dejar pasar) el KeyPress/KeyRelease de la tecla "pelada"
#-sin otros modificadores combinados- para que Qt no dispare ese efecto
#nativo por su cuenta. Esto NO afecta combinaciones como Alt+Tab (las
#intercepta el sistema operativo antes de que lleguen a Qt) ni mnemónicos
#reales tipo Alt+F (esos llegan como KeyPress de la tecla "F" con
#modificador Alt, no como KeyPress de la tecla Alt en sí, así que no se
#tocan).
#
#3) GestorRetroalimentacionClics: otro QObject instalado como event filter de
#la QApplication (mismo patrón que GestorAtajos, arriba) que da feedback
#visual a CUALQUIER botón de la app mientras el usuario lo tiene
#presionado. Al instalarse una sola vez a nivel de toda la aplicación,
#ningún módulo tiene que conectar nada a mano: se aplica por igual a
#todos los QPushButton/QToolButton/etc. existentes y a los que se creen
#después.
#
#Es un "mantener presionado" real, no un parpadeo que se dispara solo: al
#bajar el mouse, el botón se atenúa (opacidad más baja) y se QUEDA así
#mientras se sigue sosteniendo el clic; al soltar el mouse (o si el
#cursor se sale del botón sin soltar, que es como Qt considera cancelado
#un clic) vuelve a su opacidad normal. Reemplaza el rebote de geometría
#que antes solo tenía Sincronización (`_animar_click` en
#sincronizacion.py, que encogía y devolvía el tamaño del botón, con casos
#especiales para no ir encogiéndolo más con clics repetidos).


import time

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect,
    QApplication, QAbstractButton)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QShortcut, QKeySequence, QFont


#Teclas disponibles para activar la ventanita (configurable en Configuración) Teclas modificadoras "puras"
#(mantenerlas presionadas no escribe nada ni dispara menús del sistema operativo de forma agresiva) MÁS F1, que
#funciona igual para este gesto de "mantener para ver": no imprime texto y no tiene un efecto nativo agresivo
#en Windows/Qt al mantenerla sola (a diferencia de Alt "pelada" -ver docstring del módulo-, así que ni siquiera
#hace falta el manejo especial de mnemónicos para esta opción).
TECLAS_ATAJO_DISPONIBLES= {
    "Alt": Qt.Key.Key_Alt,
    "Ctrl": Qt.Key.Key_Control,
    "Shift": Qt.Key.Key_Shift,
    "F1": Qt.Key.Key_F1,
}
TECLA_ATAJO_POR_DEFECTO= "Alt"

#Mismo mapeo, pero como bandera de Qt.KeyboardModifier — lo usa el sondeo de respaldo de GestorAtajos, que le
#pregunta directamente al sistema operativo qué modificadores están abajo (más confiable que llevar la cuenta a
#mano de KeyPress/KeyRelease para una tecla que, sola, tiene comportamiento especial en Windows — ver docstring
#del módulo).
##F1 NO tiene bandera de Qt.KeyboardModifier (no es una tecla modificadora):
#a propósito no aparece en este diccionario. Para F1, GestorAtajos se apoya solo en KeyPress/KeyRelease (ver
#_tecla_qt_configurada y eventFilter) y en ApplicationDeactivate/WindowDeactivate para soltar el gesto si la
#ventana pierde el foco con F1 todavía abajo -sin el sondeo de respaldo, que solo aplica a las teclas de este
#diccionario-.
_MODIFICADORES_QT= {
    "Alt": Qt.KeyboardModifier.AltModifier,
    "Ctrl": Qt.KeyboardModifier.ControlModifier,
    "Shift": Qt.KeyboardModifier.ShiftModifier,
}

#Cuánto hay que mantener la tecla presionada antes de que aparezca la
#ventanita (evita que un Alt rápido y suelto -que en algunos temas de
#Windows abre el menú clásico- también dispare nuestra ventanita).
_RETARDO_APARICION_MS= 350


def _tecla_qt_configurada(main_window):

    nombre= getattr(main_window, "tecla_atajos", TECLA_ATAJO_POR_DEFECTO) or TECLA_ATAJO_POR_DEFECTO
    return TECLAS_ATAJO_DISPONIBLES.get(nombre, TECLAS_ATAJO_DISPONIBLES[TECLA_ATAJO_POR_DEFECTO])


#None para teclas sin bandera de modificador (F1): antes, al no estar
#en _MODIFICADORES_QT, este `get` caía en el modificador de Alt como
#"valor por defecto" -con F1 configurada, el sondeo de respaldo se
#hubiera puesto a preguntar si ALT estaba abajo en vez de F1, mostrando
#la ventanita con la tecla equivocada (o dejándola pegada si el usuario
#soltaba F1 pero tenía Alt presionada por otro motivo). Ahora, sin
#bandera disponible, se devuelve None explícitamente y el sondeo se
#desactiva para esa tecla (ver _sondear_estado_real: F1 depende solo de
#KeyPress/KeyRelease, que si cubre su caso -ver docstring del módulo).
def _modificador_qt_configurado(main_window):

    nombre= getattr(main_window, "tecla_atajos", TECLA_ATAJO_POR_DEFECTO) or TECLA_ATAJO_POR_DEFECTO
    if nombre not in _MODIFICADORES_QT:
        return None
    return _MODIFICADORES_QT[nombre]


#True si quien está usando la app ahora es un Profesor con acceso
#restringido (Modo Docente). Reutiliza permisos.es_profesor_restringido
#-la misma función que YA usan estudiantes.py, horario.py, profesores.py,
#etc. para decidir qué botones institucionales mostrar u ocultar- para
#que los atajos respeten EXACTAMENTE la misma regla que ya respeta el
#resto de la interfaz, en vez de definir un criterio propio y separado
#que podría desalinearse con ella.
def es_modo_docente(main_window):

    try:

        from src.nucleo.permisos import es_profesor_restringido
        return bool(es_profesor_restringido(main_window))
    except Exception:
        #Alguien podría cargar este módulo standalone (p. ej. main.py, que no pasa por permisos.py) o en un entorno de
        #pruebas sin bd; en ese caso, se cae al criterio simple del rol.
        return getattr(main_window, "rol_actual", None) == "Profesor"


#Registro de atajos por widget
#Crea un QShortcut real en `widget` que llama a `callback`, y lo deja
#anotado en `widget._atajos_registrados` para que la ventanita de ayuda
#(GestorAtajos) pueda listarlo.
#
#- secuencia: texto tipo "Ctrl+G", "F5", "Ctrl+Del", etc.
#- descripcion: texto corto en español para mostrar en la ventanita, p.ej.
#"Guardar".
#- solo_no_docente: si es True y el usuario logueado es Profesor, el
#atajo NO se crea (ver docstring del módulo). Úsese en toda acción que
#toque datos institucionales (crear/editar/eliminar registros de la
#fuente de verdad), nunca en acciones sobre datos locales del propio
#docente (horario_local, overrides de estudiantes.py, etc.).
#
#Devuelve el QShortcut creado, o None si se omitió por modo docente.
def registrar_atajo(widget, main_window, secuencia, descripcion, callback,
                     solo_no_docente= False, contexto=Qt.ShortcutContext.WidgetWithChildrenShortcut):

    if solo_no_docente and es_modo_docente(main_window):
        return None

    atajo= QShortcut(QKeySequence(secuencia), widget)
    atajo.setContext(contexto)
    atajo.activated.connect(callback)

    #Si no se pasó descripción, es un atajo "alias" (una variante de tecla
    #física de otro atajo ya anotado, p. ej. Ctrl+= junto a Ctrl++) que a
    #propósito no debe listarse aparte en la ventanita de ayuda -así lo documentan sus llamadas en
    #reportes_editor.py-. El QShortcut de todos modos se crea y funciona igual; solo se omite la anotación para que
    #atajos_de()/la ventanita no muestren una fila con la descripción vacía.
    if descripcion:
        if not hasattr(widget, "_atajos_registrados"):
            widget._atajos_registrados= []
        widget._atajos_registrados.append((secuencia, descripcion))

    return atajo


#Lista [(secuencia, descripcion), ...] ya filtrada por modo docente
#(porque los que no aplicaban nunca se agregaron).
def atajos_de(widget):

    return list(getattr(widget, "_atajos_registrados", []))


#Ventanita flotante de ayuda (asíncrona, no intrusiva)
#Panel flotante, sin bordes, que no roba foco y es transparente a los
#clics del mouse (no hay forma de "interactuar" con ella: solo se ve).
#No es un QMessageBox ni un warning: no tiene botones, no pausa nada, y
#desaparece sola en cuanto se suelta la tecla configurada.
class _VentanaAyudaAtajos(QWidget):

    def __init__(self):

        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setObjectName("VentanaAyudaAtajos")

        self._contenedor= QWidget(self)
        self._contenedor.setObjectName("PanelAyudaAtajos")
        self._contenedor.setStyleSheet("""
            #PanelAyudaAtajos {
                background-color: rgba(30, 32, 38, 235);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 40);
            }
            QLabel { color: #F1F1F3; background: transparent; }
        """)

        externo= QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.addWidget(self._contenedor)

        self._layout= QVBoxLayout(self._contenedor)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(6)

        self._titulo= QLabel("Atajos de teclado")
        f_titulo= QFont()
        f_titulo.setBold(True)
        f_titulo.setPointSize(f_titulo.pointSize() + 1)
        self._titulo.setFont(f_titulo)
        self._layout.addWidget(self._titulo)

        self._filas_widget= QWidget(self._contenedor)
        self._filas_layout= QVBoxLayout(self._filas_widget)
        self._filas_layout.setContentsMargins(0, 4, 0, 0)
        self._filas_layout.setSpacing(3)
        self._layout.addWidget(self._filas_widget)

        self._efecto= QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efecto)
        self._efecto.setOpacity(0.0)
        self._animacion= QPropertyAnimation(self._efecto, b"opacity", self)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)
        #Conectado UNA sola vez, para siempre: nunca se hace
        #connect()/disconnect() por cada aparición/desaparición (eso es lo
        #que generaba el RuntimeWarning "Failed to disconnect (None) from signal finished()" -PySide avisa igual aunque
        #esté dentro de un
        #try/except, porque es un warning, no una excepción, así que nunca
        #se podía silenciar de verdad-). En su lugar, el propio slot decide si le toca ocultar la ventana mirando hacia
        #dónde iba la animación que acaba de terminar.
        self._animacion.finished.connect(self._al_terminar_animacion)

    def _limpiar_filas(self):

        #Cada fila de atajo se agrega con addLayout(fila) (un QHBoxLayout con 2 QLabel adentro), no con addWidget.
        #takeAt(0) sobre un item
        #así devuelve item.widget() == None -el layout en sí no es un
        #widget-, así que el "if w is not None" de antes nunca entraba para esas filas: las etiquetas quedaban vivas y
        #visibles, solo desenganchadas del layout, y la próxima vez que se llamaba a
        #mostrar_atajos() (p. ej. al cambiar de módulo) las nuevas se
        #pintaban ENCIMA de las viejas -de ahí el texto entrecortado/ amontonado-. Ahora se recorre también el
        #sub-layout, borrando cada widget hijo antes de descartar el layout que los contenía.
        while self._filas_layout.count():
            item= self._filas_layout.takeAt(0)
            w= item.widget()
            if w is not None:
                w.deleteLater()
                continue
            sub= item.layout()
            if sub is not None:
                self._vaciar_layout(sub)

    def _vaciar_layout(self, disposicion):

        while disposicion.count():
            item= disposicion.takeAt(0)
            w= item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub= item.layout()
                if sub is not None:
                    self._vaciar_layout(sub)

    def mostrar_atajos(self, titulo_modulo, lista_atajos, punto_referencia):

        self._limpiar_filas()
        self._titulo.setText(f"⌨  Atajos — {titulo_modulo}" if titulo_modulo else "⌨  Atajos de teclado")

        if not lista_atajos:
            lbl= QLabel("Este módulo aún no tiene atajos.")
            lbl.setStyleSheet("color: #B7B9C2;")
            self._filas_layout.addWidget(lbl)
        else:
            for secuencia, descripcion in lista_atajos:
                fila= QHBoxLayout()
                fila.setSpacing(10)
                lbl_tecla= QLabel(secuencia)
                lbl_tecla.setStyleSheet(
                    "background-color: rgba(255,255,255,25); border-radius: 5px; "
                    "padding: 1px 7px; font-family: monospace; font-weight: bold;")
                lbl_tecla.setMinimumWidth(64)
                lbl_desc= QLabel(descripcion)
                fila.addWidget(lbl_tecla)
                fila.addWidget(lbl_desc, 1)
                self._filas_layout.addLayout(fila)

        self.adjustSize()
        self._posicionar(punto_referencia)
        self.show()
        self._animacion.stop()
        self._animacion.setDuration(120)
        self._animacion.setStartValue(self._efecto.opacity())
        self._animacion.setEndValue(1.0)
        self._animacion.start()

    def _posicionar(self, punto_referencia):

        pantalla= QApplication.primaryScreen()
        geo= pantalla.availableGeometry() if pantalla else None
        pos_x= punto_referencia.x() if punto_referencia else 40
        pos_y= punto_referencia.y() if punto_referencia else 40
        if geo is not None:
            pos_x= min(max(geo.left() + 16, pos_x), geo.right() - self.width() - 16)
            pos_y= min(max(geo.top() + 16, pos_y), geo.bottom() - self.height() - 16)
        self.move(QPoint(pos_x, pos_y))

    def ocultar_con_fundido(self):

        self._animacion.stop()
        self._animacion.setDuration(140)
        self._animacion.setStartValue(self._efecto.opacity())
        self._animacion.setEndValue(0.0)
        self._animacion.start()

    def _al_terminar_animacion(self):

        #Si la animación que acaba de terminar iba HACIA 0 (fundido de salida), recién ahí se oculta la ventana. Si iba
        #hacia 1 (fundido de entrada, ver mostrar_atajos), no se hace nada: la ventana debe seguir visible.
        if self._efecto.opacity() <= 0.0:
            self.hide()


#GESTOR: escucha la tecla configurada en TODA la aplicación
#Se instala una sola vez, como event filter de QApplication, en
#main.py. No interrumpe el flujo normal del sistema: la única tecla que
#"se queda" con nosotros es la propia tecla de activación PELADA (sin
#combinar), y solo para evitar el efecto visual nativo de mnemónicos de
#Windows (ver docstring del módulo). Cualquier otra combinación —
#incluida esa misma tecla combinada con otra— sigue su curso normal.
class GestorAtajos(QObject):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._ventana= None
        self._presionada= False
        self._timer_aparicion= QTimer(self)
        self._timer_aparicion.setSingleShot(True)
        self._timer_aparicion.timeout.connect(self._mostrar_ahora)

        #Sondeo de respaldo: vuelve a preguntarle al sistema operativo, cada poco, si la tecla configurada sigue
        #realmente abajo. Es la red de seguridad para que "mantenerse mientras se mantiene presionada" sea literal
        #incluso si, por lo que sea (la ventana perdió el foco, un diálogo modal se abrió encima, etc.), no nos llegó
        #el KeyRelease correspondiente.
        self._timer_sondeo= QTimer(self)
        self._timer_sondeo.setInterval(150)
        self._timer_sondeo.timeout.connect(self._sondear_estado_real)
        self._timer_sondeo.start()

    def eventFilter(self, objeto, evento):

        tipo= evento.type()
        if tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if evento.key() == _tecla_qt_configurada(self.main_window) and not evento.isAutoRepeat():
                #Consumimos SOLO la tecla pelada (sin otros modificadores combinados en el momento del evento) para apagar el
                #efecto nativo de mnemónicos de Windows sin tocar combinaciones reales que usen esta tecla junto con otra.
                if tipo == QEvent.Type.KeyPress:
                    if not self._presionada:
                        self._presionada= True
                        self._timer_aparicion.start(_RETARDO_APARICION_MS)
                else:
                    self._presionada= False
                    self._timer_aparicion.stop()
                    self._ocultar_ahora()
                return True
        elif tipo in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            #Si el usuario cambia de ventana con la tecla aún abajo (p.ej. Alt+Tab), soltamos el gesto para no dejar la
            #ventanita "pegada" mientras el usuario ya está en otra aplicación.
            self._presionada= False
            self._timer_aparicion.stop()
            self._ocultar_ahora()
        return False  #todo lo demás sigue su curso normal, sin interrupciones

    def _sondear_estado_real(self):

        modificador= _modificador_qt_configurado(self.main_window)
        abajo_de_verdad= bool(QApplication.keyboardModifiers() & modificador) if modificador else False
        if abajo_de_verdad and not self._presionada:
            self._presionada= True
            if not self._timer_aparicion.isActive():
                self._timer_aparicion.start(_RETARDO_APARICION_MS)
        elif not abajo_de_verdad and self._presionada:
            self._presionada= False
            self._timer_aparicion.stop()
            self._ocultar_ahora()

    #Normalmente el "módulo activo" es la página visible del stack
    #principal. Pero algunos widgets (p. ej. el editor de reportes,
    #reportes_editor.py) viven FUERA de esa página -embebidos dentro de
    #otra pestaña, o incluso en su propia ventana de pantalla completa-,
    #así que nunca son ellos mismos stack.currentWidget(). Para esos
    #casos, se sube por la cadena de padres del widget con foco real
    #buscando el ancestro más cercano que sí tenga atajos registrados
    #(registrar_atajo los deja anotados en `_atajos_registrados`); si no
    #se encuentra ninguno, se cae al comportamiento de siempre.
    def _widget_activo(self):

        foco= QApplication.focusWidget()
        w= foco
        while w is not None:
            if getattr(w, "_atajos_registrados", None):
                return w
            w= w.parentWidget()

        stack= getattr(self.main_window, "stacked_widget", None)
        return stack.currentWidget() if stack is not None else None

    def _mostrar_ahora(self):

        if not self._presionada:
            return
        widget= self._widget_activo()
        if widget is None:
            return
        lista= atajos_de(widget)
        titulo= getattr(widget, "_titulo_modulo_atajos", None) or type(widget).__name__

        if self._ventana is None:
            self._ventana= _VentanaAyudaAtajos()

        cursor_pos= self.main_window.cursor().pos() if hasattr(self.main_window, "cursor") else None
        self._ventana.mostrar_atajos(titulo, lista, cursor_pos)

    def _ocultar_ahora(self):

        if self._ventana is not None and self._ventana.isVisible():
            self._ventana.ocultar_con_fundido()

#Retroalimentación visual al presionar un botón — global, para TODA la app IMPORTANTE: en Qt,
#`widget.setGraphicsEffect(nuevo)` no solo "reemplaza" el efecto anterior -lo DESTRUYE de verdad (borra el
#objeto C++)-. Guardar
#una referencia al efecto viejo para "restaurarlo" después NO funciona:
#esa referencia queda apuntando a un objeto ya borrado, y usarla revienta con "Internal C++ object already
#deleted". Esto rompía, en concreto, la sombra de "BotonAnimado" (self._sombra en estudiantes.py, personal.py,
#profesores.py, reportes.py, universidad.py), que es un QGraphicsEffect propio y persistente para su animación
#de hover.
##Por eso este módulo NUNCA reemplaza un graphicsEffect ajeno:
#- Si el botón NO tiene ningún efecto puesto, se le pone un
#QGraphicsOpacityEffect propio de esta función (se crea y se destruye aquí mismo, nunca choca con nada de otro
#módulo).
#- Si el botón YA tiene un efecto puesto (p. ej. la sombra de
#BotonAnimado), no se toca ese efecto para nada: en su lugar se superpone un pequeño overlay semitransparente
#-un QWidget hijo, no un graphicsEffect- que aparece mientras se sostiene el clic y se quita al soltar. Cero
#interferencia con el efecto que ya tenía el botón.
#Al bajar el mouse sobre el botón: se atenúa y SE QUEDA atenuado
#mientras se sostiene, como un botón físico hundido.
def _iniciar_presion(boton):

    if getattr(boton, "_retroalim_presionado", False):
        return
    boton._retroalim_presionado= True

    if boton.graphicsEffect() is None:
        efecto= QGraphicsOpacityEffect(boton)
        efecto.setOpacity(1.0)
        boton.setGraphicsEffect(efecto)
        boton._retroalim_via_opacidad= True
        anim= QPropertyAnimation(efecto, b"opacity", boton)
        anim.setDuration(110)
        anim.setStartValue(1.0)
        anim.setEndValue(0.55)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        boton._anim_presion= anim  #evita que el recolector de basura la corte a mitad de vuelo
        anim.start()
    else:
        #El botón ya tiene su propio efecto (p. ej. la sombra de BotonAnimado): no se toca. Overlay aparte,
        #semitransparente, encima del botón -no es un graphicsEffect, así que no compite con el que ya tenía.
        boton._retroalim_via_opacidad= False
        overlay= QWidget(boton)
        overlay.setObjectName("_overlayRetroalimentacionClic")
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 60);")
        overlay.setGeometry(boton.rect())
        overlay.show()
        overlay.raise_()
        boton._overlay_presion= overlay


#Al soltar el mouse (o al cancelarse el clic, p. ej. arrastrando el
#cursor fuera del botón sin soltar): vuelve a la apariencia normal.
def _terminar_presion(boton):

    if not getattr(boton, "_retroalim_presionado", False):
        return
    boton._retroalim_presionado= False

    if getattr(boton, "_retroalim_via_opacidad", False):
        efecto= boton.graphicsEffect()
        if isinstance(efecto, QGraphicsOpacityEffect):
            anim_previa= getattr(boton, "_anim_presion", None)
            if anim_previa is not None and anim_previa.state() == QPropertyAnimation.State.Running:
                anim_previa.stop()
            anim= QPropertyAnimation(efecto, b"opacity", boton)
            anim.setDuration(110)
            anim.setStartValue(efecto.opacity())
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            def _quitar_efecto_propio():

                #Solo se quita si sigue siendo EL MISMO efecto que pusimos
                #nosotros (por si, entre medio, algo más le puso otro).
                if boton.graphicsEffect() is efecto:
                    boton.setGraphicsEffect(None)

            anim.finished.connect(_quitar_efecto_propio)
            boton._anim_presion= anim
            anim.start()
    else:
        overlay= getattr(boton, "_overlay_presion", None)
        if overlay is not None:
            overlay.deleteLater()
        boton._overlay_presion= None


#Event filter instalado UNA sola vez en la QApplication (ver
#main.py) que da el efecto "mantener presionado" de arriba a cualquier
#botón (QPushButton, QToolButton, chips, etc. -todo lo que herede de
#QAbstractButton-) de toda la aplicación.
#
#Al vivir a nivel de aplicación, ningún módulo tiene que conectar nada:
#aplica por igual a los botones que ya existen y a los que se creen
#después, sin tocar módulo por módulo.
class GestorRetroalimentacionClics(QObject):

    def eventFilter(self, objeto, evento):

        if isinstance(objeto, QAbstractButton):
            tipo= evento.type()
            if tipo == QEvent.Type.MouseButtonPress and evento.button() == Qt.MouseButton.LeftButton \
                    and objeto.isEnabled() and objeto.isVisible():
                _iniciar_presion(objeto)
            elif tipo == QEvent.Type.MouseButtonRelease:
                _terminar_presion(objeto)
            elif tipo == QEvent.Type.Leave:
                #El cursor salió del botón sin soltar el clic (lo arrastró afuera): Qt cancela el clic pero no siempre llega un
                #Release al propio botón en ese caso, así que también se restaura aquí para no dejarlo atenuado/oscurecido
                #indefinidamente.
                _terminar_presion(objeto)
            elif tipo == QEvent.Type.Resize and getattr(objeto, "_overlay_presion", None) is not None:
                #Poco común (redimensionar mientras se sostiene el clic), pero si pasa, el overlay debe seguir cubriendo el
                #botón.
                objeto._overlay_presion.setGeometry(objeto.rect())
        return super().eventFilter(objeto, evento)
