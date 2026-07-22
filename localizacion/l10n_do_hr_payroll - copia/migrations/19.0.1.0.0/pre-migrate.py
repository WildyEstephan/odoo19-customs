# -*- coding: utf-8 -*-
"""
Script de migración para l10n_do_hr_payroll de v18 a v19

Cambios principales en Odoo 19:
- hr.contract fue renombrado a hr.version
- Los campos personalizados deben existir en hr_version
- Las vistas heredan de hr.employee en lugar de hr.contract
"""

import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración: Preparar la base de datos antes de actualizar el módulo
    """
    _logger.info("Iniciando pre-migración de l10n_do_hr_payroll a v19.0")

    # 1. Eliminar vistas antiguas que apuntaban a hr.contract
    _logger.info("Eliminando vistas antiguas de hr.contract...")
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE name LIKE 'hr.contract.view.form.inherit.do%'
        AND model = 'hr.contract'
    """)

    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'l10n_do_hr_payroll'
        AND name LIKE 'hr_contract_view_form_inherit%'
    """)

    # 2. Verificar si la tabla hr_version existe (Odoo 19) o hr_contract (Odoo 18)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_version'
        );
    """)
    hr_version_exists = cr.fetchone()[0]

    if hr_version_exists:
        _logger.info("Tabla hr_version encontrada - Odoo 19 detectado")

        # Verificar si los campos personalizados ya existen en hr_version
        cr.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'hr_version'
            AND column_name IN (
                'income_type', 'payrolltype_id', 'deduction_plan',
                'scheduled_retentions', 'is_foreign', 'allow_accumulation',
                'retencion_unico', 'rnc_retencion_unico', 'remuneracion',
                'payment_day', 'hourly_payment', 'wage_extra_hour',
                'dieta_amount', 'wage_extra_labol', 'free_days',
                'wage_holidays_hour', 'fixed_loan', 'amount_saved',
                'comission_rate', 'assurance_amount', 'schedule_form_pay'
            );
        """)
        existing_columns = [row[0] for row in cr.fetchall()]
        _logger.info(f"Columnas existentes en hr_version: {existing_columns}")

        # Si la tabla hr_contract todavía tiene datos, migrarlos
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'hr_contract'
            );
        """)
        hr_contract_exists = cr.fetchone()[0]

        if hr_contract_exists:
            _logger.info("Tabla hr_contract encontrada - intentando migrar datos...")
            # La migración de datos de hr_contract a hr_version la hace Odoo core
            # Solo necesitamos verificar que nuestros campos personalizados se copien
    else:
        _logger.warning("Tabla hr_version NO encontrada - verificar instalación de Odoo 19")

    _logger.info("Pre-migración de l10n_do_hr_payroll completada")
