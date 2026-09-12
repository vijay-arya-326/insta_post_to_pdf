Option Explicit
Dim fso, sh, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
bat = fso.GetParentFolderName(WScript.ScriptFullName) & "\start-insta-post-to-pdf.bat"
If Not fso.FileExists(bat) Then
  WScript.Quit 1
End If
' Window style 0 = hidden, do not wait
sh.Run """" & bat & """", 0, False
