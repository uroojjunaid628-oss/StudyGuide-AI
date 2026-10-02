# StudyGuide AI

StudyGuide AI is a backend service that runs study-abroad intake consultations over WhatsApp. A student chats with it the way they would with a human counsellor, and the service turns that conversation into a structured, persistent profile: where the student is from, where they want to study, what level, what program, their academic standing, language test status, intake, and budget.

The interesting part of the project is not the chatbot. It is the boundary between the model and the rest of the system. The LLM is used for one narrow job (reading free-form text and producing a structured update), while everything that needs to be reliable, such as identity, state, persistence, and downstream sync, is handled by ordinary application code and a relational database.

Stack: Python, FastAPI, PostgreSQL, Groq via LangChain, Pydantic, Meta WhatsApp Cloud API, Google Apps Script.

---

## Problem and approach

Study-abroad consultancies typically collect the same ten or so facts from every lead before a counsellor can say anything useful. Web forms get abandoned, and in many markets students are far more comfortable in WhatsApp than on a website. A scripted bot that asks fixed questions in fixed order handles this poorly: students answer several things at once, skip questions, and change their minds.

This service takes a different approach. Each incoming message is interpreted against the profile that already exists for that student. The model decides which fields the message affects, whether anything was corrected, and what is still missing, then asks the next relevant question. A message like the following fills in four fields at once and leaves the bot to ask only about what remains:

> I'm from Pakistan and want to do a Master's in Computer Science in Italy. My CGPA is 3.45 and I'm looking for Fall 2026.

A later message such as "Actually I want Italy instead of Belgium" overwrites the stored value. It does not create a second record or leave the old value in place.

---

## How a message is processed

Every WhatsApp message goes through the same sequence:

1. Meta delivers the message to `POST /webhook`. Events that do not contain a user message (delivery receipts, read receipts) are acknowledged and discarded.
2. The sender's WhatsApp number is used to look up the student. If no record exists, one is created.
3. The current profile is loaded from PostgreSQL.
4. The existing profile and the new message are passed to the model.
5. The model returns a structured object, not free text. The object has three parts: the updated profile, the reply to send, and a flag saying whether the profile is complete.
6. The updated profile is written back to PostgreSQL.
7. If the profile is complete, it is posted to the Google Sheets webhook and the sync outcome is recorded in `webhook_status`.
8. The reply is sent to the student through the Meta Graph API.

The same pipeline sits behind the `POST /chat` endpoint, which accepts a WhatsApp number and a message directly. That makes it possible to exercise the conversation logic with curl or a test client without involving Meta at all.

---

## Design decisions

**State lives in the database, not in the model.** The model has no memory between calls. On every turn it is handed the current profile as input, so the application always knows exactly what has been collected, and a restart or redeploy loses nothing. It also means conversation behaviour can be reasoned about from the stored profile alone.

**The model returns a typed schema.** The response is validated by Pydantic before the application acts on it. There is no regex or string parsing of model output anywhere in the request path. If the output does not match the schema, it fails validation at the boundary rather than corrupting a profile later.

**One profile per student, updated in place.** The WhatsApp number is the external identifier and the internal numeric `id` is the stable key used everywhere else. Corrections are updates to the same row.

**PostgreSQL is the source of truth; Google Sheets is a projection.** The spreadsheet exists so non-technical staff can see leads. It is never read back by the application. If the sheet is wrong or the sync fails, the database is still correct and the record can be re-sent.

**Sheet writes are upserts keyed on student `id`.** Re-sending the same student, for example after the student revises an answer, updates their existing row instead of appending a duplicate.

**Sync is separated from conversation.** A failure in the Sheets webhook should not prevent the student from receiving a reply. Sync state is tracked per record in `webhook_status` so failed syncs are identifiable.

---

## Profile schema

The consultation profile has ten fields collected from the student, plus the identifiers and timestamps the application maintains itself.

