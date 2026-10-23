"""deshacer_rehacer_ui.py — Botones "Deshacer" / "Rehacer", pilas y atajos de una tabla.

Uso típico dentro de un módulo (ver materias.py, materiales.py, etc.):

    # en __init__:
    self.deshacer = GestorDeshacer(self, self.main_window, self.refrescar,
                                   nombre="espacio físico")
    # al construir la fila de botones (basta UNA línea: el widget trae los
    # dos botones, Deshacer y Rehacer, y se oculta solo cuando no hay nada):
    fila_botones.addWidget(self.deshacer.boton)

    # en el método que elimina o edita:
    with self.deshacer.grabar("Eliminó el espacio 'Aula 3'"):
        ...los DELETE/UPDATE de siempre...
    self.refrescar()

El gestor se encarga de: capturar las filas (incluidos los hijos que borra el
cascade, ver deshacer_rehacer.py), mostrar/ocultar los botones, rotularlos
("Deshacer (2)"), atender Ctrl+Z (deshacer) y Ctrl+Y / Ctrl+Shift+Z (rehacer),
restaurar o reaplicar en una transacción y avisar con un toast. Hasta 10
niveles por pantalla; se pierden al cerrar la app. Hacer una acción nueva
vacía la pila de rehacer (como en cualquier editor).
"""
from contextlib import contextmanager

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from src.nucleo.deshacer_rehacer import deshacer_rehacer as _d
from src.nucleo.feedback import mostrar_toast

MAX_NIVELES = 10


