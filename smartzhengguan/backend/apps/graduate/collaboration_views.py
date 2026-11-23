"""Private task API; the public synthetic showcase remains separate."""
from datetime import timedelta
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.common.models import CollaborationTask, PrivacyExecution
from .privacy_views import PrivacyBaseView
from . import collaboration_tasks as tasks


class TaskInput(serializers.Serializer):
    title = serializers.CharField(max_length=100)
    question = serializers.CharField(min_length=8, max_length=1200)
    grade = serializers.CharField(max_length=20, allow_blank=True, default='')
    major = serializers.CharField(max_length=150, allow_blank=True, default='')
    topic = serializers.ChoiceField(choices=list(tasks.TOPICS))

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data)-set(self.fields):
            raise serializers.ValidationError({'detail': '仅接受任务需求与筛选条件，统计数据由服务器读取。'})
        return super().to_internal_value(data)


class ExecutionInput(serializers.Serializer):
    executionMode = serializers.ChoiceField(choices=['local', 'cloud'])
    payloadDigest = serializers.CharField(max_length=64)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data)-set(self.fields):
            raise serializers.ValidationError({'detail': '不接受自定义云端载荷。'})
        return super().to_internal_value(data)


def serialize(task, detail=True):
    data = {'id': task.pk, 'title': task.title, 'question': task.question, 'grade': task.grade,
            'major': task.major, 'topic': task.topic, 'status': task.status,
            'createdAt': task.created_at.isoformat(), 'updatedAt': task.updated_at.isoformat()}
    if detail:
        data.update(plan=task.plan, result=task.result)
    return data


class TaskBase(PrivacyBaseView):
    permission_classes = [IsAuthenticated]

    def owned(self, request, pk):
        # Interrupted server processes must not leave a task stuck forever.
        CollaborationTask.objects.filter(user=request.user, pk=pk, status='running',
            updated_at__lt=timezone.now()-timedelta(minutes=3)).update(status='failed')
        return get_object_or_404(CollaborationTask, pk=pk, user=request.user)


class CollaborationTaskList(TaskBase):
    def get(self, request):
        return Response({**tasks.catalog(), 'tasks': [serialize(t, False) for t in
            CollaborationTask.objects.filter(user=request.user)[:50]]})

    def post(self, request):
        serializer = TaskInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = tasks.scope_from_question(dict(serializer.validated_data))
            plan = tasks.build_plan(data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        task = CollaborationTask.objects.create(user=request.user, plan=plan, **data)
        return Response(serialize(task), status=201)


class CollaborationTaskDetail(TaskBase):
    def get(self, request, pk):
        return Response(serialize(self.owned(request, pk)))


class CollaborationTaskExecute(TaskBase):
    def post(self, request, pk):
        serializer = ExecutionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        task = self.owned(request, pk)
        if data['payloadDigest'] != task.plan['payloadDigest']:
            return Response({'detail': '任务检查版本不一致，请重新打开任务。'}, status=409)
        if data['executionMode'] == 'cloud' and (task.plan['route'] != 'cloud_eligible' or not tasks.privacy.cloud_available()):
            return Response({'detail': '本任务当前仅支持本地统计，请切换执行方式。'}, status=409)
        if task.status in ('completed', 'fallback'):
            return Response(serialize(task))  # retry after a lost response, never duplicate an API charge
        claimed = CollaborationTask.objects.filter(pk=task.pk, status='ready').update(status='running', updated_at=timezone.now())
        if not claimed:
            return Response({'detail': '任务正在执行或已中断，请刷新记录；需要重试时复制为新任务。'}, status=409)
        try:
            result = tasks.execute(task, data['executionMode'])
        except ValueError as exc:
            task.status = 'ready'
            task.save(update_fields=['status', 'updated_at'])
            return Response({'detail': str(exc)}, status=409)
        except Exception:
            task.status = 'failed'
            task.save(update_fields=['status', 'updated_at'])
            return Response({'detail': '执行中断，已保存任务；可复制为新任务重试。'}, status=503)
        task.result = result
        task.status = 'fallback' if result['audit']['executionMode'] == 'fallback' else 'completed'
        task.save(update_fields=['result', 'status', 'updated_at'])
        PrivacyExecution.objects.create(user=request.user, audit={**result['audit'], 'scenario': 'custom'})
        return Response(serialize(task))
