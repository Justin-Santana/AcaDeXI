#Asistente de Configuración — Sincronización Directa (Fase B) de AcaDeXI.
#
#Guía paso a paso, dentro de la aplicación, para conectar uno de los métodos
#avanzados (Google Drive, Dropbox, OneDrive o Servidor institucional propio).
#Es un complemento visual a sync_backends.py: aquí solo se explica y se
#recolectan credenciales; la lógica de conexión real vive en ese módulo.
#
#Se abre desde Sincronización ▸ botón "🧭 Asistente de Configuración".
#
# -----------------------------------------
# capa visual: en vez de radio-buttons sueltos, la primera página usa
# -----------------------------------------
#tarjetas seleccionables con un indicador circular pintado a mano; cada
#página de backend usa una tarjeta de estado animada (spinner + sello ✓/✕
#pintados con QPainter) en vez de una etiqueta de texto plano; y las
#llamadas de red/OAuth de cada backend corren en un hilo aparte para que la
#ventana nunca se congele mientras se espera una respuesta (el flujo de
#OneDrive, por ejemplo, puede tardar minutos en lo que el usuario confirma
#en el navegador). El resto de la lógica de datos es la misma de siempre.
#
#Nota sobre los textos largos: antes las explicaciones extensas se pasaban
#a setSubTitle(), que en QWizard usa una franja de altura fija de una sola
#línea — el texto se veía cortado hasta que el usuario agrandaba la
#ventana manualmente. Ahora los subtítulos son frases cortas y el texto
#extenso vive en etiquetas con salto de línea (word-wrap) dentro del
#cuerpo de cada página, que siempre se ve completo sin importar el tamaño
#de la ventana.
import webbrowser

from PySide6.QtWidgets import (QWizard, QWizardPage, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QInputDialog, QPushButton, QFrame)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF, QPointF, Property, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, ICONO_ASISTENTE
from src.sincronizacion import sync_backends as avanzado
from src.sincronizacion.sincronizacion import (_crear_sombra, _hex_a_rgba, _animar_click, _fundido_entrada,
    SpinnerCircular, _HiloOperacionSync, exportar_paquete_servidor)
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji

ID_INTRO= 0
ID_GOOGLE= 1
ID_DROPBOX= 2
ID_ONEDRIVE= 3
ID_SERVIDOR= 4
ID_FINAL= 5


#Colores del tema activo de la app (mismo criterio que
#ModuloSincronizacion._paleta), para que el asistente combine con el modo
#claro/oscuro. Si no hay ventana principal disponible, usa una paleta
#neutra por defecto.
def _paleta(main_window):

    paletas= getattr(main_window, "theme_palettes", None)
    tema= getattr(main_window, "tema_actual", None)
    if not paletas or tema not in paletas:
        return {"accent": "#6366F1", "bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0",
                "txt_prim": "#0F172A", "txt_sec": "#64748B"}
    #p: paletas del tema activo; de aquí se leen los colores [claro, oscuro] que se eligen con idx.
    p= paletas[tema]
    idx= 1 if getattr(main_window, "modo_oscuro", False) else 0
    return {"accent": p["btn_op_bg"][idx], "bg_panel": p["display_bg"][idx],
            "bg_btn": p["btn_num_bg"][idx], "txt_prim": p["text_primary"][idx],
            "txt_sec": p["text_secondary"][idx]}


def _estilo_asistente(paleta):

    #p: la paleta recibida; abreviatura para interpolar sus colores en la hoja de estilo.
    p= paleta
    accent= p["accent"]
    return f"""
        QWizard {{ background-color: {p['bg_panel']}; }}
        QWizardPage {{ background-color: {p['bg_panel']}; }}
        QLabel {{ color: {p['txt_prim']}; background: transparent; }}
        QLineEdit {{
            padding: 9px 10px;
            border: 1.5px solid {p['bg_btn']};
            border-radius: 8px;
            background-color: {p['bg_panel']};
            color: {p['txt_prim']};
            selection-background-color: {accent};
        }}
        QLineEdit:focus {{ border: 1.5px solid {accent}; }}
        QPushButton {{
            padding: 9px 16px;
            border-radius: 9px;
            border: none;
            background-color: {p['bg_btn']};
            color: {p['txt_prim']};
            font-weight: 700;
        }}
        QPushButton:hover {{ background-color: {_hex_a_rgba(accent, 0.20)}; }}
        QPushButton:disabled {{ color: {p['txt_sec']}; }}
        QPushButton#BtnConectarAsistente {{
            background-color: {accent};
            color: #FFFFFF;
        }}
        QPushButton#BtnConectarAsistente:hover {{ background-color: {_hex_a_rgba(accent, 0.85)}; }}
        QPushButton#BtnConectarAsistente:disabled {{
            background-color: {_hex_a_rgba(accent, 0.35)};
            color: #FFFFFF;
        }}
    """


