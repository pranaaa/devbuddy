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
from fastapi.responses import JSONResponse
import json
import psycopg2

load_dotenv()
app = FastAPI(title="DevBuddy MCP Server")

# API credentials
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
NEON_DSN = os.getenv("NEON_DSN")  # e.g., postgres://user:pass@host.neon.tech/db
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Neon DB connection
neon_conn = psycopg2.connect(NEON_DSN)
neon_cursor = neon_conn.cursor()
neon_cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, user_id VARCHAR, task VARCHAR, status VARCHAR, created_at TIMESTAMP)''')
neon_conn.commit()

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


@app.post("/mcp")
async def mcp_endpoint(request: dict):
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or "method" not in request:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": request.get("id")}
        )

    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")

    # Define available tools
    tools = [
        {"name": "code_review", "description": "Analyzes GitHub PR for code quality", "parameters": {"pr_id": "string", "repo": "string"}},
        {"name": "learn_path", "description": "Generates learning path for a skill", "parameters": {"skill": "string"}},
        {"name": "task_remind", "description": "Creates Google Calendar task reminder", "parameters": {"task": "string", "user_id": "string"}},
        {"name": "client_analyze", "description": "Extracts deliverables from client document", "parameters": {"content": "string"}}
    ]

    # Define resources (e.g., task history in Neon DB)
    resources = [
        {"name": "task_history", "description": "Stored task history from Neon DB", "type": "database"}
    ]

    # Define prompts
    prompts = [
        {"name": "code_review_prompt", "description": "Prompt for analyzing PR descriptions"},
        {"name": "client_analyze_prompt", "description": "Prompt for extracting deliverables from documents"}
    ]

    if method == "tools/list":
        return {"jsonrpc": "2.0", "result": tools, "id": request_id}

    if method == "tools/call":
        tool_name = params.get("tool")
        tool_params = params.get("params", {})
        
        if tool_name == "code_review":
            url = f"https://api.github.com/repos/{tool_params.get('repo')}/pulls/{tool_params.get('pr_id')}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                return JSONResponse(
                    status_code=400,
                    content={"jsonrpc": "2.0", "error": {"code": -32000, "message": "GitHub API error"}, "id": request_id}
                )
            pr_data = response.json()
            body = pr_data.get("body", "") or "No description"
            return {"jsonrpc": "2.0", "result": {"pr_id": tool_params.get("pr_id"), "repo": tool_params.get("repo"), "description": body}, "id": request_id}

        elif tool_name == "learn_path":
            url = f"https://api.github.com/search/repositories?q={tool_params.get('skill')}+language:{tool_params.get('skill')}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                return JSONResponse(
                    status_code=400,
                    content={"jsonrpc": "2.0", "error": {"code": -32000, "message": "GitHub API error"}, "id": request_id}
                )
            repos = response.json().get("items", [])[:3]
            path = [repo['full_name'] for repo in repos]
            service = get_calendar_service()
            ist = ZoneInfo("Asia/Kolkata")
            now = datetime.now(ist)
            start_time = now + timedelta(minutes=30)
            end_time = start_time + timedelta(hours=1)
            event = {
                'summary': f"Learn {tool_params.get('skill')}",
                'description': f"Upskilling path: {', '.join(path)}",
                'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
                'reminders': {'useDefault': True}
            }
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            return {"jsonrpc": "2.0", "result": {"skill": tool_params.get("skill"), "path": path, "event_link": created_event.get('htmlLink')}, "id": request_id}

        elif tool_name == "task_remind":
            service = get_calendar_service()
            ist = ZoneInfo("Asia/Kolkata")
            now = datetime.now(ist)
            start_time = now + timedelta(minutes=30)
            end_time = start_time + timedelta(hours=1)
            event = {
                'summary': tool_params.get("task"),
                'description': f"Reminder for {tool_params.get('user_id')}",
                'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
                'reminders': {'useDefault': True}
            }
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            neon_cursor.execute("INSERT INTO tasks (user_id, task, status, created_at) VALUES (%s, %s, %s, %s)", (tool_params.get("user_id"), tool_params.get("task"), "pending", now))
            neon_conn.commit()
            return {"jsonrpc": "2.0", "result": {"task": tool_params.get("task"), "event_link": created_event.get('htmlLink'), "neon_status": "Task stored in Neon DB"}, "id": request_id}

        elif tool_name == "client_analyze":
            content = tool_params.get("content", "")
            return {"jsonrpc": "2.0", "result": {"content": content}, "id": request_id}

        else:
            return JSONResponse(
                status_code=400,
                content={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request_id}
            )

    if method == "resources/list":
        return {"jsonrpc": "2.0", "result": resources, "id": request_id}

    if method == "resources/read":
        resource_name = params.get("name")
        if resource_name == "task_history":
            neon_cursor.execute("SELECT user_id, task, status, created_at FROM tasks ORDER BY created_at DESC LIMIT 10")
            tasks = [{"user_id": row[0], "task": row[1], "status": row[2], "created_at": row[3].isoformat()} for row in neon_cursor.fetchall()]
            return {"jsonrpc": "2.0", "result": {"tasks": tasks}, "id": request_id}
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Resource not found"}, "id": request_id}
        )

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "result": prompts, "id": request_id}

    if method == "prompts/get":
        prompt_name = params.get("name")
        for prompt in prompts:
            if prompt["name"] == prompt_name:
                return {"jsonrpc": "2.0", "result": prompt, "id": request_id}
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Prompt not found"}, "id": request_id}
        )

    if method == "sampling/createMessage":
        content = params.get("content", "")
        return {"jsonrpc": "2.0", "result": {"message": f"Processed: {content[:100]}"}, "id": request_id}

    return JSONResponse(
        status_code=400,
        content={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": request_id}
    )

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
    return {"pr_id": query.pr_id, "repo": query.repo, "description": body}

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
    neon_cursor.execute("INSERT INTO tasks (user_id, task, status, created_at) VALUES (%s, %s, %s, %s)", (query.user_id, query.task, "pending", now))
    neon_conn.commit()
    return {"task": query.task, "event_link": created_event.get('htmlLink'), "neon_status": "Task stored in Neon DB"}

@app.post("/client/analyze")
async def analyze_doc(file: UploadFile = File(...)):
    content = (await file.read()).decode('utf-8')
    return {"content": content}

class ProxyQuery(BaseModel):
    endpoint: str
    payload: dict

@app.post("/mcp/proxy")
async def mcp_proxy(query: ProxyQuery):
    internal_url = f"http://127.0.0.1:8000{query.endpoint}"
    headers = {"Content-Type": "application/json"}
    response = requests.post(internal_url, json=query.payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Internal API error")
    return response.json()

@app.get("/mcp/proxy")
async def mcp_proxy_health():
    return {"status": "Proxy ready"}
