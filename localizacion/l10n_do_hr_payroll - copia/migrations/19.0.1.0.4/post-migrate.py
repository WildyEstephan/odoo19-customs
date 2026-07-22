# MODIFICADO: Arturo Diaz Lora - 2026-04-13 16:30
# Razón: Mover cuentas contables de BASIC a APAGAR.
#
# Desde 2026-04-04, BASIC muestra el salario mensual completo (contract.wage)
# para visualización en el recibo, mientras que APAGAR tiene el monto real
# del período (quincenal/semanal). Si BASIC tiene cuentas contables, el asiento
# registra el salario mensual completo en vez del monto del período.
#
# Esta migración:
#   1. Copia account_debit/account_credit de BASIC a APAGAR
#   2. Limpia account_debit/account_credit de BASIC
#
# Nota: La corrección de NET (eliminar account_credit) se aplicó en 19.0.1.0.3
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        "Moviendo cuentas contables de BASIC a APAGAR "
        "para corregir asientos de nómina..."
    )

    # Obtener IDs de estructuras dominicanas
    cr.execute("""
        SELECT id FROM hr_payroll_structure
        WHERE country_id = (SELECT id FROM res_country WHERE code = 'DO')
    """)
    struct_ids = [r[0] for r in cr.fetchall()]
    if not struct_ids:
        _logger.info("No se encontraron estructuras dominicanas.")
        return

    # Copiar cuentas de BASIC a APAGAR (solo si APAGAR no tiene cuentas)
    cr.execute("""
        UPDATE hr_salary_rule apagar
        SET account_debit = basic.account_debit,
            account_credit = basic.account_credit
        FROM hr_salary_rule basic
        WHERE basic.code = 'BASIC'
          AND apagar.code = 'APAGAR'
          AND basic.struct_id = apagar.struct_id
          AND basic.struct_id = ANY(%s)
          AND basic.account_debit IS NOT NULL
          AND (apagar.account_debit IS NULL)
    """, (struct_ids,))
    copied = cr.rowcount
    _logger.info("Reglas APAGAR actualizadas con cuentas de BASIC: %s", copied)

    # Limpiar cuentas de BASIC
    cr.execute("""
        UPDATE hr_salary_rule
        SET account_debit = NULL,
            account_credit = NULL
        WHERE code = 'BASIC'
          AND struct_id = ANY(%s)
          AND (account_debit IS NOT NULL OR account_credit IS NOT NULL)
    """, (struct_ids,))
    cleaned = cr.rowcount
    _logger.info("Reglas BASIC limpiadas (cuentas eliminadas): %s", cleaned)
