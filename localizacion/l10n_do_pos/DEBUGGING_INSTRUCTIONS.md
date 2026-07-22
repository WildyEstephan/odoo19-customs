# Instrucciones de Depuración L10N_DO_POS v18.0.1.0.5

## Cambios Realizados

✅ **Problemas Resueltos**:
- Eliminado debug.js que causaba conflictos con imports dinámicos
- Optimizado orden de carga de assets en manifest
- Simplificados logs de depuración para reducir ruido
- Todos los imports estáticos funcionan correctamente

## Pasos de Depuración

### 1. **Reiniciar Odoo** para regenerar assets:
```bash
sudo systemctl restart odoo18
```

### 2. **Verificar en la consola del navegador**:
- Ir a configuración POS → Abrir POS
- Presionar F12 → pestaña "Console"
- Buscar logs `[L10N_DO_POS]`

### 3. **Logs esperados**:
```
[L10N_DO_POS] models.js loaded - starting patches
[L10N_DO_POS] PosStore setup() called - BEGIN
[L10N_DO_POS] super.setup() completed successfully
[L10N_DO_POS] payer_types_selection initialized
[L10N_DO_POS] PosStore setup() - END
[L10N_DO_POS] PaymentScreen.js loaded
[L10N_DO_POS] PartnerLine.js loaded
[L10N_DO_POS] MoveReversal.js loaded
```

## Depuración Avanzada desde Shell

Usar el script de depuración incluido:

```bash
# Desde el servidor Odoo
cd /path/to/addons/l10n_do_pos
python -c "exec(open('debug_shell.py').read())"

# O desde shell de Odoo
./odoo-bin shell -d your_database -c exec(open('/path/to/l10n_do_pos/debug_shell.py').read())
```

El script verificará:
- Estado de instalación del módulo
- Dependencias
- Assets de POS
- Configuración POS
- Vistas y templates

## Si Persisten Errores

1. **Verificar que l10n_do_accounting esté instalado**
2. **Actualizar módulo**: Apps → l10n_do_pos → Upgrade
3. **Limpiar cache del navegador**
4. **Verificar logs del servidor**: `/var/log/odoo18/odoo.log`
5. **Ejecutar script de depuración** para diagnóstico completo

## Archivos de Depuración

- `debug_shell.py` - Script de diagnóstico del servidor
- `DEBUGGING_INSTRUCTIONS.md` - Este archivo
- `cleanup_debug.sh` - Limpieza de archivos temporales (opcional)

**Estado**: Módulo completamente migrado y funcional en v18.0.1.0.9

## Últimas Correcciones (v18.0.1.0.9)

✅ **Funcionalidad "Solo Facturación" Corregida**:
- Configuración automática del cliente de consumo por defecto
- Forzado automático de facturación cuando "Only Invoice" está activado
- Hook de instalación para configurar automáticamente POS existentes
- Cliente de consumo se asigna automáticamente al crear órdenes

✅ **Template de Recibo Dominicano**:
- Template personalizado con formato NCF completo
- Muestra información de contribuyente (RNC/Cédula)
- Header con datos de la empresa dominicana
- Footer con información legal requerida

✅ **Configuración Automática**:
- Post-install hook configura automáticamente cliente por defecto
- Método automático para aplicar configuración dominicana a nuevas órdenes
- Protección contra desactivación accidental de facturación

## Flujo Completo Funcionando

El módulo ahora funciona completamente para República Dominicana:
1. ✅ Selección de productos
2. ✅ Cliente de consumo automático + tipos de pagador DGII
3. ✅ Pantalla de pago con facturación forzada
4. ✅ Procesamiento de órdenes con NCF automático
5. ✅ Recibo con formato legal dominicano
6. ✅ Funcionalidad de notas de crédito
7. ✅ Configuración automática al instalar 