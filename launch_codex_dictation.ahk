#Requires AutoHotkey v2.0
#SingleInstance Force
#UseHook True
InstallKeybdHook
DetectHiddenWindows True
SetTitleMatchMode 2

projectDir := A_ScriptDir
dictationTitle := "Codex Dictation"
dictationLauncher := projectDir "\run_codex_dictation.bat"
dictationScript := projectDir "\codex_dictation.py"
terminalWindowSpecs := [
    "ahk_exe WindowsTerminal.exe",
    "ahk_class CASCADIA_HOSTING_WINDOW_CLASS",
    "ahk_class ConsoleWindowClass",
    "ahk_exe wezterm-gui.exe",
    "ahk_exe pwsh.exe",
    "ahk_exe powershell.exe",
    "ahk_exe cmd.exe",
    "ahk_exe Code.exe",
    "ahk_exe Cursor.exe"
]

IsTerminalWindow(hwnd)
{
    global terminalWindowSpecs

    for spec in terminalWindowSpecs
    {
        for candidate in WinGetList(spec)
        {
            if candidate = hwnd
                return true
        }
    }
    return false
}

IsDictationProcessRunning()
{
    global dictationScript
    escapedScript := StrReplace(dictationScript, "\", "\\")
    query := "Select ProcessId from Win32_Process where Name='pythonw.exe' or Name='python.exe'"
    for proc in ComObjGet("winmgmts:").ExecQuery(query)
    {
        cmd := ""
        try cmd := proc.CommandLine
        if InStr(StrLower(cmd), StrLower(escapedScript)) || InStr(StrLower(cmd), StrLower(dictationScript))
            return true
    }
    return false
}

BringTerminalToFront()
{
    for hwnd in WinGetList()
    {
        if !IsTerminalWindow(hwnd)
            continue

        try WinRestore("ahk_id " hwnd)
        try WinShow("ahk_id " hwnd)
        try WinActivate("ahk_id " hwnd)
        return true
    }
    return false
}

StartOrMinimizeDictation()
{
    global dictationTitle, dictationLauncher, projectDir

    if WinExist(dictationTitle)
    {
        WinMinimize dictationTitle
        BringTerminalToFront()
        return
    }

    if IsDictationProcessRunning()
    {
        BringTerminalToFront()
        return
    }

    if !FileExist(dictationLauncher)
    {
        MsgBox "Dictation launcher not found.", "Codex Dictation", "Icon!"
        return
    }

    Run Format('"{1}"', dictationLauncher), projectDir
    if WinWait(dictationTitle, , 8)
    {
        Sleep 800
        WinMinimize dictationTitle
    }
    Sleep 150
    BringTerminalToFront()
}

EnsureDictationRunning()
{
    global dictationTitle
    if !WinExist(dictationTitle) && !IsDictationProcessRunning()
        StartOrMinimizeDictation()
}

$F1::
{
    StartOrMinimizeDictation()
}

F2::
{
    if WinExist(dictationTitle)
    {
        WinShow
        WinActivate dictationTitle
    }
}

F3::
{
    if WinExist(dictationTitle)
        WinMinimize dictationTitle
}

F4::
{
    if WinExist(dictationTitle)
        WinClose dictationTitle
}

SetTimer EnsureDictationRunning, 5000
