# ============================================================
# RBAC - Control de Accesos Basado en Roles
# ============================================================
ROLES = ["Administrador", "Director", "Coordinador", "Profesor", "Administrativo"]

# ============================================================
# TECHO DE LO POSIBLE (motor de permisos, Pieza 2 del prompt de
# arquitectura de las 4 ediciones)
# ============================================================
PERMISOS_TECHO = {
    "Administrador": ["Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
                       "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
                       "Banco de Tareas", "Horario", "Calendario", "Observaciones", "Reportes",
                       "Sincronización", "Configuración"],
    "Director": ["Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
                 "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
                 "Banco de Tareas", "Horario", "Calendario", "Observaciones", "Reportes",
                 "Sincronización", "Configuración"],
    "Coordinador": ["Dashboard", "Estudiantes", "Profesores", "Personal", "Materias", "Asistencia",
                    "Calificaciones", "Politécnico", "Calificaciones Técnicas", "Universidad",
                    "Banco de Tareas", "Horario", "Calendario", "Observaciones", "Reportes",
                    "Sincronización"],
    "Profesor": ["Dashboard", "Mis Materias", "Mis Estudiantes", "Asistencia", "Calificaciones",
                 "Calificaciones Técnicas", "Banco de Tareas", "Horario", "Calendario", "Reportes",
                 "Observaciones", "Copias de Seguridad", "Sincronización", "Configuración"],
    "Administrativo": ["Dashboard", "Estudiantes", "Personal", "Reportes", "Configuración", "Materiales"],
}
ACCESO_MODULOS = PERMISOS_TECHO  # alias retrocompatible

# "Materiales" también se ofrece a los roles gerenciales y a Profesor (para
# que puedan, por ejemplo, gestionar el material de su propia aula/taller),
# sumado aparte para no repetir la lista completa de PERMISOS_TECHO arriba.
for _rol_con_materiales in ("Administrador", "Director", "Coordinador", "Profesor"):
    if "Materiales" not in PERMISOS_TECHO[_rol_con_materiales]:
        PERMISOS_TECHO[_rol_con_materiales].append("Materiales")

MODULOS_EXISTENTES = sorted({modulo for lista in PERMISOS_TECHO.values() for modulo in lista})

# ============================================================
# MÓDULOS EXCLUSIVOS DE SIDE STEPPER (Pieza 2) — existen en la app pero NO
# forman parte del "techo" de ningún rol fijo (Administrador/Director/
# Coordinador/Profesor/Administrativo): solo se pueden otorgar a un rol
# PERSONALIZADO configurado desde Side Stepper (ver
# side_stepper_config.py y guardar_permisos_side_stepper más abajo). Con
# esto, "Psicología" nunca aparece como opción para un rol fijo en
# ninguna de las otras 3 ediciones (Full/Docentes/Single Teacher) ni
# siquiera dentro de Side Stepper para un rol fijo -solo un cargo
# personalizado (típicamente llamado "Psicólogo/a" por la institución,
# pero el nombre es libre) puede recibirlo.
MODULOS_EXTRA_SIDE_STEPPER = ["Psicología"]

# Roles con permiso de escritura (crear/editar/eliminar) por módulo administrativo
ROLES_GERENCIALES = {"Administrador", "Director", "Coordinador"}


def tiene_acceso_gerencial(main_window):
    rol = getattr(main_window, "rol_actual", None)
    if rol is None:
        return True  # login desactivado -> acceso total
    return rol in ROLES_GERENCIALES


def _edicion_actual_segura():
    try:
        from src.nucleo.edicion import edicion_actual
        return edicion_actual()
    except Exception:
        return "full"


def _psicologia_habilitada_para_admin():
    """Lee configuracion.psicologia_habilitada_admin (ver
    configuracion.py ▸ pestaña "Usuarios y Roles", tarjeta "Módulo de
    Psicología", visible solo para el rol Administrador). Se consulta en
    caliente (sin caché) porque es un ajuste que se espera cambie poco y
    su lectura es barata -una sola fila de la tabla `configuracion`-."""
    try:
        from src.nucleo.bd import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT psicologia_habilitada_admin FROM configuracion WHERE id=1")
        f = c.fetchone()
        conn.close()
        return bool(f and f["psicologia_habilitada_admin"])
    except Exception:
        return False


