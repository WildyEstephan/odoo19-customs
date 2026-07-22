# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migración para regenerar códigos QR para facturas existentes
    """
    _logger.info("=== Iniciando post-migración l10n_do_edi 18.0.1.2.0 ===")
    
    # Contar facturas que tienen código de seguridad pero no tienen QR
    cr.execute("""
        SELECT COUNT(*) 
        FROM account_move 
        WHERE l10n_do_ecf_security_code IS NOT NULL 
        AND qr_code IS NULL
        AND move_type IN ('out_invoice', 'out_refund')
    """)
    
    count = cr.fetchone()[0]
    
    _logger.info(f"📊 Encontradas {count} facturas electrónicas sin código QR")
    _logger.info("ℹ️  Los códigos QR se regenerarán automáticamente al abrir cada factura")
    _logger.info("ℹ️  O puede usar el botón 'Regenerar QR' en cada factura")
    
    _logger.info("=== Post-migración completada ===")