def _etiqueta_explicativa(texto):

    lbl= QLabel(texto)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setOpenExternalLinks(True)
    return lbl


#Indicador de selección (radio circular pintado a mano)
#Punto de selección tipo radio, dibujado con QPainter. El relleno
#interior aparece con una pequeña animación de 'pop' al marcarse, en vez
#de aparecer o desaparecer de golpe.
class _IndicadorRadio(QWidget):

    def __init__(self, color="#6366F1", parent=None):

        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._color= QColor(color)
        self._progreso= 0.0
        self._anim= QPropertyAnimation(self, b"progreso", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def _leer_progreso(self):

        return self._progreso

    def _poner_progreso(self, valor):

        self._progreso= valor
        self.update()

    progreso= Property(float, _leer_progreso, _poner_progreso)

    def poner_marcado(self, marcado, animar=True):

        self._anim.stop()
        destino= 1.0 if marcado else 0.0
        if not animar:
            self._progreso= destino
            self.update()
            return
        self._anim.setStartValue(self._progreso)
        self._anim.setEndValue(destino)
        self._anim.start()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen= 2.0
        rect= QRectF(margen, margen, self.width() - 2 * margen, self.height() - 2 * margen)
        pluma= QPen(self._color)
        pluma.setWidthF(1.6)
        painter.setPen(pluma)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        if self._progreso > 0.001:
            radio_max= rect.width() / 2 - 3.5
            radio= max(0.0, radio_max * self._progreso)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._color))
            painter.drawEllipse(rect.center(), radio, radio)


