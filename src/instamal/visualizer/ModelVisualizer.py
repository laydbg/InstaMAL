import os
from typing import Dict

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
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

        self.lang_graph = LanguageGraph().load_from_file(lang_path)

        # Stable type → color mapping
        self.type_to_color = self._create_type_color_map()

        model_files = sorted(
            f for f in os.listdir(model_dir) if f.endswith((".yml", ".yaml", ".json"))
        )

        for filename in model_files[:n]:
            full_path = os.path.join(model_dir, filename)
            graph = self._read_graph_from_file(full_path)

            png_name = os.path.splitext(filename)[0] + ".png"
            dest = os.path.join(self.vis_dir, png_name)

            self._save_png_visualization(graph, dest)

        # self._create_summary_markdown()
        self._create_summary_pdf()

    def _create_type_color_map(self) -> Dict[str, tuple]:
        asset_types = sorted(self.lang_graph.assets.keys())
        cmap = plt.get_cmap("tab20")

        return {
            asset_type: cmap(i % cmap.N) for i, asset_type in enumerate(asset_types)
        }

    def _read_graph_from_file(self, path: str) -> MultiGraph:
        model = Model.load_from_file(path, self.lang_graph)
        G = nx.MultiGraph()

        # Add nodes
        for asset in model.assets.values():
            G.add_node(asset.name, type=asset.type)

        # Add edges with association names
        for asset in model.assets.values():
            for fieldname, associated_assets in asset.associated_assets.items():
                # Get the association type from MAL language
                assoc: LanguageGraphAssociation = asset.lg_asset.associations[fieldname]
                assoc_name = assoc.name

                for other in associated_assets:
                    if G.has_edge(asset.name, other.name):
                        # Append association name to existing edge
                        existing_labels = G[asset.name][other.name].get("label", [])
                        if assoc_name not in existing_labels:
                            existing_labels.append(assoc_name)
                            for key in G[asset.name][other.name]:
                                G[asset.name][other.name][key]["label"] = (
                                    existing_labels
                                )
                    else:
                        G.add_edge(asset.name, other.name, label=[assoc_name])

        return G

    def _save_png_visualization(self, graph: MultiGraph, dest: str) -> None:
        plt.figure(figsize=(12, 10))
        pos = nx.spring_layout(graph, k=0.3, iterations=75)

        # Node colors
        node_types = nx.get_node_attributes(graph, "type")
        node_colors = [self.type_to_color[node_types[node]] for node in graph.nodes()]

        nx.draw_networkx_nodes(
            graph, pos, node_color=node_colors, node_size=500, alpha=0.9
        )
        nx.draw_networkx_labels(graph, pos, font_size=8)

        # Draw edges
        nx.draw_networkx_edges(graph, pos, alpha=0.4)

        # Draw edge labels
        edge_labels = {
            (u, v): ", ".join(data["label"]) for u, v, data in graph.edges(data=True)
        }
        nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=6)

        plt.axis("off")
        plt.tight_layout()
        plt.savefig(dest, dpi=300)
        plt.close()

    def _create_summary_markdown(self) -> None:
        png_files = sorted(f for f in os.listdir(self.vis_dir) if f.endswith(".png"))

        if not png_files:
            return

        summary_path = os.path.join(self.model_dir, "summary.md")

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("# Model Visualizations\n\n")

            for png in png_files:
                f.write(f"## {png}\n\n")
                f.write(f"![{png}](vis/{png})\n\n")

    def _create_summary_pdf(self) -> None:
        png_files = sorted(f for f in os.listdir(self.vis_dir) if f.endswith(".png"))

        if not png_files:
            return

        pdf_path = os.path.join(self.model_dir, "summary.pdf")

        with PdfPages(pdf_path) as pdf:
            for png in png_files:
                img_path = os.path.join(self.vis_dir, png)
                img = mpimg.imread(img_path)

                fig = plt.figure(figsize=(12, 10))
                plt.imshow(img)
                plt.axis("off")
                plt.title(png)

                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
