from __future__ import annotations
import argparse, ctypes, difflib, json, os, queue, sys, tempfile, threading, time, traceback, urllib.error, urllib.request
from ctypes import wintypes
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import numpy as np, sounddevice as sd, soundfile as sf, tkinter as tk
from tkinter import messagebox, ttk

APP_NAME="Codex Dictation"; ROOT=Path(__file__).resolve().parent; APP_PID=os.getpid()
SETTINGS_PATH=ROOT/"codex_dictation.settings.json"; HISTORY_PATH=ROOT/"codex_dictation.history.jsonl"; LOG_PATH=ROOT/"codex_dictation.log"
AI_PREFETCH_CACHE_SIZE=3
TERMINALS={"windowsterminal.exe","wezterm-gui.exe","conhost.exe","powershell.exe","pwsh.exe","cmd.exe","mintty.exe","alacritty.exe","rio.exe","code.exe","cursor.exe"}
EXCLUDED_TARGET_PROCS={"autohotkey64.exe","shellexperiencehost.exe","dwm.exe"}
EXCLUDED_TARGET_CLASSES={"TkTopLevel","Shell_TrayWnd","Progman","WorkerW"}
INPUT_FOCUS_CLASSES={"Edit","RichEdit20A","RichEdit20W","RichEdit50W","Scintilla","Chrome_RenderWidgetHostHWND","Internet Explorer_Server"}
WEB_INPUT_PROCS={"chrome.exe","msedge.exe","brave.exe","whale.exe","firefox.exe","kakaotalk.exe","discord.exe","slack.exe","telegram.exe"}
BROWSER_FALLBACK_PROCS={"chrome.exe","msedge.exe","brave.exe","whale.exe","firefox.exe","discord.exe","slack.exe","telegram.exe"}
BROWSER_WINDOW_CLASSES={"Chrome_WidgetWin_1","MozillaWindowClass"}
WINDOWS_SEARCH_PROCS={"searchhost.exe","startmenuexperiencehost.exe","searchapp.exe"}
SYSTEM_INPUT_PROCS={"systemsettings.exe","applicationframehost.exe","explorer.exe"}
SYSTEM_INPUT_CLASSES={"ApplicationFrameWindow","Windows.UI.Core.CoreWindow","CabinetWClass","#32770","XamlExplorerHostIslandWindow"}
def _command_aliases(*values:str)->set[str]:
    out=set()
    for value in values:
        cleaned="".join(ch for ch in value.strip().lower() if ch not in " \t\r\n.,!?;:\"'")
        if cleaned: out.add(cleaned)
    return out

ENTER_COMMANDS=_command_aliases("보내","보내요","보네","보네요","보내줘","보내 줘","보내줘요","보내 줘요")
CUT_COMMANDS=_command_aliases("잘라","잘라내기","오려내기")
COPY_COMMANDS=_command_aliases("복사","복사해","복사해줘")
PASTE_COMMANDS=_command_aliases("붙여넣기","붙여 넣기","붙여넣어","붙여 넣어")
PASTE_UNDO_COMMANDS=_command_aliases("취소","붙여넣기 취소","붙여 넣기 취소","붙인 거 지워","붙인 거 취소")
REPLACE_UNDO_COMMANDS=_command_aliases("되돌려","교체 취소","바꾼 거 취소")
CLEAR_ALL_COMMANDS=_command_aliases("다 지워","다 지어","다 치워","다 지워줘","다 치워줘","전부 지워","전부 지어","전부 치워","전체 지워","전체 지어","전체 치워","모두 지워","모두 지어","모두 치워","싹 지워","싹 지어","몽땅 지워")
CLEAR_FOCUSED_INPUT_COMMANDS=_command_aliases("전체 비워","전부 비워","입력창 비워")
WINDOW_MAXIMIZE_COMMANDS=_command_aliases("최대화","창 최대화","창 크게")
WINDOW_MINIMIZE_COMMANDS=_command_aliases("최소화","창 최소화","창 작게")
WINDOW_RESTORE_COMMANDS=_command_aliases("복원","원래대로","창 복원")
ESCAPE_COMMANDS=_command_aliases("이스케이프","이스케이프 눌러","나가기","전체화면 나가기","전체 화면 나가기")
PLAY_PAUSE_COMMANDS=_command_aliases("일시정지","일시 정지","재생","재생해","재생해줘","멈춰","멈춰줘","멈춤","플레이","플레이해","플레이 해")
SEEK_FORWARD_COMMANDS=_command_aliases("앞으로 감기","앞으로감기","앞으로 감아","앞으로감아","앞으로 넘겨","앞으로넘겨")
SEEK_BACKWARD_COMMANDS=_command_aliases("뒤로 감기","뒤로감기","뒤로 감아","뒤로감아","뒤로 넘겨","뒤로넘겨")
AI_CORRECTION_COMMANDS=_command_aliases("정정","정정해","정정 해","교정","교정해","교정 해")
DELETE_SOUND_ALIASES=_command_aliases("지워","지어","치워","지워요","지어요","치워요","지워줘","지어줘","치워줘","지워줘요","치워줘요","지우","치우")
CORRECTION_PREFIXES=("다시 말해줘 ", "다시말해줘 ", "다시 말해 ", "다시말해 ", "다시 해 ", "다시해 ", "다시 ", "다시, ")
LANGUAGE_SWITCH_COMMANDS={
    **{key:"auto" for key in _command_aliases("자동","자동으로","자동 감지","자동감지","오토")},
    **{key:"ko" for key in _command_aliases("한국어","한국어로","한글","한글로")},
    **{key:"en" for key in _command_aliases("영어","영어로","잉글리시")},
}
LANGUAGE_UI_LABELS={"auto":"자동","ko":"한국어","en":"영어"}
LLM_PROFILE_MODELS={"balanced":"gemma3:4b","accurate":"gemma3:12b"}
LLM_PROFILE_UI_LABELS={"balanced":"균형","accurate":"정확도","custom":"직접지정"}
AUDIO_PRESET_UI_LABELS={"manual":"직접 조정","quiet":"조용한 방","normal":"보통","noisy":"시끄러운 방"}
DEFAULT_AUDIO_PRESET="manual"
AUDIO_PRESET_VALUES={
    "manual":{},
    "quiet":{"input_gain":1.35,"noise_gate_threshold":0.003,"voice_trigger_min_rms":0.014,"voice_trigger_ratio":2.0},
    "normal":{"input_gain":1.0,"noise_gate_threshold":0.006,"voice_trigger_min_rms":0.018,"voice_trigger_ratio":2.2},
    "noisy":{"input_gain":1.0,"noise_gate_threshold":0.012,"voice_trigger_min_rms":0.03,"voice_trigger_ratio":3.0},
}
COMMAND_PROMPT="보내 보내요 보네 보내줘 지워 지어 치워 지워요 다 지워 다 치워 전부 지워 전체 지워 모두 지워 전체 비워 전부 비워 입력창 비워 다시 다시 말해 다시 말해줘 정정 정정해 교정 복사 붙여넣기 붙여 넣기 잘라 잘라내기 취소 되돌려 자동 한국어 영어 최대화 최소화 복원 이스케이프 나가기 일시정지 재생 앞으로 감기 뒤로 감기"
SINGLE_INSTANCE_MUTEX_NAME="Local\\CodexDictationSingleton"
_single_instance_handle=None
DEFAULT_LLM_MODEL="gemma3:4b"
SLOT_NUMBER_WORDS={
    "1":1,"일":1,"하나":1,"한":1,
    "2":2,"이":2,"둘":2,"두":2,
    "3":3,"삼":3,"셋":3,"세":3,
    "4":4,"사":4,"넷":4,"네":4,
    "5":5,"오":5,"다섯":5,
    "6":6,"육":6,"여섯":6,
    "7":7,"칠":7,"일곱":7,
    "8":8,"팔":8,"여덟":8,
    "9":9,"구":9,"아홉":9,
    "10":10,"십":10,"열":10,
}
DELETE_COUNT_WORDS={
    "한":1,"하나":1,"한번":1,"한 번":1,
    "두":2,"둘":2,"두번":2,"두 번":2,
    "세":3,"셋":3,"세번":3,"세 번":3,
    "네":4,"넷":4,"네번":4,"네 번":4,
    "다섯":5,
    "여섯":6,
    "일곱":7,
    "여덟":8,
    "아홉":9,
    "열":10
}

@dataclass
class Settings:
    input_device:str=""; sample_rate:int=16000; channels:int=1; input_gain:float=1.0; audio_preset:str=DEFAULT_AUDIO_PRESET; noise_gate_threshold:float=0.0; whisper_model:str="large-v3-turbo"; whisper_device:str="auto"; whisper_compute_type:str="auto"
    language:str="auto"; initial_prompt:str=""; record_hotkey:str="f8"; always_listen_hotkey:str="f7"; paste_last_hotkey:str="f9"
    toggle_output_hotkey:str="f10"; toggle_enter_hotkey:str="f11"; output_mode:str="type"; paste_hotkey:str="ctrl+v"; auto_enter:bool=False
    trim_silence:bool=True; trim_threshold:float=0.008; normalize_whitespace:bool=True; max_record_seconds:int=45; min_record_seconds:float=0.25
    beep_feedback:bool=False; keep_window_on_top:bool=False; enable_auto_stop:bool=False; auto_stop_silence_seconds:float=0.65
    always_listen_enabled:bool=True; always_listen_preroll_seconds:float=0.25
    voice_trigger_min_rms:float=0.018; voice_trigger_ratio:float=2.2; voice_trigger_consecutive_blocks:int=2
    llm_correction_enabled:bool=False; llm_profile:str="balanced"; llm_model:str=DEFAULT_LLM_MODEL; llm_base_url:str="http://127.0.0.1:11434"; llm_timeout_seconds:float=8.0

@dataclass
class WinInfo:
    hwnd:int; pid:int; title:str; cls:str; proc:str

@dataclass
class FocusInfo:
    focus_hwnd:int; focus_cls:str; caret_hwnd:int; caret_cls:str; caret_visible:bool

@dataclass
class CorrectionTarget:
    kind:str
    source_text:str

@dataclass
class AICorrectionPrefetchEntry:
    source_text:str=""
    corrected_text:str=""
    signature:tuple[str,str,str,bool]=("", "", "", False)
    outcome:str="corrected"

@dataclass
class AICorrectionPrefetchState:
    entries:list[AICorrectionPrefetchEntry]=field(default_factory=list)
    active_source_text:str=""
    in_flight:bool=False
    job_id:int=0

CF_UNICODETEXT=13
GMEM_MOVEABLE=0x0002
CLIPBOARD_OPEN_RETRIES=20
CLIPBOARD_OPEN_DELAY=0.025

