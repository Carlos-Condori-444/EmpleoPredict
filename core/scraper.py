import re
from datetime import datetime, timedelta, timezone as dt_timezone
from html import unescape
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import FuenteDato, OfertaLaboral, PerfilProfesional, UsuarioCompetencia
from .utils import extraer_competencias_del_texto

URL_BASE = 'https://pe.computrabajo.com'
SITIO_ARBEITNOW = 'https://www.arbeitnow.com'
URL_ARBEITNOW = f'{SITIO_ARBEITNOW}/api/job-board-api'
SITIO_REMOTIVE = 'https://remotive.com'
URL_REMOTIVE = f'{SITIO_REMOTIVE}/api/remote-jobs'

HEADERS_NAVEGADOR = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'es-PE,es;q=0.9,en;q=0.8',
}

PALABRAS_VACIAS = {
    'de', 'del', 'la', 'las', 'el', 'los', 'en', 'y', 'o', 'para', 'con', 'por', 'sin', 'a',
}

MAPA_SINONIMOS_SECTOR = {
    'derecho': ['abogado', 'legal'],
    'penal': ['abogado', 'derecho'],
    'juridico': ['derecho', 'abogado'],
    'salud': ['medico', 'enfermeria'],
    'medicina': ['medico', 'salud'],
    'enfermeria': ['enfermera', 'salud'],
    'educacion': ['docente', 'profesor'],
    'docente': ['educacion', 'profesor'],
    'administracion': ['administrador', 'asistente administrativo'],
    'contabilidad': ['contador', 'finanzas'],
    'marketing': ['comunicaciones', 'marketing digital'],
    'ingenieria': ['ingeniero'],
}


class ErrorScraping(Exception):
    """La fuente no devolvió resultados que se puedan importar."""


def _texto(tarjeta, selector):
    elemento = tarjeta.select_one(selector)
    return elemento.get_text(' ', strip=True) if elemento is not None else ''


def _parsear_fecha_relativa_es(texto):
    limpio = (texto or '').strip().lower()
    if not limpio:
        return None
    ahora = timezone.now()
    if 'hoy' in limpio or 'minuto' in limpio or 'hora' in limpio or 'momento' in limpio:
        return ahora
    if 'ayer' in limpio:
        return ahora - timedelta(days=1)
    match = re.search(r'hace\s+(\d+)\s+(día|dias|días|semana|semanas|mes|meses)', limpio)
    if not match:
        return None
    cantidad = int(match.group(1))
    unidad = match.group(2)
    if 'día' in unidad or 'dia' in unidad:
        return ahora - timedelta(days=cantidad)
    if 'semana' in unidad:
        return ahora - timedelta(days=cantidad * 7)
    if 'mes' in unidad:
        return ahora - timedelta(days=cantidad * 30)
    return None


def extraer_ofertas(html, dias_max=None):
    """Lee los campos publicados en las tarjetas de la página de resultados."""
    pagina = BeautifulSoup(html, 'html.parser')
    ofertas = []
    for tarjeta in pagina.select('article.box_offer'):
        enlace = tarjeta.select_one('h2 a, a.js-o-link')
        titulo = enlace.get_text(' ', strip=True) if enlace is not None else _texto(tarjeta, 'h2')
        if not titulo:
            continue

        fecha_pub = _parsear_fecha_relativa_es(_texto(tarjeta, 'p.fs13.fc_aux, span.fc_aux'))
        if dias_max is not None and not _es_reciente(fecha_pub, dias_max):
            continue

        href = (enlace.get('href') or '').strip() if enlace is not None else ''
        url_oferta = None
        if href:
            url_oferta = f'{URL_BASE}{href}' if href.startswith('/') else href
            url_oferta = url_oferta[:500]

        empresa = _texto(tarjeta, '[itemprop="hiringOrganization"] [itemprop="name"], a[href*="/empresa/"], .box_offer_company')
        ubicacion = _texto(tarjeta, '[itemprop="addressRegion"], .box_offer_location')
        if not ubicacion:
            parrafo = tarjeta.select_one('p.fs16.fc_base')
            if parrafo is not None:
                fragmentos = [texto.strip() for texto in parrafo.stripped_strings]
                if fragmentos:
                    ubicacion = fragmentos[-1]

        region = re.split(r'\s*,\s*|\s+-\s+', ubicacion)[-1].strip()
        descripcion = _texto(tarjeta, '[itemprop="description"], .box_offer_description')
        ofertas.append({
            'titulo': titulo[:200],
            'empresa': empresa[:150] or None,
            'region': region[:100] or None,
            'descripcion': descripcion or None,
            'url_oferta': url_oferta,
            'fecha_publicacion': fecha_pub,
        })
    return ofertas


