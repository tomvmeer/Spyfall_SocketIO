#!/usr/bin/env python
from threading import Lock
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect
import os
import random
import time
import hashlib

async_mode = None
app = Flask('Spyfall')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_r = None
game_state = 'waiting'
thread_lock = Lock()
clients = {}  # A dictionary of client cookie ids associated with user names.
roles = {}
round_time = 200
inactive = []

def state_waiting(clients, admin):
    # Send each client a personal message containing all connected users.
    for client in clients:
        if clients[client] is not None:
            display = "<h1>Connected users:</h1>"
            for c in clients:
                if clients[c] is not None:
                    if clients[c] == clients[client]:
                        display += '<b>'
                    if admin == clients[c]:
                        display += str(clients[c]) + ' (admin) </b><br>'
                    else:
                        display += str(clients[c]) + '</b><br>'
                    if clients[c] != clients[client]:
                        display.replace('</b>', "")
            socketio.emit('my_response',
                          {'data': display},
                          namespace='/spyfall', room=client)


def state_starting(clients):
    global roles
    global game_state
    random.seed(os.urandom(128))
    locs = os.listdir('locations')
    with open('locations/' + locs[random.randrange(0, len(locs))], "r") as f:
        lines = f.read().split('\n')
    loc = lines[0]
    loc_roles = lines[1:]
    i, k = 0, 0
    num_players = len(clients) - list(clients.values()).count(None)
    randomlist = random.sample(range(1, len(loc_roles)), num_players - 1)
    ispy = random.randrange(0, num_players)
    print(randomlist, ispy, num_players)
    for client in clients:
        if clients[client] is not None:
            if k == ispy:
                roles[clients[client]] = loc_roles[0]
            else:
                roles[clients[client]] = loc_roles[int(randomlist[i])]
                i += 1
            k += 1
            if roles[clients[client]] == 'Spy':
                display = "<h1>You are the spy!</h1>"
                display += '<br> Location reference: <br>'
                for i in locs[:-1]:
                    display += str(i).replace('.txt', '') + ', '
                display += locs[-1].replace('.txt', '')
            else:
                display = "<h1>" + loc + "</h1>"
                display += "You are " + roles[clients[client]]
            socketio.emit('my_response',
                          {'data': display},
                          namespace='/spyfall', room=client)
    game_state = 'started'
    socketio.emit('my_response',
                  {'data': 'started'},
                  namespace='/spyfall')
    return loc, locs


def state_started(clients, loc, start_time, locs):
    global roles
    print(roles)
    for client in clients:
        if clients[client] is not None:
            time_left = int(start_time + round_time - time.time())
            if time_left > 0:
                display = 'Time left: ' + str(time_left) + ' seconds.'
                if roles[clients[client]] == 'Spy':
                    display += "<h1>You are the spy!</h1>"
                    display += '<br> Location reference: <br>'
                    for i in locs[:-1]:
                        display += str(i).replace('.txt', '') + ', '
                    display += locs[-1].replace('.txt', '')
                else:
                    display += "<h1>" + loc + "</h1>"
                    display += "You are " + roles[clients[client]]
                socketio.emit('my_response',
                              {'data': display},
                              namespace='/spyfall', room=client)
            else:
                time_left = int(start_time + round_time + 10 - time.time())
                display = "<h1>Game over!</h1> <br> Restart in " + str(time_left) + " seconds...."
                socketio.emit('my_response',
                              {'data': display},
                              namespace='/spyfall', room=client)
                if time_left <= 0:
                    return True


def background_thread():
    # Always running in the background, 1 for all clients.
    count = 0
    admin = None
    global game_state
    global inactive
    while True:
        print(clients)
        socketio.sleep(0.5)  # To make sure we are not spamming updates.
        count += 1
        for client in clients:
            # If the client has a name and is connected:
            if clients[client] is not None:
                # First client becomes admin:
                if (admin is None or admin == clients[
                    client] or admin not in clients.values()) and game_state != 'started':
                    socketio.emit('my_response',
                                  {'data': 'admin', 'count': count},
                                  namespace='/spyfall', room=client)
                    admin = clients[client]
        # Remove inactive clients.
        if game_state == 'waiting':
            for client in inactive:
                if client in clients:
                    clients.pop(client)
            inactive = []
        if game_state == 'waiting':
            state_waiting(clients, admin)
        elif game_state == 'starting':
            loc, locs = state_starting(clients)
            start_time = time.time()
        elif game_state == 'started':
            if state_started(clients, loc, start_time, locs):
                game_state = 'waiting'


