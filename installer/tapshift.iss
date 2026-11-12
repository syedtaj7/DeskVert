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
; Tapshift is a tray app that's nearly always running: Setup and the uninstaller close it
; themselves (see [Code]) instead of asking the user to quit it first.
CloseApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Tapshift\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Tapshift"; Filename: "{app}\Tapshift.exe"
Name: "{userprograms}\Uninstall Tapshift"; Filename: "{uninstallexe}"; Comment: "Remove Tapshift from this PC"
Name: "{userdesktop}\Tapshift"; Filename: "{app}\Tapshift.exe"; Tasks: desktopicon

[Registry]
; Tapshift adds itself to start-up when you choose "Start with Windows". Remove that on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Tapshift"; Flags: uninsdeletevalue dontcreatekey
; Start-up entry left by early development builds (named File Formatter then).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "FileFormatter"; Flags: uninsdeletevalue dontcreatekey

; The right-click "Convert with Tapshift" entry (Tapshift adds it while running).
Root: HKCU; Subkey: "Software\Classes\*\shell\Tapshift"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Tapshift"; Flags: uninsdeletekey dontcreatekey

[UninstallDelete]
; Settings, logs and scratch space: nothing of Tapshift stays behind.
Type: filesandordirs; Name: "{userappdata}\Tapshift"
Type: filesandordirs; Name: "{localappdata}\Tapshift"
Type: filesandordirs; Name: "{app}"
; The "Send to" entry Tapshift adds while running.
Type: files; Name: "{userappdata}\Microsoft\Windows\SendTo\Tapshift.lnk"

[Run]
Filename: "{app}\Tapshift.exe"; Description: "Start Tapshift now"; Flags: nowait postinstall skipifsilent
; In-app updates run Setup quietly with /RELAUNCH: open the new version when it's done.
Filename: "{app}\Tapshift.exe"; Flags: nowait runasoriginaluser; Check: RelaunchAfterUpdate

[Code]
// Close Tapshift (the tray app and any conversion workers) so its files can be replaced or removed.
procedure StopTapshift();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Tapshift.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopTapshift();
  Result := '';
end;

function RelaunchAfterUpdate(): Boolean;
begin
  Result := WizardSilent() and (Pos('/RELAUNCH', Uppercase(GetCmdTail())) > 0);
end;

function InitializeUninstall(): Boolean;
begin
  StopTapshift();
  Result := True;
end;
