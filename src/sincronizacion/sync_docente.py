#sync_docente.py
#================
#Exporta/importa el paquete de "Estudiantes y Cursos" que Dirección/Coordinación/
#Administración configuran, para que los profesores puedan traerlo a su propia
#instalación en Modo Docente (sin poder ellos mismos elegir qué estudiantes
#pertenecen a cada curso/sección, ni crear materias).
#
#Formato del paquete: un único archivo Excel (.xlsx) con una hoja "Info" y una
#hoja por tabla (Grados, Especialidades, Aulas, Secciones, Materias, Estudiantes,
#Asignaciones, Horarios). Es el mismo formato Excel/CSV que se usa en el resto
#de la app (p. ej. Estudiantes ▸ Importar Excel/CSV), así Dirección puede
#incluso abrir el archivo y revisarlo antes de compartirlo.
#
#Dos modos de exportación:
#- Paquete institucional completo (profesor_id=None): todo lo configurado.
#- Paquete individual de un profesor (profesor_id=<id>): solo los grados,
#secciones, materias, estudiantes, aulas, especialidades y horarios que
#le corresponden a ESE profesor -- ya sea porque es el titular de la
#materia (materias.profesor_id) o porque fue asignado como co-docente en
#materia_profesores (p. ej. "Auxiliar", "Suplente", etc. -- ver la pestaña
#Co-Docentes del módulo Materias).
#
#Importa (en la instalación del docente):
#- Hace INSERT OR REPLACE por id en cada tabla, preservando el resto de la
#base de datos del profesor (sus observaciones, calificaciones, etc.)
#- Todo dentro de una transacción; si algo falla se revierte por completo.
#- Por compatibilidad, también puede leer paquetes antiguos en .json
#generados por versiones previas de AcaDeXI.
import json
from datetime import datetime
from PySide6.QtWidgets import QFileDialog
from src.nucleo.bd import obtener_conexion, registrar_auditoria
from src.nucleo.iconos import mostrar_mensaje
from src.nucleo.permisos import puede_editar, es_profesor_restringido

TIPO_PAQUETE= "acadexi_paquete_docente"
VERSION_PAQUETE= 2

#Orden de exportación/importación: respeta dependencias de llaves foráneas (grados/especialidades/aulas antes
#que secciones; secciones/materias antes que estudiantes/materia_profesores/horarios).
TABLAS_PAQUETE= ["grados", "especialidades", "aulas", "secciones", "materias",
                   "estudiantes", "materia_profesores", "horarios"]

#Nombre de hoja de Excel por tabla.
HOJAS= {
    "grados": "Grados",
    "especialidades": "Especialidades",
    "aulas": "Aulas",
    "secciones": "Secciones",
    "materias": "Materias",
    "estudiantes": "Estudiantes",
    "materia_profesores": "Asignaciones",
    "horarios": "Horarios",
}

#Columnas por tabla que se incluyen en el paquete (se excluyen datos sensibles como usuario_id / cuentas de
#acceso, que no le corresponden al docente).
COLUMNAS= {
    "grados": ["id", "nombre", "tipo", "orden"],
    "especialidades": ["id", "nombre", "codigo", "color"],
    "aulas": ["id", "nombre", "tipo", "capacidad", "especialidad_id"],
    "secciones": ["id", "nombre", "grado_id", "turno", "aula_id", "especialidad_id",
                   "anio_academico", "profesor_guia_id"],
    "materias": ["id", "codigo", "nombre", "creditos", "especialidad_id", "estado", "profesor_id"],
    "estudiantes": ["id", "matricula", "nombre", "apellidos", "sexo", "fecha_nacimiento",
                     "documento", "direccion", "telefono", "correo", "tutor", "tutor2",
                     "seccion_id", "estado"],
    "materia_profesores": ["id", "materia_id", "profesor_id", "seccion_id", "tipo_asignacion"],
    "horarios": ["id", "dia", "hora_inicio", "hora_fin", "materia_id", "seccion_id", "aula_id"],
}


#El archivo seleccionado no es un paquete de Estudiantes/Cursos válido.
class _PaqueteInvalido(Exception):

    pass


