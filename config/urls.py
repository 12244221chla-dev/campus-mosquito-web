from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from mosquito import views
from mosquito import portal
from pubhealth import views as pubhealth_views
from pubhealth import mini


urlpatterns = [
    path('api/mini/session/', mini.session),
    path('api/mini/account/', mini.account),
    path('api/mini/logout/', mini.signout),
    path("account/", portal.account_page),
    path("account/logout/", portal.logout_view),
    path("api/session/", portal.session_info),
    path("manage/", portal.manage),
    path("manage/review/<uuid:record_id>/", portal.review_record),
    path("maps/<int:map_id>/image/", portal.map_image),
    path("admin/report-photos/<uuid:report_id>/", views.report_photo, name="report-photo"),
    path("admin/dorm-record-photos/<uuid:record_id>/", views.dorm_record_photo, name="dorm-record-photo"),
    path("admin/", admin.site.urls),
    # 公共卫生管理平台：驾驶舱 + 报备与进度跟踪（合二为一，单一入口）
    path("", pubhealth_views.home_page, name="public-health-home"),
    path("cockpit/", pubhealth_views.cockpit_page, name="cockpit"),
    path("report/", pubhealth_views.matter_page, name="matter-report"),
    path("track/", RedirectView.as_view(url="/report/#track", permanent=False), name="matter-track-page"),
    path("api/v1/", include("pubhealth.urls")),
    # 防蚊专项页面（原首页，保留兼容）
    path("vector/", views.public_page, name="vector-home"),
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