def _configure_clipboard_api():
    user32=ctypes.windll.user32
    kernel32=ctypes.windll.kernel32
    user32.OpenClipboard.argtypes=[wintypes.HWND]
    user32.OpenClipboard.restype=wintypes.BOOL
    user32.CloseClipboard.argtypes=[]
    user32.CloseClipboard.restype=wintypes.BOOL
    user32.EmptyClipboard.argtypes=[]
    user32.EmptyClipboard.restype=wintypes.BOOL
    user32.GetClipboardData.argtypes=[wintypes.UINT]
    user32.GetClipboardData.restype=wintypes.HANDLE
    user32.SetClipboardData.argtypes=[wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype=wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes=[wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype=wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes=[wintypes.HGLOBAL]
    kernel32.GlobalLock.restype=wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes=[wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype=wintypes.BOOL
    kernel32.GlobalFree.argtypes=[wintypes.HGLOBAL]
    kernel32.GlobalFree.restype=wintypes.HGLOBAL

_configure_clipboard_api()

def normalize_language_value(value:str|None)->str:
    raw=(value or "").strip().lower()
    aliases={
        "":"auto","auto":"auto","자동":"auto","자동으로":"auto","자동감지":"auto","자동 감지":"auto","오토":"auto",
        "ko":"ko","kr":"ko","한국어":"ko","한국어로":"ko","한글":"ko","한글로":"ko","korean":"ko",
        "en":"en","영어":"en","영어로":"en","english":"en","잉글리시":"en",
    }
    return aliases.get(raw,"auto")

def language_label(value:str|None)->str:
    return LANGUAGE_UI_LABELS.get(normalize_language_value(value),"자동")

def language_model_arg(value:str|None)->str|None:
    normalized=normalize_language_value(value)
    return None if normalized=="auto" else normalized

def normalize_llm_profile_value(value:str|None)->str:
    raw=(value or "").strip().lower()
    aliases={
        "balanced":"balanced","균형":"balanced",
        "accurate":"accurate","정확도":"accurate",
        "custom":"custom","직접지정":"custom","직접 지정":"custom",
    }
    return aliases.get(raw,"balanced")

def llm_profile_label(value:str|None)->str:
    return LLM_PROFILE_UI_LABELS.get(normalize_llm_profile_value(value),"균형")

def normalize_audio_preset_value(value:str|None)->str:
    raw=(value or "").strip().lower()
    aliases={
        "manual":"manual","직접":"manual","직접조정":"manual","직접 조정":"manual",
        "quiet":"quiet","조용한방":"quiet","조용한 방":"quiet",
        "normal":"normal","보통":"normal",
        "noisy":"noisy","시끄러운방":"noisy","시끄러운 방":"noisy",
    }
    return aliases.get(raw,DEFAULT_AUDIO_PRESET)

def audio_preset_label(value:str|None)->str:
    return AUDIO_PRESET_UI_LABELS.get(normalize_audio_preset_value(value),AUDIO_PRESET_UI_LABELS[DEFAULT_AUDIO_PRESET])

def resolve_llm_model(settings:Settings)->str:
    profile=normalize_llm_profile_value(settings.llm_profile)
    if profile in LLM_PROFILE_MODELS:
        return LLM_PROFILE_MODELS[profile]
    custom=(settings.llm_model or "").strip()
    return custom or DEFAULT_LLM_MODEL

def command_key(text:str)->str:
    return "".join(ch for ch in text.strip().lower() if ch not in " \t\r\n.,!?;:\"'")

def parse_language_switch_text(text:str)->str|None:
    return LANGUAGE_SWITCH_COMMANDS.get(command_key(text))

def parse_correction_text(text:str)->str:
    raw=text.strip()
    lowered=raw.lower()
    for prefix in CORRECTION_PREFIXES:
        if lowered.startswith(prefix):
            return raw[len(prefix):].strip(" \t\r\n.,!?;:\"'")
    return ""

def parse_slot_command_text(text:str)->tuple[str,int]|None:
    raw=text.strip().lower()
    compact=command_key(text)
    for token,slot in SLOT_NUMBER_WORDS.items():
        if raw in {f"{token}번 복사",f"복사 {token}번"} or compact in {f"{token}번복사",f"복사{token}번"}:
            return ("copy",slot)
        if raw in {f"{token}번 잘라",f"{token}번 잘라내기",f"잘라 {token}번"} or compact in {f"{token}번잘라",f"{token}번잘라내기",f"잘라{token}번"}:
            return ("cut",slot)
        if raw in {f"{token}번 붙여넣기",f"{token}번 붙여 넣기",f"붙여넣기 {token}번",f"붙여 넣기 {token}번"} or compact in {f"{token}번붙여넣기",f"붙여넣기{token}번"}:
            return ("paste",slot)
    return None

def parse_media_command_text(text:str)->tuple[str,int]|None:
    raw=text.strip().lower()
    compact=command_key(text)
    if compact in ESCAPE_COMMANDS:
        return ("escape",1)
    if compact in PLAY_PAUSE_COMMANDS:
        return ("play_pause",1)
    if compact in SEEK_FORWARD_COMMANDS:
        return ("forward",1)
    if compact in SEEK_BACKWARD_COMMANDS:
        return ("backward",1)
    for token,count in SLOT_NUMBER_WORDS.items():
        raw_patterns=(
            f"{token}번 앞으로 감기", f"{token} 번 앞으로 감기", f"앞으로 감기 {token}번", f"앞으로 감기 {token} 번",
            f"{token}번 앞으로 감아", f"{token} 번 앞으로 감아", f"앞으로 감아 {token}번", f"앞으로 감아 {token} 번",
            f"{token}번 뒤로 감기", f"{token} 번 뒤로 감기", f"뒤로 감기 {token}번", f"뒤로 감기 {token} 번",
            f"{token}번 뒤로 감아", f"{token} 번 뒤로 감아", f"뒤로 감아 {token}번", f"뒤로 감아 {token} 번",
        )
        compact_patterns=(
            f"{token}번앞으로감기", f"앞으로감기{token}번", f"{token}번앞으로감아", f"앞으로감아{token}번",
            f"{token}번뒤로감기", f"뒤로감기{token}번", f"{token}번뒤로감아", f"뒤로감아{token}번",
        )
        if raw in raw_patterns or compact in compact_patterns:
            if "뒤로" in raw or "뒤로" in compact:
                return ("backward",count)
            return ("forward",count)
    return None

def parse_delete_count_text(text:str)->int:
    raw=text.strip().lower()
    compact=command_key(text)
    if compact in DELETE_SOUND_ALIASES:
        return 1
    for suffix in ("번지워","번지어","번치워","개지워","개지어","개치워"):
        if compact.endswith(suffix):
            count_text=compact[:-len(suffix)]
            if count_text.isdigit():
                return max(1,int(count_text))
    for key,value in DELETE_COUNT_WORDS.items():
        for suffix in (" 번 지워"," 번 지어"," 번 치워","개 지워","개 지어","개 치워","번만 지워","번만 지어","번만 치워"):
            if raw==f"{key}{suffix}":
                return value
        for suffix in ("번지워","번지어","번치워","개지워","개지어","개치워","번만지워","번만지어","번만치워"):
            if compact==f"{key}{suffix}":
                return value
    return 0

def is_voice_command_text(text:str)->bool:
    key=command_key(text)
    if not key:
        return False
    if parse_slot_command_text(text):
        return True
    if key in ENTER_COMMANDS or key in COPY_COMMANDS or key in CUT_COMMANDS or key in PASTE_COMMANDS:
        return True
    if key in PASTE_UNDO_COMMANDS or key in REPLACE_UNDO_COMMANDS or key in CLEAR_FOCUSED_INPUT_COMMANDS or key in CLEAR_ALL_COMMANDS:
        return True
    if key in AI_CORRECTION_COMMANDS:
        return True
    if key in WINDOW_MAXIMIZE_COMMANDS or key in WINDOW_MINIMIZE_COMMANDS or key in WINDOW_RESTORE_COMMANDS:
        return True
    if parse_language_switch_text(text):
        return True
    if parse_media_command_text(text):
        return True
    if parse_delete_count_text(text):
        return True
    if parse_correction_text(text):
        return True
    return False

def conservative_postedit_prompt(text:str, language:str, strict:bool=False)->str:
    lang_note={
        "auto":"입력 언어는 한국어 또는 영어일 수 있습니다.",
        "ko":"입력 언어는 한국어입니다.",
        "en":"입력 언어는 영어입니다.",
    }.get(normalize_language_value(language),"입력 언어는 한국어 또는 영어일 수 있습니다.")
    strict_note=(
        "- 원문의 단어 순서와 문장 수를 최대한 유지합니다.\n"
        "- 새 단어를 덧붙이거나 설명을 쓰지 않습니다.\n"
        "- 확신이 없으면 한 글자도 바꾸지 않습니다.\n"
    ) if strict else ""
    return (
        "당신은 STT 후처리 교정기입니다.\n"
        f"{lang_note}\n"
        "아래 원문을 보수적으로만 교정하세요.\n"
        "규칙:\n"
        "- 띄어쓰기, 조사, 문장 부호, 명백한 오인식만 고칩니다.\n"
        "- 뜻을 추정해서 새 내용을 추가하지 않습니다.\n"
        "- 문장 수를 늘리지 않습니다.\n"
        "- 요약하거나 재서술하지 않습니다.\n"
        "- 확신이 없으면 원문을 유지합니다.\n"
        f"{strict_note}"
        "- 설명 없이 교정 결과만 한 줄로 출력합니다.\n\n"
        f"원문:\n{text}\n"
    )

def _clean_postedit_output(text:str)->str:
    cleaned=(text or "").strip()
    if "</think>" in cleaned:
        cleaned=cleaned.split("</think>",1)[-1].strip()
    if cleaned.lower().startswith("<think>"):
        cleaned=cleaned.rsplit("</think>",1)[-1].strip() if "</think>" in cleaned else ""
    cleaned=cleaned.replace("```","").strip()
    for prefix in ("교정 결과:", "결과:", "수정:", "output:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned=cleaned.split(":",1)[1].strip()
    cleaned=cleaned.splitlines()[0].strip() if cleaned.splitlines() else cleaned
    if len(cleaned)>=2 and cleaned[0]==cleaned[-1] and cleaned[0] in {"'","\""}:
        cleaned=cleaned[1:-1].strip()
    return cleaned

def short_log_text(text:str, limit:int=80)->str:
    compact=" ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit-3] + "..."

def _postedit_compare_key(text:str)->str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())

def should_accept_postedit(original:str, corrected:str)->bool:
    original_norm=normalize_text(original or "")
    corrected_norm=normalize_text(corrected or "")
    if not original_norm or not corrected_norm:
        return False
    if original_norm==corrected_norm:
        return True
    if "\n" in corrected_norm:
        return False
    original_key=_postedit_compare_key(original_norm)
    corrected_key=_postedit_compare_key(corrected_norm)
    ratio=difflib.SequenceMatcher(a=original_norm,b=corrected_norm).ratio()
    key_ratio=difflib.SequenceMatcher(a=original_key,b=corrected_key).ratio() if original_key and corrected_key else ratio
    if original_key and corrected_key and original_key==corrected_key:
        return True
    if ratio >= 0.85 and key_ratio >= 0.90:
        return True
    original_sentences=sum(original_norm.count(ch) for ch in ".!?")
    corrected_sentences=sum(corrected_norm.count(ch) for ch in ".!?")
    if corrected_sentences > original_sentences + 1:
        return False
    if ratio < 0.75 and key_ratio < 0.82:
        return False
    if len(corrected_norm) > max(len(original_norm)*2, len(original_norm)+24):
        return False
    if len(corrected_norm) < max(1, int(len(original_norm)*0.4)):
        return False
    if key_ratio < 0.68:
        return False
    return True

def postedit_similarity_metrics(original:str, corrected:str)->tuple[float,float]:
    original_norm=normalize_text(original or "")
    corrected_norm=normalize_text(corrected or "")
    ratio=difflib.SequenceMatcher(a=original_norm,b=corrected_norm).ratio()
    original_key=_postedit_compare_key(original_norm)
    corrected_key=_postedit_compare_key(corrected_norm)
    key_ratio=difflib.SequenceMatcher(a=original_key,b=corrected_key).ratio() if original_key and corrected_key else ratio
    return ratio, key_ratio

class OllamaPostEditor:
    def __init__(self, logger, status_reporter=None):
        self.log=logger
        self.report_status=status_reporter or (lambda kind, detail="": None)
    def _request(self,prompt:str,settings:Settings,trace_id:str|None=None)->str:
        trace_prefix=f"{trace_id} | " if trace_id else ""
        base_url=(settings.llm_base_url or "").strip().rstrip("/")
        if not base_url:
            self.report_status("skipped","base URL 비어 있음")
            self.log(f"{trace_prefix}LLM 교정 건너뜀: base URL 비어 있음")
            return ""
        payload={
            "model":resolve_llm_model(settings),
            "prompt":prompt,
            "stream":False,
            "options":{"temperature":0,"top_p":0.05,"num_predict":128,"repeat_penalty":1.2},
        }
        body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        req=urllib.request.Request(
            f"{base_url}/api/generate",
            data=body,
            headers={"Content-Type":"application/json"},
            method="POST",
        )
        timeout=max(float(settings.llm_timeout_seconds or 0), 0.5)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data=json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            self.report_status("connection_error",str(e))
            self.log(f"{trace_prefix}LLM 교정 건너뜀: {e}")
            return ""
        except Exception as e:
            self.report_status("request_error",str(e))
            self.log(f"{trace_prefix}LLM 교정 실패: {e}")
            return ""
        return _clean_postedit_output(data.get("response",""))
    def correct(self,text:str,settings:Settings,trace_id:str|None=None)->str:
        if not settings.llm_correction_enabled:
            self.report_status("disabled","")
            return text
        source=(text or "").strip()
        if not source:
            return text
        started=time.perf_counter()
        trace_prefix=f"{trace_id} | " if trace_id else ""
        self.report_status("request_start","")
        self.log(f"{trace_prefix}LLM 요청 시작")
        corrected=self._request(conservative_postedit_prompt(source, settings.language),settings,trace_id=trace_id)
        if not corrected:
            self.report_status("empty","")
            self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter()-started:.3f}s, empty)")
            self.log(f"{trace_prefix}LLM 빈 응답 -> 원문 유지")
            return text
        if not should_accept_postedit(source, corrected):
            self.log(f"{trace_prefix}1차 결과 거부 -> 보수 프롬프트 재시도")
            retry=self._request(conservative_postedit_prompt(source, settings.language, strict=True),settings,trace_id=trace_id)
            if retry and should_accept_postedit(source,retry):
                corrected=retry
                self.log(f"{trace_prefix}재시도 결과 채택")
            else:
                ratio, key_ratio=postedit_similarity_metrics(source, retry or corrected or source)
                self.report_status("rejected",f"ratio={ratio:.3f}, key_ratio={key_ratio:.3f}")
                self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter()-started:.3f}s, rejected)")
                self.log(f"{trace_prefix}결과 거부: diff too large (ratio={ratio:.3f}, key_ratio={key_ratio:.3f}) -> 원문 유지")
                return text
        if normalize_text(corrected)==normalize_text(source):
            self.report_status("same","")
            self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter()-started:.3f}s, same)")
            self.log(f"{trace_prefix}결과 동일 -> 원문 유지")
            return text
        self.report_status("accepted","")
        self.log(f"{trace_prefix}LLM 응답 완료 ({time.perf_counter()-started:.3f}s)")
        self.log(f"{trace_prefix}LLM 결과 채택")
        return corrected

