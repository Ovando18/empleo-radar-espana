"""
Divisão territorial oficial da Espanha em cascata:
Comunidade Autônoma -> Província -> Principais municípios.

Fonte da estrutura: INE (Instituto Nacional de Estadística) — 17 Comunidades
Autónomas, 2 Ciudades Autónomas e 50 províncias (+ Ceuta e Melilla).

Cada província guarda:
  - ``slug``: nome normalizado usado na montagem de URLs dos portais
  - ``ine``: código INE de 2 dígitos da província
  - ``cities``: principais municípios (ordem aproximada por população)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, TypedDict


class ProvinceInfo(TypedDict):
    slug: str
    ine: str
    cities: List[str]


SPAIN_LOCATIONS: Dict[str, Dict[str, ProvinceInfo]] = {
    "Andalucía": {
        "Almería": {"slug": "almeria", "ine": "04", "cities": [
            "Almería", "Roquetas de Mar", "El Ejido", "Níjar", "Vícar",
            "Adra", "Huércal-Overa", "Vera", "Mojácar", "Huércal de Almería"]},
        "Cádiz": {"slug": "cadiz", "ine": "11", "cities": [
            "Jerez de la Frontera", "Algeciras", "Cádiz", "San Fernando",
            "El Puerto de Santa María", "Chiclana de la Frontera", "La Línea de la Concepción",
            "Sanlúcar de Barrameda", "Puerto Real", "Rota", "Conil de la Frontera", "Tarifa"]},
        "Córdoba": {"slug": "cordoba", "ine": "14", "cities": [
            "Córdoba", "Lucena", "Puente Genil", "Montilla", "Priego de Córdoba",
            "Cabra", "Baena", "Palma del Río", "Pozoblanco"]},
        "Granada": {"slug": "granada", "ine": "18", "cities": [
            "Granada", "Motril", "Armilla", "Maracena", "Almuñécar", "Loja",
            "Baza", "Guadix", "Las Gabias", "Santa Fe", "Salobreña"]},
        "Huelva": {"slug": "huelva", "ine": "21", "cities": [
            "Huelva", "Lepe", "Almonte", "Isla Cristina", "Ayamonte",
            "Moguer", "Cartaya", "Punta Umbría", "Palos de la Frontera"]},
        "Jaén": {"slug": "jaen", "ine": "23", "cities": [
            "Jaén", "Linares", "Andújar", "Úbeda", "Martos", "Alcalá la Real",
            "Bailén", "Baeza", "La Carolina"]},
        "Málaga": {"slug": "malaga", "ine": "29", "cities": [
            "Málaga", "Marbella", "Mijas", "Vélez-Málaga", "Fuengirola",
            "Torremolinos", "Benalmádena", "Estepona", "Rincón de la Victoria",
            "Antequera", "Alhaurín de la Torre", "Ronda", "Nerja", "Manilva"]},
        "Sevilla": {"slug": "sevilla", "ine": "41", "cities": [
            "Sevilla", "Dos Hermanas", "Alcalá de Guadaíra", "Utrera",
            "Mairena del Aljarafe", "Écija", "La Rinconada", "Los Palacios y Villafranca",
            "Carmona", "Coria del Río", "Lebrija", "Tomares"]},
    },
    "Aragón": {
        "Huesca": {"slug": "huesca", "ine": "22", "cities": [
            "Huesca", "Monzón", "Barbastro", "Fraga", "Jaca", "Sabiñánigo",
            "Binéfar"]},
        "Teruel": {"slug": "teruel", "ine": "44", "cities": [
            "Teruel", "Alcañiz", "Andorra", "Calamocha", "Utrillas"]},
        "Zaragoza": {"slug": "zaragoza", "ine": "50", "cities": [
            "Zaragoza", "Calatayud", "Utebo", "Ejea de los Caballeros",
            "Cuarte de Huerva", "La Muela", "Tarazona", "Caspe", "La Almunia de Doña Godina"]},
    },
    "Principado de Asturias": {
        "Asturias": {"slug": "asturias", "ine": "33", "cities": [
            "Gijón", "Oviedo", "Avilés", "Siero", "Langreo", "Mieres",
            "Castrillón", "San Martín del Rey Aurelio", "Corvera de Asturias",
            "Llanes", "Villaviciosa", "Cangas de Onís"]},
    },
    "Illes Balears": {
        "Illes Balears": {"slug": "baleares", "ine": "07", "cities": [
            "Palma", "Calvià", "Ibiza", "Manacor", "Llucmajor", "Marratxí",
            "Santa Eulària des Riu", "Inca", "Ciutadella de Menorca", "Maó-Mahón",
            "Sant Josep de sa Talaia", "Alcúdia", "Sant Antoni de Portmany", "Formentera"]},
    },
    "Canarias": {
        "Las Palmas": {"slug": "las-palmas", "ine": "35", "cities": [
            "Las Palmas de Gran Canaria", "Telde", "Santa Lucía de Tirajana",
            "Arrecife", "San Bartolomé de Tirajana", "Arucas", "Puerto del Rosario",
            "Ingenio", "Agüimes", "Mogán", "Gáldar", "Pájara", "Tías", "Yaiza"]},
        "Santa Cruz de Tenerife": {"slug": "santa-cruz-de-tenerife", "ine": "38", "cities": [
            "Santa Cruz de Tenerife", "San Cristóbal de La Laguna", "Arona",
            "Adeje", "Granadilla de Abona", "La Orotava", "Los Realejos",
            "Puerto de la Cruz", "Candelaria", "Los Llanos de Aridane",
            "Santa Cruz de La Palma", "San Sebastián de La Gomera", "Valverde"]},
    },
    "Cantabria": {
        "Cantabria": {"slug": "cantabria", "ine": "39", "cities": [
            "Santander", "Torrelavega", "Castro-Urdiales", "Camargo",
            "Piélagos", "El Astillero", "Santa Cruz de Bezana", "Laredo",
            "Santoña", "Los Corrales de Buelna", "Reinosa"]},
    },
    "Castilla-La Mancha": {
        "Albacete": {"slug": "albacete", "ine": "02", "cities": [
            "Albacete", "Hellín", "Villarrobledo", "Almansa", "La Roda",
            "Caudete", "Tarazona de la Mancha"]},
        "Ciudad Real": {"slug": "ciudad-real", "ine": "13", "cities": [
            "Ciudad Real", "Puertollano", "Tomelloso", "Alcázar de San Juan",
            "Valdepeñas", "Manzanares", "Daimiel", "La Solana", "Miguelturra"]},
        "Cuenca": {"slug": "cuenca", "ine": "16", "cities": [
            "Cuenca", "Tarancón", "San Clemente", "Quintanar del Rey",
            "Motilla del Palancar", "Las Pedroñeras"]},
        "Guadalajara": {"slug": "guadalajara", "ine": "19", "cities": [
            "Guadalajara", "Azuqueca de Henares", "Alovera", "El Casar",
            "Cabanillas del Campo", "Marchamalo", "Villanueva de la Torre", "Sigüenza"]},
        "Toledo": {"slug": "toledo", "ine": "45", "cities": [
            "Toledo", "Talavera de la Reina", "Illescas", "Seseña",
            "Torrijos", "Sonseca", "Quintanar de la Orden", "Madridejos",
            "Consuegra", "Ocaña", "Yuncos"]},
    },
    "Castilla y León": {
        "Ávila": {"slug": "avila", "ine": "05", "cities": [
            "Ávila", "Arévalo", "Las Navas del Marqués", "Candeleda",
            "El Tiemblo", "Arenas de San Pedro"]},
        "Burgos": {"slug": "burgos", "ine": "09", "cities": [
            "Burgos", "Miranda de Ebro", "Aranda de Duero", "Briviesca",
            "Medina de Pomar", "Villarcayo", "Lerma"]},
        "León": {"slug": "leon", "ine": "24", "cities": [
            "León", "Ponferrada", "San Andrés del Rabanedo", "Villaquilambre",
            "Astorga", "La Bañeza", "Bembibre", "Villablino"]},
        "Palencia": {"slug": "palencia", "ine": "34", "cities": [
            "Palencia", "Aguilar de Campoo", "Guardo", "Venta de Baños",
            "Villamuriel de Cerrato", "Dueñas"]},
        "Salamanca": {"slug": "salamanca", "ine": "37", "cities": [
            "Salamanca", "Santa Marta de Tormes", "Béjar", "Ciudad Rodrigo",
            "Villamayor", "Carbajosa de la Sagrada", "Peñaranda de Bracamonte"]},
        "Segovia": {"slug": "segovia", "ine": "40", "cities": [
            "Segovia", "Cuéllar", "El Espinar", "San Ildefonso",
            "Palazuelos de Eresma", "Cantalejo"]},
        "Soria": {"slug": "soria", "ine": "42", "cities": [
            "Soria", "Almazán", "El Burgo de Osma", "Ólvega", "San Leonardo de Yagüe"]},
        "Valladolid": {"slug": "valladolid", "ine": "47", "cities": [
            "Valladolid", "Medina del Campo", "Laguna de Duero", "Arroyo de la Encomienda",
            "Tordesillas", "Íscar", "Tudela de Duero", "Cigales"]},
        "Zamora": {"slug": "zamora", "ine": "49", "cities": [
            "Zamora", "Benavente", "Toro", "Morales del Vino", "Puebla de Sanabria"]},
    },
    "Cataluña": {
        "Barcelona": {"slug": "barcelona", "ine": "08", "cities": [
            "Barcelona", "L'Hospitalet de Llobregat", "Badalona", "Terrassa",
            "Sabadell", "Mataró", "Santa Coloma de Gramenet", "Cornellà de Llobregat",
            "Sant Boi de Llobregat", "Sant Cugat del Vallès", "Rubí", "Manresa",
            "Vilanova i la Geltrú", "Viladecans", "El Prat de Llobregat",
            "Granollers", "Castelldefels", "Sitges", "Vic", "Martorell"]},
        "Girona": {"slug": "girona", "ine": "17", "cities": [
            "Girona", "Figueres", "Blanes", "Lloret de Mar", "Olot",
            "Salt", "Palafrugell", "Roses", "Sant Feliu de Guíxols", "Banyoles"]},
        "Lleida": {"slug": "lleida", "ine": "25", "cities": [
            "Lleida", "Balaguer", "Tàrrega", "Mollerussa", "La Seu d'Urgell",
            "Cervera", "Solsona", "Vielha e Mijaran"]},
        "Tarragona": {"slug": "tarragona", "ine": "43", "cities": [
            "Tarragona", "Reus", "Tortosa", "El Vendrell", "Cambrils",
            "Salou", "Valls", "Vila-seca", "Calafell", "Amposta", "Sant Carles de la Ràpita"]},
    },
    "Comunidad Valenciana": {
        "Alicante": {"slug": "alicante", "ine": "03", "cities": [
            "Alicante", "Elche", "Torrevieja", "Orihuela", "Benidorm",
            "San Vicente del Raspeig", "Elda", "Alcoy", "San Juan de Alicante",
            "Villena", "Petrer", "Dénia", "Santa Pola", "Jávea", "Crevillente",
            "Villajoyosa", "Altea", "Calpe", "Novelda", "Ibi", "El Campello"]},
        "Castellón": {"slug": "castellon", "ine": "12", "cities": [
            "Castellón de la Plana", "Vila-real", "Burriana", "La Vall d'Uixó",
            "Vinaròs", "Benicarló", "Onda", "Almassora", "Benicàssim",
            "Peñíscola", "Nules", "Segorbe"]},
        "Valencia": {"slug": "valencia", "ine": "46", "cities": [
            "Valencia", "Torrent", "Gandia", "Paterna", "Sagunto", "Mislata",
            "Burjassot", "Ontinyent", "Aldaia", "Manises", "Alzira",
            "Xirivella", "Sueca", "Cullera", "Xàtiva", "Quart de Poblet",
            "Catarroja", "Oliva", "Alboraya", "Picassent"]},
    },
    "Extremadura": {
        "Badajoz": {"slug": "badajoz", "ine": "06", "cities": [
            "Badajoz", "Mérida", "Don Benito", "Almendralejo", "Villanueva de la Serena",
            "Zafra", "Montijo", "Villafranca de los Barros", "Olivenza"]},
        "Cáceres": {"slug": "caceres", "ine": "10", "cities": [
            "Cáceres", "Plasencia", "Navalmoral de la Mata", "Coria",
            "Trujillo", "Miajadas", "Moraleja"]},
    },
    "Galicia": {
        "A Coruña": {"slug": "a-coruna", "ine": "15", "cities": [
            "A Coruña", "Santiago de Compostela", "Ferrol", "Narón", "Oleiros",
            "Arteixo", "Carballo", "Culleredo", "Ames", "Ribeira", "Betanzos"]},
        "Lugo": {"slug": "lugo", "ine": "27", "cities": [
            "Lugo", "Monforte de Lemos", "Viveiro", "Vilalba", "Sarria",
            "Burela", "Ribadeo", "Foz"]},
        "Ourense": {"slug": "ourense", "ine": "32", "cities": [
            "Ourense", "Verín", "O Barco de Valdeorras", "O Carballiño",
            "Xinzo de Limia", "Barbadás", "Ribadavia"]},
        "Pontevedra": {"slug": "pontevedra", "ine": "36", "cities": [
            "Vigo", "Pontevedra", "Vilagarcía de Arousa", "Redondela",
            "Cangas", "Marín", "Ponteareas", "Lalín", "O Porriño", "Sanxenxo",
            "Moaña", "Tui", "Cambados"]},
    },
    "Comunidad de Madrid": {
        "Madrid": {"slug": "madrid", "ine": "28", "cities": [
            "Madrid", "Móstoles", "Alcalá de Henares", "Fuenlabrada", "Leganés",
            "Getafe", "Alcorcón", "Torrejón de Ardoz", "Parla", "Alcobendas",
            "Las Rozas de Madrid", "San Sebastián de los Reyes", "Pozuelo de Alarcón",
            "Rivas-Vaciamadrid", "Coslada", "Valdemoro", "Majadahonda",
            "Collado Villalba", "Aranjuez", "Arganda del Rey", "Boadilla del Monte",
            "Tres Cantos", "Pinto", "Colmenar Viejo"]},
    },
    "Región de Murcia": {
        "Murcia": {"slug": "murcia", "ine": "30", "cities": [
            "Murcia", "Cartagena", "Lorca", "Molina de Segura", "Alcantarilla",
            "Mazarrón", "Cieza", "Águilas", "Yecla", "San Javier", "Torre-Pacheco",
            "Totana", "Caravaca de la Cruz", "Jumilla", "San Pedro del Pinatar",
            "Los Alcázares"]},
    },
    "Comunidad Foral de Navarra": {
        "Navarra": {"slug": "navarra", "ine": "31", "cities": [
            "Pamplona", "Tudela", "Barañáin", "Burlada", "Estella-Lizarra",
            "Zizur Mayor", "Tafalla", "Villava", "Ansoáin", "Berriozar", "Corella"]},
    },
    "País Vasco": {
        "Álava": {"slug": "alava", "ine": "01", "cities": [
            "Vitoria-Gasteiz", "Llodio", "Amurrio", "Salvatierra", "Oyón-Oion",
            "Iruña de Oca"]},
        "Bizkaia": {"slug": "vizcaya", "ine": "48", "cities": [
            "Bilbao", "Barakaldo", "Getxo", "Portugalete", "Santurtzi", "Basauri",
            "Leioa", "Durango", "Galdakao", "Sestao", "Erandio", "Bermeo", "Gernika-Lumo"]},
        "Gipuzkoa": {"slug": "guipuzcoa", "ine": "20", "cities": [
            "San Sebastián", "Irun", "Errenteria", "Eibar", "Zarautz",
            "Arrasate-Mondragón", "Hernani", "Lasarte-Oria", "Tolosa", "Hondarribia",
            "Beasain", "Azpeitia"]},
    },
    "La Rioja": {
        "La Rioja": {"slug": "la-rioja", "ine": "26", "cities": [
            "Logroño", "Calahorra", "Arnedo", "Haro", "Alfaro", "Lardero",
            "Nájera", "Santo Domingo de la Calzada"]},
    },
    "Ceuta (Ciudad Autónoma)": {
        "Ceuta": {"slug": "ceuta", "ine": "51", "cities": ["Ceuta"]},
    },
    "Melilla (Ciudad Autónoma)": {
        "Melilla": {"slug": "melilla", "ine": "52", "cities": ["Melilla"]},
    },
}

ALL_REGIONS_LABEL = "Toda España"
ALL_PROVINCES_LABEL = "Todas as províncias"
ALL_CITIES_LABEL = "Todas as cidades"


def slugify(text: str) -> str:
    """Normaliza um texto para uso em URLs: minúsculas, sem acentos, com hífens."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c))


