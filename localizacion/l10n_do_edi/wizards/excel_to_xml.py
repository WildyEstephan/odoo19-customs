# -*- coding: utf-8 -*-
from odoo import api, fields, models
import re, base64, tempfile, os
from openpyxl import load_workbook
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

def indent(elem, level=0):
    """Formatea el XML con sangrías."""
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level+1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    elif level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i
    return elem

def pretty_xml(element):
    """Genera XML con formato mejorado y saltos de línea correctos."""
    # Primero aplicar indentación básica
    indent(element)
    
    # Convertir a string
    xml_str = ET.tostring(element, encoding="utf-8", xml_declaration=True)
    xml_str = xml_str.decode("utf-8")
    
    # Agregar saltos de línea entre elementos hermanos de forma genérica
    import re
    
    # Dividir el XML en líneas para procesar cada línea
    lines = xml_str.split('\n')
    processed_lines = []
    
    for i, line in enumerate(lines):
        # Buscar patrones de elementos hermanos en cada línea
        # Patrón que busca elementos de cierre seguidos por elementos de apertura
        pattern = r'></([^>]+)><([^>]+)>'
        
        def add_newlines(match):
            closing_tag = match.group(1)
            opening_tag = match.group(2)
            
            # Calcular el nivel de indentación basado en la línea actual
            # Contar espacios al inicio de la línea para determinar el nivel actual
            current_indent = len(line) - len(line.lstrip())
            
            # Usar la misma indentación que la línea actual
            indent_spaces = " " * current_indent
                
            return f'></{closing_tag}>\n{indent_spaces}<{opening_tag}>'
        
        # Aplicar el reemplazo en la línea actual
        processed_line = re.sub(pattern, add_newlines, line)
        processed_lines.append(processed_line)
    
    # Unir las líneas procesadas
    xml_str = '\n'.join(processed_lines)
    
    return xml_str

