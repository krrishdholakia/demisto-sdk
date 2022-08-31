import re
from pathlib import Path
from typing import List, Set

from demisto_sdk.commands.common.constants import MarketplaceVersions
from demisto_sdk.commands.content_graph.common import ContentType
from demisto_sdk.commands.content_graph.parsers.integration_script import IntegrationScriptParser


EXECUTE_CMD_PATTERN = re.compile(r"execute_?command\(['\"]([a-zA-Z-_]+)['\"].*", re.IGNORECASE)


class ScriptParser(IntegrationScriptParser, content_type=ContentType.SCRIPT):
    def __init__(self, path: Path, pack_marketplaces: List[MarketplaceVersions], is_test_script: bool = False) -> None:
        super().__init__(path, pack_marketplaces)
        self.is_test: bool = is_test_script
        self.docker_image: str = self.yml_data.get('dockerimage', '')
        self.type: str = self.yml_data.get('subtype') or self.yml_data.get('type')
        self.tags: List[str] = self.yml_data.get('tags', [])
        if self.type == 'python':
            self.type += '2'

        self.connect_to_dependencies()
        self.connect_to_tests()

    @property
    def description(self) -> str:
        return self.yml_data.get('comment', '')

    def connect_to_dependencies(self) -> None:
        """ Creates USES_COMMAND_OR_SCRIPT mandatory relationships with the commands/scripts used.
        At this stage, we can't determine whether the dependencies are commands or scripts.
        Only when we add the relationships to the database we can detect their actual content types,
        and then they are added as USES relationships.
        """
        for cmd in self.get_depends_on():
            self.add_dependency(cmd)

        for cmd in self.get_command_executions():
            self.add_dependency(cmd)

    def get_code(self) -> str:
        """ Gets the script code.
        If the script is unified, takes it from the yml file.
        Otherwise, uses the Unifier object to get it.

        Returns:
            str: The script code.
        """
        if self.is_unified or self.yml_data.get('script') not in ['-', '']:
            return self.yml_data.get('script')
        return self.unifier.get_script_or_integration_package_data()[1]

    def get_depends_on(self) -> Set[str]:
        depends_on: List[str] = self.yml_data.get('dependson', {}).get('must', [])
        return {cmd.split('|')[-1] for cmd in depends_on}

    def get_command_executions(self) -> Set[str]:
        return set(EXECUTE_CMD_PATTERN.findall(self.get_code()))