# Serve the homepage
@app.route('/')
def index_page():
    return render_template('index.html', async_mode=socketio.async_mode)


# Serve the register page
@app.route('/register')
def register_page():
    return render_template('register.html', async_mode=socketio.async_mode)


# Handle a logon, associate the user with its username:
@socketio.on('logon', namespace='/spyfall')
def use_logon(message):
    global game_state
    correct_pswd = False
    session['receive_count'] = session.get('receive_count', 0) + 1
    if message['data'] != "I'm connected!":
        username = message['data'][0]
        password = hashlib.sha256(message['data'][1].encode()).hexdigest()
        with open('passwords.dat', 'r') as f:
            lines = f.read().split('\n')
            for line in lines:
                if line.split(' ')[0] == username:
                    if line.split(' ')[1] == password:
                        correct_pswd = True
        if username in clients.values() and correct_pswd:
            to_remove = []
            for i in clients:
                if clients[i] == username:
                    to_remove.append(i)
            for i in to_remove:
                clients.pop(i)
                socketio.emit('my_response',
                              {'data': 'Logged in from other location!'},
                              namespace='/spyfall', room=i)
                clients[request.sid] = username
            socketio.emit('my_response',
                          {'data': 'logged in'},
                          namespace='/spyfall', room=request.sid)
        elif game_state == 'waiting' and correct_pswd:
            clients[request.sid] = username
            socketio.emit('my_response',
                          {'data': 'logged in'},
                          namespace='/spyfall', room=request.sid)
        elif game_state == 'waiting' and not correct_pswd:
            socketio.emit('my_response',
                          {'data': 'Incorrect password! <a href="/"> try again </a>'},
                          namespace='/spyfall', room=request.sid)
        else:
            socketio.emit('my_response',
                          {'data': 'Game in progress, please wait.'},
                          namespace='/spyfall', room=request.sid)


# Handle the latency calculation requests:
@socketio.on('my_ping', namespace='/spyfall')
def ping_pong():
    emit('my_pong')


@socketio.on('my_ping', namespace='/register')
def ping_pong():
    emit('my_pong')


# Handle a user registering, associate the user with its username:
@socketio.on('logon_new', namespace='/register')
def use_register(message):
    username = message['data'][0]
    passwd1 = hashlib.sha256(message['data'][1].encode()).hexdigest()
    passwd2 = hashlib.sha256(message['data'][2].encode()).hexdigest()
    users = []
    with open('passwords.dat', 'r') as f:
        lines = f.read().split('\n')
        for line in lines:
            users.append(line.split(" ")[0])
    if username in users:
        socketio.emit('my_response',
                      {'data': 'Username taken <a href="/register"> try again </a>'},
                      namespace='/register', room=request.sid)
        return False
    elif passwd1 != passwd2:
        socketio.emit('my_response',
                      {'data': 'Passwords not equal <a href="/register"> try again </a>'},
                      namespace='/register', room=request.sid)
        return False
    elif username == '' or passwd1 == '':
        socketio.emit('my_response',
                      {'data': 'Please enter something <a href="/register"> try again </a>'},
                      namespace='/register', room=request.sid)
        return False
    else:
        lines.append(username + " " + str(passwd1))
        to_write = []
        i = 0
        for line in lines:
            if i > 0:
                to_write.append('\n')
            to_write.append(line)
            i += 1
        with open('passwords.dat', 'w') as f:
            f.write("".join(to_write))
        socketio.emit('my_response',
                      {'data': 'Registration successful <a href="/"> login </a>'},
                      namespace='/register', room=request.sid)
        return True


# Handle the initiation of a new user connecting:
@socketio.on('connect', namespace='/spyfall')
def user_connect():
    global thread
    global clients
    clients[request.sid] = None
    # print(request.sid)
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)
            # emit('my_response', {'data': 'Connected', 'count': 0})


@socketio.on('start', namespace='/spyfall')
def start_game():
    global game_state
    if request.sid in clients:
        game_state = 'starting'
        print('starting')


# Handle disconnects:
@socketio.on('disconnect', namespace='/spyfall')
def user_disconnect():
    print('-------------------')
    global clients
    global inactive
    inactive.append(request.sid)
    print('Client disconnected', request.sid)


if __name__ == '__main__':
    socketio.run(app, debug=False)
