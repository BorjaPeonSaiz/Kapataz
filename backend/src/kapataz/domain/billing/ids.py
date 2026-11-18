"""Identificadores de facturación.

``NewType`` sobre ``UUID``: mypy impide pasar el id de un presupuesto donde se
espera el de una factura, sin coste en tiempo de ejecución.
"""

from typing import NewType
from uuid import UUID

QuoteId = NewType("QuoteId", UUID)
QuoteVersionId = NewType("QuoteVersionId", UUID)
QuoteLineId = NewType("QuoteLineId", UUID)
InvoiceId = NewType("InvoiceId", UUID)
PaymentId = NewType("PaymentId", UUID)
BillingRecordId = NewType("BillingRecordId", UUID)
