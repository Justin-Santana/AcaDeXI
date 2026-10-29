# -----------------------------------------
# intercambio de datos entre las cuatro ediciones
# -----------------------------------------
#permisos.py resuelve qué puede ver cada edición; esto resuelve otra cosa: cómo un estudiante, una
#calificación o una asistencia capturada en UNA edición viaja y se entiende en OTRA, aunque el
#esquema de base de datos sea distinto (Single Teacher no tiene nada institucional debajo, Full y
#Docentes sí).
#Sirve para: un profesor de Single Teacher que entra a una institución y pasa sus estudiantes y
#calificaciones a Dirección; un profesor de Docentes que exporta sus estudiantes ya combinados con
#sus overrides para respaldarlos o pasárselos a un colega; o exportar las calificaciones de un
#periodo para que otra edición las revise.
#No reemplaza al .acdx del perfil ni a sincronizacion.py: esos mantienen una misma base igual
#entre equipos, esto mueve un pedazo de datos entre instalaciones que no comparten base.
##El paquete es un JSON plano con extensión .acdxpkg, sin cifrar, porque son datos que la propia
#institución maneja entre los suyos:
#{
#"version_formato": 1,
#"tipo": "estudiantes" | "calificaciones" | "asistencia",
#"edicion_origen": "full" | "docentes" | "single_teacher" | "side_stepper",
#"generado": "2026-08-21 10:00:00",
#"registros": [ {...}, ... ]
#}
#El emparejamiento nunca usa el id interno, que es distinto en cada instalación: los estudiantes
#se emparejan por nombre, apellidos y fecha de nacimiento, y las calificaciones por el NOMBRE de
#la materia y del periodo. Si el estudiante ya existe se actualiza; si no, se crea.
import json
from datetime import datetime

VERSION_FORMATO= 1
EXTENSION= ".acdxpkg"

CAMPOS_CANONICOS_ESTUDIANTE= ["nombre", "apellidos", "sexo", "fecha_nacimiento", "documento",
                              "direccion", "telefono", "correo", "tutor", "tutor2", "estado"]


# -----------------------------------------
# conexión según la edición
# -----------------------------------------
#el resto del módulo trabaja siempre sobre listas de dicts, así que este es el único punto que
#sabe de qué esquema vienen y a cuál van.
def _conexion_para_edicion(main_window):

    try:

        from src.nucleo.edicion import edicion_actual
        edicion= edicion_actual()

    except Exception:
        edicion= "full"

    if edicion == "single_teacher":
        from src.nucleo import bd_single_teacher
        return bd_single_teacher.obtener_conexion(main_window), edicion

    from src.nucleo.bd import obtener_conexion

    return obtener_conexion(), edicion


# -----------------------------------------
# estudiantes
# -----------------------------------------
#exporta los estudiantes de una sección, o todos si seccion_id es None. En la edición Docentes se
#exporta la versión ya combinada con los overrides locales, que es la que el docente ve como
#correcta, no el dato institucional crudo.
def exportar_estudiantes(main_window, ruta_archivo, seccion_id=None):

    conn, edicion= _conexion_para_edicion(main_window)
    c= conn.cursor()

    if seccion_id is not None:
        c.execute("SELECT * FROM estudiantes WHERE seccion_id=?", (seccion_id,))
    else:
        c.execute("SELECT * FROM estudiantes")

    filas= [dict(fila) for fila in c.fetchall()]
    conn.close()

    if edicion == "docentes":

        from src.nucleo.datos_locales_docente import listar_overrides_estudiantes, aplicar_override

        overrides= listar_overrides_estudiantes(main_window)
        filas= [aplicar_override(fila, overrides.get(fila["id"])) for fila in filas]

    #f: cada fila (dict) de estudiante; se queda solo con los campos canónicos, vacío si falta alguno.
    registros= [{campo: f.get(campo, "") for campo in CAMPOS_CANONICOS_ESTUDIANTE} for f in filas]
    _escribir_paquete(ruta_archivo, "estudiantes", edicion, registros)

    return len(registros)


#importa un paquete de estudiantes. Si el estudiante ya existe por nombre, apellidos y fecha de
#nacimiento, actualiza sus campos; si no, lo crea y lo deja en la sección de destino cuando se
#indicó una.
def importar_estudiantes(main_window, ruta_archivo, seccion_id_destino=None):

    datos= _leer_paquete(ruta_archivo, tipo_esperado="estudiantes")
    conn, edicion= _conexion_para_edicion(main_window)
    c= conn.cursor()

    creados= 0
    actualizados= 0

    for registro in datos["registros"]:

        c.execute("""SELECT id FROM estudiantes WHERE nombre=? AND apellidos=? AND
                     IFNULL(fecha_nacimiento,'')=IFNULL(?,'')""",
                  (registro.get("nombre", ""), registro.get("apellidos", ""),
                   registro.get("fecha_nacimiento", "")))
        existente= c.fetchone()

        if existente:

            asignaciones= ", ".join(f"{campo}=?" for campo in CAMPOS_CANONICOS_ESTUDIANTE)
            valores= [registro.get(campo, "") for campo in CAMPOS_CANONICOS_ESTUDIANTE]
            c.execute(f"UPDATE estudiantes SET {asignaciones} WHERE id=?", (*valores, existente["id"]))
            actualizados += 1
            continue

        columnas= list(CAMPOS_CANONICOS_ESTUDIANTE)
        valores= [registro.get(campo, "") for campo in columnas]

        if seccion_id_destino is not None:
            columnas.append("seccion_id")
            valores.append(seccion_id_destino)

        marcadores= ", ".join("?" for _ in columnas)
        c.execute(f"INSERT INTO estudiantes ({', '.join(columnas)}) VALUES ({marcadores})", valores)
        creados += 1

    conn.commit()
    conn.close()

    return {"creados": creados, "actualizados": actualizados}


