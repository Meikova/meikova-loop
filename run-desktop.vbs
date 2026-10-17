Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

exe = scriptDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(exe) Then
    exe = "pythonw.exe"
End If

WshShell.Run """" & exe & """ -m loopbox.desktop", 0, False