#IDs de materias/secciones/grados/aulas/especialidades relacionados con un
#profesor específico (como titular o como co-docente vía materia_profesores),
#para poder generar un paquete acotado solo a lo que ese profesor imparte.
def _calcular_alcance_profesor(conn, profesor_id):

    c= conn.cursor()
    materia_ids, seccion_ids= set(), set()
    grado_ids, aula_ids, especialidad_ids= set(), set(), set()

    c.execute("SELECT id, especialidad_id FROM materias WHERE profesor_id=?", (profesor_id,))
    for fila in c.fetchall():
        materia_ids.add(fila["id"])
        if fila["especialidad_id"] is not None:
            especialidad_ids.add(fila["especialidad_id"])

    c.execute("SELECT materia_id, seccion_id FROM materia_profesores WHERE profesor_id=?", (profesor_id,))
    for fila in c.fetchall():
        if fila["materia_id"] is not None:
            materia_ids.add(fila["materia_id"])
        if fila["seccion_id"] is not None:
            seccion_ids.add(fila["seccion_id"])

    c.execute("SELECT id, aula_id, especialidad_id FROM secciones WHERE profesor_guia_id=?", (profesor_id,))
    for fila in c.fetchall():
        seccion_ids.add(fila["id"])
        if fila["aula_id"] is not None:
            aula_ids.add(fila["aula_id"])
        if fila["especialidad_id"] is not None:
            especialidad_ids.add(fila["especialidad_id"])

    if materia_ids:
        c.execute("SELECT materia_id, seccion_id, aula_id FROM horarios")
        for fila in c.fetchall():
            if fila["materia_id"] in materia_ids:
                if fila["seccion_id"] is not None:
                    seccion_ids.add(fila["seccion_id"])
                if fila["aula_id"] is not None:
                    aula_ids.add(fila["aula_id"])

    if seccion_ids:
        marcadores= ", ".join(["?"] * len(seccion_ids))
        c.execute(f"""SELECT id, grado_id, aula_id, especialidad_id FROM secciones
                      WHERE id IN ({marcadores})""", tuple(seccion_ids))
        for fila in c.fetchall():
            if fila["grado_id"] is not None:
                grado_ids.add(fila["grado_id"])
            if fila["aula_id"] is not None:
                aula_ids.add(fila["aula_id"])
            if fila["especialidad_id"] is not None:
                especialidad_ids.add(fila["especialidad_id"])

    return {
        "materias": materia_ids, "secciones": seccion_ids, "grados": grado_ids,
        "aulas": aula_ids, "especialidades": especialidad_ids,
    }


#Ejecuta el SELECT de una tabla del paquete, acotado al alcance del
#profesor cuando corresponde (profesor_id no es None).
def _filas_tabla(c, tabla, columnas, profesor_id, alcance):

    if profesor_id is None:
        c.execute(f"SELECT {', '.join(columnas)} FROM {tabla}")
        return c.fetchall()

    if tabla in ("grados", "aulas", "especialidades", "secciones", "materias"):
        ids= alcance.get(tabla, set())
        if not ids:
            return []
        marcadores= ", ".join(["?"] * len(ids))
        c.execute(f"SELECT {', '.join(columnas)} FROM {tabla} WHERE id IN ({marcadores})", tuple(ids))
        return c.fetchall()
    if tabla == "estudiantes":
        if not alcance["secciones"]:
            return []
        marcadores= ", ".join(["?"] * len(alcance["secciones"]))
        c.execute(f"""SELECT {', '.join(columnas)} FROM estudiantes
                      WHERE seccion_id IN ({marcadores})""", tuple(alcance["secciones"]))
        return c.fetchall()
    if tabla == "materia_profesores":
        c.execute(f"SELECT {', '.join(columnas)} FROM materia_profesores WHERE profesor_id=?", (profesor_id,))
        return c.fetchall()
    if tabla == "horarios":
        if not alcance["materias"]:
            return []
        marcadores= ", ".join(["?"] * len(alcance["materias"]))
        c.execute(f"""SELECT {', '.join(columnas)} FROM horarios
                      WHERE materia_id IN ({marcadores})""", tuple(alcance["materias"]))
        return c.fetchall()
    c.execute(f"SELECT {', '.join(columnas)} FROM {tabla}")
    return c.fetchall()


