"""Authenticated, database-backed recruitment information and teacher curation."""
import hashlib
import json
from calendar import monthrange
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.models import AccountActivity
from apps.graduate.constants import REAL_MAJORS
from .models import (CATEGORIES, EMPLOYER_TYPES, PROVINCES, STATUSES, EmploymentSource,
                     Opportunity, SavedOpportunity, SchedulerState, SyncRun)
from .expanded_collectors import track_of
from .serializers import (DigestInput, FeatureInput, OpportunityInput, SavedInput, SyncInput,
                          HUB_ZONE, item_data, local_date, local_iso, opportunity_status, source_data, sync_data)


def can_manage(user):
    return user.is_superuser or getattr(user, "role", "") in {"admin", "teacher"}


def require_manager(user):
    if not can_manage(user):
        raise PermissionDenied("仅教师或管理员可维护就业信息")


def log(user, action):
    AccountActivity.objects.create(user=user, module="就业信息", action=action[:255])


def filters_data():
    return {"majors": REAL_MAJORS, "provinces": PROVINCES, "categories": CATEGORIES,
            "employerTypes": EMPLOYER_TYPES, "statuses": STATUSES}


def scheduler_data():
    row = SchedulerState.objects.filter(key="default").first()
    alive = bool(row and row.status == "running" and not row.stop_requested and row.heartbeat_at
                 and -5 <= (timezone.now() - row.heartbeat_at).total_seconds() <= 90)
    return {"running": alive, "lastHeartbeat": local_iso(row.heartbeat_at) if row else None,
            "intervalSeconds": row.interval_seconds if row else 43200,
            "status": "running" if alive else "stopped", "stopRequested": row.stop_requested if row else False}


def saved_ids(user):
    return set(SavedOpportunity.objects.filter(user=user).values_list("opportunity_id", flat=True))


def stats_data(user):
    now = timezone.now()
    rows = list(Opportunity.objects.only("id", "registration_start", "registration_end", "is_featured", "created_at", "updated_at"))
    return {
        "total": len(rows), "addedToday": sum(local_date(r.created_at) == local_date(now) for r in rows),
        "closingSoon": sum(opportunity_status(r, now) == "即将截止" for r in rows),
        "open": sum(opportunity_status(r, now) in {"报名中", "即将截止"} for r in rows),
        "featured": sum(r.is_featured for r in rows), "saved": SavedOpportunity.objects.filter(user=user).count(),
        "sourcesConnected": EmploymentSource.objects.filter(enabled=True).exclude(adapter="manual").count(),
        "sourcesTotal": EmploymentSource.objects.count(),
        "lastUpdated": local_iso(max((r.updated_at for r in rows), default=None)),
    }


def int_query(params, key, default, maximum):
    try:
        value = int(params.get(key, default))
    except (TypeError, ValueError):
        raise serializers.ValidationError({key: "请输入整数"})
    if value < 1 or value > maximum:
        raise serializers.ValidationError({key: f"范围为 1 至 {maximum}"})
    return value


def flag_query(params, key):
    value = params.get(key, "")
    if value in {"", None}:
        return None
    if value not in {"0", "1", "true", "false"}:
        raise serializers.ValidationError({key: "仅支持 0/1 或 true/false"})
    return value in {"1", "true"}


def filtered_rows(request):
    params = request.query_params
    queryset = Opportunity.objects.select_related("source")
    q = params.get("q", "").strip()
    if len(q) > 200:
        raise serializers.ValidationError({"q": "关键词不能超过 200 字"})
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(employer__icontains=q) |
                                   Q(summary__icontains=q) | Q(requirements__icontains=q))
    for key, field, allowed in [("category", "category", CATEGORIES),
                                ("employerType", "employer_type", EMPLOYER_TYPES)]:
        value = params.get(key, "")
        if value:
            if value not in allowed:
                raise serializers.ValidationError({key: "不支持的筛选项"})
            queryset = queryset.filter(**{field: value})
    channel = params.get("channel", "")
    if channel:
        if channel not in {"exam", "company"}:
            raise serializers.ValidationError({"channel": "仅支持 exam/company"})
        queryset = queryset.filter(category="企业招聘") if channel == "company" else queryset.exclude(category="企业招聘")
    if params.get("sourceId"):
        queryset = queryset.filter(source_id=int_query(params, "sourceId", 1, 2147483647))
    user_saved = saved_ids(request.user)
    saved = flag_query(params, "saved")
    if saved is not None:
        queryset = queryset.filter(pk__in=user_saved) if saved else queryset.exclude(pk__in=user_saved)
    featured = flag_query(params, "featured")
    if featured is not None:
        queryset = queryset.filter(is_featured=featured)
    major, status = params.get("major", ""), params.get("status", "")
    if major and major not in REAL_MAJORS:
        raise serializers.ValidationError({"major": "不支持的专业"})
    if status and status not in STATUSES:
        raise serializers.ValidationError({"status": "不支持的报名状态"})
    province = params.get("province", "")
    track = params.get("companyTrack", "")
    if province and province not in PROVINCES:
        raise serializers.ValidationError({"province": "不支持的筛选项"})
    if track and track not in {"state", "internet", "other"}:
        raise serializers.ValidationError({"companyTrack": "不支持的企业分组"})
    now = timezone.now()
    rows = [row for row in queryset if (not major or major in row.related_majors or row.match_kind == "不限专业")
            and (not status or opportunity_status(row, now) == status)
            and (not province or row.province == province or province in row.metadata.get("locations", []))
            and (not track or (row.category == "企业招聘" and track_of(row) == track))]
    return rows, user_saved, now


