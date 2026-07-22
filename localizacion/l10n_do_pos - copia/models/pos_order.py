# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import base64

_logger = logging.getLogger(__name__)

# Autor: Arturo Diaz Lora
# Fecha: 2025-11-23 01:20
# Razón: Log de verificación de carga del archivo pos_order.py
_logger.info("="*80)
_logger.info("[L10N_DO_POS] 📦 pos_order.py CARGÁNDOSE...")
_logger.info("="*80)


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Autor: Arturo Diaz Lora
    # Fecha: 2025-11-22
    # Cambio: Agregado store=True a l10n_latam_document_number y origin_ncf para que se almacenen
    # en la base de datos y sean visibles en las vistas de árbol del POS
    # Razón: El campo NCF aparecía vacío en la vista de órdenes pagadas porque los campos related
    # sin store=True no se almacenan en BD y pueden no mostrarse en tree views
    ncf = fields.Char("NCF")

    # Autor: Arturo Diaz Lora
    # Fecha: 2025-11-26 03:45
    # Razón: REVERTIDO - El método _load_pos_data_fields NO debe sobrescribirse en pos.order
    # porque el comportamiento por defecto (lista vacía) hace que read() devuelva TODOS los campos.
    # Al definir campos específicos, read() SOLO devuelve esos campos y se pierden campos críticos
    # como payment_ids, lines, state, etc., causando error: "can't access property 'filter', payment_ids is undefined"
    # Los campos NCF ya tienen store=True y se cargarán automáticamente con el comportamiento por defecto.

    l10n_latam_document_number = fields.Char(related="account_move.l10n_latam_document_number", string="Document Number", store=True, readonly=True)
    origin_ncf = fields.Char(related="account_move.l10n_do_origin_ncf", string="Modifies", store=True, readonly=True)
    l10n_latam_document_type_id = fields.Many2one(related="account_move.l10n_latam_document_type_id", store=True)
    l10n_do_ecf_modification_code = fields.Char(string="Modification Code", readonly=True)
    l10n_do_ncf_expiration_date = fields.Date(related="account_move.l10n_do_ncf_expiration_date", string="NCF Expiration Date", readonly=True)
    display_name = fields.Char(compute="_compute_new_display_name", store=True, index=True)

    @api.depends("pos_reference", "l10n_latam_document_number")
    def _compute_new_display_name(self):
        for record in self:
            record.display_name = "%s - %s" % (record.pos_reference, record.l10n_latam_document_number)

    @api.model
    def get_from_ui(self, order):
        """Este metodo es llamado desde el POS al dar clik en Refund

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-23 00:25 (actualizado 00:35)
        Razón: Obtener NCF de account_move para notas de crédito
        """
        # Buscar por 'name', NO por 'pos_reference'
        # Frontend envía order.name (ej: "CAJA 1/0235")
        pos_order = self.sudo().search([('name', '=', order)], limit=1)

        _logger.info(f"[L10N_DO_POS] get_from_ui called - Order name: {order}")
        _logger.info(f"[L10N_DO_POS] get_from_ui - Found order: {pos_order.name if pos_order else 'NOT FOUND'}")

        # Obtener NCF de la factura asociada si existe
        ncf = False
        if pos_order and pos_order.account_move:
            ncf = pos_order.account_move.l10n_latam_document_number
            _logger.info(f"[L10N_DO_POS] get_from_ui - NCF from invoice: {ncf}, Invoice: {pos_order.account_move.name}")
        elif pos_order:
            _logger.warning(f"[L10N_DO_POS] get_from_ui - Order {order} has no invoice yet")
        else:
            _logger.error(f"[L10N_DO_POS] get_from_ui - Order {order} NOT FOUND in database")

        return {
            'l10n_latam_document_number': ncf,
        }

    def _process_order(self, order, existing_order):
        """Sobrescribir para mapear campos dominicanos del frontend al backend.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-23 01:50 (actualizado 2025-11-24 05:10)
        Razón: En Odoo v18, sync_from_ui llama a _process_order (NO create_from_ui).
               El frontend envía modification_code pero el campo se llama l10n_do_ecf_modification_code.
               Necesitamos mapear este campo ANTES de que se cree la orden.
               IMPORTANTE: Limpiar valores vacíos ("", false) para que no se guarden incorrectamente.
        """
        _logger.info(f"[L10N_DO_POS] ========== _PROCESS_ORDER DEBUG ==========")
        _logger.info(f"[L10N_DO_POS] order keys: {list(order.keys())}")
        _logger.info(f"[L10N_DO_POS] order.get('modification_code'): {order.get('modification_code')}")
        _logger.info(f"[L10N_DO_POS] order.get('l10n_do_ecf_modification_code'): {order.get('l10n_do_ecf_modification_code')}")
        _logger.info(f"[L10N_DO_POS] order.get('origin_ncf'): {order.get('origin_ncf')}")
        _logger.info(f"[L10N_DO_POS] order.get('ncf'): {order.get('ncf')}")

        # Limpiar campos vacíos ("", false, None) del frontend
        # El frontend a veces envía "" o false, lo que puede causar problemas
        for field in ['l10n_do_ecf_modification_code', 'ncf', 'origin_ncf']:
            if field in order and not order[field]:
                order[field] = False
                _logger.info(f"[L10N_DO_POS] Limpiado campo vacío: {field}")

        # Mapear campos del frontend al backend
        # El frontend envía 'modification_code' pero el campo en el modelo es 'l10n_do_ecf_modification_code'
        if order.get('modification_code'):
            _logger.info(f"[L10N_DO_POS] ✅ Mapeando modification_code '{order['modification_code']}' a l10n_do_ecf_modification_code")
            order['l10n_do_ecf_modification_code'] = order['modification_code']

        # Mapear origin_ncf si existe
        if order.get('origin_ncf'):
            _logger.info(f"[L10N_DO_POS] ✅ Usando origin_ncf '{order['origin_ncf']}' como ncf para nota de crédito")
            order['ncf'] = order['origin_ncf']

        _logger.info(f"[L10N_DO_POS] DESPUÉS DEL MAPEO:")
        _logger.info(f"[L10N_DO_POS] order.get('l10n_do_ecf_modification_code'): {order.get('l10n_do_ecf_modification_code')}")
        _logger.info(f"[L10N_DO_POS] order.get('ncf'): {order.get('ncf')}")
        _logger.info(f"[L10N_DO_POS] ==============================================")

        # Llamar al método padre
        return super()._process_order(order, existing_order)

    @api.model
    def create_from_ui(self, orders, draft=False):
        """ Create and update Orders from the frontend PoS application.

        Create new orders and update orders that are in draft status. If an order already exists with a status
        diferent from 'draft'it will be discareded, otherwise it will be saved to the database. If saved with
        'draft' status the order can be overwritten later by this function.

        :param orders: dictionary with the orders to be created.
        :type orders: dict.
        :param draft: Indicate if the orders are ment to be finalised or temporarily saved.
        :type draft: bool.
        :Returns: list -- list of db-ids for the created and updated orders.
        """
        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-23 01:00 (actualizado 01:15)
        # Razón: Guardar l10n_do_ecf_modification_code y ncf del frontend en pos_order
        # El método padre create_from_ui no conoce estos campos dominicanos,
        # por lo que debemos actualizar las órdenes después de crearlas

        _logger.info(f"[L10N_DO_POS] ========== create_from_ui DEBUG ==========")
        _logger.info(f"[L10N_DO_POS] orders type: {type(orders)}")
        _logger.info(f"[L10N_DO_POS] orders length: {len(orders) if isinstance(orders, list) else 'N/A'}")
        if orders and isinstance(orders, list) and len(orders) > 0:
            _logger.info(f"[L10N_DO_POS] First order keys: {list(orders[0].keys()) if isinstance(orders[0], dict) else 'N/A'}")
            _logger.info(f"[L10N_DO_POS] First order 'data' keys: {list(orders[0].get('data', {}).keys()) if isinstance(orders[0], dict) else 'N/A'}")
            if isinstance(orders[0], dict) and 'data' in orders[0]:
                order_data = orders[0]['data']
                _logger.info(f"[L10N_DO_POS] First order data.name: {order_data.get('name')}")
                _logger.info(f"[L10N_DO_POS] First order data.ncf: {order_data.get('ncf')}")
                _logger.info(f"[L10N_DO_POS] First order data.l10n_do_ecf_modification_code: {order_data.get('l10n_do_ecf_modification_code')}")

        res = super(PosOrder, self).create_from_ui(orders, draft)

        _logger.info(f"[L10N_DO_POS] super().create_from_ui returned {len(res)} orders")

        for record in res:
            order = self.browse(record.get('id'))
            _logger.info(f"[L10N_DO_POS] Processing order {order.id}: name={order.name}, pos_reference={order.pos_reference}")

            # Buscar los datos originales del frontend para esta orden
            # Intentar buscar por name (field) o pos_reference
            frontend_data = {}
            for order_data in orders:
                if isinstance(order_data, dict) and 'data' in order_data:
                    data = order_data['data']
                    # El frontend envía 'name' que se convierte en 'pos_reference' en el backend
                    if data.get('name') == order.pos_reference or data.get('name') == order.name:
                        frontend_data = data
                        _logger.info(f"[L10N_DO_POS] ✅ Found frontend data for order {order.id} by matching name: {data.get('name')}")
                        break

            if not frontend_data:
                _logger.warning(f"[L10N_DO_POS] ⚠️ No frontend data found for order {order.id}")
                continue

            # Actualizar campos que el método padre no guardó
            update_vals = {}
            if frontend_data.get('ncf'):
                update_vals['ncf'] = frontend_data['ncf']
            if frontend_data.get('l10n_do_ecf_modification_code'):
                update_vals['l10n_do_ecf_modification_code'] = frontend_data['l10n_do_ecf_modification_code']

            if update_vals:
                _logger.info(f"[L10N_DO_POS] create_from_ui - Updating order {order.id} with: {update_vals}")
                order.write(update_vals)
                # Recargar orden para obtener datos actualizados
                order = self.browse(order.id)
            else:
                _logger.warning(f"[L10N_DO_POS] ⚠️ No Dominican fields to update for order {order.id}")

            # SINCRONIZACIÓN INMEDIATA DE DATOS FISCALES
            _logger.info(f"[L10N_DO_POS] create_from_ui - Processing order {order.id} for immediate fiscal sync")

            # Verificar si debe generar factura inmediatamente
            _logger.info(f"[L10N_DO_POS] 🔍 Order {order.id} - to_invoice: {order.to_invoice}, account_move: {bool(order.account_move)}")
            if order.to_invoice and not order.account_move:
                _logger.info(f"[L10N_DO_POS] 📝 Order {order.id} requires immediate invoicing")
                try:
                    # Forzar creación de factura si es necesario
                    order.action_pos_order_invoice()
                    _logger.info(f"[L10N_DO_POS] ✅ Invoice created for order {order.id}")

                    # La función action_pos_order_invoice ya maneja el envío automático a DGII
                    # si l10n_do_ecf_pos_auto_send está activado

                except Exception as e:
                    _logger.error(f"[L10N_DO_POS] ❌ Error creating invoice for order {order.id}: {e}")
            else:
                if not order.to_invoice:
                    _logger.info(f"[L10N_DO_POS] 🚨 Order {order.id} not set to invoice (to_invoice: False)")
                if order.account_move:
                    _logger.info(f"[L10N_DO_POS] 📝 Order {order.id} already has invoice: {order.account_move.name}")
            
            # Recargar orden para obtener datos actualizados
            order = self.browse(order.id)
            
            # Aplicar datos fiscales básicos
            record['ncf'] = order.l10n_latam_document_number
            record['l10n_latam_document_type_id'] = order.l10n_latam_document_type_id.name if order.l10n_latam_document_type_id else False
            record['origin_ncf'] = order.origin_ncf
            record['l10n_do_ecf_modification_code'] = order.l10n_do_ecf_modification_code
            record['l10n_do_ncf_expiration_date'] = order.l10n_do_ncf_expiration_date

            # Incluir campos EDI para facturación electrónica
            _logger.info(f"[L10N_DO_POS] create_from_ui - Order {order.id} has QR: {bool(order.QR_code)}")

            # Procesar QR Code de manera segura
            qr_code_base64 = False
            if order.QR_code:
                try:
                    qr_code_base64 = 'data:image/png;base64,' + order.QR_code.decode('ascii')
                    _logger.info("[L10N_DO_POS] create_from_ui - QR converted successfully")
                except Exception as e:
                    _logger.error(f"[L10N_DO_POS] create_from_ui - Error converting QR: {e}")
                    try:
                        qr_code_base64 = 'data:image/png;base64,' + str(order.QR_code)
                    except:
                        pass

            record['l10n_do_ecf_security_code'] = order.l10n_do_ecf_security_code
            record['l10n_do_ecf_sign_date'] = order.l10n_do_ecf_sign_date.strftime('%Y-%m-%d %H:%M:%S') if order.l10n_do_ecf_sign_date else False
            record['l10n_do_ecf_qr_code'] = qr_code_base64
            record['QR_code'] = order.QR_code
            record['qr_code_img'] = qr_code_base64
            record['l10n_do_dgii_commercial_approval'] = order.l10n_do_dgii_commercial_approval
            record['is_ecf_invoice'] = bool(order.QR_code and order.l10n_do_ecf_security_code)

            _logger.info(f"[L10N_DO_POS] create_from_ui - Record has is_ecf_invoice: {record.get('is_ecf_invoice')}")

        _logger.info(f"[L10N_DO_POS] ========== create_from_ui COMPLETED ==========")
        return res

    @api.model
    def _order_fields(self, ui_order):
        res = super()._order_fields(ui_order)
        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-22 23:10
        # Razón: Agregar captura de origin_ncf desde el frontend para notas de crédito del POS
        # El frontend (TicketScreen.js) configura destinationOrder.origin_ncf con el NCF de la factura original
        # pero este campo no se estaba capturando, causando que las notas de crédito no tengan l10n_do_origin_ncf
        res['ncf'] = ui_order.get('origin_ncf', False) or ui_order.get('ncf', False)
        res['l10n_do_ecf_modification_code'] = ui_order.get('l10n_do_ecf_modification_code', False)

        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-22 23:35
        # Razón: Logs detallados para debuggear captura de datos de notas de crédito
        _logger.info(f"[L10N_DO_POS] ========== _ORDER_FIELDS DEBUG ==========")
        _logger.info(f"[L10N_DO_POS] ui_order.get('origin_ncf'): {ui_order.get('origin_ncf')}")
        _logger.info(f"[L10N_DO_POS] ui_order.get('ncf'): {ui_order.get('ncf')}")
        _logger.info(f"[L10N_DO_POS] ui_order.get('l10n_do_ecf_modification_code'): {ui_order.get('l10n_do_ecf_modification_code')}")
        _logger.info(f"[L10N_DO_POS] res['ncf'] (resultado): {res['ncf']}")
        _logger.info(f"[L10N_DO_POS] res['l10n_do_ecf_modification_code']: {res['l10n_do_ecf_modification_code']}")
        _logger.info(f"[L10N_DO_POS] ============================================")

        return res

    def _export_for_ui(self, order):
        result = super(PosOrder, self)._export_for_ui(order)

        # Log para debugging
        _logger.info(f"[L10N_DO_POS] _export_for_ui called for order {order.id}")
        _logger.info(f"[L10N_DO_POS] Order has QR_code: {bool(order.QR_code)}")
        _logger.info(f"[L10N_DO_POS] Order has security_code: {bool(order.l10n_do_ecf_security_code)}")
        _logger.info(f"[L10N_DO_POS] Order NCF: {order.l10n_latam_document_number}")

        # Procesar QR Code
        qr_code_base64 = False
        if order.QR_code:
            try:
                # El QR ya está en base64 en la DB
                qr_code_base64 = 'data:image/png;base64,' + order.QR_code.decode('ascii')
                _logger.info("[L10N_DO_POS] QR Code converted to base64 successfully")
            except Exception as e:
                _logger.error(f"[L10N_DO_POS] Error converting QR: {e}")
                # Si falla, intentar usar directamente
                try:
                    qr_code_base64 = 'data:image/png;base64,' + str(order.QR_code)
                except:
                    pass

        result.update({
            'l10n_latam_document_type_id': order.l10n_latam_document_type_id.name if order.l10n_latam_document_type_id else False,
            'origin_ncf': order.origin_ncf,
            'ncf': order.l10n_latam_document_number,
            'l10n_latam_document_number': order.l10n_latam_document_number,
            'l10n_do_ncf_expiration_date': str(order.l10n_do_ncf_expiration_date) if order.l10n_do_ncf_expiration_date else False,
            # Campos EDI para facturación electrónica
            'l10n_do_ecf_security_code': order.l10n_do_ecf_security_code,
            'l10n_do_ecf_sign_date': order.l10n_do_ecf_sign_date.strftime('%Y-%m-%d %H:%M:%S') if order.l10n_do_ecf_sign_date else False,
            'l10n_do_ecf_qr_code': qr_code_base64,
            'QR_code': order.QR_code,  # Mantener compatibilidad con campo binario
            'qr_code_img': qr_code_base64,  # Alias para el template
            'l10n_do_dgii_commercial_approval': order.l10n_do_dgii_commercial_approval,
            'is_ecf_invoice': bool(order.account_move.is_ecf_invoice if order.account_move else False),
        })

        _logger.info(f"[L10N_DO_POS] ========== EXPORT_FOR_UI FINAL RESULT ==========")
        _logger.info(f"[L10N_DO_POS] Order ID: {order.id} - Name: {order.name}")
        _logger.info(f"[L10N_DO_POS] Account Move ID: {order.account_move.id if order.account_move else None}")
        _logger.info(f"[L10N_DO_POS] NCF (l10n_latam_document_number): {order.l10n_latam_document_number}")
        _logger.info(f"[L10N_DO_POS] Result NCF: {result.get('ncf')}")
        _logger.info(f"[L10N_DO_POS] Result l10n_latam_document_number: {result.get('l10n_latam_document_number')}")
        _logger.info(f"[L10N_DO_POS] Result l10n_latam_document_type_id: {result.get('l10n_latam_document_type_id')}")
        _logger.info(f"[L10N_DO_POS] Result has is_ecf_invoice: {result.get('is_ecf_invoice')}")
        _logger.info(f"[L10N_DO_POS] Result has qr_code_img: {bool(result.get('qr_code_img'))}")
        _logger.info(f"[L10N_DO_POS] ================================================")

        return result

    def _prepare_invoice_vals(self):
        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-22 23:12
        # Razón: Eliminar duplicación de método (estaba definido dos veces)
        # Asegurar que las notas de crédito del POS tengan l10n_do_origin_ncf y l10n_do_ecf_modification_code
        result = super(PosOrder, self)._prepare_invoice_vals()

        # Autor: Arturo Diaz Lora
        # Fecha: 2025-11-22 23:37 (actualizado 2025-11-24 05:15)
        # Razón: Logs detallados y mejorar lógica para notas de crédito
        # IMPORTANTE: Solo pasar l10n_do_ecf_modification_code si tiene un valor válido
        _logger.info(f"[L10N_DO_POS] ========== _PREPARE_INVOICE_VALS DEBUG ==========")
        _logger.info(f"[L10N_DO_POS] Order ID: {self.id}, Name: {self.name}")
        _logger.info(f"[L10N_DO_POS] move_type: {result.get('move_type')}")
        _logger.info(f"[L10N_DO_POS] self.ncf: {self.ncf}")
        _logger.info(f"[L10N_DO_POS] self.l10n_do_ecf_modification_code: '{self.l10n_do_ecf_modification_code}'")
        _logger.info(f"[L10N_DO_POS] self.l10n_do_ecf_modification_code type: {type(self.l10n_do_ecf_modification_code)}")
        _logger.info(f"[L10N_DO_POS] self.l10n_do_ecf_modification_code bool: {bool(self.l10n_do_ecf_modification_code)}")

        if result['move_type'] == 'out_refund':
            # Transferir origin_ncf siempre
            result["l10n_do_origin_ncf"] = self.ncf

            # Solo transferir l10n_do_ecf_modification_code si tiene un valor válido
            # El campo Selection en account.move NO acepta False, None, o ""
            # Solo acepta valores de la lista: "01", "02", "03", "04", "05"
            if self.l10n_do_ecf_modification_code:
                result["l10n_do_ecf_modification_code"] = self.l10n_do_ecf_modification_code
                _logger.info(f"[L10N_DO_POS] ✅ Código de modificación transferido: '{self.l10n_do_ecf_modification_code}'")
            else:
                _logger.warning(f"[L10N_DO_POS] ⚠️ l10n_do_ecf_modification_code está vacío - NO SE TRANSFERIRÁ")

            _logger.info(f"[L10N_DO_POS] ✅ Nota de crédito detectada - Seteando campos fiscales:")
            _logger.info(f"[L10N_DO_POS] result['l10n_do_origin_ncf']: {result['l10n_do_origin_ncf']}")
            _logger.info(f"[L10N_DO_POS] result['l10n_do_ecf_modification_code']: {result.get('l10n_do_ecf_modification_code', 'NO SETEADO')}")

        _logger.info(f"[L10N_DO_POS] =====================================================")

        return result

    @api.model
    def sync_from_ui(self, orders):
        """
        Sobrescribir para manejar errores de secuencia fiscal de forma clara.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-26 16:00
        Razón: El código base de Odoo en _process_saved_order captura Exception y solo
               hace log sin relanzar el error. Esto causa que los errores de secuencia
               fiscal (ValidationError) no lleguen correctamente al frontend.
               Esta sobrescritura captura los errores y los relanza como UserError
               para que el POS los muestre correctamente.
        """
        try:
            return super(PosOrder, self).sync_from_ui(orders)
        except ValidationError as e:
            error_msg = str(e)
            _logger.error(f"[L10N_DO_POS] ❌ ValidationError en sync_from_ui: {error_msg}")
            # Relanzar como UserError para que el POS lo muestre correctamente
            raise UserError(error_msg) from e
        except UserError as e:
            error_msg = str(e)
            _logger.error(f"[L10N_DO_POS] ❌ UserError en sync_from_ui: {error_msg}")
            # Relanzar el UserError tal cual
            raise
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"[L10N_DO_POS] ❌ Exception en sync_from_ui: {error_msg}")
            # Si es un error de secuencia fiscal, convertir a UserError
            if "SECUENCIA FISCAL" in error_msg or "secuencia fiscal" in error_msg.lower():
                raise UserError(error_msg) from e
            raise

    def _generate_pos_order_invoice(self):
        """
        Sobrescribir para manejar errores de secuencia fiscal agotada de forma clara.

        Autor: Arturo Diaz Lora
        Fecha: 2025-11-26 11:35 (actualizado 2025-11-26 16:05)
        Razón: Cuando la secuencia fiscal está agotada, el error ValidationError se captura
               en algún lugar y el usuario ve "Odoo Server Error" genérico en lugar del
               mensaje claro. Este método captura el ValidationError y lo relanza como
               UserError para que el POS lo muestre correctamente.
        """
        try:
            return super(PosOrder, self)._generate_pos_order_invoice()
        except ValidationError as e:
            # Capturar el ValidationError y relanzarlo como UserError
            # para que el POS lo muestre correctamente al usuario
            error_msg = str(e)
            _logger.error(f"[L10N_DO_POS] ❌ ValidationError en facturación POS: {error_msg}")

            # Si es un error de secuencia fiscal, mostrar mensaje claro
            if "SECUENCIA FISCAL" in error_msg or "secuencia fiscal" in error_msg.lower():
                raise UserError(error_msg) from e
            else:
                # Para otros ValidationError, también mostrar el mensaje claro
                raise UserError(_(
                    "Error al generar factura:\n\n%s"
                ) % error_msg) from e
        except UserError:
            # Si ya es UserError, dejarlo pasar
            raise
        except Exception as e:
            _logger.error(f"[L10N_DO_POS] ❌ Error inesperado en facturación POS: {str(e)}")
            raise

    def action_pos_order_invoice(self):
        """Override to ensure POS invoices are sent to DGII automatically"""
        _logger.info(f"[L10N_DO_POS] 🚀 action_pos_order_invoice called for {len(self)} orders")
        result = super(PosOrder, self).action_pos_order_invoice()
        _logger.info(f"[L10N_DO_POS] 📋 super().action_pos_order_invoice() completed")

        # Verificar si hay facturas creadas y si el envío automático está activado
        for order in self:
            _logger.info(f"[L10N_DO_POS] 🔍 Checking order {order.name} (ID: {order.id})")
            _logger.info(f"[L10N_DO_POS] - account_move: {bool(order.account_move)} (ID: {order.account_move.id if order.account_move else 'None'})")
            _logger.info(f"[L10N_DO_POS] - company_id: {order.company_id.name}")
            _logger.info(f"[L10N_DO_POS] - l10n_do_ecf_activated: {order.company_id.l10n_do_ecf_activated}")
            
            if order.account_move and order.company_id.l10n_do_ecf_activated:
                invoice = order.account_move
                _logger.info(f"[L10N_DO_POS] ✅ Processing invoice {invoice.name} for automatic DGII send")

                # Verificar si el envío automático para POS está activado
                _logger.info(f"[L10N_DO_POS] - l10n_do_ecf_pos_auto_send: {order.company_id.l10n_do_ecf_pos_auto_send}")
                if order.company_id.l10n_do_ecf_pos_auto_send:
                    _logger.info(f"[L10N_DO_POS] ✅ Auto-send enabled for POS invoices - processing {invoice.name}")

                    # Verificar que la factura esté confirmada y sea elegible para EDI
                    _logger.info(f"[L10N_DO_POS] - invoice.state: {invoice.state}")
                    _logger.info(f"[L10N_DO_POS] - invoice.country_code: {invoice.country_code}")
                    if invoice.state == 'posted' and invoice.country_code == 'DO':
                        _logger.info(f"[L10N_DO_POS] ✅ Invoice {invoice.name} eligible for DGII send")

                        # Buscar el formato EDI dominicano
                        edi_format = self.env['account.edi.format'].search([
                            ('code', '=', 'dgii_ecf'),  # Código del formato EDI dominicano
                        ], limit=1)

                        if edi_format:
                            _logger.info(f"[L10N_DO_POS] ✅ Found EDI format {edi_format.name} (ID: {edi_format.id}) - sending invoice {invoice.name}")
                            try:
                                # Verificar si ya existe un documento EDI para esta factura
                                existing_edi_doc = self.env['account.edi.document'].search([
                                    ('edi_format_id', '=', edi_format.id),
                                    ('move_id', '=', invoice.id),
                                ], limit=1)

                                if existing_edi_doc:
                                    _logger.info(f"[L10N_DO_POS] Existing EDI document found (state: {existing_edi_doc.state}) - processing")
                                    # Si existe pero no ha sido procesado, procesarlo
                                    if existing_edi_doc.state in ('to_send', 'to_cancel'):
                                        existing_edi_doc._process_documents_web_services()
                                    edi_document = existing_edi_doc
                                else:
                                    # Crear nuevo documento EDI si no existe
                                    _logger.info(f"[L10N_DO_POS] Creating new EDI document for invoice {invoice.name}")
                                    edi_document = self.env['account.edi.document'].create({
                                        'edi_format_id': edi_format.id,
                                        'move_id': invoice.id,
                                        'state': 'to_send'
                                    })

                                    # Procesar el documento EDI inmediatamente
                                    edi_document._process_documents_web_services()

                                _logger.info(f"[L10N_DO_POS] ✅ Invoice {invoice.name} sent to DGII successfully (EDI state: {edi_document.state})")

                            except Exception as e:
                                _logger.error(f"[L10N_DO_POS] ❌ Error sending invoice {invoice.name} to DGII: {e}")
                        else:
                            _logger.error(f"[L10N_DO_POS] ❌ No EDI format 'dgii_ecf' found for Dominican Republic")
                    else:
                        _logger.info(f"[L10N_DO_POS] ❌ Invoice {invoice.name} not eligible for DGII send (state: {invoice.state}, country: {invoice.country_code})")
                else:
                    _logger.info(f"[L10N_DO_POS] ❌ Auto-send disabled for POS invoices")
            else:
                if not order.account_move:
                    _logger.info(f"[L10N_DO_POS] ❌ Order {order.name} has no account_move")
                if not order.company_id.l10n_do_ecf_activated:
                    _logger.info(f"[L10N_DO_POS] ❌ ECF not activated for company {order.company_id.name}")

        return result

    @api.model
    def _payment_fields(self, order, ui_paymentline):
        paymentline = super()._payment_fields(order, ui_paymentline)
        paymentline['credit_note_id'] = ui_paymentline.get('credit_note_id', False)
        paymentline['note'] = ui_paymentline.get('note', '')
        return paymentline

    # Campos EDI para facturación electrónica desde account.move
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", related="account_move.l10n_do_ecf_security_code", readonly=True)
    l10n_do_ecf_sign_date = fields.Datetime(string="e-CF Sign Date", related="account_move.l10n_do_ecf_sign_date", readonly=True)
    l10n_do_electronic_stamp = fields.Text(string="Electronic Stamp", related="account_move.l10n_do_electronic_stamp", readonly=True)
    # QR_code as Binary field related to account_move.qr_code
    QR_code = fields.Binary(string="QR Code", related="account_move.qr_code", readonly=True)
    l10n_do_status_commercial_approval = fields.Selection(related="account_move.l10n_do_status_commercial_approval", readonly=True)
    l10n_do_dgii_commercial_approval = fields.Boolean(related="account_move.l10n_do_dgii_commercial_approval", readonly=True)

    @api.model
    def credit_note_info_from_ui(self, l10n_latam_document_number, partner_id=None, amount_total=None):
        refund_document_type_id = self.env["l10n_latam.document.type"].search([('internal_type', '=', 'credit_note'),
                                                                               ('active', '=', True)])

        domain = [
            ("l10n_latam_document_number", "=", l10n_latam_document_number),
            ("l10n_latam_document_type_id", "in", refund_document_type_id.ids),
        ]
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        out_refund_invoice = self.env["pos.order"].search(domain)
        if not out_refund_invoice:
            out_refund_invoice = self.env["account.move"].search(domain)
        else:
            out_refund_invoice = out_refund_invoice.account_move

        if out_refund_invoice:
            msg_error = ""
            if partner_id and out_refund_invoice.partner_id.id != partner_id:
                msg_error = "La Nota de Crédito pertenece a otro cliente"
            elif not out_refund_invoice.amount_residual:
                msg_error = "El balance de la Nota de Crédito es 0."

            residual = out_refund_invoice.amount_residual
            if amount_total and amount_total < out_refund_invoice.amount_residual:
                residual = amount_total

            return {
                "model": out_refund_invoice._name,
                "id": out_refund_invoice.id,
                "residual": residual,
                "partner_id": out_refund_invoice.partner_id.id,
                "msg": msg_error
            }

        return {'msg': "La Nota de Crédito no existe."}
    
    @api.model
    def get_fiscal_data_for_receipt(self, pos_reference):
        """Método optimizado para obtener datos fiscales para el recibo POS"""
        _logger.info(f"[L10N_DO_POS] ========================================")
        _logger.info(f"[L10N_DO_POS] get_fiscal_data_for_receipt called for: {pos_reference}")
        _logger.info(f"[L10N_DO_POS] ========================================")

        try:
            # Buscar todas las órdenes para debug
            all_orders = self.search([])
            _logger.info(f"[L10N_DO_POS] Total POS orders in system: {len(all_orders)}")
            recent_orders = self.search([], order='create_date desc', limit=5)
            for o in recent_orders:
                _logger.info(f"[L10N_DO_POS] Recent order: {o.pos_reference} (ID: {o.id})")

            # Buscar la orden POS - CORREGIDO: usar 'name' en lugar de 'pos_reference'
            # El frontend envía currentOrder.name que corresponde al campo 'name' en pos.order
            order = self.search([('name', '=', pos_reference)], limit=1)
            if not order:
                _logger.warning(f"[L10N_DO_POS] Order not found by name: {pos_reference}")
                # Intentar búsqueda por pos_reference como fallback
                order = self.search([('pos_reference', '=', pos_reference)], limit=1)
                if not order:
                    _logger.warning(f"[L10N_DO_POS] Order not found by pos_reference either: {pos_reference}")
                    # Buscar por patrones similares en ambos campos
                    similar_orders_name = self.search([('name', 'ilike', pos_reference[-10:])])
                    similar_orders_ref = self.search([('pos_reference', 'ilike', pos_reference[-10:])])
                    _logger.warning(f"[L10N_DO_POS] Similar orders by name: {[o.name for o in similar_orders_name]}")
                    _logger.warning(f"[L10N_DO_POS] Similar orders by pos_reference: {[o.pos_reference for o in similar_orders_ref]}")
                    return {}
                else:
                    _logger.info(f"[L10N_DO_POS] Order found by pos_reference fallback: {order.id}")

            _logger.info(f"[L10N_DO_POS] Order found: {order.id} - Invoice: {order.account_move.id if order.account_move else 'None'}")

            # Si no tiene factura pero debería tenerla, intentar crearla
            if order.to_invoice and not order.account_move:
                _logger.info(f"[L10N_DO_POS] Order {order.id} should have invoice, creating...")
                try:
                    order.action_pos_order_invoice()
                    order = self.browse(order.id)  # Recargar
                    _logger.info(f"[L10N_DO_POS] ✅ Invoice created: {order.account_move.id if order.account_move else 'Failed'}")
                except Exception as e:
                    _logger.error(f"[L10N_DO_POS] ❌ Error creating invoice: {e}")

            # Procesar QR Code - Leer directamente desde account_move.qr_code
            qr_code_base64 = False
            qr_code_binary = False
            invoice_data = {}

            _logger.info(f"[L10N_DO_POS] === Iniciando procesamiento de QR para orden {order.id} ===")
            _logger.info(f"[L10N_DO_POS] - order.account_move existe: {bool(order.account_move)}")

            if order.account_move:
                _logger.info(f"[L10N_DO_POS] - order.account_move.id: {order.account_move.id}")
                _logger.info(f"[L10N_DO_POS] - order.account_move.name: {order.account_move.name}")

                # IMPORTANTE: Los campos Binary no se cargan por defecto en Odoo
                # El problema es que el QR se genera DESPUÉS de que se crea la factura
                # SOLUCIÓN NUCLEAR: Bypass completo del ORM con consulta SQL directa
                _logger.info(f"[L10N_DO_POS] 🔥 Usando consulta SQL directa para bypass de caché del ORM...")

                # Consulta SQL directa que ignora completamente el caché del ORM
                self.env.cr.execute("""
                    SELECT qr_code, l10n_do_ecf_security_code, l10n_do_ecf_sign_date
                    FROM account_move
                    WHERE id = %s
                """, (order.account_move.id,))

                sql_result = self.env.cr.fetchone()
                _logger.info(f"[L10N_DO_POS] - SQL query executed successfully")
                _logger.info(f"[L10N_DO_POS] - sql_result existe: {bool(sql_result)}")

                if sql_result:
                    qr_code_from_db, security_code_from_db, sign_date_from_db = sql_result
                    _logger.info(f"[L10N_DO_POS] - qr_code_from_db type: {type(qr_code_from_db)}")
                    _logger.info(f"[L10N_DO_POS] - qr_code_from_db existe: {bool(qr_code_from_db)}")
                    if qr_code_from_db:
                        _logger.info(f"[L10N_DO_POS] - qr_code_from_db length: {len(qr_code_from_db)}")
                    _logger.info(f"[L10N_DO_POS] - security_code_from_db: {security_code_from_db}")

                    invoice_data = {
                        'id': order.account_move.id,
                        'qr_code': qr_code_from_db,
                        'l10n_do_ecf_security_code': security_code_from_db,
                        'l10n_do_ecf_sign_date': sign_date_from_db
                    }
                else:
                    invoice_data = {}
                _logger.info(f"[L10N_DO_POS] - invoice_data recibido: {bool(invoice_data)}")
                _logger.info(f"[L10N_DO_POS] - invoice_data keys: {list(invoice_data.keys())}")
                _logger.info(f"[L10N_DO_POS] - invoice_data['qr_code'] raw value: {repr(invoice_data.get('qr_code'))[:200]}")
                _logger.info(f"[L10N_DO_POS] - invoice_data['qr_code'] type: {type(invoice_data.get('qr_code'))}")
                _logger.info(f"[L10N_DO_POS] - invoice_data['qr_code'] bool: {bool(invoice_data.get('qr_code'))}")
                if invoice_data.get('qr_code'):
                    _logger.info(f"[L10N_DO_POS] - invoice_data['qr_code'] longitud: {len(invoice_data['qr_code'])}")

                _logger.info(f"[L10N_DO_POS] - order.account_move.qr_code existe (antes de read): {bool(order.account_move.qr_code)}")
                if order.account_move.qr_code:
                    _logger.info(f"[L10N_DO_POS] - order.account_move.qr_code tipo: {type(order.account_move.qr_code)}")
                    _logger.info(f"[L10N_DO_POS] - order.account_move.qr_code longitud: {len(order.account_move.qr_code)}")
            else:
                _logger.warning(f"[L10N_DO_POS] - No hay account_move vinculado a la orden")

            _logger.info(f"[L10N_DO_POS] - order.QR_code (campo related) existe: {bool(order.QR_code)}")
            if order.QR_code:
                _logger.info(f"[L10N_DO_POS] - order.QR_code tipo: {type(order.QR_code)}")
                _logger.info(f"[L10N_DO_POS] - order.QR_code longitud: {len(order.QR_code)}")

            # Intentar obtener QR desde múltiples fuentes (prioridad a invoice_data)
            if order.account_move and invoice_data.get('qr_code'):
                _logger.info(f"[L10N_DO_POS] ✅ QR encontrado en invoice_data['qr_code'] {order.account_move.name}")
                qr_code_binary = invoice_data['qr_code']
            elif order.account_move and order.account_move.qr_code:
                _logger.info(f"[L10N_DO_POS] ✅ QR encontrado en account_move.qr_code {order.account_move.name}")
                qr_code_binary = order.account_move.qr_code
            elif order.QR_code:
                _logger.info(f"[L10N_DO_POS] ✅ QR encontrado en campo related de pos.order")
                qr_code_binary = order.QR_code
            else:
                _logger.warning(f"[L10N_DO_POS] ⚠️ No hay QR code disponible en orden {order.id}")

            # Procesar QR para base64 si existe
            if qr_code_binary:
                _logger.info(f"[L10N_DO_POS] Intentando convertir QR a base64...")
                _logger.info(f"[L10N_DO_POS] - Tipo de qr_code_binary: {type(qr_code_binary)}")

                try:
                    # IMPORTANTE: SQL directo devuelve memoryview, necesitamos convertir a bytes
                    if isinstance(qr_code_binary, memoryview):
                        _logger.info(f"[L10N_DO_POS] - Detectado memoryview, convirtiendo a bytes...")
                        qr_code_binary = bytes(qr_code_binary)
                        _logger.info(f"[L10N_DO_POS] - Convertido a bytes, longitud: {len(qr_code_binary)}")

                    # Ahora decodificar bytes a string base64
                    _logger.info(f"[L10N_DO_POS] - Decodificando bytes a ASCII...")
                    qr_code_base64 = 'data:image/png;base64,' + qr_code_binary.decode('ascii')
                    _logger.info(f"[L10N_DO_POS] ✅ QR code procesado para base64 ({len(qr_code_base64)} chars)")
                except Exception as e:
                    _logger.error(f"[L10N_DO_POS] ❌ Error procesando QR: {e}")
                    _logger.error(f"[L10N_DO_POS] - Tipo final: {type(qr_code_binary)}")
                    import traceback
                    _logger.error(f"[L10N_DO_POS] - Traceback: {traceback.format_exc()}")
            else:
                _logger.warning(f"[L10N_DO_POS] ⚠️ qr_code_binary está vacío, no se puede convertir a base64")

            # Logging detallado de campos individuales
            _logger.info(f"[L10N_DO_POS] Order fields debug:")
            _logger.info(f"  - ID: {order.id}")
            _logger.info(f"  - pos_reference: {order.pos_reference}")
            _logger.info(f"  - l10n_latam_document_number: {order.l10n_latam_document_number}")
            _logger.info(f"  - l10n_do_ecf_security_code: {order.l10n_do_ecf_security_code}")
            _logger.info(f"  - QR_code exists: {bool(order.QR_code)}")
            _logger.info(f"  - QR_code length: {len(order.QR_code) if order.QR_code else 0}")
            _logger.info(f"  - account_move: {order.account_move}")

            # Compilar datos fiscales completos
            _logger.info(f"[L10N_DO_POS] === Compilando fiscal_data ===")
            _logger.info(f"[L10N_DO_POS] - qr_code_base64 existe: {bool(qr_code_base64)}")
            _logger.info(f"[L10N_DO_POS] - qr_code_base64 longitud: {len(qr_code_base64) if qr_code_base64 else 0}")

            fiscal_data = {
                'id': order.id,
                'pos_reference': order.pos_reference,
                'ncf': order.l10n_latam_document_number,
                'l10n_latam_document_number': order.l10n_latam_document_number,
                'l10n_latam_document_type_id': order.l10n_latam_document_type_id.name if order.l10n_latam_document_type_id else False,
                'l10n_do_ncf_expiration_date': str(order.l10n_do_ncf_expiration_date) if order.l10n_do_ncf_expiration_date else False,
                'l10n_do_origin_ncf': order.origin_ncf,
                # Campos EDI - USAR DATOS DE SQL DIRECTO (invoice_data) EN LUGAR DE order. (cacheado)
                'l10n_do_ecf_security_code': invoice_data.get('l10n_do_ecf_security_code') or order.l10n_do_ecf_security_code,
                'l10n_do_ecf_sign_date': invoice_data.get('l10n_do_ecf_sign_date').strftime('%Y-%m-%d %H:%M:%S') if invoice_data.get('l10n_do_ecf_sign_date') else (order.l10n_do_ecf_sign_date.strftime('%Y-%m-%d %H:%M:%S') if order.l10n_do_ecf_sign_date else False),
                'QR_code': qr_code_binary or order.QR_code,
                'qr_code_img': qr_code_base64,
                'l10n_do_dgii_commercial_approval': order.l10n_do_dgii_commercial_approval,
                # CRÍTICO: Determinar si es ECF usando datos de SQL directo (invoice_data) o account_move
                'is_ecf_invoice': bool(
                    qr_code_binary or
                    invoice_data.get('l10n_do_ecf_security_code') or
                    (order.account_move and order.account_move.l10n_latam_document_type_id.doc_code_prefix in ['E31', 'E32', 'E33', 'E34', 'E41', 'E43', 'E44', 'E45', 'E46', 'E47'])
                ),
                'has_invoice': bool(order.account_move),
                'invoice_state': order.account_move.state if order.account_move else None
            }

            _logger.info(f"[L10N_DO_POS] ✅ Fiscal data compiled successfully")
            _logger.info(f"[L10N_DO_POS] - NCF: {fiscal_data['ncf']}")
            _logger.info(f"[L10N_DO_POS] - ECF Security Code: {fiscal_data['l10n_do_ecf_security_code']}")
            _logger.info(f"[L10N_DO_POS] - is_ecf_invoice: {fiscal_data['is_ecf_invoice']}")
            _logger.info(f"[L10N_DO_POS] - qr_code_img en fiscal_data: {bool(fiscal_data['qr_code_img'])}")
            _logger.info(f"[L10N_DO_POS] - qr_code_img longitud: {len(fiscal_data['qr_code_img']) if fiscal_data['qr_code_img'] else 0}")
            _logger.info(f"[L10N_DO_POS] - Todas las claves en fiscal_data: {list(fiscal_data.keys())}")

            _logger.info(f"[L10N_DO_POS] === RETORNANDO fiscal_data para orden {order.pos_reference} ===")
            return fiscal_data

        except Exception as e:
            _logger.error(f"[L10N_DO_POS] ❌❌❌ EXCEPTION CRÍTICA en get_fiscal_data_for_receipt ❌❌❌")
            _logger.error(f"[L10N_DO_POS] - pos_reference: {pos_reference}")
            _logger.error(f"[L10N_DO_POS] - Error: {str(e)}")
            _logger.error(f"[L10N_DO_POS] - Tipo de error: {type(e).__name__}")
            import traceback
            _logger.error(f"[L10N_DO_POS] - Traceback completo:\n{traceback.format_exc()}")
            return {}

