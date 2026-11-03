' Hold the Ubuntu-24.04 distro open without flashing a console window.
'
' Why a VBS wrapper instead of calling wsl.exe directly:
'   Invoking wsl.exe from a launcher that has no console (Task Scheduler, a
'   shortcut, a background script) opens a visible console window every single
'   time. WScript.Shell.Run with window style 0 runs it hidden.
'
' WHY THERE IS NO WScript.Echo AT THE END
'   This script used to finish with `WScript.Echo "keepalive holder exited..."`.
'   Under wscript.exe, Echo is not a console write - it opens a MODAL MESSAGE
'   BOX. The holder only exits when the distro restarts, and the scheduled task
'   fires every minute, so every restart left a dialog on screen that had to be
'   dismissed by hand. Errors now go to a log file instead.
'
' NOTE: this holder is redundant with the in-distro systemd unit
'   wsl-keepalive.service (ExecStart=/bin/sleep infinity). The systemd unit
'   survives distro restarts on its own, so prefer it and leave the scheduled
'   task disabled unless systemd is unavailable.

Option Explicit

Dim shell, cmd, rc, fso, logPath, logFile

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

cmd = "C:\Windows\System32\wsl.exe -d Ubuntu-24.04 -u root -- bash -c ""while true; do sleep 3600; done"""

' 0 = hidden window, True = wait for the process to exit
rc = shell.Run(cmd, 0, True)

' Never Echo here: a non-zero rc under wscript.exe becomes a blocking dialog.
If rc <> 0 Then
    On Error Resume Next
    logPath = shell.ExpandEnvironmentStrings("%TEMP%") & "\wsl_keepalive.log"
    Set logFile = fso.OpenTextFile(logPath, 8, True)
    logFile.WriteLine Now & "  holder exited with code " & rc
    logFile.Close
    On Error GoTo 0
End If

WScript.Quit rc
