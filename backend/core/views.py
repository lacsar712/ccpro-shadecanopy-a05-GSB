from datetime import timedelta

from django.db.models import Count, Exists, OuterRef, Subquery
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClimateLog, Greenhouse, IrrigationCycle, TransplantEvent, Zone
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    TransplantEventSerializer,
    ZoneSerializer,
)
from .timewindow import TRANSPLANT_WINDOW_MINUTES


def zones_with_transplant_flags(now=None):
    """分区查询集，统一注解：

    - last_transplant_at：该分区最近一次移栽时刻；
    - in_transplant_window：当前是否处于最近移栽的前后窗口内。

    分区列表标记与仪表盘计数必须共用本查询集（同源），
    不允许在各处另行计算窗口。
    """
    now = now or timezone.now()
    span = timedelta(minutes=TRANSPLANT_WINDOW_MINUTES)
    latest_event = (
        TransplantEvent.objects.filter(zone=OuterRef("pk"))
        .order_by("-transplanted_at")
        .values("transplanted_at")[:1]
    )
    in_window_event = TransplantEvent.objects.filter(
        zone=OuterRef("pk"),
        transplanted_at__gte=now - span,
        transplanted_at__lte=now + span,
    )
    return Zone.objects.select_related("greenhouse").annotate(
        last_transplant_at=Subquery(latest_event),
        in_transplant_window=Exists(in_window_event),
    )


class GreenhouseViewSet(viewsets.ModelViewSet):
    serializer_class = GreenhouseSerializer

    def get_queryset(self):
        return Greenhouse.objects.annotate(zone_count=Count("zones"))


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        # 列表与单条都带同源的窗口标记。
        qs = zones_with_transplant_flags()
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class ClimateLogViewSet(viewsets.ModelViewSet):
    serializer_class = ClimateLogSerializer

    def get_queryset(self):
        qs = ClimateLog.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class TransplantEventViewSet(viewsets.ModelViewSet):
    serializer_class = TransplantEventSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = TransplantEvent.objects.select_related(
            "zone", "zone__greenhouse"
        ).all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class IrrigationCycleViewSet(viewsets.ModelViewSet):
    serializer_class = IrrigationCycleSerializer

    def get_queryset(self):
        qs = IrrigationCycle.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            qs = qs.filter(status=status)
        return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # 与分区列表共用同一注解查询集，保证该计数 == 列表 inTransplantWindow 为真的行数。
    zones_in_window = zones_with_transplant_flags(now).filter(
        in_transplant_window=True
    ).count()

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
            start_at__gte=today_start,
            start_at__lt=today_end,
        ).count(),
        "zonesInTransplantWindow": zones_in_window,
    }
    return Response(data)
