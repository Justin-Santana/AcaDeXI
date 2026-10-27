# -----------------------------------------
# permisos
#quién ve qué módulo y quién puede editar. Todo se decide por el rol que trae la ventana
#principal en main_window.rol_actual; si no hay rol (login desactivado) se deja pasar todo.
# -----------------------------------------
ROLES= ["Administrador", "Director", "Coordinador", "Profesor", "Administrativo"]

# -----------------------------------------
# lo que puede ver cada rol
#los tres gerenciales ven lo mismo; el Coordinador es el único que no entra a Configuración, por
#eso su lista se arma sin ese módulo en vez de repetir la lista entera tres veces.
# -----------------------------------------
MODULOS_GERENCIALES= ["Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
                      "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
                      "Banco de Tareas", "Horario", "Calendario", "Observaciones", "Reportes",
                      "Sincronización"]

PERMISOS_TECHO= {
    "Administrador": MODULOS_GERENCIALES + ["Configuración"],
    "Director": MODULOS_GERENCIALES + ["Configuración"],
    "Coordinador": list(MODULOS_GERENCIALES),
    "Profesor": ["Dashboard", "Mis Materias", "Mis Estudiantes", "Asistencia", "Calificaciones",
                 "Calificaciones Técnicas", "Banco de Tareas", "Horario", "Calendario", "Reportes",
                 "Observaciones", "Copias de Seguridad", "Sincronización", "Configuración"],
    "Administrativo": ["Dashboard", "Estudiantes", "Personal", "Reportes", "Configuración", "Materiales"],
}

ACCESO_MODULOS= PERMISOS_TECHO        #nombre viejo, se mantiene para no romper lo que ya lo usa

#"Materiales" se agrega aparte para no repetir la lista completa arriba: los gerenciales y el
#Profesor también lo ven, cada uno con el material de su propia aula o taller.
for rol_con_materiales in ("Administrador", "Director", "Coordinador", "Profesor"):
    PERMISOS_TECHO[rol_con_materiales].append("Materiales")

MODULOS_EXISTENTES= sorted({modulo for lista in PERMISOS_TECHO.values() for modulo in lista})

#módulos que solo existen en la edición Side Stepper y que ningún rol fijo puede recibir: se le
#otorgan a un cargo personalizado (por ejemplo "Psicólogo/a", el nombre lo pone la institución).
MODULOS_EXTRA_SIDE_STEPPER= ["Psicología"]

#los que pueden crear, editar y borrar en los módulos administrativos.
ROLES_GERENCIALES= {"Administrador", "Director", "Coordinador"}


# -----------------------------------------
# conexión
#se pide acá dentro y no arriba del archivo para no armar un círculo de importaciones con bd.py
# -----------------------------------------
def _conexion():

    from src.nucleo.bd import obtener_conexion

    return obtener_conexion()


