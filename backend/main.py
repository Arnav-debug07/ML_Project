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

# Initialize translation pipeline for non-English summaries
print("Loading translation model...")
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-mul-en")
print("Translation model loaded!")


class SummaryRequest(BaseModel):
    transcript: str
    summary_type: str = "detailed"  # detailed, brief, bullet_points


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptRequest(BaseModel):
    segments: list[TranscriptSegment]


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


def chunk_text(text: str, max_chunk_size: int = 900) -> list:
    """Split text into smaller chunks for summarization (conservative limit)"""
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_length = len(word) + 1  # +1 for space
        # Use conservative estimate: ~1.3 chars per token
        estimated_tokens = (current_length + word_length) / 1.3
        
        if estimated_tokens > max_chunk_size:
            if current_chunk:  # Make sure we have something to add
                chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = len(word)
        else:
            current_chunk.append(word)
            current_length += word_length
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks


def translate_to_english(text: str) -> str:
    """Translate text to English using Hugging Face translation model"""
    try:
        # Split text into chunks if too long (max ~512 tokens for translation)
        max_chars = 400  # Conservative limit
        if len(text) > max_chars:
            # Split into sentences roughly
            chunks = []
            current_chunk = ""
            sentences = text.split(". ")
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
                else:
                    current_chunk += (". " if current_chunk else "") + sentence
            
            if current_chunk:
                chunks.append(current_chunk)
            
            # Translate each chunk
            translated_chunks = []
            for chunk in chunks:
                result = translator(chunk, max_length=512)
                translated_chunks.append(result[0]['translation_text'])
            
            return " ".join(translated_chunks)
        else:
            # Translate directly
            result = translator(text, max_length=512)
            return result[0]['translation_text']
    except Exception as e:
        print(f"Translation failed: {e}")
        return text  # Return original if translation fails


def summarize_with_huggingface(transcript: str, summary_type: str = "detailed") -> str:
    """Generate summary using Hugging Face BART model"""
    
    try:
        # Count words in transcript
        word_count = len(transcript.split())
        
        # If transcript is too short, return it as-is
        if word_count < 30:
            return transcript
        
        # Different parameters for each summary type
        # Key: Make max_length and min_length significantly different
        max_length_params = {
            "detailed": {"max_length": 300, "min_length": 150},      # Longest, most comprehensive
            "brief": {"max_length": 100, "min_length": 40},          # Short and concise
            "bullet_points": {"max_length": 200, "min_length": 80}   # Medium length
        }
        
        params = max_length_params.get(summary_type, max_length_params["detailed"])
        
        # Adjust min_length based on transcript length
        adjusted_min_length = min(params["min_length"], word_count - 10, params["max_length"] - 20)
        adjusted_min_length = max(adjusted_min_length, 10)
        
        # Check transcript length - use conservative threshold (700 words ≈ 900 tokens)
        if word_count > 700:
            # For long transcripts, chunk and summarize
            chunks = chunk_text(transcript, max_chunk_size=900)
            summaries = []
            
            print(f"Splitting transcript into {len(chunks)} chunks...")
            
            # Calculate chunk parameters based on summary type
            chunk_max = max(params["max_length"] // max(len(chunks), 1), 50)
            chunk_min = max(adjusted_min_length // max(len(chunks), 1), 10)
            
            for i, chunk in enumerate(chunks):
                chunk_words = len(chunk.split())
                print(f"Processing chunk {i+1}/{len(chunks)} ({chunk_words} words)...")
                
                # Skip very short chunks
                if chunk_words < 20:
                    summaries.append(chunk)
                    continue
                    
                # Ensure min_length < chunk length and max_length
                safe_min = min(chunk_min, chunk_words - 5, chunk_max - 10)
                safe_min = max(safe_min, 10)
                
                result = summarizer(
                    chunk,
                    max_length=chunk_max,
                    min_length=safe_min,
                    do_sample=False,
                    truncation=True
                )
                summaries.append(result[0]['summary_text'])
            
            # Combine chunk summaries
            combined_summary = " ".join(summaries)
            
            # Post-process based on summary type
            if summary_type == "bullet_points":
                # Convert to bullet points
                sentences = combined_summary.split('. ')
                bullet_summary = "• " + "\n• ".join([s.strip() for s in sentences if s.strip()])
                return bullet_summary
            
            # If combined summary is still long for detailed/brief, summarize again
            combined_words = len(combined_summary.split())
            if combined_words > params["max_length"]:
                print(f"Re-summarizing combined text ({combined_words} words)...")
                safe_min_final = min(adjusted_min_length, combined_words - 10, params["max_length"] - 20)
                safe_min_final = max(safe_min_final, 10)
                
                final_result = summarizer(
                    combined_summary,
                    max_length=params["max_length"],
                    min_length=safe_min_final,
                    do_sample=False,
                    truncation=True
                )
                final_text = final_result[0]['summary_text']
                
                # Format for bullet points
                if summary_type == "bullet_points":
                    sentences = final_text.split('. ')
                    return "• " + "\n• ".join([s.strip() for s in sentences if s.strip()])
                
                return final_text
            
            return combined_summary
        else:
            # For shorter transcripts, summarize directly
            print(f"Summarizing transcript ({word_count} words)...")
            result = summarizer(
                transcript,
                max_length=min(params["max_length"], word_count + 50),
                min_length=adjusted_min_length,
                do_sample=False,
                truncation=True
            )
            summary_text = result[0]['summary_text']
            
            # Format for bullet points
            if summary_type == "bullet_points":
                sentences = summary_text.split('. ')
                return "• " + "\n• ".join([s.strip() for s in sentences if s.strip()])
            
            return summary_text
            
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
        segments = transcription_result.get("segments", [])
        
        # Format segments with timestamps
        timestamped_segments = []
        for seg in segments:
            timestamped_segments.append({
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "")
            })
        
        # Step 3: Summarize with Hugging Face
        print("Generating summary with Hugging Face...")
        summary = summarize_with_huggingface(transcript, summary_type)
        
        # Cleanup
        os.unlink(audio_path)
        
        return {
            "filename": filename,
            "transcript": transcript,
            "segments": timestamped_segments,
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


@app.post("/translate-summary")
async def translate_summary(text: str):
    """
    Translate summary to English
    """
    try:
        translated_text = translate_to_english(text)
        
        # Format bullet points if they exist
        if "•" in translated_text or "\n" in translated_text:
            # Already has bullets or newlines, keep formatting
            formatted_text = translated_text
        else:
            # Check if original had bullets (might have been lost in translation)
            if "•" in text:
                # Split by periods and add bullets
                sentences = [s.strip() for s in translated_text.split('.') if s.strip()]
                formatted_text = "• " + "\n• ".join(sentences)
            else:
                formatted_text = translated_text
        
        return {
            "original": text,
            "translated": formatted_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")


@app.post("/translate-transcript")
async def translate_transcript_segments(request: TranscriptRequest):
    """
    Translate transcript segments with timestamps to English
    """
    try:
        translated_segments = []
        
        for segment in request.segments:
            translated_text = translate_to_english(segment.text)
            translated_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "translated": translated_text
            })
        
        return {
            "segments": translated_segments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcript translation failed: {str(e)}")


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