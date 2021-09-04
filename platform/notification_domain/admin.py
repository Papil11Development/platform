from django.contrib import admin
from notification_domain.models import Trigger, Endpoint, Notification


class TriggerAdmin(admin.ModelAdmin):
    list_display = ('id', 'workspace')
    list_display_links = list_display


admin.site.register(Trigger, TriggerAdmin)
admin.site.register(Endpoint)
admin.site.register(Notification)
