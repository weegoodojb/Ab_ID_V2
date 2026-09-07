# Ab ID 다음 작업

## 현재 확인된 사항

- MySQL 원본 DB: `schbc_vision`
- `rst` 주요 컬럼: `sid`, `adt`, `tn`, `rst`, `odr`, `pid`, `Iid`
- ID 검사 완료 행: `rst.tn = "Ident"`
- A/C 행: `rst.tn = "Auto"`
- AHG: `rst.odr = "0.8% PanelC Unt w/Auto"`
- Enzyme: `rst.odr = "0.8% PanelC Enz"`
- 반응 코드: `0=N`, `5=trace`, `10=1+`, `20=2+`, `30=3+`, `40=4+`
- `pinfo` 연결: `rst.pid = pinfo.pid`, 환자명은 `pinfo.pnm`.
- `pinfo.pnm`은 `latin1` 컬럼이며 CP949 한글을 복원해 화면에 표시한다.
- `agpf` 주요 컬럼: `kd`, `lno`, `expdt`, `ag`, `rh`, `sagt`, `vl`, `agsq`, `gr`, `sq`.
- `agpf.kd = "ID"`는 ID panel이고, `agpf.kd = "ABScrS"`는 Surgiscreen 관련 reagent 데이터다.
- Screening cell 번호는 `agpf.gr`로 식별한다. `gr=27,28,29`가 각각 Cell 1,2,3이다.
- `agpf.ag="DonorN"` 행의 `vl`은 해당 Screening donor 번호다.
- `agpf.vl="Di (a+)"`인 `Sp Ag` 행의 cell이 lot별 Diego(a) 항원 양성 cell이다.
- Screening 결과는 별도 결과 테이블이 아니라 `rst`에 저장된다.
  - 검사명: `Surg 1`, `Surg 2`, `Surg 3`
  - 검사그룹: `Ab Screening`
  - 공통 Screening 결과: `ABScr`
- `idrst` 테이블은 존재하지만 현재 운영 행이 없어 Screening 결과 원본으로 사용하지 않는다.
- Antigram 표시명: `BC -> C`, `BE -> E`, `SC -> c`, `SE -> e`, `NK -> K`, `SK -> k`, `BS -> S`, `SS -> s`.

## 다음 우선 작업

- [x] **Screening 결과 원본 테이블 탐색**
  - `rst`가 Screening 결과 원본임을 확인했다. `Surg 1`~`Surg 3`은 `odr="Ab Screening"`으로 저장된다.
  - `idrst`는 현재 행이 없어 사용하지 않는다.
  - Screening 검체번호/검사일/반응값은 `rst.sid`/`rst.adt`/`rst.rst`로 연결한다.

- [ ] **ID와 Surgiscreen을 별도 동기화**
  - `kd="ID"` reagent 데이터와 Screening 원본 테이블 데이터를 별도 조회/API/SQLite snapshot으로 분리한다.
  - 전체 `agpf`를 매번 복제하지 않고, 선택한 ID lot과 Surgiscreen lot만 읽기 전용으로 조회한다.
  - SQLite 원본 보존 테이블은 source row 중복을 허용해야 한다. `lot + cell + antigen`을 고유키로 가정하지 않는다.

- [x] **Antigram cell 축 확정**
  - ID는 11 cell, Surgiscreen은 3 cell로 표시한다.
  - `agpf.sq`는 항원 순번이고, cell 식별자는 `agpf.gr`이다.
  - ID는 `gr=9..19`를 Cell 1..11로, Screening은 `gr=27..29`를 Cell 1..3으로 매핑한다.
  - ID와 Surgiscreen은 절대 하나의 표/행 집합으로 섞지 않는다.

- [x] **Lot별 Di(a) 양성 Screening cell 처리**
  - Screening donor 3개 중 Di(a) 양성 cell은 고정 cell 번호가 아니라 lot마다 달라진다.
  - Screening lot Antigram의 `ag="Sp Ag"`, `vl`에 `Di(a+`가 있는 cell을 동적으로 찾아 표시한다.
  - 화면에 `Di(a+)`를 표시하며 Cell 번호를 하드코딩하지 않는다.
  - `Surg 1`~`Surg 3`의 환자 Screening 결과도 같은 행에 표시한다.

  - [x] **확정 결과 저장 및 재조회**
    - 검체번호, ID lot, Screening lot, 4도 입력, 확정 항체, 확정 해석, 검토 메모를 SQLite `review_results`에 저장한다.
    - 같은 검체를 다시 선택하면 저장된 확정 결과 이력을 확인한다.

  - [x] **4도 입력 키보드 이동**
    - Cell 1~11 입력칸에서 Enter를 누르면 다음 Cell 입력칸으로 이동한다.

- [ ] **화면 보완**
  - ID Antigram: 11행 + 환자 AHG/Enzyme/선택적 4C를 같은 행에 표시한다.
  - Surgiscreen Antigram: 3행 + screening 검사 결과를 같은 행에 표시한다.
  - FHD 해상도에서 두 표 모두 수평 스크롤 없이 보이도록 compact table-layout을 유지한다.
  - 4C 수기입력은 기본 접힘, Cell 1~11 세로 입력. 허용값: 빈칸, `0`, `0.5`, `1`, `2`, `3`, `4`.

## 검증 기준

- [ ] 최근 7일 기본 기간에서 `tn="Ident"` 검체만 표시한다.
- [ ] 드롭다운 라벨: `검사일 | 환자이름(등록번호) | 검체번호`.
- [ ] 결과 불러오기 후 선택한 환자정보와 ID 목록이 유지된다.
- [ ] ID lot / Surgiscreen lot은 각각 ID 검사일 대비 `expdt >= 검사일`인 lot만 표시한다.
- [ ] ID 표는 정확히 11행, Surgiscreen 표는 정확히 3행이다.
- [ ] 실제 lot별 Di(a) 양성 donor cell이 정확히 표시된다.
- [ ] MySQL 접속 신호등은 `SELECT 1` 성공 시 녹색이며 접속정보/비밀번호를 로그나 화면에 표시하지 않는다.
- [ ] `python -m pytest -q` 전체 통과.

## 주의 사항

- 운영 MySQL에는 읽기만 수행한다.
- `.env`는 Git에 포함하지 않는다.
- 자동 동정 점수는 최종 판정이 아닌 검사자 검토 지원이다.
- Screening 결과 전용 테이블과 cell 축 매핑이 확정되기 전에는 clinical interpretation 규칙을 추가하지 않는다.
