from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from core.models import (
    Competencia, DatosPersonales, FuenteDato,
    IndicadorEmpleabilidadONG, OfertaLaboral, Reserva, ServicioCapacitacion,
)
from core.forms import SubirCVForm
from core.scraper import scrapear_computrabajo
from core.utils import extraer_datos_contacto, extraer_competencias_del_texto, poblar_catalogo_competencias
from django.core.files.uploadedfile import SimpleUploadedFile

class ModuloCVTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        poblar_catalogo_competencias()

    def test_extraccion_datos_contacto(self):
        texto_muestra = """
        Duván Dávila - Desarrollador Backend
        Teléfono: +51 987 654 321
        Correo: duvandavila@ejemplo.com
        LinkedIn: https://www.linkedin.com/in/duvandavila/
        GitHub: https://github.com/duvandavila
        """
        datos = extraer_datos_contacto(texto_muestra)
        self.assertEqual(datos["email"], "duvandavila@ejemplo.com")
        self.assertEqual(datos["telefono"], "+51987654321")
        self.assertTrue("linkedin.com/in/duvandavila" in datos["linkedin_url"])
        self.assertTrue("github.com/duvandavila" in datos["github_url"])

    def test_extraccion_competencias(self):
        texto_cv = """
        Experiencia trabajando con Python y Django en aplicaciones web.
        Manejo avanzado de base de datos SQL y Git para control de versiones.
        Habilidades demostradas de Liderazgo y Trabajo en Equipo.
        """
        competencias = extraer_competencias_del_texto(texto_cv)
        nombres = [c.nombre for c in competencias]
        self.assertIn("Python", nombres)
        self.assertIn("Django", nombres)
        self.assertIn("SQL", nombres)
        self.assertIn("Git", nombres)
        self.assertIn("Liderazgo", nombres)
        self.assertIn("Trabajo en Equipo", nombres)

    def test_formulario_rechaza_archivos_no_pdf(self):
        archivo_txt = SimpleUploadedFile("cv.txt", b"Texto de prueba", content_type="text/plain")
        form = SubirCVForm(files={'archivo': archivo_txt})
        self.assertFalse(form.is_valid())
        self.assertIn("archivo", form.errors)


