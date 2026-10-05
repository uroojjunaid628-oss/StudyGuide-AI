from fastapi import FastAPI
from pydantic import BaseModel
from app.webhook import router as webhook_router

from app.chatbot import get_chatbot_response
from app.database import (
    create_student,
    get_student,
    update_student
)

app = FastAPI(title="StudyGuide AI")
app.include_router(webhook_router)


class ChatRequest(BaseModel):
    whatsapp_number: str
    user_message: str


@app.get("/")
def home():
    return {"message": "StudyGuide AI is running"}


@app.post("/chat")
def chat(request: ChatRequest):
    whatsapp_number = request.whatsapp_number
    user_message = request.user_message

    student = get_student(whatsapp_number)

    if student is None:
        create_student(whatsapp_number)
        student = get_student(whatsapp_number)

    response = get_chatbot_response(
        user_message,
        student
    )

    updated_profile = response.updated_profile.model_dump()

    update_student(
        whatsapp_number,
        updated_profile
    )

    return {
        "response": response.response_message,
        "profile": updated_profile,
        "profile_complete": response.profile_complete
    }