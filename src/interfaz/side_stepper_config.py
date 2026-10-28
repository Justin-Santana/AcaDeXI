#Pantalla de configuración de módulos por rol para AcaDeXI Side Stepper
#(Pieza 2 del motor de permisos, prompt_arquitectura_4_ediciones.md).
#
#Un solo widget (`PanelPermisosSideStepper`) sirve para los DOS orígenes de
#configuración descritos en el prompt:
#
#A) Full Institutional, Configuración → "Exportar Side Stepper": el
#Director la abre ANTES de exportar, para decidir qué rol(es) y qué
#módulos tendrá la copia que está por generar.
#B) Wizard standalone de Side Stepper (Pieza 5, primer arranque): el
#propio usuario la usa para elegir su rol y sus módulos.
#
#La única diferencia entre A y B es QUIÉN la abre y en qué momento -el
#widget en sí no sabe ni le importa cuál de los dos casos es; ambos llaman a
#las mismas funciones de permisos.py (guardar_permisos_side_stepper, etc.),
#así que un cambio futuro en la lógica de permisos se aplica a ambos casos
#automáticamente.
#
#Soporta ROLES PERSONALIZADOS: además de los 5 roles fijos de
#permisos.ROLES, se puede escribir cualquier nombre de rol nuevo (ej.
#"Bibliotecario") y configurarle su propio conjunto de módulos, con
#MODULOS_EXISTENTES completo como techo (ver permisos.py,
#guardar_permisos_side_stepper).
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QListWidget, QListWidgetItem, QCheckBox, QScrollArea, QFrame, QMessageBox, QDialog,
    QDialogButtonBox, QInputDialog, QFormLayout)
from PySide6.QtCore import Qt, QSize

from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, centrar_y_al_frente
from src.nucleo.iconos_emoji import icono_emoji
from src.nucleo.limite_campos import limitar_campo_texto
from src.nucleo import permisos


