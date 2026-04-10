# Experiments

검증용 스크립트, 벤치마크, 결과물을 모아두는 디렉토리입니다.

현재 포함:
- `benchmark_sovits_realtime.py`
  - so-vits-svc 계열이 CUDA GPU 환경에서 어느 정도 실시간에 가까운지 측정하는 스크립트
- `sovits_realtime_report.md`
  - RTX 4060 기준 실험 결과 요약 문서
- `results_sovits_realtime.json`
  - 체크인된 벤치마크 결과 원본 샘플
- `results_sovits_realtime.share.json`
  - 체크인된 공유용 마스킹 결과 샘플

현재 정리된 결론:
- 워밍업 이후 기준으로는 `거의 실시간`에 가까운 결과
- 짧은 블록에서는 간헐적인 지연 스파이크 가능

재현:

```powershell
.venv\Scripts\python.exe experiments\benchmark_sovits_realtime.py
```

실행 결과는 작업 트리를 더럽히지 않도록 `outputs/sovits-realtime/` 아래에 생성됩니다.

공유용 로그/결과 마스킹:

```powershell
.venv\Scripts\python.exe codex-dictation\codex_share_safe.py --input outputs\sovits-realtime\results_sovits_realtime.json --output outputs\sovits-realtime\results_sovits_realtime.share.json
```
