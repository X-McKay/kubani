"""Tests for transport mode utilities."""


from kubani.framework.mcp.server.transport import TransportConfig, TransportMode


class TestTransportMode:
    """Tests for TransportMode enum."""

    def test_modes_exist(self):
        assert TransportMode.STDIO.value == "stdio"
        assert TransportMode.SSE.value == "sse"
        assert TransportMode.HTTP.value == "http"


class TestTransportConfig:
    """Tests for TransportConfig."""

    def test_default_config(self):
        config = TransportConfig()
        assert config.mode == TransportMode.STDIO
        assert config.host == "0.0.0.0"
        assert config.port == 8080

    def test_from_args_stdio(self):
        config = TransportConfig.from_args(["--mode", "stdio"])
        assert config.mode == TransportMode.STDIO

    def test_from_args_sse(self):
        config = TransportConfig.from_args(["--mode", "sse", "--port", "9000"])
        assert config.mode == TransportMode.SSE
        assert config.port == 9000

    def test_from_args_http(self):
        config = TransportConfig.from_args(
            ["--mode", "http", "--host", "127.0.0.1", "--port", "8888"]
        )
        assert config.mode == TransportMode.HTTP
        assert config.host == "127.0.0.1"
        assert config.port == 8888

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MCP_TRANSPORT", "sse")
        monkeypatch.setenv("MCP_HOST", "localhost")
        monkeypatch.setenv("MCP_PORT", "7777")

        config = TransportConfig.from_env()
        assert config.mode == TransportMode.SSE
        assert config.host == "localhost"
        assert config.port == 7777

    def test_from_env_defaults(self, monkeypatch):
        # Clear any existing env vars
        monkeypatch.delenv("MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("MCP_HOST", raising=False)
        monkeypatch.delenv("MCP_PORT", raising=False)

        config = TransportConfig.from_env()
        assert config.mode == TransportMode.STDIO
        assert config.host == "0.0.0.0"
        assert config.port == 8080

    def test_from_args_with_allowed_hosts(self):
        config = TransportConfig.from_args(
            ["--mode", "sse", "--allowed-hosts", "example.com:*,api.example.com:443"]
        )
        assert "example.com:*" in config.allowed_hosts
        assert "api.example.com:443" in config.allowed_hosts
        # Should also have localhost defaults
        assert "localhost:*" in config.allowed_hosts
