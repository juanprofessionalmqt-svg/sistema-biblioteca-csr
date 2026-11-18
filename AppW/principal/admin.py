from django.contrib import admin
from django.contrib.auth.models import User
from .models import Libro, Articulo, Cuenta, Prestamo, MapaBiblioteca

admin.site.index_template = 'panel_administracion.html'

index_original = admin.site.index


def custom_admin_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context['libros'] = Libro.objects.all().order_by('-id')
    extra_context['articulos'] = Articulo.objects.all().order_by('-id')
    extra_context['usuarios'] = User.objects.all().order_by('-id')
    extra_context['prestamos'] = Prestamo.objects.all().order_by('-id')
    return index_original(request, extra_context=extra_context)


admin.site.index = custom_admin_index


@admin.register(MapaBiblioteca)
class MapaBibliotecaAdmin(admin.ModelAdmin):
    list_display = ('id', 'ultima_modificacion')


@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'autor', 'estado', 'ubicacion', 'posicion_x', 'posicion_y')
    list_filter = ('estado',)
    search_fields = ('titulo', 'autor', 'ubicacion')


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'autor', 'creado_por_rol')
    search_fields = ('titulo', 'autor')


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'correo', 'rol', 'vetado')
    list_filter = ('rol', 'vetado')
    search_fields = ('nombre', 'apellido', 'correo')
    actions = ['vetar_usuarios', 'desvetar_usuarios']

    @admin.action(description="Vetar usuarios seleccionados")
    def vetar_usuarios(self, request, queryset):
        queryset.update(vetado=True)

    @admin.action(description="Desvetar usuarios seleccionados")
    def desvetar_usuarios(self, request, queryset):
        queryset.update(vetado=False)


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ('libro', 'usuario', 'estado', 'fecha_solicitud', 'fecha_aprobacion', 'fecha_vencimiento')
    list_filter = ('estado', 'fecha_solicitud')
    search_fields = ('libro__titulo', 'usuario__username', 'usuario__email')