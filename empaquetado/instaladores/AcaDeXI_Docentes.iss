; ============================================================
; AcaDeXI_Docentes.iss — Instalador para DOCENTES/PERSONAL
; ============================================================
; A diferencia de AcaDeXI.iss (Admin/Director), este instalador NO incluye
; ninguna base de datos: solo instala el programa. Es el MISMO instalador
; para todos los Docentes/Personal, sin importar la institución.
;
; La estructura institucional (grados, secciones, materias, usuarios...) y el
; perfil de cada persona llegan aparte, en su archivo .acdx (generado por el
; Administrador/Director desde Configuración → Usuarios y Roles → Generar
; Perfil, con la opción "Incluir la BD Base Institucional" activada). Por eso
; cada Docente/Personal solo necesita DOS archivos:
;   1) Este instalador (AcaDeXI_Docentes_Setup.exe) — el mismo para todos.
;   2) Su propio archivo .acdx — uno por persona.
;
; Flujo para el Docente/Personal:
;   1. Ejecuta este instalador (siguiente, siguiente, instalar). No necesita
;      permisos de administrador: se instala solo para su usuario de Windows.
;   2. Abre AcaDeXI. Como no hay ninguna BD, se le crea una vacía y aparece
;      el login (NO el Wizard de Configuración Inicial de la app, ese wizard
;      solo se activa si nunca se marcó wizard_completado=True — ver bd.py).
;   3. En el login, hace clic en "Importar Perfil Institucional (.acdx)" y
;      selecciona el archivo que le entregó el Administrador/Director.
;   4. Como ese .acdx trae la BD Base incluida, la app la aplica (con
;      confirmación) y con ella llegan su usuario y su rol.
;   5. Escribe su contraseña (o ya viene precargada, si el Administrador la
;      incluyó al generar el perfil) y entra. Listo.
;
; IMPORTANTE — Compilación:
;   Este .iss se compila UNA SOLA VEZ (aquí, o cuando cambie la versión de la
;   app) con Inno Setup, generando "output\AcaDeXI_Docentes_Setup.exe". Copia
;   ese archivo a la carpeta donde vive AcaDeXI.exe (junto al .exe del Admin),
;   con ese mismo nombre exacto: el botón "Exportar Instalador para
;   Docentes/Personal" de Configuración → Seguridad y Backups lo busca ahí
;   (ver instalador.NOMBRE_SETUP_DOCENTES / instalador.ruta_instalador_docentes()).
#define MyAppName "AcaDeXI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AcaDeXI Team"
#define MyAppExeName "AcaDeXI.exe"
#define MyAppURL "https://acadexi.com"

; ------------------------------------------------------------------
; BÚSQUEDA FLEXIBLE DE IMÁGENES DEL INSTALADOR (mismo criterio que
; _carpetas_candidatas_iconos() en iconos.py para los iconos en tiempo de
; ejecución): en vez de exigir que cada .bmp/.ico esté SIEMPRE dentro de
; _internal\, FindAsset("archivo.ext") lo busca, en este orden, y usa el
; primero que encuentre en disco AL COMPILAR:
;   1) _internal\archivo.ext
;   2) archivo.ext            (carpeta raíz del proyecto, junto al .iss)
;   3) _internal\iconos\archivo.ext
;   4) _internal\iconos\iconos_setup\archivo.ext
; Si no aparece en ninguna, se deja la ruta 1) por defecto para que el
; error de "archivo no encontrado" de Inno Setup sea claro y apunte a
; dónde debería estar.
#define FindAsset(str Name) \
  (FileExists(SourcePath + "_internal\\" + Name) ? SourcePath + "_internal\\" + Name : \
   (FileExists(SourcePath + Name) ? SourcePath + Name : \
    (FileExists(SourcePath + "_internal\\iconos\\" + Name) ? SourcePath + "_internal\\iconos\\" + Name : \
     (FileExists(SourcePath + "_internal\\iconos\\iconos_setup\\" + Name) ? SourcePath + "_internal\\iconos\\iconos_setup\\" + Name : \
      SourcePath + "_internal\\" + Name))))

#define IconSetup FindAsset("setupico.ico")
#define ImgWizardLight FindAsset("wizardimage_light.bmp")
#define ImgWizardDark FindAsset("wizardimage_dark.bmp")
#define ImgBadgeLight FindAsset("badgesmall_docentes_light.bmp")
#define ImgBadgeDark FindAsset("badgesmall_docentes_dark.bmp")


