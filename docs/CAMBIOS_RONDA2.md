# Cambios — Ronda 2 (recomendaciones de análisis)

Implementación de las recomendaciones del análisis general del proyecto
(lógica de negocio, entidad-relación, frontend). Requiere correr una
migración nueva — ver el final de este documento.

## Backend (`app.py` + modelos)

1. **Auditoría**: `fechaCreacion`/`fechaActualizacion` en Zona, Cliente,
   Dirección, Almacén, Repartidor, Usuario y Ruta (antes solo Pedido e
   Incidencia las tenían).
2. **Soft-delete**: campo `activo` en Zona, Cliente, Dirección y Almacén.
   `listarZonas`, `listarClientes` y `listarAlmacenes` ahora excluyen
   inactivos por defecto (`?incluir_inactivas=true` / `?incluir_inactivos=true`
   para verlos). Nuevos endpoints `POST /zona/<id>/desactivar`,
   `/activar`, y lo mismo para cliente y almacén.
3. **Coordenadas**: `latitud`/`longitud` en Almacén y Dirección (opcional,
   para mapas/optimización de rutas a futuro).
4. **Tabla de tarifas** (`tarifas_zona`): precio base + precio por kg entre
   un par de zonas. Endpoints `GET /tarifas`, `POST /tarifa`,
   `PUT /tarifa/<id>`, `DELETE /tarifa/<id>` (soft-delete). `crearPedido`
   ahora calcula el monto automáticamente con la tarifa registrada si no
   se especifica uno a mano.
5. **Índices** en `pedidos` sobre `estado_id`, `repartidor_id`, `ruta_id`,
   `cliente_id` — las columnas por las que más se filtra en el día a día.
6. **Buscador**: `/pedidos` acepta `?q=` (busca por código de guía, nombre
   o teléfono del cliente).
7. **`/pagos/existentes?pedido_ids=1,2,3`**: nuevo endpoint que dice cuáles
   de esos pedidos ya tienen un pago registrado — lo usa el panel de
   Pedidos para no ofrecer "Registrar pago" dos veces sobre el mismo pedido
   (evita el 409 de "pago duplicado").
8. **Máquina de estados refactorizada**: se extrajo `puedeTransicionar()`
   como función pura (sin acceso a base de datos), reutilizada en
   `cambiarEstadoPedido`, `entregarYCobrar` y `eliminarPedido` — antes cada
   una repetía la misma verificación por su cuenta. Ver
   `tests/test_estados.py` (7 pruebas, corren con `pytest` sin necesitar
   una base de datos real).
9. **CORS restringible**: si se define `ORIGENES_PERMITIDOS` en el `.env`
   (ej. `https://app.tuempresa.pe`), solo ese origen puede llamar a la API.
   Sin esa variable, se mantiene abierto (desarrollo local).
10. **Rate limiting** (Flask-Limiter) en `/login` (10/min), y en los dos
    endpoints públicos sin login que exponen datos por id/código:
    `/pedido/<id>/estado-actual` y `/rastreo/<codigoGuia>` (30/min cada uno).
11. **Documentación Swagger** en `/docs` (spec en `static/openapi.json`).

## Frontend

- **`api.js`**: si el backend responde 401 con un token guardado, la
  sesión se cierra sola y se redirige a `/login` con un aviso ("tu sesión
  expiró..."), en vez de dejar la pantalla mostrando un error suelto.
- **`Pedidos.jsx`**: buscador (código de guía/cliente/teléfono, con
  debounce de 400ms), paginación real con controles "Anterior/Siguiente"
  conectados a la paginación que el backend ya devolvía, auto-refresco
  cada 45s, y el botón "Registrar pago" ahora se oculta (muestra "✓
  Pagado") si el pedido ya tiene un pago registrado.
- **`Pagos.jsx`**: mismos controles de paginación.
- **`MiRuta.jsx`**: la foto de evidencia de entrega se comprime en el
  navegador (máx. 1280px, JPEG calidad 0.7) antes de convertirla a
  base64 — evita mandar varios MB por una foto de celular sin comprimir.
  Auto-refresco de la ruta activa y el pool cada 30s.
- **Página pública de rastreo** (`/rastreo`, sin login): el cliente final
  ingresa su código de guía y ve el estado actual + historial, usando el
  endpoint público que ya existía en el backend. Enlazada desde el login.

## Lo que se dejó fuera a propósito (necesita una decisión de negocio/infra)

- **Evidencia de entrega fuera de la base de datos** (hoy sigue en
  `LONGTEXT` como base64): requiere elegir un proveedor de almacenamiento
  (S3, Cloudinary, etc.) y sus credenciales.
- **Refresh tokens / WebSockets**: cambio de arquitectura más grande: por
  ahora, la expiración de 8h y el auto-refresco por polling (cada
  30-45s) cubren el caso de uso sin arriesgar romper el login actual.
- **Facturación consolidada B2B** (clientes con convenio, no contra-entrega):
  necesita reglas de negocio que definas tú (ciclo de facturación,
  condiciones de crédito, etc.).

## Migración pendiente

Sí, hay que correr una migración nueva antes de usar esta versión contra
tu base de datos real:

```bash
pip install -r requirements.txt
flask db upgrade
```

Esto aplica la migración `c91d4e7a2f68_auditoria_soft_delete_tarifas.py`.
Todas las columnas nuevas son nullable o tienen `server_default`, así que
tus filas actuales no se rompen ni quedan en `NULL` sin sentido. Después
de migrar, si quieres usar el cálculo automático de precios, registra al
menos una tarifa con `POST /tarifa` (o desde donde decidas exponerlo en
el frontend de Configuración — ese CRUD de tarifas quedó listo en el
backend, pero todavía no tiene una pantalla dedicada en el frontend, por
si quieres que la construya en la siguiente ronda).
