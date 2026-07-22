# MODIFICADO: Arturo Diaz Lora - 2026-04-09 11:00
# Razón: Crear _configure_payroll_account_do para configurar automáticamente
#        la cuenta predeterminada del diario Salarios y las cuentas contables
#        de las reglas salariales al crear nuevas compañías.
#        Sin este método, el diario SLR se creaba sin default_account_id,
#        causando "Operación no válida" al confirmar nóminas.
from collections import defaultdict

from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _configure_payroll_account_do(self, companies):
        account_codes = [
            '11030202',  # Anticipos a Empleados
            '11030205',  # Otros Anticipos
            '21010600',  # Nóminas por Pagar
            '21021000',  # Retenciones ISR Empleados
            '21021100',  # Retenciones TSS Empleados
            '21030401',  # SFS Patronal
            '21030402',  # AFP Patronal
            '21030403',  # SRL Patronal
            '61010100',  # Sueldos y Salarios
            '61010102',  # SFS Empleado
            '61010103',  # AFP Empleado
            '61010104',  # SRL Empleado
            '61010200',  # Horas Extras
            '61010205',  # Contribuciones Patronales TSS
            '61010400',  # Regalía Pascual
            '61010500',  # Bonificaciones
            '61010600',  # Comisiones
            '61010900',  # Prestaciones Laborales
            '61011100',  # Otros Beneficios Empleados
            '61011200',  # Incentivos
            '61011300',  # Beneficios Sociales
            '61011500',  # Dietas y Gastos de Representación
        ]
        default_account = '61010100'
        rules_mapping = defaultdict(dict)

        self._configure_payroll_account(
            companies,
            "DO",
            account_codes=account_codes,
            rules_mapping=rules_mapping,
            default_account=default_account,
        )
