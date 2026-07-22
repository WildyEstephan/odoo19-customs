# Part of Domincana Premium.
# See LICENSE file for full copyright and licensing details.
# MODIFICADO: Arturo Diaz Lora - 2026-03-24 12:00
# Razón: Tests para validar reportes DGII 606/607

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDgiiReports(TransactionCase):
    """Tests para validar la generación de reportes DGII 606 y 607."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Partner con RNC (9 dígitos)
        cls.partner_rnc = cls.env['res.partner'].create({
            'name': 'Proveedor Formal SA',
            'vat': '101234567',
            'l10n_do_dgii_tax_payer_type': 'taxpayer',
            'country_id': cls.env.ref('base.do').id,
        })

        # Partner con Cédula (11 dígitos) - persona física
        cls.partner_cedula = cls.env['res.partner'].create({
            'name': 'Juan Pérez',
            'vat': '00112345678',
            'l10n_do_dgii_tax_payer_type': 'non_payer',
            'country_id': cls.env.ref('base.do').id,
        })

        # Partner sin VAT (proveedor informal)
        cls.partner_informal = cls.env['res.partner'].create({
            'name': 'Proveedor Informal',
            'country_id': cls.env.ref('base.do').id,
        })

        # Cliente gubernamental
        cls.partner_gov = cls.env['res.partner'].create({
            'name': 'Entidad Gubernamental',
            'vat': '401234567',
            'l10n_do_dgii_tax_payer_type': 'governmental',
            'country_id': cls.env.ref('base.do').id,
        })

        # Buscar diarios
        cls.purchase_journal = cls.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

        cls.sale_journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

        # Buscar impuestos configurados
        cls.itbis_purchase = cls.env['account.tax'].search([
            ('purchase_tax_type', '=', 'itbis'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ], limit=1)

        cls.ritbis_purchase = cls.env['account.tax'].search([
            ('purchase_tax_type', '=', 'ritbis'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ], limit=1)

        cls.isr_purchase = cls.env['account.tax'].search([
            ('purchase_tax_type', '=', 'isr'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ], limit=1)

        cls.itbis_sale = cls.env['account.tax'].search([
            ('purchase_tax_type', '=', 'itbis'),
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
        ], limit=1) or cls.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
            ('amount', '=', 18),
        ], limit=1)

    def _create_dgii_report(self, period='03/2026'):
        """Helper para crear un reporte DGII."""
        return self.env['dgii.reports'].create({
            'name': period,
            'company_id': self.company.id,
        })

    # =========================================
    # Tests de formateo y utilidades
    # =========================================

    def test_formated_rnc_cedula_rnc(self):
        """Test formateo de RNC (9 dígitos)."""
        report = self._create_dgii_report()
        result = report.formated_rnc_cedula('101234567')
        self.assertEqual(result, ('101234567', 1))

    def test_formated_rnc_cedula_cedula(self):
        """Test formateo de Cédula (11 dígitos)."""
        report = self._create_dgii_report()
        result = report.formated_rnc_cedula('00112345678')
        self.assertEqual(result, ('00112345678', 2))

    def test_formated_rnc_cedula_invalid(self):
        """Test RNC/Cédula inválido retorna False."""
        report = self._create_dgii_report()
        self.assertFalse(report.formated_rnc_cedula('12345'))
        self.assertFalse(report.formated_rnc_cedula(None))
        self.assertFalse(report.formated_rnc_cedula(''))

    def test_get_formated_amount(self):
        """Test formateo de montos."""
        report = self._create_dgii_report()
        self.assertEqual(report._get_formated_amount(1234.56), '1234.56')
        self.assertEqual(report._get_formated_amount(-500.00), '500.00')
        self.assertEqual(report._get_formated_amount(0), '0.00')

    def test_get_formated_date(self):
        """Test formateo de fechas."""
        report = self._create_dgii_report()
        from datetime import date
        self.assertEqual(report._get_formated_date(date(2026, 3, 15)), '20260315')
        self.assertEqual(report._get_formated_date(None), '')

    def test_clean_spaces(self):
        """Test que _clean_spaces hace strip por campo, no elimina todos los espacios."""
        report = self._create_dgii_report()
        data = "  ABC  |  123.45  |  DEF  "
        result = report._clean_spaces(data)
        self.assertEqual(result, "ABC|123.45|DEF")

    # =========================================
    # Tests de detección de factura de consumo
    # =========================================

    def test_is_consumer_invoice_b02(self):
        """Test detección de factura consumo B02."""
        report = self._create_dgii_report()
        self.assertTrue(report._is_consumer_invoice('B0200000001'))

    def test_is_consumer_invoice_e32(self):
        """Test detección de factura consumo E32."""
        report = self._create_dgii_report()
        self.assertTrue(report._is_consumer_invoice('E320000000001'))

    def test_is_not_consumer_invoice_b01(self):
        """Test que B01 no es factura de consumo."""
        report = self._create_dgii_report()
        self.assertFalse(report._is_consumer_invoice('B0100000001'))

    # =========================================
    # Tests de formato TXT 606
    # =========================================

    def test_process_606_no_empty_fields(self):
        """Test que el formato 606 no tiene campos vacíos donde se esperan números."""
        report = self._create_dgii_report()
        values = {
            'rnc_cedula': '101234567',
            'identification_type': 1,
            'expense_type': '02',
            'fiscal_invoice_number': 'B1100000001',
            'modified_invoice_number': '',
            'invoice_date': '2026-03-15',
            'payment_date': '2026-03-20',
            'service_total_amount': 85891.53,
            'good_total_amount': 0,
            'invoiced_amount': 85891.53,
            'invoiced_itbis': 15460.47,
            'withholded_itbis': 15460.47,
            'proportionality_tax': 0,
            'cost_itbis': 0,
            'advance_itbis': 15460.47,
            'purchase_perceived_itbis': 0,
            'isr_withholding_type': '02',
            'income_withholding': 8589.15,
            'purchase_perceived_isr': 0,
            'selective_tax': 0,
            'other_taxes': 0,
            'legal_tip': 0,
            'payment_type': '02',
        }
        result = report.process_606_report_data(values)
        fields = result.split('|')

        # Verificar que no hay campos vacíos donde se esperan números (campos 7-21)
        for i in range(7, 22):
            if i == 16:  # WH_TYPE puede ser vacío si no aplica
                continue
            self.assertNotEqual(fields[i], '', 'Campo %d no debe ser vacío' % i)

        # Verificar valores específicos
        self.assertEqual(fields[0], '101234567')  # RNC
        self.assertEqual(fields[11], '15460.47')  # ITBIS Retenido
        self.assertEqual(fields[17], '8589.15')   # Retención Renta

    # =========================================
    # Tests de formato TXT 607
    # =========================================

    def test_process_607_no_empty_fields(self):
        """Test que el formato 607 no tiene campos vacíos donde se esperan números."""
        report = self._create_dgii_report()
        values = {
            'rnc_cedula': '401234567',
            'identification_type': 1,
            'fiscal_invoice_number': 'E310000000001',
            'modified_invoice_number': '',
            'income_type': '01',
            'invoice_date': '2026-03-15',
            'withholding_date': '2026-03-20',
            'invoiced_amount': 100000.00,
            'invoiced_itbis': 18000.00,
            'third_withheld_itbis': 18000.00,
            'perceived_itbis': 0,
            'third_income_withholding': 5000.00,
            'perceived_isr': 0,
            'selective_tax': 0,
            'other_taxes': 0,
            'legal_tip': 0,
            'cash': 0,
            'bank': 77000.00,
            'card': 0,
            'credit': 0,
            'swap': 0,
            'bond': 0,
            'others': 0,
        }
        result = report.process_607_report_data(values)
        fields = result.split('|')

        # Verificar que campos de retención tienen valores
        self.assertEqual(fields[9], '18000.00')   # ITBIS Retenido por Terceros
        self.assertEqual(fields[11], '5000.00')   # Retención Renta por Terceros

        # Verificar que campos percibidos son "0.00" no vacíos
        self.assertEqual(fields[10], '0.00')  # PRC_ITBIS
        self.assertEqual(fields[12], '0.00')  # PCR_ISR

    # =========================================
    # Tests de configuración de impuestos
    # =========================================

    def test_purchase_taxes_configured(self):
        """Test que los impuestos de compra tienen purchase_tax_type configurado."""
        itbis_taxes = self.env['account.tax'].search([
            ('purchase_tax_type', '=', 'itbis'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ])
        self.assertTrue(len(itbis_taxes) > 0, "Debe haber al menos un impuesto ITBIS de compra")

        ritbis_taxes = self.env['account.tax'].search([
            ('purchase_tax_type', '=', 'ritbis'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ])
        self.assertTrue(len(ritbis_taxes) > 0, "Debe haber al menos un impuesto RITBIS de compra")

        isr_taxes = self.env['account.tax'].search([
            ('purchase_tax_type', '=', 'isr'),
            ('type_tax_use', '=', 'purchase'),
            ('active', '=', True),
        ])
        self.assertTrue(len(isr_taxes) > 0, "Debe haber al menos un impuesto ISR de compra")

    def test_reconfigure_taxes(self):
        """Test que action_reconfigure_taxes configura impuestos de venta."""
        report = self._create_dgii_report()
        report.action_reconfigure_taxes()

        # Verificar que al menos los ISR de venta están configurados
        isr_sale = self.env['account.tax'].search([
            ('purchase_tax_type', '=', 'isr'),
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
        ])
        # El test pasa si hay al menos un ISR de venta configurado
        # (depende de que existan impuestos ISR de venta en la BD)
        if self.env['account.tax'].search([
            ('tax_group_id.name', 'ilike', 'ISR'),
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
        ]):
            self.assertTrue(len(isr_sale) > 0,
                            "Impuestos ISR de venta deben estar configurados después de reconfig")

    # =========================================
    # Tests de generación de reporte
    # =========================================

    def test_report_creation(self):
        """Test que se puede crear un reporte DGII."""
        report = self._create_dgii_report()
        self.assertEqual(report.state, 'draft')
        self.assertEqual(report.name, '03/2026')

    def test_report_generate_empty_period(self):
        """Test generación de reporte para período sin facturas."""
        report = self._create_dgii_report('01/2025')
        report._generate_report()
        self.assertEqual(report.state, 'generated')
        self.assertEqual(report.purchase_records, 0)
        self.assertEqual(report.sale_records, 0)