def scrapear_computrabajo(palabra_clave='python', limite=None, dias_max=None, usar_headers=False):
    """Importa una página de resultados y devuelve el número de ofertas nuevas."""
    termino = '-'.join(palabra_clave.split()).lower()
    if not termino:
        raise ErrorScraping('Ingresa una palabra clave.')
    url = f'{URL_BASE}/trabajo-de-{quote(termino, safe="")}'

    try:
        kwargs = {'timeout': 15}
        if usar_headers:
            kwargs['headers'] = HEADERS_NAVEGADOR
        respuesta = requests.get(url, **kwargs)
        respuesta.raise_for_status()
    except requests.HTTPError as error:
        codigo = error.response.status_code
        if codigo in (401, 403, 429):
            raise ErrorScraping(f'Computrabajo restringió el acceso (HTTP {codigo}).') from error
        raise ErrorScraping(f'Computrabajo respondió con HTTP {codigo}.') from error
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudo conectar con Computrabajo: {error}') from error

    ofertas = extraer_ofertas(respuesta.text, dias_max=dias_max)
    if not ofertas:
        if re.search(r'not a robot|captcha|javascript is disabled', respuesta.text, re.IGNORECASE):
            raise ErrorScraping('Computrabajo devolvió una verificación de navegador.')
        raise ErrorScraping('No se encontraron tarjetas de ofertas. Verifica el término o el HTML de la fuente.')

    if limite is not None and limite > 0:
        ofertas = ofertas[:limite]

    return _guardar_ofertas('Computrabajo', URL_BASE, ofertas)


def _es_reciente(fecha_pub, dias_max=30):
    if fecha_pub is None or dias_max is None:
        return True
    limite_fecha = timezone.now() - timedelta(days=dias_max)
    return fecha_pub >= limite_fecha


def _parsear_fecha_unix(valor):
    if isinstance(valor, (int, float)) and valor > 0:
        return datetime.fromtimestamp(valor, tz=dt_timezone.utc)
    return None


def _parsear_fecha_iso(valor):
    if not valor or not isinstance(valor, str):
        return None
    try:
        dt = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, dt_timezone.utc)
        return dt
    except ValueError:
        return None


def importar_arbeitnow(palabra_clave='python', limite=10, dias_max=30):
    """Importa coincidencias recientes de la primera página de la API pública."""
    termino = palabra_clave.strip().casefold()
    if not termino:
        raise ErrorScraping('Ingresa una palabra clave.')
    if limite < 1:
        raise ErrorScraping('El límite debe ser mayor que cero.')

    try:
        respuesta = requests.get(URL_ARBEITNOW, timeout=15)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudieron consultar las ofertas de Arbeitnow: {error}') from error

    if not isinstance(datos, dict) or not isinstance(datos.get('data'), list):
        raise ErrorScraping('La API de Arbeitnow devolvió un formato inesperado.')

    ofertas = []
    for fila in datos['data']:
        if not isinstance(fila, dict):
            continue
        titulo = (fila.get('title') or '').strip()
        if not titulo:
            continue
        fecha_pub = _parsear_fecha_unix(fila.get('created_at'))
        if not _es_reciente(fecha_pub, dias_max):
            continue
        descripcion = BeautifulSoup(unescape(fila.get('description') or ''), 'html.parser').get_text(' ', strip=True)
        if termino not in f'{titulo} {descripcion}'.casefold():
            continue
        url_oferta = (fila.get('url') or '').strip()[:500] or None
        ofertas.append({
            'titulo': titulo[:200],
            'empresa': (fila.get('company_name') or '').strip()[:150] or None,
            'region': (fila.get('location') or '').strip()[:100] or None,
            'descripcion': descripcion or None,
            'url_oferta': url_oferta,
            'fecha_publicacion': fecha_pub,
        })
        if len(ofertas) == limite:
            break

    return _guardar_ofertas('Arbeitnow', SITIO_ARBEITNOW, ofertas)


