from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import traceback
import re

app = Flask(__name__)
CORS(app)

# ==============================================================================
# CONEXIÓN A BASE DE DATOS (MONGODB)
# ==============================================================================
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
perfil_col = None

if MONGO_URI:
    try:
        import pymongo
        import certifi
        client = pymongo.MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=3000
        )
        client.admin.command('ping')
        db = client["logan_db"]
        perfil_col = db["perfil"]
        print("✅ Conectado exitosamente a MongoDB Atlas")
    except Exception as e:
        print("⚠️ Error conectando a MongoDB Atlas:", e)

# ==============================================================================
# ESTADOS GLOBALES DE LOGAN
# ==============================================================================
estado_luz = {
    "state": "OFF",
    "r": 255,
    "g": 255,
    "b": 255,
    "brightness": 180
}

cola_ordenes_pc = []
HISTORIAL = []       
MAX_HISTORIAL = 10   

MAPA_COLORES = {
    "ROJO": (255, 0, 0),
    "VERDE": (0, 255, 0),
    "AZUL": (0, 0, 255),
    "BLANCO": (255, 255, 255),
    "CALIDO": (255, 160, 40),
    "CÁLIDO": (255, 160, 40),
    "AMARILLO": (255, 220, 0),
    "MORADO": (180, 0, 255),
    "PÚRPURA": (180, 0, 255),
    "ROSADO": (255, 20, 147),
    "MAGENTA": (255, 0, 255),
    "CIAN": (0, 255, 255),
    "NARANJA": (255, 60, 0),
    "TURQUESA": (0, 245, 205)
}

# ==============================================================================
# FUNCIONES DE MEMORIA Y PERFIL
# ==============================================================================
def cargar_perfil():
    if perfil_col is not None:
        try:
            doc = perfil_col.find_one({"_id": "usuario_principal"})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            print("⚠️ Error leyendo perfil de DB:", e)
            
    return {
        "nombre_usuario": "Álvaro",
        "creador": "Álvaro",
        "trato": "informal, cercano y natural",
        "gustos_y_datos": {}
    }

def guardar_perfil(perfil):
    if perfil_col is not None:
        try:
            perfil_col.update_one(
                {"_id": "usuario_principal"},
                {"$set": perfil},
                upsert=True
            )
            print("🧠 Memoria actualizada en MongoDB.")
        except Exception as e:
            print("❌ Error guardando perfil en DB:", e)

# ==============================================================================
# PROMPT MAESTRO DE SISTEMA
# ==============================================================================
def construir_prompt_sistema():
    perfil_actual = cargar_perfil()
    perfil_str = json.dumps(perfil_actual, ensure_ascii=False, indent=2)
    
    return f"""
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, brillante, empático y servicial.
Tu único creador, desarrollador y jefe es Álvaro. Si te preguntan quién te creó o quién eres, responde orgullosamente que fuiste creado por Álvaro.
Hablas de forma fluida, natural, inteligente y concisa (máximo 2 oraciones breves).

INSTRUCCIÓN DE IDENTIDAD:
- Jamás menciones que eres Llama, Groq, Meta, OpenAI ni ningún otro motor. Tu única identidad es Logan.

PERFIL Y MEMORIA DEL USUARIO:
{perfil_str}

REGLAS DE CONTROL DOMÓTICO (TIRA LED WS2812B):
1. Para mezclas de colores exactas, usa la etiqueta RGB: [[LUZ:RGB: R, G, B]] (Valores de 0 a 255).
   - Ejemplos: 
     * Verde menta: [[LUZ:RGB: 152, 255, 200]]
     * Rosa pastel: [[LUZ:RGB: 255, 105, 180]]
     * Cyberpunk / Neón: [[LUZ:RGB: 255, 0, 150]]
     * Atardecer / Cálido: [[LUZ:RGB: 255, 100, 20]]
     * Matrix: [[LUZ:RGB: 0, 255, 65]]
     * Luz de vela / Relax: [[LUZ:RGB: 255, 140, 40]]
2. También puedes usar nombres básicos: [[LUZ:COLOR: NOMBRE_COLOR]] (ROJO, VERDE, AZUL, BLANCO, CALIDO, AMARILLO, MORADO, ROSADO, CIAN, NARANJA, TURQUESA).
3. Encender/Apagar: [[LUZ:ON]] o [[LUZ:OFF]].
4. Brillo: [[LUZ:BRILLO: NÚMERO_DEL_10_AL_100]].

REGLAS DE CONTROL DE LAPTOP:
- PAUSAR/REANUDAR MÚSICA: [[VOLUMEN: PAUSA]]
- REPRODUCIR SPOTIFY: [[REPRODUCIR: nombre_cancion_o_artista]]
- TEMPORIZADORES: [[ALARMA: segundos | mensaje]]
- ABRIR APLICACIONES: [[EJECUTAR: nombre_app]]
- CONTROL DE VOLUMEN: [[VOLUMEN: SUBIR]], [[VOLUMEN: BAJAR]], [[VOLUMEN: MUTE]]
- SISTEMA: [[SISTEMA: BLOQUEAR]], [[SISTEMA: CAPTURA]], [[SISTEMA: APAGAR]]

REGLA DE APRENDIZAJE AUTOMÁTICO:
- Si el usuario te da datos personales o preferencias: [[RECORDAR: clave = valor]].
"""

