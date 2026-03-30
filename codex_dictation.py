from __future__ import annotations
import argparse, ctypes, json, queue, sys, tempfile, threading, time, traceback
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import numpy as np, sounddevice as sd, soundfile as sf, tkinter as tk
from tkinter import messagebox, ttk

APP_NAME="Codex Dictation"; ROOT=Path(__file__).resolve().parent
SETTINGS_PATH=ROOT/"codex_dictation.settings.json"; HISTORY_PATH=ROOT/"codex_dictation.history.jsonl"; LOG_PATH=ROOT/"codex_dictation.log"
TERMINALS={"windowsterminal.exe","wezterm-gui.exe","conhost.exe","powershell.exe","pwsh.exe","cmd.exe","mintty.exe","alacritty.exe","rio.exe","code.exe","cursor.exe"}
def _command_aliases(*values:str)->set[str]:
    out=set()
    for value in values:
        cleaned="".join(ch for ch in value.strip().lower() if ch not in " \t\r\n.,!?;:\"'")
        if cleaned: out.add(cleaned)
    return out

ENTER_COMMANDS=_command_aliases("보내","보내요","보네","보네요","보내줘","보내 줘","보내줘요","보내 줘요")
CLEAR_ALL_COMMANDS=_command_aliases("다 지워","다 지어","다 치워","다 지워줘","다 치워줘","전부 지워","전부 지어","전부 치워","전체 지워","전체 지어","전체 치워","모두 지워","모두 지어","모두 치워","싹 지워","싹 지어","몽땅 지워")
DELETE_SOUND_ALIASES=_command_aliases("지워","지어","치워","지워요","지어요","치워요","지워줘","지어줘","치워줘","지워줘요","치워줘요","지우","치우")
CORRECTION_PREFIXES=("다시 말해줘 ", "다시말해줘 ", "다시 말해 ", "다시말해 ", "다시 해 ", "다시해 ", "다시 ", "다시, ")
COMMAND_PROMPT="보내 보내요 보네 보내줘 지워 지어 치워 지워요 다 지워 다 치워 전부 지워 전체 지워 모두 지워 다시 다시 말해 다시 말해줘"
SINGLE_INSTANCE_MUTEX_NAME="Local\\CodexDictationSingleton"
_single_instance_handle=None
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
    input_device:str=""; sample_rate:int=16000; channels:int=1; whisper_model:str="large-v3-turbo"; whisper_device:str="auto"; whisper_compute_type:str="auto"
    language:str="ko"; initial_prompt:str=""; record_hotkey:str="f8"; always_listen_hotkey:str="f7"; paste_last_hotkey:str="f9"
    toggle_output_hotkey:str="f10"; toggle_enter_hotkey:str="f11"; output_mode:str="type"; paste_hotkey:str="ctrl+v"; auto_enter:bool=False
    trim_silence:bool=True; trim_threshold:float=0.008; normalize_whitespace:bool=True; max_record_seconds:int=45; min_record_seconds:float=0.25
    beep_feedback:bool=False; keep_window_on_top:bool=False; enable_auto_stop:bool=False; auto_stop_silence_seconds:float=0.65
    always_listen_enabled:bool=True; always_listen_preroll_seconds:float=0.25

@dataclass
class WinInfo:
    hwnd:int; pid:int; title:str; cls:str; proc:str

def load_settings()->Settings:
    if not SETTINGS_PATH.exists():
        s=Settings(); save_settings(s); return s
    data=json.loads(SETTINGS_PATH.read_text(encoding="utf-8")); ok={f.name for f in Settings.__dataclass_fields__.values()}
    return Settings(**{k:v for k,v in data.items() if k in ok})

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

def fmt_info(info:WinInfo|None)->str:
    if not info: return "No active window"
    return f"{info.proc or 'unknown'} | {(info.title or '(no title)')} | {info.cls or 'unknown'} | hwnd={info.hwnd}"

def is_terminal(info:WinInfo|None)->bool:
    return bool(info and (info.proc in TERMINALS or info.cls in {"CASCADIA_HOSTING_WINDOW_CLASS","ConsoleWindowClass"} or any(x in (info.title or "").lower() for x in ["terminal","powershell","pwsh","cmd"])))

def is_codex_terminal(info:WinInfo|None)->bool:
    return bool(info and is_terminal(info) and ("codex" in info.title.lower() or has_codex(info.pid)))

def is_target_terminal(info:WinInfo|None)->bool:
    return bool(info and (is_codex_terminal(info) or is_terminal(info)))

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

