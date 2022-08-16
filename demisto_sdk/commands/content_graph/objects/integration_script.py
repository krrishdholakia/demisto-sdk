from abc import abstractmethod
from pathlib import Path
from typing import List

from pydantic import Field

from demisto_sdk.commands.content_graph.objects.content_item import YAMLContentItem
from demisto_sdk.commands.unify.integration_script_unifier import \
    IntegrationScriptUnifier


class IntegrationScript(YAMLContentItem):
    type: str = ''
    docker_image: str = ''
    is_unified: bool = Field(False, exclude=True)
    unifier: IntegrationScriptUnifier = Field(None, exclude=True)

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if self.parsing_object:
            self.object_id = self.yml_data.get('commonfields', {}).get('id')
            self.is_unified = YAMLContentItem.is_unified_file(self.path)
            self.unifier = None if self.is_unified else IntegrationScriptUnifier(self.path.as_posix())

    @abstractmethod
    def get_code(self) -> str:
        pass
