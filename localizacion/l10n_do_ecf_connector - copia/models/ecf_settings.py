
from odoo import models, fields, api, _
from ..netvux_api import NETVUXApi
from odoo.exceptions import ValidationError
import requests


class ECFSettingsVersion(models.Model):
    _name = 'ecf.settings.version'
    _description = 'Electronic Vouchers Configuration Version'

    name = fields.Char(string='Version', size=3)
    number = fields.Float()

    def _valid_field_parameter(self, field, name):
        return name == 'size' or super(ECFSettingsVersion, self)._valid_field_parameter(field, name)
    resolution = fields.Char()
    publication_date = fields.Char(string='Date of Publication', help='As it comes from the Resolution')
    url = fields.Char(string='Resolution URL')
    active = fields.Boolean(default=True)


class ECFSettings(models.Model):
    _name = 'ecf.settings'
    _description = 'Electronic Vouchers Configuration'
    _check_company_auto = True

    _environment_company_unique = models.Constraint(
        'unique (environment, company_id)',
        'Environment must be unique per company',
    )

    company_id = fields.Many2one('res.company', string='Company', required=True, index=True, default=lambda self: self.env.company)

    @api.model
    def _default_settings_version(self):
        return self.env.ref("l10n_do_ecf_connector.ecf_version_1_0")

    name = fields.Char()
    environment = fields.Selection([
        ('TesteCF', 'Pre-certification'),
        ('eCF', "Production"),
    ], default='TesteCF', required=True)
    ce_version = fields.Many2one('ecf.settings.version', string='Version', ondelete='set null',
                                 default=_default_settings_version)
    user = fields.Char(required=True)
    key = fields.Char(required=True)

    def action_verify(self):
        self.ensure_one()
        netvux_api = NETVUXApi(self)

        try:
            kernel = netvux_api.authentication()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'sticky': False,
                    'message': "%s" % kernel,
                }
            }

        except requests.exceptions.MissingSchema:
            raise ValidationError(_("Wrong external service URL"))

        except requests.exceptions.ConnectionError:
            raise ValidationError(_("Check you connection"))
