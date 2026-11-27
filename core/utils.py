import re
import os
from pypdf import PdfReader
from django.db import transaction
from django.utils import timezone
from .models import Competencia, UsuarioCompetencia, DatosPersonales, ExperienciaLaboral, FormacionAcademica

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

    # 2. Teléfono celular (Más flexible para aceptar guiones y formatos raros)
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
    Busca competencias en el texto usando la raíz de las palabras (Regex).
    Esto permite detectar 'proactiva', 'proactivo', 'proactividad' buscando solo 'proactiv'.
    """
    todas_competencias = Competencia.objects.all()
    competencias_encontradas = set() # Usamos un set para evitar duplicados

    texto_lower = texto.lower()

    for comp in todas_competencias:
        nombre = comp.nombre.lower()
        
        # TRUCO: Si la palabra tiene más de 5 letras, cortamos las últimas 3 (la raíz).
        # Ejemplo: "proactividad" -> "proactiv". "liderazgo" -> "lider".
        if len(nombre) > 5:
            raiz = nombre[:-3]
        else:
            raiz = nombre

        # Buscamos la raíz seguida de cualquier letra (\w*) para atrapar conjugaciones.
        patron = r'\b' + re.escape(raiz) + r'\w*'
        
        if re.search(patron, texto_lower):
            competencias_encontradas.add(comp)

    return list(competencias_encontradas)

def extraer_bloques_texto(texto, palabras_clave):
    """
    Busca un bloque de texto basado en una palabra clave (ej: 'Experiencia').
    """
    texto_lower = texto.lower()
    for palabra in palabras_clave:
        indice = texto_lower.find(palabra)
        if indice != -1:
            # Tomamos los siguientes 500 caracteres como aproximación del bloque
            bloque = texto[indice:indice+500].strip()
            return bloque
    return None

def procesar_cv(documento_cv):
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

        documento_cv.texto_extraido = texto
        
        with transaction.atomic():
            usuario = documento_cv.usuario
            datos_contacto = extraer_datos_contacto(texto)
            
            # 1. Actualizar Datos Personales (Sobrescribiendo si hay info nueva)
            perfil, _ = DatosPersonales.objects.get_or_create(usuario=usuario)
            if datos_contacto["email"]: 
                perfil.email_contacto = datos_contacto["email"]
            if datos_contacto["telefono"]: 
                perfil.telefono = datos_contacto["telefono"]
            if datos_contacto["linkedin_url"]: 
                perfil.linkedin_url = datos_contacto["linkedin_url"]
            if datos_contacto["github_url"]: 
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
                        "evidencia": f"Detectado en {documento_cv.nombre_archivo}"
                    }
                )

            # 3. Extraer Experiencia Laboral y Formación (Heurística Básica)
            bloque_exp = extraer_bloques_texto(texto, ["experiencia laboral", "experiencia profesional", "experiencia"])
            if bloque_exp:
                ExperienciaLaboral.objects.get_or_create(
                    usuario=usuario,
                    cargo="Cargo detectado en CV",
                    empresa="Ver detalles en el texto",
                    defaults={'funciones': bloque_exp, 'fecha_inicio': timezone.now().date()}
                )

            bloque_edu = extraer_bloques_texto(texto, ["educación", "formación académica", "estudios"])
            if bloque_edu:
                FormacionAcademica.objects.get_or_create(
                    usuario=usuario,
                    institucion="Institución detectada en CV",
                    carrera="Carrera detectada en CV",
                    defaults={'descripcion': bloque_edu}
                )

            # 4. Marcar como procesado
            documento_cv.estado_procesamiento = "PROCESADO"
            documento_cv.save()

        return True, f"CV procesado. Se detectaron {len(competencias)} competencias y se actualizó el perfil."

    except Exception as e:
        documento_cv.estado_procesamiento = "ERROR"
        documento_cv.save()
        return False, f"Error al procesar CV: {str(e)}"