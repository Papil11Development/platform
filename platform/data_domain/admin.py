from django.contrib import admin
from .models import Activity, Sample, BlobMeta


class ActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'person', 'creation_date')
    list_display_links = list_display


admin.site.register(Activity, ActivityAdmin)
admin.site.register(Sample)
admin.site.register(BlobMeta)
