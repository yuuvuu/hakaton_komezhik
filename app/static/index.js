let currentProfile = {};
let currentRoomId = null;
let currentRoomName = "";
let currentParticipants = [];
let currentInviteCode = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function startWebSocket(token) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
    window.ws = ws;
    const chatContainer = document.getElementById('chat-container');

    ws.onopen = () => {
        console.log("WebSocket connected, sending token:", token);
        ws.send(token);
        reconnectAttempts = 0;
        if (currentRoomId) {
            ws.send(JSON.stringify({ action: 'join_room', room_id: currentRoomId }));
        }
    };

    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            chatContainer.innerHTML += event.data;
            chatContainer.scrollTop = chatContainer.scrollHeight;
            return;
        }

        console.log("Received data:", data);
        switch(data.type) {
            case "modal":
                const modalContainer = document.createElement('div');
                modalContainer.innerHTML = data.html;
                document.body.appendChild(modalContainer);
                break;

            case "init":
                if (data.system_message) {
                    document.getElementById('system-message').innerHTML = data.system_message;
                }
                if (data.rooms_list) {
                    document.getElementById('rooms-list').innerHTML = data.rooms_list;
                }
                document.getElementById('chat-title').textContent = data.chat_title;
                currentProfile = data.profile || {};
                break;
                
            case "rooms_update":
                if (data.rooms_list) {
                    document.getElementById('rooms-list').innerHTML = data.rooms_list;
                }
                break;
                
            case "room_joined":
                if (data.chat_title && data.participants_count) {
                    document.body.classList.add('chat-active');
                    document.body.classList.remove('profile-active');
                    currentRoomId = data.room_id;
                    currentRoomName = data.chat_title;
                    currentParticipants = data.participants || [];
                    currentInviteCode = data.invite_code || null;
                    document.getElementById('chat-title').innerHTML = `<span onclick="showRoomHeader()" style="cursor: pointer;"><i class="fas fa-comment-alt"></i> ${data.chat_title}</span>`;
                    document.getElementById('participants-count').textContent = 
                        `${data.participants_count} participant${data.participants_count !== 1 ? 's' : ''}`;
                    chatContainer.innerHTML = '';
                    if (data.messages && data.messages.length > 0) {
                        data.messages.forEach(msg => {
                            chatContainer.innerHTML += `<div class="message"><strong>${msg.nickname}</strong>: ${msg.text}</div>`;
                        });
                    }
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
                break;
                
            case "room_left":
                document.body.classList.remove('chat-active');
                document.body.classList.remove('profile-active');
                document.getElementById('chat-title').textContent = data.chat_title;
                document.getElementById('participants-count').textContent = "0 participants";
                currentRoomId = null;
                currentRoomName = "";
                currentParticipants = [];
                currentInviteCode = null;
                break;
                
            case "participants_update":
                document.getElementById('participants-count').textContent = 
                    `${data.count} participant${data.count !== 1 ? 's' : ''}`;
                break;
                
            case "chat_message":
                const msg = data.message;
                chatContainer.innerHTML += `<div class="message"><strong>${msg.nickname}</strong>: ${msg.text}</div>`;
                chatContainer.scrollTop = chatContainer.scrollHeight;
                break;
                
            case "system_message":
                chatContainer.innerHTML += `<div class="system-message">${data.message}</div>`;
                chatContainer.scrollTop = chatContainer.scrollHeight;
                break;

            case "profile_updated":
                currentProfile = data.profile;
                document.getElementById('profile-nickname').value = currentProfile.nickname;
                document.getElementById('profile-schedule').value = currentProfile.schedule;
                document.getElementById('profile-description').value = currentProfile.description;
                alert(data.message);
                break;
                
            case "error":
                alert(data.message);
                break;
                
            default:
                console.log("Unknown message type:", data);
        }
    };

    ws.onerror = (error) => {
        console.error("WebSocket error:", error);
    };

    ws.onclose = (event) => {
        console.log("WebSocket disconnected. Code:", event.code, "Reason:", event.reason);
        if (reconnectAttempts < maxReconnectAttempts) {
            const delay = Math.min(2000 * Math.pow(2, reconnectAttempts), 10000);
            setTimeout(() => {
                console.log(`Reconnecting WebSocket (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})...`);
                reconnectAttempts++;
                startWebSocket(token);
            }, delay);
        } else {
            alert("Failed to reconnect after multiple attempts. Please refresh the page.");
        }
    };

    document.getElementById('message-input').addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && event.target.value.trim() !== '') {
            try {
                ws.send(JSON.stringify({ action: 'send_message', message: event.target.value }));
                event.target.value = '';
            } catch (e) {
                console.error("Error sending message:", e);
            }
        }
    });
}

