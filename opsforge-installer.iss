; opsforge-installer.iss
; ------------------------
; Installateur Windows (Inno Setup) pour OpsForge, par-dessus l'exe
; portable deja construit par PyInstaller (voir opsforge.spec).
;
; Usage :
;   1. pyinstaller opsforge.spec        -> dist/OpsForge.exe
;   2. iscc opsforge-installer.iss      -> installer/OpsForge-Setup.exe
;
; Installation par utilisateur (pas besoin de droits admin / UAC) : plus
; adapte a un outil perso qu'une install machine entiere dans Program Files.

#define MyAppName "OpsForge"
#define MyAppVersion "1.0"
#define MyAppExeName "OpsForge.exe"

[Setup]
AppId={{B4E8F3F1-6E6F-4A6A-9B0A-2C6E1B8E0C21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=OpsForge-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=web\static\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis supplémentaires :"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
