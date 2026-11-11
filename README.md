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
flask crear-admin                          # primer administrador (pide la contraseña oculta)
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

Ver todas en [backend/.env.example](backend/.env.example).

### 2. Base de datos

```bash
cd backend
flask db upgrade
flask sembrar
flask crear-admin
```

> **Antes de migrar una base existente, saca un respaldo:** `mysqldump -u root -p courrier > respaldo.sql`.
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

- **Estados del pedido:** `pendiente → en_almacen → asignado → en_camino → entregado`. Desde `en_camino` también puede pasar a `no_entregado`; desde ahí, a reintento (`asignado`), `devuelto` o `cancelado`. Los estados `entregado`, `devuelto` y `cancelado` son finales.
- **"Entregado"** solo se registra con *Entregar y cobrar*, que exige el monto exacto en los pedidos contra entrega y el número de operación cuando el pago es con Yape, Plin, tarjeta o transferencia. Es idempotente: si el celular reintenta la petición, no se duplica el pago.
- **Modalidad de pago:** `contra_entrega` (el repartidor cobra), `prepagado` o `credito` (se registra desde Pagos; el repartidor no cobra).
- **Tarifas:** si no se ingresa el monto, se calcula como `precio base + peso × precio/kg` entre la zona del almacén y la de destino. Un monto manual distinto queda en la auditoría.
- **No entregado:** exige un motivo de catálogo y como máximo admite `MAX_INTENTOS_ENTREGA` intentos. La devolución la confirma el almacén (admin/operador).
- **Liquidación de caja:** al completar una ruta, el efectivo cobrado debe entregarse en caja (*Pagos y caja → Liquidar*). Cualquier diferencia exige una observación. Un repartidor con más de `MAX_RUTAS_SIN_LIQUIDAR` rutas sin liquidar no puede tomar pedidos.
- **Repartidores:** necesitan zona y estar disponibles para tomar pedidos, y solo toman pedidos de su zona.

## Seguridad implementada

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
- PIN de entrega por WhatsApp/SMS al destinatario (requiere un proveedor de mensajería).
- Separar **remitente** (cliente comercial que paga) de **destinatario**, junto con bultos, peso volumétrico y valor declarado.
- SLA y fecha comprometida de entrega por tarifa.
- Actualizar `static/openapi.json` con los endpoints nuevos.
