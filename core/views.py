from datetime import timedelta

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
from django.views.decorators.http import require_POST

from .scraper import obtener_terminos_busqueda_usuario, recomendar_ofertas_para_usuario

from .forms import (
    DatosPersonalesForm,
    DocumentoCVEditarForm,
    ExperienciaLaboralForm,
    FormacionAcademicaForm,
    LoginForm,
    PerfilProfesionalForm,
    RegistroForm,
    SubirCVForm,
    UsuarioCompetenciaEditarForm,
    UsuarioCompetenciaForm,
)
from .models import (
    Competencia,
    DatosPersonales,
    DocumentoCV,
    ExperienciaLaboral,
    FormacionAcademica,
    OfertaLaboral,
    PerfilProfesional,
    Reserva,
    ServicioCapacitacion,
    UsuarioCompetencia,
)
from .utils import procesar_cv

def inicio(request):
    """Página de inicio del proyecto EmpleoPredict."""
    return render(request, 'core/inicio.html')


login_view = LoginView.as_view(
    template_name='core/login.html',
    authentication_form=LoginForm,
    redirect_authenticated_user=True,
)


def registro_view(request):
    if request.user.is_authenticated:
        return redirect('subir_cv')

    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Cuenta creada correctamente. Ya puedes subir tu CV.')
            return redirect('subir_cv')
    else:
        form = RegistroForm()

    return render(request, 'core/registro.html', {'form': form})

def _obtener_datos_basicos_faltantes(datos_personales, perfil_profesional=None):
    faltantes = []
    nombres = (datos_personales.nombres or '').strip()
    apellidos = (datos_personales.apellidos or '').strip()
    if not nombres or nombres.lower() == 'nuevo':
        faltantes.append('Nombres')
    if not apellidos or apellidos.lower() == 'usuario':
        faltantes.append('Apellidos')
    if not datos_personales.email_contacto:
        faltantes.append('Correo de contacto')
    if not datos_personales.telefono:
        faltantes.append('Teléfono')
    if not datos_personales.pais and not datos_personales.ciudad:
        faltantes.append('Ubicación (país/ciudad)')
    if perfil_profesional and not (perfil_profesional.titulo_profesional or '').strip():
        faltantes.append('Título profesional')
    return faltantes


@login_required
def subir_cv_view(request):
    """
    Vista protegida donde el usuario autenticado sube su CV (PDF).
    El sistema extrae el texto, busca competencias y completa su perfil.
    """
    documentos_previos = DocumentoCV.objects.filter(usuario=request.user).order_by('-fecha_subida')
    competencias_usuario = UsuarioCompetencia.objects.filter(usuario=request.user).select_related('competencia')
    datos_personales, _ = DatosPersonales.objects.get_or_create(usuario=request.user)
    perfil_profesional, _ = PerfilProfesional.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        form = SubirCVForm(request.POST, request.FILES)
        if form.is_valid():
            nuevo_cv = form.save(commit=False)
            nuevo_cv.usuario = request.user
            nuevo_cv.nombre_archivo = request.FILES['archivo'].name
            nuevo_cv.estado_procesamiento = 'PENDIENTE'

            if documentos_previos.exists():
                nuevo_cv.version = documentos_previos.first().version + 1
            else:
                nuevo_cv.version = 1

            nuevo_cv.save()

            exito, mensaje = procesar_cv(nuevo_cv)

            if exito:
                messages.success(request, mensaje)
                datos_personales.refresh_from_db()
                faltantes = _obtener_datos_basicos_faltantes(datos_personales, perfil_profesional)
                if faltantes:
                    messages.warning(
                        request,
                        f'Falta completar información básica en tu perfil: {", ".join(faltantes)}.',
                    )
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
        'datos_faltantes': _obtener_datos_basicos_faltantes(datos_personales, perfil_profesional),
    }
    return render(request, 'core/subir_cv.html', context)


@login_required
@require_POST
def editar_cv_view(request, pk):
    doc = get_object_or_404(DocumentoCV, pk=pk, usuario=request.user)
    form = DocumentoCVEditarForm(request.POST, instance=doc)
    if form.is_valid():
        form.save()
        messages.success(request, 'Nombre del CV actualizado.')
    else:
        messages.error(request, 'Ingresa un nombre válido para el documento.')
    return redirect('subir_cv')


