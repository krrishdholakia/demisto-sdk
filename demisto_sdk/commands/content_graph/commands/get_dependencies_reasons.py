from pathlib import Path
from typing import Any, Dict, Optional

import typer

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.common.handlers import DEFAULT_JSON_HANDLER as json
from demisto_sdk.commands.common.logger import (
    logger,
    logging_setup,
)
from demisto_sdk.commands.content_graph.commands.update import update_content_graph
from demisto_sdk.commands.content_graph.common import (
    RelationshipType,
)
from demisto_sdk.commands.content_graph.interface import ContentGraphInterface

app = typer.Typer()


COMMAND_OUTPUTS_FILENAME = "get_dependencies_reasons_outputs.json"


@app.command(
    no_args_is_help=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def get_dependencies_reasons(
    ctx: typer.Context,
    source: str = typer.Option(
        ...,
        "-s",
        help="The dependent pack ID (source).",
    ),
    target: str = typer.Option(
        ...,
        "-t",
        help="The dependency pack ID (target).",
    ),
    update_graph: bool = typer.Option(
        True,
        "-u/-nu",
        "--update-graph/--no-update-graph",
        is_flag=True,
        help="If true, runs an update on the graph before querying.",
    ),
    marketplace: MarketplaceVersions = typer.Option(
        MarketplaceVersions.XSOAR,
        "-mp",
        "--marketplace",
        show_default=True,
        case_sensitive=False,
        help="The marketplace version.",
    ),
    mandatory_only: bool = typer.Option(
        False,
        "--mandatory-only",
        is_flag=True,
        help="If true, returns reasons only for mandatory dependencies.",
    ),
    include_tests: bool = typer.Option(
        False,
        "--incude-test-dependencies",
        is_flag=True,
        help="If true, includes tests dependencies in outputs.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "-o",
        "--output",
        exists=True,
        dir_okay=True,
        resolve_path=True,
        show_default=False,
        help="A path to a directory in which to dump the outputs to.",
    ),
    console_log_threshold: str = typer.Option(
        "INFO",
        "-clt",
        "--console_log_threshold",
        help=("Minimum logging threshold for the console logger."),
    ),
    file_log_threshold: str = typer.Option(
        "DEBUG",
        "-flt",
        "--file_log_threshold",
        help=("Minimum logging threshold for the file logger."),
    ),
    log_file_path: str = typer.Option(
        "demisto_sdk_debug.log",
        "-lp",
        "--log_file_path",
        help=("Path to the log file. Default: ./demisto_sdk_debug.log."),
    ),
) -> None:
    """
    Returns relationships of a given content object.
    """
    logging_setup(
        console_log_threshold=console_log_threshold,
        file_log_threshold=file_log_threshold,
        log_file_path=log_file_path,
    )
    with ContentGraphInterface() as graph:
        if update_graph:
            update_content_graph(graph)
        reasons = get_dependencies_reasons_by_pack_ids(
            graph,
            source,
            target,
            marketplace,
            mandatory_only,
            include_tests,
        )
        if output:
            (output / COMMAND_OUTPUTS_FILENAME).write_text(
                json.dumps(reasons, indent=4),
            )


def get_dependencies_reasons_by_pack_ids(
    graph: ContentGraphInterface,
    source: str,
    target: str,
    marketplace: MarketplaceVersions,
    mandatory_only: bool,
    include_tests: bool,
) -> list:
    reasons = graph.get_dependencies_reasons(
        source,
        target,
        marketplace,
        mandatory_only,
        include_tests,
    )
    for record in reasons:
        log_record(record)
    logger.info("[cyan]====== SUMMARY ======[/cyan]")
    logger.info(to_tabulate(reasons))
    return reasons


def log_record(
    record: Dict[str, Any],
) -> None:
    pass  # todo
    # is_source = record["is_source"]
    # for path in record["paths"]:
    #     mandatorily = (
    #         f" (mandatory: {path['mandatorily']})"
    #         if path["mandatorily"] is not None
    #         else ""
    #     )
    #     logger.debug(
    #         f"[yellow]Found a {relationship} path{mandatorily}"
    #         f"{' from ' if is_source else ' to '}"
    #         f"{record['filepath']}[/yellow]\n"
    #         f"{path_to_str(relationship, path['path'])}\n"
    #     )


def path_to_str(
    relationship: RelationshipType,
    path: list,
) -> str:
    def node_to_str(path: str) -> str:
        return f"({path})"

    def rel_to_str(rel: RelationshipType, props: dict) -> str:
        rel_data = f"[{rel}{props or ''}]"
        spaces = " " * (len(rel_data) // 2 - 1)
        return f"\n{spaces}|\n{rel_data}\n{spaces}↓\n"

    path_str = ""
    for idx, path_element in enumerate(path):
        if idx % 2 == 0:
            path_str += node_to_str(path_element)
        else:
            path_str += rel_to_str(relationship, path_element)
    return path_str


def to_tabulate(
    data: list,
) -> str:
    pass  # todo
    # if not data:
    #     return "No results."

    # headers = ["File Path", "Min Depth"]
    # fieldnames_to_collect = ["filepath", "minDepth"]
    # maxcolwidths = [70, None]
    # if relationship in [RelationshipType.USES, RelationshipType.DEPENDS_ON]:
    #     headers.append("Mandatory")
    #     fieldnames_to_collect.append("mandatorily")
    #     maxcolwidths.append(None)

    # tabulated_data = []
    # for record in data:
    #     tabulated_data.append([record[f] for f in fieldnames_to_collect])

    # return tabulate(
    #     tabulated_data,
    #     headers=headers,
    #     tablefmt="fancy_grid",
    #     maxcolwidths=maxcolwidths,
    # )
