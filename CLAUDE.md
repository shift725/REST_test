# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案性質

此專案為作者學習 Django 所建立的 REST API 練習專案，目前僅實作帳號與認證功能（登入、註冊、登出、JWT token 管理、使用者查詢）。與使用者溝通時請使用繁體中文。

## 開發環境與常用指令

本專案預設以 **Docker Compose + PostgreSQL** 運行（見 `docker-compose.yml`、`docker/entrypoint.sh`）。根目錄的 `db.sqlite3` 為早期遺留檔（已被 `.gitignore` 排除），非目前主要資料庫。

依賴分兩層：

- `requirements.txt`：**runtime 依賴**，會被打進 Docker image（Django、DRF、gunicorn、whitenoise、psycopg、dj-database-url、python-decouple 等）。已為 UTF-8 編碼。
- `requirements-dev.txt`：**開發／CI 專用**，以 `-r requirements.txt` 繼承 runtime 並額外加入 `ruff`、`coverage`；**不會**進 runtime image（工具設定見 `pyproject.toml`）。

### Docker（建議流程）

```bash
cp .env.example .env                              # 首次：填 SECRET_KEY、DB 密碼等
docker compose up -d --build                      # 起 db + web；entrypoint 會自動 migrate / collectstatic / 建 admin
docker compose logs -f web                        # 看啟動 log
docker compose exec web python manage.py test     # 在容器內跑測試
docker compose down                               # 停止（資料保留於 pgdata volume）
```

### 本機 venv（次要；需自備 `DATABASE_URL`）

`venv/` 已在 repo 中。Windows bash (MSYS/Git Bash) 下啟用：`source venv/Scripts/activate`。

注意：`settings.py` 以 `config('DATABASE_URL')` 讀資料庫**且無預設值**；`.env` 只提供 `POSTGRES_*`/`DB_*` 元件變數，真正的 `DATABASE_URL` 是 `docker-compose.yml` 組出來注入 `web` 容器的。因此在容器外直接跑 `manage.py` 時，必須自行提供 `DATABASE_URL`，否則載入 settings 就會失敗：

```bash
pip install -r requirements-dev.txt               # 裝 runtime + dev 工具
export DATABASE_URL="sqlite:///dev.sqlite3"       # 或指向本機 Postgres
python manage.py migrate
python manage.py test                             # 全部測試（22 個，位於 accounts/tests.py）
python manage.py test accounts.tests.ClassName.test_method   # 跑單一測試
python manage.py makemigrations
python manage.py shell
```

### Lint／覆蓋率（dev 工具，設定見 `pyproject.toml`）

```bash
ruff check .                                      # lint（目前有少量既有 violation 待整理）
ruff format .                                     # 格式化
coverage run manage.py test && coverage report    # 覆蓋率（同樣需要 DATABASE_URL）
```

`accounts/tests.py` 已有實際測試（涵蓋 model、serializer、認證流程等，共 22 個 test），測試基礎設施已就緒。

## 架構概念（需要跨檔案理解的部分）

### 專案骨架

- `config/` 為 Django project 層，`config.settings` 為設定檔，`config.urls` 僅掛載 `admin/` 與 `api/auth/`（後者 include 自 `accounts.urls`）。
- `accounts/` 為唯一的 app，同時負責使用者模型與認證 API。未來新增功能請建立新的 app 並在 `config/urls.py` 掛上對應前綴。

### 自訂使用者模型（重要）

`accounts.CustomUser`（`accounts/models.py`）有兩個非預設的關鍵特性，會影響整個專案：

1. **以 `email` 作為登入帳號**：`USERNAME_FIELD = 'email'`，`username` 仍保留但只作為顯示名稱。DRF 的登入 serializer（`CustomTokenObtainPairSerializer`）因此接受 `email` + `password`，而非 `username`。
2. **UUIDv7 主鍵**：透過 `UUIDv7Mixin` 以 `uuid_utils.compat.uuid7` 生成主鍵，因此 URL 路由使用 `<uuid:pk>`（見 `accounts/urls.py`），而非 `<int:pk>`。新 model 若需同種主鍵，繼承 `UUIDv7Mixin` 即可。

`settings.AUTH_USER_MODEL = 'accounts.CustomUser'` 必須保留——改動會導致既有 migration 無法重建。

### 認證流程

- 採用 `rest_framework_simplejwt`，已啟用 `token_blacklist` app 以支援登出。
- JWT 設定（`config/settings.py` 的 `SIMPLE_JWT`）：access token 30 分鐘、refresh token 7 天、refresh 時自動輪換並將舊 refresh 加入黑名單。
- DRF `DEFAULT_PERMISSION_CLASSES` 為 `AllowAny`，因此需要登入的 endpoint 必須在 view 中明確指定 `permission_classes = [IsAuthenticated]`（或 `IsAdminUser` 等）。
- `CustomTokenObtainPairSerializer` 會在 JWT payload 內額外加入 `username`、`email`、`role`、`is_staff`，並在登入回應附帶 `user` 物件；修改使用者欄位時兩處都要同步。
- `LogoutView` 需要呼叫端傳入 `refresh` token 以加入黑名單，而非僅依賴 access token。

### API 端點（全部以 `/api/auth/` 為前綴）

- `POST login/`、`POST register/`、`POST logout/`
- `POST token/refresh/`、`POST token/verify/`（直接使用 simplejwt 內建 view）
- `GET users/`（需登入）、`GET/PATCH users/<uuid:pk>/`（GET 需登入；PATCH 需 `IsAdminUser`）

## 開發注意事項

- `config/settings.py` 已全面改吃環境變數（透過 `python-decouple`）：`SECRET_KEY` **無預設值**（缺值直接報錯，避免誤用不安全的 fallback）、`DEBUG` 預設 `False`、`ALLOWED_HOSTS` 以逗號分隔（`Csv()`，預設空）、資料庫由 `DATABASE_URL` 經 `dj-database-url` 解析。生產環境務必設定強隨機 `SECRET_KEY` 並維持 `DEBUG=False`。本機 `.env` 內的 `DEBUG=True` 僅供開發。
- 依賴分流：新增 runtime 依賴改 `requirements.txt`（會進 image）；新增開發／CI 工具（lint、coverage 等）改 `requirements-dev.txt`（不進 image）。`requirements.txt` 現為 UTF-8 編碼（早期曾是 UTF-16，已轉換）。
- Django admin：`CustomUser` 已透過 `CustomUserAdmin`（繼承 `UserAdmin`）註冊於 `accounts/admin.py`，並覆寫 `ordering`、`fieldsets`、`add_fieldsets` 以配合 email 登入與自訂欄位。未來新增繼承 `AbstractUser` 的 model 時請沿用相同模式，避免新增使用者時密碼以明文存入。一般 model 則在各 app 的 `admin.py` 中以 `@admin.register(Model)` 註冊即可。