| Field | Meaning |
| --- | --- |
| `name` | Student's name |
| `current_country` | Country the student currently lives in |
| `desired_country` | Intended study destination |
| `study_level` | Bachelor's, Master's, PhD, and so on |
| `program` | Intended field of study |
| `previous_qualification` | Most recent completed qualification |
| `academic_score` | GPA, percentage, or equivalent, stored as the student states it |
| `english_test` | IELTS, TOEFL, none, and so on |
| `preferred_intake` | Intended start term, for example "Fall 2026" |
| `budget` | Available budget, stored as the student states it |

Values such as `academic_score` and `budget` are deliberately kept as text. Students express them in incompatible ways ("3.45", "78%", "around 30000 dollars"), and normalising them is a separate concern from capturing them.

### Database

Everything is stored in a single `students` table with these columns: `id`, `whatsapp_number`, the ten profile fields above, `webhook_status`, `created_at`, and `updated_at`.

`whatsapp_number` identifies the conversation. `id` is the internal key and the one exposed to integrations. `webhook_status` records the state of the Google Sheets sync for that student.

---

## Code layout

| File | Responsibility |
| --- | --- |
| `app/main.py` | Creates the FastAPI application and exposes the health check and `/chat` endpoint |
| `app/webhook.py` | Meta webhook verification and event handling, the message-processing pipeline, outbound WhatsApp messages, Google Sheets sync |
| `app/chatbot.py` | Groq model configuration, Pydantic response schemas, and the system instructions that control extraction and conversational behaviour |
| `app/database.py` | PostgreSQL connection handling, table initialisation, and profile read/write operations |
| `test_meta.py` | Script for checking the Meta API connection |
| `data-deletion.html`, `privacy_policy.html`, `terms_of_service.html` | Static pages required by Meta for app review and publication |

---

## API reference

### `GET /`

Health check.

```json
{ "message": "StudyGuide AI is running" }
```

### `POST /chat`

Runs one conversational turn without going through WhatsApp.

| Parameter | Description |
| --- | --- |
| `whatsapp_number` | Identifier of the student |
| `user_message` | The message text |

The endpoint loads the student's profile, runs the model, persists the update, and returns the generated reply.

```bash
curl -X POST "http://localhost:8000/chat" \
  -d "whatsapp_number=923001234567" \
  -d "user_message=I want to study Computer Science in Italy"
```

### `GET /webhook`

Handles Meta's webhook verification handshake. The `hub.verify_token` supplied by Meta is compared against `META_VERIFY_TOKEN`, and the challenge is echoed back on success.

### `POST /webhook`

Receives WhatsApp events from Meta. Payloads without an actual user message are ignored.

---

## Configuration

All configuration comes from environment variables. Create a `.env` file in the project root:

```env
GROQ_API_KEY=

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_DB=studyguide_ai

META_VERIFY_TOKEN=
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_WABA_ID=

GOOGLE_SHEETS_WEBHOOK_URL=
```

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Authenticates requests to Groq |
| `POSTGRES_*` | Database connection settings |
| `META_VERIFY_TOKEN` | A string you choose; must match what you enter in the Meta developer console |
| `META_ACCESS_TOKEN` | Token used to send messages through the Graph API |
| `META_PHONE_NUMBER_ID` | The WhatsApp phone number that sends replies |
| `META_WABA_ID` | WhatsApp Business Account ID |
| `GOOGLE_SHEETS_WEBHOOK_URL` | Deployed Apps Script web app URL |

`.env` must never be committed. The Sheets webhook URL should be treated as a secret as well, since anyone holding it can write to the sheet.

---

## Running locally

**Prerequisites:** Python 3.12 or newer, a running PostgreSQL instance, a Groq API key, a Meta developer app with WhatsApp Cloud API access, a deployed Google Apps Script web app, and ngrok.

Clone and install:

