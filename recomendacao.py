import json
import os
import glob
import math
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env (GEMINI_API_KEY)
load_dotenv() 

PESO_RISCO_IA = 0.60      # Risco da alegação
PESO_ENGAJAMENTO = 0.30  # Engajamento
PESO_AUTOR = 0.10    # Relevancia da conta

# CONFIGURAÇÃO DO GEMINI
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel('gemini-2.0-flash')
    print("Modelo configurado com sucesso.")

except Exception as e:
    print(f"Erro na configuração do modelo: {e}")
    model = None


def analisar_post_para_recomendacao(texto: str) -> dict:
    if not model: return {"error": "Modelo de IA não inicializado.", "verificavel": False}
    
    prompt = f"""
    Considere o cenário político brasileiro para fazer uma análise do risco do post a seguir conter algum tipo de desinformação:
    ---
    {texto}
    ---

    Responda SOMENTE em formato JSON com a estrutura exata abaixo:
    {{
      "verificavel": boolean,
      "alegacao_principal": "string",
      "categoria": "string",
      "risco_desinformacao": integer,
      "justificativa": "string"
    }}

    Instruções para preenchimento:
    - "verificavel": true se contiver uma alegação factual específica. false caso contrário.
    - "alegacao_principal": Extraia a alegação central de forma concisa. Se não for verificável, deixe em branco.
    - "categoria": Classifique a alegação em uma das seguintes categorias: "Fraude Eleitoral", "Ataque a Instituições", "Crítica a Políticos", "Economia", "Segurança Pública", "Política Geral", "Outros".
    - "risco_desinformacao": Atribua uma nota de 1 (baixo risco) a 10 (altíssimo risco).
    - "justificativa": Explique brevemente sua análise e a atribuição da nota de risco.
    """
    try:
        response = model.generate_content(prompt)
        json_text = response.text.strip().lstrip("```json").rstrip("```")
        return json.loads(json_text)

    except Exception as e:
        print(f"  -> Erro na análise da IA: {e}")
        return {"error": str(e), "verificavel": False}


def calcular_score(post: dict, analise_ia: dict) -> float:

    # 1. Score do Conteúdo
    risco_ia = analise_ia.get("risco_desinformacao", 0)
    score_conteudo = (risco_ia / 10.0)

    # 2. Score do Engajamento
    engajamento = post.get("engajamento", {})
    total_engajamento = engajamento.get("quantidade_respostas", 0) + engajamento.get("quantidade_retweets", 0) + engajamento.get("quantidade_likes", 0)
    score_engajamento = math.log10(total_engajamento + 1) / 6.0 
    score_engajamento = min(score_engajamento, 1.0)

    # 3. Score do Autor (influência)
    score_autor = 1.0 if post.get("autor", {}).get("verificado") else 0.5
    
    # 4. Cálculo final ponderado
    G10_score = (score_conteudo * PESO_RISCO_IA) + \
                    (score_engajamento * PESO_ENGAJAMENTO) + \
                    (score_autor * PESO_AUTOR)
    
    return round(G10_score * 100, 2)


def processar_e_recomendar():

    # Procura pelos arquivos
    arquivos_brutos = glob.glob("Coleta_*.json")
    if not arquivos_brutos:
        print("Nenhum arquivo de coleta (`Coleta_*.json`) encontrado para análise.")
        return

    print(f"Encontrados {len(arquivos_brutos)} arquivos para processar.")
    
    posts_para_recomendar = []

    for nome_arquivo in arquivos_brutos:
        print(f"\n--- Processando arquivo: {nome_arquivo} ---")
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            posts = json.load(f)
        
        for i, post in enumerate(posts):
            print(f"Analisando post {i+1}/{len(posts)}...", end="\r")
            
            # Passa o conteúdo do campo "texto" para a IA
            analise = analisar_post_para_recomendacao(post['texto'])
            
            if not analise.get("verificavel"):
                continue

            score = calcular_score(post, analise)

            post["analise_ia"] = analise
            post["G10_score"] = score
            
            posts_para_recomendar.append(post)
    print("\nAnálise de todos os arquivos concluída.")

    if not posts_para_recomendar:
        print("\nNenhum post com alegações verificáveis foi encontrado.")
        return

    # Ordena a lista final de recomendações pelo score, do maior para o menor
    posts_para_recomendar.sort(key=lambda p: p["G10_score"], reverse=True)

    print("\n\n" + "="*60)
    print("      TOP 10 POSTS RECOMENDADOS PARA VERIFICAÇÃO")
    print("="*60)

    for i, post in enumerate(posts_para_recomendar[:10]):
        print(f"{i+1}. Score: {post['G10_score']:.2f} | Risco IA: {post['analise_ia']['risco_desinformacao']}/10 | Categoria: {post['analise_ia']['categoria']}")
        print(f"   Alegação: {post['analise_ia']['alegacao_principal']}")
        print(f"   URL Fonte: {post['url_fonte']}")
        print(f"   Engajamento: {post['engajamento']['quantidade_retweets']} retweets")
        print("-" * 60)

    timestamp_salvamento = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"recomendacoes_G10_{timestamp_salvamento}.json"
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(posts_para_recomendar, f, ensure_ascii=False, indent=4)
        
    print(f"\nRelatório completo com {len(posts_para_recomendar)} posts recomendados salvo em '{output_filename}'.")

# Main
if __name__ == "__main__":
    if model:
        processar_e_recomendar()
    else:
        print("\nO script não pode ser iniciado. Verifique a configuração d.")
