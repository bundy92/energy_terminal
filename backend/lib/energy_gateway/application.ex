defmodule EnergyGateway.Application do
  @moduledoc false

  use Application
  require Logger

  def start(_type, _args) do
    port = Application.get_env(:energy_gateway, :ws_port, 8765)
    start_time = System.monotonic_time(:second)
    Application.put_env(:energy_gateway, :start_time, start_time)

    children = [
      EnergyGateway.EtsCache,
      EnergyGateway.RateLimiter,
      EnergyGateway.FeedRegistry,
      EnergyGateway.DataRouter,
      EnergyGateway.MarketFeedServer,
      EnergyGateway.EiaFeedServer,
      EnergyGateway.WeatherFeedServer,
      EnergyGateway.FredFeedServer,
      EnergyGateway.WebServer
    ]

    Logger.info("Starting Energy Gateway on ws://localhost:#{port}/ws")

    Supervisor.start_link(children,
      strategy: :one_for_one,
      max_restarts: 5,
      max_seconds: 10
    )
  end
end
