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

StartDictation(showWindow := false)
{
    global dictationLauncher, projectDir

    args := showWindow ? " --show-window" : ""
    Run Format('"{1}"{2}', dictationLauncher, args), projectDir
}

CanRestoreWindow(hwnd)
{
    global dictationTitle

    if !hwnd
        return false
    try
    {
        if !WinExist("ahk_id " hwnd)
            return false
        if WinGetTitle("ahk_id " hwnd) == dictationTitle
            return false
        return true
    }
    catch
    {
        return false
    }
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

RestorePreviousWindow(hwnd)
{
    if !CanRestoreWindow(hwnd)
        return false

    try WinShow("ahk_id " hwnd)
    state := 0
    try state := WinGetMinMax("ahk_id " hwnd)
    if (state = -1)
        try WinRestore("ahk_id " hwnd)
    try WinActivate("ahk_id " hwnd)
    return true
}

StartOrMinimizeDictation()
{
    global dictationTitle, dictationLauncher, projectDir
    previousHwnd := WinExist("A")

    if WinExist(dictationTitle)
    {
        WinMinimize dictationTitle
        RestorePreviousWindow(previousHwnd)
        return
    }

    if IsDictationProcessRunning()
    {
        RestorePreviousWindow(previousHwnd)
        return
    }

    if !FileExist(dictationLauncher)
    {
        MsgBox "Dictation launcher not found.", "Codex Dictation", "Icon!"
        return
    }

    StartDictation(false)
    if WinWait(dictationTitle, , 8)
    {
        Sleep 800
        WinMinimize dictationTitle
    }
    RestorePreviousWindow(previousHwnd)
}

EnsureDictationRunning()
{
    global dictationTitle
    if !WinExist(dictationTitle) && !IsDictationProcessRunning()
        StartDictation(false)
}

$F1::
{
    StartOrMinimizeDictation()
}

F2::
{
    if WinExist(dictationTitle)
    {
        WinShow dictationTitle
        try WinRestore(dictationTitle)
        WinActivate dictationTitle
        return
    }

    StartDictation(true)
    if WinWait(dictationTitle, , 8)
    {
        WinShow dictationTitle
        try WinRestore(dictationTitle)
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
