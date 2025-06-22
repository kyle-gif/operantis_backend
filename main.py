from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import play
import os

app = FastAPI()
load_dotenv()

elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"),)

class LLMAnalysis(BaseModel):
    analysis_text: str

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
    await tts(analysis_data)
    print("\n--- 새로운 LLM 분석 결과 수신 ---")
    print(analysis_data.analysis_text)
    print("--------------------------------\n")

    return {"status": "success", "message": "Analysis received"}