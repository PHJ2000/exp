# Codex Dictation

Codex CLI와 일반 입력창에서 마이크로 말한 내용을 받아써서 넣기 위한 Windows용 받아쓰기 도구입니다.

기본 설계:
- `전역 핫키`로 녹음 시작과 종료
- `항상 듣기(always-listen)` 모드 지원
- `로컬 faster-whisper`로 무료 받아쓰기
- `클립보드 복사`, `자동 붙여넣기`, `직접 타이핑` 모드 지원
- `Codex CLI`와 포커스된 일반 입력창에서 바로 입력 가능
- `음성 명령`으로 보내기, 삭제, 교체, 복사, 붙여넣기, 잘라내기, 현재 입력창 전체 비우기, 언어 전환, 창 상태 제어, 미디어 제어 가능
- 선택적으로 `로컬 LLM` 후처리 교정 지원
- `백그라운드 시작` 지원

## 비용

- 이 받아쓰기 도구 자체는 `로컬 faster-whisper` 기반이라 추가 API 비용이 들지 않습니다.
- 즉 받아쓰기 기능만 놓고 보면 별도 과금 없이 `내 PC 자원`으로 동작합니다.
- 다만 `Codex CLI` 자체 사용 비용은 이 도구와 별개입니다.

## 환경

- 현재 이 저장소 기준으로는 루트의 `.venv`, `tools\AutoHotkey`, 그리고 `codex-dictation\` 디렉토리 기준으로 실행 흐름이 맞춰져 있습니다.
- 그래서 이 PC처럼 이미 세팅된 환경에서는 보통 추가 설정 없이 바로 실행하면 됩니다.
- 새 PC나 새 환경으로 옮길 때만 아래 정도가 필요합니다.
  - Python 설치
  - `.venv` 생성
  - `pip install -r codex-dictation\requirements-dictation.txt`
  - 마이크 장치 인식 확인
- CUDA GPU는 있으면 더 빠르지만 필수는 아닙니다.

## 설치

가상환경이 없다면 먼저 만듭니다.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r codex-dictation\requirements-dictation.txt
```

이미 이 저장소의 `.venv`를 쓰고 있다면 마지막 줄만 실행하면 됩니다.

## 단일 실행 파일 빌드

Python 설치와 가상환경 준비가 번거로운 PC로 옮길 때는 `PyInstaller`로 단일 `exe`를 만들 수 있습니다.

```powershell
codex-dictation\build_codex_dictation_exe.ps1
```

빌드가 끝나면 아래 파일이 생성됩니다.

```text
codex-dictation\dist\CodexDictation.exe
```

