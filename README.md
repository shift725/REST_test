# REST_test

作者學習 Django 的練習專案：以 Django REST Framework + SimpleJWT 實作帳號／認證 API（登入、註冊、登出、JWT 管理、使用者查詢）。本文件說明如何用 Docker 在本機跑起來、以及如何部署到單一 Linux VM 並啟用 HTTPS。

技術細節（model、URL routes、JWT 設定等）請見 `CLAUDE.md`。

---

## 快速開始（本機，HTTP）

需求：Docker Desktop 或 Docker Engine 20.10+（含 Compose v2）。

```bash
# 1) 取得專案
git clone <repo-url> rest_test
cd rest_test

# 2) 準備環境變數
cp .env.example .env
```

打開 `.env`，至少修改以下三項；其餘可用預設：

- **`SECRET_KEY`** — Django 加密金鑰。產生方式：
  ```bash
  # 本機有 Python：
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  # 或用一次性容器：
  docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```
- **`POSTGRES_PASSWORD`** — Postgres 密碼，請改成非預設值
- **`DJANGO_SUPERUSER_PASSWORD`** — 自動建立的 admin 密碼（若三個 `DJANGO_SUPERUSER_*` 都填了，容器首次啟動會自動建立 superuser）

```bash
# 3) 啟動（首次會 build image，約 2–3 分鐘）
docker compose up -d --build

# 4) 看一下 web 是否就緒（會看到 entrypoint → migrate → collectstatic → gunicorn）
docker compose logs -f web
# 按 Ctrl-C 離開 log

# 5) 打個 API 試試（空 body 應回 400）
curl -i -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" -d '{}'
```

預設 Django admin：`http://localhost:8000/admin/`，帳號為 `.env` 中的 `DJANGO_SUPERUSER_EMAIL`。

停止與資料保留：

```bash
docker compose down       # 停 container，volume 保留（資料還在）
docker compose down -v    # 連 volume 一起刪（DB 清空）
```

---

## 啟用 TLS（部署到 Linux VM）

前置條件：

1. VM 有公開 IP，port 80 與 443 對外開放
2. 你的網域 A record 已指向 VM 的 IP（用 `dig <DOMAIN>` 或 `nslookup` 確認）
3. `.env` 中 `DOMAIN_NAME` 與 `CERTBOT_EMAIL` 已填好
4. `ALLOWED_HOSTS` 加入你的網域

### 首次取得憑證（一次性 bootstrap）

nginx 需要 cert 才能啟動，cert 又需要 nginx 對外服務 ACME challenge 才拿得到。所以首次需要先放一張臨時自簽 cert 給 nginx 用，再讓 certbot 換成真實 Let's Encrypt cert。

```bash
# Step 1: 讀入 .env，準備變數
set -a; source .env; set +a

# Step 2: 用 certbot image 臨時起一個容器產生 placeholder 自簽 cert
docker compose --profile tls run --rm --entrypoint sh certbot -c "\
  apk add --no-cache openssl >/dev/null 2>&1 || true; \
  mkdir -p /etc/letsencrypt/live/$DOMAIN_NAME && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem \
    -out  /etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem \
    -subj /CN=$DOMAIN_NAME"

# Step 3: 啟動全部服務（web、db、nginx、certbot）
docker compose --profile tls up -d --build

# Step 4: 用真實的 Let's Encrypt cert 取代 placeholder
docker compose --profile tls run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  --force-renewal \
  -d "$DOMAIN_NAME"

# Step 5: reload nginx 載入真實 cert
docker compose --profile tls exec nginx nginx -s reload

# Step 6: 驗證
curl -I https://$DOMAIN_NAME/api/auth/login/      # 應看到 405 或 200，cert 有效
```

### 之後的日常啟動

`certbot-etc` volume 已保存 cert，直接啟動即可。`certbot` 服務每 12 小時自動跑 `certbot renew`，憑證到期前 30 天會自動續約。

```bash
docker compose --profile tls up -d
```

---

## 維運指令速查

```bash
# 跑測試（容器內）
docker compose exec web python manage.py test accounts

# 進 web 容器的 shell
docker compose exec web bash

# 進 Django shell
docker compose exec web python manage.py shell

# 手動 migrate（entrypoint 會自動跑，這裡是補強用）
docker compose exec web python manage.py migrate

# 手動建立 superuser（互動式；env 沒設 SUPERUSER 時用）
docker compose exec web python manage.py createsuperuser

# 看 log（即時）
docker compose logs -f web
docker compose logs -f db

# 備份 DB
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql

# 還原 DB
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql

# 完全重置（連 volume 一起砍）
docker compose down -v
docker compose up -d --build

# 看 certbot 最近一次 renew 的結果
docker compose --profile tls logs certbot --tail 50
```

---

## 環境變數對照表

