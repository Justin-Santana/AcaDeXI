#Perfil Institucional Portátil (.acdx).
#
#El Director (o el propio usuario, para sí mismo) genera un archivo .acdx
#cifrado con la configuración de una cuenta (institución, rol, modo de
#trabajo y carpeta de sincronización). Quien lo importa en el login se
#autoconfigura sin captura manual.
#
#Opcionalmente, el .acdx puede incluir la contraseña de la cuenta protegida
#con un PIN que define quien genera el perfil. La contraseña se cifra con
#una clave derivada de ESE PIN (PBKDF2-HMAC-SHA256 + salt aleatoria única
#por archivo), NO con la clave fija de la app (_CLAVE_APP, que solo protege
#el resto del contenido del perfil contra ediciones/lecturas casuales).
#Quien genera el perfil debe comunicar el PIN a quien lo recibe por un
#canal aparte del archivo (verbalmente, por teléfono, etc.) — así, alguien
#que solo tenga el .acdx (sin el PIN) no puede recuperar la contraseña,
#aunque conozca la clave fija embebida de la app. La seguridad de la cuenta
#en la base de datos sigue dependiendo del hash Argon2id de la contraseña,
#que nunca se ve afectado por lo que contenga el .acdx.
#
#Además, el .acdx generado por el Director para un Docente/Personal puede
#incluir la "BD Base Institucional" (estructura + usuarios, SIN los datos
#personales del Director — ver bd.guardar_bd_base_desde_actual). Así, un
#Docente/Personal solo necesita: 1) instalar la app con el instalador para
#Docentes (AcaDeXI_Docentes_Setup.exe, sin ninguna BD dentro), y 2) importar
#su .acdx en el login. Ese único archivo trae su perfil, su contraseña
#(opcional, protegida por PIN) y la base de datos institucional inicial.
import base64
import json
import os
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.nucleo.bd import obtener_conexion, RUTA_BD
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.nucleo.iconos import aplicar_icono_ventana, ICONO_DOCUMENTO

#Diálogo: generar perfil (.acdx) — usado desde Configuración → Usuarios
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFileDialog, QCheckBox)
from PySide6.QtCore import Qt
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji
EXTENSION= ".acdx"

_CLAVE_APP= b"AcaDeXI-perfil-institucional-clave-embebida-2026"
_fernet= Fernet(base64.urlsafe_b64encode(_CLAVE_APP.ljust(32, b"0")[:32]))

PIN_MINIMO= 4


MODOS_TRABAJO= ["Local", "Nube sincronizada", "Servidor institucional", "Sin conexión (offline)"]

TOOLTIPS_MODOS_TRABAJO= {
    "Local": "La base de datos vive solo en este equipo. No se sincroniza con nadie más; "
             "ideal para un único usuario o equipo que no comparte datos en tiempo real.",
    "Nube sincronizada": "La base de datos se guarda en una carpeta local que a su vez sincroniza "
             "un servicio externo (Google Drive, OneDrive, Dropbox, etc.). Varios equipos pueden "
             "compartir los datos, pero la sincronización depende de ese servicio.",
    "Servidor institucional": "La base de datos se sincroniza directamente contra un servidor propio "
             "de la institución (ver Sincronización Directa). Requiere URL y token configurados.",
    "Sin conexión (offline)": "El equipo trabaja de forma completamente aislada, sin ningún tipo de "
             "sincronización automática ni carpeta compartida. Los datos solo se mueven manualmente "
             "(backups, exportaciones, etc.).",
}

#Deriva una clave Fernet a partir de un PIN + salt aleatoria (única por
#archivo). PBKDF2 con muchas iteraciones hace que adivinar el PIN por
#fuerza bruta sea costoso incluso si alguien tiene el .acdx y sabe cómo
#está construido — a diferencia de la clave fija _CLAVE_APP, que es la
#misma para cualquier instalación de AcaDeXI.
def _derivar_clave_pin(pin, salt):

    kdf= PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
    return base64.urlsafe_b64encode(kdf.derive(pin.encode("utf-8")))


def _cifrar_password_con_pin(password_plana, pin):

    salt= os.urandom(16)
    clave= _derivar_clave_pin(pin, salt)
    token= Fernet(clave).encrypt(password_plana.encode("utf-8"))
    return base64.b64encode(salt).decode("ascii"), token.decode("ascii")


