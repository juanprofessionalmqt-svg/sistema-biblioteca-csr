# Sistema de Gestión Bibliotecaria y Repositorio Institucional (SGBRI)

## Descripción del Proyecto
Este sistema web fue diseñado y desarrollado para la optimización de los procesos logísticos, el control de inventario y la gestión administrativa de la biblioteca del Colegio Seminario Redentorista[cite: 1, 2]. 

La plataforma integra:
* Control de préstamos en tiempo real con ciclo de estados (*Disponible*, *En progreso*, *Prestado*, *En devolución*)[cite: 1, 2].
* Sistema automatizado de sanciones y vetos por morosidad de entregas[cite: 1, 2].
* Plano físico interactivo mediante API REST para la geolocalización y disposición de ejemplares en estantes[cite: 1, 2].
* Repositorio digital institucional (*"Trabajos Destacados"*) para carga, filtrado y lectura de artículos académicos en formato PDF[cite: 1, 2].
* Autenticación y control de accesos adaptado a 4 roles (*Administrador*, *Profesor*, *Estudiante*, *Externo*)[cite: 1, 2].

---

## Stack Tecnológico y Dependencias
* **Lenguaje de Programación:** Python 3.10+[cite: 1, 3]
* **Framework Backend:** Django (>=4.2, <5.1)[cite: 1, 2]
* **Base de Datos:** SQLite3 (entorno local) / MySQL[cite: 1, 2]
* **Controlador de DB:** PyMySQL (>=1.1.0)[cite: 2]
* **Procesamiento de Imágenes:** Pillow (>=10.0.0)[cite: 2]
* **Frontend:** HTML5, JavaScript nativo (API REST / Canvas) y Tailwind CSS[cite: 1]
* **Recursos Estáticos:** Fuentes e iconografía locales (`fa-solid-900.woff2`) para autonomía de red offline[cite: 1]

---

## Estructura del Repositorio
```text
proyecto_biblioteca/
├── backend/             # Aplicaciones Django (modelos, vistas, plantillas)[cite: 1]
├── database/            # Scripts SQL y datos iniciales (seed_data.json)[cite: 1]
├── docs/                # Documentación técnica y manuales PDF[cite: 1]
├── static/              # Archivos estáticos (CSS, JS, tipografías locales)[cite: 1]
├── media/               # Archivos subidos (portadas, artículos PDF)[cite: 1]
├── requirements.txt     # Archivo de dependencias del proyecto[cite: 1, 2]
└── README.md            # Documentación principal en la raíz[cite: 1]