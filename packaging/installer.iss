; Windows installer for LPARC Photo (Inno Setup 6).
; Build after PyInstaller:  ISCC.exe /DAppVersion=2.2.0 packaging\installer.iss
; Running a newer installer over an existing install upgrades it in place: the AppId below
; identifies the app to Windows and must never change.

#define AppName "LPARC Photo"
#define AppExe "LPARC Photo.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F4C2B1E-6D3A-4E57-9C21-5B7A0D9E3F64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LPARC
AppPublisherURL=https://lparc-photo.yibe.studio
AppSupportURL=https://github.com/kkonkobo/lparc-photo/issues
VersionInfoVersion={#AppVersion}
; Per-user by default, so no administrator password is needed on locked-down office PCs.
; An administrator can choose "all users" in the first dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=LPARC-Photo-windows-x64-setup
SetupIconFile=..\src\lparc_photo\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
; Upgrading while the app is open: ask to close it, do not relaunch it behind the user's back.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Files of the previous version that the new one no longer ships must not linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\LPARC Photo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
