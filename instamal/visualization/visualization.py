import logging
import math
import os
import re
from typing import Dict, List

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
from networkx import MultiGraph

from maltoolbox.language import LanguageGraph, LanguageGraphAssociation
from maltoolbox.model import Model

logger = logging.getLogger(__name__)


class ModelVisualizer:
    def __init__(self, model_dir: str, n: int, lang_path: str) -> None:
        """
        model_dir : directory containing generated model .yml files
        n         : number of models to visualize
        lang_path : path to the MAL language file
        """
        self.model_dir = model_dir
        self.vis_dir = os.path.join(model_dir, 'vis')
        self.n = n

        self.lang_graph = LanguageGraph().load_from_file(lang_path)
        self.type_to_color = self._create_type_color_map()

        model_files = sorted(
            (
                f
                for f in os.listdir(model_dir)
                if f.endswith(('.yml', '.yaml', '.json'))
            ),
            key=self._sort_key,
        )
        self._model_files = model_files[:n]
        self._model_paths = [os.path.join(model_dir, f) for f in self._model_files]

        # Build stable prefix → integer mapping from all models upfront
        self.prefix_to_int: Dict[str, int] = self._build_prefix_map(self._model_paths)
        self.int_to_prefix: Dict[int, str] = {
            v: k for k, v in self.prefix_to_int.items()
        }

    def render(self) -> None:
        """Render all models to SVG files and a combined PDF summary.

        Clears the vis directory before writing new output.
        """
        os.makedirs(self.vis_dir, exist_ok=True)
        for f in os.listdir(self.vis_dir):
            if os.path.isfile(os.path.join(self.vis_dir, f)):
                os.remove(os.path.join(self.vis_dir, f))

        total = len(self._model_files)
        pdf_path = os.path.join(self.model_dir, 'summary.pdf')
        with PdfPages(pdf_path) as pdf:
            for i, (filename, path) in enumerate(
                zip(self._model_files, self._model_paths)
            ):
                print(f'Visualizing models: {i}/{total}', end='\r', flush=True)
                graph = self._read_graph_from_file(path)
                svg_name = os.path.splitext(filename)[0] + '.svg'
                dest = os.path.join(self.vis_dir, svg_name)
                self._render_graph(graph, dest, pdf)

        print(f'Visualizing models: {total}/{total}')

    # Internal helpers

    def _sort_key(self, filename: str) -> int:
        match = re.search(r'(\d+)', filename)
        return int(match.group(1)) if match else 0

    def _build_prefix_map(self, model_paths: List[str]) -> Dict[str, int]:
        """Scan all model files and assign a stable integer to each unique
        asset name prefix (the part before the last ':' in an asset name)."""
        prefixes = set()
        for path in model_paths:
            try:
                model = Model.load_from_file(path, self.lang_graph)
                for asset in model.assets.values():
                    prefix = asset.name.rsplit(':', 1)[0]
                    prefixes.add(prefix)
            except Exception as e:
                logger.warning(f'Could not read model file {path}: {e}')

        return {prefix: i + 1 for i, prefix in enumerate(sorted(prefixes))}

    def _asset_label(self, asset_name: str) -> str:
        """Map an asset name to its integer label string."""
        prefix = asset_name.rsplit(':', 1)[0]
        return str(self.prefix_to_int.get(prefix, '?'))

    def _create_type_color_map(self) -> Dict[str, tuple]:
        asset_types = sorted(self.lang_graph.assets.keys())
        cmap = plt.get_cmap('tab20')
        return {
            asset_type: cmap(i % cmap.N) for i, asset_type in enumerate(asset_types)
        }

    def _read_graph_from_file(self, path: str) -> MultiGraph:
        """Load a model from disk and build an undirected multigraph from it.

        Each asset becomes a node. Each association present between two assets
        is represented by exactly one undirected edge labelled with the
        association name, regardless of which direction the association was
        traversed.

        In a MAL model, every association between assetA and assetB appears
        as two directed entries in associated_assets: one on assetA pointing
        to assetB (via the right-hand field) and one on assetB pointing back
        to assetA (via the left-hand field). Both entries share the same
        association name. We deduplicate these by tracking the set of
        (frozenset({u, v}), assoc_name) pairs already added, and skipping
        the second direction when we encounter it.

        Two assets may be connected by several distinct associations, each of
        which becomes its own edge in the multigraph so that both are visible
        in the visualisation.
        """
        model = Model.load_from_file(path, self.lang_graph)
        G = nx.MultiGraph()

        for asset in model.assets.values():
            G.add_node(
                asset.name,
                type=asset.type,
                label=self._asset_label(asset.name),
            )

        seen: set[tuple[frozenset, str]] = set()

        for asset in model.assets.values():
            for fieldname, associated_assets in asset.associated_assets.items():
                assoc: LanguageGraphAssociation = asset.lg_asset.associations[fieldname]
                assoc_name = assoc.name

                for other in associated_assets:
                    key = (frozenset({asset.name, other.name}), assoc_name)
                    if key in seen:
                        continue
                    seen.add(key)
                    G.add_edge(asset.name, other.name, label=assoc_name)

        return G

    def _render_graph(self, graph: MultiGraph, dest: str, pdf: PdfPages) -> None:
        """Draw the graph, save as SVG, and append a page to the open PDF."""
        fig, ax = plt.subplots(figsize=(14, 10))

        node_count = len(graph.nodes())
        scale = min(1.0, math.sqrt(40 / node_count) if node_count > 40 else 1.0)

        node_size = 500 * scale
        label_fontsize = 12 * math.sqrt(scale)
        edge_fontsize = 8 * math.sqrt(scale)

        pos = nx.spring_layout(graph, k=0.4, iterations=200)

        node_types = nx.get_node_attributes(graph, 'type')
        node_labels = nx.get_node_attributes(graph, 'label')
        node_colors = [self.type_to_color[node_types[node]] for node in graph.nodes()]

        nx.draw_networkx_nodes(
            graph,
            pos,
            node_color=node_colors,
            node_size=node_size,
            alpha=0.9,
            ax=ax,
        )
        nx.draw_networkx_labels(
            graph,
            pos,
            labels=node_labels,
            font_size=label_fontsize,
            ax=ax,
        )
        nx.draw_networkx_edges(graph, pos, alpha=0.4, ax=ax)

        # Build a combined label string per node pair, joining all association
        # names that appear on edges between the same two nodes.
        edge_label_map: Dict[tuple, list] = {}
        for u, v, data in graph.edges(data=True):
            pair = (u, v)
            edge_label_map.setdefault(pair, []).append(data['label'])
        edge_labels = {pair: ', '.join(names) for pair, names in edge_label_map.items()}
        nx.draw_networkx_edge_labels(
            graph,
            pos,
            edge_labels=edge_labels,
            font_size=edge_fontsize,
            ax=ax,
        )

        self._draw_legend(ax, node_types, node_labels)

        ax.axis('off')
        fig.savefig(dest, bbox_inches='tight')
        pdf.savefig(fig, bbox_inches='tight')
        plt.close(fig)

    def _draw_legend(
        self,
        ax: Axes,
        node_types: Dict[str, str],
        node_labels: Dict[str, str],
    ) -> None:
        present_types = set(node_types.values())
        present_labels = set(node_labels.values())

        color_entries = [
            Patch(facecolor=self.type_to_color[t], edgecolor='grey', label=t)
            for t in sorted(present_types)
        ]

        int_entries = [
            mlines.Line2D(
                [],
                [],
                marker='none',
                linestyle='none',
                label=f'{lbl}: {self.int_to_prefix[int(lbl)]}',
            )
            for lbl in sorted(
                present_labels, key=lambda x: int(x) if x.isdigit() else 0
            )
            if lbl.isdigit() and int(lbl) in self.int_to_prefix
        ]

        separator = mlines.Line2D([], [], marker='none', linestyle='none', label=' ')

        ax.legend(
            handles=color_entries + [separator] + int_entries,
            loc='upper left',
            bbox_to_anchor=(1.01, 1),
            borderaxespad=0,
            fontsize=7,
            framealpha=0.9,
            title='Legend',
            title_fontsize=8,
        )
