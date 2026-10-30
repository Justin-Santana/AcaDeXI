#Pantalla de bienvenida animada.
#
#Se muestra justo después de un inicio de sesión exitoso (ver
#`mostrar_login()` en main.py) y actúa como una transición elegante antes
#de que la ventana principal termine de abrirse por completo: el logo de
#la app aparece con un efecto de "pop"/rebote, luego el texto de
#bienvenida con el rol, y debajo el estado "Inicializando AcaDeXI" con una
#barra fina de carga que, al completarse, muestra un check (✓) a la
#derecha del texto. Finalmente todo se desvanece para dar paso a la app.

import os
import sys
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QApplication)
from PySide6.QtCore import (Qt, QRect, QRectF, QTimer, QEventLoop,
    QPropertyAnimation, QVariantAnimation, QEasingCurve, Property)
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap
from src.nucleo.rutas import obtener_carpeta_raiz, obtener_carpeta_iconos


NOMBRE_LOGO= "AcaDeXI_logo.png"

_AQUI= obtener_carpeta_raiz()

_CARPETA_ICONOS= obtener_carpeta_iconos()

_cache_ruta_logo= None

_cache_pixmap_logo= None

_ya_mostrada_en_esta_sesion_de_app= False

def _hex_a_rgba(hex_color, alpha):

    hex_color= hex_color.lstrip("#")
    r, g, b= int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Búsqueda del logo de la app (AcaDeXI_logo.png), con la misma filosofía de búsqueda por carpetas candidatas que
#usa iconos.py: carpeta "iconos", carpeta "_internal" (PyInstaller --onedir) y, además, la propia carpeta donde
#vive este archivo.


#Genera, en orden de prioridad, las carpetas donde puede estar el
#logo de la app, tanto en desarrollo como empaquetado con PyInstaller
#(--onedir). Sigue la misma lógica que `_carpetas_candidatas_iconos()`
#de iconos.py, agregando también la carpeta donde vive este archivo.
def _carpetas_candidatas_logo():

    candidatas= [_AQUI, _CARPETA_ICONOS]

    if getattr(sys, "frozen", False):
        meipass= getattr(sys, "_MEIPASS", None)
        if meipass:
            candidatas.append(os.path.join(meipass, "iconos"))
            candidatas.append(meipass)

        carpeta_exe= os.path.dirname(os.path.abspath(sys.executable))
        candidatas.append(os.path.join(carpeta_exe, "_internal", "iconos"))
        candidatas.append(os.path.join(carpeta_exe, "_internal"))
        candidatas.append(os.path.join(carpeta_exe, "iconos"))
        candidatas.append(carpeta_exe)

    vistas= set()
    resultado= []
    for c in candidatas:
        if c and c not in vistas:
            vistas.add(c)
            resultado.append(c)
    return resultado


def _ruta_logo():

    global _cache_ruta_logo
    if _cache_ruta_logo is not None:
        return _cache_ruta_logo
    ruta_encontrada= ""
    for carpeta in _carpetas_candidatas_logo():
        ruta= os.path.join(carpeta, NOMBRE_LOGO)
        if os.path.exists(ruta):
            ruta_encontrada= ruta
            break
    _cache_ruta_logo= ruta_encontrada
    return ruta_encontrada


#Carga (una sola vez, cacheado) el pixmap original del logo, o None
#si no se encontró el archivo en ninguna carpeta candidata.
def _pixmap_logo_base():

    global _cache_pixmap_logo
    if _cache_pixmap_logo is None:
        ruta= _ruta_logo()
        _cache_pixmap_logo= QPixmap(ruta) if ruta else QPixmap()
    return _cache_pixmap_logo if not _cache_pixmap_logo.isNull() else None


#Muestra la animación de bienvenida tras un login exitoso.
#
#Sólo se muestra UNA vez por cada apertura del programa: si el usuario
#cierra sesión y vuelve a iniciar sesión sin cerrar la app, esta
#llamada no hace nada (la bandera vive en memoria del proceso, así que
#se reinicia sola la próxima vez que se abra la app de verdad).
#
#Bloquea brevemente (con un QEventLoop local, igual que un diálogo
#modal) para que la secuencia se vea completa antes de que el flujo de
#main.py continúe hacia la apertura de la ventana principal.
def mostrar_bienvenida_animada(main_window, nombre, rol):

    global _ya_mostrada_en_esta_sesion_de_app
    if _ya_mostrada_en_esta_sesion_de_app:
        return
    _ya_mostrada_en_esta_sesion_de_app= True

    splash= SplashBienvenida(main_window, nombre or "usuario", rol or "")
    splash.mostrar_y_esperar()


