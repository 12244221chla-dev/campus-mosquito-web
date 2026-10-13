from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.overview, name="ph-overview"),
    path("scenarios/", views.scenario_list, name="ph-scenarios"),
    path("matters/", views.matter_collection, name="ph-matter-collection"),
    path("matters/list/", views.matter_list, name="ph-matter-list"),
    path("matters/<str:identifier>/", views.matter_detail, name="ph-matter-detail"),
    path("matters/<str:identifier>/advance/", views.matter_advance, name="ph-matter-advance"),
    path("matters/<str:identifier>/photo/", views.matter_photo, name="ph-matter-photo"),
    path("reminders/", views.reminder_list, name="ph-reminders"),
    path("reminders/<int:reminder_id>/ack/", views.reminder_ack, name="ph-reminder-ack"),
    path("timeline/", views.timeline, name="ph-timeline"),
    path("track/", views.matter_track, name="ph-track"),
    # 地图点位（自定义点位 + 已处理/未处理标记）
    path("map/points/", views.map_point_list, name="ph-map-points"),
    path("map/points/create/", views.map_point_collection, name="ph-map-point-create"),
    path("map/points/<int:point_id>/status/", views.map_point_status, name="ph-map-point-status"),
    path("map/points/<int:point_id>/delete/", views.map_point_delete, name="ph-map-point-delete"),
]
