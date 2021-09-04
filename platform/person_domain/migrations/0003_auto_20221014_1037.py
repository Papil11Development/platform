# Generated by Django 3.2.15 on 2022-10-14 10:37

from django.db import migrations


CHUNK_SIZE = 5000


def copy_person_info(apps, schema_editor):
    Person = apps.get_model('person_domain', 'Person')
    persons = Person.objects.select_related('profile').filter(info__main_sample_id__isnull=True, profile__isnull=False)
    for person in persons.iterator(chunk_size=CHUNK_SIZE):
        person.info = person.profile.info
        person.samples.set(person.profile.samples.all())
        person.save()


def rollback(apps, schema_editor):
    # doesn't make sense
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('person_domain', '0002_auto_20220927_1505'),
    ]

    operations = [
        migrations.RunPython(copy_person_info, rollback),
    ]