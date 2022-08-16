from typing import Any, Dict

from pydantic import Field
from demisto_sdk.commands.common.tools import field_to_cli_name

from demisto_sdk.commands.content_graph.constants import ContentTypes
from demisto_sdk.commands.content_graph.objects.content_item import JSONContentItem


class ClassifierMapper(JSONContentItem):
    classifier_mapper_type: str = Field('', alias='type')
    definition_id: str = Field('', alias='definitionId')

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if self.parsing_object:
            if self.classifier_mapper_type == 'classification':
                self.content_type = ContentTypes.CLASSIFIER
            self.content_type = ContentTypes.MAPPER
            print(f'Parsing {self.content_type} {self.object_id}')
            self.node_id = self.get_node_id()
            self.classifier_mapper_type = self.json_data.get('type')
            self.definition_id = self.json_data.get('definitionId')

            self.connect_to_dependencies()

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

            if self.classifier_mapper_type == 'mapping-outgoing':
                # incident fields are in the simple / complex.root key of each key
                for fields_mapper in internal_mapping.values():
                    if isinstance(fields_mapper, dict):
                        if incident_field_simple := fields_mapper.get('simple'):
                            self.add_dependency(
                                field_to_cli_name(incident_field_simple),
                                ContentTypes.INCIDENT_FIELD,
                            )
                        elif incident_field_complex := fields_mapper.get('complex', {}).get('root'):
                            self.add_dependency(
                                field_to_cli_name(incident_field_complex),
                                ContentTypes.INCIDENT_FIELD,
                            )

            elif self.classifier_mapper_type == 'mapping-incoming':
                # all the incident fields are the keys of the mapping
                for incident_field in internal_mapping.keys():
                    self.add_dependency(
                        field_to_cli_name(incident_field),
                        ContentTypes.INCIDENT_FIELD,
                    )

            for internal_mapping in internal_mapping.values():
                if incident_field_complex := internal_mapping.get('complex', {}):
                    self.get_filters_and_transformers_from_complex_value(incident_field_complex)
