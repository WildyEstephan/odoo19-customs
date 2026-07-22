import lxml.html
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class Partner(models.Model):
    _inherit = "res.partner"

    def _format_l10n_do_dgii_payer_type(self, vat, name, country_id):
        """ Compute the type of partner depending on soft decisions"""
        company_id = self.env["res.company"].search(
            [("id", "=", self.env.user.company_id.id)]
        )
        partner = {'l10n_do_dgii_tax_payer_type': ''}

        # Si no tiene RNC/VAT, el tipo de contribuyente debe ser vacío
        if not vat or str(vat).strip() == '':
            partner['l10n_do_dgii_tax_payer_type'] = ''
            return partner

        vat = str(vat if vat else name)
        is_dominican_partner = bool(country_id == self.env.ref("base.do").id)

        if country_id and not is_dominican_partner:
            partner['l10n_do_dgii_tax_payer_type'] = "foreigner"

        elif vat and (
            not partner['l10n_do_dgii_tax_payer_type']
            or partner['l10n_do_dgii_tax_payer_type'] == "non_payer"
        ):
            if country_id and is_dominican_partner:
                if vat.isdigit() and len(vat) in [9, 10]:
                    if not vat:
                        vat = vat
                    if name and "MINISTERIO" in name:
                        partner['l10n_do_dgii_tax_payer_type'] = "governmental"
                    elif name and any(
                        [n for n in ("IGLESIA", "ZONA FRANCA") if n in name]
                    ):
                        partner['l10n_do_dgii_tax_payer_type'] = "special"
                    elif vat.startswith("1"):
                        partner['l10n_do_dgii_tax_payer_type'] = "taxpayer"
                    elif vat.startswith("4"):
                        partner['l10n_do_dgii_tax_payer_type'] = "nonprofit"
                    else:
                        partner['l10n_do_dgii_tax_payer_type'] = "taxpayer"

                elif len(vat) == 11:
                    # Cédula dominicana (11 dígitos) siempre es "non_payer" (Cliente de consumo)
                    if vat.isdigit():
                        if not vat:
                            vat = vat
                        partner['l10n_do_dgii_tax_payer_type'] = "non_payer"
                    else:
                        partner['l10n_do_dgii_tax_payer_type'] = "non_payer"
                else:
                    partner['l10n_do_dgii_tax_payer_type'] = "non_payer"
        elif not partner['l10n_do_dgii_tax_payer_type']:
            partner['l10n_do_dgii_tax_payer_type'] = "taxpayer"
        else:
            partner['l10n_do_dgii_tax_payer_type'] = (
                partner['l10n_do_dgii_tax_payer_type']
            )

        return partner

    @api.model
    def format_from_dggi(self, vat=None, country_id=None):
        is_dominican_partner = country_id and (int(country_id) == self.env.ref("base.do").id)
        exist_rnc = self.search_count([('vat', '=', vat)])

        if is_dominican_partner and vat and not exist_rnc:
            if len(vat) not in [9, 10, 11]:
                raise UserError(
                    _(
                        "Check Vat Format or should not have any Caracter like '-'"
                    )
                )
            else:
                url = 'https://dgii.gov.do/app/WebApps/ConsultasWeb2/ConsultasWeb/consultas/rnc.aspx'
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (python-stdnum)',
                })

                document = lxml.html.fromstring(
                session.get(url, timeout=30).text)

                validation = document.find('.//input[@name="__EVENTVALIDATION"]').get('value')
                viewstate = document.find('.//input[@name="__VIEWSTATE"]').get('value')
                data = {
                    '__EVENTVALIDATION': validation,
                    '__VIEWSTATE': viewstate,
                    'ctl00$cphMain$btnBuscarPorRNC': 'Buscar',
                    'ctl00$cphMain$txtRNCCedula': vat,
                }
                # Do the actual request
                document = lxml.html.fromstring(
                    session.post(url, data=data, timeout=30).text)

                result = document.find('.//div[@id="cphMain_divBusqueda"]')
                message = document.findtext('.//*[@id="cphMain_lblInformacion"]')

                if result is not None:
                    hearder = []
                    keys = []

                    for x in result.findall('.//tr/td'):
                        if x.attrib:
                            hearder.append(x.text.strip())
                        else:
                            keys.append(x.text.strip())

                    if message:
                        data = {
                            'validation_message': message.strip(),
                        }
                    else:
                        data = {
                            'validation_message': 'Cédula/RNC es Válido',
                        }

                    data.update(zip(hearder, keys))

                    if data.get(u'Nombre/Razón Social', ''):
                        data["name"] = data[u'Nombre/Razón Social']
                        data.update(self._format_l10n_do_dgii_payer_type(vat, data["name"], country_id))
                        return data
                    else:
                        return False

    def action_dgii_autocomplete(self):
        """Método para botón de autocompletado DGII en POS"""
        if not self.vat or not self.country_id:
            raise UserError(_("Por favor ingrese el RNC y seleccione el país antes de usar el autocompletado DGII."))

        try:
            data = self.format_from_dggi(self.vat, self.country_id.id)
            if data:
                # Actualizar campos con los datos obtenidos
                self.write({
                    'name': data.get('name', self.name),
                    'l10n_do_dgii_tax_payer_type': data.get('l10n_do_dgii_tax_payer_type', self.l10n_do_dgii_tax_payer_type)
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Éxito'),
                        'message': _('Datos actualizados desde DGII exitosamente.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_("No se encontraron datos para el RNC proporcionado o ya existe un cliente con este RNC."))
        except Exception as e:
            raise UserError(_("Error al consultar DGII: %s") % str(e))
