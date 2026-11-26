from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import RegistroUsuarioForm, ReservaForm, SubirCVForm
from .models import (
    Competencia, DatosPersonales, DocumentoCV, FuenteDato,
    IndicadorEmpleabilidadONG, OfertaLaboral, Reserva, ServicioCapacitacion, UsuarioCompetencia,
)
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
        ofertas_actuales = OfertaLaboral.objects.filter(es_historica=False)
        totales = (
            ofertas_actuales.count(),
            Competencia.objects.filter(es_catalogo_cv=True).count(),
            get_user_model().objects.count(),
        )
        competencias = list(
            Competencia.objects.filter(ofertas__es_historica=False)
            .annotate(total=Count('ofertas', filter=Q(ofertas__es_historica=False)))
            .filter(total__gt=0)
            .order_by('-total', 'nombre')
            .values('nombre', 'total')[:5]
        )
        regiones = list(
            ofertas_actuales.annotate(nombre=Coalesce(NullIf('region', Value('')), Value('Sin región')))
            .values('nombre').annotate(total=Count('pk')).order_by('-total', 'nombre')
        )
        if len(regiones) > 6:
            regiones = regiones[:5] + [
                {'nombre': 'Otras regiones', 'total': sum(item['total'] for item in regiones[5:])}
            ]

    mtpe_historico = None
    if not demo:
        historicas = OfertaLaboral.objects.filter(es_historica=True)
        if historicas.exists():
            resumen = historicas.aggregate(
                total_avisos=Count('pk'),
                total_vacantes=Sum('vacantes'),
                fecha_inicio=Min('fecha_inicio_periodo'),
                fecha_fin=Max('fecha_fin_periodo'),
            )
            mtpe_historico = {
                'total_avisos': resumen['total_avisos'] or 0,
                'total_vacantes': resumen['total_vacantes'] or 0,
                'fecha_inicio': resumen['fecha_inicio'],
                'fecha_fin': resumen['fecha_fin'],
                'fuente': FuenteDato.objects.filter(ofertas__es_historica=True).order_by('pk').first(),
                'regiones': list(
                    historicas.annotate(nombre=Coalesce(NullIf('region', Value('')), Value('Sin región')))
                    .values('nombre')
                    .annotate(total_vacantes=Sum('vacantes'), total_avisos=Count('pk'))
                    .order_by('-total_vacantes', 'nombre')[:6]
                ),
                'sectores': list(
                    historicas.exclude(sector__isnull=True).exclude(sector='')
                    .values('sector')
                    .annotate(total_vacantes=Sum('vacantes'), total_avisos=Count('pk'))
                    .order_by('-total_vacantes', 'sector')[:5]
                ),
                'ocupaciones': list(
                    historicas.exclude(ocupacion__isnull=True).exclude(ocupacion='')
                    .values('ocupacion')
                    .annotate(total_vacantes=Sum('vacantes'), total_avisos=Count('pk'))
                    .order_by('-total_vacantes', 'ocupacion')[:5]
                ),
                'competencias': list(
                    Competencia.objects.filter(ofertas__es_historica=True)
                    .annotate(total=Count('ofertas', filter=Q(ofertas__es_historica=True)))
                    .filter(total__gt=0)
                    .order_by('-total', 'nombre')
                    .values('nombre', 'total')[:5]
                ),
            }

    ong_indicadores = None
    if not demo:
        indicadores_qs = (
            IndicadorEmpleabilidadONG.objects.select_related('fuente')
            .prefetch_related('competencias')
            .order_by('-anio', 'categoria', '-valor_numerico', 'titulo')
        )
        if indicadores_qs.exists():
            lista_ong = list(indicadores_qs)
            ong_indicadores = {
                'fuente': lista_ong[0].fuente,
                'anio': lista_ong[0].anio,
                'url_documento': lista_ong[0].url_documento,
                'indicadores': lista_ong,
            }

    estadisticas = [
        {'titulo': titulo, 'icono': icono, 'total': total}
        for (titulo, icono), total in zip([
            ('Ofertas laborales vigentes', 'fa-solid fa-briefcase'),
            ('Competencias del catálogo CV', 'fa-solid fa-list-check'),
            ('Usuarios registrados', 'fa-solid fa-users'),
        ], totales)
    ]
    return render(request, 'core/dashboard.html', {
        'demo': demo, 'estadisticas': estadisticas, 'competencias': competencias, 'regiones': regiones,
        'incluye_arbeitnow': not demo and OfertaLaboral.objects.filter(es_historica=False, fuente__nombre='Arbeitnow').exists(),
        'mtpe_historico': mtpe_historico,
        'ong_indicadores': ong_indicadores,
    })


