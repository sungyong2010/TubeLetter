import feedparser
import time
from google import genai  # 변경: google.generativeai → google.genai
from youtube_transcript_api import YouTubeTranscriptApi
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 설정 구간 ---
DEBUG = True  # 디버깅 플래그 (True: 디버깅 메시지 출력, False: 숨김)

# 환경 변수에서 민감 정보 불러오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# 필수 환경 변수 검증
if not all([GEMINI_API_KEY, EMAIL_ADDRESS, EMAIL_PASSWORD]):
    print("❌ 오류: .env 파일에 다음 변수들이 설정되어야 합니다:")
    if not GEMINI_API_KEY:
        print("   - GEMINI_API_KEY")
    if not EMAIL_ADDRESS:
        print("   - EMAIL_ADDRESS")
    if not EMAIL_PASSWORD:
        print("   - EMAIL_PASSWORD")
    print("\n💡 .env.example 파일을 참고하여 .env 파일을 생성하세요.")
    exit(1)

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
            'gemini-1.5-flash',      # ✅ 가장 안정적인 무료 모델 (권장)
            'gemini-1.5-flash-8b',   # ✅ 경량화 모델
            'gemini-1.5-pro',        # ✅ 고성능 모델(한도 낮음)
            'gemini-2.0-flash-exp',  # ✅ 실험적 모델 (미리보기)
            'gemini-2.0-flash',      # ❌ 아직 일반 공개 안됨
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
processed_videos = set()

def get_transcript(video_id):
    """자막 추출 함수"""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        return " ".join([i['text'] for i in transcript_list])
    except:
        return None

def send_email(subject, body):
    """이메일 발송 함수"""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

def process_youtube_automation():
    feeds_to_process = RSS_FEEDS[:1] if DEBUG else RSS_FEEDS
    
    for feed_url in feeds_to_process:
        try:
            feed = feedparser.parse(feed_url)
            if DEBUG:
                print(f"📡 피드 처리 중: {feed_url[:50]}...")
                print(f"   📊 총 {len(feed.entries)}개의 영상 발견")
            
            for entry in feed.entries:
                try:
                    video_id = entry.yt_videoid
                    if video_id not in processed_videos:
                        print(f"\n🎥 새 영상 발견: {entry.title}")
                        print(f"   📌 Video ID: {video_id}")
                        print(f"   🔗 Link: {entry.link}")
                        
                        # 1. 자막 가져오기
                        print(f"   ⏳ 자막 추출 중...")
                        transcript = get_transcript(video_id)
                        if transcript:
                            print(f"   ✅ 자막 추출 성공 (길이: {len(transcript)})")
                            content_to_analyze = transcript
                        else:
                            print(f"   ⚠ 자막 없음, 제목/설명으로 진행")
                            content_to_analyze = f"제목: {entry.title}\n설명: {entry.summary}"
                        
                        # 2. Gemini 요약 (새 API 사용)
                        print(f"   ⏳ Gemini 요약 생성 중...")
                        prompt = f"다음 유튜브 영상 내용을 3문장으로 핵심 요약해줘:\n\n{content_to_analyze}"
                        
                        try:
                            # 새 API 사용법
                            response = client.models.generate_content(
                                model=model_name,
                                contents=prompt
                            )
                            summary = response.text
                            print(f"   ✅ 요약 생성 완료")
                            print(f"   📝 요약 내용:\n{summary}")
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
                        
                        # 3. 이메일 전송 (DEBUG 모드에서는 스킵)
                        if DEBUG:
                            print(f"   ⏭ 이메일 전송 스킵 (디버깅 모드)")
                        else:
                            print(f"   ⏳ 이메일 전송 중...")
                            send_email(f"[요약] {entry.title}", f"영상 링크: {entry.link}\n\n{summary}")
                            print(f"   ✅ 이메일 전송 완료")
                        
                        processed_videos.add(video_id)
                        print(f"✅ 처리 완료: {entry.title}\n")
                        
                        # 디버깅 모드: 첫 번째 영상만 처리하고 중단
                        if DEBUG:
                            print("=" * 60)
                            print("🛑 디버깅 모드: 첫 번째 영상만 처리")
                            print("=" * 60)
                            return
                        
                except Exception as e:
                    error_msg = str(e)
                    
                    # API 한도 초과 에러
                    if "API 한도 초과" in error_msg:
                        print(f"\n⏹ 프로그램 종료됨")
                        raise
                    
                    # 다른 에러는 계속 진행
                    print(f"⚠ 영상 처리 중 오류: {error_msg[:80]}")
                    continue
        except Exception as e:
            print(f"⚠ 피드 처리 중 오류: {e}")
            continue

# 프로그램 실행 (DEBUG 모드: 첫 번째 영상만, 프로덕션: 모든 새 영상)
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
