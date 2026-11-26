import re
import os
from pypdf import PdfReader
from django.db import transaction
from .models import Competencia, UsuarioCompetencia, DatosPersonales

# Lista base universal de competencias (Técnicas y Blandas) para autodetectar
COMPETENCIAS_BASE = [
    # Habilidades Técnicas (Hard Skills)
    ("Python", "TECNICA", "Tecnología"),
    ("Django", "TECNICA", "Tecnología"),
    ("JavaScript", "TECNICA", "Tecnología"),
    ("SQL", "TECNICA", "Tecnología"),
    ("PostgreSQL", "TECNICA", "Tecnología"),
    ("SQLite", "TECNICA", "Tecnología"),
    ("HTML", "TECNICA", "Tecnología"),
    ("CSS", "TECNICA", "Tecnología"),
    ("Tailwind", "TECNICA", "Tecnología"),
    ("Git", "TECNICA", "Tecnología"),
    ("GitHub", "TECNICA", "Tecnología"),
    ("Excel", "TECNICA", "Gestión y Oficina"),
    ("Power BI", "TECNICA", "Gestión y Oficina"),
    ("Scrum", "TECNICA", "Gestión de Proyectos"),
    ("Data Analysis", "TECNICA", "Tecnología"),
    ("Machine Learning", "TECNICA", "Tecnología"),
    ("Marketing Digital", "TECNICA", "Comercial"),
    ("Ventas", "TECNICA", "Comercial"),
    ("Contabilidad", "TECNICA", "Finanzas"),
    ("Administración", "TECNICA", "Gestión"),
    
    # Habilidades Blandas (Soft Skills)
    ("Liderazgo", "BLANDA", "Habilidades Blandas"),
    ("Trabajo en Equipo", "BLANDA", "Habilidades Blandas"),
    ("Comunicación Asertiva", "BLANDA", "Habilidades Blandas"),
    ("Resolución de Problemas", "BLANDA", "Habilidades Blandas"),
    ("Proactividad", "BLANDA", "Habilidades Blandas"),
    ("Adaptabilidad", "BLANDA", "Habilidades Blandas"),
    ("Pensamiento Crítico", "BLANDA", "Habilidades Blandas"),
    ("Gestión del Tiempo", "BLANDA", "Habilidades Blandas"),
]

def poblar_catalogo_competencias():
    """Asegura que las competencias base existan en la BD."""
    for nombre, tipo, categoria in COMPETENCIAS_BASE:
        Competencia.objects.get_or_create(
            nombre=nombre,
            defaults={"tipo": tipo, "categoria": categoria}
        )

def extraer_texto_pdf(ruta_archivo):
    """
    Abre un archivo PDF y extrae todo su texto plano concatenado.
    """
    texto_completo = []
    try:
        lector = PdfReader(ruta_archivo)
        for num_pagina, pagina in enumerate(lector.pages):
            texto = pagina.extract_text()
            if texto:
                texto_completo.append(texto)
        return "\n".join(texto_completo).strip()
    except Exception as e:
        print(f"Error extrayendo texto del PDF: {e}")
        return ""

def extraer_datos_contacto(texto):
    """
    Busca patrones de email, teléfono, LinkedIn y GitHub mediante expresiones regulares.
    """
    datos = {
        "email": None,
        "telefono": None,
        "linkedin_url": None,
        "github_url": None,
    }
    
    # 1. Email
    patron_email = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    match_email = re.search(patron_email, texto)
    if match_email:
        datos["email"] = match_email.group(0)

    # 2. Teléfono celular (Formatos típicos peruanos: 987654321, 987 654 321, +51 987654321)
    patron_tel = r'(?:\+?51[\s-]?)?(?:9\d{2}[\s-]?\d{3}[\s-]?\d{3}|9\d{8})'
    match_tel = re.search(patron_tel, texto)
    if match_tel:
        # Limpiar espacios y guiones para guardar un formato estándar
        tel_limpio = re.sub(r'[\s-]', '', match_tel.group(0))
        datos["telefono"] = tel_limpio

    # 3. LinkedIn
    patron_linkedin = r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/in\/[a-zA-Z0-9_-]+(?:\/)?'
    match_linkedin = re.search(patron_linkedin, texto, re.IGNORECASE)
    if match_linkedin:
        url = match_linkedin.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        datos["linkedin_url"] = url

    # 4. GitHub
    patron_github = r'(?:https?:\/\/)?(?:www\.)?github\.com\/[a-zA-Z0-9_-]+(?:\/)?'
    match_github = re.search(patron_github, texto, re.IGNORECASE)
    if match_github:
        url = match_github.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        datos["github_url"] = url

    return datos

def extraer_competencias_del_texto(texto):
    """
    Busca coincidencias de competencias del catálogo de CV dentro del texto.
    """
    poblar_catalogo_competencias()
    todas_competencias = Competencia.objects.filter(es_catalogo_cv=True)
    competencias_encontradas = []

    texto_lower = texto.lower()

    for comp in todas_competencias:
        # Búsqueda por palabra exacta o límite de palabra para evitar falsos positivos
        nombre = comp.nombre
        patron = r'\b' + re.escape(nombre.lower()) + r'\b'
        if re.search(patron, texto_lower):
            competencias_encontradas.append(comp)

    return competencias_encontradas

def procesar_cv(documento_cv):
    """
    Orquestador principal:
    1. Lee el PDF y extrae texto plano.
    2. Extrae teléfono, redes y correo.
    3. Detecta competencias y las asocia al usuario.
    4. Actualiza estado a PROCESADO o ERROR.
    """
    try:
        ruta_archivo = documento_cv.archivo.path
        if not os.path.exists(ruta_archivo):
            documento_cv.estado_procesamiento = "ERROR"
            documento_cv.save()
            return False, "El archivo PDF no se encuentra en el servidor."

        texto = extraer_texto_pdf(ruta_archivo)
        if not texto:
            documento_cv.estado_procesamiento = "ERROR"
            documento_cv.save()
            return False, "No se pudo extraer texto del PDF (podría ser una imagen o estar protegido)."

        # Guardar texto extraído
        documento_cv.texto_extraido = texto
        
        with transaction.atomic():
            # 1. Actualizar Datos Personales si se encuentran
            usuario = documento_cv.usuario
            datos_contacto = extraer_datos_contacto(texto)
            
            perfil, _ = DatosPersonales.objects.get_or_create(usuario=usuario)
            if datos_contacto["telefono"] and not perfil.telefono:
                perfil.telefono = datos_contacto["telefono"]
            if datos_contacto["linkedin_url"] and not perfil.linkedin_url:
                perfil.linkedin_url = datos_contacto["linkedin_url"]
            if datos_contacto["github_url"] and not perfil.github_url:
                perfil.github_url = datos_contacto["github_url"]
            perfil.save()

            # 2. Extraer y asociar competencias
            competencias = extraer_competencias_del_texto(texto)
            for comp in competencias:
                UsuarioCompetencia.objects.get_or_create(
                    usuario=usuario,
                    competencia=comp,
                    defaults={
                        "nivel": "INTERMEDIO",
                        "evidencia": f"Detectado automáticamente en {documento_cv.nombre_archivo}"
                    }
                )

            # 3. Marcar como procesado con éxito
            documento_cv.estado_procesamiento = "PROCESADO"
            documento_cv.save()

        return True, f"CV procesado exitosamente. Se detectaron {len(competencias)} competencias."

    except Exception as e:
        documento_cv.estado_procesamiento = "ERROR"
        documento_cv.save()
        return False, f"Ocurrió un error al procesar el CV: {str(e)}"
