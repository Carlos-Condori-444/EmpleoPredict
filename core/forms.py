from datetime import datetime, time, timedelta

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import DocumentoCV, Reserva

INPUT_CLASES = (
    'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm '
    'text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200'
)


def rango_dia_lima(fecha_reserva):
    """Devuelve el inicio y fin del día calendario en la zona horaria activa."""
    fecha_local = timezone.localtime(fecha_reserva).date()
    zona = timezone.get_current_timezone()
    inicio_dia = timezone.make_aware(datetime.combine(fecha_local, time.min), zona)
    return inicio_dia, inicio_dia + timedelta(days=1)

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


class LoginUsuarioForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Usuario'
        self.fields['password'].label = 'Contraseña'
        for campo in self.fields.values():
            campo.widget.attrs.update({'class': INPUT_CLASES})


class RegistroUsuarioForm(UserCreationForm):
    email = forms.EmailField(required=False, label='Correo electrónico (opcional)')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Nombre de usuario'
        for campo in self.fields.values():
            campo.widget.attrs.update({'class': INPUT_CLASES})


class ReservaForm(forms.ModelForm):
    fecha_reserva = forms.DateTimeField(
        label='Fecha y hora de reserva',
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local', 'class': INPUT_CLASES},
        ),
    )

    class Meta:
        model = Reserva
        fields = ['fecha_reserva']

    def __init__(self, *args, usuario=None, servicio=None, **kwargs):
        self.usuario = usuario
        self.servicio = servicio
        super().__init__(*args, **kwargs)

    def clean_fecha_reserva(self):
        fecha = self.cleaned_data.get('fecha_reserva')
        if fecha and fecha <= timezone.now():
            raise forms.ValidationError('No puedes reservar en una fecha u hora pasada.')
        return fecha

    def clean(self):
        datos = super().clean()
        fecha = datos.get('fecha_reserva')
        if not fecha or self.servicio is None or self.usuario is None:
            return datos

        inicio_dia, fin_dia = rango_dia_lima(fecha)
        activas_fecha = Reserva.objects.filter(
            servicio=self.servicio,
            fecha_reserva__gte=inicio_dia,
            fecha_reserva__lt=fin_dia,
        ).exclude(estado='Cancelada')

        if activas_fecha.filter(usuario=self.usuario).exists():
            raise forms.ValidationError(
                'Ya tienes una reserva activa para este servicio en la fecha seleccionada.'
            )

        if activas_fecha.count() >= self.servicio.capacidad_maxima:
            raise forms.ValidationError(
                'No quedan cupos disponibles para este servicio en la fecha seleccionada.'
            )
        return datos
