from unittest.mock import patch

import requests
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Competencia, FuenteDato, OfertaLaboral, ServicioCapacitacion
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

    def test_catalogo_muestra_servicios_y_reserva_inactiva(self):
        self.assertContains(self.client.get('/servicios/'), 'Catálogo de ejemplo')
        ServicioCapacitacion.objects.create(nombre='Curso real', descripcion='Nivel básico', precio=10)
        respuesta = self.client.get('/servicios/')
        self.assertContains(respuesta, 'Curso real')
        self.assertContains(respuesta, 'disabled')
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
