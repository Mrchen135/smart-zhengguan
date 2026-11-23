"""Validation and presentation for public announcements, not eligibility decisions."""
import ipaddress
import math
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers

from apps.graduate.constants import REAL_MAJORS
from .models import CATEGORIES, EMPLOYER_TYPES, MATCH_KINDS, PROVINCES, REVIEW_STATES

HUB_ZONE = ZoneInfo("Asia/Shanghai")


def public_url(value):
    """Validate links without fetching them; fetchers separately enforce their allowlist."""
    value = value.strip()
    if any(ord(char) < 32 for char in value) or "\\" in value:
        raise serializers.ValidationError("链接包含无效字符")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise serializers.ValidationError("请输入有效的公开网页链接")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise serializers.ValidationError("仅支持公开的 HTTP/HTTPS 链接")
    if port not in {None, 80, 443}:
        raise serializers.ValidationError("仅支持标准网页端口")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".localhost", ".local", ".internal")):
            raise serializers.ValidationError("不支持本机或内部网络地址")
    else:
        if not address.is_global:
            raise serializers.ValidationError("不支持本机或内部网络地址")
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"spm", "eqid"}]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(sorted(query)), ""))


class PublicURLField(serializers.URLField):
    def to_internal_value(self, data):
        return public_url(super().to_internal_value(data))


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("请输入对象格式的数据")
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({name: "不支持的字段" for name in sorted(unexpected)})
        return super().to_internal_value(data)


class AttachmentInput(StrictInput):
    name = serializers.CharField(max_length=200)
    url = PublicURLField(max_length=2048)


class OpportunityInput(StrictInput):
    title = serializers.CharField(max_length=300)
    url = PublicURLField(source="canonical_url", max_length=2048)
    category = serializers.ChoiceField(choices=CATEGORIES)
    province = serializers.ChoiceField(choices=PROVINCES, default="全国")
    employerType = serializers.ChoiceField(source="employer_type", choices=EMPLOYER_TYPES, default="未说明")
    employer = serializers.CharField(max_length=200, allow_blank=True, default="")
    publishedAt = serializers.DateField(source="published_at", allow_null=True, default=None)
    registrationStart = serializers.DateTimeField(source="registration_start", allow_null=True, default=None, default_timezone=HUB_ZONE)
    registrationEnd = serializers.DateTimeField(source="registration_end", allow_null=True, default=None, default_timezone=HUB_ZONE)
    examAt = serializers.DateTimeField(source="exam_at", allow_null=True, default=None, default_timezone=HUB_ZONE)
    summary = serializers.CharField(max_length=16000, allow_blank=True, default="")
    requirements = serializers.CharField(max_length=30000, allow_blank=True, default="")
    relatedMajors = serializers.ListField(source="related_majors", child=serializers.ChoiceField(choices=REAL_MAJORS), max_length=8, default=list)
    matchKind = serializers.ChoiceField(source="match_kind", choices=MATCH_KINDS, default="待核实")
    matchReasons = serializers.ListField(source="match_reasons", child=serializers.CharField(max_length=500), max_length=12, default=list)
    attachments = AttachmentInput(many=True, default=list)
    reviewState = serializers.ChoiceField(source="review_state", choices=REVIEW_STATES, default="待核对")

    def validate(self, values):
        instance = self.instance
        start = values.get("registration_start", getattr(instance, "registration_start", None))
        end = values.get("registration_end", getattr(instance, "registration_end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"registrationEnd": "报名截止时间必须晚于开始时间"})
        if "related_majors" in values:
            values["related_majors"] = list(dict.fromkeys(values["related_majors"]))
        return values


class SavedInput(StrictInput):
    saved = serializers.BooleanField()


class FeatureInput(StrictInput):
    featured = serializers.BooleanField()


class DigestInput(StrictInput):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=30)


class SyncInput(StrictInput):
    sourceId = serializers.IntegerField(min_value=1, required=False, allow_null=True)


def opportunity_status(row, now=None):
    now = now or timezone.now()
    start, end = row.registration_start, row.registration_end
    if end and end <= now:
        return "已截止"
    if start and start > now:
        return "尚未开始"
    if not start or not end:
        return "时间待核实"
    if end - now <= timedelta(days=3):
        return "即将截止"
    return "报名中"


def local_iso(value):
    return timezone.localtime(value, HUB_ZONE).isoformat() if value else None


def local_date(value=None):
    return timezone.localtime(value or timezone.now(), HUB_ZONE).date()


def item_data(row, saved_ids=None, now=None):
    now = now or timezone.now()
    return {
        "id": row.pk, "title": row.title, "category": row.category,
        "employerType": row.employer_type, "province": row.province, "employer": row.employer,
        "sourceId": row.source_id, "sourceName": row.source.name if row.source_id else "老师补充",
        "sourceUrl": row.source.url if row.source_id else row.canonical_url, "url": row.canonical_url,
        "publishedAt": row.published_at.isoformat() if row.published_at else None,
        "registrationStart": local_iso(row.registration_start), "registrationEnd": local_iso(row.registration_end),
        "examAt": local_iso(row.exam_at), "summary": row.summary, "requirements": row.requirements,
        "relatedMajors": row.related_majors, "matchKind": row.match_kind, "matchReasons": row.match_reasons,
        "metadata": row.metadata, "attachments": row.attachments, "featured": row.is_featured, "reviewState": row.review_state,
        "status": opportunity_status(row, now),
        "daysLeft": math.ceil((row.registration_end - now).total_seconds() / 86400) if row.registration_end else None,
        "saved": row.pk in (saved_ids or set()), "lastSeen": local_iso(row.last_seen),
        "createdAt": local_iso(row.created_at), "updatedAt": local_iso(row.updated_at), "revisions": row.revisions,
    }


def source_data(row):
    return {"id": row.pk, "key": row.key, "name": row.name, "url": row.url,
            "province": row.province, "category": row.category, "adapter": row.adapter,
            "enabled": row.enabled, "status": row.status, "lastChecked": local_iso(row.last_checked),
            "lastSuccess": local_iso(row.last_success), "lastError": row.last_error, "metadata": row.metadata}


def sync_data(row):
    return {"id": row.pk, "sourceId": row.source_id, "sourceName": row.source.name if row.source_id else "全部已启用来源",
            "status": row.status, "startedAt": local_iso(row.started_at), "finishedAt": local_iso(row.finished_at),
            "heartbeatAt": local_iso(row.heartbeat_at), "createdCount": row.created_count,
            "updatedCount": row.updated_count, "checkedCount": row.checked_count, "error": row.error,
            "metadata": row.metadata, "createdAt": local_iso(row.created_at)}
