; installer.iss — Inno Setup script for ZDCURLCollector
[Setup]
AppName=ZDCURLCollector
AppVersion=1.0.0
AppPublisher=ZeroDayCops
DefaultDirName={autopf}\ZDCURLCollector
DefaultGroupName=ZDCURLCollector
OutputBaseFilename=ZDCURLCollector_Setup_v1.0.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output folder
Source: "dist\ZDCURLCollector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ZDCURLCollector"; Filename: "{app}\ZDCURLCollector.exe"
Name: "{autodesktop}\ZDCURLCollector"; Filename: "{app}\ZDCURLCollector.exe"; Tasks: desktopicon

[Run]
; Silent background command to download and install Playwright's Chromium browser
Filename: "{app}\ZDCURLCollector.exe"; Parameters: "--install-browsers"; StatusMsg: "Installing browser components (this may take a few minutes)..."; Flags: runhidden

; After install, open the .env file in Notepad so the user can configure their credentials
Filename: "notepad.exe"; Parameters: "{app}\.env"; Description: "Configure credentials (open .env)"; Flags: postinstall shellexec skipifsilent
