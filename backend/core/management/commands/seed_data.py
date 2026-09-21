from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ClimateLog, Greenhouse, IrrigationCycle, Zone
from core.services import create_transplant_event

User = get_user_model()


class Command(BaseCommand):
    help = "初始化演示账号与温室气候/轮灌种子数据"

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@shadecanopy.local",
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("123456")
        admin.role = User.ROLE_ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        self.stdout.write(self.style.SUCCESS(f"admin {'created' if created else 'updated'}"))

        grower, created = User.objects.get_or_create(
            username="grower",
            defaults={
                "email": "grower@shadecanopy.local",
                "role": User.ROLE_GROWER,
            },
        )
        grower.set_password("123456")
        grower.role = User.ROLE_GROWER
        grower.save()
        self.stdout.write(self.style.SUCCESS(f"grower {'created' if created else 'updated'}"))

        if Greenhouse.objects.exists():
            self.stdout.write("温室数据已存在，跳过业务种子写入。")
            return

        g1 = Greenhouse.objects.create(
            name="东坡一号棚",
            location="东区 A 排",
            area_m2=Decimal("1200.00"),
            notes="番茄与叶菜混作示范棚",
        )
        g2 = Greenhouse.objects.create(
            name="西篱二号棚",
            location="西区 B 排",
            area_m2=Decimal("860.50"),
            notes="草莓高架栽培",
        )

        z1 = Zone.objects.create(
            greenhouse=g1, zone_code="A-01", crop_name="黄瓜", status=Zone.STATUS_GROWING
        )
        z2 = Zone.objects.create(
            greenhouse=g1, zone_code="A-02", crop_name="散叶生菜", status=Zone.STATUS_GROWING
        )
        z3 = Zone.objects.create(
            greenhouse=g1, zone_code="A-03", crop_name="", status=Zone.STATUS_IDLE
        )
        z4 = Zone.objects.create(
            greenhouse=g2, zone_code="B-01", crop_name="甜查理草莓", status=Zone.STATUS_GROWING
        )
        z5 = Zone.objects.create(
            greenhouse=g2, zone_code="B-02", crop_name="章姬草莓", status=Zone.STATUS_FALLOW
        )

        now = timezone.now()

        # 移栽换茬种子（走统一服务：同事务回写作物名 + 写气候记录）
        # A-01 的移栽在 30 分钟前，仍处于 ±60 分钟移栽窗口内；
        # A-02 / B-01 的移栽已超出窗口。
        create_transplant_event(
            zone=z1,
            to_crop="樱桃番茄",
            transplanted_at=now - timedelta(minutes=30),
            operator="老周",
            notes="拔园换茬，土壤消毒后定植樱桃番茄",
        )
        create_transplant_event(
            zone=z2,
            to_crop="油麦菜",
            transplanted_at=now - timedelta(days=3),
            operator="李姐",
            notes="生菜清茬后直播油麦菜",
        )
        create_transplant_event(
            zone=z4,
            to_crop="红颜草莓",
            transplanted_at=now - timedelta(hours=26),
            operator="老周",
            notes="高架基质更换品种为红颜",
        )
        ClimateLog.objects.bulk_create(
            [
                ClimateLog(
                    zone=z1,
                    recorded_at=now - timedelta(hours=2),
                    temp_c=Decimal("24.50"),
                    humidity_pct=Decimal("68.00"),
                    par_umol=Decimal("420.00"),
                    co2_ppm=Decimal("650.00"),
                ),
                ClimateLog(
                    zone=z1,
                    recorded_at=now - timedelta(hours=6),
                    temp_c=Decimal("22.10"),
                    humidity_pct=Decimal("72.50"),
                    par_umol=Decimal("180.00"),
                    co2_ppm=Decimal("700.00"),
                ),
                ClimateLog(
                    zone=z2,
                    recorded_at=now - timedelta(hours=3),
                    temp_c=Decimal("23.80"),
                    humidity_pct=Decimal("70.00"),
                    par_umol=Decimal("390.00"),
                    co2_ppm=Decimal("620.00"),
                ),
                ClimateLog(
                    zone=z4,
                    recorded_at=now - timedelta(hours=1),
                    temp_c=Decimal("21.20"),
                    humidity_pct=Decimal("75.00"),
                    par_umol=Decimal("350.00"),
                    co2_ppm=Decimal("580.00"),
                ),
                ClimateLog(
                    zone=z4,
                    recorded_at=now - timedelta(hours=20),
                    temp_c=Decimal("18.60"),
                    humidity_pct=Decimal("80.00"),
                    par_umol=Decimal("50.00"),
                    co2_ppm=Decimal("720.00"),
                ),
            ]
        )

        today = now.replace(hour=9, minute=0, second=0, microsecond=0)
        IrrigationCycle.objects.bulk_create(
            [
                IrrigationCycle(
                    zone=z1,
                    start_at=today + timedelta(hours=1),
                    duration_min=25,
                    water_liters=Decimal("180.00"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
                IrrigationCycle(
                    zone=z2,
                    start_at=today + timedelta(hours=2),
                    duration_min=20,
                    water_liters=Decimal("120.00"),
                    status=IrrigationCycle.STATUS_SCHEDULED,
                ),
                IrrigationCycle(
                    zone=z4,
                    start_at=today - timedelta(hours=3),
                    duration_min=30,
                    water_liters=Decimal("95.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(
                    zone=z1,
                    start_at=today - timedelta(days=1, hours=2),
                    duration_min=25,
                    water_liters=Decimal("175.00"),
                    status=IrrigationCycle.STATUS_DONE,
                ),
                IrrigationCycle(
                    zone=z5,
                    start_at=today + timedelta(hours=4),
                    duration_min=15,
                    water_liters=Decimal("40.00"),
                    status=IrrigationCycle.STATUS_SKIPPED,
                ),
            ]
        )

        from core.models import TransplantEvent

        self.stdout.write(
            self.style.SUCCESS(
                f"种子完成：温室 {Greenhouse.objects.count()}，分区 {Zone.objects.count()}，"
                f"气候 {ClimateLog.objects.count()}，轮灌 {IrrigationCycle.objects.count()}，"
                f"移栽 {TransplantEvent.objects.count()}"
            )
        )
