import json
import os

DATA_FILE = "app/data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            users_dict = data.get('users', {})
            rooms_dict = {}
            for room_id, room in data.get('rooms', {}).items():
                rooms_dict[room_id] = {
                    'name': room['name'],
                    'users': set(room['users']),
                    'messages': room['messages'],
                    'invite_code': room.get('invite_code', ''),
                    'pending_messages': room.get('pending_messages', {})
                }
            for user_id, user in users_dict.items():
                if 'description' not in user:
                    user['description'] = "No description yet"
                if 'joined_rooms' not in user:
                    user['joined_rooms'] = []
            return users_dict, rooms_dict
    return {}, {}

def save_data(users_dict, rooms_dict):
    rooms_to_save = {}
    for room_id, room in rooms_dict.items():
        rooms_to_save[room_id] = {
            'name': room['name'],
            'users': list(room['users']),
            'messages': room['messages'],
            'invite_code': room['invite_code'],
            'pending_messages': room['pending_messages']
        }
    data = {'users': users_dict, 'rooms': rooms_to_save}
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

users, rooms = load_data()