#El logo de la app con un anillo de progreso alrededor y una entrada
#tipo "pop" (rebote). Si no se encuentra el archivo del logo, cae de
#vuelta a un emblema 🎓.
class _LogoAnimado(QWidget):

    def __init__(self, color_halo="#6366F1", diametro=112, parent=None):

        super().__init__(parent)
        self._diametro= diametro
        self.setFixedSize(diametro, diametro)
        self._color_halo= QColor(color_halo)
        self._progreso_anillo= 0.0    #0..1 -> barrido del arco (0° a 360°)
        self._escala_logo= 0.0        #0..~1.15 -> "pop" de entrada del logo (con rebote)

        self._pixmap_logo= None
        pixmap_base= _pixmap_logo_base()
        if pixmap_base is not None:
            #Sobremuestreo: escalamos a varias veces el tamaño final que se va a dibujar (y respetando su proporción real,
            #sin recortar el escudo) para que se vea nítido incluso cuando el "pop" de entrada lo agranda momentáneamente
            #por encima del 100%.
            factor_sobremuestreo= 4
            tam_render= int(diametro * factor_sobremuestreo)
            self._pixmap_logo= pixmap_base.scaled(
                tam_render, tam_render, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)

    def _leer_escala_logo(self):

        return self._escala_logo

    def _poner_escala_logo(self, valor):

        self._escala_logo= valor
        self.update()

    escalaLogo= Property(float, _leer_escala_logo, _poner_escala_logo)

    def _leer_anillo(self):

        return self._progreso_anillo

    def _poner_anillo(self, valor):

        self._progreso_anillo= valor
        self.update()

    progresoAnillo= Property(float, _leer_anillo, _poner_anillo)

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        margen= 6
        rect= QRect(margen, margen, self._diametro - margen * 2, self._diametro - margen * 2)
        cx, cy= self.width() / 2, self.height() / 2

        #Halo suave de fondo
        halo= QColor(self._color_halo)
        halo.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(rect)

        #Logo en el centro, con su proporción original intacta (sin recortarlo, para no perder ninguna parte del diseño
        #del escudo) y con un "pop" de entrada
        if self._escala_logo > 0:
            painter.save()
            radio_disponible= (rect.width() / 2) * 0.82
            escala= max(self._escala_logo, 0.0)

            painter.translate(cx, cy)
            painter.scale(escala, escala)
            painter.translate(-cx, -cy)

            if self._pixmap_logo is not None:
                tam_pix= self._pixmap_logo.size()
                lado_disponible= radio_disponible * 2
                proporcion= min(lado_disponible / tam_pix.width(),
                                  lado_disponible / tam_pix.height())
                w_destino= tam_pix.width() * proporcion
                h_destino= tam_pix.height() * proporcion
                destino= QRectF(cx - w_destino / 2, cy - h_destino / 2, w_destino, h_destino)
                painter.drawPixmap(destino, self._pixmap_logo, QRectF(self._pixmap_logo.rect()))
            else:
                #Sin logo disponible: emblema de respaldo
                fuente= painter.font()
                fuente.setPointSize(int(rect.width() * 0.32))
                painter.setFont(fuente)
                painter.setPen(self._color_halo)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "")
            painter.restore()

        #Anillo de progreso: drawArc mientras se dibuja (parcial) y drawEllipse una vez completo. drawArc con un
        #barrido de 360° exactos tiene un problema conocido en Qt: en vez de un círculo cerrado, lo renderiza
        #segmentado/entrecortado.
        pluma_anillo= QPen(self._color_halo, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pluma_anillo)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._progreso_anillo >= 0.999:
            painter.drawEllipse(rect)
        else:
            angulo_inicio= 90 * 16
            angulo_barrido= -int(360 * 16 * self._progreso_anillo)
            painter.drawArc(rect, angulo_inicio, angulo_barrido)


