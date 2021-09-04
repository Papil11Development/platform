from django.contrib import admin
from person_domain.models import Person, Profile, ProfileGroup


class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'person')
    list_display_links = list_display


class PersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'profile')
    list_display_links = list_display


admin.site.register(ProfileGroup)
admin.site.register(Person, PersonAdmin)
admin.site.register(Profile, ProfileAdmin)