SERVICIOS_DEMO = [
    {'nombre': 'Excel para el trabajo', 'descripcion': 'Practica fórmulas, filtros y tablas dinámicas con ejercicios de oficina.', 'precio': 35, 'capacidad_maxima': 25},
    {'nombre': 'Introducción a Python', 'descripcion': 'Escribe tus primeros programas y automatiza tareas sencillas.', 'precio': 50, 'capacidad_maxima': 20},
    {'nombre': 'Asesoría de CV', 'descripcion': 'Identifica mejoras para presentar tu experiencia y tus competencias.', 'precio': 25, 'capacidad_maxima': 8},
]


def registro_view(request):
    """Permite registrar un usuario estándar de EmpleoPredict e iniciar sesión."""
    if request.user.is_authenticated:
        return redirect('inicio')

    siguiente = request.GET.get('next') or request.POST.get('next') or ''
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            messages.success(request, f'Cuenta creada correctamente. ¡Bienvenido, {usuario.username}!')
            if siguiente and url_has_allowed_host_and_scheme(
                siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(siguiente)
            return redirect('inicio')
        messages.error(request, 'Revisa los datos ingresados para completar tu registro.')
    else:
        form = RegistroUsuarioForm()

    return render(request, 'core/registro.html', {'form': form, 'next': siguiente})


def servicios_view(request):
    consulta = request.GET.get('q', '').strip()
    hay_servicios_reales = ServicioCapacitacion.objects.exists()
    demo = not hay_servicios_reales

    if hay_servicios_reales:
        queryset = ServicioCapacitacion.objects.order_by('nombre', 'pk')
        if consulta:
            queryset = queryset.filter(Q(nombre__icontains=consulta) | Q(descripcion__icontains=consulta))
        servicios = list(queryset)
    else:
        servicios = SERVICIOS_DEMO
        if consulta:
            termino = consulta.casefold()
            servicios = [
                s for s in SERVICIOS_DEMO
                if termino in s['nombre'].casefold() or termino in s['descripcion'].casefold()
            ]

    return render(request, 'core/servicios.html', {
        'servicios': servicios,
        'demo': demo,
        'consulta': consulta,
    })


@login_required
def reservar_servicio_view(request, servicio_id):
    """Registra una reserva para un servicio real asociada al usuario autenticado."""
    servicio = get_object_or_404(ServicioCapacitacion, pk=servicio_id)

    if request.method == 'POST':
        with transaction.atomic():
            servicio_actual = ServicioCapacitacion.objects.select_for_update().get(pk=servicio.pk)
            form = ReservaForm(request.POST, usuario=request.user, servicio=servicio_actual)
            if form.is_valid():
                reserva = form.save(commit=False)
                reserva.usuario = request.user
                reserva.servicio = servicio_actual
                reserva.estado = 'Pendiente'
                reserva.save()
                messages.success(
                    request,
                    f'Reserva registrada para "{servicio_actual.nombre}" en estado Pendiente.',
                )
                return redirect('mis_reservas')
        messages.error(request, 'No se pudo completar la reserva. Revisa los mensajes de validación.')
    else:
        form = ReservaForm(usuario=request.user, servicio=servicio)

    return render(request, 'core/reservar_servicio.html', {
        'servicio': servicio,
        'form': form,
    })


@login_required
def mis_reservas_view(request):
    """Lista únicamente las reservas del usuario autenticado."""
    reservas = (
        Reserva.objects.filter(usuario=request.user)
        .select_related('servicio')
        .order_by('-fecha_reserva', '-fecha_creacion')
    )
    return render(request, 'core/mis_reservas.html', {'reservas': reservas})
