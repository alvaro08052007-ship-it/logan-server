from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import traceback

app = Flask(__name__)
CORS(app)

# Estado global del relé
estado_rele = "OFF"

# Personalidad e instrucciones de Logan
PROMPT_LOGAN = """
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa. Puedes conversar sobre cualquier tema, responder preguntas generales, dar consejos y razonar como un compañero de proyectos.

INSTRUCCIÓN DE IDENTIDAD (STRICT):
- Tu nombre es Logan. Jamás menciones que eres Llama, Groq, Meta, OpenAI, Gemini ni cualquier otro motor o modelo. Tu única identidad es Logan.

REGLAS DE CONTROL DOMÓTICO (OBLIGATORIAS):
- Si el usuario te pide encender la luz o el foco (ej. 'enciende la luz', 'prende el foco'):
  Debes incluir EXACTAMENTE el texto [[LUZ:ON]] en alguna parte de tu respuesta.
- Si el usuario te pide apagar la luz (ej. 'apaga la luz', 'deja todo a oscuras'):
  Debes incluir EXACTAMENTE el texto [[LUZ:OFF]] en alguna parte de tu respuesta.
"""

# Modelos ultrapotentes y gratuitos de Groq
MODELOS_GROQ = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192"
]

def consultar_groq(api_key, user_message):
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    ultimo_error = ""

    for modelo in MODELOS_GROQ:
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": PROMPT_LOGAN},
                {"role": "user", "content": user_message}
            ],
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
    global estado_rele
    
    # Busca la clave en GROQ_API_KEY o en GEMINI_API_KEY
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
    return f"<h1>Logan Server Activo (Groq Engine)</h1><p>Estado del Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
