# Cuenta Clara: instrucciones de integración en ASE para Claude

Fecha de revisión del código: **5 de noviembre de 2026**.

Este documento describe la aplicación que existe en este repositorio y un procedimiento para integrarla en ASE. Distingue el comportamiento implementado de las adaptaciones pendientes. Los ejemplos son ficticios; no contienen datos de la base de datos personal.

## 1. Encargo para Claude

Integra Cuenta Clara como módulo de gestión de autónomos dentro de ASE, conservando sus funciones y datos. Antes de elegir una arquitectura, inspecciona el repositorio de ASE y determina su frontend, backend, autenticación, base de datos, sistema de suscripciones, despliegue y convenciones.

No está documentado aquí qué tecnología usa ASE. No asumas que es WordPress, React, Next.js, Laravel, Django, Supabase ni ninguna otra. Aprovecha lo que realmente exista y evita crear cuentas, autenticación o facturación de suscripciones paralelas si ASE ya las ofrece.

Objetivos:

1. Conservar facturas, clientes, gastos, calendarios, documentos, simuladores, ahorro, inversiones e importaciones CSV.
2. Vincular cada negocio y sus datos a una identidad autorizada de ASE.
3. Controlar el acceso a módulos según las suscripciones reales de ASE.
4. Mantener la separación entre facturación, cobros, caja, reservas fiscales, patrimonio personal y proyecciones.
5. Migrar los datos con copia previa y verificación de resultados.
6. Entregar una integración comprobable, con instrucciones de desarrollo y despliegue, pruebas y limitaciones identificadas.

El código fuente es la referencia de comportamiento. Este documento es una guía de integración, no una declaración de cumplimiento fiscal ni un compromiso de rentabilidad.

## 2. Qué existe actualmente

**Sí hay backend.** Es una aplicación local de una sola persona, con una interfaz web, una API Python y una base SQLite persistente.

```text
Navegador
  ├─ HTML / CSS / JavaScript: public/
  └─ fetch /api/...
       └─ server.py: servidor HTTP + API + validaciones
            ├─ SQLite: data/autonomo.db
            ├─ business.py: recurrencias y copias
            ├─ wealth.py: planes y movimientos personales
            ├─ portfolio_csv.py: importaciones de cartera
            └─ invoice_pdf.py: PDF de factura y timesheet
```

El servidor utiliza `ThreadingHTTPServer` y `SimpleHTTPRequestHandler` de la biblioteca estándar. Sirve `public/` y las rutas API desde el mismo origen. Escucha únicamente en `127.0.0.1`, puerto 8000 por defecto.

No existen todavía usuarios, sesiones, tenants, permisos, suscripciones, pasarela de pago, tareas externas programadas ni sincronización bancaria. El servidor actual no debe exponerse como servicio público de ASE sin adaptaciones.

## 3. Mapa de archivos

| Archivo | Responsabilidad |
| --- | --- |
| `server.py` | Servidor local, API, conexión SQLite, validación de facturas/gastos/clientes/calendarios y coordinación de módulos. |
| `business.py` | Generación mensual de gastos recurrentes, copias JSON completas y validación de restauraciones. |
| `wealth.py` | Validación de planes de ahorro/inversión, movimientos, coherencia de saldo y migración de rentabilidad mensual antigua a anual. |
| `portfolio_csv.py` | Lectura CSV, asignación de columnas, normalización, vista previa, deduplicación y guardado transaccional. |
| `invoice_pdf.py` | Generación PDF A4 con ReportLab para facturas y timesheets. |
| `launcher.py` | Arranque local, comprobación de `/api/health` y apertura del navegador. |
| `iniciar.bat` | Entrada de doble clic para Windows; ejecuta `launcher.py`. |
| `requirements.txt` | Dependencia externa declarada: `reportlab>=4,<6`. |
| `public/index.html` | Navegación, estructura de página y carga de scripts. |
| `public/app.js` | Estado global, carga de registros, formularios, filtros, calendario y acciones CRUD. |
| `public/dashboard.js` | Agregaciones mensuales, neto estimado, gráficos SVG y avisos de cobro. |
| `public/business.js` | Caja, previsión, reparto de gastos por cliente, objetivo de sueldo y gestión de recurrencias/copias. |
| `public/simulator.js` | Simulación de subidas de tarifas sobre facturas existentes. |
| `public/wealth.js` | Ahorro, inversiones, movimientos reales, proyecciones y efecto de transferencias en caja. |
| `public/portfolio.js` | Asistente de importación CSV, cartera importada e historial de importaciones. |
| `public/style.css` | Estilos generales y adaptación a pantallas pequeñas. |
| `public/wealth.css` | Formularios y gráficos del patrimonio personal. |
| `public/portfolio.css` | Asistente de importación y tablas de cartera. |
| `tests/` | Pruebas Python de API y pruebas JavaScript de cálculo y presentación. |
| `README.md` | Notas históricas y de ejecución. Algunas primeras secciones quedaron desactualizadas; contrastar con el código y esta guía. |

`data/`, `.dependencies/`, `tmp/` y `__pycache__/` están excluidos de Git. La base, los logs y las copias pueden contener información sensible y no deben publicarse como archivos estáticos.

## 4. Ejecutar y examinar la versión local

Desde la raíz del proyecto, con Python disponible:

```powershell
python -m pip install --target .dependencies -r requirements.txt
python server.py
```

Abrir `http://127.0.0.1:8000/`. Alternativamente, hacer doble clic en `iniciar.bat`.

Detalles:

