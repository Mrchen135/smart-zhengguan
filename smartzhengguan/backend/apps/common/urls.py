from django.urls import path

from apps.common.views import ApiIndexView, HealthCheckView
from apps.common.workspace import PersonalCenterView, PasswordView, SettingsView, NotificationsView, AcademicEventView, ExportDownloadView, SearchHistoryView


urlpatterns = [
    path("", ApiIndexView.as_view(), name="api-index"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("personal-center/", PersonalCenterView.as_view()),
    path("change-password/", PasswordView.as_view()),
    path("system-settings/", SettingsView.as_view()),
    path("notifications/", NotificationsView.as_view()),
    path("search-history/", SearchHistoryView.as_view()),
    path("academic-status/records/<str:external_id>/", AcademicEventView.as_view()),
    path("export/download/<str:record_id>/", ExportDownloadView.as_view()),
]