@login_required
@require_POST
def reprocesar_cv_view(request, pk):
    doc = get_object_or_404(DocumentoCV, pk=pk, usuario=request.user)
    exito, mensaje = procesar_cv(doc)
    if exito:
        messages.success(request, f'Reprocesado: {mensaje}')
        datos_personales, _ = DatosPersonales.objects.get_or_create(usuario=request.user)
        perfil_profesional, _ = PerfilProfesional.objects.get_or_create(usuario=request.user)
        faltantes = _obtener_datos_basicos_faltantes(datos_personales, perfil_profesional)
        if faltantes:
            messages.warning(
                request,
                f'Falta completar información básica en tu perfil: {", ".join(faltantes)}.',
            )
    else:
        messages.error(request, mensaje)
    return redirect('subir_cv')


@login_required
@require_POST
def eliminar_cv_view(request, pk):
    doc = get_object_or_404(DocumentoCV, pk=pk, usuario=request.user)
    nombre = doc.nombre_archivo
    if doc.archivo:
        doc.archivo.delete(save=False)
    doc.delete()
    messages.success(request, f'Documento "{nombre}" eliminado.')
    return redirect('subir_cv')


CATEGORIAS_TRANSVERSALES = {
    'Habilidades Blandas', 'Gestión y Oficina', 'Gestión', 'Gestión de Proyectos', '',
}
COMPETENCIAS_TRANSVERSALES = {
    'excel', 'inglés', 'ingles', 'word', 'powerpoint', 'ofimática', 'ofimatica', 'redacción', 'redaccion',
}
MAPA_TEXTO_CATEGORIA = (
    (('derecho', 'abogad', 'legal', 'penal', 'civil', 'jurídic', 'juridic'), 'Legal'),
    (('salud', 'enferm', 'médic', 'medic', 'clínic', 'clinic', 'farmac'), 'Salud'),
    (('educa', 'docent', 'profesor', 'pedagog'), 'Educación'),
    (('contab', 'finanz', 'auditor', 'tribut'), 'Finanzas'),
    (('administra', 'oficina', 'asistente', 'recursos humanos'), 'Gestión y Oficina'),
    (('market', 'comunica', 'publicidad', 'redes sociales'), 'Marketing'),
    (('ingenier',), 'Ingeniería'),
    (('sistema', 'software', 'program', 'desarroll', 'datos', 'python', 'devops', 'cloud', 'ti '), 'Tecnología'),
)


def _obtener_categorias_usuario(perfil_profesional, mis_competencias):
    categorias = set()
    texto_perfil = ' '.join([
        perfil_profesional.puesto_objetivo or '',
        perfil_profesional.titulo_profesional or '',
        perfil_profesional.area_profesional or '',
    ]).lower()

    for palabras, categoria in MAPA_TEXTO_CATEGORIA:
        if any(p in texto_perfil for p in palabras):
            categorias.add(categoria)

    for uc in mis_competencias:
        cat = uc.competencia.categoria
        if cat and cat not in CATEGORIAS_TRANSVERSALES:
            categorias.add(cat)

    return categorias


def _competencia_pertinente_al_sector(competencia, categorias_usuario):
    if not categorias_usuario:
        return True
    if competencia.nombre.strip().lower() in COMPETENCIAS_TRANSVERSALES:
        return True
    cat = competencia.categoria
    if cat is None or cat in CATEGORIAS_TRANSVERSALES:
        return True
    return cat in categorias_usuario


def _agrupar_regiones(queryset):
    regiones = list(
        queryset.annotate(nombre=Coalesce(NullIf('region', Value('')), Value('Sin región')))
        .values('nombre').annotate(total=Count('pk')).order_by('-total', 'nombre')
    )
    if len(regiones) > 6:
        regiones = regiones[:5] + [
            {'nombre': 'Otras regiones', 'total': sum(item['total'] for item in regiones[5:])}
        ]
    return regiones


