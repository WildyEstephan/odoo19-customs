/** @odoo-module */

// Autor: Arturo Diaz Lora - 2026-01-10
// Actualizado para Odoo 19 - usa props.order en lugar de props.data

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

console.log('[L10N_DO_POS] ========================================');
console.log('[L10N_DO_POS] OrderReceipt.js loaded - Dominican version for Odoo 19');
console.log('[L10N_DO_POS] ========================================');

patch(OrderReceipt.prototype, {
    setup() {
        console.log('[L10N_DO_POS] OrderReceipt setup() called');
        super.setup(...arguments);
        this.pos = usePos();
        console.log('[L10N_DO_POS] OrderReceipt setup completed');
    },

    // Getter para datos de la compañía
    get companyData() {
        const order = this.props.order;
        if (!order) return {};

        return {
            id: order.company?.id,
            name: order.company?.name || 'EMPRESA NO CONFIGURADA',
            vat: order.company?.vat || '',
            street: order.company?.street || '',
            city: order.company?.city || '',
            phone: order.company?.phone || '',
            email: order.company?.email || '',
            website: order.company?.website || '',
            l10n_do_ecf_issuer: order.company?.l10n_do_ecf_issuer || false,
        };
    },

    // Getter para datos del partner/cliente
    get partnerData() {
        const order = this.props.order;
        if (!order) return {};

        const partner = order.getPartner ? order.getPartner() : null;
        if (!partner) return {};

        return {
            name: partner.name || '',
            vat: partner.vat || '',
            email: partner.email || '',
            address: partner.street || '',
            l10n_do_dgii_tax_payer_type: partner.l10n_do_dgii_tax_payer_type || 'non_payer',
        };
    },

    // Getter para líneas de productos
    get orderlines() {
        const order = this.props.order;
        if (!order || !order.lines) return [];

        return order.lines.map(line => ({
            id: line.id,
            productName: line.product?.display_name || line.getDisplayData?.()?.productName || 'Producto',
            qty: line.qty?.toFixed(2) || '0.00',
            unitPrice: line.price_unit?.toFixed(2) || '0.00',
            price: line.get_price_with_tax?.()?.toFixed(2) || line.price?.toFixed(2) || '0.00',
            discount: line.discount || 0,
            customerNote: line.customerNote || '',
            unit: line.product?.uom_id?.name || 'Unidades',
        }));
    },

    // Getter para detalles de impuestos
    get taxDetails() {
        const order = this.props.order;
        if (!order) return [];

        try {
            const taxTotals = order.get_tax_details?.() || [];
            return taxTotals.map(tax => ({
                name: tax.name || tax.tax?.name || 'ITBIS',
                amount: tax.amount?.toFixed(2) || '0.00',
                tax_percentage: tax.tax?.amount || 18,
            }));
        } catch (e) {
            console.warn('[L10N_DO_POS] Error getting tax details:', e);
            return [];
        }
    },

    // Getter para líneas de pago
    get paymentlines() {
        const order = this.props.order;
        if (!order || !order.payment_ids) return [];

        return order.payment_ids.filter(p => !p.is_change).map(payment => ({
            name: payment.payment_method_id?.name || payment.name || 'Efectivo',
            amount: payment.amount?.toFixed(2) || '0.00',
        }));
    },

    // Getter para datos fiscales dominicanos
    get dominicanFiscalData() {
        const order = this.props.order;
        if (!order) return {};

        const asStr = (v) => (typeof v === 'string' ? v : '');
        const ncf = asStr(order.l10n_latam_document_number) || asStr(order.ncf);

        return {
            ncf,
            to_invoice: order.to_invoice || false,
            is_ecf_invoice: order.is_ecf_invoice || ncf.startsWith('E'),
            l10n_do_ecf_security_code: asStr(order.l10n_do_ecf_security_code),
            l10n_do_ecf_sign_date: asStr(order.l10n_do_ecf_sign_date),
            l10n_do_ncf_expiration_date: asStr(order.l10n_do_ncf_expiration_date),
            origin_ncf: asStr(order.origin_ncf) || asStr(order.l10n_do_origin_ncf),
            QR_code: asStr(order.QR_code) || asStr(order.qr_code),
            qr_code_img: asStr(order.qr_code_img) || (asStr(order.QR_code) ? 'data:image/png;base64,' + order.QR_code : ''),
        };
    },

    // Getter para totales
    get totals() {
        const order = this.props.order;
        if (!order) return {};

        return {
            subtotal: order.get_total_without_tax?.()?.toFixed(2) || '0.00',
            tax: order.get_total_tax?.()?.toFixed(2) || '0.00',
            total: order.get_total_with_tax?.()?.toFixed(2) || '0.00',
            change: order.get_change?.()?.toFixed(2) || '0.00',
            discount: order.get_total_discount?.()?.toFixed(2) || '0.00',
        };
    },

    // Getter para nombre de la orden
    get orderName() {
        return this.props.order?.name || this.props.order?.pos_reference || 'N/A';
    },

    // Getter para cajero
    get cashierName() {
        return this.props.order?.getCashierName?.() || this.props.order?.cashier?.name || '';
    },

    // Getter para determinar si es factura electrónica
    get isElectronicInvoice() {
        const ncf = this.dominicanFiscalData.ncf || '';
        return ncf.startsWith('E');
    },

    // Getter para tipo de documento limpio
    get documentTypeName() {
        const ncf = this.dominicanFiscalData.ncf || '';
        if (ncf.startsWith('E32')) return 'FACTURA CONSUMO ELECTRÓNICA';
        if (ncf.startsWith('E33')) return 'FACTURA CRÉDITO FISCAL ELECTRÓNICA';
        if (ncf.startsWith('E34')) return 'NOTA DE CRÉDITO ELECTRÓNICA';
        if (ncf.startsWith('E43')) return 'FACTURA RÉGIMEN ESPECIAL ELECTRÓNICA';
        if (ncf.startsWith('E44')) return 'FACTURA GUBERNAMENTAL ELECTRÓNICA';
        if (ncf.startsWith('E45')) return 'FACTURA EXPORTACIÓN ELECTRÓNICA';
        if (ncf.startsWith('B01')) return 'FACTURA CRÉDITO FISCAL';
        if (ncf.startsWith('B02')) return 'FACTURA CONSUMO';
        if (ncf.startsWith('B04')) return 'NOTA DE CRÉDITO';
        if (ncf.startsWith('B14')) return 'FACTURA RÉGIMEN ESPECIAL';
        if (ncf.startsWith('B15')) return 'FACTURA GUBERNAMENTAL';
        if (ncf.startsWith('B16')) return 'FACTURA EXPORTACIÓN';
        return 'COMPROBANTE FISCAL';
    },

    // Getter para fecha formateada
    get formattedDate() {
        const now = new Date();
        const date = now.toLocaleDateString('es-DO', {day: '2-digit', month: '2-digit', year: 'numeric'});
        const time = now.toLocaleTimeString('es-DO', {hour: '2-digit', minute: '2-digit', hour12: true});
        return `${date} ${time}`;
    },
});
