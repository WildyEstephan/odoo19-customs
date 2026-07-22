from odoo import models, fields
from odoo.tools.translate import _
from odoo.exceptions import UserError, ValidationError


class CheckReportConfig(models.Model):
    _name = "check.report.config"
    _description = "Check Report Configuration"

    # ########## Configuración General #######
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, default=lambda self: self.env.company)
    name = fields.Char("Nombre", required=True)
    cheque_image = fields.Binary("Imagen")
    cheque_attribute_line_ids = fields.One2many("bank.cheque.attribute.line",
                                                "bank_cheque_id",
                                                "Atributos")
    cheque_height = fields.Float(string='Altura',
                                 default=93,
                                 required=True)
    cheque_width = fields.Float(string='Ancho',
                                default=203,
                                required=True)
    max_char_in_line1 = fields.Integer(
        "Maximo de Letras",
        help="Maximum characters in 'Amount in words Line1' field.\n Aplicable if Cheque attributes has both attributes(Amount In words Line1 & Amount In words Line2)"
    )
    cheque_measure_unit = fields.Selection([("cm", "CM"),
                                            ("in", "Pulgadas"),
                                            ("mm", "MM")],
                                           "Unidad de Medidas",
                                           default="mm",
                                           required=True)
    
    def redirect_to_bank_cheque_page(self):
        self.ensure_one()
        if not self.cheque_attribute_line_ids:
            raise UserError(
                _('First you have to set bank cheque attributes. '
                  'Then you will be able to configure attribute(s) values'))
        return {
            'type': 'ir.actions.act_url',
            'target': '_blank',
            'url': "/astra/bank/cheque/%s" % self.id,
        }