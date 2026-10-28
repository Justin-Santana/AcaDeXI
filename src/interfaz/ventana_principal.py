import sys
import json
import os
import math
from importlib import import_module
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QLabel,
    QPushButton, QFrame, QMessageBox, QLineEdit, QGraphicsOpacityEffect, QMenu,
    QSystemTrayIcon, QWidgetAction, QToolTip)
from PySide6.QtCore import (Qt, QTimer, QEventLoop, QRect, QRectF, QPropertyAnimation,
    QVariantAnimation, QEasingCurve, QSequentialAnimationGroup, Signal, Property,
    QTranslator, QLibraryInfo, QLocale, QSharedMemory, QEvent, QObject,
    qInstallMessageHandler, QtMsgType)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QPainter, QColor, QBrush, QPixmap, QPainterPath, QPen, QPalette, QIcon

from src.nucleo.bd import obtener_carpeta_datos, obtener_conexion, registrar_auditoria, ejecutar_backup_automatico_al_iniciar, ejecutar_backup_al_cerrar, inicializar_bd
from src.servicios.alarmas import MotorAlarmas
from src.interfaz.foto_utils import seleccionar_y_recortar_foto
from src.nucleo.edicion import edicion_actual
from src.interfaz.configuracion import ModuloConfiguracion, WizardConfiguracion, _fundido_entrada
from src.inicio.login import LoginWindow
from src.inicio.bienvenida import mostrar_bienvenida_animada, _pixmap_logo_base
from src.inicio.tutoriales import ofrecer_tutoriales_tras_login
from src.nucleo.iconos import icono_app, aplicar_icono_ventana, mostrar_mensaje, pixmap_icono_sidebar
from src.nucleo.permisos import modulo_visible, ROLES_GERENCIALES, obtener_preferencia_calif_tecnicas
from src.interfaz.buscador_global import DialogoBusquedaGlobal
from src.nucleo.atajos import GestorAtajos, registrar_atajo, TECLAS_ATAJO_DISPONIBLES, TECLA_ATAJO_POR_DEFECTO,\
    GestorRetroalimentacionClics
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, establecer_modo_oscuro

CONFIG_PATH= os.path.join(obtener_carpeta_datos(), "config.json")

#Los módulos de trabajo se construyen bajo demanda. Importarlos todos al arrancar anulaba ese beneficio: Python
#tenía que leer y ejecutar cada uno antes de poder mostrar el login, aunque el usuario no llegara a abrirlos.
#El caché conserva exactamente una clase por módulo durante el proceso; solo difiere ese trabajo hasta el mismo
#instante en que se crea su página.
_FABRICAS_MODULOS= {
    "Dashboard": ("src.interfaz.dashboard", "ModuloDashboard"),
    "Estudiantes": ("src.modulos.estudiantes", "ModuloEstudiantes"),
    "Profesores": ("src.modulos.profesores", "ModuloProfesores"),
    "Personal": ("src.modulos.personal", "ModuloPersonal"),
    "Materias": ("src.modulos.materias", "ModuloMaterias"),
    "Asistencia": ("src.modulos.asistencia", "ModuloAsistencia"),
    "Calificaciones": ("src.modulos.calificaciones", "ModuloCalificaciones"),
    "Politécnico": ("src.modulos.politecnico", "ModuloPolitecnico"),
    "Calificaciones Técnicas": ("src.modulos.calificaciones_tecnicas", "ModuloCalificacionesTecnicas"),
    "Universidad": ("src.modulos.universidad", "ModuloUniversidad"),
    "Reportes": ("src.modulos.reportes", "ModuloReportes"),
    "Mis Materias": ("src.modulos.docente", "ModuloMisMaterias"),
    "Mis Estudiantes": ("src.modulos.estudiantes", "ModuloEstudiantes"),
    "Copias de Seguridad": ("src.modulos.docente", "ModuloCopiasSeguridadDocente"),
    "Sincronización": ("src.sincronizacion.sincronizacion", "ModuloSincronizacion"),
    "Banco de Tareas": ("src.modulos.banco_tareas", "ModuloBancoTareas"),
    "Secuencias Didácticas": ("src.modulos.secuencias", "ModuloSecuenciasDidacticas"),
    "Horario": ("src.modulos.horario", "ModuloHorario"),
    "Calendario": ("src.modulos.calendario", "ModuloCalendario"),
    "Observaciones": ("src.modulos.observaciones", "ModuloObservaciones"),
    "Psicología": ("src.modulos.psicologia", "ModuloPsicologia"),
    "Materiales": ("src.modulos.materiales", "ModuloMateriales"),
}
#Registro APARTE (no se mezcla con _FABRICAS_MODULOS) para la edición Single Teacher: los nombres de módulo se
#repiten ("Estudiantes", "Materias"...) pero apuntan a clases DISTINTAS -las de single_teacher_ui.py,
#conectadas a bd_single_teacher.py, no a bd.py-. Mantenerlos en diccionarios separados evita que una edición
#pise el caché de fábricas de la otra si alguna vez ambas coexistieran en el mismo proceso (pruebas).
_FABRICAS_MODULOS_SINGLE_TEACHER= {
    "Dashboard": ("src.interfaz.single_teacher_ui", "ModuloDashboardST"),
    "Estudiantes": ("src.interfaz.single_teacher_ui", "ModuloEstudiantesST"),
    "Materias": ("src.interfaz.single_teacher_ui", "ModuloMateriasST"),
    "Asistencia": ("src.interfaz.single_teacher_ui", "ModuloAsistenciaST"),
    "Calificaciones": ("src.interfaz.single_teacher_ui", "ModuloCalificacionesST"),
    "Banco de Tareas": ("src.interfaz.single_teacher_ui", "ModuloBancoTareasST"),
    "Secuencias Didácticas": ("src.modulos.secuencias_st", "ModuloSecuenciasST"),
    "Horario": ("src.interfaz.single_teacher_ui", "ModuloHorarioST"),
    "Observaciones": ("src.interfaz.single_teacher_ui", "ModuloObservacionesST"),
    "Reportes": ("src.interfaz.single_teacher_ui", "ModuloReportesST"),
    "Configuración": ("src.interfaz.single_teacher_ui", "ModuloConfiguracionST"),
}
_cache_fabricas_modulos= {}
_cache_fabricas_modulos_single_teacher= {}


#Resuelve y memoriza la clase de una página de navegación. Ramifica
#por edición ANTES que nada: "Configuración" es la única excepción
#compartida por full/docentes/side_stepper (usa siempre
#ModuloConfiguracion institucional), pero Single Teacher tiene su propia
#"Configuración" también -así que ese caso especial se resuelve primero
#dentro de la rama single_teacher, no fuera de ella.
def _obtener_fabrica_modulo(nombre):

    if edicion_actual() == "single_teacher":
        fabrica= _cache_fabricas_modulos_single_teacher.get(nombre)
        if fabrica is not None:
            return fabrica
        especificacion= _FABRICAS_MODULOS_SINGLE_TEACHER.get(nombre)
        if especificacion is None:
            return None
        modulo, clase= especificacion
        fabrica= getattr(import_module(modulo), clase)
        _cache_fabricas_modulos_single_teacher[nombre]= fabrica
        return fabrica
    if nombre == "Configuración":
        return ModuloConfiguracion
    fabrica= _cache_fabricas_modulos.get(nombre)
    if fabrica is not None:
        return fabrica
    especificacion= _FABRICAS_MODULOS.get(nombre)
    if especificacion is None:
        return None
    modulo, clase= especificacion
    fabrica= getattr(import_module(modulo), clase)
    _cache_fabricas_modulos[nombre]= fabrica
    return fabrica

#Instancia única Sin esto, abrir el acceso directo dos veces (doble clic accidental, "Abrir al iniciar sesión
#de Windows" + acceso directo manual, etc.) lanza dos procesos completos de AcaDeXI, cada uno con su propio
#icono de bandeja: por eso a veces se ven 2 iconos, y cuando uno de los dos procesos termina (o Windows repinta
#la bandeja) uno de ellos "se desvanece" sin que el usuario haya hecho nada. También duplica el consumo de
#RAM/CPU en segundo plano, que es justo lo que no queremos si la app va a vivir minimizada a la bandeja.
#
#QSharedMemory actúa como candado: el primer proceso lo reserva y lo mantiene mientras viva; si el proceso
#muere (incluso por un crash), el sistema operativo libera el segmento automáticamente, así que no deja un
#"candado fantasma" que impida volver a abrir la app.
#
#QLocalServer/QLocalSocket es el canal para que, si alguien intenta abrir una segunda copia, en vez de arrancar
#en silencio (o abortar sin decir nada) se le pida a la instancia YA abierta que se restaure y se traiga al
#frente, que es lo que el usuario espera.
_ID_INSTANCIA_UNICA= "AcaDeXI-instancia-unica-a3f9c2"


#Garantiza que solo haya un proceso de AcaDeXI corriendo a la vez.
class GuardaInstanciaUnica:

    def __init__(self):

        self.shared_memory= QSharedMemory(_ID_INSTANCIA_UNICA)
        self.local_server= None
        self._al_segunda_instancia= None

        #attach() de prueba: si logra adjuntarse es que YA existe un
        #segmento válido de otro proceso vivo. En algunos sistemas (notablemente Linux tras un crash) el segmento puede
        #quedar huérfano; intentar adjuntarse y luego soltarlo lo limpia antes de crear el nuestro, evitando falsos "ya
        #está abierto".
        if self.shared_memory.attach():
            self.shared_memory.detach()

        self.es_primera_instancia= self.shared_memory.create(1)

    #Le pide a la instancia ya corriendo que se restaure. Devuelve
    #True si logró contactarla.
    def avisar_instancia_existente(self):

        socket= QLocalSocket()
        socket.connectToServer(_ID_INSTANCIA_UNICA)
        conectado= socket.waitForConnected(500)
        if conectado:
            socket.write(b"restaurar")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
        return conectado

    #Levanta un servidor local para que, si alguien más intenta
    #abrir la app, esta instancia (la única viva) reciba el aviso y
    #se restaure en primer plano.
    def escuchar_segundas_instancias(self, callback_restaurar):

        self._al_segunda_instancia= callback_restaurar
        #Por si quedó un servidor huérfano de una ejecución anterior que terminó mal (crash) sin poder cerrarlo
        #correctamente.
        QLocalServer.removeServer(_ID_INSTANCIA_UNICA)
        self.local_server= QLocalServer()
        self.local_server.newConnection.connect(self._manejar_conexion)
        self.local_server.listen(_ID_INSTANCIA_UNICA)

    def _manejar_conexion(self):

        socket= self.local_server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._leer_y_restaurar(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _leer_y_restaurar(self, socket):

        socket.readAll()
        if callable(self._al_segunda_instancia):
            self._al_segunda_instancia()


def _hex_a_rgba(hex_color, alpha):

    hex_color= hex_color.lstrip("#")
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Punto circular animado (respira) que indica sesión activa.
class PuntoEstado(QWidget):

    def __init__(self, color="#22C55E", diametro=10, parent=None):

        super().__init__(parent)
        self._color= QColor(color)
        self._diametro= diametro
        self.setFixedSize(diametro, diametro)
        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(1.0)
        self.setGraphicsEffect(self._efecto)

        self._anim= QSequentialAnimationGroup(self)
        subir= QPropertyAnimation(self._efecto, b"opacity")
        subir.setStartValue(0.35)
        subir.setEndValue(1.0)
        subir.setDuration(900)
        subir.setEasingCurve(QEasingCurve.Type.InOutSine)
        bajar= QPropertyAnimation(self._efecto, b"opacity")
        bajar.setStartValue(1.0)
        bajar.setEndValue(0.35)
        bajar.setDuration(900)
        bajar.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.addAnimation(subir)
        self._anim.addAnimation(bajar)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def poner_color(self, color):

        self._color= QColor(color)
        self.update()

    #Detiene la animación de 'respiración'. Se usa cuando la ventana
    #está oculta (minimizada a la bandeja) para que Qt deje de recalcular
    #opacidad y repintar este widget ~2 veces por segundo indefinidamente
    #en segundo plano: es CPU/GPU gastada en algo que nadie puede ver.
    def pausar(self):

        if self._anim.state() == QSequentialAnimationGroup.State.Running:
            self._anim.pause()

    #Reactiva la animación al volver a mostrar la ventana.
    def reanudar(self):

        if self._anim.state() == QSequentialAnimationGroup.State.Paused:
            self._anim.resume()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(0, 0, self._diametro, self._diametro)


#Interruptor deslizante ☀️/🌙 hecho a mano, con animación de arrastre.
class InterruptorTema(QWidget):

    clicked= Signal()

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(56, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._encendido= False  #True = modo oscuro
        self._pos_knob= 3.0
        self._color_track_on= QColor("#4F46E5")
        self._color_track_off= QColor("#CBD5E1")
        self._anim= QPropertyAnimation(self, b"posKnob")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _leer_pos_knob(self):

        return self._pos_knob

    def _poner_pos_knob(self, valor):

        self._pos_knob= valor
        self.update()

    posKnob= Property(float, _leer_pos_knob, _poner_pos_knob)

    def poner_encendido(self, encendido, animar=True):

        self._encendido= encendido
        destino= 31.0 if encendido else 3.0
        if animar:
            self._anim.stop()
            self._anim.setStartValue(self._pos_knob)
            self._anim.setEndValue(destino)
            self._anim.start()
        else:
            self._poner_pos_knob(destino)

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(evento)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_color= self._color_track_on if self._encendido else self._color_track_off
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        painter.setBrush(QBrush(QColor("#FFFFFF")))
        knob_d= 22
        painter.drawEllipse(int(self._pos_knob), 3, knob_d, knob_d)

        #Ícono dibujado a mano (sol/luna) en vez de un emoji de texto: así se ve SIEMPRE igual sin importar la fuente
        #de emojis instalada en cada equipo (ver el problema con main_antiguo_pero_con_modo_correcto.py).
        painter.setPen(Qt.PenStyle.NoPen)
        centro_x= self._pos_knob + knob_d / 2
        centro_y= 3 + knob_d / 2
        if self._encendido:
            self._dibujar_luna(painter, centro_x, centro_y, "#4338CA")
        else:
            self._dibujar_sol(painter, centro_x, centro_y, "#F59E0B")

    def _dibujar_sol(self, painter, cx, cy, color):

        radio_nucleo= 5.0
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(QRectF(cx - radio_nucleo, cy - radio_nucleo, radio_nucleo * 2, radio_nucleo * 2))
        pen= QPen(QColor(color))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        radio_interno, radio_externo= 7.0, 9.5
        for i in range(8):
            angulo= (math.pi / 4) * i
            x1= cx + radio_interno * math.cos(angulo)
            y1= cy + radio_interno * math.sin(angulo)
            x2= cx + radio_externo * math.cos(angulo)
            y2= cy + radio_externo * math.sin(angulo)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _dibujar_luna(self, painter, cx, cy, color):

        radio= 7.5
        path_luna= QPainterPath()
        path_luna.addEllipse(QRectF(cx - radio, cy - radio, radio * 2, radio * 2))
        path_sombra= QPainterPath()
        desplazamiento= 3.2
        path_sombra.addEllipse(QRectF(cx - radio + desplazamiento, cy - radio, radio * 2, radio * 2))
        path_creciente= path_luna.subtracted(path_sombra)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        painter.drawPath(path_creciente)


#Fila de navegación con chip de icono, texto y encabezado de sección opcional.
class ModuloNavItem(QWidget):

    activado= Signal(int)

    def __init__(self, indice, icono, nombre, eyebrow=None, parent=None):

        super().__init__(parent)
        self.indice= indice
        self.nombre= nombre
        self._activo= False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ModuloNavItem")

        raiz= QVBoxLayout(self)
        raiz.setContentsMargins(14, 6 if eyebrow else 3, 10, 3)
        raiz.setSpacing(2)

        self.lbl_eyebrow= None
        if eyebrow:
            self.lbl_eyebrow= QLabel(eyebrow)
            self.lbl_eyebrow.setObjectName("SeccionEyebrow")
            raiz.addWidget(self.lbl_eyebrow)

        fila= QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(12)

        self.lbl_icono= QLabel()
        self.lbl_icono.setObjectName("NavIconChip")
        self.lbl_icono.setFixedSize(34, 34)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #Icono real (PNG en iconos/sidebar_icons, ver iconos.py) en vez del emoji histórico. Si el módulo todavía no
        #tiene un archivo propio
        #ahí (ver ALIAS_ICONOS_SIDEBAR), se usa el icono VECTORIAL
        #coherente (mismo dibujo que usan los botones de ese módulo, ver
        #iconos_auto.py) en vez de texto de emoji suelto, para que la fila nunca se quede sin icono ni dependa de la
        #fuente de emojis del sistema operativo.
        _pixmap_nav= pixmap_icono_sidebar(nombre, tamano=26)
        if _pixmap_nav is not None:
            self.lbl_icono.setPixmap(_pixmap_nav)
        else:
            from src.nucleo.iconos_auto import icono_para_texto
            _icono_vectorial= icono_para_texto(nombre)
            if not _icono_vectorial.isNull():
                self.lbl_icono.setPixmap(_icono_vectorial.pixmap(26, 26))
            else:
                self.lbl_icono.setText(icono)
        fila.addWidget(self.lbl_icono)

        self.lbl_texto= QLabel(nombre)
        self.lbl_texto.setObjectName("NavTexto")
        fila.addWidget(self.lbl_texto, 1)

        raiz.addLayout(fila)

        self.setLayout(raiz)

    def poner_activo(self, activo):

        self._activo= activo
        self.lbl_icono.setProperty("activo", activo)
        self.lbl_texto.setProperty("activo", activo)
        for w in (self.lbl_icono, self.lbl_texto):
            w.style().unpolish(w)
            w.style().polish(w)

    def poner_colapsado(self, colapsado):

        self.lbl_texto.setVisible(not colapsado)
        if self.lbl_eyebrow is not None:
            self.lbl_eyebrow.setVisible(not colapsado)
        self.setToolTip(self.nombre if colapsado else "")

    def mousePressEvent(self, evento):

        if evento.button() == Qt.MouseButton.LeftButton:
            self.activado.emit(self.indice)
        super().mousePressEvent(evento)


#QStackedWidget normal, pero con una corrección a un comportamiento
#poco conocido de Qt: por defecto, sizeHint()/minimumSizeHint() de un
#QStackedWidget se calculan como el máximo entre TODAS las páginas que
#alguna vez se agregaron al stack, no solo la que está visible. Como
#main.py carga los módulos de forma perezosa (ver
#`_asegurar_modulo_cargado`), la primera vez que se entra a un módulo
#con un contenido ancho (p. ej. un formulario con varios combos), ese
#módulo se inserta al stack y desde ese momento su ancho mínimo queda
#"contaminando" el ancho mínimo de TODA la ventana —incluida la
#sidebar— aunque luego se navegue a otro módulo más angosto. Eso es lo
#que producía el desajuste de resolución reportado al entrar a Banco de
#Tareas.
#Esta subclase hace que el tamaño reportado dependa únicamente de la
#página actualmente visible, y se refresca (updateGeometry) cada vez
#que cambia de página.
class StackedWidgetTamanoActual(QStackedWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):

        w= self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):

        w= self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


#Spinner circular animado, dibujado a mano con QPainter (sin depender
#de ningún ícono/gif externo), que se usa como contenido de los
#placeholders "Cargando…" de módulos y pestañas perezosas.
#
#La animación sigue el patrón "Material Design" de progreso indeterminado:
#el arco no gira con largo fijo, sino que crece y encoge mientras rota
#-se ve vivo/pulido en vez de un simple manecilla dando vueltas-. Quien
#lo use debe llamar a `.detener()` justo antes de reemplazarlo/descartarlo.
class IndicadorCargaGiratorio(QWidget):

    _DURACION_CICLO_MS= 1400  #una vuelta completa de "crece + encoge"
    _LARGO_MIN= 22   #grados
    _LARGO_MAX= 300  #grados

    def __init__(self, texto="Cargando…", color="#4F8EF7", color_texto="#8A94A6", parent=None):

        super().__init__(parent)
        self._color= QColor(color)
        self._color_texto= QColor(color_texto)
        self._texto= texto
        self._transcurrido_ms= 0
        self.setMinimumHeight(140)
        self._timer= QTimer(self)
        self._timer.timeout.connect(self._avanzar)
        self._timer.start(16)  #~60 fps

    def detener(self):

        self._timer.stop()

    def hideEvent(self, evento):

        #Si el widget queda oculto (p. ej. otra pestaña al frente) no hace falta seguir gastando CPU animando algo que
        #nadie ve.
        self._timer.stop()
        super().hideEvent(evento)

    def showEvent(self, evento):

        if not self._timer.isActive():
            self._timer.start(16)
        super().showEvent(evento)

    def _avanzar(self):

        self._transcurrido_ms= (self._transcurrido_ms + 16) % self._DURACION_CICLO_MS
        self.update()

    def paintEvent(self, evento):

        fase= (self._transcurrido_ms / self._DURACION_CICLO_MS) * 2 * math.pi

        #Rotación base: dos vueltas completas por ciclo, para que se sienta ágil y no lento/pesado.
        rotacion_base= (self._transcurrido_ms / self._DURACION_CICLO_MS) * 720

        #Largo del arco: oscila suavemente entre _LARGO_MIN y _LARGO_MAX
        #(curva coseno = aceleración/desaceleración natural, no lineal).
        largo= self._LARGO_MIN + (self._LARGO_MAX - self._LARGO_MIN) * (0.5 - 0.5 * math.cos(fase))
        #Cuando el arco es corto, el punto de INICIO avanza más rápido que cuando es largo -así el "hueco" también
        #parece desplazarse-, que es justo el efecto que hace ver este tipo de spinner "vivo".
        inicio= rotacion_base + largo * 0.5

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radio= 18
        centro_x= self.width() / 2
        centro_y= self.height() / 2 - 16
        rect= QRectF(centro_x - radio, centro_y - radio, radio * 2, radio * 2)

        #Pista tenue de fondo (círculo completo, color suave del acento)
        pen_pista= QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 40))
        pen_pista.setWidth(4)
        pen_pista.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_pista)
        painter.drawEllipse(rect)

        #Arco giratorio de largo variable
        pen_arco= QPen(self._color)
        pen_arco.setWidth(4)
        pen_arco.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arco)
        painter.drawArc(rect, int(-inicio * 16), int(largo * 16))

        #Texto debajo del spinner
        painter.setPen(self._color_texto)
        rect_texto= QRect(0, int(centro_y + radio + 14), self.width(), 24)
        painter.drawText(rect_texto, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._texto)
        painter.end()


