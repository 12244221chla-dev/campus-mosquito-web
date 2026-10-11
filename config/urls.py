from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from mosquito import views


urlpatterns = [
    path("admin/report-photos/<uuid:report_id>/", views.report_photo, name="report-photo"),
    path("admin/dorm-record-photos/<uuid:record_id>/", views.dorm_record_photo, name="dorm-record-photo"),
    path("admin/", admin.site.urls),
    path("", views.public_page, name="public-home"),
    path("report.html", views.report_page, name="public-report"),
    path("index.html", RedirectView.as_view(url="/", permanent=False)),
    path("report.css", RedirectView.as_view(url="/static/report.css", permanent=False)),
    path("report.js", RedirectView.as_view(url="/static/report.js", permanent=False)),
    path("api/reports/", views.report_collection, name="report-collection"),
    path("api/reports/<uuid:report_id>/", views.report_detail, name="report-detail"),
    path("api/areas/", views.campus_areas, name="campus-areas"),
    path("api/dorms/", views.dorm_rooms, name="dorm-rooms"),
    path("api/dorm-records/", views.dorm_record_collection, name="dorm-record-collection"),
    path("api/dorm-records/<uuid:record_id>/", views.dorm_record_detail, name="dorm-record-detail"),
    path("health/", views.health, name="health"),
]
