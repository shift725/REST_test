"""
accounts app 單元測試

執行方式：
    python manage.py test accounts                          # 跑全部
    python manage.py test accounts.tests.CustomUserModelTests  # 跑單一 class
    python manage.py test accounts.tests.CustomUserModelTests.test_create_user_with_email  # 單一 method

每個 class 對應一個被測試的對象（model/view），class 內的每個 test_xxx
都只測試一個明確的行為，命名格式建議：test_<情境>_<預期結果>。
"""
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()  # 取得 settings.AUTH_USER_MODEL，等同 CustomUser


# ------------------------------------------------------------
# 1. Model 層測試：不打 API，直接驗證 model 的行為
# ------------------------------------------------------------
class CustomUserModelTests(APITestCase):
    """測試 CustomUser model 本身的行為（USERNAME_FIELD、UUIDv7 主鍵等）"""

    def test_create_user_with_email_success(self):
        """create_user 應能用 email + password 建立一般使用者"""
        # Arrange + Act
        user = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='strongpass123',
        )

        # Assert
        self.assertEqual(user.email, 'alice@example.com')
        self.assertEqual(user.username, 'alice')
        self.assertTrue(user.check_password('strongpass123'))  # 密碼有正確 hash
        self.assertFalse(user.check_password('wrongpass'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.role, 'member')  # default

    def test_create_superuser_success(self):
        """create_superuser 應建立 is_staff/is_superuser 都為 True 的使用者"""
        admin = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='adminpass123',
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_primary_key_is_uuidv7(self):
        """主鍵應為 UUID（UUIDv7Mixin 帶來的特性）"""
        user = User.objects.create_user(
            username='bob', email='bob@example.com', password='pass12345'
        )

        # 主鍵應為 UUID 物件，且版本應為 7
        self.assertIsInstance(user.id, uuid.UUID)
        self.assertEqual(user.id.version, 7)

    def test_str_returns_email(self):
        """__str__ 回傳 email，方便 admin 顯示"""
        user = User.objects.create_user(
            username='carol', email='carol@example.com', password='pass12345'
        )
        self.assertEqual(str(user), 'carol@example.com')

    def test_email_must_be_unique(self):
        """email 設為 unique，重複建立應丟出例外"""
        User.objects.create_user(
            username='u1', email='dup@example.com', password='pass12345'
        )

        # assertRaises 用 with 區塊：區塊內的程式必須丟出指定例外
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username='u2', email='dup@example.com', password='pass12345'
            )


