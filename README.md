# SIGLOC Agent - Automação de Aniversariantes

Este projeto automatiza a extração diária/mensal de aniversariantes e bodas do sistema SIGLOC e envia resumos formatados via WhatsApp utilizando a **Evolution Go API**.

## 🚀 Funcionalidades

- **Extração Robusta**: Scraper via Selenium otimizado para o dashboard do SIGLOC.
- **Dois Modos de Operação**:
  - **Diário**: Envia apenas quem faz aniversário hoje no horário configurado.
  - **Mensal**: Envia o resumo completo do mês no dia 01 às 00:01.
- **Painel de Controle**: Interface web via FastAPI para configurações e logs em tempo real.
- **Mensagem Customizada**: Permite definir um texto amigável para dias sem registros.

## 🛠️ Requisitos

- Python 3.8+
- Google Chrome instalado
- Instância da [Evolution API](https://github.com/EvolutionAPI/evolution-api) (Go ou v2) rodando.

## 📦 Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/simiao2025/niersigloc.git
   cd niersigloc
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure as credenciais:
   - Renomeie `config.example.json` para `config.json`.
   - Preencha seus dados de acesso do SIGLOC e da Evolution API.

## 🚦 Como Usar

1. Inicie o servidor:
   ```bash
   python app.py
   ```
2. Acesse `http://localhost:8000` no seu navegador.
3. Conecte seu WhatsApp lendo o QR Code no painel.
4. Configure o horário e o destinatário e clique em **Atualizar Configurações**.

---
*Desenvolvido para automação administrativa eficiente.*
