# Prueba física del QR de sesión en la LAN

Esta prueba la realiza una persona con el nodo AulaLista y dos teléfonos. No
requiere Internet y debe ejecutarse con la WAN desconectada.

1. Conecta la computadora y ambos teléfonos a la misma red Wi-Fi local.
2. Verifica la dirección LAN de la computadora (por ejemplo,
   `192.168.1.20`) y configura explícitamente la base, sin inventar la
   dirección:

   ```sh
   AULALISTA_LAN_URL=http://192.168.1.20:8000 \
     python3.13 scripts/run_wsgi.py --host 0.0.0.0 --port 8000
   ```

3. En el navegador de la computadora, abre `/cms/login/`, prepara una sesión
y confírmala. Abre **modo activo** o **proyección pública**.
4. En el teléfono 1, escanea el QR. Debe abrir exactamente una dirección con
   esta forma:
   `http://192.168.1.20:8000/student/sessions/<id>/join/`.
5. En el teléfono 2, escribe la URL visible bajo el QR (sin escanearla). Debe
   llegar a la misma sesión. Comprueba que ambos teléfonos puedan continuar
   sin crear una cuenta.
6. Desconecta la WAN o bloquea la salida a Internet y repite los pasos 4 y 5.
   La incorporación debe seguir funcionando porque el enlace y el QR se
   sirven y resuelven dentro de la LAN.

Si `AULALISTA_LAN_URL` no está configurada, la interfaz muestra sólo el enlace
manual del host actual y un aviso de configuración; no presenta un QR ni
finge que `localhost` sea una dirección LAN. Corrige la configuración y
reinicia el servidor antes de la prueba física.
