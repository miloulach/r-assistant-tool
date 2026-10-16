# R Chat Assistant Tool

An AI-powered web application that allows users to analyze CSV data through natural language conversations. 
The tool generates R code using Google's Gemini 2.0 Flash model, executes it, and provides results including visualizations.

## Features

- **Natural Language Data Analysis**: Ask questions about your data in plain English
- **AI-Generated R Code**: Automatically generates appropriate R code for your analysis requests
- **Interactive Web Interface**: Clean, user-friendly chat interface
- **Data Visualization**: Generates and displays plots directly in the browser
- **Download Capabilities**: Save R code, results, plots, and full session reports
- **MCP Integration**: Expose R analysis functions through Model Context Protocol endpoints
- **Session Management**: Maintains conversation context for follow-up questions

## Quick Start

### Prerequisites

- Python 3.11+
- R (version 4.0+)
- Google API key for Gemini 2.0 Flash

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/miloulach/r-assistant-tool.git
   cd r-assistant-tool
   ```

2. **Set up Python environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install R and system dependencies**
   ```bash
   sudo apt-get update
   sudo apt-get install -y r-base pandoc
   ```

4. **Install R packages**
   ```bash
   Rscript install_packages.R
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY
   ```

6. **Run the application**
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

7. **Access the application**
   Open your browser to `http://localhost:8000`

## Usage

### Web Interface

1. **Upload your CSV file** using the file upload section
2. **Ask questions** about your data in natural language:
   - "Show me the first few rows"
   - "Create a histogram of the age column"
   - "What's the correlation between price and sales?"
   - "Group by category and show means"
3. **View results** including generated R code, output, and plots
4. **Download** individual components or complete session reports

### Example Queries

```
"Create a summary of all numeric columns"
"Make a scatter plot of height vs weight"
"Show me missing values in the dataset"
"Calculate the mean age by gender"
"Create a boxplot for outlier detection"
"Find correlations between all variables"
```

### MCP Integration

The tool exposes R analysis capabilities through MCP endpoints:

- `GET /mcp/tools` - List available MCP tools
- `POST /mcp/call/execute_r_code` - Execute R code directly
- `POST /mcp/call/analyze_csv_data` - Analyze CSV data with custom R code
- `POST /mcp/call/get_basic_stats` - Calculate basic statistics
- `GET /mcp/info` - Server information

`/mcp/call/*` runs arbitrary R code, so it is disabled until `APP_API_KEY` is set and every call must send the key in the `X-API-Key` header.

#### MCP Usage Example

```bash
curl -X POST "http://localhost:8000/mcp/call/execute_r_code" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: $APP_API_KEY" \
     -d '{"code": "summary(mtcars)", "session_id": "test"}'
```

## Configuration

### Environment Variables

Create a `.env` file with:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
APP_API_KEY=change_me_to_a_long_random_string
HOST=127.0.0.1
PORT=8000
R_TIMEOUT_SECONDS=30
R_MAX_MEMORY_MB=2048
R_MAX_FILE_MB=100
```

| Variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key |
| `APP_API_KEY` | Enables `/mcp/call/*` and, when set, is required (header `X-API-Key`) on `/upload-csv`, `/chat`, `/list-files` and `/sessions/*`. The web UI has a field for it. |
| `HOST` / `PORT` | Bind address for `python main.py` (defaults to `127.0.0.1:8000`) |
| `R_TIMEOUT_SECONDS`, `R_MAX_MEMORY_MB`, `R_MAX_FILE_MB` | CPU time, memory and output-file limits for each R run |

### Supported File Types

- CSV files (.csv)
- TSV files (through CSV endpoints)
- Maximum file size: 50MB

## Project Structure

```
r-assistant-tool/
├── main.py              # FastAPI application and web interface
├── mcp_tools.py         # MCP integration tools
├── install_packages.R   # R package installation script
├── requirements.txt     # Python dependencies
├── .env.example         # Template for .env (copy and fill in)
├── uploads/             # Uploaded CSV files
├── plots/               # Generated visualizations
├── results/             # Analysis results
└── temp/                # Temporary files
```

## API Endpoints

### Web Interface
- `GET /` - Main chat interface
- `POST /upload-csv` - Upload CSV files
- `POST /chat` - Process chat messages
- `GET /plots/{filename}` - Serve plot images
- `GET /download-plot/{filename}` - Download plots
- `GET /download-session-report/{session_id}` - Download session reports

### MCP Endpoints
- `GET /mcp/tools` - List MCP tools
- `POST /mcp/call/{tool_name}` - Execute MCP tools
- `GET /mcp/info` - MCP server information

## Dependencies

### Python Packages
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pandas` - Data manipulation
- `google-generativeai` - Gemini AI integration
- `python-dotenv` - Environment variable management
- `aiofiles` - Async file operations

### R Packages
- `utils`, `graphics`, `stats` - Base R functionality
- Additional packages installed via `install_packages.R`

## Development

### Running in Development Mode
```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Adding New MCP Tools
1. Add tool function to `RAnalysisMCPTools` class in `mcp_tools.py`
2. Register the tool in `create_mcp_endpoints()` function
3. Update tool list in `/mcp/tools` endpoint

## Limitations

- R code execution has a 30-second timeout (configurable)
- File uploads limited to 50MB
- Sessions are stored in memory (not persistent across restarts)
- MCP integration uses HTTP endpoints (not native MCP protocol)

## Security Considerations

**Warning**: This tool executes AI-generated R code automatically. Only use with trusted data sources and in controlled environments. 
Consider implementing additional sandboxing for production use.

- The server binds to `127.0.0.1` by default; only expose it (`HOST=0.0.0.0`) with `APP_API_KEY` set
- MCP code execution is off unless `APP_API_KEY` is set
- Each R run gets CPU, memory and file-size limits and a minimal environment (API keys are not passed to R)
- Uploaded file names are sanitised and plot/file paths are confined to their directories
- Model and R output are HTML-escaped in the chat UI
- R itself is **not** fully sandboxed: generated code can still call `system()` or read files the server user can read. For shared or public deployments, run the app in a container as an unprivileged user

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

## Troubleshooting

### Common Issues

1. **R packages not installing**
   - Ensure R is properly installed and accessible via command line
   - Check that `install_packages.R` exists and has proper permissions

2. **Google API errors**
   - Verify your API key is correct and has Gemini API access enabled
   - Check API quota and rate limits

3. **File upload issues**
   - Ensure uploaded files are valid CSV format
   - Check file size limits (50MB maximum)

4. **Port conflicts**
   - Change the port in the uvicorn command if 8000 is already in use

### Getting Help

- Check the [Issues](https://github.com/miloulach/r-assistant-tool/issues) page for known problems
- Create a new issue with detailed error messages and system information
- Include relevant log output when reporting bugs

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- AI integration via [Google Gemini 2.0 Flash](https://ai.google.dev/)
- R statistical computing environment
- Model Context Protocol for tool integration
