"""
python -m PyInstaller `
    --onefile  `
    --name="tube.letter" tube.letter.py
"""
import feedparser
import time
from google import genai  # 변경: google.generativeai → google.genai
from youtube_transcript_api import YouTubeTranscriptApi
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import json
import markdown  # pip install markdown
from datetime import datetime, timedelta
from dateutil import parser as date_parser  # pip install python-dateutil

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 설정 구간 ---
DEBUG = True  # 디버깅 플래그 (True: 디버깅 메시지 출력, False: 숨김)
HOURS_TO_CHECK = 24  # 최근 몇 시간 이내의 영상만 처리 (24시간 = 1일)

# 환경 변수에서 민감 정보 불러오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")  # 보내는 이메일 (발신자)
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS")  # 받는 이메일들 (쉼표로 구분)

# 필수 환경 변수 검증
if not all([GEMINI_API_KEY, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS]):
    print("❌ 오류: .env 파일에 다음 변수들이 설정되어야 합니다:")
    if not GEMINI_API_KEY:
        print("   - GEMINI_API_KEY")
    if not EMAIL_SENDER:
        print("   - EMAIL_SENDER (발신자 이메일)")
    if not EMAIL_PASSWORD:
        print("   - EMAIL_PASSWORD")
    if not EMAIL_RECIPIENTS:
        print("   - EMAIL_RECIPIENTS (수신자 이메일, 쉼표로 구분)")
    print("\n💡 .env.example 파일을 참고하여 .env 파일을 생성하세요.")
    exit(1)

# 수신자 이메일 리스트 파싱 (쉼표로 구분된 문자열을 리스트로 변환)
RECIPIENT_LIST = [email.strip() for email in EMAIL_RECIPIENTS.split(',') if email.strip()]

if DEBUG:
    print(f"📧 발신자: {EMAIL_SENDER}")
    print(f"📬 수신자: {len(RECIPIENT_LIST)}명")
    for i, recipient in enumerate(RECIPIENT_LIST, 1):
        print(f"   {i}. {recipient}")

# Gemini API 무료 요금제 한도
GEMINI_FREE_TIER_LIMITS = {
    "requests_per_minute": 15,           # 분당 요청 수
    "requests_per_day": 1500,            # 일일 요청 수
    "input_tokens_per_minute": 1_000_000,  # 분당 입력 토큰
    "input_tokens_per_day": 1_000_000,   # 일일 입력 토큰
}

# 디버깅용 Pause 함수
def pause(message="계속하려면 Enter를 누르세요..."):
    """사용자 입력을 기다리는 디버깅 함수"""
    input(f"\n⏸ {message}")

# rss_feeds.txt에서 채널 ID를 읽어서 RSS 피드 URL 생성
def load_rss_feeds(filepath='rss_feeds.txt'):
    """rss_feeds.txt 파일에서 채널 ID를 읽어 RSS 피드 URL 리스트 생성"""
    rss_feeds = []
    encodings = ['utf-8', 'euc-kr', 'cp949', 'utf-16', 'latin-1']  # 인코딩 시도 순서
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                print(f"💬 파일 인코딩: {encoding}")
                for line in f:
                    line = line.strip()
                    # 빈 줄 무시
                    if not line:
                        continue
                    # 채널 이름과 ID 분리 (형식: "채널명: 채널ID")
                    if ':' in line:
                        channel_id = line.split(':')[-1].strip()
                    else:
                        channel_id = line
                    # 유효한 채널 ID인지 확인 (UC로 시작하고 길이가 24)
                    if channel_id.startswith('UC') and len(channel_id) == 24:
                        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                        rss_feeds.append(url)
                        print(f"✓ 로드됨: {channel_id}")
                    else:
                        print(f"⚠ 무효한 채널 ID: {channel_id}")
            return rss_feeds  # 성공하면 반환
        except (UnicodeDecodeError, FileNotFoundError) as e:
            if encoding == encodings[-1]:  # 마지막 인코딩도 실패
                print(f"❌ {filepath} 파일을 읽을 수 없습니다. 시도된 인코딩: {', '.join(encodings)}")
            continue
        except Exception as e:
            print(f"❌ 파일 읽기 중 오류 발생: {e}")
            return rss_feeds
    
    return rss_feeds

# RSS 피드 로드
RSS_FEEDS = load_rss_feeds('rss_feeds.txt')

if not RSS_FEEDS:
    print("❌ 로드된 RSS 피드가 없습니다. rss_feeds.txt를 확인하세요.")
elif DEBUG:
    print(f"\n📊 디버깅: 총 {len(RSS_FEEDS)}개의 RSS 피드가 로드됨")
    for i, feed in enumerate(RSS_FEEDS, 1):
        print(f"  {i}. {feed}")
    print()

