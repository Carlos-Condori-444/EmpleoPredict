import csv
import io
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pypdf import PdfReader

from .models import Competencia, FuenteDato, IndicadorEmpleabilidadONG, OfertaLaboral
from .utils import extraer_competencias_del_texto, poblar_catalogo_competencias

URL_BASE = 'https://pe.computrabajo.com'
SITIO_ARBEITNOW = 'https://www.arbeitnow.com'
URL_ARBEITNOW = f'{SITIO_ARBEITNOW}/api/job-board-api'
SITIO_GETONBOARD = 'https://www.getonbrd.com'
URL_GETONBOARD = f'{SITIO_GETONBOARD}/api/v0/search/jobs'
SITIO_MTPE = 'https://www.datosabiertos.gob.pe'
URL_MTPE_VACANTES_CSV = f'{SITIO_MTPE}/sites/default/files/Dataset_Vacantes_07.08.2025.csv'
URL_MTPE_COMPETENCIAS_CSV = f'{SITIO_MTPE}/sites/default/files/DataSet_Datos_Competencia_29.04.2025.csv'
SITIO_FORGE = 'https://fforge.org'
URL_FORGE_IMPACTO = f'{SITIO_FORGE}/impacto/'
TAMANO_LOTE_MTPE = 500
PAISES_PERU = {'peru', 'perú'}
MARCADORES_REMOTO = {'remote', 'remoto'}

logger = logging.getLogger(__name__)


class ErrorScraping(Exception):
    """La fuente no devolvió resultados que se puedan importar."""


def _limpiar_html(html_crudo):
    return BeautifulSoup(unescape(html_crudo or ''), 'html.parser').get_text(' ', strip=True)


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

    return _guardar_ofertas('Computrabajo', URL_BASE, ofertas)


def importar_arbeitnow(palabra_clave='python', limite=10):
    """Importa coincidencias de la primera página de la API pública."""
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
        descripcion = _limpiar_html(fila.get('description'))
        if termino not in f'{titulo} {descripcion}'.casefold():
            continue
        ofertas.append({
            'titulo': titulo[:200],
            'empresa': (fila.get('company_name') or '').strip()[:150] or None,
            'region': (fila.get('location') or '').strip()[:100] or None,
            'descripcion': descripcion or None,
        })
        if len(ofertas) == limite:
            break

    return _guardar_ofertas('Arbeitnow', SITIO_ARBEITNOW, ofertas)


def _extraer_empresa_getonboard(atributos):
    compania = atributos.get('company')
    if not isinstance(compania, dict):
        return None
    datos_compania = compania.get('data') or {}
    if not isinstance(datos_compania, dict):
        return None
    nombre = (datos_compania.get('attributes') or {}).get('name') or ''
    return nombre.strip()[:150] or None


