# -*- coding: utf-8 -*-
import base64
import io
import logging
import requests
import tempfile
import textwrap
import xmltodict
from collections import OrderedDict as od
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from datetime import datetime as dt
from lxml import etree

# Función para verificar la estructura de la firma en un XML
def verificar_firma_xml(xml_path):
    """Verifica si el archivo XML tiene una firma digital válida en estructura."""
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_data = f.read()

    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.XML(xml_data.encode("utf-8"), parser)

    # Verificar la presencia del nodo <Signature>
    signature_node = root.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")
    if signature_node is None:
        return "❌ El XML no contiene un nodo <Signature>."

    # Extraer valores clave
    digest_value = root.find(".//{http://www.w3.org/2000/09/xmldsig#}DigestValue")
    signature_value = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignatureValue")
    x509_certificate = root.find(".//{http://www.w3.org/2000/09/xmldsig#}X509Certificate")
    signature_method = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignatureMethod")
    digest_method = root.find(".//{http://www.w3.org/2000/09/xmldsig#}DigestMethod")

    resultados = {
        "Tiene nodo <Signature>": True,
        "DigestValue encontrado": digest_value.text if digest_value is not None else "❌ No encontrado",
        "SignatureValue encontrado": signature_value.text if signature_value is not None else "❌ No encontrado",
        "X509Certificate encontrado": x509_certificate.text[:100] + "..." if x509_certificate is not None else "❌ No encontrado",
        "SignatureMethod usado": signature_method.get("Algorithm") if signature_method is not None else "❌ No encontrado",
        "DigestMethod usado": digest_method.get("Algorithm") if digest_method is not None else "❌ No encontrado",
    }

    return resultados

# Ejecutar la verificación en el archivo `tmpiotbzt_t.xml`
verificacion_firma = verificar_firma_xml("/tmp/tmpiotbzt_t.xml")
verificacion_firma
