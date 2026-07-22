/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

console.log('[L10N_DO_POS] models.js loaded - starting patches');

patch(PosStore.prototype, {
    async setup() {
        console.log('[L10N_DO_POS] PosStore setup() called - BEGIN');
        console.log('[L10N_DO_POS] Arguments received:', arguments.length);
        try {
            await super.setup(...arguments);
            console.log('[L10N_DO_POS] super.setup() completed successfully');
            console.log('[L10N_DO_POS] this.config exists:', !!this.config);
            
            this.payer_types_selection = {
                'taxpayer': 'Contribuyente',
                'non_payer': 'Cliente de Consumo',
                'nonprofit': 'Sin fines de lucro',
                'special': 'Exento',
                'governmental': 'Gubernamental',
                'foreigner': 'Extranjero',
            }
            console.log('[L10N_DO_POS] payer_types_selection initialized');
            
            // Verificar integración con l10n_do_accounting
            this.check_l10n_do_accounting_integration();
            
            // Aplicar configuración dominicana al orden actual
            this.apply_l10n_do_configuration();
            
        } catch(e) {
            console.error('[L10N_DO_POS] Error in PosStore setup():', e);
            throw e;
        }
        console.log('[L10N_DO_POS] PosStore setup() - END');
    },
    
    // Verificar integración con l10n_do_accounting
    check_l10n_do_accounting_integration() {
        console.log('[L10N_DO_POS] Checking l10n_do_accounting integration...');

        // Verificar campo correcto: l10n_do_fiscal_sequence_id
        if (this.config && this.config.l10n_do_fiscal_sequence_id) {
            console.log('[L10N_DO_POS] ✅ l10n_do_accounting integration detected');
            console.log('[L10N_DO_POS] Fiscal Sequence ID:', this.config.l10n_do_fiscal_sequence_id);
        } else {
            console.log('[L10N_DO_POS] ℹ️ l10n_do_fiscal_sequence_id not configured (optional for non-fiscal POS)');
        }
    },
    
    // Aplicar configuración dominicana cuando se complete la carga del POS
    apply_l10n_do_configuration() {
        console.log('[L10N_DO_POS] Applying Dominican Republic configuration to current order');

        // Aplicar a la orden actual si existe
        // Autor: Arturo Diaz Lora - 2026-01-10 - Cambio de get_order() a getOrder() para Odoo 19
        let currentOrder = this.getOrder();
        if (currentOrder && currentOrder.apply_l10n_do_config) {
            currentOrder.apply_l10n_do_config(this);
        }
    },
    
    // Override createNewOrder para aplicar configuración automáticamente
    createNewOrder() {
        console.log('[L10N_DO_POS] Creating new order with Dominican Republic configuration');
        let order = super.createNewOrder(...arguments);
        
        // Aplicar configuración dominicana a la nueva orden
        if (order && order.apply_l10n_do_config) {
            order.apply_l10n_do_config(this);
        }
        
        return order;
    },
    // Override syncAllOrders para capturar datos fiscales después de sincronización
    async syncAllOrders(options = {}) {
        console.log('[L10N_DO_POS] syncAllOrders called - Odoo 18 approach');

        try {
            // Llamar al método original de syncAllOrders
            const result = await super.syncAllOrders(options);

            // Procesar órdenes sincronizadas para obtener datos fiscales dominicanos
            await this.processSyncedOrdersForDominicanData();

            return result;

        } catch (error) {
            // Autor: Arturo Diaz Lora
            // Fecha: 2025-11-26 20:30
            // Razón: Mejorar log de error para mostrar mensaje real (está en error.data.message)
            const realMessage = error?.data?.message || error?.message || 'Error desconocido';
            const exceptionType = error?.exceptionName || error?.data?.name || 'Unknown';
            console.error('[L10N_DO_POS] ❌ Error en syncAllOrders:', {
                tipoExcepcion: exceptionType,
                mensajeReal: realMessage,
                errorCompleto: error
            });
            throw error;
        }
    },

    // Procesar órdenes sincronizadas para obtener datos fiscales dominicanos
    async processSyncedOrdersForDominicanData() {
        console.log('[L10N_DO_POS] Processing synced orders for Dominican fiscal data...');

        // Autor: Arturo Diaz Lora - 2026-01-10 - Acceso defensivo a orden para evitar errores de proxy/fecha en Odoo 19
        let currentOrder;
        let orderName;
        let isFinalized;

        try {
            currentOrder = this.getOrder();
            if (!currentOrder) {
                console.log('[L10N_DO_POS] No current order to process');
                return;
            }

            // Acceder propiedades de forma segura (pueden triggear conversión de fechas)
            try {
                orderName = currentOrder.name;
                isFinalized = currentOrder.finalized || currentOrder.state === 'paid';
            } catch (propError) {
                console.warn('[L10N_DO_POS] Error accessing order properties:', propError.message);
                // Intentar continuar con lo que tengamos
                orderName = currentOrder.name || 'Unknown';
                isFinalized = true; // Asumir finalizado si ya llegamos aquí
            }

            if (!isFinalized) {
                console.log('[L10N_DO_POS] Order not finalized yet');
                return;
            }
        } catch (orderError) {
            console.warn('[L10N_DO_POS] Error getting order, skipping fiscal data processing:', orderError.message);
            return;
        }

        console.log('[L10N_DO_POS] Processing finalized order:', orderName);

        try {
            // USAR EL CONTEXTO CORRECTO DEL POS STORE PARA RPC
            console.log('[L10N_DO_POS] 🔍 Verificando contexto POS Store para RPC...');
            console.log('[L10N_DO_POS] - this.data exists:', !!this.data);
            console.log('[L10N_DO_POS] - this.data.call exists:', !!(this.data && this.data.call));
            
            if (this.data && this.data.call) {
                console.log('[L10N_DO_POS] ✅ Usando this.data.call para obtener datos fiscales');
                
                // OPCIÓN 1: Consultar datos optimizados con reintento para QR
                let fiscalData;
                let retryCount = 0;
                const maxRetries = 10; // Máximo 10 intentos (50 segundos total)

                try {
                    do {
                        fiscalData = await this.data.call(
                            'pos.order',
                            'get_fiscal_data_for_receipt',
                            [orderName]
                        );
                        console.log(`[L10N_DO_POS] ✅ get_fiscal_data_for_receipt result (attempt ${retryCount + 1}):`, fiscalData);

                        // LOG DETALLADO DE DATOS FISCALES
                        console.log('[L10N_DO_POS] 📊 Datos fiscales recibidos:', {
                            tiene_ncf: !!(fiscalData?.ncf || fiscalData?.l10n_latam_document_number),
                            ncf_valor: fiscalData?.ncf || fiscalData?.l10n_latam_document_number || 'NO',
                            es_ecf: fiscalData?.is_ecf_invoice,
                            tiene_codigo_seguridad: !!fiscalData?.l10n_do_ecf_security_code,
                            codigo_seguridad: fiscalData?.l10n_do_ecf_security_code || 'NO',
                            tiene_QR_code_binario: !!fiscalData?.QR_code,
                            QR_code_length: fiscalData?.QR_code ? fiscalData.QR_code.length : 0,
                            tiene_qr_code_img: !!fiscalData?.qr_code_img,
                            qr_code_img_preview: fiscalData?.qr_code_img ? fiscalData.qr_code_img.substring(0, 30) + '...' : 'NO',
                            tiene_factura: fiscalData?.has_invoice,
                            estado_factura: fiscalData?.invoice_state
                        });

                        // Si tenemos datos y QR, ya está listo
                        if (fiscalData && (fiscalData.qr_code_img || fiscalData.QR_code)) {
                            console.log('[L10N_DO_POS] 🎯 ✅ QR CODE DISPONIBLE - Datos completos!');
                            console.log('[L10N_DO_POS] 📦 QR listo para mostrar en recibo');
                            break;
                        }

                        // NUEVO: Verificar si la factura es electrónica antes de reintentar
                        if (fiscalData && fiscalData.is_ecf_invoice === false) {
                            console.log('[L10N_DO_POS] ✅ Factura NO electrónica detectada - sin necesidad de QR, continuando sin reintentos');
                            break;
                        }

                        // Si tenemos NCF pero no QR y ES factura electrónica, esperar y reintentar
                        if (fiscalData && fiscalData.ncf && fiscalData.is_ecf_invoice && retryCount < maxRetries) {
                            console.log(`[L10N_DO_POS] ⏳ ❌ QR NO DISPONIBLE AÚN - Factura electrónica detectada`);
                            console.log(`[L10N_DO_POS] 🔄 Reintentando en 5 segundos... (intento ${retryCount + 1}/${maxRetries})`);
                            console.log(`[L10N_DO_POS] 📝 NCF: ${fiscalData.ncf}, Código Seg: ${fiscalData.l10n_do_ecf_security_code || 'NO'}`);
                            await new Promise(resolve => setTimeout(resolve, 5000)); // Esperar 5 segundos
                            retryCount++;
                        } else {
                            if (!fiscalData?.ncf) {
                                console.log('[L10N_DO_POS] ⚠️ Sin NCF - deteniendo reintentos');
                            } else if (!fiscalData?.is_ecf_invoice) {
                                console.log('[L10N_DO_POS] ℹ️ NO es factura electrónica - deteniendo reintentos');
                            }
                            break; // Sin NCF, no es ECF, o máximo de reintentos alcanzado
                        }
                    } while (retryCount < maxRetries);

                    if (retryCount >= maxRetries) {
                        console.error('[L10N_DO_POS] ❌❌❌ MÁXIMO DE REINTENTOS ALCANZADO ❌❌❌');
                        console.error('[L10N_DO_POS] 🚨 QR NO está disponible después de 50 segundos');
                        console.error('[L10N_DO_POS] 📋 Datos finales:', fiscalData);
                        console.error('[L10N_DO_POS] 💡 POSIBLES CAUSAS:');
                        console.error('[L10N_DO_POS]    1. La factura aún no se generó en el backend');
                        console.error('[L10N_DO_POS]    2. El QR no se está guardando en account.move.qr_code');
                        console.error('[L10N_DO_POS]    3. Error en la generación del QR');
                        console.error('[L10N_DO_POS] 🔍 REVISAR LOGS DEL SERVIDOR ODOO');
                    }
                } catch (e) {
                    console.log('[L10N_DO_POS] ⚠️ get_fiscal_data_for_receipt failed, trying search_read:', e.message);
                }
                
                // OPCIÓN 2: Si no hay datos optimizados, búsqueda directa
                if (!fiscalData || Object.keys(fiscalData).length === 0) {
                    console.log('[L10N_DO_POS] ⚠️ Intentando búsqueda directa en pos.order...');
                    
                    const orderData = await this.data.call(
                        'pos.order',
                        'search_read',
                        [[['pos_reference', '=', orderName]]],
                        {
                            fields: [
                                'l10n_latam_document_number',
                                'l10n_latam_document_type_id',
                                'l10n_do_ncf_expiration_date',
                                'origin_ncf',
                                'l10n_do_ecf_security_code',
                                'l10n_do_ecf_sign_date',
                                'QR_code',
                                'l10n_do_dgii_commercial_approval'
                            ]
                        }
                    );
                    
                    if (orderData && orderData.length > 0) {
                        fiscalData = orderData[0];
                        console.log('[L10N_DO_POS] ✅ Datos fiscales obtenidos via search_read:', fiscalData);
                    }
                }
                
                // APLICAR DATOS FISCALES Y EDI A LA ORDEN
                if (fiscalData && (fiscalData.ncf || fiscalData.l10n_latam_document_number)) {
                    console.log('[L10N_DO_POS] ✅ Aplicando datos fiscales y EDI a la orden...');

                    // Actualizar datos fiscales básicos
                    if (fiscalData.ncf || fiscalData.l10n_latam_document_number) {
                        currentOrder.ncf = fiscalData.ncf || fiscalData.l10n_latam_document_number;
                        currentOrder.l10n_latam_document_number = fiscalData.l10n_latam_document_number || fiscalData.ncf;
                        console.log('[L10N_DO_POS] ✅ NCF aplicado:', currentOrder.ncf);
                    }
                    
                    if (fiscalData.l10n_latam_document_type_id) {
                        currentOrder.l10n_latam_document_type_id = fiscalData.l10n_latam_document_type_id;
                    }
                    
                    if (fiscalData.l10n_do_ncf_expiration_date) {
                        currentOrder.l10n_do_ncf_expiration_date = fiscalData.l10n_do_ncf_expiration_date;
                    }
                    
                    if (fiscalData.origin_ncf) {
                        currentOrder.l10n_do_origin_ncf = fiscalData.origin_ncf;
                    }

                    // **DATOS EDI CRUCIALES - QR CODE Y SEGURIDAD**
                    if (fiscalData.l10n_do_ecf_security_code) {
                        currentOrder.l10n_do_ecf_security_code = fiscalData.l10n_do_ecf_security_code;
                        console.log('[L10N_DO_POS] ✅ Código de seguridad EDI aplicado:', fiscalData.l10n_do_ecf_security_code);
                    }
                    
                    if (fiscalData.l10n_do_ecf_sign_date) {
                        currentOrder.l10n_do_ecf_sign_date = fiscalData.l10n_do_ecf_sign_date;
                        console.log('[L10N_DO_POS] ✅ Fecha firma EDI aplicada:', fiscalData.l10n_do_ecf_sign_date);
                    }
                    
                    if (fiscalData.QR_code) {
                        currentOrder.QR_code = fiscalData.QR_code;
                        console.log('[L10N_DO_POS] ✅✅✅ QR CODE BINARIO ASIGNADO A LA ORDEN ✅✅✅');
                        console.log('[L10N_DO_POS] 📦 Tamaño QR binario:', (fiscalData.QR_code || '').length, 'bytes');
                        console.log('[L10N_DO_POS] 📝 Preview (primeros 50 chars):', fiscalData.QR_code.substring(0, 50));
                    } else {
                        console.warn('[L10N_DO_POS] ⚠️⚠️⚠️ QR CODE NO DISPONIBLE EN fiscalData ⚠️⚠️⚠️');
                        console.warn('[L10N_DO_POS] 🔍 Verificar si qr_code se generó en account.move');
                    }

                    if (fiscalData.qr_code_img) {
                        currentOrder.qr_code_img = fiscalData.qr_code_img;
                        console.log('[L10N_DO_POS] ✅✅✅ QR CODE IMG (DATA URI) ASIGNADO ✅✅✅');
                        console.log('[L10N_DO_POS] 🖼️ Preview:', fiscalData.qr_code_img.substring(0, 50) + '...');
                    }
                    
                    if (fiscalData.l10n_do_dgii_commercial_approval !== undefined) {
                        currentOrder.l10n_do_dgii_commercial_approval = fiscalData.l10n_do_dgii_commercial_approval;
                        console.log('[L10N_DO_POS] ✅ Estado DGII aplicado:', fiscalData.l10n_do_dgii_commercial_approval);
                    }
                    
                    // Marcar como orden con datos EDI cargados
                    currentOrder._edi_data_loaded = true;

                    console.log('[L10N_DO_POS] ✅ Orden actualizada completamente con datos fiscales y EDI');
                } else {
                    console.log('[L10N_DO_POS] ⚠️ No se encontraron datos fiscales para la orden');
                }
                
            } else {
                console.log('[L10N_DO_POS] ❌ No hay acceso a this.data.call en PosStore');
            }
        } catch (error) {
            console.error('[L10N_DO_POS] Error processing Dominican fiscal data:', error);
        }
    },

    // Método para consultar datos fiscales dominicanos (Odoo 18 optimizado)
    async queryDominicanFiscalData(orderName) {
        console.log('[L10N_DO_POS] Querying Dominican fiscal data for order:', orderName);

        try {
            // OPCIÓN 1: Usar método optimizado específico
            const fiscalData = await this.data.call(
                'pos.order',
                'get_fiscal_data_for_receipt',
                [orderName]
            );
            
            if (fiscalData && Object.keys(fiscalData).length > 0) {
                console.log('[L10N_DO_POS] ✅ Fiscal data obtained via optimized method:', fiscalData);
                console.log('[L10N_DO_POS] 🔍 QR Code debug - QR_code:', !!fiscalData.QR_code, typeof fiscalData.QR_code);
                console.log('[L10N_DO_POS] 🔍 QR Code debug - qr_code_img:', !!fiscalData.qr_code_img);
                console.log('[L10N_DO_POS] 🔍 QR Code debug - l10n_do_ecf_qr_code:', !!fiscalData.l10n_do_ecf_qr_code);
                
                return {
                    ncf: fiscalData.ncf,
                    l10n_latam_document_number: fiscalData.l10n_latam_document_number,
                    l10n_latam_document_type_id: this.cleanDocumentType(fiscalData.l10n_latam_document_type_id),
                    l10n_do_ncf_expiration_date: fiscalData.l10n_do_ncf_expiration_date,
                    l10n_do_origin_ncf: fiscalData.l10n_do_origin_ncf,
                    l10n_do_ecf_security_code: fiscalData.l10n_do_ecf_security_code,
                    l10n_do_ecf_sign_date: fiscalData.l10n_do_ecf_sign_date,
                    QR_code: fiscalData.QR_code,
                    qr_code_img: fiscalData.qr_code_img,
                    l10n_do_dgii_commercial_approval: fiscalData.l10n_do_dgii_commercial_approval,
                    is_ecf_invoice: fiscalData.is_ecf_invoice
                };
            }
            
            console.log('[L10N_DO_POS] ⚠️ Optimized method returned empty, falling back to search_read');
            
            // OPCIÓN 2: Fallback al método original
            const orders = await this.data.call(
                'pos.order',
                'search_read',
                [[['pos_reference', '=', orderName]]],
                {
                    fields: [
                        'id',
                        'l10n_latam_document_number',
                        'l10n_latam_document_type_id',
                        'l10n_do_ncf_expiration_date',
                        'origin_ncf',  // Campo correcto en pos.order
                        'account_move',
                        // Campos EDI para facturación electrónica
                        'l10n_do_ecf_security_code',
                        'l10n_do_ecf_sign_date',
                        'QR_code',
                        'l10n_do_dgii_commercial_approval'
                    ]
                }
            );

            if (orders.length > 0) {
                const order = orders[0];
                console.log('[L10N_DO_POS] Order found in backend:', order);

                // Si hay NCF directamente en pos.order
                if (order.l10n_latam_document_number) {
                    return {
                        ncf: order.l10n_latam_document_number,
                        l10n_latam_document_number: order.l10n_latam_document_number,
                        l10n_latam_document_type_id: this.cleanDocumentType(order.l10n_latam_document_type_id),
                        l10n_do_ncf_expiration_date: order.l10n_do_ncf_expiration_date,
                        l10n_do_origin_ncf: order.origin_ncf,  // Mapear del campo correcto
                        // Incluir campos EDI si están disponibles
                        l10n_do_ecf_security_code: order.l10n_do_ecf_security_code,
                        l10n_do_ecf_sign_date: order.l10n_do_ecf_sign_date,
                        QR_code: order.QR_code,
                        l10n_do_dgii_commercial_approval: order.l10n_do_dgii_commercial_approval
                    };
                }

                // Si no hay NCF en pos.order, consultar account.move
                if (order.account_move && order.account_move[0]) {
                    const invoiceData = await this.data.call(
                        'account.move',
                        'search_read',
                        [[['id', '=', order.account_move[0]]]],
                        {
                            fields: [
                                'l10n_latam_document_number',
                                'l10n_latam_document_type_id',
                                'l10n_do_ncf_expiration_date',
                                'l10n_do_origin_ncf',
                                // Campos EDI para facturación electrónica
                                'l10n_do_ecf_security_code',
                                'l10n_do_ecf_sign_date',
                                'QR_code',
                                'l10n_do_dgii_commercial_approval'
                            ]
                        }
                    );

                    if (invoiceData.length > 0 && invoiceData[0].l10n_latam_document_number) {
                        return {
                            ncf: invoiceData[0].l10n_latam_document_number,
                            l10n_latam_document_number: invoiceData[0].l10n_latam_document_number,
                            l10n_latam_document_type_id: this.cleanDocumentType(invoiceData[0].l10n_latam_document_type_id),
                            l10n_do_ncf_expiration_date: invoiceData[0].l10n_do_ncf_expiration_date,
                            l10n_do_origin_ncf: invoiceData[0].l10n_do_origin_ncf,
                            // Incluir campos EDI desde account.move
                            l10n_do_ecf_security_code: invoiceData[0].l10n_do_ecf_security_code,
                            l10n_do_ecf_sign_date: invoiceData[0].l10n_do_ecf_sign_date,
                            QR_code: invoiceData[0].QR_code,
                            l10n_do_dgii_commercial_approval: invoiceData[0].l10n_do_dgii_commercial_approval
                        };
                    }
                }
            }

            return null;

        } catch (error) {
            console.error('[L10N_DO_POS] Error querying Dominican fiscal data:', error);
            return null;
        }
    },

    // Método para limpiar el tipo de documento
    cleanDocumentType(documentType) {
        if (!documentType) return '';

        // Si es un array con nombre, extraer el nombre
        if (Array.isArray(documentType) && documentType.length > 1) {
            documentType = documentType[1];
        }

        // Convertir a string y limpiar
        const docTypeStr = String(documentType).trim();

        // Mapear tipos comunes a formatos más limpios
        const typeMap = {
            'Factura de Consumo': 'DE CONSUMO',
            'Factura con valor fiscal de Consumo': 'DE CONSUMO',
            'Factura de Crédito Fiscal': 'DE CRÉDITO FISCAL',
            'Factura con valor fiscal de Crédito': 'DE CRÉDITO FISCAL',
            'Nota de Débito': 'NOTA DE DÉBITO',
            'Nota de Crédito': 'NOTA DE CRÉDITO'
        };

        // Buscar mapeo exacto
        if (typeMap[docTypeStr]) {
            return typeMap[docTypeStr];
        }

        // Limpiar automáticamente patrones comunes
        return docTypeStr
            .replace(/^Factura\s+(de\s+|con valor fiscal de\s+)?/i, '')
            .replace(/^Nota\s+de\s+/i, 'NOTA DE ')
            .toUpperCase()
            .trim();
    }
});

