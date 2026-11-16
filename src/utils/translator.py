"""
Tradução automática de termos de busca Português -> Espanhol.

Funciona 100% offline com um dicionário curado de cargos e termos do mercado
de trabalho. Primeiro tenta casar expressões completas (ex.: "auxiliar de
cozinha"), depois palavra a palavra. Palavras sem tradução são mantidas — a
maioria dos cargos técnicos (ex.: "python", "data analyst") é igual nos dois
idiomas.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Tuple

# Expressões compostas (têm prioridade sobre palavras isoladas)
PHRASES_PT_ES: Dict[str, str] = {
    "auxiliar de cozinha": "ayudante de cocina",
    "ajudante de cozinha": "ayudante de cocina",
    "auxiliar de limpeza": "auxiliar de limpieza",
    "auxiliar administrativo": "auxiliar administrativo",
    "assistente administrativo": "administrativo",
    "atendente de loja": "dependiente",
    "atendente de balcao": "dependiente",
    "atendimento ao cliente": "atención al cliente",
    "atendente de telemarketing": "teleoperador",
    "operador de telemarketing": "teleoperador",
    "operador de caixa": "cajero",
    "repositor de mercadorias": "reponedor",
    "repositor de supermercado": "reponedor",
    "auxiliar de armazem": "mozo de almacén",
    "ajudante de armazem": "mozo de almacén",
    "operador de empilhadeira": "carretillero",
    "motorista de caminhao": "conductor de camión",
    "motorista de entregas": "repartidor",
    "entregador": "repartidor",
    "camareira de hotel": "camarera de pisos",
    "arrumadeira": "camarera de pisos",
    "recepcionista de hotel": "recepcionista de hotel",
    "garcom": "camarero",
    "garconete": "camarera",
    "cuidador de idosos": "cuidador de personas mayores",
    "cuidadora de idosos": "cuidadora de personas mayores",
    "tecnico de enfermagem": "técnico en cuidados auxiliares de enfermería",
    "auxiliar de enfermagem": "auxiliar de enfermería",
    "babá": "niñera",
    "baba": "niñera",
    "professor de ingles": "profesor de inglés",
    "professor de portugues": "profesor de portugués",
    "professor de espanhol": "profesor de español",
    "engenheiro civil": "ingeniero civil",
    "engenheiro de software": "ingeniero de software",
    "engenheiro eletrico": "ingeniero eléctrico",
    "engenheiro mecanico": "ingeniero mecánico",
    "engenheiro de producao": "ingeniero de producción",
    "engenheiro ambiental": "ingeniero ambiental",
    "engenheiro de dados": "ingeniero de datos",
    "cientista de dados": "científico de datos",
    "analista de dados": "analista de datos",
    "analista de sistemas": "analista de sistemas",
    "analista financeiro": "analista financiero",
    "desenvolvedor web": "desarrollador web",
    "desenvolvedor de software": "desarrollador de software",
    "desenvolvedor front end": "desarrollador frontend",
    "desenvolvedor back end": "desarrollador backend",
    "suporte tecnico": "soporte técnico",
    "seguranca da informacao": "ciberseguridad",
    "tecnico de informatica": "técnico informático",
    "mestre de obras": "jefe de obra",
    "encarregado de obra": "encargado de obra",
    "pedreiro": "albañil",
    "ajudante de pedreiro": "peón de albañil",
    "servente de obra": "peón de obra",
    "pintor de paredes": "pintor",
    "eletricista": "electricista",
    "encanador": "fontanero",
    "vendedor de loja": "dependiente",
    "gerente de loja": "encargado de tienda",
    "gerente de projetos": "jefe de proyecto",
    "gerente de vendas": "jefe de ventas",
    "recursos humanos": "recursos humanos",
    "meio periodo": "media jornada",
    "meio expediente": "media jornada",
    "tempo parcial": "jornada parcial",
    "tempo integral": "jornada completa",
    "trabalho remoto": "teletrabajo",
    "home office": "teletrabajo",
    "fim de semana": "fin de semana",
    "fins de semana": "fines de semana",
    "estagio remunerado": "prácticas remuneradas",
    "sem experiencia": "sin experiencia",
    "primeiro emprego": "primer empleo",
}

# Palavras isoladas
WORDS_PT_ES: Dict[str, str] = {
    # Cargos gerais
    "ajudante": "ayudante", "auxiliar": "auxiliar", "assistente": "asistente",
    "atendente": "dependiente", "vendedor": "vendedor", "vendedora": "vendedora",
    "caixa": "cajero", "repositor": "reponedor", "estoquista": "mozo de almacén",
    "armazem": "almacén", "logistica": "logística", "motorista": "conductor",
    "condutor": "conductor", "faxineira": "limpiadora", "faxineiro": "limpiador",
    "limpeza": "limpieza", "zelador": "conserje", "porteiro": "conserje",
    "seguranca": "vigilante de seguridad", "vigia": "vigilante",
    "cozinheiro": "cocinero", "cozinheira": "cocinera", "cozinha": "cocina",
    "padeiro": "panadero", "confeiteiro": "pastelero", "acougueiro": "carnicero",
    "barman": "camarero de barra", "bartender": "bartender",
    "recepcionista": "recepcionista", "hotel": "hotel", "hotelaria": "hostelería",
    "turismo": "turismo", "guia": "guía", "cuidador": "cuidador", "cuidadora": "cuidadora",
    "enfermeiro": "enfermero", "enfermeira": "enfermera", "medico": "médico",
    "medica": "médica", "dentista": "dentista", "farmaceutico": "farmacéutico",
    "fisioterapeuta": "fisioterapeuta", "psicologo": "psicólogo",
    "professor": "profesor", "professora": "profesora", "educador": "educador",
    "monitor": "monitor", "tutor": "tutor", "pedagogo": "pedagogo",
    "secretaria": "secretaria", "administrativo": "administrativo",
    "contador": "contable", "contabilidade": "contabilidad", "advogado": "abogado",
    "advogada": "abogada", "juridico": "jurídico", "financeiro": "financiero",
    "gerente": "gerente", "coordenador": "coordinador", "supervisor": "supervisor",
    "diretor": "director", "chefe": "jefe", "encarregado": "encargado",
    "analista": "analista", "consultor": "consultor", "tecnico": "técnico",
    "engenheiro": "ingeniero", "engenheira": "ingeniera", "engenharia": "ingeniería",
    "arquiteto": "arquitecto", "arquiteta": "arquitecta", "projetista": "proyectista",
    "desenhista": "delineante", "topografo": "topógrafo", "obra": "obra",
    "construcao": "construcción", "civil": "civil", "eletrica": "eléctrica",
    "mecanico": "mecánico", "mecanica": "mecánica", "soldador": "soldador",
    "torneiro": "tornero", "operador": "operario", "operario": "operario",
    "montador": "montador", "carpinteiro": "carpintero", "marceneiro": "ebanista",
    "jardineiro": "jardinero", "agricultor": "agricultor", "colheita": "cosecha",
    "desenvolvedor": "desarrollador", "programador": "programador",
    "informatica": "informática", "suporte": "soporte", "dados": "datos",
    "sistemas": "sistemas", "redes": "redes",
    "designer": "diseñador", "marketing": "marketing", "vendas": "ventas",
    "comercial": "comercial", "compras": "compras", "estagio": "prácticas",
    "estagiario": "becario", "trainee": "trainee", "aprendiz": "aprendiz",
    "telemarketing": "teleoperador", "teleoperador": "teleoperador",
    "costureira": "costurera", "cabeleireiro": "peluquero", "cabeleireira": "peluquera",
    "manicure": "manicurista", "esteticista": "esteticista", "fotografo": "fotógrafo",
    "tradutor": "traductor", "interprete": "intérprete", "entregas": "reparto",
    "garcom": "camarero", "garconete": "camarera", "camareira": "camarera de pisos",
    # Termos de jornada/contrato
    "parcial": "parcial", "integral": "completa", "remoto": "remoto",
    "hibrido": "híbrido", "presencial": "presencial", "temporario": "temporal",
    "efetivo": "indefinido", "noturno": "nocturno", "turno": "turno",
    "verao": "verano", "experiencia": "experiencia", "ingles": "inglés",
    "portugues": "portugués", "espanhol": "español", "de": "de", "e": "y",
    "para": "para", "com": "con", "sem": "sin",
}


def _normalize(text: str) -> str:
    """Minúsculas e sem acentos (para comparar com o dicionário)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


