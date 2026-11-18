import subprocess
import sys
import requests

URL_BASE = "http://127.0.0.1:8000"

def imprimir_titulo(texto):
    print("\n" + "=" * 60)
    print(f" 🛡️  {texto}")
    print("=" * 60)

# 1. VERIFICACIÓN NATIVA DE CONFIGURACIÓN DJANGO
def auditar_django():
    imprimir_titulo("1. REVISIÓN DE CONFIGURACIÓN DE DJANGO (check --deploy)")
    try:
        resultado = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy"],
            capture_output=True, text=True
        )
        print(resultado.stdout)
        if resultado.stderr:
            print(resultado.stderr)
    except Exception as e:
        print(f"Error al ejecutar check deployment: {e}")

# 2. ESCANEO DE DEPENDENCIAS CON VULNERABILIDADES (CVEs)
def auditar_dependencias():
    imprimir_titulo("2. AUDITORÍA DE LIBRERÍAS INSTALADAS (pip-audit)")
    try:
        resultado = subprocess.run(["pip-audit"], capture_output=True, text=True)
        print(resultado.stdout)
        if resultado.stderr and "No conocidos" not in resultado.stderr:
            print(resultado.stderr)
    except Exception as e:
        print(f"Error al ejecutar pip-audit: {e}")

# 3. ANÁLISIS ESTÁTICO DE CÓDIGO PYTHON
def auditar_codigo_bandit():
    imprimir_titulo("3. ESCANEO DE CÓDIGO FUENTE PYTHON (Bandit)")
    try:
        resultado = subprocess.run(
            ["bandit", "-r", "principal", "-ll"], 
            capture_output=True, text=True
        )
        print(resultado.stdout)
    except Exception as e:
        print(f"Error al ejecutar Bandit: {e}")

# 4. PRUEBAS DINÁMICAS HTTP EN VIVO
def auditar_cabeceras_y_rutas():
    imprimir_titulo("4. PRUEBAS DINÁMICAS HTTP EN VIVO")
    
    try:
        res = requests.get(URL_BASE, timeout=10)
        headers = res.headers
        
        print(f"[-] Verificando servidor activo en {URL_BASE}... Status: {res.status_code}")
        
        # Cabeceras esenciales de seguridad
        cabeceras_requeridas = [
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Referrer-Policy"
        ]
        
        print("\n[ Cabeceras de Seguridad ]")
        for h in cabeceras_requeridas:
            if h in headers:
                print(f"  ✅ {h}: {headers[h]}")
            else:
                print(f"  ❌ Faltante: {h}")
                
        # Prueba de protección CSRF en la ruta raíz ('/')
        print("\n[ Protección CSRF ]")
        res_post = requests.post(f"{URL_BASE}/", data={"correo": "test@test.com"}, timeout=10)
        if res_post.status_code in [403, 405]:
            print(f"  ✅ Protección CSRF / Métodos activos (Status {res_post.status_code} ante POST sin token)")
        else:
            print(f"  ⚠️ Respuesta POST sin token: Status {res_post.status_code}")

        # Prueba de Rutas Administrativas Protegidas ('/gestion/')
        print("\n[ Control de Acceso ]")
        res_admin = requests.get(f"{URL_BASE}/gestion/", allow_redirects=False, timeout=10)
        if res_admin.status_code in [302, 403, 401]:
            print(f"  ✅ Vista administrativa protegida (Status {res_admin.status_code}: Redirige/Deniega acceso a usuarios anónimos)")
        else:
            print(f"  ⚠️ Status en ruta protegida: {res_admin.status_code}")

    except requests.exceptions.ConnectionError:
        print("  ⚠️ El servidor local no está en ejecución. Inicia 'python manage.py runserver' primero.")

if __name__ == "__main__":
    print("🚀 INICIANDO AUDITORÍA INTEGRAL DE SEGURIDAD")
    auditar_django()
    auditar_dependencias()
    auditar_codigo_bandit()
    auditar_cabeceras_y_rutas()
    print("\n✅ Auditoría finalizada.")