# Gemini 클라이언트 생성 (새 API 방식)
client = genai.Client(api_key=GEMINI_API_KEY)

# Gemini 모델 설정 (사용 가능한 모델 자동 선택)
def get_available_model():
    """사용 가능한 Gemini 모델 확인"""
    try:
        models = [
            "gemini-2.5-flash",  # ⭐ 최신 2.5 버전 - 가장 빠르고 효율적 (강력 추천!)
        ]
        for model_name in models:
            try:
                if DEBUG:
                    print(f"🔍 모델 확인 중: {model_name}")
                # 새 API에서는 모델 이름만 반환
                print(f"✅ 사용할 모델: {model_name}")
                return model_name
            except Exception as e:
                if DEBUG:
                    print(f"  ❌ {model_name} 불가: {str(e)[:50]}")
                continue

        print("❌ 사용 가능한 Gemini 모델을 찾을 수 없습니다.")
        print("   https://ai.google.dev/gemini-api/docs/models/gemini 에서 사용 가능한 모델을 확인하세요.")
        return None
    except Exception as e:
        print(f"❌ 모델 확인 중 오류: {e}")
        return None

model_name = get_available_model()
if not model_name:
    print("❌ 프로그램을 종료합니다.")
    exit(1)

# 이미 요약한 영상 ID를 저장할 세트 (중복 방지)
PROCESSED_VIDEOS_FILE = 'processed_videos.json'

