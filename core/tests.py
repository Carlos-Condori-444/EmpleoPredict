from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Competencia, UsuarioCompetencia, DatosPersonales, DocumentoCV
from core.forms import SubirCVForm
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
