# CountWords

Aplicacao desktop em Python com interface grafica em `PySide6` para contar palavras por seccoes, visualizar histogramas e manter os dados em um banco SQLite local.

## O que a aplicacao faz

- Cria seccoes com o nome de livros, capitulos ou qualquer outro agrupamento.
- Permite adicionar varios blocos de texto na mesma seccao ao longo do tempo.
- Conta palavras de forma case-insensitive.
- Exibe o histograma de uma seccao, de varias seccoes selecionadas ou de todas juntas.
- Abre o histograma em uma janela dedicada para facilitar a visualizacao.
- Permite pesquisar palavras e ordenar por quantidade ou ordem alfabetica.
- Permite excluir uma seccao inteira.
- Permite excluir uma palavra da seccao selecionada diretamente na janela do histograma.

## Requisitos

- Python 3.11 ou superior.
- Dependencias listadas em `requirements.txt`.

## Instalacao

No terminal, dentro da pasta do projeto:

```powershell
pip install -r requirements.txt
```

## Execucao

```powershell
python app.py
```

Para abrir sem janela de terminal no Windows, basta dar duplo clique em `CountWords.pyw` ou executar:

```powershell
pythonw CountWords.pyw
```

## Como usar

1. Digite o titulo da seccao e clique em `Criar seccao`.
2. Escolha a seccao de destino.
3. Cole um texto e clique em `Adicionar texto a seccao`.
4. Marque uma ou mais seccoes para combinar os histogramas.
5. Se nenhuma seccao estiver marcada, a aplicacao usa todas as seccoes.
6. Clique em `Abrir histograma em janela` para ver a tabela detalhada.
7. Na janela do histograma, use a busca e a ordenacao para filtrar os resultados.
8. Use o botao `Excluir` na linha de uma palavra para removela da seccao atual.

## Persistencia

- O arquivo `countwords.db` fica na raiz do projeto.
- O banco guarda as seccoes e as contagens por palavra.
- O texto original digitado nao e armazenado.
- Como o banco esta dentro do repositorio, voce pode versiona-lo no GitHub junto com o codigo.
- Ao clonar o repositorio em outra maquina, os dados permanecem intactos desde que `countwords.db` tenha sido commitado.

## Estrutura do projeto

- `app.py`: interface principal e janela detalhada do histograma.
- `CountWords.pyw`: launcher para abrir a interface sem terminal no Windows.
- `storage_db.py`: camada de persistencia SQLite.
- `test_app.py`: testes automatizados da logica principal.
- `countwords.db`: banco local com os dados do projeto.

## Observacoes

- O repositorio foi pensado para ser simples de clonar e executar.
- Se existirem arquivos legados de versoes anteriores, a aplicacao tenta migrar os dados automaticamente para o SQLite.
