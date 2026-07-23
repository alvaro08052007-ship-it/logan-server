from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import google.generativeai as genai
import os

app = Flask(__name__)
CORS(app)

# Configuración de API Key de Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Variable global para recordar el estado de la luz
estado_rele = "OFF"

# Configuración del Modelo y Personalidad de Logan
system_instruction = """
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, con un toque sutil de ingenio y gran capacidad conversacional.
Tus respuestas deben ser naturales, claras y concisas, conversando de tú a tú como un colaborador brillante.

INSTRUCCIONES CLAVE PARA CONTROL IOT:
- Si el usuario te pide encender la luz o el foco (ejemplo: 'enciende la luz', 'prende el foco', 'que se haga la luz'):
  Debes incluir EXACTAMENTE el comando [[LUZ:ON]] en alguna parte de tu respuesta.
- Si el usuario te pide apagar la luz (ejemplo: 'apaga la luz', 'deja a oscuras el cuarto'):
  Debes incluir EXACTAMENTE el comando [[LUZ:OFF]] en alguna parte de tu respuesta.

Ejemplo de respuesta:
"¡Entendido! Encendiendo las luces de la habitación. [[LUZ:ON]] ¿Hay algo más en lo que te pueda colaborar hoy?"
"Con gusto, apago las luces. [[LUZ:OFF]] Quedo atento si necesitas algo más."

Mantén la conversación fluida, amable y cercana.
"""

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=system_instruction
)

# Guardar historial simple en memoria
chat_session = model.start_chat(history=[])

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele
    data = request.get_json()
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No escuché ningún mensaje.', 'estado_rele': estado_rele}), 400

    try:
        # Generar respuesta usando la sesión conversacional
        response = chat_session.send_message(user_message)
        reply_text = response.text

        # Detectar comandos IoT en la respuesta
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
        print("Error:", e)
        return jsonify({'reply': 'Tuve un pequeño contratiempo al procesar la idea. ¿Me lo repites?', 'estado_rele': estado_rele}), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Estado del Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