def modulo_visible(rol, nombre_modulo, edicion=None):
    if rol is None:
        return True
    if nombre_modulo == "Dashboard":
        return True
    if edicion is None:
        edicion = _edicion_actual_segura()
    if nombre_modulo in MODULOS_EXTRA_SIDE_STEPPER:
        # Módulos exclusivos de Side Stepper (ver MODULOS_EXTRA_SIDE_STEPPER):
        # en cualquier otra edición no existen para nadie -ni siquiera para
        # un rol gerencial-, y dentro de Side Stepper los ve un rol
        # gerencial (supervisión institucional) o quien tenga el módulo
        # concedido en su configuración de permisos.
        #
        # EXCEPCIÓN para "Psicología": el rol Administrador (y solo ese,
        # ni Director ni Coordinador) puede recibirlo en CUALQUIER
        # edición si activó el interruptor de Configuración ▸ Usuarios y
        # Roles -pensado para el Administrador que también ejerce de
        # psicólogo/a y no necesita crear un cargo de Side Stepper para
        # dárselo a sí mismo.
        if nombre_modulo == "Psicología" and rol == "Administrador" and _psicologia_habilitada_para_admin():
            return True
        if edicion != "side_stepper":
            return False
        return rol in ROLES_GERENCIALES or nombre_modulo in obtener_permisos_side_stepper(rol)
    if edicion == "side_stepper":
        return nombre_modulo in obtener_permisos_side_stepper(rol)
    return nombre_modulo in PERMISOS_TECHO.get(rol, [])


# ============================================================
# CONFIGURACIÓN REAL OTORGADA — SIDE STEPPER (Pieza 2)
# ============================================================
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
    from src.nucleo.bd import get_connection
    conn = get_connection()
    _preparar_tabla_permisos_side_stepper(conn)
    c = conn.cursor()
    c.execute("SELECT modulos FROM permisos_side_stepper WHERE rol=?", (rol,))
    f = c.fetchone()
    conn.close()
    if not f:
        return []
    try:
        return json.loads(f["modulos"])
    except (TypeError, ValueError):
        return []


def guardar_permisos_side_stepper(rol, modulos):
    """`rol` puede ser uno de los 5 fijos (techo=PERMISOS_TECHO[rol]) o
    PERSONALIZADO (cualquier texto no listado en ROLES; techo=
    MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER, para cubrir un cargo
    que ninguno de los 5 roles fijos describe -incluyendo módulos
    exclusivos de Side Stepper como "Psicología", que un rol FIJO nunca
    puede recibir aunque se edite aquí mismo: el fijo sigue limitado a su
    propio PERMISOS_TECHO)."""
    import json
    from datetime import datetime
    from src.nucleo.bd import get_connection
    es_personalizado = rol not in ROLES
    techo = (MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER) if es_personalizado else PERMISOS_TECHO.get(rol, [])
    modulos_validos = [m for m in modulos if m in techo]
    conn = get_connection()
    _preparar_tabla_permisos_side_stepper(conn)
    c = conn.cursor()
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
    from src.nucleo.bd import get_connection
    conn = get_connection()
    _preparar_tabla_permisos_side_stepper(conn)
    c = conn.cursor()
    c.execute("SELECT rol, modulos, personalizado, actualizado FROM permisos_side_stepper ORDER BY rol")
    filas = c.fetchall()
    conn.close()
    resultado = []
    for f in filas:
        try:
            modulos = json.loads(f["modulos"])
        except (TypeError, ValueError):
            modulos = []
        resultado.append({"rol": f["rol"], "modulos": modulos,
                          "personalizado": bool(f["personalizado"]), "actualizado": f["actualizado"]})
    return resultado


def eliminar_rol_side_stepper(rol):
    from src.nucleo.bd import get_connection
    conn = get_connection()
    _preparar_tabla_permisos_side_stepper(conn)
    c = conn.cursor()
    c.execute("DELETE FROM permisos_side_stepper WHERE rol=?", (rol,))
    conn.commit()
    conn.close()


def techo_para_rol_side_stepper(rol):
    if rol not in ROLES:
        return MODULOS_EXISTENTES + MODULOS_EXTRA_SIDE_STEPPER
    return PERMISOS_TECHO.get(rol, MODULOS_EXISTENTES)


def roles_side_stepper_con_psicologia():
    """Nombres de los cargos personalizados de Side Stepper que tienen
    otorgado el módulo "Psicología" ahora mismo -usado por psicologia.py
    para saber a qué usuarios.rol darles acceso, sin tener que hardcodear
    el nombre "Psicólogo/a" (la institución puede llamarlo como quiera)."""
    return [info["rol"] for info in listar_roles_side_stepper_configurados()
            if "Psicología" in info["modulos"]]


