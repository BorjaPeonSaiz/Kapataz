# Estimación de costes y beneficios

Cuota de **25 € al mes IVA incluido** (20,66 € sin IVA), cobro por transferencia ([ADR-0019](../adr/0019-cobro-por-transferencia.md)) y modelo **Claude Sonnet 5.5**. Importes sin IVA. Actualizado el 2026-10-29.

## Gastos

### Fijos (al mes, sea cual sea el número de clientes)

| Concepto | Al mes |
| --- | ---: |
| Servidores en la UE (aplicación, base de datos, almacenamiento, copias) | 150,00 € |
| Dominio (20 € al año) | 1,67 € |
| Cuenta bancaria de empresa (0 € si es una cuenta sin comisiones) | 15,00 € |
| GitHub, email (SMTP de Hostinger, solo recuperación de contraseña) y monitorización (planes gratuitos) | 0,00 € |
| Copias de seguridad externas (Backblaze B2, plan gratuito hasta 10 GB; [ADR-0021](../adr/0021-copias-de-seguridad.md)) | 0,00 € |
| **Total fijos** | **166,67 €** |

### Por cliente (al mes, uso típico)

| Concepto | Al mes |
| --- | ---: |
| IA: 100 documentos (≈ 0,027 € cada uno) | 2,65 € |
| IA: 60 consultas al agente (≈ 0,023 € cada una) | 1,40 € |
| **Total por cliente** | **4,05 €** |

## Mínimo de clientes para cubrir gastos

Cada cliente deja 20,66 € − 4,05 € = **16,61 €** para pagar los gastos fijos.

**166,67 € ÷ 16,61 € = 10,03 → hacen falta 11 clientes.**

## Beneficio según el número de clientes

| Clientes | Ingresos | Gastos IA | Gastos fijos | **Beneficio al mes** | **Beneficio al año** |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 11 | 227,27 € | 44,55 € | 166,67 € | **16,05 €** | **192,60 €** |
| 25 | 516,53 € | 101,25 € | 166,67 € | **248,61 €** | **2.983,32 €** |
| 50 | 1.033,06 € | 202,50 € | 166,67 € | **663,89 €** | **7.966,68 €** |
| 100 | 2.066,12 € | 405,00 € | 166,67 € | **1.494,45 €** | **17.933,40 €** |

Beneficio antes de impuestos. No incluye impuestos sobre el beneficio, cuota de autónomos o costes de sociedad, gestoría, seguros, impagos ni tu tiempo.

## Límites por cliente

Para que ningún cliente dé pérdidas, la cuota incluye al mes:

| Límite | Valor |
| --- | --- |
| Documentos | 300 (cada documento cuenta hasta 3 páginas) |
| Consultas al agente | 150 |
| Tope de gasto de IA | 12 € |

Un cliente que agote los límites cuesta unos 11,45 € de IA. Con 100 clientes sigue dejando unos 7,50 € al mes. Al llegar a un límite, o si no paga, no pierde el acceso: solo se desactiva la IA ([ADR-0020](../adr/0020-modo-sin-ia-y-notificaciones.md)).

## Validación

Las cifras de IA son estimaciones (precios de Sonnet 5.5 de 2026-10-06: 2 $ / 10 $ por millón de tokens de entrada / salida). En la Fase 3 se medirán con unas 50 facturas reales y se actualizará este documento.
