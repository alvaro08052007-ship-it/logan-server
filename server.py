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
modelo_activo = None  # Guardará el modelo que funcione automáticamente

PROMPT_LOGAN = """
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante, con un toque sutil de ingenio y gran capacidad conversacional.
Hablas de forma fluida, cercana, natural y concisa. Puedes conversar sobre cualquier tema, responder preguntas generales, dar consejos y razonar como un compañero de proyectos.

REGLAS DE CONTROL DOMÓTICO (OBLIGATORIAS):
- Si el usuario te pide encender la luz o el foco (ej. 'enciende la luz', 'prende el foco'):
  Debes incluir EXACTAMENTE el texto [[LUZ:ON]] en alguna parte de tu respuesta.
- Si el usuario te pide apagar la luz (ej. 'apaga la luz', 'deja todo a oscuras'):
  Debes incluir EXACTAMENTE el texto [[LUZ:OFF]] en alguna parte de tu respuesta.
"""

# Lista de modelos oficiales de Gemini a probar en automático
MODELOS_CANDIDATOS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash"
]

def generar_respuesta_gemini(api_key, prompt):
    global modelo_activo
    
    # Si ya descubrimos cuál funciona en tu cuenta, usamos ese primero
    if modelo_activo:
        modelos_a_intentar = [modelo_activo] + [m for m in MODELOS_CANDIDATOS if m != modelo_activo]
    else:
        modelos_a_intentar = MODELOS_CANDIDATOS
    
    errores = []

    for modelo in modelos_a_intentar:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            }
            headers = {
                'Content-Type': 'application/json',
                'x-goog-api-key': api_key
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers
            )

            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                
            reply_text = res_data['candidates'][0]['content']['parts'][0]['text']
            
            # ¡Guardamos el modelo que funcionó!
            if modelo_activo != modelo:
                print(f"✅ ¡Modelo detectado y funcionando: {modelo}!")
                modelo_activo = modelo
                
            return reply_text

        except urllib.error.HTTPError as e:
            errores.append(f"{modelo} (HTTP {e.code})")
            continue
        except Exception as e:
            errores.append(f"{modelo} ({str(e)})")
            continue

    raise Exception(f"Ningún modelo respondió. Resultados: {', '.join(errores)}")

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({'reply': 'Falta configurar la GEMINI_API_KEY en Render.', 'estado_rele': estado_rele}), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No escuché ningún mensaje.', 'estado_rele': estado_rele}), 400

    try:
        prompt_final = f"{PROMPT_LOGAN}\n\nUsuario dice: {user_message}\nLogan responde:"
        
        reply_text = generar_respuesta_gemini(api_key, prompt_final)

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
            'reply': f"Detalle técnico: {str(e)}", 
            'estado_rele': estado_rele
        }), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Modelo activo: <b>{modelo_activo or 'Buscando...'}</b></p><p>Estado del Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
