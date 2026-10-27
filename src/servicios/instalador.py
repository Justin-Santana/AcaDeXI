"""Instalador de AcaDeXI - Exportación de paquete de instalación pre-configurado
y del instalador (.exe) para Docentes/Personal.

Dos mecanismos de distribución conviven aquí:

1. ZIP con la BD + config.json + README (exportar_paquete / 
   exportar_paquete_con_credenciales) — método histórico, sigue funcionando.

2. Instalador para Docentes/Personal (AcaDeXI_Docentes_Setup.exe), compilado
   UNA SOLA VEZ por el Administrador con Inno Setup a partir de
   AcaDeXI_Docentes.iss, y colocado junto al ejecutable de la app. Ese
   instalador NO trae ninguna base de datos dentro (a diferencia del de
   Admin/Director): la persona instala la app vacía y luego importa su
   .acdx, el cual —si el Director lo generó con la "BD Base Institucional"
   incluida (ver perfil.DialogoGenerarPerfil / bd.guardar_bd_base_desde_actual)—
   trae tanto su perfil como la estructura institucional inicial. Así, el
   Docente/Personal solo necesita DOS archivos: el instalador (uno para
   todos) y su propio .acdx (uno por persona) — ver exportar_instalador_docentes().

Ambos métodos usan, cuando existe, la "BD Base Institucional" (bd.RUTA_BD_BASE)
en vez de la BD en uso actualmente por el Director, para NO distribuir sus
datos personales. Si todavía no se ha guardado una BD Base, se puede optar
por usar la BD actual (con advertencia explícita para quien lo solicita).
"""
import os
import shutil
import time
import zipfile
import tempfile
from datetime import datetime

from src.nucleo.rutas import obtener_carpeta_raiz
from src.nucleo.bd import get_app_data_dir, DB_PATH, obtener_conexion, existe_bd_base, RUTA_BD_BASE
from src.interfaz.ventana_principal import CONFIG_PATH
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, quitar_emojis_texto


class BDBaseNoDisponible(Exception):
    """Se lanza cuando se pide empaquetar 'la BD Base' y todavía no se ha
    guardado ninguna (ver bd.guardar_bd_base_desde_actual), y no se autorizó
    explícitamente usar la BD actual como reemplazo."""
    pass


def _ruta_bd_para_paquete(forzar_bd_actual=False):
    """Devuelve la ruta de la BD a incluir en un paquete/perfil: preferentemente
    la BD Base curada por el Director (sin sus datos personales). Si no existe
    y no se autorizó `forzar_bd_actual`, lanza BDBaseNoDisponible para que la UI
    pueda preguntar antes de distribuir la BD en uso actualmente."""
    if existe_bd_base():
        return RUTA_BD_BASE
    if forzar_bd_actual:
        return DB_PATH
    raise BDBaseNoDisponible(
        "Todavía no has guardado una 'BD Base Institucional' (Configuración "
        "Seguridad y Backups BD Base Institucional). Puedes generarla ahí, o "
        "continuar usando la base de datos actual (incluirá tus datos personales).")


def exportar_paquete(ruta_destino, main_window=None, forzar_bd_actual=False):
    """Crea un ZIP con la BD configurada, config.json y README.
    
    Args:
        ruta_destino: Carpeta donde se guardará el ZIP
        main_window: Referencia a la ventana principal (para obtener versión, etc.)
        forzar_bd_actual: si no hay BD Base guardada, usar la BD en uso actualmente
            en vez de lanzar BDBaseNoDisponible (la UI debe confirmarlo con el Admin)
    
    Returns:
        str: Ruta completa del archivo ZIP generado
    """
    ruta_bd= _ruta_bd_para_paquete(forzar_bd_actual)

    fecha= datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_zip= f"AcaDeXI-Instalador-{fecha}.zip"
    ruta_zip= os.path.join(ruta_destino, nombre_zip)
    
    #Obtener versión
    version= getattr(main_window, "VERSION", "1.0") if main_window else "1.0"
    
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        #1. Base de datos (BD Base si existe; si no, la actual)
        if os.path.exists(ruta_bd):
            z.write(ruta_bd, "acadexi.db")
        
        #2. Configuración (config.json)
        if os.path.exists(CONFIG_PATH):
            z.write(CONFIG_PATH, "config.json")
        
        #3. README con instrucciones
        readme_txt= f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ ACADEXI - PAQUETE DE INSTALACIÓN ║