# -----------------------------------------
# rol y edición
# -----------------------------------------
def tiene_acceso_gerencial(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None:
        return True                   #sin login, todo el mundo entra

    return rol in ROLES_GERENCIALES


def _edicion_actual_segura():

    try:
        from src.nucleo.edicion import edicion_actual
        return edicion_actual()

    except Exception:
        return "full"                 #si algo falla, se asume la edición completa


#el interruptor de Configuración ▸ Usuarios y Roles que deja al Administrador entrar a Psicología
#sin tener que crear un cargo de Side Stepper. Se lee en caliente porque cambia poco y es una
#sola fila de la tabla configuracion.
def _psicologia_habilitada_para_admin():

    try:
        conn= _conexion()
        c= conn.cursor()
        c.execute("SELECT psicologia_habilitada_admin FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()

        return bool(fila and fila["psicologia_habilitada_admin"])

    except Exception:
        return False


# -----------------------------------------
# ¿este rol ve este módulo?
# -----------------------------------------
def modulo_visible(rol, nombre_modulo, edicion=None):

    if rol is None:
        return True                   #sin login no se esconde nada

    if nombre_modulo == "Dashboard":
        return True                   #el Dashboard siempre está

    if edicion is None:
        edicion= _edicion_actual_segura()

    #los módulos exclusivos de Side Stepper no existen en las otras ediciones, ni para un
    #gerencial; dentro de Side Stepper los ve un gerencial o el cargo que los tenga otorgados.
    if nombre_modulo in MODULOS_EXTRA_SIDE_STEPPER:

        #excepción: el Administrador puede tener Psicología en cualquier edición si activó el
        #interruptor de Configuración.
        if nombre_modulo == "Psicología" and rol == "Administrador" and _psicologia_habilitada_para_admin():
            return True

        if edicion != "side_stepper":
            return False

        return rol in ROLES_GERENCIALES or nombre_modulo in obtener_permisos_side_stepper(rol)

    #en Side Stepper manda lo que se configuró para ese rol, no el techo de fábrica.
    if edicion == "side_stepper":
        return nombre_modulo in obtener_permisos_side_stepper(rol)

    return nombre_modulo in PERMISOS_TECHO.get(rol, [])


# -----------------------------------------
# configuración de Side Stepper
#la tabla guarda, por rol, la lista de módulos en JSON. Si un rol no está configurado todavía,
#devuelve una lista vacía.
# -----------------------------------------
def _preparar_tabla_permisos_side_stepper(conn):

    conn.execute("""CREATE TABLE IF NOT EXISTS permisos_side_stepper (
        rol TEXT PRIMARY KEY,
        modulos TEXT NOT NULL DEFAULT '[]',
        personalizado INTEGER DEFAULT 0,
        actualizado TEXT
    )""")
    conn.commit()


def obtener_permisos_side_stepper(rol):

    import json

    conn= _conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("SELECT modulos FROM permisos_side_stepper WHERE rol=?", (rol,))
    fila= c.fetchone()
    conn.close()

    if not fila:
        return []

    try:
        return json.loads(fila["modulos"])

    except (TypeError, ValueError):
        return []


#guarda lo que se marcó para un rol. Si es uno de los cinco fijos, el techo es su propio
#PERMISOS_TECHO; si es un cargo personalizado, el techo es todo lo que existe. Devuelve lo que
#quedó guardado de verdad, porque lo que no entra en el techo se descarta.
def guardar_permisos_side_stepper(rol, modulos):

    import json
    from datetime import datetime

    es_personalizado= rol not in ROLES
    techo= (MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER) if es_personalizado else PERMISOS_TECHO.get(rol, [])
    modulos_validos= [modulo for modulo in modulos if modulo in techo]

    conn= _conexion()
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

    import json

    conn= _conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("SELECT rol, modulos, personalizado, actualizado FROM permisos_side_stepper ORDER BY rol")
    filas= c.fetchall()
    conn.close()

    resultado= []
    for fila in filas:

        try:
            modulos= json.loads(fila["modulos"])

        except (TypeError, ValueError):
            modulos= []

        resultado.append({"rol": fila["rol"], "modulos": modulos,
                          "personalizado": bool(fila["personalizado"]), "actualizado": fila["actualizado"]})

    return resultado


def eliminar_rol_side_stepper(rol):

    conn= _conexion()
    _preparar_tabla_permisos_side_stepper(conn)
    c= conn.cursor()
    c.execute("DELETE FROM permisos_side_stepper WHERE rol=?", (rol,))
    conn.commit()
    conn.close()


#lo máximo que se le puede marcar a un rol en la pantalla de Side Stepper.
def techo_para_rol_side_stepper(rol):

    if rol not in ROLES:
        return MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER

    return PERMISOS_TECHO.get(rol, MODULOS_EXISTENTES)


# -----------------------------------------
# psicología
# -----------------------------------------
# nombres de los cargos personalizados que tienen Psicología otorgada. Se pregunta así en vez de
#buscar "Psicólogo/a" a mano, porque la institución puede llamar el cargo como quiera.
def roles_side_stepper_con_psicologia():

    return [info["rol"] for info in listar_roles_side_stepper_configurados() if "Psicología" in info["modulos"]]


def es_psicologo(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None or rol in ROLES:
        return False                  #los cinco roles fijos no son "psicólogo"

    return rol in roles_side_stepper_con_psicologia()


#quién entra de verdad a Psicología: el cargo que la tiene otorgada, cualquier gerencial
#(supervisión institucional) y el Administrador si activó el interruptor. Un Profesor normal no
#entra nunca, aunque vea Observaciones: son tablas separadas a propósito.
def puede_ver_psicologia(main_window):

    if tiene_acceso_gerencial(main_window):
        return True

    rol= getattr(main_window, "rol_actual", None)

    if rol == "Administrador" and _psicologia_habilitada_para_admin():
        return True

    return es_psicologo(main_window)


# -----------------------------------------
# importar permisos desde un paquete
# -----------------------------------------
def importar_paquete_permisos_side_stepper(ruta_archivo):

    import json

    with open(ruta_archivo, "r", encoding="utf-8") as archivo:
        datos= json.load(archivo)

    roles_importados= []
    for info_rol in datos.get("roles", []):

        guardados= guardar_permisos_side_stepper(info_rol["rol"], info_rol.get("modulos", []))
        roles_importados.append({"rol": info_rol["rol"], "modulos": guardados})

    return roles_importados


# -----------------------------------------
# preferencia personal del Profesor
#"Calificaciones Técnicas" lo activa cada docente a mano desde Configuración ▸ Mi Cuenta, aunque
#no imparta ningún técnico, y puede desactivarlo aunque sí lo haga. Los gerenciales no pasan por
#acá: para ellos el módulo depende solo del tipo de institución.
# -----------------------------------------
def obtener_preferencia_calif_tecnicas(main_window):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return False

    conn= _conexion()
    c= conn.cursor()
    c.execute("SELECT mostrar_calif_tecnicas FROM usuarios WHERE id=?", (id_usuario,))
    fila= c.fetchone()
    conn.close()

    return bool(fila["mostrar_calif_tecnicas"]) if fila else False


def guardar_preferencia_calif_tecnicas(main_window, activo):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return

    conn= _conexion()
    c= conn.cursor()
    c.execute("UPDATE usuarios SET mostrar_calif_tecnicas=? WHERE id=?", (1 if activo else 0, id_usuario))
    conn.commit()
    conn.close()

    main_window.mostrar_calif_tecnicas= bool(activo)


# -----------------------------------------
# permisos por rol, versión corta
# -----------------------------------------
def puede_editar(main_window):

    rol= getattr(main_window, "rol_actual", None)

    if rol is None:
        return True

    return rol in ("Administrador", "Director", "Coordinador", "Profesor")


def es_admin(main_window):

    rol= getattr(main_window, "rol_actual", None)

    return rol is None or rol in ("Administrador", "Director")


def es_profesor_restringido(main_window):

    return getattr(main_window, "rol_actual", None) == "Profesor"


# -----------------------------------------
# un Profesor solo ve lo suyo
#estas cuatro funciones devuelven None cuando no hay restricción, o sea "ve todo".
# -----------------------------------------
def obtener_profesor_id(main_window):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return None

    conn= _conexion()
    c= conn.cursor()
    c.execute("SELECT id FROM profesores WHERE usuario_id=?", (id_usuario,))
    fila= c.fetchone()
    conn.close()

    return fila["id"] if fila else None


#secciones donde el Profesor es guía, donde imparte alguna materia o donde quedó como co-docente.
def obtener_secciones_permitidas(main_window):

    if not es_profesor_restringido(main_window):
        return None

    profesor_id= obtener_profesor_id(main_window)

    if profesor_id is None:
        return set()

    conn= _conexion()
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


#materias que da el Profesor, sea titular o co-docente (Auxiliar, Suplente...).
def obtener_materias_permitidas(main_window):

    if not es_profesor_restringido(main_window):
        return None

    profesor_id= obtener_profesor_id(main_window)

    if profesor_id is None:
        return set()

    conn= _conexion()
    c= conn.cursor()

    c.execute("SELECT id FROM materias WHERE profesor_id=?", (profesor_id,))
    ids= {fila["id"] for fila in c.fetchall()}

    c.execute("SELECT DISTINCT materia_id as id FROM materia_profesores WHERE profesor_id=?", (profesor_id,))
    ids.update(fila["id"] for fila in c.fetchall() if fila["id"] is not None)

    conn.close()

    return ids


# -----------------------------------------
# materiales
#acá el permiso no va por rol sino por usuario y categoría, en permisos_materiales_usuario.
# -----------------------------------------
def tiene_acceso_total_materiales(main_window):

    return tiene_acceso_gerencial(main_window)


#categorías de material que puede ver el usuario, o None si las ve todas. Un usuario que no es
#gerencial y no tiene ninguna fila asignada recibe un set() vacío: todavía no tiene acceso a nada.
def categorias_material_permitidas(main_window):

    if tiene_acceso_total_materiales(main_window):
        return None

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None:
        return None if getattr(main_window, "rol_actual", None) is None else set()

    conn= _conexion()
    c= conn.cursor()
    c.execute("SELECT categoria_id FROM permisos_materiales_usuario WHERE usuario_id=?", (id_usuario,))
    ids= {fila["categoria_id"] for fila in c.fetchall()}
    conn.close()

    return ids


#True si además de verla puede crear, editar y borrar materiales de esa categoría. La columna
#puede_editar es la que permite dar acceso de solo consulta, por ejemplo para que un Profesor vea
#el inventario de un taller sin poder tocarlo.
def puede_editar_categoria_material(main_window, categoria_id):

    if tiene_acceso_total_materiales(main_window):
        return True

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is None or categoria_id is None:
        return False

    conn= _conexion()
    c= conn.cursor()
    c.execute("SELECT puede_editar FROM permisos_materiales_usuario WHERE usuario_id=? AND categoria_id=?",
              (id_usuario, categoria_id))
    fila= c.fetchone()
    conn.close()

    return bool(fila and fila["puede_editar"])


#categorias_con_edicion es un dict {categoria_id: puede_editar}. Reemplaza todo lo que tenía el
#usuario: si una categoría no viene en el dict, se le quita el acceso. Es más predecible que ir
#acumulando altas sueltas con el tiempo.
def guardar_permisos_materiales_usuario(usuario_id, categorias_con_edicion):

    conn= _conexion()
    c= conn.cursor()

    c.execute("DELETE FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))
    for categoria_id, puede_editar_val in categorias_con_edicion.items():

        c.execute("""INSERT INTO permisos_materiales_usuario (usuario_id, categoria_id, puede_editar)
                     VALUES (?,?,?)""", (usuario_id, categoria_id, 1 if puede_editar_val else 0))

    conn.commit()
    conn.close()


def obtener_permisos_materiales_usuario(usuario_id):

    conn= _conexion()
    c= conn.cursor()
    c.execute("SELECT categoria_id, puede_editar FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))
    filas= c.fetchall()
    conn.close()

    return {fila["categoria_id"]: bool(fila["puede_editar"]) for fila in filas}
