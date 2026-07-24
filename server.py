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

# Estado global del relé
estado_rele = "OFF"

# ==============================================================================
# NUEVO: SISTEMA DE MEMORIA Y APRENDIZAJE DE PERSONALIDAD
# ==============================================================================
PERFIL_FILE = "perfil_usuario.json"
HISTORIAL = []       # Memoria a corto plazo (conversación activa)
MAX_HISTORIAL = 10   # Recuerda las últimas 10 interacciones

def cargar_perfil():
    """Lee lo que Logan ha aprendido sobre ti desde un archivo JSON."""
    if os.path.exists(PERFIL_FILE):
        try:
            with open(PERFIL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("⚠️ No se pudo cargar el perfil:", e)
    
    # Perfil inicial por defecto si el archivo no existe
    return {
        "nombre_usuario": "Amigo",
        "trato": "informal, cercano y natural",
        "gustos_y_datos": {}
    }

def guardar_perfil(perfil):
    """Guarda en disco los nuevos aprendizajes."""
    try:
        with open(PERFIL_FILE, "w", encoding="utf-8") as f:
            json.dump(perfil, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ Error guardando el perfil:", e)

# Carga el perfil aprendido al iniciar el servidor
perfil_usuario = cargar_perfil()

def construir_prompt_sistema():
    """Construye las instrucciones inyectando el perfil que Logan ha aprendido."""
    perfil_str = json.dumps(perfil_usuario, ensure_ascii=False, indent=2)
    
    return f"""
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa.

INSTRUCCIÓN DE IDENTIDAD (STRICT):
- Tu nombre es Logan. Jamás mencIONES que eres Llama, Groq, Meta, OpenAI, Gemini ni cualquier otro motor. Tu única identidad es Logan.

MEMORIA Y PERFIL DEL USUARIO (APRENDIDO HASTA AHORA):
{perfil_str}
- IMPORTANTE: Adapta tu tono, trato, vocabulario y respuestas según lo aprendido en el perfil anterior.

REGLAS DE CONTROL DOMÓTICO (OBLIGATORIAS):
- Si el usuario te pide encender la luz o el foco: debes incluir EXACTAMENTE [[LUZ:ON]] en tu respuesta.
- Si el usuario te pide apagar la luz: debes incluir EXACTAMENTE [[LUZ:OFF]] en tu respuesta.

REGLA DE APRENDIZAJE AUTOMÁTICO (NUEVA):
- Si el usuario te da información sobre su persona (nombre, gustos, profesión), o te indica cómo prefiere que le hables (ej. "llámame jefe", "sé más directo", "odio el lenguaje formal"):
  Debes incluir en alguna parte de tu respuesta la etiqueta secreta [[RECORDAR: clave = valor]].
  Ejemplos de etiquetas a generar:
  - Si dice "Me llamo Carlos" -> [[RECORDAR: nombre_usuario = Carlos]]
  - Si dice "Háblame como un camarada" -> [[RECORDAR: trato = camarada, informal]]
  - Si dice "Trabajo como programador" -> [[RECORDAR: profesion = Programador]]
"""

# Modelos disponibles en Groq
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # Preparamos el payload incluyendo el Prompt Dinámico + El Historial de Charla
    messages_payload = [{"role": "system", "content": construir_prompt_sistema()}]
    
    # Inyectamos los mensajes pasados para que tenga memoria conversacional
    for msg in HISTORIAL:
        messages_payload.append(msg)
        
    # Agregamos el mensaje actual
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

        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            ultimo_error = f"Error Groq ({e.code}): {err_body}"
            print(f"❌ Fallo con modelo {modelo}: {err_body}")
            continue
        except Exception as e:
            ultimo_error = str(e)
            continue

    raise Exception(ultimo_error)

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele, perfil_usuario, HISTORIAL
    
    api_key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({
            'reply': 'Falta configurar GROQ_API_KEY en las variables de Render.', 
            'estado_rele': estado_rele
        }), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({
            'reply': 'No logré escucharte bien. ¿Me lo repites?', 
            'estado_rele': estado_rele
        }), 400

    try:
        reply_text = consultar_groq(api_key, user_message)

        # 1. CONTROL DOMÓTICO
        if "[[LUZ:ON]]" in reply_text:
            estado_rele = "ON"
            reply_text = reply_text.replace("[[LUZ:ON]]", "").strip()
        elif "[[LUZ:OFF]]" in reply_text:
            estado_rele = "OFF"
            reply_text = reply_text.replace("[[LUZ:OFF]]", "").strip()

        # 2. APRENDIZAJE AUTOMÁTICO (Buscar etiquetas [[RECORDAR: clave = valor]])
        patron_recordar = r"\[\[RECORDAR:\s*(.*?)\s*=\s*(.*?)\s*\]\]"
        coincidencias = re.findall(patron_recordar, reply_text)

        for clave, valor in coincidencias:
            if clave in ["nombre_usuario", "trato"]:
                perfil_usuario[clave] = valor
            else:
                perfil_usuario["gustos_y_datos"][clave] = valor
            
            # Guarda los cambios permanentemente en el archivo JSON
            guardar_perfil(perfil_usuario)
            print(f"🧠 LOGAN APRENDIÓ ALGO NUEVO: {clave} = {valor}")

        # Limpiar las etiquetas de la respuesta final que lee el usuario
        reply_text = re.sub(r"\[\[RECORDAR:.*?\]\]", "", reply_text).strip()

        # 3. GUARDAR EN MEMORIA CONVERSACIONAL (HISTORIAL)
        HISTORIAL.append({"role": "user", "content": user_message})
        HISTORIAL.append({"role": "assistant", "content": reply_text})

        # Mantiene solo los últimos 10 intercambios de mensajes
        if len(HISTORIAL) > MAX_HISTORIAL * 2:
            HISTORIAL = HISTORIAL[-MAX_HISTORIAL * 2:]

        return jsonify({
            'reply': reply_text,
            'estado_rele': estado_rele
        })

    except Exception as e:
        print("❌ ERROR GENERAL:", str(e))
        traceback.print_exc()
        return jsonify({
            'reply': f"Detalle técnico: {str(e)[:150]}", 
            'estado_rele': estado_rele
        }), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Relé: <b>{estado_rele}</b></p><pre>Perfil: {json.dumps(perfil_usuario, indent=2, ensure_ascii=False)}</pre>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
