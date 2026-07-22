/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        console.log('[L10N_DO_POS] TicketScreen setup - Dominican Republic extensions loaded');
    },

    _getSearchFields() {
        const result = super._getSearchFields(...arguments);
        // Modificar campo de búsqueda para usar display_name personalizado
        if (result.RECEIPT_NUMBER) {
            result.RECEIPT_NUMBER.modelField = 'display_name';
            console.log('[L10N_DO_POS] TicketScreen search field updated to use display_name');
        }
        return result;
    },

    async onDoRefund() {
        console.log('[L10N_DO_POS] TicketScreen onDoRefund - processing Dominican refund logic');

        const order = this.getSelectedOrder();
        if (!order) {
            console.warn('[L10N_DO_POS] No order selected for refund');
            return await super.onDoRefund(...arguments);
        }

        const partner = order.getPartner();
        console.log('[L10N_DO_POS] Processing refund for order:', order.name, 'partner:', partner?.name);

        // Determinar orden de destino para el refund
        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-23 02:05 (actualizado)
        // Razón: Corregir flujo - el código de modificación debe asignarse DESPUÉS de crear la orden de reembolso

        let selectedModificationCode = null;
        let fiscalInfo = null;

        try {
            // Obtener información fiscal dominicana de la orden original
            fiscalInfo = await this.orm.call("pos.order", "get_from_ui", [order.name]);
            console.log('[L10N_DO_POS] Fiscal info retrieved for refund:', fiscalInfo);

            // Autor: Arturo Diaz Lora
            // Fecha: 2025-11-25 18:35 (actualizado)
            // Razón: Consultar ECF activation directamente desde el servidor
            // El campo l10n_do_ecf_activated no se carga automáticamente en el POS en Odoo 18
            // SOLUCIÓN: Consultar directamente desde res.company vía RPC

            console.log('[L10N_DO_POS] === Verificando ECF activation desde servidor ===');

            // Consultar estado de ECF directamente desde el servidor
            let isEcfActivated = false;
            try {
                const companyData = await this.orm.call("res.company", "search_read",
                    [[['id', '=', this.pos.company.id]]],
                    {fields: ['l10n_do_ecf_activated']}
                );

                if (companyData && companyData.length > 0) {
                    isEcfActivated = companyData[0].l10n_do_ecf_activated || false;
                    console.log('[L10N_DO_POS] ✅ ECF activation obtenido desde servidor:', isEcfActivated);
                    console.log('[L10N_DO_POS] Compañía ID:', this.pos.company.id);
                    console.log('[L10N_DO_POS] Compañía nombre:', this.pos.company.name);
                } else {
                    console.warn('[L10N_DO_POS] ⚠️ No se pudo obtener datos de la compañía');
                }
            } catch (error) {
                console.error('[L10N_DO_POS] ❌ Error consultando ECF activation:', error);
                // En caso de error, asumir que NO está activado
                isEcfActivated = false;
            }

            console.log('[L10N_DO_POS] 🔍 ECF Activado (resultado final):', isEcfActivated);
            console.log('[L10N_DO_POS] ================================================');

            if (isEcfActivated) {
                console.log('[L10N_DO_POS] ✅ Emisor Electrónico activado - mostrando popup de código de modificación');

                // Mostrar popup para seleccionar código de modificación
                const modificationCodeList = [
                    { id: "1", label: "01 - Anulación Total", item: "1" },
                    { id: "2", label: "02 - Corrección de Texto", item: "2" },
                    { id: "3", label: "03 - Corrección de Monto", item: "3" },
                    { id: "4", label: "04 - Reemplazo NCF emitido en contingencia", item: "4" },
                    { id: "5", label: "05 - Referencia Factura Consumidor Electrónica", item: "5" },
                ];

                selectedModificationCode = await makeAwaitable(this.dialog, SelectionPopup, {
                    title: _t("Seleccione el código de modificación"),
                    list: modificationCodeList,
                });

                if (!selectedModificationCode) {
                    console.warn('[L10N_DO_POS] No modification code selected, aborting refund');
                    return;
                }

                console.log('[L10N_DO_POS] ✅ Selected modification code:', selectedModificationCode);
            } else {
                console.log('[L10N_DO_POS] ℹ️ Emisor Electrónico NO activado - omitiendo código de modificación');
                // selectedModificationCode permanece null
            }
        } catch (error) {
            console.error('[L10N_DO_POS] Error retrieving fiscal info for refund:', error);
            return;  // Abortar si hay error
        }

        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-25 18:27 (actualizado)
        // Razón: Guardar modification_code SOLO si ECF está activado y fue seleccionado
        // Guardamos los datos fiscales en el POS store para que serialize() los lea
        if (selectedModificationCode) {
            this.pos.pending_refund_fiscal_data = {
                modification_code: selectedModificationCode.padStart(2, '0'),
                origin_ncf: fiscalInfo.l10n_latam_document_number
            };
            console.log('[L10N_DO_POS] ✅ Datos fiscales guardados (con código modificación):', this.pos.pending_refund_fiscal_data);
        } else {
            // Si ECF no está activado, solo guardar origin_ncf
            this.pos.pending_refund_fiscal_data = {
                modification_code: false,
                origin_ncf: fiscalInfo.l10n_latam_document_number
            };
            console.log('[L10N_DO_POS] ℹ️ Datos fiscales guardados (sin código modificación):', this.pos.pending_refund_fiscal_data);
        }

        // Proceder con el refund normal - esto crea la nueva orden
        await super.onDoRefund(...arguments);

        // AHORA asignar los datos fiscales a la orden recién creada
        // Autor: Arturo Diaz Lora - 2026-01-10 - Cambio de get_order() a getOrder() para Odoo 19
        const currentOrder = this.pos.getOrder();
        if (currentOrder && fiscalInfo) {
            console.log('[L10N_DO_POS] Assigning fiscal data to newly created refund order');
            console.log('[L10N_DO_POS] 🔍 ANTES de asignar:');
            console.log('[L10N_DO_POS]   - currentOrder.l10n_do_ecf_modification_code:', currentOrder.l10n_do_ecf_modification_code);

            // Asignar código de modificación SOLO si existe (ECF activado)
            if (selectedModificationCode) {
                currentOrder.l10n_do_ecf_modification_code = selectedModificationCode.padStart(2, '0');
                console.log('[L10N_DO_POS] ✅ Código de modificación asignado:', currentOrder.l10n_do_ecf_modification_code);
            } else {
                currentOrder.l10n_do_ecf_modification_code = false;
                console.log('[L10N_DO_POS] ℹ️ No se asignó código de modificación (Emisor Electrónico NO activado)');
            }

            // Asignar NCF y origin_ncf siempre
            currentOrder.ncf = fiscalInfo.l10n_latam_document_number;
            currentOrder.origin_ncf = fiscalInfo.l10n_latam_document_number;
            currentOrder.l10n_latam_document_number = fiscalInfo.l10n_latam_document_number;
            currentOrder.to_invoice = true;  // Forzar facturación

            console.log('[L10N_DO_POS] 🔍 DESPUÉS de asignar:');
            console.log('[L10N_DO_POS]   - currentOrder.l10n_do_ecf_modification_code:', currentOrder.l10n_do_ecf_modification_code);
            console.log('[L10N_DO_POS]   - Tipo:', typeof currentOrder.l10n_do_ecf_modification_code);
            console.log('[L10N_DO_POS]   - Valor exacto:', JSON.stringify(currentOrder.l10n_do_ecf_modification_code));

            console.log('[L10N_DO_POS] ✅ Refund order configured with Dominican fiscal data:', {
                ncf: currentOrder.ncf,
                origin_ncf: currentOrder.origin_ncf,
                to_invoice: currentOrder.to_invoice,
                modification_code: currentOrder.l10n_do_ecf_modification_code
            });
        }

        console.log('[L10N_DO_POS] Dominican refund process completed');
    }
});