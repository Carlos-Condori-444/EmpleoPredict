from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import DocumentoCV

TAILWIND_INPUT_CLASS = (
    'w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm '
    'text-slate-900 placeholder-slate-400 shadow-sm transition '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20'
)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': TAILWIND_INPUT_CLASS,
            'placeholder': 'Tu nombre de usuario',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'class': TAILWIND_INPUT_CLASS,
            'placeholder': 'Tu contraseña',
            'autocomplete': 'current-password',
        })


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
