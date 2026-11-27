from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import Competencia, FuenteDato, OfertaLaboral, PerfilProfesional, UsuarioCompetencia
from core.scraper import obtener_terminos_busqueda_usuario, recomendar_ofertas_para_usuario, scrapear_computrabajo
from core.utils import extraer_competencias_del_texto


class MultisectorialRecomendadorTestCase(TestCase):
    def setUp(self):
        self.fuente = FuenteDato.objects.create(nombre='Computrabajo', url_base='https://pe.computrabajo.com')
        self.comp_devops = Competencia.objects.create(nombre='DevOps', tipo='TECNICA')
        self.comp_python = Competencia.objects.create(nombre='Python', tipo='TECNICA')
        self.comp_equipo = Competencia.objects.create(nombre='Trabajo en Equipo', tipo='BLANDA')
        self.comp_litigacion = Competencia.objects.create(nombre='Litigación Oral', tipo='TECNICA')

        self.oferta_tech = OfertaLaboral.objects.create(
            titulo='Ingeniero DevOps Python',
            descripcion='Buscamos DevOps con Python y trabajo en equipo.',
            region='Lima',
            fuente=self.fuente,
        )
        self.oferta_tech.competencias.add(self.comp_devops, self.comp_python, self.comp_equipo)

        self.oferta_derecho = OfertaLaboral.objects.create(
            titulo='Abogado de Derecho Penal',
            descripcion='Estudio jurídico requiere abogado penalista para litigación.',
            region='Lima',
            fuente=self.fuente,
        )
        self.oferta_derecho.competencias.add(self.comp_litigacion, self.comp_equipo)

        self.oferta_salud = OfertaLaboral.objects.create(
            titulo='Licenciada en Enfermería',
            descripcion='Clínica busca personal de salud y enfermería.',
            region='Arequipa',
            fuente=self.fuente,
        )
        self.oferta_edu = OfertaLaboral.objects.create(
            titulo='Docente de Educación Secundaria',
            descripcion='Colegio requiere profesor de educación.',
            region='Cusco',
            fuente=self.fuente,
        )
        self.oferta_admin = OfertaLaboral.objects.create(
            titulo='Asistente de Administración y Contabilidad',
            descripcion='Empresa requiere apoyo en administración y finanzas.',
            region='Lima',
            fuente=self.fuente,
        )

    def _crear_usuario_con_perfil(self, username, puesto, area='', comp_blanda=True, comp_tecnica=None):
        user = User.objects.create_user(username=username, password='ClaveSegura2026!')
        PerfilProfesional.objects.filter(usuario=user).update(puesto_objetivo=puesto, area_profesional=area)
        if comp_blanda:
            UsuarioCompetencia.objects.create(usuario=user, competencia=self.comp_equipo, nivel='INTERMEDIO')
        if comp_tecnica:
            UsuarioCompetencia.objects.create(usuario=user, competencia=comp_tecnica, nivel='AVANZADO')
        return user

    def test_derecho_penal_no_recibe_devops_y_si_recibe_ofertas_juridicas(self):
        abogado = self._crear_usuario_con_perfil('julian', 'Derecho Penal', 'Derecho')
        terminos = obtener_terminos_busqueda_usuario(abogado)
        self.assertIn('Derecho Penal', terminos)
        self.assertTrue(any(t in terminos for t in ('abogado', 'derecho')))

        self.client.force_login(abogado)
        html = self.client.get('/dashboard/').content.decode()
        self.assertIn('Abogado de Derecho Penal', html)
        self.assertNotIn('Ingeniero DevOps Python', html)
        self.assertNotIn('DevOps', html)

    def test_salud_educacion_administracion_y_tecnologia(self):
        casos = [
            ('enfermera', 'Enfermería', 'Salud', 'Licenciada en Enfermería', None),
            ('docente', 'Docente', 'Educación', 'Docente de Educación Secundaria', None),
            ('admin_user', 'Administración', 'Contabilidad', 'Asistente de Administración y Contabilidad', None),
            ('dev_user', 'Desarrollador', 'Tecnología', 'Ingeniero DevOps Python', self.comp_python),
        ]
        for username, puesto, area, titulo_esperado, comp_tec in casos:
            u = self._crear_usuario_con_perfil(username, puesto, area, comp_tecnica=comp_tec)
            self.client.force_login(u)
            html = self.client.get('/dashboard/').content.decode()
            self.assertIn(titulo_esperado, html)

    def test_sin_ofertas_compatibles_informa_claramente_sin_mostrar_otro_sector(self):
        arquitecto = self._crear_usuario_con_perfil('arq', 'Arquitectura Naval', 'Diseño Naval')
        self.client.force_login(arquitecto)
        html = self.client.get('/dashboard/').content.decode()
        self.assertIn('Aún no encontramos ofertas compatibles', html)
        self.assertNotIn('DevOps', html)
        self.assertNotIn('Ingeniero DevOps Python', html)

    def test_recomendar_consulta_computrabajo_con_headers_y_fecha(self):
        abogado = self._crear_usuario_con_perfil('abog_rt', 'Derecho', 'Derecho')
        html_ct = """
        <article class="box_offer">
            <h2><a href="/ofertas-de-trabajo/abogado-penal-123">Abogado Penalista Senior</a></h2>
            <a href="/empresa/estudio">Estudio Jurídico</a>
            <p class="fs13 fc_aux">Hace 2 horas</p>
            <p class="fs16 fc_base"><span>Estudio Jurídico</span><span>Lima</span></p>
        </article>
        """
        with patch('core.scraper.requests.get') as mget:
            def side_effect(url, **kw):
                class R:
                    status_code = 200
                    text = html_ct if 'computrabajo' in url else ''
                    def raise_for_status(self): pass
                    def json(self):
                        return {'data': []} if 'arbeitnow' in url else {'jobs': []}
                return R()
            mget.side_effect = side_effect
            res = recomendar_ofertas_para_usuario(abogado, limite=10, dias_max=30)

        self.assertIn('Computrabajo', res['fuentes_ok'])
        oferta = OfertaLaboral.objects.get(titulo='Abogado Penalista Senior')
        self.assertEqual(oferta.url_oferta, 'https://pe.computrabajo.com/ofertas-de-trabajo/abogado-penal-123')
        self.assertIsNotNone(oferta.fecha_publicacion)

    def test_no_falso_positivo_docker_en_documentos_y_transversal_excel_permitido(self):
        Competencia.objects.filter(nombre='DevOps').update(categoria='Tecnología')
        comp_docker = Competencia.objects.create(nombre='Docker', tipo='TECNICA', categoria='Tecnología')
        comp_excel = Competencia.objects.create(nombre='Excel', tipo='TECNICA', categoria='Tecnología')
        comp_proact = Competencia.objects.create(nombre='Proactividad', tipo='BLANDA', categoria='Habilidades Blandas')

        texto_legal = 'Preparar fundamentos de derecho y documentos de sustento. Persona proactiva.'
        detectadas = extraer_competencias_del_texto(texto_legal)
        self.assertNotIn(comp_docker, detectadas)
        self.assertIn(comp_proact, detectadas)

        self.oferta_derecho.competencias.add(comp_docker, comp_excel)
        abogado = self._crear_usuario_con_perfil('julian_legal', 'Derecho Penal', 'Derecho')
        self.client.force_login(abogado)
        html = self.client.get('/dashboard/').content.decode()
        self.assertNotIn('Docker', html)
        self.assertIn('Excel', html)
        self.assertIn('Ya posees:', html)

    def test_oferta_sin_competencias_muestra_aviso_sin_inventar(self):
        enfermera = self._crear_usuario_con_perfil('enf_sin_tags', 'Enfermería', 'Salud', comp_blanda=False)
        self.client.force_login(enfermera)
        html = self.client.get('/dashboard/').content.decode()
        self.assertIn('El resumen no detalla competencias específicas', html)


class ScraperCompatibilidadTestCase(TestCase):
    def test_importa_y_deduplica_por_region(self):
        Competencia.objects.get_or_create(nombre='Python', tipo='TECNICA')
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
