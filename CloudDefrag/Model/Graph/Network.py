from abc import ABC
from typing import List

from CloudDefrag.Model.Graph.EnhancedGraph import EnhancedGraph
from CloudDefrag.Model.Graph.Link import Link, PhysicalLink, VirtualLink
from CloudDefrag.Model.Graph.Node import Node, Server, Router, VirtualMachine
from CloudDefrag.Logging.Logger import Logger


class Network(EnhancedGraph, ABC):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._network_nodes = []
        self._network_edges = []
        if "network_nodes" in kwargs:
            for n in kwargs["network_nodes"]:
                self.add_network_node(n)
        if "network_edges" in kwargs:
            for e in kwargs["network_edges"]:
                self.add_network_edge(e)

    @property
    def network_nodes(self):
        return self._network_nodes

    @property
    def network_edges(self):
        return self._network_edges

    def get_links(self) -> List[Link]:
        links = []
        for source, target, attributes in self.edges(data=True):
            links.append(attributes['object'])
        return links

    def get_node_dict(self):
        return {v.node_name: v for v in self.network_nodes}

    def get_links_dict(self):
        return {l.name: l for l in self.get_links()}

    def add_network_node(self, node: Node, **kwargs):
        self._network_nodes.append(node)
        self.add_node(node, **kwargs)

    def add_network_edge(self, edge: Link, **kwargs):
        self._network_edges.append(edge)
        self.add_edge(edge.source, edge.target, object=edge)

    def get_link_between(self, n1: Node, n2: Node) -> Link:
        return self.get_edge_data(n1, n2)["object"]

    def get_link_by_name_between(self, n_str1: str, n_str2: str) -> VirtualLink:
        nodes_dict = self.get_node_dict()
        n1 = nodes_dict[n_str1]
        n2 = nodes_dict[n_str2]
        return self.vm_net.get_edge_data(n1, n2)["object"]


class PhysicalNetwork(Network):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Logger.log.info(f"Created physical network {self.name}")

    def get_servers(self) -> List[Server]:
        servers = []
        for node in list(self.nodes):
            if isinstance(node, Server):
                servers.append(node)
        return servers

    def get_routers(self) -> List[Router]:
        routers = []
        for node in list(self.nodes):
            if isinstance(node, Router):
                routers.append(node)
        return routers

    def gateway_routers(self) -> List[Router]:
        routers = []
        for node in list(self.nodes):
            if isinstance(node, Router):
                if node.is_gateway:
                    routers.append(node)
        return routers


class VirtualNetwork(Network):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Logger.log.info(f"Created virtual network {self.name}")

    def get_vms(self) -> List[VirtualMachine]:
        vms = []
        for node in list(self.nodes):
            if isinstance(node, VirtualMachine):
                vms.append(node)
        return vms

    def get_vms_dict(self):
        return {v.node_name: v for v in self.vms}

    def get_gateway_router(self) -> Router:
        router = None
        for node in self._network_nodes:
            if isinstance(node, Router):
                if node.is_gateway:
                    router = node
                    return router
        return router
