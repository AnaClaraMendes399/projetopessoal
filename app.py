# app.py
import os
import json
import re
from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai
from google.genai import types
from dotenv import load_dotenv

from config import REDACAO_SCHEMA, SYSTEM_INSTRUCTION

# Carrega as variáveis de ambiente e inicia o Gemini
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Inicializa o Flask
app = Flask(__name__)
CORS(app)

# LISTA DE PALAVRÕES E CONTEÚDO OFENSIVO
PALAVROES = [
    "puta", "caralho", "buceta", "merda", "foda-se", "foder", "fodo", "fode",
    "viado", "bicha", "macaco", "neguinho", "crioulo", "vagabundo", 
    "ladrao", "bandido", "filhodaputa", "filho da puta", "desgraca",
    "porra", "bosta", "otario", "idiota", "imbecil", "otária",
    "retardado", "doente", "corna", "cornu", "chifrudo",
    "transar", "trepar", "pinto", "piroca", "rola",
    "nazista", "hitler", "racista", "analfabeto"
]

# Palavras comuns que contêm 'cu' mas NÃO SÃO PALAVRÕES
PALAVRAS_SEGURAS = [
    "desintrusao", "desintrusão", "cultura", "cuidado", "cuidadoso", "cuidadosa",
    "educacao", "educação", "educar", "documento", "documentacao", "documentação",
    "recuperar", "recuperacao", "recuperação", "acurado", "acumulado", "acumular",
    "custeio", "custear", "obscuro", "obscuridade", "escultura", "escultural",
    "agricultura", "pecuaria", "pecuária", "socultura", "aquicultura"
]

def contem_palavrao(texto):
    """Verifica se o texto contém palavras ofensivas"""
    if not texto:
        return None
    
    texto_lower = texto.lower()
    
    # Remove palavras seguras
    texto_filtrado = texto_lower
    for segura in PALAVRAS_SEGURAS:
        texto_filtrado = texto_filtrado.replace(segura, " " * len(segura))
    
    # Verifica palavras ofensivas
    for palavra in PALAVROES:
        padrao = r'\b' + re.escape(palavra) + r'\b'
        if re.search(padrao, texto_filtrado):
            return palavra
    
    return None


def detectar_modo(requisicao):
    """Detecta se o usuário quer ajuda, correção ou ambos"""
    texto = requisicao.get("mensagem", "").lower()
    redacao = requisicao.get("redacao", "")
    
    if "corrige" in texto or "avalia" in texto or "nota" in texto or redacao:
        if "ajuda" in texto or "criar" in texto or "tema" in texto:
            return "ambos"
        return "corrigir"
    return "ajudar"


def generate_redacao(requisicao):
    """Chama o Gemini para gerar resposta de redação"""
    modo = detectar_modo(requisicao)
    mensagem = requisicao.get("mensagem", "")
    redacao = requisicao.get("redacao", "")
    genero = requisicao.get("genero", "dissertacao_argumentativa")
    
    # Constrói o prompt baseado no modo
    if modo == "ajudar":
        conteudo_prompt = f"""
Modo AJUDAR. Genero: {genero}. Usuario pede: {mensagem}

Voce DEVE retornar UM JSON com os campos:
- status: "aceito"
- modo: "ajudar"
- genero: "{genero}"
- tema_sugerido: tema adequado ao genero {genero}
- eixo_tematico: um eixo tematico (se aplicavel)
- esqueleto_redacao: objeto com introducao, desenvolvimento_1, desenvolvimento_2, conclusao (adaptado ao genero)
- dicas_escrita: array com 3-5 dicas para este genero
- repertorio_sugerido: array com 3-5 referencias

NAO escreva a redacao completa.
"""

    elif modo == "corrigir":
        if genero == "dissertacao_argumentativa":
            conteudo_prompt = f"""
Modo CORRIGIR. Genero: {genero}. Redacao do usuario: {redacao}

AVALIE usando o campo "notas_competencia" com 5 competencias (0-200 cada, total 1000):
- c1_norma_culta: dominio da norma padrao (0-200)
- c2_compreensao_tema: compreensao do tema (0-200)
- c3_argumentacao: argumentacao e repertorio (0-200)
- c4_linguagem: coesao e coerencia (0-200)
- c5_proposta_intervencao: agente, acao, meio, efeito, detalhamento (0-200)

Calcule a nota_total = soma das 5 competencias (maximo 1000)

Liste erros, sugestoes, exemplo de reescrita e feedback final.
"""
        else:
            conteudo_prompt = f"""
Modo CORRIGIR. Genero: {genero}. Redacao do usuario: {redacao}

AVALIE usando o campo "notas_genericas" com 4 criterios (0-100 cada, total 400):
- estrutura: organizacao do texto (introducao, desenvolvimento, conclusao) (0-100)
- adequacao_genero: segue as regras do genero {genero} (0-100)
- clareza_coerencia: ideias claras e logicas, sem contradicoes (0-100)
- gramatica: ortografia, pontuacao, concordancia, regencia (0-100)

Calcule a nota_total = soma das 4 notas (maximo 400)

Liste erros especificos, sugestoes de correcao, exemplo de reescrita e feedback final.
"""

    else:
        conteudo_prompt = f"""
Modo AMBOS. Genero: {genero}.
Primeiro, ajude o usuario com tema e estrutura para: {mensagem}
Depois, corrija esta redacao: {redacao}

Preencha TODOS os campos de ajuda E de correcao.
"""
    
    response = client.models.generate_content(
        model="gemini-3-flash-preview",  # ✅ Mantido como você pediu
        contents=conteudo_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=REDACAO_SCHEMA,
        )
    )
    return response.text


