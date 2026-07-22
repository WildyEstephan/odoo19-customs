
from . import models
from . import wizard


def post_init_hook(env):
    """
    Hook ejecutado después de la instalación/actualización del módulo.
    Implementa trigger SQL para prevenir facturas duplicadas por race conditions.

    Autor: Arturo Diaz Lora
    Fecha: 2026-04-03
    Referencia: /odoo19/ANALISIS_CAUSA_RAIZ_FACTURAS_DUPLICADAS.md
    """

    # SQL para crear función y trigger que previene duplicados
    sql_trigger = """
    -- Función que bloquea el diario durante asignación de secuencia
    CREATE OR REPLACE FUNCTION lock_journal_for_sequence()
    RETURNS TRIGGER AS $$
    DECLARE
        v_journal_locked BOOLEAN;
    BEGIN
        -- Solo aplicar si:
        -- 1. Es una factura (move_type in invoice/refund types)
        -- 2. El nombre está cambiando de '/' a un número real
        -- 3. El estado es 'posted'

        IF NEW.state = 'posted'
           AND NEW.name IS NOT NULL
           AND NEW.name != '/'
           AND (OLD.name IS NULL OR OLD.name = '/' OR OLD.name != NEW.name)
           AND NEW.move_type IN ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
        THEN
            -- Bloquear el diario para evitar race conditions
            -- FOR UPDATE serializa las transacciones
            PERFORM id
            FROM account_journal
            WHERE id = NEW.journal_id
            FOR UPDATE;

            -- Log para debugging (visible en logs de PostgreSQL si log_min_messages <= NOTICE)
            RAISE DEBUG 'Locked journal % for move % with sequence %',
                NEW.journal_id, NEW.id, NEW.name;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Crear trigger si no existe
    DROP TRIGGER IF EXISTS trigger_lock_journal_for_sequence ON account_move;

    CREATE TRIGGER trigger_lock_journal_for_sequence
        BEFORE INSERT OR UPDATE OF name, state ON account_move
        FOR EACH ROW
        EXECUTE FUNCTION lock_journal_for_sequence();

    -- Comentarios para documentación
    COMMENT ON FUNCTION lock_journal_for_sequence() IS
        'Previene facturas duplicadas bloqueando el diario durante asignación de números de secuencia. Soluciona race conditions cuando múltiples usuarios confirman facturas simultáneamente.';

    COMMENT ON TRIGGER trigger_lock_journal_for_sequence ON account_move IS
        'Trigger que previene duplicados en números de factura bloqueando el diario durante la asignación (módulo: l10n_do_accounting)';
    """

    import logging
    _logger = logging.getLogger(__name__)

    try:
        # Usar savepoint para no envenenar la transacción principal si falla
        env.cr.execute("SAVEPOINT install_trigger")
        env.cr.execute(sql_trigger)
        env.cr.execute("RELEASE SAVEPOINT install_trigger")
        _logger.info("✅ l10n_do_accounting: Trigger de prevención de duplicados instalado correctamente")

    except Exception as e:
        env.cr.execute("ROLLBACK TO SAVEPOINT install_trigger")
        _logger.error(f"❌ l10n_do_accounting: Error al instalar trigger de prevención de duplicados: {e}")
        # No hacer raise para no bloquear la instalación del módulo