# -----------------------------------------
# calificaciones
# -----------------------------------------
#acá el destino siempre se pide explícito: mezclar notas de una materia con otra por nombre sería
#demasiado arriesgado para hacerlo solo.
def exportar_calificaciones(main_window, ruta_archivo, materia_id, periodo_id=None):

    conn, edicion= _conexion_para_edicion(main_window)
    c= conn.cursor()

    c.execute("SELECT nombre FROM materias WHERE id=?", (materia_id,))
    fila_materia= c.fetchone()
    nombre_materia= fila_materia["nombre"] if fila_materia else ""

    parametros= [materia_id]
    filtro_periodo= ""
    nombre_periodo= ""

    if periodo_id is not None:

        c.execute("SELECT nombre FROM periodos WHERE id=?", (periodo_id,))
        fila_periodo= c.fetchone()
        nombre_periodo= fila_periodo["nombre"] if fila_periodo else ""
        filtro_periodo= " AND calificaciones.periodo_id=?"
        parametros.append(periodo_id)

    c.execute(f"""SELECT estudiantes.nombre as est_nombre, estudiantes.apellidos as est_apellidos,
                  estudiantes.fecha_nacimiento as est_fecha_nacimiento,
                  calificaciones.categoria, calificaciones.descripcion,
                  calificaciones.valor, calificaciones.peso
                  FROM calificaciones
                  JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                  WHERE calificaciones.materia_id=?{filtro_periodo}""", parametros)
    filas= c.fetchall()
    conn.close()

    registros= [{
        "estudiante_nombre": fila["est_nombre"], "estudiante_apellidos": fila["est_apellidos"],
        "estudiante_fecha_nacimiento": fila["est_fecha_nacimiento"],
        "materia_nombre": nombre_materia, "periodo_nombre": nombre_periodo,
        "categoria": fila["categoria"], "descripcion": fila["descripcion"],
        "valor": fila["valor"], "peso": fila["peso"],
    } for fila in filas]

    _escribir_paquete(ruta_archivo, "calificaciones", edicion, registros)

    return len(registros)


#solo importa la nota si el estudiante ya existe en el destino. Los que falten se devuelven en una
#lista para que quien importa los cargue primero con importar_estudiantes.
def importar_calificaciones(main_window, ruta_archivo, materia_id_destino, periodo_id_destino):

    datos= _leer_paquete(ruta_archivo, tipo_esperado="calificaciones")
    conn, edicion= _conexion_para_edicion(main_window)
    c= conn.cursor()

    importadas= 0
    faltantes= []

    for registro in datos["registros"]:

        c.execute("""SELECT id FROM estudiantes WHERE nombre=? AND apellidos=? AND
                     IFNULL(fecha_nacimiento,'')=IFNULL(?,'')""",
                  (registro.get("estudiante_nombre", ""), registro.get("estudiante_apellidos", ""),
                   registro.get("estudiante_fecha_nacimiento", "")))
        fila_estudiante= c.fetchone()

        if not fila_estudiante:
            nombre_completo= f"{registro.get('estudiante_nombre', '')} {registro.get('estudiante_apellidos', '')}"
            faltantes.append(nombre_completo.strip())
            continue

        c.execute("""INSERT INTO calificaciones
                     (estudiante_id, materia_id, periodo_id, categoria, descripcion, valor, peso)
                     VALUES (?,?,?,?,?,?,?)""",
                  (fila_estudiante["id"], materia_id_destino, periodo_id_destino,
                   registro.get("categoria", ""), registro.get("descripcion", ""),
                   registro.get("valor"), registro.get("peso", 0)))
        importadas += 1

    conn.commit()
    conn.close()

    return {"importadas": importadas, "estudiantes_faltantes": faltantes}


# -----------------------------------------
# leer y escribir el paquete
# -----------------------------------------
def _escribir_paquete(ruta_archivo, tipo, edicion, registros):

    paquete= {
        "version_formato": VERSION_FORMATO,
        "tipo": tipo,
        "edicion_origen": edicion,
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "registros": registros,
    }

    with open(ruta_archivo, "w", encoding="utf-8") as archivo:
        json.dump(paquete, archivo, ensure_ascii=False, indent=2)


#se niega a abrir un paquete de otro tipo o de una versión más nueva, con un mensaje que se pueda
#entender sin saber nada del formato.
def _leer_paquete(ruta_archivo, tipo_esperado):

    with open(ruta_archivo, "r", encoding="utf-8") as archivo:
        datos= json.load(archivo)

    if datos.get("tipo") != tipo_esperado:
        raise ValueError(
            f"Este archivo es un paquete de '{datos.get('tipo', 'desconocido')}', "
            f"no de '{tipo_esperado}'. Elige el archivo correcto.")

    if datos.get("version_formato", 0) > VERSION_FORMATO:
        raise ValueError(
            "Este paquete se generó con una versión más nueva de AcaDeXI que no "
            "reconoce este campo de intercambio. Actualiza la app antes de importarlo.")

    return datos
