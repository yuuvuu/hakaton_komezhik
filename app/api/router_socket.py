from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from app.data import users, rooms, save_data
import logging
import asyncio
import json
import uuid
import secrets

logger = logging.getLogger(__name__)
router = APIRouter()

active_connections = {}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_room = None
    user_id = None
    try:
        token = await websocket.receive_text()
        logger.info(f"Received token: {token}")
        user_id = next((uid for uid, info in users.items() if info['token'] == token), None)
        if not user_id:
            logger.warning("Unauthorized token, closing connection")
            await websocket.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
            await websocket.close(code=1008)
            return

        active_connections[user_id] = websocket

        user_data = users[user_id]['data']
        default_name = user_data.get('username') or user_data.get('first_name') or f"User_{user_id}"

        if users[user_id]['nickname'] is None:
            modal_html = f"""
                <div id="modal" class="modal">
                    <div class="modal-content">
                        <h2>Welcome, {default_name}!</h2>
                        <p>Enter your nickname:</p>
                        <input type="text" id="nickname" value="{default_name}">
                        <p>Please enter your work schedule (e.g., 9:00-17:00):</p>
                        <input type="text" id="schedule" placeholder="e.g., 9:00-17:00">
                        <p>Add a description about yourself:</p>
                        <textarea id="description" placeholder="e.g., I love coding!"></textarea>
                        <button onclick="submitNicknameAndSchedule()">Submit</button>
                    </div>
                </div>
            """
            await websocket.send_text(json.dumps({"type": "modal", "html": modal_html}))

            try:
                response_text = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                try:
                    response = json.loads(response_text)
                    nickname = response.get('nickname', default_name)
                    schedule = response.get('schedule', 'Not specified')
                    description = response.get('description', 'No description yet')
                    logger.info(f"Received nickname, schedule, and description: {response}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {response_text}, error: {str(e)}")
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid data format. Please try again."}))
                    await websocket.close(code=1003)
                    return
            except asyncio.TimeoutError:
                logger.warning("WebSocket timeout while waiting for nickname and schedule")
                await websocket.send_text(json.dumps({"type": "error", "message": "Timeout waiting for your input. Please reconnect."}))
                await websocket.close(code=1002)
                return
            except Exception as e:
                logger.error(f"Error receiving nickname and schedule: {str(e)}")
                await websocket.send_text(json.dumps({"type": "error", "message": "An error occurred. Please reconnect."}))
                await websocket.close(code=1011)
                return

            users[user_id]['nickname'] = nickname
            users[user_id]['schedule'] = schedule
            users[user_id]['description'] = description

        save_data(users, rooms)

        nickname = users[user_id]['nickname']
        schedule = users[user_id]['schedule']
        description = users[user_id].get('description', 'No description yet')

        joined_rooms = users[user_id].get('joined_rooms', [])
        rooms_list_html = ''.join(
            f'<li onclick="joinRoom(\'{room_id}\')">{rooms[room_id]["name"]} '
            f'<span class="room-meta">({len(rooms[room_id]["users"])} participants)</span></li>'
            for room_id in joined_rooms if room_id in rooms
        )
        init_data = {
            "type": "init",
            "system_message": f"Your nickname is set to <strong>{nickname}</strong> and schedule to <strong>{schedule}</strong>. You can now create or join a chat room!",
            "rooms_list": rooms_list_html,
            "chat_title": "Chat: No room selected",
            "profile": {"nickname": nickname, "schedule": schedule, "description": description}
        }
        await websocket.send_text(json.dumps(init_data))

        async def broadcast(room_id, message):
            if room_id in rooms:
                for uid in rooms[room_id]['users']:
                    if uid in active_connections:
                        try:
                            await active_connections[uid].send_text(message)
                        except Exception as e:
                            logger.error(f"Error broadcasting to {uid}: {e}")
                            if room_id in rooms:
                                if 'pending_messages' not in rooms[room_id]:
                                    rooms[room_id]['pending_messages'] = {}
                                if uid not in rooms[room_id]['pending_messages']:
                                    rooms[room_id]['pending_messages'][uid] = []
                                rooms[room_id]['pending_messages'][uid].append(json.loads(message))

        async def broadcast_rooms_update(user_id_to_update):
            joined_rooms = users[user_id_to_update].get('joined_rooms', [])
            rooms_list_html = ''.join(
                f'<li onclick="joinRoom(\'{room_id}\')">{rooms[room_id]["name"]} '
                f'<span class="room-meta">({len(rooms[room_id]["users"])} participants)</span></li>'
                for room_id in joined_rooms if room_id in rooms
            )
            update_message = json.dumps({
                "type": "rooms_update",
                "rooms_list": rooms_list_html
            })
            if user_id_to_update in active_connections:
                try:
                    await active_connections[user_id_to_update].send_text(update_message)
                except Exception as e:
                    logger.error(f"Error sending rooms update to {user_id_to_update}: {e}")

        async def broadcast_participants_count(room_id):
            if room_id in rooms:
                count = len(rooms[room_id]['users'])
                message = json.dumps({
                    "type": "participants_update",
                    "count": count
                })
                for uid in rooms[room_id]['users']:
                    if uid in active_connections:
                        try:
                            await active_connections[uid].send_text(message)
                        except Exception as e:
                            logger.error(f"Error sending participants count to {uid}: {e}")

        async def render_messages(room_id):
            if room_id in rooms:
                messages = []
                for msg in rooms[room_id]['messages']:
                    sender_id = msg['user_id']
                    sender_nick = users.get(sender_id, {}).get('nickname', f"User_{sender_id}")
                    messages.append({
                        "user_id": sender_id,
                        "nickname": sender_nick,
                        "text": msg['text']
                    })
                return messages
            return []

        async def get_participants(room_id):
            if room_id in rooms:
                participants = []
                for uid in rooms[room_id]['users']:
                    user_info = users.get(uid, {})
                    nickname = user_info.get('nickname', f"User_{uid}")
                    schedule = user_info.get('schedule', 'Not specified')
                    participants.append({"nickname": nickname, "schedule": schedule})
                return participants
            return []

        async def send_pending_messages(user_id, room_id):
            if room_id in rooms and 'pending_messages' in rooms[room_id] and user_id in rooms[room_id]['pending_messages']:
                for msg in rooms[room_id]['pending_messages'][user_id]:
                    await websocket.send_text(json.dumps(msg))
                del rooms[room_id]['pending_messages'][user_id]
                save_data(users, rooms)

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                try:
                    data = json.loads(message)
                    action = data.get('action')
                    if action == 'create_room':
                        room_name = data.get('room_name', f"Room_{uuid.uuid4()}")
                        room_id = str(uuid.uuid4())
                        invite_code = secrets.token_hex(8)
                        rooms[room_id] = {
                            'name': room_name,
                            'users': {user_id},
                            'messages': [],
                            'invite_code': invite_code,
                            'creator': user_id,
                            'pending_messages': {}
                        }
                        users[user_id]['joined_rooms'] = users[user_id].get('joined_rooms', []) + [room_id]
                        current_room = room_id
                        participants = await get_participants(room_id)
                        response = {
                            "type": "room_joined",
                            "chat_title": room_name,
                            "room_id": room_id,
                            "invite_code": invite_code,
                            "participants": participants,
                            "participants_count": 1,
                            "messages": []
                        }
                        await websocket.send_text(json.dumps(response))
                        await broadcast(room_id, json.dumps({
                            "type": "system_message",
                            "message": f"<strong>{nickname}</strong> created the room."
                        }))
                        await broadcast_rooms_update(user_id)
                        save_data(users, rooms)
                        logger.info(f"Room {room_id} created by {nickname} with invite code {invite_code}")
                    elif action == 'join_room':
                        room_id = data.get('room_id')
                        if room_id in rooms:
                            if room_id not in users[user_id].get('joined_rooms', []):
                                await websocket.send_text(json.dumps({
                                    "type": "system_message",
                                    "message": "You are not a member of this room. Use the invite code to join permanently."
                                }))
                            else:
                                current_room = room_id
                                participants = await get_participants(room_id)
                                messages = await render_messages(room_id)
                                invite_code = rooms[room_id]['invite_code'] if rooms[room_id].get('creator') == user_id else None
                                await websocket.send_text(json.dumps({
                                    "type": "room_joined",
                                    "chat_title": rooms[room_id]['name'],
                                    "room_id": room_id,
                                    "invite_code": invite_code,
                                    "participants": participants,
                                    "participants_count": len(rooms[room_id]['users']),
                                    "messages": messages
                                }))
                                await send_pending_messages(user_id, room_id)
                                logger.info(f"{nickname} joined room {room_id}")
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "system_message",
                                "message": "Room does not exist."
                            }))
                    elif action == 'leave_room':
                        if current_room:
                            current_room = None
                            await websocket.send_text(json.dumps({
                                "type": "room_left",
                                "chat_title": "Chat: No room selected"
                            }))
                            logger.info(f"{nickname} left room view")
                    elif action == 'join_by_code':
                        invite_code = data.get('invite_code', '').strip()
                        room_id = next((rid for rid, r in rooms.items() if r['invite_code'] == invite_code), None)
                        if room_id:
                            if room_id not in users[user_id].get('joined_rooms', []):
                                rooms[room_id]['users'].add(user_id)
                                users[user_id]['joined_rooms'] = users[user_id].get('joined_rooms', []) + [room_id]
                                await broadcast(room_id, json.dumps({
                                    "type": "system_message",
                                    "message": f"<strong>{nickname}</strong> joined the room."
                                }))
                                await broadcast_participants_count(room_id)
                                await broadcast_rooms_update(user_id)
                                save_data(users, rooms)
                                await websocket.send_text(json.dumps({
                                    "type": "system_message",
                                    "message": f"Successfully joined room '{rooms[room_id]['name']}'!"
                                }))
                                logger.info(f"{nickname} joined room {room_id} via invite code {invite_code}")
                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "system_message",
                                    "message": "You are already a member of this room."
                                }))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "system_message",
                                "message": "Invalid invite code."
                            }))
                    elif action == 'send_message' and current_room:
                        msg = data.get('message', '').strip()
                        if msg:
                            message_data = {
                                "user_id": user_id,
                                "text": msg
                            }
                            rooms[current_room]['messages'].append(message_data)
                            rendered_messages = await render_messages(current_room)
                            response = {
                                "type": "chat_message",
                                "message": {"user_id": user_id, "nickname": nickname, "text": msg}
                            }
                            await broadcast(current_room, json.dumps(response))
                            save_data(users, rooms)
                            logger.info(f"Message from {nickname} in room {current_room}: {msg}")
                    elif action == 'update_profile':
                        old_nickname = nickname
                        nickname = data.get('nickname', nickname).strip()
                        schedule = data.get('schedule', schedule).strip()
                        description = data.get('description', description).strip()
                        if nickname:
                            users[user_id]['nickname'] = nickname
                            users[user_id]['schedule'] = schedule
                            users[user_id]['description'] = description
                            await websocket.send_text(json.dumps({
                                "type": "profile_updated",
                                "message": "Profile updated successfully!",
                                "profile": {"nickname": nickname, "schedule": schedule, "description": description}
                            }))
                            if current_room:
                                rendered_messages = await render_messages(current_room)
                                participants = await get_participants(current_room)
                                invite_code = rooms[current_room]['invite_code'] if rooms[current_room].get('creator') == user_id else None
                                await broadcast(current_room, json.dumps({
                                    "type": "room_joined",
                                    "chat_title": rooms[current_room]['name'],
                                    "room_id": current_room,
                                    "invite_code": invite_code,
                                    "participants": participants,
                                    "participants_count": len(rooms[current_room]['users']),
                                    "messages": rendered_messages
                                }))
                            save_data(users, rooms)
                            logger.info(f"Profile updated for {user_id}: {nickname}, {schedule}, {description}")
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "system_message",
                                "message": "Nickname cannot be empty."
                            }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "system_message",
                            "message": "Invalid action or no room selected."
                        }))
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON message: {message}")
                    await websocket.send_text(json.dumps({
                        "type": "system_message",
                        "message": "Invalid message format. Please try again."
                    }))
            except asyncio.TimeoutError:
                logger.warning(f"WebSocket timeout for {nickname}, keeping connection alive")
                await websocket.send_text(json.dumps({
                    "type": "system_message",
                    "message": "Connection timeout, staying connected..."
                }))
            except WebSocketDisconnect as e:
                logger.info(f"WebSocket disconnected for user {user_id}. Code: {e.code}, Reason: {e.reason}")
                break
            except Exception as e:
                logger.error(f"Error in chat loop for {nickname}: {str(e)}")
                await websocket.send_text(json.dumps({
                    "type": "system_message",
                    "message": "An error occurred. Please reconnect."
                }))
                break

    except WebSocketDisconnect as e:
        logger.info(f"WebSocket disconnected normally for user {user_id}. Code: {e.code}, Reason: {e.reason}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {str(e)}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps({
                "type": "system_message",
                "message": "A critical error occurred. Please reconnect."
            }))
            await websocket.close(code=1011)
    finally:
        if user_id in active_connections:
            del active_connections[user_id]
        save_data(users, rooms)