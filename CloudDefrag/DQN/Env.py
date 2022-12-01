import random
import numpy as np
import random
import re
from enum import Enum

from CloudDefrag.Model.Algorithm.BinpackHeur import BinpackHeur
from CloudDefrag.Model.Algorithm.SpreadHeur import SpreadHeur
from CloudDefrag.Model.Graph.Network import PhysicalNetwork
from CloudDefrag.Parsing.InputParser import InputParser
from CloudDefrag.Parsing.OutputParser import OutputParser
from CloudDefrag.Visualization.Visualizer import NetworkVisualizer


class Actions(Enum):
    DO_NOTHING = 0  # A0
    BIN_PACK = 1  # A1
    SPREAD = 2  # A2


class Env:

    def __init__(self, **kwargs) -> None:

        self.show_comments = True

        self._current_state = None
        self._input_parser = None
        self._net = None
        self._network_topology = kwargs["network_topology"] if "network_topology" in kwargs else "Reduced"

        # Requests
        self._hosted_requests = None
        self._new_requests = None
        self._initial_request = None
        self._current_request = None
        self.requests_allocated_so_far = None
        self.request_index = None

        # Time
        self.current_time_step = 0
        self.current_episode = 0

        # Reset and set initial state vector
        self.reset()
        self._state_vector_size = len(self._net.get_servers()) * 3 + len(self._net.get_links()) * 2 + 2

        # Actions
        self._action_space_size = len(Actions)

        # Rewards
        self._initial_reward = self._net.compute_gateway_connectivity()

    @property
    def is_done(self):
        if not self._new_requests:
            return True
        else:
            return False

    @property
    def current_state(self):
        return self._current_state

    @current_state.setter
    def current_state(self, value):
        self._current_state = value

    @property
    def net(self):
        return self._net

    @net.setter
    def net(self, value):
        self._net = value

    @property
    def new_requests(self):
        return self._new_requests

    @new_requests.setter
    def new_requests(self, value):
        self._new_requests = value

    def reset(self):
        # Create the network
        self.net, self._input_parser = create_network(f"Net_DQN_ENV_Ep{self.current_episode}", self._network_topology)

        # Create Requests
        make_random_new_requests = False
        self._hosted_requests, self.new_requests = create_requests(self._input_parser, make_random_new_requests)
        self._input_parser.assign_hosted_requests()

        self.requests_allocated_so_far = 0
        self.request_index = 0

        # Set initial request to the first request in new requests list
        if self._new_requests:
            self._initial_request = self._new_requests[0]
        else:
            self._initial_request = 0

        # Create initial state
        initial_state = self.__get_state_vector()

        self._current_request = self._initial_request
        self.current_state = initial_state
        if self.show_comments:
            print("Did reset!")
        return initial_state

    def get_random_action(self):
        return np.random.randint(0, self._action_space_size)

    def step(self, action: int):
        new_state = None
        reward = 0  # Initial value for reward
        if self.show_comments:
            print(f"Request: {self.request_index+1}")

        if action == 0:  # A0: Bin-Pack
            if self.show_comments:
                print("Take action BinPack!")
            heur = BinpackHeur(self._net, [self._current_request], self._hosted_requests, model_name=f"BinPack")
            heur.solve(display_result=False)

            if heur.heuristic_result.is_success:
                if self.show_comments:
                    print("Allocated request!")
                heur.display_result()
                reward += self._net.compute_gateway_connectivity()
                self.requests_allocated_so_far += 1
                # if self.requests_allocated_so_far == self.number_of_requests:
                #     reward += self._allocate_all_reward
            else:
                if self.show_comments:
                    print("Failed Allocation!")
                # reward -= self._blocked_penalty



            new_state = self.__get_state_vector()

        elif action == 1:  # A1: Spread
            if self.show_comments:
                print("Take action Spread!")
            heur = SpreadHeur(self._net, [self._current_request], self._hosted_requests, model_name=f"Spread")
            heur.solve(display_result=False)
            if heur.heuristic_result.is_success:
                heur.display_result()
                reward += self._net.compute_gateway_connectivity()
                self.requests_allocated_so_far += 1
                if self.show_comments:
                    print("Allocated request!")
                # if self.requests_allocated_so_far == self.number_of_requests:
                #     reward += self._allocate_all_reward
            else:
            #     reward -= self._blocked_penalty
                if self.show_comments:
                    print("Failed Allocation!")
            new_state = self.__get_state_vector()

        elif action == 2:  # A2: Do-Nothing
            if self.show_comments:
                print("Take action DoNothing!")
            new_state = self.current_state
            # reward -= self._do_nothing_penalty

        if self.show_comments:
            print(f"Reward: {reward}")
        # Remove the current request and get next one if any
        if self._current_request in self.new_requests:
            self.new_requests.remove(self._current_request)

        self.request_index += 1

        if self.is_done:
            done = True
            if self.show_comments:
                print(f"Done with all requests: {reward}")
        else:
            done = False
            self._current_request = self.new_requests[0]

        self.current_state = new_state

        return new_state, reward, done

    def __get_state_vector(self):
        state_vector = []
        # Compute nodes information
        for node in self._net.get_servers():
            state_vector.append(node.available_specs.cpu)
            state_vector.append(node.available_specs.memory)
            state_vector.append(node.available_specs.storage)
        # Links information
        for link in self._net.get_links():
            state_vector.append(link.link_specs.available_bandwidth)
            state_vector.append(link.link_specs.propagation_delay)
        # Request information
        state_vector.append(self._initial_request.request_type)
        gateway_name = self._initial_request.gateway_router.node_name
        state_vector.append(int(re.search('w(.+?)', gateway_name).group(1)))
        return state_vector


def create_network(network_name, network_topology):
    net = PhysicalNetwork(name=network_name)
    if network_topology == "Reduced":
        network_nodes_file = "input/ReducedTopo/01-NetworkNodes.csv"
        network_connections_file = "input/ReducedTopo/02-NetworkConnections.csv"
    elif network_topology == "Regional":
        network_nodes_file = "input/RegionalTopo/01-NetworkNodes.csv"
        network_connections_file = "input/RegionalTopo/02-NetworkConnections.csv"
    input_parser = InputParser(net, network_nodes_file=network_nodes_file,
                               network_connections_file=network_connections_file)
    return net, input_parser


def create_requests(input_parser, make_random_new_requests):
    # Todo: Generalize make_random_new_requests
    hosted_requests = input_parser.get_all_hosted_requests()
    if make_random_new_requests:
        new_requests, req_dist = input_parser.get_random_new_requests_from_gateway("w3",
                                                                                   seed_number=0)  # This bypass requests dist. file
    else:
        new_requests = input_parser.get_all_new_requests()
    return hosted_requests, new_requests
