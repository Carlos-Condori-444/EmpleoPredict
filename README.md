# EmpleoPredict - Análisis de demanda laboral y orientación de competencias

Sistema desarrollado para el curso de Lenguajes de Programación. El proyecto busca orientar a las personas hacia las competencias que realmente demanda el mercado laboral, analizando ofertas laborales y generando reportes de tendencias.

**Tecnologías utilizadas:**
*   **Backend:** Python + Django
*   **Base de Datos:** SQLite (Por defecto en Django)
*   **Frontend:** HTML + Tailwind CSS
*   **Control de versiones:** Git + GitHub

---

## 🛠️ Requisitos previos

Antes de empezar, asegúrate de tener instalado en tu computadora:
1.  **Python** (Versión 3.10 o superior). Puedes verificarlo con el comando `python --version`.
2.  **Git**. Puedes verificarlo con `git --version`.
3.  Un editor de código (Recomendado: **Visual Studio Code**).

---

## 🚀 Guía de Despliegue Local (Paso a Paso)

Sigue estos pasos en tu terminal (CMD, PowerShell, Git Bash o la terminal de VS Code) para tener el proyecto corriendo en tu máquina.

### 1. Clonar el repositorio
Abre tu terminal, ubícate en la carpeta donde quieras guardar el proyecto y ejecuta:
```bash
git clone https://github.com/TU_USUARIO/EmpleoPredict.git
cd EmpleoPredict
```
(No olvides reemplazar TU_USUARIO con el enlace real de nuestro repositorio en GitHub).

### **2. Crear y activar el Entorno Virtual**

Es obligatorio usar un entorno virtual para no mezclar las librerías de este proyecto con las de tu sistema.

**En Windows:**

bash

```
python -m venv venv
venv\Scripts\activate
```

**En Mac / Linux:**

bash

```
python3 -m venv venv
source venv/bin/activate
```

Sabrás que el entorno está activo porque verás `(venv)` al inicio de tu línea de comandos.

### **3. Instalar las dependencias**

Con el entorno virtual activado, instala las librerías necesarias, incluyendo Django y otras que vayamos agregando:

bash

```
pip install -r requirements.txt
```

### **4. Aplicar las migraciones de la Base de Datos**

Este comando creará el archivo `db.sqlite3` y las tablas necesarias en tu base de datos local:

bash

```
python manage.py migrate
```

### **5. Crear un Superusuario**

Para acceder al panel de administración de Django y probar la base de datos, crea un administrador:

bash

```
python manage.py createsuperuser
```

Te pedirá un nombre de usuario, correo y contraseña. La contraseña no se verá mientras escribes, es normal.

### **6. Correr el servidor**

Finalmente, levanta el proyecto:

bash

```
python manage.py runserver
```

Abre tu navegador y visita: [**http://127.0.0.1:8000/**](http://127.0.0.1:8000/)

Para ver el panel de administración ve a: [**http://127.0.0.1:8000/admin/**](http://127.0.0.1:8000/admin/) e ingresa con el superusuario que creaste.

---

## **📂 Estructura del Proyecto en Desarrollo**

- `config/` : Configuración principal de Django, incluye settings y urls.
- `core/` : Nuestra aplicación principal, incluye modelos, vistas y lógica de negocio.
- `templates/` : Archivos HTML, aquí trabajará el frontend.
- `venv/` : Entorno virtual, NO se sube a GitHub.
- `manage.py` : Script de gestión de Django.

---

## **👥 Equipo de Trabajo Grupo 02**

- **Carlos Manuel Condori Choquehuayta** U24316435 - Líder, Backend y Base de Datos
- **Sujey Yliana Hilaccama Choque** U23251152 - Frontend, UI y UX
- **Duvan Isai Davila Guerra** U23242026 - Backend, Calidad y Lógica

---

## **📌 Notas del Docente**

- El sistema debe leer y recuperar datos de fuentes oficiales del estado y ONGs de forma automática.
- El proyecto debe permitir buscar y reservar servicios, además de generar reportes.