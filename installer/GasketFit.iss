#ifndef AppVersion
  #define AppVersion "0.62.0"
#endif
#ifndef AppSource
  #define AppSource "..\dist\v" + AppVersion + "\GasketFit"
#endif
#ifndef AppDataFolder
  #define AppDataFolder "{localappdata}\GasketFit"
#endif
#ifndef SetupAppId
  #define SetupAppId "{{8AB76F21-1C2D-47F8-BE80-CE5EF431A6CD}"
#endif
#ifndef OutputName
  #define OutputName "GasketFit-" + AppVersion + "-Windows-x64-Setup"
#endif

[Setup]
AppId={#SetupAppId}
AppName=GasketFit Beta
AppVersion={#AppVersion}
AppPublisher=PFDhub
AppPublisherURL=https://www.pfdhub.com
DefaultDirName={localappdata}\Programs\GasketFit
DefaultGroupName=GasketFit Beta
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename={#OutputName}
SetupIconFile=..\gasketfit\assets\icon.ico
UninstallDisplayIcon={app}\GasketFit.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.KeepSettings=Keep your GasketFit settings for a later installation?%n%nYes: keep settings, languages and cache.%nNo: delete these application data.%nYour projects and exports outside the application data folder are kept.
german.KeepSettings=GasketFit-Einstellungen für eine spätere Installation behalten?%n%nJa: Einstellungen, Sprachen und Cache behalten.%nNein: Diese Anwendungsdaten löschen.%nProjekte und Exporte außerhalb des Anwendungsdatenordners bleiben erhalten.
french.KeepSettings=Conserver vos paramètres GasketFit pour une installation ultérieure ?%n%nOui : conserver paramètres, langues et cache.%nNon : supprimer ces données de l'application.%nLes projets et exports hors du dossier de données sont conservés.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Excludes: "portable.flag,installed.flag,settings.json,cache\*,updates\*,lang\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed.flag"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\GasketFit Beta"; Filename: "{app}\GasketFit.exe"; AppUserModelID: "PFDhub.GasketFit.Beta"
Name: "{userdesktop}\GasketFit Beta"; Filename: "{app}\GasketFit.exe"; Tasks: desktopicon; AppUserModelID: "PFDhub.GasketFit.Beta"

[Run]
Filename: "{app}\GasketFit.exe"; Description: "{cm:LaunchProgram,GasketFit Beta}"; Flags: nowait postinstall skipifsilent

[Code]
var RemoveSettings: Boolean;

function InitializeUninstall(): Boolean;
begin
  RemoveSettings := False;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var DataPath: String;
begin
  if CurUninstallStep = usUninstall then begin
    { Silent uninstall always keeps user data; never infer consent to delete. }
    if not UninstallSilent then
      RemoveSettings := SuppressibleMsgBox(CustomMessage('KeepSettings'), mbConfirmation,
        MB_YESNO or MB_DEFBUTTON1, IDYES) = IDNO;
#ifdef UninstallTestMode
    { Test-only build, with an isolated AppDataFolder and separate AppId. }
    RemoveSettings := Pos('/TEST-REMOVE-SETTINGS', Uppercase(GetCmdTail)) > 0;
#endif
  end;
  if (CurUninstallStep = usPostUninstall) and RemoveSettings then begin
    DataPath := ExpandConstant('{#AppDataFolder}');
    { Fixed application-owned data directory only; never touch project paths. }
    if CompareText(ExtractFileName(DataPath), 'GasketFit') = 0 then
      DelTree(DataPath, True, True, True);
  end;
end;
