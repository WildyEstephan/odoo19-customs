# MODIFICADO: Arturo Diaz Lora - 2026-04-13 16:00
# Razón: Eliminar account_credit de la regla NET (Salario Neto).
#
# Problema: La regla NET tenía account_credit apuntando a 21010600 (Nóminas por Pagar)
# sin account_debit. Esto provocaba que al generar el asiento contable:
#   1. NET creaba un crédito aislado a 21010600 por el monto neto
#   2. El sistema detectaba el desequilibrio (débitos < créditos)
#   3. _prepare_adjust_line() creaba un "Asiento de ajuste" debitando la cuenta
#      por defecto del diario (61010100 Sueldos y Salarios)
#   4. Resultado: gasto salarial y pasivo con empleado DUPLICADOS
#
# Solución: NET es un cálculo informativo (BRUTO - Retenciones), no debe tener
# cuentas contables. Las cuentas ya están correctamente afectadas por BASIC
# (gasto + pasivo bruto) y las retenciones (reclasificación del pasivo).
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info(
        "Limpiando account_credit de la regla NET para evitar "
        "doble contabilización del gasto salarial..."
    )

    # Limpiar account_credit y account_debit de TODAS las reglas NET
    # de las estructuras dominicanas (por seguridad, también limpia account_debit)
    cr.execute("""
        UPDATE hr_salary_rule
        SET account_credit = NULL,
            account_debit = NULL
        WHERE code = 'NET'
          AND struct_id IN (
              SELECT id FROM hr_payroll_structure
              WHERE country_id = (SELECT id FROM res_country WHERE code = 'DO')
          )
          AND (account_credit IS NOT NULL OR account_debit IS NOT NULL)
    """)
    updated = cr.rowcount
    _logger.info("Reglas NET corregidas: %s", updated)
