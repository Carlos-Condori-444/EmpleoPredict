from django import forms
from .models import DocumentoCV

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
