# Codex Dictation

Codex CLI를 쓰면서 마이크로 말한 내용을 받아써서 터미널에 넣기 위한 Windows용 받아쓰기 도구입니다.

기본 설계:
- `전역 핫키`로 녹음 시작과 종료
- `항상 듣기(always-listen)` 모드 지원
- `로컬 faster-whisper`로 무료 받아쓰기
- `클립보드 복사`, `자동 붙여넣기`, `직접 타이핑` 모드 지원
- `Codex CLI` 창에 포커스를 둔 상태에서 바로 입력 가능
- `음성 명령`으로 취소, 정정, 엔터 가능
- `백그라운드 시작` 지원

## 설치

가상환경이 없다면 먼저 만듭니다.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements-dictation.txt
```

이미 이 저장소의 `.venv`를 쓰고 있다면 마지막 줄만 실행하면 됩니다.

## 실행

```powershell
.venv\Scripts\python.exe codex_dictation.py
```

배치 파일로 실행:

```powershell
run_codex_dictation.bat
```

Codex 터미널만 빠르게 열기:

```powershell
run_codex_terminal.bat
```

초기 기본 핫키:
- `F7`: 항상 듣기 On / Off
- `F8`: 녹음 시작 / 종료
- `F9`: 마지막 문장 다시 붙여넣기
- `F10`: 출력 모드 전환 (`paste -> clipboard -> type`)
- `F11`: 자동 Enter 전환

## AutoHotkey 런처

`launch_codex_dictation.ahk`를 AutoHotkey v2로 실행하면 전역 단축키를 쓸 수 있습니다.
이 저장소는 AutoHotkey 엔진을 `tools\AutoHotkey` 아래에 로컬로 배치해두었고, 시작프로그램 등록도 해둘 수 있습니다.

현재 기본 전역 단축키:
- `F1`: 받아쓰기 앱 백그라운드 실행 또는 최소화
- `F2`: 받아쓰기 앱 설정 창 보이기
- `F3`: 받아쓰기 앱 설정 창 숨기기
- `F4`: 받아쓰기 앱 종료

편하게 실행하는 방법:
1. `run_codex_hotkeys.bat` 또는 `launch_codex_dictation.ahk` 실행
2. 이후엔 `F1`만 누르면 됩니다
3. 시작프로그램에 등록해두면 로그인 후에도 자동으로 살아납니다

그러면 롤 켜듯이 사실상 `F1` 하나로 받아쓰기 백그라운드를 바로 띄울 수 있습니다.

## 추천 사용 흐름

1. Codex CLI 창에 포커스를 둡니다.
2. 받아쓰기 앱은 옆에 두거나 최소화합니다.
3. `F8`을 누르고 말합니다.
4. 다시 `F8`을 누르면 전사 후 Codex CLI에 텍스트가 들어갑니다.

항상 듣기 추천 흐름:

1. Codex CLI가 떠 있는 터미널 창으로 포커스를 옮깁니다.
2. 항상 듣기는 기본으로 켜져 있으니 별도 조작 없이 바로 씁니다.
3. 포커스된 창이 터미널이면 말이 감지되고, 침묵 뒤에 자동 전사되어 입력됩니다.
4. 전송하고 싶으면 `엔터`, `전송`, `보내` 중 하나를 말하면 Enter가 눌립니다.

추천 흐름:

1. 문장을 말해서 먼저 입력합니다.
2. 틀렸으면 `취소`, `방금 지워`, `정정 OO`, `그게 아니라 OO`, `아니 OO`처럼 말합니다.
3. 맞으면 `엔터`라고 말해서 제출합니다.

## 편의 기능

- 마이크 장치 선택
- Whisper 모델 크기 선택
- 언어 고정 (`ko`, `en`) 또는 자동 감지
- 전후 무음 트리밍
- 최대 녹음 길이 제한
- 무음 기반 자동 종료 옵션
- 빠른 문장 종료 감지
- 타겟 창이 활성화된 동안만 동작하는 항상 듣기 모드
- 마지막 결과 재붙여넣기
- 음성 명령
  - `엔터`, `전송`, `보내`, `보내줘`
  - `취소`, `지워`, `삭제`, `방금 지워`, `마지막 지워`
  - `정정 OO`, `그게 아니라 OO`, `아니 OO`, `아니고 OO`
- 기록 저장: `codex_dictation.history.jsonl`
- 설정 저장: `codex_dictation.settings.json`
- 활동 로그: `codex_dictation.log`

## 점검

환경 점검:

```powershell
.venv\Scripts\python.exe codex_dictation.py --doctor
```

파일 전사 테스트:

```powershell
.venv\Scripts\python.exe codex_dictation.py --transcribe-file some_audio.wav --model tiny --language ko
```

## 메모

- 기본 백엔드는 `faster-whisper`라서 로컬에서 무료로 돌 수 있습니다.
- 처음 특정 Whisper 모델을 고르면 모델 다운로드가 한 번 필요합니다.
- 자동 붙여넣기는 보통 `Ctrl+V`로 동작하므로, Codex CLI를 여는 터미널이 해당 붙여넣기 단축키를 받아야 합니다.
- 음성 정정은 `마지막으로 이 앱이 넣은 텍스트` 기준으로 동작합니다.
- 이미 `엔터`로 제출된 문장은 안전하게 되돌리기 어렵기 때문에, 보통은 `문장 -> 정정 필요시 말하기 -> 엔터` 흐름이 가장 안정적입니다.