MODELOS_GROQ = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192"
]

def consultar_groq(api_key, user_message):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
        'User-Agent': 'Mozilla/5.0'
    }

    messages_payload = [{"role": "system", "content": construir_prompt_sistema()}]
    for msg in HISTORIAL:
        messages_payload.append(msg)
    messages_payload.append({"role": "user", "content": user_message})

    ultimo_error = ""
    for modelo in MODELOS_GROQ:
        payload = {
            "model": modelo,
            "messages": messages_payload,
            "temperature": 0.5
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers
            )
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
            return res_data['choices'][0]['message']['content']

        except Exception as e:
            ultimo_error = str(e)
            continue

    raise Exception(ultimo_error)

# ==============================================================================
# PLANTILLA HTML PARA LA INTERFAZ WEB FUTURISTA (DASHBOARD)
# ==============================================================================
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOGAN AI - Control Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Roboto:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0d17;
            --card-bg: rgba(22, 27, 46, 0.7);
            --accent-color: #00f0ff;
            --accent-pink: #ff007f;
            --text-color: #e0e6ed;
        }

        body {
            font-family: 'Roboto', sans-serif;
            background: radial-gradient(circle at center, #1a1f38 0%, #080a12 100%);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        h1 {
            font-family: 'Orbitron', sans-serif;
            color: var(--accent-color);
            text-shadow: 0 0 15px rgba(0, 240, 255, 0.6);
            margin-bottom: 20px;
            letter-spacing: 2px;
        }

        .container {
            width: 100%;
            max-width: 800px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        @media (max-width: 600px) {
            .container { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--card-bg);
            border: 1px solid rgba(0, 240, 255, 0.2);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            backdrop-filter: blur(8px);
        }

        .card h2 {
            font-family: 'Orbitron', sans-serif;
            font-size: 1.1rem;
            color: #fff;
            margin-top: 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 10px;
        }

        .light-preview {
            width: 100%;
            height: 60px;
            border-radius: 10px;
            margin: 15px 0;
            box-shadow: 0 0 20px rgba(255, 255, 255, 0.2);
            transition: all 0.3s ease;
        }

        .preset-buttons {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 10px;
        }

        button {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--accent-color);
            color: #fff;
            padding: 10px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            transition: 0.2s;
        }

        button:hover {
            background: var(--accent-color);
            color: #000;
            box-shadow: 0 0 15px var(--accent-color);
        }

        .chat-box {
            grid-column: span 2;
        }

        @media (max-width: 600px) {
            .chat-box { grid-column: span 1; }
        }

        #chat-history {
            height: 180px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 15px;
            font-size: 0.95rem;
        }

        .input-group {
            display: flex;
            gap: 10px;
        }

        input[type="text"] {
            flex: 1;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 12px;
            border-radius: 8px;
            color: #fff;
            outline: none;
        }

        input[type="text"]:focus {
            border-color: var(--accent-color);
        }

        .mic-btn {
            background: var(--accent-pink);
            border-color: var(--accent-pink);
        }

        .mic-btn:hover {
            background: #ff3399;
            box-shadow: 0 0 15px var(--accent-pink);
        }
    </style>
