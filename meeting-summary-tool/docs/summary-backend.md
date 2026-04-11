# 회의 요약 백엔드 초안

이 문서는 `meeting-summary-tool`의 요약 백엔드 전략을 정리한 초안입니다.  
기준은 Python 구현이며, 로컬 우선 처리와 확장 가능한 인터페이스를 함께 잡는 방향입니다.

작성일: 2026-04-11

## 목표

요약 백엔드는 전사 결과를 받아서, 회의에서 바로 쓸 수 있는 Markdown 결과물을 만드는 역할을 맡습니다.

핵심 목표는 다음과 같습니다.

- 입력 형식이 단순해야 합니다.
- 로컬 실행이 기본이어야 합니다.
- 모델 선택을 나중에 바꿀 수 있어야 합니다.
- 실패해도 전체 파이프라인이 끊기지 않아야 합니다.
- 결과는 사람이 바로 읽고 수정할 수 있어야 합니다.

## Python 기준 전략

초기 백엔드는 Python으로 고정합니다.

이유는 단순합니다.

- 오디오 전사, 요약, 후처리 생태계가 Python에 가장 잘 모여 있습니다.
- `faster-whisper`, `pyannote.audio`, `ollama` 연동, OpenAI SDK 같은 후보를 한 언어 안에서 묶기 쉽습니다.
- 실험 속도가 빠릅니다.
- 나중에 CLI, 로컬 웹앱, Tauri 외부 래퍼로 확장하기도 쉽습니다.

권장 구조는 아래와 같습니다.

```text
입력 파일 수집
→ 전사 결과 정규화
→ 화자 정보 병합
→ 요약 요청 생성
→ 모델 선택
→ 결과 검증 및 보정
→ Markdown 렌더링
→ 로컬 저장
```

백엔드 내부는 다음 계층으로 나누는 편이 좋습니다.

- `transcript adapter`: STT 결과를 공통 구조로 바꾼다.
- `summary planner`: 요약 프롬프트와 출력 규칙을 만든다.
- `model adapter`: Ollama, OpenAI 같은 실행 대상을 감춘다.
- `renderer`: Markdown 파일을 생성한다.
- `fallback handler`: 실패 시 대체 경로를 처리한다.

## Ollama 우선 vs BYOK 비교

요약 모델은 크게 두 축으로 봅니다.

### 1. Ollama 우선

장점:

- 로컬에서 바로 돌릴 수 있습니다.
- API 키 관리가 필요 없습니다.
- 팀 내부 실험과 공유가 쉽습니다.
- 비용 통제가 쉽습니다.

단점:

- 머신 성능에 영향을 받습니다.
- 모델 품질 편차가 있습니다.
- 환경마다 결과 차이가 날 수 있습니다.
- 긴 입력에서 속도와 메모리 이슈가 생길 수 있습니다.

추천 사용처:

- 개발 중 기본값
- 오프라인 환경
- 비용 최소화가 중요한 내부 사용

### 2. BYOK(OpenAI API 키)

장점:

- 품질과 안정성이 비교적 높습니다.
- 긴 회의 요약에서 성능 예측이 쉽습니다.
- 초기 사용자가 본인 키로 바로 검증할 수 있습니다.

단점:

- 키 입력과 보관 정책이 필요합니다.
- 비용이 발생합니다.
- 네트워크 의존성이 생깁니다.
- 사용자가 키를 준비해야 합니다.

추천 사용처:

- 로컬 모델 품질이 부족한 경우
- 빠르게 안정적인 결과가 필요한 경우
- 사용자가 직접 고품질 출력을 원할 때

### 결론

기본값은 `Ollama 우선`이 적절합니다.

이유는 이 프로젝트의 우선순위가 "쉽게 설치해서 바로 써보기"이기 때문입니다.  
다만 실제 사용성 측면에서는 `BYOK`도 같이 열어두는 편이 좋습니다.

권장 정책은 다음과 같습니다.

```text
기본값: Ollama
대체값: OpenAI BYOK
```

이렇게 두면 로컬 우선 철학을 지키면서도, 품질 보정 수단을 남길 수 있습니다.

## 입력 인터페이스 초안

백엔드가 받는 입력은 가능한 한 작고 명시적이어야 합니다.

권장 입력은 아래와 같습니다.

