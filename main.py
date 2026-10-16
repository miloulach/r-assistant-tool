import asyncio
import threading
import secrets
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import pandas as pd
import subprocess
import os
import tempfile
import json
import re
from pathlib import Path
from typing import List, Optional
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Google Generative AI
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')


# Paths are resolved from this file so the app works from any working directory
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
PLOTS_DIR = BASE_DIR / "plots"
RESULTS_DIR = BASE_DIR / "results"

# Optional key for the web endpoints; MCP code execution is disabled unless it is set
API_KEY = os.getenv("APP_API_KEY")

# Resource limits for each R process
R_TIMEOUT_SECONDS = int(os.getenv("R_TIMEOUT_SECONDS", "30"))
R_MAX_MEMORY_MB = int(os.getenv("R_MAX_MEMORY_MB", "2048"))
R_MAX_FILE_MB = int(os.getenv("R_MAX_FILE_MB", "100"))


def _key_matches(provided: Optional[str]) -> bool:
    return bool(API_KEY and provided and secrets.compare_digest(provided, API_KEY))


async def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Protect web endpoints when APP_API_KEY is configured"""
    if API_KEY and not _key_matches(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_mcp_api_key(x_api_key: Optional[str] = Header(default=None)):
    """MCP tools run arbitrary R code, so they always require a key"""
    if not API_KEY:
        raise HTTPException(status_code=403, detail="MCP tool calls are disabled. Set APP_API_KEY to enable them.")
    if not _key_matches(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def safe_csv_filename(filename: Optional[str]) -> str:
    """Strip directories and unsafe characters from an uploaded file name"""
    base = Path(filename or "").name
    if not base.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", base[:-4]).strip("._") or "data"
    return f"{stem[:100]}.csv"


def resolve_inside(directory: Path, filename: str) -> Path:
    """Return directory/filename only if it stays inside directory"""
    directory = directory.resolve()
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _r_sandbox_env() -> dict:
    """Minimal environment for R so secrets such as GOOGLE_API_KEY are not exposed"""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "R_HOME", "R_LIBS", "R_LIBS_USER", "R_LIBS_SITE")
    return {k: os.environ[k] for k in keep if k in os.environ}


def _limit_r_resources():
    """Applied in the child process before R starts (POSIX only)"""
    import resource
    limits = [
        (resource.RLIMIT_CPU, R_TIMEOUT_SECONDS),
        (resource.RLIMIT_AS, R_MAX_MEMORY_MB * 1024 * 1024),
        (resource.RLIMIT_FSIZE, R_MAX_FILE_MB * 1024 * 1024),
    ]
    for limit, value in limits:
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass


# Ensure R packages are installed
def ensure_r_packages():
    subprocess.run(["Rscript", "install_packages.R"], check=True, cwd=BASE_DIR)

ensure_r_packages()

app = FastAPI(title="R Chat Assistant Tool", description="Chat with AI to analyze CSV data using R")

# Create directories
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
PLOTS_DIR.mkdir(exist_ok=True)

# Store chat sessions and current CSV info
chat_sessions = {}

class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    r_code: Optional[str] = None
    execution_result: Optional[dict] = None
    error: Optional[str] = None
    plot_filename: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def main():
    """Chat interface for R data analysis"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>R Chat Assistant</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
            .container { display: flex; gap: 20px; }
            .upload-section { flex: 1; }
            .chat-section { flex: 2; }
            .chat-box { border: 1px solid #ccc; height: 400px; padding: 10px; overflow-y: auto; background: #f9f9f9; }
            .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
            .user-message { background: #007bff; color: white; text-align: right; }
            .assistant-message { background: #e9ecef; }
            .code-block { background: #2d3748; color: #e2e8f0; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; }
            .result-block { background: #f0f8f0; border: 1px solid #4caf50; padding: 10px; border-radius: 5px; margin: 10px 0; }
            .error-block { background: #ffe6e6; border: 1px solid #f44336; padding: 10px; border-radius: 5px; margin: 10px 0; }
            input[type="text"] { width: 70%; padding: 10px; }
            button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .file-info { background: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <h1>🤖 R Data Analysis Chat Assistant</h1>
        
        <div class="container">
            <div class="upload-section">
                <h2>📁 Upload CSV Data</h2>
                <input type="file" id="csvFile" accept=".csv">
                <button onclick="uploadFile()">Upload</button>
                <div id="fileInfo"></div>
                <p><input type="password" id="apiKey" placeholder="API key (if required)" style="width: 90%; padding: 8px;"></p>
                
                <h3>💡 Example Prompts:</h3>
                <ul>
                    <li>"Show me the first few rows of data"</li>
                    <li>"Create a summary of all numeric columns"</li>
                    <li>"Make a histogram of the age column"</li>
                    <li>"Find correlations between variables"</li>
                    <li>"Create a scatter plot of X vs Y"</li>
                    <li>"Group by category and show means"</li>
                    <li>"Show me missing values"</li>
                    <li>"Create a boxplot for outlier detection"</li>
                </ul>
            </div>
            
            <div class="chat-section">
                <h2>💬 Chat with AI Data Analyst</h2>
                <div id="chatBox" class="chat-box"></div>
                <div style="margin-top: 10px;">
                    <input type="text" id="messageInput" placeholder="Ask me anything about your data..." onkeypress="handleKeyPress(event)">
                    <button onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>

        <script>
            let currentFile = null;
            
            function escapeHtml(value) {
                return String(value ?? '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            }
            
            function authHeaders(extra = {}) {
                const key = document.getElementById('apiKey').value;
                return key ? { ...extra, 'X-API-Key': key } : extra;
            }
            
            function errorDetail(result) {
                return typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail);
            }
            
            async function uploadFile() {
                const fileInput = document.getElementById('csvFile');
                const file = fileInput.files[0];
                
                if (!file) {
                    alert('Please select a CSV file');
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const response = await fetch('/upload-csv', {
                        method: 'POST',
                        headers: authHeaders(),
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        currentFile = result.filename;
                        document.getElementById('fileInfo').innerHTML = `
                            <div class="file-info">
                                <strong>✅ File uploaded:</strong> ${escapeHtml(result.filename)}<br>
                                <strong>Rows:</strong> ${escapeHtml(result.rows)}<br>
                                <strong>Columns:</strong> ${escapeHtml(result.columns.join(', '))}
                            </div>
                        `;
                        addMessage('system', `File "${escapeHtml(result.filename)}" uploaded successfully! You can now ask me questions about your data.`);
                    } else {
                        alert('Upload failed: ' + errorDetail(result));
                    }
                } catch (error) {
                    alert('Upload error: ' + error.message);
                }
            }
            
            async function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (!message) return;
                if (!currentFile) {
                    alert('Please upload a CSV file first');
                    return;
                }
                
                addMessage('user', message);
                input.value = '';
                
                // Show loading
                addMessage('assistant', '🤔 Thinking and generating R code...');
                
                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: authHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({
                            message: message,
                            session_id: 'default'
                        })
                    });
                    
                    const result = await response.json();
                    
                    // Remove loading message
                    const chatBox = document.getElementById('chatBox');
                    chatBox.removeChild(chatBox.lastChild);
                    
                    if (response.ok) {
                        let responseHtml = escapeHtml(result.response);
                        
                        if (result.r_code) {
                            responseHtml += `<div class="code-block">📝 Generated R Code:<br><pre>${escapeHtml(result.r_code)}</pre></div>`;
                        }
                        
                        if (result.execution_result) {
                            if (result.execution_result.success) {
                                responseHtml += `<div class="result-block">📊 Results:<br><pre>${escapeHtml(result.execution_result.output)}</pre></div>`;
                                
                                // Add plot if available
                                if (result.plot_filename) {
                                    responseHtml += `<div class="result-block">📈 Generated Plot:<br><img src="/plots/${encodeURIComponent(result.plot_filename)}" style="max-width: 100%; height: auto;" alt="Generated plot"></div>`;
                                }
                            } else {
                                responseHtml += `<div class="error-block">❌ Execution Error:<br><pre>${escapeHtml(result.execution_result.error)}</pre></div>`;
                            }
                        }
                        
                        addMessage('assistant', responseHtml);
                    } else {
                        addMessage('assistant', '❌ Error: ' + escapeHtml(errorDetail(result)));
                    }
                } catch (error) {
                    const chatBox = document.getElementById('chatBox');
                    chatBox.removeChild(chatBox.lastChild);
                    addMessage('assistant', '❌ Connection error: ' + escapeHtml(error.message));
                }
            }
            
            function addMessage(sender, message) {
                const chatBox = document.getElementById('chatBox');
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + (sender === 'user' ? 'user-message' : 'assistant-message');
                messageDiv.innerHTML = message;
                chatBox.appendChild(messageDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }
            
            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            }
        </script>
    </body>
    </html>
    """

@app.post("/upload-csv", dependencies=[Depends(require_api_key)])
async def upload_csv(file: UploadFile = File(...)):
    """Upload a CSV file for analysis"""
    filename = safe_csv_filename(file.filename)
    file_path = str(resolve_inside(UPLOAD_DIR, filename))
    
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Read and analyze CSV
        df = pd.read_csv(file_path)
        
        # Store file info in session
        file_info = {
            "filename": filename,
            "path": file_path,
            "rows": len(df),
            "columns": list(df.columns),
            "column_types": {col: str(df[col].dtype) for col in df.columns},
            "sample_data": df.head(3).to_dict('records') if len(df) > 0 else []
        }
        
        # Store in default session (you could make this user-specific)
        chat_sessions["default"] = {
            "file_info": file_info,
            "chat_history": []
        }
        
        return file_info
    
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Error processing CSV: {str(e)}")

@app.post("/chat", dependencies=[Depends(require_api_key)])
async def chat_with_ai(chat_msg: ChatMessage):
    """Chat endpoint - generates R code using Google Generative AI and executes it"""
    
    session_id = chat_msg.session_id
    user_message = chat_msg.message
    
    # Check if we have a file uploaded
    if session_id not in chat_sessions:
        raise HTTPException(status_code=400, detail="No CSV file uploaded. Please upload a file first.")
    
    session = chat_sessions[session_id]
    file_info = session["file_info"]
    
    # Add user message to history
    session["chat_history"].append({"role": "user", "content": user_message})
    
    try:
        # Check if Google API key is configured
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY not found in environment variables")
            return ChatResponse(
                response="Google API key not configured. Please check your environment variables.",
                error="Missing GOOGLE_API_KEY"
            )
        
        # Generate R code using Google Generative AI
        r_code = await generate_r_code_with_gemini(user_message, file_info, session["chat_history"])
        
        if not r_code:
            return ChatResponse(
                response="I'm not sure how to help with that. Try asking about data summaries, visualizations, or specific analyses.",
                error="Could not generate appropriate R code"
            )
        
        # Execute the R code
        execution_result = await execute_r_code_internal(r_code, file_info["path"])
        
        # Generate response and check for plots
        plot_filename = None
        if execution_result["success"]:
            # Check if a plot was created
            output = execution_result["output"]
            if "PLOT_CREATED:" in output:
                plot_match = re.search(r"PLOT_CREATED: (plots/[^\s]+)", output)
                if plot_match:
                    plot_filename = plot_match.group(1).split('/')[-1]  # Get just the filename
            response_text = f"I've analyzed your data! Here's what I found:"
        else:
            response_text = f"I generated R code but encountered an error during execution. Let me show you what happened:"
        
        # Add to chat history
        session["chat_history"].append({
            "role": "assistant", 
            "content": response_text,
            "r_code": r_code,
            "execution_result": execution_result
        })
        
        return ChatResponse(
            response=response_text,
            r_code=r_code,
            execution_result=execution_result,
            plot_filename=plot_filename
        )
    
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chat processing error: {str(e)}")

async def generate_r_code_with_gemini(user_message: str, file_info: dict, chat_history: list) -> str:
    """Generate R code using Google Generative AI (Gemini)"""
    try:
        # Prepare context about the dataset
        dataset_context = f"""
Dataset Information:
- Filename: {file_info['filename']}
- Rows: {file_info['rows']}
- Columns: {file_info['columns']}
- Column Types: {file_info['column_types']}

Sample Data (first 3 rows):
{json.dumps(file_info['sample_data'], indent=2)}
"""
        
        # Prepare chat history context (last 5 messages)
        history_context = ""
        if chat_history:
            recent_history = chat_history[-5:]  # Last 5 exchanges
            for msg in recent_history:
                if msg["role"] == "user":
                    history_context += f"User: {msg['content']}\n"
                elif msg["role"] == "assistant":
                    history_context += f"Assistant: {msg['content']}\n"
        
        # Create the system prompt
        system_prompt = f"""You are an expert R data analyst. Your task is to generate R code based on user requests.

IMPORTANT RULES:
1. The CSV file is located at 'uploads/{file_info['filename']}'
2. Always start by reading the data: data <- read.csv('uploads/{file_info['filename']}')
3. Generate clean, executable R code
4. Add helpful comments
5. Handle potential errors gracefully
6. For plots, use base R graphics (avoid ggplot2 unless specifically requested)
7. Always print or display results explicitly with print() or cat()
8. Keep code concise but comprehensive
9. Use proper R syntax and functions

{dataset_context}

Previous conversation context:
{history_context}

Generate ONLY the R code, no additional explanation."""

        # Create the full prompt
        full_prompt = f"{system_prompt}\n\nPlease generate R code for this request: {user_message}"
        
        # Call Google Generative AI
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1000,
                temperature=0.3,  # Lower temperature for more consistent code generation
            )
        )
        
        r_code = response.text.strip()
        
        # Clean up the code (remove markdown formatting if present)
        if r_code.startswith("```r"):
            r_code = r_code[4:]
        elif r_code.startswith("```R"):
            r_code = r_code[4:]
        elif r_code.startswith("```"):
            r_code = r_code[3:]
        if r_code.endswith("```"):
            r_code = r_code[:-3]
        
        return r_code.strip()
    
    except Exception as e:
        logger.error(f"Google Generative AI error: {str(e)}")
        # Fallback to simple rule-based generation
        return generate_fallback_r_code(user_message, file_info)

def generate_fallback_r_code(user_message: str, file_info: dict) -> str:
    """Fallback R code generation when Google Generative AI fails"""
    message_lower = user_message.lower()
    filename = file_info["filename"]
    
    if any(word in message_lower for word in ["head", "first", "top", "preview", "show"]):
        return f"""
# Show first few rows
data <- read.csv('uploads/{filename}')
print("Dataset preview:")
head(data)
"""
    elif any(word in message_lower for word in ["summary", "describe", "statistics"]):
        return f"""
# Data summary
data <- read.csv('uploads/{filename}')
cat("Dataset Summary\\n")
cat("==============\\n")
summary(data)
cat("\\nDataset shape:", nrow(data), "rows,", ncol(data), "columns\\n")
"""
    else:
        return f"""
# Data overview
data <- read.csv('uploads/{filename}')
cat("Dataset Overview\\n")
cat("================\\n")
cat("Filename: {filename}\\n")
cat("Rows:", nrow(data), "\\n")
cat("Columns:", ncol(data), "\\n")
cat("\\nColumn names:\\n")
print(names(data))
cat("\\nFirst few rows:\\n")
head(data)
"""

async def execute_r_code_internal(r_code: str, csv_path: str) -> dict:
    """Execute R code and return results"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.R', delete=False) as temp_r_file:
        r_script_content = f"""
# Working directory is set by the caller (project root)
dir.create('plots', showWarnings = FALSE)

# Load required libraries quietly
suppressPackageStartupMessages({{
    library(utils)
}})

# Capture plots
plot_file <- paste0('plots/plot_', format(Sys.time(), '%Y%m%d_%H%M%S'), '.png')
png(plot_file, width = 800, height = 600)

# User's R code
{r_code}

# Close plot device
dev.off()

# Check if plot was created
if (file.exists(plot_file)) {{
    cat("\\nPLOT_CREATED:", plot_file, "\\n")
}}
"""
        temp_r_file.write(r_script_content)
        temp_r_script_path = temp_r_file.name
    
    try:
        result = subprocess.run(
            ['Rscript', temp_r_script_path],
            capture_output=True,
            text=True,
            timeout=R_TIMEOUT_SECONDS,
            cwd=BASE_DIR,
            env=_r_sandbox_env(),
            preexec_fn=_limit_r_resources if os.name == "posix" else None
        )
        
        os.unlink(temp_r_script_path)
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
            "return_code": result.returncode
        }
    
    except subprocess.TimeoutExpired:
        os.unlink(temp_r_script_path)
        return {
            "success": False,
            "error": f"R script execution timed out ({R_TIMEOUT_SECONDS}s limit)",
            "return_code": -1
        }
    except Exception as e:
        if os.path.exists(temp_r_script_path):
            os.unlink(temp_r_script_path)
        return {
            "success": False,
            "error": f"Execution error: {str(e)}",
            "return_code": -1
        }

@app.get("/plots/{filename}")
async def get_plot(filename: str):
    """Serve plot images"""
    plot_path = resolve_inside(PLOTS_DIR, filename)
    if plot_path.suffix.lower() != ".png" or not plot_path.is_file():
        raise HTTPException(status_code=404, detail="Plot not found")
    
    return FileResponse(plot_path, media_type="image/png")

@app.get("/sessions/{session_id}/history", dependencies=[Depends(require_api_key)])
async def get_chat_history(session_id: str):
    """Get chat history for a session"""
    if session_id not in chat_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"history": chat_sessions[session_id]["chat_history"]}

@app.get("/list-files", dependencies=[Depends(require_api_key)])
async def list_uploaded_files():
    """List all uploaded CSV files"""
    try:
        files = []
        upload_dir = UPLOAD_DIR
        
        for file_path in upload_dir.glob("*.csv"):
            stat = file_path.stat()
            files.append({
                "filename": file_path.name,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime
            })
        
        return {"files": files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

# Import the simplified MCP tools
from mcp_tools import setup_mcp_integration

# Add MCP integration to your existing app
mcp_setup_success = setup_mcp_integration(app, execute_r_code_internal, chat_sessions, auth_dependency=require_mcp_api_key)

if mcp_setup_success:
    logger.info("✅ MCP endpoints available at: /mcp/tools, /mcp/call/{tool_name}, /mcp/info")
else:
    logger.warning("❌ MCP integration failed - continuing without MCP support")
if __name__ == "__main__":
    import uvicorn
    # Localhost by default; set HOST=0.0.0.0 only behind authentication or a trusted network
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))