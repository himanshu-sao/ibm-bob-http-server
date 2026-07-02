#!/usr/bin/env python3
"""
IBM BOB HTTP Server - Exposed as OpenAI and Ollama Compatible API

This server wraps IBM BOB Shell and exposes it through both OpenAI and Ollama HTTP API formats.
It ensures full harness compatibility by mapping API models to BOB chat-modes and 
enforcing non-interactive execution.
"""

import os
import json
import subprocess
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import logging
from pathlib import Path

app = FastAPI(title="IBM BOB HTTP Server", version="0.1.2")

# CORS - Allow common clients like LM Studio, Open WebUI, etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BOB_PATH = os.getenv("BOB_PATH", "bob")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ibm-bob-ollama-api")

class ListModelsResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[str] = None
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Optional[Dict] = None
    user: Optional[str] = None

# Available models mapped to BOB shell --chat-mode
BOB_MODELS = {
    "ibm-bob-ollama": {
        "id": "ibm-bob-ollama",
        "name": "IBM BOB (Ollama Mode)",
        "description": "IBM BOB Shell optimized for chat and code generation",
        "mode": "code",
        "context_window": 128000,
        "max_tokens": 4096,
    },
    "ibm-bob-chat": {
        "id": "ibm-bob-chat",
        "name": "IBM BOB Chat",
        "description": "IBM BOB Shell optimized for natural language chat",
        "mode": "ask",
        "context_window": 128000,
        "max_tokens": 4096,
    },
    "ibm-bob-code": {
        "id": "ibm-bob-code",
        "name": "IBM BOB Code",
        "description": "IBM BOB Shell optimized for code generation and analysis",
        "mode": "code",
        "context_window": 128000,
        "max_tokens": 8192,
    },
}

def estimate_tokens(text: str) -> int:
    """Simple approximation of tokens based on word count"""
    return int(len(text.split()) * 1.3) if text else 0

async def execute_bob_command(prompt: str, model_id: str = "ibm-bob-ollama") -> str:
    """
    Helper to execute the bob shell command with full harness compatibility.
    Translates model_id to --chat-mode and ensures non-interactive execution via --yolo.
    """
    config = BOB_MODELS.get(model_id, BOB_MODELS["ibm-bob-ollama"])
    mode = config["mode"]
    
    # Build command: bob --chat-mode <mode> --yolo <prompt>
    # Using positional prompt as -p is deprecated
    cmd = [BOB_PATH, "--chat-mode", mode, "--yolo", prompt]
    
    try:
        logger.info(f"Executing BOB: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        full_output = result.stdout + result.stderr
        if "IBMid" in full_output or "login" in full_output.lower():
            logger.warning("BOB authentication required")
            raise HTTPException(status_code=401, detail={
                "error": {
                    "message": "IBM BOB Shell requires authentication. Please run 'bob' manually to authenticate first.",
                    "type": "authentication_error",
                }
            })
        
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.error("BOB execution timed out")
        raise HTTPException(status_code=408, detail={"error": {"message": "Command timed out", "type": "timeout_error"}})
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"BOB execution failed: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(e), "type": "server_error"}})

@app.get("/v1/models", response_model=ListModelsResponse)
async def list_models():
    """List available models (OpenAI format)"""
    models = []
    for model_id, config in BOB_MODELS.items():
        models.append({
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "ibm",
            "name": config["name"],
            "description": config["description"],
            "context_length": config["context_window"],
            "input_price": "$0.0",
            "output_price": "$0.0",
        })
    return {"object": "list", "data": models}

@app.get("/models", response_model=ListModelsResponse)
async def list_models_simple():
    return await list_models()

@app.get("/health", response_model=Dict[str, Any])
async def health_check():
    return {
        "status": "healthy",
        "service": "ibm-bob-ollama-api",
        "models": list(BOB_MODELS.keys()),
        "timestamp": int(time.time())
    }

@app.get("/")
async def root():
    return {
        "name": "IBM BOB Ollama API",
        "version": "0.1.2",
        "models": list(BOB_MODELS.keys()),
        "endpoints": ["/v1/models", "/v1/chat/completions", "/api/generate", "/api/chat", "/health", "/docs"]
    }

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Chat completions endpoint (OpenAI format)"""
    model_config = BOB_MODELS.get(request.model)
    if not model_config:
        raise HTTPException(status_code=404, detail={"error": {"message": f"Model '{request.model}' not found"}})

    prompt_parts = []
    for message in request.messages:
        if message.role == "user": prompt_parts.append(message.content)
        elif message.role == "system": prompt_parts.append(f"System: {message.content}")
        elif message.role == "assistant": prompt_parts.append(f"Assistant: {message.content}")
    
    prompt = "\n".join(prompt_parts)
    if not prompt.strip():
        raise HTTPException(status_code=400, detail={"error": {"message": "No prompt provided"}})

    content = await execute_bob_command(prompt, request.model)
    
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_config["id"],
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(content),
            "total_tokens": estimate_tokens(prompt) + estimate_tokens(content)
        }
    }

@app.post("/v1/completions")
async def completions(request: Dict[str, Any]):
    prompt = request.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail={"error": {"message": "Prompt is required"}})
    
    model = request.get("model", "ibm-bob-ollama")
    content = await execute_bob_command(prompt, model)
    return {
        "id": f"cmpl-{int(time.time())}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"text": content, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(content),
            "total_tokens": estimate_tokens(prompt) + estimate_tokens(content)
        }
    }

# --- OLLAMA COMPATIBILITY LAYER ---

@app.get("/api/tags")
async def ollama_tags():
    """Ollama-compatible tags endpoint"""
    models = []
    for model_id, config in BOB_MODELS.items():
        models.append({
            "name": model_id,
            "model": model_id,
            "family": "IBM BOB",
            "parameter_size": "medium",
            "quantization": "none",
            "context_length": config["context_window"],
            "description": config["description"],
        })
    return {"models": models}

@app.get("/api/show/{model_id}")
async def ollama_show(model_id: str):
    config = BOB_MODELS.get(model_id, BOB_MODELS["ibm-bob-ollama"])
    return {
        "name": config["id"],
        "modelfile": f"# BOB Shell Model\nFROM ibm-bob\nPARAMETER temperature {0.7}",
        "parameters": {"temperature": 0.7, "top_p": 1.0},
        "template": "{{ .Prompt }}\nAssistant: ",
        "details": {"family": "IBM BOB", "parameter_size": "medium", "quantization_level": "none"}
    }

@app.post("/api/generate")
async def ollama_generate(request: Dict[str, Any]):
    """Ollama-compatible generation endpoint"""
    prompt = request.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    model = request.get("model", "ibm-bob-ollama")
    content = await execute_bob_command(prompt, model)
    
    return {
        "model": model,
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "response": content,
        "done": True,
        "context": [], 
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": estimate_tokens(prompt),
        "eval_count": estimate_tokens(content)
    }

@app.post("/api/chat")
async def ollama_chat(request: Dict[str, Any]):
    """Ollama-compatible chat endpoint"""
    messages = request.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="Messages are required")
    
    prompt_parts = [f"{m.get('role')}: {m.get('content')}" for m in messages]
    prompt = "\n".join(prompt_parts)
    
    model = request.get("model", "ibm-bob-ollama")
    content = await execute_bob_command(prompt, model)
    
    return {
        "model": model,
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "message": {"role": "assistant", "content": content},
        "done": True,
        "total_duration": 0,
        "prompt_eval_count": estimate_tokens(prompt),
        "eval_count": estimate_tokens(content)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=31013, log_config=None, timeout_keep_alive=30)
