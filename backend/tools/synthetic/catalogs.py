"""Catálogos de referencia y plantillas de trabajos de cada oficio (ADR-020).

Los precios de referencia son orientativos de un autónomo de Cantabria; cada
documento los varía entre un -8 % y un +10 %, y un 3 % más en el segundo año.
"""

from dataclasses import dataclass
from decimal import Decimal

from kapataz.domain.billing.codes import RecipientType
from synthetic.model import CatalogEntryData, Trade

PRIVATE = RecipientType.PRIVATE
COMMUNITY = RecipientType.COMMUNITY
BUSINESS = RecipientType.BUSINESS


def _entry(
    key: str,
    concept: str,
    detail: str,
    unit: str,
    price: str,
    *,
    material: bool = False,
) -> CatalogEntryData:
    return CatalogEntryData(
        key=key,
        concept=concept,
        detail=detail,
        unit=unit,
        reference_price=Decimal(price),
        is_material=material,
    )


ELECTRICIAN_CATALOG = (
    _entry(
        "desplazamiento",
        "Desplazamiento a domicilio",
        "Desplazamiento del técnico con vehículo y herramienta dentro de la zona de servicio.",
        "ud",
        "25.00",
    ),
    _entry(
        "oficial",
        "Mano de obra de oficial electricista",
        "Hora de oficial de primera electricista, con pequeño material de fijación incluido.",
        "h",
        "32.00",
    ),
    _entry(
        "ayudante",
        "Mano de obra de ayudante",
        "Hora de ayudante de electricista para tendido de líneas y apertura de rozas.",
        "h",
        "22.00",
    ),
    _entry(
        "punto_luz",
        "Punto de luz sencillo",
        "Punto de luz sencillo con caja de registro, tubo corrugado y conductor de 1,5 mm² "
        "hasta el cuadro, con mecanismo de gama media.",
        "ud",
        "38.00",
    ),
    _entry(
        "punto_conmutado",
        "Punto de luz conmutado",
        "Punto de luz conmutado desde dos lugares, con cajas, tubo, conductor de 1,5 mm² y "
        "dos conmutadores de gama media.",
        "ud",
        "52.00",
    ),
    _entry(
        "base_16a",
        "Base de enchufe 16 A",
        "Base de enchufe schuko de 16 A con toma de tierra, línea de 2,5 mm² bajo tubo "
        "corrugado y caja de mecanismo.",
        "ud",
        "34.00",
    ),
    _entry(
        "toma_25a",
        "Toma de cocina 25 A",
        "Toma de 25 A para placa de cocina con línea independiente de 6 mm² desde el cuadro "
        "y su magnetotérmico.",
        "ud",
        "58.00",
    ),
    _entry(
        "cable_2_5",
        "Cable H07V-K 2,5 mm²",
        "Conductor de cobre flexible H07V-K de 2,5 mm² en colores normalizados.",
        "m",
        "0.95",
        material=True,
    ),
    _entry(
        "cable_6",
        "Cable H07V-K 6 mm²",
        "Conductor de cobre flexible H07V-K de 6 mm² para circuitos de cocina y horno.",
        "m",
        "2.10",
        material=True,
    ),
    _entry(
        "tubo",
        "Tubo corrugado de 20 mm",
        "Tubo corrugado reforzado de 20 mm de diámetro para instalación empotrada.",
        "m",
        "0.65",
        material=True,
    ),
    _entry(
        "cuadro",
        "Cuadro general de mando y protección",
        "Cuadro empotrable de 18 módulos con interruptor general, diferencial y "
        "magnetotérmicos por circuito, montado y conexionado.",
        "ud",
        "245.00",
        material=True,
    ),
    _entry(
        "diferencial",
        "Interruptor diferencial 40 A 30 mA",
        "Interruptor diferencial bipolar de 40 A y 30 mA de sensibilidad, clase AC.",
        "ud",
        "64.00",
        material=True,
    ),
    _entry(
        "magnetotermico",
        "Magnetotérmico 16 A",
        "Interruptor magnetotérmico bipolar de 16 A, curva C, 6 kA.",
        "ud",
        "13.80",
        material=True,
    ),
    _entry(
        "panel_led",
        "Luminaria LED de panel 60x60",
        "Panel LED de 40 W y 4000 K para falso techo modular, con driver y garantía de cinco años.",
        "ud",
        "46.00",
        material=True,
    ),
    _entry(
        "foco_led",
        "Foco empotrable LED",
        "Foco LED empotrable de 7 W, luz neutra y aro blanco, con su caja de empotrar.",
        "ud",
        "14.50",
        material=True,
    ),
    _entry(
        "cie",
        "Certificado de instalación eléctrica (CIE)",
        "Redacción del certificado de instalación eléctrica, mediciones y tramitación ante "
        "la Dirección General de Industria.",
        "ud",
        "140.00",
    ),
    _entry(
        "revision_comunidad",
        "Revisión de la instalación de la comunidad",
        "Revisión de cuadros, alumbrado de escalera y garaje, y medición de la toma de "
        "tierra del edificio, con informe.",
        "ud",
        "165.00",
    ),
    _entry(
        "portero",
        "Placa de portero automático",
        "Placa de calle de dos líneas con alimentador, abrepuertas y teléfonos de vivienda.",
        "ud",
        "215.00",
        material=True,
    ),
    _entry(
        "toma_tierra",
        "Toma de tierra con pica",
        "Pica de acero cobrizado de 2 m, conductor de 35 mm² y arqueta de registro.",
        "ud",
        "85.00",
    ),
    _entry(
        "detector",
        "Detector de presencia",
        "Detector de presencia de techo para el alumbrado de zonas comunes, instalado.",
        "ud",
        "39.00",
        material=True,
    ),
    _entry(
        "lampara",
        "Lámpara de techo (solo suministro)",
        "Lámpara de techo de diseño elegida por el cliente, sin instalación.",
        "ud",
        "89.00",
    ),
)

