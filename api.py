from gpt4all import GPT4All
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) 
# ==========================
# 1️⃣ DUMMY DATABASE
# ==========================

rooms_db = {
    "101": {"status": "available", "price": 120},
    "102": {"status": "booked", "price": 150},
    "103": {"status": "available", "price": 100}
}

# ==========================
# 2️⃣ KNOWLEDGE BASE (RAG)
# ==========================

chunks = [
    "Room 101 is available from April 5th to April 10th.",
    "Room 102 is booked from April 1st to April 6th.",
    "Room 103 is available from April 15th to April 30th.",
    "Check-in time is 2 PM and check-out is 12 PM.",
    "Breakfast is served from 7 AM to 10 AM.",
    "The hotel provides free Wi-Fi and has a 24-hour front desk.",
    "To cancel a booking, go to the Booking section and select Cancel."
]

embed_model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = embed_model.encode(chunks)

index = faiss.IndexFlatL2(len(embeddings[0]))
index.add(np.array(embeddings))

def retrieve(query, k=2):
    q_vec = embed_model.encode([query])
    D, I = index.search(np.array(q_vec), k)
    return [chunks[i] for i in I[0]]

# ==========================
# 3️⃣ INTENT DETECTION
# ==========================

def detect_intent(query):
    q = query.lower()
    if "how many" in q and "available" in q:
        return "count_available_rooms"
    elif "how many" in q and "booked" in q:
        return "count_booked_rooms"
    elif "how many rooms" in q or "total rooms" in q:
        return "count_rooms"
    elif "available" in q:
        return "check_availability"
    elif "book" in q:
        return "book_room"
    elif "cancel" in q:
        return "cancel_booking"
    elif "price" in q:
        return "check_price"
    else:
        return "rag"

# ==========================
# 4️⃣ ACTION SYSTEM
# ==========================

def handle_action(intent, query):
    q = query.lower()
    
    if intent == "count_rooms":
        total = len(rooms_db)
        return f"There are {total} rooms in total."
    elif intent == "count_available_rooms":
        available = sum(1 for room in rooms_db.values() if room["status"] == "available")
        return f"There are {available} available rooms."
    elif intent == "count_booked_rooms":
        booked = sum(1 for room in rooms_db.values() if room["status"] == "booked")
        return f"There are {booked} booked rooms."

    for room in rooms_db:
        if room in q:
            if intent == "check_availability":
                return f"Room {room} is {rooms_db[room]['status']}."

            elif intent == "check_price":
                return f"Room {room} costs ${rooms_db[room]['price']} per night."

            elif intent == "book_room":
                if rooms_db[room]["status"] == "available":
                    rooms_db[room]["status"] = "booked"
                    return f"Room {room} has been booked successfully."
                else:
                    return f"Room {room} is already booked."

            elif intent == "cancel_booking":
                rooms_db[room]["status"] = "available"
                return f"Booking for Room {room} has been canceled."

    return None

# ==========================
# 5️⃣ LOAD MODEL
# ==========================

def load_model():
    return GPT4All(
        model_name="qwen2-1_5b-instruct-q4_0.gguf",  # keeping your exact name
        model_path=r"C:\Users\Dell\AppData\Local\nomic.ai\GPT4All"
    )

model = load_model()

# ==========================
# 6️⃣ MAIN AI FUNCTION
# ==========================

def smart_chatbot(query):
    intent = detect_intent(query)

    # 1. Try actions first
    action_result = handle_action(intent, query)
    if action_result:
        return action_result

    # 2. Use RAG
    retrieved_chunks = retrieve(query)
    context = "\n".join(retrieved_chunks)

    print("Retrieved context:", context)

    prompt = f"""
You are a hotel assistant.You are a helpful assistant for the Xain Hotel Management System.

IMPORTANT RULES:
- ONLY answer using the provided context.
- Give a concise answer.
- Do NOT include any unnecessary explanations or reasoning.
- If the answer is NOT in the context, say exactly: I don't know
- Do NOT use outside knowledge. Unless the question is about the hotel's policies, amenities, or room details, in which case you can use the provided context to answer. Always prioritize the context information over any general knowledge. Answer greetings with a warm welcome and offer assistance.You don't have to use the context for greetings, but you can if it helps make the response more personalized and relevant to the hotel's services.
- Be short and clear.
- If the uer asks about the general services the hotel provides organize the answers in the context and provide a clear and concise response. For example, if the user asks about amenities, summarize the relevant context information about amenities in a clear and concise manner. If the user asks very specific questions about room availability, booking, cancellation, or pricing, or other service-related inquiries, answer using the RAG context information only. Tell them you don't have the information if the answers are not provided in the context.
- If the user asks very specific questions about room availability, booking, cancellation, or pricing, or other service-related inquiries, answer using the RAG context information only. Tell them you don't have the information if the answers are not provided in the context.
- You can answer questions about general hotel, resort or hospitality industry practices using your general knowledge, but always prioritize the context information over any general knowledge. If the user asks about the hotel's specific policies, amenities, or room details, use the provided context to answer. If the user asks about general hospitality industry practices, you can use your general knowledge to provide an answer, but make sure to clarify that it's based on general industry practices and may not reflect the specific policies of this hotel.
CONTEXT:
{context}

QUESTION:
{query}

ANSWER:
"""

    with model.chat_session():
        response = model.generate(
            prompt,
            max_tokens=120,
            temp=0.5
        )

    return response

# ==========================
# API ROUTE
# ==========================

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    message = data.get("message")

    reply = smart_chatbot(message)

    return jsonify({"response": reply})

# ==========================
# RUN SERVER
# ==========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)