def content_hash(row):
    fields = ["title", "category", "employer_type", "province", "employer", "published_at", "registration_start",
              "registration_end", "exam_at", "summary", "requirements", "related_majors", "match_kind", "match_reasons", "attachments"]
    return hashlib.sha256(json.dumps({key: getattr(row, key) for key in fields}, ensure_ascii=False, sort_keys=True,
                                    default=str).encode()).hexdigest()


class HubView(APIView):
    permission_classes = [IsAuthenticated]


class OpportunityListView(HubView):
    def get(self, request):
        rows, user_saved, now = filtered_rows(request)
        page = int_query(request.query_params, "page", 1, 1000000)
        page_size = int_query(request.query_params, "pageSize", 12, 100)
        return Response({"items": [item_data(row, user_saved, now) for row in rows[(page - 1) * page_size:page * page_size]],
                         "count": len(rows), "page": page, "pageSize": page_size, "stats": stats_data(request.user),
                         "filters": filters_data(), "canManage": can_manage(request.user)})

    def post(self, request):
        require_manager(request.user)
        serializer = OpportunityInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                row = Opportunity.objects.create(**serializer.validated_data)
                row.content_hash = content_hash(row)
                row.save(update_fields=["content_hash"])
                log(request.user, "补充公告：" + row.title)
        except IntegrityError:
            raise serializers.ValidationError({"url": "该公告链接已存在，请查看或更正已有记录"})
        return Response(item_data(row, saved_ids(request.user)), status=201)


