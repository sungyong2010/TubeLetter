from google import genai
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 환경 변수에서 API 키 가져오기
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ 오류: .env 파일에 GEMINI_API_KEY가 설정되어야 합니다.")
    exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)
response = client.models.generate_content(
    # model = "gemini-2.0-flash",
    model = "gemini-2.0-flash-exp",
    # model = "gemini-1.5-flash",
    # model = 'models/gemini-1.5-flash',
    # model = 'gemini-1.5-flash-latest',
    # model = 'gemini-1.5-flash-001',
    # model = 'gemini-pro',
    # model = 'gemini-pro-vision',
    contents="Hello"
)
print(response.text)