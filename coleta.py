import time
import json
import hashlib
import re
import os
import subprocess
import sys
import platform
import traceback
from datetime import datetime
from typing import Set, Dict, Any, List, Optional
from pathlib import Path
import undetected_chromedriver as uc
import whisper
import pytesseract
from PIL import Image
import requests
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


# Configuração de ambiente
SCRIPT_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
BIN_DIR = SCRIPT_DIR / "bin"
if BIN_DIR.is_dir():
    os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ["PATH"]

# Verificação do Tesseract
try:
    if platform.system() == "Windows":
        subprocess.run(['tesseract', '--version'], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
         subprocess.run(['tesseract', '--version'], check=True, capture_output=True)
    print("[INFO] Tesseract OCR encontrado no PATH do sistema.")
except (subprocess.CalledProcessError, FileNotFoundError):
    print("[ALERTA] Tesseract OCR não encontrado no PATH.")
    if platform.system() == "Windows":
        caminho_tesseract_fallback = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if Path(caminho_tesseract_fallback).exists():
            pytesseract.pytesseract.tesseract_cmd = caminho_tesseract_fallback
            print(f"[INFO] Usando Tesseract OCR do caminho padrão: {caminho_tesseract_fallback}")
        else:
            print("[ERRO FATAL] Tesseract OCR não encontrado. Por favor, instale-o e adicione ao PATH do sistema.")
            sys.exit(1)

# Constantes
INSTANCIA = "https://twiiit.com"
SALT_LGPD = "dAurora_Salt"
MAX_RESULTADOS_POR_BUSCA = 20
INTERVALO_COLETA_SEGUNDOS = 600
PASTA_DOWNLOADS = SCRIPT_DIR / "midia_coletada"
PASTA_SAIDA = SCRIPT_DIR / "Coletas"
DELETAR_MIDIA_APOS_COLETA = True
TEMPO_ESPERA_SELENIUM = 60
ARQUIVO_IDS_PERSISTIDOS = SCRIPT_DIR / "ids_coletados.txt"

HEADERS_NAVEGADOR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': f'{INSTANCIA}/',
}

try:
    NOME_ARQUIVO_BUSCAS = "lista_de_buscas.txt"
    with open(SCRIPT_DIR / NOME_ARQUIVO_BUSCAS, 'r', encoding='utf-8') as f:
        LISTA_DE_BUSCAS = [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]
    if not LISTA_DE_BUSCAS:
        print(f"[ALERTA] Arquivo de buscas '{NOME_ARQUIVO_BUSCAS}' está vazio.")
        sys.exit()
    print(f"[INFO] {len(LISTA_DE_BUSCAS)} termos de busca carregados de '{NOME_ARQUIVO_BUSCAS}'.")
except FileNotFoundError:
    print(f"\n[ERRO FATAL] Arquivo de buscas '{NOME_ARQUIVO_BUSCAS}' não foi encontrado.")
    sys.exit(1)

SELECTORS_POST_CONTAINER = ['div.tweet-card', 'div.timeline-item']

# Funções auxiliares
def carregar_ids_ja_coletados(caminho_arquivo: Path) -> Set[str]:
    if not caminho_arquivo.exists(): return set()
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except Exception as e:
        print(f"[ALERTA] Não foi possível ler o arquivo de IDs '{caminho_arquivo}': {e}")
        return set()

def salvar_novos_ids(caminho_arquivo: Path, novos_ids: List[str]):
    try:
        with open(caminho_arquivo, 'a', encoding='utf-8') as f:
            for post_id in novos_ids: f.write(f"{post_id}\n")
    except Exception as e:
        print(f"[ALERTA] Não foi possível salvar os novos IDs no arquivo '{caminho_arquivo}': {e}")

def pseudonimizar_usuario(username: str) -> str:
    return hashlib.sha256(f"{username}{SALT_LGPD}".encode('utf-8')).hexdigest()

