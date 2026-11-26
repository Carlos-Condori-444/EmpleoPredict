from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginUsuarioForm

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('subir-cv/', views.subir_cv_view, name='subir_cv'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('servicios/', views.servicios_view, name='servicios'),
    path('servicios/<int:servicio_id>/reservar/', views.reservar_servicio_view, name='reservar_servicio'),
    path('mis-reservas/', views.mis_reservas_view, name='mis_reservas'),
    path(
        'cuentas/login/',
        auth_views.LoginView.as_view(
            template_name='core/login.html',
            authentication_form=LoginUsuarioForm,
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('cuentas/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cuentas/registro/', views.registro_view, name='registro'),
]
