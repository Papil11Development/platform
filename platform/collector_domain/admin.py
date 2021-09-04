from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist

from licensing.common_managers import LicensingCommonEvent
from .models import Agent, Camera, AttentionArea, AreaType, Location, AgentIndexEvent


class CameraAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        if not change:
            try:
                lic_e_man = LicensingCommonEvent(workspace_id=str(obj.workspace_id))
                lic_e_man.create_cameras(Camera.objects.filter(workspace=obj.workspace).count())
            except ObjectDoesNotExist:  # for user from cognitive
                pass

        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        try:
            lic_e_man = LicensingCommonEvent(workspace_id=str(obj.workspace_id))
            lic_e_man.delete_cameras()
        except ObjectDoesNotExist:  # for user from cognitive
            pass
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            try:
                lic_e_man = LicensingCommonEvent(workspace_id=str(obj.workspace_id))
                lic_e_man.delete_cameras()
            except ObjectDoesNotExist:  # for user from cognitive
                pass

        super().delete_queryset(request, queryset)


class AgentIndexEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'creation_date', 'profile_id')
    ordering = ('-creation_date',)
    list_display_links = list_display


admin.site.register(Agent)
admin.site.register(Camera, CameraAdmin)
admin.site.register(AttentionArea)
admin.site.register(AreaType)
admin.site.register(Location)
admin.site.register(AgentIndexEvent, AgentIndexEventAdmin)