class GestorDeshacer(QObject):
    def __init__(self, pagina, main_window, refrescar=None, nombre="registro",
                 atajo=True, solo_no_docente=True, parent_boton=None):
        super().__init__(pagina)
        self._pagina = pagina
        self._main = main_window
        self._refrescar = refrescar
        self._nombre = nombre
        self._pila = []            # [(Grabacion, etiqueta)] -> se pueden DESHACER
        self._pila_rehacer = []    # [(Grabacion, etiqueta)] -> se pueden REHACER
        self._grupos = []          # [(contenedor, btn_deshacer, btn_rehacer)]
        self.boton = self.nuevo_boton(parent_boton)
        if atajo:
            self._registrar_atajos(solo_no_docente)

    # --------------------------------------------------------
    def nuevo_boton(self, parent=None):
        """Crea un par de botones (Deshacer + Rehacer) dentro de un único widget
        para añadirlo a un layout con UNA línea. Varios pares comparten la MISMA
        pila: p. ej. una pantalla con varias pestañas pone uno por tabla."""
        cont = QWidget(parent)
        cont.setObjectName("ContenedorDeshacerRehacer")
        lay = QHBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        bd_ = QPushButton("Deshacer", cont)
        bd_.setObjectName("BtnAccionDeshacer")
        bd_.setCursor(Qt.CursorShape.PointingHandCursor)
        bd_.clicked.connect(self.deshacer)
        br = QPushButton("Rehacer", cont)
        br.setObjectName("BtnAccionRehacer")
        br.setCursor(Qt.CursorShape.PointingHandCursor)
        br.clicked.connect(self.rehacer)
        lay.addWidget(bd_)
        lay.addWidget(br)
        self._grupos.append((cont, bd_, br))
        self._actualizar_botones()
        return cont

    # --------------------------------------------------------
    def _registrar_atajos(self, solo_no_docente):
        try:
            from src.nucleo.atajos import registrar_atajo
            existentes = {s for s, _ in getattr(self._pagina, "_atajos_registrados", [])}
            if "Ctrl+Z" not in existentes:
                registrar_atajo(self._pagina, self._main, "Ctrl+Z", "Deshacer", self.deshacer,
                                solo_no_docente=solo_no_docente)
            if "Ctrl+Y" not in existentes:
                registrar_atajo(self._pagina, self._main, "Ctrl+Y", "Rehacer", self.rehacer,
                                solo_no_docente=solo_no_docente)
                # Variante habitual en otros editores; sin descripción = no se lista aparte.
                registrar_atajo(self._pagina, self._main, "Ctrl+Shift+Z", "", self.rehacer,
                                solo_no_docente=solo_no_docente)
        except Exception:
            pass

    # --------------------------------------------------------
    @contextmanager
    def grabar(self, etiqueta="Eliminó un registro"):
        """Envuelve el borrado/edición. Al salir sin error, si hubo algo
        deshacible lo apila y muestra el botón."""
        with _d.grabar(etiqueta) as g:
            yield g
        self.registrar(g)

    def registrar(self, g, aviso=True):
        """Apila una grabación ya hecha (p. ej. la hecha en un WorkerHilo)."""
        if g is None or g.vacia:
            return
        if g.no_deshacible:
            if aviso:
                mostrar_toast(self._pagina, "Esta acción es muy grande y no podrá deshacerse.",
                              "advertencia")
            return
        self._pila.append((g, g.etiqueta))
        del self._pila[:-MAX_NIVELES]
        self._pila_rehacer.clear()          # una acción nueva invalida lo "rehacible"
        self._actualizar_botones()
        if aviso:
            mostrar_toast(self._pagina, g.etiqueta.rstrip(".") + ".", "exito",
                          accion=self.deshacer, texto_accion="Deshacer")
        # Los tutoriales (Modo Detallado) esperan este evento para saber que
        # la acción real ocurrió; antes lo emitía el cuadro modal "Eliminado".
        try:
            from src.nucleo.iconos import eventos_ui
            eventos_ui.exito_reportado.emit(self._pagina, "Eliminado", g.etiqueta)
        except Exception:
            pass

    def hay_pendientes(self):
        return bool(self._pila)

    def hay_para_rehacer(self):
        return bool(self._pila_rehacer)

    def limpiar(self):
        self._pila.clear()
        self._pila_rehacer.clear()
        self._actualizar_botones()

    # --------------------------------------------------------
    def _actualizar_botones(self):
        nu, nr = len(self._pila), len(self._pila_rehacer)
        for grupo in list(self._grupos):
            cont, bd_, br = grupo
            try:
                bd_.setVisible(nu > 0)
                br.setVisible(nr > 0)
                cont.setVisible(nu > 0 or nr > 0)
                if nu:
                    ultima = self._pila[-1][1]
                    bd_.setText("Deshacer" + (f" ({nu})" if nu > 1 else ""))
                    bd_.setToolTip(f"Deshacer: {ultima}  (Ctrl+Z)")
                    bd_.setAccessibleName(f"Deshacer: {ultima}")
                if nr:
                    sig = self._pila_rehacer[-1][1]
                    br.setText("Rehacer" + (f" ({nr})" if nr > 1 else ""))
                    br.setToolTip(f"Rehacer: {sig}  (Ctrl+Y)")
                    br.setAccessibleName(f"Rehacer: {sig}")
            except RuntimeError:
                self._grupos.remove(grupo)   # widget ya destruido

    def _auditar(self, texto):
        try:
            from src.nucleo.bd import registrar_auditoria
            usuario = getattr(self._main, "usuario_actual", None)
            # Mismo nombre de módulo que usan los demás registros de auditoría
            # (p. ej. "Materias"), para que los filtros del visor los agrupen.
            registrar_auditoria(getattr(self._pagina, "NOMBRE_AUDITORIA", self._nombre),
                                texto, usuario, "")
        except Exception:
            pass

    def _refrescar_pagina(self):
        if self._refrescar is not None:
            try:
                self._refrescar()
            except Exception:
                import traceback
                traceback.print_exc()

    # --------------------------------------------------------
    def deshacer(self):
        if not self._pila:
            mostrar_toast(self._pagina, "No hay nada que deshacer.", "info")
            return
        g, etiqueta = self._pila[-1]
        ok, resultado = _d.deshacer_grabacion(g)
        if not ok:
            mostrar_toast(
                self._pagina,
                f"No se pudo deshacer ({_traducir_error(resultado)}). Los datos no se modificaron.",
                "error", duracion=7000)
            return
        self._pila.pop()
        self._pila_rehacer.append((g, etiqueta))
        del self._pila_rehacer[:-MAX_NIVELES]
        self._actualizar_botones()
        self._auditar(f"Deshizo: {etiqueta}")
        self._refrescar_pagina()
        mostrar_toast(self._pagina, f"Deshecho: {etiqueta.rstrip('.')}.", "info",
                      accion=self.rehacer, texto_accion="Rehacer")

    def rehacer(self):
        if not self._pila_rehacer:
            mostrar_toast(self._pagina, "No hay nada que rehacer.", "info")
            return
        g, etiqueta = self._pila_rehacer[-1]
        ok, resultado = _d.rehacer_grabacion(g)
        if not ok:
            mostrar_toast(
                self._pagina,
                f"No se pudo rehacer ({_traducir_error(resultado)}). Los datos no se modificaron.",
                "error", duracion=7000)
            return
        self._pila_rehacer.pop()
        self._pila.append((g, etiqueta))
        del self._pila[:-MAX_NIVELES]
        self._actualizar_botones()
        self._auditar(f"Rehizo: {etiqueta}")
        self._refrescar_pagina()
        mostrar_toast(self._pagina, f"Rehecho: {etiqueta.rstrip('.')}.", "exito",
                      accion=self.deshacer, texto_accion="Deshacer")


def _traducir_error(msg):
    m = str(msg)
    if "UNIQUE" in m.upper():
        return "ya existe otro registro con los mismos datos únicos"
    if "FOREIGN KEY" in m.upper():
        return "un registro relacionado ya no existe"
    return m[:90]
