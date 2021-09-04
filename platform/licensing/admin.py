from django.contrib import admin
from django.db import models
from django_json_widget.widgets import JSONEditorWidget

from licensing.models import Product, BillingAccount, License, WebhookLog
from platform_lib.utils import django_admin_inline_link


class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    list_display_links = list_display
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget}
    }


class ClientAdmin(admin.ModelAdmin):
    list_display = ('username',)
    list_display_links = list_display


class LicenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'workspace_')
    list_display_links = ('id',)
    readonly_fields = ('username',)
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget}
    }

    @admin.display(description='Billing Account')
    def username(self, obj):
        return django_admin_inline_link(app_name='licensing', model_name='billingaccount', action='change',
                                        link_text=obj.billing_account.username, args=(obj.billing_account.pk,))

    @admin.display(description='Workspace')
    def workspace_(self, obj):
        return django_admin_inline_link(app_name='user_domain',
                                        model_name='workspace',
                                        action='change',
                                        link_text=obj.workspace.title if obj.workspace else "-",
                                        args=(obj.workspace.pk if obj.workspace else "-",))


class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'source', 'request_id', 'creation_date')
    list_display_links = list_display
    readonly_fields = ('creation_date',)
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget}
    }


admin.site.register(Product, ProductAdmin)
admin.site.register(BillingAccount, ClientAdmin)
admin.site.register(License, LicenseAdmin)
admin.site.register(WebhookLog, WebhookLogAdmin)
