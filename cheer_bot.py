# Socket Mode 기반 실시간 리스너 버전

import time
import os
import json
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from utils import generate_ai_response, add_clap_reaction

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
BOT_USER_ID = os.environ.get("BOT_USER_ID")
CHEOLHO_USER_ID = "U08TA111MPH"  # Cheolho Kang님의 user_id
RESPONDED_MESSAGES_FILE = "responded_messages.json"

def load_responded_messages():
    if os.path.exists(RESPONDED_MESSAGES_FILE):
        with open(RESPONDED_MESSAGES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_responded_message(message_id):
    responded = load_responded_messages()
    responded.append(message_id)
    with open(RESPONDED_MESSAGES_FILE, 'w') as f:
        json.dump(responded, f)

def should_respond_to_message(msg):
    # 1. Cheolho Kang님이 쓴 메시지
    if msg.get("user") != CHEOLHO_USER_ID:
        return False
    # 2. 스레드(댓글)에는 반응하지 않음
    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
        return False
    # 3. 이미 응답한 메시지에는 또 반응하지 않음
    responded = load_responded_messages()
    if msg["ts"] in responded:
        return False
    # 4. 텍스트 없는 메시지 제외
    if "text" not in msg or not msg["text"].strip():
        return False
    return True

def generate_cheer_message(user_message):
    prompt = f"""
    다음은 Cheolho Kang님이 작성한 메시지입니다. 이 메시지에 대해 강한 동의와 아부(칭찬, 감탄, 적극적 공감 등)를 섞어, 친근하고 격려하는 응원 메시지를 작성해주세요.
    메시지는 2-3줄 이내로 간단하게 작성해주세요.
    
    Cheolho Kang님의 메시지:
    {user_message}
    
    예시 응답:
    정말 탁월한 의견이에요! Cheolho Kang님 덕분에 팀이 한 단계 성장할 것 같아요. 이런 통찰력, 정말 존경스럽습니다! 👏
    """
    return generate_ai_response(prompt)

client = WebClient(token=SLACK_BOT_TOKEN)
socket_client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=client)

def handle_events_api(client, req):
    if req.type == "events_api":
        event = req.payload["event"]
        if event["type"] == "message":
            msg = event
            if should_respond_to_message(msg):
                cheer_message = generate_cheer_message(msg["text"])
                if cheer_message:
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                    message = f"*[{current_time}] 응원 메시지*\n\n{cheer_message}"
                    client.web_client.chat_postMessage(channel=msg["channel"], text=message, thread_ts=msg["ts"])
                    add_clap_reaction(msg["ts"])
                    save_responded_message(msg["ts"])
        # 이벤트 응답
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

socket_client.socket_mode_request_listeners.append(handle_events_api)

if __name__ == "__main__":
    print("🚀 Cheer Up Bot (Socket Mode) Started!", flush=True)
    socket_client.connect()
    print("✅ Socket Mode WebSocket 연결 시도 완료 (이후 이벤트가 오면 정상 연결)", flush=True)
    import time
    while True:
        time.sleep(10)