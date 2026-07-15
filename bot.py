import os
import json
import random
import gspread
from google.oauth2.service_account import Credentials
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
from threading import Thread

# ==========================================
# 0. SERVIDOR WEB FICTÍCIO PARA O RENDER
# ==========================================
# Isso serve apenas para abrir a porta que o Render exige no plano grátis!
app = Flask('')

@app.route('/')
def home():
    return "Bot de RPG está ativo e rodando!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Inicia o servidor web em uma thread separada para não travar o bot do Telegram
Thread(target=run_flask).start()

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS & APIs
# ==========================================
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
NOME_PLANILHA = "rpg-pedagogico-perguntas"

bot = telebot.TeleBot(TOKEN_TELEGRAM)

try:
    creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(NOME_PLANILHA).worksheet("Perguntas")
    print("✅ Conectado ao Google Sheets com sucesso!")
except Exception as e:
    print(f"❌ Erro ao conectar ao Google Sheets: {e}")

# ==========================================
# 2. BANCO DE DADOS EM MEMÓRIA (LOBBY/PARTIDA)
# ==========================================
partida = {
    "estado": "IDLE",            
    "jogadores": {},             
    "pergunta_atual": 0,
    "hp_monstro": 50,
    "hp_grupo": 3,
    "perguntas_carregadas": []
}

# ==========================================
# 3. FUNÇÕES AUXILIARES
# ==========================================
def carregar_perguntas():
    try:
        dados = sheet.get_all_records()
        random.shuffle(dados)
        return dados
    except Exception as e:
        print(f"Erro ao buscar perguntas: {e}")
        return []

def criar_teclado_lobby():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⚔️ Entrar no Jogo", callback_data="lobby_entrar"),
        InlineKeyboardButton("🏁 Iniciar Partida", callback_data="lobby_iniciar")
    )
    return markup

def criar_teclado_alternativas():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Alternativa A", callback_data="voto_A"),
        InlineKeyboardButton("Alternativa B", callback_data="voto_B"),
        InlineKeyboardButton("Alternativa C", callback_data="voto_C")
    )
    return markup

# ==========================================
# 4. LÓGICA DO TELEGRAM - COMANDOS
# ==========================================

@bot.message_handler(commands=['jogar'])
def iniciar_lobby(message):
    global partida
    
    if partida["estado"] != "IDLE":
        bot.reply_to(message, "⚠️ Já existe um lobby ativo ou uma partida em andamento neste grupo!")
        return
        
    partida["estado"] = "LOBBY"
    partida["jogadores"] = {}
    partida["hp_monstro"] = 50
    partida["hp_grupo"] = 3
    partida["pergunta_atual"] = 0
    partida["perguntas_carregadas"] = carregar_perguntas()
    
    texto = (
        "🏰 **NOVA MASMORRA PEDAGÓGICA ABERTA!**\n"
        "Tema: *Alfabetização Midiática e Combate a Fake News*\n\n"
        "**Jogadores no Lobby (0/3):**\n"
        "⏳ Aguardando heróis entrarem..."
    )
    
    bot.send_message(message.chat.id, texto, parse_mode="Markdown", reply_markup=criar_teclado_lobby())

# ==========================================
# 5. PROCESSAMENTO DE CLIQUES (CALLBACK QUERIES)
# ==========================================

