# MODIFICADO: Arturo Diaz Lora - 2026-03-19 01:25
# Razón: Actualizar metadatos y agregar dependencia l10n_do_accounting
{
    'name': 'Certificación de Retención DGII',
    'version': '19.0.1.1.0',
    'category': 'Accounting/Localizations',
    'summary': 'Generar Certificación de Retención ITBIS/ISR conforme a Normas DGII '
               '(Norma General 02-2005 y 07-2007)',
    'description': """
Certificación de Retención DGII - República Dominicana
=======================================================

Genera certificaciones de retención de ITBIS e ISR conforme a:
- Norma General No. 02-2005 (Retención del ITBIS)
- Norma General No. 07-2007 (Retención del ISR)
- Código Tributario (Ley 11-92 y sus modificaciones)

Características:
- Búsqueda de facturas por proveedor y rango de fechas
- Cálculo automático de totales de retenciones
- Reporte PDF con membrete de empresa
- Detalle por factura: NCF, base imponible, ITBIS facturado, ITBIS retenido, ISR retenido
    """,
    'author': 'Jeffry J. De La Rosa, Arturo Diaz Lora',
    'license': 'LGPL-3',
    'website': 'http://astratech.com.do',
    'depends': [
        'dgii_reports',
        'l10n_do_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/withholding_certification_wizard_views.xml',
        'report/withholding_certification_report.xml',
    ],
    'installable': True,
}
