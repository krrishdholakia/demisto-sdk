from pathlib import Path

from demisto_sdk.commands.content_graph.common import ContentTypes
from demisto_sdk.commands.content_graph.parsers.json_content_item import JSONContentItemParser


class GenericModuleParser(JSONContentItemParser, content_type=ContentTypes.GENERIC_MODULE):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.definition_ids = self.json_data.get('definitionIds')

    @property
    def content_type(self) -> ContentTypes:
        return ContentTypes.GENERIC_MODULE
