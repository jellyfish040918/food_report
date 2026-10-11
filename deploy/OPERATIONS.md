# FLAVO 운영·출시 안내

## 현재 구현 범위

여러 기업이 가입하고 각자 보고서와 Q&A를 저장하는 **단일 서버 SaaS**입니다. 서버가 기업 권한과 사용량을 확인한 뒤 영속 큐에 작업을 기록하며 하나의 모델 작업을 순차 실행합니다. Stripe 키가 없는 로컬 데모에서는 결제 버튼이 비활성화됩니다. 현재 구현·검증은 로컬이며 실제 결제, 메일 전송, DNS/TLS, 컨테이너 호스팅은 아직 연결하지 않았습니다.

포함된 Docker 구성은 배포 템플릿입니다. 이 PC에 Docker가 설치되어 있지 않아 컨테이너 실행을 검증하지 않았습니다. 외부 배포 전에 스테이징에서 아래 절차를 수행하세요. 독립 보안 감사·다중 서버 확장·SLA를 완료한 제품으로 표시하지 마세요.

2026-10-11 게시 전 검사에서는 Node 테스트 13개와 Python 테스트 63개, 의존성 검사, 정적 빌드, 임시 DB를 사용하는 별도 운영 모드 서버의 기동·인증 경계·서버 데이터 도구를 확인했습니다. SMTP는 인증서와 호스트 이름을 검증하는 TLS 컨텍스트를 사용하며, 인증서 검증 실패 시 로그인과 전송을 중단하는 테스트를 포함합니다. 백업은 새 DB 경로에서 무결성·작업·보고서 복원을 검증했습니다. 메일과 Stripe 테스트는 모의 서버/응답을 사용하므로 실제 외부 서비스 연동 성공을 의미하지 않습니다.

GitHub Actions에는 단위 테스트 후 Docker 이미지를 빌드하고 외부 네트워크가 없는 컨테이너에서 `scripts/container_smoke.py`를 실행하는 검사를 추가했습니다. 저장소 업로드 이후 해당 작업이 성공해야 Linux 컨테이너 검증 완료로 판단합니다. 이 워크플로는 검사·빌드용이며 고객용 서버 배포를 자동으로 수행하지 않습니다.

## 설정 파일

`.env.example`을 `.env`로 복사하고 **서버에서만** 편집합니다. `.env`, SQLite, 원본 자료, 모델 파일은 Git 대상이 아닙니다. 키를 채팅이나 브라우저 입력창에 넣을 필요가 없습니다.

| 설정 | 용도 |
| --- | --- |
| `FLAVO_ENV=production` | 개발 데모 차단, 이메일 인증과 Secure 쿠키 강제 |
| `FLAVO_PUBLIC_URL=https://app.example.com` | 요청 Origin, 메일 링크, 결제 복귀 주소 |
| `FLAVO_DOMAIN=app.example.com` | Compose의 Caddy 도메인 |
| `STRIPE_SECRET_KEY` | 서버 전용 테스트/라이브 비밀 키 |
| `STRIPE_WEBHOOK_SECRET` | 해당 엔드포인트의 서명 비밀값 |
| `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_TEAM` | 운영자가 정한 월 반복 가격 ID |
| `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | STARTTLS 발송 계정과 검증된 발신 주소 |
| `FLAVO_MODEL=qwen3.5:9b` | 보고서·Q&A 모델. 브라우저에서 바꿀 수 없음 |
| `OLLAMA_HOST` | 서버에서 접근하는 내부 추론 주소 |
| `FLAVO_DATABASE` | 영속 디스크의 DB 경로 |
| `FORWARDED_ALLOW_IPS` | 요청 IP를 신뢰할 역방향 프록시 IP/CIDR만 지정 |

운영 모드에서 HTTPS·메일·Stripe 설정이 빠지면 시작을 거부합니다. 개발 모드를 인터넷에 노출하는 방식으로 우회하지 마세요. 새 운영 DB로 시작하고 로컬 데모 DB를 복사하지 마세요. 모든 키가 테스트 모드인지 라이브 모드인지 통일해야 합니다.

## Stripe 연결

1. 운영 법인에 맞는 Stripe 계정을 준비하고 테스트 환경에서 Starter와 Team 제품의 **월 반복 가격**을 만듭니다. 금액·통화는 운영자가 정하며 해당 `price_...`를 환경변수에 설정합니다. 앱에 임의 가격을 표시하지 않습니다.
2. Stripe Customer Portal에서 등록한 두 상품/가격 사이의 변경, 해지, 결제수단 갱신과 청구서 보기를 설정합니다. 다른 가격이나 수량은 이 서비스의 이용 권한으로 인정하지 않습니다.
3. 이벤트 목적지는 `https://app.example.com/api/billing/webhook`입니다. `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`를 구독합니다. 엔드포인트 API 버전은 **2025-06-30.basil**로 맞춥니다.
4. 서명 비밀값을 `STRIPE_WEBHOOK_SECRET`에 저장하고 API를 재시작합니다. 성공 복귀 페이지 자체는 구독 권한을 부여하지 않습니다. 서명 검증 후 Stripe에서 현재 구독을 다시 조회하고 고객·기업·가격을 대조합니다.
5. 테스트 Checkout 완료 → Starter/Team 반영 → 새로고침 후 사용량 유지 → Portal 변경/해지 → 웹훅 중복/지연 재전송 → 결제 실패 상태 → 기간 종료 차단까지 확인합니다. 체험 DB의 요금제를 수동 변경해 테스트를 대신하지 마세요.
6. 실제 판매 전에 라이브 키·라이브 가격·라이브 웹훅 서명을 함께 바꾸고 소액 결제/환불 동작을 운영자가 확인합니다. 현재 작업에서는 외부 결제나 Stripe 리소스 생성을 실행하지 않았습니다.

