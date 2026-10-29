#deshacer_rehacer.py — Motor de deshacer y rehacer para cualquier DELETE/UPDATE de la BD.
#
#No hay que avisarle qué tablas se tocan. Al entrar en grabar() guarda una copia de la BD
#en memoria; al salir compara tabla por tabla y se queda con las filas que cambiaron. Así
#entra solo lo que borró el cascade, que es lo que un deshacer a mano siempre olvidaba.
#Deshacer y rehacer son atómicos: si algo choca, la transacción se revierte y no cambia nada.
#Después de aplicar cualquiera de los dos se vuelve a comparar, así un dato hijo añadido
#entre medias no se pierde al volver a deshacer.
#
#Uso (lo normal es hacerlo desde GestorDeshacer, en deshacer_rehacer_ui.py):
#with deshacer_rehacer.grabar("Eliminó el espacio 'Aula 3'") as g:
#...los DELETE/UPDATE de siempre...
#ok, resultado= deshacer_rehacer.deshacer_grabacion(g)
import os
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

from src.nucleo import bd


# -----------------------------------------
# límites y tablas ignoradas
# -----------------------------------------
#Más filas cambiadas que esto y la acción no se puede deshacer (la pila vive en memoria)
MAX_FILAS_CAMBIADAS= 5000

#Una BD más grande que esto no se copia: tardaría demasiado en cada borrado
MAX_BYTES_BD= 200 * 1024 * 1024

#Registros que nunca se deshacen: si se borra un estudiante, la auditoría no debe borrarse con él
TABLAS_IGNORADAS= {"auditoria", "backups", "historial_cambios_calificaciones", "tokens_recuperacion"}


class Grabacion:

    def __init__(self, etiqueta):

        self.etiqueta= etiqueta
        self.cambios= []            #[(tabla, columnas_pk, antes, despues)], antes/despues son dict o None
        self.no_deshacible= False

    @property
    def vacia(self):

        return not self.cambios and not self.no_deshacible


# -----------------------------------------
# copia y comparación
# -----------------------------------------
def _tablas_a_vigilar(conn):

    filas= conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return [fila[0] for fila in filas if fila[0] not in TABLAS_IGNORADAS]


#Las columnas de la clave primaria; si la tabla no tiene, se usa rowid
def _columnas_clave(conn, tabla):

    info= conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()
    claves= [fila[1] for fila in sorted(info, key=lambda fila: fila[5]) if fila[5] > 0]
    if claves:
        return claves
    return ["rowid"]


def _leer_tabla(conn, tabla, columnas_clave):

    cursor= conn.execute(f'SELECT rowid AS rowid, * FROM "{tabla}"')
    nombres= [descripcion[0] for descripcion in cursor.description]
    filas= {}
    for fila in cursor.fetchall():
        registro= dict(zip(nombres, fila))
        clave= tuple(registro[columna] for columna in columnas_clave)
        filas[clave]= registro
    return filas


def _copiar_a_memoria():

    if os.path.getsize(bd.RUTA_BD) > MAX_BYTES_BD:
        return None

    origen= bd.obtener_conexion()
    copia= sqlite3.connect(":memory:")
    origen.backup(copia)
    origen.close()
    return copia


def _comparar(copia_antes, conn_ahora):

    cambios= []
    for tabla in _tablas_a_vigilar(conn_ahora):
        columnas_clave= _columnas_clave(conn_ahora, tabla)
        try:

            antes= _leer_tabla(copia_antes, tabla, columnas_clave)
        except sqlite3.OperationalError:
            continue    #la tabla no existía en la copia
        ahora= _leer_tabla(conn_ahora, tabla, columnas_clave)

        for clave, fila_antes in antes.items():
            fila_ahora= ahora.get(clave)
            if fila_ahora != fila_antes:
                cambios.append((tabla, columnas_clave, fila_antes, fila_ahora))

        for clave, fila_ahora in ahora.items():
            if clave not in antes:
                cambios.append((tabla, columnas_clave, None, fila_ahora))

        if len(cambios) > MAX_FILAS_CAMBIADAS:
            return cambios
    return cambios


# -----------------------------------------
# grabar
# -----------------------------------------
@contextmanager
def grabar(etiqueta="Eliminó un registro"):

    g= Grabacion(etiqueta)
    copia= _copiar_a_memoria()
    if copia is None:
        g.no_deshacible= True
        yield g
        return

    try:

        yield g
        conn= bd.obtener_conexion()
        try:

            g.cambios= _comparar(copia, conn)
        finally:
            conn.close()
    finally:
        copia.close()

    if len(g.cambios) > MAX_FILAS_CAMBIADAS:
        g.cambios= []
        g.no_deshacible= True