# ------------------------------------------------------------
# 2. 註冊 API 測試
# ------------------------------------------------------------
class UserRegisterAPITests(APITestCase):
    """POST /api/auth/register/ 的各種情境"""

    def setUp(self):
        # reverse 用 url name 反查網址，比 hardcode '/api/auth/register/' 安全
        # 'auth' 來自 accounts/urls.py 的 app_name
        self.url = reverse('auth:register')
        self.valid_payload = {
            'username': 'newbie',
            'email': 'newbie@example.com',
            'password': 'strongpass123',
            'password_confirm': 'strongpass123',
            'phone': '0912345678',
        }

    def test_register_success_returns_201_and_tokens(self):
        """成功註冊應回 201 並包含 user 與 tokens"""
        response = self.client.post(self.url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['message'], '註冊成功')
        self.assertIn('user', response.data)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])

        # DB 應真的多了一筆使用者
        self.assertTrue(User.objects.filter(email='newbie@example.com').exists())

        # 密碼不應以明文回傳
        self.assertNotIn('password', response.data['user'])

    def test_register_password_mismatch_returns_400(self):
        """password 與 password_confirm 不同應回 400"""
        payload = {**self.valid_payload, 'password_confirm': 'different123'}

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)
        # 沒有任何使用者被建立
        self.assertEqual(User.objects.count(), 0)

    def test_register_duplicate_email_returns_400(self):
        """email 已存在應被 UniqueValidator 擋下"""
        User.objects.create_user(
            username='existing',
            email='newbie@example.com',  # 與 payload 同 email
            password='pass12345',
        )

        response = self.client.post(self.url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        # 訊息應為自訂的繁中訊息
        self.assertEqual(str(response.data['email'][0]), '此 email 已被註冊')

    def test_register_duplicate_username_returns_400(self):
        """username 已存在也應被擋下"""
        User.objects.create_user(
            username='newbie',  # 與 payload 同 username
            email='other@example.com',
            password='pass12345',
        )

        response = self.client.post(self.url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_register_short_password_returns_400(self):
        """密碼少於 8 碼應回 400（serializer 的 min_length=8）"""
        payload = {**self.valid_payload, 'password': 'short', 'password_confirm': 'short'}

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)


# ------------------------------------------------------------
# 3. 登入 API 測試
# ------------------------------------------------------------
class LoginAPITests(APITestCase):
    """POST /api/auth/login/ — 自訂的 CustomTokenObtainPairView"""

    @classmethod
    def setUpTestData(cls):
        # setUpTestData 整個 class 只跑一次，這裡的 user 不會被改動，適合放這
        cls.password = 'strongpass123'
        cls.user = User.objects.create_user(
            username='loginer',
            email='loginer@example.com',
            password=cls.password,
            role='staff',
        )

    def setUp(self):
        self.url = reverse('auth:login')

    def test_login_with_correct_credentials_returns_tokens(self):
        """正確 email + password 應回傳 access、refresh、user"""
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)
        # 自訂的 user 物件應包含這些欄位
        self.assertEqual(response.data['user']['email'], self.user.email)
        self.assertEqual(response.data['user']['username'], self.user.username)
        self.assertEqual(response.data['user']['role'], 'staff')

    def test_login_with_wrong_password_returns_401(self):
        """密碼錯誤應回 401"""
        response = self.client.post(
            self.url,
            {'email': self.user.email, 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_username_field_does_not_work(self):
        """用 username 而非 email 登入應失敗（USERNAME_FIELD = 'email'）"""
        response = self.client.post(
            self.url,
            {'username': self.user.username, 'password': self.password},
            format='json',
        )
        # 缺少必填的 email 欄位 → 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------
# 4. 登出 API 測試
# ------------------------------------------------------------
class LogoutAPITests(APITestCase):
    """POST /api/auth/logout/ — 將 refresh token 加入黑名單"""

    def setUp(self):
        self.url = reverse('auth:logout')
        self.user = User.objects.create_user(
            username='logoutuser',
            email='logout@example.com',
            password='pass12345',
        )
        # 直接用 simplejwt 產生 token，比走登入 API 快
        self.refresh = RefreshToken.for_user(self.user)
        # force_authenticate 跳過 JWT 驗證，直接把 request.user 設為指定使用者
        self.client.force_authenticate(user=self.user)

    def test_logout_success_blacklists_refresh_token(self):
        """成功登出後，該 refresh token 應無法再用來換 access token"""
        response = self.client.post(
            self.url, {'refresh': str(self.refresh)}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], '登出成功')

        # 驗證該 refresh 真的被列入黑名單
        # 拿同一個 refresh 去打 token/refresh/ 應該失敗
        refresh_url = reverse('auth:token_refresh')
        # logout 不需 access token，但 refresh 不一樣，這裡換個未認證 client
        self.client.force_authenticate(user=None)
        refresh_response = self.client.post(
            refresh_url, {'refresh': str(self.refresh)}, format='json'
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_with_invalid_token_returns_400(self):
        """傳入無效字串應回 400"""
        response = self.client.post(
            self.url, {'refresh': 'this-is-not-a-jwt'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_without_authentication_returns_401(self):
        """未登入直接打 logout 應回 401（permission_classes = IsAuthenticated）"""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url, {'refresh': str(self.refresh)}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ------------------------------------------------------------
# 5. 使用者列表 / 詳細 API 測試
# ------------------------------------------------------------
class UserListAPITests(APITestCase):
    """GET /api/auth/users/ — 需登入"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='member1', email='m1@example.com', password='pass12345'
        )
        cls.other = User.objects.create_user(
            username='member2', email='m2@example.com', password='pass12345'
        )

    def setUp(self):
        self.url = reverse('auth:user_list')

    def test_list_requires_authentication(self):
        """未登入時應回 401"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_all_users_when_authenticated(self):
        """已登入時應回所有使用者"""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class UserDetailAPITests(APITestCase):
    """GET / PATCH /api/auth/users/<uuid:pk>/"""

    def setUp(self):
        self.member = User.objects.create_user(
            username='mem', email='mem@example.com', password='pass12345',
            role='member',
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='pass12345',
        )
        self.url = reverse('auth:user_detail', kwargs={'pk': self.member.pk})

    # --- GET ---
    def test_detail_get_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_get_works_for_any_authenticated_user(self):
        """一般已登入使用者也能 GET（IsAuthenticated）"""
        self.client.force_authenticate(user=self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'mem@example.com')

    # --- PATCH ---
    def test_detail_patch_forbidden_for_non_admin(self):
        """非 admin 嘗試 PATCH 應回 403"""
        self.client.force_authenticate(user=self.member)
        response = self.client.patch(self.url, {'phone': '0900000000'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_patch_allowed_for_admin(self):
        """admin 可成功 PATCH"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {'phone': '0911222333'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 驗證 DB 真的被更新
        self.member.refresh_from_db()
        self.assertEqual(self.member.phone, '0911222333')