메모:
- 런타임 데이터는 기본적으로 `%LOCALAPPDATA%\CodexDictation\` 아래에 저장됩니다.
- 예전 버전처럼 `exe` 또는 소스 폴더 옆에 `codex_dictation.settings.json`, `codex_dictation.history.jsonl`, `codex_dictation.log`가 남아 있으면 첫 실행 때 새 위치로 이어받습니다.
- 첫 실행 시 `faster-whisper` 모델이 PC에 없다면 모델 다운로드는 여전히 한 번 필요합니다.
- 전역 핫키는 기존처럼 `tools\AutoHotkey` 또는 `run_codex_hotkeys.bat` 흐름을 같이 쓰는 것이 가장 편합니다.

## 실행

```powershell
.venv\Scripts\python.exe codex-dictation\codex_dictation.py
```

`codex-dictation` 폴더 안의 런처로 실행:

```powershell
codex-dictation\run_codex_dictation.bat
```

`CodexDictation.exe`가 `codex-dictation\dist\` 아래에 있으면 같은 런처가 자동으로 `exe`를 우선 실행합니다.

Codex 터미널만 빠르게 열기:

```powershell
codex-dictation\run_codex_terminal.bat
```

## AutoHotkey 런처

`codex-dictation\launch_codex_dictation.ahk`를 AutoHotkey v2로 실행하면 전역 단축키를 쓸 수 있습니다.
이 저장소는 AutoHotkey 엔진을 `tools\AutoHotkey` 아래에 로컬로 배치해두었고, 시작프로그램 등록도 해둘 수 있습니다.

현재 기본 전역 단축키:
- `F1`: 받아쓰기 앱 백그라운드 실행 또는 최소화
- `F2`: 받아쓰기 앱 설정 창 보이기
- `F3`: 받아쓰기 앱 설정 창 숨기기
- `F4`: 받아쓰기 앱 종료

`F1`로 실행할 때는 현재 작업 중이던 창으로 다시 돌아가도록 맞춰져 있어서, 터미널뿐 아니라 일반 입력창에서도 바로 이어서 말할 수 있습니다.

편하게 실행하는 방법:
1. `codex-dictation\run_codex_hotkeys.bat` 실행
2. 이후엔 `F1`만 누르면 됩니다
3. 시작프로그램에 등록해두면 로그인 후에도 자동으로 살아납니다

## 추천 사용 흐름

1. 텍스트를 넣고 싶은 입력창이나 터미널에 포커스를 둡니다.
2. 항상 듣기는 기본으로 켜져 있으니 별도 조작 없이 바로 씁니다.
3. 포커스된 창 안에서 실제 입력 포커스나 캐럿이 잡힌 상태면 말이 감지되고, 침묵 뒤에 자동 전사되어 입력됩니다.
4. 맞으면 `보내`, 틀리면 `지워`, `두 번 지워`, `세 번 지워`, `다 지워`, `전체 비워`, `다시 OO`처럼 말합니다.
5. 선택된 텍스트가 있으면 `복사`, `잘라`, `다시 OO`로 편집할 수 있고, 저장한 내용은 `붙여넣기`나 `1번 붙여넣기`처럼 다시 넣을 수 있습니다.

## 편의 기능

- 마이크 장치 선택
- Whisper 모델 크기 선택
- 로컬 LLM 교정
  - 기본값은 `꺼짐`
  - 기본 프로필은 `균형 = gemma3:4b`
  - `정확도 = gemma3:12b`로 바로 바꿀 수 있습니다.
  - `직접지정`으로 두면 모델명을 직접 입력할 수 있습니다.
  - 설정 UI와 설정 파일에서 사용 여부, 프로필, 모델, `Ollama` URL, 타임아웃을 바꿀 수 있습니다.
  - 음성 명령은 기존처럼 먼저 처리하고, `정정`이라고 말했을 때만 마지막 문장이나 선택 영역을 AI가 다듬습니다.
- 언어 전환
  - 기본값은 `자동`
  - 설정 UI와 설정 파일에서 `자동`, `한국어`, `영어`로 바꿀 수 있습니다.
  - 음성으로도 `자동`, `한국어`, `영어`라고 말해 바로 전환할 수 있습니다.
- 전후 무음 트리밍
- 최대 녹음 길이 제한
- 빠른 문장 종료 감지
- 타겟 창이 활성화된 동안만 동작하는 항상 듣기 모드
- 스피커 재생음보다 입 가까운 발화를 더 우선하도록 시작 감지를 보수적으로 조정
- 일반 앱은 `포커스된 텍스트 입력 상태`일 때만 받아쓰기 대상으로 판정
- 브라우저 계열 앱은 입력창 판정이 약한 경우가 있어서 현재는 창 포커스 기준 fallback도 함께 사용
- Electron 계열 앱(`슬랙`, `디스코드`)과 `윈도우 검색창`도 현재 fallback 대상으로 포함
- 시스템 UI 계열(`설정 앱`, `파일 탐색기`, `Win+R 실행 창`)도 별도 fallback 대상으로 포함
- 마지막 결과 재붙여넣기
- 음성 명령
  - 메인 명령은 `보내`, `지워`, `다 지워`, `전체 비워`, `다시 OO`만 기억하면 됩니다.
  - `지워`는 마지막 한 덩어리를 지웁니다.
  - `두 번 지워`, `세 번 지워`, `5번 지워`처럼 최근 여러 덩어리를 한 번에 지울 수 있습니다.
  - `복사`, `붙여넣기`, `잘라`로 선택된 텍스트와 내부 버퍼를 다룰 수 있습니다.
  - `정정`은 선택 영역이 있으면 그 부분을, 선택이 없으면 마지막 받아쓰기 문장을 로컬 LLM으로 보수적으로 다듬습니다.
  - `취소`는 방금 `붙여넣기`한 내용만 되돌립니다.
  - `되돌려`는 방금 `다시 OO`로 바꾼 내용을 복구합니다.
  - `1번 복사`, `2번 잘라`, `3번 붙여넣기`처럼 슬롯 버퍼 1~10번도 사용할 수 있습니다.
  - 실제 인식은 발음 흔들림을 감안해 `보내`, `지워`, `다 지워`, `전체 비워`, `다시` 계열에 몇 가지 변형 표현도 같이 받습니다.
  - `자동`, `한국어`, `영어`로 STT 언어를 바로 바꿀 수 있습니다.
  - `최대화`, `최소화`, `복원`으로 현재 포커스된 작업 창 상태를 바꿀 수 있습니다.
  - `이스케이프`, `나가기`, `일시정지`, `재생`, `앞으로 감기`, `뒤로 감기`, `세 번 앞으로 감기`, `두 번 뒤로 감기`처럼 미디어 제어 명령도 사용할 수 있습니다.
- 기록 저장: `%LOCALAPPDATA%\CodexDictation\codex_dictation.history.jsonl`
- 설정 저장: `%LOCALAPPDATA%\CodexDictation\codex_dictation.settings.json`
- 활동 로그: `%LOCALAPPDATA%\CodexDictation\codex_dictation.log`
- 공유용 마스킹: `python codex-dictation/codex_share_safe.py --input %LOCALAPPDATA%\CodexDictation\codex_dictation.log --output outputs\codex_dictation.log.share-safe`
- 입력 감도 보정: 설정의 `Input Gain`으로 마이크 입력 크기를 조절할 수 있습니다. 기본값 `1.0`은 기존 동작과 동일하고, 작은 마이크는 `1.2`~`2.0` 정도로 키워 볼 수 있습니다.
- 소음 환경 튜닝: `Noise Gate Threshold`로 작은 배경 소음을 잘라내고, `Audio Preset`으로 조용한 방/보통/시끄러운 방 기준값을 빠르게 적용할 수 있습니다.
- 오디오 프로필: 현재 마이크/always-listen 관련 값을 이름 붙여 저장하고, 나중에 `Apply Profile`로 다시 불러올 수 있습니다. `Audio Preset`은 빠른 기본값이고, 오디오 프로필은 사용자가 저장한 세부 튜닝 묶음입니다.
- always-listen 자동 튜닝: 최근 감지 패턴을 바탕으로 `Input Gain`, `Always Listen Pre-roll Seconds`, `Speech End Silence Seconds` 추천값을 계산하고, 설정 화면에서 적용/되돌리기할 수 있습니다.
- 상태 가시화: 상단에 현재 `rms`, `threshold`, `voice` 감지 상태와 마지막 LLM 교정 상태를 표시합니다.

## 로컬 LLM 교정

- 목적은 `STT 오인식 후처리`입니다.
- 기본 동작은 `명령어 우선`, 그리고 사용자가 `정정`을 말했을 때만 AI 교정을 수행하는 방식입니다.
- 즉 `보내`, `지워`, `복사` 같은 명령은 LLM에 보내지지 않습니다.
- 현재 기본 런타임 가정은 `Ollama`입니다.
- 기본 프로필은 `균형`이고, 이때 모델은 `gemma3:4b`입니다.
- `정확도` 프로필을 고르면 `gemma3:12b`를 사용합니다.
- `직접지정` 프로필을 고르면 `LLM Model` 입력값을 그대로 사용합니다.

권장 흐름:
1. `Ollama`를 실행합니다.
2. 원하는 모델을 준비합니다.
  예: `gemma3:4b`, `gemma3:12b`
3. 설정에서 `Enable local LLM correction command`를 켭니다.
4. 필요하면 `LLM Profile`을 `균형` 또는 `정확도`로 고릅니다.
5. 평소엔 그대로 받아쓰기합니다.
6. 결과가 이상하면 `정정`이라고 말합니다.
7. 선택 영역이 있으면 그 부분을, 선택이 없으면 현재 입력 중인 문장을 AI가 보수적으로 다듬습니다.

주의점:
- 교정은 `보수적`으로만 하도록 설계되어 있습니다.
- 원문과 차이가 너무 커지면 더 보수적인 재시도를 한 번 하고, 그래도 무리면 원문을 그대로 유지합니다.
- 교체 단계에서 입력이 실패해도 원문 복구를 우선 시도합니다.
- 모델이 꺼져 있거나 URL이 틀리면, 받아쓰기는 계속 되지만 LLM 교정만 건너뜁니다.
- 응답 속도는 로컬 모델 크기와 PC 성능에 영향을 받습니다.

## 점검

환경 점검:

```powershell
.venv\Scripts\python.exe codex-dictation\codex_dictation.py --doctor
```

파일 전사 테스트:

```powershell
.venv\Scripts\python.exe codex-dictation\codex_dictation.py --transcribe-file some_audio.wav --model tiny --language ko
```

## 메모

- 기본 백엔드는 `faster-whisper`라서 로컬에서 무료로 돌 수 있습니다.
- 로컬 LLM 교정을 쓰려면 별도로 `Ollama` 같은 런타임과 모델 준비가 필요합니다.
- 처음 특정 Whisper 모델을 고르면 모델 다운로드가 한 번 필요합니다.
- 자동 붙여넣기는 보통 `Ctrl+V`로 동작하므로, 포커스된 앱이 해당 붙여넣기 단축키를 받아야 합니다.
- `지워` 계열은 기본적으로 `마지막으로 이 앱이 넣은 텍스트`를 지웁니다.
- `다 지워`는 아직 보내지지 않은 현재 입력 줄 전체를 지웁니다.
- `전체 비워`는 현재 포커스된 입력창 내용을 컨텍스트와 무관하게 Ctrl+A 후 Delete로 통째로 비우는 보수적 best-effort 명령입니다.
- `복사`와 `잘라`는 현재 선택된 텍스트를 내부 버퍼에 저장합니다.
- `붙여넣기`는 내부 버퍼 텍스트를 현재 포커스 위치에 넣습니다.
- `다시 OO`는 선택 영역이 있으면 그 부분을 바꾸고, 선택이 없으면 마지막 받아쓰기 덩어리를 바꿉니다.
- `최대화`, `최소화`, `복원`은 현재 포커스된 작업 창에만 적용되며, 받아쓰기 설정 창 자체에는 적용하지 않습니다.
- `이스케이프`, `나가기`, `앞으로 감기`, `뒤로 감기`는 현재 포커스된 창에 방향키/esc 단축키를 보내는 방식이라 유튜브 같은 웹 플레이어에서 특히 잘 맞습니다.
- `일시정지`, `재생`은 시스템 `play/pause media` 키를 보내는 방식이라 브라우저 탭이나 일반 미디어 플레이어에서도 비교적 잘 맞습니다.
- 일반 받아쓰기 뒤에는 공백 한 칸이 자동으로 붙습니다.
- 언어 기본값은 `자동`이며, 필요할 때만 `한국어`나 `영어`로 고정하면 됩니다.
- 실제 인식에서는 `보내`, `지워`, `다 지워`, `다시`의 발음 흔들림을 일부 자동으로 허용합니다.
- 이미 `보내`로 제출된 문장은 안전하게 되돌리기 어렵기 때문에, 보통은 `문장 -> 다시 말하기 -> 보내` 흐름이 가장 안정적입니다.

