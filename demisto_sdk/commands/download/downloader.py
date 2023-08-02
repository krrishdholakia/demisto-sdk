import os
import re
import shutil
import tarfile
import traceback
from collections import defaultdict
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import mkdtemp
from typing import Dict, List, Union, DefaultDict

import mergedeep

import demisto_client.demisto_api
from demisto_client.demisto_api.rest import ApiException
from dictor import dictor
from flatten_dict import unflatten
from tabulate import tabulate
from urllib3 import HTTPResponse
from urllib3.exceptions import MaxRetryError

from demisto_sdk.commands.common.constants import (
    CONTENT_FILE_ENDINGS,
    ENTITY_NAME_SEPARATORS,
    ENTITY_TYPE_TO_DIR,
    INTEGRATIONS_DIR,
    PLAYBOOKS_DIR,
    SCRIPTS_DIR,
    TEST_PLAYBOOKS_DIR,
    UUID_REGEX,
)
from demisto_sdk.commands.common.handlers import DEFAULT_JSON_HANDLER as json
from demisto_sdk.commands.common.handlers import DEFAULT_YAML_HANDLER as yaml
from demisto_sdk.commands.common.logger import logger
from demisto_sdk.commands.common.tools import (
    create_stringio_object,
    find_type,
    get_child_files,
    get_code_lang,
    get_dict_from_file,
    get_display_name,
    get_entity_id_by_entity_type,
    get_entity_name_by_entity_type,
    get_file,
    get_file_details,
    get_files_in_dir,
    get_id,
    get_json,
    get_yaml,
    get_yml_paths_in_dir,
    is_sdk_defined_working_offline,
    safe_write_unicode,
)
from demisto_sdk.commands.format.format_module import format_manager
from demisto_sdk.commands.init.initiator import Initiator
from demisto_sdk.commands.split.ymlsplitter import YmlSplitter

ITEM_TYPE_TO_ENDPOINT: dict = {
    "IncidentType": "/incidenttype",
    "IndicatorType": "/reputation",
    "Field": "/incidentfields",
    "Layout": "/layouts",
    "Playbook": "/playbook/search",
    "Automation": "automation/load/",
    "Classifier": "/classifier/search",
    "Mapper": "/classifier/search",
}

ITEM_TYPE_TO_REQUEST_TYPE = {
    "IncidentType": "GET",
    "IndicatorType": "GET",
    "Field": "GET",
    "Layout": "GET",
    "Playbook": "GET",
    "Automation": "POST",
    "Classifier": "POST",
    "Mapper": "POST",
}

ITEM_TYPE_TO_PREFIX = {
    "IncidentType": ".json",
    "IndicatorType": ".json",
    "Field": ".json",
    "Layout": ".json",
    "Playbook": ".yml",
    "Automation": ".yml",
    "Classifier": ".json",
    "Mapper": ".json",
}

# Fields to keep on existing content items when overwriting them with a download (fields that are omitted by the server)
KEEP_EXISTING_JSON_FIELDS = [
    "fromVersion",
    "toVersion"
]
KEEP_EXISTING_YAML_FIELDS = [
    "fromversion",
    "toversion",
    "alt_dockerimages",
    "script.dockerimage45",
    "tests",
    "defaultclassifier",
    "defaultmapperin",
    "defaultmapperout",
]