- `invoice_pdf.py` añade `.dependencies/` al `sys.path` para cargar ReportLab. En ASE conviene sustituirlo por la gestión habitual de dependencias del proyecto.
- El servidor toma el puerto de la variable `PORT`, pero el lanzador fuerza 8000 y la URL local está fijada en su código.
- El lanzador detecta si ya existe un servidor compatible mediante `/api/health` y registra el proceso que inicia en `data/servidor.log`.
- Al arrancar/importar `server.py` se inicializa la tabla y se ejecuta la conversión de tasas antiguas de inversión. No importes este módulo contra una base personal sin entender ese efecto.
- No hay `package.json`, compilación de frontend ni framework JS. Node se utiliza para ejecutar las pruebas JavaScript.

No copies `.dependencies/`, bases personales ni rutas absolutas de este ordenador a ASE. Prepara dependencias y configuración en el entorno de destino.

## 5. Modelo de datos actual

### 5.1. Almacenamiento

Toda la aplicación usa una tabla:

```sql
CREATE TABLE records (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    data TEXT NOT NULL
);
```

`data` es un objeto JSON serializado. No existen claves foráneas ni un propietario en el esquema SQLite; las relaciones se verifican parcialmente desde Python.

El listado API aplana el objeto:

```json
{
  "id": 42,
  "kind": "expense",
  "supplier": "Proveedor de ejemplo",
  "description": "Servicio mensual",
  "date": "2026-10-01",
  "base": "100",
  "vat": "21",
  "baseCents": 10000,
  "vatCents": 2100,
  "totalCents": 12100
}
```

Una copia completa, en cambio, mantiene `{id, kind, data: {...}}`. No confundir ambos formatos.

### 5.2. Convenciones

- Moneda de trabajo: EUR.
- Importes derivados: enteros en céntimos (`*Cents`).
- Importes introducidos, tarifas, cantidades y porcentajes: frecuentemente cadenas decimales.
- Fechas: `AAAA-MM-DD`; meses: `AAAA-MM`.
- Algunas relaciones históricas, como `invoice.client`, pueden ser cadenas aunque `id` sea entero.
- Python usa `Decimal` y redondeo `ROUND_HALF_UP` para los cálculos de factura y gasto.
- El navegador usa `Number` y `Math.round` en resúmenes y simulaciones. No asumir una equivalencia decimal exacta entre ambos motores, especialmente con negativos o valores límite.
- Los borrados soportados son lógicos: cambian `kind` a `deleted_<tipo>`. El listado normal los excluye, pero las copias completas los conservan.
- No hay auditoría completa, marcas de modificación ni control de versiones concurrentes.

### 5.3. Tipos de registro

| `kind` | Datos principales y relaciones |
| --- | --- |
| `profile` | `name`, `taxid`, `address`, `email`, `iban`, `invoiceColor`, `logo`. Registro único en la versión personal. |
| `client` | Datos fiscales, `startDate`, `paymentRule`, `paymentDays`, `extraIrpf`. |
| `invoice` | `client`, `date`, `due`, `serviceMonth`, `description`, `lines`, `vat`, `irpf`, totales en céntimos, `number`, `paid`, posible `paidDate`, `clientSnapshot`, `profileSnapshot`. |
| `expense` | `supplier`, `description`, `reference`, `date`, `base`, `vat`, `deductible`, `vatDeductible`, totales, `paid`, posible `paidDate`/`recurringId`. |
| `timesheet` | `month`, listas `vacations` y `holidays`. Un calendario mensual por persona en la versión actual. |
| `recurring` | `nextDate`, `day`, `template` de gasto, `active`. |
| `cashsettings` | Ajustes acumulados: `openingBalance`, `withdrawals`, `vatPaid`, `extraIrpfUsed`. Registro único. |
| `wealthplan` | `category`: `saving`/`investment`; `name`, `startMonth`, `initial`, `monthly`, `target`, versiones `*Cents`, `annualRate`, `horizon`, `active`. |
| `wealthentry` | `planId`, `action`, `date`, `amount`, `amountCents`, `fromBusiness`, `note`. |
| `portfolioimport` | Lote importado: `planId`, `source`, `mode`, `fileName`, `created`, `imported`, `duplicates`, `ignored`. |
| `portfoliosnapshot` | Captura: `planId`, `source`, `date`, `positions`, `totalCents`, `costCents`, `fingerprint`, `importId`. |
| `portfoliotransaction` | Movimiento: `planId`, `source`, `date`, `timestamp`, `type`, `name`, `identifier`, `quantity`, `amountCents`, `feesCents`, `currency`, `reference`, `fingerprint`, `dedupKey`, `importId`. |

Los tipos con borrado lógico incluyen facturas, gastos, recurrencias, planes, movimientos personales y registros de importación de cartera. No hay botón de recuperación individual; una copia puede recuperar el estado anterior. Un borrado no equivale a una rectificación fiscal.

## 6. API actual

Las rutas son relativas al origen y empiezan en `/api`. No llevan autenticación. Las respuestas JSON usan UTF-8 y `Cache-Control: no-store`.