def focus_best_terminal()->bool:
    user32=ctypes.windll.user32
    wins=list_terminal_windows()
    if not wins:
        return False
    target=wins[0]
    try:
        user32.ShowWindow(target.hwnd, 9)
        user32.SetForegroundWindow(target.hwnd)
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
        segs,_=self._model(s).transcribe(path.as_posix(),language=(s.language or None),initial_prompt=initial_prompt_for_commands(s),vad_filter=True,beam_size=1,best_of=1,condition_on_previous_text=False)
        return " ".join(x.text.strip() for x in segs).strip()

class Recorder:
    def __init__(self,s:Settings,log): self.s=s; self.log=log; self.stream=None; self.chunks=[]; self.lock=threading.Lock(); self.t0=0.0; self.last_voice=0.0; self.on=False
    def start(self):
        if self.on: return
        self.chunks=[]; self.t0=time.monotonic(); self.last_voice=self.t0
        self.stream=sd.InputStream(samplerate=self.s.sample_rate,channels=self.s.channels,dtype="float32",device=resolve_input_device(self.s.input_device),callback=self._cb); self.stream.start(); self.on=True; self.log("Recording started")
    def stop(self)->np.ndarray:
        if not self.on: return np.zeros(0,dtype=np.float32)
        self.stream.stop(); self.stream.close(); self.stream=None; self.on=False
        with self.lock: audio=np.concatenate(self.chunks).astype(np.float32) if self.chunks else np.zeros(0,dtype=np.float32)
        self.log(f"Recording stopped: {len(audio)/self.s.sample_rate:.2f}s"); return audio
    def duration(self)->float: return time.monotonic()-self.t0 if self.on else 0.0
    def should_stop(self)->bool: return self.on and self.s.enable_auto_stop and self.duration()>=self.s.min_record_seconds and time.monotonic()-self.last_voice>=self.s.auto_stop_silence_seconds
    def _cb(self,indata,frames,time_info,status):
        if status: self.log(f"Audio status: {status}")
        mono=indata[:,0].copy()
        with self.lock: self.chunks.append(mono)
        if mono.size and float(np.sqrt(np.mean(np.square(mono))))>max(self.s.trim_threshold,0.008): self.last_voice=time.monotonic()

class AlwaysListen:
    def __init__(self,s:Settings,log,on_audio,target_active): self.s=s; self.log=log; self.on_audio=on_audio; self.target_active=target_active; self.stream=None; self.on=False; self.lock=threading.Lock(); self.pre=deque(); self.pre_n=0; self.chunks=[]; self.n=0; self.last_voice=0.0
    def start(self):
        if self.on: return
        self.reset(); self.stream=sd.InputStream(samplerate=self.s.sample_rate,channels=self.s.channels,dtype="float32",device=resolve_input_device(self.s.input_device),blocksize=max(int(self.s.sample_rate*0.06),512),callback=self._cb); self.stream.start(); self.on=True; self.log("Always-listen started")
    def stop(self):
        if not self.on: return
        self.stream.stop(); self.stream.close(); self.stream=None; self.on=False; self.reset(); self.log("Always-listen stopped")
    def reset(self):
        with self.lock: self.pre.clear(); self.pre_n=0; self.chunks=[]; self.n=0; self.last_voice=0.0
    def _push_pre(self,mono):
        self.pre.append(mono); self.pre_n+=len(mono); limit=int(self.s.sample_rate*self.s.always_listen_preroll_seconds)
        while self.pre and self.pre_n>limit: self.pre_n-=len(self.pre.popleft())
    def _finalize(self):
        if not self.chunks: return
        audio=np.concatenate(self.chunks).astype(np.float32); self.chunks=[]; self.n=0; self.last_voice=0.0; self.on_audio(audio,"always_listen")
    def _cb(self,indata,frames,time_info,status):
        if status: self.log(f"Always-listen audio status: {status}")
        mono=indata[:,0].copy()
        if not self.target_active(): self.reset(); return
        rms=float(np.sqrt(np.mean(np.square(mono))) if mono.size else 0.0); voice=rms>=max(self.s.trim_threshold,0.008); now=time.monotonic()
        with self.lock:
            if not self.chunks:
                self._push_pre(mono)
                if voice: self.chunks=list(self.pre); self.n=sum(len(x) for x in self.chunks); self.pre.clear(); self.pre_n=0; self.last_voice=now; self.log("Voice detected in target window")
            else:
                self.chunks.append(mono); self.n+=len(mono)
                if voice: self.last_voice=now
                if self.n/max(self.s.sample_rate,1)>=self.s.max_record_seconds or now-self.last_voice>=self.s.auto_stop_silence_seconds: self._finalize()

