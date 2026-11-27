from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Competencia,
    FuenteDato,
    OfertaLaboral,
    PerfilProfesional,
    Reserva,
    ServicioCapacitacion,
    UsuarioCompetencia,
)


class ServiciosReservasTestCase(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='ana_abogada', password='ClaveSegura2026!')
        self.user_b = User.objects.create_user(username='luis_otro', password='ClaveSegura2026!')
        PerfilProfesional.objects.filter(usuario=self.user_a).update(
            puesto_objetivo='Derecho Penal',
            area_profesional='Derecho',
        )

        self.comp_redaccion = Competencia.objects.create(
            nombre='Redacción Jurídica', tipo='TECNICA', categoria='Legal'
        )
        self.comp_python = Competencia.objects.create(
            nombre='Python', tipo='TECNICA', categoria='Tecnología'
        )
        self.comp_excel = Competencia.objects.create(
            nombre='Excel', tipo='TECNICA', categoria='Tecnología'
        )
        self.comp_salud = Competencia.objects.create(
            nombre='Primeros Auxilios', tipo='TECNICA', categoria='Salud'
        )
        self.comp_oficios = Competencia.objects.create(
            nombre='Electricidad Básica', tipo='TECNICA', categoria='Oficios'
        )

        self.taller_derecho = ServicioCapacitacion.objects.create(
            nombre='Taller de Redacción Jurídica',
            descripcion='Redacción de escritos y demandas.',
            categoria='DERECHO',
            proveedor='EmpleoPredict',
            duracion='6 horas',
            modalidad='EN_VIVO',
            capacidad_maxima=2,
            precio=45,
            otorga_certificado=True,
            es_externo=False,
            activo=True,
        )
        self.taller_derecho.competencias.add(self.comp_redaccion)

        self.curso_externo_ti = ServicioCapacitacion.objects.create(
            nombre='Python Essentials',
            descripcion='Curso introductorio gratuito.',
            categoria='TECNOLOGIA',
            proveedor='Cisco Networking Academy',
            duracion='30 horas',
            modalidad='VIRTUAL',
            capacidad_maxima=1,
            precio=0,
            otorga_certificado=True,
            es_externo=True,
            url_externa='https://www.netacad.com/',
            activo=True,
        )
        self.curso_externo_ti.competencias.add(self.comp_python)

        self.curso_excel = ServicioCapacitacion.objects.create(
            nombre='Excel para Oficina',
            descripcion='Hojas de cálculo transversales.',
            categoria='ADMINISTRACION',
            proveedor='EmpleoPredict',
            duracion='8 horas',
            modalidad='VIRTUAL',
            capacidad_maxima=1,
            precio=0,
            otorga_certificado=False,
            es_externo=False,
            activo=True,
        )
        self.curso_excel.competencias.add(self.comp_excel)

        self.servicio_inactivo = ServicioCapacitacion.objects.create(
            nombre='Curso Oculto',
            descripcion='No debe mostrarse.',
            categoria='SALUD',
            activo=False,
        )

    def test_catalogo_filtros_y_ocultamiento_inactivos(self):
        resp = self.client.get('/servicios/')
        html = resp.content.decode()
        self.assertIn('Taller de Redacción Jurídica', html)
        self.assertIn('Python Essentials', html)
        self.assertNotIn('Curso Oculto', html)

        resp_gratis = self.client.get('/servicios/?precio=gratis&certificado=1')
        html_g = resp_gratis.content.decode()
        self.assertIn('Python Essentials', html_g)
        self.assertNotIn('Taller de Redacción Jurídica', html_g)
        self.assertNotIn('Excel para Oficina', html_g)

        resp_cat = self.client.get('/servicios/?categoria=DERECHO&modalidad=EN_VIVO')
        html_c = resp_cat.content.decode()
        self.assertIn('Taller de Redacción Jurídica', html_c)
        self.assertNotIn('Python Essentials', html_c)

    def test_curso_externo_no_permite_reserva_interna(self):
        self.client.force_login(self.user_a)
        det = self.client.get(f'/servicios/{self.curso_externo_ti.pk}/').content.decode()
        self.assertIn('Cisco Networking Academy', det)
        self.assertIn('https://www.netacad.com/', det)

        futuro = (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(f'/servicios/{self.curso_externo_ti.pk}/reservar/', {'fecha_reserva': futuro})
        self.assertRedirects(resp, f'/servicios/{self.curso_externo_ti.pk}/')
        self.assertFalse(Reserva.objects.filter(servicio=self.curso_externo_ti).exists())

    def test_reserva_cupos_duplicado_fecha_pasada_y_cancelacion(self):
        self.client.force_login(self.user_a)

        pasado = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        self.client.post(f'/servicios/{self.curso_excel.pk}/reservar/', {'fecha_reserva': pasado})
        self.assertFalse(Reserva.objects.filter(usuario=self.user_a).exists())

        futuro = (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        resp_ok = self.client.post(f'/servicios/{self.curso_excel.pk}/reservar/', {'fecha_reserva': futuro})
        self.assertRedirects(resp_ok, '/mis-reservas/')
        self.curso_excel.refresh_from_db()
        self.assertEqual(self.curso_excel.cupos_disponibles, 0)

        # Duplicado activo del mismo usuario
        resp_dup = self.client.post(f'/servicios/{self.curso_excel.pk}/reservar/', {'fecha_reserva': futuro})
        self.assertRedirects(resp_dup, '/mis-reservas/')
        self.assertEqual(Reserva.objects.filter(usuario=self.user_a, servicio=self.curso_excel).count(), 1)

        # Otro usuario no puede reservar cuando cupos == 0
        self.client.force_login(self.user_b)
        resp_lleno = self.client.post(f'/servicios/{self.curso_excel.pk}/reservar/', {'fecha_reserva': futuro})
        self.assertRedirects(resp_lleno, f'/servicios/{self.curso_excel.pk}/')
        self.assertFalse(Reserva.objects.filter(usuario=self.user_b).exists())

        # Usuario B no puede cancelar reserva de Usuario A
        reserva_a = Reserva.objects.get(usuario=self.user_a, servicio=self.curso_excel)
        resp_seg = self.client.post(f'/mis-reservas/{reserva_a.pk}/cancelar/')
        self.assertEqual(resp_seg.status_code, 404)

        # Usuario A cancela y libera el cupo
        self.client.force_login(self.user_a)
        resp_cancel = self.client.post(f'/mis-reservas/{reserva_a.pk}/cancelar/')
        self.assertRedirects(resp_cancel, '/mis-reservas/')
        reserva_a.refresh_from_db()
        self.assertEqual(reserva_a.estado, 'Cancelada')
        self.assertEqual(self.curso_excel.cupos_disponibles, 1)

    def test_recomendaciones_multisectoriales_e_integracion_dashboard(self):
        fuente = FuenteDato.objects.create(nombre='Computrabajo', url_base='https://pe.computrabajo.com')
        oferta_legal = OfertaLaboral.objects.create(
            titulo='Abogado Penalista', descripcion='Redacción jurídica', fuente=fuente
        )
        oferta_legal.competencias.add(self.comp_redaccion)

        self.client.force_login(self.user_a)
        dash_html = self.client.get('/dashboard/').content.decode()
        self.assertIn('/servicios/?categoria=DERECHO', dash_html)

        serv_html = self.client.get('/servicios/').content.decode()
        self.assertIn('Recomendados para tu perfil y brechas', serv_html)
        self.assertIn('Refuerza: Redacción Jurídica', serv_html)

        # Verificar otros sectores (Salud, Educación, Contabilidad, Oficios, Sistemas)
        taller_salud = ServicioCapacitacion.objects.create(
            nombre='Primeros Auxilios Clínicos', descripcion='Atención inicial', categoria='SALUD', activo=True
        )
        taller_salud.competencias.add(self.comp_salud)
        taller_oficio = ServicioCapacitacion.objects.create(
            nombre='Instalaciones Eléctricas', descripcion='Práctica domiciliaria', categoria='OFICIOS', activo=True
        )
        taller_oficio.competencias.add(self.comp_oficios)

        for uname, puesto, area, esperado in [
            ('salud_u', 'Enfermería', 'Salud', 'Primeros Auxilios Clínicos'),
            ('oficio_u', 'Electricista', 'Oficios', 'Instalaciones Eléctricas'),
            ('dev_u', 'Desarrollador Python', 'Tecnología', 'Python Essentials'),
        ]:
            u = User.objects.create_user(username=uname, password='ClaveSegura2026!')
            PerfilProfesional.objects.filter(usuario=u).update(puesto_objetivo=puesto, area_profesional=area)
            self.client.force_login(u)
            html_u = self.client.get('/servicios/').content.decode()
            self.assertIn(esperado, html_u)
