
import sublime, sublime_plugin

import subprocess
import os  

class SendToIpythonCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        """
            send the current selection (or whole buffer if no selection)
            to the ipython process.
        """ 
        settings = sublime.load_settings("IPython.sublime-settings")

        sel = self.view.sel()
        if sel[0]:
            text = '\n'.join(self.view.substr(reg) for reg in sel)
        else:
            size = self.view.size()
            text = self.view.substr(sublime.Region(0, size))

        directory = os.path.dirname(os.path.realpath(__file__))
        # print directory
        # print "code : %s" % text

        # shell out to the 2.7 python included in the OS
        p = subprocess.Popen(["/usr/bin/python", 
                os.path.join( directory, "support", "ipython_send.py"), "-v", "-c", text], 
                stdin = subprocess.PIPE, stdout = subprocess.PIPE)

        (stdoutdata, stderrdata) = p.communicate()
        exitval = p.wait()

        if exitval != 0 :

            if stdoutdata is not None:
                print stdoutdata
            if stderrdata is not None:
                print stderrdata

        else:
            self.view.set_status( "ipython", "send to ipython - success" )