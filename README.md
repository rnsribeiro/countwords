# Contador de Palavras

Aplicacao em Python com interface grafica feita em `PySide6` para:

- Criar secoes com o titulo de livros, capitulos ou qualquer agrupamento.
- Adicionar varios blocos de texto a cada secao ao longo do tempo.
- Persistir apenas as palavras e suas contagens por secao.
- Visualizar o histograma de uma secao, de varias secoes juntas ou de todas.
- Exibir, ao lado de cada palavra, uma traducao sugerida para portugues e uma pronuncia em IPA.
- Abrir o histograma em uma janela dedicada para enxergar melhor as barras.
- Filtrar e ordenar diretamente dentro da janela detalhada do histograma.
- Reproduzir audio de pronuncia quando a fonte lexical disponibilizar o arquivo.
- Excluir uma secao inteira ou remover uma palavra especifica da secao atual.
- Ordenar por ordem alfabetica ou por quantidade.
- Pesquisar palavras especificas.

## Como instalar

1. Tenha o Python 3 instalado.
2. Abra um terminal na pasta do projeto.
3. Instale a dependencia:

```powershell
pip install -r requirements.txt
```

## Como executar

```powershell
python app.py
```

## Como usar

1. Digite o titulo da secao e clique em **Criar secao**.
2. Escolha a secao de destino.
3. Cole um texto e clique em **Adicionar texto a secao** ou use `Ctrl+Enter`.
4. Marque uma ou mais secoes para visualizar o histograma combinado.
5. Se nenhuma secao estiver marcada, a aplicacao mostra o histograma de todas juntas.
6. Use a busca e a ordenacao para filtrar os resultados.
7. A traducao sugerida e o IPA sao buscados automaticamente para as palavras visiveis.
8. Use **Abrir histograma em janela** para ver as barras com mais espaco.
9. Dentro da janela detalhada, use os filtros locais para pesquisar palavras e ordenar o histograma.
10. Quando houver audio disponivel, use o botao **Ouvir** na linha da palavra.
11. Use **Excluir secao selecionada** para apagar a secao atual.
12. Para remover uma unica palavra, selecione a linha na tabela e use **Excluir palavra da linha**.

## Persistencia

- O arquivo `countwords.db` e criado automaticamente na pasta do projeto.
- Esse banco SQLite guarda as secoes, as contagens por palavra, as traducoes sugeridas e os IPAs em um unico arquivo.
- O texto bruto inserido na interface nao fica armazenado.
- Como o banco fica dentro do repositorio, voce pode versiona-lo no GitHub junto com o codigo.
- Se voce clonar o repositorio em outra maquina e esse arquivo estiver commitado, a aplicacao abre com os dados intactos.

## Traducao e IPA

- A implementacao atual assume que as palavras analisadas estao em ingles.
- A traducao mostrada e uma sugestao automatica palavra a palavra para portugues.
- O IPA e preenchido quando a consulta fonetica encontra um resultado disponivel.
- O audio de pronuncia aparece quando a API consultada fornece um arquivo de audio para a palavra.
- Se a rede estiver indisponivel, a contagem continua funcionando e as colunas de traducao e IPA podem ficar vazias ou com placeholder.

## GitHub

- O projeto esta preparado para manter o banco `countwords.db` dentro da pasta principal.
- Ao publicar no GitHub, inclua esse arquivo no commit para levar os dados junto com o projeto.
- Se existirem arquivos legados `section_counts.json` ou `word_metadata_cache.json`, a aplicacao consegue migrar esses dados para o banco SQLite automaticamente.

## Regras da contagem

- A contagem nao diferencia maiusculas de minusculas.
- Palavras com acentos sao reconhecidas.
- Numeros tambem entram na contagem.
- Hifens e apostrofos internos sao preservados quando fizerem parte da palavra.
