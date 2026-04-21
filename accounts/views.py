from django.db import IntegrityError
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    UserRegisterSerializer,
)


class UserRegisterView(generics.CreateAPIView):
    """
    使用者註冊視圖

    POST /api/auth/register/
    {
        "username": "newuser",
        "email": "new@example.com",
        "password": "password123",
        "password_confirm": "password123",
        "phone": "0912345678"
    }
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            # 保險：serializer 的 UniqueValidator 通過後，若有並行請求搶先註冊，
            # DB unique 限制會在此拋錯，改回 409 而不是 500。
            return Response(
                {'error': '帳號或 email 已被使用'},
                status=status.HTTP_409_CONFLICT,
            )

        # 註冊成功後自動回傳 token
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': '註冊成功',
            'user': UserSerializer(user).data,
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }
        }, status=status.HTTP_201_CREATED)


class UserListView(GenericAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        users = self.get_queryset()
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)


class UserDetailView(GenericAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        # GET 只需要 IsAuthenticated
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        # PATCH/DELETE 需要更高權限，例如 IsAdminUser
        return [IsAdminUser()]

    def get(self, request, pk):
        user = self.get_object()
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    def patch(self, request, pk):
        self.check_object_permissions(request, self.get_object())  # 檢查物件層級權限
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    自訂 Token 取得視圖

    POST /api/auth/login/
    {
        "email": "user@example.com",
        "password": "yourpassword"
    }

    回傳：
    {
        "access": "...",
        "refresh": "...",
        "user": {
            "id": 1,
            "username": "...",
            "email": "...",
            "role": "..."
        },
    }
    """
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    """
    登出視圖 - 將 refresh token 加入黑名單

    POST /api/auth/logout/
    {
        "refresh": "<refresh_token>"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()  # 需要啟用 blacklist app
            return Response({'message': '登出成功'}, status=status.HTTP_200_OK)
        except Exception:
            return Response(
                {'error': '無效的 token'},
                status=status.HTTP_400_BAD_REQUEST
            )
