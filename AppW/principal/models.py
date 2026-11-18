from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class MapaBiblioteca(models.Model):
    estructura = models.JSONField(default=list, help_text="Coordenadas y elementos del plano en formato JSON")
    ultima_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mapa de la Biblioteca"
        verbose_name_plural = "Mapas de la Biblioteca"

    def __str__(self):
        return f"Plano General (Actualizado: {self.ultima_modificacion.strftime('%Y-%m-%d %H:%M')})"


class Libro(models.Model):
    ESTADO_CHOICES = [
        ('Disponible', 'Disponible'),
        ('En revision', 'En revisión'),
        ('En progreso', 'En progreso'),
        ('Prestado', 'Prestado'),
        ('En devolucion', 'En devolución'),
        ('Vencido', 'Vencido'),
    ]

    titulo = models.CharField(max_length=200)
    autor = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    archivo = models.FileField(upload_to='libros/pdfs/', blank=True, null=True)
    portada = models.ImageField(upload_to='libros/portadas/', blank=True, null=True)
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Disponible')
    ubicacion = models.CharField(max_length=150, default='Estante General - Piso 1')
    posicion_x = models.IntegerField(default=50)
    posicion_y = models.IntegerField(default=50)

    prestado_a = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='libros_prestados')

    def save(self, *args, **kwargs):
        if self.estado == 'Disponible':
            self.prestado_a = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titulo} ({self.estado})"


class Articulo(models.Model):
    titulo = models.CharField(max_length=200)
    autor = models.CharField(max_length=200)
    resumen = models.TextField(blank=True, null=True)
    archivo = models.FileField(upload_to='articulos/pdfs/', blank=True, null=True)
    portada = models.ImageField(upload_to='articulos/portadas/', blank=True, null=True)
    creado_por_rol = models.CharField(max_length=50, default='Estudiante')

    def __str__(self):
        return self.titulo


class Cuenta(models.Model):
    ROLES = [
        ('Administrador', 'Administrador'),
        ('Profesor', 'Profesor'),
        ('Estudiante', 'Estudiante'),
        ('Externo', 'Externo'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cuenta', null=True, blank=True)
    nombre = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150, blank=True, null=True, default='No especificado')
    correo = models.EmailField(unique=True)
    rol = models.CharField(max_length=50, choices=ROLES, default='Estudiante')
    foto_perfil = models.ImageField(upload_to='perfiles/', blank=True, null=True)
    vetado = models.BooleanField(default=False, help_text="Bloquea las solicitudes si tiene préstamos vencidos")

    def __str__(self):
        estado_veto = " [VETADO]" if self.vetado else ""
        return f"{self.nombre} {self.apellido or ''} ({self.correo}) - {self.rol}{estado_veto}"


class Prestamo(models.Model):
    ESTADOS = [
        ('En revision', 'En revisión'),
        ('En progreso', 'En progreso'),
        ('Prestado', 'Prestado'),
        ('En devolucion', 'En devolución'),
        ('Devuelto', 'Devuelto'),
        ('Vencido', 'Vencido'),
    ]

    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, related_name='prestamos')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prestamos')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    fecha_vencimiento = models.DateTimeField(null=True, blank=True)
    fecha_devolucion = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='En revision')
    recordatorio_enviado = models.BooleanField(
        default=False, 
        help_text="Indica si se envió el correo de notificación cuando queda 1 día para el vencimiento"
    )

    def esta_vencido(self):
        if self.fecha_vencimiento and self.estado in ['Prestado', 'En progreso', 'En devolucion']:
            return timezone.now() > self.fecha_vencimiento
        return False

    def __str__(self):
        return f"Préstamo #{self.id} - {self.libro.titulo} / {self.usuario.username} ({self.estado})"