class EcfCase(models.TransientModel):
    _name = "ecf.case"
    _description = "Caso ECF generado desde Excel"

    wizard_id    = fields.Many2one('ecf.excel.to.xml', ondelete='cascade')
    name         = fields.Char(string="Caso Prueba", readonly=True)
    xml_file     = fields.Binary(string="Archivo XML", readonly=True)
    xml_filename = fields.Char(string="Nombre Archivo", readonly=True)
    dgii_result  = fields.Text(string="Resultado DGII", readonly=True)
    is_authorized = fields.Boolean(string="Autorizado", readonly=True, default=False)
    modified_xml_file = fields.Binary(string="XML Modificado", help="Sube un archivo XML modificado para reemplazar el original")
    modified_xml_filename = fields.Char(string="Nombre XML Modificado")
    use_modified_xml = fields.Boolean(string="Usar XML Modificado", default=False, help="Marcar para usar el archivo XML modificado en lugar del original")
    file_version = fields.Integer(string="Versión", default=1, readonly=True, help="Versión del archivo actual")

    def action_send_xml(self):
        """Método para enviar el XML a la DGII."""
        try:
            # Obtener la empresa del wizard
            company = self.env.company
            
            # Verificar que la empresa tenga configuración ECF
            if not company.l10n_do_ecf_activated:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'La empresa no tiene ECF activado',
                        'type': 'danger',
                    }
                }
            
            # Verificar certificado
            if not company.l10n_do_pkcs12_file or not company.l10n_do_pkcs12_password:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'No se encontró el certificado en la empresa o la contraseña está vacía',
                        'type': 'danger',
                    }
                }
            
            # Obtener token de autenticación
            edi_format = self.env['account.edi.format'].search([('code', '=', 'dgii_ecf')], limit=1)
            if not edi_format:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'No se encontró el formato EDI DGII ECF',
                        'type': 'danger',
                    }
                }
            
            token = edi_format._get_token(company)
            if not token:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'No se pudo obtener el token de autenticación',
                        'type': 'danger',
                    }
                }
            
            # Decodificar el XML (original o modificado)
            if self.use_modified_xml and self.modified_xml_file:
                xml_data = base64.b64decode(self.modified_xml_file)
                xml_filename_for_log = self.modified_xml_filename or "XML modificado"
                original_filename = self.modified_xml_filename
            else:
                xml_data = base64.b64decode(self.xml_file)
                xml_filename_for_log = self.xml_filename
                original_filename = self.xml_filename
            
            # Crear archivo temporal con el XML
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml_file:
                temp_xml_file.write(xml_data)
                temp_xml_file_path = temp_xml_file.name
            
            # Generar nombre del archivo firmado (remover _unsigned del nombre original)
            if original_filename and '_unsigned' in original_filename:
                signed_base_name = original_filename.replace('_unsigned', '')
            else:
                signed_base_name = original_filename or "signed_file.xml"
            
            # Asegurar que termine en .xml
            if not signed_base_name.endswith('.xml'):
                signed_base_name += '.xml'

            signed_filename = os.path.join(os.path.dirname(temp_xml_file_path), signed_base_name)
            edi_format._sign_xml(temp_xml_file_path, signed_filename, company)
            
            # Enviar a la DGII (asumimos que no es resumen)
            response = edi_format._send_xml_to_dgii(signed_filename, company, token, is_resumen=False)
            
            # Formatear respuesta y determinar si está autorizado
            is_authorized = False
            file_info = f"Archivo usado: {xml_filename_for_log} (v{self.file_version})"
            
            if response.get('error'):
                result_message = f"{file_info}\nError: {response.get('error')}\nMensaje: {response.get('mensaje', '')}"
            elif response.get('trackId'):
                result_message = f"{file_info}\nTrack ID: {response.get('trackId')}\nEstado: Enviado correctamente"
                is_authorized = True
            elif response.get('codigo') in ['1', '4']:
                result_message = f"{file_info}\nRespuesta: {response}\nEstado: Autorizado"
                is_authorized = True
            else:
                result_message = f"{file_info}\nRespuesta: {response}"
            
            # Guardar resultado en el campo
            self.write({
                'dgii_result': result_message,
                'is_authorized': is_authorized
            })
            
            # Limpiar archivos temporales
            try:
                os.unlink(temp_xml_file_path)
                os.unlink(signed_filename)
            except:
                pass
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'ecf.excel.to.xml',
                'res_id': self.wizard_id.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except Exception as e:
            error_message = f"Error al enviar XML: {str(e)}"
            self.write({
                'dgii_result': error_message
            })
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'ecf.excel.to.xml',
                'res_id': self.wizard_id.id,
                'view_mode': 'form',
                'target': 'new',
            }

    @api.onchange('modified_xml_file')
    def _onchange_modified_xml_file(self):
        """Limpia el resultado cuando se sube un nuevo archivo modificado"""
        if self.modified_xml_file:
            self.dgii_result = ""
            self.is_authorized = False
            # Marcar automáticamente para usar el archivo modificado
            self.use_modified_xml = True
            # Incrementar versión del archivo
            self.file_version += 1

    @api.onchange('use_modified_xml')
    def _onchange_use_modified_xml(self):
        """Maneja cambios en el checkbox de usar XML modificado"""
        if not self.use_modified_xml:
            # Si se desmarca, limpiar el archivo modificado
            self.modified_xml_file = False
            self.modified_xml_filename = ""
            # Limpiar resultado si había uno
            if self.dgii_result:
                self.dgii_result = ""
                self.is_authorized = False

