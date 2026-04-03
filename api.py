from gpt4all import GPT4All
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) 
# ==========================
# 1️⃣ ROOMS DATABASE (500 ROOMS)
# ==========================

import random
from datetime import datetime, timedelta
random.seed(42)
def random_booking_dates():
    start_date = datetime(2026, 4, 1) + timedelta(days=random.randint(0, 60))
    end_date = start_date + timedelta(days=random.randint(1, 10))
    return start_date.strftime("%b %d"), end_date.strftime("%b %d")

def random_bed():
    return random.choice([
        "king-size bed", "queen bed", "twin beds",
        "double bed", "deluxe suite with sofa bed"
    ])

def random_view():
    return random.choice([
        "sea view", "city view", "garden view",
        "pool view", "mountain view"
    ])

def random_amenities():
    return random.sample([
        "air conditioning", "minibar", "smart TV", "Wi-Fi",
        "balcony", "desk and chair", "ensuite bathroom",
        "sofa", "kitchenette", "free breakfast"
    ], k=4)

rooms_db = {}

for i in range(1, 501):
    room_number = str(100 + i)
    status = random.choice(["available", "booked"])
    price = random.randint(80, 500)
    bed = random_bed()
    view = random_view()
    amenities = random_amenities()

    if status == "booked":
        start, end = random_booking_dates()
    else:
        start, end = None, None

    rooms_db[room_number] = {
        "status": status,
        "price": price,
        "bed": bed,
        "view": view,
        "amenities": amenities,
        "booking_dates": {
            "from": start,
            "to": end
        }
    }
# ==========================
# 2️⃣ KNOWLEDGE BASE (RAG)
# ==========================

room_chunks = []
info_chunks = []

# -------- ROOM CHUNKS --------
for room_num, data in rooms_db.items():
    if data["status"] == "booked":
        start = data["booking_dates"]["from"]
        end = data["booking_dates"]["to"]
        chunk = f"Room {room_num}: Booked from {start} to {end}, ${data['price']}/night, {data['bed']}, {data['view']}, amenities: {', '.join(data['amenities'])}."
    else:
        chunk = f"Room {room_num}: Available, ${data['price']}/night, {data['bed']}, {data['view']}, amenities: {', '.join(data['amenities'])}."

    room_chunks.append(chunk)

# -------- GENERAL INFO --------
info_chunks = [
    "Check-in time: 2 PM, check-out time: 12 PM.",
    "Breakfast is served from 7 AM to 10 AM.",
    "Lunch is served from 12 PM to 3 PM.",
    "Dinner is served from 6 PM to 10 PM.",
    "Room service is available 24/7.",
    "The hotel has free Wi-Fi.",
    "There is a 24-hour front desk.",
    "The hotel includes a swimming pool, spa, and fitness center.",
    "Parking is free for guests.",
    "Airport shuttle service is available.",
    "The hotel has a restaurant, bar, and lounge.",
    "Laundry services are available.",
    "Concierge services help with bookings and tours."
]

# -------- COMBINED --------
chunks = room_chunks + info_chunks

# ---------------- Embeddings + FAISS ----------------
embed_model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = embed_model.encode(chunks)

index = faiss.IndexFlatL2(len(embeddings[0]))
index.add(np.array(embeddings))

# ---------------- Retrieval ----------------
def retrieve(query, k=5):
    q = query.lower()

    # If asking about services → ONLY use info_chunks
    if any(word in q for word in ["service", "amenities", "facility", "hotel offer", "what does the hotel have"]):
        selected_chunks = info_chunks
    else:
        selected_chunks = chunks  # normal behavior

    q_vec = embed_model.encode([query])
    selected_embeddings = embed_model.encode(selected_chunks)

    temp_index = faiss.IndexFlatL2(len(selected_embeddings[0]))
    temp_index.add(np.array(selected_embeddings))

    D, I = temp_index.search(np.array(q_vec), k)
    return [selected_chunks[i] for i in I[0]]

import re

def extract_room_number(query):
    match = re.search(r"\b\d{3}\b", query)
    return match.group(0) if match else None

