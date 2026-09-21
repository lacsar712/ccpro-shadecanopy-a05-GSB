# Hand-authored migration for transplant (crop change) events.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransplantEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_crop", models.CharField(blank=True, default="", max_length=120)),
                ("new_crop", models.CharField(max_length=120)),
                ("transplanted_at", models.DateTimeField()),
                ("operator", models.CharField(max_length=120)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("zone", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transplant_events", to="core.zone")),
            ],
            options={
                "ordering": ["-transplanted_at"],
            },
        ),
        migrations.AddIndex(
            model_name="transplantevent",
            index=models.Index(fields=["zone", "transplanted_at"], name="tx_zone_time_idx"),
        ),
    ]
