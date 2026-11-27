import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Competencia

class Command(BaseCommand):
    help = 'Carga el catálogo universal de competencias desde un archivo CSV'

    def handle(self, *args, **kwargs):
        ruta_csv = os.path.join(settings.BASE_DIR, 'data', 'competencias_universales.csv')
        
        if not os.path.exists(ruta_csv):
            self.stdout.write(self.style.ERROR(f'No se encontró el archivo en {ruta_csv}'))
            return

        contador = 0
        with open(ruta_csv, mode='r', encoding='utf-8') as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                obj, created = Competencia.objects.get_or_create(
                    nombre=fila['nombre'].strip(),
                    defaults={
                        'tipo': fila['tipo'].strip(),
                        'categoria': fila['categoria'].strip()
                    }
                )
                if created:
                    contador += 1

        self.stdout.write(self.style.SUCCESS(f'¡Éxito! Se cargaron {contador} competencias nuevas desde el CSV.'))