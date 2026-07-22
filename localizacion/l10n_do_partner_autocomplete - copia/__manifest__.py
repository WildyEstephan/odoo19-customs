
{
    "name": "Rep. Dominicana - Partner Autocomplete",
    "summary": """
        Autocompletado de datos de contribuyentes desde la DGII.
        Consulta automática de RNC/Cédula para obtener nombre, estado,
        actividad económica y más información fiscal.
        Búsqueda de RNC directamente en facturas con creación automática de contactos.""",
    "author": "Adel Networks S,R,L",
    "website": "https://adelnetworks.com.do",
    "license": "LGPL-3",
    "version": "19.0.4.0.0",
    "depends": ["l10n_do_accounting", "contacts", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameters.xml",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
        "wizard/partner_from_rnc_wizard_views.xml",
    ],
    "external_dependencies": {
        "python": ["lxml", "requests"],
    },
}
