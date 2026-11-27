from django.core.management.base import BaseCommand

from core.models import Competencia, ServicioCapacitacion


CATALOGO_SERVICIOS = [
    # --- Cursos gratuitos verificados de plataformas externas ---
    {
        'nombre': 'Python Essentials 1',
        'descripcion': 'Curso oficial de programación en Python desde cero, orientado a automatización, lógica y desarrollo.',
        'categoria': 'TECNOLOGIA',
        'proveedor': 'Cisco Networking Academy',
        'duracion': '30 horas',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': True,
        'es_externo': True,
        'url_externa': 'https://www.netacad.com/courses/python-essentials-1?courseLang=es-XL',
        'competencias': ['Python'],
    },
    {
        'nombre': 'Introducción a la Ciberseguridad',
        'descripcion': 'Fundamentos de seguridad informática, protección de redes, datos y buenas prácticas digitales.',
        'categoria': 'TECNOLOGIA',
        'proveedor': 'Cisco Networking Academy',
        'duracion': '6 horas',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': True,
        'es_externo': True,
        'url_externa': 'https://www.netacad.com/courses/introduction-to-cybersecurity?courseLang=es-XL',
        'competencias': ['Ciberseguridad', 'Redes'],
    },
    {
        'nombre': 'Capacitación Laboral Gratuita (MTPE)',
        'descripcion': 'Cursos gratuitos oficiales del Ministerio de Trabajo del Perú para fortalecer competencias laborales en múltiples sectores y oficios.',
        'categoria': 'EMPLEABILIDAD',
        'proveedor': 'Ministerio de Trabajo (Empleos Perú)',
        'duracion': 'Variable según curso',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': True,
        'es_externo': True,
        'url_externa': 'https://capacitacionlaboral.trabajo.gob.pe/cursos/',
        'competencias': ['Trabajo en Equipo', 'Comunicación', 'Atención al Cliente'],
    },
    {
        'nombre': 'Cursos Técnicos y Oficios con Certificado',
        'descripcion': 'Plataforma gratuita con rutas en administración, contabilidad, salud, electricidad, gastronomía, ventas y tecnología.',
        'categoria': 'OFICIOS',
        'proveedor': 'Capacítate para el Empleo (Fundación Carlos Slim)',
        'duracion': 'A tu ritmo',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': True,
        'es_externo': True,
        'url_externa': 'https://capacitateparaelempleo.org/',
        'competencias': ['Excel', 'Ventas', 'Atención al Cliente'],
    },
    {
        'nombre': 'Marketing Digital y Analítica (Skillshop)',
        'descripcion': 'Rutas oficiales gratuitas de Google en marketing digital, analítica y publicidad en línea.',
        'categoria': 'MARKETING',
        'proveedor': 'Google Skillshop',
        'duracion': 'A tu ritmo',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': True,
        'es_externo': True,
        'url_externa': 'https://skillshop.exceedlms.com/student/catalog',
        'competencias': ['Marketing Digital', 'Google Analytics'],
    },
    {
        'nombre': 'Habilidades Digitales y Productividad',
        'descripcion': 'Recursos gratuitos de Google para mejorar competencias digitales, comunicación profesional y gestión laboral.',
        'categoria': 'ADMINISTRACION',
        'proveedor': 'Grow with Google',
        'duracion': 'A tu ritmo',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': False,
        'es_externo': True,
        'url_externa': 'https://grow.google/intl/es/',
        'competencias': ['Liderazgo', 'Comunicación', 'Trabajo en Equipo'],
    },
    {
        'nombre': 'Economía, Finanzas y Cálculo Aplicado',
        'descripcion': 'Lecciones gratuitas en español sobre finanzas personales, contabilidad básica, estadística y matemáticas.',
        'categoria': 'CONTABILIDAD',
        'proveedor': 'Khan Academy',
        'duracion': 'A tu ritmo',
        'modalidad': 'VIRTUAL',
        'precio': 0,
        'otorga_certificado': False,
        'es_externo': True,
        'url_externa': 'https://es.khanacademy.org/',
        'competencias': ['Finanzas', 'Contabilidad'],
    },
    # --- Talleres y asesorías propios de EmpleoPredict (con reserva de cupos) ---
    {
        'nombre': 'Asesoría Personalizada de CV y Entrevista',
        'descripcion': 'Sesión práctica para estructurar tu currículum, destacar logros y prepararte para entrevistas laborales en cualquier carrera u oficio.',
        'categoria': 'EMPLEABILIDAD',
        'proveedor': 'EmpleoPredict',
        'duracion': '2 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 12,
        'precio': 0,
        'otorga_certificado': False,
        'es_externo': False,
        'competencias': ['Comunicación', 'Liderazgo'],
    },
    {
        'nombre': 'Excel para el Trabajo y Gestión',
        'descripcion': 'Fórmulas, tablas dinámicas, filtros avanzados y reportes aplicados a oficina, administración, contabilidad y logística.',
        'categoria': 'ADMINISTRACION',
        'proveedor': 'EmpleoPredict',
        'duracion': '10 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 25,
        'precio': 35,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Excel'],
    },
    {
        'nombre': 'Taller de Redacción Jurídica y Argumentación',
        'descripcion': 'Elaboración de escritos, informes legales, análisis de plazos procesales y técnicas de litigación oral.',
        'categoria': 'DERECHO',
        'proveedor': 'EmpleoPredict',
        'duracion': '8 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 20,
        'precio': 40,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Derecho Penal', 'Derecho Civil', 'Redacción Jurídica', 'Litigación Oral'],
    },
    {
        'nombre': 'Tributación, Costos y Análisis Financiero',
        'descripcion': 'Taller práctico sobre registro contable, flujo de caja, presupuestos y normativa tributaria vigente.',
        'categoria': 'CONTABILIDAD',
        'proveedor': 'EmpleoPredict',
        'duracion': '8 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 20,
        'precio': 40,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Contabilidad', 'Finanzas', 'Excel'],
    },
    {
        'nombre': 'Herramientas Digitales y Evaluación Educativa',
        'descripcion': 'Diseño de sesiones, rúbricas de evaluación y uso de plataformas digitales para docentes y formadores.',
        'categoria': 'EDUCACION',
        'proveedor': 'EmpleoPredict',
        'duracion': '6 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 25,
        'precio': 30,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Docencia', 'Pedagogía', 'Comunicación'],
    },
    {
        'nombre': 'Atención al Paciente y Primeros Auxilios',
        'descripcion': 'Protocolos de atención inicial, bioseguridad, trato humano y registro clínico para personal de salud.',
        'categoria': 'SALUD',
        'proveedor': 'EmpleoPredict',
        'duracion': '8 horas',
        'modalidad': 'PRESENCIAL',
        'capacidad_maxima': 18,
        'precio': 45,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Enfermería', 'Primeros Auxilios', 'Atención al Cliente'],
    },
    {
        'nombre': 'Gestión de Proyectos e Ingeniería Aplicada',
        'descripcion': 'Planificación, control de calidad, lectura de planos y herramientas de gestión para proyectos de ingeniería.',
        'categoria': 'INGENIERIA',
        'proveedor': 'EmpleoPredict',
        'duracion': '10 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 20,
        'precio': 50,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['AutoCAD', 'Gestión de Proyectos', 'Excel'],
    },
    {
        'nombre': 'SQL, Python y Power BI para Análisis de Datos',
        'descripcion': 'Consultas SQL, limpieza de datos con Python y tableros ejecutivos en Power BI orientados a vacantes TI.',
        'categoria': 'TECNOLOGIA',
        'proveedor': 'EmpleoPredict',
        'duracion': '12 horas',
        'modalidad': 'EN_VIVO',
        'capacidad_maxima': 20,
        'precio': 50,
        'otorga_certificado': True,
        'es_externo': False,
        'competencias': ['Python', 'SQL', 'Power BI', 'Git'],
    },
]


class Command(BaseCommand):
    help = 'Carga el catálogo inicial multisectorial de cursos externos gratuitos y talleres propios.'

    def handle(self, *args, **options):
        creados = 0
        actualizados = 0

        for item in CATALOGO_SERVICIOS:
            nombres_comp = item.pop('competencias', [])
            servicio, creado = ServicioCapacitacion.objects.update_or_create(
                nombre=item['nombre'],
                defaults={**item, 'activo': True},
            )
            item['competencias'] = nombres_comp
            comps = list(Competencia.objects.filter(nombre__in=nombres_comp))
            if comps:
                servicio.competencias.set(comps)
            if creado:
                creados += 1
            else:
                actualizados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Catálogo cargado: {creados} servicios nuevos, {actualizados} actualizados.'
            )
        )
