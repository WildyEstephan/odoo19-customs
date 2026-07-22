/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

console.log('[L10N_DO_POS] PaymentScreen.js loaded');

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        console.log('[L10N_DO_POS] PaymentScreen setup() called');

        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-24 05:05 (actualizado 2026-01-10 para Odoo 19)
        // Razón: NO sobrescribir l10n_do_ecf_modification_code si ya tiene un valor
        // El TicketScreen puede haberlo seteado antes para notas de crédito
        // Proteger acceso a selectedOrder
        // Cambio de get_order() a getOrder() para Odoo 19
        if (this.pos && this.pos.getOrder && this.pos.getOrder()) {
            const currentOrder = this.pos.getOrder();

            // Solo inicializar si no tiene valor aún (false, undefined, null)
            // NO sobrescribir si ya fue seteado por TicketScreen
            if (!currentOrder.l10n_do_ecf_modification_code) {
                currentOrder.l10n_do_ecf_modification_code = false;
                console.log('[L10N_DO_POS] l10n_do_ecf_modification_code initialized to false');
            } else {
                console.log('[L10N_DO_POS] l10n_do_ecf_modification_code already set, keeping value:', currentOrder.l10n_do_ecf_modification_code);
            }

            // Forzar facturación si "Solo facturación" está activado
            if (this.pos.config && this.pos.config.only_invoice) {
                currentOrder.to_invoice = true;
                console.log('[L10N_DO_POS] Forced invoice due to only_invoice setting');
            }
        }

        this.dialog = useService("dialog");
        this.orm = useService("orm");
    },
    
    // Override toggleIsToInvoice para mantener facturación forzada
    toggleIsToInvoice() {
        if (this.pos.config && this.pos.config.only_invoice) {
            console.log('[L10N_DO_POS] Cannot toggle invoice - only_invoice is enforced');
            return; // No permitir desactivar facturación si only_invoice está activado
        }
        return super.toggleIsToInvoice(...arguments);
    },

    /**
     * Override shouldDownloadInvoice para implementar la configuración
     * l10n_do_disable_auto_print_invoice
     *
     * Este método controla si se debe descargar/imprimir automáticamente
     * el PDF de la factura en formato A4 desde el POS.
     *
     * @returns {boolean} true si se debe descargar el PDF de la factura, false si no
     */
    shouldDownloadInvoice() {
        // Verificar si la configuración de desactivar auto-impresión está activada
        if (this.pos.config && this.pos.config.l10n_do_disable_auto_print_invoice) {
            console.log('[L10N_DO_POS] Auto-print invoice (A4) disabled by configuration');
            console.log('[L10N_DO_POS] Only POS receipt will be printed, not the full invoice report');
            return false;
        }

        // Si no está activada la desactivación, usar el comportamiento por defecto
        console.log('[L10N_DO_POS] Auto-print invoice (A4) enabled - will download invoice PDF');
        return super.shouldDownloadInvoice(...arguments);
    },

    /**
     * Override _finalizeValidation para esperar QR en el backend ANTES de descargar PDF A4
     * El problema es que el PDF se genera antes de que el proceso EDI genere el QR
     */
    async _finalizeValidation() {
        const currentOrder = this.currentOrder;

        // Verificar si debemos esperar por el QR (Auto-Print A4 habilitado)
        const shouldWaitForQR = currentOrder?.is_to_invoice() &&
                                 this.shouldDownloadInvoice() &&
                                 this.pos.config;

        if (shouldWaitForQR) {
            console.log('[L10N_DO_POS] 🔄 _finalizeValidation - Auto-Print A4 habilitado, monitoreando QR...');
        }

        // Ejecutar el flujo base parcialmente - sincronizar orden
        // Replicamos la lógica del super pero interceptamos antes de descargar PDF

        if (currentOrder.is_paid_with_cash() || currentOrder.get_change()) {
            this.hardwareProxy.openCashbox();
        }

        // Usar formato ISO para la fecha (compatible con Odoo)
        currentOrder.date_order = new Date().toISOString().replace('T', ' ').substring(0, 19);

        for (const line of this.paymentLines) {
            if (!line.amount === 0) {
                currentOrder.remove_paymentline(line);
            }
        }

        this.pos.addPendingOrder([currentOrder.id]);
        currentOrder.state = "paid";

        this.env.services.ui.block();
        let syncOrderResult;
        try {
            // 1. Save order to server
            syncOrderResult = await this.pos.syncAllOrders({ throw: true });
            if (!syncOrderResult) {
                return;
            }

            // 2. ESPERAR QR si es factura electrónica y Auto-Print A4 está habilitado
            if (shouldWaitForQR && currentOrder.raw.account_move) {
                console.log('[L10N_DO_POS] ⏳ Esperando QR en backend antes de generar PDF A4...');

                const moveId = currentOrder.raw.account_move;
                const maxWaitTime = 20000; // 20 segundos máximo
                const checkInterval = 1000; // Revisar cada 1 segundo
                const startTime = Date.now();
                let qrReady = false;

                while ((Date.now() - startTime) < maxWaitTime) {
                    try {
                        // Consultar directamente si el QR está en la base de datos
                        const invoiceData = await this.orm.call(
                            'account.move',
                            'read',
                            [[moveId], ['qr_code', 'l10n_do_ecf_security_code', 'name']]
                        );

                        if (invoiceData && invoiceData.length > 0) {
                            const hasQR = invoiceData[0].qr_code && invoiceData[0].qr_code.length > 0;
                            const hasSecurityCode = invoiceData[0].l10n_do_ecf_security_code;

                            console.log(`[L10N_DO_POS] 🔍 Verificando QR para ${invoiceData[0].name}: QR=${hasQR ? 'SÍ' : 'NO'}, Código=${hasSecurityCode ? 'SÍ' : 'NO'}`);

                            if (hasQR && hasSecurityCode) {
                                console.log('[L10N_DO_POS] ✅ QR listo en backend - procediendo con PDF A4');
                                qrReady = true;
                                break;
                            }
                        }
                    } catch (e) {
                        console.warn('[L10N_DO_POS] Error verificando QR:', e.message);
                    }

                    await new Promise(resolve => setTimeout(resolve, checkInterval));
                }

                const waitedTime = Date.now() - startTime;
                console.log(`[L10N_DO_POS] ⏱️ Tiempo esperando QR: ${waitedTime}ms - ${qrReady ? '✅ LISTO' : '⚠️ TIMEOUT'}`);
            }

            // 3. Ahora descargar PDF (con QR si estuvo disponible)
            if (this.shouldDownloadInvoice() && currentOrder.is_to_invoice()) {
                if (currentOrder.raw.account_move) {
                    await this.invoiceService.downloadPdf(currentOrder.raw.account_move);
                } else {
                    throw {
                        code: 401,
                        message: "Backend Invoice",
                        data: { order: currentOrder },
                    };
                }
            }
        } catch (error) {
            // Autor: Arturo Diaz Lora
            // Fecha: 2025-11-26 16:15
            // Razón: Mejorar manejo de errores para mostrar mensajes claros de secuencia fiscal agotada
            // El error.message contiene "Odoo Server Error" pero el mensaje real está en error.data.message
            const errorName = error?.constructor?.name || '';

            if (errorName === 'ConnectionLostError') {
                this.afterOrderValidation();
                Promise.reject(error);
            } else if (errorName === 'RPCError') {
                currentOrder.state = "draft";

                // Obtener el mensaje real del error (está en error.data.message, no en error.message)
                let errorMessage = 'Error al procesar la orden';
                let errorTitle = _t('Error');

                if (error.data && error.data.message) {
                    errorMessage = error.data.message;

                    // Detectar errores de secuencia fiscal para mostrar título más claro
                    if (errorMessage.includes('SECUENCIA FISCAL') ||
                        errorMessage.toLowerCase().includes('secuencia fiscal')) {
                        errorTitle = _t('Secuencia Fiscal Agotada');
                    } else if (error.exceptionName === 'odoo.exceptions.UserError') {
                        errorTitle = _t('Operación Inválida');
                    } else if (error.exceptionName === 'odoo.exceptions.ValidationError') {
                        errorTitle = _t('Error de Validación');
                    }
                } else if (error.message && error.message !== 'Odoo Server Error') {
                    errorMessage = error.message;
                }

                console.error('[L10N_DO_POS] Error RPC:', {
                    message: error.message,
                    dataMessage: error.data?.message,
                    exceptionName: error.exceptionName
                });

                // Mostrar error al usuario con el mensaje completo
                this.dialog.add(AlertDialog, {
                    title: errorTitle,
                    body: errorMessage,
                });
            } else {
                throw error;
            }
            return error;
        } finally {
            this.env.services.ui.unblock();
        }

        // 4. Post process
        const postPushOrders = syncOrderResult.filter((order) => order.wait_for_push_order());
        if (postPushOrders.length > 0) {
            await this.postPushOrderResolve(postPushOrders.map((order) => order.id));
        }

        await this.afterOrderValidation(!!syncOrderResult && syncOrderResult.length > 0);
    },

    // Override afterOrderValidation - simplificado
    async afterOrderValidation() {
        console.log('[L10N_DO_POS] afterOrderValidation - NCF will be handled by postSyncAllOrders (v18 approach)');

        const result = await super.afterOrderValidation(...arguments);

        // Autor: Arturo Diaz Lora - 2026-01-10 - Cambio de get_order() a getOrder() para Odoo 19
        const currentOrder = this.pos.getOrder();
        console.log('[L10N_DO_POS] afterOrderValidation completed - order name:', currentOrder?.name);

        return result;
    },
    
    // Consultar el backend directamente para obtener NCF
    async queryBackendForNCF(currentOrder) {
        console.log('[L10N_DO_POS] Querying backend for NCF - order:', currentOrder.name);
        console.log('[L10N_DO_POS] ORM service available:', !!this.orm);
        console.log('[L10N_DO_POS] Current order details:', {
            name: currentOrder.name,
            id: currentOrder.id,
            server_id: currentOrder.server_id,
            state: currentOrder.state
        });
        
        // Add timeout to prevent hanging
        const timeout = new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Backend query timeout after 10 seconds')), 10000)
        );
        
        try {
            console.log('[L10N_DO_POS] Starting backend search...');
            
            // Race between the actual query and timeout
            const result = await Promise.race([
                this.performBackendQuery(currentOrder),
                timeout
            ]);
            
            return result;
            
        } catch (error) {
            console.error('[L10N_DO_POS] Error querying backend for NCF:', error);
            console.error('[L10N_DO_POS] Error details:', {
                message: error.message,
                stack: error.stack,
                name: error.name
            });
            return false;
        }
    },
    
    // Separate method for the actual backend query
    async performBackendQuery(currentOrder) {
        // Buscar la orden del POS en el backend con todos los campos necesarios
        const orderIds = await this.orm.call(
            'pos.order',
            'search',
            [[['pos_reference', '=', currentOrder.name]]]
        );
        
        console.log('[L10N_DO_POS] Backend search completed. Order IDs found:', orderIds);
        
        if (orderIds.length > 0) {
            console.log('[L10N_DO_POS] Found POS order in backend:', orderIds[0]);
            
            console.log('[L10N_DO_POS] Reading order data from backend...');
            // Obtener todos los campos dominicanos directamente de pos.order
            const orderData = await this.orm.call(
                'pos.order',
                'read',
                [orderIds, [
                    'l10n_latam_document_number',  // NCF
                    'l10n_latam_document_type_id', // Tipo documento
                    'account_move',                // Factura asociada
                    'name',                        // Nombre orden
                    'pos_reference',               // Referencia
                    'state'                        // Estado
                ]]
            );
            
            console.log('[L10N_DO_POS] Backend read completed. Order data:', orderData);
            
            if (orderData.length > 0) {
                const order = orderData[0];
                console.log('[L10N_DO_POS] 📋 Complete backend order data:', order);
                
                // El NCF está directamente en pos.order.l10n_latam_document_number
                if (order.l10n_latam_document_number) {
                    const ncf = order.l10n_latam_document_number;
                    console.log('[L10N_DO_POS] 🎯 NCF found directly in pos.order:', ncf);
                    
                    // Actualizar la orden con datos del backend
                    currentOrder.ncf = ncf;
                    currentOrder.l10n_latam_document_type_id = order.l10n_latam_document_type_id;
                    
                    // Obtener nombre de factura desde account_move si está disponible
                    if (order.account_move && order.account_move.length > 1) {
                        currentOrder.invoice_name = order.account_move[1]; // El display_name está en [1]
                    }
                    
                    console.log('[L10N_DO_POS] ✅ Order updated with backend NCF data:', {
                        ncf: ncf,
                        document_type: order.l10n_latam_document_type_id,
                        invoice_name: currentOrder.invoice_name,
                        pos_reference: order.pos_reference
                    });
                    
                    return true;
                    
                } else {
                    console.warn('[L10N_DO_POS] ⚠️ pos.order found but no l10n_latam_document_number:', order);
                    console.warn('[L10N_DO_POS] Available fields in backend order:', Object.keys(order));
                }
            } else {
                console.warn('[L10N_DO_POS] Could not read POS order data from backend');
            }
        } else {
            console.warn('[L10N_DO_POS] POS order not found in backend:', currentOrder.name);
            console.warn('[L10N_DO_POS] This might mean the order has not been synced yet');
            
            // Try searching by server_id if available
            if (currentOrder.server_id) {
                console.log('[L10N_DO_POS] Trying search by server_id:', currentOrder.server_id);
                const orderIdsByServerId = await this.orm.call(
                    'pos.order',
                    'search',
                    [[['id', '=', currentOrder.server_id]]]
                );
                console.log('[L10N_DO_POS] Search by server_id result:', orderIdsByServerId);
            }
        }
        
        return false;
    },
    pillClicked(modification_code) {
        console.log('[L10N_DO_POS] pillClicked called with:', modification_code);
        // Autor: Arturo Diaz Lora - 2026-01-10 - Cambio de get_order() a getOrder() para Odoo 19
        if (this.pos && this.pos.getOrder && this.pos.getOrder()) {
            this.pos.getOrder().l10n_do_ecf_modification_code = modification_code;
        }
    },
    async validateCreditNote(paymentMethod) {
        console.log('[L10N_DO_POS] validateCreditNote called');
        if (!paymentMethod) {
            return;
        }

        let paymentMethodCreditNote = false;

        // Buscar payment method de tipo credit_note en v18
        if (this.pos && this.pos.payment_methods) {
            console.log('[L10N_DO_POS] Searching for credit_note payment method');
            paymentMethodCreditNote = this.pos.payment_methods.find(pm => pm.type === 'credit_note');
            console.log('[L10N_DO_POS] Credit note payment method found:', !!paymentMethodCreditNote);
        }

        this.dialog.add(TextInputPopup, {
            title: 'Introduzca NCF de Nota de Crédito',
            startingValue: "",
            placeholder: 'B0401234567',
            getPayload: async (l10n_latam_document_number) => {
                if (l10n_latam_document_number !== '') {
                    // Autor: Arturo Diaz Lora - 2026-01-10 - Cambio de get_order() a getOrder() para Odoo 19
                    let order = this.pos.getOrder();
                    let partner = order ? order.getPartner() : null;
                    if (!partner){
                        console.log('[L10N_DO_POS] No partner found for credit note validation');
                        return;
                    }

                    const paymentLines = order ? order.payment_ids : [];
                    const line = paymentLines.find((line) => line.note === l10n_latam_document_number);
                    let document_number = l10n_latam_document_number.replace(/ /g, '')
                    const result = await this.orm.call("pos.order",
                                                       "credit_note_info_from_ui",
                                                       [document_number, partner.id, order.get_total_with_tax()])

                    if (result.msg !== '' || line) {
                        this.dialog.add(AlertDialog, {
                            title: 'Nota de Crédito',
                            body: result.msg || "Esta Nota de Crédito ya esta aplicada a la Orden",
                        });
                        return;
                    }

                    if (order && paymentMethodCreditNote) {
                        let newPaymentline = order.add_paymentline(paymentMethodCreditNote);
                        if (newPaymentline){
                            newPaymentline.set_amount(parseFloat(result.residual) || 0);
                            newPaymentline.set_credit_note_id(result.id);
                            newPaymentline.set_note(l10n_latam_document_number);
                            console.log('[L10N_DO_POS] Credit note payment line added');
                            return true;
                        }
                    } else {
                        console.log('[L10N_DO_POS] Could not add credit note payment line - missing order or payment method');
                    }
                }
            },
        });
    }
});
