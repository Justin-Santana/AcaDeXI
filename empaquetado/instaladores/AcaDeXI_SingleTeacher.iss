; ============================================================
; AcaDeXI_SingleTeacher.iss — Instalador para DOCENTE INDEPENDIENTE
; ============================================================
; A diferencia de AcaDeXI.iss (Admin/Director) y AcaDeXI_Docentes.iss
; (Docentes/Personal de una institución con Full Institutional detrás), esta
; edición NO depende de ninguna institución: el propio docente es dueño
; directo de sus datos (crea sus materias, estudiantes y secciones desde
; cero, sin ".acdx" ni overrides sobre nada importado).
;
; Por eso este instalador SÍ se parece más, en espíritu, a AcaDeXI.iss: la
; primera vez que se ejecuta, la app crea su propia base de datos vacía y
; muestra un Asistente de Configuración Inicial — pero la versión ENFOCADA
; en un solo docente (nombre, materia(s), nivel educativo), no el wizard
; institucional completo de Full Institutional. Aun así, igual que
; AcaDeXI_Docentes.iss, se instala SIN privilegios de administrador: un
; docente independiente puede estar usando un equipo personal o uno
; institucional sin permisos de admin.
;
; Cómo se detecta esta edición en tiempo de ejecución (ver main.py,
; edicion_actual()): por la clave de desinstalación que este .iss escribe
; en HKCU (sección [Registry] más abajo). Ni AcaDeXI.iss ni
; AcaDeXI_Docentes.iss escriben esa clave, así que no hay ambigüedad
; posible entre ediciones instaladas en el mismo equipo.
;
; IMPORTANTE — Compilación:
;   Igual que AcaDeXI_Docentes.iss, este .iss se compila aparte con Inno
;   Setup, generando "output\AcaDeXI_SingleTeacher_Setup.exe". Es un
;   instalador independiente, pensado para distribuirse directamente al
;   docente (descarga propia, sin pasar por ningún Administrador/Director).
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
#define ImgBadgeLight FindAsset("badgesmall_singleteacher_light.bmp")
#define ImgBadgeDark FindAsset("badgesmall_singleteacher_dark.bmp")


