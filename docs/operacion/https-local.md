# HTTPS en local con mkcert

Sirve para entrar en Kapataz por HTTPS desde el portátil y desde un móvil real en la misma red local, sin servicios externos, sin túneles y sin exponer nada a internet. Es lo que exige el criterio de terminado del Bloque 1: «en local, por HTTPS, se inicia sesión desde un portátil y desde un móvil real y el chat responde con el `FakeLlm`» (plan maestro, §1.5; ADR-014).

Úsalo solo en una red de confianza (la de casa, nunca una wifi pública) y solo con datos sintéticos.

## 1. Qué se monta

`sh deploy/local-up.sh --https <IP>` hace lo mismo que `sh deploy/local-up.sh` y además:

- **Certificado:** con mkcert, en `.local-tls/`, para la IP del portátil, `localhost` y `127.0.0.1`. La carpeta está en `.gitignore` y en `.dockerignore`. Se regenera sola si cambia la IP o la autoridad de mkcert.
- **Proxy `kapataz-local-tls`:**
  - `nginxinc/nginx-unprivileged`, fijada por digest, con la misma versión de nginx que KronoQR (1.31.7).
  - Sin root, con sistema de ficheros de solo lectura, `cap_drop: ALL` y `no-new-privileges`.
  - Solo está en la red `kronoqr-app` y llega a `http://kapataz:8000` por nombre, como el nginx de producción.
  - Su configuración, `deploy/local-tls/kapataz.conf`, es el bloque de `despliegue.md` §10. Las únicas diferencias, por ser local, están comentadas en el propio fichero.
  - Publica el puerto 8443 solo en `127.0.0.1` y en la IP que le pases. No escucha en ninguna otra interfaz del portátil.
- **La app**, con:
  - `COOKIE_SECURE=true`;
  - `PUBLIC_BASE_URL=https://<IP>:8443`;
  - `FORWARDED_ALLOW_IPS` igual a la subred real de `kronoqr-app` en el portátil (el 17/11/2026, `172.28.0.0/16`; en el servidor se espera `172.18.0.0/16`). Nunca `*`.

`http://localhost:8000` sigue publicado en el bucle local, pero con cookies `Secure` la sesión por HTTP no es fiable. En modo HTTPS, entra siempre por el 8443.

Contenido de `.local-tls/`:

| Fichero | Qué es | ¿Secreto? |
|---|---|---|
| `cert.pem` | Certificado del servidor | No |
| `key.pem` | Clave privada del certificado | Sí: no sale del portátil |
| `rootCA.pem`, `rootCA.crt` | Copia del certificado público de la autoridad de mkcert, para instalarlo en el móvil. Es el mismo fichero con dos extensiones | No |
| `hosts` | Nombres para los que se generó el certificado | No |

## 2. Instalar mkcert en Windows (una sola vez)

En PowerShell:

```powershell
winget install FiloSottile.mkcert
```

Cierra la terminal y abre otra, para que cargue el `PATH` nuevo. Después:

```powershell
mkcert -install
```

`mkcert -install` crea una autoridad de certificación local y la añade al almacén de confianza de Windows. Windows pide confirmación con un aviso de seguridad. Chrome y Edge usan ese almacén. Si Firefox no la reconoce, activa `security.enterprise_roots.enabled` en `about:config`.

La autoridad se guarda en la carpeta que indica `mkcert -CAROOT` (normalmente `%LOCALAPPDATA%\mkcert`).

> **`rootCA-key.pem` nunca sale del portátil.** Quien tenga esa clave puede suplantar cualquier web ante los dispositivos que confían en tu autoridad. No la copies al móvil ni al repositorio, ni a una nube ni a una copia de seguridad compartida. Al móvil solo va `rootCA.pem`.
>
> Si crees que se ha filtrado: ejecuta `mkcert -uninstall`, borra la carpeta de `mkcert -CAROOT`, quita la autoridad de los móviles (secciones 5 y 6) y repite esta sección.

## 3. Generar el certificado y arrancar

1. Busca la IP del portátil en la red local con `ipconfig`: es la «Dirección IPv4» del adaptador Wi-Fi o Ethernet conectado al router (por ejemplo, `192.168.1.50`). No uses las de `vEthernet (WSL)` ni `vEthernet (Default Switch)`. El script no la adivina, y solo admite direcciones privadas (`10.x`, `172.16-31.x` y `192.168.x`).
2. En Git Bash, desde la raíz del repositorio:

   ```sh
   cp .env.local.example .env.local      # la primera vez
   sh deploy/local-up.sh --https 192.168.1.50
   ```

   Al final, el script escribe `listo: https://192.168.1.50:8443`.

