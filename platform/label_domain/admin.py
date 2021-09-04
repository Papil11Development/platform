from django.contrib import admin
from label_domain.models import Label


class LabelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super(LabelAdmin, self).save_model(request, obj, form, change)


admin.site.register(Label, LabelAdmin)
