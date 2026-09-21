from django.db import transaction
from rest_framework import serializers

from .exceptions import Conflict
from .models import ClimateLog, Greenhouse, IrrigationCycle, TransplantEvent, Zone
from .timewindow import (
    TRANSPLANT_DEFAULT_HUMIDITY,
    TRANSPLANT_DEFAULT_TEMP_C,
    transplant_events_in_window,
)


class GreenhouseSerializer(serializers.ModelSerializer):
    areaM2 = serializers.DecimalField(
        source="area_m2", max_digits=10, decimal_places=2
    )
    zoneCount = serializers.SerializerMethodField()

    class Meta:
        model = Greenhouse
        fields = (
            "id",
            "name",
            "location",
            "areaM2",
            "notes",
            "zoneCount",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "zoneCount", "created_at", "updated_at")

    def get_zoneCount(self, obj):
        if hasattr(obj, "zone_count"):
            return obj.zone_count
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    zoneCode = serializers.CharField(source="zone_code")
    # 作物名只读：只允许通过移栽事件在服务端修改，禁止浏览器端直接改。
    cropName = serializers.CharField(source="crop_name", read_only=True)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)
    lastTransplantAt = serializers.SerializerMethodField()
    inTransplantWindow = serializers.SerializerMethodField()

    class Meta:
        model = Zone
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "zoneCode",
            "cropName",
            "status",
            "lastTransplantAt",
            "inTransplantWindow",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "greenhouseName",
            "lastTransplantAt",
            "inTransplantWindow",
            "created_at",
            "updated_at",
        )

    def get_lastTransplantAt(self, obj):
        # 由视图统一注解（annotate），保证列表/看板口径同源。
        value = getattr(obj, "last_transplant_at", None)
        return value

    def get_inTransplantWindow(self, obj):
        # 由视图统一注解；缺省（未注解、单条）时回退为否。
        return bool(getattr(obj, "in_transplant_window", False))

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        zone_code = attrs.get("zone_code") or getattr(self.instance, "zone_code", None)
        if greenhouse and zone_code:
            qs = Zone.objects.filter(greenhouse=greenhouse, zone_code=zone_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"zoneCode": "同一温室内分区编码必须唯一"}
                )
        return attrs


class ClimateLogSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    recordedAt = serializers.DateTimeField(source="recorded_at")
    tempC = serializers.DecimalField(source="temp_c", max_digits=5, decimal_places=2)
    humidityPct = serializers.DecimalField(
        source="humidity_pct", max_digits=5, decimal_places=2
    )
    parUmol = serializers.DecimalField(
        source="par_umol", max_digits=8, decimal_places=2, required=False
    )
    co2Ppm = serializers.DecimalField(
        source="co2_ppm", max_digits=8, decimal_places=2, required=False
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = ClimateLog
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "recordedAt",
            "tempC",
            "humidityPct",
            "parUmol",
            "co2Ppm",
            "created_at",
        )
        read_only_fields = ("id", "zoneCode", "greenhouseName", "created_at")

    def validate_humidityPct(self, value):
        if value < 20 or value > 100:
            raise serializers.ValidationError("湿度须在 20～100 之间")
        return value


class TransplantEventSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    # 原作物由服务端取分区当前作物名，不接受前端传入，保证同源。
    previousCrop = serializers.CharField(source="previous_crop", read_only=True)
    newCrop = serializers.CharField(source="new_crop", trim_whitespace=False)
    transplantedAt = serializers.DateTimeField(source="transplanted_at")
    operator = serializers.CharField()
    notes = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = TransplantEvent
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "previousCrop",
            "newCrop",
            "transplantedAt",
            "operator",
            "notes",
            "created_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "previousCrop",
            "created_at",
        )

    def validate_newCrop(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("新作物不能为空")
        return value.strip()

    def validate(self, attrs):
        zone = attrs["zone"]
        at = attrs["transplanted_at"]

        if zone.status == Zone.STATUS_FALLOW:
            raise serializers.ValidationError({"zoneId": "休耕分区禁止移栽"})

        # 空闲分区允许移栽，但备注必填。
        notes = attrs.get("notes") or ""
        if zone.status == Zone.STATUS_IDLE and not notes.strip():
            raise serializers.ValidationError({"notes": "空闲分区移栽时备注必填"})

        # 冲突判定（与轮灌拦截共用 transplant_events_in_window）。
        if transplant_events_in_window(zone.id, at).exists():
            raise Conflict("该分区在移栽时刻前后 60 分钟内已有移栽事件")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        zone = Zone.objects.select_for_update().get(pk=validated_data["zone"].pk)
        at = validated_data["transplanted_at"]

        # 行锁内复核，避免并发下两条移栽同时落入同一窗口。
        if zone.status == Zone.STATUS_FALLOW:
            raise serializers.ValidationError({"zoneId": "休耕分区禁止移栽"})
        if transplant_events_in_window(zone.id, at).exists():
            raise Conflict("该分区在移栽时刻前后 60 分钟内已有移栽事件")

        notes = validated_data.get("notes") or ""
        if zone.status == Zone.STATUS_IDLE and not notes.strip():
            raise serializers.ValidationError({"notes": "空闲分区移栽时备注必填"})

        # 1) 写事件（原作物取分区当前作物名）
        event = TransplantEvent.objects.create(
            zone=zone,
            previous_crop=zone.crop_name,
            new_crop=validated_data["new_crop"],
            transplanted_at=at,
            operator=validated_data["operator"],
            notes=notes,
        )

        # 2) 改分区作物名；空闲分区移栽后进入在种，在种仍保持在种。
        zone.crop_name = validated_data["new_crop"]
        if zone.status == Zone.STATUS_IDLE:
            zone.status = Zone.STATUS_GROWING
        zone.save(update_fields=["crop_name", "status", "updated_at"])

        # 3) 同事务写气候记录：采样时刻=移栽时刻，湿度取默认值 70（区间 60～80）。
        ClimateLog.objects.create(
            zone=zone,
            recorded_at=at,
            temp_c=TRANSPLANT_DEFAULT_TEMP_C,
            humidity_pct=TRANSPLANT_DEFAULT_HUMIDITY,
        )

        return event


class IrrigationCycleSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    startAt = serializers.DateTimeField(source="start_at")
    durationMin = serializers.IntegerField(source="duration_min")
    waterLiters = serializers.DecimalField(
        source="water_liters", max_digits=10, decimal_places=2
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = IrrigationCycle
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "startAt",
            "durationMin",
            "waterLiters",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        # 仅拦截“新建”；窗口函数与移栽冲突判定共用。
        if self.instance is None:
            zone = attrs["zone"]
            start_at = attrs["start_at"]
            if transplant_events_in_window(zone.id, start_at).exists():
                raise Conflict("该分区在轮灌开始时刻前后 60 分钟移栽窗口内，禁止新建轮灌")
        return attrs
