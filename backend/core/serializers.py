from rest_framework import serializers

from .models import ClimateLog, Greenhouse, IrrigationCycle, TransplantEvent, Zone
from .services import TransplantConflict, is_inside_transplant_window


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
    # cropName 只读：作物名只能由移栽换茬事件（服务端事务）修改，
    # 浏览器端直接 PATCH/PUT 作物名不会生效。
    cropName = serializers.CharField(source="crop_name", read_only=True)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)
    lastTransplantAt = serializers.DateTimeField(
        source="last_transplant_at", read_only=True
    )
    inTransplantWindow = serializers.BooleanField(
        source="in_transplant_window", read_only=True
    )

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
            "cropName",
            "lastTransplantAt",
            "inTransplantWindow",
            "created_at",
            "updated_at",
        )

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
        # 仅拦截“新建轮灌”；编辑既有轮灌不受此限
        if self.instance is None:
            zone = attrs.get("zone")
            start_at = attrs.get("start_at")
            if zone and start_at and is_inside_transplant_window(zone.pk, start_at):
                raise TransplantConflict(
                    "该分区在起灌时刻前后 60 分钟内处于移栽窗口，禁止新建轮灌"
                )
        return attrs


class TransplantEventSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    fromCrop = serializers.CharField(source="from_crop", read_only=True)
    toCrop = serializers.CharField(source="to_crop")
    transplantedAt = serializers.DateTimeField(source="transplanted_at")
    operator = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
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
            "fromCrop",
            "toCrop",
            "transplantedAt",
            "operator",
            "notes",
            "created_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "fromCrop",
            "created_at",
        )

    def validate_toCrop(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("新作物不能为空")
        return value.strip()

    def validate_operator(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("操作人不能为空")
        return value.strip()

    def validate(self, attrs):
        zone = attrs.get("zone")
        notes = (attrs.get("notes") or "").strip()
        if zone and zone.status == Zone.STATUS_FALLOW:
            raise serializers.ValidationError({"zoneId": "休耕分区禁止移栽"})
        if zone and zone.status == Zone.STATUS_IDLE and not notes:
            raise serializers.ValidationError({"notes": "空闲分区移栽时备注必填"})
        attrs["notes"] = notes
        return attrs