class OpportunityDetailView(HubView):
    def get(self, request, pk):
        return Response(item_data(get_object_or_404(Opportunity.objects.select_related("source"), pk=pk), saved_ids(request.user)))

    def patch(self, request, pk):
        require_manager(request.user)
        try:
            with transaction.atomic():
                row = get_object_or_404(Opportunity.objects.select_for_update().select_related("source"), pk=pk)
                serializer = OpportunityInput(instance=row, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                changes = {}
                for key, value in serializer.validated_data.items():
                    old = getattr(row, key)
                    if old != value:
                        changes[key] = {"before": old, "after": value}
                        setattr(row, key, value)
                if changes:
                    serialized = json.loads(json.dumps(changes, ensure_ascii=False, default=str))
                    row.revisions = (row.revisions + [{"at": local_iso(timezone.now()), "actor": request.user.username,
                                                       "type": "老师更正", "changes": serialized}])[-20:]
                    # The collector hash represents the last source content, not teacher edits.
                    # Keeping it stable prevents an unchanged source overwriting reviewed fields.
                    if not row.source_id:
                        row.content_hash = content_hash(row)
                    row.save()
                    log(request.user, "核对公告：" + row.title)
        except IntegrityError:
            raise serializers.ValidationError({"url": "该链接已关联其他公告"})
        return Response(item_data(row, saved_ids(request.user)))


class MetaView(HubView):
    def get(self, request):
        return Response({"filters": filters_data(), "stats": stats_data(request.user), "canManage": can_manage(request.user),
                         "scheduler": scheduler_data()})


class SourceListView(HubView):
    def get(self, request):
        sources = list(EmploymentSource.objects.all())
        return Response({"items": [source_data(row) for row in sources], "summary": {
            "total": len(sources), "enabled": sum(row.enabled for row in sources),
            "success": sum(row.status == "success" for row in sources), "error": sum(row.status == "error" for row in sources),
            "partial": sum(row.status == "partial" for row in sources),
            "pending": sum(row.status in {"pending", "manual"} for row in sources)}})


class SaveView(HubView):
    def post(self, request, pk):
        row = get_object_or_404(Opportunity, pk=pk)
        serializer = SavedInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["saved"]:
            SavedOpportunity.objects.get_or_create(user=request.user, opportunity=row)
        else:
            SavedOpportunity.objects.filter(user=request.user, opportunity=row).delete()
        return Response(item_data(row, saved_ids(request.user)))


class FeatureView(HubView):
    @transaction.atomic
    def post(self, request, pk):
        require_manager(request.user)
        row = get_object_or_404(Opportunity.objects.select_for_update().select_related("source"), pk=pk)
        serializer = FeatureInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        row.is_featured = serializer.validated_data["featured"]
        row.save(update_fields=["is_featured", "updated_at"])
        log(request.user, ("加入精选：" if row.is_featured else "取消精选：") + row.title)
        return Response(item_data(row, saved_ids(request.user)))


def digest_date(value):
    return timezone.localtime(value, HUB_ZONE).strftime("%Y-%m-%d %H:%M") if value else "公告未明确，请核对原文"


class DigestView(HubView):
    def post(self, request):
        serializer = DigestInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(serializer.validated_data["ids"]))
        rows = {row.pk: row for row in Opportunity.objects.select_related("source").filter(pk__in=ids)}
        if len(rows) != len(ids):
            raise serializers.ValidationError({"ids": "部分公告不存在，请刷新后重新选择"})
        pieces = ["研究生就业与招考信息", "整理日期：" + local_date().isoformat()]
        for index, pk in enumerate(ids, start=1):
            row = rows[pk]
            pieces.append("\n" + str(index) + ". " + row.title)
            pieces.append("类型：" + row.category + "｜地区：" + row.province + "｜单位性质：" + row.employer_type)
            pieces.append("专业线索：" + ("、".join(row.related_majors) or "待核实") + "（" + row.match_kind + "，不代表报考资格认定）")
            pieces.append("报名开始：" + digest_date(row.registration_start))
            pieces.append("报名截止：" + digest_date(row.registration_end) + "｜状态：" + opportunity_status(row))
            if row.exam_at:
                pieces.append("考试时间：" + digest_date(row.exam_at))
            if row.summary:
                pieces.append("摘要：" + row.summary[:500])
            pieces.append("核对状态：" + row.review_state)
            pieces.append("原文：" + row.canonical_url)
        pieces.append("\n具体岗位条件、时间及变更以发布单位最新公告为准。")
        return Response({"text": "\n".join(pieces), "count": len(ids)})


class CalendarView(HubView):
    def get(self, request):
        month = request.query_params.get("month", local_date().strftime("%Y-%m"))
        try:
            first = date.fromisoformat(month + "-01")
            if first.strftime("%Y-%m") != month:
                raise ValueError()
            last = first.replace(day=monthrange(first.year, first.month)[1])
        except (ValueError, TypeError):
            raise serializers.ValidationError({"month": "月份格式应为 YYYY-MM"})
        rows, user_saved, now = filtered_rows(request)
        matching = [row for row in rows if any(value and first <= local_date(value) <= last
                                               for value in (row.registration_start, row.registration_end, row.exam_at))]
        return Response({"items": [item_data(row, user_saved, now) for row in matching[:1000]], "count": len(matching),
                         "truncated": len(matching) > 1000, "limit": 1000, "month": month})


class SyncView(HubView):
    def get(self, request):
        now = timezone.now()
        rows = list(SyncRun.objects.select_related("source")[:20])
        return Response({"items": [sync_data(row) for row in rows], "running": any(
            row.status in {"queued", "running"} and now - (row.heartbeat_at or row.created_at) < timedelta(minutes=5)
            for row in rows), "scheduler": scheduler_data()})

    def post(self, request):
        require_manager(request.user)
        serializer = SyncInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        source_id = serializer.validated_data.get("sourceId")
        if source_id:
            source = get_object_or_404(EmploymentSource, pk=source_id)
            if not source.enabled or source.adapter == "manual":
                raise serializers.ValidationError({"sourceId": "该来源尚未开通自动同步，可打开原站或人工补充"})
        from .collectors import queue_sync
        try:
            row = queue_sync(source_id=source_id, requested_by=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        log(request.user, "发起就业信息同步")
        return Response(sync_data(row), status=202)
