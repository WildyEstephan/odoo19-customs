
from odoo import api, fields, models
from datetime import date


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_do_country_code = fields.Char(
        string="DO Country Code",
        compute="_compute_l10n_do_country_code",
        store=True,
    )

    @api.depends('country_id')
    def _compute_l10n_do_country_code(self):
        for company in self:
            company.l10n_do_country_code = company.country_id.code if company.country_id else False

    l10n_do_dgii_start_date = fields.Date("Activities Start Date")

    l10n_do_default_client = fields.Selection(
        selection=[("non_payer", "Final Consumer"), ("taxpayer", "Fiscal Consumer")],
        default=lambda self: self.env.context.get("l10n_do_default_client", "taxpayer"),
        string="Default Customer",
    )
    l10n_do_ecf_issuer = fields.Boolean(
        "Is e-CF issuer",
        help="When activating this field, NCF issuance is disabled.",
    )
    l10n_do_ecf_deferred_submissions = fields.Boolean(
        "Deferred submissions",
        help="Identify taxpayers who have been previously authorized "
        "to have sales through offline mobile devices such as "
        "sales with Handheld, enter others.",
    )
    
    # Define la fecha de vencimiento del NCF para el año en curso
    l10n_do_ncf_exp_date = fields.Date(
        string="NCF Expiration date",
        default=lambda self: date.today().replace(month=12, day=31),
    )

    # MODIFICADO: Arturo Diaz Lora - 2026-02-22
    # Razón: Campo para ocultar información de la compañía en el encabezado de facturas
    # Oculta RNC, dirección, teléfono, email del encabezado derecho de facturas dominicanas
    l10n_do_hide_company_header = fields.Boolean(
        string="Ocultar Info Compañía en Encabezado",
        default=False,
        help="Si está activo, oculta la información de la compañía (RNC, dirección, teléfono, email) "
             "en el encabezado derecho de las facturas dominicanas, mostrando solo el logo."
    )

    def _localization_use_documents(self):
        """ Dominican localization uses documents """
        self.ensure_one()
        
        return (
            True
            if self.country_id == self.env.ref("base.do")
            else False
        )
