from dockertest.subtest import SubSubtest
from dockertest.images import DockerImages, DockerImage
from dockertest import subtest
from dockertest.containers import DockerContainers
from dockertest.config import get_as_list
from collections import namedtuple
from dockertest.dockercmd import DockerCmd
from dockertest.dockercmd import AsyncDockerCmd
from dockertest.xceptions import DockerTestFail
from subprocess import call, Popen, PIPE
import shlex
import json
import os
import shutil
import re
import time

class redirect(subtest.SubSubtestCaller):
    config_section = 'docker_cli/redirect'


class redirect_base(SubSubtest):

    def systemd_daemon_control(self, daemon_name, action):

        if(action == "start"):
            return Popen(["systemctl", "start", "%s" % daemon_name], stdout=PIPE).stdout.read()
        elif(action == "stop"):
            print "stop"
            daemon = Popen(["systemctl", "stop", "%s" % daemon_name], stdout=PIPE).stdout.read()
            daemons = Popen(["systemctl", "status", "%s" % daemon_name], stdout=PIPE).stdout.read()
            RE_STOP = re.compile(r'inactive')
            match = RE_STOP.search(daemons)
            while not match:
                daemons = Popen(["systemctl", "status", "%s" % daemon_name], stdout=PIPE).stdout.read()
                match = RE_STOP.search(daemons)

            return daemon

        elif(action == "restart"):
            return Popen(["systemctl", "restart", "%s" % daemon_name], stdout=PIPE).stdout
        elif(action == "status"):
            return Popen(["systemctl", "status", "%s" % daemon_name], stdout=PIPE).stdout.read()

    def daemon_parameter_get(self, status, location):

        RE_test = re.compile(r'%s\s.*' % location)
        status = RE_test.search(status)
        return status.group()

    def daemon_parameter_append(self, origin, parameter):

        new = origin + ' ' + parameter
        return new

    def daemon_start(self, parameter):

        daemon = Popen(shlex.split(parameter), stdout=PIPE)
        return daemon.pid

    def daemon_stop(self, parameter):

        daemon_log = Popen(shlex.split(parameter), stdout=PIPE).stdout.read()
        return daemon_log

    def re_search(self, re_command, content):

        result = re_command.search(content)
        if result:
            return result.group()
        else:
            return result

    def image_json(self, image_name):

        inspect_json = DockerCmd(self, 'inspect', [image_name])
        result = inspect_json.execute()
        image_json = result.stdout

        return json.dumps(image_json)

    def makedir(self, dir_name):

        origin = os.getcwd()
        new_dir_name = dir_name
        new_dir = os.path.join(origin, new_dir_name)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)

            return (origin,new_dir)
        else:
            return (origin, new_dir)

    def makefile(self, filename):

        if os.path.exists(filename):
            f = file(filename, "r+")
        else:
            f = file(filename, "w")

        f.close

    def writefile(self, filename, content):

        f = file(filename, "w")
        f.write(content)
        f.close()

    def removefile(self, filename):

        os.remove(filename)

    def removedir(self, upper, current):

        os.chdir(upper)
        os.removedirs(current)

    def pull_process(self, image_name, re_server, re_image):

        dkrcmd = AsyncDockerCmd(self, 'pull', [image_name])
        self.loginfo("Executing background command: %s" % dkrcmd)
        dkrcmd.execute()
        while not dkrcmd:
            self.loginfo("Pulling...")
            time.sleep(3)
        self.sub_stuff["cmdresult"] = dkrcmd.wait()

        pull_server = self.re_search(re_server, str(dkrcmd.wait()))
        pull_fullname = self.re_search(re_image, str(dkrcmd.wait()))
        pull_json = self.image_json(image_name)

        clean = DockerCmd(self, 'rmi', [image_name])
        clean.execute()

        return (pull_server, pull_fullname, pull_json)

    def build_process(self, new_dir, file_name, dockerfile_content, re_server, re_image):

        #setup a new directory
        (origin_dir, new_dir) = self.makedir(new_dir)
        new = os.chdir(new_dir)
        self.makefile(file_name)
        self.writefile(file_name, dockerfile_content)

        #start command
        dcmd = DockerCmd(self, 'build', ['.'],
                                verbose=False)
        result = dcmd.execute()

        #result get
        build_content = result.stdout
        build_server = self.re_search(re_server, build_content)
        build_fullname = self.re_search(re_image, build_content)
        #FIX ME, should use the parameter instead of the self.sub_stuff
        build_json = self.image_json(self.sub_stuff["image_name"])

        #clean image file and image
        dcmd = DockerCmd(self, 'rmi', ['--force', 'rhel7'],
                                 verbose=False)
        dcmd.execute()

        self.removefile(file_name)
        os.chdir(origin_dir)
        self.removedir(origin_dir, new_dir)

        clean = DockerCmd(self, 'rmi', [self.sub_stuff['image_name']])
        clean.execute()

        return (build_server, build_fullname, build_json)

    def initialize(self):
        super(redirect_base, self).initialize()

        #prepare the self_sub_stuff variables
        self.sub_stuff["server"] = self.config["server"]
        self.sub_stuff["image_name"] = self.config["image_name"]
        RE_SERVER = re.compile(r'https://%s.*' % self.config["server"])
        RE_IMAGE = re.compile(r'%s/%s' % (self.config["server"], self.config["image_name"]))
        self.sub_stuff["re_server"] = RE_SERVER
        self.sub_stuff["re_image"] = RE_IMAGE

        #get the docker daemon parameter
        daemon_status = self.systemd_daemon_control("docker", "status")
        daemon_parameter = self.daemon_parameter_get(daemon_status, "/usr/bin/docker")
        new_daemon_parameter = self.daemon_parameter_append(daemon_parameter,
                                                                    "--add-registry=%s"
                                                                    % self.sub_stuff["server"])
        self.sub_stuff["daemon_command"] = new_daemon_parameter
        #stop systemd control docker
        self.systemd_daemon_control("docker", "stop")
        #start docker daemon in forearound with new parameter and get pid
        self.sub_stuff["pid"] = self.daemon_start(new_daemon_parameter)
        time.sleep(3)


    def run_once(self):
        super(redirect_base, self).run_once()

        RE_SERVER = self.sub_stuff["re_server"]
        RE_IMAGE = self.sub_stuff["re_image"]

        (self.sub_stuff["pull_server"],
         self.sub_stuff["pull_fullname"],
         self.sub_stuff["pull_json"]) = self.pull_process(self.sub_stuff["image_name"],
                                                                    RE_SERVER, RE_IMAGE)


        dir_name = "pull-build"
        file_name = "Dockerfile"
        content = "FROM rhel7\n"

        (self.sub_stuff["build_server"],
         self.sub_stuff["build_fullname"],
         self.sub_stuff["build_json"]) = self.build_process(dir_name,
                                                            file_name,
                                                            content,
                                                            RE_SERVER,
                                                            RE_IMAGE)


    def postprocess(self):
        super(redirect_base, self).postprocess()
        print "postprocess"



        if self.sub_stuff["pull_server"] == self.sub_stuff["build_server"]:
            self.loginfo("PASS")
        else:
            raise DockerTestFail("server MISMATCH")

        if self.sub_stuff["pull_fullname"] == self.sub_stuff["build_fullname"]:
            self.loginfo("PASS")
        else:
            raise DockerTestFail("fullname MISMATCH")

        if self.sub_stuff["pull_json"] == self.sub_stuff["build_json"]:
            self.loginfo("PASS")
        else:
            raise DockerTestFail("json MISMATCH")



    def cleanup(self):
        super(redirect_base, self).cleanup()
        print "cleanup"
        self.systemd_daemon_control("docker", "status")
        pid = self.sub_stuff["pid"]
        para = "kill -SIGTERM %s" % pid
        self.daemon_stop(para)
        time.sleep(3)
        recovery = self.systemd_daemon_control("docker", "restart")

class test(redirect_base):
    pass