| Método y ruta | Comportamiento |
| --- | --- |
| `GET /api/health` | Devuelve `{"app":"cuenta-clara"}`. |
| `GET /api/records` | Genera recurrencias vencidas y devuelve todos los registros activos, ordenados por ID descendente. **Tiene un efecto de escritura.** |
| `POST /api/records` | Crea `{kind, data}`; devuelve `{id}`. También sustituye el perfil/ajustes únicos o actualiza el calendario del mismo mes. |
| `PUT /api/records/{id}` | Actualiza campos permitidos de factura, cliente, gasto, plan o movimiento personal. Recalcula y valida. Devuelve `{id}`. |
| `PATCH /api/records/{id}` | Alterna pagado/cobrado para una factura o gasto. No necesita cuerpo. Asigna `paidDate` a hoy o `null`. |
| `DELETE /api/records/{id}` | Borrado lógico de los tipos admitidos, con comprobaciones para planes y movimientos personales. |
| `GET /api/invoices/{id}/pdf` | Descarga PDF de factura activa. |
| `GET /api/timesheets/{AAAA-MM}/pdf` | Descarga el calendario del mes, incluso si todavía no tiene marcas guardadas. |
| `GET /api/backup` | Descarga copia completa JSON con checksum. |
| `POST /api/restore` | Valida la copia completa, guarda una copia previa y reemplaza **todos** los registros de la base. |
| `GET /api/portfolio/template/positions.csv` | Plantilla de posiciones con datos ficticios. |
| `GET /api/portfolio/template/transactions.csv` | Plantilla de movimientos con datos ficticios. |
| `POST /api/portfolio/inspect` | Lee cabeceras, muestra primeras filas y sugiere columnas/tipos. |
| `POST /api/portfolio/preview` | Normaliza y valida todas las filas; muestra errores, duplicados y `previewHash`. No importa registros. |
| `POST /api/portfolio/import` | Recalcula la vista previa y guarda un lote completo en una transacción si coincide el hash y no hay errores. |
| `DELETE /api/portfolio/imports/{id}` | Elimina lógicamente el lote y sus datos todavía activos. No borra valoraciones manuales del plan. |

Creaciones habituales: 201. Actualizaciones/listados: 200. Errores de validación: 400 con `{"error":"..."}`. También hay respuestas 403/404 y 503 si falta la dependencia PDF. No todos los errores internos se normalizan actualmente.

Ejemplo ficticio de factura:

```json
{
  "kind": "invoice",
  "data": {
    "client": "2",
    "date": "2026-10-31",
    "due": "2026-11-30",
    "serviceMonth": "2026-10",
    "description": "Servicios profesionales",
    "vat": "21",
    "irpf": "15",
    "lines": [
      {"description":"Tarifa A","quantity":"10","unit":"días","rate":"200"},
      {"description":"Tarifa B","quantity":"5","unit":"días","rate":"250"}
    ]
  }
}
```

Límites aproximados implementados en los handlers: POST genérico 1.000.000 bytes, PUT 100.000 bytes, restauración 50 MB, petición CSV 6.500.000 bytes. El CSV en sí admite hasta 5 MB UTF-8 y 5.000 filas. Configura también los límites del proxy y de ASE.

## 7. Reglas funcionales que deben preservarse

### 7.1. Facturas y vencimientos

Cada factura admite hasta 100 líneas. Cada línea contiene descripción, cantidad positiva, unidad `días` o `horas`, tarifa y `baseCents`.

```text
baseLínea = redondearCéntimos(cantidad × tarifa)
baseFactura = suma(baseLínea)
IVA = redondear(baseFactura × porcentajeIVA / 100)
IRPF = redondear(baseFactura × porcentajeIRPF / 100)
totalACobrar = baseFactura + IVA − IRPF
```

Valores iniciales de la interfaz: IVA 21 % e IRPF 15 %, ambos editables. Son parámetros del producto, no una inferencia automática de la situación fiscal de cada usuario.

- Se conserva compatibilidad con facturas antiguas de una sola línea mediante `(invoice.lines || [invoice])`.
- La regla `paymentRule="nextMonth"` usa el **último día del mes siguiente a `invoice.date`**. Febrero se cobra en marzo. No se calcula desde `serviceMonth`.
- El servidor recalcula ese vencimiento al crear o editar una factura del cliente con regla `nextMonth`, aunque el navegador envíe otro `due`.
- Con regla `days`, el navegador calcula `date + paymentDays`. El backend actual no impone ese cálculo de la misma forma: debe centralizarse al integrar.
- `serviceMonth` sirve para conciliar días trabajados y facturados; no determina el período de IVA ni el vencimiento.
- La numeración actual es `AAAA-NNNN`, pero el contador se toma del máximo sufijo de **todas** las facturas activas/eliminadas, no de una secuencia independiente anual. No reutiliza números por borrado mientras exista el historial.
- La edición conserva número y estado de cobro. Si cambia el cliente, se sustituye su snapshot. Si se editan los datos del mismo cliente, no se reescribe automáticamente el snapshot de facturas anteriores.
- Al crear la factura se captura el perfil fiscal del emisor. La impresión/PDF usa esos datos históricos y el logo/color actuales del perfil como marca visual.
- La reserva `client.extraIrpf` es un porcentaje personal adicional sobre la base. No modifica el total de la factura ni se añade a la retención que paga el cliente.
- Los resúmenes consultan el porcentaje extra actual del cliente, con fallback al snapshot. Cambiar ese porcentaje recalcula también la reserva histórica mostrada.

Estados visuales:

- Pendiente y `due < hoy`: rojo.
- Cobrada: verde.
- Cobrada con `paidDate > due`: etiqueta de retraso.
- Los avisos muestran vencidos y próximos vencimientos a 7 días, sin limitarse a filtros de año/concepto.

Actualmente no se puede registrar un cobro parcial ni elegir una fecha histórica de cobro desde una acción dedicada. `PATCH` alterna el estado, por lo que no es idempotente. En ASE conviene sustituirlo por una operación explícita de pago/impago y una fecha elegida.

### 7.2. Gastos

Se pueden crear, editar, duplicar y eliminar lógicamente. Duplicar abre una copia sin ID, con fecha de hoy; solo se crea al guardar.

```text
IVAsoportado = redondear(base × IVA% / 100)
IVAdeducible = redondear(IVAsoportado × vatDeductible% / 100)
costeEconómico = base + IVAsoportado − IVAdeducible
gastoFiscalDeducible = redondear(costeEconómico × deductible% / 100)
```

No confundir coste económico con gasto fiscal deducible. El sueldo neto estimado resta el coste económico completo; el indicador de gastos deducibles usa el porcentaje fiscal.

Los gastos antiguos sin `paid` se consideran pagados. Los generados por recurrencia se crean pendientes. La fecha de gasto es también la fecha prevista de pago; actualmente no hay campos independientes para emisión y vencimiento del gasto.

