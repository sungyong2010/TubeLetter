# TubeLetter

## 설정 방법

### 1. 가상 환경 생성 및 의존성 설치
```powershell
# PowerShell
python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

```bash
# Bash/Linux/Mac
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 실제 값을 입력하세요:
```powershell
Copy-Item .env.example .env
```

`.env` 파일에 다음 정보를 입력:
- `GEMINI_API_KEY`: https://aistudio.google.com/app/apikey
- `EMAIL_ADDRESS`: Gmail 주소
- `EMAIL_PASSWORD`: Gmail 앱 비밀번호

### 3. RSS 피드 설정
`rss_feeds.txt` 파일에 구독할 유튜브 채널 ID를 입력하세요.

### 4. 실행
```powershell
python SumMail.py
```

## 개발자용

### 의존성 목록 저장
```powershell
pip freeze > requirements.txt
```


