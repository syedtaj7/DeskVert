; Inno Setup script for Tapshift. Built by tools\build_release.ps1.
; Installs per user (no admin rights needed) into %LOCALAPPDATA%\Programs\Tapshift.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6D3B7E2A-4C1F-4B8E-9A57-2F1C0D9E7A31}
AppName=Tapshift
AppVersion={#AppVersion}
AppVerName=Tapshift {#AppVersion}
AppPublisher=Tapshift
AppPublisherURL=https://github.com/syedtaj7/TapShift
AppSupportURL=https://github.com/syedtaj7/TapShift/issues
AppUpdatesURL=https://github.com/syedtaj7/TapShift/releases
DefaultDirName={localappdata}\Programs\Tapshift
DefaultGroupName=Tapshift
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=Tapshift-Setup-{#AppVersion}
SetupIconFile=..\assets\tapshift.ico
UninstallDisplayIcon={app}\Tapshift.exe
UninstallDisplayName=Tapshift
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Ask to close a running Tapshift before installing or uninstalling.
AppMutex=Local\Tapshift.SingleInstance
CloseApplications=yes
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Tapshift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Tapshift"; Filename: "{app}\Tapshift.exe"
Name: "{userdesktop}\Tapshift"; Filename: "{app}\Tapshift.exe"; Tasks: desktopicon

[Registry]
; Tapshift adds itself to start-up when you choose "Start with Windows". Remove that on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Tapshift"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Tapshift.exe"; Description: "Start Tapshift now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Tapshift.exe /F"; Flags: runhidden; RunOnceId: "StopTapshift"
