#!/usr/bin/env python

import sys

sys.path.append("../lib")

import logging

from IPython.zmq.blockingkernelmanager import BlockingKernelManager
from json import loads
from os import listdir
from os.path import expanduser, join
import re
import socket
import struct

from protocol import Connection

# utils

verbose = False

class IPythonNotFoundException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

def check_port_open(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((ip, port))
        s.shutdown(2)
        status = True
    except:
        status = False
    return status


def find_alive_server():
    # assuming we are using default profile
    security_dir = expanduser('~/.ipython/profile_default/security')
    all_json_files = listdir(security_dir)
    for json_file in all_json_files:
        with open(join(security_dir, json_file)) as f:
            cfg = loads(f.read())
        ip, port = cfg['ip'], cfg['shell_port']
        if check_port_open(ip, port):
            return cfg


# text processing

def strip_comment_lines(s):
    comment = re.compile('^#.+')
    return comment.sub('', s)


def strip_color_escapes(s):
    strip = re.compile('\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]')
    return strip.sub('', s)


# initialize kernel functions

def km_from_cfg(cfg):
    km = BlockingKernelManager(**cfg)
    km.start_channels()
    km.shell_channel.session.key = km.key
    km.hb_channel.unpause()
    return km


def initialize_km():
    cfg = find_alive_server()
    if not cfg:
        raise IPythonNotFoundException("cannot find alive server")        
    return km_from_cfg(cfg)

def extract_traceback(traceback):
    # strip ANSI color controls
    strip = re.compile('\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]')
    tb = [strip.sub('',t) for t in traceback]
    if len(tb) == 1:
        m = re.search(', line (\d+)', tb[0])
        line = int(m.group(1))
        return [('<ipython-input>', line, tb[0])]
    else:
        result = []
        for t in tb[1:-1]:
            m = re.search(r'^(\S+) in (\S+)', t)
            filename = m.group(1)
            m = re.search(r'\--+> (\d+)', t)
            line_num = int(m.group(1))
            result.append( (filename, line_num, t))
        return result

def get_response(km, msg_id):
    
    success = False
    out = []
    error = None
    while True:
        msg = km.sub_channel.get_msg()
        if verbose:
            logging.debug("---- msg ----")
            pretty( msg )
        if msg['msg_type'] == 'status':
            if msg['content']['execution_state'] == 'idle':
                break
        elif msg['msg_type'] == 'stream':
            content = msg['content']
            out.append("{0}: {1}".format(content['name'], content['data']))            
        elif msg['msg_type'] == 'pyout':            
            out.append(msg['content']['data']['text/plain'])
        elif msg['msg_type'] == 'pyerr':            
            c = msg['content']
            ename, evalue = c['ename'],c['evalue']
            traceback = '\n'.join(c['traceback'])
            error = {
                "traceback" : extract_traceback(c['traceback']),
                "error" : '{1}: {2}'.format(traceback, ename, evalue)
            }
    return ("\n".join(out), error)

    # return [m for m in msgs
            # if m['parent_header']['msg_id'] == msg_id]


def execute_code(km, code):
    code = strip_comment_lines(code)
    return km.shell_channel.execute(code)

def execute(km, code):
    msg_id = execute_code(km, code)
    return get_response(km, msg_id)
    
# magic object info

def get_object_info(km, word):
    msg_id = km.shell_channel.object_info(word)
    response = get_response(km, msg_id)
    return response[0]

# http://stackoverflow.com/a/3229493/31480
def pretty(d, indent=0):
   for key, value in d.iteritems():
      logging.info('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         logging.info( '\t' * (indent+1) + str(value))

class Server:

    def __init__(self, options):
        self.port = options.port        
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


    def handle_client(self, clientsocket):

        connection = Connection(clientsocket, verbose = verbose)
        try:
            while 1:
                (msgtype, msg) = connection.read_message()
                logging.debug( "[%i] [%s]" % (msgtype, msg))
                if msgtype == 1:
                    # execute code
                    
                    km = initialize_km()
                    out, error = execute(km, msg)
                    logging.debug( "[complete] [%s] [%s]" % (out, error))

                    if error is None:
                        connection.write_message( 2, out)
                    else:
                        connection.write_message( 3, error['error'])
                else:
                    raise RuntimeError("unknown msgtype : %s" % str(msgtype))
        except Exception as e:
            logging.error( str(e))
            clientsocket.close()
            

    def run(self):
        serversocket = self.serversocket
        serversocket.bind(("127.0.0.1", options.port))
        serversocket.listen(5)
        logging.info( "Listening on %s" % str(options.port))
        try:
            while 1:
                (clientsocket,address) = serversocket.accept()
                self.handle_client(clientsocket)
        except KeyboardInterrupt as ki:
            logging.warning( "Exiting" )
            pass

def main(options):
    
    logconfig = {'level': logging.DEBUG if options.verbose else logging.INFO }

    if options.logfile is not None:
        logconfig['filename'] = options.logfile
    else:
        logconfig['stream'] = sys.stdout

    logging.basicConfig(**logconfig)


    if options.server:
        server = Server(options)
        server.run()
    else:
        # print options
        if options.code is not None:
            code = options.code
        else:
            code = sys.stdin.read()

        verbose = options.verbose

        km = initialize_km()
        out, error = execute(km, code)

        if len( out ) > 0:
            print "\n".join(out)    
        if error is not None:
            print error['error']
            sys.exit(1)
        else:
            sys.exit(0)

if __name__ == '__main__':

    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-c', dest = 'code', help = 'Code to send to ipython kernel')
    parser.add_option('-v', '--verbose', dest = 'verbose', action='store_true', default=False,
                            help = 'Output verbose debug messages')
    parser.add_option('-s', '--server', dest = 'server', action='store_true', default=False,
                            help = 'Ignore -c and become a server listening on a port')
    parser.add_option('-d', '--daemon', dest = 'daemon', action='store_true', default=False,
                            help = 'Daemonise the process')
    parser.add_option('-p', '--port', dest = 'port', default=48721, type='int',
                            help = 'Ignore -c and become a server listening on a port')
    parser.add_option('--log', dest = 'logfile', default=None, 
                            help = 'optional Log file')
    (options, args) = parser.parse_args()

    if options.daemon:
        import daemon

        with daemon.DaemonContext(detach_process = True):
            main(options)

    else:
        main(options)