#Tarjeta de método (reemplaza los QRadioButton sueltos de la intro)
#Tarjeta seleccionable con icono, título y descripción corta, con
#una sombra que 'respira' al pasar el mouse y un rebote al hacer clic.
class _TarjetaMetodo(QFrame):

    clicked= Signal()

    def __init__(self, icono, titulo, subtitulo, color, paleta, parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaMetodo")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color= color
        self._paleta= paleta
        self._marcada= False
        self._sombra= _crear_sombra(color=color, blur=0, y=2, alpha=90)
        self.setGraphicsEffect(self._sombra)

        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(16, 12, 16, 12)
        disposicion.setSpacing(14)

        lbl_icono= QLabel()
        from src.nucleo.iconos_emoji import pixmap_emoji
        lbl_icono.setPixmap(pixmap_emoji(icono, 26))
        lbl_icono.setFixedSize(38, 38)
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icono.setObjectName("IconoTarjetaMetodo")
        disposicion.addWidget(lbl_icono)

        columna= QVBoxLayout()
        columna.setSpacing(1)
        lbl_titulo= QLabel(titulo)
        lbl_titulo.setObjectName("TituloTarjetaMetodo")
        columna.addWidget(lbl_titulo)
        lbl_subtitulo= QLabel(subtitulo)
        lbl_subtitulo.setObjectName("SubtituloTarjetaMetodo")
        lbl_subtitulo.setWordWrap(True)
        columna.addWidget(lbl_subtitulo)
        disposicion.addLayout(columna, 1)

        self.indicador= _IndicadorRadio(color=color)
        disposicion.addWidget(self.indicador, 0, Qt.AlignmentFlag.AlignVCenter)

        self._aplicar_estilo()

    def _aplicar_estilo(self):

        #p: paleta de la ventana, para pintar la tarjeta según esté marcada o no.
        p= self._paleta
        if self._marcada:
            fondo= _hex_a_rgba(self._color, 0.12)
            borde= self._color
        else:
            fondo= p["bg_panel"]
            borde= p["bg_btn"]
        self.setStyleSheet(f"""
            QFrame#TarjetaMetodo {{
                background-color: {fondo};
                border: 2px solid {borde};
                border-radius: 12px;
            }}
            QLabel#IconoTarjetaMetodo {{ font-size: 20px; background: transparent; }}
            QLabel#TituloTarjetaMetodo {{
                font-size: 14px; font-weight: 800; color: {p['txt_prim']}; background: transparent;
            }}
            QLabel#SubtituloTarjetaMetodo {{
                font-size: 11.5px; color: {p['txt_sec']}; background: transparent;
            }}
        """)

    def _animar_sombra(self, destino):

        anim= QPropertyAnimation(self._sombra, b"blurRadius", self)
        anim.setDuration(200)
        anim.setStartValue(self._sombra.blurRadius())
        anim.setEndValue(destino)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def poner_marcada(self, marcada, animar=True):

        self._marcada= marcada
        self._aplicar_estilo()
        self.indicador.poner_marcado(marcada, animar=animar)
        self._animar_sombra(26 if marcada else 0)

    def enterEvent(self, evento):

        super().enterEvent(evento)
        if not self._marcada:
            self._animar_sombra(14)

    def leaveEvent(self, evento):

        super().leaveEvent(evento)
        if not self._marcada:
            self._animar_sombra(0)

    def mousePressEvent(self, evento):

        super().mousePressEvent(evento)
        _animar_click(self)
        self.clicked.emit()


#PÁGINA 0: introducción y selección de método
class PaginaIntro(QWizardPage):

    METODOS_INFO= [
        ("google_drive", "☁", "Google Drive",
         "Recomendado si tu institución ya usa Google Workspace.", "#22C55E"),
        ("dropbox", "☁", "Dropbox",
         "Con una app propia registrada en Dropbox App Console.", "#3B82F6"),
        ("onedrive", "☁", "OneDrive / Microsoft 365",
         "Con una app propia registrada en Microsoft Entra ID.", "#0EA5E9"),
        ("servidor", "🖥", "Servidor institucional propio",
         "Se exporta con un clic; funciona incluso sin presupuesto de hosting.", "#F59E0B"),
    ]

    def __init__(self, main_window=None):

        super().__init__()
        self.setTitle("Sincronización Directa")
        self.setSubTitle("Elige qué método quieres configurar en este equipo.")
        paleta= _paleta(main_window)

        disposicion= QVBoxLayout(self)
        disposicion.setSpacing(12)
        disposicion.addWidget(_etiqueta_explicativa(
            "Esta es una alternativa avanzada a la carpeta compartida simple. Cada método "
            "requiere que tú (o tu institución) crees credenciales propias; AcaDeXI no "
            "incluye credenciales genéricas por seguridad. Puedes volver a ejecutar este "
            "asistente más tarde para configurar otro método adicional."))

        self._metodo_seleccionado= self.METODOS_INFO[0][0]
        self._tarjetas= []
        for clave, icono, titulo, subtitulo, color in self.METODOS_INFO:
            tarjeta= _TarjetaMetodo(icono, titulo, subtitulo, color, paleta)
            #Lambda: cl se fija por defecto con la clave de este método (evita que todas usen la última);
            #al hacer clic en la tarjeta selecciona ese método.
            tarjeta.clicked.connect(lambda cl=clave: self._seleccionar(cl))
            disposicion.addWidget(tarjeta)
            self._tarjetas.append((clave, tarjeta))
        self._tarjetas[0][1].poner_marcada(True, animar=False)
        disposicion.addStretch()

    def _seleccionar(self, clave):

        if clave == self._metodo_seleccionado:
            return
        self._metodo_seleccionado= clave
        for cl, tarjeta in self._tarjetas:
            tarjeta.poner_marcada(cl == clave)

    def nextId(self):

        return {"google_drive": ID_GOOGLE, "dropbox": ID_DROPBOX,
                "onedrive": ID_ONEDRIVE, "servidor": ID_SERVIDOR}[self._metodo_seleccionado]


#SELLO ✓ / ✕ pintado a mano (para la tarjeta de estado)
#Círculo con una marca ✓ o ✕ dibujada con QPainter, con una pequeña
#animación de aparición (escala) en vez de aparecer de golpe.
class _IconoEstadoPintado(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._tipo= None  #None | "ok" | "error"
        self._color= QColor("#22C55E")
        self._escala= 0.0
        self._anim= QPropertyAnimation(self, b"escala", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def _leer_escala(self):

        return self._escala

    def _poner_escala(self, valor):

        self._escala= valor
        self.update()

    escala= Property(float, _leer_escala, _poner_escala)

    def mostrar(self, tipo):

        self._tipo= tipo
        self._color= QColor("#22C55E" if tipo == "ok" else "#EF4444")
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def limpiar(self):

        self._anim.stop()
        self._tipo= None
        self._escala= 0.0
        self.update()

    def paintEvent(self, evento):

        if not self._tipo or self._escala <= 0.001:
            return
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy= self.width() / 2, self.height() / 2
        radio= (self.width() / 2 - 1) * self._escala
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(QPointF(cx, cy), radio, radio)
        if self._escala < 0.55:
            return  #el trazo aparece justo después de que el círculo ya se ve
        pluma= QPen(QColor("#FFFFFF"))
        pluma.setWidthF(2.2)
        pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pluma)
        if self._tipo == "ok":
            painter.drawLine(QPointF(cx - 4.5, cy + 0.5), QPointF(cx - 1.0, cy + 4.5))
            painter.drawLine(QPointF(cx - 1.0, cy + 4.5), QPointF(cx + 5.0, cy - 4.0))
        else:
            painter.drawLine(QPointF(cx - 3.5, cy - 3.5), QPointF(cx + 3.5, cy + 3.5))
            painter.drawLine(QPointF(cx - 3.5, cy + 3.5), QPointF(cx + 3.5, cy - 3.5))


#Tarjeta de estado de conexión (reemplaza el QLabel de texto plano)
#Fila de estado animada para el resultado de una conexión: spinner
#mientras corre en segundo plano, y un sello ✓/✕ pintado a mano cuando
#termina.
class _ChipEstado(QWidget):

    def __init__(self, color_acento="#6366F1", parent=None):

        super().__init__(parent)
        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(0, 4, 0, 4)
        disposicion.setSpacing(8)
        self._spinner= SpinnerCircular(diametro=18, color=color_acento)
        disposicion.addWidget(self._spinner)
        self._icono= _IconoEstadoPintado()
        disposicion.addWidget(self._icono)
        self._lbl= QLabel("")
        self._lbl.setWordWrap(True)
        disposicion.addWidget(self._lbl, 1)
        self.hide()

    def ocioso(self):

        self._spinner.detener()
        self._icono.limpiar()
        self.hide()

    def conectando(self, texto="Conectando…"):

        self._icono.limpiar()
        self._lbl.setStyleSheet("color: #64748B; font-weight: 600; background: transparent;")
        self._lbl.setText(texto)
        self.show()
        _fundido_entrada(self, duracion=180)
        self._spinner.iniciar()

    def ok(self, texto="Conectado correctamente."):

        self._spinner.detener()
        self._lbl.setStyleSheet("color: #16A34A; font-weight: 700; background: transparent;")
        self._lbl.setText(texto)
        self.show()
        self._icono.mostrar("ok")

    def error(self, texto):

        self._spinner.detener()
        self._lbl.setStyleSheet("color: #DC2626; font-weight: 700; background: transparent;")
        self._lbl.setText(texto)
        self.show()
        self._icono.mostrar("error")


#Base común de las páginas de backend (conexión sin congelar la ventana)
#Agrega a QWizardPage el manejo común de 'conectar en segundo plano':
#antes, las llamadas de red/OAuth de cada backend corrían directo en el
#hilo de la interfaz y podían congelar el asistente varios segundos —o
#minutos, en el caso del flujo de código de dispositivo de OneDrive—.
#Ahora corren en un QThread aparte y la ventana se mantiene fluida,
#mostrando una tarjeta de estado animada mientras tanto.
class _PaginaConectable(QWizardPage):

    def __init__(self, color_acento="#6366F1"):

        super().__init__()
        self._conectado= False
        self._hilo= None
        self._color_acento= color_acento
        self._botones_a_bloquear= []
        self.chip= _ChipEstado(color_acento)

    def _registrar_boton(self, boton):

        boton.setObjectName("BtnConectarAsistente")
        self._botones_a_bloquear.append(boton)

    def _ejecutar_en_hilo(self, funcion, al_terminar, texto_conectando="Conectando…"):

        if self._hilo is not None and self._hilo.isRunning():
            return
        for b in self._botones_a_bloquear:
            b.setEnabled(False)
        self.chip.conectando(texto_conectando)
        self._hilo= _HiloOperacionSync(funcion, self)

        def _listo(resultado, error):

            for b in self._botones_a_bloquear:
                b.setEnabled(True)
            al_terminar(resultado, error)

        self._hilo.terminado.connect(_listo)
        self._hilo.start()

    def isComplete(self):

        return self._conectado

    def nextId(self):

        return ID_FINAL


#Página: Google Drive
class PaginaGoogle(_PaginaConectable):

    def __init__(self):

        super().__init__(color_acento="#22C55E")
        self.setTitle("Google Drive")
        self.setSubTitle("Crea una app OAuth propia y conéctala aquí.")

        disposicion= QVBoxLayout(self)
        disposicion.addWidget(_etiqueta_explicativa(
            "<b>Pasos previos (una sola vez, los hace un administrador):</b><br>"
            "1. Entra a <a href='https://console.cloud.google.com/'>console.cloud.google.com</a> "
            "y crea un proyecto (o usa uno existente).<br>"
            "2. Ve a <i>APIs y servicios ▸ Biblioteca</i> y activa la <b>Google Drive API</b>.<br>"
            "3. Ve a <i>APIs y servicios ▸ Pantalla de consentimiento OAuth</i>: elige tipo "
            "\"Externo\" (o \"Interno\" si usas Google Workspace), completa los datos básicos "
            "y agrega tu correo como \"Usuario de prueba\" si queda en modo prueba.<br>"
            "4. Ve a <i>APIs y servicios ▸ Credenciales ▸ Crear credenciales ▸ ID de cliente "
            "de OAuth</i>. Tipo de aplicación: <b>\"Aplicación de escritorio\"</b>.<br>"
            "5. Copia el <b>Client ID</b> y <b>Client Secret</b> generados y pégalos abajo."))

        disposicion.addWidget(QLabel("Client ID:"))
        self.in_client_id= QLineEdit()
        limitar_campo_texto(self.in_client_id, 300)
        disposicion.addWidget(self.in_client_id)
        disposicion.addWidget(QLabel("Client Secret:"))
        self.in_client_secret= QLineEdit()
        limitar_campo_texto(self.in_client_secret, 128)
        self.in_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_client_secret)

        fila= QHBoxLayout()
        self.btn_conectar= QPushButton("Conectar con Google Drive")
        self.btn_conectar.setIcon(icono_emoji("☁"))
        self.btn_conectar.setIconSize(_QSize_emoji(16, 16))
        self.btn_conectar.setCursor(Qt.CursorShape.PointingHandCursor)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self.btn_conectar.pressed.connect(lambda: _animar_click(self.btn_conectar))
        self.btn_conectar.clicked.connect(self._conectar)
        fila.addWidget(self.btn_conectar)
        fila.addStretch()
        disposicion.addLayout(fila)
        self._registrar_boton(self.btn_conectar)

        disposicion.addWidget(self.chip)
        disposicion.addStretch()

        self.registerField("google_client_id", self.in_client_id)
        self.registerField("google_client_secret", self.in_client_secret)

    def _conectar(self):

        client_id= self.in_client_id.text().strip()
        client_secret= self.in_client_secret.text().strip()
        if not client_id or not client_secret:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el Client ID y Client Secret.", self)
            return
        mostrar_mensaje("info", "Conectar Google Drive",
                        "Se abrirá tu navegador para autorizar el acceso. Vuelve al asistente "
                        "después de aceptar.", self)

        def _al_terminar(resultado, error):

            if error is not None:
                self.chip.error(f"No se pudo conectar: {error}")
                return
            self._conectado= True
            self.chip.ok("Conectado correctamente.")
            self.completeChanged.emit()

        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._ejecutar_en_hilo(lambda: avanzado.google_drive_conectar(client_id, client_secret),
                               _al_terminar, "Esperando autorización en el navegador…")


#Página: Dropbox
class PaginaDropbox(_PaginaConectable):

    def __init__(self):

        super().__init__(color_acento="#3B82F6")
        self.setTitle("Dropbox")
        self.setSubTitle("Registra una app en Dropbox y conéctala aquí.")

        disposicion= QVBoxLayout(self)
        disposicion.addWidget(_etiqueta_explicativa(
            "<b>Pasos previos (una sola vez):</b><br>"
            "1. Entra a <a href='https://www.dropbox.com/developers/apps'>"
            "dropbox.com/developers/apps</a> y pulsa \"Create app\".<br>"
            "2. Elige API: <b>\"Scoped access\"</b>. Tipo de acceso: <b>\"App folder\"</b> "
            "(más seguro, la app solo verá su propia carpeta) o \"Full Dropbox\" si prefieres.<br>"
            "3. En la pestaña <i>Permissions</i>, activa al menos <b>files.content.write</b> y "
            "<b>files.content.read</b>, y guarda los cambios.<br>"
            "4. En la pestaña <i>Settings</i>, copia el <b>App key</b> y <b>App secret</b>.<br>"
            "5. Pégalos abajo y pulsa Conectar: se abrirá una página de Dropbox con un código "
            "que debes copiar y pegar de vuelta aquí."))

        disposicion.addWidget(QLabel("App Key:"))
        self.in_key= QLineEdit()
        limitar_campo_texto(self.in_key, 128)
        disposicion.addWidget(self.in_key)
        disposicion.addWidget(QLabel("App Secret:"))
        self.in_secret= QLineEdit()
        limitar_campo_texto(self.in_secret, 128)
        self.in_secret.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_secret)

        fila= QHBoxLayout()
        self.btn_conectar= QPushButton("Conectar con Dropbox")
        self.btn_conectar.setIcon(icono_emoji("🔌"))
        self.btn_conectar.setIconSize(_QSize_emoji(16, 16))
        self.btn_conectar.setCursor(Qt.CursorShape.PointingHandCursor)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self.btn_conectar.pressed.connect(lambda: _animar_click(self.btn_conectar))
        self.btn_conectar.clicked.connect(self._conectar)
        fila.addWidget(self.btn_conectar)
        fila.addStretch()
        disposicion.addLayout(fila)
        self._registrar_boton(self.btn_conectar)

        disposicion.addWidget(self.chip)
        disposicion.addStretch()

        self.registerField("dropbox_key", self.in_key)
        self.registerField("dropbox_secret", self.in_secret)

    def _conectar(self):

        app_key= self.in_key.text().strip()
        app_secret= self.in_secret.text().strip()
        if not app_key or not app_secret:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el App Key y App Secret.", self)
            return
        try:

            flow, url= avanzado.dropbox_conectar(app_key, app_secret)
        except Exception as e:
            mostrar_mensaje("error", "Error", f"No se pudo iniciar la conexión:\n{e}", self)
            return
        webbrowser.open(url)
        codigo, ok= QInputDialog.getText(
            self, "Conectar Dropbox",
            f"Se abrió tu navegador para autorizar el acceso.\nSi no se abrió, visita:\n{url}\n\n"
            "Pega aquí el código de autorización que te muestra Dropbox:")
        if not ok or not codigo.strip():
            return

        def _al_terminar(resultado, error):

            if error is not None:
                self.chip.error(f"No se pudo completar la conexión: {error}")
                return
            self._conectado= True
            self.chip.ok("Conectado correctamente.")
            self.completeChanged.emit()

        self._ejecutar_en_hilo(
            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            lambda: avanzado.dropbox_finalizar_conexion(flow, codigo, app_key, app_secret),
            _al_terminar, "Confirmando el código con Dropbox…")


