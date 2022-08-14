from pathlib import Path
from typing import Any, Dict, List

from demisto_sdk.commands.content_graph.constants import ContentTypes
from demisto_sdk.commands.content_graph.parsers.content_item import JSONContentItemParser


class ClassifierMapperParser(JSONContentItemParser):
    def __init__(self, path: Path, pack_marketplaces: List[str]) -> None:
        super().__init__(path, pack_marketplaces)
        print(f'Parsing {self.content_type} {self.content_item_id}')
        self.connect_to_dependencies()

    @property
    def content_type(self) -> ContentTypes:
        if self.json_data.get('type') == 'classification':
            return ContentTypes.CLASSIFIER
        return ContentTypes.MAPPER

    def get_data(self) -> Dict[str, Any]:
        json_content_item_data = super().get_data()
        classifier_mapper_data = {
            'type': self.json_data.get('type'),
            'definitionId': self.json_data.get('definitionId'),
        }
        return json_content_item_data | classifier_mapper_data

    def get_filters_and_transformers_from_complex_value(self, complex_value: dict) -> None:
        for filter in complex_value.get('filters', []):
            if filter:
                filter_script = filter[0].get('operator')
                self.add_dependency(filter_script, ContentTypes.SCRIPT)

        for transformer in complex_value.get('transformers', []):
            if transformer:
                transformer_script = transformer.get('operator')
                self.add_dependency(transformer_script, ContentTypes.SCRIPT)

    def connect_to_dependencies(self) -> None:
        if default_incident_type := self.json_data.get('defaultIncidentType'):
            self.add_dependency(default_incident_type, ContentTypes.INCIDENT_TYPE)

        if self.content_type == ContentTypes.CLASSIFIER:
            self.connect_to_classifier_dependencies()
        else:
            self.connect_to_mapper_dependencies()

    def connect_to_classifier_dependencies(self) -> None:
        for incident_type in self.json_data.get('keyTypeMap', {}).values():
            self.add_dependency(incident_type, ContentTypes.INCIDENT_TYPE)
        if transformer_complex_value := self.json_data.get('transformer', {}).get('complex', {}):
            self.get_filters_and_transformers_from_complex_value(transformer_complex_value)

    def connect_to_mapper_dependencies(self) -> None:
        for incident_type, mapping_data in self.json_data.get('mapping', {}).items():
            self.add_dependency(incident_type, ContentTypes.INCIDENT_TYPE)
            internal_mapping: Dict[str, Any] = mapping_data.get('internalMapping')

            if self.json_data.get('type') == 'mapping-outgoing':
                # incident fields are in the simple / complex.root key of each key
                for fields_mapper in internal_mapping.values():
                    if isinstance(fields_mapper, dict):
                        if incident_field_simple := fields_mapper.get('simple'):
                            self.add_dependency(incident_field_simple, ContentTypes.INCIDENT_FIELD)
                        elif incident_field_complex := fields_mapper.get('complex', {}).get('root'):
                            self.add_dependency(incident_field_complex, ContentTypes.INCIDENT_FIELD)

            elif self.json_data.get('type') == 'mapping-incoming':
                # all the incident fields are the keys of the mapping
                for incident_field in internal_mapping.keys():
                    self.add_dependency(incident_field, ContentTypes.INCIDENT_FIELD)

            for internal_mapping in internal_mapping.values():
                if incident_field_complex := internal_mapping.get('complex', {}):
                    self.get_filters_and_transformers_from_complex_value(incident_field_complex)