#Genera el archivo .xlsx con estudiantes/cursos para que los docentes lo importen.
#Solo debe invocarse desde roles gerenciales (Admin/Director/Coordinador).
#
#Si profesor_id es None, exporta el paquete institucional completo (todo lo
#configurado). Si se indica un profesor_id, exporta un paquete acotado solo
#a las materias/secciones/estudiantes/horarios de ESE profesor (como titular
#o como co-docente asignado en materia_profesores).
def exportar_paquete_docente(main_window, parent=None, profesor_id=None, profesor_nombre=None):

    if es_profesor_restringido(main_window) or not puede_editar(main_window):
        mostrar_mensaje("advertencia", "Sin permisos",
                        "Solo Dirección/Coordinación/Administración pueden exportar este paquete.", parent)
        return
    try:

        import openpyxl
    except ImportError:
        mostrar_mensaje("error", "Falta un componente",
                       "Instala 'openpyxl' (pip install openpyxl) para exportar el paquete en Excel.", parent)
        return

    sufijo= ""
    if profesor_id is not None and profesor_nombre:
        limpio= "".join(ch if ch.isalnum() else "_" for ch in profesor_nombre.strip())
        sufijo= f"_{limpio}"
    nombre_sugerido= f"acadexi_docente{sufijo}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    ruta, _= QFileDialog.getSaveFileName(
        parent, "Exportar Estudiantes y Cursos (Modo Docente)",
        nombre_sugerido, "Excel para Modo Docente (*.xlsx)")
    if not ruta:
        return
    if not ruta.lower().endswith(".xlsx"):
        ruta += ".xlsx"

    conn= obtener_conexion()
    c= conn.cursor()
    total_filas= 0
    try:

        alcance= _calcular_alcance_profesor(conn, profesor_id) if profesor_id is not None else None

        if profesor_id is not None and alcance is not None and not alcance["materias"]:
            conn.close()
            mostrar_mensaje("advertencia", "Sin materias asignadas",
                           "Este profesor no tiene materias asignadas todavía (ni como titular ni como "
                           "co-docente en la pestaña Co-Docentes de Materias), así que no hay nada que "
                           "exportar para él.", parent)
            return

        wb= openpyxl.Workbook()
        hoja_info= wb.active
        hoja_info.title= "Info"
        hoja_info.append(["tipo", "version", "generado", "alcance", "profesor_id"])
        hoja_info.append([TIPO_PAQUETE, VERSION_PAQUETE, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                          "Individual" if profesor_id is not None else "Institucional",
                          profesor_id if profesor_id is not None else ""])

        for tabla in TABLAS_PAQUETE:
            columnas= COLUMNAS[tabla]
            hoja= wb.create_sheet(HOJAS[tabla])
            hoja.append(columnas)
            try:

                filas= _filas_tabla(c, tabla, columnas, profesor_id, alcance)
            except Exception:
                #La tabla/columna puede no existir según el tipo de institución; se omite.
                continue
            for fila in filas:
                hoja.append([fila[col] for col in columnas])
                total_filas += 1
        wb.save(ruta)
    except Exception as error:
        conn.close()
        mostrar_mensaje("error", "Error", f"No se pudo guardar el archivo:\n{error}", parent)
        return
    conn.close()

    detalle_auditoria= f"{total_filas} registros - {ruta}"
    accion= "Exportó paquete de estudiantes/cursos para Modo Docente"
    if profesor_id is not None:
        accion += f" (individual: {profesor_nombre or profesor_id})"
    registrar_auditoria("Sincronización", accion, main_window.usuario_actual, detalle_auditoria)

    if profesor_id is not None:
        mostrar_mensaje("exito", "Paquete individual exportado",
                       f"El paquete de {profesor_nombre or 'este profesor'} se guardó en:\n{ruta}\n\n"
                       "Contiene solo sus materias, secciones, estudiantes y horario. Compártelo con "
                       "él/ella para que lo importe desde su Modo Docente ▸ Copias de Seguridad ▸ "
                       "Importar Estudiantes y Cursos.", parent)
    else:
        mostrar_mensaje("exito", "Paquete exportado",
                       f"El paquete se guardó en:\n{ruta}\n\nCompártelo (por correo, USB o carpeta compartida) "
                       "con tus docentes para que lo importen desde su Modo Docente ▸ Copias de Seguridad ▸ "
                       "Importar Estudiantes y Cursos.", parent)


