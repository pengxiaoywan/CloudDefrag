from typing import List
import itertools
import gurobipy as gp

from CloudDefrag.Model.Algorithm.Algorithm import Algorithm
from CloudDefrag.Model.Algorithm.Request import VMRequest, NewVMRequest, HostedVMRequest
from CloudDefrag.Model.Graph import Network
from CloudDefrag.Model.Graph.Network import PhysicalNetwork
from CloudDefrag.Model.Graph.Node import VirtualMachine, Router, Server, DummyVirtualMachine
from CloudDefrag.Logging.Logger import Logger


class RamyILP(Algorithm):
    """
        RamyILP is ILP algorithm that that takes into account hosted and new requests and model vnf migration
    """
    def __init__(self, net: PhysicalNetwork, new_requests: List[NewVMRequest], hosted_requests: List[HostedVMRequest],
                 **kwargs) \
            -> None:
        super().__init__(net, new_requests, hosted_requests, **kwargs)

    def _create_problem_model(self):
        # Create decision variables for the model
        self._create_decision_variables()

        # Objective: minimize total all new VMs assignments
        self._create_objective_function()

        # Servers Resource Capacity Constraints
        # Ensure that servers are not overused
        self._create_servers_resource_capacity_constrs()

        # Links B.W Capacity Constraints
        # Ensure that Links B.W are not overused
        self._create_links_bw_capacity_constrs()

        # Links Prop. Delay Constraints
        # Ensure that Links Links Prop. Delay are respected
        self._create_prop_delay_constrs()

        # E2E delay constrs
        # Ensure that the E2E delay requirement is met
        self._create_e2e_delay_constrs()

        # TODO: Add server processing delay constraints

        # Flow conservation constraint
        # Verifies that there will be a virtual link between each two consecutive VMs hosted on two different servers.
        self._create_flow_conservation_constr()

        # VM Single Host Constraints
        # Ensure that each VM is hosted by exactly one node
        self._create_single_host_constrs()

        # VM Single Server Constraints
        # Ensure that each VM is hosted by exactly one server
        self._create_single_server_constrs()

        # Ensure that dummy vms are placed only at their gateway routers
        self._create_dummy_vm_constrs()

    def _create_decision_variables(self):
        # New VMs Assignment variables
        for new_req in self._new_requests:
            new_req.new_vms_assign_vars = self._model.addVars(new_req.requested_vms_combinations,
                                                              name=f"new_assign", vtype=gp.GRB.BINARY)
            new_req.new_vlinks_assign_vars = self._model.addVars(new_req.requested_vlinks_combinations,
                                                                 name=f"new_assign", vtype=gp.GRB.BINARY)

        # Hosted VMs Assignment variables after migration
        for hosted_req in self._hosted_requests:
            hosted_req.hosted_vms_assign_vars = self._model.addVars(hosted_req.hosted_vms_combinations,
                                                                    name=f"hosted_assign", vtype=gp.GRB.BINARY)
            hosted_req.hosted_vlinks_assign_vars = self._model.addVars(hosted_req.hosted_vlinks_combinations,
                                                                       name=f"hosted_assign", vtype=gp.GRB.BINARY)

    def _create_objective_function(self):
        # Revenue PI
        revenue = 0
        for new_req in self._new_requests:
            revenue += new_req.new_vms_assign_vars.prod(new_req.requested_vms_servers_revenue)

        # Cost Kappa
        cost = 0
        # vm_migration_cost and vlink_migration_cost
        for hosted_req in self._hosted_requests:
            # vm_migration_cost
            vm_assign_dict = hosted_req.hosted_vms_servers_assign_dict
            y = hosted_req.hosted_vms_assign_vars
            vms_dict = hosted_req.hosted_vms_dict
            vms_combinations = hosted_req.hosted_vms_combinations
            vm_migration_cost = gp.quicksum((vm_assign_dict[v, s] * (1 - y[v, s])) *
                                            vms_dict[v].vm_migration_coeff for v, s in vms_combinations)

            # vlink_migration_cost
            vlink_assign_dict = hosted_req.hosted_vlink_assign_dict
            vl = hosted_req.hosted_vlinks_assign_vars
            vlinks_dict = hosted_req.hosted_vlinks_dict
            vlink_migrate_cost_dict = hosted_req.hosted_vlink_migrate_cost_dict
            vlinks_combination = hosted_req.hosted_vlinks_combinations
            vlink_migration_cost = gp.quicksum((vlink_assign_dict[v, s] * (1 - vl[v, s])) *
                                               vlink_migrate_cost_dict[v, s] for v, s in vlinks_combination)
            self._model.update()
            cost += vm_migration_cost + vlink_migration_cost
            #TODO: Add hosted vlink assign cost
        # New vlinks assign cost
        for new_req in self._new_requests:
            new_vlinks_assign_cost = new_req.new_vlinks_assign_vars.prod(new_req.requested_vlinks_cost)
            cost += new_vlinks_assign_cost

        self._model.setObjective(revenue - cost, gp.GRB.MAXIMIZE)

    def _create_servers_resource_capacity_constrs(self):
        # Resource Capacity Constraints: CPU, Memory & Storage (Group C1)
        for s in self._servers_names:
            # New requests terms
            new_requests_cpu_req_term = 0
            new_requests_memory_req_term = 0
            new_requests_storage_req_term = 0
            for new_req in self._new_requests:
                x = new_req.new_vms_assign_vars
                requested_vms_dict = new_req.requested_vms_dict
                requested_vms_names = new_req.requested_vms_names

                new_requests_cpu_req_term += gp.quicksum((x[v, s] * requested_vms_dict[v].specs.cpu) for v in
                                                         requested_vms_names)
                new_requests_memory_req_term += gp.quicksum((x[v, s] * requested_vms_dict[v].specs.memory) for v in
                                                            requested_vms_names)
                new_requests_storage_req_term += gp.quicksum((x[v, s] * requested_vms_dict[v].specs.storage) for v in
                                                             requested_vms_names)

            # Hosted requests terms
            hosted_requests_cpu_req_term = 0
            hosted_requests_memory_req_term = 0
            hosted_requests_storage_req_term = 0
            for hosted_req in self._hosted_requests:
                y = hosted_req.hosted_vms_assign_vars
                hosted_vms_dict = hosted_req.hosted_vms_dict
                hosted_vms_names = hosted_req.hosted_vms_names
                hosted_requests_cpu_req_term += gp.quicksum((y[v, s] * hosted_vms_dict[v].specs.cpu) for v in
                                                            hosted_vms_names)
                hosted_requests_memory_req_term += gp.quicksum((y[v, s] * hosted_vms_dict[v].specs.memory) for v in
                                                               hosted_vms_names)
                hosted_requests_storage_req_term += gp.quicksum((y[v, s] * hosted_vms_dict[v].specs.storage) for v in
                                                                hosted_vms_names)

            self._servers_dict[s].server_cpu_constrs = self._model.addConstr(
                (hosted_requests_cpu_req_term + new_requests_cpu_req_term <= self._servers_dict[s].available_specs.cpu),
                name=f"C1_{self._servers_dict[s].node_name}_cpu_cap")

            self._servers_dict[s].server_memory_constrs = self._model.addConstr(
                (hosted_requests_memory_req_term + new_requests_memory_req_term <=
                 self._servers_dict[s].available_specs.memory), name=f"C1_{self._servers_dict[s].node_name}_memory_cap")

            self._servers_dict[s].server_storage_constrs = self._model.addConstr(
                (hosted_requests_storage_req_term + new_requests_storage_req_term <=
                 self._servers_dict[s].available_specs.storage), name=f"C1_{self._servers_dict[s].node_name}_storage_cap")

    def _create_links_bw_capacity_constrs(self):
        # BW Capacity Constraints: (Group C2)
        for link in self._physical_links:
            plink1 = link.name
            plink2 = link.reverse_name
            # New requests terms
            new_requests_bw_req_term = 0
            for new_req in self._new_requests:
                vlink_vars = new_req.new_vlinks_assign_vars
                requested_vlinks_dict = new_req.requested_vlinks_dict
                requested_vlinks_names = new_req.requested_vlinks_names
                new_requests_bw_req_term += gp.quicksum(((vlink_vars[v, plink1] + vlink_vars[v, plink2]) *
                                                         requested_vlinks_dict[v].link_specs.bandwidth) for v in
                                                        requested_vlinks_names)
            # Hosted requests terms
            hosted_requests_bw_req_term = 0
            for hosted_req in self._hosted_requests:
                vlink_vars = hosted_req.hosted_vlinks_assign_vars
                hosted_vlinks_dict = hosted_req.hosted_vlinks_dict
                hosted_vlinks_names = hosted_req.hosted_vlinks_names
                hosted_requests_bw_req_term += gp.quicksum(((vlink_vars[v, plink1] + vlink_vars[v, plink2]) *
                                                            hosted_vlinks_dict[v].link_specs.bandwidth) for v in
                                                           hosted_vlinks_names)

            link.bw_constrs = self._model.addConstr((new_requests_bw_req_term + hosted_requests_bw_req_term) <=
                                                    link.link_specs.available_bandwidth, name=f"C2_{link.name}_bw_cap")

    def _create_e2e_delay_constrs(self):
        # E2E delay Constraints:  (Group C3)
        # TODO: Add the processing delay and other kind of delays in the e2e constr.
        for new_req in self._new_requests:
            e2e_delay_req = new_req.e2e_delay
            link_vars = new_req.new_vlinks_assign_vars
            vlink_prop_delay_term = link_vars.prod(new_req.requested_vlinks_prop_delay)
            gw_name = new_req.gateway_router.node_name
            new_req.e2e_delay_constr = self._model.addConstr(vlink_prop_delay_term <= e2e_delay_req,
                                                             name=f"C3_new_req{new_req.request_id}_e2e_delay_{gw_name}")

        for hosted_req in self._hosted_requests:
            e2e_delay_req = hosted_req.e2e_delay
            link_vars = hosted_req.hosted_vlinks_assign_vars
            vlink_prop_delay_term = link_vars.prod(hosted_req.hosted_vlinks_prop_delay)
            gw_name = new_req.gateway_router.node_name
            hosted_req.e2e_delay_constr = self._model.addConstr(vlink_prop_delay_term <= e2e_delay_req,
                                                                name=f"C3_hosted_req{hosted_req.request_id}_e2e_delay_{gw_name}")

    def _create_prop_delay_constrs(self):
        # Propagation delay Constraints:  (Group C4)
        plinks_dict = self._physical_links_dict
        for new_req in self._new_requests:
            gw_name = new_req.gateway_router.node_name
            link_vars = new_req.new_vlinks_assign_vars
            vlinks_dict = new_req.requested_vlinks_dict
            for vlink in new_req.requested_vlinks_names:
                req_prop_delay = vlinks_dict[vlink].link_specs.propagation_delay
                vlink_prop_delay_req_term = gp.quicksum(((link_vars[vlink, plink.name] +
                                                          link_vars[vlink, plink.reverse_name]) *
                                                         plink.link_specs.propagation_delay) for plink in
                                                        self._physical_links)
                vlinks_dict[vlink].prop_delay_req_constr = \
                    self._model.addConstr(vlink_prop_delay_req_term <= req_prop_delay,
                                          name=f"C4_new_req{new_req.request_id}_vlink_{vlink}_prop_delay_{gw_name}")
        for hosted_req in self._hosted_requests:
            gw_name = new_req.gateway_router.node_name
            link_vars = hosted_req.hosted_vlinks_assign_vars
            vlinks_dict = hosted_req.hosted_vlinks_dict
            for vlink in hosted_req.hosted_vlinks_names:
                req_prop_delay = vlinks_dict[vlink].link_specs.propagation_delay
                vlink_prop_delay_req_term = gp.quicksum(((link_vars[vlink, plink.name] +
                                                          link_vars[vlink, plink.reverse_name]) *
                                                         plink.link_specs.propagation_delay) for plink
                                                        in self._physical_links)
                vlinks_dict[vlink].prop_delay_req_constr = \
                    self._model.addConstr(vlink_prop_delay_req_term <= req_prop_delay,
                                          name=f"C4_hosted_req{hosted_req.request_id}_vlink_{vlink}_prop_delay_{gw_name}")

    def _create_flow_conservation_constr(self):
        # Flow Conservation Constraints:  (Group C5)
        nodes = self._nodes
        nodes_names = self._nodes_names
        nodes_dict = self._nodes_dict

        for new_req in self._new_requests:
            link_vars = new_req.new_vlinks_assign_vars
            vlinks_dict = new_req.requested_vlinks_dict
            vm_vars = new_req.new_vms_assign_vars
            vm_dict = new_req.requested_vms_dict
            for vlink in new_req.requested_vlinks_names:
                source = vlinks_dict[vlink].source
                target = vlinks_dict[vlink].target
                for u in nodes_names:
                    rhs = vm_vars[source.node_name, u] - vm_vars[target.node_name, u]
                    lhs = 0
                    for v in nodes_names:
                        if u == v:
                            continue
                        else:
                            if self._network.has_edge(nodes_dict[u], nodes_dict[v]):
                                var1 = f"({source.node_name},{target.node_name})", f"({u},{v})"
                                var2 = f"({source.node_name},{target.node_name})", f"({v},{u})"
                                lhs += link_vars[var1] - link_vars[var2]
                    self._model.addConstr(lhs == rhs, name=f"C5_flow_cons_{vlink}_{u}")

        for hosted_req in self._hosted_requests:
            link_vars = hosted_req.hosted_vlinks_assign_vars
            vlinks_dict = hosted_req.hosted_vlinks_dict
            vm_vars = hosted_req.hosted_vms_assign_vars
            for vlink in hosted_req.hosted_vlinks_names:
                source = vlinks_dict[vlink].source
                target = vlinks_dict[vlink].target
                for u in nodes_names:
                    rhs = vm_vars[source.node_name, u] - vm_vars[target.node_name, u]
                    lhs = 0
                    for v in nodes_names:
                        if u == v:
                            continue
                        else:
                            if self._network.has_edge(nodes_dict[u], nodes_dict[v]):
                                var1 = f"({source.node_name},{target.node_name})", f"({u},{v})"
                                var2 = f"({source.node_name},{target.node_name})", f"({v},{u})"
                                lhs += link_vars[var1] - link_vars[var2]
                    self._model.addConstr(lhs == rhs, name=f"C5_flow_cons_{vlink}_{u}")

    def _create_single_host_constrs(self):
        # Single Host Constraints:  (Group C6)
        for new_req in self._new_requests:
            x = new_req.new_vms_assign_vars
            requested_vms_names = new_req.requested_vms_names
            self._model.addConstrs((x.sum(v, '*') <= 1 for v in requested_vms_names)
                                   , name='C6_requested_vm_single_host')

        for hosted_req in self._hosted_requests:
            y = hosted_req.hosted_vms_assign_vars
            hosted_vms_names = hosted_req.hosted_vms_names
            self._model.addConstrs((y.sum(v, '*') == 1 for v in hosted_vms_names)
                                   , name='C6_hosted_vm_single_host')

    def _create_single_server_constrs(self):
        # Single server Constraints:  (Group C7)
        server_names = self._servers_names
        for new_req in self._new_requests:
            vars = new_req.new_vms_assign_vars
            vms = new_req.vm_net.get_vms_except_dummy()
            vms_names = [vm.node_name for vm in vms]
            for vm in vms_names:
                term = gp.quicksum(vars[vm, s] for s in server_names)
                self._model.addConstr(term == 1, name=f'C7_requested_vm_single_server[{vm}]')

        for hosted_req in self._hosted_requests:
            vars = hosted_req.hosted_vms_assign_vars
            vms = hosted_req.vm_net.get_vms_except_dummy()
            vms_names = [vm.node_name for vm in vms]
            for vm in vms_names:
                term = gp.quicksum(vars[vm, s] for s in server_names)
                self._model.addConstr(term == 1, name=f'C7_hosted_vm_single_server[{vm}]')

    def _create_dummy_vm_constrs(self):
        # Dummy VM Constraints:  (Group C8)
        for new_req in self._new_requests:
            vars = new_req.new_vms_assign_vars
            gateway_router = new_req.gateway_router
            dummy_vm = new_req.vm_net.get_dummy_vm()
            dummy_var = vars[dummy_vm.node_name, gateway_router.node_name]
            self._model.addConstr(dummy_var == 1, name=f"C8_req{new_req.request_id}_dummy_vm")

        for hosted_req in self._hosted_requests:
            vars = hosted_req.hosted_vms_assign_vars
            gateway_router = hosted_req.gateway_router
            dummy_vm = hosted_req.vm_net.get_dummy_vm()
            dummy_var = vars[dummy_vm.node_name, gateway_router.node_name]
            self._model.addConstr(dummy_var == 1, name=f"C8_req{hosted_req.request_id}_dummy_vm")