BRICKLAYER_CATALOG = (
    _entry(
        "oficial",
        "Oficial de primera albañil",
        "Hora de oficial de primera albañil con herramienta propia.",
        "h",
        "27.00",
    ),
    _entry(
        "peon",
        "Peón de albañil",
        "Hora de peón para acarreo de material, limpieza y ayudas.",
        "h",
        "20.50",
    ),
    _entry(
        "demolicion",
        "Demolición de tabique",
        "Demolición de tabique de ladrillo con medios manuales, con carga de escombros "
        "sobre contenedor.",
        "m²",
        "9.50",
    ),
    _entry(
        "escombros",
        "Contenedor y retirada de escombros",
        "Contenedor de 5 m³, transporte y canon de vertedero autorizado.",
        "ud",
        "185.00",
    ),
    _entry(
        "tabique",
        "Tabique de ladrillo hueco doble",
        "Tabique de ladrillo hueco doble de 7 cm recibido con mortero de cemento M-5, "
        "aplomado y con sus mochetas.",
        "m²",
        "23.50",
    ),
    _entry(
        "enfoscado",
        "Enfoscado de mortero",
        "Enfoscado maestreado y fratasado con mortero de cemento M-5 en paramentos verticales.",
        "m²",
        "13.80",
    ),
    _entry(
        "alicatado",
        "Alicatado de paredes",
        "Alicatado con azulejo cerámico recibido con cemento cola, cortes y rejuntado; "
        "pieza aportada por el cliente.",
        "m²",
        "25.00",
    ),
    _entry(
        "solado",
        "Solado de gres porcelánico",
        "Solado de gres porcelánico recibido con cemento cola, rejuntado y limpieza final; "
        "pieza aportada por el cliente.",
        "m²",
        "27.50",
    ),
    _entry(
        "recrecido",
        "Recrecido de mortero autonivelante",
        "Recrecido de mortero autonivelante de 4 cm de espesor medio, con banda perimetral.",
        "m²",
        "12.40",
    ),
    _entry(
        "trasdosado",
        "Trasdosado de placa de yeso laminado",
        "Trasdosado autoportante con placa de yeso laminado de 15 mm, perfilería de 48 mm "
        "y aislamiento de lana mineral.",
        "m²",
        "22.00",
    ),
    _entry(
        "solera",
        "Solera de hormigón",
        "Solera de hormigón HM-20 de 15 cm de espesor con mallazo electrosoldado, vertida "
        "y reglada.",
        "m²",
        "19.50",
    ),
    _entry(
        "bordillo",
        "Colocación de bordillo",
        "Bordillo de hormigón prefabricado recibido sobre base de hormigón y rejuntado.",
        "m",
        "15.80",
    ),
    _entry(
        "ayudas",
        "Ayudas de albañilería a instalaciones",
        "Apertura y tapado de rozas, recibido de cajas y pasos de instalaciones de "
        "fontanería y electricidad.",
        "pa",
        "480.00",
    ),
    _entry(
        "andamio",
        "Andamio tubular",
        "Montaje, alquiler semanal y desmontaje de andamio tubular homologado.",
        "semana",
        "210.00",
    ),
    _entry(
        "impermeabilizacion",
        "Impermeabilización de terraza",
        "Impermeabilización con lámina asfáltica de doble capa y protección con mortero.",
        "m²",
        "31.00",
    ),
    _entry(
        "cemento",
        "Cemento gris en saco de 25 kg",
        "Saco de cemento gris CEM II de 25 kg.",
        "saco",
        "6.40",
        material=True,
    ),
    _entry(
        "arena",
        "Arena de río lavada",
        "Arena de río lavada a granel.",
        "m³",
        "34.00",
        material=True,
    ),
    _entry(
        "cola",
        "Cemento cola flexible C2",
        "Saco de 25 kg de cemento cola flexible C2 TE S1.",
        "saco",
        "14.90",
        material=True,
    ),
    _entry(
        "ladrillo",
        "Ladrillo hueco doble",
        "Ladrillo cerámico hueco doble de 24 x 11,5 x 7 cm.",
        "ud",
        "0.42",
        material=True,
    ),
)

