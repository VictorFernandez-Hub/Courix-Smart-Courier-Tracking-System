# Courrier Express

Sistema de gestión para una empresa de courier: recepción en almacén, asignación a repartidores, rutas, entrega con cobro contra entrega, liquidación de caja, incidencias y rastreo público.

- **Backend:** Flask 3 + SQLAlchemy + MySQL/MariaDB, JWT con refresh token, Alembic (`backend/`).
- **Frontend:** React 18 + Vite (`frontend/`).

## Estructura

```
Courrier Express/
├── backend/
│   ├── app/                    ← paquete de la aplicación
│   │   ├── __init__.py         ← crear_app(): arma la app y registra todo
│   │   ├── config.py           ← configuración desde .env (+ validaciones de producción)
│   │   ├── extensions.py       ← base de datos, JWT, rate limit, migraciones
│   │   ├── reglas.py           ← reglas de negocio puras (estados, tarifas, catálogos)
│   │   ├── servicios.py        ← operaciones compartidas (asignación, caja, consultas)
│   │   ├── schemas.py          ← serialización modelo → JSON
│   │   ├── cli.py              ← comandos: flask sembrar, flask crear-admin
│   │   ├── core/
│   │   │   ├── seguridad.py    ← sesiones, roles, cabeceras, errores, auditoría
│   │   │   └── validacion.py   ← validación de datos de entrada
│   │   ├── models/             ← una clase por tabla
│   │   ├── routes/             ← endpoints, un archivo por dominio:
│   │   │                          auth, usuarios, catalogos, clientes, repartidores,
│   │   │                          pedidos, publico, rutas, caja, reportes, incidencias, sistema
│   │   └── static/openapi.json ← documentación Swagger
│   ├── migrations/             ← migraciones de la base de datos (Alembic)
│   ├── tests/                  ← pruebas automáticas (pytest)
│   ├── scripts/                ← seed.py, crear_admin.py
│   ├── wsgi.py                 ← punto de entrada (flask run / gunicorn / waitress)
│   ├── requirements.txt        ← dependencias (requirements-dev.txt agrega pytest)
│   ├── .env.example            ← plantilla de configuración
│   └── entorno_courrier/       ← entorno virtual de Python (no se sube a git)
│
├── frontend/
│   └── src/
│       ├── main.jsx, App.jsx   ← arranque y tabla de rutas
│       ├── api/                ← llamadas al backend, un archivo por dominio
│       │                          (cliente.js tiene la sesión y la renovación de tokens)
│       ├── routes/guards.jsx   ← protección de rutas por sesión y rol
│       ├── components/
│       │   ├── layout/         ← estructura de la app (menú lateral, barra superior)
│       │   └── ui/             ← piezas reutilizables (Modal, EstadoBadge)
│       ├── pages/              ← pantallas agrupadas por dominio
│       │                          auth, publico, pedidos, clientes, almacenes, rutas,
│       │                          repartidor, pagos, incidencias, reportes, configuracion
│       └── styles/index.css
│
└── docs/                       ← historial de cambios y diagrama de clases
```

---

## Desarrollo local

Backend (todos los comandos `flask` se corren **dentro de `backend/`**):

```bash
cd backend
python -m venv entorno_courrier
entorno_courrier\Scripts\activate          # Windows  (Linux/Mac: source entorno_courrier/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env                     # y completa DATABASE_URL y JWT_SECRET_KEY
flask db upgrade                           # crea/actualiza las tablas
flask sembrar                              # catálogo de estados
flask crear-admin                          # primer administrador: usuario, correo y contraseña oculta
flask run
```

Frontend:

```bash
cd frontend
npm install
echo VITE_API_URL=http://127.0.0.1:5000 > .env
npm run dev
```

Tests (usan una base SQLite temporal, nunca tu MySQL):

```bash
cd backend
pytest
```

---

## Puesta en producción

### 1. Variables de entorno (`backend/.env`)

Con `APP_ENV=production` la app **se niega a arrancar** si:

- `JWT_SECRET_KEY` tiene menos de 32 caracteres,
- `ORIGENES_PERMITIDOS` está vacío o es `*`,
- `DATABASE_URL` apunta a SQLite.