def load_processed_videos():
    """파일에서 처리된 영상 ID 불러오기"""
    try:
        with open(PROCESSED_VIDEOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if DEBUG:
                print(f"📂 캐시 로드: {len(data)}개의 처리된 영상")
            return set(data)
    except FileNotFoundError:
        if DEBUG:
            print("📂 캐시 파일 없음, 새로 생성")
        return set()
    except Exception as e:
        print(f"⚠ 캐시 로드 실패: {e}")
        return set()

def save_processed_videos(processed_videos):
    """처리된 영상 ID를 파일에 저장"""
    try:
        with open(PROCESSED_VIDEOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(processed_videos), f, indent=2)
        if DEBUG:
            print(f"💾 캐시 저장: {len(processed_videos)}개")
    except Exception as e:
        print(f"⚠ 캐시 저장 실패: {e}")

# 프로그램 시작 시 캐시 로드
processed_videos = load_processed_videos()

def get_transcript(video_id):
    """자막 추출 함수"""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        return " ".join([i['text'] for i in transcript_list])
    except:
        return None

def send_email(subject, body):
    """이메일 발송 함수 (HTML 지원, 다중 수신자)"""
    # 마크다운을 HTML로 변환
    html_body = markdown.markdown(body, extensions=['nl2br', 'tables'])
    
    # HTML 스타일 추가
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            h1, h2, h3 {{ color: #2c3e50; }}
            ul, ol {{ margin-left: 20px; }}
            strong {{ color: #e74c3c; }}
            code {{ background-color: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """
    
    # Multipart 메시지 생성
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = ', '.join(RECIPIENT_LIST)  # 여러 수신자를 쉼표로 연결
    
    # 텍스트와 HTML 버전 모두 추가
    part1 = MIMEText(body, 'plain', 'utf-8')
    part2 = MIMEText(html_content, 'html', 'utf-8')
    
    msg.attach(part1)
    msg.attach(part2)
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
    
    if DEBUG:
        print(f"   📧 이메일 발송: {EMAIL_SENDER} → {len(RECIPIENT_LIST)}명")

def process_youtube_automation():
    # 모든 피드 처리 (DEBUG 모드 상관없이)
    feeds_to_process = RSS_FEEDS
    
    # 시간 기준 설정 (현재 시각 - HOURS_TO_CHECK)
    time_threshold = datetime.now(datetime.now().astimezone().tzinfo) - timedelta(hours=HOURS_TO_CHECK)
    
    if DEBUG:
        print(f"⏰ 시간 필터: {HOURS_TO_CHECK}시간 이내 ({time_threshold.strftime('%Y-%m-%d %H:%M:%S')} 이후)")
    
    total_processed = 0  # 처리된 영상 수
    total_skipped_old = 0  # 오래된 영상 스킵 수
    total_skipped_cached = 0  # 캐시된 영상 스킵 수
    
    for feed_url in feeds_to_process:
        try:
            feed = feedparser.parse(feed_url)
            channel_name = feed.feed.title if hasattr(feed.feed, 'title') else 'Unknown'
            
            if DEBUG:
                print(f"\n{'='*60}")
                print(f"📡 채널: {channel_name}")
                print(f"   피드: {feed_url[:60]}...")
                print(f"   총 {len(feed.entries)}개의 영상 발견")
            
            channel_processed = 0
            
            for entry in feed.entries:
                try:
                    video_id = entry.yt_videoid
                    
                    # 1. 캐시 확인 (이미 처리한 영상)
                    if video_id in processed_videos:
                        total_skipped_cached += 1
                        if DEBUG:
                            print(f"   ⏭ 스킵 (캐시됨): {entry.title[:50]}...")
                        continue
                    
                    # 2. 게시 시간 확인 (최근 HOURS_TO_CHECK 시간 이내인지)
                    try:
                        # RSS 피드의 published 또는 updated 시간 파싱
                        if hasattr(entry, 'published_parsed'):
                            pub_time = datetime(*entry.published_parsed[:6])
                        elif hasattr(entry, 'updated_parsed'):
                            pub_time = datetime(*entry.updated_parsed[:6])
                        else:
                            # 시간 정보가 없으면 처리 (안전장치)
                            pub_time = datetime.now()
                        
                        # 타임존 추가 (naive datetime을 aware datetime으로 변환)
                        if pub_time.tzinfo is None:
                            pub_time = pub_time.replace(tzinfo=time_threshold.tzinfo)
                        
                        # 시간 비교
                        if pub_time < time_threshold:
                            total_skipped_old += 1
                            if DEBUG:
                                age_hours = (datetime.now(time_threshold.tzinfo) - pub_time).total_seconds() / 3600
                                print(f"   ⏭ 스킵 (오래됨): {entry.title[:50]}... ({age_hours:.1f}시간 전)")
                            continue
                    
                    except Exception as time_error:
                        if DEBUG:
                            print(f"   ⚠ 시간 파싱 실패, 영상 처리 계속: {time_error}")
                    
                    # 3. 새 영상 처리
                    print(f"\n{'─'*60}")
                    print(f"🎥 새 영상 발견: {entry.title}")
                    print(f"   📺 채널: {channel_name}")
                    print(f"   📌 Video ID: {video_id}")
                    print(f"   🔗 Link: {entry.link}")
                    if hasattr(entry, 'published'):
                        print(f"   📅 게시: {entry.published}")
                    
                    # 4. 자막 가져오기
                    print(f"   ⏳ 자막 추출 중...")
                    transcript = get_transcript(video_id)
                    if transcript:
                        print(f"   ✅ 자막 추출 성공 (길이: {len(transcript)}자)")
                        content_to_analyze = transcript
                    else:
                        print(f"   ⚠ 자막 없음, 제목/설명으로 진행")
                        content_to_analyze = f"제목: {entry.title}\n설명: {entry.summary}"
                        
                        # 5. Gemini 요약 (새 API 사용)
                        print(f"   ⏳ Gemini 요약 생성 중...")
                        prompt = f"""다음 유튜브 영상의 내용을 상세하게 분석하고 요약해줘.

[요약 지침]
1. 영상의 핵심 주제와 배경을 명확히 설명
2. 주요 논점을 3-5개의 섹션으로 구조화 (번호 매기기)
3. 각 섹션마다 구체적인 내용과 근거 포함
4. 중요한 발언, 수치, 날짜 등은 반드시 언급
5. 결론 또는 시사점 추가
6. 전문적이고 상세하게 작성 (최소 500자 이상)

[영상 제목]
{entry.title}

[영상 내용]
{content_to_analyze}

위 내용을 바탕으로 전문적이고 상세한 요약을 작성해줘."""
                        
                        try:
                            # 새 API 사용법 (상세 요약을 위한 설정 추가)
                            response = client.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config={
                                    "temperature": 0.3,  # 일관성 있는 요약을 위해 낮게 설정
                                    "top_p": 0.9,
                                    "top_k": 40,
                                    "max_output_tokens": 4096,  # 상세한 요약을 위해 토큰 증가
                                }
                            )
                            summary = response.text
                            print(f"   ✅ 요약 생성 완료")
                            if DEBUG:
                                print(f"   📝 요약 내용:\n{'-'*60}\n{summary}\n{'-'*60}")
                            else:
                                print(f"   📝 요약 길이: {len(summary)}자")
                        except Exception as gemini_error:
                            error_msg = str(gemini_error)
                            
                            # API 한도 초과 에러 처리
                            if "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in str(type(gemini_error)):
                                print(f"\n{'='*60}")
                                print(f"❌ Gemini API 무료 요금제 한도 초과")
                                print(f"{'='*60}")
                                print(f"📋 문제: API 요청 한도에 도달했습니다.")
                                print(f"\n📊 무료 요금제 한도:")
                                print(f"   • 분당 요청: {GEMINI_FREE_TIER_LIMITS['requests_per_minute']}회")
                                print(f"   • 일일 요청: {GEMINI_FREE_TIER_LIMITS['requests_per_day']}회")
                                print(f"   • 분당 입력 토큰: {GEMINI_FREE_TIER_LIMITS['input_tokens_per_minute']:,}개")
                                print(f"   • 일일 입력 토큰: {GEMINI_FREE_TIER_LIMITS['input_tokens_per_day']:,}개")
                                print(f"\n✅ 해결 방법:")
                                print(f"   1️⃣ 내일까지 기다리기 (24시간 후 리셋)")
                                print(f"   2️⃣ 유료 요금제 업그레이드")
                                print(f"      🔗 https://ai.google.dev/pricing")
                                print(f"   3️⃣ 다른 API 키 사용")
                                print(f"\n📖 참고 자료:")
                                print(f"   🔗 https://ai.google.dev/gemini-api/docs/rate-limits")
                                print(f"   🔗 https://ai.dev/usage?tab=rate-limit")
                                print(f"{'='*60}\n")
                                
                                # 프로그램 종료
                                raise Exception("API 한도 초과로 프로그램 종료")
                            else:
                                print(f"   ❌ 요약 생성 실패: {error_msg}")
                                
                                if DEBUG:
                                    print("=" * 60)
                                    print("🛑 디버깅 모드: 에러 발생으로 중단")
                                    print("=" * 60)
                                    raise
                                else:
                                    raise
                        
                        # 6. 이메일 전송 여부 확인
                        print(f"\n{'─'*60}")
                        send_choice = input("📧 이메일을 전송하시겠습니까? (y: 전송 / n: 스킵): ").strip().lower()
                        print(f"{'─'*60}")

                        if send_choice == 'y':
                            print(f"   ⏳ 이메일 전송 중...")
                            email_body = f"""
═══════════════════════════════════════════════════
📺 YouTube 영상 요약
═══════════════════════════════════════════════════

🎬 제목: {entry.title}

🔗 링크: {entry.link}

📅 게시일: {entry.published if hasattr(entry, 'published') else 'N/A'}

═══════════════════════════════════════════════════
📝 요약 내용
═══════════════════════════════════════════════════

{summary}

═══════════════════════════════════════════════════
🤖 이 요약은 TubeLetter에 의해 자동 생성되었습니다.
═══════════════════════════════════════════════════
"""
                            send_email(f"[요약] {entry.title}", email_body)
                            print(f"   ✅ 이메일 전송 완료")
                        else:
                            print(f"   ⏭ 이메일 전송 스킵")
                        
                        processed_videos.add(video_id)
                        save_processed_videos(processed_videos)  # ✅ 즉시 저장
                        print(f"✅ 처리 완료: {entry.title[:50]}...\n")
                        
                        channel_processed += 1
                        total_processed += 1
                        
                        # 사용자 확인 받기 (계속 진행 여부)
                        print(f"{'─'*60}")
                        user_input = input("⏸ 다음 영상을 처리하시겠습니까? (Enter: 계속 / q: 종료): ").strip().lower()
                        if user_input == 'q':
                            print(f"\n🛑 사용자 요청으로 프로그램 종료")
                            return
                        print(f"{'─'*60}\n")
                        
                except Exception as e:
                    error_msg = str(e)
                    
                    # API 한도 초과 에러
                    if "API 한도 초과" in error_msg:
                        print(f"\n⏹ 프로그램 종료됨")
                        raise
                    
                    # 다른 에러는 계속 진행
                    print(f"⚠ 영상 처리 중 오류: {error_msg[:80]}")
                    continue
            
            if DEBUG:
                print(f"📊 채널 '{channel_name}' 처리 완료: {channel_processed}개 영상 요약")
                
        except Exception as e:
            print(f"⚠ 피드 처리 중 오류: {e}")
            continue
    
    # 최종 통계
    print(f"\n{'='*60}")
    print(f"📊 처리 완료 통계")
    print(f"{'='*60}")
    print(f"✅ 요약 생성: {total_processed}개")
    print(f"⏭ 캐시 스킵: {total_skipped_cached}개")
    print(f"⏭ 오래된 영상 스킵: {total_skipped_old}개")
    print(f"{'='*60}")

# 프로그램 실행
if __name__ == "__main__":
    if DEBUG:
        print("=" * 60)
        print("🚀 TubeLetter 프로그램 시작")
        print("=" * 60)
    
    try:
        if RSS_FEEDS:
            print("🔄 자동화 작업 실행 중...")
            process_youtube_automation()
            print("✅ 작업 완료\n")
        else:
            print("❌ RSS 피드가 없어 프로그램을 종료합니다.")
    except Exception as e:
        error_msg = str(e)
        
        # API 한도 초과 에러
        if "API 한도 초과" in error_msg:
            pass
        else:
            print(f"❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
