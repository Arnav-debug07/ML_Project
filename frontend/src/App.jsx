import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';

// Helper function to format timestamp
const formatTimestamp = (seconds) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
};

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState('');
  const [transcript, setTranscript] = useState('');
  const [segments, setSegments] = useState([]);
  const [summary, setSummary] = useState('');
  const [summaryType, setSummaryType] = useState('detailed');
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');
  const [translating, setTranslating] = useState(false);
  const [translatingTranscript, setTranslatingTranscript] = useState(false);
  const [translatedSummary, setTranslatedSummary] = useState('');
  const [translatedSegments, setTranslatedSegments] = useState([]);

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      setError('');
      // Reset previous results
      setTranscript('');
      setSummary('');
      setUploadedFilename('');
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a video file first');
      return;
    }

    setUploading(true);
    setError('');
    setProgress('Uploading video...');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await axios.post(`${API_BASE_URL}/upload-video`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setUploadedFilename(response.data.filename);
      setProgress('Video uploaded successfully! Ready to process.');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Upload failed';
      setError(errorMsg);
    } finally {
      setUploading(false);
    }
  };

  const handleProcess = async () => {
    if (!uploadedFilename) {
      setError('Please upload a video first');
      return;
    }

    setProcessing(true);
    setError('');
    setProgress('Processing video...');

    try {
      // Step 1: Extract audio
      setProgress('Extracting audio from video...');
      
      // Step 2: Transcribe and summarize
      setProgress('Transcribing audio with Whisper... (this may take a while)');
      
      const response = await axios.post(
        `${API_BASE_URL}/process-video?filename=${uploadedFilename}&summary_type=${summaryType}`
      );

      setTranscript(response.data.transcript);
      setSegments(response.data.segments || []);
      setSummary(response.data.summary);
      setProgress('Processing complete!');
      
      // Cleanup uploaded file after processing
      await axios.delete(`${API_BASE_URL}/cleanup/${uploadedFilename}`);
      
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Processing failed';
      setError(errorMsg);
      setProgress('');
    } finally {
      setProcessing(false);
    }
  };

  const handleRegenerateSummary = async (newType) => {
    if (!transcript) {
      setError('No transcript available');
      return;
    }

    setSummaryType(newType);
    setProgress(`Regenerating ${newType} summary...`);
    setTranslatedSummary(''); // Clear translation when regenerating

    try {
      const response = await axios.post(`${API_BASE_URL}/summarize-transcript`, {
        transcript: transcript,
        summary_type: newType,
      });

      setSummary(response.data.summary);
      setProgress('Summary regenerated!');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Summary regeneration failed';
      setError(errorMsg);
    }
  };

  const handleTranslate = async () => {
    if (!summary) {
      setError('No summary to translate');
      return;
    }

    setTranslating(true);
    setProgress('Translating summary to English...');

    try {
      const response = await axios.post(
        `${API_BASE_URL}/translate-summary?text=${encodeURIComponent(summary)}`
      );

      setTranslatedSummary(response.data.translated);
      setProgress('Translation complete!');
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Translation failed';
      setError(errorMsg);
    } finally {
      setTranslating(false);
    }
  };

  const handleTranslateTranscript = async () => {
    if (!segments || segments.length === 0) {
      setError('No transcript to translate');
      return;
    }

    setTranslatingTranscript(true);
    setProgress('Translating transcript to English...');
    setError(''); // Clear previous errors

    try {
      const response = await axios.post(
        `${API_BASE_URL}/translate-transcript`,
        { segments: segments }  // Wrap segments in an object
      );

      setTranslatedSegments(response.data.segments);
      setProgress('Transcript translation complete!');
      setTimeout(() => setProgress(''), 3000); // Clear progress after 3 seconds
    } catch (err) {
      console.error('Translation error:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Transcript translation failed';
      setError(errorMsg);
      setProgress('');
    } finally {
      setTranslatingTranscript(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>🎥 Video Summarizer</h1>
        <p>Upload a video, get AI-powered transcription and summary</p>
      </header>

      <div className="container">
        {/* Upload Section */}
        <div className="section upload-section">
          <h2>Step 1: Upload Video</h2>
          <div className="file-input-wrapper">
            <input
              type="file"
              accept="video/*"
              onChange={handleFileSelect}
              id="file-input"
              disabled={uploading || processing}
            />
            <label htmlFor="file-input" className="file-input-label">
              {selectedFile ? selectedFile.name : 'Choose Video File'}
            </label>
          </div>
          
          <button
            onClick={handleUpload}
            disabled={!selectedFile || uploading || processing}
            className="btn btn-primary"
          >
            {uploading ? 'Uploading...' : 'Upload Video'}
          </button>
        </div>

        {/* Process Section */}
        {uploadedFilename && (
          <div className="section process-section">
            <h2>Step 2: Process & Summarize</h2>
            
            <div className="summary-type-selector">
              <label>Summary Type:</label>
              <select
                value={summaryType}
                onChange={(e) => setSummaryType(e.target.value)}
                disabled={processing}
              >
                <option value="detailed">Detailed Summary</option>
                <option value="brief">Brief Summary</option>
                <option value="bullet_points">Bullet Points</option>
              </select>
            </div>

            <button
              onClick={handleProcess}
              disabled={processing}
              className="btn btn-success"
            >
              {processing ? 'Processing...' : 'Transcribe & Summarize'}
            </button>
          </div>
        )}

        {/* Progress/Error Messages */}
        {progress && (
          <div className="progress-message">
            <div className="spinner"></div>
            <p>{progress}</p>
          </div>
        )}

        {error && (
          <div className="error-message">
            <strong>Error:</strong> {typeof error === 'string' ? error : JSON.stringify(error)}
          </div>
        )}

        {/* Results Section */}
        {summary && (
          <div className="results-section">
            <div className="section summary-section">
              <div className="section-header">
                <h2>📝 Summary</h2>
                <div className="summary-controls">
                  <div className="summary-type-buttons">
                    <button
                      onClick={() => handleRegenerateSummary('detailed')}
                      className={`btn-small ${summaryType === 'detailed' ? 'active' : ''}`}
                    >
                      Detailed
                    </button>
                    <button
                      onClick={() => handleRegenerateSummary('brief')}
                      className={`btn-small ${summaryType === 'brief' ? 'active' : ''}`}
                    >
                      Brief
                    </button>
                    <button
                      onClick={() => handleRegenerateSummary('bullet_points')}
                      className={`btn-small ${summaryType === 'bullet_points' ? 'active' : ''}`}
                    >
                      Bullets
                    </button>
                  </div>
                  <button
                    onClick={handleTranslate}
                    disabled={translating}
                    className="btn-translate"
                  >
                    {translating ? '🔄 Translating...' : '🌐 Translate to English'}
                  </button>
                </div>
              </div>
              <div className="summary-content">
                {summary.split('\n').map((line, index) => (
                  <div key={index}>{line}</div>
                ))}
              </div>
              
              {translatedSummary && (
                <div className="translated-section">
                  <h3>🌐 English Translation</h3>
                  <div className="summary-content translated">
                    {translatedSummary.split('\n').map((line, index) => (
                      <div key={index}>{line}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="section transcript-section">
              <div className="transcript-header">
                <h2>📜 Full Transcript</h2>
                {segments.length > 0 && (
                  <button
                    onClick={handleTranslateTranscript}
                    disabled={translatingTranscript}
                    className="btn-translate-small"
                  >
                    {translatingTranscript ? '🔄 Translating...' : '🌐 Translate Transcript'}
                  </button>
                )}
              </div>
              <details>
                <summary>Click to view full transcript with timestamps</summary>
                <div className="transcript-content">
                  {segments.length > 0 ? (
                    <div className="timestamped-transcript">
                      {segments.map((segment, index) => {
                        const translatedSeg = translatedSegments.find((_, i) => i === index);
                        return (
                          <div key={index} className="transcript-segment">
                            <span className="timestamp">
                              [{formatTimestamp(segment.start)} - {formatTimestamp(segment.end)}]
                            </span>
                            <div className="segment-texts">
                              <span className="segment-text original">{segment.text}</span>
                              {translatedSeg && translatedSeg.translated && (
                                <span className="segment-text translated">
                                  🌐 {translatedSeg.translated}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p>{transcript}</p>
                  )}
                </div>
              </details>
            </div>
          </div>
        )}
      </div>

      <footer>
        <p>Powered by Whisper AI & Google Gemini</p>
      </footer>
    </div>
  );
}

export default App;