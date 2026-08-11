import socket
import json
import struct
import time

def send_recv(s, pdu):
    data = json.dumps(pdu).encode('utf-8')
    s.sendall(struct.pack('>I', len(data)) + data)
    response_len_data = s.recv(4)
    if not response_len_data:
        return None
    response_len = struct.unpack('>I', response_len_data)[0]
    return json.loads(s.recv(response_len))

print("Test 1: Duplicate card in same deck")
s1 = socket.socket()
s1.connect(('localhost', 4444))
pdu1 = {'type': 'PLAYER_READY', 'seq_num': 1, 'player_id': 'p1', 'deck_list': ['mountain_001', 'mountain_001']}
print(send_recv(s1, pdu1))
s1.close()

time.sleep(0.5)

print("\nTest 2: Same card across different players")
s2 = socket.socket()
s2.connect(('localhost', 4444))
pdu2 = {'type': 'PLAYER_READY', 'seq_num': 1, 'player_id': 'p1', 'deck_list': ['mountain_001']}
print("P1:", send_recv(s2, pdu2))

s3 = socket.socket()
s3.connect(('localhost', 4444))
pdu3 = {'type': 'PLAYER_READY', 'seq_num': 1, 'player_id': 'p2', 'deck_list': ['mountain_001']}
print("P2:", send_recv(s3, pdu3))

s2.close()
s3.close()