@bot.callback_query_handler(func=lambda call: True)
def processar_cliques(call):
    global partida
    user_id = str(call.from_user.id)
    nome_usuario = call.from_user.first_name

    if call.data == "lobby_entrar":
        if partida["estado"] != "LOBBY":
            bot.answer_callback_query(call.id, "O lobby já foi fechado!")
            return
            
        if user_id in partida["jogadores"]:
            bot.answer_callback_query(call.id, "Você já está no lobby!")
            return
            
        if len(partida["jogadores"]) >= 3:
            bot.answer_callback_query(call.id, "Desculpe, o lobby de teste está lotado! (Máx: 3)")
            return

        partida["jogadores"][user_id] = {
            "nome": nome_usuario,
            "respondeu": False,
            "escolha": None
        }
        
        lista_nomes = "\n".join([f"👤 {p['nome']}" for p in partida["jogadores"].values()])
        texto_atualizado = (
            "🏰 **NOVA MASMORRA PEDAGÓGICA ABERTA!**\n"
            "Tema: *Alfabetização Midiática*\n\n"
            f"**Jogadores no Lobby ({len(partida['jogadores'])}/3):**\n"
            f"{lista_nomes}\n\n"
            "Clique abaixo para entrar ou iniciar a batalha!"
        )
        
        bot.edit_message_text(texto_atualizado, call.message.chat.id, call.message.message_id, 
                              parse_mode="Markdown", reply_markup=criar_teclado_lobby())
        bot.answer_callback_query(call.id, "Você entrou na masmorra!")

    elif call.data == "lobby_iniciar":
        if partida["estado"] != "LOBBY":
            return
            
        if len(partida["jogadores"]) == 0:
            bot.answer_callback_query(call.id, "É necessário ter pelo menos 1 jogador no lobby para iniciar!")
            return
            
        partida["estado"] = "EM_BATALHA"
        bot.answer_callback_query(call.id, "A batalha começou!")
        enviar_pergunta_rodada(call.message.chat.id)

    elif call.data.startswith("voto_"):
        if partida["estado"] != "EM_BATALHA":
            return
            
        if user_id not in partida["jogadores"]:
            bot.answer_callback_query(call.id, "Você não faz parte desta guilda ativa!", show_alert=True)
            return
            
        if partida["jogadores"][user_id]["respondeu"]:
            bot.answer_callback_query(call.id, "Você já deu o seu veredito nesta rodada!")
            return
            
        voto = call.data.split("_")[1]
        partida["jogadores"][user_id]["respondeu"] = True
        partida["jogadores"][user_id]["escolha"] = voto
        
        bot.answer_callback_query(call.id, f"Voto {voto} computado com sucesso!")
        
        todos_responderam = all([p["respondeu"] for p in partida["jogadores"].values()])
        
        if todos_responderam:
            processar_fim_de_rodada(call.message.chat.id, call.message.message_id)
        else:
            atualizar_mensagem_batalha(call.message.chat.id, call.message.message_id)

# ==========================================
# 6. FLUXO DE TURNO & RESOLUÇÃO
# ==========================================

def enviar_pergunta_rodada(chat_id):
    global partida
    
    if partida["pergunta_atual"] >= len(partida["perguntas_carregadas"]):
        bot.send_message(chat_id, "🌪️ As perguntas acabaram! O monstro fugiu e a partida empatou!")
        partida["estado"] = "IDLE"
        return

    pergunta_foco = partida["perguntas_carregadas"][partida["pergunta_atual"]]
    
    for uid in partida["jogadores"]:
        partida["jogadores"][uid]["respondeu"] = False
        partida["jogadores"][uid]["escolha"] = None

    texto_pergunta = (
        f"👾 **MONSTRO ATIVO (HP: {partida['hp_monstro']}/50)**\n"
        f"❤️ **HP do Grupo: {partida['hp_grupo']}/3**\n"
        "-------------------------------------\n"
        f"📜 **DESAFIO {partida['pergunta_atual'] + 1}:**\n"
        f"*{pergunta_foco['Pergunta']}*\n\n"
        f"A) {pergunta_foco['Alternativa_A']}\n"
        f"B) {pergunta_foco['Alternativa_B']}\n"
        f"C) {pergunta_foco['Alternativa_C']}\n\n"
        "**Status das Respostas:**\n"
    )
    
    for p in partida["jogadores"].values():
        texto_pergunta += f"👤 {p['nome']}: ⏳ Aguardando...\n"

    bot.send_message(chat_id, texto_pergunta, parse_mode="Markdown", reply_markup=criar_teclado_alternativas())

