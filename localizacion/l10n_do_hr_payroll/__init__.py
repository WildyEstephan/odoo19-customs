# -*- encoding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution Panama Payroll
#
#    Copyright (c) 2017
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from . import model
from . import report
from . import wizard


# MODIFICADO: Arturo Diaz Lora - 2026-04-03
# Razón: Corregir traducción duplicada "Listo" para estados del lote de nómina
def _fix_payslip_run_state_translations(env):
    """
    Corrige las traducciones de los estados del lote de nómina.
    En es_419.po, tanto 'Ready' como 'Done' estaban traducidos como 'Listo'.
    Esta función corrige 'Done' a 'Hecho'.
    """
    env.cr.execute("""
        UPDATE ir_model_fields_selection
        SET name = jsonb_set(name, '{es_DO}', '"Hecho"')
        WHERE name->>'en_US' = 'Done'
          AND id IN (
              SELECT imfs.id
              FROM ir_model_fields_selection imfs
              JOIN ir_model_fields imf ON imfs.field_id = imf.id
              WHERE imf.model = 'hr.payslip.run' AND imf.name = 'state'
          );
    """)


def _configure_salary_journal_default_account(env):
    """
    Configura la cuenta predeterminada (61010100 - Sueldos y Salarios)
    para el diario de Salarios en todas las compañías.

    El diario es creado por hr_payroll_account con noupdate=true,
    por lo que no se puede configurar vía XML desde otro módulo.
    """
    # MODIFICADO: Arturo Diaz Lora - 2026-04-09 10:00
    # Razón: Usar Python en lugar de XML para configurar la cuenta predeterminada
    #        del diario Salarios, ya que noupdate=true impide la actualización vía XML
    env.cr.execute("""
        UPDATE account_journal aj
        SET default_account_id = sub.account_id
        FROM (
            SELECT
                imd_j.res_id AS journal_id,
                imd_a.res_id AS account_id
            FROM ir_model_data imd_j
            JOIN ir_model_data imd_a
                ON imd_a.module = 'account'
                AND imd_a.model = 'account.account'
                AND SUBSTRING(imd_a.name FROM '^([0-9]+)_') = SUBSTRING(imd_j.name FROM '^([0-9]+)_')
                AND imd_a.name LIKE '%%l10n_do_61010100'
            WHERE imd_j.module = 'account'
                AND imd_j.model = 'account.journal'
                AND imd_j.name LIKE '%%hr_payroll_account_journal'
        ) sub
        WHERE aj.id = sub.journal_id
            AND aj.default_account_id IS NULL
    """)


def post_init_hook(env):
    _fix_payslip_run_state_translations(env)
    _configure_salary_journal_default_account(env)
