# -*- coding: utf-8 -*-
{
    'name': "República Dominicana - POS",
    'summary': """
        Incorpora funcionalidades de facturación con NCF al POS.
        """,
    'author': "Adel Networks S.R.L",
    "website": "https://adelnetworks.com.do",
    'license': 'LGPL-3',
    'category': 'Localization',
    'version': '19.0.1.0.28',  # Incrementado por Arturo Diaz Lora - 2025-11-26 03:50 - Revertido _load_pos_data_fields que causaba error
    'depends': ['l10n_do_accounting', 'l10n_do_edi', 'point_of_sale'],
    'data': [
        'data/data.xml',
        'security/ir.model.access.csv',
        # MODIFICADO: Arturo Diaz Lora - 2026-03-14 10:00
        # Razón: Agregar regla multi-company para pos.search_criteria
        'security/ir_rule.xml',
        'views/res_partner_views.xml',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
        'views/pos_payment_method_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_do_pos/static/src/css/*',
            'l10n_do_pos/static/src/app/models/models.js',
            'l10n_do_pos/static/src/app/store/models.js',
            'l10n_do_pos/static/src/app/store/pos_store_dgii.js',
            'l10n_do_pos/static/src/app/screens/**/*',
            'l10n_do_pos/static/src/app/components/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
