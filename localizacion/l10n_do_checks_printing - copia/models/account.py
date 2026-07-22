from odoo import api, models, fields


class AccountJournal(models.Model):
    _inherit = "account.journal"

    check_layout = fields.Many2one(
        comodel_name="check.report.config",
        string="Plantilla de cheque",
        required=False,
        help="Seleccione el formato que corresponde al papel en el que va a"
        " imprimir sus cheques en.\n Para desactivar la función de impresión,"
        " seleccione 'Ninguno'.",
    )
