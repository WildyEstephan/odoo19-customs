# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Hook ejecutado después de la instalación/actualización del módulo l10n_do_pos

    Realiza las siguientes configuraciones automáticas:
    1. Configura el cliente por defecto en configuraciones POS existentes
    2. Corrige el campo is_cash_count en métodos de pago existentes
    """
    _logger.info("[L10N_DO_POS] ========================================")
    _logger.info("[L10N_DO_POS] Executing post_init_hook")
    _logger.info("[L10N_DO_POS] ========================================")

    # 1. Configurar clientes por defecto
    _logger.info("[L10N_DO_POS] 1. Configuring default partners for POS configurations")
    try:
        pos_config_model = env['pos.config']
        pos_config_model._ensure_default_partner_configuration()
        _logger.info("[L10N_DO_POS] ✅ Successfully configured default partners")
    except Exception as e:
        _logger.error(f"[L10N_DO_POS] ❌ Error configuring default partners: {e}")

    # 2. Corregir is_cash_count en métodos de pago
    _logger.info("[L10N_DO_POS] 2. Fixing is_cash_count for existing payment methods")
    try:
        _fix_payment_methods_cash_count(env)
        _logger.info("[L10N_DO_POS] ✅ Successfully fixed payment methods")
    except Exception as e:
        _logger.error(f"[L10N_DO_POS] ❌ Error fixing payment methods: {e}")
        import traceback
        _logger.error(traceback.format_exc())

    _logger.info("[L10N_DO_POS] ========================================")
    _logger.info("[L10N_DO_POS] post_init_hook completed")
    _logger.info("[L10N_DO_POS] ========================================")


def _fix_payment_methods_cash_count(env):
    """
    Corrige el campo is_cash_count en métodos de pago existentes.

    PROBLEMA: Los métodos de pago con journal tipo 'cash' pueden tener
    is_cash_count = False (incorrecto), causando que las sesiones POS
    muestren saldo de efectivo = 0.

    SOLUCIÓN: Forzar el recálculo de is_cash_count para todos los métodos
    de pago que tienen journal tipo 'cash'.
    """
    PaymentMethod = env['pos.payment.method']

    # Buscar todos los métodos de pago (activos e inactivos)
    all_payment_methods = PaymentMethod.with_context(active_test=False).search([])

    _logger.info(f"[L10N_DO_POS] Found {len(all_payment_methods)} payment methods to check")

    # Identificar métodos con journal tipo 'cash' que tienen is_cash_count incorrecto
    cash_methods = all_payment_methods.filtered(
        lambda pm: pm.journal_id and pm.journal_id.type == 'cash'
    )

    if not cash_methods:
        _logger.info("[L10N_DO_POS] No cash payment methods found")
        return

    _logger.info(f"[L10N_DO_POS] Found {len(cash_methods)} cash payment methods:")
    for pm in cash_methods:
        _logger.info(
            f"[L10N_DO_POS]   - '{pm.name}' (ID: {pm.id}): "
            f"is_cash_count={pm.is_cash_count} (should be True)"
        )

    # Forzar recálculo de is_cash_count
    _logger.info(f"[L10N_DO_POS] Forcing recalculation of is_cash_count...")
    cash_methods._ensure_is_cash_count_computed()

    # Refrescar para ver valores actualizados
    cash_methods.invalidate_recordset()

    # Verificar resultados
    _logger.info(f"[L10N_DO_POS] Verification after fix:")
    fixed_count = 0
    for pm in cash_methods:
        status = "✅" if pm.is_cash_count else "⚠️"
        _logger.info(
            f"[L10N_DO_POS]   {status} '{pm.name}' (ID: {pm.id}): "
            f"is_cash_count={pm.is_cash_count}"
        )
        if pm.is_cash_count:
            fixed_count += 1

    _logger.info(
        f"[L10N_DO_POS] Fixed {fixed_count}/{len(cash_methods)} cash payment methods"
    )


def uninstall_hook(env):
    """
    Hook ejecutado antes de la desinstalación del módulo l10n_do_pos
    Limpia configuraciones específicas del módulo
    """
    _logger.info("[L10N_DO_POS] Executing uninstall_hook - cleaning up configurations")
    
    try:
        # Opcional: limpiar configuraciones específicas del módulo
        # (por ejemplo, remover referencias al cliente de consumo)
        
        _logger.info("[L10N_DO_POS] Successfully cleaned up configurations")
        
    except Exception as e:
        _logger.error(f"[L10N_DO_POS] Error in uninstall_hook: {e}") 