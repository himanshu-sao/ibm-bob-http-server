#!/usr/bin/env python3
"""
IBM BOB HTTP Server - Exposed as OpenAI-Compatible API

This server wraps IBM BOB Shell and exposes it through an OpenAI-compatible HTTP API.
Think of it like Ollama or LM Studio's API format.
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

app = FastAPI(title="IBM BOB HTTP Server", version="0.1.0")

# CORS - Allow common clients like LM Studio, etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BOB_PATH = os.getenv("BOB_PATH", "bob")
LOG_DIR = Path.home() / ".local" / "share" / "ibm-bob-http-server"
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


# Available models (BOB Shell in different modes)
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
    
    logger.info(f"Listed {len(models)} models")
    return {
        "object": "list",
        "data": models
    }

@app.get("/models", response_model=ListModelsResponse)
async def list_models_simple():
    """Alias for /v1/models"""
    return await list_models()

@app.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ibm-bob-ollama-api",
        "models": [model["id"] for model in BOB_MODELS.values()],
        "timestamp": int(time.time())
    }

@app.get("/")
async def root():
    return {
        "name": "IBM BOB Ollama API",
        "version": "0.1.0",
        "models": list(BOB_MODELS.keys()),
        "endpoints": [
            "/v1/models",
            "/v1/chat/completions",
            "/v1/completions",
            "/health",
            "/docs"
        ]
    }

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Chat completions endpoint (OpenAI format)"""
    model_config = None
    
    # Find the model config
    for model_id, config in BOB_MODELS.items():
        if model_id == request.model or config["id"] == request.model:
            model_config = config
            break
    
    if not model_config:
        logger.error(f"Model not found: {request.model}")
        raise HTTPException(status_code=404, detail={"error": {"message": f"Model '{request.model}' not found", "type": "invalid_request_error", "param": "model", "code": "model_not_found"}})
    
    logger.info(f"Chat completion requested for model: {request.model}")
    
    # Build the prompt from messages
    prompt_parts = []
    for message in request.messages:
        if message.role == "user":
            prompt_parts.append(message.content)
        elif message.role == "system":
            prompt_parts.append(f"System: {message.content}")
        elif message.role == "assistant":
            prompt_parts.append(f"Assistant: {message.content}")
    
    # Combine messages into a single prompt
    prompt = "\n".join(prompt_parts)
    
    if not prompt or len(prompt.strip()) == 0:
        logger.error("No valid prompt provided")
        raise HTTPException(status_code=400, detail={"error": {"message": "No prompt provided", "type": "invalid_request_error"}})
    
    try:
        # Execute BOB Shell command
        result = subprocess.run(
            [BOB_PATH, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # Check for authentication errors in stderr
        full_output = result.stdout + result.stderr
        
        if "IBMid" in full_output or "login" in full_output.lower():
            logger.warning("BOB authentication required")
            raise HTTPException(status_code=401, detail={
                "error": {
                    "message": "IBM BOB Shell requires authentication. Please run 'bob' manually to authenticate first.",
                    "type": "authentication_error",
                }
            })
        
        # Construct the response
        response_data = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_config["id"],
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.stdout
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": len(result.stdout.split()),
                "total_tokens": 150
            }
        }
        
        logger.info(f"Returned {len(result.stdout)} characters from BOB")
        return response_data
        
    except subprocess.TimeoutExpired:
        logger.error("BOB execution timed out")
        raise HTTPException(status_code=408, detail={"error": {"message": "Command timed out", "type": "timeout_error"}})
    
    except Exception as e:
        logger.error(f"BOB execution failed: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(e), "type": "server_error"}})

@app.post("/v1/completions")
async def completions(request: Dict[str, Any]):
    """Simple completions endpoint"""
    prompt = request.get("prompt")
    model = request.get("model")
    
    if not prompt:
        raise HTTPException(status_code=400, detail={"error": {"message": "Prompt is required"}})
    
    try:
        result = subprocess.run(
            [BOB_PATH, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if "IBMid" in result.stderr or "login" in result.stderr.lower():
            raise HTTPException(status_code=401, detail={
                "error": {
                    "message": "IBM BOB Shell requires authentication. Please run 'bob' manually to authenticate first.",
                }
            })
        
        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": model or "ibm-bob",
            "choices": [{
                "text": result.stdout,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": len(result.stdout.split()),
                "total_tokens": 100
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})


def format_ollama_model(model_id: str) -> Dict[str, Any]:
    """Format model for Ollama compatibility"""
    config = BOB_MODELS.get(model_id)
    if not config:
        model_id = "ibm-bob-ollama"
        config = BOB_MODELS[model_id]
    
    return {
        "name": config["id"],
        "model": config["id"],
        "familiy": "IBM BOB",
        "parameter_size": "medium",
        "quantization": "none",
        "context_length": config["context_window"],
        "description": config["description"],
    }

@app.get("/api/tags")
async def ollama_tags():
    """Ollama-compatible tags endpoint"""
    models = []
    for model_id in BOB_MODELS.keys():
        models.append(format_ollama_model(model_id))
    return {"models": models}

@app.get("/api/show/{model_id}")
async def ollama_show(model_id: str):
    """Ollama-compatible show endpoint"""
    config = BOB_MODELS.get(model_id)
    if not config:
        config = BOB_MODELS.get("ibm-bob-ollama")
    
    return {
        "name": config["id"],
        "modelfile": f"# BOB Shell Model\nFROM ibm-bob\nPARAMETER temperature {0.7}",
        "parameters": {
            "temperature": 0.7,
            "top_p": 1.0,
            "seed": None,
        },
        "template": "{{ .Prompt }}\nAssistant: ",
        "details": {
            "parent_model": "",
            "format": "tgz",
            "family": "IBM BOB",
            "parameter_size": "medium",
            "quantization_level": "none"
        }
    }


if __name__ == "__main__":
    logger.info("="*60)
    logger.info("Starting IBM BOB HTTP Server (Ollama/LM Studio compatible)")
    logger.info("="*60)
    logger.info(f"Serving on: http://0.0.0.0:31013")
    logger.info(f"Models: {list(BOB_MODELS.keys())}")
    logger.info(f"BOB Path: {BOB_PATH}")
    logger.info("="*60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=31013,
        log_config=None,
        timeout_keep_alive=30
    )