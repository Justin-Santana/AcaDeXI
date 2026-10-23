; ============================================================
; AcaDeXI_SideStepper.iss — Instalador para ROLES NO-DOCENTES (Side Stepper)
; ============================================================
; Un mismo instalador cubre las DOS variantes de origen de Side Stepper
; (ver prompt_arquitectura_4_ediciones.md, edición 4):
;
;   A) EXPORTADO desde Full Institutional: el Director/Administrador ya
;      decidió, antes de exportar, qué rol y qué módulos tendrá esta copia
;      (pantalla nueva en Full Institutional, Configuración → Exportar
;      Side Stepper). Esa configuración viaja en un paquete de datos
;      (mismo mecanismo que el .acdx de Docentes) que la persona importa
;      DESPUÉS de instalar, igual que hace un Docente con su .acdx.
;
;   B) STANDALONE (adquirida independiente): al primer arranque, sin ningún
;      paquete que importar, la propia app corre un wizard de "elige tu rol
;      → elige tus módulos dentro de lo que ese rol permite" (mismo motor de
;      permisos de la variante A, solo que aquí lo llena el propio usuario
;      en vez del Director).
;
; La diferencia entre A y B es de DATOS/flujo dentro de la app (si hay o no
; un paquete para importar en el primer login), no del instalador: por eso
; un solo .iss basta, igual que un solo AcaDeXI_Docentes_Setup.exe sirve
; para docentes de cualquier institución sin importar cuál .acdx importen
; después.
;
; Cómo se detecta esta edición en tiempo de ejecución (ver main.py,
; edicion_actual()): por la clave de desinstalación que este .iss escribe
; en HKCU (sección [Registry] más abajo) — igual patrón que
; AcaDeXI_Docentes.iss y AcaDeXI_SingleTeacher.iss, con su propio nombre de
; subclave para no generar ambigüedad si conviven varias ediciones en el
; mismo equipo (pruebas).
;
; IMPORTANTE — Compilación:
;   Se compila aparte con Inno Setup, generando
;   "output\AcaDeXI_SideStepper_Setup.exe". Para la variante A (exportada),
;   Full Institutional puede ofrecerlo para descargar junto con el paquete
;   de configuración generado, igual que hoy ofrece
;   AcaDeXI_Docentes_Setup.exe junto al .acdx (ver instalador.py). Para la
;   variante B (standalone), se distribuye igual que AcaDeXI_SingleTeacher
;   Setup.exe: descarga directa, sin pasar por ningún Administrador/Director.
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
#define ImgBadgeLight FindAsset("badgesmall_sidestepper_light.bmp")
#define ImgBadgeDark FindAsset("badgesmall_sidestepper_dark.bmp")


