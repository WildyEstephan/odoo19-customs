# -*- coding: utf-8 -*-
from . import controllers
from . import models
from . import wizards


def _cleanup_invalid_edi_documents(env):
    """
    Elimina documentos EDI creados para comprobantes NO electrónicos.
    Los comprobantes tradicionales (B01, B02, B14, B15) NO deben tener documentos EDI.
    Solo los comprobantes electrónicos (E31-E47) deben procesarse por EDI.

    Autor: Arturo Diaz Lora
    Fecha: 2025-12-02 21:55
    Razón: Limpieza de documentos EDI inválidos que bloquean el procesamiento del cron
    """
    import logging
    _logger = logging.getLogger(__name__)

    _logger.info("Iniciando limpieza de documentos EDI de comprobantes no electronicos...")

    # Buscar documentos EDI de comprobantes que NO empiecen con 'E'
    env.cr.execute("""
        SELECT ed.id, am.l10n_latam_document_number, am.name
        FROM account_edi_document ed
        JOIN account_move am ON ed.move_id = am.id
        WHERE ed.state = 'to_send'
        AND (
            am.l10n_latam_document_number NOT LIKE 'E%%'
            OR am.l10n_latam_document_number IS NULL
        )
    """)

    invalid_docs = env.cr.fetchall()

    if invalid_docs:
        _logger.info(f"Encontrados {len(invalid_docs)} documentos EDI invalidos para eliminar:")
        for doc_id, ncf, invoice_name in invalid_docs:
            _logger.info(f"   - ID: {doc_id}, NCF: {ncf}, Factura: {invoice_name}")

        # Eliminar documentos inválidos
        doc_ids = [doc[0] for doc in invalid_docs]
        env.cr.execute("""
            DELETE FROM account_edi_document WHERE id IN %s
        """, (tuple(doc_ids),))

        _logger.info(f"Eliminados {len(invalid_docs)} documentos EDI invalidos")
    else:
        _logger.info("No hay documentos EDI invalidos para eliminar")


def _reset_connection_error_documents(env):
    """
    Resetea el blocking_level de documentos EDI con errores de conexión temporal
    para permitir que el cron EDI los reintente automáticamente.

    Autor: Arturo Diaz Lora
    Fecha: 2025-12-06 15:45
    Razón: Los errores de conexión (Connection aborted, RemoteDisconnected, Timeout, etc.)
           son temporales y deben reintentarse. Esta función cambia blocking_level de
           'error' a 'warning' para que el cron los procese nuevamente.
    """
    import logging
    _logger = logging.getLogger(__name__)

    _logger.info("Iniciando reseteo de documentos EDI con errores de conexion...")

    # Buscar documentos EDI con errores de conexión que están bloqueados
    env.cr.execute("""
        SELECT ed.id, am.name, SUBSTRING(ed.error::text, 1, 100) as error_preview
        FROM account_edi_document ed
        JOIN account_move am ON ed.move_id = am.id
        WHERE ed.state = 'to_send'
        AND ed.blocking_level = 'error'
        AND (
            ed.error ILIKE '%%Connection aborted%%'
            OR ed.error ILIKE '%%RemoteDisconnected%%'
            OR ed.error ILIKE '%%ConnectionError%%'
            OR ed.error ILIKE '%%Timeout%%'
            OR ed.error ILIKE '%%Connection refused%%'
            OR ed.error ILIKE '%%network unreachable%%'
            OR ed.error ILIKE '%%connection reset%%'
        )
    """)

    connection_error_docs = env.cr.fetchall()

    if connection_error_docs:
        _logger.info(f"Encontrados {len(connection_error_docs)} documentos EDI con errores de conexion:")
        for doc_id, invoice_name, error_preview in connection_error_docs:
            _logger.info(f"   - ID: {doc_id}, Factura: {invoice_name}, Error: {error_preview}...")

        # Cambiar blocking_level de 'error' a 'warning' para permitir reintentos
        doc_ids = [doc[0] for doc in connection_error_docs]
        env.cr.execute("""
            UPDATE account_edi_document
            SET blocking_level = 'warning',
                error = CONCAT('(Reintentando automaticamente) ', COALESCE(error, ''))
            WHERE id IN %s
        """, (tuple(doc_ids),))

        _logger.info(f"Reseteados {len(connection_error_docs)} documentos EDI para reintento automatico")
    else:
        _logger.info("No hay documentos EDI con errores de conexion para resetear")


def post_init_hook(env):
    """Hook post-instalación para limpiar documentos EDI inválidos y resetear errores de conexión"""
    _cleanup_invalid_edi_documents(env)
    _reset_connection_error_documents(env)