@login_required
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
        estadisticas = [
            {'titulo': titulo, 'icono': icono, 'total': total}
            for (titulo, icono), total in zip([
                ('Ofertas laborales extraídas', 'fa-solid fa-briefcase'),
                ('Competencias registradas', 'fa-solid fa-list-check'),
                ('Usuarios registrados', 'fa-solid fa-users'),
            ], totales)
        ]
        return render(request, 'core/dashboard.html', {
            'demo': True, 'es_personalizado': False, 'estadisticas': estadisticas,
            'competencias': competencias, 'regiones': regiones, 'incluye_arbeitnow': False,
        })

    if request.user.is_authenticated:
        datos_personales, _ = DatosPersonales.objects.get_or_create(usuario=request.user)
        perfil_profesional, _ = PerfilProfesional.objects.get_or_create(usuario=request.user)
        mis_competencias = list(
            UsuarioCompetencia.objects.filter(usuario=request.user)
            .select_related('competencia').order_by('competencia__nombre')
        )
        mis_comp_ids = [uc.competencia_id for uc in mis_competencias]
        mis_comp_set = {uc.competencia_id for uc in mis_competencias}
        mis_comp_tecnicas_ids = [
            uc.competencia_id for uc in mis_competencias if uc.competencia.tipo == 'TECNICA'
        ]
        terminos_perfil = obtener_terminos_busqueda_usuario(request.user)
        tiene_objetivo = any(
            (getattr(perfil_profesional, campo, '') or '').strip()
            for campo in ('puesto_objetivo', 'titulo_profesional', 'area_profesional')
        )

        filtro_perfil = Q()
        if tiene_objetivo:
            for termino in terminos_perfil:
                filtro_perfil |= (
                    Q(titulo__icontains=termino)
                    | Q(descripcion__icontains=termino)
                    | Q(sector__icontains=termino)
                )
            if mis_comp_tecnicas_ids:
                filtro_perfil |= Q(competencias__in=mis_comp_tecnicas_ids)
        elif mis_comp_tecnicas_ids:
            filtro_perfil |= Q(competencias__in=mis_comp_tecnicas_ids)
        elif mis_comp_ids:
            filtro_perfil |= Q(competencias__in=mis_comp_ids)

        if filtro_perfil:
            fecha_limite = timezone.now() - timedelta(days=30)
            ofertas_qs = (
                OfertaLaboral.objects.filter(filtro_perfil)
                .filter(
                    Q(fecha_publicacion__gte=fecha_limite)
                    | Q(fecha_publicacion__isnull=True, fecha_extraccion__gte=fecha_limite)
                )
                .annotate(coincidencias=Count('competencias', filter=Q(competencias__in=mis_comp_ids), distinct=True))
                .select_related('fuente').prefetch_related('competencias')
                .order_by('-coincidencias', '-fecha_publicacion', '-fecha_extraccion')
                .distinct()
            )
            total_compatibles = ofertas_qs.count()
            regiones = _agrupar_regiones(ofertas_qs)
        else:
            ofertas_qs = OfertaLaboral.objects.none()
            total_compatibles = 0
            regiones = []

        categorias_usuario = _obtener_categorias_usuario(perfil_profesional, mis_competencias)

        ofertas_recomendadas = []
        for oferta in ofertas_qs[:10]:
            todas_oferta = list(oferta.competencias.all())
            coincidentes = [c.nombre for c in todas_oferta if c.id in mis_comp_set]
            faltantes = [
                c.nombre for c in todas_oferta
                if c.id not in mis_comp_set and _competencia_pertinente_al_sector(c, categorias_usuario)
            ]
            ofertas_recomendadas.append({
                'oferta': oferta,
                'coincidencias': len(coincidentes),
                'coincidentes': coincidentes,
                'faltantes': faltantes[:4],
            })

        if total_compatibles > 0:
            ofertas_sector_ids = list(ofertas_qs.values_list('id', flat=True))
            candidatas = (
                Competencia.objects.filter(ofertas__id__in=ofertas_sector_ids)
                .annotate(total=Count('ofertas', filter=Q(ofertas__id__in=ofertas_sector_ids), distinct=True))
                .filter(total__gt=0)
                .order_by('-total', 'nombre')
            )
            top_mercado = [
                c for c in candidatas if _competencia_pertinente_al_sector(c, categorias_usuario)
            ][:8]
            competencias = [
                {'nombre': c.nombre, 'total': c.total, 'tengo': c.id in mis_comp_set}
                for c in top_mercado[:5]
            ]
            brechas = [c for c in top_mercado if c.id not in mis_comp_set][:5]
        else:
            competencias = []
            brechas = []

        total_cvs = DocumentoCV.objects.filter(usuario=request.user).count()
        total_reservas = Reserva.objects.filter(usuario=request.user).count()

        estadisticas = [
            {'titulo': 'Mis competencias', 'icono': 'fa-solid fa-award', 'total': len(mis_comp_ids)},
            {'titulo': 'Ofertas compatibles', 'icono': 'fa-solid fa-briefcase', 'total': total_compatibles},
            {'titulo': 'CVs subidos', 'icono': 'fa-solid fa-file-pdf', 'total': total_cvs},
        ]
        return render(request, 'core/dashboard.html', {
            'demo': False,
            'es_personalizado': True,
            'datos_personales': datos_personales,
            'perfil_profesional': perfil_profesional,
            'mis_competencias': mis_competencias,
            'ofertas_recomendadas': ofertas_recomendadas,
            'brechas': brechas,
            'total_reservas': total_reservas,
            'estadisticas': estadisticas,
            'competencias': competencias,
            'regiones': regiones,
            'incluye_arbeitnow': OfertaLaboral.objects.filter(fuente__nombre='Arbeitnow').exists(),
        })

    totales = (OfertaLaboral.objects.count(), Competencia.objects.count(), get_user_model().objects.count())
    competencias = list(
        Competencia.objects.annotate(total=Count('ofertas'))
        .filter(total__gt=0).order_by('-total', 'nombre').values('nombre', 'total')[:5]
    )
    regiones = _agrupar_regiones(OfertaLaboral.objects.all())
    estadisticas = [
        {'titulo': titulo, 'icono': icono, 'total': total}
        for (titulo, icono), total in zip([
            ('Ofertas laborales extraídas', 'fa-solid fa-briefcase'),
            ('Competencias registradas', 'fa-solid fa-list-check'),
            ('Usuarios registrados', 'fa-solid fa-users'),
        ], totales)
    ]
    return render(request, 'core/dashboard.html', {
        'demo': False, 'es_personalizado': False, 'estadisticas': estadisticas,
        'competencias': competencias, 'regiones': regiones,
        'incluye_arbeitnow': OfertaLaboral.objects.filter(fuente__nombre='Arbeitnow').exists(),
    })


