# 📡 EmpleoRadar España

Painel agregador e buscador de vagas de trabalho na Espanha, feito em **Python + Streamlit**.
Consulta **10 portais de emprego** em paralelo, normaliza os dados (jornada, salário anual,
contrato, modalidade, data) e gera **links de busca pré-filtrados** para cada portal. Esses
links funcionam com 1 clique mesmo quando um portal bloqueia a coleta automática.

> Foco especial no filtro de **jornada**: *Parcial / até 30h semanais* (compatível com visto
> de estudante) × *Completa / 40h* × *Turnos / Intensiva / Flexível*.

---

## ✨ Funcionalidades

| Área | O que faz |
|---|---|
| **Portais** | InfoJobs, Indeed, LinkedIn Jobs, Empléate (SEPE), Infoempleo, Jooble, Randstad, Job Today, Tecnoempleo, Turijobs |
| **Localização em cascata** | 17 Comunidades Autônomas + Ceuta e Melilla → 52 províncias (códigos INE) → mais de 500 municípios, além de campo livre para qualquer município |
| **Filtros** | Jornada, palavra-chave (com tradução **PT → ES** automática), setor, modalidade, contrato, salário mínimo (€/ano), data de publicação e escolha de portais |
| **Deep links** | URL de busca pré-filtrada para cada portal (palavra-chave, província/cidade, jornada, período) |
| **Visualização** | Cards executivos, tabela analítica ordenável e gráficos Plotly (por portal, cidade, jornada e salário) |
| **Favoritas** | Salvar vagas na sessão e exportar para **CSV**, **Excel (.xlsx)** formatado e **relatório PDF** |
| **Resiliência** | Coleta assíncrona (`httpx` + `asyncio`), User-Agents rotativos, retentativas com backoff, detecção de captcha/403, cache de 15 min |

## 🗂️ Estrutura

```
empleo-radar-espana/
├── app.py                        # Aplicação Streamlit (interface)
├── requirements.txt              # Dependências leves (sem Selenium/Playwright)
├── .streamlit/
│   ├── config.toml               # Tema (vermelho #AA151B, ouro #F1BF00, fundo #F8F9FA)
│   └── secrets.toml.example      # Modelo de credenciais opcionais de API
├── src/
│   ├── data/spain_locations.py   # Comunidades → Províncias → Municípios
│   ├── scrapers/
│   │   ├── models.py             # JobOffer, SearchParams, rótulos dos filtros
│   │   ├── normalizer.py         # Jornada, contrato, modalidade, salário anual, datas
│   │   ├── portals.py            # Templates de URL + parsers específicos dos 10 portais
│   │   └── aggregator.py         # Motor assíncrono, parsers genéricos, filtros, deduplicação
│   └── utils/
│       ├── translator.py         # Dicionário de cargos PT → ES (offline)
│       └── exporter.py           # CSV, Excel estilizado e PDF
└── tests/test_core.py            # 32 testes offline (parsers, filtros, exportação, pipeline)
```

## 🚀 Rodando localmente

Requisito: Python 3.10 ou superior.

```bash
git clone https://github.com/Ovando18/empleo-radar-espana.git
```

```bash
cd empleo-radar-espana
```

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

O app abre em `http://localhost:8501`.

Para rodar os testes (opcional):

```bash
pip install pytest
```

```bash
python -m pytest -q
```

## ☁️ Publicando no GitHub

1. Crie um repositório vazio em <https://github.com/new> (por exemplo, `empleo-radar-espana`). Não marque a opção de README.
2. Na pasta do projeto, rode um comando por vez:

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "EmpleoRadar España: versão inicial"
```

```bash
git branch -M main
```

```bash
git remote add origin https://github.com/Ovando18/empleo-radar-espana.git
```

```bash
git push -u origin main
```

> O `.gitignore` já impede o envio de `.streamlit/secrets.toml`, para que suas chaves nunca vão para o GitHub.

## 🌐 Deploy gratuito no Streamlit Community Cloud

1. Acesse <https://share.streamlit.io> e entre com sua conta do GitHub.
2. Clique em **Create app** → **Deploy a public app from GitHub**.
3. Preencha:
   - **Repository:** `Ovando18/empleo-radar-espana`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. (Opcional) Em **Advanced settings**, escolha Python 3.12 e cole as credenciais na seção **Secrets** (veja abaixo).
5. Clique em **Deploy**. Em 1 a 3 minutos o app fica disponível em `https://<nome-do-app>.streamlit.app`.

Cada `git push` na branch `main` atualiza o app automaticamente.

### 🔑 APIs oficiais opcionais (recomendado)

Portais como InfoJobs e Indeed costumam bloquear IPs de servidores na nuvem. Para ter resultados
estáveis desses agregadores, cadastre as APIs **gratuitas** e informe as chaves em
*App → Settings → Secrets* (ou em `.streamlit/secrets.toml` localmente):

```toml
INFOJOBS_CLIENT_ID = "seu-client-id"         # https://developer.infojobs.net
INFOJOBS_CLIENT_SECRET = "seu-client-secret"
JOOBLE_API_KEY = "sua-chave"                 # https://jooble.org/api/about
```

Sem chaves, o app continua funcionando com coleta HTML e links diretos.

## ⚙️ Como funciona a coleta

1. **Deep links** são gerados sempre, para todos os portais selecionados.
2. Os portais são consultados **em paralelo** (até 6 conexões simultâneas, 25 s de limite por portal).
3. O parsing é feito em camadas:
   1. **Parser específico**: endpoint público de convidado do LinkedIn e JSON `mosaic-provider-jobcards` do Indeed.
   2. **JSON-LD `schema.org/JobPosting`**: padrão que muitos portais publicam para o Google for Jobs.
   3. **Heurística de links**: reconhece URLs de oferta de cada portal (ex.: `/of-i…` no InfoJobs, `/rf-…` no Tecnoempleo) e lê título, empresa, local e salário do bloco ao redor.
4. As vagas são **normalizadas**:
   - **Jornada:** horas semanais explícitas (≤30h = parcial, 35–45h = completa) ou termos como *media jornada*, *jornada completa*, *turnos* e *intensiva*.
   - **Salário anualizado:** mensal × 12; por hora × horas semanais × 52 (30h para parcial, 40h para as demais).
   - **Datas:** relativas (*hace 2 días*, *3 days ago*), ISO ou timestamps.
5. As vagas são **deduplicadas** (título + empresa + cidade) e **filtradas**. Filtros como contrato, salário e jornada são reaplicados localmente, sem nova coleta.

Cada portal recebe um status na aba **🛰️ Status da coleta**: *Coletado*, *Sem resultados*,
*Bloqueio anti-bot*, *Falha de conexão* ou *Apenas link direto* (Empléate é uma aplicação
JavaScript e não pode ser coletada sem navegador).

### Manutenção dos templates de URL

Os portais mudam o formato das URLs e do HTML com frequência. Todos os templates de busca e
padrões de link estão centralizados em `src/scrapers/portals.py`, uma função `link_<portal>()`
por portal mais o campo `link_patterns` do registro `PORTALS`. Se um link direto parar de aplicar
algum filtro, ajuste apenas a função correspondente.

## ⚠️ Avisos

- O EmpleoRadar não hospeda vagas: os dados pertencem aos respectivos portais. Confirme sempre as condições na vaga original.
- A coleta respeita limites conservadores (poucas requisições, cache de 15 minutos). Use o app para buscas pessoais e consulte os termos de uso de cada portal.
- **Visto de estudante:** a regra geral na Espanha permite trabalhar até 30h semanais. Confirme sempre as condições vigentes no site oficial de extranjería.
