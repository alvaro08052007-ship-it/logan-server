from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.request
import traceback

app = Flask(__name__)
CORS(app)

# Variable global para el relé
estado_rele = "OFF"

# Personalidad e instrucciones de Logan
PROMPT_LOGAN = """
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa. Puedes conversar sobre cualquier tema, responder preguntas generales, dar consejos y razonar como un compañero de proyectos.

REGLAS DE CONTROL DOMÓTICO (OBLIGATORIAS):
- Si el usuario te pide encender la luz o el foco (ej. 'enciende la luz', 'prende el foco'):
  Debes incluir EXACTAMENTE el texto [[LUZ:ON]] en alguna parte de tu respuesta.
- Si el usuario te pide apagar la luz (ej. 'apaga la luz', 'deja todo a oscuras'):
  Debes incluir EXACTAMENTE el texto [[LUZ:OFF]] en alguna parte de tu respuesta.
"""

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    
    # Obtener API Key de Render
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({'reply': 'Falta configurar la GEMINI_API_KEY en Render.', 'estado_rele': estado_rele}), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No escuché ningún mensaje.', 'estado_rele': estado_rele}), 400

    try:
        # Petición HTTP directa a Google Gemini (Compatible con claves AQ... y AIza...)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        prompt_final = f"{PROMPT_LOGAN}\n\nUsuario dice: {user_message}\nLogan responde:"
        
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt_final}]
                }
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        # Realizar la consulta a la nube
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        reply_text = res_data['candidates'][0]['content']['parts'][0]['text']

        # Detectar comandos de control domótico
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
        print("❌ ERROR EN EL SERVIDOR:", str(e))
        traceback.print_exc()
        return jsonify({
            'reply': f"Tuve un detalle técnico con Gemini: {str(e)}", 
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
