# -*- coding: utf-8 -*-
"""
Script de depuración para l10n_do_pos
Ejecutar desde shell de Odoo: python debug_shell.py

Para usar:
1. Ir al directorio del módulo
2. Ejecutar: python -c "exec(open('debug_shell.py').read())"
O desde Odoo shell:
python -c "exec(open('/path/to/l10n_do_pos/debug_shell.py').read())"
"""

def debug_l10n_do_pos():
    print("=== DEBUG L10N_DO_POS ===")
    
    # 1. Verificar que el módulo está instalado
    print("\n1. Verificando instalación del módulo...")
    try:
        module = env['ir.module.module'].search([('name', '=', 'l10n_do_pos')])
        if module:
            print(f"   ✓ Módulo encontrado: {module.display_name}")
            print(f"   Estado: {module.state}")
            print(f"   Versión: {module.latest_version}")
        else:
            print("   ✗ Módulo no encontrado")
            return
    except Exception as e:
        print(f"   ✗ Error verificando módulo: {e}")
        return
    
    # 2. Verificar dependencias
    print("\n2. Verificando dependencias...")
    try:
        dependencies = module.dependencies_id
        for dep in dependencies:
            dep_module = env['ir.module.module'].search([('name', '=', dep.name)])
            if dep_module and dep_module.state == 'installed':
                print(f"   ✓ {dep.name}: instalado")
            else:
                print(f"   ✗ {dep.name}: NO instalado")
    except Exception as e:
        print(f"   ✗ Error verificando dependencias: {e}")
    
    # 3. Verificar assets
    print("\n3. Verificando assets de POS...")
    try:
        # Buscar assets relacionados con point_of_sale
        assets = env['ir.asset'].search([
            ('bundle', '=', 'point_of_sale._assets_pos'),
            ('path', 'ilike', 'l10n_do_pos')
        ])
        if assets:
            print(f"   ✓ Assets encontrados: {len(assets)}")
            for asset in assets:
                print(f"     - {asset.path}")
        else:
            print("   ✗ No se encontraron assets")
    except Exception as e:
        print(f"   ✗ Error verificando assets: {e}")
    
    # 4. Verificar configuración POS
    print("\n4. Verificando configuración POS...")
    try:
        pos_config = env['pos.config'].search([], limit=1)
        if pos_config:
            print(f"   ✓ Configuración POS encontrada: {pos_config.name}")
            # Verificar si el módulo está activo en esta config
            print(f"   Compañía: {pos_config.company_id.name}")
        else:
            print("   ✗ No se encontró configuración POS")
    except Exception as e:
        print(f"   ✗ Error verificando POS config: {e}")
    
    # 5. Verificar vistas y templates
    print("\n5. Verificando vistas y templates...")
    try:
        views = env['ir.ui.view'].search([('name', 'ilike', 'l10n_do_pos')])
        print(f"   ✓ Vistas encontradas: {len(views)}")
        for view in views:
            print(f"     - {view.name} (ID: {view.id})")
    except Exception as e:
        print(f"   ✗ Error verificando vistas: {e}")
    
    # 6. Verificar si hay errores en los logs
    print("\n6. Recomendaciones de depuración:")
    print("   - Reiniciar servidor Odoo: sudo systemctl restart odoo18")
    print("   - Limpiar cache del navegador")
    print("   - Verificar logs en: /var/log/odoo18/odoo.log")
    print("   - En el navegador, abrir Console (F12) y buscar errores de [L10N_DO_POS]")
    
    print("\n=== FIN DEBUG ===")

# Ejecutar automáticamente si se importa
if __name__ == "__main__":
    debug_l10n_do_pos()
else:
    # Si se ejecuta desde shell de Odoo
    debug_l10n_do_pos() 