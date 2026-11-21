import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import FuenteDato, OfertaLaboral
from .utils import extraer_competencias_del_texto

URL_BASE = 'https://pe.computrabajo.com'


class ErrorScraping(Exception):
    """La fuente no devolvió resultados que se puedan importar."""


def _texto(tarjeta, selector):
    elemento = tarjeta.select_one(selector)
    return elemento.get_text(' ', strip=True) if elemento is not None else ''


def extraer_ofertas(html):
    """Lee los campos publicados en las tarjetas de la página de resultados."""
    pagina = BeautifulSoup(html, 'html.parser')
    ofertas = []
    for tarjeta in pagina.select('article.box_offer'):
        titulo = _texto(tarjeta, 'h2')
        if not titulo:
            continue

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
        })
    return ofertas


def scrapear_computrabajo(palabra_clave='python'):
    """Importa una página de resultados y devuelve el número de ofertas nuevas."""
    termino = '-'.join(palabra_clave.split()).lower()
    if not termino:
        raise ErrorScraping('Ingresa una palabra clave.')
    url = f'{URL_BASE}/trabajo-de-{quote(termino, safe="")}'

    try:
        respuesta = requests.get(url, timeout=15)
        respuesta.raise_for_status()
    except requests.HTTPError as error:
        codigo = error.response.status_code
        if codigo in (401, 403, 429):
            raise ErrorScraping(f'Computrabajo restringió el acceso (HTTP {codigo}).') from error
        raise ErrorScraping(f'Computrabajo respondió con HTTP {codigo}.') from error
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudo conectar con Computrabajo: {error}') from error

    ofertas = extraer_ofertas(respuesta.text)
    if not ofertas:
        if re.search(r'not a robot|captcha|javascript is disabled', respuesta.text, re.IGNORECASE):
            raise ErrorScraping('Computrabajo devolvió una verificación de navegador.')
        raise ErrorScraping('No se encontraron tarjetas de ofertas. Verifica el término o el HTML de la fuente.')

    with transaction.atomic():
        fuente = FuenteDato.objects.filter(url_base=URL_BASE).order_by('pk').first()
        if fuente is None:
            fuente = FuenteDato.objects.create(nombre='Computrabajo', url_base=URL_BASE, tipo='Privada')
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
