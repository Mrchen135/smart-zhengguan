"""Database-backed account, workspace preferences and per-account notifications."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.conf import settings
from django.http import FileResponse
from pathlib import Path
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.common.models import AccountActivity, NoticeRead, WorkspaceSetting
from apps.graduate.models import AcademicStatusEvent, ModuleNotice, ExportRecord


def log(user, module, action):
    AccountActivity.objects.create(user=user, module=module, action=action)


def logs(user, module=None):
    rows = AccountActivity.objects.filter(user=user)
    if module:
        rows = rows.filter(module=module)
    return [{'time': timezone.localtime(r.created_at).strftime('%Y-%m-%d %H:%M'),
             'module': r.module, 'action': r.action, 'device': '浏览器',
             'status': '成功', 'statusType': 'success'} for r in rows[:30]]


def profile(user):
    return {'name': user.get_full_name() or user.username, 'role': user.get_role_display(),
            'department': user.department, 'jobNo': user.username, 'phone': user.phone,
            'email': user.email, 'lastLogin': timezone.localtime(user.last_login).strftime('%Y-%m-%d %H:%M') if user.last_login else '首次登录'}


class LoginView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            from apps.accounts.models import User
            user = User.objects.get(username=request.data['username'])
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            log(user, '登录', '账号登录')
        return response


class ProfileInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    department = serializers.CharField(max_length=100, allow_blank=True)
    phone = serializers.CharField(max_length=20, allow_blank=True)
    email = serializers.EmailField(allow_blank=True)


class PersonalCenterView(APIView):
    def get(self, request):
        user = request.user
        return Response({'title': '个人中心', 'subtitle': '账号资料与操作记录由数据库保存',
                         'profile': profile(user), 'statCards': [],
                         'profileTags': [{'label': user.get_role_display(), 'type': 'info'}],
                         'operationLogs': logs(user),
                         'quickActions': [{'label': '修改密码', 'desc': '更新当前账号密码', 'route': '/change-pwd'},
                                          {'label': '系统设置', 'desc': '查看工作台配置', 'route': '/system'}],
                         'shortcuts': [{'label': '数据管理', 'route': '/data-management'},
                                       {'label': '综合画像', 'route': '/query-results'}]})

    @transaction.atomic
    def patch(self, request):
        serializer = ProfileInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        user = request.user
        user.first_name, user.last_name = values.pop('name'), ''
        for key, value in values.items():
            setattr(user, key, value)
        user.save(update_fields=['first_name', 'last_name', 'department', 'phone', 'email'])
        log(user, '个人中心', '更新个人资料')
        return self.get(request)


class PasswordInput(serializers.Serializer):
    currentPassword = serializers.CharField(trim_whitespace=False)
    newPassword = serializers.CharField(trim_whitespace=False)
    confirmPassword = serializers.CharField(trim_whitespace=False)


class PasswordView(APIView):
    def get(self, request):
        return Response({'title': '修改密码', 'subtitle': '更新数据库中的当前账号密码',
                         'securityTips': [{'title': '密码要求', 'desc': '至少 8 位，避免常见密码、纯数字或与账号相似的内容。'},
                                          {'title': '账号安全', 'desc': '修改成功后请重新登录。'}],
                         'passwordLogs': logs(request.user, '密码')})

    @transaction.atomic
    def post(self, request):
        serializer = PasswordInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if not request.user.check_password(values['currentPassword']):
            raise serializers.ValidationError({'currentPassword': '当前密码不正确'})
        if values['newPassword'] != values['confirmPassword']:
            raise serializers.ValidationError({'confirmPassword': '两次输入的新密码不一致'})
        try:
            validate_password(values['newPassword'], request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'newPassword': list(exc.messages)})
        request.user.set_password(values['newPassword'])
        request.user.save(update_fields=['password'])
        log(request.user, '密码', '修改密码')
        return Response({'detail': '密码修改成功，请重新登录'})


DEFAULT_SETTINGS = {'default_page': '/home', 'batch_page_size': 20}
ALLOWED_PAGES = ['/home', '/academic-status', '/data-management', '/intelligent-prediction', '/query-results']


def workspace_settings():
    return {**DEFAULT_SETTINGS, **dict(WorkspaceSetting.objects.values_list('key', 'value'))}


class SettingsInput(serializers.Serializer):
    default_page = serializers.ChoiceField(choices=ALLOWED_PAGES)
    batch_page_size = serializers.ChoiceField(choices=[10, 20, 50, 100])


class SettingsView(APIView):
    def get(self, request):
        return Response({'values': workspace_settings(), 'canEdit': request.user.is_superuser or request.user.role == 'admin',
                         'updatedAt': WorkspaceSetting.objects.order_by('-updated_at').values_list('updated_at', flat=True).first(),
                         'logs': logs(request.user, '系统设置')})

    @transaction.atomic
    def patch(self, request):
        if not (request.user.is_superuser or request.user.role == 'admin'):
            raise PermissionDenied('仅管理员可修改全站配置')
        serializer = SettingsInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        for key, value in serializer.validated_data.items():
            WorkspaceSetting.objects.update_or_create(key=key, defaults={'value': value, 'updated_by': request.user})
        log(request.user, '系统设置', '更新默认入口与批次分页配置')
        return self.get(request)


class NotificationsView(APIView):
    def get(self, request):
        notices = list(ModuleNotice.objects.all()[:50])
        read_ids = set(NoticeRead.objects.filter(user=request.user, notice__in=notices).values_list('notice_id', flat=True))
        return Response([{'id': n.pk, 'title': n.title, 'content': n.content,
                          'time': str(n.notice_date), 'read': n.pk in read_ids} for n in notices])

    @transaction.atomic
    def post(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or len(ids) > 50 or any(type(i) is not int for i in ids):
            raise serializers.ValidationError({'ids': '请提供不超过 50 条消息编号'})
        for notice in ModuleNotice.objects.filter(pk__in=ids):
            NoticeRead.objects.get_or_create(user=request.user, notice=notice)
        return self.get(request)


class SearchHistoryView(APIView):
    def get(self, request):
        values = AccountActivity.objects.filter(user=request.user, module='搜索历史').values_list('action', flat=True)[:100]
        return Response(list(dict.fromkeys(values))[:8])

    def post(self, request):
        serializer = serializers.CharField(max_length=255)
        keyword = serializer.run_validation(request.data.get('keyword'))
        log(request.user, '搜索历史', keyword)
        return self.get(request)

    def delete(self, request):
        AccountActivity.objects.filter(user=request.user, module='搜索历史').delete()
        return Response([])


class AcademicEventInput(serializers.Serializer):
    changeType = serializers.CharField(max_length=100)
    handler = serializers.CharField(max_length=100, allow_blank=True)
    reason = serializers.CharField(max_length=255, allow_blank=True)
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=['办理中', '已通过', '待审核', '已退回', '待提交', '处理中'])


class AcademicEventView(APIView):
    @transaction.atomic
    def patch(self, request, external_id):
        if not (request.user.is_superuser or request.user.role == 'admin'):
            raise PermissionDenied('仅管理员可编辑学籍记录')
        event = get_object_or_404(AcademicStatusEvent, external_id=external_id)
        serializer = AcademicEventInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        event.change_type, event.handler_name = values['changeType'], values['handler']
        event.reason, event.occurred_on = values['reason'], values['date']
        event.status = {'办理中': 'in_progress', '已通过': 'completed', '待审核': 'pending', '已退回': 'rejected', '待提交': 'draft', '处理中': 'in_progress'}[values['status']]
        event.status_tag = {'已通过': 'success', '已退回': 'danger'}.get(values['status'], 'warning')
        event.save()
        log(request.user, '学籍管理', '更新学籍异动记录')
        return Response({'detail': '已保存到数据库'})


class ExportDownloadView(APIView):
    def get(self, request, record_id):
        record = get_object_or_404(ExportRecord, record_id=record_id, operator=request.user)
        if record.status != 'completed' or (record.expires_at and record.expires_at <= timezone.now()):
            return Response({'detail': '导出文件未完成或已过期，请重新生成'}, status=410)
        root = (Path(settings.BASE_DIR) / 'tmp' / 'exports').resolve()
        path = Path(record.file_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return Response({'detail': '文件不存在，请重新生成'}, status=404)
        return FileResponse(path.open('rb'), as_attachment=True, filename=record.file_name,
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