[Setup]
; GUID DISTINTO al de AcaDeXI.iss (Admin/Director): son instalaciones
; independientes, incluso si conviven en el mismo equipo.
AppId={{7F1A2B3C-9D4E-4F5A-8B6C-1D2E3F405162}
; Mismo mutex que AcaDeXI.iss (Admin/Director): ambos instaladores apuntan
; al mismo nombre de candado que usa main.py (QSharedMemory /
; GuardaInstanciaUnica), porque el .exe instalado es el mismo binario y solo
; puede haber una instancia corriendo a la vez sea cual sea el instalador
; que se usó. Así, si AcaDeXI está corriendo (aunque esté minimizado a la
; bandeja) al lanzar este instalador, Inno Setup pide cerrarlo antes de
; continuar en vez de intentar sobrescribir un .exe bloqueado.
AppMutex=AcaDeXI-instancia-unica-a3f9c2
AppName={#MyAppName} (Docentes/Personal)
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion} (Docentes/Personal)
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Instalación por usuario, SIN requerir privilegios de administrador: muchos
; docentes usan equipos institucionales sin permisos de admin.
PrivilegesRequired=lowest
; Firma digital (Authenticode): ver explicación completa en AcaDeXI.iss.
; Descomenta ambas líneas cuando tengas el certificado configurado en
; Inno Setup (Tools > Configure Sign Tools).
;SignTool=signtool
;SignedUninstaller=yes
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=output
OutputBaseFilename=AcaDeXI_Docentes_Setup
SetupIconFile={#IconSetup}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
WizardResizable=yes
WizardSizePercent=120
WizardImageFile={#ImgWizardLight}
WizardSmallImageFile={#ImgBadgeLight}
LicenseFile=_internal\terminos.txt
ShowLanguageDialog=yes
ArchitecturesAllowed=x64 x86
ArchitecturesInstallIn64BitMode=x64
VersionInfoVersion=1.0.0.0
VersionInfoCompany=AcaDeXI Team
VersionInfoDescription=Instalador de AcaDeXI - Sistema de Gestion Escolar (Docentes/Personal)
VersionInfoCopyright=Copyright (C) 2026 AcaDeXI Team
VersionInfoProductName=AcaDeXI (Docentes/Personal)
VersionInfoTextVersion=1.0.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Igual que en AcaDeXI.iss (Admin/Director): opción para iniciar AcaDeXI
; automáticamente junto con Windows (minimizado a la bandeja del sistema).
; Desmarcada por defecto.
Name: "autostart"; Description: "Iniciar AcaDeXI automáticamente al encender Windows"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Imágenes del wizard para tema claro/oscuro (se eligen solas según el
; tema de Windows del usuario, ver EligiendoTemaDelWizard en [Code]).
; Flags: dontcopy = no se instalan en {app}, solo viajan dentro del
; instalador y se extraen a una carpeta temporal mientras el wizard corre.
Source: "{#ImgWizardLight}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "{#ImgWizardDark}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "{#ImgBadgeLight}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "{#ImgBadgeDark}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "AcaDeXI.exe"; DestDir: "{app}"; Flags: ignoreversion
; Igual que en el instalador de Admin/Director: SIN acadexi.db. Este
; instalador es idéntico para todos los Docentes/Personal — la base de datos
; y el perfil de cada quien llegan en su .acdx, no en el instalador.
Source: "_internal\*"; DestDir: "{app}\_internal"; Excludes: "acadexi.db,terminos.txt,LICENSE.txt,ICON_LICENSES.txt,README.md,Intentions_Letter.pdf"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentos legales/informativos importantes: se instalan sueltos en la raíz
; de {app} (no dentro de _internal) para que el usuario los encuentre a
; simple vista junto al .exe. skipifsourcedoesntexist evita que falle la
; compilación si alguno todavía no se ha colocado en _internal.
Source: "_internal\terminos.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "_internal\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "_internal\ICON_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "_internal\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "_internal\Intentions_Letter.pdf"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; HKCU (no HKLM): PrivilegesRequired=lowest no tiene permiso de escribir en
; HKLM. Estas claves son solo un extra informativo para "Agregar o quitar
; programas"; Inno Setup ya registra la desinstalación por su cuenta aunque
; se quite esta sección.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName} (Docentes/Personal) {#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_Docentes"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"

; Autoarranque opcional (solo si el usuario marcó la tarea "autostart" de
; arriba). El desinstalador la borra siempre.
; ValueName distinto al del instalador de Admin/Director ("AcaDeXI") para
; que, si alguien llega a tener ambas instalaciones en la misma cuenta de
; Windows (p. ej. para pruebas), una no pise la entrada de autoarranque de
; la otra.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}_Docentes"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Code]
; ============================================================
; PÁGINA "REPARAR / DESINSTALAR" cuando AcaDeXI ya está instalado
; ============================================================
; Ver la explicación completa de este bloque en AcaDeXI.iss (Admin/Director);
; funciona igual aquí, solo que la instalación es por usuario (PrivilegesRequired
; =lowest), así que {app} y unins000.exe viven bajo la carpeta del usuario y no
; hace falta distinguir HKLM/HKCU para detectarla.
var
  YaInstalado: Boolean;
  PaginaModo: TInputOptionWizardPage;
  CerrandoTrasDesinstalar: Boolean;

function EligiendoTemaDelWizard_EsOscuro(): Boolean;
// Lee la preferencia de tema de Windows (Configuración > Personalización >
// Colores > Elige tu modo). Si la clave no existe (Windows viejo o error de
// lectura), asumimos tema claro (Result queda False) para no arriesgar un
// wizard oscuro sobre un Windows claro.
var
  ValorClaro: Cardinal;
begin
  Result := False;
  if RegQueryDWordValue(HKEY_CURRENT_USER,
       'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
       'AppsUseLightTheme', ValorClaro) then
    Result := (ValorClaro = 0);
end;

procedure EligiendoTemaDelWizard_AplicarImagenes();
// Cambia en caliente las imágenes del wizard según el tema de Windows:
//   - La imagen GRANDE (bienvenida/finalización) es el logo normal de
//     AcaDeXI (wizardimage_light/dark.bmp) — igual en las 4 ediciones.
//   - La imagen CHICA (esquina superior de cada página intermedia) es el
//     badge propio de ESTA edición (badgesmall_*.bmp) — así en la misma
//     ventana se ven AMBOS iconos, en sitios distintos, sin fusionarlos. Los .bmp
// declarados con Flags: dontcopy en [Files] no se auto-extraen: hay que
// pedirlo explícitamente con ExtractTemporaryFile antes de poder leerlos.
var
  NombreGrande, NombreChica: String;
begin
  if EligiendoTemaDelWizard_EsOscuro() then
  begin
    NombreGrande := 'wizardimage_dark.bmp';
    NombreChica := 'badgesmall_docentes_dark.bmp';
  end
  else
  begin
    NombreGrande := 'wizardimage_light.bmp';
    NombreChica := 'badgesmall_docentes_light.bmp';
  end;

  ExtractTemporaryFile(NombreGrande);
  ExtractTemporaryFile(NombreChica);

  WizardForm.WizardBitmapImage.Bitmap.LoadFromFile(ExpandConstant('{tmp}\' + NombreGrande));
  WizardForm.WizardBitmapImage2.Bitmap.LoadFromFile(ExpandConstant('{tmp}\' + NombreGrande));
  WizardForm.WizardSmallBitmapImage.Bitmap.LoadFromFile(ExpandConstant('{tmp}\' + NombreChica));
end;

function InitializeSetup(): Boolean;
begin
  YaInstalado := FileExists(ExpandConstant('{app}\unins000.exe'));
  Result := True;
end;

procedure InitializeWizard();
begin
  EligiendoTemaDelWizard_AplicarImagenes();

  if YaInstalado then
  begin
    PaginaModo := CreateInputOptionPage(wpWelcome,
      'AcaDeXI ya está instalado',
      '¿Qué deseas hacer?',
      'Se detectó una instalación existente de AcaDeXI en este equipo. ' +
      'Elige una opción y haz clic en Siguiente.',
      True, False);
    PaginaModo.Add('Reparar / Reinstalar AcaDeXI (mantiene tu configuración y tus datos)');
    PaginaModo.Add('Desinstalar AcaDeXI');
    PaginaModo.SelectedValueIndex := 0;
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  // Evita el cuadro de "¿Seguro que deseas cancelar?" cuando SOMOS nosotros
  // quienes cerramos el asistente tras completar la desinstalación (no es una
  // cancelación real del usuario).
  if CerrandoTrasDesinstalar then
    Confirm := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  RutaDesinstalador: String;
  CodigoSalida: Integer;
begin
  Result := True;
  if YaInstalado and (PaginaModo <> nil) and (CurPageID = PaginaModo.ID) then
  begin
    if PaginaModo.SelectedValueIndex = 1 then
    begin
      RutaDesinstalador := ExpandConstant('{app}\unins000.exe');
      if Exec(RutaDesinstalador, '/SILENT', '', SW_SHOW, ewWaitUntilTerminated, CodigoSalida) then
        MsgBox('AcaDeXI se desinstaló correctamente.', mbInformation, MB_OK)
      else
        MsgBox('No se pudo ejecutar el desinstalador. Puedes desinstalar AcaDeXI ' +
               'manualmente desde Configuración > Aplicaciones de Windows.',
               mbError, MB_OK);
      CerrandoTrasDesinstalar := True;
      WizardForm.Close;
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
  begin
    // WizardSilent() evita que este aviso bloquee instalaciones /SILENT o
    // /VERYSILENT esperando un clic que nunca llega: importante si algún
    // Administrador despliega este instalador a varios equipos de golpe
    // (script, GPO, etc.) sin interacción humana.
    if not WizardSilent() then
      MsgBox('AcaDeXI se instaló correctamente.' + #13#10 + #13#10 +
        'Para terminar, abre la app, ve a la pantalla de inicio de sesión y haz ' +
        'clic en "Importar Perfil Institucional (.acdx)". Selecciona el archivo ' +
        '.acdx que te entregó tu Administrador/Director: con eso quedan listos ' +
        'tu usuario, tu contraseña y los datos de tu institución.' + #13#10 + #13#10 +
        'Nota: al cerrar la ventana con la "X", AcaDeXI sigue ejecutándose en ' +
        'segundo plano (icono junto al reloj de Windows) para no perder tu ' +
        'sesión. Puedes desactivar esto en Configuración > Apariencia, o cerrar ' +
        'la app por completo con clic derecho en ese icono > Salir.',
        mbInformation, MB_OK);
  end;
end;
