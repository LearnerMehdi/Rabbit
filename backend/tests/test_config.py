import config
from chat import chat_available


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


def test_project_config_loads():
    s = config.load(env={})
    assert s.port == 8000
    assert s.embed_model == "Qwen/Qwen3-Embedding-0.6B"
    assert s.embed_dim == 1024
    assert s.chat_top_k == 8
    assert s.data_dir == config.PROJECT_ROOT / "backend" / "data"


def test_values_come_from_the_file(tmp_path):
    p = write(tmp_path, "server: {port: 9001}\nchat: {top_k: 3, llm: {model: some/model}}\n")
    s = config.load(p, env={})
    assert (s.port, s.chat_top_k, s.llm_model) == (9001, 3, "some/model")
    assert s.chunk_size == 500  # missing keys fall back to defaults


def test_environment_overrides_one_value(tmp_path):
    p = write(tmp_path, "server: {port: 9001}\ndatabase: {url: postgresql://file}\n")
    s = config.load(p, env={"RABBIT_PORT": "9100"})
    assert s.port == 9100
    assert s.database_url == "postgresql://file"


def test_relative_data_dir_is_relative_to_project(tmp_path):
    p = write(tmp_path, "storage: {data_dir: some/where}\n")
    assert config.load(p, env={}).data_dir == config.PROJECT_ROOT / "some" / "where"


def test_api_key_is_read_from_the_named_variable(tmp_path):
    p = write(tmp_path, "chat: {llm: {api_key_env: MY_KEY}}\n")
    assert config.load(p, env={"MY_KEY": "secret"}).llm_api_key == "secret"
    no_key = config.load(p, env={})
    assert no_key.llm_api_key is None
    assert not chat_available(no_key)