[Setup]
; GUID DISTINTO a las otras tres ediciones: instalación independiente,
; incluso si conviven varias en el mismo equipo (pruebas).
AppId={{9F3E1D5C-4B6A-4D7E-8C9F-0A1B2C3D4E5F}
; Mismo mutex que las otras tres ediciones: el .exe instalado es el mismo
; binario y solo puede haber una instancia corriendo a la vez, sea cual
; sea el instalador que se usó.
AppMutex=AcaDeXI-instancia-unica-a3f9c2
AppName={#MyAppName} Side Stepper
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion} (Side Stepper)
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Instalación por usuario, SIN requerir privilegios de administrador: igual
; razón que en Docentes y Single Teacher — quien instala Side Stepper
; (Coordinación u otro rol no-docente) puede no tener permisos de admin en
; el equipo, sobre todo en la variante exportada desde una institución.
PrivilegesRequired=lowest
; Firma digital (Authenticode): ver explicación completa en AcaDeXI.iss.
; Descomenta ambas líneas cuando tengas el certificado configurado en
; Inno Setup (Tools > Configure Sign Tools).
;SignTool=signtool
;SignedUninstaller=yes
DefaultDirName={userpf}\{#MyAppName} Side Stepper
DefaultGroupName={#MyAppName} Side Stepper
AllowNoIcons=yes
OutputDir=output
OutputBaseFilename=AcaDeXI_SideStepper_Setup
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
VersionInfoDescription=Instalador de AcaDeXI - Edicion Side Stepper (Roles no-docentes)
VersionInfoCopyright=Copyright (C) 2026 AcaDeXI Team
VersionInfoProductName=AcaDeXI Side Stepper
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
; Igual que en Docentes y Single Teacher: acadexi.db NO se instala junto al
; ejecutable. La app la crea vacía en el primer arranque y, a partir de ahí,
; sigue uno de dos caminos (ver encabezado de este archivo):
;   A) el usuario importa el paquete de configuración exportado por su
;      Director/Administrador (mismo mecanismo que el .acdx de Docentes), o
;   B) si no hay nada que importar, la app corre el wizard standalone de
;      "elige tu rol → elige tus módulos".
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
Name: "{group}\{#MyAppName} Side Stepper"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName} Side Stepper}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} Side Stepper"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; HKCU (no HKLM): PrivilegesRequired=lowest no tiene permiso de escribir en
; HKLM. Esta clave cumple DOS funciones: registro informativo en "Agregar
; o quitar programas" Y, sobre todo, es el GANCHO que
; main.py.edicion_actual() usa para reconocer esta edición como
; "side_stepper" (ver Pieza 1 del prompt de arquitectura de las 4
; ediciones). La distinción entre variante A/B NO vive aquí — es un dato
; que la propia app determina al primer arranque (¿hay paquete para
; importar o no?), no algo que el instalador necesite saber.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName} Side Stepper {#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\AcaDeXI_SideStepper"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"

; Autoarranque opcional (solo si el usuario marcó la tarea "autostart" de
; arriba). ValueName distinto al de las otras ediciones para que, si alguien
; llega a tener varias instaladas en la misma cuenta de Windows (pruebas),
; ninguna pise la entrada de autoarranque de otra.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}_SideStepper"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

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
    NombreChica := 'badgesmall_sidestepper_dark.bmp';
  end
  else
  begin
    NombreGrande := 'wizardimage_light.bmp';
    NombreChica := 'badgesmall_sidestepper_light.bmp';
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
      'AcaDeXI Side Stepper ya está instalado',
      '¿Qué deseas hacer?',
      'Se detectó una instalación existente de AcaDeXI Side Stepper en este equipo. ' +
      'Elige una opción y haz clic en Siguiente.',
      True, False);
    PaginaModo.Add('Reparar / Reinstalar (mantiene tu configuración y tus datos)');
    PaginaModo.Add('Desinstalar AcaDeXI Side Stepper');
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
        MsgBox('AcaDeXI Side Stepper se desinstaló correctamente.', mbInformation, MB_OK)
      else
        MsgBox('No se pudo ejecutar el desinstalador. Puedes desinstalar AcaDeXI ' +
               'Side Stepper manualmente desde Configuración > Aplicaciones de Windows.',
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
    // WizardSilent() evita este aviso en despliegues /SILENT o /VERYSILENT
    // (relevante sobre todo para la variante A: un Director podría desplegar
    // esto a varios equipos de golpe).
    if not WizardSilent() then
      MsgBox('AcaDeXI Side Stepper se instaló correctamente.' + #13#10 + #13#10 +
        'Al abrir la app por primera vez:' + #13#10 +
        ' - Si tu Director/Administrador te entregó un paquete de ' +
        'configuración, impórtalo desde la pantalla de inicio de sesión.' + #13#10 +
        ' - Si no tienes ningún paquete, la app te guiará para elegir tu ' +
        'rol y los módulos que quieres activar.' + #13#10 + #13#10 +
        'Nota: al cerrar la ventana con la "X", AcaDeXI sigue ejecutándose en ' +
        'segundo plano (icono junto al reloj de Windows) para no perder tu ' +
        'sesión. Puedes desactivar esto en Configuración > Apariencia, o cerrar ' +
        'la app por completo con clic derecho en ese icono > Salir.',
        mbInformation, MB_OK);
  end;
end;
