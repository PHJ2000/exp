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

StartOrMinimizeDictation()
{
    global dictationTitle, dictationLauncher, projectDir

    if WinExist(dictationTitle)
    {
        WinMinimize dictationTitle
        return
    }

    if IsDictationProcessRunning()
        return

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
