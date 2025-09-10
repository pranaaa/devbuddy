# devbuddy

Instructions to Run DevBuddy

Clone the Repository:
git clone https://github.com/pranaaa/devbuddy.git
cd devbuddy


Install Dependencies:

Ensure Python 3.12 is installed.
Create and activate a virtual environment:python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate  # Windows


Install required packages:pip install fastapi uvicorn pydantic requests python-dotenv google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 psycopg2-binary
pip freeze > requirements.txt




Set Up Environment Variables:

Create a .env file in the project root:touch .env


Add your GitHub Personal Access Token with repo scope:GITHUB_TOKEN=your_github_token


Generate the token at github.com/settings/tokens.


Configure Google OAuth:

Ensure credentials.json is in the project root and updated with the needed content.

Add your Google account as a test user in Google Cloud Console:
Go to console.cloud.google.com.
Select project dev-buddy-471613.
Navigate to APIs & Services > OAuth consent screen > Test users > Add your email.




Run the Application:

Start the FastAPI server:uvicorn main:app --reload


Access the Swagger UI at http://127.0.0.1:8000/docs.
Test endpoints:
Code Review: Use {"pr_id": "630", "repo": "Physical-Intelligence/openpi"} to analyze a pull request.
Upskilling Path: Use {"skill": "Python"} to get learning resources and a Google Calendar event.
Task Reminders: Use {"task": "Complete UI design", "user_id": "user123"} to schedule a task.
Client Analysis: Upload a file (e.g., sample_ui_api.txt with content "Deliverables: UI design, backend API, due 2025-09-15") to extract deliverables.
MCP Proxy: Use {"endpoint": "/code/review", "payload": {"pr_id": "630", "repo": "Physical-Intelligence/openpi"}} for AI-agent integration.




