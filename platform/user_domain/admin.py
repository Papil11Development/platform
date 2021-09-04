from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.utils.safestring import mark_safe


from user_domain.managers import WorkspaceManager
from .models import Workspace, Access, EmailTemplate
from user_domain.licensing_api import LicensingOperation


class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('workspace_count', 'workspace_list')
    actions = ['create_workspace', 'delete_user_workspaces', 'create_billing_account', 'move_user_to_qa']

    @admin.action(description='Create billing account')
    def create_billing_account(self, request, queryset):
        with transaction.atomic():
            for user in queryset:
                LicensingOperation.create_billing_account(user.username)

    @admin.action(description='Create Workspace')
    def create_workspace(self, request, queryset):
        from notification_domain.managers import EndpointManager  # noqa

        with transaction.atomic():
            for user in queryset:
                workspace = WorkspaceManager.create_workspace(title=str(user.username) + "'s Workspace",
                                                              username=user.username)
                if user.groups.filter(name__iexact=settings.STANDALONE_GROUP).exists():
                    LicensingOperation.create_workspace_license(str(workspace.id), user.username)
                EndpointManager(workspace_id=workspace.id).create_default_endpoints(owner_email=user.email)
                Access.objects.create(user=user, workspace=workspace, permissions=Access.OWNER)

    @admin.action(description='Move user licenses to qa mode')
    def move_user_to_qa(self, request, queryset):

        qa_group, _ = Group.objects.get_or_create(name=settings.QA_GROUP)

        for user in queryset:
            if not user.groups.filter(name__iexact=settings.STANDALONE_GROUP).exists():
                with transaction.atomic():
                    user.groups.add(qa_group)
                    user.save()
                continue

            with transaction.atomic():
                # drop user licenses and add them to qa group
                user.billing_account.delete()
                user.groups.add(qa_group)
                user.save()
                LicensingOperation.create_billing_account(username=user)

            with transaction.atomic():
                # create autonomous license
                LicensingOperation.create_image_api_license(user.username)

                # create workspace license for each user workspace
                for access in user.accesses.filter(permissions=Access.OWNER):
                    LicensingOperation.create_workspace_license(str(access.workspace_id), user.username)

    @admin.action(description='Delete user workspaces')
    def delete_user_workspaces(self, request, queryset):
        with transaction.atomic():
            for user in queryset:
                for access in user.accesses.all():
                    workspace = access.workspace

                    for agent in workspace.agents.all():
                        agent.activations.all().delete()

                    # For proper workspace blobs deletion
                    workspace.blobmeta.all().delete()

                    workspace.delete()

    def workspace_count(self, obj):
        accesses = obj.accesses.all()
        count = 0
        if accesses:
            for access in accesses:
                count = count + 1 if access.workspace else count + 0
        return count

    def workspace_list(self, obj):
        accesses = obj.accesses.all()
        workspace_links = []
        if accesses:
            for access in accesses:
                if access.workspace:
                    workspace_links.append('<a href="/storage/admin/user_domain/workspace/{0}/change/">{1}</a>'
                                           .format(access.workspace.id, str(access.workspace)))
        return mark_safe('<br>'.join(workspace_links))


class EmailTemplateAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('template_key',)
        return self.readonly_fields


admin.site.unregister(User)

admin.site.register(Workspace)
admin.site.register(User, CustomUserAdmin)
admin.site.register(Access)
admin.site.register(EmailTemplate, EmailTemplateAdmin)
