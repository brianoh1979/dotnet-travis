# pylint: disable=import-outside-toplevel,reimported
import pytest

from kedro.extras.extensions.ipython import (
    init_kedro,
    load_ipython_extension,
    reload_kedro,
)
from kedro.framework.session.session import _deactivate_session
from kedro.framework.startup import ProjectMetadata
from kedro.pipeline import Pipeline


@pytest.fixture(autouse=True)
def project_path(mocker, tmp_path):
    path = tmp_path
    mocker.patch("kedro.extras.extensions.ipython.project_path", path)


@pytest.fixture(autouse=True)
def mocked_logging(mocker):
    # Disable logging.config.dictConfig in KedroSession._setup_logging as
    # it changes logging.config and affects other unit tests
    return mocker.patch("logging.config.dictConfig")


@pytest.fixture(autouse=True)
def cleanup_session():
    yield
    _deactivate_session()


class TestInitKedro:
    def test_init_kedro(self, tmp_path, caplog):
        from kedro.extras.extensions.ipython import project_path

        assert project_path == tmp_path

        kedro_path = tmp_path / "here"
        init_kedro(str(kedro_path))
        expected_path = kedro_path.expanduser().resolve()
        expected_message = f"Updated path to Kedro project: {expected_path}"

        log_messages = [record.getMessage() for record in caplog.records]
        assert expected_message in log_messages
        from kedro.extras.extensions.ipython import project_path

        # make sure global variable updated
        assert project_path == expected_path

    def test_init_kedro_no_path(self, tmp_path, caplog):
        from kedro.extras.extensions.ipython import project_path

        assert project_path == tmp_path

        init_kedro()
        expected_message = f"No path argument was provided. Using: {tmp_path}"

        log_messages = [record.getMessage() for record in caplog.records]
        assert expected_message in log_messages
        from kedro.extras.extensions.ipython import project_path

        # make sure global variable stayed the same
        assert project_path == tmp_path


@pytest.fixture()
def pipeline_cleanup():
    yield
    from kedro.framework.project import pipelines

    pipelines.configure(None)
    pipelines._content = {}


class TestLoadKedroObjects:
    @pytest.mark.usefixtures("pipeline_cleanup")
    def test_load_kedro_objects(self, tmp_path, mocker):
        fake_metadata = ProjectMetadata(
            source_dir=tmp_path / "src",  # default
            config_file=tmp_path / "pyproject.toml",
            package_name="fake_package_name",
            project_name="fake_project_name",
            project_version="0.1",
            project_path=tmp_path,
        )
        my_pipelines = {"ds": Pipeline([])}

        def my_register_pipeline():
            return my_pipelines

        mocker.patch(
            "kedro.framework.project._ProjectPipelines._get_pipelines_registry_callable",
            return_value=my_register_pipeline,
        )
        mocker.patch("kedro.framework.project.settings.configure")
        mocker.patch("kedro.framework.session.session.validate_settings")
        mocker.patch(
            "kedro.framework.startup.bootstrap_project",
            return_value=fake_metadata,
        )
        mock_line_magic = mocker.MagicMock()
        mock_line_magic.__name__ = "abc"
        mocker.patch(
            "kedro.framework.cli.load_entry_points", return_value=[mock_line_magic]
        )
        mock_register_line_magic = mocker.patch(
            "kedro.extras.extensions.ipython.register_line_magic"
        )
        mock_context = mocker.patch("kedro.framework.session.KedroSession.load_context")
        mock_ipython = mocker.patch("kedro.extras.extensions.ipython.get_ipython")

        reload_kedro(tmp_path)

        mock_ipython().push.assert_called_once_with(
            variables={
                "context": mock_context(),
                "catalog": mock_context().catalog,
                "session": mocker.ANY,
                "pipelines": my_pipelines,
            }
        )
        mock_register_line_magic.assert_called_once()

    def test_load_kedro_objects_extra_args(self, tmp_path, mocker):
        fake_metadata = ProjectMetadata(
            source_dir=tmp_path / "src",  # default
            config_file=tmp_path / "pyproject.toml",
            package_name="fake_package_name",
            project_name="fake_project_name",
            project_version="0.1",
            project_path=tmp_path,
        )
        mocker.patch("kedro.framework.session.session.configure_project")
        mocker.patch(
            "kedro.framework.startup.bootstrap_project",
            return_value=fake_metadata,
        )
        mock_line_magic = mocker.MagicMock()
        mock_line_magic.__name__ = "abc"
        mocker.patch(
            "kedro.framework.cli.load_entry_points", return_value=[mock_line_magic]
        )
        mock_register_line_magic = mocker.patch(
            "kedro.extras.extensions.ipython.register_line_magic"
        )
        mock_session_create = mocker.patch(
            "kedro.framework.session.KedroSession.create"
        )
        mock_ipython = mocker.patch("kedro.extras.extensions.ipython.get_ipython")

        reload_kedro(tmp_path, env="env1", extra_params={"key": "val"})

        mock_session_create.assert_called_once_with(
            "fake_package_name", tmp_path, env="env1", extra_params={"key": "val"}
        )
        mock_ipython().push.assert_called_once_with(
            variables={
                "context": mock_session_create().load_context(),
                "catalog": mock_session_create().load_context().catalog,
                "session": mock_session_create(),
                "pipelines": {},
            }
        )
        assert mock_register_line_magic.call_count == 1

    def test_load_kedro_objects_not_in_kedro_project(self, tmp_path, mocker):
        mocker.patch(
            "kedro.framework.startup._get_project_metadata",
            side_effect=RuntimeError,
        )
        mock_ipython = mocker.patch("kedro.extras.extensions.ipython.get_ipython")

        with pytest.raises(RuntimeError):
            reload_kedro(tmp_path)
        assert not mock_ipython().called
        assert not mock_ipython().push.called


class TestLoadIPythonExtension:
    @pytest.mark.parametrize(
        "error,expected_log_message,level",
        [
            (
                ImportError,
                "Kedro appears not to be installed in your current environment.",
                "ERROR",
            ),
            (
                RuntimeError,
                "Kedro extension was registered. Make sure you pass the project path to "
                "`%reload_kedro` or set it using `%init_kedro`.",
                "WARNING",
            ),
        ],
    )
    def test_load_extension_not_in_kedro_env_or_project(
        self, error, expected_log_message, level, mocker, caplog
    ):
        mocker.patch(
            "kedro.framework.startup._get_project_metadata",
            side_effect=error,
        )
        mock_ipython = mocker.patch("kedro.extras.extensions.ipython.get_ipython")

        load_ipython_extension(mocker.MagicMock())

        assert not mock_ipython().called
        assert not mock_ipython().push.called

        log_messages = [
            record.getMessage()
            for record in caplog.records
            if record.levelname == level
        ]
        assert log_messages == [expected_log_message]