║ Versión {version} ║
║ Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} ║
╚══════════════════════════════════════════════════════════════════════════════╝

📦 CONTENIDO DEL PAQUETE:
───────────────────────────────────────────────────────────────────────────────
• acadexi.db → Base de datos pre-configurada (wizard ya completado)
• config.json → Configuración local (tema, idioma, preferencias)

🚀 INSTRUCCIONES DE INSTALACIÓN:
───────────────────────────────────────────────────────────────────────────────

1. DESCOMPRIME esta carpeta en el equipo donde instalará AcaDeXI.

2. EJECUTE el programa:
 • Windows: acadexi.exe
 • Linux/Mac: python acadexi.py

3. INICIE SESIÓN con el usuario y contraseña proporcionados por su institución.
 (Si no tiene credenciales, contacte al Administrador/Director)

4. IMPORTE SU PERFIL INSTITUCIONAL (.acdx) si el Admin se lo entregó:
 • Haga clic en "📥 Importar Perfil Institucional (.acdx)" en el login
 • Seleccione el archivo.acdx que recibió
 • Esto precargará sus datos personales

⚠ NOTAS IMPORTANTES:
───────────────────────────────────────────────────────────────────────────────
• Esta instalación NO mostrará el asistente de configuración inicial.
• La base de datos ya está pre-configurada con los datos de su institución.
• Si necesita cambiar la configuración, use el módulo de Configuración
 dentro de la aplicación.

🔐 SEGURIDAD:
───────────────────────────────────────────────────────────────────────────────
• La base de datos contiene información institucional.
• Guarde este paquete en un lugar seguro.
• No lo comparta con personas no autorizadas.

📞 SOPORTE:
───────────────────────────────────────────────────────────────────────────────
Si tiene problemas, contacte al Administrador de su institución.

───────────────────────────────────────────────────────────────────────────────
© AcaDeXI - Sistema de Gestión Escolar
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        z.writestr("README.txt", readme_txt)
        
        #4. Archivo de instalación rápida
        quick_install_txt= """
═══════════════════════════════════════════════════════════════════════
ACADEXI - INSTALACIÓN RÁPIDA
═══════════════════════════════════════════════════════════════════════

1. Descomprime esta carpeta
2. Ejecuta acadexi.exe
3. Login con tu usuario

Listo. No verás el asistente de configuración.
═══════════════════════════════════════════════════════════════════════
"""
        z.writestr("INSTALAR.txt", quick_install_txt)
    
    return ruta_zip


def exportar_paquete_con_credenciales(ruta_destino, main_window=None, usuario_id=None,
                                       password_plana=None, forzar_bd_actual=False):
    """Exporta paquete incluyendo un perfil .acdx para un usuario específico.
    
    Args:
        ruta_destino: Carpeta donde se guardará el ZIP
        main_window: Referencia a la ventana principal
        usuario_id: ID del usuario para generar el perfil .acdx
        password_plana: si se provee, se incluye en texto plano dentro del .acdx
            (cifrado) para que el usuario no tenga que escribirla al importar el perfil
        forzar_bd_actual: si no hay BD Base guardada, usar la BD en uso actualmente
            en vez de lanzar BDBaseNoDisponible (la UI debe confirmarlo con el Admin)
    
    Returns:
        str: Ruta completa del archivo ZIP generado
    """
    ruta_bd= _ruta_bd_para_paquete(forzar_bd_actual)

    fecha= datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_zip= f"AcaDeXI-Instalador-ConPerfil-{fecha}.zip"
    ruta_zip= os.path.join(ruta_destino, nombre_zip)
    
    version= getattr(main_window, "VERSION", "1.0") if main_window else "1.0"
    
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        #1. Base de datos (BD Base si existe; si no, la actual)
        if os.path.exists(ruta_bd):
            z.write(ruta_bd, "acadexi.db")
        
        #2. Configuración
        if os.path.exists(CONFIG_PATH):
            z.write(CONFIG_PATH, "config.json")
        
        #3. Generar perfil .acdx para el usuario
        if usuario_id and main_window:
            from src.interfaz.perfil import guardar_perfil_archivo
            
            #Obtener modo de trabajo y carpeta de sincronización
            modo= getattr(main_window, "modo_trabajo", "Local")
            carpeta= getattr(main_window, "carpeta_sincronizacion", "")
            
            with tempfile.NamedTemporaryFile(suffix=".acdx", delete=False) as tmp:
                tmp_path= tmp.name
            
            try:
                guardar_perfil_archivo(tmp_path, usuario_id, modo, carpeta, password_plana=password_plana)
                
                #Obtener nombre de usuario para nombrar el archivo
                conn= obtener_conexion()
                c= conn.cursor()
                c.execute("SELECT username FROM usuarios WHERE id=?", (usuario_id,))
                user= c.fetchone()
                conn.close()
                
                nombre_perfil= f"perfil_{user['username'] if user else 'usuario'}.acdx" if user else "perfil.acdx"
                z.write(tmp_path, nombre_perfil)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        #4. README
        readme_txt= f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ ACADEXI - PAQUETE DE INSTALACIÓN ║
