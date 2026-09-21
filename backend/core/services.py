"""移栽换茬相关的领域服务。

拦轮灌与移栽冲突判定共用 :func:`window_events_qs` 这同一个 ±60 分钟
时间窗函数；分区列表的窗口标记与仪表盘计数共用
:func:`annotate_zone_window`，保证两处同源、数量必然一致。
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, Max, OuterRef
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import ClimateLog, TransplantEvent, Zone

#: 移栽时刻前后各 60 分钟为移栽窗口（冲突判定 / 轮灌拦截共用）
TRANSPLANT_WINDOW = timedelta(minutes=60)

#: 移栽联动气候记录的默认湿度，取值落在 60～80 之间（详见 README）
TRANSPLANT_DEFAULT_HUMIDITY = Decimal("70.00")
#: 联动气候记录的默认温度（仅湿度默认值有 60～80 的业务约定）
TRANSPLANT_DEFAULT_TEMP_C = Decimal("24.00")


class TransplantConflict(APIException):
    """移栽窗口冲突 / 窗口内新建轮灌，HTTP 409。"""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "移栽时刻前后 60 分钟内存在时间窗冲突"
    default_code = "transplant_conflict"


def window_events_qs(zone_id, moment):
    """同一分区、与 ``moment`` 相距不超过 60 分钟的移栽事件。

    移栽冲突判定与轮灌拦截都走这里，禁止另写一份时间窗逻辑。
    """
    return TransplantEvent.objects.filter(
        zone_id=zone_id,
        transplanted_at__gte=moment - TRANSPLANT_WINDOW,
        transplanted_at__lte=moment + TRANSPLANT_WINDOW,
    )


def is_inside_transplant_window(zone_id, moment):
    return window_events_qs(zone_id, moment).exists()


def annotate_zone_window(qs, now=None):
    """给分区 queryset 同源注解最近移栽时刻与是否处于移栽窗口。"""
    now = now or timezone.now()
    return qs.annotate(
        last_transplant_at=Max("transplant_events__transplanted_at"),
        in_transplant_window=Exists(window_events_qs(OuterRef("pk"), now)),
    )


def zones_in_transplant_window(now=None):
    """当前处于移栽窗口的分区 queryset（列表标记与仪表盘共用）。"""
    now = now or timezone.now()
    return annotate_zone_window(Zone.objects.all(), now).filter(
        in_transplant_window=True
    )


@transaction.atomic
def create_transplant_event(*, zone, to_crop, transplanted_at, operator, notes):
    """创建移栽事件并在同一事务内完成作物名回写与气候记录写入。

    三步要么全部成功、要么全部回滚：
    1. 写移栽事件（from_crop 取分区当前作物名）；
    2. 把分区作物名改成新作物（空闲分区首次移栽后置为在种）；
    3. 写一条气候记录，采样时刻等于移栽时刻，湿度取默认 70%。
    """
    zone = Zone.objects.select_for_update().get(pk=zone.pk)

    # 加锁后复查窗口，挡住并发请求同时穿过预校验
    if is_inside_transplant_window(zone.pk, transplanted_at):
        raise TransplantConflict(
            "同一分区在移栽时刻前后 60 分钟内已有移栽事件"
        )

    event = TransplantEvent.objects.create(
        zone=zone,
        from_crop=zone.crop_name,
        to_crop=to_crop,
        transplanted_at=transplanted_at,
        operator=operator,
        notes=notes,
    )

    zone.crop_name = to_crop
    if zone.status == Zone.STATUS_IDLE:
        # 空闲分区允许移栽：栽上作物后即为在种
        zone.status = Zone.STATUS_GROWING
    # 在种分区移栽后仍保持在种；休耕在序列化器层已被拒绝
    zone.save(update_fields=["crop_name", "status", "updated_at"])

    ClimateLog.objects.create(
        zone=zone,
        recorded_at=transplanted_at,
        temp_c=TRANSPLANT_DEFAULT_TEMP_C,
        humidity_pct=TRANSPLANT_DEFAULT_HUMIDITY,
    )

    return event
