from typing import List
import html
import asyncio
from pydantic_models import Product
from pydantic_ai_agents import Chatbot
import pydantic_ai_agents
import json
import fastapi
import uvicorn
import logging
import sys
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, WebSocket
# from starlette.middleware.cors import CORSMiddleware

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.websocket('/ws/chat')
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    user_id = id(ws) 
    logger.info(f'New Websocket Connection: {user_id}')
    chatbot = Chatbot(top_k=12, ws=ws)
    
    async def handle_chat(user_query: id):
        try:
            resp = await chatbot.chat(user_query)
            await ws.send_json({
                'type': 'response',
                'message': resp.output.message,
                'products': [p.model_dump() for p in resp.output.products if p],
                'recc': resp.output.recommended.model_dump(),
                'flow': resp.output.flow,
                'steps': resp.output.steps
            })
            logger.info('Sending ackChat ...')
            await ws.send_json({    
                "type": "ackChat",
                "message": "Chat complete"
            })
            logger.info('Sent ackChat !')                
        except Exception as e:
            logger.error(f'chat oopsie: {e}')
            await ws.send_json({
            "type": "error",
            "message": f"{e}"
        })
    
    try: 
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg['type'] == 'chat':
                user_query = msg['content']
                asyncio.create_task(handle_chat(user_query))
            elif msg['type'] == 'prompt_response':
                prompt_id = msg.get('prompt_id')
                isRec = chatbot.coach.set_userResp(msg['content'], prompt_id)
                await ws.send_json({
                    "type": "ackPromptUser",
                    "message": "Response received" if isRec else "No matching prompt :("
                })
                
    except fastapi.WebSocketDisconnect:
        logger.error(f'Websocket disconnected: {user_id}')
    except Exception as e:
        logger.error(f'Oops: {e}')
    finally:
        await ws.close()

# @app.get('/')
# async def home():
#     """Home Page Frontend"""
#     html_content = """
#     """
#     return fastapi.responses.HTMLResponse(html_content)
app.mount("/", StaticFiles(directory='static', html=True), name='static')

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)