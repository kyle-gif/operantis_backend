from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import play
import os

# 1. FastAPI 앱 인스턴스 생성
app = FastAPI()
load_dotenv()

elevenlabs = ElevenLabs(

  api_key=os.getenv("ELEVENLABS_API_KEY"),

)

# 2. POST 요청으로 받을 데이터의 형식을 Pydantic 모델로 정의
class LLMAnalysis(BaseModel):
    analysis_text: str


# 3. "/receive_llm_analysis" 엔드포인트 정의
# 이 엔드포인트는 LLMAnalysis 형식의 JSON 데이터를 POST 요청으로 받습니다.
async def tts(analysis_data: LLMAnalysis):
    audio = elevenlabs.text_to_speech.convert(

        text=analysis_data.analysis_text,

        voice_id="uyVNoMrnUku1dZyVEXwD",

        model_id="eleven_multilingual_v2",

        output_format="mp3_44100_128",

    )
    play(audio)

@app.post("/receive_llm_analysis")
async def receive_llm_analysis(analysis_data: LLMAnalysis):
    """
    메인 스크립트로부터 LLM 분석 결과를 받아 콘솔에 출력합니다.
    """
    await tts(analysis_data)
    print("\n--- 새로운 LLM 분석 결과 수신 ---")
    print(analysis_data.analysis_text)
    print("--------------------------------\n")

    # 여기서 수신한 데이터를 DB에 저장하거나, 웹소켓으로 다른 클라이언트에 전달하는 등
    # 다양한 추가 작업을 수행할 수 있습니다.

    return {"status": "success", "message": "Analysis received"}


# 4. 서버 실행 (테스트용)
# 이 파일을 직접 실행할 경우, uvicorn 서버가 8000번 포트에서 실행됩니다.
if __name__ == "__main__":
    print("FastAPI 서버를 시작합니다. http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)