#Página: OneDrive
class PaginaOneDrive(_PaginaConectable):

    def __init__(self):

        super().__init__(color_acento="#0EA5E9")
        self.setTitle("OneDrive / Microsoft 365")
        self.setSubTitle("Registra una app en Microsoft Entra ID y conéctala aquí.")

        disposicion= QVBoxLayout(self)
        disposicion.addWidget(_etiqueta_explicativa(
            "<b>Pasos previos (una sola vez):</b><br>"
            "1. Entra a <a href='https://entra.microsoft.com/'>entra.microsoft.com</a> "
            "▸ <i>Identidad ▸ Aplicaciones ▸ Registros de aplicaciones ▸ Nuevo registro</i>.<br>"
            "2. Nombre: el que quieras. Tipos de cuenta admitidos: elige según tu caso "
            "(cuentas personales, o de tu organización).<br>"
            "3. En <i>Autenticación</i>, agrega una plataforma <b>\"Cliente público/nativo "
            "(móvil y escritorio)\"</b> y activa el flujo de <b>\"código de dispositivo\"</b> "
            "en \"Configuraciones avanzadas\".<br>"
            "4. En <i>Permisos de API</i>, agrega el permiso delegado "
            "<b>Files.ReadWrite</b> de Microsoft Graph.<br>"
            "5. Copia el <b>ID de aplicación (cliente)</b> de la pantalla \"Información general\" "
            "y pégalo abajo. No necesitas un secreto de cliente para este flujo."))

        disposicion.addWidget(QLabel("Client ID:"))
        self.in_client_id= QLineEdit()
        limitar_campo_texto(self.in_client_id, 300)
        disposicion.addWidget(self.in_client_id)

        fila= QHBoxLayout()
        self.btn_conectar= QPushButton("Conectar con OneDrive")
        self.btn_conectar.setIcon(icono_emoji("☁"))
        self.btn_conectar.setIconSize(_QSize_emoji(16, 16))
        self.btn_conectar.setCursor(Qt.CursorShape.PointingHandCursor)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self.btn_conectar.pressed.connect(lambda: _animar_click(self.btn_conectar))
        self.btn_conectar.clicked.connect(self._conectar)
        fila.addWidget(self.btn_conectar)
        fila.addStretch()
        disposicion.addLayout(fila)
        self._registrar_boton(self.btn_conectar)

        disposicion.addWidget(self.chip)
        disposicion.addStretch()

        self.registerField("onedrive_client_id", self.in_client_id)

    def _conectar(self):

        client_id= self.in_client_id.text().strip()
        if not client_id:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el Client ID.", self)
            return

        def _tras_iniciar(resultado, error):

            if error is not None:
                self.chip.error(f"No se pudo iniciar la conexión: {error}")
                return
            app, flujo= resultado
            self.chip.ocioso()
            if mostrar_mensaje("pregunta", "Conectar OneDrive",
                    f"{flujo['message']}\n\n¿Ya completaste el inicio de sesión en el navegador?",
                    self) != QMessageBox.StandardButton.Yes:
                return

            def _tras_finalizar(resultado2, error2):

                if error2 is not None:
                    self.chip.error(f"No se pudo completar la conexión: {error2}")
                    return
                self._conectado= True
                self.chip.ok("Conectado correctamente.")
                self.completeChanged.emit()

            #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
            self._ejecutar_en_hilo(lambda: avanzado.onedrive_finalizar_conexion(app, flujo, client_id),
                                   _tras_finalizar, "Esperando que confirmes el inicio de sesión…")

        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._ejecutar_en_hilo(lambda: avanzado.onedrive_conectar(client_id),
                               _tras_iniciar, "Iniciando sesión de dispositivo…")