def _resolver_ubicacion_peru_getonboard(atributos):
    """Valida si la oferta confirma disponibilidad en Perú y devuelve (region, motivo_rechazo)."""
    ciudades_bloque = atributos.get('location_cities')
    ciudades_data = ciudades_bloque.get('data') if isinstance(ciudades_bloque, dict) else []
    ciudades_peru = []
    ciudades_extranjeras = []
    ciudades_sin_pais = []
    if isinstance(ciudades_data, list):
        for ciudad in ciudades_data:
            if not isinstance(ciudad, dict):
                continue
            ciudad_attr = ciudad.get('attributes')
            if not isinstance(ciudad_attr, dict):
                continue
            nombre = (ciudad_attr.get('name') or '').strip()
            pais = (ciudad_attr.get('country') or '').strip()
            if pais.casefold() in PAISES_PERU:
                ciudades_peru.append(nombre or 'Perú')
            elif pais:
                ciudades_extranjeras.append(f'{nombre} ({pais})' if nombre else pais)
            elif nombre:
                ciudades_sin_pais.append(nombre)

    paises_raw = atributos.get('countries')
    paises = [str(p).strip() for p in paises_raw if str(p).strip()] if isinstance(paises_raw, list) else []
    peru_en_paises = any(p.casefold() in PAISES_PERU for p in paises)
    paises_extranjeros = [
        p for p in paises
        if p.casefold() not in PAISES_PERU and p.casefold() not in MARCADORES_REMOTO
    ]

    tenants_bloque = atributos.get('location_tenants')
    tenants_data = tenants_bloque.get('data') if isinstance(tenants_bloque, dict) else []
    peru_en_tenants = False
    tenants_extranjeros = []
    if isinstance(tenants_data, list):
        for tenant in tenants_data:
            if not isinstance(tenant, dict):
                continue
            tenant_id = str(tenant.get('id') or '').strip()
            tenant_attr = tenant.get('attributes')
            tenant_nombre = str(tenant_attr.get('name') or '').strip() if isinstance(tenant_attr, dict) else ''
            if tenant_id.casefold() in PAISES_PERU or tenant_nombre.casefold() in PAISES_PERU:
                peru_en_tenants = True
            elif tenant_nombre or tenant_id:
                tenants_extranjeros.append(tenant_nombre or tenant_id)

    es_remoto = bool(atributos.get('remote')) or any(p.casefold() in MARCADORES_REMOTO for p in paises)

    if ciudades_peru:
        return ciudades_peru[0][:100], None
    if peru_en_paises:
        return ('Remoto' if es_remoto else 'Perú'), None
    if peru_en_tenants:
        return ('Remoto' if es_remoto else 'Perú'), None

    if es_remoto:
        extranjeros = tenants_extranjeros or paises_extranjeros or ciudades_extranjeras
        if extranjeros:
            destinos = ', '.join(dict.fromkeys(extranjeros))
            return None, f'oferta remota limitada a otros países ({destinos})'
        return None, 'oferta remota sin confirmación explícita de Perú en la API'

    extranjeros = ciudades_extranjeras or paises_extranjeros or tenants_extranjeros
    if extranjeros:
        destinos = ', '.join(dict.fromkeys(extranjeros))
        return None, f'ubicación exclusiva fuera de Perú ({destinos})'
    if ciudades_sin_pais:
        ciudades = ', '.join(dict.fromkeys(ciudades_sin_pais))
        return None, f'ubicación ambigua sin país confirmado ({ciudades})'
    return None, 'ubicación ambigua o sin datos de país en la API'


def _extraer_descripcion_getonboard(atributos):
    secciones = [
        _limpiar_html(atributos.get(campo))
        for campo in ('description', 'functions', 'desirable')
    ]
    texto = '\n\n'.join(parte for parte in secciones if parte)
    return texto or None


def importar_getonboard(palabra_clave='peru', limite=10):
    """Importa ofertas de la API pública v0 de Get on Board y devuelve cuántas son nuevas."""
    termino = palabra_clave.strip()
    if not termino:
        raise ErrorScraping('Ingresa una palabra clave.')
    if limite < 1:
        raise ErrorScraping('El límite debe ser mayor que cero.')

    parametros = {
        'query': termino,
        'per_page': min(limite, 100),
        'expand': '["company","location_cities","location_tenants"]',
    }
    cabeceras = {
        'Accept': 'application/json',
        'User-Agent': 'EmpleoPredict/1.0',
    }

    try:
        respuesta = requests.get(URL_GETONBOARD, params=parametros, headers=cabeceras, timeout=15)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.HTTPError as error:
        codigo = error.response.status_code
        if codigo in (401, 403, 429):
            raise ErrorScraping(f'Get on Board restringió el acceso (HTTP {codigo}).') from error
        raise ErrorScraping(f'Get on Board respondió con HTTP {codigo}.') from error
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudieron consultar las ofertas de Get on Board: {error}') from error
    except ValueError as error:
        raise ErrorScraping('La API de Get on Board no devolvió un JSON válido.') from error

    if not isinstance(datos, dict) or not isinstance(datos.get('data'), list):
        raise ErrorScraping('La API de Get on Board devolvió un formato inesperado.')

    ofertas = []
    for fila in datos['data']:
        if not isinstance(fila, dict):
            continue
        atributos = fila.get('attributes')
        if not isinstance(atributos, dict):
            continue
        titulo = (atributos.get('title') or '').strip()
        if not titulo:
            continue

        region, motivo_rechazo = _resolver_ubicacion_peru_getonboard(atributos)
        if motivo_rechazo:
            logger.info('Oferta de Get on Board omitida ("%s"): %s.', titulo, motivo_rechazo)
            continue

        enlaces = fila.get('links') or {}
        url_original = (enlaces.get('public_url') or '').strip()[:500] or None if isinstance(enlaces, dict) else None
        sector = (atributos.get('category_name') or '').strip()[:100] or None

        ofertas.append({
            'titulo': titulo[:200],
            'empresa': _extraer_empresa_getonboard(atributos),
            'region': region,
            'sector': sector,
            'descripcion': _extraer_descripcion_getonboard(atributos),
            'url_original': url_original,
        })
        if len(ofertas) == limite:
            break

    return _guardar_ofertas('Get on Board', SITIO_GETONBOARD, ofertas)


