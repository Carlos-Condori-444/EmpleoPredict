from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('subir-cv/', views.subir_cv_view, name='subir_cv'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('servicios/', views.servicios_view, name='servicios'),
]
