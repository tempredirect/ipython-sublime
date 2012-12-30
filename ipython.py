import sys
import os
import sublime, sublime_plugin

import subprocess
import socket
import struct
import time
import threading


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
            raise RuntimeError("python setting points to non existing file [%s]" % python)

    executable = 'pythonw.exe' if os.name == 'nt' else 'python'
    paths = os.environ.get("PATH").split(os.pathsep)
    for path in paths:
        python = os.path.join( os.path.expandvars(path), executable )
        if os.path.exists(python):
            return python

    raise RuntimeError("unable to find [%s] in path [%s]" % (executable, os.environ.get("PATH")))

def start_server_process(port):
    # print directory
    # shell out to the 2.7 python included in the OS
    settings = load_settings()

    python = find_python(settings)

    cmd = [ python, 
            os.path.join( plugin_dir(), "support", "ipython_send.py"), "-s", "-p", str(port)
            ]

    if settings.has("daemon_args"):
        for arg in settings.get("daemon_args"):
            cmd.append(arg)

    print "starting server process [%s]" % ' '.join(cmd)

    if os.name != 'nt':
        cmd.append("--daemon")


    server_process = subprocess.Popen(cmd,
            stdout = subprocess.PIPE, stderr = subprocess.PIPE)    

    if os.name != 'nt':
        (stdout,stderr) = server_process.communicate()

        exitcode = server_process.wait()
        
        if exitcode != 0:
            for out in [stdout, stderr]:
                if out is not None:
                    print out
            raise RuntimeError("Unable to start daemon process exitcode : %d" % exitcode)
    else:
        t = threading.Thread(target = server_process.communicate)
        t.daemon = True
        t.start()

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

    def execute(self, code, callback = None):        

        s = attempt_new_socket(self.port)
        try:
            connection = Connection(s)
            connection.write_message( 1, str(code))
            (msgtype, payload) = connection.read_message()

            success = msgtype == 2
            print "[%s] [%s]" % (msgtype, payload)
            if callback is not None:
                callback(success, payload)
            
            return success
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
            self.output_view.set_syntax_file(os.path.join(plugin_dir(),"ipython_output.tmLanguage"))
            

        sel = self.view.sel()
        if sel[0]:
            text = '\n'.join(self.view.substr(reg) for reg in sel)
        else:
            size = self.view.size()
            text = self.view.substr(sublime.Region(0, size))

        client = Client()

        if client.execute(text, callback = self.on_output):
            self.view.set_status( "ipython", "send to ipython - success" )
        else:
            self.view.set_status( "ipython", "send to ipython - failure" )
 

    def on_output(self, success, payload):

        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.insert(edit, self.output_view.size(), payload)
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)

        self.output_view.show(self.output_view.size())
                
        self.view.window().run_command("show_panel", {"panel": "output.ipython"})