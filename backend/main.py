"""
Video Summarizer Backend - FastAPI
Handles video upload, audio extraction, Whisper transcription, and Hugging Face summarization
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import whisper
import os
import shutil
from pathlib import Path
from pydub import AudioSegment
import tempfile
from typing import Optional
from pydantic import BaseModel
from transformers import pipeline

app = FastAPI(title="Video Summarizer API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Load Whisper model (this will download on first run)
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")  # Options: tiny, base, small, medium, large
print("Whisper model loaded!")

# Initialize Hugging Face summarization pipeline (uses free local inference)
print("Loading Hugging Face summarization model...")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
print("Hugging Face model loaded!")


class SummaryRequest(BaseModel):
    transcript: str
    summary_type: str = "detailed"  # detailed, brief, bullet_points


def extract_audio_from_video(video_path: str, output_audio_path: str):
    """Extract audio from video file using pydub/ffmpeg"""
    try:
        # Load video and extract audio
        video = AudioSegment.from_file(video_path)
        # Export as WAV for Whisper
        video.export(output_audio_path, format="wav")
        return True
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio using Whisper"""
    try:
        result = whisper_model.transcribe(audio_path)
        return {
            "text": result["text"],
            "segments": result.get("segments", []),
            "language": result.get("language", "unknown")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


def summarize_with_huggingface(transcript: str, summary_type: str = "detailed") -> str:
    """Generate summary using Hugging Face"""
    
    prompts = {
        "detailed": f"""
        Please provide a detailed summary of the following video transcript.
        Include:
        - Main topics discussed
        - Key points and takeaways
        - Important details and examples mentioned
        - Overall conclusion
        
        Transcript:
        {transcript}
        """,
        
        "brief": f"""
        Provide a brief 2-3 paragraph summary of this video transcript,
        focusing only on the most important points.
        
        Transcript:
        {transcript}
        """,
        
        "bullet_points": f"""
        Summarize this video transcript as a bulleted list of key points.
        Use clear, concise bullet points (5-10 points).
        
        Transcript:
        {transcript}
        """
    }
    
    try:
        prompt = prompts.get(summary_type, prompts["detailed"])
        response = summarizer(prompt, max_length=150, min_length=40, do_sample=False)
        return response[0]['summary_text']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")


@app.get("/")
async def root():
    return {"message": "Video Summarizer API is running!"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "whisper_loaded": whisper_model is not None,
        "huggingface_configured": summarizer is not None
    }


@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """
    Upload video file and return file info
    """
    # Validate file type
    allowed_extensions = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Save uploaded file
    file_path = UPLOAD_DIR / file.filename
    
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "filename": file.filename,
            "size": file_path.stat().st_size,
            "path": str(file_path),
            "message": "Video uploaded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/process-video")
async def process_video(filename: str, summary_type: str = "detailed"):
    """
    Process uploaded video: extract audio -> transcribe -> summarize
    """
    video_path = UPLOAD_DIR / filename
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    # Create temporary audio file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        audio_path = temp_audio.name
    
    try:
        # Step 1: Extract audio
        print(f"Extracting audio from {filename}...")
        if not extract_audio_from_video(str(video_path), audio_path):
            raise HTTPException(status_code=500, detail="Audio extraction failed")
        
        # Step 2: Transcribe with Whisper
        print("Transcribing audio with Whisper...")
        transcription_result = transcribe_audio(audio_path)
        transcript = transcription_result["text"]
        
        # Step 3: Summarize with Hugging Face
        print("Generating summary with Hugging Face...")
        summary = summarize_with_huggingface(transcript, summary_type)
        
        # Cleanup
        os.unlink(audio_path)
        
        return {
            "filename": filename,
            "transcript": transcript,
            "language": transcription_result.get("language"),
            "summary": summary,
            "summary_type": summary_type,
            "transcript_length": len(transcript),
            "word_count": len(transcript.split())
        }
        
    except Exception as e:
        # Cleanup on error
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize-transcript")
async def summarize_transcript(request: SummaryRequest):
    """
    Generate summary from existing transcript
    """
    summary = summarize_with_huggingface(request.transcript, request.summary_type)
    return {
        "summary": summary,
        "summary_type": request.summary_type
    }


@app.delete("/cleanup/{filename}")
async def cleanup_file(filename: str):
    """
    Delete uploaded video file
    """
    file_path = UPLOAD_DIR / filename
    
    if file_path.exists():
        os.unlink(file_path)
        return {"message": f"File {filename} deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

