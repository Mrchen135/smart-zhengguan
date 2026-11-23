"""Public synthetic-only showcase endpoints; no access to student data."""
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import privacy
from apps.common.models import PrivacyExecution


class PrivacyTaskSerializer(serializers.Serializer):
    scenario = serializers.ChoiceField(choices=[item["id"] for item in privacy.SCENARIOS])
    includeIdentifiers = serializers.BooleanField(default=True)
    executionMode = serializers.ChoiceField(choices=["local", "cloud"], default="local")

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["仅接受演示场景选项，不接受原始学生数据或自定义模型载荷"]})
        return super().to_internal_value(data)


class PrivacyDemoThrottle(SimpleRateThrottle):
    def get_rate(self):
        return "30/min"

    def get_cache_key(self, request, view):
        return "privacy-demo:" + request.META.get("REMOTE_ADDR", "unknown")


class PrivacyBaseView(APIView):
    # Public fictional samples; authenticated audit history is scoped to its owner.
    permission_classes = [AllowAny]
    throttle_classes = [PrivacyDemoThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def options_data(self, request):
        serializer = PrivacyTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class PrivacyCatalogView(PrivacyBaseView):
    def get(self, request):
        data = privacy.get_catalog()
        data['auditEntries'] = list(PrivacyExecution.objects.filter(user=request.user).exclude(audit__scenario='custom').values_list('audit', flat=True)[:20]) if request.user.is_authenticated else []
        return Response(data)


class PrivacyInspectView(PrivacyBaseView):
    def post(self, request):
        data = self.options_data(request)
        return Response(privacy.inspect_task(data["scenario"], data["includeIdentifiers"]))


class PrivacyExecuteView(PrivacyBaseView):
    def post(self, request):
        data = self.options_data(request)
        try:
            result = privacy.execute_task(data["scenario"], data["includeIdentifiers"], data["executionMode"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        if request.user.is_authenticated:
            PrivacyExecution.objects.create(user=request.user, audit=result['audit'])
        return Response(result)
