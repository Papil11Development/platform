import uuid

from django.apps import apps
from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import pre_delete, post_delete, post_save

from licensing.common_managers import LicensingCommonEvent
from platform_lib.exceptions import LicenseNotExist
from user_domain.models import Workspace
from label_domain.models import Label


class Person(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, related_name='persons', on_delete=models.CASCADE, null=False)
    samples = models.ManyToManyField(to='data_domain.Sample', related_name="persons", blank=True)
    info = models.JSONField(default=dict, help_text="Person's info")

    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'person_domain_person'
        verbose_name_plural = 'Persons'


class Profile(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    info = models.JSONField(default=dict, help_text="Profile's info")

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='profiles', null=False)
    person = models.OneToOneField(Person, related_name='profile', blank=True, null=True, on_delete=models.CASCADE)
    samples = models.ManyToManyField(to='data_domain.Sample', related_name="profile", blank=True)
    profile_groups = models.ManyToManyField(Label, related_name="profiles", through="ProfileGroup")

    last_modified = models.DateTimeField(auto_now=True, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'person_domain_profile'
        verbose_name_plural = 'Profiles'


class ProfileGroup(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, related_name='link_to_label', on_delete=models.CASCADE)
    label = models.ForeignKey(Label, related_name='link_to_profile', on_delete=models.CASCADE)

    class Meta:
        unique_together = ("profile", "label")


@receiver(pre_delete, sender=Profile)
def pre_delete_profile(sender, instance, *args, **kwargs):
    notification = apps.get_model('notification_domain', 'Notification')
    with transaction.atomic():
        if instance.samples:
            for sample in instance.samples.all():
                print(f"Was deleted {sample} related with {instance}")
                sample.delete()

        notification.objects.select_for_update().filter(workspace=instance.workspace,
                                                        meta__profile_id=str(instance.id)).delete()


@receiver(post_save, sender=Profile)
def post_save_profile(sender, instance, created, *args, **kwargs):
    if not created:
        return

    lic_e_man = LicensingCommonEvent(workspace_id=str(instance.workspace_id))
    # For users licensed through lk
    try:
        lic_e_man.create_persons(sender.objects.count())
    except LicenseNotExist:
        return


@receiver(post_delete, sender=Profile)
def post_delete_profile(sender, instance, *args, **kwargs):
    lic_e_man = LicensingCommonEvent(workspace_id=str(instance.workspace_id))
    # For users licensed through lk
    try:
        lic_e_man.delete_persons()
    except LicenseNotExist:
        return
