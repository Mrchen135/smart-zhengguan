"""Public recruitment information; never contains student profiles or resumes."""
from django.conf import settings
from django.db import models
from django.utils import timezone


CATEGORIES = ["选调生", "公务员", "事业单位", "人才引进", "企业招聘"]
EMPLOYER_TYPES = ["央企", "国企", "民企", "未说明", "不适用"]
MATCH_KINDS = ["明确提及", "方向相关", "不限专业", "待核实"]
REVIEW_STATES = ["待核对", "已核对"]
PROVINCES = ["全国", "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "港澳台", "境外"]
STATUSES = ["报名中", "即将截止", "尚未开始", "已截止", "时间待核实"]


def choices(values):
    return [(value, value) for value in values]


class EmploymentSource(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=2048)
    province = models.CharField(max_length=20, default="全国")
    category = models.CharField(max_length=30, default="企业招聘")
    adapter = models.CharField(max_length=50, default="manual")
    enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=30, default="pending")
    last_checked = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["province", "name", "pk"]


Source = EmploymentSource


class Opportunity(models.Model):
    source = models.ForeignKey(EmploymentSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities")
    canonical_url = models.URLField(max_length=2048, unique=True)
    title = models.CharField(max_length=300)
    category = models.CharField(max_length=30, choices=choices(CATEGORIES))
    employer_type = models.CharField(max_length=20, choices=choices(EMPLOYER_TYPES), default="未说明")
    province = models.CharField(max_length=20, default="全国")
    employer = models.CharField(max_length=200, blank=True)
    published_at = models.DateField(null=True, blank=True)
    registration_start = models.DateTimeField(null=True, blank=True)
    registration_end = models.DateTimeField(null=True, blank=True)
    exam_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    related_majors = models.JSONField(default=list, blank=True)
    match_kind = models.CharField(max_length=20, choices=choices(MATCH_KINDS), default="待核实")
    match_reasons = models.JSONField(default=list, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    is_featured = models.BooleanField(default=False)
    review_state = models.CharField(max_length=20, choices=choices(REVIEW_STATES), default="待核对")
    metadata = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    last_seen = models.DateTimeField(default=timezone.now)
    revisions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at", "-pk"]
        indexes = [models.Index(fields=["category", "province"]), models.Index(fields=["registration_end"])]


class SavedOpportunity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "opportunity"], name="employmenthub_unique_save")]


class SyncRun(models.Model):
    source = models.ForeignKey(EmploymentSource, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default="queued")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    checked_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class SchedulerState(models.Model):
    key = models.CharField(max_length=30, unique=True, default="default")
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    interval_seconds = models.PositiveIntegerField(default=43200)
    pid = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, default="idle")
    stop_requested = models.BooleanField(default=False)
