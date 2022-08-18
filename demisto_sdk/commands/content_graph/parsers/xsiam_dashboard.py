from pathlib import Path
from typing import TYPE_CHECKING

from demisto_sdk.commands.content_graph.constants import ContentTypes
from demisto_sdk.commands.content_graph.parsers.content_item import JSONContentItemParser

if TYPE_CHECKING:
    from demisto_sdk.commands.content_graph.parsers.pack import PackParser


class XSIAMDashboardParser(JSONContentItemParser):
    def __init__(self, path: Path, pack: 'PackParser') -> None:
        super().__init__(path, pack)
        print(f'Parsing {self.content_type} {self.object_id}')
        self.json_data = self.json_data.get('dashboards_data', [{}])[0]

    @property
    def object_id(self) -> str:
        return self.json_data['global_id']

    @property
    def content_type(self) -> ContentTypes:
        return ContentTypes.XSIAM_DASHBOARD

    def add_to_pack(self) -> None:
        self.pack.content_items.xsiam_dashboard.append(self)
