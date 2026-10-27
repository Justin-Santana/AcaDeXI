#Rutas de AcaDeXI en un solo lugar. Hay dos ideas distintas y no hay que mezclarlas: dónde vive
#la instalación (obtener_carpeta_raiz) y dónde están los archivos que PyInstaller mete dentro del
#.exe (obtener_carpeta_recursos, obtener_carpeta_iconos, buscar_dato). En desarrollo las dos apuntan al repo, y
#así el mismo código sirve para correr desde Python y para el .exe ya empaquetado.
import os
import sys

#Carpeta del repo cuando se corre desde el código, sin empaquetar.
RAIZ_DEL_PROYECTO= os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


#True si esto corre desde el .exe que armó PyInstaller, False si corre desde el código.
def esta_empaquetado():
    return bool(getattr(sys, "frozen", False))


#Carpeta donde está el .exe instalado (ahí el administrador deja el instalador de Docentes) o la
#raíz del repo cuando se está trabajando en desarrollo.
def obtener_carpeta_raiz():
    if esta_empaquetado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return RAIZ_DEL_PROYECTO


#Carpeta de los recursos que van dentro del .exe (_internal). En desarrollo es src/assets.
def obtener_carpeta_recursos():
    if esta_empaquetado():
        dentro_del_exe= getattr(sys, "_MEIPASS", None)
        return dentro_del_exe or os.path.join(obtener_carpeta_raiz(), "_internal")
    return os.path.join(RAIZ_DEL_PROYECTO, "src", "assets")


#Carpeta de los iconos, siempre colgando de los recursos.
def obtener_carpeta_iconos():
    return os.path.join(obtener_carpeta_recursos(), "iconos")


#Carpetas donde puede estar un archivo suelto (la guía PDF, el servidor, las licencias), en el
#orden en que se buscan: primero lo empaquetado y al final la carpeta del .exe.
def _carpetas_datos():
    if esta_empaquetado():
        raiz= obtener_carpeta_raiz()
        return [obtener_carpeta_recursos(), os.path.join(raiz, "_internal"), raiz]
    return [os.path.join(RAIZ_DEL_PROYECTO, "servidor"), os.path.join(RAIZ_DEL_PROYECTO, "docs"),
            os.path.join(RAIZ_DEL_PROYECTO, "src", "assets"), RAIZ_DEL_PROYECTO]


#Ruta completa de un archivo suelto empaquetado, o "" si no aparece en ninguna carpeta.
def buscar_dato(nombre):
    for carpeta in _carpetas_datos():
        ruta= os.path.join(carpeta, nombre)
        if os.path.isfile(ruta):
            return ruta
    return ""