[Setup]
; GUID DISTINTO al de AcaDeXI.iss y AcaDeXI_Docentes.iss: instalación
; independiente, incluso si conviven varias ediciones en el mismo equipo
; (p. ej. para pruebas).
AppId={{2A5B7C9D-1E3F-4A5B-9C7D-8E1F2A3B4C5D}
; Mismo mutex que las otras dos ediciones: el .exe instalado es el mismo
; binario y solo puede haber una instancia corriendo a la vez, sea cual
; sea el instalador que se usó.
AppMutex=AcaDeXI-instancia-unica-a3f9c2
AppName={#MyAppName} Single Teacher
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion} (Single Teacher)
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Instalación por usuario, SIN requerir privilegios de administrador, igual
; que AcaDeXI_Docentes.iss y por la misma razón: el docente puede no tener
; permisos de admin en el equipo que use.
PrivilegesRequired=lowest
; Firma digital (Authenticode): ver explicación completa en AcaDeXI.iss.
; Descomenta ambas líneas cuando tengas el certificado configurado en
; Inno Setup (Tools > Configure Sign Tools).
;SignTool=signtool
;SignedUninstaller=yes
DefaultDirName={userpf}\{#MyAppName} Single Teacher
DefaultGroupName={#MyAppName} Single Teacher
AllowNoIcons=yes
OutputDir=output
OutputBaseFilename=AcaDeXI_SingleTeacher_Setup
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
VersionInfoDescription=Instalador de AcaDeXI - Edicion Single Teacher (Docente Independiente)
VersionInfoCopyright=Copyright (C) 2026 AcaDeXI Team
VersionInfoProductName=AcaDeXI Single Teacher
VersionInfoTextVersion=1.0.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
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
; Igual que en las otras dos ediciones: acadexi.db NO se instala junto al
; ejecutable. Aquí la app la crea vacía en %APPDATA%\AcaDeXI\acadexi.db (o
; una subcarpeta propia si en la implementación de main.py se decide
; separar el almacenamiento por edición) y a continuación corre el
; Asistente de Configuración Inicial ENFOCADO en un solo docente — no el
; wizard institucional completo de Full Institutional.
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
Name: "{group}\{#MyAppName} Single Teacher"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName} Single Teacher}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} Single Teacher"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; HKCU (no HKLM): PrivilegesRequired=lowest no tiene permiso de escribir en
; HKLM. Esta clave cumple DOS funciones: registro informativo en "Agregar
; o quitar programas" Y, sobre todo, es el GANCHO que main.py.edicion_actual()
; usa para reconocer esta edición como "single_teacher" (ver Pieza 1 del
; prompt de arquitectura de las 4 ediciones). Nombre de subclave distinto al
; de AcaDeXI_Docentes y al de AcaDeXI_SideStepper para que no haya
; ambigüedad si conviven varias ediciones en el mismo equipo (pruebas).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName} Single Teacher {#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SingleTeacher"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"

; Autoarranque opcional (solo si el usuario marcó la tarea "autostart" de
; arriba). ValueName distinto al de las otras dos ediciones para que, si
; alguien llega a tener varias instaladas en la misma cuenta de Windows
; (pruebas), ninguna pise la entrada de autoarranque de otra.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}_SingleTeacher"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Code]
; ============================================================
; PÁGINA "REPARAR / DESINSTALAR" cuando esta edición ya está instalada
; ============================================================
; Ver la explicación completa de este bloque en AcaDeXI.iss (Admin/Director);
; funciona igual aquí: instalación por usuario (PrivilegesRequired=lowest),
; {app} y unins000.exe viven bajo la carpeta del usuario.
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
    NombreChica := 'badgesmall_singleteacher_dark.bmp';
  end
  else
  begin
    NombreGrande := 'wizardimage_light.bmp';
    NombreChica := 'badgesmall_singleteacher_light.bmp';
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
      'AcaDeXI Single Teacher ya está instalado',
      '¿Qué deseas hacer?',
      'Se detectó una instalación existente de AcaDeXI Single Teacher en este equipo. ' +
      'Elige una opción y haz clic en Siguiente.',
      True, False);
    PaginaModo.Add('Reparar / Reinstalar (mantiene tu configuración y tus datos)');
    PaginaModo.Add('Desinstalar AcaDeXI Single Teacher');
    PaginaModo.SelectedValueIndex := 0;
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
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
        MsgBox('AcaDeXI Single Teacher se desinstaló correctamente.', mbInformation, MB_OK)
      else
        MsgBox('No se pudo ejecutar el desinstalador. Puedes desinstalar AcaDeXI ' +
               'Single Teacher manualmente desde Configuración > Aplicaciones de Windows.',
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
    if not WizardSilent() then
      MsgBox('AcaDeXI Single Teacher se instaló correctamente.' + #13#10 + #13#10 +
        'Al abrir la app por primera vez verás un Asistente de Configuración ' +
        'rápido, pensado para un solo docente: tu nombre, tu(s) materia(s) y ' +
        'el nivel educativo con el que trabajas. No necesitas ningún archivo ' +
        '.acdx ni depender de ninguna institución — todos los datos que ' +
        'captures (estudiantes, secciones, calificaciones) son tuyos desde ' +
        'el primer momento.' + #13#10 + #13#10 +
        'Nota: al cerrar la ventana con la "X", AcaDeXI sigue ejecutándose en ' +
        'segundo plano (icono junto al reloj de Windows) para no perder tu ' +
        'sesión. Puedes desactivar esto en Configuración > Apariencia, o cerrar ' +
        'la app por completo con clic derecho en ese icono > Salir.',
        mbInformation, MB_OK);
  end;
end;
