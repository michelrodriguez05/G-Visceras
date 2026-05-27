# G-Visceras · Colbeef v4

Gestor de Vísceras — FastAPI + PostgreSQL (solo lectura).

## Arranque rápido (Windows)

| Archivo | Acción |
|---------|--------|
| `setup.bat` | Primera vez: crea venv e instala dependencias |
| `start.bat` | Inicia el servidor en segundo plano |
| `stop.bat` | Detiene el servidor |
| `restart.bat` | Reinicia el backend |
| `status.bat` | Ver si está activo + últimas líneas del log |
| `start-console.bat` | Inicia con ventana visible (depuración) |
| `install-autostart.bat` | Arranca al iniciar sesión en Windows |
| `uninstall-autostart.bat` | Quita el autoarranque |

### URLs

- En este PC: http://localhost:8000
- Desde la red: http://IP-DE-ESTE-PC:8000

Log del servidor: `logs/server.log`

## Configuración `.env`

```env
POSTGRES_HOST=10.64.1.47
POSTGRES_DB=sirt
POSTGRES_USER=acceso
POSTGRES_PASSWORD=...
POSTGRES_PORT=5432
APP_HOST=0.0.0.0
APP_PORT=8000
```

## Checklist de pruebas

1. Ejecutar `start.bat` → badge verde **BD: sirt**
2. Dashboard → Actualizar datos
3. Decomisos → Consultar y comparar con Excel
4. Despachos → Elegir turno → Procesar → PDF
5. Informe → Autocompletar → Guardar → PDF por secciones
6. Cruce Diario → Procesar → filtrar estados → PDF

## Endpoints nuevos v4

- `GET /api/salidas?fecha=YYYY-MM-DD&dias=1`
- `GET /api/decomisos_rango?fecha=YYYY-MM-DD&dias=4`
- `GET /api/cruce_diario?fecha=YYYY-MM-DD&turno=DxL&dias_decomisos=4`

## Requisito de red

El servidor PostgreSQL debe permitir la IP de este PC en `pg_hba.conf` (red intranet).
