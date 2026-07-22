# MODIFICADO: Arturo Diaz Lora - 2026-04-09 10:00
# Razón: Configurar cuenta predeterminada (61010100) para diario Salarios en todas las compañías.
#        El enfoque XML no funciona porque ir_model_data tiene noupdate=true
#        (establecido por hr_payroll_account al crear el diario).
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Configurando cuenta predeterminada para diarios de Salarios...")
    # Buscar diarios SLR sin cuenta predeterminada y asignarles la cuenta 61010100
    # de su misma compañía, usando el prefijo del XML ID (ej: 1_hr_payroll..., 1_l10n_do_61010100)
    cr.execute("""
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
    updated = cr.rowcount
    _logger.info("Diarios de Salarios actualizados con cuenta 61010100: %s", updated)
