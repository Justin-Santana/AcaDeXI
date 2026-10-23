; ============================================================
; AcaDeXI.iss — Instalador para ADMINISTRADOR/DIRECTOR
; ============================================================
; Instala la aplicación completa. La primera vez que se ejecuta, AcaDeXI crea
; su propia base de datos vacía (con el Wizard de Configuración Inicial) en
; %APPDATA%\AcaDeXI\acadexi.db — por eso acadexi.db NO se incluye aquí.
;
; Desde la app, Configuración → Seguridad y Backups permite:
;   - Guardar una "BD Base Institucional" (sin tus datos personales) para
;     distribuir a Docentes/Personal.
;   - Exportar paquetes de instalación pre-configurados (ZIP).
;   - Exportar el instalador para Docentes/Personal (AcaDeXI_Docentes_Setup.exe,
;     compilado aparte a partir de AcaDeXI_Docentes.iss — ver ese archivo).
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
#define ImgBadgeLight FindAsset("badgesmall_institucional_light.bmp")
#define ImgBadgeDark FindAsset("badgesmall_institucional_dark.bmp")


[Setup]
AppId={{B4C6D8E0-2345-6789-ABCD-EF0123456789}
; Mismo nombre que el candado QSharedMemory de main.py
; (GuardaInstanciaUnica / _ID_INSTANCIA_UNICA). Con esto, si AcaDeXI está
; corriendo (aunque sea minimizado a la bandeja) cuando se lanza este
; instalador, Inno Setup lo detecta automáticamente y le pide al usuario
; cerrarlo antes de continuar, en vez de intentar sobrescribir un .exe
; bloqueado por Windows (lo que podría dejar la instalación a medias o
; corrupta).
AppMutex=AcaDeXI-instancia-unica-a3f9c2
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Muestra la versión en el título de cada página del wizard, ej:
; "AcaDeXI 1.0.0 Setup" en vez de solo "AcaDeXI Setup".
AppVerName={#MyAppName} {#MyAppVersion} (Institucional)
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=output
OutputBaseFilename=AcaDeXI_{#MyAppVersion}_Setup
SetupIconFile={#IconSetup}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Wizard más grande/moderno (por defecto Inno Setup usa un tamaño pequeño
; heredado de versiones antiguas; esto lo hace lucir a la altura de
; instaladores actuales).
WizardResizable=yes
WizardSizePercent=120
WizardImageFile={#ImgWizardLight}
WizardSmallImageFile={#ImgBadgeLight}
LicenseFile=_internal\terminos.txt
; Muestra explícitamente la página de selección de idioma al arrancar el
; instalador (antes dependía del comportamiento por defecto de Inno Setup,
; que la omite si detecta el idioma de Windows). Con esto el usuario SIEMPRE
; puede elegir entre español/inglés/portugués aunque coincida con su Windows.
ShowLanguageDialog=yes
PrivilegesRequired=admin
; ------------------------------------------------------------------
; FIRMA DIGITAL (AUTHENTICODE) — pendiente hasta tener un certificado
; ------------------------------------------------------------------
; Sin firmar, Windows SmartScreen mostrará "Editor desconocido" al abrir
; AcaDeXI.exe o el instalador, lo que asusta a usuarios nuevos. Para
; activarlo, necesitas comprar un certificado de firma de código (EV o
; estándar) de una autoridad certificadora (DigiCert, Sectigo, SSL.com...):
; requiere validar tu identidad/empresa, toma días y no se puede automatizar
; desde aquí. Una vez lo tengas instalado en tu máquina o token USB (los EV
; suelen venir en un token físico):
;   1) Descomenta la línea SignTool de abajo.
;   2) Define esa herramienta de firma en Inno Setup (Tools > Configure
;      Sign Tools) con un comando como:
;      signtool sign /f "C:\ruta\certificado.pfx" /p "contraseña" /fd sha256
;      /tr http://timestamp.digicert.com /td sha256 $f
;      (si el certificado es EV en token USB, se usa /a en vez de /f /p).
;   3) Compila: Inno Setup firmará automáticamente AcaDeXI_Setup.exe de
;      salida Y su desinstalador (SignedUninstaller=yes).
;SignTool=signtool
;SignedUninstaller=yes
ArchitecturesAllowed=x64 x86
ArchitecturesInstallIn64BitMode=x64
VersionInfoVersion=1.0.0.0
VersionInfoCompany=AcaDeXI Team
VersionInfoDescription=Instalador de AcaDeXI - Sistema de Gestión Escolar (Admin/Director)
VersionInfoCopyright=Copyright (C) 2026 AcaDeXI Team
VersionInfoProductName=AcaDeXI
VersionInfoTextVersion=1.0.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1
; Opcional, al estilo Discord/Spotify: iniciar AcaDeXI automáticamente junto
; con Windows (minimizado a la bandeja, ver AutoStart abajo). Desmarcado por
; defecto para no sorprender al usuario; si no lo quieres, borra esta línea
; y la sección [Registry] de autoarranque más abajo.
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
; Si ya tienes compilado el instalador para Docentes/Personal, colócalo junto
; a este .iss (o edita esta línea con la ruta real) para que quede disponible
; en la carpeta de instalación y la app pueda "Exportar Instalador para
; Docentes/Personal" desde Configuración → Seguridad y Backups.
Source: "AcaDeXI_Docentes_Setup.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; NOTA: acadexi.db NO se instala junto al ejecutable. La app la crea
; automáticamente (vacía, con sus tablas y el wizard de configuración inicial)
; en %APPDATA%\AcaDeXI\acadexi.db la primera vez que se ejecuta, que es
; una carpeta con permisos de escritura garantizados. Si se instalara en
; {app} (típicamente "C:\Program Files\..."), SQLite no podría escribir ahí
; sin privilegios de administrador.
;
; El Administrador/Director puede, desde la app (Configuración → Seguridad y
; Backups):
;   1) Guardar una "BD Base Institucional" (estructura sin sus datos personales).
;   2) Generar el perfil .acdx de cada Docente/Personal con esa BD Base y su
;      contraseña incluidas (Usuarios y Roles → Generar Perfil).
;   3) Exportar el instalador para Docentes/Personal (AcaDeXI_Docentes_Setup.exe)
;      y entregarlo junto con el .acdx de cada persona. Con eso, cada persona
;      solo necesita instalar e importar su .acdx: no hace falta ningún otro
;      archivo.

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Registrar la aplicación en el registro de Windows para que aparezca en
; "Agregar o quitar programas" con información adicional
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName} {#MyAppVersion}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "HelpLink"; ValueData: "{#MyAppURL}/soporte"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"

; Autoarranque opcional (solo si el usuario marcó la tarea "autostart" de
; arriba). Se guarda en HKCU (no requiere admin) y se elimina solo si el
; usuario desmarca la tarea al reinstalar; el desinstalador la borra siempre.
; ValueName distinto al del instalador de Docentes/Personal (AcaDeXI_Docentes)
; para que, si alguien llega a tener ambas instalaciones en la misma cuenta
; de Windows (p. ej. para pruebas), una no pise la entrada de autoarranque
; de la otra.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

; NOTA SOBRE EL CÓDIGO [Code] ORIGINAL DE ESTE SCRIPT:
; La versión anterior de este .iss traía una página de wizard personalizada
; (nombre de institución, correo, módulos a activar) que escribía esos valores
; en un config.json dentro de %APPDATA%\AcaDeXI. Se quitó porque:
;   1) Tenía dos bugs de compilación: usaba las funciones BoolToStr/
;      SaveStringToFile ANTES de declararlas (Pascal Script exige declarar
;      antes de usar), y ademas redeclaraba SaveStringToFile, que ya es una
;      funcion incorporada de Inno Setup (choca con la del compilador).
;   2) Aunque compilara, esos valores nunca se leian: main.py.load_config()
;      solo reconoce las claves theme, modo_oscuro, requerir_login,
;      recordar_usuario, ultimo_usuario, login_translucido, modo_trabajo,
;      carpeta_sincronizacion, sync_ultimo_hash y sync_ultima_fecha — es decir,
;      "institucion", "correo" y "modulos" se escribian pero no hacian nada.
; Ese tipo de configuracion (nombre de institucion, modulos activos, etc.) ya
; se define dentro de la app, en el Wizard de Configuracion Inicial la primera
; vez que se ejecuta, asi que no hace falta pedirla tambien en el instalador.
; Si en el futuro quieres una pagina asi, hay que: declarar las funciones
; ANTES de usarlas (o con "forward"), no reutilizar nombres de funciones
; incorporadas, y hacer que main.py realmente lea esas claves de config.json.

[Code]
; ============================================================
; PÁGINA "REPARAR / DESINSTALAR" cuando AcaDeXI ya está instalado
; ============================================================
; Inno Setup no trae esto por defecto (a diferencia de un instalador MSI).
; Detectamos una instalación previa buscando su desinstalador (unins000.exe,
; el nombre que Inno Setup le da siempre por defecto) dentro de la carpeta de
; instalación por defecto ({app}). Si existe, insertamos una página justo
; después de la bienvenida con dos opciones:
;   - Reparar/Reinstalar: deja que el asistente siga su curso normal. Como
;     todos los archivos en [Files] usan Flags: ignoreversion, se sobrescriben
;     igual sin importar la versión — eso YA actúa como una reparación.
;   - Desinstalar: ejecuta el desinstalador existente en modo silencioso y
;     cierra este instalador sin instalar nada.
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
    NombreChica := 'badgesmall_institucional_dark.bmp';
  end
  else
  begin
    NombreGrande := 'wizardimage_light.bmp';
    NombreChica := 'badgesmall_institucional_light.bmp';
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
    // Si eligió Reparar/Reinstalar, Result queda True y el asistente sigue
    // su curso normal (licencia, carpeta, tareas, instalación).
  end;
end;
