from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('graduate', '0008_employmentrecord_data_source')]
    operations = [migrations.AlterField(model_name='student',name='current_status',field=models.CharField(max_length=32,default='active',choices=[('active','Active'),('graduated','Graduated'),('suspended','Suspended'),('withdrawn','Withdrawn'),('extended','Extended Graduation'),('other','Other')]))]
