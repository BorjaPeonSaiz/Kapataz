"""Generador de datos sintéticos de Kapataz (ADR-020, Bloque 3).

Dos partes separadas:

- La API de datos pura: ``synthetic.build.build_dataset(seed)`` devuelve un
  ``SyntheticDataset`` (``synthetic.model``) con dataclasses y ``Decimal``, sin
  E/S. Se apoya en ``people`` (personas, NIF, teléfonos, IBAN y correos
  ficticios), ``catalogs``, ``fiscal`` (reglas fiscales provisionales),
  ``planning`` (qué documento va escaneado, con error sembrado o con trampa),
  ``others`` (los documentos «otro») y ``dates``. La usa ``seed_demo.py`` para
  crear con el dominio el profesional, los clientes, el catálogo y los
  presupuestos del espacio de demostración (RF-CF-04).
- El render de los PDF de ``samples/`` y de su verdad de referencia en
  ``evals/extraction/``: ``printed`` (lo que imprime cada documento, con
  ``amounts``), ``formats``, ``layouts`` y ``pdfkit`` (las maquetaciones y el
  PDF vectorial), ``scan`` (los escaneados), ``truth`` y ``schema`` (el JSON
  esperado y su esquema), ``fingerprint`` (huellas) y ``output`` (manifiesto,
  escritura y la comprobación de ``gen_synthetic.py --check``).

Todo es determinista con la semilla: el periodo es fijo y nada lee el reloj.
"""