#Página: servidor institucional
class PaginaServidor(_PaginaConectable):

    def __init__(self, main_window=None):

        super().__init__(color_acento="#F59E0B")
        self._main_window= main_window
        self.setTitle("Servidor Institucional Propio")
        self.setSubTitle("La forma más simple: sin variables de entorno, sin TI dedicado.")

        disposicion= QVBoxLayout(self)
        disposicion.addWidget(_etiqueta_explicativa(
            "<b>1.</b> Pulsa \"Exportar Servidor Institucional\" abajo: descarga un ZIP con "
            "el código, sus dependencias y scripts para iniciarlo con un doble clic (sin "
            "necesitar terminal).<br>"
            "<b>2.</b> Compártelo (correo, USB) con quien vaya a ponerlo en marcha — puede "
            "ser cualquier PC del colegio, no hace falta un área de TI dedicada.<br>"
            "<b>3.</b> Al iniciarlo, el servidor genera un <b>token</b> automáticamente y "
            "muestra la <b>URL</b> a usar — ya no hay que configurar nada a mano.<br>"
            "<b>4.</b> Pega esa URL y ese token abajo.<br><br>"
            "El ZIP incluye <b>LEEME_PRIMERO.txt</b>, con 3 formas reales de tenerlo "
            "accesible desde internet: gratis en un equipo del colegio, gratis en la nube, "
            "o de pago en un VPS propio — según el presupuesto de tu institución."))

        fila_exportar= QHBoxLayout()
        self.btn_exportar= QPushButton("Exportar Servidor Institucional")
        self.btn_exportar.setIcon(icono_emoji("\uE002"))
        self.btn_exportar.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self.btn_exportar.pressed.connect(lambda: _animar_click(self.btn_exportar))
        self.btn_exportar.clicked.connect(self._exportar)
        fila_exportar.addWidget(self.btn_exportar)
        fila_exportar.addStretch()
        disposicion.addLayout(fila_exportar)

        disposicion.addWidget(QLabel("URL del servidor:"))
        self.in_url= QLineEdit()
        limitar_campo_texto(self.in_url, 200)
        self.in_url.setPlaceholderText("http://192.168.1.50:8420")
        disposicion.addWidget(self.in_url)
        disposicion.addWidget(QLabel("Token de acceso:"))
        self.in_token= QLineEdit()
        limitar_campo_texto(self.in_token, 128)
        self.in_token.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_token)

        fila= QHBoxLayout()
        self.btn_conectar= QPushButton("Conectar con Servidor")
        self.btn_conectar.setIcon(icono_emoji("🔌"))
        self.btn_conectar.setIconSize(_QSize_emoji(16, 16))
        self.btn_conectar.setCursor(Qt.CursorShape.PointingHandCursor)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self.btn_conectar.pressed.connect(lambda: _animar_click(self.btn_conectar))
        self.btn_conectar.clicked.connect(self._conectar)
        fila.addWidget(self.btn_conectar)
        fila.addStretch()
        disposicion.addLayout(fila)
        self._registrar_boton(self.btn_conectar)

        disposicion.addWidget(self.chip)
        disposicion.addStretch()

        self.registerField("servidor_url", self.in_url)
        self.registerField("servidor_token", self.in_token)

    def _exportar(self):

        exportar_paquete_servidor(self._main_window, self)

    def _conectar(self):

        url= self.in_url.text().strip()
        token= self.in_token.text().strip()
        if not url or not token:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa la URL y el token.", self)
            return

        def _al_terminar(resultado, error):

            if error is not None:
                self.chip.error(f"No se pudo conectar: {error}")
                return
            self._conectado= True
            self.chip.ok("Conectado correctamente.")
            self.completeChanged.emit()

        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._ejecutar_en_hilo(lambda: avanzado.servidor_conectar(url, token),
                               _al_terminar, "Contactando al servidor…")


