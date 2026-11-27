from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Competencia,
    DatosPersonales,
    DocumentoCV,
    ExperienciaLaboral,
    FormacionAcademica,
    PerfilProfesional,
    Reserva,
    UsuarioCompetencia,
)

TAILWIND_INPUT_CLASS = (
    'w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm '
    'text-slate-900 placeholder-slate-400 shadow-sm transition '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
)

TAILWIND_TEXTAREA_CLASS = TAILWIND_INPUT_CLASS + ' min-h-[90px]'
TAILWIND_CHECKBOX_CLASS = 'h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500'


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': (
            'Usuario, correo o contraseña incorrectos. '
            'Verifica tus datos (recuerda respetar mayúsculas y minúsculas).'
        ),
        'inactive': 'Esta cuenta se encuentra inactiva.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Usuario o correo electrónico'
        self.fields['username'].widget.attrs.update({
            'class': TAILWIND_INPUT_CLASS,
            'placeholder': 'Usuario o correo@ejemplo.com',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'class': TAILWIND_INPUT_CLASS,
            'placeholder': 'Tu contraseña',
            'autocomplete': 'current-password',
        })

    def clean(self):
        identificador = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if identificador and password and not User.objects.filter(username=identificador).exists():
            candidatos = User.objects.filter(email__iexact=identificador)
            for candidato in candidatos:
                if candidato.check_password(password):
                    self.cleaned_data['username'] = candidato.username
                    break
            else:
                if candidatos.count() == 1:
                    self.cleaned_data['username'] = candidatos.first().username

        return super().clean()


class RegistroForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'class': TAILWIND_INPUT_CLASS,
            'placeholder': 'correo@ejemplo.com',
            'autocomplete': 'email',
        }),
    )

    class Meta:
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': 'Elige un nombre de usuario',
            'password1': 'Crea una contraseña segura',
            'password2': 'Repite tu contraseña',
        }
        for name in ('username', 'password1', 'password2'):
            self.fields[name].widget.attrs.update({
                'class': TAILWIND_INPUT_CLASS,
                'placeholder': placeholders[name],
            })


class SubirCVForm(forms.ModelForm):
    class Meta:
        model = DocumentoCV
        fields = ['archivo']
        labels = {
            'archivo': 'Selecciona tu archivo de Curriculum Vitae (Formato PDF)'
        }
        widgets = {
            'archivo': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer border border-gray-300 rounded-lg p-2 bg-white',
                'accept': '.pdf'
            })
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            nombre = archivo.name.lower()
            if not nombre.endswith('.pdf'):
                raise forms.ValidationError('El archivo debe ser un documento en formato PDF (.pdf).')
            # Límite de 10 MB
            if archivo.size > 10 * 1024 * 1024:
                raise forms.ValidationError('El archivo es demasiado grande. El límite máximo es de 10 MB.')
        return archivo


def _aplicar_estilos_tailwind(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs['class'] = TAILWIND_CHECKBOX_CLASS
        elif isinstance(widget, forms.Textarea):
            widget.attrs['class'] = TAILWIND_TEXTAREA_CLASS
        else:
            widget.attrs['class'] = TAILWIND_INPUT_CLASS


class DatosPersonalesForm(forms.ModelForm):
    class Meta:
        model = DatosPersonales
        fields = [
            'nombres', 'apellidos', 'email_contacto', 'fecha_nacimiento',
            'telefono', 'pais', 'departamento', 'ciudad',
            'linkedin_url', 'github_url', 'portafolio_url',
        ]
        labels = {
            'email_contacto': 'Correo de contacto',
            'fecha_nacimiento': 'Fecha de nacimiento',
            'telefono': 'Teléfono',
            'pais': 'País',
            'departamento': 'Departamento / Región',
            'linkedin_url': 'LinkedIn (URL)',
            'github_url': 'GitHub (URL)',
            'portafolio_url': 'Portafolio / Web (URL)',
        }
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)