def get_regions() -> List[str]:
    """Comunidades Autônomas em ordem alfabética (ignorando acentos)."""
    return sorted(SPAIN_LOCATIONS.keys(), key=lambda r: strip_accents(r).lower())


def get_provinces(region: str | None) -> List[str]:
    """Províncias de uma comunidade; sem comunidade, retorna todas as províncias."""
    if not region or region == ALL_REGIONS_LABEL:
        provinces = [p for provs in SPAIN_LOCATIONS.values() for p in provs]
    else:
        provinces = list(SPAIN_LOCATIONS.get(region, {}).keys())
    return sorted(provinces, key=lambda p: strip_accents(p).lower())


def get_cities(province: str | None) -> List[str]:
    """Principais municípios de uma província (ordem por relevância/população)."""
    info = get_province_info(province)
    return list(info["cities"]) if info else []


def get_province_info(province: str | None) -> ProvinceInfo | None:
    if not province:
        return None
    for provs in SPAIN_LOCATIONS.values():
        if province in provs:
            return provs[province]
    return None


def get_region_of_province(province: str | None) -> str | None:
    if not province:
        return None
    for region, provs in SPAIN_LOCATIONS.items():
        if province in provs:
            return region
    return None


def find_province_by_city(city: str | None) -> str | None:
    """Localiza a província de um município conhecido (comparação sem acentos)."""
    if not city:
        return None
    target = strip_accents(city).lower().strip()
    for provs in SPAIN_LOCATIONS.values():
        for prov, info in provs.items():
            if any(strip_accents(c).lower() == target for c in info["cities"]):
                return prov
    return None


def count_summary() -> Dict[str, int]:
    regions = len(SPAIN_LOCATIONS)
    provinces = sum(len(p) for p in SPAIN_LOCATIONS.values())
    cities = sum(len(i["cities"]) for p in SPAIN_LOCATIONS.values() for i in p.values())
    return {"regions": regions, "provinces": provinces, "cities": cities}
