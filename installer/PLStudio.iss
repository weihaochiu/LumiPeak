#ifndef AppVersion
  #define AppVersion "0.5.1"
#endif

[Setup]
AppId={{8237176B-E040-4B62-96E2-2AB4AF5FC01D}
AppName=PL Studio
AppVersion={#AppVersion}
AppPublisher=PL Studio contributors
DefaultDirName={localappdata}\Programs\PL Studio
DefaultGroupName=PL Studio
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=PL-Studio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\PL-Studio.exe
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesetraditional"; MessagesFile: "ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PL-Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PL Studio"; Filename: "{app}\PL-Studio.exe"
Name: "{autodesktop}\PL Studio"; Filename: "{app}\PL-Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PL-Studio.exe"; Description: "{cm:LaunchProgram,PL Studio}"; Flags: nowait postinstall skipifsilent
