"""Límites de longitud del registro de facturación de la AEAT (RN-F-06, RN-F-07).

Viven en un solo módulo porque los usan a la vez clientes, facturas y registros:
si la AEAT cambia un límite, se cambia aquí y en ningún otro sitio.

Subir un límite es inocuo. Bajarlo no: la descripción general y el motivo de
una factura emitida ya no se comprueban al leerla, pero el nombre de las
partes, el número y el registro sí, porque sus objetos de valor validan al
construirse. Lo emitido antes dejaría de cargarse (RN-F-02).
"""

# Nombre o razón social del emisor y del destinatario (NombreRazon).
MAX_PARTY_NAME_LENGTH = 120
# Serie y número juntos (NumSerieFactura).
MAX_SERIES_NUMBER_LENGTH = 60
# Descripción general de la operación (DescripcionOperacion).
MAX_DESCRIPTION_LENGTH = 500
# NIF español: siempre nueve caracteres.
TAX_ID_LENGTH = 9
# Referencia propia del registro (RefExterna).
MAX_EXTERNAL_REF_LENGTH = 60
# Descripción del error devuelto por la AEAT.
MAX_ERROR_DESCRIPTION_LENGTH = 1500
# Bloque SistemaInformatico.
MAX_SYSTEM_NAME_LENGTH = 30
SYSTEM_ID_LENGTH = 2
MAX_SYSTEM_VERSION_LENGTH = 50
MAX_INSTALLATION_NUMBER_LENGTH = 100
