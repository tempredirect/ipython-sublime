import sys
import os
import sublime, sublime_plugin

import subprocess
import socket
import struct
import time


if os.name == 'nt':
    from ctypes import windll, create_unicode_buffer


def add_to_path(path):
    # Python 2.x on Windows can't properly import from non-ASCII paths, so
    # this code added the DOC 8.3 version of the lib folder to the path in
    # case the user's username includes non-ASCII characters
    if os.name == 'nt':
        buf = create_unicode_buffer(512)
        if windll.kernel32.GetShortPathNameW(path, buf, len(buf)):
            path = buf.value

    if path not in sys.path:
        sys.path.append(path)


lib_folder = os.path.join(sublime.packages_path(), 'IPython', 'lib')
add_to_path(lib_folder)


# import protocol
# reload(protocol)
from protocol import Connection

def load_settings():
    return sublime.load_settings("IPython.sublime-settings")

def plugin_dir():
    return os.path.join(sublime.packages_path(), 'IPython')

def find_python(settings):    
    if settings.has("python"):
        python = settings.get("python")
        if os.path.exists(python):
            return settings.get("python")
        else:
            raise RuntimeException("python setting points to non existing file [%s]" % python)

    executable = 'python.exe' if os.name == 'nt' else 'python'
    paths = os.environ.get("PATH").split(os.pathsep)
    for path in paths:
        python = os.path.join( os.path.expandvars(path), executable )
        if os.path.exists(python):
            return python

    raise RuntimeException("unable to find [%s] in path [%s]" % (executable, os.environ.get("PATH")))

def start_server_process(port):
    # print directory
    # shell out to the 2.7 python included in the OS
    settings = load_settings()

    python = find_python(settings)

    cmd = [ python, 
            os.path.join( plugin_dir(), "support", "ipython_send.py"), "-s", "-p", str(port), "-d"
            ]
    if settings.has("daemon_args"):
        for arg in settings.get("daemon_args"):
            cmd.append(arg)

    print "starting server process [%s]" % ' '.join(cmd)

    server_process = subprocess.Popen(cmd,
            stdout = subprocess.PIPE, stderr = subprocess.PIPE)    

    (stdout,stderr) = server_process.communicate()

    exitcode = server_process.wait()
    
    if exitcode != 0:
        for out in [stdout, stderr]:
            if out is not None:
                print out
        raise RuntimeException("Unable to start daemon process exitcode : %d" % exitcode)
    

def attempt_new_socket(port, start_server = True):
    print "attempt_new_socket(%d)" % port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", port))
        return s
    except socket.error as err:
        if start_server: 
            start_server_process(port)
            time.sleep(1)
            return attempt_new_socket( port, start_server = False )
        else:
            raise err

class Client:   
    def __init__(self, port = 48721):
        self.port = port

    def execute(self, code):        

        s = attempt_new_socket(self.port)
        try:
            connection = Connection(s)
            connection.write_message( 1, str(code))
            (msgtype, payload) = connection.read_message()

            print "[%s] [%s]" % (msgtype, payload)
            return msgtype == 2
        finally:
            s.close()

class SendToIpythonCommand(sublime_plugin.TextCommand):
 
    def run(self, edit):
        """
            send the current selection (or whole buffer if no selection)
            to the ipython process.
        """ 
        
        if not hasattr(self, 'output_view' ):
            self.output_view = self.view.window().get_output_panel("ipython")
            # self.output_view.set("syntax", "Packages/IPython/ipython_output.tmLanaguage")

        sel = self.view.sel()
        if sel[0]:
            text = '\n'.join(self.view.substr(reg) for reg in sel)
        else:
            size = self.view.size()
            text = self.view.substr(sublime.Region(0, size))

        client = Client()

        if client.execute(text):
            self.view.set_status( "ipython", "send to ipython - success" )
        else:
            self.view.set_status( "ipython", "send to ipython - failure" )
 
