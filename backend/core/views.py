from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, viewsets
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
from .services import (
    TransplantConflict,
    annotate_zone_window,
    create_transplant_event,
    is_inside_transplant_window,
    zones_in_transplant_window,
)


class GreenhouseViewSet(viewsets.ModelViewSet):
    queryset = Greenhouse.objects.annotate(zone_count=Count("zones")).all()
    serializer_class = GreenhouseSerializer


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        # lastTransplantAt / inTransplantWindow 由统一注解同源给出
        qs = annotate_zone_window(Zone.objects.select_related("greenhouse"))
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


class TransplantEventViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """移栽事件只允许登记（创建）与查看，不允许事后编辑/删除，

    以保证事件、分区作物名与联动气候记录三者一致。
    """

    serializer_class = TransplantEventSerializer

    def get_queryset(self):
        qs = TransplantEvent.objects.select_related(
            "zone", "zone__greenhouse"
        ).all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        zone = data["zone"]
        transplanted_at = data["transplanted_at"]

        # 序列化器已校验休耕/空闲备注；这里先做一次窗口预检，
        # 事务内 select_for_update 后还会复查，避免并发穿透。
        if is_inside_transplant_window(zone.pk, transplanted_at):
            raise TransplantConflict(
                "同一分区在移栽时刻前后 60 分钟内已有移栽事件"
            )

        event = create_transplant_event(
            zone=zone,
            to_crop=data["to_crop"],
            transplanted_at=transplanted_at,
            operator=data["operator"],
            notes=data.get("notes", ""),
        )
        return Response(
            self.get_serializer(event).data,
            status=201,
            headers=self.get_success_headers(serializer.data),
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # 与分区列表 inTransplantWindow=true 的行数同源（同一注解）
    window_zone_count = zones_in_transplant_window(now).count()

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
        "transplantWindowZoneCount": window_zone_count,
    }
    return Response(data)
