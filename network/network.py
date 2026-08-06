"""Network utilities for MTGNP."""
import socket
import json
import struct
from typing import Dict, Optional

from core.constants import MAX_PDU_SIZE


def encode_message(pdu: Dict) -> bytes:
    """
    Encode a PDU with a 4-byte big-endian length prefix.
    
    Args:
        pdu: Dictionary to encode
        
    Returns:
        Bytes with length prefix + JSON payload
        
    Raises:
        ValueError: If PDU exceeds MAX_PDU_SIZE
    """
    json_str = json.dumps(pdu, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    if len(json_bytes) > MAX_PDU_SIZE:
        raise ValueError(f"PDU exceeds max size: {len(json_bytes)}")
    return struct.pack('>I', len(json_bytes)) + json_bytes


def decode_message(data: bytes) -> Dict:
    """
    Decode a framed PDU.
    
    Args:
        data: Bytes containing length prefix + JSON payload
        
    Returns:
        Decoded dictionary
        
    Raises:
        ValueError: If message is incomplete or invalid
    """
    if len(data) < 4:
        raise ValueError("Incomplete message: missing length prefix")
    length = struct.unpack('>I', data[:4])[0]
    if len(data) < 4 + length:
        raise ValueError(f"Incomplete message: expected {length} bytes, got {len(data) - 4}")
    json_str = data[4:4+length].decode('utf-8')
    return json.loads(json_str)


def send_pdu(sock: socket.socket, pdu: Dict, verbose: bool = False) -> bool:
    """
    Send a PDU over a socket.
    
    Args:
        sock: Socket to send on
        pdu: PDU to send
        verbose: Whether to print debug output
        
    Returns:
        True if successful, False otherwise
    """
    try:
        data = encode_message(pdu)
        sock.sendall(data)
        if verbose:
            print(f"[SEND] {json.dumps(pdu, indent=2)}")
        return True
    except Exception as e:
        if verbose:
            print(f"[ERROR] Failed to send PDU: {e}")
        return False


def recv_pdu(sock: socket.socket, buffer: bytes, verbose: bool = False) -> tuple:
    """
    Receive a PDU from a socket.
    
    Args:
        sock: Socket to receive from
        buffer: Existing buffer
        verbose: Whether to print debug output
        
    Returns:
        Tuple of (decoded PDU or None, remaining buffer)
    """
    try:
        data = sock.recv(4096)
        if not data:
            return None, buffer
        buffer += data
        
        # Process all complete messages
        while len(buffer) >= 4:
            length = struct.unpack('>I', buffer[:4])[0]
            if len(buffer) < 4 + length:
                break
            
            message_data = buffer[:4+length]
            buffer = buffer[4+length:]
            
            try:
                pdu = decode_message(message_data)
                if verbose:
                    print(f"[RECV] {json.dumps(pdu, indent=2)}")
                return pdu, buffer
            except json.JSONDecodeError as e:
                if verbose:
                    print(f"[ERROR] Invalid JSON: {e}")
                continue
        
        return None, buffer
    except Exception as e:
        if verbose:
            print(f"[ERROR] Failed to receive PDU: {e}")
        return None, buffer