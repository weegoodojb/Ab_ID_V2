# Ab ID Review

혈액은행 항체 동정 검토를 위한 로컬 웹앱입니다. 운영 MySQL의 `agpf`와 `rst`를 읽기 전용으로 SQLite에 복제한 뒤, panel 반응을 기반으로 설명 가능한 단일항체 후보를 우선순위로 보여 줍니다. 결과는 최종 판정이 아닌 검사자 검토 지원 정보입니다.

## Run

1. `Copy-Item .env.example .env` 후 읽기 전용 MySQL 계정 정보를 입력합니다. `.env`는 저장소에 포함하지 않습니다.
2. `python -m pip install -e .`
3. `python -m uvicorn app.main:app --reload`
4. 브라우저에서 `http://127.0.0.1:8000`을 엽니다.
5. 기본으로 설정된 최근 7일 검사기간을 확인하거나 변경한 뒤 `ID 불러오기`를 누릅니다. MySQL `rst`에서 `tn="Ident"` 결과가 있는 검체번호만 조회합니다.
6. 검체번호 선택 후 `결과 불러오기`를 누릅니다. 해당 검체의 `rst` 결과와 `agpf` panel 표가 SQLite에 저장됩니다. Surgiscreen lot 목록에는 ID 검사일 기준으로 `agpf.expdt`가 유효한 lot만 표시됩니다.

`AGPF`의 `lno`와 `rst`의 `lid`가 예시상 동일하지 않으므로, 결과를 불러온 뒤 panel lot은 별도로 선택합니다. 자동 lot 연결은 기관의 실제 매핑 규칙을 확인한 후 추가해야 합니다.

## Current Rules

- A/C 행: `tn="Auto"`
- AHG: `odr="0.8% PanelC Unt w/Auto"`
- Enzyme: `odr="0.8% PanelC Enz"`
- 반응: `0=N`, `5=trace`, `10=1+`, `20=2+`, `30=3+`, `40=4+`
- 후보 상태: 양성·음성 일치가 각각 2개 이상이고 panel 불일치가 없을 때 `POSSIBLE`
- Screening은 보정 근거이며 단독 배제 규칙으로 사용하지 않습니다.
- 단일항체로 설명되지 않으면 복합항체 가능성을 경고합니다. 자동 조합 추천은 아직 포함하지 않습니다.