#!/bin/bash
# ══════════════════════════════════════════════════════════
#  Instalación y arranque — Gestor Vísceras Colbeef v2.0
#  Ejecutar en el servidor de intranet (Ubuntu/Debian/Windows WSL)
# ══════════════════════════════════════════════════════════

echo "=== Gestor Vísceras Colbeef — Setup ==="

# 1. Verificar Python
python3 --version || { echo "ERROR: Instala Python 3.10+"; exit 1; }

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "IMPORTANTE: Edita el archivo .env con los datos reales de tu servidor PostgreSQL:"
  echo "  DB_HOST=<IP del servidor PostgreSQL>"
  echo "  DB_NAME=<nombre de la base de datos>"
  echo "  DB_USER=<usuario>"
  echo "  DB_PASSWORD=<contraseña>"
  echo ""
  echo "Luego vuelve a ejecutar: python main.py"
  exit 0
fi

# 4. Iniciar servidor
echo "Iniciando servidor en http://0.0.0.0:8000 ..."
echo "Accede desde cualquier PC de la intranet: http://<IP-DE-ESTE-SERVIDOR>:8000"
python main.py
