import asyncio
import websockets
import json
from datetime import datetime

connected_clients = {}
chat_rooms = {
    "#geral": set(),
    "#python": set(),
    "#jogos": set()
}

room_messages = {
    "#geral": [],
    "#python": [],
    "#jogos": []
}

user_avatars = {}

async def handle_connection(websocket):
    client_id = id(websocket)
    connected_clients[client_id] = {
        "websocket": websocket,
        "nickname": None,
        "room": None,
        "avatar": None
    }

    print(f"Novo cliente conectado: {client_id}")
    print(f"Total de clientes conectados: {len(connected_clients)}")

    try:   
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"Mensagem recebida de {client_id}: {data['type']}")
                await handle_message(data, client_id)
            except json.JSONDecodeError as e:
                print(f"Erro ao decodificar JSON: {e}")
            except Exception as e:
                print(f"Erro ao processar mensagem: {e}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Conexão fechada: {client_id}")
    except Exception as e:
        print(f"Erro inesperado na conexão: {e}")
    finally:
        await handle_disconnection(client_id)

async def handle_message(data, client_id):
    try:
        client = connected_clients.get(client_id)
        if not client:
            print(f"Cliente {client_id} não encontrado")
            return

        message_type = data["type"]

        if message_type == "user_join":
            await handle_user_join(client, data)
        elif message_type == "join":
            await handle_join(client, data)
        elif message_type == "message":
            await handle_chat_message(client, data)
        elif message_type == "list_rooms":
            await send_room_list(client)
        else:
            print(f"Tipo de mensagem desconhecido: {message_type}")
    except Exception as e:
        print(f"Erro em handle_message: {e}")

async def handle_user_join(client, data):
    try:
        nickname = data["nickname"]
        avatar = data.get("avatar")
        
        print(f"Registrando usuário: {nickname}")
        
        client["nickname"] = nickname
        client["avatar"] = avatar
        
        if avatar and nickname:
            user_avatars[nickname] = avatar
        
        print(f"Usuário {nickname} registrado com sucesso")
        
        await send_room_list(client)
        
        await send_all_users_list()
        
    except Exception as e:
        print(f"Erro em handle_user_join: {e}")

async def handle_join(client, data):
    try:
        old_room = client["room"]
        new_room = data["room"]
        nickname = data["nickname"]
        avatar = data.get("avatar")

        print(f"Usuário {nickname} entrando na sala {new_room}")

        if old_room and old_room in chat_rooms:
            if client["websocket"] in chat_rooms[old_room]:
                chat_rooms[old_room].remove(client["websocket"])
                if client["nickname"]:
                    await broadcast_user_left(old_room, client["nickname"])
                await send_user_list(old_room)

        if new_room not in chat_rooms:
            chat_rooms[new_room] = set()
            room_messages[new_room] = []
            print(f"Nova sala criada: {new_room}")
            await broadcast_room_list()

        client["room"] = new_room
        client["nickname"] = nickname
        client["avatar"] = avatar or user_avatars.get(nickname)
        chat_rooms[new_room].add(client["websocket"])

        if avatar and nickname:
            user_avatars[nickname] = avatar

        await send_room_history(client, new_room)
        await broadcast_user_joined(new_room, nickname)
        await send_user_list(new_room)
        await send_all_users_list()
        
        print(f"Usuário {nickname} entrou na sala {new_room} com sucesso")

    except Exception as e:
        print(f"Erro em handle_join: {e}")

async def send_room_history(client, room):
    try:
        if room in room_messages:
            history_message = {
                "type": "room_history",
                "messages": room_messages[room][-100:]
            }
            await client["websocket"].send(json.dumps(history_message))
    except Exception as e:
        print(f"Erro em send_room_history: {e}")

async def handle_chat_message(client, data):
    try:
        room = client["room"]
        if room and room in chat_rooms:
            message_data = {
                "type": "message",
                "nickname": client["nickname"],
                "content": data["content"],
                "timestamp": datetime.now().isoformat(),
                "avatar": client["avatar"]
            }
            
            room_messages[room].append(message_data)
            
            if len(room_messages[room]) > 100:
                room_messages[room] = room_messages[room][-100:]
            
            await broadcast_to_room(room, message_data)
    except Exception as e:
        print(f"Erro em handle_chat_message: {e}")

