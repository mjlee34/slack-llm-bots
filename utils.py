import os
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

def send_slack_message(message):
    slack_client.chat_postMessage(channel=CHANNEL_ID, text=message) 