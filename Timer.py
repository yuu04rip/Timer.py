import discord
from discord.ext import commands
import time, asyncio
from gtts import gTTS
from discord import FFmpegPCMAudio
import os
from flask import Flask, jsonify, request
from threading import Thread
import requests

# Imposta il bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Variabili globali timer
session_start_time = None
total_study_time = 0
timer_start_time = None
timer_duration = 0
is_running = False
pomodoro_active = False  # Per ciclo Pomodoro

# Inizializza il server Flask
app = Flask(__name__)

@app.route('/start_timer', methods=['POST'])
def start_timer():
    global timer_start_time, timer_duration, is_running
    minutes = request.json.get('minutes')
    print(f"Ricevuta richiesta per {minutes} minuti")  # Debug
    if is_running:
        return jsonify({'message': 'Il timer è già in esecuzione.'}), 400
    timer_start_time = time.time()
    timer_duration = minutes * 60
    is_running = True
    return jsonify({'message': f"Timer avviato per {minutes} minuti."})

@app.route('/pause_timer', methods=['POST'])
def pause_timer():
    global is_running
    if not is_running:
        return jsonify({'message': 'Il timer non è in esecuzione.'}), 400
    is_running = False
    return jsonify({'message': 'Timer messo in pausa.'})

@app.route('/reset_timer', methods=['POST'])
def reset_timer():
    global timer_start_time, timer_duration, is_running
    timer_start_time = None
    timer_duration = 0
    is_running = False
    return jsonify({'message': 'Timer resettato.'})

@app.route('/get_timer', methods=['GET'])
def get_timer():
    if is_running:
        time_left = max(0, timer_duration - (time.time() - timer_start_time))
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        return jsonify({'time_remaining': f'{minutes_left:02}:{seconds_left:02}'})
    return jsonify({'time_remaining': '00:00'})

def run_flask():
    app.run(port=3001)

# Avvia Flask in un thread separato
flask_thread = Thread(target=run_flask)
flask_thread.start()
#help
@bot.command(name="comandi")
async def mostra_comandi(ctx):
    help_message = (
        "**📚 COMANDI DISPONIBILI**\n\n"
        "**🎓 Studio e Timer**\n"
        "`!studio <minuti>` - Avvia una sessione di studio per N minuti\n"
        "`!pausa` - Mette in pausa la sessione\n"
        "`!reset` - Resetta il timer attuale\n"
        "`!timer_status` - Mostra il tempo rimanente\n"
        "`!tempo_studio_attuale` - Mostra da quanto stai studiando\n"
        "`!tempo_totale` - Mostra il tempo totale di studio cumulato\n\n"
        "**🍅 Pomodoro**\n"
        "`!pomodoro <min_studio> <min_pausa>` - Avvia il ciclo Pomodoro\n"
        "`!stop` - Ferma il ciclo Pomodoro attivo\n\n"
        "**🔊 Canale Vocale**\n"
        "`!join` - Il bot entra nel tuo canale vocale\n"
        "`!leave` - Il bot esce dal canale vocale\n"
    )
    await ctx.send(help_message)


# Comando per far entrare il bot in vocale
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send("🔊 Mi sono unito al canale vocale!")
    else:
        await ctx.send("❌ Devi essere in un canale vocale.")

# Comando per farlo uscire dalla vocale
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Uscito dal canale vocale!")
    else:
        await ctx.send("❌ Non sono in un canale vocale.")

# Comando per avviare il timer studio
@bot.command()
async def studio(ctx, minuti: int):
    global session_start_time
    session_start_time = time.time()
    await ctx.send(f"🧠 Studio avviato per {minuti} minuti.")
    response = requests.post('http://localhost:3001/start_timer', json={'minutes': minuti})
    print(response.status_code, response.text)  # Debug
    if response.status_code == 200:
        await timer_voice(ctx, minuti, "Cazzo fratello la sessione è terminata!")
    else:
        await ctx.send(f"❌ {response.json()['message']}")

# Comando per pausa
@bot.command()
async def pausa(ctx):
    await ctx.send("☕ Pausa iniziata.")
    response = requests.post('http://localhost:3001/pause_timer')
    if response.status_code == 200:
        await ctx.send(response.json()['message'])
    else:
        await ctx.send(f"❌ {response.json()['message']}")

