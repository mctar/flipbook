' Start Flipbook silently in the background. Used by the Startup-folder
' shortcut so the server runs at login without a console window. Logs to
' %USERPROFILE%\.tools-crm\server.log so crashes leave a trace.
Option Explicit

Dim fso, sh, scriptDir, projectRoot, userProfile, logDir, logFile, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

scriptDir   = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
userProfile = sh.ExpandEnvironmentStrings("%USERPROFILE%")
logDir      = userProfile & "\.tools-crm"
logFile     = logDir & "\server.log"

If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)

sh.CurrentDirectory = projectRoot
cmd = "cmd /c uv run uvicorn app.main:app --host 0.0.0.0 --port 8765 >> """ & logFile & """ 2>&1"

' 0 = hidden window, False = don't wait for it to finish.
sh.Run cmd, 0, False
