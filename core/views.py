from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import SubirCVForm
from .models import DocumentoCV, DatosPersonales, UsuarioCompetencia
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
