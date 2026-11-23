from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('graduate', '0006_warningrule_warningruleversion_warninginstance_and_more')]
    operations = [
        migrations.AddField(model_name='student', name='gender_source', field=models.CharField(max_length=40, blank=True)),
        migrations.AlterField(model_name='student', name='gender', field=models.CharField(max_length=20, choices=[('男', '男'), ('女', '女')])),
    ]
