# Guia do Extensionista das Galáxias

Não entre em pânico. Onde dormir, comer e abastecer em viagem pelo Paraná: hotéis, restaurantes e postos por município, com busca, mapa e avaliações.

**Lista alimentada e mantida por colegas, como apoio. Não tem vínculo institucional com o IDR-Paraná.**

## Como funciona

- Site estático (GitHub Pages): `index.html`, `style.css`, `app.js`.
- Base inicial em `data/lugares.json` (gerada por `build/build_data.py`).
- Tudo vai para uma planilha Google pelo Apps Script em `apps-script/`. Indicação de lugar e confirmação entram direto; avaliação e correção ficam `pendente` até um mantenedor trocar o `status` para `aprovado`.
- Indicação e confirmação pedem nota de 1 a 5 estrelas e aceitam comentário; os dois aparecem no cartão do lugar, sem o nome de quem escreveu.
- Confirmação: outro colega atesta que usou. Cada nome conta uma vez por lugar. A lista ordena por pontos: confirmação vale 2, indicação de colega 1, nota média até 1.
- Nome e data de quem avalia ficam só na planilha. O site mostra nota e comentário.
- "Município próximo": sedes a até 20/42/60/80 km em linha reta, mais os vínculos aprovados na aba `vinculos`.

## Rodar local

```bash
py -3 -m http.server 8765
# http://127.0.0.1:8765/  (com #teste roda a checagem no console)
```

## Atualizar a base inicial

```bash
py -3 build/fetch_osm.py    # hotéis e restaurantes do OpenStreetMap
# Cadastur: baixar "Meios de Hospedagem" em dados.turismo.gov.br para build/raw/cadastur/hospedagem.xlsx
py -3 build/build_data.py   # junta com a planilha de postos e grava data/*.json
py -3 build/sprites.py      # pixel art: edite os desenhos em texto e regere os SVG
```

A planilha de postos não vai para o repositório (tem CNPJ, inscrição estadual e nome de contato). Só saem nome, endereço, telefone, horário e coordenada.

## Backend (clasp)

```bash
cd apps-script
clasp create --type sheets --title "Guia do Extensionista das Galáxias"
git checkout appsscript.json   # o create troca o manifesto pelo padrão; este tem o escopo mínimo e o acesso anônimo
clasp push
clasp deploy --description "v1"
# no editor: rodar setup() uma vez e aceitar a autorização (sem isso o /exec responde 403)
# para atualizar sem trocar a URL: clasp deploy -i <id da implantação>
```

Cole a URL `/exec` em `config.js`.

## Moderação na planilha

| Aba | O que fazer |
|---|---|
| `lugares` | Entra como `aprovado`. Trocar para `rejeitado` tira do site. Linha com o `id` de um lugar e `status` = `removido` tira da lista. Preencher `lat`/`lon` posiciona no mapa. |
| `avaliacoes` | Formulário antigo, não aparece mais no site. As linhas aprovadas continuam contando na nota. |
| `correcoes` | Ler, aplicar na aba `lugares` (linha com o mesmo `id`), marcar `aprovado`. |
| `confirmacoes` | Entra como `aprovado`, com nota, comentário e data. Trocar para `rejeitado` desconta. Coluna `remover` = `SIM` é pedido de remoção: vale a nota, não soma como confirmação. |
| `vinculos` | Par de códigos IBGE (`m_a`, `m_b`) que vale como "próximo" mesmo fora do raio. |

## Créditos

Hotéis, restaurantes e mapa: © colaboradores do OpenStreetMap (ODbL). Contatos de hotéis: Cadastur, Ministério do Turismo (dados abertos). Sedes municipais: kelvins/municipios-brasileiros.