║ Con Perfil Institucional Incluido ║
║ Versión {version} ║
║ Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} ║
╚══════════════════════════════════════════════════════════════════════════════╝

📦 CONTENIDO DEL PAQUETE:
───────────────────────────────────────────────────────────────────────────────
• acadexi.db → Base de datos pre-configurada
• config.json → Configuración local
• perfil_*.acdx → Su perfil institucional personalizado

🚀 INSTRUCCIONES DE INSTALACIÓN:
───────────────────────────────────────────────────────────────────────────────

1. DESCOMPRIMA esta carpeta en su equipo.

2. EJECUTE el programa:
 • Windows: acadexi.exe
 • Linux/Mac: python acadexi.py

3. IMPORTE SU PERFIL INSTITUCIONAL:
 • Haga clic en "📥 Importar Perfil Institucional (.acdx)" en el login
 • Seleccione el archivo perfil_*.acdx que viene en este paquete
 • Esto precargará sus datos y configuración

4. INICIE SESIÓN con su usuario y contraseña.

⚠ NOTAS IMPORTANTES:
───────────────────────────────────────────────────────────────────────────────
• Esta instalación NO mostrará el asistente de configuración inicial.
• Su perfil ya está configurado con su rol y preferencias.
• No comparta su archivo.acdx con otras personas.

🔐 SEGURIDAD:
───────────────────────────────────────────────────────────────────────────────
• El archivo.acdx contiene su información de perfil.
• Guárdelo en un lugar seguro.
• No lo comparta con nadie.

───────────────────────────────────────────────────────────────────────────────
© AcaDeXI - Sistema de Gestión Escolar
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        z.writestr("README.txt", readme_txt)
        
        quick_install_txt= """
═══════════════════════════════════════════════════════════════════════
ACADEXI - INSTALACIÓN RÁPIDA (con perfil incluido)
═══════════════════════════════════════════════════════════════════════

1. Descomprime esta carpeta
2. Ejecuta acadexi.exe
3. En el login, haz clic en "Importar Perfil Institucional"
4. Selecciona el archivo .acdx que viene en este paquete
5. Login con tu usuario y contraseña

Listo. No verás el asistente de configuración.
═══════════════════════════════════════════════════════════════════════
"""
        z.writestr("INSTALAR.txt", quick_install_txt)
    
    return ruta_zip


#Instalador para docentes/personal (AcaDeXI_Docentes_Setup.exe) Este .exe se compila UNA SOLA VEZ con Inno
#Setup a partir del script
#AcaDeXI_Docentes.iss (incluido junto al código fuente) y se coloca junto
#al ejecutable de la app (obtener_carpeta_raiz()). AcaDeXI no lo compila en tiempo de ejecución: la app solo lo
#LOCALIZA y lo COPIA a la carpeta que el Administrador elija, listo para distribuir junto con los .acdx.
NOMBRE_SETUP_DOCENTES= "AcaDeXI_Docentes_Setup.exe"


