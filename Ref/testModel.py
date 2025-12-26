from google import genai
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 디버깅용 Pause 함수
def pause(message="계속하려면 Enter를 누르세요..."):
    """사용자 입력을 기다리는 디버깅 함수"""
    input(f"\n⏸ {message}")

# 환경 변수에서 API 키 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ 오류: .env 파일에 GEMINI_API_KEY가 설정되어야 합니다.")
    exit(1)    

client = genai.Client(api_key=GEMINI_API_KEY)
# 사용 가능한 모델 목록 출력 코드
for model in client.models.list():
    # print(f"Model Name: {model.name}, Supported Actions: {model.supported_actions}")
    print(f"Model : {model}")

pause()
response = client.models.generate_content(
    # 🚀 추천: 최신 안정 버전
    model = "gemini-2.5-flash",  # ⭐ 최신 2.5 버전 - 가장 빠르고 효율적 (강력 추천!)
    # model = "gemini-2.5-pro",  # 🧠 2.5 Pro - 복잡한 작업용, 높은 정확도
    # model = "gemini-2.5-flash-lite",  # 🏃 2.5 경량 - 초고속, 간단한 작업용
    
    # ✅ 2.0 안정 버전
    # model = "gemini-2.0-flash",  # ❌ 현재 할당량 초과
    # model = "gemini-2.0-flash-001",  # 2.0 특정 버전
    # model = "gemini-2.0-flash-lite",  # 2.0 경량 버전
    # model = "gemini-2.0-flash-lite-001",  # 2.0 경량 특정 버전
    
    # 🧪 실험용 모델
    # model = "gemini-2.0-flash-exp",  # ❌ 실험용 2.0 - 할당량 제한
    # model = "gemini-exp-1206",  # 실험용 최신 빌드
    # model = "gemini-3-flash-preview",  # 🔥 3.0 프리뷰 (최신 실험)
    # model = "gemini-3-pro-preview",  # 🔥 3.0 Pro 프리뷰
    
    # 🎯 별칭 (자동 최신 버전)
    # model = "gemini-flash-latest",  # Flash 시리즈 최신
    # model = "gemini-pro-latest",  # Pro 시리즈 최신
    # model = "gemini-flash-lite-latest",  # Lite 시리즈 최신
    
    # 🎨 이미지 생성 특화
    # model = "gemini-2.5-flash-image",  # 이미지 생성 가능
    # model = "gemini-2.0-flash-exp-image-generation",  # 실험용 이미지 생성
    
    # 🎤 오디오/TTS 특화
    # model = "gemini-2.5-flash-preview-tts",  # Text-to-Speech
    # model = "gemini-2.5-flash-native-audio-latest",  # 네이티브 오디오 처리
    
    # 🤖 오픈소스 Gemma 시리즈
    # model = "gemma-3-27b-it",  # 가장 큰 Gemma 3 모델
    # model = "gemma-3-12b-it",  # 중형 Gemma 3
    # model = "gemma-3-4b-it",  # 소형 Gemma 3
    # model = "gemma-3-1b-it",  # 초경량 Gemma 3
    
    # 🔍 특수 목적 모델
    # model = "deep-research-pro-preview-12-2025",  # 심층 연구용
    # model = "nano-banana-pro-preview",  # 나노 바나나 (특수)
    # model = "gemini-robotics-er-1.5-preview",  # 로보틱스용
    # model = "gemini-2.5-computer-use-preview-10-2025",  # 컴퓨터 사용 제어
    
    contents="Hello"
)
print(response.text)