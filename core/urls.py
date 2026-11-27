from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro_view, name='registro'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('subir-cv/', views.subir_cv_view, name='subir_cv'),
    path('subir-cv/<int:pk>/editar/', views.editar_cv_view, name='editar_cv'),
    path('subir-cv/<int:pk>/reprocesar/', views.reprocesar_cv_view, name='reprocesar_cv'),
    path('subir-cv/<int:pk>/eliminar/', views.eliminar_cv_view, name='eliminar_cv'),
    path('perfil/', views.perfil_view, name='perfil'),
    path('perfil/experiencia/<int:pk>/editar/', views.editar_experiencia_view, name='editar_experiencia'),
    path('perfil/experiencia/<int:pk>/eliminar/', views.eliminar_experiencia_view, name='eliminar_experiencia'),
    path('perfil/formacion/<int:pk>/editar/', views.editar_formacion_view, name='editar_formacion'),
    path('perfil/formacion/<int:pk>/eliminar/', views.eliminar_formacion_view, name='eliminar_formacion'),
    path('perfil/competencia/<int:pk>/editar/', views.editar_competencia_view, name='editar_competencia'),
    path('perfil/competencia/<int:pk>/eliminar/', views.eliminar_competencia_view, name='eliminar_competencia'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('servicios/', views.servicios_view, name='servicios'),
]