### 7.3. Resumen, sueldo y filtros

Las agregaciones viven principalmente en `dashboard.js` y `business.js`.

- Importes e impuestos se agrupan por fecha de emisión.
- Días/horas facturados se agrupan por `serviceMonth`, o mes de emisión si falta.
- Las horas se muestran aparte: no se convierten a días de forma implícita.
- IVA estimado = repercutido − soportado deducible. Un saldo negativo no se presenta como dinero automáticamente recibido.
- Los gráficos muestran valores visibles y totales del período; conservan información en tooltips y tablas.
- Se filtra por año, trimestre o mes y por concepto. La búsqueda incluye descripciones de líneas de factura.
- El orden de fecha puede ser ascendente/descendente. Al editar se mantienen filtros y orden en memoria; si el registro sale del filtro se avisa.
- Los filtros no están persistidos por usuario ni necesariamente sobreviven a recargar la página.
- La media neta anual usa **todos los registros del año seleccionado y divide entre 12**, aunque haya meses sin actividad. No aplica el filtro de concepto a ese total anual.

```text
reservaExtraFactura = redondear(baseFactura × extraIrpfCliente / 100)
netoEstimado = basesFacturadas − retencionesIRPF − reservaExtra − costesEconómicos
mediaNetaAnual = netoEstimadoAnual / 12
```

Ese neto incluye facturas no cobradas: no equivale a caja. Algunas etiquetas históricas hablan de «gastos pagados» aunque esta agregación usa todos los gastos del período. Corrige la terminología al portar, sin cambiar silenciosamente la fórmula.

### 7.4. Caja y previsiones

Se usa el historial completo, sin filtro de año/concepto, y solo movimientos considerados cobrados/pagados hasta hoy. Si falta `paidDate`, se usa la fecha del documento.

```text
cobros = suma(totalCents de facturas cobradas)
pagos = suma(totalCents de gastos pagados)
IVAapartado = max(0, IVA_cobrado − IVA_deducible_pagado − vatPaid)
IRPFextraApartado = max(0, reservasExtraCobradas − extraIrpfUsed)
transferenciasPatrimonio = aportacionesDesdeCaja − retiradasQueVuelvenACaja

disponible = openingBalance + cobros − pagos − withdrawals
             − vatPaid − extraIrpfUsed
             − IVAapartado − IRPFextraApartado
             − transferenciasPatrimonio
```

Los ajustes de caja son importes acumulados de todo el historial. `openingBalance` es anterior al primer movimiento registrado, no el saldo bancario actual. Los impuestos ya pagados reducen simultáneamente caja y reserva restante para no descontarlos dos veces.

Previsión de 30/60/90 días:

- Horizontes acumulados, no sumables.
- Cobros: facturas pendientes con vencimiento entre hoy y el horizonte.
- Pagos: gastos pendientes por fecha y futuras recurrencias calculadas sin crearlas anticipadamente.
- Los cobros ya vencidos se muestran aparte, sin asumir que se cobrarán mañana.
- Ahorro/inversión previstos se presentan en una columna separada; no se descuentan de caja hasta registrar movimientos reales.
- La variación mostrada es anterior a reservas y aportaciones personales.

No hay conciliación bancaria ni previsión de nuevas ventas o liquidaciones fiscales futuras.

### 7.5. Rentabilidad por cliente y objetivo de sueldo

- Gastos repartidos entre clientes proporcionalmente a su base facturada, no por imputación directa.
- Tarifa media diaria y horaria calculadas por separado, ponderando cantidades.
- Neto por cliente después de IRPF, reserva extra y reparto de gastos.
- Retraso medio: solo cobros con fecha conocida, usando `max(0, paidDate - due)`.

El objetivo de sueldo usa la retención y reserva media ponderada del año; si no hay facturas, una hipótesis del 15 %. El gasto mensual sugerido es el coste anual dividido entre 12, editable.

```text
baseMensualNecesaria = (netoObjetivo + gastosMensuales) / (1 − tasaRetenciónYReserva)
tarifaDía = baseMensualNecesaria / díasFacturables
tarifaHora = baseMensualNecesaria / horasFacturables
```

Tarifa diaria y horaria son alternativas, no se suman. Si la tasa es >= 100 %, no se calcula un resultado válido. No se deriva automáticamente una liquidación final de IRPF.

### 7.6. Recurrencias

Cada regla mensual conserva el día deseado `day`. Un día 31 pasa al último día de febrero y vuelve al 31 en marzo.

- Generación en `generate_recurring`, al consultar `GET /api/records`.
- Solo crea fechas vencidas hasta hoy.
- Nuevos gastos pendientes de pago y vinculados mediante `recurringId`.
- Avanza `nextDate` dentro de la transacción para evitar duplicaciones por nuevas lecturas.
- Un límite por ejecución evita generar más de 1.200 gastos en una petición.
- Detener una regla conserva los gastos existentes.
- No hay proceso que trabaje con la aplicación cerrada.

Para ASE, mover a un job/worker programado por negocio y hacer el GET de listado de solo lectura. Usar una clave única `(business_id, recurring_rule_id, occurrence_date)` además de transacciones y bloqueo.

### 7.7. Timesheet

- Calendario global de la persona, no asignado a clientes.
- Lunes a viernes son laborables previstos.
- El usuario marca manualmente vacaciones/festivos; no hay consulta automática de calendarios oficiales.
- No se permite marcar un día simultáneamente en ambas categorías.
- Vacaciones/festivos en fin de semana no restan otra jornada.
- Marcar días no crea ni modifica facturas.
- El PDF marca **X solo en días laborables previstos**, dejando sin marca vacaciones, festivos y fines de semana. Incluye totales.
- No acredita asistencia ni horas efectivamente trabajadas.

