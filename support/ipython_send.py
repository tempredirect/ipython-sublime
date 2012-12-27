#!/usr/bin/env python

import sys

from IPython.zmq.blockingkernelmanager import BlockingKernelManager
from json import loads
from os import listdir
from os.path import expanduser, join
import re
import socket

# utils

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
    km.shell_channel.start()
    km.shell_channel.session.key = km.key
    return km


def initialize_km():
    cfg = find_alive_server()
    if not cfg:
        raise IPythonNotFoundException("cannot find alive server")        
    return km_from_cfg(cfg)


def get_response(km, msg_id):
    msgs = km.shell_channel.get_msgs()
    while not msgs:
        msgs = km.shell_channel.get_msgs()
    return [m for m in msgs
            if m['parent_header']['msg_id'] == msg_id]


def execute_code(km, code):
    code = strip_comment_lines(code)
    return km.shell_channel.execute(code)

def execute(km, code):
    msg_id = execute_code(km, code)
    return get_response(km, msg_id)[0] # will only be one response
    
def is_error( response ):
    return resp['header']['status'] == 'error'


# magic object info

def get_object_info(km, word):
    msg_id = km.shell_channel.object_info(word)
    response = get_response(km, msg_id)
    return response[0]

# http://stackoverflow.com/a/3229493/31480
def pretty(d, indent=0):
   for key, value in d.iteritems():
      print '\t' * indent + str(key)
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         print '\t' * (indent+1) + str(value)

if __name__ == '__main__':

    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-c', dest = 'code', help = 'Code to send to ipython kernel')
    parser.add_option('-v', '--verbose', dest = 'verbose', action='store_true', default=False,
                            help = 'Output verbose debug messages')

    (options, args) = parser.parse_args()

    # print options
    if options.code is not None:
        code = options.code
    else:
        code = sys.stdin.read()

    km = initialize_km()
    resp = execute(km, code)
    
    if options.verbose:
        pretty(resp)
    if is_error(resp):
        content = resp['content']
        print content['evalue']
        for line in content['traceback']:
            print line
        sys.exit(1)
    else:
        sys.exit(0)