#Descifra la contraseña incluida en un perfil .acdx protegida por PIN.
#Lanza ValueError si el perfil no trae contraseña protegida, si no se
#proveyó PIN, o si el PIN es incorrecto (no se puede distinguir cuál de
#estas dos últimas causas fue, a propósito: no le decimos a quien
#adivina que "casi" acierta).
def descifrar_password_perfil(datos, pin):

    salt_b64= datos.get("password_salt")
    token= datos.get("password_cifrada")
    if not salt_b64 or not token:
        raise ValueError("Este perfil no incluye una contraseña protegida por PIN.")
    if not pin:
        raise ValueError("Debes ingresar el PIN para descifrar la contraseña de este perfil.")
    try:

        salt= base64.b64decode(salt_b64)
        clave= _derivar_clave_pin(pin, salt)
        return Fernet(clave).decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        raise ValueError("PIN incorrecto: no se pudo descifrar la contraseña de este perfil.")


#Asigna a cada ítem del combo un tooltip que explica qué implica ese modo de trabajo.
def _aplicar_tooltips_modos(combo):

    for i in range(combo.count()):
        texto= combo.itemText(i)
        tip= TOOLTIPS_MODOS_TRABAJO.get(texto)
        if tip:
            combo.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)


def _datos_perfil(usuario_id, modo_trabajo, carpeta_sincronizacion, password_plana=None, pin=None):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT username, nombre_completo, rol FROM usuarios WHERE id=?", (usuario_id,))
    u= c.fetchone()
    c.execute("SELECT nombre_institucion, tipo_institucion FROM configuracion WHERE id=1")
    cfg= c.fetchone()
    conn.close()
    if not u:
        raise ValueError("Usuario no encontrado.")
    datos= {
        "version": 3,
        "institucion": (cfg["nombre_institucion"] if cfg else "") or "",
        "tipo_institucion": (cfg["tipo_institucion"] if cfg else "") or "",
        "usuario": u["username"],
        "nombre_completo": u["nombre_completo"] or "",
        "rol": u["rol"],
        "modo": modo_trabajo,
        "sincronizacion": carpeta_sincronizacion or "",
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    #NOTA DE SEGURIDAD: si se provee, la contraseña se cifra con una clave derivada del PIN (ver
    #_derivar_clave_pin), NO con la clave fija de la app. Quien reciba el .acdx necesita también el PIN (comunicado
    #por separado) para recuperar la contraseña — solo tener el archivo no alcanza, a diferencia del esquema
    #anterior.
    if password_plana:
        if not pin or len(pin) < PIN_MINIMO:
            raise ValueError(f"Para incluir la contraseña en el perfil, define un PIN de al menos "
                              f"{PIN_MINIMO} caracteres.")
        salt_b64, token_b64= _cifrar_password_con_pin(password_plana, pin)
        datos["password_salt"]= salt_b64
        datos["password_cifrada"]= token_b64
    return datos


#Genera y guarda el archivo .acdx cifrado. Devuelve el diccionario de datos.
#
#Si se pasa `password_plana`, también debe pasarse `pin`: la contraseña se
#cifra con una clave derivada de ese PIN (ver _derivar_clave_pin) y queda
#dentro del perfil como `password_cifrada` + `password_salt`. Quien
#importe el perfil necesitará ese mismo PIN (comunicado por un canal
#aparte) para que la contraseña se autocomplete; sin el PIN correcto, el
#resto del perfil se aplica igual, pero la contraseña debe escribirse
#manualmente.
#
#Si se pasa `ruta_bd_base`, el contenido de ese archivo SQLite se incrusta
#(en base64) dentro del perfil como "BD Base Institucional", para que quien
#lo importe reciba de una sola vez su perfil Y la estructura institucional
#inicial, sin necesitar ningún otro archivo. Si esa BD Base tiene un
#logotipo institucional configurado (configuracion.logo_path), el archivo
#de imagen del logo también se incrusta (en base64) para que el Dashboard
#de quien importe el perfil pueda mostrarlo igual: el `logo_path` guardado
#en la BD es una ruta absoluta del equipo del Director, que no existe tal
#cual en el equipo del Docente/Personal.
def guardar_perfil_archivo(ruta, usuario_id, modo_trabajo="Local", carpeta_sincronizacion="",
                           password_plana= None, pin=None, ruta_bd_base=None):

    datos= _datos_perfil(usuario_id, modo_trabajo, carpeta_sincronizacion, password_plana, pin)
    if ruta_bd_base:
        if not os.path.exists(ruta_bd_base):
            raise ValueError(f"No se encontró la Base de Datos Base en:\n{ruta_bd_base}")
        with open(ruta_bd_base, "rb") as f_bd:
            datos["bd_base"]= base64.b64encode(f_bd.read()).decode("ascii")
        _incrustar_logo_de_bd_base(ruta_bd_base, datos)
    token= _fernet.encrypt(json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    #f: archivo .acdx abierto en binario para escritura; recibe el token cifrado.
    with open(ruta, "wb") as f:
        f.write(token)
    return datos


#Si la BD Base tiene un logotipo institucional configurado y el archivo
#existe en este equipo (el del Director), lo incrusta en `datos` como
#`logo_base64` + `logo_nombre_archivo`. No lanza error si algo falla: el
#logo es un extra deseable, nunca debe impedir generar el perfil.
def _incrustar_logo_de_bd_base(ruta_bd_base, datos):

    import sqlite3
    try:

        conn_base= sqlite3.connect(ruta_bd_base)
        conn_base.row_factory= sqlite3.Row
        fila= conn_base.execute("SELECT logo_path FROM configuracion WHERE id=1").fetchone()
        conn_base.close()
        logo_path= fila["logo_path"] if fila else None
        if logo_path and os.path.isfile(logo_path):
            with open(logo_path, "rb") as f_logo:
                datos["logo_base64"]= base64.b64encode(f_logo.read()).decode("ascii")
            datos["logo_nombre_archivo"]= os.path.basename(logo_path)
    except Exception:
        pass


#Lee y descifra un archivo .acdx. Lanza ValueError si es inválido.
def leer_perfil_archivo(ruta):

    #f: archivo .acdx abierto en binario para lectura; su contenido cifrado se guarda en token.
    with open(ruta, "rb") as f:
        token= f.read()
    try:

        return json.loads(_fernet.decrypt(token).decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise ValueError("El archivo .acdx no es válido, está corrupto o fue alterado.")


#Aplica el perfil importado a la configuración local (config.json) y
#autocompleta el usuario recordado. Devuelve True si el usuario ya existe
#en esta base de datos local.
#
#NOTA: si el perfil trae una BD Base incluida ("bd_base"), esa parte NO se
#aplica aquí — debe resolverse antes con perfil_incluye_bd_base()/
#aplicar_bd_base(), ya que requiere confirmación del usuario (reemplaza la
#BD local). Ver login.py -> _importar_perfil().
def aplicar_perfil(main_window, datos):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT id FROM usuarios WHERE username=?", (datos.get("usuario", ""),))
    existe= c.fetchone() is not None
    conn.close()

    main_window.recordar_usuario= True
    main_window.ultimo_usuario= datos.get("usuario", "")
    main_window.modo_trabajo= datos.get("modo", "Local")
    main_window.carpeta_sincronizacion= datos.get("sincronizacion", "")
    main_window.guardar_configuracion()
    return existe


#True si este perfil .acdx trae embebida una Base de Datos Institucional Base.
def perfil_incluye_bd_base(datos):

    return bool(datos.get("bd_base"))


#True si la BD local ya tiene al menos un usuario (instalación ya usada), en
#cuyo caso reemplazarla por la BD Base del perfil es una operación destructiva
#que debe confirmarse explícitamente antes de aplicarla.
def local_ya_tiene_usuarios():

    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT COUNT(*) n FROM usuarios")
        n= c.fetchone()["n"]
        conn.close()
        return n > 0
    except Exception:
        return False


#Escribe la BD Base incluida en el perfil sobre la BD local, reemplazándola
#por completo. Si ya existía una BD local con contenido, primero crea un
#respaldo (ver bd.crear_backup). Devuelve la ruta del respaldo, o None si no
#había nada que respaldar.
#
#Si el perfil trae un logotipo institucional embebido (ver
#_incrustar_logo_de_bd_base), también lo restaura en la carpeta de logos de
#ESTE equipo y corrige `configuracion.logo_path` para que apunte ahí, en
#vez de dejar la ruta absoluta del equipo del Director (que no existe en
#este equipo). Así, el Dashboard de un Docente/Personal que importó su
#perfil vía .acdx también ve el logotipo institucional.
def aplicar_bd_base(datos):

    from src.nucleo.bd import crear_backup, obtener_carpeta_datos

    ruta_backup= None
    if os.path.exists(RUTA_BD) and os.path.getsize(RUTA_BD) > 0:
        try:

            ruta_backup= crear_backup(tipo="Pre-importación de Perfil Institucional (.acdx)")
        except Exception:
            ruta_backup= None

    contenido= base64.b64decode(datos["bd_base"])
    os.makedirs(os.path.dirname(RUTA_BD), exist_ok=True)
    #f: archivo de la base de datos local abierto para escritura binaria; recibe la BD del perfil.
    with open(RUTA_BD, "wb") as f:
        f.write(contenido)

    logo_base64= datos.get("logo_base64")
    nombre_logo= datos.get("logo_nombre_archivo")
    if logo_base64 and nombre_logo:
        try:

            carpeta_logos= os.path.join(obtener_carpeta_datos(), "logos")
            os.makedirs(carpeta_logos, exist_ok=True)
            ruta_logo_local= os.path.join(carpeta_logos, nombre_logo)
            with open(ruta_logo_local, "wb") as f_logo:
                f_logo.write(base64.b64decode(logo_base64))
            conn= obtener_conexion()
            conn.execute("UPDATE configuracion SET logo_path=? WHERE id=1", (ruta_logo_local,))
            conn.commit()
            conn.close()
        except Exception:
            pass  #El logotipo es un extra: si falla, la BD Base ya quedó aplicada igual.

    return ruta_backup


class DialogoGenerarPerfil(QDialog):

    #Si `usuario_id` se pasa (flujo clásico desde la tabla de Usuarios,
    #con una fila ya seleccionada), el diálogo genera el perfil de ese
    #usuario directamente. Si se omite (flujo del botón "Generar Perfil
    #(.acdx) para un Usuario" en Seguridad y Backups), el diálogo muestra
    #primero un combo para elegir el usuario, sin depender de que haya
    #algo seleccionado en ninguna tabla.
    def __init__(self, main_window, usuario_id=None, username=None):

        super().__init__(main_window)
        self.main_window= main_window
        self.usuario_id= usuario_id
        self.username= username
        self._seleccion_libre= usuario_id is None
        self.setWindowTitle(f"Generar Perfil Institucional — {username}" if username
                            else "Generar Perfil Institucional")
        aplicar_icono_ventana(self, ICONO_DOCUMENTO)
        self.setMinimumWidth(420)

        disposicion= QVBoxLayout(self)

        if self._seleccion_libre:
            disposicion.addWidget(QLabel("Elige el usuario para el que quieres generar el archivo .acdx:"))
            self.combo_usuario= QComboBox()
            self._cargar_usuarios_combo()
            self.combo_usuario.currentIndexChanged.connect(self._usuario_combo_cambio)
            disposicion.addWidget(self.combo_usuario)

        self.lbl_intro= QLabel()
        self.lbl_intro.setWordWrap(True)
        disposicion.addWidget(self.lbl_intro)
        self._actualizar_intro()

        disposicion.addWidget(QLabel("Modo de trabajo:"))
        self.combo_modo= QComboBox()
        self.combo_modo.addItems(MODOS_TRABAJO)
        conectar_tooltip_seleccion(self.combo_modo, "Modo de trabajo de este equipo")
        _aplicar_tooltips_modos(self.combo_modo)
        disposicion.addWidget(self.combo_modo)

        disposicion.addWidget(QLabel("Carpeta de sincronización (opcional, ej. carpeta local de Drive/OneDrive/Dropbox):"))
        fila= QHBoxLayout()
        self.in_carpeta= QLineEdit()
        limitar_campo_texto(self.in_carpeta, 300)
        self.in_carpeta.setPlaceholderText("Sin carpeta de sincronización")
        fila.addWidget(self.in_carpeta)
        btn_examinar= QPushButton("")
        btn_examinar.setIcon(icono_emoji("📁"))
        btn_examinar.setIconSize(_QSize_emoji(16, 16))
        btn_examinar.clicked.connect(self._elegir_carpeta)
        fila.addWidget(btn_examinar)
        disposicion.addLayout(fila)

        lbl_password= QLabel("Contraseña actual del usuario (opcional):")
        lbl_password.setToolTip(
            "Si la ingresas, se incluirá cifrada con el PIN de abajo dentro del archivo. El usuario "
            "NO tendrá que escribirla al importar el perfil, siempre que también reciba el PIN. Debe "
            "coincidir con la contraseña real de la cuenta, o el perfil no se generará.")
        disposicion.addWidget(lbl_password)
        self.in_password= QLineEdit()
        limitar_campo_texto(self.in_password, 128)
        self.in_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_password.setPlaceholderText("Dejar vacío para no incluir la contraseña")
        self.in_password.setToolTip(lbl_password.toolTip())
        disposicion.addWidget(self.in_password)

        lbl_pin= QLabel(f"PIN para proteger la contraseña (mín. {PIN_MINIMO} caracteres):")
        lbl_pin.setToolTip(
            "Este PIN se usa para cifrar la contraseña dentro del archivo — NO viaja en el .acdx. "
            "Comunícaselo al usuario por un canal distinto (verbalmente, por teléfono, etc.), nunca "
            "junto con el archivo. Solo hace falta si arriba incluiste una contraseña.")
        disposicion.addWidget(lbl_pin)
        self.in_pin= QLineEdit()
        limitar_campo_texto(self.in_pin, 300)
        self.in_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_pin.setPlaceholderText("Requerido solo si incluyes la contraseña arriba")
        self.in_pin.setToolTip(lbl_pin.toolTip())
        disposicion.addWidget(self.in_pin)

        from src.nucleo.bd import existe_bd_base, info_bd_base
        self.chk_bd_base= QCheckBox("Incluir la BD Base Institucional en este perfil")
        if existe_bd_base():
            info= info_bd_base()
            self.chk_bd_base.setToolTip(
                f"BD Base guardada el {info['modificado']} ({info['tamano_kb']} KB).")
            disposicion.addWidget(self.chk_bd_base)
            disposicion.addWidget(QLabel("Así, además del perfil, este .acdx trae la estructura institucional "
                                "inicial (grados, secciones, materias, usuarios...) para que la persona "
                                "solo necesite instalar la app e importar este archivo — sin ningún otro "
                                "archivo ni base de datos aparte."))
        else:
            self.chk_bd_base.setEnabled(False)
            self.chk_bd_base.setToolTip(
                "Todavía no has guardado una BD Base. Ve a Seguridad y Backups "
                "BD Base Institucional para generarla primero.")
            disposicion.addWidget(self.chk_bd_base)

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        btn_generar= QPushButton("Generar Perfil")
        btn_generar.setIcon(icono_emoji("👤"))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAgregar")
        btn_generar.clicked.connect(self._generar)
        fila_botones.addWidget(btn_generar)
        disposicion.addLayout(fila_botones)

    def _cargar_usuarios_combo(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, username, nombre_completo, rol FROM usuarios
                     ORDER BY nombre_completo, username""")
        filas= c.fetchall()
        conn.close()
        self.combo_usuario.clear()
        for fila in filas:
            etiqueta= f"{fila['nombre_completo'] or fila['username']} ({fila['username']}) — {fila['rol']}"
            self.combo_usuario.addItem(etiqueta, userData=fila["id"])
        if filas:
            self.usuario_id= filas[0]["id"]
            self.username= filas[0]["username"]
        conectar_tooltip_seleccion(self.combo_usuario, "Usuario para el que se genera el Perfil Institucional")

    def _usuario_combo_cambio(self):

        self.usuario_id= self.combo_usuario.currentData()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT username FROM usuarios WHERE id=?", (self.usuario_id,))
        fila= c.fetchone()
        conn.close()
        self.username= fila["username"] if fila else None
        self._actualizar_intro()

    def _actualizar_intro(self):

        if self.usuario_id is None:
            self.lbl_intro.setText("Elige un usuario arriba para continuar.")
            return
        nombre_archivo= f"{self.username}{EXTENSION}" if self.username else f"usuario{EXTENSION}"
        self.lbl_intro.setText(f"Se generará un archivo <b>{nombre_archivo}</b> con la configuración "
                                "de este usuario para que la importe desde su equipo.")

    def _elegir_carpeta(self):

        carpeta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de sincronización")
        if carpeta:
            self.in_carpeta.setText(carpeta)

    def _generar(self):

        from src.nucleo.iconos import mostrar_mensaje
        from src.nucleo.bd import verificar_contrasena, RUTA_BD_BASE

        if self.usuario_id is None:
            mostrar_mensaje("advertencia", "Falta usuario", "Elige el usuario para el que quieres "
                            "generar el perfil.", self)
            return

        password_plana= self.in_password.text().strip()
        pin= self.in_pin.text().strip()
        if password_plana:
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT password FROM usuarios WHERE id=?", (self.usuario_id,))
            fila= c.fetchone()
            conn.close()
            if not fila or not verificar_contrasena(password_plana, fila["password"]):
                mostrar_mensaje("error", "Contraseña incorrecta",
                                "La contraseña ingresada no coincide con la contraseña actual de este "
                                "usuario. Verifícala o deja el campo vacío para generar el perfil sin ella.",
                                self)
                return
            if len(pin) < PIN_MINIMO:
                mostrar_mensaje("advertencia", "PIN requerido",
                                f"Para incluir la contraseña, define un PIN de al menos {PIN_MINIMO} "
                                "caracteres. Ese PIN NO viaja en el archivo: deberás comunicárselo al "
                                "usuario por separado.", self)
                return

        incluir_bd_base= self.chk_bd_base.isChecked()

        nombre_sugerido= f"{self.username}{EXTENSION}" if self.username else f"perfil{EXTENSION}"
        ruta, _= QFileDialog.getSaveFileName(
            self, "Guardar Perfil Institucional", nombre_sugerido, f"Perfil AcaDeXI (*{EXTENSION})")
        if not ruta:
            return
        if not ruta.endswith(EXTENSION):
            ruta += EXTENSION
        try:

            guardar_perfil_archivo(ruta, self.usuario_id, self.combo_modo.currentText(),
                                   self.in_carpeta.text().strip(), password_plana=password_plana or None,
                                   pin= pin or None,
                                   ruta_bd_base= RUTA_BD_BASE if incluir_bd_base else None)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo generar el perfil:\n{error}", self)
            return
        avisos= ""
        if password_plana:
            avisos += ("\n\n Este archivo incluye la contraseña, cifrada con el PIN que definiste. "
                       "Recuerda comunicarle el PIN al usuario por un medio DISTINTO al archivo "
                       "(nunca lo envíes junto con el .acdx).")
        if incluir_bd_base:
            avisos += ("\n\n Este archivo también incluye la BD Base Institucional: al importarlo, "
                       "reemplazará la base de datos local de quien lo abra.")
        mostrar_mensaje("exito", "Perfil Generado",
                        f"El archivo se guardó en:\n{ruta}\n\nEntrégalo al usuario para que lo importe "
                        "desde la pantalla de inicio de sesión." + avisos, self)
        self.accept()


#Diálogo: exportar mi propio perfil (.acdx) — autoservicio, desde Configuración → Mi Cuenta. Cualquier usuario
#logueado puede generar ÚNICAMENTE su propio perfil, nunca el de otro usuario.
class DialogoExportarPerfilPropio(QDialog):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.usuario_id= getattr(main_window, "id_usuario_actual", None)
        self.username= getattr(main_window, "usuario_actual", "") or "usuario"
        self.setWindowTitle(f"Exportar Mi Perfil Institucional — {self.username}")
        aplicar_icono_ventana(self, ICONO_DOCUMENTO)
        self.setMinimumWidth(440)

        disposicion= QVBoxLayout(self)
        disposicion.addWidget(QLabel(f"Se generará el archivo <b>{self.username}{EXTENSION}</b> con tu configuración "
                            "actual. Incluirá tu contraseña vigente, cifrada con el PIN que definas abajo, "
                            "para que puedas importarlo directamente en otro equipo sin tener que volver a "
                            "escribirla — siempre que también tengas ese PIN a la mano."))

        disposicion.addWidget(QLabel("Confirma tu contraseña actual:"))
        self.in_password= QLineEdit()
        limitar_campo_texto(self.in_password, 128)
        self.in_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_password.setPlaceholderText("Tu contraseña actual")
        disposicion.addWidget(self.in_password)

        lbl_pin= QLabel(f"Define un PIN para proteger la contraseña (mín. {PIN_MINIMO} caracteres):")
        lbl_pin.setToolTip(
            "Este PIN NO viaja dentro del archivo. Anótalo o recuérdalo: lo necesitarás al importar "
            "este mismo perfil en otro equipo para que la contraseña se autocomplete.")
        disposicion.addWidget(lbl_pin)
        self.in_pin= QLineEdit()
        limitar_campo_texto(self.in_pin, 300)
        self.in_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_pin.setPlaceholderText("PIN que recordarás para importar este perfil")
        self.in_pin.setToolTip(lbl_pin.toolTip())
        disposicion.addWidget(self.in_pin)

        disposicion.addWidget(QLabel("Modo de trabajo:"))
        self.combo_modo= QComboBox()
        self.combo_modo.addItems(MODOS_TRABAJO)
        conectar_tooltip_seleccion(self.combo_modo, "Modo de trabajo de este equipo")
        _aplicar_tooltips_modos(self.combo_modo)
        modo_actual= getattr(main_window, "modo_trabajo", None)
        if modo_actual in MODOS_TRABAJO:
            self.combo_modo.setCurrentText(modo_actual)
        disposicion.addWidget(self.combo_modo)

        disposicion.addWidget(QLabel("Carpeta de sincronización (opcional):"))
        fila= QHBoxLayout()
        self.in_carpeta= QLineEdit()
        limitar_campo_texto(self.in_carpeta, 300)
        self.in_carpeta.setText(getattr(main_window, "carpeta_sincronizacion", "") or "")
        self.in_carpeta.setPlaceholderText("Sin carpeta de sincronización")
        fila.addWidget(self.in_carpeta)
        btn_examinar= QPushButton("")
        btn_examinar.setIcon(icono_emoji("📁"))
        btn_examinar.setIconSize(_QSize_emoji(16, 16))
        btn_examinar.clicked.connect(self._elegir_carpeta)
        fila.addWidget(btn_examinar)
        disposicion.addLayout(fila)

        fila_botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        btn_generar= QPushButton("Exportar Mi Perfil")
        btn_generar.setIcon(icono_emoji("\uE002"))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAgregar")
        btn_generar.clicked.connect(self._generar)
        fila_botones.addWidget(btn_generar)
        disposicion.addLayout(fila_botones)

    def _elegir_carpeta(self):

        carpeta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de sincronización")
        if carpeta:
            self.in_carpeta.setText(carpeta)

    def _generar(self):

        from src.nucleo.iconos import mostrar_mensaje
        from src.nucleo.bd import verificar_contrasena

        if self.usuario_id is None:
            mostrar_mensaje("error", "Sin sesión", "No se detectó un usuario con sesión iniciada.", self)
            return

        password= self.in_password.text().strip()
        if not password:
            mostrar_mensaje("advertencia", "Falta contraseña",
                            "Ingresa tu contraseña actual para continuar.", self)
            return
        pin= self.in_pin.text().strip()
        if len(pin) < PIN_MINIMO:
            mostrar_mensaje("advertencia", "PIN requerido",
                            f"Define un PIN de al menos {PIN_MINIMO} caracteres para proteger tu "
                            "contraseña dentro del perfil.", self)
            return

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT password FROM usuarios WHERE id=?", (self.usuario_id,))
        fila= c.fetchone()
        conn.close()
        if not fila or not verificar_contrasena(password, fila["password"]):
            mostrar_mensaje("error", "Contraseña incorrecta", "La contraseña ingresada no es correcta.", self)
            return

        ruta, _= QFileDialog.getSaveFileName(
            self, "Guardar Mi Perfil Institucional", f"{self.username}{EXTENSION}",
            f"Perfil AcaDeXI (*{EXTENSION})")
        if not ruta:
            return
        if not ruta.endswith(EXTENSION):
            ruta += EXTENSION
        try:

            guardar_perfil_archivo(ruta, self.usuario_id, self.combo_modo.currentText(),
                                   self.in_carpeta.text().strip(), password_plana=password, pin=pin)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo generar tu perfil:\n{error}", self)
            return
        mostrar_mensaje("exito", "Perfil Exportado",
                        f"Tu perfil se guardó en:\n{ruta}\n\n🔒 Tu contraseña quedó cifrada dentro del "
                        "archivo con el PIN que definiste. Guarda el archivo y RECUERDA ese PIN por "
                        "separado: sin él, no podrás autocompletar la contraseña al importar este "
                        "perfil en otro equipo (tendrás que escribirla manualmente).", self)
        self.accept()