### 7.8. PDF y marca

ReportLab genera facturas A4 con emisor, cliente, detalle de líneas, impuestos, vencimiento, total e IBAN; y timesheets con calendario y resumen.

`profile.logo` se guarda como data URL base64 PNG/JPEG/WebP. La interfaz admite un archivo de hasta 500 KB y el backend limita/valida el formato codificado. `invoiceColor` es un hexadecimal de seis dígitos.

En ASE se recomienda almacenar logos privados en almacenamiento de objetos y conservar referencias, no replicar grandes cadenas base64 en cada snapshot. Mantener el acceso autorizado al generar y descargar PDF. Sustituir rutas de fuentes/dependencias locales por recursos del despliegue.

### 7.9. Simulador de tarifas

Reutiliza el volumen de las facturas filtradas y permite subida porcentual o extra por día/hora, para todos los clientes o uno.

- Recalcula líneas, IVA, IRPF, reserva y neto.
- Mantiene gastos del período completos, sin repartirlos al seleccionar un cliente.
- No modifica facturas ni tarifas guardadas.
- No proyecta automáticamente nuevas jornadas, ventas ni gastos.

### 7.10. Ahorro e inversiones

Los planes personales se separan de la actividad del autónomo.

- Categoría `saving`: rentabilidad 0 %.
- Categoría `investment`: **rentabilidad anual efectiva** introducida por el usuario; no es una rentabilidad mensual ni una recomendación.
- Horizonte: entre 1 y 120 meses.
- El capital inicial representa patrimonio ya existente; no descuenta caja otra vez.
- La aportación mensual define un objetivo, no una transferencia automática.
- Pausar quita el compromiso de previsiones futuras, pero la comparación histórica y simulación mantienen la pauta actual.

Interés compuesto:

```text
rAnual = annualRate / 100
rMensual = (1 + rAnual)^(1/12) − 1
rendimientoMes = redondearCéntimos(saldoAnterior × rMensual)
saldoFinMes = saldoAnterior + rendimientoMes + aportaciónMensual
```

La aportación se hace **al final de mes**, después del rendimiento. No dividir la tasa anual entre 12. La proyección comienza en `startMonth`, no necesariamente en el mes actual. No incluye impuestos sobre inversiones, comisiones ni inflación.

Ejemplo de aceptación: 1.000 € iniciales, 12 % anual y cero aportaciones deben dar aproximadamente 1.120 € a los 12 meses, con pequeñas diferencias por redondeo mensual.

Compatibilidad: planes antiguos con `monthlyRate` se convierten mediante `(1 + rMensual)^12 - 1`. Hay migración al inicio del servidor y normalización al restaurar copias antiguas.

Movimientos reales:

- `contribution`: suma al saldo y a las aportaciones.
- `withdrawal`: resta al saldo; no puede superar el saldo existente en esa fecha.
- `valuation`: sustituye el valor total de la inversión en esa fecha. Solo para inversiones. No es un dividendo ni una aportación.
- Orden de validación: fecha y después ID.
- Resultado real = saldo actual − capital aportado + retiradas.
- Una valoración no transfiere caja. Aportaciones/retiradas solo afectan a caja si `fromBusiness=true`.
- No duplicar esos movimientos en las retiradas personales manuales de ajustes de caja.
- Editar/eliminar un movimiento no puede invalidar retiradas posteriores.
- No se puede borrar un plan con movimientos o importaciones activas.

El saldo real no se actualiza con la tasa simulada. La evolución real depende exclusivamente de movimientos y valoraciones registrados.

### 7.11. Importación de cartera CSV

No hay conexión con Trade Republic ni otro bróker. Se importa un archivo elegido por el usuario; no se solicitan credenciales. No se presupone un formato oficial fijo de Trade Republic.

Dos modos:

1. **`positions`:** captura completa de posiciones de una plataforma/cuenta en una fecha.
2. **`transactions`:** historial de compras, ventas, dividendos, intereses, comisiones, ingresos y retiradas.

Flujo:

```text
Seleccionar plan de inversión + archivo + plataforma
→ inspect: cabeceras / muestra / sugerencias
→ asignar columnas, formatos y significado de tipos
→ preview: todas las filas, duplicados, errores y hash
→ confirmar
→ import: recalcular, comparar hash y guardar transaccionalmente
```

Características a conservar:

- UTF-8 o Windows-1252 en el navegador; BOM admitido.
- Separadores coma, punto y coma, tabulador y barra vertical.
- Números con coma o punto decimal, seleccionados explícitamente; no adivinar números ambiguos.
- Fechas ISO (con hora cuando corresponda), día/mes/año o mes/día/año.
- Solo EUR; no hacer conversiones implícitas de moneda.
- Máximo 5 MB/5.000 filas, cabeceras únicas, 2 a 80 columnas.
- Tipos ambiguos como `TRADE` requieren asignación explícita. Ignorar filas también debe ser una elección explícita.
- Una fila inválida bloquea toda la importación; la pantalla muestra hasta 100 errores/filas de muestra, pero se valida el archivo entero.
- El hash de preview verifica que lo confirmado sigue siendo lo revisado, pero no es un mecanismo de autenticación.

Posiciones:

- Nombre o identificador, cantidad positiva y valor total o precio por título.
- Coste total o medio opcional; sin él no se inventa una ganancia.
- Valor total prevalece sobre precio; coste total prevalece sobre coste medio.
- Lotes del mismo identificador se agrupan sumando cantidad, coste conocido y valor.
- Cada captura es completa para esa plataforma/fecha. No se fusiona silenciosamente con la anterior.
- Una captura distinta para la misma fecha requiere `replaceSnapshot=true`.
- La vista usa la última captura de cada plataforma/cuenta; puede combinar fechas diferentes y debe indicarlo.
- «Usar como valoración del plan» abre un movimiento manual de valoración para revisarlo y guardarlo, sin aplicarlo automáticamente.

