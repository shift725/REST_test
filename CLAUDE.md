# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案性質

此專案為作者學習 Django 所建立的 REST API 練習專案，目前僅實作帳號與認證功能（登入、註冊、登出、JWT token 管理、使用者查詢）。與使用者溝通時請使用繁體中文。

## 開發環境與常用指令

- Python 虛擬環境位於 `venv/`（已在 repo 中）。Windows bash (MSYS/Git Bash) 下啟用：`source venv/Scripts/activate`。
- 依賴列於 `requirements.txt`（注意：此檔以 UTF-16 編碼儲存，若需重新安裝請先轉為 UTF-8）。
- 資料庫為專案根目錄下的 `db.sqlite3`（已被 `.gitignore` 排除）。

常用指令（在專案根目錄執行）：

```bash
python manage.py runserver          # 啟動開發伺服器（預設 127.0.0.1:8000）
python manage.py makemigrations     # 產生 migration
python manage.py migrate            # 套用 migration
python manage.py createsuperuser    # 建立管理員帳號
python manage.py shell              # 進入 Django shell
python manage.py test               # 執行全部測試
python manage.py test accounts      # 只執行 accounts app 的測試
python manage.py test accounts.tests.ClassName.test_method   # 執行單一測試
```

目前 `accounts/tests.py` 尚未撰寫實際測試，但測試基礎設施已就緒。

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

- `config/settings.py` 目前使用開發用預設值（`DEBUG = True`、`ALLOWED_HOSTS = ['*']`、hardcoded `SECRET_KEY`）。若要部署或展示，需另行處理。
- `requirements.txt` 為 UTF-16 編碼，一般工具讀取時會看到空白字元間隔；編輯前建議先轉碼。
- Django admin：`CustomUser` 已透過 `CustomUserAdmin`（繼承 `UserAdmin`）註冊於 `accounts/admin.py`，並覆寫 `ordering`、`fieldsets`、`add_fieldsets` 以配合 email 登入與自訂欄位。未來新增繼承 `AbstractUser` 的 model 時請沿用相同模式，避免新增使用者時密碼以明文存入。一般 model 則在各 app 的 `admin.py` 中以 `@admin.register(Model)` 註冊即可。