| Variable | Producción |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Usuario MySQL **dedicado** (no root), con permisos solo sobre la base |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ORIGENES_PERMITIDOS` | `https://app.tuempresa.pe` |
| `RATELIMIT_STORAGE_URI` | `redis://127.0.0.1:6379/0` (obligatorio si usas más de un worker) |
| `PROXY_SALTOS` | `1` detrás de Nginx |
| `URL_FRONTEND` | `https://app.tuempresa.pe` (base del enlace de recuperación; exige https) |
| `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_PASSWORD`, `SMTP_REMITENTE` | Servidor de correo para la recuperación de contraseña |

Ver todas en [backend/.env.example](backend/.env.example).

### 2. Base de datos

```bash
cd backend
flask db upgrade
flask sembrar
flask crear-admin
```

> **Antes de migrar una base existente, saca un respaldo:** `mysqldump -u root -p courrier > respaldo.sql`.
> La migración `e7f3b9c25a14` crea el campo `nombre_usuario`: a los usuarios existentes se les asigna la parte de su correo antes de la @ (`jperez@empresa.pe` → `jperez`).
> La migración `d5e2a8f41c07` agrega columnas y tablas nuevas, y marca como liquidadas las rutas ya completadas.

### 3. Servidor de aplicación

No uses `python wsgi.py` ni `flask run` en producción.

```bash
cd backend
# Linux
gunicorn -w 4 -b 127.0.0.1:8000 --access-logfile - wsgi:app
# Windows
waitress-serve --listen=127.0.0.1:8000 wsgi:app
```

### 4. Frontend

```bash
cd frontend
echo VITE_API_URL=https://api.tuempresa.pe > .env.production
npm ci && npm run build      # genera frontend/dist
```

### 5. Nginx (HTTPS obligatorio)

