# SPDX-License-Identifier: GPL-3.0-only
# Modified for ABDA-NL from Schirmi136/ABDA; imported 2026-06-29.
# Modification notice added 2026-09-05. See Git history and THIRD_PARTY_NOTICES.md.

import networkx as nx
import matplotlib.pyplot as plt

class GraphConvert:
    @staticmethod
    def convert_to_networkx_graph(graph, grounded_extension, min_max):
        """
        Converts a given argumentations graph to a printable networkX graph
        """
        G = nx.DiGraph()
        for argument in graph.Arguments:
            G.add_node(argument, Text=str(argument), Label=grounded_extension[argument], MinMaxNumber=min_max.get(argument, "N/A"))
        for attack in graph.Attacks:
            G.add_edge(attack.From, attack.To)
        return G

