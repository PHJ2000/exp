# Python v0 구조와 실행 방식

이 문서는 `meeting-summary-tool`의 Python 기반 v0 구조와 실행 방식을 정리합니다.

## 현재 결론

- v0의 주 구현 언어는 Python으로 둡니다.
- v0의 기본 실행 형태는 CLI로 시작합니다.
- 로컬 웹앱은 v1 또는 v0 후반 확장 후보로 둡니다.
- Rust는 초기에 코어 대체 언어로 도입하지 않고, 나중에 UI, 런처, 패키징 계층에서 검토합니다.

## 왜 CLI부터 시작하나

- 로컬 STT, 요약, 파일 입출력 파이프라인을 가장 짧은 거리로 검증할 수 있습니다.
- `faster-whisper`, `pyannote.audio`, 요약 백엔드 실험이 Python에서 가장 빠르게 진행됩니다.
- GUI나 웹 UI를 먼저 만들면 입력 검증, 상태 관리, 파일 업로드 흐름이 먼저 복잡해집니다.
- MVP의 첫 성공 조건은 사용자가 회의 파일 하나를 넣고 Markdown 결과를 얻는 것입니다.

즉, v0에서는 인터페이스보다 처리 파이프라인의 신뢰성을 먼저 확인합니다.

## 목표 사용자 흐름

```text
사용자가 회의 오디오 파일 경로를 넘긴다
→ Python CLI가 입력 메타데이터와 옵션을 읽는다
→ 전사 파이프라인을 실행한다
→ 필요하면 화자 분리를 시도한다
→ 요약/결정사항/액션 아이템을 생성한다
→ Markdown 파일로 저장한다
→ 실행 결과와 출력 경로를 콘솔에 보여준다
```

## v0 엔트리포인트

초기 엔트리포인트는 아래처럼 단일 CLI 스크립트로 시작합니다.

- `python -m meeting_summary_tool.cli`

최초 목표는 다음 두 가지 실행 패턴을 지원하는 것입니다.

1. 파일 경로 직접 입력
2. 최소 메타데이터 옵션 전달

예시:

```powershell
python -m meeting_summary_tool.cli `
  --input .\inputs\sample-meeting.m4a `
  --title "주간 팀 회의" `
  --date 2026-04-11 `
  --attendees "pjh,team-a,team-b"
```

## 초기 디렉토리 구조 초안

```text
meeting-summary-tool/
  README.md
  TODO.md
  docs/
    python-v0-architecture.md
  src/
    meeting_summary_tool/
      __init__.py
      cli.py
      config.py
      models.py
      pipeline.py
      io/
        audio_loader.py
        output_writer.py
      stt/
        transcribe.py
      summarize/
        backend.py
      diarization/
        diarize.py
  tests/
    test_pipeline.py
```

## 디렉토리별 역할

- `docs/`: 기획, 스파이크, 출력 포맷, 평가 기준 문서
- `src/meeting_summary_tool/cli.py`: CLI 인자 파싱과 실행 진입점
- `src/meeting_summary_tool/config.py`: 로컬 설정 파일과 기본값 로딩
- `src/meeting_summary_tool/models.py`: transcript, speaker segment, summary result 같은 내부 데이터 구조
- `src/meeting_summary_tool/pipeline.py`: 입력부터 출력 저장까지의 상위 흐름 조합
- `src/meeting_summary_tool/io/`: 파일 읽기와 Markdown 쓰기
- `src/meeting_summary_tool/stt/`: STT 호출 어댑터
- `src/meeting_summary_tool/summarize/`: 요약 백엔드 어댑터
- `src/meeting_summary_tool/diarization/`: 선택적 화자 분리
- `tests/`: 핵심 파이프라인과 출력 포맷 검증

## 설정과 로컬 경로 원칙

초기에는 아래 원칙을 둡니다.

- 입력 파일은 사용자가 경로로 직접 전달합니다.
- 결과 파일은 기본적으로 저장소 바깥이 아니라 사용자 지정 출력 디렉토리 또는 기본 출력 디렉토리에 저장합니다.
- 설정 파일은 필요할 때만 도입하고, v0 초반에는 CLI 인자를 우선합니다.
- 로그는 콘솔 출력 중심으로 두고, 상세 로그 파일은 필요 시 옵션으로 추가합니다.

기본 경로 초안:

```text
input: 사용자가 직접 지정
output: ./outputs/meeting-summary-tool/
config: ./meeting-summary-tool/config.local.json (필요 시)
```

## 초기 내부 데이터 흐름

```text
AudioInput
→ TranscriptResult
→ Optional SpeakerSegments
→ SummaryResult
→ MarkdownDocument
→ SavedOutput
```

이 흐름에 맞춰 내부 모델을 먼저 단순하게 두고, 구현이 커지면 세부 필드를 늘리는 방향으로 갑니다.

## 제외하는 것

v0 구조 설계 단계에서 아래는 먼저 넣지 않습니다.

- 웹 서버 프레임워크 강제 도입
- 실시간 스트리밍 입력
- 백그라운드 큐 처리
- 다중 사용자 세션 관리
- 원격 저장소 연동

## 다음 단계

- `faster-whisper` 기반 STT 스파이크 문서 정리
- 요약 백엔드 인터페이스 초안 정리
- Markdown 출력 포맷 스펙 정리
- 샘플 오디오와 MVP 평가 기준 정리
