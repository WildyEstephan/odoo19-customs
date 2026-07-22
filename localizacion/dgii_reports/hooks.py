# -*- coding: utf-8 -*-
# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.

# MODIFICADO: Arturo Diaz Lora - 2026-03-24 10:00
# Razón: Reescribir matching de impuestos para usar tax_group + amount
# en vez de solo nombre. Corrección de CR1: impuestos de venta no se
# configuraban porque los nombres no coincidían.

import logging

_logger = logging.getLogger(__name__)


def _configure_taxes_dgii(env):
    """
    Configura purchase_tax_type e isr_retention_type en impuestos
    según las reglas DGII de República Dominicana.

    Estrategia dual:
    1. Matching por nombre exacto (para purchase taxes conocidos)
    2. Matching por tax_group + type_tax_use + amount (para todos, especialmente ventas)
    """
    Tax = env['account.tax']
    updated_count = 0

    # ================================================================
    # PARTE 1: Configuración por nombre exacto (purchase taxes)
    # Estos ya funcionan correctamente, se mantienen.
    # ================================================================
    name_based_updates = [
        # ITBIS Normal de Compras
        ('18% ITBIS', 'purchase', 'itbis', None),
        ('18% ITBIS Serv.', 'purchase', 'itbis', None),
        ('18% ITBIS Imp.', 'purchase', 'itbis', None),
        ('16% ITBIS', 'purchase', 'itbis', None),
        ('9% ITBIS', 'purchase', 'itbis', None),
        ('8% ITBIS', 'purchase', 'itbis', None),
        # ITBIS al Costo
        ('18% Cost Good', 'purchase', 'itbis', None),
        ('18% Cost Serv.', 'purchase', 'itbis', None),
        # ITBIS Retenido
        ('-100% ITBIS (N07-09)', 'purchase', 'ritbis', None),
        ('-100% ITBIS (N01-11)', 'purchase', 'ritbis', None),
        ('-100% ITBIS (R293-11)', 'purchase', 'ritbis', None),
        ('-75% ITBIS (N08-10)', 'purchase', 'ritbis', None),
        ('-30% ITBIS Leg. (N02-05)', 'purchase', 'ritbis', None),
        ('75%', 'purchase', 'ritbis', None),
        ('2% Mat.', 'purchase', 'ritbis', None),
        ('10% Serv.', 'purchase', 'ritbis', None),
        ('2% Serv P.', 'purchase', 'ritbis', None),
        ('Restaurant', 'purchase', 'ritbis', None),
        # ISR Retenido
        ('-10% ISR Fee', 'purchase', 'isr', '02'),
        ('-10% ISR Rent.', 'purchase', 'isr', '01'),
        ('-10% ISR (L253-12)', 'purchase', 'isr', '03'),
        ('-2% ISR (N07-07)', 'purchase', 'isr', '03'),
        ('-2% ISR Mat.', 'purchase', 'isr', '03'),
        ('-27% ISR (L253-12)', 'purchase', 'isr', '03'),
    ]

    for tax_name, tax_use, tax_type, isr_type in name_based_updates:
        taxes = Tax.search([
            ('name', 'ilike', tax_name),
            ('type_tax_use', '=', tax_use),
            ('active', '=', True),
        ])
        if taxes:
            vals = {'purchase_tax_type': tax_type}
            if tax_type == 'isr' and isr_type:
                vals['isr_retention_type'] = isr_type
            taxes_to_update = taxes.filtered(
                lambda t: t.purchase_tax_type != tax_type or (
                    isr_type and t.isr_retention_type != isr_type
                )
            )
            if taxes_to_update:
                taxes_to_update.write(vals)
                updated_count += len(taxes_to_update)
                _logger.info(
                    "Updated %d tax(es) by name: %s -> %s",
                    len(taxes_to_update), tax_name, vals,
                )

    # ================================================================
    # PARTE 2: Configuración por tax_group (SALE taxes)
    # Los impuestos de venta no matcheaban por nombre.
    # Usamos grupo + monto para clasificarlos correctamente.
    # ================================================================

    # ISR de ventas: grupo ISR/ISR -10%/ISR -2%/ISR -27% con type_tax_use=sale
    isr_group_names = ['ISR', 'ISR -2%', 'ISR -10%', 'ISR -27%']
    isr_sale_taxes = Tax.search([
        ('tax_group_id.name', 'in', isr_group_names),
        ('type_tax_use', '=', 'sale'),
        ('active', '=', True),
        ('purchase_tax_type', 'in', ['none', False]),
    ])
    for tax in isr_sale_taxes:
        vals = {'purchase_tax_type': 'isr'}
        # Inferir isr_retention_type según porcentaje
        pct = abs(tax.amount)
        tax_name = tax.name.get('en_US', '') if isinstance(tax.name, dict) else str(tax.name)
        tax_name_lower = tax_name.lower()
        if 'gov' in tax_name_lower or 'gubernamental' in tax_name_lower:
            vals['isr_retention_type'] = '07'
        elif pct == 5:
            vals['isr_retention_type'] = '07'  # 5% ISR = Proveedores del Estado
        elif 'fee' in tax_name_lower or 'honorar' in tax_name_lower:
            vals['isr_retention_type'] = '02'
        elif 'rent' in tax_name_lower or 'alquil' in tax_name_lower:
            vals['isr_retention_type'] = '01'
        elif pct == 10:
            vals['isr_retention_type'] = '02'  # 10% default = Honorarios
        elif pct == 27:
            vals['isr_retention_type'] = '03'
        elif pct == 2:
            vals['isr_retention_type'] = '03'
        else:
            vals['isr_retention_type'] = '03'  # Otras Rentas por defecto
        tax.write(vals)
        updated_count += 1
        _logger.info("Updated sale ISR tax by group: %s (%.1f%%) -> %s", tax_name, tax.amount, vals)

    # ITBIS Retenido de ventas: grupo Withholdings/Retenciones con type_tax_use=sale
    wh_group_names = ['Withholdings', 'Retenciones', 'ITBIS -100%', 'ITBIS -30%']
    ritbis_sale_taxes = Tax.search([
        ('tax_group_id.name', 'in', wh_group_names),
        ('type_tax_use', '=', 'sale'),
        ('active', '=', True),
        ('purchase_tax_type', 'in', ['none', False]),
    ])
    for tax in ritbis_sale_taxes:
        tax.write({'purchase_tax_type': 'ritbis'})
        updated_count += 1
        tax_name = tax.name.get('en_US', '') if isinstance(tax.name, dict) else str(tax.name)
        _logger.info("Updated sale RITBIS tax by group: %s -> ritbis", tax_name)

    # ================================================================
    # PARTE 3: Safety net — detectar impuestos de compra sin configurar
    # que tengan grupo ITBIS/ISR/Retenciones
    # ================================================================
    unconfigured_purchase = Tax.search([
        ('type_tax_use', '=', 'purchase'),
        ('active', '=', True),
        ('purchase_tax_type', 'in', ['none', False]),
    ])
    for tax in unconfigured_purchase:
        group_name = tax.tax_group_id.name if tax.tax_group_id else ''
        if isinstance(group_name, dict):
            group_name = group_name.get('en_US', '')
        group_name_lower = group_name.lower()

        vals = {}
        if 'isr' in group_name_lower:
            vals = {'purchase_tax_type': 'isr', 'isr_retention_type': '03'}
        elif group_name_lower in ('withholdings', 'retenciones', 'itbis -100%', 'itbis -30%'):
            vals = {'purchase_tax_type': 'ritbis'}
        elif 'itbis' in group_name_lower and tax.amount < 0:
            vals = {'purchase_tax_type': 'ritbis'}
        elif 'itbis' in group_name_lower and tax.amount >= 0:
            vals = {'purchase_tax_type': 'itbis'}

        if vals:
            tax.write(vals)
            updated_count += 1
            tax_name = tax.name.get('en_US', '') if isinstance(tax.name, dict) else str(tax.name)
            _logger.info("Updated unconfigured purchase tax: %s (group: %s) -> %s", tax_name, group_name, vals)

    _logger.info("=== Configuración DGII completada: %d impuestos actualizados ===", updated_count)

    env['ir.config_parameter'].sudo().set_param(
        'dgii_reports.tax_configuration_applied',
        'post_install_hook_executed'
    )


def post_init_hook(env):
    """
    Hook que se ejecuta después de instalar el módulo.
    Configura automáticamente los purchase_tax_type según especificaciones DGII.
    """
    _configure_taxes_dgii(env)


def uninstall_hook(env):
    """
    Hook que se ejecuta al desinstalar el módulo.
    Limpia parámetros de configuración.
    """
    _logger.info("Cleaning up DGII configuration parameters")
    env['ir.config_parameter'].sudo().search([
        ('key', '=', 'dgii_reports.tax_configuration_applied')
    ]).unlink()
