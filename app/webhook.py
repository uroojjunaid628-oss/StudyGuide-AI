import os

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.chatbot import get_chatbot_response
from app.database import (
    create_student,
    get_student,
    update_webhook_status,
    update_student
)

# Load environment variables from .env
load_dotenv()

router = APIRouter()

# Meta WhatsApp configuration
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")

# Google Sheets Apps Script webhook URL
GOOGLE_SHEETS_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")

# Meta webhook verification

@router.get("/webhook")
async def verify_webhook(request: Request):

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Meta sends these values when verifying the webhook
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    return PlainTextResponse(
        "Verification failed",
        status_code=403
    )


# Receive incoming WhatsApp webhook events

@router.post("/webhook")
async def receive_webhook(request: Request):

    data = await request.json()

    print("Meta webhook received:")
    print(data)

    try:
        # Get the WhatsApp message from Meta's webhook payload
        value = data["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]

        # Get sender's WhatsApp number and message text
        sender = message["from"]
        message_text = message["text"]["body"]

        print("Sender:", sender)
        print("Message:", message_text)

        # Get the student's existing profile
        student = get_student(sender)

        # Create a new student record if this is a new WhatsApp user
        if student is None:
            create_student(sender)
            student = get_student(sender)

        # Send the student's message to StudyGuide AI
        response = get_chatbot_response(
            message_text,
            student
        )

        # Convert the structured AI response into a dictionary
        updated_profile = response.updated_profile.model_dump()
        
        print("AI response:")
        print(response)
        print("Response Message:", response.response_message)
        print("Profile complete:", response.profile_complete)

        # Save the updated student profile to PostgreSQL
        update_student(
            sender,
            updated_profile
        )

        # When all 10 consultation fields are complete,
        # send the student's information to Google Sheets
        if response.profile_complete and student["webhook_status"] != "sent":
            
            send_to_google_sheets(
                student["id"],
                sender,
                updated_profile
            )

            update_webhook_status(
                sender,
                "sent"
            )

        # Send StudyGuide AI's response back to WhatsApp
        message_to_send = response.response_message

        if not message_to_send:
            message_to_send =(
            "Hi! 😊 I already have your study details. "
            "What would you like to know about studying abroad?"
            )
        send_whatsapp_message(
            sender,
            message_to_send
        )    

    except (KeyError, IndexError, TypeError):
        # Meta also sends status events such as delivered/read.
        # These events do not contain a "messages" field.
        print(
            "Webhook event does not contain a WhatsApp message."
        )

    return {"status": "received"}



# Send a text message back to WhatsApp

def send_whatsapp_message(recipient, message):

    if not PHONE_NUMBER_ID or not ACCESS_TOKEN:
        print("Meta WhatsApp credentials (PHONE_NUMBER_ID or ACCESS_TOKEN) not set.")
        return

    url = (
        f"https://graph.facebook.com/v23.0/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )
        print("WhatsApp API response:")
        print(response.status_code)
        print(response.text)
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")



# Send completed student profile to Google Sheets

def send_to_google_sheets(
    student_id,
    whatsapp_number,
    profile
):

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        print("GOOGLE_SHEETS_WEBHOOK_URL is not configured.")
        return

    # Prepare the data using the same fields
    # as the Google Sheet columns
    payload = {
        "id": student_id,
        "whatsapp_number": whatsapp_number,
        "name": profile.get("name"),
        "current_country": profile.get("current_country"),
        "desired_country": profile.get("desired_country"),
        "study_level": profile.get("study_level"),
        "program": profile.get("program"),
        "previous_qualification": profile.get(
            "previous_qualification"
        ),
        "academic_score": profile.get("academic_score"),
        "english_test": profile.get("english_test"),
        "preferred_intake": profile.get(
            "preferred_intake"
        ),
        "budget": profile.get("budget")
    }

    # Send the completed profile to the
    # Google Apps Script web app
    try:
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        print("Google Sheets response:")
        print(response.status_code)
        print(response.text)
    except Exception as e:
        print(f"Error sending data to Google Sheets: {e}")