def parse_stat_value(text: str) -> int:
    text = text.strip().lower()
    if not text: return 0
    text_limpo = re.sub(r'[^\d.km]', '', text)
    multiplicador = 1
    if 'k' in text_limpo: multiplicador = 1000; text_limpo = text_limpo.replace('k', '')
    elif 'm' in text_limpo: multiplicador = 1_000_000; text_limpo = text_limpo.replace('m', '')
    try: return int(float(text_limpo) * multiplicador)
    except (ValueError, TypeError): return 0

def download_midia(url: str, pasta_destino: Path, post_id: str, tipo: str) -> Optional[Path]:
    caminho_final = None
    for tentativa in range(3):
        try:
            print(f"  -> Baixando {tipo} (tentativa {tentativa + 1}/3)...", end="\r")
            if tipo == "vídeo":
                caminho_saida_template = pasta_destino / f"{post_id}.%(ext)s"
                cmd = ['yt-dlp', '-o', str(caminho_saida_template), '--restrict-filenames', '--extractor-args', 'generic:impersonate', url]
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                resultado = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False, creationflags=flags)
                if resultado.returncode != 0:
                    match = re.search(r'\[download\] (.*?) has already been downloaded', resultado.stderr)
                    if match:
                        caminho_existente = Path(match.group(1).strip())
                        print(f"  -> Vídeo já baixado: {caminho_existente.name}{' '*20}")
                        return caminho_existente
                    raise subprocess.CalledProcessError(resultado.returncode, cmd, output=resultado.stdout, stderr=resultado.stderr)
                arquivos_baixados = list(pasta_destino.glob(f"{post_id}.*"))
                if arquivos_baixados:
                    caminho_final = arquivos_baixados[0]; print(f"  -> Vídeo salvo: {caminho_final.name}{' '*30}"); return caminho_final
                return None
            elif tipo == "imagem":
                response = requests.get(url, stream=True, headers=HEADERS_NAVEGADOR, timeout=30)
                response.raise_for_status()
                extensao = url.split('.')[-1].split('?')[0]
                if len(extensao) > 4 or not extensao: extensao = 'jpg'
                caminho_final = pasta_destino / f"{post_id}.{extensao}"
                with open(caminho_final, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
                print(f"  -> Imagem salva: {caminho_final.name}{' '*30}")
                return caminho_final
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403: print(f"  -> Acesso negado (403 Forbidden). O servidor bloqueou o download.{' '*20}"); break
            print(f"  -> Erro de HTTP na tentativa {tentativa + 1}: {e}")
        except (requests.exceptions.RequestException, subprocess.CalledProcessError) as e:
            print(f"  -> Falha (conexão/processo) na tentativa {tentativa + 1}.{' '*20}")
        if tentativa < 2: time.sleep(5)
    print(f"  -> Download da {tipo} falhou após múltiplas tentativas.{' '*20}")
    return None

def transcrever_imagem_ocr(caminho_imagem: Path) -> Optional[str]:
    try:
        print(f"  -> Lendo texto da imagem (OCR): {caminho_imagem.name}", end="\r")
        imagem = Image.open(caminho_imagem)
        texto = pytesseract.image_to_string(imagem, lang='por+eng')
        return texto.strip() if texto else None
    except pytesseract.TesseractNotFoundError: print("  -> ERRO: Executável do Tesseract não encontrado. A função OCR será pulada."); return None
    except Exception: print(f"  -> Erro detalhado durante o OCR em: {caminho_imagem.name}"); return None

def transcrever_video(caminho_video: Path, modelo_whisper) -> Optional[str]:
    try:
        print(f"  -> Transcrevendo vídeo: {caminho_video.name}", end="\r")
        resultado = modelo_whisper.transcribe(str(caminho_video), fp16=False)
        return resultado.get("text", "").strip()
    except Exception as e: print(f"  -> Erro durante a transcrição do vídeo: {e}"); return None


def iniciar_driver() -> uc.Chrome:
    """Configura e inicia uma instância do undetected_chromedriver."""
    options = uc.ChromeOptions()

    # Adiciona o perfil persistente para salvar cookies e sessões para facilitar a contornar restrições
    profile_path = SCRIPT_DIR / "chrome_profile"
    options.add_argument(f"--user-data-dir={profile_path}")

    # Para visualizar a execução das buscas no navegador, deixe headless=False
    driver = uc.Chrome(options=options, headless=False)
    
    return driver

def coletar_posts_com_selenium(posts_ja_coletados: Set[str], modelo_whisper) -> List[Dict[str, Any]]:
    novos_posts_neste_ciclo = []
    PASTA_DOWNLOADS.mkdir(exist_ok=True)
    driver = iniciar_driver()
    wait = WebDriverWait(driver, TEMPO_ESPERA_SELENIUM)
    try:
        for termo_busca in LISTA_DE_BUSCAS:
            print(f"\nBuscando por: '{termo_busca}'")
            try:
                search_url = f"{INSTANCIA}/search?f=tweets&q={termo_busca}&lang=pt"
                driver.get(search_url)
                
                # Se o CAPTCHA aparecer (na primeira vez), resolva manualmente. Com isso, o navegador salvará a solução, e não pedirá novamente nas próximas execuções.
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ", ".join(SELECTORS_POST_CONTAINER))))

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                post_items = soup.select(", ".join(SELECTORS_POST_CONTAINER))

                for item in post_items[:MAX_RESULTADOS_POR_BUSCA]:
                    post_path_element = item.select_one('a[href*="/status/"]')
                    post_path = post_path_element['href'] if post_path_element else ""
                    post_id = post_path.split('/status/')[-1].split('#')[0] if "/status/" in post_path else None
                    if not post_id or post_id in posts_ja_coletados: continue
                    texto = item.select_one('div.tweet-content').text.strip() if item.select_one('div.tweet-content') else None
                    if not texto: continue
                    try:
                        if detect(texto) != 'pt': continue
                    except LangDetectException: continue
                    username = item.select_one('a.username').text.strip('@') if item.select_one('a.username') else None
                    if not username: continue
                    print(f"  -> Processando post candidato (ID: {post_id})...", end="\r")
                    stats_container = item.select_one('.tweet-stats')
                    post_final = {
                        "post_id": post_id, "texto": texto,
                        "publicado_em": item.select_one('.tweet-date a')['title'] if item.select_one('.tweet-date a') else 'N/A',
                        "url_fonte": f"https://x.com/{username}/status/{post_id}",
                        "autor": {
                            "id_pseudonimizado": pseudonimizar_usuario(username), "username": username,
                            "nome_completo": item.select_one('a.fullname').text.strip() if item.select_one('a.fullname') else 'N/A',
                            "verificado": bool(item.select_one('.icon-verified'))
                        },
                        "engajamento": {
                            "respostas": parse_stat_value(stats_container.select_one('.icon-comment').parent.text) if stats_container and stats_container.select_one('.icon-comment') else 0,
                            "retweets": parse_stat_value(stats_container.select_one('.icon-retweet').parent.text) if stats_container and stats_container.select_one('.icon-retweet') else 0,
                            "likes": parse_stat_value(stats_container.select_one('.icon-heart').parent.text) if stats_container and stats_container.select_one('.icon-heart') else 0
                        },
                        "metadados": {
                            "coletado_em": datetime.now().isoformat(), "termo_de_busca": termo_busca,
                            "tem_midia": False, "comentario": bool(item.select_one('.tweet-in-reply-to')),
                            "transcricao_midia": None
                        }
                    }
                    caminho_midia = None
                    imagem_tag = item.select_one('div.attachments .attachment.image img')
                    video_tag = item.select_one('div.attachments .attachment.video-container')
                    if imagem_tag and imagem_tag.get('src'):
                        url_midia = imagem_tag['src']
                        if url_midia.startswith('/'): url_midia = INSTANCIA + url_midia
                        caminho_midia = download_midia(url_midia, PASTA_DOWNLOADS, post_id, "imagem")
                        if caminho_midia: post_final["metadados"]["transcricao_midia"] = transcrever_imagem_ocr(caminho_midia)
                    elif video_tag:
                        url_para_video = f"{INSTANCIA}/{username}/status/{post_id}"
                        caminho_midia = download_midia(url_para_video, PASTA_DOWNLOADS, post_id, "vídeo")
                        if caminho_midia: post_final["metadados"]["transcricao_midia"] = transcrever_video(caminho_midia, modelo_whisper)
                    if caminho_midia:
                        post_final["metadados"]["tem_midia"] = True
                        if DELETAR_MIDIA_APOS_COLETA:
                            try:
                                os.remove(caminho_midia); print(f"  -> Mídia temporária removida: {caminho_midia.name}{' '*20}")
                            except OSError as e: print(f"  -> Erro ao remover mídia temporária: {e}")
                    novos_posts_neste_ciclo.append(post_final)
                    posts_ja_coletados.add(post_id)
                    print(f"  -> Novo post processado! (ID: {post_id}){' '*40}")
            except TimeoutException: print(f"  -> ERRO: Tempo esgotado ao buscar por '{termo_busca}'. A página de resultados não carregou.")
            except Exception as e: print(f"  -> ERRO inesperado na busca por '{termo_busca}': {e}")
    finally:
        if driver: driver.quit()
    return novos_posts_neste_ciclo


