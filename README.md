# Coletor de dados 

## Visão Geral

Script de automação avançado, desenvolvido em Python, para a coleta e análise de conteúdo da rede social X a partir de front-ends públicos como o `twiiit.com`.

O script permite a extração de dados textuais e de mídia de postagens realizadas na rede, além de incorporar mecanismos para contornar defesas anti-automação, garantindo ciclos de coleta consistentes.

## Principais Funcionalidades

- **Coleta Automatizada por Termos:** Monitora continuamente um conjunto de termos de busca definidos pelo usuário.
- **Extração e Processamento de Mídia:**
  - **OCR para Imagens:** Utiliza o Tesseract para extrair texto de imagens publicadas.
  - **Transcrição de Vídeo:** Emprega o modelo *Whisper* da OpenAI para converter o áudio de vídeos em texto.
- **Persistência de Dados:** Mantém um registro local de posts já coletados para evitar duplicidade de dados entre as execuções.
- **Técnicas Anti-Detecção:** Implementa o `undetected-chromedriver` e um sistema de perfil de navegador persistente para navegar em sites com proteções avançadas (Cloudflare, reCAPTCHA) de forma mais eficaz.
- **Privacidade (LGPD):** Pseudonimiza os identificadores de usuário através de hash SHA256 com salt, em conformidade com as melhores práticas de proteção de dados.
- **Saída Estruturada:** Armazena os resultados em arquivos `.json` individuais por ciclo de coleta, facilitando a análise e integração com outros sistemas.

## Estrutura do Projeto

Para o correto funcionamento do script, a seguinte estrutura de pastas e arquivos deve ser mantida no diretório raiz:

```
/X/
├── chrome_profile/
├── Coletas/
├── coleta.py
├── lista_de_buscas.txt
└── ids_coletados.txt (criado automaticamente)
```

- `chrome_profile/`: Armazena a sessão do navegador (cookies, logins) para manter a "confiança" e evitar CAPTCHAs.
- `Coletas/`: Diretório de saída onde os arquivos `.json` com os dados coletados são salvos.
- `coleta.py`: O script principal do coletor.
- `lista_de_buscas.txt`: Arquivo de configuração onde os termos a serem monitorados são definidos.
- `ids_coletados.txt`: Arquivo de log com os IDs de todos os posts já processados.

## Pré-requisitos e Instalação

### Software Externo

Antes de executar o script, é necessário instalar os seguintes programas no sistema operacional (Windows):

1.  **Google Chrome:**
2.  **Tesseract-OCR:**
3.  **FFmpeg:** (essencial para a transcrição de vídeo)
4.  **yt-dlp:**

> **Nota:** É crucial que o **Tesseract** e o **FFmpeg** sejam adicionados ao PATH do sistema durante a instalação para que o script os encontre.

### Bibliotecas Python

Com o Python 3.9+ instalado, execute o comando abaixo no terminal, dentro da pasta do projeto, para instalar todas as dependências necessárias.

```bash
py -m pip install undetected-chromedriver openai-whisper pytesseract Pillow requests beautifulsoup4 langdetect selenium webdriver-manager
```

## Instruções de Uso

### 1. Configuração Inicial

Edite o arquivo `lista_de_buscas.txt` com os termos de busca desejados, um por linha. Linhas que começam com `#` são tratadas como comentários e ignoradas.

### 2. Primeira Execução ("Aquecimento")

Para que a automação contorne os sistemas de verificação, um "aquecimento" único do perfil do navegador é necessário.

1.  Certifique-se de que a pasta `chrome_profile/` esteja vazia.
2.  Execute o script. Uma janela do navegador Chrome será aberta.
3.  Nessa janela, realize as seguintes ações manualmente:
    - Navegue para `google.com` e faça login em uma conta Google.
    - Acesse o site alvo da coleta (`twiiit.com`).
    - Se um CAPTCHA aparecer, resolva-o.
4.  Após esses passos, pode fechar o navegador. A sessão de confiança foi salva.

### 3. Execução Normal

Para todas as execuções futuras, basta iniciar o script. Ele carregará o perfil "aquecido" e deverá navegar pelo site sem ser interrompido por verificações de segurança. Os dados coletados serão salvos na pasta `Coletas`.
