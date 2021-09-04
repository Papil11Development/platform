from django.db import models
from django.contrib.auth.models import User
from uuid import uuid4


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)

    title = models.CharField(max_length=100, default='', help_text="Workspace title")
    config = models.JSONField(default=dict, db_index=True,
                              help_text="Workspace configuration. Include types of workspace")

    @property
    def plan_name(self) -> str:
        return {
            '0': 'Trial',
            '1': 'Cloud',
            '2': 'Trial',
            '3': 'Cloud'
        }.get(str(self.config.get('plan_id')), '')

    class Meta:
        db_table = 'user_domain_workspace'
        verbose_name_plural = 'Workspaces'


class Access(models.Model):
    ADMIN = 'AD'
    EDITOR = 'ED'
    VIEWER = 'VI'
    OWNER = 'OW'
    USER_PERMISSIONS = [
        (ADMIN, 'Administrator'),
        (VIEWER, 'Viewer'),
        (EDITOR, 'Editor'),
        (OWNER, 'Owner')
    ]

    id = models.UUIDField(primary_key=True, unique=True, default=uuid4, editable=False)

    user = models.ForeignKey(User, related_name='accesses', on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, related_name="accesses", on_delete=models.CASCADE, blank=True, null=True)

    permissions = models.CharField(max_length=2, choices=USER_PERMISSIONS, default=VIEWER)

    class Meta:
        db_table = 'user_domain_access'
        verbose_name_plural = 'Accesses'
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'permissions'], condition=models.Q(permissions='OW'),
                                    name='unique owner')
        ]


class EmailTemplate(models.Model):
    template_key = models.CharField(max_length=255, unique=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    body = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"<{self.template_key}> {self.subject}"

    class Meta:
        db_table = 'user_domain_email_template'
        verbose_name_plural = 'EmailTemplates'
