' DeepSeek Whale — launch the floating pet with no console window, on any machine.
'
' Why a .vbs and not a shortcut: Windows hands .lnk targets to whatever terminal
' app is the default, so a console can appear — and closing that console kills
' the pet, because the pet is its child. WScript.Shell.Run with window style 0
' starts it detached and hidden: no window, nothing to close by accident.
'
' Double-click this file. First run needs Python 3.11+ with PyQt6 installed
' (see README).

Option Explicit

Dim fso, sh, here, app, pyw, candidates, i

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
app  = fso.BuildPath(here, "whale-qt.pyw")

If Not fso.FileExists(app) Then
  MsgBox "whale-qt.pyw was not found next to start.vbs." & vbCrLf & _
         "Keep the whole folder together.", 16, "DeepSeek Whale"
  WScript.Quit 1
End If

' Look for pythonw.exe: PATH first, then the usual per-user install locations.
candidates = Array( _
  "pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe", _
  "C:\Python313\pythonw.exe", _
  "C:\Python312\pythonw.exe", _
  "C:\Python311\pythonw.exe")

pyw = ""
For i = 0 To UBound(candidates)
  If pyw = "" Then
    If InStr(candidates(i), "\") = 0 Then
      pyw = candidates(i)                       ' bare name: let the shell resolve via PATH
    ElseIf fso.FileExists(candidates(i)) Then
      pyw = candidates(i)
    End If
  End If
Next

If pyw = "" Then
  MsgBox "Could not find pythonw.exe." & vbCrLf & vbCrLf & _
         "Install Python 3.11 or newer and tick ""Add python.exe to PATH""," & vbCrLf & _
         "then run:    pip install PyQt6", 16, "DeepSeek Whale"
  WScript.Quit 1
End If

' 0 = hidden window, False = don't wait for it to exit
sh.Run """" & pyw & """ """ & app & """", 0, False
WScript.Quit 0