async def handle_disconnection(client_id):
    try:
        if client_id in connected_clients:
            client = connected_clients[client_id]
            
            for room_name, room_clients in chat_rooms.items():
                if client["websocket"] in room_clients:
                    room_clients.remove(client["websocket"])
                    if client["nickname"]:
                        await broadcast_user_left(room_name, client["nickname"])
                    await send_user_list(room_name)
            
            del connected_clients[client_id]
            print(f"Cliente desconectado: {client_id}")
            print(f"Total de clientes conectados: {len(connected_clients)}")
            
            await send_all_users_list()
    except Exception as e:
        print(f"Erro em handle_disconnection: {e}")

async def broadcast_user_joined(room, nickname):
    try:
        if room in chat_rooms:
            message = {
                "type": "notification",
                "content": f"{nickname} entrou na sala",
                "timestamp": datetime.now().isoformat()
            }
            await broadcast_to_room(room, message)
    except Exception as e:
        print(f"Erro em broadcast_user_joined: {e}")

async def broadcast_user_left(room, nickname):
    try:
        if room in chat_rooms:
            message = {
                "type": "notification",
                "content": f"{nickname} saiu da sala",
                "timestamp": datetime.now().isoformat()
            }
            await broadcast_to_room(room, message)
    except Exception as e:
        print(f"Erro em broadcast_user_left: {e}")

async def send_user_list(room):
    try:
        if room in chat_rooms:
            users = []
            for client_ws in chat_rooms[room]:
                for client_id, client_info in connected_clients.items():
                    if client_info["websocket"] == client_ws and client_info["room"] == room:
                        users.append({
                            "nickname": client_info["nickname"],
                            "avatar": client_info["avatar"]
                        })
                        break
            
            users.sort(key=lambda user: user["nickname"].lower())
            
            message = {
                "type": "users_list",
                "users": users
            }
            await broadcast_to_room(room, message)
    except Exception as e:
        print(f"Erro em send_user_list: {e}")

async def send_all_users_list():
    try:
        users = []
        for client_id, client_info in connected_clients.items():
            if client_info["nickname"]:
                users.append({
                    "nickname": client_info["nickname"],
                    "avatar": client_info["avatar"]
                })
        
        users.sort(key=lambda user: user["nickname"].lower())
        
        message = {
            "type": "all_users",
            "users": users
        }
        message_json = json.dumps(message)
        
        tasks = []
        for client_id, client_info in connected_clients.items():
            try:
                tasks.append(client_info["websocket"].send(message_json))
            except Exception as e:
                print(f"Erro ao enviar lista global para {client_id}: {e}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        print(f"Lista de usuários enviada: {[user['nickname'] for user in users]}")
    except Exception as e:
        print(f"Erro em send_all_users_list: {e}")

async def send_room_list(client):
    try:
        message = {
            "type": "rooms_list",
            "rooms": list(chat_rooms.keys())
        }
        await client["websocket"].send(json.dumps(message))
    except Exception as e:
        print(f"Erro em send_room_list: {e}")

async def broadcast_room_list():
    try:
        message = {
            "type": "rooms_list",
            "rooms": list(chat_rooms.keys())
        }
        message_json = json.dumps(message)
        
        tasks = []
        for client_id, client_info in connected_clients.items():
            try:
                tasks.append(client_info["websocket"].send(message_json))
            except Exception as e:
                print(f"Erro ao enviar para cliente {client_id}: {e}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"Erro em broadcast_room_list: {e}")

async def broadcast_to_room(room, message):
    try:
        if room in chat_rooms and chat_rooms[room]:
            message_json = json.dumps(message)
            tasks = []
            disconnected_clients = []
            
            for client in chat_rooms[room]:
                try:
                    tasks.append(client.send(message_json))
                except Exception as e:
                    print(f"Erro ao enviar mensagem: {e}")
                    disconnected_clients.append(client)
            
            for client in disconnected_clients:
                chat_rooms[room].remove(client)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"Erro em broadcast_to_room: {e}")

async def main():
    print("Iniciando servidor de chat na porta 8765...")
    try:
        async with websockets.serve(handle_connection, "localhost", 8765, ping_interval=20, ping_timeout=60):
            print("Servidor de chat rodando em ws://localhost:8765")
            await asyncio.Future()  # Mantém o servidor rodando
    except Exception as e:
        print(f"Erro ao iniciar servidor: {e}")

if __name__ == "__main__":
    asyncio.run(main())