def rebuild_index():
    global chunks, index

    chunks = []

    for room_num, data in rooms_db.items():
        if data["status"] == "booked":
            start = data["booking_dates"]["from"]
            end = data["booking_dates"]["to"]
            chunk = f"Room {room_num}: Booked from {start} to {end}, ${data['price']}/night, {data['bed']}, {data['view']}, amenities: {', '.join(data['amenities'])}."
        else:
            chunk = f"Room {room_num}: Available, ${data['price']}/night, {data['bed']}, {data['view']}, amenities: {', '.join(data['amenities'])}."

        chunks.append(chunk)

    chunks.extend(info_chunks)

    embeddings = embed_model.encode(chunks)
    index = faiss.IndexFlatL2(len(embeddings[0]))
    index.add(np.array(embeddings))

def detect_intent(query):
    q = query.lower()

    # ---------------- COUNT ----------------
    if "how many" in q:
        if "available" in q:
            return "count_available_rooms", {}
        elif "booked" in q:
            return "count_booked_rooms", {}
        elif "room" in q:
            return "count_rooms", {}

    # ---------------- FILTER ----------------
    if any(word in q for word in ["show", "list", "find", "give"]):
        params = {}

        if "available" in q:
            params["status"] = "available"
        elif "booked" in q:
            params["status"] = "booked"

        # price
        price_match = re.search(r"\$(\d+)", q)
        if price_match:
            params["max_price"] = int(price_match.group(1))

        # view
        for view in ["sea", "city", "garden", "pool", "mountain"]:
            if view in q:
                params["view"] = view

        # bed
        for bed in ["king", "queen", "twin", "double", "suite"]:
            if bed in q:
                params["bed"] = bed

        return "filter_rooms", params

    # ---------------- ROOM SPECIFIC ----------------
    room_number = extract_room_number(q)

    if room_number:
        if "book" in q:
            return "book_room", {"room": room_number}
        elif "cancel" in q:
            return "cancel_booking", {"room": room_number}
        elif "price" in q or "cost" in q:
            return "check_price", {"room": room_number}
        elif "available" in q:
            return "check_availability", {"room": room_number}
        else:
            return "room_info", {"room": room_number}

    return "rag", {}
def handle_action(intent, params, query=None):

    # ---------------- COUNT ----------------
    if intent == "count_rooms":
        return f"There are {len(rooms_db)} rooms in total."

    elif intent == "count_available_rooms":
        available = sum(1 for r in rooms_db.values() if r["status"] == "available")
        return f"There are {available} available rooms."

    elif intent == "count_booked_rooms":
        booked = sum(1 for r in rooms_db.values() if r["status"] == "booked")
        return f"There are {booked} booked rooms."

    # ---------------- FILTER ----------------
    elif intent == "filter_rooms":
        results = []

        for room_num, data in rooms_db.items():
            if "status" in params and data["status"] != params["status"]:
                continue

            if "max_price" in params and data["price"] > params["max_price"]:
                continue

            if "view" in params and params["view"] not in data["view"]:
                continue

            if "bed" in params and params["bed"] not in data["bed"]:
                continue

            results.append((room_num, data))

        if not results:
            return "No matching rooms found."

        results = results[:5]

        response = "Here are some matching rooms:\n"
        for room_num, data in results:
            response += f"Room {room_num}: {data['status']}, ${data['price']}, {data['bed']}, {data['view']}\n"

        return response

    # ---------------- ROOM INFO ----------------
    elif intent == "room_info":
        room = params.get("room")

        if room in rooms_db:
            d = rooms_db[room]
            return f"Room {room}: {d['status']}, ${d['price']}, {d['bed']}, {d['view']}"
        return "Room not found."

    # ---------------- AVAILABILITY ----------------
    elif intent == "check_availability":
        room = params.get("room")

        if room in rooms_db:
            return f"Room {room} is currently {rooms_db[room]['status']}."

    # ---------------- PRICE ----------------
    elif intent == "check_price":
        room = params.get("room")

        if room in rooms_db:
            return f"Room {room} costs ${rooms_db[room]['price']} per night."

    # ---------------- BOOK ----------------
    elif intent == "book_room":
        room = params.get("room")

        if room in rooms_db:
            if rooms_db[room]["status"] == "available":
                rooms_db[room]["status"] = "booked"
                return f"Room {room} has been booked successfully."
            else:
                return f"Room {room} is already booked."

    # ---------------- CANCEL ----------------
    elif intent == "cancel_booking":
        room = params.get("room")

        if room in rooms_db:
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
    q = query.lower().strip()

    if q in ["hi", "hello", "hey"]:
        return "Hello! Welcome to our hotel. How can I assist you today?"
    
    intent, params = detect_intent(query)

    # 1. Try actions first
    action_result = handle_action(intent, params, query)
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