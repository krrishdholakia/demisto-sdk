import networkx
from pathlib import Path
from typing import Any, Dict, List

from demisto_sdk.commands.common.update_id_set import (
    BUILT_IN_FIELDS,
    get_fields_by_script_argument,
    build_tasks_graph
)
from demisto_sdk.commands.content_graph.constants import ContentTypes
import demisto_sdk.commands.content_graph.parsers.content_item as content_item

LIST_COMMANDS = ['Builtin|||setList', 'Builtin|||getList']

class PlaybookParser(content_item.YAMLContentItemParser):
    def __init__(self, path: Path, pack_marketplaces: List[str], is_test_playbook: bool = False) -> None:
        if not is_test_playbook:
            super().__init__(path, pack_marketplaces)
            print(f'Parsing {self.content_type} {self.content_item_id}')
            self.graph: networkx.DiGraph = build_tasks_graph(self.yml_data)
            self.connect_to_dependencies()
            self.connect_to_tests()

    @property
    def content_item_id(self) -> str:
        return self.yml_data.get('id')

    @property
    def content_type(self) -> ContentTypes:
        return ContentTypes.PLAYBOOK

    @property
    def deprecated(self) -> bool:
        return self.yml_data.get('deprecated', False)
    
    def is_mandatory_dependency(self, task_id: str) -> bool:
        try:
            return self.graph.nodes[task_id]['mandatory']
        except KeyError:
            # task is not connected to a branch
            return False

    def handle_playbook_task(self, task: Dict[str, Any], is_mandatory: bool) -> None:
        if playbook := task.get('task', {}).get('playbookName'):
            self.add_dependency(playbook, ContentTypes.PLAYBOOK, is_mandatory)

    def handle_script_task(self, task: Dict[str, Any], is_mandatory: bool) -> None:
        if script := task.get('task', {}).get('scriptName'):
            self.add_dependency(script, ContentTypes.SCRIPT, is_mandatory)

    def handle_command_task(self, task: Dict[str, Any], is_mandatory: bool) -> None:
        if command := task.get('task', {}).get('script'):
            if 'setIncident' in command:
                for incident_field in get_fields_by_script_argument(task):
                    self.add_dependency(incident_field, ContentTypes.INCIDENT_FIELD, is_mandatory)

            elif 'setIndicator' in command:
                for incident_field in get_fields_by_script_argument(task):
                    self.add_dependency(incident_field, ContentTypes.INDICATOR_FIELD, is_mandatory)

            elif command in LIST_COMMANDS:
                if list := task.get('scriptarguments', {}).get('listName', {}).get('simple'):
                    self.add_dependency(list, ContentTypes.LIST, is_mandatory)

            elif 'Builtin' not in command:
                if '|' not in command:
                    self.add_dependency(command, ContentTypes.COMMAND, is_mandatory)
                else:
                    integration, *_, command = command.split('|')
                    if integration:
                        self.add_dependency(integration, ContentTypes.INTEGRATION, is_mandatory)
                    else:
                        self.add_dependency(command, ContentTypes.COMMAND, is_mandatory)
    
    def add_complex_input_filters_and_transformers(self, complex_input: Dict[str, Any]) -> None:
        for filter in complex_input.get('filters', []):
            if filter:
                operator = filter[0].get('operator')
                self.add_dependency(operator, ContentTypes.SCRIPT)

        for transformer in complex_input.get('transformers', []):
            if transformer:
                operator = transformer.get('operator')
                self.add_dependency(operator, ContentTypes.SCRIPT)
    
    def handle_task_filter_and_transformer_scripts(self, task: Dict[str, Any]) -> None:
        if task.get('type') == 'condition':
            for condition_entry in task.get('conditions', []):
                for inner_condition in condition_entry.get('condition', []):
                    for condition in inner_condition:
                        if condition_lhs := condition.get('left', {}).get('value', {}).get('complex', {}):
                            self.add_complex_input_filters_and_transformers(condition_lhs)
                        if condition_rhs := condition.get('right', {}).get('value', {}).get('complex', {}):
                            self.add_complex_input_filters_and_transformers(condition_rhs)
        else:
            for script_argument in task.get('scriptarguments', {}).values():
                if arg_value := script_argument.get('complex', {}):
                    self.add_complex_input_filters_and_transformers(arg_value)

    def handle_field_mapping(self, task: Dict[str, Any], is_mandatory: bool) -> None:
        if field_mapping := task.get('task', {}).get('fieldMapping'):
            for incident_field in field_mapping:
                if incident_field not in BUILT_IN_FIELDS:
                    self.add_dependency(incident_field, ContentTypes.INCIDENT_FIELD, is_mandatory)
    
    def connect_to_dependencies(self) -> None:
        for task_id, task in self.yml_data.get('tasks', {}).items():
            is_mandatory = self.is_mandatory_dependency(task_id)
            self.handle_task_filter_and_transformer_scripts(task)
            self.handle_playbook_task(task, is_mandatory)
            self.handle_script_task(task, is_mandatory)
            self.handle_command_task(task, is_mandatory)
            self.handle_field_mapping(task, is_mandatory)