_NORMALIZED_PHRASES = sorted(
    ((_normalize(k), v) for k, v in PHRASES_PT_ES.items()),
    key=lambda kv: len(kv[0]),
    reverse=True,
)
_NORMALIZED_WORDS = {_normalize(k): v for k, v in WORDS_PT_ES.items()}


def translate_pt_to_es(query: str) -> Tuple[str, bool]:
    """
    Traduz um termo de busca PT -> ES.

    Retorna ``(texto_traduzido, houve_mudanca)``. Se nada for reconhecido, o
    texto original é devolvido intacto (mantendo acentos e maiúsculas).
    """
    if not query or not query.strip():
        return "", False

    norm = _normalize(query)
    placeholders: Dict[str, str] = {}

    # 1) Expressões compostas, das mais longas para as mais curtas
    for idx, (pt, es) in enumerate(_NORMALIZED_PHRASES):
        pattern = r"\b" + re.escape(pt) + r"\b"
        if re.search(pattern, norm):
            token = f"\x00{idx}\x00"
            placeholders[token] = es
            norm = re.sub(pattern, token, norm)

    # 2) Palavra a palavra
    out = []
    for word in norm.split(" "):
        if word.startswith("\x00"):
            out.append(placeholders.get(word, word))
        else:
            out.append(_NORMALIZED_WORDS.get(word, word))
    translated = " ".join(w for w in out if w).strip()

    changed = translated != _normalize(query)
    if not changed:
        return query.strip(), False
    return translated, True


def looks_portuguese(query: str) -> bool:
    """Heurística: o texto contém algum termo do dicionário PT que muda em ES?"""
    _, changed = translate_pt_to_es(query)
    return changed
