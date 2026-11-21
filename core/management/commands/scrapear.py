from django.core.management.base import BaseCommand, CommandError

from core.scraper import ErrorScraping, importar_arbeitnow, scrapear_computrabajo


class Command(BaseCommand):
    help = 'Importa ofertas de Computrabajo Perú o de la API pública de Arbeitnow'

    def add_arguments(self, parser):
        parser.add_argument('--keyword', default='python', help='Palabra clave a buscar')
        parser.add_argument('--fuente', choices=('computrabajo', 'arbeitnow'), default='computrabajo')
        parser.add_argument('--limite', type=int, help='Máximo de coincidencias de Arbeitnow (por defecto, 10)')

    def handle(self, *args, **options):
        keyword = options['keyword']
        es_arbeitnow = options['fuente'] == 'arbeitnow'
        limite = options['limite']
        if not es_arbeitnow and limite is not None:
            raise CommandError('--limite solo está disponible para Arbeitnow.')

        nombre = 'Arbeitnow' if es_arbeitnow else 'Computrabajo'
        self.stdout.write(f'Buscando ofertas para {keyword} en {nombre}...')
        try:
            if es_arbeitnow:
                nuevas = importar_arbeitnow(keyword, 10 if limite is None else limite)
            else:
                nuevas = scrapear_computrabajo(keyword)
        except ErrorScraping as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(f'Se importaron {nuevas} ofertas nuevas de {nombre}.'))