def _parsear_fecha_mtpe(valor):
    texto = (valor or '').strip()
    if len(texto) == 8 and texto.isdigit():
        try:
            return datetime.strptime(texto, '%Y%m%d').date()
        except ValueError:
            return None
    return None


def _formatear_region_mtpe(departamento):
    limpio = ' '.join((departamento or '').split())
    return limpio.title()[:100] or None


def _construir_descripcion_mtpe(fila):
    ubicacion = ', '.join(
        parte for parte in (
            ' '.join((fila.get('PROVINCIA') or '').split()).title(),
            ' '.join((fila.get('DISTRITO') or '').split()).title(),
        ) if parte
    )
    partes = []
    if ubicacion:
        partes.append(f'Ubicación: {ubicacion}')
    sin_exp = (fila.get('SINEXPERIENCIA') or '').strip()
    tiempo_exp = (fila.get('TIEMPOEXPERIENCIA') or '').strip()
    tipo_exp = (fila.get('TIPOTIEMPOEXPERIENCIA') or '').strip()
    if sin_exp.upper() == 'SI':
        partes.append('Experiencia: No requerida')
    elif tiempo_exp:
        partes.append(f'Experiencia: {tiempo_exp} {tipo_exp}'.strip())
    espcd = (fila.get('ESPCD') or '').strip()
    if espcd.upper() == 'SI':
        partes.append('Apto para personas con discapacidad: Sí')
    estado_corte = (fila.get('ACTIVO') or '').strip()
    if estado_corte:
        partes.append(f'Estado histórico en corte MTPE: {estado_corte}')
    return ' | '.join(partes) or None


def _abrir_csv_mtpe(url, nombre_recurso):
    cabeceras = {
        'Accept': 'text/csv,application/octet-stream,*/*',
        'User-Agent': 'EmpleoPredict/1.0',
    }
    try:
        respuesta = requests.get(url, headers=cabeceras, stream=True, timeout=60)
        respuesta.raise_for_status()
    except requests.HTTPError as error:
        codigo = error.response.status_code
        raise ErrorScraping(f'Datos Abiertos MTPE ({nombre_recurso}) respondió con HTTP {codigo}.') from error
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudo descargar el archivo del MTPE ({nombre_recurso}): {error}') from error

    lineas = (linea.decode('utf-8-sig', errors='replace') for linea in respuesta.iter_lines() if linea)
    return respuesta, csv.DictReader(lineas)