@app.route("/")
def root():
    return jsonify({
        "status": "success",
        "message": "WriteWise - Assistente de Redacao funcionando!",
        "version": "2.0",
        "generos_disponiveis": ["dissertacao_argumentativa", "carta_aberta", "artigo_opiniao", "narrativa", "descricao", "conto", "cronica"]
    }), 200


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    
    if not data or ("mensagem" not in data and "redacao" not in data):
        return jsonify({
            "status": "error",
            "message": "Envie mensagem ou redacao no JSON."
        }), 400
    
    genero = data.get("genero", "dissertacao_argumentativa")
    
    generos_validos = ["dissertacao_argumentativa", "carta_aberta", "artigo_opiniao", "narrativa", "descricao", "conto", "cronica"]
    if genero not in generos_validos:
        return jsonify({
            "status": "error",
            "message": f"Genero invalido. Escolha um: {', '.join(generos_validos)}"
        }), 400
    
    # VALIDAÇÃO DE PALAVRÕES NA MENSAGEM
    mensagem = data.get("mensagem", "")
    if mensagem:
        palavra_proibida = contem_palavrao(mensagem)
        if palavra_proibida:
            return jsonify({
                "status": "recusado",
                "mensagem": f"Infelizmente nao posso processar esta requisicao. Detectei conteudo inadequado ('{palavra_proibida}'). Por favor, use linguagem respeitosa."
            }), 400
    
    # VALIDAÇÃO DE PALAVRÕES NA REDACAO
    redacao = data.get("redacao", "")
    if redacao:
        palavra_proibida = contem_palavrao(redacao)
        if palavra_proibida:
            return jsonify({
                "status": "recusado",
                "mensagem": f"Infelizmente nao posso processar esta requisicao. Detectei conteudo inadequado ('{palavra_proibida}') na sua redacao. Por favor, escreva um texto com linguagem respeitosa."
            }), 400
    
    if redacao and len(redacao.split()) < 30:
        return jsonify({
            "status": "error",
            "message": "Redacao muito curta. Escreva pelo menos 30 palavras."
        }), 400
    
    try:
        resposta_json_string = generate_redacao(data)
        print("RESPOSTA GEMINI:", resposta_json_string)
        
        resposta_estruturada = json.loads(resposta_json_string)
        
        if resposta_estruturada.get("status") == "recusado":
            return jsonify({
                "status": "recusado",
                "mensagem": resposta_estruturada.get("motivo_recusa", "Requisicao invalida."),
                "requisicao_enviada": data
            }), 400
        
        return jsonify({
            "status": "success",
            "genero": genero,
            "modo": resposta_estruturada.get("modo"),
            "dados_resposta": resposta_estruturada
        }), 200
        
    except json.JSONDecodeError as e:
        return jsonify({
            "status": "error",
            "message": f"Erro ao processar resposta do Gemini: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erro ao gerar resposta: {str(e)}"
        }), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)