#Widget embebible (no es un QDialog en sí: quien lo use decide si lo
#mete dentro de un QDialog propio -como hace DialogoExportarSideStepper
#más abajo- o directamente en una página de wizard).
class PanelPermisosSideStepper(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        layout= QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        info= QLabel(
            "Elige un rol de la lista (o escribe uno nuevo si ninguno describe bien el cargo) "
            "y marca los módulos que tendrá disponibles. El techo de módulos posibles cambia "
            "automáticamente según si es uno de los 5 roles institucionales o uno personalizado.")
        info.setWordWrap(True)
        layout.addWidget(info)

        fila_rol= QHBoxLayout()
        fila_rol.addWidget(QLabel("Rol:"))
        self.combo_rol= QComboBox()
        self.combo_rol.setEditable(True)
        self.combo_rol.addItems(permisos.ROLES)
        self._cargar_roles_ya_configurados()
        self.combo_rol.currentTextChanged.connect(self._refrescar_checkboxes)
        fila_rol.addWidget(self.combo_rol, 1)
        layout.addLayout(fila_rol)

        self.lbl_tipo_rol= QLabel()
        self.lbl_tipo_rol.setWordWrap(True)
        layout.addWidget(self.lbl_tipo_rol)

        self.scroll_modulos= QScrollArea()
        self.scroll_modulos.setWidgetResizable(True)
        self.contenedor_checks= QWidget()
        self.layout_checks= QVBoxLayout(self.contenedor_checks)
        self.layout_checks.setSpacing(4)
        self.scroll_modulos.setWidget(self.contenedor_checks)
        layout.addWidget(self.scroll_modulos, 1)
        self._checks= {}

        fila_acciones= QHBoxLayout()
        btn_todos= QPushButton("Marcar todos")
        btn_todos.clicked.connect(lambda: self._marcar_todos(True))
        fila_acciones.addWidget(btn_todos)
        btn_ninguno= QPushButton("Desmarcar todos")
        btn_ninguno.clicked.connect(lambda: self._marcar_todos(False))
        fila_acciones.addWidget(btn_ninguno)
        fila_acciones.addStretch()
        btn_guardar_rol= QPushButton("Guardar este rol")
        btn_guardar_rol.setIcon(icono_emoji("💾"))
        btn_guardar_rol.setIconSize(QSize(16, 16))
        btn_guardar_rol.setObjectName("BtnAccionAgregar")
        btn_guardar_rol.clicked.connect(self._guardar_rol_actual)
        fila_acciones.addWidget(btn_guardar_rol)
        layout.addLayout(fila_acciones)

        layout.addWidget(QLabel("Roles ya configurados en esta copia:"))
        self.lista_roles_configurados= QListWidget()
        self.lista_roles_configurados.setMaximumHeight(120)
        layout.addWidget(self.lista_roles_configurados)

        fila_lista= QHBoxLayout()
        fila_lista.addStretch()
        btn_eliminar_rol= QPushButton("Eliminar rol seleccionado")
        btn_eliminar_rol.setIcon(icono_emoji("🗑️"))
        btn_eliminar_rol.setIconSize(QSize(16, 16))
        btn_eliminar_rol.clicked.connect(self._eliminar_rol_seleccionado)
        fila_lista.addWidget(btn_eliminar_rol)
        layout.addLayout(fila_lista)

        self._refrescar_lista_configurados()
        self._refrescar_checkboxes(self.combo_rol.currentText())

    def _cargar_roles_ya_configurados(self):

        for info_rol in permisos.listar_roles_side_stepper_configurados():
            if self.combo_rol.findText(info_rol["rol"]) < 0:
                self.combo_rol.addItem(info_rol["rol"])

    def _refrescar_checkboxes(self, rol_texto):

        rol_texto= (rol_texto or "").strip()
        for i in reversed(range(self.layout_checks.count())):
            widget= self.layout_checks.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self._checks= {}
        if not rol_texto:
            self.lbl_tipo_rol.setText("Escribe o elige un rol para configurar sus módulos.")
            return

        es_fijo= rol_texto in permisos.ROLES
        techo= permisos.techo_para_rol_side_stepper(rol_texto)
        self.lbl_tipo_rol.setText(
            f"Rol institucional fijo — techo máximo: {len(techo)} módulo(s) posibles."
            if es_fijo else
            f"Rol PERSONALIZADO (no es uno de los 5 roles fijos) — puede tener cualquier "
            f"módulo de la app ({len(techo)} disponibles).")

        otorgados_actuales= set(permisos.obtener_permisos_side_stepper(rol_texto))
        for modulo in techo:
            check= QCheckBox(modulo)
            check.setChecked(modulo in otorgados_actuales)
            self.layout_checks.addWidget(check)
            self._checks[modulo]= check
        self.layout_checks.addStretch()

    def _marcar_todos(self, estado):

        for check in self._checks.values():
            check.setChecked(estado)

    #Acceso público a los módulos actualmente marcados para el rol en
    #pantalla, sin guardar -lo usa WizardSideStepper para validar antes
    #de crear la cuenta, sin depender de un atributo "privado".
    def modulos_marcados(self):

        return [modulo for modulo, check in self._checks.items() if check.isChecked()]

    def _guardar_rol_actual(self):

        rol_texto= self.combo_rol.currentText().strip()
        if not rol_texto:
            mostrar_mensaje("advertencia", "Falta el rol", "Escribe o elige un rol primero.", self)
            return
        modulos_marcados= [modulo for modulo, check in self._checks.items() if check.isChecked()]
        guardados= permisos.guardar_permisos_side_stepper(rol_texto, modulos_marcados)
        if self.combo_rol.findText(rol_texto) < 0:
            self.combo_rol.addItem(rol_texto)
        self._refrescar_lista_configurados()
        mostrar_mensaje("exito", "Rol guardado",
                         f"«{rol_texto}» tendrá {len(guardados)} módulo(s) activo(s) en esta copia de Side Stepper.",
                         self)

    def _refrescar_lista_configurados(self):

        self.lista_roles_configurados.clear()
        for info_rol in permisos.listar_roles_side_stepper_configurados():
            etiqueta= f"{info_rol['rol']} — {len(info_rol['modulos'])} módulo(s)"
            if info_rol["personalizado"]:
                etiqueta += "  (personalizado)"
            item= QListWidgetItem(etiqueta)
            item.setData(Qt.ItemDataRole.UserRole, info_rol["rol"])
            self.lista_roles_configurados.addItem(item)

    def _eliminar_rol_seleccionado(self):

        item= self.lista_roles_configurados.currentItem()
        if not item:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un rol de la lista primero.", self)
            return
        rol= item.data(Qt.ItemDataRole.UserRole)
        respuesta= QMessageBox.question(
            self, "Confirmar", f"¿Quitar toda la configuración de «{rol}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if respuesta == QMessageBox.StandardButton.Yes:
            permisos.eliminar_rol_side_stepper(rol)
            self._refrescar_lista_configurados()
            self._refrescar_checkboxes(self.combo_rol.currentText())


#Uso A del prompt: Full Institutional, Configuración → "Exportar Side
#Stepper". El Director configura los roles/módulos con
#PanelPermisosSideStepper y, cuando está conforme, dispara la generación
#del paquete exportado (mismo mecanismo de empaquetado que ya usa el
#.acdx de Docentes — ver instalador.py) más el instalador
#AcaDeXI_SideStepper_Setup.exe para entregar a la persona.
class DialogoExportarSideStepper(QDialog):

    def __init__(self, main_window, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.setWindowTitle("Exportar Side Stepper")
        aplicar_icono_ventana(self)
        self.setMinimumSize(560, 620)

        layout= QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        titulo= QLabel("Configura los roles y módulos de la copia de Side Stepper que vas a exportar")
        titulo.setWordWrap(True)
        titulo.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(titulo)

        self.panel= PanelPermisosSideStepper(self)
        layout.addWidget(self.panel, 1)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.reject)
        botones.accepted.connect(self.accept)
        layout.addWidget(botones)

        centrar_y_al_frente(self, parent)


#Wizard standalone — Uso B del prompt (primer arranque de una copia de Side Stepper adquirida independiente,
#sin paquete de permisos exportado por ningún Director). Ver main.py, edicion_actual(). a diferencia del Uso a
#(DialogoExportarSideStepper, arriba, lo llena el Director ANTES de exportar), aquí lo llena el propio usuario,
#en su propio primer arranque, y termina creando su propia cuenta de acceso -no hay ningún Director que la haya
#creado por él.
#Se ejecuta DESPUÉS de que la estructura institucional base ya existe
#(mismo WizardConfiguracion institucional que usa Full Institutional: ver
#main.py -Side Stepper reutiliza el esquema completo de bd.py, así que
#también necesita Cursos/Grados/Secciones antes de que tenga sentido
#elegir qué módulos de Estudiantes/Materias/etc. va a usar este rol).
#Dos pasos en un solo diálogo:
#1) Elegir rol y módulos (PanelPermisosSideStepper, el MISMO widget que
#usa el Director en Uso A -mismo motor, distinto quién lo llena).
#2) Crear la cuenta de acceso (usuario/contraseña) para ESE rol -no
#hay ningún Director que la haya creado de antemano, como sí pasa
#en el Uso A exportado.
class WizardSideStepper(QDialog):

    def __init__(self, main_window, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self.setWindowTitle("Bienvenido a AcaDeXI Side Stepper")
        aplicar_icono_ventana(self)
        self.setMinimumSize(560, 640)

        layout= QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        intro= QLabel(
            "Primero elige tu rol y los módulos que vas a usar; luego crea tu cuenta de acceso. "
            "Si tu Director/Administrador ya te entregó un paquete de configuración, cancela este "
            "asistente e impórtalo desde la pantalla de inicio de sesión en su lugar.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.panel= PanelPermisosSideStepper(self)
        layout.addWidget(self.panel, 1)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separador)

        layout.addWidget(QLabel("Crea tu cuenta de acceso con el rol de arriba:"))
        form_cuenta= QFormLayout()
        self.in_nombre= QLineEdit()
        limitar_campo_texto(self.in_nombre)
        form_cuenta.addRow("Tu nombre completo:", self.in_nombre)
        self.in_usuario= QLineEdit()
        limitar_campo_texto(self.in_usuario)
        form_cuenta.addRow("Usuario:", self.in_usuario)
        self.in_password= QLineEdit()
        limitar_campo_texto(self.in_password)
        self.in_password.setEchoMode(QLineEdit.EchoMode.Password)
        form_cuenta.addRow("Contraseña:", self.in_password)
        layout.addLayout(form_cuenta)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Finalizar")
        botones.accepted.connect(self._finalizar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

        centrar_y_al_frente(self, parent)

    def _finalizar(self):

        rol= self.panel.combo_rol.currentText().strip()
        nombre= self.in_nombre.text().strip()
        usuario= self.in_usuario.text().strip()
        password= self.in_password.text().strip()
        if not rol:
            mostrar_mensaje("advertencia", "Falta el rol", "Elige o escribe un rol arriba.", self)
            return
        modulos_marcados= self.panel.modulos_marcados()
        if not modulos_marcados:
            mostrar_mensaje("advertencia", "Sin módulos",
                            "Marca al menos un módulo para tu rol antes de continuar.", self)
            return
        if not nombre or not usuario or not password:
            mostrar_mensaje("advertencia", "Datos incompletos",
                            "Completa tu nombre, usuario y contraseña para crear tu cuenta.", self)
            return

        from src.nucleo.bd import obtener_conexion, hash_password
        from datetime import datetime
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT id FROM usuarios WHERE username=?", (usuario,))
        if c.fetchone():
            conn.close()
            mostrar_mensaje("advertencia", "Usuario ya existe",
                            f"Ya existe una cuenta con el usuario «{usuario}». Elige otro.", self)
            return

        guardados= permisos.guardar_permisos_side_stepper(rol, modulos_marcados)
        #El rol se guarda TAL CUAL en `usuarios.rol` -sea uno de los 5 fijos o uno personalizado escrito a mano-:
        #permisos.modulo_visible() ya sabe consultar permisos_side_stepper para cualquier texto de rol en la edición
        #side_stepper (ver permisos.py), así que no hace falta ninguna traducción especial aquí.
        c.execute("""INSERT INTO usuarios (username, password, nombre_completo, rol, activo, fecha_creacion)
                     VALUES (?, ?, ?, ?, 1, ?)""",
                  (usuario, hash_password(password), nombre, rol, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        mostrar_mensaje("exito", "Cuenta creada",
                        f"Tu cuenta «{usuario}» quedó lista con el rol «{rol}» y {len(guardados)} "
                        "módulo(s) activo(s). Ahora inicia sesión con ella.", self)
        self.accept()
