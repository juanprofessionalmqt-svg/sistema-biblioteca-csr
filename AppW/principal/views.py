import json
import random
from datetime import timedelta
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Libro, Articulo, Cuenta, MapaBiblioteca, Prestamo

from email_validator import validate_email, EmailNotValidError

DOMINIOS_DESECHABLES_BLOQUEADOS = [
    'tempmail.com', '10minutemail.com', 'yopmail.com', 'guerrillamail.com',
    'sharklasers.com', 'dispostable.com', 'mailinator.com', 'trashmail.com'
]

LISTA_ADMINS_CSR = [
    'soportebiblioteca@colredentorista.edu.co',
]

LISTA_PROFESORES_CSR = [
    'profesor1@colredentorista.edu.co',
    'profesor2@colredentorista.edu.co',
    'coordinacion@colredentorista.edu.co',
]


def obtener_rol_por_correo(correo):
    correo = correo.lower().strip()
    if correo in LISTA_ADMINS_CSR:
        return 'Administrador'
    elif correo in LISTA_PROFESORES_CSR:
        return 'Profesor'
    elif correo.endswith('@colredentorista.edu.co'):
        return 'Estudiante'
    else:
        return 'Externo'


def obtener_o_crear_cuenta(user):
    cuenta = getattr(user, 'cuenta', None)
    if not cuenta:
        rol_auto = obtener_rol_por_correo(user.email)
        cuenta, _ = Cuenta.objects.get_or_create(
            user=user,
            defaults={
                'nombre': user.first_name or user.username,
                'apellido': user.last_name or '',
                'correo': user.email,
                'rol': rol_auto
            }
        )
    return cuenta


def obtener_rol_activo(request):
    cuenta = obtener_o_crear_cuenta(request.user)
    return cuenta.rol if cuenta else 'Externo'


