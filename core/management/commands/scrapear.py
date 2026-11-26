from django.core.management.base import BaseCommand, CommandError

from core.scraper import ErrorScraping, importar_arbeitnow, importar_getonboard, importar_mtpe, importar_ong_forge, scrapear_computrabajo

FUENTES = {
    'computrabajo': ('Computrabajo', False, None, 'python', scrapear_computrabajo),
    'arbeitnow': ('Arbeitnow', True, 10, 'python', importar_arbeitnow),
    'getonboard': ('Get on Board', True, 10, 'peru', importar_getonboard),
    'mtpe': ('MTPE Datos Abiertos', True, 1000, '', importar_mtpe),
    'forge': ('Fundación Forge', False, None, '', importar_ong_forge),
}


class Command(BaseCommand):
    help = 'Importa ofertas actuales (Computrabajo, Arbeitnow, Get on Board) o vacantes históricas oficiales (MTPE)'

    def add_arguments(self, parser):
        parser.add_argument('--keyword', default=None, help='Palabra clave a buscar')
        parser.add_argument('--fuente', choices=tuple(FUENTES.keys()), default='computrabajo')
        parser.add_argument('--limite', type=int, help='Máximo de ofertas (10 en APIs, 1000 por defecto en MTPE)')

    def handle(self, *args, **options):
        nombre, soporta_limite, limite_defecto, keyword_defecto, importador = FUENTES[options['fuente']]
        keyword = keyword_defecto if options['keyword'] is None else options['keyword']
        limite = options['limite']
        if not soporta_limite and limite is not None:
            raise CommandError('--limite solo está disponible para Arbeitnow, Get on Board y MTPE.')

        descripcion_busqueda = keyword if keyword else 'todas las ocupaciones'
        self.stdout.write(f'Buscando ofertas para {descripcion_busqueda} en {nombre}...')
        try:
            if soporta_limite:
                nuevas = importador(keyword, limite_defecto if limite is None else limite)
            else:
                nuevas = importador(keyword)
        except ErrorScraping as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(f'Se importaron {nuevas} ofertas nuevas de {nombre}.'))