@bot.command()
async def reset(ctx):
    global session_start_time, total_study_time
    await ctx.send("🔄 Reset del timer.")
    if session_start_time:
        total_study_time += time.time() - session_start_time
        session_start_time = None
    response = requests.post('http://localhost:3001/reset_timer')
    if response.status_code == 200:
        await ctx.send(response.json()['message'])
    else:
        await ctx.send(f"❌ {response.json()['message']}")

# Comando per vedere il timer rimanente
@bot.command()
async def timer_status(ctx):
    response = requests.get('http://localhost:3001/get_timer')
    await ctx.send(f"⏳ Tempo rimanente: {response.json()['time_remaining']}")
@bot.command()
async def tempo_studio_attuale(ctx):
    if session_start_time:
        elapsed = int(time.time() - session_start_time)
        minuti = elapsed // 60
        secondi = elapsed % 60
        await ctx.send(f"⏱️ Stai studiando da {minuti} minuti e {secondi} secondi.")
    else:
        await ctx.send("⚠️ Non hai una sessione di studio attiva.")
@bot.command()
async def tempo_totale(ctx):
    tempo_completo = total_study_time
    if session_start_time:
        tempo_completo += time.time() - session_start_time
    minuti = int(tempo_completo // 60)
    secondi = int(tempo_completo % 60)
    await ctx.send(f"📚 Tempo totale di studio: {minuti} minuti e {secondi} secondi.")

# Funzione per voce al termine del timer
async def timer_voice(ctx, minuti, messaggio):
    await asyncio.sleep(minuti * 60)
    if not pomodoro_active and not is_running:
        return
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        tts = gTTS(text=messaggio, lang='it')
        tts.save("fine_timer.mp3")
        if voice_client.is_connected():
            source = FFmpegPCMAudio("fine_timer.mp3")
            voice_client.play(source)
            while voice_client.is_playing():
                await asyncio.sleep(1)
        await voice_client.disconnect()
        os.remove("fine_timer.mp3")
    await ctx.send(f"📢 {messaggio}")

# Nuova funzione riutilizzabile per cicli pomodoro
async def ciclo_voce(ctx, minuti, messaggio):
    await asyncio.sleep(minuti * 60)
    if not pomodoro_active:
        return
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        tts = gTTS(text=messaggio, lang='it')
        tts.save("messaggio.mp3")
        if voice_client.is_connected():
            source = FFmpegPCMAudio("messaggio.mp3")
            voice_client.play(source)
            while voice_client.is_playing():
                await asyncio.sleep(1)
        await voice_client.disconnect()
        os.remove("messaggio.mp3")
    await ctx.send(f"📢 {messaggio}")

# Comando Pomodoro: studio/pausa ciclico
@bot.command()
async def pomodoro(ctx, minuti_studio: int, minuti_pausa: int):
    global pomodoro_active
    if pomodoro_active:
        await ctx.send("❗ Un ciclo Pomodoro è già in corso.")
        return
    pomodoro_active = True
    await ctx.send(f"🍅 Pomodoro iniziato: {minuti_studio} minuti studio, {minuti_pausa} minuti pausa.")
    while pomodoro_active:
        await ctx.send(f"🧠 Studio per {minuti_studio} minuti.")
        await ciclo_voce(ctx, minuti_studio, "Fratello finalmente puoi morire in pace, riposati!")
        if not pomodoro_active:
            break
        await ctx.send(f"☕ Pausa per {minuti_pausa} minuti.")
        await ciclo_voce(ctx, minuti_pausa, "Mi dispiace ma ti odio quindi torna a studiare!")

# Comando per fermare il ciclo pomodoro
@bot.command()
async def stop(ctx):
    global pomodoro_active
    if pomodoro_active:
        pomodoro_active = False
        await ctx.send("🛑 Ciclo Pomodoro interrotto.")
    else:
        await ctx.send("❌ Nessun ciclo Pomodoro attivo.")

# Evento bot pronto
@bot.event
async def on_ready():
    print(f'✅ Bot attivo come {bot.user.name}')


# Inserisci il tuo token qui:
bot.run('token')
