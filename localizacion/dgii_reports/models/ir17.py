from odoo import fields, models, api
import calendar
from datetime import datetime as dt


class DgiiReport(models.Model):
    _inherit = 'dgii.reports'

    # IR17
    # Fields
    ir7_records = fields.Integer(string="Registros", compute="_compute_ir7_fields", )
    ret_rent = fields.Monetary(compute="_compute_ir7_fields", string="Alquileres")
    ret_service_honoraries = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Honorarios por Servicios Independientes"
    )
    ret_award = fields.Monetary(compute="_compute_ir7_fields", string="Premios (Ley 253-17)")
    ret_title_transfer = fields.Monetary(compute="_compute_ir7_fields", string="Transferencia de Titulo y Propiedades")
    ret_dividends = fields.Monetary(compute="_compute_ir7_fields", string="Dividendos (Ley 253-17)")
    ret_legal_person10 = fields.Monetary(
        string="Intereses a personas Juridicas o Entidades no Residentes (Ley 253-12)",
        compute="_compute_ir7_fields",
    )
    ret_legal_person5 = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Juridicas o Entidades no Residentes (Ley 57-2007)"
    )
    ret_physical_person10 = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Fisicas no Residentes (Ley 253-12)"
    )
    ret_physical_person5 = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Fisicas no residentes (Leyes 57-2007 y 253-12)"
    )
    ret_remittances = fields.Monetary(compute="_compute_ir7_fields", string="Remesas al exterior (Ley 253-12)")
    ret_special_remittances = fields.Monetary(compute="_compute_ir7_fields", string="Remesas acuerdos especiales")
    ret_local_supplier = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Pagos a proveedores del estado (Ley 253-12)"
    )
    ret_phone_set = fields.Monetary(string="Juegos Telefónicos (Norma 08-2011)")
    ret_capital_earning = fields.Monetary(string="Ganancia de capital (Norma 07-2011)")
    ret_internet_games = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Juegos via internet (Ley 139-11, art. 7)"
    )
    ret_others_rent10 = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Otras rentas (Ley 11-92, Art. 309 lit. F)"
    )
    ret_others_rent2 = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Otras rentas (Decreto 139-98, Art. 70 Lit. a y b)"
    )
    ret_others_ret = fields.Monetary(compute="_compute_ir7_fields", string="Otras retenciones Norma 07-2007")
    ret_finance_entity_legal = fields.Monetary(
        string="Intereses pagados por entidades financieras a personas juridicas (norma 13-2011)"
    )
    ret_finance_entity_physical = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses pagados por entidades financieras a personas fisicas (Ley 253-12)"
    )
    
    ret_total = fields.Monetary(compute="_compute_ir7_fields", string="Total otras retenciones")

    ret_rent_base = fields.Monetary(compute="_compute_ir7_fields", string="Alquileres base")
    ret_service_honoraries_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Honorarios por Servicios Independientes base"
    )
    ret_award_base = fields.Monetary(compute="_compute_ir7_fields", string="Premios (Ley 253-17) base")
    ret_title_transfer_base = fields.Monetary(compute="_compute_ir7_fields", string="Transferencia de Titulo y Propiedades base")
    ret_dividends_base = fields.Monetary(compute="_compute_ir7_fields", string="Dividendos (Ley 253-17) base")
    ret_legal_person10_base = fields.Monetary(
        string="Intereses a personas Juridicas o Entidades no Residentes (Ley 253-12) base",
        compute="_compute_ir7_fields",
    )
    ret_legal_person5_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Juridicas o Entidades no Residentes (Ley 57-2007) base"
    )
    ret_physical_person10_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Fisicas no Residentes (Ley 253-12) base"
    )
    ret_physical_person5_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses a personas Fisicas no residentes (Leyes 57-2007 y 253-12) base"
    )
    ret_remittances_base = fields.Monetary(compute="_compute_ir7_fields", string="Remesas al exterior (Ley 253-12) base")
    ret_special_remittances_base = fields.Monetary(compute="_compute_ir7_fields", string="Remesas acuerdos especiales base")
    ret_local_supplier_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Pagos a proveedores del estado (Ley 253-12) base"
    )
    ret_phone_set_base = fields.Monetary(string="Juegos Telefónicos (Norma 08-2011) base")
    ret_capital_earning_base = fields.Monetary(string="Ganancia de capital (Norma 07-2011) base")
    ret_internet_games_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Juegos via internet (Ley 139-11, art. 7) base"
    )
    ret_others_rent10_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Otras rentas (Ley 11-92, Art. 309 lit. F) base"
    )
    ret_others_rent2_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Otras rentas (Decreto 139-98, Art. 70 Lit. a y b) base"
    )
    ret_others_ret_base = fields.Monetary(compute="_compute_ir7_fields", string="Otras retenciones Norma 07-2007 base")
    ret_finance_entity_legal_base = fields.Monetary(
        string="Intereses pagados por entidades financieras a personas juridicas (norma 13-2011) base"
    )
    
    ret_finance_entity_physical_base = fields.Monetary(
        compute="_compute_ir7_fields",
        string="Intereses pagados por entidades financieras a personas fisicas (Ley 253-12) base"
    )
    
    ret_total_base = fields.Monetary(compute="_compute_ir7_fields", string="Total otras retenciones base")

    def _compute_ir7_fields(self):
        for rec in self:
            data = {
                'ir7_records': 0,
                'ret_rent': 0,
                'ret_service_honoraries': 0,
                'ret_award': 0,
                'ret_title_transfer': 0,
                'ret_dividends': 0,
                'ret_legal_person10': 0,
                'ret_legal_person5': 0,
                'ret_physical_person10': 0,
                'ret_physical_person5': 0,
                'ret_remittances': 0,
                'ret_special_remittances': 0,
                'ret_local_supplier': 0,
                'ret_phone_set': 0,
                'ret_capital_earning': 0,
                'ret_internet_games': 0,
                'ret_others_rent10': 0,
                'ret_others_rent2': 0,
                'ret_others_ret': 0,
                'ret_finance_entity_legal': 0,
                'ret_total': 0,
                'ret_finance_entity_physical' : 0,
            }

            data_base = {
                'ret_rent_base': 0,
                'ret_service_honoraries_base': 0,
                'ret_award_base': 0,
                'ret_title_transfer_base': 0,
                'ret_dividends_base': 0,
                'ret_legal_person10_base': 0,
                'ret_legal_person5_base': 0,
                'ret_physical_person10_base': 0,
                'ret_physical_person5_base': 0,
                'ret_remittances_base': 0,
                'ret_special_remittances_base': 0,
                'ret_local_supplier_base': 0,
                'ret_phone_set_base': 0,
                'ret_capital_earning_base': 0,
                'ret_internet_games_base': 0,
                'ret_others_rent10_base': 0,
                'ret_others_rent2_base': 0,
                'ret_others_ret_base': 0,
                'ret_finance_entity_legal_base': 0,
                'ret_total_base': 0,
                'ret_finance_entity_physical_base' : 0,
            }
            ir7_line_ids = self.env["dgii.reports.ir17.line"].search([("dgii_report_id", "=", rec.id)])
            for inv in ir7_line_ids:
                data["ir7_records"] += 1
                if inv.tax_type:
                    data[inv.tax_type] += inv.taxed_amount
                    data['ret_total'] += inv.taxed_amount
                    data_base[str(inv.tax_type)+"_base"] += inv.base_amount
                    data_base['ret_total_base'] += inv.base_amount
                    
            rec.ret_rent = abs(data['ret_rent'])
            rec.ret_service_honoraries = abs(data['ret_service_honoraries'])
            rec.ret_award = abs(data['ret_award'])
            rec.ret_title_transfer = abs(data['ret_title_transfer'])
            rec.ret_dividends = abs(data['ret_dividends'])
            rec.ret_legal_person10 = abs(data['ret_legal_person10'])
            rec.ret_legal_person5 = abs(data['ret_legal_person5'])
            rec.ret_physical_person10 = abs(data['ret_physical_person10'])
            rec.ret_physical_person5 = abs(data['ret_physical_person5'])
            rec.ret_remittances = abs(data['ret_remittances'])
            rec.ret_special_remittances = abs(data['ret_special_remittances'])
            rec.ret_local_supplier = abs(data['ret_local_supplier'])
            rec.ret_phone_set = abs(data['ret_phone_set'])
            rec.ret_capital_earning = abs(data['ret_capital_earning'])
            rec.ret_internet_games = abs(data['ret_internet_games'])
            rec.ret_others_rent10 = abs(data['ret_others_rent10'])
            rec.ret_others_rent2 = abs(data['ret_others_rent2'])
            rec.ret_others_ret = abs(data['ret_others_ret'])
            rec.ret_finance_entity_legal = abs(data['ret_finance_entity_legal'])
            rec.ret_finance_entity_physical = abs(data['ret_finance_entity_physical'])
            rec.ret_total = abs(data['ret_total'])
           
            rec.ret_rent_base = abs(data_base['ret_rent_base'])
            rec.ret_service_honoraries_base = abs(data_base['ret_service_honoraries_base'])
            rec.ret_award_base = abs(data_base['ret_award_base'])
            rec.ret_title_transfer_base = abs(data_base['ret_title_transfer_base'])
            rec.ret_dividends_base = abs(data_base['ret_dividends_base'])
            rec.ret_legal_person10_base = abs(data_base['ret_legal_person10_base'])
            rec.ret_legal_person5_base = abs(data_base['ret_legal_person5_base'])
            rec.ret_physical_person10_base = abs(data_base['ret_physical_person10_base'])
            rec.ret_physical_person5_base = abs(data_base['ret_physical_person5_base'])
            rec.ret_remittances_base = abs(data_base['ret_remittances_base'])
            rec.ret_special_remittances_base = abs(data_base['ret_special_remittances_base'])
            rec.ret_local_supplier_base = abs(data_base['ret_local_supplier_base'])
            rec.ret_phone_set_base = abs(data_base['ret_phone_set_base'])
            rec.ret_capital_earning_base = abs(data_base['ret_capital_earning_base'])
            rec.ret_internet_games_base = abs(data_base['ret_internet_games_base'])
            rec.ret_others_rent10_base = abs(data_base['ret_others_rent10_base'])
            rec.ret_others_rent2_base = abs(data_base['ret_others_rent2_base'])
            rec.ret_others_ret_base = abs(data_base['ret_others_ret_base'])
            rec.ret_finance_entity_legal_base = abs(data_base['ret_finance_entity_legal_base'])
            rec.ret_finance_entity_physical_base = abs(data_base['ret_finance_entity_physical_base'])
            rec.ret_total_base = abs(data_base['ret_total_base'])
            rec.ir7_records = abs(data['ir7_records'])

    def _get_pending_invoices_ir17(self, types):
        period = dt.strptime(self.name, "%m/%Y")

        month, year = self.name.split("/")
        start_date = "{}-{}-{}".format(
            year, month, calendar.monthrange(int(year), int(month))[1]
        )
        invoice_ids = (
            self.env["account.move"]
            .search(
                [
                    ("payment_state", "in", ['paid', 'in_payment']),
                    ("payment_date", "<=", start_date),
                    ("company_id", "=", self.company_id.id),
                    ("move_type", "in", types),
                ]
            )
            .filtered(
                lambda inv: self.get_date_tuple(inv.payment_date)
                == (period.year, period.month)
            )
        )

        return invoice_ids

    def _get_move_ir17(self, states, types):
        """
        Given rec and state, return a recordset of invoices
        :param state: a list of invoice state
        :param type: a list of invoice type
        :return: filtered invoices
        """
        month, year = self.name.split("/")
        last_day = calendar.monthrange(int(year), int(month))[1]
        start_date = "{}-{}-01".format(year, month)
        end_date = "{}-{}-{}".format(year, month, last_day)

        invoice_ids = self.env["account.move"].search(
            [
                ("invoice_date", ">=", start_date),
                ("invoice_date", "<=", end_date),
                ("company_id", "=", self.company_id.id),
                ("state", "=", states),
                ("move_type", "in", types),
            ],
            order="invoice_date asc",
        )
        invoice_ids |= self._get_pending_invoices_ir17(types)

        return invoice_ids

    def _get_ir17_type(self, line, type_isr, tax_amount):
        if type_isr == '01' and tax_amount == 10:
            return 'ret_rent'

        elif type_isr == '02' and tax_amount == 10:
            return 'ret_service_honoraries'

        elif type_isr == '02' and tax_amount == 10:
            return 'ret_service_honoraries'

        elif line.account_id.is_dividend and tax_amount == 10:
            return 'ret_dividends'

        elif type_isr == '05' and tax_amount == 10:
            return 'ret_legal_person10'

        elif type_isr == '05' and tax_amount == 5:
            return 'ret_legal_person5'

        elif type_isr == '06' and tax_amount == 10:
            return 'ret_physical_person10'

        elif type_isr == '06' and tax_amount == 5:
            return 'ret_physical_person5'

        elif type_isr == '07' and tax_amount == 5:
            return 'ret_local_supplier'

        elif type_isr == '08' and tax_amount == 5:
            return 'ret_phone_set'

        elif type_isr == '03' and tax_amount == 1:
            return 'ret_others_rent10'

        elif type_isr == '03' and tax_amount == 2:
            return 'ret_others_ret'

        elif type_isr == '04' and (tax_amount == 2.7 or tax_amount == 27):
            return 'ret_remittances'

    @api.model
    def _compute_ir17_data(self):
        for rec in self:
            invoice_ids = self._get_move_ir17(['posted'], ['in_invoice', 'in_refund'])
            IR17_Line = self.env["dgii.reports.ir17.line"]
            IR17_Line.search([("dgii_report_id", "=", rec.id)]).unlink()
            line_count = 0
            for inv in invoice_ids:
                
                for line in inv.line_ids.filtered(
                    lambda x: x.account_id.account_fiscal_type == 'ISR'
                ):
                    type_line = self._get_ir17_type(
                        line,
                        line.account_id.isr_retention_type,
                        abs(line.tax_line_id.amount),
                    )
                    if not type_line:
                        continue
                    show_payment_date = self._include_in_current_report(inv)
                    values = {
                        "dgii_report_id": rec.id,
                        "line": line_count,
                        "base_amount": line.tax_base_amount,
                        "taxed_amount": abs(line.amount_currency),
                        "tax_porcent": abs(line.tax_line_id.amount),
                        "invoice_date": inv.invoice_date,
                        "invoice_paid": inv.payment_date if show_payment_date else False,
                        "tax_type": type_line,
                        "invoice_partner_id": inv.partner_id.id,
                        "invoice_id": inv.id,
                    }
                    line_count += 1
                    values.update({"line": line_count})
                    IR17_Line.create(values)
            month, year = rec.name.split('/')
            last_day = calendar.monthrange(int(year), int(month))[1]
            start_date = '{}-{}-01'.format(year, month)
            end_date = '{}-{}-{}'.format(year, month, last_day)
            move_ids = self.env['account.move'].search(
                [
                    ('date', '>=', start_date),
                    ('date', '<=', end_date),
                    ('company_id', '=', rec.company_id.id),
                    ('state', '=', 'posted'),
                    ('move_type', '=', 'entry'),
                ],
                order='date asc',
            )
            
            line_count = 0
            for m in move_ids:
                for line in m.line_ids.filtered(
                    lambda l: l.account_id.account_fiscal_type == 'ISR'
                    and l.account_id.is_dividend
                ):
                    values = {
                        "dgii_report_id": rec.id,
                        "line": line_count,
                        "base_amount": line.amount_currency,
                        "taxed_amount": abs(line.amount_currency) / 10,
                        "tax_porcent": 10,
                        "invoice_date": m.date,
                        "tax_type": 'ret_dividends',
                        "invoice_partner_id": m.partner_id.id,
                        "invoice_id": m.id,
                    }
                    
                    line_count += 1
                    values.update({"line": line_count})
                    IR17_Line.create(values)

    @api.model
    def _generate_report(self):
        self._compute_ir17_data()
        return super(DgiiReport, self)._generate_report()
    
    def get_ir17_tree_view(self):
        return {
            "name": "IR17",
            "view_mode": "list",
            "res_model": "dgii.reports.ir17.line",
            "type": "ir.actions.act_window",
            "view_id": self.env.ref("dgii_reports.dgii_reports_ir17_line_tree").id,
            "domain": [("dgii_report_id", "=", self.id)],
        }   