def load_settings()->Settings:
    if not SETTINGS_PATH.exists():
        s=Settings(); save_settings(s); return s
    data=json.loads(SETTINGS_PATH.read_text(encoding="utf-8")); ok={f.name for f in Settings.__dataclass_fields__.values()}
    settings=Settings(**{k:v for k,v in data.items() if k in ok})
    settings.input_gain=max(float(settings.input_gain),0.0)
    settings.audio_preset=normalize_audio_preset_value(settings.audio_preset)
    settings.noise_gate_threshold=max(float(settings.noise_gate_threshold),0.0)
    settings.language=normalize_language_value(settings.language)
    settings.llm_profile=normalize_llm_profile_value(settings.llm_profile)
    return settings

def save_settings(settings:Settings)->None: SETTINGS_PATH.write_text(json.dumps(asdict(settings),indent=2),encoding="utf-8")
def append_app_log(msg:str)->None:
    line=f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG_PATH.open("a",encoding="utf-8") as f:
            f.write(line)
    except Exception: pass
def append_history(text:str,meta:dict)->None:
    payload={"timestamp":datetime.now().isoformat(timespec="seconds"),"text":text,**meta}
    with HISTORY_PATH.open("a",encoding="utf-8") as f: f.write(json.dumps(payload,ensure_ascii=False)+"\n")

def get_input_devices():
    out=[]
    for i,d in enumerate(sd.query_devices()):
        if int(d["max_input_channels"])>0: out.append({"index":i,"name":str(d["name"]),"sample_rate":int(d["default_samplerate"])})
    return out

def default_input_device_name():
    try:
        default_in = sd.default.device[0]
        for d in get_input_devices():
            if int(d["index"]) == int(default_in):
                return d["name"]
    except Exception:
        pass
    devs = get_input_devices()
    return devs[0]["name"] if devs else ""

def _open_clipboard_with_retry(user32)->bool:
    for _ in range(CLIPBOARD_OPEN_RETRIES):
        if user32.OpenClipboard(None):
            return True
        time.sleep(CLIPBOARD_OPEN_DELAY)
    return False

def get_clipboard_text()->str:
    user32=ctypes.windll.user32
    kernel32=ctypes.windll.kernel32
    if not _open_clipboard_with_retry(user32):
        return ""
    handle=None
    locked=None
    try:
        handle=user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked=kernel32.GlobalLock(handle)
        if not locked:
            return ""
        return ctypes.wstring_at(locked)
    except Exception:
        return ""
    finally:
        if locked:
            kernel32.GlobalUnlock(handle)
        user32.CloseClipboard()

def set_clipboard_text(text:str)->bool:
    user32=ctypes.windll.user32
    kernel32=ctypes.windll.kernel32
    data=(text or "") + "\0"
    buf_size=len(data)*ctypes.sizeof(ctypes.c_wchar)
    handle=kernel32.GlobalAlloc(GMEM_MOVEABLE, buf_size)
    if not handle:
        return False
    locked=None
    try:
        locked=kernel32.GlobalLock(handle)
        if not locked:
            return False
        ctypes.memmove(locked, ctypes.create_unicode_buffer(data), buf_size)
        kernel32.GlobalUnlock(handle)
        locked=None
        if not _open_clipboard_with_retry(user32):
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                return False
            handle=None
            return True
        finally:
            user32.CloseClipboard()
    finally:
        if locked:
            kernel32.GlobalUnlock(handle)
        if handle:
            kernel32.GlobalFree(handle)

def acquire_single_instance()->bool:
    global _single_instance_handle
    try:
        kernel32=ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle=kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
        if not handle:
            return True
        if kernel32.GetLastError()==183:
            kernel32.CloseHandle(handle)
            return False
        _single_instance_handle=handle
        return True
    except Exception:
        return True

def resolve_input_device(v):
    if v in (None,""): return None
    if isinstance(v,int): return v
    for d in get_input_devices():
        if d["name"]==v: return int(d["index"])
    try: return int(v)
    except Exception: return None

def trim_silence(audio:np.ndarray,th:float)->np.ndarray:
    if audio.size==0: return audio
    voiced=np.where(np.abs(audio)>th)[0]
    if voiced.size==0: return audio
    a=max(int(voiced[0])-1600,0); b=min(int(voiced[-1])+1600,len(audio)); return audio[a:b]

def rms_level(audio:np.ndarray)->float:
    if audio.size==0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))

def apply_input_gain(audio:np.ndarray,gain:float)->np.ndarray:
    if audio.size==0:
        return audio
    gain=max(float(gain),0.0)
    if gain==1.0:
        return audio
    return np.clip((audio*gain).astype(np.float32,copy=False),-1.0,1.0).astype(np.float32,copy=False)

def apply_noise_gate(audio:np.ndarray,threshold:float)->np.ndarray:
    if audio.size==0:
        return audio
    threshold=max(float(threshold),0.0)
    if threshold<=0.0:
        return audio
    gated=audio.copy()
    gated[np.abs(gated)<threshold]=0.0
    return gated

def normalize_text(text:str)->str: return " ".join(text.replace("\r"," ").replace("\n"," ").split()).strip()
def initial_prompt_for_commands(settings:Settings)->str:
    base=(settings.initial_prompt or "").strip()
    return f"{base} {COMMAND_PROMPT}".strip() if base else COMMAND_PROMPT
def pick_compute_type(v:str)->str:
    if v!="auto": return v
    try:
        import torch
        return "float16" if torch.cuda.is_available() else "int8"
    except Exception: return "int8"

def safe_proc(pid:int)->str:
    try:
        import psutil
        return psutil.Process(pid).name().lower()
    except Exception: return ""

def has_codex(pid:int)->bool:
    try:
        import psutil
        p=psutil.Process(pid)
        for c in [p,*p.children(recursive=True)]:
            if "codex" in " ".join([c.name(),*c.cmdline()]).lower(): return True
    except Exception: return False
    return False

def fg_info()->WinInfo|None:
    u=ctypes.windll.user32; hwnd=u.GetForegroundWindow()
    if not hwnd: return None
    n=u.GetWindowTextLengthW(hwnd); title=ctypes.create_unicode_buffer(n+1); u.GetWindowTextW(hwnd,title,n+1)
    cls=ctypes.create_unicode_buffer(256); u.GetClassNameW(hwnd,cls,256); pid=ctypes.c_ulong(); u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    return WinInfo(int(hwnd),int(pid.value),title.value,cls.value,safe_proc(int(pid.value)))

def hwnd_class(hwnd:int)->str:
    if not hwnd:
        return ""
    u=ctypes.windll.user32
    cls=ctypes.create_unicode_buffer(256)
    try:
        u.GetClassNameW(hwnd,cls,256)
        return cls.value
    except Exception:
        return ""

def fmt_info(info:WinInfo|None)->str:
    if not info: return "No active window"
    return f"{info.proc or 'unknown'} | {(info.title or '(no title)')} | {info.cls or 'unknown'} | hwnd={info.hwnd}"

def is_terminal(info:WinInfo|None)->bool:
    return bool(info and (info.proc in TERMINALS or info.cls in {"CASCADIA_HOSTING_WINDOW_CLASS","ConsoleWindowClass"} or any(x in (info.title or "").lower() for x in ["terminal","powershell","pwsh","cmd"])))

def is_codex_terminal(info:WinInfo|None)->bool:
    return bool(info and is_terminal(info) and ("codex" in info.title.lower() or has_codex(info.pid)))

def gui_focus_info(info:WinInfo|None)->FocusInfo|None:
    if not info:
        return None
    class RECT(ctypes.Structure):
        _fields_=[("left",ctypes.c_long),("top",ctypes.c_long),("right",ctypes.c_long),("bottom",ctypes.c_long)]
    class GUITHREADINFO(ctypes.Structure):
        _fields_=[
            ("cbSize",ctypes.c_ulong),
            ("flags",ctypes.c_ulong),
            ("hwndActive",ctypes.c_void_p),
            ("hwndFocus",ctypes.c_void_p),
            ("hwndCapture",ctypes.c_void_p),
            ("hwndMenuOwner",ctypes.c_void_p),
            ("hwndMoveSize",ctypes.c_void_p),
            ("hwndCaret",ctypes.c_void_p),
            ("rcCaret",RECT),
        ]
    user32=ctypes.windll.user32
    try:
        thread_id=user32.GetWindowThreadProcessId(info.hwnd,None)
        gui=GUITHREADINFO()
        gui.cbSize=ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(thread_id,ctypes.byref(gui)):
            return None
        focus_hwnd=int(gui.hwndFocus or 0)
        caret_hwnd=int(gui.hwndCaret or 0)
        caret_rect=gui.rcCaret
        caret_visible=any(int(v)!=0 for v in (caret_rect.left,caret_rect.top,caret_rect.right,caret_rect.bottom))
        return FocusInfo(focus_hwnd,hwnd_class(focus_hwnd),caret_hwnd,hwnd_class(caret_hwnd),caret_visible)
    except Exception:
        return None

def is_general_input_target(info:WinInfo|None)->bool:
    if not info:
        return False
    if info.pid==APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
        return False
    if info.proc not in WINDOWS_SEARCH_PROCS and not (info.title or "").strip() and not is_terminal(info):
        return False
    focus=gui_focus_info(info)
    if not focus:
        return False
    if info.proc in WINDOWS_SEARCH_PROCS:
        return True
    if focus.caret_hwnd or focus.caret_visible:
        return True
    if focus.focus_cls in INPUT_FOCUS_CLASSES or focus.caret_cls in INPUT_FOCUS_CLASSES:
        return True
    if info.proc in SYSTEM_INPUT_PROCS and info.cls in SYSTEM_INPUT_CLASSES:
        return True
    if info.proc in WEB_INPUT_PROCS and focus.focus_hwnd and focus.focus_hwnd != info.hwnd:
        return True
    if info.proc in BROWSER_FALLBACK_PROCS and info.cls in BROWSER_WINDOW_CLASSES:
        return True
    return False

def has_precise_text_focus(info:WinInfo|None)->bool:
    if not info:
        return False
    focus=gui_focus_info(info)
    if not focus:
        return False
    if focus.caret_hwnd or focus.caret_visible:
        return True
    return focus.focus_cls in INPUT_FOCUS_CLASSES or focus.caret_cls in INPUT_FOCUS_CLASSES

def is_target_window(info:WinInfo|None)->bool:
    return bool(info and (is_terminal(info) or is_general_input_target(info)))

def list_terminal_windows()->list[WinInfo]:
    user32=ctypes.windll.user32
    windows=[]
    enum_proc=ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            n=user32.GetWindowTextLengthW(hwnd)
            if n<=0:
                return True
            title=ctypes.create_unicode_buffer(n+1)
            user32.GetWindowTextW(hwnd,title,n+1)
            cls=ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd,cls,256)
            pid=ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            info=WinInfo(int(hwnd),int(pid.value),title.value,cls.value,safe_proc(int(pid.value)))
            if is_terminal(info):
                windows.append(info)
        except Exception:
            pass
        return True
    user32.EnumWindows(enum_proc(_cb), 0)
    return windows

def focus_window(hwnd:int)->bool:
    user32=ctypes.windll.user32
    if not hwnd:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

def focus_best_terminal()->bool:
    wins=list_terminal_windows()
    if not wins:
        return False
    return focus_window(wins[0].hwnd)

def control_window_state(info:WinInfo|None, action:str)->bool:
    if not info:
        return False
    if info.pid==APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
        return False
    user32=ctypes.windll.user32
    show_map={"maximize":3,"minimize":6,"restore":9}
    cmd=show_map.get(action)
    if cmd is None:
        return False
    try:
        user32.ShowWindow(info.hwnd, cmd)
        if action!="minimize":
            user32.SetForegroundWindow(info.hwnd)
        return True
    except Exception:
        return False

def send_media_virtual_key(vk_code:int)->bool:
    user32=ctypes.windll.user32
    KEYEVENTF_KEYUP=0x0002
    try:
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False

class WhisperBackend:
    def __init__(self): self.cache={}; self.lock=threading.Lock()
    def _model(self,s:Settings):
        from faster_whisper import WhisperModel
        device=s.whisper_device
        if device=="auto":
            try:
                import torch
                device="cuda" if torch.cuda.is_available() else "cpu"
            except Exception: device="cpu"
        key=(s.whisper_model,device,pick_compute_type(s.whisper_compute_type))
        with self.lock:
            if key not in self.cache: self.cache[key]=WhisperModel(s.whisper_model,device=device,compute_type=key[2])
            return self.cache[key]
    def transcribe(self,path:Path,s:Settings)->str:
        segs,_=self._model(s).transcribe(path.as_posix(),language=language_model_arg(s.language),initial_prompt=initial_prompt_for_commands(s),vad_filter=True,beam_size=1,best_of=1,condition_on_previous_text=False)
        return " ".join(x.text.strip() for x in segs).strip()