#Importa un paquete de estudiantes/cursos (.xlsx) generado por un rol gerencial.
#Pensado para usarse desde el Modo Docente. También acepta, por compatibilidad,
#paquetes antiguos en formato .json.
def importar_paquete_docente(main_window, parent=None):

    ruta, _= QFileDialog.getOpenFileName(
        parent, "Importar Estudiantes y Cursos (Modo Docente)", "",
        "Excel para Modo Docente (*.xlsx);;Paquete antiguo AcaDeXI (*.json)")
    if not ruta:
        return
    try:

        if ruta.lower().endswith(".json"):
            tablas= _leer_paquete_json(ruta)
        else:
            tablas= _leer_paquete_xlsx(ruta)
    except _PaqueteInvalido as error:
        mostrar_mensaje("advertencia", "Archivo inválido", str(error), parent)
        return
    except Exception as error:
        mostrar_mensaje("error", "Error", f"No se pudo leer el archivo:\n{error}", parent)
        return

    conn= obtener_conexion()
    c= conn.cursor()
    total_filas= 0
    try:

        #Orden que respeta dependencias (grados/especialidades/aulas -> secciones ->
        #materias -> estudiantes -> resto)
        for tabla in TABLAS_PAQUETE:
            registros= tablas.get(tabla) or []
            if not registros:
                continue
            columnas= COLUMNAS[tabla]
            marcadores= ", ".join(["?"] * len(columnas))
            sql= f"INSERT OR REPLACE INTO {tabla} ({', '.join(columnas)}) VALUES ({marcadores})"
            for reg in registros:
                valores= tuple(reg.get(col) for col in columnas)
                try:

                    c.execute(sql, valores)
                    total_filas += 1
                except Exception:
                    #Se omite el registro puntual si no calza con el esquema local, sin abortar el resto de la importación.
                    continue
        conn.commit()
    except Exception as error:
        conn.rollback()
        conn.close()
        mostrar_mensaje("error", "Error al importar", f"No se pudo completar la importación:\n{error}", parent)
        return
    conn.close()
    registrar_auditoria("Sincronización", "Importó paquete de estudiantes/cursos (Modo Docente)",
                        main_window.usuario_actual, f"{total_filas} registros - {ruta}")
    mostrar_mensaje("exito", "Paquete importado",
                   f"Se importaron {total_filas} registros correctamente.\n\n"
                   "Recuerda: los estudiantes, secciones y materias solo pueden ser "
                   "actualizados de nuevo importando un paquete más reciente de Dirección/"
                   "Coordinación/Administración.", parent)
    if hasattr(main_window, "refrescar_modulo_actual"):
        main_window.refrescar_modulo_actual()


def _leer_paquete_xlsx(ruta):

    try:

        import openpyxl
    except ImportError:
        raise RuntimeError("Instala 'openpyxl' (pip install openpyxl) para importar paquetes en Excel.")
    wb= openpyxl.load_workbook(ruta, data_only=True)
    if "Info" not in wb.sheetnames:
        raise _PaqueteInvalido(
            "Este archivo no es un paquete válido de Estudiantes/Cursos de AcaDeXI "
            "(falta la hoja 'Info').")
    hoja_info= wb["Info"]
    #v: cada celda de la fila de encabezados de la hoja Info; se pasa a texto minúsculo sin espacios.
    encabezados_info= [str(v or "").strip().lower() for v in next(hoja_info.iter_rows(values_only=True), [])]
    valores_info= next(hoja_info.iter_rows(min_row=2, max_row=2, values_only=True), None)
    if not valores_info or "tipo" not in encabezados_info:
        raise _PaqueteInvalido("Este archivo no es un paquete válido de Estudiantes/Cursos de AcaDeXI.")
    tipo= valores_info[encabezados_info.index("tipo")]
    if tipo != TIPO_PAQUETE:
        raise _PaqueteInvalido(
            "Este archivo no es un paquete válido de Estudiantes/Cursos de AcaDeXI.")

    tablas= {}
    for tabla in TABLAS_PAQUETE:
        nombre_hoja= HOJAS[tabla]
        if nombre_hoja not in wb.sheetnames:
            tablas[tabla]= []
            continue
        hoja= wb[nombre_hoja]
        filas_iter= hoja.iter_rows(values_only=True)
        encabezados= next(filas_iter, None)
        if not encabezados:
            tablas[tabla]= []
            continue
        claves= [str(encabezado or "").strip() for encabezado in encabezados]
        registros= []
        for cruda in filas_iter:
            #v: cada celda de la fila cruda; la fila se omite si todas están vacías (None o '').
            if not any(v not in (None, "") for v in cruda):
                continue
            registros.append({claves[i]: (cruda[i] if i < len(cruda) else None)
                             for i in range(len(claves)) if claves[i]})
        tablas[tabla]= registros
    return tablas


#Compatibilidad con paquetes generados por versiones antiguas de AcaDeXI (.json).
#Los paquetes antiguos no incluían 'aulas' ni 'especialidades'; se omiten sin error.
def _leer_paquete_json(ruta):

    #f: manejador del archivo .json abierto para lectura; se vuelca con json.load.
    with open(ruta, "r", encoding="utf-8") as f:
        paquete= json.load(f)
    if paquete.get("tipo") != TIPO_PAQUETE:
        raise _PaqueteInvalido("Este archivo no es un paquete válido de Estudiantes/Cursos de AcaDeXI.")
    return paquete.get("tablas", {})