Movimientos:

- Tipos canónicos: `buy`, `sell`, `dividend`, `interest`, `fee`, `deposit`, `withdrawal`.
- Compras/ventas requieren cantidad positiva y activo.
- Compras/comisiones/retiradas tienen signo negativo; ventas/dividendos/intereses/ingresos, positivo.
- Las comisiones de columna son informativas y no se restan otra vez del importe.
- No generan `wealthentry` ni afectan a caja. Una compra no es necesariamente una nueva aportación de dinero.
- No proporcionan por sí solos posiciones actuales ni cotizaciones.
- Deduplicación por referencia única; si falta, por contenido y ordinal de repetición dentro del archivo.
- Sin referencias, los períodos parciales solapados con operaciones idénticas son ambiguos. No prometer deduplicación perfecta: mostrar esa limitación y preferir historial completo/referencias.
- Eliminar un lote elimina sus datos importados activos, pero no una valoración manual que el usuario guardó aparte.

Ejemplo de payload de preview de posiciones:

```json
{
  "planId": 7,
  "source": "Trade Republic - cuenta de ejemplo",
  "mode": "positions",
  "snapshotDate": "2026-10-31",
  "numberFormat": "comma",
  "dateFormat": "iso",
  "delimiter": ";",
  "mapping": {"name":"Nombre","quantity":"Cantidad","value":"Valor","cost":"Coste"},
  "csvText": "Nombre;Cantidad;Valor;Coste\nActivo de ejemplo;10;1000,00;950,00\n",
  "fileName": "cartera.csv",
  "replaceSnapshot": false
}
```

Para confirmar se envía el mismo payload añadiendo el `previewHash` recibido. El plan debe existir y ser de inversión. Las fechas no pueden ser futuras ni anteriores al mes inicial del plan.

### 7.12. Copias completas

`backup_payload` exporta todos los registros, incluidos eliminados, con:

```json
{
  "app": "cuenta-clara-backup",
  "version": 1,
  "created": "fecha ISO",
  "checksum": "SHA-256 de records serializado canónicamente",
  "records": [{"id": 1, "kind": "profile", "data": {}}]
}
```

La forma mostrada es ilustrativa, no una copia válida para restaurar.

La restauración comprueba formato, checksum, IDs, tipos y ciertas relaciones, crea una copia anterior en `data/backups/` y reemplaza la tabla dentro de una transacción. La exportación sencilla del botón de registros no es una copia completa restaurable.

El checksum detecta alteraciones accidentales; no firma el archivo ni acredita quién lo creó. En ASE, una restauración ordinaria debe quedar limitada al negocio autorizado, nunca reemplazar toda la base compartida.

## 8. Arquitectura de integración propuesta

Esta sección describe trabajo pendiente, no componentes ya implementados.

### Opción A: conservar Python como servicio del módulo

Reutilizar validaciones, importador CSV y generación PDF, pero colocar sus operaciones en el framework/API y despliegue de producción elegido para ASE. Un adaptador verifica la identidad de ASE y pasa un contexto de negocio confiable.

Útil si mantener Python es compatible con el hosting y la operación de ASE. No publicar directamente `ThreadingHTTPServer` como backend final.

### Opción B: portar el dominio al backend existente de ASE

Reimplementar las reglas con la tecnología de ASE, conservando pruebas, ejemplos y contratos funcionales. Puede simplificar usuarios, permisos y transacciones si ASE ya tiene una arquitectura madura.

No portar los cálculos mediante conversiones informales de `float`; crear pruebas de paridad en céntimos antes de cambiar de motor.

### Interfaz

Adaptar los módulos a las rutas, componentes y diseño de ASE. La aplicación actual comparte estado mediante variables globales y scripts clásicos cargados en este orden:

```text
dashboard.js → simulator.js → business.js → wealth.js → portfolio.js → app.js
```

Muchas funciones usan globales declarados en otros archivos cuando se ejecutan. Si se convierten a módulos/componentes, sustituirlos por imports y estado explícitos, no copiar scripts aislados.

No basta con un iframe: no resuelve autenticación, separación de datos, permisos, restauración ni suscripciones. Puede servir como presentación de una aplicación ya protegida, no como aislamiento de seguridad.

## 9. Datos y aislamiento para varios usuarios

El concepto de negocio/espacio de trabajo debe ser independiente de su lista de clientes. **Un `client` es un cliente del autónomo, no un usuario de ASE ni un tenant.**

Adaptación mínima propuesta:

- Identidad ASE → pertenencia a uno o más negocios.
- Toda entidad privada con `business_id` o el ámbito equivalente que use ASE.
- Roles dentro del negocio: propietario y, si se implementa, gestoría/colaborador con permisos específicos.
- Validación de pertenencia en cada lectura, escritura, referencia, PDF, CSV, copia y restauración.
- Las relaciones de factura/cliente, movimiento/plan e importación/plan deben pertenecer al mismo ámbito.
- No confiar en un `business_id` o `user_id` enviado por el navegador sin comprobarlo con la sesión del servidor.
- Configuraciones únicas por negocio: perfil, ajustes de caja y calendario mensual.

Una migración a tablas normalizadas puede incluir:

```text
ASE users / organizations / memberships       (reutilizar lo existente)
business_profiles, clients
invoices, invoice_lines, invoice_payments
expenses, recurring_rules, recurring_occurrences
timesheets, timesheet_days
cash_adjustments
wealth_plans, wealth_entries
portfolio_imports, portfolio_snapshots, portfolio_positions, portfolio_transactions
audit_events
```

Esta lista es una propuesta de diseño. No impone PostgreSQL si ASE tiene otra base adecuada. Si se adopta JSON/JSONB, mantener también columnas de ámbito, claves, índices y restricciones explícitas.

