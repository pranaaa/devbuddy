from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

load_dotenv()
app = FastAPI(title="DevBuddy MCP Server")

# API credentials
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

class ReviewQuery(BaseModel):
    pr_id: str
    repo: str

@app.post("/code/review")
async def review_code(query: ReviewQuery):
    url = f"https://api.github.com/repos/{query.repo}/pulls/{query.pr_id}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="GitHub API error")
    pr_data = response.json()
    body = pr_data.get("body", "") or "No description"
    grok_url = "https://api.x.ai/v1/chat/completions"
    grok_headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
    grok_payload = {
        "model": "grok-4",
        "messages": [{"role": "user", "content": f"Review PR description for bugs and optimizations: {body[:500]}"}],
        "stream": false,
        "temperature": 0.7
    }
    grok_response = requests.post(grok_url, headers=grok_headers, json=grok_payload)
    if grok_response.status_code != 200:
        raise HTTPException(status_code=grok_response.status_code, detail=f"Grok API error: {grok_response.text}")
    feedback = grok_response.json().get("choices", [{}])[0].get("message", {}).get("content", "No feedback")
    return {"pr_id": query.pr_id, "repo": query.repo, "feedback": feedback}

class LearnQuery(BaseModel):
    skill: str

@app.post("/learn/path")
async def generate_path(query: LearnQuery):
    url = f"https://api.github.com/search/repositories?q={query.skill}+language:{query.skill}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="GitHub API error")
    repos = response.json().get("items", [])[:3]
    path = [repo['full_name'] for repo in repos]
    service = get_calendar_service()
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    start_time = now + timedelta(minutes=30)
    end_time = start_time + timedelta(hours=1)
    event = {
        'summary': f"Learn {query.skill}",
        'description': f"Upskilling path: {', '.join(path)}",
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'reminders': {'useDefault': True}
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return {"skill": query.skill, "path": path, "event_link": created_event.get('htmlLink')}

class TaskQuery(BaseModel):
    task: str
    user_id: str

@app.post("/tasks/remind")
async def send_reminder(query: TaskQuery):
    service = get_calendar_service()
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    start_time = now + timedelta(minutes=30)
    end_time = start_time + timedelta(hours=1)
    event = {
        'summary': query.task,
        'description': f"Reminder for {query.user_id}",
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'reminders': {'useDefault': True}
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return {"task": query.task, "event_link": created_event.get('htmlLink')}

@app.post("/client/analyze")
async def analyze_doc(file: UploadFile = File(...)):
    content = await file.read().decode('utf-8')
    grok_url = "https://api.x.ai/v1/chat/completions"
    grok_headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
    grok_payload = {
        "model": "grok-4",
        "messages": [{"role": "user", "content": f"Extract deliverables from document: {content[:500]}"}],
        "stream": False,
        "temperature": 0.7
    }
    grok_response = requests.post(grok_url, headers=grok_headers, json=grok_payload)
    if grok_response.status_code != 200:
        raise HTTPException(status_code=grok_response.status_code, detail=f"Grok API error: {grok_response.text}")
    deliverables = grok_response.json().get("choices", [{}])[0].get("message", {}).get("content", "No deliverables")
    return {"deliverables": deliverables}

class ProxyQuery(BaseModel):
    endpoint: str
    payload: dict

@app.post("/mcp/proxy")
async def mcp_proxy(query: ProxyQuery):
    internal_url = f"http://127.0.0.1:8000{query.endpoint}"
    headers = {"Content-Type": "application/json"}
    response = requests.post(internal_url, json=query.payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=f"Internal API error: {response.text}")
    return response.json()