def _vincular_competencias_mtpe(pares_aviso_comp):
    """Crea competencias ESCO faltantes y las vincula en lotes sin activarlas para CV."""
    if not pares_aviso_comp:
        return

    existentes = {nombre.casefold(): pk for nombre, pk in Competencia.objects.values_list('nombre', 'pk')}
    nuevas = []
    vistas_nuevas = set()
    for _, nombre_comp in pares_aviso_comp:
        clave = nombre_comp.casefold()
        if clave not in existentes and clave not in vistas_nuevas:
            vistas_nuevas.add(clave)
            nuevas.append(Competencia(
                nombre=nombre_comp,
                tipo='TECNICA',
                categoria='MTPE ESCO',
                es_catalogo_cv=False,
            ))

    if nuevas:
        Competencia.objects.bulk_create(nuevas, batch_size=TAMANO_LOTE_MTPE, ignore_conflicts=True)
        existentes = {nombre.casefold(): pk for nombre, pk in Competencia.objects.values_list('nombre', 'pk')}

    modelo_puente = OfertaLaboral.competencias.through
    relaciones = []
    for oferta_id, nombre_comp in pares_aviso_comp:
        comp_id = existentes.get(nombre_comp.casefold())
        if comp_id is not None:
            relaciones.append(modelo_puente(ofertalaboral_id=oferta_id, competencia_id=comp_id))
        if len(relaciones) >= TAMANO_LOTE_MTPE * 2:
            modelo_puente.objects.bulk_create(relaciones, batch_size=TAMANO_LOTE_MTPE * 2, ignore_conflicts=True)
            relaciones.clear()
    if relaciones:
        modelo_puente.objects.bulk_create(relaciones, batch_size=TAMANO_LOTE_MTPE * 2, ignore_conflicts=True)


def importar_mtpe(palabra_clave='', limite=1000):
    """Importa vacantes históricas del MTPE en streaming y asocia competencias por AVISOID."""
    if limite < 0:
        raise ErrorScraping('El límite no puede ser negativo.')
    termino = (palabra_clave or '').strip().casefold()

    resp_vac, lector_vac = _abrir_csv_mtpe(URL_MTPE_VACANTES_CSV, 'vacantes')
    fuente = None
    avisos_nuevos = set()
    try:
        fuente, _ = FuenteDato.objects.get_or_create(
            url_base=SITIO_MTPE,
            defaults={'nombre': 'MTPE Datos Abiertos', 'tipo': 'Oficial'},
        )
        if fuente.tipo != 'Oficial' or fuente.nombre != 'MTPE Datos Abiertos':
            fuente.nombre = 'MTPE Datos Abiertos'
            fuente.tipo = 'Oficial'
            fuente.save(update_fields=['nombre', 'tipo'])

        existentes = set(
            OfertaLaboral.objects.filter(fuente=fuente, codigo_externo__isnull=False)
            .values_list('codigo_externo', flat=True)
        )
        lote = []
        importadas = 0
        for fila in lector_vac:
            aviso_id = (fila.get('AVISOID') or '').strip()[:100]
            titulo = ' '.join((fila.get('NOMBREAVISO') or '').split())
            if not aviso_id or not titulo or aviso_id in existentes or aviso_id in avisos_nuevos:
                continue

            ocupacion = ' '.join((fila.get('ESCO') or '').split())[:255]
            sector = ' '.join((fila.get('SECTOR') or '').split())[:100]
            departamento = (fila.get('DEPARTAMENTO') or '').strip()
            if termino and termino not in f'{titulo} {ocupacion} {sector} {departamento}'.casefold():
                continue

            vac_raw = (fila.get('VACANTES') or '').strip()
            vacantes = int(vac_raw) if vac_raw.isdigit() and int(vac_raw) > 0 else 1

            lote.append(OfertaLaboral(
                titulo=titulo[:200],
                empresa=None,
                descripcion=_construir_descripcion_mtpe(fila),
                sector=sector or None,
                region=_formatear_region_mtpe(departamento),
                salario=None,
                url_original=None,
                fuente=fuente,
                es_historica=True,
                codigo_externo=aviso_id,
                ocupacion=ocupacion or None,
                vacantes=vacantes,
                fecha_inicio_periodo=_parsear_fecha_mtpe(fila.get('FECHAINICIO')),
                fecha_fin_periodo=_parsear_fecha_mtpe(fila.get('FECHAFIN')),
            ))
            avisos_nuevos.add(aviso_id)
            importadas += 1

            if len(lote) >= TAMANO_LOTE_MTPE:
                OfertaLaboral.objects.bulk_create(lote, batch_size=TAMANO_LOTE_MTPE, ignore_conflicts=True)
                lote.clear()
            if limite and importadas >= limite:
                break

        if lote:
            OfertaLaboral.objects.bulk_create(lote, batch_size=TAMANO_LOTE_MTPE, ignore_conflicts=True)
    finally:
        resp_vac.close()

    if avisos_nuevos:
        mapa_ofertas = {
            codigo: pk
            for codigo, pk in OfertaLaboral.objects.filter(
                fuente=fuente, codigo_externo__isnull=False
            ).values_list('codigo_externo', 'pk')
            if codigo in avisos_nuevos
        }
        if mapa_ofertas:
            resp_comp, lector_comp = _abrir_csv_mtpe(URL_MTPE_COMPETENCIAS_CSV, 'competencias')
            pares = []
            try:
                for fila in lector_comp:
                    aviso_id = (fila.get('AVISOID') or '').strip()[:100]
                    oferta_id = mapa_ofertas.get(aviso_id)
                    if oferta_id is None:
                        continue
                    nombre_comp = ' '.join((fila.get('NOMBRECOMPETENCIA') or '').split())[:200]
                    if nombre_comp:
                        pares.append((oferta_id, nombre_comp))
            finally:
                resp_comp.close()
            _vincular_competencias_mtpe(pares)

    if fuente is not None:
        fuente.ultima_ejecucion = timezone.now()
        fuente.save(update_fields=['ultima_ejecucion'])

    return len(avisos_nuevos)


