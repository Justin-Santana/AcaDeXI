"""Sincronización Directa (Fase B) de AcaDeXI — métodos secundarios/avanzados.

Alternativas a la "carpeta compartida" (Fase A, en sincronizacion.py):
- Google Drive       (OAuth vía google-auth-oauthlib)
- Dropbox            (OAuth vía dropbox SDK, flujo "sin redirect")
- OneDrive           (OAuth vía msal, flujo "código de dispositivo")
- Servidor institucional propio (API REST, ver servidor_institucional.py)

Cada backend requiere que la institución/usuario aporte SUS PROPIAS
credenciales (client_id/secret de una app OAuth registrada por ellos, o la
URL+token de su propio servidor). AcaDeXI no incluye ni gestiona credenciales
propias — no hay "iniciar sesión con Google" genérico de la app.

Las credenciales y tokens se guardan cifrados localmente en
`sync_credenciales.enc` (junto a la base de datos), nunca en la BD compartida
ni en texto plano.
"""
import os
import json
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.nucleo.bd import DB_PATH, crear_backup

NOMBRE_ARCHIVO_SYNC= "acadexi_sync.db"

_CLAVE_LOCAL= b"AcaDeXI-credenciales-locales-clave-2026"
_fernet= Fernet(base64.urlsafe_b64encode(_CLAVE_LOCAL.ljust(32, b"0")[:32]))

RUTA_CREDENCIALES= os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "sync_credenciales.enc")

METODOS= {
    "carpeta": "Carpeta compartida (simple)",
    "google_drive": "Google Drive (directo, OAuth)",
    "dropbox": "Dropbox (directo, OAuth)",
    "onedrive": "OneDrive (directo, OAuth)",
    "servidor": "Servidor institucional propio",
}


#Almacén cifrado de credenciales/tokens locales (por equipo)
def _cargar_almacen():
    if not os.path.exists(RUTA_CREDENCIALES):
        return {}
    try:
        with open(RUTA_CREDENCIALES, "rb") as f:
            token= f.read()
        return json.loads(_fernet.decrypt(token).decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeDecodeError, OSError):
        return {}


