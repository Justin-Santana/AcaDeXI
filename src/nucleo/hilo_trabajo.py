"""
hilo_trabajo.py — Worker genérico QThread para AcaDeXI.

Mueve cualquier tarea pesada (I/O, cómputo) fuera del hilo principal de Qt
para que la UI nunca se congele. Uso:

    worker = WorkerHilo(mi_funcion, arg1, kwarg=valor)
    worker.terminado.connect(slot_que_recibe_resultado)
    worker.error.connect(slot_que_muestra_error)
    worker.progreso.connect(slot_progreso)   # opcional
    worker.finished.connect(worker.deleteLater)
    worker.start()

NUNCA manipules widgets Qt desde dentro de la función `tarea` — solo
devuelve datos simples (str, dict, list, etc.) via la señal `terminado`.
"""

from PySide6.QtCore import QThread, Signal


class WorkerHilo(QThread):
    """Worker genérico y reutilizable. Ejecuta `tarea(*args, **kwargs)`
    en un hilo secundario y comunica el resultado al hilo principal
    mediante señales Qt (thread-safe por diseño del mecanismo de señales).

    Señales:
        terminado(object): emitida con el valor de retorno de `tarea` cuando
            ésta finaliza sin excepción.
        error(str): emitida con el mensaje de la excepción si `tarea` lanza
            alguna, en vez de terminado.
        progreso(int, int): opcional — la propia `tarea` puede llamar a
            `self._emitir_progreso(actual, total)` si recibe el worker como
            primer argumento (ver WorkerHiloConProgreso).
    """

    terminado = Signal(object)
    error = Signal(str)
    progreso = Signal(int, int)   # actual, total

    def __init__(self, tarea, *args, **kwargs):
        super().__init__()
        self._tarea = tarea
        self._args = args
        self._kwargs = kwargs
        # Autodestroy: cuando el hilo termina su run(), se libera la memoria
        # automáticamente en vez de quedar como un objeto huérfano. Hay que
        # conectar ANTES de start() para no perder la señal finished.
        self.finished.connect(self.deleteLater)

    def run(self):
        """Ejecuta la tarea en el hilo secundario. No llamar directamente —
        usar .start() para que Qt lo lance en el hilo correcto."""
        try:
            resultado = self._tarea(*self._args, **self._kwargs)
            self.terminado.emit(resultado)
        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")

    def emitir_progreso(self, actual, total):
        """Atajo para que la tarea pueda reportar avance sin acceder a `self`
        directamente. Seguro llamarlo desde el hilo secundario."""
        self.progreso.emit(actual, total)
