from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro_view, name='registro'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('subir-cv/', views.subir_cv_view, name='subir_cv'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('servicios/', views.servicios_view, name='servicios'),
]
