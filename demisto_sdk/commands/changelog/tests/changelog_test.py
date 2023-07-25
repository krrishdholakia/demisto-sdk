import os
from pathlib import Path

import pytest

from demisto_sdk.commands.changelog import changelog
from demisto_sdk.commands.changelog.changelog import Changelog
from demisto_sdk.commands.changelog.changelog_obj import INITIAL_LOG
from demisto_sdk.commands.common.handlers import YAML_Handler

yaml = YAML_Handler()


@pytest.fixture
def changelog_mock():
    return Changelog(pr_name="test", pr_number="12345")


def test_is_release(changelog_mock):
    """
    Given:
        - Changelog obj with some different `pr_name`
    When:
        - run the is_release method
    Then:
        - Ensure return True only if pr_name is in vX.X.X format
    """
    assert not changelog_mock.is_release()
    changelog_mock.pr_name = ""
    assert not changelog_mock.is_release()
    changelog_mock.pr_name = "v1.10.2"
    assert changelog_mock.is_release()
    

def test_is_log_folder_empty(tmpdir, changelog_mock: Changelog):
    """
    Given:
        - Changelog obj and a temporary path with a .changelog folder
    When:
        - run the is_log_folder_empty method
    Then:
        - Ensure return True only if there is a file in the .changelog folder
    """
    folder_path = Path(tmpdir / ".changelog")
    os.makedirs(folder_path)
    changelog.CHANGELOG_FOLDER = folder_path
    assert changelog_mock.is_log_folder_empty()
    with (folder_path / "12345.yml").open("w") as f:
        f.write("test: test")
    assert not changelog_mock.is_log_folder_empty()


def test_is_log_yml_exist(tmpdir, changelog_mock: Changelog):
    """
    Given:
        - Changelog obj and a temporary path with a .changelog folder
    When:
        - run the is_log_yml_exist method
    Then:
        - Ensure return True only if there is a yml file
          with the same name as pr_number in the .changelog folder
    """
    folder_path = Path(tmpdir / ".changelog")
    os.makedirs(folder_path)
    changelog.CHANGELOG_FOLDER = folder_path
    assert not changelog_mock.is_log_yml_exist()
    with (folder_path / "12345.yml").open("w") as f:
        f.write("test: test")
    assert changelog_mock.is_log_yml_exist()


def test_get_all_logs(tmpdir, changelog_mock: Changelog):
    folder_path = Path(tmpdir / ".changelog")
    # changelog_path = Path(tmpdir / "CHANGELOG.md")
    os.makedirs(folder_path)
    changelog.CHANGELOG_FOLDER = folder_path
    # changelog.CHANGELOG_MD_FILE = changelog_path
    log_file = {
        "logs": [
            {
                "description": "fixed an issue where test",
                "type": "fix"
            }
        ]
    }
    log_file2 = {
        "logs": [
            {
                "description": "added a feature that test",
                "type": "feature"
            },
            {
                "description": "breaking changes: test",
                "type": "breaking"
            }
        ]
    }
    with (folder_path / "12345.yml").open("w") as f:
        yaml.dump(log_file, f)
    with (folder_path / "43524.yml").open("w") as f:
        yaml.dump(log_file2, f)
    log_files = changelog_mock.get_all_logs()
    assert len(log_files) == 2
    assert len(log_files[0].logs) == 2
