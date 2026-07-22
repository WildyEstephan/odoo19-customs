# -*- coding: utf-8 -*-
"""
Script de migración para eliminar vista vieja de hr.contract
y forzar recreación sin campos ocultos
"""

def migrate(cr, version):
    """
    Elimina la vista vieja de hr.contract para forzar recreación
    desde el archivo XML actualizado sin los campos ocultos
    """
    # Eliminar vista vieja si existe
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE name IN ('hr.contract.view.form.inherit.do', 'hr.contract.view.form.inherit.do.v2')
        AND model = 'hr.contract'
    """)

    # Eliminar referencias en ir_model_data
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'l10n_do_hr_payroll'
        AND name IN ('hr_contract_view_form_inherit_do', 'hr_contract_view_form_inherit_do_v2')
    """)
