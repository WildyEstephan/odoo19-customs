{
    'name': "República Dominicana - ECF POS",
    'summary': """
        Incorpora funcionalidades de facturación electronica con e-NCF al POS
    """,
    'author': "Adel Networks S.R.L",
    "website": "https://adelnetworks.com.do",
    'license': 'LGPL-3',
    'category': 'Sales/Point of Sale',
    'version': "19.0.1.0.0",
    'depends': ['l10n_do_pos', 'l10n_do_ecf_connector'],
    'data': [
        'views/pos_order_view.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_do_ecf_pos_connector_advance/static/src/js/Screens/PaymentScreen/PaymentScreen.js',
            'l10n_do_ecf_pos_connector_advance/static/src/js/models.js',
            'l10n_do_ecf_pos_connector_advance/static/src/xml/**/*'
        ],
    },
}
