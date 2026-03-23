"""
Chart generation functions converted from reports.ipynb.
Each function accepts data as a dict and saves the chart to the given output path.
"""

import matplotlib.pyplot as plt
import pandas as pd


def _format_k(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k".replace(".", ",")
    return str(int(value))


def generate_country_bar_chart(data: dict, output_path: str = "blue_chart.png") -> None:
    """Bar chart of active users by country."""
    df = pd.Series(data)
    bar_color = "#156082"

    plt.figure(figsize=(8, 6))
    bars = plt.bar(df.index, df.values, color=bar_color)

    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height + max(df.values) * 0.02,
            _format_k(height),
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    ax = plt.gca()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.tick_params(left=False, bottom=False)
    plt.xticks(rotation=0, fontsize=10)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close()


def generate_traffic_source_pie_chart(data: dict, output_path: str = "traffic_pie_chart_compact.png") -> None:
    """Pie chart of traffic sources (Direct = orange, Organic Search = blue)."""
    df = pd.Series(data)
    colors = ["#e97132", "#156082"]

    plt.figure(figsize=(6, 6))
    plt.pie(
        df.values,
        startangle=140,
        colors=colors,
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )
    plt.title("Source of Traffic", fontsize=14, pad=5)
    plt.legend(
        df.index,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=2,
        frameon=False,
        fontsize=10,
    )
    plt.subplots_adjust(top=0.9, bottom=0.15)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close()


def generate_user_type_pie_chart(data: dict, output_path: str = "user_pie_chart.png") -> None:
    """Pie chart of new vs returning users with counts inside slices."""
    df = pd.Series(data)
    colors = ["#156082", "#e97132"]

    plt.figure(figsize=(6, 6))
    plt.pie(
        df.values,
        labels=None,
        autopct=lambda p: _format_k(int(round(p * sum(df.values) / 100))),
        startangle=90,
        colors=colors,
        textprops={"fontsize": 14, "color": "white", "fontweight": "bold"},
        wedgeprops={"edgecolor": "white", "linewidth": 0},
    )
    plt.legend(
        df.index,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=2,
        frameon=False,
        fontsize=10,
    )
    plt.subplots_adjust(top=0.9, bottom=0.15)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close()


def generate_line_chart(data: dict, output_path: str = "line_chart.png") -> None:
    """Line chart with circle markers and values above each point."""
    df = pd.Series(data)
    color = "#156082"

    plt.figure(figsize=(7, 5))
    plt.plot(df.index, df.values, color=color, linewidth=2.5, marker="o", markersize=8)

    for i, value in enumerate(df.values):
        plt.text(
            i,
            value + max(df.values) * 0.03,
            _format_k(value),
            ha="center", va="bottom", fontsize=22, fontweight="bold",
        )

    ax = plt.gca()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.tick_params(left=False, bottom=False)
    plt.xticks(fontsize=22)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close()


def generate_page_views_bar_chart(data: dict, output_path: str = "page_views_chart.png") -> None:
    """Horizontal bar chart of page views by page name."""
    df = pd.Series(data)
    bar_color = "#156082"

    plt.figure(figsize=(12, 6))
    bars = plt.bar(df.index, df.values, color=bar_color, width=0.6)

    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height + 20,
            _format_k(height),
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    ax = plt.gca()
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.get_yaxis().set_visible(False)
    plt.tick_params(left=False, bottom=False)
    plt.xticks(fontsize=14, rotation=20)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close()
