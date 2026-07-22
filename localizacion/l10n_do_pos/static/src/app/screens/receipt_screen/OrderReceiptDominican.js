/** @odoo-module */

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";

console.log('[L10N_DO_POS] OrderReceiptDominican.js loaded');

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        console.log('[L10N_DO_POS] OrderReceipt patched for Dominican Republic');
        this.processDominicanReceiptData();
    },

    processDominicanReceiptData() {
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] PROCESANDO DATOS RECIBO DOMINICANO');
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');

        if (!this.props || !this.props.data) {
            console.log('[L10N_DO_POS] ⚠️ No hay datos en props');
            return;
        }

        const data = this.props.data;
        console.log('[L10N_DO_POS] Props data original:', Object.keys(data));

        // Crear objeto de datos dominicanos procesados
        this.dominicanReceiptData = {
            // Copiar todos los datos originales
            ...data,

            // Procesar datos fiscales específicos
            ncf: data.l10n_latam_document_number || data.ncf || null,
            l10n_latam_document_number: data.l10n_latam_document_number || data.ncf || null,
            ncf_status: this.determineNCFStatus(data),
            
            // Procesar tipo de documento
            clean_document_type: this.cleanDocumentType(data.l10n_latam_document_type_id),
            
            // Procesar datos EDI
            is_ecf_invoice: this.determineECFStatus(data),
            qr_code_img: this.processQRCode(data),
            
            // Datos de la compañía procesados
            company: this.processCompanyData(data),
            
            // Estado de aprobación DGII
            dgii_approval_status: this.processDGIIStatus(data)
        };

        console.log('[L10N_DO_POS] ✅ Datos dominicanos procesados:', this.dominicanReceiptData);
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
    },

    determineNCFStatus(data) {
        if (data.l10n_latam_document_number || data.ncf) {
            return 'CONFIRMADO';
        } else if (data.to_invoice) {
            return 'PROCESANDO';
        }
        return 'NO_REQUERIDO';
    },

    cleanDocumentType(documentType) {
        if (!documentType) return 'CONSUMO';

        // Si es un array con nombre, extraer el nombre
        if (Array.isArray(documentType) && documentType.length > 1) {
            documentType = documentType[1];
        }

        // Convertir a string y limpiar
        const docTypeStr = String(documentType).trim();

        // Mapear tipos comunes
        const typeMap = {
            'Factura de Consumo': 'CONSUMO',
            'Factura con valor fiscal de Consumo': 'CONSUMO', 
            'Consumo Electrónica': 'CONSUMO',
            'Factura de Crédito Fiscal': 'CRÉDITO FISCAL',
            'Crédito Fiscal Electrónica': 'CRÉDITO FISCAL',
            'Nota de Débito': 'NOTA DE DÉBITO',
            'Nota de Crédito': 'NOTA DE CRÉDITO'
        };

        return typeMap[docTypeStr] || docTypeStr.toUpperCase().replace('FACTURA DE ', '').replace('ELECTRÓNICA', '').trim();
    },

    determineECFStatus(data) {
        return !!(
            data.QR_code || 
            data.qr_code_img || 
            data.l10n_do_ecf_security_code || 
            data.l10n_do_ecf_sign_date ||
            (data.l10n_latam_document_number && data.l10n_latam_document_number.startsWith('E'))
        );
    },

    processQRCode(data) {
        if (data.qr_code_img) {
            return data.qr_code_img;
        } else if (data.l10n_do_ecf_qr_code) {
            return data.l10n_do_ecf_qr_code;
        } else if (data.QR_code) {
            // Si QR_code no tiene prefijo, añadirlo
            if (data.QR_code.startsWith('data:image/')) {
                return data.QR_code;
            } else {
                return `data:image/png;base64,${data.QR_code}`;
            }
        }
        return null;
    },

    processCompanyData(data) {
        const company = data.company || data.headerData?.company || {};
        
        return {
            ...company,
            // Asegurar que tenga datos mínimos
            name: company.name || 'EMPRESA NO CONFIGURADA',
            vat: company.vat || 'RNC NO CONFIGURADO',
            street: company.street || company.company_address || 'DIRECCIÓN NO CONFIGURADA',
            phone: company.phone || '',
            email: company.email || '',
            website: company.website || '',
            l10n_do_ecf_issuer: company.l10n_do_ecf_issuer || false
        };
    },

    processDGIIStatus(data) {
        if (data.l10n_do_dgii_commercial_approval === true) {
            return {
                status: 'APROBADO',
                color: '#28a745',
                icon: '✅'
            };
        } else if (data.l10n_do_dgii_commercial_approval === false) {
            return {
                status: 'PENDIENTE',
                color: '#ffc107',
                icon: '⚠️'
            };
        } else if (data.l10n_do_ecf_security_code) {
            return {
                status: 'ENVIADO',
                color: '#17a2b8', 
                icon: '📤'
            };
        }
        return null;
    },

    // Método helper para el template
    formatDominicanDate(dateStr) {
        if (!dateStr) return '';
        
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('es-DO', {
                day: '2-digit',
                month: '2-digit', 
                year: 'numeric'
            });
        } catch (e) {
            return dateStr;
        }
    },

    // Método helper para formatear fecha y hora según DGII
    formatDGIIDateTime(dateStr) {
        if (!dateStr) return '';
        
        try {
            const date = new Date(dateStr);
            const day = date.getDate().toString().padStart(2, '0');
            const month = (date.getMonth() + 1).toString().padStart(2, '0');
            const year = date.getFullYear();
            let hours = date.getHours();
            const minutes = date.getMinutes().toString().padStart(2, '0');
            const seconds = date.getSeconds().toString().padStart(2, '0');

            // Formato 12 horas con AM/PM dominicano
            const ampm = hours >= 12 ? 'p. m.' : 'a. m.';
            hours = hours % 12;
            hours = hours ? hours : 12;
            const hoursFormatted = hours.toString().padStart(2, '0');

            return `${day}/${month}/${year} ${hoursFormatted}:${minutes}:${seconds} ${ampm}`;
        } catch (e) {
            return dateStr;
        }
    }
});

console.log('[L10N_DO_POS] OrderReceiptDominican patch applied successfully');