class DashboardServiciosTestCase(TestCase):
    def test_dashboard_resume_las_ofertas_y_mantiene_la_demo_separada(self):
        fuente = FuenteDato.objects.create(nombre='Prueba', url_base='https://example.com')
        oferta = OfertaLaboral.objects.create(titulo='Desarrollo', region='Lima', fuente=fuente)
        python = Competencia.objects.create(nombre='Python', tipo='TECNICA')
        oferta.competencias.add(python)
        OfertaLaboral.objects.create(titulo='Soporte', fuente=fuente)

        respuesta = self.client.get('/dashboard/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['estadisticas'][0]['total'], 2)
        self.assertEqual(respuesta.context['competencias'], [{'nombre': 'Python', 'total': 1}])
        self.assertIn({'nombre': 'Sin región', 'total': 1}, respuesta.context['regiones'])
        self.assertContains(self.client.get('/dashboard/?demo=1'), 'Las cifras y gráficos de esta vista son ficticios')

    def test_catalogo_muestra_servicios_y_habilita_reserva_solo_para_reales(self):
        respuesta_demo = self.client.get('/servicios/')
        self.assertContains(respuesta_demo, 'Catálogo de ejemplo')
        self.assertContains(respuesta_demo, 'disabled')

        servicio = ServicioCapacitacion.objects.create(nombre='Curso real', descripcion='Nivel básico', precio=10)
        respuesta = self.client.get('/servicios/')
        self.assertContains(respuesta, 'Curso real')
        self.assertContains(respuesta, reverse('reservar_servicio', args=[servicio.pk]))
        self.assertNotContains(respuesta, 'Catálogo de ejemplo')


class ScraperTestCase(TestCase):
    def test_importa_y_deduplica_por_region(self):
        html = """
        <article class="box_offer">
            <h2>Desarrollador Python</h2>
            <a href="/empresa/ejemplo">Empresa Ejemplo</a>
            <p class="fs16 fc_base"><span>Empresa Ejemplo</span><span>Miraflores, Lima</span></p>
        </article>
        <article class="box_offer">
            <h2>Desarrollador Python</h2>
            <a href="/empresa/ejemplo">Empresa Ejemplo</a>
            <p itemprop="addressRegion">Arequipa</p>
        </article>
        <article class="box_offer"><p>Tarjeta incompleta</p></article>
        """
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.text = html
            self.assertEqual(scrapear_computrabajo(' Python Django '), 2)
            solicitar.assert_called_with('https://pe.computrabajo.com/trabajo-de-python-django', timeout=15)
            self.assertEqual(scrapear_computrabajo(), 0)

        self.assertEqual(OfertaLaboral.objects.count(), 2)
        self.assertEqual(OfertaLaboral.objects.filter(competencias__nombre='Python').count(), 2)
        self.assertIsNotNone(FuenteDato.objects.get().ultima_ejecucion)

    def test_comando_informa_bloqueo_sin_crear_registros(self):
        with patch('core.scraper.requests.get') as solicitar:
            respuesta = requests.Response()
            respuesta.status_code = 403
            solicitar.return_value = respuesta
            with self.assertRaisesMessage(CommandError, 'HTTP 403'):
                call_command('scrapear', keyword='python')

        self.assertFalse(FuenteDato.objects.exists())

    def test_arbeitnow_importa_coincidencias_y_respeta_el_limite(self):
        filas = [
            {'title': 'Diseñadora', 'description': 'Diseño gráfico'},
            {'title': 'Desarrollo', 'company_name': 'Prueba', 'location': 'Berlin',
             'description': '&lt;p&gt;Trabajo con Python&lt;/p&gt;'},
            {'title': 'Python y datos', 'location': 'Munich'},
        ]
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = {'data': filas}
            call_command('scrapear', fuente='arbeitnow', keyword='PYTHON', limite=1)
            call_command('scrapear', fuente='arbeitnow', keyword='PYTHON', limite=1)

        oferta = OfertaLaboral.objects.get()
        self.assertEqual(oferta.fuente.nombre, 'Arbeitnow')
        self.assertEqual(oferta.region, 'Berlin')
        self.assertEqual(oferta.descripcion, 'Trabajo con Python')
        self.assertTrue(oferta.competencias.filter(nombre='Python').exists())
        self.assertContains(self.client.get('/dashboard/'), 'https://www.arbeitnow.com/')

    def test_getonboard_importa_ofertas_con_url_y_deduplica(self):
        payload = {
            'data': [
                {
                    'id': 'desarrollador-python-lima',
                    'type': 'job',
                    'attributes': {
                        'title': 'Desarrollador Python',
                        'description': '<p>Desarrollo backend con <strong>Python</strong> y Django.</p>',
                        'functions': '<ul><li>Construir APIs</li></ul>',
                        'desirable': '',
                        'category_name': 'Programación',
                        'min_salary': 2500,
                        'countries': ['Chile', 'Peru'],
                        'remote': False,
                        'location_cities': {
                            'data': [
                                {'id': '1', 'attributes': {'name': 'Santiago', 'country': 'Chile'}},
                                {'id': '130', 'attributes': {'name': 'Lima', 'country': 'Peru'}},
                            ]
                        },
                        'company': {
                            'data': {'id': 'tech-pe', 'attributes': {'name': 'Tech Peru SAC'}}
                        },
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/desarrollador-python-lima'},
                },
                {
                    'id': 'sin-titulo',
                    'type': 'job',
                    'attributes': {'title': '   ', 'countries': ['Peru']},
                },
            ]
        }
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = payload
            call_command('scrapear', fuente='getonboard', keyword='peru', limite=5)
            call_command('scrapear', fuente='getonboard', keyword='peru', limite=5)

        self.assertEqual(OfertaLaboral.objects.count(), 1)
        oferta = OfertaLaboral.objects.get()
        self.assertEqual(oferta.fuente.nombre, 'Get on Board')
        self.assertEqual(oferta.empresa, 'Tech Peru SAC')
        self.assertEqual(oferta.region, 'Lima')
        self.assertEqual(oferta.sector, 'Programación')
        self.assertIsNone(oferta.salario)
        self.assertEqual(oferta.url_original, 'https://www.getonbrd.com/jobs/desarrollador-python-lima')
        self.assertIn('Desarrollo backend con Python y Django.', oferta.descripcion)
        self.assertIn('Construir APIs', oferta.descripcion)
        self.assertTrue(oferta.competencias.filter(nombre='Python').exists())

    def test_getonboard_prioriza_pais_o_remoto_y_maneja_errores(self):
        payload = {
            'data': [
                {
                    'attributes': {
                        'title': 'Analista de Datos',
                        'countries': ['Peru'],
                        'remote': False,
                        'location_cities': {'data': []},
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/analista-datos-peru'},
                },
                {
                    'attributes': {
                        'title': 'Ingeniero DevOps',
                        'countries': ['Remoto'],
                        'remote': True,
                        'location_cities': {'data': []},
                        'location_tenants': {
                            'data': [{'id': 'peru', 'type': 'country', 'attributes': {'name': 'Peru'}}]
                        },
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/devops-remoto'},
                },
            ]
        }
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = payload
            call_command('scrapear', fuente='getonboard', keyword='datos', limite=2)

        regiones = dict(OfertaLaboral.objects.values_list('titulo', 'region'))
        self.assertEqual(regiones['Analista de Datos'], 'Perú')
        self.assertEqual(regiones['Ingeniero DevOps'], 'Remoto')

        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = {'data': []}
            call_command('scrapear', fuente='getonboard', keyword='inexistente')
        self.assertEqual(OfertaLaboral.objects.count(), 2)

        with patch('core.scraper.requests.get') as solicitar:
            respuesta = requests.Response()
            respuesta.status_code = 429
            solicitar.return_value = respuesta
            with self.assertRaisesMessage(CommandError, 'HTTP 429'):
                call_command('scrapear', fuente='getonboard', keyword='peru')

    def test_getonboard_acepta_lima_y_remoto_habilitado_en_peru(self):
        payload = {
            'data': [
                {
                    'attributes': {
                        'title': 'Desarrollador Backend Lima',
                        'countries': ['Peru'],
                        'remote': False,
                        'location_cities': {
                            'data': [{'id': '130', 'attributes': {'name': 'Lima', 'country': 'Peru'}}]
                        },
                        'location_tenants': {'data': []},
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/backend-lima'},
                },
                {
                    'attributes': {
                        'title': 'Ingeniero Cloud Remoto',
                        'countries': ['Remote'],
                        'remote': True,
                        'remote_modality': 'remote_local',
                        'location_cities': {'data': []},
                        'location_tenants': {
                            'data': [
                                {'id': 'colombia', 'attributes': {'name': 'Colombia'}},
                                {'id': 'peru', 'attributes': {'name': 'Peru'}},
                            ]
                        },
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/cloud-remoto-peru'},
                },
            ]
        }
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = payload
            call_command('scrapear', fuente='getonboard', keyword='python', limite=5)

        expand = solicitar.call_args.kwargs['params']['expand']
        self.assertIn('location_tenants', expand)
        regiones = dict(OfertaLaboral.objects.values_list('titulo', 'region'))
        self.assertEqual(regiones, {
            'Desarrollador Backend Lima': 'Lima',
            'Ingeniero Cloud Remoto': 'Remoto',
        })

    def test_getonboard_rechaza_santiago_remoto_extranjero_y_ubicacion_ambigua(self):
        payload = {
            'data': [
                {
                    'attributes': {
                        'title': 'Product Owner Santiago',
                        'description': '<p>Trabaja con clientes de Perú desde Chile.</p>',
                        'countries': ['Chile'],
                        'remote': False,
                        'location_cities': {
                            'data': [{'id': '1', 'attributes': {'name': 'Santiago', 'country': 'Chile'}}]
                        },
                        'location_tenants': {'data': []},
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/po-santiago'},
                },
                {
                    'attributes': {
                        'title': 'Python Remoto Solo Chile',
                        'countries': ['Remote'],
                        'remote': True,
                        'remote_modality': 'remote_local',
                        'location_cities': {'data': []},
                        'location_tenants': {
                            'data': [{'id': 'chile', 'attributes': {'name': 'Chile'}}]
                        },
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/python-remoto-chile'},
                },
                {
                    'attributes': {
                        'title': 'DevOps Remoto Ambiguo',
                        'description': '<p>Disponible también en Perú.</p>',
                        'countries': ['Remote'],
                        'remote': True,
                        'remote_modality': 'fully_remote',
                        'location_cities': {'data': []},
                        'location_tenants': {'data': []},
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/devops-ambiguo'},
                },
                {
                    'attributes': {
                        'title': 'QA Sin Datos Geograficos',
                        'countries': [],
                        'remote': False,
                        'location_cities': {'data': []},
                        'location_tenants': {'data': []},
                    },
                    'links': {'public_url': 'https://www.getonbrd.com/jobs/qa-sin-ubicacion'},
                },
            ]
        }
        with patch('core.scraper.requests.get') as solicitar:
            solicitar.return_value.json.return_value = payload
            with self.assertLogs('core.scraper', level='INFO') as logs:
                call_command('scrapear', fuente='getonboard', keyword='python', limite=5)

        self.assertEqual(OfertaLaboral.objects.count(), 0)
        mensajes = '\n'.join(logs.output)
        self.assertIn('Product Owner Santiago', mensajes)
        self.assertIn('Santiago (Chile)', mensajes)
        self.assertIn('Python Remoto Solo Chile', mensajes)
        self.assertIn('Chile', mensajes)
        self.assertIn('DevOps Remoto Ambiguo', mensajes)
        self.assertIn('QA Sin Datos Geograficos', mensajes)


class ServiciosReservasAuthTestCase(TestCase):
    def setUp(self):
        self.usuario_normal = User.objects.create_user(
            username='valeria_user',
            password='ClaveSegura2026!',
        )
        self.otro_usuario = User.objects.create_user(
            username='carlos_user',
            password='ClaveSegura2026!',
        )
        self.servicio_python = ServicioCapacitacion.objects.create(
            nombre='Taller de Python Aplicado',
            descripcion='Automatiza tareas de análisis laboral con scripts.',
            capacidad_maxima=2,
            precio=50,
        )
        self.servicio_excel = ServicioCapacitacion.objects.create(
            nombre='Excel para Gestión',
            descripcion='Tablas dinámicas y reportes empresariales.',
            capacidad_maxima=1,
            precio=35,
        )

    def _fecha_futura_str(self, dias=5, hora='10:00'):
        fecha_local = (timezone.localdate() + timedelta(days=dias)).strftime('%Y-%m-%d')
        return f'{fecha_local}T{hora}'

    def _fecha_futura_dt(self, dias=5, hora=10, minuto=0):
        base = timezone.localtime(timezone.now()) + timedelta(days=dias)
        return base.replace(hour=hora, minute=minuto, second=0, microsecond=0)

    def test_login_de_usuario_normal_no_administrador(self):
        self.assertFalse(self.usuario_normal.is_staff)
        respuesta = self.client.post(
            reverse('login'),
            {'username': 'valeria_user', 'password': 'ClaveSegura2026!'},
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context['user'].is_authenticated)
        self.assertEqual(respuesta.context['user'].username, 'valeria_user')

    def test_registro_de_usuario_normal(self):
        respuesta = self.client.post(
            reverse('registro'),
            {
                'username': 'nuevo_postulante',
                'email': 'nuevo@ejemplo.com',
                'password1': 'ClaveSegura2026!',
                'password2': 'ClaveSegura2026!',
            },
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        nuevo = User.objects.get(username='nuevo_postulante')
        self.assertFalse(nuevo.is_staff)
        self.assertFalse(nuevo.is_superuser)
        self.assertTrue(DatosPersonales.objects.filter(usuario=nuevo).exists())
        self.assertTrue(respuesta.context['user'].is_authenticated)

    def test_acceso_reservar_sin_login_redirige_a_login_publico_y_retorna(self):
        url_reservar = reverse('reservar_servicio', args=[self.servicio_python.pk])
        respuesta = self.client.get(url_reservar)
        self.assertRedirects(respuesta, f"{reverse('login')}?next={url_reservar}")

        login_resp = self.client.post(
            f"{reverse('login')}?next={url_reservar}",
            {'username': 'valeria_user', 'password': 'ClaveSegura2026!'},
        )
        self.assertRedirects(login_resp, url_reservar)

    def test_reserva_valida_asigna_usuario_autenticado_y_redirige_a_mis_reservas(self):
        self.client.force_login(self.usuario_normal)
        url_reservar = reverse('reservar_servicio', args=[self.servicio_python.pk])
        respuesta = self.client.post(
            url_reservar,
            {
                'fecha_reserva': self._fecha_futura_str(dias=4, hora='15:30'),
                'usuario': self.otro_usuario.pk,
                'estado': 'Confirmada',
            },
        )
        self.assertRedirects(respuesta, reverse('mis_reservas'))
        reserva = Reserva.objects.get()
        self.assertEqual(reserva.usuario, self.usuario_normal)
        self.assertEqual(reserva.servicio, self.servicio_python)
        self.assertEqual(reserva.estado, 'Pendiente')

    def test_rechaza_fecha_pasada(self):
        self.client.force_login(self.usuario_normal)
        fecha_pasada = (timezone.localtime(timezone.now()) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        respuesta = self.client.post(
            reverse('reservar_servicio', args=[self.servicio_python.pk]),
            {'fecha_reserva': fecha_pasada},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Reserva.objects.exists())
        self.assertContains(respuesta, 'fecha u hora pasada')

    def test_rechaza_cuando_se_llena_capacidad_en_misma_fecha_peru(self):
        # 21:00 America/Lima equivale a 02:00 UTC del día siguiente; debe contar en el mismo día de Lima.
        Reserva.objects.create(
            usuario=self.otro_usuario,
            servicio=self.servicio_excel,
            fecha_reserva=self._fecha_futura_dt(dias=6, hora=9, minuto=0),
            estado='Confirmada',
        )
        self.client.force_login(self.usuario_normal)
        respuesta = self.client.post(
            reverse('reservar_servicio', args=[self.servicio_excel.pk]),
            {'fecha_reserva': self._fecha_futura_str(dias=6, hora='21:00')},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(respuesta, 'No quedan cupos disponibles')

    def test_acepta_reservas_mismo_servicio_en_fechas_diferentes(self):
        Reserva.objects.create(
            usuario=self.otro_usuario,
            servicio=self.servicio_excel,
            fecha_reserva=self._fecha_futura_dt(dias=6, hora=10, minuto=0),
            estado='Confirmada',
        )
        self.client.force_login(self.usuario_normal)
        respuesta = self.client.post(
            reverse('reservar_servicio', args=[self.servicio_excel.pk]),
            {'fecha_reserva': self._fecha_futura_str(dias=7, hora='10:00')},
        )
        self.assertRedirects(respuesta, reverse('mis_reservas'))
        self.assertEqual(Reserva.objects.count(), 2)

    def test_rechaza_duplicado_activo_mismo_usuario_servicio_y_fecha(self):
        Reserva.objects.create(
            usuario=self.usuario_normal,
            servicio=self.servicio_python,
            fecha_reserva=self._fecha_futura_dt(dias=5, hora=9, minuto=0),
            estado='Pendiente',
        )
        self.client.force_login(self.usuario_normal)
        respuesta = self.client.post(
            reverse('reservar_servicio', args=[self.servicio_python.pk]),
            {'fecha_reserva': self._fecha_futura_str(dias=5, hora='18:00')},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(respuesta, 'Ya tienes una reserva activa')

    def test_reservas_canceladas_no_ocupan_cupos_ni_bloquean_nueva_reserva(self):
        Reserva.objects.create(
            usuario=self.usuario_normal,
            servicio=self.servicio_excel,
            fecha_reserva=self._fecha_futura_dt(dias=8, hora=10, minuto=0),
            estado='Cancelada',
        )
        self.client.force_login(self.usuario_normal)
        respuesta = self.client.post(
            reverse('reservar_servicio', args=[self.servicio_excel.pk]),
            {'fecha_reserva': self._fecha_futura_str(dias=8, hora='14:00')},
        )
        self.assertRedirects(respuesta, reverse('mis_reservas'))
        self.assertEqual(Reserva.objects.filter(estado='Pendiente').count(), 1)

    def test_usuario_solo_puede_consultar_sus_propias_reservas(self):
        Reserva.objects.create(
            usuario=self.usuario_normal,
            servicio=self.servicio_python,
            fecha_reserva=self._fecha_futura_dt(dias=5, hora=10),
            estado='Confirmada',
        )
        Reserva.objects.create(
            usuario=self.otro_usuario,
            servicio=self.servicio_excel,
            fecha_reserva=self._fecha_futura_dt(dias=6, hora=11),
            estado='Pendiente',
        )
        self.client.force_login(self.usuario_normal)
        respuesta = self.client.get(reverse('mis_reservas'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Taller de Python Aplicado')
        self.assertContains(respuesta, 'Confirmada')
        self.assertNotContains(respuesta, 'Excel para Gestión')

    def test_catalogo_permite_buscar_servicios_por_nombre_y_descripcion(self):
        por_nombre = self.client.get('/servicios/?q=Python')
        self.assertContains(por_nombre, 'Taller de Python Aplicado')
        self.assertNotContains(por_nombre, 'Excel para Gestión')

        por_descripcion = self.client.get('/servicios/?q=dinámicas')
        self.assertContains(por_descripcion, 'Excel para Gestión')
        self.assertNotContains(por_descripcion, 'Taller de Python Aplicado')

        sin_resultados = self.client.get('/servicios/?q=Inexistente')
        self.assertContains(sin_resultados, 'No se encontraron servicios')
        self.assertNotContains(sin_resultados, 'Catálogo de ejemplo')

    def test_servicios_de_demostracion_no_permiten_reservas_reales(self):
        ServicioCapacitacion.objects.all().delete()
        catalogo = self.client.get('/servicios/')
        self.assertContains(catalogo, 'Catálogo de ejemplo')
        self.assertContains(catalogo, 'disabled')
        self.assertNotContains(catalogo, '/reservar/')

        self.client.force_login(self.usuario_normal)
        intento = self.client.post(
            reverse('reservar_servicio', args=[999]),
            {'fecha_reserva': self._fecha_futura_str(dias=4, hora='10:00')},
        )
        self.assertEqual(intento.status_code, 404)
        self.assertFalse(Reserva.objects.exists())


class MTPEHistoricoTestCase(TestCase):
    def _respuesta_csv(self, lineas):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.iter_lines.return_value = [linea.encode('utf-8') for linea in lineas]
        return resp

    def test_mtpe_importa_en_streaming_relaciona_competencias_por_avisoid_y_deduplica(self):
        comp_larga = 'a' * 124
        lineas_vacantes = [
            '\ufeffAVISOID,NOMBREAVISO,VACANTES,POSTULANTES,IDEMPRESA,UBIGEO,DEPARTAMENTO,PROVINCIA,DISTRITO,FECHAINICIO,FECHAFIN,SINEXPERIENCIA,TIEMPOEXPERIENCIA,TIPOTIEMPOEXPERIENCIA,SECTOR,ESCO,ESPCD,FECHACREACION,ACTIVO',
            '3,Asistente de Contabilidad,4,2,HASH1,200601,PIURA,SULLANA,SULLANA,20231030,20231114,NO,1,AÑO(S),Forestal/Papel y Celulosa,auxiliar contable,SI,20231017,ACTIVO',
            '4,Supervisor Textil,2,1,HASH2,150118,LA LIBERTAD,TRUJILLO,TRUJILLO,20240229,20240307,SI,,,Manufactura,supervisor textil,NO,20240220,ACTIVO',
        ]
        lineas_competencias = [
            'AVISOID,NOMBRECOMPETENCIA',
            '3,archivar documentos',
            f'3,{comp_larga}',
            '99999,competencia de aviso no importado',
        ]

        def simular_get(url, **kwargs):
            if 'Competencia' in url:
                return self._respuesta_csv(lineas_competencias)
            return self._respuesta_csv(lineas_vacantes)

        with patch('core.scraper.requests.get', side_effect=simular_get):
            call_command('scrapear', fuente='mtpe', limite=5)
            self.assertEqual(OfertaLaboral.objects.count(), 2)
            call_command('scrapear', fuente='mtpe', limite=5)

        fuente = FuenteDato.objects.get()
        self.assertEqual(fuente.tipo, 'Oficial')
        self.assertEqual(OfertaLaboral.objects.count(), 2)

        oferta3 = OfertaLaboral.objects.get(codigo_externo='3')
        self.assertTrue(oferta3.es_historica)
        self.assertEqual(oferta3.region, 'Piura')
        self.assertEqual(oferta3.vacantes, 4)
        self.assertEqual(oferta3.ocupacion, 'auxiliar contable')
        self.assertEqual(oferta3.fecha_inicio_periodo, date(2023, 10, 30))
        self.assertEqual(oferta3.fecha_fin_periodo, date(2023, 11, 14))
        self.assertSetEqual(
            set(oferta3.competencias.values_list('nombre', flat=True)),
            {'archivar documentos', comp_larga},
        )
        self.assertFalse(Competencia.objects.filter(nombre='competencia de aviso no importado').exists())
        self.assertTrue(all(not c.es_catalogo_cv for c in oferta3.competencias.all()))

    def test_mtpe_no_afecta_catalogo_cv_ni_mezcla_dashboard_vigente(self):
        poblar_catalogo_competencias()
        fuente_gob = FuenteDato.objects.create(nombre='Get on Board', url_base='https://www.getonbrd.com', tipo='Privada')
        oferta_actual = OfertaLaboral.objects.create(
            titulo='Dev Python', region='Lima', fuente=fuente_gob, es_historica=False
        )
        oferta_actual.competencias.add(Competencia.objects.get(nombre='Python'))

        fuente_mtpe = FuenteDato.objects.create(
            nombre='MTPE Datos Abiertos', url_base='https://www.datosabiertos.gob.pe', tipo='Oficial'
        )
        oferta_mtpe = OfertaLaboral.objects.create(
            titulo='Asistente Ventas',
            region='Piura',
            sector='Comercial',
            ocupacion='asistente de ventas',
            vacantes=10,
            es_historica=True,
            codigo_externo='501',
            fecha_inicio_periodo=date(2024, 1, 10),
            fecha_fin_periodo=date(2024, 2, 10),
            fuente=fuente_mtpe,
        )
        comp_esco = Competencia.objects.create(
            nombre='atender mostrador comercial',
            tipo='TECNICA',
            categoria='MTPE ESCO',
            es_catalogo_cv=False,
        )
        oferta_mtpe.competencias.add(comp_esco)

        detectadas = extraer_competencias_del_texto('Experiencia con Python y atender mostrador comercial')
        self.assertEqual([c.nombre for c in detectadas], ['Python'])

        respuesta = self.client.get('/dashboard/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['estadisticas'][0]['total'], 1)
        self.assertEqual(respuesta.context['competencias'], [{'nombre': 'Python', 'total': 1}])
        self.assertEqual(respuesta.context['regiones'], [{'nombre': 'Lima', 'total': 1}])

        historico = respuesta.context['mtpe_historico']
        self.assertEqual(historico['total_avisos'], 1)
        self.assertEqual(historico['total_vacantes'], 10)
        self.assertContains(respuesta, 'Análisis Histórico Oficial')
        self.assertContains(respuesta, 'asistente de ventas')
        self.assertContains(respuesta, 'atender mostrador comercial')

    def test_mtpe_maneja_error_http_y_usa_limite_1000_por_defecto(self):
        from core.management.commands.scrapear import FUENTES
        self.assertEqual(FUENTES['mtpe'][2], 1000)

        with patch('core.scraper.requests.get') as solicitar:
            resp = requests.Response()
            resp.status_code = 418
            solicitar.return_value = resp
            with self.assertRaisesMessage(CommandError, 'HTTP 418'):
                call_command('scrapear', fuente='mtpe')

        self.assertFalse(FuenteDato.objects.exists())
        self.assertFalse(OfertaLaboral.objects.exists())


class ONGForgeTestCase(TestCase):
    HTML_IMPACTO = """
    <html><body>
        <a href="/api/download?url=https%3A%2F%2Fforge-site.cdn.prismic.io%2Fforge-site%2FBalances2025.zip">Balances</a>
        <a href="/api/download?url=https%3A%2F%2Fforge-site.cdn.prismic.io%2Fforge-site%2FFCDUDGS1TDIhoVJW_Rendiciondecuentas2026ESREGIONALbaja.pdf&filename=Informe.pdf">Informe 2025 (PDF)</a>
    </body></html>
    """
    TEXTO_PDF_VALIDO = """
    Impacto 2025. Informe de resultados 2025.
    IMPACTO TOTAL ANUAL 641.882 jóvenes alcanzados.
    145.352 jóvenes que completaron las experiencias on-demand.
    Distribución por tipo de habilidades desarrolladas Experiencias On-Demand
    61,6% 1,1% Gestión de recursos (dinero/tiempo) Entrenamiento laboral
    36,8% Autoconocimiento 0,5% Emprendedorismo
    El "silencio" digital: El 71,4% de los jóvenes no menciona herramientas tecnológicas específicas.
    LinkedIn, el gran ausente: Casi el 73% de los perfiles omiten esta red.
    1.002 enviaron sus currículums. jóvenes de Latam.
    """

    def _mock_requests_forge(self, html=None):
        resp_html = MagicMock(status_code=200, text=html or self.HTML_IMPACTO)
        resp_html.raise_for_status.return_value = None
        resp_pdf = MagicMock(status_code=200, content=b'%PDF-1.4 mock')
        resp_pdf.raise_for_status.return_value = None
        return [resp_html, resp_pdf]

    def test_forge_importa_indicadores_asocia_competencias_y_deduplica(self):
        pagina_mock = MagicMock()
        pagina_mock.extract_text.return_value = self.TEXTO_PDF_VALIDO

        with patch('core.scraper.requests.get', side_effect=self._mock_requests_forge() * 2), \
             patch('core.scraper.PdfReader') as lector_mock:
            lector_mock.return_value.pages = [pagina_mock]
            call_command('scrapear', fuente='forge')
            self.assertEqual(IndicadorEmpleabilidadONG.objects.count(), 9)
            call_command('scrapear', fuente='forge')

        self.assertEqual(IndicadorEmpleabilidadONG.objects.count(), 9)
        self.assertEqual(OfertaLaboral.objects.count(), 0)
        fuente = FuenteDato.objects.get()
        self.assertEqual(fuente.nombre, 'Fundación Forge')
        self.assertEqual(fuente.tipo, 'ONG')

        silencio = IndicadorEmpleabilidadONG.objects.get(clave='brecha_silencio_digital')
        self.assertEqual(silencio.anio, 2025)
        self.assertEqual(silencio.valor_numerico, Decimal('71.40'))
        self.assertIn('Latinoamérica', silencio.ambito)
        self.assertTrue(silencio.competencias.filter(nombre='Python').exists())
        self.assertTrue(silencio.competencias.filter(nombre='Excel').exists())

    def test_forge_falla_si_formato_cambia_sin_guardar_datos_parciales(self):
        pagina_incompleta = MagicMock()
        pagina_incompleta.extract_text.return_value = 'Informe de resultados 2025 sin cifras esperadas.'

        with patch('core.scraper.requests.get', side_effect=self._mock_requests_forge()), \
             patch('core.scraper.PdfReader') as lector_mock:
            lector_mock.return_value.pages = [pagina_incompleta]
            with self.assertRaisesMessage(CommandError, 'No se pudo verificar'):
                call_command('scrapear', fuente='forge')

        self.assertFalse(IndicadorEmpleabilidadONG.objects.exists())
        self.assertFalse(FuenteDato.objects.exists())

    def test_dashboard_muestra_seccion_ong_separada_de_vigentes_y_mtpe(self):
        fuente_gob = FuenteDato.objects.create(nombre='Get on Board', url_base='https://www.getonbrd.com', tipo='Privada')
        OfertaLaboral.objects.create(titulo='Dev Python', region='Lima', fuente=fuente_gob, es_historica=False)

        fuente_mtpe = FuenteDato.objects.create(nombre='MTPE Datos Abiertos', url_base='https://www.datosabiertos.gob.pe', tipo='Oficial')
        OfertaLaboral.objects.create(titulo='Asistente', region='Piura', vacantes=5, fuente=fuente_mtpe, es_historica=True, codigo_externo='77')

        fuente_ong = FuenteDato.objects.create(nombre='Fundación Forge', url_base='https://fforge.org', tipo='ONG')
        poblar_catalogo_competencias()
        ind = IndicadorEmpleabilidadONG.objects.create(
            fuente=fuente_ong,
            clave='brecha_silencio_digital',
            anio=2025,
            titulo='Jóvenes sin herramientas tecnológicas en CV',
            categoria='BRECHA_CV',
            valor_numerico=Decimal('71.40'),
            unidad='%',
            ambito='Latinoamérica (incluye Perú)',
            descripcion='Indicador real de brecha digital.',
            url_documento='https://fforge.org/impacto/',
        )
        ind.competencias.add(Competencia.objects.get(nombre='Python'))

        respuesta = self.client.get('/dashboard/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['estadisticas'][0]['total'], 1)
        self.assertEqual(respuesta.context['mtpe_historico']['total_avisos'], 1)
        self.assertIsNotNone(respuesta.context['ong_indicadores'])
        self.assertContains(respuesta, 'Fuente ONG')
        self.assertContains(respuesta, 'Fundación Forge')
        self.assertContains(respuesta, '71.40%')
        self.assertContains(respuesta, 'Latinoamérica (incluye Perú)')