## 10. Funciones por plan de ASE

Consultar los planes reales de ASE antes de definir una matriz comercial. Los nombres siguientes son capacidades técnicas sugeridas, no suscripciones existentes:

```text
autonomo.invoicing
autonomo.expenses
autonomo.timesheet
autonomo.analytics
autonomo.rate_simulator
autonomo.cash_forecast
autonomo.recurring_expenses
autonomo.wealth
autonomo.portfolio_import
autonomo.backup_export
autonomo.backup_restore
```

Comprobar capacidades y límites en el backend además de la interfaz. Definir límites de registros, tamaño de importación, frecuencia de exportaciones y almacenamiento de archivos cuando tenga sentido para los planes reales.

Una bajada de plan no debe borrar información financiera ni datos de inversión silenciosamente. Definir acceso de lectura/exportación y conservación según el producto de ASE.

## 11. Cambios necesarios antes de producción

### Identidad, permisos y API

- Añadir autenticación de ASE y comprobaciones de ámbito a todos los servicios.
- Sustituir cuerpos JSON genéricos por DTO/esquemas con campos permitidos. El POST actual no es una frontera de seguridad para datos multiusuario: no asumir que todas las relaciones/campos reservados están protegidos en todas las rutas.
- Reservar al servidor IDs, propietarios, numeración, snapshots fiscales y totales calculados.
- La comprobación actual de `Origin` compara con `'http://' + Host`; fallará o será insuficiente detrás de HTTPS/proxies. Rehacerla según las sesiones, CSRF/CORS y orígenes de ASE. No resolverlo quitando la protección sin sustitución.
- Normalizar errores y evitar exponer trazas o rutas privadas al cliente.
- Aplicar límites de carga, tiempo, frecuencia y memoria, especialmente a CSV, logos, PDF y restauración.

### Despliegue y rutas

- Servidor de aplicación y proxy/hosting apropiados, HTTPS y configuración por entorno.
- Secretos de ASE por su mecanismo habitual; no hay un archivo de credenciales que deba copiarse desde esta aplicación.
- Persistencia y copias fuera de la carpeta pública y del sistema de archivos efímero del despliegue.
- API y rutas estáticas configurables. Actualmente `/style.css`, `/app.js` y `/api/...` son absolutas respecto a la raíz: romperán si se monta bajo un prefijo sin adaptación.
- `PORT` no permite cambiar el host de escucha actual: para contenedores/servicios debe configurarse correctamente, conservando el aislamiento de red del despliegue.
- Definir `Europe/Madrid` para fechas de negocio. Hoy se mezclan fechas locales del navegador y del servidor; no depender de la zona por defecto del host.

### Dominio y consistencia

- Centralizar cálculos de dominio en el servidor o en una biblioteca compartida validada. Actualmente los cálculos de factura/gasto son de servidor, pero gran parte del resumen, caja y simuladores son de navegador.
- Crear un contador de factura atómico y único por negocio/serie/período decidido, migrando los números existentes sin renumerarlos silenciosamente.
- Usar acciones de cobro explícitas, fechas elegibles e idempotencia; añadir pagos parciales solo si se decide como función nueva.
- Resolver y documentar la diferencia actual entre reglas de vencimiento `nextMonth` y `days` en el backend.
- Separar fecha de emisión, vencimiento y pago de gastos si la integración necesita previsiones precisas.
- Introducir auditoría de operaciones y concurrencia optimista para edición.
- Eliminar escrituras durante GET y usar recurrencias idempotentes programadas.
- Un porcentaje extra de IRPF es una reserva privada: no convertirlo en un impuesto adicional en la factura.
- Mantener separados gastos fiscales, gastos económicos, patrimonio y transferencias personales.

### Archivos, privacidad y cumplimiento del producto

- Autorizar descargas y evitar enlaces públicos permanentes a documentos privados.
- Escapar texto en HTML/PDF y validar logos. Evitar datos de CSV, NIF/IBAN o copias completas en logs generales.
- Definir política de retención y acceso a información de autónomos e inversiones con el responsable de ASE.
- El PDF actual es una presentación de factura; no implementa por sí mismo emisión fiscal certificada, VeriFactu, rectificativas ni presentación de modelos tributarios. No anunciar esas capacidades sin una implementación y revisión específicas.
- La proyección de inversiones es matemática y manual, no una conexión a un bróker ni una recomendación de inversión.

## 12. Migración de datos existentes

1. Obtener una copia completa y una copia consistente del SQLite, manteniéndolas privadas.
2. Probar en una base de staging separada, nunca usando los datos personales como fixtures públicas.
3. Crear el usuario/negocio destino y vincularle explícitamente el conjunto de datos local.
4. Inventariar registros activos y eliminados por tipo, sin exponer su contenido en logs.
5. Transformar importes preservando céntimos, porcentajes decimales, fechas y referencias.
6. Conservar números de factura, estados de cobro, snapshots y vínculos de importación.
7. Mantener compatibilidad con facturas de una línea, gastos antiguos sin `paid` y planes antiguos con tasa mensual.
8. Reasignar IDs con una tabla de correspondencia si ASE no puede conservarlos; actualizar todas las referencias y la deduplicación de importaciones.
9. Importar primero entidades padre y después dependientes; conservar también registros eliminados y sus relaciones históricas.
10. Comparar totales antes/después: bases, IVA, IRPF, cobros, gastos, caja, calendarios, saldos reales, capturas y resultados de simulación de control.
11. Verificar copias, PDF, permisos y referencias cruzadas en staging.
12. Definir corte, rollback y despliegue siguiendo el proceso de ASE. No hacer una doble escritura improvisada entre el SQLite personal y la base de ASE.

Al cambiar IDs, los hashes de importación que incluyen `planId` necesitan una estrategia de migración. No basta con conservar el hash antiguo y deduplicar nuevas importaciones calculadas con un ID distinto.