- **Si cambia la IP** (otra red o una IP nueva del router), repite la orden con la IP nueva. El script regenera el certificado y recrea la app con la `PUBLIC_BASE_URL` nueva. Una reserva DHCP en el router evita repetirlo.
- **Para volver al modo HTTP:** `sh deploy/local-up.sh`. Para el proxy y la app vuelve a `http://localhost:8000` con `COOKIE_SECURE=false`.
- **Para pararlo todo:**

  ```sh
  docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml --profile https down
  ```

  Sin `--profile https`, `down` deja el proxy en marcha.

> **En el portátil, entra por la IP o por `https://127.0.0.1:8443`, no por `https://localhost:8443`.** La app envía HSTS. Los navegadores lo ignoran para las IP, pero no para `localhost`: después, el navegador forzaría HTTPS también en `http://localhost:8000`, y el modo HTTP dejaría de funcionar. Si ya ha pasado, en Chrome o Edge abre `chrome://net-internals/#hsts` y borra `localhost` en «Delete domain security policies».

## 4. Cortafuegos de Windows

El móvil solo llega al 8443 si Windows lo permite, y solo debe permitirlo en redes privadas.

1. **Perfil de la red.** En Configuración > Red e Internet > Wi-Fi (o Ethernet) > la red conectada, comprueba que «Tipo de perfil de red» es **Privada**. Márcala como privada solo si es tu red de confianza. El 17/11/2026 la Ethernet del portátil estaba como **Pública**: con ese perfil, la regla de abajo no se aplica y el móvil no conecta.
2. **Regla de entrada**, en PowerShell como administrador:

   ```powershell
   New-NetFirewallRule -DisplayName "Kapataz HTTPS local (8443)" `
     -Direction Inbound -Protocol TCP -LocalPort 8443 `
     -RemoteAddress LocalSubnet -Profile Private -Action Allow
   ```

   `-RemoteAddress LocalSubnet` limita la regla a los dispositivos de tu misma subred.
3. Si Windows muestra un aviso del cortafuegos para Docker Desktop la primera vez, permite el acceso solo en **redes privadas**.
4. Para comprobar la regla y quitarla al terminar:

   ```powershell
   Get-NetFirewallRule -DisplayName "Kapataz HTTPS local (8443)" | Format-List DisplayName,Enabled,Profile,Action
   Remove-NetFirewallRule -DisplayName "Kapataz HTTPS local (8443)"
   ```

No abras el 8443 en el router: no se reenvía ningún puerto a internet.

## 5. Android

1. Copia `.local-tls/rootCA.crt` al móvil, por cable USB o por cualquier otro medio. Es un certificado público, pero comprueba su huella antes de instalarlo (paso 3).
2. En Ajustes, busca «certificado CA». Normalmente está en Seguridad y privacidad > Más ajustes de seguridad > Cifrado y credenciales > Instalar un certificado > **Certificado de CA**. Acepta el aviso y elige `rootCA.crt`. La ruta cambia según el fabricante.
3. Comprueba la huella. En el portátil, con Git Bash:

   ```sh
   openssl x509 -in .local-tls/rootCA.pem -noout -fingerprint -sha256
   ```

   En el móvil, en Cifrado y credenciales > Credenciales de confianza > **Usuario** > «mkcert …», la huella SHA-256 debe ser la misma.
4. Chrome para Android confía en las autoridades de usuario, así que no hace falta nada más. Otras apps y navegadores pueden no hacerlo; usa Chrome.
5. Para quitarla al terminar: Credenciales de confianza > Usuario > «mkcert …» > Quitar.

## 6. iPhone

1. Pasa `.local-tls/rootCA.crt` al iPhone, por ejemplo enviándotelo por correo y abriendo el adjunto en la app Mail, o desde la app Archivos. Al abrirlo aparece «Perfil descargado».
2. Ve a Ajustes > General > VPN y gestión de dispositivos, abre el perfil «mkcert …» y pulsa **Instalar**. En el detalle del certificado, comprueba que la huella SHA-256 coincide con la del paso 3 de Android.
3. **Activa la confianza total**, porque sin este paso Safari no confía: Ajustes > General > Información > **Ajustes de confianza de certificados** > activa «mkcert …».
4. Para quitarlo al terminar: Ajustes > General > VPN y gestión de dispositivos > el perfil > Eliminar perfil.

## 7. Comprobar el criterio de terminado del Bloque 1

1. **Cuenta de prueba.** El registro está cerrado (RN-13), así que se crea con `kapataz-admin`, con un email sintético. Se lanza desde PowerShell, que pide la contraseña con una terminal real:

   ```powershell
   docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml run --rm --no-deps kapataz-tools kapataz-admin create-user --email demo@example.com
   ```

