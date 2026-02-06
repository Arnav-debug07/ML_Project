import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState('');
  const [transcript, setTranscript] = useState('');
  const [summary, setSummary] = useState('');
  const [summaryType, setSummaryType] = useState('detailed');
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');

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
      setError(err.response?.data?.detail || 'Upload failed');
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
      setSummary(response.data.summary);
      setProgress('Processing complete!');
      
      // Cleanup uploaded file after processing
      await axios.delete(`${API_BASE_URL}/cleanup/${uploadedFilename}`);
      
    } catch (err) {
      setError(err.response?.data?.detail || 'Processing failed');
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

    try {
      const response = await axios.post(`${API_BASE_URL}/summarize-transcript`, {
        transcript: transcript,
        summary_type: newType,
      });

      setSummary(response.data.summary);
      setProgress('Summary regenerated!');
    } catch (err) {
      setError(err.response?.data?.detail || 'Summary regeneration failed');
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
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Results Section */}
        {summary && (
          <div className="results-section">
            <div className="section summary-section">
              <div className="section-header">
                <h2>📝 Summary</h2>
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
              </div>
              <div className="summary-content">
                {summary}
              </div>
            </div>

            <div className="section transcript-section">
              <h2>📜 Full Transcript</h2>
              <details>
                <summary>Click to view full transcript</summary>
                <div className="transcript-content">
                  {transcript}
                </div>
              </details>
            </div>
          </div>
        )}
      </div>

      <footer>
        <p>Powered by Whisper AI & Hugging Face</p>
      </footer>
    </div>
  );
}

export default App;