def ruta_instalador_docentes():
    """Ruta esperada del instalador para Docentes/Personal ya compilado,
    junto al ejecutable/código de la aplicación."""
    return os.path.join(obtener_carpeta_raiz(), NOMBRE_SETUP_DOCENTES)


def existe_instalador_docentes():
    return os.path.exists(ruta_instalador_docentes())


def exportar_instalador_docentes(ruta_destino):
    """Copia AcaDeXI_Docentes_Setup.exe (ya compilado) a `ruta_destino`, listo
    para distribuir. Es el MISMO instalador para todos los Docentes/Personal;
    lo que cambia por persona es únicamente su archivo .acdx (ver
    perfil.DialogoGenerarPerfil). Devuelve la ruta final del archivo copiado.
    """
    origen= ruta_instalador_docentes()
    if not os.path.exists(origen):
        raise FileNotFoundError(
            f"No se encontró '{NOMBRE_SETUP_DOCENTES}' junto a la aplicación:\n"
            f"{os.path.dirname(origen)}\n\n"
            "Debes compilarlo una sola vez con Inno Setup a partir de "
            "AcaDeXI_Docentes.iss y colocar el .exe resultante en esa carpeta "
            f"con el nombre '{NOMBRE_SETUP_DOCENTES}'.")
    os.makedirs(ruta_destino, exist_ok=True)
    destino= os.path.join(ruta_destino, NOMBRE_SETUP_DOCENTES)

    #Si el Administrador eligió la MISMA carpeta donde ya vive el instalador (ej. la carpeta del programa), origen
    #y destino son el mismo archivo. En Windows, comparar solo por ruta absoluta normalizada es más fiable que
    #shutil.SameFileError (que a veces no detecta el caso y termina
    #intentando reabrir el propio archivo para escritura -> WinError 32
    #"el proceso no tiene acceso al archivo porque está siendo utilizado por otro proceso"). Si ya es el mismo
    #archivo, no hay nada que copiar.
    origen_norm= os.path.normcase(os.path.normpath(os.path.abspath(origen)))
    destino_norm= os.path.normcase(os.path.normpath(os.path.abspath(destino)))
    if origen_norm == destino_norm:
        return destino

    #Reintenta un par de veces: si el .exe acaba de tocarse (p.ej. recién compilado o copiado), es común que el
    #antivirus lo tenga bloqueado en análisis por una fracción de segundo.
    ultimo_error= None
    for intento in range(3):
        try:
            shutil.copy2(origen, destino)
            return destino
        except shutil.SameFileError:
            return destino
        except PermissionError as e:
            ultimo_error= e
            time.sleep(0.4)
        except OSError as e:
            #WinError 32 llega como PermissionError en la mayoría de casos, pero por si acaso se cuela como OSError
            #genérico también se reintenta antes de rendirse.
            if getattr(e, "winerror", None) == 32:
                ultimo_error= e
                time.sleep(0.4)
                continue
            raise

    raise PermissionError(
        f"No se pudo copiar '{NOMBRE_SETUP_DOCENTES}' porque el archivo está siendo usado "
        "por otro proceso (antivirus escaneándolo, el instalador abierto, una vista previa "
        "en el Explorador de Windows, etc.). Cierra esos programas e inténtalo de nuevo. Si "
        "el problema persiste, elige una carpeta distinta a la del propio programa como "
        "destino."
    ) from ultimo_error