class ExcelToXmlWizard(models.TransientModel):
    _name = "ecf.excel.to.xml"
    _description = "Wizard para importar Excel y generar XMLs"

    file      = fields.Binary(string="Archivo Excel (.xlsx)", required=True)
    file_name = fields.Char(string="Nombre de archivo")
    cases_ids = fields.One2many('ecf.case', 'wizard_id', string="Casos Generados")

    def action_generate_xml(self):
        # 1) Leer Excel con openpyxl
        data = base64.b64decode(self.file)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(data); tmp.flush()
            wb = load_workbook(tmp.name, data_only=True)
        ws = wb["ECF"]

        # 2) Cabecera y filas
        rows = list(ws.iter_rows(values_only=True))
        headers = [str(h).strip() for h in rows[0]]
        self.cases_ids.unlink()

        for vals in rows[1:]:
            row = { hdr: (str(v).strip() if v is not None else None) for hdr, v in zip(headers, vals) }
            # normalizar: vacíos o "#e" -> None
            for k in list(row):
                if not row[k] or row[k]=="#e":
                    row[k] = None

            case_id = row.get("CasoPrueba")
            if not case_id:
                continue

            xml_str = self._build_xml(row, headers)
            xml_bytes = xml_str.encode("utf-8")
            
            # Usar el nombre del archivo del Excel si está disponible, sino usar el caso de prueba
            file_name = row.get("xml_filename")
            if file_name:
                # Remover .xml si ya lo tiene y agregar _unsigned.xml
                base_name = file_name.replace('.xml', '') if file_name.endswith('.xml') else file_name
                xml_filename = f"{base_name}_unsigned.xml"
            else:
                xml_filename = f"{case_id}_unsigned.xml"
                
            self.env['ecf.case'].create({
                'wizard_id':    self.id,
                'name':         case_id,
                'xml_file':     base64.b64encode(xml_bytes),
                'xml_filename': xml_filename,
            })

        # 3) Volver a mostrar el wizard con la lista de casos
        return {
            'name':      "Casos Generados",
            'type':      'ir.actions.act_window',
            'res_model': 'ecf.excel.to.xml',
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }

    def _build_xml(self, row, cols):
        """Construye el XML de un solo registro según la lógica definida."""
        root = ET.Element("ECF")
        enc  = ET.SubElement(root, "Encabezado")

        # --- Secuencias según XSD ---
        idoc_seq      = ["TipoeCF","ENCF","FechaVencimientoSecuencia","IndicadorEnvioDiferido",
                         "IndicadorMontoGravado","IndicadorServicioTodoIncluido","TipoIngresos",
                         "TipoPago","FechaLimitePago","TerminoPago","TablaFormasPago"]
        emisor_seq    = ["RNCEmisor","RazonSocialEmisor","NombreComercial","DireccionEmisor",
                         "Municipio","Provincia","TablaTelefonoEmisor","CorreoEmisor","WebSite",
                         "ActividadEconomica","CodigoVendedor","NumeroFacturaInterna","NumeroPedidoInterno",
                         "ZonaVenta","RutaVenta","InformacionAdicionalEmisor","FechaEmision"]
        comprador_seq = ["RNCComprador","RazonSocialComprador","ContactoComprador","CorreoComprador",
                         "DireccionComprador","MunicipioComprador","ProvinciaComprador","FechaEntrega",
                         "ContactoEntrega","DireccionEntrega","TelefonoAdicional","FechaOrdenCompra",
                         "NumeroOrdenCompra","CodigoInternoComprador","NumeroContenedor",
                         "NumeroReferencia","ResponsablePago","InformacionAdicionalComprador"]
        totales_seq   = ["MontoGravadoTotal","MontoGravadoI1","MontoGravadoI2","MontoGravadoI3",
                         "MontoExento","ITBIS1","ITBIS2","ITBIS3","TotalITBIS","TotalITBIS1",
                         "TotalITBIS2","TotalITBIS3","MontoImpuestoAdicional","ImpuestosAdicionales",
                         "MontoTotal","MontoNoFacturable","MontoPeriodo","SaldoAnterior",
                         "MontoAvancePago","ValorPagar","TotalITBISRetenido","TotalISRRetencion",
                         "TotalITBISPercepcion","TotalISRPercepcion"]
        item_seq      = ["NumeroLinea","IndicadorFacturacion","NombreItem","IndicadorBienoServicio",
                         "CantidadItem","UnidadMedida","PrecioUnitarioItem","PrecioOtraMoneda",
                         "MontoItemOtraMoneda","MontoItem"]
        infref_seq    = ["NCFModificado","RNCOtroContribuyente","FechaNCFModificado","CodigoModificacion"]

        fp_pat   = re.compile(r'^(FormaPago|MontoPago)\[(\d+)\]$')
        tel_pat  = re.compile(r'^TelefonoEmisor(?:\[(\d+)\])?$')
        item_pat = re.compile(r'^(\w+)\[(\d+)\]$')

        # Versión
        if row.get("Version"):
            ET.SubElement(enc, "Version").text = row["Version"]

        # IdDoc
        idoc = ET.SubElement(enc, "IdDoc")
        for tag in idoc_seq:
            if tag=="TablaFormasPago":
                idxs = sorted({int(m.group(2)) for c in cols if (m:=fp_pat.match(c))})
                if idxs:
                    tbl = ET.SubElement(idoc, "TablaFormasPago")
                    for i in idxs:
                        fp = row.get(f"FormaPago[{i}]")
                        mp = row.get(f"MontoPago[{i}]")
                        if fp or mp:
                            dep = ET.SubElement(tbl, "FormaDePago")
                            if fp: ET.SubElement(dep, "FormaPago").text = fp
                            if mp: ET.SubElement(dep, "MontoPago").text = mp
            else:
                col = "ENCF" if tag=="ENCF" else tag
                val = row.get(col)
                if val:
                    ET.SubElement(idoc, tag if tag!="ENCF" else "eNCF").text = val

        # Emisor
        em = ET.SubElement(enc, "Emisor")
        for tag in emisor_seq:
            if tag=="TablaTelefonoEmisor":
                idxs = sorted({int(m.group(1)) for c in cols if (m:=tel_pat.match(c)) and m.group(1)})
                if not idxs and row.get("TelefonoEmisor"):
                    idxs = [1]
                if idxs:
                    tt = ET.SubElement(em, "TablaTelefonoEmisor")
                    for i in idxs:
                        val = row.get(f"TelefonoEmisor[{i}]") or row.get("TelefonoEmisor")
                        if val:
                            ET.SubElement(tt, "TelefonoEmisor").text = val
            else:
                val = row.get(tag)
                if val:
                    ET.SubElement(em, tag).text = val

        # Comprador
        comp = ET.SubElement(enc, "Comprador")
        for tag in comprador_seq:
            val = row.get(tag)
            if val:
                ET.SubElement(comp, tag).text = val

        # Totales
        tot = ET.SubElement(enc, "Totales")
        for tag in totales_seq:
            val = row.get(tag)
            if val:
                ET.SubElement(tot, tag).text = val

        # DetallesItems
        det = ET.SubElement(root, "DetallesItems")
        idxs = sorted({int(m.group(2)) for c in cols if (m:=item_pat.match(c)) and m.group(1) in item_seq})
        for i in idxs:
            # Verificar si hay al menos un campo con datos para este item
            has_data = any(row.get(f"{tag}[{i}]") for tag in item_seq)
            if has_data:
                itm = ET.SubElement(det, "Item")
                for tag in item_seq:
                    val = row.get(f"{tag}[{i}]")
                    if val:
                        ET.SubElement(itm, tag).text = val

        # InformacionReferencia
        if any(row.get(t) for t in infref_seq):
            inf = ET.SubElement(root, "InformacionReferencia")
            for t in infref_seq:
                val = row.get(t)
                if val:
                    ET.SubElement(inf, t).text = val

        # FechaHoraFirma - Agregar fecha y hora actual en zona horaria de República Dominicana (UTC-4)
        utc_minus_4 = timezone(timedelta(hours=-4))
        fecha_hora_rd = datetime.now(utc_minus_4)
        fecha_hora_actual = fecha_hora_rd.strftime("%d-%m-%Y %H:%M:%S")
        ET.SubElement(root, "FechaHoraFirma").text = fecha_hora_actual

        xml_str = pretty_xml(root)
        return xml_str
