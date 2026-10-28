#Edición de AcaDeXI que está instalada en esta PC: full, docentes, single_teacher o side_stepper.
#Cada instalador deja una clave distinta en el registro de Windows, así que la edición se
#averigua leyendo esas claves, una sola vez al arrancar, y después queda guardada en memoria.
import sys

#Clave del registro que deja cada instalador, con la edición que representa.
CLAVES_POR_EDICION= (
    ("AcaDeXI_Docentes", "docentes"),
    ("AcaDeXI_SingleTeacher", "single_teacher"),
    ("AcaDeXI_SideStepper", "side_stepper"),
)

#Se llena la primera vez que se pregunta. Mientras siga en None, todavía no se averiguó.
_edicion_guardada= None


#Busca en el registro si existe la clave de desinstalación de alguna de las otras ediciones.
def _leer_edicion_del_registro():

    if sys.platform != "win32":
        return "full"
    try:

        import winreg
    except Exception:
        return "full"
    for clave, edicion in CLAVES_POR_EDICION:
        ruta= rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{clave}"
        try:

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta):
                return edicion
        except OSError:
            continue
    return "full"


#La edición de esta copia instalada. Si no hay ninguna clave, es la edición completa.
def edicion_actual():

    global _edicion_guardada
    if _edicion_guardada is None:
        _edicion_guardada= _leer_edicion_del_registro()
    return _edicion_guardada