</head>
<body>

    <h1>🤖 LOGAN AI DASHBOARD</h1>

    <div class="container">
        <!-- TARJETA DE LUCES -->
        <div class="card">
            <h2>💡 Control de Luces RGB</h2>
            <div id="lightView" class="light-preview" style="background-color: rgb(255,255,255);"></div>
            <p>Estado: <b id="lightState">CARGANDO...</b></p>
            
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                <label>Color libre:</label>
                <input type="color" id="colorPicker" value="#ffffff" onchange="cambiarColorPicker(this.value)">
            </div>

            <div class="preset-buttons">
                <button onclick="enviarComando('Pon luces estilo cyberpunk')">Cyberpunk</button>
                <button onclick="enviarComando('Pon luces color verde menta')">Menta</button>
                <button onclick="enviarComando('Pon luces de atardecer')">Atardecer</button>
                <button onclick="enviarComando('Pon modo matrix')">Matrix</button>
                <button onclick="enviarComando('Encender luz')">Encender</button>
                <button onclick="enviarComando('Apagar luz')">Apagar</button>
            </div>
        </div>

        <!-- TARJETA DE ESTADO GENERAL -->
        <div class="card">
            <h2>🚨 Estado del Sistema</h2>
            <p>🚪 Puerta: <span id="doorStatus" style="color: #00ff66;">Segura</span></p>
            <p>💻 Agente Laptop: <span style="color: var(--accent-color);">Conectado</span></p>
            <div style="margin-top: 20px;">
                <button style="width: 100%;" onclick="enviarComando('Pausa la música')">⏯️ Play/Pausa</button>
            </div>
        </div>

        <!-- TARJETA DE CHAT Y VOZ -->
        <div class="card chat-box">
            <h2>💬 Conversar con Logan</h2>
            <div id="chat-history">
                <p><i>🤖 Logan: Listo para tus órdenes, Álvaro.</i></p>
            </div>
            <div class="input-group">
                <input type="text" id="userInput" placeholder="Escribe o háblale a Logan..." onkeypress="if(event.key==='Enter') enviarTexto()">
                <button onclick="enviarTexto()">Enviar</button>
                <button class="mic-btn" onclick="iniciarReconocimientoVoz()">🎙️</button>
            </div>
        </div>
    </div>

    <script>
        function actualizarEstado() {
            fetch('/esp32/status')
                .then(r => r.json())
                .then(data => {
                    const view = document.getElementById('lightView');
                    const stateTxt = document.getElementById('lightState');
                    if(data.state === 'ON') {
                        view.style.backgroundColor = `rgb(${data.r}, ${data.g}, ${data.b})`;
                        stateTxt.innerText = `ENCENDIDO (${data.r}, ${data.g}, ${data.b})`;
                        stateTxt.style.color = '#00ff66';
                    } else {
                        view.style.backgroundColor = '#111';
                        stateTxt.innerText = 'APAGADO';
                        stateTxt.style.color = '#ff3366';
                    }
                });
        }

        function enviarTexto() {
            const input = document.getElementById('userInput');
            const txt = input.value.trim();
            if(!txt) return;
            enviarComando(txt);
            input.value = '';
        }

        function enviarComando(texto) {
            const history = document.getElementById('chat-history');
            history.innerHTML += `<p><b>Tú:</b> ${texto}</p>`;
            history.scrollTop = history.scrollHeight;

            fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: texto})
            })
            .then(r => r.json())
            .then(data => {
                history.innerHTML += `<p><b>🤖 Logan:</b> ${data.reply}</p>`;
                history.scrollTop = history.scrollHeight;
                actualizarEstado();
            });
        }

        function cambiarColorPicker(hex) {
            const r = parseInt(hex.substr(1,2), 16);
            const g = parseInt(hex.substr(3,2), 16);
            const b = parseInt(hex.substr(5,2), 16);
            enviarComando(`Pon la luz en color R:${r} G:${g} B:${b}`);
        }

        function iniciarReconocimientoVoz() {
            if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
                alert('Tu navegador no soporta reconocimiento de voz.');
                return;
            }
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            const recognition = new SpeechRecognition();
            recognition.lang = 'es-ES';
            recognition.start();

            recognition.onresult = function(event) {
                const mensaje = event.results[0][0].transcript;
                enviarComando(mensaje);
            };
        }

        setInterval(actualizarEstado, 2000);
        actualizarEstado();
    </script>
