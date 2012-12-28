import struct
from struct import pack, unpack

class SocketDisconnected(RuntimeError): pass

class Connection:

    def __init__(self, sock, verbose = False):
        self.sock = sock
        self.verbose = verbose

    def read_bytes(self,toread):
        result = ''
        while len(result) < toread:
            chunk = self.sock.recv(toread)
            if chunk == '':
                raise SocketDisconnected("socket connection broken on read")
            result = result + chunk
        return result

    def send_bytes(self, payload):
        totalsent = 0
        while totalsent < len(payload):
            sent = self.sock.send(payload[totalsent:])
            if sent == 0:
                raise SocketDisconnected("socket connection broken on write")
            totalsent = totalsent + sent

    def read_message(self):
        if self.verbose:
            print "read_message"
        msgtype,length = unpack('<bi', self.read_bytes(5))
    
        payload = self.read_bytes(length)

        return (msgtype, payload)

    def write_message(self, msgtype, msg ):
        if self.verbose:
            print "write_message"
        payload = pack('<bi', msgtype, len(msg) ) + msg

        self.send_bytes(payload)


if __name__ == '__main__':
    msgtype = 1
    msg = """print "wibble" """
    payload = pack('<bi', msgtype, int(len(msg)) ) + msg
    print len(payload)
    print payload