def verificar_vetado(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            cuenta = obtener_o_crear_cuenta(request.user)
            if cuenta and cuenta.vetado:
                return render(request, 'usuario_vetado.html')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def actualizar_estados_prestamos():
    ahora = timezone.now()
    limite_24h = ahora + timedelta(days=1)
    remitente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@colredentorista.edu.co')

    # 1. Enviar notificación por correo cuando quede 1 día (24 horas) o menos para la fecha de entrega
    prestamos_por_vencer = Prestamo.objects.filter(
        estado__in=['En progreso', 'Prestado'],
        fecha_vencimiento__isnull=False,
        fecha_vencimiento__gt=ahora,
        fecha_vencimiento__lte=limite_24h,
        recordatorio_enviado=False
    ).select_related('libro', 'usuario')

    for prestamo in prestamos_por_vencer:
        correo_usuario = prestamo.usuario.email
        if correo_usuario:
            titulo_libro = prestamo.libro.titulo if prestamo.libro else "Documento"
            fecha_fmt = prestamo.fecha_vencimiento.strftime('%d/%m/%Y a las %H:%M')
            
            asunto = f"⚠️ Advertencia de vencimiento: «{titulo_libro}» - Biblioteca CSR"
            mensaje = (
                f"Hola {prestamo.usuario.first_name or prestamo.usuario.username},\n\n"
                f"Su libro «{titulo_libro}» está a punto de vencer su fecha de caducidad ({fecha_fmt}), "
                f"por lo que le vamos a aplicar una sanción si no lo entrega a tiempo.\n\n"
                f"Por favor, acércate a la biblioteca para realizar la entrega a tiempo o solicita una extensión de plazo desde la plataforma.\n\n"
                f"Atentamente,\n"
                f"Equipo de la Biblioteca CSR"
            )
            try:
                # Usamos fail_silently=False para usar el backend SMTP activo igual que con el OTP
                send_mail(asunto, mensaje, remitente, [correo_usuario], fail_silently=False)
                prestamo.recordatorio_enviado = True
                prestamo.save()
            except Exception as e:
                print(f"Error al enviar correo de aviso a {correo_usuario}: {e}")

    # 2. Préstamos vencidos que superaron la fecha límite -> pasan a En devolución
    prestamos_vencidos = Prestamo.objects.filter(
        estado__in=['En progreso', 'Prestado'], 
        fecha_vencimiento__lt=ahora
    )
    for prestamo in prestamos_vencidos:
        prestamo.estado = 'En devolucion'
        prestamo.save()

        if prestamo.libro:
            prestamo.libro.estado = 'En devolucion'
            prestamo.libro.save()

        cuenta = getattr(prestamo.usuario, 'cuenta', None)
        if cuenta:
            cuenta.vetado = True
            cuenta.save()


@login_required(login_url='login')
@verificar_vetado
def modificar_tiempo_prestamo(request, prestamo_id):
    if request.method == 'POST':
        prestamo = get_object_or_404(Prestamo, id=prestamo_id)
        rol_actual = obtener_rol_activo(request)
        
        if rol_actual != 'Administrador' and prestamo.usuario != request.user:
            messages.error(request, 'No tienes permisos para modificar este tiempo de préstamo.')
            return redirect(request.META.get('HTTP_REFERER', 'guardados'))

        dias = request.POST.get('dias')
        
        if dias:
            try:
                dias_int = int(dias)
                base_fecha = prestamo.fecha_vencimiento or timezone.now()
                nueva_fecha = base_fecha + timedelta(days=dias_int)
                prestamo.fecha_vencimiento = nueva_fecha
                
                ahora = timezone.now()

                # Si con la prórroga el plazo sobrepasa nuevamente las 24 horas, reactivar la alerta de correo futura
                if nueva_fecha > ahora + timedelta(days=1):
                    prestamo.recordatorio_enviado = False

                if nueva_fecha > ahora and prestamo.estado in ['En devolucion', 'Vencido']:
                    prestamo.estado = 'Prestado'
                    if prestamo.libro:
                        prestamo.libro.estado = 'Prestado'
                        prestamo.libro.save()
                    cuenta = getattr(prestamo.usuario, 'cuenta', None)
                    if cuenta:
                        otros_vencidos = Prestamo.objects.filter(
                            usuario=prestamo.usuario,
                            estado__in=['En devolucion', 'Vencido']
                        ).exclude(id=prestamo.id).exists()
                        if not otros_vencidos:
                            cuenta.vetado = False
                            cuenta.save()
                elif nueva_fecha <= ahora and prestamo.estado in ['Prestado', 'En progreso']:
                    prestamo.estado = 'En devolucion'
                    if prestamo.libro:
                        prestamo.libro.estado = 'En devolucion'
                        prestamo.libro.save()
                    cuenta = getattr(prestamo.usuario, 'cuenta', None)
                    if cuenta:
                        cuenta.vetado = True
                        cuenta.save()

                prestamo.save()
                
                if dias_int > 0:
                    messages.success(request, f'Se han sumado {dias_int} día(s) al plazo del préstamo.')
                elif dias_int < 0:
                    messages.success(request, f'Se han restado {abs(dias_int)} día(s) al plazo del préstamo.')
            except ValueError:
                messages.error(request, 'El número de días proporcionado no es válido.')

    return redirect(request.META.get('HTTP_REFERER', 'guardados'))


def obtener_mapa_api(request):
    mapa_obj, _ = MapaBiblioteca.objects.get_or_create(id=1)
    return JsonResponse({'elementos': mapa_obj.estructura or []})


@login_required(login_url='login')
@verificar_vetado
def guardar_mapa_api(request):
    if request.method == 'POST':
        rol_actual = obtener_rol_activo(request)
        if rol_actual != 'Administrador':
            return JsonResponse({'status': 'denegado', 'mensaje': 'Sin permisos para editar el mapa.'}, status=403)
        try:
            datos = json.loads(request.body)
            mapa_obj, _ = MapaBiblioteca.objects.get_or_create(id=1)
            mapa_obj.estructura = datos.get('elementos', [])
            mapa_obj.save()
            return JsonResponse({'status': 'exito'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'mensaje': str(e)}, status=400)
    return JsonResponse({'status': 'metodo_no_permitido'}, status=405)


def login_view(request):
    if request.user.is_authenticated:
        cuenta = obtener_o_crear_cuenta(request.user)
        if cuenta and cuenta.vetado:
            return render(request, 'usuario_vetado.html')
        return redirect('inicio')

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip().lower()
        password = request.POST.get('password', '')

        user_obj = User.objects.filter(email__iexact=correo).first()
        user = None
        if user_obj:
            user = authenticate(username=user_obj.username, password=password)

        if user is not None:
            login(request, user)
            cuenta = obtener_o_crear_cuenta(user)
            if cuenta and cuenta.vetado:
                return render(request, 'usuario_vetado.html')
            messages.success(request, f'¡Bienvenido de nuevo, {user.first_name or user.username}!')
            return redirect('inicio')
        else:
            messages.error(request, 'Correo electrónico o contraseña incorrectos.')

    articulos = Articulo.objects.all().order_by('-id')
    return render(request, 'login.html', {
        'articulos': articulos,
        'modo_registro': False,
        'modo_otp': False
    })


def registro_view(request):
    if request.user.is_authenticated:
        cuenta = obtener_o_crear_cuenta(request.user)
        if cuenta and cuenta.vetado:
            return render(request, 'usuario_vetado.html')
        return redirect('inicio')

    articulos = Articulo.objects.all().order_by('-id')

    if request.method == 'POST':
        paso_otp = request.POST.get('paso_otp')

        if paso_otp == 'confirmar':
            codigo_ingresado = request.POST.get('otp_code', '').strip()
            datos_pendientes = request.session.get('registro_pendiente')

            if not datos_pendientes:
                messages.error(request, 'La sesión de registro ha expirado. Por favor, intenta de nuevo.')
                return render(request, 'login.html', {'articulos': articulos, 'modo_registro': True, 'modo_otp': False})

            if codigo_ingresado == str(datos_pendientes.get('otp')):
                correo = datos_pendientes['correo']
                nombre = datos_pendientes['nombre']
                apellido = datos_pendientes['apellido']
                password = datos_pendientes['password']

                rol_asignado = obtener_rol_por_correo(correo)

                base_username = correo.split('@')[0]
                username = base_username
                contador = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{contador}"
                    contador += 1

                user = User.objects.create_user(
                    username=username,
                    email=correo,
                    password=password,
                    first_name=nombre,
                    last_name=apellido
                )

                Cuenta.objects.create(
                    user=user,
                    nombre=nombre,
                    apellido=apellido,
                    correo=correo,
                    rol=rol_asignado
                )

                del request.session['registro_pendiente']

                user_auth = authenticate(username=username, password=password)
                if user_auth:
                    login(request, user_auth)

                messages.success(request, f'¡Cuenta verificada y creada exitosamente con el rol de {rol_asignado}!')
                return redirect('inicio')
            else:
                messages.error(request, 'El código OTP es incorrecto.')
                return render(request, 'login.html', {
                    'articulos': articulos,
                    'modo_registro': False,
                    'modo_otp': True,
                    'correo_otp': datos_pendientes.get('correo')
                })

        elif paso_otp == 'cancelar':
            if 'registro_pendiente' in request.session:
                del request.session['registro_pendiente']
            return redirect('login')

        else:
            nombre = request.POST.get('nombre', '').strip()
            prefiero_no_apellido = request.POST.get('prefiero_no_apellido')
            apellido = 'No especificado' if prefiero_no_apellido else request.POST.get('apellido', '').strip()
            correo = request.POST.get('correo', '').strip().lower()
            password = request.POST.get('password', '')

            if User.objects.filter(email__iexact=correo).exists():
                messages.error(request, 'Ya existe una cuenta registrada con este correo electrónico.')
                return render(request, 'login.html', {'articulos': articulos, 'modo_registro': True, 'modo_otp': False})

            dominio = correo.split('@')[-1] if '@' in correo else ''
            if dominio in DOMINIOS_DESECHABLES_BLOQUEADOS:
                messages.error(request, 'No se permiten registros con correos desechables.')
                return render(request, 'login.html', {'articulos': articulos, 'modo_registro': True, 'modo_otp': False})

            try:
                email_info = validate_email(correo, check_deliverability=True)
                correo = email_info.normalized
            except EmailNotValidError as e:
                messages.error(request, f'El correo no es válido: {str(e)}')
                return render(request, 'login.html', {'articulos': articulos, 'modo_registro': True, 'modo_otp': False})

            codigo_otp = str(random.randint(100000, 999999))

            request.session['registro_pendiente'] = {
                'nombre': nombre,
                'apellido': apellido,
                'correo': correo,
                'password': password,
                'otp': codigo_otp
            }

            try:
                asunto = "Código de Verificación OTP - Biblioteca CSR"
                mensaje = f"Tu código de verificación de 6 dígitos es: {codigo_otp}"
                remitente = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@colredentorista.edu.co')
                send_mail(asunto, mensaje, remitente, [correo], fail_silently=False)
                messages.success(request, f'Hemos enviado un código OTP a {correo}.')
            except Exception:
                messages.warning(request, f'Código OTP de prueba: {codigo_otp}')

            return render(request, 'login.html', {
                'articulos': articulos,
                'modo_registro': False,
                'modo_otp': True,
                'correo_otp': correo
            })

    return render(request, 'login.html', {
        'articulos': articulos,
        'modo_registro': True,
        'modo_otp': False
    })


def logout_view(request):
    logout(request)
    request.session.flush()
    messages.info(request, 'Has cerrado la sesión.')
    return redirect('login')


@login_required(login_url='login')
@verificar_vetado
def inicio(request):
    actualizar_estados_prestamos()
    query = request.GET.get('q', '').strip()
    tipo_activo = request.GET.get('tipo', 'libros')
    rol_actual = obtener_rol_activo(request)

    libros = Libro.objects.none() if rol_actual == 'Externo' else Libro.objects.all()
    articulos = Articulo.objects.all()

    if query:
        if rol_actual != 'Externo':
            libros = libros.filter(
                Q(titulo__icontains=query) | Q(autor__icontains=query) | Q(ubicacion__icontains=query)
            )
        articulos = articulos.filter(Q(titulo__icontains=query) | Q(autor__icontains=query))

    prestamos_activos_count = Prestamo.objects.filter(
        usuario=request.user, 
        estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
    ).count()

    return render(request, 'index.html', {
        'libros': libros if tipo_activo == 'libros' else [],
        'articulos': articulos if tipo_activo == 'articulos' else [],
        'tipo_activo': tipo_activo,
        'query': query,
        'rol_actual': rol_actual,
        'prestamos_activos_count': prestamos_activos_count,
    })


@login_required(login_url='login')
@verificar_vetado
def subir_documento(request):
    rol_actual = obtener_rol_activo(request)

    if request.method == 'POST':
        if rol_actual == 'Externo':
            messages.error(request, 'Los usuarios con rol Externo no tienen permiso para publicar.')
            return redirect('subir_documento')

        tipo_documento = request.POST.get('tipo_documento')
        if tipo_documento == 'libro' and rol_actual != 'Administrador':
            messages.error(request, 'Solo los administradores pueden publicar libros.')
            return redirect('subir_documento')

        titulo = request.POST.get('titulo', '').strip()
        autor = request.POST.get('autor', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        archivo_pdf = request.FILES.get('archivo_pdf')
        imagen_portada = request.FILES.get('portada')

        if tipo_documento == 'libro':
            estado = request.POST.get('estado', 'Disponible')
            ubicacion = request.POST.get('ubicacion', 'Estante General - Piso 1').strip()
            
            try:
                posicion_x = int(request.POST.get('posicion_x', 50))
                posicion_y = int(request.POST.get('posicion_y', 50))
            except (ValueError, TypeError):
                posicion_x, posicion_y = 50, 50

            Libro.objects.create(
                titulo=titulo,
                autor=autor,
                descripcion=descripcion,
                archivo=archivo_pdf,
                portada=imagen_portada,
                estado=estado,
                ubicacion=ubicacion or 'Estante General - Piso 1',
                posicion_x=posicion_x,
                posicion_y=posicion_y,
                prestado_a=None
            )
            messages.success(request, 'El libro fue publicado con éxito.')
        else:
            Articulo.objects.create(
                titulo=titulo,
                autor=autor,
                resumen=descripcion,
                archivo=archivo_pdf,
                portada=imagen_portada,
                creado_por_rol=rol_actual
            )
            messages.success(request, 'El artículo fue publicado con éxito.')

        return redirect('inicio')

    return render(request, 'subir_documento.html')


@login_required(login_url='login')
@verificar_vetado
def panel_administracion(request):
    actualizar_estados_prestamos()
    rol_actual = obtener_rol_activo(request)
    
    if rol_actual != 'Administrador':
        messages.error(request, 'Acceso denegado.')
        return redirect('inicio')

    libros = Libro.objects.all()
    articulos = Articulo.objects.all()
    usuarios_list = User.objects.all().select_related('cuenta').order_by('-id')

    return render(request, 'panel_administracion.html', {
        'libros': libros,
        'articulos': articulos,
        'usuarios': usuarios_list,
    })


@login_required(login_url='login')
@verificar_vetado
def editar_documento(request, tipo, doc_id):
    rol_actual = obtener_rol_activo(request)
    
    if rol_actual != 'Administrador':
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('inicio')

    modelo = Libro if tipo == 'libro' else Articulo
    documento = get_object_or_404(modelo, id=doc_id)
    prestamo_activo = None

    if tipo == 'libro':
        prestamo_activo = Prestamo.objects.filter(
            libro=documento,
            estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
        ).select_related('usuario', 'usuario__cuenta').first()

    if request.method == 'POST':
        documento.titulo = request.POST.get('titulo', documento.titulo).strip()
        documento.autor = request.POST.get('autor', documento.autor).strip()
        
        if tipo == 'libro':
            documento.descripcion = request.POST.get('descripcion', documento.descripcion).strip()
            nuevo_estado = request.POST.get('estado', documento.estado)
            documento.estado = nuevo_estado
            
            if nuevo_estado == 'Disponible':
                documento.prestado_a = None
                Prestamo.objects.filter(
                    libro=documento,
                    estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
                ).update(estado='Devuelto', fecha_devolucion=timezone.now())
            elif nuevo_estado in ['Prestado', 'En progreso']:
                Prestamo.objects.filter(
                    libro=documento,
                    estado__in=['En revision', 'En progreso', 'En devolucion']
                ).update(
                    estado=nuevo_estado, 
                    fecha_aprobacion=timezone.now(),
                    fecha_vencimiento=timezone.now() + timedelta(days=5)
                )
            elif nuevo_estado == 'En devolucion':
                Prestamo.objects.filter(
                    libro=documento,
                    estado__in=['En revision', 'En progreso', 'Prestado']
                ).update(estado='En devolucion')

            documento.ubicacion = request.POST.get('ubicacion', documento.ubicacion).strip()
            
            try:
                pos_x = request.POST.get('posicion_x')
                pos_y = request.POST.get('posicion_y')
                if pos_x is not None and pos_x != '':
                    documento.posicion_x = int(pos_x)
                if pos_y is not None and pos_y != '':
                    documento.posicion_y = int(pos_y)
            except ValueError:
                pass
        else:
            documento.resumen = request.POST.get('descripcion', documento.resumen).strip()

        if request.FILES.get('portada'):
            documento.portada = request.FILES.get('portada')

        if request.FILES.get('archivo_pdf'):
            documento.archivo = request.FILES.get('archivo_pdf')

        documento.save()
        messages.success(request, f'{"El libro" if tipo == "libro" else "El artículo"} fue actualizado correctamente.')
        return redirect('panel_administracion')

    return render(request, 'editar_documento.html', {
        'documento': documento,
        'tipo': tipo,
        'prestamo_activo': prestamo_activo,
    })


@login_required(login_url='login')
@verificar_vetado
def eliminar_documento(request, tipo, doc_id):
    rol_actual = obtener_rol_activo(request)
    if rol_actual != 'Administrador':
        messages.error(request, 'No tienes permisos para eliminar este contenido.')
        return redirect('inicio')

    modelo = Libro if tipo == 'libro' else Articulo
    documento = get_object_or_404(modelo, id=doc_id)
    documento.delete()
    
    messages.success(request, f'{"El libro" if tipo == "libro" else "El artículo"} ha sido eliminado correctamente.')
    return redirect('panel_administracion')


@login_required(login_url='login')
@verificar_vetado
def editar_cuenta(request, cuenta_id):
    rol_actual = obtener_rol_activo(request)
    if rol_actual != 'Administrador':
        messages.error(request, 'Acceso denegado.')
        return redirect('inicio')

    cuenta = Cuenta.objects.filter(Q(id=cuenta_id) | Q(user_id=cuenta_id)).first()
    if not cuenta:
        user_obj = get_object_or_404(User, id=cuenta_id)
        cuenta = obtener_o_crear_cuenta(user_obj)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        correo = request.POST.get('correo', '').strip().lower()
        rol = request.POST.get('rol')
        vetado_input = request.POST.get('vetado')
        foto = request.FILES.get('foto_perfil')
        nueva_password = request.POST.get('password', '').strip()

        cuenta.nombre = nombre
        cuenta.apellido = apellido
        cuenta.correo = correo
        if rol:
            cuenta.rol = rol
            
        cuenta.vetado = True if vetado_input in ['on', 'true', True] else False
        if foto:
            cuenta.foto_perfil = foto
        cuenta.save()

        if cuenta.user:
            user = cuenta.user
            user.first_name = nombre
            user.last_name = apellido
            user.email = correo
            if nueva_password:
                if len(nueva_password) < 6:
                    messages.error(request, 'La nueva contraseña debe tener al menos 6 caracteres.')
                    return render(request, 'editar_cuenta.html', {'cuenta': cuenta})
                user.set_password(nueva_password)
            user.save()

        messages.success(request, f'¡La cuenta de {nombre or cuenta.user.username} fue actualizada con éxito!')
        return redirect('panel_administracion')

    return render(request, 'editar_cuenta.html', {'cuenta': cuenta})


@login_required(login_url='login')
@verificar_vetado
def desvetar_usuario(request, cuenta_id):
    rol_actual = obtener_rol_activo(request)
    if rol_actual != 'Administrador':
        messages.error(request, 'Acceso denegado.')
        return redirect('inicio')

    cuenta = Cuenta.objects.filter(Q(id=cuenta_id) | Q(user_id=cuenta_id)).first()
    if cuenta:
        cuenta.vetado = False
        cuenta.save()
        messages.success(request, f'Se ha quitado el veto al usuario {cuenta.nombre or cuenta.user.username}.')
    else:
        messages.error(request, 'No se encontró la cuenta.')

    return redirect('panel_administracion')


@login_required(login_url='login')
@verificar_vetado
def eliminar_cuenta(request, cuenta_id):
    rol_actual = obtener_rol_activo(request)
    if rol_actual != 'Administrador':
        messages.error(request, 'Acceso denegado.')
        return redirect('inicio')

    cuenta = Cuenta.objects.filter(Q(id=cuenta_id) | Q(user_id=cuenta_id)).first()
    if cuenta:
        if cuenta.user:
            cuenta.user.delete()
        else:
            cuenta.delete()
        messages.success(request, 'La cuenta ha sido eliminada.')
    else:
        user_obj = User.objects.filter(id=cuenta_id).first()
        if user_obj:
            user_obj.delete()
            messages.success(request, 'La cuenta ha sido eliminada.')

    return redirect('panel_administracion')


@login_required(login_url='login')
@verificar_vetado
def mi_cuenta(request):
    usuario = obtener_o_crear_cuenta(request.user)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        foto = request.FILES.get('foto_perfil')

        old_password = request.POST.get('old_password', '').strip()
        new_password1 = request.POST.get('new_password1', '').strip()
        new_password2 = request.POST.get('new_password2', '').strip()

        if nombre:
            usuario.nombre = nombre
            request.user.first_name = nombre
        if apellido != '':
            usuario.apellido = apellido
            request.user.last_name = apellido
        if foto:
            usuario.foto_perfil = foto

        usuario.save()
        request.user.save()

        if old_password or new_password1 or new_password2:
            if not old_password or not new_password1 or not new_password2:
                messages.error(request, 'Para cambiar contraseña completa todos los campos.')
                return redirect('mi_cuenta')

            if not request.user.check_password(old_password):
                messages.error(request, 'La contraseña actual es incorrecta.')
                return redirect('mi_cuenta')

            if new_password1 != new_password2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return redirect('mi_cuenta')

            if len(new_password1) < 6:
                messages.error(request, 'La contraseña debe tener al menos 6 caracteres.')
                return redirect('mi_cuenta')

            request.user.set_password(new_password1)
            request.user.save()
            update_session_auth_hash(request, request.user)

            messages.success(request, 'Perfil y contraseña actualizados.')
            return redirect('mi_cuenta')

        messages.success(request, 'Perfil actualizado correctamente.')
        return redirect('mi_cuenta')

    return render(request, 'centro_cuentas.html', {'usuario': usuario})


@login_required(login_url='login')
@verificar_vetado
def guardados(request):
    actualizar_estados_prestamos()
    prestamos_activos = Prestamo.objects.filter(
        usuario=request.user, 
        estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
    ).select_related('libro', 'usuario')
    return render(request, 'guardados.html', {
        'prestamos': prestamos_activos
    })


@login_required(login_url='login')
@verificar_vetado
def historial(request):
    actualizar_estados_prestamos()
    rol_actual = obtener_rol_activo(request)
    
    if rol_actual == 'Administrador':
        historial_prestamos = Prestamo.objects.all().select_related('libro', 'usuario', 'usuario__cuenta').order_by('-id')
    else:
        historial_prestamos = Prestamo.objects.filter(usuario=request.user).select_related('libro', 'usuario', 'usuario__cuenta').order_by('-id')
        
    return render(request, 'historial.html', {
        'historial_prestamos': historial_prestamos,
        'rol_actual': rol_actual
    })


@login_required(login_url='login')
@verificar_vetado
def solicitar_prestamo(request, libro_id):
    if request.method != 'POST':
        return redirect('inicio')

    actualizar_estados_prestamos()
    libro = get_object_or_404(Libro, id=libro_id)

    ya_solicitado = Prestamo.objects.filter(
        usuario=request.user,
        libro=libro,
        estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
    ).exists()

    if ya_solicitado:
        messages.error(request, f'Ya tienes una solicitud activa para "{libro.titulo}".')
        return redirect('inicio')

    prestamos_activos_count = Prestamo.objects.filter(
        usuario=request.user, 
        estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
    ).count()

    if prestamos_activos_count >= 2:
        messages.error(request, 'Has alcanzado el límite máximo de 2 préstamos/solicitudes activas.')
    elif libro.estado != 'Disponible':
        messages.error(request, f'El libro "{libro.titulo}" no está disponible actualmente.')
    else:
        libro.estado = 'En revision'
        libro.prestado_a = request.user
        libro.save()

        Prestamo.objects.create(
            libro=libro,
            usuario=request.user,
            estado='En revision'
        )
        messages.success(request, f'Solicitud enviada para "{libro.titulo}".')
            
    return redirect('inicio')


@login_required(login_url='login')
@verificar_vetado
def aprobar_prestamo(request, prestamo_id):
    rol_actual = obtener_rol_activo(request)
    if rol_actual != 'Administrador':
        messages.error(request, 'Acceso denegado.')
        return redirect('inicio')

    prestamo = get_object_or_404(Prestamo, id=prestamo_id)
    ahora = timezone.now()

    prestamo.estado = 'Prestado'
    prestamo.fecha_aprobacion = ahora
    prestamo.fecha_vencimiento = ahora + timedelta(days=5)
    prestamo.recordatorio_enviado = False
    prestamo.save()

    libro = prestamo.libro
    if libro:
        libro.estado = 'Prestado'
        libro.prestado_a = prestamo.usuario
        libro.save()

    messages.success(request, f'El libro "{libro.titulo if libro else ""}" fue APROBADO por un plazo de 5 días.')
    return redirect('historial')


@login_required(login_url='login')
@verificar_vetado
def devolver_libro(request, libro_id):
    actualizar_estados_prestamos()
    libro = get_object_or_404(Libro, id=libro_id)
    rol_actual = obtener_rol_activo(request)

    if libro.prestado_a == request.user or rol_actual == 'Administrador':
        prestamos_activos = Prestamo.objects.filter(
            libro=libro, 
            estado__in=['En revision', 'En progreso', 'Prestado', 'En devolucion', 'Vencido']
        )

        for prestamo in prestamos_activos:
            prestamo.estado = 'Devuelto'
            prestamo.fecha_devolucion = timezone.now()
            prestamo.save()

        libro.estado = 'Disponible'
        libro.prestado_a = None
        libro.save()

        messages.success(request, f'El libro "{libro.titulo}" ha sido devuelto y está Disponible.')
    else:
        messages.error(request, 'No tienes permisos para realizar esta acción.')

    return redirect('historial')