import os
from slack_sdk import WebClient
from dotenv import load_dotenv
import openai

load_dotenv()
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

def send_slack_message(message):
    slack_client.chat_postMessage(channel=CHANNEL_ID, text=message)

def generate_ai_response(prompt):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

def add_clap_reaction(ts, channel=None):
    """
    특정 메시지(ts)에 👏 리액션을 추가합니다.
    channel이 None이면 기본 CHANNEL_ID 사용.
    """
    if channel is None:
        channel = CHANNEL_ID
    slack_client.reactions_add(
        channel=channel,
        name="clap",
        timestamp=ts
    ) 