CATALOGS = {Trade.ELECTRICIAN: ELECTRICIAN_CATALOG, Trade.BRICKLAYER: BRICKLAYER_CATALOG}


@dataclass(frozen=True, slots=True)
class TemplateItem:
    """Línea posible de un trabajo: cantidad entre ``low`` y ``high`` con paso ``step``.

    ``chance`` es la probabilidad, en tanto por ciento, de que la línea aparezca.
    """

    key: str
    low: str
    high: str
    step: str = "1"
    chance: int = 100
    outside_works: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class JobTemplate:
    """Trabajo típico del oficio. ``contractor`` es solo para constructoras."""

    subject: str
    recipients: frozenset[RecipientType]
    items: tuple[TemplateItem, ...]
    contractor: bool = False
    detailed: bool = False


def _job(
    subject: str,
    recipients: tuple[RecipientType, ...],
    *items: TemplateItem,
    contractor: bool = False,
    detailed: bool = False,
) -> JobTemplate:
    return JobTemplate(
        subject=subject,
        recipients=frozenset(recipients),
        items=items,
        contractor=contractor,
        detailed=detailed,
    )


T = TemplateItem

ELECTRICIAN_JOBS = (
    _job(
        "Reparación de avería eléctrica",
        (PRIVATE, COMMUNITY, BUSINESS),
        T("desplazamiento", "1", "1"),
        T("oficial", "1", "4", "0.5"),
        T("magnetotermico", "1", "2", chance=40),
        T("diferencial", "1", "1", chance=25),
    ),
    _job(
        "Ampliación de enchufes y puntos de luz",
        (PRIVATE, BUSINESS),
        T("punto_luz", "1", "4", chance=80),
        T("base_16a", "2", "6"),
        T("cable_2_5", "15", "60", chance=70),
        T("tubo", "10", "40", chance=60),
        T("oficial", "2", "8", "0.5"),
    ),
    _job(
        "Reforma eléctrica de cocina",
        (PRIVATE,),
        T("punto_luz", "2", "4"),
        T("base_16a", "4", "8"),
        T("toma_25a", "1", "1"),
        T("foco_led", "4", "8", chance=60),
        T("cable_2_5", "20", "50"),
        T("cable_6", "8", "15"),
        T("tubo", "15", "40"),
        T("magnetotermico", "1", "2", chance=50),
        T("oficial", "4", "10", "0.5"),
    ),
    _job(
        "Revisión de la instalación de la comunidad",
        (COMMUNITY,),
        T("revision_comunidad", "1", "1"),
        T("detector", "2", "6", chance=60),
        T("foco_led", "4", "12", chance=50),
        T("oficial", "2", "6", "0.5"),
    ),
    _job(
        "Sustitución del portero automático",
        (COMMUNITY,),
        T("portero", "1", "1"),
        T("cable_2_5", "20", "40", chance=50),
        T("oficial", "3", "6", "0.5"),
    ),
    _job(
        "Iluminación LED del local",
        (BUSINESS,),
        T("panel_led", "6", "20"),
        T("cable_2_5", "30", "80"),
        T("oficial", "6", "16", "0.5"),
        T("ayudante", "4", "12", "0.5", chance=60),
    ),
    _job(
        "Adecuación del cuadro eléctrico",
        (PRIVATE, COMMUNITY, BUSINESS),
        T("cuadro", "1", "1"),
        T("diferencial", "1", "2"),
        T("magnetotermico", "4", "8"),
        T("toma_tierra", "1", "1", chance=40),
        T("oficial", "4", "8", "0.5"),
        T("cie", "1", "1", chance=60),
    ),
    _job(
        "Renovación completa de la instalación eléctrica de la vivienda",
        (PRIVATE,),
        T("cuadro", "1", "1"),
        T("diferencial", "2", "2"),
        T("magnetotermico", "8", "10"),
        T("punto_luz", "10", "16"),
        T("punto_conmutado", "3", "6"),
        T("base_16a", "16", "24"),
        T("toma_25a", "1", "1"),
        T("foco_led", "6", "12"),
        T("cable_2_5", "120", "200"),
        T("cable_6", "15", "25"),
        T("tubo", "100", "160"),
        T("toma_tierra", "1", "1"),
        T("oficial", "30", "50", "0.5"),
        T("ayudante", "20", "40", "0.5"),
        T("cie", "1", "1"),
        detailed=True,
    ),
    _job(
        "Instalación eléctrica de local comercial",
        (BUSINESS,),
        T("cuadro", "1", "1"),
        T("diferencial", "2", "3"),
        T("magnetotermico", "8", "12"),
        T("punto_luz", "6", "10"),
        T("panel_led", "10", "18"),
        T("foco_led", "8", "16"),
        T("base_16a", "12", "20"),
        T("detector", "2", "4"),
        T("cable_2_5", "150", "260"),
        T("cable_6", "20", "40"),
        T("tubo", "120", "200"),
        T("toma_tierra", "1", "1"),
        T("oficial", "36", "60", "0.5"),
        T("ayudante", "24", "40", "0.5"),
        T("cie", "1", "1"),
        detailed=True,
    ),
)