## 13. Pruebas y criterios de aceptación

Pruebas actuales, desde la raíz:

```powershell
python -m unittest discover -s tests -v
node tests/test_business.js
node tests/test_wealth.js
node tests/test_portfolio.js
```

Las pruebas Python usan bases temporales y un servidor local de prueba. En entornos aislados pueden requerir permisos de socket/temporal. No deben sustituirse sus rutas por la base real. Las pruebas JavaScript utilizan `vm` y fixtures; no son una prueba visual del navegador.

Cobertura existente: recurrencias, cobros/gastos, copias/restauración, planes y movimientos personales, interés compuesto anual, efecto en caja e importaciones CSV. No asumir que existe una suite de extremo a extremo completa para todas las pantallas o cumplimiento fiscal.

Criterios mínimos de la integración:

- [ ] Un usuario no puede leer, modificar ni exportar datos de otro negocio, aunque conozca sus IDs.
- [ ] Los permisos de suscripción también se aplican a llamadas directas a la API, PDF, CSV y copias.
- [ ] Una factura multilínea conserva sus totales exactos antes y después de migrar.
- [ ] Factura de febrero vence el último día de marzo con regla `nextMonth`.
- [ ] Editar no pierde filtros ni renumera la factura.
- [ ] Borrar no reutiliza numeración ni equivale a una rectificación fiscal.
- [ ] Retención y reserva extra permanecen separadas en factura, resumen y caja.
- [ ] Los cobros pendientes no se suman a disponible.
- [ ] Impuestos liquidados y transferencias personales no se descuentan dos veces.
- [ ] Días facturados se asignan al mes trabajado y no se suman horas como días.
- [ ] Vacaciones/festivos no se descuentan dos veces si caen en fin de semana.
- [ ] Timesheet PDF marca X solo en los días de trabajo previstos.
- [ ] Recurrencias concurrentes no crean el mismo gasto dos veces.
- [ ] Ahorro e inversión planificados no crean transferencias reales.
- [ ] 12 % anual sin aportaciones equivale a ~12 % en doce meses, no a aplicar 12 % cada mes.
- [ ] Una valoración no se interpreta como aportación y una retirada no supera el saldo histórico.
- [ ] Importar de nuevo un CSV no duplica operaciones identificables; las ambigüedades se explican.
- [ ] Una fila inválida impide guardar todo el lote, sin escrituras parciales.
- [ ] Capturas e historial de compras no se confunden con cotizaciones en directo.
- [ ] Restaurar solo afecta al ámbito autorizado y conserva una copia de seguridad previa.
- [ ] Funcionan rutas bajo HTTPS y el prefijo de ASE sin dependencias de `localhost`.
- [ ] Pantallas, modales, filtros, gráficos y tablas son utilizables en móvil y escritorio.
- [ ] Se ha probado la migración y la reversión con datos de prueba antes de mover datos personales.

## 14. Secuencia de trabajo propuesta

### Fase 1: inspección de ASE

Localizar instrucciones del repositorio, comprobar el stack, identidad, modelos de negocio, planes, rutas y hosting. Documentar qué se conserva y qué se porta. Si falta una decisión que no pueda obtenerse del código o configuración, plantear una pregunta concreta al responsable.

### Fase 2: seguridad y persistencia

Crear el ámbito de negocio, autorización, capacidades de plan y migraciones. Preparar servicios de dominio, almacenamiento privado y una importación de datos de prueba. Probar aislamiento antes de conectar el historial personal.

### Fase 3: integración funcional

Portar clientes/perfil, facturas/gastos, fechas/cobros, PDF, calendarios, resumen, caja, recurrencias, simulador, objetivos, ahorro/inversiones e importador. Preservar explícitamente las reglas descritas arriba.

### Fase 4: operación y migración

Añadir worker de recurrencias, copias/restauración por negocio, auditoría, límites y manejo de fallos. Ejecutar comparativas y pruebas de extremo a extremo. Preparar el despliegue según el flujo real de ASE.

### Entrega que debe producir Claude

- Integración en el código real de ASE, con cambios de esquema versionados.
- Documento de decisiones y diferencias justificadas respecto al comportamiento local.
- Mecanismo de migración con modo de comprobación y rollback definido.
- Pruebas funcionales, de aislamiento y de permisos por plan.
- Configuración de desarrollo/producción sin secretos incluidos.
- Instrucciones para ejecutar, desplegar, generar copias y recuperar datos.
- Lista concreta de limitaciones restantes; no presentar como implementadas funciones solo propuestas.

## 15. Prompt breve para iniciar el trabajo en Claude

> Lee `INTEGRACION_ASE_PARA_CLAUDE.md` y examina tanto este proyecto como el repositorio de ASE. Integra Cuenta Clara como módulo de ASE reutilizando su autenticación, negocios, planes, diseño y despliegue existentes. Distingue funciones actuales de adaptaciones propuestas. Conserva los cálculos y datos, añade aislamiento y permisos en servidor, y prueba la migración en un entorno separado. No expongas el servidor local, no mezcles datos de usuarios y no copies datos personales a fixtures, logs o repositorios públicos. Empieza identificando el stack de ASE y el plan técnico concreto, y continúa con cambios verificables según las instrucciones del proyecto.

## 16. Qué compartir con Claude

Comparte este Markdown junto con el **código fuente completo** de ambos proyectos o acceso a sus repositorios autorizados. El documento no contiene el código ni una base de datos.

Para portar funciones no hace falta compartir la base personal, logos, CSV originales, extractos ni claves de acceso. Si además se va a migrar el historial real, proporcionar la copia privada por un mecanismo autorizado y limitar su uso a esa migración. `.gitignore` excluye esos datos precisamente para evitar que se incorporen por accidente al repositorio.