class Recorder:
    def __init__(self,s:Settings,log): self.s=s; self.log=log; self.stream=None; self.chunks=[]; self.lock=threading.Lock(); self.t0=0.0; self.last_voice=0.0; self.on=False; self.noise_floor=max(self.s.trim_threshold*0.8,0.003); self.last_rms=0.0; self.last_peak=0.0; self.last_threshold=0.0; self.last_voice_detected=False; self.last_updated=0.0
    def start(self):
        if self.on: return
        self.chunks=[]; self.t0=time.monotonic(); self.last_voice=self.t0; self.noise_floor=max(self.s.trim_threshold*0.8,0.003)
        self.stream=sd.InputStream(samplerate=self.s.sample_rate,channels=self.s.channels,dtype="float32",device=resolve_input_device(self.s.input_device),callback=self._cb); self.stream.start(); self.on=True; self.log("Recording started")
    def stop(self)->np.ndarray:
        if not self.on: return np.zeros(0,dtype=np.float32)
        self.stream.stop(); self.stream.close(); self.stream=None; self.on=False
        with self.lock: audio=np.concatenate(self.chunks).astype(np.float32) if self.chunks else np.zeros(0,dtype=np.float32)
        self.log(f"Recording stopped: {len(audio)/self.s.sample_rate:.2f}s"); return audio
    def duration(self)->float: return time.monotonic()-self.t0 if self.on else 0.0
    def should_stop(self)->bool: return self.on and self.s.enable_auto_stop and self.duration()>=self.s.min_record_seconds and time.monotonic()-self.last_voice>=self.s.auto_stop_silence_seconds
    def meter_snapshot(self)->tuple[float,float,float,bool,float]:
        with self.lock: return self.last_rms,self.last_peak,self.last_threshold,self.last_voice_detected,self.last_updated
    def _cb(self,indata,frames,time_info,status):
        if status: self.log(f"Audio status: {status}")
        mono=apply_input_gain(indata[:,0].copy(),self.s.input_gain)
        mono=apply_noise_gate(mono,self.s.noise_gate_threshold)
        rms=rms_level(mono)
        peak=float(np.max(np.abs(mono))) if mono.size else 0.0
        threshold=max(self.s.trim_threshold, self.s.voice_trigger_min_rms, self.noise_floor*self.s.voice_trigger_ratio)
        voice=rms>=threshold
        with self.lock:
            self.chunks.append(mono)
            self.last_rms=rms; self.last_peak=peak; self.last_threshold=threshold; self.last_voice_detected=voice; self.last_updated=time.monotonic()
        if voice:
            self.last_voice=time.monotonic()
        else:
            self.noise_floor=(self.noise_floor*0.96)+(rms*0.04)

class AlwaysListen:
    def __init__(self,s:Settings,log,on_audio,target_active): self.s=s; self.log=log; self.on_audio=on_audio; self.target_active=target_active; self.stream=None; self.on=False; self.lock=threading.Lock(); self.pre=deque(); self.pre_n=0; self.chunks=[]; self.n=0; self.last_voice=0.0; self.noise_floor=max(self.s.trim_threshold*0.8,0.003); self.voice_hits=0; self.last_rms=0.0; self.last_peak=0.0; self.last_threshold=0.0; self.last_voice_detected=False; self.last_updated=0.0
    def start(self):
        if self.on: return
        self.reset(); self.stream=sd.InputStream(samplerate=self.s.sample_rate,channels=self.s.channels,dtype="float32",device=resolve_input_device(self.s.input_device),blocksize=max(int(self.s.sample_rate*0.06),512),callback=self._cb); self.stream.start(); self.on=True; self.log("Always-listen started")
    def stop(self):
        if not self.on: return
        self.stream.stop(); self.stream.close(); self.stream=None; self.on=False; self.reset(); self.log("Always-listen stopped")
    def reset(self):
        with self.lock: self.pre.clear(); self.pre_n=0; self.chunks=[]; self.n=0; self.last_voice=0.0; self.noise_floor=max(self.s.trim_threshold*0.8,0.003); self.voice_hits=0; self.last_rms=0.0; self.last_peak=0.0; self.last_threshold=0.0; self.last_voice_detected=False; self.last_updated=0.0
    def meter_snapshot(self)->tuple[float,float,float,bool,float]:
        with self.lock: return self.last_rms,self.last_peak,self.last_threshold,self.last_voice_detected,self.last_updated
    def _push_pre(self,mono):
        self.pre.append(mono); self.pre_n+=len(mono); limit=int(self.s.sample_rate*self.s.always_listen_preroll_seconds)
        while self.pre and self.pre_n>limit: self.pre_n-=len(self.pre.popleft())
    def _finalize(self):
        if not self.chunks: return
        audio=np.concatenate(self.chunks).astype(np.float32); self.chunks=[]; self.n=0; self.last_voice=0.0; self.on_audio(audio,"always_listen")
    def _cb(self,indata,frames,time_info,status):
        if status: self.log(f"Always-listen audio status: {status}")
        mono=apply_input_gain(indata[:,0].copy(),self.s.input_gain)
        mono=apply_noise_gate(mono,self.s.noise_gate_threshold)
        if not self.target_active(): self.reset(); return
        rms=rms_level(mono)
        peak=float(np.max(np.abs(mono))) if mono.size else 0.0
        threshold=max(self.s.trim_threshold, self.s.voice_trigger_min_rms, self.noise_floor*self.s.voice_trigger_ratio)
        voice=rms>=threshold
        now=time.monotonic()
        with self.lock:
            self.last_rms=rms; self.last_peak=peak; self.last_threshold=threshold; self.last_voice_detected=voice; self.last_updated=now
            if not self.chunks:
                self._push_pre(mono)
                if voice:
                    self.voice_hits+=1
                else:
                    self.voice_hits=0
                    self.noise_floor=(self.noise_floor*0.96)+(rms*0.04)
                if self.voice_hits>=max(int(self.s.voice_trigger_consecutive_blocks),1):
                    self.chunks=list(self.pre); self.n=sum(len(x) for x in self.chunks); self.pre.clear(); self.pre_n=0; self.last_voice=now; self.voice_hits=0; self.log(f"Voice detected in target window (rms={rms:.4f}, threshold={threshold:.4f})")
            else:
                self.chunks.append(mono); self.n+=len(mono)
                if voice:
                    self.last_voice=now
                else:
                    self.noise_floor=(self.noise_floor*0.98)+(rms*0.02)
                if self.n/max(self.s.sample_rate,1)>=self.s.max_record_seconds or now-self.last_voice>=self.s.auto_stop_silence_seconds: self._finalize()

def doctor(settings:Settings|None=None)->str:
    lines=[f"{APP_NAME} doctor","-"*40,f"Python: {sys.version.split()[0]}",f"Settings: {SETTINGS_PATH}",f"History: {HISTORY_PATH}",f"Log: {LOG_PATH}"]
    if settings: lines+= [f"Always listen enabled: {settings.always_listen_enabled}",f"Audio preset: {audio_preset_label(settings.audio_preset)} ({normalize_audio_preset_value(settings.audio_preset)})",f"Input gain: {float(settings.input_gain):.2f}",f"Noise gate threshold: {float(settings.noise_gate_threshold):.4f}",f"Language: {language_label(settings.language)} ({normalize_language_value(settings.language)})",f"LLM correction enabled: {settings.llm_correction_enabled}",f"LLM profile: {llm_profile_label(settings.llm_profile)} ({normalize_llm_profile_value(settings.llm_profile)})",f"LLM model: {resolve_llm_model(settings)}",f"LLM base URL: {settings.llm_base_url}"]
    try:
        devs=get_input_devices(); lines.append(f"Input devices: {len(devs)}")
        for d in devs[:10]: lines.append(f"  - [{d['index']}] {d['name']} ({d['sample_rate']} Hz)")
    except Exception as e: lines.append(f"Input devices: failed ({e})")
    info=fg_info(); focus=gui_focus_info(info)
    lines += [f"Foreground window: {fmt_info(info)}",f"Focused child hwnd: {getattr(focus,'focus_hwnd',0)} | class={getattr(focus,'focus_cls','') or 'none'}",f"Caret hwnd: {getattr(focus,'caret_hwnd',0)} | class={getattr(focus,'caret_cls','') or 'none'} | visible={getattr(focus,'caret_visible',False)}",f"Looks like terminal: {is_terminal(info)}",f"Looks like Codex terminal: {is_codex_terminal(info)}",f"Looks like general input target: {is_general_input_target(info)}",f"Accepts as target window: {is_target_window(info)}"]
    for name,imp in [("keyboard","keyboard"),("faster-whisper","faster_whisper"),("psutil","psutil")]:
        try: __import__(imp); lines.append(f"{name}: OK")
        except Exception as e: lines.append(f"{name}: missing ({e})")
    try:
        import torch
        lines += [f"torch: {torch.__version__}",f"torch cuda available: {torch.cuda.is_available()}"]
        if torch.cuda.is_available(): lines.append(f"torch cuda device: {torch.cuda.get_device_name(0)}")
    except Exception as e: lines.append(f"torch: unavailable ({e})")
    return "\n".join(lines)

def transcribe_file(file_path:Path,settings:Settings)->str:
    text=WhisperBackend().transcribe(file_path,settings)
    text=normalize_text(text) if settings.normalize_whitespace else text
    return text

