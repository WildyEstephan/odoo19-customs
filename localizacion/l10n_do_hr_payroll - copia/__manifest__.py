# -*- encoding: utf-8 -*-
# © 2019 Jeffry Jesus De La Rosa <jeffryjesus@gmail.com>
# This file is part of Dominincan Republic - HR Payroll

# Dominincan Republic - HR Payroll is free software: you can redistribute
# it and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.

# Dominincan Republic - HR Payroll is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Dominincan Republic - HR Payroll.  If not,
# see <https://www.gnu.org/licenses/>.

{
    "name": "Dominincan Republic - HR Payroll",
    "summary": u"""
          This Module Will Add Rules, Category and all needed to 
          the Dominican Republic Payroll.
      """,
    "category": "Localization",
    "author": u"""Jeffry Jesus De La Rosa""",
    "depends": ["l10n_do", "l10n_do_accounting", "hr_payroll", "hr_payroll_account", "contacts", "hr_attendance", 'hr_holidays', "sh_message", "hr_work_entry"],
    "license": "GPL-3",
    # MODIFICADO: Arturo Diaz Lora - 2026-04-09 11:00
    # Razón: Agregar _configure_payroll_account_do para configuración automática
    #        del diario Salarios en nuevas compañías
    # MODIFICADO: Arturo Diaz Lora - 2026-04-13 16:30
    # Razón: Corregir asientos contables de nómina:
    #   1. Eliminar account_credit de NET (doble contabilización)
    #   2. Mover cuentas de BASIC a APAGAR (BASIC=mensual, APAGAR=período)
    "version": "19.0.1.0.4",
    "description": """
Dominincan Republic - HR Payroll.
=================================

    This Module Will Add:
    - Categories Rules.
    - Structure Rule
    - Salaries Rules.
    - Calculations.
    - Family Dependencies.
    - TSS Reports    
    """,
    "active": True,
    # Modificado por: Arturo Diaz Lora
    # Fecha: 2024-11-26 14:50:00 UTC
    # Razón: Se agregó l10n_do_hr_payroll_journal_config.xml para configurar el diario de nómina
    #        Esta configuración fue movida desde l10n_do_accounting porque el diario solo existe
    #        cuando hr_payroll está instalado.
    # MODIFICADO: Arturo Diaz Lora - 2026-04-03
    # Razón: Agregar post_init_hook para corregir traducciones de estados
    "post_init_hook": "post_init_hook",
    "data": [
        "views/hr_employee_views.xml",
        'security/ir.model.access.csv',
        # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
        # Razón: Agregar reglas multi-company para modelos de nómina
        'security/ir_rule.xml',
        "report/hr_payroll_report.xml",
        # MODIFICADO: Arturo Diaz Lora - 2026-04-03
        # Razón: Restaurar configuración del diario de Salarios con cuenta predeterminada
        "data/l10n_do_hr_payroll_journal_config.xml",
        "data/l10n_do_hr_payroll_structure_labor.xml",
        "data/l10n_do_hr_payroll_rules_categories.xml",
        "data/l10n_do_hr_payroll_salary_rules.xml",
        
        "data/l10n_do_hr_payroll_rule_input.xml",
        "data/l10n_do_hr_payroll_payslip_config_data.xml",
        "data/l10n_do_hr_payroll_payrolltype.xml",
        'data/l10n_do_hr_payroll_rates.xml',
        # Mail Templates
        "data/mail_template_data.xml",
        # Sequence
        "data/sequence.xml",
        "views/payslip_config_view.xml",
        "views/hr_contract_view.xml",
       # "views/hr_salary_rule_view.xml",
        'views/hr_payroll_structure_type_views.xml',
        'views/hr_payslip_run_view.xml',
         'views/working_hours_import_views.xml',
          'views/hr_employee_loan_views.xml',
          'views/hr_payslip_view.xml',
          'views/discount_import_views.xml',

    ],
    'external_dependencies': {
      'python': ['xlsxwriter', 'numpy', 'python-dateutil', 'numpy-financial']
    },
    "installable": True,
    "auto_install": False,
}