# Lo que el electricista vende fuera de la obra, al 21 % (regla provisional 4).
ELECTRICIAN_OUTSIDE_WORKS = T("lampara", "1", "3", outside_works=True)

BRICKLAYER_JOBS = (
    _job(
        "Tabiquería y enfoscados",
        (BUSINESS,),
        T("tabique", "120", "480", "0.5"),
        T("enfoscado", "200", "800", "0.5"),
        T("oficial", "20", "80", chance=60),
        T("peon", "20", "80", chance=60),
        T("ayudas", "1", "1", chance=50),
        contractor=True,
    ),
    _job(
        "Solados y alicatados",
        (BUSINESS,),
        T("solado", "80", "350", "0.5"),
        T("alicatado", "60", "260", "0.5"),
        T("recrecido", "80", "350", "0.5", chance=70),
        T("oficial", "10", "40", chance=50),
        contractor=True,
    ),
    _job(
        "Urbanización exterior",
        (BUSINESS,),
        T("solera", "60", "240", "0.5"),
        T("bordillo", "40", "180", "0.5"),
        T("peon", "20", "60"),
        T("oficial", "16", "40"),
        contractor=True,
    ),
    _job(
        "Trasdosados y ayudas a instalaciones",
        (BUSINESS,),
        T("trasdosado", "90", "300", "0.5"),
        T("ayudas", "1", "1"),
        T("oficial", "16", "60"),
        contractor=True,
    ),
    _job(
        "Trabajos de albañilería por administración",
        (BUSINESS,),
        T("oficial", "16", "120"),
        T("peon", "16", "120"),
        T("cemento", "10", "40", chance=40),
        contractor=True,
    ),
    _job(
        "Obra de albañilería de edificio de viviendas",
        (BUSINESS,),
        T("demolicion", "20", "60", "0.5"),
        T("tabique", "300", "650", "0.5"),
        T("enfoscado", "400", "900", "0.5"),
        T("trasdosado", "150", "400", "0.5"),
        T("recrecido", "200", "500", "0.5"),
        T("solado", "180", "420", "0.5"),
        T("alicatado", "120", "300", "0.5"),
        T("impermeabilizacion", "40", "120", "0.5"),
        T("solera", "80", "200", "0.5"),
        T("bordillo", "60", "160", "0.5"),
        T("ayudas", "1", "1"),
        T("andamio", "4", "10"),
        T("escombros", "4", "10"),
        T("oficial", "120", "260"),
        T("peon", "120", "260"),
        contractor=True,
        detailed=True,
    ),
    _job(
        "Reforma de baño",
        (PRIVATE,),
        T("demolicion", "4", "10", "0.5"),
        T("escombros", "1", "1"),
        T("alicatado", "14", "28", "0.5"),
        T("solado", "4", "8", "0.5"),
        T("cola", "4", "10"),
        T("cemento", "4", "12"),
        T("oficial", "16", "32"),
        T("peon", "8", "20"),
    ),
    _job(
        "Reparación de humedades y enfoscado",
        (PRIVATE, COMMUNITY),
        T("enfoscado", "10", "40", "0.5"),
        T("cemento", "3", "10"),
        T("arena", "0.5", "2", "0.5"),
        T("oficial", "6", "16"),
    ),
    _job(
        "Reparación de fachada",
        (COMMUNITY,),
        T("andamio", "1", "4"),
        T("enfoscado", "40", "160", "0.5"),
        T("impermeabilizacion", "10", "40", "0.5", chance=50),
        T("oficial", "16", "48"),
        T("peon", "16", "48"),
    ),
    _job(
        "Reforma del local",
        (BUSINESS,),
        T("demolicion", "10", "30", "0.5"),
        T("escombros", "1", "2"),
        T("tabique", "15", "40", "0.5"),
        T("trasdosado", "20", "60", "0.5"),
        T("solado", "30", "80", "0.5"),
        T("oficial", "24", "60"),
    ),
    _job(
        "Reforma integral de vivienda",
        (PRIVATE,),
        T("demolicion", "20", "45", "0.5"),
        T("escombros", "2", "4"),
        T("tabique", "25", "60", "0.5"),
        T("trasdosado", "20", "50", "0.5"),
        T("enfoscado", "30", "80", "0.5"),
        T("recrecido", "50", "90", "0.5"),
        T("solado", "50", "90", "0.5"),
        T("alicatado", "30", "60", "0.5"),
        T("ayudas", "1", "1"),
        T("cola", "15", "30"),
        T("cemento", "20", "40"),
        T("arena", "1", "3", "0.5"),
        T("ladrillo", "300", "800", "10"),
        T("oficial", "80", "160"),
        T("peon", "60", "120"),
        detailed=True,
    ),
)

JOBS = {Trade.ELECTRICIAN: ELECTRICIAN_JOBS, Trade.BRICKLAYER: BRICKLAYER_JOBS}
