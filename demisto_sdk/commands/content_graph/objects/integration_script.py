from pathlib import Path
from typing import List, Optional

from packaging.version import Version
from pydantic import Field

from demisto_sdk.commands.common.constants import (
    NATIVE_IMAGE_FILE_NAME,
    MarketplaceVersions,
    DOCKERFILES_INFO_REPO
)
from demisto_sdk.commands.common.docker_helper import (
    get_python_version,
)
from demisto_sdk.commands.common.docker_images_metadata import DockerImagesMetadata
from demisto_sdk.commands.common.logger import logger
from demisto_sdk.commands.common.native_image import (
    ScriptIntegrationSupportedNativeImages,
    file_to_native_image_config,
)
from demisto_sdk.commands.content_graph.objects.content_item import ContentItem
from demisto_sdk.commands.prepare_content.integration_script_unifier import (
    IntegrationScriptUnifier,
)


class IntegrationScript(ContentItem):
    type: str
    docker_image: Optional[str]
    description: Optional[str]
    is_unified: bool = Field(False, exclude=True)
    code: Optional[str] = Field(None, exclude=True)

    def prepare_for_upload(
        self,
        current_marketplace: MarketplaceVersions = MarketplaceVersions.XSOAR,
        **kwargs,
    ) -> dict:
        data = (
            self.data
            if kwargs.get("unify_only")
            else super().prepare_for_upload(current_marketplace)
        )
        data = IntegrationScriptUnifier.unify(
            self.path, data, current_marketplace, **kwargs
        )
        return data

    def get_supported_native_images(
        self, marketplace: MarketplaceVersions, ignore_native_image: bool = False
    ) -> List[str]:
        if marketplace == MarketplaceVersions.XSOAR and not ignore_native_image:
            if not Path(f"Tests/{NATIVE_IMAGE_FILE_NAME}").exists():
                logger.debug(f"The {NATIVE_IMAGE_FILE_NAME} file could not be found.")
                return []
            return ScriptIntegrationSupportedNativeImages(
                _id=self.object_id,
                docker_image=self.docker_image,
                native_image_config=file_to_native_image_config(),
            ).get_supported_native_image_versions(get_raw_version=True)
        return []

    def get_python_version(self) -> Optional[Version]:
        """
        Get the python version from the script/integration docker-image in case it's a python image
        """
        if "python" not in self.type or not self.docker_image:
            logger.debug(
                f"The {self.content_type} = {self.object_id=} that uses {self.docker_image=} is not a python image"
            )
            return None

        logger.debug(
            f"Getting python version for the {self.content_type} = {self.object_id}"
        )

        if python_version := DockerImagesMetadata.get_instance().python_version(
            self.docker_image
        ):
            return python_version
        logger.info(
            f"Could not get python version for {self.content_type} = {self.object_id} from {DOCKERFILES_INFO_REPO} repo, will retrieve from dockerhub api"
        )

        if python_version := get_python_version(self.docker_image, use_only_api=True):
            return python_version
        logger.debug(
            f"Could not get python version for {self.content_type} = {self.object_id} using {self.docker_image=} from dockerhub api"
        )

        return None
