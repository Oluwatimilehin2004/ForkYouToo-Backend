from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')  
    bio = models.CharField(max_length=500)
    profile_pic = models.ImageField(upload_to='profiles/', blank=True, null=True)

    # Add this field for GitHub token
    github_token = models.CharField(max_length=500, blank=True, null=True)
    github_username = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.user.username


# models.py
from django.contrib.auth.models import User

class ImportHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # ✅ User, NOT UserProfile
    original_owner = models.CharField(max_length=255)
    original_repo = models.CharField(max_length=255)
    imported_repo_name = models.CharField(max_length=255)
    imported_repo_url = models.URLField()
    customizations_applied = models.JSONField(default=list)
    status = models.CharField(max_length=50, default='success')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} imported {self.original_owner}/{self.original_repo}"