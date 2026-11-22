# archive — 보관한 옛 코드

지금은 쓰지 않는 예전 방식 코드를 참고용으로 모아 둔 곳이에요. 프로그램과 테스트는 이 폴더를 쓰지 않아요.

| 파일 | 예전에 하던 일 | 지금 대신하는 것 |
|---|---|---|
| `vocal_melody.py` | `transcribe --vocals`: 목소리를 분리해 멜로디 뽑기 | `analysis/separation.py`(A단계), `analysis/melody.py`(I단계) |
| `old_rhythm.py` | 곡 전체 빠르기 하나 찾기, 초 단위 음을 박자 칸에 맞추기 | `analysis/beats.py`(B단계), `analysis/rhythm.py`(D단계) |
| `save_midi.py` | 음원마다 `.mid` 파일 남기기 | 분석표(`_분석표.json`) |
| `old_test_*.py` | 위 코드의 테스트(이름이 `test_`로 시작하지 않아 pytest가 돌리지 않음) | — |