| 變數 | 必填 | 預設 | 用途 |
|---|---|---|---|
| `SECRET_KEY` | ✅ | 無 | Django 加密金鑰，缺值會啟動失敗 |
| `DEBUG` | ✅ | — | `True`/`False`；正式環境必設 `False` |
| `ALLOWED_HOSTS` | ✅ | `localhost,127.0.0.1` | 逗號分隔；正式環境加入你的網域 |
| `POSTGRES_USER` | ✅ | `resttest` | Postgres 帳號 |
| `POSTGRES_PASSWORD` | ✅ | placeholder | Postgres 密碼，**請改強密碼** |
| `POSTGRES_DB` | ✅ | `resttest` | Postgres 資料庫名 |
| `DB_HOST` | ✅ | `db` | 與 compose service 名一致；外部 DB 改這 |
| `DB_PORT` | ✅ | `5432` | DB 埠 |
| `WEB_PORT` | — | `8000` | 主機端對外的 web port，容器內固定 8000 |
| `DJANGO_SUPERUSER_USERNAME` | — | `admin` | 三個都填才會在容器啟動時自動建 superuser |
| `DJANGO_SUPERUSER_EMAIL` | — | — | 同上 |
| `DJANGO_SUPERUSER_PASSWORD` | — | — | 同上 |
| `DOMAIN_NAME` | TLS 必填 | `example.com` | 公開網域，nginx 與 certbot 共用 |
| `CERTBOT_EMAIL` | TLS 必填 | — | Let's Encrypt 通知信箱 |

`DATABASE_URL` 不需要手動設；compose 會從 `POSTGRES_*` 與 `DB_*` 組合後注入 web 容器。

---

## Troubleshooting

### web 容器卡在 "waiting for database"

```text
[entrypoint] waiting for database db:5432 (max 60s)...
[entrypoint] timed out waiting for db:5432
```

可能原因：

1. `db` 容器還沒 healthy 就被 web 試圖連 → 看 `docker compose ps`，db 若不是 `(healthy)`，再等幾秒或看 `docker compose logs db`
2. `DB_HOST` 設錯：本機 compose 內固定為 `db`（service 名），不是 `localhost` 或 `127.0.0.1`
3. `POSTGRES_PASSWORD` 與 web 端用的不一致：兩邊都從 `.env` 讀，但若你曾改過密碼又沒重建 volume，Postgres 初始密碼是第一次啟動時固定下來的。`docker compose down -v` 砍 volume 再 up

### collectstatic 失敗 `PermissionError: /app/staticfiles`

Dockerfile 已用 `chown app:app /app` 處理。若你客製過 Dockerfile 後遇到此錯，確認：

- `COPY --chown=app:app . .` 之後有 `chown app:app /app`（讓 app user 能在 /app 下建立目錄）
- 沒有手動掛 host volume 到 `/app/staticfiles`（會被 host 的權限蓋掉）

### certbot 拿不到憑證

```text
Failed authorization procedure. <domain> (http-01): urn:ietf:params:acme:error:connection
```

可能原因（按發生頻率排序）：

1. **DNS 沒指好**：`dig $DOMAIN_NAME` 必須回 VM 的公開 IP
2. **Port 80 不通**：雲端防火牆／安全群組沒開 80。Let's Encrypt 只能用 80 做 HTTP-01 challenge
3. **nginx 沒在跑 / placeholder cert 沒種**：先 `docker compose --profile tls ps` 確認 nginx 是 `Up`；若 nginx 因 cert 不存在起不來，照「首次取得憑證」步驟先種 placeholder
4. **Let's Encrypt rate limit**：同網域一週 5 次失敗就會被擋一小時。看 `docker compose --profile tls logs certbot` 是否提到 rate limit
5. **`--force-renewal` 在第一次取得時不需要也不會有害**：但首次成功之後別常用，否則容易撞 rate limit

debug 步驟：

```bash
# 從外部驗證 80 port 與 ACME 路徑可達
curl -I http://$DOMAIN_NAME/.well-known/acme-challenge/ping
# 應該回 404（沒有對應檔案是正常的）；若 connection refused 表示 80 port 不通

# 看 certbot 詳細 log
docker compose --profile tls logs certbot --tail 100
```

---

## 專案結構

```
.
├── accounts/                 # 唯一的 app：使用者模型 + 認證 API
│   ├── models.py             # CustomUser（USERNAME_FIELD = email、UUIDv7 主鍵）
│   ├── views.py              # register / login / logout / users
│   ├── serializers.py        # 自訂 TokenObtainPair
│   └── urls.py
├── config/                   # Django project
│   ├── settings.py           # 全部環境差異值都從 env var 讀
│   └── urls.py
├── docker/
│   ├── entrypoint.sh         # wait-for-db → migrate → collectstatic → superuser → gunicorn
│   └── nginx/
│       ├── default.conf.template
│       └── ssl-params.conf.template
├── Dockerfile                # multi-stage：builder (build deps) → runtime (slim + libpq5)
├── docker-compose.yml        # db + web；nginx + certbot 在 profile: [tls]
├── .env.example              # 環境變數樣本（複製成 .env）
├── CLAUDE.md                 # Django/DRF 技術細節
└── README.md                 # 本檔
```
