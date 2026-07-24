from flask import Flask, request, jsonify
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
# ESTADOS GLOBALES Y MEMORIA
# ==============================================================================
estado_rele = "OFF"
orden_pc_pendiente = None  

PERFIL_FILE = "perfil_usuario.json"
HISTORIAL = []       
MAX_HISTORIAL = 10   

def cargar_perfil():
    if os.path.exists(PERFIL_FILE):
        try:
            with open(PERFIL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("⚠️ No se pudo cargar el perfil:", e)
    return {
        "nombre_usuario": "Amigo",
        "trato": "informal, cercano y natural",
        "gustos_y_datos": {}
    }

def guardar_perfil(perfil):
    try:
        with open(PERFIL_FILE, "w", encoding="utf-8") as f:
            json.dump(perfil, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ Error guardando el perfil:", e)

perfil_usuario = cargar_perfil()

def construir_prompt_sistema():
    perfil_str = json.dumps(perfil_usuario, ensure_ascii=False, indent=2)
    
    return f"""
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa (máximo 2 a 3 oraciones para ser ágil al hablar).

INSTRUCCIÓN DE IDENTIDAD (STRICT):
- Tu nombre es Logan. Jamás menciones que eres Llama, Groq, Meta, OpenAI, Gemini ni ningún otro motor. Tu única identidad es Logan.

PERFIL Y MEMORIA DEL USUARIO:
{perfil_str}
- IMPORTANTE: Adapta tu tono, trato y vocabulario según lo aprendido en el perfil anterior.

REGLAS DE CONTROL DOMÓTICO (ESP32):
- Encender luz: [[LUZ:ON]]
- Apagar luz: [[LUZ:OFF]]

REGLAS DE CONTROL DE LAPTOP (OBLIGATORIAS):
- Reproducir música en SPOTIFY: [[REPRODUCIR: nombre_cancion_o_artista]]
  (ej. "pon Bohemian Rhapsody", "reproduce Bad Bunny" -> [[REPRODUCIR: Queen Bohemian Rhapsody]])
- Pausar / Reanudar música: [[VOLUMEN: PAUSA]]
  (ej. "pausa la música", "pon pausa", "sigue la música", "despausa" -> [[VOLUMEN: PAUSA]])
- Abrir aplicaciones: [[EJECUTAR: nombre_app]]
- Control de Volumen:
  - Subir volumen: [[VOLUMEN: SUBIR]]
  - Bajar volumen: [[VOLUMEN: BAJAR]]
  - Silenciar: [[VOLUMEN: MUTE]]
- Control de Sistema:
  - Bloquear pantalla: [[SISTEMA: BLOQUEAR]]
  - Tomar captura de pantalla: [[SISTEMA: CAPTURA]]
  - Apagar laptop: [[SISTEMA: APAGAR]]

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
            "temperature": 0.7
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
# RUTAS DEL SERVIDOR
# ==============================================================================

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele, perfil_usuario, HISTORIAL, orden_pc_pendiente
    
    api_key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({'reply': 'Falta configurar GROQ_API_KEY en Render.', 'estado_rele': estado_rele}), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No logré escucharte bien.', 'estado_rele': estado_rele}), 400

    try:
        reply_text = consultar_groq(api_key, user_message)

        # 1. CONTROL DOMÓTICO (ESP32)
        if "[[LUZ:ON]]" in reply_text:
            estado_rele = "ON"
            reply_text = reply_text.replace("[[LUZ:ON]]", "").strip()
        elif "[[LUZ:OFF]]" in reply_text:
            estado_rele = "OFF"
            reply_text = reply_text.replace("[[LUZ:OFF]]", "").strip()

        comando_tipo = None
        comando_valor = None

        # 2. CONTROL DE LAPTOP
        if "[[REPRODUCIR:" in reply_text:
            match = re.search(r"\[\[REPRODUCIR:\s*(.*?)\s*\]\]", reply_text)
            if match:
                comando_tipo = "REPRODUCIR"
                comando_valor = match.group(1)
                reply_text = re.sub(r"\[\[REPRODUCIR:.*?\]\]", "", reply_text).strip()

        elif "[[VOLUMEN:" in reply_text:
            match = re.search(r"\[\[VOLUMEN:\s*(.*?)\s*\]\]", reply_text)
            if match:
                comando_tipo = "VOLUMEN"
                comando_valor = match.group(1).upper()
                reply_text = re.sub(r"\[\[VOLUMEN:.*?\]\]", "", reply_text).strip()

        elif "[[SISTEMA:" in reply_text:
            match = re.search(r"\[\[SISTEMA:\s*(.*?)\s*\]\]", reply_text)
            if match:
                comando_tipo = "SISTEMA"
                comando_valor = match.group(1).upper()
                reply_text = re.sub(r"\[\[SISTEMA:.*?\]\]", "", reply_text).strip()

        elif "[[EJECUTAR:" in reply_text:
            match = re.search(r"\[\[EJECUTAR:\s*(.*?)\s*\]\]", reply_text)
            if match:
                comando_tipo = "EJECUTAR"
                comando_valor = match.group(1).lower().strip()
                reply_text = re.sub(r"\[\[EJECUTAR:.*?\]\]", "", reply_text).strip()

        # 3. APRENDIZAJE AUTOMÁTICO
        patron_recordar = r"\[\[RECORDAR:\s*(.*?)\s*=\s*(.*?)\s*\]\]"
        coincidencias_memoria = re.findall(patron_recordar, reply_text)
        for clave, valor in coincidencias_memoria:
            if clave in ["nombre_usuario", "trato"]:
                perfil_usuario[clave] = valor
            else:
                perfil_usuario["gustos_y_datos"][clave] = valor
            guardar_perfil(perfil_usuario)

        reply_text = re.sub(r"\[\[RECORDAR:.*?\]\]", "", reply_text).strip()

        # 4. REGISTRAR ORDEN Y VOZ
        orden_pc_pendiente = {
            "tipo": comando_tipo,
            "valor": comando_valor,
            "hablar": reply_text
        }

        # 5. MEMORIA CONVERSACIONAL
        HISTORIAL.append({"role": "user", "content": user_message})
        HISTORIAL.append({"role": "assistant", "content": reply_text})
        if len(HISTORIAL) > MAX_HISTORIAL * 2:
            HISTORIAL = HISTORIAL[-MAX_HISTORIAL * 2:]

        return jsonify({'reply': reply_text, 'estado_rele': estado_rele})

    except Exception as e:
        print("❌ ERROR GENERAL:", str(e))
        traceback.print_exc()
        return jsonify({'reply': f"Detalle técnico: {str(e)[:150]}", 'estado_rele': estado_rele}), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/pc/comando', methods=['GET'])
def pc_comando():
    global orden_pc_pendiente
    data = orden_pc_pendiente or {}
    orden_pc_pendiente = None  
    return jsonify(data)

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