class App:
    def __init__(self,root:tk.Tk,launch_target:WinInfo|None=None,show_window:bool=False):
        self.root=root; self.root.title(APP_NAME); self.root.geometry("980x780"); self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.launch_target=launch_target
        self.show_window=show_window
        self.s=load_settings()
        if not self.s.input_device: self.s.input_device = default_input_device_name()
        save_settings(self.s)
        self.log_q=queue.Queue(); self.res_q=queue.Queue(); self.jobs=queue.Queue(); self.backend=WhisperBackend(); self.audio_status=tk.StringVar(value="Audio | waiting for input"); self.llm_status=tk.StringVar(value="LLM | 대기"); self.posteditor=OllamaPostEditor(self.log,self._set_llm_status); self.rec=Recorder(self.s,self.log); self.listen=AlwaysListen(self.s,self.log,self.enqueue_audio,self.target_active)
        self.busy=False; self.last=""; self.last_emitted=""; self.last_submitted=False; self.pending_text=""; self.pending_segments=[]; self.last_target=None; self.t=None; self.startup_minimized=False
        self.internal_buffer=""; self.buffer_slots={i:"" for i in range(1,11)}; self.last_paste_payload=""; self.last_replace_state=None
        self.ai_correction_seq=0
        self.ai_prefetch_lock=threading.Lock()
        self.ai_prefetch=AICorrectionPrefetchState()
        self.vars={k:tk.StringVar(value=str(getattr(self.s,k))) for k in ["input_device","sample_rate","input_gain","noise_gate_threshold","whisper_model","whisper_device","whisper_compute_type","initial_prompt","record_hotkey","always_listen_hotkey","paste_last_hotkey","toggle_output_hotkey","toggle_enter_hotkey","output_mode","paste_hotkey","max_record_seconds","auto_stop_silence_seconds","always_listen_preroll_seconds","llm_model","llm_base_url","llm_timeout_seconds"]}
        self.vars["audio_preset"]=tk.StringVar(value=audio_preset_label(self.s.audio_preset))
        self.vars["language"]=tk.StringVar(value=language_label(self.s.language))
        self.vars["llm_profile"]=tk.StringVar(value=llm_profile_label(self.s.llm_profile))
        self.bools={k:tk.BooleanVar(value=getattr(self.s,k)) for k in ["auto_enter","trim_silence","normalize_whitespace","beep_feedback","keep_window_on_top","enable_auto_stop","always_listen_enabled","llm_correction_enabled"]}
        self.status=tk.StringVar(value="Idle"); self.target=tk.StringVar(value="")
        self.devices=[d["name"] for d in get_input_devices()]; self._ui(); self.refresh_target(); self.refresh_status("Starting"); self._sync_llm_status_idle(); self.root.after(20,self.ensure_window_visible_on_startup); self.root.after(50,self.bootstrap_after_launch); self.root.after(80,self.poll); self.root.after(120,self.poll_record); self.root.after(120,self.poll_diagnostics); self.root.after(150,self.poll_target)
    def _ui(self):
        self.root.columnconfigure(0,weight=1); self.root.rowconfigure(3,weight=1); head=ttk.Frame(self.root,padding=12); head.grid(row=0,column=0,sticky="ew"); head.columnconfigure(1,weight=1)
        ttk.Label(head,text=APP_NAME,font=("Segoe UI",18,"bold")).grid(row=0,column=0,sticky="w"); ttk.Label(head,textvariable=self.status,font=("Segoe UI",10,"bold")).grid(row=0,column=1,sticky="e"); ttk.Label(head,textvariable=self.target).grid(row=1,column=0,columnspan=2,sticky="w",pady=(6,0)); ttk.Label(head,text="F7 항상 듣기, F8 수동 녹음, F9 마지막 문장, F10 출력 모드, F11 Enter 전환 | 음성 명령: 보내, 지워, 다 지워, 전체 비워, 다시 ..., 복사, 붙여넣기, 잘라, 취소, 되돌려, 자동/한국어/영어, 최대화/최소화/복원, 이스케이프/나가기, 일시정지/재생, 앞으로/뒤로 감기").grid(row=2,column=0,columnspan=2,sticky="w",pady=(6,0))
        ttk.Label(head,textvariable=self.audio_status,font=("Consolas",9)).grid(row=3,column=0,columnspan=2,sticky="w",pady=(8,0))
        ttk.Label(head,textvariable=self.llm_status,font=("Consolas",9)).grid(row=4,column=0,columnspan=2,sticky="w",pady=(4,0))
        top=ttk.Frame(self.root,padding=(12,0,12,0)); top.grid(row=1,column=0,sticky="nsew"); top.columnconfigure((0,1),weight=1); left=ttk.LabelFrame(top,text="Recording",padding=12); right=ttk.LabelFrame(top,text="Output, Target, Hotkeys",padding=12); left.grid(row=0,column=0,sticky="nsew",padx=(0,6)); right.grid(row=0,column=1,sticky="nsew",padx=(6,0))
        self._combo(left,"Input Device","input_device",self.devices,0); self._entry(left,"Sample Rate","sample_rate",1); self._entry(left,"Input Gain","input_gain",2); self._combo(left,"Audio Preset","audio_preset",[audio_preset_label(k) for k in AUDIO_PRESET_UI_LABELS],3); self._entry(left,"Noise Gate Threshold","noise_gate_threshold",4); self._combo(left,"Whisper Model","whisper_model",["tiny","base","small","medium","large-v3-turbo"],5); self._combo(left,"Whisper Device","whisper_device",["auto","cpu","cuda"],6); self._combo(left,"Compute Type","whisper_compute_type",["auto","int8","int8_float16","float16","float32"],7); self._combo(left,"Language","language",["자동","한국어","영어"],8); self._entry(left,"Initial Prompt","initial_prompt",9); self._entry(left,"Max Record Seconds","max_record_seconds",10); self._entry(left,"Speech End Silence Seconds","auto_stop_silence_seconds",11); self._entry(left,"Always Listen Pre-roll Seconds","always_listen_preroll_seconds",12)
        self._check(left,"Trim leading and trailing silence","trim_silence",13); self._check(left,"Normalize whitespace","normalize_whitespace",14); self._check(left,"Enable manual mode auto stop","enable_auto_stop",15); self._check(left,"Play feedback beeps","beep_feedback",16); self._check(left,"Keep window on top","keep_window_on_top",17)
        ttk.Button(left,text="Apply Audio Preset",command=self.apply_audio_preset).grid(row=18,column=0,columnspan=2,sticky="ew",pady=(12,0))
        self._combo(right,"Output Mode","output_mode",["paste","clipboard","type"],0); self._entry(right,"Paste Hotkey","paste_hotkey",1); self._check(right,"Press Enter after output","auto_enter",2); self._check(right,"Always listen when target input window is focused","always_listen_enabled",3); self._entry(right,"Always Listen Hotkey","always_listen_hotkey",4); self._entry(right,"Record Hotkey","record_hotkey",5); self._entry(right,"Paste Last Hotkey","paste_last_hotkey",6); self._entry(right,"Toggle Output Hotkey","toggle_output_hotkey",7); self._entry(right,"Toggle Enter Hotkey","toggle_enter_hotkey",8); self._check(right,"Enable local LLM correction command","llm_correction_enabled",9); self._combo(right,"LLM Profile","llm_profile",["균형","정확도","직접지정"],10); self._entry(right,"LLM Model","llm_model",11); self._entry(right,"LLM Base URL","llm_base_url",12); self._entry(right,"LLM Timeout Seconds","llm_timeout_seconds",13)
        btn=ttk.Frame(right); btn.grid(row=13,column=0,columnspan=2,sticky="ew",pady=(14,0)); [btn.columnconfigure(i,weight=1) for i in range(3)]
        for r,c,text,cmd in [(0,0,"Start / Stop Manual",self.toggle_recording),(0,1,"Toggle Always Listen",self.toggle_always_listen),(0,2,"Paste Last",self.paste_last),(1,0,"Save Settings",self.save_from_ui),(1,1,"Doctor",self.show_doctor),(1,2,"Refresh Hotkeys",self.register_hotkeys),(2,0,"Copy Last",self.copy_last)]:
            ttk.Button(btn,text=text,command=cmd).grid(row=r,column=c,sticky="ew",padx=6 if c==1 else (0 if c==0 else 6),pady=(8 if r else 0,0))
        tf=ttk.LabelFrame(self.root,text="Latest Transcript",padding=12); tf.grid(row=2,column=0,sticky="nsew",padx=12,pady=(12,6)); tf.columnconfigure(0,weight=1); self.txt=tk.Text(tf,wrap="word",height=8,font=("Segoe UI",10)); self.txt.grid(row=0,column=0,sticky="nsew")
        lf=ttk.LabelFrame(self.root,text="Activity",padding=12); lf.grid(row=3,column=0,sticky="nsew",padx=12,pady=(6,12)); lf.columnconfigure(0,weight=1); lf.rowconfigure(0,weight=1); self.log_text=tk.Text(lf,wrap="word",font=("Consolas",10)); self.log_text.grid(row=0,column=0,sticky="nsew")
    def _entry(self,p,label,key,row): ttk.Label(p,text=label).grid(row=row,column=0,sticky="w",pady=(6,0)); ttk.Entry(p,textvariable=self.vars[key]).grid(row=row,column=1,sticky="ew",pady=(6,0),padx=(8,0)); p.columnconfigure(1,weight=1)
    def _combo(self,p,label,key,values,row): ttk.Label(p,text=label).grid(row=row,column=0,sticky="w",pady=(6,0)); ttk.Combobox(p,textvariable=self.vars[key],values=values,state="normal").grid(row=row,column=1,sticky="ew",pady=(6,0),padx=(8,0)); p.columnconfigure(1,weight=1)
    def _check(self,p,label,key,row): ttk.Checkbutton(p,text=label,variable=self.bools[key]).grid(row=row,column=0,columnspan=2,sticky="w",pady=(8 if row in {2,3,10} else 0,0))
    def log(self,msg):
        append_app_log(msg)
        self.log_q.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    def _llm_status_text(self,kind:str,detail:str="")->str:
        brief=short_log_text(detail, limit=72) if detail else ""
        status_map={
            "disabled":"LLM | 비활성",
            "request_start":f"LLM | 요청 중 ({llm_profile_label(self.s.llm_profile)})",
            "skipped":f"LLM | 설정 문제: {brief or '요청 건너뜀'}",
            "connection_error":f"LLM | 연결 실패: {brief or '응답 없음'}",
            "request_error":f"LLM | 요청 실패: {brief or '오류'}",
            "empty":"LLM | 빈 응답, 원문 유지",
            "rejected":f"LLM | 수정 폭 과다, 원문 유지 ({brief})" if brief else "LLM | 수정 폭 과다, 원문 유지",
            "same":"LLM | 동일 결과, 원문 유지",
            "accepted":"LLM | 교정안 생성됨",
            "applied":"LLM | 교정 적용 완료",
            "apply_failed":"LLM | 교정 적용 실패",
        }
        return status_map.get(kind,self.llm_status.get())
    def _set_stringvar_safe(self,var:tk.StringVar,value:str):
        def apply():
            try:
                var.set(value)
            except tk.TclError:
                pass
        try:
            self.root.after(0,apply)
        except tk.TclError:
            pass
    def _sync_llm_status_idle(self):
        self._set_stringvar_safe(self.llm_status,"LLM | 비활성" if not self.s.llm_correction_enabled else f"LLM | 대기 ({llm_profile_label(self.s.llm_profile)})")
    def _set_llm_status(self,kind:str,detail:str=""):
        self._set_stringvar_safe(self.llm_status,self._llm_status_text(kind,detail))
    def apply_audio_preset(self):
        preset=normalize_audio_preset_value(self.vars["audio_preset"].get())
        self.s.audio_preset=preset
        self.vars["audio_preset"].set(audio_preset_label(preset))
        values=AUDIO_PRESET_VALUES.get(preset,{})
        for key,value in values.items():
            setattr(self.s,key,value)
            if key in self.vars:
                self.vars[key].set(str(value))
        save_settings(self.s); self.rec.s=self.s; self.listen.s=self.s; self.refresh_status(); self.refresh_audio_status(); self.log(f"Audio preset applied: {audio_preset_label(preset)}")
    def next_ai_correction_trace(self)->str:
        self.ai_correction_seq += 1
        return f"AI-CORR-{self.ai_correction_seq:04d}"
    def _invalidate_ai_prefetch(self, clear_ready:bool=True):
        with self.ai_prefetch_lock:
            entries=[] if clear_ready else list(self.ai_prefetch.entries)
            self.ai_prefetch=AICorrectionPrefetchState(entries=entries,job_id=self.ai_prefetch.job_id)
    def _consume_ai_prefetch(self, source_text:str)->tuple[str,str]:
        source_key=normalize_text(source_text)
        current_signature=self._prefetch_model_signature()
        with self.ai_prefetch_lock:
            for idx in range(len(self.ai_prefetch.entries)-1,-1,-1):
                entry=self.ai_prefetch.entries[idx]
                if entry.signature!=current_signature:
                    continue
                if normalize_text(entry.source_text)!=source_key:
                    continue
                corrected=entry.corrected_text
                outcome=entry.outcome
                del self.ai_prefetch.entries[idx]
                return outcome, corrected
        return "", ""
    def _await_ai_prefetch(self, source_text:str, timeout_seconds:float)->tuple[str,str]:
        source_key=normalize_text(source_text)
        current_signature=self._prefetch_model_signature()
        deadline=time.time()+max(0.0,timeout_seconds)
        while time.time() <= deadline:
            with self.ai_prefetch_lock:
                for idx in range(len(self.ai_prefetch.entries)-1,-1,-1):
                    entry=self.ai_prefetch.entries[idx]
                    if entry.signature!=current_signature:
                        continue
                    if normalize_text(entry.source_text)!=source_key:
                        continue
                    corrected=entry.corrected_text
                    outcome=entry.outcome
                    del self.ai_prefetch.entries[idx]
                    return outcome, corrected
                same_in_flight=(
                    self.ai_prefetch.in_flight
                    and normalize_text(self.ai_prefetch.active_source_text)==source_key
                )
            if not same_in_flight:
                return "", ""
            time.sleep(0.05)
        return "", ""
    def _prefetch_model_signature(self)->tuple[str,str,str,bool]:
        return (
            normalize_language_value(self.s.language),
            normalize_llm_profile_value(self.s.llm_profile),
            resolve_llm_model(self.s),
            bool(self.s.llm_correction_enabled),
        )
    def _schedule_ai_prefetch_for_pending(self):
        if not self.s.llm_correction_enabled or self.last_submitted:
            self._invalidate_ai_prefetch()
            return
        source=self.pending_text.strip()
        if not source:
            self._invalidate_ai_prefetch()
            return
        signature=self._prefetch_model_signature()
        with self.ai_prefetch_lock:
            current=self.ai_prefetch
            source_key=normalize_text(source)
            if any(entry.signature==signature and normalize_text(entry.source_text)==source_key for entry in current.entries):
                return
            if normalize_text(current.active_source_text)==source_key and current.in_flight:
                return
            job_id=current.job_id+1
            self.ai_prefetch=AICorrectionPrefetchState(entries=list(current.entries),active_source_text=source,in_flight=True,job_id=job_id)
        thread=threading.Thread(target=self._ai_prefetch_worker,args=(job_id,source,signature),daemon=True)
        thread.start()
    def _ai_prefetch_worker(self, job_id:int, source_text:str, signature:tuple[str,str,str,bool]):
        trace_id=f"AI-PREFETCH-{job_id:04d}"
        self.log(f"{trace_id} | 정정 후보 생성 시작")
        corrected=self.posteditor.correct(source_text,self.s,trace_id=trace_id).strip()
        with self.ai_prefetch_lock:
            current=self.ai_prefetch
            if current.job_id!=job_id:
                self.log(f"{trace_id} | 최신 작업이 아니어서 정정 후보 폐기")
                return
            current_signature=self._prefetch_model_signature()
            if current_signature!=signature or normalize_text(current.active_source_text)!=normalize_text(source_text):
                self.ai_prefetch=AICorrectionPrefetchState(entries=list(current.entries),job_id=current.job_id)
                self.log(f"{trace_id} | 정정 후보 무효화")
                return
            if corrected and normalize_text(corrected)!=normalize_text(source_text):
                entries=[
                    entry for entry in current.entries
                    if not (entry.signature==signature and normalize_text(entry.source_text)==normalize_text(source_text))
                ]
                entries.append(AICorrectionPrefetchEntry(source_text=source_text,corrected_text=corrected,signature=signature,outcome="corrected"))
                entries=entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch=AICorrectionPrefetchState(entries=entries,job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료")
            elif corrected and normalize_text(corrected)==normalize_text(source_text):
                entries=[
                    entry for entry in current.entries
                    if not (entry.signature==signature and normalize_text(entry.source_text)==normalize_text(source_text))
                ]
                entries.append(AICorrectionPrefetchEntry(source_text=source_text,corrected_text=source_text,signature=signature,outcome="same"))
                entries=entries[-AI_PREFETCH_CACHE_SIZE:]
                self.ai_prefetch=AICorrectionPrefetchState(entries=entries,job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 저장 완료 (same)")
            else:
                self.ai_prefetch=AICorrectionPrefetchState(entries=list(current.entries),job_id=job_id)
                self.log(f"{trace_id} | 정정 후보 없음")
    def refresh_status(self,activity="Idle"): self.status.set(f"{activity} | {self.s.output_mode.upper()} | {language_label(self.s.language)}{' | LLM '+llm_profile_label(self.s.llm_profile) if self.s.llm_correction_enabled else ''}{' + ENTER' if self.s.auto_enter else ''}{' | ALWAYS-ON' if self.listen.on else ''}")
    def refresh_audio_status(self):
        source="manual" if self.rec.on else ("always-listen" if self.listen.on else "idle")
        rms,peak,threshold,voice,updated=(self.rec.meter_snapshot() if self.rec.on else self.listen.meter_snapshot())
        waiting="waiting for input" if updated<=0 else f"rms={rms:.4f} | peak={peak:.4f} | threshold={threshold:.4f} | voice={'yes' if voice else 'no'}"
        self.audio_status.set(f"Audio | source={source} | preset={audio_preset_label(self.s.audio_preset)} | gain={self.s.input_gain:.2f} | gate={self.s.noise_gate_threshold:.3f} | {waiting}")
    def refresh_target(self): self.target.set("Target: focused terminal or input field")
    def bootstrap_after_launch(self):
        self.minimize_after_startup()
        self.restore_launch_target_after_startup()
        self.refresh_status("Warming up")
        self.warmup_model()
        self.register_hotkeys()
        self.sync_listener()
        self.log("Ready")
    def minimize_after_startup(self):
        self.log("Startup minimize skipped")
        return
    def ensure_window_visible_on_startup(self):
        if not self.show_window:
            return
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.focus_force()
            self.root.after(250, lambda: self.root.attributes("-topmost", self.s.keep_window_on_top))
            self.log("Startup window shown")
        except Exception as e:
            self.log(f"Startup window show failed: {e}")
    def restore_launch_target_after_startup(self):
        try:
            if self.show_window:
                return
            if self.target_active():
                return
            if self.launch_target and self.launch_target.pid!=APP_PID and focus_window(self.launch_target.hwnd):
                self.log("Focused previous window after startup")
                return
            if focus_best_terminal():
                self.log("Focused terminal after startup")
        except Exception as e:
            self.log(f"Startup target focus skipped: {e}")
    def save_from_ui(self):
        for k,v in self.vars.items():
            cur=getattr(self.s,k); raw=v.get().strip()
            if k=="language":
                setattr(self.s,k,normalize_language_value(raw))
                self.vars["language"].set(language_label(self.s.language))
            elif k=="audio_preset":
                setattr(self.s,k,normalize_audio_preset_value(raw))
                self.vars["audio_preset"].set(audio_preset_label(self.s.audio_preset))
            elif k=="llm_profile":
                setattr(self.s,k,normalize_llm_profile_value(raw))
                self.vars["llm_profile"].set(llm_profile_label(self.s.llm_profile))
            elif isinstance(cur,int): setattr(self.s,k,int(raw or "0"))
            elif isinstance(cur,float): setattr(self.s,k,float(raw or "0"))
            else: setattr(self.s,k,raw)
        self.s.input_gain=max(float(self.s.input_gain),0.0)
        self.s.noise_gate_threshold=max(float(self.s.noise_gate_threshold),0.0)
        self.vars["input_gain"].set(str(self.s.input_gain))
        self.vars["noise_gate_threshold"].set(str(self.s.noise_gate_threshold))
        for k,v in self.bools.items(): setattr(self.s,k,bool(v.get()))
        save_settings(self.s); self.rec.s=self.s; self.listen.s=self.s; self.root.attributes("-topmost",self.s.keep_window_on_top); self.refresh_target(); self.refresh_status(); self.refresh_audio_status(); self._sync_llm_status_idle(); self.log("Settings saved")
    def register_hotkeys(self):
        self.save_from_ui()
        try: import keyboard
        except Exception as e: self.log(f"Hotkeys unavailable: {e}"); return
        try:
            try: keyboard.unhook_all_hotkeys()
            except Exception as e: self.log(f"Hotkey cleanup skipped: {e}")
            keyboard.add_hotkey(self.s.always_listen_hotkey,self.toggle_always_listen,suppress=False,trigger_on_release=False); keyboard.add_hotkey(self.s.record_hotkey,self.toggle_recording,suppress=False,trigger_on_release=False); keyboard.add_hotkey(self.s.paste_last_hotkey,self.paste_last,suppress=False,trigger_on_release=False); keyboard.add_hotkey(self.s.toggle_output_hotkey,self.cycle_output,suppress=False,trigger_on_release=False); keyboard.add_hotkey(self.s.toggle_enter_hotkey,self.toggle_enter,suppress=False,trigger_on_release=False); self.log("Hotkeys registered")
        except Exception as e: self.log(f"Hotkey registration failed: {e}")
    def beep(self,kind):
        if not self.s.beep_feedback: return
        try:
            import winsound
            for k,freq,dur in [("start",880,90),("stop",660,110),("done",1040,120),("error",330,160)]:
                if kind==k: winsound.Beep(freq,dur); return
        except Exception: pass
    def target_active(self)->bool:
        info=fg_info()
        if not info: return False
        return is_target_window(info)
    def sync_listener(self):
        if self.s.always_listen_enabled and not self.listen.on:
            try: self.listen.start()
            except Exception as e: self.s.always_listen_enabled=False; self.bools["always_listen_enabled"].set(False); save_settings(self.s); self.beep("error"); self.log(f"Failed to start always-listen: {e}")
        elif not self.s.always_listen_enabled and self.listen.on: self.listen.stop()
        self.refresh_status()
    def toggle_always_listen(self):
        if self.rec.on: self.log("Stop manual recording before enabling always-listen"); return
        self.s.always_listen_enabled=not self.s.always_listen_enabled; self.bools["always_listen_enabled"].set(self.s.always_listen_enabled); save_settings(self.s); self.sync_listener(); self.log(f"Always-listen enabled: {self.s.always_listen_enabled}")
    def toggle_recording(self):
        if self.listen.on: self.log("Manual recording is disabled while always-listen is running"); return
        if self.busy: self.log("Busy transcribing, wait a moment"); return
        if self.rec.on: self.stop_recording()
        else:
            try: self.save_from_ui(); self.rec.start(); self.beep("start"); self.refresh_status("Recording")
            except Exception as e: self.beep("error"); self.log(f"Failed to start recording: {e}"); messagebox.showerror(APP_NAME,str(e))
    def stop_recording(self): audio=self.rec.stop(); self.beep("stop"); self.queue_audio(audio,"manual"); self.refresh_status()
    def enqueue_audio(self,audio,source): self.res_q.put(("captured",{"audio":audio,"source":source}))
    def queue_audio(self,audio,source):
        dur=len(audio)/max(self.s.sample_rate,1)
        if dur<self.s.min_record_seconds: self.log(f"Ignored {source} audio because it was too short"); return
        if self.s.trim_silence:
            t=trim_silence(audio,self.s.trim_threshold)
            if t.size: audio=t
        if self.busy: self.jobs.put((audio,source)); self.log(f"Queued {source} audio while another transcription is running"); return
        self.busy=True; self.refresh_status("Transcribing"); self.t=threading.Thread(target=self._worker,args=(audio,source),daemon=True); self.t.start()
    def _worker(self,audio,source):
        t0=time.perf_counter()
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav",delete=False) as h: path=Path(h.name)
            sf.write(path,audio,self.s.sample_rate)
            raw_text=self.backend.transcribe(path,self.s)
            raw_text=normalize_text(raw_text) if self.s.normalize_whitespace else raw_text
            self.res_q.put(("done",{"text":raw_text,"raw_text":raw_text,"elapsed":time.perf_counter()-t0,"audio_seconds":len(audio)/self.s.sample_rate,"source":source}))
        except Exception as e: self.res_q.put(("error","".join(traceback.format_exception(e))))
        finally:
            try: path.unlink(missing_ok=True)
            except Exception: pass
    def _next(self):
        if self.busy: return
        try: audio,source=self.jobs.get_nowait()
        except queue.Empty: return
        self.queue_audio(audio,source)
    def warmup_model(self):
        t0=time.perf_counter(); path=None
        try:
            self.root.update_idletasks()
            self.log(f"Model warmup started for {self.s.whisper_model}")
            self.backend._model(self.s)
            with tempfile.NamedTemporaryFile(suffix=".wav",delete=False) as h:
                path=Path(h.name)
            sf.write(path,np.zeros(max(int(self.s.sample_rate*0.35),1),dtype=np.float32),self.s.sample_rate)
            self.backend.transcribe(path,self.s)
            self.log(f"Model warmup finished in {time.perf_counter()-t0:.2f}s")
        except Exception as e:
            self.log(f"Model warmup skipped: {e}")
        finally:
            if path is not None:
                try: path.unlink(missing_ok=True)
                except Exception: pass
            self.refresh_status()
    def _keyboard(self):
        import keyboard
        return keyboard
    def _backspace_text(self,text)->bool:
        if not text: return True
        try: keyboard=self._keyboard()
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        for _ in text: keyboard.press_and_release("backspace")
        return True
    def _clear_focused_input(self)->bool:
        info=fg_info()
        if not info or not (has_precise_text_focus(info) or is_terminal(info)):
            self.log("Voice command ignored: no focused input target")
            return False
        try: keyboard=self._keyboard()
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        keyboard.press_and_release("ctrl+a")
        time.sleep(0.05)
        keyboard.press_and_release("delete")
        time.sleep(0.03)
        keyboard.press_and_release("backspace")
        self.pending_text=""
        self.pending_segments=[]
        self.last_emitted=""
        self.last_submitted=False
        self._invalidate_ai_prefetch()
        self.log("Voice command executed: clear focused input")
        return True
    def _update_latest_transcript(self,text):
        self.last=text; self.txt.delete("1.0",tk.END); self.txt.insert("1.0",text); self.copy_clip(text)
    def _copy_hotkeys(self)->tuple[str,...]:
        return ("ctrl+c","ctrl+insert")
    def _cut_hotkeys(self)->tuple[str,...]:
        return ("ctrl+x","shift+delete")
    def _paste_hotkey(self)->str:
        return self.s.paste_hotkey or "ctrl+v"
    def _should_safe_paste(self,info:WinInfo|None)->bool:
        return bool(info and (info.proc in BROWSER_FALLBACK_PROCS or info.proc in WINDOWS_SEARCH_PROCS or info.proc in SYSTEM_INPUT_PROCS))
    def _run_hotkey_sequence(self,*keys:str)->bool:
        try: keyboard=self._keyboard()
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        for key in keys:
            keyboard.press_and_release(key)
            time.sleep(0.05)
        return True
    def _with_restored_clipboard(self, text:str, action)->str:
        original=get_clipboard_text()
        set_clipboard_text(text)
        time.sleep(0.05)
        try:
            return action()
        finally:
            time.sleep(0.03)
            set_clipboard_text(original)
    def _capture_selection_text(self, hotkeys:tuple[str,...], remove:bool=False)->str:
        original=get_clipboard_text()
        sentinel=f"__codex_capture__{time.time_ns()}__"
        try:
            for hotkey in hotkeys:
                set_clipboard_text(sentinel)
                time.sleep(0.03)
                if not self._run_hotkey_sequence(hotkey):
                    continue
                for _ in range(16):
                    time.sleep(0.05)
                    captured=get_clipboard_text()
                    if captured and captured != sentinel:
                        return captured
            return ""
        finally:
            set_clipboard_text(original)
    def _store_internal_buffer(self,text:str,slot:int|None=None)->bool:
        if not text:
            return False
        if slot is None:
            self.internal_buffer=text
            self.log("Voice command executed: copy to internal buffer")
        else:
            self.buffer_slots[slot]=text
            self.log(f"Voice command executed: store slot {slot}")
        return True
    def _remember_output_payload(self,payload:str,sent_enter:bool=False):
        self.last_emitted=payload
        self.last_submitted=bool(sent_enter)
        if sent_enter:
            self.pending_text=""
            self.pending_segments=[]
            self._invalidate_ai_prefetch()
        else:
            self.pending_text=f"{self.pending_text}{payload}"
            self.pending_segments.append(payload)
            self._schedule_ai_prefetch_for_pending()
    def _paste_text_via_clipboard(self,text:str)->bool:
        if not text:
            return False
        try:
            keyboard=self._keyboard()
        except Exception as e:
            self.log(f"Output hotkeys unavailable: {e}")
            return False
        original=get_clipboard_text()
        try:
            if not set_clipboard_text(text):
                return False
            time.sleep(0.05)
            keyboard.press_and_release(self._paste_hotkey())
            return True
        finally:
            time.sleep(0.03)
            set_clipboard_text(original)
    def _paste_payload(self,text:str)->bool:
        if not text:
            return False
        self._update_latest_transcript(text)
        if not self._paste_text_via_clipboard(text):
            return False
        self._remember_output_payload(text,sent_enter=False)
        self.last_paste_payload=text
        return True
    def _replace_pending_with_prepared_clipboard(self, text:str, trace_id:str|None=None)->bool:
        if not self.pending_text:
            self.log("Voice command ignored: no current text to replace")
            return False
        if self.last_submitted:
            self.log("Voice command ignored: last text was already submitted")
            return False
        info=fg_info()
        allow_space=has_precise_text_focus(info)
        payload=f"{text} " if text and allow_space else text
        old_pending=self.pending_text
        old_segments=list(self.pending_segments)
        old_last=self.last_emitted
        try:
            keyboard=self._keyboard()
        except Exception as e:
            self.log(f"Output hotkeys unavailable: {e}")
            return False
        use_typed_output = self.s.output_mode=="type" and not self._should_safe_paste(info)
        original_clipboard=get_clipboard_text() if not use_typed_output else ""
        trace_prefix=f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=pending, mode={'type' if use_typed_output else 'paste'}, old_len={len(old_pending)}, new_len={len(payload)}")
        if not use_typed_output and not set_clipboard_text(payload):
            self.log("Voice command failed: failed to prepare correction clipboard")
            return False
        try:
            try:
                keyboard.press_and_release("end")
                time.sleep(0.01)
            except Exception as e:
                self.log(f"Voice command failed: failed to prepare current input replacement ({e})")
                return False
            delete_started=time.perf_counter()
            self.log(f"{trace_prefix}교체 시작")
            if not self._backspace_text(old_pending):
                return False
            self.log(f"{trace_prefix}원문 제거 완료 ({time.perf_counter()-delete_started:.3f}s)")
            self.pending_text=""
            self.pending_segments=[]
            self.last_emitted=""
            self._update_latest_transcript(text)
            reinject_started=time.perf_counter()
            try:
                if use_typed_output:
                    keyboard.write(payload, delay=0)
                else:
                    keyboard.press_and_release(self._paste_hotkey())
            except Exception as e:
                return self._rollback_replace(old_pending,old_pending,old_segments,old_last,f"failed to emit corrected input ({e})",trace_id=trace_id)
            time.sleep(0.03)
            self._remember_output_payload(payload,sent_enter=False)
            self.log(f"{trace_prefix}교정문 삽입 완료 ({time.perf_counter()-reinject_started:.3f}s)")
            self.log(f"{trace_prefix}빈 구간 추정 {time.perf_counter()-delete_started:.3f}s")
            self._remember_replace_state("pending",old_pending,payload,old_last,old_pending,old_segments)
            self.log(f"{trace_prefix}교체 완료")
            return True
        finally:
            if not use_typed_output:
                time.sleep(0.02)
                set_clipboard_text(original_clipboard)
    def _remember_replace_state(self,kind:str,old_text:str,new_payload:str,old_segment:str="",old_pending:str="",old_segments:list[str]|None=None):
        self.last_replace_state={
            "kind":kind,
            "old_text":old_text,
            "new_payload":new_payload,
            "old_segment":old_segment,
            "old_pending":old_pending,
            "old_segments":list(old_segments or []),
        }
    def _iter_slot_tokens(self,text:str):
        raw=text.strip().lower()
        compact=self._command_key(text)
        for token,slot in SLOT_NUMBER_WORDS.items():
            yield token,slot,raw,compact
    def _parse_slot_command(self,text:str)->tuple[str,int]|None:
        for token,slot,raw,compact in self._iter_slot_tokens(text):
            if raw in {f"{token}번 복사",f"복사 {token}번"} or compact in {f"{token}번복사",f"복사{token}번"}:
                return ("copy",slot)
            if raw in {f"{token}번 잘라",f"{token}번 잘라내기",f"잘라 {token}번"} or compact in {f"{token}번잘라",f"{token}번잘라내기",f"잘라{token}번"}:
                return ("cut",slot)
            if raw in {f"{token}번 붙여넣기",f"{token}번 붙여 넣기",f"붙여넣기 {token}번",f"붙여 넣기 {token}번"} or compact in {f"{token}번붙여넣기",f"{token}번붙여넣기",f"붙여넣기{token}번"}:
                return ("paste",slot)
        return None
    def copy_selection_to_buffer(self)->bool:
        copied=self._capture_selection_text(self._copy_hotkeys())
        if not copied:
            self.log("Voice command ignored: no selected text copied")
            return False
        return self._store_internal_buffer(copied)
    def copy_selection_to_slot(self,slot:int)->bool:
        copied=self._capture_selection_text(self._copy_hotkeys())
        if not copied:
            self.log("Voice command ignored: no selected text copied")
            return False
        return self._store_internal_buffer(copied,slot)
    def cut_selection_to_buffer(self)->bool:
        cut_text=self._capture_selection_text(self._cut_hotkeys(), remove=True)
        if not cut_text:
            self.log("Voice command ignored: no selected text cut")
            return False
        return self._store_internal_buffer(cut_text)
    def cut_selection_to_slot(self,slot:int)->bool:
        cut_text=self._capture_selection_text(self._cut_hotkeys(), remove=True)
        if not cut_text:
            self.log("Voice command ignored: no selected text cut")
            return False
        return self._store_internal_buffer(cut_text,slot)
    def paste_internal_buffer(self)->bool:
        if not self.internal_buffer:
            self.log("Voice command ignored: internal buffer is empty")
            return False
        ok=self._paste_payload(self.internal_buffer)
        if ok:
            self.log("Voice command executed: paste internal buffer")
        return ok
    def paste_slot_buffer(self,slot:int)->bool:
        value=self.buffer_slots.get(slot,"")
        if not value:
            self.log(f"Voice command ignored: slot {slot} is empty")
            return False
        ok=self._paste_payload(value)
        if ok:
            self.log(f"Voice command executed: paste slot {slot}")
        return ok
    def undo_last_paste(self)->bool:
        if not self.last_paste_payload:
            self.log("Voice command ignored: no pasted text to undo")
            return False
        payload=self.last_paste_payload
        if not self._run_hotkey_sequence("ctrl+z"):
            return False
        self.last_paste_payload=""
        if self.pending_segments and self.pending_segments[-1]==payload:
            self.pending_segments=self.pending_segments[:-1]
            if self.pending_text.endswith(payload):
                self.pending_text=self.pending_text[:-len(payload)]
            self.last_emitted=self.pending_segments[-1] if self.pending_segments else ""
        self._invalidate_ai_prefetch()
        self.log("Voice command executed: undo last paste")
        return True
    def undo_last_replace(self)->bool:
        state=self.last_replace_state
        if not state:
            self.log("Voice command ignored: no replacement to undo")
            return False
        new_payload=state.get("new_payload","")
        if new_payload and not self._backspace_text(new_payload):
            return False
        old_text=state.get("old_text","")
        old_segments=state.get("old_segments",[])
        old_pending=state.get("old_pending","")
        old_segment=state.get("old_segment","")
        self.emit_text(old_text,remember=False,press_enter=False,append_space=False,force_paste=True)
        if state.get("kind") in {"last","pending"}:
            self.pending_segments=old_segments
            self.pending_text=old_pending
            self.last_emitted=old_segment
            self._schedule_ai_prefetch_for_pending()
        self.last_replace_state=None
        self.log("Voice command executed: undo last replace")
        return True
    def _rollback_replace(self,restore_text:str,old_pending:str,old_segments:list[str],old_last:str,reason:str,trace_id:str|None=None)->bool:
        restored=False
        trace_prefix=f"{trace_id} | " if trace_id else ""
        if restore_text:
            restored=bool(self.emit_text(restore_text,remember=False,press_enter=False,append_space=False,force_paste=True))
        self.pending_text=old_pending
        self.pending_segments=list(old_segments)
        self.last_emitted=old_last
        self.last_replace_state=None
        if old_pending and not self.last_submitted:
            self._schedule_ai_prefetch_for_pending()
        else:
            self._invalidate_ai_prefetch()
        if restore_text:
            self._update_latest_transcript(restore_text)
            self.log(f"{trace_prefix}롤백 시도 완료: restored={restored}")
        self.log(f"{trace_prefix}Voice command failed: {reason}")
        return restored
    def emit_text(self,text,remember=True,press_enter:bool|None=None,append_space=True,force_paste:bool=False):
        try: import keyboard
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        sent_enter=self.s.auto_enter if press_enter is None else press_enter
        info=fg_info()
        allow_space=append_space and has_precise_text_focus(info)
        payload=f"{text} " if text and allow_space and not sent_enter else text
        if self.s.output_mode=="clipboard":
            self.log("Copied transcript to clipboard")
            return True
        if self.s.output_mode=="type" and not force_paste and not self._should_safe_paste(info):
            try:
                keyboard.write(payload,delay=0)
            except Exception as e:
                self.log(f"Output typing failed: {e}")
                return False
        else:
            original=get_clipboard_text()
            try:
                if not set_clipboard_text(payload):
                    self.log("Output paste failed: clipboard set failed")
                    return False
                time.sleep(0.05)
                keyboard.press_and_release(self._paste_hotkey())
            except Exception as e:
                self.log(f"Output paste failed: {e}")
                return False
            finally:
                time.sleep(0.03)
                set_clipboard_text(original)
        if sent_enter:
            try:
                time.sleep(0.03)
                keyboard.press_and_release("enter")
            except Exception as e:
                self.log(f"Output enter failed: {e}")
                return False
        if remember:
            self._remember_output_payload(payload,sent_enter=sent_enter)
        self.log(f"Transcript sent via {self.s.output_mode}")
        return True
    def send_enter(self)->bool:
        try: keyboard=self._keyboard()
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        keyboard.press_and_release("enter")
        self.last_submitted=True
        self.pending_text=""
        self.pending_segments=[]
        self.log("Voice command executed: submit")
        return True
    def undo_last_emitted(self,count:int=1)->bool:
        if count<=0: return False
        if not self.pending_segments: self.log("Voice command ignored: no recent text to erase"); return False
        if self.last_submitted: self.log("Voice command ignored: last text was already submitted"); return False
        if count>len(self.pending_segments): count=len(self.pending_segments)
        removed="".join(self.pending_segments[-count:])
        if not self._backspace_text(removed): return False
        self.pending_segments=self.pending_segments[:-count]
        if self.pending_text.endswith(removed): self.pending_text=self.pending_text[:-len(removed)]
        self.last_emitted=self.pending_segments[-1] if self.pending_segments else ""
        if self.pending_text and not self.last_submitted:
            self._schedule_ai_prefetch_for_pending()
        else:
            self._invalidate_ai_prefetch()
        self.log(f"Voice command executed: erase last {count} segment(s)")
        return True
    def clear_pending_input(self)->bool:
        if not self.pending_text: self.log("Voice command ignored: no current text to clear"); return False
        if self.last_submitted: self.log("Voice command ignored: last text was already submitted"); return False
        try: keyboard=self._keyboard()
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return False
        keyboard.press_and_release("end")
        if not self._backspace_text(self.pending_text): return False
        self.log("Voice command executed: clear current input")
        self.pending_text=""
        self.pending_segments=[]
        self.last_emitted=""
        self._invalidate_ai_prefetch()
        return True
    def replace_last_emitted(self,text:str,trace_id:str|None=None)->bool:
        if not self.pending_segments: self.log("Voice command ignored: no recent text to replace"); return False
        if self.last_submitted: self.log("Voice command ignored: last text was already submitted"); return False
        last_segment=self.pending_segments[-1]
        old_pending=self.pending_text
        old_segments=list(self.pending_segments)
        old_last=self.last_emitted
        trace_prefix=f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=last, old_len={len(last_segment)}, new_len={len(text)}")
        if not self._backspace_text(last_segment): return False
        self.pending_segments=self.pending_segments[:-1]
        if self.pending_text.endswith(last_segment): self.pending_text=self.pending_text[:-len(last_segment)]
        self._update_latest_transcript(text)
        if not self.emit_text(text,remember=True,press_enter=False,append_space=True,force_paste=True):
            return self._rollback_replace(last_segment,old_pending,old_segments,old_last,"failed to replace last emitted text",trace_id=trace_id)
        self._remember_replace_state("last",last_segment,self.last_emitted,last_segment,old_pending,old_segments)
        self.log(f"{trace_prefix}교체 완료")
        return True
    def replace_pending_text(self,text:str,trace_id:str|None=None)->bool:
        return self._replace_pending_with_prepared_clipboard(text,trace_id=trace_id)
    def replace_selection_or_last(self,text:str)->bool:
        selected=self._capture_selection_text(self._copy_hotkeys())
        if selected:
            self._update_latest_transcript(text)
            if not self.emit_text(text,remember=False,press_enter=False,append_space=False,force_paste=True):
                self._update_latest_transcript(selected)
                self.log("Voice command failed: failed to replace current selection")
                return False
            self._remember_replace_state("selection",selected,text)
            self.log("Voice command executed: replace current selection")
            return True
        return self.replace_last_emitted(text)
    def replace_selected_text(self,selected_text:str,text:str,trace_id:str|None=None)->bool:
        selected=self._capture_selection_text(self._copy_hotkeys())
        if not selected:
            self.log("Voice command ignored: no selected text to replace")
            return False
        trace_prefix=f"{trace_id} | " if trace_id else ""
        self.log(f"{trace_prefix}교체 준비: target=selection, old_len={len(selected)}, new_len={len(text)}")
        self._update_latest_transcript(text)
        if not self.emit_text(text,remember=False,press_enter=False,append_space=False,force_paste=True):
            self._update_latest_transcript(selected_text or selected)
            self.log("Voice command failed: failed to replace current selection")
            return False
        self._remember_replace_state("selection",selected,text)
        self.log(f"{trace_prefix}교체 완료")
        return True
    def _get_ai_correction_target(self)->CorrectionTarget|None:
        info=fg_info()
        if self.pending_text and not self.last_submitted:
            source=self.pending_text.strip()
            if source:
                return CorrectionTarget("pending",source)
        if info and has_precise_text_focus(info) and not is_terminal(info):
            selected=self._capture_selection_text(self._copy_hotkeys())
            if selected and selected.strip():
                return CorrectionTarget("selection",selected.strip())
        source=self.last_emitted.strip()
        if source:
            return CorrectionTarget("last",source)
        return None
    def _apply_ai_correction_target(self,target:CorrectionTarget,corrected:str,trace_id:str|None=None)->bool:
        if target.kind=="selection":
            return self.replace_selected_text(target.source_text,corrected,trace_id=trace_id)
        if target.kind=="pending":
            return self.replace_pending_text(corrected,trace_id=trace_id)
        return self.replace_last_emitted(corrected,trace_id=trace_id)
    def ai_correct_selection_or_last(self)->bool:
        if not self.s.llm_correction_enabled:
            self.log("Voice command ignored: local LLM correction is disabled")
            return False
        trace_id=self.next_ai_correction_trace()
        self.log(f"{trace_id} | 정정 명령 수신")
        target=self._get_ai_correction_target()
        if not target or not target.source_text:
            self.log(f"{trace_id} | 교정 대상 없음")
            return False
        source=target.source_text
        self.log(f"{trace_id} | 대상 확정: kind={target.kind}, text={short_log_text(source)}")
        self.log(f"{trace_id} | LLM 요청 시작 전 원문 유지")
        corrected=""
        prefetched_outcome=""
        if target.kind=="pending":
            prefetched_outcome, corrected=self._consume_ai_prefetch(source)
            corrected=corrected.strip()
            if corrected:
                if prefetched_outcome=="same":
                    self.log(f"{trace_id} | 백그라운드 정정 후보 재사용 (same)")
                else:
                    self.log(f"{trace_id} | 백그라운드 정정 후보 재사용")
            else:
                with self.ai_prefetch_lock:
                    should_wait=(
                        self.ai_prefetch.in_flight
                        and normalize_text(self.ai_prefetch.active_source_text)==normalize_text(source)
                    )
                if should_wait:
                    self.log(f"{trace_id} | 백그라운드 정정 후보 대기")
                    prefetched_outcome, corrected=self._await_ai_prefetch(source, timeout_seconds=self.s.llm_timeout_seconds+1.0)
                    corrected=corrected.strip()
                    if corrected:
                        if prefetched_outcome=="same":
                            self.log(f"{trace_id} | 백그라운드 정정 후보 완료 후 재사용 (same)")
                        else:
                            self.log(f"{trace_id} | 백그라운드 정정 후보 완료 후 재사용")
        if prefetched_outcome=="same":
            self._update_latest_transcript(source)
            self._set_llm_status("same","")
            self.log(f"{trace_id} | 결과 동일 -> 원문 유지")
            return True
        if not corrected:
            corrected=self.posteditor.correct(source,self.s,trace_id=trace_id).strip()
        if not corrected:
            self.log(f"{trace_id} | LLM 결과 비어 있음 -> 원문 유지")
            return False
        self.log(f"{trace_id} | LLM 결과 수신: {short_log_text(corrected)}")
        if normalize_text(corrected)==normalize_text(source):
            self._update_latest_transcript(source)
            self._set_llm_status("same","")
            self.log(f"{trace_id} | 결과 동일 -> 원문 유지")
            return True
        self.log(f"{trace_id} | 결과 검증 통과 -> 교체 진행")
        ok=self._apply_ai_correction_target(target,corrected,trace_id=trace_id)
        if ok:
            self._set_llm_status("applied","")
            self.log(f"{trace_id} | 정정 완료")
        else:
            self._set_llm_status("apply_failed","")
            self.log(f"{trace_id} | 정정 실패 -> 원문 유지/복구 확인 필요")
        return ok
    def _command_key(self,text:str)->str:
        return command_key(text)
    def parse_language_switch(self,text:str)->str|None:
        return parse_language_switch_text(text)
    def parse_correction(self,text:str)->str:
        return parse_correction_text(text)
    def set_language_mode(self,language:str)->bool:
        normalized=normalize_language_value(language)
        if normalized==self.s.language:
            self.log(f"Voice command ignored: language already set to {language_label(self.s.language)}")
            return True
        self.s.language=normalized
        self.vars["language"].set(language_label(self.s.language))
        save_settings(self.s)
        self.refresh_status()
        self.log(f"Voice command executed: language -> {language_label(self.s.language)}")
        return True
    def control_focused_window(self,action:str)->bool:
        info=fg_info()
        if not info:
            self.log("Voice command ignored: no active window")
            return False
        ok=control_window_state(info,action)
        if not ok:
            self.log(f"Voice command ignored: unable to {action} current window")
            return False
        label={"maximize":"maximize","minimize":"minimize","restore":"restore"}.get(action,action)
        self.log(f"Voice command executed: window {label}")
    def parse_media_command(self,text:str)->tuple[str,int]|None:
        return parse_media_command_text(text)
    def execute_media_control(self,action:str,count:int=1)->bool:
        info=fg_info()
        if not info or info.pid==APP_PID or info.proc in EXCLUDED_TARGET_PROCS or info.cls in EXCLUDED_TARGET_CLASSES:
            self.log("Voice command ignored: no controllable foreground window")
            return False
        if action=="play_pause":
            if not send_media_virtual_key(0xB3):
                self.log("Voice command failed: media play_pause")
                return False
            self.log("Voice command executed: play/pause")
            return True
        try:
            keyboard=self._keyboard()
        except Exception as e:
            self.log(f"Output hotkeys unavailable: {e}")
            return False
        key_map={"escape":"esc","forward":"right","backward":"left"}
        press_key=key_map.get(action)
        if not press_key:
            return False
        count=max(1,min(int(count or 1),10))
        try:
            for _ in range(count):
                keyboard.press_and_release(press_key)
                time.sleep(0.03)
        except Exception as e:
            self.log(f"Voice command failed: media {action} ({e})")
            return False
        if action=="escape":
            self.log("Voice command executed: esc")
        elif action=="forward":
            self.log(f"Voice command executed: seek forward x{count}")
        else:
            self.log(f"Voice command executed: seek backward x{count}")
        return True
    def parse_delete_count(self,text:str)->int:
        return parse_delete_count_text(text)
    def is_voice_command_text(self,text:str)->bool:
        return is_voice_command_text(text)
    def handle_voice_command(self,text:str)->bool:
        key=self._command_key(text)
        if not key: return False
        slot_command=self._parse_slot_command(text)
        if slot_command:
            action,slot=slot_command
            if action=="copy": return self.copy_selection_to_slot(slot)
            if action=="cut": return self.cut_selection_to_slot(slot)
            if action=="paste": return self.paste_slot_buffer(slot)
        if key in ENTER_COMMANDS: return self.send_enter()
        if key in COPY_COMMANDS: return self.copy_selection_to_buffer()
        if key in CUT_COMMANDS: return self.cut_selection_to_buffer()
        if key in PASTE_COMMANDS: return self.paste_internal_buffer()
        if key in PASTE_UNDO_COMMANDS: return self.undo_last_paste()
        if key in REPLACE_UNDO_COMMANDS: return self.undo_last_replace()
        if key in CLEAR_FOCUSED_INPUT_COMMANDS: return self._clear_focused_input()
        if key in CLEAR_ALL_COMMANDS: return self.clear_pending_input()
        if key in AI_CORRECTION_COMMANDS: return self.ai_correct_selection_or_last()
        if key in WINDOW_MAXIMIZE_COMMANDS: return self.control_focused_window("maximize")
        if key in WINDOW_MINIMIZE_COMMANDS: return self.control_focused_window("minimize")
        if key in WINDOW_RESTORE_COMMANDS: return self.control_focused_window("restore")
        language=self.parse_language_switch(text)
        if language: return self.set_language_mode(language)
        media_action=self.parse_media_command(text)
        if media_action: return self.execute_media_control(*media_action)
        delete_count=self.parse_delete_count(text)
        if delete_count: return self.undo_last_emitted(delete_count)
        replacement=self.parse_correction(text)
        if replacement: return self.replace_selection_or_last(replacement)
        return False
    def copy_clip(self,text): self.root.clipboard_clear(); self.root.clipboard_append(text); self.root.update()
    def paste_last(self):
        if not self.last: self.log("No transcript to paste yet"); return
        self.copy_clip(self.last); self.emit_text(self.last)
    def copy_last(self):
        if not self.last: self.log("No transcript to copy yet"); return
        self.copy_clip(self.last); self.log("Last transcript copied")
    def cycle_output(self):
        order=["paste","clipboard","type"]; self.s.output_mode=order[(order.index(self.s.output_mode)+1)%len(order)] if self.s.output_mode in order else "paste"; self.vars["output_mode"].set(self.s.output_mode); save_settings(self.s); self.refresh_status(); self.log(f"Output mode: {self.s.output_mode}")
    def toggle_enter(self): self.s.auto_enter=not self.s.auto_enter; self.bools["auto_enter"].set(self.s.auto_enter); save_settings(self.s); self.refresh_status(); self.log(f"Auto enter: {self.s.auto_enter}")
    def show_doctor(self): self.log_text.insert("end","\n"+doctor(self.s)+"\n"); self.log_text.see("end")
    def poll(self):
        try:
            while True: self.log_text.insert("end",self.log_q.get_nowait()+"\n"); self.log_text.see("end")
        except queue.Empty: pass
        try:
            while True:
                kind,p=self.res_q.get_nowait()
                if kind=="captured": self.queue_audio(p["audio"],p["source"])
                elif kind=="done":
                    self.busy=False; self.refresh_status()
                    if not p["text"]: self.beep("error"); self.log(f"No speech detected from {p['source']}"); self._next(); continue
                    if self.is_voice_command_text(p["text"]):
                        if self.handle_voice_command(p["text"]): self.beep("done")
                        else: self.beep("error")
                        self._next(); continue
                    self._update_latest_transcript(p["text"]); append_history(self.last,{"elapsed_seconds":round(float(p["elapsed"]),3),"audio_seconds":round(float(p["audio_seconds"]),3),"output_mode":self.s.output_mode,"source":p["source"],"raw_text":p.get("raw_text","")}); self.emit_text(self.last); self.beep("done"); self.log(f"Transcript ready from {p['source']} in {float(p['elapsed']):.2f}s for {float(p['audio_seconds']):.2f}s audio"); self._next()
                elif kind=="error": self.busy=False; self.refresh_status(); self.beep("error"); self.log("Transcription failed"); self.log(p); self._next()
        except queue.Empty: pass
        self.root.after(80,self.poll)
    def poll_record(self):
        if self.rec.on:
            d=self.rec.duration(); self.refresh_status(f"Recording {d:.1f}s")
            if d>=self.s.max_record_seconds: self.log("Max recording length reached"); self.stop_recording()
            elif self.rec.should_stop(): self.log("Silence timeout reached"); self.stop_recording()
        self.root.after(120,self.poll_record)
    def poll_diagnostics(self):
        self.refresh_audio_status()
        self.root.after(120,self.poll_diagnostics)
    def poll_target(self):
        active=self.target_active()
        if active!=self.last_target: self.last_target=active; self.log("Target window active" if active else "Target window inactive")
        self.root.after(150,self.poll_target)
    def close(self):
        if self.rec.on:
            try: self.rec.stop()
            except Exception: pass
        if self.listen.on:
            try: self.listen.stop()
            except Exception: pass
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception: pass
        self.root.destroy()

def main():
    p=argparse.ArgumentParser(description=APP_NAME); p.add_argument("--doctor",action="store_true"); p.add_argument("--transcribe-file",type=Path); p.add_argument("--model",type=str); p.add_argument("--language",type=str); p.add_argument("--show-window",action="store_true"); a=p.parse_args(); s=load_settings()
    if a.model: s.whisper_model=a.model
    if a.language is not None: s.language=normalize_language_value(a.language)
    if a.doctor: print(doctor(s)); return
    if a.transcribe_file: print(transcribe_file(a.transcribe_file,s)); return
    if not acquire_single_instance():
        append_app_log("Another instance is already running; exiting duplicate launch")
        return
    launch_target=fg_info()
    root=tk.Tk(); style=ttk.Style()
    try: style.theme_use("vista")
    except Exception: pass
    App(root,launch_target=launch_target,show_window=a.show_window); root.mainloop()

if __name__=="__main__": main()
