"""
Test output of the host iptable rules of container
1. Run container and filter its iptables rules on host
2. Check if the rules is affected or expected
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
        self.sub_stuff['long_id'] = None

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
        vnet = []
        tmp_cmd = 'brctl show'
        cmd_result = utils.run(tmp_cmd)
        p = re.compile(r'veth\w+')
        vnet = p.findall(cmd_result.stdout)

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
        tmp_rules_list = tmp_rules.stdout.split('\n')
        for rule in tmp_rules_list:
            if net_device in rule:
                line = rule.split('\n')[0]
                container_rule.append(line)

        return container_rule

    def initialize(self):
        super(iptable_base, self).initialize()
        self._init_stuff()
        self.sub_stuff['subargs'] = self._init_subargs()

    def run_once(self):
        super(iptable_base, self).run_once()

        subargs = self.sub_stuff['subargs']
        container = NoFailDockerCmd(self.parent_subtest,
                                           'run -d -t',
                                           subargs, verbose=True).execute()

    def postprocess(self):
        super(iptable_base, self).postprocess()
        self.failif(self.sub_stuff['result'] is False,
                    self.sub_stuff['result_info'])

    def cleanup(self):
        super(iptable_base, self).cleanup()
        if self.config['remove_after_test']:
            dcmd = DockerCmd(self.parent_subtest,
                                 'rm',
                                 ['--force',
                                 self.sub_stuff['name']])
            dcmd.execute()

class iptable_remove(iptable_base):
    """
    Test if container iptable rules removed after stopped
    """
    def run_once(self):
        super(iptable_remove, self).run_once()

        added_rules = []
        removed_rules = []
        net_device_list = self.sub_stuff['net_device_list']

        if iptable_base.read_veth_device() == net_device_list:
            net_device = self.sub_stuff['net_device_list']
        else:
            net_device = list(set(self.read_veth_device()) - set(net_device_list)).pop()

        added_rules = iptable_base.read_iptable_rules(net_device)
        self.loginfo("Container %s\niptable rule list %s:" %
                      (self.sub_stuff['name'], added_rules))

        NoFailDockerCmd(self.parent_subtest,
                        'stop',
                        [self.sub_stuff['name']]).execute()

        removed_rules = iptable_base.read_iptable_rules(net_device)
        if added_rules == []:
            self.sub_stuff['result'] = False
            self.sub_stuff['result_info'] = """
                                            No rules added when container start
                                            """
        elif removed_rules:
            self.sub_stuff['result'] = False
            self.sub_stuff['result_info'] = """
                                            Container %s
                                            iptables not removed after stopped
                                            Iptable %s
                                            """ \
                                            % (self.sub_stuff['name'],
                                             removed_rules)