def es_psicologo(main_window):
    """True si el usuario logueado tiene un rol de Side Stepper (cargo
    personalizado) al que se le otorgó el módulo "Psicología"."""
    rol = getattr(main_window, "rol_actual", None)
    if rol is None or rol in ROLES:
        return False
    return rol in roles_side_stepper_con_psicologia()


def puede_ver_psicologia(main_window):
    """Acceso real al módulo de Psicología: el/la psicólogo/a que lo tiene
    otorgado, cualquier rol gerencial (supervisión institucional), o el
    rol Administrador si activó el interruptor de Configuración ▸
    Usuarios y Roles (ver _psicologia_habilitada_para_admin). Un Profesor
    normal, aunque vea Observaciones, NUNCA ve Psicología -son tablas
    separadas justamente por eso, ver bd.inicializar_bd."""
    if tiene_acceso_gerencial(main_window):
        return True
    rol = getattr(main_window, "rol_actual", None)
    if rol == "Administrador" and _psicologia_habilitada_para_admin():
        return True
    return es_psicologo(main_window)


def importar_paquete_permisos_side_stepper(ruta_archivo):
    import json
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        datos = json.load(f)
    roles_importados = []
    for info_rol in datos.get("roles", []):
        guardados = guardar_permisos_side_stepper(info_rol["rol"], info_rol.get("modulos", []))
        roles_importados.append({"rol": info_rol["rol"], "modulos": guardados})
    return roles_importados


# ============================================================
# PREFERENCIA PERSONAL: "Calificaciones Técnicas" para el rol Profesor
# ============================================================
# Ver Configuración ▸ Mi Cuenta. Es una decisión manual de cada docente
# (checkbox), NO se calcula a partir de sus materias asignadas: un Profesor
# puede activarla aunque no imparta ningún módulo técnico, o desactivarla
# aunque sí lo haga. Los roles gerenciales (Director/Coordinador/
# Administrador) NUNCA pasan por aquí: para ellos el módulo se rige solo
# por el tipo de institución, sin importar esta preferencia.
def obtener_preferencia_calif_tecnicas(main_window):
    """True si este Profesor activó ver "Calificaciones Técnicas" en su menú."""
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return False
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT mostrar_calif_tecnicas FROM usuarios WHERE id=?", (id_usuario,))
    f = c.fetchone()
    conn.close()
    return bool(f["mostrar_calif_tecnicas"]) if f else False


def guardar_preferencia_calif_tecnicas(main_window, activo):
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET mostrar_calif_tecnicas=? WHERE id=?", (1 if activo else 0, id_usuario))
    conn.commit()
    conn.close()
    main_window.mostrar_calif_tecnicas = bool(activo)


def puede_editar(main_window):
    rol = getattr(main_window, "rol_actual", None)
    if rol is None:
        return True
    return rol in ("Administrador", "Director", "Coordinador", "Profesor")


def es_admin(main_window):
    rol = getattr(main_window, "rol_actual", None)
    return rol is None or rol in ("Administrador", "Director")


# ============================================================
# RBAC REAL POR FILA (para el rol "Profesor")
# ============================================================
def es_profesor_restringido(main_window):
    """True si el usuario logueado es un Profesor y debe ver solo sus datos."""
    return getattr(main_window, "rol_actual", None) == "Profesor"


def obtener_profesor_id(main_window):
    """Devuelve el id de profesores.id vinculado al usuario logueado, o None."""
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return None
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM profesores WHERE usuario_id=?", (id_usuario,))
    f = c.fetchone()
    conn.close()
    return f["id"] if f else None


def obtener_secciones_permitidas(main_window):
    """Para un Profesor: IDs de secciones donde es guía, donde imparte alguna materia
    (vía horarios) o donde fue asignado como co-docente (materia_profesores).
    Devuelve None si no aplica restricción (ver todas)."""
    if not es_profesor_restringido(main_window):
        return None
    profesor_id = obtener_profesor_id(main_window)
    if profesor_id is None:
        return set()
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    ids = set()
    c.execute("SELECT id FROM secciones WHERE profesor_guia_id=?", (profesor_id,))
    ids.update(f["id"] for f in c.fetchall())
    c.execute("""SELECT DISTINCT horarios.seccion_id as id FROM horarios
                 LEFT JOIN materias ON horarios.materia_id = materias.id
                 WHERE materias.profesor_id=?""", (profesor_id,))
    ids.update(f["id"] for f in c.fetchall() if f["id"] is not None)
    c.execute("""SELECT DISTINCT seccion_id as id FROM materia_profesores
                 WHERE profesor_id=? AND seccion_id IS NOT NULL""", (profesor_id,))
    ids.update(f["id"] for f in c.fetchall())
    conn.close()
    return ids