#Overlay de pantalla completa, sin bordes y translúcido, con una
#tarjeta centrada que muestra la animación de bienvenida.
class SplashBienvenida(QWidget):

    def __init__(self, main_window, nombre, rol):

        super().__init__(None)
        self.main_window= main_window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                             Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._loop= QEventLoop()
        self._construir_ui(nombre, rol)
        self._posicionar()

        self._efecto= QGraphicsOpacityEffect(self)
        self._efecto.setOpacity(0.0)
        self.setGraphicsEffect(self._efecto)

        #Ver mostrar_y_esperar(): evita que la secuencia arranque más de una vez.
        self._secuencia_iniciada= False

    def _colores_tema(self):

        try:

            paleta= self.main_window.theme_palettes.get(
                self.main_window.tema_actual, self.main_window.theme_palettes["Indigo"])
            idx= 1 if self.main_window.modo_oscuro else 0
            return {
                "bg_panel": paleta["display_bg"][idx],
                "txt_prim": paleta["text_primary"][idx],
                "txt_sec": paleta["text_secondary"][idx],
                "accent": paleta["btn_op_bg"][idx],
            }
        except Exception:
            return {"bg_panel": "#1E293B", "txt_prim": "#F8FAFC",
                    "txt_sec": "#94A3B8", "accent": "#6366F1"}

    def _construir_ui(self, nombre, rol):

        colores= self._colores_tema()

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.addStretch()
        fila= QHBoxLayout()
        fila.addStretch()

        self.tarjeta= QFrame()
        self.tarjeta.setObjectName("TarjetaBienvenida")
        self.tarjeta.setFixedWidth(360)
        sombra= QGraphicsDropShadowEffect()
        sombra.setBlurRadius(55)
        sombra.setOffset(0, 16)
        sombra.setColor(QColor(0, 0, 0, 150))
        self.tarjeta.setGraphicsEffect(sombra)

        layout_tarjeta= QVBoxLayout(self.tarjeta)
        layout_tarjeta.setContentsMargins(30, 36, 30, 30)
        layout_tarjeta.setSpacing(2)
        layout_tarjeta.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.circulo= _LogoAnimado(color_halo=colores["accent"], diametro=112)
        fila_circulo= QHBoxLayout()
        fila_circulo.addStretch()
        fila_circulo.addWidget(self.circulo)
        fila_circulo.addStretch()
        layout_tarjeta.addLayout(fila_circulo)
        layout_tarjeta.addSpacing(16)

        self.contenedor_texto= QWidget()
        layout_texto= QVBoxLayout(self.contenedor_texto)
        layout_texto.setContentsMargins(0, 0, 0, 0)
        layout_texto.setSpacing(3)

        self.lbl_titulo= QLabel(f"¡Bienvenido/a, {nombre}!")
        self.lbl_titulo.setObjectName("TituloBienvenida")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_titulo.setWordWrap(True)
        layout_texto.addWidget(self.lbl_titulo)

        self.lbl_subtitulo= QLabel(f"Sesión iniciada como {rol}" if rol else "Sesión iniciada correctamente")
        self.lbl_subtitulo.setObjectName("SubtituloBienvenida")
        self.lbl_subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_texto.addWidget(self.lbl_subtitulo)

        #OJO: aquí NO se aplica un QGraphicsOpacityEffect propio a este contenedor. Un efecto de opacidad anidado
        #(widget hijo con su propio efecto, dentro de esta ventana top-level translúcida que YA tiene su propio efecto
        #de opacidad para el fade in/out) no se repinta de forma fiable en Qt: el título y el check nunca llegaban a
        #verse por esto exactamente. El fade de la ventana completa ya le da la transición; este texto se muestra
        #directamente.
        layout_tarjeta.addWidget(self.contenedor_texto)
        layout_tarjeta.addSpacing(18)

        #Fila de estado ("Inicializando AcaDeXI" + check que aparece al terminar la carga, a la derecha del texto),
        #justo arriba de la barra de carga.
        self.fila_estado= QWidget()
        layout_estado= QHBoxLayout(self.fila_estado)
        layout_estado.setContentsMargins(0, 0, 0, 0)
        layout_estado.setSpacing(6)
        layout_estado.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.lbl_estado= QLabel("Inicializando AcaDeXI")
        self.lbl_estado.setObjectName("EstadoBienvenida")
        layout_estado.addWidget(self.lbl_estado)

        self.lbl_check_estado= QLabel("\u2713")
        self.lbl_check_estado.setObjectName("CheckEstado")
        #Mismo motivo que contenedor_texto: nada de efecto de opacidad anidado, simplemente arranca oculto y se hace
        #visible cuando
        #corresponde (ver _mostrar_check_estado).
        self.lbl_check_estado.setVisible(False)
        layout_estado.addWidget(self.lbl_check_estado)

        layout_tarjeta.addWidget(self.fila_estado)
        layout_tarjeta.addSpacing(8)

        self.barra= QFrame()
        self.barra.setObjectName("TrackBarra")
        self.barra.setFixedHeight(4)
        layout_tarjeta.addWidget(self.barra)

        self.relleno_barra= QFrame(self.barra)
        self.relleno_barra.setObjectName("RellenoBarra")
        self.relleno_barra.setGeometry(0, 0, 0, 4)

        fila.addWidget(self.tarjeta)
        fila.addStretch()
        layout_raiz.addLayout(fila)
        layout_raiz.addStretch()

        self.setStyleSheet(f"""
            QFrame#TarjetaBienvenida {{
                background-color: {_hex_a_rgba(colores['bg_panel'], 250)};
                border-radius: 20px;
            }}
            QLabel#TituloBienvenida {{
                color: {colores['txt_prim']}; font-size: 17px; font-weight: 800; background: transparent;
            }}
            QLabel#SubtituloBienvenida {{
                color: {colores['txt_sec']}; font-size: 12px; background: transparent;
            }}
            QLabel#EstadoBienvenida {{
                color: {colores['txt_sec']}; font-size: 12px; font-weight: 600; background: transparent;
            }}
            QLabel#CheckEstado {{
                color: #22C55E; font-size: 14px; font-weight: 800; background: transparent;
            }}
            QFrame#TrackBarra {{
                background-color: {_hex_a_rgba(colores['txt_sec'], 45)}; border-radius: 2px;
            }}
            QFrame#RellenoBarra {{
                background-color: {colores['accent']}; border-radius: 2px;
            }}
        """)

    def _posicionar(self):

        pantalla= QApplication.primaryScreen()
        geo= pantalla.availableGeometry() if pantalla else QRect(0, 0, 1280, 800)
        self.setGeometry(geo)

    #Muestra el overlay y bloquea (con un QEventLoop local, igual que
    #un diálogo modal) hasta que termina toda la secuencia de animación.
    def mostrar_y_esperar(self):

        self.show()
        self.raise_()
        self.activateWindow()

        #self.show() sólo le pide a Qt que muestre la ventana; no
        #garantiza que el compositor del sistema ya la haya pintado en pantalla. Forzamos aquí varias vueltas del bucle
        #de eventos + un repintado real ANTES de arrancar el fade-in, para que el primer frame que se anima ya sea uno
        #realmente visible.
        for _ in range(8):
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
            self.repaint()

        QTimer.singleShot(30, self._iniciar_secuencia)
        self._loop.exec()

    #---------------- SECUENCIA DE ANIMACIÓN ----------------
    def _iniciar_secuencia(self):

        if self._secuencia_iniciada:
            return
        self._secuencia_iniciada= True

        self._anim_fade_in= QPropertyAnimation(self._efecto, b"opacity")
        self._anim_fade_in.setDuration(260)
        self._anim_fade_in.setStartValue(0.0)
        self._anim_fade_in.setEndValue(1.0)
        self._anim_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_fade_in.start()
        QTimer.singleShot(220, self._animar_logo_y_carga)

    def _animar_logo_y_carga(self):

        #El anillo se dibuja alrededor, junto con el "pop" del logo
        self._anim_anillo= QPropertyAnimation(self.circulo, b"progresoAnillo")
        self._anim_anillo.setDuration(560)
        self._anim_anillo.setStartValue(0.0)
        self._anim_anillo.setEndValue(1.0)
        self._anim_anillo.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_anillo.start()

        #El logo aparece con un pequeño rebote ("pop")
        self._anim_logo= QPropertyAnimation(self.circulo, b"escalaLogo")
        self._anim_logo.setDuration(520)
        self._anim_logo.setStartValue(0.0)
        self._anim_logo.setEndValue(1.0)
        self._anim_logo.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim_logo.start()

        #Barra de "Inicializando AcaDeXI"; al completarse, aparece el check a la derecha del texto de estado.
        ancho_track= max(self.barra.width(), 1)
        self._anim_barra= QVariantAnimation(self)
        self._anim_barra.setDuration(1500)
        self._anim_barra.setStartValue(0.0)
        self._anim_barra.setEndValue(1.0)
        self._anim_barra.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim_barra.valueChanged.connect(
            #v: avance de la animación (0 a 1) sobre el ancho total de la barra
            lambda v: self.relleno_barra.setFixedWidth(int(ancho_track * v)))
        self._anim_barra.finished.connect(self._mostrar_check_estado)
        self._anim_barra.start()

    def _mostrar_check_estado(self):

        self.lbl_check_estado.setVisible(True)
        QTimer.singleShot(700, self._cerrar_con_fade)

    def _cerrar_con_fade(self):

        self._anim_fade_out= QPropertyAnimation(self._efecto, b"opacity")
        self._anim_fade_out.setDuration(380)
        self._anim_fade_out.setStartValue(1.0)
        self._anim_fade_out.setEndValue(0.0)
        self._anim_fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_fade_out.finished.connect(self._finalizar)
        self._anim_fade_out.start()

    def _finalizar(self):

        if self._loop.isRunning():
            self._loop.quit()
        self.close()