class DgiiCancelReportLine(models.Model):
    _name = "dgii.reports.ir17.line"
    _description = "DGII Reports IR17 Line"

    dgii_report_id = fields.Many2one("dgii.reports", ondelete="cascade")
    company_id = fields.Many2one('res.company', related='dgii_report_id.company_id', store=True, index=True)
    line = fields.Integer("No.")
    base_amount = fields.Float("Base Imponible")
    taxed_amount = fields.Float("Impuesto")
    tax_porcent = fields.Float("Tasa%")
    invoice_date = fields.Date("Fecha")
    invoice_paid = fields.Date("Fecha de Pago")
    tax_type = fields.Selection(
        string='Tipo de Retencion',
        selection=[
            ('ret_rent', 'Alquileres'),
            ('ret_service_honoraries', 'Honorarios por Servicios Independientes'),
            ('ret_award', 'Premios (Ley 253-17)'),
            ('ret_title_transfer', 'Transferencia de Titulo y Propiedades'),
            ('ret_dividends', 'Dividendos (Ley 253-17)'),
            (
                'ret_legal_person10',
                'Intereses a Personas Jurídicas o Entidades no Residentes (Ley 253-12)',
            ),
            (
                'ret_legal_person5',
                'Intereses a Personas Jurídicas o Entidades no Residentes (Ley 57-2007)',
            ),
            (
                'ret_physical_person10',
                'Intereses a Personas Físicas no Residentes (Ley 253-12)',
            ),
            (
                'ret_physical_person5',
                'Intereses a Personas Físicas no Residentes (Leyes 57-2007 y 253-12)',
            ),
            ('ret_remittances', 'Remesas al Exterior (Ley 253-12)'),
            ('ret_special_remittances', 'Remesas Acuerdos Especiales'),
            ('ret_local_supplier', 'Pagos a Proveedores del Estado (Ley 253-12)'),
            ('ret_phone_set', 'Juegos Telefónicos (Norma 08-2011)'),
            ('ret_capital_earning', 'Ganancia de Capital (Norma 07-2011)'),
            ('ret_internet_games', 'Juegos Via Internet (Ley 139-11, art. 7)'),
            ('ret_others_rent10', 'Otras Rentas (Ley 11-92, Art. 309 lit. F)'),
            (
                'ret_others_rent2',
                'Otras Rentas (Decreto 139-98, Art. 70 Lit. A y B)',
            ),
            ('ret_others_ret', 'Otras Retenciones Norma 07-2007'),
            (
                'ret_finance_entity_legal',
                'Intereses Pagados por Entidades Financieras a Personas Jurídicas (Norma 13-2011)',
            ),
            (
                'ret_finance_entity_physical',
                'Intereses Pagados por Entidades Financieras a Personas Físicas (Ley 253-12)',
            ),
        ],
    )
    invoice_partner_id = fields.Many2one("res.partner", string="Contacto")
    invoice_partner_id_vat = fields.Char(
        string='RNC/CEDULA',
        related='invoice_partner_id.vat',
    )

    invoice_id = fields.Many2one("account.move", string="Asiento") 