class Downloader:
    """
    A class for downloading content from an XSOAR server locally

    Attributes:
        output_pack_path (str): A path to a pack to save the downloaded content to.
        input_files (list): A list of content item's names (not file names) to download.
        regex (str): A RegEx pattern to use for filtering the custom content files to download.
        force (bool): Whether to overwrite files that already exist in the output pack.
        insecure (bool): Whether to use insecure connection for API calls.
        client (Demisto client): Demisto client objecgt to use for API calls.
        list_files (bool): Whether to list all downloadable files or not (if True, all other flags are ignored).
        download_all_custom_content (bool): Whether to download all available custom content.
        run_format (bool): Whether to run 'format' on downloaded files.
        download_system_items (bool): Whether the current download is for system items.
        system_item_type (str): The items type to download (relevant only for system items).
        init (bool): Whether to initialize a new Pack structure in the output path and download the items to it.
        keep_empty_folders (bool): Whether to keep empty folders when using init.
    """

    def __init__(
        self,
        output: str,
        input: Union[str, List[str]],
        regex: str = "",
        force: bool = False,
        insecure: bool = False,
        list_files: bool = False,
        all_custom_content: bool = False,
        run_format: bool = False,
        system: bool = False,
        item_type: str = "",
        init: bool = False,
        keep_empty_folders: bool = False,
        **kwargs,
    ):
        self.output_pack_path = output
        self.input_files = input if isinstance(input, list) else [input]
        self.regex = regex
        self.force = force
        self.download_system_items = system
        self.system_item_type = item_type
        self.insecure = insecure
        self.list_files = list_files
        self.download_all_custom_content = all_custom_content
        self.run_format = run_format
        self.client = None
        self.init = init
        self.keep_empty_folders = keep_empty_folders
        if is_sdk_defined_working_offline() and self.run_format:
            self.run_format = False
            logger.info(
                "Formatting is not supported when the DEMISTO_SDK_OFFLINE_ENV environment variable is set, Skipping..."
            )

    def download(self) -> int:
        """
        Downloads custom content data from XSOAR to the output path provided.

        Returns:
            int: Exit code. 1 if failed, 0 if succeeded
        """
        return self.download_manager()

    def download_manager(self) -> int:
        """
        Manages all download command flows

        Returns:
            int: Exit code. 1 if failed, 0 if succeeded
        """
        try:
            if not (self.verify_flags() and self.verify_output_path()):
                return 1

            if self.init:
                self.initialize_output_path()

            if self.download_system_items and not self.list_files:
                downloaded_content_objects = self.fetch_system_content()

            else:
                all_custom_content_data = self.download_custom_content()
                all_custom_content_objects = self.parse_custom_content_data(custom_content_data=all_custom_content_data)

                # If we're in list-files mode, print the list of all available custom content and exit
                if self.list_files:
                    logger.info(f"list-files (-lf) mode detected. Listing available custom content files "
                                f"({len(all_custom_content_objects)}):")
                    table_str = self.create_custom_content_table(custom_content_objects=all_custom_content_objects)

                    logger.info(table_str)
                    return 0

                uuid_mapping = self.create_uuid_to_name_mapping(custom_content_objects=all_custom_content_objects)

                # Filter custom content so that we'll process only downloaded content
                downloaded_content_objects = self.filter_custom_content(
                    custom_content_objects=all_custom_content_objects)

                # Replace UUID IDs with names in filtered content (only content we download)
                changed_uuids_count = 0
                for _, file_object in downloaded_content_objects.items():
                    if self.replace_uuid_ids(custom_content_object=file_object, uuid_mapping=uuid_mapping):
                        changed_uuids_count += 1

                if changed_uuids_count > 0:
                    logger.debug(f"Replaced UUID IDs in {changed_uuids_count} custom content items.")

            existing_pack_data = self.build_existing_pack_structure(existing_pack_path=Path(self.output_pack_path))

            result = self.write_files_into_output_path(downloaded_content_objects=downloaded_content_objects,
                                                       existing_pack_structure=existing_pack_data)

            if result:
                logger.info(f"Content items downloaded successfully into {self.output_pack_path}.")
                return 0

            logger.error(f"Download process failed.")
            return 1

        except Exception as e:
            if not isinstance(e, HandledError):
                logger.error(f"Error: {e}")

            logger.debug(traceback.format_exc())
            return 1

    def verify_flags(self) -> bool:
        """
        Verify that the flags provided by the user are valid and used correctly.

        Returns:
            bool: Whether the flags are valid or not.
        """
        # If listing files, input / output flags are ignored.
        if self.list_files:
            return True

        if not self.output_pack_path:
            logger.error("Error: Missing required parameter '-o' / '--output'.")
            return False

        if not any((self.input_files, self.download_all_custom_content, self.regex)):
            logger.error("Error: No input parameter has been provided "
                         "('-i' / '--input', '-r' / '--regex', '-a' / '--all.")
            return False

        if self.download_system_items:
            if not self.system_item_type:
                logger.error(
                    "Error: Missing required parameter for downloading system items: '-it' / '--item-type'."
                )
                return False

            if self.regex:
                logger.error("Error: RegEx flag ('-r' / '--regex') can only be used for custom content. "
                             "Use '-i' / '--input' to provide a list of system items to download.")
                return False

            if self.download_all_custom_content:
                logger.error("Error: All custom content flag ('-a' / '--all') can only be used for custom content. "
                             "Use '-i' / '--input' to provide a list of system items to download.")
                return False

        return True

    def filter_custom_content(self, custom_content_objects: dict[str, dict]) -> dict[str, dict]:
        """
        Filter custom content data to include only relevant files for the current download command.
        The function also updates self.input_file with names of content matching the filter.

        Args:
            custom_content_objects (dict[str, dict]): A dictionary mapping custom content names
                to their corresponding objects to filter.

        Returns:
            dict[str, dict]: A new custom content objects dict with filtered items.
        """
        file_name_to_content_name_map = {
            key: value["name"] for key, value in custom_content_objects.items()
        }
        filtered_custom_content_objects: dict[str, dict] = {}

        if self.download_all_custom_content:
            logger.debug("Filtering process has been skipped as all custom content should be downloaded.")
            for file_name, content_item_data in custom_content_objects.items():
                content_item_name = file_name_to_content_name_map[file_name]

                if content_item_name not in filtered_custom_content_objects:
                    filtered_custom_content_objects[content_item_name] = content_item_data

            return filtered_custom_content_objects

        original_count = len(custom_content_objects)
        logger.debug(f"Filtering custom content data ({original_count})...")

        for file_name in custom_content_objects:
            content_item_name = file_name_to_content_name_map[file_name]

            # Filter according input / regex flags
            if ((self.regex and re.match(self.regex, content_item_name)) or (content_item_name in self.input_files)
                    and content_item_name not in filtered_custom_content_objects):
                filtered_custom_content_objects[content_item_name] = custom_content_objects[file_name]

        # Filter out content written in JavaScript since it is not support
        # TODO: Check if we actually need this (why don't we allow downloading JS content?) and remove if not.
        for filtered_custom_content_name, filtered_custom_content_object in filtered_custom_content_objects.items():
            code_language: str = filtered_custom_content_object.get("code_lang")
            content_type: str = filtered_custom_content_object["type"]

            if content_type in ("integration", "script") and code_language in ("javascript", None):
                content_name = filtered_custom_content_object["name"]
                logger.warning(f"Content item '{content_name}' is written in JavaScript which isn't supported, "
                               f"and will be skipped.")
                self.input_files.remove(content_name)
                del filtered_custom_content_objects[filtered_custom_content_name]

        logger.info(f"Filtering process completed ({len(filtered_custom_content_objects)}/{original_count}).")

        return filtered_custom_content_objects

    def create_uuid_to_name_mapping(self, custom_content_objects: dict[str, dict]) -> dict[str, str]:
        """
        Find and map UUID IDs of custom content to their names.

        Args:
            custom_content_objects (dict[str, dict]):
                A dictionary mapping custom content names to their corresponding objects.

        Returns:
            dict[str, str]: A dictionary mapping UUID IDs to corresponding names of custom content.
        """
        logger.info("Creating ID mapping for custom content...")
        mapping: dict[str, str] = {}
        duplicate_ids: list[str] = []

        for _, content_object in custom_content_objects.items():
            content_item_id = content_object["id"]

            if re.match(UUID_REGEX, content_item_id) and content_item_id not in duplicate_ids:
                if content_item_id not in mapping:
                    mapping[content_item_id] = content_object["name"]

                else:
                    logger.warning(
                        f"Found duplicate ID '{content_item_id}' for custom content item '{content_object['name']}'"
                        f" (also references to '{mapping[content_item_id]}').\n"
                        "ID replacements for these content items will be skipped."
                    )
                    duplicate_ids.append(mapping.pop(content_item_id))

        logger.info("Custom content IDs mapping created successfully.")
        return mapping

    def download_custom_content(self) -> dict[str, StringIO]:
        """
        Download custom content bundle using server's API,
        and create a StringIO object containing file data for each file within it.

        Returns:
            dict[str, StringIO]: A dictionary mapping custom content's file names to file objects.
        """
        # Set to 'verify' to None so that 'demisto_client' will use the environment variable 'DEMISTO_VERIFY_SSL'.
        verify = not self.insecure if self.insecure else None
        logger.info("Fetching custom content bundle from server...")

        try:
            self.client = demisto_client.configure(verify_ssl=verify)
            api_response: HTTPResponse = demisto_client.generic_request_func(
                self.client, "/content/bundle", "GET",  _preload_content=False,
            )[0]

        except Exception as e:
            if isinstance(e, ApiException) and e.status == 401:
                logger.error(f"Server authentication error: {e}\n"
                             "Please verify that the required environment variables ('DEMISTO_API_KEY', or "
                             "'DEMISTO_USERNAME' and 'DEMISTO_PASSWORD') are properly configured."
                             )

            elif isinstance(e, MaxRetryError):
                logger.error(f"Failed connecting to server: {e}.\n"
                             "Please verify that the environment variable 'DEMISTO_BASE_URL' is properly configured, "
                             "and that the server is accessible.")

            else:
                logger.error(f"Error while fetching custom content: {e}")

            raise HandledError from e

        logger.info("Custom content bundle fetched successfully.")
        logger.debug(f"Downloaded content bundle size (bytes): {len(api_response.data)}")

        loaded_files: dict[str, StringIO] = {}

        with tarfile.open(fileobj=BytesIO(api_response.data), mode="r") as tar:
            tar_members = tar.getmembers()
            logger.debug(f"Custom content bundle contains {len(tar_members)} items.")

            logger.debug("Loading custom content bundle to memory...")
            for file in tar_members:
                file_name = file.name.lstrip("/")
                file_data = create_stringio_object(tar.extractfile(file).read())
                loaded_files[file_name] = file_data

        logger.info("Custom content items fetched successfully.")
        return loaded_files

    def replace_uuid_ids(self, custom_content_object: dict, uuid_mapping: dict[str, str]) -> bool:
        """
        Find and replace UUID IDs of custom content items with their names.
        The method first creates a mapping of a UUID to a name, and then replaces all UUIDs using this mapping.

        Args:
            custom_content_object (dict): A single custom content object to update UUIDs in.
            uuid_mapping (dict[str, str]): A dictionary mapping UUID IDs to corresponding names of custom content.

        Returns:
            bool: True if the object was updated, False otherwise.
        """
        file = custom_content_object["file"]
        content_item_file_str = file.getvalue()

        uuid_matches = re.findall(UUID_REGEX, content_item_file_str)
        # TODO: Check if looping over all dict keys (recursively) is more efficient than dumping to string and then search that using a RegEx.
        # If we do run recursively, consider how we will want to update the StringIO object (if we need it at all?)

        if uuid_matches:
            for uuid in set(uuid_matches).intersection(uuid_mapping):
                logger.debug(f"Replacing UUID '{uuid}' with '{uuid_mapping[uuid]}' in "
                             f"'{custom_content_object['name']}'")
                content_item_file_str = content_item_file_str.replace(uuid, uuid_mapping[uuid])

            # Update ID, if it's a UUID
            if custom_content_object["id"] in uuid_mapping:
                custom_content_object["id"] = uuid_mapping[custom_content_object["id"]]

            # Update custom content object
            custom_content_object["file"] = create_stringio_object(content_item_file_str)
            loaded_file_data = get_file_details(content_item_file_str,
                                                full_file_path=custom_content_object["file_name"])
            custom_content_object["data"] = loaded_file_data

            return True
        return False

    def build_req_params(self) -> tuple[str, str, dict]:
        endpoint = ITEM_TYPE_TO_ENDPOINT[self.system_item_type]
        req_type = ITEM_TYPE_TO_REQUEST_TYPE[self.system_item_type]
        verify = (
            (not self.insecure) if self.insecure else None
        )  # set to None so demisto_client will use env var DEMISTO_VERIFY_SSL
        self.client = demisto_client.configure(verify_ssl=verify)

        req_body: dict = {}
        if self.system_item_type in ["Playbook", "Classifier", "Mapper"]:
            filter_by_names = " or ".join(self.input_files)
            req_body = {"query": f"name:{filter_by_names}"}

        return endpoint, req_type, req_body

    def get_system_automation(self, content_items: list[str]) -> list[dict]:
        """
        Fetch system automations from server.

        Args:
            content_items (list[str]): A list of system automation names to fetch.

        Returns:
            list[dict]: A list of downloaded system automations represented as dictionaries.
        """
        downloaded_automations: list[dict] = []
        logger.info("Fetching system automations...")

        for script in content_items:
            endpoint = f"automation/load/{script}"
            api_response: dict = demisto_client.generic_request_func(
                self.client, endpoint, "POST", response_type="object",
            )[0]
            downloaded_automations.append(api_response)

        logger.debug(f"{len(downloaded_automations)} system automations were successfully downloaded.")
        return downloaded_automations

    def get_system_playbook(self, content_items: list[str]) -> list[dict]:
        """
        Fetch system playbooks from server.

        Args:
            content_items (list[str]): A list of system automation names to fetch.

        Returns:
            list[dict]: A list of downloaded system playbooks represented as dictionaries.
        """
        downloaded_playbooks: list[dict] = []
        logger.info("Fetching system playbooks...")

        for playbook in content_items:
            endpoint = f"/playbook/{playbook}/yaml"
            try:
                api_response: dict = demisto_client.generic_request_func(
                    self.client, endpoint, "GET", response_type="object",
                )[0]
            except ApiException as err:
                # handling in case the id and name are not the same,
                # trying to get the id by the name through a different api call
                logger.debug(f"API call using playbook's name failed:\n{err}\n"
                             f"Attempting to fetch using playbook's ID...")

                playbook_id = self.get_playbook_id_by_playbook_name(playbook)

                if not playbook_id:
                    raise

                logger.debug(f"Found matching ID for '{playbook}' - {playbook_id}.\n"
                             f"Attempting to fetch playbook's YAML file using the ID.")

                endpoint = f"/playbook/{playbook_id}/yaml"
                api_response = demisto_client.generic_request_func(
                    self.client, endpoint, "GET",  _preload_content=False,
                )[0]

            downloaded_playbooks.append(api_response)

        logger.debug(f"'{len(downloaded_playbooks)}' system playbooks were downloaded successfully.")
        return downloaded_playbooks

    def arrange_response(self, system_items_list):
        if self.system_item_type in ["Classifier", "Mapper"]:
            system_items_list = system_items_list.get("classifiers")

        return system_items_list

    def build_file_name(self, content_item: dict, content_item_type: str) -> str:
        item_name: str = content_item.get("name") or content_item.get("id")
        return (
            item_name.replace("/", "_").replace(" ", "_")
            + ITEM_TYPE_TO_PREFIX[content_item_type]
        )

    def fetch_system_content(self) -> dict[str, dict]:
        """
        Fetch system content from the server.

        Returns:
            dict[str, dict]: A dictionary mapping content item's file names, to dictionaries containing metadata
                and content of the item.
        """
        endpoint, req_type, req_body = self.build_req_params()
        downloaded_items: list[dict]

        if self.system_item_type == "Automation":
            downloaded_items = self.get_system_automation(content_items=self.input_files)

        elif self.system_item_type == "Playbook":
            downloaded_items = self.get_system_playbook(content_items=self.input_files)

        else:
            logger.info("Fetching system items...")
            api_response = demisto_client.generic_request_func(
                self.client, endpoint, req_type, body=req_body, response_type="object",
            )[0]

            if self.system_item_type in ["Classifier", "Mapper"]:
                if classifiers_data := api_response.get("classifiers"):
                    downloaded_items = classifiers_data

                else:
                    logger.warning("Could not find expected 'classifiers' key in API response.")
                    logger.debug(f"API response:\n{json.dumps(api_response)}")
                    downloaded_items = []

            else:
                downloaded_items = api_response

        logger.info(
            f"Fetched {len(downloaded_items)} system items from server."
        )

        content_objects: dict[str, dict] = {}

        for content_item in downloaded_items:
            file_name = self.build_file_name(content_item=content_item, content_item_type=self.system_item_type)
            file_data = create_stringio_object(file_data=json.dumps(content_item))
            content_object = self.create_content_item_object(file_name=file_name,
                                                             file_data=file_data,
                                                             _loaded_data=content_item)
            content_objects[file_name] = content_object

        return content_objects

    def parse_custom_content_data(self, custom_content_data: dict[str, StringIO]) -> dict[str, dict]:
        """
        Converts a mapping of file names to raw file data (StringIO),
        into a mapping of file names to custom content objects (parsed & loaded data)

        Note:
            Custom content items with an empty 'type' key are not supported and will be omitted.

        Args:
            custom_content_data (dict[str, StringIO]): A dictionary mapping file names to their content.

        Returns:
            dict[str, dict]: A dictionary mapping content item's file names, to dictionaries containing metadata
                about the content item, and file data.
        """
        logger.info("Parsing downloaded custom content data...")
        custom_content_objects: dict[str, dict] = {}

        for file_name, file_data in custom_content_data.items():
            try:
                logger.debug(f"Parsing '{file_name}'...")
                custom_content_object: Dict = self.create_content_item_object(
                    file_name=file_name, file_data=file_data
                )

                if custom_content_object.get("type"):  # TODO: currently, this results in `list-` items to be skipped
                    custom_content_objects[file_name] = custom_content_object

                else:
                    logger.warning(f"Content type of '{file_name}' could not be detected. Skipping...")

            # Skip custom_content_objects with an invalid format
            except Exception as e:
                # We fail the whole download process, since we might miss UUIDs to replace
                #  TODO: Check if we want to replace this behavior and just skip the file. Can cause UUID replacement issues.
                logger.error(f"Error while parsing '{file_name}': {e}")
                raise

        logger.info(f"Successfully parsed {len(custom_content_objects)} custom content objects.")
        return custom_content_objects

    def create_custom_content_table(self, custom_content_objects: dict[str, dict]) -> str:
        """
        Return a printable list of all custom content that's available to download from the configured XSOAR instance.

        Args:
            custom_content_objects (dict[str, dict]): A dictionary mapping custom content's file names to objects.

        Returns:
            str: A printable list of all custom content that's available to download from the configured XSOAR instance.
        """
        tabulate_data: list[list[str]] = []

        for file_name, file_object in custom_content_objects.items():
            if item_name := file_object.get("name"):
                tabulate_data.append([item_name, file_object["type"]])

        return tabulate(tabulate_data, headers=["CONTENT NAME", "CONTENT TYPE"])

    def initialize_output_path(self) -> None:
        """Initialize output path with pack structure."""
        logger.info("Initiating pack structure...")
        root_folder = Path(self.output_pack_path)
        if root_folder.name != "Packs":
            root_folder = root_folder / "Packs"
            try:
                root_folder.mkdir(exist_ok=True)
            except FileNotFoundError as e:
                e.filename = str(Path(e.filename).parent)
                raise
        initiator = Initiator(str(root_folder))
        initiator.init()
        self.output_pack_path = initiator.full_output_path

        if not self.keep_empty_folders:
            self.remove_empty_folders()

        logger.info(f"Initialized pack structure at '{self.output_pack_path}'.")

    def remove_empty_folders(self) -> None:
        """
        Removes empty folders from the output pack path
        :return: None
        """
        pack_folder = Path(self.output_pack_path)
        for folder_path in pack_folder.glob("*"):
            if folder_path.is_dir() and not any(folder_path.iterdir()):
                folder_path.rmdir()

    def verify_output_path(self) -> bool:
        """
        Assure that the output path entered by the user is inside a "Packs" folder.

        Returns:
            bool: True if the output path is valid, False otherwise.
        """
        output_pack_path = Path(self.output_pack_path)

        if not output_pack_path.is_dir():
            logger.error(
                f"Error: Path '{output_pack_path.absolute()}' does not exist, or isn't a directory."
            )

        elif not output_pack_path.parent.name == "Packs":
            logger.error(
                f"Error: Path '{output_pack_path.absolute()}' is invalid.\n"
                f"The provided output path for the download must be inside a 'Packs' folder. e.g., 'Packs/MyPack'."
            )

        # All validations passed
        else:
            return True

        return False

    def build_existing_pack_structure(self, existing_pack_path: Path) -> dict[str, dict[str, list[dict]]]:
        """
        Create a pack structure from the content in the existing output path.
        Used later to determine which files already exist in the output path (by their content name, not file name).

        Args:
            existing_pack_path (Path): The path of the existing pack to parse.

        Returns:
            dict[str, dict[str, list[dict]]]: A dictionary representing the pack structure.

        Example return structure:
        {
            "Integrations":
                "MyIntegration":
                    [
                        {
                            "name": "MyIntegration",
                            "id": "MyIntegration",
                            "path": "Packs/TestPack/Integrations/MyIntegration/MyIntegration.yml",
                            "file_extension": "yml"
                        },
                        {
                            "name": "MyIntegration",
                            "id": "MyIntegration",
                            "path": "Packs/TestPack/Integrations/MyIntegration/MyIntegration.py",
                            "file_extension": "py"
                        },
                        ... (more files, like README and description)
                    ]
        """
        output_pack_path = Path(existing_pack_path)
        pack_structure: DefaultDict[str, dict[str, list]] = defaultdict(dict)

        for content_entity_path in output_pack_path.iterdir():
            if content_entity_path.is_dir():
                directory_name = content_entity_path.name

                if directory_name in (INTEGRATIONS_DIR, SCRIPTS_DIR):
                    # If entity is of type integration/script it will have dirs, otherwise files
                    entity_instances_paths = [p for p in content_entity_path.iterdir() if p.is_dir()]
                else:
                    entity_instances_paths = [p for p in content_entity_path.iterdir() if p.is_file()]

                for entity_instance_path in entity_instances_paths:
                    content_data = self.build_pack_content_object(
                        content_entity=directory_name,
                        entity_instance_path=entity_instance_path
                    )

                    if content_data is not None:
                        content_name, content_object = content_data
                        pack_structure[directory_name][content_name] = content_object

        return dict(pack_structure)

    def build_pack_content_object(
        self, content_entity: str, entity_instance_path: Path
    ) -> tuple[str, list[dict]] | None:
        """
        Build an object representing a single content items that already exists in the output pack path.

        Args:
            content_entity (str): The content entity, for example Integrations.
            entity_instance_path (Path): The path to the content item.

        Returns:
            tuple[str, list[dict] | None: A tuple, containing the content item's name (str),
             and a list of objects representing files (for example YAML & Python) under the content item (list[dict]).
             None if the content item could not be parsed.
        """
        # If the entity_instance_path is a file then get_files_in_dir will return the list: [entity_instance_path]
        file_paths: list = get_files_in_dir(
            str(entity_instance_path), CONTENT_FILE_ENDINGS, recursive=False
        )
        # If it's integration/script, all files under it should have the main details of the yml file,
        # otherwise we'll use the file's details.
        content_item_id, content_item_name = self.get_main_file_details(
            content_entity, entity_instance_path
        )

        # if main file doesn't exist/no entity instance path exist the content object won't be added to the pack content
        if not all((content_item_id, content_item_name, file_paths)):
            logger.debug(f"Existing content item '{content_item_name}' could not be parsed. Skipping...")
            return None

        content_item_files = []

        for file_path in file_paths:
            content_item_files.append(
                {
                    "name": content_item_name,
                    "id": content_item_id,
                    "path": file_path,
                    "file_extension": Path(file_path).suffix,
                }
            )

        return content_item_name, content_item_files

    def get_playbook_id_by_playbook_name(self, playbook_name: str) -> str | None:
        """
        Extract the playbook id by name, calling the api returns an object that cannot be parsed properly,
        and its use is only for extracting the id.

        Args:
            playbook_name (str): The name of a playbook

        Returns:
            str | None: The ID of a playbook
        """
        logger.info(f"Fetching playbook ID using API for '{playbook_name}'...")
        endpoint = "/playbook/search"
        response = demisto_client.generic_request_func(
            self.client,
            endpoint,
            "POST",
            response_type="object",
            body={"query": f"name:{playbook_name}"},
        )
        if not response:
            return None
        if not (playbooks := response[0].get("playbooks")):
            return None

        playbook_id = playbooks[0]["id"]
        logger.info(f"Found playbook ID '{playbook_id}' for '{playbook_name}'")
        return playbook_id

    @staticmethod
    def get_main_file_details(content_entity: str, entity_instance_path: Path) -> tuple:
        """
        Returns the details of the "main" file within an entity instance.
        For example: In the HelloWorld integration under Packs/HelloWorld, the main file is the yml file.
        It contains all relevant ids and names for all the files under the HelloWorld integration dir.
        :param content_entity: The content entity, for example Integrations
        :param entity_instance_path: For example: ~/.../content/Packs/TestPack/Integrations/HelloWorld
        :return: The main file id & name
        """
        main_file_data: dict = {}
        main_file_path: str = ""

        # Entities which contain yml files
        if content_entity in (
            INTEGRATIONS_DIR,
            SCRIPTS_DIR,
            PLAYBOOKS_DIR,
            TEST_PLAYBOOKS_DIR,
        ):
            if entity_instance_path.is_dir():
                _, main_file_path = get_yml_paths_in_dir(str(entity_instance_path))
            elif entity_instance_path.is_file():
                main_file_path = str(entity_instance_path)

            if main_file_path:
                main_file_data = get_yaml(main_file_path)

        # Entities which are json files (md files are ignored - changelog/readme)
        else:
            if (
                entity_instance_path.is_file()
                and entity_instance_path.suffix == ".json"
            ):
                main_file_data = get_json(entity_instance_path)

        content_item_id = get_entity_id_by_entity_type(main_file_data, content_entity)
        content_item_name = get_entity_name_by_entity_type(main_file_data, content_entity)

        return content_item_id, content_item_name

    @staticmethod
    def update_file_prefix(file_name: str) -> str:
        """
        Replace 'automation' prefix with 'script' prefix, and remove 'playbook' prefixes.

        Args:
            file_name (str): The file name to update

        Returns:
            str: The updated file name
        """
        return file_name.replace("automation-", "script-").replace("playbook-", "")

    def create_content_item_object(self, file_name: str, file_data: StringIO, _loaded_data: dict | None = None) -> dict:
        """
        Convert a single custom content item to a content object.

        Args:
            file_name (str): The file name of the custom content item.
            file_data (StringIO): The file data of the custom content item.
            _loaded_data (dict | None, optional): The loaded data of the custom content item.
                If not provided, the file will be parsed.

        Returns:
            dict: The custom content object.
        """
        file_extension = Path(file_name).suffix

        if _loaded_data:
            loaded_file_data = _loaded_data

        else:
            loaded_file_data = get_file_details(file_content=file_data.getvalue(), full_file_path=file_name)

            if not loaded_file_data:
                raise ValueError(f"Unsupported file extension: {file_extension}")

        if file_type_enum := find_type(path=file_name, _dict=loaded_file_data, file_type=file_extension):
            file_type = file_type_enum.value

        else:
            file_type = ""

        content_id = get_id(loaded_file_data)
        content_name = get_display_name(file_path=file_name, file_data=loaded_file_data)
        file_entity = self.file_type_to_entity(
            content_name=content_name,
            file_type=file_type
        )

        if not content_id:
            logger.warning(f"Could not find content ID for '{file_name}'.")

        custom_content_object: dict = {
            "id": content_id,  # str
            "name": content_name,  # str
            "entity": file_entity,  # str
            "type": file_type,  # str
            "file": file_data,  # StringIO
            "file_name": self.update_file_prefix(file_name),  # str
            "file_extension": file_extension,  # str
            "data": loaded_file_data,  # dict
        }

        if file_code_language := get_code_lang(loaded_file_data, file_entity):
            custom_content_object["code_lang"] = file_code_language

        return custom_content_object

    @staticmethod
    def file_type_to_entity(content_name: str, file_type: str) -> str:
        """
        Given the file type returns the file entity.

        Args:
            content_name (str): Content item's name (not file name)
            file_type (str): Content file's type

        Returns:
            str: File's entity. An empty string if not found.
        """
        if file_type == "playbook":
            if content_name.endswith(
                ("Test", "_test", "_Test", "-test", "-Test")
            ) or content_name.lower().startswith("test"):
                return TEST_PLAYBOOKS_DIR
        return ENTITY_TYPE_TO_DIR.get(file_type, "")

    @staticmethod
    def create_directory_name(content_item_name: str) -> str:
        """
        Creates the directory name for a content item (used for integrations / scripts).
        Example: For a content item named "Hello World Script", "HelloWorldScript" will be returned.

        Args:
            content_item_name (str): Content item's name

        Returns:
            str: The directory name for the content item
        """
        for separator in ENTITY_NAME_SEPARATORS:
            content_item_name = content_item_name.replace(separator, "")
        return content_item_name

    def write_files_into_output_path(self, downloaded_content_objects: dict[str, dict],
                                     existing_pack_structure: dict[str, dict[str, list[dict]]]) -> bool:
        """
        Download the files after processing is done to the output directory.
        For integrations / scripts, YAML extraction is done.
        Content items that already exist in the output pack, will be skipped, unless the '--force' flag is used.
        If it is, the existing and downloaded YAML files will be merged, as some fields are deleted by the server.

        Args:
            downloaded_content_objects (dict[str, dict]): A dictionary of content objects to download.
            existing_pack_structure (dict[str, list]): A dictionary of existing content objects in the output path.

        Returns:
            bool: True if all files were downloaded successfully, False otherwise.
        """
        successful_downloads_count = 0
        existing_files_skipped_count = 0
        failed_downloads_count = 0

        for file_name, content_object in downloaded_content_objects.items():
            content_item_name: str = content_object["name"]
            content_item_entity: str = content_object["entity"]
            content_item_not_skipped = True

            try:
                if content_item_entity in (INTEGRATIONS_DIR, SCRIPTS_DIR):
                    file_downloaded = self.download_unified_content(content_object=content_object,
                                                                    existing_pack_structure=existing_pack_structure,
                                                                    overwrite_existing=self.force)

                else:
                    file_downloaded = self.download_non_unified_content(content_object=content_object,
                                                                        existing_pack_structure=existing_pack_structure,
                                                                        overwrite_existing=self.force)

                # If even one file was skipped, we mark the file as skipped for the logs
                if not file_downloaded:
                    content_item_not_skipped = False

            except Exception as e:
                failed_downloads_count += 1
                logger.error(f"Failed to download content item '{content_item_name}': {e}")
                logger.debug(traceback.format_exc())
                continue

            if content_item_not_skipped:
                successful_downloads_count += 1

            else:
                existing_files_skipped_count += 1

        summary_log = f"{successful_downloads_count} files were downloaded successfully."

        if failed_downloads_count:
            summary_log += f"\n{failed_downloads_count} files failed to download."

        if existing_files_skipped_count:
            summary_log += f"\n{existing_files_skipped_count} files that exist in the output pack were skipped. " \
                           f"Use the '-f' / '--force' flag to override."

        logger.info(summary_log)

        return not failed_downloads_count  # Return True if no downloads failed, False otherwise.

    def download_unified_content(self, content_object: dict,
                                 existing_pack_structure: dict[str, dict[str, list[dict]]],
                                 overwrite_existing: bool = False) -> bool:
        """
        Download unified content items.
        Existing content items will be skipped if 'overwrite_existing' is False.
        A "smart" merge will be done for pre-existing YAML files, adding fields that exist in existing file,
        but were omitted by the server.

        Args:
            content_object (dict): The content object to download
            existing_pack_structure (list[dict]): A list of existing content item files in the output pack.
            overwrite_existing (bool): Whether to overwrite existing files or not.

        Returns:
            bool: True if the content item was downloaded successfully, False otherwise.
        """
        temp_dir: str | None = None
        content_item_name: str = content_object["name"]
        content_item_type: str = content_object["type"]
        content_item_entity: str = content_object["entity"]
        content_directory_name = self.create_directory_name(content_item_name)

        content_item_exists = (  # Content item already exists in output pack
            content_object["name"] in existing_pack_structure.get(content_item_entity, {})
        )

        if content_item_exists:
            if not overwrite_existing:  # If file exists, and we don't want to overwrite it, skip it.
                logger.debug(
                    f"Content item '{content_item_name}' already exists in output pack. Skipping..."
                )
                return False

            # If we overwrite existing files, we need to extract the existing files to a temp directory
            # for a "smart" merge.
            temp_dir = mkdtemp()
            output_path = temp_dir

        else:
            output_path = Path(self.output_pack_path, content_item_entity, content_directory_name)
            output_path.mkdir(parents=True, exist_ok=True)  # Create path if it doesn't exist
            output_path = str(output_path)

        extractor = YmlSplitter(
            input=content_object["file_name"],
            output=output_path,
            loaded_data=content_object["data"],
            file_type=content_item_type,
            base_name=content_directory_name,
            no_readme=content_item_exists,  # If the content item exists, no need to download README.md file  # TODO: Change behavior? Why not download README.md in case it was changed?
            no_auto_create_dir=True,
        )
        extractor.extract_to_package_format()
        extracted_file_paths: list[str] = get_child_files(output_path)

        for extracted_file_path in extracted_file_paths:
            if content_item_exists:
                extracted_file_path = Path(extracted_file_path)
                extracted_file_extension = extracted_file_path.suffix

                # Get the file name to search for in the existing output pack
                expected_filename: str = self.get_expected_filename(
                    content_item_name=content_item_name,
                    file_extension=extracted_file_extension,
                )

                # Find extracted file's matching existing file
                corresponding_pack_file_object: dict | None = None

                for file_object in existing_pack_structure[content_item_entity][content_item_name]:
                    if Path(file_object["path"]).name == expected_filename:
                        corresponding_pack_file_object = file_object
                        break

                if corresponding_pack_file_object:
                    corresponding_pack_file_path = corresponding_pack_file_object["path"]

                else:
                    corresponding_pack_file_path: str = os.path.join(
                        self.output_pack_path,
                        content_item_entity,
                        self.create_directory_name(content_item_name),
                        expected_filename,
                    )

                if extracted_file_extension == ".yml":  # "smart" merge is relevant only for YAML files
                    self.update_data(  # Add existing fields that were removed by the server to the new file
                        file_to_update=extracted_file_path,
                        original_file=corresponding_pack_file_path,
                        is_yaml=(extracted_file_extension == ".yml"),
                    )

                shutil.move(src=extracted_file_path, dst=corresponding_pack_file_path)
                final_path = Path(corresponding_pack_file_path)

            # If the file doesn't exist in the pack, the files were extracted to the output path
            else:
                final_path = Path(extracted_file_path)

            if self.run_format and final_path.suffix in (".yml", ".yaml", ".json"):
                format_manager(
                    input=str(final_path),
                    no_validate=False,
                    assume_answer=False,
                )

        try:  # Clean up temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)

        except shutil.Error as e:
            logger.warning(f"Failed to remove temp dir '{temp_dir}': {e}")
            logger.debug(traceback.format_exc())

        logger.debug(f"Content item '{content_item_name}' was successfully downloaded.")
        return True

    def download_non_unified_content(self, content_object: dict,
                                     existing_pack_structure: dict[str, dict[str, list[dict]]],
                                     overwrite_existing: bool = False) -> bool:
        """
        Download non-unified content items.
        Existing content items will be skipped if 'overwrite_existing' is False.
        A "smart" merge will be done for pre-existing YAML files, adding fields that exist in existing file,
        but were omitted by the server.

        Args:
            content_object (dict): The content object to download
            existing_pack_structure (list[dict]): A list of existing content item files in the output pack.
            overwrite_existing (bool): Whether to overwrite existing files or not.

        Returns:
            bool: True if the content item was downloaded successfully, False otherwise.
        """
        content_item_name: str = content_object["name"]
        content_item_entity: str = content_object["entity"]
        content_item_extension: str = content_object["file_extension"]

        content_item_exists = (  # Content item already exists in output pack
            content_object["name"] in existing_pack_structure.get(content_item_entity, {})
        )

        # If file exists, and we don't want to overwrite it, skip it.
        if content_item_exists and not overwrite_existing:
            logger.debug(
                f"File '{content_item_name}' already exists in output pack. Skipping..."
            )
            return False

        # Write downloaded file to temp directory
        temp_dir = Path(mkdtemp())

        file_name: str = content_object["file_name"]
        file_path = temp_dir / file_name
        file_data: StringIO = content_object["file"]

        with open(file_path, "w") as f:
            f.write(file_data.getvalue())

        if content_item_exists:
            # The corresponding_pack_object will have a list of length 1 as value if it's an old file which isn't
            # integration or script
            corresponding_pack_file_object: dict = existing_pack_structure[content_item_entity][content_item_name][0]
            corresponding_pack_file_path: str = corresponding_pack_file_object["path"]

            self.update_data(
                file_path,
                corresponding_pack_file_path,
                is_yaml=(content_item_extension == ".yml"))

            output_path = corresponding_pack_file_path

        else:  # If the content item doesn't exist in the output pack, create a new directory for it
            output_path = Path(self.output_pack_path, content_item_entity)
            output_path.mkdir(parents=True, exist_ok=True)  # Create path if it doesn't exist

        shutil.move(src=file_path, dst=output_path)

        try:  # Clean up temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        except shutil.Error as e:
            logger.warning(f"Failed to remove temp dir '{temp_dir}': {e}")
            logger.debug(traceback.format_exc())

            if self.run_format and output_path.suffix in (".yml", ".yaml", ".json"):
                format_manager(
                    input=str(output_path),
                    no_validate=False,
                    assume_answer=False,
                )

        logger.debug(f"Content item '{content_item_name}' was successfully downloaded.")
        return True

    @staticmethod
    def update_data(file_to_update: Path | str, original_file: str, is_yaml: bool) -> None:
        """
        Collects special chosen fields from the file_path_to_read and writes them into the file_path_to_write.

        Args:
            file_to_update (Path | str): Path to the new file to merge 'original_file' into.
            original_file (str): Path to the original file to merge into 'file_to_update'.
            is_yaml (bool): True if the file is a yml file, False if it's a json file.
        """
        file_to_update = Path(file_to_update) if isinstance(file_to_update, str) else file_to_update

        pack_obj_data, _ = get_dict_from_file(original_file)
        fields = (
            KEEP_EXISTING_YAML_FIELDS
            if is_yaml
            else KEEP_EXISTING_JSON_FIELDS
        )
        # Creates a nested-complex dict of all fields to be deleted by the server.
        # We need the dict to be nested, to easily merge it later to the file data.
        preserved_data: dict = unflatten(
            {
                field: dictor(pack_obj_data, field)
                for field in fields
                if dictor(pack_obj_data, field)
            },
            splitter="dot",
        )

        file_data = get_file(file_to_update)

        if pack_obj_data:
            mergedeep.merge(file_data, preserved_data)

        if is_yaml:
            safe_write_unicode(lambda f: yaml.dump(file_data, f), file_to_update)
        else:  # json
            safe_write_unicode(
                lambda f: json.dump(data=file_data, fp=f, indent=4), file_to_update
            )

    def get_expected_filename(self, content_item_name: str, file_extension: str) -> str:
        """
        Creates a file name to search for in the existing pack.

        Args:
            content_item_name: Content item's name
            file_extension: File's extension

        Returns:
            str: The expected file name
        """
        if file_extension in (".py", ".yml", ".yaml"):
            return f"{self.create_directory_name(content_item_name)}.{file_extension.lstrip('.')}"

        else:  # Description & image files have their type within the file name
            if file_extension == ".md":
                file_type = "description"
            elif file_extension == ".png":
                file_type = "image"
            else:
                file_type = ""
                logger.warning(
                    f"Unsupported file extension '{file_extension}'."
                )

            return f"{self.create_directory_name(content_item_name)}_{file_type}.{file_extension}"


class HandledError(Exception):
    """An exception that has already been handled & logged."""