```powershell
git clone https://github.com/uroojjunaid628-oss/StudyGuide-AI.git
cd StudyGuide-AI

python -m venv venv
venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Create the database named in `POSTGRES_DB`, fill in `.env`, then initialise the schema:

```powershell
python app/database.py
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

At this point `GET /` and `POST /chat` work, and the conversation logic can be tested without WhatsApp.

### Connecting Meta

Meta needs a public HTTPS URL to deliver webhooks to. In a second terminal:

```powershell
ngrok http 8000
```

In the Meta developer console, open the WhatsApp product configuration, set the callback URL to the ngrok HTTPS address followed by `/webhook`, and enter the same value you put in `META_VERIFY_TOKEN` as the verify token. Then subscribe the app to the `messages` webhook field. Meta calls `GET /webhook` immediately when you save, so the API must already be running.

The free ngrok URL changes each time the tunnel restarts, which means the callback URL has to be updated in the console each session. This is one of the reasons a hosted deployment is on the roadmap.

### Connecting Google Sheets

The sheet is written to by a Google Apps Script deployed as a web app. The script accepts a JSON `POST`, looks up the row whose `id` column matches the incoming `id`, updates that row if found, and appends a new row if not. Deploy it, copy the web app URL into `GOOGLE_SHEETS_WEBHOOK_URL`, and the backend will post to it whenever a profile is marked complete.

The payload is the full profile:

```json
{
  "id": 4,
  "whatsapp_number": "923001234567",
  "name": "Alina",
  "current_country": "Pakistan",
  "desired_country": "Italy",
  "study_level": "Masters",
  "program": "Computer Science",
  "previous_qualification": "BS Computer Science",
  "academic_score": "3.45",
  "english_test": "IELTS",
  "preferred_intake": "Fall 2026",
  "budget": "around 30000 dollars"
}
```

---

## Security

Credentials are read from the environment and kept out of the source tree. The following must never be committed: API keys, Meta access tokens, database credentials, any URL containing a secret, `.env`, and virtual environments. The repository should only ever contain a template of the variable names, not values.

Student data includes names, phone numbers, and financial and academic information, so the privacy policy, terms of service, and data-deletion pages included in the repository should be kept accurate. Meta requires them for app review, and they describe commitments the deployment needs to honour.

---

## Current state and limitations

The system works end to end: WhatsApp in, profile extraction and correction, persistence, follow-up questions, reply delivery, and a duplicate-safe sync of completed profiles to Google Sheets.

It is a development-stage implementation, and it is worth being clear about what that means:

- It runs locally and depends on an ngrok tunnel.
- Only the extracted profile is persisted. Raw conversation history is not stored, so the model sees the current profile and the latest message, not the full transcript.
- A failed Google Sheets sync is recorded but is not retried automatically.
- There is no monitoring, structured logging, or rate limiting.
- There is no administrative interface for browsing or editing student records.
- The assistant collects information. It does not yet recommend universities or programs, and it does not look up current admission requirements.

---

## Production requirements

Moving this from a working prototype to a service people depend on would involve:

- Hosting the FastAPI app behind a stable HTTPS endpoint
- Managed PostgreSQL with backups
- Structured logging and application monitoring
- Retry and dead-letter handling for webhook and Sheets failures
- A proper secrets manager in place of `.env` files
- Rate limiting on public endpoints
- Authentication for any administrative interface
- A CI/CD pipeline for tested, repeatable deployments

---

## Roadmap

- [ ] Cloud deployment
- [ ] Managed PostgreSQL
- [ ] Persistent conversation history
- [ ] Administrative dashboard
- [ ] Webhook retry mechanism
- [ ] Observability and monitoring
- [ ] University and program recommendation workflow
- [ ] Retrieval of current information from authoritative sources
- [ ] Automated deployment pipeline

---

## Author

Urooj Junaid, Machine Learning and Backend Engineer

[GitHub](https://github.com/uroojjunaid628-oss) · [LinkedIn](https://linkedin.com/in/urooj-junaid)
