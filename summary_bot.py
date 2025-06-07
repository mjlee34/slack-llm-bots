from utils import slack_client, send_slack_message, generate_ai_response, show_progress, update_progress, delete_progress, CHANNEL_ID
import schedule
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os
import openai

def extract_action_items(conversation):
    """
    대화 내용을 기반으로 Action Item과 담당자를 추출하는 함수 (OpenAI API 활용)
    """
    prompt = f"""
    아래 대화 내용에서 오늘의 Action Item(할 일, 요청, 결정 등)을 담당자와 함께 항목별로 추출해 주세요.
    각 항목은 "- [담당자] 할 일" 형식으로 작성해 주세요. 담당자가 명확하지 않으면 [미지정]으로 표기하세요.

    대화 내용:
    {conversation}

    답변 예시:
    - [홍길동] 문서 작성
    - [김철수] 회의 일정 잡기
    - [미지정] 자료 조사
    """
    result = generate_ai_response(prompt)
    # 결과 후처리: '- ['로 시작하는 줄만 추출
    items = []
    for line in result.splitlines():
        line = line.strip()
        if line.startswith('- ['):
            items.append(line)
    return items

def generate_daily_summary():
    """하루 동안의 대화 내용을 요약합니다."""
    print("\n📊 일일 요약 생성 시작...")
    
    # 진행 상황 표시 시작
    progress_message = show_progress("🔄 일일 요약을 생성하는 중입니다...")
    
    # 오늘의 메시지들 가져오기
    print("📥 Slack 메시지 수집 중...")
    update_progress(progress_message, "📥 Slack 메시지를 수집하는 중입니다...")
    
    # 오늘 자정부터의 타임스탬프 계산
    today_start = datetime.now(ZoneInfo("Asia/Seoul")).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    
    try:
        # 오늘의 메시지 가져오기
        response = slack_client.conversations_history(
            channel=CHANNEL_ID,
            oldest=today_start,
            limit=1000  # 충분히 큰 수로 설정
        )
        messages = response["messages"]
        
        # 다음 페이지가 있다면 계속 가져오기
        while response.get('response_metadata', {}).get('next_cursor'):
            cursor = response['response_metadata']['next_cursor']
            response = slack_client.conversations_history(
                channel=CHANNEL_ID,
                oldest=today_start,
                cursor=cursor,
                limit=1000
            )
            messages.extend(response["messages"])
            
        print(f"✅ {len(messages)}개의 메시지 수집 완료")
    except SlackApiError as e:
        print(f"❌ Slack API 오류: {e}")
        update_progress(progress_message, "❌ 메시지 수집 실패")
        delete_progress(progress_message)
        return
    
    # 메시지 내용 추출
    message_texts = []
    for msg in messages:
        if "text" in msg and not msg.get("bot_id"):  # 봇 메시지 제외
            message_texts.append(msg["text"])
    
    if not message_texts:
        print("❌ 처리할 메시지가 없습니다.")
        update_progress(progress_message, "❌ 처리할 메시지가 없습니다.")
        delete_progress(progress_message)
        return
    
    print(f"📝 {len(message_texts)}개의 메시지 처리 중...")
    update_progress(progress_message, f"📝 {len(message_texts)}개의 메시지를 처리하는 중입니다...")
    
    # 메시지들을 하나의 문자열로 결합
    conversation = "\n".join(message_texts)
    
    # 요약 생성
    prompt = f"""
    다음은 오늘 팀 채널에서 나눈 대화 내용입니다. 
    주요 논의 사항, 결정된 사항, 다음 단계로 진행해야 할 작업들을 요약해주세요:
    
    {conversation}
    
    다음 형식으로 요약해주세요:
    1. 주요 논의 사항
    2. 결정된 사항
    3. 다음 단계 작업
    4. 특이사항
    """
    
    print("🔄 AI 요약 생성 중...")
    update_progress(progress_message, "🤖 AI가 요약을 생성하는 중입니다...")
    summary = generate_ai_response(prompt)
    
    # Action Item 추출
    print("📝 Action Item 추출 중...")
    update_progress(progress_message, "📝 Action Item을 추출하는 중입니다...")
    action_items = extract_action_items(conversation)
    
    # 메시지 전송
    if summary:
        current_time = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
        message = f"*[{current_time}] 오늘의 대화 요약*\n\n{summary}"
        if action_items:
            message += "\n\n*오늘의 Action Items*\n" + "\n".join(action_items)
        else:
            message += "\n\n*오늘의 Action Items*\n(없음)"
        print("📤 Slack으로 메시지 전송 중...")
        update_progress(progress_message, "📤 요약을 전송하는 중입니다...")
        send_slack_message(message)
        print("✅ 메시지 전송 완료!")
    else:
        print("❌ 요약 생성 실패")
        update_progress(progress_message, "❌ 요약 생성에 실패했습니다.")
    
    # 진행 상황 메시지 삭제
    delete_progress(progress_message)

def get_today_messages():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        response = slack_client.conversations_history(
            channel=CHANNEL_ID,
            oldest=today_start,
            limit=1000
        )
        messages = response["messages"]
        return [msg["text"] for msg in messages if "text" in msg and not msg.get("bot_id")]
    except SlackApiError as e:
        print(f"Slack API 오류: {e}")
        return []

def summarize(messages):
    if not messages:
        return "오늘 대화가 없습니다."
    prompt = "다음은 오늘 팀 채널에서 나눈 대화 내용입니다. 요약해줘:\n" + "\n".join(messages)
    openai.api_key = os.getenv("OPENAI_API_KEY")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

def main():
    """메인 함수"""
    print("🚀 요약 봇 시작...")
    
    # 바로 요약 실행
    print("📝 요약 생성 중...")
    try:
        generate_daily_summary()
        print("✅ 요약이 성공적으로 생성되었습니다!")
    except Exception as e:
        print(f"❌ 요약 생성 중 오류 발생: {e}")
    
    print("\n테스트 완료! 봇을 종료합니다.")

    messages = get_today_messages()
    summary = summarize(messages)
    send_slack_message(f"[오늘의 요약]\n{summary}")

if __name__ == "__main__":
    main() 