def _guardar_almacen(datos):
    token= _fernet.encrypt(json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    with open(RUTA_CREDENCIALES, "wb") as f:
        f.write(token)


def guardar_credenciales(backend, datos):
    almacen= _cargar_almacen()
    almacen[backend]= datos
    _guardar_almacen(almacen)


def obtener_credenciales(backend):
    return _cargar_almacen().get(backend)


def eliminar_credenciales(backend):
    almacen= _cargar_almacen()
    almacen.pop(backend, None)
    _guardar_almacen(almacen)


def conectado(backend):
    return obtener_credenciales(backend) is not None


def desvincular(backend):
    """Rompe la conexión con `backend`: borra las credenciales/tokens
    guardados localmente para ese servicio, dejándolo como si nunca se
    hubiera conectado en este equipo.

    Es la vía de recuperación cuando algo quedó mal (token vencido o
    corrupto, credenciales equivocadas, cuenta que ya no corresponde, etc.):
    al desvincular, "Sincronización" vuelve a mostrar ese backend como "no
    conectado" y el usuario puede volver a conectarlo desde cero con
    _conectar (sin arrastrar el estado anterior).

    No borra NADA remoto: ni el archivo ya subido a la nube/servidor, ni la
    app OAuth ni el token en el servidor institucional (para revocar eso,
    hay que hacerlo del lado de Google/Dropbox/Microsoft/servidor). Solo
    quita la referencia local guardada por AcaDeXI."""
    eliminar_credenciales(backend)
    return True


def _hash_archivo(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    h= hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


#Google Drive
def google_drive_conectar(client_id, client_secret):
    """Ejecuta el flujo OAuth (abre el navegador y levanta un servidor local
    temporal para recibir la respuesta). Requiere que el administrador haya
    creado su propia app OAuth tipo 'Desktop' en Google Cloud Console."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    config_cliente= {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow= InstalledAppFlow.from_client_config(
        config_cliente, scopes=["https://www.googleapis.com/auth/drive.file"])
    credenciales= flow.run_local_server(port=0)
    guardar_credenciales("google_drive", {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": credenciales.refresh_token,
        "token": credenciales.token,
    })
    return True


def _google_drive_servicio():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    datos= obtener_credenciales("google_drive")
    if not datos:
        raise RuntimeError("Google Drive no está conectado. Ve a Sincronización y conéctalo primero.")
    cred= Credentials(
        token=datos.get("token"), refresh_token=datos.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=datos["client_id"], client_secret=datos["client_secret"],
        scopes=["https://www.googleapis.com/auth/drive.file"])
    if not cred.valid:
        cred.refresh(Request())
        datos["token"]= cred.token
        guardar_credenciales("google_drive", datos)
    return build("drive", "v3", credentials=cred)


def _google_drive_buscar_archivo(servicio):
    resp= servicio.files().list(
        q=f"name='{NOMBRE_ARCHIVO_SYNC}' and trashed=false",
        spaces="drive", fields="files(id, modifiedTime)").execute()
    archivos= resp.get("files", [])
    return archivos[0] if archivos else None


def google_drive_subir():
    from googleapiclient.http import MediaFileUpload
    servicio= _google_drive_servicio()
    existente= _google_drive_buscar_archivo(servicio)
    media= MediaFileUpload(DB_PATH, mimetype="application/octet-stream", resumable=False)
    if existente:
        servicio.files().update(fileId=existente["id"], media_body=media).execute()
    else:
        servicio.files().create(body={"name": NOMBRE_ARCHIVO_SYNC}, media_body=media, fields="id").execute()
    return "Google Drive"


def google_drive_descargar():
    import io
    from googleapiclient.http import MediaIoBaseDownload
    servicio= _google_drive_servicio()
    existente= _google_drive_buscar_archivo(servicio)
    if not existente:
        raise RuntimeError("Todavía no hay ninguna copia en Google Drive.")
    ruta_respaldo= crear_backup(tipo="Pre-sincronización (Google Drive)")
    buffer= io.BytesIO()
    solicitud= servicio.files().get_media(fileId=existente["id"])
    descargador= MediaIoBaseDownload(buffer, solicitud)
    listo= False
    while not listo:
        _, listo = descargador.next_chunk()
    with open(DB_PATH, "wb") as f:
        f.write(buffer.getvalue())
    return ruta_respaldo


#Dropbox
def dropbox_conectar(app_key, app_secret):
    """Inicia el flujo OAuth2 'sin redirect' de Dropbox: devuelve el objeto
    de flujo y la URL de autorización. El llamador (UI) debe abrir esa URL,
    pedir al usuario el código que Dropbox le muestra, y luego llamar a
    dropbox_finalizar_conexion() con ese código."""
    from dropbox import DropboxOAuth2FlowNoRedirect

    flow= DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type="offline")
    url_autorizacion= flow.start()
    return flow, url_autorizacion


def dropbox_finalizar_conexion(flow, codigo, app_key, app_secret):
    resultado= flow.finish(codigo.strip())
    guardar_credenciales("dropbox", {
        "app_key": app_key, "app_secret": app_secret,
        "refresh_token": resultado.refresh_token,
    })
    return True


def _dropbox_cliente():
    import dropbox
    datos= obtener_credenciales("dropbox")
    if not datos:
        raise RuntimeError("Dropbox no está conectado. Ve a Sincronización y conéctalo primero.")
    return dropbox.Dropbox(
        app_key=datos["app_key"], app_secret=datos["app_secret"],
        oauth2_refresh_token=datos["refresh_token"])


def dropbox_subir():
    import dropbox
    dbx= _dropbox_cliente()
    with open(DB_PATH, "rb") as f:
        dbx.files_upload(f.read(), f"/{NOMBRE_ARCHIVO_SYNC}", mode=dropbox.files.WriteMode("overwrite"))
    return "Dropbox"


def dropbox_descargar():
    dbx= _dropbox_cliente()
    ruta_respaldo= crear_backup(tipo="Pre-sincronización (Dropbox)")
    _, respuesta = dbx.files_download(f"/{NOMBRE_ARCHIVO_SYNC}")
    with open(DB_PATH, "wb") as f:
        f.write(respuesta.content)
    return ruta_respaldo


#OneDrive (Microsoft Graph vía MSAL — flujo de código de dispositivo)
def onedrive_conectar(client_id, tenant="consumers"):
    """Inicia el flujo de código de dispositivo: devuelve la app MSAL y el
    diccionario del flujo (incluye flujo['message'] con instrucciones y el
    código que el usuario debe ingresar en https://microsoft.com/devicelogin).
    Tras completarlo en el navegador, llamar a onedrive_finalizar_conexion()."""
    import msal

    app= msal.PublicClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant}")
    flujo= app.initiate_device_flow(scopes=["Files.ReadWrite"])
    if "user_code" not in flujo:
        raise RuntimeError("No se pudo iniciar el inicio de sesión de OneDrive.")
    return app, flujo


def onedrive_finalizar_conexion(app, flujo, client_id, tenant="consumers"):
    resultado= app.acquire_token_by_device_flow(flujo)
    if "access_token" not in resultado:
        raise RuntimeError(resultado.get("error_description", "No se pudo completar el inicio de sesión."))
    cuentas= app.get_accounts()
    guardar_credenciales("onedrive", {
        "client_id": client_id, "tenant": tenant,
        "home_account_id": cuentas[0]["home_account_id"] if cuentas else None,
    })
    return True


def _onedrive_token():
    import msal
    datos= obtener_credenciales("onedrive")
    if not datos:
        raise RuntimeError("OneDrive no está conectado. Ve a Sincronización y conéctalo primero.")
    app= msal.PublicClientApplication(
        datos["client_id"], authority=f"https://login.microsoftonline.com/{datos['tenant']}")
    cuentas= app.get_accounts()
    if not cuentas:
        raise RuntimeError("La sesión de OneDrive expiró. Vuelve a conectar la cuenta.")
    resultado= app.acquire_token_silent(["Files.ReadWrite"], account=cuentas[0])
    if not resultado or "access_token" not in resultado:
        raise RuntimeError("La sesión de OneDrive expiró. Vuelve a conectar la cuenta.")
    return resultado["access_token"]


def onedrive_subir():
    import requests
    token= _onedrive_token()
    with open(DB_PATH, "rb") as f:
        contenido= f.read()
    resp= requests.put(
        f"https://graph.microsoft.com/v1.0/me/drive/root:/{NOMBRE_ARCHIVO_SYNC}:/content",
        headers={"Authorization": f"Bearer {token}"}, data=contenido, timeout=60)
    resp.raise_for_status()
    return "OneDrive"


def onedrive_descargar():
    import requests
    token= _onedrive_token()
    ruta_respaldo= crear_backup(tipo="Pre-sincronización (OneDrive)")
    resp= requests.get(
        f"https://graph.microsoft.com/v1.0/me/drive/root:/{NOMBRE_ARCHIVO_SYNC}:/content",
        headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if resp.status_code == 404:
        raise RuntimeError("Todavía no hay ninguna copia en OneDrive.")
    resp.raise_for_status()
    with open(DB_PATH, "wb") as f:
        f.write(resp.content)
    return ruta_respaldo


#Servidor institucional propio (ver servidor_institucional.py)
def servidor_conectar(url_base, token):
    import requests
    url_base= url_base.rstrip("/")
    resp= requests.get(f"{url_base}/estado", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    resp.raise_for_status()
    guardar_credenciales("servidor", {"url": url_base, "token": token})
    return True


def _servidor_datos():
    datos= obtener_credenciales("servidor")
    if not datos:
        raise RuntimeError("El servidor institucional no está conectado. Configúralo en Sincronización.")
    return datos


def servidor_estado_remoto():
    import requests
    datos= _servidor_datos()
    resp= requests.get(f"{datos['url']}/estado", headers={"Authorization": f"Bearer {datos['token']}"}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def servidor_subir():
    import requests
    datos= _servidor_datos()
    with open(DB_PATH, "rb") as f:
        resp= requests.post(
            f"{datos['url']}/subir", headers={"Authorization": f"Bearer {datos['token']}"},
            files={"archivo": (NOMBRE_ARCHIVO_SYNC, f, "application/octet-stream")}, timeout=120)
    resp.raise_for_status()
    return datos["url"]


def servidor_descargar():
    import requests
    datos= _servidor_datos()
    ruta_respaldo= crear_backup(tipo="Pre-sincronización (Servidor institucional)")
    resp= requests.get(f"{datos['url']}/descargar", headers={"Authorization": f"Bearer {datos['token']}"}, timeout=120)
    if resp.status_code == 404:
        raise RuntimeError("Todavía no hay ninguna copia en el servidor.")
    resp.raise_for_status()
    with open(DB_PATH, "wb") as f:
        f.write(resp.content)
    return ruta_respaldo


#Despachador genérico usado por la UI
_SUBIR= {
    "google_drive": google_drive_subir,
    "dropbox": dropbox_subir,
    "onedrive": onedrive_subir,
    "servidor": servidor_subir,
}

_DESCARGAR= {
    "google_drive": google_drive_descargar,
    "dropbox": dropbox_descargar,
    "onedrive": onedrive_descargar,
    "servidor": servidor_descargar,
}


def _verificar_sandbox_inactivo():
    from src.nucleo import bd
    if bd.SANDBOX_TUTORIAL_ACTIVO:
        raise RuntimeError(
            "No se puede sincronizar ahora mismo: estás dentro del Tutorial Detallado, trabajando "
            "sobre una copia de práctica temporal. Termina o sal del tutorial primero.")


def subir(metodo):
    _verificar_sandbox_inactivo()
    return _SUBIR[metodo]()


def descargar(metodo):
    _verificar_sandbox_inactivo()
    return _DESCARGAR[metodo]()
