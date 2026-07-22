# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración para agregar el campo QR_code a account_move
    """
    _logger.info("=== Iniciando pre-migración l10n_do_edi 18.0.1.2.0 ===")
    
    # Verificar si la columna ya existe
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'account_move' 
        AND column_name = 'qr_code'
    """)
    
    exists = cr.fetchone()
    
    if not exists:
        _logger.info("Agregando columna qr_code a account_move...")
        # Cambiar el nombre del campo de QR_code a qr_code para seguir convención de Odoo
        cr.execute("""
            ALTER TABLE account_move 
            ADD COLUMN qr_code bytea
        """)
        _logger.info("✅ Columna qr_code agregada exitosamente")
    else:
        _logger.info("La columna qr_code ya existe en account_move")
    
    _logger.info("=== Pre-migración completada ===")

