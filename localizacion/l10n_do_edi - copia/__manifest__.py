# -*- coding: utf-8 -*-
{
    'name': 'República Dominicana - Facturación Electrónica (DGII)',
    'version': '19.0.1.2.8',
    'category': 'Accounting/Localizations',
    'summary': 'Facturación Electrónica en RD utilizando el framework EDI y firma P12',
    'description': """
        Módulo de ejemplo que implementa la facturación electrónica para República Dominicana
        en Odoo 19 usando el framework EDI y firma digital con PKCS#12 (.p12).

        Cambios v19.0.1.2.8:
        - Cron EDI cada 15 minutos en lugar de 1 día
        - Limpieza automática de documentos EDI inválidos
        - Reintentos automáticos de errores de conexión
    """,
    'author': 'Overload Solutions',
    'website': 'https://www.overloadsolutions.com.do',
    'license': 'AGPL-3',
    'depends': [
        'account',
        'account_edi',
        'l10n_do',
        'l10n_do_accounting'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_tax_group_data.xml',
        'data/account_tax_data.xml',
        'data/do_edi_format.xml',
        'data/edi_cron_config.xml',  # Arturo Diaz Lora - 2025-12-02: Cron EDI cada 15 min
        'views/account_move_views.xml',
        'views/res_company_views.xml',
        'views/report_invoice.xml',
        'wizards/commercial_approval_wizard_views.xml',
        'wizards/excel_to_xml_views.xml',
        'wizards/dgii_result_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'external_dependencies': {
        'python': ['pyqrcode'],
    },
    'post_init_hook': 'post_init_hook',  # Arturo Diaz Lora - 2025-12-02: Hook para limpiar documentos EDI inválidos
    'installable': True,
    'application': False,
}