def doctor(settings:Settings|None=None)->str:
    lines=[f"{APP_NAME} doctor","-"*40,f"Python: {sys.version.split()[0]}",f"Settings: {SETTINGS_PATH}",f"History: {HISTORY_PATH}",f"Log: {LOG_PATH}"]
    if settings: lines+= [f"Always listen enabled: {settings.always_listen_enabled}"]
    try:
        devs=get_input_devices(); lines.append(f"Input devices: {len(devs)}")
        for d in devs[:10]: lines.append(f"  - [{d['index']}] {d['name']} ({d['sample_rate']} Hz)")
    except Exception as e: lines.append(f"Input devices: failed ({e})")
    info=fg_info(); lines += [f"Foreground window: {fmt_info(info)}",f"Looks like terminal: {is_terminal(info)}",f"Looks like Codex terminal: {is_codex_terminal(info)}",f"Accepts as target terminal: {is_target_terminal(info)}"]
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
    text=WhisperBackend().transcribe(file_path,settings); return normalize_text(text) if settings.normalize_whitespace else text

class App:
    def __init__(self,root:tk.Tk):
        self.root=root; self.root.title(APP_NAME); self.root.geometry("980x780"); self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.s=load_settings()
        if not self.s.input_device: self.s.input_device = default_input_device_name()
        save_settings(self.s)
        self.log_q=queue.Queue(); self.res_q=queue.Queue(); self.jobs=queue.Queue(); self.backend=WhisperBackend(); self.rec=Recorder(self.s,self.log); self.listen=AlwaysListen(self.s,self.log,self.enqueue_audio,self.target_active)
        self.busy=False; self.last=""; self.last_emitted=""; self.last_submitted=False; self.pending_text=""; self.pending_segments=[]; self.last_target=None; self.t=None; self.startup_minimized=False
        self.vars={k:tk.StringVar(value=str(getattr(self.s,k))) for k in ["input_device","sample_rate","whisper_model","whisper_device","whisper_compute_type","language","initial_prompt","record_hotkey","always_listen_hotkey","paste_last_hotkey","toggle_output_hotkey","toggle_enter_hotkey","output_mode","paste_hotkey","max_record_seconds","auto_stop_silence_seconds","always_listen_preroll_seconds"]}
        self.bools={k:tk.BooleanVar(value=getattr(self.s,k)) for k in ["auto_enter","trim_silence","normalize_whitespace","beep_feedback","keep_window_on_top","enable_auto_stop","always_listen_enabled"]}
        self.status=tk.StringVar(value="Idle"); self.target=tk.StringVar(value="")
        self.devices=[d["name"] for d in get_input_devices()]; self._ui(); self.refresh_target(); self.refresh_status("Starting"); self.root.after(50,self.bootstrap_after_launch); self.root.after(80,self.poll); self.root.after(120,self.poll_record); self.root.after(150,self.poll_target)
    def _ui(self):
        self.root.columnconfigure(0,weight=1); self.root.rowconfigure(3,weight=1); head=ttk.Frame(self.root,padding=12); head.grid(row=0,column=0,sticky="ew"); head.columnconfigure(1,weight=1)
        ttk.Label(head,text=APP_NAME,font=("Segoe UI",18,"bold")).grid(row=0,column=0,sticky="w"); ttk.Label(head,textvariable=self.status,font=("Segoe UI",10,"bold")).grid(row=0,column=1,sticky="e"); ttk.Label(head,textvariable=self.target).grid(row=1,column=0,columnspan=2,sticky="w",pady=(6,0)); ttk.Label(head,text="F7 항상 듣기, F8 수동 녹음, F9 마지막 문장, F10 출력 모드, F11 Enter 전환 | 음성 명령: 보내, 지워, 다 지워, 다시 ...").grid(row=2,column=0,columnspan=2,sticky="w",pady=(6,0))
        top=ttk.Frame(self.root,padding=(12,0,12,0)); top.grid(row=1,column=0,sticky="nsew"); top.columnconfigure((0,1),weight=1); left=ttk.LabelFrame(top,text="Recording",padding=12); right=ttk.LabelFrame(top,text="Output, Target, Hotkeys",padding=12); left.grid(row=0,column=0,sticky="nsew",padx=(0,6)); right.grid(row=0,column=1,sticky="nsew",padx=(6,0))
        self._combo(left,"Input Device","input_device",self.devices,0); self._entry(left,"Sample Rate","sample_rate",1); self._combo(left,"Whisper Model","whisper_model",["tiny","base","small","medium","large-v3-turbo"],2); self._combo(left,"Whisper Device","whisper_device",["auto","cpu","cuda"],3); self._combo(left,"Compute Type","whisper_compute_type",["auto","int8","int8_float16","float16","float32"],4); self._entry(left,"Language","language",5); self._entry(left,"Initial Prompt","initial_prompt",6); self._entry(left,"Max Record Seconds","max_record_seconds",7); self._entry(left,"Speech End Silence Seconds","auto_stop_silence_seconds",8); self._entry(left,"Always Listen Pre-roll Seconds","always_listen_preroll_seconds",9)
        self._check(left,"Trim leading and trailing silence","trim_silence",10); self._check(left,"Normalize whitespace","normalize_whitespace",11); self._check(left,"Enable manual mode auto stop","enable_auto_stop",12); self._check(left,"Play feedback beeps","beep_feedback",13); self._check(left,"Keep window on top","keep_window_on_top",14)
        self._combo(right,"Output Mode","output_mode",["paste","clipboard","type"],0); self._entry(right,"Paste Hotkey","paste_hotkey",1); self._check(right,"Press Enter after output","auto_enter",2); self._check(right,"Always listen when target window is focused","always_listen_enabled",3); self._entry(right,"Always Listen Hotkey","always_listen_hotkey",4); self._entry(right,"Record Hotkey","record_hotkey",5); self._entry(right,"Paste Last Hotkey","paste_last_hotkey",6); self._entry(right,"Toggle Output Hotkey","toggle_output_hotkey",7); self._entry(right,"Toggle Enter Hotkey","toggle_enter_hotkey",8)
        btn=ttk.Frame(right); btn.grid(row=9,column=0,columnspan=2,sticky="ew",pady=(14,0)); [btn.columnconfigure(i,weight=1) for i in range(3)]
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
    def refresh_status(self,activity="Idle"): self.status.set(f"{activity} | {self.s.output_mode.upper()}{' + ENTER' if self.s.auto_enter else ''}{' | ALWAYS-ON' if self.listen.on else ''}")
    def refresh_target(self): self.target.set("Target: focused terminal window")
    def bootstrap_after_launch(self):
        self.minimize_after_startup()
        self.focus_terminal_after_startup()
        self.refresh_status("Warming up")
        self.warmup_model()
        self.register_hotkeys()
        self.sync_listener()
        self.log("Ready")
    def minimize_after_startup(self):
        if self.startup_minimized: return
        self.startup_minimized=True
        try:
            self.root.iconify()
            self.log("Window minimized after startup")
        except Exception as e:
            self.log(f"Startup minimize skipped: {e}")
    def focus_terminal_after_startup(self):
        try:
            if self.target_active():
                return
            if focus_best_terminal():
                self.log("Focused terminal after startup")
        except Exception as e:
            self.log(f"Startup terminal focus skipped: {e}")
    def save_from_ui(self):
        for k,v in self.vars.items():
            cur=getattr(self.s,k); raw=v.get().strip()
            if isinstance(cur,int): setattr(self.s,k,int(raw or "0"))
            elif isinstance(cur,float): setattr(self.s,k,float(raw or "0"))
            else: setattr(self.s,k,raw)
        for k,v in self.bools.items(): setattr(self.s,k,bool(v.get()))
        save_settings(self.s); self.rec.s=self.s; self.listen.s=self.s; self.root.attributes("-topmost",self.s.keep_window_on_top); self.refresh_target(); self.refresh_status(); self.log("Settings saved")
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
        return is_target_terminal(info)
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
            sf.write(path,audio,self.s.sample_rate); text=self.backend.transcribe(path,self.s); text=normalize_text(text) if self.s.normalize_whitespace else text; self.res_q.put(("done",{"text":text,"elapsed":time.perf_counter()-t0,"audio_seconds":len(audio)/self.s.sample_rate,"source":source}))
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
    def _update_latest_transcript(self,text):
        self.last=text; self.txt.delete("1.0",tk.END); self.txt.insert("1.0",text); self.copy_clip(text)
    def emit_text(self,text,remember=True,press_enter:bool|None=None,append_space=True):
        try: import keyboard
        except Exception as e: self.log(f"Output hotkeys unavailable: {e}"); return
        sent_enter=self.s.auto_enter if press_enter is None else press_enter
        payload=f"{text} " if text and append_space and not sent_enter else text
        if self.s.output_mode=="clipboard": self.log("Copied transcript to clipboard"); return
        if self.s.output_mode=="type": keyboard.write(payload,delay=0)
        else: time.sleep(0.05); keyboard.press_and_release(self.s.paste_hotkey)
        if sent_enter: time.sleep(0.03); keyboard.press_and_release("enter")
        if remember:
            self.last_emitted=payload
            self.last_submitted=bool(sent_enter)
            if sent_enter:
                self.pending_text=""
                self.pending_segments=[]
            else:
                self.pending_text=f"{self.pending_text}{payload}"
                self.pending_segments.append(payload)
        self.log(f"Transcript sent via {self.s.output_mode}")
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
        return True
    def replace_last_emitted(self,text:str)->bool:
        if not self.pending_segments: self.log("Voice command ignored: no recent text to replace"); return False
        if self.last_submitted: self.log("Voice command ignored: last text was already submitted"); return False
        last_segment=self.pending_segments[-1]
        if not self._backspace_text(last_segment): return False
        self.pending_segments=self.pending_segments[:-1]
        if self.pending_text.endswith(last_segment): self.pending_text=self.pending_text[:-len(last_segment)]
        self._update_latest_transcript(text); self.emit_text(text,remember=True,press_enter=False,append_space=True)
        self.log("Voice command executed: replace last emitted text")
        return True
    def _command_key(self,text:str)->str:
        return "".join(ch for ch in text.strip().lower() if ch not in " \t\r\n.,!?;:\"'")
    def parse_correction(self,text:str)->str:
        raw=text.strip()
        lowered=raw.lower()
        for prefix in CORRECTION_PREFIXES:
            if lowered.startswith(prefix):
                return raw[len(prefix):].strip(" \t\r\n.,!?;:\"'")
        return ""
    def parse_delete_count(self,text:str)->int:
        raw=text.strip().lower()
        compact=self._command_key(text)
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
    def handle_voice_command(self,text:str)->bool:
        key=self._command_key(text)
        if not key: return False
        if key in ENTER_COMMANDS: return self.send_enter()
        if key in CLEAR_ALL_COMMANDS: return self.clear_pending_input()
        delete_count=self.parse_delete_count(text)
        if delete_count: return self.undo_last_emitted(delete_count)
        replacement=self.parse_correction(text)
        if replacement: return self.replace_last_emitted(replacement)
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
                    if self.handle_voice_command(p["text"]): self.beep("done"); self._next(); continue
                    self._update_latest_transcript(p["text"]); append_history(self.last,{"elapsed_seconds":round(float(p["elapsed"]),3),"audio_seconds":round(float(p["audio_seconds"]),3),"output_mode":self.s.output_mode,"source":p["source"]}); self.emit_text(self.last); self.beep("done"); self.log(f"Transcript ready from {p['source']} in {float(p['elapsed']):.2f}s for {float(p['audio_seconds']):.2f}s audio"); self._next()
                elif kind=="error": self.busy=False; self.refresh_status(); self.beep("error"); self.log("Transcription failed"); self.log(p); self._next()
        except queue.Empty: pass
        self.root.after(80,self.poll)
    def poll_record(self):
        if self.rec.on:
            d=self.rec.duration(); self.refresh_status(f"Recording {d:.1f}s")
            if d>=self.s.max_record_seconds: self.log("Max recording length reached"); self.stop_recording()
            elif self.rec.should_stop(): self.log("Silence timeout reached"); self.stop_recording()
        self.root.after(120,self.poll_record)
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
    p=argparse.ArgumentParser(description=APP_NAME); p.add_argument("--doctor",action="store_true"); p.add_argument("--transcribe-file",type=Path); p.add_argument("--model",type=str); p.add_argument("--language",type=str); a=p.parse_args(); s=load_settings()
    if a.model: s.whisper_model=a.model
    if a.language is not None: s.language=a.language
    if a.doctor: print(doctor(s)); return
    if a.transcribe_file: print(transcribe_file(a.transcribe_file,s)); return
    if not acquire_single_instance():
        append_app_log("Another instance is already running; exiting duplicate launch")
        return
    root=tk.Tk(); style=ttk.Style()
    try: style.theme_use("vista")
    except Exception: pass
    App(root); root.mainloop()

if __name__=="__main__": main()
