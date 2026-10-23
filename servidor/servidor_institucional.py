"""Servidor Institucional AcaDeXI — API REST mínima para sincronización directa (Fase B).

Pensado para que lo pueda poner en marcha alguien SIN conocimientos
técnicos de servidores: ya no hace falta exportar variables de entorno a
mano ni memorizar el comando de uvicorn. Basta con:

    python servidor_institucional.py

El propio script genera un token de acceso seguro la primera vez (o
reutiliza el que ya tenía guardado) y arranca el servidor mostrando en
pantalla la URL y el token que hay que copiar dentro de AcaDeXI:
Sincronización ▸ Sincronización Directa ▸ "Servidor institucional propio".

Este servidor es OPCIONAL y debe ejecutarlo la propia institución — AcaDeXI
no lo aloja ni lo opera. Para 3 formas realistas de tenerlo accesible desde
internet (de gratis a de pago, sin necesitar experiencia previa como
administrador de servidores) consulta LEEME_PRIMERO.txt, incluido al
exportar este paquete desde Sincronización ▸ Sincronización Directa ▸
"📦 Exportar Servidor Institucional".

Requiere: fastapi, uvicorn[standard], python-multipart
    pip install -r requirements_servidor.txt

Variables de entorno opcionales (solo para quien prefiera configurarlas a
mano; nadie está obligado a usarlas):
    ACADEXI_TOKEN     token secreto compartido (Bearer). Si no se define,
                       se genera uno automáticamente y se guarda en
                       token_acadexi.txt junto a este archivo.
    ACADEXI_ARCHIVO   ruta donde se guarda el archivo sincronizado
                       (por defecto: ./acadexi_sync.db)
    ACADEXI_PUERTO / PORT   puerto donde escuchar (por defecto: 8420;
                       muchas plataformas de hosting gratuitas asignan su
                       propio puerto automáticamente a través de PORT)
"""
import os
import socket
import secrets
import hashlib
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_TOKEN = os.path.join(CARPETA, "token_acadexi.txt")
ARCHIVO = os.environ.get("ACADEXI_ARCHIVO", os.path.join(CARPETA, "acadexi_sync.db"))
PUERTO = int(os.environ.get("ACADEXI_PUERTO", os.environ.get("PORT", "8420")))


def _obtener_o_crear_token():
    """Usa el token de la variable de entorno ACADEXI_TOKEN si alguien la
    definió a mano; si no, reutiliza el que ya se generó en una ejecución
    anterior (token_acadexi.txt); y si tampoco existe, genera uno nuevo,
    seguro y aleatorio, y lo guarda para la próxima vez. Así nadie tiene
    que inventar ni escribir una "clave secreta" — es la simplificación
    más importante frente a la versión anterior de este servidor."""
    token_env = os.environ.get("ACADEXI_TOKEN")
    if token_env:
        return token_env, "variable de entorno ACADEXI_TOKEN"
    if os.path.exists(ARCHIVO_TOKEN):
        with open(ARCHIVO_TOKEN, "r", encoding="utf-8") as f:
            guardado = f.read().strip()
        if guardado:
            return guardado, f"guardado en {os.path.basename(ARCHIVO_TOKEN)}"
    nuevo = secrets.token_urlsafe(24)
    with open(ARCHIVO_TOKEN, "w", encoding="utf-8") as f:
        f.write(nuevo)
    return nuevo, "generado automáticamente ahora"


TOKEN, _ORIGEN_TOKEN = _obtener_o_crear_token()

app = FastAPI(title="Servidor Institucional AcaDeXI", version="1.1")


def _verificar_token(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de autorización.")
    if authorization.split(" ", 1)[1] != TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido.")


def _hash_archivo(ruta):
    if not os.path.exists(ruta):
        return None
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


@app.get("/")
def raiz():
    """Página de estado SIN autenticación, solo para confirmar a simple
    vista (abriendo la URL en cualquier navegador) que el servidor está
    encendido. También sirve como 'health check' automático para
    plataformas de hosting gratuitas que revisan periódicamente que la
    aplicación siga viva."""
    return JSONResponse({
        "servicio": "Servidor Institucional AcaDeXI",
        "estado": "activo",
        "version": "1.1",
    })


@app.get("/estado")
def estado(authorization: Optional[str] = Header(None)):
    _verificar_token(authorization)
    existe = os.path.exists(ARCHIVO)
    return {
        "existe": existe,
        "hash": _hash_archivo(ARCHIVO) if existe else None,
        "modificado": (
            datetime.fromtimestamp(os.path.getmtime(ARCHIVO)).strftime("%Y-%m-%d %H:%M:%S")
            if existe else None
        ),
        "tamano_kb": round(os.path.getsize(ARCHIVO) / 1024, 1) if existe else 0,
    }


@app.get("/descargar")
def descargar(authorization: Optional[str] = Header(None)):
    _verificar_token(authorization)
    if not os.path.exists(ARCHIVO):
        raise HTTPException(status_code=404, detail="Todavía no hay ninguna copia en el servidor.")
    return FileResponse(ARCHIVO, media_type="application/octet-stream", filename="acadexi_sync.db")


@app.post("/subir")
async def subir(authorization: Optional[str] = Header(None), archivo: UploadFile = File(...)):
    _verificar_token(authorization)
    contenido = await archivo.read()
    carpeta = os.path.dirname(ARCHIVO)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(ARCHIVO, "wb") as f:
        f.write(contenido)
    return {"ok": True, "hash": _hash_archivo(ARCHIVO), "tamano_kb": round(len(contenido) / 1024, 1)}


def _ip_local():
    """Detecta la IP de este equipo dentro de su red local (no llega a
    tocar internet: solo usa el truco del socket UDP para que el sistema
    operativo revele por cuál interfaz saldría). Le ahorra a alguien sin
    conocimientos de redes tener que buscar su propia IP a mano."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn

    ip = _ip_local()
    print("=" * 66)
    print(" Servidor Institucional AcaDeXI")
    print("=" * 66)
    print(f" Token de acceso ({_ORIGEN_TOKEN}):")
    print(f"   {TOKEN}")
    print()
    print(" Copia el token de arriba y UNA de estas direcciones dentro de")
    print(" AcaDeXI, en: Sincronización > Sincronización Directa >")
    print(' "Servidor institucional propio":')
    print()
    print(f"   - Desde esta misma red local:  http://{ip}:{PUERTO}")
    print(f"   - Desde este mismo equipo:     http://localhost:{PUERTO}")
    print()
    print(" ¿Necesitas que equipos de OTRA red/sede también se conecten?")
    print(" Consulta LEEME_PRIMERO.txt (incluido en el paquete exportado")
    print(" desde AcaDeXI) para 3 formas de lograrlo, de gratis a de pago.")
    print("=" * 66)
    uvicorn.run(app, host="0.0.0.0", port=PUERTO)
