#Quién puede ver y hacer qué en AcaDeXI. Todo lo de permisos vive en este archivo: si mañana cambia
#quién ve qué, se cambia acá y en ningún otro sitio.
import json
from datetime import datetime

from src.nucleo.bd import obtener_conexion
from src.nucleo.edicion import edicion_actual


# -----------------------------------------
# roles y módulos
# -----------------------------------------
ROLES= ["Administrador", "Director", "Coordinador", "Profesor", "Administrativo"]

#Lo máximo que cada rol puede llegar a ver. En Side Stepper el administrador puede quitar módulos de
#esta lista, pero nunca agregar uno que no esté. El orden es el orden en que salen en el menú.
PERMISOS_TECHO= {
    "Administrador": [
        "Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
        "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
        "Banco de Tareas", "Secuencias Didácticas", "Horario", "Calendario", "Observaciones",
        "Reportes", "Sincronización", "Configuración", "Materiales",
    ],
    "Director": [
        "Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
        "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
        "Banco de Tareas", "Secuencias Didácticas", "Horario", "Calendario", "Observaciones",
        "Reportes", "Sincronización", "Configuración", "Materiales",
    ],
    "Coordinador": [
        "Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
        "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
        "Banco de Tareas", "Secuencias Didácticas", "Horario", "Calendario", "Observaciones",
        "Reportes", "Sincronización", "Materiales",
    ],
    "Profesor": [
        "Dashboard", "Mis Materias", "Mis Estudiantes", "Asistencia", "Calificaciones",
        "Calificaciones Técnicas", "Banco de Tareas", "Secuencias Didácticas", "Horario",
        "Calendario", "Reportes", "Observaciones", "Copias de Seguridad", "Sincronización",
        "Configuración", "Materiales",
    ],
    "Administrativo": ["Dashboard", "Estudiantes", "Personal", "Reportes", "Configuración", "Materiales"],
}

#Todos los módulos que existen en algún rol, sin repetir y en orden alfabético.
MODULOS_EXISTENTES= sorted({modulo for lista in PERMISOS_TECHO.values() for modulo in lista})

#Módulos que solo existen en Side Stepper y que ningún rol fijo puede recibir: únicamente un cargo
#personalizado (el nombre lo pone cada institución, por ejemplo "Psicólogo/a") o el Administrador
#si activó el interruptor de Configuración > Usuarios y Roles.
MODULOS_EXTRA_SIDE_STEPPER= ["Psicología"]

#Roles que pueden crear, editar y eliminar en los módulos administrativos.
ROLES_GERENCIALES= {"Administrador", "Director", "Coordinador"}


