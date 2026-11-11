# Cambios de lógica de negocio — Courrier Express

Resumen de los ajustes hechos para que el flujo recepción → almacén →
asignación → tránsito → entrega/incidencia → pago sea más realista y
consistente para una empresa de courier. No se tocó el esquema de base de
datos (no hace falta correr ninguna migración nueva).

## Backend (`app.py`)

1. **Disponibilidad del repartidor, ahora sí se usa.**
   Nuevo endpoint `POST /repartidor/<id>/disponibilidad` — el repartidor
   prende/apaga su propia disponibilidad (como "online/offline" en apps de
   delivery). `tomarPedido` y `crearRuta` ahora rechazan la operación si el
   repartidor está marcado como no disponible.

2. **Validación de zona pareja en toda la app.**
   `tomarPedido` ahora exige que la zona del almacén del pedido coincida con
   la zona del repartidor — antes solo se exigía en `agregarPedidoARuta`.

3. **Cancelar respeta la máquina de estados en todos lados.**
   `eliminarPedido` (DELETE) ya no puede "cancelar" un pedido que ya está en
   un estado final (`entregado`, `devuelto`, o ya `cancelado`) — antes lo
   hacía sin pasar por `TRANSICIONES_VALIDAS`, rompiendo la regla de que los
   estados finales no tienen salida.

4. **Cancelar libera al repartidor/ruta.**
   Al cancelar un pedido (desde cualquiera de las dos rutas), se limpian
   `repartidorId` y `rutaId` para que no se quede "fantasma" contando dentro
   de una ruta que el repartidor ya no puede tocar.

5. **No se puede quitar de la ruta un pedido que ya está en camino.**
   `quitarPedidoDeRuta` ahora solo funciona si el pedido sigue en
   `asignado` (todavía no lo recoge el repartidor). Si ya está `recogido`/
   `en_camino`, hay que cancelarlo o reportar una incidencia, no "devolverlo
   al almacén" cuando físicamente está en la calle.

6. **No se agregan pedidos a una ruta cerrada.**
   `agregarPedidoARuta` valida que la ruta esté `planificada` o `en_curso`.

7. **`iniciarRuta` / `completarRuta` respetan su propia transición.**
   Solo se puede iniciar una ruta `planificada`, y solo se puede completar
   una ruta `en_curso`. Además, `completarRuta` bloquea el cierre si todavía
   quedan pedidos sin resolver (`asignado`, `recogido`, `en_camino`,
   `no_entregado`) dentro de esa ruta.

8. **Condición de carrera en la asignación de pedidos.**
   `tomarPedido` y `agregarPedidoARuta` ahora bloquean la fila del pedido
   (`SELECT ... FOR UPDATE`) durante la verificación y asignación, para que
   dos repartidores no puedan tomar el mismo pedido al mismo tiempo.

9. **Menos exposición de datos en el endpoint público del bot.**
   `GET /pedido/<id>/estado-actual` (usado por el bot de WhatsApp, sin
   login) ya no regresa el nombre del cliente a cualquiera que adivine un
   id consecutivo — solo lo hace si el teléfono enviado coincide con el
   registrado para ese pedido.

10. **Validación de campos consistente.**
    `crearZona`, `crearDireccionCliente`, `crearAlmacen`, `crearRepartidor`
    y `crearRuta` ahora validan campos obligatorios y reglas de negocio
    (usuario con rol correcto, perfil de repartidor duplicado, ruta activa
    duplicada) en vez de lanzar errores 500 sin control.

## Frontend

- `MiRuta.jsx`: switch de disponibilidad visible arriba de todo, con aviso
  cuando está "no disponible", y el botón "+ Tomar" del pool se deshabilita
  en ese caso.
- `Configuracion.jsx`: botón rápido "Marcar disponible / no disponible" en
  cada tarjeta de repartidor (mismo patrón que activar/desactivar usuario).
- `Rutas.jsx`: el selector para crear una ruta manualmente ahora marca en
  el propio nombre de la opción si el repartidor está "no disponible".

## Lo que se dejó igual a propósito

- El esquema de base de datos (11 tablas) no cambió.
- El "camino feliz" del flujo (pendiente → en_almacén → asignado → en_camino
  → entregado) sigue funcionando exactamente igual que antes; los cambios
  están todos en los bordes/casos límite.
