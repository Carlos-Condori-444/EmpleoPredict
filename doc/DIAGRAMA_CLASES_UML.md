# Diagrama de Clases UML — EmpleoPredict

A continuación se presenta el diagrama de clases UML actualizado de los modelos en `core/models.py` en dos formatos listos para usar en tu informe o herramientas de diagramación: **Mermaid** (renderizable en Markdown/GitHub/VS Code) y **PlantUML** (compatible con PlantUML/Draw.io).

---

## 1. Código UML en Mermaid

```mermaid
classDiagram
    class User {
        +int id
        +string username
        +string email
        +string password
        +bool is_staff
    }

    class DatosPersonales {
        +string nombres
        +string apellidos
        +string email_contacto
        +date fecha_nacimiento
        +string telefono
        +string pais
        +string departamento
        +string ciudad
        +url linkedin_url
        +url github_url
        +url portafolio_url
    }

    class PerfilProfesional {
        +string titulo_profesional
        +text resumen_profesional
        +string area_profesional
        +decimal anios_experiencia
        +string puesto_objetivo
        +string modalidad_preferida
        +string disponibilidad
    }

    class ExperienciaLaboral {
        +string empresa
        +string cargo
        +string departamento
        +string ubicacion
        +date fecha_inicio
        +date fecha_fin
        +bool trabajo_actual
        +text funciones
        +text logros
        +text herramientas
    }

    class FormacionAcademica {
        +string institucion
        +string carrera
        +string nivel_academico
        +string grado_obtenido
        +date fecha_inicio
        +date fecha_fin
        +string estado_estudios
        +text descripcion
    }

    class Competencia {
        +string nombre
        +string tipo
        +string categoria
        +text descripcion
    }

    class UsuarioCompetencia {
        +string nivel
        +decimal anios_experiencia
        +text evidencia
    }

    class DocumentoCV {
        +string nombre_archivo
        +file archivo
        +datetime fecha_subida
        +string estado_procesamiento
        +text texto_extraido
        +int version
    }

    class FuenteDato {
        +string nombre
        +url url_base
        +string tipo
        +datetime ultima_ejecucion
    }

    class OfertaLaboral {
        +string titulo
        +string empresa
        +text descripcion
        +string sector
        +string region
        +decimal salario
        +url url_oferta
        +datetime fecha_publicacion
        +datetime fecha_extraccion
    }

    class ServicioCapacitacion {
        +string nombre
        +text descripcion
        +string categoria
        +string proveedor
        +string duracion
        +string modalidad
        +datetime fecha_inicio
        +int capacidad_maxima
        +decimal precio
        +bool otorga_certificado
        +bool es_externo
        +url url_externa
        +bool activo
        +es_gratuito() bool
        +reservas_activas_count() int
        +cupos_disponibles() int
    }

    class Reserva {
        +datetime fecha_reserva
        +string estado
        +datetime fecha_creacion
        +puede_cancelarse() bool
    }

    User "1" -- "1" DatosPersonales : posee
    User "1" -- "1" PerfilProfesional : posee
    User "1" -- "0..*" ExperienciaLaboral : registra
    User "1" -- "0..*" FormacionAcademica : registra
    User "1" -- "0..*" DocumentoCV : sube
    User "1" -- "0..*" UsuarioCompetencia : tiene
    Competencia "1" -- "0..*" UsuarioCompetencia : clasifica
    User "1" -- "0..*" Reserva : realiza
    ServicioCapacitacion "1" -- "0..*" Reserva : recibe
    FuenteDato "1" -- "0..*" OfertaLaboral : origina
    OfertaLaboral "0..*" -- "0..*" Competencia : requiere
    ServicioCapacitacion "0..*" -- "0..*" Competencia : desarrolla
```

---

## 2. Código UML en PlantUML (para exportar a imagen PNG/SVG)

```plantuml
@startuml EmpleoPredict_Clases
skinparam classAttributeIconSize 0
hide circle

class User {
  +id : int
  +username : str
  +email : str
  +is_staff : bool
}

class DatosPersonales {
  +nombres : str
  +apellidos : str
  +email_contacto : str
  +fecha_nacimiento : date
  +telefono : str
  +pais : str
  +departamento : str
  +ciudad : str
  +linkedin_url : url
  +github_url : url
  +portafolio_url : url
}

class PerfilProfesional {
  +titulo_profesional : str
  +resumen_profesional : text
  +area_profesional : str
  +anios_experiencia : decimal
  +puesto_objetivo : str
  +modalidad_preferida : str
  +disponibilidad : str
}

class ExperienciaLaboral {
  +empresa : str
  +cargo : str
  +departamento : str
  +ubicacion : str
  +fecha_inicio : date
  +fecha_fin : date
  +trabajo_actual : bool
  +funciones : text
  +logros : text
  +herramientas : text
}

class FormacionAcademica {
  +institucion : str
  +carrera : str
  +nivel_academico : str
  +grado_obtenido : str
  +fecha_inicio : date
  +fecha_fin : date
  +estado_estudios : str
  +descripcion : text
}

class Competencia {
  +nombre : str
  +tipo : str
  +categoria : str
  +descripcion : text
}

class UsuarioCompetencia {
  +nivel : str
  +anios_experiencia : decimal
  +evidencia : text
}

class DocumentoCV {
  +nombre_archivo : str
  +archivo : file
  +fecha_subida : datetime
  +estado_procesamiento : str
  +texto_extraido : text
  +version : int
}

class FuenteDato {
  +nombre : str
  +url_base : url
  +tipo : str
  +ultima_ejecucion : datetime
}

class OfertaLaboral {
  +titulo : str
  +empresa : str
  +descripcion : text
  +sector : str
  +region : str
  +salario : decimal
  +url_oferta : url
  +fecha_publicacion : datetime
  +fecha_extraccion : datetime
}

class ServicioCapacitacion {
  +nombre : str
  +descripcion : text
  +categoria : str
  +proveedor : str
  +duracion : str
  +modalidad : str
  +fecha_inicio : datetime
  +capacidad_maxima : int
  +precio : decimal
  +otorga_certificado : bool
  +es_externo : bool
  +url_externa : url
  +activo : bool
  +es_gratuito() : bool
  +reservas_activas_count() : int
  +cupos_disponibles() : int
}

class Reserva {
  +fecha_reserva : datetime
  +estado : str
  +fecha_creacion : datetime
  +puede_cancelarse() : bool
}

User "1" -- "1" DatosPersonales
User "1" -- "1" PerfilProfesional
User "1" -- "0..*" ExperienciaLaboral
User "1" -- "0..*" FormacionAcademica
User "1" -- "0..*" DocumentoCV
User "1" -- "0..*" UsuarioCompetencia
Competencia "1" -- "0..*" UsuarioCompetencia
User "1" -- "0..*" Reserva
ServicioCapacitacion "1" -- "0..*" Reserva
FuenteDato "1" -- "0..*" OfertaLaboral
OfertaLaboral "0..*" -- "0..*" Competencia
ServicioCapacitacion "0..*" -- "0..*" Competencia
@enduml
```
