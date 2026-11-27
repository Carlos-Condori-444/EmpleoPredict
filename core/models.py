from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ==========================================
# MÓDULO DE PERFIL (Universal para cualquier carrera)
# ==========================================

class DatosPersonales(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='datos_personales')
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    email_contacto = models.EmailField(blank=True, null=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    pais = models.CharField(max_length=80, blank=True)
    departamento = models.CharField(max_length=100, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)
    linkedin_url = models.URLField(blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    portafolio_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"

class PerfilProfesional(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_profesional')
    titulo_profesional = models.CharField(max_length=150, blank=True)
    resumen_profesional = models.TextField(blank=True)
    area_profesional = models.CharField(max_length=120, blank=True)
    anios_experiencia = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    puesto_objetivo = models.CharField(max_length=150, blank=True)
    modalidad_preferida = models.CharField(max_length=30, blank=True)
    disponibilidad = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Perfil de {self.usuario.username}"

class ExperienciaLaboral(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='experiencias')
    empresa = models.CharField(max_length=150)
    cargo = models.CharField(max_length=150)
    departamento = models.CharField(max_length=100, blank=True)
    ubicacion = models.CharField(max_length=150, blank=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    trabajo_actual = models.BooleanField(default=False)
    funciones = models.TextField(blank=True)
    logros = models.TextField(blank=True)
    herramientas = models.TextField(blank=True)

    def __str__(self):
        return f"{self.cargo} en {self.empresa}"

class FormacionAcademica(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='formaciones')
    institucion = models.CharField(max_length=180)
    carrera = models.CharField(max_length=150)
    nivel_academico = models.CharField(max_length=60, blank=True)
    grado_obtenido = models.CharField(max_length=120, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    estado_estudios = models.CharField(max_length=40, blank=True)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return f"{self.carrera} - {self.institucion}"

# ==========================================
# COMPETENCIAS (Universal: Hard y Soft Skills)
# ==========================================

class Competencia(models.Model):
    TIPO_CHOICES = [
        ('TECNICA', 'Técnica / Hard Skill'),
        ('BLANDA', 'Blanda / Soft Skill'),
    ]
    nombre = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    categoria = models.CharField(max_length=100, blank=True, null=True) # Tecnología, Salud, Gastronomía...
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"

class UsuarioCompetencia(models.Model):
    NIVEL_CHOICES = [
        ('BASICO', 'Básico'),
        ('INTERMEDIO', 'Intermedio'),
        ('AVANZADO', 'Avanzado'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='competencias')
    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE)
    nivel = models.CharField(max_length=20, choices=NIVEL_CHOICES, default='BASICO')
    anios_experiencia = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    evidencia = models.TextField(blank=True) # Ej: "Certificado de Python"

    class Meta:
        unique_together = ('usuario', 'competencia') # No duplicar habilidades

    def __str__(self):
        return f"{self.usuario.username} - {self.competencia.nombre}"

# ==========================================
# DOCUMENTO CV (El núcleo de la extracción)
# ==========================================

class DocumentoCV(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PROCESADO', 'Procesado'),
        ('ERROR', 'Error'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documentos_cv')
    nombre_archivo = models.CharField(max_length=255)
    archivo = models.FileField(upload_to='cvs/')
    fecha_subida = models.DateTimeField(auto_now_add=True)
    estado_procesamiento = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='PENDIENTE')
    texto_extraido = models.TextField(blank=True, null=True)
    version = models.IntegerField(default=1)

    def __str__(self):
        return f"CV {self.version} de {self.usuario.username}"

# ==========================================
# MÓDULO DE EXTRACCIÓN (Ofertas y Fuentes)
# ==========================================

class FuenteDato(models.Model):
    TIPO_CHOICES = [
        ('Oficial', 'Oficial del Estado'),
        ('ONG', 'ONG'),
        ('Privada', 'Portal Privado'),
    ]
    nombre = models.CharField(max_length=100)
    url_base = models.URLField()
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='Privada')
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"

class OfertaLaboral(models.Model):
    titulo = models.CharField(max_length=200)
    empresa = models.CharField(max_length=150, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    sector = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    salario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fuente = models.ForeignKey(FuenteDato, on_delete=models.CASCADE, related_name='ofertas')
    competencias = models.ManyToManyField(Competencia, related_name='ofertas', blank=True)
    fecha_extraccion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.titulo} - {self.region}"

# ==========================================
# MÓDULO DE RESERVAS
# ==========================================

class ServicioCapacitacion(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField()
    capacidad_maxima = models.IntegerField(default=30)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return self.nombre

class Reserva(models.Model):
    ESTADO_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('Confirmada', 'Confirmada'),
        ('Cancelada', 'Cancelada'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    servicio = models.ForeignKey(ServicioCapacitacion, on_delete=models.CASCADE)
    fecha_reserva = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Pendiente')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reserva de {self.usuario.username} para {self.servicio.nombre}"

# ==========================================
# SEÑALES (Crear perfil vacío al registrar usuario)
# ==========================================

@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        DatosPersonales.objects.create(usuario=instance, nombres="Nuevo", apellidos="Usuario")
        PerfilProfesional.objects.create(usuario=instance)