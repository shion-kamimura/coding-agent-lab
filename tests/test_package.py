"""インストールされたパッケージの構成を検証する。"""

from importlib.metadata import distribution
from importlib.resources import files

import coding_agent


def test_installed_distribution_contains_typed_package() -> None:
    package = distribution("coding-agent-lab")

    assert package.metadata["Name"] == "coding-agent-lab"
    assert files(coding_agent).joinpath("py.typed").is_file()
