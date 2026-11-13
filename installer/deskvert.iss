; Inno Setup script for Deskvert. Built by tools\build_release.ps1.
; Installs per user (no admin rights needed) into %LOCALAPPDATA%\Programs\Deskvert.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6D3B7E2A-4C1F-4B8E-9A57-2F1C0D9E7A31}
AppName=Deskvert
AppVersion={#AppVersion}
AppVerName=Deskvert {#AppVersion}
AppPublisher=Deskvert
AppPublisherURL=https://github.com/syedtaj7/DeskVert
AppSupportURL=https://github.com/syedtaj7/DeskVert/issues
AppUpdatesURL=https://github.com/syedtaj7/DeskVert/releases
; Product name and version inside Setup itself (code signing checks these)
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Deskvert
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=Deskvert
VersionInfoDescription=Deskvert Setup
DefaultDirName={localappdata}\Programs\Deskvert
DefaultGroupName=Deskvert
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=Deskvert-Setup-{#AppVersion}
SetupIconFile=..\assets\deskvert.ico
UninstallDisplayIcon={app}\Deskvert.exe
UninstallDisplayName=Deskvert
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Deskvert is a tray app that's nearly always running: Setup and the uninstaller close it
; themselves (see [Code]) instead of asking the user to quit it first.
CloseApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Deskvert\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Deskvert was called Tapshift until 1.14: updating removes the old program file and shortcuts
; (same AppId, so it installs over the old copy; settings are carried over by the app itself).
Type: files; Name: "{app}\Tapshift.exe"
Type: files; Name: "{userprograms}\Tapshift.lnk"
Type: files; Name: "{userprograms}\Uninstall Tapshift.lnk"
Type: files; Name: "{userdesktop}\Tapshift.lnk"

[Icons]
Name: "{userprograms}\Deskvert"; Filename: "{app}\Deskvert.exe"
Name: "{userprograms}\Uninstall Deskvert"; Filename: "{uninstallexe}"; Comment: "Remove Deskvert from this PC"
Name: "{userdesktop}\Deskvert"; Filename: "{app}\Deskvert.exe"; Tasks: desktopicon

[Registry]
; Deskvert adds itself to start-up when you choose "Start with Windows". Remove that on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Deskvert"; Flags: uninsdeletevalue dontcreatekey
; Start-up entry left by early development builds (named File Formatter then).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "FileFormatter"; Flags: uninsdeletevalue dontcreatekey

; The right-click "Convert with Deskvert" entry (Deskvert adds it while running).
Root: HKCU; Subkey: "Software\Classes\*\shell\Deskvert"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Deskvert"; Flags: uninsdeletekey dontcreatekey
; Entries from before the rename (the app moves them over itself; these catch any left behind).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Tapshift"; Flags: uninsdeletevalue dontcreatekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Tapshift"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Tapshift"; Flags: uninsdeletekey dontcreatekey

[UninstallDelete]
; Settings, logs and scratch space: nothing of Deskvert stays behind.
Type: filesandordirs; Name: "{userappdata}\Deskvert"
Type: filesandordirs; Name: "{localappdata}\Deskvert"
Type: filesandordirs; Name: "{app}"
; The "Send to" entry Deskvert adds while running.
Type: files; Name: "{userappdata}\Microsoft\Windows\SendTo\Deskvert.lnk"
; The same, from before the rename (Tapshift).
Type: filesandordirs; Name: "{userappdata}\Tapshift"
Type: filesandordirs; Name: "{localappdata}\Tapshift"
Type: files; Name: "{userappdata}\Microsoft\Windows\SendTo\Tapshift.lnk"

[Run]
Filename: "{app}\Deskvert.exe"; Description: "Start Deskvert now"; Flags: nowait postinstall skipifsilent
; In-app updates run Setup quietly with /RELAUNCH: open the new version when it's done.
Filename: "{app}\Deskvert.exe"; Flags: nowait runasoriginaluser; Check: RelaunchAfterUpdate

[Code]
// Close Deskvert (the tray app and any conversion workers) so its files can be replaced or removed.
procedure StopDeskvert();
var
  Code: Integer;
begin
  // Tapshift.exe: the same app from before the rename, when this Setup updates it
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Deskvert.exe /IM Tapshift.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopDeskvert();
  Result := '';
end;

function RelaunchAfterUpdate(): Boolean;
begin
  Result := WizardSilent() and (Pos('/RELAUNCH', Uppercase(GetCmdTail())) > 0);
end;

function InitializeUninstall(): Boolean;
begin
  StopDeskvert();
  Result := True;
end;
