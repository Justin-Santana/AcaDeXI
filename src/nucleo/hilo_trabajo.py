#WorkerHilo, corre una tarea pesada en un hilo aparte para que la ventana no se congele mientras
#trabaja. La tarea devuelve datos simples (str, dict, list) y el resultado llega por la señal
#terminado; si falla, el mensaje llega por error. Se usa así:
#worker= WorkerHilo(mi_funcion, dato1, opcion=True)
#worker.terminado.connect(self.mostrar_resultado)
#worker.error.connect(self.mostrar_error)
#worker.start()
#Desde dentro de la tarea nunca se tocan widgets de Qt: eso se hace en el slot que recibe la señal.
from PySide6.QtCore import QThread, Signal


class WorkerHilo(QThread):

    terminado= Signal(object)   #trae lo que devolvió la tarea
    error= Signal(str)          #trae el mensaje de la excepción si la tarea falló
    progreso= Signal(int, int)  #avance opcional: actual, total

    def __init__(self, tarea, *args, **kwargs):

        super().__init__()
        self.tarea= tarea
        self.args= args
        self.kwargs= kwargs
        #Se borra sola cuando el hilo termina. Tiene que quedar conectado antes de start() o la
        #señal finished se pierde y el objeto queda colgado en memoria.
        self.finished.connect(self.deleteLater)

    #Corre la tarea en el hilo secundario. No se llama a mano: se usa start().
    def run(self):

        try:

            self.terminado.emit(self.tarea(*self.args, **self.kwargs))
        except Exception as error:
            import traceback
            self.error.emit(f"{error}\n\n{traceback.format_exc()}")

    #Para que la tarea pueda avisar el avance sin tener que conocer el worker entero.
    def emitir_progreso(self, actual, total):

        self.progreso.emit(actual, total)