COMPETENCIAS_INDICADOR_FORGE = {
    'impacto_anual_jovenes': ['Proactividad', 'Adaptabilidad'],
    'experiencias_ondemand': ['Proactividad', 'Gestión del Tiempo'],
    'habilidad_entrenamiento_laboral': ['Comunicación Asertiva', 'Trabajo en Equipo', 'Resolución de Problemas', 'Proactividad'],
    'habilidad_autoconocimiento': ['Adaptabilidad', 'Pensamiento Crítico', 'Liderazgo'],
    'habilidad_gestion_recursos': ['Gestión del Tiempo', 'Administración'],
    'habilidad_emprendedorismo': ['Liderazgo', 'Proactividad', 'Ventas'],
    'brecha_silencio_digital': ['Python', 'Excel', 'SQL', 'Power BI', 'Git'],
    'brecha_sin_linkedin': ['Comunicación Asertiva', 'Marketing Digital'],
    'perfiles_cv_analizados': ['Comunicación Asertiva', 'Resolución de Problemas'],
}


def _parsear_numero_forge(texto):
    limpio = (texto or '').strip().replace('.', '').replace(',', '.')
    try:
        return Decimal(limpio)
    except (InvalidOperation, ValueError) as error:
        raise ErrorScraping(f'No se pudo interpretar el valor numérico "{texto}" en el informe de Fundación Forge.') from error


def _extraer_url_pdf_forge(html):
    pagina = BeautifulSoup(html, 'html.parser')
    candidatos = []
    for enlace in pagina.select('a[href]'):
        href = (enlace.get('href') or '').strip()
        if '.pdf' not in href.casefold() or 'balance' in href.casefold():
            continue
        destino = href
        if '/api/download' in href:
            consulta = parse_qs(urlparse(href).query)
            destino = (consulta.get('url') or [''])[0].strip() or urljoin(URL_FORGE_IMPACTO, href)
        else:
            destino = urljoin(URL_FORGE_IMPACTO, href)
        texto_enlace = enlace.get_text(' ', strip=True).casefold()
        prioridad = 0 if ('informe' in texto_enlace or 'rendicion' in destino.casefold()) else 1
        candidatos.append((prioridad, destino))

    if not candidatos:
        raise ErrorScraping('No se encontró un enlace PDF de informe de impacto en Fundación Forge.')
    candidatos.sort(key=lambda item: item[0])
    return candidatos[0][1]