```json
{
  "job_id": "2026-04-11-team-sync",
  "audio_path": "C:/meeting/input/team-sync.m4a",
  "transcript_path": "C:/meeting/output/team-sync.transcript.json",
  "speaker_map": {
    "Speaker 1": "민수",
    "Speaker 2": "지현"
  },
  "meeting_title": "팀 주간 회의",
  "meeting_date": "2026-04-11",
  "summary_mode": "standard",
  "model_provider": "ollama",
  "model_name": "llama3.1:8b",
  "api_key": null,
  "language": "ko"
}
```

필드 설명:

- `job_id`: 결과 파일과 로그를 묶는 식별자입니다.
- `audio_path`: 원본 오디오 경로입니다.
- `transcript_path`: 전사 결과가 이미 있으면 재사용합니다.
- `speaker_map`: 사용자가 보정한 화자 이름입니다.
- `meeting_title`: 출력 문서 제목에 씁니다.
- `meeting_date`: 파일명과 상단 메타데이터에 씁니다.
- `summary_mode`: `standard`, `short`, `action-focused` 같은 정책값입니다.
- `model_provider`: `ollama` 또는 `openai`를 받습니다.
- `model_name`: 실제 사용할 모델 이름입니다.
- `api_key`: BYOK일 때만 사용합니다.
- `language`: 기본 출력 언어입니다.

명령줄이나 UI에서는 이 값을 전부 드러내지 않아도 됩니다.  
내부 API는 이 정도로만 정리해두면 충분합니다.

## 출력 인터페이스 초안

백엔드의 최종 출력은 Markdown 파일과 구조화된 메타데이터입니다.

권장 출력은 아래 두 개입니다.

```text
output/
├─ meeting-title.md
└─ meeting-title.summary.json
```

### Markdown

Markdown에는 사람이 바로 쓰는 내용만 둡니다.

- 제목
- 요약
- 결정사항
- 액션 아이템
- 참석자 메모
- Transcript

### JSON

JSON에는 자동 후처리에 필요한 내용을 둡니다.

- `job_id`
- `provider`
- `model_name`
- `duration_sec`
- `transcript_segments`
- `speaker_map`
- `summary_status`
- `fallback_used`
- `warnings`

이렇게 나누면 Markdown은 읽기 좋게 유지되고, JSON은 다시 처리하기 쉬워집니다.

## 실패 시 fallback 규칙

백엔드는 실패해도 가능한 한 결과를 남겨야 합니다.

우선순위는 아래처럼 둡니다.

### 1. 요약 실패 시

- 전사 결과가 있으면 transcript만 먼저 저장합니다.
- 요약 본문 대신 실패 사유를 `warnings`에 남깁니다.
- 다음 실행에서 요약만 재시도할 수 있게 합니다.

### 2. Ollama 실패 시

- 모델이 없거나 응답이 늦으면 OpenAI BYOK로 전환합니다.
- BYOK도 없으면 전사 + 템플릿 문서만 생성합니다.

### 3. BYOK 실패 시

- API 키 오류면 즉시 로컬 Ollama로 되돌아갑니다.
- 둘 다 실패하면 텍스트 골격만 남깁니다.

### 4. 입력이 불완전할 때

- `meeting_title`이 없으면 파일명에서 추론합니다.
- `meeting_date`가 없으면 실행 시각을 기본값으로 둡니다.
- `speaker_map`이 없으면 `Speaker 1/2/3`로 둡니다.

### 5. 전사 결과가 없을 때

- 요약을 시도하지 않습니다.
- 파일 처리 실패로 종료하지 말고, 실패 로그와 재시도 힌트를 남깁니다.

### 6. 출력 중간 실패

- Markdown 생성 전까지의 산출물은 가능한 한 보존합니다.
- 임시 파일은 최종 파일과 분리해서 다룹니다.
- 같은 `job_id`로 재실행하면 덮어쓸 수 있어야 합니다.

## 권장 운영 규칙

- 기본 모드는 `Ollama`입니다.
- `OpenAI BYOK`는 대체 경로로 유지합니다.
- 요약 백엔드는 전사 백엔드와 느슨하게 결합합니다.
- 출력 포맷은 Markdown 우선, JSON 보조로 둡니다.
- 실패한 작업도 최대한 읽을 수 있는 상태로 끝냅니다.

## 다음 결정 포인트

- 기본 `model_provider`를 UI에서 어디까지 노출할지
- `summary_mode`를 몇 단계로 둘지
- 실패 로그를 파일로 남길지, DB로 남길지
- BYOK 키를 환경변수로만 받을지, 앱 설정으로 받을지

