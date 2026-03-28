from django.contrib import admin
from .models import UserProfile, ImportHistory

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(ImportHistory)