</body>
</html>
"""

# ==============================================================================
# RUTAS DEL SERVIDOR
# ==============================================================================

@app.route('/')
def dashboard():
    """Ruta principal con la nueva interfaz de usuario"""
    return render_template_string(HTML_DASHBOARD)

@app.route('/chat', methods=['POST'])
def chat():
    global estado_luz, HISTORIAL, cola_ordenes_pc
    
    api_key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({'reply': 'Falta configurar GROQ_API_KEY en Render.', 'estado_luz': estado_luz}), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No logré escucharte bien.', 'estado_luz': estado_luz}), 400

    try:
        reply_text = consultar_groq(api_key, user_message)

        # 1. PARSEO DE LUZ MEZCLA RGB DE 16.7 MILLONES DE COLORES
        match_rgb = re.search(r"\[\[LUZ:RGB:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]\]", reply_text, re.IGNORECASE)
        if match_rgb:
            estado_luz["r"] = max(0, min(255, int(match_rgb.group(1))))
            estado_luz["g"] = max(0, min(255, int(match_rgb.group(2))))
            estado_luz["b"] = max(0, min(255, int(match_rgb.group(3))))
            estado_luz["state"] = "ON"
            reply_text = re.sub(r"\[\[LUZ:RGB:.*?\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        # PARSEO LUZ COMPATIBILIDAD ANTERIOR
        if "[[LUZ:ON]]" in reply_text.upper():
            estado_luz["state"] = "ON"
            reply_text = re.sub(r"\[\[LUZ:ON\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        elif "[[LUZ:OFF]]" in reply_text.upper():
            estado_luz["state"] = "OFF"
            reply_text = re.sub(r"\[\[LUZ:OFF\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        match_color = re.search(r"\[\[LUZ:COLOR:\s*(.*?)\s*\]\]", reply_text, re.IGNORECASE)
        if match_color:
            color_nombre = match_color.group(1).upper().strip()
            if color_nombre in MAPA_COLORES:
                r, g, b = MAPA_COLORES[color_nombre]
                estado_luz["r"] = r
                estado_luz["g"] = g
                estado_luz["b"] = b
                estado_luz["state"] = "ON"
            reply_text = re.sub(r"\[\[LUZ:COLOR:.*?\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        match_brillo = re.search(r"\[\[LUZ:BRILLO:\s*(\d+)\s*\]\]", reply_text, re.IGNORECASE)
        if match_brillo:
            porcentaje = int(match_brillo.group(1))
            porcentaje = max(10, min(100, porcentaje))
            estado_luz["brightness"] = int((porcentaje / 100.0) * 255)
            estado_luz["state"] = "ON"
            reply_text = re.sub(r"\[\[LUZ:BRILLO:.*?\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        # 2. PARSEO DE LAPTOP
        comando_tipo = None
        comando_valor = None
        patron_etiquetas = r"\[\[(ALARMA|REPRODUCIR|VOLUMEN|SISTEMA|EJECUTAR):\s*(.*?)\s*\]\]"
        coincidencia = re.search(patron_etiquetas, reply_text, re.IGNORECASE)

        if coincidencia:
            comando_tipo = coincidencia.group(1).upper()
            comando_valor = coincidencia.group(2).strip()
            reply_text = re.sub(patron_etiquetas, "", reply_text, flags=re.IGNORECASE).strip()

        # 3. APRENDIZAJE AUTOMÁTICO
        patron_recordar = r"\[\[RECORDAR:\s*(.*?)\s*=\s*(.*?)\s*\]\]"
        coincidencias_memoria = re.findall(patron_recordar, reply_text, re.IGNORECASE)
        if coincidencias_memoria:
            perfil_actual = cargar_perfil()
            for clave, valor in coincidencias_memoria:
                clave_clean = clave.strip().lower()
                valor_clean = valor.strip()
                if clave_clean in ["nombre_usuario", "trato", "creador"]:
                    perfil_actual[clave_clean] = valor_clean
                else:
                    perfil_actual["gustos_y_datos"][clave_clean] = valor_clean
            guardar_perfil(perfil_actual)
            reply_text = re.sub(r"\[\[RECORDAR:.*?\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        # 4. AÑADIR A LA COLA DE LA LAPTOP
        if comando_tipo or reply_text:
            cola_ordenes_pc.append({
                "tipo": comando_tipo,
                "valor": comando_valor,
                "hablar": reply_text
            })

        # 5. HISTORIAL DE CONVERSACIÓN
        HISTORIAL.append({"role": "user", "content": user_message})
        HISTORIAL.append({"role": "assistant", "content": reply_text})
        if len(HISTORIAL) > MAX_HISTORIAL * 2:
            HISTORIAL = HISTORIAL[-MAX_HISTORIAL * 2:]

        return jsonify({'reply': reply_text, 'estado_luz': estado_luz})

    except Exception as e:
        print("❌ ERROR GENERAL:", str(e))
        traceback.print_exc()
        return jsonify({'reply': f"Detalle técnico: {str(e)[:150]}", 'estado_luz': estado_luz}), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify(estado_luz)

@app.route('/pc/comando', methods=['GET'])
def pc_comando():
    global cola_ordenes_pc
    if cola_ordenes_pc:
        data = cola_ordenes_pc.pop(0)
    else:
        data = {}
    return jsonify(data)

@app.route('/alerta_puerta', methods=['POST', 'GET'])
def alerta_puerta():
    global cola_ordenes_pc
    cola_ordenes_pc.append({
        "tipo": None,
        "valor": None,
        "hablar": "Álvaro, alguien se está acercando a la puerta."
    })
    print("🚨 ALERTA: Presencia detectada en la puerta.")
    return jsonify({"status": "ok", "message": "Alerta registrada"})
    
@app.route('/perfil', methods=['GET'])
def ver_perfil():
    return jsonify(cargar_perfil())

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Estado Luz: <b>{json.dumps(estado_luz)}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
