from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import traceback
import time

app = Flask(__name__)
CORS(app)

estado_rele = "OFF"

PROMPT_LOGAN = """
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa. Puedes conversar sobre cualquier tema, responder preguntas generales, dar consejos y razonar como un compañero de proyectos.

INSTRUCCIÓN DE IDENTIDAD (STRICT):
- Tu nombre es Logan. Jamás menciones que eres Gemini, Google o cualquier otro motor. Eres Logan.

REGLAS DE CONTROL DOMÓTICO (OBLIGATORIAS):
- Si el usuario te pide encender la luz o el foco (ej. 'enciende la luz', 'prende el foco'):
  Debes incluir EXACTAMENTE el texto [[LUZ:ON]] en alguna parte de tu respuesta.
- Si el usuario te pide apagar la luz (ej. 'apaga la luz', 'deja todo a oscuras'):
  Debes incluir EXACTAMENTE el texto [[LUZ:OFF]] en alguna parte de tu respuesta.
"""

MODELOS = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

def solicitar_respuesta(api_key, prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key
    }

    # Probar con reintentos silenciosos y pausas
    for modelo in MODELOS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        
        for intento in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers
                )
                with urllib.request.urlopen(req) as response:
                    res_data = json.loads(response.read().decode('utf-8'))
                
                return res_data['candidates'][0]['content']['parts'][0]['text']

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    # Si la nube pide una pausa por velocidad, esperamos silenciosamente antes de reintentar
                    time.sleep(1.5 * (intento + 1))
                    continue
                break
            except Exception:
                break

    # Si hay una caída total de conexión, Logan responde en personaje sin romper la ilusión
    return "Disculpa, tuve un leve pestañeo en mi red interna. ¿Podrías repetirme eso?"

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({
            'reply': 'Logan necesita su GEMINI_API_KEY en Render para funcionar.', 
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
        prompt_final = f"{PROMPT_LOGAN}\n\nUsuario dice: {user_message}\nLogan responde:"
        reply_text = solicitar_respuesta(api_key, prompt_final)

        # Control domótico
        if "[[LUZ:ON]]" in reply_text:
            estado_rele = "ON"
            reply_text = reply_text.replace("[[LUZ:ON]]", "").strip()
        elif "[[LUZ:OFF]]" in reply_text:
            estado_rele = "OFF"
            reply_text = reply_text.replace("[[LUZ:OFF]]", "").strip()

        return jsonify({
            'reply': reply_text,
            'estado_rele': estado_rele
        })

    except Exception as e:
        print("❌ ERROR EN SERVIDOR:", str(e))
        traceback.print_exc()
        return jsonify({
            'reply': "Tuve un pequeño problema técnico procesando la respuesta. Inténtalo de nuevo.", 
            'estado_rele': estado_rele
        }), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Estado del Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
