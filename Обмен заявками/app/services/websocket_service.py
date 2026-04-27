import json
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Храним активные соединения по ролям: {"driver": [ws1, ws2], "admin": [ws3]}
        self.active_connections: dict[str, list[WebSocket]] = {
            "appraiser": [],
            "driver": [],
            "admin": []
        }

    async def connect(self, websocket: WebSocket, role: str):
        await websocket.accept()
        if role in self.active_connections:
            self.active_connections[role].append(websocket)

    def disconnect(self, websocket: WebSocket, role: str):
        if role in self.active_connections:
            if websocket in self.active_connections[role]:
                self.active_connections[role].remove(websocket)

    async def broadcast_to_role(self, role: str, message: dict):
        if role not in self.active_connections:
            return
        
        text_data = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections[role]:
            try:
                await connection.send_text(text_data)
            except Exception:
                dead_connections.append(connection)
                
        for dead in dead_connections:
            self.disconnect(dead, role)

    async def broadcast_to_roles(self, roles: list[str], message: dict):
        for role in roles:
            await self.broadcast_to_role(role, message)

manager = ConnectionManager()