function toggleMenu() {
    const menu = document.getElementById('menu-options');
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}

function createRoom() {
    const modalContainer = document.createElement('div');
    modalContainer.id = 'create-room-modal';
    modalContainer.className = 'modal';
    modalContainer.innerHTML = `
        <div class="modal-content">
            <h2>Create a Room</h2>
            <p>Enter the room name:</p>
            <input type="text" id="room-name" placeholder="e.g., My Chat Room">
            <button onclick="submitCreateRoom()">Create</button>
            <button onclick="hideCreateRoomModal()">Cancel</button>
        </div>
    `;
    document.body.appendChild(modalContainer);
    toggleMenu();
}

function submitCreateRoom() {
    const roomName = document.getElementById('room-name').value.trim() || `Room_${Date.now()}`;
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({ action: 'create_room', room_name: roomName }));
    }
    hideCreateRoomModal();
}

function hideCreateRoomModal() {
    const modal = document.getElementById('create-room-modal');
    if (modal) modal.remove();
}

function showJoinRoomModal() {
    const modalContainer = document.createElement('div');
    modalContainer.id = 'join-room-modal';
    modalContainer.className = 'modal';
    modalContainer.innerHTML = `
        <div class="modal-content">
            <h2>Join a Room</h2>
            <p>Enter the room invite code:</p>
            <input type="text" id="invite-code" placeholder="e.g., a1b2c3d4e5f6g7h8">
            <button onclick="joinRoomByCode()">Join</button>
            <button onclick="hideJoinRoomModal()">Cancel</button>
        </div>
    `;
    document.body.appendChild(modalContainer);
    toggleMenu();
}

function hideJoinRoomModal() {
    const modal = document.getElementById('join-room-modal');
    if (modal) modal.remove();
}

function joinRoomByCode() {
    const inviteCode = document.getElementById('invite-code').value.trim();
    if (inviteCode && window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({ action: 'join_by_code', invite_code: inviteCode }));
        hideJoinRoomModal();
    }
}

function joinRoom(roomId) {
    currentRoomId = roomId;
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({ action: 'join_room', room_id: roomId }));
    }
}

function showRoomsList() {
    currentRoomId = null;
    currentRoomName = "";
    currentParticipants = [];
    currentInviteCode = null;
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({ action: 'leave_room' }));
    }
}

function showProfile() {
    document.body.classList.remove('chat-active');
    document.body.classList.add('profile-active');
    document.getElementById('profile-nickname').value = currentProfile.nickname || '';
    document.getElementById('profile-schedule').value = currentProfile.schedule || '';
    document.getElementById('profile-description').value = currentProfile.description || '';
    toggleMenu();
}

function hideProfile() {
    document.body.classList.remove('profile-active');
}

function updateProfile() {
    const nickname = document.getElementById('profile-nickname').value.trim();
    const schedule = document.getElementById('profile-schedule').value.trim();
    const description = document.getElementById('profile-description').value.trim();
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({
            action: 'update_profile',
            nickname: nickname,
            schedule: schedule,
            description: description
        }));
    }
}

function showRoomHeader() {
    if (currentRoomId) {
        const participantsList = currentParticipants.map(p => `${p.nickname} (${p.schedule})`).join(', ');
        const headerModal = document.createElement('div');
        headerModal.id = 'room-header-modal';
        headerModal.className = 'room-header-modal';
        headerModal.innerHTML = `
            <div class="room-header-content">
                <h2>${currentRoomName}</h2>
                ${currentInviteCode ? `<p>Invite Code: ${currentInviteCode}</p>` : ''}
                <p class="participants-list">Participants: ${participantsList || 'None'}</p>
                <button onclick="hideRoomHeader()">Close</button>
            </div>
        `;
        document.body.appendChild(headerModal);
    }
}

function hideRoomHeader() {
    const headerModal = document.getElementById('room-header-modal');
    if (headerModal) {
        headerModal.remove();
    }
}

window.submitNicknameAndSchedule = function() {
    const nickname = document.getElementById('nickname').value.trim();
    const schedule = document.getElementById('schedule').value.trim();
    const description = document.getElementById('description') ? document.getElementById('description').value.trim() : 'No description yet';
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({ nickname, schedule, description }));
    }
    const modal = document.getElementById('modal');
    if (modal) modal.remove();
};