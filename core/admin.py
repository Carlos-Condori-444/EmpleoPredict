from django.contrib import admin
from .models import (
    DatosPersonales, PerfilProfesional, ExperienciaLaboral, FormacionAcademica,
    Competencia, UsuarioCompetencia, DocumentoCV,
    FuenteDato, OfertaLaboral,
    ServicioCapacitacion, Reserva
)

# ==========================================
# CONFIGURACIÓN DEL ADMIN PARA PERFIL
# ==========================================

@admin.register(DatosPersonales)
class DatosPersonalesAdmin(admin.ModelAdmin):
    list_display = ('nombres', 'apellidos', 'usuario', 'telefono', 'ciudad')
    search_fields = ('nombres', 'apellidos', 'usuario__username')

@admin.register(PerfilProfesional)
class PerfilProfesionalAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'titulo_profesional', 'area_profesional', 'anios_experiencia')
    search_fields = ('usuario__username', 'titulo_profesional')

@admin.register(ExperienciaLaboral)
class ExperienciaLaboralAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'cargo', 'empresa', 'fecha_inicio', 'trabajo_actual')
    list_filter = ('trabajo_actual', 'fecha_inicio')
    search_fields = ('cargo', 'empresa', 'usuario__username')

@admin.register(FormacionAcademica)
class FormacionAcademicaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'carrera', 'institucion', 'nivel_academico')
    search_fields = ('carrera', 'institucion', 'usuario__username')

# ==========================================
# CONFIGURACIÓN DEL ADMIN PARA COMPETENCIAS Y CV
# ==========================================

@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'categoria')
    list_filter = ('tipo', 'categoria')
    search_fields = ('nombre',)

@admin.register(UsuarioCompetencia)
class UsuarioCompetenciaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'competencia', 'nivel', 'anios_experiencia')
    list_filter = ('nivel', 'competencia__tipo')
    search_fields = ('usuario__username', 'competencia__nombre')

@admin.register(DocumentoCV)
class DocumentoCVAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nombre_archivo', 'estado_procesamiento', 'fecha_subida', 'version')
    list_filter = ('estado_procesamiento', 'fecha_subida')
    search_fields = ('usuario__username', 'nombre_archivo')
    readonly_fields = ('fecha_subida',)

# ==========================================
# CONFIGURACIÓN DEL ADMIN PARA EXTRACCIÓN (OFERTAS)
# ==========================================

@admin.register(FuenteDato)
class FuenteDatoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'url_base', 'ultima_ejecucion')
    list_filter = ('tipo',)

@admin.register(OfertaLaboral)
class OfertaLaboralAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'empresa', 'region', 'sector', 'fuente', 'fecha_extraccion')
    list_filter = ('region', 'sector', 'fuente')
    search_fields = ('titulo', 'empresa', 'descripcion')
    filter_horizontal = ('competencias',) # Interfaz visual para seleccionar competencias
    readonly_fields = ('fecha_extraccion',)

# ==========================================
# CONFIGURACIÓN DEL ADMIN PARA RESERVAS
# ==========================================

@admin.register(ServicioCapacitacion)
class ServicioCapacitacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'capacidad_maxima', 'precio')
    search_fields = ('nombre',)

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'servicio', 'fecha_reserva', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'fecha_reserva')
    search_fields = ('usuario__username', 'servicio__nombre')
    readonly_fields = ('fecha_creacion',)