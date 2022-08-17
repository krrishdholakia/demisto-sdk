from pathlib import Path
from typing import List

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.content_graph.constants import ContentTypes
from demisto_sdk.commands.content_graph.parsers.content_item import JSONContentItemParser


class LayoutParser(JSONContentItemParser):
    def __init__(self, path: Path, pack_marketplaces: List[MarketplaceVersions]) -> None:
        super().__init__(path, pack_marketplaces)
        print(f'Parsing {self.content_type} {self.object_id}')
        self.kind: str = self.json_data.get('kind')
        self.tabs: List[str] = self.json_data.get('tabs')
        self.definition_id: str = self.json_data.get('definitionId')
        self.group: str = self.json_data.get('group')

        self.edit: bool = bool(self.json_data.get('edit'))
        self.indicators_details: bool = bool(self.json_data.get('indicatorsDetails'))
        self.indicators_quick_view: bool = bool(self.json_data.get('indicatorsQuickView'))
        self.quick_view: bool = bool(self.json_data.get('quickView'))
        self.close: bool = bool(self.json_data.get('close'))
        self.details: bool = bool(self.json_data.get('details'))
        self.details_v2: bool = bool(self.json_data.get('detailsV2'))
        self.mobile: bool = bool(self.json_data.get('mobile'))


        self.connect_to_dependencies()

    @property
    def content_type(self) -> ContentTypes:
        return ContentTypes.LAYOUT

    def connect_to_dependencies(self) -> None:
        if self.group == 'incident':
            dependency_field_type = ContentTypes.INCIDENT_FIELD
        else:
            dependency_field_type = ContentTypes.INDICATOR_FIELD

        for field in self.get_field_ids_recursively():
            self.add_dependency(field, dependency_field_type, is_mandatory=False)

    def get_field_ids_recursively(self) -> List[str]:
        """ Recursively iterates over the layout json data to extract all fieldId items.

        Returns:
            list of the field IDs.
        """
        values: List[str] = []

        def get_values(current_object):
            if isinstance(current_object, list):
                for item in current_object:
                    get_values(item)

            elif isinstance(current_object, dict):
                for key, value in current_object.items():
                    if key == 'fieldId' and isinstance(value, str):
                        values.append(value)
                    else:
                        get_values(value)

        get_values(self.json_data)
        return values