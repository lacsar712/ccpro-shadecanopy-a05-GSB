"""移栽（换茬）共享业务规则。

移栽冲突判定与轮灌拦截必须共用同一时间窗函数，避免两处口径漂移：
任意时刻 ``at`` 与某分区某条移栽事件的移栽时刻相差不超过
``TRANSPLANT_WINDOW_MINUTES`` 分钟，即视为落在该事件的移栽窗口内。
"""
from datetime import timedelta
from decimal import Decimal

# 移栽窗口（分钟）：移栽时刻前后各 60 分钟
TRANSPLANT_WINDOW_MINUTES = 60

# 移栽成功后服务端自动补写气候记录时使用的默认值。
# 湿度默认 70%，取自 60～80 的默认区间（详见 README）。
TRANSPLANT_DEFAULT_HUMIDITY = Decimal("70.00")
TRANSPLANT_DEFAULT_TEMP_C = Decimal("25.00")


def transplant_window_bounds(at, minutes=TRANSPLANT_WINDOW_MINUTES):
    """返回时刻 ``at`` 前后各 ``minutes`` 分钟的窗口 (起点, 终点)，闭区间。"""
    span = timedelta(minutes=minutes)
    return at - span, at + span


def transplant_events_in_window(zone_id, at, exclude_event_id=None):
    """同一分区在 ``at`` 前后窗口内的移栽事件查询集。

    移栽创建的冲突判定与轮灌新建的拦截共用本函数。
    """
    from .models import TransplantEvent

    start, end = transplant_window_bounds(at)
    qs = TransplantEvent.objects.filter(
        zone_id=zone_id,
        transplanted_at__gte=start,
        transplanted_at__lte=end,
    )
    if exclude_event_id is not None:
        qs = qs.exclude(pk=exclude_event_id)
    return qs
