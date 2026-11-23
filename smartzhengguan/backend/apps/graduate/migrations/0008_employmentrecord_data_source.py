from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('graduate', '0007_student_gender_source')]
    operations = [migrations.AddField(model_name='employmentrecord', name='data_source', field=models.CharField(max_length=40, blank=True))]