```nginx
server {
    listen 443 ssl http2;
    server_name app.tuempresa.pe;
    # ssl_certificate ... (Let's Encrypt / certbot)

    root /srv/courrier/frontend/dist;
    location / { try_files $uri /index.html; }

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' https://api.tuempresa.pe; frame-ancestors 'none'" always;
}

server {
    listen 443 ssl http2;
    server_name api.tuempresa.pe;
    client_max_body_size 6m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6. Operación

- **Health check:** `GET /health` (responde 503 si la base no responde).
- **Logs:** cada error 500 se registra con un `requestId`, que también se devuelve al cliente y va en la cabecera `X-Request-ID`.
- **Respaldos:** `mysqldump` diario y **prueba la restauración** al menos una vez al mes.
- **Dependencias:** corre `pip-audit` y `npm audit` antes de cada despliegue.

---

## Reglas de negocio principales

### Admisión de envíos (Fase 1)

Pantalla **Pedidos → Nuevo envío** (`/pedidos/nuevo`):

1. **Remitente y destinatario** por separado. El destinatario es quien recibe; su dirección define la zona de destino.
2. **Bultos**: cada caja se pesa y se mide. Peso volumétrico = largo × ancho × alto / `FACTOR_VOLUMETRICO` (5000). Cada bulto se cobra por el **mayor** entre su peso real y su volumétrico, y el total se redondea hacia arriba al medio kilo.
3. **Inspección** (obligatoria al recibir el paquete): estado del producto, embalaje y la declaración de que no contiene artículos prohibidos. Si el producto está dañado, se exigen observaciones y una foto. Con el embalaje **rechazado**, el envío no se admite.
4. **Cotización** en vivo con `POST /cotizar`:
   - `flete = máx(precio mínimo, base + kg facturables × precio/kg)`
   - `total = flete + seguro`, donde el seguro es `SEGURO_PORCENTAJE` del valor declarado.

   Cada **tipo de servicio** (estándar o express) tiene su propia tarifa, con precio mínimo y plazo en días. El plazo se usa para calcular la fecha estimada de entrega, en hora local (`UTC_OFFSET_HORAS`; con 0 días, se entrega el mismo día). Las tarifas se gestionan en **Configuración → Tarifas**.
5. **Guía y etiqueta**: una etiqueta de 10 × 15 cm por bulto, con un QR del código del bulto (`CE-XXXX-XXXX-1`). La etiqueta **no** muestra el contenido del paquete ni el DNI (evita robos). Indica **COBRAR S/ X** o **NO COBRAR**.

Envíos pre-registrados (por ejemplo, desde una tienda online): se crean con un peso estimado y quedan en `pendiente`. Al llegar el paquete se usa **Recibir en agencia** (`/pedidos/:id/recibir`), que pide los bultos y la inspección, y recalcula el precio con el peso real si todavía no hay un pago registrado.

### Red de agencias (Fase 2)

Los almacenes funcionan como **agencias**. Cada envío tiene una agencia de **origen** (donde se admite) y una de **destino**, que se asigna sola: es la agencia de la zona de la dirección de entrega. Si es la misma que la de origen, o si esa zona no tiene agencia, el envío es **local** y se reparte desde el origen sin viajar.

Pantalla **Despachos** (`/despachos`):

1. **Clasificación (Salidas → Por despachar):** envíos de la agencia agrupados por agencia destino. La etiqueta lleva el destino en grande (**→ AGENCIA X** o **REPARTO LOCAL**).
2. **Manifiesto de salida:** se abre uno por destino y se **escanea** cada bulto, con lector USB o Bluetooth (funciona como teclado + Enter) o escribiendo el código. El campo recupera el foco después de cada lectura y suena un pitido distinto si hubo error. Se rechaza un bulto que va a otra agencia, que ya está en otro manifiesto o que es **prepagado sin pago confirmado**.
3. **Despachar:** exige transportista y placa (el precinto es opcional). **Un envío viaja completo**: si falta escanear uno de sus bultos, no se despacha. Después el manifiesto ya no se puede modificar y los envíos pasan a `en_transito`. El manifiesto se imprime con líneas de firma para el transportista.
4. **Recepción en destino (Llegadas):** se escanea cada bulto al bajarlo. Cuando llegan todos los bultos de un envío, pasa a `en_agencia_destino` y aparece para los repartidores de **esa** zona. Escanear dos veces el mismo bulto no lo cuenta doble. Un bulto que no figura en el manifiesto se marca como **SOBRANTE** y no se recibe.
5. **Cerrar recepción:** cada bulto no escaneado genera automáticamente una **incidencia "faltante"** (se exige una observación). El envío incompleto no se reparte.

**Trazabilidad:** cada movimiento de cada bulto queda registrado: quién lo hizo, en qué agencia, cuándo y en qué manifiesto. Se ve en **Historial** del pedido.

**Operador por agencia:** en **Configuración → Usuarios** se asigna la agencia de cada operador. Un operador con agencia solo ve y opera los envíos que salen de ella o llegan a ella: solo admite y despacha desde su agencia y solo recibe los manifiestos que llegan a ella. Sin agencia, el usuario ve todas.

### Recojo a domicilio y entrega con constancia (Fase 3)

**Recojo a domicilio** (pantalla **Recojos**):

1. Cuando el cliente pide que pasen por sus paquetes, se registra el recojo con dirección, fecha, franja (mañana o tarde) y bultos estimados. La agencia que lo atiende se asigna sola: es la de la zona de esa dirección.
2. Se asigna a un repartidor de **esa zona**. El repartidor lo ve arriba en **Mi Ruta** y marca *Recogí los paquetes* (con cuántos bultos) o *No pude recoger* (con el motivo). Un recojo fallido se puede reprogramar.
3. En la agencia, **Admitir paquetes** abre la admisión con el remitente y la agencia ya cargados, y se registra un envío por cada destinatario. `RECARGO_RECOJO` se suma una sola vez, al primer envío.

**Entrega con constancia:** para cerrar una entrega, el repartidor registra **quién recibe** (el destinatario, un familiar, portería…), su **DNI** y su **firma** con el dedo en la pantalla. La foto y la ubicación GPS se adjuntan si están disponibles. Todo queda en **Pedidos → Constancia** como respaldo ante un "nunca me llegó".

**Entrega con código (PIN):** es opcional para cada envío y se recomienda para los de valor.
- Al admitir el envío se genera un PIN de 6 dígitos. Se muestra **una sola vez** al operador, que se lo da al remitente; si el destinatario tiene correo, también le llega por correo.
- Sin el PIN correcto no hay entrega. Después de `MAX_INTENTOS_PIN` intentos fallidos se bloquea, y la agencia puede generar uno nuevo (**Nuevo PIN**), que anula el anterior.
- En la base solo se guarda un HMAC del PIN; nunca sale en la API ni en la etiqueta.

**Plazo comprometido (SLA):**
- **Pedidos** muestra un aviso con los envíos atrasados y los que vencen hoy, y permite filtrar los atrasados.
- **Reportes** muestra el porcentaje de entregas a tiempo.
- El rastreo público muestra la fecha estimada de entrega.

### Cámara, avisos y facturación (Fase 4)

**Escaneo con la cámara del celular:** el botón **📷 Cámara** en los manifiestos (cargar y recibir) lee los QR de las etiquetas en **modo continuo**: se va pasando caja por caja sin cerrar la cámara, y la misma caja no se cuenta dos veces. En **Pedidos**, el botón 📷 busca un envío por su QR. Usa el lector nativo del navegador si existe (Chrome en Android) y, si no, `jsQR`. El navegador solo da acceso a la cámara en **HTTPS** (o en `localhost`).

**Avisos al destinatario:** se envían cuando el envío se registra, cuando sale a reparto, cuando se entrega (con el nombre de quien recibió) y cuando no se pudo entregar.
- **Canales:** WhatsApp (Cloud API oficial de Meta) y/o correo. Solo se usa un canal si está configurado y el cliente tiene ese dato.
- **WhatsApp** solo se manda a celulares (9 dígitos que empiezan con 9).
- **Consentimiento** (Ley 29733): en **Clientes** se activa o desactiva por cliente, y queda auditado.
- **Cómo se envían:** se guardan en la tabla `notificaciones` dentro de la misma transacción del cambio de estado y se mandan en segundo plano, así que si Meta o el correo fallan, la operación no falla.
- **Reintentos:** los fallidos se reintentan con `flask reenviar-avisos`; prográmalo con cron cada 10 minutos.
- **Dónde se ven:** en el **Historial** de cada pedido.

Plantillas que hay que crear y hacer aprobar en **WhatsApp Manager** (idioma español; las variables van en este orden):

| Plantilla | Variables |
|---|---|
| `envio_registrado` | {{1}} nombre, {{2}} guía, {{3}} fecha estimada, {{4}} enlace de rastreo |
| `envio_en_camino` | {{1}} nombre, {{2}} guía, {{3}} enlace de rastreo |
| `envio_entregado` | {{1}} nombre, {{2}} guía, {{3}} quién recibió |
| `envio_no_entregado` | {{1}} nombre, {{2}} guía, {{3}} motivo |

El enlace de rastreo es `URL_FRONTEND/rastreo?guia=...` y abre el seguimiento ya buscado.

**Boletas y facturas electrónicas (Nubefact):** el botón **Comprobante** aparece en los envíos con un pago registrado.
- **Factura:** solo a un **RUC válido**, con dígito verificador, y exige la dirección fiscal.
- **Boleta:** con DNI o carnet de extranjería; **sin documento solo si es menor a S/ 700**.
- **IGV:** 18 % incluido en el precio (`gravada = total / 1.18`).
- **Pagador sugerido:** en contra entrega, el destinatario; en los demás casos, el remitente.
- **Numeración:** correlativa **sin saltos** por serie (`B001`, `F001`).
- **Reintento:** si Nubefact no responde, el comprobante queda en "error" y se reintenta con el **mismo número**.
- **Sin configurar:** si faltan `NUBEFACT_URL` y `NUBEFACT_TOKEN`, **no se emite nada** y no se consume ningún número. El sistema nunca genera un comprobante que no haya pasado por SUNAT.

### Ciclo del pedido

- **Estados del pedido:** `pendiente → en_almacen → [en_transito → en_agencia_destino] → asignado → en_camino → entregado` (el tramo entre corchetes solo existe en los envíos a otra agencia). Desde `en_camino` también puede pasar a `no_entregado`; desde ahí, a reintento (`asignado`), `devuelto` o `cancelado`. Los estados `entregado`, `devuelto` y `cancelado` son finales.
- **"Entregado"** solo se registra con *Entregar y cobrar*, que exige el monto exacto en los pedidos contra entrega y el número de operación cuando el pago es con Yape, Plin, tarjeta o transferencia. Es idempotente: si el celular reintenta la petición, no se duplica el pago.
- **Modalidad de pago:** `contra_entrega` (el repartidor cobra), `prepagado` o `credito` (se registra desde Pagos; el repartidor no cobra).
- **Tarifas:** si no se ingresa el monto, se calcula como `precio base + peso × precio/kg` entre la zona del almacén y la de destino. Un monto manual distinto queda en la auditoría.
- **No entregado:** exige un motivo de catálogo y como máximo admite `MAX_INTENTOS_ENTREGA` intentos. La devolución la confirma el almacén (admin/operador).
- **Liquidación de caja:** al completar una ruta, el efectivo cobrado debe entregarse en caja (*Pagos y caja → Liquidar*). Cualquier diferencia exige una observación. Un repartidor con más de `MAX_RUTAS_SIN_LIQUIDAR` rutas sin liquidar no puede tomar pedidos.
- **Repartidores:** necesitan zona y estar disponibles para tomar pedidos, y solo toman pedidos de su zona.

## Seguridad implementada

- **Login por nombre de usuario** (no por correo) con **captcha de imagen** propio: se genera en el servidor, sirve una sola vez, vence a los 5 minutos y se valida antes de revisar la contraseña (un bot no puede probar claves ni bloquear cuentas ajenas). No depende de servicios externos.
- **Recuperación de contraseña** (`/recuperar`): el usuario escribe su usuario o correo y recibe un enlace de un solo uso que vence en 30 minutos. La respuesta nunca revela si la cuenta existe, solo vale el último enlace enviado, se permite como máximo un envío cada 2 minutos por cuenta y, al cambiar la contraseña, se cierran todas las sesiones y se desbloquea la cuenta. En la base solo se guarda el hash del token.
- Access token de 30 minutos y refresh token de 12 horas. Desactivar a un usuario o cambiarle el rol o la contraseña **invalida sus sesiones al instante** (`tokenVersion`).
- Bloqueo temporal de la cuenta tras 5 intentos fallidos, rate limit por IP y respuesta de tiempo constante en el login (no revela si un email existe).
- Política de contraseñas: 10 o más caracteres, con letras y números. El primer admin se crea solo por CLI: ya no hay alta de usuarios sin autenticación.
- Autorización por objeto: un repartidor solo ve sus pedidos, sus rutas y su perfil, y no tiene acceso a la base de clientes.
- La identidad siempre se toma del token, nunca del cuerpo de la petición.
- Rastreo público con códigos de guía no secuenciales (`CE-7K3M-9QX2`) y solo mensajes fijos por estado: nunca se publican comentarios internos ni incidencias.
- Validación estricta de entrada (tipos, rangos, enums, tamaños) y dinero siempre en `Decimal`.
- Errores 500 sin detalles internos, cabeceras de seguridad (CSP, HSTS, `nosniff`, `X-Frame-Options`), CORS cerrado en producción y Swagger desactivado en producción.
- Auditoría (tabla `auditoria`) de cambios de rol, contraseñas, cancelaciones, montos manuales, pagos y liquidaciones.

## Pendiente (requiere decisiones de negocio o infraestructura)

- Fotos de evidencia en almacenamiento de objetos (S3, R2 o Cloudinary) en vez de base64 en MySQL.
- **Devolución entre agencias:** hoy un envío que llegó a destino y no se pudo entregar queda `devuelto` en esa agencia. Falta el manifiesto de retorno al origen.
- **Faltante encontrado después:** si aparece un bulto marcado como faltante, hoy se resuelve a mano (incidencia y ajuste por admin). Falta un flujo de "recepción tardía".
- **Notas de crédito y anulaciones** (comunicación de baja ante SUNAT): todavía no se emiten desde el sistema; se hacen en el panel de Nubefact.
- **PIN por WhatsApp:** requiere una plantilla de autenticación aprobada por Meta. Hoy el PIN se entrega al remitente y se envía por correo al destinatario.
- Actualizar `static/openapi.json` con los endpoints nuevos.