# -----------------------------------------
# aplicar al revés
# -----------------------------------------
def _sin_rowid(fila, columnas_clave):

    if columnas_clave == ["rowid"]:
        return dict(fila)
    return {columna: valor for columna, valor in fila.items() if columna != "rowid"}


def _condicion_clave(columnas_clave, fila):

    condicion= " AND ".join(f'"{columna}"=?' for columna in columnas_clave)
    valores= [fila[columna] for columna in columnas_clave]
    return condicion, valores


def _insertar(conn, tabla, columnas_clave, fila):

    datos= _sin_rowid(fila, columnas_clave)
    columnas= ", ".join(f'"{columna}"' for columna in datos)
    marcas= ", ".join("?" for _ in datos)
    conn.execute(f'INSERT INTO "{tabla}" ({columnas}) VALUES ({marcas})', list(datos.values()))


def _borrar(conn, tabla, columnas_clave, fila):

    condicion, valores= _condicion_clave(columnas_clave, fila)
    conn.execute(f'DELETE FROM "{tabla}" WHERE {condicion}', valores)


#Una fila editada se restaura con UPDATE: borrarla e insertarla de nuevo arrastraría a sus hijos por el cascade
def _restaurar(conn, tabla, columnas_clave, antes, despues):

    datos= _sin_rowid(antes, columnas_clave)
    asignaciones= ", ".join(f'"{columna}"=?' for columna in datos)
    condicion, valores_clave= _condicion_clave(columnas_clave, despues)
    conn.execute(f'UPDATE "{tabla}" SET {asignaciones} WHERE {condicion}', list(datos.values()) + valores_clave)


def _revertir(conn, cambios):

    #Primero se quitan las filas que sobran, luego se restauran las editadas y al final se reponen las borradas.
    #Las claves foráneas se revisan al terminar la transacción, así el orden entre tablas no importa.
    for tabla, columnas_clave, antes, despues in cambios:
        if antes is None:
            _borrar(conn, tabla, columnas_clave, despues)

    for tabla, columnas_clave, antes, despues in cambios:
        if antes is not None and despues is not None:
            _restaurar(conn, tabla, columnas_clave, antes, despues)

    for tabla, columnas_clave, antes, despues in cambios:
        if antes is not None and despues is None:
            _insertar(conn, tabla, columnas_clave, antes)


def _aplicar_inverso(g):

    copia= _copiar_a_memoria()
    if copia is None:
        return False, "la base de datos es demasiado grande"

    conn= bd.obtener_conexion()
    try:

        conn.isolation_level= None      #la transacción se maneja a mano
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        _revertir(conn, g.cambios)
        nuevos_cambios= _comparar(copia, conn)
        conn.execute("COMMIT")
    except Exception as error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        return False, str(error)
    finally:
        conn.close()
        copia.close()

    #Lo que acaba de pasar es lo que hay que invertir la próxima vez
    g.cambios= nuevos_cambios
    return True, ""


def _fila_ya_no_existe(g):

    #Una edición cuya fila desapareció no se puede restaurar: sería un éxito falso
    conn= bd.obtener_conexion()
    try:

        for tabla, columnas_clave, antes, despues in g.cambios:
            if antes is not None and despues is not None:
                condicion, valores= _condicion_clave(columnas_clave, despues)
                fila= conn.execute(f'SELECT 1 FROM "{tabla}" WHERE {condicion}', valores).fetchone()
                if fila is None:
                    return True
    finally:
        conn.close()
    return False


def deshacer_grabacion(g):

    if g.vacia:
        return False, "no hay nada que deshacer"
    if _fila_ya_no_existe(g):
        return False, "un registro editado ya no existe"
    return _aplicar_inverso(g)


def rehacer_grabacion(g):

    if g.vacia:
        return False, "no hay nada que rehacer"
    if _fila_ya_no_existe(g):
        return False, "un registro editado ya no existe"
    return _aplicar_inverso(g)


#El nombre que importa deshacer_rehacer_ui.py: `from ... import deshacer_rehacer as _d`
deshacer_rehacer= SimpleNamespace(
    grabar=grabar,
    deshacer_grabacion=deshacer_grabacion,
    rehacer_grabacion=rehacer_grabacion,
)