# -----------------------------------------
# preguntas rápidas sobre el usuario que entró
# -----------------------------------------
#Si rol_actual es None es porque el login está desactivado, y en ese caso todo está permitido.
def tiene_acceso_gerencial(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None:
        return True

    return rol in ROLES_GERENCIALES


def puede_editar(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None:
        return True

    return rol in ("Administrador", "Director", "Coordinador", "Profesor")


def es_admin(main_window):

    rol= getattr(main_window, "rol_actual", None)

    return rol is None or rol in ("Administrador", "Director")


def es_profesor_restringido(main_window):

    #un Profesor solo ve sus propios datos
    return getattr(main_window, "rol_actual", None) == "Profesor"


# -----------------------------------------
# qué módulos se ven en el menú
# -----------------------------------------
def modulo_visible(rol, nombre_modulo, edicion=None):

    if rol is None:
        return True

    if nombre_modulo == "Dashboard":
        return True

    if edicion is None:
        edicion= edicion_actual()

    if nombre_modulo in MODULOS_EXTRA_SIDE_STEPPER:
        return _modulo_extra_visible(rol, nombre_modulo, edicion)

    if edicion == "side_stepper":
        return nombre_modulo in obtener_permisos_side_stepper(rol)

    return nombre_modulo in PERMISOS_TECHO.get(rol, [])


#Los módulos extra no existen en ninguna edición salvo Side Stepper, ni siquiera para un rol gerencial.
#Dentro de Side Stepper los ve un rol gerencial (supervisa) o quien lo tenga concedido.
def _modulo_extra_visible(rol, nombre_modulo, edicion):

    #Psicología tiene una excepción: el Administrador (y solo él, no Director ni Coordinador) lo ve en
    #cualquier edición si activó el interruptor, pensado para el Administrador que también es psicólogo.
    if nombre_modulo == "Psicología" and rol == "Administrador" and _psicologia_habilitada_para_admin():
        return True

    if edicion != "side_stepper":
        return False

    return rol in ROLES_GERENCIALES or nombre_modulo in obtener_permisos_side_stepper(rol)


#Lee el interruptor de Configuración > Usuarios y Roles > Módulo de Psicología. Se consulta cada vez
#porque es una sola fila y casi nunca cambia, así que no vale la pena guardarla en memoria.
def _psicologia_habilitada_para_admin():

    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT psicologia_habilitada_admin FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()

        return bool(fila and fila["psicologia_habilitada_admin"])

    except Exception:
        return False


# -----------------------------------------
# permisos de Side Stepper
# -----------------------------------------
def _preparar_tabla_permisos_side_stepper(conn):

    conn.execute("""CREATE TABLE IF NOT EXISTS permisos_side_stepper (
        rol TEXT PRIMARY KEY,
        modulos TEXT NOT NULL DEFAULT '[]',
        personalizado INTEGER DEFAULT 0,
        actualizado TEXT
    )""")
    conn.commit()


#Los módulos se guardan como texto JSON. Si el texto está dañado se devuelve una lista vacía.
def _leer_modulos(texto_json):

    try:
        return json.loads(texto_json)

    except (TypeError, ValueError):
        return []


def obtener_permisos_side_stepper(rol):

    conn= obtener_conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("SELECT modulos FROM permisos_side_stepper WHERE rol=?", (rol,))
    fila= c.fetchone()
    conn.close()

    if not fila:
        return []

    return _leer_modulos(fila["modulos"])


#El rol puede ser uno de los 5 fijos (su techo es PERMISOS_TECHO[rol]) o uno personalizado, que es
#cualquier texto que no esté en ROLES. Un cargo personalizado puede recibir cualquier módulo, incluidos
#los exclusivos de Side Stepper; un rol fijo nunca pasa de su propio techo, aunque se edite acá.
#Devuelve los módulos que de verdad se guardaron.
def guardar_permisos_side_stepper(rol, modulos):

    es_personalizado= rol not in ROLES
    techo= techo_para_rol_side_stepper(rol)
    modulos_validos= [modulo for modulo in modulos if modulo in techo]

    conn= obtener_conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("""INSERT INTO permisos_side_stepper (rol, modulos, personalizado, actualizado)
                 VALUES (?,?,?,?)
                 ON CONFLICT(rol) DO UPDATE SET
                    modulos=excluded.modulos, personalizado=excluded.personalizado,
                    actualizado=excluded.actualizado""",
              (rol, json.dumps(modulos_validos, ensure_ascii=False), 1 if es_personalizado else 0,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return modulos_validos


def listar_roles_side_stepper_configurados():

    conn= obtener_conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("SELECT rol, modulos, personalizado, actualizado FROM permisos_side_stepper ORDER BY rol")
    filas= c.fetchall()
    conn.close()

    roles= []

    for fila in filas:
        roles.append({"rol": fila["rol"], "modulos": _leer_modulos(fila["modulos"]),
                      "personalizado": bool(fila["personalizado"]), "actualizado": fila["actualizado"]})

    return roles


def eliminar_rol_side_stepper(rol):

    conn= obtener_conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("DELETE FROM permisos_side_stepper WHERE rol=?", (rol,))
    conn.commit()
    conn.close()


def techo_para_rol_side_stepper(rol):

    if rol not in ROLES:
        return MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER

    return PERMISOS_TECHO.get(rol, MODULOS_EXISTENTES)


def importar_paquete_permisos_side_stepper(ruta_archivo):

    with open(ruta_archivo, "r", encoding="utf-8") as archivo:
        datos= json.load(archivo)

    roles_importados= []

    for info_rol in datos.get("roles", []):
        guardados= guardar_permisos_side_stepper(info_rol["rol"], info_rol.get("modulos", []))
        roles_importados.append({"rol": info_rol["rol"], "modulos": guardados})

    return roles_importados


# -----------------------------------------
# psicología
# -----------------------------------------
#Nombres de los cargos personalizados que ahora mismo tienen el módulo "Psicología". Sirve para no
#escribir a mano "Psicólogo/a": cada institución le pone el nombre que quiera.
def roles_side_stepper_con_psicologia():

    return [info["rol"] for info in listar_roles_side_stepper_configurados()
            if "Psicología" in info["modulos"]]


#True si el usuario tiene un cargo personalizado de Side Stepper con el módulo "Psicología".
def es_psicologo(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None or rol in ROLES:
        return False

    return rol in roles_side_stepper_con_psicologia()


#Ven Psicología: el psicólogo que lo tiene concedido, cualquier rol gerencial (supervisa) y el
#Administrador si activó el interruptor. Un Profesor normal nunca lo ve, aunque vea Observaciones:
#por eso son tablas separadas.
def puede_ver_psicologia(main_window):

    if tiene_acceso_gerencial(main_window):
        return True

    rol= getattr(main_window, "rol_actual", None)

    if rol == "Administrador" and _psicologia_habilitada_para_admin():
        return True

    return es_psicologo(main_window)


# -----------------------------------------
# calificaciones técnicas del Profesor
# -----------------------------------------
#Es una decisión de cada docente (casilla en Configuración > Mi Cuenta). No se deduce de sus materias:
#puede activarla sin dar ningún módulo técnico, o apagarla aunque sí dé. Los roles gerenciales no pasan
#por acá: para ellos el módulo depende solo del tipo de institución.
def obtener_preferencia_calif_tecnicas(main_window):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return False

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT mostrar_calif_tecnicas FROM usuarios WHERE id=?", (id_usuario,))
    fila= c.fetchone()
    conn.close()

    return bool(fila["mostrar_calif_tecnicas"]) if fila else False


def guardar_preferencia_calif_tecnicas(main_window, activo):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE usuarios SET mostrar_calif_tecnicas=? WHERE id=?", (1 if activo else 0, id_usuario))
    conn.commit()
    conn.close()

    main_window.mostrar_calif_tecnicas= bool(activo)


# -----------------------------------------
# datos propios del Profesor
# -----------------------------------------
#El id de la tabla profesores que corresponde al usuario que entró, o None si no tiene.
def obtener_profesor_id(main_window):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return None

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT id FROM profesores WHERE usuario_id=?", (id_usuario,))
    fila= c.fetchone()
    conn.close()

    return fila["id"] if fila else None


#Para un Profesor: los ids de las secciones donde es guía, donde da alguna materia (por el horario)
#o donde está como co-docente. Devuelve None si no hay restricción, o sea si puede ver todas.
def obtener_secciones_permitidas(main_window):

    if not es_profesor_restringido(main_window):
        return None

    profesor_id= obtener_profesor_id(main_window)

    if profesor_id is None:
        return set()

    conn= obtener_conexion()
    c= conn.cursor()
    ids= set()

    c.execute("SELECT id FROM secciones WHERE profesor_guia_id=?", (profesor_id,))
    ids.update(fila["id"] for fila in c.fetchall())

    c.execute("""SELECT DISTINCT horarios.seccion_id as id FROM horarios
                 LEFT JOIN materias ON horarios.materia_id = materias.id
                 WHERE materias.profesor_id=?""", (profesor_id,))
    ids.update(fila["id"] for fila in c.fetchall() if fila["id"] is not None)

    c.execute("""SELECT DISTINCT seccion_id as id FROM materia_profesores
                 WHERE profesor_id=? AND seccion_id IS NOT NULL""", (profesor_id,))
    ids.update(fila["id"] for fila in c.fetchall())

    conn.close()

    return ids


#Para un Profesor: los ids de las materias que da, como titular o como co-docente (auxiliar,
#suplente). Devuelve None si no hay restricción.
def obtener_materias_permitidas(main_window):

    if not es_profesor_restringido(main_window):
        return None

    profesor_id= obtener_profesor_id(main_window)

    if profesor_id is None:
        return set()

    conn= obtener_conexion()
    c= conn.cursor()

    c.execute("SELECT id FROM materias WHERE profesor_id=?", (profesor_id,))
    ids= {fila["id"] for fila in c.fetchall()}

    c.execute("SELECT DISTINCT materia_id as id FROM materia_profesores WHERE profesor_id=?", (profesor_id,))
    ids.update(fila["id"] for fila in c.fetchall() if fila["id"] is not None)

    conn.close()

    return ids


# -----------------------------------------
# materiales: permisos por usuario y categoría
# -----------------------------------------
def tiene_acceso_total_materiales(main_window):

    #los roles gerenciales ven y administran todas las categorías sin mirar la tabla de permisos
    return tiene_acceso_gerencial(main_window)


#Los ids de categoría que el usuario puede abrir, o None si puede abrirlas todas (rol gerencial o login
#desactivado). Un usuario sin ninguna fila en permisos_materiales_usuario recibe un set vacío: todavía
#no tiene acceso a ninguna categoría.
def categorias_material_permitidas(main_window):

    if tiene_acceso_total_materiales(main_window):
        return None

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return None if getattr(main_window, "rol_actual", None) is None else set()

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT categoria_id FROM permisos_materiales_usuario WHERE usuario_id=?", (id_usuario,))
    ids= {fila["categoria_id"] for fila in c.fetchall()}
    conn.close()

    return ids


#Una cosa es poder ver una categoría y otra poder modificarla. Los gerenciales siempre pueden; el
#resto depende de la columna puede_editar, que permite dar acceso de solo consulta (por ejemplo, que
#un Profesor vea el inventario de un taller sin poder cambiarlo).
def puede_editar_categoria_material(main_window, categoria_id):

    if tiene_acceso_total_materiales(main_window):
        return True

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None or categoria_id is None:
        return False

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT puede_editar FROM permisos_materiales_usuario WHERE usuario_id=? AND categoria_id=?",
              (id_usuario, categoria_id))
    fila= c.fetchone()
    conn.close()

    return bool(fila and fila["puede_editar"])


#categorias_con_edicion es un diccionario {categoria_id: puede_editar}. Reemplaza TODO lo que el
#usuario tenía: si una categoría vieja no viene en el diccionario, pierde el acceso. Así es más fácil
#saber qué permisos tiene alguien que ir sumando altas sueltas con el tiempo.
def guardar_permisos_materiales_usuario(usuario_id, categorias_con_edicion):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("DELETE FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))

    for categoria_id, puede_editar_categoria in categorias_con_edicion.items():
        c.execute("""INSERT INTO permisos_materiales_usuario (usuario_id, categoria_id, puede_editar)
                     VALUES (?,?,?)""", (usuario_id, categoria_id, 1 if puede_editar_categoria else 0))

    conn.commit()
    conn.close()


#Devuelve {categoria_id: puede_editar} de un usuario, para llenar el diálogo de permisos.
def obtener_permisos_materiales_usuario(usuario_id):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT categoria_id, puede_editar FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))
    filas= c.fetchall()
    conn.close()

    return {fila["categoria_id"]: bool(fila["puede_editar"]) for fila in filas}
