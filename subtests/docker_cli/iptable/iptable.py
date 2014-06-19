"""
Test output of the host iptable rules of container
1. Run container and parse/gather it's iptable rules on host.
2. Check if rules are affected as expected/are handled properly.
"""
# Okay to be less-strict for these cautions/warnings in subtests
# pylint: disable=C0103,C0111,R0904,C0103

from dockertest.dockercmd import NoFailDockerCmd
from dockertest.dockercmd import DockerCmd
from dockertest.containers import DockerContainers
from dockertest.images import DockerImage
from dockertest.subtest import SubSubtest
from dockertest.subtest import SubSubtestCallerSimultaneous
from autotest.client import utils
import re

class iptable(SubSubtestCallerSimultaneous):

    pass


class iptable_base(SubSubtest):

    def _init_stuff(self):
        """
        Initialize stuff parameters
        """
        self.sub_stuff['subargs'] = None
        self.sub_stuff['rule'] = []
        self.sub_stuff['result'] = True
        self.sub_stuff['result_info'] = []
        self.sub_stuff['name'] = None
        self.sub_stuff['net_device_list'] = self.read_veth_device()
        self.sub_stuff['net_device'] = None

    def _init_subargs(self):
        """
        Initialize basic arguments that will use for start container
        Will return a list 'args'
        """
        docker_containers = DockerContainers(self.parent_subtest)
        image = DockerImage.full_name_from_defaults(self.config)
        prefix = self.config['name_prefix']
        name = docker_containers.get_unique_name(prefix, length=4)
        self.sub_stuff['name'] = name
        bash_cmd = self.config['bash_cmd']
        args = ["--name=%s" % name,
                image,
                bash_cmd]

        return args

    @staticmethod
    def read_veth_device():
        """
        Temp method to get container net device name
        """
        tmp_cmd = 'brctl show'
        cmd_result = utils.run(tmp_cmd)
        vnet = re.findall(r'veth\w+', cmd_result.stdout)

        return vnet

    @staticmethod
    def read_iptable_rules(vnet):
        """
        Find container related iptable rule
        param vnet: The container's virtual net card, for now
                    can get it through 'brctl show' after container
                    started
        """
        tmp_cmd = 'iptables -L -n -v'
        net_device = vnet
        container_rule = []
        tmp_rules = utils.run(tmp_cmd)
        tmp_rules_list = tmp_rules.stdout.splitlines()

        for rule in tmp_rules_list:
            if net_device in rule:
                line = rule
                container_rule.append(line)

        return container_rule

    def initialize(self):
        super(iptable_base, self).initialize()
        self._init_stuff()
        self.sub_stuff['subargs'] = self._init_subargs()

    def run_once(self):
        super(iptable_base, self).run_once()
        subargs = self.sub_stuff['subargs']
        NoFailDockerCmd(self.parent_subtest,
                        'run -d -t',
                        subargs, verbose=True).execute()

    def postprocess(self):
        super(iptable_base, self).postprocess()

    def cleanup(self):
        super(iptable_base, self).cleanup()
        if self.config['remove_after_test']:
            dcmd = DockerCmd(self.parent_subtest,
                                 'rm',
                                 ['--force',
                                  '--volumes',
                                 self.sub_stuff['name']])
            dcmd.execute()


class iptable_remove(iptable_base):
    """
    Test if container iptable rules are removed after stopped
    """
    def run_once(self):
        super(iptable_remove, self).run_once()
        net_device_list = set(self.read_veth_device()).\
                             difference(self.sub_stuff['net_device_list'])
        self.failif(len(net_device_list) != 1,
                    "Can't obtain network device of the tested container,"
                    "difference of list of net devices before/after is %s"
                    % net_device_list)
        self.sub_stuff['net_device'] = net_device_list.pop()

    def postprocess(self):
        net_device = self.sub_stuff['net_device']
        container_rules = lambda: self.read_iptable_rules(net_device)
        added_rules = utils.wait_for(container_rules, 10, step = 0.1)
        self.failif(not added_rules, "No rules added when container started.")
        self.loginfo("Container %s\niptable rule list %s:" %
                      (self.sub_stuff['name'], added_rules))

        NoFailDockerCmd(self.parent_subtest,
                        'stop',
                        ["-t 0", self.sub_stuff['name']]).execute()

        container_rules = lambda: not self.read_iptable_rules(net_device)
        removed_rules = utils.wait_for(container_rules, 10, step=0.1)
        self.failif(not removed_rules, "Container %s iptable rules not "
                    "removed in 10s after stop. Rules:\n%s"
                    % (self.sub_stuff['name'],
                       self.read_iptable_rules(net_device)))
