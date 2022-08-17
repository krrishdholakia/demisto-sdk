from pathlib import Path
from typing import List

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.content_graph.constants import ContentTypes
from demisto_sdk.commands.content_graph.parsers.content_item import JSONContentItemParser


class TriggerParser(JSONContentItemParser):
    def __init__(self, path: Path, pack_marketplaces: List[MarketplaceVersions]) -> None:
        super().__init__(path, pack_marketplaces)
        print(f'Parsing {self.content_type} {self.object_id}')

        self.connect_to_dependencies()

    @property
    def content_type(self) -> ContentTypes:
        return ContentTypes.TRIGGER

    @property
    def object_id(self) -> str:
        return self.json_data.get('trigger_id')

    @property
    def name(self) -> str:
        return self.json_data.get('trigger_name')

    def connect_to_dependencies(self) -> None:
        if playbook := self.json_data.get('playbook_id'):
            self.add_dependency(playbook, ContentTypes.PLAYBOOK)