if __name__ == "__main__":
    print("\n" + "="*60)
    print("      INICIANDO COLETOR DE DADOS (NAVEGADOR INDETECTÁVEL)")
    print("="*60 + "\n")
    try:
        ids_coletados_global = carregar_ids_ja_coletados(ARQUIVO_IDS_PERSISTIDOS)
        print(f"[INFO] {len(ids_coletados_global)} IDs de posts já coletados foram carregados.")
        print("\nCarregando modelo de transcrição Whisper (base)... Isso pode levar um momento.")
        modelo_whisper = whisper.load_model("base")
        print("Modelo carregado com sucesso!\n")
        PASTA_SAIDA.mkdir(exist_ok=True)
        while True:
            timestamp_inicio_ciclo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n--- INICIANDO NOVO CICLO DE COLETA ({timestamp_inicio_ciclo}) ---")
            novos_posts = coletar_posts_com_selenium(ids_coletados_global, modelo_whisper)
            if novos_posts:
                print(f"\n\nSUCESSO! {len(novos_posts)} novo(s) post(s) coletado(s) neste ciclo.")
                timestamp_salvamento = datetime.now().strftime("%Y%m%d_%H%M%S")
                nome_arquivo_base = f"Coleta_{timestamp_salvamento}.json"
                caminho_arquivo_final = PASTA_SAIDA / nome_arquivo_base
                with open(caminho_arquivo_final, 'w', encoding='utf-8') as f:
                    json.dump(novos_posts, f, ensure_ascii=False, indent=4)
                print(f"Dados salvos em: {caminho_arquivo_final}")
                ids_deste_ciclo = [post['post_id'] for post in novos_posts]
                salvar_novos_ids(ARQUIVO_IDS_PERSISTIDOS, ids_deste_ciclo)
                print(f"{len(ids_deste_ciclo)} novo(s) ID(s) foram adicionados ao arquivo de persistência.")
            else:
                print("\nNenhum post novo encontrado neste ciclo.")
            print(f"--- Ciclo concluído. Aguardando {INTERVALO_COLETA_SEGUNDOS} segundos... ---")
            time.sleep(INTERVALO_COLETA_SEGUNDOS)
    except KeyboardInterrupt:
        print("\n\nColeta interrompida pelo usuário.")
    except WebDriverException as e:
        print(f"\n[ERRO FATAL DE WEBDRIVER] Verifique sua instalação do Chrome/ChromeDriver e a conexão de rede: {e}")
    except Exception as e:
        print(f"\n[ERRO FATAL] Ocorreu um erro inesperado: {e}")
    print("Monitoramento concluído.")