def obtener_materias_permitidas(main_window):
    """Para un Profesor: IDs de materias.id que él imparte, ya sea como titular
    (materias.profesor_id) o como co-docente asignado en materia_profesores
    (p. ej. Auxiliar, Suplente). None si no aplica restricción."""
    if not es_profesor_restringido(main_window):
        return None
    profesor_id = obtener_profesor_id(main_window)
    if profesor_id is None:
        return set()
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM materias WHERE profesor_id=?", (profesor_id,))
    ids = {f["id"] for f in c.fetchall()}
    c.execute("SELECT DISTINCT materia_id as id FROM materia_profesores WHERE profesor_id=?", (profesor_id,))
    ids.update(f["id"] for f in c.fetchall() if f["id"] is not None)
    conn.close()
    return ids

# ============================================================
# RBAC GRANULAR — MÓDULO MATERIALES (por usuario+categoría, no por rol)
# ============================================================
def tiene_acceso_total_materiales(main_window):
    """Los roles gerenciales siempre ven y administran TODAS las
    categorías de materiales, sin pasar por permisos_materiales_usuario."""
    return tiene_acceso_gerencial(main_window)


def categorias_material_permitidas(main_window):
    """Devuelve el set de categorias_material.id a los que el usuario
    logueado puede acceder, o None si tiene acceso TOTAL (rol gerencial,
    o login desactivado). Un usuario no-gerencial sin ninguna fila en
    permisos_materiales_usuario obtiene un set() vacío -sin acceso a
    ninguna categoría todavía-, igual que el resto del RBAC por fila de
    la app (ver obtener_secciones_permitidas)."""
    if tiene_acceso_total_materiales(main_window):
        return None
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return None if getattr(main_window, "rol_actual", None) is None else set()
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT categoria_id FROM permisos_materiales_usuario WHERE usuario_id=?", (id_usuario,))
    ids = {f["categoria_id"] for f in c.fetchall()}
    conn.close()
    return ids


def puede_editar_categoria_material(main_window, categoria_id):
    """True si el usuario puede crear/editar/eliminar materiales de esa
    categoría (no solo verlos). Los gerenciales siempre pueden; el resto
    depende de la columna `puede_editar` de su fila en
    permisos_materiales_usuario (permite otorgar acceso de SOLO CONSULTA
    a una categoría, por ejemplo para que un Profesor vea el inventario
    de un taller sin poder modificarlo)."""
    if tiene_acceso_total_materiales(main_window):
        return True
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None or categoria_id is None:
        return False
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puede_editar FROM permisos_materiales_usuario WHERE usuario_id=? AND categoria_id=?",
              (id_usuario, categoria_id))
    f = c.fetchone()
    conn.close()
    return bool(f and f["puede_editar"])


def guardar_permisos_materiales_usuario(usuario_id, categorias_con_edicion):
    """`categorias_con_edicion`: dict {categoria_id: puede_editar(bool)}.
    Reemplaza POR COMPLETO las categorías asignadas a `usuario_id` (si una
    categoría existente no viene en el dict, se le retira el acceso) -es
    más predecible para quien administra permisos que ir acumulando altas
    sueltas con el tiempo."""
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))
    for categoria_id, puede_editar_val in categorias_con_edicion.items():
        c.execute("""INSERT INTO permisos_materiales_usuario (usuario_id, categoria_id, puede_editar)
                     VALUES (?,?,?)""", (usuario_id, categoria_id, 1 if puede_editar_val else 0))
    conn.commit()
    conn.close()


def obtener_permisos_materiales_usuario(usuario_id):
    """Devuelve {categoria_id: puede_editar(bool)} de un usuario concreto,
    para precargar el diálogo de asignación de permisos."""
    from src.nucleo.bd import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT categoria_id, puede_editar FROM permisos_materiales_usuario WHERE usuario_id=?", (usuario_id,))
    filas = c.fetchall()
    conn.close()
    return {f["categoria_id"]: bool(f["puede_editar"]) for f in filas}