def _copiar_instalador_generico(origen, nombre_archivo, ruta_destino):
    """Misma lógica de copia/reintento que exportar_instalador_docentes()
    (comparación por ruta normalizada + reintentos ante bloqueo temporal de
    antivirus), factorizada para no repetirla en Single Teacher/Side
    Stepper."""
    if not os.path.exists(origen):
        raise FileNotFoundError(
            f"No se encontró '{nombre_archivo}' junto a la aplicación:\n"
            f"{os.path.dirname(origen)}\n\n"
            f"Debes compilarlo una sola vez con Inno Setup a partir del .iss correspondiente "
            f"y colocar el .exe resultante en esa carpeta con el nombre '{nombre_archivo}'.")
    os.makedirs(ruta_destino, exist_ok=True)
    destino= os.path.join(ruta_destino, nombre_archivo)

    origen_norm= os.path.normcase(os.path.normpath(os.path.abspath(origen)))
    destino_norm= os.path.normcase(os.path.normpath(os.path.abspath(destino)))
    if origen_norm == destino_norm:
        return destino

    ultimo_error= None
    for intento in range(3):
        try:
            shutil.copy2(origen, destino)
            return destino
        except shutil.SameFileError:
            return destino
        except PermissionError as e:
            ultimo_error= e
            time.sleep(0.4)
        except OSError as e:
            if getattr(e, "winerror", None) == 32:
                ultimo_error= e
                time.sleep(0.4)
                continue
            raise

    raise PermissionError(
        f"No se pudo copiar '{nombre_archivo}' porque el archivo está siendo usado "
        "por otro proceso (antivirus escaneándolo, el instalador abierto, una vista previa "
        "en el Explorador de Windows, etc.). Cierra esos programas e inténtalo de nuevo. Si "
        "el problema persiste, elige una carpeta distinta a la del propio programa como "
        "destino."
    ) from ultimo_error


#Instalador para Single Teacher (AcaDeXI_SingleTeacher_Setup.exe)
NOMBRE_SETUP_SINGLE_TEACHER= "AcaDeXI_SingleTeacher_Setup.exe"


def ruta_instalador_single_teacher():
    return os.path.join(obtener_carpeta_raiz(), NOMBRE_SETUP_SINGLE_TEACHER)


def existe_instalador_single_teacher():
    return os.path.exists(ruta_instalador_single_teacher())


def exportar_instalador_single_teacher(ruta_destino):
    """Copia AcaDeXI_SingleTeacher_Setup.exe a `ruta_destino`. A diferencia
    de Docentes, Single Teacher no depende de ningún .acdx -arranca desde
    cero con su propio wizard (ver main.py, edicion_actual())."""
    return _copiar_instalador_generico(ruta_instalador_single_teacher(), NOMBRE_SETUP_SINGLE_TEACHER, ruta_destino)


#Instalador para Side Stepper (AcaDeXI_SideStepper_Setup.exe)
NOMBRE_SETUP_SIDE_STEPPER= "AcaDeXI_SideStepper_Setup.exe"
NOMBRE_PAQUETE_PERMISOS_SIDE_STEPPER= "permisos_side_stepper.json"


def ruta_instalador_side_stepper():
    return os.path.join(obtener_carpeta_raiz(), NOMBRE_SETUP_SIDE_STEPPER)


def existe_instalador_side_stepper():
    return os.path.exists(ruta_instalador_side_stepper())


def exportar_instalador_side_stepper(ruta_destino):
    """Copia AcaDeXI_SideStepper_Setup.exe a `ruta_destino`. Mismo .exe para
    las dos variantes de origen (exportado vs standalone): lo que cambia es
    si se acompaña o no del paquete de permisos generado abajo."""
    return _copiar_instalador_generico(ruta_instalador_side_stepper(), NOMBRE_SETUP_SIDE_STEPPER, ruta_destino)


def exportar_paquete_permisos_side_stepper(ruta_destino):
    """Escribe, junto al instalador, un JSON con los roles ya configurados
    en side_stepper_config.PanelPermisosSideStepper (ver
    permisos.listar_roles_side_stepper_configurados). Quien reciba este
    paquete lo importa en su primer arranque (WizardSideStepper) para
    quedar configurado con el rol/módulos que el Director decidió, sin
    pasar por el paso de "elige tu rol". Devuelve la ruta final."""
    import json
    from src.nucleo import permisos
    os.makedirs(ruta_destino, exist_ok=True)
    destino= os.path.join(ruta_destino, NOMBRE_PAQUETE_PERMISOS_SIDE_STEPPER)
    roles_configurados= permisos.listar_roles_side_stepper_configurados()
    if not roles_configurados:
        raise ValueError(
            "Todavía no configuraste ningún rol para esta copia de Side Stepper. "
            "Abre 'Exportar Side Stepper' y guarda al menos un rol con sus módulos "
            "antes de generar el paquete.")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"version_formato": 1, "roles": roles_configurados}, f, ensure_ascii=False, indent=2)
    return destino