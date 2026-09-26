#!/usr/bin/env python3
"""Generate architecture and bench diagrams for Continuum V4.

Uses only the standard library (xml.etree.ElementTree) to avoid dependencies.
Outputs SVG files to the same directory.
"""

from pathlib import Path
from xml.etree import ElementTree as ET


def create_architecture_diagram(output_path: Path) -> None:
    """Create 03-architecture.svg: browser → Vercel → Atlas, OpenRouter, ai.mongodb.com."""
    width, height = 1200, 700

    svg = ET.Element('svg', {
        'viewBox': f'0 0 {width} {height}',
        'xmlns': 'http://www.w3.org/2000/svg',
        'width': str(width),
        'height': str(height),
    })

    # Background
    ET.SubElement(svg, 'rect', {
        'width': str(width),
        'height': str(height),
        'fill': '#f9f9f9',
        'stroke': '#ddd',
        'stroke-width': '1',
    })

    # Define arrow marker
    defs = ET.SubElement(svg, 'defs')
    marker = ET.SubElement(defs, 'marker', {
        'id': 'arrowhead',
        'markerWidth': '10',
        'markerHeight': '10',
        'refX': '5',
        'refY': '5',
        'orient': 'auto',
    })
    ET.SubElement(marker, 'polygon', {
        'points': '0 0, 10 5, 0 10',
        'fill': '#666',
    })

    def draw_box(x, y, w, h, text, color='#e8f4f8'):
        """Draw a labeled box."""
        ET.SubElement(svg, 'rect', {
            'x': str(x),
            'y': str(y),
            'width': str(w),
            'height': str(h),
            'fill': color,
            'stroke': '#333',
            'stroke-width': '2',
        })
        text_elem = ET.SubElement(svg, 'text', {
            'x': str(x + w / 2),
            'y': str(y + h / 2 + 8),
            'text-anchor': 'middle',
            'font-family': 'sans-serif',
            'font-size': '16',
            'font-weight': 'bold',
            'fill': '#333',
        })
        text_elem.text = text

    def draw_arrow(x1, y1, x2, y2):
        """Draw an arrow line."""
        ET.SubElement(svg, 'line', {
            'x1': str(x1),
            'y1': str(y1),
            'x2': str(x2),
            'y2': str(y2),
            'stroke': '#666',
            'stroke-width': '2',
            'marker-end': 'url(#arrowhead)',
        })

    # Browser layer
    draw_box(500, 30, 200, 60, 'React/Vite Browser', '#c8e6c9')

    # Arrow down
    draw_arrow(600, 90, 600, 130)

    # Vercel layer
    draw_box(450, 130, 300, 60, 'Vercel (Web + API Function)', '#bbdefb')

    # Arrows down to three services
    draw_arrow(500, 190, 250, 280)  # to Atlas
    draw_arrow(600, 190, 600, 280)  # to OpenRouter
    draw_arrow(700, 190, 950, 280)  # to ai.mongodb.com

    # MongoDB Atlas
    draw_box(100, 280, 300, 80, 'MongoDB Atlas Sandbox\nmemories + policies\noutcomes + audit\nbench_runs', '#fff9c4')

    # OpenRouter
    draw_box(450, 280, 300, 80, 'OpenRouter\nopenai/gpt-oss-20b\ntemp=0, 4K context', '#f8bbd0')

    # ai.mongodb.com (Voyage)
    draw_box(800, 280, 300, 80, 'ai.mongodb.com\nVoyage embeddings\n1024 dimensions', '#d1c4e9')

    # Description at bottom
    desc = ET.SubElement(svg, 'text', {
        'x': str(width / 2),
        'y': str(height - 40),
        'text-anchor': 'middle',
        'font-family': 'sans-serif',
        'font-size': '14',
        'fill': '#666',
    })
    desc.text = 'All data synthetic, labeled synthetic: true. Vector Search with tenant/type filters.'

    # Write SVG
    ET.indent(svg, space='  ')
    tree = ET.ElementTree(svg)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f'Created {output_path.name}')


def create_bench_diagram(output_path: Path) -> None:
    """Create 04-harness-bench.svg: three arms side by side with five metrics each."""
    width, height = 1200, 500

    svg = ET.Element('svg', {
        'viewBox': f'0 0 {width} {height}',
        'xmlns': 'http://www.w3.org/2000/svg',
        'width': str(width),
        'height': str(height),
    })

    # Background
    ET.SubElement(svg, 'rect', {
        'width': str(width),
        'height': str(height),
        'fill': '#fafafa',
        'stroke': '#ddd',
        'stroke-width': '1',
    })

    def draw_arm_column(col_x, arm_name, arm_color):
        """Draw one arm with its five metrics."""
        col_width = 350

        # Arm header
        ET.SubElement(svg, 'rect', {
            'x': str(col_x),
            'y': '20',
            'width': str(col_width),
            'height': '50',
            'fill': arm_color,
            'stroke': '#333',
            'stroke-width': '2',
        })

        title = ET.SubElement(svg, 'text', {
            'x': str(col_x + col_width / 2),
            'y': str(55),
            'text-anchor': 'middle',
            'font-family': 'sans-serif',
            'font-size': '18',
            'font-weight': 'bold',
            'fill': '#fff',
        })
        title.text = arm_name

        # Metrics
        metrics = [
            ('Cost', '$X'),
            ('Wall time (s)', '~Y'),
            ('Vector calls', 'N'),
            ('Tokens', 'T'),
            ('Correct %', 'C%'),
        ]

        y_start = 100
        metric_height = 70

        for i, (label, value) in enumerate(metrics):
            y = y_start + i * metric_height

            # Metric box
            ET.SubElement(svg, 'rect', {
                'x': str(col_x + 10),
                'y': str(y),
                'width': str(col_width - 20),
                'height': str(metric_height - 10),
                'fill': '#fff',
                'stroke': '#ccc',
                'stroke-width': '1',
            })

            # Label
            label_elem = ET.SubElement(svg, 'text', {
                'x': str(col_x + 20),
                'y': str(y + 25),
                'font-family': 'sans-serif',
                'font-size': '12',
                'font-weight': 'bold',
                'fill': '#333',
            })
            label_elem.text = label

            # Value placeholder
            value_elem = ET.SubElement(svg, 'text', {
                'x': str(col_x + 20),
                'y': str(y + 50),
                'font-family': 'monospace',
                'font-size': '14',
                'fill': '#666',
            })
            value_elem.text = value

    # Three arms
    draw_arm_column(30, 'out_of_box', '#ffcc80')
    draw_arm_column(425, 'context_stuffing', '#ce93d8')
    draw_arm_column(820, 'continuum', '#81c784')

    # Footer
    footer = ET.SubElement(svg, 'text', {
        'x': str(width / 2),
        'y': str(height - 15),
        'text-anchor': 'middle',
        'font-family': 'sans-serif',
        'font-size': '13',
        'fill': '#999',
    })
    footer.text = 'Same 12 synthetic tasks, temperature=0, deterministic seed. Stored in MongoDB Atlas bench_runs collection.'

    # Write SVG
    ET.indent(svg, space='  ')
    tree = ET.ElementTree(svg)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f'Created {output_path.name}')


if __name__ == '__main__':
    diagrams_dir = Path(__file__).parent
    create_architecture_diagram(diagrams_dir / '03-architecture.svg')
    create_bench_diagram(diagrams_dir / '04-harness-bench.svg')
    print('All diagrams generated.')
