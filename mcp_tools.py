# mcp_tools.py - Simplified version
import json
import tempfile
import os
import asyncio
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class RAnalysisMCPTools:
    """Simple MCP tools wrapper for R Analysis functions"""
    
    def __init__(self, r_executor_func, chat_sessions_store):
        self.execute_r_code = r_executor_func
        self.chat_sessions = chat_sessions_store
        
    async def execute_r_code_tool(self, code: str, session_id: str = "mcp_session") -> Dict[str, Any]:
        """Execute R code through MCP"""
        try:
            result = await self.execute_r_code(code, None)
            return {
                "success": result["success"],
                "output": result["output"],
                "error": result.get("error"),
                "session_id": session_id
            }
        except Exception as e:
            logger.error(f"MCP R execution error: {e}")
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}",
                "output": None,
                "session_id": session_id
            }

    async def analyze_csv_data_tool(self, csv_content: str, analysis_code: str) -> Dict[str, Any]:
        """Analyze CSV data provided as string"""
        try:
            # Create temporary CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                temp_file.write(csv_content)
                temp_path = temp_file.name

            # Modify R code to use the temp file
            r_code = f"""
# Read the provided CSV data
data <- read.csv('{temp_path}')

# User's analysis code
{analysis_code}
"""
            
            result = await self.execute_r_code(r_code, temp_path)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            
            return {
                "success": result["success"],
                "output": result["output"],
                "error": result.get("error")
            }
            
        except Exception as e:
            logger.error(f"MCP CSV analysis error: {e}")
            return {
                "success": False,
                "error": f"CSV analysis failed: {str(e)}",
                "output": None
            }

    async def get_basic_stats_tool(self, data: List[float]) -> Dict[str, Any]:
        """Calculate basic statistics"""
        try:
            data_str = ",".join(map(str, data))
            r_code = f"""
data_vector <- c({data_str})
cat("Basic Statistics:\\n")
cat("Mean:", mean(data_vector), "\\n")
cat("Median:", median(data_vector), "\\n") 
cat("Standard Deviation:", sd(data_vector), "\\n")
cat("Min:", min(data_vector), "\\n")
cat("Max:", max(data_vector), "\\n")
cat("Length:", length(data_vector), "\\n")
"""
            result = await self.execute_r_code(r_code, None)
            return {
                "success": result["success"],
                "output": result["output"],
                "statistics": {
                    "count": len(data),
                    "mean": sum(data) / len(data) if data else 0,
                    "min": min(data) if data else 0,
                    "max": max(data) if data else 0
                } if result["success"] else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Statistics calculation failed: {str(e)}"
            }

# Simple HTTP-based MCP interface (instead of stdio)
def create_mcp_endpoints(app, r_tools: RAnalysisMCPTools):
    """Add MCP-like endpoints to FastAPI app"""
    
    @app.get("/mcp/tools")
    async def list_mcp_tools():
        """List available MCP tools"""
        return {
            "tools": [
                {
                    "name": "execute_r_code",
                    "description": "Execute R code and return results",
                    "parameters": {
                        "code": "string - R code to execute",
                        "session_id": "string - Session ID (optional)"
                    }
                },
                {
                    "name": "analyze_csv_data", 
                    "description": "Analyze CSV data with R code",
                    "parameters": {
                        "csv_content": "string - CSV data as string",
                        "analysis_code": "string - R code for analysis"
                    }
                },
                {
                    "name": "get_basic_stats",
                    "description": "Get basic statistics for numeric data",
                    "parameters": {
                        "data": "array of numbers - Data to analyze"
                    }
                }
            ]
        }
    
    @app.post("/mcp/call/{tool_name}")
    async def call_mcp_tool(tool_name: str, arguments: dict):
        """Call an MCP tool"""
        try:
            if tool_name == "execute_r_code":
                result = await r_tools.execute_r_code_tool(
                    code=arguments["code"],
                    session_id=arguments.get("session_id", "mcp_session")
                )
            elif tool_name == "analyze_csv_data":
                result = await r_tools.analyze_csv_data_tool(
                    csv_content=arguments["csv_content"],
                    analysis_code=arguments["analysis_code"]
                )
            elif tool_name == "get_basic_stats":
                result = await r_tools.get_basic_stats_tool(
                    data=arguments["data"]
                )
            else:
                result = {"success": False, "error": f"Unknown tool: {tool_name}"}
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.get("/mcp/info")
    async def mcp_server_info():
        """MCP server information"""
        return {
            "name": "r-analysis-server",
            "version": "1.0.0",
            "description": "R Data Analysis MCP Server",
            "tools_count": 3
        }

def setup_mcp_integration(app, execute_r_func, chat_sessions):
    """Setup MCP integration with your FastAPI app"""
    try:
        # Create MCP tools
        r_tools = RAnalysisMCPTools(execute_r_func, chat_sessions)
        
        # Add MCP endpoints to your existing FastAPI app
        create_mcp_endpoints(app, r_tools)
        
        logger.info("MCP integration setup complete - endpoints available at /mcp/*")
        return True
        
    except Exception as e:
        logger.error(f"MCP setup failed: {e}")
        return False