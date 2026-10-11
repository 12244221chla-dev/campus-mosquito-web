from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mosquito", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="hazardreport",
            name="photo",
            field=models.ImageField(blank=True, upload_to="reports/%Y/%m/", verbose_name="现场照片"),
        ),
    ]
