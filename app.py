#!/usr/bin/env python
from threading import Lock
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect

async_mode = None
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_lock = Lock()
clients = {}  # A dictionary of client cookie ids associated with user names.


def background_thread():
    # Always running in the background, 1 for all clients.
    count = 0
    while True:
        print(clients)

        socketio.sleep(1)  # To make sure we are not spamming updates.
        count += 1
        inactive = []
        for client in clients:
            # If the client is dead:
            if clients[client] == -1:
                inactive.append(client)
            # If the client has a name and is connected:
            elif clients[client] is not None:
                # Send each client a personal message containing it's username.
                socketio.emit('my_response',
                              {'data': "<h1>" + str(clients[client]) + str(count) + "</h1>", 'count': count},
                              namespace='/spyfall', room=client)
        for client in inactive:
            clients.pop(client)


# Serve the homepage
@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)


# Handle a logon, associate the user with its username:
@socketio.on('logon', namespace='/spyfall')
def use_logon(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    print(message['data'])
    if message['data'] != "I'm connected!":
        clients[request.sid] = message['data']


# Handle a disconnect:
@socketio.on('disconnect_request', namespace='/spyfall')
def disconnect_request():
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': 'Disconnected!', 'count': session['receive_count']})
    disconnect()


# Handle the latency calculation requests:
@socketio.on('my_ping', namespace='/spyfall')
def ping_pong():
    emit('my_pong')


# Handle the initiation of a new user connecting:
@socketio.on('connect', namespace='/spyfall')
def user_connect():
    global thread
    global clients
    clients[request.sid] = None
    print(request.sid)
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)
            # emit('my_response', {'data': 'Connected', 'count': 0})


# Handle disconnects:
@socketio.on('disconnect', namespace='/spyfall')
def user_disconnect():
    print('-------------------')
    global clients
    clients[request.sid] = -1
    print('Client disconnected', request.sid)


if __name__ == '__main__':
    socketio.run(app, debug=False)
