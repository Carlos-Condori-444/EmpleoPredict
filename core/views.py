from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Value
from django.db.models.functions import Coalesce, NullIf

from .forms import SubirCVForm
from .models import Competencia, DatosPersonales, DocumentoCV, OfertaLaboral, ServicioCapacitacion, UsuarioCompetencia
from .utils import procesar_cv

def inicio(request):
    """Página de inicio del proyecto EmpleoPredict."""
    return render(request, 'core/inicio.html')

@login_required
def subir_cv_view(request):
    """
    Vista protegida donde el usuario autenticado sube su CV (PDF).
    El sistema extrae el texto, busca competencias y completa su perfil.
    """
    documentos_previos = DocumentoCV.objects.filter(usuario=request.user).order_by('-fecha_subida')
    competencias_usuario = UsuarioCompetencia.objects.filter(usuario=request.user).select_related('competencia')
    datos_personales, _ = DatosPersonales.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        form = SubirCVForm(request.POST, request.FILES)
        if form.is_valid():
            nuevo_cv = form.save(commit=False)
            nuevo_cv.usuario = request.user
            nuevo_cv.nombre_archivo = request.FILES['archivo'].name
            nuevo_cv.estado_procesamiento = 'PENDIENTE'

            # Control de versiones del CV subido
            if documentos_previos.exists():
                nuevo_cv.version = documentos_previos.first().version + 1
            else:
                nuevo_cv.version = 1

            nuevo_cv.save()

            # Disparar la lógica de extracción de texto y detección de competencias
            exito, mensaje = procesar_cv(nuevo_cv)

            if exito:
                messages.success(request, mensaje)
            else:
                messages.error(request, mensaje)

            return redirect('subir_cv')
    else:
        form = SubirCVForm()

    context = {
        'form': form,
        'documentos': documentos_previos,
        'competencias': competencias_usuario,
        'datos_personales': datos_personales,
    }
    return render(request, 'core/subir_cv.html', context)


def dashboard_view(request):
    demo = request.GET.get('demo') == '1'
    if demo:
        totales = (120, 36, 82)
        competencias = [
            {'nombre': nombre, 'total': total}
            for nombre, total in [('Excel', 41), ('Python', 31), ('SQL', 25), ('Inglés', 18), ('Git', 11)]
        ]
        regiones = [
            {'nombre': nombre, 'total': total}
            for nombre, total in [('Lima', 60), ('Arequipa', 27), ('Cusco', 19), ('La Libertad', 14)]
        ]
    else:
        totales = (OfertaLaboral.objects.count(), Competencia.objects.count(), get_user_model().objects.count())
        competencias = list(
            Competencia.objects.annotate(total=Count('ofertas'))
            .filter(total__gt=0).order_by('-total', 'nombre').values('nombre', 'total')[:5]
        )
        regiones = list(
            OfertaLaboral.objects.annotate(nombre=Coalesce(NullIf('region', Value('')), Value('Sin región')))
            .values('nombre').annotate(total=Count('pk')).order_by('-total', 'nombre')
        )
        if len(regiones) > 6:
            regiones = regiones[:5] + [
                {'nombre': 'Otras regiones', 'total': sum(item['total'] for item in regiones[5:])}
            ]

    estadisticas = [
        {'titulo': titulo, 'icono': icono, 'total': total}
        for (titulo, icono), total in zip([
            ('Ofertas laborales extraídas', 'fa-solid fa-briefcase'),
            ('Competencias registradas', 'fa-solid fa-list-check'),
            ('Usuarios registrados', 'fa-solid fa-users'),
        ], totales)
    ]
    return render(request, 'core/dashboard.html', {
        'demo': demo, 'estadisticas': estadisticas, 'competencias': competencias, 'regiones': regiones,
        'incluye_arbeitnow': not demo and OfertaLaboral.objects.filter(fuente__nombre='Arbeitnow').exists(),
    })


def servicios_view(request):
    servicios = list(ServicioCapacitacion.objects.order_by('nombre', 'pk'))
    demo = not servicios
    if demo:
        servicios = [
            {'nombre': 'Excel para el trabajo', 'descripcion': 'Practica fórmulas, filtros y tablas dinámicas con ejercicios de oficina.', 'precio': 35, 'capacidad_maxima': 25},
            {'nombre': 'Introducción a Python', 'descripcion': 'Escribe tus primeros programas y automatiza tareas sencillas.', 'precio': 50, 'capacidad_maxima': 20},
            {'nombre': 'Asesoría de CV', 'descripcion': 'Identifica mejoras para presentar tu experiencia y tus competencias.', 'precio': 25, 'capacidad_maxima': 8},
        ]
    return render(request, 'core/servicios.html', {'servicios': servicios, 'demo': demo})
