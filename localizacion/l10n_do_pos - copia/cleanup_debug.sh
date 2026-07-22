#!/bin/bash

# Script para limpiar archivos de depuración temporales del módulo l10n_do_pos

echo "Limpiando archivos de depuración temporales..."

# Eliminar archivo debug.js
if [ -f "static/src/app/debug.js" ]; then
    rm static/src/app/debug.js
    echo "✓ Eliminado debug.js"
fi

# Eliminar archivo de instrucciones
if [ -f "DEBUGGING_INSTRUCTIONS.md" ]; then
    rm DEBUGGING_INSTRUCTIONS.md
    echo "✓ Eliminado DEBUGGING_INSTRUCTIONS.md"
fi

# Eliminar este script
rm "$0"
echo "✓ Script de limpieza eliminado"

echo "Limpieza completada. No olvides:"
echo "1. Quitar los console.log() de los archivos JavaScript"
echo "2. Remove debug.js from __manifest__.py assets"
echo "3. Reiniciar Odoo para regenerar assets" 