@login_required
@require_POST
def recomendar_ofertas_view(request):
    resultado = recomendar_ofertas_para_usuario(request.user, limite=10, dias_max=30)
    if not resultado['terminos']:
        messages.warning(
            request,
            'Primero sube tu CV o agrega tu puesto objetivo y competencias en Mi Perfil para recomendar vacantes.',
        )
    elif resultado['fuentes_ok']:
        messages.success(
            request,
            f"Búsqueda en tiempo real completada ({', '.join(resultado['fuentes_ok'])}): "
            f"{resultado['nuevas']} ofertas recientes nuevas encontradas para {', '.join(resultado['terminos'])}.",
        )
    else:
        messages.warning(
            request,
            'No se pudieron obtener nuevas ofertas en este momento desde las fuentes externas.',
        )
    return redirect('dashboard')


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


@login_required
def perfil_view(request):
    datos, _ = DatosPersonales.objects.get_or_create(usuario=request.user)
    perfil_profesional, _ = PerfilProfesional.objects.get_or_create(usuario=request.user)

    datos_form = DatosPersonalesForm(instance=datos)
    profesional_form = PerfilProfesionalForm(instance=perfil_profesional)
    exp_form = ExperienciaLaboralForm()
    formacion_form = FormacionAcademicaForm()
    comp_form = UsuarioCompetenciaForm()

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'guardar_datos':
            datos_form = DatosPersonalesForm(request.POST, instance=datos)
            if datos_form.is_valid():
                datos_form.save()
                messages.success(request, 'Datos personales actualizados correctamente.')
                return redirect('perfil')
        elif accion == 'guardar_profesional':
            profesional_form = PerfilProfesionalForm(request.POST, instance=perfil_profesional)
            if profesional_form.is_valid():
                profesional_form.save()
                messages.success(request, 'Perfil profesional actualizado correctamente.')
                return redirect('perfil')
        elif accion == 'agregar_experiencia':
            exp_form = ExperienciaLaboralForm(request.POST)
            if exp_form.is_valid():
                exp = exp_form.save(commit=False)
                exp.usuario = request.user
                exp.save()
                messages.success(request, 'Experiencia laboral agregada.')
                return redirect('perfil')
        elif accion == 'agregar_formacion':
            formacion_form = FormacionAcademicaForm(request.POST)
            if formacion_form.is_valid():
                formacion = formacion_form.save(commit=False)
                formacion.usuario = request.user
                formacion.save()
                messages.success(request, 'Formación académica agregada.')
                return redirect('perfil')
        elif accion == 'agregar_competencia':
            comp_form = UsuarioCompetenciaForm(request.POST)
            if comp_form.is_valid():
                comp = comp_form.cleaned_data.get('competencia')
                if not comp:
                    nombre = comp_form.cleaned_data['nueva_competencia'].strip()
                    tipo = comp_form.cleaned_data.get('tipo_nueva') or 'TECNICA'
                    comp = Competencia.objects.filter(nombre__iexact=nombre).first()
                    if not comp:
                        comp = Competencia.objects.create(nombre=nombre, tipo=tipo)
                UsuarioCompetencia.objects.update_or_create(
                    usuario=request.user,
                    competencia=comp,
                    defaults={
                        'nivel': comp_form.cleaned_data['nivel'],
                        'anios_experiencia': comp_form.cleaned_data.get('anios_experiencia'),
                        'evidencia': comp_form.cleaned_data.get('evidencia', ''),
                    },
                )
                messages.success(request, f'Competencia "{comp.nombre}" guardada en tu perfil.')
                return redirect('perfil')

    competencias = UsuarioCompetencia.objects.filter(usuario=request.user).select_related('competencia').order_by('competencia__nombre')
    experiencias = ExperienciaLaboral.objects.filter(usuario=request.user).order_by('-trabajo_actual', '-fecha_inicio', '-pk')
    formaciones = FormacionAcademica.objects.filter(usuario=request.user).order_by('-fecha_fin', '-fecha_inicio', '-pk')
    documentos = DocumentoCV.objects.filter(usuario=request.user).order_by('-fecha_subida')

    return render(request, 'core/perfil.html', {
        'datos': datos,
        'perfil_profesional': perfil_profesional,
        'datos_faltantes': _obtener_datos_basicos_faltantes(datos, perfil_profesional),
        'competencias': competencias,
        'experiencias': experiencias,
        'formaciones': formaciones,
        'documentos': documentos,
        'datos_form': datos_form,
        'profesional_form': profesional_form,
        'exp_form': exp_form,
        'formacion_form': formacion_form,
        'comp_form': comp_form,
        'nivel_choices': UsuarioCompetencia.NIVEL_CHOICES,
    })