2. **Desde el portátil:** abre `https://<IP>:8443` en Chrome o Edge.
   - Hay candado y ningún aviso.
   - Inicias sesión.
   - En DevTools > Application > Cookies, `kapataz_session` tiene `Secure` y `HttpOnly`.
   - Envías un mensaje en el chat y la respuesta del `FakeLlm` llega palabra a palabra, no de golpe.
3. **Desde el móvil**, en la misma wifi: abre `https://<IP>:8443`. Sin aviso de certificado, inicias sesión y el chat responde palabra a palabra.
4. **Desde Git Bash**, sin `-k`: el `curl` de Git para Windows usa el almacén de Windows, así que comprueba también la confianza.

   ```sh
   curl -s https://<IP>:8443/api/health                                   # 200 y "status":"ok"
   curl -sI https://<IP>:8443/ | grep -ci strict-transport-security       # 1: HSTS una sola vez
   ```

5. **Anota el resultado en el PR del Bloque 1:** fecha, modelo y sistema del móvil, navegador y resultado.

## 8. Límites

- **Nada en internet.** El proxy solo escucha en `127.0.0.1` y en la IP local, y el router no reenvía ningún puerto. No se usan túneles.
- **Mientras lo usas:** solo datos sintéticos, con el registro cerrado, el `FakeLlm` y sin clave de la API de Claude.
- **Al terminar:** vuelve al modo HTTP o para el entorno, y quita la regla del cortafuegos si ya no la necesitas.
- **IP del cliente.** En local no se puede comprobar con la IP real. Docker Desktop traduce las conexiones entrantes, y nginx ve siempre la puerta de enlace de `kronoqr-app` (`172.28.0.1`), que está dentro de la subred de confianza. Por eso, en local, uvicorn acepta un `X-Forwarded-For` que envíe el propio cliente. La IP real se comprueba en producción con `tests/e2e_api/test_transporte.py` (Bloque 12).

## 9. Problemas frecuentes

- **`falta mkcert`:** instálalo (sección 2) y abre una terminal nueva.
- **`mkcert no tiene autoridad local`:** ejecuta `mkcert -install`.
- **`no es una IPv4 privada`:** pasa la IP del adaptador Wi-Fi o Ethernet, no la pública ni la de WSL.
- **El proxy no arranca, con `cannot assign requested address`:** la IP ya no es del portátil. Mírala con `ipconfig` y repite la orden.
- **El móvil no conecta** (se queda cargando):
  - comprueba que está en la misma red, no en la de invitados;
  - que el perfil de la red es Privada y que existe la regla del cortafuegos;
  - que el router no tiene activado el «aislamiento de clientes» (AP isolation).
- **El móvil avisa de que la conexión no es privada:**
  - la autoridad no está instalada o, en el iPhone, falta la confianza total (sección 6, paso 3);
  - o el certificado es de otra autoridad: has repetido `mkcert -install` en otro equipo o tras borrar la carpeta.
- **`502`:** `kapataz` no está sano. Revisa los logs con `docker compose ... logs kapataz`.
- **El chat llega de golpe:** hay búfer en algún punto. Compara con el bloque de §10 de `despliegue.md`: `proxy_buffering off` y nada de `gzip` para `text/event-stream`.

## 10. Prueba en local (17/11/2026)

Hecha sin mkcert, con un certificado autofirmado de usar y tirar en `.local-tls/`, que se borró al terminar:

- **Configuración:** `docker compose config` es válido en los dos modos, y el modo HTTP mantiene `COOKIE_SECURE=false`, `PUBLIC_BASE_URL=http://localhost:8000` y `FORWARDED_ALLOW_IPS=127.0.0.1`.
- **Proxy:**
  - corre como uid 101, con raíz de solo lectura, `CapDrop=[ALL]` y `no-new-privileges`;
  - `nginx -t` es correcto y negocia HTTP/2;
  - publica solo en `127.0.0.1:8443` y en la IP local; desde otra interfaz no responde.
- **Respuestas por HTTPS:**
  - `/api/health` responde `200`, con HSTS una sola vez, CSP y el resto de cabeceras de seguridad;
  - HTTP plano al 8443 redirige con `301` a HTTPS;
  - sin `kapataz`, el proxy responde `502`, y vuelve a `200` cuando `kapataz` vuelve, sin recargar nginx.
- **Sesión y chat:**
  - las cookies `kapataz_csrf` y `kapataz_session` llevan `Secure`;
  - el chat por SSE da el primer byte a los 0,015 s, con un total de 0,83 s, así que no hay búfer.
- **Cabeceras reenviadas:** con un servicio de eco en el lugar de `kapataz`, uvicorn ve `scheme=https`, el `Host` con el puerto y como cliente la IP que pone nginx.
- **Modo HTTP:** al volver a él, el proxy se para, `http://localhost:8000` responde, la sesión funciona sin `Secure` y el chat responde.