patch(PosOrder.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        console.log('[L10N_DO_POS] PosOrder setup() called, this.pos exists:', !!this.pos);

        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-22 23:30
        // Razón: Inicializar campos dominicanos para notas de crédito
        // Estos campos se setean desde TicketScreen cuando se hace refund
        this.ncf = this.ncf || false;
        this.origin_ncf = this.origin_ncf || false;
        this.l10n_do_ecf_modification_code = this.l10n_do_ecf_modification_code || false;
        this.l10n_latam_document_type_id = this.l10n_latam_document_type_id || false;

        // Verificar que this.pos y this.pos.config estén disponibles
        if (this.pos && this.pos.config) {
            this.apply_l10n_do_config();
        } else {
            console.log('[L10N_DO_POS] PosOrder setup() - pos.config not available yet, skipping config-dependent logic');
        }
    },
    
    // Nueva función para aplicar configuración dominicana
    apply_l10n_do_config(pos = null) {
        console.log('[L10N_DO_POS] Applying Dominican Republic POS configuration');
        
        // Use passed pos parameter or this.pos
        let posStore = pos || this.pos;
        
        if (!posStore || !posStore.config) {
            console.log('[L10N_DO_POS] POS config not available, skipping Dominican configuration');
            return;
        }
        
        // 1. Solo facturación: Force to_invoice = true
        if (posStore.config.only_invoice) {
            this.to_invoice = true;
            console.log('[L10N_DO_POS] Only invoicing enabled - to_invoice set to true');
        }

        // 2. Cliente por defecto: Set default partner if no partner selected
        if (!this.getPartner()) {
            const pos_default_partner = posStore.config.default_partner_id;
            // En Odoo 19 los M2O en pos.config son records, no [id, name].
            const partnerId = pos_default_partner?.id ?? (Array.isArray(pos_default_partner) ? pos_default_partner[0] : pos_default_partner);
            if (partnerId && posStore.models?.["res.partner"]) {
                const client = posStore.models["res.partner"].get(partnerId);
                if (client) {
                    // Odoo 19 renombró set_partner → setPartner. Mantener fallback.
                    if (typeof this.setPartner === "function") {
                        this.setPartner(client);
                    } else if (typeof this.set_partner === "function") {
                        this.set_partner(client);
                    } else {
                        this.partner_id = client;
                    }
                    console.log('[L10N_DO_POS] Default partner set:', client.name);
                }
            }
        }
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.ncf = json.ncf;
        this.l10n_latam_document_type_id = json.l10n_latam_document_type_id;
        this.origin_ncf = json.origin_ncf;
        this.l10n_do_ecf_modification_code = json.l10n_do_ecf_modification_code;  // Autor: Arturo Diaz Lora - 2025-11-23 - Faltaba restaurar campo
        this.to_invoice = json.to_invoice;
    },
    serialize(options = {}) {
        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-23 14:50 (actualizado 15:20)
        // Razón: En Odoo 18, serialize() reemplaza export_as_JSON() para transmisión de datos al backend.
        //        Los campos fiscales dominicanos deben agregarse en serialize() para que se incluyan
        //        en el JSON que se envía al servidor vía sync_from_ui().
        //
        //        CRÍTICO: Sin este override, l10n_do_ecf_modification_code NO llega al backend y las
        //        notas de crédito se crean sin código de modificación, siendo rechazadas por DGII.
        //
        //        ACTUALIZACIÓN 15:20: NO borrar pending_refund_fiscal_data - serialize() se llama múltiples
        //        veces y necesitamos que los datos persistan hasta que la orden se finalice.
        //
        //        Referencia: /odoo18/2025-11-23_14-45_SOLUCION_CORRECTA_serialize_vs_export_as_json.md
        console.log('[L10N_DO_POS] 🔥 SERIALIZE LLAMADO (Odoo 18) 🔥');
        console.log('[L10N_DO_POS] Order name:', this.name);
        console.log('[L10N_DO_POS] Order ID:', this.id);

        // Llamar al método padre para obtener serialización base
        const json = super.serialize(options);

        // Verificar si hay datos fiscales pendientes (de un reembolso)
        // IMPORTANTE: NO borramos pending_refund_fiscal_data porque serialize() se llama múltiples veces
        if (this.pos && this.pos.pending_refund_fiscal_data) {
            console.log('[L10N_DO_POS] 🎯 DATOS FISCALES PENDIENTES DETECTADOS - Aplicando...');
            const pending = this.pos.pending_refund_fiscal_data;
            console.log('[L10N_DO_POS] pending data:', pending);

            // Aplicar a la orden actual SOLO si aún no se han aplicado
            // Verificamos que sea false, undefined, null o string vacío
            if (!this.l10n_do_ecf_modification_code || this.l10n_do_ecf_modification_code === false || this.l10n_do_ecf_modification_code === '') {
                this.l10n_do_ecf_modification_code = pending.modification_code;
                this.origin_ncf = pending.origin_ncf;
                this.ncf = pending.origin_ncf;
                console.log('[L10N_DO_POS] ✅ Datos fiscales aplicados a orden por primera vez');
                console.log('[L10N_DO_POS]    modification_code:', this.l10n_do_ecf_modification_code);
            } else {
                console.log('[L10N_DO_POS] ℹ️ Datos fiscales ya aplicados anteriormente');
                console.log('[L10N_DO_POS]    modification_code actual:', this.l10n_do_ecf_modification_code);
            }
        }

        // SIEMPRE agregar campos fiscales dominicanos al JSON
        json.ncf = this.ncf;
        json.l10n_latam_document_type_id = this.l10n_latam_document_type_id;
        json.origin_ncf = this.origin_ncf;
        json.l10n_do_ecf_modification_code = this.l10n_do_ecf_modification_code;
        json.to_invoice = this.is_to_invoice();

        console.log('[L10N_DO_POS] 📋 SERIALIZE - Campos fiscales agregados al JSON:');
        console.log('[L10N_DO_POS]   - ncf:', json.ncf);
        console.log('[L10N_DO_POS]   - origin_ncf:', json.origin_ncf);
        console.log('[L10N_DO_POS]   - l10n_do_ecf_modification_code:', json.l10n_do_ecf_modification_code);
        console.log('[L10N_DO_POS]   - to_invoice:', json.to_invoice);
        console.log('[L10N_DO_POS] ✅ SERIALIZE COMPLETADO');

        return json;
    },
    export_as_JSON() {
        // Autor: Arturo Diaz Lora
        // Fecha: 2025-11-23 08:15 (actualizado)
        // Razón: Mejorada lógica de datos fiscales pendientes - ahora verifica pending_refund_fiscal_data
        //        SIN condición de amount_total para capturar datos antes de calcular montos negativos
        console.log('[L10N_DO_POS] 🔥🔥🔥 EXPORT_AS_JSON LLAMADO 🔥🔥🔥');
        console.log('[L10N_DO_POS] Order name:', this.name);
        console.log('[L10N_DO_POS] Order amount_total:', this.amount_total);
        console.log('[L10N_DO_POS] Order refunded_order_id:', this.refunded_order_id);
        console.log('[L10N_DO_POS] this.l10n_do_ecf_modification_code ANTES:', this.l10n_do_ecf_modification_code);
        console.log('[L10N_DO_POS] pending_refund_fiscal_data exists:', !!(this.pos && this.pos.pending_refund_fiscal_data));

        const json = super.export_as_JSON(...arguments);

        // Verificar si hay datos fiscales pendientes (de un reembolso)
        // NOTA: NO verificamos amount_total < 0 porque puede no estar calculado aún en este punto
        if (this.pos && this.pos.pending_refund_fiscal_data) {
            console.log('[L10N_DO_POS] 🎯 DATOS FISCALES PENDIENTES DETECTADOS - Aplicando...');
            const pending = this.pos.pending_refund_fiscal_data;
            console.log('[L10N_DO_POS] pending data:', pending);

            // Aplicar TANTO a this (orden) como a json (payload)
            this.l10n_do_ecf_modification_code = pending.modification_code;
            this.origin_ncf = pending.origin_ncf;
            this.ncf = pending.origin_ncf;

            console.log('[L10N_DO_POS] ✅ Datos fiscales aplicados a this (orden):');
            console.log('[L10N_DO_POS]   - modification_code:', pending.modification_code);
            console.log('[L10N_DO_POS]   - origin_ncf:', pending.origin_ncf);

            // Limpiar los datos pendientes
            delete this.pos.pending_refund_fiscal_data;
            console.log('[L10N_DO_POS] ✅ pending_refund_fiscal_data limpiado');
        }

        // SIEMPRE agregar campos dominicanos al JSON, incluso si son undefined/false
        // El backend usará los valores que existan
        json.ncf = this.ncf;
        json.l10n_latam_document_type_id = this.l10n_latam_document_type_id;
        json.origin_ncf = this.origin_ncf;
        json.to_invoice = this.is_to_invoice();
        json.l10n_do_ecf_modification_code = this.l10n_do_ecf_modification_code;

        console.log('[L10N_DO_POS] 📋 DATOS FINALES PARA BACKEND (JSON):');
        console.log('[L10N_DO_POS]   - json.ncf:', json.ncf);
        console.log('[L10N_DO_POS]   - json.origin_ncf:', json.origin_ncf);
        console.log('[L10N_DO_POS]   - json.l10n_do_ecf_modification_code:', json.l10n_do_ecf_modification_code);
        console.log('[L10N_DO_POS]   - json.to_invoice:', json.to_invoice);
        console.log('[L10N_DO_POS]   - json.refunded_order_id:', json.refunded_order_id);
        console.log('[L10N_DO_POS] 🔥🔥🔥 EXPORT_AS_JSON COMPLETADO 🔥🔥🔥');
        console.log('[L10N_DO_POS] ==================================================');

        return json;
    },
    async export_for_printing() {
        let self = this;
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] EXPORT_FOR_PRINTING INICIADO - CONSULTA FISCAL EN TIEMPO REAL');
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] Order name:', self.name);
        console.log('[L10N_DO_POS] Order finalized:', self.finalized);
        console.log('[L10N_DO_POS] Order to_invoice:', self.to_invoice);

        let result = super.export_for_printing(...arguments);

        console.log('[L10N_DO_POS] ✅ SUPER export_for_printing resultado inicial:', result);

        // DEBUG HEADER DATA INICIAL
        console.log('[L10N_DO_POS] 🏢 HeaderData en result:', !!result.headerData);
        if (result.headerData) {
            console.log('[L10N_DO_POS] 🏢 Company en headerData:', !!result.headerData.company);
            if (result.headerData.company) {
                console.log('[L10N_DO_POS] 🏢 Company name inicial:', result.headerData.company.name);
            }
        }

        // 📅 FORMATEAR FECHA Y HORA SEGÚN DGII
        const now = new Date();
        const day = now.getDate().toString().padStart(2, '0');
        const month = (now.getMonth() + 1).toString().padStart(2, '0');
        const year = now.getFullYear();
        let hours = now.getHours();
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');

        // Formato 12 horas con AM/PM dominicano
        const ampm = hours >= 12 ? 'p. m.' : 'a. m.';
        hours = hours % 12;
        hours = hours ? hours : 12; // la hora '0' debe ser '12'
        const hoursFormatted = hours.toString().padStart(2, '0');

        // Formato DGII: "14/09/2025 05:27:11 a. m."
        result.date = `${day}/${month}/${year} ${hoursFormatted}:${minutes}:${seconds} ${ampm}`;
        console.log('[L10N_DO_POS] 📅 Fecha DGII formateada:', result.date);

        // ⚡ TRANSFERENCIA INMEDIATA DE DATOS DISPONIBLES
        console.log('[L10N_DO_POS] 📋 DATOS NCF ANTES DE PROCESAR:');
        console.log('[L10N_DO_POS] - result.ncf:', result.ncf);
        console.log('[L10N_DO_POS] - result.l10n_latam_document_number:', result.l10n_latam_document_number);
        console.log('[L10N_DO_POS] - result.l10n_latam_document_type_id:', result.l10n_latam_document_type_id);
        console.log('[L10N_DO_POS] - self.l10n_latam_document_number:', self.l10n_latam_document_number);
        console.log('[L10N_DO_POS] - self.ncf:', self.ncf);
        
        // 🔥 TRANSFERIR DATOS DISPONIBLES INMEDIATAMENTE
        if (self.l10n_latam_document_number) {
            result.l10n_latam_document_number = self.l10n_latam_document_number;
            result.ncf = self.l10n_latam_document_number;
            console.log('[L10N_DO_POS] ⚡ NCF transferido inmediatamente:', self.l10n_latam_document_number);
        }
        
        if (self.l10n_latam_document_type_id) {
            result.l10n_latam_document_type_id = Array.isArray(self.l10n_latam_document_type_id) ? 
                self.l10n_latam_document_type_id[1] : self.l10n_latam_document_type_id;
            console.log('[L10N_DO_POS] ⚡ Tipo documento transferido:', result.l10n_latam_document_type_id);
        }
        
        // Transferir otros campos disponibles
        if (self.l10n_do_ncf_expiration_date) {
            // Formatear fecha para mostrar
            try {
                const expirationDate = new Date(self.l10n_do_ncf_expiration_date);
                result.l10n_do_ncf_expiration_date = expirationDate.toLocaleDateString('es-DO', {
                    day: '2-digit',
                    month: '2-digit', 
                    year: 'numeric'
                });
                console.log('[L10N_DO_POS] ⚡ Vencimiento NCF transferido y formateado:', result.l10n_do_ncf_expiration_date);
            } catch (e) {
                result.l10n_do_ncf_expiration_date = self.l10n_do_ncf_expiration_date;
                console.log('[L10N_DO_POS] ⚡ Vencimiento NCF transferido sin formatear:', result.l10n_do_ncf_expiration_date);
            }
        } else {
            console.log('[L10N_DO_POS] ⚠️ Vencimiento NCF no disponible en self');
        }
        
        if (self.l10n_do_ecf_security_code) {
            result.l10n_do_ecf_security_code = self.l10n_do_ecf_security_code;
        }
        
        if (self.l10n_do_ecf_sign_date) {
            result.l10n_do_ecf_sign_date = self.l10n_do_ecf_sign_date;
        }
        
        if (self.QR_code) {
            result.QR_code = self.QR_code;
            if (typeof self.QR_code === 'string') {
                // Verificar si ya tiene el prefijo data URI
                if (self.QR_code.startsWith('data:image')) {
                    result.qr_code_img = self.QR_code;
                } else {
                    result.qr_code_img = `data:image/png;base64,${self.QR_code}`;
                }
                console.log('[L10N_DO_POS] ⚡ QR Code transferido desde self (string):', self.QR_code.substring(0, 50) + '...');
            } else {
                console.log('[L10N_DO_POS] ⚡ QR Code transferido desde self (binary):', typeof self.QR_code);
            }
        } else {
            console.log('[L10N_DO_POS] ⚠️ QR Code no disponible en self');
        }
        
        if (self.l10n_do_dgii_commercial_approval !== undefined) {
            result.l10n_do_dgii_commercial_approval = self.l10n_do_dgii_commercial_approval;
        }

        // ⚡ CONSULTA ACTIVA DE DATOS FISCALES EN TIEMPO REAL
        if (self.to_invoice && self.name) {
            console.log('[L10N_DO_POS] 🔥 CONSULTANDO DATOS FISCALES EN TIEMPO REAL...');

            try {
                // VERIFICAR SI YA TENEMOS DATOS EDI PRE-CARGADOS
                console.log('[L10N_DO_POS] 🔍 Verificando datos EDI pre-cargados en la orden...');
                console.log('[L10N_DO_POS] - self._edi_data_loaded:', !!self._edi_data_loaded);
                console.log('[L10N_DO_POS] - self.QR_code exists:', !!self.QR_code);
                console.log('[L10N_DO_POS] - self.l10n_do_ecf_security_code:', !!self.l10n_do_ecf_security_code);
                console.log('[L10N_DO_POS] - self.l10n_do_ecf_sign_date:', !!self.l10n_do_ecf_sign_date);
                
                // SI YA TENEMOS DATOS EDI PRE-CARGADOS, USARLOS DIRECTAMENTE
                if (self._edi_data_loaded) {
                    console.log('[L10N_DO_POS] ✅ Usando datos EDI pre-cargados desde sincronización');
                    
                    // Transferir datos EDI ya cargados
                    if (self.QR_code) {
                        result.QR_code = self.QR_code;
                        // Verificar si ya tiene el prefijo data URI
                        if (self.QR_code.startsWith('data:image')) {
                            result.qr_code_img = self.QR_code;
                        } else {
                            result.qr_code_img = `data:image/png;base64,${self.QR_code}`;
                        }
                        console.log('[L10N_DO_POS] ✅ QR Code transferido desde datos pre-cargados');
                    }
                    
                    if (self.l10n_do_ecf_security_code) {
                        result.l10n_do_ecf_security_code = self.l10n_do_ecf_security_code;
                    }
                    
                    if (self.l10n_do_ecf_sign_date) {
                        result.l10n_do_ecf_sign_date = self.l10n_do_ecf_sign_date;
                    }
                    
                    if (self.l10n_do_dgii_commercial_approval !== undefined) {
                        result.l10n_do_dgii_commercial_approval = self.l10n_do_dgii_commercial_approval;
                    }
                    
                    console.log('[L10N_DO_POS] ✅ Todos los datos EDI pre-cargados aplicados exitosamente');
                } else {
                    console.log('[L10N_DO_POS] ⚠️ No hay datos EDI pre-cargados, intentando consulta en tiempo real (modo fallback)...');

                    // FALLBACK: Intentar obtener datos en tiempo real
                    console.log('[L10N_DO_POS] - this.pos exists:', !!this.pos);
                    console.log('[L10N_DO_POS] - this.env exists:', !!this.env);
                    console.log('[L10N_DO_POS] - Order finalized:', !!self.finalized);

                    // Solo intentar si tenemos contexto disponible
                    if (this.pos && typeof this.pos.queryDominicanFiscalData === 'function') {
                        console.log('[L10N_DO_POS] ✅ queryDominicanFiscalData disponible como fallback...');

                        // 🔄 REINTENTOS CON DELAY para ventas nuevas que necesitan esperar el procesamiento
                        let fiscalData = null;
                        const maxRetries = 10;
                        const delays = [2000, 3000, 3000, 4000, 4000, 5000, 5000, 6000, 6000, 8000]; // Total hasta 46s

                        for (let attempt = 0; attempt < maxRetries; attempt++) {
                            console.log(`[L10N_DO_POS] 🔄 Intento ${attempt + 1}/${maxRetries} de obtener datos fiscales...`);

                            fiscalData = await this.pos.queryDominicanFiscalData(self.name);

                            // Si obtuvimos QR o código de seguridad, es suficiente
                            if (fiscalData && (fiscalData.QR_code || fiscalData.l10n_do_ecf_security_code)) {
                                console.log(`[L10N_DO_POS] ✅ Datos fiscales obtenidos en intento ${attempt + 1}`);
                                break;
                            }

                            // Si no obtuvimos datos y aún quedan intentos, esperar antes de reintentar
                            if (attempt < maxRetries - 1) {
                                const delayMs = delays[attempt];
                                console.log(`[L10N_DO_POS] ⏳ Esperando ${delayMs}ms antes del siguiente intento...`);
                                await new Promise(resolve => setTimeout(resolve, delayMs));
                            } else {
                                console.log('[L10N_DO_POS] ⚠️ Agotados los reintentos sin obtener datos fiscales');
                            }
                        }

                if (fiscalData) {
                    console.log('[L10N_DO_POS] 🎯 DATOS FISCALES OBTENIDOS:', fiscalData);

                    // Aplicar todos los datos fiscales al resultado
                    if (fiscalData.ncf || fiscalData.l10n_latam_document_number) {
                        const ncf = fiscalData.ncf || fiscalData.l10n_latam_document_number;
                        result.l10n_latam_document_number = ncf;
                        result.ncf = ncf;
                        console.log('[L10N_DO_POS] ✅ NCF aplicado:', ncf);
                    }

                    if (fiscalData.l10n_latam_document_type_id) {
                        result.l10n_latam_document_type_id = fiscalData.l10n_latam_document_type_id;
                        console.log('[L10N_DO_POS] ✅ Tipo documento aplicado:', fiscalData.l10n_latam_document_type_id);
                    }

                    if (fiscalData.l10n_do_ncf_expiration_date) {
                        // Formatear fecha de vencimiento
                        try {
                            const expirationDate = new Date(fiscalData.l10n_do_ncf_expiration_date);
                            result.l10n_do_ncf_expiration_date = expirationDate.toLocaleDateString('es-DO', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric'
                            });
                            console.log('[L10N_DO_POS] ✅ Vencimiento NCF aplicado y formateado:', result.l10n_do_ncf_expiration_date);
                        } catch (e) {
                            result.l10n_do_ncf_expiration_date = fiscalData.l10n_do_ncf_expiration_date;
                            console.log('[L10N_DO_POS] ✅ Vencimiento NCF aplicado sin formatear:', fiscalData.l10n_do_ncf_expiration_date);
                        }
                    } else {
                        console.log('[L10N_DO_POS] ⚠️ Vencimiento NCF no disponible en fiscalData');
                    }

                    if (fiscalData.l10n_do_origin_ncf) {
                        result.l10n_do_origin_ncf = fiscalData.l10n_do_origin_ncf;
                        result.origin_ncf = fiscalData.l10n_do_origin_ncf;
                        console.log('[L10N_DO_POS] ✅ NCF Modificado aplicado:', fiscalData.l10n_do_origin_ncf);
                    }

                    // Datos EDI - QR Code con debug mejorado
                    if (fiscalData.QR_code) {
                        result.QR_code = fiscalData.QR_code;
                        // Asegurar formato correcto del QR Code
                        if (typeof fiscalData.QR_code === 'string') {
                            // Verificar si ya tiene el prefijo data URI
                            if (fiscalData.QR_code.startsWith('data:image')) {
                                result.qr_code_img = fiscalData.QR_code;
                            } else {
                                result.qr_code_img = `data:image/png;base64,${fiscalData.QR_code}`;
                            }
                        } else if (fiscalData.qr_code_img) {
                            result.qr_code_img = fiscalData.qr_code_img;
                        }
                        console.log('[L10N_DO_POS] ✅ QR Code aplicado - Tipo:', typeof fiscalData.QR_code);
                        console.log('[L10N_DO_POS] ✅ qr_code_img set:', !!result.qr_code_img);
                    } else {
                        console.log('[L10N_DO_POS] ⚠️ QR Code no disponible en fiscalData');
                    }

                    if (fiscalData.l10n_do_ecf_security_code) {
                        result.l10n_do_ecf_security_code = fiscalData.l10n_do_ecf_security_code;
                        console.log('[L10N_DO_POS] ✅ Código seguridad aplicado:', fiscalData.l10n_do_ecf_security_code);
                    }

                    if (fiscalData.l10n_do_ecf_sign_date) {
                        result.l10n_do_ecf_sign_date = fiscalData.l10n_do_ecf_sign_date;
                        console.log('[L10N_DO_POS] ✅ Fecha firma aplicada:', fiscalData.l10n_do_ecf_sign_date);
                    }

                } else {
                    console.log('[L10N_DO_POS] ⚠️ No se encontraron datos fiscales para la orden');
                }
                    } else {
                        console.log('[L10N_DO_POS] ❌ Sin contexto para consulta en tiempo real');
                    }
                }
                
                // Si no hay datos EDI pre-cargados ni se pudieron obtener en tiempo real,
                // simplemente continuar sin ellos (el recibo mostrará placeholder)
                if (!result.QR_code && !result.l10n_do_ecf_security_code) {
                    console.log('[L10N_DO_POS] ⚠️ Sin datos EDI disponibles - mostrando placeholders');
                }

            } catch (error) {
                console.error('[L10N_DO_POS] ❌ Error consultando datos fiscales:', error);

                // Fallback: usar datos del modelo si existen
                if (self.ncf) {
                    result.l10n_latam_document_number = self.ncf;
                    result.ncf = self.ncf;
                    console.log('[L10N_DO_POS] 🎯 Usando NCF desde modelo:', self.ncf);
                }
            }
        }

        // Datos básicos de fallback
        if (self.l10n_latam_document_type_id) {
            result.l10n_latam_document_type_id = self.l10n_latam_document_type_id;
            console.log('[L10N_DO_POS] Including document type:', self.l10n_latam_document_type_id);
        } else {
            result.l10n_latam_document_type_id = 'Consumo';
        }
        
        // Asegurar fecha de vencimiento si aún no está procesada
        if (self.l10n_do_ncf_expiration_date && !result.l10n_do_ncf_expiration_date) {
            try {
                const expirationDate = new Date(self.l10n_do_ncf_expiration_date);
                result.l10n_do_ncf_expiration_date = expirationDate.toLocaleDateString('es-DO', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric'
                });
                console.log('[L10N_DO_POS] 📅 Vencimiento NCF (fallback):', result.l10n_do_ncf_expiration_date);
            } catch (e) {
                result.l10n_do_ncf_expiration_date = self.l10n_do_ncf_expiration_date;
                console.log('[L10N_DO_POS] 📅 Vencimiento NCF (fallback sin formato):', result.l10n_do_ncf_expiration_date);
            }
        }
        
        // Datos básicos dominicanos
        result.partner = self.getPartner();

        // NCF modificado (usar campo correcto)
        if (self.origin_ncf) {
            result.l10n_do_origin_ncf = self.origin_ncf;
            result.origin_ncf = self.origin_ncf;
            console.log('[L10N_DO_POS] Including origin NCF:', self.origin_ncf);
        }
        result.to_invoice = self.to_invoice;
        result.l10n_do_ecf_modification_code = self.l10n_do_ecf_modification_code;

        // Datos EDI para facturación electrónica
        if (self.l10n_do_ecf_security_code) {
            result.l10n_do_ecf_security_code = self.l10n_do_ecf_security_code;
            console.log('[L10N_DO_POS] Including EDI security code:', self.l10n_do_ecf_security_code);
        }

        if (self.l10n_do_ecf_sign_date) {
            result.l10n_do_ecf_sign_date = self.l10n_do_ecf_sign_date;
            console.log('[L10N_DO_POS] Including EDI sign date:', self.l10n_do_ecf_sign_date);
        }

        if (self.QR_code) {
            result.QR_code = self.QR_code;
            // Verificar si ya tiene el prefijo data URI
            if (self.QR_code.startsWith('data:image')) {
                result.l10n_do_ecf_qr_code = self.QR_code;
            } else {
                result.l10n_do_ecf_qr_code = `data:image/png;base64,${self.QR_code}`;
            }
            console.log('[L10N_DO_POS] Including EDI QR code');
        }

        if (self.l10n_do_dgii_commercial_approval !== undefined) {
            result.l10n_do_dgii_commercial_approval = self.l10n_do_dgii_commercial_approval;
        }

        // ⚡ CORREGIR NOMBRES DE IMPUESTOS FALTANTES
        console.log('[L10N_DO_POS] 🔧 Corrigiendo tax_details...');
        console.log('[L10N_DO_POS] tax_details original:', result.tax_details);

        if (result.tax_details && Array.isArray(result.tax_details)) {
            result.tax_details = result.tax_details.map((tax, index) => {
                // Si no tiene nombre, asignar uno basado en el porcentaje/monto
                if (!tax.name || tax.name === '') {
                    const amount = parseFloat(tax.amount || 0);
                    const base = parseFloat(tax.base || result.total_without_tax || 0);

                    if (amount > 0 && base > 0) {
                        const percentage = Math.round((amount / base) * 100);
                        tax.name = `${percentage}% ITBIS Incl:`;  // Formato DGII oficial
                        console.log('[L10N_DO_POS] ✅ Asignado nombre impuesto:', tax.name);
                    } else if (amount > 0) {
                        tax.name = 'ITBIS';
                        console.log('[L10N_DO_POS] ✅ Asignado nombre genérico:', tax.name);
                    } else {
                        tax.name = `Impuesto ${index + 1}`;
                        console.log('[L10N_DO_POS] ✅ Asignado nombre fallback:', tax.name);
                    }
                }
                return tax;
            });

            console.log('[L10N_DO_POS] tax_details corregido:', result.tax_details);
        } else {
            console.log('[L10N_DO_POS] ⚠️ tax_details no es array válido, creando desde totales...');

            // Crear tax_details desde los totales si no existe
            const totalWithTax = parseFloat(result.amount_total || result.total_with_tax || 0);
            const totalWithoutTax = parseFloat(result.total_without_tax || 0);
            const taxAmount = totalWithTax - totalWithoutTax;

            if (taxAmount > 0) {
                const percentage = Math.round((taxAmount / totalWithoutTax) * 100);
                result.tax_details = [{
                    name: `${percentage}% ITBIS Incl:`,  // Formato DGII oficial
                    amount: taxAmount,
                    base: totalWithoutTax,
                    tax_percentage: percentage
                }];
                console.log('[L10N_DO_POS] ✅ tax_details creado desde totales:', result.tax_details);
            }
        }

        // Indicar si es un documento de facturación electrónica válido
        result.is_ecf_invoice = !!(result.QR_code || result.l10n_do_ecf_security_code || result.qr_code_img);

        // Para compatibilidad con template existente
        result.ncf = result.l10n_latam_document_number;
        
        // ASEGURAR DATOS MÍNIMOS PARA RECIBO FISCAL
        if (self.to_invoice) {
            // Verificar si hay NCF disponible (desde cualquier fuente)
            const availableNCF = result.l10n_latam_document_number || result.ncf || self.l10n_latam_document_number;
            
            if (availableNCF && availableNCF !== 'PROCESANDO...') {
                result.ncf_status = 'CONFIRMADO';
                result.l10n_latam_document_number = availableNCF;
                result.ncf = availableNCF;
                console.log('[L10N_DO_POS] ✅ NCF confirmado:', availableNCF);
            } else {
                result.ncf_status = 'PROCESANDO...';
                result.l10n_latam_document_number = 'PROCESANDO...';
                console.log('[L10N_DO_POS] ⚠️ NCF en procesamiento');
            }
            
            // Determinar tipo de documento dinámico basado en NCF y contexto
            const currentNCF = result.l10n_latam_document_number || result.ncf;
            const partnerType = result.partner?.l10n_do_dgii_tax_payer_type || 'non_payer';
            
            if (currentNCF && currentNCF.startsWith('E')) {
                // Determinar tipo base sin duplicar "Electrónica"
                if (currentNCF.startsWith('E31')) {
                    // Factura de Crédito Fiscal Electrónica
                    result.l10n_latam_document_type_id = 'Crédito Fiscal';
                    result.clean_document_type = 'CRÉDITO FISCAL';
                } else if (currentNCF.startsWith('E32')) {
                    // Factura de Consumo Electrónica
                    result.l10n_latam_document_type_id = 'Consumo';
                    result.clean_document_type = 'CONSUMO';
                } else if (currentNCF.startsWith('E33')) {
                    // Nota de Débito Electrónica
                    result.l10n_latam_document_type_id = 'Nota de Débito';
                    result.clean_document_type = 'NOTA DE DÉBITO';
                } else if (currentNCF.startsWith('E34')) {
                    // Nota de Crédito Electrónica
                    result.l10n_latam_document_type_id = 'Nota de Crédito';
                    result.clean_document_type = 'NOTA DE CRÉDITO';
                } else if (currentNCF.startsWith('E43')) {
                    // Régimen Especial Electrónica
                    result.l10n_latam_document_type_id = 'Régimen Especial';
                    result.clean_document_type = 'RÉGIMEN ESPECIAL';
                } else if (currentNCF.startsWith('E44')) {
                    // Gubernamental Electrónica
                    result.l10n_latam_document_type_id = 'Gubernamental';
                    result.clean_document_type = 'GUBERNAMENTAL';
                } else if (currentNCF.startsWith('E45')) {
                    // Exportación Electrónica
                    result.l10n_latam_document_type_id = 'Exportación';
                    result.clean_document_type = 'EXPORTACIÓN';
                } else {
                    // Electrónica genérica
                    result.l10n_latam_document_type_id = result.l10n_latam_document_type_id || 'Consumo';
                    result.clean_document_type = this.pos ? this.pos.cleanDocumentType(result.l10n_latam_document_type_id) : 'CONSUMO';
                }
                
                console.log('[L10N_DO_POS] 📋 Tipo documento determinado por NCF:', result.clean_document_type);
            } else {
                // Fallback para documentos no electrónicos
                if (!result.l10n_latam_document_type_id) {
                    result.l10n_latam_document_type_id = 'Consumo';
                    console.log('[L10N_DO_POS] 📋 Tipo documento por defecto asignado');
                }
                result.clean_document_type = this.pos ? this.pos.cleanDocumentType(result.l10n_latam_document_type_id) : 'CONSUMO';
            }
        }

        // Usar nombre de factura del servidor si está disponible
        if (self.to_invoice && !result.name) {
            result.name = self.name || 'PROCESANDO...';
        }
        
        // Datos adicionales para el template dominicano
        if (self.is_copy) {
            result.is_copy = self.is_copy;
        }
        
        // Asegurar información fiscal completa
        if (result.to_invoice) {
            // Asegurar que el partner tenga información mínima
            if (!result.partner) {
                result.partner = {
                    name: 'Cliente de consumo',
                    vat: false
                };
            }
            
            // Asegurar tipo de contribuyente
            if (result.partner && !result.partner.l10n_do_dgii_tax_payer_type) {
                result.partner.l10n_do_dgii_tax_payer_type = 'non_payer';
            }
        }
        
        // Asegurar que los datos de la compañía incluyan información dominicana
        if (result.headerData && result.headerData.company) {
            // Si no existe company_address, usar la dirección formateada
            if (!result.headerData.company.company_address && self.pos && self.pos.company && self.pos.company.partner_id) {
                result.headerData.company.company_address = self.pos.company.street || '';
            }
        }
        
        console.log('[L10N_DO_POS] Complete Dominican receipt data:', {
            ncf: result.ncf,
            ncf_status: result.ncf_status,
            l10n_latam_document_number: result.l10n_latam_document_number,
            l10n_latam_document_type_id: result.l10n_latam_document_type_id,
            clean_document_type: result.clean_document_type,
            partner: result.partner?.name,
            to_invoice: result.to_invoice,
            is_ecf_invoice: result.is_ecf_invoice,
            l10n_do_ecf_security_code: result.l10n_do_ecf_security_code,
            l10n_do_ecf_sign_date: result.l10n_do_ecf_sign_date,
            l10n_do_dgii_commercial_approval: result.l10n_do_dgii_commercial_approval,
            has_qr: !!result.qr_code_img,
            has_ecf_data: !!(result.QR_code || result.l10n_do_ecf_security_code)
        });

        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] EXPORT_FOR_PRINTING RESULTADO FINAL (PosOrder):');
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] result.headerData final:', result.headerData);
        console.log('[L10N_DO_POS] result.headerData?.company:', result.headerData?.company);
        console.log('[L10N_DO_POS] result.company final:', result.company);
        console.log('[L10N_DO_POS] result keys:', Object.keys(result));
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');

        return result;
    }
});

patch(PosPayment.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.credit_note_id = '';
        this.note = '';
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.credit_note_id = json.credit_note_id;
        this.note = json.note;
    },
    set_credit_note_id(credit_note_id){
        if(this.credit_note_id !== credit_note_id){
            this.credit_note_id = credit_note_id;
        }
    },
    get_credit_note_id(){
        return this.credit_note_id;
    },
    set_note(note){
        if(this.note !== note){
            this.note = note;
        }
    },
    get_note(){
        return this.note;
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.credit_note_id = this.credit_note_id;
        json.note = this.note;
        return json;
    },
    export_for_printing() {
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');
        console.log('[L10N_DO_POS] EXPORT_FOR_PRINTING LLAMADO (PosPayment)');
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');

        const result = super.export_for_printing(...arguments);

        console.log('[L10N_DO_POS] PosPayment super result:', result);

        result.credit_note_id = this.credit_note_id;
        result.note = this.note;

        console.log('[L10N_DO_POS] PosPayment final result:', result);
        console.log('[L10N_DO_POS] ═══════════════════════════════════════════════════');

        return result;
    }
});

