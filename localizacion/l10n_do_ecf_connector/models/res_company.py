from odoo import models, fields, api, _
from werkzeug import urls
from odoo.exceptions import UserError, RedirectWarning, ValidationError
import base64
from lxml import etree
from ..netvux_api import NETVUXApi

parser = etree.XMLParser(remove_blank_text=True)


class ResCompany(models.Model):
    _inherit = 'res.company'

    commercial_name = fields.Char("Commercial Name")
    ecf_config = fields.Many2one('ecf.settings', string='Electronic Voucher Setting', check_company=True)

    @api.constrains("ecf_config")
    def _check_ecf_service_env(self):
        """
        Checks ECF environment consistency. Once an ECF is issued to one environment,
        a distinct one can't be used.
        """
        for company in self:
            signed_invoice = self.env["ecf.document"].search(
                [
                    ("l10n_do_electronic_stamp", "!=", False),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if not signed_invoice:
                continue

            company_service_env = self.ecf_config and self.ecf_config.environment
            current_service_env = urls.url_unquote(
                signed_invoice.l10n_do_electronic_stamp
            ).split("/")[3]

            if current_service_env == 'eCF' and current_service_env != company_service_env:
                raise ValidationError(
                    _(
                        "You cannot change company ECF Environment since there "
                        "are invoices sent to %s" % current_service_env
                    )
                )
