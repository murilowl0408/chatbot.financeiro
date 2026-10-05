# 💰 Chatbot de Organização Financeira

Protótipo de um **chatbot para Telegram desenvolvido em Python**, criado para facilitar o registro e o acompanhamento de gastos pessoais diretamente pelo celular.

A proposta é tornar o controle financeiro mais simples: em vez de preencher planilhas ou utilizar uma interface complexa, o usuário pode simplesmente enviar uma mensagem como `uber 23,90 pix`, e o bot interpreta automaticamente a **categoria, valor e forma de pagamento**, armazenando essas informações para consultas futuras.

### Funcionalidades

- Registro de gastos através de mensagens no Telegram
- Identificação automática de categoria, valor e forma de pagamento
- Suporte para Pix, crédito, débito e dinheiro
- Resumo dos gastos do mês
- Gastos organizados por categoria
- Consulta dos gastos por forma de pagamento
- Consulta dos gastos de um ano inteiro
- Visualização da última despesa registrada
- Exclusão do último registro
- Limpeza completa dos registros com confirmação e backup
- Restrição de acesso ao usuário autorizado 

### Tecnologias e conceitos

- **Python 3**
- **Telegram Bot API**
- **python-telegram-bot**
- **SQLite**
- **python-dotenv**
- Expressões regulares (`re`)
- Manipulação e validação de dados
- Tratamento de exceções
- Consultas SQL
- Organização do projeto em módulos

O projeto separa a comunicação com o Telegram da lógica responsável pelo processamento e armazenamento dos gastos. A lógica financeira é independente da plataforma de mensagens, permitindo que futuramente a mesma estrutura possa ser adaptada para outros canais.

### Banco de dados

Os gastos são armazenados em um banco **SQLite**, contendo informações como data, categoria, valor e forma de pagamento. Os valores são armazenados em **centavos como números inteiros**, evitando problemas de precisão comuns em operações com números decimais. 

Este projeto foi desenvolvido como um **protótipo de aplicação prática em Python**, com foco em automação, organização financeira e integração com APIs, servindo também como exercício para aprofundar conhecimentos em desenvolvimento de bots e manipulação de dados.
