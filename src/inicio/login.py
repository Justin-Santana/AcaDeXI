import os
import secrets
import sys
from datetime import datetime, timedelta
from src.nucleo.bd import (obtener_conexion, registrar_auditoria, hash_password, verificar_contrasena, enviar_correo,
    verificar_bloqueo_login, registrar_intento_fallido_login, resetear_intentos_login)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QMessageBox, QCheckBox, QGraphicsDropShadowEffect,
    QTabWidget, QWidget, QFileDialog, QApplication, QInputDialog)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QColor
from src.nucleo.iconos import (obtener_icono, icono_app, aplicar_icono_ventana, ICONO_OK, ICONO_WARNING,
    ICONO_ERROR, ICONO_LOGIN, pixmap_logo_app)
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, quitar_emojis_texto


def _hex_a_rgba(hex_color, alpha):
    hex_color= hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _centrar_y_al_frente(dialogo, parent):
    """Centra `dialogo` sobre su ventana padre (o sobre la pantalla si no hay
    padre visible) y se asegura de que aparezca POR ENCIMA de todas las demás
    ventanas de la app, aunque el usuario haya cambiado de ventana mientras
    tanto. Sin esto, en apps con varias ventanas los diálogos pueden abrirse
    "detrás" y el usuario tiene que buscarlos en la barra de tareas."""
    dialogo.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    referencia= parent if (parent is not None and parent.isVisible()) else None
    if referencia is not None:
        geo_padre= referencia.frameGeometry()
        dialogo.adjustSize()
        x= geo_padre.x() + (geo_padre.width() - dialogo.width()) // 2
        y= geo_padre.y() + (geo_padre.height() - dialogo.height()) // 2
        dialogo.move(max(0, x), max(0, y))
    else:
        pantalla= dialogo.screen() if hasattr(dialogo, "screen") and dialogo.screen() else None
        if pantalla is not None:
            geo= pantalla.availableGeometry()
            dialogo.adjustSize()
            x= geo.x() + (geo.width() - dialogo.width()) // 2
            y= geo.y() + (geo.height() - dialogo.height()) // 2
            dialogo.move(max(0, x), max(0, y))
    dialogo.raise_()
    dialogo.activateWindow()


def _msg(main_window, parent, icono, titulo, texto):
    try:
        paleta= main_window.theme_palettes.get(
            main_window.tema_actual, main_window.theme_palettes["Indigo"])
        idx= 1 if main_window.modo_oscuro else 0
        bg, txt = paleta["display_bg"][idx], paleta["text_primary"][idx]
        accent= paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]
    except Exception:
        bg, txt, accent, hv_accent = "#1E293B", "#F8FAFC", "#6366F1", "#4F46E5"

    box= QMessageBox(parent)
    box.setWindowTitle(titulo)
    box.setText(texto)
    box.setIcon(icono)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)

    if icono == QMessageBox.Icon.Information:
        box.setWindowIcon(obtener_icono(ICONO_OK))
    elif icono == QMessageBox.Icon.Warning:
        box.setWindowIcon(obtener_icono(ICONO_WARNING))
    elif icono == QMessageBox.Icon.Critical:
        box.setWindowIcon(obtener_icono(ICONO_ERROR))
    else:
        box.setWindowIcon(icono_app())

    box.setStyleSheet(f"""
        QMessageBox {{ background-color: {bg}; }}
        QMessageBox QLabel {{ color: {txt}; font-size: 13px; background-color: transparent; }}
        QPushButton {{
            background-color: {accent}; color: white; border: none;
            border-radius: 6px; padding: 8px 22px; font-weight: bold; min-width: 70px;
        }}
        QPushButton:hover {{ background-color: {hv_accent}; }}
    """)
    _centrar_y_al_frente(box, parent)
    return box.exec()


