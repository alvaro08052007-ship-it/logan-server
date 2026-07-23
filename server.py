from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import traceback

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

# Probamos endpoints oficiales
OPCIONES_API = [
    ("https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent", "v1-gemini-1.5-flash"),
    ("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent", "v1beta-gemini-2.0-flash")
]

def solicitar_respuesta(api_key, prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key
    }

    ultimo_error = ""

    for url_base, nombre in OPCIONES_API:
        url = f"{url_base}?key={api_key}"
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
            err_msg = e.read().decode('utf-8')
            ultimo_error = f"{nombre} ({e.code}): {err_msg}"
            continue
        except Exception as e:
            ultimo_error = f"{nombre}: {str(e)}"
            continue

    raise Exception(ultimo_error)

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({
            'reply': 'Falta configurar la GEMINI_API_KEY en Render.', 
            'estado_rele': estado_rele
        }), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({
            'reply': 'No escuché ningún mensaje.', 
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
            'reply': f"Detalle de red: {str(e)[:150]}", 
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