def _extraer_indicadores_forge(texto_pdf, url_pdf):
    texto = ' '.join((texto_pdf or '').split())
    if not texto:
        raise ErrorScraping('El informe PDF de Fundación Forge no contiene texto legible.')

    match_anio = re.search(r'(?:Impacto|Informe de resultados)\s+(20\d{2})', texto, re.IGNORECASE)
    if not match_anio:
        raise ErrorScraping('No se pudo verificar el año del informe oficial de Fundación Forge.')
    anio = int(match_anio.group(1))

    especificaciones = [
        (
            'impacto_anual_jovenes', 'ALCANCE', 'Jóvenes alcanzados en ciclo anual', 'jóvenes',
            'Latinoamérica (incluye Perú)',
            r'IMPACTO TOTAL ANUAL\s+([\d.]+)\s+j[oó]venes alcanzados',
            'Total anual de jóvenes alcanzados por programas de formación y empleabilidad de Fundación Forge.',
        ),
        (
            'experiencias_ondemand', 'ALCANCE', 'Jóvenes en experiencias digitales on-demand', 'jóvenes',
            'Latinoamérica (incluye Perú)',
            r'([\d.]+)\s+j[oó]venes que completaron las experiencias on-demand',
            'Jóvenes que completaron experiencias digitales de orientación laboral y habilidades en 8 países, incluido Perú.',
        ),
        (
            'habilidad_entrenamiento_laboral', 'HABILIDAD', 'Entrenamiento laboral (habilidades desarrolladas)', '%',
            'Latinoamérica (incluye Perú)',
            r'Experiencias On-Demand\s+(\d+,\d+)%.*?Entrenamiento laboral',
            'Porcentaje de participación en contenidos de entrenamiento para postulación, entrevistas y mejora de CV.',
        ),
        (
            'habilidad_autoconocimiento', 'HABILIDAD', 'Autoconocimiento y habilidades socioemocionales', '%',
            'Latinoamérica (incluye Perú)',
            r'(\d+,\d+)%\s*Autoconocimiento',
            'Porcentaje de participación en módulos de autoconocimiento y desbloqueo socioemocional.',
        ),
        (
            'habilidad_gestion_recursos', 'HABILIDAD', 'Gestión de recursos (dinero y tiempo)', '%',
            'Latinoamérica (incluye Perú)',
            r'(\d+,\d+)%\s*Gesti[oó]n de recursos',
            'Porcentaje de participación en módulos de gestión del tiempo y educación financiera.',
        ),
        (
            'habilidad_emprendedorismo', 'HABILIDAD', 'Emprendedorismo', '%',
            'Latinoamérica (incluye Perú)',
            r'(\d+,\d+)%\s*Emprendedorismo',
            'Porcentaje de participación en módulos de iniciativa emprendedora.',
        ),
        (
            'brecha_silencio_digital', 'BRECHA_CV', 'Jóvenes que no mencionan herramientas tecnológicas en su CV', '%',
            'Latinoamérica (análisis de >1,000 perfiles)',
            r'El\s+["“]?silencio["”]?\s+digital:\s*El\s+(\d+(?:,\d+)?)%\s+de los j[oó]venes no menciona herramientas tecnol[oó]gicas',
            'Brecha detectada al revisar currículums: omitir herramientas tecnológicas específicas reduce visibilidad laboral.',
        ),
        (
            'brecha_sin_linkedin', 'BRECHA_CV', 'Perfiles que omiten enlace a LinkedIn', '%',
            'Latinoamérica (análisis de >1,000 perfiles)',
            r'LinkedIn,\s+el gran ausente:\s*Casi el\s+(\d+(?:,\d+)?)%\s+de los perfiles omiten esta red',
            'Brecha detectada en currículums juveniles que dejan fuera su perfil profesional en LinkedIn.',
        ),
        (
            'perfiles_cv_analizados', 'BRECHA_CV', 'Currículums juveniles revisados con voluntarios de RR.HH.', 'jóvenes',
            'Latinoamérica (10 países)',
            r'([\d.]+)\s+enviaron sus curr[ií]culums\.\s*j[oó]venes de Latam',
            'Muestra de currículums evaluados en la campaña «Se ve tu CV» junto a voluntarios de recursos humanos.',
        ),
    ]

    indicadores = []
    por_clave = {}
    for clave, categoria, titulo, unidad, ambito, patron, descripcion in especificaciones:
        coincidencia = re.search(patron, texto, re.IGNORECASE)
        if not coincidencia:
            raise ErrorScraping(
                f'No se pudo verificar la cifra "{titulo}" en el informe de Fundación Forge (posible cambio de formato).'
            )
        valor = _parsear_numero_forge(coincidencia.group(1))
        por_clave[clave] = valor
        indicadores.append({
            'clave': clave,
            'anio': anio,
            'titulo': titulo,
            'categoria': categoria,
            'valor_numerico': valor,
            'unidad': unidad,
            'ambito': ambito,
            'descripcion': descripcion,
            'url_documento': url_pdf[:500],
        })

    suma_habilidades = (
        por_clave['habilidad_entrenamiento_laboral']
        + por_clave['habilidad_autoconocimiento']
        + por_clave['habilidad_gestion_recursos']
        + por_clave['habilidad_emprendedorismo']
    )
    if abs(suma_habilidades - Decimal('100')) > Decimal('1.0'):
        raise ErrorScraping('La distribución de habilidades del informe de Fundación Forge no suma 100%.')

    return indicadores