class PerfilProfesionalForm(forms.ModelForm):
    class Meta:
        model = PerfilProfesional
        fields = [
            'titulo_profesional', 'area_profesional', 'puesto_objetivo',
            'anios_experiencia', 'modalidad_preferida', 'disponibilidad',
            'resumen_profesional',
        ]
        labels = {
            'titulo_profesional': 'Título profesional',
            'area_profesional': 'Área profesional',
            'puesto_objetivo': 'Puesto objetivo',
            'anios_experiencia': 'Años de experiencia',
            'modalidad_preferida': 'Modalidad preferida',
            'disponibilidad': 'Disponibilidad',
            'resumen_profesional': 'Resumen profesional',
        }
        widgets = {
            'anios_experiencia': forms.NumberInput(attrs={'min': '0', 'step': '0.5'}),
            'modalidad_preferida': forms.TextInput(attrs={'placeholder': 'Ej. Remoto, Híbrido, Presencial'}),
            'disponibilidad': forms.TextInput(attrs={'placeholder': 'Ej. Inmediata, 15 días'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)

    def clean_anios_experiencia(self):
        valor = self.cleaned_data.get('anios_experiencia')
        if valor is not None and valor < 0:
            raise forms.ValidationError('Los años de experiencia no pueden ser negativos.')
        return valor


class ExperienciaLaboralForm(forms.ModelForm):
    class Meta:
        model = ExperienciaLaboral
        fields = [
            'cargo', 'empresa', 'departamento', 'ubicacion',
            'fecha_inicio', 'fecha_fin', 'trabajo_actual',
            'funciones', 'logros', 'herramientas',
        ]
        labels = {
            'ubicacion': 'Ubicación',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_fin': 'Fecha de fin',
            'trabajo_actual': 'Actualmente trabajo aquí',
            'herramientas': 'Herramientas utilizadas',
        }
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)


class FormacionAcademicaForm(forms.ModelForm):
    class Meta:
        model = FormacionAcademica
        fields = [
            'institucion', 'carrera', 'nivel_academico', 'grado_obtenido',
            'fecha_inicio', 'fecha_fin', 'estado_estudios', 'descripcion',
        ]
        labels = {
            'institucion': 'Institución',
            'nivel_academico': 'Nivel académico',
            'grado_obtenido': 'Grado obtenido',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_fin': 'Fecha de fin',
            'estado_estudios': 'Estado de estudios',
            'descripcion': 'Descripción',
        }
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'estado_estudios': forms.TextInput(attrs={'placeholder': 'Ej. Egresado, En curso, Titulado'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)


class UsuarioCompetenciaForm(forms.ModelForm):
    nueva_competencia = forms.CharField(
        required=False,
        max_length=120,
        label='O crear nueva competencia',
        widget=forms.TextInput(attrs={'placeholder': 'Ej. Power BI, Comunicación Asertiva'}),
    )
    tipo_nueva = forms.ChoiceField(
        required=False,
        choices=Competencia.TIPO_CHOICES,
        label='Tipo de nueva competencia',
    )

    class Meta:
        model = UsuarioCompetencia
        fields = ['competencia', 'nivel', 'anios_experiencia', 'evidencia']
        labels = {
            'competencia': 'Competencia existente',
            'anios_experiencia': 'Años de experiencia',
            'evidencia': 'Evidencia o respaldo',
        }
        widgets = {
            'anios_experiencia': forms.NumberInput(attrs={'min': '0', 'step': '0.5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['competencia'].required = False
        self.fields['competencia'].queryset = Competencia.objects.order_by('nombre')
        self.fields['competencia'].empty_label = 'Selecciona del catálogo...'
        _aplicar_estilos_tailwind(self)

    def clean_anios_experiencia(self):
        valor = self.cleaned_data.get('anios_experiencia')
        if valor is not None and valor < 0:
            raise forms.ValidationError('Los años de experiencia no pueden ser negativos.')
        return valor

    def clean(self):
        cleaned = super().clean()
        comp = cleaned.get('competencia')
        nueva = (cleaned.get('nueva_competencia') or '').strip()
        if not comp and not nueva:
            raise forms.ValidationError('Selecciona una competencia existente o escribe el nombre de una nueva.')
        return cleaned


class UsuarioCompetenciaEditarForm(forms.ModelForm):
    class Meta:
        model = UsuarioCompetencia
        fields = ['nivel', 'anios_experiencia', 'evidencia']
        labels = {
            'anios_experiencia': 'Años de experiencia',
            'evidencia': 'Evidencia o respaldo',
        }
        widgets = {
            'anios_experiencia': forms.NumberInput(attrs={'min': '0', 'step': '0.5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)

    def clean_anios_experiencia(self):
        valor = self.cleaned_data.get('anios_experiencia')
        if valor is not None and valor < 0:
            raise forms.ValidationError('Los años de experiencia no pueden ser negativos.')
        return valor


class DocumentoCVEditarForm(forms.ModelForm):
    class Meta:
        model = DocumentoCV
        fields = ['nombre_archivo']
        labels = {
            'nombre_archivo': 'Nombre del documento',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_estilos_tailwind(self)


class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ['fecha_reserva']
        labels = {
            'fecha_reserva': 'Fecha y hora deseada',
        }
        widgets = {
            'fecha_reserva': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_reserva'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]
        _aplicar_estilos_tailwind(self)

    def clean_fecha_reserva(self):
        fecha = self.cleaned_data.get('fecha_reserva')
        if fecha and fecha < timezone.now():
            raise forms.ValidationError('La fecha y hora de reserva no pueden estar en el pasado.')
        return fecha
