defmodule EnergyGateway.WebServer do
  use GenServer
  require Logger

  @name __MODULE__

  def start_link(_) do
    GenServer.start_link(__MODULE__, nil, name: @name)
  end

  @impl true
  def init(_) do
    port = Application.get_env(:energy_gateway, :ws_port, 8765)

    dispatch = :cowboy_router.compile([
      {:_, [
        {"/ws", EnergyGateway.WsHandler, []},
        {"/health", EnergyGateway.HealthHandler, []}
      ]}
    ])

    case :cowboy.start_clear(:http_listener, [{:port, port}], %{env: %{dispatch: dispatch}}) do
      {:ok, _pid} ->
        Logger.info("Energy Gateway HTTP listener started on port #{port}")
        {:ok, %{port: port}}

      {:error, reason} ->
        {:stop, reason}
    end
  end

  @impl true
  def terminate(_reason, _state) do
    :ok = :cowboy.stop_listener(:http_listener)
    :ok
  end
end
