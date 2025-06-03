import os
from datetime import datetime
from zoneinfo import ZoneInfo
from utils import send_slack_message, slack_client, CHANNEL_ID
import openai
from slack_sdk.errors import SlackApiError
from collections import defaultdict
import notion_client
from openai import OpenAI
from tqdm import tqdm
import numpy as np

openai.api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 오늘 메시지 수집
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
        return [msg for msg in messages if "text" in msg and not msg.get("bot_id")]
    except SlackApiError as e:
        print(f"Slack API 오류: {e}")
        return []

# 정보 밀도 평가
def information_density(messages):
    informative = 0
    for msg in messages:
        prompt = f"이 Slack 메시지는 정보 전달(논의/결정/지식공유)인가요, 아니면 잡담인가요?\n메시지: {msg['text']}\n답: informative 또는 chatter로만 답하세요."
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10, temperature=0
        )
        answer = resp.choices[0].message.content.strip().lower()
        if "informative" in answer:
            informative += 1
    return informative / len(messages) if messages else 0

# Action Item 추출
def extract_action_items(messages):
    prompt = "아래는 오늘 Slack 대화입니다. Action Item(할 일, 요청, 결정 등)을 항목별로 추출해줘.\n" + "\n".join([m['text'] for m in messages])
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300, temperature=0.3
    )
    items = [line for line in resp.choices[0].message.content.splitlines() if line.strip().startswith("-")]
    return items

# 응답 속도(분)
def avg_response_time(messages):
    ts_map = {m['ts']: m for m in messages}
    total, count = 0, 0
    for m in messages:
        thread_ts = m.get('thread_ts')
        if thread_ts and thread_ts != m['ts'] and thread_ts in ts_map:
            parent = ts_map[thread_ts]
            diff = float(m['ts']) - float(parent['ts'])
            total += diff / 60
            count += 1
    return total / count if count else 0

# 요약 길이(단어 수)
def summary_length(messages):
    prompt = "아래는 오늘 Slack 대화입니다. 요약해줘.\n" + "\n".join([m['text'] for m in messages])
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500, temperature=0.5
    )
    summary = resp.choices[0].message.content
    return len(summary.split())

# 발화자 분포
def speaker_distribution(messages):
    dist = defaultdict(int)
    for m in messages:
        user = m.get('user', 'unknown')
        dist[user] += 1
    return dict(dist)

# 대화 중복도 측정 (임베딩 기반)
def message_redundancy(messages, threshold=0.85):
    if len(messages) < 2:
        return 0.0
    texts = [m['text'] for m in messages]
    embeds = client.embeddings.create(
        input=texts,
        model="text-embedding-ada-002"
    ).data
    vectors = np.array([e.embedding for e in embeds])
    # 코사인 유사도 행렬 계산
    norm = np.linalg.norm(vectors, axis=1, keepdims=True)
    normed = vectors / (norm + 1e-8)
    sim_matrix = np.dot(normed, normed.T)
    # 상삼각행렬에서 자기 자신 제외, threshold 이상 비율 계산
    n = len(texts)
    redundant = 0
    total = 0
    for i in range(n):
        for j in range(i+1, n):
            total += 1
            if sim_matrix[i, j] >= threshold:
                redundant += 1
    return redundant / total if total else 0.0

# 할 일 이행 비율 측정
def action_item_completion_ratio(messages, action_items):
    if not action_items:
        return 0.0
    completed = 0
    texts = [m['text'] for m in messages]
    for item in action_items:
        # Action Item에서 핵심 키워드 추출 (단순화: 첫 5글자)
        keyword = item.replace('-', '').strip().split()[0]
        found = False
        for text in texts:
            if keyword in text and any(x in text for x in ["완료", "했어요", "PR", "merge", "끝", "처리"]):
                found = True
                break
        if found:
            completed += 1
    return completed / len(action_items)

def append_report_to_notion(report: str):
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    PAGE_ID = os.getenv("NOTION_PAGE_ID")
    notion = notion_client.Client(auth=NOTION_TOKEN)
    now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    try:
        notion.blocks.children.append(
            block_id=PAGE_ID,
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"[생산성 메트릭 보고서] {now}\n{report}"}
                            }
                        ]
                    }
                }
            ]
        )
        print("✅ Notion 페이지에 보고서가 추가되었습니다.")
    except Exception as e:
        print("❌ Notion 페이지에 보고서 추가 실패!", e)

# 메트릭 종합 및 전송
def main():
    
    messages = get_today_messages()
    if not messages:
        send_slack_message("오늘 대화가 없습니다. (생산성 평가 불가)")
        return
    info_density = information_density(messages)
    action_items = extract_action_items(messages)
    avg_resp = avg_response_time(messages)
    sum_len = summary_length(messages)
    speaker_dist = speaker_distribution(messages)
    redundancy = message_redundancy(messages)
    completion_ratio = action_item_completion_ratio(messages, action_items)
    report = f"[오늘의 생산성 메트릭]\n"
    report += f"정보 밀도: {info_density:.2f}\n"
    report += f"Action Item 수: {len(action_items)}\n"
    report += f"평균 응답 속도: {avg_resp:.1f}분\n"
    report += f"요약 길이: {sum_len} 단어\n"
    report += f"발화자 분포: {speaker_dist}\n"
    report += f"대화 중복도: {redundancy:.2%}\n"
    report += f"Action Item 이행 비율: {completion_ratio:.2%}\n"
    # send_slack_message(report)
    append_report_to_notion(report)

if __name__ == "__main__":
    main() 