def importar_ong_forge(palabra_clave=''):
    """Descarga el informe anual oficial de Fundación Forge y guarda indicadores verificados."""
    cabeceras = {'Accept': 'text/html,application/pdf,*/*', 'User-Agent': 'EmpleoPredict/1.0'}
    try:
        resp_html = requests.get(URL_FORGE_IMPACTO, headers=cabeceras, timeout=20)
        resp_html.raise_for_status()
        url_pdf = _extraer_url_pdf_forge(resp_html.text)

        resp_pdf = requests.get(url_pdf, headers=cabeceras, timeout=30)
        resp_pdf.raise_for_status()
    except requests.HTTPError as error:
        codigo = error.response.status_code
        raise ErrorScraping(f'Fundación Forge respondió con HTTP {codigo}.') from error
    except requests.RequestException as error:
        raise ErrorScraping(f'No se pudo consultar el informe de Fundación Forge: {error}') from error

    try:
        lector = PdfReader(io.BytesIO(resp_pdf.content))
        texto_pdf = ' '.join((pagina.extract_text() or '') for pagina in lector.pages)
    except Exception as error:
        raise ErrorScraping(f'No se pudo leer el archivo PDF de Fundación Forge: {error}') from error

    indicadores = _extraer_indicadores_forge(texto_pdf, url_pdf)
    poblar_catalogo_competencias()
    catalogo = {
        comp.nombre: comp
        for comp in Competencia.objects.filter(es_catalogo_cv=True)
    }

    with transaction.atomic():
        fuente, _ = FuenteDato.objects.get_or_create(
            url_base=SITIO_FORGE,
            defaults={'nombre': 'Fundación Forge', 'tipo': 'ONG'},
        )
        if fuente.tipo != 'ONG' or fuente.nombre != 'Fundación Forge':
            fuente.nombre = 'Fundación Forge'
            fuente.tipo = 'ONG'
            fuente.save(update_fields=['nombre', 'tipo'])

        nuevos = 0
        for datos in indicadores:
            indicador, creado = IndicadorEmpleabilidadONG.objects.get_or_create(
                fuente=fuente,
                anio=datos['anio'],
                clave=datos['clave'],
                defaults=datos,
            )
            if creado:
                nombres_comp = COMPETENCIAS_INDICADOR_FORGE.get(datos['clave'], [])
                indicador.competencias.set([catalogo[n] for n in nombres_comp if n in catalogo])
                nuevos += 1

        fuente.ultima_ejecucion = timezone.now()
        fuente.save(update_fields=['ultima_ejecucion'])

    return nuevos


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
