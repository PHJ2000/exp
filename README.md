# Exp

개인 실험 저장소입니다. 현재는 음성 입력, 받아쓰기, 보이스 변환 실험을 한 저장소 안에서 관리하고 있고, 각 작업물은 디렉토리 단위로 옮기기 쉽게 정리해두었습니다.

## 프로젝트

### `codex-dictation/`

Codex CLI에 붙여 쓰는 Windows용 로컬 받아쓰기 프로젝트입니다.

- 목적: 마이크 입력을 실시간에 가깝게 받아서 Codex CLI 터미널에 직접 타이핑
- 핵심 기능: 항상 듣기, 터미널 포커스 연동, 음성 명령(`보내`, `지워`, `다 지워`, `다시 ...`)
- 실행 파일과 문서는 모두 `codex-dictation/` 아래에 정리되어 있습니다.
- 상세 문서: [`codex-dictation/README.md`](./codex-dictation/README.md)

### `experiments/`

개별 성능 검증, 벤치마크, 재현 스크립트를 모아둔 실험 디렉토리입니다.

현재 포함:
- `benchmark_sovits_realtime.py`
  - so-vits-svc 계열이 CUDA GPU 환경에서 어느 정도 실시간에 가까운지 측정하는 스크립트
- `sovits_realtime_report.md`
  - RTX 4060 기준 실험 결과 정리 문서
- `results_sovits_realtime.json`
  - 벤치마크 결과 원본 데이터

요약:
- 워밍업 이후 기준으로는 `거의 실시간`에 가까운 결과가 나왔고
- 짧은 블록에서는 간헐적인 지연 스파이크가 생길 수 있음을 확인했습니다.
- 상세 문서: [`experiments/README.md`](./experiments/README.md)

### `external/`

외부 프로젝트나 서드파티 소스를 보관하는 디렉토리입니다.

현재 포함:
- `so-vits-svc-fork/`
  - 보이스 변환 실험에 사용한 외부 저장소 사본
- 상세 문서: [`external/README.md`](./external/README.md)

## 지원 디렉토리

아래 디렉토리는 프로젝트 실행이나 실험 재현을 위한 지원용입니다.

- `inputs/`: 입력 오디오, 샘플, 실험용 원본 데이터
- `models/`: 로컬 모델 파일이나 체크포인트 보관
- `outputs/`: 생성물, 변환 결과, 산출물 보관
- `temp/`: 임시 작업 파일
- `tools/`: 로컬 도구 모음
  - 현재 `AutoHotkey` 실행 파일 포함

## 실행 메모

- 실제 받아쓰기 본체 파일은 `codex-dictation/` 아래에 있습니다.
- 받아쓰기 기능 자체는 로컬 `faster-whisper` 기반이라 추가 API 비용 없이 동작합니다.
- 다만 `Codex CLI` 자체 사용 비용은 별도입니다.

## 다음 머지 기준

나중에 `main` 쪽으로 가져갈 때는 기본적으로 아래 두 단위를 기준으로 보면 됩니다.

- `codex-dictation/`: 실제 제품화에 가까운 받아쓰기 프로젝트
- `experiments/`: 검증용 스크립트와 결과물
