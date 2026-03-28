from django.urls import path
from . import views

urlpatterns= [
    path('register/', views.register_user, name="register_user"),
    path('login/', views.login_user, name='login'),
    path('alu-repos/', views.alu_repos, name="alu_repos"),
    path('import/', views.import_repository, name='import_repo'),
    path('imports/', views.my_imports, name='my_imports'),
    path('import/<int:import_id>/status/', views.import_status, name='import_status'),
    path('connect-github/', views.connect_github, name="connect-github")
]