Checkout 생성 실패의 결과가 불명확해도 저장된 idempotency key와 요청을 재사용합니다. 진행 중 결제가 있으면 다른 플랜의 중복 Checkout을 만들지 않습니다. 해당 링크는 30–60분 뒤 만료됩니다. 새 구독을 만들기 전에 기존 구독은 Portal에서 관리합니다. 웹훅 장애는 Stripe에서 재전송하고, API 로그의 요청 ID와 작업 ID로 조사합니다. 원문 비밀번호·토큰·보고서 내용은 로그에 넣지 않습니다.

구현 근거: [Stripe Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create), [구독 연동](https://docs.stripe.com/billing/subscriptions/build-subscriptions), [웹훅 서명과 이벤트 처리](https://docs.stripe.com/webhooks).

## 서버 배포

Python 3.13 + Node.js 22 + 영속 로컬 디스크가 있는 서버 또는 포함된 Compose 템플릿을 사용합니다. GitHub는 소스와 CI 결과를 보관하며 GitHub Pages만으로 이 서버를 실행할 수 없습니다.

```sh
# 운영 서버에서 .env를 먼저 구성합니다.
docker compose config --quiet
docker compose up -d model
docker compose exec model ollama pull qwen3.5:9b
docker compose up -d --build web proxy
docker compose ps
```

`docker compose config` 전체 출력은 비밀값을 포함할 수 있으므로 로그·채팅에 공유하지 마세요. 이 템플릿은 80/443만 공개하고 4175/11434는 외부에 게시하지 않습니다. `proxy_api`의 `172.30.42.0/24`가 기존 네트워크와 충돌하면 네트워크와 `FORWARDED_ALLOW_IPS`를 함께 바꾸세요. 앱은 이 전용 프록시 네트워크에서 전달한 클라이언트 IP만 신뢰합니다.

Compose의 모델 저장소는 현재 Windows 설치와 별개입니다. 첫 서버 배포에서 모델을 받아야 하며 위 구성은 기본 CPU 실행입니다. 고객 규모·대기 시간에 맞춰 GPU 서버를 마련하고 실제 모델 버전·드라이버·VRAM으로 부하 테스트하세요. Docker 이미지는 출시 시 검증한 태그/다이제스트로 고정하세요. 모델 라이선스와 서비스 이용 조건도 배포 전에 확인합니다.

`GET /api/health`는 DB 접근과 워커 생존을 확인하며 모델 준비 완료까지 보증하지는 않습니다. 로그인한 `/api/status`가 AI 준비 상태를 제공합니다. HTTPS 경유 회원가입과 인증 메일, 비밀번호 재설정, 다른 이메일 계정으로 팀 초대를 실제 테스트해야 합니다. SMTP는 자동 테스트에서 모의 처리하며 실제 발송은 검증하지 않았습니다.

## 운영 한도와 복구

- **단일 API 프로세스·단일 워커만 지원**합니다. DB 파일 잠금으로 같은 DB를 사용하는 두 번째 워커 시작을 막습니다. `uvicorn --workers 2`나 컨테이너 복제를 하지 마세요.
- 분석 실행은 전체에서 1개씩 순차 처리합니다. 기업당 대기·진행 작업은 3개, 전체 50개로 제한합니다. 모델 호출 최대 300초, 작업 전체 최대 330초입니다. 대기 시간은 별도이며 허위 남은 시간을 표시하지 않습니다.
- 브라우저 종료·새로고침은 작업을 취소하지 않습니다. 취소 버튼은 서버 작업을 취소하고 추론 HTTP 연결을 닫습니다. 엔진 자체 연산이 잠깐 더 이어질 수 있으나 취소한 결과는 저장·차감하지 않습니다.
- 서버 재시작 때 대기 작업은 유지합니다. 실행 중 작업은 실패, 취소 중 작업은 취소로 기록하며 실패 작업은 사용자가 새 작업으로 재시도합니다. 중간 모델 응답을 이어 생성하는 체크포인트는 없습니다.
- 사용량 예약은 SQLite 트랜잭션으로 처리합니다. Trial은 14일에 5회, Starter 30회/월·3석, Team 100회/월·10석입니다. 월 한도는 UTC 1일에 갱신됩니다. 결제 주기와 한도 갱신일의 차이를 가격 안내에 명시하세요.
- 다운그레이드 후 멤버가 좌석 한도를 넘으면 새 분석을 막습니다. 기존 결과는 읽을 수 있고 관리자가 멤버 접근을 해제하거나 요금제를 바꿀 수 있습니다. 해제한 멤버의 해당 기업 세션은 즉시 폐기합니다.
- 자동 환불·크레딧 이월·쿠폰 정책, 대규모 테넌트 큐 스케줄링, SSO/MFA, 이메일 변경/소유권 이전, 셀프서비스 계정 삭제는 미구현입니다. 초기 판매 약속에 포함하지 마세요. 계정 정정·삭제·환불은 운영자가 본인 확인 후 처리할 지원 채널을 준비해야 합니다.
- 서버 CPU/메모리/디스크, 인증 오류, 작업 실패율, 대기 시간, 웹훅 실패와 외부 `/api/health`를 모니터링하세요. 다중 서버 확장 전에는 Postgres·별도 작업 브로커로 이전하고 테넌트 분리·중복 실행 검증을 유지해야 합니다.

## 백업과 복구

SQLite 파일을 실행 중 단순 복사하지 않고 SQLite 백업 API를 사용합니다. 백업에는 계정과 기업 자료가 있으므로 접근을 제한하고 암호화된 별도 저장소에 복제하세요. 아래 작업은 새 파일만 생성하고 기존 백업을 덮어쓰지 않습니다.

```powershell
# 로컬 서버
.venv\Scripts\python.exe scripts/backup.py var/backups/flavo-2026-10-11.sqlite3
```

```sh
# 컨테이너 내부 백업 후 별도 보관
docker compose exec web python scripts/backup.py /app/var/backups/flavo-backup.sqlite3
docker compose cp web:/app/var/backups/flavo-backup.sqlite3 ./flavo-backup.sqlite3
```

운영 복구는 API를 중지한 뒤 진행합니다. 기존 DB·WAL·SHM을 같은 시점의 보관 폴더에 함께 보존하고, 검증된 백업을 **새 디렉터리의 새 DB 경로**로 복사한 다음 `FLAVO_DATABASE` 또는 볼륨 경로를 그 파일로 지정하세요. 원본 DB를 덮어쓰거나 오래된 WAL과 백업을 섞지 마세요. 소유권 10001과 쓰기 권한을 확인하고 한 프로세스를 재시작합니다. 스테이징에서 로그인, 기업별 보고서 수, 최근 작업, 결제 고객 연결을 확인한 후 운영 전환합니다. DB 백업 복구만으로 Stripe 상태를 과거로 돌릴 수 없으므로 이후 이벤트를 재전송하여 동기화해야 합니다.

## 출시 전에 운영자가 완료할 사항

1. 실제 판매 가격·통화·운영 법인에 맞는 Stripe 계정, SMTP 발신 도메인, HTTPS 서비스 도메인 설정.
2. Stripe 테스트 결제·구독 변경·해지와 실메일 인증/재설정/초대 검증, 컨테이너 빌드·시작·백업 복구 시험.
3. 실제 하드웨어에서 한국어/영어 보고서 품질과 처리 시간, 동시 접속·대기열 부하 시험.
4. 제공된 Shutterstock 이미지와 각 원본 데이터의 **상업 서비스 사용·재배포 권한** 확인. 사용자 제공 파일이라는 사실만으로 판매용 라이선스를 확인한 것으로 간주하지 않습니다. 앱에는 원문 리뷰와 작성자 정보를 배포하지 않지만 집계 자료의 사용 조건도 확인해야 합니다.
5. 실제 사업자·보관 기간·지원 연락처·해지/환불 방침에 맞는 약관과 개인정보 안내를 작성해 게시하고 필요한 동의·기록 절차를 연결. 현재 코드에 사업자 정보나 법적 준수 보장을 임의로 만들어 넣지 않았습니다.
6. 현재 데이터는 2026-10-09 집계 스냅샷이며 Food.com 리뷰는 2000–2020년 자료입니다. 자동 최신 시장조사라고 판매하지 말고 자료 갱신 주기·해석 범위를 명시.

비밀번호와 세션 처리 참고: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). 서버 운영 범위 참고: [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/).