#Página final
class PaginaFinal(QWizardPage):

    def __init__(self):

        super().__init__()
        self.setTitle("Listo")
        self.setSubTitle("La conexión quedó guardada en este equipo.")
        disposicion= QVBoxLayout(self)
        disposicion.addWidget(_etiqueta_explicativa(
            "El método quedó conectado. Vuelve a la pantalla de <b>Sincronización</b>, "
            "selecciónalo en \"Método\" y usa los botones <b>Subir (directo)</b> / "
            "<b>Descargar (directo)</b> para sincronizar cuando lo necesites.<br><br>"
            "Recuerda: cada equipo que use este método directo necesita conectarse "
            "también (este asistente lo hace por equipo, no una sola vez para toda "
            "la institución)."))
        disposicion.addStretch()

    def nextId(self):

        return -1


#ASISTENTE (QWizard)
class AsistenteSincronizacion(QWizard):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.setWindowTitle("Asistente de Configuración — Sincronización Directa")
        aplicar_icono_ventana(self, ICONO_ASISTENTE)
        self.setMinimumSize(640, 580)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setStyleSheet(_estilo_asistente(_paleta(main_window)))

        self.setPage(ID_INTRO, PaginaIntro(main_window))
        self.setPage(ID_GOOGLE, PaginaGoogle())
        self.setPage(ID_DROPBOX, PaginaDropbox())
        self.setPage(ID_ONEDRIVE, PaginaOneDrive())
        self.setPage(ID_SERVIDOR, PaginaServidor(main_window))
        self.setPage(ID_FINAL, PaginaFinal())
        self.setStartId(ID_INTRO)

        #Transición suave entre pasos y un pequeño rebote en los botones de navegación, para que el asistente se sienta
        #vivo y no dé saltos bruscos al avanzar/retroceder.
        self.currentIdChanged.connect(self._al_cambiar_pagina)
        for rol in (QWizard.WizardButton.NextButton, QWizard.WizardButton.BackButton,
                    QWizard.WizardButton.FinishButton, QWizard.WizardButton.CancelButton):
            boton= self.button(rol)
            if boton is not None:
                boton.setCursor(Qt.CursorShape.PointingHandCursor)
                #Lambda: b se fija con el botón actual; al presionarlo (pressed) lanza su animación de rebote.
                boton.pressed.connect(lambda b=boton: _animar_click(b))

    def _al_cambiar_pagina(self, _id):

        pagina= self.currentPage()
        if pagina is not None:
            _fundido_entrada(pagina, duracion=240)