class MainWindow(QMainWindow):

    VERSION= "1.0.0"
    
    def __init__(self):

        super().__init__()
        self.version= self.VERSION
        self.setWindowTitle("AcaDeXI - Sistema Escolar")
        self.setMinimumSize(1000, 720)
        aplicar_icono_ventana(self)

        #Bandera para distinguir "cerrar de verdad" (Salir del menú de la bandeja) de un clic normal en la 'X' de la
        #ventana, que solo debe ocultarla. Ver closeEvent() y _salir_de_verdad() más abajo.
        self._saliendo_de_verdad= False

        self.cargar_configuracion()

        self.usuario_actual= None
        self.rol_actual= None
        self.id_usuario_actual= None
        self.nombre_usuario= None

        #--- Paletas de Colores ---
        self.theme_palettes= {
            "Colorful (Multicolor)": {
                "window_bg": ("#F1F5F9", "#0B1220"),
                "display_bg": ("#FFFFFF", "#111827"),
                "sidebar_bg": ("#1E293B", "#0B1220"),
                "sidebar_btn_bg": ("#334155", "#1E293B"),
                "sidebar_btn_hover": ("#475569", "#334155"),
                "sidebar_text_primary": ("#F8FAFC", "#F8FAFC"),
                "sidebar_text_secondary": ("#94A3B8", "#94A3B8"),
                "text_primary": ("#0F172A", "#F1F5F9"),
                "text_secondary": ("#64748B", "#94A3B8"),
                "btn_num_bg": ("#E2E8F0", "#1E293B"),
                "btn_num_hover": ("#CBD5E1", "#334155"),
                "btn_op_bg": ("#2563EB", "#3B82F6"),
                "btn_op_hover": ("#1D4ED8", "#2563EB"),
            },
            "Indigo": {
                "window_bg": ("#F8FAFC", "#0F172A"),
                "display_bg": ("#FFFFFF", "#1E293B"),
                "text_primary": ("#0F172A", "#F8FAFC"),
                "text_secondary": ("#64748B", "#94A3B8"),
                "btn_num_bg": ("#E2E8F0", "#334155"),
                "btn_num_hover": ("#CBD5E1", "#475569"),
                "btn_op_bg": ("#6366F1", "#4F46E5"),
                "btn_op_hover": ("#4F46E5", "#4338CA"),
            },
            "Emerald (Esmeralda)": {
                "window_bg": ("#F0FDF4", "#022C22"),
                "display_bg": ("#FFFFFF", "#064E3B"),
                "text_primary": ("#065F46", "#ECFDF5"),
                "text_secondary": ("#059669", "#34D399"),
                "btn_num_bg": ("#D1FAE5", "#0F766E"),
                "btn_num_hover": ("#A7F3D0", "#115E59"),
                "btn_op_bg": ("#10B981", "#059669"),
                "btn_op_hover": ("#059669", "#047857"),
            },
            "Sunset (Naranja)": {
                "window_bg": ("#FFF7ED", "#1C1917"),
                "display_bg": ("#FFFFFF", "#292524"),
                "text_primary": ("#7C2D12", "#FFF7ED"),
                "text_secondary": ("#EA580C", "#FDBA74"),
                "btn_num_bg": ("#FFEDD5", "#44403C"),
                "btn_num_hover": ("#FED7AA", "#57534E"),
                "btn_op_bg": ("#F97316", "#EA580C"),
                "btn_op_hover": ("#EA580C", "#D97706"),
            },
            "Midnight (Púrpura)": {
                "window_bg": ("#FAF5FF", "#0B0415"),
                "display_bg": ("#FFFFFF", "#180B2B"),
                "text_primary": ("#5B21B6", "#FAF5FF"),
                "text_secondary": ("#9333EA", "#C084FC"),
                "btn_num_bg": ("#F3E8FF", "#2E1065"),
                "btn_num_hover": ("#E9D5FF", "#3B0764"),
                "btn_op_bg": ("#A855F7", "#8B5CF6"),
                "btn_op_hover": ("#8B5CF6", "#7C3AED"),
            },
            "Omega (Rojo/Negro)": {
                "window_bg": ("#FEF2F2", "#09090B"),
                "display_bg": ("#FFFFFF", "#18181B"),
                "text_primary": ("#991B1B", "#FEF2F2"),
                "text_secondary": ("#DC2626", "#F87171"),
                "btn_num_bg": ("#FEE2E2", "#27272A"),
                "btn_num_hover": ("#FCA5A5", "#3F3F46"),
                "btn_op_bg": ("#EF4444", "#DC2626"),
                "btn_op_hover": ("#DC2626", "#B91C1C"),
            },
            "Ocean (Azul)": {
                "window_bg": ("#EFF6FF", "#0C1B33"),
                "display_bg": ("#FFFFFF", "#132A4D"),
                "text_primary": ("#1E3A8A", "#EFF6FF"),
                "text_secondary": ("#2563EB", "#60A5FA"),
                "btn_num_bg": ("#DBEAFE", "#1E3A5F"),
                "btn_num_hover": ("#BFDBFE", "#254A73"),
                "btn_op_bg": ("#3B82F6", "#2563EB"),
                "btn_op_hover": ("#2563EB", "#1D4ED8"),
            },
            "Rose (Rosa)": {
                "window_bg": ("#FFF1F2", "#1F0A0F"),
                "display_bg": ("#FFFFFF", "#2E1015"),
                "text_primary": ("#9F1239", "#FFF1F2"),
                "text_secondary": ("#E11D48", "#FB7185"),
                "btn_num_bg": ("#FFE4E6", "#3F1520"),
                "btn_num_hover": ("#FECDD3", "#4C1D2B"),
                "btn_op_bg": ("#F43F5E", "#E11D48"),
                "btn_op_hover": ("#E11D48", "#BE123C"),
            },
            "Amber (Dorado)": {
                "window_bg": ("#FFFBEB", "#1C1508"),
                "display_bg": ("#FFFFFF", "#2B2110"),
                "text_primary": ("#92400E", "#FFFBEB"),
                "text_secondary": ("#D97706", "#FBBF24"),
                "btn_num_bg": ("#FEF3C7", "#3D2F14"),
                "btn_num_hover": ("#FDE68A", "#4A3A19"),
                "btn_op_bg": ("#F59E0B", "#D97706"),
                "btn_op_hover": ("#D97706", "#B45309"),
            },
            "Slate (Gris Elegante)": {
                "window_bg": ("#F8FAFC", "#0A0A0A"),
                "display_bg": ("#FFFFFF", "#171717"),
                "text_primary": ("#18181B", "#FAFAFA"),
                "text_secondary": ("#52525B", "#A1A1AA"),
                "btn_num_bg": ("#E4E4E7", "#27272A"),
                "btn_num_hover": ("#D4D4D8", "#3F3F46"),
                "btn_op_bg": ("#3F3F46", "#71717A"),
                "btn_op_hover": ("#27272A", "#52525B"),
            },
            "Turquesa (Cyan)": {
                "window_bg": ("#ECFEFF", "#042F2E"),
                "display_bg": ("#FFFFFF", "#083E3D"),
                "text_primary": ("#155E75", "#ECFEFF"),
                "text_secondary": ("#0891B2", "#22D3EE"),
                "btn_num_bg": ("#CFFAFE", "#0E4B4A"),
                "btn_num_hover": ("#A5F3FC", "#115E5B"),
                "btn_op_bg": ("#06B6D4", "#0891B2"),
                "btn_op_hover": ("#0891B2", "#0E7490"),
            }
        }

        if self.tema_actual not in self.theme_palettes:
            self.tema_actual= "Colorful (Multicolor)"

        #--- Contenedor Principal ---
        main_widget= QWidget()
        self.setCentralWidget(main_widget)
        main_layout= QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        #--- Panel Lateral Izquierdo ---
        self.sidebar_ancho_normal= 250
        self.sidebar_ancho_colapsado= 76
        self.sidebar_colapsado= False

        left_panel= QFrame()
        left_panel.setObjectName("LeftPanel")
        left_panel.setFixedWidth(self.sidebar_ancho_normal)
        self.left_panel= left_panel
        left_layout= QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 16)
        left_layout.setSpacing(0)

        #--- Cabecera de marca ---
        cabecera= QFrame()
        cabecera.setObjectName("Cabecera")
        cabecera_layout= QHBoxLayout(cabecera)
        cabecera_layout.setContentsMargins(18, 22, 14, 18)
        cabecera_layout.setSpacing(10)

        self.lbl_insignia= QLabel()
        self.lbl_insignia.setObjectName("InsigniaLogo")
        self.lbl_insignia.setFixedSize(40, 40)
        self.lbl_insignia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #Logo real de AcaDeXI en la cabecera del sidebar. Si por algún motivo no se encuentra el archivo (ver
        #_pixmap_logo_base en bienvenida.py, que ya resuelve rutas en dev y empaquetado con PyInstaller), se cae de
        #vuelta al emblema de graduación 🎓.
        _pixmap_base_insignia= _pixmap_logo_base()
        if _pixmap_base_insignia is not None:
            _pixmap_insignia= _pixmap_base_insignia.scaled(
                28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.lbl_insignia.setPixmap(_pixmap_insignia)
        else:
            self.lbl_insignia.setText("")
        cabecera_layout.addWidget(self.lbl_insignia)

        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(0)
        self.lbl_marca= QLabel("AcaDeXI")
        self.lbl_marca.setObjectName("MarcaTitulo")
        self.lbl_subtitulo_marca= QLabel("SISTEMA ESCOLAR")
        self.lbl_subtitulo_marca.setObjectName("MarcaSubtitulo")
        bloque_titulo.addWidget(self.lbl_marca)
        bloque_titulo.addWidget(self.lbl_subtitulo_marca)
        cabecera_layout.addLayout(bloque_titulo, 1)

        self.btn_colapsar= QPushButton("«")
        self.btn_colapsar.setObjectName("BtnColapsar")
        self.btn_colapsar.setFixedSize(24, 24)
        self.btn_colapsar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_colapsar.clicked.connect(self.alternar_sidebar)
        cabecera_layout.addWidget(self.btn_colapsar)

        left_layout.addWidget(cabecera)

        self.linea_marca= QFrame()
        self.linea_marca.setObjectName("LineaAcento")
        self.linea_marca.setFixedHeight(2)
        left_layout.addWidget(self.linea_marca)

        #--- Tarjeta de perfil ---
        self.tarjeta_perfil= QFrame()
        self.tarjeta_perfil.setObjectName("TarjetaPerfil")
        perfil_layout= QHBoxLayout(self.tarjeta_perfil)
        perfil_layout.setContentsMargins(14, 12, 14, 12)
        perfil_layout.setSpacing(10)

        self.lbl_avatar= QLabel("?")
        self.lbl_avatar.setObjectName("AvatarPerfil")
        self.lbl_avatar.setFixedSize(38, 38)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_avatar.setToolTip("Cambiar foto de perfil")
        self.lbl_avatar.mousePressEvent= self._abrir_menu_avatar
        perfil_layout.addWidget(self.lbl_avatar)

        bloque_perfil_texto= QVBoxLayout()
        bloque_perfil_texto.setSpacing(1)
        self.lbl_usuario_logueado= QLabel("")
        self.lbl_usuario_logueado.setObjectName("PerfilNombre")
        self.lbl_usuario_logueado.setWordWrap(True)
        self.lbl_perfil_rol= QLabel("")
        self.lbl_perfil_rol.setObjectName("PerfilRol")
        bloque_perfil_texto.addWidget(self.lbl_usuario_logueado)
        bloque_perfil_texto.addWidget(self.lbl_perfil_rol)
        perfil_layout.addLayout(bloque_perfil_texto, 1)

        self.punto_estado= PuntoEstado(color="#22C55E", diametro=10)
        perfil_layout.addWidget(self.punto_estado, alignment=Qt.AlignmentFlag.AlignTop)

        self.tarjeta_perfil.setVisible(False)
        left_layout.addWidget(self.tarjeta_perfil)

        #--- Buscador tipo píldora ---
        self.pildora_busqueda= QFrame()
        self.pildora_busqueda.setObjectName("PildoraBusqueda")
        fila_busqueda_global= QHBoxLayout(self.pildora_busqueda)
        fila_busqueda_global.setContentsMargins(12, 0, 8, 0)
        fila_busqueda_global.setSpacing(6)
        lbl_icono_busqueda= QLabel("⌕")
        lbl_icono_busqueda.setObjectName("IconoBusqueda")
        fila_busqueda_global.addWidget(lbl_icono_busqueda)
        self.in_busqueda_global= QLineEdit()
        limitar_campo_texto(self.in_busqueda_global, 150)
        self.in_busqueda_global.setObjectName("BusquedaGlobal")
        self.in_busqueda_global.setPlaceholderText("Buscar en todo el sistema...")
        self.in_busqueda_global.returnPressed.connect(self.abrir_buscador_global)
        fila_busqueda_global.addWidget(self.in_busqueda_global)
        left_layout.addWidget(self.pildora_busqueda)
        left_layout.addSpacing(6)

        #--- Navegación con indicador deslizante ---
        self.nav_list= QListWidget()
        self.nav_list.setObjectName("NavList")
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self._pildora_nav= QFrame(self.nav_list.viewport())
        self._pildora_nav.setObjectName("PildoraNav")
        self._pildora_nav.setGeometry(0, 0, 0, 0)
        self._anim_pildora= QPropertyAnimation(self._pildora_nav, b"geometry")
        self._anim_pildora.setDuration(240)
        self._anim_pildora.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._construir_modulos_info()

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self.cambiar_vista)
        self.nav_list.verticalScrollBar().valueChanged.connect(
            lambda _v: self._mover_pildora_nav(self.nav_list.currentRow(), animar=False))
        left_layout.addWidget(self.nav_list, 1)

        #--- Pie: interruptor de tema + cerrar sesión ---
        pie_layout= QVBoxLayout()
        pie_layout.setContentsMargins(16, 8, 16, 0)
        pie_layout.setSpacing(10)

        fila_tema= QHBoxLayout()
        self.lbl_tema_texto= QLabel("Modo oscuro" if self.modo_oscuro else "Modo claro")
        self.lbl_tema_texto.setObjectName("TemaTexto")
        fila_tema.addWidget(self.lbl_tema_texto)
        fila_tema.addStretch()
        self.btn_tema= InterruptorTema()
        self.btn_tema.clicked.connect(self.animar_cambio_tema)
        self.btn_tema.poner_encendido(self.modo_oscuro, animar=False)
        fila_tema.addWidget(self.btn_tema)
        pie_layout.addLayout(fila_tema)

        self.btn_cerrar_sesion= QPushButton("Cerrar sesión")
        self.btn_cerrar_sesion.setIcon(icono_emoji("🚪"))
        self.btn_cerrar_sesion.setIconSize(_QSize_emoji(16, 16))
        self.btn_cerrar_sesion.setObjectName("BtnCerrarSesion")
        self.btn_cerrar_sesion.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar_sesion.clicked.connect(self.cerrar_sesion)
        self.btn_cerrar_sesion.setVisible(False)
        pie_layout.addWidget(self.btn_cerrar_sesion)

        left_layout.addLayout(pie_layout)

        main_layout.addWidget(left_panel)

        #--- Área de Contenido Central ---
        self.stacked_widget= StackedWidgetTamanoActual()
        self._construir_stack()
        main_layout.addWidget(self.stacked_widget)

        self.aplicar_tema()
        self._aplicar_permisos_por_rol()

        #--- Sistema de Alarmas/Alertas (calendario, horario, recordatorios) ---
        self.motor_alarmas= MotorAlarmas(self)
        self.motor_alarmas.iniciar()

        #Ya NO precargamos módulos en segundo plano - solo el Dashboard Cargamos solo el Dashboard inmediatamente
        self._asegurar_modulo_cargado(0)

        self._configurar_bandeja_sistema()
        self._configurar_atajos_teclado()

    #Atajos de teclado — instalación global (ver atajos.py)
    #Instala el vigía de la tecla "mantener para ver atajos" (Alt por
    #defecto, configurable en Configuración) y los atajos globales de la
    #ventana principal, disponibles sin importar el módulo abierto.
    def _configurar_atajos_teclado(self):

        self._gestor_atajos= GestorAtajos(self)
        QApplication.instance().installEventFilter(self._gestor_atajos)
        #Retroalimentación visual de clic (ver atajos.py): un solo filtro global para TODOS los botones de la app, en
        #vez de que cada módulo tenga que conectarlo a mano en cada botón.
        self._gestor_retroalimentacion_clics= GestorRetroalimentacionClics(self)
        QApplication.instance().installEventFilter(self._gestor_retroalimentacion_clics)
        self._titulo_modulo_atajos= "AcaDeXI"

        registrar_atajo(self, self, "Ctrl+K", "Buscar en todo el sistema",
                         lambda: (self.in_busqueda_global.setFocus(), self.in_busqueda_global.selectAll()),
                         contexto=Qt.ShortcutContext.ApplicationShortcut)
        #Se guarda la referencia (no solo se registra) porque el Tutorial Detallado necesita poder desactivarlo
        #mientras el tour está activo -abrir el Buscador Global a mitad de un paso saca al usuario de la pantalla que
        #el tutorial está resaltando y puede dejarlo "atascado" buscando el botón que ya no está a la vista (ver
        #tutoriales.py: AsistenteSpotlight lo desactiva al iniciar y lo restaura siempre al cerrar, se haya completado
        #el tour o no).
        self._atajo_buscador_global= registrar_atajo(
            self, self, "Ctrl+F", "Abrir/cerrar el Buscador Global",
            self.abrir_buscador_global, contexto=Qt.ShortcutContext.ApplicationShortcut)
        registrar_atajo(self, self, "Ctrl+Shift+Q", "Cerrar sesión",
                         self.cerrar_sesion, contexto=Qt.ShortcutContext.ApplicationShortcut)
        registrar_atajo(self, self, "Ctrl+B", "Colapsar/expandir menú lateral",
                         self.alternar_sidebar, contexto=Qt.ShortcutContext.ApplicationShortcut)

    #Bandeja del sistema (System Tray)
    #Crea el icono en la bandeja del sistema y su menú contextual.
    #Con esto la 'X' de la ventana solo la oculta (ver closeEvent);
    #la app sigue viva en segundo plano hasta que el usuario elige
    #'Salir' explícitamente desde este icono.
    def _configurar_bandeja_sistema(self):

        if not QSystemTrayIcon.isSystemTrayAvailable():
            #En algunos entornos (p. ej. ciertas distros Linux sin bandeja, o pruebas headless) puede no haber bandeja
            #disponible; en ese caso la 'X' simplemente cierra la app con normalidad.
            self.tray_icon= None
            return

        self.tray_icon= QSystemTrayIcon(icono_app(), self)
        self.tray_icon.setToolTip("AcaDeXI - Sistema Escolar")
        self._reconstruir_menu_bandeja()
        self._actualizar_icono_bandeja()
        self.tray_icon.activated.connect(self._al_activar_icono_bandeja)
        self.tray_icon.show()

    #Icono de la app con un PUNTO de estado en la esquina inferior
    #derecha, para saber de un vistazo (sin abrir el menú) qué pasará al
    #cerrar la ventana principal:
    #- AZUL  (#3B82F6): la app seguirá en segundo plano (bandeja).
    #- ROJO  (#EF4444): la app se cerrará del todo.
    def _icono_bandeja_con_estado(self):

        base= icono_app().pixmap(64, 64)
        pintor= QPainter(base)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        azul= QColor("#3B82F6") if getattr(self, "minimizar_a_bandeja", True) else QColor("#EF4444")
        borde= QColor("#FFFFFF")
        s= base.width()
        d= s * 0.34  #diámetro del punto
        pintor.setBrush(QBrush(azul))
        pintor.setPen(QPen(borde, max(2.0, s * 0.045)))
        pintor.drawEllipse(QRectF(s - d - s * 0.04, s - d - s * 0.04, d, d))
        pintor.end()
        return QIcon(base)

    #Punto de estado AZUL/ROJO solo (mismo color que el badge del icono
    #de la bandeja), para teñir el icono de la acción 'Ejecutar en segundo
    #plano al cerrar' del menú según el estado actual.
    def _punto_estado_bandeja(self, size=18):

        pm= QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        pintor= QPainter(pm)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        azul= QColor("#3B82F6") if getattr(self, "minimizar_a_bandeja", True) else QColor("#EF4444")
        s= size
        pintor.setBrush(QBrush(azul))
        pintor.setPen(QPen(QColor("#FFFFFF"), max(1.5, s * 0.09)))
        pintor.drawEllipse(QRectF(s * 0.10, s * 0.10, s * 0.80, s * 0.80))
        pintor.end()
        return QIcon(pm)

    #Repinta el icono de la bandeja (y su tooltip) según el estado de
    #'minimizar_a_bandeja'. Se llama al crear la bandeja y cada vez que
    #cambia la preferencia (menú de la bandeja o Configuración).
    def _actualizar_icono_bandeja(self):

        if getattr(self, "tray_icon", None) is None:
            return
        self.tray_icon.setIcon(self._icono_bandeja_con_estado())
        if getattr(self, "minimizar_a_bandeja", True):
            self.tray_icon.setToolTip(
                "AcaDeXI - AZUL: seguirá en segundo plano al cerrar la ventana")
        else:
            self.tray_icon.setToolTip(
                "AcaDeXI - ROJO: se cerrará por completo al cerrar la ventana")
        #La acción del menú también se tiñe del mismo color de estado.
        if getattr(self, "_accion_bandeja_toggle", None) is not None:
            self._accion_bandeja_toggle.setIcon(self._punto_estado_bandeja())

    #Reconstruye por completo el menú contextual del icono de bandeja:
    #encabezado con el usuario conectado (avatar/iniciales, nombre y rol),
    #estilo acorde al tema/modo actual de la app e iconos en cada acción.
    #Se llama al arrancar la bandeja y cada vez que cambia algo que afecta
    #lo que ese menú debe mostrar: iniciar sesión, cerrar sesión, o cambiar
    #de tema/modo claro-oscuro (aplicar_tema), para que nunca quede
    #desactualizado ni con los colores del tema anterior.
    def _reconstruir_menu_bandeja(self):

        if getattr(self, "tray_icon", None) is None:
            return

        paleta= self.theme_palettes[self.tema_actual]
        idx= 1 if self.modo_oscuro else 0
        bg_panel= paleta["display_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        bg_btn= paleta["btn_num_bg"][idx]
        accent= paleta["btn_op_bg"][idx]
        borde= _hex_a_rgba(bg_btn, 0.65)

        menu_bandeja= QMenu()
        menu_bandeja.setObjectName("MenuBandeja")
        menu_bandeja.setStyleSheet(f"""
            QMenu#MenuBandeja {{
                background-color: {bg_panel};
                border: 1px solid {borde};
                border-radius: 10px;
                padding: 6px;
            }}
            QMenu#MenuBandeja::item {{
                color: {txt_prim};
                background-color: transparent;
                padding: 8px 14px 8px 10px;
                border-radius: 6px;
                margin: 1px 2px;
            }}
            QMenu#MenuBandeja::item:selected {{
                background-color: {_hex_a_rgba(accent, 0.22)};
                color: {txt_prim};
            }}
            QMenu#MenuBandeja::item:disabled {{
                color: {txt_sec};
            }}
            QMenu#MenuBandeja::separator {{
                height: 1px;
                background-color: {borde};
                margin: 6px 8px;
            }}
            QMenu#MenuBandeja::icon {{
                padding-left: 6px;
            }}
        """)

        #--- Encabezado: avatar/iniciales + nombre + rol del usuario conectado ---
        hay_sesion= bool(self.usuario_actual)
        cabecera= QWidget()
        fila_cab= QHBoxLayout(cabecera)
        fila_cab.setContentsMargins(12, 8, 12, 10)
        fila_cab.setSpacing(10)

        avatar= QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap_avatar= self.lbl_avatar.pixmap() if hay_sesion and hasattr(self, "lbl_avatar") else None
        if pixmap_avatar is not None and not pixmap_avatar.isNull():
            avatar.setPixmap(pixmap_avatar.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
            avatar.setStyleSheet("background-color: transparent;")
        else:
            iniciales= "".join(p[0] for p in (self.nombre_usuario or "?").split()[:2]).upper()\
                if hay_sesion and self.nombre_usuario else "?"
            avatar.setText(iniciales)
            avatar.setStyleSheet(f"""
                background-color: {accent}; color: #FFFFFF; border-radius: 18px;
                font-weight: bold; font-size: 13px;
            """)
        fila_cab.addWidget(avatar)

        col_texto= QVBoxLayout()
        col_texto.setSpacing(0)
        lbl_nombre= QLabel(self.nombre_usuario if hay_sesion else "Sin sesión iniciada")
        lbl_nombre.setStyleSheet(f"color: {txt_prim}; font-weight: 600; font-size: 13px; background: transparent;")
        col_texto.addWidget(lbl_nombre)
        lbl_rol= QLabel(self.rol_actual if hay_sesion else "Inicia sesión desde la ventana")
        lbl_rol.setStyleSheet(f"color: {txt_sec}; font-size: 11px; background: transparent;")
        col_texto.addWidget(lbl_rol)
        fila_cab.addLayout(col_texto, 1)

        accion_cabecera= QWidgetAction(menu_bandeja)
        accion_cabecera.setDefaultWidget(cabecera)
        menu_bandeja.addAction(accion_cabecera)
        menu_bandeja.addSeparator()

        accion_abrir= menu_bandeja.addAction(icono_emoji("🪟"), "Abrir AcaDeXI")
        accion_abrir.triggered.connect(self._restaurar_desde_bandeja)
        menu_bandeja.addSeparator()

        self._accion_bandeja_toggle= menu_bandeja.addAction(
            self._punto_estado_bandeja(), "Ejecutar en segundo plano al cerrar")
        self._accion_bandeja_toggle.setCheckable(True)
        self._accion_bandeja_toggle.setChecked(getattr(self, "minimizar_a_bandeja", True))
        self._accion_bandeja_toggle.toggled.connect(self._establecer_minimizar_a_bandeja)

        if hay_sesion:
            menu_bandeja.addSeparator()
            accion_cerrar_sesion= menu_bandeja.addAction(icono_emoji("🚪"), "Cerrar sesión")
            accion_cerrar_sesion.triggered.connect(self._cerrar_sesion_desde_bandeja)

        menu_bandeja.addSeparator()
        accion_salir= menu_bandeja.addAction(icono_emoji("✖"), "Salir")
        accion_salir.triggered.connect(self._salir_de_verdad)

        self.tray_icon.setContextMenu(menu_bandeja)

    #Restaura la ventana antes de cerrar sesión desde el menú de la
    #bandeja: el diálogo de confirmación y el login que siguen necesitan
    #una ventana visible en primer plano, no minimizada/oculta.
    def _cerrar_sesion_desde_bandeja(self):

        self._restaurar_desde_bandeja()
        self.cerrar_sesion()

    def _al_activar_icono_bandeja(self, razon):

        #Doble clic (o clic simple, según plataforma) sobre el icono restaura la ventana. El clic derecho lo maneja el
        #propio QMenu asignado con setContextMenu.
        if razon in (QSystemTrayIcon.ActivationReason.DoubleClick,
                     QSystemTrayIcon.ActivationReason.Trigger):
            self._restaurar_desde_bandeja()

    def _restaurar_desde_bandeja(self):

        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    #Único punto que cambia la preferencia 'minimizar_a_bandeja', ya sea
    #desde el propio menú de la bandeja o desde Configuración ▸ Apariencia,
    #para que ambos lugares queden siempre sincronizados entre sí.
    def _establecer_minimizar_a_bandeja(self, activo):

        self.minimizar_a_bandeja= bool(activo)
        self.guardar_configuracion()
        self._actualizar_icono_bandeja()
        if getattr(self, "_accion_bandeja_toggle", None) is not None:
            #Evita un bucle de señales cuando quien llamó fue el propio checkbox del menú (toggled ya se disparó); solo
            #re-sincroniza cuando el cambio vino de otro lado (p. ej. Configuración).
            if self._accion_bandeja_toggle.isChecked() != self.minimizar_a_bandeja:
                self._accion_bandeja_toggle.blockSignals(True)
                self._accion_bandeja_toggle.setChecked(self.minimizar_a_bandeja)
                self._accion_bandeja_toggle.blockSignals(False)

    #Único punto por el que la aplicación termina realmente.
    def _salir_de_verdad(self):

        self._saliendo_de_verdad= True
        if getattr(self, "tray_icon", None) is not None:
            self.tray_icon.hide()
        self.close()
        #Con setQuitOnLastWindowClosed(False) (necesario para el patrón de
        #bandeja), cerrar la ventana NO basta para que app.exec() retorne:
        #Qt no da por hecho que "cerrar la última ventana" deba terminar el bucle de eventos. Sin este quit()
        #explícito, el proceso de Python se queda vivo en segundo plano (en la terminal se ve como que sigue "colgado",
        #sin volver al prompt) aunque no quede ninguna ventana ni icono de bandeja visible. Lo pedimos explícitamente
        #para que el proceso realmente termine.
        QApplication.instance().quit()

    #Módulos dinámicos según tipo de institución
    def _tipo_institucion(self):

        try:

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT tipo_institucion, modulos_personalizados FROM configuracion WHERE id=1")
            fila= c.fetchone()
            conn.close()
            if not fila:
                return "Escuela", []
            personalizados= (fila["modulos_personalizados"] or "").split(",")
            return fila["tipo_institucion"] or "Escuela", personalizados
        except Exception:
            return "Escuela", []

    #Agrupación visual (no afecta el índice real del módulo, solo decide dónde aparece el pequeño rótulo de sección
    #encima de la fila).
    _SECCIONES= {
        "Dashboard": "PRINCIPAL", "Estudiantes": "PRINCIPAL", "Profesores": "PRINCIPAL",
        "Personal": "PRINCIPAL", "Materias": "PRINCIPAL", "Asistencia": "PRINCIPAL",
        "Calificaciones": "PRINCIPAL", "Politécnico": "PRINCIPAL",
        "Calificaciones Técnicas": "PRINCIPAL", "Universidad": "PRINCIPAL",
        "Mis Materias": "DOCENCIA", "Mis Estudiantes": "DOCENCIA", "Banco de Tareas": "DOCENCIA",
        "Secuencias Didácticas": "DOCENCIA",
        "Horario": "DOCENCIA", "Calendario": "DOCENCIA", "Observaciones": "DOCENCIA",
        "Psicología": "DOCENCIA", "Materiales": "DOCENCIA",
        "Reportes": "SISTEMA", "Copias de Seguridad": "SISTEMA",
        "Sincronización": "SISTEMA", "Configuración": "SISTEMA",
    }

    def _seccion_de(self, nombre):

        return self._SECCIONES.get(nombre, "PRINCIPAL")

    def _construir_modulos_info(self):

        if edicion_actual() == "single_teacher":
            #Menú fijo y conocido de antemano (Pieza 3): sin tipo de institución que consultar, sin RBAC, sin "Mis
            #Materias"/"Mis Estudiantes" institucionales -aquí el docente es dueño directo.
            self.modulos_info= [
                ("📊", "Dashboard"), ("🎓", "Estudiantes"), ("📘", "Materias"),
                ("✅", "Asistencia"), ("📊", "Calificaciones"), ("📋", "Banco de Tareas"),
                ("📝", "Secuencias Didácticas"), ("📅", "Horario"), ("🗒", "Observaciones"), ("📊", "Reportes"), ("⚙", "Configuración"),
            ]
            self.modulos= [nombre for _, nombre in self.modulos_info]
            self.nav_list.blockSignals(True)
            self.nav_list.clear()
            self._nav_items= []
            for idx, (icono, nombre) in enumerate(self.modulos_info):
                item= QListWidgetItem()
                fila= ModuloNavItem(idx, icono, nombre, eyebrow=None)
                fila.poner_colapsado(self.sidebar_colapsado)
                fila.activado.connect(self.nav_list.setCurrentRow)
                item.setSizeHint(fila.sizeHint())
                self.nav_list.addItem(item)
                self.nav_list.setItemWidget(item, fila)
                self._nav_items.append(fila)
            self.nav_list.blockSignals(False)
            self._pildora_nav.lower()
            return
        tipo, modulos_personalizados= self._tipo_institucion()
        #Los caracteres aquí son solo el ÚLTIMO respaldo (ver ModuloNavItem):
        #primero se intenta el PNG de sidebar_icons/, y si tampoco existe, el icono vectorial coherente de
        #iconos_auto.py. Esta lista casi nunca llega a mostrarse tal cual, pero se mantiene con un emoji sensato por
        #módulo por si ninguno de los dos anteriores aplica.
        self.modulos_info= [
            ("📊", "Dashboard"),
            ("🎓", "Estudiantes"),
            ("👥", "Profesores"),
            ("👥", "Personal"),
            ("📘", "Materias"),
            ("✅", "Asistencia"),
            ("📊", "Calificaciones"),
        ]
        if tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in modulos_personalizados):
            self.modulos_info.append(("🏫", "Politécnico"))
            self.modulos_info.append(("📊", "Calificaciones Técnicas"))
        if tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in modulos_personalizados):
            self.modulos_info.append(("🏛", "Universidad"))

        self.modulos_info.append(("📘", "Mis Materias"))
        self.modulos_info.append(("🎓", "Mis Estudiantes"))
        self.modulos_info.append(("📋", "Banco de Tareas"))
        self.modulos_info.append(("📝", "Secuencias Didácticas"))
        self.modulos_info.append(("📅", "Horario"))
        self.modulos_info.append(("📆", "Calendario"))
        self.modulos_info.append(("🗒", "Observaciones"))
        #"Psicología" solo la ve de verdad quien tenga el módulo otorgado
        #(ver permisos.puede_ver_psicologia / _aplicar_permisos_por_rol):
        #se agrega siempre a la lista, igual que el resto, y es
        #modulo_visible() quien la oculta para cualquiera que no sea el
        #cargo de Side Stepper con el módulo concedido o un rol gerencial.
        self.modulos_info.append(("🧠", "Psicología"))
        self.modulos_info.append(("📦", "Materiales"))

        self.modulos_info.append(("📊", "Reportes"))
        self.modulos_info.append(("🛡", "Copias de Seguridad"))
        self.modulos_info.append(("🔄", "Sincronización"))
        self.modulos_info.append(("⚙", "Configuración"))

        self.modulos= [nombre for _, nombre in self.modulos_info]
        self.nav_list.blockSignals(True)
        self.nav_list.clear()
        seccion_anterior= None
        self._nav_items= []
        for idx, (icono, nombre) in enumerate(self.modulos_info):
            seccion= self._seccion_de(nombre)
            eyebrow= seccion if seccion != seccion_anterior else None
            seccion_anterior= seccion

            item= QListWidgetItem()
            fila= ModuloNavItem(idx, icono, nombre, eyebrow=eyebrow)
            fila.poner_colapsado(self.sidebar_colapsado)
            fila.activado.connect(self.nav_list.setCurrentRow)
            item.setSizeHint(fila.sizeHint())
            self.nav_list.addItem(item)
            self.nav_list.setItemWidget(item, fila)
            self._nav_items.append(fila)
        self.nav_list.blockSignals(False)
        self._pildora_nav.lower()

    def _construir_stack(self):

        self._modulos_cargados= set()

        while self.stacked_widget.count():
            w= self.stacked_widget.widget(0)
            self.stacked_widget.removeWidget(w)
            w.deleteLater()

        #Solo agregamos placeholders para todos los módulos
        for idx, modulo in enumerate(self.modulos):
            page= self._crear_placeholder(modulo)
            self.stacked_widget.addWidget(page)

    def recargar_modulos_dinamicos(self):

        #IMPORTANTE: se guarda el NOMBRE del módulo actual, no su índice. Al reconstruir modulos_info (p. ej. tras
        #cambiar el tipo de institución en Configuración) la cantidad y el orden de módulos puede cambiar, así que el
        #mismo índice puede terminar apuntando a otro módulo distinto (por eso, al guardar en Configuración, a veces se
        #terminaba mostrando "Reportes" u otro módulo en vez de quedarse en "Configuración").
        fila_actual= self.nav_list.currentRow()
        modulo_actual= self.modulos[fila_actual] if 0 <= fila_actual < len(self.modulos) else None
        self._construir_modulos_info()
        self._construir_stack()
        if modulo_actual is not None and modulo_actual in self.modulos:
            nueva_fila= self.modulos.index(modulo_actual)
        else:
            nueva_fila= 0 if fila_actual < 0 else min(fila_actual, self.nav_list.count() - 1)
        self.nav_list.setCurrentRow(nueva_fila)
        self._aplicar_permisos_por_rol()

    #Accent + color de texto secundario del tema ACTUAL, para que el
    #spinner de carga combine con el resto de la app (y no un azul fijo
    #que desentona en algún tema/oscuro). Con un respaldo seguro por si
    #se llama antes de que el tema esté completamente inicializado.
    def _colores_carga(self):

        try:

            paleta= self.theme_palettes[self.tema_actual]
            idx= 1 if self.modo_oscuro else 0
            return paleta["btn_op_bg"][idx], paleta["text_secondary"][idx]
        except Exception:
            return "#4F8EF7", "#8A94A6"

    def _crear_placeholder(self, nombre_modulo):

        page= QWidget()
        page_layout= QVBoxLayout(page)
        page_layout.setContentsMargins(40, 40, 40, 40)
        accent, txt_sec= self._colores_carga()
        spinner= IndicadorCargaGiratorio(f"Cargando {nombre_modulo}…", color=accent, color_texto=txt_sec)
        page.spinner= spinner  #referencia para poder detenerlo antes de descartar la página
        page_layout.addStretch()
        page_layout.addWidget(spinner)
        page_layout.addStretch()
        return page

    #Carga el módulo bajo demanda (lazy loading) si no está cargado.
    def _asegurar_modulo_cargado(self, indice):

        if indice < 0 or indice >= len(self.modulos):
            return
        if indice in self._modulos_cargados:
            return
        nombre= self.modulos[indice]
        fabrica= _obtener_fabrica_modulo(nombre)
        if fabrica is None:
            self._modulos_cargados.add(indice)
            return

        #Crear el módulo real (puede ser pesado: varias pestañas, tablas, consultas a la BD, animaciones). Para cuando
        #este método corre, el placeholder "Cargando…" de este índice YA está pintado en pantalla (ver cambiar_vista,
        #que lo muestra y difiere esta llamada un ciclo de evento después con QTimer.singleShot(0, ...)) — así Windows
        #siempre tiene un frame real que mostrar mientras el hilo se ocupa con esto, y nunca aparece un hueco en blanco
        #("ventana fantasma").
        pagina_real= fabrica(self)
        placeholder= self.stacked_widget.widget(indice)
        era_visible= (self.stacked_widget.currentIndex() == indice)

        if placeholder is not None:
            spinner= getattr(placeholder, "spinner", None)
            if spinner is not None:
                spinner.detener()
            self.stacked_widget.removeWidget(placeholder)
            placeholder.deleteLater()
        self.stacked_widget.insertWidget(indice, pagina_real)
        self._modulos_cargados.add(indice)

        if era_visible:
            self.stacked_widget.setCurrentIndex(indice)
            #El contenido real reemplaza al spinner con un fundido suave en vez de un corte seco -mismo efecto que usa el
            #resto de la app al cambiar de pestaña/paso (ver configuracion._fundido_entrada)- así la transición se siente
            #intencional y pulida.
            _fundido_entrada(pagina_real)

    def cambiar_vista(self, index):

        if index < 0 or index >= len(self.modulos):
            return
        ya_cargado= index in self._modulos_cargados

        #Se muestra de inmediato lo que YA exista en ese índice: si el módulo nunca se cargó, eso es el placeholder
        #"Cargando…" (ver _crear_placeholder) — NUNCA un hueco en blanco. La construcción pesada del módulo real se
        #dispara recién en el SIGUIENTE ciclo del bucle de eventos, vía QTimer.singleShot(0, ...). Eso le da tiempo a
        #Qt de pintar ese placeholder y entregarle a Windows un frame válido ANTES de bloquear el hilo principal: si se
        #hiciera todo de corrido, Windows no tiene nada que mostrar durante el bloqueo y rellena el hueco con un
        #rectángulo en blanco — la "ventana fantasma" que aparecía al entrar a un módulo pesado.
        self.stacked_widget.setCurrentIndex(index)
        self._indice_modulo_tema= index
        for i, fila in enumerate(getattr(self, "_nav_items", [])):
            fila.poner_activo(i == index)
        self._mover_pildora_nav(index, animar=True)

        if ya_cargado:
            pagina= self.stacked_widget.widget(index)
            if hasattr(pagina, "refrescar"):
                #Usamos QTimer para que la UI no se congele al refrescar
                QTimer.singleShot(10, pagina.refrescar)
        else:
            #120ms alcanza para varios frames del spinner (a 60fps son ~7
            #vueltas de arco) antes de arrancar la construcción pesada:
            #así el usuario ve una animación real e intencional en vez de un "flash" -aunque fuera de un frame bonito, un
            #solo frame se percibe como un parpadeo/glitch, no como una carga.
            QTimer.singleShot(120, lambda: self._cargar_modulo_diferido(index))

    #Construye el módulo real un instante después de mostrar el
    #placeholder «Cargando…» (ver cambiar_vista) y lo deja en su lugar
    #dentro del stack.
    def _cargar_modulo_diferido(self, indice):

        try:

            self._asegurar_modulo_cargado(indice)
        except Exception:
            import traceback
            traceback.print_exc()
            return
        #Si seguimos viendo este módulo (el usuario no navegó a otro lado mientras se cargaba), refrescamos igual que
        #se hace con los módulos que ya estaban cargados.
        if self.stacked_widget.currentIndex() == indice:
            pagina= self.stacked_widget.widget(indice)
            if hasattr(pagina, "refrescar"):
                QTimer.singleShot(10, pagina.refrescar)

    def _mover_pildora_nav(self, indice, animar=True):

        if indice < 0 or indice >= self.nav_list.count():
            return
        item= self.nav_list.item(indice)
        if item is None or item.isHidden():
            self._pildora_nav.setGeometry(0, 0, 0, 0)
            return
        rect= self.nav_list.visualItemRect(item)
        destino= QRect(8, rect.y() + 2, self.nav_list.viewport().width() - 16, rect.height() - 4)
        self._pildora_nav.setVisible(True)
        if animar and self._pildora_nav.geometry().width() > 0:
            self._anim_pildora.stop()
            self._anim_pildora.setStartValue(self._pildora_nav.geometry())
            self._anim_pildora.setEndValue(destino)
            self._anim_pildora.start()
        else:
            self._pildora_nav.setGeometry(destino)
        self._pildora_nav.lower()

    def alternar_sidebar(self):

        self.sidebar_colapsado= not self.sidebar_colapsado
        ancho_destino= self.sidebar_ancho_colapsado if self.sidebar_colapsado else self.sidebar_ancho_normal

        anim= QVariantAnimation(self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(self.left_panel.width())
        anim.setEndValue(ancho_destino)
        anim.valueChanged.connect(lambda v: self.left_panel.setFixedWidth(int(v)))
        anim.valueChanged.connect(
            lambda _v: self._mover_pildora_nav(self.nav_list.currentRow(), animar=False))
        self._anim_sidebar_activa= anim
        anim.start()

        self.btn_colapsar.setText("»" if self.sidebar_colapsado else "«")
        self.lbl_marca.setVisible(not self.sidebar_colapsado)
        self.lbl_subtitulo_marca.setVisible(not self.sidebar_colapsado)
        self.pildora_busqueda.setVisible(not self.sidebar_colapsado)
        self.lbl_perfil_rol.setVisible(not self.sidebar_colapsado)
        self.lbl_usuario_logueado.setVisible(not self.sidebar_colapsado and self.usuario_actual is not None)
        self.lbl_tema_texto.setVisible(not self.sidebar_colapsado)
        for fila in getattr(self, "_nav_items", []):
            fila.poner_colapsado(self.sidebar_colapsado)

    def abrir_buscador_global(self):

        #Ctrl+F (o Enter en la píldora de búsqueda) actúa como interruptor:
        #si el diálogo ya está abierto, esta misma tecla lo cierra en vez de intentar abrir uno nuevo encima. Se guarda
        #la referencia en self._dialogo_busqueda_global para poder consultarla la próxima vez que se dispare el atajo,
        #incluso mientras el diálogo (modal,
        #exec()) todavía tiene el bucle de eventos anidado corriendo — el
        #QShortcut de Ctrl+F tiene ApplicationShortcut, así que le sigue llegando el evento igual.
        dialogo_actual= getattr(self, "_dialogo_busqueda_global", None)
        if dialogo_actual is not None and dialogo_actual.isVisible():
            dialogo_actual.close()
            return
        texto= self.in_busqueda_global.text().strip()
        dialogo= DialogoBusquedaGlobal(self, texto_inicial=texto)
        self._dialogo_busqueda_global= dialogo
        dialogo.exec()
        self._dialogo_busqueda_global= None
        self.in_busqueda_global.clear()

    def _aplicar_permisos_por_rol(self):

        for i, nombre in enumerate(self.modulos):
            item= self.nav_list.item(i)
            visible= modulo_visible(self.rol_actual, nombre)
            #"Calificaciones Técnicas" para el rol Profesor: además de estar en PERMISOS_TECHO, depende de
            #self.mostrar_calif_tecnicas, que se resolvió en mostrar_login() — True si el docente activó su preferencia
            #personal, O automáticamente si la institución es un
            #Politécnico (ver mostrar_login(). Los roles gerenciales NO
            #pasan por esta condición: para ellos basta con modulo_visible() de arriba, como siempre.
            if nombre == "Calificaciones Técnicas" and self.rol_actual == "Profesor":
                visible= visible and bool(getattr(self, "mostrar_calif_tecnicas", False))
            item.setHidden(not visible)

        if "Copias de Seguridad" in self.modulos and self.rol_actual in ROLES_GERENCIALES:
            from src.nucleo.bd import mostrar_backups_gerenciales
            i= self.modulos.index("Copias de Seguridad")
            self.nav_list.item(i).setHidden(not mostrar_backups_gerenciales())

        fila_actual= self.nav_list.currentRow()
        if fila_actual < 0 or self.nav_list.item(fila_actual).isHidden():
            for i in range(self.nav_list.count()):
                if not self.nav_list.item(i).isHidden():
                    self.nav_list.setCurrentRow(i)
                    break

        if "Configuración" in self.modulos:
            i= self.modulos.index("Configuración")
            #Asegurar que el módulo esté cargado antes de aplicar permisos
            self._asegurar_modulo_cargado(i)
            pagina= self.stacked_widget.widget(i)
            if hasattr(pagina, "aplicar_permisos_por_rol"):
                pagina.aplicar_permisos_por_rol()

        item_actual= self.nav_list.currentItem()
        if item_actual is not None:
            self.nav_list.scrollToItem(item_actual)

        for i, fila in enumerate(getattr(self, "_nav_items", [])):
            fila.poner_activo(i == self.nav_list.currentRow())
        self._mover_pildora_nav(self.nav_list.currentRow(), animar=False)

    #TEMA
    #Fundido de opacidad al cambiar de modo claro/oscuro: baja a un
    #nivel translúcido (55%, se sigue viendo la ventana de fondo pero
    #atenuada -look "cristal"-), aplica el tema con la ventana en ese
    #estado, y vuelve a subir a 100%. Usa QPropertyAnimation con easing
    #(igual que abrir_con_fundido y el resto de animaciones de la app)
    #en vez de un QTimer a mano recalculando el alpha paso a paso:
    #además de quedar más suave -la curva de aceleración/desaceleración
    #se nota, ya no es un fundido lineal a saltos de 15ms-, Qt puede
    #fusionar sus updates con el ciclo normal de refresco de pantalla en
    #vez de competir con él, así que no cuesta recursos extra.
    #Duraciones cortas (100ms bajada / 140ms subida) para que se sienta
    #instantáneo sin perder el efecto translúcido.
    def animar_cambio_tema(self):

        #Si ya hay un cambio de tema en curso (fundido de bajada, aplicación por páginas en segundo plano, o fundido de
        #subida), se ignora el nuevo toggle en vez de arrancar una segunda pasada encima: la aplicación por páginas
        #ahora es asíncrona (ver _refrescar_paginas_tema_async) y dos pasadas superpuestas podrían dejar páginas a
        #medio actualizar con el tema equivocado.
        if getattr(self, "_aplicando_tema", False):
            return
        self.modo_oscuro_futuro= not self.modo_oscuro
        #Si el usuario alcanza a tocar el interruptor de nuevo mientras la animación anterior todavía está en curso, se
        #corta en seco en vez de dejar dos animaciones peleando por la misma propiedad (eso sí se notaría como algo
        #raro/tironeado).
        anim_previa= getattr(self, "_anim_tema", None)
        if anim_previa is not None and anim_previa.state() == QPropertyAnimation.State.Running:
            anim_previa.stop()
        anim_bajada= QPropertyAnimation(self, b"windowOpacity", self)
        anim_bajada.setDuration(100)
        anim_bajada.setStartValue(self.windowOpacity())
        anim_bajada.setEndValue(0.55)
        anim_bajada.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_bajada.finished.connect(self._a_mitad_cambio_tema)
        self._anim_tema= anim_bajada
        anim_bajada.start()

    def _a_mitad_cambio_tema(self):

        self.modo_oscuro= self.modo_oscuro_futuro
        self.btn_tema.poner_encendido(self.modo_oscuro)
        self.lbl_tema_texto.setText("Modo oscuro" if self.modo_oscuro else "Modo claro")
        #OJO -causa real del "congelamiento" que había antes (el cursor de carga de Windows y la ventana sin responder
        #durante el cambio de tema): aplicar_tema() no es liviano. Recorre TODAS las páginas de módulos que ya se
        #construyeron en esta sesión (Calendario, Politécnico, Reportes -con su pesado editor incluido si se llegó a
        #abrir-, Configuración, etc.) y cada una reconstruye su propio QSS y refresca sus iconos/tablas; sumado, puede
        #tardar varios cientos de milisegundos. QTimer.singleShot(0, ...) deja que este frame -ya atenuado al 55%-
        #termine de pintarse primero, y
        #aplicar_tema() de paso le da respiro al bucle de eventos entre
        #página y página (ver el comentario ahí), así Windows nunca deja de recibir mensajes el tiempo suficiente como
        #para considerar que la app se colgó.
        QTimer.singleShot(0, self._terminar_cambio_tema)

    #Segunda mitad de animar_cambio_tema(): el trabajo pesado real
    #se ejecuta acá, con la ventana ya atenuada al 55% y en un ciclo del
    #bucle de eventos aparte del que disparó el fundido -ver el
    #comentario en _a_mitad_cambio_tema()-.
    #
    #A diferencia de antes, NO se llama a self.aplicar_tema() (esa
    #versión recorre las páginas de forma síncrona, solo con
    #QApplication.processEvents() como respiro entre una y otra -ver
    #_refrescar_paginas_tema_sincrono-, y sigue siendo un único tramo
    #ininterrumpido de trabajo Python; processEvents() NO le devuelve
    #el control al sistema operativo entre medio, solo bombea la cola
    #de eventos de Qt desde dentro de la misma llamada, así que si una
    #sola página pesada (p. ej. el editor de reportes con una hoja
    #grande) tarda más de un par de segundos ella sola, Windows igual
    #marca la ventana como "No responde" aunque el resto del bucle
    #tenga sus respiros).
    #
    #PERO trocear el bucle de páginas (_refrescar_paginas_tema_async)
    #NO ALCANZA por sí solo: el congelamiento real no viene de ahí, sino
    #de self.setStyleSheet(qss) -dentro de _aplicar_estilos_globales_tema-
    #aplicado sobre `self` (la ventana principal). Qt repule TODO el
    #árbol de widgets descendiente de forma SÍNCRONA E ININTERRUMPIBLE
    #dentro de ESA MISMA llamada en C++ -no hay ningún QTimer ni
    #processEvents de Python que pueda partir esa llamada en pedazos,
    #porque el trabajo pesado ocurre entero antes de que la función le
    #devuelva el control a Python-. Con varios módulos ya visitados en
    #la sesión (cada uno con sus propias tablas/tarjetas/etc., visibles
    #o no), ese árbol puede ser enorme, y ESE único repulido -no el
    #bucle de actualizar_tema()- es la causa real de que la ventana
    #siguiera colgándose aunque el bucle ya estuviera troceado.
    #
    #La solución: antes de tocar el stylesheet, _preparar_paginas_para_tema()
    #saca temporalmente del árbol todas las páginas YA CONSTRUIDAS que no
    #sean la que está visible ahora mismo (se reemplazan por un QWidget
    #vacío en su mismo lugar -sin destruir nada, sin perder ningún
    #estado-), así el repulido de setStyleSheet queda acotado a una sola
    #página en vez de a todas las que se hayan visitado en la sesión.
    #Esas páginas se reinsertan una por una, DESPUÉS del fundido de
    #vuelta, con _restaurar_paginas_ocultadas_por_tema -ver ahí por qué
    #eso sí puede trocearse sin problema.
    def _terminar_cambio_tema(self):

        #Mismo candado de reentrancia que ya usaba aplicar_tema(): mientras esté en True, cualquier llamada a
        #aplicar_tema() desde otro lado (p. ej. si algo dispara un refresco de tema por su cuenta durante este tramo)
        #no hace nada, en vez de competir por las mismas páginas a medio actualizar.
        self._aplicando_tema= True
        self._preparar_paginas_para_tema()
        self._aplicar_estilos_globales_tema()
        self._refrescar_paginas_tema_async(al_terminar=self._fade_subida_tema)

    #Saca temporalmente del árbol de widgets todas las páginas ya
    #construidas (self._modulos_cargados) SALVO la que está visible en
    #este momento, reemplazando cada una por un QWidget vacío EN SU
    #MISMO ÍNDICE dentro de self.stacked_widget -mismo truco de
    #índice-estable que ya usa _asegurar_modulo_cargado() para
    #reemplazar un placeholder "Cargando…" por el módulo real (y
    #viceversa aquí): el conteo y el orden del stack no cambian, así
    #que cambiar_vista()/_asegurar_modulo_cargado() siguen funcionando
    #con total normalidad mientras dura el cambio de tema.
    #
    #La página visible NUNCA se saca del stack: permanece intacta en su
    #índice para que el usuario nunca sea enviado a otro módulo ni vea
    #parpadeos. El setStyleSheet() posterior solo afecta a esa página
    #visible y a la estructura base de la ventana, completándose en
    #fracción de segundo.
    #
    #Las páginas secundarias reales NO se destruyen (no hay deleteLater
    #aquí): se guardan tal cual, con todo su estado intacto, en
    #self._paginas_ocultadas_tema, para reinsertarlas después de que el
    #fundido de vuelta ya haya terminado -ver
    #_restaurar_paginas_ocultadas_por_tema.
    def _preparar_paginas_para_tema(self):

        actual= self.stacked_widget.currentIndex()
        self._indice_modulo_tema= actual
        self._paginas_ocultadas_tema= {}
        for idx in list(getattr(self, "_modulos_cargados", set())):
            if idx == actual or idx < 0 or idx >= self.stacked_widget.count():
                continue
            pagina= self.stacked_widget.widget(idx)
            if pagina is None:
                continue
            self.stacked_widget.removeWidget(pagina)
            self.stacked_widget.insertWidget(idx, QWidget())
            self._paginas_ocultadas_tema[idx]= pagina
        #Reasegurar que el stacked_widget y la navegación permanezcan en el módulo activo
        if 0 <= actual < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(actual)

    #Reinserta -una página por vuelta del bucle de eventos, con
    #QTimer.singleShot(0, ...)- las páginas que _preparar_paginas_para_tema()
    #sacó temporalmente del árbol. A diferencia del setStyleSheet() de
    #arriba, ESTO SÍ se puede trocear sin problema: cuando un widget ya
    #construido se reinserta en un padre que ya tiene stylesheet, Qt
    #solo repule el subárbol de ESE widget recién insertado -no vuelve a
    #tocar el resto del árbol-, así que el costo de cada vuelta queda
    #acotado a una sola página en vez de a todas juntas.
    #
    #Se llama recién cuando el fundido de vuelta a opacidad completa ya
    #terminó (ver _fade_subida_tema): el usuario ve la ventana
    #respondiendo con normalidad desde el primer instante, y estas
    #páginas -invisibles hasta que se navegue a ellas- se ponen al día
    #en segundo plano sin que se note.
    def _restaurar_paginas_ocultadas_por_tema(self):

        pendientes= getattr(self, "_paginas_ocultadas_tema", None)
        actual= getattr(self, "_indice_modulo_tema", self.stacked_widget.currentIndex())
        if not pendientes:
            self._paginas_ocultadas_tema= {}
            if 0 <= actual < self.stacked_widget.count():
                self.stacked_widget.setCurrentIndex(actual)
                if hasattr(self, "nav_list") and self.nav_list.currentRow() != actual:
                    self.nav_list.setCurrentRow(actual)
            return

        idx= next(iter(pendientes))
        pagina= pendientes.pop(idx)
        marcador= self.stacked_widget.widget(idx)
        self.stacked_widget.removeWidget(marcador)
        marcador.deleteLater()
        self.stacked_widget.insertWidget(idx, pagina)

        #Garantizar que el índice visible no cambie bajo ninguna circunstancia
        if 0 <= actual < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(actual)
            if hasattr(self, "nav_list") and self.nav_list.currentRow() != actual:
                self.nav_list.setCurrentRow(actual)

        if hasattr(pagina, "actualizar_tema"):
            pagina.actualizar_tema()
        QTimer.singleShot(0, self._restaurar_paginas_ocultadas_por_tema)

    #Última parte del cambio de tema: ya con la página visible
    #actualizada, guarda la configuración y sube la opacidad de vuelta
    #a 100%. Al terminar ese fundido, arranca la restauración en
    #segundo plano de las demás páginas (ver
    #_restaurar_paginas_ocultadas_por_tema): para entonces la ventana
    #ya se ve completamente cambiada y respondiendo con normalidad.
    def _fade_subida_tema(self):

        self.guardar_configuracion()
        actual= getattr(self, "_indice_modulo_tema", self.stacked_widget.currentIndex())
        if 0 <= actual < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(actual)
            if hasattr(self, "nav_list") and self.nav_list.currentRow() != actual:
                self.nav_list.setCurrentRow(actual)
        anim_subida= QPropertyAnimation(self, b"windowOpacity", self)
        anim_subida.setDuration(140)
        anim_subida.setStartValue(self.windowOpacity())
        anim_subida.setEndValue(1.0)
        anim_subida.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_subida.finished.connect(self._restaurar_paginas_ocultadas_por_tema)
        self._anim_tema= anim_subida
        anim_subida.start()

    #Igual que el tramo final de _aplicar_tema_impl (recorrer
    #self.stacked_widget llamando actualizar_tema() en cada página, y
    #reconstruir el menú de la bandeja al final), pero troceado: cada
    #página se procesa en su propia vuelta del bucle de eventos
    #(QTimer.singleShot(0, ...)) en vez de todas seguidas con
    #processEvents() de por medio. La diferencia importa: processEvents()
    #bombea eventos SIN que esta función termine de ejecutarse -sigue
    #siendo una sola llamada larga desde el punto de vista del sistema
    #operativo-, mientras que aquí la función realmente retorna entre
    #una página y la siguiente, dejando que Qt/Windows procesen mensajes
    #con toda normalidad. Eso es lo único que garantiza que la ventana
    #NUNCA se marque como "No responde", sin importar cuántas páginas
    #haya ni cuán pesada sea alguna en particular.
    def _refrescar_paginas_tema_async(self, indice=0, al_terminar=None):

        total= self.stacked_widget.count()
        if indice >= total:
            self._reconstruir_menu_bandeja()
            self._aplicando_tema= False
            actual= getattr(self, "_indice_modulo_tema", self.stacked_widget.currentIndex())
            if 0 <= actual < self.stacked_widget.count():
                self.stacked_widget.setCurrentIndex(actual)
                if hasattr(self, "nav_list") and self.nav_list.currentRow() != actual:
                    self.nav_list.setCurrentRow(actual)
            if al_terminar is not None:
                al_terminar()
            return
        pagina= self.stacked_widget.widget(indice)
        if hasattr(pagina, "actualizar_tema"):
            pagina.actualizar_tema()
        QTimer.singleShot(0, lambda: self._refrescar_paginas_tema_async(indice + 1, al_terminar))


    def aplicar_tema(self):

        #Candado de reentrancia: aplicar_tema() bombea el bucle de eventos (ver más abajo) mientras recorre páginas; si
        #por lo que sea algo disparado durante ese respiro terminara llamando aplicar_tema() de
        #nuevo (p. ej. una señal de cambio de tema reentrante), sin este
        #candado se anidaría sobre sí misma. Con él, la segunda llamada simplemente no hace nada.
        if getattr(self, "_aplicando_tema", False):
            return
        self._aplicando_tema= True
        try:

            self._aplicar_tema_impl()
        finally:
            self._aplicando_tema= False

    #Versión síncrona completa (estilos globales + recorrido de
    #páginas con processEvents() como respiro). La usan el arranque de
    #la app y cualquier otro llamador de aplicar_tema() que no pase por
    #la animación de fundido (animar_cambio_tema), y se deja intacta
    #para no cambiarles el comportamiento. El propio toggle de modo
    #claro/oscuro YA NO pasa por aquí -ver _terminar_cambio_tema-, que
    #usa la versión troceada (_refrescar_paginas_tema_async) para
    #garantizar que la ventana nunca se congele.
    def _aplicar_tema_impl(self):

        self._aplicar_estilos_globales_tema()
        self._refrescar_paginas_tema_sincrono()

    def _aplicar_estilos_globales_tema(self):

        #Antes que nada: algunos íconos (p. ej. el de "Filtros") usan un gris neutro pensado para fondo claro y se
        #vuelven casi invisibles en modo oscuro. Esto refresca esos pocos íconos -y dejará refrescados también los que
        #se pidan de ahora en adelante-.
        establecer_modo_oscuro(self.modo_oscuro)

        paleta= self.theme_palettes[self.tema_actual]
        idx= 1 if self.modo_oscuro else 0
        bg_window= paleta["window_bg"][idx]
        bg_panel= paleta["display_bg"][idx]
        bg_sidebar= paleta.get("sidebar_bg", paleta["display_bg"])[idx]
        bg_sidebar_btn= paleta.get("sidebar_btn_bg", paleta["btn_num_bg"])[idx]
        bg_sidebar_btn_hover= paleta.get("sidebar_btn_hover", paleta["btn_num_hover"])[idx]
        txt_sidebar_prim= paleta.get("sidebar_text_primary", paleta["text_primary"])[idx]
        txt_sidebar_sec= paleta.get("sidebar_text_secondary", paleta["text_secondary"])[idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        bg_btn= paleta["btn_num_bg"][idx]
        hv_btn= paleta["btn_num_hover"][idx]
        accent= paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]

        accent_suave= _hex_a_rgba(accent, 0.16)
        sidebar_borde= _hex_a_rgba(bg_sidebar_btn, 0.60)

        #------------------------------------------------------------
        #ETIQUETAS CON RECUADRO (Configuración › Apariencia › Accesibilidad visual). Por defecto, TODAS las etiquetas
        #"planas" de TODOS los
        #módulos (las que no tienen su propio objectName/estilo — p. ej.
        #"Curso:", "Sección:", "Fecha:") se ven de forma normal: color de acento del tema y sin ningún fondo detrás del
        #texto.
        #
        #El "rectángulo" que a veces se ve detrás de una etiqueta (p. ej. "Fecha:" en Calendario) NO es un estilo
        #puesto a propósito: sale de la regla global "QMainWindow, QWidget { background-color: ... }" de más abajo, que
        #como QLabel también es un QWidget, le pinta su propio fondo de página; se nota más o menos según el panel
        #donde viva cada etiqueta. Por default ese fondo se quita en todos lados.
        #
        #La opción de accesibilidad "Etiquetas con recuadro" permite activar ese fondo/recuadro a propósito y en TODOS
        #los módulos por igual, para personas con dificultades visuales a quienes les ayude tener cada etiqueta
        #delimitada dentro de una caja. Está desactivada por defecto (etiquetas normales, sin recuadro).
        #
        #Los QLabel que ya tienen su propio "QLabel#objectName{...}"
        #(títulos, chips, iconos, etc.) NO se ven afectados en ningún caso:
        #un selector por ID siempre tiene más prioridad que el selector genérico "QLabel" en Qt, sin importar el orden.
        #
        #¿De qué color se pintan esas etiquetas? SIEMPRE negro en modo claro y SIEMPRE blanco en modo oscuro — nunca
        #dependen del "Tema de color" elegido (Indigo, Colorful, etc.) ni de su color de acento. Esto es intencional y
        #fijo: no hay ninguna opción para que las etiquetas "sigan" el tema; solo cambian con el modo claro/oscuro. El
        #toggle "Etiquetas con recuadro" (accesibilidad) es un asunto aparte: solo agrega/quita el fondo en forma de
        #caja detrás de la etiqueta, nunca afecta el color del texto.
        color_etiqueta_plana= "#FFFFFF" if self.modo_oscuro else "#000000"
        etiquetas_con_recuadro= getattr(self, "etiquetas_con_recuadro", False)
        fondo_etiqueta= (
            f"background-color: {_hex_a_rgba(bg_btn, 0.55)}; border-radius: 6px; "
            f"padding: 2px 6px;"
            if etiquetas_con_recuadro else "background: transparent;"
        )
        qss_labels_accesibilidad= f"QLabel {{ color: {color_etiqueta_plana}; {fondo_etiqueta} }}"

        #------------------------------------------------------------
        #TEXTO MÁS GRANDE (Configuración › Apariencia › Accesibilidad visual). Desactivado por defecto. Al activarse,
        #sube el tamaño de letra base de los controles de texto más comunes (etiquetas, botones, campos, pestañas) en
        #TODA la app, para quienes necesiten una fuente más grande para leer cómodamente. Como es una regla genérica
        #por tipo de widget (sin "#objectName"), cualquier control que ya tenga su propio tamaño de fuente explícito en
        #su propio QLabel#objectName{...} (títulos, chips, etc.) no se ve afectado. Si el tema define su propia paleta
        #de sidebar (p. ej. "Colorful", que siempre tiene una sidebar oscura sin importar el modo claro/oscuro de la
        #app), el degradado debe quedarse dentro de esa paleta oscura. De lo contrario, en modo claro el degradado
        #terminaba mezclándose con el fondo claro de la ventana y el texto gris de la sidebar perdía contraste sobre
        #esa zona clara.
        tiene_sidebar_propia= "sidebar_bg" in paleta
        sidebar_gradiente_fin= bg_sidebar_btn if tiene_sidebar_propia else bg_window

        es_colorful= self.tema_actual == "Colorful (Multicolor)"
        if es_colorful:
            color_agregar, color_agregar_hv= "#22C55E", "#16A34A"
            color_editar, color_editar_hv= "#3B82F6", "#2563EB"
            color_ajustar, color_ajustar_hv= "#F97316", "#EA580C"
            color_eliminar, color_eliminar_hv= "#EF4444", "#DC2626"
            color_neutro, color_neutro_hv= "#475569", "#334155"
        else:
            color_agregar, color_agregar_hv= accent, hv_accent
            color_editar, color_editar_hv= accent, hv_accent
            color_ajustar, color_ajustar_hv= accent, hv_accent
            color_eliminar, color_eliminar_hv= accent, hv_accent
            color_neutro, color_neutro_hv= accent, hv_accent

        qss= f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_btn};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QMainWindow, QWidget {{
                background-color: {bg_window};
                color: {txt_prim};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            {qss_labels_accesibilidad}
            QFrame#LeftPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_sidebar}, stop:1 {sidebar_gradiente_fin});
                border-right: 1px solid {sidebar_borde};
            }}
            QFrame#Cabecera {{ background: transparent; }}
            QLabel#InsigniaLogo {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {hv_accent});
                border-radius: 12px;
                font-size: 18px;
            }}
            QLabel#MarcaTitulo {{
                font-size: 17px;
                font-weight: 800;
                color: {txt_sidebar_prim};
                background: transparent;
            }}
            QLabel#MarcaSubtitulo {{
                font-size: 10px;
                font-weight: 600;
                color: {txt_sidebar_sec};
                background: transparent;
            }}
            QPushButton#BtnColapsar {{
                background-color: {bg_sidebar_btn};
                color: {txt_sidebar_sec};
                border: none;
                border-radius: 12px;
                font-weight: 900;
            }}
            QPushButton#BtnColapsar:hover {{
                background-color: {accent};
                color: white;
            }}
            QFrame#LineaAcento {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:0.5 {accent_suave}, stop:1 transparent);
                border: none;
                margin: 0px 18px;
            }}
            QFrame#TarjetaPerfil {{
                background-color: {bg_sidebar_btn};
                border: 1px solid {sidebar_borde};
                border-radius: 12px;
                margin: 14px 14px 4px 14px;
            }}
            QLabel#AvatarPerfil {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {hv_accent});
                color: white;
                font-weight: 800;
                font-size: 13px;
                border-radius: 19px;
            }}
            QLabel#PerfilNombre {{
                font-size: 12px;
                font-weight: 700;
                color: {txt_sidebar_prim};
                background: transparent;
            }}
            QLabel#PerfilRol {{
                font-size: 10px;
                color: {txt_sidebar_sec};
                background: transparent;
            }}
            QFrame#PildoraBusqueda {{
                background-color: {bg_sidebar_btn};
                border: 1px solid {sidebar_borde};
                border-radius: 16px;
                margin: 10px 14px 0px 14px;
                min-height: 34px;
                max-height: 34px;
            }}
            QLabel#IconoBusqueda {{
                color: {txt_sidebar_sec};
                font-size: 15px;
                background: transparent;
            }}
            QLineEdit#BusquedaGlobal {{
                background: transparent;
                border: none;
                color: {txt_sidebar_prim};
                font-size: 12px;
            }}
            QListWidget#NavList {{
                background: transparent;
                border: none;
                outline: 0;
                padding: 6px 0px;
            }}
            QListWidget#NavList::item {{
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
            QFrame#PildoraNav {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {hv_accent});
                border-radius: 10px;
            }}
            QWidget#ModuloNavItem {{ background: transparent; }}
            QWidget#ModuloNavItem:hover {{
                background-color: {accent_suave};
                border-radius: 10px;
            }}
            QLabel#SeccionEyebrow {{
                font-size: 10px;
                font-weight: 800;
                color: {txt_sidebar_sec};
                background: transparent;
                padding-top: 6px;
            }}
            QLabel#NavIconChip {{
                background-color: {bg_sidebar_btn};
                color: {txt_sidebar_sec};
                border-radius: 9px;
                font-size: 15px;
            }}
            QLabel#NavIconChip[activo="true"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}, stop:1 {hv_accent});
                color: white;
            }}
            QLabel#NavTexto {{
                font-size: 13px;
                color: {txt_sidebar_sec};
                background: transparent;
            }}
            QLabel#NavTexto[activo="true"] {{
                color: {txt_sidebar_prim};
                font-weight: 700;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {bg_sidebar_btn};
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {bg_sidebar_btn_hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {bg_sidebar_btn};
                border-radius: 3px;
                min-width: 24px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {bg_sidebar_btn_hover}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
            QLabel#TituloModulo {{
                font-size: 30px;
                font-weight: bold;
                background-color: transparent;
            }}
            QLabel#DescModulo {{
                font-size: 15px;
                color: {txt_sec};
                background-color: transparent;
            }}
            QLabel#TemaTexto {{
                font-size: 12px;
                font-weight: 600;
                color: {txt_sidebar_sec};
                background: transparent;
            }}

            QPushButton#BtnCerrarSesion {{
                background-color: transparent;
                color: {txt_sidebar_sec};
                border: 1px solid {sidebar_borde};
                border-radius: 8px;
                padding: 9px 14px;
                text-align: left;
                font-weight: 600;
            }}
            QPushButton#BtnCerrarSesion:hover {{
                background-color: #EF4444;
                border-color: #EF4444;
                color: white;
            }}
            QFrame#TarjetaIndicador {{
                background-color: {bg_panel};
                border: 1px solid {bg_btn};
                border-radius: 10px;
            }}
            QLabel#TarjetaIcono {{ font-size: 22px; background: transparent; }}
            QLabel#TarjetaValor {{ font-size: 26px; font-weight: 800; color: {accent}; background: transparent; }}
            QLabel#TarjetaTitulo {{ font-size: 12px; color: {txt_sec}; background: transparent; }}
            QTabWidget::pane {{
                border: 1px solid {bg_btn};
                border-top: none;
                border-radius: 0px 0px 8px 8px;
                background-color: {bg_panel};
                top: -1px;
            }}
            QTabWidget::tab-bar {{ left: 0px; alignment: left; }}
            QTabBar {{ background-color: transparent; border: none; }}
            QTabBar::tab {{
                background-color: transparent;
                color: {txt_sec};
                padding: 10px 20px;
                margin-right: 6px;
                border: none;
                border-bottom: 3px solid transparent;
                font-weight: 600;
                font-size: 14px;
                outline: none;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:hover {{
                color: {txt_prim};
                background-color: {bg_btn};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
            QTabBar::tab:selected {{
                color: {accent};
                border-bottom: 3px solid {accent};
                background-color: transparent;
                font-weight: bold;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {bg_panel};
                border: 1px solid {bg_btn};
                color: {txt_prim};
                padding: 6px;
                border-radius: 4px;
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: {bg_panel};
                border: 1px solid {bg_btn};
                color: {txt_prim};
                padding: 5px;
                border-radius: 4px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                background-color: {bg_btn};
                width: 16px;
                border: none;
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background-color: {hv_btn};
            }}
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hv_accent}; }}
            QPushButton:disabled {{ background-color: {bg_btn}; color: {txt_sec}; }}
            QPushButton#BtnAccionAgregar {{ background-color: {color_agregar}; }}
            QPushButton#BtnAccionAgregar:hover {{ background-color: {color_agregar_hv}; }}
            QPushButton#BtnAccionEditar {{ background-color: {color_editar}; }}
            QPushButton#BtnAccionEditar:hover {{ background-color: {color_editar_hv}; }}
            QPushButton#BtnAccionAjustar {{ background-color: {color_ajustar}; }}
            QPushButton#BtnAccionAjustar:hover {{ background-color: {color_ajustar_hv}; }}
            QPushButton#BtnAccionEliminar {{ background-color: {color_eliminar}; }}
            QPushButton#BtnAccionEliminar:hover {{ background-color: {color_eliminar_hv}; }}
            QPushButton#BtnAccionNeutro {{ background-color: {color_neutro}; }}
            QPushButton#BtnAccionNeutro:hover {{ background-color: {color_neutro_hv}; }}
            QTableWidget {{
                background-color: {bg_panel};
                alternate-background-color: {bg_btn};
                color: {txt_prim};
                gridline-color: {bg_btn};
                border: 1px solid {bg_btn};
                border-radius: 4px;
            }}
            QTableWidget::item {{ padding: 4px; }}
            QHeaderView::section {{
                background-color: {bg_btn};
                color: {txt_sec};
                padding: 5px;
                border: none;
                border-right: 1px solid {bg_panel};
                border-bottom: 1px solid {bg_panel};
                font-weight: bold;
            }}
            QTableCornerButton::section {{
                background-color: {bg_btn};
                border: none;
                border-right: 1px solid {bg_panel};
                border-bottom: 1px solid {bg_panel};
            }}
            QTableWidget::item:selected {{ background-color: {accent}; color: white; }}
            QScrollArea {{ background-color: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background-color: transparent; }}
            QDateEdit {{
                background-color: {bg_panel};
                border: 1px solid {bg_btn};
                color: {txt_prim};
                padding: 5px;
                border-radius: 4px;
            }}
            QRadioButton, QCheckBox {{ color: {txt_prim}; background-color: transparent; }}
            QGroupBox {{
                border: 1px solid {bg_btn};
                border-radius: 5px;
                margin-top: 15px;
                color: {txt_prim};
                background-color: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: {accent};
                font-weight: bold;
                background-color: transparent;
            }}
            QProgressBar {{
                border: 1px solid {bg_btn};
                border-radius: 4px;
                text-align: center;
                background-color: {bg_btn};
                color: {txt_prim};
            }}
            QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}
            QLabel#PreviewLogo {{ border: 2px dashed {bg_btn}; border-radius: 10px; color: {txt_sec}; }}
        """
        self.setStyleSheet(qss)

        #El bloque "QToolTip {...}" de arriba está dentro de self.setStyleSheet(qss), y un stylesheet puesto en UN
        #widget (aunque sea la ventana principal) solo cascada a sus DESCENDIENTES normales -no llega a ventanas de
        #nivel superior
        #aparte (diálogos, y también el popup interno que usa cada QComboBox para su
        #lista desplegable), ni se aplica de forma fiable al tooltip de un widget
        #DESHABILITADO (Qt no lo "pule" igual que a uno habilitado). Por eso, sin
        #importar cuántas veces se repita "QToolTip {...}" en cada módulo, siempre quedaban huecos: justo los que se
        #ven como el tooltip "feo" nativo de Qt (fondo blanco, texto negro), no por velocidad del mouse sino porque ese
        #tooltip en concreto nunca estuvo alcanzado por ningún stylesheet.
        #
        #La única hoja de estilo que Qt SÍ aplica de forma universal, a TODO widget de la aplicación sin excepción
        #(top-level o no, habilitado o no, dentro de un popup de combo o no) es la de QApplication.setStyleSheet(...).
        #Fijar ahí -y solo ahí- la regla del tooltip resuelve el problema de raíz en un único lugar, en vez de
        #perseguir casos sueltos por todo el código.
        app= QApplication.instance()
        if app is not None:
            app.setStyleSheet(f"""
                QToolTip {{
                    background-color: {bg_panel};
                    color: {txt_prim};
                    border: 1px solid {bg_btn};
                    padding: 6px 10px;
                    border-radius: 6px;
                }}
            """)
            #Además de la QSS de arriba, se fija también la QPalette de la app (incluido el grupo Disabled) como respaldo:
            #por si algún estilo de plataforma decide resolver el tooltip por paleta en vez de por QSS, queda igualmente en
            #tono con el tema actual.
            paleta_app= app.palette()
            for grupo in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                          QPalette.ColorGroup.Disabled):
                paleta_app.setColor(grupo, QPalette.ColorRole.ToolTipBase, QColor(bg_panel))
                paleta_app.setColor(grupo, QPalette.ColorRole.ToolTipText, QColor(txt_prim))
            app.setPalette(paleta_app)

    #Recorrido síncrono de páginas (con processEvents() como respiro
    #entre una y otra) para la versión completa de aplicar_tema() -ver
    #_aplicar_tema_impl-. NO la usa el toggle animado de modo
    #claro/oscuro: para ese caso está _refrescar_paginas_tema_async, que
    #troza el trabajo con QTimer.singleShot(0, ...) en vez de
    #processEvents() -ver el porqué en el docstring de
    #_terminar_cambio_tema-.
    def _refrescar_paginas_tema_sincrono(self):

        for i in range(self.stacked_widget.count()):
            pagina= self.stacked_widget.widget(i)
            if hasattr(pagina, "actualizar_tema"):
                pagina.actualizar_tema()
            #Respiro para el bucle de eventos entre página y página: cada
            #actualizar_tema() puede ser bastante trabajo (reconstruir QSS,
            #refrescar iconos, repoblar tablas completas) y, sumado en todos los módulos que ya se hayan construido en la
            #sesión (Calendario, Politécnico, Reportes -incluyendo su pesado editor si se abrió-, Configuración, etc.),
            #puede tardar varios cientos de milisegundos. Sin este respiro, Windows deja de recibir mensajes de la ventana
            #durante todo ese tramo y la marca como "no responde": ahí aparece el cursor de carga y la ventana se ve
            #congelada, aunque la animación de opacidad en sí ya haya terminado. OJO: sin el flag ExcludeUserInputEvents,
            #processEvents() también redelivera eventos de mouse/teclado/tooltip en cola. Si el cursor está quieto sobre un
            #widget con tooltip mientras se recorren las páginas, Qt reinserta QEvent.Type.ToolTip en cada vuelta y cada
            #uno atraviesa TODA la cadena de filtros globales (alarmas.py, atajos.py x2, este mismo filtro de tooltips e
            #iconos_auto.py). Con varias páginas cargadas eso anida
            #processEvents() dentro de sí mismo sin desenrollarse nunca,
            #dejando la app congelada. Excluyendo eventos de entrada se seguí dando el respiro de pintura/ventana que este
            #bucle necesita, sin reabrir ese ciclo.
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        #El menú de la bandeja tiene su propio QSS calcado del tema actual (ver _reconstruir_menu_bandeja); si no se
        #reconstruye aquí, tras cambiar de tema o de modo claro/oscuro se quedaría con los colores viejos hasta el
        #próximo reinicio.
        self._reconstruir_menu_bandeja()

    #LOGIN
    def mostrar_login(self):

        login= LoginWindow(self)
        resultado= login.exec()

        if resultado == login.DialogCode.Accepted:
            self.usuario_actual= login.usuario_actual
            self.rol_actual= login.rol_actual
            self.id_usuario_actual= login.id_usuario_actual
            self.nombre_usuario= login.nombre_completo
            #Preferencia personal del docente (checkbox en Configuración ▸ Mi Cuenta): si quiere ver "Calificaciones
            #Técnicas" en su menú. Solo aplica al rol Profesor; se relee en cada login por si se cambió desde otro equipo
            #con el mismo usuario.
            #
            #EXCEPCIÓN: si la institución es un Politécnico (o "Personalizado" con el módulo Politécnico activado), se
            #asume que trabajar con módulos técnicos es la norma, no la excepción — así que se activa automáticamente para
            #todos los docentes, hayan tocado o no el checkbox. Esto no pisa ni borra la preferencia guardada del usuario:
            #si la institución deja de ser Politécnico, vuelve a mandar lo que el docente eligió manualmente.
            tipo_inst_login, personalizados_inst_login= self._tipo_institucion()
            es_politecnico_inst= (tipo_inst_login == "Politécnico"
                                    or (tipo_inst_login == "Personalizado"
                                        and "Politécnico" in personalizados_inst_login))
            self.mostrar_calif_tecnicas= es_politecnico_inst or obtener_preferencia_calif_tecnicas(self)

            self._actualizar_avatar_visual()
            self.lbl_usuario_logueado.setText(self.nombre_usuario)
            self.lbl_perfil_rol.setText(self.rol_actual)
            self.tarjeta_perfil.setVisible(True)
            self.btn_cerrar_sesion.setVisible(True)
            #IMPORTANTE: no basta con _aplicar_permisos_por_rol() (eso solo oculta/muestra ítems del menú lateral). Módulos
            #como Reportes o Configuración deciden QUÉ PESTAÑAS internas construir según el rol en el momento en que se
            #instancian -y si el usuario ya había entrado antes con otro rol en esta misma sesión de la
            #app (o cambia de cuenta con "Cerrar sesión" sin reiniciar el
            #programa), esos módulos ya estaban construidos y CACHEADOS con las pestañas del rol anterior; cerrar_sesion()
            #nunca los reconstruye. recargar_modulos_dinamicos() bota esos módulos ya
            #cargados (los deja como placeholders) para que se reconstruyan
            #desde cero -con las pestañas correctas- la próxima vez que se visiten, y de paso ya llama a
            #_aplicar_permisos_por_rol().
            self.recargar_modulos_dinamicos()
            self._reconstruir_menu_bandeja()
            #Animación de bienvenida (anillo + logo + check + texto) como transición vistosa justo antes de que la ventana
            #principal termine de abrirse, seguida del mensaje de éxito de siempre.
            mostrar_bienvenida_animada(self, self.nombre_usuario, self.rol_actual)
            mostrar_mensaje("exito", "Acceso Concedido",
                           f"Bienvenido/a, {self.nombre_usuario}.\nHas iniciado sesión correctamente como {self.rol_actual}.",
                           self)
            #Tutorial de primer uso (general y/o de Modo Docente, según el rol). No bloquea nada si el usuario ya lo vio o
            #elige saltarlo; ver tutoriales.py para el detalle de cuándo se ofrece cada uno.
            ofrecer_tutoriales_tras_login(self)
            return True
        return False

    #Muestra la ventana principal maximizada con una aparición suave
    #(fundido de opacidad), como cierre natural de la animación de
    #bienvenida en vez de un salto brusco a la pantalla completa.
    def abrir_con_fundido(self):

        self.setWindowOpacity(0.0)
        self.showMaximized()
        self._anim_apertura= QPropertyAnimation(self, b"windowOpacity")
        self._anim_apertura.setDuration(380)
        self._anim_apertura.setStartValue(0.0)
        self._anim_apertura.setEndValue(1.0)
        self._anim_apertura.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_apertura.start()

    def cerrar_sesion(self):

        resp= mostrar_mensaje("pregunta", "Cerrar Sesión",
                               f"¿Está seguro de cerrar la sesión de {self.usuario_actual}?", self)
        if resp != QMessageBox.StandardButton.Yes:
            return

        registrar_auditoria("Sistema", "Cierre de sesión", self.usuario_actual, f"Rol: {self.rol_actual}")

        self.usuario_actual= None
        self.rol_actual= None
        self.id_usuario_actual= None
        self.nombre_usuario= None
        self.lbl_avatar.setPixmap(QPixmap())
        self.lbl_avatar.setText("?")
        self.tarjeta_perfil.setVisible(False)
        self.btn_cerrar_sesion.setVisible(False)
        self._reconstruir_menu_bandeja()

        self.hide()

        if not self.mostrar_login():
            #El usuario canceló el login tras cerrar sesión: aquí sí queremos terminar el proceso de verdad, no ocultarlo a
            #la
            #bandeja (closeEvent normalmente solo oculta la ventana).
            self._salir_de_verdad()
        else:
            #Mismo fundido de apertura que en el arranque de la app (ver abrir_con_fundido / window.abrir_con_fundido() al
            #final del archivo): antes aquí se llamaba showMaximized() directo, así que solo el primer login de la sesión
            #de la app tenía fundido; cerrar sesión y volver a entrar (con cualquier cuenta) aparecía de golpe, sin la
            #animación.
            self.abrir_con_fundido()

    #Avatar de perfil (foto o iniciales)
    def _abrir_menu_avatar(self, evento=None):

        if not self.id_usuario_actual:
            return
        menu= QMenu(self)
        menu.addAction(icono_emoji("✂"), "Elegir y recortar foto…", self._cambiar_foto_avatar)
        menu.addAction("Usar iniciales", self._quitar_foto_avatar)
        menu.exec(self.lbl_avatar.mapToGlobal(self.lbl_avatar.rect().bottomLeft()))

    def _cambiar_foto_avatar(self):

        destino_dir= os.path.join(obtener_carpeta_datos(), "fotos")
        destino= seleccionar_y_recortar_foto(self, destino_dir, prefijo="usr")
        if not destino:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE usuarios SET foto=? WHERE id=?", (destino, self.id_usuario_actual))
        conn.commit()
        conn.close()
        registrar_auditoria("Sistema", "Actualizó foto de perfil", self.usuario_actual, "")
        self._actualizar_avatar_visual()

    def _quitar_foto_avatar(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE usuarios SET foto=? WHERE id=?", ("", self.id_usuario_actual))
        conn.commit()
        conn.close()
        self._actualizar_avatar_visual()

    def _generar_pixmap_circular(self, ruta, tamano=38):

        origen= QPixmap(ruta)
        if origen.isNull():
            return None
        origen= origen.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
        pos_x= max(0, (origen.width() - tamano) // 2)
        pos_y= max(0, (origen.height() - tamano) // 2)
        origen= origen.copy(pos_x, pos_y, tamano, tamano)
        resultado= QPixmap(tamano, tamano)
        resultado.fill(Qt.GlobalColor.transparent)
        pintor= QPainter(resultado)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        ruta_circular= QPainterPath()
        ruta_circular.addEllipse(0, 0, tamano, tamano)
        pintor.setClipPath(ruta_circular)
        pintor.drawPixmap(0, 0, origen)
        pintor.end()
        return resultado

    def _actualizar_avatar_visual(self):

        foto= ""
        if self.id_usuario_actual:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT foto FROM usuarios WHERE id=?", (self.id_usuario_actual,))
            fila= c.fetchone()
            conn.close()
            foto= (fila["foto"] if fila else "") or ""
        if foto and os.path.exists(foto):
            pixmap= self._generar_pixmap_circular(foto, 38)
            if pixmap is not None:
                self.lbl_avatar.setText("")
                self.lbl_avatar.setPixmap(pixmap)
                self._reconstruir_menu_bandeja()
                return
        iniciales= "".join(p[0] for p in (self.nombre_usuario or "").split()[:2]).upper() or "?"
        self.lbl_avatar.setPixmap(QPixmap())
        self.lbl_avatar.setText(iniciales)
        self._reconstruir_menu_bandeja()

    #CONFIGURACIÓN JSON
    def cargar_configuracion(self):

        try:

            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg= json.load(f)
                self.tema_actual= cfg.get("theme", "Colorful (Multicolor)")
                self.modo_oscuro= cfg.get("modo_oscuro", True)
                self.requerir_login= cfg.get("requerir_login", True)
                self.recordar_usuario= cfg.get("recordar_usuario", False)
                self.ultimo_usuario= cfg.get("ultimo_usuario", "")
                self.login_translucido= cfg.get("login_translucido", True)
                self.modo_trabajo= cfg.get("modo_trabajo", "Local")
                self.carpeta_sincronizacion= cfg.get("carpeta_sincronizacion", "")
                self.sync_ultimo_hash= cfg.get("sync_ultimo_hash", "")
                self.sync_ultima_fecha= cfg.get("sync_ultima_fecha", "")
                self.formato_hora= cfg.get("formato_hora", "24h")
                self.formato_fecha= cfg.get("formato_fecha", "dmy")
                self.etiquetas_con_recuadro= cfg.get("etiquetas_con_recuadro", False)
                self.accesibilidad_texto_grande= cfg.get("accesibilidad_texto_grande", False)
                self.accesibilidad_bordes_remarcados= cfg.get("accesibilidad_bordes_remarcados", False)
                self.minimizar_a_bandeja= cfg.get("minimizar_a_bandeja", True)
                self.tecla_atajos= cfg.get("tecla_atajos", TECLA_ATAJO_POR_DEFECTO)
                if self.tecla_atajos not in TECLAS_ATAJO_DISPONIBLES:
                    self.tecla_atajos= TECLA_ATAJO_POR_DEFECTO
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.tema_actual= "Colorful (Multicolor)"
            self.modo_oscuro= True
            self.requerir_login= True
            self.recordar_usuario= False
            self.ultimo_usuario= ""
            self.login_translucido= True
            self.modo_trabajo= "Local"
            self.carpeta_sincronizacion= ""
            self.sync_ultimo_hash= ""
            self.sync_ultima_fecha= ""
            self.formato_hora= "24h"
            self.formato_fecha= "dmy"
            self.etiquetas_con_recuadro= False
            self.accesibilidad_texto_grande= False
            self.accesibilidad_bordes_remarcados= False
            self.minimizar_a_bandeja= True
            self.tecla_atajos= TECLA_ATAJO_POR_DEFECTO

    def guardar_configuracion(self):

        cfg= {
            "theme": self.tema_actual,
            "modo_oscuro": self.modo_oscuro,
            "requerir_login": getattr(self, 'requerir_login', True),
            "recordar_usuario": getattr(self, 'recordar_usuario', False),
            "ultimo_usuario": getattr(self, 'ultimo_usuario', ""),
            "login_translucido": getattr(self, 'login_translucido', True),
            "modo_trabajo": getattr(self, 'modo_trabajo', "Local"),
            "carpeta_sincronizacion": getattr(self, 'carpeta_sincronizacion', ""),
            "sync_ultimo_hash": getattr(self, 'sync_ultimo_hash', ""),
            "sync_ultima_fecha": getattr(self, 'sync_ultima_fecha', ""),
            "formato_hora": getattr(self, 'formato_hora', "24h"),
            "formato_fecha": getattr(self, 'formato_fecha', "dmy"),
            "etiquetas_con_recuadro": getattr(self, 'etiquetas_con_recuadro', False),
            "accesibilidad_texto_grande": getattr(self, 'accesibilidad_texto_grande', False),
            "accesibilidad_bordes_remarcados": getattr(self, 'accesibilidad_bordes_remarcados', False),
            "minimizar_a_bandeja": getattr(self, 'minimizar_a_bandeja', True),
            "tecla_atajos": getattr(self, 'tecla_atajos', TECLA_ATAJO_POR_DEFECTO),
        }
        try:

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
        except OSError as error:
            print(f"Error al guardar configuración: {error}")

    def showEvent(self, evento):

        super().showEvent(evento)
        QTimer.singleShot(0, lambda: self._mover_pildora_nav(self.nav_list.currentRow(), animar=False))
        #Al volver desde la bandeja, reactivamos lo que pausamos en
        #hideEvent (ver ahí el porqué).
        if getattr(self, "punto_estado", None) is not None:
            self.punto_estado.reanudar()
        self._pausar_reanudar_modulos_en_segundo_plano(pausar=False)

    def hideEvent(self, evento):

        super().hideEvent(evento)
        #Cuando "Ejecutar en segundo plano al cerrar" está activo, closeEvent llama a self.hide() en vez de destruir la
        #ventana: la app sigue viva pero sin nada visible. Sin este pausar(), el punto verde de "sesión activa"
        #seguiría animándose (repintando) para siempre en segundo plano, gastando CPU/GPU por una animación que nadie
        #ve. Lo pausamos aquí y lo reanudamos en showEvent al reabrir.
        if getattr(self, "punto_estado", None) is not None:
            self.punto_estado.pausar()
        self._pausar_reanudar_modulos_en_segundo_plano(pausar=True)

    #Recorre todas las páginas ya creadas del stacked widget (Dashboard,
    #y cualquier otro módulo futuro) y detiene/reactiva sus temporizadores
    #de refresco automático (relojes en vivo, autorefresh periódico,
    #etc.) cuando la ventana se oculta/reaparece desde la bandeja.
    #
    #Usamos duck typing (pausar_actualizaciones/reanudar_actualizaciones)
    #en vez de importar cada módulo aquí, para no acoplar main.py a la
    #lista de módulos: cualquier módulo que defina esos dos métodos queda
    #cubierto automáticamente, sin tener que tocar este archivo de nuevo.
    def _pausar_reanudar_modulos_en_segundo_plano(self, pausar):

        if not hasattr(self, "stacked_widget"):
            return
        metodo= "pausar_actualizaciones" if pausar else "reanudar_actualizaciones"
        for i in range(self.stacked_widget.count()):
            pagina= self.stacked_widget.widget(i)
            funcion= getattr(pagina, metodo, None)
            if callable(funcion):
                try:

                    funcion()
                except Exception as error:
                    print(f"No se pudo {'pausar' if pausar else 'reanudar'} actualizaciones de {pagina}: {error}")

    def resizeEvent(self, evento):

        super().resizeEvent(evento)
        if hasattr(self, "nav_list"):
            self._mover_pildora_nav(self.nav_list.currentRow(), animar=False)
        if hasattr(self, "motor_alarmas"):
            self.motor_alarmas.reposicionar()

    def closeEvent(self, evento):

        if hasattr(self, "motor_alarmas"):
            self.motor_alarmas.detener_motor()
        #Si hay bandeja de sistema disponible, el usuario tiene activada la preferencia "Ejecutar en segundo plano al
        #cerrar" (configurable en Configuración ▸ Apariencia o desde el propio icono de la bandeja), y no se pidió
        #explícitamente "Salir", la 'X' de la ventana solo oculta la app (sigue viva en segundo plano), igual que
        #Discord/Spotify/Avast. Si el usuario desactivó esa preferencia, la 'X' cierra la aplicación normalmente. El
        #cierre real siempre puede forzarse desde _salir_de_verdad().
        if (getattr(self, "tray_icon", None) is not None
                and getattr(self, "minimizar_a_bandeja", True)
                and not self._saliendo_de_verdad):
            evento.ignore()
            self.hide()
            if self.tray_icon.supportsMessages():
                self.tray_icon.showMessage(
                    "AcaDeXI sigue activo",
                    "La aplicación se está ejecutando en segundo plano. "
                    "Haz doble clic en este icono para volver a abrirla.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            return

        try:

            ejecutar_backup_al_cerrar()
        except Exception as error:
            print(f"Backup al cerrar fallido: {error}")
        super().closeEvent(evento)
        #Cierre REAL ('X' con "Ejecutar en segundo plano" desactivado, o botón "Salir"): como la app arranca con
        #setQuitOnLastWindowClosed(False) (necesario para el patrón de bandeja), cerrar la última ventana NO hace
        #retornar app.exec() — el proceso quedaba vivo e invisible y parecía que "siguiera en segundo plano" aunque el
        #punto estuviera en rojo. Hay que pedir el quit() explícitamente, igual que hace
        #_salir_de_verdad().
        QApplication.instance().quit()


def wizard_completado():

    if edicion_actual() == "single_teacher":
        try:

            from src.nucleo import bd_single_teacher
            return bd_single_teacher.wizard_completado()
        except Exception:
            return False
    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT wizard_completado FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        return bool(fila and fila["wizard_completado"])
    except Exception:
        return False


#Corrige un problema de caché de estilo del propio Qt: el widget
#QToolTip es UNO SOLO, compartido por toda la aplicación y reutilizado
#para cada tooltip que se muestra. Cuando el mouse pasa RÁPIDO de un
#widget con tooltip a otro (p. ej. entre varios combos seguidos), Qt
#encadena el siguiente tooltip de forma "instantánea" (sin el pequeño
#retraso inicial) reutilizando ese mismo widget/label sin darle tiempo a
#repintarse con el QSS del tema actual -a veces se queda pintado con el
#estilo nativo de Qt (fondo blanco, texto negro) en vez del oscuro/claro
#de AcaDeXI, que es justo lo que se reportó: tooltips que "no se ven
#mal" pero no son el que queremos, y que dependen de la velocidad con la
#que se mueve el mouse, no de qué pantalla o widget se trate.
#
#OJO: Qt reenvía QEvent.Type.ToolTip repetidamente MIENTRAS el cursor
#sigue sobre el MISMO widget (cada vez que se mueve un pixel dentro de
#él), no solo la primera vez. Por eso NO se puede llamar
#QToolTip.hideText() en cada evento sin condición: eso cierra el
#tooltip contra el propio widget en el que el cursor sigue quieto,
#dándole apenas un parpadeo en vez de dejarlo abierto. Solo hace falta
#"limpiar" el tooltip anterior cuando el widget que lo pide CAMBIÓ
#respecto al último evento -es decir, justo al saltar de un elemento a
#otro-, que es el único momento en el que Qt reutiliza el widget
#reciclado sin repintarlo.
class _FiltroTooltipsFrescos(QObject):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._ultimo_widget= None

    def eventFilter(self, watched, evento):

        if evento.type() == QEvent.Type.ToolTip:
            if watched is not self._ultimo_widget and QToolTip.isVisible():
                #OJO: NO se puede llamar QToolTip.hideText() aquí mismo, de forma síncrona, dentro del propio manejo del evento
                #ToolTip. Ocultar el tooltip "en caliente" hace que Qt, como el mouse sigue quieto sobre el widget, vuelva a
                #pedir el tooltip DE INMEDIATO -mismo evento, mismo ciclo-, lo que dispara un nuevo QEvent.Type.ToolTip que
                #pasa otra vez por TODOS los event filters globales de la
                #app (Alarmas, Atajos, este mismo...) y así sin parar:
                #una recursión infinita entre filtros que nunca termina
                #sola (el "KeyboardInterrupt" de la consola era justo eso
                #cortado a la fuerza, no un choque real entre módulos). Con QTimer.singleShot(0, ...) el hideText() se ejecuta
                #en el siguiente tick del event loop -ya no dentro del mismo evento que lo disparó-, así deja de ser
                #reentrante.
                QTimer.singleShot(0, QToolTip.hideText)
            self._ultimo_widget= watched
        elif evento.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
            if watched is self._ultimo_widget:
                self._ultimo_widget= None
        return False


#Punto de entrada de la aplicación (lo invoca el main.py de la raíz).
def main():

    #Silencia únicamente el aviso de Windows "Unable to set geometry"
    #que Qt imprime cuando, al reposicionar/centrar un diálogo (por
    #ejemplo el recorte de foto), el sistema ajusta la ventana 1-2px
    #para respetar el tamaño mínimo que Windows exige para su marco.
    #Es un aviso puramente cosmético -no cambia el comportamiento ni
    #el tamaño real visible del diálogo-, así que en vez de dejarlo
    #ensuciar la consola en cada cierre se descarta aquí. Cualquier
    #otro mensaje de Qt (advertencias/errores que sí importan) se
    #sigue imprimiendo con normalidad.
    def _filtrar_avisos_qt_inofensivos(tipo_msg, contexto, mensaje):

        if "Unable to set geometry" in mensaje and "QWindowsWindow" in mensaje:
            return
        if tipo_msg == QtMsgType.QtDebugMsg:
            return
        sys.stderr.write(mensaje + "\n")

    qInstallMessageHandler(_filtrar_avisos_qt_inofensivos)

    app= QApplication(sys.argv)

    _filtro_tooltips_frescos= _FiltroTooltipsFrescos(app)
    app.installEventFilter(_filtro_tooltips_frescos)

    _guarda_instancia= GuardaInstanciaUnica()
    if not _guarda_instancia.es_primera_instancia:
        #Ya hay una copia de AcaDeXI corriendo (posiblemente minimizada a la bandeja): le avisamos que se muestre y
        #este proceso nuevo termina de inmediato, sin crear una segunda ventana ni un segundo icono de bandeja.
        _guarda_instancia.avisar_instancia_existente()
        sys.exit(0)

    #Crea las tablas si no existen y aplica las migraciones de esquema (columnas nuevas, índices, etc.) ANTES de
    #abrir cualquier ventana. Sin esto, la base de datos se queda con el esquema viejo y módulos como Observaciones
    #fallan con "no such column" al intentar usar columnas que bd.py agrega dinámicamente (materia_id, naturaleza,
    #...).
    inicializar_bd()

    app.setWindowIcon(icono_app())
    #Iconización automática y coherente de TODA la app: un filtro global que asigna (sin sobreescribir los
    #manuales) un icono vectorial a cualquier botón/pestaña/diálogo que quede sin uno, según su texto y con un
    #único mapa semántico compartido por todos los módulos.
    from src.nucleo.iconos_auto import instalar_iconos_automaticos
    instalar_iconos_automaticos(app)
    #Crítico para el patrón "bandeja de sistema": sin esto, Qt cerraría la app automáticamente en cuanto se oculta
    #la última ventana visible (justo lo que hace closeEvent al minimizar a la bandeja), matando el proceso aunque
    #el usuario nunca pidió "Salir".
    app.setQuitOnLastWindowClosed(False)

    #Traduce al español los diálogos NATIVOS de Qt (el selector de color, el selector de archivos del sistema,
    #etc.), que por defecto vienen en inglés porque Qt trae sus propios textos separados de los nuestros. Si el
    #paquete de idioma no está disponible en la instalación de Qt del usuario, simplemente no se instala el
    #traductor y esos diálogos se ven en inglés como hasta ahora (no rompe nada).
    _traductor_qt= QTranslator(app)
    _ruta_traducciones= QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if _traductor_qt.load(QLocale("es_ES"), "qtbase", "_", _ruta_traducciones):
        app.installTranslator(_traductor_qt)

    window= MainWindow()
    #Mantenemos viva la referencia al guarda en la propia ventana para que no la recoja el recolector de basura
    #(QLocalServer dejaría de escuchar) y para poder restaurar la ventana cuando alguien intente abrir una segunda
    #copia de la app.
    window._guarda_instancia= _guarda_instancia
    _guarda_instancia.escuchar_segundas_instancias(window._restaurar_desde_bandeja)

    _edicion= edicion_actual()
    if not wizard_completado() and _edicion == "full":
        wizard= WizardConfiguracion(window)
        if wizard.exec() != wizard.DialogCode.Accepted:
            sys.exit(0)
        window.recargar_modulos_dinamicos()
        window.requerir_login= True
        window.guardar_configuracion()
    elif not wizard_completado() and _edicion == "single_teacher":
        from src.interfaz.single_teacher_ui import WizardSingleTeacher
        wizard= WizardSingleTeacher(window)
        if wizard.exec() != wizard.DialogCode.Accepted:
            sys.exit(0)
        window.recargar_modulos_dinamicos()
        window.requerir_login= False
        window.guardar_configuracion()
    elif not wizard_completado() and _edicion == "side_stepper":
        #TODO: WizardSideStepper (side_stepper_config.py) aún no verificado contra este código rediseñado -cae al
        #wizard institucional genérico mientras tanto, igual que "docentes" nunca lo necesita.
        wizard= WizardConfiguracion(window)
        if wizard.exec() != wizard.DialogCode.Accepted:
            sys.exit(0)
        window.recargar_modulos_dinamicos()
        window.requerir_login= True
        window.guardar_configuracion()
    elif _edicion == "single_teacher":
        window.requerir_login= False

    if window.requerir_login:
        if not window.mostrar_login():
            sys.exit(0)
    elif _edicion == "single_teacher":
        #Sin login (un solo docente, dueño de un solo archivo): el enganche normal de ofrecer_tutoriales_tras_login()
        #vive DENTRO de
        #mostrar_login(), que aquí nunca se llama.
        ofrecer_tutoriales_tras_login(window)

    try:

        ejecutar_backup_automatico_al_iniciar()
    except Exception as error:
        print(f"Backup automático fallido: {error}")

    window.abrir_con_fundido()
    sys.exit(app.exec())
