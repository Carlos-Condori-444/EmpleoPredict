from django.core.management.base import BaseCommand, CommandError

from core.scraper import ErrorScraping, scrapear_computrabajo


class Command(BaseCommand):
    help = 'Extrae ofertas laborales públicas de Computrabajo Perú'

    def add_arguments(self, parser):
        parser.add_argument('--keyword', default='python', help='Palabra clave a buscar')

    def handle(self, *args, **options):
        keyword = options['keyword']
        self.stdout.write(f'Buscando ofertas para {keyword}...')
        try:
            nuevas = scrapear_computrabajo(keyword)
        except ErrorScraping as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(f'Se importaron {nuevas} ofertas nuevas de Computrabajo.'))