def importar_remotive(palabra_clave='python', limite=10, dias_max=30):
    """Importa ofertas remotas recientes desde la API pública gratuita de Remotive."""
    termino = palabra_clave.strip()
    if not termino:
        raise ErrorScraping('Ingresa una palabra clave.')
    if limite < 1:
        raise ErrorScraping('El límite debe ser mayor que cero.')

    try:
        respuesta = requests.get(
            URL_REMOTIVE,
            params={'search': termino, 'limit': max(limite * 2, 20)},
            timeout=15,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudieron consultar las ofertas de Remotive: {error}') from error

    if not isinstance(datos, dict) or not isinstance(datos.get('jobs'), list):
        raise ErrorScraping('La API de Remotive devolvió un formato inesperado.')

    ofertas = []
    for fila in datos['jobs']:
        if not isinstance(fila, dict):
            continue
        titulo = (fila.get('title') or '').strip()
        if not titulo:
            continue
        fecha_pub = _parsear_fecha_iso(fila.get('publication_date'))
        if not _es_reciente(fecha_pub, dias_max):
            continue
        descripcion = BeautifulSoup(unescape(fila.get('description') or ''), 'html.parser').get_text(' ', strip=True)
        ofertas.append({
            'titulo': titulo[:200],
            'empresa': (fila.get('company_name') or '').strip()[:150] or None,
            'region': (fila.get('candidate_required_location') or 'Remoto').strip()[:100] or None,
            'descripcion': descripcion or None,
            'url_oferta': (fila.get('url') or '').strip()[:500] or None,
            'fecha_publicacion': fecha_pub,
        })
        if len(ofertas) == limite:
            break

    return _guardar_ofertas('Remotive', SITIO_REMOTIVE, ofertas)


def obtener_terminos_busqueda_usuario(usuario):
    """Construye hasta 4 términos multisectoriales según puesto objetivo, título, área y competencias."""
    terminos = []
    vistos = set()

    def _agregar(texto):
        limpio = (texto or '').strip()
        clave = limpio.casefold()
        if limpio and clave not in vistos:
            vistos.add(clave)
            terminos.append(limpio)

    perfil = PerfilProfesional.objects.filter(usuario=usuario).first()
    textos_perfil = []
    if perfil:
        for campo in (perfil.puesto_objetivo, perfil.titulo_profesional, perfil.area_profesional):
            if campo and campo.strip():
                _agregar(campo)
                textos_perfil.append(campo)

    for texto in textos_perfil:
        palabras = [p for p in re.findall(r'[a-zA-ZáéíóúñÁÉÍÓÚÑ]+', texto.lower()) if len(p) > 3 and p not in PALABRAS_VACIAS]
        if len(palabras) > 1:
            _agregar(palabras[0])
        for palabra in palabras:
            normalizada = palabra.translate(str.maketrans('áéíóú', 'aeiou'))
            for sinonimo in MAPA_SINONIMOS_SECTOR.get(normalizada, []):
                _agregar(sinonimo)

    competencias_tecnicas = (
        UsuarioCompetencia.objects.filter(usuario=usuario, competencia__tipo='TECNICA')
        .select_related('competencia')
        .order_by('-anios_experiencia', 'competencia__nombre')
    )
    for uc in competencias_tecnicas:
        _agregar(uc.competencia.nombre)
        if len(terminos) >= 4:
            break

    if not terminos:
        competencias_todas = (
            UsuarioCompetencia.objects.filter(usuario=usuario)
            .select_related('competencia')
            .order_by('-anios_experiencia', 'competencia__nombre')
        )
        for uc in competencias_todas:
            _agregar(uc.competencia.nombre)
            if len(terminos) >= 2:
                break

    return terminos[:4]


def recomendar_ofertas_para_usuario(usuario, limite=10, dias_max=30):
    """Extrae en tiempo real ofertas recientes multisectoriales acordes al perfil del usuario."""
    terminos = obtener_terminos_busqueda_usuario(usuario)
    if not terminos:
        return {
            'nuevas': 0,
            'terminos': [],
            'fuentes_ok': [],
            'errores': ['Completa tu puesto objetivo o agrega competencias para buscar recomendaciones.'],
        }

    nuevas = 0
    fuentes_ok = set()
    errores = []

    for termino in terminos:
        for nombre_fuente, fn in (
            ('Computrabajo', lambda t=termino: scrapear_computrabajo(t, limite=limite, dias_max=dias_max, usar_headers=True)),
            ('Arbeitnow', lambda t=termino: importar_arbeitnow(t, limite=limite, dias_max=dias_max)),
            ('Remotive', lambda t=termino: importar_remotive(t, limite=limite, dias_max=dias_max)),
        ):
            try:
                nuevas += fn()
                fuentes_ok.add(nombre_fuente)
            except ErrorScraping as error:
                errores.append(f'{nombre_fuente}: {error}')

    return {
        'nuevas': nuevas,
        'terminos': terminos,
        'fuentes_ok': sorted(fuentes_ok),
        'errores': errores,
    }


def _guardar_ofertas(nombre, url_base, ofertas):
    if not ofertas:
        return 0

    with transaction.atomic():
        fuente = FuenteDato.objects.filter(url_base=url_base).order_by('pk').first()
        if fuente is None:
            fuente = FuenteDato.objects.create(nombre=nombre, url_base=url_base, tipo='Privada')
        nuevas = 0
        for datos in ofertas:
            empresa = Q(empresa__iexact=datos['empresa']) if datos['empresa'] else Q(empresa__isnull=True)
            region = Q(region__iexact=datos['region']) if datos['region'] else Q(region__isnull=True)
            if OfertaLaboral.objects.filter(empresa, region, fuente=fuente, titulo__iexact=datos['titulo']).exists():
                continue

            oferta = OfertaLaboral.objects.create(fuente=fuente, **datos)
            texto = f"{oferta.titulo} {oferta.descripcion or ''}"
            oferta.competencias.set(extraer_competencias_del_texto(texto))
            nuevas += 1

        fuente.ultima_ejecucion = timezone.now()
        fuente.save(update_fields=['ultima_ejecucion'])

    return nuevas
