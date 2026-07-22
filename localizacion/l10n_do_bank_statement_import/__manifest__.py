{
    'name': "Importacion De Exracto Dominicanos",

    'summary': """
        Permite importar los extractos bancarios.
        """,

    'description': u"""
        Luego de descargar el extracto bancario desde el banco este módulo
        le permitirá importarlo para fines de conciliación.
    """,

    'author': 'Jeffry J. De La Rosa',
    'website': "http://astratech.com.do",
    "license": "LGPL-3",

    'category': 'Account',
    'version': "19.0.1.0.0",

    # any module necessary for this one to work correctly
    'depends': ['base','l10n_do', 'account'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_view.xml',
        'views/bank_statement.xml'
    ],
}
