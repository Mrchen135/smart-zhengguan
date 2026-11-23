from django.db import migrations,models
class Migration(migrations.Migration):
    dependencies=[('graduate','0009_student_graduated_status')]
    operations=[
        migrations.AddField(model_name='student',name='profile_source',field=models.CharField(max_length=40,blank=True)),
        migrations.AddField(model_name='student',name='enrolled_on',field=models.DateField(null=True,blank=True)),
        migrations.AddField(model_name='student',name='graduated_on',field=models.DateField(null=True,blank=True)),
        migrations.AddField(model_name='student',name='required_credits',field=models.PositiveSmallIntegerField(default=0)),
    ]+[migrations.AddField(model_name=name,name='data_source',field=models.CharField(max_length=40,blank=True)) for name in ['trainingplan','degreeapplication','scholarshipaward','predictionsnapshot']]
