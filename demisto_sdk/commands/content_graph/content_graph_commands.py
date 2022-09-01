import logging


from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.content_graph.content_graph_builder import \
    ContentGraphBuilder
from demisto_sdk.commands.content_graph.content_graph_loader import ContentGraphLoader
from demisto_sdk.commands.content_graph.interface.graph import ContentGraphInterface

import demisto_sdk.commands.content_graph.neo4j_service as neo4j_service
from demisto_sdk.commands.content_graph.common import REPO_PATH
from demisto_sdk.commands.content_graph.objects.repository import Repository

logger = logging.getLogger('demisto-sdk')


def create_content_graph(
    content_graph_interface: ContentGraphInterface,
) -> None:
    """This function creates a new content graph database in neo4j from the content path

    Args:
        content_graph_interface (ContentGraphInterface): The content graph interface.
    """
    content_graph_builder = ContentGraphBuilder(REPO_PATH, content_graph_interface)
    content_graph_builder.create_graph()


def stop_content_graph(
    use_docker: bool = True,
) -> None:
    """
    This function stops the neo4j service if it is running.

    Args:
        use_docker (bool, optional): Whether or not the service runs with docker.
    """
    neo4j_service.stop(use_docker=use_docker)


def marshal_content_graph(
    content_graph_interface: ContentGraphInterface,
    marketplace: MarketplaceVersions = MarketplaceVersions.XSOAR,
) -> Repository:
    """This function marshals the content graph to python models.

    Args:
        content_graph_interface (ContentGraphInterface): The content graph interface.
        marketplace (MarketplaceVersions, optional): The marketplace to use. Defaults to MarketplaceVersions.XSOAR.

    Returns:
        Repository: The repository model loaded from the content graph.

    """
    content_graph_loader = ContentGraphLoader(marketplace, content_graph_interface)
    return content_graph_loader.load()