def atualizar_mensagem_batalha(chat_id, message_id):
    global partida
    pergunta_foco = partida["perguntas_carregadas"][partida["pergunta_atual"]]
    
    texto_pergunta = (
        f"👾 **MONSTRO ATIVO (HP: {partida['hp_monstro']}/50)**\n"
        f"❤️ **HP do Grupo: {partida['hp_grupo']}/3**\n"
        "-------------------------------------\n"
        f"📜 **DESAFIO {partida['pergunta_atual'] + 1}:**\n"
        f"*{pergunta_foco['Pergunta']}*\n\n"
        f"🅰️ {pergunta_foco['Alternativa_A']}\n"
        f"🅱️ {pergunta_foco['Alternativa_B']}\n"
        f"🆃 {pergunta_foco['Alternativa_C']}\n\n"
        "**Status das Respostas:**\n"
    )
    
    for p in partida["jogadores"].values():
        status = "✅ Pronto!" if p["respondeu"] else "⏳ Aguardando..."
        texto_pergunta += f"👤 {p['nome']}: {status}\n"
        
    bot.edit_message_text(texto_pergunta, chat_id, message_id, parse_mode="Markdown", reply_markup=criar_teclado_alternativas())

def processar_fim_de_rodada(chat_id, message_id):
    global partida
    pergunta_foco = partida["perguntas_carregadas"][partida["pergunta_atual"]]
    resposta_correta = str(pergunta_foco['Correta']).strip().upper()
    
    acertos = 0
    erros = 0
    detalhes_resultado = ""

    for p in partida["jogadores"].values():
        if p["escolha"] == resposta_correta:
            acertos += 1
            detalhes_resultado += f"✅ *{p['nome']}* acertou! (Causou 10 de dano)\n"
        else:
            erros += 1
            detalhes_resultado += f"❌ *{p['nome']}* errou! (Sua resposta foi {p['escolha']})\n"

    dano_no_monstro = acertos * 10
    dano_no_grupo = 1 if erros > 0 else 0

    partida["hp_monstro"] -= dano_no_monstro
    partida["hp_grupo"] -= dano_no_grupo

    bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)

    texto_resultado = (
        f"📊 **RESULTADO DA RODADA {partida['pergunta_atual'] + 1}:**\n\n"
        f"{detalhes_resultado}\n"
        f"💥 O grupo aplicou **{dano_no_monstro} de dano** no monstro!\n"
        f"💔 O grupo recebeu **{dano_no_grupo} de dano**!\n\n"
        f"👾 HP do Monstro: {max(0, partida['hp_monstro'])}/50\n"
        f"❤️ HP da Guilda: {max(0, partida['hp_grupo'])}/3\n"
    )
    
    bot.send_message(chat_id, texto_resultado, parse_mode="Markdown")

    if partida["hp_monstro"] <= 0:
        bot.send_message(chat_id, "🎉 **VITÓRIA!** Vocês desmascararam a fake news e derrotaram o monstro! O reino de Veridion está salvo graças aos Detetives da Informação! 🏆")
        partida["estado"] = "IDLE"
    elif partida["hp_grupo"] <= 0:
        bot.send_message(chat_id, "💀 **DERROTA!** O grupo caiu sob a desinformação do monstro. Estudem mais as técnicas de checagem e tentem novamente usando `/jogar`!")
        partida["estado"] = "IDLE"
    else:
        partida["pergunta_atual"] += 1
        bot.send_message(chat_id, "⏳ Próximo desafio se aproximando em 5 segundos...")
        import time
        time.sleep(5)
        enviar_pergunta_rodada(chat_id)

# ==========================================
# COMANDO EXTRA: RESETAR O JOGO
# ==========================================
@bot.message_handler(commands=['resetar', 'limpar'])
def resetar_jogo(message):
    global partida
    
    # Reseta todas as variáveis do jogo para o estado inicial
    partida = {
        "estado": "IDLE",            
        "jogadores": {},             
        "pergunta_atual": 0,
        "hp_monstro": 50,
        "hp_grupo": 3,
        "perguntas_carregadas": []
    }
    
    texto_reset = (
        "🔄 **SISTEMA REINICIADO!**\n\n"
        "A masmorra ativa foi limpa e todas as variáveis foram resetadas.\n"
        "Você já pode iniciar um novo jogo digitando `/jogar`!"
    )
    
    bot.send_message(message.chat.id, texto_reset, parse_mode="Markdown")

# ==========================================
# 7. INICIALIZAÇÃO
# ==========================================
if __name__ == "__main__":
    print("🤖 Bot Iniciado e pronto para rodar!")
    bot.infinity_polling()
