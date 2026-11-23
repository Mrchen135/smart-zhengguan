from django.urls import path
from . import views

urlpatterns = [
    path("", views.OpportunityListView.as_view()),
    path("meta/", views.MetaView.as_view()),
    path("sources/", views.SourceListView.as_view()),
    path("calendar/", views.CalendarView.as_view()),
    path("digest/", views.DigestView.as_view()),
    path("sync/", views.SyncView.as_view()),
    path("<int:pk>/", views.OpportunityDetailView.as_view()),
    path("<int:pk>/save/", views.SaveView.as_view()),
    path("<int:pk>/feature/", views.FeatureView.as_view()),
]