class LoginWindow(QDialog):
    def __init__(self, main_window):
        super().__init__()
        self.main_window= main_window
        self.usuario_actual= None
        self.rol_actual= None
        self.id_usuario_actual= None
        self.nombre_completo= None
        self.password_visible= False
        self.translucido= getattr(main_window, "login_translucido", True)
        self._drag_pos= None
        aplicar_icono_ventana(self, ICONO_LOGIN)
        self._build_ui()
        self._apply_theme()
        self._cargar_usuario_recordado()

    def _build_ui(self):
        self.setWindowTitle("Iniciar Sesión - AcaDeXI")
        self.setFixedWidth(440)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout_principal= QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 24, 24, 24)
        layout_principal.setSpacing(0)

        self.frame_fondo= QFrame()
        self.frame_fondo.setObjectName("LoginFrame")
        sombra= QGraphicsDropShadowEffect()
        sombra.setBlurRadius(40)
        sombra.setOffset(0, 10)
        sombra.setColor(QColor(0, 0, 0, 140))
        self.frame_fondo.setGraphicsEffect(sombra)

        layout_frame= QVBoxLayout(self.frame_fondo)
        layout_frame.setContentsMargins(36, 22, 36, 26)
        layout_frame.setSpacing(9)

        fila_superior= QHBoxLayout()
        self.btn_translucido= QPushButton("" if self.translucido else "▢")
        self.btn_translucido.setAutoDefault(False)
        self.btn_translucido.setFixedSize(30, 30)
        self.btn_translucido.setObjectName("BtnTranslucidoLogin")
        self.btn_translucido.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translucido.setToolTip("Alternar panel translúcido / sólido")
        self.btn_translucido.setIcon(icono_emoji("🌫" if self.translucido else "🪟"))
        self.btn_translucido.setIconSize(_QSize_emoji(16, 16))
        self.btn_translucido.clicked.connect(self._toggle_translucido)
        fila_superior.addWidget(self.btn_translucido)
        fila_superior.addStretch()
        btn_cerrar= QPushButton("")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setAutoDefault(False)
        btn_cerrar.setFixedSize(30, 30)
        btn_cerrar.setObjectName("BtnCerrarLogin")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.close)
        fila_superior.addWidget(btn_cerrar)
        layout_frame.addLayout(fila_superior)

        contenedor_logo= QFrame()
        contenedor_logo.setObjectName("LoginLogoAro")
        contenedor_logo.setFixedSize(160, 160)
        layout_logo_aro= QVBoxLayout(contenedor_logo)
        layout_logo_aro.setContentsMargins(0, 0, 0, 0)
        self.lbl_logo= QLabel()
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_logo_aro.addWidget(self.lbl_logo)

        logo_cargado= False
        self.nombre_institucion= None
        try:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT logo_path, nombre_institucion FROM configuracion WHERE id = 1")
            result= c.fetchone()
            conn.close()
            if result and result["logo_path"] and os.path.exists(result["logo_path"]):
                pixmap= QPixmap(result["logo_path"])
                if not pixmap.isNull():
                    scaled= pixmap.scaled(132, 132, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
                    self.lbl_logo.setPixmap(scaled)
                    logo_cargado= True
            self.nombre_institucion= result["nombre_institucion"] if result and result["nombre_institucion"] else None
        except Exception:
            pass

        if not logo_cargado:
            #Sin logo institucional todavía: en vez de dejar el aro vacío, se muestra el logo de la propia app (el escudo)
            #para que el login no se vea "roto". El nombre de la institución (o su ausencia) sigue resolviéndose
            #exactamente igual más abajo en self.lbl_titulo -esto NO lo reemplaza-.
            logo_app= pixmap_logo_app(132)
            if logo_app is not None:
                self.lbl_logo.setPixmap(logo_app)
            else:
                self.lbl_logo.setText("")
                self.lbl_logo.setStyleSheet("font-size: 72px; background-color: transparent;")

        fila_logo= QHBoxLayout()
        fila_logo.addStretch()
        fila_logo.addWidget(contenedor_logo)
        fila_logo.addStretch()
        layout_frame.addLayout(fila_logo)

        if not logo_cargado:
            self.lbl_nombre_app_logo= QLabel("AcaDeXI")
            self.lbl_nombre_app_logo.setObjectName("LoginNombreAppLogo")
            self.lbl_nombre_app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_nombre_app_logo.setStyleSheet(
                "font-size: 11px; font-weight: 600; letter-spacing: 1px; "
                "background-color: transparent; color: palette(mid);")
            layout_frame.addWidget(self.lbl_nombre_app_logo)

        layout_frame.addSpacing(2)

        self.lbl_titulo= QLabel(self.nombre_institucion or "AcaDeXI")
        self.lbl_titulo.setObjectName("LoginTitulo")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_titulo.setWordWrap(True)
        layout_frame.addWidget(self.lbl_titulo)

        self.lbl_subtitulo= QLabel("Sistema de Gestión Escolar")
        self.lbl_subtitulo.setObjectName("LoginSubtitulo")
        self.lbl_subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_frame.addWidget(self.lbl_subtitulo)
        layout_frame.addSpacing(10)

        lbl_usuario= QLabel("USUARIO")
        lbl_usuario.setObjectName("LoginLabel")
        layout_frame.addWidget(lbl_usuario)
        self.input_usuario= QLineEdit()
        limitar_campo_texto(self.input_usuario, 300)
        self.input_usuario.setObjectName("LoginInput")
        self.input_usuario.setPlaceholderText("Nombre de usuario")
        self.input_usuario.returnPressed.connect(self._iniciar_sesion)
        layout_frame.addWidget(self.input_usuario)

        lbl_password= QLabel("CONTRASEÑA")
        lbl_password.setObjectName("LoginLabel")
        layout_frame.addWidget(lbl_password)
        fila_pass= QHBoxLayout()
        fila_pass.setSpacing(6)
        self.input_password= QLineEdit()
        limitar_campo_texto(self.input_password, 128)
        self.input_password.setObjectName("LoginInput")
        self.input_password.setPlaceholderText("Contraseña")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.returnPressed.connect(self._iniciar_sesion)
        fila_pass.addWidget(self.input_password)
        self.btn_ver_pass= QPushButton("")
        self.btn_ver_pass.setIcon(icono_emoji("🙈"))
        self.btn_ver_pass.setIconSize(_QSize_emoji(16, 16))
        self.btn_ver_pass.setAutoDefault(False)
        self.btn_ver_pass.setFixedSize(38, 38)
        self.btn_ver_pass.setObjectName("BtnVerPass")
        self.btn_ver_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_pass.clicked.connect(self._toggle_password)
        fila_pass.addWidget(self.btn_ver_pass)
        layout_frame.addLayout(fila_pass)

        #Aviso de Bloq Mayús: se consulta el estado REAL del teclado del
        #sistema (no un toggle interno) cada vez que se presiona CapsLock o
        #se enfocan los campos usuario/contraseña. Así, aunque el Bloq Mayús quedara activado fuera de la app (p. ej.
        #al escribir el PIN de Windows), el aviso refleja el estado verdadero desde el inicio.
        self.lbl_capslock= QLabel("Bloq Mayús activado")
        self.lbl_capslock.setObjectName("LoginCapsLock")
        self.lbl_capslock.setVisible(False)
        layout_frame.addWidget(self.lbl_capslock)

        self._capslock_on= False
        self.input_usuario.installEventFilter(self)
        self.input_password.installEventFilter(self)

        fila_extra= QHBoxLayout()
        self.chk_recordar= QCheckBox("Recordar usuario")
        self.chk_recordar.setObjectName("ChkRecordar")
        self.chk_recordar.setCursor(Qt.CursorShape.PointingHandCursor)
        fila_extra.addWidget(self.chk_recordar)
        fila_extra.addStretch()
        btn_olvido= QPushButton("¿Olvidó su contraseña?")
        btn_olvido.setObjectName("BtnLinkLogin")
        btn_olvido.setAutoDefault(False)
        btn_olvido.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_olvido.clicked.connect(self._abrir_recuperacion)
        fila_extra.addWidget(btn_olvido)
        layout_frame.addLayout(fila_extra)
        layout_frame.addSpacing(6)

        self.btn_ingresar= QPushButton("Iniciar Sesión")
        self.btn_ingresar.setIcon(icono_emoji("🔑"))
        self.btn_ingresar.setIconSize(_QSize_emoji(16, 16))
        self.btn_ingresar.setObjectName("LoginButton")
        self.btn_ingresar.setMinimumHeight(44)
        self.btn_ingresar.setCursor(Qt.CursorShape.PointingHandCursor)
        #Evita que se dispare 2 veces al presionar Enter: sin esto, Qt ejecuta tanto el returnPressed del campo
        #contraseña como el click implícito del botón por defecto del diálogo, mostrando el error duplicado.
        self.btn_ingresar.setAutoDefault(False)
        self.btn_ingresar.setDefault(False)
        self.btn_ingresar.clicked.connect(self._iniciar_sesion)
        layout_frame.addWidget(self.btn_ingresar)

        btn_importar_perfil= QPushButton("Importar Perfil Institucional (.acdx)")
        btn_importar_perfil.setIcon(icono_emoji("\uE001"))
        btn_importar_perfil.setIconSize(_QSize_emoji(16, 16))
        btn_importar_perfil.setObjectName("BtnLinkLogin")
        btn_importar_perfil.setAutoDefault(False)
        btn_importar_perfil.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_importar_perfil.clicked.connect(self._importar_perfil)
        layout_frame.addWidget(btn_importar_perfil)

        layout_principal.addWidget(self.frame_fondo)

    @staticmethod
    def _consultar_capslock():
        """Devuelve el estado REAL de Bloq Mayús según el sistema operativo.
        En Windows se usa GetKeyState(VK_CAPITAL); en otras plataformas se
        intenta el equivalente y, si no es posible consultarlo, devuelve None
        (no se puede saber) para no mostrar un aviso falso."""
        try:
            if sys.platform == "win32":
                import ctypes
                #VK_CAPITAL = 0x14; el bit menos significativo indica toggle activo
                return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
            if sys.platform == "darwin":
                import Quartz
                return bool(Quartz.CGEventSourceKeyState(
                    Quartz.kCGEventSourceStateHIDSystemState, 57))  #57 = kVK_CapsLock
        except Exception:
            pass
        return None

    def _actualizar_capslock(self):
        """Sincroniza el aviso con el estado real de Bloq Mayús del sistema."""
        estado= self._consultar_capslock()
        if estado is not None:
            self._capslock_on= estado
            self.lbl_capslock.setVisible(estado)

    def eventFilter(self, obj, event):
        if obj in (self.input_usuario, self.input_password):
            if event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_CapsLock:
                #Al presionar CapsLock consultamos el estado real del SO (GetKeyState), en lugar de alternar una bandera. OJO:
                #el toggle NO se refleja en GetKeyState durante el propio
                #KeyPress (se actualiza ~30-40 ms después), así que la
                #consulta se poslona con un QTimer; de lo contrario leería el estado anterior y el aviso nunca cambiaría.
                QTimer.singleShot(50, self._actualizar_capslock)
            elif event.type() == event.Type.FocusIn:
                #Al enfocar usuario/contraseña, sincronizar con el estado real actual (cubre el caso de mayúsculas activadas
                #fuera de la app, p. ej. al escribir el PIN del dispositivo).
                self._actualizar_capslock()
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        #Estado real de Bloq Mayús ya al abrir el diálogo de login.
        self._actualizar_capslock()
        super().showEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _cargar_usuario_recordado(self):
        if getattr(self.main_window, "recordar_usuario", False):
            self.input_usuario.setText(getattr(self.main_window, "ultimo_usuario", ""))
            self.chk_recordar.setChecked(True)
            self.input_password.setFocus()
        else:
            self.input_usuario.setFocus()

    def _importar_perfil(self):
        from src.interfaz.perfil import (leer_perfil_archivo, aplicar_perfil, EXTENSION,
                            perfil_incluye_bd_base, local_ya_tiene_usuarios, aplicar_bd_base,
                            descifrar_password_perfil)
        from src.nucleo.iconos import mostrar_mensaje
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Importar Perfil Institucional", "", f"Perfil AcaDeXI (*{EXTENSION})")
        if not ruta:
            return
        try:
            datos= leer_perfil_archivo(ruta)
        except Exception as e:
            mostrar_mensaje("error", "Perfil inválido", str(e), self)
            return

        ruta_backup_bd= None
        if perfil_incluye_bd_base(datos):
            #Este perfil trae su propia BD Base institucional embebida: es el caso típico de un Docente/Personal que
            #instaló la app (sin ninguna BD) y solo tiene este .acdx para arrancar.
            proceder= True
            if local_ya_tiene_usuarios():
                proceder= mostrar_mensaje(
                    "pregunta", "Reemplazar base de datos local",
                    "Este perfil incluye una Base de Datos Institucional inicial, pero este equipo ya "
                    "tiene datos guardados localmente.\n\n¿Deseas reemplazar la base de datos local por "
                    "la que trae este perfil? Se hará un respaldo de la actual antes de reemplazarla, "
                    "pero cualquier cambio no respaldado en la BD local se perderá.",
                    self) == QMessageBox.StandardButton.Yes
            if proceder:
                try:
                    ruta_backup_bd= aplicar_bd_base(datos)
                except Exception as e:
                    mostrar_mensaje("error", "Error",
                                    f"No se pudo aplicar la base de datos incluida en el perfil:\n{e}", self)

        existe= aplicar_perfil(self.main_window, datos)
        self.input_usuario.setText(datos.get("usuario", ""))
        self.chk_recordar.setChecked(True)

        #Perfiles nuevos (versión 3+): la contraseña, si viene, está cifrada con un PIN que el usuario debe conocer por
        #separado (no viaja en el archivo). Perfiles viejos (generados antes de este cambio) todavía pueden traer
        #"password" en texto plano — se soporta por compatibilidad, con una advertencia más fuerte.
        password_incluida= ""
        password_protegida= bool(datos.get("password_cifrada"))
        pin_incorrecto= False
        if password_protegida:
            pin, ok = QInputDialog.getText(
                self, "Contraseña protegida por PIN",
                "Este perfil incluye una contraseña protegida con PIN.\n"
                "Ingresa el PIN para autocompletarla (o cancela para escribirla tú mismo):",
                QLineEdit.EchoMode.Password)
            if ok and pin:
                try:
                    password_incluida= descifrar_password_perfil(datos, pin.strip())
                except Exception:
                    pin_incorrecto= True
        elif datos.get("password"):
            #Compatibilidad con perfiles viejos (texto plano, sin PIN).
            password_incluida= datos.get("password", "")

        if password_incluida:
            self.input_password.setText(password_incluida)
            self.password_visible= True
            self.input_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_ver_pass.setText("")
        self.input_password.setFocus()

        aviso_extra= "" if existe else ("\n\n Este usuario todavía no existe en esta base de datos local."
                                          "Pide al Director que lo cree o sincronice antes de iniciar sesión.")
        if password_incluida:
            #Ya no se repite la contraseña en texto dentro de este mensaje: quedó precargada en el campo de contraseña, no
            #hace falta mostrarla de nuevo.
            aviso_password= ("\n\n La contraseña se descifró con el PIN y quedó precargada en el "
                               "formulario. Si compartes este equipo con alguien más, ciérrala o cámbiala "
                               "después desde tu cuenta.")
        elif password_protegida and pin_incorrecto:
            aviso_password= ("\n\n El PIN ingresado no permitió descifrar la contraseña de este "
                               "perfil. Escríbela manualmente para iniciar sesión.")
        elif password_protegida:
            aviso_password= ("\n\n Este perfil incluye una contraseña protegida por PIN. Escríbela "
                               "manualmente o vuelve a importar el perfil con el PIN correcto.")
        else:
            aviso_password= "\n\n(Este perfil no incluye contraseña; deberás escribirla manualmente.)"
        aviso_bd= ""
        if perfil_incluye_bd_base(datos) and ruta_backup_bd is not None:
            aviso_bd= f"\n\n📀 Se reemplazó la base de datos local. Respaldo de la anterior en:\n{ruta_backup_bd}"
        elif perfil_incluye_bd_base(datos) and ruta_backup_bd is None:
            aviso_bd= "\n\n Se aplicó la Base de Datos Institucional incluida en este perfil."
        mostrar_mensaje("exito", "Perfil Importado",
                        f"Institución: {datos.get('institucion', '')}\n"
                        f"Usuario: {datos.get('usuario', '')}\n"
                        f"Rol: {datos.get('rol', '')}\n"
                        f"Modo de trabajo: {datos.get('modo', '')}" + aviso_password + aviso_bd + aviso_extra, self)

    def _toggle_password(self):
        self.password_visible= not self.password_visible
        self.input_password.setEchoMode(
            QLineEdit.EchoMode.Normal if self.password_visible else QLineEdit.EchoMode.Password)
        #Icono de estado: ojo abierto cuando la contraseña se muestra, mono tapando los ojos cuando está oculta (como
        #antes).
        self.btn_ver_pass.setIcon(icono_emoji("👁" if self.password_visible else "🙈"))
        self.btn_ver_pass.setToolTip(
            "Ocultar contraseña" if self.password_visible else "Mostrar contraseña")


    def _toggle_translucido(self):
        self.translucido= not self.translucido
        self.main_window.login_translucido= self.translucido
        self.main_window.guardar_configuracion()
        #Icono de estado: bruma cuando el panel es translúcido, ventana sólida cuando no lo es.
        self.btn_translucido.setIcon(icono_emoji("🌫" if self.translucido else "🪟"))
        self.btn_translucido.setText("")
        self.btn_translucido.setToolTip(
            "Panel translúcido (pulsar para sólido)" if self.translucido
            else "Panel sólido (pulsar para translúcido)")
        self._apply_theme()

    def _abrir_recuperacion(self):
        dialogo= RecuperarPasswordDialog(self.main_window, self)
        dialogo.exec()

    def _iniciar_sesion(self):
        usuario= self.input_usuario.text().strip()
        password= self.input_password.text().strip()

        if not usuario or not password:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Campos incompletos",
                 "Ingrese usuario y contraseña.")
            return

        #Protección contra fuerza bruta: si esta cuenta acumuló demasiados intentos fallidos recientes, se rechaza sin
        #siquiera consultar la contraseña, aunque la que están escribiendo ahora sea la correcta.
        try:
            bloqueada, minutos_restantes = verificar_bloqueo_login(usuario)
        except Exception:
            bloqueada, minutos_restantes = False, 0
        if bloqueada:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta bloqueada temporalmente",
                 f"Esta cuenta se bloqueó por demasiados intentos fallidos.\n\n"
                 f"Intenta de nuevo en {minutos_restantes} minuto(s), o usa "
                 f"\"¿Olvidó su contraseña?\" si no recuerdas tu contraseña.")
            return

        #Feedback visual mientras se consulta la BD: en instalaciones con BD sincronizada/en red la consulta puede
        #tardar un poco y, sin esto, el botón se ve "muerto" (sin respuesta) durante ese momento.
        self.btn_ingresar.setEnabled(False)
        self.btn_ingresar.setText("⏳ Verificando...")
        QApplication.processEvents()
        try:
            try:
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT * FROM usuarios WHERE username = ?", (usuario,))
                fila= c.fetchone()
                conn.close()
            except Exception as e:
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Error",
                     f"No se pudo consultar la base de datos:\n{e}")
                return

            if not fila or not verificar_contrasena(password, fila["password"]):
                registrar_auditoria("Login", "Intento fallido", usuario)
                if fila:
                    #Solo se cuenta el intento contra el bloqueo si la cuenta existe: así un simple error de tipeo en el usuario no
                    #puede usarse para bloquear cuentas ajenas (bloqueo por nombre de usuario inexistente no tiene sentido).
                    try:
                        bloqueada_ahora, intentos_restantes = registrar_intento_fallido_login(usuario)
                    except Exception:
                        bloqueada_ahora, intentos_restantes = False, None
                    if bloqueada_ahora:
                        registrar_auditoria("Login", "Cuenta bloqueada por intentos fallidos", usuario)
                        _msg(self.main_window, self, QMessageBox.Icon.Critical, "Cuenta bloqueada",
                             "Se alcanzó el máximo de intentos fallidos. Esta cuenta quedó bloqueada "
                             "temporalmente por seguridad.")
                        return
                    if intentos_restantes is not None:
                        _msg(self.main_window, self, QMessageBox.Icon.Critical, "Acceso denegado",
                             f"Usuario o contraseña incorrectos.\n\n"
                             f"Te queda(n) {intentos_restantes} intento(s) antes de que la cuenta se "
                             f"bloquee temporalmente.")
                        return
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Acceso denegado",
                     "Usuario o contraseña incorrectos.")
                return

            if not fila["activo"]:
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta inactiva",
                     "Esta cuenta ha sido desactivada. Contacte al administrador.")
                return

            self.usuario_actual= fila["username"]
            self.rol_actual= fila["rol"]
            self.id_usuario_actual= fila["id"]
            self.nombre_completo= fila["nombre_completo"] or fila["username"]

            try:
                resetear_intentos_login(usuario)
            except Exception:
                pass

            self.main_window.recordar_usuario= self.chk_recordar.isChecked()
            self.main_window.ultimo_usuario= usuario if self.chk_recordar.isChecked() else ""
            self.main_window.guardar_configuracion()

            registrar_auditoria("Login", "Inicio de sesión exitoso", usuario, f"Rol: {fila['rol']}")
            self.accept()
        finally:
            self.btn_ingresar.setEnabled(True)
            self.btn_ingresar.setText("Iniciar Sesión")

    def _apply_theme(self):
        paleta= self.main_window.theme_palettes.get(
            self.main_window.tema_actual, self.main_window.theme_palettes["Indigo"])
        idx= 1 if self.main_window.modo_oscuro else 0
        bg_window, bg_panel = paleta["window_bg"][idx], paleta["display_bg"][idx]
        txt_prim, txt_sec = paleta["text_primary"][idx], paleta["text_secondary"][idx]
        bg_btn, accent = paleta["btn_num_bg"][idx], paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]

        opacidad_panel= 235 if self.translucido else 255

        self.setStyleSheet(f"""
            QDialog {{ background-color: transparent; }}
            QFrame#LoginFrame {{
                background-color: {_hex_a_rgba(bg_panel, opacidad_panel)};
                border: 1px solid {bg_btn};
                border-radius: 18px;
            }}
            QLabel#LoginTitulo {{ font-size: 22px; color: {accent}; font-weight: 800; background: transparent; }}
            QLabel#LoginSubtitulo {{ color: {txt_sec}; font-size: 12px; background: transparent; }}
            QLabel#LoginLabel {{ color: {txt_sec}; font-size: 10px; font-weight: bold;
                                 letter-spacing: 1px; background: transparent; margin-top: 4px; }}
            QLabel#LoginCapsLock {{ color: #F59E0B; font-size: 11px; font-weight: bold;
                                    background: transparent; margin-top: 2px; }}
            QLineEdit#LoginInput {{
                background-color: {bg_window}; border: 1px solid {bg_btn}; color: {txt_prim};
                padding: 10px; border-radius: 8px; font-size: 13px;
            }}
            QLineEdit#LoginInput:focus {{ border: 2px solid {accent}; }}
            QPushButton#BtnVerPass {{
                background-color: {bg_btn}; border: none; border-radius: 8px; font-size: 15px;
            }}
            QPushButton#BtnVerPass:hover {{ background-color: {accent}; }}
            QCheckBox#ChkRecordar {{ color: {txt_sec}; font-size: 12px; background: transparent; }}
            QPushButton#BtnLinkLogin {{
                background: transparent; color: {accent}; border: none; font-size: 12px;
                font-weight: bold; padding: 0px; text-decoration: underline;
            }}
            QPushButton#LoginButton {{
                background-color: {accent}; color: white; border: none; border-radius: 8px;
                font-size: 15px; font-weight: bold;
            }}
            QPushButton#LoginButton:hover {{ background-color: {hv_accent}; }}
            QPushButton#BtnCerrarLogin, QPushButton#BtnTranslucidoLogin {{
                background: transparent; color: {txt_sec}; border: none; border-radius: 15px; font-weight: bold;
            }}
            QPushButton#BtnCerrarLogin:hover, QPushButton#BtnTranslucidoLogin:hover {{
                background-color: {bg_btn}; color: {txt_prim};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos= event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos= None
        super().mouseReleaseEvent(event)


class RecuperarPasswordDialog(QDialog):
    """Recuperación de contraseña: por autorización de un Administrador activo,
    o por código enviado al correo registrado del usuario."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window= main_window
        aplicar_icono_ventana(self, ICONO_LOGIN)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
                             | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(420)
        self._build_ui()
        self._apply_theme()
        _centrar_y_al_frente(self, parent)

    def _campo(self, layout, etiqueta, placeholder="", es_password=False):
        lbl= QLabel(etiqueta)
        lbl.setObjectName("LoginLabel")
        layout.addWidget(lbl)
        entrada= QLineEdit()
        limitar_campo_texto(entrada, 300)
        entrada.setObjectName("LoginInput")
        entrada.setPlaceholderText(placeholder)
        if not es_password:
            layout.addWidget(entrada)
            return entrada

        #Igual que en el login principal: un botón 👁 al lado del campo para mostrar/ocultar la contraseña mientras se
        #escribe, útil sobre todo aquí porque son contraseñas NUEVAS que el usuario está inventando (más fácil
        #equivocarse sin verlas).
        entrada.setEchoMode(QLineEdit.EchoMode.Password)
        fila= QHBoxLayout()
        fila.setSpacing(6)
        fila.addWidget(entrada)
        btn_ver= QPushButton("")
        btn_ver.setIcon(icono_emoji("🔒"))
        btn_ver.setIconSize(_QSize_emoji(16, 16))
        btn_ver.setAutoDefault(False)
        btn_ver.setFixedSize(38, 38)
        btn_ver.setObjectName("BtnVerPass")
        btn_ver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ver.setCheckable(True)
        btn_ver.toggled.connect(lambda visible, e=entrada, b=btn_ver: (
            e.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password),
            b.setText("" if visible else "")))
        fila.addWidget(btn_ver)
        layout.addLayout(fila)
        return entrada

    def _build_ui(self):
        layout_principal= QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 24, 24, 24)

        self.frame= QFrame()
        self.frame.setObjectName("LoginFrame")
        sombra= QGraphicsDropShadowEffect()
        sombra.setBlurRadius(40)
        sombra.setOffset(0, 10)
        sombra.setColor(QColor(0, 0, 0, 140))
        self.frame.setGraphicsEffect(sombra)

        layout= QVBoxLayout(self.frame)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(6)

        fila_top= QHBoxLayout()
        fila_top.addStretch()
        btn_cerrar= QPushButton("")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setAutoDefault(False)
        btn_cerrar.setFixedSize(28, 28)
        btn_cerrar.setObjectName("BtnCerrarLogin")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.reject)
        fila_top.addWidget(btn_cerrar)
        layout.addLayout(fila_top)

        titulo= QLabel("Restablecer contraseña")
        titulo.setObjectName("LoginTitulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet("font-size: 18px;")
        layout.addWidget(titulo)
        layout.addSpacing(8)

        self.tabs= QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._tab_admin(), "Autorización Admin")
        self.tabs.addTab(self._tab_correo(), "Por Correo")

        layout_principal.addWidget(self.frame)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    #---------------- TAB: AUTORIZACIÓN DE ADMINISTRADOR ----------------
    def _tab_admin(self):
        w= QWidget()
        layout= QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        self.input_cuenta= self._campo(layout, "CUENTA A RESTABLECER", "Usuario de la cuenta afectada")

        layout.addSpacing(4)
        linea= QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(linea)
        layout.addSpacing(4)

        self.input_admin_user= self._campo(layout, "AUTORIZACIÓN - USUARIO ADMIN", "Usuario administrador")
        self.input_admin_pass= self._campo(layout, "AUTORIZACIÓN - CONTRASEÑA ADMIN", "Contraseña administrador",
                                             es_password= True)

        layout.addSpacing(4)
        self.input_nueva= self._campo(layout, "NUEVA CONTRASEÑA", "Nueva contraseña", es_password=True)
        self.input_confirmar= self._campo(layout, "CONFIRMAR CONTRASEÑA", "Repita la nueva contraseña",
                                            es_password= True)
        self.input_confirmar.returnPressed.connect(self._restablecer_por_admin)

        layout.addSpacing(8)
        btn_restablecer= QPushButton("Restablecer contraseña")
        btn_restablecer.setIcon(icono_emoji("♻"))
        btn_restablecer.setIconSize(_QSize_emoji(16, 16))
        btn_restablecer.setObjectName("LoginButton")
        btn_restablecer.setMinimumHeight(42)
        btn_restablecer.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restablecer.clicked.connect(self._restablecer_por_admin)
        layout.addWidget(btn_restablecer)
        return w

    #---------------- TAB: RECUPERACIÓN POR CORREO ----------------
    def _tab_correo(self):
        w= QWidget()
        layout= QVBoxLayout(w)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        info= QLabel("Se enviará un código de verificación de 6 dígitos al correo "
                      "registrado de la cuenta. El código expira en 15 minutos.")
        info.setObjectName("LoginInfoText")
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setText(
            "<p style='line-height:140%;'>Se enviará un código de verificación de 6 "
            "dígitos al correo registrado de la cuenta. El código expira en 15 minutos.</p>")
        layout.addWidget(info)
        layout.addSpacing(4)

        self.input_cuenta_correo= self._campo(layout, "CUENTA", "Usuario de la cuenta afectada")

        btn_enviar_codigo= QPushButton("Enviar código al correo")
        btn_enviar_codigo.setIcon(icono_emoji("✉"))
        btn_enviar_codigo.setIconSize(_QSize_emoji(16, 16))
        btn_enviar_codigo.setObjectName("LoginButton")
        btn_enviar_codigo.setMinimumHeight(38)
        btn_enviar_codigo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_enviar_codigo.clicked.connect(self._enviar_codigo)
        layout.addWidget(btn_enviar_codigo)

        layout.addSpacing(6)
        linea= QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(linea)
        layout.addSpacing(6)

        self.input_codigo= self._campo(layout, "CÓDIGO RECIBIDO", "Ej. 482913")
        self.input_nueva_correo= self._campo(layout, "NUEVA CONTRASEÑA", "Nueva contraseña", es_password=True)
        self.input_confirmar_correo= self._campo(layout, "CONFIRMAR CONTRASEÑA", "Repita la nueva contraseña",
                                                    es_password= True)
        self.input_confirmar_correo.returnPressed.connect(self._restablecer_por_correo)

        layout.addSpacing(8)
        btn_restablecer2= QPushButton("Restablecer con código")
        btn_restablecer2.setIcon(icono_emoji("♻"))
        btn_restablecer2.setIconSize(_QSize_emoji(16, 16))
        btn_restablecer2.setObjectName("LoginButton")
        btn_restablecer2.setMinimumHeight(42)
        btn_restablecer2.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restablecer2.clicked.connect(self._restablecer_por_correo)
        layout.addWidget(btn_restablecer2)
        return w

    def _apply_theme(self):
        paleta= self.main_window.theme_palettes.get(
            self.main_window.tema_actual, self.main_window.theme_palettes["Indigo"])
        idx= 1 if self.main_window.modo_oscuro else 0
        bg_window, bg_panel = paleta["window_bg"][idx], paleta["display_bg"][idx]
        txt_prim, txt_sec = paleta["text_primary"][idx], paleta["text_secondary"][idx]
        bg_btn, accent = paleta["btn_num_bg"][idx], paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]

        self.setStyleSheet(f"""
            QDialog {{ background-color: transparent; }}
            QFrame#LoginFrame {{
                background-color: {_hex_a_rgba(bg_panel, 245)};
                border: 1px solid {bg_btn}; border-radius: 16px;
            }}
            QLabel#LoginTitulo {{ color: {accent}; font-weight: 800; background: transparent; }}
            QLabel#LoginLabel {{ color: {txt_sec}; font-size: 10px; font-weight: bold;
                                 background: transparent; margin-top: 4px; }}
            QLabel#LoginInfoText {{ color: {txt_sec}; font-size: 11px; font-weight: normal;
                                 background: transparent; padding: 2px 4px 2px 0px; }}
            QLineEdit#LoginInput {{
                background-color: {bg_window}; border: 1px solid {bg_btn}; color: {txt_prim};
                padding: 9px; border-radius: 8px; font-size: 13px;
            }}
            QLineEdit#LoginInput:focus {{ border: 2px solid {accent}; }}
            QPushButton#LoginButton {{
                background-color: {accent}; color: white; border: none; border-radius: 8px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton#LoginButton:hover {{ background-color: {hv_accent}; }}
            QPushButton#BtnCerrarLogin {{
                background: transparent; color: {txt_sec}; border: none; border-radius: 14px; font-weight: bold;
            }}
            QPushButton#BtnCerrarLogin:hover {{ background-color: {bg_btn}; color: {txt_prim}; }}
            QTabWidget::pane {{ border: 1px solid {bg_btn}; border-radius: 8px; top: -1px; }}
            QTabBar::tab {{
                background: {bg_window}; color: {txt_sec}; padding: 8px 10px; font-size: 11px;
                font-weight: bold; border-top-left-radius: 6px; border-top-right-radius: 6px;
            }}
            QTabBar::tab:selected {{ background: {accent}; color: white; }}
        """)

    def _restablecer_por_admin(self):
        cuenta= self.input_cuenta.text().strip()
        admin_user= self.input_admin_user.text().strip()
        admin_pass= self.input_admin_pass.text().strip()
        nueva= self.input_nueva.text().strip()
        confirmar= self.input_confirmar.text().strip()

        if not all([cuenta, admin_user, admin_pass, nueva]):
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Campos incompletos",
                 "Completa todos los campos.")
            return
        if len(nueva) < 4:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Contraseña muy corta",
                 "Usa al menos 4 caracteres.")
            return
        if nueva != confirmar:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "No coincide",
                 "Las contraseñas nuevas no coinciden.")
            return

        try:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, rol, activo, password FROM usuarios WHERE username=?", (admin_user,))
            admin= c.fetchone()

            if not admin or admin["rol"] not in ("Administrador", "Director") or not admin["activo"]:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "No autorizado",
                     "Esas credenciales no corresponden a un Administrador/Director activo.")
                return

            #Esta pestaña es OTRA forma de autenticarse (con la contraseña del admin) además del login normal, así que debe
            #compartir el mismo límite de intentos: sin esto, alguien podía probar la contraseña del administrador aquí sin
            #ningún freno, evadiendo por completo el bloqueo de _iniciar_sesion.
            conn.close()
            bloqueada, minutos_restantes = verificar_bloqueo_login(admin_user)
            if bloqueada:
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta bloqueada temporalmente",
                     f"La cuenta '{admin_user}' se bloqueó por demasiados intentos fallidos.\n\n"
                     f"Intenta de nuevo en {minutos_restantes} minuto(s).")
                return

            if not verificar_contrasena(admin_pass, admin["password"]):
                registrar_auditoria("Seguridad", "Intento fallido de autorización de admin", admin_user)
                bloqueada_ahora, intentos_restantes = registrar_intento_fallido_login(admin_user)
                if bloqueada_ahora:
                    registrar_auditoria("Seguridad", "Cuenta bloqueada por intentos fallidos (recuperación)", admin_user)
                    _msg(self.main_window, self, QMessageBox.Icon.Critical, "Cuenta bloqueada",
                         "Se alcanzó el máximo de intentos fallidos. Esta cuenta quedó bloqueada temporalmente.")
                    return
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "No autorizado",
                     f"Contraseña de administrador incorrecta.\n\n"
                     f"Te queda(n) {intentos_restantes} intento(s) antes de que la cuenta se bloquee.")
                return

            resetear_intentos_login(admin_user)

            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id FROM usuarios WHERE username=?", (cuenta,))
            if not c.fetchone():
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta no encontrada",
                     f"No existe ninguna cuenta con el usuario '{cuenta}'.")
                return

            nueva_hash= hash_password(nueva)
            c.execute("UPDATE usuarios SET password=? WHERE username=?", (nueva_hash, cuenta))
            conn.commit()
            conn.close()
        except Exception as e:
            _msg(self.main_window, self, QMessageBox.Icon.Critical, "Error",
                 f"No se pudo restablecer la contraseña:\n{e}")
            return

        registrar_auditoria("Seguridad", "Restableció contraseña", admin_user, f"Cuenta afectada: {cuenta}")
        _msg(self.main_window, self, QMessageBox.Icon.Information, "Contraseña restablecida",
             f"La contraseña de '{cuenta}' fue actualizada correctamente.")
        self.accept()

    #---------------- LÓGICA: RECUPERACIÓN POR CORREO ----------------
    def _enviar_codigo(self):
        cuenta= self.input_cuenta_correo.text().strip()
        if not cuenta:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Campo requerido",
                 "Ingresa el usuario de la cuenta.")
            return
        try:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, correo, activo FROM usuarios WHERE username=?", (cuenta,))
            usuario= c.fetchone()

            if not usuario:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta no encontrada",
                     f"No existe ninguna cuenta con el usuario '{cuenta}'.")
                return
            if not usuario["activo"]:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta inactiva",
                     "Esta cuenta está desactivada. Contacta a un administrador.")
                return
            if not usuario["correo"]:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Sin correo registrado",
                     "Esta cuenta no tiene un correo registrado. Usa la recuperación por "
                     "autorización de Administrador.")
                return

            token= f"{secrets.randbelow(1000000):06d}"
            ahora= datetime.now()
            expira= ahora + timedelta(minutes=15)

            #Invalidar cualquier código anterior sin usar de esta cuenta:
            #sin esto, cada vez que alguien pide "reenviar código" quedan varios tokens simultáneamente válidos por 15
            #minutos cada uno, ampliando la ventana de ataque innecesariamente.
            c.execute("UPDATE tokens_recuperacion SET usado=1 WHERE usuario_id=? AND usado=0",
                      (usuario["id"],))

            c.execute("""INSERT INTO tokens_recuperacion (usuario_id, token, creado, expira, usado)
                         VALUES (?, ?, ?, ?, 0)""",
                      (usuario["id"], token, ahora.strftime("%Y-%m-%d %H:%M:%S"),
                       expira.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

            enviar_correo(
                usuario["correo"],
                "AcaDeXI - Código de recuperación de contraseña",
                f"Hola,\n\nTu código de verificación para restablecer tu contraseña en AcaDeXI es:\n\n"
                f"    {token}\n\n"
                f"Este código expira en 15 minutos. Si no solicitaste este cambio, ignora este mensaje."
            )
        except Exception as e:
            _msg(self.main_window, self, QMessageBox.Icon.Critical, "No se pudo enviar el código", str(e))
            return

        registrar_auditoria("Seguridad", "Solicitó código de recuperación por correo", cuenta)
        _msg(self.main_window, self, QMessageBox.Icon.Information, "Código enviado",
             f"Se envió un código de verificación a {usuario['correo']}.")

    def _restablecer_por_correo(self):
        cuenta= self.input_cuenta_correo.text().strip()
        codigo= self.input_codigo.text().strip()
        nueva= self.input_nueva_correo.text().strip()
        confirmar= self.input_confirmar_correo.text().strip()

        if not all([cuenta, codigo, nueva]):
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Campos incompletos",
                 "Completa el usuario, el código y la nueva contraseña.")
            return
        if len(nueva) < 4:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "Contraseña muy corta",
                 "Usa al menos 4 caracteres.")
            return
        if nueva != confirmar:
            _msg(self.main_window, self, QMessageBox.Icon.Warning, "No coincide",
                 "Las contraseñas nuevas no coinciden.")
            return

        try:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id FROM usuarios WHERE username=?", (cuenta,))
            usuario= c.fetchone()
            if not usuario:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Warning, "Cuenta no encontrada",
                     f"No existe ninguna cuenta con el usuario '{cuenta}'.")
                return

            c.execute("""SELECT id, expira, usado, intentos FROM tokens_recuperacion
                         WHERE usuario_id=? AND token=? ORDER BY id DESC LIMIT 1""",
                      (usuario["id"], codigo))
            token_fila= c.fetchone()
            if not token_fila:
                #No hubo coincidencia exacta de token: se cuenta como intento fallido contra el ÚLTIMO código vigente de esta
                #cuenta (si existe), para poner un límite a cuántos códigos se pueden probar sin acertar. Sin esto, alguien
                #podría intentar los 1,000,000 de combinaciones posibles sin ningún freno.
                c.execute("""SELECT id, intentos FROM tokens_recuperacion
                             WHERE usuario_id=? AND usado=0 ORDER BY id DESC LIMIT 1""",
                          (usuario["id"],))
                vigente= c.fetchone()
                if vigente:
                    nuevos_intentos= (vigente["intentos"] or 0) + 1
                    c.execute("UPDATE tokens_recuperacion SET intentos=? WHERE id=?",
                              (nuevos_intentos, vigente["id"]))
                    if nuevos_intentos >= 5:
                        c.execute("UPDATE tokens_recuperacion SET usado=1 WHERE id=?", (vigente["id"],))
                    conn.commit()
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Código inválido",
                     "El código ingresado no es válido para esta cuenta.")
                return
            if token_fila["usado"]:
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Código ya utilizado",
                     "Este código ya fue utilizado o se invalidó por demasiados intentos fallidos. "
                     "Solicita uno nuevo.")
                return
            if (token_fila["intentos"] or 0) >= 5:
                c.execute("UPDATE tokens_recuperacion SET usado=1 WHERE id=?", (token_fila["id"],))
                conn.commit()
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Código inválido",
                     "El código ingresado no es válido para esta cuenta.")
                return
            if datetime.strptime(token_fila["expira"], "%Y-%m-%d %H:%M:%S") < datetime.now():
                conn.close()
                _msg(self.main_window, self, QMessageBox.Icon.Critical, "Código expirado",
                     "El código expiró. Solicita uno nuevo.")
                return

            nueva_hash= hash_password(nueva)
            c.execute("UPDATE usuarios SET password=? WHERE id=?", (nueva_hash, usuario["id"]))
            c.execute("UPDATE tokens_recuperacion SET usado=1 WHERE id=?", (token_fila["id"],))
            conn.commit()
            conn.close()
        except Exception as e:
            _msg(self.main_window, self, QMessageBox.Icon.Critical, "Error",
                 f"No se pudo restablecer la contraseña:\n{e}")
            return

        registrar_auditoria("Seguridad", "Restableció contraseña por correo", cuenta)
        _msg(self.main_window, self, QMessageBox.Icon.Information, "Contraseña restablecida",
             f"La contraseña de '{cuenta}' fue actualizada correctamente.")
        self.accept()
