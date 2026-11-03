' Run any wsl.exe command without flashing a console window.
'
' Usage (from PowerShell, CMD, or a Task Scheduler action):
'   wslc -d Ubuntu-24.04 -u root -- bash -lc "docker ps"
'   wslc -d Ubuntu-24.04 -- echo hello
'
' Put this directory on PATH, or call it by full path. "wslc" = wsl console.
'
' WHY
' ---
' Invoking wsl.exe directly from a scheduled task, a shortcut, or a script that
' is not attached to a console opens a visible console window every single time.
' On a desktop machine that is intrusive, and when the task fires once a minute
' it flickers constantly.
'
' This wrapper uses WScript.Shell.Run with window style 0 (hidden). A hidden
' window has no console attached, so its output does not reach the caller;
' --redirect / --redirect-err capture it to files that the caller then echoes.
'
' FLAGS (consumed before the wsl arguments)
'   --no-wait        fire and forget; do not wait for wsl.exe to exit
'   --redirect PATH  write stdout to PATH
'   --redirect-err P write stderr to PATH

Option Explicit

Dim args, cmd, i, wait, outPath, errPath, sh, rc, fso, outFile, errFile

Set args = WScript.Arguments
Set sh = CreateObject("WScript.Shell")

If args.Count = 0 Then
    WScript.Echo "usage: wslc.vbs [--no-wait] [--redirect PATH] [--redirect-err PATH] <wsl arguments...>"
    WScript.Quit 2
End If

wait = True
outPath = ""
errPath = ""

i = 0
Do While i < args.Count
    Select Case args(i)
        Case "--no-wait"
            wait = False
        Case "--redirect"
            i = i + 1
            If i < args.Count Then outPath = args(i)
        Case "--redirect-err"
            i = i + 1
            If i < args.Count Then errPath = args(i)
        Case "--"
            i = i + 1
            Exit Do
        Case Else
            Exit Do
    End Select
    i = i + 1
Loop

' Rebuild the command line, quoting anything that contains a space.
Dim quoted
quoted = ""
Do While i < args.Count
    If quoted <> "" Then quoted = quoted & " "
    If InStr(args(i), " ") > 0 Or InStr(args(i), """") > 0 Then
        quoted = quoted & """" & Replace(args(i), """", """""") & """"
    Else
        quoted = quoted & args(i)
    End If
    i = i + 1
Loop

cmd = "C:\Windows\System32\wsl.exe " & quoted

' A hidden window cannot redirect its own output, so wrap the command in a
' shell that writes stdout and stderr to the requested files.
If outPath <> "" Or errPath <> "" Then
    Dim redir
    redir = ""
    If outPath <> "" Then redir = redir & " > """ & outPath & """"
    If errPath <> "" Then redir = redir & " 2> """ & errPath & """"
    cmd = "cmd.exe /c """ & cmd & redir & """"
End If

' 0 = hidden window. The last argument is bWaitOnReturn.
If wait Then
    rc = sh.Run(cmd, 0, True)
Else
    sh.Run cmd, 0, False
    rc = 0
End If

WScript.Quit rc