@login_required
@require_POST
def editar_experiencia_view(request, pk):
    exp = get_object_or_404(ExperienciaLaboral, pk=pk, usuario=request.user)
    form = ExperienciaLaboralForm(request.POST, instance=exp)
    if form.is_valid():
        form.save()
        messages.success(request, 'Experiencia laboral actualizada.')
    else:
        messages.error(request, 'Revisa los datos de la experiencia laboral (cargo, empresa y fecha de inicio son obligatorios).')
    return redirect('perfil')


@login_required
@require_POST
def eliminar_experiencia_view(request, pk):
    exp = get_object_or_404(ExperienciaLaboral, pk=pk, usuario=request.user)
    exp.delete()
    messages.success(request, 'Experiencia laboral eliminada.')
    return redirect('perfil')


@login_required
@require_POST
def editar_formacion_view(request, pk):
    formacion = get_object_or_404(FormacionAcademica, pk=pk, usuario=request.user)
    form = FormacionAcademicaForm(request.POST, instance=formacion)
    if form.is_valid():
        form.save()
        messages.success(request, 'Formación académica actualizada.')
    else:
        messages.error(request, 'Revisa los datos de formación académica (institución y carrera son obligatorios).')
    return redirect('perfil')


@login_required
@require_POST
def eliminar_formacion_view(request, pk):
    formacion = get_object_or_404(FormacionAcademica, pk=pk, usuario=request.user)
    formacion.delete()
    messages.success(request, 'Formación académica eliminada.')
    return redirect('perfil')


@login_required
@require_POST
def editar_competencia_view(request, pk):
    uc = get_object_or_404(UsuarioCompetencia, pk=pk, usuario=request.user)
    form = UsuarioCompetenciaEditarForm(request.POST, instance=uc)
    if form.is_valid():
        form.save()
        messages.success(request, f'Competencia "{uc.competencia.nombre}" actualizada.')
    else:
        messages.error(request, 'No se pudo actualizar la competencia.')
    return redirect('perfil')


@login_required
@require_POST
def eliminar_competencia_view(request, pk):
    uc = get_object_or_404(UsuarioCompetencia, pk=pk, usuario=request.user)
    nombre = uc.competencia.nombre
    uc.delete()
    messages.success(request, f'Competencia "{nombre}" eliminada de tu perfil.')
    return redirect('perfil')
