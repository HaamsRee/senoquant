#define AppName "SenoQuant"
#define AppVersion ReadIni(SourcePath + "\..\..\pyproject.toml", "project", "version", "1.0.0b3")
#define AppPublisher "SenoQuant Contributors"
#define AppExe "launch_senoquant.bat"
#define SourceDir "..\\..\\dist\\windows-installer\\senoquant"
#define AppIcon AddBackslash(SourceDir) + "senoquant_icon.ico"

[Setup]
AppId={{1e18d802-2989-4c2f-8df5-66ecb8679233}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
SetupIconFile={#AppIcon}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
OutputBaseFilename=SenoQuant-Installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\senoquant_icon.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\senoquant_icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\post_install.ps1"" ""{app}"""; Flags: waituntilterminated; StatusMsg: "Setting up SenoQuant environment..."

[Code]
function IsProgramFilesPath(const Path: string): Boolean;
var
	pf: string;
	pf86: string;
begin
	pf := AddBackslash(ExpandConstant('{pf}'));
	pf86 := AddBackslash(ExpandConstant('{pf32}'));
	Result := (CompareText(Copy(Path, 1, Length(pf)), pf) = 0)
						or (CompareText(Copy(Path, 1, Length(pf86)), pf86) = 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
	Result := True;
	if CurPageID = wpSelectDir then
	begin
		if IsProgramFilesPath(WizardDirValue) then
		begin
			MsgBox(
				'SenoQuant will download models and caches at runtime. Installing under Program Files may cause permissions errors.' + #13#10 +
				'We recommend installing under your user profile (e.g., LocalAppData).',
				mbInformation,
				MB_OK
			);
		end;
	end;
end;
