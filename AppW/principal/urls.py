from django.urls import path
from . import views

urlpatterns = [
    # Autenticación y Cuentas
    path('', views.login_view, name='login'),
    path('registro/', views.registro_view, name='registro'),
    path('logout/', views.logout_view, name='logout'),
    
    # Navegación del Catálogo y Perfil
    path('inicio/', views.inicio, name='inicio'),
    path('subir/', views.subir_documento, name='subir_documento'),
    path('cuenta/', views.mi_cuenta, name='mi_cuenta'),
    path('guardados/', views.guardados, name='guardados'),
    path('historial/', views.historial, name='historial'),
    
    # Endpoints API para Persistencia del Mapa Global
    path('api/mapa/obtener/', views.obtener_mapa_api, name='obtener_mapa_api'),
    path('api/mapa/guardar/', views.guardar_mapa_api, name='guardar_mapa_api'),
    
    # Gestión de Libros y Artículos
    path('gestion/', views.panel_administracion, name='panel_administracion'),
    path('editar/<str:tipo>/<int:doc_id>/', views.editar_documento, name='editar_documento'),
    path('eliminar/<str:tipo>/<int:doc_id>/', views.eliminar_documento, name='eliminar_documento'),

    # Gestión de Cuentas de Usuario
    path('panel-admin/cuenta/editar/<int:cuenta_id>/', views.editar_cuenta, name='editar_cuenta'),
    path('panel-admin/cuenta/desvetar/<int:cuenta_id>/', views.desvetar_usuario, name='desvetar_usuario'),
    path('panel-admin/cuenta/eliminar/<int:cuenta_id>/', views.eliminar_cuenta, name='eliminar_cuenta'),

    # Flujo de Préstamos, Modificación de Tiempo y Devoluciones
    path('solicitar-prestamo/<int:libro_id>/', views.solicitar_prestamo, name='solicitar_prestamo'),
    path('aprobar-prestamo/<int:prestamo_id>/', views.aprobar_prestamo, name='aprobar_prestamo'),
    path('modificar-tiempo/<int:prestamo_id>/', views.modificar_tiempo_prestamo, name='modificar_tiempo_prestamo'),
    path('devolver-libro/<int:libro_id>/', views.devolver_libro, name='devolver_libro'),
]