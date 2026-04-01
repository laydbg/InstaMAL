import math
import os
import re
from typing import Dict, List

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import networkx as nx
from networkx import MultiGraph

from maltoolbox.language import LanguageGraph, LanguageGraphAssociation
from maltoolbox.model import Model


class ModelVisualizer:
    def __init__(self, model_dir: str, n: int, lang_path: str) -> None:
        """
        model_dir : directory containing generated model .yml files
        n         : number of models to visualize
        lang_path : path to the MAL language file
        """
        self.model_dir = model_dir
        self.vis_dir = os.path.join(model_dir, "vis")

        os.makedirs(self.vis_dir, exist_ok=True)
        existing = [
            f
            for f in os.listdir(self.vis_dir)
            if os.path.isfile(os.path.join(self.vis_dir, f))
        ]
        for f in existing:
            os.remove(os.path.join(self.vis_dir, f))

        model_files = sorted(
            (
                f
                for f in os.listdir(model_dir)
                if f.endswith((".yml", ".yaml", ".json"))
            ),
            key=self._sort_key,
        )

        self.lang_graph = LanguageGraph().load_from_file(lang_path)

        # Stable type → color mapping
        self.type_to_color = self._create_type_color_map()

        # Build stable prefix → integer mapping from all models upfront
        self.prefix_to_int: Dict[str, int] = self._build_prefix_map(
            [os.path.join(model_dir, f) for f in model_files[:n]]
        )
        # Reverse map for legend
        self.int_to_prefix: Dict[int, str] = {
            v: k for k, v in self.prefix_to_int.items()
        }

        pdf_path = os.path.join(self.model_dir, "summary.pdf")
        with PdfPages(pdf_path) as pdf:
            for filename in model_files[:n]:
                full_path = os.path.join(model_dir, filename)
                graph = self._read_graph_from_file(full_path)
                svg_name = os.path.splitext(filename)[0] + ".svg"
                dest = os.path.join(self.vis_dir, svg_name)
                self._save_and_collect(graph, dest, pdf)

    def _sort_key(self, filename: str) -> int:
        match = re.search(r"(\d+)", filename)
        return int(match.group(1)) if match else 0

    def _build_prefix_map(self, model_paths: List[str]) -> Dict[str, int]:
        """Scan all model files and assign a stable integer to each unique
        asset name prefix (the part before the last ':' in an asset name)."""
        prefixes = set()
        for path in model_paths:
            try:
                model = Model.load_from_file(path, self.lang_graph)
                for asset in model.assets.values():
                    prefix = asset.name.rsplit(":", 1)[0]
                    prefixes.add(prefix)
            except Exception:
                pass

        return {prefix: i + 1 for i, prefix in enumerate(sorted(prefixes))}

    def _asset_label(self, asset_name: str) -> str:
        """Map an asset name to its integer label string."""
        prefix = asset_name.rsplit(":", 1)[0]
        return str(self.prefix_to_int.get(prefix, "?"))

    def _create_type_color_map(self) -> Dict[str, tuple]:
        asset_types = sorted(self.lang_graph.assets.keys())
        cmap = plt.get_cmap("tab20")
        return {
            asset_type: cmap(i % cmap.N) for i, asset_type in enumerate(asset_types)
        }

    def _read_graph_from_file(self, path: str) -> MultiGraph:
        model = Model.load_from_file(path, self.lang_graph)
        G = nx.MultiGraph()

        for asset in model.assets.values():
            G.add_node(
                asset.name,
                type=asset.type,
                label=self._asset_label(asset.name),
            )

        for asset in model.assets.values():
            for fieldname, associated_assets in asset.associated_assets.items():
                assoc: LanguageGraphAssociation = asset.lg_asset.associations[fieldname]
                assoc_name = assoc.name

                for other in associated_assets:
                    if G.has_edge(asset.name, other.name):
                        existing_labels = G[asset.name][other.name].get("label", [])
                        if assoc_name not in existing_labels:
                            existing_labels.append(assoc_name)
                            for key in G[asset.name][other.name]:
                                G[asset.name][other.name][key][
                                    "label"
                                ] = existing_labels
                    else:
                        G.add_edge(asset.name, other.name, label=[assoc_name])

        return G

    def _save_and_collect(self, graph: MultiGraph, dest: str, pdf: PdfPages) -> None:
        """Draw the graph, save as SVG, and also write directly to the open PDF."""
        fig, ax = plt.subplots(figsize=(14, 10))

        n = len(graph.nodes())
        scale = min(1.0, math.sqrt(40 / n) if n > 40 else 1.0)

        node_size = 500 * scale
        label_fontsize = 12 * math.sqrt(scale)
        edge_fontsize = 8 * math.sqrt(scale)
        k = 0.4

        pos = nx.spring_layout(graph, k=k, iterations=200)

        node_types = nx.get_node_attributes(graph, "type")
        node_labels = nx.get_node_attributes(graph, "label")
        node_colors = [self.type_to_color[node_types[node]] for node in graph.nodes()]

        nx.draw_networkx_nodes(
            graph, pos, node_color=node_colors, node_size=node_size, alpha=0.9, ax=ax
        )
        nx.draw_networkx_labels(
            graph, pos, labels=node_labels, font_size=label_fontsize, ax=ax
        )
        nx.draw_networkx_edges(graph, pos, alpha=0.4, ax=ax)

        edge_labels = {
            (u, v): ", ".join(data["label"]) for u, v, data in graph.edges(data=True)
        }
        nx.draw_networkx_edge_labels(
            graph, pos, edge_labels=edge_labels, font_size=edge_fontsize, ax=ax
        )

        # ── Legend ────────────────────────────────────────────────────────────

        present_types = {node_types[n] for n in graph.nodes()}
        present_prefixes = {node_labels[n] for n in graph.nodes()}

        color_entries = [
            Patch(facecolor=self.type_to_color[t], edgecolor="grey", label=t)
            for t in sorted(present_types)
        ]

        int_entries = [
            mlines.Line2D(
                [],
                [],
                marker="none",
                linestyle="none",
                label=f"{lbl}: {self.int_to_prefix[int(lbl)]}",
            )
            for lbl in sorted(
                present_prefixes, key=lambda x: int(x) if x.isdigit() else 0
            )
            if lbl.isdigit() and int(lbl) in self.int_to_prefix
        ]

        separator = mlines.Line2D([], [], marker="none", linestyle="none", label=" ")

        ax.legend(
            handles=color_entries + [separator] + int_entries,
            loc="upper left",
            bbox_to_anchor=(1.01, 1),
            borderaxespad=0,
            fontsize=7,
            framealpha=0.9,
            title="Legend",
            title_fontsize=8,
        )

        ax.axis("off")

        fig.savefig(dest, bbox_inches="tight")  # SVG file
        pdf.savefig(fig, bbox_inches="tight")  # PDF page (vector)
        plt.close(fig)
